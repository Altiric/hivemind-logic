#!/usr/bin/env python3
"""
Movement Logic Module v2.0.0
Hot-loadable movement coordination logic
"""

__version__ = "2.0.0"

import math
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# Import from parent directories
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.data_models import ClientData, Position, TaskData, Config

logger = logging.getLogger('hivemind.movement')

class MovementCoordinator:
    """Hot-loadable movement coordinator"""
    # ... your existing movement logic here ...
    
    def __init__(self):
        self.last_positions: Dict[str, Position] = {}
        
    def generate_movement_tasks(self, clients: Dict[str, ClientData], config: Config, 
                              client_manager=None) -> List[Tuple[str, TaskData]]:
        """
        Generate movement tasks for all clients based on follow leader logic
        
        Args:
            clients: Active clients dictionary
            config: Global configuration
            client_manager: Optional client manager for per-client configs
        
        Returns:
            List of (client_serial, TaskData) tuples
        """
        tasks = []
        
        # Check if follow leader is enabled globally
        if not config.follow_leader or config.behavior_mode != "Follow Leader":
            return tasks
        
        # Find the leader
        leader = self._find_leader(clients, config.leader_serial)
        if not leader:
            logger.debug("No leader found, no movement tasks generated")
            return tasks
        
        # Get active followers
        followers = []
        for client in clients.values():
            if client.serial == leader.serial:
                continue
                
            # Check client-specific config if available
            if client_manager:
                client_config = client_manager.get_client_config(client.serial, config)
                # Skip if this client has custom tactics that disable following
                if not client_config.follow_leader or client_config.behavior_mode != "Follow Leader":
                    logger.debug(f"Skipping {client.name} - custom tactics disable following")
                    continue
            
            if client.is_active(config.client_timeout):
                followers.append(client)
        
        if not followers:
            logger.debug("No active followers, no movement tasks generated")
            return tasks
        
        logger.info(f"Generating movement for {len(followers)} followers around leader {leader.name}")
        
        # Calculate formation positions for each follower
        for i, follower in enumerate(followers):
            # Get client-specific config for distances
            follower_config = config
            if client_manager:
                follower_config = client_manager.get_client_config(follower.serial, config)
            
            # Calculate positions using follower-specific config
            formation_positions = self._calculate_formation_positions(
                leader.pos, len(followers), follower_config
            )
            
            target_pos = formation_positions[i]
            
            # Check if follower needs to move
            if self._should_move(follower, target_pos, follower_config):
                task = TaskData(
                    action="move",
                    args={"x": target_pos.x, "y": target_pos.y}
                )
                tasks.append((follower.serial, task))
                logger.debug(f"Moving {follower.name} to ({target_pos.x}, {target_pos.y})")
        
        return tasks
    
    def _find_leader(self, clients: Dict[str, ClientData], preferred_serial: Optional[str]) -> Optional[ClientData]:
        """Find the leader client"""
        # Use preferred leader if available and active
        if preferred_serial and preferred_serial in clients:
            leader = clients[preferred_serial]
            if leader.is_active():
                return leader
        
        # Otherwise, auto-select first active client
        for client in clients.values():
            if client.is_active():
                logger.info(f"Auto-selected {client.name} as leader")
                return client
        
        return None
    
    def _calculate_formation_positions(self, leader_pos: Position, 
                                     follower_count: int, config: Config) -> List[Position]:
        """Calculate circular formation positions around leader"""
        positions = []
        
        if follower_count == 0:
            return positions
        
        # Base distance from config
        min_dist = config.leader_distance['min']
        max_dist = config.leader_distance['max']
        
        # Adjust distance based on formation tightness and follower count
        # More followers = need more space
        base_distance = min_dist + (max_dist - min_dist) * (1 - config.formation_tightness / 10)
        distance = max(min_dist, min(max_dist, base_distance + (follower_count - 1) * 0.5))
        
        # Calculate positions in a circle around leader
        angle_step = (2 * math.pi) / follower_count
        
        for i in range(follower_count):
            angle = i * angle_step
            x = leader_pos.x + int(distance * math.cos(angle))
            y = leader_pos.y + int(distance * math.sin(angle))
            
            # Find nearest walkable tile (for now, just use calculated position)
            # TODO: Check against client's tile data when implementing full spatial system
            positions.append(Position(x, y, leader_pos.z))
        
        return positions
    
    def _should_move(self, client: ClientData, target_pos: Position, config: Config) -> bool:
        """Determine if client should move to target position"""
        current_pos = client.pos
        
        # Calculate distance to target
        distance = current_pos.distance_to(target_pos)
        
        # Only move if beyond movement threshold
        if distance <= config.movement_threshold:
            return False
        
        # Check if we're already moving towards this position
        # (Avoid spamming move commands)
        last_pos = self.last_positions.get(client.serial)
        if last_pos and last_pos.distance_to(target_pos) < 1:
            # We already sent a move command to roughly this position
            return False
        
        # Update last position
        self.last_positions[client.serial] = target_pos
        
        return True
    
    def cleanup_inactive_clients(self, active_serials: List[str]):
        """Remove inactive clients from tracking"""
        self.last_positions = {
            serial: pos for serial, pos in self.last_positions.items()
            if serial in active_serials
        }