# Reducing Tight Coupling and Increasing Cohesion Within Components

## 1. Why Is This an Important Design Principle?

When designing a cloud application architecture, architects do not merely choose networking, compute, databases, or deployment methods. They also must decide **which functionality belongs to which component** and **how components are allowed to depend on one another**. These two decisions directly affect software change velocity, scalability, incident blast radius, security, cost, and operational complexity.

Two foundational concepts:

- **Coupling:** the degree to which one component must know about, rely on, or change alongside another component to complete its work. **Tight coupling** means strong mutual dependency; **loose coupling** means minimal, controlled dependency.
- **Cohesion:** the degree to which responsibilities, data, and behaviors inside a component serve a single clear purpose together. **High cohesion** means tightly focused alignment.

The practical goal is **high cohesion within boundaries, and minimal, intentional coupling across boundaries**. It is neither possible nor necessary to eliminate all dependencies: a booking service still needs to know whether inventory is available, and a payment service must still connect to a payment gateway. The key is choosing dependencies that are stable, understandable, verifiable, and do not cause small changes to ripple widely.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish coupling from cohesion and explain why they impact cloud architecture.
2. Identify forms of tight coupling: source-code, data-schema, temporal, deployment, resource, and operational coupling.
3. Define component boundaries based on business capabilities, data ownership, and invariants that must be protected.
4. Apply API contracts, events, encapsulation, dependency inversion, and error-handling mechanisms to reduce unnecessary coupling.
5. Evaluate trade-offs between a modular monolith and microservices, synchronous and asynchronous communication, across Well-Architected perspectives.

## 2. Distinguishing Coupling and Cohesion with an Example

Consider an accommodation rental platform with these business capabilities: room search, booking confirmation, pricing calculation, payment, and notifications.

**A tightly coupled design:**

- A single component named **RentalManager** handles search, price updates, booking, sending emails, calculating taxes, and exporting reports.
- Multiple components directly modify the **rooms**, **bookings**, and **payments** tables.
- When email sending fails, booking confirmation returns an error as well; when pricing calculation changes, multiple services must be redeployed together.

**A design with clearer boundaries:**

- **Catalog/Search** handles listing information and room search.
- **Pricing** owns pricing policies and provides quotes under a defined contract.
- **Booking/Inventory** owns hold rules and double-booking prevention.
- **Payment** is responsible for payment transaction workflows and provider integrations.
- **Notification** consumes business events to send notifications, without deciding whether a booking is valid.

This partitioning is only **an initial option**. If the team is small, the business scope is simple, and requirements are evolving rapidly, these components can remain modules inside a single shared deployment. Logical boundaries remain valuable even before considering splitting into distributed services.

| Criterion | Low Cohesion, Tight Coupling | High Cohesion, Controlled Coupling |
|---|---|---|
| Responsibilities | One component performs many unrelated tasks | Each component has a clear reason to exist and change |
| Data | Other components arbitrarily read/write internal tables | The owner controls how its data is read/modified |
| Change | Changing one rule forces code edits in many places | Most changes stay within the relevant boundary |
| Deployment | Teams must release simultaneously to avoid compatibility bugs | Ability to evolve contracts and deploy independently when needed |
| Incidents | Failure in an auxiliary system breaks the core business flow | Appropriate timeouts, graceful degradation, and recovery exist |
| Testing | Tests always require spinning up the entire system | Modules and explicit integration contracts can be tested individually |

**Cohesion does not mean "every class is tiny"**, and coupling is not just counting API calls. A large module focused on a single business capability can have better cohesion than dozens of tiny services calling one another synchronously in chains.

## 3. Identifying Forms of Tight Coupling

A cloud application can be coupled across many layers. Distinguishing them helps choose the right remediation.

| Form of Coupling | Symptom | Consequence on Change or Failure |
|---|---|---|
| **Implementation coupling** | A accesses internal classes, object structures, or private configs of B | Changing B's internals forces A to change |
| **Contract coupling** | A relies on B's API/event format | Normal when the contract is clear, stable, and compatibility-tested |
| **Data coupling** | Two services mutate the same table, rely on each other's triggers/schemas | Hard migrations, contested ownership, and data integrity bugs |
| **Temporal coupling** | A only completes when B, C, and D all respond immediately | Cumulative latency; one dependency outage breaks the transaction |
| **Ordering coupling** | Components must start up, run jobs, or deploy in an implicit sequence | Hard to automate, hard to recover after incidents |
| **Deployment coupling** | One change requires multiple services to release simultaneously | Increases release risk and coordination overhead |
| **Infrastructure/resource coupling** | Multiple capabilities share a DB pool, queue, cluster, or quota | Resource contention; a traffic spike in one impacts others |
| **Platform coupling** | Business logic directly uses provider-specific SDKs, formats, and features | Hard to test, migrate, or change deployment models |
| **Operational coupling** | No clear owner; shared logs, alerts, and runbooks that are hard to separate | Hard to triage incidents, increases cross-team support burden |

Not every form of coupling is bad. **Coupling to a public, stable contract** is often necessary. Conversely, trying to completely hide every cloud SDK can introduce unnecessary abstraction layers. Architects must evaluate coupling by the real-world impact of change and failure.

### Questions to Detect High Coupling

- If an internal data column in Booking changes, which components must be updated?
- If Pricing temporarily stops responding, how long does Booking wait and how does it terminate?
- If one deployment fails, must other deployments also be rolled back?
- If Search scales up manyfold, does Booking suffer resource contention or connection limit exhaustion?
- If the email provider needs to be swapped, must booking business logic source code change?
- If a new feature requires modifying six services simultaneously, do current boundaries reflect the actual business domain?

Answer these questions using actual change histories, dependency graphs, source code, deployment metrics, and incident records, rather than looking only at a high-level diagram.

## 4. Increasing Cohesion with Clear Business Boundaries

### 4.1. Grouping Behaviors That Protect the Same Invariant

A **business invariant** is a condition that must remain true after every valid operation. Example: **an accommodation must not be confirmed for two guests for the same time window if policy forbids double-booking**.

Behaviors that jointly protect the booking invariant — conflict checking, holding, confirming, canceling, or expiring holds — usually belong together inside one consistent boundary (**Booking/Inventory**). Splitting them too finely and requiring multiple independent services to coordinate constantly to check an invariant turns a rule needing atomicity into a harder distributed transaction problem.

With a relational database, operations affecting an invariant may need a **database transaction** along with locking, constraints, or an appropriate concurrency control mechanism. Making two sequential API calls ("check first, write later") does not prevent double-booking under concurrent requests.

### 4.2. Grouping by Reason to Change

A component has high cohesion when changes typically stem from **the same set of rules and the same business owner**. Example:

| Change | Priority Boundary to Review | Should Not Leak Into |
|---|---|---|
| Update weekend pricing policy | Pricing | Notification, Search adapter, deployment platform |
| Change reservation hold duration | Booking/Inventory | Email provider, reporting |
| Update confirmation email template | Notification | Availability checking rules |
| Change DB redundancy configuration | Data infrastructure of the relevant component | Business logic independent of infrastructure details |
| Change user authentication mechanism | IAM/gateway and ingress integration | Unrelated business rules; authorization checks still needed where actions execute |

When a single business policy is scattered across multiple repositories and every change requires multi-team coordination, that may indicate poorly drawn boundaries.

### 4.3. Distinguishing Component Levels

- **Function/class:** focuses on a single closely related responsibility; hides internal details.
- **Module/package:** groups objects belonging to one business capability with a clear internal API.
- **Service:** has an operational boundary and communication contract; can be deployed, scaled, or recovered independently if genuinely separate.
- **Shared platform:** provides repeatable technical capabilities such as log collection, secrets management, CI/CD; avoid turning it into a dumping ground for every team's business logic.

Never treat splitting packages/classes as proof of good service boundaries. Conversely, never create a microservice for every database table or every API verb.

## 5. Techniques for Reducing Coupling in Software Design

### 5.1. Information Hiding and Stable Contracts

**Information hiding** requires a component to expose only what external callers genuinely need to know. API contracts carry business meaning; table schemas, algorithms, and storage providers are implementation details.

For example, a Booking API exposes **CreateReservation** and **GetReservationStatus** instead of letting other services directly modify the `bookings` table. Booking retains the freedom to change its schema or concurrency handling without forcing every consumer to change code, as long as the contract remains compatible.

A good contract should explicitly specify:

1. Business meaning, calling permissions, data format, and version.
2. Success conditions, handleable errors, and behavior on duplicate requests.
3. Timeouts, rate limits, pagination, and backpressure mechanisms where needed.
4. What is guaranteed to be immediately consistent versus what is only eventually consistent.
5. Backward compatibility policy and deprecation window for old fields.

Do not confuse **fewer fields** with a good contract: if essential data is omitted, clients will have to make multiple calls to assemble it, creating temporal coupling and increasing latency.

### 5.2. Dependency Inversion at the Source Code Layer

Business logic should depend on **capability interfaces** defined by its own boundary, rather than directly on cloud SDKs, DB drivers, or email libraries.

~~~java
// Domain/Application layer: describes what is needed rather than how it is stored.
public interface BookingRepository {
    Booking findById(BookingId id);
    void save(Booking booking);
}

public interface BookingEventPublisher {
    void publish(BookingConfirmed event);
}

public final class BookingApplicationService {
    private final BookingRepository repository;
    private final BookingEventPublisher publisher;

    public BookingApplicationService(
            BookingRepository repository,
            BookingEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    public void confirm(BookingId id) {
        Booking booking = repository.findById(id);
        booking.confirm();             // Enforces aggregate rules.
        repository.save(booking);
        publisher.publish(new BookingConfirmed(id.value()));
    }
}
~~~

This is an **illustrative example of depending on interfaces**, not production code guaranteeing transactional integrity. Saving the Booking and publishing the event as two separate steps leaves an **event-loss gap** if the process crashes after committing to the DB but before publishing. In a real architecture, this gap must be addressed, such as with a **transactional outbox** (writing the event to an outbox table in the same transaction with a separate publisher relaying it), or an equivalent mechanism with verified guarantees.

One adapter can implement `BookingRepository` using a managed relational database; another adapter can implement the publisher using a message broker. Swapping adapters should mainly affect the infrastructure layer. However, transaction semantics, consistency, and storage capabilities remain **architectural constraints** that must be modeled explicitly and cannot be erased behind an interface.

### 5.3. Decoupling Dependencies with Events When Business Rules Permit

Instead of Booking calling email, SMS, loyalty, and analytics sequentially within a single request, Booking can record a **BookingConfirmed** event. Interested components subscribe to process it:

~~~mermaid
flowchart LR
    Client["Web / Mobile"] --> Booking["Booking: confirm reservation"]
    Booking --> Database[("Booking DB + Outbox")]
    Database --> Relay["Outbox relay"]
    Relay --> Bus[["Event bus / Queue"]]
    Bus --> Notify["Notification"]
    Bus --> Loyalty["Loyalty"]
    Bus --> Analytics["Analytics"]
~~~

As a result, slow notification delivery or analytics updates do not block returning the booking confirmation. However, asynchrony introduces trade-offs:

- **Ordering and duplicates:** queues can redeliver messages; consumers must be idempotent and handle duplicates.
- **Eventual consistency:** other systems may update with a delay; UI and business workflows must reflect this state.
- **Operations:** requires monitoring backlog, message age, retries, dead-letter queues, schema compatibility, and replay capability.
- **Security:** events should only include necessary data; publish/subscribe permissions must be controlled.

Do not use events merely to reduce HTTP call counts if the user is still required to wait for the entire downstream chain to finish. Asynchrony makes sense when **business rules permit decoupling completion times**.

Example event contract:

~~~json
{
  "eventId": "evt-84ce",
  "eventType": "booking.confirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-18T03:00:00Z",
  "bookingId": "bk-1732",
  "propertyId": "home-25"
}
~~~

The **eventId** field helps consumers deduplicate processing; **schemaVersion** helps manage contract evolution. Do not automatically stuff emails, phone numbers, or payment details into broad events without a business requirement and corresponding access permissions.

### 5.4. Reducing Temporal Coupling When Synchronous Calls Are Required

Not every interaction fits a queue. For example, when finalizing a booking against an instant quote, Booking may need to verify pricing results or an approval rule before responding. In that case:

- Set **timeouts** aligned with the user journey's latency budget.
- Bound retries and use **exponential backoff** with jitter where appropriate; never infinitely retry an unrecoverable error.
- Use **circuit breakers**, bulkheads, or concurrency limits when needed to curb cascading failures.
- Clarify the outcome when a dependency is unavailable: fail safely, return a pending state, or use a business-approved fallback.
- Attach idempotency keys to operations that may be retried to avoid creating duplicate transactions or unintended side effects.

**Fallbacks must never violate business invariants.** You cannot "guess that a room is available" when the inventory check system is unresponsive; a search cache may be stale and should not become the source of truth for committing a booking.

### 5.5. Managing Data Dependencies

The key principle is **clear data ownership**. Modules may share a physical database in a modular monolith, provided write permissions are controlled and arbitrary cross-boundary queries are avoided. When splitting into services, each service should own its data model and write path; **database-per-service** is a common architectural pattern, not a mandatory requirement for every system.

Several techniques:

- Expose shared data via APIs/query models/events with stable semantics.
- Use **CQRS/read models** or read replicas when optimizing aggregate queries; accept and measure synchronization lag.
- Evolve schemas incrementally: **expand → migrate → contract**, avoiding forcing all consumers to switch at the exact same moment.
- Keep invariants requiring strong transactions within the same boundary whenever possible.
- Only consider sagas or compensating workflows for multi-boundary long-running transactions after clearly defining intermediate states, retries, and failures that cannot be automatically compensated.

Intentional replication of read data can reduce runtime coupling, but requires defining the source of truth, acceptable freshness, access permissions, and drift reconciliation mechanisms.

## 6. Partitioning Boundaries by Business Flow: Booking Example

Suppose the product needs to support room search, quoting, holding, payment, and sending confirmations. The architect together with product, engineering, security, and operations can map responsibilities:

| Component | Owned Capabilities / Policies | Owned Data | External Contract | Should Not Own |
|---|---|---|---|---|
| Catalog | Listing info and display status | Room metadata, descriptions | Search, view room | Authorizing booking rights at commit time |
| Pricing | Price calculation, promotions, tax rules within product scope | Price rules, quotes, and versions | Fetch time-limited quote | Directly mutating Booking state |
| Booking/Inventory | Hold/release, confirm, cancel, double-booking prevention | Bookings, holds, inventory state | Create/request confirmation/cancel; status events | Sending emails, marketing analytics |
| Payment | Payment capture requests, refunds, reconciliation per regulations | Payment attempts, provider references | Create request, return status/receive webhooks | Directly modifying hold tables |
| Notification | Channel selection, templates, sending and tracking notifications | Delivery records | Consume events and process delivery | Deciding whether a Booking transaction succeeded |

Between Pricing and Booking, clarify: **when is the price locked, how long is it valid, and who is the source of truth for the accepted price**. Between Payment and Booking, clarify: **how PENDING, CONFIRMED, FAILED, and CANCELLED states transition**, and how compensation/refund works if payment succeeds while slot confirmation fails. These decisions matter more than choosing REST vs. gRPC.

### 6.1. Confirmation Flow with Bounded Dependencies

~~~mermaid
sequenceDiagram
    participant U as User
    participant B as Booking
    participant DB as Booking DB
    participant Q as Queue
    participant N as Notification
    U->>B: Confirm booking (idempotency key)
    B->>DB: Transaction: check invariant, write booking and outbox
    alt Ineligible / conflict
        DB-->>B: Rollback / conflict
        B-->>U: Return clear status
    else Transaction succeeded
        DB-->>B: Commit
        B-->>U: Booking confirmed
        Note over DB,Q: Relay forwards event from outbox
        DB-->>Q: BookingConfirmed
        Q-->>N: Process notification (may redeliver)
        N->>N: Idempotency + send confirmation
    end
~~~

This is a **simplified flow** illustrating the boundary between booking transactions and notifications. In applications with payments, final confirmation may traverse multiple states and an orchestration or compensation workflow. Do not infer from the diagram that "exactly once" email delivery is guaranteed: real brokers and providers may only support processing/redelivery with different semantics.

### 6.2. Designing Networking and Compute While Preserving Boundaries

Business boundaries should be enforced appropriately in infrastructure:

- **Compute:** modules sharing a runtime can share autoscaling. If Booking and Search need different resource tiers or scaling policies, consider isolating by workload. Splitting deployments only pays off when corresponding operational processes exist.
- **Network:** expose only necessary endpoints, separate public and internal traffic; apply security groups/firewalls/policies aligned with actual access needs.
- **Identity & access:** separate workload identities, least-privilege access to DBs, buckets, queues, and secrets; avoid giving a single service account full system-wide permissions.
- **Data:** control write paths, connection pools, quotas, replication, and recovery models. Logically separate services sharing a single DB can still suffer shared failures and resource contention.
- **Observability:** cross-boundary tracing, logs with correlation IDs, metrics per business journey; every message/event should be traceable without exposing personal data.

**A network diagram is not a business boundary diagram.** Two components placed in two subnets are not necessarily loosely coupled; conversely, two modules running in the same process can still maintain clean source-code boundaries.

## 7. Modular Monolith or Microservices?

High-cohesion and loose-coupling design **does not mandate** microservices. Choosing a deployment model should be driven by load, number of development teams, release cadence, independent reliability requirements, and operational capability.

| Criterion | Modular Monolith | Microservices |
|---|---|---|
| Business boundaries | Internal modules/APIs, enforced via code structure and tests | Separate services/APIs/events, requiring cross-network contract governance |
| Deployment | Typically released as one application | Can deploy individual services independently if free of tight deployment coupling |
| Data transactions | Easy to keep single-DB transactions within module boundaries | Distributed transactions are hard; requires eventual consistency or choreography/orchestration |
| Scaling | Typically scales the whole application or supported workload groups | Can scale individual services |
| Network failures | Few remote calls between modules | Must handle timeouts, retries, redeliveries, partial failures |
| Operations | Fewer independent pipelines/runtimes | More pipelines, dashboards, permissions, configs, and on-call duties |
| Cost | Typically simpler initially | Incurs network, message broker, observability, and baseline overhead costs |
| Best suited for | Small/mid-sized teams, rapidly evolving domains, no need for separate operations yet | Multiple independent teams, well-established boundaries, markedly different load or release cycles |

**Anti-pattern: distributed monolith.** Multiple separate deployments exist, yet every request traverses long synchronous call chains, reads a single DB schema, and requires simultaneous releases. The system pays the cost of distributed architecture without gaining the desired independence.

The safe path is usually to **build clear module boundaries, measure demand, and extract only boundaries with compelling reasons**. When extracting, migrate data and write paths incrementally under control, avoiding a "big-bang rewrite" that heightens outage risk.

## 8. Trade-Offs Under Well-Architected Thinking

Reducing coupling and increasing cohesion improve changeability, but do not automatically make a system more secure, cheaper, or more available. Trade-offs must be verified:

| Perspective | Potential Positive Impact | Trade-Offs to Check |
|---|---|---|
| **Operational excellence** | Clearer owners and runbooks, localized changes, less release coordination | More components requiring tracing, versioning, and contract governance |
| **Security** | Least-privilege access, data isolation, smaller blast radius | More identities, entry points, and access policies to manage |
| **Reliability** | Single-component failures can be isolated, per-workload recovery | Temporal coupling and lost/duplicate events can introduce new failure modes |
| **Performance efficiency** | Targeted scaling, dedicated caches/read models | Network hops, serialization, and consistency lag increase latency |
| **Cost optimization** | Scale resource-heavy components precisely without over-provisioning all | Baseline infrastructure, traffic, queues, logs, traces, and on-call operational costs |
| **Sustainability** | Reduce over-provisioning and redundant load via right-sized boundaries | Too many idle services and duplicated data can create waste |

### Trade-Off Scenario

A team wants to split Pricing out of Booking so pricing rules can ship weekly. The expected benefit is that Pricing changes quickly without redeploying Booking. However, if every confirmation request calls Pricing over the network with high latency, Booking gains an extra point of failure.

The architect needs to discuss and measure:

1. Can Booking use a **signed/confirmed quote that is still valid**, or must it recalculate a fresh price at confirmation time?
2. If a quote expires, does the business require returning an error, recalculating, or honoring the price?
3. When Pricing fails, which states is Booking permitted to proceed to?
4. Do latency SLOs, peak traffic, network costs, and operational isolation remain acceptable?
5. Is the fast-changing part genuinely the Pricing contract, or just rule configuration that can be managed within the same module?

If these remain unanswered, **the decision to split deployments is outpacing the understanding of business process coupling**.

## 9. Measuring Independence Instead of Just Looking at Diagrams

There is no single metric proving a system is "loosely coupled." Combine quantitative measurements with assessments anchored in business journeys:

| Signal or Metric | How to Use | Caveat When Interpreting |
|---|---|---|
| **Change coupling** | Count changes that frequently require editing/releasing multiple modules together | May reflect large product initiatives, not solely poor boundaries |
| **Fan-out and call-chain depth** | Check how many dependencies and hops a request traverses | Many calls are not inherently bad; cross-check against latency/failure |
| **Deployment independence** | Measure ratio of coordinated releases and cross-service rollbacks | Can be skewed by process policies |
| **SLOs and cascading errors** | Track whether failure in one dependency disrupts another business capability | SLOs must accurately define journeys and load bounds |
| **Rate of schema changes breaking consumers** | Detect producers and consumers coupled to internal structures | Distinguish intentional contract evolution from unexpected breaks |
| **Event latency and backlog** | Measure temporal coupling converted into asynchronous flows | A stable queue does not guarantee downstream data is always fresh |
| **Cost per business transaction** | Compare network, compute, broker, and logging costs before/after splitting | Requires consistent cost allocation and comparable load |

In source code, you can map package/module dependencies and enforce architectural rules: the **Notification** module must not import internal packages of **Booking**; cloud adapters must not be accessed directly from the domain layer. These rules can be enforced in CI using ecosystem-appropriate tools (for example, architecture tests in Java), though heavy machinery is unnecessary while modules remain small and easy to inspect.

### Architecture Fitness Functions

A **fitness function** is a check or measurement verifying that an architectural constraint continues to hold during evolution. Examples:

- CI checks detecting reverse dependencies between domain and infrastructure layers.
- Contract tests catching API changes that break published consumer expectations.
- Concurrency tests for Booking verifying zero double-bookings under contention.
- Fault injection on the Email provider proving booking transactions do not depend on email.
- Measuring p95 latency and error rates after extracting a new RPC out of process.

An up-to-date architecture diagram is helpful, but **behavior under change and failure is what proves boundaries truly work**.

## 10. Common Anti-Patterns and How to Improve Them

| Anti-Pattern | Why It Causes Problems | Remediation Direction |
|---|---|---|
| **God component / SharedService** containing everything | Low cohesion, every feature touches the same choke point | Identify business capabilities and split into modules with clear owners |
| **Shared database without write access control** | Schema collisions, hard migrations, cascading bugs | Enforce a single write path/owner; expose appropriate APIs or read models |
| **Chatty distributed calls** | Latency and failure probability compound across the chain | Revisit boundaries, consolidate contracts, reduce hops, use async where appropriate |
| **Service per table** | Business invariants are fragmented, forcing cross-service transactions | Group by business rules and lifecycle instead of database tables |
| **Event soup** without owners/schemas/versions | Nobody knows who produces or consumes events, hard to debug | Manage an event catalog, schema versions, permissions, lineage, and ownership |
| **Duplicated business logic** | Two services compute different answers for the same rule | Choose a policy owner, provide a contract or conditional snapshot |
| **Over-abstraction** | Many pass-through interfaces, hard to trace | Only abstract boundaries expected to change or needing testing/adapter swaps |
| **Trying to eliminate all coupling** | Contracts become indirect and obscure, adding integration layers | Accept reasonable, explicit, and controlled dependencies |

A note on **shared libraries**: sharing logging, tracing, error types, or common clients can make sense; however, a library holding the entire domain model of multiple services easily creates deployment coupling because every business rule change forces all services to upgrade versions together.

## 11. Practical Workflow for Improving an Existing Architecture

You do not need to rewrite an entire system to improve coupling/cohesion. Iterate in small steps:

**Step 1 — Define the change goal.** Example: editing an email template should not require deploying Booking; Search traffic spikes should not exhaust the confirmation transaction's connection pool.

**Step 2 — Map the current state.** List components, owners, data boundaries, dependency directions, call chains, deployments, and failure scenarios. Distinguish **compile-time**, **runtime**, and **operational** coupling.

**Step 3 — Select invariants and capabilities.** Identify behaviors that genuinely belong in the same boundary; assign one clear owner for each core rule and data write path.

**Step 4 — Propose one small change.** Example: turn email into a consumer of outbox-published events; keep Booking with its existing DB in the first phase. Or extract Pricing into a module with an internal interface before splitting over the network.

**Step 5 — Design safely for both success and failure.** Check contracts, idempotency, timeouts, permissions, deploy/backfill procedures, rollback or roll-forward, and recovery.

**Step 6 — Measure before/after.** Track the number of modules modified per request, rate of coordinated deployments, latency, cascading failures, event lag, cost, and operational load.

**Step 7 — Record decisions and continue iterating.** Update ADRs/diagrams, share the new boundaries with teams, and verify production operations before splitting further.

### Architecture Decision Record (ADR) Template

~~~text
ADR-012: Decouple notification handling from booking confirmation flow
Status: Accepted

Context:
  Booking currently calls the email provider synchronously.
  Slowness or errors from the email provider cause booking requests to fail.

Options:
  A. Keep synchronous call, add timeout and retry.
  B. Commit Booking + outbox; emit BookingConfirmed;
     Notification processes asynchronously.

Decision:
  Choose B, because sending email is not a business condition for confirming a booking.

Consequences:
  + Reduces temporal coupling to the email provider.
  + Allows scaling Notification independently if genuinely needed.
  - Requires outbox relay, retries, idempotent consumer,
    backlog monitoring, and dead-letter message handling.

Validation:
  - When email provider is down, Booking still completes validly.
  - No event loss after DB commit.
  - Monitor notification latency and duplicate messages.

Revisit when:
  - Business rules change to require synchronous email confirmation;
  - Delivery latency targets and operational costs change significantly.
~~~

## 12. Design Self-Assessment Exercise

**Scenario:** A company has three services: Reservation, Pricing, and Notification. Reservation directly queries Pricing's price table, calls Notification synchronously before committing, and whenever Pricing's schema changes, all three services must deploy on the same day. During promotions, Notification bottlenecks drive up booking failure rates.

Answer for yourself:

1. Which forms of coupling are present? Which dependency directly hurts reliability?
2. Which rules must remain inside Reservation's transaction boundary, and which can run afterward?
3. What contract can replace querying the price table? At what point must the price be consistent?
4. Which mechanisms must be added when moving Notification to event-driven processing?
5. What tests and metrics are needed to prove the improvement succeeded?

**Suggested direction:** Use a versioned, time-bounded Pricing API/quote instead of touching Pricing's tables; lock down quote validity semantics; keep availability checks and confirmation inside the appropriate transaction boundary; convert Notification into a consumer receiving reliable post-commit events via outbox; implement deduplication, bounded retries, backlog observability, and event data protection. Test concurrent bookings, email provider outages, post-commit process crashes, schema compatibility, p95 latency, and cost to verify.

### Review Checklist

- [ ] Each component has one clear business purpose or technical capability, avoiding mixed unrelated responsibilities.
- [ ] Invariants requiring protection are identified and have a single unified owner.
- [ ] Necessary dependencies are defined with explicit contracts, failure bounds, and security controls.
- [ ] There are no unmanaged direct write paths into data owned by another component.
- [ ] Synchronous calls have timeouts, safe retries, and defined behavior when dependencies are unavailable.
- [ ] Asynchronous flows handle duplicates, loss/redelivery, schema versioning, and backlog monitoring.
- [ ] Network, compute, IAM, data, and deployment designs reflect responsibility boundaries.
- [ ] Architecture is validated via change, fault, load testing, and operational/cost metrics.
- [ ] Complexity was compared against a modular monolith or internal modules before splitting into services.
- [ ] Decisions, trade-offs, owners, and revisit triggers are documented.

## 13. Key Takeaways

**High cohesion** gives a component focused responsibilities, protects related rules, and limits its reasons to change. **Loose coupling** lets components communicate across clear boundaries, minimizes exposed internals, and reduces cascading impacts during deployment or failure.

In cloud architecture, these two principles must be applied alongside requirements for **reliability, security, scalability, performance, cost, and operations**. The goal is not having more services or more abstraction layers, but a system that **can change, be verified, and be operated** without breaking critical business invariants.
