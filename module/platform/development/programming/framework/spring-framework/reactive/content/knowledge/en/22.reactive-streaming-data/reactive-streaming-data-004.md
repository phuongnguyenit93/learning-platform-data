# Media Type text/event-stream, id, event, and retry in Spring WebFlux

## 1. What are Server-Sent Events used for?

**Server-Sent Events (SSE)** is an HTTP mechanism allowing a server to continuously send data to the browser over an open response connection. The client opens a GET request; the server responds with the **text/event-stream** media type and writes events as they become ready. The browser can receive each event as soon as it is flushed, without continuous polling.

SSE is suitable for:

- Processing progress of a long-running task.
- Order or running workflow status.
- Notifications and dashboard updates.
- Price boards, metrics, or system status changing over time.
- Unidirectional logs/notifications from server to client.

SSE is **unidirectional server → client** communication. The client still sends commands, filters, or actions via separate HTTP requests. If continuous bidirectional communication is needed, consider WebSocket or another suitable protocol.

In Spring WebFlux, a handler can return **Flux<ServerSentEvent<T>>**. The framework uses **ServerSentEventHttpMessageWriter** to encode each event into SSE format and write it as a reactive stream.

A minimal endpoint:

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(sequence -> ServerSentEvent.builder(
                "update-" + sequence
            )
            .build());
}
~~~

This snippet requires importing Reactor, Spring WebFlux, and Duration. For each element of the Flux, WebFlux writes one event. As long as the Flux has not completed, the response stays open to send new data.

## 2. Media type text/event-stream and wire format

SSE uses the **text/event-stream** media type and UTF-8 encoded content. An event consists of field lines, ending with a blank line. The blank line signals the client to dispatch the event.

Example:

~~~text
id: 42
event: progress
retry: 3000
data: {"percent":75,"message":"Processing"}

~~~

Meaning:

- **id**: event identifier, recorded by the browser as the last event ID.
- **event**: event name; the client can register listeners for this name.
- **retry**: wait duration before reconnecting, in milliseconds.
- **data**: event payload. The payload can be plain text or serialized JSON.

An event can contain only data:

~~~text
data: Hello

~~~

When there is no event field, the default event type on the browser side is **message**.

An event can also have multiple data lines:

~~~text
data: First line
data: Second line
data: Third line

~~~

The browser joins data lines with newline characters before placing the content into event.data. If data is JSON, serialize it into a valid JSON document; the client parses it with JSON.parse.

### 2.1. Standard fields

| Field | Purpose | Example |
| --- | --- | --- |
| **data** | Event content | data: {"status":"running"} |
| **event** | Event type name | event: progress |
| **id** | Event ID used when reconnecting | id: 105 |
| **retry** | Reconnect wait interval, milliseconds | retry: 3000 |
| **comment** | Comment line, does not dispatch an event | : heartbeat |

Field names are written in lowercase as specified by the protocol. Unknown fields are ignored by the client.

### 2.2. Blank line as event boundary

Each event must end with a blank line. If the server sends only data lines without a blank line, the browser may not dispatch that event yet. Therefore, when constructing SSE manually, you must terminate the event properly.

When using **ServerSentEvent** in WebFlux, the message writer is responsible for serializing fields and delimiters. Do not manually concatenate SSE strings into a single String without a special reason; using the builder helps avoid formatting bugs and supports object encoding.

### 2.3. Comments and heartbeats

A line starting with a colon is a comment:

~~~text
: heartbeat

~~~

The browser ignores comments, so they do not generate message events. The server can send periodic comments to keep the connection alive when the stream has little data and prevent proxies/load balancers from closing idle connections.

In Spring:

~~~java
ServerSentEvent.<String>builder()
    .comment("heartbeat")
    .build();
~~~

You can merge heartbeats into the stream using a scheduled Flux. The heartbeat interval must be shorter than the idle timeout of proxies/servers along the path. Do not send heartbeats too frequently, as this creates unnecessary traffic and work.

## 3. ServerSentEvent<T> in Spring WebFlux

Spring provides the **org.springframework.http.codec.ServerSentEvent<T>** class to represent an SSE. The generic T is the payload type of the data field.

Main properties:

- **id()**: event identifier.
- **event()**: event name.
- **retry()**: Duration requested for the next reconnect attempt.
- **comment()**: comment/heartbeat.
- **data()**: payload.

The builder can create an event with data immediately:

~~~java
ServerSentEvent<Progress> event =
    ServerSentEvent.<Progress>builder(
        new Progress(42, "running")
    )
    .id("42")
    .event("progress")
    .retry(Duration.ofSeconds(3))
    .build();
~~~

Or create a builder and assign each field:

~~~java
ServerSentEvent<Progress> event =
    ServerSentEvent.<Progress>builder()
        .id("42")
        .event("progress")
        .retry(Duration.ofSeconds(3))
        .data(new Progress(42, "running"))
        .build();
~~~

Spring writes retry in milliseconds. For example, a 3-second Duration is serialized as:

~~~text
retry:3000
~~~

Do not confuse the Java **Duration** type with the wire format value: the Spring API accepts Duration, while the SSE protocol transmits an integer number of milliseconds.

### 3.1. ServerSentEventHttpMessageWriter

When a handler returns Flux<ServerSentEvent<T>> and the response uses text/event-stream, Spring selects **ServerSentEventHttpMessageWriter**. The writer handles:

1. Setting/writing the appropriate media type.
2. Serializing id, event, retry, and comment.
3. Encoding data using the corresponding codec/message writer.
4. Writing each event to the response.
5. Flushing in a manner suitable for a streaming response.

If data is a Java object and Jackson is on the classpath, the payload is typically serialized to JSON. If data is a String, the content is written as text. The client must know the payload schema to parse it properly.

Do not manually set Content-Length for a stream of unknown length. Do not collect the entire Flux into a List just to return SSE; doing so loses streaming behavior and delays delivering events to the client.

### 3.2. Is ServerSentEvent mandatory?

No. WebFlux can also emit a Flux of plain objects when the mapping declares text/event-stream:

~~~java
@GetMapping(
    value = "/messages",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<String> messages() {
    return Flux.just("one", "two", "three");
}
~~~

In this case, each element is written as a data-only event. Use **ServerSentEvent<T>** when you need id, event name, retry, or comment.

## 4. id: identifying events and resuming the stream

The **id** field is a string identifying the event. The browser stores the most recent ID it has processed. If the connection is interrupted and EventSource automatically reconnects, the browser sends this value in the **Last-Event-ID** request header.

Basic flow:

~~~text
Server sends event id=101
          |
          v
Browser receives and stores last event ID = 101
          |
          v
Connection drops
          |
          v
EventSource automatically reconnects
          |
          v
Request sends Last-Event-ID: 101
          |
          v
Server reads header and replays events after 101
~~~

Example:

~~~text
id: 101
event: progress
data: {"percent":50}

id: 102
event: progress
data: {"percent":75}

~~~

If the connection drops after event 101, the browser can reconnect with Last-Event-ID set to 101. The server needs to locate subsequent events from historical storage to resume from 102.

**id does not automatically store events on the server.** It is only a cursor carried by the protocol. To truly resume, the application needs an event log, database, message broker, or storage capable of querying events after that cursor.

### 4.1. Reading Last-Event-ID in WebFlux

You can receive the header directly:

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<Progress>> events(
    @RequestHeader(
        name = "Last-Event-ID",
        required = false
    ) String lastEventId
) {
    long lastSeen = lastEventId == null
        ? 0
        : Long.parseLong(lastEventId);

    return eventStore.findAfter(lastSeen)
        .map(this::toServerSentEvent);
}
~~~

This snippet assumes eventStore returns a Publisher of events with IDs greater than the cursor. If the header can come from untrusted clients, validate the format, bound its length, and handle non-existent or stale IDs.

Do not restart sequence numbers from 1 on every server restart if clients may reconnect across deployments. The ID must remain stable within the event store's retention window, such as a database sequence or message broker offset.

### 4.2. Event IDs should be unique and suitably ordered

An ID can be an increasing number, an offset, or a lookup token. What matters is that the server can determine which events follow that ID.

A UUID can be unique but does not inherently express ordering. If using UUIDs, the event store must maintain an index mapping UUIDs to positions. For ordered streams, sequences/offsets are usually more convenient.

### 4.3. Avoiding duplicate or missed events on reconnect

On reconnect, the server might replay the last received event if client and server are not completely synchronized. Applications should design idempotent consumers: processing the same event again does not duplicate side effects.

A common pattern:

- Events have stable IDs.
- The client records processed IDs.
- The server queries events after Last-Event-ID.
- The client skips already-processed events if there is overlap.
- The server retains history long enough for the committed reconnect window.

SSE provides the cursor and reconnect mechanism; guaranteeing exactly-once semantics is the responsibility of application logic and the event store.

## 5. event: categorizing messages

The **event** field names the event type. If event is absent, the browser dispatches the default event type **message**.

Example:

~~~text
event: order-created
id: 501
data: {"orderId":"ORD-501","status":"created"}

event: order-shipped
id: 502
data: {"orderId":"ORD-501","status":"shipped"}

~~~

The browser registers listeners by name:

~~~javascript
const source = new EventSource("/api/orders/events");

source.addEventListener("order-created", (event) => {
    const payload = JSON.parse(event.data);
    console.log("Created:", payload.orderId);
});

source.addEventListener("order-shipped", (event) => {
    const payload = JSON.parse(event.data);
    console.log("Shipped:", payload.orderId);
});
~~~

If the server does not send an event field, use onmessage:

~~~javascript
source.onmessage = (event) => {
    console.log(event.data);
};
~~~

### 5.1. Naming events by contract

Event names should describe the business event or update type, for example:

- progress
- completed
- failed
- order-updated
- notification
- heartbeat

Avoid overly generic names like update if the client must distinguish multiple data flows. Also avoid placing sensitive data into the event name; this name is metadata visible to the client.

### 5.2. Distinguishing event name from data schema

event is only a classification label. data holds the payload. A progress event can carry percentage, task ID, and timestamp; a failed event can carry an error code and a display-safe message.

Example:

~~~java
public record Progress(
    long sequence,
    int percent,
    String status
) {}

public record StreamFailure(
    String code,
    String message
) {}
~~~

Version the schema if client and server may be deployed independently. Do not change the meaning of existing fields without a compatibility policy.

## 6. retry: reconnect interval

The **retry** field specifies how long the client waits before attempting to reconnect after the stream is interrupted. The value on the wire is an integer in milliseconds.

Example:

~~~text
retry:3000
~~~

The browser receives this value and updates its reconnection delay. If the field is not a valid integer, the client ignores that field and continues using the previous reconnect value or its implementation default.

In Spring:

~~~java
ServerSentEvent.builder("working")
    .event("progress")
    .retry(Duration.ofSeconds(5))
    .build();
~~~

Spring converts Duration into milliseconds when writing SSE.

### 6.1. Choosing a retry interval

- A short retry helps clients recover quickly from transient errors.
- A long retry reduces reconnect frequency when the server is overloaded.
- If many clients disconnect simultaneously, retrying at the exact same interval can cause a reconnect storm.
- You can combine client-side jitter/backoff or emit retry intervals adapted to server state.

Do not set retry too low for a service with tens of thousands of connections. Calculate the total number of reconnects that could happen when a server or proxy recovers.

### 6.2. retry is not Reactor's retry

These are two different concepts:

- **SSE retry field**: instructs the browser EventSource how long to wait before reopening the HTTP connection.
- **Reactor retryWhen/retry**: resubscribes to a Publisher in server-side or client-side code.

SSE retry does not automatically restart a failed Publisher on the server. It tells the client to open a new HTTP request. The server must build a new pipeline and use Last-Event-ID/event store if resumption is needed.

### 6.3. Browser automatic reconnection

The browser's EventSource automatically reconnects when the connection closes under protocol conditions. Errors can be observed via onerror:

~~~javascript
source.onerror = (error) => {
    console.warn("SSE connection interrupted", error);
};
~~~

Do not call **source.close()** if you want to keep the default reconnection behavior. Calling close() transitions EventSource to the closed state and stops reconnecting.

Not every HTTP response causes the browser to keep retrying. Invalid responses or statuses disallowed by the protocol can terminate the connection permanently; verify status and Content-Type on the server.

## 7. Complete WebFlux controller for SSE

A controller can generate periodic events:

~~~java
package com.example.sse;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api")
public class EventController {

    public record Progress(
        long sequence,
        int percent,
        String status
    ) {}

    @GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<Progress>> events(
        @RequestHeader(
            name = "Last-Event-ID",
            required = false
        ) String lastEventId
    ) {
        long lastSeen = lastEventId == null
            ? 0
            : Long.parseLong(lastEventId);

        return Flux.range(1, 5)
            .filter(sequence -> sequence > lastSeen)
            .delayElements(Duration.ofMillis(250))
            .map(sequence -> {
                Progress progress = new Progress(
                    sequence,
                    sequence * 20,
                    "processing"
                );

                return ServerSentEvent.<Progress>builder(progress)
                    .id(Long.toString(sequence))
                    .event("progress")
                    .retry(Duration.ofSeconds(3))
                    .build();
            });
    }
}
~~~

This is a complete controller in a Spring Boot WebFlux application. It emits five events with IDs 1 through 5. When the client reconnects with Last-Event-ID set to 2, the endpoint emits only events 3, 4, and 5.

The source in the example is Flux.range, providing a fixed history to illustrate resumption. In production, replace it with an event store or message broker with a durable cursor; do not use a new range starting from 1 if event data changes over time.

### 7.1. Why use Flux.delayElements?

Flux.interval or delayElements simulates events arriving over time. The Publisher stays reactive without requiring manual thread sleeping inside the controller.

Do not use Thread.sleep inside a handler. It blocks the thread handling the request and can degrade concurrency across connections.

### 7.2. Emitting heartbeats

If the stream may remain silent for long periods, you can emit periodic comments:

~~~java
ServerSentEvent.<Progress>builder()
    .comment("heartbeat")
    .build();
~~~

A full implementation needs to merge heartbeats with business events while preserving order. Do not emit heartbeats too frequently; base the interval on proxy/load balancer idle timeouts and system load.

## 8. Browser client with EventSource

JavaScript example:

~~~javascript
const source = new EventSource("/api/events");

source.addEventListener("progress", (event) => {
    const progress = JSON.parse(event.data);
    console.log(
        progress.sequence,
        progress.percent,
        progress.status
    );
});

source.onerror = (error) => {
    console.warn("Connection interrupted", error);
};

// When the user leaves the screen or no longer needs the stream:
function stopEvents() {
    source.close();
}
~~~

The browser automatically sends a GET request and keeps the connection open. When the server sends an event with an id, EventSource stores the last event ID. If the connection drops and reconnects, the browser sends Last-Event-ID in the new request.

### 8.1. EventSource provides no arbitrary API for request headers

Native EventSource has no option to set an arbitrary Authorization header. If authentication is needed, common approaches are:

- Secure session cookies with appropriate SameSite/Secure/HttpOnly attributes.
- Short-lived token mechanisms in the URL when the threat model permits and token logging is avoided.
- A fetch-based SSE client when custom headers and reconnect control are needed.

Do not put long-lived access tokens in the query string if URLs may appear in access logs, history, or telemetry.

### 8.2. CORS and credentials

If the browser connects cross-origin, configure CORS with the proper origin. If using cookie credentials, the client can create EventSource with the withCredentials option:

~~~javascript
const source = new EventSource(
    "https://api.example.com/events",
    { withCredentials: true }
);
~~~

The server must return CORS headers compatible with credentials; do not combine a wildcard origin with credentialed requests. Check cookie and SameSite policies when deploying across domains.

## 9. Testing SSE with WebTestClient

Because SSE is a stream, tests must read the body and inspect individual events, not merely assert status 200.

Example:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class EventControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void emitsEventsWithIdEventAndRetry() {
        FluxExchangeResult<ServerSentEvent<EventController.Progress>>
            result = client.get()
                .uri("/api/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM
                    )
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<EventController.Progress>
                    >() {}
                );

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event ->
                "1".equals(event.id())
                    && "progress".equals(event.event())
                    && event.retry().equals(Duration.ofSeconds(3))
                    && event.data().percent() == 20
            )
            .expectNextMatches(event ->
                "2".equals(event.id())
                    && event.data().percent() == 40
            )
            .thenCancel()
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void resumesAfterLastEventId() {
        FluxExchangeResult<ServerSentEvent<EventController.Progress>>
            result = client.get()
                .uri("/api/events")
                .header("Last-Event-ID", "2")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<EventController.Progress>
                    >() {}
                );

        StepVerifier.create(result.getResponseBody())
            .expectNextMatches(event -> "3".equals(event.id()))
            .expectNextMatches(event -> "4".equals(event.id()))
            .expectNextMatches(event -> "5".equals(event.id()))
            .verifyComplete();
    }
}
~~~

This is a test snippet requiring imports for JUnit, WebTestClient, ServerSentEvent, ParameterizedTypeReference, FluxExchangeResult, StepVerifier, and Duration. The first test reads two events and cancels so it does not have to wait for the entire stream. The second test verifies the Last-Event-ID cursor.

### 9.1. Testing real reconnects

WebTestClient sends the Last-Event-ID header to simulate a reconnect request. It does not simulate the full state machine of browser EventSource. To test automatic browser reconnection, integration/e2e tests using a browser or a real SSE client are needed.

Reconnect tests should verify:

- The last event ID is recorded accurately.
- The new request sends Last-Event-ID.
- The server replays from the next event.
- Old events are handled idempotently if overlap occurs.
- Events past retention are handled according to the resync policy.

## 10. Java 17+ project setup to run the example

This example uses **Spring Boot 3.3.5**, Spring Framework 6.1.x, and Java 17.

Structure:

~~~text
webflux-sse-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/sse/
    │   │       ├── SseApplication.java
    │   │       └── EventController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── com/example/sse/
                └── EventControllerTest.java
~~~

File **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webflux-sse-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File **SseApplication.java**:

~~~java
package com.example.sse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SseApplication {

    public static void main(String[] args) {
        SpringApplication.run(SseApplication.class, args);
    }
}
~~~

File **application.properties**:

~~~properties
spring.application.name=webflux-sse-demo
server.port=8080
logging.level.com.example.sse=INFO
~~~

Place EventController from section 7 and EventControllerTest from section 9 into the appropriate package. For Spring Boot tests, you can use @SpringBootTest(webEnvironment = RANDOM_PORT) to test through a real server; in that case add the webEnvironment attribute to the annotation.

### 10.1. Running and observing the stream

Requires JDK 17+ and Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Open another terminal:

~~~bash
curl -N -i \
  -H "Accept: text/event-stream" \
  http://localhost:8080/api/events
~~~

Curl may display events like:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

id:1
event:progress
retry:3000
data:{"sequence":1,"percent":20,"status":"processing"}

id:2
event:progress
retry:3000
data:{"sequence":2,"percent":40,"status":"processing"}

id:3
event:progress
retry:3000
data:{"sequence":3,"percent":60,"status":"processing"}
~~~

This is the expected content format; extra headers, field order, and whitespace may vary by server/writer. Event ID, event type, retry, and data are the values to verify.

Simulate reconnecting from event 2:

~~~bash
curl -N -i \
  -H "Accept: text/event-stream" \
  -H "Last-Event-ID: 2" \
  http://localhost:8080/api/events
~~~

The server only emits events with IDs 3, 4, and 5. This is how to test server-side resume logic; browser EventSource will automatically send the Last-Event-ID header on reconnect per the protocol.

Stop the application with Ctrl+C.

## 11. Common errors and fixes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Client receives a JSON array after a long wait | Endpoint returns Flux with media type application/json | Declare produces = text/event-stream |
| Browser does not dispatch events | Missing blank line ending event or stream not flushed | Use ServerSentEvent writer and check response streaming |
| onmessage does not fire | Server sets a custom event name | Use addEventListener with the exact event name |
| JSON.parse fails | data is not JSON or payload was encoded unexpectedly | Verify data schema and codec |
| Browser does not reconnect at the right interval | retry is not a valid integer in milliseconds | Use ServerSentEvent.Builder.retry(Duration) |
| Reconnects but starts over from the beginning | Server ignores Last-Event-ID | Read header and query events after the cursor |
| Reconnect misses events | Event ID is unstable or event store lacks sufficient retention | Use durable sequences/offsets and appropriate retention |
| Client processes duplicate events | Server replay has overlap | Design an idempotent consumer keyed by event ID |
| Connection closed by proxy when stream is silent | Idle timeout at proxy/load balancer | Send periodic comment heartbeats |
| CPU/resource usage grows due to many connections | Each client holds a long-lived stream | Bound connections, timeouts, backpressure, and monitor metrics |
| Server keeps producing data after client closes | Source does not respond to cancellation or uses manual subscribe | Compose Publisher and clean up on cancel |
| Cannot send Authorization header with EventSource | Native EventSource does not support arbitrary headers | Use appropriate cookies or a fetch-based SSE client |
| Test only verifies 200 OK | Response stream not consumed | Use WebTestClient and StepVerifier to inspect events |
| Calling close() and expecting auto-reconnect | close() permanently closes EventSource | Create a new EventSource if reopening is desired |
| Using SSE retry like Reactor retryWhen | Confusing browser-side retry with server-side resubscribe | Handle each mechanism on its proper side |
| Using UUIDs but server cannot find next event | ID lacks ordering/lookup index | Store a mapping or use sequences/offsets |

## 12. SSE security and operations

SSE keeps HTTP connections open for long periods. Each stream must be managed as a resource with a lifecycle.

- **Authentication/authorization:** authenticate before opening the stream and verify the user only receives permitted events.
- **CORS:** configure explicit origins, especially when using cookie credentials.
- **Heartbeat:** keep connections alive without generating excessive traffic.
- **Timeout:** align idle timeouts across the server, reverse proxy, and load balancer.
- **Backpressure:** avoid creating unbounded event queues for slow clients; establish policies for dropping, bounded buffering, or disconnecting.
- **Cancellation:** when the client closes the connection, cancel the subscription and release resources.
- **Retention:** keep events long enough for the committed reconnect window.
- **Rate limiting:** limit streams per user/tenant/IP to protect the server.
- **Observability:** track open connections, event rate, reconnects, lag, errors, and cancellations.
- **Data privacy:** do not expose sensitive information in event IDs, URLs, event names, or unnecessary payload fields.

Do not use SSE as an event store. SSE is only a transport channel; data requiring replay must reside in an event store or storage system with a retention policy.

## 13. SSE endpoint design checklist

Before deploying, confirm:

1. Does the endpoint properly declare text/event-stream?
2. Does the publisher emit event by event rather than collecting all data?
3. Does each event have a stable id when resumption is needed?
4. Are event names clear and client-compatible?
5. Does retry have a reasonable millisecond value?
6. Is Last-Event-ID read and validated?
7. Does the server have a durable replay source if resumption is required?
8. Is the event consumer idempotent during replay?
9. Is there a heartbeat aligned with proxy timeouts?
10. Are cancellation and cleanup handled on client disconnect?
11. Are queues/buffers bounded for slow clients?
12. Are CORS and authentication configured properly?
13. Does the browser client handle onerror, named events, and close()?
14. Do tests verify individual event contents, retry, ID, and reconnect?
15. Do metrics track connections, reconnects, lag, and errors?

## 14. Practice exercises

**Exercise 1 — Basic events:** Create a Flux<String> and return text/event-stream. Use curl -N to observe each event.

**Exercise 2 — ServerSentEvent:** Switch to Flux<ServerSentEvent<Progress>>. Set id, event, and data for each element.

**Exercise 3 — Retry:** Use retry(Duration.ofSeconds(5)). Observe the retry line on the wire and explain why the value is 5000.

**Exercise 4 — Named events:** Emit progress and completed events. Write a browser client using addEventListener for each type.

**Exercise 5 — Last-Event-ID:** Read the Last-Event-ID header, skip older events, and emit only events with IDs greater than the cursor.

**Exercise 6 — Event store:** Replace Flux.range with a list of events stored in a database or message broker. Design retention and handling for expired cursors.

**Exercise 7 — Heartbeat:** Emit periodic heartbeat comments. Simulate a proxy idle timeout and choose a suitable interval.

**Exercise 8 — Cancellation:** Open a stream and then close the browser/curl. Observe doFinally receiving CANCEL and verify the source is cleaned up.

**Exercise 9 — Slow consumer:** Simulate a slow-reading client. Bound the queue and decide when to drop events or disconnect.

**Exercise 10 — WebTestClient:** Verify content type, event ID, event name, retry, data, and reconnect from Last-Event-ID.

**Exercise 11 — Browser reconnect:** Use EventSource in a browser, intentionally interrupt the server connection, and verify the reconnect request includes Last-Event-ID.

**Exercise 12 — Security:** Protect streams per user. Verify user A does not receive user B's events and reconnects preserve proper authorization.

## 15. Key takeaways

**text/event-stream** is the media type for a UTF-8 event stream, with each event terminated by a blank line. In Spring WebFlux, use **Flux<ServerSentEvent<T>>** when you need to control event metadata.

- **id** tells the browser the event cursor to send back via Last-Event-ID on reconnect.
- **event** names the message type so clients can register listeners.
- **retry** specifies the reconnect wait duration in milliseconds.
- **comment** can be used as a heartbeat.
- **data** carries the text or JSON payload.

EventSource automatically reconnects per the protocol; the server must read Last-Event-ID and have an event store if replay is required. The retry field does not replace Reactor's retryWhen. Design event schemas, cancellation, retention, authorization, and backpressure before taking SSE to production.

## 16. References

- Spring Framework Reference — WebFlux Controller Return Values: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
- Spring Framework API — ServerSentEvent (6.1): https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/codec/ServerSentEvent.html
- Spring Framework API — ServerSentEventHttpMessageWriter: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/codec/ServerSentEventHttpMessageWriter.html
- Spring Framework API — WebTestClient: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/web/reactive/server/WebTestClient.html
- Spring Boot Reference — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- WHATWG HTML Standard — Server-sent events: https://html.spec.whatwg.org/multipage/server-sent-events.html
- MDN — Using server-sent events: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- MDN — EventSource: https://developer.mozilla.org/en-US/docs/Web/API/EventSource
