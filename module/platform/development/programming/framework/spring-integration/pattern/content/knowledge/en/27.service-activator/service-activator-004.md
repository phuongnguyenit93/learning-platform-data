# Return Values as Reply Messages

> **Chapter:** Service activator  
> **Module:** `SPRING_INTEGRATION_PATTERN` — learning how to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows. Practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, while testing and observing execution branches. This lesson focuses on **how a business method's return value is converted into a reply message and routed properly in Spring Integration**.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain the role of a **Service Activator** in EIP: passing messages from the integration layer into a business method and, if a result is produced, returning that result to the message flow.
2. Describe the full lifecycle **request → handler invocation → return value → reply message → reply destination**.
3. Distinguish methods returning a **POJO/record**, returning **`Message<?>`**, returning **`null`**, returning **`void`**, or throwing an exception; understand why they behave differently.
4. Distinguish a **configured output channel** from the **request's `replyChannel`**, and know when a waiting Gateway receives a reply or times out.
5. Write Service Activators using Spring Integration **Java DSL** and demonstrate Gateway request–reply, metadata propagation, typed business rejection, and error handling.
6. Know which metadata—such as `businessCorrelationId`, `operationId`, `replyChannel`, and `errorChannel`—to keep or strip when constructing responses, especially before an external transport boundary.
7. Analyze the impact of local retry, broker redelivery, threads/`ExecutorChannel`, Splitter/Aggregator, duplicate replies, and idempotency on a reply-producing flow.
8. Write JUnit 5 tests for both services and integration flows, covering successful results, business rejections, reply routing, missing replies, and branches that must not emit data.

## 2. The problem: stock reserved, yet the Gateway never receives the result

An e-commerce application sends a stock reservation command:

~~~json
{
  "tenantId": "shop-a",
  "operationId": "RSV-901",
  "orderId": "ORD-901",
  "sku": "BOOK-42",
  "quantity": 2
}
~~~

The business method might return a result object:

~~~json
{
  "operationId": "RSV-901",
  "orderId": "ORD-901",
  "status": "RESERVED",
  "reason": null
}
~~~

In Spring Integration, **a Java method returning `ReserveReceipt`** is different from **the caller receiving a reply message**. The handler must wrap the return value into a message, know which channel to send it to, handle cases with no result, and preserve essential metadata.

~~~mermaid
sequenceDiagram
    participant G as Gateway / Producer
    participant C as Request channel
    participant A as Service Activator
    participant S as ReservationService
    participant R as Reply channel
    G->>C: Message<ReserveCommand> + replyChannel
    C->>A: Deliver request
    A->>S: reserve(ReserveCommand)
    S-->>A: ReserveReceipt
    A-->>R: Message<ReserveReceipt>
    R-->>G: Reply correlated to request
~~~

A flow can **process business logic successfully** while the caller still waits until timeout if the reply is routed to the wrong channel, dropped, or never created because the handler returned `null`.

### 2.1. A return value is not a transport ACK

A broker ACK, an HTTP status, a Java return value, and a business commit are **four distinct events**:

~~~text
Business service returns ReserveReceipt
    != Warehouse DB definitely committed
    != Broker ACK already sent
    != Gateway caller already received reply
    != Exactly-once business side effect
~~~

In a demo without a real DB, we can only say the service **computed a result**. In production, announce `RESERVED` only after commit proof or a durably persisted outcome per contract.

## 3. Service Activator in Enterprise Integration Patterns

A **Service Activator** connects a messaging system to a **method on a service object**. It receives a message, selects/invokes the matching method, and can send the result back into the messaging infrastructure.

~~~text
Message<ReserveCommand>
   |
   v
[inputChannel]
   |
   v
Service Activator
   |
   +-- invoke reservationService.reserve(command)
   |
   +-- return ReserveReceipt / Message<ReserveReceipt>
   |
   v
[reply destination]
~~~

In Spring Integration, a Service Activator can be configured via:

- Java DSL `IntegrationFlow...handle(service, "method")`.
- Annotation `@ServiceActivator(inputChannel = "...", outputChannel = "...")` on an appropriate bean method.
- The specialized `ServiceActivatingHandler` for advanced configuration.
- A Gateway sending to a request channel and receiving the reply emitted by the flow.

### 3.1. Service Activator vs. Transformer

| Component | Primary purpose | Example |
| --- | --- | --- |
| **Transformer** | Change payload/message representation | Partner JSON → `ReserveCommand` |
| **Service Activator** | Invoke a business method from a message | `reservationService.reserve(command)` |
| **Gateway** | Bridge application API calls into/out of a message flow | `gateway.reserve(command)` returns receipt |
| **Router** | Select a channel based on conditions | `status=REJECTED` → rejection channel |
| **Filter** | Accept or discard messages | Block invalid requests |
| **Outbound Adapter** | Push messages to external systems | Publish to Kafka / call HTTP |
| **Aggregator** | Combine child replies into a group result | Combine outcomes of three line items |

**A Transformer can also return a new payload**, but in design terms, a Service Activator is normally where a **business service** or specific operational handler is invoked. Do not assume that because an endpoint returns a reply, it should perform side effects inside a data-mapping step.

### 3.2. Not every Service Activator produces a reply

- **One-way:** receives an event, performs work, produces no reply per contract.
- **Request–reply:** receives a command, returns a business outcome.
- **Event-to-event:** receives an event, produces a new event for the next stage.
- **Async:** executes off the calling thread; replies may arrive later via dedicated endpoint/transport mechanics.

What matters is the **flow contract**: is the caller waiting for a response, or only expecting the request to be accepted into a queue?

## 4. From return value to reply message: six steps

A typical request–reply flow:

1. **Receive request message**: identify payload, headers, and source metadata.
2. **Method invocation**: Spring Integration invokes the selected business method from the message.
3. **Obtain return value**: may be a POJO, `Message<?>`, or no result.
4. **Build/prepare reply**: when returning a POJO, the framework can create a `Message<POJO>` and apply header propagation rules; when returning `Message<?>`, that message forms part of the result.
5. **Resolve reply destination**: configured output channel or the channel carried by the request, depending on topology/endpoint.
6. **Send reply**: through a channel or Gateway/adapter, subject to its own timeouts, errors, and transactions.

~~~mermaid
flowchart TD
    IN["Request Message"] --> INV["Invoke service method"]
    INV --> RT{"Return shape?"}
    RT -->|"POJO / record"| WRAP["Build reply Message"]
    RT -->|"Message<?> "| MSG["Use returned message, apply endpoint rules"]
    RT -->|"null / void"| NO["No normal reply; policy may fail"]
    RT -->|"throws"| ERR["Exception / error handling"]
    WRAP --> DEST{"Reply destination available?"}
    MSG --> DEST
    DEST -->|"Configured output channel"| OUT["Send to outputChannel"]
    DEST -->|"Request replyChannel"| RP["Send to request replyChannel"]
    DEST -->|"None or send fails"| FAIL["No-reply / delivery error handling"]
~~~

This is a **conceptual diagram**. Channel selection rules, reply requirements, and header behavior also depend on the handler, endpoint, Spring Integration version, and flow configuration. Never assume a reply “automatically lands in the right place” unless the topology defines a clear path.

## 5. Return value types and their meanings

| Method return | Ordinary reply message | What to verify |
| --- | --- | --- |
| `ReserveReceipt` / POJO / `record` | Framework creates a reply with that payload type | Header propagation and destination |
| `String` / `Integer` | Payload is the returned value itself | Does it match downstream schema? |
| `Message<ReserveReceipt>` | Reply is the message built by the method, subject to endpoint rules | Headers/metadata, internal channels, security |
| `null` | No ordinary reply payload | `requiresReply` / Gateway timeout |
| `void` | No ordinary reply from method | Is this a one-way contract? |
| Throws exception | No ordinary success reply | Error channel, exception mapping, retry |
| `Optional<T>` | **Do not assume** `Optional.empty()` equals `null` in business contracts | Convert to an explicit typed outcome |
| `CompletableFuture<T>`/reactive type | Depends on endpoint async/reactive support | Completion, timeout, error, and reply semantics |

**Do not confuse:** `null` does not mean business rejection. For a business rejection, return an object such as `ReserveReceipt(status=REJECTED)` so callers receive a meaningful outcome.

### 5.1. Why does `Optional.empty()` require care?

An `Optional.empty()` is **an object** in Java, not `null`. Depending on the handler/method invocation and converters, it may be handled differently than expected. Contracts should define explicitly:

~~~java
record LookupResult(
    String key,
    String status,
    String value
) {}
~~~

Instead of returning `Optional.empty()` hoping the framework interprets “not found,” the service can return `LookupResult(status="NOT_FOUND")` or an appropriate typed rejection. This keeps Gateways, APIs, and tests consistent.

### 5.2. A Service Activator can produce a reply that the caller never receives

If an endpoint has a **fixed output channel** receiving the result, while a Gateway waits on the request's temporary `replyChannel`, that output **does not automatically route back to the Gateway**. Design a response bridge/flow or let replies route to the proper reply channel.

## 6. Reply destinations: `outputChannel` and `replyChannel`

Two common routes:

| Mechanism | Source of destination | When used |
| --- | --- | --- |
| **Configured output channel** | Endpoint/`IntegrationFlow` assigns destination channel | Fixed next pipeline stage |
| **Request `replyChannel`** | Header on the request supplied by framework/Gateway | Request–reply with dynamic callers |
| **No reply path** | None configured and request carries no reply address | One-way; or contract violation if reply expected |

Two example topologies:

~~~text
A. Explicit output:
  input -> Service Activator -> orders.processed -> next step

B. Gateway request/reply:
  gateway.reserve() -> requests -> Service Activator
                                  -> temporary replyChannel
                                  -> Gateway receives receipt
~~~

**Note:** In a message flow, a handler/endpoint's fixed output channel is usually chosen as the reply target when configured, rather than using the request's reply address. Therefore, when writing a Gateway flow, **do not accidentally append `.channel("monitoring.queue")` at the end of the flow** and assume the Gateway still always gets the receipt. If you need both logging and a response, use a wire tap, publish-subscribe, or an intentional bridge—and test it.

### 6.1. `replyChannel` is control metadata

Within the same JVM, the `replyChannel` header may hold a `MessageChannel` or a framework-resolved identifier. It is not an arbitrary HTTP/AMQP/Kafka address and should never be serialized across a broker as a Java object.

If external callers are allowed to specify reply destinations, enforce ACL/allowlist checks so internal data is never routed to unauthorized targets.

### 6.2. `errorChannel` is not `replyChannel`

- `replyChannel` routes **normal processing results**.
- `errorChannel` participates in **error handling paths**, depending on endpoint type, poller, executor, adapter, and configuration.
- An `ErrorMessage` is not equivalent to `ReserveReceipt(REJECTED)`.
- An exception on a synchronous `DirectChannel` can propagate back to the caller instead of automatically going to an async error channel.

Never rely on an `errorChannel` header as proof that Spring Integration will route exceptions to that channel in every topology.

## 7. Java 17: commands and typed replies

Use records to represent request/reply types. The next example omits real inventory calls to focus on return-value semantics.

~~~java
import java.util.Objects;

record ReserveCommand(
    String tenantId,
    String operationId,
    String orderId,
    String sku,
    int quantity
) {
    ReserveCommand {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(operationId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(sku);
    }
}

record ReserveReceipt(
    String operationId,
    String orderId,
    String status,
    String reasonCode
) {
    ReserveReceipt {
        Objects.requireNonNull(operationId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(status);
    }

    boolean accepted() {
        return "RESERVED".equals(status);
    }
}
~~~

### 7.1. Separating validation and business outcomes

Do not assume a method returning a receipt has committed state. In this demo, `RESERVED` is only a simulated decision. When backed by a real database, publish `RESERVED` only after the transaction/operation outcome is finalized and crash recovery is accounted for.

### 7.2. Service method returning a POJO

~~~java
final class ReservationService {

    public ReserveReceipt reserve(ReserveCommand command) {
        if (command.tenantId().isBlank()
                || command.operationId().isBlank()
                || command.orderId().isBlank()
                || command.sku().isBlank()) {
            return new ReserveReceipt(
                command.operationId(),
                command.orderId(),
                "REJECTED",
                "REQUIRED_FIELD_MISSING");
        }

        if (command.quantity() < 1
                || command.quantity() > 500) {
            return new ReserveReceipt(
                command.operationId(),
                command.orderId(),
                "REJECTED",
                "QUANTITY_OUT_OF_RANGE");
        }

        // Demo: does not execute real warehouse mutation.
        return new ReserveReceipt(
            command.operationId(),
            command.orderId(),
            "RESERVED",
            null);
    }
}
~~~

Key point: the method accepts `ReserveCommand` (the payload) and returns `ReserveReceipt` (a POJO). When invoked through a reply-capable Service Activator, **the framework builds a reply message for that value** and forwards it to the appropriate reply destination.

In production, verify the tenant using **trusted sources/authentication**, not by checking that `tenantId` is non-blank. When outcomes depend on live inventory, check at the transaction boundary.

## 8. Java DSL: creating a reply from the service's return payload

A flow using `DirectChannel` for requests and `QueueChannel` to inspect replies:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
class ReservationReplyFlowConfiguration {

    @Bean("reservations.requests")
    DirectChannel requests() {
        return new DirectChannel();
    }

    @Bean("reservations.replies")
    QueueChannel replies() {
        return new QueueChannel();
    }

    @Bean
    ReservationService reservationService() {
        return new ReservationService();
    }

    @Bean
    IntegrationFlow reserveWithExplicitReplyChannel(
            ReservationService reservationService) {
        return IntegrationFlow.from("reservations.requests")
            .handle(reservationService, "reserve")
            .channel("reservations.replies")
            .get();
    }
}
~~~

Execution flow:

~~~text
request message payload ReserveCommand
  -> reservations.requests (DirectChannel)
  -> service activator calls ReservationService.reserve
  -> reserve returns ReserveReceipt
  -> framework emits reply message
  -> reservations.replies (QueueChannel)
  -> receive() can inspect reply
~~~

### 8.1. `.handle(...)` vs. `.channel(...)`

- `.handle(reservationService, "reserve")` invokes the method.
- `.channel("reservations.replies")` specifies the output channel used in the flow.
- `QueueChannel` holds messages for a consumer to poll; it does **not** automatically treat them as responses for a Gateway on another channel.

### 8.2. Method selection and type conversion

When a service has overloads or payloads arrive with mismatched types, method resolution can fail or pick the wrong method if poorly designed. Prefer:

- Handler interfaces/methods with **concrete input types**.
- Normalizing payloads with a Transformer before the Service Activator.
- Avoiding generic `Object`/map parameters across all commands where possible.
- Testing method invocation, converters, and type mismatch errors.

For instance, `reserve(ReserveCommand)` is far clearer than `reserve(Object)` when a service exposes multiple handler methods.

### 8.3. A reply is not a final confirmed outcome

A `QueueChannel` may hold a `Message<ReserveReceipt>` that downstream has not processed yet. If the next stage is an outbound HTTP/Kafka adapter, send failures, duplicates, timeouts, or consumer crashes can still happen. Distinguish **return**, **message created**, **message sent**, and **business acknowledged**.

## 9. Request–reply Gateway: do not assign arbitrary output channels

In a Java application, callers often want to write:

~~~java
ReserveReceipt receipt = gateway.reserve(command);
~~~

While execution underneath runs across a message flow. A **Messaging Gateway** bridges the Java method call and the request–reply flow.

### 9.1. Defining the gateway interface

~~~java
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "reserve.gateway.in")
interface ReservationGateway {

    ReserveReceipt reserve(ReserveCommand command);
}
~~~

The interface has `@MessagingGateway`; Spring Integration needs the corresponding gateway registration/scanning enabled in the application context (for example via `@IntegrationComponentScan`).

### 9.2. Flow using the Gateway's `replyChannel`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
@IntegrationComponentScan
class ReservationGatewayFlowConfiguration {

    @Bean("reserve.gateway.in")
    DirectChannel inputChannel() {
        return new DirectChannel();
    }

    @Bean
    ReservationService gatewayReservationService() {
        return new ReservationService();
    }

    @Bean
    IntegrationFlow reserveGatewayRequestReply(
            ReservationService service) {
        return IntegrationFlow.from("reserve.gateway.in")
            .handle(service, "reserve")
            // Do not intercept output onto another QueueChannel.
            // The endpoint can route the reply to the Gateway's replyChannel.
            .get();
    }
}
~~~

When `gateway.reserve(...)` is called, the Gateway builds a request message with the proper return path. The handler returns `ReserveReceipt`; the flow sends the reply to the Gateway's temporary reply channel so the Java call receives the result.

~~~mermaid
sequenceDiagram
    participant C as Java caller
    participant G as Messaging Gateway
    participant S as Service Activator
    participant R as Temporary replyChannel
    C->>G: reserve(command)
    G->>S: Message<ReserveCommand> + replyChannel
    S-->>R: Message<ReserveReceipt>
    R-->>G: Reply
    G-->>C: ReserveReceipt
~~~

### 9.3. When does the caller time out?

- Handler returns `null` or `void` in a flow expecting a reply.
- Handler routes the reply to a different output channel without bridging back to the Gateway.
- A Filter drops the request or reply without emitting a rejection result.
- Broker/worker processing exceeds the Gateway's reply timeout.
- `replyChannel` or correlation metadata is lost across boundaries.
- Handler throws an exception handled on an error flow that produces no corresponding response.
- An async reply arrives after the Gateway has already timed out.

**A timeout does not prove the business operation failed.** The warehouse may have committed while the response was lost. Callers must keep the **same operation ID** when retrying, and the backend must support idempotency/reconciliation.

### 9.4. Distinguishing a Gateway from a static output channel

| Flow | How results are consumed | Design preference |
| --- | --- | --- |
| `requests → .handle(service) → replies.queue` | Consumer polls `replies.queue` | One-way pipeline with a fixed output channel |
| `Gateway → requests → .handle(service)` | Gateway waits on `replyChannel` | Synchronous request–reply |
| `Gateway → requests → handler → transform reply` | Gateway receives converted DTO | Reply Translator after business service |
| `requests → handler → outbound adapter` | External system receives message/event | Do not assume caller waits for a local reply |

All four topologies can coexist in one system. **Choose based on the caller's contract** instead of attaching a `QueueChannel` to every return value.

## 10. When a handler returns `Message<?>` instead of a POJO

Returning a POJO is simple and keeps services decoupled from Spring Messaging. However, sometimes a response must include **newly computed or explicitly controlled metadata**.

For example, a Service Activator processing `Message<ReserveCommand>` and returning a reply message with selected business headers:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class ReservationReplyMessageService {
    private final ReservationService delegate;

    ReservationReplyMessageService(ReservationService delegate) {
        this.delegate = delegate;
    }

    public Message<ReserveReceipt> reserveWithMetadata(
            Message<ReserveCommand> request) {
        ReserveCommand command = request.getPayload();
        ReserveReceipt receipt = delegate.reserve(command);

        Object correlation = request.getHeaders()
            .get("businessCorrelationId");

        if (!(correlation instanceof String id)
                || id.isBlank()) {
            throw new IllegalArgumentException(
                "BUSINESS_CORRELATION_ID_MISSING");
        }

        return MessageBuilder.withPayload(receipt)
            .setHeader("businessCorrelationId", id)
            .setHeader("operationId", command.operationId())
            .setHeader("targetSchemaVersion", "reserve-receipt-v1")
            .build();
    }
}
~~~

**Note:** This is an **explicit `Message` return value**, no longer just `ReserveReceipt`. Verify actual endpoint behavior for **request-header propagation, `replyChannel`, and `errorChannel`**. Do not inspect only the headers of the newly built message and assume the **final message on the wire** is filtered properly.

### 10.1. Does returning `Message<?>` automatically preserve `replyChannel`?

Do not make absolute assumptions. Depending on the handler/endpoint, reply-related headers may be processed/propagated by the framework per specific rules. If a **static output channel is configured**, the response goes to that channel; if a Gateway should receive the reply, verify the **request reply path** with an integration test.

You can use this for a static pipeline:

~~~java
@Bean
IntegrationFlow explicitReplyMessageFlow(
        ReservationReplyMessageService service) {
    return IntegrationFlow.from("reservations.typed.in")
        .handle(service, "reserveWithMetadata")
        .channel("reservations.typed.out")
        .get();
}
~~~

This is a **fragment**; `reservations.typed.in/out` and the service bean must be declared when wiring it up. In a Gateway flow, verify that the final reply destination still works properly.

### 10.2. Using `copyHeaders(...)` carries risk

~~~java
// Use caution: easily pulls in metadata that does not belong in the reply contract.
return MessageBuilder.withPayload(receipt)
    .copyHeaders(request.getHeaders())
    .build();
~~~

A request may carry `authorization`, `rawPayload`, unverified tenant headers, internal `replyChannel`, or transport delivery metadata. Replies sent to external partners must never include these automatically.

Prefer an **allowlist**:

~~~text
Business reply headers allowed:
  businessCorrelationId
  operationId
  targetSchemaVersion

Forbidden at external boundary:
  authorization
  cookie
  rawPayload
  internalPrincipal
  MessageChannel object
  broker deliveryTag / internal retry state
~~~

**Key takeaway:** Do not filter only in the Service Activator. Outbound adapters/header mappers must also block disallowed headers from leaving the system, because the framework or intermediate endpoints can add or propagate metadata.

### 10.3. Do not overuse `Message<?>` inside domain services

A domain service can return:

~~~java
ReserveReceipt reserve(ReserveCommand command);
~~~

Then the integration layer handles routing and enriching headers. This separation is easier to unit test and less coupled than forcing every domain service to import `org.springframework.messaging.Message`.

Use `Message<?>` when you genuinely need to read or set message metadata at a clear integration point, such as replying to a different channel or attaching correlation metadata outside the payload.

## 11. `null`, `void`, and `requiresReply`

A Java method can certainly return `null`:

~~~java
final class ReservationLookupService {

    public ReserveReceipt lookup(ReserveCommand command) {
        // Illustrates a not-found result:
        return null;
    }
}
~~~

However, a caller waiting for `ReserveReceipt` gets no ordinary business reply. If the flow lacks a clear policy, the Gateway may wait and time out.

### 11.1. Avoid using `null` for meaningful business outcomes

Instead of:

~~~text
lookup returns null
Gateway waits
Gateway times out
Caller guesses reservation does not exist
~~~

Return a typed outcome:

~~~java
record LookupOutcome(
    String operationId,
    String status,
    String reasonCode
) {}

LookupOutcome lookup(ReserveCommand command) {
    return new LookupOutcome(
        command.operationId(),
        "NOT_FOUND",
        "RESERVATION_NOT_FOUND");
}
~~~

A result with status `NOT_FOUND` is completely different from “no reply due to an integration error.” This matters greatly for retries and error reporting.

### 11.2. `requiresReply`: policy when no result is returned

A reply-producing handler can support a **`requiresReply`** setting specifying whether returning `null` is allowed. When a reply is required and none is produced, the handler can raise an appropriate error rather than letting the flow fall silent.

**Configuration-oriented example** with `ServiceActivatingHandler`:

~~~java
import org.springframework.integration.handler.ServiceActivatingHandler;

// Service/method lookup() may return null.
ServiceActivatingHandler handler =
    new ServiceActivatingHandler(lookupService, "lookup");

// Enable required-reply enforcement per the handler semantics/version in use.
handler.setRequiresReply(true);

// Wire the handler into an IntegrationFlow or appropriate endpoint,
// and test the error path on your actual Spring Integration version.
~~~

This fragment illustrates the policy boundary, not a standalone runnable configuration. When integrating, verify the API against your project's Spring Integration version and test actual exception/error-channel behavior. **Do not automatically retry a “missing reply” error endlessly** if the service deterministically returned `null`.

### 11.3. `void` fits one-way endpoints

~~~java
final class AuditEventService {

    public void record(AuditEvent event) {
        // Record audit; no business reply returned.
    }
}

record AuditEvent(
    String operationId,
    String eventType
) {}
~~~

A flow with an input event and a `void` Service Activator makes sense when the caller **does not wait for a reply**. However, if called through a Gateway method returning `ReserveReceipt`, using that same one-way handler can cause the Gateway to time out.

### 11.4. Using `Optional.empty()` to signify no-reply?

Avoid guessing. `Optional.empty()` is not `null` in Java. Depending on converters/handlers, it may pass through as a payload or be unwrapped specially. Contracts should return `LookupOutcome(status=NOT_FOUND)`, or explicitly define how “no result” is represented and back it with integration tests.

## 12. Business rejections should be replies, not technical exceptions

A reservation command with an invalid quantity is a **business/validation rejection**; there is no reason to endlessly retry the same payload. The service can return:

~~~java
return new ReserveReceipt(
    command.operationId(),
    command.orderId(),
    "REJECTED",
    "QUANTITY_OUT_OF_RANGE");
~~~

The Gateway receives a normal reply and maps it to the corresponding API response. This is different from:

~~~java
throw new IllegalStateException("DATABASE_UNAVAILABLE");
~~~

`DATABASE_UNAVAILABLE` is technical/transient; policy may perform bounded retries or route to an error channel/DLQ depending on topology.

### 12.1. Response and failure matrix

| Scenario | What does the handler do? | What does the caller/downstream receive? |
| --- | --- | --- |
| Reserve succeeds | Returns `ReserveReceipt(RESERVED)` | Normal reply |
| Invalid quantity | Returns `ReserveReceipt(REJECTED)` | Typed business rejection |
| Reservation not found | Returns `LookupOutcome(NOT_FOUND)` | Typed not-found reply |
| DB timeout | Throws technical exception | Exception/error flow, bounded retry |
| Handler returns `null` unexpectedly | No ordinary reply | Timeout or `requiresReply` error |
| One-way `void` handler | No ordinary reply | Valid if no response is awaited |
| Broker ACK fails after commit | Possible redelivery | Idempotency/reconciliation, no new command created |

### 12.2. Error channels depend on topology

With synchronous `DirectChannel`, exceptions from the service can propagate to the sender as a `MessagingException` or wrapped cause. With pollers, executors, or inbound broker adapters, errors may become `ErrorMessage`s according to the endpoint/error-channel configuration.

**Do not** assume exceptions automatically convert into a business `ReserveReceipt(REJECTED)`. If callers expect typed errors, implement error mapping/exception translation at the Gateway/boundary.

### 12.3. Do not swallow exceptions and return success

~~~java
// Anti-pattern: external service may not have committed.
try {
    warehouseApi.reserve(command);
} catch (Exception ignored) {
    return new ReserveReceipt(
        command.operationId(),
        command.orderId(),
        "RESERVED",
        null);
}
~~~

If the downstream call failed, returning a fake `RESERVED` reply hides lost work and corrupts sagas or payments. Instead, distinguish `FAILED_FINAL`, `UNKNOWN`, and `RETRYABLE_FAILURE` per your system's contract and reconciliation capabilities.

## 13. Threading, timeouts, and late replies

`DirectChannel` normally invokes the handler on the sender's thread; `ExecutorChannel` and async adapters can hand work off to another thread/process.

~~~mermaid
sequenceDiagram
    participant G as Gateway
    participant E as Executor/Broker
    participant S as Service
    G->>E: request + reply correlation
    E->>S: async dispatch
    Note over G: Waiting up to reply timeout
    S-->>E: ReserveReceipt
    E-->>G: late/normal reply
~~~

If the Gateway times out at 5 seconds while the business service finishes at 7 seconds, **the caller's timeout does not roll back the side effect**.

### 13.1. Deadlines and late-reply policies are mandatory

- Gateway send/reply timeouts must match SLA and topology.
- Long-running async requests can return `ACCEPTED + operationId` immediately, letting callers poll or receive a webhook instead of holding a call open.
- Retrying after a timeout must reuse the same operation ID so the backend does not double-commit.
- Late replies must be logged, reconciled, or discarded per policy—never routed into a new request.
- Tracing should link attempts by business operation rather than assuming a span ID stays constant.

### 13.2. `replyChannel` only matters while a receiver exists

A temporary reply channel may no longer be useful after a Gateway timeout. For long-lived brokers/workers, use **durable reply destinations and a correlation registry**, rather than relying on an indefinitely live Java channel object.

### 13.3. Async return types must be tested on your exact version

If a service method returns `CompletableFuture<ReserveReceipt>`, a Reactor type, or a callback, your Spring Integration version/endpoint must support **awaiting or emitting the reply upon completion**. Never assume a Future can simply be cast to a receipt.

Conceptual example:

~~~java
import java.util.concurrent.CompletableFuture;

CompletableFuture<ReserveReceipt> reserveAsync(
        ReserveCommand request) {
    return CompletableFuture.supplyAsync(
        () -> reservationService.reserve(request));
}
~~~

This snippet illustrates an async return type, **not** advice to use `supplyAsync` with unbounded pools in production. You need managed executors, cancellation, timeouts, exception mapping, and integration tests for your framework version.

## 14. Retry, broker redelivery, and idempotent replies

A Service Activator may be invoked multiple times when:

- `RequestHandlerRetryAdvice` retries the handler in-process.
- A Gateway/client resends due to a response timeout.
- JMS/AMQP/Kafka redelivers a record after a crash, rollback, rebalance, or ACK/offset failure.
- A retry topic, DLQ, or operator replays the message.
- An upstream workflow restarts with the same existing command.

In all cases, **the same business operation** must keep its `operationId`. Replies may be emitted multiple times, but business effects must not commit multiple times when the contract requires idempotency.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant A as Activator A
    participant W as Warehouse
    participant C as Activator B
    B->>A: ReserveCommand(operationId=RSV-901)
    A->>W: Reserve with stable operation key
    W-->>A: Committed result
    A--xB: ACK/reply lost
    B->>C: Redelivery same operationId
    C->>W: Lookup / reuse outcome
    W-->>C: Existing RESERVED
    C-->>B: Reply + ACK
~~~

### 14.1. Multiple invocations, one business outcome

~~~text
Number of handler invocations >= Number of committed operations
~~~

What must be enforced is **at most one committed business effect per operation key** within the defined consistency boundary, not a promise that the handler runs only once under every failure scenario.

### 14.2. Persisted result for safe re-replies

A business owner can persist:

~~~text
reservation_operation(
  tenant_id,
  operation_id,
  request_fingerprint,
  status,
  stored_result,
  updated_at
)
UNIQUE(tenant_id, operation_id)
~~~

When the request arrives again:

1. If `COMPLETED`, return the **persisted result** without reserving again.
2. If `IN_PROGRESS`, defer/wait/reconcile per policy.
3. If same key with a meaningfully different payload, return `IDEMPOTENCY_CONFLICT`.
4. If absent, atomically claim the operation where the mutation commits.
5. If an external service may have committed while the response was lost, enforce idempotency **at the destination** or perform status lookup/reconciliation.

A duplicate request can receive **a new reply message** containing the stored result. That is not a new side effect.

### 14.3. Transactions and when replies are emitted

A `@Transactional` service can return an object before the transaction proxy commits; if the commit fails, the caller must receive an error rather than a false success. Ensure a `RESERVED` response reflects a finalized outcome, not merely “the request was queued.”

### 14.4. Outbox after business commit

~~~text
BEGIN TRANSACTION
  claim operation key
  reserve stock
  persist ReserveReceipt
  insert outbox event StockReserved
COMMIT

Outbox publisher:
  publish event; retry after send failure
  event may be delivered more than once
~~~

An outbox prevents losing notifications after commit, yet **does not guarantee the broker delivers only once**. Event subscribers and Aggregators need their own idempotency.

## 15. Replies and correlation in Splitter–Aggregator

A batch has three child messages:

~~~text
executionId = RUN-901-A
expected childIds = LINE-1, LINE-2, LINE-3

LINE-1 -> Service Activator -> RESERVED reply
LINE-2 -> Service Activator -> REJECTED reply
LINE-3 -> Service Activator -> RESERVED reply
~~~

The Aggregator needs to know which replies **belong to which group**, **which children have results**, and **when to release**.

| Key | Purpose | Example |
| --- | --- | --- |
| `executionId` | Group correlation for one workflow run | `RUN-901-A` |
| `lineId` / `childId` | Identifies a unique part | `LINE-2` |
| `operationId` | Prevents duplicate side effects | `RSV-901-LINE-2` |
| `businessCorrelationId` | Traces steps of the same order | `ORD-901` |
| Spring Message ID | Identifies a single envelope | UUID |

### 15.1. Returning `null` from a handler can leave a group incomplete

~~~text
LINE-1 -> ReserveReceipt
LINE-2 -> null (no ordinary reply)
LINE-3 -> ReserveReceipt
Aggregator -> receives 2/3; may wait until timeout
~~~

If `LINE-2` fails business validation, emit a **typed child outcome**:

~~~java
record LineOutcome(
    String executionId,
    String lineId,
    String operationId,
    String status,
    String reasonCode
) {}
~~~

Then the Aggregator receives all three **unique child outcomes** and can emit a batch status of `PARTIAL/FAILED` per policy. Receiving all replies does not mean all succeeded.

### 15.2. Duplicate and late replies

If `LINE-1` is redelivered:

~~~text
LINE-1 RESERVED
LINE-1 RESERVED (duplicate)
LINE-3 RESERVED
~~~

`group.size() == 3` does not prove `LINE-2` has a result. The release strategy must check the unique set of `lineId`s against the expected IDs.

If a reply arrives late after the group has already completed, do not start a new group and emit a second final result when the contract allows only one finalization. Use a closed-execution state/tombstone and an idempotent finalizer.

### 15.3. Correlation headers are not auto-generated from business fields

When a handler returns a POJO, do not assume the framework extracts `executionId` from the payload and sets a matching group key header. If a downstream Aggregator relies on a header, pass or derive verified metadata at the right step and test the output. When replies cross a broker, header mappers may alter types or drop fields.

## 16. When a service returns a list or async type

A Service Activator returning `List<ReserveReceipt>` **does not automatically mean** emitting N reply messages. A collection may be the payload of **one** message, depending on the handler.

### 16.1. One reply containing the whole batch

~~~java
record BatchReserveResult(
    String executionId,
    java.util.List<ReserveReceipt> results
) {}
~~~

A Gateway invoking a batch and receiving `BatchReserveResult` is a clear contract.

### 16.2. When each child must be processed independently

~~~text
BatchReserveCommand
  -> Splitter: N child commands
  -> Service Activator per child: ReserveReceipt
  -> Aggregator: BatchReserveResult
~~~

Do not expect a `List<?>` return type to trigger a Splitter automatically unless the topology configures one.

### 16.3. Reactive/stream return types

A method returning `Stream<T>`, `Flux<T>`, or `Publisher<T>` can have specific behavior depending on the endpoint and version. Decide between **one batch reply** vs. **N child replies**, and test on your real framework version instead of guessing automatic behavior.

## 17. Request–reply over HTTP, JMS, AMQP, and Kafka

Inside a JVM, `replyChannel` can be an object or internal routing metadata. Across transports, reply destinations must have protocol-appropriate representations and access permissions.

| Transport | Boundaries to design | Notes |
| --- | --- | --- |
| HTTP | Response status/body, request timeout | HTTP 200 does not prove async downstream committed |
| AMQP/RabbitMQ | Reply queue, correlation, ACK/NACK, DLQ | Header mapper and redelivery |
| JMS | `JMSReplyTo`, `JMSCorrelationID`, session TX/ACK | Do not serialize Java channel objects |
| Kafka | Request/reply topics, record key, correlation headers | Offset/rebalance does not replace business ID |
| Internal `DirectChannel` | Synchronous dispatch on caller thread | Exceptions can propagate |
| `ExecutorChannel` | Another thread, local reply routing | Deadlines and late-reply policy |

### 17.1. `JMSCorrelationID` is not automatically `operationId`

JMS uses `JMSMessageID`/`JMSCorrelationID` for request–reply routing. `operationId` is a business ID. They should match only when **deliberately chosen by contract**, never assumed equivalent by default.

### 17.2. Kafka offsets are not reply identities

A record has a topic/partition/offset; republishing to a retry topic changes the offset. Requests and replies need stable correlation contracts plus an appropriate registry/timeout. Idempotency at the business owner still relies on the operation key, not the offset.

### 17.3. Do not send Java channel objects across a broker

Outbound adapters must strip or translate non-serializable `replyChannel`/`errorChannel` objects. Broker reply addresses must be governed by ACLs/allowlists rather than letting external parties pick arbitrary destinations for internal data.

## 18. Unit test: business method returns a typed reply

Test the Java method first to separate business bugs from messaging bugs.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ReservationServiceTest {

    private final ReservationService service =
        new ReservationService();

    private static ReserveCommand command(int quantity) {
        return new ReserveCommand(
            "shop-a", "RSV-901", "ORD-901",
            "BOOK-42", quantity);
    }

    @Test
    void acceptedCommandReturnsReceipt() {
        ReserveReceipt receipt = service.reserve(command(2));

        assertEquals("RSV-901", receipt.operationId());
        assertEquals("ORD-901", receipt.orderId());
        assertEquals("RESERVED", receipt.status());
        assertNull(receipt.reasonCode());
        assertTrue(receipt.accepted());
    }

    @Test
    void invalidQuantityIsTypedBusinessRejection() {
        ReserveReceipt receipt = service.reserve(command(-3));

        assertEquals("REJECTED", receipt.status());
        assertEquals(
            "QUANTITY_OUT_OF_RANGE",
            receipt.reasonCode());
        assertFalse(receipt.accepted());
    }
}
~~~

These tests **do not yet prove** Spring Integration builds a reply message or routes it to the right channel. They only verify the value the Service Activator receives as its return value.

## 19. Integration test: return value becomes a reply message

Using `ReservationReplyFlowConfiguration` from section 8; `DirectChannel` delivers messages to the handler synchronously, and `QueueChannel` lets the test read the output.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ReservationReplyFlowConfiguration.class)
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class ReservationReplyFlowTest {

    @Autowired @Qualifier("reservations.requests")
    MessageChannel input;

    @Autowired @Qualifier("reservations.replies")
    PollableChannel output;

    private static ReserveCommand command(int quantity) {
        return new ReserveCommand(
            "shop-a", "RSV-901", "ORD-901",
            "BOOK-42", quantity);
    }

    @Test
    void returnValueBecomesReplyPayload() {
        Message<ReserveCommand> request =
            MessageBuilder.withPayload(command(2))
                .setHeader("businessCorrelationId", "ORD-901")
                .build();

        assertTrue(input.send(request));

        Message<?> response = output.receive(1000);
        assertNotNull(response);
        assertInstanceOf(
            ReserveReceipt.class, response.getPayload());

        ReserveReceipt receipt =
            (ReserveReceipt) response.getPayload();

        assertEquals("RSV-901", receipt.operationId());
        assertEquals("RESERVED", receipt.status());
        assertNull(output.receive(0),
            "A request should yield one normal reply in this demo");
    }

    @Test
    void businessRejectionStillProducesReply() {
        assertTrue(input.send(MessageBuilder
            .withPayload(command(0))
            .build()));

        Message<?> response = output.receive(1000);
        assertNotNull(response);
        assertInstanceOf(
            ReserveReceipt.class, response.getPayload());

        ReserveReceipt receipt =
            (ReserveReceipt) response.getPayload();

        assertEquals("REJECTED", receipt.status());
        assertEquals(
            "QUANTITY_OUT_OF_RANGE",
            receipt.reasonCode());
        assertNull(output.receive(0));
    }
}
~~~

What this test proves:

- `.handle(service, "reserve")` invokes the right method from the request payload.
- A `ReserveReceipt` return value becomes the **payload of the reply message**.
- The reply arrives at the **configured output channel**.
- Terminal business errors are represented as typed replies, not `null`.
- One demo request yields one output at the time of inspection.

**Limitations:** `receive(0)` checks the queue at test time. With `ExecutorChannel`, brokers, or async retries, use bounded waits, synchronization, and business commit counts. This test also does not prove a Warehouse DB committed.

## 20. Testing Gateways: caller receives the returned object

Using `ReservationGatewayFlowConfiguration` and `ReservationGateway` from section 9.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(ReservationGatewayFlowConfiguration.class)
class ReservationGatewayFlowTest {

    @Autowired
    ReservationGateway gateway;

    @Test
    void gatewayMethodGetsReplyFromServiceActivator() {
        ReserveReceipt receipt = gateway.reserve(
            new ReserveCommand(
                "shop-a", "RSV-901", "ORD-901",
                "BOOK-42", 2));

        assertNotNull(receipt);
        assertEquals("RESERVED", receipt.status());
        assertEquals("RSV-901", receipt.operationId());
    }
}
~~~

The test uses `@SpringJUnitConfig` to start the context and component-scan the Gateway interface. In a real project, component scan configuration must see the `@MessagingGateway` interface. If the Gateway is not initialized, that is a wiring issue, not “the business service returned null.”

### 20.1. Negative test: output channel captures the Gateway's reply

A common misconfiguration:

~~~text
Gateway -> request channel -> Service Activator
    |
    +-- handler output configured to audit.queue
         (Gateway temporary replyChannel never gets the receipt)
~~~

A test should:

1. Call the Gateway with a finite reply timeout.
2. Simulate the flow routing replies to the wrong output channel.
3. Assert the Gateway does **not** receive the expected business receipt.
4. After fixing the flow/bridge, assert the Gateway receives the proper receipt.

Never write tests with infinite timeouts; set bounded timeouts so builds never hang.

### 20.2. Negative test: handler returns `null`

A method returning `null` in a request–reply flow needs a dedicated contract test:

~~~text
request: known operation
handler: returns null
requiresReply=false -> no ordinary reply; Gateway may time out
requiresReply=true  -> missing-reply error according to handler config
~~~

Tests on your project's Spring Integration version must verify exception/wrapping behavior and the error path. Never equate Java `null` with `ReserveReceipt(status=NOT_FOUND)`.

## 21. Testing explicit `Message<?>` and metadata

Using `ReservationReplyMessageService` from section 10 to verify the reply contains only metadata explicitly chosen at the integration layer.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class ReservationReplyMessageServiceTest {

    private final ReservationReplyMessageService service =
        new ReservationReplyMessageService(
            new ReservationService());

    @Test
    void createsBusinessReplyMessageWithAllowedHeaders() {
        ReserveCommand command = new ReserveCommand(
            "shop-a", "RSV-901", "ORD-901",
            "BOOK-42", 2);

        Message<ReserveCommand> input =
            MessageBuilder.withPayload(command)
                .setHeader(
                    "businessCorrelationId", "ORD-901")
                .setHeader("authorization", "Bearer not-for-output")
                .setHeader("rawPayload", "confidential")
                .build();

        Message<ReserveReceipt> reply =
            service.reserveWithMetadata(input);

        assertEquals("RESERVED", reply.getPayload().status());
        assertEquals("ORD-901",
            reply.getHeaders().get("businessCorrelationId"));
        assertEquals("RSV-901",
            reply.getHeaders().get("operationId"));
        assertEquals("reserve-receipt-v1",
            reply.getHeaders().get("targetSchemaVersion"));
        assertNull(reply.getHeaders().get("authorization"));
        assertNull(reply.getHeaders().get("rawPayload"));
    }

    @Test
    void missingBusinessCorrelationFailsClearly() {
        ReserveCommand command = new ReserveCommand(
            "shop-a", "RSV-902", "ORD-902",
            "BOOK-42", 2);

        Message<ReserveCommand> input =
            MessageBuilder.withPayload(command).build();

        IllegalArgumentException error = assertThrows(
            IllegalArgumentException.class,
            () -> service.reserveWithMetadata(input));

        assertEquals(
            "BUSINESS_CORRELATION_ID_MISSING",
            error.getMessage());
    }
}
~~~

**Important:** This test verifies **the method returning `Message`**. It does not yet prove the Service Activator endpoint or outbound adapter avoids propagating extra unexpected headers. Add integration tests inspecting the message **after the endpoint**, and contract tests verifying **serialized headers on the wire** when publishing externally.

## 22. Comprehensive testing matrix

| Scenario | What to assert |
| --- | --- |
| Handler returns `ReserveReceipt` | Output is `Message<ReserveReceipt>` with matching payload |
| Handler returns `String` | Reply contains string per contract |
| Handler returns `Message<Receipt>` | Allowed metadata present, no secrets leaked |
| Handler returns `null` | No-reply or missing-reply error per configuration |
| Handler returns `void` | One-way flow waits for no reply |
| Sync Gateway call with reply | Java method receives expected receipt |
| Gateway output misrouted | Test catches timeout/misrouting |
| Business rejection | Typed `REJECTED` reply, no infinite retry |
| Handler throws transient exception | Bounded retry/backoff/error path |
| Handler throws authorization error | Not retried to bypass permissions |
| `replyChannel` lost across Transformer | Test catches reply failing to reach caller |
| Stale content-type after translation | Adapter serializes target type properly |
| Async service exceeds deadline | Late reply reconciled/discarded properly |
| Multiple child replies | Grouped by execution, unique children counted |
| Duplicate child reply | No premature release or double final outcome |
| Null child reply | Aggregator does not hang unexpectedly |
| Commit succeeds, ACK lost | Redelivery with same `operationId`, no double mutation |
| Outbox publisher retries | Consumer is idempotent on event/result |
| External broker reply-to | Address allowlisted/ACL-checked |
| Sensitive headers in request | Never leaked into external replies |
| v1/v2 reply schemas | Response Translator/contract mapping works |
| Operation ID changes on retry | Test fails; no new command generated |
| Rate limit/timeout | No retry storm or thread leak |

**A test asserting only “a reply arrived” is insufficient.** Verify **the reply reaches the right caller, with the right business identity, matching schema, and without creating extra side effects**.

## 23. Observability: distinguishing return, reply sent, and outcome

To debug “the service ran yet the Gateway still timed out,” do not merely log `handler completed`. Observe each stage:

~~~text
request accepted
  -> handler invoked
  -> return value produced
  -> reply message constructed
  -> reply destination resolved
  -> reply send attempted
  -> caller received reply / timed out
  -> downstream business effect confirmed
~~~

### 23.1. Recommended metrics

| Signal | Question answered |
| --- | --- |
| `service_activator_invocations_total` | How many times was the handler invoked? |
| `service_activator_success_total` | Was a valid return value produced? |
| `service_activator_null_return_total` | How many invocations returned no ordinary reply? |
| `service_activator_exception_total` | What categories of exceptions were thrown? |
| `reply_created_total` | How many reply messages were constructed? |
| `reply_send_failed_total` | How many reply sends to channels/adapters failed? |
| `gateway_reply_timeout_total` | How many callers timed out waiting? |
| `reply_latency` | Latency from request to reply? |
| `late_reply_total` | How many replies arrived after the deadline? |
| `business_rejection_total` | How many typed `REJECTED` replies? |
| `business_effect_committed_total` | How many mutations actually committed? |
| `idempotency_reused_total` | How many replies reused persisted outcomes? |
| `aggregator_duplicate_reply_total` | How many duplicate child outcomes arrived? |
| `error_channel_messages_total` | How many technical errors entered error flows? |

Metric names are **application suggestions**, not a claim that Spring Integration emits all of these automatically. Use Micrometer/observation instrumentation supplemented by business metrics.

### 23.2. Sample log for a successful request–reply

~~~json
{
  "event": "service_activator_reply_produced",
  "flow": "reserve-stock",
  "operationId": "RSV-901",
  "businessCorrelationId": "ORD-901",
  "replyType": "ReserveReceipt",
  "replyStatus": "RESERVED",
  "delivery": "internal-reply-channel"
}
~~~

This is an **illustrative application log schema**. Never log JWTs, raw payment data, PII, or full message headers. `operationId` and `businessCorrelationId` have high cardinality: do not place them in time-series metric labels arbitrarily; record them in access-controlled logs/traces per retention policy.

### 23.3. Measuring the right boundaries

A set of metrics might look like:

~~~text
handler_invocations = 1200
reply_messages_sent = 1190
gateway_timeouts    = 10
business_effects    = 970
idempotency_reused  = 220
~~~

These numbers are illustrative. Reply counts can differ from side-effect counts due to business rejections, retries, duplicates, and one-way no-reply paths. Do not assume `handler_invocations - reply_messages_sent` equals lost orders without checking the topology.

### 23.4. Debugging reply timeouts

Follow this order:

1. **Did input enter the right channel?** The Gateway may be sending to a channel with no consumer.
2. **Was the handler invoked?** Check method binding and conversion.
3. **What was the return value?** POJO, `Message`, `null`, `Future`, or exception?
4. **Is there a fixed output channel?** Is it “swallowing” the Gateway's reply?
5. **Is the `replyChannel` header present where needed?** Did a Transformer or Header Filter alter it?
6. **Is there an async boundary?** Did the Gateway time out before the handler finished?
7. **Was there a send/serialization error?** Does the reply contain a Java object that cannot cross the broker?
8. **Did the business operation commit?** If so, reconcile and retry with the same operation ID.

## 24. Common anti-patterns

| Anti-pattern | Consequence | Better approach |
| --- | --- | --- |
| Assuming returning a POJO guarantees the Gateway gets a reply | Timeouts on miswired channels | Diagram and test the reply path end-to-end |
| Setting a static output channel and forgetting temporary `replyChannel` | Gateway never receives results | Choose explicit topology/bridge |
| Returning `null` to indicate `NOT_FOUND` | Callers wait and time out | Typed `LookupOutcome(NOT_FOUND)` |
| Using `void` in a reply-expecting flow | No normal reply emitted | Separate one-way and request–reply |
| Not configuring/testing `requiresReply` | Silent reply loss | Choose policy and test no-reply |
| Returning `Optional.empty()` assuming no reply | Ambiguous behavior per converter | Typed outcome contract |
| Catching all exceptions and returning `RESERVED` | False success on downstream failure | Explicit error/retry/reconciliation |
| Representing business rejection with retryable exceptions | Retry storms on bad input | Typed rejection or terminal error |
| Using `MessageHeaders.ID` for idempotency | Redelivery creates new operations | Stable business operation key |
| Calling non-idempotent external APIs inside retryable handlers | Double charges/reservations | Backend idempotency/transactions |
| Copying all headers into outbound replies | Leaked tokens/PII and control metadata | Outbound header allowlist |
| Stripping `replyChannel` without a plan | Callers do not know where replies go | Preserve/resolve at proper boundaries |
| Serializing `MessageChannel` over a broker | Codec failures or topology leakage | Transport reply destinations |
| Equating `errorChannel` with `replyChannel` | Wrong error/response semantics | Dedicated error mapping |
| Returning `List<T>` expecting N replies | Aggregator/consumer gets wrong payload | Explicit Splitter or batch reply DTO |
| Returning `CompletableFuture<T>` assuming automatic unwrapping | Wrong type or timeout at caller | Verify async handler support per version |
| Using `group.size()` to release despite duplicate replies | Releases with missing children | Unique child IDs and expected set |
| Letting a Filter drop a child outcome | Aggregator waits forever | Typed `LineOutcome(REJECTED)` |
| Treating post-timeout replies as failures | Side effect may have committed | Late-reply reconciliation |
| Testing only the Java method | Misses wiring/channel bugs | Spring context + Gateway/transport tests |
| Asserting only payload, ignoring headers | Lost correlation or data leaks | Test metadata inclusion and exclusion |
| Logging all headers for debugging | Secret exposure, high cardinality | Minimal structured logs |

## 25. Implementation checklist

- [ ] Determine whether the Service Activator is **one-way** or **request–reply**.
- [ ] Method input and output types have clear contracts; avoid ambiguous overloads.
- [ ] Payload/headers are validated at the right trust boundary before the handler.
- [ ] When returning a POJO, verify the framework builds reply messages and keeps required metadata.
- [ ] When returning `Message<?>`, enforce a header allowlist and never leak secrets.
- [ ] When returning `null`/`void`, no-reply policies and caller expectations are verified.
- [ ] Appropriate `requiresReply`/Gateway timeout policies are in place.
- [ ] Static output channels are not confused with dynamic request `replyChannel`s.
- [ ] `replyDestination`/Gateway temporary channels are tested end-to-end.
- [ ] Error channels and business rejections have distinct contracts.
- [ ] Async boundaries define deadlines, late-reply handling, and cancellation/reconciliation.
- [ ] Correlation ID, operation ID, and execution ID roles are not conflated.
- [ ] Handlers with side effects are protected by idempotency keyed by business operation.
- [ ] Retryable/terminal error policies define backoff, max attempts, and alerts.
- [ ] Post-commit events/replies have reliable delivery/recovery paths (outbox when needed).
- [ ] Splitter/Aggregator receives typed child outcomes rather than stalling on `null`/drops.
- [ ] Group release relies on unique child IDs; duplicate/late replies have defined policies.
- [ ] Header mapping over HTTP/JMS/AMQP/Kafka is verified with contract tests.
- [ ] Java `replyChannel`/`errorChannel` objects are never serialized to external transports.
- [ ] Unit tests check service return values for both accepted and rejected cases.
- [ ] Integration tests verify `MessageChannel` and Gateway deliver real results.
- [ ] Tests prove unselected branches produce no side effects.
- [ ] Measure handler invocations, reply sends, gateway timeouts, and committed outcomes separately.
- [ ] All logs/metrics comply with access control, data minimization, and retention.

## 26. Practice exercise

A ticketing system has a `TicketReservationGateway` accepting `ReserveSeatCommand`. Each command carries `tenantId`, `operationId`, `eventId`, `seatId`, `executionId`, and `businessCorrelationId`. It invokes a Service Activator to reserve a seat, which can return:

- `SeatReservationReceipt(status="RESERVED")`.
- `SeatReservationReceipt(status="SEAT_UNAVAILABLE")`.
- A technical error when the DB is unavailable.
- A timeout after the DB committed before the Gateway received the reply.

**Tasks:**

1. Design `ReserveSeatCommand` and `SeatReservationReceipt` records, separating request identity from reply/status.
2. Write a `reserve(command)` method returning `SeatReservationReceipt`, never returning `null` when a seat is already taken.
3. Diagram the flow `MessagingGateway → request channel → Service Activator → replyChannel → caller`.
4. Write Java DSL for a flow with a static output channel to test via `QueueChannel`.
5. Write a Gateway flow variant that preserves the dynamic `replyChannel`.
6. Write a method returning `Message<SeatReservationReceipt>` with validated `businessCorrelationId` and `operationId`.
7. List headers that must be stripped when replying over HTTP/JMS/Kafka, especially `Authorization` and channel objects.
8. Explain how `requiresReply` helps if a handler unexpectedly returns `null`.
9. Distinguish the typed reply `SEAT_UNAVAILABLE` from a technical exception; choose different retry policies.
10. Write a JUnit test for the method's return value and an integration test proving the Java return value is wrapped in a Spring reply message.
11. Write a Gateway integration test verifying the caller receives the receipt within the timeout.
12. Intentionally misconfigure the output channel and observe the Gateway timeout; fix the topology.
13. Simulate two requests with the same `operationId` due to redelivery; the database must reserve the seat only once despite two replies.
14. Design an outbox if `SeatReserved` must be published after DB commit, and describe duplicate-event handling.
15. For a batch of five seats where one seat is unavailable, use typed `LineOutcome` so the Aggregator does not hang.
16. Choose metrics for handler calls, reply sends, timeouts, duplicate operations, and late replies.
17. With `CompletableFuture`/async workers, specify deadline policies and correlation preservation across threads/brokers.
18. Explain why Kafka offsets or Spring Message IDs should never be used as `operationId`.

**Hint:** Tests should prove three things **independently**: (1) the method produces the right business outcome, (2) the Service Activator sends the reply to the right channel/Gateway, and (3) business side effects are never duplicated on retry/redelivery.

## 27. Summary

**Turning return values into reply messages** is a core mechanism of Service Activators in Spring Integration. When a method returns a POJO/record, a reply-producing handler can build a message with that value as its payload; when returning `Message<?>`, the method participates in controlling metadata. Conversely, `null`/`void` produces no ordinary reply and can cause a Gateway timeout if no no-reply policy exists. Meaningful business rejections should be represented as **typed outcomes**, not confused with technical errors.

The reply path must be designed explicitly: a **fixed output channel** for pipelines, or the **Gateway's `replyChannel`** when a caller waits for the result. Correlation, operation, execution, and reply/error routing headers should only cross necessary boundaries and be constrained per transport. Under retry/redelivery, handlers may execute multiple times, so business logic needs idempotency where state commits; under Splitter/Aggregator, replies need accurate grouping and unique child IDs. Combine Java DSL, Gateways, error handling, tests, and observability to achieve the goal: **right return value, reply routed to the right place, caller understands the outcome, and side effects are never duplicated**.

**References:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Service Activator, Request-Reply, Correlation Identifier, Idempotent Receiver, Aggregator); Spring Integration Reference on Service Activator, Message Handlers, Java DSL, Gateways, Request–Reply, Error Handling, Message Channels, Retry Advice, and Testing; Spring Messaging API for `Message`, `MessageHeaders`, and `MessageBuilder`; Spring Framework Transaction Management; Java SE on records and `CompletableFuture`.







