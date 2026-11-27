# Identifying Distributed Monoliths and Premature Service Decomposition

## 1. The architectural problem: multiple services that still must change together

In cloud application design, teams often consider moving from a monolithic application to microservices for independent deployment, flexible scaling, or fault containment. However, **the number of deployed services does not prove architectural independence**. A system with ten containers, multiple repositories, an API gateway, and a message broker can still force every component to change, release, and recover together.

This situation is commonly called a **distributed monolith**: the application is split into multiple processes or deployment units, yet the parts remain **tightly coupled across business logic, data, timing, or release cycles**. The system incurs network latency, partial failures, and distributed operational overhead while failing to realize the autonomy expected from services.

A common root cause is **premature service decomposition**: splitting an application into services before achieving a stable understanding of business boundaries, data ownership, change patterns, load profiles, and operational capacity. Splitting early is not always wrong, but it becomes risky when driven mainly by a desire to adopt new technology, database table counts, or the current org chart.

For example, a booking platform splits Booking, Room, Price, Coupon, Payment, and Notification into six services. On every booking confirmation, Booking waits sequentially on five services; all read and write the same database; renaming a column in the booking table forces redeploying all six. Although it looks like microservices on a diagram, **actual independence is very low**.

### Learning objectives

After this lesson, you will be able to:

1. Distinguish traditional monoliths, well-modularized monoliths, microservices, and distributed monoliths.
2. Recognize tight-coupling symptoms across source code, data, runtime flows, deployment, and operations.
3. Explain the impact of premature service decomposition on reliability, security, performance, cost, and teams.
4. Decide when to keep a modular monolith and when to extract a capability into a separate service.
5. Propose a phased decoupling and extraction roadmap with measurements and recovery plans.

## 2. Four concepts that are easily confused

| Model | Structure and Deployment | Notable Characteristics |
|---|---|---|
| **Unstructured monolith** | Many capabilities inside one codebase, typically deployed together | Changes and tests easily ripple outward; initial operations are relatively simple |
| **Modular monolith** | One deployment unit containing business modules with clear APIs and ownership | Easy to guard transactions within a shared process/DB; can keep source-level coupling low |
| **Well-bounded microservices** | Multiple services, each owning a capability and contract, able to evolve relatively independently | Must handle networking, distributed transactions, security, and operations; independence depends on actual design |
| **Distributed monolith** | Multiple services/processes tightly coupled across several dimensions | Bears distributed overhead while still struggling to release, scale, or recover independently |

**A monolith is not bad design by default.** For small teams, evolving domains, or workflows requiring strong transactions, a well-designed modular monolith can be a more reliable and economical choice.

**Microservices do not automatically become a distributed monolith.** Truly necessary synchronous dependencies can still exist; the deciding factors are **contracts, autonomy, and the system's resilience when a dependency is unavailable**.

### Comparing two diagrams

~~~mermaid
flowchart TD
    Client["User"] --> Gateway["API Gateway"]
    Gateway --> Booking["Booking service"]
    Booking --> Room["Room service"]
    Room --> Pricing["Pricing service"]
    Pricing --> Coupon["Coupon service"]
    Booking --> Payment["Payment service"]
    Payment --> Notify["Notification service"]
    Booking --> SharedDB[("Shared DB")]
    Room --> SharedDB
    Pricing --> SharedDB
    Coupon --> SharedDB
    Payment --> SharedDB
    Notify --> SharedDB
~~~

*Example at risk of being a distributed monolith: long call chains, multiple writers mutating shared data, hard-to-isolate failures, and coordinated releases. The diagram merely illustrates an anti-pattern; verify against actual code and operations.*

~~~mermaid
flowchart TD
    Client["User"] --> API
    subgraph AppBoundary["Modular Monolith - single deployment unit"]
        API["API / Application layer"]
        BookingM["Booking module"]
        PricingM["Pricing module"]
        NotificationM["Notification module"]
        API --> BookingM
        BookingM --> PricingM
        BookingM -. "Internal event" .-> NotificationM
    end
    BookingM --> DB[("Database with logical ownership permissions")]
    PricingM --> DB
    NotificationM --> DB
~~~

*Illustrating a modular monolith: modules may still share one physical database while respecting logical boundaries. A shared deployment unit does not prevent modules from having distinct owners, contracts, or tests.*

## 3. Signs of a distributed monolith

Do not diagnose from a topology diagram alone. Ask development and operations teams **how far a small change or a single failure propagates**.

| Symptom | How to Verify | Why It Matters |
|---|---|---|
| **Lockstep releases required** | A new field forces multiple repositories/teams to release together | Incompatible contracts or unclear boundary ownership |
| **Multiple services write the same tables** | Audit DB access permissions, migrations, and SQL queries | No single source of truth or unified write path; data bugs spread |
| **Long synchronous call chains** | Use distributed tracing; measure fan-out and chain depth | Latency, timeouts, and dependency errors compound on user paths |
| **Chatty inter-service calls** | One business action needs dozens of fine-grained RPCs | Boundaries split by functions/tables instead of capabilities |
| **One service failure breaks the whole transaction** | Disable an auxiliary component and observe behavior | Degradable or deferrable steps are not isolated |
| **All services import a shared domain library** | Inspect imports and forced version-bump frequency | Business rules and schemas leak across multiple services |
| **Distributed writes lack state models** | Inspect multi-DB write sequences and compensation logic | Can produce half-finished states, duplicate sends, or broken invariants |
| **Independent deployment on paper only** | Compare release histories and joint rollbacks | Separate deploy units that remain operationally coupled |
| **Scaling one service saturates the whole system** | Load-test per workload; measure pools, quotas, locks, and queues | Shared resources are not properly isolated |
| **Unclear incident/data ownership** | Run incident drills; ask who owns a failed state | Service boundaries do not match accountability |

A single symptom **is not conclusive**. For instance, a task might legitimately need three synchronous calls to preserve business behavior, or a major regulatory change might force multiple services to update together. Look for **recurring patterns across many changes, incidents, and journeys**.

### Three practical tests

**The change test:** "If the cancellation fee formula changes tomorrow, which components must change code and deploy?" If Booking, Payment, Email, Search, and Report must all release together, revisit rule boundaries.

**The failure test:** "If Notification stops working for 30 minutes, can users still place valid bookings?" If emailing is merely a post-confirmation step, making Booking wait on Notification creates unnecessary temporal coupling.

**The scaling test:** "When Search load jumps 10x, can we scale Search compute without saturating Booking's transactional DB?" If services share the bottleneck resource, scaling independence exists only at the deployment label level.

## 4. Dimensions of coupling to measure—not just repository count

### 4.1. Code and contract coupling

An API with a stable contract hides implementation details. Conversely, if consumers depend on exact internal entity structures, unversioned enum values, or undocumented step ordering, internal refactoring breaks consumers.

Bad example: the Report service imports `BookingEntity` from Booking's private library and accesses fields tied directly to DB schemas. When Booking splits into multiple tables, Report must both upgrade the library and rewrite queries.

Better direction: Report uses a **read model** or dedicated data/event contract with defined business semantics, versions, and compatibility policies. Never extract a shared domain library merely to dodge contract design.

### 4.2. Data coupling

A **shared database** can work very well in a modular monolith; risk arises when **independently deployed services** write directly into the same internal schema without ownership and migration control.

Questions to answer:

- Who is the source of truth for booking status and locked-in pricing?
- Who holds write authority and controls transactions guarding the "no double-booking" invariant?
- Do consumers receive data via APIs, events, views/read models, or direct table queries?
- During schema edits, can both old and new producers be supported across a transition window?

The standard rule is that **a service owns its data and write paths**. That does not automatically require one physical DB server per service; schema, permission, and resource isolation should reflect risk, independence, and cost.

### 4.3. Temporal coupling

A synchronous operation requires both caller and dependency to be available at the exact same moment. In a chain of multiple mandatory calls, one slow stage slows the whole journey. With unbounded retries, pressure spikes right when the dependency is already overloaded.

Example: Booking waits for Pricing, Inventory, Payment, Notification, and Loyalty before returning a response. Distinguish:

- Checking **booking eligibility**, **applicable price**, or **payment result** may be preconditions before confirming.
- Sending **email**, awarding **loyalty points**, or updating **analytics** can usually happen asynchronously if the business accepts lag.

Do not push everything onto queues if the workflow truly demands an immediate result. **Consistency, latency, and user experience** must be decided alongside the business owner.

### 4.4. Deployment and operational coupling

Two services can have separate databases yet remain coupled if breaking APIs force simultaneous deployments, a fixed release train bundles them, or one pipeline holds overly broad admin privileges. Conversely, releasing together by organizational choice does not prove bad code design; separate technical causes from process causes.

Useful indicators:

- Percentage of releases requiring coordination with another service.
- Lead time for a small change versus integration testing and cross-team deploy waits.
- Number of cross-service rollbacks caused by incompatible APIs/schemas.
- How many workloads fail when one DB pool, DNS, quota, or message broker degrades.
- Number of runbooks, alerts, and on-call engineers pulled into a routine incident.

## 5. Why premature service decomposition increases risk

### 5.1. Unclear business boundaries

While a product is still discovering its business model, rules shift frequently. Drawing boundaries from tables like **User**, **Room**, **Booking**, and **Price** without understanding pricing, holding, and cancellation rules forces teams to shuttle logic back and forth across services.

A better way to split is asking: **which business invariants must remain consistent within a single boundary?** For instance, "no overlapping confirmed bookings for the same room" may require keeping conflict checks and booking writes in one transaction or coordinated concurrency mechanism. Splitting Inventory and Booking with unclear ownership turns invariant enforcement into a harder distributed transaction problem.

### 5.2. Technical choices carry operational overhead

Every new service may require the following depending on the platform:

| Need | Additional Work |
|---|---|
| **Deployment** | Builds, pipelines, configuration, rollouts, rollbacks, API compatibility |
| **Communication** | DNS/service discovery, TLS/mTLS or appropriate transport security, timeouts, retries, contract versioning |
| **Data** | Schema ownership and migrations, CDC/events or read-model replication, data recovery |
| **Observability** | Logs, metrics, tracing, correlation IDs, dashboards, alerts, and runbooks |
| **Security** | Workload identity, IAM, secrets, config/dependency scanning, network policies |
| **Resilience** | Partial-failure handling, idempotency, retries/backoff, replay, chaos/fault testing |
| **Cost** | Baseline compute, DBs/queues, cross-zone/region traffic, log ingestion, and on-call staffing |

On the cloud, autoscaling and managed services reduce some toil, but do not eliminate responsibility for designing failure behavior, access controls, billing, and incident response.

### 5.3. Reliability does not increase automatically by splitting

Suppose one request must wait for five dependencies. If each independent dependency has **99.9%** availability over the same measurement window and all five are mandatory, the simplified end-to-end success probability is:

\[
0.999^{5} \approx 99.50\%
\]

This is an **illustrative mathematical example**, not a production SLO formula: real outages are often correlated, and flows use retries, caches, redundancy, or fallback paths. It shows that when a request depends on many mandatory services, **end-to-end reliability must be measured on the user journey** rather than inferred from individual SLOs.

### 5.4. Security and permissions also become more complex

More services generally mean more workload identities, network interfaces, policies, secrets, and data stores. If a small team lacks least-privilege tooling, config governance, rotation, and audit visibility, splitting early expands the misconfiguration surface. Service separation improves resource and data isolation **only when permission boundaries are genuinely enforced**.

## 6. End-to-end scenario: a cloud booking platform

A six-engineer team builds an accommodation rental platform. Aiming for "proper microservices from day one," the team creates:

- **RoomService:** fetches room details and room status.
- **AvailabilityService:** checks availability.
- **ReservationService:** creates holds and confirms bookings.
- **PriceService:** computes quotes and discounts.
- **PaymentService:** integrates with the payment provider.
- **EmailService:** sends confirmation emails.

Each service has its own container and pipeline, yet all access the **rooms**, **reservations**, and **prices** tables in one DB. Reservation calls Room, then Availability, then Price, then Payment, then Email inside one HTTP request. Every environment shares one migration bundle and deploys simultaneously whenever a column changes.

### 6.1. Identified problems

| Observation | Root Mechanism | Challenging Question |
|---|---|---|
| Both Room and Availability decide availability state | Unclear source of truth and double-booking invariant | Which single place has authority to accept confirmation? |
| Reservation waits for Email to return success | Unnecessary communication on the critical path | Should an email error cancel an otherwise valid booking? |
| PriceService and Reservation both edit the total price column | Data coupling and missing ownership of locked-in price | Who determines and persists the effective price snapshot? |
| All services share one DB migration | Zero schema-change autonomy | Can expand–migrate–contract be applied? |
| Released together in one evening | Deployment coupling hidden inside contracts | Can consumers deploy before compatible producers? |
| Six dashboards but no business SLIs | Resource-centric monitoring missing the booking journey | How many valid booking requests finish within SLO? |

### 6.2. Typical failure during a promotion

As traffic climbs, EmailService responds slowly. Reservation keeps waiting for email even after the DB recorded the booking. Users see timeouts and retry. Without an **idempotency key** or deduplication logic, retries trigger unwanted extra actions. If Reservation retries en masse without backoff, EmailService gets hit even harder.

The fix is not merely adding more EmailService replicas. First clarify **whether sending email is a precondition for booking confirmation**. If not, decouple notifications from the user response path, and handle post-commit event publishing, retries, and failed-notification states.

### 6.3. Simpler design for the early stage

The team can use a **modular monolith** with Catalog, Pricing, Booking/Inventory, Payment Integration, and Notification modules, keeping availability-check and reservation-commit rules inside one consistency boundary. Modules interact via internal contracts, and only Booking/Inventory may update booking-decision states.

~~~mermaid
flowchart LR
    User["Web / Mobile"] --> App["Application / API"]
    subgraph AppBoundary["Single workload with modules"]
        App --> Catalog["Catalog"]
        App --> Pricing["Pricing"]
        App --> Booking["Booking + Inventory"]
        App --> Payment["Payment Integration"]
        App --> Notify["Notification Worker"]
    end
    Booking --> DB[("Booking DB")]
    Pricing --> DB
    Booking --> Outbox[("Transactional Outbox")]
    Outbox -. "Publisher" .-> Notify
    Payment --> Provider["Payment Provider"]
    Notify --> Mail["Email Provider"]
~~~

*This is an illustrative logical diagram, not a rule forcing all modules onto one DB or queue. Payment and booking states must be modeled per business rules. Outbox and worker can deploy inside the initial system; when used, ensure duplicate handling and job observability.*

When Search grows rapidly with a distinct read workload, the team can **extract Search first** once read data, update contracts, and freshness bounds are clear. Splitting Booking/Inventory early solely because there are two tables is far riskier due to tight consistency rules.

## 7. What should service boundaries be based on?

### 7.1. Business capabilities and reasons to change

A good boundary groups rules sharing the **same purpose, lifecycle, and rate of change**, while hiding internal details from other services.

Examples:

- Changing promotion formulas mainly affects **Pricing**.
- Changing room-hold rules affects **Booking/Inventory**.
- Changing SMS/email templates affects **Notification**.
- Changing search indexing/config affects **Search**.

If "changing cancellation fees" consistently requires editing 4–5 services, check whether the rule is overly fragmented.

### 7.2. Data invariants and transaction boundaries

An **invariant** is a condition that must hold after every valid operation. For example, no two confirmed bookings may overlap for the same asset if double-booking is forbidden. Identify who owns the invariant and how it is protected before splitting databases or deployments.

Putting multiple services across a **check-then-write** sequence does not make it atomic. You may need DB transactions, locks/constraints, optimistic concurrency, or another fitting design. When splitting across boundaries, clarify what can be eventually consistent and what must be confirmed immediately.

### 7.3. Practical team independence

Microservices help most when one team can **develop, test, deploy, observe, and troubleshoot** a capability without pulling multiple other teams into every change. Conversely, if the same handful of engineers maintain all services, multiple repositories/pipelines add administrative toil without speeding delivery.

Do not treat a fixed headcount as a rigid threshold: automation maturity, domain complexity, and compliance needs also matter.

### 7.4. Scaling, isolation, and compliance needs

Consider extracting a service if:

- Load or resource profiles differ markedly (e.g., Search needs read/CPU optimization, Booking needs transactions and I/O).
- Dedicated deployment/recovery requirements exist, with clear fault boundaries and compatibility plans.
- Data or capabilities need distinct access controls where real security boundaries can be enforced.
- Owning teams change it independently often enough for benefits to outweigh operational cost.

Do not split just to "use Kubernetes" or "enable autoscaling." A monolithic app can still scale horizontally; extraction pays off only when optimizing distinct resources or lifecycles.

## 8. Deciding between modular monolith and microservices

| Criterion | Favors **modular monolith** | Favors **microservices** |
|---|---|---|
| **Domain** | Business rules change often; boundaries still shifting | Capabilities and invariants have clear owners |
| **Team** | Small team, centralized operations, low need for independent releases | Multiple teams capable of self-operating and releasing |
| **Transactions** | Many rules require atomicity on shared data | States and cross-boundary consistency can be modeled cleanly |
| **Load** | Most parts scale up/down under similar load | Workloads have sharply different scaling needs |
| **Reliability** | Low need for runtime isolation; minimal network paths | Blast-radius isolation needed, with timeouts, fallbacks, and observability ready |
| **Cost** | Limited cloud/staff budget; simplicity prioritized | Independent runtime, DB, network, and telemetry costs are justified |
| **Security** | In-app controls sufficiently enforce business permissions | Dedicated identity/permission/data boundaries needed with governance maturity |
| **Rate of change** | Low cross-module change volume or unmeasured | Local changes frequently blocked by shared release schedules |

There is no threshold like "above N users you must use microservices." Measure **real load, bottlenecks, change history, and operational maturity**. Even after adopting microservices, other modules can remain in a shared deployment unit.

## 9. Split services step by step, never all at once

### Step 1 — Gather baseline evidence

Pick one concrete journey, such as **search room → hold → pay → confirm**. Use traces, logs, and data maps to record:

- Participating components, call methods, and mandatory conditions.
- Who owns tables/states and what changes together.
- p95/p99 latency, error rates, retries, DB/queue bottlenecks, and cost.
- Deployment history, rollbacks, incidents, and cross-team coordination overhead.

Do not draw future microservices before seeing the current system's data flows and limits.

### Step 2 — Define modules and contracts first

Inside the monolith, group logic by capability and specify which module may access which data. Create internal APIs or interfaces for genuinely needed interactions:

~~~java
// Contract published by the Booking module.
public interface BookingFacade {
    BookingResult confirm(ConfirmBookingCommand command);
    BookingStatus getStatus(BookingId bookingId);
}

// Consumers know only the business request.
public record ConfirmBookingCommand(
        String bookingId,
        String quoteId,
        String idempotencyKey) {}
~~~

This snippet illustrates only the **contract boundary**. Quote validation, holds, payments, and idempotency states must be implemented per business rules; declaring an interface does not guarantee those properties on its own.

If an interface mirrors table columns and forces callers to make ten calls to complete one action, redesign the contract around **business semantics** rather than exposing raw CRUD over HTTP.

### Step 3 — Test boundaries and compatibility

- Unit/domain tests verifying invariants and state transitions.
- Architecture tests blocking illegal cross-package/module imports.
- Contract tests verifying producer/consumer compatibility when APIs or events evolve.
- Load/fault tests evaluating timeouts, idempotency, backlogs, and graceful degradation.
- Reviews of data permissions, sensitive logging, secrets, and auditing per boundary.

Maintain **fitness functions** that the team actually runs in CI or reviews. Avoid over-complicating tooling before needs are clear.

### Step 4 — Pick one capability with clear extraction value

For instance, extract **Search** when search traffic dominates, read models can update from events, and bounded lag is acceptable; or extract **Notification** when delivery/scheduling lifecycles differ and fault boundaries are clear.

Formulate a concrete hypothesis: "Extracting Search lets read compute scale independently and eliminates resource contention with Booking, while keeping search p95 and cost per query within target." Only with a hypothesis can you tell whether extraction succeeded.

### Step 5 — Transition data and contracts safely

Reference sequence:

1. Identify the **source of truth** and who has write authority at each stage.
2. Build backward-compatible contracts; use **expand → migrate → contract** for schemas/APIs where appropriate.
3. Replicate or backfill required data; measure lag, detect drift, and handle failed records.
4. Route a small slice of traffic through the new endpoint or controlled routing.
5. Compare business outcomes, errors, performance, cost, and SLOs; roll back or proceed by preset criteria.
6. After switching ownership, remove legacy write paths, redundant data/configs, and update docs.

**Avoid writing to two independent data stores without reconciliation rules.** Dual-writing across two DBs creates drift when one succeeds and the other fails. If using CDC, outbox, or event sync, establish redelivery, deduplication, lag monitoring, and recovery plans.

### Step 6 — Operate independently and close the measurement loop

Consider a service truly independent only when its owning team can deploy compatible contracts, monitor SLOs, handle failures, and recover **within defined boundaries**, without forcing system-wide rollbacks for routine changes.

If cost, incidents, or coordination overhead rise without achieving benefits, consider **keeping them together or re-merging boundaries**. Service boundaries are adjustable decisions, not one-way doors.

## 10. Designing communication to avoid recreating a distributed monolith

### 10.1. Synchronous when an immediate answer is truly needed

For example, confirming a booking may require checking accepted pricing and current availability before reporting success. For synchronous RPC/HTTP:

- Define a **timeout budget** for the journey; child calls must fit inside that budget.
- Bound retries with backoff/jitter where suitable; never retry non-idempotent actions without safety mechanisms.
- Use circuit breakers, bulkheads, rate limits, or backpressure depending on context.
- Specify what happens when unable to proceed: explicit rejection, pending state, or previously verified data.
- Enforce workload-to-workload authentication/authorization, transport encryption, and request/trace ID observability.

**Fallbacks must not break invariants.** If Inventory is unresponsive, never fall back to a search cache to assert a room is available.

### 10.2. Asynchronous when the business accepts deferred processing

For notifications, analytics, or post-transaction integrations, events/queues reduce temporal coupling. However, you must accept **eventual consistency**, delayed or duplicate events, and state monitoring.

~~~mermaid
sequenceDiagram
    participant U as Customer
    participant B as Booking
    participant DB as DB + Outbox
    participant Q as Queue
    participant N as Notification
    U->>B: Confirm booking (idempotency key)
    B->>DB: Transaction: check invariants + write Booking + outbox
    alt Invalid
        DB-->>B: Rollback / conflict
        B-->>U: Failure with clear reason
    else Commit succeeded
        DB-->>B: Commit
        B-->>U: Confirmed status
        Note over DB,Q: Relay forwards event post-commit
        DB-->>Q: BookingConfirmed
        Q-->>N: Receive event (may redeliver)
        N->>N: Check idempotency / retry
    end
~~~

A **transactional outbox** closes the gap between committing business data and emitting events by writing events to the outbox in the same transaction, then relaying them. It **does not** automatically guarantee an email sends exactly once: event redelivery, worker retries, and provider behavior still need proper handling.

### 10.3. Do not turn every transaction into a Saga just because microservices exist

A **Saga** models local steps with compensating actions when a workflow crosses multiple boundaries, such as holding capacity, requesting payment, then confirming. Sagas require defining intermediate states, timeouts, unknown outcomes, safe retries, and cases where compensation itself fails.

If an invariant fits inside **one simple transaction boundary**, do not scatter it across services and patch the consequences with a Saga. Sagas fit genuinely long workflows spanning multiple owners; they do not replace sound data consistency design.

## 11. Measuring costs and benefits of splitting

A design should be evaluated solely by **real operations and change behavior**:

| Metric | Before Extraction | After Extraction to Verify |
|---|---|---|
| **Lead time for a local change** | Time from commit to safe deploy | Did it drop without raising incidents? |
| **Deployment coupling** | Share of releases needing multi-module/service coordination | Can most changes deploy independently? |
| **Mean time to recovery (MTTR)** | How long to diagnose and fix incidents | Is blast radius smaller and recovery faster? |
| **p95/p99 latency** | Critical journeys pre-split | Did new network hops breach thresholds? |
| **End-to-end errors** | Booking/checkout success SLI | Did it improve even when local dependencies fail? |
| **Resource load** | CPU, DB pools, locks, I/O, queues, quotas | Does each workload scale cleanly without shared bottlenecks? |
| **Cost per transaction** | Compute, storage, egress, telemetry, operations | Do gains justify baseline and network overhead? |
| **Teams involved per change/incident** | Coordination complexity | Is ownership clearer? |

For example, a team targets reducing coordinated releases from 70% to under 20% for Search-only changes while keeping search p95 within SLO. These numbers are **purely examples of setting criteria**, not universal benchmarks.

Agree on measurement windows, comparable load, and pre/post cost allocation. Measuring only container count or deploys per week risks optimizing a technical vanity metric without improving business value.

## 12. Trade-offs with Well-Architected thinking

| Lens | Well-Drawn Boundaries Can Help | Premature Splitting Can Cause |
|---|---|---|
| **Operational excellence** | Clear owners, independent deploys and fixes | Extra pipelines, runbooks, dashboards; complex incident coordination |
| **Reliability** | Fault containment, workload isolation, per-component recovery | More network failure points, retry storms, inconsistent data |
| **Security** | Capability-scoped IAM and data boundaries | Many identities, secrets, endpoints, and misconfigurable policies |
| **Performance efficiency** | Independent scaling for distinct workloads | Network hops, serialization, fan-out, and DB contention |
| **Cost optimization** | Avoids overprovisioning everything; scales to load | Baseline compute, gateways, brokers, DBs, network, logs/traces |
| **Sustainability** | Right-sized resources, scales down when idle | Many idle services, duplicated data, and unnecessary traffic |

Reliability must cover realistic failure scenarios. **RTO** defines recovery time targets and **RPO** defines tolerable data loss in time; splitting services does not achieve those automatically. Test zone/region failures, DB restores, IAM misconfigurations, broker outages, and safe version rollbacks.

One networking note: if multiple services run in the same cluster/zone yet every call routes through a central gateway or NAT, "distribution" can raise latency, cost, and shared failure points. Measure **actual traffic paths**, routing, DNS, quotas, and service permissions rather than merely counting deploy units.

## 13. ADR: deciding not to split Booking and Inventory yet

~~~text
ADR-021 — Keep Booking and Inventory in the same boundary initially
Status: Accepted

Context
  The product is still evolving hold and cancellation rules.
  A critical invariant is preventing double bookings.
  The team is small and does not yet need separate deployments for both capabilities.

Options
  A. Split Booking and Inventory into two services/DBs immediately.
  B. Keep together in one business module with explicit transactions;
     expose stable APIs to other modules.

Decision
  Choose B for the current phase.

Rationale
  Avoids distributed transaction coordination, simplifies concurrency
  testing and operations, and preserves clear business boundaries.

Consequences
  + Easy to enforce invariants and adjust rules.
  - Booking/Inventory cannot scale or deploy independently yet.
  - Must maintain discipline on module boundaries and write permissions.

Verification
  - Concurrency tests for the no-double-booking rule.
  - Measure latency, DB pools, error rates, and release coupling.
  - Track business changes forcing edits to both modules.

Revisit when
  Distinct scaling, ownership, or release-cadence needs emerge clearly
  with a solid plan for consistency.
~~~

An ADR must explain **why the decision fits the current context**, its consequences, and review triggers. Never write "choose microservices because it is the modern standard" as technical justification.

## 14. Checklist for detecting and preventing a distributed monolith

Before splitting a system into multiple services, verify:

- [ ] Business goals and the concrete current problem that splitting must solve are identified.
- [ ] Capabilities and invariants needing consistency have clear owners.
- [ ] Each service has a focused reason to change and publishes business-meaningful contracts.
- [ ] Multiple services do not directly write the same internal data outside an explicit governed process.
- [ ] Compatibility strategies exist for APIs, schemas, and events when producers/consumers run staggered versions.
- [ ] Slow, failing, or duplicate dependency cases are tested; timeouts, retries, and fallbacks are in place.
- [ ] Synchronous business steps are clearly distinguished from deferrable background work.
- [ ] Mechanisms protect invariants, transactions, and intermediate states when splitting data.
- [ ] Each service has an owner, IAM/secrets, observability, runbooks, and recovery procedures.
- [ ] Baselines measure release coupling, p95/p99, SLIs/SLOs, cost, and incident blast radius before splitting.
- [ ] Compared against a modular monolith or internal module extraction first.
- [ ] A phased data migration, rollback/roll-forward, and old-write-path removal plan exists.
- [ ] The split decision is documented in an ADR with expected benefits, trade-offs, and review criteria.

## 15. Practice exercise

**Scenario:** A car-rental startup has four engineers. The system is currently a Java application with Reservation, Fleet, Pricing, Billing, and Notification modules. The team plans to split into five microservices, each with its own DB, deployed on Kubernetes. Current requirements: no double-booking cars, invoices must be issued, car search spikes sharply on weekends, and the team has no dedicated SRE on-call yet.

Build an architecture proposal:

1. Identify **invariants requiring strong consistency** and tasks that can complete after the main transaction.
2. List at least **four risks** of splitting all five services right now.
3. Propose a well-bounded **modular monolith** or selectively extracted service(s), and explain why.
4. Draw the **car booking** flow and describe behavior when Billing or Notification is unresponsive.
5. Define **three measurable hypotheses** to tell when Search/Fleet or Notification should be extracted.
6. Write a short ADR capturing the decision, consequences, and review triggers.

**Guidance hint:** Vehicle holds and booking confirmation must guard invariants using appropriate transactions/concurrency controls. Notification can usually run asynchronously; Billing may require stateful workflows depending on invoicing/payment rules. Search traffic spikes signal optimizing read models, caching, or workload scaling before splitting the entire domain. Every option requires matching monitoring, permissions, and recovery.

## 16. Key takeaways

A **distributed monolith** emerges when a system takes the shape of many services yet stays bound together by shared data, execution flows, versions, or release processes. **Premature service decomposition** forces teams to solve distributed networking, distributed transactions, and operations before understanding the business boundaries they need to protect.

Good design starts from **capabilities, invariants, data ownership, load, and operational ownership**, then selects an appropriate deployment model. A well-bounded modular monolith provides a foundation to evolve into microservices when clear evidence demands it; microservices deliver value only when autonomy and fault tolerance are substantial enough to outweigh distributed overhead.
