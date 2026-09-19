from enum import Enum

from pydantic import AliasChoices, BaseModel, Field


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewSchema(BaseModel):
    file_path: str
    line_number: int
    title: str
    description: str
    severity: Severity
    suggestion: str | None = Field(
        default=None, description="Suggestion for the review"
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="Confidence score of the review (0.0 to 1.0)"
    )


class AgentReviewResult(BaseModel):
    summary: str = Field(
        default="Review completed.",
        description="High-level summary of the review",
    )
    findings: list[ReviewSchema] = Field(
        default_factory=list,
        validation_alias=AliasChoices("findings", "finding", "vulnerabilities", "issues"),
        description="List of review findings",
    )

    @property
    def finding(self) -> list[ReviewSchema]:
        """Backward-compatibility alias for single finding access."""
        return self.findings