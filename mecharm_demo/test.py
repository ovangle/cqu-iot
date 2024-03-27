import time
import pdb

from pymycobot.mycobot import MyCobot

from pymycobot.genre import Angle
from pymycobot import PI_PORT, PI_BAUD

pickup_at = [-90, 90, -100, -0, 0, -60]
dropoff_at = [90, 90, -100, -0, 0, -60]

def get_pencil(mc):
    mc.send_angle(Angle.J6.value, 30, 100)
    time.sleep(2.5)
    mc.set_gripper_value(30, 100)
    time.sleep(2.5)
    
    print('pencil in position (y/N)?')
    x = input()
    while not x.lower().startswith('y'):
        if x.lower().startswith('n'):
            raise Exception('Did not pick up pencil')
    
        print('input y/N')
        x = input()

    mc.set_gripper_value(10, 100)
    time.sleep(2.5)
    mc.send_angle(Angle.J6.value, -60, 100)
    time.sleep(2.5)

def drop_pencil(mc):
    mc.set_gripper_value(100, 100)
    time.sleep(0.5)


def do_test(mc):
    print('going to pickup location ({0})'.format(pickup_at))
    mc.send_angles(pickup_at, 50)
    time.sleep(2.5)
    print('at pickup location ({0})'.format(mc.get_angles()))

    get_pencil(mc)

    
    mc.send_angles(dropoff_at, 50)
    print('going to dropoff location ({0})'.format(dropoff_at))
    time.sleep(2.5)
    print('at dropoff location ({0})'.format(mc.get_angles()))

    drop_pencil(mc)

if __name__ == '__main__':
    mc = MyCobot(PI_PORT, PI_BAUD)
    try:
        do_test(mc)
    finally:
        mc.release_all_servos()

