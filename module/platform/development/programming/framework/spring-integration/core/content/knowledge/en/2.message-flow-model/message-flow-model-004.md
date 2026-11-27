# Request-reply flow

In the **Message flow model** chapter of the **SPRING_INTEGRATION_CORE** module, request-reply is a pattern where a caller sends a request message and receives a corresponding response. A Java call such as `quoteGateway.quote(request)` can pass through multiple channels and endpoints before returning a quote object.

This lesson connects `Message`, `MessageChannel`, endpoints, messaging gateways, and Java DSL to explain that path. The examples use an in-memory quote-calculation service, then expand to cross-thread processing, errors, and testing. The goal is to read a flow and answer four questions: **who sends the request, who creates the reply, where does the reply go, and how does the caller stop waiting?**

## 1. Contract of a request-reply flow

Suppose an order screen needs to calculate the price for three books. The caller sends a SKU and quantity, while the flow returns the normalized SKU along with the total amount:

~~~text
QuoteRequest(" java-book ", 3)
              |
              v
     Normalize -> Calculate price
              |
              v
QuoteReply("JAVA-BOOK", 360000)
~~~

From a business perspective, this call requires a result for each valid request. Technically, there are three termination outcomes to design explicitly:

| Termination outcome | Meaning for the caller | Example |
| --- | --- | --- |
| Valid reply received | Receives a result matching the contract | A `QuoteReply` containing the total amount |
| Error propagated back | Operation did not complete normally | Unknown SKU, pricing service failure |
| Wait timed out | No result received within the configured wait duration | Slow worker or a branch that emits no reply |

A timeout does not prove the request was not processed. An operation may finish on a worker after the caller has stopped waiting. For operations with side effects such as charging payment or reserving inventory, this directly affects retry decisions.

Request-reply describes the relationship between a request and a response. It does not require HTTP, a broker, a queue, or a separate thread. In this lesson, the entire baseline example runs inside a single JVM.

### Distinguishing from one-way send

With a one-way send, the caller does not require a business result from the flow. A gateway method returning `void` can express that contract. However, `void` does not automatically make execution asynchronous: if the channel invokes the handler directly, the caller still executes the handler on the current thread.

Conversely, a gateway returning `QuoteReply` expresses that the caller expects a result. Do not wire such a gateway to a flow that merely logs and terminates without a reply policy.

## 2. How does a request enter and the reply return?

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant G as Messaging gateway
    participant I as Request channel
    participant T as Transformer
    participant S as Service activator
    participant R as Temporary reply channel

    C->>G: quote(request)
    G->>I: Message<QuoteRequest> + replyChannel
    I->>T: Forward request
    T->>S: Normalized request
    S->>R: Message<QuoteReply>
    R-->>G: Reply for this call
    G-->>C: QuoteReply
~~~

The gateway converts a method invocation into a message. In typical usage, the gateway creates a temporary reply channel for the exchange and puts that address in the `replyChannel` header. Therefore, the basic flow does not need to declare a separate reply channel bean. This implements the **Return Address** pattern: the request carries the address to send the result back to. [Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html)

The diagram shows the logical path, not a guarantee of multiple threads. If all channels in the flow are `DirectChannel`, endpoint invocations run on the caller's thread.

One distinction to keep clear: `requestChannel.send(message)` is only a send operation. The boolean value returned by `send` is not the reply payload. Sending and then receiving a result requires a gateway, `MessagingTemplate`, or an application-managed reply reception mechanism.

## 3. Payload, return address, and correlation

A request in the example can be pictured as follows:

~~~text
Message<QuoteRequest>
  payload:
    sku: " java-book "
    quantity: 3
  headers:
    id: message UUID
    replyChannel: result destination address
    requestId: "REQ-2026-001"       # custom business header
~~~

Different headers play different roles:

| Header | Question it answers | Usage in this lesson |
| --- | --- | --- |
| `id` | Which message instance is this? | Identifies a message during diagnostics |
| `replyChannel` | Where should the result be sent back? | Return path to the caller |
| `errorChannel` | Where should an error message be sent when error handling applies? | Failure path |
| `correlationId` | Which group/exchange does this message belong to under current conventions? | Useful when correlating groups or exchanges across transports |
| `requestId` | Which business request is this? | Application-defined identifier for tracking |

`replyChannel` can hold a channel object or a channel name that the framework can resolve. Do not assume it is always a string ready to cross a network boundary. Payloads and custom header values are also not deeply immutable by default, even though the `MessageHeaders` map cannot be modified directly. [Message](https://docs.spring.io/spring-integration/reference/message.html)

In this example, `requestId` is an application convention, not a special header that automatically triggers reply matching. Likewise, merely adding `correlationId` to two messages does not make a `QueueChannel` automatically route the right response to each caller.

## 4. How does an endpoint decide where to send a reply?

For a standard service activator in this lesson without a configured routing slip, the reply path follows this order:

1. If the endpoint has a configured output channel, the result goes to that output channel.
2. If there is no output channel, the endpoint uses `replyChannel` from the request.
3. If the request lacks that address and the returned value is a `Message`, the framework can use `replyChannel` on the returned message.
4. If the endpoint produced a result but cannot resolve a destination, the flow fails when resolving where to send the reply.

This rule explains why the final handler in a flow only needs to return a POJO: the framework builds a result message and sends it to the appropriate destination. When the handler returns `null` or `void`, there is no reply payload to forward; `requiresReply(true)` turns missing results into an error at a reply-requiring endpoint. [Service Activator](https://docs.spring.io/spring-integration/reference/service-activator.html)

A configuration example that easily causes misunderstanding:

~~~text
Gateway -> Calculate price -> auditQueue
                                 |
                                 v
                            Log only
~~~

The pricing endpoint sent its output to `auditQueue`. If the queue's consumer simply logs and terminates, the caller never receives a quote. When message observation is needed, design a separate observation branch and keep the reply-producing path returning to the gateway. Nor should the observation branch accidentally emit an extra business reply.

## 5. Complete example: gateway and Java DSL for quote calculation

### 5.1. Prerequisites for using the example

The classes below use Java 17 and the Spring Integration 6.x Java DSL API. Each block shows its corresponding filename; place the files in the same `example.requestreply` package in a practice project.

Required classpath:

| Purpose | Dependency |
| --- | --- |
| Message channels, endpoints, gateways, and Java DSL | `org.springframework.integration:spring-integration-core` |
| Java context initialization | `org.springframework:spring-context` |
| Test examples in the later section | `org.springframework:spring-test` and `org.junit.jupiter:junit-jupiter` |

Use compatible Spring versions managed by the project's BOM or dependency management. In a Spring Boot project, `spring-boot-starter-integration` and `spring-boot-starter-test` can provide the corresponding artifacts. The main code below initializes the context directly to show the minimal configuration clearly.

### 5.2. Request and reply objects

**QuoteRequest.java**

~~~java
package example.requestreply;

public record QuoteRequest(String sku, int quantity) {
}
~~~

**QuoteReply.java**

~~~java
package example.requestreply;

import java.math.BigDecimal;

public record QuoteReply(String sku, BigDecimal total) {
}
~~~

Request and reply are two distinct data types. Separating them tells callers exactly what input to supply and what output to expect, instead of using a `Map` with unclear key contracts.

### 5.3. Business logic

**QuoteService.java**

~~~java
package example.requestreply;

import java.math.BigDecimal;

public class QuoteService {

    public QuoteReply quote(QuoteRequest request) {
        if (request.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        BigDecimal unitPrice = switch (request.sku()) {
            case "JAVA-BOOK" -> new BigDecimal("120000");
            case "SI-BOOK" -> new BigDecimal("180000");
            default -> throw new IllegalArgumentException(
                    "Unknown SKU: " + request.sku());
        };

        BigDecimal total = unitPrice.multiply(
                BigDecimal.valueOf(request.quantity()));

        return new QuoteReply(request.sku(), total);
    }
}
~~~

The service is a POJO that accepts a request and returns a reply. It does not need to know which channel carried the request. In this example, an unknown SKU is an error propagated to the caller; if the product requires returning a business status such as `NOT_FOUND`, expand the reply type and define clearly which fields hold values for each status.

### 5.4. Gateway interface

**QuoteGateway.java**

~~~java
package example.requestreply;

import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "quoteRequests")
public interface QuoteGateway {

    @Gateway(requestTimeout = 500, replyTimeout = 1500)
    QuoteReply quote(QuoteRequest request);
}
~~~

Both timeout values are in milliseconds. They are specified explicitly so the example does not depend on defaults. `@Gateway` allows method-level configuration; `requestTimeout` applies to sends that may block, while `replyTimeout` applies to waiting for a response. [Gateway API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/annotation/Gateway.html)

### 5.5. Flow configuration

**QuoteFlowConfig.java**

~~~java
package example.requestreply;

import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.config.IntegrationComponentScan;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
@IntegrationComponentScan(basePackageClasses = QuoteGateway.class)
public class QuoteFlowConfig {

    @Bean
    public MessageChannel quoteRequests() {
        return new DirectChannel();
    }

    @Bean
    public QuoteService quoteService() {
        return new QuoteService();
    }

    @Bean
    public IntegrationFlow quoteFlow(QuoteService quoteService) {
        return IntegrationFlow.from("quoteRequests")
                .<QuoteRequest, QuoteRequest>transform(request ->
                        new QuoteRequest(
                                request.sku() == null
                                        ? ""
                                        : request.sku().trim()
                                                .toUpperCase(Locale.ROOT),
                                request.quantity()))
                .handle(quoteService, "quote",
                        endpoint -> endpoint.requiresReply(true))
                .get();
    }
}
~~~

`@IntegrationComponentScan` scans for interfaces annotated with `@MessagingGateway` and registers the corresponding proxies. Standard component scanning alone is not enough to discover gateway interfaces under this mechanism. [MessagingGateway API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/annotation/MessagingGateway.html)

In the flow, the transformer receives a `QuoteRequest`, creates a new request with a normalized SKU, and then the service activator invokes `QuoteService.quote`. Java DSL uses `.handle(...)` to wire POJO or handler processing into the flow. [Service Activators and the .handle() method](https://docs.spring.io/spring-integration/reference/dsl/java-handle.html)

`requiresReply(true)` is configured on the pricing endpoint. It expresses the requirement: if the method is invoked normally, it must produce a result. It is not a mechanism that monitors every branch across the entire flow. [GenericEndpointSpec API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/dsl/GenericEndpointSpec.html)

There is no `.channel("someReplies")` at the end of the flow. The pricing result uses the request's return address to return to the gateway.

### 5.6. Sample execution

**RequestReplyDemo.java**

~~~java
package example.requestreply;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class RequestReplyDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(QuoteFlowConfig.class)) {

            QuoteGateway gateway = context.getBean(QuoteGateway.class);

            QuoteReply reply = gateway.quote(
                    new QuoteRequest(" java-book ", 3));

            if (reply == null) {
                throw new IllegalStateException("No quote reply received");
            }

            System.out.println(reply.sku());
            System.out.println(reply.total());
        }
    }
}
~~~

Expected output:

~~~text
JAVA-BOOK
360000
~~~

With the input above, the execution sequence is:

1. Caller invokes the `QuoteGateway` proxy.
2. Gateway creates a request message and a return address.
3. `quoteRequests` delivers the request to the transformer.
4. Transformer turns `" java-book "` into `"JAVA-BOOK"`.
5. Service activator invokes the POJO, calculating `120000 × 3`.
6. Message containing `QuoteReply` goes to the reply channel.
7. Proxy extracts the payload and returns `QuoteReply` to the caller.

If invoked with `quantity = 0`, the service throws an exception instead of producing a quote. If a programming bug causes the service to return `null`, the endpoint configured with `requiresReply` reports the missing result.

## 6. Using MessagingTemplate when direct Message access is needed

A gateway fits well when the calling layer wants to work through a business interface. When you need to inspect headers or send a hand-built `Message`, you can use `MessagingTemplate.sendAndReceive`. This API returns the reply message, allowing the caller to read both payload and headers. [MessagingTemplate API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/core/MessagingTemplate.html)

The example below is a method that can be added to the demo class; the `context` passed in is the context initialized earlier:

~~~java
public static void callWithMessage(
        org.springframework.context.ApplicationContext context) {

    var requests = context.getBean(
            "quoteRequests", org.springframework.messaging.MessageChannel.class);

    var template =
            new org.springframework.integration.core.MessagingTemplate();
    template.setSendTimeout(500);
    template.setReceiveTimeout(1500);

    org.springframework.messaging.Message<QuoteRequest> request =
            org.springframework.messaging.support.MessageBuilder
                    .withPayload(new QuoteRequest(" si-book ", 2))
                    .setHeader("requestId", "REQ-2026-001")
                    .build();

    org.springframework.messaging.Message<?> reply =
            template.sendAndReceive(requests, request);

    if (reply == null) {
        throw new IllegalStateException("No reply for REQ-2026-001");
    }

    QuoteReply payload = (QuoteReply) reply.getPayload();
    System.out.println(payload.total()); // 360000
    System.out.println(reply.getHeaders().get("requestId"));
}
~~~

The example uses the request channel instance retrieved from the context directly, rather than resolving the channel by name through the template. The template manages sending and waiting for the reply for this exchange.

Do not replace `sendAndReceive` with `send` and expect a `QuoteReply` back. Nor should you treat the boolean return value of `send` as proof that the service succeeded.

## 7. Threads and timeouts: two concerns to read separately

### 7.1. DirectChannel keeps execution on the caller's thread

In the baseline configuration, `DirectChannel` invokes a single subscriber on the sending thread. Choosing this channel fits a small example because the path is easy to trace. It also means a slow I/O call inside the service can hold the caller's thread for a long time. [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

Suppose another version of `QuoteService` calls a vendor and that call takes 5 seconds:

~~~text
Caller thread:
  gateway.quote(...)
    -> DirectChannel.send(...)
      -> service.quote(...)       takes 5 seconds
    <- send finishes
    -> gateway receives reply
  <- method returns
~~~

Do not infer that `replyTimeout = 1500` will abort `service.quote(...)` at 1.5 seconds. The gateway's reply wait timer begins once the thread returns to the gateway after sending, not as a timer that interrupts the entire call stack from the instant the request is sent. [Gateway API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/annotation/Gateway.html)

Therefore, timeouts for HTTP clients, JDBC, or downstream resources must be configured at the resource-access layer itself. Timeout settings on the gateway do not replace those limits.

### 7.2. Request timeout and reply timeout address two phases

| Setting | Phase being bounded | Should not be interpreted as |
| --- | --- | --- |
| `requestTimeout` | Waiting to send the request into a channel whose send operation can block | Maximum execution budget of the service |
| `replyTimeout` | Waiting for a reply after the send phase | Automatic worker cancellation or business rollback |
| Downstream client timeout | Waiting to connect, read, or execute via that client's API | Proof that the remote operation never occurred |

An easy scenario to visualize for request timeout is a bounded `QueueChannel` that is full. With a timed send, the sender waits until space opens up or the timeout expires. A non-full queue only confirms the message entered the buffer, not that the pricing result already exists. [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

In the example configured with `500` and `1500` milliseconds, do not write an operational requirement claiming "every call is guaranteed to finish within 2 seconds." Synchronous phases prior to waiting for the reply and other downstream mechanisms still count toward the overall call budget.

### 7.3. After a timeout, business decisions remain

For a read-only pricing API, the caller may choose to retry according to load policies. For an order-creation API, retries must include a request identifier capable of detecting duplicate processing.

A complete policy should specify:

- What the caller does when the outcome is still unknown.
- Which business identifier can be used to query status.
- How late-arriving results are observed or handled.
- Under what conditions retrying an operation with side effects is safe.

These are application decisions; merely setting `replyTimeout` does not establish any of these rules.

## 8. Offloading work to a worker while keeping request-reply

You can replace the existing `quoteRequests` bean with an `ExecutorChannel` backed by a Spring-managed executor. The transformer and service activator need no changes.

**Replacement/additional beans in QuoteFlowConfig:**

~~~java
@Bean
public org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor
        quoteExecutor() {

    var executor =
            new org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(20);
    executor.setThreadNamePrefix("quote-worker-");
    return executor;
}

@Bean
public MessageChannel quoteRequests(
        org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor
                quoteExecutor) {

    return new org.springframework.integration.channel.ExecutorChannel(
            quoteExecutor);
}
~~~

Replace the old channel bean; do not keep two beans both named `quoteRequests`. Because the executor is a Spring bean, the container manages its initialization and lifecycle.

The typical execution path is now:

~~~text
Caller thread: create request -> hand off to executor -> wait for reply
Worker thread:                          normalize -> calculate price -> send reply
Caller thread:                                                          receive result
~~~

Because the caller still uses a method returning `QuoteReply`, it still waits for the result. Having a worker thread does not turn that contract into a one-way send.

`ExecutorChannel` dispatches work via an executor; executor policies can affect which thread executes the work. Nor should you assume a transaction on the caller's thread automatically spans processing on the worker. [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

If replaced with a `QueueChannel`, a consumer must be designed for the pollable channel, typically an endpoint with a poller. Switching a channel to a queue without an active consumer simply leaves requests sitting idle. Additionally, an in-memory queue does not provide durability across restarts on its own.

When the caller needs a handle to await the result later, you can explore gateways with `Future` or `CompletableFuture`. Distinguish two decisions: **the flow uses workers for execution** vs. **the caller's API returns results asynchronously**.

## 9. Should two concurrent requests share one reply queue?

Suppose there are two requests:

~~~text
Request A: JAVA-BOOK, quantity = 1
Request B: SI-BOOK,   quantity = 2
~~~

If B finishes before A, completion order differs from submission order. With a custom shared reply queue where both callers call `receive()`, the caller waiting for A might accidentally pull B's result if there is no correlation mechanism.

The design must solve all three concerns:

1. Attach a correlation identifier to the request.
2. Propagate that identifier into the reply by contract.
3. Provide a dispatcher or registry that delivers each reply to the matching waiting invocation.

In the basic in-process flow above, let the gateway manage the return address per exchange instead of building a shared queue yourself. The `defaultReplyChannel` bean name is a gateway configuration option; do not assume it behaves like a queue from which every caller blindly pulls the first element.

When requests cross HTTP, JMS, or another broker, transport adapters/gateways must translate addresses and metadata according to the protocol. Do not send an internal channel object over the network expecting another JVM to use it. In those cases, consult the request-reply contract of the specific transport in use.

## 10. How do transformers, filters, routers, and aggregators affect replies?

The goal of request-reply is not merely "having a final endpoint return data." Every branch that can terminate processing must make sense to the caller.

| Flow component | Scenario to watch for | Design decision for the quote flow |
| --- | --- | --- |
| Transformer | Builds a custom message and drops metadata needed for return path | Preserve required headers; use plain payload transformations when appropriate |
| Filter | Rejects a request without producing a result | Choose to throw a rejection exception or provide a branch producing a business reply |
| Router | A request type routes to a branch that emits no reply | Define processing branches and outcomes explicitly for every type |
| Splitter + aggregator | One request spawns multiple messages but the group never meets release conditions | Define correlation, release, and incomplete-group handling |
| Final handler | Only writes data/logs and returns `void` | Use a one-way send or add an outcome matching the contract |

### Filter is not synonymous with a "rejected" reply

A filter can drop a message. To turn rejection into an error for the caller, configure `throwExceptionOnRejection(true)`. To return a business result such as "not eligible," the discard branch must have an endpoint that produces that result. Configuring a discard channel alone does not guarantee a reply is returned. [Filter](https://docs.spring.io/spring-integration/reference/filter.html)

Example design-level decision:

~~~text
Quote request
  -> Check permission
       -> Allowed: calculate price -> QuoteReply
       -> Denied: create QuoteDecision(REJECTED, reason)
~~~

If you choose this design, the gateway must return a data type able to hold both outcomes, such as `QuoteDecision`. You cannot keep the signature `QuoteReply quote(...)` and arbitrarily return an incompatible error type.

### Routers must be read path by path

For a router separating standard customers and priority customers, trace both branches all the way to where a reply is produced. Mapping, resolution, and default-output settings depend on router type; consult the documentation for the exact router rather than assuming all unmatched cases behave identically. [Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html)

### Aggregators have a group wait window

An aggregator holds related messages and releases a result once release conditions are met. It has a correlation strategy and a release strategy; thus "one branch finished processing" does not yet mean "there is a reply for the original request." [Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html)

If an aggregated quote needs results from three sources and only two respond, you must decide whether to return a partial result, return an error, or keep waiting up to the group's expiry window. That budget must align with how long the caller is willing to wait.

## 11. Errors are a termination path that must be designed

Distinguish clearly:

- **Processing error:** an endpoint throws an exception.
- **Missing result:** no reply is produced or it never reaches the waiting party.
- **Wait expired:** the caller stops waiting per configuration.
- **Negative business outcome:** a valid reply is returned, such as `REJECTED`.

In a flow running on the same thread, exceptions can propagate along the call stack. With cross-thread execution, the worker's call stack cannot throw directly into the caller; the framework uses error messaging where appropriate. When asynchronous error publishing applies, the request's `errorChannel` header takes precedence, followed by the global error channel. Do not infer that every exception in a synchronous flow is automatically sent to the `errorChannel` bean. [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)

In the current example, no error flow is configured to transform errors into replies. Callers must handle business exceptions such as `IllegalArgumentException` from the service; during diagnostics, also note that the framework may wrap exceptions and attach the failed message.

If you want the gateway to route errors into a dedicated flow, the annotation attribute is `errorChannel`, for example `@MessagingGateway(defaultRequestChannel = "quoteRequests", errorChannel = "quoteErrors")`. That flow must decide whether to return a compatible result or let the error propagate to the caller. [MessagingGateway API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/annotation/MessagingGateway.html)

An error handler that only logs and returns `null` does not automatically become a business response. In particular, never use a zero price quote to mask technical failures: callers may misinterpret it as a real price.

When an API must force an error upon reply timeout, Spring Integration 6.2+ supports `errorOnTimeout` on `@MessagingGateway`. Check the version in use and remember that this option is not a mechanism to interrupt synchronous downstream calls.

## 12. Calling a request-reply subflow with .gateway()

Beyond gateway interfaces at the application boundary, Java DSL provides the `.gateway(...)` operator so one flow can invoke another flow via an input channel and receive a reply. The result from the called flow becomes the input to the next step of the calling flow. [Operator gateway()](https://docs.spring.io/spring-integration/reference/dsl/java-gateway.html)

The example below adds a flow returning only the total amount. It reuses `quoteRequests` and the existing pricing service:

~~~java
@Bean
public IntegrationFlow quoteTotalFlow() {
    return IntegrationFlow.from("quoteTotalRequests")
            .gateway("quoteRequests",
                    gateway -> gateway
                            .requestTimeout(500L)
                            .replyTimeout(1500L))
            .<QuoteReply, java.math.BigDecimal>transform(QuoteReply::total)
            .get();
}
~~~

The input to `quoteTotalRequests` is still `QuoteRequest`, while this flow's business output is `BigDecimal`. Callers can invoke the new flow via a gateway returning `BigDecimal` or via `MessagingTemplate`.

Comparing intents:

| Wiring style | Meaning in design |
| --- | --- |
| `.channel("quoteRequests")` | Forward the message to the next channel |
| `.gateway("quoteRequests")` | Perform an exchange with the target flow and process the reply in the next step |

The inner exchange's return address and the outer caller's return path are two separate layers to keep intact. Use the gateway operator when you need "call a subflow and continue"; do not overwrite the outer flow's reply header with a fixed channel.

## 13. Illustrating request-reply contract tests

The following tests are meant for learners to add to a practice project. They use JUnit Jupiter and Spring Test; no HTTP server or broker is needed.

**QuoteFlowTest.java**

~~~java
package example.requestreply;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.integration.core.MessagingTemplate;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = QuoteFlowConfig.class)
class QuoteFlowTest {

    @Autowired
    QuoteGateway gateway;

    @Autowired
    org.springframework.context.ApplicationContext context;

    @Test
    void normalizesSkuAndReturnsQuoteToCaller() {
        QuoteReply reply = gateway.quote(
                new QuoteRequest(" java-book ", 3));

        assertNotNull(reply);
        assertEquals("JAVA-BOOK", reply.sku());
        assertEquals(0,
                new BigDecimal("360000").compareTo(reply.total()));
    }

    @Test
    void reportsInvalidQuantityToCaller() {
        assertThrows(IllegalArgumentException.class,
                () -> gateway.quote(
                        new QuoteRequest("JAVA-BOOK", 0)));
    }

    @Test
    void returnsPayloadAndPreservesBusinessRequestId() {
        MessageChannel requests = context.getBean(
                "quoteRequests", MessageChannel.class);

        MessagingTemplate template = new MessagingTemplate();
        template.setSendTimeout(500);
        template.setReceiveTimeout(1500);

        Message<QuoteRequest> request = MessageBuilder
                .withPayload(new QuoteRequest(" si-book ", 2))
                .setHeader("requestId", "REQ-001")
                .build();

        Message<?> reply = template.sendAndReceive(requests, request);

        assertNotNull(reply);
        QuoteReply payload =
                assertInstanceOf(QuoteReply.class, reply.getPayload());

        assertEquals("SI-BOOK", payload.sku());
        assertEquals(0,
                new BigDecimal("360000").compareTo(payload.total()));
        assertEquals("REQ-001",
                reply.getHeaders().get("requestId"));
    }
}
~~~

The three examples verify outcomes observable by callers: data is normalized properly, errors are reported back, and required business metadata survives. These matter more than merely checking that an endpoint was invoked.

As the flow grows, add scenarios matching real changes:

| Scenario | What to verify |
| --- | --- |
| Filter rejection | Caller receives the specified error or rejection reply |
| Router with multiple branches | Every valid branch terminates per contract |
| Service may return `null` | Reply-requiring endpoint reports an error |
| Two concurrent requests | Each result matches the right request |
| Worker emits no reply | Caller stops waiting per timeout policy |
| Worker finishes late | Application handles the unknown-outcome state |
| Aggregator missing parts | Group expiry policy and caller outcome exist |

For testing timeouts or completion ordering, control workers with a latch or synchronization signal to create deterministic scenarios instead of relying only on `Thread.sleep`. Spring Integration also provides dedicated tooling to mock endpoints and test individual segments or entire flows. [Testing support](https://docs.spring.io/spring-integration/reference/testing.html)

## 14. Diagnosing a call that waits too long

Start from the symptom observed at the caller, then trace the request:

| Symptom | Where to check first |
| --- | --- |
| Gateway method is not injected | Gateway interface scanning and package scope |
| Sending to direct channel reports no subscribers | Whether the flow is registered and endpoints are active |
| Service runs but caller receives no reply | Final output channel and return path via `replyChannel` |
| Only some inputs time out | Router branches, filters, or aggregator release conditions |
| Requests sit in queue but service never runs | Consumers, pollers, and endpoint status |
| Small `replyTimeout` yet method still takes long | Whether a downstream step is blocking the caller thread |
| Only error logs appear, caller still waits | Whether the error flow produces a result or propagates an error to the caller |
| Results mixed up across calls | Shared reply queue, correlation, and custom dispatcher |
| Retries create duplicate data | Idempotency contract and post-timeout processing state |

You can record `requestId`, endpoint name, and thread at key checkpoints. In the quote example, three useful checkpoints are before the gateway, when pricing starts, and when the caller receives the result. Those points help distinguish queueing time, processing time, and wait time.

Do not start by increasing every timeout. If a filter already dropped the message without producing a reply, increasing the wait duration only delays surfacing the design bug.

## 15. Extended practice

1. Add SKU `"SPRING-BOOK"` priced at `150000` and verify a request for two copies returns total `300000`.
2. Define a business reply containing status `QUOTED` or `REJECTED`; update the service, gateway, and caller assertions consistently.
3. Replace the request channel with `ExecutorChannel` and log thread names to observe the caller/worker boundary.
4. Design a filter capping order quantity; decide explicitly how the caller receives an outcome when a request is rejected.
5. Issue two requests with different processing durations and verify each caller receives its own SKU.
6. Sketch a flow fetching quotes from multiple sources, specifying the correlation key, release condition, and how to reply when one source does not respond.

After the exercises, trace any request by hand from the gateway to the final endpoint. At each step, identify the current payload, headers to preserve, executing thread, and termination paths for both success and failure. That is the basis for composing larger integration patterns while keeping an explicit contract with callers.
