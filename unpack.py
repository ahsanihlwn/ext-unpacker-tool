# Derived from https://github.com/cubinator/ext4
# Original author: cubinator
# License: GNU General Public License v3.0
# Modifications: Split into standalone utility


import os
import re
import struct
from check import detect_type
import ext4, ext3, ext2   # asumsi 3 file udah ada

# === CONFIG DASAR ===
Volume = None  # akan di-set runtime

base = os.path.dirname(__file__)
# Ganti ini kalau mau partisi lain, misal "system.img", "vendor.img"
img_path = os.path.join(base, "product.img")

# Nama partisi = nama file tanpa .img (product.img -> "product")
partition_name = os.path.splitext(os.path.basename(img_path))[0]

# Folder extract & file config
EXTRACT_DIR = os.path.join(base, partition_name)
CONFIG_DIR = os.path.join(base, "config") 


# ====== HELPER ======

def get_perm_from_modestr(mode_str: str) -> str:
    """
    Clone dari Extractor.__get_perm() di imgextractor.py
    Convert "drwxr-xr-x" -> "0755"
    """
    if len(mode_str) < 9 or len(mode_str) > 11:
        return ''
    # buang tipe file di depan (d, -, l, dsb)
    if len(mode_str) > 8:
        mode_str = mode_str[1:]

    o = s = w = g = 0
    perms = {'r': 4, 'w': 2, 'x': 1}

    for n, sym in enumerate(mode_str):
        if n == 0 and perms.get(sym):
            o = perms.get(sym)
        elif n == 1 and perms.get(sym):
            o += perms.get(sym)
        elif n == 2:
            if sym == 'S':
                s = 4
            elif perms.get(sym):
                o += perms.get(sym)
            elif sym == 's':
                s += 4
                o += 1
        elif n == 3 and perms.get(sym):
            g = perms.get(sym)
        elif n == 4 and perms.get(sym):
            g += perms.get(sym)
        if n == 5:
            if perms.get(sym):
                g += perms.get(sym)
            elif sym == 'S':
                s += 2
            elif sym == 's':
                s += 2
                g += 1
        elif n == 6 and perms.get(sym):
            w = perms.get(sym)
        elif n == 7 and perms.get(sym):
            w += perms.get(sym)
        elif n == 8:
            if perms.get(sym):
                w += perms.get(sym)
            elif sym == 'T':
                s += 1
            elif sym == 't':
                s += 1
                w += 1

    return f'{s}{o}{g}{w}'


fs_config = []
file_contexts = []
space_paths = []
error_times = 0


def scan_dir(root_inode, root_path: str = ""):
    """
    Port dari Extractor.scan_dir() di imgextractor.py,
    disesuaikan untuk:
    - path prefix = partition_name
    - skip entry fs_config untuk lost+found root (biar ga ada product/lost+found)
    """
    global error_times

    for entry_name, entry_inode_idx, entry_type in root_inode.open_dir():
        if entry_name in ('.', '..') or entry_name.endswith(' (2)'):
            continue

        if error_times >= 200:
            print("Some thing wrong, stop scan!")
            break

        entry_inode = root_inode.volume.get_inode(entry_inode_idx, entry_type)
        entry_inode_path = root_path + '/' + entry_name

        # Kalau path diakhiri slash tapi bukan dir => error
        if entry_inode_path.endswith('/') and not entry_inode.is_dir:
            error_times += 1
            continue

        # --- Permission & UID/GID ---
        mode = get_perm_from_modestr(entry_inode.mode_str)
        uid = entry_inode.inode.i_uid
        gid = entry_inode.inode.i_gid

        cap = ''
        link_target = ''
        # tmp_path = FileName + entry_inode_path (FileName = partition_name)
        # tmp_path harus mengandung prefix partition seperti imgextractor:
        # contoh -> "system_ext/apex/com.android...": (FileName + entry_path)
        tmp_path = partition_name + entry_inode_path   # contoh: product + "/app/..." -> "product/app/..."
        # pastikan tidak ada double-slash: kalau entry_inode_path sudah ada prefix yang aneh, normalize:
        tmp_path = tmp_path.lstrip('/')   # remove leading slash so later we add one when writing

        # --- XATTR (SELINUX & CAP) ---
        for fname, val in entry_inode.xattrs():
            if fname == "security.selinux":
                ctx = val.decode("utf8", errors="ignore").rstrip("\x00").rstrip()

                # Escape special chars (MIO-Kitchen behavior)
                esc = tmp_path
                for ch in "\\^$.|?*+(){}[]":
                    esc = esc.replace(ch, "\\" + ch)

                # prepend "/" → /lost+found , /app/Photos.apk, ...
                file_contexts.append(f"/{esc} {ctx}")

            elif fname == 'security.capability':
                r = struct.unpack('<5I', val)
                if r[1] > 65535:
                    cap_val = hex(int(f'{r[3]:04x}{r[1]:04x}', 16))
                else:
                    cap_val = hex(int(f'{r[3]:04x}{r[2]:04x}{r[1]:04x}', 16))
                cap = f" capabilities={cap_val}"

        # --- symlink target (kalau symlink) ---
        if entry_inode.is_symlink:
            try:
                link_target = entry_inode.open_read().read().decode("utf8")
            except Exception:
                link_target_block = int.from_bytes(entry_inode.open_read().read(), "little")
                link_target = root_inode.volume.read(
                    link_target_block * root_inode.volume.block_size,
                    entry_inode.inode.i_size
                ).decode("utf8", errors="ignore")

        # --- FS_CONFIG entry path handling (spasi) + SKIP product/lost+found ---
        # lost+found root: root_path == "" dan entry_name == "lost+found"
        # => JANGAN bikin "product/lost+found" di fs_config, tapi context tetap jalan.
        skip_fs_entry = (root_path == "" and entry_name == "lost+found")

        if not skip_fs_entry:
            if tmp_path.find(' ', 1, len(tmp_path)) > 0:
                space_paths.append(tmp_path)
                out_path = tmp_path.replace(' ', '_')
            else:
                out_path = tmp_path

            # Append ke fs_config persis format kitchen:
            # path uid gid mode[ cap] linktarget
            fs_config.append(f"{out_path} {uid} {gid} {mode}{cap} {link_target}")

        # --- Extract file/folder ke EXTRACT_DIR (tetep sama kayak sebelumnya) ---
        if entry_inode.is_dir:
            dir_target = os.path.join(EXTRACT_DIR, entry_inode_path.lstrip('/').replace(' ', '_').replace('"', ''))
            if dir_target.endswith('.') and os.name == 'nt':
                dir_target = dir_target[:-1]
            if not os.path.isdir(dir_target):
                os.makedirs(dir_target, exist_ok=True)

            scan_dir(entry_inode, entry_inode_path)

        elif entry_inode.is_file:
            file_target = os.path.join(EXTRACT_DIR, entry_inode_path.lstrip('/').replace(' ', '_').replace('"', ''))
            file_target_dir = os.path.dirname(file_target)
            if not os.path.exists(file_target_dir):
                os.makedirs(file_target_dir, exist_ok=True)
            try:
                with open(file_target, 'wb') as out:
                    out.write(entry_inode.open_read().read())
            except Exception as e:
                print(f"[E] Cannot write to {file_target}: {e}")

        elif entry_inode.is_symlink:
            # Di Windows nggak ada symlink native, tapi kita skip aja untuk sekarang
            target = os.path.join(EXTRACT_DIR, entry_inode_path.lstrip('/').replace(' ', '_'))
            # Kalau mau bener-bener copy behaviour symlink, perlu posix.symlink;
            # tapi di Windows ga wajib buat tool config.

def main(img_path: str):
    global Volume
    import os
    import shutil
    from check import detect_type

    # === ROOT FOLDER = FOLDER TEMPAT IMAGE BERADA ===
    root = os.path.dirname(img_path)

    partition_name = os.path.splitext(os.path.basename(img_path))[0]

    # === PATH OUTPUT EXT4 (IKUT EROFS) ===
    part_dir = os.path.join(root, partition_name)   # <-- ROOT/<partition_name>/
    config_dir = os.path.join(root, "config")       # <-- ROOT/config/

    # reset global state
    global fs_config, file_contexts, space_paths, error_times
    fs_config.clear()
    file_contexts.clear()
    space_paths.clear()
    error_times = 0

    # bersihkan folder lama (biar fresh)
    if os.path.isdir(part_dir):
        shutil.rmtree(part_dir)
    os.makedirs(part_dir, exist_ok=True)

    os.makedirs(config_dir, exist_ok=True)

    # === OVERRIDE EXTRACT_DIR GLOBAL ===
    # sekarang semua output dari scan_dir akan masuk ke folder ini
    globals()['EXTRACT_DIR'] = part_dir
    globals()['CONFIG_DIR']  = config_dir
    globals()['partition_name'] = partition_name

    # ====== BUKA IMAGE ======
    with open(img_path, "rb") as f:
        # pakai ext4 dulu buat baca superblock
        tmp_vol = ext4.Volume(f)
        fs_type, *_ = detect_type(tmp_vol.superblock)

        # reset file pointer
        f.seek(0)

        if fs_type == "EXT2":
            Volume = ext2.Volume
        elif fs_type == "EXT3":
            Volume = ext3.Volume
        else:
            Volume = ext4.Volume

        print(f"[ENGINE] Volume = {Volume.__module__}")

        vol = Volume(f)
        root_inode = vol.root
        scan_dir(root_inode)


    # ====== WRITE FS_CONFIG HEADER ======
    fs_config.insert(0, '/ 0 0 0755')
    fs_config.insert(1, f'{partition_name} 0 0 0755')
    fs_config.insert(2, f'{partition_name}/lost+found 0 0 0700')

    # ====== FILE_CONTEXTS HEADER — enforce exact format like imgextractor ======
    if file_contexts:
        file_contexts.sort()

        # ambil representative SELinux label dari entry pertama, fallback aman
        first_parts = file_contexts[0].split()
        sel_label = first_parts[1] if len(first_parts) > 1 else "u:object_r:system_file:s0"

        # headers dalam urutan yang LU MAU:
        headers = [
            f"/ {sel_label}",
            f"/{partition_name}(/.*)? {sel_label}",
            f"/{partition_name} {sel_label}",
            f"/{partition_name}/lost+\\found {sel_label}",
        ]

        # insert headers at top preserving desired order (insert reversed)
        for h in reversed(headers):
            if h not in file_contexts:
                file_contexts.insert(0, h)

        # keep legacy kitchen special-case for build.prop if it exists
        # (insert after headers, exactly like extractor)
        for c in list(file_contexts):
            if re.search(r'/system/system/build..prop\s', c):
                # insert lost+found and the "double partition" pattern used by kitchen
                if '/lost+\\found u:object_r:rootfs:s0' not in file_contexts:
                    file_contexts.insert(3, '/lost+\\found u:object_r:rootfs:s0')
                dbl = f'/{partition_name}/{partition_name}/(/.*)? {sel_label}'
                if dbl not in file_contexts:
                    file_contexts.insert(4, dbl)
                break

    # 4. Tulis file hasil ke CONFIG_DIR
    fs_config_path = os.path.join(CONFIG_DIR, f"{partition_name}_fs_config")
    file_contexts_path = os.path.join(CONFIG_DIR, f"{partition_name}_file_contexts")
    space_path = os.path.join(CONFIG_DIR, f"{partition_name}_space.txt")

    with open(fs_config_path, "w", newline="\n", encoding="utf-8") as fcfg:
        fcfg.write("\n".join(fs_config))

    if file_contexts:
        with open(file_contexts_path, "w", newline="\n", encoding="utf-8") as fctx:
            fctx.write("\n".join(file_contexts))

    if space_paths:
        with open(space_path, "w", newline="\n", encoding="utf-8") as fsp:
            fsp.write("\n".join(space_paths))

    # ====== BUILD <partition_name>_info ======
    fmt, journal, extents, *_ = detect_type(vol.superblock)
    filesystem_size = vol.superblock.s_blocks_count * vol.block_size
    block_size = vol.block_size  # <--- ambil block size ext4 asli

    info_path = os.path.join(CONFIG_DIR, f"{partition_name}_info")
    with open(info_path, "w", encoding="utf-8", newline="\n") as finfo:
        finfo.write(f"PartitionName: {partition_name}\n")
        finfo.write(f"Format: {fmt}\n")
        finfo.write(f"Size: {filesystem_size}\n")
        finfo.write(f"BlockSize: {block_size}\n")
        finfo.write(f"BlockCount: {vol.get_block_count}\n")
        finfo.write(f"FreeBlocks: {vol.get_free_blocks_count}\n")
        finfo.write(f"MountPoint: {vol.get_mount_point}\n")
        finfo.write(f"VolumeName: {vol.superblock.s_volume_name.decode()}\n")
        finfo.write(f"UUID: {vol.uuid}\n")
        
    # === RETURN KE GUI ===
    return True, part_dir

# ===================== MAIN =====================

if __name__ == "__main__":
    print(f"[*] Image  : {img_path}")
    print(f"[*] Mount  : /{partition_name}")
    print(f"[*] Output : {EXTRACT_DIR}")
    print(f"[*] Config : {CONFIG_DIR}")
    print("=================================")

    os.makedirs(EXTRACT_DIR, exist_ok=True)
    os.makedirs(CONFIG_DIR, exist_ok=True)

    with open(img_path, "rb") as f:
        vol = Volume(f)
        root = vol.root

        # 1. Extract isi EXT4 + kumpulin metadata (fs_config + context)
        scan_dir(root)

    # 2. FS_CONFIG HEADER SIMPLE:
    # /                     0 0 0755
    # <partition_name>      0 0 0755
    # <partition_name>/lost+found 0 0 0700
    fs_config.insert(0, '/ 0 0 0755')
    fs_config.insert(1, f'{partition_name} 0 0 0755')
    fs_config.insert(2, f'{partition_name}/lost+found 0 0 0700')

    # ====== FILE_CONTEXTS HEADER — enforce exact format like imgextractor ======
    if file_contexts:
        file_contexts.sort()

        # ambil representative SELinux label dari entry pertama, fallback aman
        first_parts = file_contexts[0].split()
        sel_label = first_parts[1] if len(first_parts) > 1 else "u:object_r:system_file:s0"

        # headers dalam urutan yang LU MAU:
        headers = [
            f"/ {sel_label}",
            f"/{partition_name}(/.*)? {sel_label}",
            f"/{partition_name} {sel_label}",
            f"/{partition_name}/lost+\\found {sel_label}",
        ]

        # insert headers at top preserving desired order (insert reversed)
        for h in reversed(headers):
            if h not in file_contexts:
                file_contexts.insert(0, h)

        # keep legacy kitchen special-case for build.prop if it exists
        # (insert after headers, exactly like extractor)
        for c in list(file_contexts):
            if re.search(r'/system/system/build..prop\s', c):
                # insert lost+found and the "double partition" pattern used by kitchen
                if '/lost+\\found u:object_r:rootfs:s0' not in file_contexts:
                    file_contexts.insert(3, '/lost+\\found u:object_r:rootfs:s0')
                dbl = f'/{partition_name}/{partition_name}/(/.*)? {sel_label}'
                if dbl not in file_contexts:
                    file_contexts.insert(4, dbl)
                break

    # 4. Tulis file hasil ke CONFIG_DIR
    fs_config_path = os.path.join(CONFIG_DIR, f"{partition_name}_fs_config")
    file_contexts_path = os.path.join(CONFIG_DIR, f"{partition_name}_file_contexts")
    space_path = os.path.join(CONFIG_DIR, f"{partition_name}_space.txt")

    with open(fs_config_path, "w", newline="\n", encoding="utf-8") as fcfg:
        fcfg.write("\n".join(fs_config))

    if file_contexts:
        with open(file_contexts_path, "w", newline="\n", encoding="utf-8") as fctx:
            fctx.write("\n".join(file_contexts))

    if space_paths:
        with open(space_path, "w", newline="\n", encoding="utf-8") as fsp:
            fsp.write("\n".join(space_paths))

    # ====== BUILD <partition_name>_info ======
    fmt, journal, extents, *_ = detect_type(vol.superblock)
    filesystem_size = vol.superblock.s_blocks_count * vol.block_size
    block_size = vol.block_size  # <--- ambil block size ext4 asli

    info_path = os.path.join(CONFIG_DIR, f"{partition_name}_info")
    with open(info_path, "w", encoding="utf-8", newline="\n") as finfo:
        finfo.write(f"PartitionName: {partition_name}\n")
        finfo.write(f"Format: {fmt}\n")
        finfo.write(f"Size: {filesystem_size}\n")
        finfo.write(f"BlockSize: {block_size}\n")
        finfo.write(f"BlockCount: {vol.get_block_count}\n")
        finfo.write(f"FreeBlocks: {vol.get_free_blocks_count}\n")
        finfo.write(f"MountPoint: {vol.get_mount_point}\n")
        finfo.write(f"VolumeName: {vol.superblock.s_volume_name.decode()}\n")
        finfo.write(f"UUID: {vol.uuid}\n")

    print("📄 info           ->", info_path)
    print("=================================")
    print("📄 fs_config      ->", fs_config_path)
    print("📄 file_contexts  ->", file_contexts_path)
    if space_paths:
        print("📄 space paths    ->", space_path)
    print("📂 extracted dir  ->", EXTRACT_DIR)
