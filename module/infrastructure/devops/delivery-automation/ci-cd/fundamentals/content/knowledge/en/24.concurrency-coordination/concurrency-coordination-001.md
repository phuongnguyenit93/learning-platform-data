# Distinguishing Intra-Pipeline Job Parallelism from Inter-Pipeline Concurrency

## Learning Objectives

After this lesson, learners will be able to:

- Distinguish between running jobs in parallel within a single pipeline and multiple pipeline runs overlapping in time.
- Explain the relationship between concurrency, parallelism, dependency graphs, and runner capacity.
- Design a DAG to independently execute steps that can run in parallel while preserving proper order for dependent steps.
- Identify race conditions when multiple pipelines simultaneously access environments, databases, registries, caches, or infrastructure.
- Choose among isolation, queues, concurrency groups, distributed locks, and optimistic concurrency control.
- Design cancellation, retry, and idempotency to avoid out-of-order deployments or duplicated side effects.
- Set concurrency limits based on resources, environments, and risk levels.
- Observe, test, and trace coordination behavior in CI/CD.

## 1. Two Problems Commonly Lumped Together as "Running in Parallel"

CI/CD can perform multiple pieces of work at the same time in two different ways.

**Intra-pipeline parallelism** is splitting a single pipeline run into independent jobs or tasks and executing them simultaneously once their dependencies are ready.

For example, the same commit can run unit tests, lint, dependency checks, and builds on different runners. These jobs belong to the same pipeline run and usually share a single release context.

**Inter-pipeline concurrency** occurs when multiple separate pipeline runs overlap in execution time. They may originate from different commits, pull requests, branches, repositories, scheduled runs, or manual triggers.

For example:

- The pipeline for commit A is running integration tests.
- A developer pushes commit B and a new pipeline starts.
- A nightly scheduled pipeline is also building.
- The release pipeline for the `main` branch is preparing to deploy to staging.

These are independent pipeline runs. They may share a runner pool, registry, test database, staging environment, or cloud account.

The two concepts are related but not synonymous:

| Aspect | Intra-pipeline parallelism | Inter-pipeline concurrency |
|---|---|---|
| Scope | Jobs/tasks within the same run | Multiple independent runs |
| Primary goal | Reduce completion time of a single pipeline | Increase throughput and accept more events |
| Dependencies | Typically modeled as a DAG | May be unaware of each other without coordination mechanisms |
| Data | Can share artifacts/context of the same run | May contend for shared resources |
| Coordination | Job dependencies, matrix, runner scheduler | Queues, concurrency groups, locks, quotas |
| Prominent risk | Job runs before its inputs are ready | Race conditions, overwrites, out-of-order deployments |
| Control method | DAG and fan-out limits | Isolation and coordination on shared resources |

A good CI/CD system must handle both. Increasing the number of parallel jobs inside one pipeline does not resolve conflicts between two pipeline runs. Conversely, serializing every pipeline fails to take advantage of independent jobs within each run.

## 2. Distinguishing Concurrency and Parallelism

These two terms are often used interchangeably in conversation, but they have distinct technical meanings.

- **Concurrency:** multiple tasks have overlapping lifecycles. The system may interleave their execution or run them across multiple workers.
- **Parallelism:** multiple tasks are genuinely executing at the exact same point in time, typically across multiple CPU cores, processes, machines, or runners.

For example, a runner with only one CPU core can still coordinate multiple processes concurrently by switching between them. Yet at any single instant, the CPU may execute only one instruction stream. If two jobs run on two separate runners, they can genuinely execute in parallel.

In CI/CD, users generally care more about completion time and the number of active runs than how a scheduler allocates CPU time. However, distinguishing the two concepts helps explain why:

- Multiple pipeline runs are in the running state, yet some are still waiting for a runner.
- Multiple jobs are declared to run in parallel, yet only a subset execute due to concurrency limits.
- Adding more runners does not make a single migration step run faster.
- A pipeline can run many jobs in parallel yet still wait for a final step that depends on all results.

Concurrency describes overlapping work; parallelism describes true simultaneous execution. Both require appropriate schedulers, resources, and coordination rules.

## 3. Parallel Execution Within a Pipeline Using a Dependency Graph

A pipeline is typically modeled as a Directed Acyclic Graph (DAG)—a directed graph with no cycles. Each node is a job or task; each edge represents a dependency.

The following example has three independent check jobs. The package job only runs after all three checks pass:

~~~mermaid
flowchart TD
    A["Checkout source"] --> B["Lint"]
    A --> C["Unit tests"]
    A --> D["Dependency scan"]
    B --> E["Package artifact"]
    C --> E
    D --> E
    E --> F["Publish artifact"]
~~~

If jobs B, C, and D do not depend on one another, the scheduler can run them concurrently. Once all pass, job E can begin.

Do not create dependencies merely to make the workflow look sequential. For example, forcing unit tests to wait for lint to finish prolongs execution time if the two steps do not consume each other's output.

Conversely, do not omit real dependencies. If integration tests require a service already deployed to a test environment, they must wait for the environment provisioning and deployment jobs to complete.

A simple rule of thumb:

- Only create a dependency edge when there is an actual data, state, or conditional relationship.
- If a job needs an artifact from another job, pass the artifact through the pipeline's storage mechanism rather than assuming a shared workspace.
- Independent jobs can run in parallel, but they must maintain separate outputs and states.
- An aggregation job only proceeds when all required dependencies succeed.

## 4. Pipeline Duration and the Critical Path

Parallel execution helps reduce overall duration, but duration does not simply equal the sum of job durations divided by the number of runners.

With a DAG, the ideal duration is bounded by the longest path from start to finish, known as the critical path. Actual duration also adds runner wait time, environment initialization, dependency downloads, artifact transfers, and resource constraints.

For example:

| Job | Assumed duration | Dependencies |
|---|---:|---|
| Checkout | 1 minute | None |
| Lint | 2 minutes | Checkout |
| Unit test | 6 minutes | Checkout |
| Dependency scan | 4 minutes | Checkout |
| Package | 3 minutes | Lint, unit test, scan |
| Publish | 1 minute | Package |

If run sequentially, the total duration is about 17 minutes. If the three jobs—lint, unit test, and scan—run in parallel, the ideal duration is about 11 minutes: checkout (1) + check group (6) + package (3) + publish (1).

In practice, it may take longer if:

- Only one runner is idle.
- Jobs have to download the same dependencies repeatedly.
- Runners are constrained by CPU or memory.
- The registry or package repository is throttled or congested.
- The longest job has high duration variance.
- A test matrix spawns too many jobs at once.

Pipeline optimization should start from the critical path and wait times, not merely by increasing the number of jobs. If a single job accounts for most of the duration, increasing concurrency of other jobs makes little difference.

## 5. Fan-Out and Fan-In

Fan-out is splitting a set of work into multiple independent jobs. Fan-in is gathering the results back into an aggregation step or subsequent stage.

Test matrix examples:

- Testing across multiple Java versions.
- Testing across multiple operating systems.
- Testing multiple independent modules.
- Building for multiple CPU architectures.
- Running multiple groups of integration tests.

~~~mermaid
flowchart TD
    A["Single commit"] --> B["Fan-out"]
    B --> C["Test Java 17"]
    B --> D["Test Java 21"]
    B --> E["Test Linux"]
    B --> F["Test Windows"]
    C --> G["Fan-in: aggregate results"]
    D --> G
    E --> G
    F --> G
    G --> H{"All required pass?"}
    H -- "Yes" --> I["Allow next step"]
    H -- "No" --> J["Block pipeline"]
~~~

Fan-out needs to be bounded. A matrix of 5 operating systems × 4 runtime versions × 6 modules can generate 120 jobs for a single commit. If multiple pull requests run simultaneously, the number of jobs can far exceed the capacity of the runner pool.

Best practices:

- Use matrices only for combinations that provide testing value.
- Use `max_parallelism` to cap the number of concurrent jobs.
- Partition tests into groups with balanced durations.
- Use runners suited to the workload type.
- Limit the number of pipeline runs allowed to fan out simultaneously.
- Cancel unnecessary jobs once outcomes are clear, according to policy.

## 6. When Does Inter-Pipeline Concurrency Occur?

A new pipeline run can be created by many events:

- Pushing a new commit.
- Creating or updating a pull request.
- Merging into the main branch.
- Creating a tag or release.
- Scheduled cron triggers.
- Manual triggers by a user.
- Another pipeline invoking a reusable workflow or downstream pipeline.
- Retrying a failed run.

These events can occur closely together. For instance, a developer pushes three commits within one minute. If every commit triggers a pipeline, all three runs may be active at the same time.

Multiple pipeline runs can also come from different branches. A pull request may be running tests while the `main` branch deploys to staging. A nightly scan may run at the same time as a release pipeline.

This is not necessarily an error. Concurrent runs allow the system to accept more changes and reduce wait times. Problems arise when they contend for a resource or produce effects that require ordering.

## 7. Two Coordination Axes That Must Be Designed Separately

You can envision two independent axes:

| | Single pipeline run | Multiple pipeline runs |
|---|---|---|
| Sequential execution | Job A then B then C | Each run is queued |
| Parallel/concurrent execution | Independent jobs in the DAG run simultaneously | Multiple runs are allocated resources by the scheduler simultaneously |

For example:

- One pipeline runs lint, tests, and scans in parallel.
- Two pipelines for two pull requests run simultaneously, each with its own DAG.
- One pipeline runs a test matrix while another builds artifacts.
- Multiple pipelines simultaneously request deployment to a staging environment.

A policy must be chosen for each level. You might allow parallel tests within a run and multiple concurrent test runs, while serializing deployments to a shared staging environment.

This is a key point: the concurrency limit of pipeline runs and the concurrency limit of jobs do not necessarily share the same value or the same scope.

## 8. Runner Scheduler and Resource Limits

A job can only run when the scheduler allocates an appropriate runner. Runners can be constrained by:

- Number of runner machines or containers.
- CPU, memory, and disk.
- Runner labels or operating system types.
- Platform concurrency limits.
- Quotas per organization, repository, or project.
- Network bandwidth and connection limits.
- Rate limits of package registries, cloud APIs, or test services.

When multiple pipeline runs exist, the scheduler must decide which job runs first. Policies may be based on FIFO, priority, runner labels, fairness, or quotas.

It is important to distinguish:

- **Job pending:** waiting on dependencies or conditions.
- **Job queued:** ready to run but not yet assigned a runner.
- **Job running:** currently executing.
- **Job blocked:** held by an approval, lock, or policy.
- **Job cancelled:** terminated before or during execution.

If a pipeline is slow, determine whether time is being lost in dependencies, the queue, or execution. Adding runners only helps when the bottleneck is a lack of runners and other limits allow it.

Do not allocate the entire runner pool to a long fan-out batch of jobs if doing so starves urgent release jobs of resources. Dedicated runner pools, priorities, or quotas by workload type may be required.

## 9. Multiple Pipelines Can Contend for Shared Resources

This is the biggest risk difference compared to running independent jobs within the same pipeline.

Commonly shared resources:

| Resource | Potential conflict |
|---|---|
| Staging environment | Two releases overwrite each other's version or configuration |
| Test database | Migrations and tests from two runs alter each other's schema |
| Registry tag | Two builds overwrite the same tag such as `latest` |
| Cache | Untrusted jobs write data consumed by other jobs |
| Terraform state | Two applies update the same state or resource simultaneously |
| Test account | Two runs simultaneously change passwords, permissions, or data |
| Cloud quota | Multiple runs provision resources exceeding quota |
| Shared namespace | A job deletes or modifies another run's resources |
| Message queue | A test consumer receives messages from another pipeline |
| External API sandbox | Multiple runs share quota or account state |

If resources are isolated per run, multiple pipelines can run concurrently much more safely. If resources are shared and hold mutable state, isolation or coordination is required.

## 10. Race Conditions Between Pipelines

A race condition occurs when the outcome depends on the order or timing of concurrent operations.

### 10.1. Two Pipelines Deploying to Staging Simultaneously

- Run A deploys commit A.
- Run B deploys commit B.
- Run B finishes first.
- Run A finishes later and overwrites staging with the older commit.

Staging no longer reflects the latest commit, even though both pipelines report success.

### 10.2. Two Pipelines Running Migrations Simultaneously

- Run A checks and sees migration M does not exist yet.
- Run B also checks and sees M does not exist yet.
- Both start executing M.
- One run may encounter lock errors, duplicate DDL, or a half-applied migration state.

Checking before running is insufficient if the check-and-write operation is not atomically protected.

### 10.3. Two Pipelines Writing the Same Artifact Tag

- Run A builds an artifact from commit A and pushes the tag `service:latest`.
- Run B builds from commit B and pushes the same tag.
- Run A's deployment might pull the tag after it has already been replaced by Run B.

Using immutable digests and keeping tags strictly for lookup avoids this ambiguity.

### 10.4. Tests Sharing a Database

Two runs truncate tables or seed data simultaneously. Run A's tests may read data created by Run B or deleted by Run B.

Both test suites can pass individually yet fail when run concurrently.

### 10.5. Shared Terraform or Infrastructure

Two runs read the same stale state and plan changes. If state locking is not used properly, one apply can overwrite or lose the updates of the other apply.

A state backend with locking and drift checks before apply is required.

## 11. Isolation Is Often Better Than Locking Everything

Whenever dedicated resources can be provisioned per pipeline run, prefer isolation.

Examples:

- Separate database or separate schema per run ID.
- Separate Kubernetes namespace.
- Separate bucket or prefix.
- Separate test account.
- Separate artifact path.
- Separate cache namespace.
- Separate ports and service endpoints.
- Independently seeded dataset.

Resource names can be constructed from project, run ID, and attempt ID. Cleanup and TTL policies are necessary to prevent temporary resources from accumulating.

Isolation allows multiple pipeline runs to genuinely run in parallel with minimal waiting on each other. However, not every resource can be duplicated. Production, shared staging, large databases, or cloud quotas may require coordination.

Do not lock an entire pipeline just because a single step uses a shared resource. Isolate independent steps and serialize only the conflicting region.

## 12. Concurrency Groups and Queues

A concurrency group groups runs that may contend for the same scope. When one run in the group is active, another run may have to wait, be cancelled, or be scheduled according to policy.

Reasonable group examples:

- Production deployment of the same service.
- Migrations on the same database.
- Applying the same Terraform state.
- Modifying a shared staging environment.
- Publishing to an ordered release channel.

A concurrency group should represent the specific resource or state that needs protection. Do not use a single global group for every job across all repositories if they do not share resources.

Common policies:

| Policy | Behavior | Suitable when |
|---|---|---|
| Allow concurrent | Allows multiple runs to execute simultaneously | Runs are isolated and independent |
| Queue/serialize | Runs one after another in turn | Shared resource requires a single writer |
| Cancel previous | Cancels the older run when a new run arrives | Only the latest state matters and the old run has not produced irreversible side effects |
| Latest wins | Keeps the latest request and drops older ones by policy | Deploying preview or staging environments per branch |
| FIFO | Preserves request order | Every release must be processed sequentially |

Exact names and semantics depend on the CI/CD platform. Some systems keep only one running and one pending run; some support multi-run queues; some cancel old runs as soon as a new run arrives. Check the documentation and test actual behavior before relying on it.

## 13. Cancelling an Old Pipeline Is Not Always Safe

Cancelling an old run can reduce wasted resources, but cancellation is not equivalent to rollback.

For example:

- A job running unit tests can be safely cancelled.
- A job building temporary artifacts can be cancelled and have its workspace cleaned up.
- A deploying job may have already modified a subset of instances.
- A job running migrations may have already committed some changes.
- A job applying infrastructure may have already created resources without recording complete state.
- A job sending messages or calling a payment provider may have already caused side effects.

Before enabling `cancel-in-progress` or a similar mechanism, verify:

- Can the job receive cancellation signals?
- Does the operation have irreversible commit points?
- Is there cleanup or compensation upon cancellation?
- Is the current state recorded?
- Will the new run wait for the old run to release its lock?
- Can a partially completed deployment be detected?

For steps with side effects, design cooperative cancellation: the job checks for stop signals at checkpoints, completes or safely releases resources, and only then exits.

Do not cancel a migration mid-flight if the migration tool does not support recovering from a partially executed state.

## 14. Distributed Locks When Multiple Pipelines Modify One Resource

When a resource cannot be isolated, a distributed lock can ensure that only one actor executes a sensitive region of operations at a time.

For example, only one pipeline is allowed to deploy a service to shared staging.

A lock needs:

- **Resource key:** exact identifier of the locked resource.
- **Owner:** run ID or identity of the pipeline holding the lock.
- **Lease/expiry:** a timeout to prevent a lock from being held forever if a runner dies.
- **Renewal:** a mechanism to extend the lease if the operation takes longer.
- **Release:** releasing the lock upon completion.
- **Audit:** recording who acquired, renewed, and released the lock.

Avoid a subtle bug: the lease expires while the old job is still running. A new job acquires the lock and starts deploying, while the old job continues writing to the resource.

A **fencing token** can be used: each lock grant generates a monotonically increasing sequence number. The target resource only accepts operations from the newest token and rejects older writers. Having a lease timeout without fencing or owner validation at the target resource may not be enough to stop an old writer from continuing.

Do not roll your own distributed lock using temporary files or environment variables when multiple machines need to coordinate. Use a backend-supported locking mechanism such as state locking, database advisory locks, or a proper lock service.

## 15. Optimistic Concurrency and Compare-and-Swap

Not every operation requires holding a lock for its entire duration. For some resources, you can read the current revision and write only if that revision has not changed.

For example:

1. The pipeline reads environment revision 42.
2. The pipeline computes the desired state.
3. Before writing, it requests an update only if the revision is still 42.
4. If the revision is now 43, the operation is rejected and the pipeline must re-resolve state.

This is optimistic concurrency control or compare-and-swap.

Advantages:

- Does not hold long-lived locks.
- Prevents overwriting a newer update.
- Fits APIs with versions or ETags.
- Can retry after re-reading state.

Limitations:

- May require recomputing on conflict.
- Unsuitable if the operation causes irreversible side effects before the compare step.
- Requires backend support for atomic conditional updates.

For deployments, you can require that the environment revision still matches the revision checked before applying manifests. If state has changed, the pipeline stops and re-evaluates rather than blindly overwriting.

## 16. Protecting Release Order and Avoiding Deploying Stale Commits

Push events can arrive close together or be processed with varying latencies. A run for an older commit may finish slower than a newer run.

For example:

~~~text
10:00  Commit A is pushed, Pipeline A starts
10:02  Commit B is pushed, Pipeline B starts
10:05  Pipeline B deploys B successfully
10:08  Pipeline A finishes deploying A
~~~

Without coordination, the environment can revert to commit A even though B is newer.

Control measures:

- Use a desired revision or release sequence to determine which version is allowed to deploy.
- Before deploying, verify that the commit/release is still a valid target.
- Serialize deployments per service/environment.
- Use latest-wins for preview environments if policy permits.
- Use FIFO when every release must be processed in order.
- Cancel obsolete runs before steps with side effects if they are already superseded.
- Use immutable artifact digests and record deployment records.

Do not merely compare pipeline start times. Push time, run creation time, and deployment time can differ. Rely on commit ancestry, release sequence, or an authoritative desired state.

## 17. Idempotency Makes Retries and Coordination Safe

CI/CD may resend requests on timeouts or network drops. A job can also be retried manually. If an operation is not idempotent, repeated execution can create duplicate resources or side effects.

Examples:

- Creating two deployment records for the same release.
- Running a migration twice.
- Creating multiple cloud resources with conflicting names.
- Sending duplicate release notifications.
- Publishing two different artifacts under the same tag.
- Sending the same message multiple times.

Safeguards:

- Use a unique release ID or operation ID.
- Check state before creating or modifying resources.
- Use upserts or API idempotency keys where supported.
- Version migrations and track already-executed history.
- Identify artifacts by digest.
- Retry jobs only on transient failures and with backoff.
- Record checkpoints to resume from a known state.
- Provide compensation or cleanup for operations that cannot be made idempotent.

Idempotency does not replace locks. Two pipelines can both check that a state does not exist yet and both create the resource. An atomic operation, unique constraint, lock, or conditional create is needed to handle the race.

## 18. Database Migrations and Shared Resources Require Dedicated Coordination

Database migrations typically have a wider blast radius than a test job.

If two pipelines run migrations simultaneously:

- Both may attempt to create the same table or index.
- Both may contend for database locks.
- A migration depending on another may execute out of order.
- One pipeline may inspect state before the other commits its migration record.
- A long-running migration may block production requests.

Principles:

- Each database or schema has a single migration lock mechanism.
- Migrations are versioned with clear execution history.
- Use transactions if the database and migration support them.
- Define behavior if a migration fails partway through.
- Do not allow test jobs to arbitrarily run migrations against a shared database.
- Use a separate database or schema per test run whenever possible.
- Production migrations require appropriate gates, permissions, and runbooks.

Similarly, Terraform state, Kubernetes namespaces, shared staging, and registry release channels all require coordination keyed by the specific resource.

## 19. Caches and Artifacts in Multi-Pipeline Environments

Caches speed up builds, but they can also serve as shared mutable state.

An overly broad cache key can cause a run on one branch to read data produced by another branch. If cached data is incompatible or poisoned, build results become unreliable.

Best practices:

- Derive cache keys from lockfiles, toolchains, and operating systems.
- Partition caches along trust boundaries.
- Never use a cache as the authoritative source of an artifact.
- Never allow untrusted jobs to write caches consumed by trusted release jobs.
- Provide invalidation mechanisms when dependencies or configurations change.

Artifacts should be stored separately per run or release, with digests and metadata. Do not use a single shared mutable tag as the sole output of multiple pipelines.

If aliases such as `latest` or `stable` are needed, update the alias only through a coordinated publish step after verifying which run is authorized to become the newest version.

## 20. Practical Coordination Model for CI/CD

A balanced model typically follows these principles:

- Independent lint, unit test, and scan jobs run in parallel within a pipeline.
- Integration tests run in an isolated database or namespace per run.
- Multiple validation pipelines can run concurrently if runner capacity allows.
- Built artifacts are stored by immutable digest.
- Publishing aliases or release metadata is coordinated to prevent overwrites.
- Deploying to preview environments can run in parallel if each branch has its own environment.
- Deploying to shared staging is serialized or checks the desired revision.
- Production deployments use locks, approvals, and dedicated identities.
- Migrations use database/schema-level locking.
- Cleanup deletes only resources belonging to the exact run ID.

~~~mermaid
flowchart TD
    A["Push / PR event"] --> B["Pipeline run"]
    B --> C["Lint"]
    B --> D["Unit tests"]
    B --> E["Dependency scan"]
    C --> F["Package"]
    D --> F
    E --> F
    F --> G["Artifact registry by digest"]
    G --> H["Integration test in isolated environment"]
    H --> I["Release verification"]
    I --> J["Acquire environment coordination"]
    J --> K["Deploy shared environment"]
    K --> L["Post-deploy verification"]
    L --> M["Release evidence"]
~~~

While this pipeline is running, other validation pipelines can still execute in parallel. Only the step mutating the shared environment requires coordination.

## 21. Example Logical Concurrency Configuration

The following YAML illustrates the general concept, not the syntax of any specific platform:

~~~yaml
pipeline:
  jobs:
    lint:
      parallel: true
      needs: [checkout]

    unit_tests:
      parallel: true
      needs: [checkout]
      matrix:
        runtime: [17, 21]
      max_parallel: 4

    dependency_scan:
      parallel: true
      needs: [checkout]

    package:
      needs: [lint, unit_tests, dependency_scan]

    integration_tests:
      needs: [package]
      environment:
        isolation_key: run_id
        cleanup_ttl: 2h

    deploy_staging:
      needs: [integration_tests]
      concurrency:
        resource: service-staging
        policy: queue
      precondition:
        desired_revision_must_match: true

    deploy_production:
      needs: [deploy_staging]
      concurrency:
        resource: service-production
        policy: queue
      approval: required
      lock_lease: bounded
      verify_after_deploy: true
~~~

This configuration demonstrates two levels:

- Independent test jobs can fan out within a run, bounded by `max_parallel`.
- Staging and production deployments use coordination keyed by environment resource.

In real-world implementations, check the exact semantics of your CI tool: whether concurrency groups maintain a queue or cancel older runs, whether locks are held across jobs, and how cancellation is propagated to running processes.

## 22. Observing and Measuring Coordination

Without metrics, it is hard to tell whether a pipeline is slow due to a lack of runners, long queues, or dependencies.

Metrics to track:

| Metric | Meaning |
|---|---|
| Queue wait time | Time a job waits for a runner or slot |
| Job execution time | Actual execution duration |
| Pipeline duration | Time from trigger to final outcome |
| Active pipeline runs | Number of currently active pipeline runs |
| Active jobs / runner utilization | Runner usage level |
| Concurrency limit hits | Number of times blocked by concurrency limits |
| Lock wait time | Time spent waiting on a shared resource |
| Lock timeout / stale lock | Coordination failure or expired lease |
| Cancelled / superseded runs | Number of runs cancelled or replaced by newer runs |
| Deployment revision order | Actual order of deployed revisions |
| Resource contention | CPU, memory, disk, quota, or rate limit pressure |
| Test isolation failures | Failures caused by shared data or environments |

Attach run ID, commit SHA, release ID, environment ID, and resource key to logs so execution can be traced from jobs down to resources.

If queue wait increases while runner utilization is low, the issue may lie in concurrency groups or approvals. If runner utilization is consistently high and queues grow long, review capacity, fan-out limits, and priorities. If lock wait is high, the resource scope may be too broad or the lock may be held for too long.

## 23. Testing Contention Scenarios

Do not test a pipeline only in isolation. Test scenarios where multiple runs are active at once:

- Two pull requests running integration tests simultaneously.
- Two consecutive commits requesting a staging deployment simultaneously.
- Two pipelines running migrations on the same database simultaneously.
- A run being cancelled mid-deployment.
- A runner losing connectivity while holding a lock.
- A lease expiring while the old process has not yet stopped.
- Retrying after a timeout when the prior operation may have already succeeded.
- Two pipelines publishing the same artifact alias simultaneously.
- An older pipeline finishing after a newer pipeline.
- Cleanup from one run executing while another run is still using resources.
- Queue or external API hitting rate limits.
- A pipeline holding a lock longer than expected.

Test results must demonstrate that:

- No two writers modify an exclusive resource simultaneously.
- No older revision is deployed after a newer revision when policy forbids it.
- Retries do not produce duplicate side effects.
- Cancellation does not leave unrecorded partial state.
- Locks are released or fencing blocks stale writers.
- Temporary resources of one run are not cleaned up by another run.

## 24. Common Anti-Patterns

| Anti-pattern | Risk | Improvement |
|---|---|---|
| Running every job in parallel | Increased load, contention, and harder debugging | Rely on a DAG and genuine dependencies |
| Serializing the entire pipeline | Long wait times, reduced throughput | Serialize only shared-resource regions |
| Confusing job concurrency with run concurrency | Overlooking conflicts between multiple pipelines | Design two separate coordination levels |
| Letting all pipelines deploy to staging concurrently | Older runs can overwrite newer runs | Use queues, locks, or isolated environments |
| Using mutable tags for artifacts | Pipelines may deploy the wrong content | Use immutable digests |
| Sharing a test database | Tests corrupt another run's data | Use dedicated databases/schemas/containers |
| Cancelling older runs at any point | Migrations or deployments may be left half-done | Use cooperative cancellation and checkpoints |
| Using locks without leases/fencing | Stale locks or old writers continue modifying state | Use leases, owner checks, and fencing tokens |
| Retrying every failure | Repeated side effects or amplified load | Classify failures, use backoff and idempotency |
| Relying only on CI concurrency groups to lock a database | Other tools can still modify the database | Lock at the resource or backend itself |
| Cleaning up by generic names | Deleting another run's resources | Tie resources to run ID and owner |
| Not checking commit order | Older commits can deploy after newer ones | Enforce desired revision and preconditions |
| Measuring only total pipeline duration | Unclear whether bottlenecks are in queuing or execution | Track queue wait, lock wait, and critical path |

## 25. Concurrency Design Checklist

When designing a pipeline, verify that:

- [ ] Job parallelism within a run and concurrency across multiple runs are distinguished.
- [ ] The DAG reflects only genuine dependencies.
- [ ] Fan-out is bounded and matches runner capacity.
- [ ] Critical path and queue wait time are measured separately.
- [ ] Multiple validation pipelines can run concurrently when data is isolated.
- [ ] Shared resources have explicit resource keys and owners.
- [ ] Test databases, namespaces, caches, and artifacts are partitioned per run when possible.
- [ ] Deployments to shared environments are queued or locked.
- [ ] Migrations have database/schema-level coordination.
- [ ] Artifacts use immutable digests; aliases are updated in a controlled manner.
- [ ] Cancellation is designed around operation types and side effects.
- [ ] Retries use backoff, idempotency keys, or checkpoints.
- [ ] Locks include owner, lease, renewal, release, and stale-writer prevention.
- [ ] Desired revision is checked before deployment.
- [ ] Cleanup affects only resources belonging to the matching run.
- [ ] Logs and metrics exist to trace queues, locks, runs, and deployment order.
- [ ] Concurrent runs, retries, cancellations, and runner failures have been tested.

## 26. Self-Assessment Exercise

A repository has the following pipeline:

- Every pull request runs lint, unit tests, dependency scan, and integration tests.
- Integration tests share a single staging database.
- Every commit to `main` triggers a staging deployment pipeline.
- The deployment pipeline uses the `latest` image tag.
- If a new commit arrives, the older run is cancelled immediately.
- Migrations run at the beginning of the deployment step.
- A nightly pipeline also runs migrations and smoke tests on the same staging environment.

When two consecutive commits are pushed, the team experiences flaky tests and occasionally staging runs an older version than the newest commit.

Analyze:

1. Which jobs within a single pipeline can run in parallel?
2. Why do integration tests sharing a database cause race conditions?
3. How can databases or schemas be isolated per run?
4. How should staging deployment pipelines be coordinated?
5. What risks does the `latest` tag introduce when two builds publish concurrently?
6. Should old runs be cancelled even while migrations are running?
7. What locks or separate environments does the nightly pipeline need?
8. How can you prevent an older commit from deploying after a newer commit?
9. How must migration retries guarantee idempotency and consistent state?
10. Which metrics should be tracked to identify whether queues, runners, or locks are the bottleneck?

A sound design keeps lint, unit tests, and scans running in parallel; provisions isolated databases for integration tests; builds immutable artifacts; serializes only operations that modify shared staging or shared databases; and validates the desired revision prior to deployment.

## Conclusion

Running jobs in parallel within a pipeline shortens the critical path by executing independent jobs simultaneously. Running multiple pipelines concurrently enables the system to handle more events and increase throughput, yet can introduce race conditions when runs modify shared resources at the same time.

Model dependencies with a DAG, bound fan-out to capacity, isolate data and environments per run, and use queues, locks, or compare-and-swap on resources requiring coordination. Combine idempotency, safe cancellation, immutable artifacts, and revision order checks so pipelines stay fast without overwriting one another's state. Good coordination does not mean everything must run sequentially; it means work runs concurrently when safe and coordinates cleanly when conflicts exist.
