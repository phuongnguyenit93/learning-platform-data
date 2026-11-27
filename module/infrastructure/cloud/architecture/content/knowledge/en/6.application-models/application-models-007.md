# Partitioning Components by Scalability and Change Cadence

When designing a cloud application, the question "how many services should we have?" is often asked too early. A more useful question is: **which parts experience different loads, change at different rates, and truly need independent development, deployment, and operations?** Answering that gives a sound basis for choosing an application model, defining component boundaries, and laying out compute, networking, and data.

In **CLOUD_ARCHITECTURE**, component partitioning is an architectural decision tied simultaneously to **scalability, reliability, security, cost, and operations**. There is no rule that a cloud application must use microservices. A well-structured **modular monolith** still meets the needs of many products; separate services pay off when independent scaling or independent change needs are large enough to offset the cost of a distributed system.

This topic focuses on defining **functional boundaries, resource boundaries, and deployment boundaries**, and evaluating whether they should coincide or diverge at each stage of growth.

## 1. Three types of boundaries to distinguish

A **module** is a unit of source-code organization and dependency rules. A **service** is a unit providing capabilities via an interface/contract and may have its own runtime lifecycle. A **deployment unit** is a unit that can be released, scaled, and rolled back as one block, such as a containerized app, function, or service.

These three concepts relate to one another, yet **do not have to coincide**:

| Boundary | Core Question | Example |
| --- | --- | --- |
| **Functional / business** | Who owns this part's business rules and data? | Booking, payment, search |
| **Resource / scalability** | What distinct resource types and capacity does this part need? | Search needs high CPU/RAM; image processing needs workers; booking needs a transactional database |
| **Change / deployment** | How independently must this part release, test, roll back, and contain failures? | Promotion rules change daily; payment core changes cautiously |

One service may bundle multiple modules if they always change and deploy together. Conversely, a single business capability may have **multiple deployment units** for APIs, background workers, and scheduled jobs when load profiles differ. Never treat every database table, HTTP endpoint, or class as a microservice.

### Illustrating on a booking application

~~~mermaid
flowchart LR
    Client["Client application"]
    Client --> Gateway["API / BFF"]
    subgraph Core["Transactional business logic"]
        Booking["Booking"]
        Payment["Payment"]
    end
    subgraph Read["Query / discovery"]
        Catalog["Catalog"]
        Search["Search"]
    end
    subgraph Async["Background processing"]
        Notify["Notification"]
        Media["Image processing"]
    end
    Gateway --> Booking
    Gateway --> Catalog
    Gateway --> Search
    Booking --> Payment
    Booking --> Notify
    Catalog --> Media
~~~

This diagram depicts **logical capabilities**, not a mandate that they run as six services. First verify the load, change cadence, data consistency, and reliability targets of each capability.

## 2. Start from user journeys and business boundaries

Design starts by listing concrete journeys: searching listings, viewing details, holding a spot, paying, canceling, sending confirmations, and updating photos. For each journey, identify business rules, required data, consistency demands, and the component authorized to decide outcomes.

For example, the booking journey typically requires **checking availability and recording the reservation consistently**. Splitting availability checks and reservation writes into two independent services without an anti-contention protocol can cause double bookings. Meanwhile, confirmation emails do not need to sit inside the reservation creation transaction because they can be sent afterward.

### Using bounded contexts to shape responsibilities

A *bounded context* is a boundary within which terms, rules, and data models carry consistent meaning. For example:

- **Catalog** owns listing descriptions, amenities, and published photos.
- **Availability/Booking** owns hold rules, schedule conflicts, and reservation status.
- **Payment** owns charge/refund commands, payment states, and reconciliation.
- **Notification** owns message templates, delivery channels, send history, and retries.

A bounded context **can be a module inside a monolith before becoming a service**. The benefit of this step is clear ownership boundaries without yet paying for network calls, distributed data, and release coordination.

When evaluating a boundary, ask:

1. Are there **independent business rules** and a clear owner?
2. Does it need **strong transactions** with another component on most requests?
3. Can its contract be expressed with a stable API or events?
4. Does changing this part frequently force code edits in the other part?
5. When this component fails, can the rest degrade gracefully or isolate impact?

If two components must always update together to uphold a transactional invariant, splitting them too early easily produces a **distributed monolith**: multiple processes still tightly coupled across data, deployments, and reliability.

## 3. Analyzing load profiles to find independent scaling needs

Scalability is a major reason to separate deployment units when parts **consume different resources or hit non-overlapping traffic peaks**. Profile by capability, not merely total application RPS.

| Capability | Typical Load Pattern | Scaling Style to Consider | Potential Bottlenecks |
| --- | --- | --- | --- |
| Catalog / detail pages | High reads, cache-friendly, variable payloads | CDN/cache, add API replicas | Egress, cache misses, DB reads |
| Search and filtering | Read-heavy, complex queries | Scale search index/cluster independently | CPU, RAM, index freshness |
| Booking | Transactional writes, anti-double-booking checks | Controlled API scaling; transaction tuning | Locks, DB writer, contention |
| Payment | External system calls, variable response times | Isolate connection pools and concurrency | Latency, third-party rate limits |
| Image resizing | CPU/I/O-heavy, background, bursty inputs | Workers autoscaling on backlog | CPU, memory, object storage |
| Email / notifications | Background tasks piling up after campaigns | Queue- and quota-driven workers | Provider quotas, retry storms |

Key metrics include **requests/s**, **jobs/s**, **CPU-seconds/job**, **RAM/job**, **processing duration**, **p95/p99 latency**, **queue depth/lag**, **database QPS/IOPS**, **network egress**, and **growth rate**. Two parts with identical RPS can have completely different compute needs.

### Quantitative example: extracting an image-processing worker

Suppose an application has steady API traffic and generates **12,000 images/day**. Each image takes **2 CPU-seconds** on average to produce multiple sizes; an import campaign brings **6,000 images within 15 minutes**. These are illustrative numbers; measure real CPU, memory, and I/O.

- Total daily processing demand: \(12,000 \times 2 = 24,000\) CPU-seconds/day, or roughly **6.67 CPU-hours**.
- During the 15-minute burst: \(6,000 \times 2 = 12,000\) CPU-seconds.
- To finish all 6,000 images within 15 minutes, ideally you need \(12,000 / 900 \approx 13.34\) continuously busy CPU cores, **before overhead and target utilization headroom**.
- If each worker processes one image sequentially at 70% effective CPU efficiency, you might need about \(\lceil 13.34 / 0.70 \rceil = 20\) single-core workers to meet the deadline, assuming storage and queues keep up.

If image resizing runs inside the booking API, adding image capacity forces scaling the entire API codebase and risks CPU contention with critical transactions. Moving images to a **queue + independently scalable worker pool** is often a valuable split even while other business modules still share a monolith.

Even so, extracting a worker **does not automatically remove bottlenecks**. Object storage, network connections, read/write limits, and retry counts must still be checked. Autoscaling on queue depth must factor in worker startup time, job duration, and acceptable backlog.

### When does scaling together still make sense?

If two modules are always invoked together, use similar resources, and usually change in the same release, splitting processes can raise latency and complexity without adding useful scaling capacity. A monolith running multiple replicas behind a load balancer already **scales the whole application horizontally**; trouble mainly appears when one resource-hungry part makes whole-app scaling wasteful or harms SLOs.

## 4. Analyzing change cadence and independent release needs

**Change cadence** describes how often and in what way a component changes: business rules, APIs, data, assets, configs, or algorithms. Two parts with identical load but very different release cadences may need separate deployment boundaries.

Examples:

| Component | Assumed Change Cadence | Impact If Always Released Together |
| --- | --- | --- |
| Search ranking & recommendations | Daily experiments, algorithm tweaks | Every experiment triggers regression tests and rollout of the transactional core |
| Promotion policies | Several times per week | Risk of pricing edits affecting payments if unisolated |
| Booking & conflict checks | Several times per month, strict testing required | May be forced onto the release train of lower-risk features |
| Payment gateway integration | Changes per provider and compliance audits | Switching providers impacts broadly if code is scattered across the app |
| Image processing | Changes in dimensions, formats, pipelines | Must redeploy transactional APIs just to update workers |

These are illustrative assumptions, not universal rules. A feature's criticality does not automatically dictate release frequency: payment systems can still deploy frequently if tests, rollbacks, and risk controls are strong.

### Signals to spot change boundaries

Gather **actual change history** instead of relying on gut feel:

- **Change coupling:** how many other modules must change when module A changes? Commits repeatedly touching A and B together signal unstable boundaries.
- **Deployment coupling:** does changing A force releasing B at the same version? Can A roll back without rolling back B?
- **Release frequency:** how often per week/month does this part deploy, and does it need its own canary, feature flags, or approvals?
- **Change failure rate and MTTR:** how often does this part break deployments, how long does recovery take, and how wide is the blast radius?
- **Team ownership:** which team owns design, operations, and SLOs? Do multiple teams wait on one another for every release?
- **Schema/contract stability:** are interfaces and events stable enough for both sides to evolve at different speeds?

If recommendations change 15 times/month while booking changes 2 times/month, forcing every recommendation tweak to release the entire system expands testing scope and blast radius. However, **separating deployments alone does not guarantee independent deploys**: if renaming an API field forces both sides to upgrade simultaneously, services remain release-coupled.

### Independent deployment requires compatible contracts

For two components to change at different cadences:

1. Each side publishes clear **API contracts or event schemas**, backed by contract testing.
2. Make changes backward-compatible whenever possible; never delete fields or alter event semantics while old consumers remain active.
3. For breaking changes, run a transition phase: add the new field, upgrade consumers, observe usage, and only then remove the old field.
4. Deploy via canary/rolling updates with health checks, metrics, and rollback owned by that component.
5. Decouple **feature release** from **code deployment** using feature flags when needed; disable a feature without rolling back everything.
6. Define database migration policies: can old and new releases run concurrently during rolling updates?

For example, renaming `guestCount` to `numberOfGuests` in the Booking API should not immediately break Catalog and Notification. Accept both fields temporarily in requests, emit responses/events with the new field during transition, update consumers, and remove the old field once telemetry confirms zero remaining usage.

**Splitting services without contract versioning, telemetry, and independent rollouts** often multiplies repositories and deployments without improving delivery speed.

## 5. Choosing the right split level: module, process, service, or background flow?

Common options lie along a spectrum:

| Model | Advantages | Limits | Best Fit |
| --- | --- | --- | --- |
| **Modularized monolith** | Fast in-process calls, simple transactions, easy deployment and debugging | Usually scales/releases as one block; coupling can creep in without discipline | New products, small teams, evolving domains |
| **Monolith + separate workers/queues** | Isolates CPU/I/O-heavy or async work; scales by workload type | Must manage queues, retries, job states | Image processing, email, syncs, data imports |
| **Selected extracted services** | Independent scaling, releases, and fault isolation for targeted parts | Cross-network calls, contracts, data, and observability are harder | Search, recommendations, media with distinct needs |
| **Bounded-context microservices** | Multiple teams own and evolve services independently when boundaries are sound | Distributed data, ops overhead, dependencies, DR/QA complexity | Large domains, mature platform/ops teams, stable boundaries |

There is no default destination where "every module must become a microservice." A hybrid model can make complete sense: **Booking and Payment** stay tight modules in the transactional core early on, **Search** is a read service with its own index, and **Media** and **Notification** are asynchronous workers. Later, Payment can be extracted if distinct compliance, team ownership, or release schedules emerge clearly.

### Deployment unit vs. scaling unit

A deployment unit is what gets released and rolled back together; a scaling unit is the resource group whose capacity scales up/down together. In practice they can differ:

- A monolithic app with three modules in one process: all three scale together when adding replicas.
- One codebase with two entrypoints, **API** and **worker**: built from one repository yet deployed and scaled as two separate workloads.
- Two services sharing one Kubernetes cluster while setting separate autoscaling, quotas, and resource requests/limits.
- A serverless function scaling per request, still bounded by concurrency limits, cold starts, and database connections—not "infinite scaling."
- A group of services scales out, yet a shared database writer still caps end-to-end journey throughput.

Therefore, specify **which component actually scales independently**, which autoscaling signals drive it, and which dependencies remain bottlenecks.

### Do not use lines of code as the primary criterion

A 5,000-line module with complex payment logic may belong inside the same transaction more than a 50,000-line module processing independent documents. Splitting by line count or folder names without inspecting transactions, load, and change cadence creates extra network calls without increasing autonomy.

## 6. Data ownership determines real independence

A frequent mistake when moving from a monolith to multiple services is **splitting code while letting services directly mutate the same database schema**. One migration by service A can break service B; neither deploys independently, and both contend on connection pools, locks, and writer throughput.

In business-aligned partitioning, each component **owns its read/write logic and data invariants**. "Database per service" is one way to achieve that ownership, **not a mandate for one physical database server per service**. You can start with separate schemas, dedicated access credentials, data-owning APIs, and strict no-cross-write rules, then separate physical data infrastructure when load or lifecycle isolation is truly required.

### When must transactions stay within one boundary?

Booking is a classic example:

1. One slot may be booked by only one valid transaction at a time.
2. Checking availability and reserving must prevent race conditions.
3. Reservation state must remain consistent with the "no double-booking" invariant.

Checking availability via service A and writing reservations via service B without concurrency control lets two requests both see availability and both book. One design keeps **Booking owning the transaction/constraint** preventing overlaps and emitting events post-commit. Catalog/Search may consume a status projection for queries, while that projection **is never the final source of truth for writes**.

### Events and eventual consistency

When separating components with distinct lifecycles, synchronization lag is sometimes acceptable:

~~~mermaid
sequenceDiagram
    participant Client as Client
    participant Booking as Booking
    participant DB as Booking database
    participant Outbox as Event publisher
    participant Queue as Event broker
    participant Search as Search indexer
    Client->>Booking: Create booking (idempotency key)
    Booking->>DB: Commit reservation + outbox
    DB-->>Booking: Success
    Booking-->>Client: Booking confirmed
    Outbox->>Queue: ReservationCreated
    Queue-->>Search: Event (may duplicate / arrive late)
    Search->>Search: Update read model
~~~

In this design, Booking decides transaction correctness, while Search consumes data to optimize reads and may reflect updates a few seconds later. Specify **acceptable lag bounds**, protect consumers against duplicate, out-of-order, or missing events, and build replay/reconciliation mechanisms. The diagram shows logical flow; the outbox publisher needs a reliable mechanism to read committed records.

Not all business rules accept eventual consistency: certain financial or inventory constraints must be guarded at the data owner using transactions, constraints, locks, or appropriate protocols.

### Safe data migrations while two versions coexist

Schema migrations should follow **expand → migrate → contract**:

1. **Expand:** add backward-compatible structures without immediately dropping old ones.
2. **Migrate:** deploy app code supporting both old and new, backfill data in batches, track errors and lag, and upgrade consumers.
3. **Contract:** drop old columns, events, or API paths only after confirming zero remaining producers/consumers.

While two versions run concurrently, clarify which write path is authoritative to avoid non-transactional "dual writes" causing drift. Service separation is incomplete if schema migrations still require halting the whole system together.

## 7. Inter-component communication: fast, reliable, and loosely coupled

Turning an in-process function call into a network call changes how the system fails. A call from Booking to Payment can time out, drop connections, or return an ambiguous result; in-process calls do not suffer those network failure modes. Thus, **a service boundary is also an error-handling boundary**.

### Synchronous vs. asynchronous

| Method | Fits When | Trade-off |
| --- | --- | --- |
| In-process call | Immediate data needed, shared transaction and lifecycle | Shared deployment/scaling unit; harder to isolate faults within one process |
| Synchronous HTTP/gRPC | Client needs direct response; clear request/response contract | Network latency, timeouts, retries, fan-out, dependency blocks main path |
| Events via message broker | Broadcasting occurred facts to multiple consumers that can act later | Eventual consistency, duplicate handling, ordering, versioning |
| Commands via queue | Background tasks needing bounded processing and tracking | Backlogs, async states, dead-letter handling, monitoring |
| Batch / file transfer | High-volume integration without real-time needs | Latency, reconciliation, and run tracking |

You do not need events for every interaction. Direct calls remain sensible when immediate answers are needed and dependencies meet suitable SLOs. However, a chain like **Gateway → Service A → Service B → Service C → Service D** makes end-to-end latency and failure risk depend on every hop. Minimize calls on the *critical path* and avoid unnecessary fan-out.

### Availability of a dependency chain

Suppose three mandatory dependencies with independent failure probabilities have availabilities of 99.9%, 99.9%, and 99.5%. If every request requires all three to succeed:

\[
A_{\text{chain}} \approx 0.999 \times 0.999 \times 0.995
\approx 99.30\%.
\]

This merely illustrates the case **when failures are independent and all dependencies are mandatory**, not a universal formula for production systems: caching, retries, fallbacks, redundancy, and correlated failures alter real outcomes. Still, it shows why splitting services does not automatically raise availability.

### Protecting service boundaries

- **Timeouts/deadlines** per call and overall journey time budget.
- **Bounded retries with backoff and jitter**, only for safe or idempotent operations.
- **Circuit breakers and bulkheads** so one failing dependency cannot exhaust application resources.
- **Queues, backpressure, and rate limiting** for background jobs or streams unable to keep up with producers.
- **Trace-ID observability** across calls and events; track failed requests, queue lag, processing durations, and producer/consumer versions.
- **Ordering and duplication contracts:** never assume once-only message delivery; design idempotent consumers and per-entity ordering keys if business rules demand them.

For workflows spanning multiple data stores, use **sagas** (local transaction steps plus compensating actions) when business rules allow. Compensating actions are not strict transaction rollbacks; for instance, a "refund" takes time, incurs fees, and has intermediate states. Business invariants must be clarified before splitting transactions across services.

## 8. Scaling individual components: from measurements to deployment mechanisms

Saying "this service scales independently" only means something when you know **what to measure, what to scale, and where the limits lie**.

For request groups with relatively steady CPU cost, you can make a rough estimate:

\[
\text{Required CPU cores} \approx
\frac{\text{RPS} \times \text{CPU seconds/request}}
{\text{target CPU utilization}}.
\]

For example, a search endpoint receives **150 RPS**, each request takes **0.03 CPU-seconds** on average per profiling, and target average CPU utilization is under **60%**. Estimated demand is \(150 \times 0.03 / 0.6 = 7.5\) effective CPU cores, before adding overhead, peak headroom, fault-tolerance replicas, and memory constraints. If search has heavy p99 queries or a large index, average CPU alone is insufficient for sizing.

For queue workloads, measure **arrival rate**, **service rate**, and **backlog**:

\[
\text{Backlog growth per second} \approx
\max(0, \lambda_{\text{arrival}} - \mu_{\text{service}}).
\]

If a queue receives **100 jobs/s** while workers finish only **80 jobs/s**, backlog grows by roughly **20 jobs/s**, or **1,200 jobs/minute**. Scaling workers must factor in startup time, downstream quotas, and time to drain backlog after peaks. Scaling replicas by CPU alone may miss queue backlog or job latency; some workloads need autoscaling on **queue depth, queue age, or concurrency**.

Each workload type can pick an appropriate deployment model:

| Component Type | Potentially Suitable Deployment | What Must Be Tested |
| --- | --- | --- |
| Stateless API with steady load | Container service, VM autoscaling, or managed app platform | Load balancer, readiness, sessions, CPU/RAM, scale-out |
| Search with dedicated index | Managed search service or dedicated cluster | Index size, freshness, query p99, replicas, failover |
| Event-driven image processing | Queue + container/serverless workers | Cold starts, memory, job duration, duplicates, concurrency quotas |
| Scheduled heavy batch | Job/batch scheduler | Completion windows, checkpoints, retries, runtime cost |
| Transactions needing consistent DB | Stateless API + dedicated data layer | Locks, transaction contention, writer QPS, failover, RPO/RTO |

**Serverless, containers, and VMs can each fit part of the problem.** Choose based on job duration, cold starts, resources, traffic, quotas, pricing models, and operational skill. Avoid choosing "microservices + serverless" merely because a function is small: a function hitting a database with unbounded concurrency can still exhaust the connection pool.

### Independent scaling still hits shared constraints

Scaling a service from 4 to 40 replicas helps only if **database connection pools, writers, caches, brokers, and external APIs** can absorb the extra load. Measure end-to-end capacity and size limits around the scarcest resource. If every instance opens 30 DB connections, 40 instances can open **1,200 connections**, overwhelming a small database. Connection pooling, backpressure, and concurrency caps are integral to scaling design.

## 9. Trade-offs across reliability, security, cost, and operations

Sound component partitioning reduces *blast radius*, yet introduces new failure paths: networking, contracts, inter-service auth, DNS, message brokers, data replication, and deployment pipelines. Weigh benefits against real costs.

| Well-Architected Lens | Better When Split Sensibly | Worse When Over-Split |
| --- | --- | --- |
| **Reliability** | Isolates resources; shields booking from image/search spikes | Many mandatory dependencies, cascading timeouts, duplicate/delayed events |
| **Performance efficiency** | Tunes CPU/RAM/runtime and autoscales per workload | Network overhead, serialization, fan-out, cross-service cache misses |
| **Security** | Granular permissions, isolated sensitive data and processing zones | More identities, secrets, tokens, and inter-service attack surface |
| **Cost optimization** | Avoids scaling entire app for one workload; fits specialized machines | Minimum standby replicas, load balancers, egress, logs/traces, environments |
| **Operational excellence** | Independent deploys/rollbacks, clear ownership, smaller blast radius | More pipelines, release coordination, tracing, on-call, and runbooks |
| **Sustainability** | Places resources where needed; scales workers with load | Idle baseline headroom spread across too many services |

### Illustrating cost trade-offs

Suppose a three-component monolith needs **6 instances** to handle load. Splitting one part into an independent service might leave the monolith at 4 instances and the new service at 2—not immediately cheaper since total capacity stays 6, while adding a load balancer, logging, and networking. Real savings emerge if the new service **scales capacity up and down on its own schedule**, uses a better-matched machine type, or reduces baseline resource needs elsewhere.

Beyond compute bills, count **cross-AZ/region data transfer, separate databases, brokers, observability, deployment pipelines, incident response time, and operational effort**. Never compare architectures by counting running containers at a single point in time.

### Security isolation by business boundary

Service boundaries allow narrow permissions: Media workers only read input objects and write output objects; Notification reads only minimized alert fields; Payment protects payment data under stricter policies. However, splitting services creates new links requiring **service-to-service authentication, authorization, encryption in transit, secret management, and auditing**. Do not replicate personal data into every service merely so each service has its own database. If data residency or deletion requirements apply, track copies, events, and retention windows across the entire system.

## 10. Decision process for whether to split a component

A component is a strong extraction candidate when it has a **clearly owned business capability**, distinct **scaling** or **independent release** needs, and a **sufficiently stable communication contract**. Conversely, a component that routinely changes with the core, shares continuous transactions, and lacks operational owners gains little from splitting.

Use a qualitative evaluation matrix:

| Criterion | Signals Favoring Extraction | Signals Favoring Shared Deployment |
| --- | --- | --- |
| **Load & resources** | Different peak hours, specialized CPU/RAM/IO, clear separate scaling savings | Similar load/resources; whole-unit scaling meets SLOs |
| **Change cadence** | Frequent releases at a different pace; independent rollback is valuable | Always edited and released together |
| **Business boundaries** | Dedicated rules and ownership; clear contracts | Tight business invariants and transactions |
| **Data** | Clear owned data source; usable via API/events | Needs cross-boundary joins/writes on hot paths |
| **Reliability** | Failures can be isolated or degraded independently | Adds mandatory synchronous dependencies, raising outage risk |
| **Security & compliance** | Needs dedicated permissions, data zones, network zones, or controls | Adds excessive sensitive data transfer paths |
| **Team & operations** | Dedicated owner for SLOs, pipelines, monitoring, and on-call | Lacks operational capacity or accountable owning team |
| **Total cost** | Measurable compute savings or reduced outage damage | Infrastructure, tracing, deployment, and support outweigh benefits |

Do not turn this matrix into an arbitrary "scorecard." Record **evidence, confidence level, current choice, and review triggers**. For example:

> **Decision:** Extract the image-processing worker from the API this quarter because image CPU reaches 65% during import hours, images have a 5-minute completion SLA, and no synchronous transaction with booking is required. **Keep Booking in the modular monolith** because 90% of Availability and Reservation changes modify a shared data invariant. **Revisit extracting Search** if search p95, compute budget, or release velocity crosses agreed thresholds.

A verifiable decision should pair with success metrics: latency, error rate, throughput, cost/workload, deploy velocity, and cross-capability incidents.

## 11. Phased roadmap for splitting a live application

Starting from a monolith, prioritize **creating boundaries in code and measuring impact before moving communication onto the network**. A pragmatic roadmap:

### Step 1 — Observe the primary paths

Add tracing and metrics for search, booking, payment, and image processing journeys. Measure CPU/memory per task, RPS, query counts, time inside transactions, synchronous dependencies, code change frequency, and release-related errors. Establish a baseline before changing anything so you know whether extraction helps.

### Step 2 — Establish clear modules and ownership inside the current app

Group code by capability, define entrypoints/contracts between modules, restrict direct table access across modules, and test business invariants. Start with namespaces/packages, interfaces, dependency injection, and separate build modules. These boundaries reveal coupling before you pay the price of a distributed system.

### Step 3 — Extract low-dependency workloads

Prioritize background tasks like images and email: durable event/job recording, dedicated workers, idempotency, retries, and dead-letter handling. Tune worker capacity independently. Do not migrate all data and features into new services in one big bang.

### Step 4 — Separate data and contracts for the next candidate

For example, Search can ingest data via events/CDC or a controlled sync pipeline to build its own index. Define Catalog/Booking as authoritative sources, acceptable sync lag, backfill mechanisms, and reconciliation. Never let Search update reservations directly to fix availability.

### Step 5 — Shift traffic gradually using the strangler pattern

Place a stable routing layer, route selected endpoints/request slices to the new service, and use canaries, feature flags, or rollback-ready routing. Compare outputs, latency, error rates, inter-component call counts, and total cost. Shifting 100% of traffic before testing incidents/rollbacks introduces more risk than value.

~~~mermaid
flowchart TB
    Client["Client"] --> Route["API gateway / routing"]
    Route -->|Remaining flows| Mono["Modular monolith: Booking + Catalog"]
    Route -->|Search canary| Search["Search service"]
    Mono -->|Committed events| Broker["Message broker"]
    Broker --> Media["Media workers"]
    Broker --> Notification["Notification workers"]
    Broker --> Indexer["Search indexer"]
    Indexer --> Search
~~~

This is a reference layout; using an API gateway is not mandatory for every application. What matters is having **a forwarding and rollback path**, data contracts, and reliable operations.

### Step 6 — Retire legacy paths and verify independence

After shifting traffic, remove old code/write paths on schedule, guard against duplicate data sources, and clean up retired flags and schemas. Verify the new service deploys and rolls back independently, handles its own load, survives dependency errors, and has dashboards/on-call coverage. If deploys still require coordinating multiple services every time, boundaries still need refinement.

**Exit criteria for stopping extraction** should be explicit: if gains in SLOs, cost, change velocity, or fault isolation are insufficient, keeping the module inside the monolith may be the soundest choice.

## 12. Case study: choosing boundaries for a booking platform

Suppose a platform has the following **illustrative** characteristics:

| Component | Requirements & Signals | Initial Design Direction |
| --- | --- | --- |
| **Catalog** | Read-heavy content, updated a few times/day | Module owning source data; cache/CDN for public content |
| **Search** | High CPU/RAM queries; ranking changes often; needs dedicated index | Independent service if baseline proves separate scaling and releases add value |
| **Booking/Availability** | Anti-double-booking transactions; rules change together; low latency | Keep shared transaction boundary in modular monolith or unified Booking service |
| **Payment integration** | Needs idempotency, reconciliation, provider quotas | Adapter/module with clear contract; extract if security, ops, or independent change demands it |
| **Media** | Campaign upload spikes; CPU-heavy resizing | Queue + independently autoscaled workers, object storage |
| **Notification** | Event-driven sends, tolerates a few minutes of lag | Outbox/events + workers, retries, and backlog monitoring |

### If starting from an unmodularized monolith

An import batch of 10,000 images spikes CPU, degrading booking API p99. Meanwhile, search ranking tweaks require redeploying and regression-testing booking. These are two distinct signals: **load needing separation** and **release cadence needing separation**.

### A well-grounded evolutionary plan

Initially, reorganize modules into Catalog, Search, Booking, and Payment. Move Media and Notification to async workers because tasks, failure domains, and retry rules are straightforward. Re-measure latency, error rates, CPU, backlog, and cost; once Search proves distinct load and release cadence, extract the Search index and API.

Booking and Availability keep sharing a transactional write boundary to guard the no-double-booking invariant. Payment keeps an adapter with idempotency and explicit reconciliation states, ready for deployment extraction once interfaces and data stabilize. Search data may lag slightly, whereas "booking succeeded" always relies on Booking.

### Two post-extraction acceptance criteria

**Performance:** When image import load multiplies several-fold, Booking p95/p99 and error rates stay within SLO; Media backlog clears within acceptable time without over-scaling the API. Measure at the workload and journey level, not merely replica counts.

**Change cadence:** The Search team can deploy new ranking logic, canary, and roll back without deploying Booking. Contracts/schemas maintain compatibility and simultaneous cross-service edits decline. If p99 improves yet every release still requires three teams coordinating, change independence has not been achieved.

### What goes wrong when boundaries are misdesigned?

- Search queries Booking synchronously for **each result** on a listing page: fan-out drives latency and DB load sharply upward; use synced projections and verify finality only during booking.
- Notification calls back into multiple services mid-send to gather full customer details: risks cascading failures and broad data access; prefer minimal payloads or tailored query APIs.
- Booking and Availability split databases while still demanding synchronous updates for every action: invites race conditions and makes consistency hard to prove.
- Media lacks concurrency and retry limits: extracting workers still overloads object storage or downstream APIs.

These failures underscore that **good boundaries reduce coupling and isolate resources**, rather than merely renaming packages to services.

## 13. Common mistakes

1. **One table = one service:** technical data boundaries rarely equal business capabilities; breeds distributed joins and transactions.
2. **Splitting by lines of code:** codebase size says nothing about scaling needs or release independence.
3. **Calling it microservices while sharing schemas and cross-writing:** increases deployments while still forcing lockstep upgrades.
4. **Synchronous calls for everything:** fan-out chains inflate latency and mandatory failure points.
5. **Splitting strong transactions without consistency mechanisms:** risks double bookings, drifted payment states, or dropped events.
6. **Scaling APIs while ignoring downstream limits:** database writers, connection pools, provider rate limits, or brokers remain bottlenecks.
7. **Ignoring baseline service overhead:** standby replicas, load balancers, networking, observability, and on-call hours raise total cost.
8. **Independent releases in name only:** breaking schemas/APIs still force every service to deploy together; missing contract tests and deprecation processes.
9. **Missing per-service ownership/SLOs:** every incident wastes time hunting for the accountable team despite split services.
10. **Big-bang mass extraction:** changing code, data, and routing boundaries simultaneously makes rollbacks and root-cause analysis far harder.

## 14. Practice exercise and guided answers

A training platform includes login, course viewing, course search, course purchase, video streaming, and PDF certificate generation. Currently everything runs in one container app; observations show:

- Search consumes 55% CPU when students search materials, yet represents only 10% of total requests.
- PDF certificate export takes 2 minutes per job; an exam wave can generate 3,000 jobs in 10 minutes.
- Course purchase and payment rules often change in the same pull request due to reconciliation constraints.
- The content team wants to tune search ranking daily; the transactions team releases on a more cautious schedule.
- The purchase API must complete exactly once logically and preserve state even when the email service fails.

**Question 1 — Choosing what to split first:** Should all six features become six services immediately?

**Answer hint:** No justification yet. Establish module boundaries and measure a baseline; **PDF export** is a prime candidate for a dedicated worker/queue due to long jobs, bursty load, and async tolerance. **Search** is also a strong extraction candidate given distinct CPU usage and release cadence, though index sizing, latency, data contracts, and cost should be measured first. Login and course purchase do not automatically require separate services.

**Question 2 — Choosing scaling signals for PDF workers:** Why is scaling by API RPS alone insufficient?

**Answer hint:** The API can accept 3,000 job creation requests very quickly and return, while each PDF job takes 2 minutes. Signals should include **queue depth/age, job duration, concurrency, CPU/RAM**, completion deadlines, and storage quotas. Design retries and idempotency to avoid generating or emailing duplicate certificates.

**Question 3 — Should course purchase and payment be split?**

**Answer hint:** Distinguish *responsibility boundaries* from *deployment*. First establish a payment adapter/contract and idempotency/reconciliation mechanisms. If purchase and payment share a tight invariant, lack a stable contract, and always release together, keeping them in the same deployment lowers risk. Extract later when evidence proves independent benefits and distributed state handling is ready.

**Question 4 — How to prove Search truly deploys independently?**

**Answer hint:** Define compatible API/event schemas, contract tests, and independent canary/rollback; Search updates its index without direct write access to purchase tables. Track simultaneous edits across Search and core, p99 latency, post-deploy errors, and per-workload cost.

**Question 5 — Which Well-Architected goals must be reviewed?**

**Answer hint:** Reliability of purchase transactions, containing incidents caused by PDF/Search; worker data access permissions; workload-specific scaling; observability, runbooks, and ownership; compute/queue/storage/egress costs; and ability to recover to a stable state after a bad rollout.

When evaluating any component partitioning plan, present **business boundaries, load profiles, change history, data dependencies, communication contracts, deploy/rollback strategies, and effectiveness metrics**. Those pieces of evidence govern when to keep a modular monolith, when to extract workers, and when an independent service is genuinely warranted.
