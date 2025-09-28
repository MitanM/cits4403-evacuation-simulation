import pygame 
import sys 

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
EMPTY, WALL, EXIT = 0, 1, 2 

# Placement modes
MODE_WALL, MODE_AGENT, MODE_EXIT = 1, 2, 3


def make_screen(grid_w, grid_h, cell_size):
    return pygame.display.set_mode((grid_w * cell_size, grid_h * cell_size))

def in_bounds(x, y, grid_w, grid_h):
    return 0 <= x < grid_w and 0 <= y < grid_h


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

    agents = []   
    running_sim = False  
    mode = MODE_AGENT  

    # Create a 2D list initialized to EMPTY
    grid = [[EMPTY for _ in range(grid_width)] for _ in range(grid_height)]

    running = True 
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False 

        screen.fill(WHITE)
        for y in range(grid_height):
            for x in range(grid_width):
                rect = pygame.Rect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                pygame.draw.rect(screen, WHITE, rect)
                pygame.draw.rect(screen, GRAY, rect, 1)


        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

