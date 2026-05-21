# -*- mode: python ; coding: utf-8 -*-
# EyeGuard PyInstaller spec dosyası
# Kullanım: pyinstaller eyeguard.spec

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# Mediapipe model dosyaları
mediapipe_datas = collect_data_files('mediapipe')

a = Analysis(
    ['eyeguard.py'],
    pathex=['.'],
    binaries=collect_dynamic_libs('mediapipe'),
    datas=[
        # Mediapipe model files
        *mediapipe_datas,
        # Sound files — copied next to EXE
        ('notifications', 'notifications'),
    ],
    hiddenimports=[
        'mediapipe',
        'mediapipe.python',
        'mediapipe.python.solutions',
        'mediapipe.python.solutions.face_mesh',
        'mediapipe.python.solution_base',
        'cv2',
        'pygame',
        'pystray',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'tkinter',
        'tkinter.font',
        'winreg',
        'winsound',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'pandas',
        'numpy.testing',
        'IPython',
        'jupyter',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='EyeGuard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # Konsol penceresi çıkmasın
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',    # İkon eklemek istersen: ico dosyası ekle
)
