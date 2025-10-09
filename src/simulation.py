import pygame 
import sys 
from collections import deque, defaultdict
import random



# --- Config ---
CELL_SIZE = 20 # pixels per grid cell, needs to be zoomable later
FPS = 10 

# Colors (R, G, B)
WHITE = (255, 255, 255)
GRAY = (200, 200, 200)
BLACK = (0, 0, 0)
BLUE = (0, 0, 255)
GREEN = (0, 255, 0)

# Cell types 
EMPTY, WALL, EXIT, FIRE, SMOKE = 0, 1, 2, 3, 4

# Placement modes
MODE_WALL, MODE_AGENT, MODE_EXIT, MODE_FIRE = 1, 2, 3, 4

# Fire config
FIRE_SPREAD_DELAY = 10    # fire spreads every X ticks
SMOKE_SPREAD_DELAY = 5    # smoke spreads every X ticks
EXIT_CAPACITY_PER_TICK = 1  # max agents that can go through each exit cell per tick

def make_screen(grid_w, grid_h, cell_size):
    return pygame.display.set_mode((grid_w * cell_size, grid_h * cell_size))

def in_bounds(x, y, grid_w, grid_h):
    return 0 <= x < grid_w and 0 <= y < grid_h

def compute_distance_map(exits, grid, grid_width, grid_height):
    """Return a 2D array of shortest distances from each cell to the nearest exit."""
    INF = float("inf")
    dist_map = [[INF for _ in range(grid_width)] for _ in range(grid_height)]
    q = deque()

    # Start BFS from all exits
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
                            if grid[ny][nx] == EMPTY:
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

    # Ask the user for grid size (weight and height) 
    try: 
        grid_width = int(input("Enter grid width (number of cells): "))
        grid_height = int(input("Enter grid height (number of cells): "))
    except ValueError:
        print("Invalid input, using default 30x20)")
        grid_width = 30
        grid_height = 20
    
    # Create the window using grid sizes 
    cell_size = CELL_SIZE
    screen = make_screen(grid_width, grid_height, cell_size)
    pygame.display.set_caption("Evacuation Simulation")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 22) 

    agents = []   
    exits = []
    dist_map = None
    running_sim = False  
    mode = MODE_AGENT  
    tick = 0
    exited_count = 0

    # Agent data and menu tracking
    agent_data = {} # {(x, y): {"id": int, "speed": float, "age": int, "panic": int}}
    selected_agent = None
    next_agent_id = 1 
    show_menu = False

    # Create a 2D list initialized to EMPTY
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
                    running_sim = not running_sim
                elif event.key == pygame.K_r:
                    grid = [[EMPTY for _ in range(grid_width)] for _ in range(grid_height)]
                    agents = []
                    exits = []
                    dist_map = None
                    running_sim = False
                    mode = MODE_AGENT
                    exited_count = 0
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS):
                    # zoom in 
                    cell_size = min(100, cell_size + 5)
                    screen = make_screen(grid_width, grid_height, cell_size)
                elif event.key == pygame.K_MINUS:
                    # zoom out 
                    cell_size = max(5, cell_size - 5)
                    screen = make_screen(grid_width, grid_height, cell_size)
                
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

                # remove button when menu open
                if show_menu and selected_agent:
                    remove_rect = pygame.Rect(10 + 40, 40 + 120, 100, 30)
                    if remove_rect.collidepoint(mx, my):
                        if selected_agent in agents:
                            agents.remove(selected_agent)
                        if selected_agent in agent_data:
                            del agent_data[selected_agent]
                        selected_agent = None
                        show_menu = False
                        continue
                
                if (gx, gy) in agents:
                    selected_agent = (gx, gy)
                    show_menu = True
                    continue

                if mode == MODE_WALL:
                    if (gx, gy) in agents:
                        pass  # ignore wall placement if agent is there
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
                        else:
                            agents.append((gx, gy))
                            agent_data[(gx, gy)] = {
                                "id": next_agent_id,
                                "speed": 1.0,
                                "age": 30,
                                "panic": 5
                            }
                            next_agent_id += 1

                
                elif mode == MODE_FIRE:
                    if grid[gy][gx] == FIRE:
                        grid[gy][gx] = EMPTY
                    else:
                        grid[gy][gx] = FIRE
                

        if running_sim:
            tick += 1
            spread_fire_and_smoke(grid, grid_width, grid_height, tick)

        if running_sim and dist_map is not None:
            occupied = set(agents)  # cells taken at start of tick
            normal_targets = defaultdict(list) # stores the agents that want to move into each normal floor cell
            exit_targets = defaultdict(list) # stores the agents that want to move into each exit cell 

            survivors_idx = set() # agents that will stay in place this tick
            winners_move = {} # agent_idx -> new (x,y)
            removed_idx = set() # agents that exit this tick

            # Stage 1: each agent declares an intended move (no stepping into occupied cells) 
            for idx, (ax, ay) in enumerate(agents):
                # Agent already on an exit leaves immediately
                if grid[ay][ax] == EXIT:
                    exited_count += 1
                    continue
                
                # No known path -> wait
                if dist_map[ay][ax] == float("inf"):
                    survivors_idx.add(idx)
                    continue
                
                best_move = None
                best_dist = dist_map[ay][ax]
                for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
                    nx, ny = ax + dx, ay + dy
                    if in_bounds(nx, ny, grid_width, grid_height):
                        # crowding rule: cannot move into a cell that is currently occupied
                        if grid[ny][nx] != WALL and (nx, ny) not in occupied and dist_map[ny][nx] < best_dist:
                            best_dist = dist_map[ny][nx]
                            best_move = (nx, ny)

                if best_move is None:
                    survivors_idx.add(idx)
                    continue
                
                # If target is an EXIT cell, propose to exit; else propose normal move
                if grid[best_move[1]][best_move[0]] == EXIT:
                    exit_targets[best_move].append(idx)
                else:
                    normal_targets[best_move].append(idx)

            # Stage 2: resolve conflicts for normal cells (one winner per cell)
            for target, idxs in normal_targets.items():
                if len(idxs) == 1:
                    winners_move[idxs[0]] = target
                else:
                    random.shuffle(idxs)
                    winners_move[idxs[0]] = target
                    for loser in idxs[1:]:
                        survivors_idx.add(loser)

            # Stage 3: resolve exits with capacity (queueing at doors)
            exit_cap_remaining = {e: EXIT_CAPACITY_PER_TICK for e in exits}
            for exit_pos, idxs in exit_targets.items():
                random.shuffle(idxs)
                cap = exit_cap_remaining.get(exit_pos, EXIT_CAPACITY_PER_TICK)
                winners_to_exit = idxs[:cap]
                removed_idx.update(winners_to_exit)
                for loser in idxs[cap:]:
                    survivors_idx.add(loser)

            # --- Stage 4: build next agent list ---
            new_agents = []
            for idx, pos in enumerate(agents):
                if idx in removed_idx:
                    continue
                if idx in winners_move:
                    new_agents.append(winners_move[idx])
                elif idx in survivors_idx:
                    new_agents.append(pos)
                else:
                    # agents that were on EXIT already were skipped above (they "left")
                    pass
                
            agents = new_agents


        screen.fill(WHITE)
        for y in range(grid_height):
            for x in range(grid_width):
                rect = pygame.Rect(x * cell_size, y * cell_size, cell_size, cell_size)
                cell = grid[y][x]
                if cell == WALL:
                    pygame.draw.rect(screen, BLACK, rect)
                elif cell == EXIT:
                    pygame.draw.rect(screen, GREEN, rect)
                elif cell == FIRE:
                    pygame.draw.rect(screen, (255, 0, 0), rect)
                elif cell == SMOKE:
                    pygame.draw.rect(screen, (120, 120, 120), rect)
                else:
                    pygame.draw.rect(screen, WHITE, rect)
                pygame.draw.rect(screen, GRAY, rect, 1)
        
        for (ax, ay) in agents:
            rect = pygame.Rect(ax * cell_size, ay * cell_size, cell_size, cell_size)
            pygame.draw.rect(screen, BLUE, rect)

        # HUD
        remaining = len(agents)
        hud_text = f"Exited: {exited_count}   Remaining: {remaining}"
        hud_surf = font.render(hud_text, True, BLACK)
        screen.blit(hud_surf, (8, 8))


        #agents info menu
        if show_menu and selected_agent in agent_data:
            data = agent_data[selected_agent]
            menu_x, menu_y = 10, 40
            pygame.draw.rect(screen, (230, 230, 230), (menu_x, menu_y, 180, 120))
            pygame.draw.rect(screen, BLACK, (menu_x, menu_y, 180, 120), 2)

            lines = [
                f"Agent ID: {data['id']}",
                f"Speed: {data['speed']:.1f}",
                f"Age: {data['age']}",
                f"Panic: {data['panic']}",
                "ESC = Close"
            ]
            for i, text in enumerate(lines):
                surf = font.render(text, True, BLACK)
                screen.blit(surf, (menu_x + 8, menu_y + 8 + i * 20))
            
            # draw remove button
            remove_rect = pygame.Rect(menu_x + 40, menu_y + 120, 100, 30)
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

