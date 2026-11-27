# Checking Formatting, Code Rules, and Static Analysis Issues

In CI/CD, source code must be verified before being integrated into the main branch or used to produce release artifacts. Beyond running tests, the pipeline should enforce quality gates that check code presentation, team coding rules, and defects detectable without executing the application.

The three commonly used check categories are **formatting**, **lint/code rules**, and **static analysis**. They are related, yet answer different questions:

- Formatters ensure code has consistent presentation.
- Linters and code rule sets detect non-conformance to conventions or undesirable coding patterns.
- Static analysis inspects structure, types, control flow, or data flow to uncover potential bugs without running the program.

A solid quality gate specifies which tools must run, which defect severities block the pipeline, how legacy warnings are handled, and what evidence is retained. This enables teams to catch issues early, simplify reviews, and maintain stable quality standards across builds.

## 1. Distinguishing the three check categories

| Category | Core question | Examples | Expected output |
|---|---|---|---|
| Formatting | Is the code presented consistently? | Indentation, line wrapping, import order, whitespace | Files conform to the standard format |
| Lint and code rules | Does the code violate agreed conventions or coding patterns? | Naming, complexity, unused imports, prohibited APIs | List of rule violations with locations and rule IDs |
| Static analysis | Are there logic errors or risks inferable without running the program? | Null dereference, resource leak, dead code, unsafe data paths | Findings with severity, location, and explanation |

The boundary between lint and static analysis varies across tools. A linter may perform data-flow analysis; a static analyzer may also check style. Therefore, when designing pipelines, classify checks by your team's objectives and policy rather than relying solely on product labels.

## 2. Formatting: standardizing code presentation

A formatter automatically applies a set of presentation rules. Given the same input and the same formatter version/configuration, the tool produces consistent line breaks, indentation, spacing, or import ordering.

Formatting typically handles:

- Indentation, braces, and whitespace.
- Line length and expression wrapping.
- Import ordering or import grouping when supported by the formatter.
- Formatting of annotations, generics, lambdas, and language constructs.
- Formatting rules for JSON, YAML, XML, Markdown, or configuration files.

Formatters keep reviews focused on logic changes because diffs contain less personal-style noise. They also reduce repetitive style debates and keep new files visually uniform.

### Format and check are two distinct operations

On a developer workstation, engineers may run a command that automatically modifies files, for example:

```bash
./gradlew spotlessApply
```

In CI, you should normally run a check-only command:

```bash
./gradlew spotlessCheck
```

`spotlessApply` can modify files in the workspace. `spotlessCheck` verifies that files are already properly formatted and fails if deviations are detected. CI should fail so the author fixes and commits the changes, ensuring the contents are reviewed and recorded in Git.

Do not let the pipeline silently reformat files and continue building without exposing the diff. Doing so could produce an artifact from content different from the reviewed commit. If an organization wants a bot to open formatting commits or pull requests, that must be a separate workflow with explicit permissions and history.

### Consistent formatter configuration

Store configuration in the repository or in a version-pinned shared tool. For example, a Java project can use Spotless with an explicitly configured formatter:

```kotlin
plugins {
    id("com.diffplug.spotless") version "<PINNED_PLUGIN_VERSION>"
}

spotless {
    java {
        googleJavaFormat("<PINNED_FORMATTER_VERSION>")
        target("src/**/*.java")
    }
}
```

Values in angle brackets are placeholders that must be replaced with versions selected and vetted by the organization. Do not let a formatter pull the latest version dynamically, as formatter changes can create massive diffs even when business code has not changed.

When upgrading a formatter, perform the upgrade in a separate pull request or clearly separate formatting changes from logic changes. This makes reviewing easier and avoids hiding bugs inside large diffs.

## 3. Lint and code rules: enforcing coding conventions and design limits

Linting checks for suspicious patterns or deviations from conventions. Code rules may be defined by the language, framework, organization, or the project itself.

Example rules:

- No unused imports or variables.
- Follow naming conventions for classes, methods, and fields.
- Do not call deprecated APIs or APIs banned within the module.
- Limit method complexity or conditional branch counts.
- Do not swallow exceptions or leave catch blocks empty.
- Require resource handling via try-with-resources.
- Do not call `System.out` in production code when the project mandates a logger.
- Avoid wildcard imports if disallowed by convention.

For Java, common tools include Checkstyle, PMD, and compiler warnings/rules. Checkstyle focuses heavily on style and code structure; PMD can detect many suspicious code patterns, complexity issues, or inappropriate API usage. Exact capabilities depend on the configured rule set and version.

For example, Checkstyle can enforce:

```xml
<module name="Checker">
    <module name="TreeWalker">
        <module name="UnusedImports"/>
        <module name="NeedBraces"/>
        <module name="AvoidInlineConditionals"/>
    </module>
</module>
```

This is an illustrative snippet; verify module names and configuration structure against the Checkstyle version in use. Never copy a rule set without reviewing it against project conventions.

### Pick useful rules instead of enabling every warning

An overly broad or ill-suited rule set can generate low-value noise. When that happens, developers tend to ignore results, disable rules, or add arbitrary suppressions.

Start with rules that:

1. Prevent common defects with clear impact.
2. Have concrete, consistent fixes across team members.
3. Fit the repository's language, framework, and architecture.
4. Can be enforced automatically or explained clearly in review.
5. Have an owner accountable when rules need updates.

Rules driven by personal preference should be weighed carefully before becoming blocking gates. Rules around safety, resource handling, API usage, and outage-prone bugs usually carry far more value than low-impact style rules.

## 4. Static analysis: finding potential bugs without running the program

Static analysis inspects source code or bytecode to find execution paths that could lead to defects. Tools may use ASTs, type information, control-flow graphs, data-flow analysis, or interprocedural modeling to reason about behavior.

Common finding categories include:

| Category | Example | Risk |
|---|---|---|
| Nullability | Potential dereference of a null reference | Runtime exception |
| Resource management | Opening a stream/socket without closing it | Resource leak |
| Error handling | Ignoring exceptions or mishandling error branches | Masked errors, inconsistent state |
| Concurrency | Unsafe access to shared state | Race condition or corrupted data |
| Dead code | Unreachable branches or unused values | Redundant code, forgotten logic |
| API misuse | Using an API outside its contract or unsafely | Runtime error or unexpected behavior |
| Security-related flow | Untrusted data flowing into a sensitive sink | Injection or data exposure depending on context |

For Java, SpotBugs analyzes bytecode for bug patterns; Error Prone adds compile-time checks; other tools perform deeper data-flow or security analysis. Outcomes depend on configuration, tool version, annotation libraries, and the scope of analyzed code.

Static analysis does not prove a program is completely correct. Tools can miss bugs (false negatives) or report findings that are not bugs in a specific context (false positives). Unit tests, integration tests, reviews, and runtime testing remain essential because they provide different kinds of evidence.

## 5. Designing quality gates by severity

Not every finding deserves the same treatment. A quality gate must define severities and blocking thresholds:

| Level | Reference handling | Examples |
|---|---|---|
| Error/Critical | Block pipeline or merge | Bugs likely to cause crashes, severe resource leaks, or clear vulnerabilities |
| High | Block per risk policy | Bug patterns likely to cause data corruption or security flaws |
| Medium | Warn or block per module | High complexity, missing error handling, risky APIs in certain contexts |
| Low/Info | Display for incremental improvement | Maintainability or style suggestions with no direct impact |

Severity names are not uniform across tools. Map each scanner's severities to a shared project policy and document clearly which findings block merges.

A practical gate might require:

- Mandatory formatter and lint checks have zero new violations.
- Static analysis has zero new Error/Critical findings.
- High findings are resolved or covered by an approved exception.
- Medium/Low findings are tracked in the backlog or via quality thresholds.
- Required checks have results matching the exact commit under evaluation.

Do not set thresholds by counting total findings regardless of type and severity. One critical finding can be far worse than hundreds of style warnings. Conversely, letting finding counts grow unbounded degrades quality while the dashboard stays green.

## 6. Baselines: controlling legacy issues and preventing new ones

Long-lived repositories may already contain hundreds of findings before static analysis is introduced to CI. Blocking everything immediately makes adopting the tool difficult without a massive remediation effort.

A baseline records existing findings at a point in time to distinguish legacy technical debt from new issues. One implementation approach:

1. Run the analyzer on a chosen baseline revision.
2. Store the baseline alongside the repository or in a versioned finding management system.
3. On pull requests, compare new results against the baseline.
4. Block new findings at designated severities.
5. Periodically shrink the baseline by fixing old findings and updating the list.

A baseline must have an owner, creation date, update rules, and reviewability. If the baseline automatically absorbs every finding after each run, it will swallow new bugs and defeat the gate.

For new projects, you can start without a baseline if the rule set is well calibrated. For legacy projects, set gradual reduction targets by module or severity instead of ignoring all results.

## 7. Suppressions and exceptions require justification

Sometimes an analyzer reports a finding that does not apply in a specific context. Suppression allows excluding that finding, but its scope must be constrained:

- Suppress only the specific rule or finding; avoid disabling the entire analyzer.
- Document the rationale and conditions making the finding inapplicable.
- Attach an owner or tracking ticket if the suppression is temporary.
- Set a review expiration date when possible.
- Review suppressions like normal source code changes.

Java example:

```java
@SuppressWarnings("SpecificRule")
void processLegacyPayload() {
    // Justification and ticket link should be recorded in a comment per project conventions.
}
```

`SpecificRule` is a placeholder; the suppression name must match the analyzer in use. Never add blanket suppressions like `all` just to make the pipeline green. When a finding is accepted, the exception record should state who approved it, what scope is exempted, and when it must be re-evaluated.

## 8. Handling generated code and analysis scope

Generated code often differs in style from handwritten code and can trigger repetitive findings. Analyzers can be configured to exclude generated directories from certain rules, provided generated code is still verified at necessary layers such as compilation, dependency scanning, or security checks.

Do not exclude an entire directory just because it contains generated files if handwritten code lives there too. Separating generator output into a dedicated directory, marking generation sources, and controlling generator versions keeps configuration clean.

In monorepos, define scan scope by module and dependency graph. Scanning only changed files can miss defects caused by shared library changes affecting consumers. Changes to build scripts, rule configs, dependencies, or generated sources usually require expanding the check scope.

## 9. Quality gate example in Gradle and CI

A Gradle project can wire formatter, lint, and static analysis into separate tasks. Conceptual example:

```kotlin
plugins {
    java
    id("com.diffplug.spotless") version "<PINNED_VERSION>"
    checkstyle
    pmd
    id("com.github.spotbugs") version "<PINNED_VERSION>"
}

tasks.named("check") {
    dependsOn(
        "spotlessCheck",
        "checkstyleMain",
        "pmdMain",
        "spotbugsMain"
    )
}
```

This is an illustrative example; select plugin versions compatible with your Gradle/JDK versions, configure rule sets, and verify the actual generated tasks. In multi-module projects, ensure tasks apply to the right modules and source sets. Additional test or verification tasks can be attached to `check` per policy.

The CI pipeline then only needs to invoke one aggregate task:

```yaml
jobs:
  code_quality:
    steps:
      - name: Checkout
        uses: actions/checkout@<FULL_COMMIT_SHA>
      - name: Run code quality gate
        run: ./gradlew --no-daemon check
      - name: Publish reports
        if: always()
        run: ./gradlew --no-daemon aggregateQualityReports
```

`<FULL_COMMIT_SHA>` is a placeholder that must be replaced with a verified SHA. `aggregateQualityReports` is only an illustrative task name; create the task or replace it with your project's actual report-upload mechanism. The report-publishing step should run even after failures to preserve evidence, but a successful upload must never turn a failed quality gate into a pass.

In GitHub Actions, GitLab CI, or Jenkins, check groups can be split into separate jobs to run in parallel. If split across jobs, include an aggregator job that checks every required check and distinguishes success, failure, skipped, and cancelled. The merge gate passes only when required checks produce valid results for the exact revision.

## 10. Keeping results stable and actionable

Quality gate reliability depends on the stability of the tools themselves:

- Pin versions of formatters, linters, analyzers, plugins, and rule bundles.
- Keep rule configurations in Git so changes are reviewable.
- Run the same tool versions locally and in CI whenever possible.
- Record version, command, commit SHA, report, and execution duration.
- Prevent analyzers from downloading uncontrolled latest rules or policies at runtime.
- Separate reports by module and source set so findings have clear locations.
- Monitor execution time and avoid analyzing the same source repeatedly without benefit.

When a tool version changes, findings can change even if the source code did not. Treat analyzer upgrades as changes affecting the quality gate: read release notes, dry-run against the baseline, triage new findings, and update thresholds with review.

## 11. Common mistakes

| Mistake | Consequence | How to address |
|---|---|---|
| Running only a formatter without checking rules | Code looks uniform but still harbors potential bugs | Add appropriate lint and static analysis |
| Using auto-fix formatter mode in CI | Artifacts may differ from the reviewed commit | Use check mode; require authors to fix and commit |
| Enabling too many rules at once | Low-value noise causes the team to lose trust | Select rules by risk and roll out in phases |
| Blocking the pipeline on every warning | Increases false positives and turnaround time | Define clear severities and thresholds |
| Disabling the analyzer on hard-to-fix findings | Loses ability to catch new defects | Use baselines and justified suppressions |
| Letting the baseline auto-absorb all findings | New bugs turn into legacy debt | Review baseline changes and track trends |
| Broadly excluding entire generated folders | May skip code that still needs inspection | Isolate generated output and narrow exclusions |
| Failing to save reports when jobs fail | Hard to investigate findings and tune rules | Upload reports via an always-running diagnostics step |

## 12. Code quality gate design checklist

- [ ] A formatter is configured in check mode that does not mutate source in CI.
- [ ] Formatter version and configuration are pinned and stored in the repository.
- [ ] Lint/code rules reflect actual project conventions and risks.
- [ ] Static analysis is configured for the right language, framework, and source sets.
- [ ] Severities map clearly to blocking or warning policies.
- [ ] New findings are separated from legacy technical debt via controlled baselines when needed.
- [ ] Suppressions have narrow scope, justification, and an accountable owner.
- [ ] Generated code follows dedicated rules without overly broad exclusions.
- [ ] Reports, logs, rule IDs, and commit SHAs are retained for traceability.
- [ ] The quality gate aggregates statuses from all required checks and blocks when any check is missing results.

Formatting, lint, and static analysis complement one another. Formatting creates consistency, code rules preserve conventions and design boundaries, and static analysis uncovers latent defects from program structure. When tools are version-pinned, rules are intentional, and gates have transparent thresholds, pipelines provide fast feedback while maintaining verifiable quality standards.
