"""SkillAudit: a layered, plug-in auditor for copied AI agent skills.

Layers (dependencies only point downward):

    reporting.py  ->  writes CSV results, the run manifest and charts
    checks/       ->  plug-ins implementing the Check interface
    parsing.py    ->  turns rows into Skill objects and a Corpus
    data.py       ->  reads the official GitSkills SQLite file
"""

__version__ = "0.1.0"
