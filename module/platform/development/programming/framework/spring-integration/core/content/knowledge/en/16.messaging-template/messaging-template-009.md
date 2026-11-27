# MessagingTemplate and DirectChannel

In the **SPRING_INTEGRATION_CORE** module, `MessagingTemplate` is the bridge when Java code proactively calls a message flow. This lesson belongs to the **MessagingTemplate** chapter and focuses on sending messages through `DirectChannel`, receiving replies, understanding the execution flow, and designing error handling.

The running scenario is order-code normalization: the application sends `"  ord-009  "`, and the integration flow returns `"ORD-009"`. This small example makes the roles of `Message`, `MessageChannel`, endpoints, and the Java DSL easy to observe before applying them to larger business flows.

## 1. Objectives and Practice Setup

After this lesson, you will be able to:

- Choose a one-way send or request–reply operation.
- Explain which thread runs the handler when the input is a `DirectChannel`.
- Build a Java DSL flow and invoke it with `MessagingTemplate`.
- Distinguish reply wait duration from business processing duration.
- Diagnose missing subscribers, missing return paths, and misused receive operations.
- Write tests for replies, headers, and synchronous execution behavior.

The examples use Java, Spring Integration Core, and Spring Context; the test section uses JUnit Jupiter. Your project must declare `org.springframework.integration:spring-integration-core` and `org.junit.jupiter:junit-jupiter` for tests, with compatible versions managed by the project's dependency configuration. No broker, HTTP server, or poller is required to run these `DirectChannel` flows.

The two demonstration programs are standalone examples. Each program can be placed in a Java file matching its public class name in a practice project. The Java DSL example uses `AnnotationConfigApplicationContext` to show endpoint registration and startup clearly.

## 2. Two Components with Different Responsibilities

**MessagingTemplate** provides the API for application code to send a `Message`, send a payload via conversion, or send a request and retrieve a reply. It does not replace business endpoints. [MessagingTemplate documentation](https://docs.spring.io/spring-integration/reference/channel/template.html).

**DirectChannel** dispatches messages to a subscriber directly on the send-calling thread. It is a `SubscribableChannel`, not a queue where a receiver calls `receive()`. On a successful dispatch, one handler is selected to handle the message; the channel does not broadcast copies to all subscribers. [DirectChannel Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/DirectChannel.html).

| Component | Responsibility in the Normalization Example |
|---|---|
| `Message<String>` | Carries the input string and request-tracking headers |
| `MessagingTemplate` | Sends the request and manages waiting for the reply |
| `DirectChannel` | Connects the sender to the endpoint on the same thread |
| Transformer endpoint | Trims leading/trailing whitespace and converts to uppercase |
| Reply channel | Delivers the result back to the waiting call |

Conceptual diagram of the flow:

~~~mermaid
flowchart LR
    A["Calling code"] --> B["MessagingTemplate"]
    B --> C["DirectChannel: normalizeInput"]
    C --> D["Transformer endpoint"]
    D --> E["Temporary reply channel"]
    E --> B
    B --> F["Reply Message"]
~~~

`DirectChannel` determines how handoff occurs at that point. To know whether the entire flow is synchronous, you must inspect all downstream channels and endpoints as well.

### 2.1. One Subscriber Does Not Mean Only One Thread Can Send

If two application threads call `send()` concurrently, the handler can be executed simultaneously by both threads. “Runs on the sender's thread” does not mean all requests are serialized.

In the normalization problem, the lambda uses only local data and holds no shared state. If you replace the lambda with a service holding a shared mutable `ArrayList`, that design must be reviewed for thread safety.

### 2.2. Multiple Subscribers Do Not Form a Pipeline

Suppose you register both a data-validation step and an order-saving step on the same `DirectChannel`. That is not how to express “validate then save”.

Under default configuration, `DirectChannel` uses round-robin to pick one handler; failover may try another handler if the selected one throws an exception. Thus a message may be retried across handlers upon failure, yet this is neither a broadcast nor a sequential business pipeline. [Message channel implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

To express mandatory sequential steps, chain them in order inside an `IntegrationFlow`. If using failover across handlers that produce side effects, account for the case where the first handler completed partial work before failing.

## 3. Choosing the Right MessagingTemplate Operation

The import used in this lesson is:

~~~java
import org.springframework.integration.core.MessagingTemplate;
~~~

This is Spring Integration's template, extending `GenericMessagingTemplate` from Spring Messaging. You can pass a default channel via constructor or configure a default destination. [MessagingTemplate Javadoc](https://docs.spring.io/spring-integration/api/org/springframework/integration/core/MessagingTemplate.html).

| Operation | Primary Input | Outcome at the Caller |
|---|---|---|
| `send(channel, message)` | Constructed `Message` | Does not return a reply `Message` |
| `send(message)` | `Message` and default channel | Same as above |
| `convertAndSend(channel, payload)` | Payload | Converts to a `Message` and sends |
| `sendAndReceive(channel, request)` | Request `Message` | Reply `Message` or `null` |
| `convertSendAndReceive(channel, payload, String.class)` | Payload and target type | Reply payload as `String` or `null` |
| `receive(channel)` | Channel supporting polling | `Message` or `null` |

With the template API used here, `send(...)` returns `void`. A `boolean` return value belongs to `MessageChannel.send(...)`. If sending returns `false`, the template raises a delivery exception; there is no `boolean success = template.send(...)`. Check method signatures against your dependency's Javadoc when reading older examples. [Template send API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/AbstractMessageSendingTemplate.html).

The `convert...` methods use a `MessageConverter`. Do not assume calling `convertAndSend` always serializes to JSON; conversion capabilities depend on the configured converter. In the `String` examples below, no JSON converter is needed.

### 3.1. Passing a Channel Directly or Using a Default Channel

These two approaches express the same target destination:

~~~java
DirectChannel input = new DirectChannel();
input.subscribe(message ->
        System.out.println(message.getPayload()));

MessagingTemplate explicit = new MessagingTemplate();
explicit.convertAndSend(input, "ord-009");

MessagingTemplate withDefault = new MessagingTemplate(input);
withDefault.convertAndSend("ord-010");
~~~

This snippet assumes `DirectChannel` and `MessagingTemplate` are imported.

A Spring-managed template can also resolve channel names through its destination resolver mechanism. When using a manually instantiated object, passing the channel instance directly is transparent and avoids relying on bean-name resolution. [MessagingTemplate source](https://raw.githubusercontent.com/spring-projects/spring-integration/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/core/MessagingTemplate.java).

Do not mutate the default channel of a shared template per request. If two requests need different destinations, pass the channel in each call.

## 4. One-Way Send Example: Observing Same-Thread Execution

The following program registers a `MessageHandler` directly. The handler only prints information and produces no reply.

~~~java
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class DirectSendDemo {

    public static void main(String[] args) {
        DirectChannel input = new DirectChannel();

        input.subscribe(message -> {
            System.out.println("handler thread = "
                    + Thread.currentThread().getName());
            System.out.println("payload = " + message.getPayload());
            System.out.println("requestId = "
                    + message.getHeaders().get("requestId"));
        });

        MessagingTemplate template = new MessagingTemplate(input);

        Message<String> request = MessageBuilder
                .withPayload("ord-009")
                .setHeader("requestId", "req-009")
                .build();

        System.out.println("before send, thread = "
                + Thread.currentThread().getName());

        template.send(request);

        System.out.println("after send");
    }
}
~~~

When run from a standard `main`, the expected output order is:

~~~text
before send, thread = main
handler thread = main
payload = ord-009
requestId = req-009
after send
~~~

You can set a breakpoint inside the handler and inspect the call stack from `main` to `template.send(...)`, into the channel, and into the handler.

Three takeaways from this example:

1. The handler finished running before the `after send` line executed.
2. One-way send only means the caller does not ask to receive a reply `Message`.
3. If the handler is slow, the caller waits inside the send call as well.

Do not generalize “all work is finished” to flows that hand off to a downstream executor or queue. In those cases, the sender's call stack can unwind before asynchronous work finishes.

## 5. Request–Reply Example with Java DSL

In this example, the application needs the normalized code back. We use a transformer endpoint that produces output instead of the logging-only `MessageHandler` from the previous section.

The Java DSL describes flow components and registers them in the Spring context via an `IntegrationFlow` bean. Merely constructing a builder in a local variable does not replace endpoint registration. [Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html).

~~~java
import java.util.Locale;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class NormalizeFlowDemo {

    @Configuration
    @EnableIntegration
    public static class FlowConfig {

        @Bean
        public DirectChannel normalizeInput() {
            return new DirectChannel();
        }

        @Bean
        public IntegrationFlow normalizeFlow(
                @Qualifier("normalizeInput") DirectChannel input) {

            return IntegrationFlow.from(input)
                    .transform(String.class,
                            value -> value.trim()
                                    .toUpperCase(Locale.ROOT))
                    .get();
        }

        @Bean
        public MessagingTemplate normalizeTemplate(
                @Qualifier("normalizeInput") DirectChannel input) {

            MessagingTemplate template = new MessagingTemplate(input);
            template.setSendTimeout(1_000);
            template.setReceiveTimeout(1_000);
            return template;
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(FlowConfig.class)) {

            MessagingTemplate template = context.getBean(
                    "normalizeTemplate", MessagingTemplate.class);

            Message<String> request = MessageBuilder
                    .withPayload("  ord-009  ")
                    .setHeader("requestId", "req-009")
                    .build();

            Message<?> reply = template.sendAndReceive(request);

            if (reply == null) {
                throw new IllegalStateException(
                        "No normalization result received");
            }

            System.out.println("normalized = " + reply.getPayload());
            System.out.println("requestId = "
                    + reply.getHeaders().get("requestId"));

            String second = template.convertSendAndReceive(
                    "  si-core  ", String.class);

            if (second == null) {
                throw new IllegalStateException(
                        "No second reply received");
            }

            System.out.println("second = " + second);
        }
    }
}
~~~

Ignoring Spring startup logs, the expected business output is:

~~~text
normalized = ORD-009
requestId = req-009
second = SI-CORE
~~~

The `transform(String.class, ...)` overload specifies the data type the lambda accepts. The lambda only performs the transformation; the transformer endpoint handles constructing and forwarding the output `Message`. [Transformer API in Java DSL](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html).

The example uses `Locale.ROOT` so uppercasing rules do not depend on the host machine's default locale. The business rule here is strictly trimming whitespace and uppercasing; order-code format validation is not included.

### 5.1. Why Is No Reply QueueChannel Declared?

The template creates a temporary reply channel per exchange and puts the reply address into the request `Message`. The flow-end endpoint can send the result to that address.

For output-producing endpoints, an explicitly configured output channel takes precedence over the `replyChannel` header address. When no output channel is set, the endpoint can use `replyChannel` to return the result. [Endpoint reply-sending rules](https://docs.spring.io/spring-integration/reference/service-activator.html).

In the example, the transformer is the final endpoint and has no separate output channel, so the result returns to the template. Do not add a `QueueChannel` to hold results and expect the template to find it automatically.

If you decide to route output to another channel, the design must guarantee a path forwarding results back to the caller. Merely putting the result into a queue does not fulfill the request–reply contract.

### 5.2. Sequence of a Synchronous Call

~~~mermaid
sequenceDiagram
    participant App as Application code
    participant T as MessagingTemplate
    participant C as DirectChannel
    participant E as Transformer endpoint
    participant R as Temporary reply channel

    App->>T: sendAndReceive(request)
    T->>T: Prepare reply address
    T->>C: send(request with replyChannel)
    C->>E: handleMessage(request), same thread
    E->>E: trim and uppercase
    E->>R: Send result Message
    E-->>C: Handler completes
    C-->>T: Send completes
    T->>R: Receive reply
    R-->>T: Result Message
    T-->>App: reply
~~~

Participants represent components, not separate threads. In this flow, the reply is already sent into the temporary channel before the template begins its receive step.

An application-set `requestId` helps correlate requests with logs and replies. It does not replace preserving the exchange's `replyChannel` address. When constructing a new `Message` manually mid-flow, check which headers must be carried forward.

### 5.3. A Plain MessageHandler Does Not Produce Replies Automatically

The contract of `MessageHandler` is `handleMessage(Message<?> message)` returning `void`. Computing a string in a local variable inside a handler does not turn that string into a reply.

To transform data, use a transformer as shown. To call a business service with a return value, use a service activator endpoint, such as `.handle(service, "methodName")`. That endpoint is responsible for turning the method's return value into output; it differs from merely calling `subscribe` with a logging lambda.

## 6. What Do Timeouts Bound?

`setSendTimeout(...)` and `setReceiveTimeout(...)` use milliseconds. The API also supports per-`Message` timeouts via the corresponding headers. [Timeout configuration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/GenericMessagingTemplate.html).

| Setting | Question to Ask When Reading a Flow |
|---|---|
| `sendTimeout` | Does the target channel have a wait operation when accepting messages? |
| `receiveTimeout` | After the send step, how long should it wait to pull the reply? |

### 6.1. DirectChannel Provides No Handler Deadline

In `GenericMessagingTemplate`'s implementation, the send step runs before the reply-receiving step. Therefore `receiveTimeout` does not interrupt a synchronous handler executing inside the send step. [Exchange source code](https://raw.githubusercontent.com/spring-projects/spring-framework/6.2.x/spring-messaging/src/main/java/org/springframework/messaging/core/GenericMessagingTemplate.java).

Reasoning example: replace the transformer with an external-system call taking three seconds, set `receiveTimeout = 100` ms, and have that system succeed. As long as the whole path stays synchronous, the caller may wait roughly three seconds and then receive the result; you cannot expect the template to exit after 100 ms.

Likewise, `sendTimeout` does not turn a handler invocation on `DirectChannel` into a task with deadline cancellation. If the service makes HTTP or database calls, configure appropriate timeouts on that client or resource.

In the code-normalization scenario, computation is tiny. When replacing it with I/O processing, re-evaluate thread occupancy and caller resource limits.

### 6.2. Handler Finishes Without a Reply

If you replace the transformer with a `void` handler, the send call can finish yet the receive step has no `Message` to return. With a finite receive timeout, `sendAndReceive` can return `null`. The caller must handle that branch before accessing the payload.

Minimal example where the channel has a subscriber, yet the subscriber sends no reply:

~~~java
DirectChannel input = new DirectChannel();
input.subscribe(message -> {
    // Consume the message only; do not produce a reply.
});

MessagingTemplate template = new MessagingTemplate(input);
template.setReceiveTimeout(0);

Message<?> reply = template.sendAndReceive(
        MessageBuilder.withPayload("ord-009").build());

// reply is null: handler ran yet produced no reply.
~~~

The imports match earlier examples. A value of `0` asks the receive step to check immediately, useful for demonstrating a missing reply without adding wait time.

In business design, define explicitly what `null` represents. If “no order found” is a valid outcome, return an explicit result structure to distinguish it from “no reply from the flow”.

### 6.3. Switching to Async Does Not Cancel Work on Timeout

Suppose a step behind the input channel hands requests off to an executor. The template can wait for a reply while the worker processes. If the caller times out, the worker can keep running and cause side effects.

For a payment command, automatically resending just because no reply arrived can create duplicate charges. When extending the example to side-effecting operations, stable `requestId` values, duplicate checks, and retry policies must accompany the reply contract.

## 7. Why Is receive(DirectChannel) Incorrect?

`receive(...)` pulls a message from a destination supporting polling; it does not register a new subscriber. `DirectChannel` only dispatches to existing subscribers. Thus it can serve as the request channel for `sendAndReceive`, not as a reply queue.

`receive` can return `null` when no message is available, and `receiveAndConvert` variants extract the payload as a target type. [Message receiving contract](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/core/MessageReceivingOperations.html).

Distinguish two questions:

- `sendAndReceive(input, request)`: send to `input`, then get the reply via the template's exchange mechanism.
- `receive(input)`: request to pull a waiting message directly from `input` itself.

Having a common `MessageChannel` parameter type does not guarantee every channel implementation supports every operation. When a receiver needs to actively pull buffered messages, consider `QueueChannel` and a corresponding consumption mechanism.

## 8. How Do Synchronous Errors Return to the Caller?

In a flow running on the caller's thread over `DirectChannel`, unhandled endpoint errors unwind up the call stack. You cannot simply add an `errorChannel` header and assume the template will swallow the error and emit an `ErrorMessage`. Asynchronous error mechanisms must be evaluated at the corresponding execution boundary. [Error Handling in Spring Integration](https://docs.spring.io/spring-integration/reference/error-handling.html).

At the call site, you can handle messaging errors:

~~~java
try {
    Message<?> reply = template.sendAndReceive(request);

    if (reply == null) {
        throw new IllegalStateException(
                "Flow returned no result for req-009");
    }

    // Use reply.getPayload() only after checking for null.
}
catch (org.springframework.messaging.MessagingException ex) {
    // Log requestId and cause chain per application policy.
    // Let the calling layer decide how to return the error; do not turn failures into success.
    throw ex;
}
~~~

This snippet illustrates placing handling inside a method that already has `template` and `request`. Business exceptions can be wrapped inside a messaging exception as they cross endpoints; inspect the cause chain instead of looking solely for one business exception class at the top level.

| Symptom | What to Check First |
|---|---|
| Error about no subscriber immediately on send | Has the context started; is the endpoint subscribed to the right channel? |
| Handler ran yet caller received `null` | Does the handler produce output and have a return path? |
| Result sits in another queue while caller waits | Is there forwarding from that queue back to the reply address? |
| Calling `receive(input)` fails | Is `input` a `PollableChannel`? |
| Call duration exceeds `receiveTimeout` | Is slow synchronous work running inside the send step? |
| Two business steps do not both run | Were both registered as competing subscribers on the same `DirectChannel`? |

This table is a triage sequence for the lesson's examples, not a substitute for reading the stack trace and actual configuration.

## 9. Transactions and Threads Must Be Read Together

`DirectChannel` keeps handler invocation on the sender's thread, enabling operations using compatible resources to participate in an active transaction. The channel does not start a transaction on its own simply because it is named `DirectChannel`.

An application-initiated flow transaction remains governed by standard Spring transaction configuration. Thread-handoff boundaries require re-evaluation because thread-bound transactions do not automatically propagate to a new worker thread. [Transactions in message flows](https://docs.spring.io/spring-integration/reference/transactions.html).

Design example: a service with an active transaction calls the template to validate and persist data across synchronous steps. If one step fails, rollback outcomes still depend on the transaction manager, propagation, participating resources, and rollback rules.

If the final step calls an external shipping service, do not assume a database rollback also undoes the request already sent to that external service. Separate side effects from business compensation mechanisms.

## 10. Testing Key Contracts

The tests below use JUnit Jupiter. Place them in the same package as `NormalizeFlowDemo` from section 5. Neither Spring Boot nor a broker is needed for these cases.

~~~java
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MessagingTemplateDirectChannelTest {

    @Test
    void handlerRunsOnCallingThread() {
        DirectChannel input = new DirectChannel();
        AtomicReference<Thread> observed = new AtomicReference<>();
        input.subscribe(message ->
                observed.set(Thread.currentThread()));

        MessagingTemplate template = new MessagingTemplate(input);
        Thread caller = Thread.currentThread();

        template.send(MessageBuilder.withPayload("ord-009").build());

        assertSame(caller, observed.get());
    }

    @Test
    void dslFlowReturnsNormalizedPayloadAndRequestId() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             NormalizeFlowDemo.FlowConfig.class)) {

            MessagingTemplate template = context.getBean(
                    "normalizeTemplate", MessagingTemplate.class);

            Message<?> reply = template.sendAndReceive(
                    MessageBuilder.withPayload("  ord-009  ")
                            .setHeader("requestId", "req-009")
                            .build());

            assertNotNull(reply);
            assertEquals("ORD-009", reply.getPayload());
            assertEquals("req-009",
                    reply.getHeaders().get("requestId"));
        }
    }

    @Test
    void oneWayHandlerDoesNotProduceReply() {
        DirectChannel input = new DirectChannel();
        input.subscribe(message -> {
            // No output.
        });

        MessagingTemplate template = new MessagingTemplate(input);
        template.setReceiveTimeout(0);

        Message<?> reply = template.sendAndReceive(
                MessageBuilder.withPayload("ord-009").build());

        assertNull(reply);
    }

    @Test
    void channelWithoutSubscriberFailsToDeliver() {
        DirectChannel input = new DirectChannel();
        MessagingTemplate template = new MessagingTemplate(input);

        assertThrows(MessagingException.class,
                () -> template.send(
                        MessageBuilder.withPayload("ord-009").build()));
    }
}
~~~

The four test cases isolate four contracts: execution thread, reply value with headers, no-reply behavior, and delivery failure when no subscriber exists. Using the general messaging exception in the final case verifies the failure contract without coupling to exact log wording across versions.

Do not use `Thread.sleep(...)` to wait for endpoints in these synchronous cases. If an asynchronous boundary is introduced later, replace test synchronization with a completion condition and appropriate wait bound.

These code snippets are practice examples to run in a learner's project; this article does not claim they were compiled or run in a specific environment.

## 11. Choosing MessagingTemplate or a Gateway?

If an infrastructure layer needs to build a `Message`, attach headers, and pick channels itself, `MessagingTemplate` expresses those decisions directly.

If a business service only needs a contract such as `String normalize(String rawCode)`, a messaging gateway can hide `Message` and channel APIs behind an interface. [Messaging gateways](https://docs.spring.io/spring-integration/reference/gateway.html).

| Need at the Call Site | Design Direction |
|---|---|
| Build a `Message` and control exchange headers | `MessagingTemplate` |
| Business API as a strongly typed method | Messaging gateway |
| Short sequential steps on the caller thread | `DirectChannel` in the flow |
| Buffer bursts for later processing | Consider `QueueChannel` and a corresponding consumer |
| Offload work from the caller thread | Consider an executor boundary and error/reply contracts |

Choosing a template or gateway does not by itself decide whether a flow is synchronous or asynchronous. That decision also lives in the flow's channels and components.

## 12. Extended Practice

Using the normalization flow as a starting point, work through these steps in order:

1. Add a transformer checking for blank codes after `trim()`. Define explicitly whether invalid input returns a rejection result or throws an error; never leave the caller mistaking it for a lost reply.
2. Log `requestId` at entry and exit. Send two requests with distinct IDs and match each result to the right request.
3. Replace the final endpoint with a logging-only handler. Observe `null` under a finite receive timeout and update the call site to match a one-way contract.
4. Register two handlers printing different names on a standalone `DirectChannel` and send multiple messages. Observe dispatch behavior, then rewrite as an `IntegrationFlow` when both steps must run sequentially.
5. Design on paper replacing a normalization step with an HTTP call. Point out where to put the I/O timeout, where threads might switch, and how to avoid duplicate side effects when the caller retries.

Completion criterion: for every call, you can identify which channel the `Message` enters, which endpoint processes it, which thread executes it, which path returns the result, and what happens if no reply arrives.