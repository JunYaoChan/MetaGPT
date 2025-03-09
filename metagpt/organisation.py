#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
from pathlib import Path

# import agentops
import typer

from metagpt.logs import logger
from metagpt.const import CONFIG_ROOT
import flat
import federation
import holarchy
from metagpt.utils.project_repo import ProjectRepo

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)


def generate_repo(
    idea,
    paradigm,
    investment=3.0,
    n_round=7,
    code_review=True,
    run_tests=False,
    implement=True,
    project_name="",
    inc=False,
    project_path="",
    reqa_file="",
    max_auto_summarize_code=0,
    recover_path=None,
) -> ProjectRepo:
    """Run the startup logic. Can be called from CLI or other Python scripts."""
    from metagpt.config2 import config
    from metagpt.context import Context
    from metagpt.roles import (
        Architect,
        Engineer,
        ProductManager,
        ProjectManager,
        QaEngineer,
    )
    from metagpt.team import Team
   
    # if config.agentops_api_key != "":
    #     agentops.init(config.agentops_api_key, tags=["software_company"])

    config.update_via_cli(project_path, project_name, inc, reqa_file, max_auto_summarize_code)
    ctx = Context(config=config)
    if paradigm =="Team" :
        if not recover_path:
            company = Team(context=ctx)
            company.hire(
                [
                    ProductManager(),
                    Architect(),
                    ProjectManager(),
                ]
            )

            if implement or code_review:
                company.hire([Engineer(n_borg=5, use_code_review=code_review), Engineer(n_borg=5, use_code_review=code_review, name = "John"), Engineer(n_borg=5, use_code_review=code_review, name = "Roger")])

            if run_tests:
                company.hire([QaEngineer()])
                if n_round < 8:
                    n_round = 8  # If `--run-tests` is enabled, at least 8 rounds are required to run all QA actions.
        else:
            stg_path = Path(recover_path)
            if not stg_path.exists() or not str(stg_path).endswith("team"):
                raise FileNotFoundError(f"{recover_path} not exists or not endswith `team`")

            company = Team.deserialize(stg_path=stg_path, context=ctx)
            idea = company.idea

        company.invest(investment)
        company.run_project(idea)
        asyncio.run(company.run(n_round=n_round))

        # if config.agentops_api_key != "":
        #     agentops.end_session("Success")
    elif(paradigm == "Flat"):
        print("hello")
        flat_org = flat.Flat(context=ctx)
        flat_org.hire(roles=[
            ProductManager(),
            Architect(),
            ProjectManager(),
            Engineer(name="eng1"),
            Engineer(name="eng2"),
            QaEngineer()
        ])
        flat_org.invest(investment)
        flat_org.run_project(idea)
        asyncio.run(flat_org.run(n_round=n_round))
        
    elif(paradigm == "Holarchy"):
        print("hello")
        # Holarchy
        hol = holarchy.Holarchy(context=ctx)
        # Create nested structure
        pm_node = hol.create_holon(ProductManager())
        arch_node = hol.create_holon(Architect(), "ProductManager")
        eng_node = hol.create_holon(Engineer(name="eng1"), "Architect")
        qa_node = hol.create_holon(QaEngineer(), "Architect")
        hol.invest(investment)
        hol.run_project(idea)
        asyncio.run(hol.run(n_round=n_round))
        
    elif(paradigm == "Hierarchy"):
        print("hello")
        flat_org = flat.Flat(context=ctx)
        flat_org.hire(roles=[
            ProductManager(),
            Architect(),
            ProjectManager(),
            Engineer(name="eng1"),
            Engineer(name="eng2"),
            QaEngineer()
        ])
        flat_org.invest(investment)
        flat_org.run_project(idea)
        asyncio.run(flat_org.run(n_round=n_round))
        
    elif(paradigm == "Federation"):
        print("hello")
        # Federation
        fed = federation.Federation(context=ctx)
        # Create development team
        fed.create_team(
            "dev_team",
            [Engineer(name="dev1"), Engineer(name="dev2")],
            ProjectManager()
        )
        # Create architecture team
        fed.create_team(
            "arch_team",
            [Engineer(name="arch1"), Engineer(name="arch2")],
            Architect()
)
        fed.invest(investment)
        fed.run_project(idea)
        asyncio.run(fed.run(n_round=n_round))

    

    return ctx.repo


@app.command("", help="Start a new project.")
#pass the arugments using the startup function
def startup(
    idea: str = typer.Argument(None, help="Your innovative idea, such as 'Create a 2048 game.'"),
    paradigm: str = typer.Argument("Team", help="Team, Flat, Hierarchy, Holarchy, Federation" ),
    investment: float = typer.Option(default=3.0, help="Dollar amount to invest in the AI company."),
    n_round: int = typer.Option(default=7, help="Number of rounds for the simulation."),
    code_review: bool = typer.Option(default=True, help="Whether to use code review."),
    run_tests: bool = typer.Option(default=False, help="Whether to enable QA for adding & running tests."),
    implement: bool = typer.Option(default=True, help="Enable or disable code implementation."),
    project_name: str = typer.Option(default="", help="Unique project name, such as 'game_2048'."),
    inc: bool = typer.Option(default=False, help="Incremental mode. Use it to coop with existing repo."),
    project_path: str = typer.Option(
        default="",
        help="Specify the directory path of the old version project to fulfill the incremental requirements.",
    ),
    reqa_file: str = typer.Option(
        default="", help="Specify the source file name for rewriting the quality assurance code."
    ),
    max_auto_summarize_code: int = typer.Option(
        default=0,
        help="The maximum number of times the 'SummarizeCode' action is automatically invoked, with -1 indicating "
        "unlimited. This parameter is used for debugging the workflow.",
    ),
    recover_path: str = typer.Option(default=None, help="recover the project from existing serialized storage"),
    init_config: bool = typer.Option(default=False, help="Initialize the configuration file for MetaGPT."),
):
    """Run a startup. Be a boss."""
    if init_config:
        copy_config_to()
        return

    if idea is None:
        typer.echo("Missing argument 'IDEA'. Run 'metagpt --help' for more information.")
        raise typer.Exit()

    return generate_repo(
        idea,
        paradigm,
        investment,
        n_round,
        code_review,
        run_tests,
        implement,
        project_name,
        inc,
        project_path,
        reqa_file,
        max_auto_summarize_code,
        recover_path,
    )


DEFAULT_CONFIG = """# Full Example: https://github.com/geekan/MetaGPT/blob/main/config/config2.example.yaml
# Reflected Code: https://github.com/geekan/MetaGPT/blob/main/metagpt/config2.py
# Config Docs: https://docs.deepwisdom.ai/main/en/guide/get_started/configuration.html
llm:
  api_type: "openai"  # or azure / ollama / groq etc.
  model: "gpt-4-turbo"  # or gpt-3.5-turbo
  base_url: "https://api.openai.com/v1"  # or forward url / other llm url
  api_key: "YOUR_API_KEY"
"""


def copy_config_to():
    """Initialize the configuration file for MetaGPT."""
    target_path = CONFIG_ROOT / "config2.yaml"

    # 创建目标目录（如果不存在）
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # 如果目标文件已经存在，则重命名为 .bak
    if target_path.exists():
        backup_path = target_path.with_suffix(".bak")
        target_path.rename(backup_path)
        print(f"Existing configuration file backed up at {backup_path}")

    # 复制文件
    target_path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    print(f"Configuration file initialized at {target_path}")


if __name__ == "__main__":
    logger.info("Starting application [software_company.py]")
    print("Starting application [software_company.py]")
    app()
