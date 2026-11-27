# Monolith Decomposition and Service Boundaries on AWS

A monolithic application often starts as a sensible implementation approach: business capabilities live in the same codebase, share a single build pipeline, and typically access a single database. This structure helps development teams start quickly, test easily, and execute transactions within a single process. As the product grows, multiple teams end up modifying the same codebase, deploying a small change may require releasing the entire application, and a bug or traffic spike in one feature can affect other features.

Decomposing a monolith into services helps organize the system around business capabilities, allowing each part to evolve and scale independently. However, splitting an application into multiple processes also introduces network communication, distributed failures, asynchronous data, and new operational requirements. Dividing along database tables or technical layers without clear business boundaries can create a distributed monolith that is harder to change than the original application.

On AWS, there are multiple ways to implement those boundaries: Amazon ECS or Amazon EKS for long-running services, AWS Lambda for event-driven processing, Amazon API Gateway or Application Load Balancer for HTTP communication, Amazon SQS, Amazon SNS, and Amazon EventBridge for asynchronous integration, along with data services suited to each business domain's ownership. AWS services are only the implementation vehicle; the right boundaries must start from how the business creates value and manages data.

This lesson falls under `CLOUD_PROVIDERS_AWS`: designing scalable, secure, operable, and cost-controlled applications. The focus is on recognizing monolith limits, identifying bounded contexts, choosing decomposition approaches, migrating incrementally using Strangler Fig, and designing communication, data, and deployment on AWS.

## 1. Learning Objectives

After this lesson, you can:

- Identify when a monolith needs refactoring and when it is still better to keep a monolithic architecture.
- Distinguish between a modular monolith, service-oriented architecture, and microservices.
- Define service boundaries based on business capability, bounded context, data ownership, and rate of change.
- Decompose a monolith by business domain rather than mechanically splitting by technical layers or database tables.
- Design synchronous and asynchronous communication using API Gateway, load balancers, SQS, SNS, and EventBridge.
- Plan incremental migration using Strangler Fig, manage data transitions, and avoid dual-writes.
- Choose ECS, EKS, or Lambda based on workload characteristics and team operational capability.
- Handle consistency, idempotency, timeouts, retries, sagas, observability, and security between services.

## 2. Monoliths and Reasons for Decomposition

### 2.1. What Is a Monolith?

A monolith is an application built and deployed as a single unit. A monolith can be very well structured internally with clear modules, interfaces, and dependency rules. Therefore, a monolith does not automatically mean messy code or poor design.

For example, an e-commerce application might contain:

- Customer and profile management.
- Product catalog and pricing.
- Shopping cart and orders.
- Payments.
- Inventory.
- Shipping.
- Notifications and customer support.

These capabilities might run inside a single Spring Boot application sharing one relational database. When an order request arrives, the application calls internal modules and writes to multiple tables within a single transaction.

### 2.2. Signs a Monolith Is Becoming a Bottleneck

Do not decompose simply because microservices are popular. Look for evidence of real problems:

- **Cross-locked deployments:** a small change in one module forces the entire application to be built, tested, and released.
- **Inefficient scaling:** high load on search requires scaling out all instances even when payments have low load.
- **Different rates of change:** the payments team needs to release frequently but is constrained by the catalog team's release schedule.
- **Cascading failures:** a heavy reporting job exhausts the connection pool or thread pool, impacting the checkout flow.
- **Unclear ownership:** multiple teams edit the same module or modify the same database tables.
- **Difficulty choosing technology:** one part of the workload needs event-driven processing or independent batch runs but is locked into the monolith's runtime.

These symptoms should be measured by build/deploy duration, release frequency, rollback rate, latency, resource utilization, code conflict frequency, and incident recovery time. If the root cause is module coupling in code, a modular monolith can solve the problem at a lower cost.

### 2.3. When Should You Keep a Monolith?

A monolith is often appropriate when:

- The product is still small and the business domain is not yet stable.
- The development team is small and can coordinate effectively in a single codebase.
- Transactions require atomicity across multiple data sets and there is no need for distribution yet.
- Load does not yet require independent scaling per capability.
- Operational, monitoring, and distributed incident-response capabilities are not yet ready.

You can start with a modular monolith: split code into modules by business domain, restrict data access, use explicit interfaces, and prevent circular dependencies. When a domain has a strong enough business justification for independent deployment, that module already has a cleaner boundary for extraction into a service.

## 3. Choosing an Architectural Model

### 3.1. Modular Monolith

A modular monolith is still deployed as a single application, but its internal structure consists of business modules with clear internal APIs. Each module owns its logic and has its own data access rules. Other modules must not directly access internal tables or classes except through published contracts.

Advantages:

- Simple to deploy and operate.
- Can use in-process transactions.
- Easy to refactor boundaries before having to deal with network failures.
- Lower infrastructure and observability overhead than many services.

The limitation is that modules cannot yet scale or release independently. When modules are well isolated, this can serve as a safe intermediate step before extracting services.

### 3.2. Service-Oriented Architecture and Microservices

Service-oriented architecture (SOA) organizes a system into services with communication contracts. SOA may use larger services integrated through a shared platform.

Microservices typically emphasize smaller services aligned to business domains, owning their data and independent deployment lifecycles, which can be developed by teams with clear ownership. A service does not have to be tiny in lines of code; it needs a cohesive business scope with minimal direct dependencies on other services.

There is no universal standard service size for all systems. Services that are too large are hard to release independently; services that are too small increase network calls, configuration, pipelines, and failure points. Good boundaries reduce the need for frequent cross-team coordination.

### 3.3. Comparing Options

| Criterion | Modular Monolith | Microservices |
|---|---|---|
| Deployment unit | Single application | Multiple independent services |
| Internal communication | In-process calls and module APIs | APIs or messages over the network |
| Data transactions | Easy to use local transactions | Often requires eventual consistency or sagas |
| Scaling | Primarily scales the whole application | Can scale individual services |
| Releases | Single shared release schedule | Can release per service |
| Operations | Fewer distributed components | Must manage networking, retries, observability, and inter-service security |
| Best suited for | Small-to-medium products, evolving domains | Stable business domains, teams, and clear independence needs |

Choose an architecture based on business goals and total operational cost. The number of services is not a direct measure of architectural quality.

## 4. Finding Service Boundaries from the Business Domain

### 4.1. Start from Business Capabilities

A business capability is something the organization needs to do to deliver value, such as catalog management, order processing, payment collection, or shipping. Capabilities are generally more durable than org charts or technical team names.

When analyzing, ask:

- What job is the customer or operations team trying to complete?
- Which business rules change together?
- Which data should have a single primary owning team?
- Which parts have different load, availability, or security requirements?
- Does a change in this domain require frequent coordination with another domain?

The answers help identify cohesive groups of functionality and dependencies that need to be reduced.

### 4.2. Bounded Context in Domain-Driven Design

A bounded context is a boundary within which a domain model and ubiquitous language have consistent meaning. The same word can carry different meanings in different domains.

For example, the term **Customer** in an e-commerce system can have multiple perspectives:

- In the accounts domain, Customer is a login identity, contact information, and verification status.
- In the orders domain, Customer is a buyer linked to shipping addresses and purchase history.
- In the support domain, Customer is a profile for lookups and ticket handling.

These views may reference the same customer ID, but you should not force all domains to share one model and database table. Each bounded context can maintain a model tailored to its own rules.

One bounded context can correspond to one service, though it is not mandatory. Two contexts can be deployed in the same service initially if they share the same owner and operational requirements. Conversely, a large context might need multiple deployable components while still maintaining a single clear data and business boundary.

### 4.3. Using Event Storming and Domain Maps

Event storming is a collaborative technique to map out business events that have occurred, the actions producing them, the actors or systems triggering them, and associated rules. For example:

- Customer registered.
- Product price changed.
- Order placed.
- Payment authorized.
- Inventory reserved.
- Shipment dispatched.

From the sequence of events, the team identifies commands, aggregates, policies, and bounded contexts. Highlight the points where one domain needs information from another, then choose the appropriate communication pattern.

A domain map can record:

- Contexts and primary responsibilities.
- Owning team and business owner.
- Core data managed by the context.
- APIs or events provided.
- Dependent contexts and dependency strength.
- Legacy systems that must be integrated during the transition period.

### 4.4. Principles for Defining Service Boundaries

A well-defined service boundary typically exhibits these traits:

1. **Business cohesion:** internal behaviors serve a single goal or capability.
2. **Owned data:** one service is responsible for writing and maintaining the domain's core data.
3. **Explicit contracts:** other services interact via published APIs or events, never directly reading/writing internal databases.
4. **Relatively independent change:** rules and release schedules rarely force cross-team coordination.
5. **Operable:** the team can deploy, monitor, troubleshoot, and own the service.
6. **Reasonable size:** large enough to avoid excessive chatter, small enough to change without impacting unrelated domains.

If two services always have to be released together, share transactions, and mutate data together, consider merging them or redrawing the boundary.

## 5. E-Commerce Monolith Decomposition Example

### 5.1. Initial State

Suppose a Spring Boot monolith has the following packages and tables:

- customer: customer profiles, addresses.
- catalog: products, categories, prices.
- order: orders and line items.
- payment: payment transactions.
- inventory: stock quantities.
- shipping: shipments and delivery status.

All modules share a single relational database. The Order module can access Inventory and Payment tables directly. When creating an order, the application writes the order, deducts stock, and creates a payment inside one large transaction.

The weakness is not just having one database. The core issue is unclear data boundaries, one module being able to mutate state managed by another module, and teams being unable to deploy independently.

### 5.2. Proposed Bounded Contexts

An initial proposal:

| Bounded Context | Responsibility | Owned Data |
|---|---|---|
| Customer | Customer profile, contacts, and status | Customer profile, contact preferences |
| Catalog | Categories, descriptions, list prices | Product, category, catalog price |
| Order | Order lifecycle, line items, and processing status | Order, order item, order status |
| Payment | Authorization, capture, refunds, and reconciliation | Payment intent, transaction, refund |
| Inventory | Available stock, reservations, and stock adjustments | Stock level, reservation |
| Shipping | Creating shipments, tracking delivery | Shipment, tracking status |

This is an architectural hypothesis. Before splitting, validate how the business actually operates. For instance, if the selling price is locked at checkout time, Order should store a snapshot of the price and required line-item description; it should not rely on Catalog always returning the current price.

### 5.3. Relationships Between Services

When a customer places an order, Order may need to validate cart data, check inventory, and request payment. Illustrative flow:

~~~mermaid
flowchart TD
    C[Web or Mobile] --> G[API Gateway or ALB]
    G --> O[Order Service]
    O --> I[Inventory Service]
    O --> P[Payment Service]
    O --> E[EventBridge or SQS]
    E --> S[Shipping Service]
    E --> N[Notification Service]
    K[Catalog Service] --> O
    U[Customer Service] --> O
~~~

The diagram only shows participating domains; it does not mandate that every request call every service sequentially. Determine which data must be checked synchronously during checkout and which data can be updated asynchronously.

### 5.4. Do Not Split by Technical Layers

A common problematic split is creating separate User Interface Service, Business Logic Service, and Database Service for the entire system. In that setup, every business change still cuts across multiple shared services, and the services still must coordinate to complete a single feature. Technical-layer boundaries may suit certain SOA styles, but they do not create independent business ownership.

Split by capability and bounded context. Each service should have a business purpose that its owning team can explain clearly.

## 6. Migration Strategy: Strangler Fig

### 6.1. Concept

Strangler Fig is an incremental modernization approach. Instead of rewriting the entire monolith at once, the organization extracts a new capability into a separate service, routes matching requests to that service, and gradually shrinks the monolith's responsibilities.

General process:

1. Identify a capability with sufficiently clear boundaries and risks.
2. Create the new service along with its API or event contract.
3. Prepare data and synchronization mechanisms for the transition period.
4. Route a portion of requests to the new service.
5. Compare results, monitor errors, and gradually ramp up traffic.
6. Cut over data write ownership to the new service when ready.
7. Retire the legacy functionality and obsolete integration paths.

This pattern limits the blast radius of each change and allows rollback by switching routing back to the monolith when conditions permit.

### 6.2. Choosing What to Extract First

Choose a capability that:

- Has measurable business value or operational benefits.
- Has minimal transactional dependencies on other modules.
- Has well-defined inputs and outputs.
- Can be observed and tested independently.
- Has an owning team committed after release.

For example, Notification Service is often a strong candidate because sending emails/SMS can be processed asynchronously and rarely shares transactions with Order. A Catalog Read API can also be a candidate if read data can be synced and cached. Conversely, extracting a small slice of the payment workflow that still depends heavily on internal transactions can introduce significant risk.

### 6.3. Request Routing

For HTTP, Amazon API Gateway or Application Load Balancer can serve as the entry point. During migration, the routing layer can direct certain paths or request groups to the new service while the rest still go to the monolith.

Example:

| Request | Target During Transition |
|---|---|
| GET /catalog/* | Catalog Service |
| POST /orders | Monolith or Order Service by phase |
| GET /orders/* | Can read from monolith during synchronization |
| POST /legacy-checkout | Monolith until the new flow is verified |

Do not just change routing while ignoring sessions, authentication, rate limits, request IDs, timeouts, and error formats. Keep external contracts stable if clients cannot change simultaneously.

### 6.4. Rollback Plan

Before each traffic ramp-up, define:

- Which metrics allow proceeding, such as error rate, latency, and processing success rate.
- Rollout stop conditions.
- How to switch routing back to the previous version.
- How to handle requests that already wrote data to the new service.
- How to keep data consistent during rollback.

Rolling back code does not automatically revert data. If the new service has already written state diverging from the monolith, design a separate reconciliation or compensation process.

## 7. Data Ownership and Consistency

### 7.1. One Service Owns Writes for Domain Data

In microservices, database-per-service is a principle of logical ownership: each service is responsible for mutating its own domain data. This does not necessarily require each service to have a separate database server from day one. You can share a managed cluster while separating databases/schemas, credentials, and access permissions; what matters is that other services do not directly access internal tables.

Examples:

- Order Service owns order status.
- Payment Service owns payment status.
- Inventory Service owns stock levels and reservations.

Order can store a `paymentId` or payment status received via events. It must not directly update Payment's transaction tables.

### 7.2. Do Not Use a Shared Database as an Implicit API

If multiple services write to the same schema, changing a column or constraint in one service can break another service without any change to the API contract. This is a form of hidden coupling.

When migrating incrementally:

1. Identify which service is the final owner of each table or dataset.
2. Prevent new code from directly accessing tables owned by other domains.
3. Provide APIs or events for consumers to receive information.
4. Migrate write ownership first, then migrate read consumers according to plan.
5. Remove legacy permissions and access code once no dependencies remain.

During transition, read replicas or compatibility tables may exist. Clearly mark them as temporary data, who updates them, and when they will be retired.

### 7.3. Avoiding Dual-Write

A dual-write happens when a request writes the same change to two independent systems, such as writing to a database and then sending a message. If the database commit succeeds but sending the message fails, the two systems diverge. If sending the message succeeds but the transaction rolls back, consumers receive an event with no corresponding record.

Transactional outbox is a common way to address this:

1. The service writes the business change and an outbox record in the same database transaction.
2. A publisher reads unpublished outbox records.
3. The publisher sends events to the broker.
4. After delivery confirmation, the publisher marks records as processed.
5. Consumers process events idempotently.

Example table structure:

~~~sql
CREATE TABLE outbox_event (
    event_id       VARCHAR(80) PRIMARY KEY,
    aggregate_id   VARCHAR(80) NOT NULL,
    event_type     VARCHAR(120) NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL
);
~~~

Order Service can write the Order and the `OrderPlaced` outbox event in the same transaction. The publisher can run inside the application, as a separate ECS worker, or via Lambda triggered by an appropriate polling/stream mechanism. Retries, record locking, and concurrent publisher handling must be designed carefully.

### 7.4. Eventual Consistency

When services own separate data, updates across domains may not occur in a single transaction. An event is emitted and consumers update their state afterward. For a brief window, other screens or services may see stale state.

The design must clarify:

- Which state is considered the source of truth?
- How will users see in-progress states?
- How much delay is acceptable?
- What does a consumer do upon receiving duplicate or out-of-order events?
- Is there a reconciliation process when events are lost or fail processing?

Not every business operation tolerates eventual consistency. If a condition must be verified immediately at transaction time, use a synchronous API with an explicit timeout or keep that business logic inside the same boundary until a suitable solution exists.

## 8. Choosing Inter-Service Communication

### 8.1. Synchronous Communication via APIs

HTTP/REST or gRPC is appropriate when the caller needs an immediate result to continue processing. On AWS, entry points can be:

- Amazon API Gateway for public APIs, authentication management, quotas, throttling, and backend integration.
- Application Load Balancer for HTTP/HTTPS routing to services running on ECS, EKS, or EC2.
- Internal load balancers or service discovery for internal communication within a private network.

The advantage of synchronous APIs is straightforward execution flow and immediate responses to the caller. The drawback is that the caller depends on the availability and latency of the callee. Long synchronous call chains increase total latency and expand failure blast radius.

Design rules:

- Set timeouts smaller than the overall request deadline.
- Never retry infinitely; use backoff with jitter and bounded retry counts.
- Only retry operations that are safe to repeat or carry an idempotency key.
- Return structured errors without leaking stack traces or sensitive data.
- Limit payload sizes and protect against oversized requests.
- Propagate correlation IDs or trace context across the entire call chain.

### 8.2. Asynchronous Communication via Messages and Events

Asynchronous communication fits when the producer does not need to wait for the consumer to finish immediately, or when you want to decouple load and processing timing.

| AWS Service | Model | When to Use |
|---|---|---|
| Amazon SQS | Message queue; consumers pull and process | Work needing load buffering, retries, rate control, and producer/consumer decoupling |
| Amazon SNS | Pub/sub fan-out to multiple subscribers | Broadcasting a notification to multiple targets such as SQS, Lambda, or HTTPS |
| Amazon EventBridge | Event bus with filtering rules and event routing | Connecting producers/consumers by business events or AWS events |
| AWS Step Functions | Stateful workflow orchestration | Multi-step workflows, branching, retries, timeouts, and compensation handling |

For example, when an Order is created, Order Service emits an `OrderPlaced` event. EventBridge can route the event to queues for Inventory, Shipping, and Notification. Each consumer processes independently and can scale based on queue depth.

SQS retains messages until a consumer processes and deletes them. SNS fans out notifications to multiple subscribers. EventBridge routes events based on rules and integrates with many AWS services. Choose the service based on communication pattern, filtering requirements, durability, ordering, and replay capability—not just by name.

### 8.3. Choosing Queue Types and Handling Failed Messages

Amazon SQS Standard offers high scalability and throughput, but can deliver a message more than once and does not guarantee strict ordering. Consumers must be idempotent.

SQS FIFO supports ordering by message group and deduplication within service mechanics. It is useful when business ordering matters, though message groups must be designed so a single group does not become a bottleneck.

For both queue types:

- Set visibility timeout long enough for expected processing duration.
- Use a dead-letter queue (DLQ) to isolate messages exceeding max receive count.
- Monitor the age of the oldest message and approximate messages waiting.
- Have a process to investigate, fix data, and replay messages from the DLQ.
- Never automatically purge a DLQ before identifying the root cause.

### 8.4. Designing Event Contracts

Events need a stable schema, unique identifier, and sufficient information for consumers to understand the business meaning:

~~~json
{
  "eventId": "evt-01JEXAMPLE",
  "eventType": "OrderPlaced",
  "eventVersion": 1,
  "occurredAt": "2026-11-20T05:00:00Z",
  "producer": "order-service",
  "correlationId": "req-7f31",
  "data": {
    "orderId": "ord-1042",
    "customerId": "cus-208",
    "currency": "VND",
    "totalAmount": 1250000
  }
}
~~~

This is an illustrative payload. Actual contracts must specify data types, required fields, currency units, versioning rules, sensitive data handling, and backward-compatibility policies. Avoid putting payment details or unnecessary personal data into events.

Consumers should ignore or handle new fields gracefully when schemas evolve in a compatible way. When a change breaks the contract, publish a new version or create a new event type according to an agreed strategy.

## 9. Orchestrating Distributed Business Workflows

### 9.1. Why Are Distributed Transactions Hard?

In a monolith, a single database transaction can write Order, Payment, and Inventory together. When these parts are split into services with separate databases, you cannot assume a single ACID transaction spans all databases and message brokers.

Instead of trying to build a long-lived distributed transaction, systems typically use multi-step workflows with explicit states, retries, and compensating actions.

### 9.2. Saga Pattern

A saga models a long-running business transaction as a sequence of local transactions. Each step commits in the database of its owning service. If a step fails, the workflow runs compensating actions to bring the system back to an acceptable business state.

Example checkout workflow:

1. Order Service creates the order in `PENDING` state.
2. Inventory Service reserves stock and emits `InventoryReserved`.
3. Payment Service requests payment.
4. If payment succeeds, Order transitions to `CONFIRMED` and emits an event for Shipping.
5. If payment fails, Order asks Inventory to release the reservation and transitions to `CANCELLED`.

Compensating actions do not always cleanly undo the previous action. A captured payment may require a refund; a dispatched parcel may require a return process. Intermediate states and failure handling when compensation itself fails must be defined.

### 9.3. Choreography and Orchestration

**Choreography** uses events so each service reacts independently. This reduces centralized coordination, but business flows can become hard to trace when there are many events and branches.

**Orchestration** uses an orchestrator to manage workflow state and instruct each service to perform the next step. AWS Step Functions fits workflows with state, timeouts, retries, branching, and integrations with Lambda or AWS services.

| Criterion | Choreography | Orchestration |
|---|---|---|
| Coordination | Services react to events | One workflow orchestrates steps |
| Coupling | Producers and consumers know little about each other | Workflow knows steps and service contracts |
| Flow tracking | Must stitch events and correlation IDs | Centralized execution history |
| Best suited for | Simple event flows, few steps | Multi-step workflows, branching, and compensations |

Do not use Step Functions for every single call between two services. Use it when state management and orchestration logic genuinely add value.

## 10. Choosing a Service Deployment Platform on AWS

### 10.1. Amazon ECS

Amazon ECS suits containerized services that run continuously or as tasks. ECS can run on AWS Fargate so AWS manages the underlying server infrastructure, or on EC2 when deeper control over instances, capacity, and configuration is needed.

ECS is often a good choice when an organization wants to run containers without needing the entire Kubernetes ecosystem. You can use Application Load Balancer to route HTTP to services, CloudWatch for logs/metrics, and IAM task roles to grant permissions to applications.

### 10.2. Amazon EKS

Amazon EKS suits organizations already standardized on Kubernetes, requiring Kubernetes APIs and ecosystem tools, or having complex workload scheduling requirements. EKS provides a managed Kubernetes control plane; the team remains responsible for cluster configuration, nodes, networking, add-ons, security, and upgrades according to the usage model.

Do not choose EKS just because the system has many microservices. Kubernetes adds significant concepts and operational work. If ECS meets requirements, ECS can reduce complexity.

### 10.3. AWS Lambda

AWS Lambda suits event-driven processing, short-lived tasks, or intermittent workloads. Examples: processing `OrderPlaced` events, generating thumbnails, sending notifications, or handling webhooks.

Lambda can be triggered from SQS, EventBridge, API Gateway, and many other sources. When using Lambda, pay attention to execution duration limits, concurrency, cold starts, payload size, retries, and duplicate message handling.

### 10.4. Choosing by Workload

| Characteristic | ECS/Fargate | EKS | Lambda |
|---|---|---|---|
| Long-running | Suitable | Suitable | Not the default model |
| Short, bursty events | Can use tasks/workers | Can use workloads | Very suitable |
| Runtime control | High | Very high | Limited to supported runtimes |
| Platform overhead | Low to moderate | Moderate to high | Low at the server layer |
| Best when | Containers with simpler operations needed | Existing Kubernetes capability | Event-driven, short execution duration |

A single system can combine models. For instance, the Order API runs on ECS, SQS consumers run on Lambda, and compensation workflows are orchestrated by Step Functions.

## 11. Data, Security, and Operations Across Services

### 11.1. Choosing Data Stores by Domain

Not every service must use the same database engine. Choose based on access patterns and data characteristics:

- Amazon RDS or Aurora when relational modeling, SQL, and transactions within a domain are needed.
- Amazon DynamoDB when low-latency key-value/document access with clear access patterns is needed.
- Amazon ElastiCache when caching frequently accessed data.
- Amazon S3 for objects, documents, and unstructured data.

Polyglot persistence lets each domain use fitting technology, but increases the number of platforms requiring security, backups, observability, and operational skills. Prefer the smallest number of database types that satisfy requirements.

### 11.2. Service Identity Security

Each service needs its own identity and permissions:

- Use IAM task roles for ECS tasks, IAM roles for EKS workloads via the appropriate mechanism, and execution/function roles for Lambda.
- Grant permissions following least privilege, restricting resources and actions.
- Use AWS Secrets Manager or AWS Systems Manager Parameter Store to manage secrets and sensitive configuration.
- Use TLS for network communication and encryption at rest as required.
- Keep internal services in private subnets where appropriate; expose only necessary entry points.
- Use security groups to restrict connection sources and destinations.

Never share a static access key across multiple services. Credentials should be issued automatically via roles and rotated through service-managed mechanisms.

### 11.3. API Authentication and Authorization

API Gateway can integrate with Amazon Cognito, Lambda authorizers, or other appropriate authentication mechanisms. For service-to-service communication, authenticate caller identity, authorize by action, and restrict network access.

Authentication establishes who the caller is; authorization determines what the caller is allowed to do. A service may be permitted to invoke an endpoint while still barred from accessing arbitrary orders or customers. Enforce business-level authorization when data belongs to multiple tenants or users.

### 11.4. Distributed Observability

When a request traverses multiple services, a single log line is not enough to explain a full failure. Standardize:

- Structured logs with timestamp, service name, environment, request ID, and correlation ID.
- Metrics for request rate, error rate, latency percentiles, queue depth, and saturation.
- Distributed tracing to follow requests across APIs and services.
- Alarms aligned with SLOs and user impact.
- Dashboards displaying dependencies and component health.

Amazon CloudWatch provides logs, metrics, dashboards, and alarms. AWS X-Ray supports tracing for integrated components; OpenTelemetry can also be used to collect traces and metrics using open standards. For asynchronous events, propagate the correlation ID inside messages to link producers and consumers.

### 11.5. Reliability and Fault Tolerance

Every service should assume dependencies can be slow or unavailable:

- Use timeouts on all network calls.
- Perform bounded retries with exponential backoff and jitter.
- Use circuit breakers or load shedding to avoid cascading failures onto dependencies.
- Design idempotency for commands that can be resent.
- Use queues to absorb bursts and decouple producers from consumers.
- Route failed messages to DLQs and have a redrive process.
- Limit concurrency to protect databases and downstream services.

Do not retry a non-idempotent operation merely because a timeout occurred. A timeout can happen after the server committed the change while the response never reached the caller. Use idempotency keys or check state before retrying.

## 12. Steps to Execute a Decomposition Program

### Phase 1: Understand Current State

1. Diagram modules, databases, APIs, and data flows.
2. Gather metrics on deployments, latency, errors, load, and code conflicts.
3. Identify direct dependencies between modules.
4. Interview business teams to understand capabilities and change rules.
5. Select a concrete problem the decomposition program must solve.

### Phase 2: Design Boundaries

1. Create a domain map and bounded contexts.
2. Identify core data and the service that owns it.
3. Define API/event contracts.
4. Determine which interactions require synchronous calls and which can be eventually consistent.
5. Choose the runtime and database suited to the workload.
6. Evaluate security, observability, cost, and on-call operability.

### Phase 3: Extract One Capability

1. Create the new service and an independent build/deploy pipeline.
2. Provision IAM roles, networking, secrets, logs, metrics, and alarms.
3. Build API or event contracts and run compatibility tests.
4. Migrate data according to plan, establishing a single write source.
5. Route a portion of requests or events to the new service.
6. Measure outcomes, monitor errors, and preserve rollback capability.

### Phase 4: Expand and Retire Legacy Code

1. Increase traffic in waves as metrics stabilize.
2. Cut over data ownership and update consumers.
3. Reconcile duplicate, missing, or inconsistent data.
4. Remove legacy read/write paths after confirming zero remaining consumers.
5. Update runbooks, architecture diagrams, and operational ownership.
6. Re-evaluate boundaries before extracting the next capability.

## 13. Common Design Mistakes

| Mistake | Consequence | Mitigation |
|---|---|---|
| Splitting services by tables or technical layers | Multiple services still have to coordinate for one business task | Start from capabilities and bounded contexts |
| Splitting too finely | Increases network hops, pipelines, and on-call burden | Combine parts that change together and share the same owner |
| Multiple services writing to one database | Schema becomes an implicit contract and causes cascading breakages | Define data owners and use APIs/events |
| Synchronous calls chained across too many services | Latency and failure scope multiply along the chain | Use events/queues for work not needing immediate responses |
| Infinite retries | Creates retry storms and overloads dependencies | Timeouts, backoff, jitter, bounded retries, and DLQs |
| Dual-write to database and message broker | Data and events can drift out of sync | Transactional outbox and idempotent consumers |
| Assuming events arrive exactly once | Duplicate processing creates duplicate orders or charges | Idempotency keys and tracking processed event IDs |
| No cross-service tracing | Hard to pinpoint error sources in distributed flows | Correlation IDs, distributed tracing, and structured logs |
| Migrating data without verification | Monolith and new service can return different results | Reconciliation, shadow reads, and controlled write cutover |
| Extracting a service with no owner | Nobody owns SLOs or incidents | Assign the service to an owning team and runbook |

## 14. Service Boundary Evaluation Checklist

Before deciding to extract a module into a service, answer:

1. What is the service's business capability?
2. Are the bounded context and business language clear?
3. Which data does the service own, and does it have exclusive write ownership?
4. Through which contracts do other services interact with it?
5. Which interactions must be synchronous, and which can be asynchronous?
6. Are error handling, retries, idempotency, and reconciliation clearly defined?
7. Can the service be built, deployed, scaled, and rolled back independently?
8. Are proper IAM roles, secrets, network policies, and encryption in place?
9. Are logs, metrics, traces, alarms, dashboards, and runbooks ready?
10. Do business benefits outweigh the distributed complexity and operational cost?

If many questions remain unanswered, continue clarifying module boundaries inside the monolith before splitting processes.

## 15. Conclusion

Monolith decomposition is the process of finding and establishing business boundaries that can be owned, changed, and operated independently. Business capabilities and bounded contexts determine where to draw boundaries; data ownership prevents hidden coupling; and API and event contracts create controlled communication.

On AWS, services can be deployed with ECS, EKS, or Lambda, routed via API Gateway or load balancers, integrated asynchronously with SQS, SNS, and EventBridge, and orchestrated with Step Functions, while CloudWatch and tracing observe the entire system. Service choices must be grounded in workload characteristics, team skills, and operational cost.

Migrating with Strangler Fig enables incremental change and risk control. Every step requires a data plan, routing plan, rollback plan, and verification criteria. By combining clear business boundaries, data ownership, distributed error handling, and accountable operations, an organization can evolve its system as needed without turning monolith decomposition into an unmanageable web of dependencies.
