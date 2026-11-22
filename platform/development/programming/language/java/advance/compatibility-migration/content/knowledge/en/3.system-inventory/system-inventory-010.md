# Building a Risk Matrix and Transition Acceptance Criteria

During the **System Inventory** phase of **Java Advance Compatibility Migration**, building a risk matrix and acceptance criteria helps the migration team identify upfront what can break, the impact on the system, and the evidence required to conclude that an upgrade is safe.

A migration plan that merely lists steps to bump JDK, framework, or library versions is not enough. You must understand how components depend on each other, which contracts the application uses, which clients may already have been precompiled, and which runtime conditions must be preserved. A risk matrix turns those assumptions into items with accountable owners, priorities, and handling measures. Acceptance criteria turn transition goals into conditions verifiable by build outputs, tests, and runtime observation.

## 1. Objectives and Scope of Risk Assessment

Migration risk is the likelihood that a change during transition causes an incident or degrades system quality. Incidents can appear right at compile time, when the JVM loads and links classes, during business processing, when reading old data, or after deploying to production.

A risk assessment must answer these questions:

- Which components will change and which components depend on them?
- Which contracts must be preserved so old components continue working?
- Which changes could prevent old clients from linking with a new library?
- Which data, configurations, protocols, or behaviors may change?
- Which risks can be detected before release, and which only surface at runtime?
- What evidence proves a risk has been handled or accepted?
- If the transition fails, how can the system return to its previous working state?

Assessment scope should cover both directly upgraded components and affected consumers. For example, when upgrading an internal library, scope is not just the library's repository. You must consider applications, plugins, batch jobs, services, and modules already compiled against the old version.

A change may cause zero errors in an application rebuilt end to end yet still break an independently released plugin. Therefore, clearly identify two consumer groups:

| Consumer group | Characteristics | Appropriate verification |
|---|---|---|
| Consumers rebuilt alongside migration | Can recompile source code with the new dependency | Build all modules and run integration tests |
| Independently released consumers | May continue using bytecode compiled against the old API | Run old artifacts with new dependencies; check linkage and behavior |
| External uncontrolled consumers | Cannot force simultaneous updates | Keep APIs compatible, run contract tests, and plan version support |
| Consumers appearing only at runtime | Plugins, reflection, service providers, or dynamic class loaders | Test discovery, class loading, and real execution paths |

Do not bring a component into scope solely because it lives in the same repository. Base scoping on dependency relationships, deployment paths, and how components are loaded or invoked at runtime.

## 2. Gathering Data Before Scoring Risks

A matrix is only valuable when inputs accurately reflect the system. Before scoring, create a baseline describing the current state.

### 2.1. Identifying Baseline Versions and Artifacts

Record at minimum:

- Java version used to compile and JVM version used to run.
- Gradle, Maven, or build tool version and related plugins.
- Framework, internal library, and external dependency versions.
- Released artifacts: JAR, WAR, ZIP, images, or corresponding deployment packages.
- Classpath or module path configuration and how plugins are loaded.
- Runtime configuration, environment variables, system properties, and feature flags.
- Deployment profiles and differences across dev, test, staging, and production.

Distinguish versions declared in the build from artifacts actually loaded at runtime. Dependency resolution can pick a different version than expected due to transitive dependencies, dependency constraints, exclusions, or class loaders.

### 2.2. Mapping Dependency Relationships

For each component, identify:

- The component providing the API or capability.
- Consumers calling that API directly or through an abstraction.
- Compile-time, runtime, and test-time relationships.
- Whether components deploy together or follow independent release lifecycles.
- Integration points over HTTP, messaging, databases, files, serialization, or other protocols.
- Components loaded via classpath, module path, reflection, ServiceLoader, or plugin frameworks.

Example of a simple dependency graph:

~~~text
                    +------------------+
                    |  shared-api v1   |
                    +------------------+
                       ^       ^     ^
                       |       |     |
             +---------+       |     +----------+
             |                 |                |
       +-----------+    +-------------+   +-------------+
       | service A |    | plugin B    |   | batch job C |
       +-----------+    +-------------+   +-------------+
          built with       released          runs
          migration        separately        independently
~~~

Service A can be rebuilt together with the new library. Plugin B and batch job C may still keep old bytecode. These three consumers have different exposure levels despite depending on the same API.

### 2.3. Capturing the Current Contract

For Java libraries, the baseline should record public APIs and extension points:

- Public classes, interfaces, enums, records, and annotations.
- Constructors, methods, and fields accessible to consumers.
- Names, parameter types, return types, descriptors, and access modifiers.
- Inheritance relationships, implemented interfaces, and overridden methods.
- Generic signatures, annotations, and metadata used by frameworks or reflection.
- Compile-time constants that may already be inlined into consumer bytecode.
- Constructors or factory methods invoked by frameworks.
- Service providers, resources, class names in config, and discovery points.

When possible, save old artifacts and API analysis results to compare against the new version. Do not use current source code to guess the bytecode of a consumer released long ago; use the actual consumer artifact or a fixture compiled from the baseline version.

## 3. Classifying Risks in a Java Migration

A useful matrix does not merely say “the build might fail”. It classifies distinct failure modes to choose corresponding verification measures.

### 3.1. Binary Compatibility Risk

This is the risk that bytecode compiled against an old API fails to link against new classes or interfaces.

Common causes:

- Deleting or renaming classes, methods, constructors, or fields.
- Changing method descriptors by altering parameters or return types.
- Changing a member from static to instance or vice versa.
- Narrowing access visibility.
- Replacing a class with an interface or making incompatible inheritance changes.
- Adding an abstract method causing old implementations to lack an implementation when that call path is invoked.

Runtime symptoms can include **NoSuchMethodError**, **NoSuchFieldError**, **NoClassDefFoundError**, **AbstractMethodError**, **IllegalAccessError**, or **IncompatibleClassChangeError**.

Appropriate controls include comparing binary APIs, running clients compiled on the old version against the new artifact, and testing independently released implementations or plugins.

### 3.2. Source Compatibility Risk

Old source code may fail to compile against the new API even when old bytecode still runs.

Examples:

- Adding an overload makes a call ambiguous.
- Changing generic signatures or type inference.
- Adding checked exceptions to a method declaration.
- Changing return types affecting caller source code.
- Changing access rules or inherited types.
- Changing annotations or APIs used by annotation processors.

The control is compiling consumers from source with the new dependency while keeping binary compatibility tests separate. A passing build does not prove previously released bytecode still runs.

### 3.3. Behavioral Compatibility Risk

The API still exists, yet how it behaves has changed.

Examples:

- A method returns a different result or alters element ordering.
- Thrown exceptions change.
- Default values, timeouts, or retry policies change.
- Callback invocation order or side effects change.
- Transaction, synchronization, or concurrency rules change.
- An API that previously accepted null now rejects null.
- An operation that was previously idempotent now causes duplicate side effects.

These changes are usually not detected by descriptor comparison. Contract tests, regression tests, and business-result verification on representative data are needed.

### 3.4. Data and Serialization Risk

Migration can alter how data is read, written, or interpreted:

- Java serialization and serialVersionUID.
- JSON/XML field names, data types, nullability, and default values.
- Database schemas, indexes, constraints, and column types.
- Message schemas or event versions.
- File formats, encodings, timezones, and precision.
- Data cached or stored in sessions.

Test both reading old data and writing new data. If the system must support rolling deployments, determine whether old and new application versions can read/write data concurrently during the transition phase.

### 3.5. Runtime and Platform Risk

An API may remain identical yet the runtime still fails compatibility:

- Bytecode compiled for a newer Java target than the deployed JVM supports.
- Dependencies requiring JDK classes or methods absent at runtime.
- Changes to classpath/module path or module exports.
- Library version conflicts caused by transitive dependencies.
- Differences in class loaders or class loading order.
- Changes in reflection, proxies, instrumentation, or annotation processing.
- Differences in native libraries, TLS providers, charsets, or operating systems.

For example, **UnsupportedClassVersionError** usually indicates the running JVM does not support the class file version. This is a platform compatibility issue, not necessarily a binary API change in a library.

### 3.6. Operational and Security Risk

Do not limit the survey to source code. Version upgrades can alter:

- How configs, environment variables, and secrets are read.
- Health checks, readiness, liveness, and graceful shutdown.
- Logging, tracing, metrics, and log formats.
- TLS, certificates, cipher suites, and authentication.
- File permissions, process user, and network policies.
- Performance, heap usage, threads, connection pools, and latency.
- Rollback capability and schema/artifact compatibility.

These risks require evidence in a production-like deployment environment and sign-off from operational owners.

## 4. Building a Scoring Matrix

A risk matrix should be simple enough for the whole team to use consistently, yet still express likelihood, impact, and detection difficulty.

### 4.1. Scoring Likelihood

A 1-to-5 scale can be used:

| Score | Level | Reference description |
|---:|---|---|
| 1 | Rare | No dependency path or error condition observed; solid control evidence exists |
| 2 | Low | Possible yet narrow in scope with reliable controls already in place |
| 3 | Medium | Real dependency path exists; some assumptions remain unverified |
| 4 | High | Signs of incompatibility already seen or multiple consumers affected |
| 5 | Very high | Error already reproduced, contract-breaking change, or failure condition almost certain |

Do not score likelihood as low merely because no incident has been reported yet. If plugins or external consumers have not yet been surveyed, the accurate status is insufficient evidence to evaluate.

### 4.2. Scoring Impact

| Score | Level | Reference description |
|---:|---|---|
| 1 | Negligible | Minor impact, easy recovery, no effect on core business |
| 2 | Low | A secondary feature affected with a clear workaround |
| 3 | Medium | One consumer group or one business flow disrupted |
| 4 | High | Multiple services or critical business flows affected |
| 5 | Critical | System outage, data loss/corruption, security violation, or unsafe rollback |

Impact should be determined by actual consequences to users and operations, not by line count or fix difficulty.

### 4.3. Calculating Scores and Assigning Tiers

Simple formula:

~~~text
Risk Score = Likelihood x Impact
~~~

With each factor from 1 to 5, the risk score ranges from 1 to 25.

You can start with these reference thresholds:

| Score | Priority level | Handling approach |
|---:|---|---|
| 1–4 | Low | Monitor and record control evidence |
| 5–9 | Medium | Apply mitigation and test before release |
| 10–16 | High | Needs owner, remediation plan, and evidence before passing gate |
| 17–25 | Critical | Block transition until fixed or formally accepted at the appropriate level |

These thresholds are starting examples. Projects may adjust them according to system criticality, yet must apply the same rule across the entire migration. A security or data-loss risk may have to be treated as release-blocking even when its composite score is low.

### 4.4. Recording Detection Difficulty

Likelihood × Impact helps prioritize, yet two risks with the same score can require different handling. Add a **Detectability** field to record how easily it can be spotted:

| Level | Meaning |
|---|---|
| Easy | Detectable via builds, static analysis, or deterministic automated tests |
| Medium | Requires integration tests, environment tests, or representative data |
| Hard | Surfaces only in rare consumers, real load, special timing, or production |

Detectability can be kept as an additional attribute rather than multiplied into the score. This avoids creating a seemingly precise number that hides real reasons. Hard-to-detect risks need extra runtime observation, canaries, logs, or dedicated test plans.

## 5. Risk Matrix Template for a Java Migration

The table below illustrates how to record risks. Scores are examples to demonstrate evaluation; projects must substitute actual survey data.

| ID | Risk / cause | Impact | L | I | Score | Detectability | Action / required evidence |
|---|---|---|---:|---:|---:|---|---|
| R-01 | New library removes a method called by an old plugin | Plugin fails when running with new library | 4 | 5 | 20 | Hard | Inventory plugins, compare binary APIs, run old plugin with new JAR |
| R-02 | Interface adds an abstract method | Old consumers may hit AbstractMethodError | 3 | 4 | 12 | Medium | Inventory implementations, use default method if suitable, test old implementation classes |
| R-03 | Consumer uses an inlined compile-time constant | Behavior uses stale value after upgrade | 4 | 3 | 12 | Hard | Identify public constants, replace with runtime query if needed, test old clients |
| R-04 | Runtime JDK is lower than class-file target | JVM cannot load new classes | 2 | 5 | 10 | Easy | Verify target release and JDK across all deployment environments |
| R-05 | Transitive dependency resolves a different version | Linkage error or unexpected behavior | 3 | 4 | 12 | Medium | Save dependency graph, verify runtime classpath and integration tests |
| R-06 | JSON field or default value changes | Consumer reads wrong data or drops field | 3 | 5 | 15 | Hard | Contract tests with old/new payloads, check null/defaults and schema |
| R-07 | Timeout or connection pool config changes | Latency, timeouts, or resource exhaustion | 2 | 4 | 8 | Medium | Compare effective config, load tests, and observe metrics |
| R-08 | Database migration change does not support rollback | Cannot safely revert to previous version | 2 | 5 | 10 | Hard | Test restore, verify backward-compatible schema and rollback runbook |

A risk record should contain at least these fields:

- Unique ID.
- Description of cause and trigger condition.
- Affected components and consumers.
- Consequences for the system or business.
- Likelihood, Impact, score, and priority level.
- Current evidence and unknowns.
- Preventive or mitigating measures.
- Test plan and completion criteria.
- Accountable owner.
- Status, due date, and residual risk after handling.

Do not merge different root causes into one row merely to shorten the table. For example, a class-file version error and a NoSuchMethodError have different causes, detection methods, and fixes; they should be separate risks.

## 6. From Risks to Handling Measures

After prioritizing, select verifiable handling measures. Four common strategies are:

| Strategy | When to use | Example |
|---|---|---|
| Risk avoidance | Scope or design can be adjusted to eliminate the error condition | Keep old API in releases that must support old clients |
| Mitigation | Probability or consequence can be reduced via engineering and testing | Keep bridge methods, add binary compatibility checks |
| Transfer / share | Part of the risk belongs to a vendor or another team | Require dependency vendor to confirm supported version |
| Controlled acceptance | Residual risk is within allowed limits and an authorized owner approves | Accept a minor change with tested workaround and rollback |

“Acceptance” does not mean deleting the risk row from the table. Record approver, rationale, scope, effective duration, monitoring conditions, and contingency plan if the risk materializes.

High risks are not automatically solved by adding more tests. Match checks to failure mechanisms:

- Binary API changes: compare APIs and run old bytecode.
- Source compatibility changes: compile consumers from source.
- Behavioral changes: contract and regression tests.
- Serialization or schema changes: test old and new data.
- Runtime changes: verify on the exact JDK, classpath, module path, and deployment config.
- Performance changes: benchmarks or load tests with a baseline.
- Operational changes: deployment, health check, and rollback rehearsals.

## 7. Defining Transition Acceptance Criteria

Acceptance criteria describe concrete conditions that must be met before a transition is deemed complete or allowed past a release stage.

Good criteria must be:

1. **Specific:** identify the component, version, and behavior being verified.
2. **Measurable:** have an outcome or threshold determining pass vs fail.
3. **Reproducible:** others can rerun and gather equivalent evidence.
4. **Scoped:** clearly specify consumers, environments, data, and applicability conditions.
5. **Owned:** clear who confirms the outcome.
6. **Failure-handled:** define how to block, fix, roll back, or request an exception.

Avoid vague phrases like “application runs normally”, “no serious errors”, or “fully tested”. They do not specify which tests to run, against which artifacts, or what evidence is needed.

### 7.1. Build and Source Compatibility Criteria

Examples:

- All modules within migration scope build successfully with the target JDK and build tool.
- No new compilation errors due to API or dependency changes.
- Designated source consumers compile cleanly against the new artifact.
- No outdated dependency versions remain outside the approved exception list.
- Builds are reproducible from the recorded commit and dependency lock or configuration.

Specify the exact build command, commit, JDK, profile, and module list. One command succeeding on a developer laptop is insufficient if the pipeline or deployment environment uses a different configuration.

### 7.2. Binary Compatibility Criteria

This category is critical when the goal is continuing to run already-compiled components without recompiling them.

Examples:

- Public and protected APIs under the supported contract keep required descriptors and visibility, or all breaking changes are listed and approved.
- API comparison tools report no binary breaking changes outside the approved exception list.
- All designated representative consumers compiled against the baseline artifact run with the new artifact in the target environment.
- No linkage errors such as NoSuchMethodError, NoSuchFieldError, AbstractMethodError, IllegalAccessError, or IncompatibleClassChangeError occur in defined test scenarios.
- Old plugins, interface implementations, and extension points load and execute successfully.

Identify old and new artifacts precisely by version or checksum. If a test recompiles the client against the new dependency, that test does not prove binary compatibility.

### 7.3. Business Behavior Criteria

Examples:

- Critical contract tests yield matching results per the agreed specification.
- Critical status codes, exception contracts, side effects, and retry rules remain unchanged or have approved changes.
- Critical business flows complete with representative data.
- No regressions exceed agreed thresholds for latency, throughput, or error rate.
- Intentional behavioral changes have migration notes and tests proving the new behavior.

If a behavior is permitted to change, criteria must explicitly describe the new outcome. Do not force every output to stay identical to the old version if the migration includes an approved business change.

### 7.4. Data and Integration Criteria

Examples:

- Payloads or records created by the old version remain readable during the committed compatibility window.
- Old and new consumers process schemas/messages according to the versioning strategy.
- No unintended missing fields, type errors, timezone shifts, or precision loss.
- Database migrations complete and a recovery plan has been tested.
- APIs, message brokers, file exchanges, and service contracts pass contract tests.

For rolling deployments, test at least the relevant interaction pairs: old app with new data, new app with old data, and concurrent producers/consumers.

### 7.5. Runtime and Operational Criteria

Examples:

- Artifact starts up on the target JDK and target production configuration.
- Health checks, readiness, liveness, and graceful shutdown operate properly.
- Dependencies resolve to exact versions; no duplicate classes or known class loader conflicts.
- Secrets, configurations, and permissions are properly supplied.
- Metrics, logging, and tracing are sufficient to detect post-deployment failures.
- Performance and resource metrics stay within approved thresholds.
- Rollback has been rehearsed or has equivalent recovery evidence.

### 7.6. Documentation and Support Criteria

Examples:

- Lists of breaking changes and deprecated APIs are published.
- Migration guides include examples for consumers needing changes.
- List of consumers confirmed updated or in the supported old-bytecode group.
- Deployment, post-deployment verification, and rollback runbooks are updated.
- Technical owners and operational owners confirm their areas of responsibility.

## 8. Example Set of Acceptance Criteria Usable as Gates

The following criteria illustrate how to translate migration goals into verifiable conditions. Thresholds must be adjusted based on system SLAs and criticality.

| Gate | Pass criteria | Evidence |
|---|---|---|
| G1 — Scope | 100% of known modules, services, plugins, and consumers are classified by impact; unknowns have owners and verification deadlines | Dependency inventory and consumer matrix |
| G2 — API | Zero binary breaking changes outside the approved exception list | Revapi/japicmp report or equivalent tool |
| G3 — Build | 100% of mandatory modules build cleanly on target toolchain | CI run, commit, JDK, and build log |
| G4 — Old bytecode | 100% of designated representative old consumers pass compatibility scenarios; zero linkage errors outside approved exceptions | Artifact checksums, test reports, and runtime logs |
| G5 — Behavior | All critical contract tests pass; regressions within defined thresholds | Test reports, baseline, and comparison results |
| G6 — Data | Old/new data fixtures and schema migrations pass defined read/write scenarios | Data compatibility report and migration tests |
| G7 — Runtime | Application starts, health checks and mandatory integrations work in target environment | Deployment test and observability snapshot |
| G8 — Operations | Rollback or recovery rehearsed; runbooks and on-call owners ready | Rehearsal record and runbook |
| G9 — Approval | High/critical risks resolved or accepted by properly authorized owners | Risk register and approval records |

Criteria can be divided into three statuses:

- **Pass:** sufficient evidence exists and threshold is met.
- **Fail:** evidence shows failure; gate is blocked until resolved.
- **Pending:** evidence is missing or check not yet run. Pending must not be treated as Pass.

A gate passes only when all mandatory criteria for that gate are Pass. If exceptions exist, they must reference the corresponding risk ID, approver, and acceptance conditions.

## 9. Detailed Example: Accepting a Shared Library Replacement

Suppose the system has a **shared-api** version 1 library and multiple consumers:

- Service A is rebuilt as part of the migration.
- Plugin B is precompiled and deployed independently.
- Batch C runs on a schedule only and cannot update simultaneously.
- Several external consumers are managed by other teams.

The goal is releasing **shared-api** version 2 while continuing to support Plugin B and Batch C during the transition period.

### 9.1. Recorded Risks

| ID | Risk | Initial assessment | Handling |
|---|---|---|---|
| R-01 | Version 2 removes a method called by Plugin B | High | Keep bridge method in version 2 |
| R-02 | Version 2 alters an interface implemented by Batch C | High | Inspect old implementation; prefer default method if contract permits |
| R-03 | Version 2 alters output of a shared method | Medium | Contract tests and regression tests on representative data |
| R-04 | External consumers not yet inventoried | Not yet assessable | List consumers and request artifact/version confirmation |

### 9.2. Concrete Acceptance Criteria

| ID | Criterion | Verification method |
|---|---|---|
| AC-01 | Service A builds cleanly with shared-api v2 on target JDK | Run CI build from locked commit |
| AC-02 | Old Plugin B artifact runs with shared-api v2 | Run archived Plugin B JAR alongside v2 JAR; do not recompile Plugin B |
| AC-03 | Old Batch C artifact loads and executes used API call paths cleanly | Run fixture or old batch artifact with new runtime dependency |
| AC-04 | Zero linkage errors across defined scenarios | Collect test logs and inspect for JVM errors |
| AC-05 | Critical contract outputs unchanged outside approved changes | Compare outputs, exceptions, and side effects against baseline |
| AC-06 | External consumers have support confirmation or sit on approved exception list | Store confirmation and owner in consumer inventory |
| AC-07 | Can revert to artifact v1 under verified data and configuration conditions | Rehearse rollback in an equivalent environment |

### 9.3. Mandatory Evidence

A “compatible” conclusion should trace back to:

- Commit and build ID producing shared-api v2.
- Version or checksum of shared-api v1 and v2.
- Version or checksum of Plugin B and Batch C used in tests.
- JDK, build tool, runtime flags, and dependency graph of the run.
- Test reports, startup logs, and logs of executed scenarios.
- Exception list and approval decisions.
- Post-handling risk register, including residual risk.

If Plugin B was recompiled against v2 before testing, AC-02 is not proven. Exact old bytecode must run to prove the goal of not requiring recompilation.

## 10. Linking Risks with Criteria and Evidence

Risks and acceptance criteria must link bidirectionally. Every critical risk must have at least one control or acceptance decision. Every critical criterion must point to the risk or goal it controls.

A management structure that can be used:

~~~text
Risk ID
  -> root cause and impact
  -> mitigation measure
  -> Acceptance Criteria ID
  -> specific test / check
  -> evidence location
  -> Pass / Fail / Pending result
  -> confirming owner
~~~

Example:

| Risk ID | Acceptance Criteria | Check | Evidence |
|---|---|---|---|
| R-01 | AC-02, AC-04 | Run old plugin with new library | Plugin compatibility test report |
| R-02 | AC-03, AC-04 | Run old implementation of interface | Legacy implementation test |
| R-03 | AC-05 | Compare contract output | Regression report |
| R-04 | AC-06 | Cross-check consumer list | Consumer confirmation record |

If a test fails, update the risk status and re-evaluate the score once additional data arrives. Do not mark a risk closed merely because a related test ran; check whether the test actually covers the error-triggering condition.

## 11. Organizing Gates Across Migration Progress

Do not wait until the end of the project to check all criteria. Splitting them into timed gates helps detect flawed assumptions early.

### Gate A — Survey Complete

Exit criteria:

- Module and consumer scope defined.
- Baseline artifacts, toolchain, and runtime saved.
- Dependency inventory and consumer matrix have owners.
- Unknown risks recorded as Pending with a verification plan.
- Compatibility targets and supported consumer groups agreed upon.

### Gate B — Transition Design Accepted

Exit criteria:

- Changed APIs or schemas classified.
- Breaking changes have compatibility plans, adapters, or transition schedules.
- High risks have controls, owners, and verification criteria.
- Test plan covers old consumers, old data, and target runtime.
- Rollback strategy fits code and data changes.

### Gate C — Technical Verification Passed

Exit criteria:

- Build and source compatibility passed.
- Binary compatibility tests with old artifacts passed.
- Mandatory contract, regression, data, and integration tests passed.
- Remaining bugs linked to risk IDs with explicit decisions.
- Evidence report is traceable.

### Gate D — Ready for Deployment

Exit criteria:

- Artifact matching commit and checksum verified.
- Configuration, secrets, runtime, and dependencies verified.
- Canary or rollout strategy prepared if needed.
- Dashboards, logs, alerts, and on-call operators ready.
- Rollback or recovery rehearsed.
- Residual risks accepted by the right owners.

### Gate E — Post-Deployment Confirmation

Completion criteria:

- Health checks and critical business flows pass.
- No new linkage errors or compatibility bugs within the defined observation window.
- Error rate, latency, and resource usage within thresholds.
- Independent consumers confirmed working or have tracked transition plans.
- Emerging risks updated with owners.

The observation window must match real usage cycles. For a daily or weekly batch job, checking immediately after deployment is insufficient to prove the batch is compatible.

## 12. Rollback Decisions and Managing Residual Risk

Rollback must be designed alongside migration, especially when schemas or data change.

Before choosing rollback, determine:

- Are previous version artifacts and configurations still available?
- Is the new database schema still compatible with the old application?
- Can data written by the new version be read by the old version?
- Can already-emitted messages or events be processed by old consumers?
- Are there irreversible actions such as sending payments, dispatching notifications, or deleting data?
- Who has authority to decide rollback and what are the trigger thresholds?

For databases, an expand-and-contract strategy usually reduces risk:

1. Expand the schema in a way the old version keeps working.
2. Deploy new code capable of reading/writing under compatible rules.
3. Migrate data and consumers in stages.
4. Confirm no consumer still uses the old structures.
5. Only then remove old columns, fields, or processing paths.

Do not assume rolling back code equals rolling back data. If new code has written data in a format old code cannot read, reverting to the old binary can break the system further.

Residual risk is the risk remaining after controls have been applied. Re-evaluate likelihood and impact based on new evidence, explicitly record what could not be tested, and set monitoring conditions. If consumer coverage is incomplete, risk cannot be considered eliminated merely because existing tests all Pass.

## 13. Recording Templates Teams Can Adopt

### 13.1. Risk Register Template

~~~text
Risk ID:
Risk name:
Component / consumer:
Root cause:
Trigger condition:
Consequence:
Likelihood (1-5):
Impact (1-5):
Risk Score:
Detectability:
Available evidence:
Unverified items:
Handling measure:
Related Acceptance Criteria:
Test / check:
Owner:
Due date:
Status: Open / Mitigating / Pending / Accepted / Closed
Residual risk:
Approver (if any):
Evidence location:
~~~

### 13.2. Acceptance Criteria Template

~~~text
AC ID:
Criterion name:
Compatibility target:
Module / consumer scope:
Input artifact or version:
Environment and conditions:
Verification action:
Expected result:
Pass threshold:
Fail condition:
Evidence to retain:
Confirming owner:
Related Risk ID:
Applicable gate:
~~~

### 13.3. Exception Decision Template

~~~text
Exception ID:
Risk ID:
Criterion failed or unverifiable:
Reason:
Affected consumer scope:
Impact if it occurs:
Compensating controls:
Monitoring conditions:
Acceptance expiration:
Invalidation conditions:
Authorized approver:
Evidence:
~~~

Exception templates must be used under control. A Pending item due to missing tests must not be switched to Accepted merely to pass a gate. There must be a reason, scope, compensating control, deadline, and accountable owner.

## 14. Checklist for Completing Risk Survey and Acceptance Criteria

- [ ] Identified baseline versions, artifacts, JDK, build tool, and actual runtime.
- [ ] Listed modules, services, plugins, batches, and external consumers.
- [ ] Recorded compile-time, runtime, and independent deployment relationships.
- [ ] Captured baseline APIs and critical extension points.
- [ ] Classified binary, source, behavioral, data, runtime, security, and operational risks.
- [ ] Scored likelihood and impact on a consistent scale.
- [ ] Recorded detection difficulty and missing evidence.
- [ ] Assigned owners, handling measures, and acceptance criteria to critical risks.
- [ ] Added tests running old consumer bytecode with new artifacts.
- [ ] Added appropriate source compatibility, behavioral, data, and runtime tests.
- [ ] Defined Pass, Fail, Pending, and exception conditions.
- [ ] Linked every criterion to concrete tests and evidence.
- [ ] Defined gates, approvers, and rollback conditions.
- [ ] Assessed residual risk prior to deployment and after the observation window.

A risk matrix is useful when it helps the team decide what to test first, who is accountable, and what evidence suffices to proceed. A set of acceptance criteria is useful when any team member can reproduce the check and conclude Pass, Fail, or Pending from the same artifact, environment, and data. When these two parts are linked, migration can be managed with concrete evidence rather than relying on a feeling that the system was test-run and looks okay.
