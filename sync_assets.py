"""
Script para sincronizar assets de game/ para as pastas que pgzero espera
Execute este script sempre que adicionar novas imagens/sons em game/
"""
import shutil
import os
from pathlib import Path

# Caminhos
GAME_SPRITES = Path("game/sprites")
GAME_SOUNDS = Path("game/sounds")
GAME_MUSIC = Path("game/music")

IMAGES_DIR = Path("images")
SOUNDS_DIR = Path("sounds")
MUSIC_DIR = Path("music")

def sync_folder(source, dest):
    """Copia arquivos de source para dest"""
    if not source.exists():
        print(f"Pasta {source} não existe, pulando...")
        return
    
    dest.mkdir(exist_ok=True)
    
    copied = 0
    for file in source.glob("*"):
        if file.is_file():
            dest_file = dest / file.name
            shutil.copy2(file, dest_file)
            copied += 1
            print(f"Copiado: {file.name}")
    
    if copied == 0:
        print(f"Nenhum arquivo encontrado em {source}")
    else:
        print(f"Total: {copied} arquivo(s) copiado(s)")

print("Sincronizando assets...")
print("-" * 40)
sync_folder(GAME_SPRITES, IMAGES_DIR)
print("-" * 40)
sync_folder(GAME_SOUNDS, SOUNDS_DIR)
print("-" * 40)
sync_folder(GAME_MUSIC, MUSIC_DIR)
print("-" * 40)
print("Sincronização concluída!")
