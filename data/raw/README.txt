NASA C-MAPSS raw dataset files go here.

This directory is gitignored. Download via:

    uv run python scripts/fetch_data.py

Or manually — download CMAPSSData.zip from:
  https://data.nasa.gov/dataset/cmapss-jet-engine-simulated-data

Then extract so the following files are present in this folder:

  data/raw/
  ├── train_FD001.txt
  ├── test_FD001.txt
  ├── RUL_FD001.txt
  ├── train_FD002.txt
  ├── test_FD002.txt
  ├── RUL_FD002.txt
  ... (FD003, FD004 same pattern)

If you already have only train_FD001.txt and test_FD001.txt (and RUL_FD001.txt),
that is sufficient to run M1–M3 with dataset=FD001.
