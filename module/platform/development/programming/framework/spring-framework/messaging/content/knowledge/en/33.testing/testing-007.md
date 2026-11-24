# End-to-End Testing with WebSocketStompClient

## 1. Objectives and Scope

When a Spring application uses STOMP over WebSocket, a test that merely calls a controller method directly does not verify the full message path. Real requests also travel through the WebSocket handshake, STOMP CONNECT, payload converters, destinations, message channels, the broker, and STOMP MESSAGE frames returned to the client.

**WebSocketStompClient** is the STOMP client provided by Spring on top of WebSocketClient. Use it in end-to-end (E2E) tests to connect to a running real server, send STOMP frames, and verify that response frames arrive at the client.

This lesson covers:

- Starting the WebSocket server in tests and obtaining a dynamic port.
- Configuring WebSocketStompClient, MessageConverter, and TaskScheduler.
- Connecting at both the WebSocket and STOMP layers.
- Subscribing, waiting for subscription readiness, sending messages, and receiving results.
- Writing a StompFrameHandler to convert payloads into DTOs.
- Collecting errors from the STOMP session and transport.
- Cleaning up subscriptions, sessions, clients, and schedulers.
- Distinguishing E2E tests from server-side controller tests and knowing when a real broker is needed.

## 2. What Does an E2E Test Verify?

A typical STOMP flow in Spring:

~~~text
Test client
    |
    | WebSocket handshake: GET /ws + Upgrade
    v
WebSocket endpoint
    |
    | STOMP CONNECT
    v
STOMP session / CONNECTED
    |
    | SUBSCRIBE /topic/replies
    v
Message broker stores subscription
    |
    | SEND /app/echo
    v
clientInboundChannel
    |
    v
@MessageMapping("/echo")
    |
    | @SendTo("/topic/replies")
    v
brokerChannel / broker
    |
    | STOMP MESSAGE
    v
clientOutboundChannel
    |
    v
WebSocketStompClient
    |
    v
StompFrameHandler.handleFrame(...)
    |
    v
Test assertion
~~~

An E2E test can verify multiple components at once:

| Component | What to Verify |
| --- | --- |
| HTTP/WebSocket handshake | The endpoint can be opened and the server accepts connections. |
| STOMP CONNECT/CONNECTED | STOMP version, session, and handshake headers are handled properly. |
| MessageConverter | DTOs are serialized on send and deserialized on receive. |
| Destination routing | `/app` prefix routes to controllers; `/topic` or `/queue` routes to the broker. |
| @MessageMapping | The right handler is invoked with the converted payload. |
| Broker subscription | The client subscribes to the right destination and receives MESSAGE frames. |
| Error handling | STOMP ERROR, conversion errors, and transport errors are observed. |
| Session cleanup | UNSUBSCRIBE and DISCONNECT are sent when the test finishes. |

Spring has two approaches for testing STOMP-over-WebSocket. Server-side tests can send messages directly into clientInboundChannel to verify controllers and annotations within the Spring messaging infrastructure. E2E tests require a running WebSocket server and a real client sending WebSocket messages containing STOMP frames. The two approaches complement each other; E2E is broader but heavier to start up and maintain.

MockMvc or a test that simply calls Java methods does not perform a real WebSocket handshake. When you need to verify the handshake, STOMP protocol, broker routing, and client frame reception, run the server in embedded/random-port mode and connect using WebSocketStompClient.

## 3. Required STOMP Server Configuration

Example configuration for tests using a broker relay that supports RECEIPT:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("localhost")
            .setRelayPort(61613);
    }
}
~~~

The STOMP broker must already be running on the configured host/port. Configure login, passcode, and system connection settings according to the actual broker. If you only need an in-memory broker for basic flows, you can replace the relay with:

~~~java
registry.enableSimpleBroker("/topic", "/queue");
~~~

The destinations in the example mean:

- **/ws** is the endpoint URL for the WebSocket handshake.
- **/app** is the prefix for messages routed to `@MessageMapping` methods.
- **/topic** and **/queue** are broker prefixes.

Controller handling requests:

~~~java
import java.util.Locale;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class EchoController {

    @MessageMapping("/echo")
    @SendTo("/topic/replies")
    public ChatMessage echo(ChatMessage message) {
        return new ChatMessage(message.text().toUpperCase(Locale.ROOT));
    }
}
~~~

DTO:

~~~java
public record ChatMessage(String text) {
}
~~~

The client sends to `/app/echo`; Spring strips the `/app` application prefix to match `@MessageMapping("/echo")`. The method's return value is sent to `/topic/replies`.

The simple in-memory broker is suitable for basic flows. It supports only a subset of STOMP and lacks features such as ACK/NACK and RECEIPT. If tests require receipts, acknowledgements, broker relay, or RabbitMQ/ActiveMQ-specific behavior, run a real broker in the test environment and configure `enableStompBrokerRelay` accordingly.

## 4. Initializing WebSocketStompClient

### 4.1. Choosing a WebSocket Transport

Spring builds WebSocketStompClient on top of a WebSocketClient implementation:

~~~java
WebSocketClient webSocketClient = new StandardWebSocketClient();
WebSocketStompClient stompClient =
    new WebSocketStompClient(webSocketClient);
~~~

StandardWebSocketClient uses the standard Java WebSocket API. If the endpoint supports SockJS and tests need to verify SockJS fallback, you can configure SockJsClient as the WebSocketClient. Use the exact URL and transport deployed by the application.

### 4.2. MessageConverter

StompSession.send(destination, payload) uses MessageConverter to serialize the payload into `byte[]`. When receiving frames, StompFrameHandler declares the target type so the converter can deserialize the payload.

For JSON DTOs, configure the Jackson converter:

~~~java
stompClient.setMessageConverter(new MappingJackson2MessageConverter());
~~~

If the client sends a ChatMessage, the converter produces the corresponding JSON. On the receiving side, when the handler returns ChatMessage.class from getPayloadType, the converter constructs the object passed into handleFrame.

Without an appropriate converter configured, tests may fail with missing-converter errors, wrong payload types, or JSON conversion errors. Data types on both sides and content-type must be compatible.

### 4.3. TaskScheduler, Heartbeats, and Receipts

You can attach a TaskScheduler to the client:

~~~java
ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
scheduler.setPoolSize(1);
scheduler.setThreadNamePrefix("stomp-test-");
scheduler.initialize();

stompClient.setTaskScheduler(scheduler);
~~~

The scheduler is used for heartbeats and tracking RECEIPT deadlines. When testing a broker that supports receipts, explicitly configure the scheduler and receipt time limit. If only testing a basic flow with the simple broker, there is no need to enable receipts.

Heartbeats help detect dead connections. WebSocketStompClient sends heartbeats only when no other messages are sent; application traffic can count as activity. In tests running large numbers of clients, consider disabling heartbeats if heartbeat behavior is not under test, since each session can schedule its own heartbeat tasks.

## 5. Connecting and STOMP Session Lifecycle

A successful WebSocket handshake is not enough for a test to send messages. The client must also send STOMP CONNECT and receive STOMP CONNECTED.

With Spring Framework 6 and later, you can use connectAsync:

~~~java
StompSession session = stompClient.connectAsync(
    "ws://localhost:8080/ws",
    new StompSessionHandlerAdapter() {
        @Override
        public void afterConnected(
                StompSession session, StompHeaders connectedHeaders) {
            System.out.println("STOMP connected: " + session.getSessionId());
        }
    }
).get(5, TimeUnit.SECONDS);
~~~

connectAsync returns a `CompletableFuture<StompSession>`. The future completes when the STOMP session is ready for use—that is, after the client receives the CONNECTED frame from the broker/server. Always supply a timeout on `get` so tests do not hang indefinitely if the server cannot be reached.

Key components:

- **StompSessionHandler:** receives session lifecycle events, ERROR frames, and transport errors.
- **StompSessionHandlerAdapter:** adapter class providing default methods so you can override only the callbacks you want to observe.
- **StompSession:** sends messages, creates subscriptions, unsubscribes, and disconnects.
- **StompFrameHandler:** receives a STOMP frame and specifies the payload type.

StompSessionHandler is also a StompFrameHandler, so it can handle ERROR frames. Distinguish the two error callbacks:

- `handleException(...)`: errors during STOMP frame processing, such as failing to convert a payload or a handler throwing an exception.
- `handleTransportError(...)`: transport-layer errors, such as I/O failures or lost connections.

Do not check only `session.isConnected()` and treat it as proof that the broker can handle every message. An open connection does not guarantee valid destinations, active subscriptions, or a healthy broker.

## 6. Subscribing and Receiving Payloads with StompFrameHandler

`session.subscribe(destination, handler)` sends STOMP SUBSCRIBE and returns a `StompSession.Subscription`. The subscription serves as a handle to unsubscribe or track receipts when supported by the broker.

A handler for a DTO:

~~~java
StompFrameHandler frameHandler = new StompFrameHandler() {
    @Override
    public Type getPayloadType(StompHeaders headers) {
        return ChatMessage.class;
    }

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        ChatMessage message = (ChatMessage) payload;
        // Pass result to queue/latch for the test thread to verify.
    }
};
~~~

The two methods have distinct roles:

1. `getPayloadType(headers)` is called first to determine the Java type the MessageConverter should produce.
2. `handleFrame(headers, payload)` receives the headers and the converted object.

You can return `String.class`, `byte[].class`, a DTO, or an appropriate `Type`. If the payload is a JSON object, the DTO must be compatible with Jackson. If the payload has a generic type such as `List<ChatMessage>`, declare the full generic `Type` instead of returning just `List.class`.

The `handleFrame` callback runs on the client's message-handling thread. Keep the callback brief: put the payload into a `BlockingQueue`, complete a `CompletableFuture`, or decrement a `CountDownLatch`. Do not put complex assertions or blocking work inside the callback; errors thrown inside the callback may be routed to `handleException` instead of directly failing the test method.

## 7. Synchronizing Subscriptions Before Sending Messages

This is one of the most common sources of flaky tests.

Calling `subscribe` sends the SUBSCRIBE frame asynchronously. The `subscribe` method returning does not by itself prove that the broker has finished processing the frame and registered the subscription. Sending a message immediately can create a race: the server publishes the message before the subscription is registered.

### 7.1. Using RECEIPT When Supported by the Broker

STOMP defines a RECEIPT frame. The client sends a `receipt` header in a SUBSCRIBE or SEND frame; the server/broker returns RECEIPT after processing that frame. `StompSession.Receiptable` lets you register callbacks for receipt arrival or receipt expiration.

Example:

~~~java
StompHeaders subscribeHeaders = new StompHeaders();
subscribeHeaders.setDestination("/topic/replies");
subscribeHeaders.setReceipt("subscribe-ready");

StompSession.Subscription subscription =
    session.subscribe(subscribeHeaders, frameHandler);

CountDownLatch subscribed = new CountDownLatch(1);
AtomicReference<Throwable> receiptFailure = new AtomicReference<>();

subscription.addReceiptTask(subscribed::countDown);
subscription.addReceiptLostTask(() ->
    receiptFailure.set(new AssertionError("SUBSCRIBE receipt expired")));

assertTrue(subscribed.await(5, TimeUnit.SECONDS));
assertNull(receiptFailure.get());
~~~

To track receipts, WebSocketStompClient must be configured with a TaskScheduler. You can call `session.setAutoReceipt(true)` to automatically add a receipt header to subsequent SEND and SUBSCRIBE commands; if you want per-command control, add the receipt header manually as shown.

**Note:** Spring's in-memory `enableSimpleBroker` does not support RECEIPT. Do not enable auto-receipt and wait forever when testing against the simple broker. Receipt-based synchronization is appropriate when testing with a broker relay or a STOMP broker that supports RECEIPT.

A receipt confirms that the frame was processed according to broker/server receipt semantics. It does not prove that another subscriber processed business logic or committed data.

### 7.2. When Using the Simple Broker

With the simple broker, do not use RECEIPT as a barrier. You can choose one of the following approaches:

- Design the test fixture with an application-level readiness signal and verify that signal before publishing.
- Observe server-side subscription events in the test harness and coordinate with the appropriate broker state.
- If the goal is solely to verify controller methods and annotations, use server-side tests with `clientInboundChannel`.
- Use a real broker relay in tests that need to verify receipts, ACK/NACK, or broker-specific behavior.

Avoid resolving races with `Thread.sleep(...)`. Sleeping only waits for a guessed duration; it does not prove that the desired condition occurred.

## 8. Sending Messages and Awaiting Asynchronous Results

Once the subscription is ready, send the message:

~~~java
session.send("/app/echo", new ChatMessage("hello"));
~~~

To receive messages, use a `BlockingQueue`:

~~~java
BlockingQueue<ChatMessage> received = new LinkedBlockingQueue<>();

// Inside handleFrame:
received.offer((ChatMessage) payload);

// On the test thread:
ChatMessage reply = received.poll(5, TimeUnit.SECONDS);

assertNotNull(reply, "No STOMP MESSAGE received before timeout");
assertEquals("HELLO", reply.text());
~~~

`poll(timeout, unit)` both waits for a message and enforces a time bound. If no message arrives, the test fails with a clear message. This is much more reliable than `Thread.sleep` followed by checking a variable that might not yet be updated.

If multiple messages must be verified, drain the required number of items from the queue. If ordering matters, compare sequence numbers or contents in arrival order. If stale messages from an earlier session could arrive, create per-test-ID destinations or check correlation IDs to prevent interference from other tests.

### 8.1. Correlation ID and Message Headers

When multiple tests run concurrently, include a unique ID in the payload or a custom STOMP header. When receiving responses, assert only on messages with the matching ID.

Example:

~~~java
StompHeaders headers = new StompHeaders();
headers.setDestination("/app/echo");
headers.add("x-test-id", testId);

session.send(headers, new ChatMessage("hello"));
~~~

Do not assume every custom header passes unchanged through the broker or maps into DTOs. When headers carry business data, explicitly verify where Spring reads and propagates those headers.

## 9. E2E Test Example with Spring Boot and JUnit

The following example assumes the application configures the `/ws` endpoint, `/app/echo` controller, and a broker relay supporting RECEIPT. The server runs on a random port; the test connects using a real WebSocketStompClient.

### 9.1. Dependencies

In a Spring Boot application, you need the WebSocket starter and test starter. Versions are managed by Spring Boot dependency management:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-websocket</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

The application also needs the Jackson dependency if tests serialize JSON DTOs. If tests use a broker relay, the STOMP broker must be started and configured for the test environment.

### 9.2. Test Class

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Type;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.messaging.converter.MappingJackson2MessageConverter;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompFrameHandler;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebSocketStompClientE2ETest {

    @LocalServerPort
    int port;

    private ThreadPoolTaskScheduler scheduler;
    private WebSocketStompClient stompClient;
    private StompSession session;

    @BeforeEach
    void setUp() {
        scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-test-");
        scheduler.initialize();

        stompClient = new WebSocketStompClient(
            new StandardWebSocketClient()
        );
        stompClient.setMessageConverter(
            new MappingJackson2MessageConverter()
        );
        stompClient.setTaskScheduler(scheduler);
        stompClient.setReceiptTimeLimit(5_000);
        stompClient.start();
    }

    @AfterEach
    void tearDown() {
        if (session != null && session.isConnected()) {
            session.disconnect();
        }
        if (stompClient != null) {
            stompClient.stop();
        }
        if (scheduler != null) {
            scheduler.shutdown();
        }
    }

    @Test
    void sendToControllerAndReceiveTopicMessage() throws Exception {
        BlockingQueue<ChatMessage> received =
            new LinkedBlockingQueue<>();
        BlockingQueue<Throwable> clientErrors =
            new LinkedBlockingQueue<>();

        String url = "ws://localhost:" + port + "/ws";

        session = stompClient.connectAsync(
            url,
            new StompSessionHandlerAdapter() {
                @Override
                public void handleException(
                        StompSession session,
                        StompCommand command,
                        StompHeaders headers,
                        byte[] payload,
                        Throwable exception) {
                    clientErrors.offer(exception);
                }

                @Override
                public void handleTransportError(
                        StompSession session, Throwable exception) {
                    clientErrors.offer(exception);
                }
            }
        ).get(5, TimeUnit.SECONDS);

        StompFrameHandler frameHandler = new StompFrameHandler() {
            @Override
            public Type getPayloadType(StompHeaders headers) {
                return ChatMessage.class;
            }

            @Override
            public void handleFrame(
                    StompHeaders headers, Object payload) {
                received.offer((ChatMessage) payload);
            }
        };

        StompHeaders subscribeHeaders = new StompHeaders();
        subscribeHeaders.setDestination("/topic/replies");
        subscribeHeaders.setReceipt("subscribe-ready");

        CountDownLatch subscribed = new CountDownLatch(1);
        AtomicReference<Throwable> receiptFailure =
            new AtomicReference<>();

        StompSession.Subscription subscription =
            session.subscribe(subscribeHeaders, frameHandler);

        subscription.addReceiptTask(subscribed::countDown);
        subscription.addReceiptLostTask(() ->
            receiptFailure.set(
                new AssertionError("SUBSCRIBE receipt was not received")
            )
        );

        assertTrue(
            subscribed.await(5, TimeUnit.SECONDS),
            "Subscription was not acknowledged"
        );
        assertNull(receiptFailure.get());

        session.send(
            "/app/echo",
            new ChatMessage("hello")
        );

        ChatMessage reply = received.poll(5, TimeUnit.SECONDS);

        assertNotNull(reply, "No reply received");
        assertEquals("HELLO", reply.text());
        assertTrue(
            clientErrors.isEmpty(),
            () -> "Unexpected STOMP client error: " + clientErrors.peek()
        );

        subscription.unsubscribe();
    }
}
~~~

This test proceeds step by step:

1. Starts the Spring application context with an embedded server and random port.
2. Creates WebSocketStompClient, Jackson converter, and scheduler.
3. Connects to the endpoint and awaits STOMP CONNECTED.
4. Subscribes to `/topic/replies` with a StompFrameHandler.
5. Awaits RECEIPT to confirm the broker relay processed SUBSCRIBE.
6. Sends ChatMessage to `/app/echo`.
7. Waits up to five seconds to receive the response DTO.
8. Checks content and client errors.
9. Unsubscribes; `@AfterEach` disconnects the session, stops the client, and shuts down the scheduler.

If using `enableSimpleBroker` instead of a broker relay, remove the receipt block and use a readiness mechanism suited to the test fixture. The simple broker does not send RECEIPT, so the test above requires a broker supporting receipts.

In real test code, remove unused imports, place DTOs in an appropriate source/test package, and match the application's actual class packages. `@LocalServerPort` injects the port assigned by Spring Boot for the `RANDOM_PORT` server.

## 10. STOMP Receipts, ACK/NACK, and Broker Relay

### 10.1. What Does a Receipt Confirm?

STOMP RECEIPT is a response to a frame for which the client requested a receipt. `StompSession.setAutoReceipt(true)` automatically adds a receipt header to subsequent SEND and SUBSCRIBE commands. Callbacks can be registered via `Receiptable.addReceiptTask(...)` and `addReceiptLostTask(...)`.

Receipts are useful to:

- Confirm the broker processed SUBSCRIBE before the test publishes.
- Confirm the broker processed a SEND frame per receipt semantics.
- Detect when the broker fails to return a receipt within the deadline.

A receipt is not an application-level acknowledgement. For example, a SEND receipt does not prove that a consumer ran business logic or wrote data to a database. To confirm that, you need a separate response/event or business state check.

### 10.2. ACK and NACK

STOMP provides ACK/NACK so consumers can acknowledge or reject processed messages. When using them, subscriptions must set the `ack` header to `client` or `client-individual`; the client then calls `session.acknowledge(...)` accordingly.

Spring's simple broker does not fully support ACK/NACK. When tests need to verify message acknowledgement semantics, redelivery, or durable queues, use a real broker and test against the actual broker type being deployed.

### 10.3. Broker Relay vs. Simple Broker

| Criterion | Simple Broker | Broker Relay |
| --- | --- | --- |
| Purpose | Getting started, basic flow tests, in-memory broker | Connecting to a dedicated STOMP broker |
| Subscriptions | Stored in application memory | Forwarded to the broker |
| Receipt / ACK | Not fully supported; simple broker does not support RECEIPT or ACK/NACK | Depends on broker capabilities |
| Clustering / durability | Unsuitable for distributed brokers or durable storage | Uses dedicated broker features |
| Testing | Fast with minimal dependencies | Closer to production, but requires a broker |

Do not conclude that a production system using RabbitMQ/ActiveMQ works properly just because tests with the simple broker pass. E2E tests with the simple broker verify in-memory Spring endpoint/controller/broker integration; tests with a broker relay additionally verify external broker connectivity and semantics.

## 11. Error and Transport Testing

### 11.1. STOMP ERROR

The server can send an ERROR frame when receiving an invalid frame, an unaccepted destination, or a processing failure per server/broker policy. Because StompSessionHandler is a StompFrameHandler, StompSessionHandlerAdapter can handle ERROR frames.

When testing errors, verify:

- Whether an ERROR frame is sent back to the client.
- Whether error headers/body contain the expected code or details.
- Whether the session remains usable or was closed by the server.
- Whether the application leaks stack traces or sensitive data in error payloads.

### 11.2. Callback Errors and Transport Errors

`handleException` handles exceptions thrown while processing STOMP frames, such as a converter failing to parse JSON or a handler throwing an error. `handleTransportError` handles transport failures such as I/O errors or dropped connections.

Push errors into a `BlockingQueue<Throwable>` or `AtomicReference` so the test thread can inspect them afterward. Never swallow errors in callbacks. If errors are ignored, the test may simply time out in `received.poll` and misreport the root cause as the server failing to send a message.

### 11.3. Connection Loss and Reconnect

When the transport drops, the current session is no longer reliable. Reconnecting typically creates a new STOMP session; destinations must be re-subscribed and necessary client state restored. The broker relay does not automatically reconnect every client session on the application's behalf.

When testing reconnects, explicitly verify:

1. `handleTransportError` receives the error.
2. The old session is considered disconnected.
3. The client establishes a new connection and receives CONNECTED.
4. The client recreates its subscriptions.
5. Post-reconnect messages are received with the exact multiplicity required by business rules.

Do not reuse subscription handles from the old session.

## 12. Authentication, Headers, and SockJS

### 12.1. WebSocket Handshake Headers vs. STOMP CONNECT Headers

`connectAsync` has overloads accepting `WebSocketHttpHeaders` for the HTTP handshake and `StompHeaders` for STOMP CONNECT. These are two distinct phases:

- HTTP handshake headers are sent during the WebSocket upgrade request.
- STOMP CONNECT headers are sent after the WebSocket connection is open.

When testing authentication, place tokens/cookies on the exact layer checked by server security. Do not assume headers sent in STOMP CONNECT also appear during the HTTP handshake.

### 12.2. Destinations and Authorization

Test both allowed and denied cases:

- Can an unauthenticated client open the endpoint?
- Is the user allowed to SEND to `/app/...`?
- Is the user allowed to SUBSCRIBE to `/topic/...` or `/user/queue/...`?
- Are messages targeted at another user blocked?
- Does the server enforce authorization per message, not only at handshake time?

Create separate sessions with separate principals/credentials so an authenticated session does not skew results for another session's test.

### 12.3. SockJS

If the endpoint registers `addEndpoint("/ws").withSockJS()`, tests must use an appropriate SockJS client. For direct WebSocket, use `StandardWebSocketClient` and a `ws://...` URL; for SockJS, use `SockJsClient` and an HTTP endpoint URL matching the SockJS configuration. Test fallback transports only when the application truly needs to support those fallbacks.

## 13. Layered Testing Strategy

Not every scenario requires running a real server and broker.

| Test Type | Tools / Setup | What to Test |
| --- | --- | --- |
| Service unit test | JUnit, Mockito | Business logic independent of STOMP. |
| Controller/message handler test | `clientInboundChannel` and Spring messaging infrastructure | Mapping annotations, argument conversion, validation, return destinations. |
| WebSocket E2E with simple broker | Embedded server + `WebSocketStompClient` | Handshake, STOMP session, converters, routing, and in-Spring message delivery. |
| WebSocket E2E with broker relay | Embedded server + real broker + `WebSocketStompClient` | Broker connectivity, receipts, ACK/NACK, and broker-specific behavior. |
| Browser/client compatibility | Real browser or corresponding client | Cookies, CORS/origin, SockJS, browser behavior, and reconnects. |
| Load/performance | Multiple clients and production-like broker | Throughput, latency, connection counts, scheduler/heartbeats, and broker capacity. |

Keep E2E tests focused on critical flows. Test controllers and business logic with lighter tests; reserve a real broker for features that depend on broker behavior.

## 14. Common Mistakes and Fixes

| Error | Cause | How to Fix |
| --- | --- | --- |
| Test times out at `connectAsync` | Wrong URL/port, server not ready, wrong endpoint path, or STOMP CONNECT rejected. | Use `RANDOM_PORT`, verify endpoint path, and inspect `handleTransportError`/ERROR. |
| WebSocket connects but test has no session | WebSocket handshake finished, but STOMP CONNECTED has not arrived. | Wait for the `connectAsync` Future to complete before using the session. |
| Payload arrives as `String` or `byte[]` | Incorrect `getPayloadType` or `MessageConverter`. | Return `DTO.class` and configure the matching converter. |
| No message received after send | Wrong destination, wrong controller mapping, wrong broker prefix, or subscribe not yet processed. | Verify `/app`, `/topic`, `@MessageMapping`, `@SendTo`, and subscription synchronization. |
| Test flakes due to `Thread.sleep` | Sleeping does not prove the broker registered the subscription. | Use RECEIPT when supported by the broker or an application-layer readiness barrier. |
| Receipt never arrives | Simple broker does not support RECEIPT, or broker lacks that configuration. | Use a broker relay supporting receipts, or omit receipts in simple-broker tests. |
| Assertion fails in `handleFrame` but test does not fail properly | Callback runs on client thread and errors are routed to the exception callback. | Push payloads into a queue/future and assert on the test thread. |
| Test hangs when server disconnects | Missing timeout on Future, poll, or latch. | Use `get`/`poll`/`await` with timeouts on every async wait point. |
| Another test receives the wrong message | Shared destination across parallel tests. | Use correlation IDs, dedicated destinations, or clean up subscriptions. |
| Client keeps threads alive after test | Client or scheduler not stopped. | Disconnect, stop `WebSocketStompClient`, and shut down `TaskScheduler` in `finally`/`AfterEach`. |
| Using simple broker to test ACK/RECEIPT | Simple broker supports only a STOMP subset. | Run a real broker when those features must be tested. |
| Checking only that `client.send` throws no error | Local API send success does not prove server processing succeeded. | Wait for the response/message or an application-level acknowledgement. |

## 15. Checklist for a Stable E2E Test

Before finishing a test, verify:

1. The server actually runs in a web environment supporting WebSocket, typically `RANDOM_PORT`.
2. The client uses the exact endpoint URL and transport.
3. `connectAsync` completes before operating on the session.
4. `MessageConverter` is compatible with DTOs and content type.
5. Subscriptions target the right destination and are synchronized before sending.
6. Every `poll`, `await`, and `get` uses a finite timeout.
7. Callbacks only forward data/errors to the test thread without blocking.
8. Assertions check the content, headers, or correlation IDs actually required.
9. Receipt/ACK are used only when supported by the broker.
10. Subscriptions are unsubscribed, sessions disconnected, clients stopped, and schedulers shut down.
11. Tests are independent when run in parallel, without shared destinations/IDs that could cross-deliver messages.
12. Transport errors and STOMP ERROR frames are captured so failure messages are actionable.

## 16. Key Takeaways

- WebSocketStompClient is a STOMP client built on WebSocketClient, suitable for E2E tests against a real server.
- `connectAsync` completes when the STOMP session receives CONNECTED; a successful WebSocket handshake alone is not enough.
- MessageConverter serializes payloads on send and deserializes them into the type returned by `StompFrameHandler.getPayloadType`.
- `subscribe` is asynchronous; synchronize subscription state before publishing if ordering matters.
- Use RECEIPT as a barrier only when the broker supports it; Spring's simple broker does not support RECEIPT or ACK/NACK.
- Use `BlockingQueue.poll` or `CountDownLatch.await` with timeouts instead of `Thread.sleep`.
- Collect errors via `handleException` and `handleTransportError`.
- Clean up subscriptions, sessions, WebSocketStompClient, and TaskScheduler so tests do not leak connections or threads.
- E2E tests with the simple broker do not replace real-broker tests when production relies on broker-specific behavior.

## 17. References

- [Spring Framework Reference — Testing STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/testing.html): server-side tests and end-to-end integration tests.
- [Spring Framework Reference — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html): WebSocketStompClient, connect, send, subscribe, heartbeats, and receipts.
- [Spring Framework Reference — STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html): destination routing, annotated controllers, simple broker, and broker relay.
- [WebSocketStompClient Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html): API of the STOMP client over WebSocket.
- [StompSession Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.html): send, subscribe, receipts, acknowledgement, and disconnect.
- [StompFrameHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompFrameHandler.html): declaring payload types and handling frames.
- [STOMP 1.2 Specification](https://stomp.github.io/stomp-specification-1.2.html): CONNECT, CONNECTED, SEND, SUBSCRIBE, MESSAGE, RECEIPT, ACK, NACK, and DISCONNECT.
