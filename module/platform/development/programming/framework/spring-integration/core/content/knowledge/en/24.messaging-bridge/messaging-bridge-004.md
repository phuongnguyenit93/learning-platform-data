# Request-Reply Bridge

## 1. Objectives and Use Case

In the **Messaging bridge** chapter of the **SPRING_INTEGRATION_CORE** module, this lesson explains how to place a bridge inside a request-reply flow: forwarding the request to the processor and returning the result to the right caller. The focus is on the relationship between `Message`, `MessageChannel`, endpoints, gateways, and Java DSL.

After this lesson, you will be able to:

- Explain when a bridge uses its output channel and when it uses the `replyChannel` header.
- Design the request and reply paths without confusing a bridge with a gateway.
- Preserve the reply path when the flow passes through a transformer, router, filter, or aggregator.
- Identify errors caused by missing destinations, lost headers, wait timeouts, and mismatched reply types.
- Write tests for the reply path and channel precedence rules.

Consider a quoting service: the application sends a product code and quantity, the pricing engine produces a result, and the result returns to the original call. We want to connect the parts of the flow using clearly named channels so each point can be easily replaced or observed.

A bridge handles connecting those points. The pricing engine remains responsible for producing the business result.

## 2. What Does a Bridge Do in a Request-Reply Flow?

### 2.1. A Bridge Forwards Messages

`BridgeHandler` forwards the received message to the next destination without transforming the payload. A bridge at the end of a flow may omit an output channel; in that case, the `replyChannel` header provides the destination. If no destination can be resolved, processing fails with a messaging exception. See [`BridgeHandler` API](https://docs.spring.io/spring-integration/api/org/springframework/integration/handler/BridgeHandler.html).

Therefore, the phrase "request-reply bridge" describes **the role of the bridge within the overall flow**, not that a bridge calls a service itself and manages waiting for a result.

Example:

~~~text
QuoteRequest
    -> bridge forwarding request
    -> pricing engine
    -> QuoteReply
    -> bridge forwarding result
    -> waiting reply destination
~~~

The first bridge sees a request. The final bridge sees a reply. Both only forward messages at their respective positions.

If you remove the pricing engine and connect the request directly to the final bridge, the caller may receive its own input data back. That is echo behavior, not a successful quote. If the gateway expects `QuoteReply` but receives `QuoteRequest`, return-type mapping may also fail.

### 2.2. Three Components, Three Responsibilities

| Component | Responsibility in the quote example | Does it manage the request-reply call? |
| --- | --- | --- |
| Messaging gateway | Translates a Java call into a request message and receives the reply | Yes |
| Bridge | Forwards the message to the next channel or reply path | Does not create its own reply wait |
| Pricing endpoint | Receives the request and creates the business result | Produces the reply content |

Also distinguish these two ways of connecting flows in Java DSL:

~~~java
// Forward to the next flow.
IntegrationFlow.from("outerInput")
        .bridge()
        .channel("pricingInput")
        .get();
~~~

~~~java
// Call a subflow, receive the result, and then continue the current flow.
IntegrationFlow.from("outerInput")
        .gateway("pricingInput")
        .channel("afterPricing")
        .get();
~~~

These are **two alternatives**; do not register both at the same time for the same example. The `gateway()` operator has a mechanism to send a request and receive a reply so the outer flow can continue processing. See [Java DSL `gateway()`](https://docs.spring.io/spring-integration/reference/dsl/java-gateway.html).

Use a bridge when you want to hand off a message and keep using the existing reply path. Use a gateway when one flow needs to invoke another flow as a processing step that returns a result.

## 3. Rules for Choosing the Next Send Destination

This section covers standard configuration, without routing slips or custom handlers.

| Bridge output channel | `replyChannel` header | Send destination |
| --- | --- | --- |
| Present | Present or absent | Configured output channel |
| Absent | Present and resolvable | Channel from the header |
| Absent | Absent | Error due to missing send destination |

The rule of omitting the output channel to use the reply channel is described in [the Messaging Bridge documentation](https://docs.spring.io/spring-integration/reference/bridge.html).

Minimal XML example for the two positions:

~~~xml
<int:bridge input-channel="quoteRequests"
            output-channel="quoteProcessing"/>

<int:bridge input-channel="quoteResponses"/>
~~~

This is a configuration snippet; it must be placed inside a Spring XML document that declares the `int` namespace and the corresponding channels.

The second bridge does not mean "send nowhere". It requires the incoming message to carry a reply path.

One detail to watch: having a configured output channel that fails to send does **not** cause the bridge to fall back to `replyChannel`. To handle send failures, you must design an explicit error policy.

### 3.1. `replyChannel` Is the Reply Address

The `MessageHeaders.REPLY_CHANNEL` header typically holds a `MessageChannel` object or a string resolved by the infrastructure to a channel. If it is a bean name, that bean must exist in the corresponding context. This header differs from `correlationId`: one header specifies where to send, while the other links related messages. See [Message Headers](https://docs.spring.io/spring-integration/reference/message.html).

In request-reply via a gateway, the gateway normally creates a temporary reply channel and sets it on the request. Downstream endpoints must preserve this context until it is time to reply.

Illustrative message example:

~~~text
payload:
  QuoteRequest("BOOK-01", 2)

headers:
  replyChannel: <temporary channel for call A>
  traceId: "trace-A"
~~~

The business result can have a new payload:

~~~text
payload:
  QuoteReply("BOOK-01", 2, 300000)

headers:
  replyChannel: <temporary channel for call A>
  traceId: "trace-A"
~~~

The final bridge uses call A's reply path. When call B runs concurrently, it must preserve B's reply path.

Do not assume that merely having the same `correlationId` tells a bridge which gateway is waiting. A bridge is not a store that matches requests by correlation ID.

## 4. Complete Java DSL Example: Quote Flow

The example uses Java 17+, Spring Integration 6+, and `spring-integration-core`. If the project uses Spring Boot, you can use the Spring Integration starter and let the project's BOM manage versions.

The classes below are placed in the same package `example.bridge`; each `public` type goes in its own Java file. File names in the presentation are only for practice.

### 4.1. Request and Result Data

`QuoteRequest.java`:

~~~java
package example.bridge;

public record QuoteRequest(String sku, int quantity) {
}
~~~

`QuoteReply.java`:

~~~java
package example.bridge;

public record QuoteReply(
        String sku,
        int quantity,
        long totalVnd) {
}
~~~

Using integer values in VND keeps the example free from floating-point arithmetic noise.

### 4.2. Gateway for the Caller

`QuoteGateway.java`:

~~~java
package example.bridge;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
        defaultRequestChannel = "quoteRequests",
        defaultRequestTimeout = "1000",
        defaultReplyTimeout = "2000")
public interface QuoteGateway {

    QuoteReply quote(QuoteRequest request);
}
~~~

Timeout values in the annotation are in milliseconds. The example deliberately sets values so readers can see the intended wait limits; these limits also depend on where the flow actually waits, as explained in a later section. See [`MessagingGateway` API](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/MessagingGateway.html).

There is no need to declare `defaultReplyChannel` in this example: the gateway's temporary reply path is sufficient.

### 4.3. Channels and Three Flows

`QuoteFlowConfig.java`:

~~~java
package example.bridge;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
@IntegrationComponentScan(basePackageClasses = QuoteGateway.class)
public class QuoteFlowConfig {

    @Bean
    public DirectChannel quoteRequests() {
        return new DirectChannel();
    }

    @Bean
    public DirectChannel quoteProcessing() {
        return new DirectChannel();
    }

    @Bean
    public DirectChannel quoteResponses() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow requestBridgeFlow() {
        return IntegrationFlow.from(quoteRequests())
                .bridge()
                .channel(quoteProcessing())
                .get();
    }

    @Bean
    public IntegrationFlow pricingFlow() {
        return IntegrationFlow.from(quoteProcessing())
                .handle(QuoteRequest.class,
                        (request, headers) -> calculate(request))
                .channel(quoteResponses())
                .get();
    }

    @Bean
    public IntegrationFlow replyBridgeFlow() {
        return IntegrationFlow.from(quoteResponses())
                .bridge()
                .get();
    }

    private QuoteReply calculate(QuoteRequest request) {
        if (request.quantity() <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be greater than zero");
        }

        if (!"BOOK-01".equals(request.sku())) {
            throw new IllegalArgumentException(
                    "unsupported sku: " + request.sku());
        }

        long unitPriceVnd = 150_000L;
        long totalVnd = Math.multiplyExact(
                unitPriceVnd, request.quantity());

        return new QuoteReply(
                request.sku(), request.quantity(), totalVnd);
    }
}
~~~

`@IntegrationComponentScan` scans for gateway interfaces in the specified package. Regular component scanning alone is not enough to detect interfaces this way. See [Messaging Gateway Annotation and XML Configuration](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-configuration-with-annotations-and-xml).

The three flows are separated to make each connection point explicit:

1. `requestBridgeFlow` forwards the request from `quoteRequests` to `quoteProcessing`.
2. `pricingFlow` calculates the price and sends the reply to `quoteResponses`.
3. `replyBridgeFlow` has no output channel, so it forwards the reply to the channel in the header.

The pricing endpoint is configured with `quoteResponses` as its output, so it sends the result there first. The presence of the reply header does not cause it to bypass that channel.

### 4.4. Startup and Sample Invocation

`BridgeDemo.java`:

~~~java
package example.bridge;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class BridgeDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             QuoteFlowConfig.class)) {

            QuoteGateway gateway =
                    context.getBean(QuoteGateway.class);

            QuoteReply reply = gateway.quote(
                    new QuoteRequest("BOOK-01", 2));

            System.out.println(reply);
        }
    }
}
~~~

Expected result:

~~~text
QuoteReply[sku=BOOK-01, quantity=2, totalVnd=300000]
~~~

### 4.5. Tracing the Path of One Call

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as QuoteGateway
    participant B1 as Request bridge
    participant P as Pricing endpoint
    participant B2 as Reply bridge
    participant R as Temporary reply channel

    C->>G: quote(BOOK-01, 2)
    G->>B1: QuoteRequest and replyChannel=R
    B1->>P: Forward request
    P->>B2: QuoteReply via quoteResponses
    B2->>R: Forward reply via header
    R-->>G: Call result
    G-->>C: QuoteReply
~~~

The diagram abbreviates the input channel names to focus on the reply path. In the actual configuration, the message passes through `quoteRequests`, `quoteProcessing`, and `quoteResponses` exactly as declared in the three flows.

If the pricing endpoint ends with a return value and has no dedicated output channel, it can reply directly via `replyChannel`; in that case, an extra final bridge is unnecessary. The example intentionally keeps `quoteResponses` as a named connection point to demonstrate when a reply bridge is needed.

## 5. Preserving the Reply Path While Processing Messages

### 5.1. Returning a Payload from an Endpoint

In the example, `calculate` simply returns a `QuoteReply`. The reply-producing endpoint infrastructure builds the result message and propagates appropriate request headers according to its default configuration. This style reduces the risk of manually constructing a message missing the reply header.

If you build a message manually and send it directly to a channel, actively preserve the necessary context. The example below assumes `request` is the input message:

~~~java
Message<QuoteReply> response = MessageBuilder
        .withPayload(new QuoteReply("BOOK-01", 2, 300_000L))
        .copyHeaders(request.getHeaders())
        .build();
~~~

Corresponding imports:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;
~~~

This snippet illustrates copying headers within an internal flow. When integrating across trust boundaries or different protocols, choose which headers are allowed to propagate according to the system contract.

An easy way to lose the reply path is to build a message from the payload alone and send it to `quoteResponses`:

~~~java
// Does not carry the original request's context.
Message<QuoteReply> detachedResponse = MessageBuilder
        .withPayload(new QuoteReply("BOOK-01", 2, 300_000L))
        .build();
~~~

If this message is sent directly into the final bridge, the bridge has neither an output channel nor a `replyChannel`.

The key point is to distinguish **returning a result from an endpoint** from **manually building and sending a message outside that endpoint**. These two approaches should not be treated as equivalent for header propagation.

### 5.2. Passing Through Transformer, Router, Filter, and Aggregator

Other integration patterns must also satisfy the flow's reply contract:

| Component in the request-reply path | What needs to be designed |
| --- | --- |
| Transformer | Output payload has the type needed downstream; do not lose reply context when customizing headers |
| Router | Every valid branch leads to a result or an intentional termination |
| Filter | If rejecting a request, define whether the caller receives an error, a rejection result, or times out |
| Splitter and aggregator | Aggregate results into a contract-compliant reply before returning to the gateway |
| Final bridge | Place only at the point where the message is ready to become the reply |

For example, a quote request rejected by a filter and silently dropped will not turn into an "invalid item" response on its own. If the contract requires a rejection result, create that result or raise an explicit error.

Similarly, placing a reply bridge immediately after a splitter can push partial results back to a gateway that expects only a single reply. Define the aggregation point before closing the processing path.

A bridge does not substitute for routing logic, acceptance decisions, or message-group completion.

### 5.3. Process Boundaries

The temporary channel object belongs to the current context and call lifecycle. Do not treat it as a durable address that can be sent verbatim over a broker, stored long-term, and reused in another process.

If the flow crosses JMS, AMQP, or a network protocol, use the gateway, adapter, and correlation mechanism of the appropriate transport. Local bridges can still connect channels on each side, but the cross-system request-reply contract must be designed at the transport boundary.

## 6. Putting a QueueChannel on the Request Path

### 6.1. A Bridge Does Not Create an Asynchronous Thread on Its Own

In the main example, all channels are `DirectChannel`s. The flow runs on the sender's thread under standard configuration.

`QueueChannel` holds messages for a consumer to receive later; the endpoint reading the queue needs a poller. `ExecutorChannel` delegates execution via an executor. Thread handoffs come from the channel and execution infrastructure, not from the name "bridge". See [MessageChannel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

To have the caller enqueue the request and wait for the result while a poller processes it, replace the **two corresponding beans** in `QuoteFlowConfig`; keep the rest:

~~~java
@Bean
public QueueChannel quoteRequests() {
    return new QueueChannel(100);
}

@Bean
public IntegrationFlow requestBridgeFlow() {
    return IntegrationFlow.from(quoteRequests())
            .bridge(endpoint -> endpoint.poller(
                    Pollers.fixedDelay(50)
                            .maxMessagesPerPoll(10)))
            .channel(quoteProcessing())
            .get();
}
~~~

Add imports:

~~~java
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.Pollers;
~~~

Do not keep both the old and new beans with the same name.

The processing path becomes:

~~~text
Caller thread:
  gateway -> quoteRequests queue -> wait for reply

Poller thread:
  pull request
    -> bridge
    -> quoteProcessing
    -> pricing calculation
    -> quoteResponses
    -> final bridge
    -> temporary reply channel
~~~

The gateway can still present a synchronous API to the caller even though part of the flow runs on another thread.

### 6.2. Understanding Poller Configuration Under Operating Conditions

In the snippet above:

- The queue has a capacity of 100 messages.
- `fixedDelay(50)` sets a 50 ms pause between polls using fixed-delay semantics.
- `maxMessagesPerPoll(10)` caps the number of messages processed in a single poll.

Do not take `10 / 50 ms` and claim that as actual throughput. If steps after the bridge run synchronously on the poller thread, the time spent pricing and sending results also takes up time within the poll. Configuring a poller for a bridge is illustrated in [Messaging Bridge with Java DSL](https://docs.spring.io/spring-integration/reference/bridge.html#configuring-a-bridge-with-the-java-dsl).

In operation, monitor queue depth, time spent in the queue, and end-to-end latency from send to reply receipt. A queue not being full does not guarantee requests are still being answered within the caller's wait timeout.

## 7. Distinguishing Timeout Limits

| Configuration | Which stage does it bound? | Example |
| --- | --- | --- |
| Gateway `requestTimeout` | Wait time to send the request if sending can block | Request queue is already full |
| Gateway `replyTimeout` | Wait time to receive the reply when the gateway enters its wait stage | Request was accepted into the queue, but the result has not arrived yet |
| Bridge `sendTimeout` | Wait time to send the message to the bridge's target if the target can block | Bridge forwards to a bounded queue |
| HTTP client or external service timeout | Time allowed for the corresponding I/O operation | Pricing endpoint calls a supplier API |

A gateway timeout does not replace timeouts at the I/O layer.

### 7.1. With DirectChannel, `replyTimeout` Does Not Interrupt a Running Method

In the main configuration, the gateway calls into a synchronous processing chain. If `calculate` takes 10 seconds, setting `defaultReplyTimeout = "2000"` does not cause Java to abort the method after 2 seconds. The gateway is still inside the request-sending call stack.

When the request goes through a queue and executes on another thread, the gateway can wait for the reply with the configured timeout. See [Gateway Behavior When Downstream Processing Takes Longer](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-behavior-when-no-response-arrives).

### 7.2. Timing Out Does Not Mean the Work Was Canceled

Example of a call processed through a queue:

~~~text
t = 0 ms       gateway sends request
t = 2000 ms    reply wait times out
t = 2600 ms    endpoint finishes producing result
~~~

The caller may have stopped waiting, yet the work still completes. You need a policy for late results and retries.

In an order-recording or payment-charging system, if the application resends after a timeout, use a business request ID and appropriate deduplication. A bridge does not provide exactly-once guarantees.

With a standard gateway, timing out can return `null`; the application must define how to interpret a missing result. If your project version supports an option to raise an error on timeout, configure it according to the desired contract and test that behavior. Do not infer from the mere existence of a bridge that a reply is guaranteed to arrive.

## 8. Named Reply Channels and the Risk of Misrouting

`quoteResponses` in the example is an intermediate channel in the flow. It is not the channel the gateway is directly waiting on for the result.

The gateway waits on the temporary channel in the header; the final bridge connects these two points:

~~~text
quoteResponses -> final bridge -> call's replyChannel
~~~

If you declare `defaultReplyChannel` for a gateway, Spring Integration uses internal bridging infrastructure to connect the configured reply channel to the call's temporary channel. See [Setting the Default Reply Channel](https://docs.spring.io/spring-integration/reference/gateway.html#setting-the-default-reply-channel).

When choosing that approach, redesign the reply path consistently. Do not mechanically add another "reply listener" consumer on the same channel assuming it only observes data.

On a point-to-point channel, adding a consumer can cause messages to be delivered to that consumer instead of the intended reply path. To observe messages, use a wire tap or an appropriate interceptor. If you use publish-subscribe for a named reply path, explicitly design each subscriber and the impact of subscriber errors on the flow.

Another dangerous configuration is:

~~~text
quoteResponses -> bridge -> quoteResponses
~~~

Because the bridge already has an output channel, it keeps picking that output; it does not automatically detect "this is the final reply" and switch to the header. On a synchronous path, a loop can recurse until the stack overflows; with a queue, it can cause messages to spin endlessly.

Draw the path for both requests and replies before adding a bridge at a connection point.

## 9. Errors and Diagnosis

### 9.1. Same-Thread Errors vs. Errors Across an Asynchronous Boundary

With `DirectChannel`, processing errors can propagate back along the call stack to the sender. When a queue or executor is involved, the sender is decoupled from the processing thread; an error channel mechanism is needed. `errorChannel` is the error path, whereas `replyChannel` is the reply path; configuring one does not replace the other. See [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

In the initial quote configuration, a request with quantity 0 causes the pricing endpoint to throw `IllegalArgumentException`. Since the gateway has no dedicated error flow configured, the caller receives the error; depending on the processing path, the business exception may appear as the cause of a messaging exception.

If you add an error flow that merely logs and terminates, determine how the waiting gateway will be unblocked. Logging an error is not a reply.

When designing error responses, you can choose to:

- Propagate the error back to the caller per the exception contract.
- Transform the error into a result object of a type accepted by the gateway.
- For long-running operations, use a request-acceptance and separate status-lookup contract.

The choice belongs to the service contract, not the bridge.

### 9.2. Symptom Table

| Symptom | Possibilities to check | Diagnostic action |
| --- | --- | --- |
| Final bridge reports missing send destination | No output and missing `replyChannel` | Inspect the message headers immediately before the bridge |
| Gateway times out while data remains in the queue | Poller not running or processing too slow | Check endpoint lifecycle, poller, and queue depth |
| Sending to `DirectChannel` fails | No active subscriber receiving | Check flow beans, wiring, and endpoint state |
| Caller receives the input payload back | Reply bridge placed before the result-producing step | Check the position of the business endpoint |
| Reply type conversion error | Reply type does not match the gateway | Inspect the actual payload at the final bridge |
| Result stolen by another consumer | Multiple consumers on a point-to-point channel | Inspect all endpoints consuming that channel |
| Error log appears but caller keeps waiting | Error flow does not fulfill the reply contract | Inspect the error flow's output and timeouts |
| Repeated processing or looping messages | Bridge output connects back to an earlier path | Redraw edges between channels |

When logging for diagnostics, record the business request ID, endpoint name, and timestamp. Avoid relying solely on the string representation of a temporary channel to correlate calls.

## 10. Testing the Reply Path

The following examples are test code for practicing with JUnit Jupiter. The goal is to verify observable behavior: returning the right result, preserving the reply path, prioritizing explicit output, and failing when no destination exists.

### 10.1. Testing the Gateway End-to-End

Place the test class in the same package as the configuration in Section 4:

~~~java
package example.bridge;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class QuoteFlowTest {

    @Test
    void returnsCalculatedQuoteToCaller() {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             QuoteFlowConfig.class)) {

            QuoteGateway gateway =
                    context.getBean(QuoteGateway.class);

            QuoteReply reply = gateway.quote(
                    new QuoteRequest("BOOK-01", 2));

            assertNotNull(reply);
            assertEquals("BOOK-01", reply.sku());
            assertEquals(2, reply.quantity());
            assertEquals(300_000L, reply.totalVnd());
        }
    }
}
~~~

This test verifies the end-to-end result of both request and reply paths. A test that only checks `send()` succeeded does not prove the caller received the business result.

### 10.2. Unit-Testing Channel Selection Rules

The tests below invoke the handler directly. `QueueChannel` acts as a mailbox so the test can read results; no poller is needed because the test calls `receive()` itself.

~~~java
package example.bridge;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.handler.BridgeHandler;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class BridgeReplyRoutingTest {

    @Test
    void usesReplyHeaderWhenOutputIsAbsent() {
        QueueChannel replies = new QueueChannel(1);
        BridgeHandler bridge = initializedBridge(null);

        Message<String> request = MessageBuilder
                .withPayload("reply-body")
                .setReplyChannel(replies)
                .setHeader("traceId", "trace-001")
                .build();

        bridge.handleMessage(request);

        Message<?> reply = replies.receive(100);
        assertNotNull(reply);
        assertEquals("reply-body", reply.getPayload());
        assertEquals("trace-001",
                reply.getHeaders().get("traceId"));
    }

    @Test
    void explicitOutputTakesPriorityOverReplyHeader() {
        QueueChannel output = new QueueChannel(1);
        QueueChannel replies = new QueueChannel(1);
        BridgeHandler bridge = initializedBridge(output);

        Message<String> request = MessageBuilder
                .withPayload("forward-body")
                .setReplyChannel(replies)
                .build();

        bridge.handleMessage(request);

        Message<?> forwarded = output.receive(100);
        assertNotNull(forwarded);
        assertEquals("forward-body", forwarded.getPayload());
        assertNull(replies.receive(0));
    }

    @Test
    void failsWhenNoOutputAndNoReplyHeaderExist() {
        BridgeHandler bridge = initializedBridge(null);

        Message<String> request = MessageBuilder
                .withPayload("no-destination")
                .build();

        assertThrows(MessagingException.class,
                () -> bridge.handleMessage(request));
    }

    private static BridgeHandler initializedBridge(
            QueueChannel output) {

        BridgeHandler bridge = new BridgeHandler();
        bridge.setBeanFactory(
                new DefaultListableBeanFactory());

        if (output != null) {
            bridge.setOutputChannel(output);
        }

        bridge.afterPropertiesSet();
        return bridge;
    }
}
~~~

The first test has no business endpoint: it intentionally proves that the bridge only forwards the message based on the header. The gateway test in the previous subsection proves that a quote request is calculated into a `QuoteReply`.

### 10.3. Scenarios to Verify When Extending the Flow

| Change in the system | Behavior to prove |
| --- | --- |
| Add multiple concurrent calls | Each request receives its own matching reply |
| Introduce a queue into the processing path | Poller pulls requests and results still return to the right gateway |
| Let a filter reject a request | Caller receives termination matching the contract |
| Add a splitter and aggregator | Gateway receives the aggregated result, never a partial piece |
| Simulate processing longer than timeout | Timeout behavior and late-result handling are deterministic |
| Add an error flow | Errors reach the caller or are converted into a valid result |

For timeout or concurrency tests, use synchronization primitives like latches and finite deadlines. Avoid simply inserting `Thread.sleep()` and treating a passing run as solid proof.

## 11. Application Principles

A request-reply bridge flow needs a clear path from receiving the request to returning the reply:

1. The gateway or sender provides the reply context.
2. The business endpoint produces a contract-compliant result.
3. Intermediate steps preserve the information needed to reply.
4. A bridge with an output forwards to that output.
5. A final bridge without an output uses the existing reply path.
6. Every rejected, failing, or timed-out branch has a defined termination.

When reading a configuration, locate where the result is created first, then trace the channels from that result back to the caller. This reading order helps uncover bridges placed too early, channels missing consumers, and branches that cannot complete the call.
