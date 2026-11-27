# End-to-End Availability Analysis Across Dependency Chains

> **Chapter:** Reliability  
> **Scope:** Designing cloud application architectures from business requirements through networking, compute, data, and deployment models. This lesson focuses on evaluating availability across a business journey spanning multiple components and providers, identifying common-cause failures, quantifying dependency impacts, and verifying SLO, RTO, and RPO targets with Well-Architected thinking.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish availability of a component, a service, and an end-to-end business journey.
2. Model dependency graphs to identify mandatory, optional, sequential, parallel, redundant, and common-cause failure components.
3. Estimate dependency-chain availability using appropriate probabilistic models and recognize limits of independence assumptions.
4. Evaluate how timeouts, retries, queues, caches, fallbacks, circuit breakers, and graceful degradation affect actual availability.
5. Define SLIs/SLOs by user journey; distinguish availability, latency, correctness, freshness, RTO, and RPO.
6. Design fault tests, recovery drills, and operational evidence to validate end-to-end availability commitments.

## 1. What Is End-to-End Availability?

A service may have multiple replicas, a multi-AZ database, and redundant load balancers yet still leave users unable to complete transactions. The reason is that a business journey typically traverses many components: DNS, CDN/WAF, gateways, compute, identity providers, databases, brokers, payment providers, and external systems.

**End-to-end availability** describes the ability for users to complete a business action under defined conditions over a measurement period. It encompasses every dependency needed for that action to succeed, along with how the system handles failures and degradation.

For example, in a booking journey:

1. User opens the app and authenticates.
2. Searches services and views available schedules.
3. Creates a booking and reserves inventory.
4. Pays through an external provider.
5. Receives confirmation and notifications.

If the notification provider goes down while the booking is recorded accurately and the user can view status inside the app, the booking journey can still count as successful. Conversely, if the payment provider cannot confirm whether funds were captured, the system must never declare the booking complete just to avoid showing an error.

Therefore, **business success** must be defined before calculating availability. A page returning HTTP 200 does not guarantee a valid booking was created; a healthy API does not guarantee the entire journey finished.

## 2. Building Dependency Graphs by Business Journey

### 2.1. Start from User Actions

Choose a measurably meaningful action, such as:

- Successful login.
- Searching products within target latency.
- Completing checkout with a deterministic transaction state.
- Delivering scheduled reports on time.
- Restoring data read/write capability after an incident.

Then map the components genuinely required for that action to succeed. Separate clearly:

- **Hard dependency:** without it, the action cannot validly succeed.
- **Soft/optional dependency:** without it, auxiliary functions can degrade temporarily without breaking the core objective.
- **Alternative dependency:** one or more valid substitute paths exist.
- **Shared dependency:** serves multiple flows and can create a wide blast radius.
- **Hidden dependency:** DNS, certificates, secret managers, identity, control planes, quotas, or operational systems often overlooked.

### 2.2. Dependency Graph Example

~~~mermaid
flowchart TD
    U["User"] --> DNS["DNS / edge / WAF"]
    DNS --> GW["API gateway"]
    GW --> AUTH["Identity provider"]
    GW --> BOOK["Booking service"]
    BOOK --> INV["Inventory service"]
    BOOK --> DB[("Booking DB")]
    BOOK --> PAY["Payment provider"]
    BOOK --> OUT["Transactional outbox"]
    OUT --> BR["Message broker"]
    BR --> NOTI["Notification service"]
    NOTI --> EMAIL["Email/SMS provider"]
    BOOK --> OBS["Logs / metrics / tracing"]
    AUTH --> OBS
    PAY --> OBS
~~~

This diagram is only a starting point. If a user already holds a valid session, the identity provider might not be called on every request. If notifications are asynchronous, email/SMS sits off the checkout critical path. Classify dependencies by **actual execution path and system state**, not merely by edges shown on a diagram.

### 2.3. Dependency Matrix

| Component | Role in journey | Mandatory to record booking? | Behavior on failure |
| --- | --- | --- | --- |
| DNS/edge/gateway | Receive requests | Yes | Health routing/failover if configured |
| Identity provider | Authenticate or issue tokens | Depends on session state and policy | Cache tokens/sessions within valid limits; never skip auth |
| Booking service | Enforce booking rules | Yes | Other replicas/zones, safe rollback |
| Inventory | Hold slots, prevent overselling | Yes in this model | Reservation policy or controlled rejection |
| Booking database | Persist state and transaction invariants | Yes | HA/restore per RTO/RPO |
| Payment provider | Confirm payment per contract | Yes for prepaid bookings | Pending/unknown and reconciliation; never assume failure |
| Broker/outbox relay | Emit event notifications after commit | Not necessarily for initial HTTP response | Outbox retains events, retries, and DLQ |
| Email/SMS provider | Send notifications | No | Show booking in app, resend later |
| Observability | Diagnostics, alerting | Not a runtime dependency per request | Buffer/alternate telemetry; never let trace loss halt business |

This table depends on business policy. If legal/contract rules require sending an SMS OTP before confirming, the SMS provider becomes a hard dependency for that verification step.

## 3. Series Chains and Parallel Components

### 3.1. Series Chains

Along a path where every component must work, assuming independent failures and component availabilities \(A_i\), chain availability is:

\[
A_{\text{series}}=\prod_{i=1}^{n} A_i
\]

Suppose a request traverses four sequential components, each with 99.9% availability over the same period and measurement scope:

\[
A_{\text{series}}=0.999^4 \approx 0.996006
\]

That is roughly 99.60%. Each individual component appears highly available, yet the chain can be noticeably lower.

This is a **modeling estimate**, not a real-world guarantee. The formula assumes independent failure events, identical time definitions across availabilities, and no recovery/timeout behavior altering results. In reality, shared networks, regions, identity, quotas, or misconfigurations can fail multiple components together.

### 3.2. Parallel Redundancy

Given two independent instances, each with full capacity and a load balancer shifting requests to the surviving one, layer availability can be estimated as:

\[
A_{\text{parallel}}=1-(1-A_1)(1-A_2)
\]

If each instance has 99% availability:

\[
A_{\text{parallel}}=1-(0.01 \times 0.01)=0.9999
\]

The theoretical result is 99.99%, holding only if instance failures are independent and detection/traffic shifting act fast enough. If both instances share a zone, a broken image, or a dead database, redundancy does not survive the shared fault.

### 3.3. Multiple Redundant Layers Do Not Automatically Stack

For instance, two API replicas both relying on a single primary database with no failover. API availability may be high while the database caps the entire journey. Putting two load balancers in front also adds zero availability if both share a misconfigured DNS zone or expired certificate.

Diagram all of:
- Redundant components.
- Shared dependencies and common-cause failures.
- Control planes required to trigger/orchestrate failover.
- Data paths and state preserved during cross-region shifts.
- Time to detect, decide, and execute recovery.

## 4. Common-Cause Failures and Blast Radius

A **common-cause failure** happens when a single shared root cause disables or degrades multiple redundant components at once. This is why multiplying independent availabilities tends to be optimistic.

Examples:
- Two replicas across two AZs sharing a revoked IAM policy.
- Multiple services depending on the same DNS resolver or identity provider.
- Two database nodes hitting a fault in a shared storage/control plane.
- A deployment pipeline pushing bad config simultaneously to all regions.
- A cloud account hitting quota limits or getting suspended.
- A shared certificate, secret, or KMS key expiring/becoming inaccessible.

### 4.1. Common-Cause Layers to Review

| Scope | Common-cause examples | Controls |
| --- | --- | --- |
| Region/AZ | Power, network fabric, or regional service outage | Distribute failure domains, tested DR |
| Identity/IAM | Shared broken policy, IdP/KMS unavailable | Controlled break-glass, policy testing, rotation plans |
| DNS/certificates | Misconfigured zone, registrar/issuer, expiry | DNS monitoring, automated renewal, alternate access |
| Deployments | Broken image/config rolled out across all replicas | Canaries, staged rollouts, rollbacks |
| Data | Corrupted schema, bad migration, broken replication | Immutable backups, PITR, safe migrations |
| Control plane | Cluster/API/quota or orchestrator unavailable | Valid manual runbooks, control-plane recovery |
| External dependencies | Payment, email, SaaS, or cloud API outage | Timeouts, degraded modes, alternate providers where feasible |
| People/process | Accidental deletion, overly broad permissions | Risk-based approvals, audits, separation of duties |

### 4.2. Failure Domains and Blast Radius

A failure domain is the scope of resources exposed to the same fault. Separation can occur by process, node, rack, AZ, region, account/subscription, control plane, or provider.

Separating everything is not always right. Every new boundary introduces costs in replication, networking, consistency, IAM, observability, and operations. The goal is isolating faults with unacceptable consequences while keeping the architecture operable.

## 5. Availability Must Tie to SLI/SLO Definitions

### 5.1. SLI, SLO, and SLA

- **SLI (Service Level Indicator):** actual measurement, e.g., percentage of valid checkouts completing within 2 seconds.
- **SLO (Service Level Objective):** target for an SLI over a measurement period, e.g., 99.9% of valid bookings completing over a one-month window.
- **SLA (Service Level Agreement):** contractual commitment with definitions, exclusions, and remedies on breach.

An SLO with an unclear denominator breeds disputes. Specify:
- Which requests are in scope: all requests, valid requests, user journeys, or vetted transactions?
- Do client 4xx errors from invalid input count in the SLI?
- How is a client timeout counted when the server actually committed the booking?
- Do retries of the same transaction count as one or multiple measured events?
- Is the window a rolling 30 days or a calendar month?
- Is scheduled maintenance excluded, and who approves it?

### 5.2. End-to-End Checkout SLI

A valid transaction can be defined as successful when:
1. The booking is recorded once in a valid business state.
2. Inventory is reserved per business rules.
3. Payment is confirmed or in a contractually permitted pending state.
4. The user receives a queryable outcome.
5. No data invariants are violated.

A single HTTP 2xx metric cannot represent this outcome.

Example SLI:
\[
SLI_{\text{checkout}}=
\frac{\text{valid transactions completed with proper semantics within deadline}}
{\text{total valid transactions attempted}}
\]

Targets and deadlines must be agreed among Product, SRE, and business owners based on required user experience.

### 5.3. Error Budgets

With a 99.9% availability SLO over a 30-day period (assuming 30 continuous days):

\[
30 \times 24 \times 60 \times (1-0.999)
=43.2 \text{ minutes}
\]

This is the equivalent downtime budget if the SLI is time-based. If the SLI is based on successful request ratios, the error budget is the allowed rate of failed requests and does not convert directly into minutes when traffic fluctuates.

Error budgets facilitate trade-off discussions between release velocity and stability. They are never automatic permission to bypass security, compliance, or data correctness controls.

## 6. Dependencies Do Not All Belong on the Critical Path

A sound architecture classifies tasks by how essential they are to business outcomes. Auxiliary tasks can leave synchronous requests via queues or outboxes.

For example:
- Recording booking and payment state are core steps.
- Sending emails, updating analytics, and notifying CRM can run asynchronously.
- Recommendations can turn off under overload.
- Dashboards can lag a few minutes without failing checkout.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant B as Booking service
    participant D as Booking DB
    participant P as Payment provider
    participant O as Outbox
    participant Q as Broker
    participant N as Notification
    C->>B: Create booking
    B->>D: Write PENDING / reservation
    B->>P: Confirm payment
    P-->>B: Transaction outcome
    B->>D: Commit valid state
    B->>O: Write event in same transaction
    B-->>C: Queryable outcome
    O->>Q: Relay event
    Q->>N: Consume event
    Note over Q,N: Notification failure never reverses committed booking
~~~

This is a conceptual pattern. If the payment provider times out after receiving a charge request, the state may be **UNKNOWN/PENDING_RECONCILIATION** and must never be treated as a definitive failure. Use idempotency keys and transaction lookups before retrying or releasing inventory.

## 7. Timeouts, Retries, and End-to-End Completion Time

### 7.1. End-to-End Timeout Budgets

Suppose a request has a 2-second deadline. If the gateway waits 2 seconds for the backend, the backend waits 2 seconds for the database, and the payment client waits 2 seconds, actual requests can stretch far beyond the target.

Propagate deadlines/budgets across hops:
- Gateway reserves time for serialization and returning responses.
- Application allocates remaining budget to dependencies.
- Database statement timeouts stay appropriately below application timeouts.
- External calls define separate connect and response timeouts.
- Workers/queues define visibility timeouts, job timeouts, and retry policies.

Timeouts do not necessarily stop execution at the target system. A client may time out while payment still processes. Thus timeouts create uncertainty; reconcile rather than assuming the command never ran.

### 7.2. Retries Can Raise Availability or Worsen Outages

Retries help with transient errors, yet synchronized retries can spark a **retry storm**. Rules:
- Exponential backoff and jitter.
- Cap attempt counts, retry budgets, and total deadlines.
- Retry only idempotent operations or calls carrying idempotency keys.
- Classify permanent/transient errors, 4xx/5xx, rate limits, and timeouts.
- Stop or curb retries when circuit breakers open.
- Never retry simultaneously at every layer; retry amplification multiplies requests exponentially.

If three tiers each retry three times, one original request can generate many downstream dependency calls. Decide which tier owns retries and track attempt counts.

### 7.3. Circuit Breakers and Bulkheads

- **Circuit breaker:** temporarily pauses calls to a continuously failing dependency, giving recovery time and probing cautiously in half-open state.
- **Bulkhead:** isolates connection pools, thread pools, queues, or concurrency so one dependency outage never exhausts the whole application.
- **Load shedding:** rejects lower-priority work when load exceeds capacity.
- **Graceful degradation:** keeps core business intact while disabling or reducing auxiliary features.

Test these controls with realistic thresholds, timeouts, and recovery behaviors. Overly sensitive circuit breakers cause service flapping; overly loose ones fail to protect resources.

## 8. How Do Caches, Queues, and Fallbacks Affect Availability?

### 8.1. Caches

Caches can serve reads when origins temporarily fail, but only when stale data is acceptable to the business. Stale-while-revalidate works for public catalogs; never use stale inventory counts or payment statuses if it risks invalid transactions.

Specify:
- Source of truth.
- TTL and freshness objectives.
- Invalidation/refresh mechanisms.
- Behavior on cache miss during an origin outage.
- Cache poisoning prevention and tenant isolation.
- Cold-cache origin capacity.

### 8.2. Queues

Queues absorb bursts and decouple producers from consumers. When consumers fail, producers can continue within buffer/retention limits; however, queues cannot guarantee timely completion if backlogs grow unchecked.

Monitor:
- Oldest message age.
- Consumer lag and throughput.
- Remaining retention window.
- DLQ growth, retries, and poison messages.
- Sink saturation and backlog drain times.

### 8.3. Fallbacks

Fallbacks improve availability only when returning **valid business outcomes**. For example:
- Recommendation service fails: return the page without suggestions.
- Email provider fails: still display the booking in the app and retry email later.
- Search index fails: fall back to querying another source if capacity and correctness permit.
- Payment provider fails: return an ambiguous status with lookup options, never marking paid falsely.

A fallback serving stale or wrong data turns an availability outage into a worse correctness incident.

## 9. Quantifying Availability with Redundancy and Practical Limits

### 9.1. Example Chain with Redundancy

A journey requires:
- Gateway availability 99.99%.
- API layer with two parallel replicas, each 99.9% (assuming independence).
- Database HA availability 99.95%.
- Payment provider availability 99.9%.

Estimated API layer availability:

\[
A_{\text{API}}=1-(1-0.999)^2=0.999999
\]

Chain availability:

\[
A_{\text{journey}}=
0.9999 \times 0.999999 \times 0.9995 \times 0.999
\approx 0.998401
\]

Roughly 99.84% under the independence model. The payment provider and database still weigh heavily even with very high API redundancy.

### 9.2. Adding Common-Cause Failures

Suppose the probability of a common-cause fault taking down both API replicas during the period is \(q\). Then API layer availability cannot use the pure independence formula alone. A simple model is:

\[
A_{\text{API}} \approx (1-q)\left[1-(1-a)^2\right]
\]

Where \(a\) is each replica's independent availability absent common-cause failures. If \(q\) is significant, redundancy gains shrink. Even this model simplifies reality since common-cause and individual faults can correlate.

### 9.3. Time-Based vs. Request-Based Availability

- **Time-based availability:** share of time a service is up during the period.
- **Request-based availability:** share of eligible requests completing under valid conditions.
- **Journey-based availability:** share of users completing the business journey.
- **Data freshness/quality:** whether data is fresh and accurate enough to serve the action.

A service might stay up 99.99% of the time yet fail 1% of requests due to peak-hour overload. Conversely, brief nighttime downtime may affect very few requests. Choose SLIs reflecting user value.

Never add or multiply availabilities with differing definitions or measurement periods together.

## 10. RTO, RPO, and Recovery Planning

- **RTO (Recovery Time Objective):** maximum target duration to restore service after an incident within a defined scope.
- **RPO (Recovery Point Objective):** maximum acceptable data loss expressed as time.
- **MTTR:** mean time to repair/recover; an operational metric, not a replacement for RTO.
- **Failover:** shifting operations to a standby component/region.
- **Failback:** returning to the primary environment after resolving the incident and verifying state.

Each journey can have distinct RTO/RPO targets. Catalog APIs can tolerate slower recovery than checkout; analytics logs can have a different RPO than the booking database.

### 10.1. DR Strategies

| Strategy | Description | Trade-offs |
| --- | --- | --- |
| Backup and restore | Restore from backups after an incident | Lower standby cost, typically longer RTO |
| Pilot light | Core components run minimally in secondary region | Requires scaling and configuration during failover |
| Warm standby | Standby environment runs at reduced capacity | Faster RTO, incurs ongoing standby cost |
| Active-active | Multiple regions serve concurrently | Can minimize downtime, yet complex routing, consistency, and conflicts |

No strategy meets RTO/RPO automatically until tested. Replication does not replace backups: logic bugs or accidental deletions replicate to standby regions too.

### 10.2. Recovery Details Must Be Thorough

Runbooks must specify:
- Failover triggers and decision authority.
- Which components shift first and dependency order.
- DNS/traffic routing, certificates, IAM, secrets, and networking.
- Database replication lag, transaction consistency, write fencing, and split-brain prevention.
- Queue offsets, outboxes/inboxes, and message replays.
- Payment/inventory/booking reconciliation.
- Traffic opening criteria and journey-level health checks.
- Failback plan, customer communication, and auditing.

## 11. Designing SLOs by Dependency and Degraded Mode

Some components do not need the same SLO as the primary journey. Set SLOs by criticality:

| Journey/component | Suggested SLI | Acceptable degraded mode |
| --- | --- | --- |
| Login | Valid authentication rate, latency | Honor already-issued sessions/tokens within policy bounds |
| Search | Valid query result rate, p95 | Fresh public result caches within bounds |
| Checkout | Transactions completing with valid semantics | Never confirm if payment is unknown; allow status lookup |
| Booking confirmation | Queryable state rate | Clear pending state while external step is unresolved |
| Notification | On-time delivery rate | Queue and retry; never roll back booking |
| Reporting | On-schedule report completion rate | Delay with alerts without affecting checkout |

Optional dependencies may still need their own SLOs. For example, notifications may lag up to 10 minutes without failing checkout. Defining degraded modes and recovery bounds prevents confusion during incidents.

### 11.1. Dependency SLOs Do Not Simply Add Up

If an API depends on a payment provider, the API's SLO is influenced by the provider's SLO, though not necessarily equal to their product. Retries, timeouts, async workflows, fallbacks, and transaction counting determine observed outcomes.

Measure end-to-end directly, then use dependency metrics for root-cause analysis. Never simply multiply vendor SLAs together and publish that as your product SLO.

## 12. Chaos Engineering and Failure Testing

Mathematical models only form hypotheses. Knowing how a system truly behaves requires verification in controlled environments.

### 12.1. Tests by Failure Domain

| Test | Question | Evidence |
| --- | --- | --- |
| Kill one API instance | Do load balancers detect and reroute traffic? | Error rate, recovery time, remaining capacity |
| Lose one AZ | Do surviving AZs have enough capacity and data? | SLOs, replica placement, DB failover |
| DB failover | How do active requests, pools, and transactions behave? | Error duration, data integrity, RTO |
| Payment timeout | Are duplicate charges or wrong booking states avoided? | Idempotency, reconciliation, pending states |
| Broker unavailable | Do outboxes/backlogs hold events safely? | Queue age, event loss/duplicates, recovery |
| DNS/certificate failure | Can clients and service-to-service still connect? | Resolution, TLS errors, fallback paths |
| Secret/KMS unavailable | How are running vs. restarting workloads affected? | Secret fetches, caching/rotation behavior |
| Regional outage | Does DR boot and serve end-to-end? | RTO/RPO, data consistency, user journeys |

### 12.2. Safe Testing Principles

- Define hypothesis, scope, blast radius, stop conditions, and accountable owners.
- Start in sufficiently representative test/staging environments, then controlled production tests if approved.
- Never simulate faults that corrupt customer data or trigger unauthorized real transactions.
- Measure baselines before and after tests.
- Maintain rollback/abort controls and incident communication channels.
- Document outcomes, surprises, and remediation items.
- Test recovery hazards too: dependency recovered while backlogs are huge, caches are cold, or replicas are resyncing.

Chaos engineering is not random fault creation. Its purpose is testing resilience hypotheses.

## 13. Journey-Based Observability and Alerting

Dashboards should combine:
- **Business SLIs:** checkout success, booking state correctness, payment reconciliation.
- **User experience:** p95/p99 journey latency, error rates, region/device breakdowns.
- **Dependency health:** latency, availability, quotas/throttles, circuit breaker states.
- **Resource saturation:** CPU, memory, connection pools, DB locks/I/O, networking.
- **Queueing:** oldest message age, backlog, retries/DLQs.
- **Recovery:** replication lag, backup validation, last successful DR test.
- **Change correlation:** deploys/config/feature flags changed prior to incidents.

Distributed tracing needs correlation IDs across APIs, queues, and workers. For async paths, propagate trace context or business correlation/causation IDs; never log sensitive tokens or PII purely for debugging convenience.

Alerts should reflect **user symptoms** and severity. An 80% CPU alert may be a helpful signal, yet checkout p95 or success rate breaching SLO shows direct business impact.

## 14. Real-World Scenario: Checkout with Multiple Dependencies

### 14.1. Context

A booking platform has these components:
- Edge/gateway and authentication.
- Booking API and Inventory service.
- Booking database.
- External payment provider.
- Broker and notification worker.
- Email/SMS provider.

Hypothetical goals:
- 99.9% of valid checkout transactions reach a deterministic state over 30 days.
- Checkout p95 under 2 seconds at agreed load.
- Booking database RTO under 60 minutes; RPO under 5 minutes.
- Notifications sent within 10 minutes normally, never blocking bookings.

Thresholds are lesson assumptions and must be confirmed by Product/SRE/legal before becoming commitments.

### 14.2. Critical-Path Classification

| Component | Hard/soft in checkout | Behavior on failure |
| --- | --- | --- |
| Gateway/API | Hard | Shift to healthy replicas/zones |
| Auth | Hard where auth is required | Never bypass policy; allow valid cached sessions/tokens |
| Inventory | Hard | Reject or hold pending per reservation rules; never oversell |
| Booking DB | Hard | HA/failover, commit, and reconcile |
| Payment | Hard for prepaid bookings | Unknown/pending + idempotent lookups |
| Broker | Soft for sync response if outbox is durable | Outbox relay retries later |
| Email/SMS | Soft | Queue and resend; status stays queryable in app |

### 14.3. Common Failures from Poor Design

- Email provider outage causes checkout to return 500 despite payment succeeding.
- Payment timeout is treated as failure; client retry creates a second charge.
- Booking DB promotes a new primary, yet app keeps stale connections writing to the old endpoint.
- Broker runs out of storage; outbox relay stalls with zero alerts.
- Two AZs run API replicas yet share an unavailable identity dependency.
- Regional failover triggers without matching data/secrets/certificates ready.

### 14.4. Verification Plan

1. Disable email provider in staging; prove bookings complete and events deliver later.
2. Time out payment requests after provider acceptance; prove zero duplicate charges and successful reconciliation.
3. Kill API instances; measure traffic shift duration and p95.
4. Drill DB failover; verify transactions, connection pools, and data integrity.
5. Halt the broker temporarily; measure outbox growth, alerts, and drain times.
6. Simulate regional loss per DR plan; measure RTO/RPO and post-recovery checkout journeys.
7. Review cost and capacity when redundancy activates.

## 15. Common Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Using API uptime as product availability | Misses DB, auth, payment, and external dependencies | Measure SLIs across business journeys |
| Multiplying all component availabilities as independent | Over-optimistic when common-cause failures exist | Analyze common causes and failure domains |
| Treating notifications as hard dependencies | Auxiliary provider fails checkout | Decouple with outboxes/queues and degraded modes |
| Treating payment timeouts as failures | Risks duplicate charges | Idempotency, status lookups, and reconciliation |
| Unbounded retries at every layer | Retry storms, prolonged outages | Retry budgets, backoff, jitter, and single retry owner |
| Replicas sharing AZ/credentials/config | Redundancy fails on common-cause faults | Separate failure domains and test |
| Backups exist without restore drills | RTO/RPO lacks proof | Rehearse restores and measure outcomes |
| Using vendor SLAs as product SLOs | Fails to reflect actual requests/journeys | Define and measure end-to-end SLIs |
| Fallbacks serving stale data for transactions | Causes correctness bugs | Freshness policies and sources of truth |
| Treating queues as infinite capacity | Backlogs swell and data expires | Retention, bounded admission, age alerts |
| Alerting only on CPU | Misses user journey failures | Business SLIs, traces, dependencies, and saturation |
| Chaos tests without stop conditions | Causes uncontrolled outages | Hypotheses, scope, abort/rollback, and owners |

## 16. Hands-On Exercise

A cloud booking platform runs across two availability zones. Users report intermittent checkout failures even though dashboards show 99.99% API uptime. The system also depends on a booking database, identity provider, payment gateway, broker, email provider, and DNS. Product proposes 99.9% valid checkout completion over 30 days; database RTO 45 minutes, RPO 5 minutes.

Complete the following:

1. Draw the dependency graph for the checkout journey; classify hard, soft, alternative, and shared dependencies.
2. Define an end-to-end SLI with denominator, eligibility criteria, success semantics, and completion deadline.
3. Compute estimated series availability with explicit assumptions; add two-replica redundancy and common-cause modeling.
4. Identify at least five common-cause failures capable of taking down both AZs together.
5. Design degraded modes for email, broker, payment, identity, and database; specify which features degrade.
6. Allocate timeouts/deadlines across gateway, API, database, and payment; explain handling of ambiguous payment outcomes.
7. Propose SLOs for checkout, notification freshness, and reporting; calculate error budgets where appropriate.
8. Write database failover and regional DR runbooks covering data consistency, queues/outboxes, and reconciliation.
9. Build a chaos/failure test plan with hypotheses, blast radius, stop conditions, and pass criteria.
10. Write an ADR capturing decisions, trade-offs, residual risks, owners, and revisit triggers.

**Self-Assessment Criteria:** a strong solution measures business-outcome availability, uncovers hidden dependencies and common-cause faults, uses semantically sound fallbacks, validates RTO/RPO, and explicitly documents residual risks.

## 17. Pre-Commitment Availability Checklist

- [ ] Business journeys and success criteria are explicitly defined.
- [ ] Dependency graphs include external services, control planes, identity, DNS, secrets, and data.
- [ ] Components are classified as hard, soft, alternative, shared, and hidden dependencies.
- [ ] Series, parallel redundancy, and common-cause analyses state explicit assumptions.
- [ ] Failure domains and blast radii appear on diagrams.
- [ ] SLIs/SLOs/SLAs specify denominators, deadlines, request scope, and exclusions.
- [ ] Error budgets match their SLI type.
- [ ] Cross-hop timeouts/deadlines are budgeted; retries enforce idempotency and bounds.
- [ ] Circuit breakers, bulkheads, backpressure, and degraded modes are tested.
- [ ] Caches/fallbacks never violate freshness, authorization, or correctness.
- [ ] Queues/outboxes, replays, DLQs, and side effects have clear semantics.
- [ ] RTO/RPO targets are set per dataset/journey and verified via restore/failover drills.
- [ ] Common-cause failures across DNS, IAM, KMS, deployments, quotas, and regions are addressed.
- [ ] Dashboards/alerts track business SLIs, dependency health, and saturation.
- [ ] Chaos/failure tests include hypotheses, stop conditions, rollbacks, and owners.
- [ ] ADRs record evidence, trade-offs, residual risks, and revisit triggers.

## Key Takeaways

A system's availability does not equal one API's uptime or replica count. It depends on **actual business journeys**, mandatory dependencies, how they compose in series or parallel, common-cause failures, and how the system degrades or recovers.

Design from the chain **user action → dependency graph → SLI/SLO → failure domains → timeouts/retries/fallbacks → RTO/RPO → fault testing and production telemetry**. Commit to availability targets only with definitions, evidence, and operational procedures proving end-to-end results.
