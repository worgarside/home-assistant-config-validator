try-repo:
	git add . && cd ../home-assistant && git add . && pre-commit try-repo ../home-assistant-config-validator

vscode-shortcut-1:
	make try-repo
