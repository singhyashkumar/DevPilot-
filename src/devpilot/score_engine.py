"""Final score, grade, top issues, and roadmap generator."""

from __future__ import annotations

from devpilot.models import (
    CodeQualityResult,
    DependencyResult,
    ReadmeResult,
    ScoreBreakdown,
    SecurityResult,
    StructureResult,
    TestingResult,
)


class ScoreEngine:
    """Combine analyzer scores into one professional repository score."""

    WEIGHTS = {
        "code_quality": 0.25,
        "documentation": 0.20,
        "testing": 0.15,
        "security": 0.20,
        "dependencies": 0.10,
        "structure": 0.10,
    }

    def calculate(
        self,
        *,
        structure: StructureResult,
        code_quality: CodeQualityResult,
        readme: ReadmeResult,
        dependencies: DependencyResult,
        testing: TestingResult,
        security: SecurityResult,
    ) -> ScoreBreakdown:
        """Calculate an overall score and omit unavailable Python-only signals fairly."""
        component_scores: dict[str, int] = {
            "documentation": readme.score,
            "testing": testing.score,
            "security": security.score,
            "dependencies": dependencies.score,
            "structure": structure.score,
        }
        if code_quality.is_applicable:
            component_scores["code_quality"] = code_quality.score

        included_weight = sum(self.WEIGHTS[name] for name in component_scores)
        raw_score = sum(component_scores[name] * self.WEIGHTS[name] for name in component_scores) / included_weight
        overall = round(raw_score)
        effective_weights = {
            name: round(self.WEIGHTS[name] / included_weight, 4)
            for name in component_scores
        }

        strong_points = self._strong_points(structure, code_quality, readme, dependencies, testing, security)
        weak_points = self._weak_points(structure, code_quality, readme, dependencies, testing, security)
        top_issues = self._top_issues(structure, code_quality, readme, dependencies, testing, security)
        roadmap = self._roadmap(top_issues, structure, readme, testing, security, dependencies, code_quality)

        return ScoreBreakdown(
            overall_score=overall,
            grade=self.grade(overall),
            strong_points=strong_points,
            weak_points=weak_points,
            top_issues=top_issues,
            roadmap=roadmap,
            weights=effective_weights,
        )

    @staticmethod
    def grade(score: int) -> str:
        """Convert a score into a repository grade."""
        if score >= 90:
            return "Excellent"
        if score >= 75:
            return "Good"
        if score >= 60:
            return "Average"
        if score >= 40:
            return "Needs Improvement"
        return "Poor"

    @staticmethod
    def _strong_points(
        structure: StructureResult,
        code_quality: CodeQualityResult,
        readme: ReadmeResult,
        dependencies: DependencyResult,
        testing: TestingResult,
        security: SecurityResult,
    ) -> list[str]:
        points: list[str] = []
        if structure.score >= 75:
            points.append("Repository structure is organized")
        if readme.score >= 75:
            points.append("README documentation is strong")
        if dependencies.score >= 75:
            points.append("Dependency setup looks healthy")
        if security.score >= 85:
            points.append("No major security warning found")
        if testing.score >= 70:
            points.append("Testing setup is present")
        if code_quality.is_applicable and code_quality.score >= 75:
            points.append("Cross-language maintainability signal is healthy")
        if code_quality.is_applicable and len(code_quality.language_breakdown) > 1:
            points.append(f"Language-aware audit covers {len(code_quality.language_breakdown)} source ecosystems")
        if not code_quality.is_applicable:
            points.append("Code quality was marked N/A instead of incorrectly scored")
        return points or ["Repository has a starting foundation that can be improved"]

    @staticmethod
    def _weak_points(
        structure: StructureResult,
        code_quality: CodeQualityResult,
        readme: ReadmeResult,
        dependencies: DependencyResult,
        testing: TestingResult,
        security: SecurityResult,
    ) -> list[str]:
        points: list[str] = []
        if testing.score < 60:
            points.append("Testing readiness is weak")
        if readme.score < 70:
            points.append("README is incomplete")
        if code_quality.is_applicable and code_quality.score < 70:
            points.append("Code quality needs refactoring")
        if security.score < 80:
            points.append("Security warnings need attention")
        if dependencies.score < 70:
            points.append("Dependency file needs improvement")
        if structure.score < 70:
            points.append("Folder structure needs cleanup")
        return points

    @staticmethod
    def _top_issues(
        structure: StructureResult,
        code_quality: CodeQualityResult,
        readme: ReadmeResult,
        dependencies: DependencyResult,
        testing: TestingResult,
        security: SecurityResult,
    ) -> list[str]:
        candidates: list[tuple[int, str]] = []

        for issue in testing.issues:
            candidates.append((100 - testing.score + 20, issue))
        for issue in readme.missing_sections[:5]:
            candidates.append((100 - readme.score + 10, f"README missing section: {issue}"))
        for issue in security.warnings[:10]:
            candidates.append((100 - security.score + 30, issue))
        for issue in structure.issues:
            candidates.append((100 - structure.score + 5, issue))
        if code_quality.is_applicable:
            severity_bonus = {"high": 28, "medium": 14, "low": 5}
            for issue in code_quality.issues[:30]:
                candidates.append((100 - code_quality.score + severity_bonus.get(issue.severity, 8), issue.message))
            for issue in code_quality.missing_type_hints[:10]:
                candidates.append((100 - code_quality.score, issue))
        for issue in dependencies.warnings:
            candidates.append((100 - dependencies.score, issue))

        seen: set[str] = set()
        top: list[str] = []
        for _priority, issue in sorted(candidates, reverse=True, key=lambda item: item[0]):
            if issue not in seen:
                seen.add(issue)
                top.append(issue)
            if len(top) == 10:
                break
        return top or ["No serious issue found"]

    @staticmethod
    def _roadmap(
        top_issues: list[str],
        structure: StructureResult,
        readme: ReadmeResult,
        testing: TestingResult,
        security: SecurityResult,
        dependencies: DependencyResult,
        code_quality: CodeQualityResult,
    ) -> list[str]:
        roadmap: list[str] = []

        if readme.score < 80:
            roadmap.append("Phase 1: Improve README with installation, usage, screenshots, roadmap, license, and contact sections.")
        if testing.score < 75:
            roadmap.append("Phase 2: Add automated tests for core modules, public APIs, error paths, and business logic using the standard framework for this stack.")
        if code_quality.is_applicable and code_quality.score < 75:
            roadmap.append("Phase 3: Refactor long functions/files, reduce deep nesting, remove debug output, and apply the right formatter/linter for each detected language.")
        if security.score < 90:
            roadmap.append("Phase 4: Remove hardcoded secrets, delete committed .env files, and replace unsafe eval/subprocess usage.")
        if dependencies.score < 85:
            roadmap.append("Phase 5: Pin important dependencies and document the primary package/build manifest for each ecosystem.")
        if structure.score < 85:
            roadmap.append("Phase 6: Add docs/, LICENSE, .gitignore, and GitHub Actions workflow.")

        roadmap.append("Final Phase: Export sample reports and add screenshots/GIF demo to make the repository recruiter-ready.")
        return roadmap[:8]
