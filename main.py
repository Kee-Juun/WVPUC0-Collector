# Decompiled with PyLingual (https://pylingual.io)
# Internal filename: 'main.py'
# Bytecode version: 3.13.0rc3 (3571)
# Source timestamp: 1970-01-01 00:00:00 UTC (0)

"""\nMain entry point for WVPUC0 Document Collector\n"""
import sys
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
# Import PyPDF2 at top level to ensure PyInstaller includes it
import PyPDF2
from ui.gui import WVPCU0GUI
def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    icon_path = None
    try:
        base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        # Use the WVPUC0 app icon everywhere (taskbar, title bar, etc.)
        icon_path = (base / 'assets' / 'wvpuc0_icon.ico').resolve()
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))
    except Exception:
        pass
    app.setStyle('Fusion')
    window = WVPCU0GUI()
    try:
        if icon_path and icon_path.exists():
            window.setWindowIcon(QIcon(str(icon_path)))
    except Exception:
        pass
    window.show()
    sys.exit(app.exec_())
if __name__ == '__main__':
    main()
