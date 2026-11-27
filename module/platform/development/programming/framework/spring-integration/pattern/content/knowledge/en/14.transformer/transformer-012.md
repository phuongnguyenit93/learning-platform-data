# Distinguishing Transformer from Service Activator

## 1. Why Distinguish Two Endpoints That Look So Similar?

In the **Transformer** chapter of the **SPRING_INTEGRATION_PATTERN** module, we practice Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible, and testable message flows. Alongside Router, Filter, Splitter, Aggregator, Gateway, retry, error channel, and correlation, **Transformer** and **Service Activator** are two components frequently placed back-to-back in the same `IntegrationFlow`.

They are easily confused because both can receive a message, invoke a Java method, and send a result onward:

~~~java
// Both statements can take an input and produce an output.
.transform(RawOrder.class, normalizer::normalize)
.handle(NormalizedOrder.class, (order, headers) -> service.process(order))
~~~

The critical difference **is not whether a Java method is called**, but **the endpoint's responsibility and contract**:

- **Transformer** changes the representation or content of a message for subsequent steps to consume. It must **produce a non-null result** when succeeding.
- **Service Activator** invokes a service to perform an operation. It may **only execute an action with no reply**, or **return a reply** when acting as a request/reply step.

Example order system receiving raw orders:

~~~mermaid
flowchart LR
    A["RawOrder<br/>amountText='1250000'"] --> T["Transformer<br/>parse + normalize"]
    T --> B["NormalizedOrder<br/>amountVnd=1250000"]
    B --> S["Service Activator<br/>record order"]
    S --> D["Order repository / domain service"]
~~~

A function parsing an amount string to `BigDecimal` and normalizing a country code needs no database access. Conversely, **placing an order, reserving inventory, or calling a payment API** is a business action belonging in a Service Activator or a dedicated adapter/gateway.

**Lesson Objectives**

1. Understand the roles of Transformer and Service Activator in Enterprise Integration Patterns.
2. Distinguish **outputs, replies, `null`, side effects, transactions, and failures** for each endpoint.
3. Write Java DSL with `.transform()`, `.handle()`, and their corresponding annotations.
4. Understand that a Service Activator can also return a message, without turning every operation into a Transformer.
5. Choose the right endpoint in sync/async flows and request/reply flows with Gateways.
6. Test transformation logic, single-execution effects, header propagation, and error paths.

## 2. Definitions at the Enterprise Integration Patterns Level

### 2.1. Message Transformer: Converting Message Representation

A Transformer is a step that processes an inbound message and creates a message with **transformed content or structure**. For example:

- Parsing a JSON string into a record/domain DTO.
- Normalizing currency codes and converting amounts to `BigDecimal`.
- Converting a domain object into a payload suited for another system.
- Translating a record from an older schema version into a newer schema.
- Projecting a payload containing sensitive fields into a DTO holding only permitted outbound data.

Mental model:

~~~text
Input message
    -> transform(payload[, headers])
    -> Output message
~~~

On success, a Transformer produces **one result** for a normal input. Never use `null` to signify "skip processing." If the primary goal is keeping or dropping messages, use a **Message Filter** with an explicit discard policy.

### 2.2. Service Activator: Invoking a Service Operation

A Service Activator connects a message to **a business method or application service**:

- Inserting an order into a database.
- Sending emails, SMS messages, or notifications.
- Submitting a risk-assessment request.
- Triggering a domain service or calling an integration API.
- Querying status and returning a result.

Mental model:

~~~text
Input message
    -> invoke service operation
    -> [optional reply message]
~~~

A Service Activator **is not required** to return a reply. If the service method returns `void` or the endpoint returns `null` in one-way mode, completing the operation can be a **valid terminal point**.

Yet a Service Activator can also act as a **request/reply** step—such as placing an order and returning an `orderId`/receipt. Saying "a Service Activator never returns output" is therefore **false**.

### 2.3. Quick Comparison Table

| Aspect | Transformer | Service Activator |
| --- | --- | --- |
| Primary purpose | Transform payload/message representation | Invoke a service operation |
| Design question | "What shape should the data become?" | "What action should the system perform?" |
| Java DSL | `.transform(...)` | `.handle(...)` |
| Annotation | `@Transformer` | `@ServiceActivator` |
| Success result | Must produce a non-null result | May produce a reply or none |
| Returning `null` | Transformation error | Can be valid in one-way mode |
| Side effects | Avoid; prefer pure functions | Permitted and often the primary duty |
| Request/reply | Produces data in a conversion stage | Can return the outcome of a service call |
| Retry | Usually safe if pure | Must address idempotency of side effects |
| Threading | Determined by channel/endpoint | Determined by channel/endpoint |
| Transactions | Not transactional by itself | Not transactional by itself |
| Headers/correlation | Can preserve, modify, or add metadata | Can read headers and produce replies |
| Terminal position | Usually needs downstream to consume output | Can terminate a one-way flow |

**Pragmatic rule of thumb:** if removing the endpoint means **the outside world loses no business action**, it is usually a Transformer; if removing it prevents a business action from happening, it is usually a Service Activator. This is a design heuristic, not an absolute technical rule.

## 3. Null and Reply Contracts Are the Biggest Difference

### 3.1. A Transformer Must Not Return `null`

In Spring Integration, Transformers are built on a **reply-producing** contract: a successful transformation must yield output. Since Spring Integration 2.0, returning `null` from a Transformer is treated as an error raising **MessageTransformationException**, rather than silently making the message vanish.

~~~java
// Do not use this approach to filter messages.
String normalize(String text) {
    if (text == null || text.isBlank()) {
        return null;
    }
    return text.trim();
}
~~~

If blank text is **invalid input**, throw a clearly coded error:

~~~java
String normalize(String text) {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException("EMPTY_TEXT");
    }
    return text.trim();
}
~~~

If blank text is **allowed to be skipped**, use a Filter:

~~~java
IntegrationFlow.from("inputTextChannel")
        .filter(String.class, text -> !text.isBlank())
        .transform(String.class, String::trim)
        .channel("normalizedTextChannel")
        .get();
~~~

The example assumes channels are declared with proper consumers. The Filter must have a business-appropriate discard policy; never let important messages drop silently.

### 3.2. A Service Activator Can End One-Way

~~~java
IntegrationFlow.from("validatedOrdersChannel")
        .handle(NormalizedOrder.class, (order, headers) -> {
            orderService.place(order);
            return null; // No reply produced: one-way flow ends.
        })
        .get();
~~~

When the endpoint is the final step of a one-way flow, **returning no reply** is clean design. Never do this mid-flow if subsequent steps **depend on a reply** to continue.

### 3.3. A Service Activator Can Also Return a Reply

~~~java
IntegrationFlow.from("placeOrderRequestsChannel")
        .handle(NormalizedOrder.class,
                (order, headers) -> orderService.placeAndReturnReceipt(order))
        .channel("orderReceiptsChannel")
        .get();
~~~

When the service returns `PlacementReceipt` or another valid object, Spring Integration creates the output message and sends it to the output channel. This is still a **Service Activator**, because the business intent is **placing an order**; the reply is simply the service's result.

**Watch out with Gateways:** a synchronous Gateway waiting for a reply that hits a one-way Service Activator returning `null` may block until timeout or enter an error path depending on configuration. A Transformer returning `null` does not "return no result"; it is a transformation failure.

### 3.4. No Reply Differs from Unsuccessful Execution

A one-way handler can commit a database write successfully and return `null`; that **does not mean** the producer received a processing receipt. With `ExecutorChannel` or `QueueChannel`, `send()` returning true may only mean the message was accepted or queued.

If the caller needs certainty that the business action completed, design explicit **acknowledgements, replies, or durable status tracking** at the proper boundary. Changing a return type to `void` does not create delivery guarantees.

## 4. Where Do Both Endpoints Sit in a Pipeline?

A transparent order pipeline:

~~~mermaid
flowchart TD
    I["Ingress RawOrder"] --> V["Validation"]
    V --> T["Transformer<br/>RawOrder -> NormalizedOrder"]
    T --> F{"Filter<br/>should proceed?"}
    F -->|"Yes"| R{"Router<br/>STANDARD / REVIEW"}
    R --> S["Service Activator<br/>placeOrder"]
    R --> M["Service Activator<br/>requestReview"]
    S --> P["Order persisted"]
    M --> Q["Review request persisted"]
    V -.->|"Invalid"| E["Error / quarantine"]
    F -->|"Discard per policy"| D["Discard handler"]
~~~

Separation lets each component be tested independently:

- **Validation/Transformer:** input/output contracts and data errors.
- **Filter:** keep/drop decisions.
- **Router:** policy-based channel selection.
- **Service Activator:** business side effects and optional replies.
- **Gateway:** bridges Java request/reply method calls to flows.
- **Retry/error channel:** handles errors at the right boundaries.
- **Correlation:** tracks events across steps; does not prevent duplicates on its own.

An application service sometimes combines normalization and DB persistence. Separating a Transformer step is **not a ceremonial mandate**, yet it clarifies responsibility boundaries, reduces retry blast radius, and lets you measure conversion failure rates separately from downstream failures.

## 5. Building a Complete Example: `RawOrder` → `NormalizedOrder` → Place Order

The example uses Java 17+, Spring Framework, and Spring Integration Java DSL. To highlight the contrast cleanly, we use a **pure Java Transformer** and a **side-effecting service**; Spring endpoints act solely as messaging wiring.

### 5.1. Input and Output Models

~~~java
import java.math.BigDecimal;

record RawOrder(
        String eventId,
        String orderId,
        String amountText,
        String countryCode) {}

record NormalizedOrder(
        String eventId,
        String orderId,
        BigDecimal amountVnd,
        String countryCode) {}

record PlacementReceipt(
        String orderId,
        String status) {}
~~~

**RawOrder** represents unnormalized data. **NormalizedOrder** enforces the type contract for subsequent steps, yet **does not prove** the sender owns the order or tenant. Authentication and authorization belong at trust boundaries and services.

### 5.2. Pure Transformer Without Side Effects

~~~java
import java.math.BigDecimal;
import java.util.Locale;

final class OrderNormalizer {

    NormalizedOrder normalize(RawOrder raw) {
        if (raw == null) {
            throw new IllegalArgumentException("MISSING_ORDER");
        }
        if (raw.eventId() == null || raw.eventId().isBlank()
                || raw.orderId() == null
                || !raw.orderId().matches("ORD-[A-Za-z0-9-]{1,32}")) {
            throw new IllegalArgumentException("INVALID_IDENTIFIERS");
        }
        if (raw.amountText() == null || raw.amountText().isBlank()) {
            throw new IllegalArgumentException("MISSING_AMOUNT");
        }

        BigDecimal amount;
        try {
            amount = new BigDecimal(raw.amountText().trim());
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "INVALID_AMOUNT_FORMAT", ex);
        }
        if (amount.signum() <= 0
                || amount.stripTrailingZeros().scale() > 0) {
            throw new IllegalArgumentException("INVALID_AMOUNT_VALUE");
        }

        String country = raw.countryCode();
        if (country == null
                || !country.trim().matches("[A-Za-z]{2}")) {
            throw new IllegalArgumentException("INVALID_COUNTRY");
        }

        return new NormalizedOrder(
                raw.eventId(),
                raw.orderId(),
                amount,
                country.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

This function uses only its input and returns a result—no DB writes, HTTP calls, or emitted events. Identical valid `RawOrder` inputs produce identical results. In production, enforce monetary bounds, allowlisted country codes, and payload size caps; the two-letter regex here illustrates syntax checking only.

### 5.3. Service Performing the Operation

~~~java
interface OrderPlacementService {
    // Reply-producing operation: used for request/reply.
    PlacementReceipt placeAndReturnReceipt(NormalizedOrder order);

    // One-way operation: no reply needed when the contract only issues a command.
    void place(NormalizedOrder order);
}
~~~

The implementation layer may call repositories, transactions, outboxes, payment adapters, or other services. Consequently, the service needs **idempotency and proper business error handling**. The method signature defines only the contract; it does not implement deduplication by itself.

### 5.4. Spring Integration Java DSL Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class OrderFlowConfiguration {

    @Bean
    OrderNormalizer orderNormalizer() {
        return new OrderNormalizer();
    }

    @Bean
    MessageChannel rawOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel normalizedOrdersChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow normalizeOrders(OrderNormalizer normalizer) {
        return IntegrationFlow.from("rawOrdersChannel")
                .transform(RawOrder.class, normalizer::normalize)
                .channel("normalizedOrdersChannel")
                .get();
    }

    @Bean
    IntegrationFlow placeOrders(OrderPlacementService service) {
        return IntegrationFlow.from("normalizedOrdersChannel")
                .handle(NormalizedOrder.class, (order, headers) -> {
                    service.place(order);
                    return null; // One-way Service Activator.
                })
                .get();
    }
}
~~~

The flow runs as follows:

1. Producer sends `Message<RawOrder>` to **rawOrdersChannel**.
2. **Transformer** endpoint produces `NormalizedOrder`. If data is invalid, this step throws an exception.
3. The resulting message passes through **normalizedOrdersChannel**.
4. **Service Activator** endpoint invokes `orderPlacementService.place()`.
5. Service Activator returns `null`, so the one-way flow **ends** here.

This terminal stage must not be used as a flow **expecting a reply** from a Gateway. If clients need a receipt, use a Service Activator returning `PlacementReceipt` and wire `replyChannel`/`outputChannel` accordingly.

### 5.5. Adding Request/Reply Without Turning the Service into a Transformer

~~~java
// Added inside the @Configuration class above, with dedicated channels.
@Bean
MessageChannel orderPlacementRequestsChannel() {
    return new DirectChannel();
}

@Bean
MessageChannel orderPlacementReceiptsChannel() {
    return new DirectChannel();
}

@Bean
IntegrationFlow receiptFlow(OrderPlacementService service) {
    return IntegrationFlow.from("orderPlacementRequestsChannel")
            .handle(NormalizedOrder.class,
                    (order, headers) ->
                            service.placeAndReturnReceipt(order))
            .channel("orderPlacementReceiptsChannel")
            .get();
}
~~~

This is a **reply-producing Service Activator**. A consumer must receive receipts on `orderPlacementReceiptsChannel`. In Gateway flows, when the Gateway expects replies via the **`replyChannel`** header, design the reply-producing endpoint without an explicit `outputChannel` so the framework honors the request's `replyChannel`; ensure no intermediate channel blocks replies or returns `null`.

### 5.6. What Spring Integration Does Automatically vs. Does Not Do

| Behavior | Framework Handles | Application Must Still Implement |
| --- | --- | --- |
| Invoke transform or handle function | Yes | Ensure methods follow contract |
| Build reply message from returned payload | Yes | Define output/channel for replies |
| Manage channels and endpoints | Yes | Register valid topology/consumers |
| Enforce Transformer never returns null | Checks contract | Write valid data logic |
| Persist order results to database | No | Implement `OrderPlacementService` |
| Prevent duplicate orders on broker redelivery | No | Idempotency and transactions |
| Create transactions for every handler | No | Transaction manager/appropriate boundaries |
| Guarantee end-to-end exactly-once | No | Delivery/recovery architecture |

## 6. Using Annotations Instead of Java DSL

When organizing endpoints with annotations, Spring Integration provides **`@Transformer`** and **`@ServiceActivator`**. They express a method's role in the messaging flow, not merely decorative names.

~~~java
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.annotation.Transformer;
import org.springframework.stereotype.Component;

@Component
class AnnotatedOrderEndpoints {
    private final OrderNormalizer normalizer;
    private final OrderPlacementService placement;

    AnnotatedOrderEndpoints(
            OrderNormalizer normalizer,
            OrderPlacementService placement) {
        this.normalizer = normalizer;
        this.placement = placement;
    }

    @Transformer(
            inputChannel = "rawAnnotatedOrdersChannel",
            outputChannel = "normalizedAnnotatedOrdersChannel")
    public NormalizedOrder normalize(RawOrder raw) {
        return normalizer.normalize(raw);
    }

    @ServiceActivator(
            inputChannel = "normalizedAnnotatedOrdersChannel")
    public void place(NormalizedOrder order) {
        placement.place(order);
    }
}
~~~

This example requires declaring both channels, enabling annotation endpoint processing per Spring Integration setup, and providing an `OrderPlacementService` bean. Annotations wire methods into the flow; **they do not turn normalization into a side effect** or make a `void` method emit a receipt.

When placing **`@ServiceActivator`** on a method returning `PlacementReceipt`, the result can be sent to `outputChannel` or `replyChannel` as a request/reply step. Clarify whether callers await replies and how errors are reported.

### 6.1. An Identical Method Could Be Wired Two Ways

~~~java
NormalizedOrder invoke(RawOrder raw) {
    return normalizer.normalize(raw);
}
~~~

If wired as a Service Activator, technically it **can still return a reply** carrying `NormalizedOrder`. Design-wise, however, the method performs a **transformation**, so `@Transformer` expresses the contract better, enforces non-null checking, and keeps flow intent clear.

Conversely, if a method both inserts an order into the DB and returns `PlacementReceipt`, that is a **service operation**. Annotating it `@Transformer` just because "it produces output" hides side effects and creates replay hazards.

## 7. Payload, Message, and Header Propagation

A Spring Message consists of payload and `MessageHeaders`. Both Transformer and Service Activator can accept the payload, the full Message, or header values via method parameters depending on declaration. Avoid confusing **payload transformation** with **authority to alter routing metadata**.

### 7.1. Transformer Returning Payload vs. Returning `Message`

When a Transformer returns a payload:

~~~java
NormalizedOrder normalize(RawOrder raw) {
    return normalizer.normalize(raw);
}
~~~

The framework builds the result message and propagates headers per endpoint mechanics. In an authenticated flow, required headers like `businessCorrelationId`, trace context, or `replyChannel` may need to survive across hops.

A Transformer can also return **`Message<NormalizedOrder>`** to specify both payload and selected metadata:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<NormalizedOrder> normalizeMessage(
        Message<RawOrder> incoming) {
    NormalizedOrder output = normalizer.normalize(
            incoming.getPayload());

    return MessageBuilder.withPayload(output)
            .setHeader("normalizedSchemaVersion", 1)
            .build();
}
~~~

**Warning:** do not treat returning a new `Message` as a guaranteed way to wipe all old headers. Spring Integration applies header handling/propagation rules when building endpoint replies; test real outputs in your target version. To enforce a **trust boundary**, control the ingress adapter, retain only allowlisted metadata, and never let clients dictate `replyChannel`, `errorChannel`, `routingSlip`, or `trustedRoute`.

### 7.2. Service Activator Reading Headers for Action Context

~~~java
import org.springframework.messaging.MessageHeaders;

// This is a Java method invoked from .handle() or @ServiceActivator.
PlacementReceipt placeWithContext(
        NormalizedOrder order,
        MessageHeaders headers) {

    Object correlation = headers.get("businessCorrelationId");
    // Can record verified correlation into the audit context.
    return placement.placeAndReturnReceipt(order);
}
~~~

This snippet is illustrative; dependencies and correlation handling belong in the application. Tracing headers **do not prove authorization** or prevent duplicate events. The Service Activator must validate tenant, actor, permissions, and business state before executing side effects.

### 7.3. Correlation Across Splitter/Aggregator

If a Transformer sits between Splitter and Aggregator, **`correlationId`**, **`sequenceNumber`**, and **`sequenceSize`** headers may be essential for reassembling child results. If the Transformer returns `null` or throws on one child message, the Aggregator can **stall waiting for missing members** and needs group timeout/release strategies.

A Service Activator in the same spot can return a reply to participate in aggregation, or return `null` and **emit no item**. Placing a one-way Service Activator mid-pipeline when all replies are expected will therefore starve downstream aggregation.

| Position | Reply Behavior | Downstream Impact |
| --- | --- | --- |
| Transformer between Splitter/Aggregator | Must return a result | Every succeeding child message advances |
| Reply-producing Service Activator | Can return a result | Usable as a processing step producing results |
| One-way Service Activator | No reply | Valid only if pipeline needs no result at that spot |
| Filter dropping child message | Discards per policy | Group must be designed for missing members |

Never alter correlation headers arbitrarily just to unstick an Aggregator timeout. When partial success is required, design explicit success/failure result objects, group timeouts, and proper message stores.

## 8. `DirectChannel` and `ExecutorChannel` Do Not Change the Pattern

A common misconception is "Transformers are synchronous, Service Activators are asynchronous." That is **false**.

**Channels** and endpoint configuration dictate threading:

- **DirectChannel** dispatches to subscribers on the sending thread, usually propagating exceptions back to the caller.
- **ExecutorChannel** hands work to an executor, creating an async boundary; callers may get `send()` back before downstream completes.
- **QueueChannel** buffers messages until a poller or consumer picks them up, running downstream at a different time.
- Broker adapters apply ack, redelivery, and error handling per configuration.

~~~mermaid
flowchart TD
    P["Producer"] --> D{"Channel"}
    D -->|"DirectChannel"| ST["Transformer or Service Activator<br/>same thread"]
    D -->|"ExecutorChannel"| EX["Executor worker<br/>Transformer or Service Activator"]
    D -->|"QueueChannel"| Q["Poller picks up message"]
    Q --> WK["Transformer or Service Activator"]
    ST -->|"Exception"| C["Caller receives error"]
    EX -->|"Exception"| E["Error handler / ErrorMessage"]
    WK -->|"Exception"| E
~~~

### 8.1. If a Service Activator Returns `null` on `ExecutorChannel`

The method may finish its side effect and produce no reply. Yet **`send()` returning `true`** at the producer only means the message was accepted under channel semantics—it does not mean the side effect committed.

To know when business work finished, rely on receipts, durable status records, acknowledgements, or correlated outcome events—never infer completion from `send()`'s boolean return.

### 8.2. If a Transformer Throws on `ExecutorChannel`

Exceptions do not necessarily return to the producer thread; errors can route as **`ErrorMessage`** to a configured `errorChannel`. The same applies when a Service Activator fails across an async boundary.

**Do not assume** every synchronous error is published to the global `errorChannel`. On `DirectChannel`, exceptions normally unwind on the call stack; with Spring Integration pollers/executors, message-based error handling applies, though actual adapter/executor behavior must be tested.

## 9. Transactions and Side Effects: Where to Place Boundaries

A Transformer can be evaluated as **data in → data out**. With a pure function, re-running identical inputs creates no duplicate side effects.

A Service Activator invokes operations such as:

- `INSERT` an order.
- `UPDATE` inventory quantities.
- `POST` a charge to a payment gateway.
- Send an email.
- Publish an event to another system.

None of those actions are automatically safe against retries or redeliveries.

### 9.1. Transactions for a DB-Writing Service Activator

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class JdbcOrderPlacementService implements OrderPlacementService {
    private final OrderRepository orders;

    JdbcOrderPlacementService(OrderRepository orders) {
        this.orders = orders;
    }

    @Override
    @Transactional
    public void place(NormalizedOrder order) {
        // Repository must enforce a unique constraint/idempotency on eventId.
        orders.insertIfAbsent(
                order.eventId(),
                order.orderId(),
                order.amountVnd());
    }

    @Override
    @Transactional
    public PlacementReceipt placeAndReturnReceipt(
            NormalizedOrder order) {
        orders.insertIfAbsent(
                order.eventId(),
                order.orderId(),
                order.amountVnd());
        return new PlacementReceipt(order.orderId(), "ACCEPTED");
    }
}

interface OrderRepository {
    void insertIfAbsent(
            String eventId, String orderId, java.math.BigDecimal amountVnd);
}
~~~

This example assumes **OrderRepository** is backed by a real implementation with an appropriate unique constraint. `@Transactional` applies only when invoked through a properly configured Spring proxy/transaction manager. It does not roll back external non-DB APIs automatically.

**Idempotency must live where side effects occur.** If a broker redelivers the same `eventId`, the database should prevent duplicate rows. If two distinct logical events target the same `orderId`, business rules must specify update/duplicate-order semantics instead of treating `eventId` as a one-size-fits-all answer.

### 9.2. Should a Transformer Read from a Database?

It is not technically forbidden, yet if every transform must query a DB/HTTP service for enrichment, consider:

~~~text
RawOrder
  -> Pure Transformer (parse + normalize)
  -> Enricher / Gateway (reads external state)
  -> Router / Service Activator
~~~

Separating I/O lets you configure timeouts, retries, caching, circuit breakers, and observability at the exact step that needs them. If separation is impossible, document clearly that the Transformer is no longer pure, retries depend on external state, and tests must cover I/O failure modes.

### 9.3. External Payments Do Not Roll Back with the Database

A Service Activator might save `eventId` to the database and call a payment provider. If the payment provider already captured funds and the response drops, rolling back the DB transaction **does not refund the payment**.

To retry safely:

1. Generate a stable **logical payment operation ID**.
2. Pass a stable **idempotency key** to the provider if supported.
3. Persist **PENDING / COMPLETED / UNKNOWN** states per contract.
4. For ambiguous timeouts, query/reconcile rather than issuing a brand-new command with a new key.
5. Use outbox/inbox or durable brokers if recovery must survive restarts.

Neither `transform()` nor `handle()` creates **end-to-end exactly-once side effects** on its own. Design transaction and delivery boundaries per effect.

## 10. Retries: Differences in Consequences

### 10.1. Retrying a Pure Transformer

Given the same `RawOrder`, a pure `normalize()` writes no state; running twice yields the exact same output or error. Side-effect-wise, retrying is relatively safe—though retrying **deterministic bad data** like `INVALID_AMOUNT_FORMAT` remains pointless.

### 10.2. Retrying a Service Activator

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant S as Service Activator
    participant DB as Order DB
    P->>S: place(evt-500)
    S->>DB: INSERT order
    DB-->>S: Commit succeeded
    S--xP: Connection lost before reply
    P->>S: Retry place(evt-500)
    S->>DB: INSERT again?
    Note over DB: Unique key/idempotent service protects effect
~~~

**Re-invoking with the same message does not mean the effect may execute twice.** If a Service Activator sits under retry advice and the action committed before an exception fired, retrying can duplicate side effects.

### 10.3. Scope Retries as Narrowly as Useful

In a flow `Transformer → Service Activator → Router → Notification`:

- Parse errors must not trigger full-pipeline retries.
- Transient DB errors may retry at the DB operation if transactions/idempotency support it.
- Notification failures must not accidentally re-run an already-committed order placement.

With **`RequestHandlerRetryAdvice`**, attach advice only to the endpoint with recoverable failures and define explicit recovery/backoff. Never wrap an entire `IntegrationFlow` assuming every step is harmless to repeat.

## 11. Transformer Errors Differ from Service Activator Errors

| Error Type | Where It Originates | Handling Approach |
| --- | --- | --- |
| Malformed JSON or unparseable amount | Transformer | Reject/quarantine; rarely retry |
| Transformer returns `null` | Transformer | Transformation contract error |
| Unsupported `schemaVersion` | Transformer/validation | Quarantine until consumer upgrades |
| DB unavailable | Service Activator | Bounded retry; monitor transactions |
| Business rule forbids placing order | Domain service via Service Activator | Business rejection; no blind retry |
| Payment provider timeout | Service Activator or Gateway | Idempotency/reconciliation |
| One-way Service Activator returns no reply | Flow design | Valid if no reply is expected |
| Gateway times out waiting for reply | Request/reply integration | Check reply path and endpoint contracts |
| Downstream channel has no subscriber | Wiring/dispatch | Fix topology; do not mislabel as conversion error |

On synchronous paths, both exception types can unwind to the caller. On async paths, Spring Integration can emit an **`ErrorMessage`** per error channel mechanics. Classify failures by **component, root cause, and error code**, not just "send failed."

### 11.1. Error Channels Do Not Persist Messages Automatically

An `ErrorMessage` sent to `errorChannel` aids diagnostics; it does not provide a DLQ, replay, or exactly-once guarantees. If critical failed messages must survive restarts, use durable consumers, brokers, or a `MessageStore` with clear retry policies.

When ingress accepts untrusted data, never copy client-supplied **`errorChannel`** headers directly. That can redirect error routing, leak information, or suppress failures.

## 12. Gateways and Request/Reply: Using Reply-Producing Service Activators

A Gateway turns a Java method call into a request message, often expecting a matching reply. A Gateway **does not have to end at a Transformer**: the replying endpoint can be a Service Activator.

Example gateway interface:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
interface OrderGateway {
    @Gateway(requestChannel = "orderGatewayRequestsChannel")
    PlacementReceipt place(NormalizedOrder order);
}
~~~

Endpoint:

~~~java
@Bean
IntegrationFlow gatewayOrderFlow(OrderPlacementService service) {
    return IntegrationFlow.from("orderGatewayRequestsChannel")
            .handle(NormalizedOrder.class,
                    (order, headers) ->
                            service.placeAndReturnReceipt(order))
            .get();
}
~~~

In a Gateway context, the framework can use the request's **`replyChannel` header** when a handler returns a reply and the endpoint specifies no explicit `outputChannel`. Ensure component scanning/gateway registration, channel beans, and timeouts are configured; this snippet assumes a fully configured Spring messaging context.

**Never replace that endpoint with a one-way Service Activator** expecting the Gateway to magically know the order succeeded. Without a reply from the handler, callers wait until timeout or receive incomplete outcomes per contract.

### 12.1. Gateway Calling a Transformer to Normalize Before Replying?

Completely valid if the sole requirement is converting `RawOrder` to `NormalizedOrder` and returning the normalized data:

~~~text
Gateway<RawOrder, NormalizedOrder>
  -> Transformer
  -> replyChannel
~~~

When the requirement is **placing an order and returning a receipt**:

~~~text
Gateway<RawOrder, PlacementReceipt>
  -> Transformer
  -> Service Activator returning PlacementReceipt
  -> replyChannel
~~~

The second flow shows cleanly where side-effecting business work belongs. Never call a DB-writing service inside the Transformer merely to eliminate one endpoint.

## 13. Unit Testing the Transformer: No Spring Context Needed

Since the Transformer is pure Java, unit tests verify outputs and error codes without running Spring Integration.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderNormalizerTest {
    private final OrderNormalizer normalizer = new OrderNormalizer();

    @Test
    void convertsAmountAndUppercasesCountry() {
        RawOrder raw = new RawOrder(
                "evt-101", "ORD-101", "1250000", "vn");

        NormalizedOrder output = normalizer.normalize(raw);

        assertEquals("evt-101", output.eventId());
        assertEquals("ORD-101", output.orderId());
        assertEquals(new BigDecimal("1250000"), output.amountVnd());
        assertEquals("VN", output.countryCode());
    }

    @Test
    void malformedAmountFailsWithoutProducingOutput() {
        RawOrder raw = new RawOrder(
                "evt-102", "ORD-102", "abc", "VN");

        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> normalizer.normalize(raw));
        assertEquals("INVALID_AMOUNT_FORMAT", error.getMessage());
    }

    @Test
    void rejectsNegativeOrFractionalVnd() {
        IllegalArgumentException negative = assertThrows(
                IllegalArgumentException.class,
                () -> normalizer.normalize(
                        new RawOrder(
                                "evt-103", "ORD-103", "-10", "VN")));
        assertEquals("INVALID_AMOUNT_VALUE", negative.getMessage());

        assertThrows(IllegalArgumentException.class,
                () -> normalizer.normalize(
                        new RawOrder(
                                "evt-104", "ORD-104", "3.5", "VN")));
    }
}
~~~

Unit tests prove the conversion and bad-input handling; they **do not** prove both channels are wired together or that the Service Activator executed the right action.

## 14. Integration Testing: Transformer Emits Output, Service Activator Executes Effect

The example uses synchronous `DirectChannel`s and a recording test service. In production, the real service needs databases/APIs and matching idempotency.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TransformerServiceActivatorTest.Config.class)
class TransformerServiceActivatorTest {

    static class RecordingService implements OrderPlacementService {
        final List<String> calls = new CopyOnWriteArrayList<>();

        @Override
        public void place(NormalizedOrder order) {
            calls.add("one-way:" + order.eventId());
        }

        @Override
        public PlacementReceipt placeAndReturnReceipt(
                NormalizedOrder order) {
            calls.add("reply:" + order.eventId());
            return new PlacementReceipt(order.orderId(), "ACCEPTED");
        }
    }

    @Configuration
    @EnableIntegration
    static class Config {
        @Bean
        RecordingService service() {
            return new RecordingService();
        }

        @Bean
        MessageChannel rawTestInput() {
            return new DirectChannel();
        }

        @Bean
        MessageChannel receiptTestInput() {
            return new DirectChannel();
        }

        @Bean
        QueueChannel receiptTestOutput() {
            return new QueueChannel();
        }

        @Bean
        IntegrationFlow oneWayFlow(RecordingService service) {
            OrderNormalizer normalizer = new OrderNormalizer();
            return IntegrationFlow.from("rawTestInput")
                    .transform(RawOrder.class, normalizer::normalize)
                    .handle(NormalizedOrder.class, (order, headers) -> {
                        service.place(order);
                        return null;
                    })
                    .get();
        }

        @Bean
        IntegrationFlow replyFlow(RecordingService service) {
            return IntegrationFlow.from("receiptTestInput")
                    .handle(NormalizedOrder.class, (order, headers) ->
                            service.placeAndReturnReceipt(order))
                    .channel("receiptTestOutput")
                    .get();
        }
    }

    @Autowired
    @Qualifier("rawTestInput")
    MessageChannel rawInput;

    @Autowired
    @Qualifier("receiptTestInput")
    MessageChannel receiptInput;

    @Autowired
    @Qualifier("receiptTestOutput")
    QueueChannel receipts;

    @Autowired
    RecordingService service;

    @BeforeEach
    void reset() {
        service.calls.clear();
        while (receipts.receive(0) != null) {
            // Drain previous test's queue if context is reused.
        }
    }

    @Test
    void transformerFeedsOneWayServiceActivator() {
        RawOrder raw = new RawOrder(
                "evt-201", "ORD-201", "90000", "vn");

        assertTrue(rawInput.send(
                MessageBuilder.withPayload(raw).build()));

        assertEquals(List.of("one-way:evt-201"), service.calls);
    }

    @Test
    void malformedInputNeverCallsOrderService() {
        RawOrder raw = new RawOrder(
                "evt-202", "ORD-202", "not-a-number", "VN");

        assertThrows(RuntimeException.class,
                () -> rawInput.send(
                        MessageBuilder.withPayload(raw).build()));

        assertTrue(service.calls.isEmpty());
    }

    @Test
    void serviceActivatorCanProduceAReply() {
        NormalizedOrder order = new NormalizedOrder(
                "evt-203", "ORD-203",
                new java.math.BigDecimal("75000"), "VN");

        assertTrue(receiptInput.send(
                MessageBuilder.withPayload(order).build()));

        Message<?> response = receipts.receive(0);
        assertNotNull(response);
        PlacementReceipt receipt =
                (PlacementReceipt) response.getPayload();

        assertEquals("ORD-203", receipt.orderId());
        assertEquals("ACCEPTED", receipt.status());
        assertEquals(List.of("reply:evt-203"), service.calls);
        assertNull(receipts.receive(0));
    }
}
~~~

**What the tests prove:**

- Transformation emits a contract-compliant output received by the Service Activator.
- Invalid input fails transformation and **never calls the service**.
- A Service Activator can return a `PlacementReceipt` when designed for request/reply.
- A one-way Service Activator **needs no reply**.

This is only an in-memory Spring context integration test using `DirectChannel`. It **does not** prove idempotency under broker redelivery or transaction durability across restarts. To verify those properties, test real repositories/brokers with unique constraints and failover.

## 15. Counter-Example Test: Never Return `null` from a Transformer

A dedicated contract test flow can be structured like this:

~~~java
// Used only in error-contract tests; never deploy to production.
@Bean
IntegrationFlow illegalTransformerFlow() {
    return IntegrationFlow.from("illegalTransformInput")
            .transform(String.class, value -> (String) null)
            .channel("unusedOutput")
            .get();
}
~~~

When a `String` message enters `illegalTransformInput`, the `null` return must be treated as a transformation failure, not a Filter discard. Tests can assert `RuntimeException` and the appropriate root cause/wrapper for your Spring Integration version, while confirming `unusedOutput` receives nothing.

Never add a one-way Service Activator just to "swallow" Transformer errors: to drop messages conditionally, place a Filter before transformation or use an explicit discard/error flow.

## 16. Endpoint Selection Matrix in Real Scenarios

| Need | Appropriate Pattern | Reason |
| --- | --- | --- |
| Convert JSON String to `OrderDto` | Transformer | Changes data structure |
| Convert `amountText` to `BigDecimal` | Transformer | Normalizes data |
| Map schema v1 to schema v2 | Transformer | Changes message representation |
| Omit sensitive fields before outbound dispatch | Transformer | Projects to target schema |
| Keep/drop events conditionally | Filter | Not a data transformation |
| Pick channel for orders needing review | Router | Destination decision |
| Save order to database | Service Activator | Business side effect |
| Fetch quote from external service and return result | Gateway or reply-producing Service Activator | I/O-backed service invocation |
| Send SMS without waiting for reply | One-way Service Activator or SMS outbound adapter | Side-effecting command |
| Place order and return receipt | Reply-producing Service Activator | Business action returning a result |
| Send one event to multiple targets conditionally | Recipient List | Fan-out |
| Split an order into line items | Splitter | Produces multiple child messages |
| Combine multiple line-item results | Aggregator | Groups and releases results |
| Modify verified headers | Header Enricher/Transformer | Contract-driven metadata transformation |
| Call the same API repeatedly with retries | Service Activator/Gateway + Retry Advice | Retries require idempotency management |

### 16.1. Decision Flowchart

~~~mermaid
flowchart TD
    A{"What should the step do?"} -->|"Transform data only"| T["Transformer"]
    A -->|"Decide keep/drop only"| F["Filter"]
    A -->|"Select route"| R["Router"]
    A -->|"Invoke business operation"| S{"Is a reply needed?"}
    S -->|"No"| O["One-way Service Activator"]
    S -->|"Yes"| Q["Reply-producing Service Activator"]
    T --> N{"Might it return null?"}
    N -->|"Valid data might be absent"| G["Validate/Filter or fail upfront"]
    N -->|"No"| DONE["Return non-null output"]
~~~

When an operation both transforms data and causes side effects, prefer separating the two responsibilities if that clarifies error handling, retries, and transactions. Do not multiply endpoints purely out of dogma: if invoking one service and returning a DTO is a single cohesive business action, one reply-producing Service Activator fits naturally.

## 17. Common Pitfalls

### 17.1. Using a Transformer to Send Email

~~~java
// Anti-pattern: external service with side effects inside Transformer.
EmailPayload transform(OrderAccepted order) {
    emailClient.sendConfirmation(order);
    return new EmailPayload(order.orderId());
}
~~~

If the endpoint retries, the email can be sent twice. A cleaner design:

~~~text
OrderAccepted
  -> Transformer: OrderAccepted -> EmailCommand
  -> Service Activator / outbound adapter: send email
  -> Record status + dedicated idempotency/retry
~~~

Here `EmailPayload`, `EmailCommand`, and `emailClient` are illustrative names, not built-in Spring Integration APIs.

### 17.2. Using a Service Activator Instead of a Filter

~~~java
// Confusing style in a multi-step pipeline:
.handle(RawOrder.class, (raw, headers) ->
        isAllowed(raw) ? raw : null)
~~~

Returning `null` ends the one-way flow, yet readers cannot easily tell this is a **discard decision**, and there is no explicit discard policy. When the goal is dropping messages, use a Filter with proper logging/storage.

### 17.3. Using a Transformer Without Returning Valid Output

~~~java
.transform(RawOrder.class, raw ->
        raw.amountText() == null ? null : normalizer.normalize(raw))
~~~

A Transformer returning `null` does not trigger Filter discard—it violates the contract. Throw an explicit error or place a Filter upfront if skipping is permitted.

### 17.4. Returning the Wrong Reply Type and Expecting the Gateway to Understand

If a Gateway declares `PlacementReceipt` as its return type while a Service Activator returns an arbitrary `String`, the framework may fail conversion or throw mapping/casting errors depending on context. Test **reply types**, timeouts, and error handling.

### 17.5. Ignoring Correlation and Trusted Headers

A Transformer must not drop `businessCorrelationId` where tracing depends on it, nor copy control headers from unauthenticated clients. A Service Activator must never trust client-supplied `tenantId` or `role` headers as proof of authorization.

### 17.6. Equating One Send with One Commit

Synchronous `DirectChannel` dispatch does not wrap external systems in one transaction. Enqueuing on `QueueChannel` also does not mean consumers finished. Identify explicitly where acknowledgements are issued and where side effects commit.

### 17.7. Wrapping the Entire Flow in a Single Retry

If `Transformer → Place Order → Notification` succeeds at `Place Order` and fails at `Notification`, retrying from the start can re-invoke `Place Order`. Scope retries to recoverable steps and make side-effecting consumers idempotent.

## 18. Practice Exercise: Outbound Warehouse Shipment Processing

Design a flow accepting:

~~~java
record RawShipment(
        String eventId,
        String shipmentId,
        String weightGramsText,
        String destinationCountry) {}

record NormalizedShipment(
        String eventId,
        String shipmentId,
        long weightGrams,
        String destinationCountry) {}

record ShipmentReceipt(
        String shipmentId,
        String status) {}
~~~

Business contract:

1. Input contains weight as a string and an unnormalized country code.
2. Weight must be a positive integer within business-defined upper bounds.
3. Valid shipments must be **persisted** and **scheduled for delivery**.
4. Brokers may redeliver an event if a consumer crashes.
5. The system must return a receipt across synchronous Gateways, or publish status tracking in async flows.

**Implementation steps**

1. Write a pure Java **ShipmentNormalizer** taking `RawShipment` and returning `NormalizedShipment`, with no DB/HTTP calls.
2. Write unit tests for valid inputs, unparseable `weightText`, negative weight, over-limit weight, and invalid `countryCode`.
3. Create **ShipmentSchedulingService** with two methods: one-way `schedule()` and `scheduleWithReceipt()`.
4. Wire an `IntegrationFlow` with **`.transform()`** followed by **`.handle()`**; test Transformer output and service call counts.
5. Build a request/reply flow with a Service Activator returning `ShipmentReceipt`, verified via `QueueChannel` or Gateway replies.
6. Intentionally return `null` from the Transformer and observe the transformation error in an integration test.
7. Switch input to `ExecutorChannel` and inspect differences in exception/`ErrorMessage` handling.
8. Design an idempotency key using **`tenant + eventId + logicalActionId`** for scheduling.
9. Simulate a successful schedule followed by a lost reply; retries must not create two delivery schedules.
10. Add separate metrics for transform failures, service failures, and prevented duplicate side effects.

### Analysis Questions

1. Should a method that both parses weight and queries the DB be placed in a Transformer? Why or why not?
2. If analytics-only events must be dropped, is Filter or Transformer more appropriate?
3. Can a Service Activator return `ShipmentReceipt` without a trailing Transformer?
4. When a synchronous Gateway receives `null` from a Service Activator, what happens for the caller?
5. If a Service Activator already committed to the DB and downstream fails, what retry scope is appropriate?
6. Why does a Transformer returning `null` differ from a one-way Service Activator returning `null`?
7. Which headers must be controlled when HTTP requests enter the flow?
8. If a child message fails to produce output from a Transformer, how must an Aggregator handle it?

## 19. Pre-Release Checklist

- **Payload transformation** and **business operations** are cleanly separated.
- Transformer always returns non-null output on success; invalid input raises classified errors.
- Filter is used whenever the intent is **keeping or dropping** messages.
- One-way Service Activator is used only when no reply is needed at that stage.
- Reply-producing Service Activator has an explicit result contract for Gateways/downstream.
- Data types are explicit, avoiding ambiguous casts and mismatched reply types.
- Required reply/error/correlation headers are preserved within proper trust boundaries.
- Channel types match sync/async semantics and have real consumers.
- Transactions, retries, and idempotency protect critical side effects.
- Error channels and quarantine queues have real consumers/retention; never assume durability by default.
- Unit tests cover Transformers and integration tests cover all endpoint types.
- Tests cover invalid inputs, `null` returns, no-reply, and valid replies.
- Metrics/logs separate **transform** errors from **service operation** errors and **downstream dispatch** failures.

**Conclusion:** Both Transformer and Service Activator can look like functions taking a message and returning a result in Spring Integration, yet they express **two distinct contracts**. Use **Transformer** for data conversions that must emit output; use **Service Activator** to trigger service actions, with or without a reply. Separating responsibilities cleanly and defining explicit retry, transaction, and Gateway boundaries makes Router–Filter–Transformer–Service Activator flows far easier to test, observe, and recover.

## References

- [Spring Integration Reference — Message Transformers](https://docs.spring.io/spring-integration/reference/transformer.html): Transformer contracts, outputs, null results, annotations, and Java DSL.
- [Spring Integration Reference — Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html): service invocation, replies, and `MessageHandler`.
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html): request/reply and `replyChannel`.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): exceptions, `DirectChannel`, `ExecutorChannel`, and `ErrorMessage`.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): `.transform()`, `.handle()`, `IntegrationFlow`, and endpoints.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): channel semantics, transaction boundaries, and async dispatch.
- [Enterprise Integration Patterns — Message Translator](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html): conceptual foundation of Transformers.
- [Enterprise Integration Patterns — Messaging Adapter](https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingAdapter.html): bridging service applications with messaging systems.
