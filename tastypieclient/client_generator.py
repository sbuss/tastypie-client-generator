#!/usr/bin/env python
import argparse

from .client_builder import ClientBuilder


def build_client(name, base_url):
    builder = ClientBuilder(base_url)
    builder.generate_client(name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="The name of the generated module.")
    parser.add_argument("base_url", help="The base URL of the server.")
    args = parser.parse_args()
    build_client(args.name, args.base_url)
