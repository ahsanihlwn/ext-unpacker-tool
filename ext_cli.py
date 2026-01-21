# Derived from https://github.com/cubinator/ext4
# Original author: cubinator
# License: GNU General Public License v3.0
# Modifications: Split into standalone utility

import sys
import os

def print_help():
    print("EXT4 Tool CLI")
    print("Usage:")
    print("  --read   <path/to/image.img>")
    print("  --unpack <path/to/image.img>")
    sys.exit(1)

def main():
    if len(sys.argv) < 3:
        print_help()

    cmd = sys.argv[1]
    img = sys.argv[2]

    if not os.path.exists(img):
        print(f"[ERR] File not found: {img}")
        sys.exit(2)

    # ---- READ MODE ----
    if cmd == "--read":
        from check import check_ext4
        check_ext4(img)
        return

    # ---- UNPACK MODE ----
    if cmd == "--unpack":
        from unpack import main as unpack_main
        ok, out_dir = unpack_main(img)
        if ok:
            print("[OK] Unpack finished")
            print("Output:", out_dir)
        else:
            print("[ERR] Unpack failed")
        return

    print_help()

if __name__ == "__main__":
    main()
