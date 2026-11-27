# Rejecting Malformed Messages

## 1. The Problem: Bad Messages Must Not Enter Business Logic

An order processing system receives a JSON event from HTTP or a broker. The normal flow is:

~~~text
OrderSubmitted
  → Inbound Adapter
  → Validate
  → Router
  → Transformer
  → Splitter
  → Inventory / Pricing
  → Aggregator
  → OrderAccepted
~~~

However, a producer may send data missing required fields, having wrong types, violating the schema, or exceeding allowed size limits:

~~~json
{
  "schemaVersion": "1",
  "eventId": "EV-501",
  "tenantId": "tenant-a",
  "orderId": "",
  "revision": 2,
  "items": [
    {"sku": "", "quantity": -3}
  ]
}
~~~

If a Filter skips validation, bad data can travel deep into the Router or Transformer before throwing `NullPointerException`, enter repeated retries, keep an Aggregator waiting for a result that never arrives, or worse, trigger side effects from an invalid order.

**Rejecting malformed messages** means **detecting contract-violating data early, rejecting it intentionally, and routing it into a semantically accurate error-handling path**, instead of letting invalid data continue through the business flow. Rejection may mean returning HTTP 400/422, a rejection result, or a DLQ/quarantine record; it is not always silent dropping.

~~~mermaid
flowchart TD
    IN["Incoming bytes / message"] --> PARSE{"Decode + schema check"}
    PARSE -->|"Bad JSON/schema"| RAW["Ingress rejection / quarantine"]
    PARSE -->|"OK"| VAL{"Validate payload + metadata"}
    VAL -->|"Malformed / policy invalid"| REJ["Reject path: reason code + safe context"]
    VAL -->|"Well-formed"| ROUTE["Router / Transformer / business handler"]
    ROUTE --> OUT["Business outcome"]
    RAW --> OBS["Metrics + audit + delivery decision"]
    REJ --> OBS
~~~

This lesson belongs to the **Message filter and validation** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module focuses on implementing Enterprise Integration Patterns with Spring Integration, combining **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, while testing and observing each processing branch.

**After this lesson**, you will know how to classify input errors, choose where validation happens, configure Spring Integration Filters and discard/error flows, preserve correlation upon rejection, handle HTTP/brokers appropriately, write Java validation, and test malformed messages without infinite retries or business side effects.

## 2. Malformed Differs from Business Rejection and Transient Errors

Not every message that "cannot be processed" is malformed.

| Category | Example | Typical policy |
|---|---|---|
| **Malformed bytes** | JSON missing a brace, invalid encoding | Reject at ingress before constructing `Message<?>` |
| **Schema/type invalid** | `quantity="abc"` instead of integer, missing required `eventId` | Reject for contract violation |
| **Field constraints invalid** | `quantity=-3`, `items=[]`, `sku=""` | Reject per Bean Validation/business input policy |
| **Unsupported schema version** | Consumer supports v1/v2, receives v9 | Reject/quarantine with a dedicated error code |
| **Untrusted identity/header** | Payload tenant conflicts with principal | Authorization/security rejection, not treated as network failure |
| **Valid request rejected by business rule** | Out of stock, insufficient credit limit | Return a **business outcome** like `OUT_OF_STOCK`; not necessarily "malformed" |
| **Transient infrastructure error** | Database timeout, broker unavailable, HTTP 503 | Bounded retry/backoff |
| **Unknown remote outcome** | HTTP timeout after remote may have committed | Reconciliation/idempotency, do not assume malformed |

If all errors go into the same exception/retry path, unfixable malformed JSON will be redelivered repeatedly. Conversely, treating every exception as invalid input and ACKing/dropping it can cause a temporary database glitch to **lose valid work**.

**Principle:** classify by recoverability and responsibility: does the producer need to fix the data, or does the consumer need to retry a dependency? That distinction determines rejection, retry, DLQ, ACK, and Gateway status.

## 3. Three Layers of Validation Before Reaching the Business Handler

| Layer | Checks | Location |
|---|---|---|
| **Transport & decoding** | Byte size, encoding, JSON syntax, JSON types, Content-Type | HTTP controller, message converter, deserializer, inbound adapter |
| **Contract/schema** | Version, required fields, enums, nested objects, field formats, bounds | Validator before Router/Transformer |
| **Business admissibility** | Tenant permissions, order state, business limits, duplicate conflicts | Boundary service/domain validation |

These layers can overlap, yet they are distinct. Syntactically valid JSON can still miss `items`; a structurally valid `OrderCommand` can still try to update another tenant's order; a valid order can still lack inventory.

**A Filter only sees messages that were already constructed.** If Jackson/Avro/Protobuf deserialization fails **before the adapter emits a Spring Message**, the Filter is never invoked. You must design **separate ingress error handling**; you cannot claim "we have a Filter so all malformed JSON goes to `discardChannel`".

## 4. A Decision Contract for Every Inbound Message

A flow should terminate each input in one of the following semantically clear states:

1. **ACCEPTED:** qualified to enter the business processing pipeline.
2. **REJECTED_PERMANENT:** input violates the contract or permissions; cannot be fixed by retrying the exact payload.
3. **RETRYABLE_FAILURE:** undecided due to a temporary infrastructure failure; must not be ACKed as succeeded without durable recovery.

**BUSINESS_REJECTED** can also occur after validation—for example, insufficient stock; this differs from `MALFORMED_MESSAGE`.

~~~text
eventId=EV-501
validation=REJECTED_PERMANENT
reasonCode=INVALID_QUANTITY
field=items[0].quantity
retryable=false
~~~

Reason codes should be **stable, allowlisted**, and aligned with the contract; never expose raw JDBC/JSON parser exception messages publicly. APIs may return field details to authenticated callers, while logs/quarantine have separate data boundaries.

## 5. Why Rejecting Early Reduces Error Propagation

~~~mermaid
flowchart LR
    A["Malformed order"] --> F{"Ingress Filter"}
    F -->|"Reject"| R["Safe rejection"]
    F -->|"Accept"| T["Transformer"]
    T --> S["Splitter"]
    S --> W["Workers"]
    W --> G["Aggregator"]
    G --> O["Order result"]
~~~

If an invalid message is accepted upfront:

- Router may pick a route based on a null field or forged header.
- Transformer throws an exception with a hard-to-trace message.
- Splitter emits some children before encountering an invalid item.
- Workers may cause side effects from already-emitted children.
- Aggregator fails to receive enough expected outcomes.
- Gateway times out even though the true cause was invalid input data.
- Broker redelivers repeatedly because the handler throws an unclassified exception.

Therefore, prioritize validating **invariants checkable from the raw payload before any side effects or fan-out**. You do not need to run every expensive business check inside the Filter; however, fundamentals like schema, IDs, data types, collection bounds, and required fields should be verified early.

## 6. Java 17+: Defining the Input Contract with Records

Example using Bean Validation with the Jakarta API (Spring Framework 6/Boot 3+):

~~~java
record OrderLine(
    @NotBlank String sku,
    @Positive int quantity
) {}

record OrderCommand(
    @NotBlank String schemaVersion,
    @NotBlank String eventId,
    @NotBlank String tenantId,
    @NotBlank String orderId,
    @Positive int revision,
    @NotNull @Size(min = 1, max = 100)
    List<@Valid OrderLine> items
) {}
~~~

Annotations require importing `jakarta.validation.Valid` and constraints from `jakarta.validation.constraints`. In older Spring versions, the package differs; keep your Bean Validation dependency/provider aligned with your project version.

| Annotation | Condition |
|---|---|
| `@NotBlank` | Non-null string, not empty or whitespace-only |
| `@Positive` | Number greater than 0 |
| `@NotNull` | Field must have a non-null value |
| `@Size(min=1,max=100)` | Line item count within bounds |
| `@Valid` | Cascades validation into nested objects |

**Trap:** The Java record uses primitive `int`. JSON missing `quantity` may be defaulted to `0` by the deserializer depending on configuration; `@Positive` catches that case, but if you need to distinguish **missing** from **explicit zero**, use `Integer` with `@NotNull` and configure the deserializer/schema accordingly.

**Annotations are not automatically applied to every Spring Integration message.** A Validator must actually be invoked at an endpoint or via configured method validation; simply putting `@Valid` on a DTO does not ensure rejection.

## 7. Bean Validation in an Independently Testable Service

A validation service:

~~~java
@Service
class OrderValidationService {
    private final Validator validator;

    OrderValidationService(Validator validator) {
        this.validator = validator;
    }

    boolean isWellFormed(OrderCommand command) {
        if (command == null) {
            return false;
        }
        return validator.validate(command).isEmpty();
    }
}
~~~

`Validator` is `jakarta.validation.Validator`, provided by a Bean Validation provider such as Hibernate Validator (e.g., Spring Boot validation starter). This predicate is **pure, fast, and deterministic** as long as constraints do not query external systems.

In production, validation may also need:

- `eventId` matching a published format.
- Total byte size and item count bounded at the adapter.
- `orderId` uniqueness/tenant alignment per business policy.
- Maximum length on `sku`; `@NotBlank` alone does not block multi-megabyte strings.
- Checking `items` for duplicate line IDs if required by the contract.
- Schema version and allowed fields from the wire contract.

**Never place an HTTP/DB lookup that can time out inside a predicate and classify every lookup error as malformed.** A dependency outage is a `RETRYABLE_FAILURE`, not invalid input.

## 8. Java DSL: Filter Routing Bad Messages to a Discard Channel

Given a successfully deserialized `OrderCommand`:

~~~java
@Configuration
@EnableIntegration
class OrderValidationFlow {

    @Bean
    IntegrationFlow filterMalformedOrders(
            OrderValidationService validation) {
        return IntegrationFlow.from("orders.in")
            .filter(OrderCommand.class,
                validation::isWellFormed,
                spec -> spec.discardChannel("orders.rejected"))
            .channel("orders.valid")
            .get();
    }
}
~~~

**Meaning:**

- Predicate returns `true` → message continues to `orders.valid`.
- Predicate returns `false` → message is routed to `orders.rejected` per the discard channel configuration.
- There is no reason to forward malformed payloads to Routers or business handlers.

This snippet is a Java DSL pattern requiring imports, channels, and consumers suited to your Spring Integration version. `orders.rejected` must have a subscriber capable of storing/managing rejections; never create a discard channel without a receiver.

This is an **explicit business rejection path**, not automatically an `ErrorMessage` on `errorChannel`. If you need to throw an exception instead of sending to discard, see the separate option in section 11.

## 9. `@Filter` Annotation: Equivalent Style

You can use an annotated endpoint:

~~~java
@MessageEndpoint
class OrderMessageFilter {
    private final OrderValidationService validation;

    OrderMessageFilter(OrderValidationService validation) {
        this.validation = validation;
    }

    @Filter(
        inputChannel = "orders.filter.input",
        outputChannel = "orders.valid",
        discardChannel = "orders.rejected")
    public boolean accept(OrderCommand command) {
        return validation.isWellFormed(command);
    }
}
~~~

This example uses **a different input channel** from the Java DSL in section 8. They are **two independent alternatives**; do not register both for the same input unless competing consumers/dispatch semantics are intended.

The predicate must return a semantically meaningful Boolean. `false` is an **expected rejection**, unlike an infrastructure exception inside the method. When validation must return a list of error codes, a Boolean is not enough; you can use a validator/service step producing a `ValidationResult` before the Filter or let the rejection handler run deterministic validation again.

## 10. Ways to React When a Filter Rejects

| Configuration/policy | Desired behavior | Caution needed |
|---|---|---|
| No discard channel, no throw | Message stops at the Filter | Can **lose visibility** without metrics/audits |
| `discardChannel` | Sends rejected message to a separate flow | That flow must actually process and store/reply |
| `throwExceptionOnRejection(true)` | Throws `MessageRejectedException` for invalid messages | Callers/containers may retry if unclassified |
| Service Activator validation | Can throw a specific exception with reasons | Needs proper error handling and mapping |
| Return `RejectedOrder` as payload | Produces a structured response instead of an exception | Do not emit a rejection disguised as `OrderAccepted` |

Do not enable throw and discard simultaneously and **assume** both paths receive a copy. Exact ordering/behavior depends on the Filter/configuration mechanics and must be tested; for clarity in learning and operations, pick **one clear primary strategy** and build around it.

**Discard is not the same as a broker DLQ.** A discard channel is a concept **inside an `IntegrationFlow`**, whereas a DLQ is a transport failure destination; publishing to a DLQ requires configuring the corresponding publisher/handler.

## 11. Java DSL: Throwing Exceptions When Callers Need Fail-Fast

If the contract requires the caller to receive an immediate failure:

~~~java
@Bean
IntegrationFlow failFastOrderFilter(
        OrderValidationService validation) {
    return IntegrationFlow.from("orders.failfast.in")
        .filter(OrderCommand.class,
            validation::isWellFormed,
            spec -> spec.throwExceptionOnRejection(true))
        .channel("orders.failfast.valid")
        .get();
}
~~~

A `false` triggers `MessageRejectedException` at the Filter per configuration. In a synchronous flow using `DirectChannel`, the exception can propagate back to the Gateway/HTTP adapter. With `ExecutorChannel`, pollers, or broker listeners, however, it arises inside a **worker/error boundary** rather than returning directly to the original sending thread.

**Important:** throwing is a technical signal; it **does not automatically choose an HTTP status or broker ACK**. If a broker listener retries every exception by default, malformed events can loop indefinitely. You need a classifier/recoverer for permanent input errors distinct from retryable failures.

## 12. Keeping Specific Error Codes When a Predicate Only Returns Boolean?

A simple predicate:

~~~java
boolean isWellFormed(OrderCommand command)
~~~

only returns `true/false`. To know why a message was rejected, use a structured result type:

~~~java
record ValidationIssue(
    String fieldPath,
    String reasonCode
) {}

record ValidationResult(
    boolean valid,
    List<ValidationIssue> issues
) {
    static ValidationResult accepted() {
        return new ValidationResult(true, List.of());
    }

    static ValidationResult rejected(List<ValidationIssue> issues) {
        return new ValidationResult(false, List.copyOf(issues));
    }
}
~~~

Each issue carries a **stable** code such as `MISSING_ORDER_ID`, `INVALID_ITEM_QUANTITY`, or `TOO_MANY_ITEMS`, rather than a raw exception message with a stack trace. A validator can convert `ConstraintViolation<OrderCommand>` into `ValidationIssue` by mapping constraint names and field paths to the API's error code catalog.

**Never arbitrarily echo invalid field values into responses or logs.** Those values may contain PII or log-injection payloads.

## 13. Creating an Auditable Rejection Envelope Instead of Raw Exceptions

An error-path record:

~~~java
record RejectedOrder(
    String eventId,
    String orderId,
    String correlationKey,
    String outcome,
    List<ValidationIssue> issues,
    boolean retryable
) {}
~~~

Example:

~~~json
{
  "eventId": "EV-501",
  "orderId": null,
  "correlationKey": "batch-Q-501",
  "outcome": "REJECTED_PERMANENT",
  "issues": [
    {"fieldPath": "orderId", "reasonCode": "MISSING_ORDER_ID"},
    {"fieldPath": "items[0].sku", "reasonCode": "MISSING_SKU"},
    {"fieldPath": "items[0].quantity", "reasonCode": "INVALID_QUANTITY"}
  ],
  "retryable": false
}
~~~

For malformed raw bytes, **`eventId` or `correlationKey` may be missing**. Never invent a shared `UNKNOWN` key and dump unrelated rejected messages into the same aggregation group. Use a **transport message identity/quarantine record ID** for auditing; business correlation applies only when trusted data is available.

Logging rules: bound issue count, field path length, and stored payload size; encrypt/mask sensitive data; write structured logs with clear access controls and retention.

## 14. Rejection Handler: Safe Persistence Before Completing Delivery

A Service Activator for the discard channel:

~~~java
@MessageEndpoint
class RejectedOrderHandler {
    private final RejectionStore rejectionStore;

    RejectedOrderHandler(RejectionStore rejectionStore) {
        this.rejectionStore = rejectionStore;
    }

    @ServiceActivator(inputChannel = "orders.rejected")
    public void handleRejected(Message<OrderCommand> message) {
        // The store re-runs deterministic validation,
        // generates reason codes, and persists sanitized metadata.
        rejectionStore.recordMalformedOrder(message);
    }
}
~~~

`RejectionStore` is an application interface **you implement**, not a built-in framework API. If it writes to a DB or forwards to a DLQ, make sure the record is persisted or durable responsibility is transferred before considering the input handled.

**Never push raw payloads containing credentials/PII into a public DLQ** without controls. Enforce capacity/quotas on quarantine; a buggy producer can send millions of malformed messages and fill storage.

**Never loop a discard flow back into the input Filter infinitely** unless there is a controlled, contract-bound data repair step. Retrying the exact same malformed payload will never make it valid.

## 15. JSON Syntax Errors Happen Before the Filter

A raw message:

~~~text
{"orderId": "O-501", "items": [
~~~

The Jackson/JSON decoder will throw an exception due to the unclosed input. At that point, Spring Integration's `filter(OrderCommand.class, ...)` **has no `OrderCommand` to inspect**.

Ingress options:

- HTTP: map parse/deserialization errors to a 400 response per the API contract.
- Kafka: configure a deserializer/error-handling deserializer and listener recoverer suited to your adapter version.
- AMQP/JMS: message converter, container error handler, and DLQ/quarantine policy.
- File ingest: record the error/safe raw reference and move to a quarantine directory with retention.

**Do not claim malformed messages always reach `errorChannel`**: in several adapters, failures happen during conversion before a Spring message is ever published; handling resides at the container/adapter boundary. You must test parse errors using **real raw bytes**, not only by constructing an invalid Java object and sending it to a channel.

## 16. Schema Versions and Contract Evolution

A consumer accepts v1/v2 but receives:

~~~json
{
  "schemaVersion": "9",
  "eventId": "EV-502",
  "orderId": "O-502",
  "items": [{"sku": "SKU-1", "quantity": 2}]
}
~~~

This is an **unsupported schema version**, distinct from `INVALID_QUANTITY`. Policies may include:

1. Reject with `UNSUPPORTED_SCHEMA_VERSION`, listing supported versions.
2. Quarantine until the consumer/schema registry is updated cleanly.
3. Route through a version-specific converter **if supported by the contract**.

Do not assume a new schema has the same semantics merely because Jackson deserializes most fields. Changes in amount/currency semantics, permissions, or nullable fields can silently produce wrong results without throwing exceptions.

**Unknown fields** can be allowed for forward compatibility or rejected in strict mode; choose **intentionally** and test. Missing required fields should always be caught at the schema/validation layer rather than relying on getters returning null in business handlers.

## 17. Header Validation: Transport Metadata and Identity

A message with a valid payload but invalid headers:

~~~text
headers.contentType = "application/octet-stream"
headers.tenantId    = "tenant-b"   // payload belongs to tenant-a
headers.schemaVer   = "2"          // payload is schema v1
headers.correlation = very-long-untrusted-string
~~~

Distinguish between:

- Headers attached by a **trusted adapter** after authentication.
- **Self-declared producer/client headers**, which may be wrong or spoofed.
- Framework headers like `replyChannel`, `errorChannel`, and `MessageHeaders.ID`, which carry internal semantics.

**Never use a raw tenant header to decide authorization or correlation** before verifying the principal/credentials. If payload and header conflict, reject or enforce canonical policy from the authenticated source; never pick one arbitrarily.

Limit header count/length and allowlist names for broker mappings. Keep untrusted expressions, channel names, or bean names out of Routers and Control Bus.

## 18. Placing the Filter Before or After Transformer and Router?

| Position | Advantages | Risks |
|---|---|---|
| Right after ingress decoding | Stops malformed inputs early, fewer side effects | Lacks enriched data needed for some business rules |
| After canonicalization Transformer | Validates a uniform model, fewer branches | Transformer may throw if payload is badly broken |
| Before Router | Router never sees null fields or wrong schema | Must provide a clear rejection route |
| After Router, before business handler | Operation-specific validation | Easy to miss validating some branches |
| After Splitter | Validates each child | Other children may already be emitted; Aggregator misses members |

**Recommended layering:** validate **bytes/schema/basic constraints at ingress**, canonicalize safely, validate **domain-specific rules at the appropriate service boundary**, and validate outbound contracts when needed. Not every check belongs in a single Filter.

Avoid a Transformer calling `value.trim()` on a null before validation runs: the error becomes an uncoded `NullPointerException`. Use null-safe conversion for nullable fields and route failures into the error catalog.

## 19. Validators Must Not Turn Infrastructure Outages into Malformed Errors

An anti-pattern:

~~~java
boolean isValid(OrderCommand order) {
    try {
        return inventoryApi.productExists(order.items().get(0).sku());
    } catch (Exception unavailable) {
        return false; // Wrong: turns an outage into invalid input.
    }
}
~~~

If the Inventory service times out, returning `false` permanently rejects a valid order. Instead:

- Use **pure validation** in Filters for shape/format/size/range.
- Keep dependency-calling business validation in a separate stage.
- Classify timeouts/network errors as `RETRYABLE_FAILURE`.
- Produce `UNKNOWN_SKU` or business rejection **only after verifying the dependency returned an authoritative negative response**.

Storage/network exceptions must not be routed into a discard flow just to suppress retries, nor should malformed input be retried like a database outage.

## 20. Filter vs Router, Transformer, and Bean Validation

| Component | Primary question | Output |
|---|---|---|
| **Message Filter** | Should this message continue? | Forward or reject/discard/exception |
| **Content-Based Router** | Which branch should this valid message take? | One/multiple channels per policy |
| **Transformer** | How should the payload be represented? | Transformed payload/message |
| **Bean Validation** | Does the object violate constraints? | Constraint violations |
| **Service Activator** | Which business operation runs? | Reply/side effect or exception |
| **Aggregator** | Which messages share a group and when is it complete? | Aggregated result |

A Filter is not a **JSON parser**, **schema registry**, **transaction manager**, or **authorization framework**. It can call a predicate evaluating admission criteria, while the other responsibilities belong in their proper components.

**A rejected request does not automatically become a response.** Returning a rejection reason via a Gateway requires a reply path or exception mapper. Informing a broker of permanent failure requires container recoverers/DLQ/ACK policies.

## 21. Gateway: Dropping Messages Can Turn Validation Errors into Timeouts

A synchronous Gateway expects **a reply**:

~~~java
@MessagingGateway(defaultRequestChannel = "orders.gateway.in")
interface OrderGateway {
    OrderAccepted submit(OrderCommand command);
}
~~~

If the Filter returns `false` and **silently drops** the message, no reply reaches the caller. The caller waits until `replyTimeout` and fails with a timeout even though the root cause was simply an empty `orderId`.

Two clear options:

**A — throw an exception (fail fast):**

~~~text
Gateway request
  → Filter throwExceptionOnRejection=true
  → MessageRejectedException
  → Controller/HTTP error mapper
  → 400/422 + validation reasonCode
~~~

**B — return a typed rejection:**

~~~text
Gateway request
  → validation decision
  → invalid: OrderRejected(eventId, issues)
  → valid: OrderAccepted(orderId)
  → Gateway receives an OrderDecision
~~~

Option B requires an **explicit step building the rejection reply** and a matching return type—it does not appear automatically just because a Filter has `discardChannel`. For async Gateways, verify reply headers/channels and timeout policies. Never return a fake `SUCCESS` just to avoid a timeout.

## 22. Typed Rejection Results for Request–Reply

A Java contract:

~~~java
sealed interface OrderDecision
    permits OrderAccepted, OrderRejectedDecision {}

record OrderAccepted(
    String eventId,
    String orderId
) implements OrderDecision {}

record OrderRejectedDecision(
    String eventId,
    String reasonCode,
    List<ValidationIssue> issues
) implements OrderDecision {}
~~~

Gateway:

~~~java
@MessagingGateway(defaultRequestChannel = "orders.decide")
interface DecisionGateway {
    OrderDecision decide(OrderCommand command);
}
~~~

This is an **application contract**, not an API auto-generated by `.filter()`. A decision service/Transformer or rejection reply flow must produce `OrderRejectedDecision` with the proper reply headers. When JSON syntax fails before DTO construction, the controller or adapter must separately map parse errors into the same reason code catalog.

## 23. Brokers: A Malformed Message Can Become a Poison Pill

A Kafka/AMQP consumer receives:

~~~text
eventId=EV-900
quantity="many"    // wrong type, not an integer
~~~

Redelivering the exact same bytes will not make the message valid. If the container retries indefinitely, the partition/queue can get **blocked by the poison pill**, flooding logs and delaying valid messages behind it.

~~~mermaid
flowchart TD
    IN["Broker message"] --> DECODE{"Deserialize + validate"}
    DECODE -->|"Permanently malformed"| D["Durable DLQ / quarantine"]
    DECODE -->|"Valid"| WORK["Business handler"]
    WORK -->|"Success"| ACK["ACK / commit offset"]
    WORK -->|"Transient failure"| RETRY["Bounded retry + backoff"]
    RETRY --> WORK
    D --> DUR{"DLQ safely persisted?"}
    DUR -->|"Yes"| ACK
    DUR -->|"No"| RETAIN["Retain recovery responsibility; do not lose source"]
~~~

This is a **conceptual workflow**: Kafka, AMQP, and JMS each have distinct transaction/ACK semantics. "Publish to DLQ then commit source" is not automatically atomic. When the DLQ is unavailable, durable retry/quarantine is required; never silently ACK and drop the input.

**Do not assume `MessageRejectedException` is non-retryable by default.** The container error classifier/recoverer must distinguish permanent validation errors from transient exceptions.

## 24. Discard Channel, Error Channel, and DLQ Are Distinct Boundaries

| Concept | Context | Responsibility |
|---|---|---|
| `discardChannel` | Spring Integration Filter | Receives messages rejected by the predicate |
| `errorChannel` | Spring Integration error messaging | Receives `ErrorMessage` when errors occur within an error-handled boundary |
| Broker DLQ/DLT | Kafka/AMQP/JMS | Stores failed messages outside the main consumption stream |
| Quarantine database/object store | Application | Stores metadata/reasons and a safe raw reference for review/replay |
| Rejection reply | Gateway/HTTP | Informs caller so input can be fixed |

A discard handler may publish to a DLQ, yet **configuring `discardChannel("orders.rejected")` does not create a DLQ**. Parse errors in a message converter may enter the adapter/container recoverer **without ever reaching the Filter**.

Quarantine records should store:

~~~text
quarantineId, sourceSystem, receivedAt
transportReference, schemaVersion (if available)
eventId (if trustworthy), reasonCode
sanitizedIssues, payloadHashOrProtectedReference
reviewStatus, replayPolicy
~~~

Enforce payload limits, access control, encryption, retention, and quotas. Never send raw bodies containing PII/credentials to a public DLQ.

## 25. Permanent vs Retryable: Classify Before ACKing

| Outcome | Auto-retry same bytes? | Action |
|---|---|---|
| Malformed JSON | No | Reject at decoder, quarantine |
| Missing required field | No | Field reason code |
| Unsupported schema | Do not hot-retry | Quarantine/migrate once converter exists |
| Unauthorized tenant | No | Security rejection and audit |
| Database timeout | Possibly | Bounded retry, fresh transaction |
| Remote 503 | Conditionally | Backoff, deadline, circuit breaker |
| HTTP timeout, unknown side effect | Do not blindly retry | Reconcile/idempotency |
| Duplicate completed event | Do not re-run side effect | ACK/cached result |

**Message Filter is only one place where rejection happens.** If a Filter's validator calls a dependency and hits a network exception, that does not prove the payload is malformed. Separate pure validation from I/O checks so you never wrongly tag failures as `retryable=false`.

Reprocessing a DLQ after a producer fixes a schema **is a controlled workflow**, not infinite hot-retrying of the same bad payload.

## 26. A Filter After Splitter Can Leave an Aggregator Waiting Forever

Example:

~~~text
Order O-101 → Splitter → L1, L2, L3

L1 valid → Inventory reply
L2 invalid quantity → Filter drops
L3 valid → Inventory reply

Aggregator expectedMembers={L1,L2,L3}
Aggregator receivedMembers={L1,L3}
→ group missing L2
~~~

~~~mermaid
flowchart TD
    S["Splitter: L1,L2,L3"] --> F{"Per-line Filter"}
    F -->|"L1,L3 valid"| W["Workers"]
    F -->|"L2 invalid"| REJ["Line rejection outcome"]
    W --> AG["Aggregator"]
    REJ --> AG
    AG --> O["OrderResult / PARTIAL / FAILED"]
~~~

Two options:

1. **Validate the entire collection before Splitter:** if any line is malformed, reject the whole request and emit zero children.
2. **Per-item rejection outcome:** if partial processing is valid, convert the failure into `LineOutcome(success=false, reasonCode="INVALID_QUANTITY")` with the proper **group ID, member ID, and sequence metadata** so the Aggregator completes intentionally.

Never arbitrarily shrink `expectedMembers` from 3 to 2 and report success. Invalid members must be represented via an **explicit outcome/skip policy** or whole-batch failure.

## 27. Java: Child Rejections Must Carry Proper Correlation

~~~java
record LineOutcome(
    String orderGroupId,
    String lineId,
    boolean success,
    String reasonCode
) {}

LineOutcome invalidLine = new LineOutcome(
    "tenant-a|O-101|rev-2",
    "L2",
    false,
    "INVALID_QUANTITY");
~~~

When the Aggregator receives this outcome:

- `orderGroupId` must point to one logical processing group.
- `lineId` must belong to the expected **manifest member IDs**.
- Duplicates must not count as new members.
- A failure outcome is a **terminal conclusion for a member**, not an exception dropping the reply.
- The final summary must be `FAILED`/`PARTIAL` if any required member did not succeed.

If the entire request is rejected **before Splitter**, returning a single rejection result directly is cleaner than creating a dummy Aggregator group just to collect errors.

## 28. Malformed Messages and Idempotency Keys

A rejected message may have a valid event ID, or the ID may be missing or mutated:

~~~text
Message 1: eventId=EV-501, orderId missing
Message 2: eventId=EV-501, orderId=O-502, payload changed
~~~

If duplicate tracking for message 1 marks it as **business completed**, a fixed resend from the producer could be blocked. Yet storing nothing allows repeated redelivery of the exact malformed bytes to cause noise. You need **two distinct record types** by contract:

- **Quarantine/rejection record:** tracks bad inputs and fixes/replays.
- **Business idempotency record:** tracks logical operations already processed.

Same key + different payload requires a fingerprint/validation/version policy rather than silent acceptance. The producer must specify whether a corrected message uses a **new event revision** or the same logical event under allowed rules. Reprocessing requires auditing and protection against double side effects.

When a trusted `eventId` cannot be extracted from raw bytes, use a separate **transport/quarantine reference** for tracing instead of lumping everything under an `UNKNOWN` key.

## 29. Resource Limits Even Before the Filter

A syntactically valid JSON payload that is dangerously large:

~~~text
Content-Length: 120 MiB
items: 1_000_000 entries
nestingDepth: 100_000
header businessKey: 10 MiB string
~~~

Because Filters run **after deserialization**, they cannot guard against all parser costs. Enforce:

- Max request/message bytes at the adapter.
- Parser limits on depth, token count, and field length.
- Max array length and line item count.
- Timeouts/concurrency quotas for parsing/validation.
- Avoidance of high-complexity regexes on untrusted inputs.
- Never logging huge raw payloads or retaining rejected messages indefinitely.

Bound sizes before **Splitter fan-out** so one message cannot spawn millions of tasks. Rejecting oversized input early is far cheaper than validating after allocating the entire object graph.

## 30. Security: Useful `reasonCode` Without Leaking PII

A malformed message may contain credentials, tokens, emails, or log-injection payloads. Never copy raw values into error bodies:

~~~text
Wrong:
  reason="Invalid payment.cardNumber=4111...; Bearer secret..."

Right:
  reasonCode=INVALID_CARD_FORMAT
  fieldPath=payment.cardNumber
  eventId=EV-501
~~~

Validation does not replace parameterized SQL, authorization, or output encoding, yet it is the first gate against contract-violating inputs.

In multi-tenant systems, verify the tenant from a trusted principal/credential; mismatches with payload/headers must be rejected per security policy. Never use a client-supplied raw `tenantId` for authorization just because it passed Bean Validation.

Do not return internal exceptions containing table names, host addresses, stack traces, or raw secrets to callers. Use a stable reason-code catalog, log sanitization, and sensitivity-based retention.

## 31. Unit Testing Bean Validation: Both Object and Nested Items

JUnit 5 with a Bean Validation provider:

~~~java
@Test
void rejectsBlankOrderAndInvalidNestedItem() {
    ValidatorFactory factory =
        Validation.buildDefaultValidatorFactory();
    try {
        Validator validator = factory.getValidator();
        OrderCommand malformed = new OrderCommand(
            "1", "EV-501", "tenant-a", " ",
            2, List.of(new OrderLine("", -3)));

        Set<ConstraintViolation<OrderCommand>> violations =
            validator.validate(malformed);

        assertFalse(violations.isEmpty());
        assertTrue(violations.stream().anyMatch(v ->
            v.getPropertyPath().toString()
                .contains("orderId")));
        assertTrue(violations.stream().anyMatch(v ->
            v.getPropertyPath().toString()
                .contains("quantity")));
    } finally {
        factory.close();
    }
}

@Test
void acceptsWellFormedOrder() {
    ValidatorFactory factory =
        Validation.buildDefaultValidatorFactory();
    try {
        OrderCommand valid = new OrderCommand(
            "1", "EV-502", "tenant-a", "O-502",
            1, List.of(new OrderLine("SKU-1", 2)));
        assertTrue(factory.getValidator()
            .validate(valid).isEmpty());
    } finally {
        factory.close();
    }
}
~~~

Imports are omitted; you can inject a Spring-managed `Validator` rather than creating a factory per test. For tests to catch nested `quantity`, a Bean Validation provider must be present and cascaded `@Valid` properly applied.

**Object-level unit tests do not prove the deserializer rejects wrongly typed JSON**, because the Java object already exists. Nor do they prove routing to the discard channel or broker ACKs.

## 32. Integration Test: Filter Routing Malformed Objects to Discard Channel

Isolated Spring test context:

~~~java
@Configuration
@EnableIntegration
class OrderFilterTestConfig {

    @Bean
    IntegrationFlow validationFlow(
            OrderValidationService validation) {
        return IntegrationFlow.from("test.orders.in")
            .filter(OrderCommand.class,
                validation::isWellFormed,
                spec -> spec.discardChannel("test.orders.rejected"))
            .channel("test.orders.valid")
            .get();
    }

    @Bean("test.orders.valid")
    PollableChannel validOutput() {
        return new QueueChannel();
    }

    @Bean("test.orders.rejected")
    PollableChannel rejectedOutput() {
        return new QueueChannel();
    }
}
~~~

Test:

~~~java
@Autowired
ApplicationContext context;

@Test
void malformedOrderGoesOnlyToRejectChannel() {
    MessageChannel input = context.getBean(
        "test.orders.in", MessageChannel.class);
    PollableChannel valid = context.getBean(
        "test.orders.valid", PollableChannel.class);
    PollableChannel rejected = context.getBean(
        "test.orders.rejected", PollableChannel.class);

    OrderCommand malformed = new OrderCommand(
        "1", "EV-501", "tenant-a", "",
        1, List.of(new OrderLine("SKU-1", 2)));

    assertTrue(input.send(new GenericMessage<>(malformed)));
    Message<?> rejectedMessage = rejected.receive(1_000);
    assertNotNull(rejectedMessage);
    assertEquals(malformed, rejectedMessage.getPayload());
    assertNull(valid.receive(0));
}
~~~

Run in an isolated context with no competing consumers draining the test output. This test demonstrates **accurate internal Filter rejection and routing**; it does not replace broker DLQ durability tests or raw JSON error handling tests.

## 33. Integration Test: Fail-Fast Throwing at the Right Boundary

A separate synchronous test flow:

~~~java
@Bean
IntegrationFlow failFastTestFlow(OrderValidationService validation) {
    return IntegrationFlow.from("test.failfast.in")
        .filter(OrderCommand.class,
            validation::isWellFormed,
            spec -> spec.throwExceptionOnRejection(true))
        .channel("test.failfast.valid")
        .get();
}
~~~

A guiding assertion:

~~~java
@Test
void failFastFilterRejectsMalformedOrder() {
    MessageChannel input = context.getBean(
        "test.failfast.in", MessageChannel.class);
    OrderCommand bad = new OrderCommand(
        "1", "EV-503", "tenant-a", "",
        1, List.of(new OrderLine("SKU-1", 2)));

    assertThrows(MessagingException.class,
        () -> input.send(new GenericMessage<>(bad)));
}
~~~

In Spring Integration, a Filter rejection error is typically `MessageRejectedException` (a messaging exception subtype), though callers/adapters may wrap exceptions; thorough tests should assert **root cause and failed message** against the actual topology.

With an `ExecutorChannel`, the Filter runs on a worker thread, so do not expect `input.send()` to throw immediately on the test thread. In that case, test the error channel or recoverer instead.

## 34. Testing Raw Bytes and Failures Before the Filter Runs

These cases cannot be simulated with `GenericMessage<OrderCommand>` alone:

~~~text
{ "items": [

{"quantity": "two"}

{"schemaVersion": "9", ...}

<Extremely deep JSON nesting>

Body with unsupported encoding.
~~~

Test at the real boundaries:

- **HTTP:** send raw bodies with the proper Content-Type; assert HTTP error status, response code, and max-size behavior.
- **Kafka:** send bytes through real serializer/deserializer; test listener error handler, DLT, and offset policy.
- **AMQP/JMS:** send messages with invalid content-type/converter metadata; verify reject/nack/DLQ.
- **File ingest:** test quarantine paths and retention for unparseable files.

JSON with duplicate keys may be parsed using the last value if strict duplicate detection is disabled. If the contract **forbids duplicate property names**, enable the parser setting/schema validation and test separately; a deserialized Java object retains no memory of duplicate keys.

**Distinction:** decode errors happen before a Spring Integration message exists, so testing the Filter directly does not verify adapter recovery.

## 35. End-to-End Test Matrix

| Case | Input/fault | What must be proven |
|---|---|---|
| Valid order | Matches schema and required fields | Enters business route |
| Malformed syntax | JSON missing closing bracket | Rejected at ingress |
| Wrong JSON type | Quantity is a string | Schema/type rejection |
| Missing ID | `eventId=""` | Does not reach handler |
| Empty items | `items=[]` | Violates `@Size` |
| Invalid nested item | `sku=""`, `quantity=-3` | Field issues returned |
| Unsupported schema | Version 9 | Code `UNSUPPORTED_SCHEMA_VERSION` |
| Unexpected fields | Strict/compatible mode | Outcome matches chosen contract |
| Header/tenant mismatch | Tenant conflicts with principal | Security rejection |
| Oversized body | Exceeds byte/array limits | Rejected before fan-out |
| Filter discard | Predicate false | Only reaches discard channel |
| Fail-fast Filter | Throw enabled | Proper exception/response |
| Gateway invalid input | Missing order ID | No pointless timeout |
| Broker poison pill | Same malformed bytes redelivered | No infinite retry |
| DLQ publish unavailable | Quarantine destination down | Unpersisted message not lost |
| Database outage | External validation dependency fails | Retryable path, not permanent reject |
| Invalid child | Filter drops L2 after Splitter | Reject whole group or keep correlated outcome |
| Aggregator duplicate | L1 arrives twice | Does not falsely reach expectedCount |
| Same key/different payload | Input fixed but event ID reused | Conflict/revision policy |
| Async exception | Worker throws after send | Hits proper error boundary |
| Cross-tenant collision | Identical IDs, different tenants | No data mixing or leakage |
| DLQ replay | Fixed input replayed cleanly | Idempotency and auditing hold |

Do not merely assert that a DLQ message exists. Verify **the business handler did not run**, zero side effects occurred, `reasonCode` is accurate, retries are bounded, and recovery holds across consumer restarts.

## 36. Observability: Knowing Whether Rejections Are Data or Infrastructure Errors

Suggested metric names:

| Metric | Meaning |
|---|---|
| `ingress.messages.received.count` | Messages arriving |
| `ingress.decode.failure.count` | Syntax/encoding/type errors |
| `validation.rejected.count` | Messages rejected post-deserialization |
| `validation.issues.count` | Count of field violations |
| `validation.rejected.by_reason.count` | Common reason codes |
| `validation.duration` | Validator latency and CPU |
| `validation.payload.too_large.count` | Inputs exceeding limits |
| `rejection.channel.failure.count` | Failures routing to rejection path |
| `quarantine.pending.count` | Messages awaiting review |
| `quarantine.storage.bytes` | Storage pressure |
| `broker.poison.retry.count` | Redeliveries of malformed messages |
| `broker.dlq.publish.failure.count` | DLQ unavailable |
| `gateway.invalid.timeout.count` | Caller timeouts due to missing rejection replies |
| `aggregator.missing.member.count` | Groups missing children after Filter |

These are **suggested metrics**, not default meters exported by Spring Integration. Use low-cardinality labels like `flowName`, `reasonCode`, `outcome`, and finite `schemaVersion`; never use full event IDs, order IDs, or raw exception strings as metric tags.

Structured logs/quarantine entries might contain:

~~~text
quarantineId=Q-9001
source=orders.kafka
schemaVersion=9
reasonCode=UNSUPPORTED_SCHEMA_VERSION
transportReference=partition-2/offset-183
eventId=EV-501
retryable=false
businessHandlerInvoked=false
~~~

Enforce access control, PII masking, and retention. Do not use unbounded-cardinality fields as metric labels or send raw malformed payloads to uncontrolled monitoring systems.

## 37. Runbook When a Malformed Event Stalls a Consumer

1. **Identify the failure boundary:** decode, Filter, Transformer, or business handler?
2. **Inspect the contract:** syntax, schema version, required fields, Content-Type, payload size.
3. **Classify:** permanently malformed, business rejection, or transient infrastructure failure?
4. **Check retry policy:** is it hot-retrying the exact same bytes endlessly?
5. **Inspect the Filter:** discard, throw, or silent drop?
6. **Check broker ACK/offset:** was DLQ/quarantine persisted safely before finishing the source message?
7. **Check the reject handler:** does the channel have a consumer, remaining storage capacity, and write permissions?
8. **Check the Gateway:** does the caller receive a rejection or just time out?
9. **Check the Aggregator:** did a Filter-dropped child leave a group short of outcomes?
10. **Check security:** who supplied tenant/headers; did raw data leak into logs?
11. **Remediate:** fix the producer, schema adapter, or quarantine failing messages per policy.
12. **Regression test:** replay raw bad bytes and verify zero side effects.

Never bulk-ACK/drop without separating permanently invalid messages from outages. Never replay an entire DLQ after a schema upgrade without rate limiting, authorization, auditing, and idempotency.

## 38. Practice Exercise: Pipeline Rejecting Malformed Orders

Build the **ValidatedOrderFlow** application:

1. Define `OrderCommand` with Jakarta Bean Validation and item/payload byte limits.
2. Write a pure, deterministic `OrderValidationService` for required fields/formats.
3. Configure `orders.in → Filter → orders.valid` with `discardChannel=orders.rejected`.
4. Write a reject handler producing `reasonCode` and storing sanitized metadata.
5. Build a separate fail-fast flow with `throwExceptionOnRejection(true)` and compare both behaviors.
6. Test a Gateway so invalid input yields a reply/exception instead of timing out pointlessly.
7. Test raw malformed HTTP JSON and type errors occurring before the Filter.
8. Connect a broker adapter and configure permanent failure/DLQ handling.
9. Simulate an unavailable DLQ and verify source messages are not lost before durable recovery.
10. Add a Splitter with three items where item 2 is invalid; choose whole-order rejection or per-item failure outcomes.
11. Test correlation, duplicates, late replies, and transient failures to ensure zero double side effects.
12. Monitor rejections, reason codes, poison pills, and quarantine backlogs.

**Completion criteria:** malformed input is rejected at the right boundary; no side effects occur; error paths carry `reasonCode`; no infinite retries; transient outages are not misclassified as malformed; Gateways return meaningful outcomes; Aggregators never silently lose children; tests cover both raw bytes and Spring messages.

## 39. Common Misconceptions

**"Message Filter catches all malformed JSON."** False. The deserializer may fail before a Spring Message is ever created.

**"Filter returning false means it goes to `errorChannel`."** No. It may drop, send to discard, or throw an exception depending on configuration.

**"`discardChannel` is the broker DLQ."** No. It is a channel inside `IntegrationFlow`; a DLQ requires an adapter/publisher.

**"Enabling `throwExceptionOnRejection` automatically returns HTTP 400."** Not automatically. You need an appropriate Gateway/controller mapper.

**"Silent dropping lets the request finish cleanly."** Gateways can time out, and brokers can ACK and lose unaudited input.

**"Every validation failure should be retried."** Permanently malformed data cannot be fixed by retrying the same bytes.

**"A database timeout inside a validator means invalid input."** False. Outages belong to a different failure category.

**"Adding `@Valid` to a DTO is enough to reject messages automatically."** No. A Validator must actually be invoked.

**"If a post-Splitter Filter drops one line, Aggregator still has enough members."** No. The group can remain incomplete forever.

**"Receiving three messages means all three lines arrived."** False when duplicates occur; use manifests and distinct member IDs.

**"Raw tenant headers can be used for authorization."** No. Tenants must be verified against the principal/credentials.

**"Logging the entire raw payload is best for debugging."** It can leak PII/secrets and enable log injection/storage abuse.

**"If the new schema parses, it is compatible."** Not necessarily; check semantics, constraints, and versions.

**"Any DLQ message can be replayed at any time."** Requires authorization, versioning, idempotency, quotas, and auditing.

**"Filter replaces transactions, retries, and idempotency."** No. It only decides forward vs reject based on a predicate.

## 40. Takeaways

**Rejecting malformed messages** is an **intentional rejection workflow**, not merely a `true/false` predicate. Layer **decode → schema/Bean Validation → domain/security checks**, separate permanently malformed payloads from business rejections and transient failures, and choose **discard channel, typed rejection, or exception** according to the caller/transport contract.

In **Spring Integration**, a Filter only inspects **messages already constructed**; JSON parse failures must be handled at the inbound adapter. A Filter can send rejected messages to a discard channel or throw an exception, but **it does not automatically produce HTTP 400s, broker DLQs, or ACK policies**. Those must be designed and tested independently.

Validate **before side effects and Splitter whenever possible**; when rejecting individual children, preserve correlation and emit failure outcomes for the Aggregator or fail the entire batch. Combine stable `reasonCode`s, safe logging, bounded resource usage, idempotency, retry classification, and cross-wire/message-boundary tests so bad data is rejected **at the right place, for the right reason, without losing valid work**.

### References

- Spring Integration Reference, **Message Filter**: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Framework Reference, **Bean Validation**: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Enterprise Integration Patterns, **Message Filter**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Filter.html
