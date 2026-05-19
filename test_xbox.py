import pygame

pygame.init()
pygame.display.set_mode((100,100))

pygame.joystick.init()

print(pygame.joystick.get_count())

for i in range(pygame.joystick.get_count()):
    joy = pygame.joystick.Joystick(i)
    joy.init()

    print("Name:", joy.get_name())
    print("GUID:", joy.get_guid())