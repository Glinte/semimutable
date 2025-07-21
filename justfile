#!/usr/bin/env just --justfile
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]
export PATH := join(justfile_directory(), ".env", "bin") + ":" + env_var('PATH')

python_dir := if os_family() == "windows" { "./.venv/Scripts" } else { "./.venv/bin" }
python := python_dir + if os_family() == "windows" { "/python.exe" } else { "/python3" }

default:
  just --list

upgrade:
  uv lock --upgrade

lint:
    {{python}} -m ruff check --fix --exit-zero
    {{python}} -m ruff format --target-version py312