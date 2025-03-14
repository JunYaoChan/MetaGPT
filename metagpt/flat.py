# from typing import Any, Optional, Dict, List
# from pydantic import BaseModel, Field
# from metagpt.actions.add_requirement import UserRequirement
# from metagpt.actions.project_management import WriteTasks
# from metagpt.roles import Role, ProductManager, Architect, ProjectManager, Engineer, QaEngineer
# from metagpt.environment import Environment
# from metagpt.context import Context
# from metagpt.schema import Message, MESSAGE_ROUTE_TO_ALL
# from metagpt.logs import logger
# from metagpt.utils.common import NoMoneyException
# from metagpt.actions.project_management_an import TASK_LIST, REFINED_TASK_LIST
# import json

# class Flat(BaseModel):
#     """
#     Flat Organization: All agents are peers and communicate directly with each other.
#     No hierarchy, decisions made through consensus or voting.
#     """
#     investment: float = Field(default=10.0)
#     idea: str = Field(default="")
#     env: Optional[Environment] = None
#     roles: Dict[str, Role] = Field(default_factory=dict)
#     votes_needed: int = Field(default=2)  # Minimum votes needed for decision
#     task_distribution_done: bool = Field(default=False)
    
#     def __init__(self, context: Context = None, **data: Any):
#         super().__init__(**data)
#         self.env = Environment(context=context or Context())
#         self.task_distribution_done = False
        
#     def hire(self, roles: list[Role]):
#         """Add roles as peers"""
#         for role in roles:
#             # Ensure each role has a unique profile in the environment
#             if role.name:
#                 # Set the profile to include the role's name for uniqueness
#                 role.profile = f"{role.profile}_{role.name}"
            
#             self.roles[role.profile] = role
#             # Each role can communicate directly with all others
#             role.peers = [r for r in self.roles.values() if r != role]
        
#         # Now add the roles to the environment
#         self.env.add_roles(roles)
        
#     @property
#     def cost_manager(self):
#         """Get cost manager"""
#         return self.env.context.cost_manager
        
#     def invest(self, investment: float):
#         """Invest in the organization"""
#         self.investment = investment
#         self.cost_manager.max_budget = investment
#         logger.info(f"Investment: ${investment}.")
        
#     def _check_balance(self):
#         """Check if there's enough budget"""
#         if self.cost_manager.total_cost >= self.cost_manager.max_budget:
#             raise NoMoneyException(self.cost_manager.total_cost, f"Insufficient funds: {self.cost_manager.max_budget}")
            
#     def run_project(self, idea, send_to: str = ""):
#         """Run a project using flat organization structure"""
#         self.idea = idea
#         # Broadcast to all peers
#         self.env.publish_message(
#             Message(
#                 role="Human",
#                 content=idea,
#                 cause_by=UserRequirement,
#                 send_to=send_to or MESSAGE_ROUTE_TO_ALL
#             ),
#             peekable=False,
#         )
        
#     def _get_engineers(self):
#         """Get all engineer roles in the organization"""
#         engineers = []
#         # Check if roles is a dictionary with profile keys
#         if isinstance(self.roles, dict):
#             for profile, role in self.roles.items():
#                 if "Engineer" in role.__class__.__name__ and "QaEngineer" not in role.__class__.__name__:
#                     engineers.append(role)
#                     logger.info(f"Found engineer: {role.name} ({profile})")
        
#         # If no engineers found in roles dictionary, check the env.roles list
#         if not engineers and self.env and hasattr(self.env, 'roles'):
#             for role in self.env.roles:
#                 if "Engineer" in role.__class__.__name__ and "QaEngineer" not in role.__class__.__name__:
#                     engineers.append(role)
#                     logger.info(f"Found engineer in env: {role.name} ({role.__class__.__name__})")
        
#         if not engineers:
            
#             logger.warning("No engineers found in the organization")
#         else:
#             logger.info(f"Found {len(engineers)} engineers: {[eng.name for eng in engineers]}")
        
#         return engineers
        
#     def _extract_tasks_from_messages(self):
#         """Extract tasks from WriteTasks messages in the environment"""
#         tasks = []
#         for role in self.env.roles:
#             if isinstance(role, ProjectManager):
#                 for msg in role.rc.memory.get():
#                     if hasattr(msg, 'instruct_content') and msg.instruct_content:
#                         try:
#                             if hasattr(msg.instruct_content, 'docs'):
#                                 docs = msg.instruct_content.docs
#                                 for filename, doc in docs.items():
#                                     content = doc.content
#                                     try:
#                                         task_data = json.loads(content)
#                                         # Check different possible task list keys
#                                         task_list = task_data.get("Task list") or task_data.get(TASK_LIST.key) or task_data.get(REFINED_TASK_LIST.key)
#                                         if task_list:
#                                             tasks.extend(task_list)
#                                             logger.info(f"Found {len(task_list)} tasks in document {filename}")
#                                     except json.JSONDecodeError:
#                                         logger.error(f"Could not parse JSON from document content")
#                         except Exception as e:
#                             logger.error(f"Failed to extract tasks from message: {e}")
                            
#         logger.info(f"Total tasks extracted: {len(tasks)}")
#         return tasks
            
#     def distribute_tasks(self):
#         """Distribute tasks among engineers using round-robin approach"""
#         if self.task_distribution_done:
#             return
            
#         engineers = self._get_engineers()
#         if not engineers:
#             logger.warning("No engineers found in the organization")
#             return
            
#         # Extract tasks from messages
#         tasks = self._extract_tasks_from_messages()
#         if not tasks:
#             logger.warning("No tasks found to distribute")
#             return
            
#         logger.info(f"Distributing {len(tasks)} tasks among {len(engineers)} engineers")
        
#         # Distribute tasks among engineers using round-robin
#         for i, task in enumerate(tasks):
#             engineer_index = i % len(engineers)
#             engineer = engineers[engineer_index]
            
#             # Assign task to engineer
#             if not hasattr(engineer, "assigned_tasks"):
#                 engineer.assigned_tasks = []
#             engineer.assigned_tasks.append(task)
            
#             logger.info(f"Assigned task '{task}' to {engineer.name}")
            
#         self.task_distribution_done = True
        
#     async def run(self, n_round=3):
#         """Run the flat organization until consensus or rounds exhausted"""
#         task_distribution_round = 4  # After this round, distribute tasks
        
#         for current_round in range(n_round):
#             if self.env.is_idle:
#                 logger.debug("All roles are idle.")
#                 break
                
#             # Check if we need to distribute tasks
#             if current_round == task_distribution_round and not self.task_distribution_done:
                
#                 self.distribute_tasks()
                
#             # Run a round
#             self._check_balance()
#             await self.env.run()
#             logger.debug(f"Round {current_round+1}/{n_round} completed.")
            
#         self.env.archive()
    
#     async def run_vote(self, proposal: Message) -> bool:
#         """Run a voting process among peers"""
#         votes = 0
#         for role in self.roles.values():
#             if await role.vote_on_proposal(proposal):
#                 votes += 1
#         return votes >= self.votes_needed

from typing import Any, Optional, Dict, List
from pydantic import BaseModel, Field
from metagpt.actions.add_requirement import UserRequirement
from metagpt.roles import Role, ProductManager, Architect, ProjectManager, Engineer, QaEngineer
from metagpt.environment import Environment
from metagpt.context import Context
from metagpt.schema import Document, Message, MESSAGE_ROUTE_TO_ALL
from metagpt.logs import logger
from metagpt.utils.common import NoMoneyException

class Flat(BaseModel):
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