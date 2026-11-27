# Designing Health Checks, Self-Healing, and Graceful Shutdown

## 1. Reliability Starts with How Failures Are Detected and Handled

A cloud service can run on VMs, containers, Kubernetes, functions, or managed platforms. Even when the platform provisions resources automatically, a process can hang, fail startup, lose database connectivity, exhaust threads, run out of memory, or stop completing requests on time. An existing instance is not necessarily serving well; a process answering a test endpoint is not necessarily ready to accept traffic.

Three capabilities must work together:

- **Health checks:** provide structured signals on whether a component has started, can accept traffic, or needs restarting.
- **Self-healing:** the platform or application detects failure states and takes recovery actions such as restarting a process/container, replacing an instance, rescheduling a pod, or recreating a replica.
- **Graceful shutdown:** the component stops accepting new work, completes or hands off in-flight work, closes connections, and exits within the allowed deadline.

If health checks are misdesigned, the system may endlessly restart an app merely waiting on a dependency; without readiness checks, load balancers may route requests to booting instances; if shutdown is abrupt, requests or messages may be lost, processed twice, or leave transactions in ambiguous states.

In the **CLOUD_ARCHITECTURE** module, health checks and workload lifecycles are integral to reliability design. They must be evaluated alongside SLOs, failure domains, dependencies, autoscaling, deployment strategies, retries, queue semantics, and operability.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish startup, readiness, and liveness checks, and choose the right action for each signal.
2. Design safe, fast health endpoints that do not overload dependencies.
3. Combine application, container platform, and load balancer health checks.
4. Design self-healing across processes, containers, nodes, and failure domains.
5. Handle crash loops and unhealthy dependencies while avoiding cascading failures.
6. Design graceful shutdown with draining, termination signals, deadlines, and in-flight work handling.
7. Protect queue messages, transactions, and connections when workers stop.
8. Test failure/recovery scenarios and define metrics, alerts, and runbooks.

## 2. Three Types of Probes: Startup, Readiness, and Liveness

Do not lump every health question into one endpoint returning 200 or 500. Three probe types serve three distinct decisions.

| Probe | Question | On failure | Used to |
|---|---|---|---|
| **Startup** | Has the application finished initial initialization? | Startup is not marked complete yet; platform keeps waiting or eventually restarts per policy | Protect apps with slow startup, model loading, or long migrations/init |
| **Readiness** | Can this instance safely accept new work right now? | Removed from endpoints/traffic or stops receiving new tasks | Prevent requests from hitting unready or draining instances |
| **Liveness** | Is the process still making progress and able to continue? | Restarts the process/container per platform config | Recover deadlocked/hung processes or unrecoverable internal states |

### 2.1. Startup Probes

Startup probes give slow-starting apps time to initialize without being prematurely killed by liveness probes. For instance, an inference service needing to load models, initialize runtimes, and warm caches. Before startup succeeds, the platform waits within a defined budget and never routes traffic to an unready service.

Startup probes should not wait forever. Set thresholds from startup duration p95/p99, deployment time limits, and recovery SLOs. If startup frequently breaches thresholds, investigate image size, dependency initialization, model loading, or resource limits.

### 2.2. Readiness Probes

Readiness determines whether an instance can accept new requests. An instance can be alive yet unready:

- Loading configuration or warming caches.
- Not yet having established required connection pools.
- Draining before shutdown.
- Hitting saturation and intentionally pausing new work intake.
- An essential dependency is temporarily unresponsive, where restarting the process would not fix it.

Readiness failure should generally instruct load balancers/service routers to stop sending new traffic; it should not necessarily restart the instance. Once conditions recover, the instance can return to ready.

### 2.3. Liveness Probes

Liveness checks whether the process is still alive and making progress—for example, whether an event loop is deadlocked, an internal worker thread is stuck, or the main service loop stopped processing work.

Liveness failures can trigger restarts. Thus probes must check things a restart can actually fix. Do not tie liveness directly to every external service such as databases, payment providers, or DNS; a dependency outage could cause every replica to restart simultaneously, worsening the incident.

### 2.4. Decision Flow

~~~mermaid
flowchart TD
    Start["Workload starts"] --> Startup{"Startup complete?"}
    Startup -->|No| Wait["Continue bounded startup checks"]
    Wait --> Startup
    Startup -->|Yes| Ready{"Can accept new work?"}
    Ready -->|No| Out["Keep out of traffic / wait"]
    Out --> Ready
    Ready -->|Yes| Serve["Serve requests"]
    Serve --> Live{"Process making progress?"}
    Live -->|Yes| Serve
    Live -->|No, recoverable by restart| Restart["Restart workload"]
    Restart --> Start
~~~

This is a logical model. Platforms combine probes, health states, and restart policies differently; verify the exact semantics of your platform.

## 3. What Should Health Endpoints Check?

A health endpoint must drive a clear decision, not act as an expensive aggregator calling every dependency.

### 3.1. Process Health vs. Dependency Health

| Check | Which probe? | Reasoning |
|---|---|---|
| Main event loop/thread still responsive | Liveness | Is internal progress occurring? |
| Startup/config loaded | Startup | Did mandatory init finish? |
| App can handle simple requests | Readiness | Ready to receive new traffic? |
| DB connection pool usable | Readiness or separate dependency status | Is DB required for every request? |
| Payment provider is down | Usually dependency status/feature degradation | Restarting the entire API will not fix a provider outage |
| Queue consumer still accepting messages | Worker readiness | Can it accept and process new work? |
| Disk usage rising | Monitoring/alerts, sometimes readiness | Define thresholds and recoverability |
| Thread pool exhausted | Readiness/saturation signal; investigate liveness separately | Instance may fail to serve requests even while process runs |

### 3.2. Do Not Turn Health Checks into Load Tests

Health checks are invoked periodically by control planes, endpoint monitors, and load balancers. If every probe runs heavy queries, calls multiple services, or scans full caches, the probes themselves can overload the system.

Best practices:

- Keep probes fast with tight deadlines.
- Use lightweight checks, bounded queries, and zero side effects.
- Cache dependency health briefly if needed instead of fanning out on every probe.
- Avoid synchronized probes firing simultaneously across all replicas; add jitter if appropriate.
- Separate detailed diagnostic endpoints for dashboards from simple probe endpoints.
- Never expose secrets, connection strings, internal hostnames, or stack traces on public endpoints.

### 3.3. Health States Should Have Stable Semantics

An application can represent health state as:

~~~json
{
  "status": "NOT_READY",
  "checks": {
    "startup": "READY",
    "request_handler": "READY",
    "database_pool": "DEGRADED",
    "shutdown": "DRAINING"
  }
}
~~~

This is an illustrative internal payload, not a mandatory standard schema. Readiness endpoints may simply return platform-expected status codes, while secured diagnostic endpoints expose details. While draining, readiness must fail or the service registry must mark the instance unavailable for new requests.

## 4. Liveness Must Not Blindly Depend on the Database

A common design mistake is a liveness endpoint running `SELECT 1` against the database. When the DB has an outage, every API replica goes unhealthy and enters a restart loop. Once the DB recovers, all replicas boot together and trigger a connection storm.

Separate clearly:

- **Process liveness:** is the application making progress?
- **Readiness:** can the application accept new workloads?
- **Dependency health:** what state are databases, queues, caches, or providers in?
- **Business health:** are critical business flows meeting success rates/SLOs?

If the DB is mandatory for every write request, readiness can stop accepting writes when the DB is unavailable while liveness still reports the process alive. The system can return controlled errors or serve read paths if the business permits.

### 4.1. One Dependency Should Not Automatically Make the Whole Service Unhealthy

For example, the Booking API reads reservations from the primary database, sends emails via a notification queue, and calls a payment provider. When the email provider is down:

- The Booking API can continue creating bookings if the core transaction commits and notifications persist in an outbox/queue.
- Notification workers can lower readiness or pause pulling messages once backlogs/attempts hit thresholds.
- The payment flow can return pending/unknown if the provider is unresponsive.
- Booking API liveness must never fail simply because the email provider is down.

Health semantics must match the mandatory dependencies of each operation, not apply one uniform dependency list across the entire application.

## 5. Multi-Layer Self-Healing

Self-healing is an automated response to a detected failure. It can happen at the process, container, node, instance, service routing, or data layer.

| Layer | Signal | Recovery action |
|---|---|---|
| Process | Main loop hung, process exit | Supervisor or runtime restarts process |
| Container | Liveness fails, container exits | Container runtime restarts container per policy |
| Pod/workload | Pod unhealthy or evicted | Controller creates replacement pod |
| Node/VM | Node loses heartbeat, host failure | Scheduler reschedules workloads onto another node; autoscaler adds nodes if needed |
| Service routing | Endpoint not ready | Load balancer/service mesh removes from traffic |
| Queue consumer | Worker stops or lease expires | Message redelivered; another consumer picks it up |
| Database | Node failover/replica promotion | Managed DB or cluster recovers per configuration |
| Region | Regional outage | Fail over to another region if architecture and data allow |

Restarting is only one form of self-healing. Not every failure is fixed by a restart; select actions based on failure modes and data state.

### 5.1. Desired State and Controllers

In declarative desired-state systems, controllers continuously reconcile actual state against desired state. If a deployment asks for 5 replicas and only 4 exist, the controller spins up a replacement pod. If a pod restarts, the controller maintains the desired count.

This heals dead instances, yet it does not prove the app inside is functioning properly from a business standpoint. A pod can be Running and Ready while returning wrong data; separate quality metrics, synthetic checks, and business SLIs are still required.

## 6. Restart Policies and Crash Loops

Restarts can clear deadlocks or transient faults, yet continuous restarts cause instability.

### 6.1. When Restarts Help

- Process is deadlocked and cannot progress.
- Accumulated memory leaks hit thresholds; restarts restore service temporarily while root cause is investigated.
- Internal state is corrupted with no in-process recovery path.
- Workers get stuck in a non-progressing state after timeouts.

### 6.2. When Restarts Make Things Worse

- The database is down and all replicas restart together.
- Startup depends on an unavailable provider, causing a crash loop.
- Credentials are invalid or config is broken—restarts do not change the cause.
- Memory limits are too low, causing every new instance to OOM immediately.
- Dependency connection storms overload the DB further.

### 6.3. Backoff and Restart Budgets

Restart policies should apply backoff to avoid rapid restart loops:

~~~text
Attempt 1 -> wait 1s
Attempt 2 -> wait 2s
Attempt 3 -> wait 4s
Attempt 4 -> wait 8s
...
Cap at a configured maximum delay
~~~

Values are illustrative only. Platforms may apply their own backoff; applications should avoid adding another self-restart loop that amplifies storms. Cap restarts within a time window, then hold the workload in a failed/unhealthy state and alert operators.

Classify crash loops by exit code, `OOMKilled`, startup timeouts, probe failures, dependency timeouts, and config errors. Never merely raise probe thresholds to mask slow startup bugs.

## 7. Readiness and Load Balancers

Load balancers periodically probe targets and route traffic only to healthy endpoints. However, load balancer probes, orchestrator readiness, and application health checks can differ in semantics.

### 7.1. New Instance Onboarding Flow

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant A as New instance
    participant L as Load balancer
    P->>A: Create instance
    A->>A: Start process and initialize
    P->>A: Startup check
    A-->>P: Startup ready
    P->>A: Readiness check
    A-->>P: Ready
    P->>L: Register / mark target healthy
    L->>A: Health probe
    L->>A: Route production traffic
~~~

Never let a load balancer send traffic merely because the VM finished booting. The application must be initialized and able to serve requests.

### 7.2. Target Deregistration and Connection Draining

During scale-in or deployments, load balancers must stop sending new requests to terminating targets. **Deregistration delay / connection draining** gives in-flight requests time to finish before closing targets.

If the drain timeout is shorter than the longest valid request, requests get severed. If too long, deployments or scale-in slow down. Size it based on request durations, streaming, WebSockets, long polling, and termination grace periods.

Load balancers may keep persistent connections or WebSockets open after marking a target unhealthy; test actual behavior instead of assuming every connection closes immediately.

## 8. Graceful Shutdown: Stopping New Work Before Stopping the Process

Graceful shutdown is an orderly termination sequence. The goal is to stop new work from entering, let in-flight work finish or hand off safely, and then close dependencies.

A typical sequence:

1. Receive termination signal or shutdown notification.
2. Transition readiness to `NOT_READY`/`DRAINING`.
3. Deregister target from load balancers/service routing.
4. Stop accepting new requests/messages/jobs.
5. Complete running requests/tasks within the grace period.
6. Commit or roll back internal transactions deterministically.
7. Ack/delete messages only after side effects are safe; if unfinished, let messages redeliver.
8. Flush logs/telemetry and close pools/connections.
9. Exit process before the platform deadline.

~~~mermaid
flowchart TD
    Signal["SIGTERM / shutdown event"] --> Mark["Set readiness = NOT_READY"]
    Mark --> Deregister["Deregister / drain traffic"]
    Deregister --> Stop["Stop accepting new work"]
    Stop --> Wait["Wait for in-flight work"]
    Wait --> Finish{"Work completed before deadline?"}
    Finish -->|Yes| Close["Commit, flush telemetry, close connections"]
    Finish -->|No| Safe["Cancel safely / leave message retryable"]
    Safe --> Close
    Close --> Exit["Exit process"]
~~~

Never start shutdown by closing database pools before in-flight requests finish. Those requests may still need DB reads/writes to conclude consistently.

## 9. SIGTERM, SIGKILL, and Termination Grace Periods

In many container/Linux environments, the runtime sends `SIGTERM` to ask a process to stop. If the process fails to exit within the grace period, the runtime may send `SIGKILL` or forcefully terminate it.

- **SIGTERM:** opportunity for the app to catch the signal and shut down cleanly.
- **SIGINT:** typically represents terminal interrupts; apps may handle it similarly, though semantics depend on runtime.
- **SIGKILL:** cannot be caught or handled; terminates the process immediately.
- **Termination grace period:** time the platform grants a process to finish after termination starts.

The grace period must exceed the longest expected in-flight request/task under policy while remaining acceptable for rollout/scale-in durations.

### 9.1. Calculating a Shutdown Budget

Example:

| Step | Illustrative budget |
|---|---:|
| Mark readiness and deregister | 5 seconds |
| Wait for in-flight requests | 25 seconds |
| Flush/commit/close | 5 seconds |
| Buffer | 5 seconds |
| **Total** | **40 seconds** |

This is an example. If an API supports 2-minute requests or hours-long WebSockets, you cannot set a 40-second grace period and expect all connections to finish. Bound request durations, support reconnects, session resumption, or contractual draining.

### 9.2. Registering Shutdown Hooks

Illustrative Java pseudocode:

~~~java
public final class ServiceLifecycle {
    private final ReadinessState readiness;
    private final RequestTracker requests;
    private final ExecutorService executor;
    private final DataSource dataSource;

    public void register() {
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            readiness.markDraining();
            stopAcceptingNewRequests();
            requests.awaitInFlight(Duration.ofSeconds(25));
            executor.shutdown();
            try {
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                executor.shutdownNow();
            }
            closeDataSource(dataSource);
        }));
    }
}
~~~

This is illustrative pseudocode; closing server listeners, connection pools, transaction managers, and executors depends on the framework. Hooks must be idempotent, bounded by a total deadline, and must not swallow interrupts. Shutdown hooks are not guaranteed to run on `SIGKILL`, hard crashes, or power loss.

## 10. Graceful Shutdown for Queue Workers

Message-processing workers require safer shutdown than simple HTTP servers because messages can be redelivered after timeouts or visibility leases.

### Fundamental Rules

- Upon receiving a drain signal, stop polling/receiving new messages.
- Allow in-flight messages to finish if enough time remains.
- Ack/delete only after side effects commit or operation states persist durably.
- If unable to finish, do not ack; let the broker redeliver after visibility timeout/lease expiry.
- Consumers must be idempotent to handle duplicates safely.
- If lease extension is supported, renew leases only while the worker is genuinely making progress.

### Example Scenario

A worker receives a message to issue an invoice. The process receives `SIGTERM` after the provider creates the invoice but before the worker acks the message. The broker redelivers the message to another worker. Without an idempotency key tied to the invoice operation, the system may create two invoices or send duplicate notifications.

The solution is a stable operation ID, querying provider/reference status, and recording completion state before acking. If the outcome is ambiguous, the new worker reconciles before creating any new side effect.

## 11. Graceful Shutdown for Long Requests and Streaming

Not every request finishes in a few seconds. Large uploads/downloads, WebSockets, server-sent events, long polling, and stream consumers can stay open long-term.

Options:

- Enforce maximum request durations and return reconnect hints when needed.
- Stop accepting new connections while giving existing connections a drain window.
- Send close frames/termination events to WebSocket clients with reconnect and cursor resumption support.
- For uploads, persist checkpoints/received chunks so clients can resume.
- For streaming responses, close cleanly per protocol without cutting mid-record if possible.
- For long jobs, persist durable operation state so another worker can resume.

If a connection drops, clients must know whether retrying is safe. Write requests need idempotency keys or operation status lookup to avoid duplicate effects.

## 12. Dependency Failures and Cascading Restarts

One down dependency should not automatically force every dependent service to restart. Distinguish recovery capabilities from load-reduction controls:

- **Timeouts:** cap wait durations; prevent threads/connections from hanging forever.
- **Circuit breakers:** pause calls to failing dependencies; allow recovery probes per policy.
- **Bulkheads:** isolate resource budgets per dependency or request class.
- **Retries with backoff/jitter:** retry only transient errors and safe operations.
- **Fallbacks/degraded modes:** return cached data or reduced features only when business allows.
- **Readiness:** remove an instance from traffic when that instance cannot safely take requests; do not equate global outages with dead processes.
- **Admission control:** shed new requests to prevent overloading dependencies.

### Example

If the database is failing over:

1. API applies short timeouts and circuit breakers for DB calls.
2. Do not spawn unbounded waiting threads.
3. Liveness continues reflecting whether the process makes progress.
4. Readiness reflects ability to serve relevant request types per design.
5. Write requests can be rejected cleanly or queued if business semantics allow.
6. When the DB recovers, connection pools reconnect with backoff; do not let all replicas reconnect simultaneously.

## 13. Self-Healing and Failure Domains

A system with many replicas that all sit on a single node, zone, or shared dependency still has a single point of failure.

### Layered Recovery

| Failure domain | Detection | Action |
|---|---|---|
| Process | Liveness, process exit, watchdog | Restart process |
| Container/pod | Container exit, probe failure | Restart/recreate pod |
| Node/VM | Heartbeat, node condition | Reschedule onto another node |
| Availability zone | Health signals and dependency monitoring | Shift traffic/workloads to healthy zones |
| Region | Regional health and data replication status | Fail over per DR plan |
| External provider | Error rates/timeouts, status feeds | Circuit breaker, fallback, or degraded mode |

Automated failover must account for data freshness, write authority, split-brain, replication lag, and failback. Shifting traffic to another region before the database is ready can cause errors or data loss.

### 13.1. Never Restart the Entire Fleet Simultaneously

If every replica fails liveness due to the same dependency timeout, synchronized restarts trigger reconnect storms and mass cold starts. Use jitter, restart budgets, deployment `maxUnavailable`, circuit breakers, and backoff to prevent synchronization.

## 14. Readiness in Deployments and Rolling Updates

During rolling deployments, new instances should receive traffic only after startup finishes and readiness passes. Old instances must drain before terminating.

Sequence:

~~~mermaid
sequenceDiagram
    participant C as Controller
    participant N as New replica
    participant O as Old replica
    participant LB as Load balancer
    C->>N: Start new replica
    N->>N: Startup and initialize
    N-->>C: Startup and readiness pass
    C->>LB: Add new replica
    LB-->>N: Route new traffic
    C->>O: Begin termination
    O->>LB: Mark not ready / deregister
    LB-->>O: Stop new traffic; drain existing
    O->>O: Complete in-flight work
    O-->>C: Exit
~~~

Parameters like max unavailable, max surge, readiness period, and termination grace period must align. If max unavailable is too large, capacity drops below minimum; if max surge is too large, database connections and compute quotas can be exceeded.

## 15. Health Checks and Autoscaling

Health checks affect autoscaling and placement:

- New instances count toward usable capacity only after readiness passes.
- Unhealthy instances get replaced, potentially spiking replica startup churn.
- Pending pods are not liveness failures; they usually indicate scheduler/node capacity issues.
- Readiness failures caused by a global dependency can remove every endpoint from service.
- Scale-in must both drain targets and wait for workloads to finish.

Dashboards should distinguish desired replicas, running replicas, ready replicas, unhealthy replicas, and pending replicas. Raw "replica count" does not directly reflect serving capacity.

## 16. Securing Health and Lifecycle Endpoints

Health endpoints can leak infrastructure details if exposed too broadly:

- Never return stack traces, sensitive package versions, DB hosts, internal IPs, or credentials.
- Separate minimal probe endpoints from detailed diagnostics endpoints.
- Restrict diagnostics via authentication/network policies.
- Use dedicated identities for agents/monitors when needed.
- Never allow external callers to trigger restarts via health endpoints.
- Log health-check traffic at reasonable volume to avoid noise and cost.
- Ensure probe endpoints have zero side effects and mutate no data.

Shutdown signals must also be protected. Only trusted control planes or runtimes should trigger drain/termination; admin APIs require authorization and auditing.

## 17. Observability and Operations

### 17.1. Key Metrics

| Metric | Meaning |
|---|---|
| Startup duration p50/p95/p99 | How long workloads take to initialize |
| Readiness transition count | Whether instances flap in and out of ready |
| Liveness failure/restart count | Abnormal process/container restarts |
| `CrashLoopBackOff` / `OOMKilled` | Repeated crashes or memory limit breaches |
| Unready endpoint count | Endpoints pulled out of traffic |
| In-flight requests at termination | Requests active when shutdown begins |
| Drain duration | Time to complete graceful shutdown |
| Forced termination count | Processes killed after grace period expiry |
| Queue redelivery/visibility timeouts | Messages redelivered because workers failed to ack |
| Dependency errors/timeouts | Upstream failures potentially causing unready states |
| Recovery time | Time from incident to service restoration |

### 17.2. Recommended Alerts

- Abnormal rise in restart counts or prolonged crash loops.
- Simultaneous readiness failures across multiple replicas.
- Startup duration breaching threshold or deployment failing to reach desired ready count.
- Healthy endpoint count dropping below redundancy floor.
- Spikes in forced terminations or aborted requests.
- Rising queue redeliveries/DLQs after scale-in or deployments.
- Dependency timeouts climbing alongside readiness/liveness failures.
- Recovery time breaching SLOs.

Do not alert on single isolated probe timeouts that only create noise. Tie alerts to rates, duration, impacted replica counts, and business SLIs.

### 17.3. Investigation Runbook

1. Determine scope: single process, node, zone, or multiple services.
2. Check startup/readiness/liveness events and state-transition timestamps.
3. Inspect restart reasons, exit codes, OOM events, probe timeouts, and pre-shutdown logs.
4. Inspect CPU, memory, threads, connection pools, disk, and network.
5. Check dependency timeouts/rate limits/failovers.
6. Identify which requests/messages were in-flight or redelivered.
7. Check recent deployments/config/secret changes near incident onset.
8. Shed load or isolate failing dependencies if needed; avoid unplanned fleet-wide restarts.
9. Verify readiness and business SLIs return to normal.
10. Document root cause, recovery actions, and recurrence prevention.

## 18. Case Study: Booking API and Notification Worker

**Context:** a room booking platform runs the Booking API across multiple replicas and a Notification worker consuming messages from a queue. The Booking API needs p95 under 300 ms. The worker sends emails through a provider that occasionally slows down or returns 429s. During deployments, the system must not drop requests or send duplicate emails.

### 18.1. Health Design

| Component | Startup | Readiness | Liveness |
|---|---|---|---|
| Booking API | Config, routes, schema/client init complete | Can serve core operations; mandatory dependencies ready per policy | Event loop and request handlers progressing |
| Notification worker | Config, queue client, and provider policy loaded | Can pull new messages and has concurrency budget | Consumer loop/worker process progressing |
| Payment integration | Client/credentials initialized | Separate dependency state; outages do not restart the API | Never use provider availability for API liveness |

### 18.2. API Shutdown

1. Platform sends `SIGTERM`.
2. API flips readiness to `DRAINING`.
3. Load balancer stops sending new requests and drains persistent connections per policy.
4. API waits for in-flight requests within grace period.
5. Requests finish transactions/outbox; requests exceeding deadlines cancel cleanly per contract.
6. API flushes telemetry, closes DB pools, and exits.

### 18.3. Worker Shutdown

1. Worker flips readiness to stop accepting new messages.
2. Stops polling/receiving.
3. Waits for in-flight messages within grace period.
4. If side effects succeed, saves operation state and acks the message.
5. If incomplete or outcome ambiguous, does not ack; on redelivery, consumer checks idempotency key/provider reference.
6. Closes queue client and provider connections, then exits.

### 18.4. When Email Provider Fails

- Worker caps retries and honors `Retry-After`/backoff.
- Queue retains backlog; oldest message age is monitored.
- Worker does not restart repeatedly merely because the provider returns 429s.
- When backlog hits thresholds, lower concurrency or pause pulling new messages.
- Booking API still confirms bookings if core business commits and events save safely; notifications stay pending.
- When the provider recovers, workers resume processing and deduplicate.

### 18.5. Acceptance Criteria

- Unready instances receive no traffic.
- Liveness failures restart processes only for restart-recoverable conditions.
- Provider outages never trigger a restart storm across the Booking API.
- Rolling deployments never drop ready capacity below required thresholds.
- API drains finish in-flight requests within the grace period or return deterministic outcomes.
- Workers never ack messages before side effects are durably stored.
- Message redeliveries never send unintended duplicate emails.
- Dashboards show restarts, readiness, draining, queue age, and dependency health.

## 19. Testing Health, Self-Healing, and Shutdown

| Test | Failure simulated in controlled environment | Expected result |
|---|---|---|
| Slow startup | Extend config/model load time | Startup probe grants sufficient time without routing traffic |
| Readiness failure | Prevent worker from accepting new work | Endpoint removed from routing without pointless restarts |
| Liveness hang | Create deadlock/non-progressing test endpoint | Runtime restarts per policy; alert fires |
| Dependency outage | Block DB/provider in test | No cascading restarts; timeouts/circuit breakers engage |
| OOM | Constrain memory in test | Restart classified properly; alert and root cause clear |
| Node drain | Planned workload eviction | New pod becomes ready; old pod drains safely |
| Rolling deployment | Swap versions under load | Ready capacity and error budget preserved |
| SIGTERM mid-request | Terminate instance during test | Request finishes or cancels cleanly |
| SIGTERM mid-message | Stop worker mid-message | No premature ack; idempotent redelivery |
| Grace period expiry | Extend task past deadline | Forced termination measured without corrupting data |
| Fleet restart | Simulate simultaneous loss of multiple instances | Jitter/backoff and capacity recovery avoid storms |

Tests require synthetic data and dependency sandboxes; never inject failures intentionally in production without scope/authorization and rollback plans.

## 20. Common Mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| One health check for all decisions | Wrongful restarts or traffic hitting unready instances | Separate startup, readiness, and liveness |
| Liveness calls every dependency | DB/provider outage restarts whole fleet | Focus liveness on internal progress |
| Readiness returns 200 just because process exists | Booting instances still receive traffic | Check actual readiness to accept workload |
| Probes fan out to many services every few seconds | Adds load and amplifies outages | Keep probes light; cache health and separate diagnostics |
| Restarting immediately on brief timeouts | Crash loops and cold-start storms | Thresholds, timeouts, backoff, and restart budgets |
| Relying solely on container Running state | Process may be unready or hung | Monitor readiness and business SLIs |
| Shutdown closes DB pools before draining | In-flight requests fail | Stop new intake, finish in-flight work, then close dependencies |
| Worker acks before commit | Messages lost despite incomplete side effects | Ack after durable completion |
| Assuming shutdown hooks always run | Data loss on SIGKILL/hard crashes | Design idempotency, leases, and recovery |
| Grace period shorter than requests/tasks | Frequent forced terminations | Measure durations and build shutdown budgets |
| All replicas restart simultaneously | Connection storms and prolonged outages | Jitter, max unavailable, circuit breakers |
| Public health endpoints expose dependencies | Leaks internal architecture info | Separate probes/diagnostics, add auth and redaction |

## 21. Architecture Review Checklist

### Health Checks

- [ ] Startup, readiness, and liveness have distinct purposes.
- [ ] Startup timeouts are grounded in actual initialization measurements.
- [ ] Readiness reflects ability to accept new work and `DRAINING` state.
- [ ] Liveness checks internal progress without blindly depending on all dependencies.
- [ ] Probes are fast, side-effect free, and generate minimal load.
- [ ] Detailed diagnostic endpoints are secured and leak no secrets.

### Self-Healing

- [ ] Restart policies, backoff, and restart budgets are defined.
- [ ] Controller/replica replacement operates at the right failure domains.
- [ ] Desired, running, ready, pending, and unhealthy capacity are tracked separately.
- [ ] Dependency outages do not cause restart storms.
- [ ] Concurrency/connection limits guard workload replacements.
- [ ] Zone/region failovers define clear data freshness, write authority, and recovery plans.

### Graceful Shutdown

- [ ] Termination signals flip readiness to `NOT_READY`/`DRAINING`.
- [ ] Routing/load balancers stop sending new requests and drain connections.
- [ ] In-flight requests/tasks have clear deadlines and cancellation behavior.
- [ ] Workers stop polling and ack messages only after durable results.
- [ ] Side effects are idempotent and ambiguous outcomes get reconciled.
- [ ] Grace periods cover drain/close without exceeding deployment budgets.
- [ ] Fallbacks exist when `SIGKILL` or hard crashes bypass shutdown hooks.

### Operations

- [ ] Dashboards track startup, readiness, liveness, restarts, drain times, and recovery times.
- [ ] Alerts target impact/SLOs rather than isolated single probe failures.
- [ ] Runbooks exist for crash loops, dependency outages, node drains, and message redelivery.
- [ ] Fault-injection tests have run under representative load.
- [ ] Owners are assigned for health policies, restart policies, and termination configurations.

## 22. Hands-On Exercise

**Context:** A booking application runs 8 replicas on Kubernetes. Startup takes 40 seconds due to config loading and client initialization. The API calls a database to confirm bookings; a notification worker processes messages and calls an email provider. Database failover takes 20 seconds. Rolling deployments require at least 6 ready replicas at all times. Some requests take up to 25 seconds; worker messages can take 45 seconds. The platform sends a termination signal with a 30-second grace period.

Design the lifecycle:

1. Propose startup/readiness/liveness probes and explain what must be excluded from liveness.
2. Define readiness behavior during database failover while the process stays alive.
3. Calculate a shutdown budget fitting 25-second requests and 45-second worker tasks; highlight gaps in the current grace period.
4. Design rolling updates so ready replicas never drop below 6.
5. Describe how the Booking API transitions to `DRAINING`, load balancers drain, and DB pools close.
6. Describe how the worker stops polling, completes/avoids acking messages, and handles duplicates.
7. Propose restart backoff/budgets to avoid fleet-wide restarts during database outages.
8. Define metrics/alerts for startup duration, ready replicas, restarts, drain times, and queue age.
9. Write fault-injection tests for DB failover, `SIGTERM` mid-request, and worker crash after side effects.
10. Define runbooks and SLO-based acceptance criteria.

**Self-Assessment Hint:** Readiness is not synonymous with process liveness; liveness must never turn a database outage into a restart storm. A 30-second grace period is shorter than a 45-second worker task, requiring earlier draining, checkpoint/lease support, or deadline adjustments. Messages may be acked only after side effects are durable and deduplication is in place.

## 23. Key Takeaways

Health checks must answer the right questions: has startup finished, can this instance accept new work, and is the process making progress? Startup, readiness, and liveness trigger different actions; misconfigured probes can turn minor outages into restart storms.

Self-healing must align with failure domains and desired state, combining restarts, rescheduling, routing, backoff, and dependency bounds. Graceful shutdown begins by stopping new work intake, draining in-flight requests/messages, saving results safely, and closing connections within the termination deadline. Reliable designs also account for hard failures where shutdown hooks never run, enforce idempotency on redeliverable work, and verify everything through fault injection, metrics, alerts, and runbooks.
