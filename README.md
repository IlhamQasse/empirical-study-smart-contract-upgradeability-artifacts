# Empirical Study on Smart Contract Upgradeability

This repository accompanies the EMSE submission **“Immutable in Principle, Upgradeable by Design: Exploratory Study of Smart Contract Upgradeability.”**  
It focuses on the **artifact bundle** (datasets + analysis code).

---

## Repository Layout

```
.
├─ paper/
│  └─ Immutable_in_Principle___Modified_Version__EMSE___Last_Revision_.pdf
├─ artifact/
│  └─ EMSE-R2/
│     ├─ Dataset/
│     │  ├─ RQ2-Events/
│     │  ├─ Evaluation/
│     │  ├─ Sample Data/
│     │  ├─ RQ2-RQ4.csv
│     │  └─ RQ4-top_20_proxies_data.csv
│     └─ Source-Code/
│        ├─ DataCollection.ipynb
│        ├─ RQ2-Events.ipynb
│        ├─ RQ3.ipynb
│        ├─ RQ4.ipynb
│        └─ Classification.py
└─ README.md
```

> If your unzipped folder has a different name, replace `artifact/EMSE-R2/` accordingly.

---

## Quick Start

### 1) Create an environment (optional)
```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
```

### 2) Install common packages
```bash
pip install pandas numpy tqdm requests web3 jupyter matplotlib scikit-learn
```

### 3) Open notebooks
```bash
jupyter lab   # or: jupyter notebook
# Navigate to: artifact/EMSE-R2/Source-Code/
```

### 4) (Optional) Run the classifier
- Provide a folder of `.txt` **decompiled contracts** (one file per address).
- Edit the input folder path inside `Classification.py` and run:
```bash
python artifact/EMSE-R2/Source-Code/Classification.py
```

---

## Data Notes

- CSVs may contain an automatic index column like `Unnamed: 0`; it is safe to drop:
  ```python
  import pandas as pd
  df = pd.read_csv("file.csv").loc[:, lambda x: ~x.columns.str.startswith("Unnamed")]
  ```
- JSON pages under `Dataset/RQ2-Events/` are raw event responses useful for reconstructing version lineages.
- Start with `Dataset/Sample Data/` for quick execution before scaling up.

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

---

## How to Cite

If you use these artifacts or build on this work, please cite the paper:

**Plain text**
```
Qasse, I., Hamdaqa, M., & Jónsson, B. Þ. (2025).
Immutable in Principle, Upgradeable by Design: Exploratory Study of Smart Contract Upgradeability.
Empirical Software Engineering (EMSE). Under review.
```

**BibTeX**
```bibtex
@article{Qasse2025ImmutableUpgradeability,
  title   = {Immutable in Principle, Upgradeable by Design: Exploratory Study of Smart Contract Upgradeability},
  author  = {Qasse, Ilham and Hamdaqa, Mohammad and Jónsson, Björn Þór},
  journal = {Empirical Software Engineering},
  note    = {Under review},
  year    = {2025}
}
```


