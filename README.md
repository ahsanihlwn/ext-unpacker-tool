This project contains source code derived from:

Repository: https://github.com/cubinator/ext4
Author(s): cubinator
License: GNU General Public License v3.0

The original source code has been modified and split
into standalone Python utilities for external usage.

All original rights belong to their respective authors.

### ext4 CLI Utility

Standalone command-line utility for reading and unpacking EXT filesystem images
(EXT2 / EXT3 / EXT4).

This repository contains a modified and separated version of the original code from:
https://github.com/cubinator/ext4

Licensed under the GNU General Public License v3.0 (GPL-3.0).

## Usage

All operations are executed using command-line arguments.

### Basic Syntax

python ext_cli.py [operation] --x <path/to/image.img>

## Operations

### --read

Reads the EXT filesystem image without extracting files.

Example:

python ext_cli.py --read --x system.img

### --unpack

Extracts the contents of the EXT filesystem image.

Example:

python ext_cli.py --unpack --x system.img

## Arguments

### --x <path>

Path to the EXT filesystem image file.

Example:

--x ./image.img

## Notes

- Only one operation flag should be used per execution
- The image path must point to a valid EXT filesystem image

## License

GNU General Public License v3.0  
See the LICENSE file for details.

## Attribution

Derived from:
https://github.com/cubinator/ext4

Author: cubinator
Edited by : ahsanihlwn
License: GNU General Public License v3.0

The source code has been modified and reorganized into a standalone CLI utility.

