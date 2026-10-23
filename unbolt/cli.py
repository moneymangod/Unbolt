"""Command-line front end: unbolt-cli FILE... --to FORMAT [-o DIR]"""
import argparse
import os
import sys

from unbolt.convert import FORMATS, convert


def main(argv=None):
    ap = argparse.ArgumentParser(prog="unbolt-cli", description="Convert locked file formats into open ones.")
    ap.add_argument("files", nargs="*", help="files to convert")
    ap.add_argument("-t", "--to", help="output format, e.g. png, pdf, pptx, mp3, mp4, wav")
    ap.add_argument("-o", "--out", help="output folder (default: next to each input file)")
    ap.add_argument("-l", "--list", action="store_true", help="list supported formats and their outputs")
    args = ap.parse_args(argv)

    if args.list:
        for ext, (outputs, _, _) in FORMATS.items():
            print(f"{ext:8} -> {', '.join(outputs)}")
        return 0
    if not args.files or not args.to:
        ap.error("give at least one file and --to FORMAT (or use --list)")

    failed = 0
    for path in args.files:
        try:
            outs, warns = convert(path, args.to.lower(), args.out or os.path.dirname(os.path.abspath(path)))
        except Exception as e:
            print(f"{path}: failed: {e}", file=sys.stderr)
            failed += 1
            continue
        for o in outs:
            print(o)
        for w in dict.fromkeys(warns):
            print(f"  note: {w}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
