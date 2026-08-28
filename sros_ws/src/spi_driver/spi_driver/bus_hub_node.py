
#Import client library
import rclpy
from rclpy.node import Node
from rcl_interfaces.msg import SetParametersResult

from .bus_manager import BusManager

#Import custom interfaces
from kickbot_interfaces.msg import BusState, ActuatorCmdFrame
from kickbot_interfaces.srv import ConfigUpdate


class BusHubNode(Node):
    
    PIN_PARAM_NAMES = ['oe_pin', 'latch_pin', 'sck_pin', 'data_pin', 'sync_pin', 'ce_pin_option', 'spi_channel']

    def __init__(self):
        super().__init__("bus_hub")
        
        #Shift register pinouts
        self.declare_parameter('oe_pin', 5)
        self.declare_parameter('latch_pin', 6)
        self.declare_parameter('sck_pin', 13)
        self.declare_parameter('data_pin', 26)
        
        #SPI Harness pinouts, continued
        self.declare_parameter('sync_pin', 25)
        self.declare_parameter('ce_pin_option', 0)
        self.declare_parameter('spi_channel', 0)
        
        self.add_on_set_parameters_callback(self.parameter_callback)

        #Create the BusManager object, fetch the initial state of the bus
        self.bus = BusManager(self)
        for path_id, device in self.bus.devices.items():
            self.bus.discover_device(device)

        self.config_client = self.create_client(ConfigUpdate, "/config_update")

        #Create a timer and timer callback that polls each device periodically
        self.bus_publisher = self.create_publisher(BusState, "/bus_state", 10)
        timer_freq = 100. #Hz
        timer_period = 1. / timer_freq # seconds
        self.timer = self.create_timer(timer_period, self.timer_callback)

        #Create a subscriber that listens for commands from the KickBot node
        self.cmd_subscriber = self.create_subscription(ActuatorCmdFrame, "/cmd", self.cmd_callback, 10)

    def timer_callback(self):
        self.detect_config_change()
        self.bus.poll_devices()
    
    def cmd_callback(self, msg):

        for path in range(self.bus.num_paths):
            #Extract the command data for this path from the message, and update the bus manager's cmd attribute
            cmd_data = msg.cmd_data[path*4:path*4+4] #Assuming each path has 4 bytes of command data, may need to be updated based on actual message format
            self.bus.devices[path].cmd = [int(cmd) for cmd in cmd_data] #Not ideal, but I can't have these np.uint8's floating around

    def detect_config_change(self):

        if self.bus.active_paths != self.bus.prev_active_paths:
            request = ConfigUpdate.Request()
            request.active_paths = self.bus.active_paths
            request.device_ids = self.bus.device_ids
            future = self.config_client.call_async(request)
            future.add_done_callback(self.config_update_callback)

    def config_update_callback(self, future):
        try:
            result = future.result()
            self.get_logger().info(f"Config update response: {result.configuration}")
        except Exception as e:
            self.get_logger().error(f"Config update service call failed: {e}")
            
    def build_pin_dict(self):
        
        return {param:self.get_parameter(param)._value for param in self.PIN_PARAM_NAMES}
    
    def parameter_callback(self, params):
        
        if any(param.name in pin_params for param in params):
            # Cleanly shut down existing harness
            self.bus.spi.cleanup()
            # Rebuild pin dict with updated values
            self.bus.spi = Harness(self.build_pin_dict())
            
        return SetParametersResult(successful=True)




def main(args = None):

    #Start the client library
    rclpy.init(args = args)

    bus_hub = BusHubNode()

    #TODO: Check if the spin_until_future_complete makes more sense here
    rclpy.spin(bus_hub)

    #Release the chip and request objects, as well as the spi kernel
    bus_hub.bus.reg.cleanup()
    bus_hub.bus.spi.disable_bus()
    #Shutdown ROS stuff
    bus_hub.destroy_node()
    rclpy.shutdown()



if __name__ == "__main__":
    main()