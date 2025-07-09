# __main__.py
from .dev_argparse import parse_argv
from .context import run, Config


def main() -> None:
  args = parse_argv()
  cfg = Config(reload_modules=args.reload)
  key = run(args.source, cfg=cfg)
  if args.patch:
    run(key, args.patch)


if __name__ == '__main__':
  main()
