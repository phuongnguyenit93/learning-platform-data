# Bounding Queues When Broadcasting to Many Sessions or Slow Consumers in Spring WebFlux WebSocket

## 1. Problem: One Slow Client Can Degrade the Entire Broadcast Channel

WebSocket maintains a bidirectional connection so server and client can exchange messages in real time. In Spring WebFlux, each WebSocketSession has a reactive receive stream and a reactive send stream. When a message must be broadcast to hundreds or thousands of sessions, each client's consumption speed can vary widely:

- Clients on fast networks read immediately.
- Clients on mobile networks or low-end devices process slowly.
- Browsers move tabs to the background and throttle UI updates.
- Proxies or sockets become congested so the server cannot keep writing.
- A session has disconnected, but the cleanup pipeline has not finished yet.

If the server pushes 1,000 messages/second while a client can only process 50, the backlog grows by roughly 950 messages/second. An unbounded queue increases memory usage, introduces huge latency, triggers garbage collection, and eventually impacts healthy clients too.

The right goal is not "never have a backlog"; the goal is **bounding the backlog, choosing an explicit full-queue policy, and isolating slow receivers**.

This lesson explains:

1. How Reactor backpressure differs from actual memory limits.
2. Why a shared multicast sink can let a slow client hold back fast clients.
3. How to organize a bounded outbound queue per session.
4. Policies: FAIL_OVERFLOW, drop, coalesce, disconnect, and resume.
5. A runnable Spring Boot/WebFlux example using Sinks.Many unicast and ArrayBlockingQueue.
6. Testing that a slow subscriber does not cause fast subscribers to lose messages.
7. Calculating memory budgets, tracking metrics, and accounting for hidden transport queues.

## 2. Lifecycle of a WebSocketSession

Spring WebFlux provides WebSocketHandler:

~~~java
public interface WebSocketHandler {
    Mono<Void> handle(WebSocketSession session);
}
~~~

A session has two streams:

| API | Meaning |
| --- | --- |
| session.receive() | Flux<WebSocketMessage> received from the client |
| session.send(Publisher<WebSocketMessage>) | Writes outbound messages and returns Mono<Void> |
| session.close(CloseStatus) | Requests closing the session with an appropriate close code |
| session.getId() | Session identifier within runtime scope |

Minimal example echoing back received messages:

~~~java
public Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> replies = session.receive()
        .map(message ->
            session.textMessage(message.getPayloadAsText())
        );

    return session.send(replies);
}
~~~

In broadcast scenarios, multiple sessions receive content from a single source. Crucially, **each session has exactly one outbound publisher passed to session.send(...)**; never call send() individually per event in a loop.

### 2.1. Typical Processing Flow

~~~text
Business event source
         |
         v
Check publish permissions and payload size
         |
         v
Broadcast / room router
         |
         +------> Session A queue --> session A.send(...) --> browser A
         |
         +------> Session B queue --> session B.send(...) --> browser B
         |
         +------> Session C queue --> session C.send(...) --> browser C
                          |
                          v
                   Backlog limit
                          |
                          v
                Drop / disconnect / resume
~~~

This approach decouples each client's read rate. However, you must still bound total sessions and account for buffer layers beneath the application queue.

### 2.2. Enqueue Success Does Not Mean the Client Received It

Sinks.Many.tryEmitNext(...) returning OK only indicates the element was accepted by the sink at that moment. It **does not confirm that bytes were written to the socket, received by the browser, or processed by the client application**.

Similarly, an item leaving the application queue does not mean it has left Netty or OS buffers. When processing guarantees are required, use application-level ACKs or durable storage/replay.

## 3. Backpressure: Demand Does Not Automatically Become a Memory Quota

In Reactive Streams, subscribers signal demand via request(n). A backpressure-compliant Publisher does not emit onNext items beyond requested demand.

In practice, multiple boundaries are not strictly synchronous:

- Producers outside Reactor such as broker callbacks may emit faster than demand.
- Sinks are proactively called via tryEmitNext from multiple threads.
- Operators such as publishOn, flatMap, and buffer may maintain their own prefetch/queues.
- HTTP/WebSocket writers may transfer messages into transport buffers.
- Netty and the kernel maintain their own outbound buffers.
- Browsers have their own buffers and JavaScript execution time.

Therefore, backpressure is a signaling coordination mechanism; **a bounded queue limit is an additional resource policy**.

### 3.1. Patterns That Cause Unbounded Backlogs

Avoid using the following constructs for an unquotaed broadcast stream:

~~~java
Sinks.Many<String> sink =
    Sinks.many().unicast().onBackpressureBuffer();
~~~

Here, the overload without a Queue parameter can accumulate unbounded data when the subscriber has no demand.

~~~java
Flux<String> output = source.onBackpressureBuffer();
~~~

The overload without capacity likewise risks unbounded buffering.

~~~java
Sinks.Many<String> history =
    Sinks.many().replay().all();
~~~

Replaying full history fits small/bounded-lifecycle cases, but not an infinitely running room without retention limits.

### 3.2. Element-Count Bounded Buffers

You can use:

~~~java
Flux<String> bounded = source.onBackpressureBuffer(64);
~~~

When downstream lacks demand, the operator holds at most 64 elements; exceeding the limit triggers an overflow error per this overload's semantics. This bounds only that operator stage, not buffers in other layers.

Or create a unicast sink backed by a bounded Queue:

~~~java
Sinks.Many<String> sink = Sinks.many()
    .unicast()
    .onBackpressureBuffer(
        new ArrayBlockingQueue<String>(64)
    );
~~~

When a new element cannot be added because the Queue is full, tryEmitNext can return FAIL_OVERFLOW. The application must handle this result rather than ignoring it.

## 4. Why Can a Shared Multicast Sink Cause Head-of-Line Blocking?

Reactor supports several multicast strategies. They are **not equivalent** with respect to latency and subscriber independence.

### 4.1. multicast().onBackpressureBuffer(capacity)

~~~java
Sinks.Many<String> room = Sinks.many()
    .multicast()
    .onBackpressureBuffer(64);
~~~

This strategy emits to multiple subscribers and respects demand according to the slowest subscriber. If the speed gap between subscribers exceeds the buffer allowance, tryEmitNext can return FAIL_OVERFLOW.

Key points:

- The 64-slot buffer is **a single shared sink storage area**, not a separate 64-slot queue per client.
- One slow client can throttle the stream for fast clients.
- On overflow, using emitNext with an unsuitable error handler can put the sink into a terminal error state, affecting the entire room.
- Before any subscriber joins, the sink has a bounded warm-up buffer mechanism.
- Auto-cancel when the last subscriber cancels affects whether the sink can continue to be used.

For a small chat room where every client moves at the same pace, this may fit. For large broadcasts with independent clients, it is usually not the best choice.

### 4.2. multicast().directAllOrNothing()

~~~java
Sinks.Many<String> room = Sinks.many()
    .multicast()
    .directAllOrNothing();
~~~

If **any** subscriber has no demand, the new element may be dropped for **all** subscribers; tryEmitNext reports FAIL_OVERFLOW. The slow subscriber is not disconnected solely due to this event.

Choose this only when the protocol accepts dropping an event across the entire room simultaneously. Do not choose it for chat history, control commands, or transactions that must reach all recipients.

### 4.3. multicast().directBestEffort()

~~~java
Sinks.Many<String> room = Sinks.many()
    .multicast()
    .directBestEffort();
~~~

If only some subscribers are slow, the element is dropped for those subscribers while subscribers with demand still receive it. When **no** subscribers have demand, tryEmitNext can return FAIL_OVERFLOW.

This option fits telemetry or dashboards that can tolerate dropping stale frames. It provides no replay, per-client queues, or guarantee that every event reaches every client.

### 4.4. Comparing Broadcast Approaches

| Approach | Does a slow subscriber affect others? | Can data be lost? | Best Used For |
| --- | --- | --- | --- |
| Shared multicast onBackpressureBuffer(64) | Potentially | On overflow, errors must be handled | Small rooms needing coordinated demand |
| Shared directAllOrNothing() | Yes, events may be lost for everyone | Yes | Synchronized signals where missing samples are fine |
| Shared directBestEffort() | Limited, slow clients drop individually | Yes | Best-effort dashboards/telemetry |
| Separate bounded queue per session | Need not fill other sessions' queues | Per overflow policy | Many sessions needing isolation |
| Broker storing events + cursor/ACK | No, if quotas are handled properly | No loss within retention SLA | Events requiring resume/replay |

No single approach fits every application. Identify the criticality, frequency, and replayability of each message type.

## 5. Defining a Policy When the Queue Is Full

A bounded queue is only half the solution. You must decide what happens when pushing item N+1.

### 5.1. Stop Producing or Throttle Upstream

If the producer can be throttled, this preserves data and prevents backlogs.

- Propagate demand signals back upstream.
- Limit consumption rate from message brokers per tenant/room.
- Pause emitting non-essential data.
- Reduce sampling frequency under overload.

This does not always suit a broadcast source with many independent subscribers. Halting the entire source for one slow client can cause head-of-line blocking.

### 5.2. DROP_LATEST: Drop New Items

When the queue is full, keep older queued events and drop incoming ones. Use only if newer events are no more important than older ones.

For example, a best-effort log stream can tolerate losing some lines, but should report how many lines were dropped.

### 5.3. DROP_OLDEST: Drop Old Items

When the queue is full, drop the oldest event to keep the newest one. Suitable for dashboards showing latest state, unsuitable for a command sequence requiring complete ordered delivery.

If events carry sequence numbers, the client can detect gaps and request a fresh snapshot.

In Reactor, a per-client operator can apply:

~~~java
Flux<Snapshot> latestStates = source
    .onBackpressureBuffer(
        32,
        BufferOverflowStrategy.DROP_OLDEST
    );
~~~

Crucial condition: this operator must sit **inside each client's pipeline** for per-client quotas; do not place it once on a shared source and assume each subscriber gets 32 slots.

### 5.4. Coalesce by Key

For replaceable state (stock prices, cursor positions, progress), store only the latest value per key instead of queuing every update:

~~~text
Before coalescing:
  price-A=10, price-A=11, price-A=12, price-B=20

After coalescing:
  price-A=12, price-B=20
~~~

Coalescing requires a data structure with bounded key count, retention time, and payload size. Do not use an unbounded Map to replace an unbounded queue.

### 5.5. Disconnect Slow Clients

When messages must arrive completely in order but a client cannot keep up, **closing the slow session** is usually safer than holding an unbounded backlog or dropping silently.

Implementation steps:

1. Set a per-session queue capacity.
2. tryEmitNext reports FAIL_OVERFLOW.
3. Record the slow_consumer_disconnect metric.
4. Remove the session from the registry.
5. Request closure with an appropriate close code, such as **1013 (SERVICE_OVERLOAD)**.
6. The client reconnects and fetches a snapshot/replay from its cursor if supported.

Never include sensitive details in the close reason. Close frames may also fail to reach the client if the transport is already broken.

### 5.6. Time-Based Quotas

Even when a queue is not full, a message can sit waiting for tens of seconds. You can enforce:

- Max queue age.
- Max time without ACK.
- Max idle send interval.
- Max wall-clock time for a send operation.
- Max backlog in bytes.

Time limits should match the data type. Stale events should be dropped or trigger a resync rather than being delivered minutes late with no staleness indication.

## 6. Calculating Memory Budgets

For queues sized by message count:

~~~text
N = concurrent sessions
Q = max queued messages per session
B = max size of one message
M_app ≈ N × Q × B
~~~

Example:

- N = 200 sessions.
- Q = 64 messages/session.
- B = 8 KiB/message.

A conservative payload bound is roughly **100 MiB** (200 × 64 × 8 KiB), excluding metadata, object headers, codec buffers, Netty, kernel sockets, in-flight frames, and broker buffers.

This is a **budget estimate**, not an exact heap measurement: if multiple sessions share references to the same immutable String object, part of the payload may be shared; encoding to bytes and holding individual frames still consumes extra memory.

### 6.1. Counting Messages Alone Is Not Enough

If each message has unbounded size, 64 messages can exceed hundreds of MiB. Simultaneously bound:

- Max message bytes.
- Max queue elements.
- Max active sessions.
- Total memory budget per instance/tenant.
- Connection quotas and publish rates per user/room.

Measure **UTF-8 bytes**, not just String.length(), because UTF-16 code unit count does not equal wire byte count.

### 6.2. Isolating Budgets per Room and Tenant

One tenant could open thousands of sessions and consume most of an instance's budget. Enforce per-tenant/room limits and priority policies if some streams are more critical.

## 7. Java 17+ Example with Per-Session Bounded Outbound Queues

The following example uses **Spring Boot 4.1.2, Java 17+, Spring WebFlux, and Project Reactor**. It implements a simple broadcast hub:

- Each client has a unicast Sinks.Many.
- The queue is an ArrayBlockingQueue with 64 slots.
- Limit of 200 clients per instance.
- Text payload max 8 KiB.
- When one client's queue fills up, only that client is removed from the registry and requested to close.
- Other clients continue receiving messages.
- No manual subscribe for individual WebSocket messages.
- Includes a test reproducing a subscriber that requests no demand.

The example uses public text data without authentication. Protect the publish endpoint before deploying to production.

Structure:

~~~text
bounded-websocket-broadcast/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/broadcast/
    │       ├── BroadcastApplication.java
    │       ├── BoundedHub.java
    │       ├── BroadcastSocketHandler.java
    │       ├── BroadcastRoutes.java
    │       └── PublishController.java
    └── test/
        └── java/com/example/broadcast/
            └── BoundedHubTest.java
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>bounded-websocket-broadcast</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
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
            <artifactId>spring-boot-starter-webflux-test</artifactId>
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

The Spring Boot parent manages compatible Spring Framework, Reactor, Netty, and related dependencies. The webflux-test starter in Boot 4 provides testing utilities for WebFlux.

### 7.2. BroadcastApplication.java

~~~java
package com.example.broadcast;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BroadcastApplication {

    public static void main(String[] args) {
        SpringApplication.run(BroadcastApplication.class, args);
    }
}
~~~

### 7.3. BoundedHub.java

This is the core of the example.

~~~java
package com.example.broadcast;

import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.CloseStatus;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

@Component
public final class BoundedHub {

    public static final int MAX_SESSIONS = 200;
    public static final int MAX_PENDING = 64;
    public static final int MAX_TEXT_BYTES = 8192;

    private final ConcurrentMap<String, Peer> peers =
        new ConcurrentHashMap<>();

    private final AtomicInteger active = new AtomicInteger();

    public record BroadcastReport(
        int accepted,
        int disconnected,
        int activeSessions
    ) {}

    public static final class Peer {

        private final String id;

        private final Sinks.Many<String> outgoing =
            Sinks.many().unicast().onBackpressureBuffer(
                new ArrayBlockingQueue<String>(MAX_PENDING)
            );

        private final Sinks.One<CloseStatus> closeRequested =
            Sinks.one();

        private boolean stopped;

        private Peer(String id) {
            this.id = id;
        }

        public String id() {
            return id;
        }

        public Flux<String> outgoing() {
            return outgoing.asFlux();
        }

        public Mono<CloseStatus> closeRequested() {
            return closeRequested.asMono();
        }

        // Serialize only the producers of THIS peer's sink.
        private synchronized Sinks.EmitResult offer(String text) {
            if (stopped) {
                return Sinks.EmitResult.FAIL_TERMINATED;
            }

            return outgoing.tryEmitNext(text);
        }

        private synchronized void requestClose(
            CloseStatus status
        ) {
            if (!stopped) {
                stopped = true;
                closeRequested.tryEmitValue(status);
            }
        }

        private synchronized void finish() {
            stopped = true;
            outgoing.tryEmitComplete();
        }
    }

    public Peer register() {
        while (true) {
            int count = active.get();

            if (count >= MAX_SESSIONS) {
                throw new IllegalStateException(
                    "Too many WebSocket sessions"
                );
            }

            if (active.compareAndSet(count, count + 1)) {
                break;
            }
        }

        Peer peer = new Peer(UUID.randomUUID().toString());
        peers.put(peer.id(), peer);
        return peer;
    }

    public BroadcastReport broadcast(String text) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(
                "A broadcast must have non-blank text"
            );
        }

        if (text.getBytes(StandardCharsets.UTF_8).length
                > MAX_TEXT_BYTES) {
            throw new IllegalArgumentException(
                "Broadcast exceeds 8 KiB"
            );
        }

        int accepted = 0;
        int disconnected = 0;

        for (Peer peer : peers.values()) {
            Sinks.EmitResult result = peer.offer(text);

            if (result == Sinks.EmitResult.OK) {
                accepted++;
                continue;
            }

            // Fail closed. An unexpected sink failure must be logged
            // and counted separately in a production application.
            if (detach(peer)) {
                disconnected++;
                peer.requestClose(
                    CloseStatus.SERVICE_OVERLOAD
                        .withReason("Outbound backlog")
                );
            }
        }

        return new BroadcastReport(
            accepted,
            disconnected,
            active.get()
        );
    }

    public int activeCount() {
        return active.get();
    }

    public void unregister(Peer peer) {
        detach(peer);
        peer.finish();
    }

    private boolean detach(Peer peer) {
        if (peers.remove(peer.id(), peer)) {
            active.decrementAndGet();
            return true;
        }

        return false;
    }
}
~~~

**Why use ArrayBlockingQueue?**

Sinks.many().unicast().onBackpressureBuffer() without a Queue argument defaults to holding an unbounded backlog. When passed a bounded Queue, the sink cannot enqueue messages beyond available slots. When demand is absent and the queue is full, tryEmitNext reports FAIL_OVERFLOW.

**Why create a separate sink per Peer?**

A slow client fills only its own queue. It does not occupy slots in other clients' queues. Each Peer also has only one outbound subscriber corresponding to one session.send(...).

**Why use synchronized on offer?**

Producers can invoke broadcast from multiple requests/threads. Reactor safe sinks detect unserialized concurrent emissions and can return FAIL_NON_SERIALIZED. Synchronizing at the Peer ensures only one producer calls tryEmitNext on that session's sink at a time. This is a simple approach for a demo, not the optimal fan-out architecture at very large scale.

**Why use AtomicInteger for MAX_SESSIONS?**

Merely checking peers.size() before adding would allow concurrent handshakes to overshoot the limit together. The compareAndSet loop reserves quota before creating the Peer. detach decrements the session count only once thanks to key/value removal.

### 7.4. BroadcastSocketHandler.java

~~~java
package com.example.broadcast;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.CloseStatus;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketSession;

import reactor.core.publisher.Mono;

@Component
public final class BroadcastSocketHandler
        implements WebSocketHandler {

    private final BoundedHub hub;

    public BroadcastSocketHandler(BoundedHub hub) {
        this.hub = hub;
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        final BoundedHub.Peer peer;

        try {
            peer = hub.register();
        }
        catch (IllegalStateException overloaded) {
            return session.close(
                CloseStatus.SERVICE_OVERLOAD
            );
        }

        Mono<Void> outbound = session.send(
            peer.outgoing().map(session::textMessage)
        );

        // Consume the inbound stream so completion can detect
        // that the client has disconnected.
        Mono<Void> inbound = session.receive().then();

        // When a queue overflows, close only this session.
        Mono<Void> forcedClose = peer.closeRequested()
            .flatMap(session::close);

        // Terminate when the connection closes, sending fails,
        // or this peer must be disconnected.
        return Mono.firstWithSignal(
                inbound,
                outbound,
                forcedClose
            )
            .doFinally(signal -> hub.unregister(peer));
    }
}
~~~

Each session has a single session.send(...). Mono.firstWithSignal lets the session lifecycle end when inbound completes, outbound completes/errors, or policy requires closing the session. doFinally cleans up the registry on complete, error, or cancel.

In a production system, observe session close errors and distinguish graceful close from transport failures. Do not expect close frame 1013 to always reach the client if the socket has already disconnected.

### 7.5. BroadcastRoutes.java

~~~java
package com.example.broadcast;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;

@Configuration
public class BroadcastRoutes {

    @Bean
    HandlerMapping socketMapping(
        BroadcastSocketHandler handler
    ) {
        return new SimpleUrlHandlerMapping(
            Map.of("/ws/live", handler),
            -1
        );
    }
}
~~~

In Spring Boot's WebFlux configuration, WebSocketHandlerAdapter is provided by the WebFlux infrastructure. SimpleUrlHandlerMapping maps the URL /ws/live to the WebSocketHandler.

### 7.6. PublishController.java

~~~java
package com.example.broadcast;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class PublishController {

    private final BoundedHub hub;

    public PublishController(BoundedHub hub) {
        this.hub = hub;
    }

    @PostMapping(
        value = "/broadcast",
        consumes = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<BoundedHub.BroadcastReport> publish(
        @RequestBody Mono<String> text
    ) {
        return text.map(hub::broadcast)
            .onErrorMap(
                IllegalArgumentException.class,
                error -> new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Invalid broadcast message",
                    error
                )
            );
    }
}
~~~

POST /api/broadcast accepts text and forwards it to active Peers. This is a demo endpoint; **in production you must authenticate and authorize publishers**, bound request bodies at the gateway/server, and enforce rate limits.

The broadcast loop is synchronous O(N) work across Peers. It suffices to explain queue isolation, but you should not run thousands of expensive processing iterations on the Netty event loop. At large scale, offload fan-out to a bounded dispatcher, shard by room, and enforce system-wide quotas.

## 8. Testing with JUnit 5 and StepVerifier

The test below exercises the hardest case without depending on socket timing: one Peer does not subscribe, so its queue is never drained. The second Peer subscribes with unbounded demand and receives normally.

### 8.1. BoundedHubTest.java

~~~java
package com.example.broadcast;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.socket.CloseStatus;

import reactor.core.Disposable;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class BoundedHubTest {

    @Test
    void slowPeerIsRemovedButFastPeerKeepsReceiving() {
        BoundedHub hub = new BoundedHub();

        BoundedHub.Peer fast = hub.register();
        BoundedHub.Peer slow = hub.register();

        List<String> received = new ArrayList<>();

        // This subscriber requests demand and drains its sink.
        Disposable subscription =
            fast.outgoing().subscribe(received::add);

        // The slow peer intentionally has no subscriber;
        // its bounded queue cannot drain.
        for (int i = 0; i <= BoundedHub.MAX_PENDING; i++) {
            hub.broadcast("message-" + i);
        }

        assertEquals(
            BoundedHub.MAX_PENDING + 1,
            received.size()
        );
        assertEquals("message-0", received.get(0));
        assertEquals(
            "message-" + BoundedHub.MAX_PENDING,
            received.get(BoundedHub.MAX_PENDING)
        );

        // The slow peer exceeded its queue capacity.
        assertEquals(1, hub.activeCount());

        StepVerifier.create(slow.closeRequested())
            .expectNextMatches(status ->
                status.getCode()
                    == CloseStatus.SERVICE_OVERLOAD.getCode()
            )
            .verifyComplete();

        subscription.dispose();
        hub.unregister(fast);
        hub.unregister(slow);
    }

    @Test
    void rejectsOversizedMessageBeforeFanout() {
        BoundedHub hub = new BoundedHub();

        String oversized = "x".repeat(
            BoundedHub.MAX_TEXT_BYTES + 1
        );

        assertThrows(
            IllegalArgumentException.class,
            () -> hub.broadcast(oversized)
        );
    }

    @Test
    void enforcesMaximumConnectionQuota() {
        BoundedHub hub = new BoundedHub();
        List<BoundedHub.Peer> peers = new ArrayList<>();

        for (int i = 0; i < BoundedHub.MAX_SESSIONS; i++) {
            peers.add(hub.register());
        }

        assertThrows(
            IllegalStateException.class,
            hub::register
        );

        for (BoundedHub.Peer peer : peers) {
            hub.unregister(peer);
        }

        assertEquals(0, hub.activeCount());
    }
}
~~~

**Meaning of the first test:** the 64-slot queue of the unsubscribed Peer fills up on the subsequent emit; the slow Peer is detached. The fast Peer maintains demand and keeps receiving all messages in the example. This tests the **in-application queue**, not proof that an external network client actually receives every byte.

The second test verifies the payload limit. The third test verifies the session count limit.

### 8.2. Run Commands

Requires JDK 17+ and Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Maven runs unit tests before the application is started in the second command.

### 8.3. Trying via Browser and curl

Open the browser developer console:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/live");

socket.onopen = () => console.log("connected");
socket.onmessage = (event) => console.log(event.data);
socket.onclose = (event) => {
    console.log("closed", event.code, event.reason);
};
~~~

Open one or two more tabs with the same snippet, then publish from the terminal:

~~~bash
curl -i -X POST http://localhost:8080/api/broadcast \
  -H "Content-Type: text/plain" \
  --data-binary "Hello room"
~~~

If the sessions are active, each browser receives:

~~~text
Hello room
~~~

The REST response looks like:

~~~json
{
  "accepted": 3,
  "disconnected": 0,
  "activeSessions": 3
}
~~~

These numbers are **illustrative** when exactly three sessions are registered and no queue has overflowed. accepted counts sinks that accepted the message, not browsers that confirmed processing.

When all clients read quickly, it is not easy to fill the queue with just a few requests. Unit tests using an undrained Peer trigger overflow deterministically. To verify real slow networks, test with throttled clients, bandwidth-limited proxies, and monitor transport buffers as well.

## 9. Limitation of the Example: Application Queues Are Not End-to-End Flow Control

The example uses ArrayBlockingQueue to bound **each session's Sinks.Many**. However, at least three other layers must be managed:

~~~text
Application per-session queue
           |
           v
Reactor operators / writer prefetch
           |
           v
Netty outbound pending bytes
           |
           v
Kernel socket send buffer
           |
           v
Network and browser
~~~

If session.send(...) requests messages faster than the socket actually writes, the application queue may drain while messages accumulate in Netty. In that case, tryEmitNext returning OK does not mean total backlog is small.

Therefore, **do not claim this simple example blocks all memory growth from a slow receiver**. Production also needs bounds on:

- Pending bytes awaiting write on the connection.
- Write timeouts or send timeouts per server adapter.
- Netty Channel writability and write-buffer watermarks when integrating at the Netty layer.
- In-flight frame count.
- Unacknowledged frame count when data must be processed reliably.
- Max lifetime of a message in the queue or transport.
- Max inbound frame/message size to prevent oversized payloads.

Specific settings vary across Reactor Netty, Tomcat, Jetty, and Spring versions. Check your actual server adapter API rather than assuming a Netty limit applies to another connector.

### 9.1. Do Not Equate WebSocket Write with Browser ACK

A message written to the transport does not guarantee JavaScript onmessage has run. For events requiring confirmed client processing, use an application protocol:

~~~text
Server: EVENT {sequence: 101, ...}
Client: ACK   {sequence: 101}
Server: record lastAck = 101
~~~

Cap unacknowledged events at W. If pending ACKs exceed W or time out, pause/close the session or ask the client to resync. Never blindly resend events if handlers have side effects; clients must handle idempotency via sequence/event IDs.

### 9.2. When Zero Data Loss Is Required

An in-memory WebSocket queue is not a durable event store. When a process restarts or a connection drops, the queue disappears.

A system requiring resume typically uses:

- A database log or message broker persisting events.
- Monotonically increasing sequences/offsets per room or partition.
- Client-side last-acknowledged cursor.
- Replay after reconnect within the retention window.
- Snapshot/resync if the cursor has expired.
- Idempotent consumers to handle duplicate events.

Do not turn financial transactions or critical control commands into a DROP_OLDEST policy just to save memory.

## 10. Ensuring Ordering and Fairness Across Sessions

### 10.1. Ordering

WebSocket preserves frame order on a single connection, yet business event ordering also depends on producers and how messages enter each queue.

If multiple threads call broadcast concurrently, synchronized on each Peer only guarantees emissions are **not concurrent on the same sink**. It does not strictly guarantee every Peer sees the exact same order when two broadcast calls interleave.

If room-wide ordering is required:

- Assign sequences at ingress.
- Serialize the source stream per room/partition.
- Use a bounded dispatcher per room.
- Fan out in fixed sequence order.
- Detect gaps on the client and support replay when needed.

### 10.2. Fairness

One huge room can monopolize dispatcher time and starve smaller rooms. You can shard by room, tenant, or session ID hash, bound items processed per turn, and keep heavy work off the event loop.

Do not allocate a dedicated thread per WebSocket session without good reason; tens of thousands of threads incur heavy memory and scheduling overhead.

### 10.3. Global Backpressure

If all sessions become slow simultaneously, disconnecting sessions one by one can trigger a reconnect storm. The system should also include:

- Global publish rate limits.
- Adaptive admission control.
- Circuit breakers/bulkheads for event sources.
- Reduced update frequencies or coalescing per tenant.
- Cooldowns/reconnect jitter.
- Session budgets per instance and room.

## 11. Cleanup and Lifecycle Management

When a client disconnects or the server requests closure:

1. Remove the session from the registry.
2. Cancel the outbound Publisher.
3. Drain/clear queues and subscriptions.
4. Release references to payloads.
5. Stop any timers or listeners tied exclusively to the session.
6. Record close/cancel metrics and reasons.

In the example, Mono.firstWithSignal and doFinally clean up the registry when the session completes or is cancelled. In deployments with timers, broker subscriptions, or other resources, dispose of them in the same lifecycle.

Never remove only the Map entry while leaving a Flux.interval or broker consumer emitting to a disconnected session.

## 12. Testing Realistic Slow Consumers

Unit tests with a non-requesting subscriber are necessary but insufficient. A load/integration test plan should cover:

| Scenario | What to Observe |
| --- | --- |
| 1 fast client, 1 non-reading client | Fast client keeps receiving; slow client is handled per policy |
| 1,000 normally reading clients | Heap, CPU, queue depth, and latency stay within budget |
| 10% low-bandwidth clients | No unbounded memory growth |
| Large messages near 8 KiB | Byte budget and throughput remain accurate |
| One client sends oversized payload | Clear inbound size limit and protocol error |
| Client disconnects mid-broadcast | No retained references to closed sessions |
| Concurrent producers publishing | No unexpected FAIL_NON_SERIALIZED |
| Mid-stream network drop | Proper close/cancel/cleanup and reconnect |
| Server restart | Client resyncs/replays per contract |
| Broker faster than WebSocket | Source quotas, queues, and fan-out remain bounded |

Use Gatling, k6 with WebSocket, or custom test clients to generate load. Tests should measure memory, pending outbound bytes, and network throughput—not just successful request counts.

### 12.1. Metrics to Monitor

- websocket_sessions_active.
- websocket_outbound_queue_depth.
- websocket_outbound_queue_overflow_total.
- websocket_slow_consumer_disconnect_total.
- websocket_publish_accepted_total.
- websocket_publish_rejected_total.
- websocket_outbound_bytes_pending.
- websocket_event_lag_seconds.
- websocket_send_timeout_total.
- websocket_disconnect_total by close code.
- websocket_reconnect_rate.
- websocket_replay_gap_total.

Metric names can follow your system's conventions; these are design suggestions. With high-cardinality rooms/tenants, never use session ID as a Prometheus metric label, as it causes time-series explosion.

### 12.2. Early Alerts

Set alerts when:

- p95 queue depth rises over several minutes.
- Overflow rate increases.
- Active session count approaches threshold.
- Transport pending bytes keep climbing.
- Client lag exceeds SLA.
- GC pauses or heap usage grow with session count.
- Reconnect rate spikes after a node overload.

## 13. WebSocket Security and Resource Protection

Queue bounding is part of protecting services from accidental or intentional abuse.

- Authenticate at the handshake or appropriate HTTP layer.
- Enforce Origin/CORS matching WebSocket policy; do not rely on REST CORS as a substitute.
- Authorize rooms/tenants before subscribing.
- Limit connections per user, tenant, and IP.
- Limit frame sizes and total message sizes.
- Rate-limit publish and inbound messages.
- Do not allow clients to broadcast freely into arbitrary rooms.
- Never log access tokens or sensitive payloads.
- Configure appropriate idle/heartbeat durations; use WebSocket ping/pong where supported by the stack.
- Clean up sessions when tokens expire or permissions are revoked per contract.
- Use wss:// in production.

The POST /api/broadcast endpoint in the example is for local testing only; never deploy it publicly without authentication, authorization, and rate limiting.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Sinks.unicast().onBackpressureBuffer() without Queue | Backlog can grow unboundedly | Pass a bounded Queue |
| Sinks.replay().all() for an infinite room | Accumulates full history in memory | Use bounded retention or an event store |
| Using shared multicast buffer assuming per-client queues | Slow clients throttle fast clients | Isolate per-session queues or use intentional best-effort |
| Ignoring tryEmitNext results | Unnoticed lost events/overflows | Handle FAIL_OVERFLOW, FAIL_TERMINATED, FAIL_NON_SERIALIZED |
| Calling emitNext overflowing a shared sink | Can put the whole room into terminal error | Use tryEmitNext and local policies |
| Calling session.send(...).subscribe() per event | Multiple writers, lost ordering, hard cleanup | One outbound Flux per session |
| Using unbounded queues to avoid dropping events | Memory and latency spike | Bounded queues + replay/ACK |
| Bounding event count without bounding bytes | One huge event still causes OOM | Bound UTF-8 payload bytes |
| Treating sink OK as client processing confirmation | Overstates delivery guarantees | Use ACKs if needed |
| Monitoring only Java heap queues, ignoring Netty buffers | Misses transport-layer backlogs | Measure pending outbound bytes and send timeouts |
| Using DROP_OLDEST for payment commands | Loses critical events | Persist durably and use ACK/replay |
| Failing to clean up Peer on disconnect | Memory leaks, phantom sessions | doFinally, remove, and dispose |
| Concurrent broadcasts without serializing producers | FAIL_NON_SERIALIZED or reordering | Serialize per room/Peer |
| Heavy publishing on the event loop | Increases latency for all connections | Bounded dispatcher, shard fan-out |
| Rate-limiting only inbound, ignoring outbound | Server still OOMs pushing | Enforce quotas in both directions |
| All clients reconnecting simultaneously | Reconnect storm | Backoff and jitter |
| Not validating Origin/rooms | Cross-origin or unauthorized access | Validate handshake and authorization |

## 15. Production Readiness Checklist

Before going live, verify:

1. Does every session have a single explicit outbound Publisher?
2. Do per-session queues have hard limits on both message count and bytes?
3. Are max sessions per instance, user, and tenant configured?
4. Does the overflow policy match event semantics?
5. When a queue fills, is only the slow session impacted or the whole room?
6. Are tryEmitNext results checked?
7. Are concurrent producers serialized according to ordering requirements?
8. Are in-flight frames bounded at the transport layer?
9. Are send timeouts, channel writability, or equivalent safeguards configured?
10. For critical data, are durable ACKs/cursors/replay in place?
11. Is there a snapshot/resync policy when events are missed?
12. Are queue depth, pending bytes, lag, and overflows monitored?
13. Are subscriptions/timers/registries cleaned up in doFinally?
14. Have load tests covered slow networks, disconnects, reconnects, and large payloads?
15. Are authentication, room authorization, Origin checks, and rate limits enforced?
16. Is heavy broadcast fan-out kept off the event loop?
17. Are retry budgets/cooldowns in place to prevent reconnect storms?
18. Are shutdown and restart handled without losing required data?

## 16. Practice Exercises

**Exercise 1 — Bounded queue:** Create a unicast sink with ArrayBlockingQueue(4). Emit five elements before any subscriber joins and inspect the overflowing emission.

**Exercise 2 — Slow vs fast:** Create two Peers, subscribing only to the fast Peer. Broadcast five messages. Verify the fast Peer receives all of them while the slow Peer is closed.

**Exercise 3 — Multicast:** Compare multicast().onBackpressureBuffer(4), directBestEffort(), and directAllOrNothing() with one subscriber calling request(0) and one subscriber with demand.

**Exercise 4 — Overflow policy:** Replace disconnect with DROP_OLDEST for dashboard data; verify the client receives the latest snapshot and detects sequence gaps.

**Exercise 5 — Ordering:** Call broadcast from two threads. Assign sequences at ingress and verify every client observes a consistent per-room order.

**Exercise 6 — Byte budget:** Set MAX_TEXT_BYTES=1024. Send Unicode text and verify the limit enforces UTF-8 byte count rather than only String.length().

**Exercise 7 — Load test:** Open 200 WebSocket sessions where 10% read slowly. Measure heap, queue depth, pending bytes, and disconnect rate.

**Exercise 8 — ACK protocol:** Add sequence numbers, client ACKs, a cap of 16 unacknowledged events, and a timeout when the client fails to acknowledge.

**Exercise 9 — Replay:** Persist events in a broker/database. Reconnect with lastAck and replay only missing events.

**Exercise 10 — Cleanup:** Close browser tabs intentionally; verify activeCount decreases and no timers/subscriptions retain Peers.

**Exercise 11 — Multi-tenant:** Limit to 20 sessions per tenant and 200 sessions per instance. Test quota enforcement under concurrent handshakes.

**Exercise 12 — Transport backpressure:** Use a proxy to throttle outbound bandwidth. Identify where backlogs drain from the application queue yet remain in Netty, and add appropriate limits.

## 17. Key Takeaways

Bounding queues for WebSocket broadcast is more than adding a buffer. A safe design chooses **queue scope (per session vs room-wide), capacity, overflow policy, resource cleanup, and delivery guarantees**.

In Spring WebFlux, each session is served by one session.send(Publisher<WebSocketMessage>) and a reactive lifecycle. When slow clients must be isolated, per-session **Sinks.many().unicast().onBackpressureBuffer(bounded Queue)** is a clear starting point: check tryEmitNext, handle FAIL_OVERFLOW, and clean up Peers on disconnect.

Shared multicast sinks have different semantics: onBackpressureBuffer tracks the lowest demand, directAllOrNothing can drop for the whole room, and directBestEffort drops per slow subscriber. Choose based on product semantics, not throughput alone.

Finally, **an application queue does not automatically bound all transport memory**. Measure pending bytes, send timeouts, payload sizes, session counts, and event lag. For data requiring complete ordered delivery, add ACKs/cursors/replay; for replaceable data, consider controlled dropping/coalescing.

## 18. References

- Spring Framework Reference — WebFlux WebSockets: https://docs.spring.io/spring-framework/reference/web/webflux-websocket.html
- Spring Framework Reference — WebFlux Config / WebSocketService: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework API — WebSocketSession: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html
- Spring Framework API — CloseStatus: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/socket/CloseStatus.html
- Reactor Core Reference — Sinks: https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html
- Reactor Core API — Sinks.UnicastSpec: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.UnicastSpec.html
- Reactor Core API — Sinks.MulticastSpec: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.MulticastSpec.html
- Reactor Core API — Flux.onBackpressureBuffer: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Reactor Netty Reference Guide: https://projectreactor.io/docs/netty/release/reference/http-server.html
- Spring Boot 4.1 Reference — Reactive Web Applications: https://docs.spring.io/spring-boot/4.1/reference/web/reactive.html
