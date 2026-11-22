# Direct Upgrade or Intermediate Milestones: Selection Criteria

When planning the roadmap for a Java migration, the team must decide whether to move from the current version to the target version in one big step or split it into multiple intermediate milestones. This decision affects change scope, execution time, root-cause isolation when failures happen, testing cost, deployment planning, and rollback safety.

In **Java Advance Compatibility Migration**, under **Versions and Roadmap**, there is no fixed rule that direct upgrades are always faster or sequential upgrades are always safer. The right approach depends on the distance between the two versions, JDK and framework constraints, dependency compatibility, system structure, data, testability, and how much time the organization can allocate to migration.

Crucially, the roadmap must be chosen based on evidence. A large version jump can be reasonable if the upgrade path is supported and the system has sufficient tests. Conversely, an intermediate milestone may be mandatory if a framework, build tool, data format, or vendor requires transitioning in a specific order.

## 1. Two ways to structure a roadmap

### 1.1. Direct upgrade

A direct upgrade moves the system from the current baseline to the target version in a single primary migration wave.

Example:

~~~text
Current state
    Java A
    Framework X
    Dependency set P
        |
        | One migration wave
        v
Target state
    Java C
    Framework Z
    Dependency set R
~~~

The team analyzes changes from A to C, adjusts source code and configuration, updates frameworks/dependencies, and then validates everything on the target state.

"Direct upgrade" does not mean skipping release notes of versions between A and C. A team must still inspect changes, deprecated or removed APIs, toolchain requirements, and migration guides appearing in every intervening release. It only means you do not necessarily have to install, release, or operate the system on every intermediate version.

This approach usually fits when:

- The direct upgrade path is supported by vendors.
- Core components can run on the target version.
- There is no mandatory requirement to pass through a bridge version.
- Source code and dependencies can be adjusted within one controlled scope.
- The system has sufficient tests and environments to verify all changes.
- Supported consumers can be updated or remain compatible with the new API.
- Deployment and rollback can execute within one verified plan.

### 1.2. Upgrading through intermediate milestones

An intermediate-step upgrade splits the path from current version to target version into multiple separately verifiable states.

Example:

~~~text
Java A
   |
   | Milestone 1: handle platform changes
   v
Java B
   |
   | Milestone 2: upgrade framework and dependencies
   v
Java C
   |
   | Milestone 3: finalize configs and runtime tuning
   v
Target state
~~~

Each milestone may encompass a JDK version, framework, build tool, or selected change set. The team verifies builds, tests, and compatibility contracts at each state before advancing to the next milestone.

Not every milestone needs to become a production deployment. A milestone may be only a checkpoint on a migration branch or a test environment. If an intermediate version is not supported for long-term operation, do not assume it must be shipped to production.

This approach usually fits when:

- A vendor requires upgrading through a specific framework or tool version.
- One big jump packs too many breaking changes to handle simultaneously.
- The system has many independent modules, plugins, or consumers.
- Continuous operation must be preserved while teams update on different schedules.
- Data or protocol changes require a transitional compatibility phase.
- The team needs to isolate failure causes per group of changes.
- Intermediate states can be tested and managed reliably.

### 1.3. Distinguish technical milestones from deployment milestones

A roadmap may have multiple technical milestones yet only one production deployment. Conversely, a small technical change may require multiple rollout waves due to a distributed system or consumers unable to update concurrently.

Separate three concepts:

| Concept | Meaning | Example |
|---|---|---|
| Technical version | JDK, framework, build tool, or dependency version | JDK 17, Spring Boot 3.x |
| Verification milestone | Code/config state built and tested to confirm part of migration | Completed compile on new JDK, completed namespace switch |
| Deployment milestone | Release or rollout to a real running environment | Canary, staging, production rollout |

Do not add a production deployment just to get another technical checkpoint. Choose milestone forms based on verifiability, rollback capability, and operational requirements.

## 2. Factors determining the roadmap

Before choosing an upgrade path, evaluate the following factor groups. Each group can be a hard requirement or a factor influencing cost and risk.

### 2.1. Vendor-supported upgrade path

This is the first condition to check.

Some JDKs, frameworks, application servers, plugins, or tools support upgrading directly from an old version to a new version. Others require bridge versions, conversion procedures, or specific upgrade orders.

Verify:

- Official compatibility matrices for the JDK, framework, and application server.
- Minimum versions of build tools and plugins needed to build or run on the target JDK.
- Dependency versions supported by the framework.
- Upgrade guides between major releases.
- Prerequisites that must be completed before upgrading.
- Whether intermediate versions remain supported or are end-of-life.
- Whether ordered upgrades are required for metadata, schemas, configs, or artifacts.

If official documentation mandates an upgrade path, that is a roadmap constraint. Do not skip it just because a small experiment on a developer machine appeared to work.

Also distinguish "supported" from "runs". A version combination may boot yet fall outside the vendor's support matrix. When failures happen, the team may receive neither patches nor necessary support.

### 2.2. Distance between current and target versions

The wider the version gap, the more release notes, deprecations, API removals, and default changes must be surveyed.

However, the number of skipped versions does not by itself dictate how many milestones to install. One project can jump across several major versions directly if vendor-supported and all changes fit one wave. Another project upgrading just one major version may still need multiple checkpoints due to major architectural or data shifts.

List changes from baseline to target:

- Deprecated or removed JDK APIs.
- Module, package, or access-permission changes.
- Bytecode target and runtime requirement changes.
- Default configuration changes.
- Framework extension point changes.
- Dependency and plugin changes.
- Serialization, schema, or protocol changes.
- Garbage collector, concurrency, TLS, or networking behavior shifts where relevant.

If many independent changes land together, consider splitting checkpoints to isolate causes when tests fail.

### 2.3. Magnitude of source code and API changes

Assess the volume and complexity of required edits:

- Does source only need warning cleanup or deprecated API fixes?
- Are removed APIs forcing implementation replacements?
- Is there a broad namespace or package migration?
- Are interfaces, abstract classes, or public APIs changing?
- Do modules use reflection or internal JDK access?
- Are code generators or annotation processors tied to old versions?
- Must multiple modules change together due to circular dependencies or shared contracts?

Localized changes in one module can proceed directly. Changes spanning many independent modules, frameworks, and consumers typically benefit from clearer checkpoints.

### 2.4. Dependency and build tool compatibility

A Java system depends not just on the JDK, but also on frameworks, libraries, build plugins, and supporting tools.

Check:

- Direct and transitive dependencies.
- BOMs, dependency constraints, and version catalogs.
- Gradle wrapper or Maven version.
- Build, test, packaging, code coverage, and static analysis plugins.
- Annotation processors, compiler plugins, and code generators.
- Test frameworks, mocking frameworks, and integration-test tooling.
- Agents, instrumentation, bytecode enhancers, and native libraries.
- Dependencies present only at runtime and absent from the compile classpath.

If the current build tool cannot run on the target JDK, a build-tool upgrade step before source edits may be necessary. If a new framework requires a new dependency major version, evaluate whether integration libraries stay compatible.

Do not upgrade every dependency to the latest version merely because the JDK upgraded. Select versions within the support matrix with concrete justification.

### 2.5. Consumer binary compatibility

This is especially critical for shared libraries, SDKs, plugins, or independently released modules.

Identify:

- Which consumers will be rebuilt?
- Which consumers keep old bytecode untouched?
- Which consumers cannot update simultaneously?
- Did any public APIs change descriptors or access permissions?
- Do old classes implement new interfaces?
- Do consumers use reflection, ServiceLoader, or class names in config?
- Are compile-time constants inlined into bytecode?

If old consumers must keep running without recompiling, test the exact pre-compiled baseline artifacts against the new dependency. Rebuilding all consumers checks only source compatibility, not binary compatibility.

### 2.6. Data and cross-version communication

Distributed systems usually cannot update all producers and consumers at the exact same moment.

Evaluate:

- Does the database schema change?
- Does the JSON/XML or message schema change?
- Do old producers and new consumers understand each other?
- Do new producers and old consumers understand each other?
- Can data written by the new version be read by the old version?
- Are caches, sessions, or serialized objects shared across versions?
- Are there irreversible data migrations?

If old and new versions must coexist for a period, intermediate milestones can preserve bidirectional compatibility. In such cases, design schemas using an expand-and-contract strategy or suitable versioning.

### 2.7. System scale and coordination capability

A simple application owned by one team upgrades directly more easily than a system of many services, plugins, and consumers managed by multiple teams.

Evaluate:

- Number of impacted modules and services.
- Number of teams owning consumers.
- Ability to deploy concurrently.
- Release cadence of each component.
- Time required for regression testing.
- Ability to provision isolated staging or test environments.
- Observability and error-tracing capability.
- Readiness of operations owners.

If a consumer runs only on a weekly schedule, a short rollout window may not even exercise it. The roadmap must account for actual consumer cadences.

## 3. Comparing advantages and costs of both approaches

| Criterion | Direct upgrade | Through intermediate milestones |
|---|---|---|
| Number of change waves | Fewer waves | More waves |
| Overall management duration | Can be shorter when scope is simple | Can be longer due to validating each milestone |
| Change scope per wave | Large | Smaller if split well |
| Isolating regression cause | Harder when many changes happen together | Easier to localize per milestone |
| Testing | Needs comprehensive suite at target state | Needs per-milestone tests plus final integration tests |
| Dependency management | Can update centrally | Can adjust per group |
| Temporary compatibility needs | Can have fewer intermediate states | May need to support multiple version combinations |
| Rollback | Can be simple before irreversible data changes | Must manage rollback states at each milestone |
| Multi-team coordination | May require large-scale synchronization | Can divide work, yet must manage interfaces between milestones |
| Cumulative risk | Many changes can obscure causes | Can catch early, yet adds transition points |
| Intermediate version | No need to operate if direct path is valid | Must choose milestones with fitting purpose and support |

Do not conclude that more milestones always mean lower risk. Every milestone adds a state to build, test, configure, store artifacts for, and potentially maintain compatibility with. If an intermediate milestone brings neither new insight nor better control, it only raises cost.

Conversely, do not choose a direct upgrade solely to minimize release count. If one jump bundles inseparable changes, the team may spend far longer debugging and recovering.

## 4. Hard constraints and trade-off criteria

To avoid gut-feel decisions, separate hard constraints from optimization trade-offs.

### 4.1. Hard constraints

If any condition below is unmet, the corresponding path must not be chosen until resolved:

- Vendor does not support a direct path and mandates passing through a bridge version.
- Current build tool or framework cannot run or migrate directly per support docs.
- Schema migrations must execute in strict sequence.
- An intermediate artifact must be produced to convert formats or metadata.
- An API or protocol cannot run old and new states concurrently while rolling deployments are mandatory.
- The target state cannot be tested reliably until dependencies or toolchains resolve at a prior milestone.
- Operational policy or vendor support mandates a specific intermediate state.

When hitting a hard constraint, record its confirming source, applicable versions, and the consequence of skipping it.

### 4.2. Trade-off criteria

Absent hard constraints, compare options by:

- Total time and engineering effort.
- Change magnitude per milestone.
- Ability to pinpoint regression causes.
- Ability to keep legacy consumers running.
- Cost of creating and maintaining environments.
- Number of build, test, and release cycles.
- Rollback feasibility.
- Team readiness.
- Remaining support life of the current version before EOL.
- Operational cost if an intermediate version must be maintained.

A sound decision states which criteria matter most to the system, rather than mechanically summing scores without grasping severity.

## 5. Decision framework

Use the following workflow to pick a direct upgrade or intermediate-step upgrade.

### Step 1: Lock baseline and target

Record:

- Current JDK and target JDK.
- Current and target framework/application server.
- Current and target build tool and plugins.
- Critical dependencies and supported versions.
- Artifacts and consumers that must keep working.
- Source, binary, behavioral, and data compatibility goals.
- Support deadline or required completion date.

Do not pick a target merely because it is the newest release. Consider support lifecycles, framework compatibility, deployment environments, and maintenance plans.

### Step 2: Gather official upgrade paths

Read migration docs and release notes for versions between baseline and target.

Build a table:

| Component | Baseline | Target | Major changes | Ordering requirements |
|---|---|---|---|---|
| JDK | Current version | Target version | APIs, bytecode, runtime, modules | Per JDK docs |
| Framework | Current version | Target version | APIs, config, extension points | Per framework guide |
| Build tool | Current version | Target version | Wrapper, plugins, compiler | Per compatibility matrix |
| Dependencies | Current version set | Target version set | APIs and transitive graph | Per BOM/vendor |
| Data/schema | Current schema | Target schema | Read/write, migration, rollback | Per data plan |

Document supported paths and pre-upgrade prerequisites. If docs describe only adjacent steps, do not assume intermediate steps can be skipped.

### Step 3: List changes and classify severity

For each change, assess:

- Scope of affected files/modules.
- Is it a breaking change?
- Can it be handled independently?
- Are old consumers impacted?
- Can a reproducible test be written?
- Does it depend on other changes?
- Does it require data or config changes?

Suggested classification:

| Tier | Description | Examples |
|---|---|---|
| Small | Localized change, verifiable quickly | Updating warnings or obsolete settings |
| Medium | Affects a few modules or APIs | Replacing deprecated APIs, upgrading build plugins |
| Large | Affects many modules or contracts | Major framework shift, namespace migration |
| Very large | Affects architecture, data, or many independent consumers | Breaking schema change, changing runtime/container model |

Classification must reflect dependency graphs and consumer inventories, not merely changed line counts.

### Step 4: Identify hard constraints

If a rule mandates passing through an intermediate version or state, put it in the roadmap first. Do not try to minimize milestones by violating an official support requirement.

If no hard constraint exists, compare costs and risks of both paths.

### Step 5: Run a small technical spike

Before deciding for the entire system, pick a representative module whose dependencies and runtime pattern resemble the real system.

The spike should check:

- Building with the target JDK and build tool.
- Compiling source against target dependencies.
- Running existing tests and several critical business flows.
- Loading plugins or extensions if the system uses them.
- Running consumers compiled against older library versions if binary compatibility is required.
- Checking config, serialization, and representative data.
- Recording errors, edit volume, and resolution time.

A spike need not replace the entire migration. Its goal is reducing uncertainty before committing to a roadmap. Pick a representative module carrying realistic risk; a trivial module can create a false sense of security.

### Step 6: Compare options and record the decision

Draft at least two options:

- Option A: direct upgrade from baseline to target.
- Option B: stepping through required intermediate milestones.

For each option, document:

- Support conditions.
- Changes required.
- Top risks and controls.
- Required environments and tests.
- Number of releases or checkpoints.
- Estimated timeline and assumptions.
- Rollback feasibility.
- Which consumers need updating and when.

Then document the rationale for the chosen option. If data is still insufficient, the decision may be "undecided" paired with spikes or audits to finish.

## 6. Reference selection matrix

The table below helps spot signals favoring each approach. This is qualitative guidance; hard constraints and empirical evidence remain decisive.

| Observed criterion | Favors direct upgrade | Favors intermediate milestones |
|---|---|---|
| Official upgrade path | Direct path supported | Bridge version mandated |
| Framework | Supports target, clear migration guide | Major releases require sequential transition |
| Build tool | Wrapper/plugins can upgrade in same wave | Old tools cannot execute transition steps |
| APIs | Few breaking changes, small scope | Many API removals or changed extension points |
| Old consumers | Updatable or fully binary-tested | Independent consumers, cannot update concurrently |
| Data | Schema and protocol stay compatible | Requires expand/contract or multi-stage changes |
| Code scope | Focused, clear dependencies | Many modules and cross-dependencies |
| Testing | Comprehensive target tests available | Needs checkpoints to isolate changes |
| Rollback | Prior artifacts/configs safely restorable | Needs transitional compatible state |
| Resources | Team can handle simultaneous changes | Need to split work across teams and time |
| Support deadline | Completable in one wave | Need to de-risk staggered multi-team releases |

High-priority signals:

- A mandatory vendor requirement outweighs aggregate score.
- A critical consumer that cannot update may force retaining APIs or adding adapters.
- An irreversible data migration can dictate deployment order.
- A system lacking reliable tests needs uncertainty reduction before sweeping changes.

## 7. Scoring model to compare options

If both approaches are viable, teams may score them to clarify trade-offs. Scores do not replace engineering judgment; they surface assumptions and rationale.

### 7.1. Choose criteria and weights

Example weighting scale:

| Criterion | Example weight | Interpretation |
|---|---:|---|
| Compatibility safety | 30% | Ability to preserve API, binary, behavioral, and data contracts |
| Verifiability | 20% | Ability to detect and isolate failures via tests/evidence |
| Rollback capability | 15% | Ability to revert to a prior working state |
| Total effort | 15% | Coding, testing, coordination, and operational effort |
| Time to completion | 10% | Ability to meet deadlines and support windows |
| Operational complexity | 10% | Number of states to maintain and monitor |

Weights total 100%. Projects may adjust weights, yet must agree before scoring.

### 7.2. Score each option

Use a 1–5 scale where 5 is most favorable. For "total effort", higher means less effort; for "operational complexity", higher means easier to operate.

Formula:

~~~text
Weighted Score = Sum(criterion_score x criterion_weight)
~~~

Illustrative example:

| Criterion | Weight | Direct | Intermediate milestones |
|---|---:|---:|---:|
| Compatibility safety | 30% | 3 | 4 |
| Verifiability | 20% | 3 | 5 |
| Rollback capability | 15% | 4 | 4 |
| Total effort | 15% | 5 | 3 |
| Time to completion | 10% | 5 | 3 |
| Operational complexity | 10% | 4 | 3 |
| **Weighted score** | **100%** | **3.70/5** | **3.90/5** |

In this example, the intermediate approach scores higher due to verifiability. However, if a hard constraint forbids direct upgrade, scoring is unnecessary to pick intermediate milestones. Conversely, if direct upgrade is supported, well-tested, and extra milestones reduce no risk, direct upgrade may be better.

Never use scores to mask a severe risk. For example, data-loss risk must not be offset by a high time-savings score.

## 8. Roadmap selection examples in Java scenarios

The examples below illustrate the reasoning process. Real versions and support matrices must be verified against each framework, vendor, and dependency's documentation.

### 8.1. Small internal library with centrally managed consumers

Suppose a library has few public APIs, serves only a few internal services within the same organization, and every consumer can be rebuilt.

Characteristics:

- Small, known dependency graph.
- No external plugins.
- No schema or protocol conversion needed.
- Sufficient unit/integration test coverage.
- Framework and build tool directly support the target.

The roadmap can be a direct upgrade:

1. Freeze the baseline artifact.
2. Upgrade JDK/build tool/dependencies to target.
3. Update source and config.
4. Rebuild all consumers.
5. Run regression and integration tests.
6. Verify runtime and roll out.
7. Archive evidence and release decision.

There is no need to cut a production release for every intermediate JDK unless a support or compliance rule requires it. Even so, still read release notes of skipped versions.

### 8.2. Application spanning multiple framework major releases

Suppose an application uses a large framework with config and extension-point changes across multiple major releases. Some integration libraries support the new framework only after upgrading to a bridge version.

An intermediate roadmap can fit:

~~~text
Old framework
    |
    v
Milestone A: handle deprecated APIs/configuration
    |
    v
Milestone B: upgrade to supported bridge version
    |
    v
Milestone C: update extensions and dependencies
    |
    v
Target framework
~~~

At each milestone:

- Check support matrices.
- Build and test impacted modules.
- Record changed configurations.
- Test integration adapters.
- Verify consumers and plugins.
- Advance only when the milestone gate passes.

Not every milestone must deploy to production. If milestones can stay in branches and test environments, teams can still isolate failures without creating long-lived operational states.

### 8.3. Broad namespace or API transition

Major framework migrations may change packages, APIs, or component discovery mechanisms. For example, migrating from legacy Java EE to Jakarta EE can impact imports, annotations, servlet APIs, validation, persistence, dependencies, and configuration.

In this case, audit:

- Every namespace in use.
- Whether integration libraries support the target namespace.
- Whether plugins and code generators still emit the old source.
- Whether any artifacts must upgrade first to support the new namespace.
- Whether dependency updates can be separated from source conversion.
- Whether any consumers must keep running on the old namespace.

If dependencies or frameworks provide an official bridge step, use that milestone. If everything can update cleanly on one branch and pass full tests, direct migration may still be viable. Base the decision on the dependency inventory and a real spike.

### 8.4. Public library with independently compiled plugins

Suppose an SDK is consumed by multiple organizations. Some plugins may not be recompiled for months.

Here, binary compatibility may outweigh minimizing milestones. The roadmap needs to:

1. Capture the binary API baseline.
2. Inventory extension points and legacy implementations.
3. Preserve bridge methods or adapters where possible.
4. Run old plugin artifacts against the target library.
5. Release a transitional compatibility version if needed.
6. Announce deprecations and API removal timelines.
7. Move to breaking releases only with consumer policy and confirmation.

An intermediate release can serve as a transitional compatibility release, yet only when it has a clear purpose and long enough support. Never create temporary releases solely to add steps.

### 8.5. System with database migrations and rolling deployment

If the new app alters schemas while old instances still run during rollout, design the roadmap so both versions coexist throughout transition.

Example:

~~~text
Schema v1 + Application v1
          |
          v
Expand schema: v1 + new column
          |
          v
Application v2 reads/writes compatibly
          |
          v
Migrate data and consumers
          |
          v
Verify old structure is no longer used
          |
          v
Contract schema: remove old structure
~~~

This is a sequence of data and deployment milestones. It may be necessary even when the JDK and framework upgrade directly. Java version roadmaps and schema roadmaps should be managed separately yet coordinated together.

## 9. Common mistakes when choosing a roadmap

### 9.1. Ignoring intermediate release notes

Choosing a direct upgrade does not mean ignoring intermediate releases. An API may be deprecated in an earlier version and removed in the target version. Reading only target guidance risks missing prerequisites or default shifts introduced earlier.

Fix: list release notes and migration guides from baseline to target; flag changes impacting the system.

### 9.2. Upgrading everything at once without a baseline

Upgrading JDK, framework, build tool, and all dependencies in one commit makes root-causing failures hard. When tests fail, the team cannot tell whether bytecode, APIs, config, plugins, or dependencies broke.

Fix: record baseline and group logically coupled changes. Even with a direct upgrade, separate commits or test checkpoints per group.

### 9.3. Creating too many unnecessary milestones

Each milestone adds build, test, artifact, configuration, and coordination cost. If a milestone satisfies no support requirement, reduces no uncertainty, and yields no new evidence, it lacks sufficient value.

Fix: every milestone must state its purpose, entry preconditions, exit criteria, and permitted post-milestone decision.

### 9.4. Deploying an end-of-life intermediate version

An intermediate version may aid technical transition while being unsuitable for production. If it must deploy, confirm its support lifecycle and intended lifetime.

Fix: separate test checkpoints from production milestones. Deploy intermediate versions only with clear operational justification and time bounds.

### 9.5. Checking only source compatibility

A passing build after recompiling every module does not prove legacy plugins or consumers still work.

Fix: retain baseline artifacts and execute old bytecode against the new library. Test legacy implementations of interfaces, plugins, and service providers.

### 9.6. Overlooking schedules of batch consumers

A weekly batch job may not run during a short rollout window. The system looks healthy until the next scheduled run fails.

Fix: include batch schedules in acceptance criteria and observation windows. Trigger tests proactively with representative artifacts and data.

### 9.7. Treating code rollback as full-system rollback

If the new version altered schemas, wrote new formats, or emitted events unreadable by the old version, rolling back binaries may not restore service.

Fix: assess rollback separately across code, config, databases, messages, and external side effects; rehearse before deployment.

### 9.8. Picking a target merely because it is newest

The newest version may lack full support from frameworks, application servers, plugins, or deployment platforms.

Fix: select targets based on support windows, ecosystem compatibility, maintainability, and operational requirements. Record rationale for target choice.

## 10. Designing checkpoints and exit criteria per milestone

If choosing an intermediate path, each milestone needs a verification contract. Do not name a milestone purely by version without stating the target state to achieve.

Milestone definition template:

| Field | Content to record |
|---|---|
| Milestone ID | Unique ID, e.g., M1 |
| Baseline | Input versions and artifacts |
| Target state | JDK/framework/build/dependencies after milestone |
| Scope | Relevant modules, consumers, and environments |
| Changes | Source, config, dependency, or data edits |
| Preconditions | Requirements before starting |
| Acceptance criteria | Verifiable Pass conditions |
| Evidence | Build IDs, test reports, artifact checksums, logs |
| Rollback | How to revert to pre-milestone state |
| Owner | Responsible person |
| Decision | Go / No-Go / Pending |

Example:

| Milestone | Goal | Exit criteria |
|---|---|---|
| M0 — Baseline | Freeze current state | Artifacts, dependency graph, test baseline, and consumer inventory saved |
| M1 — Toolchain | Build with target toolchain | Wrapper/plugins supported, compile and basic tests pass |
| M2 — API/framework | Complete API and framework edits | Zero compile errors; binary/API checks pass |
| M3 — Runtime/data | Verify runtime and data | Integration, serialization, schema, and health checks pass |
| M4 — Release candidate | Confirm final state | Regression, performance, rollback, and approvals pass |

This is only an example structure. If the system has no data or framework changes, do not invent matching milestones just to fill the table.

### 10.1. Go / No-Go rules

A milestone can be evaluated with three statuses:

- **Go:** all mandatory criteria Pass and evidence is archived.
- **No-Go:** any criterion Fails or unresolved risk exceeds threshold.
- **Pending:** insufficient data or checks not yet run. Pending never counts as Go.

Waiver decisions require a risk ID, impact scope, compensating control, expiration date, and authorized approver.

### 10.2. Do not equate a checkpoint with a release

Checkpoints can be created via:

- Commits or tags on a migration branch.
- Dedicated CI artifact builds.
- Integration test environments.
- API compatibility reports.
- Test suites with old consumers.
- Configuration and dependency-graph snapshots.

Cut a release or production rollout only when conditions require testing factors that earlier environments cannot represent.

## 11. Planning tests across the roadmap

Whichever path is chosen, the test plan must cover the target state. An intermediate roadmap adds checks at checkpoints; it does not replace final validation.

### 11.1. For direct upgrades

A test plan may include:

1. Build baseline to ensure a reproducible starting point.
2. Freeze baseline artifacts and dependency graph.
3. Apply changes toward target.
4. Run compilation, unit tests, and static analysis.
5. Run source compatibility tests for rebuilt consumers.
6. Run binary compatibility tests against legacy consumers.
7. Run integration, contract, and regression tests.
8. Verify data migrations, runtime, performance, and security.
9. Test rollout and rollback in an equivalent environment.
10. Verify acceptance criteria before release.

### 11.2. For intermediate-step upgrades

Beyond final checks, each milestone requires:

1. Confirming the prior milestone's baseline.
2. Applying only the current milestone's change set.
3. Building and testing against the milestone's acceptance criteria.
4. Archiving artifacts, configs, and reports.
5. Assessing failures and updating the risk register.
6. Making a Go/No-Go decision.
7. Advancing only once entry conditions are satisfied.

Once the target is reached, re-run the final integration suite. Individual passing milestones do not guarantee the full final combination operates properly.

### 11.3. Selecting representative consumers

If there are multiple consumers, group them by how they use the API:

- Consumers that only call standard public APIs.
- Consumers that implement interfaces or extend abstract classes.
- Consumers that use reflection or annotations.
- Dynamically loaded plugins.
- Consumers that use serialization or share schemas.
- Consumers running on a different JDK or environment.
- Consumers running on a schedule or with specific workloads.

Select at least one representative for each distinct risk group. If real artifacts cannot be obtained for an important consumer group, document the limitation and residual risk level.

## 12. Dependency management and upgrade order

Upgrade order should follow the dependency graph and support matrix.

A reference sequence:

~~~text
1. Baseline and inventory
          |
          v
2. Check JDK/build tool/plugins
          |
          v
3. Upgrade toolchain sufficient to build the target
          |
          v
4. Upgrade frameworks and dependencies per support matrix
          |
          v
5. Update source, configuration, and extension points
          |
          v
6. Verify consumers, data, and runtime
          |
          v
7. Release candidate, rollout, and observation
~~~

The actual order may differ. For example, a build plugin may require a new JDK to run while the compiler target can still emit bytecode for an older version. Or a framework may require upgrading dependencies before changing the JDK. Rely on official documentation and testing; do not apply the diagram as a rigid rule.

Track separately:

- The JDK used to run Gradle/Maven.
- The compiler/toolchain JDK used to compile source.
- The **--release**, source compatibility, and target bytecode options.
- The application runtime JDK.
- JDKs in containers, CI, and production.
- Actually resolved framework and dependency versions.

A build succeeding on a new JDK while producing target bytecode incompatible with the deployment runtime can still fail at runtime. Conversely, an older bytecode target does not guarantee the application will run if source or dependencies use APIs available only in newer JDKs.

## 13. Managing branches, artifacts, and rollback capability

During a long-running migration, state management matters as much as upgrade order.

### 13.1. Save a reproducible baseline

Save:

- Source commits.
- Released artifacts.
- Checksums.
- Dependency graph or lockfile.
- JDK and build tools.
- Runtime configuration.
- Baseline test results.
- Schemas and data snapshots if policy permits.

Do not rely on an old build directory of unknown origin. Artifacts must be traceable to their commit and build process.

### 13.2. Managing migration branches

A dedicated migration branch can be used for major changes, provided you define:

- Which branch is the source of truth.
- How bug fixes are synced from the main branch.
- Merge conditions.
- How release candidates are built.
- How to handle a cancelled milestone.
- How to avoid keeping multiple branches on different dependency versions for too long.

When splitting into multiple checkpoints, tags or commits can record achieved states. There is no need to create a long-lived branch for every milestone.

### 13.3. Layered rollback

Rollback must evaluate:

| Layer | Question |
|---|---|
| Application artifact | Can old JARs/images be restored? |
| Runtime/JDK | Is downgrading the runtime still platform-supported? |
| Configuration | Can configs and feature flags be restored? |
| Dependency | Do old artifacts still resolve the exact old dependencies? |
| Database | Are new schemas and data compatible with old code? |
| Messaging | Are new events/messages understood by old consumers? |
| External side effects | Have any irreversible actions already occurred? |

If rollback is unsafe after a data step, mark the checkpoint following that step as a point of no simple return. In that case, a recovery or forward-fix plan is mandatory.

## 14. Recording the roadmap selection decision

A migration decision should be clear enough for others to understand why the team chose direct upgrade or intermediate-step upgrade.

Decision record template:

~~~text
Decision ID:
Date:
Decision maker:
System / module:
Baseline:
Target:
Compatibility goals:

Option A - Direct upgrade:
- Supported upgrade path:
- Key changes:
- Impacted consumers:
- Tests and evidence:
- Risks:
- Timeline/effort:
- Rollback:

Option B - Intermediate steps:
- Milestones:
- Rationale for each milestone:
- Support path:
- Consumers at each milestone:
- Tests and evidence:
- Risks:
- Timeline/effort:
- Rollback:

Hard constraints:
Trade-offs:
Spike performed:
Spike results:
Chosen option:
Rationale:
Residual risks:
Re-evaluation conditions:
Approver:
Evidence location:
~~~

If choosing intermediate steps, each milestone must have a clear purpose. If choosing direct upgrade, the decision must record why an intermediate state is unnecessary and what evidence proves the direct path is controllable.

## 15. Checklist before locking the roadmap

### Scope and goals

- [ ] Baseline and target locked for JDK, framework, build tool, and dependencies.
- [ ] Supported consumers and source/binary/behavior/data compatibility requirements identified.
- [ ] Baseline artifacts, checksums, and dependency graph saved.
- [ ] Support deadlines and operational goals identified.

### Upgrade path

- [ ] Migration guides and release notes read from baseline to target.
- [ ] Official compatibility matrices checked.
- [ ] Bridge version requirements or mandatory ordering identified.
- [ ] Changes classified by scope and severity.
- [ ] API, configuration, module, bytecode, and runtime changes checked.

### Comparing options

- [ ] Direct upgrade and intermediate-step upgrade described.
- [ ] Hard constraints separated from trade-offs.
- [ ] Each intermediate milestone has a goal, inputs, outputs, and Go/No-Go criteria.
- [ ] No milestones or releases created merely to increase step count.
- [ ] Technical spike run on a representative module where major uncertainty remains.
- [ ] Rationale for selection and assumptions recorded.

### Testing and operations

- [ ] Source compatibility tests exist for consumers that must be rebuilt.
- [ ] Binary compatibility tests exist for legacy consumers that must keep running.
- [ ] Suitable contract, regression, data, and integration tests exist.
- [ ] Build JDK, compiler target, and runtime JDK confirmed.
- [ ] Rollout, observation, and rollback plans defined.
- [ ] Owner and evidence assigned for each gate.
- [ ] Residual risks recorded with acceptance decisions.

A sound roadmap is one that satisfies supported upgrade paths, reduces uncertainty at genuine risk points, and generates adequate evidence before transitioning states. Direct upgrade fits when the path is clear, scope is manageable, and target testing is strong. Intermediate milestones fit when they resolve ordering requirements, isolate major changes, or create necessary checkpoints for consumers, data, and operations. Decisions should be recorded alongside assumptions and re-evaluation conditions so the team can adjust when investigations uncover new information.
