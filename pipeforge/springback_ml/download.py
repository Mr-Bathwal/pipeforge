"""Download the TubeBEND pickle from Zenodo and verify its size and md5.

Only the 797 MB pickle is needed (the 1.47 GB STL zip is not used). The file
stays out of git (.gitignore); the derived per-run table that training uses
is committed under data/tubebend/derived with attribution.
"""

from __future__ import annotations

import sys
import urllib.request

from .load import MD5, RAW, SIZE, md5_of

URL = "https://zenodo.org/records/18458823/files/experiments_process_and_results.pkl?download=1"


def main() -> int:
    if RAW.exists() and RAW.stat().st_size == SIZE and md5_of(RAW) == MD5:
        print(f"{RAW} already present and verified")
        return 0
    RAW.parent.mkdir(parents=True, exist_ok=True)
    tmp = RAW.with_suffix(".part")
    print(f"downloading {URL}\n  -> {RAW} ({SIZE / 1e6:.0f} MB)")
    req = urllib.request.Request(URL, headers={"User-Agent": "pipeforge-download"})
    with urllib.request.urlopen(req, timeout=60) as resp, tmp.open("wb") as fh:
        done = 0
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
            done += len(chunk)
            if done % (50 << 20) < (1 << 20):
                print(f"  {done / 1e6:.0f} MB")
    if tmp.stat().st_size != SIZE or md5_of(tmp) != MD5:
        tmp.unlink(missing_ok=True)
        print("download did not match the published size/md5; deleted", file=sys.stderr)
        return 1
    tmp.replace(RAW)
    print("verified md5", MD5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
