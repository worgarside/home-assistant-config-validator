try-repo:
	git add . && cd ../home-assistant && git add . && pre-commit try-repo ../home-assistant-config-validator

include .env
export

vscode-shortcut-1:
	make try-repo

vscode-shortcut-2:
	poetry run python home_assistant_config_validator/validate_entities.py
