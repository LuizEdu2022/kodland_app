# Jogo Platformer - Pygame Zero

## Estrutura de Pastas

O jogo usa duas estruturas de pastas:

1. **`game/`** - Onde você coloca seus assets originais:
   - `game/sprites/` - Imagens do jogo
   - `game/sounds/` - Sons do jogo  
   - `game/music/` - Música de fundo

2. **Pastas do pgzero** (criadas automaticamente):
   - `images/` - Imagens (sincronizadas de `game/sprites/`)
   - `sounds/` - Sons (sincronizados de `game/sounds/`)
   - `music/` - Música (sincronizada de `game/music/`)

## Como Usar

1. **Adicione suas imagens** em `game/sprites/`:
   - `hero_idle1.png`, `hero_idle2.png`
   - `hero_run1.png`, `hero_run2.png`
   - `enemy_idle1.png`, `enemy_idle2.png`
   - `enemy_move1.png`, `enemy_move2.png`

2. **Adicione seus sons** em `game/sounds/`:
   - `jump.wav`
   - `hit.wav`

3. **Adicione a música** em `game/music/`:
   - `bgm.mp3`

4. **Execute o script de sincronização**:
   ```bash
   py sync_assets.py
   ```
   Isso copiará todos os arquivos para as pastas que o pgzero espera.

5. **Execute o jogo**:
   ```bash
   py main.py
   ```

## Nota

Sempre que adicionar novos arquivos em `game/`, execute `sync_assets.py` novamente para sincronizá-los.
