# Smart Contract Upgradeability — EMSE Artifacts

This repository accompanies the EMSE submission **“Immutable in Principle, Upgradeable by Design: Exploratory Study of Smart Contract Upgradeability.”**  
It focuses on the **artifact bundle** (datasets + analysis code).

---

## Repository Layout

```
.
├─ paper/
│  └─ Immutable_in_Principle___Modified_Version__EMSE___Last_Revision_.pdf
├─ artifact/
│  └─ Smart Contract Upgradeability-EMSE-R2-20251001T171149Z-1-001.zip
└─ README.md
```

**Artifact ZIP:** `Smart Contract Upgradeability-EMSE-R2-20251001T171149Z-1-001.zip`
SHA-256: `13c19430029154dd0e5766b4851614681a30e38d7586a1e2cc1b064f6cbffc51`

**Paper PDF:** `Immutable_in_Principle___Modified_Version__EMSE___Last_Revision_.pdf`
SHA-256: `48a5ebffb9cca8a9e99a3a9862472f62a564384c5f0432f07388fc619678925f`

---

## Quick Start

**Unpack the artifact**

**macOS/Linux**
```bash
mkdir -p artifact/unpacked
unzip "artifact/Smart Contract Upgradeability-EMSE-R2-20251001T171149Z-1-001.zip" -d artifact/unpacked
```

**Windows (PowerShell)**
```powershell
New-Item -ItemType Directory -Force artifact\unpacked | Out-Null
Expand-Archive -Path "artifact\Smart Contract Upgradeability-EMSE-R2-20251001T171149Z-1-001.zip" -DestinationPath "artifact\unpacked"
```

---

## Artifact Contents Overview

Below is a compact preview of the ZIP structure (depth ≤ 3):

```
├─ Smart Contract Upgradeability-EMSE-R2/
│  ├─ Dataset/
│  │  ├─ Evaluation/
│  │  │  ├─ 10-pairs-false_negative_analysis.csv
│  │  │  ├─ 50-pair-security-fix-reviewers.csv
│  │  │  ├─ UPC-Classification-Evaluation.csv
│  │  ├─ RQ2-Events/
│  │  │  ├─ Event-Addresses/
│  │  │  ├─ Versions/
│  │  │  ├─ FunctionUpdate(bytes4,address,address,string).json
│  │  │  ├─ ImplChanged(address,address).json
│  │  │  ├─ ImplementationUpdated(address).json
│  │  │  ├─ NewImplementation(address,address).json
│  │  │  ├─ NewImplementation(bytes32,bytes32,address).json
│  │  │  ├─ ProxyUpdated(address,address).json
│  │  │  ├─ TargetUpdated(address).json
│  │  │  ├─ Upgraded(address).json
│  │  │  ├─ Upgraded(address)X3.json
│  │  │  ├─ Upgraded(address)X4.json
│  │  │  ├─ Upgraded(uint256,address).json
│  │  ├─ Sample Data/
│  │  │  ├─ RQ2&4-Sample.csv
│  │  │  ├─ RQ3_Sample_Final.csv
│  │  ├─ RQ2-RQ4.csv
│  │  ├─ RQ4-top_20_proxies_data.csv
│  │  ├─ Sampling_proxy_events.csv
│  ├─ Source-Code/
│  │  ├─ Classification.py
│  │  ├─ DataCollection.ipynb
│  │  ├─ RQ2-Events.ipynb
│  │  ├─ RQ3.ipynb
│  │  ├─ RQ4.ipynb
```

> Tip: Use the files under **Dataset/** for immediate analysis; start with small samples in `Dataset/Sample Data/`.

### Analysis Code
_(Open `Source-Code/` to find notebooks and scripts. If present, `Classification.py` detects upgradeable proxy patterns from decompiled `.txt` files and writes `results.csv`.)_

---

## Running the Analyses

1. **Create an environment (optional)**
   ```bash
   python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
   ```
2. **Install common packages**
   ```bash
   pip install pandas numpy tqdm requests web3 jupyter matplotlib scikit-learn
   ```
3. **Open notebooks**
   ```bash
   jupyter lab   # or: jupyter notebook
   # Navigate to: artifact/unpacked/<unzipped-root>/Source-Code/
   ```
4. **(Optional) Run the classifier**
   - Provide a folder of `.txt` **decompiled contracts** (one file per address).
   - Edit the input folder path inside `Classification.py` and run:
   ```bash
   python artifact/unpacked/<unzipped-root>/Source-Code/Classification.py
   ```

---

## Data Notes

- CSVs may contain an automatic index column like `Unnamed: 0`; it is safe to drop:
  ```python
  import pandas as pd
  df = pd.read_csv("file.csv").loc[:, lambda x: ~x.columns.str.startswith("Unnamed")]
  ```
- JSON pages under `Dataset/RQ2-Events/` are raw event responses useful for reconstructing version lineages.

---

## Requirements

- **Python** ≥ 3.9 (tested with 3.10+)
- Suggested: `pandas`, `numpy`, `tqdm`, `requests`, `web3`, `jupyter`, `matplotlib`, `scikit-learn`
- Optional: Access to an Ethereum RPC/explorer API if you plan to refresh on-chain data

---

## License

- **Data & notebooks:** CC BY 4.0  
- **Scripts:** MIT

---

## Contact

- Ilham Qasse — Reykjavik University — ilham20@ru.is
