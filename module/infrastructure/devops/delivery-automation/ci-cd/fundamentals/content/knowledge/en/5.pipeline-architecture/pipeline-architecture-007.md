# Separating Fast Checks from Resource-Intensive Checks

A good CI/CD pipeline must quickly answer whether a change is heading in the right direction while still running sufficiently deep checks to protect release quality. These two objectives carry different costs. Formatting checks, static analysis, and unit tests generally run fast with minimal environment dependencies. End-to-end tests, load tests, multi-service integration tests, or comprehensive security scans can require substantial CPU, memory, time, specialized runners, and shared resources.

Putting every check into one mandatory flow for every pull request update slows down feedback and grows CI queues. Removing heavy checks from all decision gates lets critical defects slip further before discovery. Pipeline architecture must tier work by cost and risk, choose the right execution timing, and clearly specify which checks must block merging, which must pass before release, and which can run on a schedule.

This lesson explains how to separate fast checks from resource-intensive checks, organize them into lanes and jobs with dependency relationships, allocate runners, optimize feedback time, and measure effectiveness without weakening quality gates.

## 1. Understanding the two groups of checks

**Fast checks** have short execution times, low resource costs, or high stability, and can typically run on every pull request. They catch common errors early and provide feedback quickly enough while the developer still remembers the change clearly.

Examples:

- Formatting, style convention, and lint checks.
- Static analysis or type checking.
- Unit tests.
- Building small modules or building the application with basic configuration.
- Configuration, schema, and file validity checks.
- Detecting committed secrets and checking dependencies within changed scope.
- Certain fast-running contract tests or component tests.

**Resource-intensive checks** consume significant time or compute resources, require multiple dependent services, large datasets, specialized environments, or many configuration variants.

Examples:

- Integration tests spinning up multiple services, databases, or message brokers.
- System and end-to-end tests across multiple business flows.
- Testing across multiple runtime versions, operating systems, browsers, or CPU architectures.
- Load tests, stress tests, soak tests, and benchmarks.
- Comprehensive security scans across repositories, container images, or dependency graphs.
- Building many large modules or producing multiple artifact types.
- Migration testing against large dataset copies.
- Backward-compatibility and regression testing across the entire product.

The boundary is not defined solely by minutes. A two-minute job requiring a specialized device, exclusive environment, or multiple shared services can still carry high operational cost. Conversely, a longer-running job using predictable CPU and memory might fit into an extended check tier without needing special runners.

Therefore, when classifying a check, consider duration, CPU, memory, I/O, dependent service count, resource wait time, environment cost, and result criticality.

## 2. Architectural goal: fast feedback and deep verification

The architecture should establish two complementary capabilities:

1. **Fast feedback loop:** catch high-probability, low-cost defects as soon as a pull request is created or updated.
2. **Extended verification loop:** run deep checks on relevant changes, shared branch state, release builds, or on a schedule.

Overview diagram:

~~~mermaid
flowchart TD
    A["Pull request / commit update"] --> B["Fast lane"]
    B --> C{"Fast checks passed?"}
    C -- "No" --> D["Report errors to author"]
    D --> A
    C -- "Yes" --> E["Analyze change scope"]
    E --> F["Targeted heavy checks"]
    F --> G{"Risk-required checks passed?"}
    G -- "No" --> D
    G -- "Yes" --> H["Review and merge"]
    H --> I["Shared branch pipeline"]
    I --> J["Full integration / regression"]
    J --> K["Build and store artifact"]
    K --> L["Environment verification"]
    M["Scheduled trigger"] --> N["Full matrix / load / scan"]
    N --> O["Report and create follow-up tasks"]
    P["Release request"] --> Q["Release validation"]
    Q --> R{"Release gates passed?"}
    L --> R
    O --> R
    R -- "Passed" --> S["Promote and deploy"]
    R -- "Failed" --> T["Halt release, investigate"]
~~~

The diagram shows a reference model. Not every project needs full load tests or a full matrix before every release. Actual gates must reflect product risk, operational requirements, and release policy.

The key point is that each group of checks has a **deadline by which it must complete**. If a security or compatibility check is mandatory for release, running it on a schedule is not enough to replace a pre-release gate. Conversely, a long-running benchmark tracking performance trends can run periodically without blocking every pull request.

## 3. Classifying checks by cost and risk

You can start with the following classification table and adjust based on actual repository metrics:

| Check Type | Typical Cost | Appropriate Timing | Gate Role |
|---|---|---|---|
| Format, lint, config check | Low | Every pull request | Usually mandatory before merge |
| Static analysis, type check | Low to medium | Every pull request | Mandatory per policy |
| Unit tests | Low to medium | Every pull request and main branch | Usually mandatory |
| Build application or affected modules | Medium | Pull request and main branch | Mandatory if outputs require building |
| Component tests | Medium | Pull request based on change scope | Mandatory for relevant components |
| Multi-service integration tests | Medium to high | Selective pull request, post-merge | Mandatory before release if covering critical risks |
| Full-system end-to-end tests | High | Main branch, staging, or release candidate | Blocks release according to criticality |
| Cross-browser / cross-platform matrix | High | Pull request on UI changes, main branch, or schedule | Minimal matrix pre-merge, expanded later |
| Full security scan | Medium to high | Main branch and pre-release | Mandatory gate per risk policy |
| Load / stress / soak tests | High to very high | Pre-release, scheduled, or on performance changes | Blocks release when performance thresholds are mandatory |
| Migration testing on large datasets | High | Schema-related pull requests, staging, or release | Mandatory before sensitive data changes |
| Full regression suite | High | Main branch, nightly, or release candidate | Gate per release strategy |

This table is a starting point, not a rigid rule. For instance, a small library project might run its entire test suite in a few minutes and not need multiple lanes. A multi-service system may need per-service test selection and a full suite on the main branch.

### 3.1. Assessing actual cost

To avoid guessing, collect:

- Job p50 and p90 execution times, not just averages.
- Runner queue wait time before the job starts.
- CPU, peak memory, and disk usage.
- Number of services, containers, or virtual machines required.
- Data seeding and environment cleanup durations.
- Job failure rates broken down by product bugs, flaky tests, and infrastructure errors.
- Cost or quota limits for runners and external services.
- Severity of impact if a check is deferred to a later stage.

Execution time and queue wait time are distinct metrics. A job might run for only three minutes yet wait twenty minutes in the queue due to pool capacity limits. Optimizing only test code will not fix that real bottleneck.

### 3.2. Do not equate fast checks with low-importance checks

A fast check can be a critical safeguard, such as secret detection, license verification, or blocking banned dependencies. A heavy check can also be a mandatory pre-release requirement, such as migration testing or load testing for a transactional service.

Classify along two separate axes:

- **Execution cost:** low, medium, or high.
- **Controlled risk level:** low, medium, or high.

A high-cost, high-risk check must be optimized to run selectively where targeted, given adequate resources, and placed before the appropriate decision gate. Never drop it from the workflow merely because it takes long to run.

## 4. Organizing a pipeline into lanes

A lane is a workflow stream with a relatively clear objective and resource profile. A lane does not have to be a standalone pipeline; it can be a group of stages or jobs within the same workflow.

### Fast lane

The fast lane receives new changes and runs quick-feedback checks. Its goal is answering early whether the change is fit to continue toward review and integration.

Typically, the fast lane includes:

- Source checkout and safe cache restoration.
- Formatting, lint, and configuration checks.
- Static analysis and type checking.
- Unit tests.
- Fast builds or building affected modules.
- Fast blocking security checks.

The fast lane should have tight timeouts, readable logs, and clear check statuses. When a foundational step fails, the pipeline must distinguish source errors from runner or dependent-service errors.

### Targeted lane

The targeted lane runs resource-intensive checks limited to affected areas or specific risks. For instance, a change in the payments module can trigger payments integration tests, contract tests with orders, and related end-to-end flows.

This lane avoids running the entire system for every change. Scope selection must rely on dependency graphs, module configurations, change labels, or managed rules. When safe scope cannot be determined, the pipeline should fall back to the broader defined suite.

### Full validation lane

The full validation lane runs broad checks on shared branch states or release candidates. It can include full regression, system-wide integration tests, runtime matrices, and deep security scans.

This lane often runs post-merge, on a schedule, or pre-release. Checks designated as release gates must finish before promoting artifacts to target environments.

### Scheduled lane

The scheduled lane runs tasks that do not need to block every pull request, such as:

- Full regression on the main branch.
- Load and soak tests.
- Scheduled comprehensive dependency scans.
- Testing across multiple runtime versions or platforms.
- Long-term compatibility checks and benchmarks.
- Detecting upward trends in build times or performance regressions.

Scheduled lane results must be monitored with clear ownership. If a failure is detected without triggering alerts or remediation tasks, periodic runs provide no real protective value.

### Release lane

The release lane validates a specific release candidate. It must check the exact artifact intended for deployment, metadata, signatures or provenance where applicable, environment configuration, acceptance tests, and operational criteria.

Do not rely solely on results from a pipeline run on a similar commit. Match commit SHA and artifact digest to verify that the tested build is the exact build being released.

## 5. Designing dependency relationships in a DAG

Modern pipelines typically execute jobs via a dependency graph (DAG). Independent jobs can run in parallel; a job starts only once its input conditions are ready.

Example:

~~~mermaid
flowchart TD
    A["Checkout + prepare dependencies"] --> B["Lint / static analysis"]
    A --> C["Unit tests"]
    A --> D["Build changed modules"]
    B --> E{"Fast gate"}
    C --> E
    D --> E
    E --> F["Select test scope"]
    F --> G["Integration test service A"]
    F --> H["Integration test service B"]
    F --> I["Contract tests"]
    G --> J{"Targeted gate"}
    H --> J
    I --> J
    J --> K["Review / merge"]
    K --> L["Full regression"]
    K --> M["Security scan artifact"]
    L --> N["Release candidate gate"]
    M --> N
    N --> O["Publish / promote artifact"]
~~~

Several principles when building a DAG:

- Declare real dependencies between jobs; do not chain them sequentially just for convenience.
- Run independent checks in parallel when runners and dependent services have capacity.
- Prevent heavy jobs from starving runners needed by the fast lane.
- Use aggregator gates to explicitly define continuation criteria.
- When a mandatory job fails, stop jobs depending on that result.
- Allow collecting logs and reports from completed jobs even when another job fails.
- Never allow publish or deploy steps to run when mandatory checks have not passed.

Parallelism does not always make pipelines faster. If multiple jobs concurrently spin up databases, pull images, or call a shared sandbox, total time can increase due to resource contention. Measure both total duration and per-job wait time after changing concurrency levels.

## 6. Example pipeline configuration across resource tiers

The example below is a conceptual model illustrating how lanes, triggers, and resource classes are partitioned. It is not executable syntax for GitHub Actions, GitLab CI, or Jenkins:

~~~yaml
pipeline:
  pull_request:
    fast_lane:
      runner: standard
      required: true
      timeout: short
      jobs:
        - lint
        - static_analysis
        - unit_tests
        - build_affected_modules

    targeted_lane:
      runner: integration
      required_when: affected_services_detected
      timeout: medium
      jobs:
        - affected_integration_tests
        - contract_tests
        - focused_end_to_end_tests

  push_to_shared_branch:
    validation_lane:
      runner: integration
      required_before_artifact: true
      jobs:
        - full_integration_tests
        - regression_subset

    package_lane:
      needs: [validation_lane]
      runner: standard
      jobs:
        - build_release_artifact
        - calculate_digest
        - publish_artifact

  schedule:
    full_validation:
      runner: high_memory
      cadence: nightly
      jobs:
        - full_regression_matrix
        - cross_platform_tests
        - dependency_full_scan

    performance:
      runner: performance
      cadence: weekly
      jobs:
        - load_tests
        - stress_tests
        - soak_tests

  release:
    release_gate:
      needs: [package_lane]
      runner: integration
      jobs:
        - verify_artifact_provenance
        - release_acceptance_tests
        - deployment_smoke_tests
~~~

In real implementations, replace runner names, triggers, and conditions with your platform's exact configuration. In particular, do not treat fields such as `required`, resource classes, or `cadence` in this example as standard syntax.

## 7. Selecting checks by change scope

Selective testing runs only checks relevant to modified source code. This is a key technique for cutting time and cost, especially in monorepos or multi-service systems.

Scope can be determined by:

- Changed file paths.
- Module or service owning the file.
- Inter-module dependency graph.
- Labels or metadata on the pull request.
- Test mappings linked to components.
- Analysis of API, schema, or deployment configuration changes.

For example, UI-only changes might trigger lint, UI unit tests, and selected browser tests. Shared library changes might trigger tests for all dependent modules. Pipeline, build script, or dependency lockfile changes may require running a broader scope.

### 7.1. Building an impact map

An impact map might define:

| Changed Area | Checks to Trigger |
|---|---|
| UI module | UI unit tests, component tests, browser smoke tests |
| Public API | Contract tests, consumer integration tests |
| Shared library | Dependent module tests and related full builds |
| Database schema | Migration tests, integration tests, version compatibility |
| Build config or dependencies | Broader build and test suites |
| Dockerfile or container base image | Image build, image scan, container smoke tests |
| Pipeline or deployment scripts | Config checks, pipeline validation, safe deploy dry-runs |
| Unable to determine impact area | Run broad test suite per policy |

### 7.2. Avoiding missed checks from path filters

Simple path filters can miss risks if they overlook:

- Shared modules or transitive dependencies.
- Global configuration files.
- Build scripts and plugins.
- Generated code or schemas used across multiple places.
- Changes in CI/CD workflows.
- Dependency lockfiles or toolchain versions.
- Renamed, moved, or deleted files.

Fallback rules are essential. If the tool cannot determine impact, if the dependency graph fails, or if changes touch foundational layers, run the broader suite. Time optimization must never rely on assuming every change can be classified perfectly.

### 7.3. Combining selection with mandatory gates

Some checks may run only when relevant areas change. However, "did not need to run" must remain distinct from "ran and passed." Dashboards or summary checks should clearly show why a job was skipped, what scope was evaluated, and which rules applied.

For high-risk changes, reviewers may be required to confirm test scope or trigger additional suites. Govern this mechanism carefully so arbitrary labels cannot become a way to bypass checks.

## 8. Runner allocation and resource limits

Runners are the machines or environments executing CI jobs. Separating runner pools prevents heavy jobs from slowing down fast-feedback checks.

A reference allocation model:

| Runner Group | Characteristics | Suitable Work |
|---|---|---|
| Standard | Moderate CPU and memory, fast startup | Lint, static analysis, unit tests, small builds |
| Integration | Supports containers and multiple dependent services | Integration tests, contract tests, component tests |
| High-memory / large CPU | High compute resources | Full regression, large builds, data analysis |
| Performance | Stable environment, low noise, controlled resources | Load tests, stress tests, benchmarks |
| Specialized | Dedicated devices, runtimes, or specific platforms | Mobile, GPU, cross-platform, or hardware tests |

Not every organization needs multiple physical runner types. You can use shared infrastructure with distinct CPU, memory, concurrency, and queue limits. What matters is ensuring the fast lane retains enough capacity for quick feedback during peak hours.

### 8.1. Controlling concurrency

If heavy jobs grow unchecked, the system may suffer:

- Runner exhaustion and growing queue wait times.
- CPU or memory starvation on runner hosts.
- Overloaded databases, registries, or test services.
- Data collisions between jobs.
- Rising cloud costs or quota breaches.
- Noisy benchmarks caused by co-located jobs.

Set concurrency limits per resource group, cap concurrent ephemeral environments, and use dedicated queues for performance workloads. Jobs needing reliable performance measurements should run in environments with controlled background load.

### 8.2. Isolating environments and data

Each integration job should have its own data or namespace wherever possible. If multiple jobs write to the same test database, outcomes become erratic and hard to reproduce. Create minimal fixtures, clean up data after tests, and set timeouts for dependent services.

For load tests, never share environments with standard functional tests because synthetic load can skew functional outcomes or disrupt other jobs.

## 9. Optimizing speed while preserving reliability

### Parallelizing by dependency

Split tests into independent shards or groups. An aggregation job waits for mandatory results. This works well when a large suite can be partitioned without sharing mutable state.

### Sharding by historical duration

Do not split solely by test count if individual test durations vary widely. Use historical execution times to balance shard workloads evenly. Monitor the slowest shard, as it usually determines when the gate completes.

### Using accurately keyed caches

Caching dependencies and build outputs can cut execution times significantly. Cache keys should include inputs affecting outputs, such as lockfiles, toolchain versions, build configurations, and operating systems. Never reuse stale cache when inputs have changed.

Cache is a performance optimization, not a source of truth. When investigating an error suspected to be cache-related, pipelines should support running cleanly without cache for comparison.

### Reusing artifacts and environments

If downstream steps only test the same output, build once and pass artifacts between jobs. Avoid rebuilding with differing configurations in each lane. For test environments, standardized images or snapshots can be used when isolation is guaranteed.

### Canceling obsolete work

When a pull request receives a new commit, jobs for the older commit can be canceled if no longer valuable. However, retain jobs serving active investigations or confirmed release tasks. Cancellation rules must prevent old jobs from overwriting the state or environment of newer jobs.

### Avoiding unbounded retries

Retries are appropriate only with evidence of transient infrastructure errors or when tests are designed to be retry-safe. For flaky tests, record retry counts, initial outcomes, and final outcomes. A job passing only after multiple retries is still a signal requiring investigation.

### Reducing initialization work

Use standardized dependency services, pre-built images, minimal fixtures, and reusable setup routines. Avoid downloading large datasets or reinstalling identical tools in every job when versioned runner images can provide them.

## 10. Placing quality gates at the right time

Splitting lanes only works when the team clearly defines criteria to advance.

| Gate | Timing | Example Criteria |
|---|---|---|
| Fast gate | Before review/merge | Mandatory lint, static analysis, and unit tests pass |
| Targeted gate | Before merge for impacted changes | Relevant integration or contract tests pass |
| Integrated gate | Post-merge | Build and tests on shared branch commit pass |
| Artifact gate | Before publish/promote | Valid artifact with digest and metadata |
| Release gate | Before target deployment | Risk-aligned full tests, scans, and required approvals pass |
| Runtime gate | Post-deployment | Health checks, smoke tests, and operational metrics within thresholds |

Some checks can run at multiple gates with different scopes. For example, a pull request runs contract tests for the modified API; post-merge runs contract tests against all consumers; pre-release adds backward-compatibility checks.

Never equate a scheduled job running with a gate passing. If a full security scan is a mandatory release condition, the release pipeline must verify the latest valid result tied to the exact artifact or commit. If the result is stale or inputs changed, re-run it.

## 11. Security when using runners for heavy checks

Some integration tests require network access, privileged containers, cloud services, or secrets. Heavy jobs must not automatically receive elevated permissions simply because they require more compute resources.

Apply these principles:

- Grant least-privilege permissions per job.
- Separate runners for untrusted source code from runners holding deployment permissions.
- Never expose production secrets to pull request pipelines from forks or untrusted sources.
- Restrict runner network and write permissions during tests.
- Use short-lived credentials if supported by the platform.
- Tear down temporary environments and revoke credentials once the job finishes.
- Log access and runner image versions for auditing.

If testing requires production-like data, use anonymized/sanitized datasets compliant with data policy. Never copy secrets or sensitive data into CI environments merely for test convenience.

## 12. Handling failures and flaky results

When the fast lane fails, feedback should pinpoint the failing step and link to the current commit. Developers need to know whether they can fix the defect immediately or whether an operator needs to inspect the runner.

When targeted or full validation fails, assess the blast radius and whether the failure blocks merge, publish, or release. A heavy check can fail for several reasons:

- Functional bugs that surface only when services interact.
- Unready test environment or invalid test data.
- Runner running out of CPU, memory, or disk space.
- Dependent service rate-limited or unreachable.
- Flaky tests caused by timing, ordering, or shared state.
- Performance regressions breaching agreed thresholds.

Logs should record commit, pipeline run, test shard, environment configuration, resource class, and queue wait time. This helps separate product defects from infrastructure failures.

For flaky tests, assign an owner and a remediation deadline. If a test must temporarily be removed from a gate, the exception needs a justification, scope, and restoration date. Never quietly turn a mandatory check into a permanent non-blocking warning.

## 13. Measuring pipeline architecture effectiveness

To see whether separating lanes works, measure speed, cost, and quality together:

| Metric | Meaning | Warning Sign |
|---|---|---|
| PR feedback time p50/p90 | Time to receive fast gate results | Rising p90 may indicate runner queuing or slow jobs |
| Queue wait time | Time waiting for a runner | High values indicate insufficient capacity or poor pool allocation |
| Job duration p50/p90 | Actual execution time | Lengthening jobs may need sharding or setup optimization |
| Runner utilization | Resource usage level | Too high causes queuing; too low indicates over-provisioning |
| Cache hit rate | Rate of valid cache reuse | Low rates may come from overly volatile cache keys |
| Flaky test rate | Rate of unstable tests | High rates erode gate trustworthiness |
| Compute cost per change | CI cost per change | Rapid growth may indicate redundant runs or oversized matrices |
| Heavy-check detection rate | Critical defects caught in extended lanes | Unusually low values may indicate test coverage gaps |
| Defect escape rate | Defects reaching later environments or users | Review test scope and execution timing |

Do not chase shorter pipeline durations at all costs. A good architectural change must improve feedback speed while maintaining or strengthening detection of critical defects. Likewise, do not judge purely by summed job durations: ten two-minute parallel jobs can consume more resources than one ten-minute job.

## 14. Sample scenario: multi-module monorepo

Suppose a monorepo houses three groups: API, web UI, and a shared library. A pull request edits only UI CSS.

An un-tiered pipeline might build every module, spin up all services, run the full end-to-end suite, and scan the entire runtime matrix on every update. Feedback slows down even though most checks are unrelated to the change.

A tiered architecture can work as follows:

1. Fast lane runs formatting, lint, static analysis, UI unit tests, and the UI build.
2. Change analysis confirms modifications stay within UI, touching neither the shared library nor the API.
3. Targeted lane runs UI component tests and selected browser smoke tests.
4. Once the pull request passes and merges, the main branch pipeline runs integration tests between the UI and the API deployed in a test environment.
5. Full regression and cross-browser matrix run on a schedule or before release candidates.
6. If a pull request edits the shared library, the dependency graph expands scope to API and UI; if impact cannot be determined, the pipeline runs the broader test suite.
7. Artifacts are built from the verified integration commit and promoted across environments.

This organization reduces irrelevant work for small changes while keeping broad checks at the right moments. If a change touches a critical business flow, the targeted lane may still need to run relevant end-to-end tests before allowing merge.

## 15. Implementation roadmap

You can apply this to an existing repository in steps:

1. **Inventory checks:** collect all existing jobs, their objectives, execution times, queue times, resource usage, and risk levels.
2. **Classify:** label each as fast, targeted, full, scheduled, or release; document the rationale and which gate it protects.
3. **Build the fast lane:** group fast, stable checks required for every change into an early feedback stream.
4. **Separate runners:** define pools or resource classes for integration, full regression, and performance tests.
5. **Build the dependency graph:** declare which modules, services, and tests are impacted by each source area.
6. **Add the targeted lane:** run heavy checks scoped to changes, with a fallback when impact cannot be determined.
7. **Organize full validation:** run comprehensive tests on shared branches, on schedule, or pre-release per policy.
8. **Configure gates:** specify which checks must pass before merge, publish, and target environment deployment.
9. **Measure before and after:** compare PR feedback p50/p90, queue wait, runner cost, flake rate, and escaped defects.
10. **Run failure drills:** introduce a defect visible only in integration or performance tests, confirming the pipeline halts at the right step and preserves sufficient evidence.

### Completion criteria

Learners can consider the practice complete when they can demonstrate:

- Distinguishing execution cost from a check's risk level.
- Classifying fast, targeted, full, scheduled, and release checks.
- Designing a DAG for independent and dependent jobs.
- Allocating runners and setting appropriate concurrency limits.
- Selecting tests by changed area with safe fallbacks.
- Placing quality gates properly before merge, publish, and release.
- Optimizing caching, sharding, and environments while keeping results trustworthy.
- Measuring pipeline feedback time, queue time, cost, and stability.

## Conclusion

Separating fast checks from resource-intensive checks is an architectural decision about feedback timing, execution capacity, and risk. The fast lane gives developers early signals. The targeted lane focuses resources on impacted changes. Full validation and scheduled lanes verify the system broadly. The release lane ensures the exact artifact passes required criteria before reaching target environments.

When lanes have clear goals, inputs, resources, dependencies, and decision gates, pipelines deliver faster feedback while preserving verification depth. Effectiveness must be validated through metrics on duration, queuing, cost, stability, and escaped defects, then tuned to your product's actual architecture and risk profile.
