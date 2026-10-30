#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Анализатор кривизны подложки.
Точка входа. Работает на Windows и Linux (Linux Mint) с одним и тем же кодом.
"""

import sys
import os
import json

from PyQt5.QtWidgets import QApplication
from gui import WaferAnalyzerGUI


def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"window_width": 1450, "window_height": 850}


def main():
    app = QApplication(sys.argv)
    config = load_config()
    window = WaferAnalyzerGUI(config)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
