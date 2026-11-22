# Choosing a Solution Based on Startup Frequency, Application State, and Integration Cost

A slow-starting Java application does not automatically mean it needs CRaC (Coordinated Restore at Checkpoint). There are many ways to reduce the time from when a process is created until the application is ready: optimizing startup, using Class Data Sharing (CDS/AppCDS), using AOT techniques, compiling into a native executable, keeping ready instances in a warm pool, or creating checkpoints to restore a warmed-up process.

Each approach solves a different part of the problem. Some reduce class and runtime initialization overhead; some eliminate the usual JVM startup step; some keep processes ready beforehand; CRaC restores the state of a previously running process. Actual benefits depend on how frequently new instances need to be created, how stateful the application is, warm-up duration, compatibility requirements, and integration costs.

This article provides a way to choose a solution based on three main groups of factors:

- **Startup frequency:** does the system frequently create new processes or keep instances running long-term?
- **Application state:** does startup only create internal objects or also connect to databases, load secrets, caches, sessions, leases, and external resources?
- **Integration cost:** to what extent must the team modify code, builds, runtime, infrastructure, testing, and operations?

The goal is to choose a solution that meets the time-to-ready target with appropriate total cost and risk. Do not choose CRaC just because it can restore quickly; it is necessary to determine which portion of time can actually be saved and which parts of state can be safely recovered.

## 1. Identify the startup problem to solve

Before comparing technologies, startup time must be measured accurately. A Java application typically goes through several phases:

1. Container or VM is provisioned.
2. JVM process is created.
3. JVM loads runtime, modules, and classes.
4. Framework creates the application context.
5. Application reads configuration and secrets.
6. Connects to databases, brokers, caches, and other services.
7. Loads data or builds caches.
8. Warms up JIT and critical execution paths.
9. Runs health checks.
10. Readiness transitions to true and the instance receives traffic.

The time from step 1 to step 9 can be much longer than the time it takes for the JVM process to start running. If you only measure the execution time of the java command, you might optimize the wrong part that is not the bottleneck.

### 1.1 Break down time milestones

The following milestones can be recorded:

~~~text
T0: container/VM allocation begins
T1: container is running
T2: JVM process starts
T3: application context initialized
T4: mandatory dependencies connected
T5: cache and warm-up completed
T6: readiness becomes true
T7: first production request completes
~~~

Meaningful metrics:

- **Container provisioning time:** T1 - T0.
- **JVM startup time:** from T2 until the JVM can execute application code.
- **Application initialization time:** T3 - T2.
- **Dependency initialization time:** T4 - T3.
- **Warm-up time:** T5 - T4.
- **Time-to-ready:** T6 - T0.
- **First-request latency:** time to process the first request after receiving traffic.

Time-to-ready is typically the key metric for autoscaling, serverless-like workloads, and rollouts. First-request latency matters when JIT or caches continue warming up after readiness.

### 1.2 Measure distributions, not just a single run

Startup time can vary due to node load, image pulls, DNS, databases, network, GC, JIT, and caches. Measure multiple times and track p50, p95, p99 along with the number of cold starts.

For example, a 2-second p50 startup with an 18-second p99 can cause major problems during sudden scale-out. Conversely, a steady 8-second startup may be acceptable for a service deployed only a few times a day.

Distinguish between:

- Cold start on a host without the container image cached.
- Cold start when the image is already on the node.
- New JVM start inside an already running container.
- Restore checkpoint from local storage.
- Restore checkpoint after downloading the artifact over the network.
- Instance restart after a crash.
- Scale-out due to traffic increase.

These scenarios have different costs. Do not compare a CRaC restore from local disk with a JVM startup that includes an image pull and conclude CRaC is always faster.

## 2. Startup frequency determines economic value

Reducing startup time is most valuable when the system frequently needs new instances and startup delay affects latency, capacity, or cost.

Startup frequency can come from:

- Autoscaling when traffic changes.
- Serverless or scale-to-zero.
- Rolling deployments.
- Node replacements and cluster upgrades.
- Crash recovery.
- Scheduled batch jobs or workers.
- Test environments created and destroyed continuously.
- New tenants or workloads requiring separate processes.
- Hourly or seasonal burst workloads.

A service running continuously for weeks and restarting only on deploys may not gain much benefit from checkpoints. A worker spawned thousands of times a day can benefit significantly if startup and warm-up account for a substantial portion of processing time.

### 2.1 Distinguish request frequency from process startup frequency

An API may handle millions of requests per hour while running only a stable group of instances. High request frequency does not mean high process startup frequency.

Conversely, a job may receive only a few requests, yet each request spawns a separate JVM. Process startup frequency in that case is very high.

Measure:

- Number of new instances per minute/hour/day.
- Number of restarts per instance.
- Proportion of instances created by autoscaling.
- Ratio of cold starts to warm reuse.
- Number of workloads that finish shortly after startup.
- Number of checkpoint/restores that can actually replace new startups.

### 2.2 Calculate startup minutes potentially saved

A simple estimate:

~~~text
SavedStartupTime =
    NewInstancesPerPeriod
    x (BaselineTimeToReady - OptimizedTimeToReady)
~~~

For example:

- Baseline time-to-ready: 12 seconds.
- After optimization: 4 seconds.
- New instances: 900 per day.

Waiting time saved:

~~~text
900 x (12 - 4) = 7,200 seconds
                     = 120 minutes/day
~~~

This is the total startup time saved across instance creations, not 120 minutes of CPU time or 120 minutes of direct cost savings. It is necessary to determine which portion of that benefit actually translates into revenue, latency, capacity, or resource reduction.

### 2.3 When startup frequency is low

If instances are long-lived and restarts are rare, prioritize:

- Optimizing the startup path.
- Removing unnecessary initialization.
- Connecting dependencies lazily when appropriate.
- Using CDS/AppCDS if class loading is significant.
- Adjusting deployment strategy and readiness.
- Maintaining a small amount of warm capacity if cost is reasonable.

CRaC can still be useful if startup is extremely expensive or rollouts require rapid recovery, but the costs of creating, testing, storing, and maintaining checkpoint artifacts must be accounted for.

## 3. Application state affects the suitability of each solution

Two applications with the same startup time may need different solutions because the state they hold in memory differs.

### 3.1 Stateless or near-stateless applications

Examples:

- APIs reading data from a database.
- Workers processing independent requests.
- Services holding only rebuildable caches.
- Application contexts not tied to a specific tenant or instance.

These applications are usually easier to use with CRaC because after restore they can:

- Reconnect to the database.
- Resolve new endpoints.
- Obtain credentials via workload identity.
- Rebuild caches.
- Rejoin broker groups.
- Open readiness after validation completes.

However, being stateless at the business layer does not mean the process holds no state. HTTP clients, TLS contexts, thread pools, schedulers, DNS caches, and framework singletons can still hold runtime state.

### 3.2 Stateful applications

Examples:

- Session store residing on the heap.
- In-memory workflow engines.
- Long-running stream processors.
- Game servers holding session or world state.
- Workers holding cursors, offsets, or state machines.
- Services with leader leases or locks.
- Applications holding native handles or long-lived connections.

For this group, answer:

- Is state persisted durably outside the process?
- Can it be replayed or reconstructed after restore?
- Is there instance identity or ownership tied to the old process?
- Can state be duplicated when restoring the same image multiple times?
- Can duplicate side effects be produced?
- Are fencing tokens or external coordination needed?
- Does state expire while the image is stored?

If state exists only on the heap with no way to persist or reconcile, restoring an image can return the application to an old snapshot. That can cause lost updates or duplicate processing. Before choosing CRaC, design state recovery.

### 3.3 Classifying state

| State type | Examples | Handling on restore |
|---|---|---|
| Immutable startup data | Release-fixed rules, parsed metadata | Can be kept if version is compatible |
| Rebuildable cache | Reference data, computed lookup | Keep if still valid or rebuild |
| Dynamic configuration | Feature flags, endpoints, limits | Refresh per revision/policy |
| Credentials | Tokens, secrets, certificates | Fetch new or revalidate |
| External connections | JDBC, HTTP pools, broker clients | Close/recreate/reconnect |
| Durable business state | Orders, accounts, workflow records | Read from authoritative source |
| Temporary ownership | Leases, locks, leader state | Reacquire or validate |
| Event processing state | Offsets, cursors, assignments | Rejoin/replay/deduplicate |
| Instance-specific identity | Pod ID, node ID, process generation | Re-issue after restore |

A good checkpoint typically retains expensive but stable initialization states, while recovering dynamic state and external resources after restore.

## 4. Options for reducing startup time

No single solution fits every workload. Compare options by the portion of startup they reduce, the extent of application changes, and operational costs.

### 4.1 Conventional startup optimization

This is usually the first step to take:

- Remove unnecessary classpath entries and dependencies.
- Defer initialization that does not serve the first request.
- Reduce classpath scanning or component scanning.
- Avoid loading the entire dataset if only a subset is needed immediately.
- Use appropriately sized connection pools.
- Reduce sequential network calls during startup.
- Run independent steps in parallel when safe.
- Move non-mandatory tasks to the background after readiness.
- Measure and eliminate slow initializers.

Pros:

- Low platform dependence.
- Easy to debug.
- Keeps the conventional JVM model.
- No need for checkpoint artifacts or native executables.
- Can improve both startup and long-term operations.

Cons:

- Limited ceiling; some frameworks or workloads have inherently high initialization cost.
- Lazy initialization can shift latency to the first request.
- Background execution can cause readiness to incompletely reflect actual readiness.

Start by profiling startup and identifying bottlenecks before adding new technology.

### 4.2 Class Data Sharing (CDS) and AppCDS

CDS allows the JVM to share class metadata stored in an archive. AppCDS extends this capability to application and dependency classes, depending on the JDK and configuration.

CDS/AppCDS can reduce part of class loading overhead and memory footprint. It does not save the heap state of a running application process, does not preserve a created application context, and does not replace database connections or cache loading.

Suitable when:

- Startup has significant class loading cost.
- The application uses many classes/frameworks.
- You want to keep the normal JVM model.
- You want optimization with minimal lifecycle changes.
- The workload runs on a JDK supporting the corresponding feature.

Verify that the archive is created and used with the exact JDK/build. Changes to classpath, JDK, or dependencies may require regenerating the archive.

### 4.3 Ahead-of-Time (AOT) cache and AOT compilation

AOT is a group of techniques with many forms. Depending on the JDK and framework, AOT can store pre-analyzed information or pre-compile part of the code to reduce runtime work.

AOT cache is not synonymous with a native executable. Some mechanisms still run inside the JVM and still need to initialize objects, connect dependencies, load configs, and perform dynamic warm-up.

Suitable when:

- The runtime or framework has appropriate AOT support.
- Expensive startup work lies in analysis or compilation that can be done ahead of time.
- You want to reduce startup while keeping the JVM.
- The team accepts additional build pipeline complexity.

Evaluate cache stability across JDK, classpath, application build, and environment. Do not assume every AOT artifact can be shared across builds.

### 4.4 GraalVM Native Image

GraalVM Native Image compiles a Java application into a native executable prior to deployment. Some workloads can achieve faster startup and lower footprint than the traditional JVM.

In return, the build and runtime have different characteristics:

- Reflection, dynamic proxies, resources, and class loading need to be handled.
- Additional metadata or configuration may be needed for frameworks/libraries.
- Some native libraries and dynamic behaviors require adjustment.
- Builds can be slow and resource-intensive.
- Runtime behavior, memory management, and performance profiles differ from the JVM.
- Runtime JIT optimization is not the same as on a regular JVM.

Native Image is suitable when startup and memory footprint are critical requirements, the workload is compatible, and the team can maintain a native build pipeline.

It is not a drop-in replacement for every Java application. Try building a vertical slice including frameworks, reflection, JDBC, TLS, and critical dependencies before committing to a full migration.

### 4.5 Maintaining a warm pool or minimum replicas

An operational option is keeping a number of running and ready instances on standby. When traffic increases, the scheduler sends requests to existing instances instead of waiting to spawn new processes.

Pros:

- No runtime changes or checkpoint creation required.
- Easy to apply to existing applications.
- Can directly reduce cold starts.
- Keeps active connection and cache state warm.

Cons:

- Consumes resources when there is no traffic.
- Does not eliminate startup when the warm pool is exhausted.
- Instances can still die or be replaced.
- Requires capacity and scale-down management.
- May hold connections or credentials longer than desired.

A warm pool is suitable when startups are rare or predictable, and the cost of keeping idle capacity is lower than the cost of cold starts.

### 4.6 CRaC checkpoint/restore

CRaC coordinates the application with a checkpoint engine to save the state of a running process and restore that process later.

The application can be warmed up before checkpoint. Upon restore, most class loading, object creation, and some startup work are already completed in the snapshot. Resource callbacks help the application close or recover resources that cannot be preserved across a checkpoint.

CRaC is suitable when:

- Instance creation frequency is high.
- Startup and warm-up are time-consuming.
- The heap has significant stable state that can be retained.
- Dependencies can reconnect/reconcile.
- JDK/engine/platform can be controlled.
- The team can maintain Resource lifecycles and restore testing.

Costs include:

- Integrating callbacks and managing resources.
- Creating and storing checkpoint artifacts.
- Testing source-target compatibility.
- Managing image version, age, and invalidation.
- Securing heap snapshots that may contain secrets/data.
- Operating fallback when restore fails.
- Monitoring external state and readiness.

CRaC does not solve state consistency on its own. It helps restore the process quickly; the application must still ensure external state is valid.

## 5. Comparing the solutions

| Solution | Primary startup portion reduced | Application changes | Operational cost | When suitable |
|---|---|---|---|---|
| Startup optimization | Unnecessary initialization, network, and framework work | Low to medium | Low | Almost every application |
| CDS/AppCDS | Class loading and metadata | Low to medium | Low to medium | Class loading is the bottleneck |
| AOT cache/compilation | Partial ahead-of-time analysis/compilation | Medium | Medium | Framework/JDK has appropriate support |
| Native Image | JVM startup and some runtime initialization | Medium to high | High in build/debug | Compatible workload, startup/footprint very important |
| Warm pool | Waiting for new process creation | Low | Idle capacity cost | Predictable traffic or ready capacity needed |
| CRaC | Multiple snapshotted process initialization steps | Medium to high | Higher for lifecycle/artifacts/compatibility | Frequent startups, expensive warm-up, and recoverable state |

The table is a guide, not a benchmark. Actual results depend on framework, JDK, workload, native dependencies, platform, and measurement method.

### 5.1 Solutions can be combined

A system does not necessarily have to choose only one technique.

For example:

- Optimize startup first, then use CDS to reduce class loading.
- Use CRaC for services with high cold starts and a warm pool for extreme bursts.
- Use Native Image for a small worker, keeping the JVM for services with complex dynamic libraries.
- Use a warm pool for the control plane and CRaC for the data plane.
- Use AOT at build time and then checkpoint a warmed-up process if the runtime supports it and the combination is verified.

However, each optimization layer should be measured separately. Combining technologies does not automatically stack benefits; an already optimized step can reduce the marginal benefit of the next step.

## 6. Evaluating by startup frequency

Workloads can be divided into groups to select an initial direction.

| Process creation frequency | Example | Priority direction |
|---|---|---|
| Very low | Long-running service, deployed a few times per week | Startup optimization, CDS/AppCDS |
| Low to medium | Lightly autoscaled API, long-running worker | Startup optimization, CDS/AOT, small warm pool |
| High in bursts | API scaling rapidly when traffic spikes | Warm pool, CRaC, or a combination |
| Very high | Short-lived worker, jobs continuously creating processes | CRaC, Native Image, or redesign into a worker pool |
| Scale-to-zero | Workload barely runs when idle | CRaC or Native Image; compare cost of maintaining a warm pool |
| Per-tenant creation | Each tenant needs a separate runtime | CRaC/Native Image if state is isolated and startup is sufficiently expensive |

High frequency alone is not enough to choose CRaC. If a process takes only 100 ms to start up, the benefit is small. If a process takes 15 seconds but warm-up consists mainly of slow external service calls, checkpointing may reduce internal initialization while still having to reconnect dependencies after restore.

### 6.1 Short startup, high frequency

If JVM startup is already fast and the application context is small, Native Image or CRaC may add more complexity than benefit.

Measure first:

- JVM startup.
- Application context.
- Network initialization.
- Time-to-ready.
- First request.

Sometimes a simple change like removing a synchronous call to an analytics service during startup already solves the problem.

### 6.2 Long startup, low frequency

If startup is long but happens only during deployments or node replacements, startup optimization and CDS usually have a better benefit-to-cost ratio.

Downtime can be reduced with rolling deployments and keeping sufficient old capacity while new instances start. Changing the application lifecycle is not necessarily required.

### 6.3 Long startup, high frequency

This is the group worth evaluating CRaC or Native Image for. Compare:

- The portion of time CRaC can snapshot.
- The portion of time that must be re-executed after restore.
- Checkpoint creation and storage costs.
- Number of restores per image.
- Compatibility testing costs.
- Cost of keeping a warm pool as an alternative.

If most of the startup time is spent on snapshottable data and recoverable resources, CRaC has great potential.

## 7. Evaluating by application state

### 7.1 Simple, rebuildable state

The application has an application context and internal caches, while source data resides in an external database or service. Caches can be reloaded after restore.

This is a good candidate for CRaC if:

- Caches do not contain sensitive data or artifacts are properly protected.
- Caches have revision/TTL.
- Connections can be recreated.
- Instance identity is newly issued.
- Readiness waits for mandatory dependencies.

CDS/AppCDS may still suffice if the bottleneck is primarily class loading.

### 7.2 Large state that is immutable per release

For example, a service loads a large model, rule set, or metadata at startup. If the state does not contain sensitive data and is pinned per release, checkpointing can save loading time.

Bind the image to the digest/version of the model and rule set. If the model changes, old images need to be invalidated or the code must have a safe refresh mechanism.

### 7.3 Continuously changing state

If the process holds continuously updated state without a durable source, the snapshot can become stale very quickly.

Examples:

- Session state living only on the heap.
- In-memory queues without a durable log.
- Uncommitted workflow state.
- Locally updated counters or sequences.
- Distributed locks held inside the process.

Before using CRaC, move critical state into a durable store, use event replay, or define reconciliation rules. Otherwise, a warm pool or startup optimization may carry less risk.

### 7.4 State tied to identity or ownership

Objects such as pod IDs, leader flags, lease tokens, OAuth refresh tokens, or consumer partition assignments should not be cloned as shared state.

After restore, the application needs to:

- Generate a new instance identity.
- Obtain credentials via workload identity.
- Rejoin the broker group.
- Acquire a new lease.
- Use fencing tokens or idempotency keys.
- Not continue side effects based on ownership stored on the heap.

If the application cannot perform these steps safely, CRaC integration cost can be high.

## 8. Integration costs must be accounted for in full

Cost is not just the number of lines of code added. Initial costs and operational costs across the lifecycle must be calculated.

### 8.1 Code and lifecycle costs

With CRaC, identify which resources must:

- Stop before checkpoint.
- Drain requests or transactions.
- Close sockets, pools, and clients.
- Pause schedulers and consumers.
- Recreate after restore.
- Refresh secrets/config.
- Validate before readiness.

Applications using many third-party libraries may need to check each library. If a library holds native handles or background threads without an appropriate lifecycle, integration cost increases.

### 8.2 Build and platform costs

This may require:

- CRaC-enabled JDK distribution.
- Checkpoint engine.
- Compatible host kernel/capabilities.
- Container images pinned by digest.
- Dedicated runners or node pools.
- Artifact storage for checkpoints.
- Dedicated permissions and security policies.
- Source-target compatibility matrix.

With Native Image, costs focus more on build configuration, reflection/resource metadata, native dependencies, and executable debugging.

With a warm pool, costs focus on capacity, scheduling, idle resources, and scaling policies.

### 8.3 Testing costs

CRaC requires testing:

- beforeCheckpoint/afterRestore callbacks.
- Real process checkpoint/restore.
- Source-target matrix.
- External dependency reconciliation.
- Multiple restores from the same image.
- Restore after config/secret/schema changes.
- Failure and fallback.
- Performance and resource usage.

A callback unit test does not replace a real restore test. Similarly, Native Image requires testing the actual executable on the target platform, not just succeeding at compilation.

### 8.4 Security costs

A checkpoint image may contain heap data and decrypted secrets. It requires:

- Synthetic data during image build when possible.
- Scoped credentials with short TTLs.
- Fetching production secrets after restore.
- Encrypting artifacts.
- ACLs and access auditing.
- Retention/revocation.
- Not publishing checkpoints to public registries.
- Verifying multiple replicas do not share tokens or identities.

### 8.5 Long-term operational costs

Account for:

- Rebuilding images on release/runtime changes.
- Restore matrix when kernel/JDK/engine changes.
- Tracking image age and compatibility.
- Managing old artifacts.
- Debugging restore failures.
- Maintaining fallback paths.
- Supporting incidents when callbacks or dependencies fail.

A solution that reduces startup by 8 seconds but requires many hours of operational effort per month may not be economical if only creating a few instances per day.

## 9. Estimating break-even and total cost

Do not compare only startup duration. Bring benefits and costs into the same time period.

A simple model can be used:

~~~text
BenefitPerPeriod =
    NumberOfStarts
    x ValueOfTimeSavedPerStart

CostPerPeriod =
    BuildAndTestCost
    + ArtifactStorageCost
    + RuntimeOverhead
    + OperationsCost
    + IdleCapacityCost
    + FailureRecoveryCost

NetValue =
    BenefitPerPeriod - CostPerPeriod
~~~

ValueOfTimeSavedPerStart can include:

- Reducing requests waiting on cold starts.
- Reducing the number of instances that need to be kept warm.
- Accelerating rollouts or recovery.
- Reducing job completion time.
- Reducing CPU/memory startup overhead.
- Improving user experience.

Do not convert seconds saved into money without first determining the actual impact.

### 9.1 Comparing CRaC with a warm pool

Suppose:

- Each JVM cold start takes 10 seconds.
- The warm pool keeps 3 idle instances.
- An idle instance uses 0.5 CPU core and 512 MiB RAM.
- The system creates an average of 500 new instances per day.
- CRaC restore time is 2 seconds, but requires maintaining builders, matrix tests, and artifact storage.

A warm pool has continuous idle capacity costs. CRaC has per-release image creation and testing costs. The break-even point depends on the number of instance creations and the value of the 8 seconds saved.

### 9.2 Comparing by release lifecycle

For each release, estimate:

- JAR/container build time.
- Warm-up and checkpoint time.
- Restore matrix time.
- Checkpoint storage.
- Number of restores during the release lifetime.
- Operational and incident costs.
- Time saved per instance.

If an image is restored only 5 times before the next release replaces it, checkpointing and testing costs may not be recovered. If an image is restored tens of thousands of times, build costs can become small compared to total benefit.

### 9.3 Factoring risk into the model

Total cost should also include risk:

- Restore failures slowing down rollouts.
- Stale images causing application errors after restore.
- Compatibility drift making images unusable on new nodes.
- Exposure of artifacts containing secrets.
- Duplicate side effects from multiple restored instances.
- Fallback startups causing sudden capacity spikes.

It is not necessary to convert every risk into an exact number. Low/medium/high levels can be used, with release gates placed for unacceptable risks.

## 10. Solution selection matrix

The table below is for initial screening. Evaluate according to the actual workload and a proof of concept.

| Criterion | Startup optimization | CDS/AppCDS | AOT/Native Image | Warm pool | CRaC |
|---|---|---|---|---|---|
| Low startup frequency | Very suitable | Possible | Possible | Often redundant | Likely overly complex |
| High startup frequency | Helpful but limited | Helpful | Suitable if compatible | Suitable if idle cost is acceptable | Suitable if state is recoverable |
| Preserves warmed-up heap | No | No | Does not keep JVM heap | Yes, since process stays running | Yes, from checkpoint |
| Keeps existing connections | Per startup logic | Per startup logic | Per startup logic | Can keep while process is alive | Usually needs recreation |
| Requires Resource callbacks | No | No | No CRaC lifecycle | No | Yes |
| Depends on host/kernel checkpoint | No | Not via process checkpoint | Per native binary/platform | No | Yes |
| Build pipeline changes | Low | Medium | High | Low | Medium to high |
| Idle capacity cost | No | No | No | Yes | Usually lower than warm pool, but has artifact/storage |
| State reconciliation | Per startup | Per startup | Per startup | Per instance lifecycle | Mandatory for dynamic state |
| Fallback | JVM startup | JVM startup | JVM startup/JVM build if maintained | Create new instance | Fresh JVM startup |

### 10.1 Choosing by bottleneck

- If class loading dominates startup: try CDS/AppCDS.
- If the framework has many analysis/initialization steps that can be done ahead of time: try appropriate AOT.
- If application initialization is sequential and optimizable: fix the startup path.
- If ready capacity is needed and the workload is predictable: warm pool.
- If fast cold start is needed, warm-up is expensive, and state is recoverable: CRaC.
- If startup and memory footprint are critical requirements and the application is compatible with native compilation: evaluate Native Image.

Do not choose a technology based solely on another application's benchmark. Frameworks, drivers, dependencies, and application state can make results differ.

## 11. Decision-making process

Walk through the following steps to narrow down the options.

### Step 1 — Set goals

Define specific targets:

- Maximum time-to-ready.
- Maximum first-request latency.
- New instances per minute.
- Acceptable cold start rate.
- Memory footprint per instance.
- Rollout/recovery time.
- Idle capacity budget.

For example: p95 time-to-ready must be under 3 seconds when scaling out 50 instances in one minute. Specific targets help compare options.

### Step 2 — Measure baseline

Run the workload on a near-production environment and measure milestones T0–T7. Determine which portions belong to the JVM, framework, dependencies, caches, and warm-up.

Do not optimize startup before knowing where most of the time is spent.

### Step 3 — Check process creation frequency

Calculate the number of cold starts in a day or release lifetime. Distinguish restarts caused by deploys, autoscale, crashes, and job scheduling.

If startups are rare, lightweight optimization may be sufficient.

### Step 4 — Inventory application state

Classify caches, configs, credentials, connections, sessions, leases, cursors, and native resources. Mark which state is immutable, rebuildable, external-authoritative, or instance-specific.

If state cannot be safely reconciled, address state architecture before choosing CRaC.

### Step 5 — Estimate integration cost

For each option, estimate:

- Code changes.
- Build changes.
- Platform constraints.
- Test coverage.
- Security controls.
- Operational ownership.
- Fallback.
- Per-release maintenance cost.

Do not count only prototype costs; calculate maintenance costs when the JDK, kernel, and dependencies change.

### Step 6 — Select two or three options to test

Usually it is best to compare an optimized baseline with one runtime option and one operational option. For example:

- Startup optimization + CDS.
- CRaC.
- Warm pool.

If Native Image has good compatibility potential, it can be included in a separate proof of concept.

### Step 7 — Run a proof of concept with the same workload

Use the same synthetic data, dependency profile, resource limits, and test scenarios. Measure time-to-ready, first-request latency, memory, CPU, build time, and failure rate.

With CRaC, test real checkpoint/restore on target profiles. With Native Image, test the executable on the target platform. With a warm pool, measure both idle capacity and instance provisioning time.

### Step 8 — Calculate TCO and risks

Compare actual benefits against build, testing, storage, idle capacity, and operations. Identify risks that could block adoption.

### Step 9 — Deploy at a small scope

Select a service or worker with a clear owner, do a canary rollout, and keep a fallback. Do not replace the entire platform before having evidence.

### Step 10 — Re-evaluate after operations

After a few weeks or one release cycle, measure actual cold starts, restore failures, time-to-ready, and costs. The chosen solution may no longer fit as the workload evolves.

## 12. Selection examples by workload type

### 12.1 Long-running API, few restarts

An API runs 20 stable instances, deployed once a day. Startup takes 4 seconds, but rolling deployments always maintain sufficient old capacity.

Selection direction:

- Profile startup.
- Optimize synchronous dependency calls.
- Try CDS/AppCDS if class loading is significant.
- Maintain rolling deployments and proper readiness.
- CRaC is not yet needed if cold start benefits are small.

Reason: instance creation count is not high and the system already hides most startup latency via its deployment strategy.

### 12.2 Short-lived worker, starting thousands of times

A worker processes independent jobs. Each process takes 8 seconds to create the framework context and load the rule set, while the job runs for only 20 seconds.

Selection direction:

- First see whether it can be converted to a long-lived worker pool.
- If process isolation is a requirement, try CRaC with a pinned rule set and retainable cache.
- Evaluate Native Image if the framework and dependencies are compatible.
- Compare with a warm pool and idle capacity costs.

Reason: startup accounts for a large proportion of total job time and process creation frequency is high.

### 12.3 Scale-to-zero service

A service has uneven traffic, with zero instances most of the time. When a request arrives, cold start is 15 seconds.

Selection direction:

- If keeping one warm instance is low-cost, a warm pool may be simplest.
- If true scale-to-zero is desired, try CRaC or Native Image.
- With CRaC, identify which external state must be re-fetched after restore and measure time-to-ready.
- Configure a JVM startup fallback if the checkpoint is incompatible.

Reason: the goal is to reduce time from zero capacity to ready, but idle cost and restore cost must be compared.

### 12.4 Service with a large, rarely changing cache

A service loads a 2 GB reference dataset at startup. The data changes on a weekly release cycle.

Selection direction:

- Can warm up the cache and create a checkpoint per data revision.
- Tag/bind the image with the dataset digest.
- Invalidate the image when the dataset version changes.
- After restore, verify the revision before accepting traffic.
- Evaluate memory footprint and checkpoint download time.

Reason: large, relatively stable data that takes long to load can be state worth preserving.

### 12.5 Stateful stream processor

A consumer holds offsets, assignments, and state on the heap. The broker may rebalance while the process is checkpointed.

Selection direction:

- Prioritize durable state, replay, and consumer group coordination.
- Use idempotent processing and proper commit semantics.
- If using CRaC, stop the consumer before checkpoint and rejoin the group after restore.
- Do not resume old assignments or use offsets stored only on the heap.
- Test duplicate processing and failover.

Reason: state has ownership and ordering semantics; startup speed must not compromise correctness.

### 12.6 Application with complex native dependencies

The application uses JNI, native threads, specialized drivers, and file mappings. Startup is slow, but native state is hard to recover.

Selection direction:

- Measure whether the bottleneck is in Java class loading.
- Try CDS/AOT or startup optimization first.
- Evaluate Native Image if the native dependencies are supported.
- Choose CRaC only after a proof of concept with the real engine/platform and clear callback lifecycles.

Reason: integration cost and compatibility risk may outweigh the benefit.

## 13. What should a proof of concept measure?

A useful PoC must compare options on the same workload.

| Category | Metrics |
|---|---|
| Startup | p50/p95/p99 time-to-ready |
| Request | First-request latency and post-warm-up latency |
| Scale | Instance creation rate and cold start percentage |
| CPU | CPU time during startup and warm-up |
| Memory | RSS/PSS, heap, and native memory |
| Build | Build time and artifact size |
| CRaC | Checkpoint time, restore time, artifact size, callback time |
| Native Image | Native build time, executable size, runtime footprint |
| Warm pool | Idle CPU/RAM and pool miss rate |
| Reliability | Restore/startup failure rate, readiness failure |
| Integration | Number of resources requiring callbacks or custom configuration |
| Operations | Time spent on incident handling, retesting, and release maintenance |

### 13.1 Keep the workload identical

For a fair comparison:

- Same application version.
- Same dependency versions.
- Same dataset or synthetic fixture.
- Same CPU/memory limits.
- Same target node class.
- Same number of warm-up requests.
- Same readiness criteria.
- Same external dependency latency.
- Same number of iterations.

If one option runs on a faster node or closer database, the results are no longer directly comparable.

### 13.2 Measure failure paths as well

With CRaC, test restore failures due to unavailable dependencies, config mismatches, or invalid target profiles. With Native Image, test startup when resources or native dependencies are missing. With a warm pool, test when the pool is exhausted.

A good solution must have clear fallback and failure behavior, not just attractive benchmark results under ideal conditions.

## 14. Signs that CRaC is a suitable choice

CRaC deserves to be shortlisted when several of the following conditions hold simultaneously:

- There are many new process creations.
- Startup and warm-up make up a significant portion of time-to-ready.
- Much initialization overhead can be snapshotted and reused.
- Application state can be classified and reconciled.
- Resource lifecycles can be managed via callbacks.
- JDK/engine/host platform can be pinned and tested.
- Ability to protect checkpoint artifacts.
- The team has the capability to operate the compatibility matrix and rebuild policy.
- Measured benefits exceed build/test/operations costs.

CRaC is less suitable when:

- Startup is already fast.
- Processes rarely restart.
- Most startup time is in external dependencies that still must run again after restore.
- The application holds non-durable state that cannot be reconciled.
- Native resources cannot be safely recovered.
- The restore environment changes continuously and cannot be controlled.
- Checkpoint artifacts cannot be protected.
- Integration cost exceeds cold start benefits.

These are screening criteria, not a prohibition list. Only a PoC on the actual workload can confirm costs and benefits.

## 15. Common mistakes when choosing a solution

### Choosing a technology based on another application's benchmark

Startup time depends on framework, dependencies, data, and host. External benchmarks only help form hypotheses. Measure your own application.

### Confusing request frequency with startup frequency

An API with many requests but few new instances may not need a cold start solution. Count actual process creations.

### Measuring only JVM startup

Time-to-ready also includes framework, network, caches, and readiness. Measure the entire path.

### Choosing CRaC for fast restore while ignoring state

Process restore is fast, yet connections, secrets, leases, and broker assignments still need recovery. Measure time-to-ready after reconciliation.

### Choosing Native Image without checking dependencies

Reflection, dynamic class loading, and native libraries can complicate migration. Build a PoC with actual dependencies.

### Using a warm pool without accounting for idle cost

Always-ready instances consume resources when there is no traffic. Measure pool miss rate and idle CPU/RAM.

### Lazy initialization slowing down the first request

Moving work out of startup can increase first-request latency. Measure both startup and the request path.

### Ignoring fallback

Checkpoint restore or a native executable can fail on a new target. Keep a safe startup path and test it.

### Not accounting for maintenance costs

Each new JDK, kernel, dependency, or release can trigger retesting/rebuilding. Calculate lifecycle costs, not just PoC costs.

## 16. Selection checklist

Before deciding, answer the following questions:

### Startup frequency

- How many new instances per hour/day?
- Do cold starts occur due to autoscaling, deployment, crashes, or job scheduling?
- What percentage of job duration does startup consume?
- Does p95/p99 time-to-ready violate the SLO?
- Can a warm pool meet requirements at an acceptable cost?

### Application state

- Which state resides on the heap?
- Which state can be rebuilt?
- Which state has an external authoritative source?
- Are credentials and identities freshly acquired after restore?
- Can connections, threads, schedulers, and native resources be recovered?
- Does restoring multiple instances cause duplicate side effects?
- Do caches have version/TTL and an invalidation policy?

### Integration cost

- Can JDK/engine/host platform be pinned?
- Are self-hosted runners or dedicated node pools required?
- How many resources require callbacks?
- Can real restore tests be run in CI?
- Are artifact storage and access control already in place?
- Can the team maintain the compatibility matrix and age policy?
- Is the fallback path tested?

### Business and operational outcomes

- What is the specific time-to-ready target?
- How many seconds of cold start are actually saved?
- Does the benefit translate into latency, throughput, or cost improvements?
- What are the build, storage, idle capacity, and operations costs?
- Are remaining risks within acceptable limits?

## 17. Selection and deployment workflow

A workflow that can be applied to a Java service:

**Step 1 — Measure baseline.** Collect startup phases, time-to-ready, first-request latency, and process creation frequency in a near-production environment.

**Step 2 — Identify bottlenecks.** Separate class loading, framework initialization, dependency connections, data loading, and warm-up.

**Step 3 — Classify application state.** Document caches, configs, credentials, connections, sessions, leases, cursors, and native resources.

**Step 4 — Create a shortlist.** Select startup optimization, CDS/AOT, Native Image, warm pool, or CRaC based on bottlenecks and state.

**Step 5 — Estimate integration cost.** Account for code, build, platform, testing, security, and operations across the release lifecycle.

**Step 6 — Run a fair PoC.** Use the same workload, dependencies, data, resource limits, and target profiles; measure both startup and time-to-ready.

**Step 7 — Test failures and fallback.** Test dependency outages, target mismatches, credential refreshes, and restore/startup failures.

**Step 8 — Compare TCO.** Bring startup savings, idle capacity, build/testing, artifact storage, and operational effort into the same time period.

**Step 9 — Canary rollout.** Deploy a small workload, monitor latency, failure rate, and resource usage.

**Step 10 — Expand or adjust.** Expand only when actual benefits exceed costs and the team can maintain the lifecycle.

## 18. Selection conclusion

Startup frequency indicates how often cold start benefits can occur. Application state indicates which parts can be safely retained and which must be recovered. Integration cost indicates whether the team can sustain the solution throughout the application's lifecycle.

For rare startups, prioritize optimizing the startup path and low-lifecycle-change mechanisms like CDS/AppCDS. For frequent startups where the application can run in a warm pool, compare the cost of maintaining idle capacity against other options. For scale-to-zero or continuous process-creation workloads, CRaC and Native Image are worth testing if state and dependencies fit. For stateful or native-heavy applications, evaluate recovery costs and consistency before focusing on speed.

A good decision is based on time-to-ready, startup frequency, state recovery, compatibility, and measured total operational cost. Run a PoC on the actual workload and keep a clear fallback before broad adoption.

## References

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): checkpoint/restore model and application coordination.
- [CRaC — Running an Application With CRaC](https://docs.azul.com/crac/usage/running-crac): preparing the runtime and running a CRaC application.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): Resource callbacks before checkpoint and after restore.
- [OpenJDK — Class Data Sharing](https://openjdk.org/jeps/310): Application Class-Data Sharing.
- [Java Launcher — Class Data Sharing](https://docs.oracle.com/en/java/javase/21/vm/class-data-sharing.html): configuring CDS and AppCDS in the JVM.
- [GraalVM — Native Image](https://www.graalvm.org/latest/reference-manual/native-image/): compiling Java applications into native executables.
- [GraalVM — Native Image Build Configuration](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildConfiguration/): build configuration and metadata for Native Image.
- [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/reference/packaging/aot.html): AOT processing in Spring Boot.
- [Kubernetes — Horizontal Pod Autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/): scaling workloads on demand.
- [Kubernetes — Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): pod lifecycle and readiness state.
