from pathlib import Path
import os
import shutil
import wave

# IMPORTANTE:
# `import pgzrun` chama `prepare_mod(__main__)`, que injeta `pgzero.builtins`
# no namespace do seu script e pode sobrescrever a variável global `__file__`.
# Por isso, capturamos o caminho REAL do arquivo antes de importar pgzrun.
_THIS_FILE = Path(__file__).resolve()
_ROOT = _THIS_FILE.parent

# Centraliza a janela do jogo no centro da tela (SDL/pygame).
# Precisa ser definido ANTES de o pygame/pgzero criar a janela.
os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "centered")

import pgzrun
from pgzero.rect import Rect
import random
import math
import pygame

_assets_prepared = False

def _ensure_images_point_to_game_sprites():
    """
    Pedido: sprites ficam em `game/sprites/`.

    O PGZero sempre carrega imagens pela pasta `images/` (relativa ao root).
    Então garantimos que exista `game/images/` apontando para `game/sprites/`:
    - tenta criar um symlink (se permitido no Windows)
    - senão, faz cópia dos PNGs (fallback)
    """
    sprites_dir = _ROOT / "game" / "sprites"
    images_dir = _ROOT / "game" / "images"

    if not sprites_dir.exists():
        return

    # 1) tenta symlink (pode exigir permissão no Windows)
    try:
        if not images_dir.exists():
            os.symlink(str(sprites_dir), str(images_dir), target_is_directory=True)
            return
    except Exception:
        pass

    # 2) fallback: copia os PNGs para game/images
    try:
        images_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return

    for p in sprites_dir.glob("*.png"):
        if not p.is_file():
            continue
        try:
            if p.stat().st_size == 0:
                continue
        except Exception:
            continue

        try:
            shutil.copy2(p, images_dir / p.name)
        except Exception:
            pass

def _prepare_assets_once():
    """Tenta evitar crash por assets vazios/corrompidos (ex.: PNG/MP3 de 0 bytes)."""
    global _assets_prepared
    if _assets_prepared:
        return
    _assets_prepared = True

    # Garante o caminho de imagens em `game/sprites` (via game/images link/cópia).
    _ensure_images_point_to_game_sprites()

    try:
        import pgzero.loaders as _runtime_loaders
        # set_root aceita arquivo ou pasta.
        # Para usar assets em D:\...\game\*, setamos root para a pasta `game`.
        _runtime_loaders.set_root(str((_ROOT / "game").resolve()))
        # força revalidação do root
        try:
            _runtime_loaders.images.have_root = False
        except Exception:
            pass
        try:
            _runtime_loaders.sounds.have_root = False
        except Exception:
            pass
    except Exception:
        pass

    # Fallback: se por algum motivo o PGZero estiver usando outro root (ex.: a pasta
    # de onde o usuário executou), garante que exista um `images/` lá também.
    try:
        import pgzero.loaders as _runtime_loaders2
        runtime_root = Path(_runtime_loaders2.root).resolve()
        dst_images = runtime_root / "images"
        if not dst_images.exists():
            src_images = _ROOT / "game" / "images"
            if src_images.exists():
                dst_images.mkdir(parents=True, exist_ok=True)
                for p in src_images.glob("*.png"):
                    if p.is_file():
                        try:
                            shutil.copy2(p, dst_images / p.name)
                        except Exception:
                            pass
    except Exception:
        pass

    # Se as imagens estiverem vazias, tenta recriar placeholders e sincronizar.
    images_dir = _ROOT / "game" / "sprites"
    try:
        bad_images = [p for p in images_dir.glob("*.png") if p.is_file() and p.stat().st_size == 0]
    except Exception:
        bad_images = []

    if bad_images:
        try:
            # Import seguro (sync_assets não executa mais no import)
            from sync_assets import ensure_sprites_valid

            ensure_sprites_valid()
        except Exception:
            # Se não der (ambiente sem pillow, permissões etc.), deixa seguir.
            pass

# pgzero globals (injected at runtime by pgzrun)
# These will be available after pgzrun.go() is called
# We don't declare them here to avoid conflicts with pgzrun injection

WIDTH = 800
HEIGHT = 600
BG_IMAGE = "treasure_cave"

# --- Level / Platforms ---
platforms = []
BRICK_W = 64
BRICK_H = 64

class Platform:
    def __init__(self, x, y, w, h):
        # Rect usa (left, top), (width, height)
        self.rect = Rect((x, y), (w, h))

    def draw(self):
        screen_obj = globals().get('screen')
        if not screen_obj:
            return

        # Desenha tiles de brick ao longo do retângulo
        x0 = int(self.rect.left)
        y0 = int(self.rect.top)
        x1 = int(self.rect.right)

        # evita loop infinito se tamanho estiver zerado
        if BRICK_W <= 0 or BRICK_H <= 0:
            return

        x = x0
        while x < x1:
            screen_obj.blit("brick", (x, y0))
            x += BRICK_W

# --- Game States ---
MENU = "menu"
PLAYING = "playing"
GAME_OVER = "game_over"
WIN = "win"

game_state = MENU
game_over_frames = 0
GAME_OVER_DELAY_FRAMES = 90  # ~1.5s em ~60 FPS
GAME_OVER_MESSAGE = "Game Over! Reiniciando..."
win_frames = 0
WIN_DELAY_FRAMES = 90  # ~1.5s em ~60 FPS
WIN_MESSAGE = "Você venceu! Reiniciando..."

# --- Audio Variables ---
jump_sound = None
hit_sound = None
audio_initialized = False
music_enabled = True
sfx_enabled = True
_music_backend = None  # "pgzero" | "pygame" | None
_music_loaded = None   # "bgm" ou caminho do arquivo
music_generation = 1            # incrementa quando ligar música (toca 1x por geração)
_music_generation_started = 0   # última geração já iniciada
audio_status = "Áudio: (inicializando)"
audio_last_error = None
MUSIC_TRACK = "game_music"  # nome do arquivo (sem extensão) em music/

def _find_bgm_path():
    """Retorna (backend, ref) onde backend é 'pgzero' ou 'pygame', e ref é nome/arquivo."""
    # Pedido: usar sempre a pasta game/music
    music_dir = _ROOT / "game" / "music"

    # Preferir formatos comuns (mp3/ogg/oga) e tocar via pygame com caminho completo.
    for ext in ("ogg", "oga", "mp3", "wav"):
        p = music_dir / f"{MUSIC_TRACK}.{ext}"
        try:
            if p.is_file() and p.stat().st_size > 0:
                return "pygame", str(p)
        except Exception:
            pass

    return None, None

def _ensure_bgm_wav():
    """Cria um WAV simples (tom) caso não exista música válida."""
    music_dir = _ROOT / "game" / "music"
    p = music_dir / f"{MUSIC_TRACK}.wav"
    try:
        # Regera sempre (para evitar ficar com arquivo silencioso/corrompido)
        if p.exists():
            p.unlink()
    except Exception:
        pass

    try:
        music_dir.mkdir(parents=True, exist_ok=True)
        sample_rate = 22050
        duration_s = 20.0  # longo o suficiente para perceber, sem loop
        # Frequências mais graves (menos "estridentes")
        freqs = (110.0, 165.0)
        amp = 6000  # mais audível, ainda longe de clipping
        nframes = int(duration_s * sample_rate)

        frames = bytearray()
        for n in range(nframes):
            t = n / sample_rate
            # fade in/out mais longo para evitar estalos
            fade = 1.0
            fade_in = sample_rate * 0.15
            fade_out = sample_rate * 0.25
            if n < fade_in:
                fade = n / fade_in
            if n > nframes - fade_out:
                fade = min(fade, max(0.0, (nframes - n) / fade_out))

            # mistura suave de senoides
            s = 0.0
            for f in freqs:
                s += math.sin(2 * math.pi * f * t)
            s /= max(1, len(freqs))
            val = int(amp * fade * s)
            frames += int(val).to_bytes(2, "little", signed=True)

        with wave.open(str(p), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(frames)
    except Exception:
        # Se não der pra criar, simplesmente não terá música.
        return

# --- Initialize Audio ---
def init_audio():
    global jump_sound, hit_sound, audio_initialized, _music_backend, _music_loaded
    global music_generation, _music_generation_started
    global audio_status, audio_last_error

    _prepare_assets_once()
    
    # Acessa music e sounds do namespace global (injetados pelo pgzrun)
    music_obj = globals().get('music')
    sounds_obj = globals().get('sounds')
    
    if music_obj is None or sounds_obj is None:
        return
    
    try:
        audio_last_error = None
        # garante mixer inicializado
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
        except Exception as e:
            audio_last_error = f"mixer.init falhou: {e}"

        # SFX
        if sfx_enabled:
            # Preferir MP3 do game/sounds (pedido do usuário); fallback para loader do pgzero.
            jump_sound = None
            try:
                jump_mp3 = (_ROOT / "game" / "sounds" / "jump.mp3")
                if jump_mp3.is_file() and jump_mp3.stat().st_size > 0:
                    jump_sound = pygame.mixer.Sound(str(jump_mp3))
            except Exception as e:
                audio_last_error = f"jump.mp3 falhou: {e}"
                jump_sound = None

            if jump_sound is None:
                try:
                    jump_sound = sounds_obj.jump
                except Exception:
                    jump_sound = None

            # hit: preferir MP3 do game/sounds; fallback para loader do pgzero.
            hit_sound = None
            try:
                hit_mp3 = (_ROOT / "game" / "sounds" / "hit.mp3")
                if hit_mp3.is_file() and hit_mp3.stat().st_size > 0:
                    hit_sound = pygame.mixer.Sound(str(hit_mp3))
            except Exception as e:
                audio_last_error = f"hit.mp3 falhou: {e}"
                hit_sound = None

            if hit_sound is None:
                try:
                    hit_sound = sounds_obj.hit
                except Exception:
                    hit_sound = None
        else:
            jump_sound = None
            hit_sound = None

        # Música: aplica SEMPRE conforme o toggle do menu
        if not music_enabled:
            try:
                music_obj.stop()
            except Exception:
                pass
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            _music_backend = None
            _music_loaded = None
            # não toca de novo até o usuário ligar novamente
            audio_status = "Música: desligada"
        else:
            # Toca apenas 1 vez por "geração" (cada vez que o usuário liga a música).
            if _music_generation_started == music_generation:
                try:
                    busy = bool(pygame.mixer.music.get_busy())
                except Exception:
                    busy = False
                # Se por algum motivo não estiver tocando, não "trava" a geração:
                # deixa seguir para tentar iniciar novamente (corrige caso o play falhe
                # silenciosamente ou o mixer não esteja pronto ainda).
                if busy:
                    audio_status = f"Música: ligada (tocando={busy})"
                    audio_initialized = True
                    return

            backend, ref = _find_bgm_path()
            if backend is None:
                # Sem mp3/ogg válido → cria um WAV simples e toca via pygame
                _ensure_bgm_wav()
                backend, ref = _find_bgm_path()

            if backend == "pgzero":
                # sem loop
                try:
                    music_obj.play_once(MUSIC_TRACK)
                except Exception:
                    # fallback
                    music_obj.play(MUSIC_TRACK)
                music_obj.set_volume(0.6)
                _music_backend = "pgzero"
                _music_loaded = MUSIC_TRACK
                _music_generation_started = music_generation
                audio_status = "Música: ligada (pgzero)"
            elif backend == "pygame" and ref:
                try:
                    pygame.mixer.music.load(ref)
                    pygame.mixer.music.set_volume(1.0)
                    # sem loop
                    pygame.mixer.music.play(0)
                    _music_backend = "pygame"
                    _music_loaded = ref
                    try:
                        busy = bool(pygame.mixer.music.get_busy())
                    except Exception:
                        busy = False

                    if busy:
                        _music_generation_started = music_generation
                        audio_status = f"Música: ligada (pygame, tocando={busy})"
                    else:
                        # Não marca como "iniciada" para tentar novamente nos próximos frames.
                        audio_status = "Música: erro (pygame não iniciou reprodução)"
                except Exception as e:
                    audio_last_error = f"pygame music falhou: {e}"
                    audio_status = "Música: erro (pygame)"
            else:
                audio_status = "Música: ligada (sem arquivo válido)"

        audio_initialized = True
    except Exception as e:
        audio_last_error = str(e)
        audio_status = "Música: erro"
        print("[audio] erro:", e)
        return

# --- Button Class ---
class Button:
    def __init__(self, text, x, y, w, h, action):
        self.text = text
        self.rect = Rect((x, y), (w, h))
        self.action = action

    def draw(self):
        screen_obj = globals().get('screen')
        if screen_obj:
            screen_obj.draw.filled_rect(self.rect, "gray")
            label = self.text() if callable(self.text) else self.text
            screen_obj.draw.text(label, center=self.rect.center, fontsize=30, color="white")

    def click(self, pos):
        if self.rect.collidepoint(pos):
            self.action()

# --- Hero Class ---
class Hero:
    def __init__(self):
        self.x = 100
        self.y = HEIGHT - 150
        self.vy = 0
        self.on_ground = False
        self.move_speed = 5
        self.jump_velocity = -12

        # Animações
        # - parado (sem tecla): anima (inclui idle3)
        # - esquerda: anima com idle1/idle2 (pedido anterior)
        self.stand_frames = ["hero_idle3", "hero_idle1", "hero_idle2"]
        self.left_frames = ["hero_idle1", "hero_idle2"]
        self.run_frames = ["hero_run1", "hero_run2"]
        # Sprite usado enquanto estiver no ar (pulo/queda)
        self.jump_image = "hero_jump"
        self.current_frame = 0
        self.frame_timer = 0

        # Obtém Actor do namespace global (injetado pelo pgzrun)
        Actor_class = globals().get('Actor')
        if Actor_class is None:
            # Tenta acessar do módulo principal
            import __main__
            Actor_class = getattr(__main__, 'Actor', None)
        if Actor_class is None:
            raise RuntimeError("Actor não está disponível. Certifique-se de que pgzrun.go() foi chamado.")
        # Começa parado (primeiro frame do idle)
        self.actor = Actor_class(self.stand_frames[0], (self.x, self.y))

        # Hitbox fixa: evita que trocar de sprite (com tamanho diferente)
        # quebre colisões e o "on_ground".
        self.collider_w = int(getattr(self.actor, "width", 64))
        self.collider_h = int(getattr(self.actor, "height", 64))

    def _collider_rect(self):
        """Retorna um Rect de colisão fixo, centrado no Actor."""
        left = self.actor.x - self.collider_w / 2
        top = self.actor.y - self.collider_h / 2
        return Rect((left, top), (self.collider_w, self.collider_h))

    def _set_collider_left(self, left):
        self.actor.x = left + self.collider_w / 2

    def _set_collider_right(self, right):
        self.actor.x = right - self.collider_w / 2

    def _set_collider_top(self, top):
        self.actor.y = top + self.collider_h / 2

    def _set_collider_bottom(self, bottom):
        self.actor.y = bottom - self.collider_h / 2

    def update_animation(self, frames):
        self.frame_timer += 1
        if self.frame_timer > 8:
            self.frame_timer = 0
            self.current_frame = (self.current_frame + 1) % max(1, len(frames))
            self.actor.image = frames[self.current_frame]

    def update(self):
        global platforms
        keys = globals().get('keyboard')
        if keys is None:
            return
        moving = False
        moving_left = False
        moving_right = False

        # Movimento horizontal (com colisão lateral)
        dx = 0
        if keys.left:
            dx -= self.move_speed
            moving = True
            moving_left = True
        if keys.right:
            dx += self.move_speed
            moving = True
            moving_right = True

        # Pulo com seta para cima (Mario-like)
        if keys.up and self.on_ground:
            self.vy = self.jump_velocity
            self.on_ground = False
            if jump_sound:
                jump_sound.play()

        # aplica horizontal
        if dx != 0:
            self.actor.x += dx
            for plat in platforms:
                if self._collider_rect().colliderect(plat.rect):
                    if dx > 0:
                        self._set_collider_right(plat.rect.left)
                    else:
                        self._set_collider_left(plat.rect.right)

        # gravity + movimento vertical (com colisão por cima/baixo)
        self.vy += 0.5
        self.on_ground = False
        self.actor.y += self.vy

        for plat in platforms:
            if self._collider_rect().colliderect(plat.rect):
                if self.vy > 0:  # caindo: “pousa” em cima
                    self._set_collider_bottom(plat.rect.top)
                    self.vy = 0
                    self.on_ground = True
                elif self.vy < 0:  # subindo: bate embaixo
                    self._set_collider_top(plat.rect.bottom)
                    self.vy = 0

        # limites do mundo
        r = self._collider_rect()
        if r.left < 0:
            self._set_collider_left(0)
        if r.right > WIDTH:
            self._set_collider_right(WIDTH)
        if r.bottom > HEIGHT:
            self._set_collider_bottom(HEIGHT)
            self.vy = 0
            self.on_ground = True

        # Ground-check robusto (quando está "encostando" na plataforma).
        if not self.on_ground and self.vy >= 0:
            rr = self._collider_rect()
            probe = Rect((rr.left, rr.top + 1), (rr.width, rr.height))
            for plat in platforms:
                if probe.colliderect(plat.rect):
                    self._set_collider_bottom(plat.rect.top)
                    self.vy = 0
                    self.on_ground = True
                    break

        self.x, self.y = self.actor.pos
        # Se estiver no ar, usa sprite de pulo e não deixa idle/run sobrescrever.
        if not self.on_ground:
            self.actor.image = self.jump_image
        else:
            # Direção:
            # - esquerda: usa hero_idle1/hero_idle2
            # - direita: usa hero_run1/hero_run2
            if moving_left and not moving_right:
                self.update_animation(self.left_frames)
            elif moving_right and not moving_left:
                self.update_animation(self.run_frames)
            else:
                # Sem movimento: anima idle também
                self.update_animation(self.stand_frames)

# --- Enemy Class ---
class Enemy:
    def __init__(self, x, y):
        self.x = x
        self.y = y

        self.idle_frames = ["enemy_idle1", "enemy_idle2"]
        self.move_frames = ["enemy_move1", "enemy_move2"]
        self.current_frame = 0
        self.frame_timer = 0

        # Obtém Actor do namespace global (injetado pelo pgzrun)
        Actor_class = globals().get('Actor')
        if Actor_class is None:
            # Tenta acessar do módulo principal
            import __main__
            Actor_class = getattr(__main__, 'Actor', None)
        if Actor_class is None:
            raise RuntimeError("Actor não está disponível. Certifique-se de que pgzrun.go() foi chamado.")
        self.actor = Actor_class(self.idle_frames[0], (self.x, self.y))
        self.direction = random.choice([-1, 1])
        self.speed = 2
        self.pause_frames = 0

    def update_animation(self, frames):
        self.frame_timer += 1
        if self.frame_timer > 12:
            self.frame_timer = 0
            self.current_frame = (self.current_frame + 1) % max(1, len(frames))
            self.actor.image = frames[self.current_frame]

    def update(self):
        moving = True

        # Às vezes o inimigo "para" e fica em idle (com animação)
        if self.pause_frames > 0:
            self.pause_frames -= 1
            moving = False
        else:
            self.x += self.direction * self.speed

            # change direction randomly
            if random.random() < 0.01:
                self.direction *= -1

            # chance de parar por um tempo
            if random.random() < 0.005:
                self.pause_frames = random.randint(30, 90)

        self.actor.pos = (self.x, self.y)

        # animation (move e idle)
        frames = self.move_frames if moving else self.idle_frames
        self.update_animation(frames)

# --- Game Instances (initialized after pgzrun) ---
hero = None
enemies = []
trophy = None
game_initialized = False

def init_game():
    global hero, enemies, trophy, game_initialized, platforms, BRICK_W, BRICK_H
    # Verifica se Actor está disponível (injetado pelo pgzrun)
    if game_initialized:
        return

    _prepare_assets_once()
    
    # Acessa Actor do namespace global (injetado pelo pgzrun)
    actor = globals().get('Actor')
    if actor is None:
        return
    
    # Injeta Actor temporariamente no namespace para as classes usarem
    import __main__
    __main__.Actor = actor
    
    try:
        #  tamanho do brick  
        try:
            brick_probe = actor("brick", (0, 0))
            BRICK_W = max(1, int(getattr(brick_probe, "width", 64)))
            BRICK_H = max(1, int(getattr(brick_probe, "height", 64)))
        except Exception:
            BRICK_W, BRICK_H = 64, 64

        # Plataformas
        platforms = [
            # chão
            Platform(0, HEIGHT - BRICK_H, WIDTH, BRICK_H),
        ]

        # escadinha: cada degrau sobe 1 tile e anda 1 tile para a direita
        base_x = 220
        base_y = HEIGHT - BRICK_H * 2  # um tile acima do chão
        step_w = BRICK_W * 3           # largura de cada plataforma/degrau
        step_h = BRICK_H
        for i in range(3):
            platforms.append(
                Platform(
                    base_x + i * BRICK_W,
                    base_y - i * BRICK_H,
                    step_w,
                    step_h,
                )
            )

        hero = Hero()
        enemies = [Enemy(400, HEIGHT - 100), Enemy(700, HEIGHT - 100)]

        # Troféu: meio da tela, canto direito
        trophy = None
        try:
            trophy_path = _ROOT / "game" / "sprites" / "trophy.png"
            if trophy_path.exists():
                trophy = actor("trophy", (0, 0))
                tw = int(getattr(trophy, "width", 64))
                margin = 24
                trophy.pos = (WIDTH - (tw / 2) - margin, HEIGHT / 2)
        except Exception:
            trophy = None
        game_initialized = True
    except (TypeError, NameError) as e:
        # Actor ainda não está disponível ou há outro erro
        return

# --- Buttons ---
def start_game():
    global game_state
    game_state = PLAYING

def trigger_game_over():
    global game_state, game_over_frames
    if game_state != GAME_OVER:
        game_state = GAME_OVER
        game_over_frames = 0
        if hit_sound:
            hit_sound.play()

def trigger_win():
    global game_state, win_frames
    if game_state != WIN:
        game_state = WIN
        win_frames = 0
        if hit_sound:
            hit_sound.play()

def toggle_music():
    global music_enabled, audio_initialized, music_generation
    music_enabled = not music_enabled
    audio_initialized = False
    music_obj = globals().get('music')
    if not music_enabled and music_obj is not None:
        try:
            music_obj.stop()
        except Exception:
            pass
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
    else:
        # ao ligar, incrementa a geração para tocar uma vez
        music_generation += 1
    # aplica imediatamente
    init_audio()

def toggle_sfx():
    global sfx_enabled, audio_initialized, jump_sound, hit_sound
    sfx_enabled = not sfx_enabled
    # aplica na hora
    if not sfx_enabled:
        jump_sound = None
        hit_sound = None
    audio_initialized = False
    # aplica imediatamente
    init_audio()

def quit_game():
    exit()

buttons = [
    Button("Start Game", 300, 190, 200, 50, start_game),
    Button(lambda: f"Música: {'Ligada' if music_enabled else 'Desligada'}", 300, 260, 200, 50, toggle_music),
    Button(lambda: f"Sons: {'Ligados' if sfx_enabled else 'Desligados'}", 300, 330, 200, 50, toggle_sfx),
    Button("Quit", 300, 400, 200, 50, quit_game),
]

# --- Game Loop ---
def update():
    global game_over_frames, win_frames, game_initialized
    init_game()  # Initialize game objects after pgzrun sets up globals
    if game_state == PLAYING and hero:
        hero.update()
        for enemy in enemies:
            enemy.update()

        # collision
        for enemy in enemies:
            # Usa a hitbox fixa do herói para não depender do tamanho do sprite.
            if enemy.actor.colliderect(hero._collider_rect()):  # type: ignore[attr-defined]
                trigger_game_over()
                break

        # Vitória: tocar no troféu
        if trophy is not None and game_state == PLAYING:
            try:
                if trophy.colliderect(hero._collider_rect()):  # type: ignore[attr-defined]
                    trigger_win()
            except Exception:
                pass
    elif game_state == GAME_OVER:
        # Pausa o jogo e reinicia após um curto delay.
        game_over_frames += 1
        if game_over_frames >= GAME_OVER_DELAY_FRAMES:
            game_initialized = False  # força recriar hero/enemies/platforms
            start_game()
    elif game_state == WIN:
        # Pausa o jogo e reinicia após um curto delay.
        win_frames += 1
        if win_frames >= WIN_DELAY_FRAMES:
            game_initialized = False  # força recriar hero/enemies/platforms/trophy
            start_game()

def draw():
    init_audio()  # Initialize audio after pgzrun sets up globals
    init_game()  # Initialize game objects after pgzrun sets up globals
    screen_obj = globals().get('screen')
    if screen_obj is None:
        return
    screen_obj.clear()
    # Background
    try:
        screen_obj.blit(BG_IMAGE, (0, 0))
    except Exception:
        pass
    if game_state == MENU:
        screen_obj.draw.text("My Platformer!", center=(WIDTH//2,100), fontsize=60, color="white")
        # Debug de áudio (para entender por que não sai som)
        try:
            mixer_ok = pygame.mixer.get_init() is not None
            busy = bool(pygame.mixer.music.get_busy())
        except Exception:
            mixer_ok = False
            busy = False
        screen_obj.draw.text(
            f"{audio_status} | mixer={mixer_ok} | busy={busy}",
            center=(WIDTH//2, 135),
            fontsize=24,
            color="yellow",
        )
        if audio_last_error:
            screen_obj.draw.text(
                f"Erro áudio: {audio_last_error}",
                center=(WIDTH//2, 160),
                fontsize=20,
                color="red",
            )
        for btn in buttons:
            btn.draw()
    elif game_state in (PLAYING, GAME_OVER, WIN):
        for plat in platforms:
            plat.draw()
        if hero:
            hero.actor.draw()
        for enemy in enemies:
            enemy.actor.draw()
        if trophy is not None:
            trophy.draw()

        if game_state == GAME_OVER:
            # Overlay de Game Over
            screen_obj.draw.text(
                GAME_OVER_MESSAGE,
                center=(WIDTH // 2, HEIGHT // 2),
                fontsize=60,
                color="red",
            )
        elif game_state == WIN:
            screen_obj.draw.text(
                WIN_MESSAGE,
                center=(WIDTH // 2, HEIGHT // 2),
                fontsize=60,
                color="green",
            )

def on_mouse_down(pos):
    if game_state == MENU:
        for btn in buttons:
            btn.click(pos)

pgzrun.go()
