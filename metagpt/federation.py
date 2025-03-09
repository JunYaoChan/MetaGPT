from typing import Any, Optional, Dict, List
from pydantic import BaseModel, Field
from metagpt.actions.add_requirement import UserRequirement
from metagpt.roles import Role, ProductManager, Architect, ProjectManager, Engineer, QaEngineer
from metagpt.environment import Environment
from metagpt.context import Context
from metagpt.schema import Message
from metagpt.logs import logger
from metagpt.utils.common import NoMoneyException

class Federation(BaseModel):
    """
    Federation: Semi-autonomous teams that coordinate through representatives.
    Teams have internal hierarchy but coordinate as peers with other teams.
    """
    investment: float = Field(default=10.0)
    idea: str = Field(default="")
    env: Optional[Environment] = None
    teams: Dict[str, Dict[str, Role]] = Field(default_factory=dict)
    representatives: Dict[str, Role] = Field(default_factory=dict)
    
    def __init__(self, context: Context = None, **data: Any):
        super().__init__(**data)
        self.env = Environment(context=context or Context())
    
    def create_team(self, team_name: str, roles: List[Role], representative: Role):
        """Create a new autonomous team with its representative"""
        self.teams[team_name] = {role.name: role for role in roles}
        self.representatives[team_name] = representative
        
        # Representative can communicate with other representatives
        representative.peer_representatives = list(self.representatives.values())
        
        # Add all roles to environment
        self.env.add_roles(roles + [representative])
    
    async def coordinate_teams(self, message: Message):
        """Coordinate work between teams through representatives"""
        for rep in self.representatives.values():
            await rep.handle_cross_team_communication(message)
            
    @property
    def cost_manager(self):
        """Get cost manager"""
        return self.env.context.cost_manager
        
    def invest(self, investment: float):
        """Invest in the federation"""
        self.investment = investment
        self.cost_manager.max_budget = investment
        logger.info(f"Investment: ${investment}.")
        
    def _check_balance(self):
        """Check if there's enough budget"""
        if self.cost_manager.total_cost >= self.cost_manager.max_budget:
            raise NoMoneyException(self.cost_manager.total_cost, f"Insufficient funds: {self.cost_manager.max_budget}")
            
    def run_project(self, idea, send_to: str = ""):
        """Run a project using federated team structure"""
        self.idea = idea
        # Send to representatives first
        for rep in self.representatives.values():
            self.env.publish_message(
                Message(
                    role="Human",
                    content=idea,
                    cause_by=UserRequirement,
                    send_to=rep.name
                ),
                peekable=False,
            )
            
    async def run(self, n_round=3):
        """Run the federation until completion or rounds exhausted"""
        while n_round > 0:
            if self.env.is_idle:
                logger.debug("All teams are idle.")
                break
            n_round -= 1
            self._check_balance()
            await self.env.run()
            logger.debug(f"max {n_round=} left.")
        self.env.archive()