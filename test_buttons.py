import pygame
import time

pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    raise SystemExit("No joystick found")

j = pygame.joystick.Joystick(0)
j.init()

print(f"Joystick: {j.get_name()}")
print(f"Buttons: {j.get_numbuttons()}, Hats (D-pads): {j.get_numhats()}")
print("Press buttons in your sequence... (Ctrl+C to quit)\n")

num_buttons = j.get_numbuttons()
num_hats = j.get_numhats()

prev_buttons = [0] * num_buttons
prev_hats = [ (0, 0) ] * num_hats

while True:
    pygame.event.pump()

    # Buttons (triangle, circle, X, square, shoulder buttons etc.)
    buttons = [j.get_button(i) for i in range(num_buttons)]
    for i, val in enumerate(buttons):
        if val == 1 and prev_buttons[i] == 0:
            print(f"BUTTON PRESSED: index={i}")
    prev_buttons = buttons

    # Hats = D-pad (left side cross)
    hats = [j.get_hat(i) for i in range(num_hats)]
    for i, hat in enumerate(hats):
        if hat != prev_hats[i]:
            print(f"HAT {i} changed to {hat}")
    prev_hats = hats

    time.sleep(0.05)
