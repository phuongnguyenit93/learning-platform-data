# Health Checks, Unhealthy Target Ejection, and Failover Traffic Steering

> **Chapter:** System Entry Points  
> **Module:** CLOUD_ARCHITECTURE  
> **Scope:** Cloud application architecture design from business requirements to networking, compute, data, and deployment models; balancing reliability, security, scalability, cost, and operations under Well-Architected principles.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish health checks at the process, instance, application, dependency, and end-to-end service levels, choosing the right check for each goal.
2. Explain the roles of startup, liveness, readiness, and load balancer/orchestrator health checks.
3. Design probe thresholds that detect unhealthy targets, remove them from traffic distribution, and avoid state flapping.
4. Describe connection draining, graceful shutdown, and handling of in-flight requests when a target is removed.
5. Distinguish intra-zone/intra-region failover from cross-region traffic steering, selecting appropriate health probes, routing policies, TTLs, and recovery mechanisms.
6. Validate failure behaviors to prevent cascading outages caused by overly deep probes, retries, or uncontrolled traffic shifts.

## 1. Why Do Systems Need Health Checks and Traffic Steering?

An entry point such as a load balancer, API gateway, reverse proxy, or DNS router typically distributes requests across multiple targets: VMs, containers, pods, application instances, or regions. A target list is useful only when the system knows which targets can actually receive and process requests.

If a stopped instance still receives traffic, users see errors. If a process is alive yet the app has not loaded configuration or cannot reach its database, requests still fail. If a probe marks the entire cluster unhealthy just because a non-essential dependency is slow, the system can eject all remaining healthy capacity.

A **health check** is a periodic or event-driven check evaluating a specific health state. Results can be used to:

- Decide whether a process/container should be restarted.
- Permit or stop an instance from receiving new requests.
- Remove a target from a load balancer's pool.
- Shift traffic to a standby availability zone or region.
- Alert operations teams and feed signals to autoscaling/automation.

Crucially, you must know **who runs the check, what is checked, and what action the result triggers**. An endpoint returning HTTP 200 does not prove every business flow works; a single timeout does not prove an entire region has failed.

### 1.1. Concepts to Distinguish

| Concept | Question Answered | Typical Associated Action |
|---|---|---|
| **Process health** | Is the process running and responsive? | Process or runtime monitoring |
| **Startup check** | Has the application finished initializing? | Wait before evaluating liveness/readiness |
| **Liveness** | Is the process making progress or deadlocked/broken? | Potentially restart the instance/container |
| **Readiness** | Can the application accept this class of traffic right now? | Add/remove target from serving endpoints |
| **Load balancer target health** | Does the target satisfy the LB's configured health criteria? | Include or eject target from pool |
| **Dependency health** | Are databases, caches, queues, or external providers usable? | Degrade features, apply bounded retries, alert |
| **Service health / SLO** | Can users complete key journeys at committed quality? | Higher-level service assessment and steering |

These states are related yet **not interchangeable**. A live process is not necessarily ready; a healthy database does not guarantee valid API logic; DNS health does not reflect every user's individual requests.

## 2. Types of Health Checks and Where They Belong

### 2.1. Startup, Liveness, and Readiness

In container/orchestrator environments, three probe types carry distinct meanings:

- **Startup probe:** verifies the application has initialized enough to begin normal monitoring. Useful when apps start slowly, run safe startup migrations, or warm initial caches. Until startup passes, platforms can hold off other probes.
- **Liveness probe:** verifies the process is operating as expected rather than wedged. After consecutive failures reach a threshold, the orchestrator may restart the container.
- **Readiness probe:** verifies an instance can accept new requests. When failing, the orchestrator or endpoint controller removes the instance from serving endpoints while letting the process keep running and recover.

Never put a slow database query inside a liveness probe indiscriminately. If the database slows down, every container can fail liveness and restart simultaneously—wiping warm connection pools/caches and hammering the database further. Liveness should catch unrecoverable process wedging; readiness can reflect traffic readiness across a carefully chosen dependency scope.

Illustrative endpoint specification:

~~~text
GET /health/startup
  200: bootstrap complete
  503: application still initializing

GET /health/live
  200: event loop/main thread making progress
  500/503: process stuck in state requiring restart

GET /health/ready
  200: instance can accept new requests per policy
  503: instance temporarily not ready
~~~

These paths and status codes are examples. Actual implementations depend on framework and platform. Restrict access to health endpoints and never return secrets, connection strings, stack traces, or sensitive topology details.

### 2.2. Load Balancer Health Checks

Load balancers probe targets using configured protocols: TCP connect, HTTP/HTTPS requests, gRPC health protocols, or platform-native checks. A target is marked healthy only when probe results satisfy configured thresholds.

| Probe Type | What It Proves | What It Cannot Prove |
|---|---|---|
| **TCP connect** | Port accepts TCP handshakes | App handles requests properly or DB is reachable |
| **HTTP path** | Server returns expected path/status response | Full business workflow succeeds |
| **HTTPS** | TLS handshake and app response match config | Other clients/routes have valid certs and policies |
| **gRPC health service** | Service reports status via health protocol | Specific business RPCs or optional dependencies succeed |
| **Synthetic transaction** | A simulated client journey succeeds | All tenants, regions, and request paths are error-free |

Probes should test just enough to decide whether a target can take new traffic. Shallow probes keep broken targets in rotation; overly deep probes calling many dependencies add extra load, risk data exposure, or trigger false negatives.

### 2.3. Dependency Health and Graceful Degradation

Applications rely on dependencies of varying criticality. For example:

| Dependency | Impact on Failure | Reasonable Behavioral Choice |
|---|---|---|
| Primary transactional DB | Cannot confirm bookings | Fail booking-write API readiness or return controlled errors; never fake success |
| Cache | Slows queries, though authoritative data remains in DB | Fall back to DB if capacity allows; alert and shed excess load |
| Notification queue | Bookings can commit while notifications lag | Allow bookings if durable outbox writes succeed; monitor backlog/lag |
| Search index | Search unavailable or falls back to simpler queries | Degrade or temporarily disable search endpoint |
| Email provider | Immediate emails cannot send | Queue with bounded retries; never break committed bookings |
| Identity provider | New sessions cannot authenticate | Behavior follows token/session policy; never bypass authentication |

Readiness should not report unhealthy just because **any secondary feature** is impaired. Scope readiness to the endpoints or workloads a target serves. If one deployment serves both booking writes and reporting, define an explicit readiness policy—or split workloads/routes by capability.

### 2.4. External Synthetic Monitoring

Internal health probes inside the same network miss failures affecting real users: public DNS, edge certificates, Internet routing, WAF, CDN, identity providers, or misconfigured entry points. **Synthetic monitoring** executes test transactions from user-adjacent locations outside the cloud boundary:

1. Resolve DNS and complete the TLS handshake.
2. Call the public endpoint using a narrowly scoped test identity.
3. Perform a non-destructive action or an isolated test-data mutation.
4. Verify business outcome, latency, and request ID.
5. Emit metrics/alerts when failures cross thresholds.

Never run synthetic tests that create real bookings or send real SMS/emails every few seconds without strict data, cost, and side-effect controls. Use dedicated test accounts, isolated data, rate caps, and automated cleanup.

## 3. Designing Probes: Frequency, Timeouts, and Thresholds

### 3.1. Core Parameters

A health check typically configures:

| Parameter | Meaning | Impact When Misconfigured |
|---|---|---|
| **Interval** | Time between consecutive probes | Too long delays detection; too short adds overhead |
| **Timeout** | Max wait per probe | Too short triggers false negatives; too long delays detection and ties up resources |
| **Healthy threshold** | Consecutive successes to mark healthy | Too high delays bringing new/recovered targets online |
| **Unhealthy threshold** | Consecutive failures to eject target | Too low causes jitter-driven ejections; too high leaves broken targets serving |
| **Initial delay / grace** | Wait before probing or treating boot failures as fatal | Too short causes startup restart loops |
| **Path / port / protocol** | Endpoint and protocol probed | Wrong path, SNI, or port marks healthy apps down |
| **Expected status / body** | Criteria for a passing response | Too permissive accepts errors; too strict rejects valid targets |

Illustrative configuration:

~~~text
Protocol: HTTP
Path: /health/ready
Interval: 10 seconds
Timeout: 2 seconds
Unhealthy threshold: 3 consecutive failures
Healthy threshold: 2 consecutive successes
Startup grace period: 30 seconds
~~~

Never copy these numbers verbatim into production. Derive values from measured startup time, tail latency, network stability, detection goals, and load capacity. A 2-second timeout suits a lightweight internal endpoint, not a path executing heavy queries.

### 3.2. Estimating Detection Time

If a health check runs every \(I\) seconds with timeout \(T\), requires \(N\) consecutive failures, and a fault occurs right after a passing probe, time from fault onset to target ejection falls roughly within:

\[
(N-1)I+T \quad \text{to} \quad NI+T
\]

This is a simplified estimate; platforms may stagger probe schedules, run multiple parallel checkers, add jitter, and take extra time to propagate state.

For example, with a 10-second interval, 2-second timeout, and unhealthy threshold of 3:

- If failure occurs right before the next probe starts, detection takes roughly \(2\times10+2=22\) seconds.
- If failure occurs right after a probe starts, three failed probes may finish around \(3\times10+2=32\) seconds depending on scheduling.

Measure real detection times on your target platform. **Detecting a bad target does not mean traffic has finished shifting**—pool updates, deregistration, DNS caches, and routing convergence still take time.

### 3.3. False Positives and False Negatives

- **False positive:** a healthy target is marked unhealthy. This shrinks capacity, piles load onto remaining targets, and can trigger cascading cluster failure.
- **False negative:** a broken target stays marked healthy. User requests continue failing and recovery drags out.

To reduce false positives:

- Choose noise-tolerant thresholds, realistic timeouts matched to latency, and avoid unneeded network/DB calls inside probes.
- Aggregate health across multiple targets and telemetry sources; never let a single probe trigger global failover.
- Use hysteresis: recovery thresholds can differ from ejection thresholds.
- Keep headroom so losing one target does not push survivors past saturation.

To reduce false negatives:

- Never rely solely on TCP checks if the app can accept sockets while deadlocked.
- Probe the actual readiness endpoint tied to the serving listener/route.
- Pair internal probes with external synthetic checks and business metrics.
- Test failure modes like exhausted pools, wedged threads/event loops, and failed critical dependencies.

### 3.4. Avoiding Health Check Storms and Flapping

**Flapping** occurs when a target oscillates rapidly between healthy and unhealthy. If probes hit databases or heavy CPU paths, stressed systems suffer even further from probe traffic.

Mitigations:

1. Keep probe endpoints lightweight, fast, and resource-bounded.
2. Tune intervals, timeouts, and thresholds with hysteresis.
3. Avoid synchronized probe bursts across checkers; add jitter or staggered scheduling where self-managed.
4. Never auto-restart all instances simultaneously due to a single external dependency outage.
5. Alert on unhealthy target counts, state-flip frequency, remaining capacity, and user error rates.
6. Define explicit policy when **all targets go unhealthy**: fail closed, fail open, retain targets, or fail over—each is a deliberate choice requiring verification.

Defaulting blindly to fail-open or fail-closed is risky. Retaining dead targets keeps failing requests; draining every target leaves zero endpoints. Decide based on business safety, partial-degradation viability, and provider behavior.
## 4. Ejecting Failed Targets and Returning Them to the Pool

### 4.1. Health States and Target Lifecycle

Load balancers track per-target states such as initial, healthy, unhealthy, draining, or unused. State names and transition rules vary by provider; never assume identical names mean identical behavior everywhere.

~~~mermaid
stateDiagram-v2
    [*] --> Initial
    Initial --> Healthy: probes pass threshold
    Initial --> Unhealthy: probes fail per policy
    Healthy --> Unhealthy: failures hit threshold
    Unhealthy --> Healthy: passes hit threshold
    Healthy --> Draining: deregistration / scale-in / deployment
    Draining --> Removed: drain timeout expires
    Removed --> [*]
~~~

When a target turns unhealthy, the load balancer stops routing new requests to it once state propagates. That **does not mean active connections drop instantly**, nor does it guarantee failed in-flight requests automatically replay to another target. Retry behavior depends on protocol, failure timing, and request semantics.

### 4.2. Deregistration and Connection Draining

During scale-in or deployments, targets may still be serving HTTP requests, streaming responses, WebSockets, or long transactions. **Deregistration delay / connection draining** stops new connections/requests while giving active work a bounded window to finish.

A typical graceful shutdown sequence:

1. Mark the instance unavailable for new work (readiness false or deregister).
2. Wait for the load balancer/orchestrator to stop sending new requests and update endpoints.
3. Finish active requests within the drain window.
4. Stop polling new queue jobs; finish or release leases/visibility timeouts cleanly.
5. Flush logs/telemetry, close connections, and release resources.
6. Exit within the termination grace period; past that, the orchestrator may force-kill the process.

Size drain timeouts from real request durations, protocols, and platform limits. Too short cuts off active requests; too long slows scale-in and wastes compute.

| Workload Type | Recommended Draining Approach |
|---|---|
| Short HTTP APIs | Stop accepting new requests; finish active ones within deadline |
| Streaming / SSE / WebSocket | Signal reconnect, support client reconnection, define session/state continuity |
| Queue workers | Stop polling new messages; finish or release in-flight items safely; never ack prematurely |
| Long batch jobs | Avoid abrupt kills; checkpoint or wait within bounded shutdown windows |
| Event consumers | Manage offsets/acks and in-flight messages to stay within loss/duplicate policies |

Never assume a load balancer marking a target unhealthy stops the process safely. Implement application shutdown hooks, orchestration grace periods, and deployment/scale-in tests.

### 4.3. Returning Recovered Targets to the Pool

When a failed target recovers, restoring full load too abruptly can trigger flapping. Confirm startup completed, configs/secrets are valid, listeners accept traffic, readiness passes, and connection pools/caches are initialized. If cold caches or startup overhead are heavy, warm up before ramping traffic. Some platforms support slow start or gradual traffic ramping—verify actual load balancer capabilities.

### 4.4. When All Targets Are Unhealthy

Plan this scenario ahead of time:

| Policy | Pros | Risks |
|---|---|---|
| Send zero traffic to unhealthy targets | Avoids routing requests to known-broken backends | Empty pool even if some targets could serve partial requests |
| Fail open / retain targets per platform capability | Can preserve partial service | Traffic may keep hitting genuinely broken instances |
| Shift to another pool / zone / region | Preserves entry point if standby has capacity | Bad probes can trigger false failovers; standby data may lag |
| Return controlled errors and protect data | Prevents corrupted business state | Users lose functionality during the outage |

Never disable health checks unconditionally during a cluster outage. For booking platforms, returning 503 is safer than confirming bad reservations; for public pages, serving cached static fallbacks may be acceptable. Decide fallbacks at the business level and test them.

## 5. Intra-Region Failover Steering

### 5.1. Distributing Across Availability Zones

A common pattern spreads targets across multiple availability zones behind one stable entry point:

~~~mermaid
flowchart TB
    U[Clients] --> DNS[DNS]
    DNS --> LB[Regional Load Balancer]
    subgraph Region[Cloud Region]
        subgraph AZA[Availability Zone A]
            A1[API target A1]
            A2[API target A2]
        end
        subgraph AZB[Availability Zone B]
            B1[API target B1]
            B2[API target B2]
        end
        LB --> A1
        LB --> A2
        LB --> B1
        LB --> B2
        A1 --> DB[(Database HA)]
        A2 --> DB
        B1 --> DB
        B2 --> DB
    end
~~~

When a single target turns unhealthy, the LB ejects it and routes traffic to healthy peers. If an entire AZ fails, the surviving AZ keeps serving only if all required components have matching fault-tolerant capacity and topology.

Verify whether the load balancer supports cross-zone routing, whether each zone holds sufficient post-failure compute capacity, whether databases, caches, queues, secret endpoints, egress, and DNS survive zone loss, and whether returning zones ramp traffic smoothly.

For example, if peak load is 600 requests/sec split evenly across two zones (300 each), losing one zone pushes all 600 onto the survivor. Size post-failure capacity accordingly or enforce load shedding/rate limits and agreed degraded modes. Running in two zones does not automatically guarantee post-failover capacity.

### 5.2. Regional Load Balancing and DNS Failover

~~~mermaid
flowchart TB
    U[Global users] --> G[Global DNS / Traffic Manager]
    G -->|Primary healthy| P[Region A endpoint]
    G -.->|Failover| S[Region B endpoint]
    subgraph RA[Region A - Primary]
        P --> PA[Regional LB]
        PA --> AP[Application targets]
        AP --> DP[(Primary data)]
    end
    subgraph RB[Region B - Standby]
        S --> PB[Regional LB]
        PB --> AS[Standby / scaled application]
        AS --> DS[(Replicated / recoverable data)]
    end
    DP -.->|Replication / backup path| DS
~~~

DNS failover evaluates endpoint health checks and updates DNS answers. However:

- Clients, resolvers, and middleboxes cache records up to TTL or per local policies.
- Not every client immediately re-queries DNS when a primary endpoint fails.
- Apps holding long-lived connections or pinning IPs may stick to the old endpoint.
- Lower TTLs increase DNS query load without eliminating forced caching by clients/resolvers.
- DNS failover does not sync databases or resolve conflicts if two regions accept writes simultaneously.

Thus, DNS failover is **not instantaneous cutover** and should rarely be the sole mechanism across all client types. Pair it with global load balancers/traffic managers or client retry and re-resolution logic.

### 5.3. Multi-Region Routing Strategies

| Strategy | How It Works | When to Use | Trade-Offs |
|---|---|---|---|
| Active-passive | Primary handles traffic; standby sits idle or scaled down | Simplifies write consistency model | Standby capacity, warm-up lag, and replication lag |
| Active-active | Multiple regions serve live traffic | Needed for global latency and backed by compatible data design | Write conflicts, routing, observability, and ops complexity |
| Weighted | Splits traffic by weight | Canaries, migrations, load distribution | Weights ignore health/latency unless paired with checks |
| Latency-based | Picks endpoint by estimated RTT | Geographically dispersed users | DNS latency does not reflect full app response time |
| Geolocation / geoproximity | Routes by user location or geographic rules | Data residency or regional policies | GeoIP is imperfect |
| Failover | Activates standby when health policy triggers | Disaster recovery | Requires fencing to prevent split-brain |

Select strategies based on RTO/RPO, data topology, user spread, regulatory rules, budget, and operational maturity. **Multi-region is not automatically better than multi-AZ**; active-active can massively inflate complexity when writes are centralized or conflict resolution is absent.

### 5.4. Failover Readiness Requires More Than a Responsive Endpoint

Before shifting traffic to a standby region, verify: does it have sufficient instances, quotas, certificates, secrets, and latest configs; is the database recovered/replicated; is split-brain prevented; could queues, schedulers, and background jobs double-run; do monitoring and on-call tooling work independently outside the failed region; and who is authorized to declare failover and execute fencing?

A health check may show Region B responding while its database lacks recent commits or lacks write promotion. Build service-level readiness and explicit data failover steps; never open write traffic merely because a TCP/HTTP probe passes.

### 5.5. Failback — Returning to Primary

Once the primary recovers, never shift traffic back just because probes turn green. Verify root cause is resolved; reconcile any writes from the failover window; pick resync direction and verify replication lag; confirm fencing prevents dual writers; shift traffic incrementally while watching SLIs.

Failback sometimes requires data migrations or scheduled maintenance windows. Healthy endpoints alone are never sufficient to flip database roles.

## 6. Designing Safe Health Endpoints

### 6.1. Composite Readiness Without Calling Every Dependency

A readiness check can combine local runtime states:

~~~text
isReady =
    startupComplete
    AND configurationValid
    AND listenerAcceptingRequests
    AND criticalLocalResourcesAvailable
    AND requiredDataPathAcceptingWork
~~~

When checking database reachability, prefer lightweight short-timeout checks or recent connection/operation health signals over running heavy queries on every probe. For critical databases, readiness can reflect core write/read capability—yet avoid letting transient DB slowness eject every instance simultaneously until none remain to handle recovery traffic.

Optional dependencies like email or search should report through separate metrics and degrade only their own endpoints rather than failing whole-process liveness.

### 6.2. Separate Load Balancer Health Endpoints from Admin Diagnostics

Load balancer endpoints should return minimal payloads:

~~~json
{
  "status": "ready"
}
~~~

Internal diagnostics endpoints for operators may expose details, strictly protected by authentication and access controls:

~~~json
{
  "status": "degraded",
  "checks": {
    "database": "available",
    "cache": "unavailable",
    "notificationQueue": "available"
  },
  "checkedAt": "2026-11-18T05:00:00Z"
}
~~~

Never let public health endpoints expose internal hostnames, database addresses, clusters, accounts, secrets, stack traces, or SQL error text. Health endpoints must never run migrations, mutate state, or emit side-effect messages.

### 6.3. Protecting Health Checks from Abuse

- Restrict internal diagnostic endpoints to authorized probe sources where supported.
- Enforce rate/resource bounds so endpoints stay lightweight and never become DoS amplifiers.
- Use TLS/authentication for cross-network or cross-region probes.
- Avoid leaking sensitive details; log/meter sufficiently for triage without creating log storms.
- Exclude probe traffic when computing user SLIs, while retaining end-to-end synthetic monitoring.

## 7. Observing and Operating Health and Failover

### 7.1. Look Beyond Green/Red Status Indicators

| Metric Group | Examples | Meaning |
|---|---|---|
| Target state | Healthy/unhealthy/initial/draining counts | Current traffic-serving capacity |
| Probe behavior | Pass rate, timeouts, latency, status codes | Misconfigured probes or target flapping |
| User impact | 5xx, timeouts, request success rate, p95/p99 | Are real users actually affected? |
| Capacity | CPU, memory, DB connections, queue lag | Can surviving targets absorb shifted load? |
| Traffic distribution | Requests/bytes by zone/region/target | Confirms load balancing and failover execution |
| Recovery | Detection time, drain time, failover/failback duration | Tracks against RTO and runbooks |
| Data health | Replication lag, consistency checks | Does standby hold sufficiently fresh data? |
| DNS / routing | Health state, DNS answers, TTL, resolution latency | Are clients receiving updated routes? |

Alert on impact: unhealthy target percentage exceeding thresholds, zero healthy targets, remaining capacity below failover minimums, rapid error-budget burn, or stalled failovers. One unhealthy target during a deploy may be normal; a whole zone turning red or concurrent latency spikes demand immediate priority.

### 7.2. Runbook When Targets Are Ejected

1. Scope the incident: single target, multiple targets in one AZ, whole region, or a single checker?
2. Check user impact: error rates, latency, request success, and business journeys.
3. Diagnose root cause: process, startup, readiness, network, certificate, config, quota, or dependency.
4. Check remaining capacity: can healthy targets carry load without breaching DB/connection/queue limits?
5. Decide load shedding or failover per runbook, data risk, and approval authority.
6. Recover targets: fix root cause, warm up, verify readiness, and reintroduce gradually.
7. Reconcile in-flight requests, messages, data state, routing, SLIs, and cost.
8. Record detection/ejection/recovery timestamps, false positives/negatives, root cause, and follow-up actions.

Automation handles single-instance faults well; promoting database writers or failing over regions typically requires explicit guardrails and clear authorization due to data impact.

### 7.3. Testing Health Checks and Traffic Steering

| Test | Controlled Execution Method | Outcome to Verify |
|---|---|---|
| Slow startup | Extend bootstrap/cache warm-up delay | Zero restart loops; receives traffic only once ready |
| Wedged process | Simulate deadlock / blocked event loop | Liveness detects and recovers cleanly |
| Readiness false | Flip instance temporarily unready | LB/orchestrator stops sending new traffic |
| Slow dependency | Inject latency into DB/cache/provider | Timeouts, readiness, and graceful degradation work without mass ejection |
| Killed target | Terminate an active load-bearing instance | Detection lag, draining, user impact, and capacity |
| Long drain | Hold long requests/streams or active workers | Zero unexpected drops outside policy |
| Target flapping | Alternate passing and failing probe responses | Hysteresis prevents rapid state oscillations |
| Zone loss | Approved zone fault injection | Traffic shifts cleanly to surviving zone; capacity and data path hold |
| DNS failover | Flip primary endpoint health in test env | Resolvers/clients shift within measured bounds |
| Region failover/failback | Execute full DR drill | RTO/RPO, fencing, writer state, routing, and data match targets |

Every test needs a baseline, approved scope, abort criteria, test lead, and rollback steps. Never kill production nodes or alter live DNS without operational authorization.

## 8. End-to-End Example for the Scheduling Application

### 8.1. Illustrative Requirements

A scheduling service runs in one region across two availability zones. Stateless APIs run multiple instances backed by a managed HA database. Assumed requirements:

- Single-instance failures must not take down the API.
- Losing one zone must not drop booking transactions provided capacity and DB failover behave as designed.
- Slow email delivery must never fail Booking API health.
- Deploys/scale-in must not sever active requests outside policy.
- Operators can identify which target was ejected and why.

Convert these into concrete SLO/RTO/RPO targets and validate them on the chosen cloud provider before deployment.

### 8.2. Execution Flow

~~~mermaid
sequenceDiagram
    participant LB as Regional Load Balancer
    participant A as API Instance A
    participant B as API Instance B
    participant DB as Managed DB HA
    LB->>A: Probe /health/ready
    A-->>LB: 200 ready
    LB->>B: Probe /health/ready
    B-->>LB: 200 ready
    LB->>A: POST /v1/bookings
    A->>DB: Commit booking + outbox
    DB-->>A: Commit success
    A-->>LB: 201 Created
    LB-->>A: Deregister / drain
    Note over LB,A: Stop new requests; in-flight drains per policy
    LB->>B: Route new request
    B->>DB: Process next request
    A-->>LB: Shutdown after drain
    Note over DB: Notification queue processes async, isolated from API health
~~~

### 8.3. Decision Matrix

| Question | Illustrative Decision | Rationale and Boundaries |
|---|---|---|
| Is the process alive? | Lightweight process/event-loop liveness probe | Catches deadlocks; avoids heavy DB calls |
| Can the instance serve? | Readiness checks startup, config, and critical dependencies | Separates process liveness from traffic eligibility |
| How does LB probe? | Lightweight HTTP endpoint with measured timeouts/thresholds | Detects app-level faults; still pair with synthetic checks |
| How are failed targets removed? | Eject from pool and drain per policy | In-flight requests are not automatically replayed |
| Single-zone outage? | Regional LB shifts load to surviving zone sized for full load | Holds only if DB/network/critical deps also survive |
| Email provider outage? | Queue buffers jobs with retries/DLQ; Booking API stays healthy | Alert on backlog; exclude email from API readiness |
| Primary region outage? | Fail over only once DR data path and writer fencing are ready | DNS/global routing alone never secures data consistency |

## 9. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| One endpoint for startup, liveness, and readiness | Restart loops or unready targets taking traffic | Separate probes by triggered action |
| Calling external DB/cache inside liveness | Slow dependency restarts entire fleet | Keep liveness local/light; handle dependencies in readiness |
| Using TCP-only probes | Port stays open while app is deadlocked | Use meaningful HTTP/gRPC readiness probes |
| Running heavy business logic in probes | Adds load and side effects | Keep probes cheap; isolate synthetic tests |
| Setting unhealthy threshold too low | Noise ejects healthy instances | Tune from latency, timeouts, intervals, and hysteresis |
| Setting threshold too high | Dead targets keep serving failing requests | Set explicit detection targets and verify |
| Restarting all targets on DB errors | Fleet loses capacity; DB struggles harder to recover | Remove external dependencies from liveness |
| Omitting connection draining | Active requests dropped during deploys/scale-in | Configure graceful shutdown and test draining |
| Assuming LB retries all failed requests | Duplicate mutations or dropped requests | Enforce client retries with idempotency and clear semantics |
| Failing over on one failing probe | Spurious cross-region traffic shifts | Require corroborated signals and user-impact checks |
| Treating low DNS TTL as instant cutover | Clients retain cached records/open sockets | Test resolvers/clients and use appropriate routing |
| Equating multi-AZ with multi-region DR | Fails during full-region outage | Build dedicated DR, replication, backups, and runbooks |
| Failing back immediately on green probes | Data divergence or split-brain | Fence writers, reconcile, warm up, and ramp traffic slowly |
| Not measuring load after target ejection | Survivors saturate while probes look green | Monitor saturation/capacity and SLIs |

## 10. Practice Exercise: Designing Health Checks and Failover

**Scenario:** A booking application runs across two availability zones with multiple API instances per zone. A regional load balancer probes targets. The primary database is a managed relational DB; a notification queue and cache are supporting dependencies. Product requires keeping the API up on single-instance loss, limiting blast radius on zone loss, and maintaining a DR plan for region loss. The team has not yet measured startup time, p95 latency, drain duration, or post-failure capacity.

Produce a design document covering:

1. **Health classification:** define startup, liveness, readiness, target health, synthetic checks, and dependency health, stating triggered actions.
2. **Probe design:** select path/port/protocol, interval, timeout, thresholds, initial delay, and expected statuses; explain how values will be derived from measurements.
3. **Dependency matrix:** DB, cache, queue, and email provider; specify which break API readiness vs. degrade gracefully.
4. **Target ejection:** describe unhealthy state, deregistration, connection draining, graceful shutdown, and in-flight request behavior.
5. **Intra-region:** diagram the two-zone deployment, calculate surviving capacity after single-zone loss, list shared dependencies, and define all-targets-unhealthy behavior.
6. **Cross-region:** choose active-passive or an alternative; describe health signals, DNS/global routing, replication, fencing, RTO/RPO, and failback.
7. **Observability:** design dashboards for target state, probe latency/errors, user error rates, traffic split, capacity, replication lag, and recovery time.
8. **Testing:** plan tests for wedged processes, slow DB, draining, zone loss, DNS failover, and failback; record baselines, abort criteria, and pass gates.

| Topic | Question to Answer | Evidence |
|---|---|---|
| Readiness | Which business requests can this target accept? | Endpoint/dependency failure tests |
| Liveness | Which conditions genuinely require a restart? | Deadlock/startup tests |
| Thresholds | How fast are bad targets detected and ejected? | Measured detection times |
| Draining | How are in-flight requests/streams/jobs handled? | Deploy/scale-in tests |
| Capacity | After losing a target/zone, does enough capacity remain? | Load and saturation tests |
| Failover | Which signals justify shifting traffic? | DR drills and decision logs |
| Data safety | Does standby hold valid data and writer state? | Replication lag, fencing, reconciliation |
| Failback | Who approves, and how are data and traffic restored? | Runbooks and measured RTO/RPO |

**Completion criteria:** A reader can trace from a failing probe to target ejection, understand how in-flight requests are handled, see where traffic shifts, and identify which tests prove fault tolerance within committed bounds.

## 11. Key Takeaways

- **Health checks drive concrete actions:** startup delays probes, liveness restarts wedged processes, readiness gates new traffic, and load balancers select targets.
- **Probes must be representative yet lightweight:** check enough to decide safely without polling every dependency or causing load/side effects.
- **Target removal requires full lifecycle handling:** unhealthy detection, deregistration, draining, shutdown, warm-up, and controlled re-entry.
- **Traffic steering depends on capacity and data:** Multi-AZ, regional failover, and DNS failover cover different failure scopes.
- **Failover is more than routing:** standby regions require data paths, permissions, fencing, quotas, observability, runbooks, and failback plans.
- **Every commitment must be tested:** detection time, user impact, post-failure capacity, RTO/RPO, and convergence time require measured numbers.

System entry points must steer traffic to components capable of serving it, yet health states are only approximate signals. Sound designs pair purpose-built probes, stable thresholds, controlled target ejection, fault-domain steering, data-integrity protection, and user-centric observability—allowing systems to absorb faults without turning a localized degradation into a widespread outage.
