# Gateway Default Request Channel

> **Chapter:** Messaging gateway  
> **Module:** `SPRING_INTEGRATION_PATTERN` — learning to implement Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows. Practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, along with testing and monitoring processing branches. This lesson focuses on **`defaultRequestChannel` of Messaging Gateway: where a Java call is converted into a request message and begins traversing the integration flow**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain Messaging Gateway as a bridge between a **Java method call** and a **messaging system**, not an HTTP API Gateway or an ordinary `MessageChannel`.
2. Distinguish `defaultRequestChannel` from `defaultReplyChannel`, a request's `replyChannel`, an outbound adapter, and channels configured in Java DSL.
3. Declare `@MessagingGateway(defaultRequestChannel = "...")`, define the corresponding channel bean, and wire it to a Spring Integration flow.
4. Know when a method with `@Gateway(requestChannel = "...")` **overrides** the interface's default request channel.
5. Design a **request–reply** flow with a `Service Activator` returning results to the Gateway without accidentally routing replies to an unreturned channel.
6. Analyze the impact of `DirectChannel`, `ExecutorChannel`, and `QueueChannel` on threading, send timeouts, reply timeouts, pollers, and throughput.
7. Handle `void` methods, typed business rejections, technical errors, error channels, retries, idempotency, and redeliveries without misinferring commit state.
8. Write JUnit tests for default routing, method-level overrides, no-subscriber/missing-poller failures, reply destinations, and duplicate processing risks.

## 2. Scenario: One Java Service Calling Two Order Flows

An application has two needs: processing regular inventory reservations and sending priority reservations. The calling layer just wants a Java API:

~~~java
ReserveReceipt normal = reservationGateway.reserve(command);
ReserveReceipt priority = reservationGateway.reservePriority(command);
~~~

The application **does not want** controllers/business callers to know how to build a `Message`, pick a Spring `MessageChannel`, or manipulate `replyChannel` manually.

Messaging Gateway handles this translation:

~~~mermaid
flowchart LR
    CALL["Java caller"] --> GW["ReservationGateway proxy"]
    GW --> D{"Method-level requestChannel?"}
    D -->|"No"| DEF["reservations.commands (default)"]
    D -->|"Yes: priority"| PRI["reservations.priority"]
    DEF --> H1["Service Activator: reserve"]
    PRI --> H2["Service Activator: reservePriority"]
    H1 --> REP["Reply to caller"]
    H2 --> REP
~~~

Core configuration:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
    defaultRequestChannel = "reservations.commands",
    defaultReplyTimeout = "3000")
interface ReservationGateway {

    // Inherits the interface's defaultRequestChannel.
    ReserveReceipt reserve(ReserveCommand command);

    // Specific method has its own request channel.
    @Gateway(requestChannel = "reservations.priority")
    ReserveReceipt reservePriority(ReserveCommand command);
}
~~~

**Important point:** `defaultRequestChannel` does not decide how **replies** return. It only specifies **where requests are sent** when a method does not declare its own request channel.

## 3. How Does a Messaging Gateway Differ from a Regular Service?

In Java code, a Gateway looks like an interface. At runtime, Spring Integration creates a **proxy** that intercepts method invocations, converts arguments into a message, sends it to the request channel, and (if the method expects a return value) waits for a reply per configuration.

~~~text
gateway.reserve(command)
    |
    v
Gateway proxy
    |  creates Message<ReserveCommand>
    |  selects request channel
    v
reservations.commands
    |
    v
IntegrationFlow / Service Activator
    |  returns ReserveReceipt
    v
reply routing
    |
    v
Gateway maps reply payload to ReserveReceipt
    |
    v
Java caller resumes
~~~

### 3.1. Distinguishing Four Concepts

| Concept | Function | Example |
| --- | --- | --- |
| **Gateway interface** | Java API for application code | `ReservationGateway.reserve(...)` |
| **Default request channel** | Target where **requests** are sent unless overridden | `reservations.commands` |
| **IntegrationFlow input** | Channel/endpoint that **receives** and processes messages | `IntegrationFlow.from("reservations.commands")` |
| **Reply destination** | Where **responses** return to the Gateway | Temporary `replyChannel` or another valid config |

An application can configure `defaultRequestChannel` accurately and still **time out waiting for a reply** if the flow fails to produce a result or misroutes it.

### 3.2. A Gateway Is Not a Spring MVC Controller

`@MessagingGateway` is a **Messaging Gateway** in Spring Integration, distinct from:

- An HTTP API Gateway or reverse proxy sitting in front of microservices.
- A Spring MVC `@RestController` receiving HTTP requests.
- An Outbound Gateway calling an external HTTP/JMS/AMQP service.
- A `Service Activator` invoking business methods directly.

These components can be chained together, yet `defaultRequestChannel` refers to a **MessageChannel inside the Spring application context**, not a URL.

### 3.3. Do Not Confuse `@MessagingGateway` with `IntegrationFlow.gateway(...)`

Spring Integration also has a gateway endpoint concept in Java DSL for calling a **request–reply subflow** inside an `IntegrationFlow`. This lesson focuses on the **interface-level Messaging Gateway** and the annotation's `defaultRequestChannel` attribute.

Both share the request–reply idea, yet **their syntax is not directly interchangeable**. When reading framework documentation, verify whether you are reading about the interface Gateway or the DSL gateway endpoint.

## 4. What Is `defaultRequestChannel`?

`@MessagingGateway(defaultRequestChannel = "reservations.commands")` sets the **default request channel for gateway methods in the interface**.

If a method lacks its own request channel declaration, the Gateway uses this channel as the destination for messages created from invocations.

### 4.1. Request Channel Resolution Diagram

~~~mermaid
flowchart TD
    INV["Invoke gateway method"] --> M{"Method has @Gateway(requestChannel)?"}
    M -->|"Yes"| O["Use method requestChannel"]
    M -->|"No"| D{"Interface defaultRequestChannel?"}
    D -->|"Yes"| DEF["Use defaultRequestChannel"]
    D -->|"No"| MISS["Needs valid request destination config"]
    O --> SEND["Send request message"]
    DEF --> SEND
    MISS --> ERR["Configuration / invocation failure"]
~~~

**Practical precedence rule:** a request channel specified at the **method** level applies to that method; other methods still inherit the interface default. Never assume an override on one method changes the entire Gateway.

### 4.2. The Attribute Does Not Make the Channel Exist Automatically

Declaring the name `"reservations.commands"` does not substitute for having **a valid destination**. In our example, we explicitly declare the channel bean:

~~~java
@Bean("reservations.commands")
DirectChannel reservationCommands() {
    return new DirectChannel();
}
~~~

And wire the flow:

~~~java
@Bean
IntegrationFlow reserveFlow(ReservationOperations service) {
    return IntegrationFlow.from("reservations.commands")
        .handle(service, "reserve")
        .get();
}
~~~

In some cases, Spring Integration can auto-create channels by convention/configuration. However, to keep the **lesson contract explicit**, we declare the target bean, define the consumer, and test it rather than relying on implicit channel creation.

### 4.3. A Default Channel Is Not a Business Router

`defaultRequestChannel` does not inspect the payload to choose between warehouse A/B, tenant A/B, or domestic/international markets. It is a **shared request destination**. If content-based routing is needed, place a **Router** in the flow after the channel or use method-level overrides for genuinely distinct use cases.

~~~text
Gateway defaultRequestChannel
       |
       v
orders.commands
       |
       v
Validate/Authorize
       |
       v
Content-Based Router
   /       |        \
Domestic Priority International
~~~

That way callers do not need to know downstream handler addresses, reducing coupling while still enforcing **source identity, authorization, and policy** before the Router.

## 5. Method-Level `@Gateway(requestChannel)` Overrides the Default

A Gateway can have multiple methods with different message types. For example:

~~~java
@MessagingGateway(
    defaultRequestChannel = "reservations.commands")
interface ReservationGateway {

    // Uses default.
    ReserveReceipt reserve(ReserveCommand command);

    // Overrides only this method.
    @Gateway(requestChannel = "reservations.priority")
    ReserveReceipt reservePriority(ReserveCommand command);

    // Still uses default, unless explicitly overridden.
    ReserveReceipt retryExisting(ReserveCommand command);
}
~~~

| Method | Request Channel Used | Reason |
| --- | --- | --- |
| `reserve` | `reservations.commands` | Inherits interface default |
| `reservePriority` | `reservations.priority` | Has method-level override |
| `retryExisting` | `reservations.commands` | No override |
| Method on another gateway interface | Per that interface's annotation/config | Does not inherit configuration from this interface |

**Never treat `defaultRequestChannel` as a "fallback if the overridden channel is broken."** Once a method has its own request channel configured, that channel must exist and handle messages properly; the framework does not ignore a priority-branch error and fall back to normal.

### 5.1. When Should You Use a Method-Level Override?

It fits when methods have **clearly distinct semantics**, such as:

- `reserve(...)` and `reservePriority(...)` having different policies/lanes.
- `submit(...)` accepting commands while `cancel(...)` needs a cancellation handler.
- `query(...)` needing a read-path request channel separate from the write path.

Do not create hundreds of methods just to map every tenant to its own channel. For dynamic tenant/domain routing, it is usually better for the Gateway to send into **a trusted input** and let a Router/authorization step pick the route.

### 5.2. An Override Is Not Access Control

Calling `reservePriority` does not prove the caller has priority privileges. The `reservations.priority` flow must still verify principal, quota, tenant, and policy. Never rely on method names or channel names as your sole security boundary.

## 6. Request Channel Differs from Reply Channel

An interface configuration might look like:

~~~java
@MessagingGateway(
    defaultRequestChannel = "reservations.commands",
    defaultReplyTimeout = "3000")
interface ReservationGateway {
    ReserveReceipt reserve(ReserveCommand command);
}
~~~

**Here `defaultReplyChannel` is not configured**: in internal request–reply, the Gateway can create a temporary reply destination for the waiting call. The Service Activator returns a `ReserveReceipt`, which must be routed back along that path.

~~~mermaid
sequenceDiagram
    participant J as Java caller
    participant G as Gateway proxy
    participant I as reservations.commands
    participant S as Service Activator
    participant R as Gateway temporary reply channel
    J->>G: reserve(command)
    G->>I: Message<ReserveCommand> + replyChannel
    I->>S: Invoke reserve
    S-->>R: Message<ReserveReceipt>
    R-->>G: Reply
    G-->>J: ReserveReceipt
~~~

### 6.1. Why Shouldn't You Hardcode a Fixed Reply Output When Using a Gateway?

If a flow configures:

~~~java
IntegrationFlow.from("reservations.commands")
    .handle(service, "reserve")
    .channel("reservations.replies.audit")
    .get();
~~~

The result can go into `reservations.replies.audit` instead of the reply destination the Gateway is waiting on. Without a bridge/consumer returning it to the caller, the Gateway will time out.

**Right approach depending on goal:**

- If the goal is **the Gateway returning an object**: let the flow emit the reply back to the request `replyChannel`, and test end-to-end.
- If the goal is **sending the result to another flow too**: add an intentional bridge/route while still fulfilling the Gateway's reply contract.
- If the goal is **logging/metrics in parallel**: consider a wire tap / observability hook rather than diverting the reply into a separate queue and starving the caller.

### 6.2. `defaultReplyChannel` Is Not Another Name for `defaultRequestChannel`

| Attribute / Metadata | Meaning |
| --- | --- |
| `defaultRequestChannel` | **Where** the Gateway sends requests when a method has no override |
| `@Gateway(requestChannel = "...")` | Overrides the request target for one method |
| `defaultReplyChannel` | Configures a default reply channel per Gateway mechanics when needed |
| `@Gateway(replyChannel = "...")` | Method-scoped reply channel per supported configuration |
| Request `replyChannel` header | Reply path provided by the Gateway/framework for the current request |
| `errorChannel` header / Gateway error policy | Error handling, not an ordinary business reply |

A **shared reply channel** can be tricky under concurrent requests; if used, make sure routing/correlation never mixes up replies. For internal synchronous request–reply, temporary reply channels managed by the Gateway are usually simpler.


## 7. Java 17: Typed Command and Result Models

The example simulates two reservation flows to make it clear **which request channel received the message**. No database is connected; a `RESERVED` result in the demo does not mean real inventory committed.

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
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(operationId, "operationId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(sku, "sku");
    }
}

record ReserveReceipt(
    String operationId,
    String orderId,
    String status,
    String processedBy,
    String reasonCode
) {
    ReserveReceipt {
        Objects.requireNonNull(operationId, "operationId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(processedBy, "processedBy");
    }
}
~~~

The `processedBy` field only helps assert the `NORMAL` or `PRIORITY` branch in the example. In a real application, shape the response schema around the business contract without necessarily exposing internal handler names.

### 7.1. Service Simulating Two Handler Types

~~~java
import java.util.concurrent.atomic.AtomicInteger;

final class ReservationOperations {

    private final AtomicInteger normalCalls = new AtomicInteger();
    private final AtomicInteger priorityCalls = new AtomicInteger();

    public ReserveReceipt reserve(ReserveCommand command) {
        normalCalls.incrementAndGet();
        return decide(command, "NORMAL");
    }

    public ReserveReceipt reservePriority(ReserveCommand command) {
        priorityCalls.incrementAndGet();
        return decide(command, "PRIORITY");
    }

    private static ReserveReceipt decide(
            ReserveCommand command, String lane) {
        if (command.tenantId().isBlank()
                || command.operationId().isBlank()
                || command.orderId().isBlank()
                || command.sku().isBlank()) {
            return new ReserveReceipt(
                command.operationId(), command.orderId(),
                "REJECTED", lane, "REQUIRED_FIELD_MISSING");
        }

        if (command.quantity() < 1
                || command.quantity() > 500) {
            return new ReserveReceipt(
                command.operationId(), command.orderId(),
                "REJECTED", lane, "QUANTITY_OUT_OF_RANGE");
        }

        return new ReserveReceipt(
            command.operationId(), command.orderId(),
            "RESERVED", lane, null);
    }

    int normalCalls() {
        return normalCalls.get();
    }

    int priorityCalls() {
        return priorityCalls.get();
    }
}
~~~

**Meaning:** `ReserveReceipt(status="REJECTED")` is still a **valid reply** for a properly routed request. Do not return `null` or throw a technical error to represent a validation failure just to avoid defining a result DTO.

Tenant checks in the demo are purely syntactic. Production must authenticate the principal/tenant at ingress and re-verify permissions, stock, and quotas at the business boundary.

## 8. Defining the Gateway Interface with Default and Override

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
    defaultRequestChannel = "reservations.commands",
    defaultRequestTimeout = "500",
    defaultReplyTimeout = "3000")
interface ReservationGateway {

    // Uses reservations.commands per defaultRequestChannel.
    ReserveReceipt reserve(ReserveCommand command);

    // Overrides request channel for this method only.
    @Gateway(requestChannel = "reservations.priority")
    ReserveReceipt reservePriority(ReserveCommand command);
}
~~~

Timeout strings illustrate **milliseconds** in Spring Integration annotations, not production SLA recommendations.

- `defaultRequestTimeout` relates to waiting when sending to a channel whose send operation can block.
- `defaultReplyTimeout` relates to waiting for a reply under Gateway semantics.
- Neither promises a database rollback or automatically kills a running business thread.
- With synchronous `DirectChannel`, the handler can run inside the send call; reply timeout **does not necessarily interrupt a blocking method**.

The names `reservations.commands` and `reservations.priority` are **integration infrastructure details**. Callers only need `ReservationGateway`; if clients call `MessageChannel` directly to "bypass" the contract, shared checks can be skipped.

## 9. Spring Integration Java DSL: Two Channels, Two Flows

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
class GatewayDefaultChannelConfiguration {

    @Bean("reservations.commands")
    DirectChannel normalChannel() {
        return new DirectChannel();
    }

    @Bean("reservations.priority")
    DirectChannel priorityChannel() {
        return new DirectChannel();
    }

    @Bean
    ReservationOperations reservationOperations() {
        return new ReservationOperations();
    }

    @Bean
    IntegrationFlow normalReservationFlow(
            ReservationOperations service) {
        return IntegrationFlow.from("reservations.commands")
            .handle(service, "reserve")
            .get();
    }

    @Bean
    IntegrationFlow priorityReservationFlow(
            ReservationOperations service) {
        return IntegrationFlow.from("reservations.priority")
            .handle(service, "reservePriority")
            .get();
    }
}
~~~

`@IntegrationComponentScan` must find the `@MessagingGateway` interface. If a project places Gateways in another package, specify scan base packages explicitly; never rely on default scanning unverified.

### 9.1. Normal Processing Flow

~~~text
Java caller
  -> ReservationGateway.reserve(command)
  -> request channel "reservations.commands"
  -> ReservationOperations.reserve()
  -> ReserveReceipt(processedBy=NORMAL)
  -> Gateway reply channel
  -> caller receives ReserveReceipt
~~~

### 9.2. Priority Override Flow

~~~text
Java caller
  -> ReservationGateway.reservePriority(command)
  -> @Gateway requestChannel="reservations.priority"
  -> ReservationOperations.reservePriority()
  -> ReserveReceipt(processedBy=PRIORITY)
  -> Gateway reply channel
  -> caller receives ReserveReceipt
~~~

The two flows do not have to share the same Service Activator method. Sharing a service class is a design choice. A method-level override does not move `reserve` onto the priority channel.

### 9.3. Argument Mapping When a Method Has Multiple Parameters

With a single `ReserveCommand` parameter, the Gateway can use that object directly as the payload. With multiple parameters, specify which is the payload and which are headers/metadata.

~~~java
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;

// Illustrative fragment; not part of the complete interface above:
@Gateway(requestChannel = "reservations.commands")
ReserveReceipt reserveWithTag(
    @Payload ReserveCommand command,
    @Header("clientRequestTag") String tag);
~~~

Never treat the `clientRequestTag` header as proof of tenant authority. It can come from the client and is untrusted; operation identity must follow the business contract.

### 9.4. Default Channel Is Not a Content-Based Router

If you need to select a warehouse by SKU, tenant, or quota, structure it as:

~~~text
Gateway default request channel
   -> Validate/authorize
   -> Content-Based Router
       -> Domestic handler
       -> International handler
       -> Priority handler
~~~

The Router picks the branch from verified data; `defaultRequestChannel` only selects the **ingress point into the flow**.

## 10. One-Way Gateway with a `void` Method

A Java API may not expect a reply:

~~~java
record AuditEvent(String operationId, String eventType) {}

@MessagingGateway(defaultRequestChannel = "audit.events")
interface AuditGateway {
    void record(AuditEvent event);
}
~~~

Illustrative flow:

~~~java
final class AuditRecorder {
    public void record(AuditEvent event) {
        // Demo: record event, return no business reply.
    }
}

@Bean("audit.events")
DirectChannel auditChannel() {
    return new DirectChannel();
}

@Bean
IntegrationFlow auditFlow(AuditRecorder recorder) {
    return IntegrationFlow.from("audit.events")
        .handle(recorder, "record")
        .get();
}
~~~

These `@Bean` definitions are fragments that must live inside an appropriate `@Configuration` along with an `AuditRecorder` bean. They do not belong to the two-channel configuration in Section 9.

**Do not infer "`void` means async fire-and-forget."** With `DirectChannel`, the handler can run synchronously before the `void` method returns. With `QueueChannel` or a broker, the Gateway can return once the request is accepted into the queue, before business processing runs.

If the caller needs a commit outcome, return a typed reply or an operation ID paired with a status API; `void` alone cannot express success/rejected/unknown.

## 11. How Does Channel Type Affect Behavior?

| Channel | Dispatch | Strengths | Gateway Caveats |
| --- | --- | --- | --- |
| `DirectChannel` | Usually synchronous, same thread | Simple, easy to debug | Slow business calls hold the caller thread |
| `ExecutorChannel` | Worker thread managed by executor | Thread isolation / concurrency | Timeouts, tracing, security context, shutdown |
| `QueueChannel` | Messages wait to be polled | Buffering and backpressure | **Must have a poller**; accepted differs from processed |
| `PublishSubscribeChannel` | Fans out to subscribers | Broadcasts / notifications | Multiple replies need Scatter-Gather / Aggregator |
| `PriorityChannel` | Priority queue | Controls dequeue order | Starvation, poller, and capacity |

### 11.1. `DirectChannel` Is Not Automatically "Interrupted" by `replyTimeout`

~~~text
Caller thread
  -> Gateway.send()
    -> DirectChannel
      -> slow business method (10 seconds)
        -> produce reply
    -> send returns
  -> Gateway returns
~~~

When `send()` executes the handler synchronously, `defaultReplyTimeout="3000"` is not a 3-second hard deadline enforced across the entire method. For real I/O, configure JDBC/HTTP client timeouts, circuit breakers, thread budgets, and end-to-end SLAs.

### 11.2. `ExecutorChannel`: Reply Arrives on Another Thread

~~~text
Gateway caller ----send---> ExecutorChannel
                        worker thread ---> handler ---> reply
Gateway caller <-------------- response on reply route
~~~

Do not rely blindly on `ThreadLocal` tenant/principal state in async flows. Propagate auth/correlation context through controlled mechanisms; never copy raw bearer tokens into payloads/headers "just to keep permissions."

### 11.3. `QueueChannel`: Without a Poller, There Is No Reply

~~~text
Gateway -> QueueChannel.send(request) = accepted
                   |
                   v
             waiting in queue
                   |
             no consumer/poller
                   |
           Gateway waits / times out
~~~

If the queue is bounded, `requestTimeout` can affect sends when the queue is full. Even when enqueue succeeds, that does not mean the service executed.

Demo poller (separate config; do not reuse names from the `DirectChannel` in Section 9):

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Bean("reservations.queued")
QueueChannel queuedReservations() {
    return new QueueChannel(1000);
}

@Bean
IntegrationFlow queuedFlow(ReservationOperations service) {
    return IntegrationFlow
        .from("reservations.queued",
              endpoint -> endpoint.poller(
                  Pollers.fixedDelay(100)))
        .handle(service, "reserve")
        .get();
}
~~~

A 100 ms poller is just an example; production needs concurrency, capacity, retry/error policies, and persistence if durability is required.

### 11.4. Publish-Subscribe and Multiple Replies

A `PublishSubscribeChannel` can deliver a request to multiple subscribers. A Gateway waiting for **one** reply does not automatically aggregate results from all subscribers. If results from multiple parties are needed, apply **Scatter-Gather / Aggregator** with a release strategy, timeouts, and unique-reply handling.


## 12. Request Timeout and Reply Timeout Are Two Distinct Phases

Trace the lifecycle of a Gateway method call:

~~~text
T0  Java caller invokes gateway method
T1  Gateway builds Message<ReserveCommand>
T2  Gateway attempts to send to request channel
T3  Request channel accepts/dispatches
T4  Handler computes business outcome
T5  Handler sends reply message
T6  Gateway obtains reply and returns Java value
~~~

Two kinds of waiting are easy to confuse:

- **Request timeout** governs sending to the request channel (for example, a full bounded queue blocking send completion).
- **Reply timeout** governs waiting for a result from the request–reply flow after sending.

If the request is processed synchronously during the send call, a Gateway-level reply timeout does not necessarily interrupt a blocking handler, as explained in Section 11.

### 12.1. Timeline: `QueueChannel` Missing a Poller

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant Q as QueueChannel
    participant H as Handler
    C->>G: reserve(command)
    G->>Q: Send request
    Q-->>G: Accepted into queue
    Note over Q,H: No poller, handler never invoked
    Note over G: Wait reply timeout
    G-->>C: Timeout / no reply outcome
~~~

This is not a Mapper or `ReservationOperations` bug; **it was never invoked**. Inspect channel wiring, pollers, lifecycle, and queue backlog.

### 12.2. Timeline: DB Commits, Reply Lost

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Gateway
    participant W as Worker
    participant DB as DB
    C->>G: reserve(op=RSV-901)
    G->>W: request via channel
    W->>DB: Commit business operation
    DB-->>W: COMMITTED
    W--xG: Reply lost / worker crash
    Note over G: Reply timeout
    G-->>C: Timeout
    C->>G: Retry with same operationId
    G->>W: Same operation again
    W->>DB: Find stored outcome
    DB-->>W: RESERVED (no new mutation)
    W-->>G: Reply
    G-->>C: RESERVED
~~~

**A timeout does not say the operation failed to commit.** A proper retry preserves the **same business operation ID** and relies on idempotency where the effect commits.

### 12.3. Do Not Guess Timeouts

For an API with an SLA, account for:

- Serialization and dispatch overhead.
- Queue wait / poller delay.
- Service/DB/HTTP client time.
- Internal retry backoff.
- Network latency and external caller timeouts.
- Overall workflow deadline and potential late replies.

`defaultReplyTimeout="3000"` is a demo value. Production may require tiered budgets and `UNKNOWN`/`PROCESSING` handling if callers expire before an outcome settles.

### 12.4. Method-Level Timeout Override

The `@Gateway` annotation can configure per-method behavior as supported by your Spring Integration version, such as different reply timeouts for priority commands vs. queries. Yet **do not equate** overriding `requestChannel` with automatically adjusting timeouts. Each attribute has its own responsibility and needs tests when changed.

## 13. Configuration Errors Related to `defaultRequestChannel`

| Mistake | Symptom | Where to Check |
| --- | --- | --- |
| Wrong/unresolved channel name | Gateway fails to send; config/invocation error | Bean names, application context, channel resolution |
| `DirectChannel` has no subscriber | Send fails due to missing handler | Did `IntegrationFlow` actually register a consumer? |
| Two subscribers on `DirectChannel` | Expected handler not invoked | Dispatch/load-balancing semantics, not broadcast |
| Method override points to wrong channel | Only `reservePriority` fails | `@Gateway(requestChannel)` and priority flow |
| `QueueChannel` has no poller | Send succeeds yet times out | Consumer/poller and queue depth |
| Fixed output channel swallows reply | Handler runs yet Gateway times out | Reply channel topology/bridge |
| Service method returns `null` | No ordinary reply | `requiresReply` / typed outcome |
| Handler throws exception | Caller gets exception or error route | Type/wrapping/error channel policy |
| Async executor saturated | Slow replies or task rejections | Pool saturation / rejected execution |
| Transport reply headers stripped | Remote caller receives no response | Header mapper / correlation |
| Gateway interface not registered | Cannot inject interface bean | `@IntegrationComponentScan` / config |
| Output type mismatch | Mapping reply to Java return type fails | Payload converter, return-type contract |

### 13.1. A `DirectChannel` with Two Subscribers Does Not Copy Requests Twice

`DirectChannel` uses point-to-point dispatch; with multiple handlers/subscribers, it applies dispatch/failover semantics rather than broadcasting copies to every subscriber. Therefore, never attach both **normal + priority** handlers to the same `DirectChannel` expecting both to run.

When multi-recipient/broadcast behavior is needed, use an appropriate pattern such as Publish-Subscribe / Recipient List / Scatter-Gather and define a reply release strategy.

### 13.2. Channel Names Are Not the Caller's API Contract

Callers should not need to know `"reservations.commands"` to call `reserve(...)`. Channel names exist for internal wiring and monitoring; the public business API should be the interface method with clear inputs and outputs.

When renaming a channel, update the Gateway annotation, bean declarations, and flow together. Constants or configuration properties help, provided stale references to deleted beans are avoided. Tests catch wiring breaks early.

### 13.3. What Payload Should the Service Activator Return?

If the handler returns `ReserveReceipt`, the Gateway method declares `ReserveReceipt`. If the handler returns `Message<ReserveReceipt>`, Spring Integration extracts or passes the payload/message according to message-handling rules. Test the **actual return types** instead of guessing.

A `ReserveReceipt(status="REJECTED")` is a business reply; it is not automatically an exception. If a controller should return HTTP 422, that decision belongs **at the HTTP boundary**, not inside `defaultRequestChannel` semantics.

## 14. Technical Errors, Business Rejections, and Error Channel

A flow can produce three categories of outcomes:

| Category | Example | How the Gateway Should Express It |
| --- | --- | --- |
| **Success** | Inventory reservation committed | Typed `ReserveReceipt(RESERVED)` |
| **Business rejection** | Invalid quantity, out of stock per terminal policy | Typed `ReserveReceipt(REJECTED)` with reason |
| **Technical failure** | DB timeout, broker unavailable, serialization error | Exception / error flow / bounded retry |

### 14.1. An Error Channel Is Not a Request Channel

`defaultRequestChannel` answers **where requests go**. An error channel answers **how errors are handled**, usually depending on the endpoint, poller, executor, and adapter.

With synchronous `DirectChannel`, handler exceptions can typically propagate back to the Gateway caller as an exception/wrapper. In async flows, errors can be emitted as `ErrorMessage` per configuration. **Never** assume every exception goes to a global error channel and magically turns into a `ReserveReceipt`.

### 14.2. Business Rejections Should Have Clear Replies

~~~java
return new ReserveReceipt(
    command.operationId(),
    command.orderId(),
    "REJECTED",
    "NORMAL",
    "QUANTITY_OUT_OF_RANGE");
~~~

Turning this into a retryable exception causes brokers/clients to retry the same invalid quantity endlessly. A typed result lets Gateway callers distinguish a **valid rejection** from an **unknown outcome**.

### 14.3. Never Rewrite Technical Failures into Fake Success

~~~java
// DO NOT DO THIS:
try {
    externalWarehouse.reserve(command);
} catch (Exception ignored) {
    return new ReserveReceipt(
        command.operationId(), command.orderId(),
        "RESERVED", "NORMAL", null);
}
~~~

A remote API error does not prove the side effect succeeded. Use status lookup/reconciliation if responses can be lost after commit; never catch-all and return `RESERVED`.

### 14.4. Gateway Error Mapping Must Be an Intentional Policy

For a Java method returning `ReserveReceipt`, a technical exception may need to propagate or map into a `PROCESSING`/`UNKNOWN` DTO at the boundary. Choose based on the business contract. Never lump all errors into `REJECTED`, losing the ability to retry or reconcile.

## 15. Important Metadata Across the Gateway

The Gateway builds a message from method arguments. Some metadata belongs to integration, some to business. Distinguish:

| Metadata | Role | Rule Through Flow |
| --- | --- | --- |
| `operationId` | Idempotency for business effects | Keep identical across retries/redeliveries |
| `tenantId` | Data scope and permissions | Verify principal; never trust unverified body |
| `businessCorrelationId` | Trace one business request | Propagate per contract |
| `executionId` | Correlation of one workflow run | Scope to that execution only |
| `replyChannel` | Gateway's reply destination | Preserve per required internal topology |
| `errorChannel` | Error routing metadata | Never substitute for normal reply |
| `MessageHeaders.ID` | Framework-assigned envelope ID | Never use as operation key |
| `sequenceNumber/sequenceSize` | Splitter/Aggregator metadata | Keep only when group semantics apply |
| `traceId/spanId` | Observability | Never use as security/idempotency identity |
| HTTP/JMS/AMQP/Kafka delivery metadata | Transport-specific | Never treat as business identity |

### 15.1. Correlation Differs from Idempotency

~~~text
businessCorrelationId = ORD-901
executionId           = RUN-901-A
operationId           = RSV-901-LINE-1
Spring Message ID     = UUID-of-envelope
~~~

One order can have multiple operations. If you dedupe solely by `businessCorrelationId=ORD-901`, a `RELEASE` command might be wrongly blocked by an earlier `RESERVE`. If you use the envelope ID, redelivery generates a new ID and repeats the effect.

### 15.2. A Gateway Proxy Does Not Authenticate Tenants Just Because a Parameter Has `tenantId`

Calling `reserve(new ReserveCommand("shop-b", ...))` is a Java call, not proof of authorization. In multi-tenant architectures, establish authenticated identity at ingress or the service boundary and verify the caller can act on that order/tenant before committing.

An internal channel is just a pipe. If it carries externally influenced data, downstream must still enforce AuthN/AuthZ and data limits.

### 15.3. Thread Context Across `ExecutorChannel`

When a flow runs on a worker thread, `ThreadLocal`-based security/tracing context may not propagate automatically. Use framework-supported context propagation and/or contract-approved business identity in message metadata; **never copy raw bearer tokens into payloads/headers** "so permissions aren't lost."

### 15.4. `replyChannel` Is an Internal Object, Not an External Address

Over HTTP/Kafka/JMS/AMQP, a `replyChannel` holding a Java `MessageChannel` object must not be serialized as-is. Remote request–reply requires a **transport reply destination** with a correlation ID, ACLs, timeouts, and proper conversion.

## 16. Retries/Redeliveries Must Not Randomly Switch Request Channels

When a client or consumer retries the same business operation, the big question is not merely whether it took the normal or priority channel, but **whether side effects execute twice**.

~~~text
First attempt:
  operationId=RSV-901, routed NORMAL, stock reserved
  reply lost

Redelivery:
  operationId=RSV-901, perhaps routed PRIORITY
  lookup existing operation result
  do NOT reserve stock again
~~~

If the same operation key can enter through two lanes, **both lanes must share the same idempotency boundary at the business owner**. A per-worker local `HashSet` is not enough.

### 16.1. Failure Window: Commit Succeeds, Then Reply Is Lost

~~~mermaid
sequenceDiagram
    participant C as Client/Gateway
    participant A as Handler A
    participant DB as Shared inventory DB
    participant B as Handler B
    C->>A: RSV-901
    A->>DB: Atomic claim + reserve
    DB-->>A: COMMITTED
    A--xC: Reply lost
    C->>B: Retry RSV-901
    B->>DB: Read unique operation key
    DB-->>B: Stored RESERVED result
    B-->>C: RESERVED reply
~~~

**Ensure:** A and B never both commit inventory for one operation. With a shared database, use a unique operation key + transaction alongside the mutation; with external APIs, use an idempotency token at the **target** or reconciliation.

### 16.2. Changing Routes Must Not Invent a New Command

If a timeout prompts the caller to invoke `reservePriority(...)` instead of `reserve(...)`, that may simply be a **retry of the same command** on another lane, or a brand-new business command. The contract must decide; never generate a fresh `UUID.randomUUID()` "to run faster." If business allows **priority escalation**, record policy against the existing operation instead of changing identity.

### 16.3. Gateways Do Not Provide Exactly-Once Automatically

Messaging Gateway only translates calls into messages/request–reply and assists routing; **it does not make business side effects idempotent**. Kafka/JMS transactions and broker ACKs have their own consistency boundaries and do not create an atomic DB+HTTP transaction across all components.

### 16.4. Retry Storms and Timeout Budgets

A client retrying twice, a Gateway retrying three times, and a consumer redelivering twice multiply attempts for the same key. Nested retries need budgets, backoff, and jitter; if all instances hammer a slow DB simultaneously, queue backlogs and lock contention spike.

Classify **terminal input errors** as non-retryable, **transient transport errors** as bounded-retryable, and **unknown business outcomes** as requiring reconciliation rather than new side effects.

## 17. Gateways in Splitter–Aggregator and Scatter-Gather Flows

One Gateway method can represent a **batch command**, while the flow behind it processes multiple child messages:

~~~mermaid
flowchart TD
    G["Gateway: reserveBatch(batch)"] --> IN["defaultRequestChannel"]
    IN --> S["Splitter"]
    S --> A["Reserve LINE-1"]
    S --> B["Reserve LINE-2"]
    S --> C["Reserve LINE-3"]
    A --> AG["Aggregator by executionId"]
    B --> AG
    C --> AG
    AG --> R["BatchReserveReceipt"]
    R --> G
~~~

The Gateway expects **one aggregated reply** if the method declares `BatchReserveReceipt` as its return type. One child returning a result is not enough to complete the batch cleanly.

### 17.1. Losing One Child Can Cause the Gateway to Time Out

If `LINE-2` is silently dropped by a Filter:

~~~text
Expected: LINE-1, LINE-2, LINE-3
Received: LINE-1, LINE-3
Aggregator waiting: 2/3
Gateway: reply timeout
~~~

If rejection is a meaningful outcome, return `LineOutcome(lineId, status=REJECTED)` for that child instead of silently dropping it. The Aggregator can collect three **unique outcomes** and return a `PARTIAL`/`FAILED` batch result.

### 17.2. Group Correlation Needs the Right Scope

- `executionId` groups replies for one workflow run.
- `lineId` uniquely identifies each child; duplicate replies must not be counted twice.
- `operationId` protects each child's side effects.
- `businessCorrelationId` traces back to the original order.
- `sequenceNumber/sequenceSize` need accurate semantics if used for release.

If two concurrent executions run for the same order, grouping solely by `orderId` mixes replies. Never rely on raw group size when duplicates can arrive; track unique child IDs and closed-execution tombstones.

### 17.3. Zero Replies: Aggregator Timeout Alone Is Not Always Enough

If no child emits a reply, **there may not even be a group yet for group-timeout to fire**. An execution-level deadline watcher may be needed. A Gateway timeout is only a caller-side signal and does not clean up in-flight business operations underneath.

### 17.4. The Gateway Does Not Close Groups Automatically

If the Aggregator already emitted `BatchReserveReceipt` and a duplicate late reply recreates the group, it can emit a second final result. Persist closed-execution state or make the finalizer idempotent rather than relying purely on the Gateway "only taking one reply."


## 18. JUnit 5: Verifying the Gateway Actually Uses the Default Channel

The code in Sections 7–9 includes `ReservationGateway`, `ReserveCommand`, `ReserveReceipt`, `ReservationOperations`, and `GatewayDefaultChannelConfiguration`. This test runs inside a Spring context to verify **routing to the right endpoint**, not just the logic of a Java method.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(GatewayDefaultChannelConfiguration.class)
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class GatewayDefaultChannelIntegrationTest {

    @Autowired
    ReservationGateway gateway;

    @Autowired
    ReservationOperations operations;

    private static ReserveCommand command(
            String operationId, int quantity) {
        return new ReserveCommand(
            "shop-a", operationId, "ORD-901",
            "BOOK-42", quantity);
    }

    @Test
    void methodWithoutOverrideUsesDefaultRequestChannel() {
        ReserveReceipt receipt =
            gateway.reserve(command("RSV-901", 2));

        assertNotNull(receipt);
        assertEquals("RSV-901", receipt.operationId());
        assertEquals("RESERVED", receipt.status());
        assertEquals("NORMAL", receipt.processedBy());

        assertEquals(1, operations.normalCalls());
        assertEquals(0, operations.priorityCalls());
    }

    @Test
    void methodLevelGatewayOverridesRequestChannel() {
        ReserveReceipt receipt =
            gateway.reservePriority(command("RSV-902", 2));

        assertNotNull(receipt);
        assertEquals("RSV-902", receipt.operationId());
        assertEquals("RESERVED", receipt.status());
        assertEquals("PRIORITY", receipt.processedBy());

        assertEquals(0, operations.normalCalls());
        assertEquals(1, operations.priorityCalls());
    }

    @Test
    void rejectedBusinessInputStillReturnsReplyViaDefault() {
        ReserveReceipt receipt =
            gateway.reserve(command("RSV-903", -1));

        assertNotNull(receipt);
        assertEquals("REJECTED", receipt.status());
        assertEquals(
            "QUANTITY_OUT_OF_RANGE",
            receipt.reasonCode());
        assertEquals("NORMAL", receipt.processedBy());

        assertEquals(1, operations.normalCalls());
        assertEquals(0, operations.priorityCalls());
    }

    @Test
    void twoGatewayInvocationsKeepTheirOwnRoutingContracts() {
        ReserveReceipt ordinary =
            gateway.reserve(command("RSV-904", 2));
        ReserveReceipt priority =
            gateway.reservePriority(command("RSV-905", 1));

        assertEquals("NORMAL", ordinary.processedBy());
        assertEquals("PRIORITY", priority.processedBy());
        assertNotEquals(
            ordinary.operationId(), priority.operationId());

        assertEquals(1, operations.normalCalls());
        assertEquals(1, operations.priorityCalls());
    }
}
~~~

### 18.1. Why Assert Counters?

Checking only `receipt.status() == "RESERVED"` **is not enough**: both normal and priority handlers can return `RESERVED`, so the test would still pass even if a request went to the wrong channel.

The assertion pair:

~~~java
assertEquals(1, operations.normalCalls());
assertEquals(0, operations.priorityCalls());
~~~

proves `reserve(...)` actually hit the normal handler. For `reservePriority(...)`, the counts swap. That verifies the **routing semantics** of `defaultRequestChannel`, not just the business result.

### 18.2. Why Use `@DirtiesContext`?

`ReservationOperations`'s counters live in a singleton bean in the test context. `@DirtiesContext(AFTER_EACH_TEST_METHOD)` keeps these illustrative tests independent of execution order. In larger suites, replace with an explicit fixture reset or fresh test containers based on resource constraints.

**Never carry these in-memory counters into production deduplication.** A multi-replica system needs a shared, durable idempotency boundary.

### 18.3. Limitations of This Test

A single-`ApplicationContext` test proves the Gateway proxy, channels, and Service Activator wiring at the Spring Integration level. It does not yet test:

- Database commits and rollbacks.
- Broker ACK/redelivery.
- Failures sending replies over remote transports.
- Real security principals and tenant authorization.
- Gateways backed by `QueueChannel`/`ExecutorChannel` with delays.
- Multi-instance idempotency.
- Timeouts where the handler committed yet the reply was lost.

Those cases need integration, contract, and chaos tests at their corresponding boundaries.

## 19. Testing Error Configurations and Timeouts

Do not test only the happy path; the hardest Gateway bugs happen when **a request was accepted** yet no reply comes back.

### 19.1. Request Channel Has No Subscriber

Configure a `DirectChannel` with no connected handler and invoke the Gateway. In many configurations, send fails because no subscriber exists. Tests should match the framework/version's error reporting and assert:

1. No business side effects occurred.
2. A clear route/dispatcher error is raised instead of returning a fake `RESERVED`.
3. No silent fallback rerouting to another channel just because the default channel failed.

**Do not hardcode a single exception class** across all versions without verifying against your actual dependency.

### 19.2. `QueueChannel` Has Messages but No Poller

Have the Gateway send to a `QueueChannel` with no configured consumer/poller and a bounded reply timeout.

~~~text
Given: queue empty, no poller
When: gateway.reserve(command)
Then:
  - request may be accepted into queue
  - ReservationOperations.normalCalls() stays 0
  - Gateway does not get ReserveReceipt
  - bounded timeout/no-reply behavior is observed
~~~

This test matters because **send success** can hide the fact that the request never reached a handler.

### 19.3. Fixed Output Channel Prevents the Gateway from Receiving the Reply

Intentionally append after the handler:

~~~java
// Broken variant if the Gateway is expecting a different reply:
.handle(service, "reserve")
.channel("reservations.unconsumed.out")
~~~

If that channel does not return replies to the Gateway, the handler can execute and build a receipt while the Gateway times out. Tests should check both invocation counts and caller outcomes to catch **reply routing failures**.

### 19.4. Do Not Equate No-Reply with Rejected

If a handler returns `null` or `void` in a flow where the Gateway method expects `ReserveReceipt`, the caller receives no normal reply. Check `requiresReply` if supported on the handler and the error flow for your version.

A message blocked by a Filter can also cause a missing reply. When rejection is a valid business outcome, return `ReserveReceipt(status=REJECTED)` or a typed error mapping instead of silently dropping.

### 19.5. 100 Concurrent Calls Test

With multiple operations having distinct keys:

~~~text
Given:
  100 distinct commandIds
  20 concurrent callers
  shared Spring Gateway proxy
  handler returns matching operationId

Assert:
  every caller receives receipt for its own operationId
  no cross-request reply leak
  normalCalls == number of normal requests
  priorityCalls == number of priority requests
~~~

When using `ExecutorChannel` or a remote broker, verify timeouts, correlation, service thread-safety, and metrics. Never use the envelope's `MessageHeaders.ID` as a business ID.

### 19.6. Testing a Handler Blocked Longer Than `replyTimeout`

Do not just put `Thread.sleep(5000)` inside a `DirectChannel` expecting `defaultReplyTimeout=3000` to preempt it. Because send can be synchronous, the call still blocks until the handler finishes.

To genuinely test reply deadlines, use a **controlled async boundary** or a Gateway/broker with an independent reply-wait mechanism; add fake clocks/latches or proper synchronization instead of brittle timing tests.

## 20. Observing and Troubleshooting Gateway Failures

A `Gateway invoked` log does not prove the request reached the right handler, and a `handler returned` log does not prove the caller received the reply.

### 20.1. Measurement Points

| Metric / Signal | Purpose |
| --- | --- |
| `gateway_invocations_total` by method | How many API calls occurred |
| `gateway_request_send_attempts_total` | How many send attempts were made |
| `gateway_request_send_failed_total` | Failures sending into the channel |
| `gateway_reply_received_total` | How many replies the Gateway received |
| `gateway_reply_timeout_total` | Callers waiting past deadline |
| `gateway_missing_reply_total` | Handler/flow produced no ordinary reply |
| `gateway_route_normal_total` | Traffic using the default route |
| `gateway_route_priority_total` | Traffic using the method override |
| `service_activator_invocations_total` | How often handlers actually ran |
| `business_rejections_total` | Typed terminal rejections |
| `business_effect_committed_total` | Side effects actually committed |
| `idempotency_reuse_total` | Duplicates served from persisted outcome |
| `queue_depth` / `queue_oldest_age` | Congestion / poller lag |
| `executor_rejected_tasks_total` | Executor saturation |
| `late_reply_total` | Replies arriving after deadline |
| `error_channel_messages_total` | Technical errors routed to error flow |

These are **suggested metrics defined by your application/observability layer**, not a guarantee that Spring Integration emits every row out of the box. Use Micrometer/observation instrumentation plus custom metrics.

### 20.2. Sample Log on Normal Routing

~~~json
{
  "event": "gateway_request_routed",
  "gatewayMethod": "reserve",
  "requestChannel": "reservations.commands",
  "targetFlow": "normalReservationFlow",
  "outcome": "REPLIED",
  "replyType": "ReserveReceipt"
}
~~~

Log only fields cleared by security policy. `operationId`, `tenantId`, `businessCorrelationId`, and `orderId` have high cardinality and may be sensitive; never place them arbitrarily into metric tags. Logs/traces need masking, retention, and access control.

### 20.3. Step-by-Step Procedure to Debug a Gateway Timeout

1. **Is the Gateway bean registered?** Check `@IntegrationComponentScan`, packages, and bean injection.
2. **Which method was called?** Does it use the default or a method-level override?
3. **Does the request channel name resolve?** Check bean names, collisions, or wrong context.
4. **Does the channel have a consumer?** For `DirectChannel` check subscribers; for `QueueChannel` check pollers.
5. **Was the handler invoked?** Check method binding, payload type, and exceptions.
6. **What did the handler return?** DTO, `Message<?>`, `null`, `void`, or `Future`?
7. **Where did the reply go?** Is a fixed output channel capturing the receipt?
8. **Is there an async boundary?** Did the reply arrive late, or is the worker/thread pool saturated?
9. **Did the operation already commit?** Timeouts can happen after commit; reconcile.
10. **Are retries keeping the same operation ID?** Ensure no duplicate side effect is created.

### 20.4. Distinguish Channel Activity from Business Outcomes

~~~text
Gateway method called:           1000
Messages accepted by channel:     998
Handlers invoked:                 995
Replies delivered to Gateway:     990
Business effects committed:       850
Idempotency results reused:       100
Business rejections:               45
~~~

These numbers are **illustrative**, not a balance equation that always adds up across metrics. Flows can include one-way calls, async retries, duplicate deliveries, and lost replies. Never jump to `"1000 - 990 = 10 lost orders"` without checking in-flight requests and committed outcomes.


## 21. Anti-Patterns Around `defaultRequestChannel`

| Anti-Pattern | Why Dangerous? | Replacement |
| --- | --- | --- |
| Treating `defaultRequestChannel` as reply channel | Gateway sends requests fine yet has no return path | Separate request and reply topology explicitly |
| Declaring channel name with no consumer | Nobody processes or dispatch fails | Define flow handler and test it |
| Using `QueueChannel` without a poller | Send succeeds, Gateway waits until timeout | Polling endpoint or different channel type |
| Assuming default is a fallback when override fails | Priority method breaks silently without falling back | Fix specific route, clear error policy |
| Putting two `DirectChannel` subscribers expecting fan-out | Point-to-point dispatch does not broadcast | PublishSubscribe / Recipient List / Scatter-Gather |
| Switching all methods to priority via global config | Breaks contracts and quotas | Method-level override or policy-driven Router |
| Appending a fixed output channel at end of Gateway flow | Reply leaves temporary reply channel | Proper bridge/reply path |
| Using `void` then reporting "committed" | Method may only have enqueued | Typed outcome / status API |
| Returning `null` when out of stock | Gateway can time out | `ReserveReceipt(REJECTED)` with reason |
| Asserting only `receipt.status` in tests | Misses misrouted channels | Assert lane markers and handler counters |
| Letting request channels enforce authorization | Callers can bypass controls | AuthN/AuthZ at trusted boundary |
| Using `orderId` as dedupe key across all operations | Wrongly blocks `CANCEL`/`AMEND` | Stable operation-level key |
| Using `MessageHeaders.ID` for retries | Redelivery creates a new envelope ID | Preserve business operation ID |
| Treating Gateway timeout as operation rollback | Commit may have occurred already | Reconcile and idempotent retry |
| Treating `defaultReplyTimeout` as hard limit on `DirectChannel` | Synchronous handlers can block longer | Service I/O deadlines and async design |
| Treating in-memory `QueueChannel` as a durable broker | Restarts lose queued requests | Durable messaging when required |
| Copying Java `replyChannel` over Kafka/JMS | Serialization errors or topology leaks | Transport reply-to + correlation |
| Routing by raw client-supplied tenant header | Cross-tenant data leakage | Trusted identity, ACLs, and validation |
| `PublishSubscribe` fan-out with a single Gateway reply | Multiple results go unaggregated | Aggregator / Scatter-Gather |
| Filter drops a child before Aggregator | Batch reply never completes | Typed child rejection outcome |
| Retrying validation errors endlessly | Retry storms, congested queues | Terminal reject + bounded retry |
| Testing one JVM and claiming multi-instance idempotency | Misses crashes/rebalances/races | Shared DB/transport integration tests |
| Logging all headers to debug Gateway | Exposes secrets and personal data | Safe structured logs |

## 22. Pre-Deployment Checklist

- [ ] `@MessagingGateway` sits on the right interface and the Gateway bean is component-scanned/registered.
- [ ] `defaultRequestChannel` points to a meaningful, properly declared/resolved request destination.
- [ ] Every non-overridden method uses the default per contract.
- [ ] Every `@Gateway(requestChannel = "...")` override is tested independently.
- [ ] An active consumer/`IntegrationFlow` receives messages on every request channel.
- [ ] `defaultRequestChannel`, `defaultReplyChannel`, and temporary `replyChannel` are not confused.
- [ ] When a method returns a value, the **reply** returns to the right caller with the right schema.
- [ ] Replies are not accidentally diverted to an output `QueueChannel` with no bridge back to the Gateway.
- [ ] Policies exist for `null`/`void`/no-reply, plus `requiresReply` on handlers if used.
- [ ] Business rejections return typed outcomes instead of silent timeouts.
- [ ] Request/send timeouts and reply timeouts have separate SLAs/time budgets.
- [ ] With `DirectChannel`, I/O durations inside handlers are bounded.
- [ ] With `ExecutorChannel`, the executor is bounded with backpressure and tracing/security context propagation.
- [ ] With `QueueChannel`/`PriorityChannel`, pollers, capacity, retries, and durability policies are defined.
- [ ] With `PublishSubscribeChannel`, fan-out and multiple replies are explicitly handled.
- [ ] Method argument mapping uses `@Payload`/`@Header` as needed without treating external input as trusted metadata.
- [ ] AuthN/AuthZ/tenant/priority quotas are enforced at the proper business boundary.
- [ ] Business operation IDs stay identical across client retries, broker redeliveries, and lane changes.
- [ ] Side effects are protected by shared idempotency/transactions at the owner.
- [ ] Technical failures are separated from terminal business rejections, with retry budgets and error handling.
- [ ] Late replies have reconcile/discard policies so final outcomes never emit twice.
- [ ] Splitter/Aggregator preserve group/child/operation IDs with timeouts and closed-group policies.
- [ ] Remote reply-to/correlation over HTTP/JMS/AMQP/Kafka is properly mapped and secured.
- [ ] Java `replyChannel`/`errorChannel` objects are never serialized to a broker.
- [ ] Unit tests cover business services; Spring context tests cover both default and override routes.
- [ ] Negative tests cover no subscriber, no poller, wrong reply output, and null returns.
- [ ] Dedicated metrics track request sends, handler invocations, reply receipts, timeouts, and business commits.
- [ ] High-cardinality IDs and PII are excluded from metric labels; logs follow security policy.

## 23. Hands-On Exercise: Default Gateway for Order Payments

An Order Processing service uses a Messaging Gateway for three operations:

- `authorizePayment(command)`: checks and holds payment limit.
- `capturePayment(command)`: settles an authorized payment.
- `refundPayment(command)`: refunds with stricter validation policy.

The desired Gateway interface uses a **default request channel** for authorize/capture, while refund goes through a **dedicated channel with authorization and auditing**.

### 23.1. Interface Design

Example contract:

~~~java
record PaymentCommand(
    String tenantId,
    String operationId,
    String orderId,
    long amountMinor,
    String currency
) {}

record PaymentReceipt(
    String operationId,
    String status,
    String reasonCode
) {}
~~~

**Requirements:**

1. Create `@MessagingGateway(defaultRequestChannel = "payments.commands")`.
2. Declare `authorizePayment` and `capturePayment` using the default channel; add a **verified** way to distinguish operation types in the payload/header so an internal Router separates the two commands.
3. Declare `@Gateway(requestChannel = "payments.refunds")` for `refundPayment`.
4. Diagram two `IntegrationFlow`s with input channels `payments.commands` and `payments.refunds`, along with their Routers/Service Activators.
5. Write Java DSL for each flow and a Gateway method returning `PaymentReceipt`.
6. Explain why checking only the method name `refundPayment` **is not enough** for authorization; principal/roles/limits are needed in the handler.
7. Write JUnit tests proving authorize and capture take the default route while refund takes the override; assert counters on all three handlers.
8. Test refund retried with the same operation ID after a lost reply: payment backend must not refund twice.
9. Explain why a new operation ID must never be generated on each Gateway retry.
10. Configure a `QueueChannel` with no poller to observe the Gateway waiting for reply; add a poller and prove the outcome changes.
11. Intentionally attach a fixed output channel unbridged back to the Gateway and write a bounded timeout test (no infinite wait).
12. Explain why `defaultReplyTimeout` does not preempt a handler running inside `DirectChannel`.
13. Design a typed `PaymentReceipt(status=REJECTED)` for invalid amounts, distinct from a technical error on payment API 503.
14. For a batch of five payment operations, use Splitter/Aggregator with typed child outcomes so an invalid child never drops its reply.
15. Add a `void audit(AuditEvent)` Gateway method and explain why `void` does not mean async committed.
16. Design metrics for Gateway routing, reply timeouts, idempotency hits, refund conflicts, and business commits.
17. Write a security test confirming client-supplied tenant/refund headers cannot bypass authorization or leak onto an outgoing broker.
18. Propose a migration path from `DirectChannel` to `ExecutorChannel` without losing replies/correlation or causing retry storms.

### 23.2. Acceptance Criteria

A solution satisfies the requirements when it proves **three independent properties**:

1. **Routing correctness:** each Gateway method sends to the expected default or overridden request channel.
2. **Request–reply correctness:** each reply-expecting method receives the expected typed outcome without misrouting to another queue or timing out needlessly.
3. **Business-effect correctness:** retries, redeliveries, and multiple instances never double-execute payments, double-refund, or produce two final decisions.

Never use "the API returned 200" or "service unit tests pass" as proof of all three properties at once.

## 24. Summary

**Gateway default request channel** is a key configuration of an interface-level Messaging Gateway in Spring Integration: it specifies **which channel requests enter when a method does not declare its own channel**. Methods with `@Gateway(requestChannel = "...")` override that choice for specific use cases. This lets callers work with a clean Java API while the integration layer handles routing, validation, handler invocation, and replies.

However, **a request destination is not a reply destination**. A Gateway returning results must have a valid reply path back to the caller; `DirectChannel`, `ExecutorChannel`, and `QueueChannel` impose different threading and timeout behavior. A Gateway can time out even after business commit, so retries need stable business operation IDs and owner-side idempotency. Across Router, Filter, Splitter, Aggregator, Gateway/error channels, and remote adapters, preserve correlation, separate typed business rejections from technical failures, and test both default and override routes alongside negative and late-reply paths.

A solid implementation does not stop at `@MessagingGateway(defaultRequestChannel = "reservations.commands")`. It pairs that with **channels backed by real consumers, explicit reply contracts, meaningful timeouts, proper security boundaries, idempotency, and tests proving both correct routing and correct outcomes**.

**References:** Gregor Hohpe & Bobby Woolf, *Enterprise Integration Patterns* (Messaging Gateway, Request-Reply, Service Activator, Content-Based Router, Correlation Identifier, Idempotent Receiver, Aggregator); Spring Integration Reference on Messaging Gateways, `@MessagingGateway`, `@Gateway`, Integration Component Scan, Message Channels, Java DSL, Service Activators, Retry/Error Handling, and Testing; Spring Framework on ApplicationContext and transaction management; Spring Messaging on `Message`/`MessageHeaders`; Java SE on records and concurrency.








