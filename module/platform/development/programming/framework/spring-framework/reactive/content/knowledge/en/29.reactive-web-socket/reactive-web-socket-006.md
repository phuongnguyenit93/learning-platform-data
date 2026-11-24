# Cancellation, Errors, Session Closure, and Resource Cleanup in Spring WebFlux WebSocket

## 1. Why Must the WebSocket Lifecycle Be Explicitly Managed?

WebSocket keeps a bidirectional connection open for a long time. A single session may receive and send thousands of messages while holding broker subscriptions, timers, queues, per-session caches, buffers, or external resources. When a client closes a tab, loses network connectivity, sends invalid data, the server encounters an error, or the application begins shutting down, every activity tied to that session must terminate properly.

In Spring WebFlux, this lifecycle is modeled with Reactive Streams:

- Inbound: WebSocketSession.receive() returns Flux<WebSocketMessage>.
- Outbound: WebSocketSession.send(Publisher<WebSocketMessage>) returns Mono<Void>.
- Handler: WebSocketHandler.handle(WebSocketSession) returns Mono<Void> representing when session processing completes.
- Close: WebSocketSession.close(CloseStatus) returns Mono<Void> to send a WebSocket close frame.
- Close status: WebSocketSession.closeStatus() returns Mono<CloseStatus>, which may complete empty if the transport ends without a close status.

**Core principle:** connect inbound, outbound, and session resources into the same reactive lifecycle. When one side ends, the other side and dependent resources must be cancelled or closed according to the chosen policy.

Do not call subscribe() separately on streams inside the handler, do not call block() to wait for messages, and do not rely on a boolean checking whether the connection is still open to coordinate the lifecycle. Let completion, error, and cancellation propagate through publishers.

## 2. A WebSocket Session Has Two Independent Streams

Spring WebFlux models a session with one receive stream and one send stream:

~~~text
                   WebSocketSession
                          |
             +------------+------------+
             |                         |
             v                         v
      receive(): Flux              send(Publisher)
             |                         |
             v                         v
      Client -> Server             Server -> Client
             |                         |
             +------------+------------+
                          |
                          v
                 handle(): Mono<Void>
                          |
                          v
             complete / error / cancel
                          |
                          v
             close and resource cleanup
~~~

receive() emits messages arriving from the client. This stream completes when the connection closes and may terminate with an error if the transport fails.

send(...) accepts a publisher of outbound messages, writes them onto the connection, and completes when the source publisher completes and writing finishes. If the source publisher is cancelled, sending stops as well.

The handler must compose both streams into one unified Mono<Void>. Depending on business requirements, the session may end when inbound finishes, outbound finishes, either branch emits an error, or the application proactively calls session.close(...).

### 2.1. Simple Echo Handler

If every incoming message produces exactly one reply message, inbound can be wired directly to outbound:

~~~java
class EchoHandler implements WebSocketHandler {

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        Flux<WebSocketMessage> replies = session.receive()
            .map(WebSocketMessage::getPayloadAsText)
            .map(text -> session.textMessage("echo: " + text));

        return session.send(replies);
    }
}
~~~

When the client sends a text message, the handler produces a corresponding response. When inbound completes, the reply publisher also completes; when writing fails, the error propagates through send and handle.

This pattern fits when outbound depends solely on inbound. When the server also has an independent feed, such as broker events or periodic notifications, you must also compose that feed and define what happens when inbound closes.

## 3. Three Terminal Signals to Distinguish

Reactive Streams has three primary termination outcomes:

| Signal | Meaning | Action Needed |
| --- | --- | --- |
| ON_COMPLETE | Publisher ended normally | Complete dependent branches and close resources |
| ON_ERROR | Publisher ended due to an error | Record error, map appropriate close status, clean up |
| CANCEL | Subscriber cancelled subscription | Stop source, cancel tasks, and release resources |

These three signals are not equivalent.

For example:

- Client sends a valid close frame: inbound typically completes normally.
- Client drops network abruptly: the adapter may emit an error or completion depending on transport and detection timing.
- Server shuts down or another processing branch ends the session: outbound may receive cancellation.
- Handler is cancelled externally: all downstream subscriptions must receive cancellation.

Do not assume every client disconnect is always represented as CANCEL or always produces one specific exception. Handle terminal signals generally and use closeStatus() to read the close code when the transport provides one.

## 4. Composing Inbound and Outbound with the Right Lifecycle

There are two common structures.

### 4.1. One Outbound Stream Derived from Inbound

If each inbound message produces an outbound message, use a single pipeline:

~~~java
Mono<Void> handle(WebSocketSession session) {
    Flux<WebSocketMessage> output = session.receive()
        .concatMap(message ->
            process(message.getPayloadAsText())
                .map(session::textMessage)
        );

    return session.send(output);
}
~~~

concatMap processes sequentially and preserves message order. If work per message is independent and can run concurrently, you can use flatMap with bounded concurrency. Never choose unbounded concurrency for messages from untrusted clients.

### 4.2. Inbound and Outbound with Separate Sources

A chat or dashboard session may both receive client commands and push events from the server:

~~~java
Mono<Void> input = session.receive()
    .concatMap(message -> processCommand(message.getPayloadAsText()))
    .then();

Flux<WebSocketMessage> serverEvents =
    eventService.events(session.getId())
        .map(session::textMessage);

Mono<Void> output = session.send(serverEvents);
~~~

Both publishers must be combined into one lifecycle. If inbound ends while serverEvents remains infinite, merely waiting for both to complete would keep the outbound subscription running. If the application policy is "when either branch stops, the session ends," you can use Mono.firstWithSignal:

~~~java
return Mono.firstWithSignal(input, output);
~~~

firstWithSignal emits the first terminal signal among the racing Monos: complete, empty completion, or error. When one branch ends, the other branch is cancelled. This is a clear choice when inbound closure must cancel the outbound feed, or when outbound completion means there is no longer a need to keep receiving messages.

Spring also illustrates composing independent inbound and outbound streams using input.and(output) in the WebFlux WebSocket documentation. Choose the operator matching your application's desired semantics; understand which branch is allowed to live on after the other completes and ensure cancellation propagates upstream.

### 4.3. Do Not Send via Multiple Independent Subscriptions

Avoid calling session.send multiple times for the same session or manually subscribing to multiple outbound publishers:

~~~java
// Avoid: two independent writers concurrently controlling one session.
session.send(replies).subscribe();
session.send(notifications).subscribe();
return session.receive().then();
~~~

Instead, merge message sources and call send once:

~~~java
Flux<WebSocketMessage> outbound = Flux.merge(
    replies,
    notifications
);

return session.send(outbound);
~~~

merge allows multiple sources to emit concurrently and may interleave messages across sources. If strict global ordering is required, funnel messages into an ordered queue or use appropriate sequential composition. Either way, only one outbound publisher should drive session writes.

## 5. Cancellation Must Propagate to Data Sources

Suppose each WebSocket session opens a subscription to Redis Pub/Sub. When the client leaves, closing only the socket is not enough. The Redis subscription may still exist and keep receiving messages if it is not part of the same reactive chain.

The right flow:

~~~text
Client disconnect
       |
       v
session.receive() complete/error
       |
       v
input lifecycle terminates
       |
       v
combined handler terminates
       |
       v
session.send publisher is cancelled
       |
       v
event feed is cancelled
       |
       v
broker subscription is closed
       |
       v
session registry entry is removed
~~~

When cancellation propagates properly, upstream has the opportunity to stop work and release resources. If a service manually calls subscribe() and keeps the subscription in a global map unlinked from the session lifecycle, WebSocket cancellation will not automatically cancel that subscription.

Audit resources created per session:

- Message broker subscriptions.
- Database change streams or cursors.
- Timers and scheduled tasks.
- Per-session sinks or queues.
- Files/channels or data streams.
- Asynchronous message-processing tasks.
- Entries in active session registries.

## 6. Using usingWhen to Open and Close Asynchronous Resources

doFinally is suitable for recording metrics or performing short synchronous cleanup. If closing a resource returns a publisher, use Flux.usingWhen or Mono.usingWhen.

usingWhen manages a resource across all three termination paths:

1. Resource closure completes normally.
2. Resource closure emits an error.
3. Downstream cancels.

Skeleton example:

~~~java
Flux<String> messages = Flux.usingWhen(
    subscriptionService.open(sessionId),
    subscription -> subscription.messages(),
    subscription -> subscription.close(),
    (subscription, error) -> subscription.close(),
    subscription -> subscription.close()
);
~~~

The second parameter creates the publisher that uses the resource. The last three callbacks perform cleanup corresponding to complete, error, and cancel.

This is the right approach for broker subscriptions with an asynchronous unsubscribe operation:

- Open the subscription when the WebSocket starts using the feed.
- Emit messages from the subscription.
- When the client closes or the handler is cancelled, call close/unsubscribe.
- When the feed errors, still invoke cleanup before terminating the stream.
- When the feed completes normally, also close the resource.

Keep all work that requires the resource to stay open inside the resource-usage closure. Do not leak the resource outside and continue using it after usingWhen has terminated.

## 7. doFinally, doOnCancel, and doOnError

Lifecycle observation operators have different scopes:

| Operator | When It Runs | Used For |
| --- | --- | --- |
| doOnComplete | Complete | Recording normal completion |
| doOnError | Error | Logging or incrementing error metrics |
| doOnCancel | Cancel | Recording subscription cancellation |
| doFinally | Complete, error, or cancel | Logging terminal signals, general metrics |

Example:

~~~java
Mono<Void> lifecycle = Mono.firstWithSignal(input, output)
    .doOnError(error ->
        log.error("WebSocket session failed: {}", session.getId(), error)
    )
    .doFinally(signal ->
        log.info(
            "WebSocket session {} terminated with {}",
            session.getId(),
            signal
        )
    );
~~~

doFinally receives a SignalType. It is useful for recording lifecycle events, but its callback is synchronous and not the ideal place to await an asynchronous resource close operation.

If asynchronous cleanup is needed, use usingWhen. If you have a synchronous Disposable such as a dedicated timer, you can call dispose() inside a cleanup callback and ensure that callback runs on complete, error, and cancel.

Do not rely solely on doOnTerminate to release resources because it does not include cancellation.

## 8. Deliberately Closing a WebSocket Session

To proactively close a session, call:

~~~java
session.close(CloseStatus.NORMAL);
~~~

This method returns Mono<Void>. You must compose that publisher into the pipeline so the close frame is actually sent and completion/errors are observed:

~~~java
return session.receive()
    .takeUntil(message ->
        "bye".equals(message.getPayloadAsText())
    )
    .then(session.close(CloseStatus.NORMAL));
~~~

When the client sends the bye message, takeUntil includes the triggering message and completes the stream. Then the handler calls close with normal status.

Do not call session.close(...) and discard the publisher. Creating a Mono does not mean the close frame has been sent; the operation runs only when the publisher is subscribed to.

### 8.1. Close Handshake

WebSocket close is a handshake at the WebSocket layer:

1. One side sends a Close control frame with a close status.
2. The other side replies with a Close frame.
3. The connection is closed.

HTTP status 101 is only the status of the HTTP-to-WebSocket upgrade handshake. It is not the close status of the WebSocket session.

Once the close handshake begins, do not continue sending business messages as if the session were still active. Stop outbound message publishers and clean up session-bound resources.

### 8.2. Reading Close Status

~~~java
return session.closeStatus()
    .doOnNext(status ->
        log.info(
            "Session {} closed with code {} and reason {}",
            session.getId(),
            status.getCode(),
            status.getReason()
        )
    )
    .then();
~~~

closeStatus() provides the close status produced by either the local or remote endpoint. The publisher may complete empty if the connection ends without a close status, such as an abrupt transport loss.

Do not rely on close status to decide whether to run cleanup. Cleanup must still run when the publisher completes, errors, or is cancelled.

## 9. Choosing the Appropriate CloseStatus

Spring provides CloseStatus constants for common cases:

| Code | Spring Constant | Meaning |
| --- | --- | --- |
| 1000 | NORMAL | Normal closure |
| 1002 | PROTOCOL_ERROR | Protocol error |
| 1003 | NOT_ACCEPTABLE | Unacceptable received data type |
| 1008 | POLICY_VIOLATION | Message violates policy |
| 1009 | TOO_BIG_TO_PROCESS | Message too big |
| 1011 | SERVER_ERROR | Unexpected server error |
| 1012 | SERVICE_RESTARTED | Service restarting |
| 1013 | SERVICE_OVERLOAD | Service overloaded |

Example:

~~~java
return session.close(CloseStatus.POLICY_VIOLATION);
~~~

Codes 1005, 1006, and 1015 are reserved values and must not be sent as status codes in a Close control frame. 1006 is typically used to represent abnormal closure when no close frame was received; do not explicitly call close with this code.

Choosing a close code matching the root cause helps the client decide whether to reconnect or display an error. Never include stack traces, tokens, personal data, or internal details in the reason string.

## 10. Mapping Application Errors to Close Status

Errors occurring during message processing can be mapped to an appropriate close status.

Example:

~~~java
return processMessages(session)
    .onErrorResume(
        InvalidClientMessageException.class,
        error -> session.close(CloseStatus.POLICY_VIOLATION)
    )
    .onErrorResume(
        error -> session.close(CloseStatus.SERVER_ERROR)
    );
~~~

A straightforward policy:

- Message violates business rules: 1008.
- Payload exceeds limit: 1009.
- Protocol error or invalid message type: 1002 or 1003 depending on the case.
- Unexpected server error: 1011.
- Server overloaded: 1013 if the application has an appropriate rejection policy.

Do not map every error to 1000. Normal closure can mislead the client into thinking the session ended successfully and no error needs to be displayed.

Likewise, do not send raw exception messages to the client. Log details on the server; the client only needs a safe, concise close code and reason.

### 10.1. Do Not Swallow Errors with Mono.empty

Avoid:

~~~java
return processMessages(session)
    .onErrorResume(error -> Mono.empty());
~~~

This turns an error into a normal completion. The client may observe close behavior that does not reflect the cause, and error metrics are lost if not recorded beforehand.

If a recoverable business error allows the session to continue, explicitly translate that error into a structured protocol message. If the error prevents the session from continuing, map it to a close status and terminate.

### 10.2. Distinguishing Application Errors from Transport Errors

| Error Type | Examples | Handling |
| --- | --- | --- |
| Client sent invalid data | Malformed JSON schema, unauthorized command | Close 1008 or protocol error reply |
| Message too big | Exceeds business limit | Close 1009 or appropriate frame limit |
| Internal processing error | Null pointer, bug, service failure | Log server-side and close 1011 |
| Broker/database error | Feed stops working | Stop feed, log, close, or enter degraded state per policy |
| Client lost network | TCP reset, transport error | Clean up; close status may be absent |
| Client closed normally | Valid close frame | Complete and clean up normally |

Do not treat every error signal as a client disconnect. Errors can come from validation, serialization, the broker, transport, or application code.

## 11. Resource Cleanup: Each Resource Type Has Its Own Way to Close

A WebSocket session often holds multiple kinds of resources:

| Resource | Cleanup Approach |
| --- | --- |
| Reactor subscription | Propagate cancellation upstream |
| Broker subscription | Call asynchronous unsubscribe/close |
| Timer or Disposable | Call dispose |
| Session registry entry | Remove the matching session ID |
| Database cursor | Close/cancel query |
| File/channel | Close channel |
| Pooled DataBuffer | Release per ownership rules |
| Per-session Sink | Complete/error and drop references |
| Per-session Queue | Stop producers and release queue |

Cleanup should have these properties:

1. **Idempotent:** calling multiple times does not corrupt state.
2. **Covers all terminal paths:** complete, error, and cancel.
3. **Ordered:** stop producers before removing registry entries or closing resources producers still use.
4. **Does not block the event loop:** blocking operations must be offloaded to an appropriate scheduler.
5. **Drops references:** remove map entries, listeners, and callbacks once the session ends.
6. **Observable:** logs/metrics for open, closed, errored sessions, and lifetimes.

Do not use a static map to hold resources indefinitely. If a registry for active sessions is needed, remove entries in the resource's cleanup callback.

## 12. DataBuffer and WebSocketMessage: Avoiding Memory Leaks

On runtimes such as Reactor Netty, buffers may be pooled and reference-counted. When a message is received, the framework manages buffer lifecycles. If the application holds a message to process across an asynchronous boundary, the buffer may already be released before async code finishes reading it.

### 12.1. Reading Payloads Synchronously Before Moving to Async

If you only need a String, extract the payload immediately inside the pipeline:

~~~java
return session.receive()
    .map(WebSocketMessage::getPayloadAsText)
    .concatMap(text -> messageService.process(text));
~~~

The String is created before entering the asynchronous operation, so there is no need to hold onto WebSocketMessage just to read text later.

### 12.2. Retaining a Message When Needed Across an Async Boundary

If you must pass the message itself or its payload buffer into asynchronous work, use retain and release matching the lifecycle:

~~~java
return session.receive()
    .concatMap(message -> {
        message.retain();

        return messageService.processMessage(message)
            .doFinally(signal -> message.release());
    })
    .then();
~~~

retain() increments the reference count when the runtime uses pooled buffers. release() decrements the reference count after work finishes. doFinally covers complete, error, and cancel of the message-processing publisher.

Retain only when you genuinely need to keep the buffer. Do not release a message the application did not retain or does not own. Do not release twice. Do not keep buffers in long-lived caches or queues without an explicit ownership policy.

### 12.3. Buffers Discarded Inside Operators

If you write custom pipelines processing DataBuffer and use operators that may prefetch or discard items such as filter, skip, or certain buffering operators, handle discarded buffers with an appropriate discard hook such as doOnDiscard(DataBuffer.class, DataBufferUtils::release) when the application owns that buffer.

For high-level messages such as Strings or DTOs decoded by codecs, let the framework manage buffers. Drop down to the DataBuffer layer only when byte-level processing is genuinely required.

## 13. Backpressure and Sequential Message Processing

WebSocket can receive messages faster than the application can process them. If a handler launches unbounded concurrent async work, queues and memory can grow continuously.

concatMap processes one message at a time in order:

~~~java
Mono<Void> input = session.receive()
    .concatMap(message ->
        commandService.execute(message.getPayloadAsText())
    )
    .then();
~~~

Use flatMap when messages are independent and concurrent processing is allowed:

~~~java
Mono<Void> input = session.receive()
    .flatMap(
        message -> commandService.execute(message.getPayloadAsText()),
        8
    )
    .then();
~~~

The concurrency parameter bounds how many tasks run concurrently. If reply order must match request order, use concatMap or attach sequence IDs and order at the protocol layer.

Do not create unbounded queues per session. If a client sends too fast, you may need to:

- Limit message size.
- Limit in-flight requests.
- Apply rate limiting per user/session.
- Reject commands exceeding quota.
- Close the session on policy violation.
- Measure queue depth and processing latency.

## 14. Closing a Session Does Not Replace Cleanup

These two actions are distinct:

- session.close(CloseStatus) closes the WebSocket protocol connection.
- Resource cleanup closes broker subscriptions, timers, database cursors, queues, buffers, and registry entries.

A session may be closed while a broker subscription remains alive if it was created outside the reactive chain. Conversely, resources can be cleaned up when the handler is cancelled even if a close frame could not be sent because the client lost network connectivity.

Therefore, both mechanisms are required:

1. Use close status when the connection is still capable of performing the close handshake.
2. Use the reactive lifecycle to release resources regardless of whether the close handshake succeeds.

Do not place all cleanup in a branch that runs only on normal close calls.

## 15. Graceful Shutdown When the Application Stops

When the server prepares to shut down, open WebSocket sessions may need to be closed cleanly.

A common procedure:

1. Stop accepting new sessions or mark the service as shutting down.
2. Reject new commands or return a service-stopping notification.
3. Send an appropriate close status, commonly 1012 when the service restarts.
4. Wait for a bounded grace period.
5. Cancel remaining sessions when the timeout expires.
6. Clean up broker subscriptions, timers, and registries.
7. Allow the server to finish shutting down.

Do not block application shutdown indefinitely just because one WebSocket client fails to respond to a close handshake. Enforce a timeout on the graceful shutdown phase and track a metric for remaining sessions.

If using a session registry, the registry should provide a way to snapshot active sessions and request closure reactively. Avoid iterating over an unsynchronized mutable map while other sessions are being created or closed.

## 16. Logging and Metrics for Session Lifecycle

Log lifecycle events, and do not log full message payloads in production if payloads may contain sensitive data.

Useful metrics:

| Metric | Purpose |
| --- | --- |
| websocket_active_sessions | Number of currently open sessions |
| websocket_open_total | Total opened sessions |
| websocket_close_total | Total closed sessions |
| websocket_error_total | Total sessions ending in error |
| websocket_cancel_total | Total cancelled sessions |
| websocket_close_code_total | Closures broken down by close code |
| websocket_session_duration | Session lifetime duration |
| websocket_inbound_messages_total | Inbound message count |
| websocket_outbound_messages_total | Outbound message count |
| websocket_feed_active | Number of active feed subscriptions |

Minimum logs should include session ID, log-safe user ID, close code if present, terminal signal, lifetime, and error category. Do not log tokens, cookies, raw authentication headers, or sensitive payloads.

When closeStatus() is empty, record "no close status received" rather than synthesizing 1000 or 1006 as a sent close frame. That is an observed state, not a status proactively emitted by the server.

## 17. Complete Java 17+ Spring Boot WebFlux Demo

The demo below exhibits the following behaviors:

- WebSocket endpoint at /ws/chat.
- Client sends text messages, server echoes them back.
- Server concurrently pushes periodic events.
- Client sends /close to request a normal close.
- Messages exceeding the limit are closed with policy violation.
- Each session's dedicated feed is managed with usingWhen.
- The feed is cleaned up on complete, error, or cancel.
- The handler composes inbound and outbound with Mono.firstWithSignal.

### 17.1. Project Structure

~~~text
webflux-websocket-lifecycle/
  build.gradle
  src/
    main/java/demo/
      DemoApplication.java
      WebSocketConfig.java
      ChatWebSocketHandler.java
      PolicyViolationException.java
      SessionFeed.java
      SessionFeedService.java
    test/java/demo/
      SessionFeedServiceTest.java
~~~

### 17.2. build.gradle

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

Spring Boot manages compatible Spring Framework and Reactor versions. The demo uses Java 17 and the WebFlux starter to run on Reactor Netty.

### 17.3. DemoApplication.java

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

### 17.4. PolicyViolationException.java

~~~java
package demo;

public class PolicyViolationException extends RuntimeException {
    public PolicyViolationException(String message) {
        super(message);
    }
}
~~~

This exception represents a message violating the endpoint's policy, such as a payload exceeding the character limit. The handler maps the error to close status 1008.

### 17.5. SessionFeed.java

~~~java
package demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Sinks;

final class SessionFeed {
    private final String sessionId;
    private final Sinks.Empty<Void> closed = Sinks.empty();
    private final AtomicBoolean closeStarted = new AtomicBoolean();

    SessionFeed(String sessionId) {
        this.sessionId = sessionId;
    }

    String sessionId() {
        return sessionId;
    }

    Flux<String> events() {
        return Flux.interval(Duration.ofSeconds(5))
            .map(sequence ->
                "update-" + sequence + " for " + sessionId
            )
            .takeUntilOther(closed.asMono());
    }

    Mono<Void> close() {
        return Mono.fromRunnable(() -> {
            if (closeStarted.compareAndSet(false, true)) {
                closed.tryEmitEmpty();
            }
        });
    }

    boolean isClosed() {
        return closeStarted.get();
    }
}
~~~

SessionFeed represents a resource bound to one session. The feed emits periodic events. When the close signal is emitted, takeUntilOther stops the timer and completes the publisher.

In a real application, this resource could be a broker subscription or database change feed. The close() method would then unsubscribe/close the real resource.

### 17.6. SessionFeedService.java

~~~java
package demo;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
class SessionFeedService {
    private final ConcurrentMap<String, SessionFeed> active =
        new ConcurrentHashMap<>();

    Mono<SessionFeed> open(String sessionId) {
        return Mono.fromSupplier(() -> {
            SessionFeed feed = new SessionFeed(sessionId);
            SessionFeed existing = active.putIfAbsent(sessionId, feed);

            if (existing != null) {
                throw new IllegalStateException(
                    "Feed already exists for session " + sessionId
                );
            }

            return feed;
        });
    }

    Mono<Void> close(SessionFeed feed) {
        return feed.close()
            .doFinally(signal ->
                active.remove(feed.sessionId(), feed)
            );
    }

    Flux<String> events(String sessionId) {
        return Flux.usingWhen(
            open(sessionId),
            SessionFeed::events,
            this::close,
            (feed, error) -> close(feed),
            this::close
        );
    }

    int activeCount() {
        return active.size();
    }
}
~~~

events(sessionId) creates one resource per subscription. usingWhen invokes close when the feed completes, emits an error, or is cancelled. The active map only retains active feeds, and entries are removed during cleanup.

### 17.7. ChatWebSocketHandler.java

~~~java
package demo;

import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.socket.CloseStatus;
import org.springframework.web.reactive.socket.WebSocketHandler;
import org.springframework.web.reactive.socket.WebSocketMessage;
import org.springframework.web.reactive.socket.WebSocketSession;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SynchronousSink;

@Component
class ChatWebSocketHandler implements WebSocketHandler {
    private static final Logger log =
        LoggerFactory.getLogger(ChatWebSocketHandler.class);

    private static final int MAX_TEXT_LENGTH = 1024;

    private final SessionFeedService feedService;

    ChatWebSocketHandler(SessionFeedService feedService) {
        this.feedService = feedService;
    }

    @Override
    public Mono<Void> handle(WebSocketSession session) {
        return session.receive()
            .map(WebSocketMessage::getPayloadAsText)
            .handle((String text, SynchronousSink<String> sink) -> {
                if (text.length() > MAX_TEXT_LENGTH) {
                    sink.error(new PolicyViolationException(
                        "Message exceeds the allowed length"
                    ));
                } else {
                    sink.next(text);
                }
            })
            .publish(messages -> {
                AtomicBoolean closeRequested = new AtomicBoolean();

                Mono<Void> input = messages
                    .takeUntil("/close"::equals)
                    .doOnNext(text -> {
                        if ("/close".equals(text)) {
                            closeRequested.set(true);
                        }
                    })
                    .then()
                    .then(Mono.defer(() ->
                        closeRequested.get()
                            ? session.close(CloseStatus.NORMAL)
                            : Mono.<Void>empty()
                    ));

                Flux<WebSocketMessage> replies = messages
                    .filter(text -> !"/close".equals(text))
                    .map(text -> session.textMessage("echo: " + text));

                Flux<WebSocketMessage> updates =
                    feedService.events(session.getId())
                        .map(session::textMessage);

                Mono<Void> output = session.send(
                    Flux.merge(replies, updates)
                );

                return Mono.firstWithSignal(input, output)
                    .doOnError(error ->
                        log.error(
                            "WebSocket session {} failed",
                            session.getId(),
                            error
                        )
                    )
                    .onErrorResume(
                        PolicyViolationException.class,
                        error -> closeSafely(
                            session,
                            CloseStatus.POLICY_VIOLATION
                        )
                    )
                    .onErrorResume(
                        error -> closeSafely(
                            session,
                            CloseStatus.SERVER_ERROR
                        )
                    )
                    .doFinally(signal ->
                        log.info(
                            "WebSocket session {} ended with {}",
                            session.getId(),
                            signal
                        )
                    )
                    .then(
                        session.closeStatus()
                            .doOnNext(status ->
                                log.info(
                                    "WebSocket session {} close code {}",
                                    session.getId(),
                                    status.getCode()
                                )
                            )
                            .then()
                    );
            });
    }

    private Mono<Void> closeSafely(
            WebSocketSession session,
            CloseStatus status) {

        return session.close(status)
            .onErrorResume(closeError -> {
                log.debug(
                    "Could not complete close handshake for session "
                        + session.getId(),
                    closeError
                );
                return Mono.empty();
            });
    }
}
~~~

Lifecycle explanation:

1. session.receive() creates the inbound stream.
2. handle enforces the message length limit before sharing data between the two branches.
3. publish(Function) shares a single inbound subscription across the lifecycle-tracking branch and the echo-producing branch; the socket is not subscribed twice.
4. Upon receiving /close, the input branch finishes and composes session.close(CloseStatus.NORMAL).
5. The output branch merges echo replies and the server feed, then calls session.send exactly once.
6. Mono.firstWithSignal terminates the handler when either branch completes or errors, while cancelling the other branch.
7. When output is cancelled, Flux.usingWhen on the feed runs cancellation cleanup.
8. Policy errors close with 1008; unexpected errors close with 1011.
9. doFinally logs the terminal signal; closeStatus() reads the status if provided by the transport.

closeSafely handles the case where the connection is already lost and the close handshake cannot complete. Close errors are logged, while publisher cleanup still runs.

### 17.8. WebSocketConfig.java

~~~java
package demo;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.HandlerMapping;
import org.springframework.web.reactive.handler.SimpleUrlHandlerMapping;
import org.springframework.web.reactive.socket.WebSocketHandler;

@Configuration
class WebSocketConfig {

    @Bean
    HandlerMapping webSocketMapping(ChatWebSocketHandler handler) {
        Map<String, WebSocketHandler> handlers =
            Map.of("/ws/chat", handler);

        SimpleUrlHandlerMapping mapping = new SimpleUrlHandlerMapping();
        mapping.setOrder(-1);
        mapping.setUrlMap(handlers);

        return mapping;
    }
}
~~~

Spring Boot WebFlux auto-configuration provides the WebSocket adapter infrastructure when WebFlux configuration is active. If building an application without WebFlux config, register WebSocketHandlerAdapter per Spring Framework documentation.

Do not add EnableWebFlux solely to map a WebSocket handler in a Spring Boot app; configuring a dedicated handler mapping is sufficient for this example.

### 17.9. SessionFeedServiceTest.java

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class SessionFeedServiceTest {

    @Test
    void completionReleasesFeed() {
        SessionFeedService service = new SessionFeedService();

        Flux<String> oneEvent = Flux.usingWhen(
            service.open("complete-session"),
            feed -> feed.events().take(1),
            service::close,
            (feed, error) -> service.close(feed),
            service::close
        );

        StepVerifier.withVirtualTime(() -> oneEvent)
            .thenAwait(Duration.ofSeconds(5))
            .expectNext("update-0 for complete-session")
            .verifyComplete();

        assertEquals(0, service.activeCount());
    }

    @Test
    void cancellationReleasesFeed() {
        SessionFeedService service = new SessionFeedService();

        StepVerifier.withVirtualTime(() ->
                service.events("cancelled-session"))
            .thenAwait(Duration.ofSeconds(5))
            .expectNext("update-0 for cancelled-session")
            .thenCancel()
            .verify();

        assertEquals(0, service.activeCount());
    }

    @Test
    void errorReleasesFeed() {
        SessionFeedService service = new SessionFeedService();

        Flux<String> failed = Flux.usingWhen(
            service.open("failed-session"),
            feed -> Flux.<String>error(
                new IllegalStateException("feed failed")
            ),
            service::close,
            (feed, error) -> service.close(feed),
            service::close
        );

        StepVerifier.create(failed)
            .expectErrorMessage("feed failed")
            .verify();

        assertEquals(0, service.activeCount());
    }
}
~~~

The three tests verify that cleanup runs on resource closure completion, error, and cancellation. Virtual time lets you test timers without real waiting. Do not use Thread.sleep.

### 17.10. Running the Application

From the project directory:

~~~bash
./gradlew bootRun
~~~

Or:

~~~bash
gradle bootRun
~~~

Connect using the browser console:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/chat");

socket.onopen = () => {
    socket.send("hello");
};

socket.onmessage = event => {
    console.log("received:", event.data);
};

socket.onclose = event => {
    console.log("closed:", event.code, event.reason);
};

socket.onerror = error => {
    console.error("websocket error", error);
};
~~~

The server returns the echo message almost immediately and emits additional periodic events. To request a normal close:

~~~javascript
socket.send("/close");
~~~

To test a policy violation, send text exceeding 1024 characters. The server will close the session with close code 1008. In the demo, the feed is cleaned up after the output publisher is cancelled.

Run tests:

~~~bash
./gradlew test
~~~

The tests verify the three cleanup paths of the feed resource. They do not replace testing handshakes over the network; before shipping an endpoint to production, add integration tests with WebSocketClient or a compatible client to test close handshakes, reconnects, and transport errors.

## 18. Client-Side WebSocketClient Example

Spring WebFlux also provides WebSocketClient. execute(URI, WebSocketHandler) returns a Mono<Void> representing the client session lifecycle.

~~~java
WebSocketClient client = new ReactorNettyWebSocketClient();
URI uri = URI.create("ws://localhost:8080/ws/chat");

Mono<Void> conversation = client.execute(uri, session ->
    session.send(
        Mono.just(session.textMessage("hello"))
    )
    .then(
        session.receive()
            .map(WebSocketMessage::getPayloadAsText)
            .next()
            .doOnNext(System.out::println)
            .then()
    )
    .then(
        session.close(CloseStatus.NORMAL)
    )
);
~~~

The client sends one message, reads the first response, and then closes the session normally. If the caller cancels conversation, the client handler also receives cancellation and both receive/send publishers must terminate according to the lifecycle.

Do not call subscribe() separately and discard the execute publisher. Return the Mono to the caller so the caller controls subscription, timeouts, cancellation, and error handling.

## 19. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Only closing the socket, forgetting broker subscription | Upstream resource stays active | Bind subscription into usingWhen |
| Cleaning up only in doOnComplete | Misses error and cancel | Use usingWhen or doFinally appropriately |
| Catching only error, ignoring cancel | Client leaves while task keeps running | Ensure cancellation propagates to publishers |
| Using separate subscribe for feed | Lifecycle detached from handler | Return publisher and compose with send |
| Calling close without composing Mono | Close frame may not be sent | Chain session.close(...) into Mono |
| Calling session.send multiple times | Multiple writers contend for writes | Merge message sources and send once |
| Leaving infinite output alive after inbound closes | Feed keeps holding resources | Use composition that terminates the remaining branch |
| Using Mono.when without understanding semantics | May wait for all branches to complete | Choose operator matching session-termination policy |
| Swallowing errors into Mono.empty | Errors turn into normal closure | Map errors to intentional close statuses |
| Using close code 1006 to send a close frame | Uses invalid reserved code | Let transport represent abnormal closure |
| Treating HTTP 101 as close status | Confuses handshake with close handshake | Read WebSocket CloseStatus |
| Using isOpen() as a synchronization condition | Race between check and send | Rely on reactive signals and handle write errors |
| Holding WebSocketMessage across async boundary without retain | Pooled buffer may already be released | Copy payload synchronously or retain/release |
| Retaining without releasing | Memory leak | Release in doFinally of the message-holding task |
| Blocking event loop during cleanup | Increases latency and stalls server | Use reactive cleanup or an appropriate scheduler |
| Registry fails to remove session | Memory leak and stale state | Remove entry during cleanup |
| Unbounded outbound queue | RAM grows when client is slow | Apply backpressure, bounded queues, and quotas |
| Logging full payloads | May expose sensitive data | Log metadata, close codes, and correlation IDs |
| Using close status 1000 for all errors | Client mistakenly assumes normal completion | Map errors to 1008/1009/1011 appropriately |

## 20. Pre-Production WebSocket Checklist

1. Does the handler return a single Mono<Void> representing the session lifecycle?
2. Are inbound and outbound composed according to the right termination policy?
3. When inbound closes, is the outbound feed cancelled?
4. When output errors, is inbound cancelled?
5. Do broker/database subscriptions clean up on complete, error, and cancel?
6. Is session.close(...) composed and awaited?
7. Do close codes accurately reflect the cause?
8. Are abnormal client disconnects handled even when closeStatus() is empty?
9. Are message size, concurrency, and queue bounds enforced?
10. Are retain/release used if pooled messages cross an async boundary?
11. Does the session registry remove entries during cleanup?
12. Is cleanup idempotent and non-blocking on the event loop?
13. Are metrics tracked for active sessions, close codes, errors, cancels, and duration?
14. Are there tests for complete, error, and cancel?
15. Are there integration tests for handshake, normal close, and abnormal disconnect?
16. Does graceful shutdown have a grace period and timeout?

| Requirement | API or Mechanism |
| --- | --- |
| Receive messages | session.receive() |
| Send messages | session.send(...) |
| Normal close | session.close(CloseStatus.NORMAL) |
| Policy close | CloseStatus.POLICY_VIOLATION |
| Server error close | CloseStatus.SERVER_ERROR |
| Read close code | session.closeStatus() |
| Stop when first branch stops | Mono.firstWithSignal(...) |
| Async cleanup on complete/error/cancel | Flux.usingWhen(...) |
| Observe terminal signals | doFinally(...) |
| Observe cancellation | doOnCancel(...) |
| Retain pooled message | message.retain() |
| Release retained message | message.release() |

## 21. Self-Check Questions with Answers

**Question 1.** What type does WebSocketHandler.handle return and what does it represent?

**Answer:** Mono<Void> representing when session processing completes. The handler must compose inbound, outbound, and cleanup into that lifecycle.

**Question 2.** How do receive() and send(...) differ?

**Answer:** receive() is the inbound message Flux, completing when the connection closes. send(...) writes the outbound publisher and returns Mono<Void> completing when both the message source and write operations finish.

**Question 3.** When a client closes the connection, why must the outbound feed be cancelled?

**Answer:** The feed may be infinite and hold subscriptions to a broker or other resources. Cancellation stops the source and triggers cleanup.

**Question 4.** Which signals does doFinally cover?

**Answer:** Complete, error, and cancel. It is suitable for lifecycle observation or short synchronous cleanup.

**Question 5.** When should usingWhen be used?

**Answer:** When a resource must be opened and closed asynchronously across all three cases: complete, error, and cancel.

**Question 6.** Does session.close(CloseStatus.NORMAL) execute immediately when the Mono is created?

**Answer:** No. It is a reactive publisher; it must be subscribed to or composed into the lifecycle for the close handshake to execute.

**Question 7.** How do 1000 and 1008 differ?

**Answer:** 1000 is normal closure; 1008 is closure due to a message violating policy.

**Question 8.** Can 1006 be sent in a Close control frame?

**Answer:** No. 1006 is a reserved code representing abnormal closure when no close frame was received.

**Question 9.** Why can closeStatus() complete empty?

**Answer:** The transport may terminate without receiving a WebSocket close status, such as network loss or a reset connection.

**Question 10.** When must message.retain() be called?

**Answer:** When needing to keep a message or pooled DataBuffer for use after leaving a synchronous receive callback or across an asynchronous boundary.

**Question 11.** Why must a retained message be released?

**Answer:** Retain increments the reference count of a pooled buffer. Releasing at the right time brings the reference count down so the buffer can be reclaimed.

**Question 12.** What does Mono.firstWithSignal(input, output) mean?

**Answer:** The publisher emits the first terminal signal between the two Monos; the remaining branch is cancelled. Used when one side ending means the session should not continue.

**Question 13.** Does closing a WebSocket session automatically unsubscribe all broker subscriptions created by the application?

**Answer:** No. Broker subscriptions must participate in the reactive lifecycle or have a dedicated cleanup callback such as usingWhen.

**Question 14.** Why should subscribe() not be called separately inside WebSocketHandler?

**Answer:** An independent subscription is no longer controlled by the handler's lifecycle; session cancellation and errors may not propagate to that publisher.

## 22. Key Takeaways and Official Documentation

- WebSocketHandler returns Mono<Void> representing the entire session handling.
- receive() and send(...) are two reactive streams that must be composed.
- When one side ends per policy, cancel the other side so upstream resources are cleaned up.
- session.close(CloseStatus) sends the close handshake and must be composed.
- closeStatus() may be empty when transport ends abnormally.
- Use appropriate close codes: 1000 normal, 1008 policy, 1009 too big, 1011 server error.
- usingWhen manages async cleanup for complete, error, and cancel.
- doFinally observes all three terminal signals; doOnCancel observes only cancellation.
- Never let broker subscriptions, timers, registries, or queues outlive the WebSocket session.
- Pooled DataBuffers require explicit ownership; retain must be paired with release.
- Never use manual subscribe or multiple independent writers for the same session.

Official Documentation:

1. [Spring Framework Reference — WebFlux WebSockets](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-websocket.html): WebSocketHandler, receive/send composition, cancellation, session closure, client API, and DataBuffer.
2. [Spring Framework Javadoc — WebSocketSession](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/socket/WebSocketSession.html): close, closeStatus, receive, send, and session metadata.
3. [Spring Framework Javadoc — CloseStatus](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/reactive/socket/CloseStatus.html): close codes, constants, and meanings.
4. [Spring Framework Javadoc — WebSocketMessage](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/reactive/socket/WebSocketMessage.html): payload, retain, and release.
5. [Spring Framework Reference — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html): pooled buffers, reference counting, retain/release, and discard.
6. [Project Reactor Javadoc — Flux.usingWhen](https://projectreactor.io/docs/core/3.7.17/api/reactor/core/publisher/Flux.html): asynchronous resource cleanup on complete, error, and cancel.
7. [Project Reactor Javadoc — Mono.firstWithSignal](https://projectreactor.io/docs/projectreactor/reactor-core/docs/current/api/reactor/core/publisher/Mono.html): selecting the first terminal signal from multiple Monos.
8. [Spring Framework Javadoc — WebSocketClient](https://docs.spring.io/spring-framework/docs/6.2.2/javadoc-api/org/springframework/web/reactive/socket/client/WebSocketClient.html): execute handshake and client session management.
