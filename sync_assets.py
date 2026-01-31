"""
Script para sincronizar assets de game/ para as pastas que pgzero espera
Execute este script sempre que adicionar novas imagens/sons em game/
"""
import shutil
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # Pillow pode não estar instalado em alguns ambientes
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]

import wave

# Caminhos
BASE_DIR = Path(__file__).resolve().parent

GAME_SPRITES = BASE_DIR / "game" / "sprites"
GAME_SOUNDS = BASE_DIR / "game" / "sounds"
GAME_MUSIC = BASE_DIR / "game" / "music"

IMAGES_DIR = BASE_DIR / "images"
SOUNDS_DIR = BASE_DIR / "sounds"
MUSIC_DIR = BASE_DIR / "music"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
RIFF_SIGNATURE = b"RIFF"

def _is_valid_png(path: Path) -> bool:
    """Valida rapidamente se o arquivo parece ser um PNG válido."""
    try:
        if not path.exists() or not path.is_file():
            return False
        if path.stat().st_size == 0:
            return False
        with path.open("rb") as f:
            header = f.read(8)
        if header != PNG_SIGNATURE:
            return False
        # Verificação extra (se Pillow estiver disponível)
        if Image is not None:
            try:
                with Image.open(path) as img:
                    img.verify()
            except Exception:
                return False
        return True
    except Exception:
        return False

def _is_valid_wav(path: Path) -> bool:
    """Validação simples de WAV (RIFF/WAVE) e tamanho mínimo."""
    try:
        if not path.exists() or not path.is_file():
            return False
        if path.stat().st_size < 44:
            return False
        with path.open("rb") as f:
            hdr = f.read(12)
        return hdr.startswith(RIFF_SIGNATURE) and hdr[8:12] == b"WAVE"
    except Exception:
        return False

def _generate_silence_wav(path: Path, *, duration_s: float = 0.15, sample_rate: int = 22050) -> bool:
    """Gera um WAV PCM com silêncio (placeholder)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        nframes = int(duration_s * sample_rate)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(b"\x00\x00" * nframes)
        return True
    except Exception:
        return False

def _placeholder_colors(stem: str) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Escolhe cores baseadas no nome do sprite para diferenciar visualmente."""
    s = stem.lower()
    if "hero" in s:
        return (40, 140, 255, 255), (10, 30, 60, 255)  # fg, bg
    if "enemy" in s:
        return (255, 80, 80, 255), (60, 10, 10, 255)
    return (220, 220, 220, 255), (40, 40, 40, 255)

def _generate_placeholder_sprite_png(path: Path) -> bool:
    """Gera um PNG simples (placeholder) para evitar crash do Pygame/PGZero."""
    if Image is None or ImageDraw is None:
        return False

    fg, bg = _placeholder_colors(path.stem)
    size = (64, 64)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fundo arredondado
    pad = 6
    draw.rounded_rectangle(
        [pad, pad, size[0] - pad, size[1] - pad],
        radius=12,
        fill=bg,
        outline=fg,
        width=3,
    )

    # Um “personagem” minimalista
    # cabeça
    draw.ellipse([22, 14, 42, 34], fill=fg)
    # corpo
    draw.rectangle([26, 32, 38, 52], fill=fg)
    # perninha (varia pelo nome p/ dar sensação de animação)
    offset = 0
    name = path.stem.lower()
    if name.endswith("2"):
        offset = 2
    draw.rectangle([24 + offset, 50, 30 + offset, 58], fill=fg)
    draw.rectangle([34 - offset, 50, 40 - offset, 58], fill=fg)

    # Texto curto (identificação)
    label = path.stem.replace("_", " ")[:10]
    try:
        font = ImageFont.load_default() if ImageFont is not None else None
        draw.text((8, 6), label, fill=(255, 255, 255, 220), font=font)
    except Exception:
        pass

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG", optimize=True)
    return True

def ensure_sprites_valid():
    """
    Garante que todos os .png em game/sprites são PNGs válidos.
    Se algum estiver vazio/corrompido, recria como placeholder.
    """
    if not GAME_SPRITES.exists():
        return

    fixed = 0
    for p in sorted(GAME_SPRITES.glob("*.png")):
        if not _is_valid_png(p):
            ok = _generate_placeholder_sprite_png(p)
            if ok:
                fixed += 1
                print(f"Sprite inválido recriado: {p.name}")
            else:
                print(f"Sprite inválido detectado (não consegui recriar): {p.name}")
    if fixed:
        print(f"Sprites corrigidos: {fixed}")

def ensure_sounds_valid():
    """
    Garante que os .wav em game/sounds sejam válidos.
    Se estiverem vazios/corrompidos, recria como WAV de silêncio.
    """
    if not GAME_SOUNDS.exists():
        return

    fixed = 0
    for p in sorted(GAME_SOUNDS.glob("*.wav")):
        if not _is_valid_wav(p):
            if _generate_silence_wav(p):
                fixed += 1
                print(f"Som inválido recriado: {p.name}")
            else:
                print(f"Som inválido detectado (não consegui recriar): {p.name}")
    if fixed:
        print(f"Sons corrigidos: {fixed}")

def sync_folder(source: Path, dest: Path, *, skip_empty: bool = True, delete_empty_dest: bool = True) -> int:
    """Copia arquivos de source para dest. Retorna quantos foram copiados."""
    if not source.exists():
        print(f"Pasta {source} não existe, pulando...")
        return 0
    
    dest.mkdir(exist_ok=True)
    
    copied = 0
    for file in source.glob("*"):
        if file.is_file():
            try:
                size = file.stat().st_size
            except Exception:
                size = -1

            if skip_empty and size == 0:
                # Evita copiar arquivos vazios (causam crash no pygame/pgzero)
                dest_file = dest / file.name
                if delete_empty_dest and dest_file.exists():
                    try:
                        if dest_file.stat().st_size == 0:
                            dest_file.unlink()
                            print(f"Removido destino vazio: {dest_file.name}")
                    except Exception:
                        pass
                print(f"Aviso: {file.name} está vazio (0 bytes). Não foi copiado.")
                continue

            dest_file = dest / file.name
            shutil.copy2(file, dest_file)
            copied += 1
            print(f"Copiado: {file.name}")
    
    if copied == 0:
        print(f"Nenhum arquivo encontrado em {source}")
    else:
        print(f"Total: {copied} arquivo(s) copiado(s)")
    return copied

def sync_all():
    print("Sincronizando assets...")
    print("-" * 40)
    ensure_sprites_valid()
    sync_folder(GAME_SPRITES, IMAGES_DIR)
    print("-" * 40)
    ensure_sounds_valid()
    sync_folder(GAME_SOUNDS, SOUNDS_DIR)
    print("-" * 40)
    sync_folder(GAME_MUSIC, MUSIC_DIR)
    print("-" * 40)
    print("Sincronização concluída!")

if __name__ == "__main__":
    sync_all()
