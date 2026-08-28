from launch.actions import IncludeLaunchDescription
from launch_xml.launch_description_sources import XMLLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
from pathlib import Path

from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    
    rosbridge_launch_path = str(Path(
        get_package_share_directory('rosbridge_server')) / 'launch' / 'rosbridge_websocket_launch.xml')

    rosbridge_include = IncludeLaunchDescription(
        XMLLaunchDescriptionSource(rosbridge_launch_path)
    )
    
    return LaunchDescription([
        rosbridge_include,
        Node(
            package='kickbrain',
            executable='test_motor',
            name='motor_send',
            output='screen',
        ),
        Node(
            package='spi_driver',
            executable='spi_hub',
            name='comms_hub',
            output='screen',
        ),
    ])