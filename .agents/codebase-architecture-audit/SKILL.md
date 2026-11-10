---
name: codebase-architecture-audit
description: Fully audit an existing codebase and recommend the simplest, leanest, and most maintainable project structure without modifying files.
---

# Codebase Architecture Audit

## Purpose

Analyze the entire codebase and recommend the best project structure based on its actual requirements, existing implementation, and complexity.

Prioritize simplicity, maintainability, clear responsibilities, and ease of navigation. Avoid unnecessary abstractions and overengineering.

## Instructions

### 1. Inspect the Codebase

Before making recommendations, inspect:

- Project directory and file structure.
- Dependencies and configuration files.
- Existing architecture and design patterns.
- Modules, components, services, and utilities.
- Data flow and dependencies between modules.
- Existing documentation and development conventions.

Understand how the application works before evaluating its structure.

### 2. Identify Structural Problems

Look for:

- Poorly organized files and directories.
- Unnecessary directory nesting.
- Duplicated code and responsibilities.
- Tightly coupled modules.
- Unnecessary abstractions and design patterns.
- Unused files, directories, and dependencies.
- Inconsistent naming conventions.
- Components or modules with multiple responsibilities.
- Unnecessary complexity in the existing architecture.

Only report issues supported by actual codebase findings.

### 3. Evaluate the Existing Architecture

Determine whether the current architecture is appropriate for the project's:

- Size and complexity.
- Technology stack.
- Application requirements.
- Development workflow.
- Long-term maintenance needs.

Do not force architectural patterns simply because they are commonly recommended.

### 4. Recommend a Lean Structure

Propose a clean and maintainable directory structure.

Follow these principles:

- Separation of concerns.
- Single responsibility.
- Loose coupling.
- High cohesion.
- Reusability where genuinely beneficial.
- Consistent and descriptive naming.
- Minimal directory nesting.
- Clear ownership of files and modules.

Prefer a simple structure that fits the project rather than a generic enterprise architecture.

### 5. Review Existing Files

Classify existing files and directories into:

- Keep: Already organized appropriately.
- Move: Belong in a different directory.
- Rename: Have unclear or inconsistent names.
- Merge: Duplicate or unnecessarily separated responsibilities.
- Remove: Confirmed unused or unnecessary files.

Do not recommend removing files without verifying their usage.

### 6. Minimize Complexity

Follow these constraints:

- Prefer existing implementations over unnecessary rewrites.
- Reuse existing utilities and conventions.
- Avoid unnecessary services, managers, providers, and abstractions.
- Avoid introducing additional dependencies.
- Avoid excessive folder nesting.
- Do not create directories for hypothetical future requirements.
- Do not sacrifice readability for architectural complexity.
- Keep documentation consistent with the actual implementation.

## Expected Output

Produce a comprehensive audit report with the following sections:

### 1. Current Structure Assessment
Describe the existing organization and overall architectural quality.

### 2. Identified Problems
List structural issues, unnecessary complexity, duplication, and maintainability concerns.

### 3. Recommended Architecture
Explain the recommended architectural approach and why it fits the project.

### 4. Proposed Directory Structure
Provide a complete directory tree with brief descriptions of important directories.

### 5. File Organization Recommendations
Identify which existing files should be kept, moved, renamed, merged, or removed.

### 6. Improvement Opportunities
Recommend practical improvements to organization, separation of concerns, and maintainability.

### 7. Prioritized Action Plan
Organize recommended changes by priority:

- High: Important structural or architectural problems.
- Medium: Improvements to maintainability and consistency.
- Low: Optional cleanup and minor organizational improvements.

For each recommendation, explain its purpose and expected benefit.

## Constraints

- DO NOT modify, move, rename, delete, or create project files during the audit.
- DO NOT implement the proposed structure.
- DO NOT install additional dependencies.
- DO NOT rewrite existing functionality.
- DO NOT introduce unnecessary architectural patterns.
- Preserve existing functionality and project conventions.
- Base every recommendation on actual codebase inspection.
- Clearly distinguish verified problems from optional improvements.

## Approval Requirement

This skill is strictly for auditing and recommending.

After presenting the audit report, STOP and wait for explicit user approval before making any changes.

Do not automatically proceed with implementation.