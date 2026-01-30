import pgzrun
from pgzero.rect import Rect
import random
import math

# pgzero globals (injected at runtime by pgzrun)
# These will be available after pgzrun.go() is called
# We don't declare them here to avoid conflicts with pgzrun injection

WIDTH = 800
HEIGHT = 600

# --- Game States ---
MENU = "menu"
PLAYING = "playing"

game_state = MENU

# --- Audio Variables ---
jump_sound = None
hit_sound = None
audio_initialized = False

# --- Initialize Audio ---
def init_audio():
    global jump_sound, hit_sound, audio_initialized
    if audio_initialized:
        return
    
    # Acessa music e sounds do namespace global (injetados pelo pgzrun)
    music_obj = globals().get('music')
    sounds_obj = globals().get('sounds')
    
    if music_obj is None or sounds_obj is None:
        return
    
    try:
        music_obj.play("bgm")
        music_obj.set_volume(0.5)
        jump_sound = sounds_obj.jump
        hit_sound = sounds_obj.hit
        audio_initialized = True
    except (AttributeError, NameError):
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
            screen_obj.draw.text(self.text, center=self.rect.center, fontsize=30, color="white")

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

        self.idle_frames = ["hero_idle1", "hero_idle2"]
        self.run_frames = ["hero_run1", "hero_run2"]
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

    def update_animation(self, moving):
        self.frame_timer += 1
        if self.frame_timer > 8:
            self.frame_timer = 0
            self.current_frame = (self.current_frame + 1) % 2

            if moving:
                self.actor.image = self.run_frames[self.current_frame]
            else:
                self.actor.image = self.idle_frames[self.current_frame]

    def update(self):
        keys = globals().get('keyboard')
        if keys is None:
            return
        moving = False

        if keys.left:
            self.x -= 5
            moving = True
        if keys.right:
            self.x += 5
            moving = True

        if keys.space and self.on_ground:
            self.vy = -10
            self.on_ground = False
            if jump_sound:
                jump_sound.play()

        # gravity
        self.vy += 0.5
        self.y += self.vy

        if self.y > HEIGHT - 100:
            self.y = HEIGHT - 100
            self.vy = 0
            self.on_ground = True

        self.actor.pos = (self.x, self.y)
        self.update_animation(moving)

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

    def update(self):
        self.x += self.direction * 2

        # change direction randomly
        if random.random() < 0.01:
            self.direction *= -1

        self.actor.pos = (self.x, self.y)

        # animation
        self.frame_timer += 1
        if self.frame_timer > 12:
            self.frame_timer = 0
            self.current_frame = (self.current_frame + 1) % 2
            self.actor.image = self.move_frames[self.current_frame]

# --- Game Instances (initialized after pgzrun) ---
hero = None
enemies = []
game_initialized = False

def init_game():
    global hero, enemies, game_initialized
    # Verifica se Actor está disponível (injetado pelo pgzrun)
    if game_initialized:
        return
    
    # Acessa Actor do namespace global (injetado pelo pgzrun)
    actor = globals().get('Actor')
    if actor is None:
        return
    
    # Injeta Actor temporariamente no namespace para as classes usarem
    import __main__
    __main__.Actor = actor
    
    try:
        hero = Hero()
        enemies = [Enemy(400, HEIGHT - 100), Enemy(700, HEIGHT - 100)]
        game_initialized = True
    except (TypeError, NameError) as e:
        # Actor ainda não está disponível ou há outro erro
        return

# --- Buttons ---
def start_game():
    global game_state
    game_state = PLAYING

def quit_game():
    exit()

buttons = [
    Button("Start Game", 300, 200, 200, 50, start_game),
    Button("Quit", 300, 300, 200, 50, quit_game)
]

# --- Game Loop ---
def update():
    init_game()  # Initialize game objects after pgzrun sets up globals
    if game_state == PLAYING and hero:
        hero.update()
        for enemy in enemies:
            enemy.update()

        # collision
        for enemy in enemies:
            if hero.actor.colliderect(enemy.actor):
                if hit_sound:
                    hit_sound.play()
                start_game()  # restart

def draw():
    init_audio()  # Initialize audio after pgzrun sets up globals
    init_game()  # Initialize game objects after pgzrun sets up globals
    screen_obj = globals().get('screen')
    if screen_obj is None:
        return
    screen_obj.clear()
    if game_state == MENU:
        screen_obj.draw.text("My Platformer!", center=(WIDTH//2,100), fontsize=60, color="white")
        for btn in buttons:
            btn.draw()
    elif game_state == PLAYING:
        if hero:
            hero.actor.draw()
        for enemy in enemies:
            enemy.actor.draw()

def on_mouse_down(pos):
    if game_state == MENU:
        for btn in buttons:
            btn.click(pos)

pgzrun.go()
