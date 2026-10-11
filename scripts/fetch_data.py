import os
import urllib.request
import zipfile

RAW_DIR = os.getenv("VANELOOP_DATA_DIR", "data/raw")
TARGET_ZIP = os.path.join(RAW_DIR, "CMAPSSData.zip")
NASA_URL = "https://data.nasa.gov/docs/legacy/CMAPSSData.zip"
GITHUB_MIRROR = "https://raw.githubusercontent.com/hankroark/Turbofan-Engine-Degradation/master/CMAPSSData"
FILES = [
    "train_FD001.txt", "train_FD002.txt", "train_FD003.txt", "train_FD004.txt",
    "test_FD001.txt", "test_FD002.txt", "test_FD003.txt", "test_FD004.txt",
    "RUL_FD001.txt", "RUL_FD002.txt", "RUL_FD003.txt", "RUL_FD004.txt",
]


def download_data():
    os.makedirs(RAW_DIR, exist_ok=True)

    # Check if primary dataset is already present
    if os.path.exists(os.path.join(RAW_DIR, "train_FD001.txt")):
        print("Data files already exist in", RAW_DIR)
        return

    # Attempt 1: Fast GitHub mirror (avoids NASA data.nasa.gov cloud timeouts)
    print("Fetching C-MAPSS dataset from fast GitHub mirror...")
    success = True
    for f in FILES:
        target_path = os.path.join(RAW_DIR, f)
        if not os.path.exists(target_path):
            url = f"{GITHUB_MIRROR}/{f}"
            try:
                print(f"Downloading {f}...")
                urllib.request.urlretrieve(url, target_path)
            except Exception as e:
                print(f"Failed to fetch {f} from mirror: {e}")
                success = False
                break

    if success and os.path.exists(os.path.join(RAW_DIR, "train_FD001.txt")):
        print("All data files downloaded successfully from mirror.")
        return

    # Attempt 2: NASA legacy zip fallback
    print(f"Falling back to NASA legacy zip from {NASA_URL}...")
    try:
        if not os.path.exists(TARGET_ZIP):
            urllib.request.urlretrieve(NASA_URL, TARGET_ZIP)
        with zipfile.ZipFile(TARGET_ZIP, "r") as zip_ref:
            zip_ref.extractall(RAW_DIR)
        print("Extraction complete.")
    except Exception as exc:
        print(f"NASA download failed: {exc}")


if __name__ == "__main__":
    download_data()
