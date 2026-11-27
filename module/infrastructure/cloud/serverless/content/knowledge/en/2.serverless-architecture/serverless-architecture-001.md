# Decomposing Business Logic into Functions and Services with Clear Boundaries

In the **Serverless Architecture Design** chapter, the critical decision is not how many functions to create, but how to partition the system by business responsibilities and where to place data boundaries. A FaaS function is an execution unit invoked by HTTP, a message, or an event. A service is the unit that owns a business capability, its rules, and its associated data. A service can contain multiple functions; therefore, each function should not be treated as an independent microservice.

This lesson belongs to the **CLOUD_SERVERLESS** module and focuses on developing and deploying serverless applications, particularly Java functions triggered by HTTP, messages, or events. Decomposition decisions must account for state, access permissions, retries, idempotency, cold start, scalability, and operational cost. The goal is to establish boundaries clear enough for each part to be developed and operated independently without fragmenting business workflows.

## 1. Distinguishing Business Capabilities, Services, and Functions

Before partitioning the system, align on three concepts:

| Concept | Question Answered | Example |
|---|---|---|
| Business capability | What does the system need to do for the organization or users? | Order management, inventory management, payment processing |
| Service / bounded context | Which part of the business owns its own rules, data, and contracts? | Order Service owns the order lifecycle |
| Function | Which processing step is triggered by a specific trigger? | Function handling HTTP order creation, function handling new-order events |

A function typically performs a single processing step with well-defined inputs and outputs. It can be deployed independently, scaled by invocation count, and granted permissions as needed. A service groups functions that share the same business context, data ownership, and set of rules.

For example, Order Service might include:

- A function receiving HTTP requests to create an order.
- A function receiving HTTP requests to query order status.
- A function processing payment-succeeded events.
- A function processing order-cancellation requests from a queue.

These functions have different triggers and operational characteristics, yet they all operate on the order lifecycle. They still belong to one business boundary because they share responsibility for order state and rules.

Conversely, a function should not be split into a separate service merely because it has its own endpoint or its own Java class. Service boundaries must stem from business responsibility, data ownership, and the required degree of independence.

## 2. Principles for Defining Boundaries

### 2.1. Partition by Business Capability, Not by Technical Layer

A common but coupling-prone approach is creating services such as UserController, OrderRepository, or PaymentDatabase. This is partitioning by technical layer. When a business workflow must traverse multiple layers across multiple services, even a small change can force multiple teams to modify and deploy together.

Start with the question: “Which business capability needs to be managed independently?”. For example:

- Order is responsible for accepting orders, managing status, and enforcing order lifecycle rules.
- Inventory is responsible for sellable quantities, stock reservations, and inventory releases.
- Payment is responsible for payment requests, transaction results, and reconciliation.
- Notification is responsible for delivering information via email, SMS, or other notification channels.

A service name should express a business responsibility. If the name only describes a technology or a database table, reconsider the boundary.

### 2.2. Data and Rules Must Have an Owner

Each service should be the authoritative place for changing its own business data. Other services access that data through APIs or consume published events, rather than writing directly to that service's tables.

For example, Inventory owns stock quantities and reservation rules. Order does not decrement quantities in the inventory database itself. Order sends a reservation request or emits an OrderPlaced event; Inventory decides whether stock can be reserved and responds with the result.

Data ownership helps answer clearly:

- Which service is allowed to create, modify, or transition the state of the data?
- Which rules must be protected within the same transaction?
- What information do other services need to continue the workflow?
- If the data changes, which service is responsible for publishing the update?

“Database per service” is a principle about logical ownership. In small systems, multiple services may share a single physical database cluster, but they still need separate schemas, write permissions, and access contracts. Sharing a server does not mean other services may access internal tables directly.

### 2.3. Keep Business Invariants Within the Same Boundary

An invariant is a condition that must always hold true for business data. For example:

- The sum of the line items must match the order total according to the pricing policy.
- An order cannot have payment confirmed twice.
- Sellable inventory quantity cannot be negative.
- A payment transaction must not transition from refunded back to paid.

If two operations must always succeed together or fail together to preserve an invariant, they should generally reside in the same service and the same transaction boundary. Moving them into two different services turns a local transaction into a distributed workflow, requiring compensation mechanisms and intermediate state handling.

Not every step of a workflow needs to be in the same service. Only rules requiring immediate consistency need to share a boundary. Steps that can complete later, such as sending a confirmation email, are suited to asynchronous processing.

### 2.4. Reduce Synchronous Dependencies Between Services

A function synchronously calling multiple other services can form a dependency chain:

**HTTP → Order → Inventory → Pricing → Customer → Payment**

If one service is slow or fails, the entire request can slow down or fail. Long call chains also increase latency, data transfer costs, and retry complexity.

Call synchronously only when the caller genuinely needs an immediate result to answer the current request. If the next step can be processed later, consider sending a message or publishing an event. Asynchronous communication reduces runtime coupling, at the trade-off of accepting intermediate states and eventual consistency.

### 2.5. Keep Functions Independent of State from Previous Invocations

FaaS platforms can run multiple instances concurrently, reuse execution environments, or spin up new ones. One invocation must not depend on in-memory variables from a previous invocation. Data that must persist across invocations must be stored in a database, object storage, cache, or an appropriate state-management system.

Connection clients or immutable configuration may be reused across an instance's lifecycle to reduce initialization overhead. However, global variables or instance memory must never be treated as reliable storage for business state.

## 3. Workflow for Decomposing from Business Logic to Functions

The following process can be applied to a new system or when migrating an existing application to serverless.

### Step 1: Describe the End-to-End Business Flow

Start with a journey that is meaningful to the user or organization, rather than starting from a list of endpoints or database tables.

Example purchase flow:

1. The user submits an order request.
2. The system validates the information and records the order.
3. The system reserves the item quantities.
4. The system requests payment.
5. The system confirms or rejects the order.
6. The system sends a notification to the user.

For each step, record the actor, input data, expected outcome, possible errors, and which steps require an immediate result.

### Step 2: Group Activities by Business Capability

Group activities that share the same business language and are responsible for the same set of rules. In the example above, order management, inventory reservation, payment processing, and notification delivery are distinct capabilities.

A well-formed group usually shows these signs:

- A clear business objective.
- Data and rules for which the group is accountable.
- Definable contracts with other groups.
- Practical reasons to change, deploy, or scale independently.

If two groups constantly have to change together, share the same invariants, or call each other synchronously in almost every operation, the boundaries may be split too finely.

### Step 3: Identify Owned Data and Transaction Boundaries

List the key entities, states, and rules of each capability. Mark which service owns each piece of data. Then determine which operations must be executed atomically.

Example:

| Data / Rule | Owning Service | Reason |
|---|---|---|
| Order ID, line items, order status | Order | Manage order lifecycle |
| Available quantity, stock reservations | Inventory | Protect inventory rules |
| Transaction ID, payment status | Payment | Track transaction results |
| Email delivery status, notification history | Notification | Manage information delivery |

A service may store a snapshot of data needed for its own business logic. For instance, Order stores the product name and price at the time of ordering so the invoice does not change when product catalog details are updated. This snapshot does not make Order the owner of product catalog data.

### Step 4: Choose Synchronous or Asynchronous Communication

Classify each interaction:

- **Synchronous** when an immediate answer is needed, such as checking access permissions or returning query results.
- **Asynchronous** when processing can happen later, when the lifetimes of sender and receiver need to be decoupled, or when multiple parties care about an event.
- **Hybrid** when the request needs immediate acknowledgment of receipt while a long-running workflow proceeds in the background.

Do not turn every call into an event. If the user needs to know immediately whether input data is valid, a synchronous call with a clear timeout and error handling may be more appropriate. Conversely, do not hold an HTTP connection open while waiting on a lengthy workflow if you can return a tracking ID and process it in the background.

### Step 5: Set Service Boundaries First, Then Choose Functions

Once business groups and data ownership are established, identify the entry points of each service. Each entry point can become a separate function if it requires a different trigger, access permissions, scaling profile, or deployment lifecycle.

For example, Order Service could have:

| Function | Trigger | Responsibility |
|---|---|---|
| PlaceOrderFunction | HTTP POST | Validate request and initialize order |
| GetOrderFunction | HTTP GET | Return order details according to access permissions |
| PaymentResultFunction | Event | Update order based on payment result |
| CancelOrderFunction | Message | Process an accepted order-cancellation request |

There is no need to create a function for every statement or every internal method. A single function can invoke multiple classes within the same service to fulfill a use case. Splitting should deliver concrete benefits in triggers, permissions, scaling, fault isolation, or deployment.

### Step 6: Define Contracts Between Boundaries

For APIs, define paths, methods, schemas, error codes, timeouts, and authentication mechanisms. For messages or events, define names, schema versions, identifiers, emission timing, and business semantics.

Distinguish clearly:

- **Command**: requests a service to perform an action, e.g., ReserveStock.
- **Event**: announces that something has happened, e.g., OrderPlaced.

A command typically has one responsible handler. An event can have multiple independent subscribers. Event names should describe what occurred and typically use the past tense; do not use an event to disguise a command call where the sender expects an immediate result.

### Step 7: Design Failures and States Before Deployment

For each function, specify what happens on timeout, duplicate processing, invalid data, dependency failure, or retry exhaustion. For multi-service workflows, define intermediate states, completion conditions, and compensating actions.

A design that only describes the happy path is not ready for production deployment. In serverless environments, messages can be redelivered, events can arrive late, and functions can execute concurrently.

## 4. Example: Decomposing an Order Placement Workflow

Suppose an e-commerce application needs to accept orders, reserve inventory, process payments, and send notifications. It can be partitioned into four services:

~~~mermaid
flowchart TD
    U[Buyer] --> H[HTTP Function<br/>Order Service]
    H --> O[(Order Data)]
    H -->|OrderPlaced| Q[Event Bus]
    Q --> I[Inventory Function]
    I --> ID[(Inventory Data)]
    I -->|StockReserved / StockRejected| Q
    Q --> P[Payment Function]
    P --> PD[(Payment Data)]
    P -->|PaymentSucceeded / PaymentFailed| Q
    Q --> R[Order Result Function]
    R --> O
    Q --> N[Notification Function]
    N --> E[Email / SMS Provider]
~~~

The boundaries carry the following meaning:

- **Order Service** owns the order and statuses such as PENDING, CONFIRMED, REJECTED, or CANCELLED.
- **Inventory Service** owns stock quantities and inventory reservations.
- **Payment Service** owns transactions, payment results, and reconciliation data.
- **Notification Service** owns notification delivery status and integration with email or SMS providers.

A flow can proceed as follows:

1. HTTP Function receives the order request, validates input, and invokes the place-order use case. Order Service persists the order in PENDING status.
2. After saving the order successfully, Order Service publishes the OrderPlaced event.
3. Inventory Function receives the event, checks stock, and reserves items. It publishes StockReserved or StockRejected.
4. Once stock is reserved, Payment Function processes the payment and publishes PaymentSucceeded or PaymentFailed.
5. Order Result Function receives the outcome and updates the order status. If payment succeeds, the order transitions to CONFIRMED; if it fails, the order can transition to a status requiring cancellation or further handling.
6. Notification Function receives the relevant events and sends notifications. A failure to send email should not discard the payment result or revert the order status.

The diagram is an example of event-driven coordination. The actual sequence must be defined explicitly: for example, Payment must only run after StockReserved, whereas on StockRejected no payment may be requested. If the workflow involves complex branching, timeouts, and compensating actions, a Saga Orchestrator can manage workflow state. If steps are relatively independent and events clearly express outcomes, choreography can be simpler.

### 4.1. Choosing Orchestration vs. Choreography

| Coordination Style | Characteristics | Suitable When |
|---|---|---|
| Orchestration | A coordinator knows the next step, tracks state, and decides actions | Long workflows with complex branching, timeouts, and compensation steps |
| Choreography | Services react to events published by other services | Steps have low coupling, event contracts are clear, and multiple independent subscribers exist |

Choreography reduces reliance on a central coordinator, but when there are too many events and subscribers, the overall flow becomes hard to observe. Orchestration makes progress explicit, though the coordinator can become a concentration of logic. Choose based on workflow complexity, not technology trends.

### 4.2. Why Not Put Every Step into One Function?

A large function that places the order, reserves inventory, processes payment, and sends email seems simple at first. However, if the function times out after payment succeeds, the system needs to know which steps completed in order to retry safely. The function would also require access to data and services across multiple business domains while scaling with the load of the entire workflow.

Splitting by service allows Inventory to scale with reservation traffic, Payment with transaction traffic, and Notification with notification volume. Each service only needs permissions appropriate for its own data. In exchange, the engineering team must handle distributed state, event contracts, and eventual consistency.

### 4.3. Why Not Create a Function for Every Small Operation?

If every internal operation—such as calculating tax, normalizing an address, or validating a field—were a separate function, a simple request might traverse multiple network calls. This increases latency, billing invocations, failure points, and observability overhead.

Purely computational steps that share the same lifecycle and do not need independent scaling or permissions should generally remain methods or components within the same function/service. Only split into a separate function when there is a concrete operational or architectural reason.

## 5. Mapping Triggers to Functions

The trigger determines how a function receives input, how it responds, and how errors are handled. The following table helps select the appropriate trigger type:

| Trigger | When to Use | What Must Be Designed |
|---|---|---|
| HTTP | Users or external systems need to call an API and typically expect an immediate response | Authentication, input validation, timeouts, HTTP status codes, rate limiting |
| Queue / message | Work can be processed in the background and needs load buffering or retries | Acknowledgement, visibility timeout, retries, dead-letter queue, idempotency |
| Event bus | A business event may be of interest to multiple services | Schema/versioning, subscriber filtering, event IDs, ordering, and duplicate delivery handling |
| Scheduler | Periodic jobs such as reconciliation or aggregation | Time zones, overlapping runs, job locking, processing windows |
| Storage event | Reacting when a file or object is created/updated | File size, object identifiers, duplicate events, and ordering |

Do not choose a trigger simply because the platform supports it. Start from business needs: who initiates the work, whether an immediate result is required, whether the work can wait, and who is responsible for retrying on failure.

## 6. Structuring Java Functions Around Use Cases

Business processing should reside in a use case or domain service. The function acts as an adapter: translating trigger payloads into internal commands, invoking business logic, and converting results into appropriate responses.

The illustrative example below uses custom-defined HTTP types to focus on architectural boundaries; an actual adapter maps to the request/response types of the FaaS platform in use.

~~~java
public record PlaceOrderCommand(
        String customerId,
        List<OrderLine> lines,
        String idempotencyKey) {
}

public record OrderLine(String productId, int quantity) {
}

public record PlaceOrderResult(String orderId, String status) {
}

public interface PlaceOrderUseCase {
    PlaceOrderResult execute(PlaceOrderCommand command);
}

public record HttpRequest(
        String customerId,
        List<OrderLine> lines,
        String idempotencyKey) {
}

public record HttpResponse(int statusCode, String body) {
}

public final class PlaceOrderHttpFunction {
    private final PlaceOrderUseCase placeOrder;

    public PlaceOrderHttpFunction(PlaceOrderUseCase placeOrder) {
        this.placeOrder = placeOrder;
    }

    public HttpResponse handle(HttpRequest request) {
        if (request.customerId() == null || request.customerId().isBlank()) {
            return new HttpResponse(400, "customerId is required");
        }

        if (request.lines() == null || request.lines().isEmpty()) {
            return new HttpResponse(400, "order lines are required");
        }

        PlaceOrderCommand command = new PlaceOrderCommand(
                request.customerId(),
                request.lines(),
                request.idempotencyKey());

        PlaceOrderResult result = placeOrder.execute(command);

        return new HttpResponse(
                202,
                "{\"orderId\":\"" + result.orderId()
                        + "\",\"status\":\"" + result.status() + "\"}");
    }
}
~~~

The example shows that the function only handles the HTTP protocol and forwards the request to the use case. Rules such as pricing, quantity limits, order status, and data persistence must live in the business layer. In a real application, use a JSON serializer instead of manual JSON string concatenation, and authenticate the caller and check authorization before executing the use case.

A message-triggered function has a similar structure:

~~~java
public record OrderPlacedEvent(
        String eventId,
        String orderId,
        List<OrderLine> lines) {
}

public interface ReserveInventoryUseCase {
    void reserve(OrderPlacedEvent event);
}

public final class ReserveInventoryMessageFunction {
    private final ReserveInventoryUseCase reserveInventory;

    public ReserveInventoryMessageFunction(
            ReserveInventoryUseCase reserveInventory) {
        this.reserveInventory = reserveInventory;
    }

    public void handle(OrderPlacedEvent event) {
        reserveInventory.reserve(event);
    }
}
~~~

The message adapter does not need to know how Inventory calculates available quantities. The use case is responsible for checking whether the event has already been processed, applying reservation rules, persisting the result, and ensuring safe duplicate handling. The platform adapter only acknowledges the message after business logic has been processed and data has been committed according to the platform's mechanism.

## 7. Designing State, Retries, and Idempotency

In serverless environments, retries are a normal part of operations. The platform may redeliver a message when a function times out or fails to acknowledge success. An event may also be re-emitted due to publisher retries. Therefore, never assume a function executes only once per business operation.

### 7.1. Idempotency

An idempotent operation can be executed multiple times with the same identifier without causing additional business side effects. For example, receiving the OrderPlaced event again must not create an extra stock reservation.

Common implementation approaches:

- Give every request or event a stable idempotency key.
- Persist processed keys along with their results in a database.
- Place a unique constraint on the key to prevent two instances from processing the same request concurrently.
- Record processing state in the same transaction as the business change whenever possible.
- If the operation calls an external system, pass the idempotency key to the provider if their API supports it.

Do not check the key solely in function memory because two instances can run in parallel or a new instance may be created later.

### 7.2. Retries and Dead-Letter Queues

Retries are appropriate for transient errors such as network timeouts, rate limits, or temporarily unavailable dependencies. Configure a maximum retry count, exponential backoff, and jitter to prevent many functions from retrying simultaneously.

Do not retry invalid data or unrecoverable business errors indefinitely. After the allowed number of attempts, the message can be routed to a dead-letter queue for inspection and controlled replay.

Distinguish clearly between:

- **Transient errors**: can be retried later.
- **Permanent errors**: require fixing data or rules before reprocessing.
- **Unknown outcome**: the function timed out after sending a request to an external system; query by transaction ID or idempotency key before retrying.

### 7.3. Distributed Workflow State

When a workflow spans multiple services, no single database transaction covers all steps. Model states explicitly, for example:

**PENDING → STOCK_RESERVED → PAYMENT_PENDING → CONFIRMED**

Failure branches might include:

**STOCK_REJECTED**, **PAYMENT_FAILED**, **CANCEL_PENDING**, **CANCELLED**, **REFUND_PENDING**.

State names should reflect confirmed facts. For example, after sending a payment request without yet receiving a response, do not record the status as PAID. Use PAYMENT_PENDING to indicate work is still in progress.

### 7.4. Transactional Outbox

A common failure occurs when a service commits data successfully but fails to publish the event, or publishes the event successfully while the data transaction rolls back. These two operations are not automatically atomic with each other.

The transactional outbox pattern solves this by writing the business change and the event record within the same transaction:

~~~sql
BEGIN;

INSERT INTO orders (order_id, status)
VALUES ('ORD-1001', 'PENDING');

INSERT INTO outbox (event_id, event_type, payload)
VALUES ('EVT-9001', 'OrderPlaced', '{...}');

COMMIT;
~~~

A separate publisher reads the outbox and sends events to the message broker. The publisher may send duplicates if it fails after the broker accepts the event but before the publisher marks it as completed. Consequently, consumers must still be idempotent. The outbox guarantees that data changes and the intent to publish an event are persisted together; it does not by itself make the entire distributed workflow exactly-once.

## 8. Access Permissions and Security Along Boundaries

Each function should have an execution identity and only the minimum permissions required. For example:

- PlaceOrderFunction has permission to write order data and publish the OrderPlaced event.
- ReserveInventoryFunction has permission to read/write inventory data and publish reservation results.
- PaymentFunction has permission to access payment provider credentials and transaction data.
- NotificationFunction has permission to read notification configuration and call the email/SMS provider.

Avoid granting full database access to every function in the same project. Permissions should reflect each function's exact responsibilities, reducing the blast radius if credentials are leaked or a function is compromised.

Secrets such as API keys and connection credentials must be retrieved from a secret manager or the platform's secure configuration mechanism. Do not store secrets in source code, broadly shared environment variables, or logs.

For HTTP triggers, authenticate callers, enforce authorization on specific resources, and apply rate limiting where appropriate. For message/event triggers, control publish/subscribe permissions and validate the event source. Do not assume that an event arriving from a broker automatically has valid contents.

## 9. Latency, Cold Start, Scaling, and Cost

Decomposition directly impacts operations. Each function can scale according to its own traffic, yet every call across a function/service boundary can add latency and cost.

### 9.1. Cold Start

Cold start occurs when the platform must initialize a new execution environment before handling a request. For Java, startup time can be affected by:

- Number of dependencies and artifact size.
- Initialization time of frameworks, dependency injection, and clients.
- Loading configuration or establishing connections during initialization.
- Packaging format, runtime, and platform resource configuration.

Impact can be reduced by keeping functions focused, limiting unnecessary dependencies, avoiding heavy work in static initializers, and safely reusing clients across invocations. For workloads with strict latency requirements, measure actual cold start duration and consider mechanisms that keep instances warm if the platform supports them.

Do not split a business workflow into many tiny functions just to make them “lighter” without measuring end-to-end chain latency. Multiple initializations and data transfers can yield worse performance.

### 9.2. Scalability

Functions typically scale based on incoming requests or queued messages. This is useful when capabilities experience different traffic patterns: Notification may spike while order queries remain steady.

However, rapid scaling can put pressure on databases, external APIs, or concurrency limits. Configure concurrency limits, control queue consumption rates, and design backpressure when downstream dependencies cannot process at the same speed.

### 9.3. Cost

Serverless cost typically depends on invocation count, execution duration, resource configuration, storage, data transfer, and supporting services. Splitting allows scaling only the part under load, but also increases invocation counts, message counts, logs, traces, and management resources.

When comparing two options, include indirect costs:

- Number of calls between functions and services.
- Waiting time from synchronous calls.
- Number of retries and duplicate message deliveries.
- Storage costs for state, outbox tables, queues, and logs.
- Engineering effort for development, observability, and incident response.

Benchmark on a representative workload rather than relying on function count or the list price of a single invocation.

## 10. Signals for Splitting or Merging Boundaries

| Signal | Recommended Action to Consider |
|---|---|
| Distinct business language, rules, and data | Split into a service with clear ownership |
| Significantly different scaling needs under load | Split function or service to scale independently |
| Different security or access-permission requirements | Split functions and assign separate permissions |
| Independent deployment schedules or owning teams | Separate service boundaries may be beneficial |
| Two parts always have to be updated together | Re-evaluate whether the split is too granular |
| Frequent back-and-forth synchronous calls within one operation | Re-evaluate boundaries or move part of it to asynchronous |
| Two operations always require the same transaction to protect an invariant | Keep within the same service/transaction if possible |
| Function is just a small transformation with no distinct operational needs | Keep as an internal method or component |

There is no rule stating “one function per service” or “one database per function.” The right level of decomposition depends on business complexity, traffic, security requirements, operational capabilities, and team maturity.

For a small system, you can start with a modular application organized by bounded context and deploy select entry points as functions. Once there is concrete evidence of scaling, independent deployment, or fault-isolation needs, split out services. This keeps business boundaries clear from the start without introducing premature distributed complexity.

## 11. Common Design Mistakes

**Splitting by endpoint:** Making each endpoint a separate service scatters rules of the same domain and forces multi-place coordination for simple changes. Group endpoints by capability and data ownership.

**Splitting by table:** One service per table often turns data relationships into a web of network calls. Group data by business behavior and the invariants that must be protected.

**Sharing a database as a contract:** When other services read/write internal tables directly, schema changes can break multiple consumers. Use versioned APIs or events.

**Using events for everything:** Events are unsuitable when the caller needs an immediate answer or needs confirmation that an action was accepted. Choose commands, APIs, or events based on semantics and response requirements.

**Assuming messages arrive only once:** Retries and redeliveries can create duplicate orders, reservations, or payments. Use idempotency keys, unique constraints, and durable processing state.

**Holding business state in function memory:** Instances can be replaced or run concurrently. Persist required state in an appropriate data store.

**Neglecting access permissions:** Overly broad permissions on a function increase the blast radius of failures. Grant permissions strictly for the data and actions the function needs.

**Over-splitting to optimize cold start:** Increased call hops and failure points can slow the system down. Measure startup time and end-to-end latency before deciding.

**Inability to trace cross-service flows:** Isolated logs are insufficient to diagnose a stuck order. Propagate correlation IDs, event IDs, and trace context across calls and messages; emit structured logs without logging sensitive data.

## 12. Pre-Deployment Checklist

For each service and function, ensure you can answer the following questions:

- [ ] Can the service's business responsibility be expressed in one clear sentence?
- [ ] Which data and invariants does the service own?
- [ ] Is the function invoked by HTTP, message, event, or scheduler? Does the trigger match business needs?
- [ ] Are inputs, outputs, and error contracts defined?
- [ ] Where is state that must persist across invocations stored?
- [ ] Where can retries happen, and is the operation idempotent?
- [ ] Are a dead-letter queue, outbox, or Saga needed?
- [ ] Does the function have the exact minimum permissions to access its data and dependencies?
- [ ] Have timeouts, concurrency, cold start, and downstream dependency limits been reviewed?
- [ ] Are correlation IDs, event IDs, logs, and metrics in place to trace end-to-end flows?
- [ ] Have the costs of invocations, messages, storage, and data transfer been estimated on a representative workload?
- [ ] Does this boundary allow independent changes without creating excessive synchronous calls?

If data ownership, business rules, and duplicate-message handling cannot be answered clearly, the boundary is not yet ready for safe deployment.

## Conclusion

Serverless decomposition should start from business capabilities and data ownership. Services establish boundaries for rules, state, and contracts; functions are execution units triggered by HTTP, messages, or events. After defining boundaries, choose communication styles, design state and failure handling, and evaluate the impact on access permissions, retries, idempotency, cold start, scalability, and cost. A sound design lets each part evolve and scale under control while keeping the overall business workflow understandable and observable.
