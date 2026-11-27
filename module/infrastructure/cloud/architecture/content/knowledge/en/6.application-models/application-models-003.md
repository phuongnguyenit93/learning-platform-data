# Service-Oriented Architecture and Microservices Architecture

> **Chapter:** Application Models  
> **Scope:** Designing cloud application architectures from business requirements to network, compute, data, and deployment models. This lesson analyzes **Service-Oriented Architecture (SOA)** and **Microservices Architecture** through trade-offs in reliability, security, scalability, cost, operations, and Well-Architected thinking.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish SOA, microservices architecture, and a well-structured monolithic application (modular monolith).
2. Design service boundaries around business capabilities and **bounded contexts**, avoiding splitting services solely by technical layers or database tables.
3. Choose synchronous/asynchronous communication, define API/event contracts, and handle failures and cross-service transactions.
4. Apply principles of independent deployment, data ownership, secure communication, observability, and recovery on the cloud.
5. Compare options using measurable requirements, TCO, organizational complexity, and compliance readiness.
6. Outline a phased migration and evaluate the design against Well-Architected pillars.

## 1. The essence of SOA and microservices

### 1.1. What is Service-Oriented Architecture (SOA)?

**Service-Oriented Architecture — SOA** is an architectural style that organizes software capabilities into **services with explicit contracts**, so other applications or business processes can consume them through published interfaces.

A service might represent a capability such as **customer management**, **credit checking**, **inventory lookup**, or **invoice processing**. Consumers do not need to know the full internal implementation, but they must understand the capabilities, rules, data, and constraints provided by the service contract.

SOA often appears in large organizations needing to integrate many legacy applications, heterogeneous technologies, or systems across business units. SOA **is not defined by a single technology**: SOAP/WSDL, REST, message brokers, API gateways, and other communication mechanisms can all participate depending on context.

In some enterprise SOA solutions, an **Enterprise Service Bus (ESB)** acts as an intermediary for routing, message transformation, process orchestration, and applying integration policies. An ESB is a common implementation pattern, **not a mandatory requirement** for a system to be considered SOA.

### 1.2. What is Microservices Architecture?

**Microservices Architecture** structures an application as a collection of services with **clear business boundaries**, typically owned end-to-end from development to operations by teams, capable of **relatively independent release and scaling**.

Each service should own the logic and data within its scope; services collaborate via APIs or contracted events. The core idea is **autonomy and reducing coupling during change**. "Micro" does not mean few lines of code, a single database table, or a single endpoint.

Microservices can be viewed as one realization of service-oriented thinking, emphasizing attributes such as independent deployment, partitioned data ownership, automation, and business-aligned team organization. Still, **SOA and microservices are not mutually exclusive rule sets**; a system can exhibit characteristics of both.

### 1.3. A well-structured monolith remains a valid option

A **modular monolith** contains multiple business modules with clear boundaries, yet is packaged, executed, and typically deployed together. It can allow direct data transactions, easy end-to-end testing, and lower initial operational overhead.

Do not conclude that "microservices are the mandatory next step after a monolith." If the team is small, the domain is not yet clear, or the system has no need for independent deployment, a modular monolith often delivers software faster and more safely.

### 1.4. Illustrating three ways to organize

~~~mermaid
flowchart TB
    subgraph M["Modular monolith"]
      MA["Catalog module"] --> MB["Order module"]
      MB --> MC["Payment module"]
      MD[("Single deployment unit")]
    end
    subgraph S["SOA: integrating multiple systems"]
      SA["CRM"] --> SE["API / integration intermediary"]
      SB["ERP"] --> SE
      SE --> SC["Billing service"]
      SE --> SD["Inventory service"]
    end
    subgraph U["Microservices"]
      UA["Order service"] --> UB["Inventory API"]
      UA --> UC["Payment API"]
      UA --> UE["Event broker"]
      UE --> UD["Notification service"]
    end
~~~

The diagram illustrates concepts; it does not imply that every SOA system must use a central integration hub or that every microservice must communicate directly.

## 2. Similarities and differences: do not just count services

| Criterion | Enterprise-integration SOA | Microservices | Modular Monolith |
| --- | --- | --- | --- |
| Typical goal | Capability reuse, cross-platform system integration | Change autonomy, deployment and scaling by business domain | Deployment simplicity, keeping module boundaries clear |
| Service scope | Can be fairly broad, serving many applications | Usually focused on a single capability/bounded context | Modules inside the same application |
| Contracts | APIs and messages, often with integration governance | Versioned APIs/events, emphasizing autonomy | In-process module interfaces |
| Data | May use shared or coordinated data models | Prioritizes dedicated data ownership per service | Can share one DB with module rules |
| Releases | May depend on shared integration processes | Goal is relatively independent releases | Releases the whole application |
| Integration | May include ESB or shared orchestration layer | Uses API gateway, broker, service-to-service; avoids central node holding too much business logic | In-process internal calls |
| Change control | Can have centralized contract governance | Primarily via contracts and team ownership | Via encapsulation rules and tests |
| Operational cost | Depends on integration platform and legacy systems | Multiple deployment units, observability, security, data | Usually lower initially |
| Common pitfalls | Integration intermediary becomes a bottleneck or slows change | Distributed monolith, network failures, inconsistent async data | Hard to scale/release independently if boundaries evolve poorly |

**Note:** the table describes design tendencies; there is no rule that SOA must use SOAP or an ESB, that microservices must use REST or Kubernetes, or that an SOA service cannot be deployed independently.

### Evaluating by "degree of coupling"

A system with 40 services that must all deploy simultaneously whenever a single data field changes may be a **distributed monolith**. It pays the price of networking and distributed infrastructure while gaining no autonomy.

Conversely, an application with six clear business modules, minimal circular dependencies, solid tests, and daily releases can satisfy requirements much better in early stages.

Ask three questions before naming an architecture:

1. Can a team **change and release a business capability** with minimal need for other teams to edit code?
2. How are failures, load, and sensitive data **contained in blast radius**?
3. Are operational cost and complexity proportional to **measurable requirements**?

## 3. Partitioning service boundaries by business domain

### 3.1. Bounded contexts and ownership

In **Domain-Driven Design (DDD)**, a *bounded context* is a boundary within which terminology, rules, and business models have consistent meaning. Context boundaries are a useful starting point for finding service boundaries, though **one bounded context does not have to correspond one-to-one with one service**.

Example booking application:

- **Catalog:** service listings, availability schedules, and display rules.
- **Booking:** booking state, reservation rules, and cancellation policies.
- **Payment:** payment requests, transaction states, refund handling.
- **Customer:** customer profiles and access policies.
- **Notification:** message delivery and delivery status tracking.

Contexts may interpret the word "status" differently. Booking has **CONFIRMED/CANCELLED**; Payment has **AUTHORIZED/CAPTURED/REFUNDED**. Forcing them to share a single system-wide enum creates unnecessary cross-domain coupling.

~~~mermaid
flowchart LR
    CU["User"] --> API["API Gateway / BFF"]
    API --> BK["Booking"]
    API --> CA["Catalog"]
    BK --> PA["Payment"]
    BK --> IN["Inventory"]
    BK --> EV["Event broker"]
    EV --> NO["Notification"]
    BK --> DB1[("Booking data")]
    PA --> DB2[("Payment data")]
    IN --> DB3[("Inventory data")]
~~~

Arrows are illustrative business dependencies. They do not force every step to be synchronous or create distributed transactions.

### 3.2. Criteria for choosing good boundaries

A service generally makes sense when:

- It has a **distinct business capability and language**; a person/team owns its rules.
- Its changes can be tested and deployed relatively independently.
- It owns the data needed to enforce core **business invariants**.
- Its load, availability, data, or compliance profile differs significantly from the rest.
- Its APIs/events have clear business intent, rather than being CRUD wrappers directly exposing internal tables.
- The separation benefit is large enough to offset networking, data, deployment, logging, and on-call costs.

**Avoid splitting by technical layer** into CustomerControllerService, CustomerRepositoryService, and CustomerDatabaseService if a single business request must traverse all those "services" for basic work. That increases network chatter without establishing autonomous boundaries.

### 3.3. Signs of poorly drawn boundaries

- Every feature requires modifying multiple services simultaneously.
- Service A must directly query Service B's tables to execute its logic.
- One user request triggers dozens of synchronous steps; latency and error rates climb rapidly.
- A "shared" service accumulates heavy business rules from multiple domains.
- Teams wait on a central governance team to modify shared orchestration for every minor change.

When these signs appear, consider **merging services**, redrawing bounded-context boundaries, moving coordination back to the process owner, or using events to reduce temporal coupling.

## 4. Communication contracts: synchronous, asynchronous, and integration

### 4.1. Synchronous communication (request/response)

A service calls another service's API and typically waits for a response. Appropriate when the caller genuinely needs **an immediate result**, such as Booking needing payment authorization confirmation before returning status.

Common technical options:

- **HTTP/REST:** easy client interoperability, large ecosystem, clear resource/business representation.
- **gRPC:** strongly typed contracts, streaming support, efficient communication in certain environments.
- **SOAP:** still common in enterprise integrations with formal contracts and specific standards requirements.
- **Message request/reply:** can run over a broker, though it still creates a synchronous wait dependency if caller logic blocks on the reply.

Choose technology based on contracts, environment, latency, and operability. **No protocol automatically turns a service into a microservice or SOA.**

**Risks:** network failures, timeouts, connection resets, incompatible contract versions, and multi-step fan-out increasing latency/error rates. Never assume internal service calls are as reliable as in-process method calls.

### 4.2. Asynchronous communication via events/messages

A service publishes an event describing a change that occurred; interested services consume it to update local data or trigger tasks.

Example after Booking confirms an order:

~~~json
{
  "event_id": "evt-731a",
  "event_type": "BookingConfirmed",
  "event_version": 1,
  "occurred_at": "2026-11-18T04:30:00Z",
  "booking_id": "bkg-204",
  "customer_id": "cust-19",
  "tenant_id": "tenant-08"
}
~~~

Illustrative payload. Events need contracts, event IDs, versions, timestamps, authorization rules, and traceability. Do not include sensitive data just because the broker is "internal."

**Benefits:** producers and consumers do not need to be available simultaneously; easy consumer scaling; reactive flows after business completion. **Trade-offs:** delivery can be duplicated, out of order, delayed, or failed; the system needs idempotency, controlled retries, dead-letter handling, and replay procedures.

### 4.3. Orchestration vs. choreography

- **Orchestration:** a coordinator knows the workflow steps, decides whom to call next, and handles timeouts and compensations. Easy to inspect the overall workflow, but the coordinator can become a major point of coupling.
- **Choreography:** services react to events emitted by other services. Reduces centralized coordination, but makes tracing the action chain hard when there are too many events and implicit dependencies.

Both can be used in SOA and microservices. Choose based on business complexity, observability needs, resilience, and workflow ownership; do not assume choreography is always better.

### 4.4. API Gateway, ESB, and service mesh do not replace each other

| Component | Typical Responsibilities | Should Not Take Over |
| --- | --- | --- |
| **API Gateway / BFF** | Client entry point; initial auth, routing, rate limiting, client-facing interface adaptation | Core business rules across all domains |
| **ESB / integration platform** | Connecting heterogeneous protocols, data transformation, governed integration orchestration | Becoming a hub for all product logic if it slows change |
| **Message broker** | Routing and buffering messages/events per platform guarantees | Enforcing business invariants or end-to-end exactly-once |
| **Service mesh** | Service-to-service connectivity policies, mTLS, telemetry, traffic management per platform | Designing business permissions, data boundaries, transactions |

**You do not necessarily need all of them.** A small system might need only an API gateway and a managed queue. Adding more intermediary layers increases configuration, operational skill requirements, and cost.

## 5. Data and cross-service transactions

### 5.1. Each service owns its data, not necessarily its own DB server

The **database ownership** principle means only the owning service may write or dictate the structure of its business data. You may have separate databases/schemas, or separate via permissions and access rules within shared managed infrastructure; the core requirement is **no direct dependency on another service's internal tables**.

If Booking needs Payment status, use a published API or maintain a **read model/projection** updated from contracted events. Avoid having Booking join directly against Payment tables in a shared database, because any Payment schema change can break Booking.

### 5.2. Why are distributed transactions hard?

Within a single database, an ACID transaction can update multiple related tables atomically. When Booking, Inventory, and Payment own separate data, you cannot assume a single shared database transaction protects the whole process.

Approaches:

- **Keep invariants inside one service** whenever possible; operations requiring strong consistency should sit inside the same business/transaction boundary.
- **Saga** for multi-service workflows using local steps and compensating actions when later steps fail.
- **Transactional outbox** to write business data and event records in the **same local transaction**, then relay events to the broker.
- **Idempotent consumer** to process the same message repeatedly without creating duplicate side effects.
- **CQRS/read projection** when a fast consolidated view is needed and designed update lag is acceptable.

Not every saga can "roll back" cleanly to the exact prior state: refunding after a charge may involve business rules, fees, or waiting periods; define intermediate states explicitly and provide manual resolution when compensation fails.

### 5.3. Booking Saga example

Consider the workflow: **reserve resource → charge payment → confirm booking**. When payment fails, the system must release the reserved spot.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant B as Booking / Orchestrator
    participant I as Inventory
    participant P as Payment
    participant E as Event broker
    C->>B: POST /bookings (idempotency key)
    B->>B: Create PENDING state
    B->>I: Reserve(item, bookingId)
    I-->>B: Reservation token
    B->>P: Charge(amount, bookingId)
    alt Payment succeeded
      P-->>B: Charged
      B->>B: CONFIRMED + write outbox
      B-->>C: Status CONFIRMED
      B-->>E: BookingConfirmed via outbox relay
    else Declined or confirmation failed
      P-->>B: Failed or unknown
      B->>B: Check outcome/idempotency
      B->>I: Release(reservation token) when appropriate
      B-->>C: FAILED / PENDING_REVIEW
    end
~~~

This is a conceptual diagram. In practice, **a Payment timeout does not prove Payment failed**: you must query transaction status or process callbacks/webhooks with an idempotency key before compensating. Especially avoid charging twice on retries.

### 5.4. Outbox and idempotency

An illustrative outbox design:

~~~sql
BEGIN;
UPDATE booking
SET status = 'CONFIRMED'
WHERE id = :booking_id;

INSERT INTO outbox_event
    (event_id, aggregate_id, event_type, payload, created_at)
VALUES
    (:event_id, :booking_id, 'BookingConfirmed', :payload, CURRENT_TIMESTAMP);
COMMIT;
~~~

A separate relay reads unpublished outbox rows, sends them to the broker, and marks them processed. Because the relay can send duplicates if it crashes between sending and marking, consumers should handle **at-least-once delivery** conservatively. For example, the consumer records the processed `event_id` in the same transaction as its related state update, or uses an appropriate unique constraint.

An API **idempotency key** is generated/scoped per user or tenant, bound to a logical operation, and given a clear retention window. Do not conflate requests that share a key but carry different payloads without checking.

## 6. Reliability: the network becomes part of the failure model

An in-process function call has a different latency and failure profile from a network call. In a distributed architecture, every dependency adds another failure point and slow path.

As a **simple estimation** example: a sequential path must call four services, each with an independent 99.9% success probability under the same measurement window and conditions. The probability that all succeed is approximately:

\[
0.999^4 \approx 99.60\%
\]

This figure **only illustrates** the case under an independence assumption; shared infrastructure failures, retries, and caching alter actual outcomes. The practical takeaway is to avoid long synchronous chains and design for graceful degradation.

### Essential mechanisms

| Mechanism | Purpose | What to Avoid |
| --- | --- | --- |
| **Timeouts and deadlines** | Bound wait times; propagate remaining time budget from root request | Overly long timeouts exhausting thread/connection pools |
| **Retries with backoff and jitter** | Overcome transient errors; avoid retry storms | Unbounded retries; retrying non-idempotent side-effect operations |
| **Circuit breaker** | Stop failing dependencies from cascading into the caller | Treating a breaker as a fix for the root bug |
| **Bulkhead / isolation** | Isolate quotas, thread pools, connections, and load across workloads | Letting one slow service exhaust all shared resources |
| **Rate limiting and backpressure** | Block overload before it spreads | Unbounded queue growth |
| **Graceful degradation** | Preserve core functions if auxiliary ones fail | Returning fake success for operations requiring correctness |
| **Health checks** | Separate liveness and readiness; govern routing/startup | Having readiness depend on every non-essential system and causing cascading outages |
| **Multi-AZ / DR** | Reduce impact of component/zone loss; recover data | Trusting RTO/RPO from diagrams without running drills |

For example, an unresponsive product recommendation service should not fail the entire checkout if recommendations are optional. Conversely, when payment capture cannot be confirmed, **never display "paid"** merely for a smoother user experience.

### Scaling mechanisms

Microservices allow scaling a high-load service independently, but only when the **real bottleneck** lies inside that service and downstream dependencies have capacity. Doubling API replicas will not help if the database, broker, or payment partner is already saturated.

Measure CPU, memory, throughput, p95/p99 latency, queue depth/age, error rates, and dependency saturation before choosing autoscaling rules. For background jobs, scaling on queue depth/age is often more useful than CPU.

## 7. Security and trust boundary governance

A system with many services and links must control **both external ingress and service-to-service access**.

1. **Identity and authorization:** authenticate clients appropriately; the API gateway validates basic tokens, while the data-owning service enforces business authorization itself. Never assume requests from the internal network are trustworthy.
2. **Service identity:** each workload has its own identity and least-privilege permissions; use mTLS or appropriate transport protection, and manage certificates and key lifecycles.
3. **Segmentation and egress:** route through permitted network zones/endpoints, enforce DB/broker access policies, control outbound egress, and isolate environments.
4. **Secrets:** use a secrets management system; avoid embedding keys in images/source/logs; rotate on personnel changes or incidents.
5. **Data classification and residency:** identify where personal data, payment details, replicas, logs, and events are stored/transmitted; encrypt at rest and in transit.
6. **Threat modeling:** evaluate API authorization, replay attacks, event spoofing, log leakage, mesh/gateway misconfiguration, supply chain pipelines, images, and libraries.
7. **Auditing:** record critical access and mutation events sufficiently for traceability, while avoiding unnecessary sensitive data in traces or event payloads.

Splitting into small services can **increase the attack surface** if IAM or network policies are overly permissive; separating services does not automatically improve security. Likewise, an ESB or API gateway does not replace business authorization checks at the target service.

In multi-tenant systems, propagate an **authenticated tenant context** across APIs, queues, and jobs, and enforce tenant isolation at the data layer. A client-supplied Tenant ID alone is not proof of authorization.

## 8. Cloud deployment: infrastructure decisions must follow requirements

### 8.1. Compute and deployment models

SOA and microservices can run on virtual machines, containers, managed container platforms, or serverless. Choose based on deployment needs, startup time, load, connectivity, operational cost, and organizational constraints.

| Option | Fits When | What to Control |
| --- | --- | --- |
| **VM / managed app platform** | Simple environments or legacy applications | Standard images, patching, autoscaling, HA |
| **Container orchestration** | Multiple workloads needing rolling updates, service discovery, self-healing | Cluster operations, network policies, permissions, capacity, cost |
| **Serverless functions / managed containers** | Variable load, short/independent tasks, reducing server management | Cold starts, execution limits, concurrency, DB connections, traffic-based cost |
| **Managed database / broker** | Reducing operational burden for foundational infrastructure | Backups, permissions, quotas, failover, service limits, deployment regions |

**Kubernetes is not what defines microservices.** A handful of services on a managed app platform can still release independently; a monolith running on Kubernetes is still a monolith.

### 8.2. Networking and service discovery

When deploying to the cloud, define:

- Public/private boundaries, ingress, load balancers, API gateways, DNS, and how service discovery works.
- Regions and availability zones for workloads/data; latency and **cross-zone/cross-region transfer** charges where applicable.
- Connectivity to databases, brokers, and external partners; egress policies and port/connection limits.
- Where TLS/mTLS, IAM, rate limiting, network policies, and web application firewalls apply as required.
- Safe route/version switching mechanisms during rollout and recovery.

Do not use service discovery or a service mesh to mask tight communication contracts: network reachability does not mean API changes are compatible.

### 8.3. CI/CD and release independence

An independently releasable service needs a minimum pipeline: build, dependency checks, contract tests, security scans, immutable identified artifact creation, bounded rollout, monitoring, and rollback or roll-forward.

**Backward compatibility** is especially critical:

- Add optional fields with defaults; do not force every consumer to upgrade immediately.
- For public APIs, avoid changing the semantics of an existing field name; version breaking changes.
- For events, consumers must handle supported versions, missing fields, and duplicate messages.
- For databases, prefer **expand → migrate → contract** cycles so old and new application versions do not break each other while running concurrently.

In an SOA setup with an integration platform, also verify mapping compatibility, routing, canonical schema changes, and the impact of modifying ESB flows.

## 9. Observability, operations, and recovery

A distributed system cannot be operated effectively by inspecting logs on individual machines.

### Signals to connect

- **Metrics:** request rate, error rate, p50/p95/p99, saturation, timeouts, queue age, job retries, dependency error rates, resource usage.
- **Distributed tracing:** correlation ID/trace ID across APIs, queues, and jobs; used to trace a request's actual path.
- **Structured logs:** include service identifier, version, environment, request/trace ID, and error codes; avoid logging tokens, passwords, or sensitive data.
- **Service map and ownership:** who owns each service, upstream/downstream dependencies, runbooks, dashboards, on-call rotations.
- **Business metrics:** successful bookings, duplicate/ambiguous charges, pending events, reconciliation discrepancies.

Track **user-journey SLIs/SLOs**, not just individual container health. For example, a checkout SLO must specify what counts as a successful checkout, response deadline, measurement window, and reasonable exclusions. An **SLA** is a contractual commitment and may differ from internal SLOs.

### Incident and data failure management

A proper runbook should answer: which service or flow is impacted; who receives alerts; can load be shed or auxiliary features disabled; are messages backlogged or duplicated; how to replay safely; and who authorizes data restoration.

**RTO** is the maximum acceptable recovery time; **RPO** is the maximum tolerable data loss measured in time. Both targets must be defined for business workflows and their associated data, not merely individual VMs. For instance, restoring Booking while losing Payment outbox records can create transactional inconsistency even if every server is healthy.

Rehearse real scenarios: a service loses DB connectivity, broker slows down, an AZ becomes unavailable, a dependency fails persistently, events are redelivered, and an incompatible deploy occurs. Record results against SLOs, RTO/RPO, and remediation cost.

## 10. Performance, cost, and Well-Architected trade-offs

### 10.1. Microservices are not faster by default

In-process function calls generally incur far less overhead than network HTTP calls. In microservices, serialization, TLS, DNS, load balancing, distributed databases, and queues all have costs. Designs should prioritize **reducing hops on the critical path**, using controlled read caches, and offloading non-immediate work to asynchronous paths.

When performance matters, measure **p95/p99 at target load**, not just averages. Microservices enable **selective scaling**, but do not guarantee high throughput if requests routinely require synchronous calls across many services.

### 10.2. TCO includes both infrastructure and complexity

A conceptual model:

\[
TCO = C_{\text{compute}} + C_{\text{data}} + C_{\text{network}} + C_{\text{platform}} + C_{\text{ops}} + C_{\text{reliability/security}}
\]

Where:

- **Compute:** service replicas, headroom capacity, autoscaling, test environments.
- **Data:** DBs, indexes, backups, replicas, storage, and recovery.
- **Network:** load balancers, gateways, egress, cross-AZ/region transfer where billed.
- **Platform:** brokers, discovery, mesh, registries, CI/CD, observability.
- **Ops:** on-call, incidents, contract testing, schema and permission management.
- **Reliability/security:** DR drills, audits, scanning, secrets, policies, and patching.

Microservices can save money when a small fraction of an application requires massive resources; conversely, splitting too many low-traffic services increases baseline resources and operational toil. SOA integrating multiple systems can avoid duplicating shared capabilities, though a heavy ESB or intermediary layer also carries costs and bottlenecks.

### 10.3. Framing decisions across the six Well-Architected pillars

| Assessment Pillar | Questions for SOA and Microservices |
| --- | --- |
| **Operational Excellence** | Which team owns the service? Are IaC, runbooks, pipelines, and change management in place? |
| **Security** | Are identity, per-service permissions, data, secrets, and audit boundaries clear? |
| **Reliability** | Are timeouts, circuit breakers, idempotency, HA, DR strategy, and drills in place? |
| **Performance Efficiency** | Are p95/p99 measured, long synchronous chains avoided, and the right bottlenecks scaled? |
| **Cost Optimization** | Is TCO attributed per application/service; are unnecessary services and resources trimmed? |
| **Sustainability** | Are right-sizing, autoscaling, idle reduction, and trimming unnecessary storage applied? |

The pillars guide **periodic review and improvement**, rather than producing a single right answer. A decision might improve release velocity while increasing cost and operational risk; document clearly who accepts the trade-off.

## 11. When to choose SOA, microservices, or modular monolith?

### Decision framework

| Signal from Requirements | Approach Worth Considering First |
| --- | --- |
| Need to integrate CRM, ERP, billing, and long-lived legacy systems across departments | SOA with a governed integration layer |
| Independent teams/domains with distinct release cadences and very different load profiles | Domain-bounded microservices |
| Small team, rapidly shifting domain, limited automation and observability | Modular monolith with disciplined module boundaries |
| One part needs special security/load/cost isolation | Extract that part selectively into a separate service; keep the rest monolithic |
| Multiple services must deploy together and share schemas directly | Revisit boundaries; avoid a "distributed monolith" |
| Strong data synchronization required in a short flow with minimal split benefit | Keep the transaction inside one processing boundary when appropriate |
| Must support many partners with existing integration contracts | Organize adapters, API contracts, and event integration; no need to microservicize everything |

**Do not decide based on a trending buzzword.** Before splitting, ask about business impact: how much independent scaling is needed, which team owns it, what reliability is required, and what maximum infrastructure/operational cost is acceptable.

### Minimum prerequisites for microservices to pay off

- Domain boundaries are understood well enough to establish clear **ownership**.
- CI/CD and deployment of one service do not force releasing all other services.
- Contract/API testing, versioning strategy, and running multiple versions side by side when needed.
- Distributed observability, dashboards, and accountable alert responders.
- Plans for data, transactions, and network failures.
- Operational tooling and skills proportional to the number of services.

If these foundations are missing, invest first in **modularization, tests, CI/CD, and metrics**, then extract domains incrementally where evidence proves autonomy is needed.

## 12. End-to-end practical scenario: cloud booking platform

A platform supports service search, booking, payment, and notifications. The product team observes:

- Search accounts for most traffic and spikes sharply during campaigns.
- Booking must guarantee no duplicate orders and prevent overbooking available capacity.
- Payment relies on an external payment gateway with delayed callbacks.
- Notifications matter for UX, but must never block the payment flow.
- Operations targets tracking **p95**, booking success rate, cost per order, and incident recovery capability.

### 12.1. Proposed boundary partitioning

| Component | Owns | Preferred Communication | Primary Risks |
| --- | --- | --- | --- |
| Catalog/Search | Listings and search results | Read API, async index updates | Stale cache, search load spikes |
| Booking | Orders, reservation states, cancellation rules | Client API; coordinates Inventory/Payment | Duplicate orders, inconsistency after timeout |
| Inventory | Available capacity and reservations | Keyed reserve/release APIs | Overselling, race conditions |
| Payment | Payment intents, reconciliation, webhooks | API + webhooks/events | Double charging, ambiguous status |
| Notification | Creating, sending, tracking notifications | Consumes events after business states | Duplicate sends, backlog, provider failures |

This is just one option; if the team is small or Booking–Inventory transactions are tightly coupled, those two domains can start in the same service or module as long as correctness is proven.

### 12.2. A resilient booking flow

~~~mermaid
flowchart TD
    UI["Client / API Gateway"] --> BK["Booking API"]
    BK --> BDB[("Booking DB + Outbox")]
    BK --> INV["Inventory API / DB"]
    BK --> PAY["Payment API / DB"]
    PAY --> EXT["Payment gateway"]
    BDB --> RELAY["Outbox relay"]
    RELAY --> BROKER["Broker"]
    BROKER --> NOTIFY["Notification worker"]
    BROKER --> REPORT["Analytics projection"]
~~~

The flow must define states such as **PENDING, RESERVED, PAYMENT_PENDING, CONFIRMED, FAILED, CANCELLED** and valid transitions for each state. Avoid holding an HTTP request open waiting long durations for a third-party payment callback; return a pending state with a lookup ID and update asynchronously.

### 12.3. Failure handling matrix

| Scenario | Reasonable Handling | Evidence to Verify |
| --- | --- | --- |
| User clicks book multiple times | Idempotency key, business-level unique constraint | One logical request never creates two bookings |
| Timeout after calling Payment | Query status using transaction key; do not immediately recharge | Zero double charges under retries |
| Inventory declines reservation | Return clear status; do not execute erroneous payment | No overselling under concurrent load |
| Broker temporarily unavailable | Persist outbox in transaction; relay with controlled retries | Event eventually processed; idempotent consumer |
| Notification provider fails | Bounded retries and dead-letter path | Checkout still completes cleanly |
| Booking database fails | Health checks, failover/restore, outbox and consistency checks | RTO/RPO measured via drills |
| Search overloaded | Caching, rate limiting, autoscaling, graceful degradation | Checkout is not taken down by search |

### 12.4. Illustrative architecture requirements and verification

The following values are **exercise assumptions**, not default SLOs:

| Assumed Requirement | Verification Test |
| --- | --- |
| Search p95 ≤ 300 ms at 500 requests/sec in target scenario | Load test with representative production-like data and cache |
| Booking creates no duplicate orders on resent requests with same idempotency key | Concurrency/retry tests and constraint checks |
| Checkout success rate meets SLI/SLO agreed by Product and SRE | Synthetic transactions, end-to-end dashboards |
| Notification failure does not prevent Booking from recording successful transactions | Provider outage injection and backlog recovery test |
| No confirmation events lost due to crash after Booking commit | Outbox relay drill, duplicate delivery, and replay |
| Meets approved RTO/RPO for Booking + Payment | Restore/failover drill and data reconciliation |
| Cloud cost within budget at normal/peak load | Cost model covering compute, network, broker, DB, observability, DR |

**Important:** requirements like "no duplicate bookings / no double charges" are never achieved through retries or adding replicas alone. You must design business invariants, idempotency keys, database constraints, and reconciliation.

## 13. Incremental migration from an existing system

Apply the **Strangler Fig Pattern**: route selected flows through a façade/API gateway and gradually replace legacy capabilities with new services, instead of trying to split the entire application at once.

~~~mermaid
flowchart LR
    C["Client"] --> F["Façade / Gateway"]
    F --> OLD["Existing application"]
    F --> NEW["Extracted new service"]
    NEW --> OWN[("Owned data")]
    OLD --> LEGACY[("Legacy data")]
    OLD -. "Events / forwarding adapter" .-> NEW
~~~

### Six-step plan

1. **Map domains and dependencies.** Measure cross-module change frequency, deployment cadence, load, errors, and data access. Pick a capability with clear boundaries and few cross-domain transactions.
2. **Stabilize contracts.** Define versioned APIs/events, ownership, and minimal exchanged data; design consumers to keep working when producers deploy first.
3. **Build an independent deployment path.** CI/CD, image/artifact, configuration, secrets, logs, metrics, alerts, rollback, and runbook for the new service.
4. **Separate data ownership.** Avoid uncontrolled dual writes across two schemas. When migrating data, use explicit replication, reconciliation, and cutover; test recovery.
5. **Shift traffic safely.** Canary, feature flags, shadow reads (where appropriate), discrepancy monitoring; define stop and rollback criteria.
6. **Remove legacy dependencies.** After sufficient evidence over time, remove unused routes/adapters/code; update ADRs and system diagrams.

**Choosing the split point:** Notification is usually easier to make independent than a payment or inventory transaction deeply tied to the same database. Still, "easy" depends on actual coupling and reconciliation capability.

### Verification checks during extraction

- Contract tests between producer/consumer, schema compatibility, and dual-version coexistence.
- Fault injection tests: new service down, slow network, duplicate messages, broker lag.
- Track latency, errors, cost, deployments, and incident counts before/after extraction.
- Verify IAM permissions, TLS, secrets, service identities, data residency, and auditing.
- Rehearse rollback when old and new paths have overlapping data or events.

Do not treat creating another deployment as a "successful migration" if synchronized releases and cross-service table sharing are still required.

## 14. Recording decisions with an Architecture Decision Record (ADR)

An ADR helps future engineers understand goals, alternatives, experiments, and accepted risks.

~~~markdown
# ADR-032: Extract Notification from the booking application

Status: Proposed / conditionally approved
Decision owner: Architect and Product/SRE representatives
Date: YYYY-MM-DD

Context:
- Notification provider has transient failures, slowing down checkout.
- Notification has a different load and deployment lifecycle from Booking.
- Team already has CI/CD, broker, dashboards, and on-call.

Options:
A. Keep a modular monolith, processing via internal jobs.
B. Extract Notification service consuming events from outbox.
C. Split all domains immediately.

Proposed decision:
- Choose B, keeping Booking as the source of truth for order state.
- Booking writes events to outbox in the same local transaction.
- Notification processes idempotently, with bounded retries and DLQ as needed.

Trade-offs:
- Introduces eventual consistency delay and broker operations.
- Requires cross-service tracing, replay handling, and backlog monitoring.

Acceptance criteria:
- Provider failures do not fail checkout.
- Zero lost events after crash/restart; duplicate deliveries handled safely.
- Measure checkout p95, queue age, cost, and recovery procedure.

Review triggers:
- Load or cost changes significantly; SLOs are violated;
  domain needs change or replay errors cannot be resolved.
~~~

## 15. Common mistakes and how to avoid them

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Splitting services per table or controller | Too many hops and lockstep releases | Split by bounded context/business invariants |
| Letting every service access a shared schema | DB changes cause cascading failures | Enforce data ownership, APIs, or event projections |
| Putting all business rules into ESB/gateway | Integration layer becomes an innovation bottleneck | Keep business logic in the owning domain |
| Assuming microservices require Kubernetes | Buying unnecessary infrastructure complexity | Choose runtime based on measurable requirements |
| Ignoring network failures and timeouts | Local failures cascade widely | Timeout budgets, safe retries, bulkheads, circuit breakers |
| Assuming messages are processed exactly once | Duplicate orders/charges/notifications | Idempotency, deduplication, outbox, and reconciliation |
| Measuring only per-service CPU | Misses business workflow failures | User-journey SLOs, tracing, business metrics |
| Splitting services before understanding domains | Repeatedly editing multiple services together | Modularize first; extract based on real usage data |
| Replicating data without consistency rules | Stale projections or decisions made on outdated data | Define consistency level, freshness, source-of-truth rules |
| Independent deployments without owner/on-call | Nobody owns integration failures | Clear ownership, runbooks, alerts, and on-call duties |
| Treating mesh/gateway security as full authorization | Unauthorized business data reads still possible | Enforce authorization at service and data layers |
| Counting only compute cost | Under-budgeting broker, DB, egress, observability, and DR | Full TCO across load scenarios |

## 16. Practice exercise

A company runs a large sales management application serving 200 stores. It integrates with ERP, payments, and shipping; new features launch multiple times per month. Recently, email-sending failures have blocked order creation, while product search sees many times the traffic of payments. The engineering org has three independent teams, but lacks full distributed tracing.

Complete the following:

1. **Requirements analysis:** write at least six measurable requirements covering order creation, search, ERP integration, payments, security, cost, and operations. Mark which targets are still assumptions to confirm.
2. **Propose three options:** (A) modular monolith with background jobs, (B) SOA with an integration layer across existing systems, (C) selective extraction into microservices. State pros/cons, dependencies, and fit with team maturity.
3. **Sketch domain boundaries:** define owned data for Order, Catalog/Search, Payment, Notification, and Adapter/Integration.
4. **Draw the failure flow:** when Payment times out after accepting a request, how does the system distinguish "unpaid" from "unknown outcome"? How do you prevent double charging on retries?
5. **Design contracts:** one API with an idempotency key and one event with `event_id`/`version`; specify when the event is emitted and how duplicate messages are handled.
6. **Operations:** propose SLIs/SLOs, dashboards, trace propagation, queue-age alerts, a runbook when the broker disconnects, and one DR scenario.
7. **Decision:** write a short ADR choosing the right option; present residual risks, estimated TCO, and review triggers.

**Self-assessment tip:** a strong answer does not have to split the most services. It clearly identifies who owns data and rules, when synchronous calls are mandatory, where events fit, how correctness is preserved, and what evidence must be measured to decide.

## 17. Pre-finalization architecture review checklist

- [ ] Started from business goals, load, SLOs, RTO/RPO, security, budget, and team capability.
- [ ] Service/module boundaries align with business capabilities; owners and sources of truth are identified.
- [ ] Every API/event has a contract, version, and backward-compatible change handling.
- [ ] Network flows have timeouts, safe retries, backpressure, and explicit error handling.
- [ ] Operations with side effects have idempotency/deduplication and reconciliation for ambiguous outcomes.
- [ ] No direct access to another service's internal DB tables.
- [ ] Distributed workflows specify intermediate states, compensations, outbox, and replay procedures.
- [ ] Identity, authorization, secrets, network policies, encryption, auditing, and data residency are designed.
- [ ] Genuine independent deployment pipelines and rollback/roll-forward strategies exist.
- [ ] User-journey traces, logs, metrics, SLIs/SLOs, and incident ownership are established.
- [ ] Load, network failure, duplicate message, DR, and data inconsistency tests exist.
- [ ] TCO comparison includes infrastructure, data, network transfer, platform, and operations.
- [ ] An ADR exists with trade-offs, residual risks, verification evidence, and review triggers.

## Key Takeaways

**SOA** organizes software capabilities into contracted services for integration and reuse, especially useful in multi-system environments. **Microservices** emphasize business boundaries, data ownership, and relatively independent deployment, fitting when scale and organizational needs justify service-level autonomy. A **modular monolith** remains a strong choice when the problem does not yet require distribution.

Good architecture is proven by meeting **business requirements, correctness, SLOs, security, scalability, cost, and operations** in practice. Pattern names are only a starting point; contracts, data boundaries, failure testing, and Well-Architected evidence show whether the choice actually fits.
