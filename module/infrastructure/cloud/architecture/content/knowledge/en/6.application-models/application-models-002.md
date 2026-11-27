# Layered Architecture, N-Tier, and the Limits of Tier Separation

## Learning Objectives

In **Cloud Architecture** design, two decisions are very easy to confuse: **splitting source code responsibilities into layers** and **splitting a running system into deployment tiers**. A *layered architecture* helps manage change, dependencies, and testing. An *N-tier architecture* defines deployment boundaries, network connectivity, and operational capabilities. A system can use multiple logical layers within one application process; conversely, a single layer can be deployed across multiple processes or infrastructure zones.

After this lesson, you will be able to:

- Distinguish *layer* (logical layer) and *tier* (deployment tier), and differentiate both from module and microservice.
- Design presentation, application, domain, and data/infrastructure layers with sound dependency directions.
- Map a Java/Spring Boot application structure onto network, compute, database, and cloud deployment models.
- Analyze the benefits, limits, and costs of tier separation: security, scaling, fault isolation, network latency, data, and operations.
- Decide the appropriate number of tiers based on business requirements, measurable criteria, and **Well-Architected** principles.

## 1. Real-world problem: from a booking screen to cloud architecture

A booking platform provides a web app, mobile app, and partner API. The system needs to search rooms, calculate prices, create bookings, collect payments, cancel bookings, and send notifications. The team receives these requirements:

- Pricing rules and cancellation policies must be identical across web, mobile, and partner channels.
- When room search traffic spikes, the API must still meet its latency target.
- Do not sell the same spot twice under concurrent requests or retries.
- Users may only view and edit their own bookings.
- When an instance or an Availability Zone fails, the booking flow must continue serving within agreed recovery targets.
- Cloud costs and operational workload must stay within budget.

Two types of architectural questions emerge:

1. **How is the source code organized?** Where do HTTP handling, use-case orchestration, business rules, persistence, and external system calls live?
2. **Where do components run?** Do web, API, worker, database, and cache live in the same process, different processes, or separate subnets/clusters? Are multiple AZs/regions needed?

The first question leads to **layered architecture**; the second leads to **N-tier and deployment models**. You cannot infer the number of servers from the number of Java directories.

## 2. How does a layer differ from a tier?

### 2.1. Layer: logical boundary

A logical layer groups related responsibilities while establishing dependency rules and contracts between them. For example:

| Layer | Responsibility | Example | What to Avoid |
| --- | --- | --- | --- |
| **Presentation / API** | Receive requests, validate input format, map DTOs, return responses and error codes | REST controller, input/output DTO | Embedding SQL and pricing policies inside controllers |
| **Application / Use case** | Orchestrate a use case, define transaction boundaries, and verify business authorization | CreateBookingService, CancelBookingUseCase | Coupling core logic to HTTP servlets |
| **Domain / Business** | Invariants, states, calculations, policies, and business rules | Booking, CancellationPolicy, PriceCalculator | Depending on cloud configuration or database drivers |
| **Infrastructure / Data access** | Implement persistence, call external services, email, queues, object storage | JPA adapter, payment API client | Making arbitrary business decisions in the integration layer |

An application can use just three layers: presentation–business–data access. If the domain is complex, separating application and domain can make testing and dependency control easier. There is no fixed number of layers required for every system.

### 2.2. Tier: runtime or deployment boundary

A tier is a group of components deployed or executed within a distinct boundary, typically interacting with other tiers over a network. A traditional **3-tier** model has a presentation tier, an application tier, and a data tier.

| Term | What It Partitions | Example |
| --- | --- | --- |
| **Layer** | Responsibilities and dependencies in software | Controller → Service → Repository |
| **Tier** | Deployment, process, and network boundaries | Web client → App server → Database server |
| **Module** | Packaging and business capability boundaries in code | Booking, Payment, Inventory |
| **Service** | A component providing a functional contract, either in-process or over a network | Booking service |
| **Microservice** | A relatively independently deployable service, typically tied to a business capability and data ownership | Separately deployed Payment service |

The terms *layer* and *tier* are sometimes used interchangeably in documentation. To avoid ambiguity during reviews, explicitly clarify whether you are discussing **code dependencies** or **network request paths**.

### 2.3. One system, two valid diagrams

Logical layer view:

~~~mermaid
flowchart TB
  API["Presentation: controller / DTO"]
  APP["Application: use case / transaction"]
  DOM["Domain: business logic"]
  PORT["Repository interface"]
  ADAPTER["Persistence adapter: SQL / JPA"]
  API --> APP
  APP --> DOM
  APP --> PORT
  ADAPTER -. implements .-> PORT
~~~

N-tier deployment view:

~~~mermaid
flowchart LR
  USER["Browser / Mobile"]
  EDGE["WAF / Load balancer"]
  A["App instance AZ A\nLogical layers"]
  B["App instance AZ B\nLogical layers"]
  DB[("Managed database")]
  USER --> EDGE
  EDGE --> A
  EDGE --> B
  A --> DB
  B --> DB
~~~

Even with multiple code layers, those layers **reside together inside the app instance**. The infrastructure has a replicated application tier and a data tier. Multi-AZ improves fault tolerance for certain components, but does not automatically resolve application bugs or accidental data deletion.

## 3. Principles for designing layered architecture

### 3.1. Clear responsibilities and contracts

Each layer should provide an easily describable contract. A create-booking flow might traverse:

~~~text
HTTP POST /bookings
    → Controller: decode request, validate format
    → Application service: verify caller, orchestrate use case, transaction
    → Domain: verify business conditions
    → Repository port: request data write/query
    → Persistence adapter: SQL/JPA statements, data constraints
    → Application service: result/exception
    → Controller: map to HTTP response
~~~

For sensitive data, the **authentication context** must be obtained from server-trusted middleware/security context, never from a client-supplied user ID.

### 3.2. Strict layering vs. relaxed layering

- **Strict layering:** A layer only calls its adjacent layer according to established rules. Easy to control, though it sometimes adds pass-through layers with little value.
- **Relaxed layering:** Simple read paths may be allowed to call a deeper component, within clear limits. Without governance, layers are easily bypassed or hollowed out.
- **Dependency inversion:** Domain/application defines the interfaces it needs; adapters in the outer layer implement those interfaces. Runtime control flows outward to infrastructure, while source code dependencies point inward toward business logic.

Do not equate layering with creating excessive interfaces. A meaningful contract is one that isolates change, enables testing, or protects business logic; an interface with a single implementation is not inherently wrong, nor does it automatically prove its value.

### 3.3. Measuring cohesion and coupling

**Cohesion** is about keeping code that serves a single purpose close together. **Coupling** is about how much a change in one part forces changes in others.

If changing room pricing requires editing a controller, a queue consumer, a repository, and three services just to synchronize the same formula, the rule is likely scattered in the wrong places. If a service merely delegates a single line to a repository without adding behavior or control, consider whether that abstraction is necessary.

A feature-based package structure can also combine layering:

~~~text
com.example.booking
├── booking
│   ├── api
│   ├── application
│   ├── domain
│   └── infrastructure
├── catalog
│   ├── api
│   ├── application
│   └── infrastructure
└── payment
    ├── application
    └── infrastructure
~~~

This approach makes boundaries between booking, catalog, and payment clearer than placing all controllers across all features in one package and all services in another.

## 4. Layering example with Java and Spring Boot

Suppose the **view booking details** use case may only be executed by a user authorized for that booking. The examples below illustrate structure and responsibility boundaries; imports, security configuration, and HTTP exception mapping are omitted.

### 4.1. Domain and repository contract

~~~java
public record Booking(
    UUID id,
    UUID customerId,
    BookingStatus status
) {}

public enum BookingStatus {
    PENDING, CONFIRMED, CANCELLED
}

public interface BookingRepository {
    Optional<Booking> findById(UUID bookingId);
}
~~~

In a dependency-inversion design, the repository interface can live in the domain or application layer, defining **what the application needs**. The concrete persistence layer is responsible for implementing it.

### 4.2. Application service

~~~java
public final class BookingQueryService {
    private final BookingRepository repository;

    public BookingQueryService(BookingRepository repository) {
        this.repository = repository;
    }

    public Booking findForCustomer(UUID bookingId, UUID callerId) {
        Booking booking = repository.findById(bookingId)
            .orElseThrow(BookingNotFoundException::new);

        if (!booking.customerId().equals(callerId)) {
            throw new BookingAccessDeniedException();
        }

        return booking;
    }
}
~~~

Here, view permission is checked in the use case, so if mobile, batch, or GraphQL APIs are added later, the rule is still reused. In a real product, authorization rules can be more complex and extracted into a dedicated policy.

### 4.3. Controller and DTO

~~~java
public record BookingResponse(
    UUID id,
    UUID customerId,
    String status
) {}

@RestController
@RequestMapping("/bookings")
public class BookingController {
    private final BookingQueryService service;

    public BookingController(BookingQueryService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public BookingResponse get(
        @PathVariable UUID id,
        @AuthenticationPrincipal AppPrincipal principal
    ) {
        Booking booking = service.findForCustomer(
            id, principal.userId()
        );
        return new BookingResponse(
            booking.id(),
            booking.customerId(),
            booking.status().name()
        );
    }
}
~~~

The controller handles the HTTP protocol, while the access control decision sits in the application layer. *AppPrincipal* must be produced by a verified authentication flow. The API needs consistent exception handling and HTTP status mapping; this snippet is not a standalone runnable application.

### 4.4. Persistence adapter

~~~java
@Component
public class BookingRepositoryAdapter implements BookingRepository {
    private final BookingJpaRepository jpa;

    public BookingRepositoryAdapter(BookingJpaRepository jpa) {
        this.jpa = jpa;
    }

    @Override
    public Optional<Booking> findById(UUID id) {
        return jpa.findById(id).map(entity ->
            new Booking(
                entity.getId(),
                entity.getCustomerId(),
                BookingStatus.valueOf(entity.getStatus())
            )
        );
    }
}
~~~

The adapter converts between the persistence model and the business model, reducing leakage of JPA entities into HTTP and domain layers. Weigh the practical mapping cost; you do not necessarily need a conversion layer for every simple piece of data.

**Transaction boundary:** For a create-booking use case, the transaction is typically coordinated in the application service. The invariant "a room cannot be sold twice" must also be protected by database concurrency mechanisms, such as unique constraints, optimistic/pessimistic locking, or conditional updates. Checking in Java before writing is **not enough** when two requests run concurrently.

## 5. Deployment models from simple to multi-tier

### 5.1. Single application process and one database

~~~mermaid
flowchart LR
  C["Client"] --> APP["Spring Boot process\nController + Use case + Domain + Adapter"]
  APP --> DB[("Managed DB")]
~~~

The application has multiple layers but a single deployable unit. You can run multiple app replicas behind a load balancer for scalability and reliability without turning layers into separate network services.

This model is usually easy to develop, test, deploy, and roll back; it fits when the team is small, business logic is cohesive, and SLOs can be met by scaling multiple instances.

### 5.2. Three-tier (3-tier)

~~~mermaid
flowchart LR
  WEB["Presentation tier\nWeb frontend"]
  APP["Application tier\nBusiness logic"]
  DATA[("Data tier\nDatabase")]
  WEB --> APP --> DATA
~~~

In the traditional model, presentation, application, and data run across three deployment boundaries. With modern SPA/mobile apps, presentation may live in the browser, CDN, or a frontend server. An API gateway can add a deployment and policy boundary without necessarily adding another business layer.

The advantage is scaling and protecting web, app, and DB according to their individual profiles. The consequence is added network hops, connections, timeouts, cross-tier logging, and operational responsibility for new components.

### 5.3. N-tier with asynchronous processing

~~~mermaid
flowchart TB
  U["Web / Mobile"] --> EDGE["CDN / WAF / API gateway"]
  EDGE --> API["Booking application"]
  API --> DB[("Transactional DB")]
  API --> QUEUE[("Message queue")]
  QUEUE --> WORKER["Notification worker"]
  API --> CACHE[("Cache, if needed")]
~~~

The worker and queue create a separate processing path so notification work does not sit on the booking response path if business requirements allow. However, a queue does not guarantee exactly-once processing; consumers must handle retries/duplicates and may need a dead-letter queue.

Depending on classification, this diagram has more deployment components than a three-tier model, though not every component is necessarily a tier in a linear sense. N-tier is a model for understanding runtime boundaries and dependencies, not a box-counting contest.

## 6. Practical benefits of tier separation

### 6.1. Scaling by workload type

The web tier may need many connections, the business processing tier needs CPU, and workers scale by queue depth. Separation enables provisioning resources according to actual load—such as scaling workers when backlog grows without scaling all API instances.

Identify the **real bottleneck** before splitting. If database wait time from locks or missing indexes is what drives latency up, doubling the API tier can make things worse by opening more connections.

### 6.2. Restricting access paths and permissions

You can place the database in a private subnet, allowing connections only from the application tier and blocking direct Internet access. The edge applies TLS, WAF, and rate limiting; the application checks permissions on each resource.

Separating network tiers allows distinct policies, but **does not automatically guarantee security**. You must control service-to-service identity, encryption in transit/at rest, least privilege, auditing, and sensitive data boundaries.

### 6.3. Fault isolation

If the email gateway is slow, the booking flow can still write successfully and emit a notification event via a queue. If the worker fails, notification delivery is delayed without necessarily blocking bookings.

Conversely, if booking rules are split into three mandatory synchronous services, a failure in one service can fail the entire request. Having more separate processes **does not automatically mean** better end-to-end reliability.

### 6.4. Release lifecycle and ownership

Separating frontend, API, and worker enables independent deployments when contracts are stable. One team can update the frontend without releasing the backend.

However, deployment independence is limited if every change requires modifying a shared schema or releasing multiple services simultaneously. Data boundaries, API versioning, and backward compatibility matter more than pipeline count.

## 7. Limits and trade-offs of tier separation

### 7.1. Network latency and chained load risks

An in-JVM call differs drastically from an HTTP/gRPC call over the network. Each hop can add:

- Network transmission and load balancer latency.
- Serialization/deserialization, TLS, and connection setup.
- Connection pools, DNS, quotas, and congestion risk.
- Timeouts, retries, partial failures, or ambiguous outcomes.
- Network, egress, and observability costs.

As an **illustrative** example, suppose the application spends an average of 40 ms on business logic. If there are three **sequential** calls to another tier, each adding 12 ms on average, a simple average latency estimate is:

~~~text
40 ms + 3 × 12 ms = 76 ms
~~~

This is **not** a p95 or p99 forecast. Percentiles cannot simply be summed from averages; tail latency, retries, and queueing can make real-world latency much higher.

**Chatty architecture** is a common anti-pattern: service A calls B for each data row, and B calls C for each attribute. For 100 records, a network N+1 flow can generate hundreds of round trips. Consider batch APIs, read models, aggregated queries, or caching depending on data characteristics.

### 7.2. Multiple mandatory dependencies alter availability

Suppose a user journey must successfully call three independent services, each with a 99.9% success probability over a given measurement window. **Assuming independent failures** and that all three are mandatory, the simplified success probability is:

~~~text
0.999 × 0.999 × 0.999
= 0.997002999
≈ 99.7003%
~~~

This result only illustrates the effect of adding dependencies. In reality, failures can be correlated, fallbacks/retries may exist, and SLOs may be measured differently. Still, you should never mechanically extrapolate individual service uptimes to claim availability for the **entire booking transaction**.

### 7.3. Distributed transactions

An ACID database transaction **does not automatically span** two databases or a networked payment service. When booking, payment, and inventory are split into independent services, the team must resolve intermediate states and failure handling.

| Mechanism | Value | Trade-off |
| --- | --- | --- |
| Single-DB transaction | Preserves strong consistency within one boundary | Does not cover external services |
| Outbox + message broker | Bridges DB state with more reliable event publishing | Requires relay, idempotency, retries, backlog monitoring |
| Saga/compensation | Coordinates business steps with compensating actions | Must model intermediate states and eventual consistency |
| Distributed transaction / 2PC | Can coordinate consistency when fully supported | Complex, can hurt availability, inconsistent across cloud services |

For example, if payment succeeds but the client times out, retrying the booking could charge twice without an idempotency key and reconciliation mechanism. Splitting payment into a separate tier does not solve this by itself.

### 7.4. Higher operational and infrastructure costs

Each independent tier may require compute, load balancers, addressing/networking, IAM, service accounts, certificates, secrets, logging, tracing, CI/CD, health checks, alerts, runbooks, and on-call effort. On the cloud, there are also cross-AZ/region traffic, NAT, egress, or private endpoint fees depending on the architecture.

Total cost should be evaluated as **TCO**, covering infrastructure, managed services, data transfer, staffing, failure testing, and cost of changing the system. Two options are only fairly compared when serving the same requirements and quality targets.

### 7.5. Distributed monolith

Splitting technical layers into separate services while sharing a database/schema, requiring synchronized releases, and calling each other continuously often creates a **distributed monolith**: paying distributed networking and deployment overhead while remaining tightly coupled on change.

Symptoms include:

- Changing one rule requires releasing a batch of services.
- Services read and write into each other's tables.
- A large number of sequential synchronous calls.
- Inability to run/test a single module in isolation because everything must be online.
- A single team maintaining too many small services.

The remedy should start with **re-establishing business boundaries and data ownership**, rather than multiplying services to fix coupling.

## 8. Layered monolith, modular monolith, N-tier, and microservices

The following models can be combined rather than being mutually exclusive.

| Model | Core Idea | Benefits | Limits |
| --- | --- | --- | --- |
| **Layered monolith** | Multiple logical layers in one deployable app | Short call paths, simple transactions, easy deployment | Scaling and releases usually move together |
| **Modular monolith** | One deployable app, business modules with clear boundaries | Easy testing, ownership in code, prepared for later extraction | Cannot scale/release modules independently if single process |
| **N-tier** | Deployment tiers with network or process boundaries | Separates security/scaling/availability per tier | Extra network hops, ops, and cost |
| **Microservices** | Relatively independently deployable business services | Independent scaling, ownership, and releases when boundaries are sound | Distributed transactions, contracts, observability are harder |

A microservices application can still use layers **inside each service**. Conversely, a layered monolith can be deployed across multiple AZs with high availability. These concepts answer different questions.

**Practical choice:** When a product is new, the team is small, and business rules change rapidly, a modular monolith with clear boundaries is usually easiest to start with. A module should become a separate service only when there is a clear independent need for load, releases, ownership, security, or data lifecycle sufficient to offset distributed operational overhead.

## 9. Designing N-tier on the cloud across network, compute, data, and deployment

### 9.1. Network and security

~~~mermaid
flowchart TB
  CLIENT["Internet client"] --> WAF["WAF / Public load balancer"]
  subgraph CLOUD["Virtual private network - multi AZ"]
    subgraph APP["Private application subnets"]
      A["App A"]
      B["App B"]
    end
    subgraph DATA["Private data subnets"]
      DB[("Database")]
    end
    A --> DB
    B --> DB
  end
  WAF --> A
  WAF --> B
~~~

Design principles:

1. Expose only endpoints that must be reached from the Internet; databases generally do not need public IPs.
2. Define network rules for actually required traffic; do not open all ports just because a subnet is private.
3. Authenticate service-to-service traffic and encrypt data in transit across critical boundaries.
4. Account for cross-AZ/region traffic fees and latency when designing chatty paths.
5. Define behavior when DNS, connections, or load balancers fail; test timeouts and retries.

### 9.2. Compute and autoscaling

Stateless apps can run on VMs, containers, managed application runtimes, or serverless depending on requirements. Consider health checks, graceful shutdown, session handling, autoscaling metrics, quotas, concurrent request limits, and cold starts where applicable.

If an API and a batch scheduler share the same process, scaling out the API duplicates the scheduler and generates duplicate events. This is an example where **separating the worker** has clear value even while sharing a codebase.

### 9.3. Data and consistency

The data tier needs to:

- Define who owns each table/data set and which invariants the database must enforce.
- Design indexes, connection pools, cache invalidation, and control N+1 queries.
- Rehearse backup/restore and set RPO/RTO per failure scenario.
- Enforce encryption, access permissions, and auditing for sensitive data.
- Forecast traffic, IOPS, storage growth, and replication costs.

Do not assume that "having a data tier" means "every logical layer needs its own database." Separate databases should follow true data boundaries, ownership, and independence requirements.

### 9.4. Deployment and reliability

Multi-AZ can protect against part of AZ-level risk; multi-region can serve DR when a region goes down. However, **backup is not failover**: multi-AZ does not replace backups against accidental deletion or buggy writes.

Every scenario must specify: when an instance, AZ, region, application, or database fails, which parts keep running; plus RTO, RPO, and how they are measured in practice. Separating into multiple tiers introduces additional dependencies that must be verified in drills.

## 10. Choosing boundaries using measurable quality scenarios

Suppose the business sets the following **illustrative** targets; exact numbers must be confirmed with the product owner and real load data.

| ID | Stimulus and Environment | Expected Response | Measure |
| --- | --- | --- | --- |
| QA-PERF-01 | Peak hour, room search reaches 800 req/s for 30 minutes | API maintains quality without saturating the DB | p95 ≤ 400 ms; HTTP 5xx < 0.5% at gateway |
| QA-REL-01 | One application AZ becomes unavailable | Load balancer shifts traffic to remaining instances | ≥ 99.9% valid booking requests succeed during 15-min test window |
| QA-SEC-01 | Account A attempts to access Account B's booking | Rejected server-side and audit logged | 100% of authorization test suite cases rejected, zero data leaked |
| QA-OPS-01 | Email provider is slow for 10 minutes | Booking is unblocked; notifications queue and process later | Booking meets SLO; queue age returns below threshold |
| QA-REC-01 | Database loses data or becomes unavailable | Restore and reconcile bookings | Agreed RTO/RPO, measured via end-to-end drill |
| QA-COST-01 | Traffic triples | Scale the right components | Cost per completed booking stays under budget |

These criteria point to different solutions: for QA-OPS-01, separating a worker/queue helps; for QA-REL-01, multiple instances across AZs may suffice; for QA-REC-01, backup and data recovery strategy is needed—it cannot be solved by adding more services.

An **SLI** is an observed indicator; an **SLO** is the target for that indicator. **RTO** is the recovery time limit; **RPO** is the maximum acceptable data loss measured in time. Both must be verified through drills rather than assumed from enabled infrastructure features.

### 10.1. Decision matrix

| Situation | Option to Try First | Required Evidence |
| --- | --- | --- |
| Single/shared dev team, moderate load, cohesive logic | Layered modular monolith | Unit/integration tests, SLOs, release velocity |
| Notifications slow down bookings | Dedicated queue and worker | Booking p95, queue lag, retries, idempotency |
| A business area has genuinely independent load and releases | Domain-aligned separate service | API contract, data ownership, cost, load tests |
| DB is the primary bottleneck | Optimize queries/indexes/connections, cache, or read model | Query plan, p95, DB saturation |
| Sensitive data requires network isolation | Private network tier and policies | Security tests, audits, threat model review |
| Extracted microservices still release together | Strengthen contracts or revisit boundaries | Cross-service change count, test and release time |

### 10.2. Illustrative TCO

Suppose Option A is a modular monolith with 2 app instances and a DB, while Option B adds a service for a small use case, an internal load balancer, and a separate worker. Units are in **million VND/month**, purely to illustrate the lesson—not an actual price quote.

| Line Item | A: Layered App + DB | B: Multi-tier / Service |
| --- | ---: | ---: |
| Application compute | 35 | 40 |
| Database and backups | 25 | 25 |
| Load balancer / network / egress | 8 | 15 |
| Queue and worker | 0 | 12 |
| Logging, tracing, monitoring | 7 | 12 |
| Allocated operational effort | 20 | 35 |
| **Total** | **95** | **139** |

~~~text
Difference = 139 - 95 = 44 million VND/month
Relative increase = 44 / 95 × 100% ≈ 46.3%
~~~

This increase **reflects assumptions only**. If B eliminates a bottleneck and reduces system-wide scaling costs at high load, total cost may change. Comparisons must hold **the same SLOs and transaction volume**, cost per completed booking, incident risk, and staffing costs—not just hourly VM prices.

## 11. Case study: evidence-driven improvements to the booking platform

### 11.1. Initially: layered within one application

Booking, catalog, payment integration, and notification were written as modules inside one Spring Boot application. The application was deployed across two AZs behind a load balancer, using managed PostgreSQL with backups.

The team moved fast because the booking path mostly ran within one transaction, modules were easy to test, and only a single artifact had to be released.

### 11.2. Issues emerging under higher load

Load testing recorded three hypothetical phenomena:

1. Room search API p95 spiked due to filter queries missing an index.
2. Create-booking API waited for synchronous email sending, so when the email provider slowed down, bookings timed out.
3. The notification scheduler ran in every API replica, so scaling API instances caused duplicate notification processing.

Choosing to "split all Java layers into microservices" would add many network hops without necessarily solving query bottlenecks or data correctness.

### 11.3. Intentional improvement plan

- Optimize queries and indexes, and bound connection pools.
- Keep booking transactions and rules inside the existing business module.
- Persist booking state and notification events reliably, such as using a transactional outbox where appropriate.
- Move notifications to a dedicated queue and worker with idempotent processing, bounded retries, and a dead-letter queue.
- Consider extracting catalog/search into a separate service only when independent scaling, data, ownership, and release needs are proven.

~~~mermaid
flowchart TB
  U["Web / Mobile"] --> LB["WAF / LB"]
  LB --> A["Spring Boot A: Booking + Catalog"]
  LB --> B["Spring Boot B: Booking + Catalog"]
  A --> DB[("Transactional DB")]
  B --> DB
  DB -. Outbox relay .-> Q[("Queue")]
  Q --> W["Notification worker"]
~~~

### 11.4. Post-change verification

Re-run with the original data set and load ramp, collecting:

- Booking success rate, p95/p99, HTTP 5xx, and timeout cases.
- Queue lag, failed event count, notification delivery latency, and duplicate-handled events.
- DB latency, connection pool usage, lock waits, and throughput.
- Instance/AZ fault injection and recovery results.
- Total cloud cost, operational cost, and cost per successful booking.

If measured targets are not met, the team adjusts the architecture based on root causes. Simply "having extracted a worker" is not enough proof of success.

## 12. Cross-tier testing, observability, and operations

| Item | Verification Question | Evidence |
| --- | --- | --- |
| Unit test | Does pricing/cancellation/authorization logic run without web/DB? | Application/domain tests |
| Integration test | Are DB constraints, transactions, and concurrent bookings correct? | Tests against an equivalent database |
| Contract test | Do frontend and backend stay compatible across releases? | API schemas and contract tests |
| Load test | Do p95/p99 and throughput hold at target load? | Dashboards on identical test data |
| Fault injection | When an instance/AZ/queue/dependent API fails, which flows keep running? | Error duration, success rate, traces |
| Restore drill | Are data and services restored within deadlines? | Measured RTO/RPO and reconciliation |
| Security test | Are unauthorized access and sensitive logging blocked? | Security test suite and audit events |

**Observability:** Combine metrics (request rate/error rate/latency/saturation), structured logs, and distributed tracing when multiple services exist. A correlation ID connects the request path; do not log sensitive data for tracing purposes.

**Timeouts and retries:** Each tier must have timeouts fitting within the overall request budget. Retries need limits, backoff with jitter, and idempotency checks for operations with side effects. A client timeout **does not mean** the server failed to create the booking; handle cases where a response is lost after the transaction already committed.

**Deployment:** When running multiple application versions during rolling/canary deployments, schema migrations must stay backward-compatible long enough for old and new versions to operate concurrently.

## 13. Evaluating with Well-Architected

| Pillar | Questions When Layering and Separating Tiers |
| --- | --- |
| **Operational Excellence** | Does the component count match deploy capacity, on-call staffing, IaC, runbooks, and drills? |
| **Security** | Are domains/data protected by least privilege, authentication/authorization, network segmentation, and encryption? |
| **Reliability** | How does each synchronous dependency affect success rate? Are failover, backups, and RTO/RPO drills in place? |
| **Performance Efficiency** | Does each network hop deliver clear value? Have p95/p99, throughput, and real bottlenecks been measured? |
| **Cost Optimization** | Does tier separation reduce scaling costs enough to justify added compute, network, logging, and staffing? |
| **Sustainability** | Does it reduce overprovisioning and avoid unnecessary data transfer/replication? |

A Well-Architected review is a process of examining trade-offs for a real workload, not a fixed diagram template to copy.

## 14. Sample ADR for deciding to extract a worker

~~~yaml
id: ADR-APP-002
title: Extract notification worker from Booking API
status: proposed
context:
  - Booking API waits for synchronous email sending
  - p95 rises when the email provider is slow
options:
  - synchronous_email
  - queue_and_worker
decision: queue_and_worker
quality_scenarios:
  - QA-PERF-01
  - QA-OPS-01
benefits:
  - Does not block booking requests due to email
  - Scale worker based on queue lag
risks:
  - Retries and duplicate handling
  - Need to monitor backlog and DLQ
verification:
  - TEST-BOOKING-LOAD
  - TEST-WORKER-RETRY
review_when:
  - SLO_not_met
  - Operational_cost_exceeds_budget
owner: Architecture Team
~~~

In a real project, an ADR should include date, accountable owner, test evidence, and a rollback plan. The thresholds and test names in the template merely illustrate decision traceability.

## 15. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Three packages means three servers | Unnecessary infrastructure growth | Draw logical and deployment diagrams separately |
| Creating one microservice per technical layer | Chatty calls, coupling, and a distributed monolith | Split by business capability and data |
| Assuming more tiers are always safer | More configuration, IAM, secret, and network surface | Build a threat model and policies per boundary |
| Adding API replicas during DB saturation | Increases connections and lock contention | Profile DB, indexes/queries first |
| Service-level transaction prevents double booking | Race conditions across concurrent requests | Database constraints/locking and concurrency tests |
| Having a queue means exactly-once event processing | Retries can cause duplicate processing | Idempotency and reconciliation checks |
| Summing average hop latencies for p95 | Ignores tail latency and retries | End-to-end load testing |
| Multi-AZ removes the need for backups | Accidental deletes/logic bugs still corrupt data | Backups/restore and DR drills |
| Separate containers equals independent deployment | Shared schemas still force lockstep releases | Contracts, compatible migrations, data ownership |
| Layered architecture is outdated | Loses a useful tool for organizing responsibilities | Use layering inside a monolith or service where appropriate |

## 16. Practice exercise

A company runs a Java/Spring Boot order management system. Normal traffic is 100 req/s, peaking at 800 req/s. A team of 7 operates order creation, payment, shipment tracking, and email sending.

1. Draw a **four-logical-layer** architecture for the create-order use case, explaining where authorization and transactions live.
2. Draw two deployment options: **A** is a layered modular monolith with a database and worker; **B** splits order, payment, and notification into services. Distinguish logical layers from physical tiers.
3. With three sequential synchronous calls, each adding 15 ms on average, compute the added average latency; explain why p95 cannot be concluded yet.
4. Handle the case where a user clicks pay twice or retries after a timeout; identify the required database constraints, idempotency, and reconciliation.
5. Outline how to test losing one AZ and having the email service fail for 10 minutes, specifying SLIs, SLOs, and pass/fail criteria.
6. Build a monthly TCO table for both options, including network, load balancer, database, queue, logging, and operations.
7. Write a one-page ADR selecting the right option for a 7-person team, listing risks and conditions to revisit the decision.

**Self-assessment tip:** A strong proposal explains *why* each boundary is needed, its impact on quality attributes, and **how to measure** effectiveness after the change.

## 17. Architecture decision checklist

- [ ] Distinguished layer, tier, module, and microservice.
- [ ] Each layer has clear responsibilities and contracts; business rules are not scattered in controllers.
- [ ] Sensible dependency rules exist; domain/application can be tested independently of adapters.
- [ ] Every new deployment tier has a clear rationale in load, security, ownership, or change lifecycle.
- [ ] All mandatory synchronous calls on the critical path are identified.
- [ ] Impact of network hops, serialization, timeouts, and retries on p95/p99 is measured.
- [ ] Transaction boundaries, consistency, idempotency, and concurrency are explicitly designed.
- [ ] Failure models exist for instance/AZ/database and data recovery procedures.
- [ ] IAM, network segmentation, encryption, and auditing are appropriate.
- [ ] Metrics, logs, tracing, alerts, and runbooks cover operational tiers.
- [ ] TCO includes infrastructure, networking, observability tools, and staffing.
- [ ] The conclusion is recorded as an ADR with verification criteria and review triggers.

**Conclusion:** Layered architecture solves how to **organize responsibilities and dependencies**; N-tier solves how to **deploy and connect components**. Adding tiers delivers value only when it helps meet performance, reliability, security, scaling, or operational targets at an acceptable cost. Start from business requirements, measure quality against scenarios, and verify trade-offs using Well-Architected principles.
