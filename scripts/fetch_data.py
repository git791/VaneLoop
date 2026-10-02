import urllib.request
import zipfile
import os

URL = "https://data.nasa.gov/docs/legacy/CMAPSSData.zip"
TARGET_ZIP = "data/raw/CMAPSSData.zip"
RAW_DIR = "data/raw/"

def download_data():
    os.makedirs(RAW_DIR, exist_ok=True)
    if not os.path.exists(TARGET_ZIP):
        print(f"Downloading from {URL}...")
        urllib.request.urlretrieve(URL, TARGET_ZIP)
        print("Download complete.")
        
    print(f"Extracting {TARGET_ZIP}...")
    with zipfile.ZipFile(TARGET_ZIP, 'r') as zip_ref:
        zip_ref.extractall(RAW_DIR)
    print("Extraction complete.")

if __name__ == "__main__":
    download_data()
