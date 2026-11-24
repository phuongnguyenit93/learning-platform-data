# Heartbeats to Detect Dead Connections in Spring WebFlux

## 1. What is a heartbeat?

When an endpoint returns a long-lived HTTP stream, the server may not send business data for many seconds or minutes. During that quiet period, the client may have closed the tab, lost network connectivity, switched networks, turned off the device, or had the connection closed by a proxy. If upstream only emits events when business state changes, the server may perform no writes for a long time and detection of a broken connection is delayed.

A **heartbeat** is a small signal sent periodically while the stream is active. It helps:

- Generate periodic write activity on the connection.
- Help the server detect write failures when the client has disconnected.
- Help proxies/load balancers see traffic on the stream, avoiding unintended idle timeouts.
- Allow the client to track liveness if the heartbeat is represented as an event visible to the client.
- Provide an observation point to measure stream lifetime and detect abnormal connections.

In Spring WebFlux, heartbeats are typically generated with Reactor's **Flux.interval(...)** and merged with the business data publisher. With Server-Sent Events (SSE), a comment-only event is a good choice when the goal is keeping the stream active and detecting disconnects server-side without creating business messages for the JavaScript client.

A heartbeat is not absolute proof that the client application received and processed the data. It is a liveness signal at a specific connection layer. To confirm the client received or processed data, a separate acknowledgement mechanism is required.

## 2. Why does streaming need heartbeats?

A streaming response can stay open much longer than a typical request/response:

~~~text
Client opens HTTP stream
       |
       v
Server sends response headers
       |
       v
Stream stays open
       |
       +---- no business data for 30 seconds
       |
       +---- no business data for 2 minutes
       |
       +---- client may have disconnected
       |
       v
Server only notices a problem when the next write fails
~~~

Suppose the server only sends notifications when an order changes status. If the order does not change for 20 minutes, the publisher emits no new items. The connection may linger, yet the server performs no writes to detect that the client has vanished.

Spring Framework recommends sending periodic data when streaming responses, such as **text/event-stream** or **application/x-ndjson**, to detect client disconnects earlier. This data can be a comment-only SSE, an empty SSE event, or a no-op record that the client knows to ignore.

A heartbeat causes an extra write on the response. If the connection is already closed, the write can fail. The error or cancellation is then propagated back up the reactive chain so the publisher and related resources are cleaned up.

This is especially useful when upstream holds a subscription to Kafka, Redis Pub/Sub, a message broker, a database change feed, or another event source. When the client leaves, the application needs to cancel that subscription so it does not keep consuming resources for a recipient that no longer exists.

## 3. Distinguishing heartbeats across layers

Not every keep-alive mechanism has the same goal.

| Mechanism | Layer | Effect | Visible to JavaScript client? |
| --- | --- | --- | --- |
| SSE comment heartbeat | HTTP application payload | Creates periodic writes in the SSE response | Does not dispatch a message event |
| SSE named heartbeat event | HTTP application payload | Produces heartbeat data the client can handle | Yes, via addEventListener |
| NDJSON heartbeat record | HTTP application payload | Sends a no-op JSON record per NDJSON framing | Yes, client must parse and ignore |
| WebSocket Ping/Pong | WebSocket protocol | Checks peer responsiveness at the WebSocket layer | Usually handled by WebSocket implementation |
| HTTP/2 PING | HTTP/2 connection protocol | Checks connection state with PING/ACK | Not a business message |
| TCP keepalive | TCP transport | Probes peer at the TCP layer after OS-configured idle interval | No |

**SSE heartbeats and TCP keepalive do not replace each other.** TCP keepalive is a transport-layer probe, usually with a long OS-dependent interval and potentially disabled by default. A reverse proxy can also enforce an HTTP-layer idle timeout; a TCP probe does not necessarily count as new HTTP response payload.

HTTP/2 PING is an HTTP/2 connection mechanism. Reactor Netty can use PING/ACK to check connections when an appropriate idle timeout is configured. It does not replace application-layer heartbeats if the client needs a business signal or a proxy needs to see data on the response stream.

For SSE or NDJSON over HTTP, a heartbeat payload is the direct way to generate periodic write activity on the response stream itself.

## 4. SSE comment-only heartbeats

SSE has a simple text syntax. A typical event can include id, event, data, and a blank line ending the event:

~~~text
id: 42
event: order-update
data: {"orderId":"A-42","status":"SHIPPED"}

~~~

SSE also supports comments, with lines starting with a colon:

~~~text
:keep-alive

~~~

Comments are sent over the connection without generating a message event for EventSource listeners. This is a useful property of heartbeat comments: the server can emit a write without forcing the client to handle another business notification.

Spring provides **ServerSentEvent<T>** and a builder with the **comment(String)** method:

~~~java
ServerSentEvent<String> heartbeat =
    ServerSentEvent.<String>builder()
        .comment("keep-alive")
        .build();
~~~

To emit a periodic sequence of heartbeats:

~~~java
Flux<ServerSentEvent<String>> heartbeats =
    Flux.interval(Duration.ofSeconds(15))
        .map(tick -> ServerSentEvent.<String>builder()
            .comment("keep-alive")
            .build());
~~~

**Flux.interval** emits the first tick after the configured interval and continues periodically. Each tick is converted into an SSE comment.

There is no need to set data or id on a comment heartbeat. In particular, avoid incrementing the SSE event ID just for sending heartbeats; Last-Event-ID should represent data events that the client can replay, not keep-alives.

## 5. Client-visible event heartbeats

Sometimes the client application also needs to know the server is still sending heartbeats. In that case, use a named SSE event with data:

~~~java
ServerSentEvent<String> heartbeat =
    ServerSentEvent.<String>builder("alive")
        .event("heartbeat")
        .build();
~~~

Wire format looks like:

~~~text
event: heartbeat
data: alive

~~~

JavaScript can listen for it:

~~~javascript
const source = new EventSource("/api/orders/A-42/events");
let lastHeartbeatAt = Date.now();

source.addEventListener("heartbeat", () => {
    lastHeartbeatAt = Date.now();
});

source.addEventListener("order-update", event => {
    const update = JSON.parse(event.data);
    renderOrder(update);
});

source.onerror = () => {
    console.log("SSE connection interrupted; EventSource may reconnect");
};
~~~

**EventSource** does not fire message callbacks for comment-only heartbeats. If you need a client watchdog, use a named heartbeat event or another mechanism observable by the client.

You can choose between two separate goals:

- **Server-side disconnect detection:** comment-only heartbeats are usually sufficient.
- **Client-side liveness watchdog:** named heartbeat events let JavaScript update the timestamp of the latest heartbeat.

SSE is a unidirectional server-to-client protocol. A named heartbeat event still does not prove the client successfully processed business data; if confirmation is required, the client must send an acknowledgement via a separate request or use a bidirectional protocol such as WebSocket.

## 6. How to choose the heartbeat interval?

There is no single interval suitable for every system. Start from the shortest timeout among components along the path:

- Browser or client application.
- Reverse proxy / ingress.
- Load balancer.
- API gateway or CDN.
- Firewall/NAT.
- HTTP server and transport.
- Application timeout policy.

Heartbeats must arrive before the shortest idle timeout with margin for scheduler jitter, system load, and network latency.

For example, if a proxy closes streams after 60 seconds without payload, you can start by testing a 15–20 second heartbeat. This is only a starting point; measure on real infrastructure and tune to actual timeouts.

| Shortest idle timeout | Trial heartbeat interval | Notes |
| --- | --- | --- |
| 30 seconds | 8–10 seconds | Leave clear margin |
| 60 seconds | 15–20 seconds | Common example for HTTP streams |
| 120 seconds | 30–40 seconds | Also verify client and proxy timeouts |
| Unknown | Measure actual timeouts first | Do not pick an arbitrary value and assume it is guaranteed |

A memorable starting rule of thumb is setting the heartbeat well below the shortest idle timeout, such as roughly one-third of that timeout. This is an initial design heuristic, not a requirement of HTTP or Spring.

Balance three factors:

1. **Disconnect detection:** shorter intervals make failed writes happen sooner.
2. **Overhead:** every connection receives extra heartbeats; tens of thousands of connections generate notable write and scheduler activity.
3. **Intermediate timeouts:** heartbeats must arrive early enough so proxies or load balancers do not close the stream.

Do not set the interval overly short just to feel safe. Measure concurrent connections, heartbeats per second, CPU, network writes, and streams closed by timeouts.

## 7. Merging heartbeats with the business data stream

A simple approach for long-lived data sources:

~~~java
Flux<ServerSentEvent<OrderUpdate>> dataEvents =
    service.events(orderId)
        .map(update -> ServerSentEvent.<OrderUpdate>builder(update)
            .event("order-update")
            .build());

Flux<ServerSentEvent<OrderUpdate>> heartbeats =
    Flux.interval(Duration.ofSeconds(15))
        .map(tick -> ServerSentEvent.<OrderUpdate>builder()
            .comment("keep-alive")
            .build());

return Flux.merge(dataEvents, heartbeats);
~~~

**Flux.merge** allows business events and heartbeats to be emitted together to the response. When the business data source is silent, heartbeats still generate periodic writes.

**Note on finite sources:** **Flux.interval** is a publisher that never completes on its own. If merged with a finite business source via **Flux.merge**, the response will stay open after the business source completes because heartbeats keep running. The simple approach above fits endpoints designed as long-lived streams that end when the client disconnects or the application cancels the stream.

If the business source can complete normally, tie the heartbeat lifecycle to the source lifecycle. The example below shares a single source subscription using **publish**, then uses the source completion signal to stop the timer:

~~~java
public final class HeartbeatStreams {
    private HeartbeatStreams() {
    }

    public static <T> Flux<ServerSentEvent<T>> withHeartbeat(
            Flux<T> source,
            Duration interval) {

        return source.publish(shared -> {
            Flux<ServerSentEvent<T>> data = shared.map(value ->
                ServerSentEvent.<T>builder(value)
                    .event("update")
                    .build()
            );

            Mono<Boolean> sourceCompleted =
                shared.then(Mono.just(Boolean.TRUE));

            Flux<ServerSentEvent<T>> heartbeat =
                Flux.interval(interval)
                    .onBackpressureDrop()
                    .map(tick ->
                        ServerSentEvent.<T>builder()
                            .comment("keep-alive")
                            .build()
                    )
                    .takeUntilOther(sourceCompleted);

            return Flux.merge(data, heartbeat);
        });
    }
}
~~~

Here:

- **publish** shares the same subscription to source between the data branch and the completion-tracking branch.
- **sourceCompleted** emits true only when the business source completes normally.
- **takeUntilOther** stops the heartbeat timer when the source completes.
- **Flux.merge** completes once both the data branch and heartbeat branch have completed.
- If downstream cancels the stream, cancellation propagates back through both branches to the shared source.

**onBackpressureDrop()** fits heartbeat ticks because heartbeats are auxiliary signals. If a client is slow and has no demand, dropping a tick is better than accumulating a heartbeat queue. Do not apply a similar drop policy to business events if losing data is unacceptable.

If the business source is an infinite stream, sourceCompleted never emits and heartbeats continue until the client disconnects or upstream terminates with an error. If the source emits an error, the error propagates downstream and the timer is cancelled along with the stream.

## 8. Distinguishing heartbeats from business data timeouts

A heartbeat answers the question: “Can we still write data over the response stream?” It does not necessarily answer the question: “Is the business source still emitting events?”

For example, a stock ticker feed may have no price changes for a period. Heartbeats continue steadily while business data has no new events. That can be completely normal.

If business rules define no events for 2 minutes as abnormal, place a timeout on the business data publisher before merging heartbeats:

~~~java
Flux<Quote> quotes =
    quoteService.stream(symbol)
        .timeout(Duration.ofMinutes(2));

return HeartbeatStreams.withHeartbeat(
    quotes,
    Duration.ofSeconds(15)
);
~~~

Here heartbeats do not mask silence from the quote source because **timeout** is placed on **quotes** before heartbeats are added.

If **timeout** were placed on the already-merged stream, every heartbeat would reset the inactivity timer. The timeout would then only measure time without any frame, no longer time without business data.

Name metrics separately for the two durations:

- **time_since_last_heartbeat**: time since the last heartbeat.
- **time_since_last_business_event**: time since the last business event.

The two metrics answer two different operational questions.

## 9. NDJSON heartbeats: use a clearly typed record

NDJSON has no comment syntax like SSE. Every line must be an independent JSON document. Do not insert **:keep-alive** lines into an NDJSON stream because it would no longer be valid JSON.

One approach is using an envelope with a type field:

~~~java
public record StreamFrame(
    String type,
    Object payload,
    Instant sentAt
) {
    public static StreamFrame heartbeat() {
        return new StreamFrame("heartbeat", null, Instant.now());
    }

    public static StreamFrame data(Object payload) {
        return new StreamFrame("data", payload, Instant.now());
    }
}
~~~

Publisher:

~~~java
Flux<StreamFrame> frames = Flux.merge(
    service.events(orderId).map(StreamFrame::data),
    Flux.interval(Duration.ofSeconds(15))
        .onBackpressureDrop()
        .map(tick -> StreamFrame.heartbeat())
);
~~~

The response uses the **application/x-ndjson** media type. Lines can look like:

~~~json
{"type":"heartbeat","payload":null,"sentAt":"2026-11-08T02:00:15Z"}
{"type":"heartbeat","payload":null,"sentAt":"2026-11-08T02:00:30Z"}
{"type":"data","payload":{"orderId":"A-42","status":"SHIPPED"},"sentAt":"2026-11-08T02:00:31Z"}
~~~

The client parses each line and ignores frames whose type is heartbeat. Do not mix JSON records with unframed plain text lines.

Like SSE, if the NDJSON source is finite, tie the heartbeat lifecycle to the source or explicitly accept that the endpoint will remain open after data finishes.

## 10. WebSocket heartbeats and acknowledgements

WebSocket is a bidirectional connection. In addition to application-defined message heartbeats, the WebSocket protocol has Ping and Pong control frames.

- Ping is sent to check the peer.
- The peer replies with Pong per the WebSocket protocol.
- Server or client can use timeouts to mark a connection unresponsive.
- STOMP over WebSocket and SockJS have their own protocol-level heartbeat mechanisms.

This differs from SSE comments: SSE comments only flow from server to client and do not ask the client to send an ACK.

If the system needs the server to know the client can still respond, WebSocket Ping/Pong or application-level acknowledgements are more suitable. If you only need periodic write activity on an HTTP stream to detect disconnects on write, SSE comments are usually simpler.

Do not send the string "ping" inside a WebSocket data frame and call it a protocol Ping. Data frames and control Ping frames are two different frame types.

## 11. Detecting client disconnects and cleaning up publishers

When a client closes the connection, the server can detect the problem on the next write. Depending on the server adapter and disconnect timing, the reactive chain can end with an error or a cancellation.

Therefore, do not assume every disconnect appears as a single exception type or solely as CANCEL. Use **doFinally** to observe all terminal signals:

~~~java
return HeartbeatStreams.withHeartbeat(
        service.events(orderId),
        Duration.ofSeconds(15))
    .doFinally(signal -> {
        log.info("Stream {} terminated with {}",
            orderId, signal);
    });
~~~

**SignalType** can be:

- **ON_COMPLETE**: publisher completed normally.
- **ON_ERROR**: publisher terminated with an error.
- **CANCEL**: downstream cancelled the subscription.

If you only want to count cancellations:

~~~java
.doOnCancel(() ->
    log.info("Client cancelled stream for {}", orderId))
~~~

If resources must be cleaned up regardless of outcome, **doFinally** is a suitable place for simple cleanup. For asynchronous resources such as broker sessions, external system subscriptions, or resources with reactive close operations, consider **usingWhen** for lifecycle-bound cleanup and explicit cleanup error handling.

Example event source requiring cleanup:

~~~java
Flux<OrderUpdate> updates =
    Flux.usingWhen(
        eventClient.openSubscription(orderId),
        subscription -> subscription.events(),
        subscription -> subscription.close(),
        (subscription, error) -> subscription.close(),
        subscription -> subscription.close()
    );
~~~

This is an illustrative pattern; **eventClient** and subscription types are defined by the application. **usingWhen** binds cleanup to complete, error, and cancel. Do not hold a global per-client subscription if it must be released when the client leaves the stream.

### 11.1. Do not swallow response write errors

Avoid handling all errors by returning a fallback response:

~~~java
return stream
    .onErrorResume(error -> Flux.empty());
~~~

If the response has already started writing, switching to an empty publisher cannot make the client receive a new status or headers. It can also hide why the stream was interrupted.

Classify errors properly:

- Client disconnect / write failure: record appropriate metrics and clean up subscriptions.
- Data source error: record and apply business retry/fallback policies.
- Programming error: let the error handler record and handle it properly.
- Cancellation due to client closing the stream: clean up, do not try to write more body to a closed connection.

## 12. Proxies, load balancers, and response buffering

Heartbeats only help if bytes are actually pushed out of the application frequently enough. Intermediate components may buffer responses, compress data, or apply their own idle timeouts.

When deploying streaming through a reverse proxy:

1. Disable or configure buffering appropriately for SSE/NDJSON endpoints.
2. Verify the proxy flushes each event/chunk.
3. Set idle timeouts higher than the heartbeat interval with safety margin.
4. Check timeouts across ingress, load balancers, and CDNs.
5. Verify whether compression delays flushing small payloads.
6. Test across the real production network path, not just localhost.

With Nginx, SSE endpoints often need **proxy_buffering off;**. The **X-Accel-Buffering: no** header can be used if the Nginx architecture permits. Exact configuration names depend on the reverse proxy; there is no single setting for all gateways.

Spring WebFlux writes and flushes data according to the codec/media type. For SSE, the framework processes each event to avoid waiting to buffer the entire stream. However, external proxies or middleware can still buffer, so end-to-end testing is mandatory.

A heartbeat generated in Reactor that sits inside a proxy buffer does not show network activity to the client or intermediaries. Verify using **curl -N** or a real streaming client through the exact ingress users will traverse.

## 13. Reactor Netty idle timeout and HTTP/2 PING

Reactor Netty provides timeouts at the transport/server layer:

- **idleTimeout** limits how long a connection can remain inactive per server configuration.
- With HTTP/2, Reactor Netty supports PING/ACK to check peers when idle timeout and PING parameters are configured.
- Without an appropriate idle timeout configured, HTTP/2 PING health checks may not trigger as expected.

HTTP/2 PING checks the connection at the HTTP/2 layer. One HTTP/2 connection can carry many streams; PING does not replace application-level per-stream heartbeats if the client needs heartbeat events or business state updates.

TCP keepalive is a different mechanism. Reactor Netty notes that **SO_KEEPALIVE** is not enabled by default in all configurations and probe intervals usually depend on the OS. Do not rely on TCP keepalive to satisfy a short HTTP idle timeout such as 30 or 60 seconds.

Choose the right layer:

| Goal | Mechanism to consider |
| --- | --- |
| Keep SSE response active with payload writes | SSE comment heartbeat |
| JavaScript client needs to observe heartbeats | Named SSE heartbeat event |
| JSON record stream | NDJSON heartbeat envelope |
| Check WebSocket peer | WebSocket Ping/Pong or STOMP heartbeat |
| Check HTTP/2 connection | Transport HTTP/2 PING/ACK |
| Detect long-lived TCP connection failures | TCP keepalive and transport timeouts |

## 14. Backpressure and load with many clients

Each client stream may have its own heartbeat publisher. With thousands or tens of thousands of connections, heartbeats generate significant periodic write volume.

Suppose there are 10,000 connections and each sends a heartbeat every 15 seconds. On average, the server generates roughly 667 heartbeats per second, excluding business events and network overhead. As client count grows, measure:

- Heartbeats emitted per second.
- Active stream count.
- Pending writes and write duration.
- Disconnects, errors, and cancellations.
- Scheduler queues and CPU.
- Downstream buffers/backpressure.
- Upstream resources such as broker subscriptions.

Heartbeats are not business data, so they can be dropped when downstream has no demand. Do not buffer heartbeats unboundedly; stale heartbeats have no value when a new tick is about to arrive.

Conversely, do not drop business events if the system must guarantee every event is delivered. Separate the heartbeat backpressure policy from the data event policy.

Avoid creating a dedicated scheduler per client. **Flux.interval** uses Reactor's default scheduler; if a custom scheduler is needed, manage its lifecycle and thread limits explicitly.

## 15. Client watchdog and reconnect

If using comment-only SSE, JavaScript receives no event callback for heartbeats. If the client needs a watchdog, emit named heartbeat events and update a timestamp upon receipt:

~~~javascript
const source = new EventSource("/api/orders/A-42/events");
let lastHeartbeatAt = Date.now();

source.addEventListener("heartbeat", () => {
    lastHeartbeatAt = Date.now();
});

source.addEventListener("order-update", event => {
    const update = JSON.parse(event.data);
    renderOrder(update);
});

const watchdog = setInterval(() => {
    const silentFor = Date.now() - lastHeartbeatAt;

    if (silentFor > 45000) {
        console.warn("No heartbeat received recently");
    }
}, 5000);
~~~

This example only illustrates a client-side watchdog. In a real application, clear the timer when closing EventSource and account for timer throttling in background browser tabs.

**EventSource** automatically reconnects when the connection is interrupted according to browser policy. The **retry** field in SSE can suggest how long to wait before reconnecting; it is **not a heartbeat interval**.

If events must be replayed after reconnecting:

- Assign stable IDs to business events.
- Have the server read Last-Event-ID and resume from the right position.
- Do not assign new IDs to comment heartbeats.
- Keep replay/idempotency policies clear so duplicate events are not re-processed.

Do not treat reconnect as a guarantee against data loss. The server must store or reconstruct events by ID if the contract requires replay.

## 16. Complete Java 17+ Spring Boot WebFlux demo

The demo creates an SSE endpoint for an order. A simulated business source emits only one update every 45 seconds; comment heartbeats are emitted every 15 seconds. When the client disconnects, cancellation or write errors flow through the reactive chain and are observed with **doFinally**.

### 16.1. Project structure

~~~text
webflux-heartbeat-demo/
  build.gradle
  src/
    main/java/demo/
      DemoApplication.java
      OrderUpdate.java
      OrderEventService.java
      HeartbeatStreams.java
      OrderStreamController.java
    test/java/demo/
      HeartbeatStreamsTest.java
~~~

### 16.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot manages compatible Spring Framework and Reactor versions through dependency management. There is no need to manually pin a different Reactor version without a specific requirement.

### 16.3. DemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 16.4. OrderUpdate.java

~~~java
package demo;

import java.time.Instant;

public record OrderUpdate(
    String orderId,
    long sequence,
    String status,
    Instant occurredAt
) {
}
~~~

Record representing a business event. sequence can serve as the SSE ID in the demo; real systems should use a stable ID from an event store or data source.

### 16.5. OrderEventService.java

~~~java
package demo;

import java.time.Duration;
import java.time.Instant;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class OrderEventService {

    public Flux<OrderUpdate> stream(String orderId) {
        // Demo: simulate a business change every 45 seconds.
        return Flux.interval(Duration.ofSeconds(45))
            .map(sequence -> new OrderUpdate(
                orderId,
                sequence + 1,
                "PROCESSING",
                Instant.now()
            ));
    }
}
~~~

In a real application, replace the simulated Flux.interval with a publisher from Kafka, Redis Pub/Sub, a database change stream, or an event service. Do not use a simulated timer as a business source in production.

### 16.6. HeartbeatStreams.java

~~~java
package demo;

import java.time.Duration;
import org.springframework.http.codec.ServerSentEvent;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class HeartbeatStreams {
    private HeartbeatStreams() {
    }

    public static <T> Flux<ServerSentEvent<T>> withHeartbeat(
            Flux<T> source,
            Duration interval) {

        return source.publish(shared -> {
            Flux<ServerSentEvent<T>> data = shared.map(value ->
                ServerSentEvent.<T>builder(value)
                    .event("order-update")
                    .build()
            );

            Mono<Boolean> sourceCompleted =
                shared.then(Mono.just(Boolean.TRUE));

            Flux<ServerSentEvent<T>> heartbeat =
                Flux.interval(interval)
                    .onBackpressureDrop()
                    .map(tick ->
                        ServerSentEvent.<T>builder()
                            .comment("keep-alive")
                            .build()
                    )
                    .takeUntilOther(sourceCompleted);

            return Flux.merge(data, heartbeat);
        });
    }
}
~~~

The method uses publish to share a single subscription to the source. The completion-tracking branch stops the timer when a finite source completes. For an infinite source, the timer only stops when downstream cancels or the source terminates with an error.

### 16.7. OrderStreamController.java

~~~java
package demo;

import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

@RestController
public class OrderStreamController {
    private static final Logger log =
        LoggerFactory.getLogger(OrderStreamController.class);

    private static final Duration HEARTBEAT_INTERVAL =
        Duration.ofSeconds(15);

    private final OrderEventService service;

    public OrderStreamController(OrderEventService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/api/orders/{orderId}/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<OrderUpdate>> events(
            @PathVariable String orderId) {

        return HeartbeatStreams.withHeartbeat(
                service.stream(orderId),
                HEARTBEAT_INTERVAL
            )
            .doFinally((SignalType signal) ->
                log.info("Order stream {} ended with {}",
                    orderId, signal));
    }
}
~~~

The endpoint returns text/event-stream. While there are no updates yet, the client still receives comment heartbeats. When the source emits an update, the client receives an order-update event. doFinally observes complete, error, and cancel.

### 16.8. HeartbeatStreamsTest.java

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class HeartbeatStreamsTest {

    @Test
    void emitsHeartbeatWhenBusinessSourceIsQuiet() {
        StepVerifier.withVirtualTime(() ->
                HeartbeatStreams.withHeartbeat(
                    Flux.<String>never(),
                    Duration.ofSeconds(10)
                ))
            .thenAwait(Duration.ofSeconds(10))
            .expectNextMatches(event ->
                "keep-alive".equals(event.comment())
                    && event.data() == null)
            .thenCancel()
            .verify();
    }

    @Test
    void finiteSourceCompletionStopsHeartbeat() {
        StepVerifier.withVirtualTime(() ->
                HeartbeatStreams.withHeartbeat(
                    Flux.just("completed"),
                    Duration.ofSeconds(10)
                ))
            .expectNextMatches(event ->
                "order-update".equals(event.event())
                    && "completed".equals(event.data()))
            .verifyComplete();
    }

    @Test
    void cancellationPropagatesToBusinessSource() {
        AtomicBoolean cancelled = new AtomicBoolean();

        Flux<String> source =
            Flux.<String>never()
                .doOnCancel(() -> cancelled.set(true));

        StepVerifier.withVirtualTime(() ->
                HeartbeatStreams.withHeartbeat(
                    source,
                    Duration.ofSeconds(10)
                ))
            .thenAwait(Duration.ofSeconds(10))
            .expectNextMatches(event ->
                "keep-alive".equals(event.comment()))
            .thenCancel()
            .verify();

        assertTrue(cancelled.get());
    }

    @Test
    void sourceEventCarriesItsBusinessData() {
        OrderUpdate update = new OrderUpdate(
            "A-42",
            7,
            "SHIPPED",
            Instant.parse("2026-11-08T02:00:00Z")
        );

        StepVerifier.withVirtualTime(() ->
                HeartbeatStreams.withHeartbeat(
                    Flux.just(update),
                    Duration.ofSeconds(10)
                ))
            .expectNextMatches(event ->
                "order-update".equals(event.event())
                    && update.equals(event.data()))
            .verifyComplete();
    }
}
~~~

The tests use Reactor's virtual time so they do not have to wait a real 10 seconds. They verify that heartbeats appear when the source is silent, the timer stops when a finite source completes, and cancellation propagates back to the source.

### 16.9. Running the application

In the project directory:

~~~bash
./gradlew bootRun
~~~

Or if Gradle is installed:

~~~bash
gradle bootRun
~~~

Open the stream:

~~~bash
curl -N -i http://localhost:8080/api/orders/A-42/events
~~~

During the roughly 45 seconds before the first business update, the response contains heartbeat comments spaced about 15 seconds apart:

~~~text
:keep-alive

:keep-alive

event: order-update
data: {"orderId":"A-42","sequence":1,"status":"PROCESSING","occurredAt":"..."}

~~~

The ellipsis represents the runtime-dependent timestamp. Comment heartbeats are not dispatched as message events by JavaScript EventSource.

Stop curl with Ctrl+C to cancel the client stream. The server detects the disconnect on the next write or when the transport reports the connection closed; doFinally logs the corresponding terminal signal.

Run the tests:

~~~bash
./gradlew test
~~~

No Thread.sleep is needed in tests. Virtual time allows deterministic testing of heartbeat intervals and cancellation.

## 17. Testing streaming via WebTestClient

Beyond unit tests for the publisher, WebTestClient can verify that the endpoint declares the right media type and the stream reads properly as SSE:

~~~java
var result = client.get()
    .uri("/api/orders/A-42/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
    .contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
    .returnResult(
        new ParameterizedTypeReference<ServerSentEvent<OrderUpdate>>() {}
    );

StepVerifier.create(result.getResponseBody())
    .expectNextMatches(event ->
        "keep-alive".equals(event.comment()))
    .thenCancel()
    .verify(Duration.ofSeconds(20));
~~~

This is an integration test pattern requiring WebTestClient, ParameterizedTypeReference, ServerSentEvent, and StepVerifier. In real tests, configure a shorter heartbeat interval, such as one second, to avoid waiting 15 seconds. After receiving an event, thenCancel closes the stream and checks cancellation.

Do not use expectBodyList on an infinite SSE stream because the test would wait for the body to complete. Use returnResult to obtain the response body publisher and consume a deliberate number of events.

## 18. Observing heartbeats in production

Record metrics and logs per stream lifecycle, rather than logging every heartbeat at INFO level for every connection under high traffic.

Useful metrics:

| Metric | Meaning |
| --- | --- |
| active_streams | Number of currently open streams |
| heartbeat_sent_total | Total heartbeats emitted |
| stream_disconnect_total | Streams terminated by disconnect/write failure |
| stream_cancel_total | Streams that received cancellation |
| stream_error_total | Streams terminated by error |
| stream_duration_seconds | Stream lifetime duration |
| time_since_last_business_event | Time since the last business event |
| time_since_last_heartbeat | Time since the last heartbeat |

Do not treat every ON_ERROR as a client disconnect. Errors can come from upstream, serialization, timeouts, bugs, or transport. Classify exceptions and record separate metrics where possible.

With thousands of clients, do not emit an INFO log for each heartbeat. Log when streams open/close, on errors, or when anomalies are detected; use counters/histograms for normal heartbeats.

## 19. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Sending data only when business state changes | Connections can sit silent too long and disconnects are detected late | Send periodic heartbeats |
| Using heartbeat comments expecting JavaScript to receive messages | EventSource ignores comments in event dispatch | Use named heartbeat events if the client needs a watchdog |
| Using SSE comments in NDJSON | Lines are no longer valid JSON | Use a JSON envelope with type=heartbeat |
| Merging infinite Flux.interval with a finite source via merge | Response never completes when the data source finishes | Stop the timer upon source completion or omit heartbeats if unnecessary |
| Not cancelling upstream when client leaves | Subscriptions to brokers/services hold onto resources | Observe doFinally, use usingWhen for async cleanup |
| Catching only cancellation | Some disconnects surface as write errors | Observe complete/error/cancel with doFinally and classify errors |
| Assuming heartbeats prove the client processed messages | Confusing write liveness with application acknowledgement | Use separate acknowledgements if confirmation is needed |
| Choosing a heartbeat longer than proxy idle timeout | Proxy closes the stream before the next heartbeat | Set interval lower than the shortest timeout with safety margin |
| Proxy buffers responses | Heartbeats do not reach the client on time | Disable or tune buffering, verify flushing through ingress |
| Using TCP keepalive instead of HTTP heartbeats | TCP probes may not refresh HTTP idle timers | Use application heartbeats for SSE/NDJSON |
| Putting timeout after merging heartbeats | Heartbeats reset the timer and hide business source silence | Place timeout on the business publisher before merging |
| Buffering heartbeats unboundedly | Increases memory and sends stale, useless heartbeats | Drop heartbeat ticks when downstream is slow |
| Dropping business events to reduce load | Loss of important data | Drop only heartbeats; choose separate backpressure policies for data events |
| Assigning event IDs to heartbeats | Changes Last-Event-ID unnecessarily | Assign IDs only to replayable business events |
| Logging every heartbeat at INFO | Log volume explodes with client count | Use metrics; log open/close and errors |
| Using Thread.sleep to generate heartbeats | Blocks threads and breaks the reactive pipeline | Use Flux.interval |
| Calling subscribe separately for heartbeats | Lifecycle detaches from response and complicates cleanup | Merge publishers and return a single Flux |
| Using one global publisher for all clients without understanding sharing | Clients may share lifecycles or data unintentionally | Create publishers per subscription and manage fan-out explicitly |

## 20. Heartbeat design checklist

Before deploying a stream to production, determine:

1. Does the stream use SSE, NDJSON, WebSocket, or another protocol?
2. Are heartbeats only for server-side disconnect detection or must the client observe them too?
3. What is the shortest idle timeout among proxies, load balancers, gateways, and servers?
4. Is the heartbeat interval short enough with safety margin?
5. Does the response truly flush through the entire proxy chain?
6. If a finite source completes, does the heartbeat timer stop?
7. If the client disconnects, is the upstream subscription cancelled/cleaned up?
8. How are response write errors distinguished from business errors?
9. Are heartbeats dropped when downstream is slow instead of accumulating unboundedly?
10. Are business events unaffected by the heartbeat backpressure policy?
11. Does the client need named heartbeat events or a watchdog?
12. Does reconnect use event IDs/Last-Event-ID for replay?
13. Are there metrics for active streams, heartbeats, errors, cancels, and duration?
14. Has it been tested through real reverse proxies/ingress?

| Need | Choice |
| --- | --- |
| SSE server-side keep-alive | Comment-only ServerSentEvent.comment(...) |
| SSE client watchdog | Named heartbeat event with data |
| NDJSON keep-alive | JSON envelope type=heartbeat |
| Finite source | Stop timer when source completes |
| Long-lived source | Timer runs until cancel/error/complete |
| Subscription cleanup | doFinally, usingWhen |
| Non-blocking timer | Flux.interval |
| Drop heartbeats on slow client | onBackpressureDrop |
| Business data timeout | timeout before merging heartbeats |
| WebSocket peer liveness | Ping/Pong or STOMP heartbeat |
| HTTP/2 connection health | Transport-level PING/ACK |
| Client reconnect/replay | SSE retry and Last-Event-ID |

## 21. Self-check questions with answers

**Question 1.** Why does a WebFlux stream need to send heartbeats when there are no business events?

**Answer:** To generate periodic writes, helping detect disconnects sooner and preventing intermediaries from closing the stream due to idle timeouts.

**Question 2.** Does an SSE comment-only heartbeat trigger onmessage in EventSource?

**Answer:** No. Comments are ignored in event dispatch; they are still data transmitted over the response stream.

**Question 3.** If JavaScript needs to know the most recent heartbeat, which form should be used?

**Answer:** A named SSE event like event: heartbeat with data, listened to via addEventListener("heartbeat", ...).

**Question 4.** Why does TCP keepalive not replace SSE heartbeats?

**Answer:** TCP keepalive operates at the transport layer, typically with different intervals and configuration. It does not necessarily refresh HTTP idle timeouts or deliver events to the client.

**Question 5.** Does Flux.interval complete naturally?

**Answer:** No. It continues emitting ticks until cancelled or terminated by an error. Thus, when merged with a finite source, the timer must be stopped according to the source lifecycle.

**Question 6.** Why does the example use publish when the data source can complete?

**Answer:** publish shares a single subscription between the data branch and the completion-tracking branch, avoiding subscribing to the source twice to detect completion and stop heartbeats.

**Question 7.** How does doFinally differ from doOnCancel?

**Answer:** doFinally runs on complete, error, or cancel and receives SignalType; doOnCancel only observes cancellation.

**Question 8.** Should timeout be placed on a stream already merged with heartbeats to detect business source silence?

**Answer:** No. Heartbeats will reset the inactivity timer. Place timeout on the business publisher before merging heartbeats.

**Question 9.** Can NDJSON use :keep-alive comments like SSE?

**Answer:** No. NDJSON requires every line to be a JSON document; use a record envelope with type=heartbeat.

**Question 10.** If a response is buffered by a proxy, are heartbeats effective?

**Answer:** They may not reach the client on time. Configure proxy flushing/buffering properly and test end-to-end.

**Question 11.** Does a heartbeat comment prove the client processed business events?

**Answer:** No. It only creates periodic write payloads. Confirming client processing requires separate acknowledgements or a bidirectional protocol.

**Question 12.** If a client is slow, should delayed heartbeats be buffered unboundedly?

**Answer:** No. Old heartbeats are no longer useful; heartbeat ticks can be dropped when downstream lacks demand, while business events must have their own backpressure policy.

## 22. Takeaways and official documentation

- A heartbeat is a small signal sent periodically in long-lived streams to generate write activity and detect disconnects earlier.
- For SSE, comment-only heartbeats are clean because they do not generate message events for EventSource.
- If JavaScript needs a watchdog, use a named heartbeat event with data.
- For NDJSON, use a JSON record with a heartbeat type; do not use SSE comments.
- Choose the interval based on the shortest idle timeout of proxies, load balancers, gateways, and servers, with margin.
- Flux.interval does not complete on its own; bind the timer to the source lifecycle if the source can be finite.
- publish can share a single upstream subscription when you need both to emit data and track source completion.
- doFinally observes complete/error/cancel; subscription cleanup must be bound to the reactive lifecycle.
- Timeouts on the business publisher must be placed before merging heartbeats if you want to detect silent business sources.
- TCP keepalive, HTTP/2 PING, SSE comments, and WebSocket Ping/Pong operate at different layers.
- Heartbeats do not replace acknowledgements when confirmation of client data processing is required.

Official documentation:

1. [Spring Framework Reference — Reactive Core: Streaming](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): recommends sending periodic data for text/event-stream and application/x-ndjson to detect client disconnects; describes comment-only SSE and no-op heartbeats.
2. [Spring Framework Javadoc — ServerSentEvent.Builder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/ServerSentEvent.Builder.html): comment, event, id, retry, and data APIs.
3. [Spring Framework Reference — WebFlux Controller Return Types](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): returning Flux and ServerSentEvent from controllers.
4. [Project Reactor Reference — Handling Errors and doFinally](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): terminal signals, cancellation, and cleanup.
5. [Project Reactor Javadoc — Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): interval, publish, merge, takeUntilOther, onBackpressureDrop, and doFinally.
6. [Reactor Netty Reference — HTTP Server](https://projectreactor.io/docs/netty/release/reference/http-server.html): server idle timeout and HTTP/2 PING/ACK health check.
7. [Reactor Netty Reference — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html): TCP keepalive and HTTP/2 connection health check.
8. [Spring Framework Reference — WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket.html): choosing WebSocket for bidirectional communication.
