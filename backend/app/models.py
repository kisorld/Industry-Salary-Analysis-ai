from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    keyword: str = Field(default="数据分析师")
    city: str = Field(default="北京")
    use_ai: bool = Field(default=True)


class ScrapeRequest(BaseModel):
    url: str = ""
    urls: list[str] = Field(default_factory=list)
    limit: int = 20
    use_ai: bool = True
    mode: str = Field(default="auto", pattern="^(auto|static|dynamic)$")


class AgentRequest(BaseModel):
    goal: str = Field(default="分析目标岗位的行业薪酬水平")
    url: str = ""
    urls: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    industry: str = ""
    cities: list[str] = Field(default_factory=list)
    job_keywords: list[str] = Field(default_factory=list)
    experience: str = ""
    education: str = ""
    start_date: str = ""
    end_date: str = ""
    limit: int = 40
    pages: int = 20
    use_ai: bool = True
    use_sample: bool = True
    mode: str = Field(default="auto", pattern="^(auto|static|dynamic)$")


class ReportRequest(BaseModel):
    use_ai: bool = True
    title: str = "行业薪酬洞察报告"
