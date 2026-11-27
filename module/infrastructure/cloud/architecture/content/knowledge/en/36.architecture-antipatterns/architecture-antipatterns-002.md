# Splitting microservices without clear business boundaries

## 1. What is this antipattern?

In **cloud application architecture** design, microservices enable components to be developed, deployed, and scaled relatively independently. However, **splitting microservices without clear business boundaries** is an architectural antipattern: the development team splits an application into separately deployed services before knowing which business rules, data, and changes each service owns.

The result is often a **distributed monolith**: the diagram shows many services, yet a small change requires modifying and deploying multiple places simultaneously. The system takes on network overhead, latency, partial failures, inter-service authentication, and distributed monitoring without gaining meaningful independence.

**Example:** an e-commerce application runs stably in a single process. The team splits it into CustomerService, CartService, OrderLineService, PriceService, CouponService, and OrderService because “each table gets a service.” Every time a customer places an order, OrderService must sequentially call multiple services to read info, calculate prices, apply coupons, and write the order. Every change to discount rules forces simultaneous edits to PriceService, CouponService, and OrderService. This decomposition can make the system less reliable and harder to change than the original monolith.

> **Key idea:** A service boundary should reflect a business capability with relatively clear responsibilities, data, and rules. The number of services or containers is not a measure of architectural maturity.

The antipattern lies in the **timing and criteria for splitting**, not in microservices themselves. There are many cases where splitting early is justified, such as security isolation requirements, vastly different load profiles, or stable business domains with clear owning teams. The decision must rest on evidence from the specific system.

## 2. Why do business boundaries matter?

In Domain-Driven Design (DDD), a **bounded context** is the scope within which terminology, models, and business rules carry a consistent meaning. For instance, a “product” in catalog management is display content, whereas an “item” in a confirmed order is a snapshot of details and price at purchase time. Trying to share a single Product model everywhere can force components to change together whenever pricing logic or display changes.

Three concepts should be distinguished:

| Concept | Question it answers | Note |
|---|---|---|
| **Business capability** | What does the organization need to do, such as taking orders or processing payments? | Starting point for understanding responsibilities and value |
| **Bounded context** | Within what scope do models, terms, states, and rules have consistent meaning? | Helps identify where a rule is owned |
| **Service boundary** | Which software unit needs independent operation, deployment, and data ownership? | A technical decision; does not have to map 1:1 to a bounded context |

A large bounded context can be implemented with multiple modules inside one application. A microservice can serve a scope smaller than a bounded context when there is a clear reason. DDD should not be treated as a formula where “every noun or every table = one microservice.”

### 2.1. Questions that reveal boundaries

Before drawing a new service, ask:

1. **What business capability is provided?** Names like Order, Payment, and Inventory are usually more useful than purely technical names like Validation or DatabaseWrapper, though they still require real validation.
2. **Which rules and invariants must hold true?** For example, the total on a confirmed order must not change just because list prices change.
3. **Who decides changes to the rules?** Which business owner, product group, or operations team approves changes?
4. **Which data does this scope own?** Who may write, and who may only read via a contract or query replica?
5. **Which operations require immediate consistency?** Which parts can update asynchronously, accepting intermediate states?
6. **Do changes tend to happen together or independently?** If two “services” always change together, the current boundary may be misplaced.
7. **Who directly builds and operates it?** Service boundaries must match team ownership, on-call capacity, and autonomy.

Unclear answers are a signal to keep exploring the domain and keep components as modules rather than immediately creating another independent deployment.

## 3. Common flawed ways to split

| Flawed or incomplete split criterion | Example | Why it tends to cause problems |
|---|---|---|
| **By database table** | UserService, AddressService, OrderRowService | One business transaction must call multiple services; rule ownership is unclear |
| **By CRUD** | CreateOrderService, UpdateOrderService, GetOrderService | Operations on the same lifecycle are scattered, increasing coupling and making invariants hard to uphold |
| **By technical layer** | ValidationService, RepositoryService, MappingService | Every request crosses multiple network hops just to complete a local task |
| **By UI screen** | CartPageService, CheckoutPageService | UI changes frequently; data models and business rules get twisted around screens |
| **By headcount or current team count** | Each team gets an arbitrary service | When business flows cross team boundaries, constant coordination is required |
| **By desire to use new technology** | Splitting a service solely to run another framework | Adds deployment overhead without solving a business need |
| **By codebase size** | One 1,000-line package = one service | Line count does not measure cohesion or coupling |

These criteria are not always wrong: an independent query service or a tech-specific component can make sense with distinct load, permissions, SLAs, or deployment needs. The mistake is using technical criteria as the **sole basis** without examining business flows and data ownership.

## 4. How a distributed monolith emerges

### 4.1. Sequential synchronous calls (chatty communication)

Suppose an order request must call 7 services in sequence. Each call adds network transit, serialization/encryption, authentication, resource contention, and timeout risk. When one service slows down or fails, the entire flow is easily dragged down.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as OrderService
    participant P as PriceService
    participant D as DiscountService
    participant I as InventoryService
    participant L as OrderLineService
    participant X as Shared DB
    C->>O: POST /checkout
    O->>P: Calculate price per product
    P->>X: Read price table
    P-->>O: Price
    O->>D: Calculate promotion
    D->>X: Read discount rules
    D-->>O: Discount
    O->>I: Check inventory
    I->>X: Read stock
    I-->>O: In stock
    O->>L: Write each order line
    L->>X: INSERT
    L-->>O: OK
    O-->>C: Completed
~~~

This diagram illustrates an unhealthy decomposition: many synchronous calls on the critical path and services reading/writing a shared database. It does not claim every design with a Price or Discount service is wrong; independence, contracts, and real latency must be evaluated.

For a chain of calls that **must all succeed together**, overall chain success probability drops as dependencies are added. If five components each have an independent 99.9% success probability over a measurement window, the theoretical probability of all five succeeding together is roughly \(0.999^5 \approx 99.5\%\). This is only an illustration: real systems experience correlated failures, retries, caching, and graceful degradation, so this multiplication cannot replace actual SLO measurement.

### 4.2. Shared data and multiple writers

A classic mistake is splitting into 6 services while still letting all of them directly access the Order, Product, or Payment tables. When a schema changes, every service can be affected. Table locks, slow queries, or data migrations still ripple across the entire system.

**Data ownership** does not necessarily mean each service must have its own dedicated DB server. During a transition phase, they can share a DB engine while separating schemas, permissions, and write paths. What matters is that each piece of data has one business owner and other components access it via controlled contracts rather than arbitrarily modifying each other's tables.

### 4.3. Unintentionally creating distributed transactions

In a monolith, certain invariants can be protected within a local transaction. When split across services, updating Order, Inventory, and Payment simultaneously crosses transaction boundaries. You cannot assume calling three APIs yields atomicity.

Solutions may involve narrowing transaction scope, using reservations, events, and workflows with compensation. However, these introduce state, idempotency, retries, and partial-failure handling. Without understanding business rules, it is hard to know when compensation is allowed and what constitutes a valid outcome.

### 4.4. Synchronized deployments and long coordination loops

A service having its own CI/CD pipeline does not mean independent deployment. If renaming one attribute requires editing five services together, synchronizing API versions, and releasing within a single maintenance window, the organization has merely moved coupling from compile time to runtime.

### 4.5. Harder observability and security

When one transaction traverses many services, operations teams must manage cross-service traces, correlation IDs, retry storms, circuit breakers, secrets, mTLS/TLS, IAM, network policies, rate limits, and configuration. These requirements are worthwhile when boundaries fit; they become wasted overhead when services are split arbitrarily.

## 5. Symptoms in a running system

| Observed symptom | Evidence to collect | How to interpret |
|---|---|---|
| A small change routinely modifies multiple repos | Commit history, pull requests, linked tickets | Splits may follow technical layers instead of business capabilities |
| Multiple services must be deployed together | Release logs, dependency matrix, rollback plans | Contracts are not independent enough or data ownership is ambiguous |
| Requests traverse many hops just for CRUD | Distributed tracing, service call graphs, p95/p99 latency | Boundaries may be too fine-grained or cross-calls unnecessary |
| Services access each other's DBs/tables | Query logs, DB permissions, ERDs, migration history | Missing data ownership, growing schema coupling |
| One service outage triggers widespread failures | Incidents, timeouts, retry metrics, SLOs | Lack of fault isolation and graceful degradation |
| Unclear who owns updating a business rule | Incident ownership, CODEOWNERS, responsibility docs | Bounded context or ownership roles are unclear |
| Engineering spends excessive time on infrastructure | CI/CD time, on-call load, ops work, cloud bill | Distribution overhead outweighs autonomy benefits |

**Do not conclude from a single metric.** Some services must call multiple partners because integrations are genuinely independent. Some large systems require multiple repositories due to organizational policy. Cross-check actual call topology against business rules, independent changeability, and SLO targets.

## 6. Running example: decomposing an e-commerce system

A team wants to modernize an e-commerce application on the cloud. They plan to split by tables: Cart, CartItem, Order, OrderLine, Product, ProductPrice, Coupon, Stock, and Payment. The rule “a customer receives a discount when buying two products in group A, capped at the total promotion limit” will span multiple small services. When issuing a refund, the team has to coordinate state across all these services.

### 6.1. Start from business processes

Instead of using table names as boundaries, the team describes capabilities:

- **Catalog:** manages product content, categorization, and display information.
- **Ordering/Checkout:** creates orders, locks snapshots of line items, prices, and accepted terms; manages order lifecycle states.
- **Inventory:** manages sellable quantities, stock reservations/releases, and inventory rules.
- **Payment:** manages payment intents, confirmations from payment providers, refunds, and reconciliation.
- **Fulfillment:** schedules delivery, shipping, parcel tracking, and returns.

These are **bounded context candidates**, not a commitment to have exactly five microservices. A small team can implement Ordering, Pricing, and Promotion as modules inside a monolith; Inventory or Payment are split independently only when needs and contracts are clear enough.

### 6.2. Define data ownership and invariants

| Business scope | Owned data / policy | Representative invariant | How other scopes consume it |
|---|---|---|---|
| Catalog | Product content, published attributes, categories | Display info matches the published version | Catalog update APIs or events |
| Ordering | Order, order lines, status, locked snapshot prices and terms | Confirmed orders keep snapshot pricing; only valid state transitions occur | Status lookup API, order created/confirmed events |
| Inventory | Stock ledger, reservations, allocation policies | Never allocate beyond sellable quantity under published rules | Reserve/release commands, outcome events |
| Payment | Payment intent, attempts, transactions, refunds | Never record the same payment twice on retry | Idempotency-keyed payment commands, outcome events |
| Fulfillment | Shipments, shipping labels, tracking, returns handling | Never ship an order that has not met fulfillment eligibility | Consumes eligible status from Ordering |

**Critical detail:** List prices may be decided by Catalog/Pricing, but Ordering must own the accepted price snapshot inside an order. If the list price changes tomorrow, today's order must not automatically change its total.

### 6.3. Order flow with clearer contracts

~~~mermaid
flowchart TD
    A[Customer submits order] --> B[Ordering / Checkout]
    B --> C[Validate rules & lock snapshot]
    C --> D[Order in PENDING state]
    D --> E[Inventory: request stock hold]
    E --> F{Stock reserved?}
    F -- No --> G[Ordering: reject or cancel order]
    F -- Yes --> H[Payment: request payment]
    H --> I{Payment succeeded?}
    I -- No --> J[Release stock hold]
    J --> G
    I -- Yes --> K[Ordering: confirm order]
    K --> L[Fulfillment: start shipping process]
~~~

This diagram shows a **multi-state business workflow**; it does not imply every arrow must be synchronous HTTP. You can use events, queues, and workflow coordinators, or keep some steps inside the same application depending on consistency, response time, and recoverability.

When using asynchronous mechanisms, design at least:

1. **Idempotency:** reservation/payment commands and consumers can receive duplicate messages without double-deducting stock or double-charging.
2. **Transactional outbox or equivalent:** persist business state changes and the outbound event record in the same local transaction, then publish reliably.
3. **Correlation IDs and tracking state:** trace an order across components and distinguish PENDING, CONFIRMED, CANCELLED, REFUND_PENDING, etc.
4. **Retries, timeouts, and dead-letter queues:** handle transient failures without infinite retries or retry storms.
5. **Business-meaningful compensation:** if stock was reserved and payment fails, release the hold; if payment was captured and a later step cannot complete, issue a refund per policy.

Do not treat a **Saga** as a way to get automatic ACID transactions across all services. A Saga coordinates local transactions and compensating actions, may expose observable intermediate states, and real-world actions like sending an email or shipping goods may not be fully reversible.

## 7. Discovering boundaries through domain exploration

To avoid this antipattern, architects work with product owners, domain experts, engineers, operations, and security through the following steps.

### 7.1. Start from business events

In an Event Storming session or similar workshop, list:

- **Events:** OrderCreated, StockReserved, PaymentFailed, OrderCancelled, OrderDelivered.
- **Commands:** PlaceOrder, ReserveStock, CapturePayment, CancelOrder, CreateShipment.
- **Policies/rules:** Confirm order only when conditions are met; refund according to payment status; do not ship unready orders.
- **Actors:** customer, warehouse, finance, payment gateway, shipping partner.
- **Hotspots:** unresolved rules, disputed data ownership, or unclear states.

From there, identify clusters of rules with their own language, lifecycle, and stable owner. Mark where flows cross clusters to design communication contracts.

### 7.2. Analyze change coupling

Review past feature requests, bug fixes, and recent commits to see which parts frequently change together. For example, promotion calculation and order totals may always need consistent updates during checkout; splitting them into two independent deployments may add no value.

**Change coupling** is a signal, not absolute proof: two modules may change together during a new product launch and later diverge in cadence. Combine this with the business model and expected rate of change.

### 7.3. Analyze data and consistency

For each operation, determine:

- Which data must be consistent together within **one transaction**?
- Which data can update via events within seconds or minutes?
- What does the user see while the next step has not completed?
- On partial failure, can we retry or compensate?
- Who is permitted to modify which state and records?

If strict transactions are required across a set of data and there is no business plan for eventual consistency, that is a sign to **keep the related rules within the same deployment boundary** for now.

### 7.4. Check team autonomy

An independent microservice needs people accountable from development through monitoring, on-call, data, and API lifecycle. Creating multiple teams that “own services” while every change still waits on another team does not produce genuine autonomy.

### 7.5. Create a context map and contracts

Use a context map to clarify relationships such as upstream/downstream, event contracts, APIs, and where an anti-corruption layer is needed. Contracts should use **business language** rather than exposing internal schemas.

For example, a clean contract might look like:

~~~json
{
  "eventType": "InventoryReservationConfirmed",
  "eventVersion": 1,
  "eventId": "evt-example-123",
  "orderId": "ord-example-456",
  "reservationId": "res-example-789",
  "occurredAt": "2026-01-10T12:00:00Z"
}
~~~

This is an illustrative payload, not a complete contract. In production, specify schema validation, sender identity, versioning, deduplication, and event ordering as appropriate. Consumers should rely on the meaning “stock has been reserved” rather than reading rows directly from the StockLedger table.

## 8. Modular monolith: a useful starting point

A **modular monolith** is a single deployable application divided into modules along clear business boundaries, restricting dependencies and protecting internal data. It lets teams clarify the domain and refine the model before paying the cost of multiple independent runtime environments.

~~~mermaid
flowchart TB
    U[Web / API] --> M
    subgraph M[Single deployable application]
      O[Ordering Module]
      I[Inventory Module]
      P[Payment Module]
      F[Fulfillment Module]
      O --> I
      O --> P
      O --> F
    end
    O --> DO[(Ordering Data)]
    I --> DI[(Inventory Data)]
    P --> DP[(Payment Data)]
    F --> DF[(Fulfillment Data)]
~~~

This diagram shows **logical ownership** of data; the data areas may reside on the same DB server initially. What matters is that other modules do not directly modify internal structures. Module calls must also follow meaningful APIs/contracts rather than allowing arbitrary class-to-class calls across modules.

In Java, packages can be organized by domain:

~~~text
com.example.commerce
  ordering
    api/
    application/
    domain/
    infrastructure/
  inventory
    api/
    application/
    domain/
    infrastructure/
  payments
    api/
    application/
    domain/
    infrastructure/
  fulfillment
    api/
    application/
    domain/
    infrastructure/
~~~

Conventions:

- The Ordering module calls the public interface of Inventory or Payment; it does not directly import another module's internal repositories and entities.
- Business rules live near the owning model; do not dump all logic into a GlobalBusinessService.
- Schemas and migrations have owners; if sharing a DB, enforce permissions or dependency checks to prevent cross-writes.
- Enforce module dependencies via architecture rules and reviews; Java modules, ArchUnit, or platform-appropriate mechanisms can be applied.

A modular monolith **does not automatically guarantee good architecture**. An application with many packages that still shares mutable state and global repositories remains tangled. Boundaries must be enforced in code and in team practices.

### 8.1. Comparing the two options

| Criterion | Modular monolith | Microservices with clear boundaries |
|---|---|---|
| Deployment | One primary release | Services can release independently |
| Inter-scope communication | Mostly in-process calls, low network overhead | Network/APIs/events, partial failures apply |
| Data and transactions | Convenient for local transactions | Requires explicit data ownership and cross-service consistency |
| Scaling | Usually scales the whole app; modules can be optimized in code | Can scale individually based on actual demand |
| Operations | Pipelines, alerts, and traces are usually simpler | Many pipelines, secrets, IAM, logs, tracing, and on-call |
| Domain learning | Easier to refactor boundaries while still at module level | Wrong boundaries incur API and data migration costs |
| Main strength | Reduces technical coordination cost while business evolves | Autonomy and isolation once domain, team, and load are clear |

Do not pick a modular monolith solely because “the company is small” or microservices solely because “the company is large.” Compare based on team structure, SLOs, change frequency, load patterns, and required independence.

## 9. When is splitting a microservice a well-founded decision?

A scope is a strong split candidate when most of these signals hold:

- **Business:** rules, terminology, lifecycle, and ownership of the scope are relatively stable.
- **Data:** the write source has a clear owner; external contracts do not expose internal schemas.
- **Change:** there is a need to release on a different cadence from other scopes, with backward compatibility during transitions.
- **Load or SLO:** distinct, measurable requirements for scaling, latency, availability, deployment region, or fault isolation.
- **Security/compliance:** trust boundary, access control, or data isolation requirements that justify the operational overhead.
- **Team:** capability to build, maintain, observe, and own the service after deployment.
- **Testing:** service inputs/outputs and stakeholder contracts can be verified independently.

These are **evaluation criteria**, not a mandatory checklist requiring every box checked. For instance, a sensitive-data component may require isolation for strong security reasons even with a small team; a compute-heavy module may need separate scaling even if usage patterns are simple.

### 9.1. Quantitative questions before splitting

| Evaluation dimension | Pre-change data | Desired post-change outcome |
|---|---|---|
| Lead time | Commit-to-production time for independent changes | Reduced wait time caused by unrelated releases |
| Change failure rate | Frequency of faulty changes and blast radius | Smaller blast radius or fewer cross-cutting failures |
| MTTR | Time to detect and recover from incidents | Faster incident localization |
| Runtime | p95/p99, throughput, CPU/memory, queue backlog | Scale the actual bottleneck instead of the entire app |
| Coupling | Number of repos, APIs, and teams touched per change | Fewer synchronized edits |
| Cost | Compute, storage, egress, observability, CI/CD, on-call | Total cost aligned with delivered value |
| Reliability | SLOs, error budgets, cascading failure causes | Measurable reliability with degradation plans |

Do not set a blanket threshold like “above N requests/sec you must use microservices.” A well-tuned monolith can serve heavy load; a small service with strict isolation requirements may need splitting early.

## 10. Safe incremental extraction roadmap

Once there is a sound reason to split, an incremental approach validates hypotheses before raising operational cost.

### Step 1 — Document the problem and baseline

Write an **Architecture Decision Record (ADR)** stating the concrete problem: for example, image processing must scale 10x while the monolith sees growth in only one area; or payment releases must follow a separate approval workflow. Record baselines for performance, errors, cost, release frequency, and current dependencies.

### Step 2 — Clean up boundaries inside the application

Group related rules into the same module, create stable internal APIs, and block direct modification of each other's data. The goal is being able to answer: **which module will business change X touch?**

### Step 3 — Pick a relatively independent scope as a pilot

Prioritize a scope with measurable outcomes, clear data ownership, and few tight transactions with the rest of the system. Avoid splitting the entire system at once or starting with the most coupled flow when the team lacks distributed-operations experience.

### Step 4 — Design contracts and data

Define commands, queries, events, schemas, versioning, permissions, SLAs/SLOs, idempotency, timeouts, and error detection. Choose a suitable data transition method: controlled sync, batch, CDC, or ownership transfer. If using temporary dual-writes, put discrepancy detection and reconciliation in place; uncontrolled dual-writes easily cause drift when one write succeeds and the other fails.

### Step 5 — Extract via Strangler Fig or a vertical slice

Gradually route a group of requests or a business flow to the new component with observability and rollback. You can use feature flags, tenant-based routing, or migrating a specific endpoint. Do not duplicate business logic indefinitely across two systems.

~~~mermaid
flowchart LR
    C[Client] --> G[API gateway / Router]
    G -->|Migrated flow| N[New service]
    G -->|Remaining flow| O[Legacy application]
    N --> D[(Data owned by new service)]
    O --> L[(Legacy data)]
    O -. Controlled contract .-> N
~~~

Once data ownership moves, progressively remove cross-reads/writes and eliminate duplicate logic. The final step closes only when no consumers or writers still rely on the old capability.

### Step 6 — Verify independence before splitting further

Measure whether the new service actually:

1. Deploys without forcing simultaneous deployments of other parts.
2. Owns and evolves its data/contracts within managed bounds.
3. Tolerates local failures or degrades in a controlled manner.
4. Has a team accountable for observability and incident response.
5. Meets target goals for load, latency, security, or delivery speed.

If not, re-analyze the boundary. **Adding more services rarely fixes coupling in existing services.**

## 11. What if you already built a distributed monolith?

Do not assume a full rewrite is required. First measure real call paths and why changes happen together, then choose one or more remedies:

| Existing problem | Improvement measure | Risks / conditions |
|---|---|---|
| Multiple services always edited and released together | Consider **merging** them back into one module or deployment with cohesive responsibilities | Requires routing, data handling, ownership, and rollback plans |
| Cross-DB access | Establish data owners, close direct write paths, introduce APIs/events, and transition ownership | Transition phase requires sync and reconciliation |
| Many synchronous calls just to fetch auxiliary data | Use read models, snapshots, or controlled caching | Must publish data freshness guarantees and refresh mechanisms |
| Contract changes cause recurring failures | Contract testing, schema evolution, backward compatibility, versioning | Requires version lifecycle management |
| A minor failure cascades across entire requests | Timeouts, bounded retries, bulkheads, circuit breakers, graceful degradation | Do not use retries to mask deterministic business errors |
| Unclear where a rule lives | Domain workshops, context mapping, assign owners, move logic to the right module | Requires alignment between business and engineering |
| Too much infrastructure for little gain | Consolidate pipelines/runtimes or return to a modular monolith where justified | Evaluate migration cost and operational readiness |

**Merging services is a normal architectural choice** when it reduces coupling and cost while still meeting requirements. The goal is right-sized boundaries and changeability, not endlessly increasing service count.

### A remediation example

Three services—Coupon, DiscountRule, and OrderTotal—are always updated together whenever pricing policies change. They share a promotion table and call each other synchronously on every checkout.

A viable fix is consolidating those three capabilities into a **Pricing/Promotion module** inside checkout or behind a clear business contract. In the first refactoring pass, the module can remain inside the application. Consider independent deployment only when the team has distinct load, ownership, and contract reasons. If multiple channels (web, POS, partner apps) require the same pricing policy and Pricing has a clear lifecycle, an independent Pricing service can also make sense; the decision depends on the actual domain.

## 12. Well-Architected evaluation

Splitting on the wrong boundaries often harms multiple pillars:

| Pillar | Risk when split poorly | How to evaluate / prevent |
|---|---|---|
| **Operational Excellence** | Many pipelines, environments, alerts, on-call rotations; small changes need heavy coordination | Track lead time, release coupling, incident ownership; standardize without multiplying services unnecessarily |
| **Security** | More endpoints, machine identities, secrets, and network paths; overlapping data access | Trust-boundary threat modeling, least privilege, data ownership, and auditing |
| **Reliability** | Partial failures, timeouts, retry storms, distributed transactions, cascading failures | User-journey SLOs, tracing, targeted fault injection, idempotency and graceful degradation |
| **Performance Efficiency** | Slowness from excessive network hops; scaling the wrong component | Analyze p95/p99, critical path, saturation, contention, and per-capability load |
| **Cost Optimization** | Higher baseline cost for containers, clusters, API gateways, egress, logging, and operations | Calculate full lifecycle cost and weigh against independent deploy/scale benefits |
| **Sustainability** | Always-on resources for low-load services, excess telemetry and data transfer | Rightsize, eliminate idle capacity, and reduce pointless data chatter |

In particular, poor service splitting can create an **illusion of safety**: the number of deployments grows, yet every request still depends on all services, so end-to-end availability does not improve.

## 13. ADR template for deciding not to split a service yet

Example decision record from an e-commerce team:

~~~markdown
# ADR-014: Keep Pricing and Promotion inside the Checkout module

## Context
- Promotion rules and order totals usually change together.
- Checkout needs to calculate a consistent total when the customer confirms purchase.
- Operations currently has no separate scaling or SLO requirement for Pricing.
- Splitting PriceService and CouponService would add 2 synchronous hops.

## Decision
Keep Pricing and Promotion as well-bounded modules inside the
Checkout application. Confirmed price snapshots remain owned by Ordering.

## Consequences
- Rules can be updated and tested in a single release.
- Pricing cannot yet be deployed independently.
- Imports and data ownership must be enforced to prevent internal coupling.

## Re-evaluation conditions
- Multiple sales channels need the same pricing contract with a clear owner.
- Metrics demonstrate a need to scale or deploy Pricing separately.
- Plans are in place for consistency, latency, observability, and rollback.

## Verification criteria
- Checkout preserves exact totals at order confirmation time.
- Promotion changes do not require edits to unrelated modules.
- Checkout p95/p99 and error rate meet team-agreed SLOs.
~~~

An ADR is simply a tool for recording decisions and assumptions. When data or needs shift, the team can write a new ADR to extract a service after quantifying benefits and costs.

## 14. Architecture analysis exercise

**Scenario:** A team of 8 engineers maintains a service-booking application. The initial version has one Java app and one DB, serving 30,000 bookings/day. They plan to split into UserService, AppointmentService, TimeSlotService, BookingStatusService, EmailService, NotificationTemplateService, and PaymentService because each name corresponds to a table. There are no load metrics or independent deployment targets yet. A new rule requires that cancellations past the cutoff receive no refund.

**Analysis tasks:**

1. List at least four business and ownership questions to clarify before choosing boundaries.
2. Identify pairs of services likely to be over-split or tightly bound by transactions.
3. Propose an initial module layout and contracts between Booking, Payment, and Notification.
4. Describe one scenario with strong evidence to extract a module into a microservice.
5. Propose three metrics to measure whether the architectural change delivers value.

**Solution hints:**

- Understand the appointment lifecycle, reschedule/cancel rules, refund eligibility, who owns time slots, how double-booking is prevented, and what happens when payment fails.
- Appointment, TimeSlot, and BookingStatus likely belong to one **Booking** bounded context if they jointly protect against double-booking and enforce valid state transitions. User/Profile and Payment may have distinct models; verify real needs.
- Start with a modular monolith containing Booking, Customer, Payment Integration, and Notification. Booking emits a BookingCancelled event; refund eligibility logic needs a clear business owner; Payment handles idempotent refunds. Notification consumes events and sends notifications with retries. Deploying every module as a service is unnecessary.
- If Notification generates heavy send load, needs isolation from email provider failures, and has a separate SLO, the team can extract a notification worker with a queue. If payments face strict security controls or justified independent releases, Payment can also be extracted.
- Measure cancellation-policy change lead time, incident rate, and p95/p99 for the booking/cancellation journey; add infrastructure cost and count of components released together.

**Pitfall to avoid in the exercise:** Do not use the 30,000 bookings/day figure alone to conclude microservices must or must not be used. The choice also depends on peak load profiles, transactions, team structure, SLOs, and required isolation.

## 15. Checklist before drawing a new microservice

- [ ] Have the business capability and rule owner for this scope been described?
- [ ] Do terms, states, and invariants carry consistent meaning within the scope?
- [ ] Do you know which data this scope owns, who writes, who reads, and via which contract?
- [ ] Have operations needing local transactions vs. steps accepting eventual consistency been identified?
- [ ] Have change coupling and synchronous call paths in user journeys been checked?
- [ ] Is there a measurable reason—release cadence, scale, security, fault isolation, or ownership—to split?
- [ ] Can the owning team deploy, monitor, handle on-call, and manage the service lifecycle?
- [ ] Do APIs/events have appropriate versioning, timeouts, idempotency, retries, and contract testing?
- [ ] Has a modular monolith or keeping the same deployment been considered while the domain stabilizes?
- [ ] Are there baselines, an incremental rollout plan, observability, rollback, and post-experiment decision criteria?

## 16. Conclusion

Splitting microservices without clear business boundaries turns internal application dependencies into network dependencies, raising latency, operational complexity, and cost without guaranteeing autonomy. Good architecture starts from **business capabilities, invariants, data ownership, change cadence, and operational needs**; deployment boundaries follow afterward.

For new systems or evolving domains, a **modular monolith with enforced boundaries** is often a sensible proving ground. When evidence demonstrates a need for independent release, scaling, or isolation, extract one scope at a time behind clear contracts and verify the outcome afterward. The ultimate goal is a cloud architecture that meets business needs and balances **reliability, security, scalability, cost, performance, and operations** in the Well-Architected spirit.
