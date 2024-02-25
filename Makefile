install:
	poetry install --all-extras --sync

update:
	poetry cache clear --all _default_cache && poetry update

try-repo:
	git add . && cd ../home-assistant && git add . && pre-commit try-repo ../home-assistant-config-validator

include .env
export

vscode-shortcut-1:
	make try-repo

vscode-shortcut-2:
	poetry run python home_assistant_config_validator/readme_generator.py

vscode-shortcut-3:
	poetry run python home_assistant_config_validator/validate_entities.py

vscode-shortcut-4:
	poetry run python home_assistant_config_validator/validate_lovelace.py
