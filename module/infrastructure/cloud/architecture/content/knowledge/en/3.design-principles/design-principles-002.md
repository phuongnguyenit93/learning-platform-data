# Designing for Failure, Change, and Growth

> **Chapter:** Design Principles  
> **Module:** CLOUD_ARCHITECTURE  
> **Scope:** Designing cloud application architectures from business requirements to networking, compute, data, and deployment models; balancing reliability, security, scalability, cost, operations, and evaluating under Well-Architected principles.

## Learning Objectives

After this lesson, you will be able to:

1. Explain why **failure, change, and growth** must be treated as normal states in the lifecycle of a cloud system.
2. Analyze failure domains, single points of failure, dependency chains, and fault-tolerance boundaries of an architecture.
3. Select appropriate controls: redundancy, fault isolation, timeouts, bounded retries, idempotency, queues, graceful degradation, and backup and recovery.
4. Design safe change using module boundaries, compatibility contracts, Infrastructure as Code, progressive delivery, data migrations, and rollback capabilities.
5. Estimate capacity, choose compute/data scaling strategies, and verify resilience against traffic spikes.
6. Explain trade-offs among reliability, change velocity, complexity, and cost; evaluate using Well-Architected thinking.

## 1. Three Certainties of a Running System

An application may work well during a demo yet still be unprepared for real production operations. Servers get replaced; networks drop packets or experience latency spikes; databases become overloaded; payment providers go down temporarily; development teams release new versions; user traffic grows faster than expected. The architecture must account for these scenarios before they turn into severe incidents.

| Design Direction | Question to Answer | Expected Outcome |
|---|---|---|
| **For failure** (*design for failure*) | If a component, connection, or infrastructure domain fails, what can the system still do? | Limit blast radius, preserve data correctness, detect, and recover |
| **For change** (*design for change*) | When modifying business logic, APIs, schemas, or infrastructure, how do we release with control? | Loosely coupled components, compatibility, testing, and a rollback path |
| **For growth** (*design for scale*) | As users, requests, data, and background jobs grow, where do the bottlenecks lie? | Scale with demand within performance, operational, and cost limits |

These three directions interact with one another. Increasing the number of instances to scale can exhaust database connections; deploying a faulty release all at once can bring down every instance; uncontrolled retries can amplify a minor glitch into a system-wide outage. Therefore, you cannot simply enable autoscaling or run two redundant servers and declare the architecture resilient.

### 1.1. Starting from Business Impact

Consider an **appointment booking platform** with flows for schedule lookup, slot reservation, booking confirmation, and sending notifications:

- **Booking:** must never double-book a doctor/time slot; must be safe when users resend requests.
- **Lookup:** requires fast responses, but can tolerate slightly stale data within a business-agreed boundary.
- **Email/SMS:** can be delivered with a delay without losing the completed booking transaction.
- **Management reports:** can be temporarily paused under overload to reserve capacity for core transactions.

These distinctions determine what must be synchronous, what can be processed asynchronously later, which data is the source of truth, and when graceful service degradation is acceptable.

### 1.2. Setting Measurable Targets

| Dimension | Illustrative Target | Must Be Clarified Before Committing |
|---|---|---|
| Availability | 99.9% of valid booking requests succeed over 30 days | Where is it measured from, which errors are in scope, and do timeouts count as failures? |
| Latency | Lookup API p95 under 400 ms at target load | From which client regions, and for which datasets and endpoint mix? |
| Peak Load | 600 requests/second | Read/write ratio, concurrency, and duration of the peak? |
| Recovery | RTO 60 minutes, RPO 15 minutes upon primary database loss | Does this cover full region loss or accidental data deletion? |
| Change | Release API updates without full-system downtime | Can old and new versions run concurrently and be rolled back? |
| Cost | Monthly budget and alert thresholds | Does it account for redundancy, logs, backups, egress, and peak-hour costs? |

The values above are **hypothetical examples for study purposes only**, not universal standards for every system.

- **SLI (Service Level Indicator):** an actual measured metric, such as the ratio of successful requests.
- **SLO (Service Level Objective):** the target for an SLI over a specific measurement window.
- **RTO (Recovery Time Objective):** the target maximum time to recover after a defined incident type.
- **RPO (Recovery Point Objective):** the maximum acceptable loss of recent data, expressed in time, for a defined incident type.
- **Error budget:** the permissible deviation from an SLO, which can be used to balance change velocity and reliability investment.

For example, a 99.9% SLO over 30 days corresponds to roughly **43.2 minutes** of unavailability budget under ideal time calculation; actual results also depend on the SLI definition and measurement method. RTO/RPO must be tied to specific scenarios: losing a single instance, losing a zone, accidental data deletion, and losing an entire region each require different plans.

## 2. Designing for Failure: Never Assume Dependencies Always Work

### 2.1. Mapping Failure Domains and Dependency Chains

A **failure domain** is a set of components that can fail together from a single root cause: a process, VM, node, network path, availability zone, region, or shared management plane. Two app instances on the same VM do not protect against VM failure; two apps in two different zones still share a single point of failure if both depend on a database running in only one zone.

~~~mermaid
flowchart LR
    C[Users] --> E[DNS / Edge / HTTPS Load Balancer]
    E --> A[Booking API]
    A --> DB[(Database)]
    A --> IDP[Identity provider]
    A --> Q[(Queue)]
    Q --> W[Notification worker]
    W --> S[Email / SMS provider]
    A --> OBJ[(Object storage)]
~~~

For every arrow in the diagram, ask five questions: if the target does not respond, how long does the caller wait; if the response is lost after the transaction succeeds, how do we detect it; if retried, does it cause duplicate side effects; can many failing requests exhaust shared resources; who receives the alert and how is it recovered?

| Incident | Typical Consequence | Mechanisms to Consider |
|---|---|---|
| A process/VM dies | In-flight requests are lost | Replicas, health checks, instance replacement, idempotency |
| A zone loses connectivity | Loss of part of compute/data capacity | Multi-AZ across the entire critical path, failover testing |
| Database slows down or exhausts connections | API holds connections, requests pile up | Bounded connection pools, timeouts, load shedding, and alerting |
| Email provider goes down | API slows down if sent synchronously | Queues, bounded retries, DLQ, and alerting |
| Accidental data deletion | Replicas may replicate the delete operation as well | Independent backups, point-in-time recovery if available, restore testing |
| Faulty release/configuration | Multiple instances degrade simultaneously | Canary/rolling deployment, metrics, and rollback |
| Sudden traffic spike | Exhausts CPU, workers, quotas, DB capacity | Admission control, autoscaling, backpressure |

**Redundancy does not equal independence:** replicas can share DNS, IAM, keys, quotas, configuration, pipelines, or databases. Correlated failures must be analyzed rather than just counting instances.

### 2.2. Redundancy and Recovery Must Match the Scope

- **Replicas + load balancing:** distribute requests and avoid single-instance dependency; apps should be stateless for critical sessions, or store state in an appropriate shared system.
- **Multi-AZ:** reduces the impact of a single-zone failure if every core dependency is genuinely configured accordingly.
- **Managed service HA:** reduces administrative effort and can support failover; you must understand failover duration, connection drops, replication lag, and service limits.
- **Backup/restore:** recovers data after logical errors or major incidents; backups must be protected against deletion/overwriting and tested for restoration.
- **Multi-region DR:** consider if full-region failure tolerance or geographic requirements apply; trade off data consistency, routing, complexity, and cost.

Distinguish between **high availability** (continuing to serve within the designed failure domain), **disaster recovery** (recovering after an incident exceeding normal fault tolerance), and **data correctness** (never writing wrong, missing, or duplicate business state). A system that always returns HTTP 200 while double-booking appointments is still unreliable.

### 2.3. Preventing Cascading Failures

If every request waits indefinitely on a slow dependency, thread/connection pools will exhaust, causing other features to fail as well.

| Mechanism | Effect | Risk When Misused |
|---|---|---|
| **Timeout/deadline** | Prevents holding resources indefinitely, bounds end-to-end duration | Per-layer timeouts summing up beyond the client deadline |
| **Bounded retry** | Recovers from transient errors if the operation is safe to retry | Infinite retries across multiple layers, increasing load on an already overloaded dependency |
| **Exponential backoff + jitter** | Spaces out attempts, reduces synchronized retry storms | Unbounded backoff/deadlines |
| **Circuit breaker** | Temporarily stops calling a persistently failing dependency, probes recovery in a controlled way | Missing alerts, fallbacks, or recovery probing |
| **Bulkhead** | Isolates resource pools so one feature cannot stall the entire system | Sharing a single unbounded pool across all features |
| **Rate limit/load shedding** | Rejects excess load early when beyond processing capacity | Accepting all requests and causing mass timeouts at the DB |
| **Backpressure** | Forces upstream callers to slow down when downstream is saturated | Unbounded queue growth, uncontrolled latency spikes |

Example of allocating a time budget, **not a mandatory configuration**:

~~~text
End-to-end client request deadline: 3 seconds.
Database query: bounded timeout and limited connection pool.
External service call: short timeout, at most 1-2 retries when safe.
Retry: use backoff + jitter, never exceeding remaining deadline.
Non-essential dependency fails: defer/skip secondary feature with an appropriate notice.
Essential dependency fails: return a clear, measurable error, never report false success.
~~~

You must measure real latency and observe the behavior of each dependency. One original request with 3 retries produces up to **4 calls** to the dependency; retries across multiple layers can amplify load much more severely. Limit retries to the appropriate layer and prefer idempotent operations.

**A response error does not prove the operation failed.** For example, a payment system may have charged the card while the response was lost; retrying without an idempotency key could charge the customer twice. For any operation with business side effects, design a way to recognize whether the transaction already executed or query its status before resending.

### 2.4. Intentional Graceful Degradation

During overload, a booking platform can disable ranking/recommendations, serve cached read data that is allowed to be briefly stale, defer notifications, and restrict reporting requests. The API must preserve priority for **accurate booking writes and secure authentication**. If a transaction cannot be committed, it must return an error or an unconfirmed state; it must never report a successful booking. Never bypass authorization to increase throughput.

Handling overload can also include returning HTTP 429 for requests exceeding limits and instructing callers to retry according to policy. Failing fast, clearly, and measurably is usually better than waiting indefinitely and exhausting all resources.

### 2.5. Protecting Data Against Duplicate Requests and Messages

To prevent two customers from booking the same time slot, invariants must be enforced at the write point: a transaction, a unique constraint under a discrete slot model, or an appropriate concurrency control mechanism. Having two requests both "read that a slot is free" and then write separately does not prevent race conditions.

One way to implement **idempotency** for booking creation:

1. The client sends an idempotency key for exactly one booking intent; scope the key by user and operation.
2. The API validates authentication, payload, and the key's processing state in durable storage.
3. Inside a transaction, write the booking, bind the key to the outcome, and enforce the slot constraint to prevent duplicates.
4. Repeated requests with the same key and payload receive the prior result or an in-progress status; the same key with a different payload must be rejected.
5. Define key retention duration and retry windows according to the transaction lifecycle.

For asynchronous processing, queues may redeliver messages. Consumers must implement idempotency/deduplication, bounded retries, and a **dead-letter queue (DLQ)** for messages that persistently fail processing. If you need to commit a booking and guarantee an event is emitted afterward, use a **transactional outbox**: write the event within the same data transaction, and after commit a dispatcher reads the outbox and pushes to the queue. The dispatcher may emit duplicates, so consumers must still guard against duplicate processing.

~~~mermaid
sequenceDiagram
    actor U as Bookers
    participant API as Booking API
    participant DB as Database
    participant O as Outbox dispatcher
    participant Q as Queue
    participant W as Worker
    U->>API: Create booking + idempotency key
    API->>DB: Transaction: booking + key + outbox
    alt Slot available
        DB-->>API: Commit succeeded
        API-->>U: Booking ID
        O->>DB: Read committed outbox
        O->>Q: Publish booking.created
        Q->>W: Deliver message, may duplicate
        W->>W: Check idempotency
        W-->>U: Send notification via provider
    else Conflict or invalid
        DB-->>API: Conflict / rollback
        API-->>U: Booking not created
    end
~~~

Sending to an external service can still land in an uncertain state between "sent" and "confirmed completed." If the provider supports an idempotency key, use it; otherwise, manage duplicate-send risk by policy rather than promising end-to-end "exactly once" delivery.

### 2.6. Recovery Must Be Rehearsed

A recovery runbook needs to state **failure scenarios, owner, trigger conditions, step-by-step actions, correctness checks, and completion criteria**. Writing "backup enabled" is not enough.

1. Single-instance failure: how quickly does the load balancer stop sending traffic, and how are in-flight requests handled?
2. Single-zone failure: do the app, DB, queue, network, and dependencies continue operating?
3. Accidental deletion / data corruption: are there independent backups or point-in-time recovery?
4. Full-region failure: is there a DR plan, or is this an accepted risk?
5. Configuration/permission error: is there still a way to restore administrative access, adjust configuration, and roll back safely?

Restore tests must confirm **data actually reads/writes properly and the application functions**, not merely that a backup job reported success. Record measured RTO/RPO, scope of lost data, and test conditions. Replicas can replicate accidental delete commands as well, so replicas do not replace backups.

## 3. Designing for Change: Updating Systems While Preserving Compatibility

### 3.1. Component Boundaries Determine the Cost of Change

Changeability does not begin with CI/CD tools; it begins with how responsibilities are partitioned:

- Separate **core business logic** (booking rules, payment states) from the HTTP layer and external provider integrations.
- Maintain clear interfaces/contracts between modules; avoid letting modules arbitrarily mutate one another's database tables.
- Keep dependencies directional and testable; never hardcode secrets or environment configurations directly in source code.
- Split out microservices when there is a concrete reason involving business boundaries, independent deployment/scaling, or fault isolation, and the team has the operational capability to run them.

A **modular monolith** with clear module boundaries often satisfies initial change needs well. Microservices can multiply APIs, versions, network calls, observability overhead, and distributed transactions; "splitting things up" does not automatically make an architecture agile.

### 3.2. Maintaining Compatibility Across Concurrent Versions

Rolling/canary deployments have a phase where **old and new versions run simultaneously**. Therefore, APIs, events, and schemas must support the transition period.

| Change Type | Common Safe Approach | Error-Prone Approach |
|---|---|---|
| API | Add optional fields, preserve old semantics, version breaking contract changes | Removing/renaming required fields while old clients remain |
| Message/event | Consumers tolerate unknown new fields, use version conventions | Changing format abruptly, causing old-version workers to fail |
| Database | **Expand → migrate/backfill → switch → contract** | Dropping old columns in the same deploy as new code |
| Configuration | Versioned, validated, tested on a small scope | Untracked manual edits causing drift across environments |
| Keys/secrets | Rotate keys with an overlap period when the protocol allows | Revoking old keys before all consumers switch over |

Example of renaming a phone number column from **phone** to **contact_phone**:

1. **Expand:** create `contact_phone` as nullable while keeping `phone`; new code should handle data in both forms.
2. **Migrate:** backfill in batches to avoid holding large locks; synchronize writes during the transition period, and track remaining missing records.
3. **Switch:** switch reads to `contact_phone` after verifying the data and all relevant consumers.
4. **Contract:** remove `phone` only when no old version depends on it and the rollback window has closed.

For real schemas, evaluate locks, dataset size, replication, indexes, and database engine before running migrations. **Rolling back code does not mean rolling back data.** An operation that dropped columns or performed an irreversible transformation requires a separate recovery plan and may require pausing a write stream within a controlled window.

### 3.3. Progressive Delivery with Stop Conditions

~~~mermaid
flowchart LR
    A[Code / config commit] --> B[Build + test + security checks]
    B --> C[Deploy to staging environment]
    C --> D[Verify contracts and migrations]
    D --> E[Canary to small cohort]
    E --> F{SLI, error rate, latency met?}
    F -- Yes --> G[Gradually increase traffic]
    G --> H[Complete release]
    F -- No --> I[Halt rollout, rollback or mitigate impact]
~~~

Common strategies:

- **Rolling deployment:** replaces batches of instances sequentially; relatively capacity-efficient, but requires handling old/new versions running concurrently.
- **Blue-green deployment:** prepares two environments, then switches traffic; switches quickly, but temporarily increases resource costs and still requires solving shared data compatibility.
- **Canary deployment:** routes a fraction of traffic to the new version, measuring SLIs before increasing the percentage; requires routing controls and representative metrics.
- **Feature flags:** toggle features by cohort or condition; requires managing change permissions, fallbacks, lifecycle, and cleaning up stale flags.

A safe release process must confirm **which changes are reversible**, schema/data state after rollback, observability plans, halt conditions, and the responsible owner. Track business metrics such as successful/duplicate/failed bookings alongside error rate, latency, and saturation; a "container Running" status is not sufficient to declare a release successful.

### 3.4. Infrastructure as Code and Infrastructure Change Control

Infrastructure is also part of the application's versioned state. **Infrastructure as Code (IaC)** turns networking, compute, IAM, databases, and observability into reviewed configurations; CI/CD enables reproducible environments and pre-apply impact checks.

The workflow should include: syntax/policy checks, displaying the change plan, reviewing permissions and data impact, applying incrementally by scope, monitoring outcomes, and detecting **configuration drift**. IaC does not guarantee safety on its own: a syntactically valid change can still delete resources, open access permissions, or incur unexpected costs.

For irreversible changes, use phased migration strategies or test in an isolated environment first. Exercise particular caution with changes to IAM, routing, databases, and encryption keys because they can impact multiple workloads simultaneously.

### 3.5. Using Metrics to Evaluate Change Capability

Useful metrics:

- **Deployment frequency:** frequency of successful releases as defined by the team.
- **Lead time for changes:** time from code change to running in the target environment.
- **Change failure rate:** percentage of changes leading to service degradation or requiring intervention.
- **Failed deployment recovery time:** time to recover after a failed release.
- **Rollback success:** rate at which drills or real incidents recover according to plan.

Do not chase deployment counts. The goal is **small, verifiable changes, fast feedback, and controlled recovery**.

## 4. Designing for Growth: Scaling at the Right Bottleneck

### 4.1. Distinguishing Vertical Scaling, Horizontal Scaling, and Elasticity

- **Vertical scaling (scale up):** increasing CPU/RAM/IOPS for a single instance; simple, but hits hardware ceilings and sometimes requires stopping/restarting.
- **Horizontal scaling (scale out):** increasing the number of instances or workers; suited for distributable tasks, requires load balancing and state management.
- **Elasticity:** adjusting resources dynamically with demand; constrained by startup time, observation metrics, quotas, and cost.

Not all layers scale the same way. Stateless APIs are usually easy to replicate; databases with transactions and state require evaluating query optimization, read replicas, partitioning, resource upgrades, or sharding when genuinely needed.

### 4.2. Estimating Capacity by Unit of Work

A starting formula for the number of compute instances:

~~~text
Required instances
  = ceil(peak traffic / sustainable throughput per instance at target utilization)
~~~

Suppose load testing shows **each instance handles 100 requests/second at its performance limit**, but the team only wants to operate at **80% of measured capacity** to leave headroom. Each instance is then budgeted at roughly 80 requests/second. At a peak load of 600 requests/second with a similar request mix:

~~~text
ceil(600 / 80) = 8 instances
8 instances × 80 = 640 requests/second at target utilization
~~~

**Eight instances only satisfy normal peak load**, without proving zone fault tolerance. If split 4 instances across each of two zones and one zone is lost, the surviving side only retains 4 × 80 = 320 requests/second at target utilization. To **immediately** sustain 600 requests/second after losing a zone, you may need 8 instances in each zone (16 instances when balanced across two zones), or accept graceful degradation/rate limiting and scale-up delay. The decision must weigh cost, number of actually available zones, database capacity, and limits of other services.

This example distinguishes two different concepts: **sufficient capacity for peak hours** and **sufficient capacity when a failure domain is lost**. Actual throughput per instance also depends on read/write ratio, database queries, cache hit rate, payload size, latency, GC, networking, and connection pooling policy; it must be re-measured under representative conditions.

### 4.3. Databases and Caches Have Their Own Limits

Scaling out API instances easily shifts the bottleneck to the database. Options must be evaluated with measurements:

1. **Query observability:** identify slow queries, N+1 patterns, full table scans, long-running transactions, lock contention, and connection exhaustion.
2. **Schema/index optimization:** add indexes supporting critical queries, while accounting for write overhead and storage size.
3. **Strategic caching:** choose data tolerant of staleness, configure TTL/invalidation, control cache stampedes, and handle cache failures.
4. **Read replicas:** offload read traffic appropriately, accounting for replication lag; never rely solely on a lagging replica to confirm slot availability.
5. **Increase database resources or service capacity:** check limits, maintenance windows, and cost projections.
6. **Partitioning/sharding when justified:** distributes load, but increases complexity in transactions, joins, queries, rebalancing, and recovery.

Even a managed or auto-scaling database service has limits on connections, I/O, transactions, throughput, and quotas. Never treat API autoscaling as proof that the entire system can scale infinitely.

### 4.4. Queues Absorb Load Spikes, They Do Not Eliminate Work

Queues allow producers and consumers to operate at different speeds, but **backlog grows whenever arrival rate exceeds processing rate**.

Suppose a 10-minute campaign generates **400 notifications/second**, while workers only process **250 notifications/second**, ignoring retries and per-job variance:

~~~text
Accumulation rate = 400 - 250 = 150 notifications/second
Backlog after 10 minutes = 150 × 600 = 90,000 notifications

After the campaign, arrival rate drops back to 100 notifications/second:
Remaining backlog drain capacity = 250 - 100 = 150 notifications/second
Approximate drain time = 90,000 / 150 = 600 seconds (10 minutes)
~~~

If the business requires delivering notifications within **2 minutes**, this configuration fails during the peak wave. You must add workers, introduce priority queues, or renegotiate the SLO. Metrics should include **oldest message age, queue depth, throughput, retry count, and DLQ count**; queue depth alone can mask old messages stuck for too long.

### 4.5. Preventing Overload Before Scaling Catches Up

Architectures designed for growth must also handle **unplanned** load:

- **Rate limits/quotas:** prevent a single customer or tenant from monopolizing shared resources.
- **Admission control:** accept only the amount of work that can be completed within desired bounds.
- **Backpressure:** signal upstream callers to slow down when downstream is saturated.
- **Pool protection:** bound DB connections, workers, memory, queues, and concurrent calls.
- **Business prioritization:** reserve capacity for bookings over reporting or recommendations.
- **Warm capacity:** maintain headroom when autoscaling requires startup time.
- **Cost guardrails:** budgets, alerts, policies preventing runaway scaling, and growth reviews.

Autoscaling is a control loop with lag. Relying solely on CPU as a metric when the real bottleneck is the DB, setting inappropriate cooldowns, or hitting quotas can spin up many instances while SLOs still fail. Measure **saturation and recovery time per component**, not just instance counts.

## 5. Example Architecture Combining All Three Principles

For the booking platform, a v1 architecture could be structured as follows:

~~~mermaid
flowchart TB
    U[Web / Mobile] --> EDGE[DNS / CDN / WAF]
    EDGE --> LB[HTTPS Load Balancer]
    subgraph R[Cloud Region]
        subgraph Z1[Availability Zone A]
            A1[Stateless Booking API A]
            W1[Notification Worker A]
        end
        subgraph Z2[Availability Zone B]
            A2[Stateless Booking API B]
            W2[Notification Worker B]
        end
        LB --> A1
        LB --> A2
        A1 --> D[(Managed Relational DB / HA)]
        A2 --> D
        A1 --> O[(Transactional Outbox)]
        A2 --> O
        O --> Q[(Managed Queue + DLQ)]
        Q --> W1
        Q --> W2
    end
    W1 --> P[Email / SMS provider]
    W2 --> P
    D -.-> B[(Backup / PITR)]
    OBS[Metrics / Logs / Traces] -.-> A1
    OBS -.-> A2
    OBS -.-> D
~~~

**Notes when reading the diagram:**

- This is a **logical model**; it does not yet depict subnets, routes, IAM, secrets, private endpoints, encryption, DNS failover, or per-component permissions.
- The outbox is typically a record/table inside the transactional database; a post-commit dispatcher reads the record and sends it to the queue. The arrow passing through the outbox represents this process, not that the API writes directly to the queue inside the database transaction.
- Labels **HA** and **Backup/PITR** indicate the requirement to select/configure appropriate capabilities; actual cloud service support must be verified. Redundancy across two zones does not protect against losing an entire region or losing data due to logical errors.
- APIs/workers should reside in private networks or have appropriately restricted ingress; public endpoints require TLS and authentication/authorization. Backups also require separate protection policies and access controls.

### 5.1. Expected Behavior by Event

| Event | Expected Business Behavior | Supporting Mechanism | Verification |
|---|---|---|---|
| An API instance dies | New requests route to healthy instances; in-flight requests can be safely retried | Statelessness, health checks, idempotency | Stop instance; measure 5xx, latency, duplicate bookings |
| A zone becomes unavailable | Essential flows continue or recover within SLO | Multi-AZ, standby capacity, DB/queue HA | Simulate zone failure and measure failover |
| Email provider fails for 20 minutes | Bookings still commit; notifications may be delayed | Queue, retry/backoff, DLQ | Disconnect provider, measure queue age, retries, and duplicate sends |
| New API release spikes 5xx | Halt rollout, limit affected users | Canary, metric gates, rollback | Controlled faulty release, measure detection/recovery time |
| Adding a booking data field | Old and new versions work together during transition | Expand-contract migration | Run two versions concurrently and test rollback |
| Traffic triples | Scale compute/workers, protect database and quotas | Autoscale, connection limits, admission control | Load/spike tests, record saturation and cost |
| Accidental booking deletion | Restore and reconcile per data loss tolerance policy | Backup/PITR, audit logs, runbook | Isolated restore, measure actual RTO/RPO |

### 5.2. Trade-Offs Must Be Explicitly Documented

Multi-zone design typically increases redundancy cost while reducing single-zone failure risk. Moving email to a queue removes synchronous dependency while requiring backlog and duplicate-processing management. Canary releases limit the blast radius of bad deployments while requiring traffic splitting and solid metrics. Read replicas increase read capacity while not guaranteeing immediate read-after-write visibility. Every decision must record **goal, alternatives, cost, residual risk, and evidence**.

An illustrative **Architecture Decision Record (ADR)**:

~~~text
ADR-012: Decouple notification sending from the booking creation request

Context:
- Booking creation API must respond within the agreed SLO.
- Email provider can be slow or temporarily unavailable.

Option A: Send email synchronously during booking.
Option B: Commit booking + outbox; queue and worker send email asynchronously.

Decision: B.
Benefits: Booking does not wait on email; workers can scale and retry independently.
Trade-offs: Notifications may be delayed; must manage backlog, duplicate messages, and DLQ.
Verification: Disconnect email provider for 20 minutes; bookings stay accurate;
              backlog alert fires; duplicates handled per policy.
Revisit when: Notification SLO, traffic volume, or cost changes.
~~~

## 6. Reviewing with Well-Architected Thinking

**Well-Architected** is a methodology for questioning architectural quality, identifying risks, and improving with evidence. Pillar groupings vary across providers. The table below uses the **six familiar AWS Well-Architected pillars** as a reference framework without requiring AWS services.

| Pillar | Questions for Failure, Change, and Growth | Expected Evidence |
|---|---|---|
| **Operational Excellence** | Are there runbooks, deployment pipelines, alerts, and post-incident improvements? | Dashboards, drills, rollback procedures, postmortems |
| **Security** | Do scaling/deployments expose secrets, widen permissions, or bypass controls? | IAM least privilege, network policies, encryption, CI/CD permissions |
| **Reliability** | Does it tolerate faults within committed scope and restore accurate data? | Fault injection, failover/restore tests, RTO/RPO, SLOs |
| **Performance Efficiency** | Which layer bottlenecks under load, and is it predicted and measured? | Load tests, profilers, capacity models, p95/p99, saturation |
| **Cost Optimization** | Do redundancy and autoscaling deliver the service level at a reasonable total cost? | Budgets, allocation tags, replica/egress/log costs, owner |
| **Sustainability** | Are idle resources minimized and resources utilized efficiently? | Safe scale-in, storage lifecycle, pruning redundant workloads |

Cross-pillar questions:

1. If an external provider fails for 20 minutes, which flows remain operational and what do users see?
2. If requests triple, can the database and quotas keep pace with compute?
3. If a new release fails, can we halt and recover before exhausting the error budget?
4. If yesterday's backup succeeded, is there evidence of **restoring accurate data**?
5. If we must keep double capacity for zone fault tolerance, how much does cost rise and does the business accept it?

Never evaluate an architecture by tool count. Enabling autoscaling when the DB is bottlenecked can still crash the system; having backups never tested for restore does not prove RTO/RPO compliance; having canary deployments without tracking business metrics can still ship undetected defects.

### 6.1. Risk Prioritization Matrix

To decide where to invest first, assess **likelihood**, **business impact**, **detectability**, and **recovery time**. There is no need for one universal risk score across all companies; use criteria agreed upon with product owners, security, and operations.

Example:

| Risk | Impact | Hypothetical Priority | First Remediation Step |
|---|---|---|---|
| Duplicate booking on retry | Corrupts core business state, impacts customers | Very High | Transaction + constraint + idempotency, concurrency tests |
| Unable to restore backup | Data loss or RTO/RPO breach | Very High | Isolated restore drill, data reconciliation |
| Email provider outage | Delayed notifications | Medium if delay is permitted | Queue + retry + DLQ + dedicated SLO |
| Insufficient API peak capacity | Lost transactions and degraded experience | High | Load test, capacity plan, admission control |
| Rollout without metrics/rollback | Widespread impact from faulty release | High | Canary gate, rollback runbook, compatibility checks |

Actual priority varies with damage severity, regulatory requirements, cost, and dependency criticality. The matrix is a starting point for discussion, not a substitute for organization-specific risk analysis.

## 7. Empirical Architecture Verification Plan

Reading diagrams and checking off checklists is not enough. Tests should map directly to SLOs and risks:

| Test | How to Test | Metrics / Evidence |
|---|---|---|
| **Load test** | Ramp up to design load with representative endpoint mix and dataset | p95/p99, error rate, throughput, CPU, DB pool, queue age, and cost |
| **Spike test** | Apply a sudden short-duration traffic surge | Autoscale lag, rate limits, successful requests, and post-spike recovery |
| **Soak test** | Sustain load over an extended period | Memory/connection leaks, tail latency, log/storage growth |
| **Instance/zone failure** | Terminate instances or simulate zone loss within a controlled scope | Failed requests, failover time, remaining capacity, booking correctness |
| **Dependency failure** | Inject latency or disconnect provider/cache/DB in a controlled way | Timeouts, retry budget, circuit breaker, fallback, and cascade behavior |
| **Duplicate/concurrency test** | Send identical requests/messages repeatedly, contend for one slot | Zero duplicate bookings, policy-compliant deduplication, audit trail |
| **Canary rollback** | Ship a controlled faulty release to a small cohort | Accurate detection, rollback/mitigation, schema/data remain compatible |
| **Backup restore** | Restore into an isolated environment and reconcile business data | Measured RTO/RPO, data integrity, complete permissions and runbooks |

For intentional fault testing, start in a safe environment, define blast radius and abort criteria, record a baseline, and only then execute. Test in production only with appropriate operational controls. After each test, update runbooks, monitoring, capacity models, and ADRs if initial assumptions no longer hold.

### 7.1. Signals That Require Re-Evaluating the Architecture

- p95/p99 climbs rapidly while requests/second have barely risen: possible pool contention, locking, or dependency bottleneck.
- API CPU is low while many requests time out: check DB connections, DNS/networking, and thread/async queues.
- API scales out continuously while throughput stays flat: the system may have hit a limit at the DB, queue, quota, or upstream layer.
- Queue depth drops while oldest message age remains high: a group of messages is stuck or consumers are failing and retrying.
- API rollback succeeds but data cannot be read: incompatible schema/data migration.
- Backups always succeed yet restores exceed RTO: DR plan and runbook must be revised.
- Alerts fire frequently yet on-call engineers do not know what action to take: replace alerts with impact-based ones linked to runbooks.

## 8. Hands-On Exercise: Designing to Survive a Growth Surge

**Scenario:** The booking platform currently runs on a single public VM hosting both the API and database. Emails are sent synchronously before returning the response. The service processes around 5,000 bookings/day. A new marketing campaign may increase lookup traffic by **5x within 15 minutes**. The team wants to release a cancellation feature with zero downtime and must prevent duplicate bookings when requests are retried. Per-instance p95 and throughput have not yet been measured.

Produce a v1 architectural proposal with the following deliverables:

1. **Measurable requirements:** propose SLIs/SLOs for lookup and booking; define separate RTO/RPO targets for at least two incident scenarios; explicitly list assumptions to verify.
2. **Failure map:** trace the request path, mark single points of failure, and describe expected behavior when the VM, DB, zone, or email provider fails.
3. **Correctness:** describe the transaction/constraint preventing double-booking, handling re-sent identical idempotency keys, and workers receiving duplicate messages.
4. **Change:** choose rolling/canary for releasing cancellations; describe one schema change using expand-contract, the parallel-running phase, and rollback conditions.
5. **Growth:** specify metrics for API/worker autoscaling, DB bottlenecks, core-request protection strategy, cost limits, and backlog control policy.
6. **Verification:** at least one load test, one dependency failure test, one canary rollback, and one restore test. Each test must specify pass criteria, metrics to record, and residual risks.

Without measured throughput per instance, **do not fabricate instance counts**. Use the capacity formula and a load test plan to determine input values before finalizing.

Sample decision table:

| Decision | Requirement | Choice and Trade-Offs | Evidence to Collect |
|---|---|---|---|
| Separate DB from API VM | No data loss when app instance fails | Managed DB increases baseline cost but reduces operational toil | Restore/failover, throughput, cost |
| Idempotent booking | No duplicate writes on repeated requests | Requires storing keys and data transactions/constraints | Concurrent request and replay tests |
| Notification queue | Booking does not wait on email | Notifications may be delayed; requires retry/DLQ | Backlog behavior, provider failure test |
| Canary + compatible schema | Safe cancellation release | Requires telemetry and schema transition phase | Dual-version run, rollback test |
| API autoscaling | Handle traffic spikes | Replicas increase DB load and cost | Load/spike tests, saturation, and cost |

**Completion criteria:** A reader of the proposal must be able to point out (a) how the system keeps functioning when each dependency fails; (b) how old and new versions coexist during release; (c) where the next growth bottleneck lies; (d) what evidence verifies each claim.

## 9. Design Memory Framework

- **Failure:** identify failure domains, prevent propagation, keep data accurate, and test real recovery.
- **Change:** clear responsibility boundaries, transition compatibility, progressive delivery, and a rollback path.
- **Growth:** measure real load, scale at the bottleneck layer, size capacity for faults, and control quotas, backlogs, and cost.
- **Trade-offs:** every decision must link to requirements, alternatives, residual risks, and validating measurements.

An architecture can start simple and evolve. The right level of redundancy, automation, and complexity depends on the business impact of failure, desired change velocity, actual scale, and the team's operational skills. Only the **measure → test → learn → adjust** loop turns a cloud diagram into a reliably operable system.
