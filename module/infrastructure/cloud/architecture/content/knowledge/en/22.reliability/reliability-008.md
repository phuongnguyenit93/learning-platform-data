# Fallback Paths, Degradation Modes, and Non-Critical Dependencies

A reliable cloud system does not merely avoid failures. It must also sustain critical functions when part of the infrastructure or a dependent service fails. A booking page can still show confirmed appointments even if the recommendation service fails; users can still view essential information when personalization temporarily stops; a transaction can be accepted into a durable queue when downstream processing is overloaded. These choices must be designed before incidents occur.

A **fallback path** is an alternative execution path activated when the preferred path cannot respond. **Graceful degradation** is how a system reduces partial quality or features while keeping core functionality intact. A **non-critical dependency** is a service whose failure should not halt the entire primary business workflow. Dependency classification must be based on actual impact per use case; the same service may be critical for one operation yet non-critical for another.

A good fallback needs bounds, activation conditions, timeouts, substitute data, observability, and a recovery path. Unbounded fallbacks or unclear semantics can produce wrong data, mask incidents, overload fallback systems, or turn local faults into cascading failures.

This lesson belongs to the **Reliability** section of the cloud architecture track. The focus is designing fallback paths, degradation modes, and dependency boundaries to balance reliability, performance, security, scalability, cost, and operations under Well-Architected principles.

After this lesson, you will be able to:

- Classify dependencies by criticality and business impact.
- Design fallbacks for caches, external services, search, recommendations, and asynchronous tasks.
- Apply graceful degradation, timeouts, retries, circuit breakers, bulkheads, and load shedding.
- Determine when to use stale data, default responses, queues, or read replicas.
- Design safe fallbacks for write operations and avoid false success confirmations.
- Test failure paths, recovery paths, and ensure fallbacks do not trigger cascading failures.
- Measure SLOs, fallback rates, dependency health, and evaluate operational risk.

## 1. Why Are Fallback Paths Needed?

A request can traverse many components: API gateway, authentication, database, cache, search, recommendations, payment provider, and notifications. If every component is called synchronously and one failure fails the entire request, overall flow reliability can fall below any single component's reliability.

For example, an appointment detail page needs the Booking Service for the schedule, Customer Service for the display name, Recommendation Service for cross-service suggestions, and Analytics Service to record page views. Bookings and access permissions are core. Recommendations and analytics can usually run later or pause temporarily. If the page refuses to render simply because analytics timed out, the architecture let a secondary dependency dictate core business availability.

~~~mermaid
flowchart TD
    U["Client request"] --> API["Application API"]
    API --> CORE["Core booking data"]
    API --> REC["Recommendation"]
    API --> ANA["Analytics event"]
    CORE --> R["Response"]
    REC --> R
    ANA --> R
    R --> U
~~~

If the API waits on all three branches before responding, latency and failures in secondary branches degrade the whole request. Determine which branches are mandatory synchronous calls, which run asynchronously, and which have substitute options.

### Reliability Does Not Mean Every Feature Works All the Time

Users primarily care about business outcomes: viewing appointments, booking slots, knowing whether payments succeeded. They can accept temporarily missing suggestions, avatars, or secondary dashboards if core functions keep working accurately.

The goal of graceful degradation is protecting primary value during incidents, not keeping every feature intact at any cost. Degradation modes must be explicitly defined so users never misinterpret data or state.

## 2. Classifying Dependencies by Use Case

Never label a service as universally critical or non-critical across the entire system. Evaluate each dependency within a specific execution path.

| Level | Meaning | Example in a booking app | Handling on failure |
| --- | --- | --- | --- |
| **Required for correctness** | Cannot safely complete business logic without the result | Auth checks, slot check/hold, payment status when confirming booking | Fail closed, bounded retries, or transition to pending state |
| **Required by policy** | Must satisfy security/regulatory rules before proceeding | Sensitive record access checks, transaction limit verification | Reject or wait; never bypass policy to raise availability |
| **Important with fallback option** | Can continue using substitute data or methods within limits | Cache/read replica, approved backup auth provider | Conditional fallback with explicit freshness |
| **Non-critical for current request** | Failure must never block the core workflow | Recommendations, analytics tracking, post-commit email notifications | Skip temporarily, queue, or process in background |

### Questions for Classification

1. If the dependency does not respond, could it produce wrong results or violate business rules?
2. Is there a verified substitute, or only a guess?
3. How stale can substitute data be before it becomes unsafe?
4. Are there legal, security, or authorization checks that must run?
5. Can the function be deferred without hurting the business?
6. When fallback activates, who knows and monitors it?

### Technical Dependencies vs. Business Dependencies

An application has technical dependencies on DNS, secret managers, databases, identity providers, and message brokers. A business dependency owns decisions or capabilities in another domain, such as a payment provider or pricing engine.

Not every technical failure can be fallen back in application code. If identity cannot be verified, the application must never assume the caller is valid. If database secrets cannot be fetched, never hardcode fallback credentials. Fallbacks must preserve security boundaries.

## 3. Defining Core Functions and Permissible Degradation

Before designing fallbacks, specify the minimum experience the system must uphold during each incident.

| Use case | Normal | When secondary dependency fails | Non-negotiable invariant |
| --- | --- | --- | --- |
| View appointment | Schedule details, profile, and suggestions | Hide suggestions; show minimal saved name | Never expose another user's schedule |
| Search doctors | Fresh results and rankings | Use latest directory/cache or basic search | Never show slots known to be taken |
| Create booking | Revalidate slot and persist transaction | Accept pending request if contract permits | Never confirm booking without holding a slot |
| Send confirmation email | Send after booking commit | Queue and retry later | Never lose booking state; never send false success notices |
| Analytics dashboard | Fresh metrics | Show last-updated timestamp | Never present stale data as real-time status |

### Service Degradation Budgets

You can define a degradation budget: which features may be turned off, for what maximum duration, what percentage of requests may be affected, and maximum data staleness. For example, recommendations may be disabled for 30 minutes; booking status must never be stale past business limits; analytics may lag 15 minutes.

These are hypothetical targets requiring domain owner confirmation. Do not apply identical thresholds across all data types or customers.

## 4. Common Fallback Strategies

| Strategy | How it works | Fits best for | Risks to control |
| --- | --- | --- | --- |
| Static/default response | Return pre-approved default config or content | Banners, suggestions, non-transactional content | Wrong, outdated, or tenant-mismatched defaults |
| Cached/stale response | Return cached copy within stale bounds | Catalogs, profiles, dashboards | Stale data, revoked permissions, cache poisoning |
| Alternate provider/path | Call backup provider or route | DNS, officially supported backup identity/payment paths | Differing provider semantics, split-brain |
| Read replica/read model | Read from replica or projection | Read-only queries tolerating lag | Stale reads, failover, or unknown lag |
| Queue/defer | Persist work durably to process later | Notifications, analytics, exports, long tasks | Backlogs, retention, duplicates, full queues |
| Reduced feature set | Disable secondary pieces, keep core | Recommendations, personalization, previews | Users need clarity that feature is temporarily unavailable |
| Load shedding | Reject early or shed load under control | Overload, protecting core dependencies | Tenant fairness and retry storms |
| Fail fast | Stop request when unable to process accurately | Authorization, strongly consistent transactions | UX needs clear error states and safe retry paths |

A single system can combine strategies: cache-aside for catalogs, queues for emails, disabling recommendations on failure, and failing fast on ambiguous payment states.

## 5. Default Responses and Cached/Stale Data

The simplest fallback returns a substitute value. Yet not all data can be replaced with defaults.

### Default Responses

Defaults must be approved by domain owners, contain no personal or speculative data, carry clear semantics, and never mislead users into thinking an action completed. Defaults should be safely configurable.

For instance, when recommendations fail, returning an empty list with a `recommendations unavailable` status makes sense. Returning a guessed list of open booking slots does not.

### Stale-While-Revalidate

Applications can serve cached data that is stale yet within allowed bounds while refreshing in the background. Distinguish:

- **Fresh TTL:** data is considered fresh.
- **Stale window:** stale data may be served temporarily.
- **Hard expiry:** beyond this threshold, data must not be used.

~~~text
if age <= fresh_ttl:
    return cached_value
elif age <= hard_expiry:
    return cached_value_with_stale_flag
    trigger_refresh_in_background()
else:
    load_from_source_or_return_unavailable()
~~~

Stale bounds must be set by the business. Service catalogs may tolerate a few minutes; permissions, balances, or booking states must never rely on stale caches during commits.

### Read Replicas as Fallbacks

Read replicas can help when the primary writer is busy or a read query does not need read-after-write. Still, check replication lag and identify which queries tolerate staleness. Never route queries requiring latest state to a replica without an explicit consistency contract.

### Fallbacks Must Never Bypass Authorization

If the primary auth service is down, use cached authorization decisions only when policy allows, with short lifetimes and sufficiently fresh data. When permissions are revoked, stale caches can permit unauthorized access. Sensitive operations must fail closed even at the expense of availability.

## 6. Timeouts, Retries, and Fallback Time Bounds

Fallbacks help only if slow dependencies are detected early enough. Never wait the entire request deadline before switching paths.

### Timeout Budgets

Suppose an API has a 2-second deadline:

~~~text
Total request budget: 2000 ms
  Authentication:          150 ms
  Core database:            700 ms
  Optional recommendation:  250 ms
  Response/serialization:   150 ms
  Safety margin:            250 ms
  Unallocated reserve:      500 ms
~~~

These numbers are illustrative only. Allocate dependency timeouts from SLOs and remaining time. If recommendations do not respond within 250 ms, the API drops that branch and returns core results. Never wait 2 seconds before degrading.

### Selective Retries

Apply retries only to recoverable failures and idempotent operations. Retrying ambiguous write requests can create duplicate side effects. Use exponential backoff, jitter, max attempts, and overall deadlines.

Never retry clear authentication/authorization failures, unrecoverable validation/business-rule errors, non-idempotent requests lacking safeguards, or dependencies once the request deadline has passed.

### Retry Budgets

Cap the ratio of retried requests over a window or retries per request. During a dependency outage, curbing retries protects resources and avoids request storms.

## 7. Circuit Breakers, Bulkheads, and Load Shedding

These three patterns protect against dependency failures while solving distinct problems.

### Circuit Breakers

A circuit breaker tracks dependency errors or latency. When thresholds breach, it **opens** and rejects dependency calls for a period; then enters **half-open** to test a few probes; if healthy, it transitions back to **closed**.

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Error/latency threshold exceeded
    OPEN --> HALF_OPEN: Cooldown elapsed
    HALF_OPEN --> CLOSED: Probe succeeds
    HALF_OPEN --> OPEN: Probe fails
~~~

When open, callers must take explicit action: serve cache, skip secondary features, enqueue if appropriate, or fail fast. Circuit breakers neither pick fallbacks automatically nor repair dependencies.

With multiple application instances, local breakers may open on one instance before another. That is often reasonable to avoid a global state store, provided you understand the scope and total probe volume. Never assume local breakers synchronize cluster-wide.

### Bulkheads

Bulkheads isolate resources so one failing dependency cannot consume all threads, connections, or workers. For example, recommendations get a dedicated pool of 20 concurrent slots; core databases get their own pool. A hung recommendation service cannot starve booking connections.

### Load Shedding

When approaching overload, reject lower-priority requests or features early to protect remaining capacity. Prioritize core transactions, enforce tenant quotas, pause exports, or drop recommendations.

Load shedding requires business-impact priority tiers, per-tenant/operation quotas and rate limits, retry guidance in responses, and metrics on shed requests. Prevent clients from retrying immediately and adding load.

## 8. Non-Critical Dependencies and Asynchronous Processing

An effective way to reduce coupling is moving work that does not need immediate results off the critical path.

For example, when a booking is confirmed:

1. Booking Service commits booking state and an outbox event in the same transaction.
2. Relay publishes `BookingConfirmed` to the broker.
3. Notification worker consumes the event and sends the email.
4. Analytics consumer updates metrics.
5. If the email provider fails, the worker retries per policy and may route to a DLQ.

~~~mermaid
flowchart TD
    API["Create booking request"] --> CORE["Core booking transaction"]
    CORE --> DB[("Booking DB")]
    CORE --> OUT[("Transactional outbox")]
    OUT --> RELAY["Outbox relay"]
    RELAY --> Q[("Durable event queue")]
    Q --> N["Notification worker"]
    Q --> A["Analytics consumer"]
    N --> EP["Email/SMS provider"]
    N --> DLQ[("Dead-letter queue")]
~~~

Once the booking is persisted, emails can lag without losing the booking. However, client responses must state accurate status: booking confirmed, notification pending or unsent; never claim the email was delivered when it was only enqueued.

### Queues Are Not Infinite Error Sinks

Queues have finite retention, storage, and throughput. When consumers fall behind, monitor depth and oldest message age, throttle producers or apply backpressure, tune consumer concurrency to downstream capacity, define retry counts and DLQs, and maintain poison-message/replay runbooks. If a queue is full or cannot persist durably, return an ingestion error rather than faking acceptance.

### Accepted vs. Completed

HTTP 202 indicates a request was accepted for asynchronous processing, yet APIs must provide an operation ID/status endpoint or callback. 202 does not mean completion. For financial, booking, or side-effecting operations, document these semantics explicitly.

## 9. Fallbacks for Data Writes and Transactions

Read fallbacks are generally simpler than write fallbacks. Reading catalogs can return stale caches. Writing bookings or payments with ambiguous outcomes risks duplicate transactions or data corruption.

Write-path principles:

- Confirm success only after the source of truth commits or a contractually defined durable acceptance mechanism succeeds.
- Use idempotency keys for retries of the same intent.
- Persist operation state and correlation IDs to resolve ambiguous outcomes.
- For long workflows, return pending status and provide a status-check mechanism.
- Never switch to another provider/route and re-execute a write without confirming the first provider did not process it.

### Payment Timeout Example

The payment provider times out after receiving a charge request. The system does not know whether the charge succeeded. Safe fallback:

1. Mark the payment `UNKNOWN` or `PENDING_RECONCILIATION`.
2. Preserve the same provider idempotency key and operation reference.
3. Query transaction status by reference.
4. If captured, save the outcome and proceed with booking.
5. If definitively not captured, retry per provider contract.
6. If indeterminable, escalate to reconciliation/manual review.

Never call a second provider with a new key simply because the first provider was slow. That risks double-charging the customer.

### Falling Back to a Replica or Region

If the primary writer is unavailable, fail over writes only with fencing to guarantee a single active writer, known commit state, and acceptable RPO. Otherwise, pause writes or accept requests into a durable queue as pending, never pretending transactions committed.

## 10. Dependency Graphs and Cascading Failures

A request can depend indirectly across many tiers. API calls service A; A calls B and C; C calls D. If D slows down, C's connections and workers stay held; C slowing causes A to hold resources; finally the API times out and sparks new retries. A tiny initial fault spreads widely.

~~~mermaid
flowchart TD
    CLIENT["Clients / retries"] --> API["API service"]
    API --> A["Core service"]
    API --> OPT["Optional service"]
    A --> DB["Database"]
    A --> C["Internal dependency"]
    C --> D["External provider"]
    D -. "Latency / failure" .-> C
    C -. "Resource exhaustion" .-> A
    A -. "Queue/thread saturation" .-> API
    API -. "Retry amplification" .-> CLIENT
~~~

Defense layers include timeouts at every network boundary, retry budgets and backoff/jitter, circuit breakers, bulkheads isolating pools/threads/queues, concurrency/rate limits, business-prioritized load shedding, caches/defaults for stale-tolerant reads, queues/outboxes for non-synchronous side effects, and bounded capacity headroom.

Autoscaling is not an infinite fallback. If every new instance opens extra connections to an already overloaded database, scaling out the application can worsen the outage.

## 11. Multi-Provider and Independent Fallback Paths

Some capabilities support backup providers: DNS, email/SMS, object storage, identity, payments, or regions. Yet two providers are not drop-in substitutes by default.

Before using an alternate provider, verify compatible API/status/error mapping, ready credentials/quotas/billing, residency/compliance approval, cross-provider idempotency, routing/failback protections against dual execution, business-reflective health checks, and tested failback procedures.

### Active-Passive vs. Active-Active

- **Active-passive:** primary provider handles traffic; secondary receives traffic only on failover. Easier ownership, yet requires verifying secondary readiness and quotas.
- **Active-active:** both providers handle traffic concurrently or split load. Increases capacity and resilience but requires conflict handling, idempotency, and reconciliation.

For payments or identity, active-active can be complex because each provider holds separate state, fraud policies, and transaction references. Do not deploy it merely to inflate uptime on paper.

## 12. Health Checks and Fallback Activation Decisions

Health checks must reflect the ability to execute required operations. An HTTP 200 from a root endpoint does not prove database queries, permissions, or downstream workflows work.

- **Liveness:** process is alive and able to keep running.
- **Readiness:** instance can handle current traffic types.
- **Dependency health:** status of specific databases, brokers, providers, or features.

Do not fold every optional dependency into service-wide readiness. If recommendations fail while booking works, marking the whole API not-ready needlessly hurts availability.

Fallbacks can trigger from timeouts/error rates/latency breaching thresholds, open circuit breakers, exhausted provider quotas, operator kill switches, maintenance windows, or health policies detecting invalid responses. Thresholds need windows and hysteresis to prevent flapping. Include cooldowns, bounded probes, and gradual recovery.

### Kill Switches and Feature Flags

Feature flags can disable non-critical parts rapidly. Gate changes with access control and audits; ensure configs have safe defaults; separate operational flags from product flags; assign owners and expirations to emergency flags. Never use flags to bypass security or business invariants.

## 13. Observability for Graceful Degradation

When fallbacks activate, the system may continue returning 200 responses while quality degrades. Tracking only HTTP availability can leave operators unaware a feature has been disabled for hours.

| Metric | Purpose |
| --- | --- |
| Fallback invocation count/rate | Know how often fallbacks run |
| Fallback reason | Timeout, breaker open, quota, cache miss, or operator switch |
| Stale response age | Measure age of returned data |
| Optional feature availability | Track each non-critical feature individually |
| Dependency latency/errors | Spot issues before fallbacks spike |
| Queue depth/oldest age | Monitor delayed work |
| Retry/circuit state | Catch retry storms or breaker flapping |
| Shed/throttle count | Measure rejected load |
| Recovery time | Measure time to return to normal mode |
| Business outcomes | Bookings/payments succeeded, canceled, or pending |

Attach `degraded_mode`, `fallback_reason`, dependency name, correlation ID, and operation ID to logs/traces. Never log sensitive payloads or credentials. Traces should show which branch was skipped, which substitute branch ran, and how much time was saved.

### Experience-Based Alerts

Alert when fallback rates breach thresholds or persist too long, stale ages exceed bounds, queue backlogs/oldest ages breach SLOs, core transactions fail, dependencies recover while breakers remain open, or fallback providers underperform required success rates.

Do not alert only on services going down; alert on user and business impact.

## 14. Testing Failure Paths and Recovery Paths

Fallbacks must be tested as rigorously as primary paths. Unit tests on default branches alone are insufficient.

Test categories:

1. **Dependency timeout:** simulate unresponsive dependency; does the API degrade within deadline?
2. **Dependency 5xx/429:** do retries/backoff and breakers behave properly?
3. **Cache unavailable:** can the backing data source survive fallback QPS?
4. **Stale data:** is data past stale bounds rejected; is sensitive data withheld properly?
5. **Queue full/backlog:** do producers avoid false accepts or unbounded queuing?
6. **Provider failover:** does the backup route have valid credentials, quotas, and semantics?
7. **Partial response:** do clients understand which features are unavailable and which data is stale?
8. **Concurrent requests:** do simultaneous requests triggering fallback cause stampedes or duplicates?
9. **Recovery:** when dependencies recover, do traffic ramps, probes, and breaker closures behave safely?
10. **Kill switches:** can operators toggle features safely with audit trails?

### Fault Injection and Chaos Engineering

In test environments, intentionally inject latency, packet loss, connection resets, HTTP 500s, quota exhaustion, or broker slowdowns. Measure both normal and degraded modes. Keep scope bounded so production is never impacted outside approved plans.

Chaos experiments test measurable hypotheses, such as "Recommendation Service failure does not push Booking API p95 past 500 ms." Every experiment needs a hypothesis, blast radius, safe abort conditions, observed metrics, owner, expected outcomes, and recovery procedures.

## 15. Design Example: Booking Page Working When Recommendations and Notifications Fail

**Hypothetical Context:** A booking app uses Booking Service, Customer Profile, Recommendation, Email Provider, and Analytics. Bookings live in a relational database. Recommendations can time out during peak hours; the email provider suffers occasional outages; analytics has no real-time requirement. The appointment page SLO is p95 under 500 ms and 99.9% availability. These are practice targets.

### Dependency Classification

| Dependency | Role | Criticality for appointment page |
| --- | --- | --- |
| Authentication/authorization | Verify user and schedule access | Mandatory |
| Booking database/service | Read accurate bookings | Mandatory |
| Customer profile | Display name, optional fields | Can use minimal saved snapshot if policy permits |
| Recommendation | Service suggestions | Non-critical |
| Email provider | Post-commit notifications | Non-critical for booking response; background processing |
| Analytics | Record page view events | Non-critical |

### Execution Path

1. Authenticate user and check authorization.
2. Read booking from source of truth or appropriately consistent read model.
3. Call profile with a short timeout; if unavailable, use saved display name if still valid.
4. Call recommendations with a tight deadline; on failure, return empty suggestions with a degraded flag.
5. Emit analytics event asynchronously; if broker/queue rejects, apply log/buffer or drop policy per importance.
6. Emit email after booking commit via outbox; worker handles retries and DLQ.

~~~mermaid
flowchart TD
    U["User"] --> API["Booking page API"]
    API --> AUTH["Auth / authorization"]
    API --> BOOK["Booking source of truth"]
    API --> PROF["Profile with short timeout"]
    API --> REC["Recommendation with circuit breaker"]
    PROF --> RESP["Compose response"]
    REC --> RESP
    REC -. "Failure: omit suggestions" .-> RESP
    RESP --> U
    BOOK --> OUT["Outbox"]
    OUT --> Q[("Queue")]
    Q --> EMAIL["Email worker"]
    Q --> ANA["Analytics consumer"]
~~~

### Failure Behavior

- If Booking Service is unreachable and no sufficiently fresh read replica exists, never show guessed schedules; return unavailable or clear retry status.
- If Recommendation fails, do not block the page; omit suggestions.
- If Email fails after commit, the booking retains its accurate status; pending notifications are tracked and retried.
- If Analytics fails, never inflate page latency; drop non-critical events per policy or use a durable queue if events must be kept.
- If authorization fails, fail closed for private data.

### Acceptance Criteria

- Recommendation timeouts never push page p95 past target deadline.
- Bookings still load accurately without cross-user leakage when profile fails.
- Email retries never send uncontrolled duplicates; operations carry IDs and idempotency.
- Degraded responses emit clear metrics and traces.
- Queue backlogs and DLQs trigger alerts.
- When dependencies recover, traffic reopens under control.

## 16. Hands-On Exercise: Designing Degradation Modes for an E-Commerce Platform

**Scenario:** A retail platform has Catalog, Inventory, Pricing, Recommendation, Payment, Notification, and Analytics. Catalog and Inventory have caches; Pricing requires promo rules; Payment calls an external provider. Users must browse products, add to cart, place orders, and pay. Recommendations, review summaries, and analytics can lag. This is a simulated scenario.

### Tasks

1. **Map the dependency graph:** identify sync/async paths, criticality per use case, and failure impact.
2. **Define degradation modes:** for each failing dependency, specify fallback, stale bounds, default response, fail-fast, or queue.
3. **Allocate timeout budgets:** set deadlines for APIs, dependencies, and safety margins; define retry budgets.
4. **Design protections:** circuit breakers, bulkheads, concurrency limits, load shedding, and kill switches.
5. **Design write paths:** handle payment timeouts, inventory uncertainty, full queues, and ambiguous outcomes via idempotency/reconciliation.
6. **Design observability:** fallback rates, stale ages, queue backlogs, breaker states, shed counts, and business outcomes.
7. **Design recovery:** probes, gradual ramp-up, replays, DLQs, and exiting degraded mode.

### Scenario Matrix

| Failing dependency | Options to evaluate | What never to do |
| --- | --- | --- |
| Recommendation | Hide suggestions/default list | Block the product page |
| Review aggregation | Show timestamped rating snapshot or hide ratings | Display stale figures as live data |
| Catalog cache | Bounded origin fallback or cached stale within bounds | Forward unbounded traffic straight to DB |
| Inventory source | Return unavailable/pending or revalidate later | Confirm stock when unknown |
| Pricing | Use versioned rule snapshot if policy permits; else fail closed | Guess prices/promotions |
| Payment provider | Unknown state; query/reconcile with same idempotency key | Charge another provider with a new key |
| Notification | Outbox/queue retries and DLQ | Roll back order just because email failed |
| Analytics | Async events or audited policy-based drops | Hold checkout waiting on analytics |

### Testing

- Inject timeouts per dependency and measure use-case p95/p99.
- Simulate cache outages to verify databases do not stampede.
- Slow down queue consumers and observe backlog/backpressure.
- Time out payment provider after charge acceptance; verify zero duplicate charges.
- Break pricing service; verify wrong prices are never applied.
- Toggle circuit breakers and kill switches; verify audit logs.
- Recover dependencies, ramp traffic, and ensure fallbacks do not stay stuck on.

### Deliverables

- Dependency graph and criticality matrix.
- Degradation contract per use case.
- Timeout/retry budgets and circuit/bulkhead policies.
- Fallback designs for read/write/async paths.
- Dashboards, alerts, runbooks, and recovery procedures.
- Fault injection/chaos test report and ADR.

## 17. Well-Architected Review

| Pillar | Questions for fallbacks and degradation modes |
| --- | --- |
| **Operational Excellence** | Are there dependency inventories, runbooks, kill switches, owners, degraded dashboards, and recovery procedures? |
| **Security** | Do fallbacks preserve authorization, tenant isolation, data classification, keys, and policies? |
| **Reliability** | Are optional failures isolated? Have timeouts, retries, circuits, bulkheads, queues, and recovery been tested? |
| **Performance Efficiency** | Do fallbacks have short deadlines, bounded fan-out, and avoid new bottlenecks? |
| **Cost Optimization** | Are redundant multi-providers/standbys/queues and runaway autoscaling avoided? |
| **Sustainability** | Are retry storms, constant polling, wasteful refreshes, and endless degraded resource holds avoided? |

## 18. Common Mistakes

**Treating every dependency as critical.** A recommendation or analytics service can drag down availability if placed unnecessarily on the critical path.

**Falling back to unbounded stale data.** Stale data drives bad decisions; always define fresh TTLs, stale bounds, and hard expiries.

**Bypassing authorization during dependency failures.** Never use fallbacks to expose data disallowed by policy.

**Waiting until the full request timeout before falling back.** Useful response time is gone; branch timeouts must be smaller than the overall deadline.

**Infinite retries.** Retry storms keep both dependencies and your own system overloaded.

**Circuit breaker opens without substitute behavior.** Callers still fail or receive unclear errors.

**Using local caches as durable write buffers.** Process/node loss loses uncommitted data.

**Switching payments to another provider after timeout without querying.** Risks double transactions.

**Disabling a feature with no metric.** Degraded mode can linger unnoticed.

**Auto-failing back immediately when a dependency recovers.** Traffic spikes can knock it down again; use probes and gradual ramps.

**Queuing everything without retention/backpressure.** Backlogs grow endlessly, blowing past cost and latency limits.

**Health-checking optional dependencies into service-wide readiness.** A secondary feature outage should not pull the core service out of load balancers.

## 19. Pre-Production Checklist for Degradation Modes

- [ ] Use-case dependency graphs exist with assigned owners.
- [ ] Criticality separates correctness/security dependencies from optional features.
- [ ] Degraded behavior and reduced features are clearly documented in API/UI contracts.
- [ ] Every fallback defines triggers, timeouts, stale bounds, hard expiry, and stop conditions.
- [ ] Authorization and business invariants hold across every fallback.
- [ ] Read fallbacks never present stale data as live state.
- [ ] Write fallbacks enforce idempotency, operation states, and reconciliation.
- [ ] Optional side effects move off the critical path via outboxes/queues where appropriate.
- [ ] Queues enforce durable acceptance, retention, backpressure, retries, and DLQs.
- [ ] Timeout budgets, retry budgets, circuit breakers, bulkheads, and load shedding are configured.
- [ ] Alternate providers have verified semantics, quotas, credentials, routing, and failback.
- [ ] Health checks do not needlessly fold optional dependencies into readiness.
- [ ] Kill switches/feature flags enforce access control, audits, owners, and expirations.
- [ ] Metrics/logs/traces track fallback reasons, stale ages, queue ages, and business outcomes.
- [ ] Fault injection, concurrency, provider timeout, and recovery tests exist.
- [ ] Gradual recovery, failback, and pending/unknown handling have been rehearsed.
- [ ] Costs for fallbacks, standbys, queues, caches, and headroom are budgeted.

Fallback paths and graceful degradation let systems preserve core business value when dependencies fail. Achieving this requires classifying dependencies per use case, identifying what is mandatory for correctness or security, and choosing fallbacks with clear semantics. Stale caches, default responses, queues, alternate providers, and fail-fast each have their place; all require timeouts, bounds, idempotency, observability, and matching recovery procedures. A trustworthy system is not one that hides every failure, but one that degrades under control, produces no corrupt results, and knows how to return to normal operation.
