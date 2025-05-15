

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Time    : 2023/5/11 14:43
@Author  : alexanderwu
@File    : engineer.py
@Modified By: mashenquan, 2023-11-1. In accordance with Chapter 2.2.1 and 2.2.2 of RFC 116:
    1. Modify the data type of the `cause_by` value in the `Message` to a string, and utilize the new message
        distribution feature for message filtering.
    2. Consolidate message reception and processing logic within `_observe`.
    3. Fix bug: Add logic for handling asynchronous message processing when messages are not ready.
    4. Supplemented the external transmission of internal messages.
@Modified By: mashenquan, 2023-11-27.
    1. According to Section 2.2.3.1 of RFC 135, replace file data in the message with the file name.
    2. According to the design in Section 2.2.3.5.5 of RFC 135, add incremental iteration functionality.
@Modified By: mashenquan, 2023-12-5. Enhance the workflow to navigate to WriteCode or QaEngineer based on the results
    of SummarizeCode.
"""

from __future__ import annotations
import asyncio
from metagpt.configs.llm_config import LLMConfig
from metagpt.provider.llm_provider_registry import create_llm_instance

import json
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Union
import re

from metagpt.actions import Action, WriteCode, WriteCodeReview, WriteTasks
from metagpt.actions.fix_bug import FixBug
from metagpt.actions.project_management_an import REFINED_TASK_LIST, TASK_LIST
from metagpt.actions.summarize_code import SummarizeCode
from metagpt.actions.write_code_plan_and_change_an import WriteCodePlanAndChange
from metagpt.const import (
    BUGFIX_FILENAME,
    CODE_PLAN_AND_CHANGE_FILE_REPO,
    REQUIREMENT_FILENAME,
    SYSTEM_DESIGN_FILE_REPO,
    TASK_FILE_REPO,
)
from metagpt.logs import logger
from metagpt.roles import Role
from metagpt.schema import (
    CodePlanAndChangeContext,
    CodeSummarizeContext,
    CodingContext,
    Document,
    Documents,
    Message,
)
from metagpt.utils.common import any_to_name, any_to_str, any_to_str_set

IS_PASS_PROMPT = """
{context}

----
Does the above log indicate anything that needs to be done?
If there are any tasks to be completed, please answer 'NO' along with the to-do list in JSON format;
otherwise, answer 'YES' in JSON format.
"""



class ExpertiseLevel:
# Define expertise levels for engineersclass ExpertiseLevel:
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    
    # Task complexity threshold for each level
    COMPLEXITY_THRESHOLDS = {
        JUNIOR: 3,  # Junior engineers can handle tasks with complexity up to 3
        MID: 7,     # Mid-level engineers can handle tasks with complexity up to 7
        SENIOR: 10  # Senior engineers can handle any task complexity
    }

# Define an engineer profile class to encapsulate engineer details
class EngineerProfile:
    def __init__(self, name: str, expertise: str = ExpertiseLevel.MID):
        self.name = name
        # Validate and set expertise level
        if expertise not in [ExpertiseLevel.JUNIOR, ExpertiseLevel.MID, ExpertiseLevel.SENIOR]:
            logger.warning(f"Unknown expertise level: {expertise}. Defaulting to {ExpertiseLevel.MID}")
            self.expertise = ExpertiseLevel.MID
        else:
            self.expertise = expertise
        
        # Add an LLM instance specific to this engineer
        self.llm = None

    def __str__(self):
        return f"{self.name} ({self.expertise})"

class Engineer(Role):
    """
    Represents an Engineer role responsible for writing and possibly reviewing code.
    Can distribute tasks among multiple engineers working in parallel, with different expertise levels.

    Attributes:
        name (str): Primary name of the engineering team lead.
        profile (str): Role profile, default is 'Engineer'.
        goal (str): Goal of the engineer.
        constraints (str): Constraints for the engineer.
        engineers (List[EngineerProfile]): List of engineer profiles to distribute tasks among.
        use_code_review (bool): Whether to use code review.
    """

    name: str = "Eng"
    profile: str = "Engineer"
    goal: str = "write elegant, readable, extensible, efficient code"
    constraints: str = (
        "the code should conform to standards like google-style and be modular and maintainable. "
        "Use same language as user requirement"
    )
    engineers: List[EngineerProfile] = []  # List of engineer profiles
    use_code_review: bool = False
    code_todos: list = []
    summarize_todos: list = []
    next_todo_action: str = ""
    n_summarize: int = 0
    n_engineers : int = 1
    paradigm: str = "hierarchy"  # Default paradigm


    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
             # Set the paradigm if provided
        if "paradigm" in kwargs:
            self.paradigm = kwargs["paradigm"]
        
        # Initialize engineers
        self._initialize_engineers(**kwargs)
        
        # Initialize LLM for each engineer
        self._initialize_engineer_llms()
            
        self.set_actions([WriteCode])
        self._watch([WriteTasks, SummarizeCode, WriteCode, WriteCodeReview, FixBug, WriteCodePlanAndChange])
        self.code_todos = []
        self.summarize_todos = []
        self.next_todo_action = any_to_name(WriteCode)
    
    def _initialize_engineers(self, **kwargs):
        """Initialize the list of engineers based on parameters, preventing duplicates."""
        # Keep track of engineer names to prevent duplicates
        engineer_names = set()
        self.engineers = []
        
        # If engineers are provided directly
        if "engineers" in kwargs and isinstance(kwargs["engineers"], list):
            for eng in kwargs["engineers"]:
                if isinstance(eng, EngineerProfile):
                    if eng.name not in engineer_names:
                        self.engineers.append(eng)
                        engineer_names.add(eng.name)
                    else:
                        logger.warning(f"Skipping duplicate engineer: {eng.name}")
                elif isinstance(eng, dict) and "name" in eng:
                    if eng["name"] not in engineer_names:
                        expertise = eng.get("expertise", ExpertiseLevel.MID)
                        self.engineers.append(EngineerProfile(eng["name"], expertise))
                        engineer_names.add(eng["name"])
                    else:
                        logger.warning(f"Skipping duplicate engineer: {eng['name']}")
                elif isinstance(eng, str):
                    # If just a name is provided, default to mid-level
                    if eng not in engineer_names:
                        self.engineers.append(EngineerProfile(eng))
                        engineer_names.add(eng)
                    else:
                        logger.warning(f"Skipping duplicate engineer: {eng}")
        
        # If engineer_names is provided
        elif "engineer_names" in kwargs and isinstance(kwargs["engineer_names"], list):
            engineer_expertises = kwargs.get("engineer_expertises", [])
            for i, name in enumerate(kwargs["engineer_names"]):
                if name not in engineer_names:
                    expertise = engineer_expertises[i] if i < len(engineer_expertises) else ExpertiseLevel.MID
                    self.engineers.append(EngineerProfile(name, expertise))
                    engineer_names.add(name)
                else:
                    logger.warning(f"Skipping duplicate engineer: {name}")
        
        # If n_engineers is provided without names
        elif "n_engineers" in kwargs and isinstance(kwargs["n_engineers"], int) and kwargs["n_engineers"] > 0:
            for i in range(kwargs["n_engineers"]):
                # Create default engineer profiles
                base_name = f"{self.name}_{i+1}" if i > 0 else self.name
                
                # Ensure unique names by appending a number if needed
                name = base_name
                counter = 1
                while name in engineer_names:
                    name = f"{base_name}_{counter}"
                    counter += 1
                
                # Distribute expertise - more senior engineers for smaller teams
                if kwargs["n_engineers"] <= 3:
                    expertise = [ExpertiseLevel.SENIOR, ExpertiseLevel.MID, ExpertiseLevel.JUNIOR][min(i, 2)]
                else:
                    # For larger teams, create a mix with more mid-level engineers
                    if i == 0:
                        expertise = ExpertiseLevel.SENIOR  # Team lead is senior
                    elif i < kwargs["n_engineers"] // 3:
                        expertise = ExpertiseLevel.SENIOR
                    elif i < kwargs["n_engineers"] * 2 // 3:
                        expertise = ExpertiseLevel.MID
                    else:
                        expertise = ExpertiseLevel.JUNIOR
                
                self.engineers.append(EngineerProfile(name, expertise))
                engineer_names.add(name)
        
        # Default case - just one engineer (the team lead)
        if not self.engineers:
            self.engineers = [EngineerProfile(self.name, ExpertiseLevel.SENIOR)]
        
        logger.info(f"Engineering team initialized with {len(self.engineers)} engineers:")
        for eng in self.engineers:
            logger.info(f"  - {eng}")

    def _initialize_engineer_llms(self):
        """Initialize a separate LLM instance for each engineer with appropriate system prompt."""
        for engineer in self.engineers:
            # Create a new LLM instance by cloning the main one
            logger.debug(f"LLM Detail : {self.config}")
            config_copy = self.config.copy()
            
            # You might want to modify the config here if needed for different engineers
            # For example, junior engineers might use gpt-3.5-turbo while senior engineers use gpt-4
            if engineer.expertise == ExpertiseLevel.JUNIOR:
                # Optionally use a different model for junior engineers
                config_copy.llm = LLMConfig(
                        api_key="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",
                        api_type="openai",
                        base_url="https://api.openai.com/v1",
                        model="gpt-4o-mini",
                        # Add other default parameters
                        temperature=0,
                        max_token=4096,
                        stream=True
        )
                
            
            elif engineer.expertise == ExpertiseLevel.MID:
                # Optionally use a different model for senior engineers
                pass
            
            # Create a new LLM instance based on the main one
            engineer.llm = create_llm_instance(config_copy.llm)
            
            # Set the cost manager to be the same as the team's
            engineer.llm.cost_manager = self.llm.cost_manager
            
            # Set a tailored system prompt for each engineer based on their expertise
            coding_style = {
                ExpertiseLevel.JUNIOR: "Focus on readable, well-commented code. Favor clarity over optimization.",
                ExpertiseLevel.MID: "Balance readability with efficiency. Use established patterns and optimize common cases.",
                ExpertiseLevel.SENIOR: "Write elegant, optimized code. Consider edge cases, performance, and maintainability."
            }
            
            engineer_prompt = (
                f"You are Engineer {engineer.name}, a {engineer.expertise}-level software developer. "
                f"Your goal is to write elegant, readable, extensible, efficient code. "
                f"{coding_style[engineer.expertise]} "
                f"The code should conform to standards like google-style and be modular and maintainable. "
                f"Use the same language as the user requirement."
            )
            
            engineer.llm.system_prompt = engineer_prompt
            logger.info(f"Initialized LLM for engineer {engineer.name} with expertise {engineer.expertise}")

    @staticmethod
    def _parse_tasks(task_msg: Document) -> list[str]:
        m = json.loads(task_msg.content)
        return m.get(TASK_LIST.key) or m.get(REFINED_TASK_LIST.key)
    
   
    def _assign_tasks_flat(self, tasks: list) -> Dict[EngineerProfile, list]:
        """
        Distribute tasks sequentially across engineers in a round-robin fashion.
        Returns a dictionary mapping engineers to their assigned tasks.
        """
        if not tasks:
            return {}
            
        # If only one engineer, they get all tasks
        if len(self.engineers) == 1:
            return {self.engineers[0]: tasks}
        
        # Initialize task assignments
        assignments = {eng: [] for eng in self.engineers}
        
        # Distribute tasks in round-robin fashion
        for i, task in enumerate(tasks):
            engineer_index = i % len(self.engineers)
            assignments[self.engineers[engineer_index]].append(task)
        
        # Log task assignments
        logger.info("Task assignments (flat paradigm):")
        for eng, eng_tasks in assignments.items():
            if eng_tasks:
                logger.info(f"  - {eng}: {eng_tasks}")
        
        return assignments
    def _assign_tasks_by_expertise(self, tasks : dict) -> Dict[EngineerProfile, list]:
        """
        Distribute tasks based on engineer expertise levels.
        Returns a dictionary mapping engineers to their assigned tasks.
        """
        if not tasks:
            return {}
            
        # If only one engineer, they get all tasks
        if len(self.engineers) == 1:
            return {self.engineers[0]: tasks}
       

        # Estimate complexity for each task
        task_complexities = []
        for task_name, task_context in tasks.items():
            complexity = self._estimate_task_complexity(task_name, task_context.i_context)
            logger.debug(f"Code Context : {task_name} , {task_context.i_context}")
            task_complexities.append((task_name, complexity))
        # Sort tasks by complexity (highest to lowest)
        task_complexities.sort(key=lambda x: x[1], reverse=True)
        logger.info(f"Task Complexity : {task_complexities}")

        
        # Group engineers by expertise level
        senior_engineers = [eng for eng in self.engineers if eng.expertise == ExpertiseLevel.SENIOR]
        mid_engineers = [eng for eng in self.engineers if eng.expertise == ExpertiseLevel.MID]
        junior_engineers = [eng for eng in self.engineers if eng.expertise == ExpertiseLevel.JUNIOR]
        
        # Ensure we have at least one engineer available at each level
        # If not, promote engineers from lower levels
        if not senior_engineers and mid_engineers:
            senior_engineers = [mid_engineers.pop(0)]
        if not mid_engineers and junior_engineers:
            mid_engineers = [junior_engineers.pop(0)]
        
        # Initialize task assignments
        assignments = {eng: [] for eng in self.engineers}
        
        # Assign tasks by complexity
        for task, complexity in task_complexities:
            if complexity > ExpertiseLevel.COMPLEXITY_THRESHOLDS[ExpertiseLevel.MID]:
                # High complexity - assign to senior engineers
                if senior_engineers:
                    # Find the senior engineer with the least tasks
                    engineer = min(senior_engineers, key=lambda e: len(assignments[e]))
                    assignments[engineer].append(task)
                    continue
            
            if complexity > ExpertiseLevel.COMPLEXITY_THRESHOLDS[ExpertiseLevel.JUNIOR]:
                # Medium complexity - try mid engineers first, then senior
                available_engineers = mid_engineers + senior_engineers
                if available_engineers:
                    engineer = min(available_engineers, key=lambda e: len(assignments[e]))
                    assignments[engineer].append(task)
                    continue
            
            # Low complexity or no appropriate engineers available - assign to anyone
            all_engineers = junior_engineers + mid_engineers + senior_engineers
            engineer = min(all_engineers, key=lambda e: len(assignments[e]))
            assignments[engineer].append(task)
        
        # Log task assignments
        logger.info("Task assignments by expertise:")
        for eng, eng_tasks in assignments.items():
            if eng_tasks:
                logger.info(f"  - {eng}: {eng_tasks}")
        
        return assignments

    def _estimate_task_complexity(self, task_filename: str, task_content) -> int:
        """
        Estimate the complexity of a task based on the filename and task content.
        
        Args:
            task_filename (str): The filename of the task
            task_content: Document object or other content with task information
            
        Returns:
            int: A complexity score from 1-10
        """
        complexity = 3  # Base complexity
        filename_base = task_filename.split('.')[0].lower()
        if filename_base in ["config", "constants", "settings"]:
            return complexity

        logger.info(f"Taskk CONTENT : {task_content}")
        # Default complexity if no content
        if task_content is None:
            return 5
            
        # Extract content as string for analysis
        content_str = ""
        
        # Handle Document objects (most common case)
        if hasattr(task_content, 'content'):
            try:
                content = task_content.content
                # logger.info(f"CONT : {content}")
                # Check if content is a JSON string that we can parse
                if isinstance(content, str) and content.strip().startswith('{'):
                    try:
                        import json
                        parsed_json = json.loads(content)
                        # logger.info(f"JSON : {parsed_json}")
                        # If this is a design doc with class diagrams, do special analysis
                        if isinstance(parsed_json, dict) and 'design_doc' in parsed_json and 'content' in parsed_json['design_doc']:
                            # Check for class diagram and sequence diagram
                            design_doc_content = json.loads(parsed_json['design_doc']['content'])
                            # Now we can access the actual fields
                            class_diagram = design_doc_content.get("Data structures and interfaces", "")
                            # class_diagram = parsed_json.get("Data structures and interfaces", "")
                            # logger.info(f"CLASS DIAGRAM : {class_diagram}")
                            sequence_diagram = parsed_json.get("Program call flow", "")
                            class_blocks = self._extract_class_blocks(class_diagram)
                            
                            
                            matching_class = None
                            for class_name, class_content in class_blocks.items():
                                # Check if class name matches filename
                                if class_name.lower() == filename_base or filename_base in class_name.lower():
                                    matching_class = class_name
                                    break
                            
                          
                            # If no matching class found, use default complexity
                            if not matching_class:
                                if "game" in filename_base:
                                    complexity += 2  # Add 2 points to complexity for main files
                                    logger.info(f"Added complexity")
                                logger.info(f"No matching class found for {task_filename}")
                                return 5
                            
                            # Get the class content
                            class_content = class_blocks[matching_class]
                            
                            # Count functions (methods with +)
                            function_count = len(re.findall(r'\+\w+\(', class_content))
                            
                            # Count variables (properties with -)
                            variable_count = len(re.findall(r'-\w+:', class_content))
                            
                            logger.info(f"File: {task_filename}, Class: {matching_class}, Functions: {function_count}, Variables: {variable_count}")
                            
                            # Calculate complexity based on function and variable counts
                            
                            # Add complexity for functions (each function adds 1 point)
                            complexity += min(4, function_count)  # Cap at +4 for functions
                            
                            # Add complexity for variables (every 2 variables add 0.5 point)
                            complexity += min(3, (variable_count // 2) * 0.5)  # Cap at +3 for variables
                            
                            # Ensure complexity is within 1-10 range
                            complexity = max(1, min(10, round(complexity)))
                            
                            return complexity
                          
                        
                        # If we couldn't do special analysis, use the string content
                    except json.JSONDecodeError:
                        content_str = str(content)
                else:
                    content_str = str(content)
            except Exception as e:
                logger.warning(f"Error parsing content: {e}")
                content_str = str(task_content)
        return complexity
 


    def _extract_class_blocks(self, class_diagram: str) -> dict:
        """
        Extract class blocks from a class diagram string.
        """
        class_blocks = {}
        if not class_diagram:
            logger.error("Empty class diagram provided")
            return class_blocks

        # Fix the escaped newlines and normalize whitespace
        class_diagram = class_diagram.encode().decode('unicode_escape')

        # Improved regex for multiline class content extraction
        class_pattern = r'class\s+(\w+)\s*\{([^}]*)\}'
        matches = re.findall(class_pattern, class_diagram, re.DOTALL)

        if not matches:
            logger.error("No matches found with regex.")
            return class_blocks

        for class_name, class_content in matches:
            class_blocks[class_name.strip()] = class_content.strip()

        logger.info(f"Extracted class blocks: {list(class_blocks.keys())}")
        return class_blocks
    
    
    async def _process_engineer_tasks(self, todos, engineer: EngineerProfile, review=False) -> Tuple[Set[str], List]:
        """Process a list of todos by a single engineer, using the engineer's dedicated LLM.
        Returns a tuple of (changed_files, coding_contexts)"""
        changed_files = set()
        coding_contexts = []  # Store all coding contexts for batch review
        
        for todo in todos:
            # Store the original LLM
            original_llm = todo.llm
            
            # Replace with the engineer's LLM
            todo.llm = engineer.llm
            
            # logger.info("Coding context : {todo.i_context}")
            
            # Run the task with the engineer's LLM
            try:
                coding_context = await todo.run()
                
                # Store the coding context for possible batch review later
                coding_contexts.append(coding_context)
                
                # Don't do individual review anymore - moved to batch process
                
                dependencies = {coding_context.design_doc.root_relative_path, coding_context.task_doc.root_relative_path}
                if self.config.inc:
                    dependencies.add(coding_context.code_plan_and_change_doc.root_relative_path)
                
                await self.project_repo.srcs.save(
                    filename=coding_context.filename,
                    dependencies=list(dependencies),
                    content=coding_context.code_doc.content,
                )
                
                # Use the engineer's name with their expertise level
                eng_role = f"{engineer.name} ({engineer.expertise})"
                msg = Message(
                    content=coding_context.model_dump_json(),
                    instruct_content=coding_context,
                    role=eng_role,
                    cause_by=WriteCode,
                )
                self.rc.memory.add(msg)
                
                changed_files.add(coding_context.code_doc.filename)
            finally:
                # Restore the original LLM
                todo.llm = original_llm
        
        return changed_files, coding_contexts
    

    def extract_and_parse_json(self, text):
        """Extract and parse JSON with better recovery mechanisms"""
        try:
            # Try to find JSON content between triple backticks
            json_pattern = r'```json\s*([\s\S]*?)\s*```'
            match = re.search(json_pattern, text, re.DOTALL)
            
            if match:
                json_str = match.group(1)
            else:
                # Try to extract anything that looks like a JSON object
                json_pattern = r'(\{\s*"review_status".*\})'
                match = re.search(json_pattern, text, re.DOTALL)
                if match:
                    json_str = match.group(1)
                else:
                    logger.warning("Could not find JSON content in the response")
                    return {"review_status": "LBTM", "overview": "Failed to parse response", "refined_files": {}}
            
            # Attempt to clean the JSON string
            # Replace invalid escape sequences
            json_str = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', json_str)
            
            # Try standard JSON parsing first
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # If that fails, use a more lenient approach: extract just the review status and overview
                status_match = re.search(r'"review_status"\s*:\s*"([^"]+)"', json_str)
                overview_match = re.search(r'"overview"\s*:\s*"([^"]+)"', json_str)
                
                result = {
                    "review_status": status_match.group(1) if status_match else "LBTM",
                    "overview": overview_match.group(1) if overview_match else "Failed to parse response",
                    "refined_files": {}  # Empty to prevent further errors
                }
                
                # Try to extract file contents individually
                files_section = re.search(r'"refined_files"\s*:\s*\{([\s\S]*?)\}(?=\s*\})', json_str)
                if files_section:
                    file_content = files_section.group(1)
                    # Parse each file entry separately
                    file_entries = re.findall(r'"([^"]+)"\s*:\s*"((?:\\.|[^"\\])*)"', file_content)
                    for filename, content in file_entries:
                        # Unescape the content
                        content = content.encode().decode('unicode_escape')
                        result["refined_files"][filename] = content
                        
                return result
                
        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            return {
                "review_status": "LBTM",
                "overview": f"Failed to process response: {str(e)}",
                "refined_files": {}
            }
        
    async def show_token_usage(self):
        """
        Display the total token usage statistics after code generation.
        Shows both the total prompt tokens and completion tokens that were used
        during the code generation process, along with total cost.
        
        Returns:
            str: A formatted string with token usage statistics
        """
        if not self.llm.cost_manager:
            logger.warning("No cost manager available to track token usage")
            return "Token usage tracking not available"
        
        # Get token usage statistics from cost manager
        costs = self.llm.cost_manager.get_costs()
        
        # Get aggregated stats across all engineers
        total_stats = self._aggregate_token_usage()
        
        # Format the output
        output = (
            "\n==== TOKEN USAGE STATISTICS ====\n"
            f"Team prompt tokens: {costs.total_prompt_tokens}\n"
            f"Team completion tokens: {costs.total_completion_tokens}\n"
            f"Team total tokens: {costs.total_prompt_tokens + costs.total_completion_tokens}\n"
            f"Team cost: ${costs.total_cost:.4f}\n"
            "\n==== AGGREGATE TOKEN USAGE ====\n"
            f"Total prompt tokens: {total_stats['prompt_tokens']}\n"
            f"Total completion tokens: {total_stats['completion_tokens']}\n"
            f"Total tokens: {total_stats['total_tokens']}\n"
            f"Total cost: ${total_stats['total_cost']:.4f}\n"
            "=================================="
        )
        
        # Also include per-engineer statistics if we have multiple engineers
        if len(self.engineers) > 1:
            output += "\n\n==== ENGINEER-SPECIFIC TOKEN USAGE ====\n"
            for engineer in self.engineers:
                if not engineer.llm or not engineer.llm.cost_manager:
                    continue
                    
                eng_costs = engineer.llm.cost_manager.get_costs()
                output += (
                    f"Engineer: {engineer.name} ({engineer.expertise})\n"
                    f"  Prompt tokens: {eng_costs.total_prompt_tokens}\n"
                    f"  Completion tokens: {eng_costs.total_completion_tokens}\n"
                    f"  Total tokens: {eng_costs.total_prompt_tokens + eng_costs.total_completion_tokens}\n"
                    f"  Cost: ${eng_costs.total_cost:.4f}\n\n"
                )
        
        logger.info(output)
        return output

    def _aggregate_token_usage(self):
        """
        Aggregates token usage from all engineers and the main LLM.
        
        Returns:
            dict: A dictionary containing aggregated token usage statistics
        """
        # Start with the team's LLM usage
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cost = 0.0
        
        # Add the main LLM's usage if available
        if self.llm and self.llm.cost_manager:
            costs = self.llm.cost_manager.get_costs()
            total_prompt_tokens += costs.total_prompt_tokens
            total_completion_tokens += costs.total_completion_tokens
            total_cost += costs.total_cost
        
        # Add each engineer's usage
        for engineer in self.engineers:
            if not engineer.llm or not engineer.llm.cost_manager:
                continue
                
            eng_costs = engineer.llm.cost_manager.get_costs()
            total_prompt_tokens += eng_costs.total_prompt_tokens
            total_completion_tokens += eng_costs.total_completion_tokens
            total_cost += eng_costs.total_cost
        
        return {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_prompt_tokens + total_completion_tokens,
            "total_cost": total_cost
        }

 
    
    async def _integrating_codebase(self, all_coding_contexts: List) -> Set[str]:
        """
        Refines all code files as a single codebase with multiple iterations if needed.
        Splits the input into smaller batches to stay within token limits.
        """
        changed_files = set()

        if not all_coding_contexts:
            return changed_files

        logger.info(f"Starting direct refinement of {len(all_coding_contexts)} files")

        # Get the number of review iterations to perform
        k = max(2, self.context.config.code_review_k_times or 0)
        logger.info(f"Will perform up to {k} iterations of code refinement (minimum 2 enforced).")

        # Step 1: Gather all code files
        code_files = {}  # Dictionary of filename -> content
        ctx_by_filename = {}  # Dictionary to map filename to context object

        for ctx in all_coding_contexts:
            code_files[ctx.filename] = ctx.code_doc.content
            ctx_by_filename[ctx.filename] = ctx

        # Split files into two batches for processing
        filenames = list(code_files.keys())
        midpoint = len(filenames) // 2
        batch1_filenames = filenames[:midpoint]
        batch2_filenames = filenames[midpoint:]
        
        logger.info(f"Split files into two batches: {len(batch1_filenames)} and {len(batch2_filenames)} files")

        # Initial code state
        current_code_files = dict(code_files)

        # Perform up to k iterations
        for iteration in range(k):
            logger.info(f"Starting refinement iteration {iteration + 1}/{k}")
            
            # Base refinement prompt - same for both batches
            refinement_prompt = """
            You are an experienced software engineer tasked with improving a complete codebase to ensure it's consistent, correct, well-integrated, and free of common errors.

            Review the file(s) provided below and refine them based on these criteria:
            1.  Missing imports: Ensure every file imports all classes, functions, constants, and types it uses from other files.
            2.  Import correctness: Fix import paths and module names according to the project structure.
            3.  Interface consistency: Make sure function/method parameters (including types) and return values match between definition and usage.
            4.  Constant usage: Ensure constants are defined centrally (if appropriate) and imported correctly elsewhere.
            5.  Class inheritance & Interfaces: Check for proper inheritance chains and abstract method implementations.
            6.  Naming consistency: Use consistent naming conventions across all files.
            7.  Syntax correctness: Ensure the code is free from syntax errors that would prevent execution.
            8.  Variable/Attribute Definition: Ensure all variables and class attributes are defined before use.
            9.  Basic Bug Prevention: Identify and fix common errors like potential null references or incorrect logic.

            For each file you modify, provide the COMPLETE refined code, not just the changes.

            Return your response strictly in this JSON format:
            {
            "review_status": "LGTM" or "LBTM", // LBTM = Looks Bad To Me, LGTM = Looks Good To Me
            "overview": "Brief explanation of improvements made or issues remaining.",
            "refined_files": {
                "filename1": "COMPLETE refined code for this file",
                "filename2": "COMPLETE refined code for this file",
                ... // Include ALL files provided in the input
            }
            }

            Important: Include the ENTIRE content of **every** file in `refined_files`, even if you made no changes to it.
            If the code looks good and requires no changes according to the criteria, set `review_status` to "LGTM" and include the original, unmodified code in `refined_files`.
            Focus on correctness and integration.
            """
            
            # Process batch 1
            batch1_files = {filename: current_code_files[filename] for filename in batch1_filenames}
            batch1_input = {
                "files": batch1_files,
                "instructions": "Refine these files based on the criteria provided."
            }
            batch1_json = json.dumps(batch1_input, indent=2)
            
            # Process batch 2
            batch2_files = {filename: current_code_files[filename] for filename in batch2_filenames}
            batch2_input = {
                "files": batch2_files,
                "instructions": "Refine these files based on the criteria provided."
            }
            batch2_json = json.dumps(batch2_input, indent=2)
            
            # Run refinement for both batches
            batch_results = []
            
            for batch_num, batch_json in enumerate([batch1_json, batch2_json], 1):
                if batch_num == 1 and not batch1_filenames:
                    continue
                if batch_num == 2 and not batch2_filenames:
                    continue
                    
                logger.info(f"Processing batch {batch_num} with {len(batch1_filenames if batch_num == 1 else batch2_filenames)} files")
                
                # Send the request to the LLM
                refinement_result = await self.llm.aask(
                    refinement_prompt + f"\n\nBatch {batch_num} files to refine:\n" + batch_json, 
                    stream=False
                )
                
                try:
                    # Parse the results
                    refined_data = self.extract_and_parse_json(refinement_result)
                    review_status = refined_data.get("review_status", "LBTM").upper()
                    logger.info(f"Batch {batch_num}, Iteration {iteration + 1} overview: {refined_data.get('overview')}")
                    logger.info(f"Review status: {review_status}")
                    
                    # Extract refined files
                    refined_files_data = refined_data.get("refined_files", {})
                    if not isinstance(refined_files_data, dict):
                        logger.error(f"Invalid format for 'refined_files' in batch {batch_num}. Expected a dict.")
                        continue
                        
                    # Add to batch results for later processing
                    batch_results.append((review_status, refined_files_data))
                    
                except Exception as e:
                    logger.error(f"Failed to process batch {batch_num}: {e}")
                    logger.error(f"Raw LLM Response (first 500 chars): {refinement_result[:500]}...")
            
            # Combine results from both batches
            iteration_changes = False
            all_lgtm = True
            
            for review_status, refined_files_data in batch_results:
                # Update files with refined content
                for filename, refined_content in refined_files_data.items():
                    if filename not in ctx_by_filename:
                        logger.warning(f"Refinement includes unknown file: {filename}. Skipping.")
                        continue
                        
                    # Ensure content is a string
                    if not isinstance(refined_content, str):
                        logger.warning(f"Refined content for {filename} is not a string. Skipping update.")
                        continue
                        
                    current_content = current_code_files.get(filename)
                    
                    # Only update if content actually changed
                    if refined_content != current_content:
                        logger.debug(f"Code change detected in {filename} during iteration {iteration + 1}.")
                        current_code_files[filename] = refined_content
                        iteration_changes = True
                        
                # Track if all batches returned LGTM
                if review_status != "LGTM":
                    all_lgtm = False
            
            # Check if we should continue
            if all_lgtm:
                logger.info(f"Stopping refinement after iteration {iteration + 1} as all batches returned LGTM.")
                break
                
            if not iteration_changes:
                logger.info(f"Stopping refinement after iteration {iteration + 1} as no code changes were detected.")
                break
                
            if iteration == k - 1:
                logger.info(f"Reached maximum iterations ({k}). Applying final changes.")
        
        # Apply the final changes to the actual files
        logger.info("Applying final refinement changes to project repository.")
        for filename, final_content in current_code_files.items():
            if filename not in ctx_by_filename:
                continue
                
            original_ctx = ctx_by_filename[filename]
            original_content_before_refinement = code_files.get(filename)
            
            # Only save if content actually changed from the initial state
            if final_content != original_content_before_refinement:
                logger.info(f"Saving refined changes for {filename}.")
                
                # Create updated document
                updated_code_doc = Document(
                    root_path=original_ctx.code_doc.root_path,
                    filename=original_ctx.filename,
                    content=final_content
                )
                
                # Update context with new document
                original_ctx.code_doc = updated_code_doc
                
                # Save the updated file
                dependencies = set()
                if hasattr(original_ctx, 'design_doc') and original_ctx.design_doc:
                    dependencies.add(original_ctx.design_doc.root_relative_path)
                if hasattr(original_ctx, 'task_doc') and original_ctx.task_doc:
                    dependencies.add(original_ctx.task_doc.root_relative_path)
                if self.config.inc and hasattr(original_ctx, 'code_plan_and_change_doc') and original_ctx.code_plan_and_change_doc:
                    dependencies.add(original_ctx.code_plan_and_change_doc.root_relative_path)
                    
                await self.project_repo.srcs.save(
                    filename=original_ctx.filename,
                    dependencies=list(dependencies),
                    content=final_content,
                )
                
                # Record the refinement action in memory
                msg = Message(
                    content=original_ctx.model_dump_json(),
                    instruct_content=original_ctx,
                    role=self.profile,
                    cause_by=WriteCodeReview,
                )
                self.rc.memory.add(msg)
                
                changed_files.add(filename)
            else:
                logger.info(f"No net changes detected for {filename} after refinement loop. File not re-saved.")
                
        return changed_files
    # This manages the engineers to write the code
    async def _act_sp_with_cr(self, review=False) -> Set[str]:
        changed_files = set()
        all_coding_contexts = []  # Collect all coding contexts for batch review
        
        if not self.code_todos:
            logger.info("No code todos to process.")
            return changed_files
        
        # If only one engineer or one task, process sequentially
        if len(self.engineers) <= 1 or len(self.code_todos) <= 1:
            engineer = self.engineers[0]
            for todo in self.code_todos:
                # Use the engineer's LLM
                original_llm = todo.llm
                todo.llm = engineer.llm
                
                try:
                    # Run the task with the engineer's LLM
                    coding_context = await todo.run()
                    all_coding_contexts.append(coding_context)
                    
                    dependencies = {coding_context.design_doc.root_relative_path, coding_context.task_doc.root_relative_path}
                    if self.config.inc:
                        dependencies.add(coding_context.code_plan_and_change_doc.root_relative_path)
                    await self.project_repo.srcs.save(
                        filename=coding_context.filename,
                        dependencies=list(dependencies),
                        content=coding_context.code_doc.content,
                    )
                    msg = Message(
                        content=coding_context.model_dump_json(),
                        instruct_content=coding_context,
                        role=f"{engineer.name} ({engineer.expertise})",
                        cause_by=WriteCode,
                    )
                    self.rc.memory.add(msg)
                    changed_files.add(coding_context.code_doc.filename)
                finally:
                    # Restore the original LLM
                    todo.llm = original_llm
        else:
           
            # Get a list of all task filenames
            task_filenames = [todo.i_context.filename for todo in self.code_todos]
            
            # Create a mapping from task filename to todo object
            todo_map = {todo.i_context.filename: todo for todo in self.code_todos}
            
            # Assign tasks based on selected paradigm
            if self.paradigm.lower() == "flat":
                logger.info(f"Assigned task : Flat")
                todo_assignments = self._assign_tasks_flat(task_filenames)
            else:  # Default to hierarchy paradigm
                todo_assignments = self._assign_tasks_by_expertise(todo_map)            
            
            # Create a list of tasks for each engineer
            engineer_tasks = []
            for engineer, assigned_tasks in todo_assignments.items():
                if not assigned_tasks:
                    continue
                
                engineer_todos = []

                # Process each task separately instead of bundling them
                for index, task in enumerate(assigned_tasks):
                    todo_obj = todo_map[task]
                    parsed_json = json.loads(todo_obj.i_context.content)
                    filename = todo_obj.i_context.filename.split('.')[0].capitalize().replace('_','')

                    
                    
                    if index ==0 and engineer.expertise == ExpertiseLevel.JUNIOR:
                        if 'design_doc' in parsed_json and parsed_json['design_doc']:
                             parsed_json = self.filter_class_for_junior(parsed_json, filename)
                             logger.info(f"Manage Access : {parsed_json}")
                            
                            
                    if index >0:
                        parsed_json = json.loads(todo_obj.i_context.content)
                        logger.info(f"Before : { parsed_json}")

                        # Empty the design_doc
                        if 'design_doc' in parsed_json and parsed_json['design_doc']:
                            # Keep the existing document structure but set content to empty
                            parsed_json['design_doc']['content'] = "{}"  # Empty JSON object as a string
                        
                        if 'task_doc' in parsed_json and parsed_json['task_doc']:
                            # Keep the existing document structure but set content to empty
                            parsed_json['task_doc']['content'] = "{}"  # Empty JSON object as a string
                                    # json.loads(parsed_json['design_doc']['content'])
                        
                        # Update the content with modified JSON
                    todo_obj.i_context.content = json.dumps(parsed_json)
                    logger.info(f"Updated : { todo_obj.i_context.content}")
                        
                        
                    
                    engineer_todos.append(todo_obj)
                    
                    
                engineer_tasks.append(self._process_engineer_tasks(engineer_todos, engineer, False))  # Never review individual tasks

                
                # # Convert task filenames back to todo objects
                # engineer_todos = [todo_map[task] for task in assigned_tasks]
                # engineer_tasks.append(self._process_engineer_tasks(engineer_todos, engineer, False))  # Never review individual tasks
            
            # Wait for all engineers to complete their tasks
            results = await asyncio.gather(*engineer_tasks)
            
            # Collect all changed files and coding contexts
            for changed, contexts in results:
                changed_files.update(changed)
                all_coding_contexts.extend(contexts)
        
        # After all engineers have completed their work, perform batch code review if enabled
        if review and all_coding_contexts:
            logger.info(f"All coding tasks completed. Starting direct code refinement...")
            # Use the direct refinement method instead of review
            refinement_changed_files = await self._integrating_codebase(all_coding_contexts)
            changed_files.update(refinement_changed_files)
        
        if not changed_files:
            logger.info("Nothing has changed.")
        return changed_files
    
    def filter_class_for_junior(self, parsed_json, class_name="Main"):
        if 'design_doc' in parsed_json and parsed_json['design_doc']:
            # Parse the content string as JSON
            design_content = json.loads(parsed_json['design_doc']['content'])
            
            # Check if Data structures and interfaces exists
            if 'Data structures and interfaces' in design_content:
                class_diagram = design_content['Data structures and interfaces']
                
                # Extract only the specified class part using regex with the class name as a variable
             
                class_pattern = r'class ' + re.escape(class_name) + r' \{[^}]+\}'
                class_match = re.search(class_pattern, class_diagram)
                
                if class_match:
                    class_content = class_match.group(0)
                    
                    # Create a simplified class diagram with only the specified class
                    simplified_diagram = "\nclassDiagram\n " + class_content + "\n"
                    
                    # Update the content with only the specified class
                    design_content['Data structures and interfaces'] = simplified_diagram
                    
                    # Update the parsed_json with the modified content
                    parsed_json['design_doc']['content'] = json.dumps(design_content)
        
        return parsed_json

    async def _act(self) -> Message | None:
        """Determines the mode of action based on whether code review is used."""
        if not self.src_workspace:
            self.src_workspace = self.git_repo.workdir / self.git_repo.workdir.name
        if self.rc.todo is None:
            return None
        if isinstance(self.rc.todo, WriteCodePlanAndChange):
            self.next_todo_action = any_to_name(WriteCode)
            return await self._act_code_plan_and_change()
        if isinstance(self.rc.todo, WriteCode):
            self.next_todo_action = any_to_name(SummarizeCode)
            logger.debug(f"CODE REVIEW : {self.use_code_review}")
            return await self._act_write_code()
        if isinstance(self.rc.todo, SummarizeCode):
            self.next_todo_action = any_to_name(WriteCode)
            return await self._act_summarize()
        return None

    
    async def _act_write_code(self):
        perform_review = self.paradigm.lower() != "flat"

        changed_files = await self._act_sp_with_cr(review=perform_review)
        usage_stats = await self.show_token_usage()
        return Message(
            content="\n".join(changed_files),
            role=self.profile,
            cause_by=WriteCodeReview if self.use_code_review else WriteCode,
            send_to=self,
            sent_from=self,
        )

    async def _act_summarize(self):
        tasks = []
        for todo in self.summarize_todos:
            summary = await todo.run()
            summary_filename = Path(todo.i_context.design_filename).with_suffix(".md").name
            dependencies = {todo.i_context.design_filename, todo.i_context.task_filename}
            for filename in todo.i_context.codes_filenames:
                rpath = self.project_repo.src_relative_path / filename
                dependencies.add(str(rpath))
            await self.project_repo.resources.code_summary.save(
                filename=summary_filename, content=summary, dependencies=dependencies
            )
            is_pass, reason = await self._is_pass(summary)
            if not is_pass:
                todo.i_context.reason = reason
                tasks.append(todo.i_context.model_dump())

                await self.project_repo.docs.code_summary.save(
                    filename=Path(todo.i_context.design_filename).name,
                    content=todo.i_context.model_dump_json(),
                    dependencies=dependencies,
                )
            else:
                await self.project_repo.docs.code_summary.delete(filename=Path(todo.i_context.design_filename).name)

        logger.info(f"--max-auto-summarize-code={self.config.max_auto_summarize_code}")
        if not tasks or self.config.max_auto_summarize_code == 0:
            return Message(
                content="",
                role=self.profile,
                cause_by=SummarizeCode,
                sent_from=self,
                send_to="Edward",  # The name of QaEngineer
            )
        # The maximum number of times the 'SummarizeCode' action is automatically invoked, with -1 indicating unlimited.
        # This parameter is used for debugging the workflow.
        self.n_summarize += 1 if self.config.max_auto_summarize_code > self.n_summarize else 0
        return Message(
            content=json.dumps(tasks), role=self.profile, cause_by=SummarizeCode, send_to=self, sent_from=self
        )

    async def _act_code_plan_and_change(self):
        """Write code plan and change that guides subsequent WriteCode and WriteCodeReview"""
        node = await self.rc.todo.run()
        code_plan_and_change = node.instruct_content.model_dump_json()
        dependencies = {
            REQUIREMENT_FILENAME,
            str(self.project_repo.docs.prd.root_path / self.rc.todo.i_context.prd_filename),
            str(self.project_repo.docs.system_design.root_path / self.rc.todo.i_context.design_filename),
            str(self.project_repo.docs.task.root_path / self.rc.todo.i_context.task_filename),
        }
        code_plan_and_change_filepath = Path(self.rc.todo.i_context.design_filename)
        await self.project_repo.docs.code_plan_and_change.save(
            filename=code_plan_and_change_filepath.name, content=code_plan_and_change, dependencies=dependencies
        )
        await self.project_repo.resources.code_plan_and_change.save(
            filename=code_plan_and_change_filepath.with_suffix(".md").name,
            content=node.content,
            dependencies=dependencies,
        )

        return Message(
            content=code_plan_and_change,
            role=self.profile,
            cause_by=WriteCodePlanAndChange,
            send_to=self,
            sent_from=self,
        )

    async def _is_pass(self, summary) -> (str, str):
        rsp = await self.llm.aask(msg=IS_PASS_PROMPT.format(context=summary), stream=False)
        logger.info(rsp)
        if "YES" in rsp:
            return True, rsp
        return False, rsp

    async def _think(self) -> Action | None:
        
        if not self.src_workspace:
            self.src_workspace = self.git_repo.workdir / self.git_repo.workdir.name
        write_plan_and_change_filters = any_to_str_set([WriteTasks, FixBug])
        write_code_filters = any_to_str_set([WriteTasks, WriteCodePlanAndChange, SummarizeCode])
        summarize_code_filters = any_to_str_set([WriteCode, WriteCodeReview])
        if not self.rc.news:
            return None
        msg = self.rc.news[0]
        if self.config.inc and msg.cause_by in write_plan_and_change_filters:
            logger.debug(f"TODO WriteCodePlanAndChange:{msg.model_dump_json()}")
            await self._new_code_plan_and_change_action(cause_by=msg.cause_by)
            return self.rc.todo
        if msg.cause_by in write_code_filters:
            await self._new_code_actions()
            logger.debug(f"TASK : {self.rc.todo}")
            return self.rc.todo
        if msg.cause_by in summarize_code_filters and msg.sent_from == any_to_str(self):
            logger.debug(f"TODO SummarizeCode:{msg.model_dump_json()}")
            await self._new_summarize_actions()
            return self.rc.todo
        return None

    async def _new_coding_context(self, filename, dependency) -> CodingContext:
        old_code_doc = await self.project_repo.srcs.get(filename)
        if not old_code_doc:
            old_code_doc = Document(root_path=str(self.project_repo.src_relative_path), filename=filename, content="")
        dependencies = {Path(i) for i in await dependency.get(old_code_doc.root_relative_path)}
        task_doc = None
        design_doc = None
        code_plan_and_change_doc = await self._get_any_code_plan_and_change() if await self._is_fixbug() else None
        for i in dependencies:
            if str(i.parent.as_posix()) == TASK_FILE_REPO:
                task_doc = await self.project_repo.docs.task.get(i.name)
            elif str(i.parent.as_posix()) == SYSTEM_DESIGN_FILE_REPO:
                design_doc = await self.project_repo.docs.system_design.get(i.name)
            elif str(i.parent.as_posix()) == CODE_PLAN_AND_CHANGE_FILE_REPO:
                code_plan_and_change_doc = await self.project_repo.docs.code_plan_and_change.get(i.name)
        if not task_doc or not design_doc:
            logger.error(f'Detected source code "{filename}" from an unknown origin.')
            raise ValueError(f'Detected source code "{filename}" from an unknown origin.')
        context = CodingContext(
            filename=filename,
            design_doc=design_doc,
            task_doc=task_doc,
            code_doc=old_code_doc,
            code_plan_and_change_doc=code_plan_and_change_doc,
        )
        return context

    async def _new_coding_doc(self, filename, dependency):
        context = await self._new_coding_context(filename, dependency)
        coding_doc = Document(
            root_path=str(self.project_repo.src_relative_path), filename=filename, content=context.model_dump_json()
        )
        return coding_doc

    async def _new_code_actions(self):
        bug_fix = await self._is_fixbug()
        # Prepare file repos
        changed_src_files = self.project_repo.srcs.all_files if bug_fix else self.project_repo.srcs.changed_files
        changed_task_files = self.project_repo.docs.task.changed_files
        changed_files = Documents()
        # Recode caused by upstream changes.
        for filename in changed_task_files:
            design_doc = await self.project_repo.docs.system_design.get(filename)
            task_doc = await self.project_repo.docs.task.get(filename)
            code_plan_and_change_doc = await self.project_repo.docs.code_plan_and_change.get(filename)
            task_list = self._parse_tasks(task_doc)
            logger.info(f"Processing task file: {filename}")
            logger.debug(f"Task list: {task_list}")
            for task_filename in task_list:
                old_code_doc = await self.project_repo.srcs.get(task_filename)
                if not old_code_doc:
                    old_code_doc = Document(
                        root_path=str(self.project_repo.src_relative_path), filename=task_filename, content=""
                    )
                if not code_plan_and_change_doc:
                    context = CodingContext(
                        filename=task_filename, design_doc=design_doc, task_doc=task_doc, code_doc=old_code_doc
                    )
                else:
                    context = CodingContext(
                        filename=task_filename,
                        design_doc=design_doc,
                        task_doc=task_doc,
                        code_doc=old_code_doc,
                        code_plan_and_change_doc=code_plan_and_change_doc,
                    )
                coding_doc = Document(
                    root_path=str(self.project_repo.src_relative_path),
                    filename=task_filename,
                    content=context.model_dump_json(),
                )
                if task_filename in changed_files.docs:
                    logger.warning(
                        f"Potential conflict detected for file: {task_filename}"
                    )
                changed_files.docs[task_filename] = coding_doc
        self.code_todos = [
            WriteCode(i_context=i, context=self.context, llm=self.llm) for i in changed_files.docs.values()
        ]
        # Code directly modified by the user.
        dependency = await self.git_repo.get_dependency()
        for filename in changed_src_files:
            if filename in changed_files.docs:
                continue
            coding_doc = await self._new_coding_doc(filename=filename, dependency=dependency)
            changed_files.docs[filename] = coding_doc
            self.code_todos.append(WriteCode(i_context=coding_doc, context=self.context, llm=self.llm))

        if self.code_todos:
            self.set_todo(self.code_todos[0])

    async def _new_summarize_actions(self):
        src_files = self.project_repo.srcs.all_files
        # Generate a SummarizeCode action for each pair of (system_design_doc, task_doc).
        summarizations = defaultdict(list)
        for filename in src_files:
            dependencies = await self.project_repo.srcs.get_dependency(filename=filename)
            ctx = CodeSummarizeContext.loads(filenames=list(dependencies))
            summarizations[ctx].append(filename)
        for ctx, filenames in summarizations.items():
            ctx.codes_filenames = filenames
            new_summarize = SummarizeCode(i_context=ctx, context=self.context, llm=self.llm)
            for i, act in enumerate(self.summarize_todos):
                if act.i_context.task_filename == new_summarize.i_context.task_filename:
                    self.summarize_todos[i] = new_summarize
                    new_summarize = None
                    break
            if new_summarize:
                self.summarize_todos.append(new_summarize)
        if self.summarize_todos:
            self.set_todo(self.summarize_todos[0])
            self.summarize_todos.pop(0)


    async def _new_code_plan_and_change_action(self, cause_by: str):
        """Create a WriteCodePlanAndChange action for subsequent to-do actions."""
        files = self.project_repo.all_files
        options = {}
        if cause_by != any_to_str(FixBug):
            requirement_doc = await self.project_repo.docs.get(REQUIREMENT_FILENAME)
            options["requirement"] = requirement_doc.content
        else:
            fixbug_doc = await self.project_repo.docs.get(BUGFIX_FILENAME)
            options["issue"] = fixbug_doc.content
        code_plan_and_change_ctx = CodePlanAndChangeContext.loads(files, **options)
        self.rc.todo = WriteCodePlanAndChange(i_context=code_plan_and_change_ctx, context=self.context, llm=self.llm)

    @property
    def action_description(self) -> str:
        """AgentStore uses this attribute to display to the user what actions the current role should take."""
        return self.next_todo_action

    async def _is_fixbug(self) -> bool:
        fixbug_doc = await self.project_repo.docs.get(BUGFIX_FILENAME)
        return bool(fixbug_doc and fixbug_doc.content)

    async def _get_any_code_plan_and_change(self) -> Optional[Document]:
        changed_files = self.project_repo.docs.code_plan_and_change.changed_files
        for filename in changed_files.keys():
            doc = await self.project_repo.docs.code_plan_and_change.get(filename)
            if doc and doc.content:
                return doc
        return None