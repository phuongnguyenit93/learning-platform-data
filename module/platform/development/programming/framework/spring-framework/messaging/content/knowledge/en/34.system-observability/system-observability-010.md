# Hop-by-Hop Diagnosis of Missing Messages

When a message "never arrives," the first question is: where did it not arrive? The producer may have created the message without sending it; the transport may have received the request without routing it to a handler; the handler may have run without emitting a result; the reply may have reached the client only to be dropped by decoding, filtering, or cancellation. The phrase "not received" only describes a symptom at one observation point, not the layer causing the failure.

An effective diagnostic approach is to split the messaging flow into named hops, record evidence at each hop boundary, and use the same correlation ID to link events. Once you know where the last recorded event appeared, you can narrow the failure down to the very next segment without logging full payloads or guessing from a timeout.

This lesson focuses on Spring Messaging and RSocket, while showing how to apply the same approach to Spring Integration channels.

## 1. Mapping the Path of a Message

A typical RSocket request/response flow has the following hops:

~~~text
Producer / API caller
       |
       v
Create request + correlation ID
       |
       v
RSocketRequester: route + encode + subscribe
       |
       v
Connection / transport / RSocket protocol
       |
       v
RSocketMessageHandler: decode + route mapping
       |
       v
@MessageMapping handler
       |
       v
Business service / downstream channel
       |
       v
Handler creates Mono/Flux response
       |
       v
Encode + transport returns response
       |
       v
RSocketRequester decode + caller consume
~~~

With Spring Integration, between the handler and business service there may also be a MessageChannel, router, filter, transformer, splitter, aggregator, or outbound adapter. Each channel and endpoint is a boundary that must be observed separately. Do not collapse everything into a single "Spring received the message" step.

Before investigating, state clearly:

- Where is the message created and who is the producer?
- Which event defines "sent"?
- Which component is expected to receive the message next?
- Is the message request/response, stream, fire-and-forget, or channel-based?
- What evidence proves a hop has completed?

A completed send call, a subscribed publisher, a transport receiving frames, and a business handler committing data are four distinct events. Do not treat them as interchangeable.

## 2. Attaching an End-to-End Identifier

Every business operation should have a correlation ID that stays stable across hops. For each retry, you can add an attempt number or a separate request ID to distinguish send attempts. Message ID identifies a single message instance; it can change when the framework constructs a new message, so do not use it as the cross-hop correlation key.

In Spring Integration, IntegrationMessageHeaderAccessor.CORRELATION_ID links messages belonging to the same group; SEQUENCE_NUMBER and SEQUENCE_SIZE support splitters/aggregators. In RSocket, the correlation ID can reside in a payload envelope or in application metadata configured on both sides. Do not assume metadata automatically becomes a Spring header unless a MetadataExtractor is configured.

An event log should include these fields:

| Field | Purpose |
|---|---|
| timestamp | Compare event ordering; use time synchronization across hosts |
| event | Hop name: created, send, accepted, handler-start, reply, consumed... |
| correlationId | Stitch logs of the same operation |
| messageId | Identify the message instance at the current hop |
| route / destination | Identify the target endpoint |
| interaction | Request-Response, Request-Stream, Fire-and-Forget, or Request-Channel |
| node / service | Identify the processing instance |
| attempt | Distinguish retries |
| payloadType / size | Check codecs and sizes without logging sensitive content |
| outcome / error | Record success, timeout, cancellation, or error |
| durationMs | Measure processing time at the hop |

Correlation IDs belong in logs or traces, not as metric tags, since every request can produce a distinct value and cause unbounded cardinality growth. Metrics should only use low-cardinality dimensions such as route, interaction, outcome, and service.

Do not log full payloads, tokens, personal data, or secrets. If payload verification is needed, log the data type, size, or a digest governed by clear security policies.

## 3. Diagnosing From the Last Observed Event

Use this table as a decision tree. Start from the producer, find the last event with the same correlation ID, and inspect the hop immediately following it.

| Last recorded evidence | Next hop to inspect | Common causes |
|---|---|---|
| No created event | Producer / trigger | Trigger did not fire, validation stopped, transaction rolled back before publish |
| Created exists, no send | Outbound publisher | Filter dropped message, branch not subscribed, code returned publisher without subscribing |
| Send exists, no transport/connection evidence | Client connection and transport | Not connected, setup failed, connection closed, DNS/TLS/network issue, or wrong address |
| Connection exists, no handler entry | Route and responder mapping | Wrong route, routing metadata not encoded, wrong interaction model, responder not registered |
| Handler entry exists, no processing-start | Handler/reactive pipeline | Publisher not subscribed, conditional branch, synchronous error before calling service |
| Processing-start exists, no processing-complete | Business service/downstream | Hung call, full queue, slow dependency, exception, deadlock, or cancellation |
| Processing-complete exists, no reply | Handler output/encoding | Handler returned Mono.empty/Mono<Void>, encoding error, mismatched response type |
| Server reply exists, not seen on client | Response transport/client decode | Connection already closed, codec/MIME type mismatch, cancelled response, or client timeout |
| Client received reply, caller did not see it | Final consumer | Filtered/dropped, mapping error, subscriber cancelled, result not persisted or rendered |

A missing log at one hop does not prove that hop did not execute: logs can be sampled, filtered, lost by collectors, or not yet flushed. Cross-check with metrics, traces, queue depth, broker offsets, and a small reproducible test.

## 4. Distinguishing Send, Delivery, and Business Completion

Messaging systems often have multiple levels of confirmation:

- Created: the application constructed the message.
- Published/sent: the publisher invoked the send API or the publisher completed per its contract.
- Accepted: the broker/transport confirmed receipt of the data per protocol.
- Delivered: the consumer received the message.
- Processed: the handler finished executing its logic.
- Committed: side effects were durably persisted.
- Replied/acknowledged: the response or acknowledgement was sent.

RSocket Fire-and-Forget provides no business response. `requester.send()` completing does not prove the handler committed. When business confirmation is needed, use Request-Response, a separate completion event, or an independent state query.

With Spring Integration, `MessageChannel.send()` returns when the channel accepts the message according to channel semantics. With `ExecutorChannel`, the message may only be placed onto the executor queue while the handler runs later. A successful send does not mean downstream endpoints have finished. Instrument both channel boundaries and services/handlers.

With brokers using acknowledgements, distinguish delivery tag/offset from the moment of ack. A consumer may have received the message without committing yet; the message may be redelivered. Design idempotent consumers and record duplicates rather than assuming every message arrives exactly once.

## 5. Instrumenting Spring Integration Channels

`ChannelInterceptor` observes the `MessageChannel` instances it is registered on. `preSend` runs before the channel sends the message; `postSend` observes the send outcome; `afterSendCompletion` runs after send completion or failure. For asynchronous channels, these callbacks do not replace handler logs because the send can finish before the consumer processes the message.

Simple interceptor example using `System.Logger`:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;

public final class DiagnosticChannelInterceptor
        implements ChannelInterceptor {

    private static final System.Logger LOG =
            System.getLogger(DiagnosticChannelInterceptor.class.getName());

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        Object correlationId = message.getHeaders().get("correlationId");
        LOG.log(System.Logger.Level.INFO,
                "event=channel-pre-send channel=" + channel
                        + " correlationId=" + correlationId
                        + " messageId=" + message.getHeaders().getId());
        return message;
    }

    @Override
    public void postSend(
            Message<?> message, MessageChannel channel, boolean sent) {
        LOG.log(System.Logger.Level.INFO,
                "event=channel-post-send sent=" + sent
                        + " correlationId="
                        + message.getHeaders().get("correlationId"));
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex) {
        if (ex != null) {
            LOG.log(System.Logger.Level.ERROR,
                    "event=channel-send-error correlationId="
                            + message.getHeaders().get("correlationId"),
                    ex);
        }
    }
}
~~~

Register the interceptor on the channels you want to observe, such as channels supporting `ChannelInterceptor` or through application channel configuration. Do not register an interceptor on one channel and assume it covers every transport or every other channel.

With Spring Integration, `wireTap` can forward a copy of messages to a diagnostic channel. `MessageHistory` can record the components a message traversed when history tracking is enabled. This is valuable evidence for internal routing paths, though it does not replace inter-process tracing or broker/transport logs.

## 6. Instrumenting RSocket Requester and Handler

`RSocketRequester` returns lazy publishers. If the publisher is not subscribed to, the request is not sent. Place hooks on the publisher to observe subscription, response, error, and terminal signals:

~~~java
Mono<OrderReply> reply = requester.route("orders.lookup")
        .data(request)
        .retrieveMono(OrderReply.class)
        .doOnSubscribe(ignored -> log.info(
                "event=rsocket-client-send correlationId={}", correlationId))
        .doOnNext(value -> log.info(
                "event=rsocket-client-reply correlationId={}", correlationId))
        .doOnError(error -> log.error(
                "event=rsocket-client-error correlationId={}", correlationId, error))
        .doFinally(signal -> log.info(
                "event=rsocket-client-terminal correlationId={} signal={}",
                correlationId, signal));
~~~

`doOnSubscribe` proves the publisher was subscribed to; it does not prove the server received the request. `doOnNext` proves the client decoded and received the response. If `doOnNext` never fires, inspect server-side logs and connection/transport events.

On the responder, log when the handler is invoked and when the reactive pipeline actually subscribes and terminates:

~~~java
@MessageMapping("orders.lookup")
public Mono<OrderReply> lookup(@Payload OrderRequest request) {
    String correlationId = request.correlationId();
    log.info("event=rsocket-handler-invoked correlationId={}", correlationId);

    return Mono.defer(() -> {
        log.info("event=business-start correlationId={}", correlationId);
        return orderService.lookup(request.orderId())
                .doOnNext(value -> log.info(
                        "event=business-complete correlationId={}", correlationId))
                .doOnError(error -> log.error(
                        "event=business-error correlationId={}", correlationId, error))
                .doFinally(signal -> log.info(
                        "event=handler-terminal correlationId={} signal={}",
                        correlationId, signal));
    });
}
~~~

This example assumes `OrderRequest` carries `correlationId` in its payload. Applications can pass the ID via metadata instead, provided the MIME type and `MetadataExtractor` are configured on the responder to extract the value properly. Do not use `ThreadLocal` to pass correlation across a Reactor pipeline unless context propagation is enabled; callbacks may run on different threads. When context is needed, use Reactor Context or Micrometer Observation/Tracing integration appropriate for your application version.

## 7. Using Metrics and Tracing to Narrow Down Failure Locations

Logs help inspect a specific request; metrics show whether an error is widespread; traces show where time was spent.

Useful metrics:

- Requests sent and responses received by route/interaction.
- Rates of errors, timeouts, cancellations, and requests without responses.
- Processing durations in handlers and downstream dependencies.
- Queue depth, consumer lag, pending messages, and retry counts.
- Active connections and connection setup/error counts.
- `MessageGroupStore` size or pending groups if using an aggregator.

Do not assume metric names are identical across all Spring versions, RSocket transports, and registries. List the metrics actually exposed by your exporter and identify the right ones for your deployed version. Use low-cardinality tags; correlation ID, user ID, or message ID should not become tags.

Tracing connects spans across services. A useful trace has spans for the producer, outbound messaging, transport/server, handler, and downstream dependencies. If a trace stops at the producer, check context propagation and outbound client instrumentation. If the server span fails to link to the client span, check transport propagation and tracing configuration. RSocket metadata carries trace context only when client/server are configured accordingly; do not assume every RSocket connection automatically propagates W3C trace headers.

Synchronize clocks across hosts using NTP or an equivalent mechanism. When comparing durations inside the same process, use a monotonic clock such as `System.nanoTime()` instead of subtracting two wall-clock timestamps that can be adjusted.

## 8. Checking Routes, Codecs, and Metadata

When the server has a connection but shows no handler entry, check the following:

- Does the route in the requester match `@MessageMapping` exactly?
- Is the requester sending routing metadata with the proper composite metadata MIME type?
- Are the data MIME types compatible on both sides?
- Do the Encoder/Decoder support the actual payload type?
- Does `MetadataExtractor` register the MIME type and map metadata to the expected header?
- Does the interaction model match the handler signature?
- Is the handler registered in `RSocketMessageHandler` or the Spring ApplicationContext?

Testing with a plain default `String` does not prove custom JSON/CBOR codecs work. Send real objects, real metadata, and assert values inside the handler. When debugging, log route, MIME type, payload class, and metadata keys; avoid logging tokens or raw metadata containing secrets.

## 9. Distinguishing Reactive Lifecycle Failures

A common mistake is creating a `Mono`/`Flux` without subscribing. Reactor publishers are lazy: code inside `map`/`defer` executes only upon subscription. With `RSocketRequester`, creating the request publisher does not mean the request has been sent.

Symptoms to distinguish:

- Missing `doOnSubscribe`: the publisher was never subscribed to, or code never entered the branch creating the publisher.
- `doOnSubscribe` present without response/error: the request may be waiting, the server is unresponsive, the connection is hung, or no timeout is configured.
- `doOnError` present: classify transport, route, codec, or business errors from the cause and server logs.
- `doFinally` with `signal=CANCEL`: the subscriber cancelled, or a timeout/upstream operator cancelled.
- `handler-invoked` present without `handler-terminal`: the handler publisher may never complete or is held up by a dependency.
- Server completes while client receives nothing: inspect response encoding, connection state, and client cancellation.

Use bounded timeouts and handle cancellations explicitly. Never call `block()` on an event-loop or reactive handler, as it can deadlock or stall transport threads. In tests, use `StepVerifier.verify(Duration)` to avoid hanging indefinitely.

## 10. Step-by-Step Investigation Workflow for a Real Incident

1. Collect a correlation ID and a narrow time window. Record route, interaction model, service/instance, and attempt.
2. Locate the first event on the producer. Confirm the message was created and reached the send call.
3. Check client requester events: subscribe, send, error, terminal. If subscribe is missing, investigate publisher creation and execution branches.
4. Inspect connection/transport, setup, and broker/queues if present. Cross-check connection logs, active connections, queue depth, and consumer lag.
5. Locate the `handler-invoked` event on the responder. If absent, check routes, responder mappings, MIME types, and codecs.
6. If the handler ran, trace every downstream dependency, channel, filter, router, and transaction.
7. If business logic completed without a response, inspect `Mono`/`Flux` return types, empty completions, error mapping, and encoding.
8. If the server emitted a reply, inspect client response/error/terminal hooks, timeouts, cancellations, and decoding.
9. Reproduce with a `LocalTransport` integration test to isolate mapping/codec/protocol; then run TCP/WebSocket tests if a real transport issue is suspected.
10. Document the last hop with evidence, the confirmed root cause, and which metrics/logs/tests will detect it early next time.

When messages travel through a broker, add checks for broker publish acknowledgements, routing keys/topics, subscriptions/bindings, consumer groups/offsets, retry queues, dead-letter queues, and acknowledgements. Do not assume RSocket transports and brokers share the same delivery semantics.

## 11. Reproducing With a LocalTransport Test

`LocalTransport` lets you connect `RSocketRequester` and `RSocketMessageHandler` through the protocol stack within the same process. Use a unique transport name per test. This test proves routes, payloads, and handlers actually exchange messages while producing correlated log checkpoints.

### 11.1. Maven dependencies

Minimal POM for Java 17, Spring Framework 7.0.8, RSocket Java 1.1.5, Reactor Test, and JUnit 5:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>rsocket-missing-message-test</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <spring.version>7.0.8</spring.version>
    <rsocket.version>1.1.5</rsocket.version>
    <junit.version>5.12.2</junit.version>
    <reactor.version>3.8.7</reactor.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-messaging</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>${spring.version}</version>
    </dependency>
    <dependency>
      <groupId>io.rsocket</groupId>
      <artifactId>rsocket-core</artifactId>
      <version>${rsocket.version}</version>
    </dependency>
    <dependency>
      <groupId>io.rsocket</groupId>
      <artifactId>rsocket-transport-local</artifactId>
      <version>${rsocket.version}</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <version>${reactor.version}</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>${junit.version}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
        <configuration><release>17</release></configuration>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.3</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

If the application uses Spring Boot, prefer Boot's dependency management rather than pinning standalone versions like this example.

### 11.2. Complete test

Save as src/test/java/example/MissingMessageDiagnosticTest.java:

~~~java
package example;

import java.time.Duration;
import java.util.List;

import io.rsocket.core.RSocketServer;
import io.rsocket.transport.local.LocalClientTransport;
import io.rsocket.transport.local.LocalServerTransport;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertNotNull;

class MissingMessageDiagnosticTest {

    static final class DiagnosticHandler {
        private static final System.Logger LOG =
                System.getLogger(DiagnosticHandler.class.getName());

        @MessageMapping("orders.lookup")
        public Mono<String> lookup(@Payload String envelope) {
            String[] parts = envelope.split("\\|", 2);
            if (parts.length != 2) {
                return Mono.error(new IllegalArgumentException(
                        "Expected correlationId|orderId"));
            }

            String correlationId = parts[0];
            String orderId = parts[1];
            LOG.log(System.Logger.Level.INFO,
                    "hop=server-handler-invoked correlationId=" + correlationId);

            return Mono.defer(() -> {
                LOG.log(System.Logger.Level.INFO,
                        "hop=server-processing-start correlationId=" + correlationId);
                return Mono.just("found:" + orderId)
                        .doOnNext(value -> LOG.log(System.Logger.Level.INFO,
                                "hop=server-processing-complete correlationId="
                                        + correlationId))
                        .doFinally(signal -> LOG.log(System.Logger.Level.INFO,
                                "hop=server-handler-terminal correlationId="
                                        + correlationId + " signal=" + signal));
            });
        }
    }

    @Test
    void logsCorrelationAtClientAndHandlerAndReturnsReply() {
        String transportName = "missing-message-row396";
        String correlationId = "corr-396";
        RSocketStrategies strategies = RSocketStrategies.create();

        RSocketMessageHandler messageHandler = new RSocketMessageHandler();
        messageHandler.setRSocketStrategies(strategies);
        messageHandler.setHandlers(List.of(new DiagnosticHandler()));
        messageHandler.afterPropertiesSet();

        Disposable server = RSocketServer.create(messageHandler.responder())
                .bind(LocalServerTransport.create(transportName))
                .block(Duration.ofSeconds(5));
        assertNotNull(server);

        RSocketRequester requester = RSocketRequester.builder()
                .rsocketStrategies(strategies)
                .transport(LocalClientTransport.create(transportName));

        System.Logger log = System.getLogger(
                MissingMessageDiagnosticTest.class.getName());
        try {
            Mono<String> reply = requester.route("orders.lookup")
                    .data(correlationId + "|order-42")
                    .retrieveMono(String.class)
                    .doOnSubscribe(ignored -> log.log(System.Logger.Level.INFO,
                            "hop=client-send correlationId=" + correlationId))
                    .doOnNext(value -> log.log(System.Logger.Level.INFO,
                            "hop=client-reply correlationId=" + correlationId))
                    .doOnError(error -> log.log(System.Logger.Level.ERROR,
                            "hop=client-error correlationId=" + correlationId, error))
                    .doFinally(signal -> log.log(System.Logger.Level.INFO,
                            "hop=client-terminal correlationId=" + correlationId
                                    + " signal=" + signal));

            StepVerifier.create(reply)
                    .expectNext("found:order-42")
                    .expectComplete()
                    .verify(Duration.ofSeconds(5));
        }
        finally {
            requester.dispose();
            server.dispose();
        }
    }
}
~~~

The test uses a `correlationId|orderId` envelope payload to keep the example compact. In real applications, use typed DTOs or registered metadata MIME types. The expected outcome is client sends, server enters the handler, business processing finishes, client receives the reply, and both publishers complete. Logs sharing `correlationId` tie the hops together.

Run:

~~~bash
mvn test
~~~

Surefire output:

~~~text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
~~~

`LocalTransport` does not test ports, TLS, WebSocket upgrades, or network failures. Use this test to isolate protocol/requester/handler issues before running real transport tests.

## 12. Common Mistakes

| Symptom | Possible cause | Verification step |
|---|---|---|
| Producer log exists, requester never sends | Publisher not subscribed or filtered out | Check subscription, doFinally, and code branches |
| Client send exists, server has no handler | Connection, route, or responder mapping | Check setup/transport, route, and MIME metadata |
| Handler runs, service never runs | Reactive pipeline unsubscribed or conditional branch | Log inside Mono.defer and before calling service |
| Service finishes, client keeps waiting | Handler returns empty, encoding fails, or response unsent | Check terminal signals and server-side errors |
| Server replies, client never receives | Connection closed, timeout, cancellation, or decode | Compare client hooks, codecs, and connection logs |
| Fails only under load | Full queue, consumer lag, saturated scheduler, timeout | Check latency, backlog, threads, and retries |
| Message disappears after filter | Filter intentionally discarded it | Emit metrics/logs for discard paths |
| Same message appears multiple times | Redelivery, retry, or duplicate publish | Use idempotency key and log delivery/attempt |
| Trace stops across two services | Context not propagated | Check Reactor Context, tracing instrumentation, and transport metadata |

## 13. Operations Checklist

- Every operation has a cross-hop correlation ID; retries have separate attempt numbers.
- Logs distinguish created, subscribed, sent, handler-invoked, processed, replied, and consumed.
- Logs include route, interaction, service/instance, outcome, and duration.
- Metrics use low-cardinality tags; correlation ID is never a metric tag.
- Traces connect producer, messaging transport, handler, and downstream dependencies.
- Logs exist for filter/discard, retry, timeout, and dead-letter events.
- Sensitive payloads, tokens, and secret metadata never appear in logs.
- LocalTransport tests verify requester, route, handler, and codecs.
- Separate TCP/WebSocket tests verify production transport settings.
- All tests use bounded timeouts and clean up requesters/servers.
- Runbooks specify the last hop with evidence and the next investigative step.

## References

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — Messaging](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework API — RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)
- [Spring Framework API — RSocketMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html)
- [Spring Integration — Message History](https://docs.spring.io/spring-integration/reference/message-history.html)
- [Reactor Test — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
