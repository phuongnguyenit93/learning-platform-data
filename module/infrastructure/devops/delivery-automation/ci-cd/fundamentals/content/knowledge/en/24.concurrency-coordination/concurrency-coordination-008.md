# Bounding Concurrency by Resource and Dependency Capacity

## 1. Why Do Pipelines Need Concurrency Limits?

CI/CD frequently accelerates delivery by running multiple jobs simultaneously: building multiple modules, testing across multiple runtime versions, running security scans, packaging multiple images, or deploying multiple services. Parallelism reduces wait time, yet every job consumes resources and may call shared dependencies such as databases, package registries, container registries, cloud APIs, test environments, or secret management systems.

If the number of concurrent jobs exceeds runner or dependency capacity, pipelines can actually slow down instead of speeding up. Runners starved of CPU/memory prolong builds; many jobs downloading dependencies together trigger registry throttling; hundreds of integration tests generating data overload the database; multiple deployments updating one environment simultaneously cause conflicts or state overwrites.

Bounding concurrency means controlling how many tasks are allowed to execute at the same time. Limits must be derived from resource capacity and dependency load tolerance, while balancing speed, stability, fairness, and cost.

The goal is not to run the fewest jobs possible. The goal is to maintain high enough parallelism to use resources efficiently without pushing runners or dependencies into overload.

## 2. Distinguishing Concurrency Layers

A pipeline can have multiple layers of concurrent execution. Setting a limit solely at the workflow level still lets child jobs or other pipelines consume resources together.

| Layer | Scope | Example |
|---|---|---|
| Organization/global | Entire organization or runner fleet | Maximum 80 running CI jobs |
| Project/repository | A single project or repository | Maximum 12 pipelines in the repository |
| Pipeline/workflow | Stages/jobs belonging to one run | Build and lint running in parallel |
| Job/step | A single job or group of operations | Maximum 4 test workers inside one job |
| Matrix/fan-out | Variants generated from one job | Testing across 5 JDKs × 3 OSes |
| Resource/dependency | A shared resource or service | Maximum 6 integration tests sharing a database |
| Environment/deployment | A deployment target environment | Only one release writing to production at a time |

These layers must work in concert. For example, capping a repository at 20 jobs does not protect the test database if each job spawns 10 test workers. Actual database concurrency could hit 200.

## 3. Calculating Actual Concurrency from Fan-Out

When a pipeline fans out work, the final task count can be far larger than the pipeline count.

For example:

- 8 pipelines running.
- Each pipeline has 3 parallel test jobs.
- Each test job spawns 4 workers.

The configured maximum number of concurrent test workers can reach:

\[
8 \times 3 \times 4 = 96
\]

If each worker opens 3 database connections, theoretical connection load can reach 288 connections—before even counting the application under test, migration jobs, and other services.

When calculating parallelism, account for fan-out at the workflow, matrix, job, test framework, and child-process layers. A cap applied solely to runner job counts can miss the true concurrency multiplying inside each job.

## 4. Deriving Limits from Runner Capacity

Runners have finite CPU, memory, disk I/O, network bandwidth, and process/file descriptor limits. Suitable job counts depend on the consumption profile of each workload type.

| Resource | Overload symptoms | Impact on pipelines |
|---|---|---|
| CPU | Sustained high CPU, long run queues, rising steal time | Slow compilation/tests, timeouts |
| Memory | RAM nearly full, swapping, or OOM kills | Killed builds, evicted caches, flaky tests |
| Disk I/O | High I/O wait, deep disk queues | Slow checkouts, dependency extraction, and packaging |
| Disk capacity | Workspace/cache full | Jobs fail writing files or uploading artifacts |
| Network | Saturated bandwidth, packet loss | Slow dependency/image pulls and API calls |
| Process/file descriptors | OS limits reached | Inability to spawn processes, sockets, or files |

Never use CPU count as the sole limit. A compile job may be CPU-bound; an integration test job may use little CPU while holding many database connections; a container build job may consume heavy memory and disk I/O.

## 5. Estimating Concurrent Jobs from CPU and Memory

An initial estimate can divide usable resources by the average or conservative per-job consumption:

\[
C_{cpu} = \left\lfloor \frac{CPU_{usable}}{CPU_{per\ job}} \right\rfloor
\]

\[
C_{memory} = \left\lfloor \frac{Memory_{usable}}{Memory_{per\ job}} \right\rfloor
\]

The initial runner limit should not exceed the tightest resource constraint:

\[
C_{runner} \leq \min(C_{cpu}, C_{memory}, C_{io}, C_{network})
\]

For example, a runner has 16 vCPUs and 32 GiB of RAM. After reserving resources for the OS, agent, and daemons, about 13 vCPUs and 26 GiB remain. If a build job uses roughly 3 vCPUs and 5 GiB of RAM under load, the CPU-based estimate is 4 jobs and the memory-based estimate is 5 jobs. CPU is the tighter limit, so you can start at 3 jobs to preserve headroom and measure in practice.

This is only a starting point. Usage varies with cache hit rates, project size, test parallelism, and background load. Measure p50/p95 CPU, memory, I/O, and duration under real load before raising limits.

## 6. Reserving Headroom for the System and Load Spikes

Never allocate 100% of theoretical capacity to jobs. Runners need headroom for the OS, agent, container runtime, logging, security/antivirus agents, and short spikes.

Principles:

- Reserve a fixed CPU/memory baseline for the OS and agent.
- Never plan solely around average usage if jobs exhibit sharp peaks.
- Monitor OOM events, swap usage, I/O wait, and queue wait times.
- Offload heavy workloads like image builds, browser tests, or load tests to dedicated pools.
- Bound workspace disk usage and clean temporary data over the job lifecycle.
- Reserve a slice of capacity for high-priority or incident-response jobs if the organization needs it.

If runners share hosts with developers or other services, factor in non-CI load. If ephemeral runners spin up on demand, limits also depend on cloud quotas, provisioning speed, image startup time, and cost.

## 7. Bounding by Dependent Services

Healthy runners do not mean dependencies can withstand arbitrary parallelism. Many jobs may concurrently call a service whose quota or capacity is lower than the runner fleet's.

| Dependency | Limits to consider | Consequences when exceeded |
|---|---|---|
| Package registry | Request rate, download bandwidth, connection count | HTTP 429, timeouts, slow dependency downloads |
| Container registry | Pull/push quotas, concurrent uploads, storage | Throttling, push/pull failures |
| Test database | Connection limit, CPU, IOPS, lock contention | Connection refused, slow queries, flaky tests |
| Cloud API | Request quotas by account/region/resource | Rate limiting, API errors |
| Secret manager | Request rate, token issuance quota | Jobs fail to retrieve credentials |
| Kubernetes API | API Priority and Fairness, request rate, admission webhooks | Slow applies or throttling |
| Shared test environment | Shared mutable state, data, or ports | Tests overwrite data, nondeterministic outcomes |
| External sandbox | Partner quotas, test account limits | Rejected requests or locked accounts |

Dependency limits must be managed separately from runner limits. For example, you might allow 20 build jobs to run simultaneously while permitting only 5 jobs to hit the integration database at once.

## 8. Calculating Parallelism from Service Quotas

For dependencies enforcing requests-per-second quotas, estimate aggregate request rate across all active jobs.

If each job generates an average of $R_{job}$ requests/second and the dependency allows $R_{limit}$, the theoretical maximum parallelism is:

\[
C_{dependency} \leq \left\lfloor \frac{R_{limit}}{R_{job}} \right\rfloor
\]

For example, a partner sandbox permits 40 requests/second. An active integration test worker generates an average of 5 requests/second. The theoretical cap is 8 workers. Accounting for other traffic, burst limits, or retries, set the limit lower—say 5 or 6 workers—and measure.

Quotas may be enforced per token, project, account, IP, region, or endpoint. Identify the exact quota scope. If 3 repositories share one cloud account, independent per-repository limits can sum up and breach the account-wide quota.

## 9. Using Semaphores or Concurrency Groups for Shared Resources

A semaphore limits how many tasks may enter a resource region simultaneously. A semaphore of capacity 1 acts as an exclusive lock; a capacity greater than 1 allows a bounded number of concurrent tasks.

For example, multiple pipelines can build in parallel while at most 3 jobs run integration tests against the shared database:

~~~text
semaphore: shared-integration-db
capacity: 3

job:
  acquire: shared-integration-db
  run: integration-tests
  release: shared-integration-db
~~~

This pseudocode illustrates the concept. Real systems may use resource groups, concurrency groups, distributed locks, queues, or orchestration plugins. Ensure permits are released on job cancellation, runner death, or timeout; use leases/TTLs and safeguards against stale jobs writing after lease expiration.

Avoid applying a global lock across all jobs when only a small dependency needs throttling. Lock the exact resource and size capacity to its capability to avoid needlessly reducing concurrency.

## 10. Exclusive Locks for Deployment Environments

A shared environment may not tolerate multiple simultaneous deployments—for example, two pipelines updating staging at once, concurrent migrations, or a cleanup job deleting another job's resources.

In those cases, use a concurrency group or environment lock:

- Only one deployment mutates an environment at a time.
- Define policy when a newer release arrives while an older release is running.
- Cancel the older job, queue, or reject the newer job depending on environment type.
- Cover the entire conflicting sequence—deploy, migration, smoke tests, and cleanup if they share state.
- After acquiring the lock, verify the release/commit remains authorized for deployment.

For example, production typically requires serializing workload mutations and migrations. Meanwhile, read-only verification jobs can run concurrently if they do not disturb shared resources or data.

## 11. Queues and Backpressure

When arriving jobs outnumber executable slots, the system needs a queue. Queues absorb bursts and help bound concurrency, yet queuing alone cannot solve sustained capacity shortages.

Backpressure slows down or limits producers when receivers can no longer process safely. In CI/CD, backpressure can include:

- Capping the number of pipelines created or admitted to run.
- Capping jobs waiting for runner allocation.
- Scaling down matrix fan-out when registries or test environments are busy.
- Pausing low-priority jobs when dependencies cross saturation thresholds.
- Returning retryable statuses when quotas throttle.
- Using bounded queues with explicit rejection/expiration policies.

An unbounded queue can turn a short burst into hours-long waits, tie up quotas, and leave CI results stale by the time jobs run. Track queue depth, oldest job age, wait time, and cancellation rate for obsolete work.

## 12. Fairness and Priority Across Pipelines

With a strict FIFO queue, long jobs can block short jobs; always prioritizing new jobs can starve older jobs. If one repository floods the queue, it can monopolize runners and stall other projects.

Common mechanisms:

| Mechanism | How it works | Suitable when |
|---|---|---|
| FIFO | Earlier arrivals run first | Simple systems with steady load |
| Per-project quota | Each project gets its own cap | Preventing one project from starving others |
| Weighted fair queue | Splits capacity by weight | Teams with differing priorities or demands |
| Priority class | Critical jobs jump ahead | Hotfixes, security patches, production releases |
| Aging | Boosts priority over wait time | Preventing starvation |
| Separate pools | Splits runners by workload type | Browser tests, image builds, trusted releases |

Priorities must be clearly defined. Never let every job carry the `urgent` label, or priority becomes meaningless. Also reserve baseline capacity for standard jobs so high-priority jobs do not completely stall regular development flow.

## 13. Matrix Builds and Controlled Fan-Out

Matrices test across combinations of runtimes, operating systems, databases, or configurations. However, a large matrix can spawn dozens or hundreds of jobs in a single run.

Example:

~~~yaml
strategy:
  matrix:
    java: [17, 21]
    os: [linux, windows, macos]
    database: [postgres, mysql]
  max-parallel: 4
~~~

This matrix has 2 × 3 × 2 = 12 combinations. `max-parallel: 4` bounds how many combinations run simultaneously within that matrix job according to platform semantics. It does not bound other pipelines or child workers spawned inside each job.

Ways to control fan-out:

- Set `max-parallel` or an equivalent cap.
- Run a fast test subset on every commit and the full matrix on schedule or pre-release.
- Use matrix `include`/`exclude` to drop low-value combinations.
- Run smoke tests on representative combinations before expanding.
- Shard tests while capping total worker count.
- Stop remaining variants early upon hitting a blocking failure if policy allows.

Never trim a matrix so aggressively that supported platforms go untested. Use historical failure data, usage share, and compatibility risk to select mandatory combinations.

## 14. Parallel Coordination Between Builds and Tests

Not every step must run sequentially. Independent jobs can run in parallel, while dependent jobs wait for upstream outputs.

Example:

~~~mermaid
flowchart TD
    A[Checkout revision] --> B[Compile / build]
    B --> C[Unit tests]
    B --> D[Static analysis]
    B --> E[Dependency scan]
    C --> F[Quality gate]
    D --> F
    E --> F
    F --> G[Package and publish]
    G --> H[Integration test]
    G --> I[Image scan]
    H --> J[Release candidate gate]
    I --> J
~~~

Running independent checks in parallel cuts total duration. However, if all jobs download dependencies, start databases, or invoke scanners simultaneously, downstream dependencies can suffer bursts. Add caches, mirrors, semaphores, or staggered starts to smooth load.

Distinguish DAG concurrency from infrastructure concurrency. Just because a DAG allows 10 jobs to run in parallel does not mean runners or dependencies can handle all 10 at once.

## 15. Database Connection Limits and Contention

Integration tests often overload databases because each test worker may open its own connection pool, transactions, and shared datasets.

When designing limits:

- Estimate connections per process and total connections across all jobs.
- Reserve connections for applications, migrations, monitoring, and administration.
- Use separate databases/schemas per job when feasible.
- Cap worker concurrency inside the test framework.
- Avoid running concurrent migrations against the same schema.
- Clean test data by namespace or appropriate transaction rollbacks.
- Monitor lock waits, deadlocks, query latency, connection pool usage, and IOPS.
- Enforce timeouts so tests never hold locks indefinitely.

For example, a database has a 200-connection limit. Reserving 80 for apps and background services, 20 for admin/monitoring, and 30 for headroom leaves at most roughly 70 connections for CI. If each test worker holds 5 connections, the theoretical cap is 14 workers; start lower to leave headroom for bursts and auxiliary connections.

Never simply raise `max_connections` to hide overload. Raising the limit increases database memory pressure and worsens query contention. Diagnose whether the bottleneck is CPU, I/O, locks, or connections before tuning.

## 16. API and Registry Request Limits

External services often return `429 Too Many Requests`, quota exceeded errors, or wait-duration headers. Pipelines must follow protocol backpressure instead of retrying immediately.

Practices:

- Read and honor `Retry-After` when provided by the API.
- Use exponential backoff with jitter so jobs do not retry in lockstep.
- Bound maximum retry attempts and total wait time.
- Never retry authentication errors or non-idempotent requests as transient errors.
- Cache dependencies and use registry mirrors where appropriate.
- Bound global concurrency to the account quota, not merely per repository.
- Separate read-only requests from write/publish requests if quotas differ.

Retries can amplify load while a service is already overloaded. If 100 jobs all receive 429 and retry after exactly 1 second, they trigger a fresh burst. Jitter spreads retry timing; semaphores/backpressure reduce outgoing request volume upfront.

## 17. Coordinating Timeouts, Cancellation, and Retries with Concurrency

Concurrency control must work alongside timeouts and cancellation. A hung job continues holding slots, connections, or locks and stalls other jobs.

Each layer needs appropriate timeouts:

- Job timeout: bounds total execution duration.
- Step timeout: bounds single operations such as downloads or deployments.
- Network timeout: bounds connections and responses.
- Lock wait timeout: prevents waiting forever for a semaphore.
- Test timeout: catches hung tests or deadlocks.
- Shutdown grace period: lets processes clean up before termination.

When cancelling a job, terminate child processes and release resources. Never merely mark a job `canceled` in the UI while runner processes keep executing and hitting dependencies.

Retries must be bounded and distinguish transient failures from deterministic failures. A build failing due to a compile error should not retry; throttled requests can retry with backoff; timed-out deployments must inspect actual state before resending because the first attempt may have partially applied.

## 18. Preventing Retry Storms and Thundering Herds

A retry storm happens when many jobs simultaneously retry a failing dependency, increasing load and blocking recovery. A thundering herd occurs when many clients wake up or hit a resource at the exact same instant.

Mitigations:

- Exponential backoff with full jitter or equal jitter from a proven library.
- Bounded retry counts and overall deadlines.
- Circuit breakers to pause calls to a dependency suffering continuous failures.
- Queuing requests instead of holding large numbers of waiting jobs.
- Reducing concurrency when error rates or throttling spike.
- Staggering nightly/full-matrix schedules.
- Caching shared results or artifacts where correctness allows.

A circuit breaker does not replace a retry policy. It halts repeated calls when evidence shows a dependency is failing; after a cooldown period, controlled probe requests test whether the dependency has recovered.

## 19. Adaptive Concurrency and Signal-Based Tuning

Static limits are simple to operate, yet may underutilize capacity during off-peak hours or underprotect during load shifts. Adaptive concurrency adjusts parallelism based on observed signals.

Signals to monitor:

- Runner pool CPU/memory utilization and queue depth.
- Job wait time and execution time.
- Dependency HTTP 429/5xx rates, timeouts, and latency.
- Database connection usage, lock waits, and query latency.
- Registry throughput and error rates.
- Cloud quota or capacity signals.

A simple policy:

1. Start from a measured conservative concurrency baseline.
2. Step up gradually when latency/errors are stable and headroom exists.
3. Back off quickly when throttling, timeouts, or saturation cross thresholds.
4. Hold steady between adjustments to avoid oscillation.
5. Enforce hard min/max bounds and rate-of-change limits.

Never let individual repositories tune independently if they share a single quota. The coordinator needs global load visibility or partitioned group quotas. For smaller setups, static limits are often more predictable and sufficient.

## 20. Estimating Queues and Wait Times

When jobs arrive faster than they finish, queue depth grows. Little's Law is commonly used to relate average work in the system, throughput, and time in the system:

\[
L = \lambda W
\]

Where:

- $L$: average number of jobs in the system (running and/or waiting, depending on measurement boundary).
- $\lambda$: average throughput—jobs completed or arriving per unit time in steady state.
- $W$: average time a job spends in the system.

For example, if the system completes an average of 30 jobs per hour and holds an average of 15 jobs in the system, average total time from entry to exit is roughly 0.5 hours under steady state.

This is an average-case relationship; it does not accurately predict p95 queue wait when job durations vary widely or arrivals are bursty. Measure queue wait, execution time, throughput, and job age separately. If queues grow continuously, simply raising concurrency does not always help: the bottleneck may be a dependency or one long job type.

## 21. Splitting Pools by Workload Type

A shared runner pool can be monopolized by heavy workloads. Splitting pools bounds the right resources and prevents noisy-neighbor interference.

Example:

| Pool | Workload | Bounding strategy |
|---|---|---|
| General CI | Lint, unit tests, small builds | Many jobs, moderate CPU/memory limits |
| Large build | Monorepo builds, large container images | Fewer jobs, high disk/memory |
| Browser test | E2E browsers, multiple browser processes | Bounded by RAM and browser count |
| Integration | Tests using shared databases/brokers | Semaphore keyed to dependency |
| Release/deploy | Artifact publishing and production deployments | Dedicated permissions, environment locks |
| Untrusted PR | Code from forks or untrusted contributors | Ephemeral runners, restricted network/secrets |

Separate pools improve resource control but can create idle capacity in one pool while another queues. If your platform supports it, use dynamic quotas or autoscaling pools while still preserving global limits on shared dependencies.

## 22. Example Multi-Layer Concurrency Configuration

A conceptual pipeline can place limits at the workflow, matrix, and shared-resource levels:

~~~yaml
workflow:
  maxConcurrentRuns: 6

jobs:
  unit-tests:
    matrix:
      java: [17, 21]
    maxParallel: 3

  integration-tests:
    resourceGroup: shared-test-database
    maxConcurrent: 2
    timeout: 30m

  deploy-staging:
    resourceGroup: staging-environment
    maxConcurrent: 1

  deploy-production:
    resourceGroup: production-environment
    maxConcurrent: 1
    approvalRequired: true
~~~

This is generic pseudocode, not the exact syntax of GitHub Actions, GitLab CI, Jenkins, or any specific engine. In real systems, map each limit to the appropriate concurrency group, resource group, lock, runner pool, or plugin.

Intended outcomes:

- No more than 6 concurrent workflow runs within the managed scope.
- Matrix tests fan out to at most 3 variants simultaneously.
- At most 2 jobs access the integration database concurrently.
- Staging and production allow only one mutating deployment at a time.
- Production privileges are granted only to jobs passing policy gates and approvals.

## 23. Observing and Tuning Concurrency

You cannot choose good limits without measuring. Monitor resources, queues, and quality outcomes together.

| Metric | Question to answer |
|---|---|
| Active jobs | How many jobs are running per pool/project? |
| Queue depth/age | How many jobs are waiting and how old is the oldest waiting job? |
| Queue wait p50/p95 | How long do developers wait for a runner? |
| Job duration p50/p95 | Do jobs slow down as concurrency rises? |
| Runner CPU/memory/I/O | Does the pool still have headroom or is it saturated? |
| Dependency latency | Do databases/registries/APIs slow down with parallelism? |
| 429/timeout/error rate | Are we hitting throttling or overload failures? |
| Retry count | Are retries amplifying load? |
| Cancellation rate | How many jobs are cancelled due to new commits or timeouts? |
| Cost per successful pipeline | Does higher concurrency improve efficiency or only raise cost? |

Adjust limits step-by-step and compare before/after on comparable workloads. If execution time drops while queue wait, dependency errors, or cost jump sharply, evaluate holistically rather than looking solely at job duration.

## 24. Common Anti-Patterns

| Anti-pattern | Consequence | Improvement |
|---|---|---|
| Unbounded matrix/fan-out | One commit spawns hundreds of jobs | Set `max-parallel` and select combinations by risk |
| Bounding runners while ignoring dependencies | Databases/registries still overload | Enforce separate per-dependency semaphores/quotas |
| Independent per-repo quotas | Aggregate load exceeds shared quota | Allocate global or group-level quotas |
| Global lock on every job | Unnecessary throughput drop | Lock only the exact resource and capacity needing protection |
| Unbounded queues | Old jobs wait forever and consume management overhead | Queue bounds, expiry, cancellation, and backpressure |
| Immediate retry on 429/timeout | Retry storms and thundering herds | Backoff, jitter, retry budgets, and lower concurrency |
| No job/lock timeouts | Slots stay held indefinitely | Timeouts and cleanup on cancellation |
| Raising `max_connections` to hide DB bottlenecks | Increases memory/contention and destabilizes the DB | Measure CPU, I/O, locks, and pool usage |
| Using only average utilization | Misses load spikes and p95 | Use percentiles, headroom, and burst testing |
| Marking every job urgent | Regular jobs starve | Priority policies, aging, and minimum quotas |
| Rigid runner pool splits | Idle pools while other pools queue | Flexible quotas with global dependency caps |

## 25. Concurrency Limit Design Checklist

Before raising concurrency or expanding a matrix, verify:

- [ ] Fan-out is calculated across pipelines, matrices, jobs, and child workers/processes.
- [ ] Runner CPU, memory, disk I/O, network, and process limits are measured.
- [ ] Headroom exists for OS, agent, daemons, and load spikes.
- [ ] Shared dependencies and quotas are identified at the exact account/project/region scope.
- [ ] Dedicated limits exist for databases, registries, APIs, secret managers, and test environments as needed.
- [ ] Jobs using exclusive resources have semaphores, locks, or resource groups.
- [ ] Locks have timeouts/leases and release on cancellation or runner death.
- [ ] Queues have bounds, fairness/priority policies, and backpressure.
- [ ] Matrices enforce `max-parallel` and select combinations based on risk.
- [ ] Retries use backoff/jitter, attempt caps, and transient-error classification.
- [ ] Jobs, steps, network calls, and lock waits have appropriate timeouts.
- [ ] Cancellation stops child processes and frees resources.
- [ ] Metrics cover queues, execution, runners, dependencies, retries, and cost.
- [ ] Concurrency changes are measured and tuned incrementally.
- [ ] Production deployments are serialized with proper authorization controls.

## 26. Core Practical Principles

1. Compute parallelism at every layer, including pipelines, matrices, jobs, and child workers.
2. Set runner limits based on real CPU, memory, I/O, network, and headroom.
3. Enforce separate quotas for dependencies; idle runner capacity does not mean the database or API has capacity.
4. Use semaphores/resource groups for databases, environments, and shared resources.
5. Regulate queues with backpressure, fairness, priorities, and wait-time bounds.
6. Bound matrices/fan-out by testing value and risk coverage.
7. Combine timeouts, cancellation, retry budgets, exponential backoff, and jitter.
8. Prevent retry storms using circuit breakers or by throttling concurrency when dependencies degrade.
9. Split runner pools by workload type and trust boundary when needed.
10. Measure queue wait, execution time, saturation, throttling, errors, and cost before tuning limits.

Bounding concurrency is a resource-coordination decision spanning the entire CI/CD chain. When runners, dependencies, queues, and environments have well-calibrated limits, pipelines can leverage concurrency to shorten feedback loops while preserving stability and predictability. Start from real measurements, reserve headroom, and adjust incrementally rather than adding concurrent jobs just to make pipelines appear faster.
