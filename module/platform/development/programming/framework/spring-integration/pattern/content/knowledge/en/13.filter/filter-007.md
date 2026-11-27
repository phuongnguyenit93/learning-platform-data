# Throw Exception on Rejection

## 1. The Problem: How Does the System Know When a Filter Rejects a Message?

In an order processing flow, a message arrives from HTTP, a broker, or a Gateway. A **Filter** must decide whether an order may proceed. For instance, an order must have an identifier and a positive quantity. For an invalid order, there are very different possible behaviors:

- Do not forward the message and **silently drop** it.
- Do not forward the message, but send it to a **discard channel** for recording and handling.
- **Throw an exception** so the caller or system error handling knows about the rejection.

In Spring Integration, the third option is controlled by `MessageFilter`'s `throwExceptionOnRejection` configuration. When the selector returns `false` and this flag is `true`, the Filter raises `MessageRejectedException`. This is an **intentional** error signal at the message boundary, not an accidental exception caused by buggy checking code.

**Key question:** is rejecting a message normal business behavior, or an error that the producer/poller must be notified about? There is no universal answer. Enabling exceptions in the wrong place can cause **endless retries of the exact same invalid message**, unnecessary transaction rollbacks, or a Gateway returning an error instead of a structured rejection result.

This lesson belongs to the **Filter** chapter of the **SPRING_INTEGRATION_PATTERN** module. The content supports learning to implement Enterprise Integration Patterns with Spring Integration: building loosely coupled message flows combining **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, while testing and observing processing branches.

After this lesson, you will understand default behavior versus throwing exceptions, how to configure it with Java DSL/annotations/XML, how it behaves in synchronous and asynchronous flows, interactions with transactions, advice, and discard channels, as well as how to test rejected messages without triggering unintended side effects.

## 2. Under Which Contract Does Filter Operate?

**Message Filter** implements the **Selective Consumer** pattern from Enterprise Integration Patterns. It reads a message and asks a **selector** whether the message is accepted. A typical selector takes the form of a pure function:

~~~java
record OrderRequest(
    String eventId,
    String orderId,
    Integer quantity
) {}

final class OrderGuard {
    public boolean accepted(OrderRequest order) {
        return order.eventId() != null
            && !order.eventId().isBlank()
            && order.orderId() != null
            && !order.orderId().isBlank()
            && order.quantity() != null
            && order.quantity() > 0;
    }
}
~~~

At the Filter:

| Selector result | Filter behavior |
|---|---|
| `true` | Forwards message to output channel; downstream handlers can proceed |
| `false`, default mode | Does not forward to output; sends to discard channel if configured, otherwise drops |
| `false` and `throwExceptionOnRejection=true` | Does not forward to output; raises `MessageRejectedException` |
| Selector itself throws exception | Runtime failure evaluating predicate; handled per exception/error policy |

One crucial distinction: **a selector returning `false`** is a valid outcome of the rule, whereas **a selector throwing an exception** may stem from wrong data types, bugs, timeouts, or external logic. Both can cause a flow to fail, yet they do not share the same root cause and should not necessarily share the same error code or retry strategy.

Filter is not Router. Filter answers "may the message proceed?", while Router answers "which branch should the message take?". If you need to distinguish multiple failure reasons such as `MISSING_FIELD`, `UNSUPPORTED_VERSION`, and `BUSINESS_REJECTED`, a **classifier + Router** is sometimes more useful than a single boolean predicate.

## 3. Three Ways to Handle Rejection

~~~mermaid
flowchart TD
    IN["orders.in"] --> F{"Filter selector"}
    F -->|"true"| OK["orders.accepted"]
    F -->|"false"| R{"Rejection policy"}
    R -->|"Default"| DROP["Drop message / no output"]
    R -->|"discardChannel"| DC["orders.rejected"]
    R -->|"throwExceptionOnRejection"| EX["MessageRejectedException"]
    EX --> ERR["Caller / error handler / transaction boundary"]
~~~

| Configuration | Message on output? | Discard message sent? | Exception when predicate=false? |
|---|---:|---:|---:|
| Default, no discard | No | No | No |
| `discardChannel("orders.rejected")` | No | Yes | No |
| `throwExceptionOnRejection(true)` | No | No, unless configured separately | Yes |
| **Both discard and throw** | No | **Yes** | **Yes, after discard action** |

The last row is very easy to misunderstand. According to `MessageFilter` behavior, if both `discardChannel` and `throwExceptionOnRejection=true` are configured simultaneously, **the message is still sent to the discard channel, and then the exception is still thrown**. It is not an *either/or* toggle. If the discard handler already persisted a record or published to a broker, and then an upstream transaction rolls back and retries, you may see **duplicate recordings of the same rejection**.

Do not enable both just because "you want to be sure failed messages are not lost". Decide what behavior you actually need: direct error feedback, routed rejection handling, or both under a contract with idempotency.

**Note on logging:** since Spring Integration 6.1, a default Filter with neither a discard channel nor exception throwing enabled may log a warning about discarded messages. Thus "silently dropped" describes routing semantics, **not a guarantee that logs are completely silent**.

## 4. Java DSL: Enabling `throwExceptionOnRejection(true)`

Keep examples concise with a concrete contract. Note that the configuration snippets below **are alternatives**; do not register multiple flows simultaneously on the same input to avoid competing subscribers.

~~~java
@Configuration
@EnableIntegration
public class RejectingOrderFlow {

    @Bean
    OrderGuard orderGuard() {
        return new OrderGuard();
    }

    @Bean
    IntegrationFlow rejectInvalidOrders(OrderGuard guard) {
        return IntegrationFlow.from("orders.in")
            .filter(OrderRequest.class, guard::accepted,
                spec -> spec.throwExceptionOnRejection(true))
            .channel("orders.accepted")
            .get();
    }
}
~~~

Here:

1. `orders.in` receives `OrderRequest`.
2. Filter calls `OrderGuard.accepted(order)`.
3. If the result is `true`, the message proceeds to `orders.accepted`.
4. If the result is `false`, the Filter throws `MessageRejectedException`; **no message** is emitted to `orders.accepted` from that branch.
5. Channel `orders.accepted` needs a real consumer, such as a Service Activator or a test channel; declaring a channel name without a handler does not form a complete business workflow.

The example uses a Java record (Java 17+) and Spring Integration Java DSL. Imports are omitted. When integrating, ensure application configuration scans the beans and includes the appropriate Spring Integration dependencies.

**Never** treat the Filter snippet above as a complete solution for inputs with arbitrary payloads. The typed filter overload assumes the message payload can be converted to `OrderRequest`. When the inbound protocol can send malformed JSON, `String`, or `byte[]`, decode and validate type/schema at the adapter or build a dedicated type gate **before** this predicate is invoked.

## 5. Comparing with Discard Channel in Java DSL

If the business wants to receive failed messages to record a `REJECTED` status **without throwing exceptions back to the producer**, configure discard:

~~~java
@Bean
IntegrationFlow routeInvalidOrdersToDiscard(OrderGuard guard) {
    return IntegrationFlow.from("orders.in")
        .filter(OrderRequest.class, guard::accepted,
            spec -> spec.discardChannel("orders.rejected"))
        .channel("orders.accepted")
        .get();
}

@Bean
IntegrationFlow processRejections() {
    return IntegrationFlow.from("orders.rejected")
        .handle(message ->
            System.out.println("Rejected order: "
                + message.getHeaders().getId()))
        .get();
}
~~~

The `processRejections()` snippet only illustrates logging. In production applications, the handler should record a **reason code** and event ID, use validated data, avoid logging raw sensitive payloads, and never assume `MessageHeaders.ID` is a stable event identifier across redeliveries.

**Important:** when using only `discardChannel`, everything can look like a successful `send()` to upstream. Therefore, never use the Boolean return value of `send()` to infer **that the order passed the Filter** or that a business handler committed. For a request–reply Gateway, a Filter producing no reply after rejecting can leave the caller waiting until timeout unless a suitable response flow exists.

## 6. If Both Discard and Throw Are Enabled, What Order Applies?

The configuration below **intentionally enables both**:

~~~java
.filter(OrderRequest.class, guard::accepted,
    spec -> spec
        .discardChannel("orders.rejected")
        .throwExceptionOnRejection(true))
~~~

When the predicate returns `false`, the Filter forwards the message to the discard channel and then **throws the exception**. Consequently:

- The message does not enter the success output.
- The discard consumer may execute side effects before upstream sees the exception.
- If a transaction spans the discard consumer and can roll back, side effects inside that same transaction may roll back; **this does not apply to all external systems**.
- If the discard consumer writes files, calls HTTP, or writes to another non-transactional store, upstream retries can write multiple copies.
- If the discard consumer itself throws an exception, the observed failure path may reflect the discard handling error rather than just the initial rejection.

To avoid confusion, pick one of two patterns:

**Pattern A – Rejection is business data:** route the message to a reject flow, persist a `REJECTED` outcome, and emit an appropriate response/event without throwing an exception that triggers upstream retries.

**Pattern B – Rejection is an error condition:** enable `throwExceptionOnRejection`, letting an error boundary translate it into an HTTP error, rollback, or controlled failure-handling flow.

Only combine both when you genuinely need **both to persist the discarded message and signal an error**, and you have designed idempotency, transactions, and monitoring for redelivery scenarios.

## 7. Configuring with Annotations and XML

Beyond Java DSL, Spring Integration provides an annotation for Filter:

~~~java
@Component
class AnnotatedOrderGuard {

    @Filter(
        inputChannel = "orders.in",
        outputChannel = "orders.accepted",
        throwExceptionOnRejection = "true")
    public boolean accept(OrderRequest order) {
        return order.quantity() != null && order.quantity() > 0;
    }
}
~~~

The annotation example uses the string `"true"` per Spring Integration's annotation attribute type. **This is an alternative** to the Java DSL flow in section 4. Do not declare both in the same test context unless you intentionally want multiple selective consumers and have designed the dispatcher accordingly.

In XML namespace configuration:

~~~xml
<int:filter input-channel="orders.in"
            output-channel="orders.accepted"
            ref="orderSelector"
            method="accept"
            throw-exception-on-rejection="true"/>
~~~

The `orderSelector` bean must provide the matching boolean-returning method; the XML namespace and bean must be declared in the Spring context. The default value of this attribute is `false`. If you use Spring Boot/Java DSL, XML is not required; this snippet helps when reading legacy project configurations.

## 8. What Exact Exception Is Thrown?

When the selector returns `false` and `throwExceptionOnRejection=true`, `MessageFilter` throws **`MessageRejectedException`**. It is a Spring Integration messaging exception carrying the rejected message context for diagnostics.

Distinguishing it from other errors:

| Situation | Outcome | Handling approach |
|---|---|---|
| Selector returns `false` | `MessageRejectedException` if flag enabled | Rejection policy |
| Selector calls method on `null` | May raise runtime exception/wrapper | Fix data/validator/predicate |
| Wrong payload type before selector | Type conversion or handler error | Type gate/contract validation |
| No consumer on output channel | Send/dispatch failure depending on channel | Check topology |
| Discard handler fails | Exception sending or handling discard | Discard flow's error path |
| Downstream consumer fails | Failure after Filter accepted | Consumer's retry/error policy |

**Never assume the exact exception always surfaces directly to the caller.** A Gateway, poller, or adapter can wrap it in another messaging exception or route it through an error channel. In tests, verify `MessageRejectedException` in the **cause chain** when frameworks/proxies add wrappers.

Exception contents and message text can change across versions; business logic should not classify errors by matching exact message strings. Use exception types or reason codes explicitly mapped by adapters.

## 9. Synchronous: Who Sees the Rejection?

With `DirectChannel`, handlers are typically dispatched **synchronously on the sender's thread**. If the Filter throws an exception, it can propagate back to the `send()` caller or Gateway.

~~~mermaid
sequenceDiagram
    participant C as Caller / Gateway
    participant IN as DirectChannel
    participant F as MessageFilter
    participant OUT as Accepted consumer
    C->>IN: send(OrderRequest)
    IN->>F: handleMessage
    F->>F: selector returns false
    F-->>IN: MessageRejectedException
    IN-->>C: exception (possibly wrapped)
    Note over OUT: No message from rejected branch
~~~

Example of an application with an HTTP command boundary:

~~~text
HTTP request
    -> adapter / Gateway
    -> DirectChannel
    -> Filter(throwExceptionOnRejection=true)
    -> exception reaches boundary
    -> mapped to appropriate error response
~~~

HTTP adapters/controllers **do not automatically convert every `MessageRejectedException` into `400 Bad Request`** under an immutable contract. You must configure exception → HTTP response mapping appropriately—for example, `422 Unprocessable Entity` for business validation, `403 Forbidden` for authorization checks, or another code per API contract.

A Filter rejection should not default to HTTP 500 when the application anticipated the rejection rule. However, selecting the HTTP status depends on error semantics and the public API contract, not solely on the exception class.

## 10. Asynchronous: Publishers May Never See the Filter Error

When a message passes through an `ExecutorChannel`, `QueueChannel` with a polling consumer, or a broker listener, the exception can happen **after the publisher already finished sending**. Therefore:

~~~mermaid
flowchart LR
    P["Publisher"] --> CH["Queue / Executor"]
    CH --> F{"Filter"}
    F -->|"true"| OK["Business handler"]
    F -->|"false, throw"| E["Exception"]
    E --> EH["Error handler / error channel"]
    EH --> DEC{"Recovery policy"}
    DEC -->|"Non-retryable"| DLQ["Quarantine / reject status"]
    DEC -->|"Transient"| R["Bounded retry + backoff"]
~~~

A successful `send()` call to a queue or executor **only proves work was accepted at that boundary**, not that the Filter accepted it or that all consumers completed.

**Context-dependent behavior:**

- A poller can use an appropriate error handler or publish an `ErrorMessage` to an error channel if configured.
- An executor can report errors through the asynchronous task's error path.
- An inbound broker adapter decides ack/nack/redelivery based on its listener container, error handler, and transaction boundary.
- Not every channel type automatically sends errors to a channel named `errorChannel` merely because that channel exists.

For **permanently** invalid inputs, you need a "non-retryable" classification to prevent a poison message from being replayed endlessly and clogging consumers. Specify the policy on the **right adapter/poller**, not just on the Filter.

## 11. Rejection and Transaction Rollback

One valid reason to enable `throwExceptionOnRejection` is **forcing a transactional unit of work to fail when the Filter rejects**.

For example, a message read from a transactional broker session or transactional poller:

~~~text
transaction begin
  → receive message
  → Filter selector = false
  → MessageRejectedException
transaction rollback (if exception escapes boundary and policy requires)
  → message may be redelivered
~~~

However, **throwing an exception does not automatically guarantee rollback**. A transaction rolls back only when:

1. The Filter step executes **inside the relevant transaction boundary**.
2. The exception reaches the transaction manager and is classified for rollback.
3. The adapter or message store supports the corresponding rollback/ack semantics.
4. No intermediate advice or error handler catches the exception and treats it as handled before the boundary.

A rollback can cause the message to **be redelivered**, depending on source and configuration. Without poison-message handling, the Filter will keep rejecting the same message forever. A sound strategy is bounding retries, routing to DLQ/quarantine, or converting into an observable business error.

**Do not roll back solely to inform callers of bad data** when the issue is permanent validation failure and the workflow already has an explicit rejection path. Transaction rollback is valuable for preserving atomicity of receive/process units, not as a replacement for business policy.

## 12. Combining Filter with Retry Advice: Beware Infinite Loops

Spring Integration supports advice around handlers, such as retry advice. When `throwExceptionOnRejection=true`, the Filter actively throws an exception; if advice is configured to retry **all exceptions**, the message can be re-evaluated repeatedly even though data never changes.

~~~mermaid
flowchart TD
    M["Contract-invalid message"] --> F["Filter: predicate false"]
    F --> E["MessageRejectedException"]
    E --> RETRY{"Does retry advice treat it as retryable?"}
    RETRY -->|"Yes, overly broad config"| F
    RETRY -->|"No"| REJECT["Reject / DLQ / error response"]
~~~

Recommended practices:

- Treat `MessageRejectedException` from **permanent validation** as **non-retryable**, unless the business expects an external condition to change.
- Retry transient failures, such as dependency disconnects in downstream handlers, with backoff and limits.
- Include controlled reason-code/event-ID metadata in error records; do not use raw exception messages as business keys.
- If a `RetryAdvice` wraps the Filter and discard flow, understand clearly when discard and exception execution occur relative to the advice scope.

**Key characteristic of Filter advice:** by default, rejection discard and exception actions execute **inside the advice chain**. Hence, if retry advice catches rejection exceptions, **each attempt may re-execute discard side effects**.

Spring Integration offers `discardWithinAdvice(false)` to move discard/exception actions **outside** the advice scope. This is not an "automatic fix for all retries"; you still must design the retry policy and understand the effects when the Filter stops a message from proceeding.

## 13. When to Use `discardWithinAdvice`?

Here is an illustrative configuration for a Filter with both discard and throw:

~~~java
.filter(OrderRequest.class, guard::accepted,
    spec -> spec
        .discardChannel("orders.rejected")
        .throwExceptionOnRejection(true)
        .discardWithinAdvice(false))
~~~

**Meaning:** `discardWithinAdvice(false)` shifts the boundary of discard and exception actions relative to the advice chain **applied to the Filter itself**. If retry advice is present, the rejection step runs after the advised portion, so it does not occur as a retryable exception inside the normal advised handler invocation.

This is a technical decision about **where the error is raised**; never use it to hide errors or assume transactions always commit/rollback in one fixed way. Real tests must check:

1. How many times was the selector evaluated?
2. How many times did the discard handler receive the same event?
3. When does the caller/poller see the exception?
4. Does the transaction span the discard handler?
5. Does the error message include the rejected message and proper correlation?

**Do not configure both out of habit.** Most use cases should pick either intentional discard or intentional exception. `discardWithinAdvice` is for specific cases involving advice where side-effect boundaries must be controlled.

## 14. Point-to-Point Channels with Multiple Selective Consumers

An advanced scenario: multiple Filters registered as **competing selective consumers** on the same point-to-point channel, such as a `DirectChannel`. Each Filter accepts only one subset of messages.

~~~text
orders.in (point-to-point)
    ├── Filter A: accepts market=VN only
    └── Filter B: accepts market=US only
~~~

If the dispatcher picks Filter A for a US message:

- When A **silently drops**, the dispatcher may consider that dispatch **handled**, leaving Filter B with no chance to receive the US message.
- When A **throws `MessageRejectedException`**, the dispatcher **can** try another subscriber according to the configured failover strategy.

Spring Integration documentation cites this as one reason to use `throwExceptionOnRejection=true` with multiple Selective Consumers. However, there is **no guarantee** subscriber B will always be tried: you must check how the dispatcher selects handlers, failover configuration, subscriber count, and which exceptions qualify for retry/failover.

If the actual requirement is choosing **one branch by `market`**, a **Content-Based Router** mapping `VN → orders.vn` and `US → orders.us` is usually clearer, easier to test, and more observable than relying on dispatcher failover to probe multiple Filters.

**Distinction:** multiple subscribers on a `PublishSubscribeChannel` follow a fan-out model, whereas multiple subscribers on a `DirectChannel` are point-to-point; do not carry the "every Filter gets called" assumption from pub/sub into point-to-point.

## 15. Handling Missing/Wrong-Type Inputs Before Filter

When messages arrive from HTTP, Kafka, or AMQP, you cannot assume every payload is already a valid `OrderRequest`.

Common failure examples:

| Input | Sure predicate ran? | How to handle |
|---|---|---|
| Malformed JSON syntax | No, error may occur in adapter/deserializer | Ingress decode error |
| Payload is `String` instead of `OrderRequest` | Unlikely, may fail type conversion | Type gate/schema rejection |
| `orderId=null` | Yes if DTO still parses | Predicate false |
| `quantity=null` | Yes if field is nullable | Predicate false |
| `quantity=-3` | Yes | Predicate false |
| Valid payload lacking authorization | Should not rely solely on a regular Filter | Authorization boundary |
| Broker redelivery of same event | Predicate may run multiple times | Idempotency + recovery policy |

**Recommended design:** decode → schema/type validation → business Filter → Transformer/Router → downstream handler. If you want separate exception policies for decoding and validation, classify errors at each stage rather than expecting every input error to become `MessageRejectedException`.

A predicate **should not query a database or make HTTP calls for every message** when it can stay pure Java and fast. If external data is required, extract it into an independent service/handler with clear timeouts and retries; the Filter only reads the resolved result.

## 16. Gateway Request–Reply and Rejection Results

Consider a Gateway sending an order to a Filter and awaiting a result:

~~~java
@MessagingGateway(defaultRequestChannel = "orders.in")
public interface OrderGateway {
    OrderReceipt submit(OrderRequest order);
}
~~~

If the Filter **silently drops**, the Gateway does not automatically receive `OrderReceipt(REJECTED)`. Depending on timeout and config, the caller may hang or receive null/error with no reply. If the Filter **throws**, the caller can receive the messaging exception directly or wrapped.

If the API requires **returning a structured business result**, there are two directions:

- **Exception boundary:** enable throw, map `MessageRejectedException` to an API error without exposing internal stack traces/messages to clients.
- **Business outcome:** before replying, classify `ACCEPTED/REJECTED` into a dedicated `OrderReceipt` object; only use Filter if dropping a branch does not break expected replies.

Example business result type:

~~~java
public record OrderReceipt(
    String orderId,
    String status,        // ACCEPTED / REJECTED
    String reasonCode
) {}
~~~

If the business requires a receipt for **every protocol-valid input**, using a classifier or Router that produces both reply types can feel more natural than a Filter throwing exceptions. Never design an API that infers Filter acceptance merely from "the HTTP request did not time out".

## 17. Error Channel and What `ErrorMessage` Should Contain

When a Filter throws an exception in a context with an error handler, the framework can build an `ErrorMessage` wrapping the original exception. The error path should preserve diagnostic context without leaking sensitive data:

~~~text
ErrorMessage
    ├─ exception type: MessageRejectedException
    ├─ failedMessage / eventId (if preserved)
    ├─ input channel, endpoint name
    ├─ trace / correlation context
    └─ application-classified reason code
~~~

Failed messages and cause chains can vary due to wrappers and adapters; tests should not rely on a single rigid exception structure across all sources.

**Never auto-retry** every `ErrorMessage`. Rejections from permanent validation differ from transient network failures. With AMQP/Kafka, deciding nack, offset commit, requeue, DLQ, or skip depends on the adapter/container and configured policy; throwing an exception in Filter is only **one signal**, not the entire delivery semantics.

## 18. Correlation, Splitter, and Aggregator When Filter Rejects

Suppose an order is split by a **Splitter** into three line items, and a Filter rejects an invalid line before the **Aggregator**:

~~~mermaid
flowchart LR
    ORD["Order O-101"] --> SPLIT["Splitter"]
    SPLIT --> L1["Line 1"]
    SPLIT --> L2["Line 2: invalid"]
    SPLIT --> L3["Line 3"]
    L1 --> FIL{"Filter"}
    L2 --> FIL
    L3 --> FIL
    FIL -->|"Accepted"| AG["Aggregator"]
    FIL -->|"Rejected + throw"| ER["Error handling"]
    AG --> RES["OrderResult?"]
~~~

If the initial sequence size is 3 yet one line never reaches the Aggregator, the group may **wait forever for missing members**. When the Filter throws an exception:

- In synchronous flows, the exception can halt emitting subsequent lines.
- In asynchronous flows, other lines may already be processing and the Aggregator receives an incomplete group.
- If the whole order must fail whenever any line is invalid, apply a fail-fast rule before the Splitter or use a coordinator handling failure outcomes.
- If per-line outcomes are allowed, convert rejections into a **failure result** carrying the correlation ID so the Aggregator combines both accepted and rejected lines.

**Do not manually hack `sequenceSize`** just to avoid timeouts before the business defines release rules. Design release strategy, group timeout, expired-message handling, and deduplication.

Intentionally preserve `correlationId`, event ID, and sequence numbers across Transformers/adapters; never use newly generated message IDs on redelivery as unique business keys.

## 19. Testing Exception Throwing Directly

With an integration test running in a Spring context containing `RejectingOrderFlow` and a test consumer on `orders.accepted`, you can verify rejected messages as follows:

~~~java
@SpringJUnitConfig(classes = RejectingOrderFlow.class)
class FilterRejectionTest {

    @Autowired
    ApplicationContext context;

    @Test
    void rejectsInvalidQuantityWithMessagingException() {
        MessageChannel input = context.getBean(
            "orders.in", MessageChannel.class);

        Message<OrderRequest> invalid = MessageBuilder
            .withPayload(new OrderRequest("E-1", "O-1", -1))
            .build();

        assertThrows(MessagingException.class,
            () -> input.send(invalid));
    }
}
~~~

Note that this illustrative test **checks only the `MessagingException` family** to tolerate wrappers; add an assertion searching for `MessageRejectedException` in the cause chain for your project's framework version. In synchronous flows, `orders.in` must be wired to the Filter handler via configuration. To test the happy path, provide a consumer on `orders.accepted` via a `QueueChannel` in **test-only configuration**, avoiding sending accepted messages to an output channel with no subscriber.

Valuable tests:

| Case | Input | Expected result |
|---|---|---|
| Valid | `quantity=2`, complete IDs | Accepted channel receives message |
| Negative quantity | `quantity=-1` | `MessageRejectedException` or wrapper containing it |
| Null quantity | `quantity=null` | Rejection, not `NullPointerException` |
| Missing orderId | `orderId=null` | Rejection |
| Missing eventId | `eventId=""` | Rejection |
| Throw disabled | Predicate false | No exception; default/discard per config |
| Discard only | Predicate false | Rejected channel receives, accepted does not |
| Both discard + throw | Predicate false | Discard receives and caller sees exception |
| Predicate throws exception | Bug/type error | Not mistaken for valid rejection |
| Downstream consumer fails | Predicate true, handler fails | Classified as downstream error |

Avoid tests that only assert `send() == true`. A default Filter can drop messages without raising an exception, so that check **does not prove** the business step processed anything.

## 20. Testing Retry, Transaction, and Error Paths

Integration tests should mirror production paths:

1. **Synchronous DirectChannel:** verify the exception propagates to the producer/Gateway and the accepted handler is not called.
2. **Async executor/queue:** verify `ErrorMessage` or the error handler receives the rejection, without expecting the publisher to catch the exception directly.
3. **Discard + throw:** count how many times the discard consumer runs; if retry advice exists, verify `discardWithinAdvice` behavior.
4. **Transaction:** use a real transactional resource to verify rollback; do not claim rollback happened merely because a test caught an exception.
5. **Broker redelivery:** verify non-retryable validation policy, DLQ/quarantine, and absence of infinite retries.
6. **Idempotency:** arriving multiple times with the same `eventId` records business results/rejections according to policy.
7. **Splitter/Aggregator:** one rejected item does not leave the group waiting indefinitely without a timeout or failure result.

For concurrency tests, use latches, test channels, and finite timeouts. Never rely on fixed `Thread.sleep` durations or accidental thread scheduling order.

## 21. Observing and Diagnosing Rejections

An operations team must clearly separate intentional Filter rejections from error exceptions:

| Recommended signal | Explanation |
|---|---|
| `filter.accepted.count` | Number of messages passing the predicate |
| `filter.rejected.count` | Number of messages discarded by Filter |
| `filter.rejection.exception.count` | Number of cases throwing `MessageRejectedException` |
| `filter.discard.count` | Number of messages sent to discard channel |
| `filter.predicate.error.count` | Number of errors evaluating the selector |
| `filter.downstream.error.count` | Failures after Filter already accepted |
| `consumer.retry.count` | Retries grouped by error type |
| `dlq.count` and backlog | Messages awaiting investigation/remediation |

These are **suggested metric names**, not claims of built-in Spring Integration meters. With Micrometer/observation, add bounded endpoint and reason-code tags; avoid using `orderId`/`eventId` as metric tags due to high cardinality. Keep specific IDs in access-controlled tracing/logs.

When a message goes "missing" after a Filter, inspect in order:

~~~text
Ingress decode/type
   → Filter selector result
   → throwExceptionOnRejection?
   → discardChannel?
   → channel/caller error handling
   → transaction/retry decision
   → DLQ/quarantine or business result
~~~

At each point, identify when it happened and who owns the decision. A producer seeing an error does not prove no side effects happened; a producer seeing `send()` succeed does not prove the Filter accepted the message.

## 22. When to Enable and When Not To?

| Goal | Recommendation | Reason |
|---|---|---|
| Request–reply needs explicit error on invalid data | Consider **throw** and map to API error | Caller gets error signal instead of waiting |
| Want to record rejected messages for investigation | **discard channel** with an owner | Does not force upstream rollback |
| Want to drop irrelevant telemetry | Do not throw; discard/null channel works | Dropping is expected behavior |
| Transaction must roll back when selector rejects | **throw**, plus rollback policy | Exception informs transaction boundary of failure |
| Poison message on broker | Never retry infinitely; pair with non-retryable recovery | Validation errors rarely self-heal |
| Multiple Selective Consumers on point-to-point channel | Consider throw + tested dispatcher failover | Can give another handler a chance to receive |
| Orders need `ACCEPTED/REJECTED` result in every case | Classifier/Router producing business result | Boolean Filter + drop can lose replies |
| One branch of Aggregator rejected | Failure result or group failure policy | Avoid hanging for missing members |

**Rule of thumb:** an **expected** rejection does not have to be an exception. Only enable `throwExceptionOnRejection` when an upstream component **needs the error signal**, and you know exactly what behavior that signal triggers.

## 23. Common Mistakes

**"Predicate returning false means an exception."** False. By default Filter may drop or discard; only when the flag is enabled does it raise `MessageRejectedException` on rejection.

**"Having a discard channel means it won't throw."** False. If both are configured, the message can be discarded **and** the exception still thrown afterward.

**"Enabling throw automatically sends messages to `errorChannel`."** False. Error paths depend on channel type, caller, adapter, poller, and error handler.

**"Enabling throw automatically rolls back transactions."** False. The exception must actually escape and cross a transaction boundary with matching rollback rules.

**"Every exception should be retried."** False. Predicate false from invalid data is usually permanent; retrying creates poison messages.

**"Filter false and a bug in the predicate are the same."** False. Intentional rejection differs from evaluation/schema bugs.

**"Gateway getting `send()==true` means the order was accepted."** False. Acceptance at the channel boundary differs from business acceptance.

**"Discard + throw never causes duplicate side effects."** False. If discard writes outside the transaction before the exception triggers a retry, records can be duplicated.

**"Filter is the best way to return multiple reason codes."** Not necessarily. Use a classifier/Router or result type when structured rejection reasons are needed.

## 24. Practice Exercise

Build an **OrderAdmission** flow consisting of:

1. **Gateway/producer** sending `OrderRequest(eventId, orderId, quantity)`.
2. **Filter** using `OrderGuard.accepted()` to check required fields.
3. **Case A:** use default Filter, test a rejected order, observe whether any reply arrives.
4. **Case B:** use `discardChannel("orders.rejected")` with a consumer counting rejections.
5. **Case C:** enable `throwExceptionOnRejection(true)` and verify the exception.
6. **Case D:** enable both discard and throw to observe discard running before the exception; test again with retry advice.
7. **Error handling:** separate `MessageRejectedException` from downstream handler timeouts; configure non-retryable policy for bad data.
8. **Transaction:** test a transactional poller/adapter; verify when exceptions trigger rollback and message redelivery.
9. **Splitter/Aggregator:** one order line is rejected; design a failure result or group timeout.
10. **Observability:** measure accepted, rejected, discard, exception, retry, and DLQ; correlate via event ID/correlation.

**Completion criteria:** include a table demonstrating the three modes (default/discard/throw) differ; test both `false` and selector exceptions; explicitly document which thread/boundary receives exceptions, retry policy, idempotency, and final caller-observable state.

## 25. Key Takeaways

**`throwExceptionOnRejection=true`** turns a **Filter selector returning `false`** into **`MessageRejectedException`**. It lets upstream know a message was rejected and can drive dispatch failover, rollback, or error handling **when those boundaries are configured accordingly**. This flag does **not** automatically supply HTTP error mapping, error channels, retry policies, or transaction rollbacks.

Distinguish **silent drop**, **discard channel**, and **exception**, especially since discard and throw **can happen together**. Choose a contract consistent with your Gateway, broker, Filter/Router/Transformer, Splitter/Aggregator, retry, error channel, and correlation so invalid messages are handled intentionally without infinite retries or lost business outcomes.

### References

- Spring Integration Reference, **Filter**: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration API, **MessageFilter**: https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/filter/MessageFilter.html
- Spring Integration API, **FilterEndpointSpec**: https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/dsl/FilterEndpointSpec.html
- Spring Integration Reference, **Advising Filters**: https://docs.spring.io/spring-integration/reference/handler-advice/advising-filters.html
