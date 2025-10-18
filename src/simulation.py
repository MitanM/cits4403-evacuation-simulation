import pygame
import sys
from collections import deque, defaultdict
import random
import numpy as np
import json
import os

# --- Config ---
CELL_SIZE = 20
FPS = 10

# Colors (R, G, B)
WHITE = (255, 255, 255)
GRAY = (200, 200, 200)
BLACK = (0, 0, 0)
BLUE = (0, 0, 255)
GREEN = (0, 255, 0)
ORANGE = (255, 165, 0)
RED = (255, 0, 0)

# Cell types
EMPTY, WALL, EXIT, FIRE, SMOKE = 0, 1, 2, 3, 4

# Placement modes
MODE_WALL, MODE_AGENT, MODE_EXIT, MODE_FIRE = 1, 2, 3, 4

# Agent health states
HEALTHY, INJURED, FATALLY_INJURED, INCAPACITATED = 0, 1, 2, 3
# Fire config
FIRE_SPREAD_DELAY = 70    # fire spreads every X ticks
SMOKE_SPREAD_DELAY = 18    # smoke spreads every X ticks
EXIT_CAPACITY_PER_TICK = 1  # max agents that can go through each exit cell per tick

# Fire config
FIRE_SPREAD_DELAY = 70
SMOKE_SPREAD_DELAY = 25
EXIT_CAPACITY_PER_TICK = 1

# Temperature config
AMBIENT_TEMP = 20.0
FIRE_TEMP = 600.0
THERMAL_DIFFUSIVITY = 0.05
WALL_INSULATION = 0.3
SAFE_TEMP_THRESHOLD = 50.0

# Assumptions for exposure thresholds:
# Fire and smoke are fully developed instantly for simplicity
# Model does not include modelling the build up of fire or smoke 
# Injury occurs at ~33% the time required to incapacitate 
# Fatal injury occurs at ~67% of the time required to incapacitate

# Heat exposure thresholds based on ISO 13571
# Each tuple: (Temperature_C, non_fatal_injury_ticks, fatal_injury_ticks, incapacitation_ticks)
# Conversion: 12 ticks = 1 simulation minute (10 ticks/sec real-time, 5 sec/tick sim-time)
# 
# Based on ISO Equation (10) for convective heat: t_Iconv = (5 × 10^7) × T^(-3.4) minutes
# This calculates time until occupant cannot take effective action to escape (incapacitation)
# 
# Injury progression model:
# - Non-fatal injury (~33% of incapacitation time): Burns developing, painful but mobile
# - Fatal injury (~67% of incapacitation time): Severe burns that will cause death later, but adrenaline allows continued movement
# - Incapacitation (100% of ISO time): Pain/thermal damage so extreme the agent collapses and cannot move
# 
# Thresholds assume dry air (<10% water vapor) for simplicity; steam causes faster injury at lower temperatures and would drastically reduce injury and incapacitation times 
#
HEAT_THRESHOLDS = [
    (50, 240, 480, 720),      # 60 min incap
    (60, 120, 240, 360),      # 30 min incap
    (70, 68, 136, 204),       # 17 min incap
    (80, 40, 80, 120),        # 10 min incap
    (90, 26, 52, 78),         # 6.5 min incap
    (100, 16, 32, 48),        # 4 min incap
    (110, 11, 22, 32),        # 2.7 min incap
    (120, 8, 16, 24),         # 2 min incap
    (130, 5, 10, 16),         # 1.3 min incap
    (140, 4, 8, 12),          # 1 min incap
    (150, 3, 7, 10),          # 50 sec incap
    (160, 3, 5, 8),           # 40 sec incap
    (170, 2, 4, 7),           # 32 sec incap
    (180, 2, 3, 5),           # 24 sec incap
    (200, 1, 2, 3),           # 15 sec incap
    (250, 1, 1, 1),           # 6 sec incap
]

# Smoke thresholds: (non_fatal_ticks, fatal_ticks, incapacitation_ticks)
# Smoke/toxic gas thresholds for fully developed building fire
# Based on ISO 13571 FED (Fractional Effective Dose) model for asphyxiant gases
# 
# Assumes post-flashover fire conditions with high CO (8,000 ppm), CO₂ (8%), and HCN (150 ppm)
# CO₂ causes hyperventilation, dramatically increasing toxin uptake
# 
# ISO calculation: FED accumulates at 4.51 per minute in these conditions
# - Theoretical incapacitation: ~13 seconds (2.6 ticks)
# - Adjusted for variable exposure, agent movement, and uncertainty
# - Values represent continuous exposure to dense smoke in fully developed fire
#
# (non_fatal_injury_ticks, fatal_injury_ticks, incapacitation_ticks)
SMOKE_THRESHOLD = (2, 3, 4)

# Direct fire exposure (flames/fire tiles at 600°C)
# Agent is standing directly on a fire tile (600°C convective heat + radiant heat from flames)
# 
# Based on ISO 13571:
# Equation (10) for unclothed/lightly clothed: t_Iconv = (5 × 10^7) × T^(-3.4) minutes
# At 600°C: t = (5 × 10^7) × (600)^(-3.4) = 0.000015 minutes = 0.0009 seconds
# 
# Additionally:
# - ISO notes 120°C causes "considerable pain and burns within minutes"
# - 600°C is 5× higher than this threshold
# - Direct flame contact also adds extreme radiant heat (>10 kW/m²)
# - Respiratory tract experiences immediate thermal burns from superheated air
# 
# At 600°C exposure:
# - All three injury stages (injury/fatal/incapacitation) occur essentially instantly
# - Severe burns develop in <1 second
# - Pain causes immediate collapse, shock and inability to move
# 
# (non_fatal_injury_ticks, fatal_injury_ticks, incapacitation_ticks)
DIRECT_FLAME_THRESHOLDS = (1, 1, 1)

def get_heat_thresholds(temp):
    for threshold_temp, nf_ticks, f_ticks, inc_ticks in HEAT_THRESHOLDS:
        if temp >= threshold_temp:
            return (nf_ticks, f_ticks, inc_ticks)
    return (float('inf'), float('inf'), float('inf'))

def temp_to_color(temp):
    """Convert temperature to color gradient: white -> yellow -> orange -> red"""
    if temp <= AMBIENT_TEMP:
        return (255, 255, 255)
    elif temp >= FIRE_TEMP:
        return (255, 0, 0)

    norm = (temp - AMBIENT_TEMP) / (FIRE_TEMP - AMBIENT_TEMP)

    if norm < 0.33:
        t = norm / 0.33
        r = 255
        g = 255
        b = int(255 * (1 - t))
    elif norm < 0.66:
        t = (norm - 0.33) / 0.33
        r = 255
        g = int(255 * (1 - 0.5 * t))
        b = 0
    else:
        t = (norm - 0.66) / 0.34
        r = 255
        g = int(128 * (1 - t))
        b = 0

    return (r, g, b)

def save_layout(filename, grid, agents, exits, fires):
    """Save current grid configuration to a JSON file."""
    layout = {
        "grid_width": len(grid[0]),
        "grid_height": len(grid),
        "walls": [(x, y) for y, row in enumerate(grid) for x, c in enumerate(row) if c == WALL],
        "exits": exits,
        "fires": fires,
        "agents": agents
    }

    base_dir = os.path.dirname(os.path.dirname(__file__))
    layouts_dir = os.path.join(base_dir, "data", "layouts")
    os.makedirs(layouts_dir, exist_ok=True)
    path = os.path.join(layouts_dir, filename)

    with open(path, "w") as f:
        json.dump(layout, f, indent=2)
    print(f"Layout saved to {path}")


def load_layout(filename):
    """Load a layout JSON file and return grid + lists."""
    base_dir = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base_dir, "data", "layouts", filename)

    with open(path) as f:
        layout = json.load(f)

    grid_width = layout["grid_width"]
    grid_height = layout["grid_height"]
    grid = [[EMPTY for _ in range(grid_width)] for _ in range(grid_height)]

    for (x, y) in layout["walls"]:
        grid[y][x] = WALL
    for (x, y) in layout["fires"]:
        grid[y][x] = FIRE
    for (x, y) in layout["exits"]:
        grid[y][x] = EXIT

    agents = sorted([tuple(a) for a in layout["agents"]])
    exits = [tuple(e) for e in layout["exits"]]
    fires = [tuple(f) for f in layout["fires"]]

    print(f"Loaded layout: {filename}")
    return grid, agents, exits, fires

def make_screen(grid_w, grid_h, cell_size):
    return pygame.display.set_mode((grid_w * cell_size, grid_h * cell_size))

def in_bounds(x, y, grid_w, grid_h):
    return 0 <= x < grid_w and 0 <= y < grid_h

def compute_distance_map(exits, grid, grid_width, grid_height):
    """Return a 2D array of shortest distances from each cell to the nearest exit."""
    INF = float("inf")
    dist_map = [[INF for _ in range(grid_width)] for _ in range(grid_height)]
    q = deque()

    for (ex, ey) in exits:
        dist_map[ey][ex] = 0
        q.append((ex, ey))

    while q:
        x, y = q.popleft()
        for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < grid_width and 0 <= ny < grid_height:
                if grid[ny][nx] != WALL and dist_map[ny][nx] == INF:
                    dist_map[ny][nx] = dist_map[y][x] + 1
                    q.append((nx, ny))
    return dist_map

def diffuse_temperature(temp_grid, grid, grid_width, grid_height):
    """Apply heat diffusion using finite difference method."""
    new_temp = np.copy(temp_grid)

    for y in range(grid_height):
        for x in range(grid_width):
            if grid[y][x] == FIRE:
                new_temp[y, x] = FIRE_TEMP
                continue

            neighbors_sum = 0
            neighbor_count = 0

            for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < grid_width and 0 <= ny < grid_height:
                    if grid[ny][nx] == WALL:
                        diffusion_factor = THERMAL_DIFFUSIVITY * WALL_INSULATION
                    else:
                        diffusion_factor = THERMAL_DIFFUSIVITY

                    neighbors_sum += temp_grid[ny, nx] * diffusion_factor
                    neighbor_count += diffusion_factor

            if neighbor_count > 0:
                avg_neighbor_temp = neighbors_sum / neighbor_count
                new_temp[y, x] = temp_grid[y, x] + (avg_neighbor_temp - temp_grid[y, x])

                cooling_rate = 0.02
                new_temp[y, x] += (AMBIENT_TEMP - new_temp[y, x]) * cooling_rate

    return new_temp

def spread_fire_and_smoke(grid, grid_width, grid_height, tick):
    """Spread fire and smoke at different speeds."""
    if tick % FIRE_SPREAD_DELAY == 0:
        new_fire = []
        for y in range(grid_height):
            for x in range(grid_width):
                if grid[y][x] == FIRE:
                    for dx, dy in [(1,0),(-1,0),(0,1),(0,-1)]:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < grid_width and 0 <= ny < grid_height:
                            if grid[ny][nx] in (EMPTY, SMOKE):
                                new_fire.append((nx, ny))

        for fx, fy in new_fire:
            grid[fy][fx] = FIRE

    if tick % SMOKE_SPREAD_DELAY == 0:
        new_smoke = []
        for y in range(grid_height):
            for x in range(grid_width):
                if grid[y][x] in (FIRE, SMOKE):
                    for dx, dy in [(1,0),(0,1),(-1,0),(0,-1)]:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < grid_width and 0 <= ny < grid_height:
                            if grid[ny][nx] == EMPTY:
                                new_smoke.append((nx, ny))
        for sx, sy in new_smoke:
            grid[sy][sx] = SMOKE


def main():
    pygame.init()

    random.seed(42)
    # Ask the user for grid size (weight and height) 
    try: 
        grid_width = int(input("Enter grid width (number of cells): "))
        grid_height = int(input("Enter grid height (number of cells): "))
    except ValueError:
        print("Invalid input, using default 30x20)")
        grid_width = 30
        grid_height = 20

    cell_size = CELL_SIZE
    screen = make_screen(grid_width, grid_height, cell_size)
    pygame.display.set_caption("Evacuation Simulation with Temperature")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 22)

    agents = []
    exits = []
    dist_map = None
    running_sim = False
    mode = MODE_AGENT
    tick = 0
    exited_count = 0
    exited_injured_count = 0
    exited_fatally_injured_count = 0
    incapacitated_count = 0
    exposure = {}
    agent_data = {}
    agent_health = {}
    heat_exposure_ticks = {}
    selected_agent = None
    show_menu = False
    fires = []
    show_global_menu = False
    global_panic_value = 5  # default value we use

    

    temp_grid = np.full((grid_height, grid_width), AMBIENT_TEMP, dtype=float)

    agent_data = {}
    selected_agent = None
    next_agent_id = 1
    show_menu = False

    grid = [[EMPTY for _ in range(grid_width)] for _ in range(grid_height)]

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_1:
                    mode = MODE_WALL
                elif event.key == pygame.K_2:
                    mode = MODE_AGENT
                elif event.key == pygame.K_3:
                    mode = MODE_EXIT
                elif event.key == pygame.K_4:
                    mode = MODE_FIRE
                elif event.key == pygame.K_SPACE:
                    if not running_sim:
                        random.seed(42)
                        tick = 0
                        exited_count = 0
                        exited_injured_count = 0
                        exited_fatally_injured_count = 0
                        incapacitated_count = 0
                        exposure = {pos: {"smoke": 0, "fire": 0} for pos in agents}
                        agent_health = {pos: HEALTHY for pos in agents}
                        heat_exposure_ticks = {pos: 0 for pos in agents}
                        dead_count = 0
                        exposure = {pos: {"smoke": 0, "fire": 0} for pos in agents}
                        if exits:
                            dist_map = compute_distance_map(exits, grid, grid_width, grid_height)
                    running_sim = not running_sim
                elif event.key == pygame.K_r:
                    grid = [[EMPTY for _ in range(grid_width)] for _ in range(grid_height)]
                    temp_grid = np.full((grid_height, grid_width), AMBIENT_TEMP, dtype=float)
                    agents = []
                    exits = []
                    dist_map = None
                    running_sim = False
                    mode = MODE_AGENT
                    tick = 0
                    exited_count = 0
                    exited_injured_count = 0
                    exited_fatally_injured_count = 0
                    incapacitated_count = 0
                    exposure = {}
                    agent_data = {}
                    agent_health = {}
                    heat_exposure_ticks = {}
                
                elif event.key == pygame.K_m:
                    show_global_menu = not show_global_menu
                
                elif event.key == pygame.K_s:
                    save_layout("custom_layout.json", grid, agents, exits, 
                                [(x, y) for y, row in enumerate(grid) for x, c in enumerate(row) if c == FIRE])
                elif event.key == pygame.K_l:
                    try:
                        grid, agents, exits, fires = load_layout("DenseCorridor_layout.json")
                        running_sim = False
                        tick = 0
                        exited_count = 0
                        dead_count = 0

                        random.seed(42)

                        dist_map = compute_distance_map(exits, grid, grid_width, grid_height)

                        agent_data = {}
                        exposure = {}
                        next_agent_id = 1
                        for (ax, ay) in agents:
                            agent_data[(ax, ay)] = {
                                "id": next_agent_id,
                                "speed": 1.0,
                                "age": 30,
                                "panic": 5
                            }
                            exposure[(ax, ay)] = {"smoke": 0, "fire": 0}
                            next_agent_id += 1
                    except FileNotFoundError:
                        print("No layout found in /data/layouts/")

                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS):
                    cell_size = min(100, cell_size + 5)
                    screen = make_screen(grid_width, grid_height, cell_size)
                elif event.key == pygame.K_MINUS:
                    cell_size = max(5, cell_size - 5)
                    screen = make_screen(grid_width, grid_height, cell_size)
                
                elif show_global_menu:
                    if event.key == pygame.K_UP or event.key == pygame.K_RIGHT:
                        global_panic_value = min(10, global_panic_value + 1)
                    elif event.key == pygame.K_DOWN or event.key == pygame.K_LEFT:
                        global_panic_value = max(0, global_panic_value - 1)
                    elif event.key == pygame.K_RETURN:
                        for pos in agent_data:
                            agent_data[pos]["panic"] = global_panic_value
                        print(f"All agents set to panic level {global_panic_value}")
                        show_global_menu = False
                    elif event.key == pygame.K_ESCAPE:
                        show_global_menu = False
                
                # placeholder adjusting agents attributes
                elif show_menu and selected_agent in agent_data:
                    if event.key == pygame.K_UP:
                        agent_data[selected_agent]["panic"] = min(10, agent_data[selected_agent]["panic"] + 1)
                    elif event.key == pygame.K_DOWN:
                        agent_data[selected_agent]["panic"] = max(0, agent_data[selected_agent]["panic"] - 1)
                    elif event.key == pygame.K_RIGHT:
                        agent_data[selected_agent]["speed"] += 0.1
                    elif event.key == pygame.K_LEFT:
                        agent_data[selected_agent]["speed"] = max(0.1, agent_data[selected_agent]["speed"] - 0.1)
                    elif event.key == pygame.K_ESCAPE:
                        show_menu = False
                        selected_agent = None

            elif event.type == pygame.MOUSEBUTTONDOWN and not running_sim:
                mx, my = pygame.mouse.get_pos()
                gx, gy = mx // cell_size, my // cell_size
                if not in_bounds(gx, gy, grid_width, grid_height):
                    continue

                if show_menu and selected_agent:
                    remove_rect = pygame.Rect(10 + 40, 40 + 160, 100, 30)
                    if remove_rect.collidepoint(mx, my):
                        if selected_agent in agents:
                            agents.remove(selected_agent)
                        if selected_agent in agent_data:
                            del agent_data[selected_agent]
                        if selected_agent in exposure:
                            del exposure[selected_agent]
                        if selected_agent in agent_health:
                            del agent_health[selected_agent]
                        if selected_agent in heat_exposure_ticks:
                            del heat_exposure_ticks[selected_agent]
                        selected_agent = None
                        show_menu = False
                        continue

                if (gx, gy) in agents:
                    selected_agent = (gx, gy)
                    show_menu = True
                    continue

                if mode == MODE_WALL:
                    if (gx, gy) in agents:
                        pass
                    else:
                        grid[gy][gx] = EMPTY if grid[gy][gx] == WALL else WALL
                        if exits:
                            dist_map = compute_distance_map(exits, grid, grid_width, grid_height)

                elif mode == MODE_EXIT:
                    if grid[gy][gx] == WALL:
                        pass
                    else:
                        if grid[gy][gx] == EXIT:
                            grid[gy][gx] = EMPTY
                            if (gx, gy) in exits:
                                exits.remove((gx, gy))
                        else:
                            grid[gy][gx] = EXIT
                            exits.append((gx, gy))
                        dist_map = compute_distance_map(exits, grid, grid_width, grid_height)

                elif mode == MODE_AGENT:
                    if grid[gy][gx] != WALL:
                        if (gx, gy) in agents:
                            agents.remove((gx, gy))
                            if (gx, gy) in agent_data:
                                del agent_data[(gx, gy)]
                            if (gx, gy) in exposure:
                                del exposure[(gx, gy)]
                            if (gx, gy) in agent_health:
                                del agent_health[(gx, gy)]
                            if (gx, gy) in heat_exposure_ticks:
                                del heat_exposure_ticks[(gx, gy)]
                        else:
                            agents.append((gx, gy))
                            agent_data[(gx, gy)] = {
                                "id": next_agent_id,
                                "speed": 1.0,
                                "age": 30,
                                "panic": 1
                            }
                            exposure[(gx, gy)] = {"smoke": 0, "fire": 0}
                            agent_health[(gx, gy)] = HEALTHY
                            heat_exposure_ticks[(gx, gy)] = 0
                            next_agent_id += 1

                elif mode == MODE_FIRE:
                    if grid[gy][gx] == FIRE:
                        grid[gy][gx] = EMPTY
                        temp_grid[gy, gx] = AMBIENT_TEMP
                    else:
                        grid[gy][gx] = FIRE
                        temp_grid[gy, gx] = FIRE_TEMP

        if running_sim:
            tick += 1
            spread_fire_and_smoke(grid, grid_width, grid_height, tick)
            temp_grid = diffuse_temperature(temp_grid, grid, grid_width, grid_height)

        if running_sim and dist_map is not None:
            agents.sort()
            occupied = set(agents)  # cells taken at start of tick
            normal_targets = defaultdict(list) # stores the agents that want to move into each normal floor cell
            exit_targets = defaultdict(list) # stores the agents that want to move into each exit cell 

            survivors_idx = set()
            winners_move = {}
            removed_idx = set()
            incapacitated_idx = set()

            # Stage 0: hazard exposure & injury determination (at current positions)
            for idx, (ax, ay) in enumerate(agents):
                cell = grid[ay][ax]
                temp = temp_grid[ay, ax]
                key = (ax, ay)

                if key not in exposure:
                    exposure[key] = {"smoke": 0, "fire": 0}
                if key not in agent_health:
                    agent_health[key] = HEALTHY
                if key not in heat_exposure_ticks:
                    heat_exposure_ticks[key] = 0

                # Update exposure counters for smoke and fire
                if cell == FIRE:
                    exposure[key]["fire"] += 1
                    exposure[key]["smoke"] = 0
                elif cell == SMOKE:
                    exposure[key]["smoke"] += 1
                    exposure[key]["fire"] = 0
                else:
                    exposure[key]["smoke"] = 0
                    exposure[key]["fire"] = 0

                # Track continuous heat exposure
                if temp >= SAFE_TEMP_THRESHOLD:
                    heat_exposure_ticks[key] += 1
                else:
                    heat_exposure_ticks[key] = 0

                health = agent_health[key]

                if health == INCAPACITATED:
                    continue

                # Check direct flame (FIRE cell)
                if cell == FIRE:
                    nf_flame, f_flame, inc_flame = DIRECT_FLAME_THRESHOLDS

                    if exposure[key]["fire"] >= inc_flame and health != INCAPACITATED:
                        agent_health[key] = INCAPACITATED
                        incapacitated_idx.add(idx)
                        continue
                    elif exposure[key]["fire"] >= f_flame and health in (HEALTHY, INJURED):
                        agent_health[key] = FATALLY_INJURED
                    elif exposure[key]["fire"] >= nf_flame and health == HEALTHY:
                        agent_health[key] = INJURED

                # Check smoke
                nf_smoke, f_smoke, inc_smoke = SMOKE_THRESHOLD

                if exposure[key]["smoke"] >= inc_smoke and health != INCAPACITATED:
                    agent_health[key] = INCAPACITATED
                    incapacitated_idx.add(idx)
                    continue
                elif exposure[key]["smoke"] >= f_smoke and health in (HEALTHY, INJURED):
                    agent_health[key] = FATALLY_INJURED
                elif exposure[key]["smoke"] >= nf_smoke and health == HEALTHY:
                    agent_health[key] = INJURED

                # Check heat - progressive with continuous exposure tracking
                nf_heat, f_heat, inc_heat = get_heat_thresholds(temp)
                heat_ticks = heat_exposure_ticks[key]

                if heat_ticks >= inc_heat and health != INCAPACITATED:
                    agent_health[key] = INCAPACITATED
                    incapacitated_idx.add(idx)
                    continue
                elif heat_ticks >= f_heat and health in (HEALTHY, INJURED):
                    agent_health[key] = FATALLY_INJURED
                elif heat_ticks >= nf_heat and health == HEALTHY:
                    agent_health[key] = INJURED

            # Stage 1: each agent declares an intended move
            for idx, (ax, ay) in enumerate(agents):
                if idx in incapacitated_idx:
                    survivors_idx.add(idx)
                    continue

                if grid[ay][ax] == EXIT:
                    exit_pos = (ax, ay)
                    exit_targets[exit_pos].append(idx)
                    continue

                if dist_map[ay][ax] == float("inf"):
                    survivors_idx.add(idx)
                    continue

                cands = []
                for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
                    nx, ny = ax + dx, ay + dy
                    if in_bounds(nx, ny, grid_width, grid_height):
                        if grid[ny][nx] != WALL and (nx, ny) not in occupied:
                            cands.append((nx, ny))

                if not cands:
                    survivors_idx.add(idx)
                    continue

                cands.sort(key=lambda p: dist_map[p[1]][p[0]])
                best = cands[0]
                cur_dist = dist_map[ay][ax]

                panic_lvl = agent_data.get((ax, ay), {}).get("panic", 0)
                panic_prob = panic_lvl / 10.0

                if len(cands) > 1 and random.random() < panic_prob:
                    move = random.choice(cands[1:])
                else:
                    if dist_map[best[1]][best[0]] < cur_dist:
                        move = best
                    else:
                        survivors_idx.add(idx)
                        continue

                if grid[move[1]][move[0]] == EXIT:
                    exit_targets[move].append(idx)
                else:
                    normal_targets[move].append(idx)

            # Stage 2: resolve conflicts for normal cells (one winner per cell)
            for target, idxs in sorted(normal_targets.items()):
                if len(idxs) == 1:
                    winners_move[idxs[0]] = target
                else:
                    random.shuffle(idxs)
                    winners_move[idxs[0]] = target
                    for loser in idxs[1:]:
                        survivors_idx.add(loser)

            # Stage 3: resolve exits with capacity (queueing at doors)
            exit_cap_remaining = {e: EXIT_CAPACITY_PER_TICK for e in exits}
            for exit_pos, idxs in sorted(exit_targets.items()):
                random.shuffle(idxs)
                cap = exit_cap_remaining.get(exit_pos, EXIT_CAPACITY_PER_TICK)
                winners_to_exit = idxs[:cap]
                removed_idx.update(winners_to_exit)
                exited_count += len(winners_to_exit)
                for winner_idx in winners_to_exit:
                    health_state = agent_health.get(agents[winner_idx], HEALTHY)
                    if health_state == INJURED:
                        exited_injured_count += 1
                    elif health_state == FATALLY_INJURED:
                        exited_fatally_injured_count += 1
                for loser in idxs[cap:]:
                    survivors_idx.add(loser)

            # Stage 4: build next agents list + carry exposure and health to new coords
            new_agents = []
            new_exposure = {}
            new_agent_data = {}
            new_agent_health = {}
            new_heat_exposure_ticks = {}
            for idx, pos in enumerate(agents):
                if idx in removed_idx:
                    if pos in exposure:
                        del exposure[pos]
                    if pos in agent_data:
                        del agent_data[pos]
                    if pos in agent_health:
                        del agent_health[pos]
                    if pos in heat_exposure_ticks:
                        del heat_exposure_ticks[pos]
                    continue
                if idx in incapacitated_idx:
                    if pos in exposure:
                        del exposure[pos]
                    if pos in agent_data:
                        del agent_data[pos]
                    if pos in agent_health:
                        del agent_health[pos]
                    if pos in heat_exposure_ticks:
                        del heat_exposure_ticks[pos]
                    incapacitated_count += 1
                    continue

                new_pos = winners_move[idx] if idx in winners_move else pos
                new_agents.append(new_pos)
                old_exp = exposure.get(pos, {"smoke": 0, "fire": 0})
                new_exposure[new_pos] = old_exp
                if pos in exposure and pos != new_pos:
                    del exposure[pos]

                old_data = agent_data.get(pos)
                if old_data is not None:
                    new_agent_data[new_pos] = old_data
                    if pos != new_pos and pos in agent_data:
                        del agent_data[pos]

                old_health = agent_health.get(pos, HEALTHY)
                new_agent_health[new_pos] = old_health
                if pos in agent_health and pos != new_pos:
                    del agent_health[pos]

                old_heat_ticks = heat_exposure_ticks.get(pos, 0)
                new_heat_exposure_ticks[new_pos] = old_heat_ticks
                if pos in heat_exposure_ticks and pos != new_pos:
                    del heat_exposure_ticks[pos]

            agents = new_agents
            exposure = new_exposure
            agent_data = new_agent_data
            agent_health = new_agent_health
            heat_exposure_ticks = new_heat_exposure_ticks

        screen.fill(WHITE)
        for y in range(grid_height):
            for x in range(grid_width):
                rect = pygame.Rect(x * cell_size, y * cell_size, cell_size, cell_size)
                cell = grid[y][x]

                if cell == WALL:
                    pygame.draw.rect(screen, BLACK, rect)
                elif cell == EXIT:
                    pygame.draw.rect(screen, GREEN, rect)
                else:
                    temp_color = temp_to_color(temp_grid[y, x])
                    pygame.draw.rect(screen, temp_color, rect)

                if cell == SMOKE:
                    smoke_surf = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
                    smoke_surf.fill((120, 120, 120, 140))
                    screen.blit(smoke_surf, (x * cell_size, y * cell_size))

                if cell == FIRE:
                    pygame.draw.rect(screen, (255, 0, 0), rect)

                pygame.draw.rect(screen, GRAY, rect, 1)

        for (ax, ay) in agents:
            rect = pygame.Rect(ax * cell_size, ay * cell_size, cell_size, cell_size)
            health = agent_health.get((ax, ay), HEALTHY)

            if health == HEALTHY:
                color = BLUE
            elif health == INJURED:
                color = ORANGE
            elif health == FATALLY_INJURED:
                color = RED
            elif health == INCAPACITATED:
                color = (128, 0, 128)

            pygame.draw.rect(screen, color, rect)

        # HUD
        inside = len(agents)
        hud_text = f"Inside: {inside}   Exited: {exited_count}   Injured: {exited_injured_count}   Fatal: {exited_fatally_injured_count}   Casualties: {incapacitated_count}"
        hud_surf = font.render(hud_text, True, BLACK)
        screen.blit(hud_surf, (8, 8))
        
        # global panic and future to be speed menu (activate this by clicking m)
        if show_global_menu:
            menu_w, menu_h = 260, 100
            menu_x = (screen.get_width() - menu_w) // 2
            menu_y = (screen.get_height() - menu_h) // 2
            pygame.draw.rect(screen, (230, 230, 230), (menu_x, menu_y, menu_w, menu_h))
            pygame.draw.rect(screen, BLACK, (menu_x, menu_y, menu_w, menu_h), 2)

            title = font.render("Set Panic Level for All Agents", True, BLACK)
            screen.blit(title, (menu_x + 15, menu_y + 10))

            val_text = font.render(f"Panic: {global_panic_value}", True, (0, 0, 180))
            screen.blit(val_text, (menu_x + 90, menu_y + 40))

            hint_text = font.render("up or down arrow to change", True, BLACK)
            screen.blit(hint_text, (menu_x + 25, menu_y + 70))

        #agents info menu
        if show_menu and selected_agent in agent_data:
            data = agent_data[selected_agent]
            ax, ay = selected_agent
            temp_at_agent = temp_grid[ay, ax]
            health = agent_health.get(selected_agent, HEALTHY)
            exp = exposure.get(selected_agent, {"smoke": 0, "fire": 0})
            heat_ticks = heat_exposure_ticks.get(selected_agent, 0)

            nf_heat, f_heat, inc_heat = get_heat_thresholds(temp_at_agent)

            health_str = ["HEALTHY", "INJURED", "FATALLY INJURED", "INCAPACITATED"][health]

            menu_x, menu_y = 10, 40
            pygame.draw.rect(screen, (230, 230, 230), (menu_x, menu_y, 200, 160))
            pygame.draw.rect(screen, BLACK, (menu_x, menu_y, 200, 160), 2)

            lines = [
                f"Agent ID: {data['id']}",
                f"Speed: {data['speed']:.1f}",
                f"Age: {data['age']}",
                f"Panic: {data['panic']}",
                f"Health: {health_str}",
                f"Temp: {temp_at_agent:.1f}°C",
                f"Heat Ticks: {heat_ticks}/{inc_heat if inc_heat != float('inf') else '∞'}",
                f"Smoke: {exp['smoke']}/{SMOKE_THRESHOLD[2]}",
                "ESC = Close"
            ]
            for i, text in enumerate(lines):
                surf = font.render(text, True, BLACK)
                screen.blit(surf, (menu_x + 8, menu_y + 8 + i * 16))

            # draw remove button
            remove_rect = pygame.Rect(menu_x + 50, menu_y + 160, 100, 30)
            pygame.draw.rect(screen, (200, 50, 50), remove_rect)
            pygame.draw.rect(screen, BLACK, remove_rect, 2)
            remove_text = font.render("Remove", True, WHITE)
            screen.blit(remove_text, (remove_rect.x + 18, remove_rect.y + 5))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()