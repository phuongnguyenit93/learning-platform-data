# Header propagation through channels

In the **Message headers** chapter of the `SPRING_INTEGRATION_CORE` module, header propagation is the flow of control and context information traveling alongside a message through an integration pipeline. An order may be normalized, routed, processed on another thread, and aggregated; `tenantId` or a tracking ID still needs to reach where it is used.

This lesson focuses on the relationship among `Message`, `MessageChannel`, and endpoints. It provides the foundation for designing flows with Java DSL, using gateways, transformers, routers, filters, and aggregators, and diagnosing bugs caused by missing metadata.

After this lesson, you can:

- Distinguish a forwarding channel from an endpoint that constructs an output message.
- Predict which headers are preserved across synchronous channels, queues, and executor-backed channels.
- Handle the difference between a transformer returning a payload and returning a full `Message`.
- Proactively keep, overwrite, or suppress headers at a processing step.
- Design tests verifying propagation without depending on arbitrary wait times.

## 1. Headers belong to the message

Suppose a producer creates the following message:

~~~java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

Message<String> input = MessageBuilder
        .withPayload("  order-42  ")
        .setHeader("acmeTraceId", "trace-2026-0042")
        .setHeader("tenantId", "tenant-hcm")
        .setHeader("sourceSystem", "web")
        .build();
~~~

`acmeTraceId`, `tenantId`, and `sourceSystem` live inside `input.getHeaders()`. They are not properties owned by the channel, nor do they automatically live inside a consumer's thread-local variable.

There are three distinct operations to recognize:

| Operation | Example | Question to ask |
| --- | --- | --- |
| Forwarding a message | Sending `input` through an ordinary `DirectChannel` | Which message does the consumer receive? |
| Building output from processing result | Transformer returns normalized string | How does the framework construct the new message and where do headers come from? |
| Intentionally modifying metadata | Header enricher adds `processingStage` | Are old headers preserved or overwritten per configuration? |

~~~mermaid
flowchart LR
    P["Producer: M0 + headers"] --> C1["DirectChannel"]
    C1 --> T["Transformer: returns normalized payload"]
    T --> C2["Next channel: M1 + headers"]
    C2 --> H["Service activator"]
~~~

In this diagram, the point to examine header-copying rules is the transformer's output. The first `DirectChannel` primarily connects the producer to its consumer.

When reading logs, do not assume that crossing a channel regenerates headers. Find the first step where a value changes or disappears.

## 2. Distinguishing message identity from business context

Do not use one header for every purpose.

| Header | Meaning in this lesson | How to use |
| --- | --- | --- |
| `MessageHeaders.ID`, name `id` | Identifies a message instance | Use when correlating message-building steps |
| `MessageHeaders.TIMESTAMP`, name `timestamp` | Message creation time | Do not use as a transaction ID |
| `acmeTraceId` | Application-defined tracking ID | Keep stable across steps of a request |
| `tenantId` | Tenant context | Verify from a trusted source before use |
| `IntegrationMessageHeaderAccessor.CORRELATION_ID` | Framework metadata linking a message group | Coordinates with splitters, publish-subscribe, and aggregators |
| `SEQUENCE_NUMBER`, `SEQUENCE_SIZE` | Sequence position and size | Keep consistent when handling multi-branch results |
| `MessageHeaders.REPLY_CHANNEL` | Reply destination | Must be managed in request-reply flows |
| `MessageHeaders.ERROR_CHANNEL` | Error destination when the error mechanism uses this header | Retain until steps that can raise asynchronous errors |

With the default builder, `id` and `timestamp` are read-only headers managed by the framework. A new message gets a new identity; forwarding the same instance does not require changing its identity. See [Message and predefined headers](https://docs.spring.io/spring-integration/reference/message.html).

For example, two messages can carry the same `acmeTraceId=trace-2026-0042` while having different `id` values because a step changed the payload. That matches the requirement to trace one business operation across multiple transformations.

Two messages can also be created within the same millisecond. Therefore, tests should not force two `timestamp` values to differ just to prove a new message was created.

`acmeTraceId` in this lesson is a custom header and does not automatically integrate with a distributed tracing system. If the application uses a tracing tool, integrate via that tool's context propagation mechanism.

## 3. How do channels affect propagation?

The table below considers the baseline setup: channels within the same JVM, no message-mutating interceptors, no datatype conversion, and no durable message store.

| Channel | Delivery mechanism | Headers to note |
| --- | --- | --- |
| `DirectChannel` | Invokes a consumer on the sending thread in normal success paths | Passes message with headers; does not strip headers when crossing channels |
| `QueueChannel` with in-memory queue | Stores message for a consumer to receive later | Headers travel with the message; a successful `send` only confirms queuing |
| `ExecutorChannel` with thread pool | Submits processing task to an executor | Headers still travel with the message; thread-bound context needs separate handling |
| `PublishSubscribeChannel`, `applySequence=false` | Broadcasts to subscribers | Subscribers may receive the same message instance |
| `PublishSubscribeChannel`, `applySequence=true` | Creates messages carrying sequence metadata for each subscriber | Includes `correlationId`, `sequenceNumber`, and `sequenceSize` matching each branch |

`QueueChannel` does not run business logic automatically on `send`. If wired to an endpoint in a Spring-managed flow, the polling consumer requires a poller configuration. Calling `receive` directly as in the tests below does not need a poller. See [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

`ExecutorChannel` does not guarantee a different thread with every executor implementation: a direct executor or a caller-runs rejection policy can change execution behavior. This lesson uses `Executors.newSingleThreadExecutor()` to illustrate a clear thread boundary.

The distinction to keep sharp is:

- **Metadata in the message:** consumers read from `message.getHeaders()`.
- **Thread-bound context:** such as values in `ThreadLocal` or a logging library's MDC.
- **Transaction boundaries:** a transaction bound to the sending thread does not automatically become the worker's transaction just because the message retains all headers.

Missing a tracking ID in a worker's log is not proof that the channel dropped the header. First read `acmeTraceId` directly from the message the worker receives.

## 4. Endpoints decide how outputs are built

Suppose the incoming message has:

~~~text
payload = "  order-42  "
headers:
  acmeTraceId = "trace-2026-0042"
  tenantId = "tenant-hcm"
  region = "VN"
~~~

Distinguish the following cases:

| Endpoint or outcome | Typical propagation outcome |
| --- | --- |
| Bridge or router forwarding a message | Continues delivering the message; not an output payload construction |
| Filter accepts a message | Forwards the accepted message |
| Filter rejects a message | No output on the success path; discard/error depends on configuration |
| Transformer returns a payload | Framework builds output message and preserves input headers per its rules |
| Transformer returns a full `Message<?>` | The returned message is the complete result; code must provide needed headers |
| Service activator returns a payload | Typically inherits input headers when building output |
| Service activator returns a `Message<?>` | Typically supplements missing input headers; values already on the output take precedence |

Propagation rules and transformer exceptions are documented at [Header Propagation](https://docs.spring.io/spring-integration/reference/message.html#message-header-propagation).

### 4.1. Changing only the payload

The following DSL snippet returns a string:

~~~java
.transform(String.class, text ->
        text.trim().toUpperCase(java.util.Locale.ROOT))
~~~

The business result is `ORDER-42`. When building the output message, the transformer handles preserving headers. You do not have to copy `tenantId` manually just because you applied a string transformation function.

### 4.2. Returning a full Message and forgetting headers

The snippet below uses a `Transformer` that receives and returns a full message:

~~~java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.integration.transformer.Transformer;

Transformer rebuildWithoutHeaders = source -> MessageBuilder
        .withPayload(source.getPayload().toString().trim())
        .build();
~~~

When passing this transformer to `.transform(rebuildWithoutHeaders)`, the output has payload `order-42` and the new message's system headers. `acmeTraceId` and `tenantId` are not restored automatically.

This is a bug caused by how the output message was constructed. The next channel simply receives a message already missing metadata.

If you need to change the payload and keep headers, specify copying explicitly:

~~~java
Transformer normalizeAndKeepHeaders = source -> MessageBuilder
        .withPayload(source.getPayload().toString().trim())
        .copyHeaders(source.getHeaders())
        .setHeader("processingStage", "normalized")
        .build();
~~~

This snippet uses `org.springframework.integration.support.MessageBuilder`. With default behavior, the builder does not let copying overwrite the read-only `id` and `timestamp` of the new message.

If changing only headers and keeping the payload, you can start with:

~~~java
Message<?> updated = MessageBuilder.fromMessage(input)
        .setHeader("processingStage", "received")
        .build();
~~~

`copyHeadersIfAbsent` is helpful when you want to keep values already set on the builder and only fill in missing keys. The builder can return the original message if no effective changes were made; do not rely on `fromMessage(...).build()` as a way to force creating a new instance. See [MessageBuilder](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/MessageBuilder.html) and [BaseMessageBuilder](https://docs.spring.io/spring-integration/api/org/springframework/integration/support/BaseMessageBuilder.html).

## 5. A read-only header map does not mean values are deep-copied

Do not modify the header map directly like this:

~~~java
input.getHeaders().put("tenantId", "tenant-other");
~~~

With default messages, this modification throws `UnsupportedOperationException`. However, an object referenced by a header can still be mutable.

For example:

~~~java
java.util.List<String> tags = new java.util.ArrayList<>();
tags.add("web");

Message<String> message = MessageBuilder.withPayload("order-42")
        .setHeader("tags", tags)
        .build();

tags.add("changed-after-build");
~~~

The message can observe the mutated list even though you never called `put` on the header map. That is the difference between immutability of the map structure and immutability of the values inside. See [Message Headers](https://docs.spring.io/spring-integration/reference/message.html#message-headers).

For multi-branch flows, choose simple or immutable values:

~~~java
Message<String> message = MessageBuilder.withPayload("order-42")
        .setHeader("tags", java.util.List.copyOf(tags))
        .build();
~~~

`List.copyOf` protects the list structure in this string example; it does not deep-copy every element of an arbitrary object graph. Mutable payloads need similar care in design.

If subscriber A mutates a shared object, subscriber B can see changed data or hit race conditions. Creating separate message wrappers per branch does not automatically isolate all inner data.

## 6. Practicing a complete Java DSL flow

Scenario: ingest an order code, attach a pipeline name, normalize the payload, pass through an intermediate channel, and validate the order. At the final output, keep business metadata while suppressing headers meant for internal use.

The examples use Java DSL with `spring-integration-core` and JUnit Jupiter for tests. The project needs compatible Spring dependencies; Spring Boot can manage versions via BOM. The code below uses a Spring context directly without requiring a Boot application startup.

### 6.1. Flow configuration

~~~java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class HeaderPropagationConfig {

    @Bean
    public DirectChannel ordersIn() {
        return new DirectChannel();
    }

    @Bean
    public DirectChannel handoff() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel completed() {
        return new QueueChannel(10);
    }

    @Bean
    public IntegrationFlow orderFlow() {
        return IntegrationFlow.from("ordersIn")
                .enrichHeaders(headers ->
                        headers.header("pipeline", "order-v1"))
                .transform(String.class, payload ->
                        payload.trim().toUpperCase(Locale.ROOT))
                .channel("handoff")
                .handle(String.class,
                        (payload, headers) -> payload + "|VALIDATED",
                        endpoint -> endpoint.notPropagatedHeaders(
                                "internal*", "authToken"))
                .channel("completed")
                .get();
    }
}
~~~

`notPropagatedHeaders` belongs to the `handle` endpoint configuration. It specifies which input headers are not copied when the handler constructs its output; it does not configure stripping headers on the `handoff` channel. The API supports exact header names and simple `*` patterns, not regular expressions. See [ConsumerEndpointSpec.notPropagatedHeaders](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/ConsumerEndpointSpec.html).

### 6.2. Testing output payload and headers

Place the test below in the same package as `HeaderPropagationConfig`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class HeaderPropagationFlowTest {

    @Test
    void keepsBusinessContextAndSuppressesInternalHeaders() {
        try (var context = new AnnotationConfigApplicationContext(
                HeaderPropagationConfig.class)) {

            DirectChannel input =
                    context.getBean("ordersIn", DirectChannel.class);
            QueueChannel output =
                    context.getBean("completed", QueueChannel.class);

            Message<String> request = MessageBuilder
                    .withPayload("  order-42  ")
                    .setHeader("acmeTraceId", "trace-2026-0042")
                    .setHeader("tenantId", "tenant-hcm")
                    .setHeader("internalRouteMemo", "temporary-note")
                    .setHeader("authToken", "demo-token")
                    .build();

            assertTrue(input.send(request, 1_000));

            Message<?> result = output.receive(1_000);
            assertNotNull(result);
            assertEquals("ORDER-42|VALIDATED", result.getPayload());
            assertEquals("trace-2026-0042",
                    result.getHeaders().get("acmeTraceId"));
            assertEquals("tenant-hcm",
                    result.getHeaders().get("tenantId"));
            assertEquals("order-v1",
                    result.getHeaders().get("pipeline"));
            assertFalse(result.getHeaders()
                    .containsKey("internalRouteMemo"));
            assertFalse(result.getHeaders().containsKey("authToken"));
            assertNotEquals(request.getHeaders().getId(),
                    result.getHeaders().getId());
        }
    }
}
~~~

Expected results:

| Property | Input | Output |
| --- | --- | --- |
| Payload | `"  order-42  "` | `"ORDER-42\|VALIDATED"` |
| `acmeTraceId` | `trace-2026-0042` | Preserved |
| `tenantId` | `tenant-hcm` | Preserved |
| `pipeline` | Absent | `order-v1` |
| `internalRouteMemo` | Present | Absent |
| `authToken` | Present | Absent |
| `id` | Request ID | Output message ID |

In this flow, `completed` is an explicitly configured output channel. The test actively receives from the queue, so no poller is required. Nor does it rely on `Thread.sleep`: the `receive` call has a timeout waiting directly for the expected result.

The tests in this lesson are practice code to run in a project with appropriate dependencies; the lesson does not include pre-captured test run outputs.

## 7. Verifying via DirectChannel and ExecutorChannel

The flow test above checks the outcome across multiple endpoints. To clearly separate message handoff from output creation, you can test channels individually.

The following example uses in-memory channels with no interceptors or message history configured:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class ChannelHeaderHandoffTest {

    @Test
    void directChannelHandsTheMessageToItsSubscriber() {
        DirectChannel channel = new DirectChannel();
        AtomicReference<Message<?>> received = new AtomicReference<>();
        channel.subscribe(received::set);

        Message<String> sent = MessageBuilder.withPayload("order-42")
                .setHeader("acmeTraceId", "trace-42")
                .build();

        assertTrue(channel.send(sent, 1_000));

        assertSame(sent, received.get());
        assertEquals("trace-42",
                received.get().getHeaders().get("acmeTraceId"));
    }

    @Test
    void executorChannelKeepsHeadersAcrossTheThreadBoundary()
            throws InterruptedException {

        var executor = Executors.newSingleThreadExecutor();
        try {
            ExecutorChannel channel = new ExecutorChannel(executor);
            QueueChannel observed = new QueueChannel(1);
            AtomicReference<Thread> worker = new AtomicReference<>();
            Thread sender = Thread.currentThread();

            channel.subscribe(message -> {
                worker.set(Thread.currentThread());
                observed.send(message, 1_000);
            });

            Message<String> sent = MessageBuilder.withPayload("order-42")
                    .setHeader("acmeTraceId", "trace-42")
                    .setHeader("tenantId", "tenant-hcm")
                    .build();

            assertTrue(channel.send(sent, 1_000));

            Message<?> received = observed.receive(1_000);
            assertNotNull(received);
            assertEquals("trace-42",
                    received.getHeaders().get("acmeTraceId"));
            assertEquals("tenant-hcm",
                    received.getHeaders().get("tenantId"));
            assertNotNull(worker.get());
            assertNotSame(sender, worker.get());
        }
        finally {
            executor.shutdownNow();
            executor.awaitTermination(1, TimeUnit.SECONDS);
        }
    }
}
~~~

`assertSame` in the first test simply describes delivery in that minimal configuration. When interceptors create new messages or other features enrich metadata, the application should assert the required header contract rather than demanding identical Java object references everywhere.

In the second test, pulling the message from `observed` proves the worker actually received the message. Merely asserting `channel.send(...) == true` does not prove the asynchronous business step completed.

## 8. PublishSubscribeChannel and sequence metadata

Suppose an order needs two branches:

- Branch A calculates shipping cost.
- Branch B checks inventory.
- A downstream aggregator waits for results from both branches.

`PublishSubscribeChannel` has an `applySequence` option. By default this option is `false`. When enabled, the channel provides sequence metadata to subscribers; each branch's message may be a different wrapper while still sharing the payload reference. See [PublishSubscribeChannel Configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html#channel-configuration-pubsubchannel).

The test below illustrates two synchronous branches; no executor is attached, so results can be collected immediately after `send`:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.integration.support.MessageBuilder;
import org.springframework.messaging.Message;

import static org.junit.jupiter.api.Assertions.*;

class FanOutHeadersTest {

    @Test
    void addsSequenceMetadataAndKeepsBusinessHeaders() {
        PublishSubscribeChannel channel = new PublishSubscribeChannel();
        channel.setApplySequence(true);

        List<Message<?>> copies = new ArrayList<>();
        channel.subscribe(message -> {
            copies.add(message);
        });
        channel.subscribe(message -> {
            copies.add(message);
        });

        Message<String> request = MessageBuilder.withPayload("order-42")
                .setHeader("acmeTraceId", "trace-42")
                .setHeader("tenantId", "tenant-hcm")
                .build();

        assertTrue(channel.send(request, 1_000));
        assertEquals(2, copies.size());

        String correlation =
                IntegrationMessageHeaderAccessor.CORRELATION_ID;
        String sequenceNumber =
                IntegrationMessageHeaderAccessor.SEQUENCE_NUMBER;
        String sequenceSize =
                IntegrationMessageHeaderAccessor.SEQUENCE_SIZE;

        for (Message<?> branch : copies) {
            assertEquals("trace-42",
                    branch.getHeaders().get("acmeTraceId"));
            assertEquals("tenant-hcm",
                    branch.getHeaders().get("tenantId"));
            assertEquals(request.getHeaders().getId(),
                    branch.getHeaders().get(correlation));
            assertEquals(2, branch.getHeaders().get(sequenceSize));
        }

        assertEquals(1,
                copies.get(0).getHeaders().get(sequenceNumber));
        assertEquals(2,
                copies.get(1).getHeaders().get(sequenceNumber));
        assertNotSame(copies.get(0), copies.get(1));
    }
}
~~~

The test uses two separate subscriber lambdas to create two distinct registrations. A regular list works because the example runs synchronously; if switching to parallel execution, use a thread-safe mechanism to collect results.

When connecting branches to an aggregator, preserve group and sequence metadata until the aggregator has consumed them. For example, if a transformer returns a brand-new message keeping only `acmeTraceId`, `sequenceSize` metadata can vanish even though the tracking ID remains.

`acmeTraceId` serves business tracing. `correlationId` in the fan-out example serves group correlation. Keeping these two purposes separate prevents a grouping step from corrupting the end-to-end tracking ID.

Enabling `applySequence` does not guarantee the aggregator will receive all results either: if a branch is dropped by a filter or finishes without producing output, an appropriate release/timeout policy matching business rules is required.

## 9. Proactively controlling headers

### 9.1. Setting output values and precedence rules

A service activator can proactively return a message carrying new values:

~~~java
.handle(String.class, (payload, headers) ->
        MessageBuilder.withPayload(payload)
                .setHeader("region", "APAC")
                .build())
~~~

With a service activator's default propagation, missing input headers can be supplemented. `region=APAC` already present on the output takes precedence over `region=VN` from the input.

With a header enricher, you can specify whether overwriting is permitted:

~~~java
.enrichHeaders(headers ->
        headers.header("processingStage", "validated", true))
~~~

The `true` parameter here is the overwrite flag. Specify this option explicitly when a status must reflect the current step. See [HeaderEnricherSpec](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/HeaderEnricherSpec.html).

### 9.2. Suppressing copying is not equivalent to deleting from every source

`notPropagatedHeaders("authToken")` prevents copying `authToken` from the input message to the output on a matching handler. If the handler's own code builds an output containing `authToken`, do not treat this setting as an all-purpose header-stripping layer.

Another trap is deleting a header from the message returned by a service activator while still allowing default propagation: the framework may add the missing key back from the request.

When the goal is to remove headers from the current message, you can use a header filter as a dedicated step:

~~~java
.headerFilter("authToken")
~~~

This is a transformer for headers, distinct from `filter(...)` which decides whether to allow the entire message to proceed. The example uses an exact name; when pattern-based removal is needed, configure the header filter's pattern matching capability per the API in use. See [Java DSL headerFilter](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html#headerFilter(java.lang.String...)).

Do not configure `notPropagatedHeaders` on a router or bridge expecting forwarding-only components to rebuild output messages to drop headers.

### 9.3. Selecting an allowlist of headers for an explicit boundary

In an event-publishing-only flow, you can build messages with a curated list of metadata:

~~~java
import org.springframework.integration.support.MessageBuilder;
import org.springframework.integration.transformer.Transformer;

Transformer toExportEvent = source -> MessageBuilder
        .withPayload(source.getPayload())
        .setHeader("acmeTraceId",
                source.getHeaders().get("acmeTraceId", String.class))
        .setHeader("tenantId",
                source.getHeaders().get("tenantId", String.class))
        .build();
~~~

When using `.transform(toExportEvent)`, the list of outbound business headers is decided explicitly by this code. This is deliberate rather than accidentally forgetting to copy.

This fits an event-export boundary designed without needing to reply to a caller. If reused in a request-reply flow, additionally account for `replyChannel`, `errorChannel`, and any required group metadata.

Likewise, keeping `tenantId` only provides context info; it does not replace authentication or tenant access authorization checks.

## 10. Reply channel, error channel, and hard-to-observe failures

### 10.1. Gateways need an intact reply path

A request-reply gateway typically creates a temporary reply channel and puts its reference in the request's headers. If endpoints preserve the necessary context, the reply can return to where the gateway is waiting. See [Messaging Gateways: Setting the Default Reply Channel](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-default-reply-channel).

Example path:

~~~text
Gateway
  -> requestChannel
  -> transformer
  -> reply-producing service activator
  -> request's replyChannel
~~~

If a mid-flow transformer returns a new `Message` without keeping `replyChannel`, subsequent steps may lack a return path. With no output channel or other routing mechanism, the endpoint may fail with destination-resolution errors; the caller may also receive no reply depending on error and timeout settings.

Check all of these together:

1. Which channel is the gateway sending requests to?
2. Which step rebuilds the full message?
3. Does the final endpoint have an explicit output channel?
4. Are reply headers and timeouts still consistent with processing duration?

The practice flow in section 6 ends at `completed`. If you switch the caller to a gateway while keeping that output, the gateway does not automatically retrieve results from that queue just because the request had a `replyChannel`. Design a matching return path.

### 10.2. Having errorChannel is not enough to turn every failure into a message

With direct calls through `DirectChannel`, exceptions usually propagate back up the call stack. When executing via asynchronous tasks managed by Spring Integration, an error handler mechanism can emit an `ErrorMessage`, preferring the destination in the request's `errorChannel` and then falling back to the global error channel. See [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

Hence, distinguish these two symptoms:

| Symptom | What to check |
| --- | --- |
| Producer catches an exception directly on `send` | The flow is executing on the sender's thread |
| `send` succeeds yet business logic fails afterward | Error handler and error-receiving channel of the async task |
| Error goes to global channel instead of dedicated channel | Was `errorChannel` still on the message at the moment of failure? |
| Business headers missing on `ErrorMessage` | Inspect failed request or failed message; do not assume all request headers live at the top level of the error message |

A queue itself does not know how a consumer failed in business terms. If you write your own `receive` loop and invoke handlers outside the framework's endpoint/poller mechanism, design exception catching and forwarding accordingly.

## 11. Leaving single-process memory

Preserving headers across an internal channel does not prove headers will survive a broker, HTTP, or persistence mechanism.

### 11.1. Message stores may serialize data

When persisting messages into a durable message store, retaining payload and headers depends on the serializer and implementation. A Java object that passes smoothly over `DirectChannel` may not persist intact. Default `JdbcMessageStore`, for example, filters out non-serializable headers before serialization. See [Message Store](https://docs.spring.io/spring-integration/reference/message-store.html).

In the order example, `String` values such as `tenantId` and `acmeTraceId` are far easier to contract around than placing service beans, connections, or execution-context objects into headers.

Tests at this boundary should read the message back after it has actually passed through the store, rather than only checking the map before saving.

### 11.2. Channel references are process-local resources

`replyChannel` can hold a `MessageChannel` object. When serialization is required, the header channel registry mechanism can replace channel references with string keys to resolve back later. That key depends on the registry still existing and the entry still being valid. See [Header Channel Registry](https://docs.spring.io/spring-integration/reference/content-enrichment.html#header-channel-registry).

Do not treat a registry key as a network address across application instances. For communication between two services, design an explicit transport reply contract and appropriate correlation keys.

### 11.3. Transports have their own header mappers

An internal header named `tenantId` does not automatically become an HTTP header or broker property. Adapters and mappers decide the names, types, and scope of headers sent over the transport.

For HTTP, for example, inspect mapped-header configuration or `DefaultHttpHeaderMapper`. See [HTTP Header Mappings](https://docs.spring.io/spring-integration/reference/http/header-mapping.html).

A complete verification covers: the message before the adapter, the data actually transmitted over the transport, and the message reconstructed on the receiving side. This lesson does not implement adapters; this principle defines the boundaries of propagation guarantees within core.

## 12. Finding where headers are lost and practicing on your own

### 12.1. Recording checkpoints accurately

When a consumer fails to receive `tenantId`, compare each stage:

~~~text
A. Message freshly created by producer
B. Message entering normalization endpoint
C. Message exiting normalization endpoint
D. Message before entering executor or queue
E. Message actually received by consumer
~~~

At each stage, log only the metadata needed for investigation, for example:

~~~text
checkpoint=normalized-out
id=<message-id>
acmeTraceId=trace-2026-0042
tenantId=tenant-hcm
thread=<thread-name>
~~~

A `ChannelInterceptor` can observe sends or receives; `preSend` can also replace the message with another result. Therefore, when a message changes right on a channel, check both local interceptors and global interceptors. Receive hooks apply only to pollable channels. See [Channel Interceptors](https://docs.spring.io/spring-integration/reference/channel/interceptors.html).

Do not log the entire message just to track down one header because the payload or other headers may contain private data or tokens.

### 12.2. Scenarios to recognize

| Symptom | Possible cause to check | Fix |
| --- | --- | --- |
| After transformer, payload exists but business metadata is gone | Returned full message and forgot to copy headers | Return payload or explicitly build required headers |
| Across executor, message has trace ID yet log misses it | Logging context lives on the thread | Restore and clear context in workers |
| Header removed then reappears after service activator | Output lacks key and propagation filled it from input | Suppress at handler or use a header filter in an explicit step |
| Two subscribers affect each other's data | Shared mutable header value or payload | Use immutable data or copy intentionally |
| Aggregator lacks facts to group | Missing sequence metadata or missing one branch's result | Check each branch's output and group completion policy |
| Internal headers complete, HTTP receiver misses them | Mapper does not export header over transport | Check configuration and receiving-side message |
| Message reference changes even when just crossing a channel | Interceptor or metadata-enriching feature | Assert the header contract, not just reference equality |

### 12.3. Extension exercises

1. Replace the payload-returning transformer in section 6 with `rebuildWithoutHeaders`. Predict which assertions fail, then verify in your project.
2. Switch the transformer to `normalizeAndKeepHeaders` and assert both payload and business headers.
3. Remove `notPropagatedHeaders` from the service activator. Observe `authToken` at the output and add `headerFilter("authToken")` at an appropriate step.
4. Replace `handoff` with an `ExecutorChannel` whose executor lifecycle is managed by Spring. Keep waiting for the result via `receive(timeout)` and check headers as before.
5. Expand fan-out into two branches with different outputs. Preserve group metadata up to an aggregator and design the case where one branch returns no result.
6. With a separate request-reply gateway, write tests with finite timeouts for both keeping and losing the return path.

The goal upon completion is to be able to explain **who created each header, which message owns it, which endpoint decides copying, and which boundaries need dedicated contracts**. These questions help you read and design Spring Integration flows without relying on the assumption that "every header is always preserved."
