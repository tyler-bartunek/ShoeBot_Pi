
#Basic ROS functionality
import rclpy
from rclpy.node import Node
from rcl_interfaces.msg import SetParametersResult

#Topic message formats
from kickbot_interfaces.msg import BatteryInfo, ActuatorCmdFrame, BusState, BotState
from geometry_msgs.msg import Twist

#Service message formats
from kickbot_interfaces.srv import ConfigUpdate

#Configuration files for different kinematic configurations
from kick_configs import CONFIGURATIONS, PARTIAL_CONFIGURATIONS

class KickbrainNode(Node):

    def __init__(self):
        super().__init__('shoebot_node')

        #ShoeBot parameters
        self.battery_threshold = 3.1 #Voltage threshold for low battery warning, in volts
        self.config = None
        self.kinematic_config = 'Echo'
        #modified by GUI
        self.declare_parameter('rail-spacing', 100) #Separation between rails, mm. Distance between central flat portions of rail geometry
        self.declare_parameter('module-placement', [0, 0, 0, 0, 0, 0]) #Module offset from assumed connection location, #notches

        self.desired_vel = None
        self.last_feedback = None

        #Create control loop parameters
        control_timer_freq = 100.0  # Hz, subject to Pi 3B+ reality
        self.control_timer_period = 1 / control_timer_freq
        self.control_timer = self.create_timer(self.control_timer_period, self.control_loop)

        #Create the subscriber to the battery monitoring topic
        self.battery_subscriber = self.create_subscription(BatteryInfo, 'battery-info', self.battery_callback, 10)

        #Create the subscriber to the motion_plan topic, notably velocity commands
        self.vel_subscriber = self.create_subscription(Twist, '/cmd_vel', self.vel_callback, 10)

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
            self.get_logger().warn(f"Partial configuration detected: {PARTIAL_CONFIGURATIONS[key]}")
        else:
            self.get_logger().error(f"Unrecognized device configuration: {key}")

    def config_update_callback(self, call, response):

        self.lookup_configuration(call.active_paths, call.device_ids)
        response.configuration = self.kinematic_config

        return response

    def battery_callback(self, msg):
        #TODO: Handle incoming battery status message, and decide how to warn the user and when to shut it down
        self.voltage = msg.voltage
        if msg.voltage < self.battery_threshold:
            self.get_logger().warn(f"Battery voltage low: {msg.voltage:.2f}V")

        pass

    def vel_callback(self, msg):
        
        self.desired_vel = msg

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
        msg.active_paths = self.last_feedback.active_paths
        msg.device_ids = self.last_feedback.device_ids
        msg.voltage = self.voltage
        #TODO: Add velocity update to BotState definition
        
        self.bot_state_publisher.publish(msg)

        

        
            



def main(args = None):

    rclpy.init(args = args)

    kickbrain_node = KickbrainNode()

    rclpy.spin(kickbrain_node)

    kickbrain_node.destroy_node()
    rclpy.shutdown()