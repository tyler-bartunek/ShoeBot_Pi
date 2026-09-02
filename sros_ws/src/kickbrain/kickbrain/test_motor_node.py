#Basic ROS functionality
import rclpy
from rclpy.node import Node

#Topic message formats
from kickbot_interfaces.msg import ActuatorCmdFrame, BusState, BotState
from geometry_msgs.msg import Twist

#Service message formats
from kickbot_interfaces.srv import ConfigUpdate

#Configuration files for different kinematic configurations
from kick_configs import CONFIGURATIONS, PARTIAL_CONFIGURATIONS, TestMotor

class TestMotorNode(Node):

    def __init__(self):
        super().__init__('test_motor_node')

        #Kick Robot parameters
        self.config = None
        self.kinematic_config = 'Echo'

        self.desired_vel = None
        self.last_feedback = None

        #Create control loop parameters
        control_timer_freq = 100.0  # Hz, subject to Pi 3B+ reality
        self.control_timer_period = 1 / control_timer_freq
        self.control_timer = self.create_timer(self.control_timer_period, self.control_loop)

        #Replace the motion_plan topic subscription with a timer callback that generates pseudo-commands
        cmd_timer_freq = 1.0  # Hz, for testing purposes
        cmd_timer_period = 1 / cmd_timer_freq
        self.cmd_timer = self.create_timer(cmd_timer_period, self.cmd_timer_callback)

        #Create the subscriber to the bus state topic
        self.bus_subscriber = self.create_subscription(BusState, '/bus_state', self.bus_callback, 10)

        #Create service server for configuration updates
        self.config_server = self.create_service(ConfigUpdate, '/config_update', self.config_update_callback)
        
        #Publisher for bot state topic
        bot_state_timer_freq = 20.0  # Hz, subject to Pi 3B+ reality
        self.state_timer_period = 1 / bot_state_timer_freq
        self.state_timer = self.create_timer(self.state_timer_period, self.state_update)
        self.bot_state_publisher = self.create_publisher(BotState, '/bot_state', 10)

        #Create publisher for actuator command topic
        self.actuator_cmd_publisher = self.create_publisher(ActuatorCmdFrame,'/cmd', 10)

    def config_ready(self) -> bool:
        if not self.config:
            self.get_logger().warn("No configuration loaded, waiting for ConfigUpdate service call")
            return False
        return True

    def lookup_configuration(self, active_paths, device_ids):
        
        key = frozenset(d for d in device_ids if d is not None)

        if key in CONFIGURATIONS:
            config_class = CONFIGURATIONS[key]
            self.config = config_class(self, active_paths, device_ids)
            self.kinematic_config = f"{config_class.__name__}"
            self.get_logger().info(f"Loaded configuration: {config_class.__name__}")
        elif key in PARTIAL_CONFIGURATIONS:
            # Check for if it is one of the two motor configurations, and if so, assign the test_motor configuration which just sends a simple command to the motor
            if key == frozenset({0x00, 0x02}) or key == frozenset({0x00, 0x03}):
                self.config = TestMotor(self, active_paths, device_ids)
                self.kinematic_config = "TestMotor"
                self.get_logger().info(f"Loaded configuration: TestMotor for partial motor configuration")
        else:
            self.get_logger().error(f"Unrecognized device configuration: {key}")

    def config_update_callback(self, call, response):

        self.lookup_configuration(call.active_paths, call.device_ids)
        response.configuration = self.kinematic_config

        return response

    def cmd_timer_callback(self):
        
        #Generate a pseudo-velocity command that iterates from 0 to the max motor command, then back down, to test the echo functionality
        if self.desired_vel is None:
            self.desired_vel = Twist()
            self.angular_cmd_value = 0
            self.increment = 100
        else:
            #Increment command values together to maintain a consistent ratio between linear and angular components, which should be reflected in the feedback if the echo configuration is working correctly
            self.angular_cmd_value += self.increment
            if self.angular_cmd_value > 10000 or self.angular_cmd_value < -10000:
                self.increment *= -1
                self.angular_cmd_value += self.increment * 2
            
            #Set linear and angular components of the desired velocity message
            # to be equal-valued components that have magnitude equal to the linear_cmd_value and angular_cmd_value arguments
            self.desired_vel.angular.z = self.angular_cmd_value


    def bus_callback(self, msg):
        
        self.last_feedback = msg

    def control_loop(self):

        if not self.config:
            return
        if self.desired_vel is None:
            return

        commands = self.config.fetch_commands(self.desired_vel, self.last_feedback)
        msg = ActuatorCmdFrame()
        msg.cmd_data = commands
        self.actuator_cmd_publisher.publish(msg)

    def state_update(self):
        
        msg = BotState()
        if self.last_feedback:
            msg.active_paths = self.last_feedback.active_paths
            msg.device_ids = self.last_feedback.device_ids
            msg.voltage = 3.3 #Hard-coded for now
        
        self.bot_state_publisher.publish(msg)
           



def main(args = None):

    rclpy.init(args = args)

    test_motor_node = TestMotorNode()

    rclpy.spin(test_motor_node)

    test_motor_node.destroy_node()
    rclpy.shutdown()

