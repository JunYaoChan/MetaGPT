from typing import Any, Optional, Dict, List
from pydantic import BaseModel, Field
from metagpt.actions.add_requirement import UserRequirement
from metagpt.roles import Role, ProductManager, Architect, ProjectManager, Engineer, QaEngineer
from metagpt.environment import Environment
from metagpt.context import Context
from metagpt.schema import Message
from metagpt.logs import logger
from metagpt.utils.common import NoMoneyException


class HolarchyNode(BaseModel):
    """
    Node in a Holarchy: Can be both whole and part, containing other nodes
    while being contained in higher-level nodes.
    """
    role: Role
    children: Dict[str, 'HolarchyNode'] = Field(default_factory=dict)
    parent: Optional['HolarchyNode'] = None
    
    def add_child(self, node: 'HolarchyNode'):
        """Add a child node to this holon"""
        self.children[node.role.name] = node
        node.parent = self

class Holarchy(BaseModel):
    """
    Holarchy: Nested structure where each unit (holon) is both autonomous
    and part of a larger whole. Flexible hierarchy that can reorganize.
    """
    investment: float = Field(default=10.0)
    idea: str = Field(default="")
    env: Optional[Environment] = None
    root: Optional[HolarchyNode] = None
    all_nodes: Dict[str, HolarchyNode] = Field(default_factory=dict)
    
    def __init__(self, context: Context = None, **data: Any):
        super().__init__(**data)
        self.env = Environment(context=context or Context())
        
    def create_holon(self, role: Role, parent_name: Optional[str] = None) -> HolarchyNode:
        """Create a new holon and optionally attach it to a parent"""
        node = HolarchyNode(role=role)
        self.all_nodes[role.name] = node
        
        if parent_name:
            parent_node = self.all_nodes.get(parent_name)
            if parent_node:
                parent_node.add_child(node)
                # Set up message routing between parent and child
                parent_addrs = self.env.get_addresses(parent_node.role)
                child_addrs = {role.name}
                self.env.set_addresses(role, child_addrs)
                parent_addrs.add(role.name)
                self.env.set_addresses(parent_node.role, parent_addrs)
        elif not self.root:
            self.root = node
            # Initialize root node addresses
            self.env.set_addresses(role, {role.name})
            
        self.env.add_roles([role])
        return node

    async def process_message_chain(self, message: Message, node: HolarchyNode):
        """Process message through the entire chain"""
        # Process current node
        await node.role.process_message(message)
        
        # Create follow-up messages for children if needed
        for child in node.children.values():
            child_message = Message(
                role=node.role.name,
                content=message.content,
                cause_by=message.cause_by,
                send_to=child.role.name,
                refer=message.id  # Link to parent message
            )
            self.env.publish_message(child_message, peekable=True)
    
    # def __init__(self, context: Context = None, **data: Any):
    #     super().__init__(**data)
    #     self.env = Environment(context=context or Context())
    
    # def create_holon(self, role: Role, parent_name: Optional[str] = None) -> HolarchyNode:
    #     """Create a new holon and optionally attach it to a parent"""
    #     node = HolarchyNode(role=role)
    #     self.all_nodes[role.name] = node
        
    #     if parent_name:
    #         parent_node = self.all_nodes.get(parent_name)
    #         if parent_node:
    #             parent_node.add_child(node)
    #     elif not self.root:
    #         self.root = node
            
    #     self.env.add_roles([role])
    #     return node
    
    # async def process_up_chain(self, message: Message, start_node: HolarchyNode):
    #     """Process a message up the holarchy chain"""
    #     current = start_node
    #     while current:
    #         await current.role.process_message(message)
    #         current = current.parent
    
    # async def process_down_chain(self, message: Message, start_node: HolarchyNode):
    #     """Process a message down through child holons"""
    #     await start_node.role.process_message(message)
    #     for child in start_node.children.values():
    #         await self.process_down_chain(message, child)
            
    @property
    def cost_manager(self):
        """Get cost manager"""
        return self.env.context.cost_manager
        
    def invest(self, investment: float):
        """Invest in the holarchy"""
        self.investment = investment
        self.cost_manager.max_budget = investment
        logger.info(f"Investment: ${investment}.")
        
    def _check_balance(self):
        """Check if there's enough budget"""
        if self.cost_manager.total_cost >= self.cost_manager.max_budget:
            raise NoMoneyException(self.cost_manager.total_cost, f"Insufficient funds: {self.cost_manager.max_budget}")
            
    def run_project(self, idea: str):
        """Run a project with improved message propagation"""
        self.idea = idea
        if not self.root:
            raise ValueError("Holarchy must have a root node")
            
        # Create initial message
        initial_message = Message(
            role="Human",
            content=idea,
            cause_by=UserRequirement,
            send_to=self.root.role.name
        )
        
        # Set up routing for root node
        root_addrs = self.env.get_addresses(self.root.role)
        root_addrs.add(self.root.role.name)
        self.env.set_addresses(self.root.role, root_addrs)
        
        # Publish initial message
        self.env.publish_message(initial_message, peekable=True)
        
    async def run(self, n_round=3):
        """Run the holarchy with improved message handling"""
        rounds_without_progress = 0
        max_idle_rounds = 2  # Allow some idle rounds before stopping
        
        while n_round > 0:
            if self.env.is_idle:
                rounds_without_progress += 1
                if rounds_without_progress >= max_idle_rounds:
                    logger.debug("Holarchy is consistently idle. Stopping.")
                    break
            else:
                rounds_without_progress = 0
                
            n_round -= 1
            self._check_balance()
            await self.env.run()
            logger.debug(f"max {n_round=} left.")
            
        self.env.archive()