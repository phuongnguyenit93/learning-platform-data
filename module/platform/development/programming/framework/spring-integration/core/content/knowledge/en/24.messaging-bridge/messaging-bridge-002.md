# Inbound Channel and Outbound Channel

## Lesson Objectives

In the **Messaging bridge** chapter of the **SPRING_INTEGRATION_CORE** module, this lesson focuses on both sides of a bridge: the channel from which the bridge receives messages and the channel to which the bridge sends messages. This is foundational knowledge for connecting endpoints, gateways, and Java DSL flows into a message flow with clear behavior.

After this lesson, you will be able to:

- Identify the input channel and output channel when reading a bridge diagram or configuration.
- Distinguish a bridge's inbound/outbound direction from that of a channel adapter.
- Choose appropriate channels and place the poller on the right endpoint.
- Trace payload, headers, execution flow, and errors as messages pass through a bridge.
- Design a way to verify message forwarding in a Java DSL example.

## 1. Inbound and Outbound Must Be Tied to a Point of View

Consider an order intake system:

~~~text
Order source
    → ordersReceived
    → bridge
    → ordersForProcessing
    → order processing endpoint
~~~

Standing at the bridge:

| Component | Role |
| --- | --- |
| Order source | Producer sending messages to the channel before the bridge |
| ordersReceived | Inbound channel of the bridge, i.e. the input channel |
| Bridge | Endpoint receiving messages on the input side and forwarding them to the output side |
| ordersForProcessing | Outbound channel of the bridge, i.e. the output channel |
| Order processing endpoint | Next consumer in the flow |

"Inbound channel" and "outbound channel" in this lesson refer to **roles relative to the bridge**. In XML configuration, the corresponding attributes are `input-channel` and `output-channel`. They are not two separate channel classes named `InboundChannel` and `OutboundChannel`.

A single channel can play two roles when viewed from different endpoints:

~~~text
Endpoint A ──send──> channel X ──receive──> Endpoint B
~~~

`channel X` is the output of A and the input of B. Therefore, names like `ordersReceived` or `ordersReady` usually convey business meaning better than generic names like inbound and outbound.

According to the [Messaging Bridge documentation](https://docs.spring.io/spring-integration/reference/bridge.html), a bridge connects message channels; a typical use case is connecting a pollable channel to a subscribable channel.

### Distinguishing from Inbound Adapters and Outbound Adapters

When talking about an **adapter**, the point of view is usually the integration application:

~~~mermaid
flowchart LR
    S["Source system"] --> IA["Inbound adapter"]
    IA --> I["Bridge input channel"]
    I --> B["Messaging bridge"]
    B --> O["Bridge output channel"]
    O --> OA["Outbound adapter"]
    OA --> T["Target system"]
~~~

- An inbound adapter brings data from a source into the application's message flow.
- An outbound adapter transfers data from the message flow to a destination.
- A bridge connects two points within the flow and does not become a protocol adapter on its own.

For example, a file-reading adapter is responsible for interacting with the filesystem. A JMS sending adapter is responsible for communicating with JMS. Placing a bridge between two channels does not add file-reading capabilities, broker connectivity, or authentication configuration. See [Channel Adapter](https://docs.spring.io/spring-integration/reference/channel-adapter.html).

A system can use a bridge solely between two internal flows, with no external system involved in that connection at all.

## 2. Contracts of Both Channel Sides

### 2.1. MessageChannel Is the Send Contract

At a basic usage level:

~~~java
boolean accepted = channel.send(message, 1_000);
~~~

A producer needs a `MessageChannel` to send. The return value indicates the send result according to the channel's mechanism; if a dispatch error or synchronous processing error occurs, the call can also throw an exception.

You cannot infer that `accepted` being `true` always means the order has been completely processed. The exact meaning depends on the receiving channel.

### 2.2. PollableChannel Has an Active Receive Operation

`PollableChannel` adds `receive()`:

~~~java
Message<?> message = queueChannel.receive(1_000);

if (message != null) {
    // Process the received message.
}
~~~

`QueueChannel` is a familiar example. A consumer must actively pull messages from the queue. For endpoints managed by Spring Integration, that work is typically performed by a poller.

### 2.3. SubscribableChannel Dispatches Messages to Registered Handlers

`SubscribableChannel` has a mechanism for registering a `MessageHandler`. It does not provide `receive()` for consumer polling.

`DirectChannel` is a common implementation. An endpoint attached to this channel is invoked via dispatch when a message is sent to it.

The send, receive, and subscribe contracts are described in [The MessageChannel Interface](https://docs.spring.io/spring-integration/reference/channel/interfaces.html).

> Inbound/outbound direction answers "where is the message going relative to the endpoint?". Pollable/subscribable answers "by what mechanism does the endpoint receive messages?". These are two different questions.

## 3. What Does a Bridge Forward?

`BridgeHandler` is the handler that performs message forwarding. In the normal case, it passes the received message to the output channel without applying business transformations. See [BridgeHandler API](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/BridgeHandler.html).

Suppose the incoming message has:

~~~text
payload = "ORDER-1001"

headers:
  traceId  = "trace-1001"
  tenantId = "shop-vn"
~~~

A pure bridge with no transformation step must allow downstream components to continue receiving that payload and those headers. When verifying, compare the data that needs to be preserved rather than assuming every pipeline keeps the exact same Java object reference: interceptors or additional endpoints can affect the result.

Comparing with other components in the module:

| Business need | Appropriate component |
| --- | --- |
| Forward the exact message from channel A to channel B | Bridge |
| Convert payload from a JSON string to an order object | Transformer |
| Choose a target channel by order type | Router |
| Reject orders that do not meet a condition | Filter |
| Group multiple messages by correlation into one result | Aggregator |
| Provide a method interface to call into the message flow | Messaging gateway |

This table shows how to make design choices for the order example. If two systems require two different data formats, represent the conversion step explicitly in the flow.

## 4. The Input Channel Type Determines How the Bridge Receives Messages

### 4.1. DirectChannel at the Input

~~~text
Producer thread
    → DirectChannel
    → BridgeHandler
    → output channel
~~~

The bridge is attached to the input channel through a subscription-based endpoint. No poller is needed to pull messages from a `DirectChannel`.

If the output is also a `DirectChannel`, the processing chain normally continues on the sending thread until it hits another execution boundary.

### 4.2. QueueChannel at the Input

~~~text
Producer thread
    → QueueChannel
    → producer can continue

Poller thread
    → receive from QueueChannel
    → BridgeHandler
    → output channel
~~~

The bridge needs a polling consumer to pull messages. The poller configuration belongs to the **endpoint consuming the input channel**, not a background task running inside `QueueChannel` itself.

You must provide an explicit poller or have an appropriate default poller in the context. In the lesson's example, the poller is declared explicitly right on the bridge.

Spring Integration distinguishes `EventDrivenConsumer` and `PollingConsumer` based on the type of channel the endpoint consumes. See [Poller](https://docs.spring.io/spring-integration/reference/polling-consumer.html).

### 4.3. Input and Output Combination Table

The table below applies to standard `DirectChannel` and `QueueChannel`:

| Input channel | Output channel | How does the bridge obtain messages? | After the bridge sends |
| --- | --- | --- | --- |
| DirectChannel | DirectChannel | Subscription, no polling | Dispatched onward to subscriber |
| QueueChannel | DirectChannel | Bridge's poller calls receive() | Dispatched to subscriber on the poll execution thread |
| DirectChannel | QueueChannel | Subscription, no polling | Message is placed into the output queue |
| QueueChannel | QueueChannel | Poller pulls from the input queue | Message is placed into the output queue |

The key distinction is that **the bridge's poller reads the input side**, while **the next consumer reads the output side**. If the output is a `QueueChannel`, the downstream endpoint still needs its own mechanism to pull messages.

With `ExecutorChannel` or `PublishSubscribeChannel`, also account for the specific executor and distribution mechanism. Do not conclude that every `SubscribableChannel` executes on the producer's thread. See [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

## 5. Java DSL Example: QueueChannel → bridge → DirectChannel

### 5.1. Problem Statement and Prerequisites

The application receives a sudden spike in orders. We want to:

1. Place orders into a bounded-capacity queue.
2. Pull at most five messages in one polling cycle.
3. Forward messages to a subscription-based processing channel.
4. Collect messages at the end of the flow to inspect payload and headers.

The example below is illustrative code in the file `BridgeDemo.java`. Compatible `spring-integration-core` and `spring-context` dependencies are required; if using Spring Boot, you can use Boot's dependency management to align versions. The syntax uses Java DSL's `IntegrationFlow.from`, with dependencies meeting the JDK requirements of your chosen version.

~~~java
package example.bridge;

import java.time.Duration;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class BridgeDemo {

    @Configuration
    @EnableIntegration
    public static class BridgeConfig {

        @Bean
        public QueueChannel bridgeInbound() {
            return new QueueChannel(100);
        }

        @Bean
        public DirectChannel bridgeOutbound() {
            return new DirectChannel();
        }

        @Bean
        public QueueChannel observedMessages() {
            return new QueueChannel(100);
        }

        @Bean
        public IntegrationFlow forwardingFlow() {
            return IntegrationFlow.from("bridgeInbound")
                    .bridge(endpoint -> endpoint
                            .id("ordersBridge")
                            .poller(Pollers.fixedDelay(Duration.ofMillis(100))
                                    .receiveTimeout(0)
                                    .maxMessagesPerPoll(5)))
                    .channel("bridgeOutbound")
                    .get();
        }

        @Bean
        public IntegrationFlow observationFlow() {
            return IntegrationFlow.from("bridgeOutbound")
                    .handle((Message<?> message) -> {
                        boolean accepted =
                                observedMessages().send(message, 1_000);

                        if (!accepted) {
                            throw new IllegalStateException(
                                    "Observation queue is full");
                        }
                    })
                    .get();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(BridgeConfig.class)) {

            MessageChannel input =
                    context.getBean("bridgeInbound", MessageChannel.class);
            QueueChannel observed =
                    context.getBean("observedMessages", QueueChannel.class);

            Message<String> sent = MessageBuilder
                    .withPayload("ORDER-1001")
                    .setHeader("traceId", "trace-1001")
                    .setHeader("tenantId", "shop-vn")
                    .build();

            if (!input.send(sent, 1_000)) {
                throw new IllegalStateException("Input queue is full");
            }

            Message<?> received = observed.receive(3_000);

            if (received == null) {
                throw new IllegalStateException(
                        "No message reached the observation queue");
            }

            if (!Objects.equals(sent.getPayload(), received.getPayload())
                    || !Objects.equals(
                            sent.getHeaders().get("traceId"),
                            received.getHeaders().get("traceId"))
                    || !Objects.equals(
                            sent.getHeaders().get("tenantId"),
                            received.getHeaders().get("tenantId"))) {
                throw new IllegalStateException(
                        "Payload or business headers changed");
            }

            System.out.println(received.getPayload() + " / "
                    + received.getHeaders().get("traceId"));
        }
    }
}
~~~

Expected output:

~~~text
ORDER-1001 / trace-1001
~~~

`observedMessages` is a collection point for demonstration purposes. In a business flow, `observationFlow` can be replaced with a service activator processing the order or an outbound adapter sending data to the target system.

### 5.2. Reading Each Configuration Part

| Configuration | Meaning in the example |
| --- | --- |
| from("bridgeInbound") | Channel that the bridge endpoint will consume |
| bridge(...) | Adds `BridgeHandler` to the flow and configures its endpoint |
| id("ordersBridge") | Names the endpoint for identification |
| fixedDelay(Duration.ofMillis(100)) | Delay between polls, measured after the previous task finishes in this configuration |
| receiveTimeout(0) | Do not wait when attempting to receive from an empty queue |
| maxMessagesPerPoll(5) | Limits the number of messages pulled in one poll |
| channel("bridgeOutbound") | Destination channel for the bridge |
| observationFlow | Subscriber consuming `bridgeOutbound` |
| observed.receive(3_000) | Bounded wait point to observe the result |

`IntegrationFlow` must be registered as a bean so Spring Integration's infrastructure creates and manages the flow's components. See [Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html).

The `fixedDelay` and `fixedRate` overloads accepting `Duration` are described in [Pollers API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/Pollers.html).

### 5.3. Execution Sequence

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as bridgeInbound: QueueChannel
    participant T as Poller
    participant B as BridgeHandler
    participant D as bridgeOutbound: DirectChannel
    participant H as Observation handler
    participant R as observedMessages: QueueChannel

    P->>Q: send(message, 1000)
    Q-->>P: true when enqueued successfully
    T->>Q: receive(0)
    Q-->>T: message
    T->>B: handleMessage(message)
    B->>D: send(message)
    D->>H: handleMessage(message)
    H->>R: send(message, 1000)
~~~

In this configuration, the observation handler runs on the poll execution thread because `bridgeOutbound` is a `DirectChannel`. The original producer may already have moved on immediately after placing the message into `bridgeInbound`.

Therefore, a `try/catch` around `input.send()` only covers the queue-enqueue phase. It does not catch exceptions that occur later on the polling task.

### 5.4. Five Messages Per Poll Is Not One Message Containing Five Orders

`maxMessagesPerPoll(5)` limits the number of message receives and deliveries in a single poll. It does not group five payloads into a list; if grouping is needed, that is the job of an aggregator.

If the queue becomes empty early, the poll may process fewer than five messages. Downstream processing time also affects the actual cadence.

Estimate for this exact configuration, when the queue always has data and tasks run sequentially:

~~~text
approximate throughput
    ≈ messages per poll / (processing time per poll + fixedDelay)

Example:
    5 messages / (0.04 seconds + 0.10 seconds)
    ≈ 35.7 messages/second
~~~

This is an estimate based on the example's assumptions, not a throughput guarantee. With an executor, multiple consumers, errors, or different scheduling configurations, you must re-evaluate the execution model.

## 6. The Same Connection Direction When Reading XML

The following configuration snippet illustrates the same connection direction. Assume the `int` namespace is declared as `http://www.springframework.org/schema/integration` in the Spring XML document:

~~~xml
<int:channel id="bridgeInbound">
    <int:queue capacity="100"/>
</int:channel>

<int:channel id="bridgeOutbound"/>

<int:bridge id="ordersBridge"
            input-channel="bridgeInbound"
            output-channel="bridgeOutbound">
    <int:poller fixed-delay="100"
                receive-timeout="0"
                max-messages-per-poll="5"/>
</int:bridge>
~~~

This is a partial configuration; a consumer registered on `bridgeOutbound` is still needed to complete the flow, like `observationFlow` in the Java DSL example.

Reading in order:

- `input-channel` is where the bridge pulls messages from.
- `output-channel` is where the bridge forwards messages to.
- `poller` is nested under `bridge` because `bridgeInbound` is a `QueueChannel`.

Choose either XML or Java DSL for the same endpoint. If you declare both versions of the bridge consuming the same `QueueChannel`, you have created competing consumers pulling messages.

## 7. When the Output Channel Is a Queue

Another combination is having the producer send synchronously to the bridge and then place the message into an output queue:

~~~java
@Bean
public DirectChannel immediateInput() {
    return new DirectChannel();
}

@Bean
public QueueChannel bufferedOutput() {
    return new QueueChannel(100);
}

@Bean
public IntegrationFlow bufferFlow() {
    return IntegrationFlow.from("immediateInput")
            .bridge(endpoint -> endpoint.id("bufferBridge"))
            .channel("bufferedOutput")
            .get();
}
~~~

Place these beans in a `@Configuration` class with `@EnableIntegration`; the channel and DSL imports are the same as in the previous example.

`bufferBridge` does not need a poller because its input is a `DirectChannel`. `bufferedOutput` simply holds messages for another consumer to pick up later.

Three points in time to distinguish in this design are:

~~~text
1. Producer calls send().
2. Message is successfully placed into bufferedOutput.
3. Downstream consumer receives and finishes processing the message.
~~~

Success at point 2 does not confirm point 3. If the requirement is "return the order processing result", design an additional request/reply contract, such as through a messaging gateway.

Do not add a poller to the bridge just because you see a `QueueChannel` on the output. The poller must be placed on whichever endpoint actually reads that queue.

## 8. Explicit Output Channel and `replyChannel`

The easiest approach to follow is explicitly specifying the bridge's output channel. However, a bridge can also route messages using the `replyChannel` header when no output channel is configured. If neither is present, the bridge has no send target and processing will fail. This rule is stated in [Messaging Bridge](https://docs.spring.io/spring-integration/reference/bridge.html).

Standalone example, not sharing channel names with the main configuration:

~~~xml
<int:channel id="requests"/>

<int:bridge id="replyBridge"
            input-channel="requests"/>
~~~

The caller of this flow must supply a reply channel, for example:

~~~java
QueueChannel replies = new QueueChannel(1);

Message<String> request = MessageBuilder
        .withPayload("PING")
        .setReplyChannel(replies)
        .build();

// requests is the MessageChannel retrieved from the context containing the XML configuration above.
if (!requests.send(request, 1_000)) {
    throw new IllegalStateException("Request was not accepted");
}

Message<?> reply = replies.receive(1_000);

if (reply == null) {
    throw new IllegalStateException("No reply received");
}
~~~

Here `replies` is a `QueueChannel` held by the caller to receive the result. A pure bridge forwards the `"PING"` payload; it does not generate a new business result on its own.

In a fixed flow, an explicit output channel lets readers see the send destination right in the configuration. Only use the `replyChannel` mechanism when it is an intentional part of the calling contract.

## 9. Capacity, Timeouts, and Errors

### 9.1. A Bounded Queue Needs a Full-Queue Policy

With `new QueueChannel(100)`, capacity is capped at 100 messages. The API provides observation methods such as `getQueueSize()` and `getRemainingCapacity()`; see [QueueChannel API](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/QueueChannel.html).

The lesson example uses `send(message, 1_000)` and checks the boolean result to avoid unbounded waiting when sending directly to the queue.

Distinguish the timeout parameters:

| Parameter | Where does it wait? |
| --- | --- |
| Timeout in `input.send(message, timeout)` | When sending to the input channel |
| Poller's `receiveTimeout` | When the poller tries to receive a message from the input queue |
| Forwarding handler's send timeout | When the handler sends to the output channel |
| Timeout in `observed.receive(timeout)` | When the observer waits for the result message |

Setting a timeout on the producer does not automatically configure timeouts for every downstream step. If the output queue can fill up, explicitly define the handler's send timeout and how to handle forwarding failures.

### 9.2. Errors Follow Execution Boundaries

| Flow | Where processing errors are observed |
| --- | --- |
| Producer → DirectChannel → bridge → DirectChannel → handler | Exceptions normally propagate back to the caller along the same call stack |
| Producer → QueueChannel → poller → bridge → handler | Errors downstream of the queue occur inside the poll task |
| Bridge → QueueChannel → another consumer | Subsequent processing errors belong to that consumer's execution |

For polling tasks managed by Spring Integration's infrastructure, the default mechanism can publish an `ErrorMessage` to an error channel. The destination is typically determined from the message's `errorChannel` header, if present, or the global `errorChannel`. Re-examine this if you replace the error handler or scheduler yourself.

Simply attaching an `errorChannel` header does not turn an exception in a synchronous `DirectChannel` call into asynchronous handling. See [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

When investigating the order example, record the endpoint name, `traceId`, receive/send timestamps, queue size, and error cause to know how far the message got.

### 9.3. A Bridge Does Not Add Storage Guarantees

A standard `QueueChannel` in the example holds messages in memory. A bridge does not provide durable persistence, retries, or system-wide exactly-once guarantees on its own.

A scenario to anticipate during design:

~~~text
Poller takes message from input queue
    → sends to output
    → downstream encounters an error
~~~

Do not assume the message will automatically return to the input queue. Recovery behavior must be designed based on the queue/message store, transactions, retries, and the capabilities of the adapter or broker in use.

If business requirements demand zero lost orders and tolerance for duplicate processing, choose an appropriate persistence/recovery mechanism and design an idempotent consumer keyed by order ID. This is an additional flow decision; placing a bridge between two channels does not solve that requirement by itself.

## 10. Common Misconceptions

| Symptom or misconception | Point to check |
| --- | --- |
| Sent to `QueueChannel` but messages are not moving forward | Is the queue-reading endpoint active and does it have a suitable poller? |
| Added a poller because the output is a `QueueChannel` | Identify the input of the bridge endpoint itself |
| `DirectChannel` reports no subscribers | Is the receiving endpoint registered and running? |
| Orders only go through one of two bridges | Are there competing consumers on the same input channel? |
| Wanting to send one copy to each branch while using `DirectChannel` | Review the broadcast requirement and channel type |
| Bridge connects fine but target system cannot understand payload | Missing a transformation step or mismatched data contract |
| `send()` succeeds so concluding the order is finished | Check whether the channel only enqueued or invoked the handler synchronously |
| Omitting output assuming the message will just terminate | A bridge needs an explicit send target or a valid `replyChannel` |
| After adding a queue, caller no longer catches errors as before | The queue decoupled the send call from subsequent processing |
| Renaming channels alone to reverse flow direction | Direction is determined by endpoint configuration and where messages are sent |

In particular, two bridges reading from the same queue do not produce two copies of a message for two sides. If the requirement is for two business handlers to both receive an event, explicitly model the corresponding distribution mechanism.

## 11. Verification Exercises

The following steps are for learners to practice on the example; they are not a report that code has already been run in your environment.

### Exercise 1: Verify the Forwarding Contract

Send a message with payload `"ORDER-1001"`, `traceId`, and `tenantId` as in the example. Receive at `observedMessages` with a finite timeout and verify:

1. A message is received.
2. The payload matches the sent value.
3. `traceId` and `tenantId` are preserved.
4. Do not infer business success solely from the `send()` result into `bridgeInbound`.

Do not use a fixed `Thread.sleep` to guess that the message has arrived. `receive(timeout)` lets you wait for the exact event being observed and detect when no result arrives.

### Exercise 2: Change the Input Channel Type

In a practice copy of the configuration, replace `bridgeInbound` with a `DirectChannel` and remove the poller from `ordersBridge`.

Record the thread names at the producer and the observation handler, then compare with the original `QueueChannel` configuration. Explain which point in the flow caused the thread difference.

### Exercise 3: Change the Output Channel Type

Change `bridgeOutbound` to a `QueueChannel` and configure a poller for the observation endpoint reading it.

Before running, redraw the two polling points:

~~~text
bridgeInbound queue
    → bridge poller
    → bridgeOutbound queue
    → observation endpoint poller
~~~

Explain why merely changing the `DirectChannel` bean to a `QueueChannel` without reviewing the downstream consumer can leave the configuration without a mechanism to receive messages.

### Exercise 4: Observe an Intentional Error

Have the observation handler throw an exception when receiving a specific order ID. Compare:

- Input is `DirectChannel`: how does the caller sending the message observe the error?
- Input is `QueueChannel`: has the caller already received the `send()` result when the processing error occurs?
- Does the error flow contain enough `traceId` and failed-message details for tracing?

Keep the exercises independent, without accidentally registering multiple bridges on the same input channel at once.

## 12. Key Takeaways

When designing both sides of a messaging bridge, determine each of the following in order:

1. **Direction:** which channel is the input and which is the output of the endpoint under consideration?
2. **Receive mechanism:** is the input consumed via subscription or polling?
3. **Forwarding behavior:** does the output dispatch immediately or buffer messages for later processing?
4. **Data contract:** should the message be preserved as-is or is a transformation step needed?
5. **Results and errors:** which stage does `send()` confirm, and on which thread do errors arise?
6. **Recoverability:** where do messages wait, and what happens when the next step fails?

Answering these six questions lets you integrate a bridge into a Spring Integration flow while maintaining visibility over every message's path, data, and processing state.
