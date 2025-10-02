import re
import os
import csv
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from web3 import Web3

# === Configuration ===
RPC_URL = "xx"  # Replace with your Infura project ID
DEDAUB_API_KEY = "xxx"  # Replace with your Dedaub API key
DEDAUB_BASE_URL = "https://api.dedaub.com/api/on_demand"
REQUEST_TIMEOUT = 30  # Timeout (seconds) for requests
DIAMOND_STORAGE_SLOT = "0xc8fcad8db84d3cc18b4c41d551ea0ee66dd599cde068d998e57d5e09332c131c"

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# Helper Functions

def clean_line(line):
    return re.sub(r'//.*', '', line).strip()

def is_diamond_proxy(decompiled_code, contract_address):
    """Comprehensive Diamond proxy detection"""
    results = {
        'is_diamond': False,
        'is_upgradeable': False,
        'facet_address': None,
        'details': []
    }

    # First check for Diamond storage slot pattern in decompiled code
    if DIAMOND_STORAGE_SLOT.lower() in decompiled_code.lower():
        results['is_diamond'] = True
        results['details'].append("Diamond storage slot found")
    else:
        # Early return if not a Diamond
        results['details'].append("No Diamond storage slot found")
        return results

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    try:
        checksum_addr = Web3.to_checksum_address(contract_address)
        
        # Try to call facetAddress(0x1f931c1c) - diamondCut selector
        selector = "0x1f931c1c"
        calldata = (
            "0xcdffacc6" +                    # facetAddress(bytes4)
            selector.ljust(66, '0')[2:]       # Right-padded selector
        )
        
        result = w3.eth.call({
            'to': checksum_addr,
            'data': calldata
        }).hex()
        
        # Parse result (address is last 20 bytes)
        facet_address = "0x" + result[-40:]
        
        if facet_address == "0x" + "00" * 20:
            results['details'].append("DiamondCut function not found")
            return results
            
        results['facet_address'] = facet_address
        results['details'].append(f"Facet address: {facet_address}")
        
        # Check facet code for DiamondCut pattern
        facet_code = w3.eth.get_code(Web3.to_checksum_address(facet_address)).hex()
        if facet_code and facet_code != "0x":
            # Decompile the facet code
            try:
                decompiled_facet = decompile_bytecode(facet_code)
                
                # Search for emit DiamondCut in decompiled code
                diamond_cut_pattern = re.compile(r'emit\s+DiamondCut\s*\(', re.IGNORECASE)
                if diamond_cut_pattern.search(decompiled_facet):
                    results['is_upgradeable'] = True
                    results['details'].append("UPGRADEABLE (emit DiamondCut found in facet)")
                else:
                    results['details'].append("Non-upgradeable Diamond (no emit DiamondCut in facet)")
            except Exception as e:
                results['details'].append(f"Decompilation failed: {str(e)}")
                logging.error(f"Decompilation failed for {facet_address}: {e}")
                
    except Exception as e:
        logging.error(f"Blockchain query failed for {contract_address}: {e}")
        results['details'].append(f"Error: {str(e)}")
    
    return results

def check_storage_slot_modification(decompiled_code, target_slot):
    """
    Checks if 'target_slot' is modified in 'decompiled_code' e.g. sstore(slot, X) or storage[slot] = X
    """
    tslot = target_slot.lower()
    sstore_pat = rf'sstore\s*\(\s*({tslot})\s*,'
    storage_pat = rf'storage\[({tslot})\]'
    return bool(re.search(sstore_pat, decompiled_code.lower()) or re.search(storage_pat, decompiled_code.lower()))



# Single-Step Decompiler
def decompile_bytecode(bytecode):
    """
    Single-step decompile using Dedaub On-Demand.
    """
    headers = {"x-api-key": DEDAUB_API_KEY, "Content-Type": "application/json"}
    try:
        logging.info("Sending decompilation request to Dedaub API")
        response = requests.post(DEDAUB_BASE_URL, headers=headers, json=bytecode, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        md5 = response.json()
        status_url = f"{DEDAUB_BASE_URL}/{md5}/status"

        max_retries = 10
        for attempt in range(1, max_retries + 1):
            logging.info(f"Checking decompilation status (attempt {attempt})")
            status_response = requests.get(status_url, headers=headers, timeout=REQUEST_TIMEOUT)
            status_response.raise_for_status()
            status = status_response.json()

            if status == "COMPLETED":
                decompile_url = f"{DEDAUB_BASE_URL}/decompilation/{md5}"
                decompile_response = requests.get(decompile_url, headers=headers, timeout=REQUEST_TIMEOUT)
                decompile_response.raise_for_status()
                logging.info("Decompilation completed successfully")
                return decompile_response.json().get("source", "")
            elif status in ["UNKNOWN", "SCHEDULED", "DECOMPILATION_STARTED", "ANALYSIS_STARTED", "ANALYSIS_ENDED"]:
                time.sleep(5)
            else:
                logging.error(f"Unexpected status: {status}")
                raise Exception(f"Unexpected status: {status}")

        # If we exit loop, max tries reached
        logging.error("Max retries reached without completion")
        raise Exception("Max retries reached without completion")

    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed: {e}")
        raise Exception(f"Request failed: {e}")



# The Main Classification - Scans All Delegatecalls
def resolve_delegate_target(all_lines, impl_var):
    """
    Resolves delegate-call target variables that come from getter functions.

    Handles all of:
      ①  vX   = someVar.someGetter();
      ②  v0, v1 = ContractVar.someGetter().gas(...);   # tuple + .gas (Beacon)
      ③  (any tuple form) where impl_var is one of the LHS items.

    Returns:
        * concrete variable name that the getter ultimately returns, **or**
        * "__getter_missing_code__"  – getter body not found (likely external), **or**
        * None                       – no getter pattern detected / unresolved.
    """
    candidate   = None          # variable that getter 'return's
    getter_func = None          # getter function name we spot
        
    for i in range(len(all_lines) - 1, -1, -1):
        raw = all_lines[i]
        if '=' not in raw:
            continue

        lhs, rhs = raw.split('=', 1)

        if not re.search(rf'\b{re.escape(impl_var)}\b', lhs):
            continue

        m = re.search(r'\.\s*(\w+)\s*\(\)\s*(?:\.gas)?', rhs)
        if m:
            getter_func = m.group(1)
            logging.info(f"[Resolver] {impl_var} set via getter .{getter_func}() in line: {raw.strip()}")
            break

    if not getter_func:
        logging.info(f"[Resolver] No getter-based assignment for {impl_var} — keeping as-is")
        return None

    getter_found = False
    for i in range(len(all_lines)):
        clean = clean_line(all_lines[i])
        if re.match(rf'\s*function\s+{re.escape(getter_func)}\s*\(', clean):
            getter_found = True
            logging.info(f"[Resolver] Found getter declaration: {clean.strip()}")
            for j in range(i, min(i + 20, len(all_lines))):
                ret = re.search(r'\breturn\s+(\w+)\s*;', all_lines[j])
                if ret:
                    candidate = ret.group(1)
                    logging.info(f"[Resolver] Getter {getter_func}() returns variable '{candidate}'")
                    break
            break

    # Getter referenced but **not** present ⇒ probably an external contract
    if not getter_found:
        logging.info(f"[Resolver] Getter '{getter_func}()' referenced but definition missing")
        return "__getter_missing_code__"

    # Getter found but we couldn't dig out a return variable
    if not candidate:
        logging.info(f"[Resolver] Getter '{getter_func}()' found but return variable unresolved")
        return None

    logging.info(f"[Resolver] Resolved delegate target: {impl_var} → {candidate} via {getter_func}()")
    return candidate

# Full proxy-classification 

def detect_delegatecall_and_address(file_path):
    try:
        logging.info(f"\n----- Analyzing file: {file_path} -----")
        with open(file_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        all_code         = "".join(all_lines)
        contract_address = os.path.basename(file_path).replace(".txt", "")

        def _find_return_var(decomp_code: str, getter_name: str):
            """Locate the variable returned by `getter_name()` in `decomp_code`."""
            src = decomp_code.splitlines()
            for k, ln in enumerate(src):
                if re.match(rf'\s*function\s+{re.escape(getter_name)}\s*\(', ln):
                    for j in range(k, min(k + 30, len(src))):
                        m = re.search(r'\breturn\s+(\w+)\s*;', src[j])
                        if m:
                            return m.group(1)
                    break
            return None

        def _var_is_reassigned(decomp_code: str, var_name: str):
            """Heuristic: var_name appears on LHS of assignment inside an upgrade function."""
            if not re.search(rf'\b{re.escape(var_name)}\b\s*=', decomp_code):
                return False
            
            if re.search(r'function\s+(?:upgrade|upgradeTo)\w*\s*\(', decomp_code, re.IGNORECASE):
                return True
            
            return True

        def _external_getter_flow(all_lines_local, delegate_idx, impl_var_local, proxy_addr):
            span = range(delegate_idx - 1, max(-1, delegate_idx - 60), -1)
            for j in span:
                raw = all_lines_local[j]
                if '=' not in raw:
                    continue
                lhs, rhs = raw.split('=', 1)
                if not re.search(rf'\b{re.escape(impl_var_local)}\b', lhs):
                    continue

                m_rhs = re.search(r'([\S]+?)\.(\w+)\s*\(\)\s*(?:\.gas)?', rhs)
                if not m_rhs:
                    continue

                contract_expr     = m_rhs.group(1).strip()
                getter_name       = m_rhs.group(2)
                logging.info(f"[External Getter] Candidate line: {raw.strip()}")

                # Determine external contract address 
                w3       = Web3(Web3.HTTPProvider(RPC_URL))
                ext_addr = None

                m_static = re.match(r'address\(\s*(0x[a-fA-F0-9]{40})\s*\)', contract_expr, re.IGNORECASE)
                if m_static:
                    ext_addr = Web3.to_checksum_address(m_static.group(1))
                    logging.info(f"[External Getter] Static address {ext_addr}")

                else:
                    var_name      = contract_expr
                    slot_hex      = None
                    for ln in all_lines_local:
                        dm = re.search(
                            rf'\b(?:address|uint256)\s+{re.escape(var_name)}\s*;\s*//\s*STORAGE\[(0x[a-fA-F0-9]+)\]',
                            ln
                        )
                        if dm:
                            slot_hex = dm.group(1).lower()
                            logging.info(f"[External Getter] {var_name} stored in slot {slot_hex}")
                            break
                    if slot_hex:
                        try:
                            proxy_cs = Web3.to_checksum_address(proxy_addr)
                            stored   = w3.eth.get_storage_at(proxy_cs, int(slot_hex, 16))
                            ext_addr = Web3.to_checksum_address("0x" + stored.hex()[-40:])
                            logging.info(f"[External Getter] Slot resolved to {ext_addr}")
                        except Exception as e:
                            logging.warning(f"[External Getter] eth_getStorageAt failed: {e}")

                if not ext_addr or ext_addr.lower() == "0x" + "00"*20:
                    continue  # couldn't resolve address; keep looking

                #Decompile the external contract & inspect
                try:
                    code_hex = w3.eth.get_code(ext_addr).hex()
                    if code_hex in ("0x", ""):
                        logging.info(f"[External Getter] {ext_addr} has no code")
                        continue

                    decomp    = decompile_bytecode(code_hex)
                    ret_var   = _find_return_var(decomp, getter_name)
                    if not ret_var:
                        logging.info(f"[External Getter] Couldn't find return var of {getter_name}()")
                        continue

                    if _var_is_reassigned(decomp, ret_var):
                        detail = (
                            f"External getter {getter_name}() in {ext_addr} returns "
                            f"'{ret_var}' which IS reassigned in an upgrade function"
                        )
                        logging.info(f"[Upgrade Detected] {detail}")
                        return ("Upgradeable proxy", detail, all_lines_local, impl_var_local, None, None)
                    else:
                        # not upgradeable via this path; continue outer logic
                        logging.info(f"[External Getter] '{ret_var}' never reassigned – no upgrade path")
                except Exception as decomp_e:
                    logging.warning(f"[External Getter] Decompilation failed: {decomp_e}")
            return None
    

        diamond_info = is_diamond_proxy(all_code, contract_address)
        if diamond_info['is_diamond']:
            det = " | ".join(diamond_info['details'])
            cls = "Diamond proxy" + (" (Upgradeable)" if diamond_info['is_upgradeable'] else "")
            return cls, det, all_lines, diamond_info['facet_address'], None, None

        found_delegatecalls = False
        first_impl_var      = None
        del_pat             = re.compile(r'(\w+(?:\[[^\]]+\])?)\.delegatecall\(')

        fb_start = next((i for i, ln in enumerate(all_lines)
                         if clean_line(ln).startswith('function fallback()')), None)
        fb_end   = None
        if fb_start is not None:
            braces = 0
            for i in range(fb_start, len(all_lines)):
                braces += all_lines[i].count('{') - all_lines[i].count('}')
                if braces == 0 and i > fb_start:
                    fb_end = i
                    break

        for idx, ln in enumerate(all_lines):
            c_ln   = clean_line(ln)
            match  = del_pat.search(c_ln)
            impl_v = None

            if not match:
                if ".delegatecall(" in c_ln:              # slow-path extraction
                    pos  = c_ln.find(".delegatecall(")
                    i    = pos - 1
                    br   = pr = 0
                    buf  = []
                    while i >= 0:
                        ch = c_ln[i]
                        if   ch == ']': br += 1
                        elif ch == ')': pr += 1
                        elif ch == '[' and br: br -= 1
                        elif ch == '(' and pr: pr -= 1
                        elif (ch.isspace() or ch == '=') and not br and not pr:
                            break
                        buf.append(ch); i -= 1
                    buf.reverse()
                    if buf: impl_v = "".join(buf)
                else:
                    continue
            else:
                impl_v = match.group(1)

            found_delegatecalls = True
            if not first_impl_var:
                first_impl_var = impl_v

            # Resolve getter (internal)
            resolved = resolve_delegate_target(all_lines, impl_v)
            if resolved == "__getter_missing_code__":
                # Try external getter tracing
                external_result = _external_getter_flow(all_lines, idx, impl_v, contract_address)
                if external_result:
                    return external_result
                # If external tracing fails, keep original variable for storage checks
            elif resolved:
                impl_v = resolved

            # Extract STORAGE slot (constant hex in comments)
            slot_hex = slot_ascii = None
            for l in all_lines:
                if impl_v in l and 'STORAGE[' in l:
                    slot_match = re.search(r'STORAGE\[(0x[a-fA-F0-9]+)\]', l)
                    if slot_match:
                        slot_hex = slot_match.group(1).lower()
                        logging.info(f"[Storage Slot] Found slot_hex = {slot_hex}")
                        try:
                            ascii_candidate = bytes.fromhex(slot_hex[2:]).rstrip(b'\x00').decode('utf-8')
                            slot_ascii = ascii_candidate
                            logging.info(f"[Storage Slot] Decoded slot_ascii = '{slot_ascii}'")
                        except Exception as e:
                            logging.warning(f"[Storage Slot] Could not decode ASCII from slot: {e}")
                    break

            # Check 1: Direct assignment to implementation variable
            direct_assignment = any(
                re.search(rf'{re.escape(impl_v)}\s*=', clean_line(l))
                for i, l in enumerate(all_lines)
                if fb_start is None or i < fb_start or (fb_end and i > fb_end)
            )
            logging.info(f"[Check] Direct assignment to {impl_v}: {'YES' if direct_assignment else 'NO'}")
            if direct_assignment:
                return "Upgradeable proxy", f"Direct assignment to {impl_v}", all_lines, impl_v, None, None

            # Check 2: Assignment to constant hex slot 
            if slot_hex:
                hex_written = any(
                    re.search(
                        rf'(sstore\s*\(\s*{re.escape(slot_hex)}\s*,|storage\[\s*{re.escape(slot_hex)}\s*\]\s*=)',
                        clean_line(l), re.IGNORECASE
                    )
                    for i, l in enumerate(all_lines)
                    if fb_start is None or i < fb_start or (fb_end and i > fb_end)
                )
                logging.info(f"[Check] Hex slot {slot_hex} assignment: {'YES' if hex_written else 'NO'}")
                if hex_written:
                    return "Upgradeable proxy", f"Write to hex slot {slot_hex}", all_lines, impl_v, None, None

            # Check 3: Assignment to STORAGE[keccak256('ascii')] (constant string key)
            if slot_ascii:
                ascii_written = any(
                    re.search(
                        rf"STORAGE\s*\[\s*keccak256\(\s*['\"]{re.escape(slot_ascii)}['\"]\s*\)\s*\]\s*=",
                        clean_line(l), re.IGNORECASE
                    )
                    for i, l in enumerate(all_lines)
                    if fb_start is None or i < fb_start or (fb_end and i > fb_end)
                )
                logging.info(f"[Check] ASCII slot keccak('{slot_ascii}') assignment: {'YES' if ascii_written else 'NO'}")
                if ascii_written:
                    logging.info(f"[Upgrade Detected] Assignment to STORAGE[keccak256('{slot_ascii}')] found")
                    return "Upgradeable proxy", f"Detected assignment to STORAGE[keccak256('{slot_ascii}')]", all_lines, impl_v, None, None

            # Check 4: Matching dynamic keccak256 string literal
            if (not slot_ascii) and "keccak256(" in impl_v:
                mem_expr_match = re.search(r"keccak256\((MEM\[.+?\])\)", impl_v)
                if mem_expr_match:
                    mem_expr = mem_expr_match.group(1)
                    # Find the string literal used for this storage slot
                    string_literal = None
                    for full_line in all_lines:
                        m = re.search(rf"{re.escape(mem_expr)}\s*=\s*['\"]([^'\"]+)['\"]", full_line)
                        if m:
                            string_literal = m.group(1)
                            break
                    if string_literal:
                        logging.info(f"[Storage Slot] Derived string literal: '{string_literal}'")
                        # Check if that string's hash is used in any storage write
                        ascii_written_dynamic = any(
                            ("STORAGE[keccak256(" in l) and ('=' in l) and ("!=" not in l) and ("==" not in l)
                            for j, l in enumerate(all_lines)
                            if fb_start is None or j < fb_start or (fb_end and j > fb_end)
                        )
                        logging.info(f"[Check] Dynamic keccak slot '{string_literal}' assignment: {'YES' if ascii_written_dynamic else 'NO'}")
                        if ascii_written_dynamic:
                            logging.info(f"[Upgrade Detected] Matching keccak256 storage key '{string_literal}' used in read/write")
                            return "Upgradeable proxy", f"Detected assignment to STORAGE[keccak256('{string_literal}')]", all_lines, impl_v, None, None
                    else:
                        logging.info("[Storage Slot] No string literal found for dynamic slot")
            if slot_hex:
                try:
                    w3 = Web3(Web3.HTTPProvider(RPC_URL))
                    checksum_address = Web3.to_checksum_address(contract_address)
                    stored_val = w3.eth.get_storage_at(checksum_address, int(slot_hex, 16)).hex()
                    impl_address = "0x" + stored_val[-40:]
                    if re.fullmatch(r'0x[a-fA-F0-9]{40}', impl_address):
                        code_hex = w3.eth.get_code(Web3.to_checksum_address(impl_address)).hex()
                        if not code_hex.startswith("0x"):
                            code_hex = "0x" + code_hex

                        try:
                            decompiled_code = decompile_bytecode(code_hex)
                            if check_storage_slot_modification(decompiled_code, slot_hex):
                                logging.info(f"Implementation contract modifies slot {slot_hex}")
                                return (
                                    "Upgradeable proxy",
                                    f"Implementation modifies slot {slot_hex}",
                                    all_lines,
                                    impl_v,
                                    None,
                                    None
                                )
                        except Exception as decomp_err:
                            logging.warning(f"Decompilation failed for {impl_address}: {decomp_err}")
                except Exception as e:
                    logging.warning(f"Failed fallback dynamic check: {e}")

        # Final classification
        if found_delegatecalls:
            return ("Forward proxy", "Found delegatecall(s), none are upgradeable",
                    all_lines, first_impl_var, None, None)

        return ("Not a proxy", "No delegatecall found & no Diamond pattern",
                all_lines, None, None, None)

    except Exception as e:
        logging.error(f"[Error] detect_delegatecall_and_address failed: {e}")
        return ("Error", str(e), None, None, None, None)


# The main multi-thread approach + CSV writing

def process_file(file_path):
    try:
        logging.info(f"Processing file: {file_path}")
        classification, details, full_sevm_output, impl_var, update_line_num, update_line = detect_delegatecall_and_address(file_path)
        contract_address = os.path.basename(file_path).replace(".txt", "")
        logging.info(f"Completed processing file: {file_path}")

        return {
            'Contract Address': contract_address,
            'Classification': classification,
            'Details': details,
            'Implementation Variable': impl_var if impl_var else "N/A"
        }
    except Exception as e:
        logging.error(f"Error processing file {file_path}: {e}")
        return {
            'Contract Address': os.path.basename(file_path).replace(".txt", ""),
            'Classification': "Error",
            'Details': str(e),
            'Implementation Variable': "N/A"
        }

def main():
    folder_path = "xxx"  # your folder of decompiled files (.txt), the should be named with the contract address
    output_csv = "results.csv"

    if not os.path.exists(folder_path):
        logging.error(f"Error: Folder '{folder_path}' does not exist.")
        return

    files = [f for f in os.listdir(folder_path) if f.endswith(".txt")]
    if not files:
        logging.error(f"No .txt files found in '{folder_path}'.")
        return

    logging.info(f"Found {len(files)} files to process.")
    start_time = time.time()

    with open(output_csv, mode='w', newline='') as csv_file:
        fieldnames = ['Contract Address', 'Classification', 'Details', 'Implementation Variable']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for filename in files:
                path = os.path.join(folder_path, filename)
                logging.info(f"Submitting file for processing: {path}")
                futures.append(executor.submit(process_file, path))

            for future in as_completed(futures):
                try:
                    row = future.result()
                    results.append(row)
                    logging.info(f"Processed file: {row['Contract Address']}")
                except Exception as e:
                    logging.error(f"Error processing file: {e}")

        writer.writerows(results)

    end_time = time.time()
    total_time = end_time - start_time
    logging.info(f"\nTotal time taken: {total_time:.2f} seconds")

if __name__ == '__main__':
    main()