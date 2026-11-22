# Slow startup and the warm-up phase of Java applications

In a long-running Java application, the time from process launch until the application reports ready is often not the whole story of startup performance. After the application reports ready, the first requests can still be noticeably slower than subsequent requests. The JVM is still loading classes, compiling hot code, building internal structures, and the application continues initializing caches or connections to external services. This period is called the **warm-up phase** (*warm-up*).

In the context of **CRaC (Coordinated Restore at Checkpoint)**, these two phenomena are particularly important. CRaC allows creating a checkpoint of a running Java process and restoring a process from that checkpoint. If the checkpoint is taken after the application has been properly initialized and warmed up, restoring can reuse much of the prepared state, thereby reducing the time to bring the application into service. To gain this benefit, you need to understand where the application spends time, choose the right checkpoint moment, and handle resources that cannot continue to be used after restoration.

## 1. Distinguishing startup and warm-up

The two concepts are related yet describe different phases.

**Startup** is the process of starting a new Java process and bringing the application to a state where it can accept work. This process can include initializing the JVM, loading classes, creating objects, initializing frameworks, reading configuration, opening connections, and running readiness checks.

**Warm-up** is the process in which the application gradually reaches steady-state performance after starting to run. The JVM observes frequently executed code segments to compile them with the JIT compiler; the application may also populate caches, build metadata, establish connection pools, or finish *lazy initialization*.

An application can finish startup and pass its readiness probe while still warming up. Therefore, a “ready” state does not necessarily mean a “steady-state throughput and latency” state. A system can have a short startup time while still experiencing high latency on early requests.

| Aspect | Startup | Warm-up |
|---|---|---|
| Timing | From process start until the application is ready | After the process starts; can continue past readiness |
| Typical work | JVM initialization, class loading, framework setup, reading configuration | JIT compilation of hot code, exercising business paths, populating caches |
| Symptom | High time to readiness | Slow initial requests, elevated CPU, initially low throughput |
| Goal | Bring the application into a serviceable state | Bring performance to a stable and predictable level |

A typical timeline:

```text
Process starts
       |
       v
Initialize JVM and load classes
       |
       v
Initialize frameworks, configuration, resources
       |
       v
Application reports ready  <---- startup ends per readiness
       |
       v
First requests, JIT, and caches continue warming up
       |
       v
Latency and throughput approach steady state
```

The boundary between the two phases is not absolute. For example, if an application proactively performs warm-up before reporting readiness, part or all of warm-up falls inside the measured startup time. When comparing two deployment approaches, agree on consistent definitions of start and end points.

## 2. Why can Java applications start slowly?

Startup time is usually the sum of many small tasks. The biggest contributors depend on the application, frameworks, libraries, runtime environment, and deployment method.

### 2.1. JVM initialization work

Before application code actually processes business logic, the JVM must set up the execution environment. Tasks can include:

- Initializing structures to manage the heap, garbage collector, threads, and runtime.
- Loading, *verifying*, *linking*, and *initializing* required classes.
- Creating class loaders and loading class metadata into the corresponding memory regions.
- Setting up components for JIT compilation and compiled code management.
- Initializing standard libraries or native libraries used by the application.

Not every class is loaded immediately when the JVM starts. Many classes are loaded only when an execution path requires them. Consequently, part of the class-loading cost appears on the first request rather than entirely during startup.

### 2.2. Framework and application initialization

Java frameworks typically perform substantial work to assemble the application before serving requests. For instance, a Spring application may scan components, build an application context, resolve dependencies, generate proxies, configure the web server, register converters, and instantiate beans. An application using an ORM may need to read mappings, construct metadata, prepare statements, or initialize persistence-related components.

Other libraries may also perform classpath scanning, read annotations, load schemas, compile expressions, create serializers, or build registries. Some operations take time due to large numbers of classes and dependencies; others take time due to performing I/O or waiting on external services.

### 2.3. Reading configuration and depending on external services

Applications commonly read configuration files, environment variables, secrets, certificates, and connection details. Afterward, the application may connect to databases, message brokers, caches, identity services, or centralized configuration systems.

Network wait times, DNS, TLS handshakes, authentication, and retries can lengthen startup. If a dependency is temporarily unresponsive, the application can be much slower than when running in a development environment. Measuring startup only on a local machine can miss these costs.

### 2.4. Lazy initialization

To reduce startup time, an application or framework may defer certain work until first use. This helps the process report ready sooner, yet shifts the cost to the first request.

For example, invoking a feature for the first time may require creating a serializer, loading metadata, opening a connection, loading a rarely used class, or initializing a bean. If this feature lies on a critical request path, users will notice latency even though the readiness probe already succeeded.

## 3. Why are the first requests often slow?

### 3.1. JIT compilation and hot code

Java usually compiles bytecode to machine code while the program runs. The JIT compiler monitors execution behavior, such as which methods are called frequently and which branches are commonly taken. When a method becomes “hot”, the JVM can compile it at higher optimization levels.

Early on, some code segments may run in the interpreter or as lower-optimization compiled code. Once the JVM gathers enough profiling information, it can recompile to improve performance. Therefore, the first requests simultaneously execute business work and generate profiling data for the JIT compiler.

This process is commonly called **JVM warm-up**. It does not have a fixed duration: a small application may stabilize quickly, whereas an application with many business paths or fluctuating traffic may take longer. Execution paths never exercised are also unlikely to be warmed up yet.

### 3.2. Caches and runtime-generated data

Applications typically have caches across multiple layers:

- Application-level caches, such as reference data, computation results, or metadata.
- Caches belonging to libraries, frameworks, ORMs, and serializers.
- Caches of the OS, filesystem, or DNS resolver.
- Connection pools and structures holding session state.

On the first run, caches may be empty. The application must fetch data from sources, parse, transform, and store it. Subsequent requests can be faster because they reuse already generated results.

Not every cache can or should be kept in a checkpoint. Caches containing shared, regenerable, instance-independent data are usually more suitable. Caches holding sensitive data, per-user data, or time-limited data must be evaluated separately.

### 3.3. Connections and resources initialized on first use

A connection pool may create connections only upon the first request. TLS sessions, HTTP clients, message broker channels, or clients to other services may also be lazily created. Consequently, the first request pays resource setup costs before finishing the main work.

### 3.4. Workload shape and traffic

Warm-up depends on which execution paths are exercised. Repeatedly hitting one simple endpoint does not ensure other critical endpoints are warmed up. An application with diverse request types, payloads, or processing branches needs a representative workload to warm up meaningful paths.

## 4. Impact on the system

Slow startup increases the time to deploy new versions, scale replica counts, or recover services after failures. In autoscaling or serverless environments, this time can directly increase how long users wait for a new instance.

Slow warm-up creates a period where latency and throughput are unstable. Early requests can spike p95 or p99 latency; CPU may rise due to JIT compilation and cache population. If the system receives heavy traffic right after a new instance is added, warm-up can happen concurrently with real load, reducing serving capacity precisely when the system needs to scale out.

Therefore, measuring only from running the `java` command until the HTTP port opens is insufficient. You must also measure time to readiness, first-request latency, time to reach steady throughput, and resource consumption during that window.

## 5. Measuring startup and warm-up

Before optimizing, identify where time is being spent. A baseline measurement suite should distinguish the following milestones:

| Metric | Meaning |
|---|---|
| Process start time | Moment the JVM process begins |
| Application ready time | Moment the application passes readiness checks |
| First-request latency | Latency of the first request for each critical business flow |
| Warm-up duration | Time from starting the workload until performance stabilizes per chosen criteria |
| Steady-state latency | Latency once the application has stabilized; inspect p50, p95, and p99 |
| Throughput | Number of requests or tasks completed per unit of time |
| CPU and GC | CPU cost, garbage collection activity, and memory usage in each phase |

You can record timestamps at key initialization milestones inside the application while using framework startup logs and readiness probes to pinpoint readiness. JDK Flight Recorder (JFR), JVM observability tools, and profilers help reveal significant class loading, JIT compilation, allocation, GC, thread contention, and I/O activity.

When measuring, use the same JDK version, heap configuration, CPU/memory limits, image, application config, and network environment. Run multiple trials from a cold state to avoid mistaking OS or external service caches for genuine improvements. Use a representative workload, separate startup results from steady-state results, and record both latency and throughput.

A useful measurement should answer three questions:

1. How long does the application take to become ready to accept requests?
2. Which requests or tasks remain slow during the initial phase?
3. After how long, and under what load, does performance reach the defined stability threshold?

“Stability” must be defined by measurable criteria, for example p95 latency staying within a target range and throughput no longer rising significantly across consecutive measurement windows. Do not pick a fixed iteration count and assume every application has warmed up.

## 6. Ways to reduce startup and warm-up without CRaC

CRaC is one option in an optimization strategy, yet conventional measures remain worth understanding because they can be combined together.

**Reduce unnecessary initialization work.** Remove unused dependencies, limit overly broad classpath scanning, and avoid initializing clients or beans unneeded for the main serving path. Audit synchronous network calls during startup and configure appropriate timeouts.

**Choose initialization timing deliberately.** Eager initialization avoids first-request latency at the expense of longer startup. Lazy initialization makes the application ready sooner yet may shift cost onto the first user. Decisions should be based on actual latency and readiness requirements.

**Warm up with a representative workload.** Exercise critical endpoints or tasks with suitable test data to trigger needed classes, business paths, and JIT compilation. Do not merely repeat one endpoint unrepresentative of real load.

**Consider Class Data Sharing (CDS/AppCDS).** CDS can help reduce part of class-loading cost by sharing prepared class metadata. It does not save full running application state and does not replace warming up business paths.

**Evaluate ahead-of-time compilation or native images when appropriate.** AOT or native image solutions change how the application is compiled and executed, which can improve startup in some cases. They carry different compatibility, build, optimization, and runtime models compared to the regular JVM; measure on the actual application.

## 7. How does CRaC solve startup and warm-up?

CRaC stands for **Coordinated Restore at Checkpoint**. The core idea is bringing the application to a prepared state, taking a process checkpoint at that state, and using the checkpoint to restore a new process.

With normal startup, each new replica must re-run many steps: initializing the JVM, loading classes, creating the application context, performing part of warm-up, and setting up resources. With CRaC, one process can execute the expensive steps beforehand, run a warm-up workload, and then create a checkpoint. Upon restore, the process resumes from the saved state and runs the required resource recovery callbacks.

```text
Prepare checkpoint
  Start application
        |
        v
  Initialize frameworks and application
        |
        v
  Run warm-up workload
        |
        v
  Prepare resources for checkpoint
        |
        v
  Save checkpoint

Start new instance
  Restore from checkpoint
        |
        v
  Recover resources and environment-dependent state
        |
        v
  Check readiness and serve requests
```

A checkpoint saves process state at a single point in time. Thus, in-memory states already built before the checkpoint can be reused upon restore, depending on the CRaC JDK, platform, and deployment configuration. This can avoid repeating substantial initialization and warm-up work. Actual improvement must be measured on the exact target application and environment.

CRaC does not make all costs vanish. The system must still restore the process, finish callbacks, reconnect services, validate state, verify readiness, and handle data that changed since the checkpoint. If a checkpoint is taken too early, before critical paths have warmed up, warm-up benefits will be limited.

## 8. Choosing the right moment to take a checkpoint

A checkpoint should represent a stable baseline state that multiple instances can safely share. Typically, the process should complete these steps before checkpointing:

1. Read baseline configuration and initialized essential application components.
2. Created objects, metadata, and caches that can be shared safely across instances.
3. Executed a warm-up workload representative of critical paths.
4. Met defined steady-state performance criteria, if the goal includes saving JIT state and warmed caches.
5. No in-flight user requests or incomplete transactions remain.
6. Prepared resources that must be closed, paused, or recreated during the checkpoint/restore lifecycle.

Do not checkpoint while the application is actively handling user requests, performing incomplete data writes, or holding per-session private state. A checkpoint captured from an inconsistent state can cause every instance restored from it to inherit the same defect.

Warm-up must also avoid generating real business data. Use test data or safe, repeatable, side-effect-free operations. If a warm-up request sends emails, creates orders, or writes real records, the checkpoint will be created after those side effects occurred and every checkpoint-preparation run may repeat them.

## 9. Managing resources with CRaC Resource

A running process can hold environment-specific resources: sockets, database connections, file descriptors, background threads, locks, timers, TLS clients, or message broker connections. After the process is checkpointed and restored, some resources may have expired, become invalid, or be unusable in the new environment.

CRaC provides the `org.crac.Resource` API so the application can coordinate the lifecycle of those resources. A resource implements two callbacks:

- `beforeCheckpoint(...)`: prepares the resource before saving the checkpoint. Depending on the resource kind, the application may stop accepting new work, complete active work, close connections, or release locks.
- `afterRestore(...)`: restores or recreates the resource after the process is restored. For example, creating a new connection pool, reopening files, or restarting background workers.

The example below illustrates a resource managing an object that can be closed and recreated. `createPool()` and `close()` represent the concrete logic of the connection pool library used by the application:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class PoolResource implements Resource {
    private final PoolFactory poolFactory;
    private AutoCloseable pool;

    public PoolResource(PoolFactory poolFactory) throws Exception {
        this.poolFactory = poolFactory;
        this.pool = poolFactory.createPool();
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        if (pool != null) {
            pool.close();
            pool = null;
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        pool = poolFactory.createPool();
    }

    public interface PoolFactory {
        AutoCloseable createPool() throws Exception;
    }
}
```

This is a skeleton example to show the lifecycle. In a real application, ensure all components using the pool have stopped using it before closing, and dependent components only receive the new pool once restore completes. Specific integration depends on the framework and connection library.

A Resource can be registered with the global context or a context matching the application structure. Read the documentation of the CRaC JDK in use to confirm APIs, callback ordering, and platform limits. If a library already has CRaC integration, prefer using the supported integration rather than managing the same resource twice yourself.

## 10. States to verify before and after restore

Not every Java object on the heap can be used indefinitely after restore. Review the following state groups:

| State group | Potential issue | Common handling approach |
|---|---|---|
| Sockets and network connections | Connection closed by peer, address or route changed | Close before checkpoint; create new connections after restore |
| Databases and connection pools | Old connections timed out or closed by server | Close old pool, create new pool, and verify connections |
| HTTP/TLS clients | Sockets, sessions, or certificates no longer valid | Recreate client or refresh environment-dependent resources |
| DNS and service addresses | Cached resolution results no longer accurate | Re-resolve per application DNS policy |
| Files and file descriptors | Mounts, paths, or file states changed | Close/reopen files and verify access permissions |
| Threads and executors | Workers stopped, holding locks, or in invalid states | Stop gracefully before checkpoint; restart after restore |
| Timers and periodic tasks | Schedules based on pre-checkpoint wall time | Recalculate schedules and avoid unintended catch-up runs |
| Tokens, secrets, and certificates | Expired or rotated after checkpoint | Fetch fresh values from the secret source |
| Caches and config data | Stale data or bound to one instance | Refresh, invalidate, or validate TTL after restore |

A useful principle is separating **shareable state** from **instance-specific state**. Immutable metadata or shared caches may be appropriate to include in a checkpoint. IP addresses, dynamically assigned ports, short-lived tokens, instance IDs, and active request state usually need to be set or refreshed after restore.

Callbacks should be safely repeatable whenever possible. If a recovery callback fails, the application must report a clear error and refuse traffic until essential resources are ready. Readiness probes should reflect real post-restore state rather than merely checking that the process exists.

## 11. High-level CRaC deployment workflow

The exact workflow depends on the CRaC-supporting JDK distribution, OS, container runtime, and checkpoint/restore platform. A typical workflow includes the following steps:

**Step 1: Prepare a compatible environment.** Choose a CRaC JDK and supported environment. Check requirements for the OS, kernel, checkpoint/restore mechanism, container privileges, native libraries, and checkpoint storage. Checkpoints are usually tightly tied to the environment that created them; do not assume a checkpoint can restore on any arbitrary machine or image.

**Step 2: Start the application to establish baseline state.** Use the exact artifacts, configuration, and dependency versions intended for deployment. Avoid embedding single-instance-specific data into the baseline state.

**Step 3: Run warm-up.** Send a representative workload to activate critical business flows, JIT compilation, caches, and necessary lazy initialization. Measure until stability criteria are met.

**Step 4: Prepare resources.** Register `Resource` handlers for resources needing coordination. Stop accepting new work, finish in-flight work, and close or release resources that cannot cross a checkpoint.

**Step 5: Create the checkpoint.** Use the checkpoint mechanism specified by the documentation of your JDK and deployment platform. Some distributions provide dedicated JVM options and diagnostic commands; syntax and support levels may vary across distributions.

**Step 6: Launch from the checkpoint and verify.** Upon restore, `afterRestore` callbacks must recreate resources. Check readiness, service connections, logs, metrics, and a few representative requests before placing the instance under real traffic.

**Step 7: Measure and compare.** Compare against normal cold start under identical conditions. Measure restore-to-readiness time, first requests, remaining warm-up, throughput, p95/p99 latency, CPU, and error rates. If most of the time is still spent connecting to external services, CRaC may not improve that metric much.

## 12. Comparing CRaC with CDS and native image

These techniques all aim to reduce startup cost yet address problems at different layers.

| Technique | Approach | Cost portion reduced | Key considerations |
|---|---|---|---|
| CDS/AppCDS | Share prepared class data | Part of class loading and class metadata processing | Does not save full running application state |
| CRaC | Save and restore process state at checkpoint | Can reuse initialized/warmed JVM and application state | Requires resource coordination and restore-environment compatibility |
| GraalVM Native Image/AOT | Ahead-of-time compilation into a native executable | Can reduce JVM initialization and runtime JIT dependence | Carries trade-offs in compatibility, build time, optimization, and runtime model |

There is no single best choice for every application. If startup is dominated by framework initialization and warm-up, CRaC may be worth testing. If class-loading cost dominates, CDS can help. If ultra-fast startup is required and the application fits the AOT model, native image may be another option. Measure on actual workloads and deployment environments before deciding.

## 13. Common design mistakes

**Taking a checkpoint before meaningful warm-up.** On restore, the application still has to load classes or compile unexercised paths. Use a representative workload and measure post-restore performance.

**Keeping old network connections intact.** A socket may no longer be valid after checkpoint duration or inside the restore environment. Manage connection lifecycles via callbacks and check for reconnection errors.

**Leaving background workers running during checkpointing.** Workers may be holding locks, processing messages, or mid-way through updating data. Stop accepting new work and define how to complete or bring jobs to a recoverable state.

**Putting instance-specific data into the checkpoint.** For example, the checkpoint contains the IP address, short-lived token, or instance ID of the checkpoint-creation process. When multiple replicas share a checkpoint, that state can cause conflicts or routing errors. Regenerate instance-specific data after restore.

**Failing to update expired state.** Tokens, certificates, DNS caches, and configuration data can change while a checkpoint is stored. Restore callbacks must refresh time-sensitive or mutable data.

**Marking ready too early.** The process may have restored while pools are not yet built or workers are not running. Readiness must wait until essential resources are ready.

**Comparing benchmarks under mismatched conditions.** Comparing a cold start on an idle machine against a restore in an environment with different CPU or I/O leads to wrong conclusions. Control configuration and run repeated trials.

**Treating checkpoints as harmless artifacts.** Memory state can contain secrets, tokens, user data, or internal information. Control read/write permissions, storage locations, retention periods, and deletion procedures for checkpoints.

## 14. Design checklist for a Java application using CRaC

Before putting CRaC into production, the development team can use the following questions to review the design:

- [ ] Have startup, readiness, first-request latency, and warm-up duration been measured separately?
- [ ] Does the checkpoint-preparation workload represent critical paths?
- [ ] Has it been determined which state is safe to share across instances?
- [ ] Have sockets, pools, files, threads, timers, locks, and environment-dependent resources been inventoried?
- [ ] Does every necessary resource have a way to close before checkpoint and recreate after restore?
- [ ] Does the application prevent in-flight requests or incomplete transactions from entering the checkpoint?
- [ ] Are secrets, tokens, certificates, and time-sensitive data refreshed when needed?
- [ ] Does readiness succeed only after callbacks and essential resources have completed?
- [ ] Has restore been tested in the exact target image, kernel, JDK, and deployment configuration?
- [ ] Have error rate, latency, throughput, CPU, and memory been measured after restore?
- [ ] Is the checkpoint protected as an artifact containing sensitive memory state?

## Conclusion

Slow startup and slow warm-up are two distinct sources of latency. Startup primarily reflects the cost of process creation and application initialization; warm-up reflects the JVM and application reaching steady-state performance as workload executes. Measure both phases separately to pinpoint the true root causes.

CRaC can substantially reduce repetitive work when spinning up new instances by restoring an already initialized and warmed process. Effectiveness depends on checkpoint quality, the warm-up workload, and resource management capability. When an application properly closes/reopens resources, refreshes environment-dependent state, and signals readiness only after restoration completes, CRaC can shorten the time to bring a Java application into service while preserving the JVM execution model.