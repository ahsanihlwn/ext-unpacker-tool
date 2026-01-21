# Derived from https://github.com/cubinator/ext4
# Original author: cubinator
# License: GNU General Public License v3.0
# Modifications: Split into standalone utility

from ext4 import Volume, MagicError, ext4_superblock
import sys, os
print("")
def detect_type(sb):
    # CORRECT journal bit
    has_journal = bool(sb.s_feature_compat & 0x4)  # HAS_JOURNAL

    # extents (EXT4 feature)
    has_extents = bool(sb.s_feature_incompat & 0x40)

    is_64bit = bool(sb.s_feature_incompat & ext4_superblock.INCOMPAT_64BIT)
    sparse_super2 = bool(sb.s_feature_ro_compat & 0x200)

    if sb.s_inode_size >= 256:
        fs = "EXT4" if has_extents else "EXT4 (Legacy)"
    else:
        if has_journal:
            fs = "EXT3"
        else:
            fs = "EXT2"

    return fs, has_journal, has_extents, is_64bit, sparse_super2

def check_ext4(img_path):
    if not os.path.exists(img_path):
        print("File not found!")
        return

    try:
        with open(img_path, "rb") as f:
            vol = Volume(f)
            sb = vol.superblock

        fs, journal, extents, is64, sparse2 = detect_type(sb)

        print("RennsAndroidKitchen CLI - EXT CHECKER")
        print("=================================")
        print("Valid EXT filesystem:", "YES" if sb.s_magic == 0xEF53 else "NO")
        print("Magic number       :", hex(sb.s_magic))
        print("Detected type      :", fs)
        print("Journal support    :", "YES" if journal else "NO")
        print("EXTENTS (EXT4)     :", "YES" if extents else "NO")
        print("64-bit mode        :", "YES" if is64 else "NO")
        print("Sparse Super2      :", "YES" if sparse2 else "NO")
        print("---------------------------------")
        print("Block size         :", vol.block_size)
        print("Block count        :", sb.s_blocks_count)
        print("Inode size         :", sb.s_inode_size)
        print("Volume name        :", sb.s_volume_name.decode(errors='ignore'))
        print("Mounted path       :", sb.s_last_mounted.decode(errors='ignore'))
        print("UUID               :", vol.uuid)
        print("=================================")

    except MagicError:
        print("Not EXT4 (Magic mismatch)")
    except Exception as e:
        print("Error reading image")
        print("Detail:", e)

def check_ext4_magic(img_path):
    """
    Return:
      "EXT4" / "EXT3" / "EXT2" / "" (kalau bukan EXT)
    """
    try:
        with open(img_path, "rb") as f:
            vol = Volume(f)
            sb = vol.superblock

        if sb.s_magic != 0xEF53:
            return ""

        fs, journal, extents, *_ = detect_type(sb)
        return fs  # "EXT4", "EXT3", "EXT2"

    except:
        return ""

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("   python check_ext4_full.py <path_to_img>")
        sys.exit(1)

    check_ext4(sys.argv[1])
