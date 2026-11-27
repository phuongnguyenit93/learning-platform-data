# Selecting Methods Without Unintended Side Effects

## 1. The problem: message hits the right channel yet invokes the wrong behavior

An order-processing system has multiple methods related to `Order`:

~~~java
class OrderOperations {
    OrderPreview preview(PreviewOrderQuery query) {
        // Compute estimated fee without persisting data.
        return calculatePreview(query);
    }

    OrderReceipt place(PlaceOrderCommand command) {
        // Persist order and emit event.
        return saveOrderAndPublish(command);
    }

    void cancel(CancelOrderCommand command) {
        // Cancel the order.
        performCancellation(command);
    }
}
~~~

If a Service Activator is loosely configured, changes signatures, has overloads, or routes the wrong message, the result can be:

- A request meant **only to preview** ends up **placing an order**.
- Retrying the same `PlaceOrderCommand` causes the system to **decrement inventory twice**.
- A method returning `null` leaves a Gateway **waiting until timeout**, even though the handler executed a side effect.
- A validation error is caught and returns success, causing the broker to ACK unprocessed input.
- A message with a spoofed header is used to select a write/cancel method.

~~~mermaid
flowchart TD
    I["Incoming Message"] --> SEL{"Select method to invoke"}
    SEL -->|"Explicit, matching command"| VALID["Validate & authorize"]
    SEL -->|"Wrong method/payload type"| WRONG["Unintended side effect"]
    VALID -->|"Valid"| TX["Business handler with transaction/idempotency"]
    VALID -->|"Invalid"| REJ["Reject with reasonCode"]
    TX --> RES["Reply / durable outcome"]
    WRONG --> INCIDENT["Double write / accidental cancel / lost work"]
~~~

A **Service Activator** in Enterprise Integration Patterns connects a **message** to a **method/service** that executes processing. In Spring Integration, it can be configured via `@ServiceActivator` or Java DSL `.handle(...)`. **Selecting the method** is a **routing/invocation** concern, whereas **preventing unintended side effects** requires business contracts, validation, authorization, transactions, idempotency, and error handling.

This lesson belongs to the **Service activator** chapter in the **SPRING_INTEGRATION_PATTERN** module. The module teaches Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows—practicing **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, while testing and observing execution branches.

After this lesson, you will choose handlers explicitly, understand overload and parameter-binding risks, separate queries from commands, constrain side effects, design safe retry/ACK policies, and write tests proving messages never accidentally trigger write-capable business methods.

## 2. What does a Service Activator actually do?

In a message flow:

~~~text
Inbound adapter
  → Channel
  → [Service Activator → application method]
  → Reply channel / next step
~~~

A Service Activator:

1. Receives a message from its **input channel**.
2. Resolves the configured **method/handler**.
3. Maps **payload, headers, or the full `Message`** into matching arguments.
4. Invokes application logic.
5. If an appropriate return value exists, may emit a **reply message**.
6. If the method throws an exception, errors follow the active **synchronous/asynchronous boundary**.

A Service Activator **does not automatically guarantee** the called method is read-only, transactional, or idempotent. Whether a method is `void`, returns an object, or throws an exception is part of the endpoint contract, not proof of safety.

Example of an order-creation command:

~~~text
Channel orders.place
   ↓
Service Activator: OrderCommandHandler.place(PlaceOrderCommand)
   ↓
Database transaction + outbox
   ↓
OrderReceipt
   ↓
orders.place.result
~~~

Here the channel and method have **one clear purpose**. Never lump `preview`, `place`, and `cancel` into one endpoint without strictly controlled command selection rules.

## 3. “No unintended side effects” does not mean “no side effects”

A Service Activator invoking a business service **may need legitimate side effects**. For example:

- Persisting an authorized order.
- Decrementing inventory for a logical operation.
- Recording a controlled audit entry.
- Writing an outbox event to publish after commit.

What must be prevented are side effects **outside the message/contract's intent**:

| Side effect | When legitimate? | When anomalous? |
|---|---|---|
| `INSERT` order | Valid, authorized `PlaceOrderCommand` | `PreviewOrderQuery` routed to `place` |
| `UPDATE` inventory | Committed, idempotent operation | Retry of same event decrements twice |
| Publish event | Via outbox / confirmed outcome | Published before commit, then transaction rolls back |
| HTTP payment call | Authorized with idempotency key | Invoked merely to validate input |
| Send email | Explicit business intent/consent | Read-only query sends notifications |
| Write audit | Sanitized data with retention | Raw PII payload logged endlessly |
| Delete record | Verified `CancelOrderCommand` | Method chosen via untrusted header |

**Design goal:** the handler chosen **matches the message's intent**, performs only permitted effects, and handles errors/retries without duplicating already-committed effects.

## 4. Three layers that must all be right together

A safe endpoint needs all three:

| Layer | Question | Measure |
|---|---|---|
| **Invocation correctness** | Does the message map to the right method? | Explicit handler/method, clear payload type, avoid ambiguous overloads |
| **Business correctness** | Is the method allowed to do this? | Validate command, tenant, operation, state, and authorization |
| **Delivery correctness** | Do retries, redeliveries, or crashes cause double effects or lost work? | Transactions, idempotency, outbox, ACK/DLQ/retry policies |

Locking down method selection without idempotency fails to stop double writes. Having transactions while misrouting a method can still **atomically commit the wrong behavior**.

## 5. Naming channels and handlers by operation

Avoid generic catch-all channels like:

~~~text
orders.operations
  → OrderService (method guessed from payload/header)
~~~

where readers cannot even tell which operations are callable.

An easily governed topology:

~~~text
orders.preview  → OrderQueryHandler.preview
orders.place    → OrderCommandHandler.place
orders.cancel   → OrderCommandHandler.cancel
~~~

Methods with side effects should sit behind **dedicated command endpoints with separate permissions**, keeping query/read-only endpoints separated from write paths.

**Channel names do not replace authorization.** If an external producer can send straight into `orders.cancel`, the system still needs permission checks. Trusting channel names alone is a flawed security decision.

## 6. Java 17: commands and results with distinct types

Example:

~~~java
record PlaceOrderCommand(
    String tenantId,
    String commandId,
    String orderId,
    List<OrderLine> lines
) {}

record OrderLine(
    String sku,
    int quantity
) {}

record OrderReceipt(
    String orderId,
    String commandId,
    String status
) {}

record PreviewOrderQuery(
    String tenantId,
    String orderId
) {}

record CancelOrderCommand(
    String tenantId,
    String commandId,
    String orderId,
    String reasonCode
) {}

record OrderPreview(
    String orderId,
    BigDecimal estimatedTotal
) {}
~~~

`commandId` represents the **logical operation**; keep it constant across broker redeliveries and retries. It differs from `MessageHeaders.ID`, which is the ID of a Spring message instance.

Separating `PreviewOrderQuery` from `PlaceOrderCommand` prevents picking the wrong method by payload. If both query and command reused `OrderDto`, a small annotation or config change could make a query call a write method.

**Distinct DTO types alone do not make it safe**: still validate trusted `tenantId`, `orderId`, line counts, quantities, authorization, and valid state. Never let a client-supplied `tenantId` bypass principal verification.

## 7. Option A: `@ServiceActivator` placed on the exact method

A command-handling endpoint:

~~~java
@MessageEndpoint
class PlaceOrderEndpoint {
    private final OrderCommandHandler handler;

    PlaceOrderEndpoint(OrderCommandHandler handler) {
        this.handler = handler;
    }

    @ServiceActivator(
        inputChannel = "orders.place",
        outputChannel = "orders.place.result")
    public OrderReceipt place(PlaceOrderCommand command) {
        return handler.place(command);
    }
}
~~~

Strengths:

- Only `place(PlaceOrderCommand)` is annotated for this input channel.
- Does not ask the framework to guess among multiple overloads on a service.
- Input has a concrete type.
- Return value is `OrderReceipt`, giving downstream/Gateways a meaningful result.
- Endpoint is easy to test by sending `PlaceOrderCommand` to `orders.place`.

**Note:** this is **one configuration option**; do not simultaneously register the annotated endpoint and another Java DSL `.handle(...)` consuming the same channel without an intentional dispatch design. With `DirectChannel` and multiple subscribers, behavior is competing dispatch rather than running all subscribers.

## 8. Option B: Java DSL `.handle(bean, "methodName")`

When specifying the method name explicitly:

~~~java
@Configuration
@EnableIntegration
class PlaceOrderFlow {

    @Bean
    IntegrationFlow placeOrderFlow(
            OrderCommandHandler orderHandler) {
        return IntegrationFlow.from("orders.place")
            .handle(orderHandler, "place")
            .channel("orders.place.result")
            .get();
    }
}
~~~

Idea: the endpoint is configured to invoke **`place`** on a specific bean, instead of letting a component search among ambiguous candidates.

To avoid overload ambiguity, keep **one matching `place(PlaceOrderCommand)` method** on this bean. Specifying the method name **reduces ambiguity**, yet if the bean has multiple overloads **with the same name**, the framework still has to pick a signature matching payload/message and conversion rules.

**Never take the method name directly from an untrusted header** like `headers.operationMethod`. Methods capable of writing or canceling must never become a reflection API chosen by clients.

## 9. Option C: Java DSL typed handler lambda

When a small flow performs a single operation, use a typed handler:

~~~java
@Bean
IntegrationFlow typedPlaceFlow(
        OrderCommandHandler orderHandler) {
    return IntegrationFlow.from("orders.place.typed")
        .handle(
            PlaceOrderCommand.class,
            (command, headers) -> orderHandler.place(command))
        .channel("orders.place.typed.result")
        .get();
}
~~~

Characteristics:

- Payload type is stated right in the DSL.
- The lambda invokes **one concrete method** directly.
- Does not depend on framework selection among identically named methods on a bean.
- Headers can extract **already-verified context**, never alter the operation.

This snippet is a Spring Integration Java DSL pattern; verify overloads and imports for your version. It **does not add authorization/transactions by itself**: business logic must live in a Spring-managed service with dedicated controls.

Do not register examples 7, 8, and 9 simultaneously on **the same input channel** unless competing endpoints are intended.

## 10. Overloaded methods: why are they hard to control?

Consider a bean:

~~~java
class AmbiguousOrderService {
    OrderReceipt handle(PlaceOrderCommand command) {
        return placeOrder(command);
    }

    OrderPreview handle(PreviewOrderQuery query) {
        return previewOrder(query);
    }

    Object handle(Object anyPayload) {
        return fallbackOperation(anyPayload);
    }
}
~~~

If an endpoint configures `handle(service, "handle")`, overload selection can be influenced by **runtime payload types, method resolution, and conversion rules**. A message mis-deserialized as a `Map` or `String` can hit the `Object` overload instead of being rejected.

Worse, if the fallback method **has side effects**, an out-of-contract input can still execute an unwanted action.

Recommendations:

1. Never combine **preview**, **place**, and **cancel** under one overloaded method name relying on implicit selection.
2. Use distinct operation names or separate handler beans.
3. Configure endpoints with **one concrete payload type and method**.
4. Never put write logic in an `handle(Object)` fallback.
5. When type conversion is used, test that invalid payloads are **rejected**, not coerced into calling the wrong method.

**Never assume a specific overload will be picked by Spring across every version/configuration.** Test the real endpoint and avoid designs relying on guesswork.

## 11. Never let input specify which method to invoke

Anti-pattern:

~~~text
headers.methodName="cancelAllOrders"
payload={...}
    ↓
Generic reflection-based invoker
    ↓
orderService[headers.methodName](payload)
~~~

When headers come from external HTTP/brokers, this can become an **arbitrary method invocation vulnerability** or severe routing bug. Never let callers supply bean names, class names, SpEL expressions, or method names for arbitrary evaluation.

Instead, use an **allowlist mapping operation → channel/handler**:

~~~text
operation=PREVIEW → orders.preview  → preview(query)
operation=PLACE   → orders.place    → place(command)
operation=CANCEL  → orders.cancel   → cancel(command)
otherwise         → reject UNSUPPORTED_OPERATION
~~~

**The Router picks the channel; the Service Activator invokes the method fixed to that channel.** The Router must verify message type, source/tenant, and permissions before forwarding to write-capable commands. An operation enum never replaces authorization.

## 12. Binding parameters: payload, header, or full `Message`?

Spring Integration supports common handler signatures:

~~~java
@ServiceActivator(inputChannel = "orders.simple")
public OrderReceipt place(PlaceOrderCommand command) {
    return handler.place(command);
}
~~~

or:

~~~java
@ServiceActivator(inputChannel = "orders.verified")
public OrderReceipt placeVerified(
        @Payload PlaceOrderCommand command,
        @Header("verifiedTenantId") String verifiedTenantId) {
    authorization.verifyTenant(command, verifiedTenantId);
    return handler.place(command);
}
~~~

or accepting the full message:

~~~java
@ServiceActivator(inputChannel = "orders.full-message")
public OrderReceipt placeFromMessage(
        Message<PlaceOrderCommand> message) {
    PlaceOrderCommand command = message.getPayload();
    String tenant = (String) message.getHeaders()
        .get("verifiedTenantId");
    authorization.verifyTenant(command, tenant);
    return handler.place(command);
}
~~~

These are **independent options**, not three endpoints deployed together in one production flow. Regarding headers:

- `@Header` extracts a header value, yet **trust it only** when an internal adapter verified it and blocked external spoofing.
- `@Payload` marks the payload parameter, clarifying the method contract.
- `Message<T>` fits when both payload **and** metadata like correlation are needed.
- Avoid using a generic `Map<String,Object>` for every command when a concrete model can be declared.

**Header presence does not mean header verification.** Enforce authorization at the business boundary rather than trusting how a `Message` was constructed.

## 13. Select methods by command type, not accidental argument order

A clean handler has a stable name and signature:

~~~java
OrderReceipt place(PlaceOrderCommand command)
~~~

An opaque handler:

~~~java
Object handle(Object payload, Map<String, Object> headers)
~~~

Drawbacks of overly generic signatures:

- Type mismatches are not caught at compile time.
- Logic relies on `instanceof`/casts inside the method.
- Hard to audit whether the method writes to DBs or publishes events.
- Easy for fallback branches to trigger on payloads from new schemas.
- Input test matrix becomes much harder.

When supporting multiple message types, let **Router/Normalizer/Transformer** handle types/formats first and deliver a canonical command to the Service Activator. **Never turn a Service Activator into a dynamic dispatcher knowing every schema, operation, and side effect.**

## 14. Command–Query Separation: read-only methods and write methods must stay separate

A query:

~~~java
@Service
class OrderQueryHandler {
    private final OrderReadRepository orders;

    OrderQueryHandler(OrderReadRepository orders) {
        this.orders = orders;
    }

    public OrderPreview preview(PreviewOrderQuery query) {
        return orders.preview(query.tenantId(), query.orderId());
    }
}
~~~

A command:

~~~java
@Service
class OrderCommandHandler {
    private final OrderWriteRepository orders;
    private final OrderAuthorization authorization;

    OrderCommandHandler(
            OrderWriteRepository orders,
            OrderAuthorization authorization) {
        this.orders = orders;
        this.authorization = authorization;
    }

    public OrderReceipt place(PlaceOrderCommand command) {
        authorization.verifyCanPlace(command);
        return orders.place(command);
    }
}
~~~

The repository/authorization services above are **application abstractions**, not built-in Spring Integration beans. Here they only illustrate **permissions and responsibilities**, not a complete transaction/idempotency setup.

**Query endpoints** must never silently write to ledgers, decrement stock, issue invoices, or send emails. Recording observability metrics/audits is a permissible technical side effect, provided it is **bounded and triggers no new business behavior**.

**Command endpoints** may write, and must own transactions, retries, and idempotency. Separating the two makes code reviews and tests catch unintended side effects easily.

## 15. “Hidden” side effects that method selection never catches

A method named `validate()` sounds read-only, yet:

~~~java
boolean validateAndReserve(PlaceOrderCommand command) {
    inventory.reserve(command.lines());
    return true;
}
~~~

The method **reserves inventory** right inside validation. If a Filter calls it for a `true/false` check, a retried message can place multiple reservations before even reaching the main handler.

Hard-to-spot side effects:

- `validator.isValid()` calling an API to create a missing customer.
- `mapper.normalize()` calling `save()` to cache as a business record.
- `toString()`, getters, or lazy ORM access triggering unintended I/O.
- A “preview” method emitting an `OrderCreated` event.
- Pre-method advice/interceptors storing a dedup marker that **does not roll back** when the handler fails.
- A retry callback re-running an HTTP `POST` when the remote side lacks idempotency.
- An exception handler writing a fake `SUCCESS` result to ACK the broker.

Rule: explicitly distinguish **pure validation**, **read-only query**, **business command**, **external side effect**, and **audit/diagnostic**. Never bundle everything under a generic method name hoping callers know the internals.

## 16. Validate input before touching repositories or remote services

A pure validation service:

~~~java
@Service
class PlaceOrderValidator {
    void validate(PlaceOrderCommand command) {
        if (command == null) {
            throw new InvalidCommandException("MISSING_COMMAND");
        }
        if (command.commandId() == null
                || command.commandId().isBlank()) {
            throw new InvalidCommandException("MISSING_COMMAND_ID");
        }
        if (command.orderId() == null
                || command.orderId().isBlank()) {
            throw new InvalidCommandException("MISSING_ORDER_ID");
        }
        if (command.lines() == null
                || command.lines().isEmpty()
                || command.lines().size() > 100) {
            throw new InvalidCommandException("INVALID_LINES");
        }
        for (OrderLine line : command.lines()) {
            if (line == null
                    || line.sku() == null
                    || line.sku().isBlank()
                    || line.quantity() <= 0) {
                throw new InvalidCommandException(
                    "INVALID_ORDER_LINE");
            }
        }
    }
}
~~~

`InvalidCommandException` is an application exception carrying a stable reason code. This validator **writes to no database, calls no external API, and emits no messages**, so repeated calls from Filters or pre-handlers never mutate business state.

**Never equate validation with authorization.** Input with all fields valid can still target another tenant or violate permissions. Authorization must obtain principal/tenant from a trusted context; never let clients self-declare `tenantId` and act freely.

Byte-size, nesting-depth, and line-count limits should be enforced **at ingress before deserialization/fan-out**, since object-level validators cannot stop all resource exhaustion attacks.

## 17. Protect write methods with authorization at a trusted boundary

A handler must verify **whether the caller is permitted to execute the operation**:

~~~java
interface OrderAuthorization {
    void verifyTenant(
        PlaceOrderCommand command, String verifiedTenantId);
    void verifyCanPlace(PlaceOrderCommand command);
    void verifyCanCancel(CancelOrderCommand command);
}
~~~

In a real implementation, the service may read the security principal from Spring Security context or a verified identity envelope with provenance; it must verify:

- The tenant context genuinely belongs to the sender.
- `orderId` belongs to the authorized tenant.
- The operation is allowed in the current business state.
- Whether the sender has only `PREVIEW` permission or `PLACE/CANCEL` permission.
- Broker/HTTP headers cannot spoof internal identity.

When Spring Integration moves messages across an executor or broker, thread-local security context **does not propagate automatically**. If relying on context for authorization, configure trusted context propagation or carry verified identity inside an envelope with a strict contract and integrity protection.

**Picking the right method is not authorization.** A properly typed `CancelOrderCommand` must still be denied if the caller lacks cancel permissions.

## 18. Transaction boundaries must cover side effects in the same database

An implementation for the `PLACE` command:

~~~java
@Service
class TransactionalOrderCommandHandler {
    private final PlaceOrderValidator validator;
    private final OrderAuthorization authorization;
    private final ProcessedCommandRepository inbox;
    private final OrderWriteRepository orders;
    private final OutboxRepository outbox;
    private final CommandFingerprint fingerprint;

    TransactionalOrderCommandHandler(
            PlaceOrderValidator validator,
            OrderAuthorization authorization,
            ProcessedCommandRepository inbox,
            OrderWriteRepository orders,
            OutboxRepository outbox,
            CommandFingerprint fingerprint) {
        this.validator = validator;
        this.authorization = authorization;
        this.inbox = inbox;
        this.orders = orders;
        this.outbox = outbox;
        this.fingerprint = fingerprint;
    }

    @Transactional
    public OrderReceipt place(PlaceOrderCommand command) {
        validator.validate(command);
        authorization.verifyCanPlace(command);

        String hash = fingerprint.canonicalHash(command);
        boolean first = inbox.insertIfAbsent(
            command.tenantId(),
            command.commandId(),
            "PLACE",
            hash);

        if (!first) {
            inbox.assertSameFingerprint(
                command.tenantId(),
                command.commandId(),
                "PLACE",
                hash);
            return inbox.loadCommittedReceipt(
                command.tenantId(),
                command.commandId(),
                "PLACE");
        }

        OrderReceipt receipt = orders.create(command);
        outbox.recordOrderPlaced(command, receipt);
        inbox.saveReceipt(
            command.tenantId(),
            command.commandId(),
            "PLACE",
            receipt);
        return receipt;
    }
}
~~~

The interfaces `ProcessedCommandRepository`, `OutboxRepository`, `CommandFingerprint`, and their methods are **application-implemented contract examples**, not Spring Integration APIs. Key ideas:

1. Validate/authorize before business writes.
2. Only one transaction claims `(tenant, commandId, operation)` thanks to a **database unique constraint**.
3. Write order, outbox, and receipt **inside the same transaction**.
4. If an exception occurs before commit, **roll back both marker and business changes**.
5. If the broker redelivers after commit, return the saved receipt—**never create the order a second time**.
6. If the same key arrives with a different payload hash, raise **idempotency key conflict** rather than accepting silently.

**Prerequisite:** inbox, order repository, and outbox must share **the same database transaction/transaction manager**. `@Transactional` does not automatically include Redis or HTTP side effects in the same atomic commit.

## 19. Why use an outbox instead of publishing directly inside the transaction?

An error-prone implementation:

~~~java
@Transactional
public OrderReceipt place(PlaceOrderCommand command) {
    OrderReceipt receipt = orders.create(command);
    eventPublisher.publish(new OrderPlaced(command.orderId()));
    return receipt;
}
~~~

If the broker send succeeds and the database rolls back, downstream receives an event **for an order that does not exist**. If the database commits and the process crashes before sending, downstream **never receives the event**.

**Transactional Outbox** writes the event-intent record in the same transaction as the order:

~~~text
BEGIN
  INSERT processed_command
  INSERT orders
  INSERT outbox_event
COMMIT
  → Outbox publisher reads and sends
  → Downstream consumers deduplicate by eventId/outboxId
~~~

An outbox **does not stop the broker from receiving duplicates** if the publisher crashes after sending yet before marking published. It keeps publish intent durable and retryable; consumers still need idempotency.

**Permitted side effects must have clear boundaries.** If a Service Activator is designed only to save an order and outbox row, it should not tack on email sending, payment charging, and publishing to two brokers without an explicit workflow/transaction protocol.

## 20. Methods with `@Transactional` can still bypass the proxy

A common bug:

~~~java
@Service
class UnsafeOrderService {
    public OrderReceipt place(PlaceOrderCommand command) {
        return doPlace(command); // self-invocation
    }

    @Transactional
    public OrderReceipt doPlace(PlaceOrderCommand command) {
        // Writes inbox + order.
        return writeOrder(command);
    }
}
~~~

With Spring's default transaction proxy, internal calls like `this.doPlace(...)` bypass the proxy, preventing `@Transactional` from creating the expected transaction.

A cleaner design: have the **Service Activator invoke a Spring-managed transactional service bean directly**, never instantiate handlers manually via `new`, and never bury transactions behind private methods/self-calls.

Also, Spring's default rollback rules apply primarily to unchecked exceptions; if using checked exceptions, configure rollback rules explicitly. Avoid catching exceptions and returning success, which lets the transaction commit a marker even though business failed.

**`@Transactional(readOnly=true)` is not a security guarantee forbidding all writes**; it is a transaction hint/config whose enforcement varies by persistence provider/DB. Query handlers must **never call write methods by design**, backed by tests and DB permissions where needed.

## 21. Retries after handler failure: methods can be invoked multiple times

In message-driven environments, `at-least-once delivery` is the norm. Failure example:

~~~text
T1 Broker delivers PlaceOrderCommand commandId=C-801.
T2 Handler writes order and commits.
T3 Process crashes before ACK.
T4 Broker redelivers C-801.
T5 Handler is invoked a second time.
~~~

**Never assume “one message = one method invocation.”** The guarantee to aim for is **one logical operation never produces duplicate side effects**.

| Failure point | What must be guaranteed |
|---|---|
| Before transaction | Safe to retry |
| After claiming marker, before commit | Marker rolls back or stays retryable |
| After DB commit, before broker ACK | Deduplication returns `duplicate completed` |
| During HTTP `POST` to remote | Outcome may be unknown; use remote idempotency/reconcile |
| After event publish, before marking sent | Downstream deduplicates |
| When retries are exhausted | DLQ/recovery plan; never return fake success |

RetryAdvice or broker redelivery can trigger **the same method multiple times**. Handler designs must tolerate that rather than relying on an in-JVM `boolean handled` flag.

## 22. Ordering Retry Advice and Idempotent Receiver does not replace proper transactions

Two wrapping orders:

~~~text
RetryAdvice(
    IdempotentAdvice(
        ServiceActivator.handle()
    )
)

IdempotentAdvice(
    RetryAdvice(
        ServiceActivator.handle()
    )
)
~~~

If an `IdempotentReceiverInterceptor` using `MetadataStoreSelector` **marks “seen” before the handler**, outer-layer retries can see the marker and treat subsequent attempts as duplicates **even though the earlier handler failed**.

Putting `RetryAdvice` inside helps in-process retries reach the handler, yet **if retries exhaust while the marker remains**, broker redeliveries can still be blocked. **Swapping advice order alone does not fix marker semantics.**

Safer solutions:

- Make markers and business side effects **atomic inside one DB transaction**, or
- Use an inbox with `PROCESSING/FAILED_RETRYABLE/SUCCEEDED` states, leases/fencing, and clear recovery; or
- For external side effects, use remote idempotency keys and reconciliation.

Verify any advice-chain behavior against your exact Spring Integration version and selector/metadata-store setup. **Never assume an interceptor rolls back a marker** if its storage lives outside the transaction.

## 23. External side effects are not rolled back by JDBC

A handler:

~~~text
BEGIN database transaction
  INSERT order
  HTTP POST /payment/capture
  UPDATE local order status
COMMIT
~~~

If the remote side captured payment yet the client timed out, the local transaction may roll back while money was already charged. A retry sending an HTTP request **with a new key** can charge again.

**Principles**:

1. Use a **stable business idempotency key**, sending the same remote key across all retries when supported by the provider.
2. Persist durable operation intent and outcome state.
3. Distinguish `FAILED_RETRYABLE` from `UNKNOWN_OUTCOME`.
4. On timeouts after external calls, **reconcile** instead of assuming the remote side did nothing.
5. Never add remote charges inside query/preview/validation methods.
6. Split operations into workflow steps with compensation where the domain permits.

If a provider offers no idempotency/query API, never auto-retry dangerous commands like charge/refund on timeout; require a verification protocol or manual review.

## 24. `void`, `null`, and Service Activator reply contracts

A one-way handler:

~~~java
@ServiceActivator(inputChannel = "audit.events")
public void audit(AuditEvent event) {
    auditSink.record(event);
}
~~~

This fits when upstream **does not expect a reply**. However, if a synchronous Gateway calls through a `void` endpoint expecting a result, the caller can **time out**, even though the side effect ran.

Another case:

~~~java
public OrderReceipt place(PlaceOrderCommand command) {
    orders.create(command);
    return null; // No response for the Gateway to receive.
}
~~~

A `null` return never produces a successful reply. Define explicitly:

- **Request–reply:** return a typed result, or throw an exception mapped properly.
- **One-way:** never assume a caller awaits a reply; handle delivery/recovery per adapter.
- **Async accepted:** may return `ACCEPTED/PENDING` once durable intent is persisted, never a fake business `SUCCEEDED`.
- **Command failure:** throw an exception or return a structured terminal outcome; never catch and return a fake receipt.

**Business side effects and replies are two separate events.** A Gateway timeout does not cancel an in-flight backend transaction/HTTP call; caller retries must preserve the same command ID.

## 25. Synchronous vs. asynchronous: the invocation boundary decides who sees errors

~~~mermaid
flowchart TD
    IN["Incoming message"] --> B{"Channel boundary"}
    B -->|"DirectChannel/sync"| H1["Handler on caller thread"]
    B -->|"ExecutorChannel/async"| H2["Handler on worker thread"]
    H1 -->|"Exception"| C["Caller / Gateway exception path"]
    H2 -->|"Exception"| EC["Error channel / container handler"]
    H1 -->|"Return"| R1["Synchronous reply"]
    H2 -->|"Return"| R2["Async reply or completion"]
~~~

If a Service Activator throws on a synchronous `DirectChannel`, the error normally propagates back to the sender/Gateway. With `ExecutorChannel` or a broker/poller, upstream `send()` may return before the handler runs; errors belong to **the worker/container error boundary**, not automatically thrown back to the caller.

**Never place `@Transactional` on the caller expecting transactions to span across worker threads.** Transaction contexts are typically thread- and manager-bound; put the transaction boundary on the service actually invoked by the worker.

A test catching an exception from `input.send()` on a `DirectChannel` does not prove how an async flow sends `ErrorMessage`s or ACKs a broker.

## 26. Message headers do not replace permissions or business identity

A message carries:

~~~text
headers.verifiedTenantId=tenant-a
headers.businessCorrelationId=tenant-a|O-801|revision-2
headers.traceId=...
headers.replyChannel=<temporary channel>
payload.commandId=C-801
~~~

Distinguish:

- `commandId`: idempotency of the logical command.
- `businessCorrelationId`: workflow grouping such as Order → children/replies.
- `traceId`: flow observability, never permissions.
- `replyChannel`: return address, usually temporary and never serialized across brokers.
- `MessageHeaders.ID`: ID of the message object, which can change after Transformers/replays.
- `verifiedTenantId`: trustworthy **only when attached and protected by an authenticated adapter**.

Never use `traceId` as an idempotency key; retries with different traces are still the same logical command. Never let `businessCorrelationId` decide whether a user can cancel or place an order.

**When messages cross brokers/Transformers**, header mapping can drop metadata. Identities needed for recovery must live in the wire contract or a durable mapping; never trust all Spring headers to survive every hop.

## 27. Command handlers must be independent of delivery count

Good model:

~~~text
Receive logical command C-801
  → validate/authorize
  → transactional inbox claim
  → apply side effect + write outbox
  → commit
  → reply/ACK

Redelivery C-801
  → same fingerprint + committed inbox
  → cached receipt / duplicate completed
  → no new business side effect
~~~

Dangerous model:

~~~text
Receive C-801
  → in-memory HashSet.add(C-801)
  → HTTP charge
  → local DB update
  → crash

Restart/redelivery
  → HashSet empty
  → charge again
~~~

Across multiple instances, a per-JVM `HashSet` is unsynchronized, non-durable across restarts, and not a distributed idempotency store. Use durable unique constraints/inboxes or protocols with proper atomic claims.

## 28. What should Router, Filter, and Transformer do before the Service Activator?

An intentional flow:

~~~mermaid
flowchart LR
    IN["Incoming command"] --> PARSE["Decode + schema validation"]
    PARSE --> FILTER["Filter: structural acceptance"]
    FILTER --> ROUTER["Router: operation"]
    ROUTER --> TRANS["Transformer: canonical command"]
    TRANS --> ACT["Service Activator: explicit method"]
    ACT --> OUT["Business reply / outbox"]
~~~

| Endpoint | Role | Must NOT do |
|---|---|---|
| **Filter** | Check continuation conditions, reject malformed inputs | Execute reserve/charge inside predicates |
| **Router** | Select channel/branch for verified operations | Invoke arbitrary methods from headers |
| **Transformer** | Normalize payload/type, keep needed IDs | Create payments/save orders while converting types |
| **Service Activator** | Invoke service method with clear business contract | Guess operations or handle arbitrary raw schemas |
| **Gateway** | Request–reply interface over message flows | Treat timeouts as proof of command rollback |
| **Splitter** | Split one message into child messages | Assume each child is automatically authorized |
| **Aggregator** | Collect outcomes by correlation/release policy | Fabricate fake successes for missing children |

**Separating duties does not forbid all method calls in Routers/Filters/Transformers**, but keeps their logic **pure and predictable**, never triggering unauthorized business side effects.

If a Filter must query a database for a business rule, distinguish **negative business answers** from **database timeouts**. Never catch a timeout and return `false`, permanently rejecting a valid message.

## 29. Splitter/Aggregator: each child needs its own method and idempotency key

An order:

~~~text
PlaceOrder C-801
  → Splitter
      → Line L1 → inventory.reserveOneLine
      → Line L2 → inventory.reserveOneLine
      → Line L3 → inventory.reserveOneLine
  → Aggregator
  → PlaceOrderResult
~~~

Do not use **the exact same idempotency key `C-801`** for all three children if receivers deduplicate by that key; the first child would cause the next two to be treated as duplicates.

A suitable child key:

~~~text
tenantId + parentCommandId + operation + lineId
~~~

In addition:

- `correlationId` groups results back to one parent.
- `lineId` identifies each member of the group.
- `sequenceNumber/sequenceSize` expresses position/child count per topology.
- `attemptId` tracks retry attempts, **not child identity**.

If the Service Activator processing child `L2` fails permanently, emit **`LineOutcome(success=false, reasonCode=...)`** or enforce an explicit group failure policy. If an error handler merely logs and drops `L2`, the Aggregator may hang forever or release wrong partial results.

Never count duplicate `L1` outcomes as new members toward the expected count. Aggregators need distinct member IDs and explicit manifest/release strategies.

## 30. Never let a write method be re-invoked due to late replies or completion logic

A Gateway/Scatter-Gather flow might experience:

~~~text
Gateway sends command C-801
  → worker A succeeds
  → worker B replies late
  → aggregator/group completion
  → caller times out and retries C-801
~~~

Scenarios to design for:

1. Completed-group/tombstone policy stops **late replies** from emitting a second group output.
2. Replies carry accurate business correlation; never merge two tenants sharing `orderId`.
3. Gateway timeouts do not cancel workers or undo side effects.
4. Caller retries keep **the same logical `commandId`** instead of creating a new UUID for the same operation.
5. Duplicate replies must never trigger a **write-capable** Service Activator again.

**Merely changing output channels or renaming methods never solves replays/late replies.** You need domain idempotency and aggregator completion policies.

## 31. Service Activators must classify errors, not catch all into success

An error contract:

~~~java
final class InvalidCommandException extends RuntimeException {
    private final String reasonCode;

    InvalidCommandException(String reasonCode) {
        super(reasonCode);
        this.reasonCode = reasonCode;
    }

    String reasonCode() {
        return reasonCode;
    }
}
~~~

Common error types:

| Error | Source | Handling |
|---|---|---|
| `MISSING_COMMAND_ID` | Input validation | Permanent rejection |
| `FORBIDDEN_ORDER_OPERATION` | Authorization | Reject/audit; never infrastructure-retry |
| `IDEMPOTENCY_KEY_CONFLICT` | Same key, differing content | Quarantine/investigate |
| `ORDER_ALREADY_CANCELED` | Domain state | Terminal business outcome per contract |
| `DB_DEADLOCK` | Persistence | Bounded retry with fresh transaction |
| `PAYMENT_OUTCOME_UNKNOWN` | Remote side effect | Reconcile |
| `UNEXPECTED_HANDLER_EXCEPTION` | Code defect | Alert/recovery; never blame producer |

Avoid:

~~~java
try {
    orderHandler.place(command);
} catch (Exception failure) {
    return new OrderReceipt(
        command.orderId(),
        command.commandId(),
        "SUCCESS"); // Wrong: creates a fake success.
}
~~~

Handlers must throw or return an appropriate **structured business outcome**, so callers/adapters know whether to retry, ACK, DLQ, or report an error. Raw exception messages should never be exposed publicly if they contain DB, tenant, or secret details.

## 32. Error channels are not automatically invoked for every exception

In synchronous flows:

~~~text
DirectChannel → Service Activator throws
  → exception propagates to sender/Gateway
~~~

In asynchronous flows:

~~~text
ExecutorChannel / poller / broker listener
  → Service Activator throws on worker thread
  → error handler/container or ErrorMessage/errorChannel
~~~

A Spring `ErrorMessage` carries a `Throwable` payload. If the exception is a `MessagingException`, `getFailedMessage()` may provide headers/correlation. However:

- Deserialization errors can occur **before any Spring Message exists**.
- `failedMessage` may be null or carry an unexpected payload type.
- A misconfigured/unsubscribed error channel can lose the recovery path.
- `RetryAdvice` only catches exceptions within **the scope of the handler it wraps**.

**Never catch inside an error handler and ACK just to “clear the queue” when business state never committed.** Use durable recovery policies, DLQ/reconciliation, and diagnostic info sufficient for reprocessing.

## 33. ACK/DLQ ties to execution outcomes, not method names

A Service Activator returning cleanly in Java does not mean business work succeeded:

~~~java
public void handle(PlaceOrderCommand command) {
    executor.submit(() -> placeOrder(command));
    // Method returns immediately; background task has not committed yet.
}
~~~

If the broker ACKs right away because `handle()` returned, and the background task fails without a durable queue/recovery, **work is lost**.

A sound policy might be:

| Outcome | Typical ACK/recovery consideration |
|---|---|
| Business commit succeeded | ACK |
| Duplicate already `SUCCEEDED`, fingerprint matches | ACK, no new side effect |
| Input invalid/unauthorized | Quarantine/terminal response, ACK per adapter policy |
| Transient DB failure before commit | Bounded retry/backoff; never ACK and lose work |
| Async task persisted durable intent, not processed yet | May ACK per async-accepted contract |
| External outcome unknown | Durable reconciliation; never report fake success |
| DLQ/quarantine unavailable | Never drop unless another recovery source exists |

There is no universal ACK API across Kafka, AMQP, and JMS. Transaction ordering, requeueing, offset commits, and error handlers depend on the adapter/container; test against real transports.

**An async accepted result is a different state from `SUCCEEDED`.** When choosing a method that only enqueues work, both its name and return type must reflect that.

## 34. Handler thread safety and concurrency

Spring-managed singleton services can be called concurrently by multiple worker threads:

~~~java
@Service
class UnsafeSequenceHandler {
    private long nextOrderNumber = 0L;

    public OrderReceipt place(PlaceOrderCommand command) {
        long n = ++nextOrderNumber; // Race condition.
        return saveWithNumber(command, n);
    }
}
~~~

A mutable field on a singleton guarantees neither uniqueness nor thread safety. Across multiple instances, even an `AtomicLong` in one JVM **does not guarantee** cluster-wide unique sequence numbers.

Use database sequences/unique constraints, durable state, and transactions when generated IDs require global uniqueness. When two consumers receive the same command:

~~~text
W1: INSERT inbox key C-801
W2: INSERT inbox key C-801
→ unique constraint/transaction serializes outcome
→ only one committed business side effect
~~~

Test concurrency with latches/barriers and concurrent transactions; calling sequentially twice never exposes races. Also test deadlocks/serialization failures with appropriate retry policies.

## 35. Logging and metrics are also side effects that need limits

A handler may log on every retry:

~~~text
INFO customerEmail=... paymentToken=... fullOrderPayload=...
~~~

While not a business side effect, this can cause **data leaks**, storage bloat, and log injection. For diagnostics:

- Log `commandId`/`correlationId` only where access control is appropriate.
- Never log raw credentials, tokens, or unnecessary PII.
- Restrict full payloads and stack traces per retention policy.
- Bound lengths of fields/causes originating from untrusted inputs.
- Never use unique IDs as metric labels (unbounded cardinality).

Metrics should answer **which method actually ran, on which attempt, and whether it committed**, rather than merely counting inbound messages.

## 36. Design conventions for reviewable method selection

| Convention | Purpose |
|---|---|
| One channel represents one named operation | Easy to trace and authorize |
| Public handler methods named explicitly by behavior | Easy to audit side effects |
| Avoid overloading the same name for different command/query purposes | Reduces method-resolution ambiguity |
| DTOs typed per logical operation | Catches type errors early |
| No reflection from untrusted headers | Limits invocable surface |
| Pure validation and authorization before writes | Zero side effects on rejection |
| Separate transactional service bean | Clear proxy/transaction boundary |
| Durable idempotency per logical command | Survives retries and restarts |
| Outbox instead of direct broker publish before commit | Keeps durable intent in sync with business state |
| Explicit Gateway reply vs. one-way contracts | Avoids timeouts and fake successes |
| Error classifier separating permanent/transient/unknown | Proper retry/DLQ/reconciliation |

You do not necessarily need a separate class per operation. What matters is **never exposing an ambiguous endpoint where a message can self-select a write-capable behavior**.

## 37. Unit test: queries must never invoke command handlers

A basic test using Mockito:

~~~java
@Test
void previewDoesNotPlaceOrCancelOrder() {
    OrderQueryHandler queryHandler =
        mock(OrderQueryHandler.class);
    OrderCommandHandler commandHandler =
        mock(OrderCommandHandler.class);

    PreviewOrderQuery query =
        new PreviewOrderQuery("tenant-a", "O-801");
    when(queryHandler.preview(query)).thenReturn(
        new OrderPreview("O-801", new BigDecimal("29.00")));

    OrderPreview preview = queryHandler.preview(query);

    assertEquals("O-801", preview.orderId());
    verify(queryHandler, times(1)).preview(query);
    verifyNoInteractions(commandHandler);
}
~~~

This test only verifies **calls in test code**, not whether Spring Integration picks the right method. Its value is establishing a **clear invariant**: the preview/query path must never touch the command handler.

In the integration test below, send messages through the real Spring channel and verify the exact same invariant, because method-selection bugs typically happen **in endpoint wiring**, not inside POJO logic.

## 38. Integration test: preview input reaches only the right Service Activator

A test-only flow:

~~~java
@Configuration
@EnableIntegration
class PreviewFlowTestConfig {
    @Bean
    IntegrationFlow previewFlow(OrderQueryHandler queryHandler) {
        return IntegrationFlow.from("test.orders.preview")
            .handle(
                PreviewOrderQuery.class,
                (query, headers) -> queryHandler.preview(query))
            .channel("test.orders.preview.reply")
            .get();
    }

    @Bean("test.orders.preview.reply")
    PollableChannel previewReplyQueue() {
        return new QueueChannel();
    }
}
~~~

Test inside an isolated Spring context with mocked `queryHandler` and `commandHandler`:

~~~java
@Autowired ApplicationContext context;
@Autowired OrderQueryHandler queryHandler;
@Autowired OrderCommandHandler commandHandler;

@Test
void previewChannelNeverInvokesPlace() {
    PreviewOrderQuery query =
        new PreviewOrderQuery("tenant-a", "O-801");
    when(queryHandler.preview(query)).thenReturn(
        new OrderPreview("O-801", new BigDecimal("29.00")));

    MessageChannel input = context.getBean(
        "test.orders.preview", MessageChannel.class);
    PollableChannel replies = context.getBean(
        "test.orders.preview.reply", PollableChannel.class);

    assertTrue(input.send(new GenericMessage<>(query)));
    Message<?> reply = replies.receive(1_000);

    assertNotNull(reply);
    assertInstanceOf(OrderPreview.class, reply.getPayload());
    verify(queryHandler).preview(query);
    verifyNoInteractions(commandHandler);
}
~~~

**Mock beans, test context, and imports must be configured in your project.** This sample illustrates what assertions to make, not a complete standalone test class. Run an isolated context so no production endpoints subscribe to the same channel.

Where method selection is risky, also test **wrong-type runtime payloads** or new source schemas: they must be rejected rather than falling into a side-effect-bearing `handle(Object)` fallback.

## 39. Test: invalid commands must stop before writing

A test with fake/mock repositories:

~~~java
@Test
void invalidQuantityDoesNotReachWriteRepository() {
    PlaceOrderValidator validator =
        new PlaceOrderValidator();

    PlaceOrderCommand invalid = new PlaceOrderCommand(
        "tenant-a",
        "C-802",
        "O-802",
        List.of(new OrderLine("SKU-1", -2)));

    InvalidCommandException failure = assertThrows(
        InvalidCommandException.class,
        () -> validator.validate(invalid));

    assertEquals(
        "INVALID_ORDER_LINE",
        failure.reasonCode());
}
~~~

To prove the **no-side-effect** invariant, also test the wired handler/flow with fake repositories or Mockito spies:

~~~java
verify(orderWriteRepository, never()).create(any());
verify(outboxRepository, never()).recordOrderPlaced(
    any(), any());
~~~

These two assertions **supplement tests invoking the handler or `IntegrationFlow`**; they do not apply to calling `Validator` directly since repositories are not wired there. Real tests should build the full message-intake path, inject invalid input, and assert those interactions never happen.

**Do not treat a Filter returning `false` as proof no write method ran** if the Filter predicate or an upstream interceptor already caused side effects. For pure validation, assert `verifyNoInteractions(...)` on write collaborators whenever rejection occurs.

## 40. Test: retry after rollback and redelivery after commit

For `TransactionalOrderCommandHandler` from section 18:

~~~text
Case A: error before COMMIT
  inbox marker INSERT
  order INSERT
  throw transient DB exception
  ROLLBACK entire transaction
  retry same commandId
  → reprocessed cleanly, exactly one committed order

Case B: error after COMMIT, before ACK
  inbox marker + order + outbox COMMIT
  crash before ACK
  broker redelivery same commandId
  → DUPLICATE_COMPLETED / cached receipt
  → no extra order/outbox record
~~~

With a real database or Testcontainers:

~~~java
@Test
void redeliveryAfterCommitDoesNotCreateSecondOrder() {
    PlaceOrderCommand command = sampleCommand("C-801");

    OrderReceipt first = transactionalHandler.place(command);
    OrderReceipt second = transactionalHandler.place(command);

    assertEquals(first, second);
    assertEquals(
        1, orderRepository.countByCommandId("C-801"));
    assertEquals(
        1, outboxRepository.countByCommandId("C-801"));
}
~~~

`sampleCommand` and the repository count methods are **application-implemented test fixtures**. Run the test with **each call crossing a real transaction boundary**; if the test method itself carries an outer `@Transactional`, it can mask production commit/rollback behavior.

**Calling the handler twice alone does not prove broker ACKs.** To verify crashes after commit before ACK, run integration tests with real adapters/containers and fault injection at the exact point.

## 41. Concurrency test: two consumers with the same logical command

A sequential test misses races:

~~~text
call place(C-801)
call place(C-801)
assert one order
~~~

You need a test with **two competing transactions/threads**:

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant B as Worker B
    participant DB as Database
    A->>DB: Claim key C-801
    B->>DB: Claim key C-801
    DB-->>B: Wait/conflict on unique key
    A->>DB: Insert order + outbox + COMMIT
    DB-->>B: Duplicate committed key
    B->>DB: Read same fingerprint/result
    Note over A,B: Expected committed order count = 1
~~~

Checklist:

- Use real unique constraints on `(tenant, operation, commandId)`.
- Test two concurrent callers with identical IDs.
- Test same key with a **different** fingerprint raising conflict.
- Test winner rollback: loser proceeds/retries safely without being falsely marked successful.
- Test under the application's real DB isolation level.
- Set timeouts on concurrency tests so pipelines never hang.
- Across multiple instances, test across processes/nodes rather than only within one JVM.

A `synchronized` method on a singleton bean never solves idempotency across a cluster or across restarts.

## 42. Error-handling test: handler errors must reach the right boundary

Try an intentionally failing handler:

~~~java
@ServiceActivator(inputChannel = "test.orders.fail")
public OrderReceipt fail(PlaceOrderCommand command) {
    throw new InvalidCommandException("INVALID_ORDER_LINE");
}
~~~

On **`DirectChannel`**, inspect exceptions/root causes from `input.send()` or Gateways. On **`ExecutorChannel`**, route errors to the matching error channel and verify `ErrorMessage`, cause chain, and failed-message context.

Required assertions:

1. Permanent errors **never hot-retry endlessly**.
2. Transient errors retry within bounds.
3. Invalid commands **create no business side effects**.
4. Error records capture sanitized `commandId`, `operation`, and `reasonCode` when IDs are trustworthy.
5. Gateways never return fake success or hang until meaningless timeouts on deterministic errors.
6. DLQ/quarantine is never assumed durable when publishing fails.
7. A child handler error does not leave an Aggregator missing members indefinitely.

**Never assume every exception goes to global `errorChannel`.** Test the actual poller, adapter, channel, retry advice, and error-handler configuration used in production.

## 43. Testing matrix for method selection and side effects

| Test case | Input/fault | What must be proven |
|---|---|---|
| Preview request | `PreviewOrderQuery` | Only `preview()` runs; zero writes |
| Place request | `PlaceOrderCommand` | Only `place()` is selected |
| Cancel request | `CancelOrderCommand` | Only `cancel()` after authorization |
| Wrong payload type | JSON/Map/String not matching command | Never hits a write-capable fallback |
| Unknown operation | Unknown `methodName` header | Rejected; no reflection invocation |
| Untrusted tenant | Spoofed tenant header | Security rejection |
| Invalid lines | Negative or excessive quantity | Nothing written to DB/outbox |
| Duplicate completed command | Same `commandId`/fingerprint | No double write; cached result |
| Same key, different payload | Fingerprint mismatch | Conflict and audit |
| Failure before commit | Exception while writing order | Both inbox and order roll back |
| Crash after commit before ACK | Broker redelivery | No double write |
| Publish before rollback | Event sent before DB rollback | Outbox needed instead of broken design |
| Remote timeout | HTTP provider committed | Reconcile / reuse idempotency key |
| `@Transactional` self-call | Internal method | Test proves real transaction boundary |
| Gateway `void` reply | Caller waits for result | Intentional contract/timeout |
| `ExecutorChannel` failure | Handler throws on worker | Proper `ErrorMessage`/container recovery |
| DLQ unavailable | Quarantine write fails | Never ACK and lose work |
| Concurrent same key | Two workers | Unique committed effect |
| Splitter child failure | `L2` fails | Accurate group outcome |
| Duplicate aggregate reply | Repeated `L1` member | Never releases prematurely |
| Late reply after completion | Result arrives late | Never re-triggers side effects |
| Restart after delivery | JVM loses state | Idempotency persists durably |

**Do not assert only the receipt payload.** Verify side effects via **database row counts, outbox records, fake external-provider call counts, authorization mocks, and error-channel events**.

## 44. Observability: seeing which method actually ran

These metrics are **suggestions**, not default Spring Integration meters:

| Metric | Purpose |
|---|---|
| `service_activator.message.received.count` | Messages arriving at the endpoint |
| `service_activator.method.invoked.count` | Actual method invocation count |
| `service_activator.method.success.count` | Handlers completing per contract |
| `service_activator.method.failure.count` | Exceptions by error group |
| `service_activator.duplicate.completed.count` | Handled redeliveries |
| `service_activator.idempotency.conflict.count` | Same key, differing payload |
| `service_activator.side_effect.committed.count` | Real business commits |
| `service_activator.outbox.pending.count` | Durable events awaiting publish |
| `service_activator.retry.attempts.count` | Retry amplification |
| `service_activator.retry.exhausted.count` | Work failing to self-recover |
| `service_activator.authorization.rejected.count` | Methods denied on permissions |
| `service_activator.unexpected_method.count` | Endpoints receiving wrong method/type |
| `service_activator.ack.failure.count` | Redelivery risk |
| `service_activator.duration` | Latency per operation |

Tags should come from a **finite set**: `flowName`, `operation`, `handlerName`, `outcome`, `reasonCode`. **Never use `commandId`, `orderId`, email, or raw headers as metric labels**, due to cardinality and data-leakage risks.

Controlled structured log:

~~~text
eventId=EV-801
commandId=C-801
operation=PLACE
endpoint=orders.place
handler=OrderCommandHandler.place
attempt=2
idempotencyState=SUCCEEDED
transactionOutcome=COMMITTED
businessSideEffectCount=0
result=DUPLICATE_COMPLETED
~~~

A `SUCCEEDED` redelivery can increment **handler invocation count** while leaving **business side-effect count at zero**. That distinction is vital for debugging and impossible to see with metrics that only count “messages processed.”

## 45. Runbook: detecting an unintentionally invoked method

When receiving a report like “the user only previewed, yet an order was placed”:

1. **Locate the actual message** from transport reference/event ID and check its payload type.
2. **Check the receiving channel**: did the message enter `orders.preview` or `orders.place`?
3. **Check endpoint bindings**: which `@ServiceActivator`, `.handle(bean,"method")`, or typed lambda is registered?
4. **Check overloads**: does the bean have `handle(Object)` or multiple methods with the same name?
5. **Check routing**: was the operation read from untrusted headers, SpEL, or reflection?
6. **Check authorization**: where are verified principal/tenant checks enforced?
7. **Check validation**: did a Filter/validator create side effects before rejecting?
8. **Audit commits**: did order, inventory, outbox, or external providers mutate?
9. **Check retries**: did `commandId`/`attemptId` change, or did a redelivery create a new effect?
10. **Check transactions**: did `@Transactional` pass through a Spring proxy covering both inbox and domain writes?
11. **Check async boundaries**: did the caller ACK right after enqueuing onto a thread pool?
12. **Check errors/compensation**: are there permanent failures, unknown remote outcomes, or DLQ entries?
13. **Remediate safely**: block the wrong route, reconcile committed side effects, apply domain compensation; **never delete inbox markers just to replay**.
14. **Add regression tests**: preview never calls command, wrong type never hits fallback, retries never double-commit.

**Always verify whether business effects actually committed before replaying or rolling back manually.** A caller exception never proves the remote system left the command untouched.

## 46. Practice lab: three command/query endpoints that cannot misfire

Build a mini-project **SafeOrderActivator** in Spring Integration:

1. Define `PreviewOrderQuery`, `PlaceOrderCommand`, and `CancelOrderCommand` separately.
2. Name channels `orders.preview`, `orders.place`, and `orders.cancel`.
3. Configure a `@ServiceActivator` endpoint for preview and a Java DSL `.handle(bean, "place")` endpoint for commands; test there are no competing subscribers.
4. Experiment with a `handle(Object)` overload to observe the risk, then remove the ambiguous design.
5. Add a pure Filter/Validator ahead of the command handler.
6. Add authorization backed by a trusted principal/tenant.
7. Use `@Transactional` across inbox + order + outbox in the same DB.
8. Add a unique constraint `(tenantId, operation, commandId)` and fingerprint check.
9. Have the handler throw before commit: retries must succeed and the marker must roll back.
10. Inject a crash after commit before ACK: redelivery must create no second order.
11. Configure bounded Retry Advice and error-channel recovery.
12. Test a reply-expecting Gateway; never use `void` or return `null` for request–reply.
13. Run an async flow and prove transaction/error boundaries belong to the worker thread.
14. Add a Splitter for three line tasks, giving each child its own idempotency key.
15. Add an Aggregator and a failure outcome for one failing member.
16. Test two consumers concurrently processing the same command ID.
17. Attach a fake external payment provider and simulate timeout after remote commit; never send a new key.
18. Measure invocation count, committed effect count, retries, and duplicate metrics.

**Completion criteria:** previews create zero write side effects; wrong-type/header messages never invoke the wrong method; write-capable commands run only after validation and authorization; duplicates/retries never duplicate DB/outbox/remote effects; Gateways, error channels, and DLQs honor their contracts; and tests prove both **right method** and **right effect**.

## 47. Common misconceptions

**“Simply naming a method `preview` makes it read-only.”** False. Inspect its implementation, collaborators, and side effects.

**“`@ServiceActivator` automatically picks a business-safe method.”** No. The framework invokes per configuration/signature, with no awareness of write permissions.

**“`handle(bean, "handle")` is always unambiguous.”** Not when the bean has overloads with the same name and differing payloads/conversions.

**“A `handle(Object)` fallback makes the system more compatible.”** It can mask invalid payloads and trigger unintended side effects.

**“A `methodName` header is a flexible way to control services.”** Dangerous without allowlists/trust boundaries; can become arbitrary method invocation.

**“Channel `orders.cancel` proves the caller is allowed to cancel.”** No. Channels never replace authorization.

**“Filter validation has no side effects because it only returns a Boolean.”** False if the predicate calls `reserve()` or writes to a DB.

**“`@Transactional(readOnly=true)` forbids every write operation.”** Not an absolute security guarantee.

**“Putting `@Transactional` on an internal method means self-calls always trigger the proxy.”** False under default proxy semantics.

**“One message only invokes the handler once.”** False with retries, broker redeliveries, and workflow replays.

**“RetryAdvice automatically makes a method idempotent.”** No; side effects must be guarded separately.

**“A Redis seen marker before the handler means business work finished.”** False if the handler fails and the marker never rolls back.

**“DB transactions roll back HTTP payments too.”** No. Remote side effects have separate boundaries.

**“Publishing to a broker inside a transaction is atomic.”** False without coordinated protocol transactions; an outbox usually fits better.

**“`void` methods work fine for reply-waiting Gateways.”** Usually false; can cause timeouts.

**“`send()` returning `true` means the async handler committed.”** False if the worker has not even executed yet.

**“Every exception goes to global `errorChannel`.”** Depends on sync/async boundaries and configuration.

**“A `synchronized` handler is enough for cluster-wide idempotency.”** False across multiple instances and restarts.

**“Receiving N replies means all N child members succeeded.”** False with duplicates; use manifests and distinct members.

**“Once ACKed, business work definitely succeeded.”** It may only represent durable async acceptance depending on contract/adapter.

## 48. Key takeaways

**Selecting methods without unintended side effects** in a Service Activator requires both **explicit method selection** and **business side-effect discipline**. Assign clear operations per channel, use `@ServiceActivator` on the right method, `.handle(bean, "specificMethod")`, or a typed handler lambda; avoid ambiguous `handle(Object)` overloads/fallbacks, and never let untrusted messages select methods via reflection or SpEL.

Separate **query/read-only** from **command/write**, validate and authorize before side effects, wrap inbox/domain/outbox in one **transaction** when sharing a database, and guard logical commands with durable idempotency keys across retries and redeliveries. For external payments/HTTP, use remote idempotency keys and reconciliation instead of assuming JDBC rollbacks cover everything.

Verify **reply contracts**, `DirectChannel` vs. async/error channels, ACKs/DLQs, Splitter/Aggregator correlation, and concurrency. Tests must assert not merely that “the handler returned the right `OrderReceipt`,” but also prove that **write methods never run when unauthorized**, **commits never repeat on retries**, and **error outcomes never masquerade as fake successes**. That is the foundation for Service Activators that are both flexible and trustworthy in message-driven systems.

### References

- Enterprise Integration Patterns, **Service Activator**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessagingAdapter.html
- Spring Integration Reference, **Service Activator**: https://docs.spring.io/spring-integration/reference/service-activator.html
- Spring Integration Reference, **Message Filter**: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration Reference, **Router**: https://docs.spring.io/spring-integration/reference/router.html
- Spring Integration Reference, **Gateway**: https://docs.spring.io/spring-integration/reference/gateway.html
- Spring Integration Reference, **Error Handling**: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring Integration Reference, **Idempotent Receiver**: https://docs.spring.io/spring-integration/reference/handler-advice/idempotent-receiver.html
- Spring Framework Reference, **Declarative Transaction Management**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
