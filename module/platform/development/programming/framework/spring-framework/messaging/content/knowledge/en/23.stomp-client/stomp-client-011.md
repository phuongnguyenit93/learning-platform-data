# Graceful Disconnection and Releasing STOMP Client Resources in Spring

## Learning Objectives

After this lesson, you can:

- Distinguish canceling a single subscription, disconnecting a STOMP session, and stopping an entire WebSocket client.
- Send STOMP `UNSUBSCRIBE` and `DISCONNECT` at the right time.
- Design a shutdown sequence to stop emitting messages, release subscriptions, close connections, and stop client-owned components.
- Manage the lifecycles of `WebSocketStompClient`, `WebSocketClient`, `TaskScheduler`, and HTTP clients without inadvertently closing shared resources.
- Handle race conditions between asynchronous connections and shutdown requests.
- Distinguish intentional disconnection from transport errors, timeouts, and reconnects.
- Make server-side cleanup safe when disconnect events fire multiple times.

This article focuses on Java STOMP over WebSocket with Spring Framework. Examples use APIs available in Spring Framework 6.x and newer; differences between Spring 6.2 and 7.0 are noted explicitly where they affect source code.

## 1. Multi-layered client lifecycle

A STOMP client typically owns or interacts with multiple objects having different lifecycles:

| Component | Responsibility | How to terminate |
|---|---|---|
| `StompSession` | Connected STOMP session, sending messages, managing subscriptions | `disconnect()` |
| `StompSession.Subscription` | A single subscription receiving messages at a destination | `unsubscribe()` |
| WebSocket connection | Underlying bidirectional transport channel beneath STOMP | Closed when session ends; raw API has `WebSocketSession.close()` |
| `WebSocketStompClient` | Manages STOMP connections over WebSocketClient | `stop()` per client lifecycle |
| `WebSocketClient` | Transport implementation such as Standard, Jetty, or SockJS | Stopped if implementation supports `Lifecycle` |
| `TaskScheduler` | Runs heartbeat tasks and receipt tracking | Stopped by scheduler owner |
| HTTP client / connection pool | Supports SockJS XHR transport or custom transports | Closed by HTTP client owner |

Not every object shares the same owner. An application may share one `WebSocketStompClient` and one `TaskScheduler` across multiple sessions. In that case, closing one session must not stop the shared client or shared scheduler.

## 2. Distinguishing UNSUBSCRIBE, DISCONNECT, and WebSocket CLOSE

These three operations serve different purposes:

- **UNSUBSCRIBE:** cancels one subscription. The STOMP session stays active and can continue sending messages or subscribing to other destinations.
- **DISCONNECT:** terminates the entire STOMP session. All subscriptions tied to that session are released when the session ends.
- **WebSocket CLOSE:** closes the transport connection at the WebSocket layer. This is a low-level operation and does not replace the semantics of STOMP DISCONNECT.

Example of a session listening to two destinations:

~~~text
STOMP session S1
  +-- subscription sub-1 -> /topic/orders
  +-- subscription sub-2 -> /topic/notifications
~~~

To stop only order notifications, send UNSUBSCRIBE for `sub-1`; `sub-2` continues working. If the application is shutting down completely, send DISCONNECT for session S1 to end the session and release both subscriptions.

Do not close the raw WebSocket first and hope the broker receives a STOMP DISCONNECT. When you have a `StompSession`, use the session's STOMP API to end the session according to protocol.

## 3. Canceling a subscription while the session remains active

`StompSession.subscribe` returns a `StompSession.Subscription` handle. Retain this handle if you later need to cancel that individual subscription:

~~~java
StompSession.Subscription updates = session.subscribe(
        "/topic/updates",
        new StompFrameHandler() {

            @Override
            public Type getPayloadType(StompHeaders headers) {
                return String.class;
            }

            @Override
            public void handleFrame(
                    StompHeaders headers,
                    Object payload) {
                System.out.println("Update: " + payload);
            }
        });

// When /topic/updates is no longer needed:
updates.unsubscribe();
~~~

`unsubscribe()` sends a STOMP UNSUBSCRIBE frame for that subscription. The session stays connected and other subscriptions keep running.

Notes to keep in mind:

1. Retain handles for each subscription the application needs to cancel independently.
2. Do not create new subscriptions on each reconnect while forgetting to clean up the old session.
3. Once a session has lost connection, there is no need to send UNSUBSCRIBE for every old handle; the broker cleans up session-bound subscriptions when the connection ends.
4. Unsubscribing does not delete data in the broker or database; it only stops receiving messages through that subscription.

### API difference between Spring 6.2 and 7.0

In Spring 6.2, `Subscription.unsubscribe()` returns `void`. Starting in Spring 7.0, this method returns `StompSession.Receiptable`, allowing receipt tracking if the broker supports it and the client has configured a `TaskScheduler`.

Do not write code relying on the return value of `unsubscribe()` if the project must remain compatible with Spring 6.2. Check the Javadoc for your exact version.

## 4. Ending the entire STOMP session

`StompSession.disconnect()` sends the STOMP DISCONNECT frame. The interface also provides an overload accepting `StompHeaders` to pass additional headers.

~~~java
if (session != null && session.isConnected()) {
    session.disconnect();
}
~~~

In Spring's default implementation, disconnecting sends the DISCONNECT frame and then resets and closes the underlying transport connection. The public API commits to terminating the STOMP session by sending DISCONNECT.

After disconnecting:

- The session is no longer an active session for sending messages.
- Subscriptions tied to the session are terminated.
- The client must establish a new STOMP session if it wants to reconnect.
- Old subscription handles must not be reused for a new session.

`isConnected()` checks the session's current state. However, this state is not an instant remote network probe. If the network just dropped and heartbeats or error callbacks have not processed yet, the observed state may not immediately reflect reality.

## 5. A safe shutdown sequence

When the application proactively stops the client, follow this sequence:

1. Mark the client as shutting down so no new connections or reconnects are initiated.
2. Stop business tasks that are emitting messages through the session.
3. Cancel individual subscriptions if the session still needs to stay alive briefly. If closing the entire session immediately, DISCONNECT terminates all subscriptions.
4. Send DISCONNECT for active STOMP sessions.
5. Clear session and subscription references to avoid retaining unused objects.
6. Stop `WebSocketStompClient` if the current component owns that client.
7. Close dedicated HTTP clients, schedulers, or executors only after all sessions and clients using them have finished.

Example method to terminate a session:

~~~java
private final AtomicReference<StompSession> sessionRef =
        new AtomicReference<>();

public void disconnectSession() {
    StompSession current = sessionRef.getAndSet(null);

    if (current != null && current.isConnected()) {
        current.disconnect();
    }
}
~~~

Using `getAndSet(null)` ensures only one thread claims ownership of terminating the current session. If multiple threads invoke shutdown concurrently, subsequent calls will not retrieve the same reference.

If the application exclusively owns `WebSocketStompClient`, it can stop it after ending the session:

~~~java
public void closeOwnedClient() {
    try {
        disconnectSession();
    }
    finally {
        stompClient.stop();
    }
}
~~~

If `WebSocketStompClient` is shared across multiple sessions or components, do not call `stop()` when only one session ends. Stop the client only when the application-level owner decides the entire client is no longer used.

## 6. Stopping WebSocketStompClient and managing Lifecycle

`WebSocketStompClient` implements `SmartLifecycle`. It provides `start()`, `stop()`, `isRunning()`, and phase configuration for startup and shutdown ordering.

When managed as a Spring bean:

- `autoStartup` defaults to `true`.
- Spring's Lifecycle processor can automatically start and stop the client when the ApplicationContext refreshes or closes.
- `setPhase` adjusts startup and shutdown order. Components with higher phase values start later and stop earlier.
- `stop()` stops the contained `WebSocketClient` if that implementation also implements `Lifecycle`.

Bean configuration example:

~~~java
@Configuration
public class StompClientConfiguration {

    @Bean
    public WebSocketStompClient webSocketStompClient(
            WebSocketClient webSocketClient,
            TaskScheduler taskScheduler) {

        WebSocketStompClient client =
                new WebSocketStompClient(webSocketClient);

        client.setTaskScheduler(taskScheduler);
        client.setInboundMessageSizeLimit(64 * 1024);
        client.setPhase(100);

        return client;
    }
}
~~~

In the example, `WebSocketClient` and `TaskScheduler` are injected from the container. The client bean uses the scheduler for heartbeats and receipt tracking. The container manages bean lifecycles according to their `Lifecycle` configuration.

If the application needs to send DISCONNECT before the client transport is stopped, the component holding `StompSession` instances must perform cleanup in an appropriate shutdown phase. Do not rely solely on `WebSocketStompClient.stop()` to replace disconnecting individual sessions.

## 7. Distinguishing client-owned resources from shared resources

This is the most important principle when releasing resources.

### Per-session resources

- Current `StompSession`.
- Subscription handles of that session.
- Heartbeat or receipt tasks tied to that session.
- Callbacks or listeners held by the component specifically for that session.

When a session ends, clear these references and stop associated application tasks.

### Per-client resources

- `WebSocketStompClient`.
- `WebSocketClient` implementation.
- SockJS HTTP transport client if present.
- Dedicated connection pools or executors created by the client.

Close these only after every session using the client has terminated and the owner no longer needs the client.

### Application-shared resources

- `TaskScheduler` used by multiple clients or services.
- Shared executors.
- Shared HTTP connection pools.
- Beans managed by the Spring container.

Do not shut down shared resources from a single session's close method. Let the container or top-level owner execute shutdown at the proper time.

## 8. Heartbeats and TaskScheduler

`WebSocketStompClient` can use a `TaskScheduler` for STOMP heartbeats and receipt tracking. When a scheduler is configured, the client enables appropriate default heartbeats if heartbeats were previously disabled.

Example:

~~~java
stompClient.setTaskScheduler(taskScheduler);
~~~

Each session may schedule tasks to monitor connection liveness. When the session terminates, session state management and related tasks must conclude cleanly.

Do not do the following when a single session closes:

~~~java
// Do not do this if the scheduler is still used by other sessions:
((ThreadPoolTaskScheduler) taskScheduler).shutdown();
~~~

Shutting down a shared scheduler disrupts heartbeats and receipt tracking for all other sessions.

If the application creates a dedicated scheduler serving only one client owner, stop that scheduler after the owner has closed all sessions and stopped the client. If the scheduler is a shared Spring bean, let Spring manage that bean's lifecycle.

Heartbeats detect inactive connections. They do not replace an intentional DISCONNECT operation, nor do they guarantee all business messages have been processed.

## 9. Closing transport with plain WebSocket or SockJS

When using STOMP, the application layer should terminate via `StompSession.disconnect()`. The `WebSocketSession.close()` API belongs to the transport layer and typically appears in code working directly with WebSocket.

`WebSocketSession.close()` closes the WebSocket connection with normal close status 1000; another overload allows specifying a close status. If code holds a raw `WebSocketSession` without STOMP, close it following the raw WebSocket lifecycle.

With `SockJsClient`, the transport may be WebSocket or an HTTP fallback. The application should not assume every session has the same raw WebSocket object. Use the `StompSession` API to terminate the STOMP session, and let the SockJS transport release associated requests and sessions.

If supplying a custom-created HTTP client or Jetty client, its owner must stop or close that resource via the implementation's API. `WebSocketStompClient.stop()` only forwards stop to its delegate if the delegate implements `Lifecycle`; it cannot automatically close arbitrary custom resources created externally by the application.

## 10. Handling asynchronous connections and race conditions

STOMP connections are typically asynchronous. The following situation can occur:

1. The application initiates connect.
2. Shutdown starts before STOMP CONNECTED is received.
3. The `afterConnected` callback executes after the application already marked shutdown.
4. A new session is established while the application is closing.

If the callback does not check shutdown state, the application can accidentally create new subscriptions or keep an unclosed session alive.

Handling pattern:

~~~java
private final AtomicBoolean closing = new AtomicBoolean(false);
private final AtomicReference<StompSession> sessionRef =
        new AtomicReference<>();

public void onConnected(StompSession connected) {
    if (closing.get()) {
        connected.disconnect();
        return;
    }

    sessionRef.set(connected);

    // Create subscriptions after the session is ready.
}

public void close() {
    closing.set(true);

    StompSession current = sessionRef.getAndSet(null);
    if (current != null && current.isConnected()) {
        current.disconnect();
    }
}
~~~

This is a lifecycle handling skeleton; if connect callbacks and shutdown can run concurrently in the application, synchronize session registration so there is no window between checking `closing` and `sessionRef.set` where a session gets missed.

With multiple threads or multiple concurrent connections, use a lock, a state machine, or a connection owner with atomic state transitions. Do not rely solely on separate boolean flags if multiple callbacks can mutate the session simultaneously.

## 11. Distinguishing intentional shutdown from transport errors

`StompSessionHandler` provides key callbacks:

- `afterConnected`: STOMP session received CONNECTED and is ready.
- `handleTransportError`: a transport-layer error occurred, such as lost connection.
- `handleException`: error while processing messages or callbacks.
- `handleFrame`: processes STOMP frames, including ERROR frames in the appropriate handler.

When the user or application intentionally shuts down, mark the closing state before calling `disconnect()`. If an error callback arrives afterward, do not trigger a reconnect.

When an unexpected transport error occurs, clear the broken session reference and decide whether to reconnect per application policy. A successful reconnect creates a new session; the application must re-register required destinations.

Do not treat `handleTransportError` as a command to shut down the application. It is a signal to update connection state and apply a recovery policy.

## 12. Reconnecting must create a new session and new subscriptions

After a connection breaks, do not reuse the old session or old subscription handles. Typical recovery flow:

1. Mark the current session inactive.
2. Clear references to the old session and subscriptions.
3. If the application is not shutting down, wait using exponential backoff with jitter.
4. Create a new STOMP connection.
5. Wait for the `afterConnected` callback.
6. Re-register required destinations.
7. Synchronize missed data via an API or history mechanism if required by business logic.

Distinguish two situations:

| Situation | Action |
|---|---|
| Application intentionally closes | Do not reconnect |
| Unexpected network or server drop | May reconnect per retry policy |
| Authentication expired | Refresh credentials before retrying |
| Server returns STOMP ERROR | Analyze error; do not retry indefinitely on config or permission errors |
| Shutdown during connect | Disconnect the session immediately when the connect callback arrives and do not subscribe |

Retries must have limits, jitter, and cancellation capability. If thousands of clients reconnect simultaneously after a server recovers, randomized jitter helps dampen traffic spikes.

## 13. Server-side cleanup via SessionDisconnectEvent

On the Spring server side, `SessionDisconnectEvent` is published when a STOMP session ends. The event can fire when a client sends DISCONNECT or when the WebSocket session closes.

Spring notes that a single session can generate more than one disconnect event in certain cases. Therefore, server cleanup must be idempotent.

Example:

~~~java
@Component
public class StompSessionCleanupListener {

    private final ConcurrentMap<String, Boolean> activeSessions =
            new ConcurrentHashMap<>();

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        String sessionId = event.getSessionId();

        if (activeSessions.remove(sessionId) != null) {
            // Perform business cleanup only once.
            // For example: mark user offline or release presence.
        }
    }
}
~~~

The example assumes the map is populated when the session connects. In real systems, presence updates must be designed safely against races among disconnect, reconnect, and multiple nodes. Do not use disconnect events as the sole source of truth for critical business state if high durability is required.

Other related events:

- `SessionConnectEvent`: STOMP CONNECT received.
- `SessionConnectedEvent`: broker responded with CONNECTED.
- `SessionSubscribeEvent`: client sent SUBSCRIBE.
- `SessionUnsubscribeEvent`: client sent UNSUBSCRIBE.
- `SessionDisconnectEvent`: session ended.

These events are helpful for monitoring and state management, but do not replace durable business data persistence.

## 14. Receipts when needing to know the broker processed an operation

STOMP has a RECEIPT mechanism so the server/broker confirms processing a frame carrying a `receipt` header. Spring clients can use `setAutoReceipt(true)` to automatically add receipt headers to subsequent send and subscribe operations, or add the header manually.

To track receipts, configure a `TaskScheduler` and appropriate receipt timeout. The broker must also support receipts.

Version notes:

- `send` and `subscribe` return `Receiptable` to track receipts.
- `Subscription` is also a `Receiptable`.
- Starting in Spring 7.0, `unsubscribe()` returns `Receiptable`; in Spring 6.2, this method returns `void`.
- `StompSession.disconnect()` returns `void`; there is no direct `Receiptable` handle from this method.

For normal shutdown, there is no need to wait for a receipt on every UNSUBSCRIBE if the application is about to close the entire session right afterward. If you need confirmation that a subscription operation was processed by the broker while the session stays open, design specifically for your broker's capabilities and Spring version.

A receipt only confirms the broker processed the frame per the protocol. It does not prove a subscribing client finished business processing.

## 15. Common mistakes and fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Calling only `WebSocketStompClient.stop()` without managing sessions | No explicit STOMP DISCONNECT sequence per session | Keep session handles and call `disconnect()` before stopping the client |
| Calling `disconnect()` for each subscription | Wrong API; one session can hold multiple subscriptions | Use `Subscription.unsubscribe()` to cancel individually; use `StompSession.disconnect()` to close the whole session |
| Closing raw WebSocket before sending DISCONNECT | Broker may only see an abrupt connection loss | Close via `StompSession.disconnect()` when using STOMP |
| Shutting down a shared scheduler when one session closes | Heartbeats/receipts for other sessions stop working | Let the scheduler owner manage shutdown |
| Calling `stompClient.stop()` when one of several sessions ends | Other components lose client transport | Stop the client at the owner level once all sessions are closed |
| Reconnecting after intentional shutdown | New connections appear while the app is stopping | Use a shutdown flag and cancel retry tasks |
| Reusing old subscription handles after reconnect | Subscriptions do not belong to the new session | Create new subscriptions on the new session |
| Non-idempotent server cleanup | Presence or resources released multiple times | Check state and handle duplicate disconnects safely |
| Failing to manage SockJS custom HTTP client | Connection pool or executor keeps running after shutdown | Close resources per ownership and implementation lifecycle |

## 16. Testing lifecycle and resource release

A test suite should cover:

| Scenario | What to verify |
|---|---|
| Cancel one subscription | Client stops receiving that destination; session still sends/receives normally |
| Disconnect entire session | STOMP DISCONNECT is sent and transport closes |
| Close session twice | Safe cleanup, no errors from repeated release |
| Two sessions sharing one client | Closing one session does not disrupt the remaining session |
| Two sessions sharing one scheduler | Closing one session does not halt the other's heartbeats |
| Shutdown during connect | Late-arriving session is closed and creates no subscriptions |
| Transport error | Old session is discarded, reconnect is bounded |
| Shutdown while reconnecting | Retry task is cancelled, no new connection is created |
| Server receives duplicate disconnect events | Business cleanup finishes only once |
| ApplicationContext closes | Lifecycle beans stop by phase and owned resources are released |

During load tests, monitor active session count, subscription count, heartbeat task count, thread count, TCP/HTTP connections, connection pools, heap, and shutdown duration. A client is cleanly shut down when no unexpected active sessions remain, no retry tasks remain, and all client-owned resources have stopped.

## 17. Production readiness checklist

- [ ] Every active session has a clear owner.
- [ ] Subscription handles are retained when independent cancellation is needed.
- [ ] Shutdown stops sending messages and reconnecting before closing sessions.
- [ ] Use `StompSession.disconnect()` to terminate the entire STOMP session.
- [ ] Call `WebSocketStompClient.stop()` only at the client owner level.
- [ ] Shared schedulers are never shut down by an individual session.
- [ ] Custom HTTP clients, connection pools, and executors are closed according to ownership.
- [ ] Reconnecting creates a new session and new subscriptions.
- [ ] Server-side cleanup handles duplicate disconnect events safely.
- [ ] Tested shutdown during connect, while receiving messages, and during transport errors.
- [ ] Verified APIs against the project's exact Spring Framework version.

## References

- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)
- [Spring Framework — Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework Javadoc — StompSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.html)
- [Spring Framework Javadoc — StompSession.Subscription](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompSession.Subscription.html)
- [Spring Framework Javadoc — WebSocketStompClient](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/WebSocketStompClient.html)
- [Spring Framework Javadoc — WebSocketSession](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/WebSocketSession.html)
