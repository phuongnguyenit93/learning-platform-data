# Gateway Sending One-Way Messages

## 1. Scenario: Calling a Java Method to Emit a Message Without Waiting for a Business Result

An ordering application needs to notify the system that an order has been received. Application service code wants to invoke an easy-to-understand Java API:

~~~java
orderSubmissionGateway.submit(command);
~~~

The rest of the system can process the event with Spring Integration: validate, Filter, Router, transform the payload, send to a broker, update audit logs, or send notifications. However, the caller **does not need to receive a business response object** from this invocation right away.

That is a classic case of a **Messaging Gateway sending a one-way message**: a Java interface turned by Spring Integration into an entry point that feeds messages into an integration flow, with a method that **does not require a reply payload**.

~~~mermaid
flowchart LR
    CALL["Application Service"] --> G["One-way Messaging Gateway"]
    G --> C["Request Channel"]
    C --> V["Filter / Transformer / Router"]
    V --> H["Consumer / Outbound Adapter"]
    H --> S["Side effect or durable handoff"]
~~~

Example command:

~~~text
SubmitOrder(
  operationId = "SUBMIT-901",
  orderId     = "ORD-901",
  tenantId    = "TENANT-A",
  amountVnd   = 850000
)
~~~

The service calls a method returning `void`. Yet **`void` does not mean the message is guaranteed to be durably persisted, processed successfully, immune to failure, or always executed asynchronously**. Those guarantees depend on the channel, consumer, adapter, transaction, and error-handling contract.

This lesson belongs to the **Messaging gateway** chapter of the `SPRING_INTEGRATION_PATTERN` module. The module focuses on learning Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows; practicing Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation, as well as testing and monitoring processing branches.

### Objectives

After this lesson, you will:

1. Understand **one-way messages** and the difference between a `void` Gateway and a request–reply Gateway.
2. Distinguish **one-way**, **asynchronous**, **fire-and-forget**, **durable enqueue**, **broker acknowledgment**, and **business completion**.
3. Create a `@MessagingGateway` with a `void` method and a request channel using Spring Integration 6.x.
4. Compare `DirectChannel`, `ExecutorChannel`, and `QueueChannel` across threading, latency, failure, and persistence.
5. Design error-handling paths when the caller does not receive a business reply.
6. Protect side effects with idempotency, retry/backoff, transport acknowledgment, and audit.
7. Write unit/integration tests verifying that commands go to the right channel and avoiding the misconception that returning `void` means business completion.

## 2. What Is One-Way?

In Enterprise Integration Patterns, **one-way** describes a **message exchange pattern**: the sender emits a message and does not require a corresponding reply message under that send's business protocol.

~~~text
Sender -------- Command/Event --------> Receiver
       (no immediate business reply required)
~~~

It differs from **request–reply**:

~~~text
Sender -------- Request -------------> Receiver
Sender <-------- Reply ---------------- Receiver
~~~

A one-way request can still trigger a whole series of downstream actions, including new events or status notifications over another channel. Those are **independent messages or an asynchronous workflow linked by identity/correlation**, not a "mandatory reply" to the original Java method.

### 2.1. Concepts Often Conflated

| Concept | Meaning | Does Not Automatically Guarantee |
|---|---|---|
| **One-way** | No business reply is required for this send. | Not synonymous with asynchronous. |
| **`void` Gateway method** | The Java caller receives no business return value. | Does not mean all exceptions are swallowed. |
| **Synchronous dispatch** | Consumer runs inside the call / on the same thread per channel semantics. | Does not require a reply. |
| **Asynchronous dispatch** | Handoff via executor/queue/broker; caller and consumer can run on different threads. | Not automatically durable. |
| **Fire-and-forget** | Informal term when the caller does not wait for a result. | Does not prove the message cannot be lost. |
| **Durable enqueue** | Infrastructure durably stores the message per contract. | Does not prove the consumer has finished. |
| **Broker ack/confirm** | Broker/transport confirms a milestone. | Does not prove the business effect committed. |
| **Business completion** | An authoritative business receipt/state exists. | Cannot be inferred solely from gateway return. |

### 2.2. Two Similar-Looking Snippets, Different Semantics

~~~java
// Both are void-returning Java APIs.
gateway.submit(command);

// Underneath may be a synchronous DirectChannel,
// or an ExecutorChannel, broker adapter, queue...
~~~

**The Java signature only establishes that the caller receives no reply payload.** The channel and endpoints determine dispatch behavior, return timing, error propagation, and the acceptance milestone.

### 2.3. One-Way Does Not Forbid Tracking Results

For long-running work, design a separate tracking path:

~~~text
Command SUBMIT-901
  -> Gateway one-way
  -> Accepted / queued
  -> Background order processing
  -> OrderProcessed event (operationId=SUBMIT-901)
  -> Status projection / notification
~~~

The caller can check the outcome via a query/status API or receive an event callback later. You must then distinguish **operation ID**, **delivery attempt**, **correlation ID**, and **business receipt**.

## 3. Why Use a Messaging Gateway Instead of Calling a MessageChannel Directly?

With Spring Integration, an application service could interact directly:

~~~java
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

boolean acceptedByChannel = channel.send(
        MessageBuilder.withPayload(command).build());
~~~

That approach forces the application service to know the Spring Messaging API and manually build messages/headers. A **Messaging Gateway interface** hides the messaging layer so the application service only sees a meaningful business Java method:

~~~java
interface OrderSubmissionGateway {
    void submit(OrderSubmission command);
}
~~~

At runtime, Spring Integration creates a **gateway proxy** that turns a method invocation into a message sent to the request channel.

### 3.1. Benefits

- **Decoupling:** application services have minimal dependency on `MessageBuilder`/`MessageChannel` APIs.
- **Clear intent:** `submit(...)` expresses business intent better than an abstract `send(...)` call.
- **Centralized metadata:** routing configuration, header mapping, and validation live at the ingress boundary.
- **Testability:** easy to fake the interface in unit tests and run the Spring flow in integration tests.
- **Swappable channels/adapters:** many infrastructure changes do not require editing the application caller.

### 3.2. Limitations

- Does not automatically ensure DB + broker atomicity.
- Does not automatically create a durable queue.
- Does not automatically make work async just because the return type is `void`.
- Does not automatically prevent duplicates.
- Does not automatically provide retry, error channel, or contract-compliant observability.
- Does not produce a business reply if the sender did not ask for one.

A Gateway is **an API boundary**, not every property of a messaging system.

## 4. Designing a One-Way Contract

### 4.1. Commands and Events Are Not the Same

A Gateway can emit:

- **Command:** asks a consumer to perform an action, e.g., `SubmitOrder`, `SendNotification`. Usually expects a responsible party to handle it.
- **Event:** announces something that already happened, e.g., `OrderPlaced`. May have multiple subscribers and no single designated owner.

If a method is `sendOrderNotification(...)`, clarify whether it produces a **command requesting a notification** or an **event that an order occurred**. An ambiguous API name can corrupt retry, idempotency, and ownership logic.

### 4.2. A Sample Contract

~~~text
Operation: SubmitOrder
  operationId: stable logical command ID
  orderId: business order ID
  amountVnd: positive integer in VND
  authenticatedTenant: derived at trusted boundary

Gateway:
  Java method: void submit(OrderSubmission command)
  request channel: orders.submit.input

Handoff semantics:
  Demo: synchronous DirectChannel dispatch
  Production: choose explicit durability/ack contract

Failures:
  Invalid command -> reject/quarantine with reason
  Technical failures -> bounded retry/error handling
  Business completion -> separate status/receipt/event
~~~

**Important:** If the caller needs to know the command was **durably accepted**, a `void`-only API may not be explicit enough; you might need an `AcceptedReceipt` outcome or a transactional outbox model. Returning `void` after sending to an in-memory channel is not a promise of durable persistence.

### 4.3. Operation Identity Differs from Spring Message ID

~~~text
Business operationId = SUBMIT-901
Spring MessageHeaders.ID, attempt #1 = UUID-A
Spring MessageHeaders.ID, retry #2   = UUID-B
~~~

The same logical command can pass through multiple Spring message instances. For side-effecting operations such as charging or creating orders, downstream needs a **stable `operationId` / business idempotency key**, not deduplication by runtime UUID.

### 4.4. Do Not Treat Self-Declared Tenant as Authorization

A command carrying `tenantId=TENANT-A` does not by itself prove the caller is authorized for tenant A. At trusted ingress, you must bind identity from the principal/adapter context and validate the request. In demos, a tenant field may be placed on the command for illustration, but **it must never be treated as authorization**.

## 5. Java: A Basic One-Way Gateway

The examples use Java 17+, Spring Framework/Spring Integration 6.x, and Spring Test/JUnit 5. Classes/records/interfaces are assumed to be in the same package and placed in separate files in a real project.

### 5.1. Command Payload

~~~java
import java.math.BigDecimal;

record OrderSubmission(
        String operationId,
        String orderId,
        BigDecimal amountVnd) {

    OrderSubmission {
        if (operationId == null || operationId.isBlank()
                || orderId == null || orderId.isBlank()
                || amountVnd == null
                || amountVnd.signum() <= 0) {
            throw new IllegalArgumentException(
                    "INVALID_ORDER_SUBMISSION");
        }
    }
}
~~~

There are no Spring Messaging imports in `OrderSubmission`: it is a business/application command. The constructor DTO validator only enforces **simple invariants**; at raw ingress, you still need authentication, schema checks, and malformed payload checks before instantiating the typed command.

### 5.2. Gateway Interface with `void`

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway
interface OrderSubmissionGateway {

    @Gateway(requestChannel = "orders.submit.input")
    void submit(OrderSubmission command);
}
~~~

**Key point:** `@MessagingGateway` declares an integration gateway interface; `@Gateway(requestChannel=...)` maps the method call to a channel. The `void submit(...)` signature states that **there is no business return value to read**.

The application service does not need to build `Message<OrderSubmission>` just to call this API. However, it must still handle errors and obtain a stable operation ID from the proper source.

### 5.3. Service Calling the Gateway

~~~java
import java.math.BigDecimal;

final class CheckoutApplicationService {
    private final OrderSubmissionGateway gateway;

    CheckoutApplicationService(OrderSubmissionGateway gateway) {
        this.gateway = gateway;
    }

    void submitOrder(String orderId, String operationId) {
        gateway.submit(new OrderSubmission(
                operationId,
                orderId,
                new BigDecimal("850000")));

        // Do not assert from this that Payment/Inventory finished.
        // Depending on the channel, dispatch may be synchronous or handed off.
    }
}
~~~

A `submit(...)` command retried due to an HTTP retry must be given the **same `operationId`** if it represents the same logical operation. Never generate a fresh UUID inside the handler on every receipt and treat it as a new order.

## 6. Spring Integration Java DSL: One-Way Handling via DirectChannel

### 6.1. Synchronous Execution Diagram

~~~mermaid
sequenceDiagram
    participant A as Application Service
    participant G as One-way Gateway Proxy
    participant C as DirectChannel
    participant H as Message Handler
    A->>G: submit(command): void
    G->>C: Message(command)
    C->>H: invoke handler in caller thread
    H-->>C: return normally
    C-->>G: send completed
    G-->>A: return void
    Note over A,H: No business reply payload
~~~

In this example, the handler executes **synchronously** with the call to `DirectChannel`. Thus the caller can be held until the handler finishes. Not returning business data **is different from** not waiting for the work.

### 6.2. Probe Recording Commands for Observation

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

final class SubmissionProbe {
    private final List<OrderSubmission> received =
            new CopyOnWriteArrayList<>();

    void record(OrderSubmission command) {
        received.add(command);
    }

    List<OrderSubmission> snapshot() {
        return List.copyOf(received);
    }
}
~~~

`SubmissionProbe` is for testing, **not a database or broker**. It does not guarantee durability across JVM restarts, does not enforce tenant isolation, and does not protect idempotency.

### 6.3. Configuring Gateway, Channel, and Terminal Handler

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan
class OneWayGatewayConfiguration {

    @Bean(name = "orders.submit.input")
    MessageChannel orderSubmitInput() {
        return new DirectChannel();
    }

    @Bean
    SubmissionProbe submissionProbe() {
        return new SubmissionProbe();
    }

    @Bean
    IntegrationFlow processSubmittedOrders(SubmissionProbe probe) {
        return IntegrationFlow.from("orders.submit.input")
                .handle(
                        OrderSubmission.class,
                        (command, headers) -> {
                            probe.record(command);
                            return null; // Terminal one-way handler.
                        })
                .get();
    }
}
~~~

Place `OrderSubmissionGateway` and the configuration in **a scanned demo package** or configure the scan scope explicitly. `@IntegrationComponentScan` finds `@MessagingGateway` interfaces and registers proxies; `@EnableIntegration` enables the required infrastructure.

**Note:** The handler above returns `null` to represent a **terminal side-effect endpoint** (producing no reply payload). This is an intentional choice for the demo. Do not treat `null` as an external system's "completed" business receipt.

### 6.4. What Happens When Calling the Gateway?

~~~java
OrderSubmission command = new OrderSubmission(
        "SUBMIT-901",
        "ORD-901",
        new java.math.BigDecimal("850000"));

gateway.submit(command);
~~~

A successful call through `DirectChannel` in this example passes these milestones:

1. The Java method on the gateway proxy is invoked.
2. The gateway builds a message with payload `OrderSubmission`.
3. The message is sent to `orders.submit.input`.
4. `DirectChannel` dispatches to the subscribed handler.
5. The handler records into `SubmissionProbe` and returns `null`.
6. The gateway method returns `void`.

There is no step returning an `OrderResult` or `PaymentReceipt`. If the real handler is long-running, the caller will **wait for that operation on the synchronous path**, unless an asynchronous boundary is introduced.

### 6.5. When Downstream Throws an Exception in DirectChannel

If the handler throws `IllegalStateException` or a Spring Messaging exception, calling `void submit(...)` can still **throw the error back to the caller** through the gateway/synchronous dispatch, possibly wrapped by the framework in `MessagingException`.

~~~mermaid
sequenceDiagram
    participant A as Caller
    participant G as Gateway
    participant C as DirectChannel
    participant H as Handler
    A->>G: submit(command)
    G->>C: send
    C->>H: invoke
    H--xC: exception
    C--xG: propagate
    G--xA: exception (possibly wrapped)
~~~

**Therefore the statement "a one-way gateway has no reply so it has no errors" is false.** `void` only removes the business return value; exception propagation depends on the synchronous/asynchronous boundary and endpoint configuration.

## 7. Integration Test for a Synchronous One-Way Gateway

### 7.1. Only One Command Reaches the Handler

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(OneWayGatewayConfiguration.class)
@DirtiesContext(classMode =
        DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class OneWayGatewayIntegrationTest {

    @Autowired
    OrderSubmissionGateway gateway;

    @Autowired
    SubmissionProbe probe;

    @Test
    void voidGatewayDispatchesCommandWithoutBusinessReply() {
        OrderSubmission command = new OrderSubmission(
                "SUBMIT-901",
                "ORD-901",
                new BigDecimal("850000"));

        gateway.submit(command);

        assertEquals(1, probe.snapshot().size());
        assertEquals(command, probe.snapshot().get(0));
    }
}
~~~

Asserting immediately after the method call is valid here **because the example uses synchronous `DirectChannel`**. If switched to `ExecutorChannel` or a broker, this test could no longer assume the handler has already executed when `submit(...)` returns.

### 7.2. A Gateway Method Can Be Unit Tested with a Fake

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CheckoutApplicationServiceTest {

    @Test
    void callsGatewayWithStableOperationId() {
        List<OrderSubmission> sent = new ArrayList<>();
        OrderSubmissionGateway fake = sent::add;
        CheckoutApplicationService service =
                new CheckoutApplicationService(fake);

        service.submitOrder("ORD-901", "SUBMIT-901");

        assertEquals(1, sent.size());
        assertEquals("SUBMIT-901",
                sent.get(0).operationId());
        assertEquals("ORD-901",
                sent.get(0).orderId());
        assertEquals(new BigDecimal("850000"),
                sent.get(0).amountVnd());
    }
}
~~~

This unit test proves the application service invokes the **Java interface** properly; it does not prove the Spring proxy, channel subscription, broker, or business side effects. Distinguish test scopes so you do not attribute guarantees to a unit test that it never checked.

### 7.3. A `void` Method Can Still Throw

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OneWayGatewayContractTest {

    @Test
    void gatewayInterfaceDoesNotPromiseNeverToThrow() {
        OrderSubmissionGateway failing = command -> {
            throw new IllegalStateException(
                    "SYNCHRONOUS_DISPATCH_FAILED");
        };

        assertThrows(IllegalStateException.class, () ->
                failing.submit(new OrderSubmission(
                        "SUBMIT-2", "ORD-2",
                        new BigDecimal("100000"))));
    }
}
~~~

This example illustrates a property of the **Java interface**. With a real Spring Gateway, the exception may be wrapped by the framework; do not assert a specific exception class without verifying the cause chain and actual configuration.

### 7.4. Not Returning a Result Differs from Not Knowing the Status

While the demo handler only writes to a probe, in production a handler might:

- Call an external API and wait for a response.
- Write an outbox row to a database.
- Send a message to an outbound broker adapter.
- Enqueue onto another in-memory channel.

**The success milestones differ.** Tests must assert the exact milestone required by the application contract—for instance, **durable outbox persisted** or **broker confirm**—not merely "the gateway method returned."

## 8. When Asynchronous Is Needed: ExecutorChannel

### 8.1. Adding a Thread Boundary

If the caller should not wait for a long handler, you can choose an asynchronous channel/adapter.

~~~mermaid
sequenceDiagram
    participant A as Caller
    participant G as Void Gateway
    participant E as ExecutorChannel
    participant W as Worker Thread
    A->>G: submit(command)
    G->>E: dispatch to executor
    E-->>G: task submitted/accepted
    G-->>A: return void
    E->>W: run message handler
    W->>W: process command
    Note over A,W: Caller may return before processing is complete
~~~

What is new is the **executor boundary**. The Java signature is still `void`; the reason it is asynchronous is not `void`, but because `ExecutorChannel` dispatches through a thread pool.

### 8.2. Bounded Executor Example

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.core.task.TaskExecutor;

import java.util.concurrent.ThreadPoolExecutor;

@Configuration
class AsyncOrderFlowConfiguration {

    @Bean(name = "orderGatewayExecutor")
    ThreadPoolTaskExecutor orderGatewayExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("orders-oneway-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean(name = "orders.async.input")
    MessageChannel asyncOrderInput(
            @Qualifier("orderGatewayExecutor")
            TaskExecutor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean
    IntegrationFlow asyncOrderHandler(SubmissionProbe probe) {
        return IntegrationFlow.from("orders.async.input")
                .handle(OrderSubmission.class,
                        (command, headers) -> {
                            probe.record(command);
                            return null;
                        })
                .get();
    }
}
~~~

The configuration above only illustrates **thread-handoff**; it must be paired with a `SubmissionProbe` bean, a gateway interface pointing to `orders.async.input`, and appropriate infrastructure in a dedicated demo context.

### 8.3. Corresponding Gateway Interface

~~~java
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.annotation.Gateway;

@MessagingGateway
interface AsyncOrderSubmissionGateway {

    @Gateway(requestChannel = "orders.async.input")
    void submit(OrderSubmission command);
}
~~~

In an application with multiple gateways, restrict component scanning scope or place examples in separate packages/contexts. Never register two interfaces with the same bean name and rely on accidental behavior.

### 8.4. Not "Sent Successfully" If the Executor Rejected It

The pool and queue have finite capacity. Under overload, `ExecutorChannel` may fail to submit the task, and a rejection error can appear immediately when calling the Gateway. Therefore:

~~~text
Gateway void return
    ≠ job always queued
    ≠ job processed
    ≠ job persisted across restart
~~~

A bounded thread pool makes overload observable. Yet **it is not durable**: if the process dies, tasks waiting in memory can be lost. Production needs retry, fallback, backpressure policies, and—if reliability across restarts is required—a durable handoff.

### 8.5. Do Worker Exceptions Still Throw Back to the Caller?

If the task has been handed off to a worker and **the worker throws an exception after the caller returned**, the caller cannot receive the exception synchronously as with `DirectChannel`. Spring Integration can publish an `ErrorMessage` to an error channel depending on the error-handling context/configuration, or use a dedicated handler; **it must be configured and tested**, rather than assuming all async errors automatically go to the same place.

~~~text
Caller returns
       |
       v
Async worker fails
       |
       +-> configured error channel / failure handler
       +-> retry/recovery/DLQ according to endpoint/adapter
       +-> alert & audit unresolved operation
~~~

**Error design is a mandatory part of a one-way asynchronous flow** because there is no immediate business reply to represent failure.

### 8.6. Testing Async Properly

With async, do not write:

~~~java
gateway.submit(command);
assertEquals(1, probe.snapshot().size()); // Can race.
~~~

Use `CountDownLatch`, `BlockingQueue.poll(timeout)`, or a deadline-bounded await mechanism. If a test uses a message handler waiting on a latch, release the latch in `finally` so worker threads do not hang. Never use `Thread.sleep(...)` and treat it as proof that the handler processed durably.
## 9. QueueChannel: Decoupling Send and Receive Time, Not Necessarily Durable

### 9.1. In-Memory Store-and-Forward

Spring Integration's `QueueChannel` can accept messages into a queue so a consumer/poller can pick them up later.

~~~text
Caller -> Gateway (void) -> QueueChannel (in-memory queue)
                                 |
                           scheduled poller
                                 |
                                 v
                           Message handler
~~~

Unlike `DirectChannel`, the consumer can run later on a poller thread. Unlike `ExecutorChannel`, the queue has **channel-level polling/storage semantics**, not just submitting a task to an executor.

**However, a plain `QueueChannel` is not a durable message broker.** An in-memory queue can lose data on JVM restart; use a message store, persistent channel, or proper broker if the contract requires crash recovery.

### 9.2. QueueChannel and Polling Consumer Example

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
class QueuedOrderConfiguration {

    @Bean(name = "orders.queued.input")
    MessageChannel queuedOrderInput() {
        return new QueueChannel(100);
    }

    @ServiceActivator(
            inputChannel = "orders.queued.input",
            poller = @Poller(fixedDelay = "1000"))
    public void consumeQueuedOrder(OrderSubmission command) {
        // Simulate side effect; production needs transaction,
        // idempotency, error/retry, and monitoring.
        System.out.println("Handled order " + command.orderId());
    }
}
~~~

This is an abbreviated example for a **pollable channel**. When run in a Spring Integration context with the corresponding infrastructure beans, the poller pulls messages and invokes the handler. In real code, replace `System.out.println` with sanitized structured logs and an explicit application handler.

### 9.3. Gateway Pointing to a Queue

~~~java
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.annotation.Gateway;

@MessagingGateway
interface QueuedOrderSubmissionGateway {

    @Gateway(requestChannel = "orders.queued.input")
    void submit(OrderSubmission command);
}
~~~

`submit(...)` can return as soon as the message is accepted into the queue, **before the poller invokes the consumer**. Do not record `orderStatus=COMPLETED` in the caller just because the call returned.

### 9.4. Queue Full and Send Timeout

If the queue has capacity 100 and is full, the next send can **block, time out, or fail depending on the send contract and Gateway/channel timeout configuration**. Not every queue accepts messages forever.

An operational runbook needs:

- Current queue depth and capacity.
- Consumer throughput, poller state, and backlog age.
- Enqueue time and failure/timeout counts.
- Recovery when the poller stops or the consumer throws.
- Backpressure on callers/ingress.
- Retry policies that do not duplicate side effects.

Never turn a queue into an "unbounded buffer"; without capacity and retention controls, a consumer outage can exhaust resources.

### 9.5. In-Memory Channels and Durable Queues Are Different Contracts

| Design | Can Return Before Handler? | Survives Process Restart? | Needs Error Policy? |
|---|---|---|---|
| `DirectChannel` | Usually no if handler is synchronous. | Not storage. | Yes. |
| `ExecutorChannel` | Possible. | Not by default. | Yes; async errors are hard to return to caller. |
| In-memory `QueueChannel` | Possible. | Not by default. | Yes; polling/retry/backlog. |
| Persistent message store/queue | Possible. | Depends on store/transaction config. | Yes; ack/redelivery/idempotency. |
| External broker | Possible. | Depends on durability, retention, confirms, and consumer config. | Yes; broker acknowledgment differs from business commit. |

Never promise "exactly-once" simply because a queue has "persistent" in its name.

## 10. One-Way Gateway Sending via Kafka, RabbitMQ, or JMS

In real applications, a Gateway often sends commands into a Spring Integration flow that has an **outbound channel adapter**, such as:

~~~mermaid
flowchart LR
    A["Application Service"] --> G["void Messaging Gateway"]
    G --> C["Request Channel"]
    C --> V["Validate + Enrich headers"]
    V --> S["Serializer / Outbound Adapter"]
    S --> B[("Kafka / RabbitMQ / JMS")]
    B --> R["Inbound Consumer"]
    R --> I["Idempotent Business Handler"]
~~~

The one-way API does not depend on which broker is connected. However, **message acknowledgment and error semantics are determined by the adapter/broker**, not the Java return type.

### 10.1. Outbound Publish Milestones

~~~text
T0: Gateway method invoked.
T1: Spring request channel accepts/dispatches message.
T2: Outbound adapter serializes command.
T3: Network publish attempted.
T4: Broker may acknowledge/confirm receipt.
T5: Consumer receives record.
T6: Consumer commits business effect.
T7: Consumer acknowledges processed delivery.
~~~

What is guaranteed when `gateway.submit(...)` returns depends on **where the flow/adapter returns control**. A synchronous outbound adapter may wait for a specific publish condition; an async producer may only enqueue into a client buffer. Never rely on `void` to infer that T4, T6, or T7 has been reached.

### 10.2. Broker Acknowledgment Is Not Business Acknowledgment

~~~text
Broker accepted record     -> messaging handoff milestone
Consumer processed record  -> consumer processing milestone
DB update committed        -> business persistence milestone
External payment completed -> another side-effect milestone
~~~

A message broker confirm only states that the broker fulfilled its acknowledgment contract; it does not prove the consumer updated the database or completed payment.

### 10.3. When Commands Must Not Be Lost Between DB and Broker

An application might write business state and then call the Gateway to publish an event:

~~~text
1. DB order transaction COMMIT.
2. Process CRASH.
3. Gateway has not published event yet.
~~~

The system changed state yet lost the event. Conversely, publishing before DB commit can deliver an event to consumers even if the DB rolls back. This is the **dual-write problem**.

A common solution is the **transactional outbox**:

~~~mermaid
flowchart LR
    API["Order API"] --> TX["Database Transaction"]
    TX --> ORDER[("Orders")]
    TX --> OUTBOX[("Outbox event")]
    OUTBOX --> RELAY["Publisher / One-way Gateway"]
    RELAY --> BROKER[("Durable Broker")]
    BROKER --> INBOX["Idempotent Consumer"]
~~~

Within the same database transaction, the application writes both the business row and the outbox row with a stable event ID. The relay can retry publishing without losing intent. Consumers must deduplicate because the relay may publish twice if a broker ack is lost.

**A Gateway does not replace an outbox.** It is a way to inject messages into a transport flow; atomicity with a business transaction requires separate design.

### 10.4. What If the Requirement Is Only "At-Most-Once Send"?

Not every message is as critical as a payment. A telemetry ping or noncritical cache warm-up may tolerate losing some messages, cutting cost with best-effort delivery. Yet that choice must **be documented in the contract/SLO**:

~~~text
Event type: CACHE_WARMUP_HINT
Reliability: best-effort
Loss tolerance: acceptable
Retry: limited or none
Business impact: cache may warm later
~~~

By contrast, `CHARGE_PAYMENT` or `CREATE_ORDER` should not casually use the same semantics. One-way is an **exchange pattern**, whereas reliability is a **business decision**.

## 11. Acknowledgment: Received, Persisted, or Processed?

### 11.1. Defining Success for the Caller

It can be broken into levels:

| Level | Meaning | Appropriate API |
|---|---|---|
| L0: Caller invoked API | Java method was called. | Not suitable as a business guarantee. |
| L1: Channel accepted | Gateway delivered to the channel per semantics. | `void` may suffice if best-effort. |
| L2: Durable enqueue committed | Proof of write to queue/outbox/broker exists. | May require an explicit accepted receipt/transaction. |
| L3: Consumer accepted | Consumer confirmed it will process per contract. | Usually asynchronous status. |
| L4: Business completed | Authoritative business outcome/receipt exists. | Status query, event/callback, or request–reply if truly needed. |

A `void` method can fit L1 or serve as part of an L2 API with explicit transaction/commit semantics. But if the caller needs `paymentReceiptId` or `orderStatus` immediately, a **one-way `void` Gateway is not an informative enough interface**.

### 11.2. Do Not Return HTTP 200 "Completed" Just Because the Gateway Returned

REST controller example:

~~~text
POST /orders/submit
   -> gateway.submit(command)
   -> return 200 "ORDER_COMPLETED"
~~~

This is a dangerous contract if processing actually happens afterward. When async, one option is returning **202 Accepted** with an operation/status reference *if* the server has fulfilled the work-acceptance contract, paired with a status endpoint or event to query the outcome. Nor does `202` by itself guarantee a durable queue; it must match actual execution.

### 11.3. Consumer Broker Ack

A consumer may:

- Ack **after** the business DB transaction commits.
- Use a transactional consumer/producer where supported by the broker.
- Retry after failure and redeliver.
- Route to a DLQ after policy exhaustion.

When **business commit succeeds but the ack is lost**, redelivery can happen; that is why the handler needs idempotency. You cannot claim "it's one-way so there are no duplicates" when transports typically lean toward at-least-once.

## 12. Error Handling for a One-Way Gateway

### 12.1. Four Failure Locations

~~~mermaid
flowchart TD
    G["void Gateway"] --> C{"Request channel"}
    C -->|No subscriber / rejection / timeout| E1["Dispatch failure"]
    C -->|Accepted| T["Transformer / Validator"]
    T -->|Mapping error| E2["Validation / contract handling"]
    T -->|OK| A["Async / Broker boundary"]
    A -->|Publish / network failure| E3["Transport recovery"]
    A -->|Delivered| H["Business handler"]
    H -->|Processing failure| E4["Business retry / reconciliation"]
~~~

Each failure can happen **before or after** `submit(...)` returns. Never write a catch-all handler assuming the caller always sees the error.

### 12.2. DirectChannel: Errors Can Propagate Back to the Caller

With a synchronous handler, exceptions from the handler can propagate up the call stack. At the application boundary:

~~~java
try {
    gateway.submit(command);
} catch (RuntimeException dispatchFailure) {
    // Decide retry/rejection based on error type.
    // Do not conclude the side effect did not occur if an external call was already made.
    throw dispatchFailure;
}
~~~

This snippet only illustrates exception visibility. It is **not a retry policy**, and it does not mean an immediate retry is safe. If an external service committed before the exception reached the caller, repeating the operation can create duplicate side effects.

### 12.3. Executor/Queue/Broker: Errors May Only Be Visible at the Consumer

Once the caller has returned, consumer errors need a clear path:

~~~text
Async worker
  -> exception
  -> configured error handling
       -> classify retryable?
       -> bounded retry/backoff
       -> DLQ/quarantine if exhausted
       -> audit failure state + alert
~~~

In Spring Integration, `ErrorMessage` and `errorChannel` are error-handling mechanisms within the appropriate execution context. **Do not claim the global `errorChannel` automatically catches every error from a Kafka deserializer, HTTP mapping, `ExecutorChannel`, or custom callback.** Check the specific adapter/error handler and test failures at that exact point.

### 12.4. An Error Channel Is Not a Business Reply

An `ErrorMessage` handled by a monitoring/recovery flow does not mean a `void` Gateway method will automatically receive an `OrderFailed` reply. If the caller must track outcomes, you need an **operation status store**, callback, or event tied to business correlation.

### 12.5. Retry Advice Needs Scope Awareness

| Failure Point | Should Retry? | Condition |
|---|---|---|
| No subscriber / misconfiguration | Do not retry indefinitely. | Fix wiring/deployment. |
| Executor temporarily overloaded | Bounded backoff possible. | Prevent queue overload; preserve intent. |
| Broker publish timeout | Possible, though publish outcome is unclear. | Stable message ID / dedupe. |
| Deterministic validation failure | Do not auto-retry indefinitely. | Source fix / schema update. |
| Database temporarily unavailable | Possible. | Idempotent transaction and retry policy. |
| Remote payment timed out | Safe to retry only with remote idempotency/reconciliation. | May have committed already. |
| Unauthorized tenant | No. | Security audit/reject. |
| Final business rejection | Per business contract. | Do not turn into fake success. |

### 12.6. Do Not Rely on Caller Retries as the Sole Recovery Mechanism

If the Gateway returns after enqueueing into an in-memory queue and the JVM crashes, the caller may never know the message was lost. Relying solely on "the caller will call again" risks dropped work; if it does call again, it risks duplicates. High reliability requires a durable record at an authoritative boundary (outbox/queue/inbox ledger) and reconciliation, not just a `try-catch` around a `void` method.

## 13. Idempotency: A One-Way Gateway Can Still Trigger Duplicate Processing

### 13.1. At-Least-Once Differs from Exactly-Once

With a broker or outbox relay, the same logical command/event can be delivered multiple times:

~~~text
T0  SUBMIT-901 published.
T1  Consumer receives SUBMIT-901.
T2  Consumer commits order.
T3  Consumer crashes before broker ack.
T4  Broker redelivers SUBMIT-901.
T5  Consumer sees same logical operation.
~~~

If the handler lacks idempotency, T5 can create another order or double-charge. **A one-way Gateway does not prevent duplicates automatically.** A stable operation ID lets the consumer recognize the same logical intent even if the Spring Message ID or broker offset changes.

### 13.2. Choosing the Idempotency Key at the Right Level

| Scenario | Suitable Key (Illustrative) | Why |
|---|---|---|
| Create order command | `tenant + CREATE_ORDER + operationId` | Same submit command gets retried. |
| Send order notification | `tenant + NOTIFY_ORDER + eventId + recipient` | Each recipient needs to be notified once. |
| Payment charge | `merchant + CHARGE + paymentOperationId` | Prevents duplicate charges. |
| Audit projection | `tenant + AUDIT_CONSUMER + eventId` | Same event must still be processed by other consumers. |
| Split batch item | `batchId + childId + operationType` | Avoids wrongly blocking distinct children. |

**Do not use** just `orderId` if one order can undergo multiple valid operations (`CREATE`, `CANCEL`, `ADJUST`, `REFUND`). Nor should you use `traceId`/`correlationId` alone, since they can group multiple messages.

### 13.3. In-Memory Duplicate Guard Demo Is for Learning Only

~~~java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

final class DemoOnceOnlyHandler {
    private final Set<String> seen =
            ConcurrentHashMap.newKeySet();
    private final AtomicInteger applied = new AtomicInteger();

    void handle(OrderSubmission command) {
        if (!seen.add(command.operationId())) {
            return; // Same key observed in this JVM.
        }
        applied.incrementAndGet(); // Simulated effect.
    }

    int appliedCount() {
        return applied.get();
    }
}
~~~

This code only demonstrates **in-JVM deduplication while state lives in memory**. It is **not a production implementation**: if the process crashes after `seen.add(...)` but before the effect, the retry is skipped; if the effect occurs before the record is durably saved, a retry can apply the effect a second time.

### 13.4. Unit Testing the Idempotency Concept for the Same Operation

~~~java
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OneWayDuplicateCommandTest {
    @Test
    void duplicateCommandHasOneSimulatedEffectInMemory() {
        DemoOnceOnlyHandler handler = new DemoOnceOnlyHandler();
        OrderSubmission same = new OrderSubmission(
                "SUBMIT-901",
                "ORD-901",
                new BigDecimal("850000"));

        handler.handle(same);
        handler.handle(same);

        assertEquals(1, handler.appliedCount());
    }
}
~~~

Such a passing unit test **does not prove** multi-node safety, database transactions, broker acks, remote payments, crash recovery, or business status correctness.

### 13.5. Durable Operation Ledger

For consumers requiring durable processing, consider this design:

~~~text
Operation key:
  (authenticatedTenant, operationType, operationId)

State:
  NEW -> IN_PROGRESS -> COMPLETED
                     -> FAILED_RETRYABLE
                     -> OUTCOME_UNKNOWN -> reconciliation

Stored information:
  payload fingerprint
  attempt/lease and fencing version
  authoritative business receipt
  createdAt/updatedAt
  policy/retention
~~~

A sample table:

~~~sql
CREATE TABLE order_command_inbox (
    tenant_id        VARCHAR(100) NOT NULL,
    operation_type   VARCHAR(100) NOT NULL,
    operation_id     VARCHAR(120) NOT NULL,
    payload_hash     VARCHAR(128) NOT NULL,
    operation_state  VARCHAR(40) NOT NULL,
    receipt_ref      VARCHAR(160),
    updated_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation_type, operation_id)
);
~~~

This is an **illustrative schema**, omitting leases, concurrency fencing, audit, cleanup, receipt versions, and tenant authorization. For business effects in the same DB, unique constraints and transactions can provide atomicity. For remote side effects over HTTP, you still need a **remote idempotency key** or reconciliation because a DB and an HTTP call do not form one atomic transaction.

### 13.6. Same Key, Different Payload Must Be Detected

~~~text
Attempt A:
  operationId=SUBMIT-901
  amountVnd=850000

Attempt B:
  operationId=SUBMIT-901
  amountVnd=950000
~~~

Do not treat B simply as a duplicate success of A. You need **payload fingerprinting/canonicalization** and an `OPERATION_CONFLICT` outcome or an authorized correction workflow. If the caller wants to modify a submitted order, define a **new operation** (e.g., `ADJUST_ORDER`) instead of silently altering the payload under the same operation ID.

### 13.7. Handler Completed, Caller Unaware

In one-way mode, the caller gets no business reply; this is why you need:

- A query API keyed by `operationId`.
- Completion events carrying correlation/causation.
- A receipt/ledger with durable status.
- Deadlines and alerts for pending operations.
- Idempotent handling of late replies or duplicate completion events.

Do not write "once gateway method returns, mark COMPLETED" logic in the application service.

## 14. Filter, Validation, and One-Way Discard

### 14.1. Validation Before Side Effects

A command can be sent one-way and still be invalid:

~~~text
SubmitOrder(
  operationId = SUBMIT-901,
  amountVnd   = -850000
)
~~~

If the DTO constructor does not validate (for example, a raw decoded DTO), a validation step is needed:

~~~mermaid
flowchart LR
    G["Void Gateway"] --> V["Validate"]
    V --> F{"Valid?"}
    F -->|Yes| B["Business handler"]
    F -->|No| Q["Quarantine / reject"]
~~~

A `Filter` returning false can drop the message from the main flow. If audit/replay is required, configure a `discardChannel` and a durable handler/queue; **do not assume rejected messages are saved automatically**.

### 14.2. A Filter Can Cause "Silent Success"

With `DirectChannel`, a Filter can drop the command without throwing per configuration. The `void` Gateway may return normally even though the business handler never ran. That is not a Gateway bug; it is an **underspecified one-way and Filter contract**.

If the caller must be notified immediately of ineligibility, a synchronous validation step **before calling the Gateway** or an API returning a typed rejection result may fit better.

### 14.3. Rejection Differs from Technical Error

| Case | Example | Handling |
|---|---|---|
| Invalid business input | Negative amount. | Rejection/quarantine or error contract. |
| Unsupported message schema | Unknown version. | Compatibility quarantine, producer upgrade. |
| Tenant unauthorized | Caller lacks permission to place order. | Security rejection/audit. |
| Channel not subscribed | No consumer handler. | Deployment/technical failure. |
| Database unavailable | Handler cannot commit. | Bounded retry/backoff/error path. |
| Duplicate already completed | Same `operationId`. | Return/use previous outcome, ack duplicate per contract. |

Do not turn every exception into a business validation failure, nor treat a duplicate as meaning the same thing as invalid.

### 14.4. Gateway and Quarantine

If a one-way flow sends an invalid command to quarantine, record:

~~~text
quarantineId      = Q-901
operationId       = SUBMIT-901
trustedTenant     = TENANT-A
source            = order-api
reasonCodes       = [INVALID_AMOUNT]
payloadReference  = protected-ref
validationVersion = orders-v3
state             = NEW
~~~

Never log raw payment/customer payloads or credentials into error text. If business needs replay, the operator must be authorized for that tenant/resource, revalidate under the defined policy, preserve the idempotency key, and maintain full audit logs.

### 14.5. A Synchronous Flow Can Be a Good Choice

Not every one-way operation has to be asynchronous. If a command is small, non-blocking, makes no network calls, and errors should propagate to the caller, `DirectChannel` with a terminal handler can be simpler than an executor or broker. Only add async when latency, throughput, isolation, and fault-tolerance requirements **genuinely** demand it.

## 15. Metadata, Headers, and Correlation

### 15.1. One-Way Lacks a Business Reply, Still Needs Correlation

In a workflow:

~~~text
Checkout CHECKOUT-88
  -> Gateway sends SubmitOrder SUBMIT-901
  -> OrderSubmitted event EVT-911
  -> InventoryReserved event EVT-912
  -> NotificationRequested event EVT-913
~~~

Messages can share `correlationId=CHECKOUT-88` and carry `causationId` pointing to the causing message/operation. Correlation serves **tracing and workflow stitching**, and does not automatically serve as the idempotency key for every message.

### 15.2. How to Pass Metadata?

You can use custom Spring headers or a typed envelope:

~~~java
record OrderCommandEnvelope(
        String eventId,
        String correlationId,
        String authenticatedTenant,
        OrderSubmission payload) {}
~~~

However, `authenticatedTenant` is only trusted if **produced by a real security boundary**, not because of its field name or client assertion.

When using `@Header` on a method parameter:

~~~java
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.messaging.handler.annotation.Header;

@MessagingGateway
interface CorrelatedOrderGateway {

    @Gateway(requestChannel = "orders.submit.input")
    void submit(
            OrderSubmission command,
            @Header("businessCorrelationId")
            String correlationId);
}
~~~

Callers may supply correlation per the API contract, but correlation **is not authorization**. If privileged headers like tenant, source, or route must be protected, construct them from the authenticated context at the adapter/application boundary.

### 15.3. Spring `MessageHeaders.ID` Can Change When Messages Are Rebuilt

~~~text
Gateway builds Spring message:
  headers.id = UUID-A
  businessOperationId = SUBMIT-901

Broker consumer rebuilds Spring message:
  headers.id = UUID-B
  businessOperationId = SUBMIT-901
~~~

An Idempotent Receiver relies on `operationId`, not `headers.id`. If correlation or `operationId` is stripped by a Transformer, adapter header mapper, or reserialization, retries can cause double effects. Have **adapter round-trip tests** to catch dropped metadata.

### 15.4. Never Send Internal Reply Channels Over the Wire

`replyChannel` and `errorChannel` in a Spring Message can be JVM channel objects. Over a broker or HTTP, use **transport-specific reply destinations / error routing** when needed; never serialize or trust arbitrary header classes/objects from external sources.

### 15.5. Correlation Does Not Turn One-Way into Request–Reply

Having a `correlationId` in a message **does not** make the Gateway wait for a reply. A later completion event can use correlation alongside operation status; it remains a separate message exchange, not the Java return value of `void submit(...)`.

## 16. Comparing Related EIPs

### 16.1. Messaging Gateway vs. Outbound Channel Adapter

| Component | Boundary | Example |
|---|---|---|
| **Messaging Gateway** | Java application interface → messaging system. | `gateway.submit(command)`. |
| **Outbound Channel Adapter** | Spring Integration flow → external system, per adapter semantics. | Send to Kafka/JMS/HTTP/file. |
| **Inbound Channel Adapter** | External system → Spring message flow. | Receive broker record, poll file. |
| **Service Activator** | Channel message → business/service method. | `handle(OrderSubmission)`. |
| **Router** | Selects channel by condition. | By command type, region. |
| **Transformer** | Transforms payload/metadata. | Domain DTO → wire command schema. |

An architecture often includes **both a gateway and an outbound adapter**, rather than choosing one over the other:

~~~text
Java service
   -> Messaging Gateway
   -> Internal Channel
   -> Transformer / Filter
   -> Outbound Channel Adapter
   -> External Broker
~~~

### 16.2. Gateway and Publish–Subscribe

A `void` Gateway can send an **event** to a `PublishSubscribeChannel`, though semantics change with subscribers:

~~~mermaid
flowchart TD
    G["Void Gateway publishes OrderPlaced"] --> PUB["PublishSubscribeChannel"]
    PUB --> AUDIT["Audit"]
    PUB --> NOTICE["Notification"]
    PUB --> ANALYTICS["Analytics"]
~~~

Not all subscribers have the same criticality. If a one-way event must reach three independent consumers, consider isolation, error propagation, retry, and durable pub/sub. A throwing subscriber on a synchronous channel can affect dispatch to other subscribers depending on configuration; **do not assume one failing branch never affects another**.

Each consumer needs **its own idempotency scope** when the same event is redelivered. A single global dedupe marker shared between Audit and Notification could wrongly drop the second subscriber.

### 16.3. Gateway and Recipient List

If a command must go to conditionally selected recipients, a Recipient List can fan out. The Gateway returning `void` does not mean we know **all recipients succeeded**. Per-recipient state, retry/idempotency, and a completion policy are needed if business requires every branch.

~~~text
order command
  -> Gateway
  -> Recipient List:
      Billing
      Inventory
      Notification

Gateway returns != all recipients committed
~~~

### 16.4. Gateway and Splitter

A batch command can be split by a Splitter into items:

~~~text
BatchCommand(batchId=B-1)
   -> Gateway (void)
   -> Splitter:
       Item I-1
       Item I-2
       Item I-3
~~~

If the caller does not wait for a reply, another mechanism is needed to know each item's outcome:

- Store batch status and per-item outcomes.
- Emit completion/failure events per child.
- Aggregate status once all children finish per contract.
- Set a timeout if an item is invalid or lost.
- Keep `batchId + itemId` as the operation identity for each side effect.

Never use the same `batchId` as the idempotency key for every item, or the second and third items may be treated as duplicates of the first.

### 16.5. Gateway and Aggregator

An Aggregator typically builds a result from multiple messages. If the Gateway caller uses `void`, **there is no place to return the aggregated result via the original invocation's return value**. Options include:

~~~text
Gateway submitBatch(B-1)
  -> async processing
  -> Aggregator creates BatchCompleted(B-1)
  -> status store / event notification
~~~

If the caller needs the batch result immediately, choose a **request–reply Gateway** with an appropriate deadline and resource budget. Never silently bury an Aggregator under a `void` Gateway and claim the application received the result just because it sent the command.

### 16.6. Gateway and Scatter–Gather

Scatter–Gather collects replies from multiple recipients, usually requiring correlation, timeouts, and a release strategy. A one-way Gateway can **initiate** a scatter–gather workflow without waiting for the final aggregate; the result is emitted on another event/status flow.

If the workflow requires Fraud + Inventory + Pricing all to succeed, never report `APPROVED` just because the `void` Gateway returned or one of the three branches confirmed.

### 16.7. Gateway and Resequencer

A Gateway may send events with `businessSequence` 1, 2, 3. With concurrent executors or broker partitions, arrival/processing order can differ. A Resequencer and correlation metadata can help restore release order, yet:

- A message dropped by a Filter can create a **sequence gap**.
- Duplicate deliveries must not be counted as missing items.
- Correct release order does not guarantee DB commit order if downstream runs in parallel afterward.
- Partitioning or version guards are needed if business requires strict write ordering.

### 16.8. Gateway and Claim Check

For large command payloads:

~~~text
Large command
   -> protected store (Claim Check)
   -> Gateway sends reference
   -> Consumer restores payload
~~~

A `void` Gateway return only says the **reference** was sent per channel contract, not that the consumer could read the original payload. If the Claim Check store expires before processing, the command may be unrecoverable. Nor does a Claim ID automatically replace a **business operation ID**.

### 16.9. Gateway and Message Translator / Envelope Wrapper

A Gateway can accept a domain command and let a Translator convert it into a partner schema:

~~~text
OrderSubmission
   -> Void Gateway
   -> Message Translator
   -> Envelope Wrapper
   -> Broker adapter
~~~

The Translator may reject unmappable fields; the Envelope Wrapper holds source/type/version/correlation; the broker adapter maps wire headers. Never let the Translator generate a new `operationId` on every retry or take `tenantId` from an untrusted header and treat it as trusted.

### 16.10. Gateway and Idempotent Receiver

An Idempotent Receiver typically sits at the **side-effect consumer** to deduplicate redeliveries. It can use `ConcurrentMetadataStore`/`IdempotentReceiverInterceptor` at the Spring Integration level, yet **a `SEEN` marker is not `COMPLETED`**. For payments or orders, you need durable operation state/receipts and reconciliation, not just an in-memory selector.

## 17. Timeouts, Transactions, and Backpressure

### 17.1. Request Timeout Is Not End-to-End Flow Execution Timeout

A Gateway/Channel can configure timeouts around **send/handoff**. With a synchronous downstream handler calling an external API for 30 seconds, a `QueueChannel` send timeout does not cancel that external request after 30 seconds. Distinguish:

| Timeout | Interval Measured | Handling Needed |
|---|---|---|
| Gateway/channel send timeout | Time waiting to send / be accepted by channel, per implementation. | Manage overload/backpressure. |
| Executor queue deadline | Time waiting for task scheduling/execution. | Queue saturation and stale requests. |
| Broker publish timeout | Waiting for producer send/ack per adapter. | Publish outcome may be `UNKNOWN`. |
| Consumer processing deadline | Limit on business operation. | Idempotent retry/reconcile if timeout occurs after side effect. |
| Operation SLA | From accepted to authoritative completion. | Status store, alerts, and compensation. |

Do not describe every timeout as a "Gateway timeout." Each has **different start/end boundaries and recovery steps**.

### 17.2. Calling a One-Way Gateway Inside a DB Transaction

Example:

~~~java
// Pseudocode, not a system-wide guaranteed transaction.
@Transactional
void placeOrder(...) {
    orderRepository.save(order);
    gateway.submit(new OrderSubmission(...));
}
~~~

If the Gateway leads to a broker publish that does not participate in the same DB transaction, an error after publishing can roll back the DB while the record remains published, or the DB commits while publishing fails. When atomic intent is required, use **outbox/CDC/transactional architecture** with commit proof.

### 17.3. Async Boundaries Usually Break Transaction Context

With `ExecutorChannel`, the handler runs on a different thread; the caller's **`ThreadLocal` transaction/security context** is not automatically preserved intact. Do not rely on a caller-opened transaction to span an async consumer. Pass permitted metadata and open transactions/authorization contexts inside the handler per architecture.

In particular, never pass raw database sessions, principal objects, or transaction managers in message payloads as a way to "preserve the transaction"; that crosses execution and security boundaries.

### 17.4. Do Not Equate Transaction Commit with Broker Ack

~~~text
Transaction DB commit OK
Broker consumer ack lost
  -> message may redeliver
  -> idempotency ledger recognizes operation COMPLETED
~~~

A transaction on one resource manager does not automatically extend to an HTTP payment API or across all brokers/databases. State the **scope of atomicity**, and do not label an entire workflow "exactly once" without proving it.

### 17.5. Backpressure for One-Way Senders

A caller that does not wait for a business reply can send faster than downstream can process. Limits are required:

~~~text
Input rate        = 10,000 commands/s
Consumer capacity =  1,000 commands/s
Backlog growth    =  9,000 commands/s
~~~

With an unbounded queue, you risk OOM or disk exhaustion. With a bounded queue, senders may block or reject. Options include:

- Bounded executor/queue and overload status.
- Ingress rate limiting by tenant/priority.
- Durable buffer with retention, capacity alerts, and proper partitioning.
- Consumer autoscaling when side effects and idempotency permit.
- Deadlines: should an expired command still run after waiting too long in the queue?
- Circuit breakers when downstream is unavailable.
- Returning backpressure/retry-after at synchronous API boundaries instead of silently dropping.

**One-way does not mean the caller can send unboundedly without load responsibility.**

### 17.6. Do Not Forget Shutdown Semantics

Shutting down a JVM while `ExecutorChannel` still holds pending tasks can lose unpersisted work. Graceful shutdown can wait for tasks up to a point, yet **it does not replace a persistent queue** during crashes, `SIGKILL`, node loss, or shutdown timeouts.

At the broker layer, plan intake pause, backlog drain, redelivery, and resume. A "successful" deployment does not by itself prove zero messages were lost during rollout.

## 18. Security When Sending One-Way Messages

### 18.1. Do Not Trust Calls Just Because They Return No Reply

An attacker can abuse a fire-and-forget endpoint to flood commands, build backlogs, or trigger background side effects. Enforce:

- Authentication and authorization per tenant/operation.
- Input schema validation, payload size limits, and rate limiting.
- Quotas per principal/tenant.
- Properly scoped business idempotency keys.
- Auditing of accepted/rejected operations.
- Never returning fake success when the system cannot hand off the work.

### 18.2. Header Routing Is Not an Authorization Mechanism

An inbound caller-supplied header `targetChannel=paymentProcessor` **must never be used directly** to select any Spring channel or bean. If using a Dynamic Router or Header-Based Router, enforce an allowlist and a trusted source/policy.

### 18.3. Do Not Put Secrets into Message Logs

One-way commands can contain addresses, tokens, emails, or payment details. Logging should focus on:

~~~text
operationRef = opaque/stable ID
commandType  = SUBMIT_ORDER
tenantScope  = trusted, access controlled
route        = orders.submit.input
outcome      = DISPATCH_ACCEPTED
~~~

Never print raw payloads or system credentials in `toString()`, stack traces, error-channel messages, or dead-letter headers. For data needed during investigation, use protected storage/references with retention and read access controls.

### 18.4. Replay Must Be Re-Authorized

A three-day-old command in a DLQ is not automatically authorized for replay today. User permissions may have been revoked, tenant policies changed, or prices invalidated. Replay must re-check security/business rules, status/receipt, and operation identity before triggering side effects.

### 18.5. Client-Generated Operation IDs Are Not Proof of Permission

A predictable `operationId` like `SUBMIT-901` is just an identifier. Never return a business receipt solely to someone who knows the ID without verifying permission on the order/tenant. When deduplicating on the same key, also verify fingerprint and authorization to prevent a user from probing or blocking another user's operation.

## 19. Observability and Diagnostics for One-Way Flows

### 19.1. Log by Milestone, Not One Generic "DONE" Event

~~~text
event=GATEWAY_INVOKED
  operationRef=SUBMIT-901
  commandType=SUBMIT_ORDER

event=CHANNEL_HANDOFF_ACCEPTED
  operationRef=SUBMIT-901
  channel=orders.submit.input

event=OUTBOX_PERSISTED
  operationRef=SUBMIT-901
  outboxRef=OUT-901

event=BROKER_PUBLISHED
  operationRef=SUBMIT-901
  brokerRef=...

event=CONSUMER_RECEIVED
  operationRef=SUBMIT-901
  deliveryAttempt=2

event=BUSINESS_OPERATION_COMPLETED
  operationRef=SUBMIT-901
  receiptRef=ORD-901

event=CONSUMER_ACKNOWLEDGED
  operationRef=SUBMIT-901
~~~

This is a **recommended structured logging schema**, not default Spring Integration events. Each log should only be emitted at an **evidenced milestone**. For example, `OUTBOX_PERSISTED` must rest on a database commit contract; `BUSINESS_OPERATION_COMPLETED` must rest on an authoritative result, not merely method return.

### 19.2. Recommended Metrics

| Metric | Meaning |
|---|---|
| `gateway_invocations_total{method}` | Number of times callers invoked the Gateway. |
| `gateway_dispatch_accepted_total{channel}` | Handoffs accepted by the channel. |
| `gateway_dispatch_failed_total{reason}` | Send/rejection/timeout failures. |
| `gateway_dispatch_latency_seconds` | Latency from invocation to handoff milestone. |
| `oneway_executor_queue_depth` | Task backlog in the executor. |
| `oneway_executor_rejected_total` | Tasks rejected under overload. |
| `oneway_consumer_received_total` | Deliveries received by the consumer. |
| `oneway_business_completed_total{outcome}` | Operations reaching a final outcome. |
| `oneway_duplicate_delivery_total` | Deliveries for an existing operation. |
| `oneway_business_outcome_unknown_total` | Operations needing reconciliation. |
| `oneway_error_channel_messages_total{class}` | Errors handled by the error flow. |
| `oneway_dlq_messages_total{reason}` | Records routed to DLQ. |
| `oneway_operation_age_seconds` | Latency from accepted to final status. |
| `oneway_outbox_pending_total` | Outbox rows not yet published/confirmed. |

These names are suggestions only. Spring Integration or Micrometer may expose different metrics depending on version/configuration; do not assume the framework creates all of them automatically. **Never attach `operationId`/`orderId`/customer ID/email/`traceId` as metric labels**: cardinality explodes and PII can leak.

### 19.3. A Dashboard Example Easily Misread

~~~text
Gateway invocations:        10,000
Channel handoff accepted:    9,998
Broker published:           9,990
Consumer received:         10,120  (redeliveries)
Business operations done:    9,875
Pending/unknown operations:    123
~~~

These are illustrative numbers. `Consumer received` can exceed `Gateway invocations` due to retries/redeliveries. You cannot treat total deliveries as total unique operations. Differences across handoff/publish/completed also include **in-flight, lag, and time-window effects**; join by operation identity and time window before concluding messages were lost.

### 19.4. Message History Is Useful, Not a Receipt

Spring Integration Message History, when enabled, shows which Gateway, Transformer, Router, and handlers a message passed through. Yet by itself it does not prove:

- The outbox committed.
- The broker acked.
- An external payment completed.
- A DLQ record still exists past retention.
- Retries used a stable `operationId`.
- The caller was authorized for the tenant.

To investigate an operation, combine **trusted operation IDs, structured logs, message history, broker coordinates, durable inbox/outbox state, and business receipts**.

### 19.5. When the Gateway Returns, Yet No Message Reaches the Consumer

Check in order:

1. **Caller:** was `submit(...)` actually called, or was an exception caught and ignored?
2. **Gateway proxy:** was the interface properly scanned/registered by Spring?
3. **Request channel:** does the channel name match `@Gateway(requestChannel=...)`?
4. **Channel type:** Direct/Executor/Queue or adapter; at what milestone does each return?
5. **Subscription:** is a handler/subscriber active? Is the consumer stopped/disabled?
6. **Overload:** did the executor reject, queue fill up, or poller stall?
7. **Transform/Filter:** was the message validation-rejected or discarded without a quarantine handler?
8. **Outbound adapter:** serialization error, header mapper, publish timeout?
9. **Broker:** topic/queue, partition/key, auth, retention, and producer confirms?
10. **Inbound consumer:** adapter subscription, consumer group, offset, deserialization error/DLQ?
11. **Idempotency:** did the consumer already see the same operation and legitimately skip the duplicate?
12. **Business handler:** DB/API error, was ledger/receipt written?
13. **Tracing:** did correlation/`operationId` survive every hop?
14. **Recovery:** is the record pending, retrying, or expired?

Never start by raising Gateway timeouts or adding infinite retries. Find the **first boundary where the message or proof of processing disappears**, then fix it at that exact boundary.

### 19.6. Runbook When Executor/Queue Overloads

~~~text
Detect:
  queue_depth rises
  executor_rejected_total rises
  consumer_latency grows

Protect:
  enforce rate limit and bounded queue
  reject or backpressure new intake by contract

Recover:
  inspect downstream bottleneck
  scale consumer only if side effect supports concurrency
  drain durable pending messages

Validate:
  no silent loss
  no duplicate business effects
  operation age and error counts return to expected level
~~~

Never increase thread counts without bound if the bottleneck is a database, a rate-limited API, or an ordering constraint; that can make the system even more unstable.

## 20. Failure Tests Worth Prioritizing

### 20.1. Synchronous: Handler Exceptions Must Surface

A test can define a dedicated throwing handler:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.integration.channel.DirectChannel;

@Configuration
class OneWayFailingHandlerConfiguration {
    @Bean(name = "orders.failing.input")
    MessageChannel failingInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow failingFlow() {
        return IntegrationFlow.from("orders.failing.input")
                .handle(OrderSubmission.class,
                        (command, headers) -> {
                            throw new IllegalStateException(
                                    "DOWNSTREAM_UNAVAILABLE");
                        })
                .get();
    }
}
~~~

To run through a Gateway, define another `@MessagingGateway` pointing to `orders.failing.input` in the test context; assert the invocation throws a runtime/messaging exception, and inspect the cause chain per framework version.

**Do not conclude with certainty that side effects did not occur** if the error was thrown after an external commit. Dedicated crash-window tests require an authoritative business ledger or a remote idempotency mock.

### 20.2. Async: Verify Worker Execution Instead of Asserting Immediately

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertTrue;

class AsyncGatewayObservationPatternTest {
    @Test
    void awaitAnExplicitCompletionSignal() throws Exception {
        CountDownLatch completion = new CountDownLatch(1);
        // In a real integration test, inject completion into the handler,
        // handler.countDown() after the milestone to observe.
        Runnable fakeWorker = completion::countDown;
        Thread worker = new Thread(fakeWorker);
        try {
            worker.start();
            assertTrue(completion.await(2, TimeUnit.SECONDS));
        } finally {
            worker.join(2000);
        }
    }
}
~~~

This test illustrates the **signal-waiting technique**, not a Spring Integration test. In a full integration test, replace `fakeWorker` with a handler triggered via `AsyncOrderSubmissionGateway`/`ExecutorChannel`. Use deadline-bounded shared latch/queue assertions, clean up the executor, and also test submission rejections.

### 20.3. No Subscriber

A `DirectChannel` with no handler generally cannot dispatch successfully. Tests should verify the **error/false handling** matching the channel/gateway setup rather than treating `void` as proof every message had a handler.

### 20.4. Queue Full

With a capacity-1 `QueueChannel`, no poller, or a paused consumer:

~~~text
send command A -> queue has 1 message
send command B -> may block/timeout/fail by send policy
~~~

Verify the deadline, latency, and remaining message count. Never write a test that hangs indefinitely simply because send lacks an appropriate timeout.

### 20.5. Crash After Enqueue

A system/chaos test:

~~~text
1. Gateway returns after in-memory enqueue.
2. Kill process before consumer polls.
3. Restart process.
4. Check whether command remains.
~~~

With an in-memory `QueueChannel`, **do not expect durability**. Repeat the test with a persistent queue/broker to measure **durability per contract**, and never apply the same conclusion across every channel type.

### 20.6. Broker Publish Succeeds, Ack Lost

~~~text
1. Publisher sends SUBMIT-901.
2. Broker persists, response lost.
3. Publisher retries same event.
4. Consumer sees duplicate SUBMIT-901.
5. Ledger prevents repeated business effect.
~~~

Do not just assert "the broker has two records"; assert **only one business effect occurred** and the outcome/receipt survives restarts.

### 20.7. Business Commit Succeeds, Consumer Ack Lost

~~~text
1. Consumer commits order operation.
2. Process dies before broker ack.
3. Record redelivered.
4. Consumer queries ledger and returns completed result.
5. No second order/charge created.
~~~

This is a critical scenario that a unit test using only `ConcurrentHashMap` cannot prove.

### 20.8. Error Channel Receive and Recovery

With an async endpoint, inject an exception after dispatch and verify:

- An error event exists with the right exception class/reason.
- The error flow does not expose raw PII.
- Retries are bounded and route to dead-letter/fallback when exhausted.
- The operation transitions to `FAILED_RETRYABLE` or `OUTCOME_UNKNOWN` based on evidence.
- Business effects do not re-execute if a prior attempt already committed.

Test against the **real execution model**: error behavior differs among `DirectChannel`, `ExecutorChannel`, and transport adapters.

### 20.9. Gateway Returned, Filter Dropped

Inject an **already decoded** invalid command into a Filter configured with a discard channel; assert:

- The business handler **did not** run.
- The quarantine handler received the issue/reason.
- Durable handoff is verified if required in production.
- If the caller needs a rejection response, do not use a `void` one-way contract as if it could return a rejection object.

## 21. One-Way Messaging Gateway Test Matrix

| ID | Scenario | Must Verify | Must Not Happen |
|---|---|---|---|
| GW-01 | Call `void gateway.submit(command)` via DirectChannel | Handler receives one command with exact payload. | Assuming a reply object must exist. |
| GW-02 | Synchronous handler takes long | Caller waits per synchronous dispatch semantics. | Claiming `void` is always async. |
| GW-03 | DirectChannel handler throws | Error propagates/wraps per contract. | Swallowing errors due to `void` return type. |
| GW-04 | DirectChannel has no subscriber | Dispatch failure is detected. | Reporting successful processing. |
| GW-05 | Wrong Gateway request channel name | Wiring failure / clear test failure. | Silent drop. |
| GW-06 | Interface not scanned/registered | Spring context lacks gateway bean. | Calling a bean assumed to exist. |
| GW-07 | Command has stable `operationId` | Payload preserves identity. | Generating a new ID per attempt. |
| GW-08 | Invalid command amount | Rejection/validation error or quarantine per contract. | Invoking business payment. |
| GW-09 | Filter discards invalid | Quarantine receives reason and business does not run. | Caller interpreting `void` return as business accepted. |
| GW-10 | One-way Gateway with ExecutorChannel | True asynchronous dispatch occurs. | Asserting handler finished right after return. |
| GW-11 | Executor queue accepted, worker not yet run | Pending state is observable. | Marking `COMPLETED` prematurely. |
| GW-12 | Executor queue full | Bounded rejection/backpressure. | Silent task loss. |
| GW-13 | Worker throws after caller returns | Error flow/alert/recovery receives error. | Expecting caller to catch synchronously. |
| GW-14 | Async worker fails before side effect | Valid retry per policy. | Operation abandoned with no audit. |
| GW-15 | Async worker fails after side effect | Idempotency/reconciliation. | Double charge. |
| GW-16 | Capacity-1 QueueChannel is full | Send timeout/behavior matches config. | Uncontrolled infinite blocking. |
| GW-17 | QueueChannel has no poller yet | Queue depth grows, not reported done. | Treating enqueue as business completion. |
| GW-18 | In-memory QueueChannel then process crash | Data loss acknowledged per contract. | Claiming durability. |
| GW-19 | Durable queue then process restart | Recovery/redelivery per store semantics. | Losing commands on restart. |
| GW-20 | Outbound adapter serialization throws | Publish error route is handled. | Treating gateway return as broker commit. |
| GW-21 | Kafka/RabbitMQ/JMS broker publish timeout | Publish outcome `UNKNOWN`, retry/dedupe. | Generating a new command ID. |
| GW-22 | Broker confirms receipt | Confirms broker handoff milestone. | Marking business `COMPLETED` immediately. |
| GW-23 | Broker record gets new offset on republish | Stable business operation key. | Deduplicating by offset. |
| GW-24 | Consumer commits then ack lost | Redelivery returns previous receipt. | Executing side effect a second time. |
| GW-25 | Producer DB commits before publish completes | Outbox/reconciliation protects intent. | Event lost permanently. |
| GW-26 | Outbox relay publishes twice | Consumer-side idempotency. | Double business effect. |
| GW-27 | Same `operationId`, different amount | Payload fingerprint conflict. | Returning old success without checking. |
| GW-28 | Same `orderId` has CREATE and CANCEL | Two operation scopes. | Blocking CANCEL because CREATE ran. |
| GW-29 | Same event fans out to Audit and Notification | Each consumer processes once. | Global dedupe blocking the second branch. |
| GW-30 | Splitter creates three child commands | Per-child keys and correlation. | Blocking two children due to shared `batchId`. |
| GW-31 | Aggregator missing one child | Timeout/failure outcome. | Returning a fake completed aggregate. |
| GW-32 | Scatter–Gather Fraud branch fails | Overall result not `APPROVED` early. | Relying only on `void` Gateway return. |
| GW-33 | Resequencer encounters gap | Monitored gap/release policy. | Emitting messages out of order. |
| GW-34 | Gateway sends Claim Check token | Consumer restores with auth/TTL. | Treating token as original payload. |
| GW-35 | Unsupported outbound schema | Error/quarantine before broker publish. | Serializing malformed data. |
| GW-36 | Transport adapter drops custom operation header | Round-trip test detects it. | Deduplicating by runtime `MessageHeaders.ID`. |
| GW-37 | Caller sends fake tenant header | AuthN/AuthZ from trusted principal. | Tenant impersonation. |
| GW-38 | Caller sends arbitrary channel selector | Route allowlist/policy. | Unauthorized routing to privileged handler. |
| GW-39 | Client flooding one-way endpoint | Quota/rate limit/backpressure. | Unbounded queue growth. |
| GW-40 | Worker needs DB transaction | Transaction opens at worker boundary. | Using caller's async `ThreadLocal` transaction. |
| GW-41 | Gateway inside DB tx separate from broker | Detect dual-write / outbox strategy. | Assuming 2 resources are automatically atomic. |
| GW-42 | Gateway returns HTTP response immediately | Response reflects true accepted milestone. | Returning fake `"ORDER_COMPLETED"`. |
| GW-43 | Caller wants receipt immediately | Choose request–reply or status contract. | Using `void` and fabricating an implicit reply. |
| GW-44 | Caller wants result via later event | Proper correlation/causation. | Using `traceId` as sole identity. |
| GW-45 | Redelivery creates new Spring Message ID | Dedupe still uses stable `operationId`. | Duplicate effect. |
| GW-46 | `ErrorChannel` receives async exception | Recovery/bounded retry/alert. | Assuming caller receives error automatically. |
| GW-47 | Invalid message enters quarantine | Durable record and reason codes. | Silent discard. |
| GW-48 | Quarantine DB unavailable | Retry/backpressure/no false ack. | Sending invalid data to business flow. |
| GW-49 | DLQ replay of already completed operation | Receipt reconciliation. | Creating a new order. |
| GW-50 | Payload contains PII/secret | Redacted logs, protected store. | Raw data in metrics/logs. |
| GW-51 | Guessable caller-supplied operation ID | Principal/resource authorization. | Exposing someone else's receipt. |
| GW-52 | Executor shutdown with remaining tasks | Drain/recovery per durability contract. | Assuming RAM tasks are durable. |
| GW-53 | Consumer 10x slower than ingress | Queue monitoring, rate limits, capacity policy. | Unwarned OOM. |
| GW-54 | Gateway returned, no consumer record | Trace every handoff/ack/consumer milestone. | Concluding message loss without evidence. |
| GW-55 | Tracking enabled | Message History aids bounded tracing. | Treating Message History as a durable receipt. |
| GW-56 | Source event schema version upgraded | Typed translator/adapter compatibility. | Downgrading to V1 and dropping critical fields. |
| GW-57 | Command expired while in queue | Clear deadline/expiry policy. | Executing an expired transaction anyway. |
| GW-58 | Same command resent with conflicting payload | Conflict/review workflow. | Overwriting a completed receipt. |
| GW-59 | Gateway request timeout while handler committed | `UNKNOWN` outcome + reconciliation. | Blind retry. |
| GW-60 | Meter shows received higher than completed | Separate delivery count from unique operation count. | Equating business operations with deliveries. |

### 21.1. What Does Each Test Level Prove?

| Test Level | Verifies Best | Cannot Prove |
|---|---|---|
| **Application service unit** | Caller invokes gateway interface with right command/ID. | Spring gateway proxy and channel wiring. |
| **Spring Integration sync test** | Proxy → DirectChannel → handler, error propagation. | Durable broker/async semantics. |
| **Spring Integration async test** | ExecutorChannel dispatch, latch, rejection/error flow. | Persistence across process crash. |
| **Queue/adapter integration test** | Queue capacity, poller, outbound serialization/header mapping. | External business side effects when mocked. |
| **Broker integration test** | Producer confirm, consumer ack/redelivery/DLQ. | DB + HTTP atomicity outside broker. |
| **Database test** | Outbox/inbox transactions, unique keys, concurrent consumers. | Remote payment processed exactly-once. |
| **System/chaos test** | Restarts, lost publish/ack, multi-node recovery. | Real-world failures outside simulation. |
| **Security test** | Tenant auth, header spoofing, replay rights, PII. | Unaudited trust boundaries. |

A passing unit test for `CheckoutApplicationService` cannot guarantee a Kafka record was durably persisted by the broker. Test at the **exact infrastructure boundary on which the guarantee depends**.

### 21.2. Golden Contract for a One-Way Gateway

~~~text
Command:
  operationId = SUBMIT-901
  orderId = ORD-901
  amountVnd = 850000

Ingress:
  verified tenant = TENANT-A

Gateway:
  method = void submit(OrderSubmission)
  requestChannel = orders.submit.input

Transport:
  durable handoff defined separately

Consumer:
  dedupe key = (TENANT-A, CREATE_ORDER, SUBMIT-901)
  idempotency fingerprint = canonical command fields
  state = NEW -> IN_PROGRESS -> COMPLETED
  receipt = ORD-901

Failure:
  no subscriber -> dispatch error
  invalid -> rejection/quarantine
  timeout after commit -> reconciliation
~~~

The golden fixture should be tested across multiple layers: Gateway proxy, channel, adapter, consumer, and ledger. When a version, schema, or routing rule changes, the test ensures one-way semantics do not silently degrade into "accepted with nobody receiving" or "duplicate orders."

## 22. Common Design Mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| "`void` method means async execution." | Caller still blocks on `DirectChannel`. | Understand channel boundaries. |
| "One-way means it cannot throw." | Synchronous dispatch exceptions go unhandled. | Test error propagation. |
| "Gateway returning means consumer finished." | False success reporting. | Separate handoff from receipt. |
| "`QueueChannel` is durable by default." | Messages lost on restart. | Persistent queue/broker/outbox. |
| "`ExecutorChannel` means messages won't be lost." | Pending tasks in RAM lost on crash. | Durable handoff if required. |
| "Broker ack is business ack." | Unknown whether consumer committed. | Track operation receipt separately. |
| "Wrapping `void` Gateway in a retry is enough." | Double effects or lost messages. | Idempotency, state, reconciliation. |
| "Synchronous timeout means side effect didn't happen." | Retrying after an external commit. | `UNKNOWN` outcome + status query. |
| "Return HTTP 200 Completed when gateway returns." | Client misinterprets state. | Accepted/status contract. |
| "Global `errorChannel` catches every error." | Adapter/deserializer errors slip past. | Adapter-specific error tests. |
| "No reply means no correlation needed." | Cannot trace completion events. | Stable IDs/correlation/causation. |
| "Use `MessageHeaders.ID` for deduplication." | Redelivery rebuilds a different ID. | Business operation ID. |
| "Dedupe by `orderId` across all operations." | Blocks valid `CANCEL`/`REFUND`. | Operation-scoped key. |
| "Dedupe `SEEN` equals `COMPLETED`." | Crash before commit drops work. | Durable state/receipt/recovery. |
| "Put retry count in payload to track it." | Alters business fingerprint across attempts. | Delivery metadata/logs. |
| "All subscribers share one global dedupe state." | Downstream fan-out branches get blocked. | Consumer-specific keys. |
| "One-way needs no backpressure." | Queue/threads/storage explode. | Bounded channels and rate limits. |
| "No logs hides errors; log whole payload." | PII leaks. | Structured redacted logs. |
| "Caller self-declares `trustedTenant`." | Cross-tenant routing/security flaw. | Trusted auth context. |
| "Gateway inside `@Transactional` spans broker." | Dual-write inconsistency. | Outbox/transaction architecture. |
| "No consumer log = message definitely lost." | May still be in queue/DLQ/pending/replay. | Trace milestones by identity. |
| "DLQ replay creates a new operation." | Side effects double. | Replay original operation ID, check ledger. |
| "`DirectChannel` is always bad design." | Unnecessary async complexity. | Choose by latency/reliability contract. |
| "Publish–Subscribe is a single consumer." | Misunderstood fault isolation/fan-out. | Per-recipient state/metrics. |
| "Graceful shutdown replaces persistence." | Node crash still loses pending tasks. | Durable store when loss is unacceptable. |

## 23. Hands-On Exercises

1. **Basic `void` Gateway:** create `OrderSubmissionGateway` with `@MessagingGateway` and `@Gateway(requestChannel=...)`, and call it from an application service without importing Spring `Message`.
2. **DirectChannel:** configure `OneWayGatewayConfiguration`, assert one call invokes the handler and returns no business reply.
3. **Fake gateway:** unit test `CheckoutApplicationService` using a method reference/lambda, verifying `operationId` is preserved.
4. **Synchronous error:** make the handler throw, observe the exception through `DirectChannel`, and explain why returning `void` does not suppress exceptions.
5. **No subscriber:** remove the terminal handler from `DirectChannel`; assert the gateway invocation cannot be interpreted as successful processing.
6. **Async executor:** switch `requestChannel` to `ExecutorChannel` with a bounded pool and verify the caller can return before the handler finishes.
7. **Async latch:** use `CountDownLatch` to verify the handler executed; do not assert immediately after invocation.
8. **Executor rejection:** block the worker, fill the bounded queue, submit another command, and verify configured rejection/backpressure.
9. **Async error:** make the worker throw after gateway return; configure an error handler and confirm structured failure events/alerts.
10. **QueueChannel:** create a capacity-2 queue with a poller, send three commands, and verify queue-full/send-timeout semantics.
11. **Queue restart:** send a command into an in-memory `QueueChannel`, restart the context, and prove it is not a durable queue.
12. **Durable handoff:** replace the in-memory queue with a broker/persistent store and test restart recovery at the infrastructure layer.
13. **Latency contract:** measure Gateway return, broker confirm, and consumer completion separately; do not collapse them into one metric.
14. **Business status:** design `OperationStatus(SUBMIT-901)` with `NEW`/`IN_PROGRESS`/`COMPLETED`/`UNKNOWN`; do not mark completed at the gateway.
15. **HTTP response:** return HTTP `202 Accepted` + operation reference once durable acceptance is achieved; verify the status endpoint afterward.
16. **Outbox:** write the order row and outbox event in the same DB transaction; relay-publish with a stable event ID.
17. **Producer ack lost:** simulate a successful publish where the publisher misses the ack, retry with the same event ID, and verify the consumer does not double-process.
18. **Consumer ack lost:** commit business state then kill the consumer before ack; verify redelivery returns the previous receipt.
19. **Same operation, two Spring messages:** rebuild the message with a new runtime ID and assert consumer dedupe still relies on `operationId`.
20. **Fingerprint conflict:** send the same `operationId` with a different amount; must produce a conflict rather than creating a second order.
21. **Filter:** add a validation Filter before the handler, routing invalid commands to quarantine with reason codes instead of silent drop.
22. **Gateway response contract:** compare needing an immediate `OrderReceipt` vs. only sending a command; justify request–reply vs. one-way.
23. **Router:** route `SubmitOrder` and `CancelOrder` to two handlers; never use a client-supplied arbitrary channel name.
24. **Publish–Subscribe:** send one event to Audit, Notification, and Analytics; give each consumer its own idempotency key.
25. **Splitter:** split a batch into child commands with stable child IDs and test that duplicating one child does not substitute for a missing child.
26. **Aggregator:** make one child invalid; design the batch's failure outcome/timeout and completion event.
27. **Scatter–Gather:** Inventory passes while Fraud times out; do not emit final approval for the whole order.
28. **Resequencer:** send events 1 and 3 before 2; verify ordering/gap policy and accurate business version writes.
29. **Claim Check:** store a large payload in protected storage and send a reference through the Gateway; test claim expiry, retention, and restore authorization.
30. **Header mapping:** pass `businessEventId`/`correlationId` across outbound/inbound adapters while ensuring Spring Message IDs may differ.
31. **Tenant security:** send a self-declared `trustedTenant=TENANT-A` header under a tenant B principal; deny before routing.
32. **Rate limit:** emit commands faster than the consumer can handle; design queue capacity and overload behavior.
33. **Transaction:** demonstrate that a DB transaction does not span broker publishing; propose an outbox/recovery plan.
34. **DLQ replay:** replay an already completed command; verify the idempotency ledger does not re-run side effects.
35. **Metric audit:** build a dashboard separating gateway invocations, channel handoffs, published, received, and unique business completed.
36. **Production runbook:** document the full diagnostic path for "gateway returned, no business result seen" across boundaries.

### 23.1. Acceptance Criteria

A one-way Gateway implementation meets the lesson's requirements when:

- Application callers invoke a clear Java interface without knowing `MessageChannel` unnecessarily.
- Request channels and subscribers/adapters are properly configured and integration tested.
- It is understood that `void` is **not async**, not durable, and not a no-throw guarantee.
- Direct/Executor/Queue/broker is chosen based on latency, workload, and durability needs.
- Reporting accepted/published/completed rests on contract-level evidence.
- Error paths handle both synchronous and asynchronous failures.
- Retries follow bounded policies without repeating remote business effects.
- Stable operation identity and durable state/receipts prevent duplicates across redeliveries/crashes.
- Security, rate limits, tenant isolation, metadata preservation, and redacted logs are in place.
- Tests cover the exact adapter, broker, database, and recovery boundaries relied upon.

## 24. Self-Check Questions

**Question 1: What is a One-Way Messaging Gateway?**

It is a gateway interface that sends a message from a Java application into a Spring Integration flow where the invocation requires no business reply payload from the receiver, such as `void submit(OrderSubmission)`.

**Question 2: Does `void` automatically make message processing asynchronous?**

No. `DirectChannel` can dispatch synchronously on the caller thread. Asynchrony comes from `ExecutorChannel`, `QueueChannel`/poller, a broker, or another async boundary.

**Question 3: Why can `void submit(...)` still throw an exception?**

Because message dispatch or a synchronous downstream handler can fail before the method returns. `void` only states that the Java method returns no business value.

**Question 4: When using `DirectChannel`, up to what milestone does the caller usually wait?**

The caller runs along synchronous dispatch until the channel/handler returns (or throws). That does not necessarily prove an external business side effect was durably committed if the handler lacks corresponding evidence.

**Question 5: Does `ExecutorChannel` guarantee messages are not lost on a process crash?**

No. `ThreadPoolTaskExecutor` and in-memory queues are not persistent stores. A durable handoff is required if message loss is unacceptable.

**Question 6: How does `QueueChannel` differ from `ExecutorChannel`?**

`QueueChannel` is a pollable queue whose consumer usually reads via a poller; `ExecutorChannel` dispatches work through an executor. Both can decouple caller from handler, yet durability and failure semantics must be designed separately.

**Question 7: Does a Gateway returning after sending to a `QueueChannel` mean the consumer processed it?**

No. The message may still sit in the queue, the poller may not have picked it up yet, the consumer may be failing, or backlog may be growing.

**Question 8: Does a broker confirm mean the business operation is complete?**

No. A broker confirm certifies the receipt/storage milestone per the broker contract, not the consumer's payment/order transaction.

**Question 9: Why is a transactional outbox needed when updating a DB and publishing an event?**

To prevent lost or duplicated intent from dual-writes across a DB and a broker that are not atomic by default. The outbox keeps event metadata and payload references in the same DB transaction; a relay republishes using a stable identity.

**Question 10: Does an outbox make every message processed exactly-once?**

No. The relay can publish twice if an ack is lost; consumers still must be idempotent and handle crash windows.

**Question 11: If a broker redelivers a command after the DB already committed, how should it be handled?**

Look up the durable operation ledger by stable business operation ID, verify the fingerprint and authoritative receipt, and avoid executing a second side effect.

**Question 12: Should Spring `MessageHeaders.ID` be used as an idempotency key?**

Not by default. Spring Message IDs can change when messages are rebuilt or when adapters deserialize records. Use a stable business event/operation identity.

**Question 13: Are CREATE and CANCEL for the same `orderId` duplicates?**

No. They are distinct valid operations; keys must incorporate the operation type and appropriate operation ID.

**Question 14: If the caller does not wait for a reply, should `correlationId` be omitted?**

No. Correlation/causation remains valuable for linking asynchronous completion events, logs, workflows, and status; however, it does not replace the business operation ID.

**Question 15: When an async worker throws after the Gateway returned, does the caller receive the exception immediately?**

Not through the already-completed synchronous call. You need a configured error channel/recovery/DLQ/status tracking and tests for the specific channel/adapter.

**Question 16: If a Filter drops a message in a one-way flow, is it guaranteed to be in quarantine?**

No. Filter discard and quarantine persistence are two separate steps. Configure `discardChannel` + a durable handler and verify the ack/error path.

**Question 17: When a request is invalid, should it be retried indefinitely?**

No. Deterministic errors generally require fixing the input/policy and will not heal through retries. Technical failures can use bounded retry/backoff.

**Question 18: If the Gateway is called inside `@Transactional`, does the broker send roll back automatically with the DB?**

Not by default. You must identify transaction resources and design an outbox or coordination strategy when consistency is needed.

**Question 19: Why does one-way sending still need backpressure?**

Because senders can emit faster than consumers can process. Unbounded queues/threads lead to OOM, high latency, and hard-to-recover failures.

**Question 20: Can HTTP `"ORDER_COMPLETED"` be returned right after a one-way Gateway returns?**

No, if business processing still runs afterward. Only report accepted when you have proper evidence, and provide a status/receipt endpoint or completion event for the final outcome.

**Question 21: Should an event sent to multiple subscribers use a single global dedupe marker?**

No, if each consumer must perform an independent action. Scope the key by recipient/consumer and logical event.

**Question 22: Why doesn't a Gateway replace an Outbound Channel Adapter?**

A Gateway is the Java API → message flow boundary; an outbound adapter is the flow → external system boundary. They commonly appear together.

**Question 23: If the caller catches a timeout exception, is it certain no side effect happened?**

No. A remote system may have committed while the response/ack was lost; the state is `UNKNOWN` and requires reconciliation or remote idempotency.

**Question 24: Can `replyChannel` inside a Spring Message be sent as-is over Kafka/HTTP?**

Never assume so. It may be an internal JVM object, not wire-portable, and arbitrary objects from untrusted sources should not be accepted.

**Question 25: Can Message History replace an authoritative business receipt?**

No. It helps trace components, not prove DB/remote payment commits or authorization/replay state.

**Question 26: Is a command that sat in a queue for too long still valid to execute?**

Depends on the business deadline and policy. If expired/cancelled, the consumer must follow explicit rules rather than blindly executing an expired transaction.

**Question 27: At what levels should a one-way Gateway be tested?**

Unit tests for API invocation, Spring Integration tests for proxy/channel, async/error tests, adapter/broker tests, DB/outbox/inbox tests, system crash/replay tests, and security tests for relevant boundaries.

**Question 28: What are three key questions before choosing a `void` Gateway?**

**(1)** Does the caller truly not need an immediate business reply? **(2)** At what handoff milestone does the call return, and is the message durable? **(3)** Where are errors, duplicates, and subsequent completion observed and recovered?

## 25. Quick Selection Flow

~~~mermaid
flowchart TD
    START["Application needs to send a command/event"] --> Q1{"Caller needs business result now?"}
    Q1 -->|Yes| REPLY["Request–Reply Gateway + bounded deadline"]
    Q1 -->|No| Q2{"Need durable handoff?"}
    Q2 -->|No| Q3{"Must caller wait for synchronous processing?"}
    Q3 -->|Yes| DIRECT["Void Gateway + DirectChannel"]
    Q3 -->|No| ASYNC["Void Gateway + bounded async/queue; accept loss contract"]
    Q2 -->|Yes| DURABLE["Void Gateway + outbox/durable broker/channel"]
    DURABLE --> INBOX["Idempotent consumer + status/receipt"]
    REPLY --> ERR["Timeout/error/unknown outcome handling"]
    DIRECT --> ERR
    ASYNC --> ERR
    INBOX --> ERR
~~~

The diagram is a **selection guide**, not an algorithm for every infrastructure. Both request–reply and one-way may need outbox/idempotency, retry, authorization, and observability. Base the choice on **business contract, latency, and reliability**, not solely on whether a Java method returns `void` or a class is named Gateway.

## 26. Conclusion

**Gateway Sending One-Way Messages** lets application services use a **simple Java interface** to send commands or events into a Spring Integration flow without requiring a reply payload on the initial call. With Java DSL, `@MessagingGateway` and `@Gateway(requestChannel=...)` connect `void submit(...)` to a channel; downstream can be a Filter, Transformer, Router, Service Activator, broker adapter, or larger workflow.

**Yet one-way does not mean asynchronous or unconditionally reliable.** `DirectChannel` can run synchronously and throw exceptions to the caller; `ExecutorChannel`/`QueueChannel` can return before processing yet are not durable by default; a broker confirm is not proof of business completion. Only by explicitly designing acceptance milestones, acknowledgment, transactions, backpressure, error handling, and replay can a one-way API provide a trustworthy operational contract.

In `SPRING_INTEGRATION_PATTERN`, combine Gateways with Router, Filter, Transformer, Splitter, Aggregator, Scatter–Gather, Resequencer, Claim Check, retry, error channel, correlation, and Idempotent Receiver to build loosely coupled, extensible, and testable flows. Always distinguish **"sent to channel"**, **"durably persisted on transport"**, and **"side effects completed"**; preserve a stable operation ID, store authoritative outcomes, and test crash windows. That is the foundation for using a one-way Gateway that is both simple at the API and sound when failures happen.
