# WebSocket Scope and Per-Session Data Lifecycle

## 1. What Is WebSocket Scope?

In a Spring WebSocket/STOMP application, a user can open multiple concurrent connections: multiple browser tabs, multiple windows, or multiple devices. Each WebSocket session may need a small amount of dedicated data, such as temporary operation context, UI selections, progress of a connection-bound task, or short-lived resources that must be released when the session ends.

If this data is placed in a singleton service, all WebSocket sessions can access the same instance and accidentally share data. If placed in the HTTP session, the data scope is the entire HTTP session, which may be shared by multiple WebSocket sessions.

Spring provides **WebSocket scope** to manage beans according to the lifecycle of a WebSocket session. Each session gets its own instance for each bean in this scope. Spring creates the instance when the bean is first accessed in the session, stores it in session attributes, and returns the same instance on subsequent accesses. When the WebSocket session ends, Spring invokes the bean's lifecycle callbacks, including **@PreDestroy**.

WebSocket scope is suited for short-lived, connection-scoped state. Business data that must survive after the user closes the browser or reconnects still needs to be stored in a database or appropriate persistence store.

## 2. Distinguishing WebSocket Scope from Other Scopes

| Scope | Lifetime Scope | Usage Example |
|---|---|---|
| **singleton** | One instance per bean definition in the Spring container. | Stateless services shared across the entire application. |
| **prototype** | New instance every time the container creates the bean. | Short-lived objects explicitly created by the application. |
| **request** | One HTTP request. | Data used only within a single request. |
| **session** | One HTTP session. | Data tied to an HTTP login session. |
| **websocket** | One WebSocket session. | Dedicated workspace or context for a STOMP connection. |

WebSocket scope is not synonymous with HTTP session scope:

- One HTTP session can open multiple WebSocket sessions.
- Each WebSocket session has its own WebSocket-scoped beans.
- Two tabs of the same user typically have two separate WebSocket sessions, so they do not share WebSocket-scoped instances.
- When a WebSocket reconnect creates a new session, beans from the old session do not automatically transfer to the new session, even if the HTTP session cookie is still valid.

~~~mermaid
flowchart TD
    U["One user / HTTP session"] --> W1["WebSocket session A"]
    U --> W2["WebSocket session B"]
    W1 --> A["WebSocket-scoped bean A"]
    W2 --> B["WebSocket-scoped bean B"]
    A -. "No shared instance" .- B
~~~

Choose the scope based on the real lifecycle of the data. Use singleton for shared, thread-safe logic; use WebSocket scope for short-lived context of a single connection; use HTTP session scope when data must be shared across an HTTP login session.

## 3. Session Attributes Data

Each WebSocket session has an attributes map. Spring attaches this map to the headers of inbound client messages. Controllers can access it via **SimpMessageHeaderAccessor.getSessionAttributes()**:

~~~java
import java.time.Instant;
import java.util.Map;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.stereotype.Controller;

@Controller
public class SessionMetadataController {

    @MessageMapping("/session/touch")
    public void touch(SimpMessageHeaderAccessor headers) {
        Map<String, Object> attributes = headers.getSessionAttributes();

        if (attributes != null) {
            attributes.put("lastActionAt", Instant.now());
            attributes.put("lastAction", "touch");
        }
    }
}
~~~

In the example, **lastActionAt** and **lastAction** belong to the current session. Another WebSocket session has its own attributes map.

You can retrieve the session id with **headers.getSessionId()** for logging or correlating per-session data. Do not use the session id as user identity or proof of authorization; use the authenticated **Principal**.

Session attributes are suited for small, temporary metadata. Do not store full message histories, large files, sensitive data, or long-lived objects in this map. Values are kept in application memory until the session ends.

## 4. Declaring a Bean in WebSocket Scope

Use **@Scope(scopeName = "websocket")** to declare a per-session bean. If the bean is injected into a singleton controller, enable a scoped proxy because the controller outlives individual WebSocket sessions:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;

@Component
@Scope(scopeName = "websocket", proxyMode = ScopedProxyMode.TARGET_CLASS)
public class SessionWorkspace {

    private final Map<String, String> selections = new ConcurrentHashMap<>();
    private final AtomicLong actionCount = new AtomicLong();

    @PostConstruct
    public void initialize() {
        // Runs when the session's instance is created for the first time.
    }

    public void remember(String key, String value) {
        selections.put(key, value);
        actionCount.incrementAndGet();
    }

    public Map<String, String> getSelections() {
        return Map.copyOf(selections);
    }

    public long getActionCount() {
        return actionCount.get();
    }

    @PreDestroy
    public void destroy() {
        // Release short-lived session resources if any.
        selections.clear();
    }
}
~~~

**@PostConstruct** is invoked after Spring creates the bean and injects dependencies. The bean is normally lazily initialized: this callback runs when the session accesses the bean for the first time, not necessarily right when the WebSocket handshake completes.

**@PreDestroy** is invoked when the WebSocket session's scope is destroyed. This is the right place to close resources owned by the bean or clear temporary data. Do not place long blocking work in this callback because session cleanup should not stall message processing flows.

The example uses **jakarta.annotation.PostConstruct** and **jakarta.annotation.PreDestroy**, matching Spring Framework 6 and later. For older Spring versions using the Java EE ecosystem, annotation packages may differ.

## 5. Injecting a WebSocket-Scoped Bean into a Singleton Controller

Controllers are normally singletons, yet they can still inject a WebSocket-scoped bean through a proxy:

~~~java
import java.util.Map;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.stereotype.Controller;

@Controller
public class WorkspaceController {

    private final SessionWorkspace workspace;

    public WorkspaceController(SessionWorkspace workspace) {
        this.workspace = workspace;
    }

    @MessageMapping("/workspace/select")
    public void select(Map<String, String> command,
                       SimpMessageHeaderAccessor headers) {

        String key = command.get("key");
        String value = command.get("value");

        if (key == null || value == null) {
            throw new IllegalArgumentException("key and value are required");
        }

        workspace.remember(key, value);

        String sessionId = headers.getSessionId();
        // sessionId can be used for logging or tracing.
    }
}
~~~

When a method is called within the message-processing context of a WebSocket session, the proxy looks up the exact target bean belonging to that session. If session A calls the method, the proxy resolves workspace A; if session B calls the method, the proxy resolves workspace B.

The scoped proxy bridges the lifecycle difference between the singleton controller and the per-session bean. If the proxy is omitted, Spring may fail to inject the bean because no specific WebSocket session exists when the controller is instantiated.

With **ScopedProxyMode.TARGET_CLASS**, the proxied class should not be final, and proxied methods should not be final. If you prefer an interface proxy, you can choose **ScopedProxyMode.INTERFACES** and inject via the corresponding interface.

## 6. Lifecycle of a WebSocket-Scoped Bean

Basic lifecycle:

1. WebSocket handshake creates a WebSocket session.
2. Client sends STOMP CONNECT and Spring sets up the message context.
3. When a controller or inbound channel interceptor accesses the WebSocket-scoped bean for the first time, Spring creates the target instance.
4. Spring stores the instance in session attributes.
5. Subsequent messages belonging to that session access the same instance.
6. When the WebSocket session ends and the scope is destroyed, Spring runs destruction callbacks, including **@PreDestroy**.

~~~mermaid
flowchart TD
    A["WebSocket session created"] --> B["First message accesses bean"]
    B --> C["Spring creates target instance"]
    C --> D["Store target in session attributes"]
    D --> E["Subsequent messages use the same instance"]
    E --> F{"Session still active?"}
    F -->|Yes| E
    F -->|No| G["Destroy WebSocket scope"]
    G --> H["@PreDestroy and cleanup"]
~~~

A bean never accessed during the session may never be instantiated. In that case, there is no target instance on which to invoke **@PreDestroy**. If you need to track all sessions right from CONNECT, use session lifecycle events or a dedicated registry instead of assuming every WebSocket-scoped bean has been created.

WebSocket scope is tied to the WebSocket session, not to an individual STOMP subscription. Canceling one subscription does not destroy the WebSocket scope; the session may still have other subscriptions.

## 7. Tracking Session Lifecycle with Spring Events

Spring publishes application context events so the application can track STOMP session lifecycles:

- **SessionConnectEvent**: Spring receives STOMP CONNECT from the client.
- **SessionConnectedEvent**: the broker has replied with CONNECTED and the STOMP session is established.
- **SessionSubscribeEvent**: client sends SUBSCRIBE.
- **SessionUnsubscribeEvent**: client sends UNSUBSCRIBE.
- **SessionDisconnectEvent**: the STOMP session disconnects.

Example listener:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.messaging.SessionConnectedEvent;
import org.springframework.web.socket.messaging.SessionDisconnectEvent;

@Component
public class StompSessionLifecycleListener {

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        String sessionId = event.getSessionId();
        // Record that the session was accepted by the broker.
    }

    @EventListener
    public void onDisconnected(SessionDisconnectEvent event) {
        String sessionId = event.getSessionId();
        // Cleanup must be safe if the event is published multiple times.
    }
}
~~~

**SessionConnectEvent** indicates the client sent CONNECT, not necessarily that the broker accepted it. If you need to mark a session as STOMP-connected, **SessionConnectedEvent** is the more appropriate milestone.

**SessionDisconnectEvent** may be published multiple times for the same session along certain connection-closing paths. Therefore, cleanup operations must be idempotent: calling them multiple times produces the same result, does not decrement presence multiple times, does not release already-released resources, and does not delete another session's data.

Do not treat the disconnect of a single WebSocket session as the user logging out completely. A user may have multiple tabs or devices. Only mark the user offline when no valid sessions remain according to the application's presence policy.

## 8. WebSocket Scope and Concurrency

**clientInboundChannel** can process messages using an executor thread pool. If multiple messages from the same session are processed concurrently, they can access the same WebSocket-scoped bean from multiple threads.

Therefore, WebSocket scope does not automatically make fields inside the bean thread-safe. In the example above, **ConcurrentHashMap** and **AtomicLong** are used to support concurrent updates. For more complex data structures, use locks, immutable state, or appropriate synchronization.

You can instruct Spring to preserve receive order of messages within the same session with:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws");
    registry.setPreserveReceiveOrder(true);
}
~~~

This option ensures inbound messages from the same session are passed to the channel in receive order. However, it does not replace thread safety if the bean is also accessed from other threads, schedulers, or asynchronous tasks.

If the bean is used in an asynchronous task after the handler returns, do not assume the WebSocket scope context is automatically propagated to another executor. The proxy needs an active session context to locate the target. Explicitly pass the session id or required immutable data to the background service, and process it through an API with explicit scope and authorization. Do not hold onto a scoped proxy to call arbitrarily from a scheduler or a thread lacking session context.

## 9. Resource Lifecycle and Avoiding Memory Leaks

A WebSocket session can stay open for hours or days. A bean in WebSocket scope can therefore hold memory for a long time as well.

You should:

- Store only small, necessary per-session data.
- Bound element counts and collection sizes.
- Remove listeners, callbacks, or references to large objects in **@PreDestroy**.
- Close resources truly owned by the bean, such as internal subscriptions or short-lived file handles.
- Avoid creating per-session threads, database connection pools, or broker connections.
- Do not cache entire business datasets inside session beans; use caches or persistence services with separate limits and eviction policies.

For example, if each session holds 100 KB of data and there are 20,000 concurrent sessions, that state alone requires roughly 2 GB of memory before counting object, map, proxy, and framework overhead. Estimate based on peak session counts and measure actual heap usage.

Do not store references to WebSocket-scoped beans inside singleton collections or static maps. When the session ends, an external reference can keep the bean alive past its scope and cause a memory leak. If a session registry is needed, store only minimal metadata such as session id, user id, and timestamp; remove entries idempotently on disconnect or timeout.

**@PreDestroy** is a scope lifecycle callback in a running process; it is not a durable storage guarantee. If the JVM is killed or the server loses power, the callback may not run. Do not rely on this callback as the sole mechanism protecting business data.

## 10. Recovering Data After Reconnect

Reconnecting typically creates a new WebSocket session, so a new WebSocket-scoped bean is created upon access. Data in the old session's bean does not automatically transfer to the new session.

If temporary selections need to survive reconnect, you can choose one of these approaches:

| Data Type | Appropriate Storage |
|---|---|
| Temporary data needed only for one connection | WebSocket-scoped bean or session attributes. |
| Selections needed across reconnects without long-term durability | Client store or server-side cache with TTL, tied to user/logical session. |
| Data that must survive logout, restart, or device change | Database or persistence layer. |
| State updated concurrently by multiple clients | Authoritative backend store with version or sequence. |
| Messages/events needing replay | Event log or message store with cursor. |

Do not use the WebSocket session id as the sole key for data that must survive reconnect because the new session id may differ from the old one. Use the authenticated user id or a server-issued conversation/workspace id with authorization checks. Do not trust a client-sent id if it is used to access someone else's data.

A typical recovery flow consists of:

1. Client reconnects and receives CONNECTED.
2. Client re-registers subscriptions.
3. Client sends a sync request containing the last processed cursor/version.
4. Server returns a snapshot or event replay.
5. Client applies data by version and ignores duplicate events.
6. Client transitions to ready state after sync completes.

## 11. WebSocket Scope Does Not Replace Session Authentication

WebSocket scope determines object lifecycle, not what a user is allowed to do. A separate bean per session does not guarantee that the session belongs to a valid user or only accesses that user's data.

In controllers and services:

- Use the **Principal** authenticated by Spring Security to obtain user identity.
- Enforce authorization on every destination and business operation.
- Do not use the session id as an access token.
- Do not trust user id, tenant id, or roles inside payloads/session attributes if they are client-controlled.
- Do not share mutable session state across users through a singleton service.

If a session loses authorization or the user logs out, the application must close or reject subsequent operations per security policy. WebSocket scope is destroyed when the session ends; it does not perform logout or token revocation itself.

## 12. Testing Lifecycle and Resources

Important tests:

| Scenario | What to Verify |
|---|---|
| Two WebSocket sessions for the same user | Each session has its own WebSocket-scoped bean. |
| Two messages in the same session | Both access the same instance until the session ends. |
| Unaccessed bean | Do not assume **@PostConstruct** has run. |
| Session disconnect | **@PreDestroy** is called when the scope is destroyed. |
| Duplicate disconnect events | Cleanup does not release resources or update presence twice. |
| Reconnect with the same HTTP session | New session does not reuse the old WebSocket session's bean. |
| Multiple concurrent messages | Bean state has no race conditions. |
| Async task after handler | Do not access scoped proxy when session context is absent. |
| Long-lived session | Per-session memory is bounded and observable. |
| Abnormal JVM shutdown | Business data remains safe even if cleanup callbacks do not run. |

You can use integration tests with a WebSocket STOMP client to open two sessions, send messages to each session, and verify state is not shared. Verify lifecycle callbacks with a test bean having a separate counter or recorder. When testing disconnect, wait until the session is actually closed and scope cleanup finishes rather than assuming events happen synchronously at the close call.

## 13. Common Mistakes

- **Using a singleton to store per-WebSocket-session data:** sessions can overwrite or read each other's data. Use WebSocket scope or session attributes.
- **Using @SessionScope while expecting per-tab isolation:** an HTTP session can be shared by multiple WebSocket sessions. Use websocket scope for each connection.
- **Injecting a scoped bean into a singleton without a proxy:** Spring cannot resolve a session target when creating the controller. Enable ScopedProxyMode.TARGET_CLASS or an interface proxy.
- **Assuming the bean is created right at CONNECT:** WebSocket-scoped beans are normally lazily created on first access.
- **Assuming @PreDestroy runs immediately when the network drops:** scope cleanup depends on the server detecting session termination; timeouts or sudden failures can delay cleanup.
- **Assuming each session has only one thread:** the inbound executor can process concurrently; use thread-safe structures or preserve ordering where appropriate.
- **Using a scoped proxy from a background thread:** that thread may lack a WebSocket scope context. Pass required data explicitly.
- **Storing durable data in a session bean:** reconnects or restarts can lose data. Use persistence.
- **Holding references to session beans in singletons/static maps:** objects may fail to be garbage-collected after disconnect. Clean up registries and references properly.

## 14. Key Takeaways

WebSocket scope creates one bean instance per WebSocket session, normally initialized on first access and destroyed when the session ends. Use **@Scope("websocket", proxyMode = TARGET_CLASS)** when injecting into a singleton controller; use **SimpMessageHeaderAccessor.getSessionAttributes()** for small per-session metadata. Data in this scope does not automatically survive reconnects and does not replace HTTP sessions, authentication, or persistence. Because inbound messages can be processed concurrently, state inside the bean must be thread-safe; because sessions can live long, data must stay small and cleanup must be idempotent. Proper lifecycle design isolates data across tabs, prevents memory leaks, and preserves performance under many concurrent connections.

## References

- [Spring Framework 6.2 — WebSocket Scope](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/scope.html)
- [Spring Framework 6.2 — Application Context Events](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/application-context-events.html)
- [Spring Framework 6.2 — Performance](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/configuration-performance.html)
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html)