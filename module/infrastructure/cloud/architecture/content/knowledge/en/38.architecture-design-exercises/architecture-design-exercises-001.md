# Designing from Scratch: Requirements, Assumptions, Options, and Decisions

Cloud architecture design does not start with the question "should we use Kubernetes or serverless?", but rather with **what problem the system needs to solve, what is still unknown, and what trade-offs the organization is willing to make**. Two architectures with the same functionality can look completely different because of differing requirements for reliability, data consistency, delivery speed, team capability, regulations, and budget.

This exercise belongs to the **Design Exercises** topic of CLOUD_ARCHITECTURE. Learners will progress from business context to choosing networking, compute, data, integration, and deployment models; compare options, document justified decisions, and self-evaluate results against Well-Architected principles.

**Expected outcome:** after this lesson, learners can produce a defensible design document that includes:

1. A requirements table with sources, priorities, acceptance metrics, and scope boundaries.
2. An **Assumption register** detailing unknowns, impact if wrong, validation methods, and owners.
3. At least two viable architectural options with trade-offs across reliability, security, performance, cost, operations, and schedule.
4. A context diagram, a component diagram, and descriptions of critical data flows.
5. One or more **ADRs** (Architecture Decision Records) explaining the decision, rejected options, and conditions for revisiting.
6. A verification plan using load testing, fault injection, recovery, security testing, and business acceptance.

The content includes **a problem statement** for self-solving and **a reference solution** for comparison. There is no single right diagram for every organization. A good option needs to show which assumptions keep the decision valid and what evidence could cause the team to change its choice.

## 1. Thinking Process: From Requirements to Evidence

~~~mermaid
flowchart LR
    B["Business context & goals"] --> R["Measurable requirements"]
    R --> A["Assumptions & unknowns"]
    A --> C["Constraints & options"]
    C --> T["Trade-offs / ADR decisions"]
    T --> D["Diagrams & detailed design"]
    D --> V["Testing / review"]
    V -->|"New data available"| A
    V -->|"Criteria met"| G["Approval & phased rollout"]
~~~

This process is iterative. For example, if load testing proves the database becomes a bottleneck, the team loops back to consider caching, queries, data structures, or splitting workloads. Initial decisions are **testable architectural hypotheses**, not immutable commitments.

### 1.1. Distinguishing Four Types of Information

| Type | Meaning | Example |
|---|---|---|
| **Requirement** | Something the system must satisfy and has an approver | Customers can place orders successfully even during high traffic |
| **Constraint** | Something that cannot be arbitrarily changed within the current scope | Must use the contracted payment provider |
| **Assumption** | Something temporarily treated as true without sufficient evidence yet | Over 90% of catalog views can be cached |
| **Decision** | A justified choice after evaluating options | Use a modular monolith application for the initial release |

Misclassification degrades design quality. For example, "must use microservices" may just be a **technology preference**, not a requirement; "the system must tolerate the loss of one Availability Zone" is a testable requirement if approved by the product owner.

## 2. Problem Statement: Designing a Retail Platform for a Store Chain

A retail enterprise with **120 physical stores** plans to launch an online ordering channel combining delivery and in-store pickup. The team wants to launch the first version in **6 months** with a team of 8 developers, 2 infrastructure/operations engineers, and access to public cloud. The in-store inventory management system (ERP) currently exposes an API but will continue running in the on-premises data center for at least two years.

Users include customers, store staff, customer support, and system administrators. The application needs to support product search, pricing lookup, shopping cart, order placement, partner payment processing, order status tracking, and cancellation/refund requests according to business workflows.

### 2.1. Input Metrics Provided by the Business

| Item | Value used in exercise | Notes |
|---|---|---|
| Stores | 120 | Stores have different inventory and order-fulfillment capacities |
| Catalog | Around 12,000 SKUs | Prices and promotions change per campaign |
| Average orders | 45,000 orders/day | Needs verification against business forecasts |
| Peak product browsing | 1,200 requests/second | Total requests through CDN, not traffic reaching the origin API |
| Peak checkout | 60 checkout attempts/second for 5 minutes | "Attempts" does not mean 60 successfully paid orders |
| Read-to-write ratio | Read-heavy | Breakdown per endpoint not yet available |
| Initial deployment scope | One country, one cloud region | Data residency requirements need clarification |
| Time to launch | 6 months | Team capacity and feature scope constraint |
| Inventory ERP | On-premises, has API | Response time and availability not yet measured |
| Payments | Via PSP partner | Do not store raw card data in the application |

These are **simulated data for pedagogical purposes**, not figures from a real company. All thresholds below must be treated as proposals awaiting approval in a real project.

### 2.2. Minimum Functional Requirements

- Customers can browse the catalog, search for products, view store-specific pricing, and add items to a cart.
- Customers can place an order with a specific fulfillment option; the system prevents creating duplicate orders or duplicate payment charges when users click multiple times.
- Item quantities are confirmed only after checking/reserving inventory per contract with the ERP or an authorized reservation service.
- Customers can view order status; authorized staff can perform valid state transitions with an audit trail.
- Payments, cancellations, and refunds have clear states; events from the PSP may arrive late or be duplicated.
- Operations can view ordering health and receive alerts when critical business flows fail.

### 2.3. Questions Learners Must Clarify Themselves

Before designing the architecture, record your questions and assumptions:

1. Are products allowed to be **oversold** if the ERP does not respond?
2. How long are customers willing to wait for order confirmation? What are the start and end timestamps for that measurement?
3. When the PSP has captured funds but the ordering service loses connectivity, who reconciles and resolves it?
4. Does the ERP support **reservations with a TTL and idempotency key**? What are its actual rate limits and latency?
5. Does the system need to keep serving if **an entire cloud region fails** in the initial release, or is manual recovery within an approved timeframe acceptable?
6. How much order data loss can the business tolerate at most, and for which incident types are RTO/RPO measured?
7. Where may personal data and transaction records be stored, for how long, and who has access?
8. Does e-commerce need to split teams by domain immediately, or should simplicity be prioritized to hit the six-month deadline?

Do not pick convenient answers yourself and record them as validated requirements. In practice, these questions form the agenda of discovery meetings with the business owner, ERP owner, PSP, security, and operations.

### 2.4. Expected Deliverables

**In 90–120 minutes**, produce an initial design with four parts: a requirements table; assumptions/risks; two or three options; and one decision plus a verification plan. Then use the reference solution from section 7 onward for self-evaluation.

The duration is a suggestion for a workshop, not a hard limit. Each group should present **its hardest trade-off** along with the assumption that would change the decision.

## 3. Step 1 — Turning Needs into Testable Requirements

Quality requirements should specify an actor, a condition, and a measurable response. "Fast", "secure", "highly available", or "infinitely scalable" are all too vague.

| ID | Proposed requirement for the example | Measurement / Acceptance criteria | Priority |
|---|---|---|---|
| F-01 | Search and view products, update cart, place order, look up order | End-to-end business scenario test suite | Must |
| F-02 | No duplicate orders or charge requests caused by retries | Test sending the same idempotency key across multiple requests | Must |
| F-03 | Do not confirm a sale without a valid inventory reservation | Inventory contention and ERP failure tests | Must |
| Q-01 | Checkout availability **99.95% monthly**, with exclusions as agreed | Synthetic checks and SLIs from real checkout flows | Must |
| Q-02 | Catalog page p95 latency **≤ 300 ms** from edge/CDN in target market | Load testing + RUM measurement by connection type | Should |
| Q-03 | Internal checkout API processing p95 **≤ 800 ms**, excluding PSP-controlled payment steps | Load test with latency breakdown | Should |
| Q-04 | Sustain peak **60 checkout attempts/s for 5 minutes** and **1,200 catalog read requests/s** | Spike load test with realistic traffic distribution | Must |
| Q-05 | Full region loss: recovery target **RTO ≤ 60 minutes, RPO ≤ 5 minutes** | DR drill with post-recovery reconciliation | Proposed, needs approval |
| Q-06 | Do not store card numbers/PAN, protect personal data, and audit admin actions | Data flow, permission, log review, and testing | Must |
| Q-07 | Deliver initial release within **6 months** without exceeding current team capacity | Milestone plan, dependencies, completion level, and operating cost | Must |

The thresholds in Q-01 through Q-05 are meaningful only when **the SLI, measurement window, target subject, exclusions, and approver are properly defined**. For example, 99.95% over a 30-day month equals roughly **21.6 minutes of not meeting the target** when measured on a time basis. This is an illustrative error budget, not a free pass for every failure mode; request-based SLIs use a different formula.

### 3.1. Separating Functionality from Quality Attributes

**"Save an order"** is functionality; **"do not lose confirmed orders when a node fails"** is reliability; **"customers cannot see other people's orders"** is access control; **"ordering flow can recover within 60 minutes when an entire region is unavailable"** is a DR objective. Each leads to different design mechanisms and test approaches.

### 3.2. Assigning Sources and Decision Makers

The requirements table template should include columns: ID, statement, source, stakeholder/owner, priority, acceptance criteria, status (*proposed/approved/challenged*), and link to test/ADR. If no owner has approved it yet, mark it **proposed**. Architectural decisions based on unapproved requirements must be treated as carrying risk.

### 3.3. Defining Out-of-Scope Items

For the initial release, assume we are not designing a loyalty program, third-party marketplace, multi-country support, real-time ML recommendations, or ERP replacement. Including **out-of-scope** items in the document helps prevent scope creep in the diagram and inaccurate cost/schedule estimates.

## 4. Step 2 — Managing Assumptions and Unknowns

Assumptions should follow the structure: **what is temporarily assumed → impact if wrong → how to validate → owner → validation deadline**.

| ID | Illustrative assumption | What if it is wrong? | Validation method / owner |
|---|---|---|---|
| A-01 | CDN can serve ≥ 90% of catalog view requests at peak | Origin/API and database must handle much higher load than expected | Cache POC + hit ratio measurement / Web lead |
| A-02 | ERP supports safe, idempotent reservations with clear timeouts | Risk of overselling or having to redesign checkout flow | API test and ERP contract / ERP owner |
| A-03 | PSP supports payment intents, idempotency, and verifiable webhooks | Retries could create duplicate charges or transactions | Sandbox + contract docs / Payment lead |
| A-04 | Single region, multi-AZ meets initial release targets | Need active-passive/multi-region and extra budget | BIA, DR workshop / Business owner |
| A-05 | Team can operate the managed compute platform | Higher operational overhead, incidents, and maintenance | Pilot deploy, on-call drill / SRE lead |
| A-06 | Customer data is allowed to reside in the selected region | May require changing topology, storage, and policies | Data classification/legal review / Security |
| A-07 | Peak checkout of 60 attempts/s lasts only 5 minutes | Need higher capacity, quotas, and budget | Campaign forecast, load profile / Product |

Not all assumptions carry equal impact. Prioritize validating assumptions with **high consequence and low confidence**. For instance, A-02 determines order correctness and must be verified before finalizing service diagrams; A-01 determines cache and origin sizing and can be adjusted after load testing.

### 4.1. Simple Risk Classification Matrix

| Impact if wrong | High confidence | Low confidence |
|---|---|---|
| **High** | Monitor, validate at key milestones | **Early spike/POC, block dependent decisions** |
| **Low** | Record, review periodically | Validate during optimization or pre-launch |

Do not turn the "assumption register" into a place to justify choices after a product has already been picked. If an assumption is disproven, record the change, update the ADR, and note the impact on scope.

## 5. Step 3 — Defining Business, Data, and State Boundaries

The architecture must solve the ordering journey from the user's perspective and uphold business invariants. Choose domain boundaries before choosing container counts.

### 5.1. Business Capability Map

| Domain | Core responsibilities | Owned data |
|---|---|---|
| **Catalog** | SKUs, descriptions, images, display prices, product categories | Read data and point-in-time synchronized replicas |
| **Cart** | Unconfirmed customer shopping cart | Cart/session with TTL, not finalized orders |
| **Checkout/Orders** | Order creation and lifecycle management, idempotency, state | Orders, line items, price snapshots, state history |
| **Inventory integration** | Check/reserve/release inventory via ERP | Reservation ID, sync state, and reconciliation results |
| **Payment integration** | Create payment intents, receive webhooks, reconcile payments | Payment reference, status, and events; no PAN stored |
| **Fulfillment** | Route orders to stores, track preparation/delivery | Processing history and delivery/pickup milestones |
| **Identity & access** | Customer authentication and staff authorization | Identities, roles, account associations |

Domains do not have to map **one microservice per domain**. With a small team and a six-month launch target, they can be structured as modules with explicit contracts inside a unified deployable application, and split later when there is evidence of independent scaling, fault isolation, or team ownership needs.

### 5.2. Invariants to Uphold

1. **Never process one checkout request as two independent orders** when a user retries with the same idempotency key.
2. **A confirmed order** must be backed by a valid inventory reservation decision or an approved backorder rule.
3. **Never declare payment successful** solely because a browser redirect succeeded; rely on authoritative PSP state and reconciliation.
4. **Every critical state transition** has an event source, timestamp, actor, and cannot jump to an invalid state.
5. **No cross-customer or cross-store data leakage** across APIs, caches, queues, logs, and reports.

These constraints matter more than specific service names. A clean-looking diagram that fails to explain how these invariants hold is still an incomplete design.

### 5.3. System Context Diagram

~~~mermaid
flowchart LR
    Customer["Customers"] --> Shop["Cloud ordering platform"]
    Staff["Store staff"] --> Shop
    Ops["Operations / support"] --> Shop
    Shop <-->|"Reserve stock, check inventory"| ERP["On-premises ERP"]
    Shop <-->|"Payment intent, webhook"| PSP["Payment partner"]
    Shop --> Notify["Email/SMS service"]
~~~

The ERP and PSP sit outside the application's boundary of control. Document the **contract, timeouts, quotas, retries, authentication mechanism, incident ownership, and owner** for every integration.

## 6. Step 4 — Proposing and Comparing Options

Before deciding, the team should present at least two options capable of meeting the "Must" requirements. There is no need to list ten token architectures just to prove options were considered.

### Option A — Modular Monolith on Managed Compute

A single application API clearly divided into modules by domain; operated on a managed container or application platform with autoscaling and multi-AZ deployment. Transactional data lives in a managed relational database; cache/CDN serves read queries; asynchronous workers process events from a **transactional outbox** and queue. The system integrates with ERP/PSP via adapters.

**Pros:** simpler development, data consistency testing, and initial operations; fewer inter-service contracts; fits a small team and deadline. **Risks:** sharing one runtime/deployment can amplify faults, independent per-module scaling is harder, and module boundaries must be enforced to prevent coupling.

### Option B — Domain Microservices with Event-Driven Integration

Catalog, Orders, Inventory, and Payment are deployed independently, each owning its data; communication happens over APIs and a broker/queue; long-running business flows use sagas or state machines.

**Pros:** independent deployment and scaling per domain, suited to multiple autonomous teams. **Risks:** more versioned contracts, distributed data, duplicate/late events, higher observability and incident-debugging overhead; order confirmation flows become more complex. Event-driven **does not automatically provide** consistency or exactly-once delivery.

### Option C — Serverless Functions + Event-Driven Workflows

An API gateway invokes functions per feature; managed queues, a workflow engine, databases, and storage are used as appropriate. Suits short-lived tasks, bursty traffic, and minimal OS operational responsibility.

**Pros:** request-based scaling, pay-per-use resource billing, and heavy use of managed services. **Risks:** concurrency/quotas, cold starts where SLOs are strict, execution time limits, network integration to on-premises ERP, workflow testing/debugging complexity, and cost variability under traffic spikes.

These three options can be combined technically: for example, A can still use functions for standalone jobs; B still uses managed databases; C still needs a transactional state model. Options are distinguished primarily by **deployment boundaries and state management**, not technology logos.

### 6.1. Building a Trade-Off Matrix

Suppose the team agrees on weights driven by the need to launch quickly and preserve order correctness:

| Criterion | Weight | A: Modular | B: Microservices | C: Serverless |
|---|---:|---:|---:|---:|
| Reliability / resilience | 30% | 4 | 4 | 4 |
| Consistency and ease of reconciliation | 25% | 5 | 3 | 3 |
| Delivery speed with current team | 20% | 5 | 2 | 3 |
| Scalability | 15% | 3 | 5 | 4 |
| Cost and operational effort | 10% | 5 | 2 | 4 |
| **Weighted total (out of 5)** | **100%** | **4.40** | **3.30** | **3.55** |

The 1–5 scores and weights are **assumed evaluations for the exercise** and must be backed by POC data and team expertise. For example, 30% × 4 + 25% × 5 + 20% × 5 + 15% × 3 + 10% × 5 = **4.40** for A. If the enterprise has multiple platform-savvy teams requiring independent domain deployments, B's score could change. If the application handles large volumes of short asynchronous tasks, C might make more sense.

Weighted averages **do not permit ignoring gating constraints**: an option that fails to protect data invariants, security scope, or mandatory deadlines must be fixed or disqualified before scoring.

### 6.2. Sensitivity Analysis

Try shifting the weights or a key assumption:

- If we raise the priority of independent scaling and add 5 domain teams, does A still come out on top?
- If the PSP does not support idempotency, which options require changing the payment flow?
- If the system must achieve RTO under 5 minutes when an **entire region** goes down, how much do topology and data replication requirements increase?
- If the 90% cache hit rate drops to 40%, are origin and database capacity still sufficient?

A decision is persuasive when the team states clearly **what conditions would cause them to reverse it**.

## 7. Reference Solution — Choosing a Good-Enough Architecture to Ship

Suppose the team tentatively picks **Option A (modular monolith on managed compute)** because it must ship in six months with a small team, order transactions require strong consistency, and the input traffic numbers do not yet justify splitting into many services. Choosing A **does not mean** putting every function into one single process or dumping all data into a single unpartitioned schema without boundaries.

### 7.1. Container-Level Component Diagram

~~~mermaid
flowchart TB
    User["Customers / staff"] --> Edge["DNS + CDN + WAF"]
    Edge --> LB["L7 Load Balancer / API ingress"]
    subgraph Region["Primary cloud region"]
      subgraph App["Private compute, multiple Availability Zones"]
        API["Modular app: catalog, cart, checkout, orders"]
        Worker["Worker: outbox, fulfillment, webhook jobs"]
      end
      DB[("Managed relational DB - Multi-AZ")]
      Cache[("Managed cache / session store")]
      Q[("Durable queue / event broker")]
      Object[("Object storage: images, exports, backups")]
      Obs["Logs, metrics, traces, alerting"]
      LB --> API
      API --> DB
      API --> Cache
      API --> Object
      Worker --> DB
      Worker --> Q
      Q --> Worker
      API --> Obs
      Worker --> Obs
    end
    API <-->|"Private link/VPN via adapter"| ERP["On-premises ERP"]
    API <-->|"Authenticated API"| PSP["Payment PSP"]
    PSP -->|"Verified webhook at public endpoint"| LB
    Worker -->|"Send notifications"| Notify["Notification provider"]
~~~

This is a logical diagram, without picking a specific vendor or service SKU yet. In the physical design, you must add VPCs/subnets, routing, security groups/firewalls, multi-AZ load balancing, private connectivity to the ERP, egress, DNS, key management, backups, and a standby region if regional DR is approved.

| Layer | Choice in reference solution | Why |
|---|---|---|
| Edge/CDN | CDN + WAF, cache catalog/image content when safe | Reduces origin load; curbs malicious traffic and anomalous requests |
| Compute | Managed container/application service, at least multi-AZ | Small team, needs autoscaling and repeatable deployments |
| Database | Managed relational DB with multi-AZ HA and backup/PITR | Protects order state and transactional operations |
| Cache | Cache for read data and temporary sessions if needed | Reduces queries; cached data must never be the source of truth |
| Event/queue | Durable queue and outbox publisher | Decouples side tasks, prevents losing events after commit |
| Network | Controlled ingress, private app/DB, VPN or private link to ERP | Limits attack surface; manages latency and hybrid dependencies |
| Observability | SLI-aligned metrics, tracing, logs with correlation IDs | Enables tracing failed orders across API, DB, ERP, and PSP |
| Delivery | IaC, CI/CD, schema migrations, phased rollouts | Repeatable, supports software rollback and auditing |

A **cache hit** does not guarantee promotional pricing and inventory are always accurate. Catalog views may display cached prices up to a TTL, but checkout must validate pricing and apply active sales policies. Contention-sensitive inventory data must never be treated as accurate solely because it was just read from cache.

### 7.2. Network and Access Boundary Pattern

Public endpoints include CDN/ingress for customers and the PSP webhook. Application services do not need public IPs; the database, cache, and queue are accessed over private networking with least-privilege policies. Operator accounts authenticate through corporate identity with role-based permissions. Secrets and encryption keys live in a secrets/key management service, never in source code or images.

For the cloud → ERP link, specify **who initiates connections**, subnets, firewalls, DNS, encryption, authentication, connection limits, and failover paths. If the VPN fails, traffic must never fail over automatically to an unguarded public ERP endpoint. The design must preserve safe state: return "processing / inventory unconfirmed" per business contract rather than unconditionally confirming orders.

### 7.3. Designing Order States Before Writing APIs

A suggested state machine:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING_RESERVATION: Create request with idempotency key
    PENDING_RESERVATION --> RESERVED: ERP reserve succeeds
    PENDING_RESERVATION --> REJECTED: Out of stock / cannot reserve
    RESERVED --> PAYMENT_PENDING: Create payment intent
    PAYMENT_PENDING --> PAID: Valid PSP signal received
    PAYMENT_PENDING --> CANCELLED: Cancelled / expired
    PAID --> CONFIRMED: Verify reservation still valid
    PAID --> COMPENSATION_REQUIRED: Reservation expired / unexpected error
    COMPENSATION_REQUIRED --> REFUNDED: Void/refund reconciled
    CONFIRMED --> FULFILLING: Routed to store
    FULFILLING --> COMPLETED: Delivered / picked up
    REJECTED --> [*]
    CANCELLED --> [*]
    REFUNDED --> [*]
    COMPLETED --> [*]
~~~

This diagram illustrates **one** business policy. The business must decide when an order is considered "confirmed" to the customer, whether funds are *authorized* before *capture*, and how long inventory reservations last. If the PSP supports separate authorization/capture, you can verify stock and capture only once all conditions are guaranteed. If the PSP only supports immediate charge, prepare a void/refund and reconciliation path whenever a downstream step fails.

**Common pitfall:** never conclude "payment success" solely from a browser redirect page. Verify signed webhooks or query transaction status via the PSP API; webhooks can be duplicated, delayed, or arrive out of order. Idempotency must cover **both the application side and any PSP calls that support it**.

### 7.4. A Verifiable Checkout Sequence

~~~mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant A as API / Orders
    participant D as Order DB
    participant E as ERP
    participant P as PSP
    participant W as Outbox worker
    C->>A: POST checkout + idempotency key
    A->>D: Create / read PENDING_RESERVATION (unique key)
    A->>E: Reserve(orderId, items, TTL)
    alt ERP rejects / times out
      A->>D: Record rejection or pending lookup state
      A-->>C: Unconfirmed, do not assume success
    else Reservation succeeds
      A->>D: Record RESERVED
      A->>P: Create payment intent (idempotent)
      P-->>A: Payment reference
      A-->>C: Payment instructions with payment reference
      P->>A: Status webhook (may repeat)
      A->>P: Verify when needed
      A->>D: Transaction: order state + outbox event
      D-->>W: Read pending outbox
      W->>W: Publish with retry / dedupe
    end
~~~

In practice, the webhook receiver is logically separated from customer-facing request endpoints/workers; the diagram merges them into the API box to show responsibility. Verifying that the reservation is still valid and handling refund/void when stock is no longer available must be part of the state machine, never skipped just because the payment call returned success.

**Consistency:** update the order state and insert the outbox event within **the same Order DB transaction**. The worker may replay an event if it crashes after publishing but before marking it sent; consumers must be idempotent on `eventId`. A transactional outbox narrows the "order committed but event dropped" window, though it does not guarantee end-to-end exactly-once semantics from ERP to PSP.

### 7.5. Failure Handling Across Every Boundary

| Failure | Desired behavior | Verification signal |
|---|---|---|
| User resubmits checkout | Return same state/orderId for same active idempotency key | Never two orders from one key |
| ERP times out after reserving stock | Look up reservation by stable key; do not blindly create new ones | No duplicate holds; timeouts clearly classified |
| PSP sends duplicate webhooks | One valid state transition, one financial impact | Deduplicate by event and payment reference |
| PSP captures funds, order unconfirmed | Route to reconciliation/compensation queue, alert | Stuck transactions have an owner and resolution SLA |
| DB primary failover | In-flight requests can retry safely | No lost consistency or duplicate orders |
| Queue temporarily unavailable | Outbox retains committed events; worker retries | Backlog measured, alerted, and drained |
| Cache outage | Fall back to DB within budgeted limits without corrupting prices | Test cache outage and protect DB from thundering herds |
| Entire region outage | Execute approved DR plan | Measured RTO/RPO and post-recovery reconciliation |

**No response** is a meaningful state. For external dependencies, a timeout does not prove the business operation failed. The ERP might have reserved inventory or the PSP might have captured payment right before the connection dropped. Always **query by a durable transaction key and reconcile** before retrying.

## 8. Step 5 — Estimating Capacity from Workload, Not Gut Feel

Estimates initialize the design and POC plan; final sizing must come from benchmarks using realistic data, endpoints, and latencies.

### 8.1. Separating CDN Load from Origin Load

Assuming **1,200 requests/second** of catalog browsing and a **90% cache hit ratio**, read traffic reaching the origin becomes:

\[
1\,200 \times (1-0.90)=120\ \text{requests/second}.
\]

Combined with **60 checkout attempts/second**, we get roughly **180 requests/second for these two flows**. This is **not the whole system**: login, cart, search, payment webhooks, fulfillment, background jobs, and uncacheable catalog requests also add load.

Suppose an initial load test proves one API replica handles **75 requests/second at the representative request mix** while meeting SLOs. If we target operating at most around **70% of measured capacity** for headroom, one replica supports:

\[
75 \times 0.70 = 52.5\ \text{requests/second}.
\]

If deployed with **6 replicas spread evenly across 3 Availability Zones**, losing 1 AZ leaves 4 replicas, giving an assumed capacity of:

\[
4\times52.5=210\ \text{requests/second} > 180.
\]

This example only shows **how to check one scenario**, not proof that the system meets its SLO. Checkout processing is typically heavier than catalog queries; load tests must reflect the actual mix, external APIs, database, connection pools, cache misses, and queues. If 75 requests/second was measured only with lightweight GETs, the math above is **invalid**.

### 8.2. Estimating Order Data Volume

At an average of **45,000 orders/day**, assuming each order plus its line items and metadata totals **3 KB of raw data**:

\[
45\,000\times3\,000=135\,000\,000\ \text{bytes/day}
\]

which equals about **135 MB/day** and **49.3 GB/year** of raw data (decimal units, 365 days). Actual storage is higher once indexes, MVCC/overhead, replication, transaction logs, backups, audit records, data growth, and integration tables are included. The enterprise should separate hot operational data from historical data per retention policies and audit requirements.

### 8.3. Cache Hit Sensitivity Analysis

| CDN cache hit | Catalog origin RPS at 1,200 edge RPS | Multiple vs. 90% baseline |
|---|---:|---:|
| 90% | 120 | Baseline assumption |
| 75% | 300 | 2.5x |
| 50% | 600 | 5x |
| 0% | 1,200 | 10x |

Therefore, cache hit ratio is a **high-impact assumption**. Test across products, regional pricing, cookies, access permissions, TTLs, invalidation, and promotional-hour behavior. Avoid leaking personal data across users due to improper cache keys.

### 8.4. Capacity of Off-Cloud Dependencies

The API sustaining 60 checkout attempts/second **does not mean** the ERP sustains 60 reservations/s or the PSP sustains 60 intents/s. Measure:

- API throughput/quotas, connection pools, timeouts, p95/p99 latency, and ERP/PSP error rates.
- Queue growth rate when a dependency slows down; backlog drain time after recovery.
- Database connection count, transaction duration, lock contention, and CPU/IO.
- Price/inventory update frequency and stale-cache risk.

The design needs rate limits, circuit breakers, backpressure, and business-appropriate **degraded modes**. If inventory cannot be checked/reserved, customers may save carts or join a waitlist, but **stock must not be confirmed** unless policy permits it.

## 9. Step 6 — Designing for Failure, Security, and Operations

A convincing architecture must explain **how the system behaves when conditions are no longer ideal**, not just describe the happy path.

### 9.1. Fault Boundaries and Recovery Targets

| Incident | Design mechanism | What must be proven |
|---|---|---|
| Single app instance loss | Health checks, autoscale/restart, idempotent request retries | No committed state lost |
| Availability Zone loss | LB routes to remaining AZs; compute and DB have HA | Remaining capacity suffices, DB fails over cleanly, no duplicate orders |
| Logical DB corruption or accidental delete | PITR, verified backups, separation of privileges | Data restored to target point and reconciled |
| Queue/worker stall | Durable queue/outbox, age/backlog monitoring, bounded retries | Committed tasks are not "lost" despite processing delays |
| ERP connectivity loss | Timeouts, circuit breaker, queue or reject confirmation per policy | No overselling, no unbounded hung requests |
| PSP outage | Display clear pending state, reconcile later | No double charging, clear path for stuck transactions |
| Full cloud region outage | DR to another region per approved plan | Achieves RTO/RPO if that requirement is truly mandatory |

**Multi-AZ is not multi-region.** A multi-AZ HA relational database protects against many intra-region failures, but does not by itself satisfy a 60-minute RTO / 5-minute RPO when an **entire region** fails. If Q-05 is approved as mandatory at launch, the design must also include:

- Asynchronous data replication to a standby region with replication lag monitoring and clear write ownership.
- Infrastructure, config, secrets, network dependencies, and deployable images ready to start/run in the standby region—not just database backups.
- DNS/traffic failover, handling of in-flight transactions, and post-failover reconciliation with PSP/ERP.
- DR drills measuring **actual service recovery time** and **actual recovered data point**; if targets are missed, invest more or renegotiate targets.

Asynchronous replicas can lose the most recent records if the primary region fails before replication completes. For orders and payments, the DR plan must state how missing transactions are detected and recovered from immutable logs, the PSP, and the ERP. **Never claim RPO = 0** merely because replication is enabled.

**RTO/RPO should be broken down by incident tier:** pod restarts, intra-AZ/region failover, full region loss, logical data corruption, and vendor outages are distinct scenarios. Each tier carries its own mechanism and cost.

### 9.2. Reliability of Dependency Chains

Checkout may depend simultaneously on the API, database, ERP, and PSP. If every dependency must be up simultaneously, the availability of the business flow is typically **lower than any individual component**. You cannot infer 99.95% checkout availability simply from a 99.99% compute SLA.

In practice, build a **dependency map** and measure error rates, timeouts, and latencies per call path; negotiate integration SLAs or design acceptable pending states. If "immediate order confirmation" cannot be met when the ERP is offline, the business owner must decide whether to support **queued orders, backorders, or pausing checkout**.

### 9.3. Security Along Data Flows

Label on the diagram: PII, payment tokens, public data, order data, staff accounts, secrets, and audit logs.

| Surface | Baseline controls | Verification method |
|---|---|---|
| Customer → API | TLS, appropriate auth, rate limiting, input validation, WAF | Scoped pen test, API abuse and bot testing |
| Staff → Admin | SSO/MFA, RBAC/ABAC, least privilege, session policies | Cross-store access tests and action audits |
| App → DB/cache/queue | Private network, workload identity, least privilege | Network policy/IAM review, denied-access testing |
| App → PSP/ERP | TLS/mTLS or agreed mechanism, webhook signatures, secret rotation | Spoofed webhook and timeout/retry tests |
| Data at rest | Encryption at rest, key policies, lifecycle, backup and restore | Read-access, restore, and policy-based deletion tests |
| CI/CD & supply chain | Deployment RBAC, dependency/image scanning, artifact provenance | Pipeline testing, production change-privilege audit |
| Observability | Redact sensitive data from logs, dashboard permissions, retention | Request/error log review and access workflow checks |

Do not store raw card data or adopt integration methods that expand card-data compliance scope without proper assessment. Accept only payment tokens/references from the PSP and scope compliance based on the actual integration pattern.

When storing customer data in caches or report exports, bind cache keys to user scope and enforce authorization by authenticated subject to prevent **IDOR** (Insecure Direct Object Reference) or returning another user's data due to missing API-layer checks.

### 9.4. Business-Aligned Observability

For each order, events across frontend, API, ERP adapter, PSP callbacks, database, and workers must link via a **correlation ID** and appropriate transaction references, without logging secrets or card data.

Recommended dashboards:

- **Business SLIs:** checkout success rate as defined, prolonged pending order rate, transactions needing reconciliation, out-of-stock cancellation rate.
- **Customer experience:** p95/p99 latency, errors by browser/device/region, Core Web Vitals where relevant, dropped requests.
- **Dependencies:** ERP/PSP latency, timeouts, quotas, retries, circuit breaker state.
- **Data/async:** DB connection pool, lock time, replication lag, outbox age, queue depth, dead-letter count.
- **Operations:** error budget burn, deployment rollbacks, mean time to recover, backup/restore pass count.

Alerts must link to **a runbook and an owner**. For instance, "count of PAID orders not CONFIRMED exceeding threshold for 10 minutes" matters more than a CPU occasionally hitting 80% with no service impact.

### 9.5. Deployment and Change Practices

Suggested pipeline: **commit → tests → image build → vulnerability scan → staging deploy → smoke/integration → canary/rolling production → measure SLIs → complete or rollback**. Use IaC for networking, compute, permissions, and config; manage secrets separately and never commit them to Git.

For database schemas, prefer **expand-and-contract migrations** so old and new application versions can run concurrently during a rollout window. Code rollbacks **do not automatically roll back mutated data** or PSP transactions; have forward-fix, reconciliation, and recovery plans ready.

## 10. Step 7 — Estimating Cost and Organizing Delivery

Costs should be compared on **total cost of ownership** across at least normal, peak, and failure scenarios, rather than comparing the price of one container against one function.

### 10.1. Variable-Driven Cost Estimation Table

| Component | Units to collect | Cost drivers |
|---|---|---|
| Compute | Replicas × hours × instance size; scaling volume | Traffic peaks, multi-AZ HA, minimum idle floor |
| Database | Nodes/CPU/RAM, storage, I/O, backups, replicas | Transactions, indexes, long retention, DR |
| Cache | Node count, RAM, HA setup | SKU cardinality, sessions, cache invalidation |
| Queue/stream | Requests, throughput, retention, data transfer | Retry storms, replays, consumer count |
| CDN/WAF/API | Requests, bandwidth/egress, rules, logs | Cache misses, bots, campaign traffic |
| Hybrid networking | VPN/private link, egress, redundant bandwidth | ERP traffic, connection counts, latency |
| Observability | Log GB, metric/time-series count, trace sampling | Cardinality, debug logging, retention |
| DR and backups | Secondary-region replicas, snapshot storage, failover tests | Strict RTO/RPO, drill frequency |
| Staffing and tooling | On-call, maintenance, development, security reviews | Runtime/service sprawl, manual ops, technical debt |

For instance, adding a standby region to meet Q-05 is **a deliberate cost decision**, not something to hide under "reliability." Conversely, cutting costs by running a single production replica may violate the single-AZ fault tolerance requirement.

Trade-off questions to raise:

1. What percentage of catalog traffic can be offloaded from origin via CDN/cache?
2. Can historical data be tiered to object storage instead of keeping everything in the OLTP DB?
3. Does the extra cost of strict regional RTO/RPO match the estimated business impact of downtime?
4. Does the team have the skill to operate multiple microservices, service meshes, and self-hosted brokers, or should we buy managed capabilities?
5. Are budget alerts, quotas, tagging, and cost allocation by environment/feature group in place?

Do not cite a specific dollar figure without **the region, configuration, current service pricing, taxes, discounts, and traffic model**. For real estimates, document pricing sources, calculation dates, and high/low bounds so they can be audited.

### 10.2. Phased Delivery Plan

| Phase | Verifiable deliverables | Exit criteria |
|---|---|---|
| **Discovery** | NFRs, data classification, ERP/PSP contracts, assumption register | High-impact assumptions have owners and test plans |
| **Architecture spike** | Test reservation/idempotency, DB/API benchmarks, DR cost estimate | Correctness and hardest assumptions proven |
| **Foundation** | Network, IAM, secrets, IaC, CI/CD, logs/metrics, backups | Security baseline and restore tested |
| **Vertical slice** | One end-to-end checkout journey on staging | Payment, inventory, order, and tracing reconciled |
| **Hardening** | Load, failover, security, chaos/DR drills per scope | Approved SLO/SLIs met; runbooks and on-call ready |
| **Launch & observe** | Canary rollout, business dashboards, hypercare | Go/No-Go checklist and stuck-transaction handling operational |

Phases may overlap; avoid pushing all reliability and security tests to the end of the project. For example, discovering in month five that the ERP lacks idempotent reservations will alter the state machine and acceptance scope.

## 11. Step 8 — Writing Architecture Decision Records (ADRs)

A concise ADR helps others understand **why the current architecture looks the way it does** and when it should be revisited. Template:

~~~text
ADR-ID:
Title:
Status: Proposed / Accepted / Superseded
Date and approver:
Context and related requirements:
Unvalidated assumptions:
Options considered:
Decision:
Rationale and evidence:
Positive / negative consequences:
Verification method:
Conditions for revisiting:
~~~

### ADR-001 — Choose a Modular Monolith for the Initial Launch

**Status:** Proposed, awaiting confirmation from product/engineering owner.

**Context:** team of 8 developers, 2 infrastructure engineers, six-month deadline; checkout requires strong consistency and rapid fault investigation.

**Options:** A — modular monolith with outbox and queue; B — domain microservices; C — serverless functions + workflows.

**Proposed decision:** choose A, deployed on multi-AZ managed compute, managed relational DB, cache/CDN, and async workers for post-commit work.

**Rationale:** fits team skills and timeline, minimizes cross-service transactions; reference matrix scores A = 4.40; requires a POC to verify peak capacity.

**Consequences:** modules share a release schedule and runtime blast radius; must enforce module boundaries, interface tests, domain-level metrics, and avoid direct cross-domain DB table access unless justified.

**Verification:** load test with realistic request mix, simulate one AZ failure, measure business change lead time and deploy velocity; review coupling regularly.

**Revisit when:** independent domain delivery teams form, release cycles conflict frequently, or a module develops a load/fault-isolation profile that the current setup cannot meet cost-effectively.

### ADR-002 — Share One Transaction Between Orders and Outbox

**Status:** Proposed, awaiting confirmation from data/operations owner.

**Context:** after confirming an order state, fulfillment and notifications must be triggered. Updating the DB successfully while failing to publish the event risks dropped work.

**Options:** (1) write DB then publish directly; (2) single transaction for order state + outbox, worker publishes with retries; (3) distributed transactions across resources.

**Proposed decision:** choose (2). Consumers process idempotently since events may be replayed.

**Consequences:** adds an outbox table, worker, backlog age monitoring, and cleanup jobs; in return, eliminates the dual-write gap on the main commit path. Never treat a queue ack as full business completion.

**Revisit when:** the platform provides a proven, efficient atomic commit mechanism, or throughput/latency needs shift substantially.

### ADR-003 — Full-Region Outage Recovery

**Status:** Pending business decision.

**Context:** the prompt proposes **RTO ≤ 60 minutes, RPO ≤ 5 minutes** for a full region loss, without approved budget or data-loss risk tolerance yet.

**Two options to present for approval:**

- **Meet immediately:** warm standby/replicated data in a secondary region, failover routing, order/PSP state reconciliation, and regular drills. Higher cost and operational load.
- **Phase in later:** initially focus on multi-AZ HA, backups/PITR, and restore procedures; accept a different regional DR target or post-launch DR completion **only if the business owner approves the requirement change**.

**Decision drivers:** business impact analysis, data residency limits, provider evaluation, and DR POC results. Do not mark Q-05 as "met" when only multi-AZ backups exist.

### ADR-004 — ERP as Inventory Source of Truth in Phase One

**Status:** Proposed, depends on A-02.

**Context:** the new system does not replace the ERP; inventory is shared across multiple sales channels. Copying quantities to the cloud for display can tolerate lag, but confirming a sale requires an anti-oversell mechanism.

**Proposed decision:** keep ERP as source of truth; use read replicas for display, while checkout requires a reservation/commit following an ERP-confirmed protocol. Reject confirmation or enter pending state without valid reservation proof.

**Consequences:** checkout availability depends on ERP/WAN health; requires measurement plus policies for waiting, timeouts, reconciliation, stale data, and incident channels. If the ERP lacks idempotent reservations, this is an **architectural blocker** requiring business and technical alternatives.

## 12. Step 9 — Verifying the Design with Scenarios

Do not review diagrams on opinion alone. Every major decision must have tests, thresholds, owners, and evidence.

| Area | Verification scenario | Expected outcome |
|---|---|---|
| **Functional** | Successful order, out-of-stock, cancel, PSP refund, order lookup | States and totals match business contract |
| **Idempotency** | Submit same checkout key 100 times, duplicate/out-of-order webhooks | No duplicate orders or charges from retries |
| **Load** | Burst of 60 checkout attempts/s for 5 minutes alongside read traffic | p95, error rate, and throughput meet approved thresholds |
| **Cache** | CDN hit drops from 90% to 50%, cache outage | No data leaks, origin protected, degradation observed |
| **ERP** | Timeout after reserve, ERP 429/503, VPN drop | Correct lookup/reconciliation, no false stock confirmation |
| **PSP** | Payment succeeds but webhook delayed, lost, or duplicated | Pending orders reconciled/resolved, no duplicate charge calls |
| **Database** | Primary failover mid-transaction and while outbox worker runs | Durable writes, safe retries, no lost committed events |
| **Availability Zone** | Loss of one AZ under peak load | Remaining capacity and DB failover meet targets |
| **Region DR** | Simulate full region loss, restore service and reconcile | Measured RTO/RPO meets approved requirements |
| **Security** | Cross-account/cross-store access, forged webhook, secret exposure | Rejected and audited per policy |
| **Operations** | Failed canary, code rollback, incompatible schema migration | Recoverable without corrupting transactional data |
| **Cost** | Normal/peak load, log spikes, replication/egress | Budgets, quotas, and cost alerts trigger properly |

### 12.1. Sample Verification Record for One Scenario

~~~yaml
scenarioId: LOAD-CHECKOUT-01
requirementRefs: [Q-03, Q-04]
assumptionRefs: [A-01, A-02, A-03]
environment: staging-representative
load:
  checkoutAttemptsPerSecond: 60
  burstDurationMinutes: 5
  catalogRequestsPerSecond: 1200
acceptance:
  checkoutApiP95Ms: 800
  businessInvariants: "No duplicate orders or charges"
  dependencyErrors: "Within separately approved thresholds"
evidence:
  dashboard: "Add link after test session"
  traceSamples: "Add link after test session"
owner: performance-lead
status: NOT_RUN
~~~

The YAML file above is an **illustrative template** for recording test evidence, not a system configuration or completed test result. In a real project, add PASS/FAIL status with timestamp, deployed version, test dataset, and error rate thresholds; leave `NOT_RUN` until executed.

### 12.2. Lightweight ATAM-Style Critique

Pick three conflicting **quality attribute scenarios**:

1. **Cost reduction vs. reliability:** the business requires surviving a single-AZ failure without losing checkout. What happens if we cut replicas to one and drop DB HA?
2. **Launch speed vs. service decomposition:** what does splitting Payment/Orders immediately gain, and what extra contracts, tracing, state machines, and chaos testing does it demand?
3. **Consistency vs. availability when ERP is offline:** can the business accept queued/backorder orders, or must order confirmation stop?

Each group presents a **sensitivity point** (a parameter that alters the design, such as cache hit ratio), a **trade-off point** (a decision affecting multiple attributes, such as multi-region replication), and an unvalidated **risk**.

## 13. Well-Architected Evaluation

This is a review of **a concrete option** once the team has produced a design and risk register.

| Pillar | Challenge questions | Expected evidence |
|---|---|---|
| **Operational Excellence** | Can we deploy, observe, troubleshoot, and recover without relying on one individual? | IaC, pipelines, runbooks, on-call, tracing, health checks |
| **Reliability** | How does each business flow behave when a node, AZ, DB, queue, ERP, or region fails? | Failure matrix, RTO/RPO drills, idempotency, and reconciliation |
| **Security** | Who can access which data, how are secrets protected, and are all actions auditable? | IAM/RBAC, data classification, encryption, flow reviews, pen tests |
| **Performance Efficiency** | Are p95/throughput and scaling based on measured workloads? | Workload model, load tests, bottlenecks, capacity/headroom |
| **Cost Optimization** | Are normal/peak/DR costs predictable and attributable? | TCO table, tagging, quotas, budget alerts, sensitivity scenarios |
| **Sustainability** | Have idle resources, data transfer, retention, and redundant workloads been reviewed? | Autoscaling, lifecycle policies, cache ratios, storage tiering |

Do not mark PASS merely because a cloud service "supports" a feature. For example, **provider support for multi-AZ** differs from an application actually being configured, failover-tested, and verified. For items without evidence yet, log an **Open risk** with an owner and validation deadline.

### 13.1. Sample Risk Register for Reviews

| Risk | Impact | Mitigation | Owner / timing |
|---|---|---|---|
| ERP lacks idempotent reserves | Duplicate holds, overselling, hard-to-recover transactions | Spike + API contract + reconciliation workflow | ERP owner / before design freeze |
| Actual cache hit lower than expected | Origin overload, higher costs | Realistic traffic POC, origin scaling, cache strategy | Web lead / before load test |
| PSP webhooks delayed or lost | Paid orders left unprocessed | Verification, reconciliation, pending state, and alerts | Payment lead / before pilot |
| Regional failover exceeds RTO/RPO | Lost transactions or missed recovery SLA | DR architecture + drills; sign off on residual risk | SRE & business owner / before go-live |
| Team struggles to operate platform | Prolonged outages, slow releases | Pick managed services, on-call rehearsals, runbooks | Engineering manager / during pilot |

## 14. Hands-On Exercise for Learners

Take the role of an architect presenting to a panel consisting of a product owner, data engineer, security, SRE, and store operations representative. You do not need to pick a vendor before the design session. Submit:

1. **One-page context:** goals, stakeholders, scope, and three critical business journeys.
2. **Table of at least eight requirements:** including at least four measurable NFRs, priorities, owners, and acceptance criteria.
3. **Assumption register with at least five items:** flag assumptions needing an early spike and the impact if wrong.
4. **Two architectural options** with diagrams, data flow descriptions, and behavior when the ERP or PSP loses connectivity.
5. **Comparison matrix and three ADRs:** at least one ADR still pending due to missing evidence or business decisions.
6. **Verification plan:** load testing, single-AZ failure, duplicate data, and access control; specify PASS/FAIL observations.
7. **A scenario change:** the business owner announces checkout must keep accepting orders during a 45-minute ERP WAN outage. Explain how **oversell/backorder rules, reservations, order states, or availability requirements** must change; do not assume a queue alone solves consistency.

### 14.1. 100-Point Grading Rubric

| Category | Points | Characteristics of a strong submission |
|---|---:|---|
| Understanding business, boundaries, and stakeholders | 15 | Clear value streams, scope, and integration ownership |
| Measurable requirements and priorities | 15 | SLIs/acceptance have metrics and approval sources |
| Assumptions, dependencies, and risks | 15 | Key unknowns identified with tests/owners |
| Option comparison and decisions | 20 | At least two viable options, trade-offs, and justified ADRs |
| Data, transactions, and security | 15 | Addresses idempotency, inventory, PSP, permissions, and data boundaries |
| Reliability, performance, cost, operations | 10 | Capacity, DR, and cost estimates have explicit limits |
| Verification plan and defensibility | 10 | Tests have pass/fail criteria; knows when to change the design |
| **Total** | **100** | |

A submission packed with managed services that cannot prove order state correctness or identify **who accepts the risk** has not met the exercise objective.

### 14.2. Advanced Questions

- If launch day hits **10,000 catalog browsing requests/s** while checkout grows only slightly, must Orders be split into a microservice? Or should cache, CDN, static content, and the database read path be optimized first?
- If the business expands to two countries with differing data residency laws, how do account/region structure, key management, tenancy, and data flows change?
- If stores are allowed to accept **capped backorders**, how must the state machine and return/refund SLAs change?
- If three new product teams join in year one, does ADR-001 still hold? Name at least two operational signals that warrant considering domain extraction.
- If **RPO = 0 for confirmed orders** is required during a region outage, how must data replication choices, latency, cost, and disconnect behavior be discussed?

## 15. Common Pitfalls When Designing from Scratch

**Picking technology before knowing requirements:** leads to over-engineering or missed business invariants. Write quality scenarios, constraints, and data flows before comparing product names.

**Treating assumptions as facts:** "the ERP definitely supports retries" breaks checkout during network drops. Record sources, owners, tests, and validation deadlines.

**Comparing options with generic bullet points:** "microservices scale easily" is not enough; answer which module needs independent scaling, deployment frequency, team capacity, and observability cost.

**Calling managed services an SLO guarantee:** a single component's SLA does not represent the checkout flow across DB, ERP, and PSP. Test end-to-end journeys under real faults.

**Forgetting data and external side effects:** code rollbacks do not refund captured money; missing a webhook does not mean the PSP did not charge. Design idempotency and reconciliation upfront.

**Ignoring intermediate states:** pending payment, ERP timeout after reserve, and unpublished outbox rows are all valid states that must be modeled.

**Estimating cost from a single average number:** ignores campaign spikes, bandwidth, replica storage, logs, DR, and on-call staffing. Always model normal, peak, and incident scenarios.

**Not knowing when a decision should change:** ADRs must state assumptions, consequences, and revisit triggers, not just "decided to use X."

## 16. Pre-Review Checklist

- [ ] Business goals, owners, scope, and system context diagram are documented.
- [ ] Measurable requirements/NFRs exist, distinguishing approved items from proposals.
- [ ] Unvalidated assumptions, impacts, owners, and validation plans are listed.
- [ ] At least two valid options and a trade-off matrix with gating criteria are included.
- [ ] Data flows, sources of truth, consistency, and dependency-failure states are described.
- [ ] Network/trust boundaries, permissions, encryption, secrets, residency, and data lifecycle are mapped.
- [ ] Requests, capacity, database, cache misses, queues, and integration quotas are estimated.
- [ ] Node/AZ/region failure scenarios, RTO/RPO, and matching recovery evidence are defined.
- [ ] Cost estimates cover workload, DR options, observability, and operations.
- [ ] ADRs explain choices, rejected options, consequences, and revisit conditions.
- [ ] Load/failure/security/DR test plans include PASS/FAIL criteria and owners.
- [ ] Open risks list and Go/No-Go mechanism exist prior to production launch.

**Key takeaway of the exercise:** good cloud architecture is a traceable chain of reasoning from **requirements → assumptions → options → decisions → verification evidence**. When business needs, data, team capacity, or costs change, the design can be adjusted transparently while preserving the system's critical invariants.
