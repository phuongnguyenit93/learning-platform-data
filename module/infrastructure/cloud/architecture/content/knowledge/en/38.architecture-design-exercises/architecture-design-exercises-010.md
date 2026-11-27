# Defending Options and Adapting When Business Requirements Change

## 1. Exercise Objectives

A sound cloud application design still needs to be **defended under critique**: which business need does it solve, what reliability and performance does it achieve, what trade-offs does it make, what evidence backs the decision, and what conditions force a redesign?

This lesson puts learners in the role of architect for a retail platform. Learners must **define requirements → design options → compare choices → defend decisions → absorb requirement changes → run impact analysis → update the design → plan verification**. These skills move Well-Architected principles from a passive checklist into active engineering decisions.

By the end of this lesson, learners will be able to:

1. Translate business needs into measurable non-functional targets, SLIs/SLOs, and acceptance criteria.
2. Construct arguments along the chain **requirement – choice – trade-off – evidence – risk – revisit trigger**.
3. Answer critiques from product owners, SRE, security, data governance, and finance.
4. Analyze ripple effects of new requirements across networking, compute, data, security, scalability, reliability, cost, and operations.
5. Update Architecture Decision Records (ADRs), diagrams, migration plans, and test plans consistently.
6. Recognize when to negotiate targets or escalate for business decisions rather than making unbacked technical promises.

> **Guiding principle:** Defending an architecture does not mean clinging to your initial choice at all costs. A good decision holds within its stated assumptions and carries clear triggers to revisit when facts change.

## 2. Running Scenario: OmniOrder

### 2.1. Context

The hypothetical enterprise **OmniOrder** is modernizing an ordering system running on self-managed servers into a cloud application. Customers can browse products, search, add to cart, place orders, and pay via a partner gateway. Operations staff can look up, cancel/refund, and reconcile orders. The delivery team has eight engineers experienced in Java, SQL, containers, and CI/CD, with limited experience operating multi-service distributed systems.

All parameters below are **assumptions for design practice**, not generic sizing recommendations or commitments for any specific cloud provider.

| Code | Initial requirement or constraint | Priority |
|---|---|---|
| BR-01 | Customers can place orders, pay, and track status | Mandatory |
| BR-02 | Staff look up and export end-of-day order reports | Mandatory |
| Q-01 | Current peak: 300 read requests/second and 40 checkout starts/second | Forecast requiring test |
| Q-02 | Product view p95 under 400 ms; order-creation response p95 under 900 ms | Per-journey SLO |
| Q-03 | Ordering API availability SLO 99.9% monthly | Target; scope needs definition |
| Q-04 | Single Availability Zone failure: target service recovery within 10 minutes | Target requiring drill |
| Q-05 | Full-region disaster: max RTO 2 hours, max RPO 15 minutes | DR requirement needing proof |
| S-01 | Customer and payment data must be protected, encrypted, and access-controlled | Mandatory |
| O-01 | Deploy multiple times per week with error observability and rollback | Mandatory |
| C-01 | Total cloud spend stays under finance-approved ceiling | Ceiling not yet provided |
| T-01 | Cutover within 6 months; legacy system remains for transition reconciliation | Schedule constraint |

**Critique point to catch:** 99.9% availability over a 30-day month equals roughly \(30 \times 24 \times 60 \times 0.001 = 43.2\) minutes of unavailability budget if measured by minutes with zero exclusions. A single 2-hour region outage blows past that budget. Therefore **Q-03 and Q-05 are not yet proven compatible**; clarify SLO scope, incident probability/duration, continuity plans, or accepted risk levels. Never treat a 2-hour RTO as proof of meeting 99.9%.

### 2.2. Business Flow and Invariants

Critical customer journey:

1. Browse catalog and add items to cart.
2. Submit order-creation request with an **idempotency key** for safe retries.
3. System snapshots price, quantities, address, and total amount; saves order in awaiting-payment state.
4. Payment gateway returns a result or sends callbacks that may arrive late or duplicated.
5. System confirms valid orders and emits events for notifications and operations.

Unbreakable **invariants**: a retry must never create a second order; the same payment must never be recorded twice due to retries; locked order totals must not mutate just because catalog prices change; orders transition only along valid state paths.

The platform must distinguish **request accepted** from **order completed**. HTTP 202 does not mean payment succeeded; replying fast while backlogs grow unboundedly also fails business needs.

### 2.3. Questions to Ask Before Drawing Diagrams

- Does 40 checkouts/second mean user clicks on confirm or completed paid orders? What is the retry rate?
- Which endpoints and customer cohorts fall under the availability SLO? Are maintenance windows or bad inputs excluded?
- At which step must orders, inventory, and payments be immediately consistent? Which steps can run asynchronously?
- Does the payment gateway enforce connection/rate limits, callback timeouts, and provide failure-simulation sandboxes?
- Who signs off on sensitive data classification, residency, retention, and backup/key policies?
- Can we use payment-gateway tokens to avoid storing raw card data in our application?
- What is the exact C-01 ceiling, and which items are included (logging, egress, backups, DR, support)?
- How many regions/AZs and which services match legal, latency, and operational constraints?
- Which features take priority when resources tighten: checkout, or recommendations and reporting?

Where answers are missing, log an **assumption** with an owner and confirmation deadline. Never turn unverified guesses into written promises.

## 3. How to Defend a Decision

A strong argument follows this chain:

~~~text
Business goal / numbered requirement
   ↓
Quality attribute scenario and acceptance criteria
   ↓
Architectural choice and alternatives weighed
   ↓
Rationale, trade-offs, and cost
   ↓
Existing evidence / tests needed
   ↓
Residual risks, owners, and revisit triggers
~~~

For every major decision, learners must answer:

1. **What problem are we solving?** Tie directly to BR/Q/S/O/T codes.
2. **What viable alternatives existed?** At least one realistic option weighed.
3. **Why choose the current option?** Analyze performance, reliability, security, change velocity, and cost.
4. **What evidence backs it?** Benchmarks, data-flow reviews, failover tests, service pricing, and quota limits.
5. **What remains uncertain?** Traffic forecasts, data traits, partner behavior, team skill.
6. **When does the decision stop holding?** Shifts in load, regulations, SLAs, budget, or org structure.

Example of a weak answer: "Use microservices because they are cloud-native, easy to scale, and reliable."

Example of an evaluable answer: "With an eight-person team and evolving business logic, we prefer a multi-replica modular monolith. Ordering, Catalog, and Payment Integration keep clean module boundaries to govern data ownership. The downside is scaling the entire runtime when only checkout grows; we will measure DB waits, p95/p99, and throughput in load tests. Once independent scaling or release cadence is proven necessary and domain contracts stabilize, we will evaluate extracting modules via Strangler Fig."

## 4. Initial Architectural Choice

### 4.1. Option A: Multi-Replica Modular Monolith

One logical design:

~~~mermaid
flowchart TB
    C[Web / Mobile] --> E[DNS + CDN/WAF + Load Balancer]
    E --> A[Multi-replica / multi-AZ Java app]
    subgraph M[Modular Monolith]
      A --> CAT[Catalog]
      A --> ORD[Ordering]
      A --> PAY[Payment Integration]
    end
    CAT --> CACHE[(Read cache)]
    CAT --> DB[(Managed relational DB / Multi-AZ)]
    ORD --> DB
    PAY --> DB
    ORD --> OUT[Transactional Outbox]
    OUT --> R[Outbox Relay]
    R --> Q[Queue / Event Bus]
    Q --> W[Notification Worker]
    PAY --> PSP[Payment provider / Sandbox]
    A -. Logs, metrics, traces .-> OBS[Observability]
    DB -. Backups, health, audit .-> OBS
    Q -. Lag / DLQ .-> OBS
~~~

This is a **logical diagram**. The outbox is typically a table inside the business database written in the same transaction as order state changes; forwarding events to the broker happens afterward and may deliver duplicates, so consumers must be idempotent. Multi-AZ support at each layer must be verified against the chosen services; drawing a diagram does not automatically grant regional fault tolerance.

Key decisions:

- **Compute:** stateless multi-replica app; health/readiness checks, load balancing, controlled deployments, and rollbacks.
- **Networking:** expose only required entry points; isolate databases, workers, brokers, and management via network segmentation and least privilege.
- **Data:** authoritative relational DB for orders and transactions; explicit ownership of schemas, indexes, and migrations.
- **Cache:** suitable read caching with TTLs and invalidation; never let cache dictate transaction outcomes.
- **Messaging:** queue for post-processing work like notifications; bounded retries, DLQ, and business-completion SLOs.
- **Security:** TLS, least-privilege IAM, secret/key management, callback verification, and data-classification-aware logging.
- **Operations:** CI/CD, IaC, order-journey SLIs, DB waits, quotas, queue lag, and per-environment cost tracking.

### 4.2. Asynchronous Payment Handling and Deduplication

~~~mermaid
sequenceDiagram
    participant U as Client
    participant O as Ordering
    participant DB as DB
    participant P as Payment provider
    participant Q as Queue
    participant W as Worker
    U->>O: Create order (idempotency key)
    O->>DB: Transaction: pending order + outbox
    DB-->>O: Commit
    O-->>U: Order ID + pending status
    O->>P: Payment request (idempotency)
    P-->>O: Response / Callback
    O->>DB: Verify callback + transition state + outbox
    DB-->>O: Commit
    DB-->>Q: Relay emits stored event
    Q->>W: OrderConfirmed (may redeliver)
    W-->>Q: Ack after idempotent handling
~~~

This diagram simplifies a real state machine. The design must handle timeouts when the provider accepted the request before the app saw the response; out-of-order callbacks; refunds; ledger reconciliation with the provider; and preventing double charges. **Never assume ACID transactions span your database and an external payment gateway.**

### 4.3. Comparing Three Options

| Criterion | A. Multi-replica modular monolith | B. Domain microservices | C. Event-driven serverless |
|---|---|---|---|
| Delivery speed with 8-person team | Few pipelines, low ops coupling | Many services, contracts, ownership boundaries | Requires new workflow/event/quota expertise |
| Order-creation transactions | Straightforward local transactions | Requires cross-service consistency patterns | Requires state management and duplicate handling |
| Per-feature scaling | Limited if modules share one runtime | Strong when boundaries hold and downstreams keep up | Strong for fitting tasks; bounded by concurrency/quotas |
| Latency & partial failures | Minimal internal network hops | More network hops and timeouts to manage | Event/workflow orchestration can add latency |
| Security | Fewer service identities; must guard module boundaries | Many network boundaries, IAM roles, secrets | Fine-grained permissions per function/event/data |
| Cost | Predictable baseline; scales whole runtime | Higher baseline overhead, telemetry, network, on-call | Driven by invocations, runtime, downstream services |
| Future evolution | Extracting modules demands dependency discipline | Independent if domains are truly stable | Dependent on event contracts and reliability |

Choose **A conditionally** for phase one because the team is small, domains are still settling, and no per-capability scaling evidence exists yet. Never claim A is cheapest or meets SLOs before running benchmarks and cost models. B or C can still become the right choice if requirements, team capabilities, or workloads shift.

### 4.4. Risks to Disclose Upfront

| Risk | Consequence | Action needed / owner |
|---|---|---|
| Database bottlenecks at peak checkout | High latency, lock/connection exhaustion | Data + Platform measure queries, pools, IOPS, transactions |
| Full region outage | Breaches RTO/RPO/availability | Architect + SRE design and drill DR |
| Callback/payment timeouts & retries | Corrupted state or double charges | Payment owner runs sandbox and reconciliation tests |
| Stale cache | Outdated prices or product info shown | Product/Data define acceptable staleness |
| Slow autoscaler ramp | Spikes breach SLO before replicas ready | SRE measures scale-up time; consider pre-warming |
| Unconfirmed service pricing & ceiling | Budget overrun risk | Finance + Platform confirm pricing, budgets, buffers |

## 5. Putting the Design Under Verification

| Requirement | Related design | Verification required | Decision criteria |
|---|---|---|---|
| Q-01 / Q-02 | Gateway, app, DB, cache | Load test matching browse/search/checkout mix | Meets p95, error rate, and business throughput at peak |
| Q-03 | Multi-replica, health checks, rollback | End-to-end SLIs, replica fault tests | Serves within defined error budget |
| Q-04 | Multi-AZ spread, DB HA | Single-AZ failure drill | Restores function and data within target |
| Q-05 | DR/backups/replication | Restore/failover drill and reconciliation | Measured RTO/RPO pass |
| S-01 | IAM, secrets, encryption, networking, audit | Threat model, access tests, data-flow review | Zero privilege escalation; data policies satisfied |
| C-01 | Compute, DB, storage, observability, DR | Load-based forecast and post-test audit | Total spend within cap including headroom |
| O-01 | IaC, pipelines, runbooks | Canary/rollback and incident drills | Ops team can safely revert changes |

Different tests answer different questions. A load test does not prove RTO/RPO; a Multi-AZ toggle does not prove the SLO; a successful deployment does not prove proper data authorization.

### 5.1. Defending with Properly Scoped Metrics

Keep in mind when presenting:

- **Availability** differs from **RTO** and **RPO**: a slow recovery target can blow through an error budget.
- **Useful throughput** is successful business transactions within SLO, not raw accepted requests or HTTP 202s.
- **p95/p99 latency** must measure end-to-end journeys, never average percentiles across instances.
- **Autoscaling** adds compute, yet cannot cure saturated DBs, caches, queues, or downstream quotas on its own.
- **Backups** do not prove successful restores; test decryption, readability, and consistent recovery.
- **Cost** must include compute, DB, cache, egress, logging/tracing, backups, and DR under explicit assumptions.

## 6. Review Board Defense Session

Simulate 5 roles: Product Owner, SRE/Platform, Security, Data Owner, and Finance. The architect presents for 10 minutes, followed by 15 minutes of Q&A.

| Reviewer | Challenge question | Expected answer elements |
|---|---|---|
| Product | Why not split everything into microservices to scale easily? | Explain data/team coupling, alternatives, and extraction thresholds |
| SRE | If an AZ or full region dies, what happens to checkout? | Specify failure domains, dependencies, DR drills, unverified gaps |
| Security | What if callbacks are forged or replayed? | Signatures/auth, anti-replay, idempotency, audits, test proof |
| Data Owner | How do we prevent duplicate orders or double payments? | Invariants, unique constraints, idempotency, transactions, outbox, reconciliation |
| Finance | If traffic jumps 5–8x, what happens to spend? | Cost model, guardrails, scale caps, pricing assumptions, shedding plans |
| Business continuity | Can a 2-hour RTO truly coexist with a 99.9% SLO? | Surface the tension; offer higher HA/DR, approved SLO change, or residual risk |

Strong answers follow the pattern: **"We chose X to satisfy requirement Y, trading off Z. Evidence A supports it; B is still missing and will be tested via C. If D fails, we pivot to E."**

Weak answers treat product names or marketing claims as hard proof—such as "The cloud handles HA and scaling automatically so it can't go down."

## 7. Change Request 1: Flash Sale Campaign

After the initial review, the business adds a new requirement:

> During a 30-minute flash sale, reads jump from **300 to 2,400 requests/second** and checkout starts jump from **40 to 320 attempts/second**. Traffic can ramp within **30 seconds**. Checkout must hold p95 under 900 ms with zero duplicate orders; total autoscaling spend must not silently blow past budget.

These are **attempt initiation rates**, not completed paid orders. Capacity math must separate total requests, business throughput, retries, and asynchronous work.

### 7.1. Impact Matrix

| Layer | Risk from change | Evidence to measure |
|---|---|---|
| CDN / edge | Bandwidth, cache misses, WAF/rate limits | Cache hit ratio, edge quotas, egress spend |
| Application | Spike arrives faster than replicas boot | Desired/ready replicas, startup lag, p95/p99 |
| Ordering | Higher order writes, idempotency checks, lock contention | Successful orders, duplicates, DB locks, connections |
| Database | Queries, write IOPS, outbox growth, pool exhaustion | Wait times, query durations, locks, replication lag |
| Queue / workers | Events arrive faster than workers drain | Enqueue/dequeue rates, oldest age, DLQ, drain time |
| Payments | Provider rate limits and timeouts | Sandbox behavior, quotas, retries, reconciliation |
| Observability | Log/trace volume and ingestion cost surge | Sampling rates, log GB, ingestion spend |
| Finance | Pre-scaling and headroom add cost | Spike cost estimate, hard ceiling, scale-in behavior |

### 7.2. Improvement Options

**A1. Pre-scale the app ahead of the campaign:** raise minimum replicas based on tests, tune database, cache read paths, check quotas and payment limits. Fast to execute, though it scales the whole runtime and can push bottlenecks straight into the DB.

**A2. Separate read and write paths:** CDN/cache for catalog, read models or read replicas where appropriate; checkout keeps hitting authoritative data. Offloads DB reads while introducing cache staleness, stampede risk, and new costs.

**A3. Bounded asynchronous checkout intake:** durably persist orders and idempotency keys, return clear pending status, process via workflow/queue. Absorbs spikes smoothly, yet changes UX, requires business-completion SLOs, deduplication, and backlog management. Never declare an order successful merely for entering a queue.

**Conditional proposal:** test A1 combined with A2's read offloading first; adopt A3 only if the business accepts asynchronous checkout states and transactional guarantees pass correctness tests. Do not reflexively rewrite into microservices just to survive a short traffic spike.

### 7.3. Test Plan and Decision

~~~text
Test 1: baseline 300 read/s + 40 checkout attempts/s
Test 2: step-ramp to 2,400 read/s + 320 checkout attempts/s
Test 3: 30-second burst ramp to peak load
Test 4: sustain peak for 30 minutes; watch DB/queue and outcomes
Test 5: drop load; measure backlog drain and scale-in
Test 6: payment timeouts, duplicate callbacks, retries, and order reconciliation
~~~

Record **requested vs. achieved rate, p95/p99, errors, valid orders, duplicates, DB waits, lag, quotas, autoscaling timeline, and cost**. If the load generator fails to hit target rate or uses unrepresentative data, never claim production readiness.

Abort conditions include order/payment discrepancies, sustained errors above approved bounds, runaway backlog growth, and out-of-scope impacts. Admission control protects the system under overload, provided rejection rates are reported transparently in SLIs.

**Adaptable decision:** keep the modular monolith, pre-warm for flash sales, optimize/cache reads, bound DB/payment concurrency, and monitor drain and scale-in. If flash sales become frequent or Ordering proves independent scaling/release needs, spin it out later via a new ADR.

## 8. Change Request 2: New Data Residency and Recovery Targets

An enterprise customer contractually requires that **identifying data, logs containing PII, backups, and DR copies remain inside a specific territory**. This is an **exercise assumption**, not a legal statement about any specific country's laws.

Simultaneously, the customer wants full-region disaster RTO cut from **2 hours to 30 minutes**, and RPO cut from **15 to 5 minutes**.

### 8.1. Conflict Analysis Before Redesigning

- Data copies can exist in databases, caches, logs, traces, analytics, object stores, snapshots, queues, dead-letter queues, and support tools.
- Inspect whether paths through payment providers, third-party observability, or external networks carry restricted data out of bounds.
- Multi-AZ within one region **does not equal** full-region outage resilience.
- A 30-minute RTO may require an independent standby region and rehearsed failover. If the designated territory lacks two independent compliant regions, residency directly conflicts with regional DR goals.
- Periodic backups alone cannot satisfy a 5-minute RPO; replication alone does not prove a 30-minute RTO if surrounding services cannot serve.
- Specify data, encryption keys, access controls, recovery sequencing, DNS, event replay, and consistency during regional switchover.

**Mandatory action:** verify exact contract wording, classify and map data flows, check permitted services/regions, design DR options, and model cost. If no feasible topology satisfies both constraints, escalate the conflict to business and legal owners—never quietly drop the residency rule.

### 8.2. DR Options to Compare

| Option | Value | Risks or limits |
|---|---|---|
| Multi-AZ inside compliant region + backup/PITR | Handles many local faults; simpler ops | Does not survive full-region loss |
| Two independent regions both inside residency bounds | Enables cross-region DR design | Must verify services, replication, keys, failover, cost |
| Heterogeneous DR env within the territory | Can satisfy location mandates | Complex networking, sync, ops, and drills |
| On-demand backup restore | Lower idle baseline cost | Unlikely to meet 30-min RTO / 5-min RPO |

**Conditional proposal:** if two compliant independent regions with required capabilities exist, engineer DR around failure domains, replication, security parity, runbooks, and real failover timings. If not, present **business options** to the contract owner: negotiate compliant SLAs, narrow service scope, or fund alternative infrastructure. Never claim compliance from a diagram alone.

### 8.3. Acceptance Criteria for the New Requirement

Run drills with representative workloads and data; measure from fault detection until customers can complete valid transactions. Reconcile recovered data against RPO, verify the order/payment state machine, confirm zero double-charging on event replay, test key decryption access, and validate integrations. Audit real end-to-end data flows from app through logs, backups, analytics, and third parties to prove residency.

## 9. Requirement Change Management Workflow

~~~mermaid
flowchart TD
    R[New requirement] --> C[Clarify owner, target, scope, deadline]
    C --> T[Classify mandatory / target / assumption]
    T --> I[Impact analysis across app, data, network, security, cost]
    I --> O[Compare options and trade-offs]
    O --> D{Feasible within constraints?}
    D -->|Yes| P[ADR + migration/test/rollback plan]
    D -->|Not yet| E[Escalate to authorized business owner]
    E --> O
    P --> V[Measure and verify]
    V --> G{Meets criteria?}
    G -->|No| O
    G -->|Yes| A[Approve rollout and monitor]
~~~

| Impact dimension | Questions that must be answered |
|---|---|
| Business / UX | Does the definition of "success", execution order, or user behavior change? |
| Compute / scale | Do we need pre-warming, new autoscaling signals, component splits, or quota bumps? |
| Networking | Do latency, gateways, ingress/egress, partner links, or failure domains change? |
| Data | Do schemas, data owners, replication, consistency, backups, residency, or retention change? |
| Security | Do trust boundaries, IAM, secrets, keys, audits, or data-processing agreements change? |
| Reliability | Do SLOs, RTO/RPO, blast radius, failover, rollback, or runbooks change? |
| Operations | Are CI/CD, observability, on-call, manageability, and ownership ready? |
| Cost | Do compute, DB, egress, queues, logs, backup/DR, staffing spend, or caps change? |
| Delivery | How are deadlines, partner dependencies, in-flight data, and backward compatibility handled? |

A change request may be solved by **tuning parameters**, **adding/swapping components**, **adjusting boundaries/contracts**, or **renegotiating business targets**. The size of an architectural change is measured not by lines of IaC, but by impact on business logic, data, dependencies, and reversibility.

## 10. Defending Decisions with Traceability Records

Architectures are often presented as diagrams, yet a diagram alone never explains why components exist or what must be tested. A **requirement traceability matrix** connects each requirement to design, evidence, and accountable owners.

| Requirement | Linked decision | Evidence or test | Status / risk |
|---|---|---|---|
| BR-01: create & pay orders | Ordering, transaction/outbox, Payment Integration | Idempotency, retry, callback, order/payment reconciliation tests | Inconclusive prior to testing |
| Q-02: checkout p95 < 900 ms | Replicas, DB indexes/pools, network path | Load test with representative journey & dataset | Must measure at Q-01 load |
| Q-03: 99.9% monthly availability | Multi-AZ, health checks, rollback | End-to-end SLIs and fault drills | Tensions with regional RTO |
| Q-05: RTO 2h / RPO 15m | DR/backup/replication | Restore/failover drills and reconciliation | Not guaranteed by backups alone |
| CH-01: 8x spike | Pre-scale, read caching, quotas/guardrails | Spike/soak + cost report + business checks | DB/payment may bottleneck |
| CH-02: data residency | Data inventory, placement, IAM, logging, backups | Data-flow mapping, config/audit review | Compliant regions not yet verified |
| CH-03: RTO 30m / RPO 5m | Upgraded DR topology if needed | End-to-end recovery drill | May conflict with cost/residency |

When requirements change, update **deployment diagrams, data flows, requirement tables, ADRs, threat models, test plans, cost models, runbooks, and risk registers** together. Never let an ADR declare a new data owner while another diagram still depicts two systems writing freely.

### 10.1. Tagging Statement Certainty

| Label | Meaning | Example |
|---|---|---|
| **Assumed** | Unverified working assumption | 320 checkout attempts/s peak lasts only 30 minutes |
| **Measured** | Empirically measured with stated env and timestamp | p95 710 ms in 200 checkout/s test on dataset X |
| **Approved** | Signed off by authorized owner (decision or risk) | Product approves `PENDING` checkout state |
| **Open** | No reliable answer yet | Whether provider offers two compliant DR regions |
| **Rejected** | Violates constraints or fails cost-benefit | Dropping sensitive-data logging just to cut costs |

**Measured does not mean Approved**, and Approved does not replace Measured. Performance numbers hold only for the tested config, workload, data, and environment; an approved decision still requires a verification plan.

### 10.2. Sample ADR for a Workload Change

~~~markdown
# ADR-012: Capacity Strategy for OmniOrder Flash Sale

## Status
Proposed — pending load test results and budget approval.

## Context
CH-01: reads 300 to 2,400 req/s; checkout attempts
40 to 320/s within 30 seconds;
sustain peak 30 minutes, checkout p95 under 900 ms.

## Options
A. Pre-scale modular monolith, read caching, DB tuning.
B. Extract Ordering into an independently pipelined service.
C. Move checkout to an async intake workflow.

## Proposed Decision
Test A combined with read-path optimization first.
Keep Ordering as a module until evidence on load,
release cadence, or isolation demands extraction.

## Trade-offs
Higher pre-campaign cost and whole-app scaling;
DB/payment may still cap throughput.

## Verification
30-second spike ramp; 30-minute hold; reconcile
transactions, callbacks, retries, backlog, and cost.

## Revisit Triggers
If SLO fails inside budget cap or frequent campaigns
require independent scaling, evaluate B/C via a new ADR.

## Owners and Approval
Product, SRE, Data, Security, Finance.
~~~

When a new decision replaces an older ADR, mark **supersedes / superseded by** instead of erasing history. That preserves why an earlier choice fit once yet had to evolve as requirements or evidence shifted.

## 11. Negotiating Real Trade-Offs

Requirements often collide: stronger DR cuts RTO at higher cost; lower latency may demand extra caches, compute, or relaxed consistency; residency restricts deployment regions; tighter security alters access paths and operations.

Architects must present **options and consequences**:

| Choice | Value gained | Price paid | Decision maker |
|---|---|---|---|
| Keep high SLA, expand DR capacity | Achievable RTO/RPO if drills succeed | Replication, standby capacity, infra, ops toil | Business owner + Finance + SRE |
| Hold budget, negotiate longer recovery | Optimizes baseline cost | Longer outage exposure during disasters | Business / risk owner |
| Prioritize checkout under overload | Protects revenue path | May degrade recommendations, advanced search, reports | Product owner |
| Delay market launch until residency met | Cuts legal and data exposure | Delays revenue / expansion targets | Project sponsor and legal |
| Keep monolith, scale workers on queue | Minimal business-code churn; faster queue drain | Cannot isolate all runtime paths; still manage DB | Architect + Engineering |

**Mandatory constraints cannot be casually traded away.** If verified legal or contractual terms prohibit processing data in a location, never pick a non-compliant option because it is cheaper. Bring lawful options and business goals to authorized decision makers.

### 11.1. Quantifying Cost Without Inventing Figures

Model total cost as:

\[
C_{\text{total}} = C_{\text{compute}} + C_{\text{database}}
 + C_{\text{storage}} + C_{\text{network}} + C_{\text{observability}}
 + C_{\text{backup/DR}} + C_{\text{external}}
\]

For each term, publish **resource counts, active hours, data transferred/stored, unit prices, region, quotas, billing model, error margins, and buffers**. Pre-scaling for a flash sale raises replica-hours, while logging scales with request count and event size. DR adds standby replicas, backups, replication traffic, and drill costs.

Never assume spend scales linearly with RPS: caching reduces DB load, network egress scales with payload size, and many services use tiered pricing. Before obtaining live quotes, mark figures *unverified* and assign an owner rather than fabricating precise numbers.

### 11.2. Quantifying Risks

A practical risk register includes:

| Risk ID | Scenario | Preliminary severity | Trigger | Mitigation / Owner |
|---|---|---|---|---|
| R-01 | DB pool exhausts during flash sale | High | Rising queue waits or timeouts | Benchmarks, pool/connection caps, Data + SRE |
| R-02 | No DR region meets residency | High | Region/service audit fails | Present contractual/infra options, Architect + Legal |
| R-03 | Duplicate or out-of-order payment callbacks | High | Reconciliation mismatch or duplicates | State machine, idempotency, Payment owner |
| R-04 | Runaway scaling breaches budget | Medium–High | Replicas/egress/logs exceed thresholds | Quotas, cost alerts, pre-approved cap, Finance/SRE |
| R-05 | App rollback breaks data compatibility | High | Incompatible schema migration | Expand-contract, canary, rehearsal, Engineering |
| R-06 | SLO breached during AZ outage | High | Fault drill fails or slow failover | Readiness checks, HA DB, SRE |

Ratings above are illustrative; real teams apply an agreed risk scale noting likelihood, impact, and residual risk after controls.

## 12. Cutover, Acceptance, and Rollback Planning

Even an approved architecture fails if rollout and data transitions are poorly planned.

1. **Snapshot baseline:** releases, configs, dependencies, topology, traffic, telemetry, data, and pre-change costs.
2. **Validate key hypotheses:** run scoped PoCs/benchmarks; measure DB and gateway quotas, DR, and key access.
3. **Contracts and data:** data owners, schema versions, migrations, reconciliation, backfills, failure modes, compatibility.
4. **Canary or traffic shift:** move a controlled traffic slice; compare SLIs and business events across versions.
5. **Rollback gates:** define error, latency, data-integrity, overload, or budget thresholds that trigger a halt.
6. **Point of no return:** dropping DBs/keys, irreversible migrations, writer cutover—only after sign-off and evidence.
7. **Post-change watch:** compare SLOs, alerts, queue lag, transaction data, spend, and scale-in behavior.

**Rollback is not merely reverting a container image.** Once a new version writes data under a new schema, old binaries may fail to parse it. Use expand-and-contract patterns and backward-compatible migrations where feasible; specify how post-cutover writes are handled and what happens past the point of no return.

### 12.1. Inspectable Gate Template

~~~yaml
change_id: omniorder-flash-sale
status: proposed
business_owner: omniorder-product
technical_owner: platform-team
requirements:
  - CH-01
gates:
  workload_profile_reviewed: pending
  load_and_spike_test_passed: pending
  idempotency_reconciliation_passed: pending
  database_and_payment_quota_checked: pending
  security_review_passed: pending
  cost_ceiling_approved: pending
  rollback_drill_passed: pending
rollout:
  strategy: canary-then-progressive
  stop_on_slo_breach: true
  observation_window: "Per change record"
evidence:
  adr: "ADR link"
  test_report: "Load test report link"
  runbook: "Rollback runbook link"
approvals:
  product: pending
  sre: pending
  security: pending
  finance: pending
~~~

This is a form template, **not an automated deployment script**. Pending gates must be closed with evidence and authorized sign-offs; pending does not authorize cutover.

## 13. Re-Evaluating Against All Six Well-Architected Pillars

| Pillar | Questions the architect must defend | Evidence and trade-offs |
|---|---|---|
| **Operational Excellence** | Can the team understand, monitor, deploy, roll back, and operate post-change? | IaC, runbooks, ADRs, SLIs, on-call; extra services increase ops overhead |
| **Security** | Are trust boundaries and data protected under new requirements? | Threat models, IAM, encryption/keys, data flows, audits; residency narrows DR choices |
| **Reliability** | How do instance/AZ/region and partner outages affect journeys? | Fault/DR drills, retries, idempotency, circuit breakers, RTO/RPO; redundancy adds cost |
| **Performance Efficiency** | Do constrained resources scale right and hit real p95/p99? | Load/spike/soak tests, query waits, queue lag, autoscale timelines; caches carry staleness |
| **Cost Optimization** | Are SLOs met inside budget with sensible post-peak scale-in? | Cost per successful transaction, quotas, egress, logs, DR; HA raises baseline spend |
| **Sustainability** | Are idle resources, wasteful retries, and unnecessary transfers minimized? | Right-sizing, scale-in, retention policies, workload efficiency, deduplication |

**Conditional pass** is valid when unverified items have explicit owners and deadlines. However, if mandatory mandates like data residency or payment correctness remain unverified, never mark the design fully compliant.

## 14. Hands-On Workshop: Architecture Review Board

### 14.1. Roles and Timing

| Role | Primary focus |
|---|---|
| Cloud Architect | Target design, assumptions, trade-offs, architectural updates |
| Product / Business Owner | Revenue flows, UX, priorities, scope, deadlines |
| SRE / Platform | SLOs, autoscaling, on-call, failover, rollback, operational cost |
| Security / Data Owner | Data residency, access controls, encryption, auditing, correctness |
| Finance | Total cost, budget caps, load-driven headroom |
| Reviewer | Probes weak assumptions, conflicts, and missing evidence |

Groups of 4–6 can combine roles; solo learners write both critiques and responses. Suggested timing **100 minutes**: 15 min clarify requirements; 20 min draft design; 15 min defend; 10 min receive change request; 20 min update design; 15 min second review; 5 min write minutes.

### 14.2. Deliverables Learners Must Submit

1. **Requirement register** with at least eight codes, priorities, owners, acceptance criteria, and verification status.
2. **Before-and-after diagrams** annotating data owners, sync/async paths, trust boundaries, and failure domains.
3. **Decision matrix** comparing at least three options, selection rationale, consequences, and revisit triggers.
4. **Two ADRs:** the initial decision and the updated decision driven by a change request.
5. **Impact analysis** of CH-01 and CH-02/CH-03 across compute, networking, data, security, DR, cost, and operations.
6. **Verification plan:** load/spike, data reconciliation, fault/DR drills, security/cost reviews with pass/fail thresholds.
7. **Risk register** with at least five risks, severity, owners, triggers, and mitigations.
8. **Board minutes:** approved, approved with conditions, or redesign required, with rationale.

### 14.3. Three-Round Practice Format

**Round A — Defend the baseline design:** Architecture team presents the scenario and A/B/C in 10 minutes. Reviewers trace every "fast, reliable, cheap, safe" claim to concrete metrics or evidence.

**Round B — Confront an 8x traffic spike:** Facilitator announces CH-01. The team updates bottlenecks, capacity plans, costs, SLOs, data flows, and slow-payment impacts. Adding app replicas alone is a hypothesis, not a complete solution.

**Round C — Strict residency and DR:** Facilitator announces CH-02/CH-03. The team flags unknowns, territory-compliant options, costs, RTO/RPO test plans, and required business decisions. Giving confident answers without verifying cloud service availability is a design error.

### 14.4. 100-Point Grading Rubric

| Criterion | Max points | Passing signs |
|---|---:|---|
| Requirement grasp, assumption & conflict detection | 15 | Highlights SLO–RTO tension and residency rules |
| Architecture, data ownership, and flows | 15 | Accurate diagram semantics, states, and failure domains |
| Rationale, alternatives, and trade-offs | 20 | Justified reasoning and clear revisit triggers |
| Analysis and adaptation under requirement shifts | 20 | Consistent impact analysis and updated ADRs |
| Test, DR, and rollback planning | 15 | Pass/fail thresholds, representative envs, evidence owners |
| Cost, security, and operations | 10 | Guardrails, quotas, residency, on-call, cost model |
| Presentation and defense | 5 | Direct answers without hiding limits |
| **Total** | **100** | |

This rubric is a learning aid. An alternative like Option A can still earn full marks if it meets requirements, provides solid evidence, and articulates trade-offs clearly.

## 15. Self-Practice Exercises and Answer Guide

### Exercise 1: Spotting Unbacked Promises

A teammate claims: "Deploying three replicas across two AZs with autoscaling enabled guarantees 99.9% availability and handles the flash sale."

**Task:** Write three critique questions and two verification tests.

**Hint:** Ask which failure domains cover the DB, gateway, and queue; how fast new replicas reach readiness; which endpoints/requests define the 99.9%; and what downstream capacity exists. Verify with a single-AZ fault drill and a spike test measuring p95, business throughput, and DB waits/queue lag. Extra app replicas cannot save a shared bottleneck.

### Exercise 2: How Does RPO Differ from RTO?

A customer demands at most five minutes of data loss and service recovery within 30 minutes after a full-region outage. The team has only hourly DB snapshots and IaC scripts.

**Task:** Critique the solution and propose additional evidence.

**Hint:** Hourly snapshots generally fail a five-minute RPO; IaC rebuilds infrastructure but does not restore recent transactions. Add appropriate replication/restore mechanisms, verified backup chains and key access, compliant regions, and failover drills measuring the last recovered transaction plus post-reopen order/payment processing.

### Exercise 3: Change Architecture or Renegotiate Targets?

A territory's available infrastructure options cannot achieve a 30-minute RTO within current budget, yet contracts mandate keeping data inside that territory.

**Task:** Draft two options for the business owner.

**Hint:** (a) increase budget or invest in independent compliant in-territory DR infrastructure backed by a PoC/drill and decision gates; (b) renegotiate a compliant RTO/service window or narrow product scope if contracting parties agree. Never store data in a prohibited location and dismiss it as an "accepted risk."

### Exercise 4: Reporting After a Failed Benchmark

In a spike test, 320 checkout attempts/s are sent yet only 180/s complete; p95 hits 1,600 ms, DB waits climb, queue oldest age rises steadily, and the autoscaler already scaled from 4 to 12 replicas.

**Task:** Defend a next step without overstating conclusions.

**Hint:** Conclude **failed** CH-01/Q-02 under test conditions. Do not blame insufficient app replicas, since rising DB waits and queue lag point to downstream saturation. Measure DB pools/locks/IOPS, retries, achieved rate, queue drain times, and payment quotas; tune queries, workers, and concurrency caps before altering topology. Update the ADR and retest under the exact same workload.

## 16. Sample Board Minutes After Two Requirement Changes

A well-grounded exercise outcome might read:

> The board **conditionally approves** the multi-replica modular monolith for phase one. Before cutover, the team must deliver Q-01 load test results, transaction reconciliation, a single-AZ outage drill, security review, and C-01 cost estimates. For CH-01, the team will test pre-scaling paired with read caching; if SLOs fail inside the cost cap, present an alternative option. For CH-02/CH-03, the board withholds approval on new residency or RTO/RPO commitments until data-flow reviews, compliant region/service verification, and DR drills complete. Product Owner, Security/Data Owner, and Finance remain accountable for confirming business constraints and budget.

Minutes do not declare a project finished. They record **decisions, conditions, unverified gaps, and next-step owners**. Whenever test results or contracts shift, update statuses and documentation before releasing.

## 17. Common Pitfalls

| Pitfall | Consequence | How to avoid |
|---|---|---|
| Presenting technology instead of needs | Unclear when the option adds value | Trace from business outcomes to quality attributes |
| "Cloud handles HA and autoscale" | Ignores DBs, quotas, startup lag, region loss | Engineer failure domains, drills, and load tests |
| Presenting only one option | Hides trade-offs and pivot conditions | Compare viable alternatives |
| Adding only app replicas for load spikes | DB/payments/queues stay bottlenecked | Profile bottlenecks system-wide |
| Treating HTTP 202 as order success | Backlog swells while users wait endlessly | Set SLOs on business completion |
| Treating Multi-AZ as regional DR | Fails RTO/RPO in region outages | Scope failure domains and run drills |
| Forgetting logs/backups in residency scope | Sensitive data escapes legal bounds | Run end-to-end data inventory and flows |
| Changing requirements without updating ADRs | Docs and reality drift apart | Enforce traceability, versioning, and reviews |
| Rolling back only container images | New data/schemas break older code | Use expand-contract, reconciliation, rollback drills |
| Hiding missing evidence | Board decides on blind assumptions | Tag assumed/measured/approved/open explicitly |
| Promising everything on a fixed budget | Masks real conflicts | Surface options and accountable decision makers |

## 18. Pre-Final-Defense Checklist

- [ ] Business requirements have owners, priorities, scope, assumptions, and acceptance criteria?
- [ ] Conflicts such as availability SLO vs. RTO/RPO are explicitly analyzed?
- [ ] Diagrams show entry points, authoritative data stores, sync/async paths, trust boundaries, and failure domains?
- [ ] At least two alternatives, selection rationale, and pivot conditions are documented?
- [ ] Compute, networking, data, caches, queues, third parties, quotas, security, and costs are re-evaluated for load shifts?
- [ ] Residency is checked across databases, logs, traces, backups, snapshots, queues, analytics, and partners?
- [ ] Representative workload tests measure p95/p99 latency, business throughput, errors, retries, backlog, and cost?
- [ ] Fault/DR drills measure actual RTO and RPO, including data and workflow recovery?
- [ ] Rollout, migrations, compatibility, canarying, rollback, and point-of-no-return gates exist?
- [ ] ADRs, risk register, requirement matrix, cost model, test plan, and runbook describe the exact same current decision?
- [ ] Unverified claims have owners, validation deadlines, and fallback plans?
- [ ] All six Well-Architected pillars are reviewed with explicit business-facing trade-offs?

## 19. Conclusion

**Defending an architecture** means turning a diagram into an auditable decision: linking requirements to solutions, exposing trade-offs, citing evidence, surfacing risks, and answering critiques responsibly. **Adapting when requirements change** means upholding business invariants and hard constraints while updating deployments, data placement, infrastructure, SLOs, and verification plans as needed.

In cloud application design, no single diagram fits every lifecycle stage. The right architecture must **explain why it works today, quantify its own limits, and carry clear triggers for what must change next**. That is how reliability, security, scalability, performance, cost, operations, and sustainability stay balanced under Well-Architected thinking.
