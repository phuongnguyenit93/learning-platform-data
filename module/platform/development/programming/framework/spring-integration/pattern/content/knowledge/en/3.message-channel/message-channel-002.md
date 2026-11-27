# DirectChannel and Chained Handler Invocation

## 1. Lesson Objectives

In the **Message channel** chapter of the **SPRING_INTEGRATION_PATTERN** module, we learn how to connect components following **Enterprise Integration Patterns** using Spring Integration. The module focuses on building loosely coupled, extensible message flows; implementing Router, Filter, Transformer, Splitter, Aggregator, and Gateway; handling retries, error channels, and correlation; and testing and tracing processing branches.

This lesson focuses on **DirectChannel**: a **point-to-point, synchronous** channel that transfers messages directly from a producer to one selected handler on **the very thread calling send()**. To build a multi-step processing workflow, you connect handlers with consecutive channels or use IntegrationFlow.

After this lesson, you will be able to:

1. Explain how DirectChannel selects a handler and what synchronous processing implies.
2. Distinguish **multiple subscribers on the same DirectChannel** from **multiple sequential handlers in a flow**.
3. Build a **validate → transform → handle** chain using Java and Spring Integration DSL.
4. Predict how exceptions, transactions, and threads affect the entire chain.
5. Test invocation order, intermediate data, and error behavior properly.

## 2. How Does DirectChannel Work?

In Spring Integration, **MessageChannel** is the message-passing boundary. **DirectChannel** implements the **SubscribableChannel** interface and uses a single-subscriber dispatch mechanism. The producer sends a message via **send()**; the handler receives the message through **handleMessage()**.

~~~mermaid
flowchart LR
    P["Producer<br/>thread T1"] -->|"send(message)"| C["DirectChannel"]
    C -->|"Invoked directly on T1"| H["One MessageHandler"]
    H -->|"Returns or throws error"| P
~~~

Three key characteristics:

- **Synchronous:** send() invokes the handler directly; under normal conditions, send() only completes after the handler finishes.
- **Same thread:** the handler runs on the sender's thread and does not switch to a thread pool by default.
- **Point-to-point:** on each dispatch, one handler is chosen to receive the message; this is not a broadcast mechanism.

For example, an HTTP request calls a service, the service sends a message into a DirectChannel, and the handler executes its operation on the same execution thread. In that case, handler execution time is part of the HTTP request response time.

| Property | DirectChannel |
| --- | --- |
| Message delivery mechanism | Subscriber registration (MessageHandler) |
| Handlers receiving a single send | One handler selected by the dispatcher |
| Execution thread | The thread calling send(), unless the handler explicitly switches threads |
| Default buffer/queue | None |
| Queue-based backpressure | No internal queue to absorb spikes |
| Errors from handler | Can propagate back up the call stack to the sender |
| Sender transaction | Can continue across synchronous steps on the same thread |
| Common use cases | Internal processing steps requiring immediate results and low latency |

### Multiple Subscribers Do Not Form a Chain

Suppose the same DirectChannel registers three handlers A, B, and C:

~~~mermaid
flowchart TB
    P["Producer"] --> D["DirectChannel"]
    D -.->|"Selects one subscriber"| A["Handler A"]
    D -.->|"Or"| B["Handler B"]
    D -.->|"Or"| C["Handler C"]
~~~

These handlers are **candidate receivers**, **not** an A → B → C sequence. DirectChannel uses **UnicastingDispatcher**; when multiple subscribers exist, the load-balancing and failover strategies decide which handler receives the message and whether another handler is tried on failure. Specific defaults or options depend on the Spring Integration configuration/version.

If the requirement is *every message must pass through A, then B, then C*, build a sequential flow where A's output goes to B and B's output goes to C. Do not register all three on the same DirectChannel expecting them to be invoked sequentially.

## 3. Synchronous Processing Chain: A → B → C

Each step can send a message to the **next DirectChannel**. Because send() calls are nested on the same thread, the execution flow looks like this:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C1 as inputChannel
    participant A as Validate handler
    participant C2 as validatedChannel
    participant B as Transform handler
    participant C3 as invoiceChannel
    participant C as Invoice handler
    P->>C1: send(order)
    C1->>A: handleMessage(order)
    A->>C2: send(validatedOrder)
    C2->>B: handleMessage(validatedOrder)
    B->>C3: send(invoiceCommand)
    C3->>C: handleMessage(invoiceCommand)
    C-->>C3: return
    C3-->>B: return
    B-->>C2: return
    C2-->>A: return
    A-->>C1: return
    C1-->>P: send() completes
~~~

Key takeaway: **DirectChannel does not construct a pipeline on its own**. Chained invocation emerges from how endpoints and channels are wired together.

### 3.1. Java Example with Three DirectChannels

The example below uses Java 17+ (records) and Spring Integration/Spring Messaging classes. To make the mechanics clear, we manually register each handler. In real applications, configure endpoints as beans or IntegrationFlow so Spring manages their lifecycle.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

record OrderPlaced(String orderId, BigDecimal amount) {}
record InvoiceCommand(String orderId, BigDecimal amount) {}

DirectChannel inputChannel = new DirectChannel();
DirectChannel validatedChannel = new DirectChannel();
DirectChannel invoiceChannel = new DirectChannel();

List<String> steps = new ArrayList<>();

// Handler 1: validate data and send to the next channel.
inputChannel.subscribe(message -> {
    steps.add("validate");
    OrderPlaced order = (OrderPlaced) message.getPayload();

    if (order.orderId() == null || order.orderId().isBlank()
            || order.amount() == null
            || order.amount().signum() <= 0) {
        throw new IllegalArgumentException("Invalid order");
    }

    validatedChannel.send(message);
});

// Handler 2: convert payload and mark the event type.
validatedChannel.subscribe(message -> {
    steps.add("transform");
    OrderPlaced order = (OrderPlaced) message.getPayload();

    Message<InvoiceCommand> next =
            MessageBuilder.withPayload(
                    new InvoiceCommand(order.orderId(), order.amount()))
                    .copyHeaders(message.getHeaders())
                    .setHeader("eventType", "invoice.requested")
                    .build();

    invoiceChannel.send(next);
});

// Handler 3: perform the final operation.
invoiceChannel.subscribe(message -> {
    steps.add("invoice");
    InvoiceCommand command = (InvoiceCommand) message.getPayload();
    System.out.println("Create invoice for " + command.orderId());
});

Message<OrderPlaced> event = MessageBuilder.withPayload(
                new OrderPlaced("ORD-42", new BigDecimal("125000")))
        .setHeader("eventType", "order.placed")
        .setHeader("correlationId", "ORD-42")
        .build();

boolean accepted = inputChannel.send(event);

System.out.println(accepted); // true when dispatch succeeds
System.out.println(steps);    // [validate, transform, invoice]
~~~

Here, **each DirectChannel has exactly one subscriber**, making the behavior straightforward and predictable. Step by step:

1. The producer sends **OrderPlaced** into inputChannel.
2. The first handler validates the data, then calls **validatedChannel.send(message)**.
3. The second handler creates **InvoiceCommand** and sends it into invoiceChannel.
4. The final handler executes the business logic and returns.
5. Only after all nested calls finish does **inputChannel.send()** return.

Using **copyHeaders** should be intentional: for example, keeping correlationId to trace the order while updating eventType from order.placed to invoice.requested. Do not blindly copy headers that are only meaningful to a prior step or contain sensitive information. MessageBuilder builds a new message; it does not mutate the original message's payload/headers.

> **Practical note:** the example uses a List to observe steps in a single run. In a service handling concurrent requests, do not share an unsynchronized ArrayList for activity tracking. Use logs/tracing keyed by correlationId or an appropriate observability tool.

### 3.2. Why Does a Synchronous Flow "Chain Calls"?

If you view send() calls as method calls, the stack at the final step can be pictured as:

~~~text
producer.publish()
  inputChannel.send(order)
    validateHandler.handleMessage(order)
      validatedChannel.send(order)
        transformHandler.handleMessage(order)
          invoiceChannel.send(invoice)
            invoiceHandler.handleMessage(invoice)
~~~

There is no intermediate message queue and no new thread created by default. That is why DirectChannel is suited for steps needing fast validation/transformation, sharing a transaction, or sharing a processing context.

## 4. Designing a Chain with Spring Integration Java DSL

Registering handlers with **subscribe()** is useful for learning the mechanics, but when building Spring applications, **IntegrationFlow** makes the business pipeline explicit.

Example illustrating a flow that receives OrderPlaced, filters valid orders, transforms them into InvoiceCommand, and calls a service:

~~~java
import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class OrderIntegrationConfig {

    @Bean
    MessageChannel orderInputChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow orderFlow(InvoiceService invoiceService) {
        return IntegrationFlow.from("orderInputChannel")
                .filter(OrderPlaced.class, order ->
                        order.amount() != null
                        && order.amount().signum() > 0)
                .transform(OrderPlaced.class, order ->
                        new InvoiceCommand(order.orderId(), order.amount()))
                .handle(InvoiceCommand.class, (command, headers) -> {
                    invoiceService.create(command);
                    return null; // terminal endpoint does not emit further messages
                })
                .get();
    }
}

interface InvoiceService {
    void create(InvoiceCommand invoice);
}

record OrderPlaced(String orderId, BigDecimal amount) {}
record InvoiceCommand(String orderId, BigDecimal amount) {}
~~~

**The flow executes sequentially** through Filter → Transformer → Service Activator. In a default synchronous pipeline using direct channels between endpoints, each step immediately calls the next step on the same thread. Intermediate channels are managed by the DSL, so the example does not need to name every channel.

If an order fails the Filter condition, the message is dropped from the flow by default, and subsequent steps **do not** run. Depending on requirements, you can configure a discard channel or throw an exception on rejection. Therefore, **send() returning true does not mean every message reaches InvoiceService**.

In production code, add orderId validation and clearly specify how invalid orders are handled. For branching steps, you can add a Router; for list payloads, you can add a Splitter followed by an Aggregator with proper correlation/sequence metadata. These choices should be driven by the message contract, not merely by the pipeline shape.

## 5. Threads, Ordering, and Concurrency

### 5.1. Same Thread for a Single Send

If thread **T1** calls send(), the pipeline's synchronous handlers execute on T1. Steps run **in order within a single send**, and the call stack accurately reflects the processing chain.

However, two producers can concurrently call send() from **T1** and **T2** into the same DirectChannel:

~~~mermaid
flowchart LR
    P1["Request 1 / T1"] --> D["DirectChannel"]
    P2["Request 2 / T2"] --> D
    D --> H["One handler logic"]
    H --> S["Business service"]
~~~

In that case, the handler can be invoked concurrently from two threads. DirectChannel **does not serialize all requests system-wide** and **does not guarantee global ordering** across send() calls from multiple senders.

Design implications:

- Handlers must be **thread-safe** if they hold shared state.
- Do not assume request A sent earlier is guaranteed to finish before request B.
- If ordering must be preserved per business key, use an appropriate mechanism: locking by routing key, partitioning, or a component with controlled queues/consumers.
- Avoid blocking for long periods in handlers because it holds the sender's thread.

### 5.2. Comparison with Other Channels

| Channel | Delivery Style | Characteristics vs. DirectChannel |
| --- | --- | --- |
| **DirectChannel** | Unicast, synchronous handler invocation | No queue; same sender thread |
| **ExecutorChannel** | Unicast, offloads processing via Executor | Switches threads; does not preserve thread-bound transactions |
| **QueueChannel** | PollableChannel, holds messages in a queue | Producer and consumer decoupled in time; requires poller/consumer |
| **PublishSubscribeChannel** | Delivers to multiple subscribers | Suitable for fan-out; synchronous by default, but different semantics |
| **RendezvousChannel** | Sender/receiver rendezvous to hand off messages | Creates a synchronization point between both sides instead of invoking subscribers directly |

Do not choose ExecutorChannel or QueueChannel just to "speed things up" if downstream work must complete before the producer returns. Conversely, do not use DirectChannel for slow work just because the code looks shorter; it can inflate response times and reduce request-handling thread throughput.

## 6. How Do Exceptions and Transactions Flow Through the Chain?

### 6.1. Exceptions in Handlers

With a synchronous DirectChannel, if a handler throws an exception and no layer catches it, the send() call typically terminates with the exception propagating up the call stack; depending on the dispatcher and endpoint, the exception may be wrapped in a messaging exception.

~~~java
DirectChannel input = new DirectChannel();

input.subscribe(message -> {
    throw new IllegalStateException("Unable to connect to target service");
});

try {
    input.send(MessageBuilder.withPayload("ORD-42").build());
} catch (RuntimeException ex) {
    // Log with correlationId, apply retry/error reporting
    // according to the application's policy.
}
~~~

Do not assume every exception from send() automatically appears on an **errorChannel**. Publishing an **ErrorMessage** to an error channel depends on how the flow/gateway/adapter and error handlers are configured. When threads switch via ExecutorChannel or a poller, exception propagation back to the sender also differs.

If a **DirectChannel has multiple subscribers**, **failover** configuration can cause the dispatcher to try another subscriber when the first handler fails. This is not automatic business retry; be careful with operations that have already performed partial side effects before failing.

### 6.2. Transactions

DirectChannel runs on the current thread, so it can participate in the producer's **thread-bound transaction context** when transactions are managed by Spring. For example: a `@Transactional` service sends a message into a DirectChannel chain, and the final handler calls a repository; database operations sharing the same transaction manager can belong to a single transaction.

However, this **does not** create distributed transactions for HTTP calls, email, brokers, or external systems. A handler that successfully sends an external request and then rolls back a subsequent DB operation can leave inconsistent state. When cross-system reliability is needed, consider outbox, idempotency, bounded retries, or transactional mechanisms supported by those systems.

| Scenario | What to Expect |
| --- | --- |
| DirectChannel → synchronous handler → repository with same transaction manager | Can participate in the sender's transaction |
| DirectChannel → ExecutorChannel → handler | Typically switches threads; sender's transaction does not automatically propagate |
| DirectChannel → HTTP/broker adapter | Remote side effects do not automatically roll back with the DB |
| Handler throws mid-chain | Subsequent steps do not run on the normal path; transaction may roll back per policy |
| Handler performed side effects before throwing | Must design idempotent/compensating actions; do not assume automatic undo |

## 7. Rules for Designing Maintainable Handler Chains

### Single Responsibility per Step

Separate Validate, Transform, and Act into components with clear contracts:

- **Validate:** check validity and emit an error or route to discard; avoid unnecessary side effects.
- **Transform:** construct a new payload while retaining genuinely meaningful headers.
- **Handle:** perform the business action, such as saving an invoice, publishing an event, or calling an external system.

When a Router is needed, branches after the Router can continue via separate DirectChannels; when using a Filter, clearly define rejection conditions; when using Splitter/Aggregator, maintain proper correlation and sequence metadata.

### One Channel, One Clear Role

Name channels by purpose, such as **orderInputChannel**, **validatedOrdersChannel**, **invoiceCommandsChannel**. Avoid reusing the same channel for both sending business commands and returning responses of a different type without an explicit contract.

### Design for Observability

Track the following data:

| Observability Data | Purpose |
| --- | --- |
| correlationId or business key | Links steps of the same transaction |
| traceId/spanId | Traces the call stack and path across components |
| Channel/endpoint name | Identifies which step received the message |
| Processing duration per handler | Identifies time-consuming steps |
| Error/rejection rate | Distinguishes infrastructure errors from data filtered out |

Do not log full payloads/headers if they contain sensitive data. You can use metrics, observation/tracing, or interceptors appropriate to your Spring Integration version and operations tooling; verify that collection does not leak sensitive information.

## 8. Testing Handler Order and Failures

The first test verifies two core properties of DirectChannel: **same thread** and **sequential invocation when channels are chained**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.support.MessageBuilder;

class DirectChannelChainTest {

    @Test
    void callsHandlersInOrderOnTheSenderThread() {
        DirectChannel first = new DirectChannel();
        DirectChannel second = new DirectChannel();
        DirectChannel third = new DirectChannel();

        List<String> calls = new ArrayList<>();
        Thread sender = Thread.currentThread();
        AtomicReference<Thread> lastHandlerThread = new AtomicReference<>();

        first.subscribe(message -> {
            calls.add("validate");
            second.send(message);
        });
        second.subscribe(message -> {
            calls.add("transform");
            third.send(MessageBuilder
                    .withPayload(((String) message.getPayload()).trim())
                    .copyHeaders(message.getHeaders())
                    .build());
        });
        third.subscribe(message -> {
            calls.add("handle:" + message.getPayload());
            lastHandlerThread.set(Thread.currentThread());
        });

        boolean accepted = first.send(
                MessageBuilder.withPayload(" ORD-42 ").build());

        assertTrue(accepted);
        assertEquals(List.of("validate", "transform", "handle:ORD-42"),
                calls);
        assertSame(sender, lastHandlerThread.get());
    }

    @Test
    void failureStopsTheNextStepAndReachesTheCaller() {
        DirectChannel first = new DirectChannel();
        DirectChannel second = new DirectChannel();

        List<String> calls = new ArrayList<>();
        first.subscribe(message -> {
            calls.add("validate");
            throw new IllegalArgumentException("Invalid data");
        });
        second.subscribe(message -> calls.add("should-not-run"));

        assertThrows(RuntimeException.class,
                () -> first.send(
                        MessageBuilder.withPayload("bad").build()));
        assertEquals(List.of("validate"), calls);
    }
}
~~~

Test 1 confirms handlers are called in order within a single send() via the first → second → third wiring. Test 2 confirms when the first handler throws and does not forward, the next handler does not run. These are local behavior tests and do not verify transactions, brokers, dynamic routing, or complex error channel setups.

In real IntegrationFlow tests, add cases for Filter rejection, multiple concurrent producers, a slow handler, and Router paths; use test data with correlationId to trace each message.

## 9. Common Confusions

| Confusion | Why It Is Wrong | Correct Understanding |
| --- | --- | --- |
| Registering A, B, C on the same DirectChannel invokes A → B → C | The dispatcher is unicast | Use sequential channels or IntegrationFlow |
| DirectChannel has a built-in queue | It does not buffer messages | Use QueueChannel when decoupling send/receive timing |
| DirectChannel always has only one thread | Each send uses the producer's own thread | Different senders can execute concurrently |
| send() returning true means the whole business task succeeded | Flow may have Filters, branches, or external side effects | Define acknowledgment per business requirements |
| Exceptions always go to errorChannel automatically | Depends on endpoint and error handling configuration | Define an explicit error handling policy |
| Adding @Transactional rolls back HTTP/broker calls | Local transactions do not span remote side effects | Design outbox/idempotency/compensation when needed |
| Multiple subscribers guarantee even load distribution | Load balancing/failover depends on configuration and handler load can vary | Measure in practice and configure an appropriate strategy |
| Replacing DirectChannel with ExecutorChannel does not affect semantics | Threads, transactions, and exception propagation change | Design async boundaries explicitly and re-test |

## 10. Practice Exercise: Three-Step Order Processing

Suppose a system receives an **order.placed** event and needs to:

1. **Validate:** positive amount, non-empty orderId.
2. **Enrich/Transform:** create a **PaymentRequest(orderId, amount, tenantId)** record and attach header eventType=payment.requested.
3. **Handle:** call PaymentService to process the request, recording the result and correlationId.

Implement a **synchronous IntegrationFlow** starting from DirectChannel **orderInputChannel**. Create two tests:

- When the order is valid, all three steps are invoked in order and PaymentService receives the exact expected data.
- When the order is invalid, the Transform step and PaymentService are not invoked; explicitly decide whether the Filter drops the message or throws an error.

Then try replacing one boundary with an **ExecutorChannel** and answer: which thread runs the final handler? Do exceptions from PaymentService still propagate directly to the producer? Does the producer's transaction automatically exist on the new thread?

**Self-Check Questions:**

1. Why does a DirectChannel with three subscribers not form a three-handler chain?
2. When should you choose DirectChannel over ExecutorChannel or QueueChannel?
3. Does a flow using DirectChannel guarantee that all messages across the system are processed in order?
4. What happens if a middle handler throws an exception before sending to the next channel?
5. When is sharing a transaction an advantage, and what are its limits with external systems?

## 11. DirectChannel Adoption Checklist

- Determine upfront whether the flow must be **synchronous** or asynchronous.
- Document clearly that each channel delivers **one message to one selected handler**; use sequential flows for multi-step processing.
- Ensure handlers are thread-safe and do not hold producer threads too long.
- Clearly specify behavior for data dropped by Filters and exceptions at each step.
- Test processing order, execution threads, metadata/correlation, and error paths.
- Evaluate impacts on transactions and external side effects.
- Monitor per-endpoint latency and avoid logging sensitive data.

**Practical Conclusion:** DirectChannel is the right fit for Spring Integration segments needing immediate invocation, same-thread execution, and tight linkage to the caller. "Chained handler invocation" is a result of **flow architecture**: each handler forwards to the next step, or the DSL wires endpoints together. Understanding this distinction lets Router, Filter, Transformer, and other components work together predictably and testably.

## References

- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): MessageChannel types, DirectChannel, and dispatch differences.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): defining IntegrationFlow and chained endpoints.
- [Spring Integration API — DirectChannel](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/DirectChannel.html): DirectChannel interface and configuration.
- [Spring Framework Reference — Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction scope and thread-bound context mechanisms.
