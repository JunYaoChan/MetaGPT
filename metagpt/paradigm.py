from typing import Any, Optional, Dict, List
from pydantic import BaseModel, Field
from metagpt.actions.add_requirement import UserRequirement
from metagpt.roles import Role, ProductManager, Architect, ProjectManager, Engineer, QaEngineer
from metagpt.environment import Environment
from metagpt.context import Context
from metagpt.schema import Document, Message, MESSAGE_ROUTE_TO_ALL
from metagpt.logs import logger
from metagpt.utils.common import NoMoneyException

class Paradigm(BaseModel):
    """
    Flat Organization: All agents are peers and communicate directly with each other.
    No hierarchy, decisions made through consensus or voting.
    """
    investment: float = Field(default=10.0)
    idea: str = Field(default="")
    env: Optional[Environment] = None
    roles: Dict[str, Role] = Field(default_factory=dict)
    votes_needed: int = Field(default=2)  # Minimum votes needed for decision
    
    def __init__(self, context: Context = None, **data: Any):
        super().__init__(**data)
        self.env = Environment(context=context or Context())
        
    def hire(self, roles: list[Role]):
        """Add roles as peers"""
        for role in roles:
            # Ensure each role has a unique profile in the environment
            if role.name:
                # Set the profile to include the role's name for uniqueness
                role.profile = f"{role.profile}_{role.name}"
            
            self.roles[role.profile] = role
            # Each role can communicate directly with all others
            role.peers = [r for r in self.roles.values() if r != role]
        
        # Now add the roles to the environment
        self.env.add_roles(roles)
        
    @property
    def cost_manager(self):
        """Get cost manager"""
        return self.env.context.cost_manager
        
    def invest(self, investment: float):
        """Invest in the organization"""
        self.investment = investment
        self.cost_manager.max_budget = investment
        logger.info(f"Investment: ${investment}.")
        
    def _check_balance(self):
        """Check if there's enough budget"""
        if self.cost_manager.total_cost >= self.cost_manager.max_budget:
            raise NoMoneyException(self.cost_manager.total_cost, f"Insufficient funds: {self.cost_manager.max_budget}")
            
    def run_project(self, idea, send_to: str = ""):
        """Run a project using flat organization structure"""
        self.idea = idea
        # Broadcast to all peers
        self.env.publish_message(
            Message(
                role="Human",
                content=idea,
                cause_by=UserRequirement,
                send_to=send_to or MESSAGE_ROUTE_TO_ALL
            ),
            peekable=False,
        )
        
    async def run(self, n_round=3):
        """Run the flat organization until consensus or rounds exhausted"""
        while n_round > 0:
            if self.env.is_idle:
                logger.debug("All roles are idle.")
                # Get the latest messages from environment memory
                
                break
            logger.debug(self.env.history) 
            # if(n_round ==4 ):
            #     i_context: Document = Field(default_factory=Document)
            #     logger.info(f"I_COntext : {i_context.content}")
            
            n_round -= 1
            self._check_balance()
            await self.env.run()
            logger.debug(f"max {n_round=} left.")
        self.env.archive()
        
    async def run_vote(self, proposal: Message) -> bool:
        """Run a voting process among peers"""
        votes = 0
        for role in self.roles.values():
            if await role.vote_on_proposal(proposal):
                votes += 1
        return votes >= self.votes_needed