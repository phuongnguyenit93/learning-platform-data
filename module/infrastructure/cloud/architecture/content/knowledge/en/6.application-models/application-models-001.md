# Modular Monolith Architecture and Suitability Conditions

A cloud application does not necessarily have to start with dozens of microservices. Many systems have complex business needs yet still work well as **a single unified deployable application**, as long as the source code is organized into **modules with clear boundaries**. That approach is commonly called a **modular monolith**.

In the **Application Models** chapter of the **Cloud Architecture** track, this lesson explains how to design a modular monolith from business requirements, deploy it to cloud infrastructure, and evaluate suitability conditions. The focus is on trade-offs across **reliability, security, scalability, cost, evolvability, and operations**, along with how to assess those trade-offs using Well-Architected thinking.

After this lesson, you will be able to:

- Distinguish a traditional monolith, a modular monolith, and microservices by source code, deployment, and data boundaries.
- Identify module boundaries based on business capabilities, invariants, data ownership, and rate of change.
- Design communication contracts between modules without letting modules arbitrarily access each other's internals.
- Handle transactions, events, synchronization, and database changes within a monolithic application.
- Deploy a modular monolith on the cloud with load balancing, backups, observability, and horizontal scaling.
- Recognize when to continue maintaining a modular monolith and when to consider extracting certain modules into independent services.

## 1. What is a modular monolith?

A **monolith** is generally understood as a system whose business parts are packaged and deployed together as one primary operational unit. That unit may be a Java application running on a virtual machine, a container image, or a group of processes belonging to the same release. A monolith **does not necessarily** run on a single server.

A **modular monolith** is a monolith in which the source code is divided into modules with **clear responsibilities and interfaces**, restricted cross-dependencies, hidden implementation details, and architecture governance rules. Modules are still typically built and deployed together and communicate primarily in-process, so an internal network call is not required for every business invocation.

Three things to distinguish:

1. **Source code boundary:** code is divided by business domain, such as Customer, Booking, Inventory, Billing; internal implementation is used only within the owning module.
2. **Deployment boundary:** the entire application typically has **a single release version**; when upgrading the Booking module, the application release containing that change must be deployed.
3. **Operational boundary:** CPU, RAM, processes, runtime environment, and most of the startup sequence may be shared; resource issues or failures in one module can affect the entire application.

A modular monolith can have multiple Maven/Gradle modules, but **multiple directories or multiple build projects do not automatically create modularity**. The value lies in controlling dependencies and being able to change one part without having to understand, modify, or test too many other parts.

### 1.1. Comparing common models

| Criterion | Unstructured Monolith | Modular Monolith | Microservices |
| --- | --- | --- | --- |
| Deployment packaging | Usually one unit | Usually one unit | Multiple independent units |
| Business boundaries | Easily overlap | Clear and controlled | Clear across code, APIs, and operations when well designed |
| Cross-feature calls | Direct calls, mutual access | Via in-process API/contracts | Over the network or messaging |
| Cross-feature transactions | Can share DB but dependencies are hard to control | Often leverages single-DB transactions; still requires ownership boundaries | Usually requires considering distributed consistency |
| Independent per-part deployment | No | Usually no | Yes, if boundaries are truly independent |
| Independent per-part scaling | Hard | Hard at the process level if sharing a deployment unit | Possible when each service is designed independently |
| Distributed operational overhead | Lower | Lower | Higher due to networking, discovery, monitoring, IAM, tracing, deploy |
| Primary risks | Code becomes tangled and hard to change | Boundaries erode over time; a single failure can affect the entire process | Operational complexity, network latency, partial failures, data governance |

The table describes tendencies, not guarantees for every system. A poorly designed microservice can be more tightly coupled than a monolith; a modular monolith placing heavy workloads in the same process can hit resource limits early.

### 1.2. Layered architecture is not the same as modular architecture

Organizing code by technical layers, such as Controller → Service → Repository, can still lead to a massive Service layer calling across every part. A modular monolith adds an organizational axis **by business capability**; inside each module, code is further divided into API, application, domain, and infrastructure if needed.

~~~text
Split by application-wide technical layers:
  controller/
    BookingController, InventoryController, BillingController
  service/
    BookingService, InventoryService, BillingService
  repository/
    BookingRepository, InventoryRepository, BillingRepository

Split by business modules:
  booking/
    api/, application/, domain/, infrastructure/
  inventory/
    api/, application/, domain/, infrastructure/
  billing/
    api/, application/, domain/, infrastructure/
~~~

Both structures can work, but the second makes it clear **who owns the business logic and data** for each part. It also makes it possible to enforce the rule that Booking cannot arbitrarily use Inventory's internal repository.

## 2. Visualizing architectural boundaries

Consider an equipment rental platform with four capabilities: customer management, catalog/inventory, booking, and billing.

~~~mermaid
flowchart TB
    USER["Web / mobile application"] --> LB["Load Balancer / API entry"]
    LB --> APP

    subgraph APP["Single deployable application unit: Modular Monolith"]
        API["HTTP API and input validation"]
        CUSTOMER["Customer module"]
        INVENTORY["Inventory module"]
        BOOKING["Booking module"]
        BILLING["Billing module"]
        API --> CUSTOMER
        API --> INVENTORY
        API --> BOOKING
        API --> BILLING
        BOOKING -->|"Contract: check and reserve item"| INVENTORY
        BOOKING -->|"Contract: create payment request"| BILLING
        BOOKING -->|"Contract: verify customer"| CUSTOMER
    end

    APP --> DB[("Shared database at deployment level,\ntable ownership partitioned by module")]
    BILLING --> PSP["External payment provider"]
~~~

The diagram highlights the difference between two boundary lines:

- **Outside the application:** clients call a single deployment unit through a load balancer; only one primary deployment schedule and one application-level observation point are needed.
- **Inside the application:** modules communicate only via public contracts; each module protects its own rules and data, even when sharing a process and DB.

This is a logical diagram. In actual deployment, one application release can run on **multiple replicas**; the replicas share the database or appropriate storage services. Being a monolith lies in the source code and deployment unit, not in the number of servers.

## 3. Identifying modules from business capabilities

Start by asking **which business area has its own responsibilities, rules, and lifecycle?**, rather than starting by evenly splitting Java classes across teams.

Useful signals for separating modules:

- **A relatively independent business capability:** billing, inventory management, user management, booking processing.
- **Invariants that must be protected in one place:** preventing double-booking of an asset during the same time window; preventing charging twice for the same transaction.
- **Vocabulary and data with clear owners:** booking status is managed by Booking; payment status is managed by Billing.
- **Different reasons to change:** updating pricing rules does not necessarily modify the inventory audit flow.
- **Team ownership boundaries:** one team understands and approves changes to the core rules of a module.

The concept of **bounded context** in Domain-Driven Design (DDD) is a helpful tool for discussing language and business model boundaries. However, you should not assume every table, entity, or process step is a bounded context; nor is it mandatory for every bounded context to become a microservice.

### 3.1. Trial partitioning table

| Module | Primary Responsibility | Owned Data | Provided Contracts |
| --- | --- | --- | --- |
| **Customer** | Registration, account status, contact information | Customer profiles and service eligibility | Verify valid customer; return minimal permitted information |
| **Inventory** | Assets, availability status, reservations | Assets, occupied time windows, reservation records | Check and create reservation; release reservation |
| **Booking** | Rental order lifecycle, booking and cancellation rules | Rental orders, order status, business audit trail | Create order, confirm, cancel; query status |
| **Billing** | Pricing, invoices, payments, refunds | Invoices, transactions, payment reference codes | Create payment request, record result, refund per authorization |

This boundary is only an initial proposal. If pricing policies are tightly coupled to each asset configuration and change together with reservation rules, you may need to reconsider the boundary between Inventory and Billing. Validate using **real use cases and business events** before deciding.

### 3.2. Choosing the right granularity

A module that is too large creates friction because too many responsibilities are bundled together; too many small modules create excessive contracts, dependencies, and simultaneous changes without delivering real independence.

Verification questions:

1. Can the module's responsibility be described in a few clear sentences?
2. Are the most important rules enforced inside the module that owns them?
3. Does a typical feature change frequently require modifying multiple modules even when the logic belongs to one place?
4. Is there a sufficiently stable interface for other modules to use without knowing internal DB structures?
5. If this module is extracted later, which data and transaction dependencies would make that difficult?

You do not need to achieve "absolute independence." The goal is **intentional, understandable, and controlled dependencies**.

## 4. Rules for designing module boundaries

### 4.1. Modules publish contracts, hide implementation

Between two modules, there should be an interface with business semantics: **reserve item**, **confirm order**, **create invoice**, instead of exposing entire repositories or entities to each other.

Principles:

- Other parts depend only on a module's **public API**; implementation code, repositories, table schemas, and internal rules must not become an implicit API.
- APIs describe business operations and outcomes, avoiding returning internal objects that could be mutated outside the owner's control.
- Parameters and return types should be stable and concise; use clear identifiers and DTOs/value objects.
- The module owning an invariant must validate that invariant itself. Callers must not assume "it was already checked at the API gateway."
- Dependency directions must be explicit and avoid cycles; do not introduce a massive "common" module holding all domain objects as a way to bypass boundaries.

### 4.2. Example structure of a Java application

~~~text
com.example.rental
├── bootstrap/
│   └── RentalApplication.java
├── customer/
│   ├── api/
│   │   └── CustomerQuery.java
│   ├── application/
│   ├── domain/
│   └── infrastructure/
├── inventory/
│   ├── api/
│   │   ├── InventoryReservation.java
│   │   └── ReserveItemCommand.java
│   ├── application/
│   ├── domain/
│   └── infrastructure/
├── booking/
│   ├── api/
│   ├── application/
│   ├── domain/
│   └── infrastructure/
├── billing/
│   ├── api/
│   ├── application/
│   ├── domain/
│   └── infrastructure/
└── platform/
    ├── security/
    ├── database/
    └── observability/
~~~

Package names are only examples. You can use a single project with package dependency rules or multiple build modules so the compiler helps restrict access. **The number of build projects does not determine modularity**, though build rules and automated checks help keep boundaries from eroding.

### 4.3. Example Java contract

A public interface of the Inventory module might look like:

~~~java
package com.example.rental.inventory.api;

import java.time.Instant;
import java.util.UUID;

// Illustrative model: public contract of Inventory
public interface InventoryReservation {
    ReservationResult reserve(
        UUID itemId,
        Instant startsAt,
        Instant endsAt,
        UUID bookingRequestId
    );

    void release(UUID reservationId, UUID bookingRequestId);
}

public record ReservationResult(
    UUID reservationId,
    boolean accepted,
    String reasonCode
) {}
~~~

In real Java code, public top-level types usually must be placed in **separate `.java` files** matching the type name. The snippet above is combined to show the contract in one place; in implementation, split the files and add input validation.

Booking only knows about `InventoryReservation` and `ReservationResult`. Booking **must not** import `InventoryRepository` or read the asset table directly to perform reservation logic itself. The rule against overlapping rental periods must reside in Inventory, backed by appropriate locking, constraints, or transactions to prevent race conditions when two requests arrive concurrently.

An example adapter using the interface:

~~~java
package com.example.rental.booking.application;

import com.example.rental.inventory.api.InventoryReservation;
import com.example.rental.inventory.api.ReservationResult;
import java.time.Instant;
import java.util.UUID;

// Simplified to illustrate dependency direction between modules
public final class BookingApplicationService {
    private final InventoryReservation inventory;

    public BookingApplicationService(InventoryReservation inventory) {
        this.inventory = inventory;
    }

    public ReservationResult reserveForBooking(
            UUID itemId,
            Instant from,
            Instant to,
            UUID requestId) {
        return inventory.reserve(itemId, from, to, requestId);
    }
}
~~~

This example only shows **dependency direction**. It does not yet implement full validation, transactions, order persistence, idempotency, or handling reservation failure cases.

### 4.4. Dependencies between modules must have rules

For any relationship A → B, answer:

- Why does A need B, and can the set of invoked operations be narrowed?
- Does the operation need to share the same transaction to protect correctness?
- Does A depend on B's internal tables or classes?
- If B changes its data structure, must A change as well?
- Is there a dependency cycle A → B → C → A? If so, are the boundaries or business coordination flawed?

Use dependency diagrams, architecture tests, or build-time rules to prevent access to internal packages. For example, a target rule: **booking must not depend on `inventory.domain` and `inventory.infrastructure`**; other application modules may only use `inventory.api` according to defined policy.

A modular monolith still needs continuous architecture reviews. If "just calling the repository temporarily for speed" becomes a habit, the boundaries on the diagram lose their meaning.

## 5. Data ownership within a single database

A modular monolith typically uses **a single physical database**. This is an operational and transactional advantage, but avoid equating "same database" with "every module can manipulate every table."

Distinguish between:

- **Sharing the database management system:** multiple modules share one DB engine, DB cluster, connection pool, and backup schedule.
- **Arbitrarily sharing data structures:** modules directly read/write the same tables without an owner, creating hidden coupling.

The second breaks independent evolvability and causes difficulties if a service needs to be extracted later.

### 5.1. Assigning tables to modules

| Module | Example Owned Tables | Who Can Modify? | How Others Query |
| --- | --- | --- | --- |
| Customer | customer_profile, customer_status | Customer | CustomerQuery or managed data projections |
| Inventory | asset, asset_reservation | Inventory | InventoryAvailability/InventoryReservation |
| Booking | booking, booking_line, booking_history | Booking | BookingQuery |
| Billing | invoice, payment_attempt | Billing | BillingQuery, business events |

Teams can use separate schemas within the same database, table naming conventions, appropriate DB-level permissions, and migration checks to make ownership explicit. Some DBMSs offer useful cross-table constraints; using them is a trade-off between data integrity and coupling. Document the intent rather than applying them everywhere by default.

### 5.2. Reporting queries across multiple modules

A reporting requirement such as "monthly revenue by asset type" often needs data from Booking, Inventory, and Billing. Do not let an arbitrary endpoint become a place to write ad-hoc SQL across all modules' tables.

Options:

1. **Read model/reporting module:** the reporting module receives published data or events from source modules; accepts synchronization latency if appropriate.
2. **Approved query:** a unified query layer with clear ownership and change control; useful when reports require high freshness and the project is still small.
3. **Data warehouse/analytics:** controlled extraction for heavy analytical workloads; reduces the impact of reporting on the transactional DB.

Each option has different costs and latencies. If choosing to read source tables directly, record the **data coupling debt** and the approver before expanding it into a general pattern.

## 6. Transactions, consistency, and events between modules

A practical advantage of a modular monolith is that modules can participate in **the same single-database transaction** when a business operation requires atomicity. However, this does not happen automatically just because classes run in the same JVM; transactions must be configured properly and the steps must genuinely use the same transaction manager and transactional resource.

### 6.1. When to use synchronous calls

Direct calls through an in-process interface are appropriate when:

- The caller needs an immediate answer to complete the use case.
- There is a cross-module invariant that the system must verify before committing.
- There is no overly long dependency chain that increases lock hold times and cascading failure risk.

For example: Booking asks Inventory to reserve an asset and creates the order in the "reserved" state only if Inventory accepts. With the same database and transaction manager, one transaction can ensure both the reservation record and the order status are committed or rolled back together.

However, large transactions spanning many modules, locking many tables, and running for a long time can cause **lock contention**, deadlocks, higher response times, and poor scalability. Set **transaction boundaries around business invariants**, and avoid wrapping an entire long flow in a single transaction by default.

### 6.2. When to use internal events

Events are appropriate when a module has finished its own work and other modules need to know in order to perform tasks that **do not have to happen in the same transaction**.

Example:

~~~text
Booking confirms order
    |
    +--> Updates data owned by Booking
    |
    +--> Publishes BookingConfirmed event
              |
              +--> Notification prepares to send alert
              +--> Reporting updates metrics
              +--> Loyalty updates reward points (if applicable)
~~~

Events reduce direct coupling between producer and consumers, but introduce concerns around **ordering, duplicate events, failed delivery, retries, and observability**. Do not add a distributed message broker just because microservices use one. Within a single process, an internal event mechanism can be simpler; when the business requires guaranteeing no event is lost after a DB commit, durable persistence must be considered.

### 6.3. Why in-memory event publishing alone may not suffice

Suppose the application writes "order confirmed" to the DB and then submits an event to an in-JVM executor. If the JVM stops in between, the order may be committed while the event is never processed. For a non-critical notification this might be acceptable; for updating financial obligations, a more reliable mechanism is required.

The **transactional outbox** is one option: write both the business record and the event record in a single DB transaction, then have a worker read the outbox to deliver to consumers; the worker must retry and process idempotently. An outbox adds complexity, so apply it only where genuinely needed.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant B as Booking module
    participant DB as Database
    participant W as Outbox worker
    participant N as Notification/Consumer

    C->>B: Confirm booking
    B->>DB: Transaction: update booking + insert outbox
    DB-->>B: Commit
    B-->>C: Confirmed
    W->>DB: Read unprocessed outbox
    W->>N: Send BookingConfirmed(eventId)
    N-->>W: Acknowledge processing
    W->>DB: Mark outbox as sent
~~~

Between N succeeding and W recording the status, the worker could fail; the next retry will send it again. Therefore, consumers still need deduplication keys such as `eventId` or a business key, rather than assuming "exactly once" across the entire flow.

### 6.4. Interacting with external services

HTTP calls to payment providers, email services, or SaaS **are not** part of the application database's ACID transaction. Avoid holding a DB transaction open while waiting for an external response whenever possible. Instead, use explicit business states (`PENDING_PAYMENT`, `CONFIRMED`, `FAILED`, `CANCELLED`), idempotency keys, bounded retries, and compensation or reconciliation processes when needed.

The difference from microservices is that a modular monolith can keep simple **the parts that truly belong to the same internal transaction**; however, every boundary to external services still requires distributed failure design.

## 7. How a modular monolith runs on the cloud

A modular monolith **does not mean a single machine**. A single build artifact can run across multiple VMs, containers, or pods. A load balancer distributes requests across replicas; persistent data lives in a managed database and appropriate object storage.

~~~mermaid
flowchart TB
    CLIENT["Users / client apps"] --> LB["Load Balancer"]
    LB --> A1["Replica 1: full modular monolith"]
    LB --> A2["Replica 2: full modular monolith"]
    LB --> A3["Replica N: full modular monolith"]
    A1 --> DB[("Managed relational database")]
    A2 --> DB
    A3 --> DB
    A1 --> CACHE[("Cache / session storage if needed")]
    A2 --> CACHE
    A3 --> CACHE
    A1 --> OBJ[("Object storage")]
    A2 --> OBJ
    A3 --> OBJ
    A1 --> OBS["Logs / metrics / traces"]
    A2 --> OBS
    A3 --> OBS
~~~

To run multiple replicas safely, you must:

- **Do not rely on a single replica's local RAM for critical session state.** Use tokens, appropriate session storage, or a shared state model as required.
- **Do not write critical business data solely to the container filesystem.** Use DB/object storage; understand ephemeral disks and backup policies.
- **Manage schema migrations** so old and new versions can coexist during rollout windows if needed.
- **Check background jobs:** a scheduler running in all three replicas could execute three times without proper coordination, locking, or work-queue mechanisms.
- **Bound connection pools:** increasing replicas also increases total connections; this can bottleneck the DB.
- **Configure sensible readiness and liveness probes:** unnecessary dependency failures in health checks can pull all replicas out of load balancing.

### 7.1. Horizontal scaling and practical limits

Suppose an application has 4 modules, where Booking uses 70% of CPU and Catalog uses only 5%. When scaling from 2 to 6 replicas, the system still runs **all modules on all 6 replicas**. This approach is usually simple and remains efficient when traffic across parts grows roughly together.

However, if a report-generation job consumes high RAM or AI inference saturates CPU, scaling the entire monolith can be costly and hurt latency for other features. Before deciding to split into microservices, consider:

1. Moving heavy tasks to a separate **job/worker** in the same codebase with a **separate deployment unit** if the organization accepts a hybrid model; in that case, explicitly document that the architecture has expanded beyond a pure single deployment unit.
2. Optimizing queries, caching, and queues to separate synchronous load from batch tasks.
3. Setting resource limits and concurrency limits per processing path; monitoring cross-impact.
4. Splitting into an independent service only when operational/scaling benefits clearly outweigh distributed overhead.

**Key point:** replicating the monolith can increase throughput, but it does not eliminate DB limits, hot data, or lock contention. Measure bottlenecks before adding more replicas.

### 7.2. Reliability with multiple replicas

Running multiple replicas across appropriate availability zones reduces the risk of a single process or zone failing. However, **a logic bug in a release** can affect all replicas; the **shared DB** can be a single point of failure if not properly designed for HA and backups.

Questions to measure:

- When a replica stops abruptly, how are in-flight requests retried and could duplicate writes occur?
- When the DB is slow or loses connectivity, which modules fail, and are there circuit breakers/timeouts for out-of-process dependencies?
- When a release has a bug, can the application be rolled back and how are already-migrated schemas handled?
- What are the RTO/RPO of the DB, object storage, and queues? Have data restoration tests been performed?
- As replicas increase, can database capacity keep up?

A modular monolith can achieve high availability when deployed properly. Yet because processes are shared, **fault isolation** is weaker than in a model with truly independent services; do not claim each module has an independent SLA if the infrastructure does not guarantee it.

## 8. Security and compliance along business boundaries

Splitting into modules helps manage responsibilities and policies, but **package boundaries in a JVM are not security boundaries equivalent to processes or networks**.

For example, Billing may allow only the Accountant role to issue refunds; Booking may be allowed to "create a payment request" but must not arbitrarily invoke "refund." If all modules run under the same DB identity, you cannot expect the DB to automatically detect a statement accessing the wrong business layer; access must be enforced at the application layer and optionally reinforced with DB permissions by design.

Principles:

- **Authentication** identifies who/what is calling the system; **authorization** verifies the right permissions for the operation and data object.
- Each module must validate permissions and invariants at critical action boundaries; do not rely solely on the UI hiding action buttons.
- Business endpoints must verify tenant boundaries and record ownership to prevent cross-customer data leaks.
- Strip sensitive information from logs; record only necessary audit trails with appropriate retention and access controls.
- Manage secrets through proper security mechanisms, never embed them in code or artifacts; encrypt data in transit and at rest based on classification.
- When sharing a database, separate query, operator, and migration permissions by responsibility rather than granting overly broad admin rights.

**Compliance** depends on data type, jurisdiction, industry, and contracts. Even with a single database, you still need a data inventory, locations of primary/replica/log copies, retention schedules, and deletion procedures. Separating packages is not enough to prove compliance with a regulatory requirement.

## 9. Observability: seeing both the whole system and individual modules

The "single process" nature makes internal tracing simpler than network calls, but it can hide which module is consuming resources or driving up errors. The system needs observability by **module, use case, dependency, and data**.

Key signals:

| Scope | Metrics or Evidence |
| --- | --- |
| Whole application | Throughput, p95/p99 latency, error rate, uptime, memory, GC, CPU |
| Per use case | Order creation duration, booking success rate, cancellation and payment processing rate |
| Per module | Execution time, business errors, request count, related pools/queues |
| Database | Query latency, slow queries, lock wait, connection pool, replication lag |
| Background jobs | Queue depth, retries, count of failed or duplicate jobs |
| Events/outbox | Age of unsent records, delivery success rate, duplicate and slow-processed events |
| Release changes | Build version, deploy time, post-deploy errors, rollbacks |

Include appropriate `moduleName`, `operation`, `correlationId`/`traceId`, and `outcome` fields in logs/traces; avoid exposing PII. A request flowing from Booking through Inventory and Billing must be traceable across module boundaries. Define SLOs around business outcomes, such as order creation success rate and p95 order creation latency, rather than merely measuring "JVM is running."

## 10. Organizing testing and protecting architecture

A modular monolith succeeds when module boundaries are preserved across many changes and contributors, not just on the initial diagram.

### 10.1. Necessary verification layers

- **Module unit tests:** verify invariants and business behavior within a single module.
- **Internal contract tests:** verify interfaces and failure scenarios that other modules depend on.
- **Integration tests:** verify repositories, transactions, and data against a DB behaving close to production.
- **Critical end-to-end tests:** create order, reserve item, pay, cancel/refund with error handling.
- **Architecture tests:** prevent other modules from accessing internal packages, detect dependency cycles, detect cross-module repository access.
- **Load/failure tests:** verify p95/p99, replica scaling behavior, DB bottlenecks, and behavior when external partners fail.

Do not write trivial tests just to prove a getter returns a field. Test the places that risk breaking business logic, eroding boundaries, or causing operational incidents.

### 10.2. Checking dependency rules

A conceptual rule set:

~~~text
Allowed:
  booking.application  -> inventory.api
  booking.application  -> customer.api
  booking.application  -> billing.api

Forbidden:
  booking.*            -> inventory.infrastructure
  booking.*            -> inventory.domain
  billing.*            -> booking.infrastructure
  inventory.*          -> booking.infrastructure

No cyclic module dependencies.
~~~

You can use ArchUnit, Java module rules, build dependency constraints, or equivalent tools to automate these rules. Exact configuration depends on project structure; verify actual dependency directions rather than checking directory names alone.

### 10.3. CI/CD structure

A typical pipeline:

~~~mermaid
flowchart LR
    C["Commit / Pull Request"] --> L["Compile, lint, and architecture checks"]
    L --> T["Unit + integration + contract"]
    T --> B["Build single application artifact"]
    B --> SEC["Scan config, libraries, container"]
    SEC --> ST["Deploy staging"]
    ST --> E2E["E2E + smoke + migration check"]
    E2E --> P["Canary/rolling deploy production"]
    P --> O["Monitor SLOs, rollback if needed"]
~~~

Because multiple modules share one release, pay special attention to **the impact of schema changes, configuration changes, and rollback capability**. Rolling deployments across multiple replicas often mean old and new versions use the DB simultaneously; use backward-compatible schema changes during transition phases.

## 11. Rules for safe database changes

Suppose Billing needs to rename a column representing payment status. If renamed directly in one migration and new code is deployed, old running instances may fail.

An **expand–migrate–contract** cycle:

1. **Expand:** add the new column/structure while keeping the old column valid; release code capable of reading old and new states as planned.
2. **Migrate:** backfill existing data and transition write behavior in phases; verify consistency, monitor errors and legacy jobs.
3. **Contract:** once all processes use the new structure and the rollback window has closed, remove the old structure.

This cycle reduces risk when running multiple replicas, but **does not guarantee every data change can always be rolled back**. For data that must be preserved, prepare a one-way migration plan, backups, and pre-tested recovery procedures.

Migration ownership rule: **whichever module owns the data is responsible for schema changes**, even when all migrations are packaged in the same deployment pipeline.

## 12. When is a modular monolith a good fit?

Instead of asking "Are microservices more modern?", examine business requirements and operational capability.

### 12.1. Conditions that usually favor a modular monolith

1. **The business domain is still evolving and needs fast learning.** Real boundaries are not yet stable; a unified application makes refactoring contracts and data easier.
2. **One or a few teams work together on the product.** There is no need yet for frequent independent deployments and operations.
3. **Use cases require strong transactions across multiple capabilities.** You can leverage one DB and transaction manager if boundaries are well controlled.
4. **Traffic can be met through application optimization, DB tuning, and scaling the application artifact.** There are no extreme differences in requirements across parts.
5. **Operational budget is limited.** No need yet to absorb the cost of service discovery, internal networking, distributed tracing, service mesh, or many independent pipelines.
6. **Reliability requirements do not mandate strict fault isolation per capability.** The whole application can share a deployment lifecycle and failure blast radius.
7. **The team has the discipline to uphold module boundaries.** There are owners, code reviews, architecture tests, and enforced dependency rules.

A modular monolith also fits mature products if operational needs and rate of change remain unified. It is **not merely a mandatory stepping stone** before microservices.

### 12.2. Signals to consider extracting independent services

- One part of the system needs to **scale by a large factor** compared to others, making scaling the whole monolith unreasonably expensive.
- Teams need independent releases, and a shared deploy schedule repeatedly creates conflicts or measurable delivery delays.
- A high-risk workload requires **process/resource isolation** or distinct availability targets.
- Regulatory, data, or network requirements mandate isolation at the infrastructure and independent-identity level.
- One part must use a significantly different runtime, technology stack, or resource lifecycle.
- A module already has sufficiently decoupled APIs and data that extraction cost is lower than the benefit of independence.

These signals are **evaluation triggers**, not automatic mandates for microservices. Before splitting, measure: CPU/RAM share per part, failure impact, deploy frequency and work delayed by shared deploys, infrastructure cost, and operational staffing.

### 12.3. Reasons that are not enough to split into microservices

- The application has "a lot of lines of code" without measured structural or operational problems.
- There are multiple development teams, when collaboration and ownership can still be solved through modules.
- An endpoint is slow because a query lacks an index and has not been profiled or optimized.
- Wanting to use Kubernetes or containers; a modular monolith deploys cleanly on containers/Kubernetes as well.
- Wanting to go event-driven; a modular monolith still supports internal events and outbox when needed.
- Wanting fault tolerance; a multi-replica, multi-AZ monolith with HA DB still satisfies many availability targets.

## 13. Application model decision matrix

| Question | Modular monolith usually fits when… | Evaluate extracting services when… |
| --- | --- | --- |
| Do modules need independent releases? | Can release on a shared cadence | Different release schedules frequently slow down changes |
| Is per-capability scaling needed? | Load is relatively uniform or total load is within limits | Load/cost disparities across parts are large and sustained |
| Data and transaction complexity? | Many invariants need local transactions | Data is already independent and asynchronous communication is acceptable |
| Team operational capability? | Small team, no distributed service operations platform yet | Appropriate SRE/platform, observability, and automation are in place |
| Fault/resource isolation? | Single-part failures can be handled within one process | Dedicated failure, resource, or compliance boundaries are required |
| Stability of business boundaries? | Still exploring, need fast refactoring | Relatively stable with well-defined contracts |
| Overall cost? | Distributed development and operational overhead is unwarranted | Proven benefits of independence outweigh added cost |

**Evaluation rule:** use measurable requirements instead of team count, user count, or lines of code as an absolute threshold. There is no fixed number like "above X requests/sec you must use microservices"; the outcome depends on processing work, DB, cache, resources, and SLO targets.

## 14. Practical example: equipment rental platform

Suppose a product lets customers browse equipment, check availability, create rental orders, pay, and receive notifications. This is an **illustrative scenario** for choosing a model, not a description of a specific company's system.

### 14.1. Assumed requirements

| Requirement | Design Assumption | Impact |
| --- | --- | --- |
| Development | Two teams build together and release weekly | One shared release pipeline remains acceptable |
| Traffic | Load mainly comes from catalog browsing and availability lookup | Need read-path separation, caching, and query optimization |
| Business logic | Cannot double-book the same piece of equipment for the same period | Needs invariants and race-condition handling in Inventory |
| Payment | Payment via external provider | Needs states, idempotency, retries, and reconciliation |
| Availability | Targets defined via business SLOs and maintenance windows | Needs replicas, health checks, database HA, and testing |
| Data | Contains personal information and rental order records | Needs access control, encryption, retention, and proper logging |

Missing requirements such as RTO/RPO, actual load levels, data residency, and cost limits must be gathered before finalizing the deployment plan.

### 14.2. Initial modular monolith design

- **Catalog:** publishes catalog, search, and filtering; can use caching for read-heavy data.
- **Inventory:** determines availability and time-based reservations; guards against double-booking under concurrency.
- **Booking:** orchestrates the rental order lifecycle; records states with business meaning.
- **Billing:** manages invoices and payment results; integrates with partners using idempotency keys.
- **Customer:** provides valid status and permitted customer info.
- **Notification:** consumes business events after commit to send email/SMS without slowing down core transactions.

All six modules can be built into one artifact and run as multiple replicas behind a load balancer. The database is shared at the infrastructure level, while tables have **owning modules**. Background jobs use queues/outbox and appropriate checkpoints to avoid duplicate execution as replicas scale.

### 14.3. Controlled order-creation flow

~~~mermaid
sequenceDiagram
    participant U as Customer
    participant B as Booking
    participant C as Customer
    participant I as Inventory
    participant DB as Database
    participant P as Payment provider
    participant N as Notification

    U->>B: Create rental request(requestId)
    B->>C: Verify valid account
    C-->>B: Result
    B->>I: Reserve asset / time window
    I->>DB: Check and create reservation in appropriate transaction
    DB-->>I: Result
    I-->>B: reservationId or rejection
    B->>DB: Save order PENDING_PAYMENT
    DB-->>B: Success
    B-->>U: Order ID + payment-required status
    U->>P: Pay via provider flow
    P-->>B: Result callback/webhook
    B->>DB: Verify, record idempotent state
    B-->>N: Post-commit event / via outbox
~~~

The diagram intentionally simplifies how reserving and saving the order are coordinated. If the system requires reservation and order creation to succeed or fail together, they must be placed inside **a proper transaction boundary** and tested. In addition, there must be reservation expiration times, release rules on timeout/payment failure, and handling for late or duplicate callbacks.

### 14.4. What happens when load increases?

Suppose during a promotion, catalog search requests spike and the DB becomes the bottleneck. Do not assume "we must split Catalog into a microservice."

A sensible evaluation sequence:

1. Identify p95/p99 and slow queries; distinguish application CPU, DB, I/O, and lock contention.
2. Optimize indexes, pagination, caching, and request limits; verify cache invalidation.
3. Scale application replicas and connection pools within DB limits; check the impact on Booking.
4. Once data proves Catalog has a long-term distinct load lifecycle, evaluate separating read capability or moving part of search to a dedicated service.
5. Account for additional data sync, cache invalidation, deployment, observability, and access control costs before finalizing.

Thanks to early module boundaries, Catalog can be extracted in a controlled way if truly needed, but splitting a service **does not automatically fix** a poor data design or query algorithm.

### 14.5. When payment failures affect the entire application

If the payment provider is slow, synchronous calls holding threads too long can affect Booking and other modules in the same process. Immediate mitigations include timeouts, bulkheads/concurrency limits, appropriate retries, and keeping external waits out of DB transactions. If strong isolation is still needed afterward, consider extracting Billing or the payment adapter into an independent deployment unit. Decisions should be based on **actual incident frequency and blast radius**.

## 15. Path from modular monolith to services when needed

A good modular monolith creates the ability to split **selectively**; the goal is not to turn every module into a microservice.

Suggested process:

1. **Measure the pain point:** define the reason for splitting and success criteria, such as reducing scaling costs or reducing how often payment failures affect order creation.
2. **Choose a module with stable boundaries:** clearly used contracts, minimal cross-module transaction and data query dependencies.
3. **Remove internal dependencies:** switch callers to contract APIs, trim shared libraries and cross-module SQL queries.
4. **Separate data ownership:** the new module becomes the sole writer of its owned data; design safe querying, replication, and data migration mechanisms.
5. **Add a network boundary:** standardize authn/authz, timeouts, retries, idempotency, tracing, and API versioning.
6. **Shift traffic in phases:** test, canary, observe, and keep a rollback path if errors occur.
7. **Re-evaluate transactions:** replace former local transactions with business states, outbox, and appropriate consistency mechanisms if needed.
8. **Remove the old path:** once data and traffic have fully migrated, clean up unused cross-access points.

A form of the **strangler pattern** can be used: place a stable interface in front of the old system, move each capability to the new service, and gradually turn off the old execution path. However, if data is split in two without an authoritative source, extraction will cause hard-to-recover errors.

### 15.1. What changes after extraction

Previously, Booking called `InventoryReservation` as an in-process method. After extracting Inventory:

- Every call incurs **network latency** and can time out even when the receiver succeeded.
- Both sides may be deployed on **different versions** for extended periods.
- A shared single-DB transaction may no longer be feasible or desirable.
- Service-to-service permissions and separate data policies are required.
- Partial failures and eventual consistency states must be observable.

Therefore, having good internal interfaces **helps reduce coupling**, but it does not turn extraction into a simple transport swap.

## 16. Common mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Splitting folders by domain while keeping every class public | Parts import arbitrarily; boundaries exist only on diagrams | Hide implementations; enforce dependencies at build time |
| A Shared/Common module holding all entities and services | Every change ripples across the entire app | Share only truly common foundational primitives; keep domain models owned |
| Booking directly reads/writes Inventory tables | Breaks invariants and makes module changes hard | Access via contracts and let Inventory enforce rules |
| Modules call each other in cycles | Causes tight coupling; hard to test and extract | Review boundaries; separate orchestration and clear contracts |
| Using events for every operation | Hard to reason about consistency and debug even when immediate answers are needed | Use synchronous calls when results are required; events for post-commit work |
| Publishing events only in RAM while requiring zero loss | Crashes after commit drop tasks | Use outbox or durable mechanisms when business requires |
| Creating very long transactions with external HTTP calls inside | Long locks, timeouts, cascading failures | Design explicit states and short appropriate transactions |
| Letting multiple replicas run the same scheduler uncontrolled | Jobs execute multiple times | Use appropriate leader election/lease/queues and idempotent handling |
| Thinking a monolith cannot scale | Lack of optimization and HA design | Scale replicas, tune DB/cache, measure bottlenecks |
| Thinking a modular monolith isolates faults like microservices | A RAM/GC issue affects the entire application | Measure blast radius, set resource limits, and split when truly needed |
| Splitting microservices per table | Chatty network calls, circular dependencies, hard-to-keep consistent data | Split by business capability and data ownership |
| Ignoring DB migration/rollback | New deploys break old versions and cannot roll back | Phased schema changes, backups, tested recovery |

## 17. Recording an Architecture Decision Record (ADR)

When choosing a model, record the decision and re-evaluation conditions. This is a hypothetical example:

~~~yaml
decision_id: ADR-001
title: Use a modular monolith for the initial rental platform
status: accepted
context:
  teams: 2
  release_cadence: weekly
  business_domains:
    - customer
    - inventory
    - booking
    - billing
  transactional_consistency: required_for_booking_and_inventory
decision:
  application_model: modular_monolith
  deployment_unit: single_application_artifact
  data_platform: shared_relational_database_with_module_ownership
  internal_communication: explicit_module_contracts
  external_side_effects: durable_events_where_required
constraints:
  - no_cross_module_repository_access
  - no_cyclic_module_dependencies
  - mandatory_architecture_tests
  - independently_owned_data_migrations
consequences:
  benefits:
    - simple_initial_deployment
    - local_transactions_where_appropriate
    - reduced_distributed_operations
  limitations:
    - shared_release_cycle
    - shared_process_failure_domain
    - scaling_whole_application
review_triggers:
  - sustained_module_specific_scale_cost
  - measured_release_coordination_delay
  - repeated_cross_module_incidents
  - new_data_isolation_requirement
owner: architecture_team
review_date: project_defined
~~~

This is a decision document, not a cloud service configuration file. Its value lies in **assumptions, trade-offs, and review triggers**. When team count, cost, SLOs, or data constraints change, the organization has a factual basis to revisit the decision instead of debating by intuition.

## 18. Evaluating with Well-Architected thinking

| Aspect | Practical Questions |
| --- | --- |
| **Security** | Does each module enforce permission policies per action? Is there cross-tenant data leak risk? Are log/backup locations controlled? |
| **Reliability** | How many capabilities does one process failure affect? Are there multiple replicas/zones, DB HA, backups, and tested restores? Do calls to external services have timeouts and retry handling? |
| **Performance Efficiency** | Do critical use cases meet p95/p99 targets? Is the bottleneck in DB, CPU, or external dependencies? Is scaling the whole application cost-effective? |
| **Cost Optimization** | What does a shared pipeline and shared DB save? Are lightly used modules being over-replicated just to scale a high-load module? |
| **Operability** | Are deploys/rollbacks easy and reliable? Are there per-module metrics and logs? Who owns migrations, contracts, and incident response? |

Some Well-Architected Framework editions also list dedicated pillars such as **Operational Excellence and Sustainability**; the exact pillar count and naming depend on the chosen provider's framework. The table above focuses on trade-offs directly relevant to this lesson's topic and does not claim to replace an entire official framework.

### Design acceptance checklist

- [ ] Each module has clearly documented business responsibilities, an owner, and public contracts.
- [ ] There are no circular dependencies or arbitrary cross-module repository/implementation access.
- [ ] Critical invariants and data ownership live inside the responsible module.
- [ ] Internal transactions, post-commit events, and external integrations have designed failure semantics.
- [ ] Replicas operate without depending on local RAM or local files for durable state.
- [ ] There is a plan for app/DB scaling, preventing duplicate job runs, and bounding connection pools.
- [ ] Appropriate authn/authz, tenant checks, secret management, and auditing are in place.
- [ ] Migration process is compatible with rolling deploys; rollback and restore are accounted for.
- [ ] Latency, errors, resources, queues/outbox, and business SLOs are measured per module.
- [ ] The modular monolith decision has an ADR, trade-offs, and clear review triggers.

## 19. Architecture thinking exercise

A SaaS platform currently has **a team of 8 engineers**, releasing twice a week. Features include accounts, billing, search, attachment processing, and reporting. Search load spikes during peak hours, while heavy summary reports run only nightly. Billing data requires high correctness; the team does not yet have a full distributed tracing system.

Propose an initial application model by answering:

1. Which business modules would you separate? What tables and rules do those modules own?
2. Which communications should use synchronous calls, and which suit post-commit events? Which tasks require idempotency?
3. If using a modular monolith, how would you deploy multiple replicas on the cloud, and how would you handle scheduled reporting so nightly load does not affect the API?
4. What conditions and metrics would lead you to consider extracting search or reporting into an independent deployment?
5. What checks would you run to verify the system meets security, availability, and cost requirements?

A well-founded proposal could start with a modular monolith to simplify transactions and operations, while separating heavy reporting workloads with appropriate queues/jobs. If an additional deployment unit is needed, clearly describe the impact on transactions, data, and operations. Do not base the conclusion solely on engineer headcount or feature count.

## 20. Key takeaways

A modular monolith is a design choice for **a tightly structured modular application**, deployed as a single unit while keeping business capabilities independent at the code and contract level. It fits when rapid development is needed, multiple transactions require correctness, infrastructure scale does not yet demand per-part scaling, and the team wants to keep operational overhead low.

Modularity does not exist automatically from package naming. It must be maintained through **data ownership, public APIs, controlled dependency direction, architecture tests, and release discipline**. When the need for separation grows, these boundaries enable a methodical transition, while still requiring solutions for new distributed-system concerns such as timeouts, versioning, duplicate events, and eventual consistency.

In Cloud Architecture design, the deciding question is not "Are monoliths or microservices more popular?", but **which model satisfies business requirements, SLOs, and data constraints with the most reasonable complexity and total cost at this point in time**.
