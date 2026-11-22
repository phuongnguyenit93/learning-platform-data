# Separating Security Patch Changes From Major Changes When Root-Cause Tracing Is Needed

## 1. Why Separate Both Types of Changes?

During Java ecosystem upgrades, teams often have to handle two needs simultaneously: patching a security vulnerability affecting a dependency or runtime, and upgrading the major version of a JDK, framework, or library to retain support or gain new capabilities. These two needs may arise at the same time, yet they have different goals and risk profiles.

A **security patch** aims to eliminate or mitigate an identified vulnerability. The necessary change may be tiny, such as bumping one dependency from a vulnerable patch version to a CVE-fixed patch version. A **major change** typically has a much broader scope: APIs may be removed, default behaviors may shift, the dependency graph may be reorganized, namespaces may move from `javax` to `jakarta`, or minimum JDK/build tool requirements may change.

Combining a security patch and a major migration into one big change makes root-cause identification difficult when the system fails. Errors could stem from the patch, API changes, transitive dependencies, new configurations, the compiler, the runtime, or interactions among multiple changes. Prolonged root-cause investigation can slow down both security remediation and migration.

Separating changes into independent parts helps the team answer critical questions:

- Does the security patch resolve the exact vulnerability without causing unexpected behavioral changes?
- Does the major migration introduce standalone failures when no security patch accompanies it?
- If only the patch is deployed without upgrading the major version yet, does the system still build, run, and stay supported?
- If both must deploy together, what evidence indicates whether a failure stems from the patch, the migration, or their interaction?
- Can part of the change be rolled back or re-released without creating an insecure security posture?

The goal of separation is preserving traceability and fault isolation. Deployment may happen in two separate waves or within the same release, depending on urgency and technical constraints. Crucially, each group of changes must maintain its own scope, evidence, and acceptance criteria.

## 2. Distinguishing Security Patches From Major Changes

### 2.1. Security Patches

A security patch is a change made to remediate a weakness or vulnerability. It may arrive in a patch release, minor release, vendor update, backport, or newer library version. Not all providers follow the same versioning conventions, so version numbers alone cannot determine the magnitude of change.

Information to verify before choosing a patch:

- Vulnerability identifier (e.g., CVE), severity, and exploitation conditions.
- Affected artifacts, modules, and versions, including transitive dependencies.
- Vendor-published fixed version and release branches still under support.
- Whether a backport patch exists for the current branch or upgrading to a new minor/major is required.
- Accompanying changes beyond the security fix: APIs, configuration, runtime requirements, other dependencies, or default behaviors.
- Migration guides, advisories, release notes, and known limitations of the patch.

A patch may fix a vulnerability yet simultaneously alter behavior because it tightens validation, removes weak algorithms, changes TLS defaults, or rejects previously accepted inputs. Therefore, "security patch" does not mean "zero compatibility risk".

### 2.2. Major Changes

Major versions are typically milestones likely to contain incompatible changes, though actual scope depends on each project's release policy. Some ecosystems follow Semantic Versioning quite strictly; some platforms have custom rules or introduce large changes in minor releases.

Signs indicating a major migration may have broad scope:

- Public APIs removed, signatures altered, or semantics changed.
- Package/namespace changes, e.g., moving Jakarta EE APIs from `javax.*` to `jakarta.*`.
- Minimum JDK, class-file target, or minimum build tool version changes.
- Dependency BOM/platform alters many artifacts simultaneously.
- Configuration, auto-configuration, lifecycle, serialization, security, or transaction semantics change.
- Plugins, annotation processors, test engines, runtime containers, or drivers must upgrade together.

A major migration must be evaluated as a platform change. It should not be treated as a simple "version bump" step.

### 2.3. Comparison Table of Goals and Evidence

| Aspect | Security patch | Major migration |
| --- | --- | --- |
| Primary goal | Remediate vulnerability or reduce exploitation risk | Move to target platform/API/version |
| Expected scope | Can be small, yet must be verified | Typically broader with many interrelated components |
| Input evidence | Security advisory, CVE, fixed version, dependency path | Migration guide, compatibility matrix, release notes |
| Primary risks | Regressions from security or dependency changes | Breaking APIs/behavior, build/runtime, schema, and integration |
| Core testing | Exploit path tests, related regressions, dependency scans | Build, unit/integration/contract, runtime, and operations |
| Completion criteria | Fixed version is deployed and vulnerability is absent within assessed scope | System satisfies contracts and requirements on the new platform |
| Rollback | Must weigh risk of reverting to a vulnerable build | Must weigh bytecode, data, schema, and version compatibility |

Both change types can intersect. For instance, a vendor may release a CVE fix only in a new major version. In that case, the team must evaluate upgrading the major version as part of the security remediation plan rather than assuming complete separation is possible via an old patch version.

## 3. When Should Changes Be Separated?

Separating security patches from major migrations is especially helpful when these conditions hold:

1. The security patch can be applied on the current branch without a major upgrade.
2. The major migration involves many API, configuration, or dependency changes unrelated to the CVE.
3. When failures occur, the team needs to pinpoint quickly which change caused the regression.
4. Each change set can be tested independently against the same baseline.
5. Separate artifacts or commits can be produced for comparison, rollback, and traceability.
6. Security deadlines and the major migration schedule differ.

For example, a service runs Spring Boot 2.x and an HTTP library that has a CVE patch within the same branch. The team also plans to move to Spring Boot 3.x, Java 21, and the Jakarta namespace. If the patch can be applied safely on the current branch, verify and release the patch independently first, then perform the major migration on the patched baseline.

Separation ensures that if the major migration introduces an error, the team can compare against a baseline already containing the security patch. Consequently, the vulnerability never has to be reopened merely to revert to the pre-migration state.

## 4. When Is Complete Separation Impossible or Inadvisable?

An independent patch for the current branch is not always available. Separation may be impossible when:

- The vendor fixes the vulnerability only in a new major version.
- The old version is end-of-life and no longer receives security updates.
- The patch requires API or data-structure changes supported only in the new major.
- The affected dependency is an integral part of the framework; upgrading it alone creates an unsupported version combination.
- Both the patch and migration require the same schema/protocol change to avoid an insecure state.
- An urgent mandate forces deployment within a single window.

Even in those cases, still **separate logic and evidence**, even if deployment artifacts cannot be separated. The team can prepare separate commits, test variants on investigation branches, and then combine the necessary changes into one evaluated release.

Never delay patching a severely exploitable vulnerability merely to keep root-cause analysis convenient. If simultaneous deployment is unavoidable, prioritize reducing security risk while strengthening testing, observability, and recovery plans. If the patch exists only in the new major, upgrading the major may itself be the mandatory remediation action.

## 5. Designing Branches and Commits to Preserve Traceability

### 5.1. Starting From a Defined Baseline

Before editing, identify the verified baseline commit, release tag, JDK, build tool, dependency lock/BOM, and test results. The baseline must be reproducible for comparison.

Example branch convention:

```text
main
  ├── security/CVE-2026-12345
  └── migration/java21-framework-major
```

CVE and branch names are examples only. Projects may use other conventions as long as each branch has a clear objective and links to an issue/advisory.

### 5.2. Security Branch Contains Only Changes Needed for the Patch

The security branch should contain only the dependency updates, configurations, or code changes truly required to address the vulnerability. Avoid mixing formatters, unrelated refactors, major framework switches, or bulk dependency bumps into the same branch.

Example commit history:

```text
security/CVE-2026-12345
  1. Update vulnerable-client to fixed patch release
  2. Add regression test for vulnerable input
  3. Update security advisory record
```

Each commit should describe its reason and evidence. If multiple modules must change, preserve links to the CVE and why each change belongs within patch scope.

### 5.3. Major Migration Branch Keeps Its Own Scope

The migration branch contains the JDK/framework/API changes needed for the major target. If the security branch has already been merged or released, branch the migration off the patched baseline so you never accidentally revert to the vulnerable dependency.

If you need to analyze the major migration's impact separately, create a worktree or test branch from the patched commit and apply the major changes there. Avoid resetting or rewriting shared branches; retain commits and artifacts for traceability.

### 5.4. Controlled Cherry-Picks and Merges

If the security branch must land across multiple supported release branches, cherry-pick commits or merge per repository policy. After applying, re-run tests on every branch because patches may depend on different APIs or dependencies.

Never blindly cherry-pick a commit from a major branch back to an older branch. If that commit uses new APIs or altered structures, backport separately and test in the target branch's exact environment.

Illustrative Git commands:

```bash
# Create security patch branch from verified baseline
git switch -c security/CVE-2026-12345 <baseline-tag>

# After testing and committing the patch, switch to migration branch
git switch -c migration/java21-framework-major <security-patch-commit>

# Check history and migration diff
git log --oneline --decorate -n 20
git diff <security-patch-commit>..HEAD
```

Placeholders like `<baseline-tag>` and `<security-patch-commit>` must be replaced with verified real commits/tags. Do not run these commands mechanically if the repository enforces specific branch protection rules or release flows.

## 6. Test Matrix for Root-Cause Isolation

To determine whether the patch or the major migration caused a failure, create comparable variants from the same baseline. A minimal matrix includes:

| Variant | Security patch | Major migration | Purpose |
| --- | --- | --- | --- |
| A — Baseline | No | No | Confirm original state and validate test environment. |
| B — Patch only | Yes | No | Isolate impact of the security patch alone. |
| C — Major only | No | Yes | Isolate impact of the major migration when safely testable. |
| D — Combined | Yes | Yes | Validate final combination and detect interactions between both changes. |

Not every variant C is permissible to run or release. If the baseline has a severe vulnerability, run only in isolated environments with synthetic data and solely for the time needed to investigate; never deploy an exploitable variant to production. If the vendor does not support the new major without the patch, variant C may be invalid and this limitation must be documented explicitly.

### 6.1. Keeping Test Conditions Identical

When comparing A, B, C, and D, hold variables outside the factor under test constant:

- Same source baseline and same test suite, except intentionally added new tests.
- Same JDK/build tool when measuring a dependency patch alone; if testing a major JDK upgrade, document this change explicitly.
- Same configurations, environment variables, database snapshots, and input datasets.
- Same dependency repositories, lockfiles/BOMs, and resolution rules.
- Same container/OS/CPU types and resource limits when comparing runtime.
- Same build/test commands and pass/fail criteria.

If multiple factors must change together, document them as a composite variant. Never conclude a single dependency is the cause merely because an error appeared after a build containing many changes.

### 6.2. Interpreting Results

| Observed result | Investigation direction |
| --- | --- |
| A pass, B fail | Focus on the security patch, swapped dependency, security configuration, and regression tests. |
| A pass, C fail | Focus on major changes: APIs, framework, JDK, plugins, configurations, and runtime. |
| B pass, C pass, D fail | Possible interaction between patch and major; check dependency alignment, classpath order, config, and inter-component contracts. |
| A fail, B/C/D yield varying outcomes | Baseline already failing or test environment unstable; separate pre-existing errors from new ones. |
| C cannot be validly built without required patch | Record matrix limitation; use an isolated test branch or other commit/diff comparisons instead of assuming C's outcome. |

A single pass/fail is not always conclusive. For flaky tests, race conditions, or performance issues, run repeatedly, control data, and inspect logs/metrics. For production-only errors, gather runtime evidence without exposing the system to unnecessary risk.

## 7. Tracking Dependencies and Security Advisories

### 7.1. Identifying Affected Dependencies

A CVE may reside in a transitive dependency the team never declared directly. Therefore, inspect the dependency graph for the exact configuration and packaged artifacts.

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency vulnerable-artifact --configuration runtimeClasspath
```

With Maven:

```bash
mvn dependency:tree -Dscope=runtime
mvn help:effective-pom
```

Inspect runtime, compile, test, plugin, and buildscript dependencies whenever they can affect the release process. A vulnerability in a build plugin can impact the pipeline even if the production artifact never packages that plugin.

### 7.2. Verifying Fixed Versions and Impact Scope

Do not rely solely on a single scanner output. Cross-check vendor advisories, changelogs, package metadata, and the actually resolved version. Record:

- Affected versions and the first fixed version.
- Exploitation conditions and whether modules/features exercise the vulnerable code path.
- Whether a patch exists for the current branch or only a new major release.
- Whether the patch requires upgrading foundational dependencies, the JDK, or the framework.
- Any vendor-published regressions or known issues.

If a scanner flags a vulnerable version yet the dependency is neither packaged nor reachable at runtime, still document the rationale and exclusion evidence per organizational policy. Never dismiss a finding just because you do not immediately see a call site in source code.

### 7.3. Using SBOMs and Scans to Verify After Changes

A Software Bill of Materials (SBOM) records the components inside an artifact. Once patched, regenerate the SBOM from the new artifact and re-scan to confirm the dependency actually moved to the fixed version. Comparing before/after SBOMs catches unintended shifts in the dependency graph.

An update may fix a known CVE while pulling in another dependency that has its own vulnerability. Always verify overall post-change results rather than checking only that one specific CVE vanished.

## 8. Organizing Commits and Reporting Changes

### 8.1. Splitting Commits by Objective

Keep security commits independent of major migration commits whenever possible. For example:

```text
SECURITY: Upgrade vulnerable HTTP client to fixed release
TEST: Add regression coverage for CVE-2026-12345
MIGRATION: Move application to Java 21 toolchain
MIGRATION: Upgrade framework major and Jakarta APIs
MIGRATION: Align persistence and test dependencies
```

Small commits help reviewers understand each change and enable `git bisect` when regressions surface. If a squashed or combined release commit is needed, retain commit history or link back to component commits.

### 8.2. Recording Evidence at Each Step

For security patches, save the advisory/CVE, fixed version, dependency path, regression tests, and post-build scan results. For major migrations, save the applied migration guide, API/configuration changes, JDK/build tool versions, dependency graph, and test results.

In pull requests or change records, state clearly:

- Goal of the change and linked issues/advisories.
- Which dependencies or modules were changed.
- Which components were intentionally left unchanged.
- Build/test commands and execution environment.
- Pass/fail outcomes, remaining warnings, and test limitations.
- Rollout, observability, and rollback plans.

Never write "all tests passed" if only unit tests ran. State the exact test scope so reviewers know what the evidence actually proves.

## 9. Tracing Regressions With Git and Build Tools

### 9.1. Comparing Commits and Dependency Graphs

When a failure appears, start by identifying which changes entered the artifact:

```bash
git diff <known-good-commit>..<failing-commit> -- build.gradle settings.gradle gradle/libs.versions.toml
git diff <known-good-commit>..<failing-commit> -- pom.xml
git log --oneline --decorate <known-good-commit>..<failing-commit>
```

Compare against the resolved runtime dependency graph, not just declaration files. Version catalogs, BOMs, plugin management, constraints, and dependency substitutions can make resolved versions differ from what someone infers from a single line of declaration.

### 9.2. Using `git bisect` When an Automated Test Exists

If a regression is reproducibly triggered by a stable test or build command, `git bisect` locates the first commit where the error appeared:

```bash
git bisect start
git bisect bad <failing-commit>
git bisect good <known-good-commit>
git bisect run ./gradlew test --tests com.example.CompatibilityTest
git bisect reset
```

This example uses Gradle; for Maven, substitute the corresponding test command. Use `git bisect run` only when the command returns reliable exit codes: failing tests must exit non-zero, required environment dependencies must exist, and results must not suffer from flaky tests. Otherwise, bisect manually and record each step.

`git bisect` identifies the commit that changed state according to the defined test. It neither explains the technical root cause on its own nor distinguishes two changes bundled into a single commit. Thus, goal-separated commits and regression tests make the tool effective.

### 9.3. Inspecting Class Loading and Actual Runtime

When suspecting dependencies/classpath, verify which JAR the JVM loaded classes from. Class-loading logs can be enabled in an appropriate test environment:

```bash
java -Xlog:class+load=info -jar application.jar
```

This log links classes to load sources, though it can be huge; enable it only in investigation environments and filter by relevant packages/classes. Combine with dependency insight, startup logs, and launcher configuration to determine the actual runtime classpath.

## 10. Rollout and Rollback When Both Changes Have Different Timelines

### 10.1. Releasing the Security Patch First

If the patch is independent and the current branch remains supported, ship a small update to reduce security risk before completing the major migration. After release, confirm:

- The production artifact actually contains the fixed version.
- Scanners/SBOMs no longer report the affected version within remediated scope.
- Regression tests and critical business flows continue passing.
- Monitoring shows no new errors in latency, connectivity, authentication, or input handling.
- The major migration branch starts from the patched baseline or pulls the patch through a clear merge workflow.

### 10.2. Releasing the Major Migration Afterward

Once the baseline is patched, the team proceeds with the major migration using its own tests and acceptance criteria. If the major migration introduces failures, you can revert to the patched artifact, preserving a stronger security posture than reverting to an exploitable artifact.

This is safe only if schemas, messages, and data produced by the new version remain compatible with the patched version. If the migration makes backward-incompatible data changes, use an expand–migrate–contract strategy or a dedicated roll-forward plan.

### 10.3. When Simultaneous Release Is Unavoidable

If the patch exists only in the new major or security deadlines prevent splitting waves, prepare a combined release. Even then, separate commits/branches and tests where possible; run combined tests on the final artifact; and document parts that could not be tested independently along with reasons.

Rollback planning must factor in security. If the old artifact contains an actively exploited vulnerability, full rollback may be unacceptable. Prepare roll-forward fixes, feature flags, exposure reduction, or approved network-level mitigations.

## 11. Case Study: HTTP Library Patch and Major Framework Migration

Suppose an application runs Java 17 and an older framework generation. An HTTP client dependency has a CVE; the vendor releases a fixed patch on the current branch. Simultaneously, the team plans a move to Java 21 and a new major framework with the Jakarta namespace.

### 11.1. Plan to Split Into Two Workstreams

**Security workstream:**

1. Identify affected artifacts via the runtime dependency graph.
2. Cross-check the CVE/advisory and select the fixed patch supported on the current framework.
3. Cut a security branch from the tag currently running in production.
4. Upgrade only the dependency needing patching and add regression tests for the vulnerable input/exploit path.
5. Build, run integration tests, generate an SBOM, and re-scan the artifact.
6. Release the small patch and verify runtime uses the fixed version.

**Major migration workstream:**

1. Branch from the commit already containing the security patch.
2. Check whether the Gradle/Maven wrapper and plugins support JDK 21.
3. Upgrade the framework major per migration guide and migrate related Jakarta APIs.
4. Align persistence, validation, security, HTTP client, and test dependencies to the target BOM.
5. Run unit, integration, contract, and runtime tests on a JDK 21 image.
6. Compare performance, startup, connection errors, and HTTP behavior against the patched baseline.

### 11.2. Interpreting Failures

Suppose after patching, build B runs cleanly. After upgrading the major version on top of the patched baseline, build D hits HTTP timeout errors.

The team should compare timeout settings, connection pools, TLS, retry policies, and HTTP client versions in the dependency graph. Since B has no errors while D fails, investigate the major change set or framework-client interactions. If testing a major-only variant can be done safely in an isolated environment, its results can add evidence; otherwise, never create an unpatched variant for production.

If timeouts appear only when enabling a new framework setting, run controlled experiments keeping the patched dependency while toggling that single setting. Record connection metrics, pool saturation, and handshake logs to determine the mechanism. Do not rush to roll back to an exploitable artifact if you can keep the patch and fix forward.

### 11.3. Completion Criteria

The security workstream completes only when the fixed version is present in the deployed artifact, scans/SBOMs confirm it, and relevant regression tests pass. The major workstream completes only when the system meets build/runtime/API/data requirements on the new platform, major-induced errors are resolved, and rollout/rollback plans are verified.

Both workstreams may share certain tests or artifacts, yet their results and acceptance criteria must be recorded separately to avoid blurring accountability.

## 12. Decision Checklist: Whether to Separate or Not

Before starting, the team can use these questions:

- Does a fixed version exist for the current branch?
- Is the current branch still supported by the vendor?
- Does the patch pull in breaking APIs or major framework changes?
- Can independent commits and artifacts be built for the security patch?
- Can patch-only tests run without introducing security risks?
- Is the major migration large enough to warrant isolated investigation if regressions occur?
- Must legacy consumers or runtimes stay supported during a transition period?
- If combining is mandatory, can individual commits/variants still be tested in an isolated environment?
- Would rollback revert the system to an exploitable version?
- Do SBOMs, scans, regression tests, and logs/metrics exist to verify results?

If the answers regarding a fixed version, support, and independence are yes, separating the patch from the major usually yields superior traceability. If not, explicitly document the constraints preventing separation and strengthen verification evidence for the combined release.

## 13. Conclusion

Separating security patches from major changes is a variable-isolation technique during migration. It helps teams evaluate patch impact, validate migrations independently, scope regressions, and retain a rollback path with an acceptable security posture. Separation should be used whenever a supported standalone patch exists and does not create dependency combinations outside the compatibility matrix.

When separating artifacts is impossible or security timelines mandate shipping together, teams should still separate commits, tests, evidence, and acceptance criteria per goal. Never delay fixing a critical vulnerability solely for investigation convenience; instead, rely on clear baselines, test matrices, SBOMs, dependency analysis, and runtime observability to pinpoint root causes while keeping risk under control.
