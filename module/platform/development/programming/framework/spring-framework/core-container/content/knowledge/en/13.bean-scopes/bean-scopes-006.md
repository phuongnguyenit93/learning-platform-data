# Request, Session, Application, and WebSocket Scopes in the Spring Framework

## 1. Why do we need web bean scopes?

The Spring IoC Container manages a bean's lifecycle by **scope**. If no scope is specified, a bean is normally `singleton`: one instance per bean definition in a Spring IoC container. In web applications, not all state should be shared across every request or user. Spring provides four web scopes to bind an instance to the lifecycle of an HTTP request, HTTP session, `ServletContext`, or WebSocket session.

Distinguish three concepts:
- **Bean definition**: configuration telling Spring how to create the object.
- **Bean instance**: the actual object created from the bean definition.
- **Scope**: the rule Spring uses to look up/create and retain an instance for a specific context. Two accesses to the same bean definition within *the same scope context* normally receive the same target instance; when the context changes, the target can differ.

| Scope | Context Key | Target Creation Time | Termination / Reclamation | Typical Use |
| --- | --- | --- | --- | --- |
| `request` | An HTTP request | First time the bean is used in the request | Request ends and corresponding cleanup runs | Request ID, temporary processing data for one request |
| `session` | An HTTP `HttpSession` | First time used in that session | Session expires or is invalidated | UI preferences, stateful multi-step flows for one session |
| `application` | A `ServletContext` | First time the bean is used in the web application | `ServletContext` shuts down | State/configuration shared within **one application instance** |
| `websocket` | A WebSocket session in Spring STOMP messaging infrastructure | First time used in the WebSocket session | WebSocket session ends | Per-connection counters/state for a STOMP connection |

These scopes are **not** synonymous with `singleton` or `prototype`. `singleton` belongs to each Spring IoC container; `application` belongs to the `ServletContext`, and can be visible as a servlet context attribute even when an application has multiple Spring `ApplicationContext`s. None of these scopes automatically makes an object thread-safe, synchronizes across application replicas, or persists state to a database.

### Quick visualization

```text
HTTP request #1 ── request bean R1 ─┐
HTTP request #2 ── request bean R2 ─┴── same HTTP session S1 ── session bean S1
HTTP request #3 ── request bean R3 ──── HTTP session S2 ── session bean S2

                         ServletContext A ── application bean A
WebSocket connection W1 ── websocket bean W1
WebSocket connection W2 ── websocket bean W2
```

Each new HTTP request gets a new request bean if it accesses that bean. Two requests sending the same valid session ID share the same session-scoped target; omitting or changing the session ID can lead to a different session. A WebSocket session is neither a long-lived HTTP request nor automatically an HTTP session.

## 2. Requirements and management mechanism

The four web scopes only work when Spring has a web-aware application context and the corresponding scope infrastructure. In Spring MVC handled via `DispatcherServlet`, Spring already exposes the request to the current context; Spring Boot applications using `spring-boot-starter-web` typically have this out of the box. If handling servlets outside `DispatcherServlet` (such as certain integrations), configure `RequestContextListener` or `RequestContextFilter` to bind the request context when appropriate.

In a Java SE application using only a plain `AnnotationConfigApplicationContext`, you cannot expect `request`/`session`/`application` to be registered or have a web context to resolve against; an unknown scope error can occur. For `websocket`, Spring messaging infrastructure for **STOMP over WebSocket** must be enabled (e.g., `@EnableWebSocketMessageBroker`); merely opening a raw WebSocket endpoint does not guarantee Spring's websocket bean scope.

Spring stores a target by key in the corresponding scope's store: request attributes, session attributes, servlet context attributes, or WebSocket/SIMP session attributes. The bean is created on the first eligible access, unless special initialization forces earlier access. For web-scoped targets, lifecycle callbacks such as `@PostConstruct` and destruction callbacks can be applied upon scope creation/destruction; do not assume scope termination always means a graceful server shutdown (a crash can skip callbacks).

## 3. HTTP request scope

`@RequestScope` is a composed annotation for `@Scope("request")`. Each HTTP request has its own target bean; multiple components using the bean within one request share that target. On the next HTTP request, a new target is created on demand.

```java
package edu.example.scopes;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestMarker {
    private final String id = UUID.randomUUID().toString();

    public String id() {
        return id;
    }
}
```

Use for temporary trace/context data, per-request memoization, or an object accumulating results during a single processing pass. Do not use it to store a shopping cart or preferences that must persist across requests. This scope is bound to an **HTTP request**, not "one thread": the servlet container can reuse threads for different requests; tasks dispatched via `@Async`/`Executor` do not automatically carry the request context.

## 4. HTTP session scope

`@SessionScope` is a composed annotation for `@Scope("session")`. The first time the bean is used in `HttpSession` S1, Spring creates target S1; subsequent requests in the same S1 continue using target S1. Different sessions receive separate targets. When the session expires or `invalidate()` is called, the state tied to that session is no longer valid.

```java
package edu.example.scopes;

import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.SessionScope;

@Component
@SessionScope
public class SessionVisits {
    private int visits;

    // A single session can receive multiple concurrent requests.
    public synchronized int next() {
        return ++visits;
    }
}
```

An HTTP session is commonly identified via the `JSESSIONID` cookie, yet the cookie primarily holds the *session identifier*; the actual bean resides on the server/session store. A new browser tab usually shares cookies and thus shares the HTTP session with existing tabs in the same browser profile. "One bean per user" is a misleading phrasing: one person can have multiple sessions, and users/devices are not identified by bean scope.

Be careful with session size and clustered deployments: if sessions must be replicated/serialized, objects stored in the session must be compatible with the system's persistence/serialization mechanism; Java `Serializable` is only part of the picture and does not guarantee sessions are automatically shared across every server. Do not treat session scope as a security layer or source of truth for access permissions.

## 5. Application scope

`@ApplicationScope` is a composed annotation for `@Scope("application")`, with the target bound to a single `ServletContext`. It fits state genuinely shared across all requests/sessions **on a single web application instance**. The bean also appears as an attribute in the servlet context.

```java
package edu.example.scopes;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.ApplicationScope;

@Component
@ApplicationScope
public class ApplicationVisits {
    private final AtomicLong count = new AtomicLong();

    public long next() {
        return count.incrementAndGet();
    }
}
```

Multiple concurrent requests can call `next()` simultaneously. `AtomicLong` makes incrementing thread-safe; using a plain `long` and unsynchronized `++` can lose updates. In a cluster of two JVMs/pods, each instance has its own `ServletContext` and counter. If you need a cluster-wide visit total, use a datastore or metrics backend designed for it.

Compared to `singleton`: if the system has only one `ApplicationContext` in the `ServletContext`, observed behavior may look similar, yet the *storage boundary* differs. `@ApplicationScope` clearly states intent when sharing at the `ServletContext` level is required, whereas most stateless services should stay at the default `singleton`.

## 6. Complete Spring Boot MVC Example: observing three HTTP scopes

The following example runs with **Java 17+, Maven 3.6.3+, and Spring Boot 3.5.6** (Spring Framework 6.2.x). It is a minimal project requiring no database. Create the structure:

```text
spring-scopes-demo/
├── pom.xml
└── src/main/java/edu/example/scopes/
    ├── ScopeDemoApplication.java
    ├── RequestMarker.java
    ├── SessionVisits.java
    ├── ApplicationVisits.java
    └── ScopeController.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>spring-scopes-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

`ScopeDemoApplication.java`:

```java
package edu.example.scopes;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ScopeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScopeDemoApplication.class, args);
    }
}
```

The three files `RequestMarker.java`, `SessionVisits.java`, and `ApplicationVisits.java` use **verbatim** the Java classes presented in sections 3, 4, and 5; each class has package `edu.example.scopes` and is a separate public class. File `ScopeController.java`:

```java
package edu.example.scopes;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ScopeController {
    private final RequestMarker requestMarker;
    private final SessionVisits sessionVisits;
    private final ApplicationVisits applicationVisits;

    public ScopeController(RequestMarker requestMarker,
                           SessionVisits sessionVisits,
                           ApplicationVisits applicationVisits) {
        this.requestMarker = requestMarker;
        this.sessionVisits = sessionVisits;
        this.applicationVisits = applicationVisits;
    }

    @GetMapping("/scopes")
    public ScopeInfo getScopes() {
        return new ScopeInfo(
                requestMarker.id(),
                sessionVisits.next(),
                applicationVisits.next()
        );
    }

    public record ScopeInfo(String requestId, int sessionVisits,
                            long applicationVisits) {}
}
```

The controller is a singleton by default; the three dependencies are injected via proxies generated because of the configured HTTP scope annotations. Only when a method invokes the target does the proxy resolve the current bean from the corresponding scope.

Run in the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Open another terminal, try two requests sharing a cookie/session and then one request with a different cookie jar:

```bash
curl -s -c jar-a.txt -b jar-a.txt http://localhost:8080/scopes
curl -s -c jar-a.txt -b jar-a.txt http://localhost:8080/scopes
curl -s -c jar-b.txt -b jar-b.txt http://localhost:8080/scopes
```

If the application has just started and **only** these three commands hit the endpoint, the output looks like (UUIDs are **illustrative examples**, not fixed):

```json
{"requestId":"2d50fe8b-0d58-4a8e-b514-d363303a65c0","sessionVisits":1,"applicationVisits":1}
{"requestId":"8876aa20-2963-408e-b01d-dfa670aa94a4","sessionVisits":2,"applicationVisits":2}
{"requestId":"4b079e10-eaa4-431d-9b39-cc11c3fc3139","sessionVisits":1,"applicationVisits":3}
```

Explanation: `requestId` differs after each HTTP request; `sessionVisits` increments to 2 with the same jar A and starts from 1 with jar B; `applicationVisits` increments across the whole instance. If jar B already existed, multiple clients called concurrently, or the app had received prior requests, the exact counts may differ. Delete both jar files to test two fresh HTTP sessions; restart the app to reset the in-RAM application counter.

**Code note:** The snippets in sections 3–5 are the complete source of the three listed files; no extra `@Bean` or request/session scope configuration is needed for this Boot MVC sample. Do not use plain `javac` on the project because Spring dependencies are required; Maven compiles and runs it via the plugin.

## 7. WebSocket scope with STOMP messaging

`websocket` scope in Spring is bound to **the WebSocket session of the STOMP messaging infrastructure**, not to individual messages. When the same connection sends multiple messages, the WebSocket target bean retains its state; another connection gets a different target. Spring stores the bean in the STOMP/SIMP message session attributes and reclaims it when the session ends.

Add to the `<dependencies>` section of `pom.xml` in the example above:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-websocket</artifactId>
</dependency>
```

Create `StompConfig.java`:

```java
package edu.example.scopes;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
```

Create `SocketCounter.java`:

```java
package edu.example.scopes;

import java.util.UUID;
import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;

@Component
@Scope(scopeName = "websocket", proxyMode = ScopedProxyMode.TARGET_CLASS)
public class SocketCounter {
    private final String connectionMarker = UUID.randomUUID().toString();
    private int count;

    public synchronized int next() {
        return ++count;
    }

    public String marker() {
        return connectionMarker;
    }
}
```

Create `StompCounterController.java`:

```java
package edu.example.scopes;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class StompCounterController {
    private final SocketCounter counter;

    public StompCounterController(SocketCounter counter) {
        this.counter = counter;
    }

    @MessageMapping("/count")
    @SendTo("/topic/counts")
    public CountReply count() {
        return new CountReply(counter.marker(), counter.next());
    }

    public record CountReply(String connectionMarker, int count) {}
}
```

Use a STOMP client: connect via WebSocket to `ws://localhost:8080/ws`; subscribe to `/topic/counts`; send two STOMP `SEND` messages to `/app/count`. On a new connection, the replies normally have the same `connectionMarker` and `count` equal to 1 then 2; disconnect, open a new WebSocket session, and send again, and the new target's `count` starts from 1. `/topic/counts` is a **broadcast**: other subscribers will also see the messages; the example only sends test data—do not broadcast sensitive session or user details in real systems.

The sample above uses syntax that runs on both Spring Framework 6.2 and 7.x. Starting in **Spring Framework 7.0**, `@Scope(scopeName = "websocket", proxyMode = ScopedProxyMode.TARGET_CLASS)` can be replaced with `@WebSocketScope` (import `org.springframework.web.socket.config.annotation.WebSocketScope`); the new annotation creates a class-based scoped proxy by default. **Do not use `@WebSocketScope` with Spring Framework 6.2**, as that version does not include this annotation.

A raw socket with a standalone `WebSocketHandler` is not enough to directly apply `@MessageMapping`/STOMP and this scope. An `HttpSession` existing at handshake time is also not synonymous with a WebSocket session; authenticating and mapping users across the two protocols is a separate concern from bean scope.

## 8. Scoped proxies and injecting short-lived beans into singletons

The MVC example injects `RequestMarker`, `SessionVisits`, and `ApplicationVisits` into a singleton controller. Directly injecting a short-lived *target* when the singleton initializes would cause Spring either to find no active request/session or to accidentally retain a target from the first request. The standard approach is a **scoped proxy**.

Actual flow:

```text
Singleton ScopeController (long-lived)
        |
        +--> RequestMarker proxy (stable reference)
                    |
                    +-- HTTP request X --> target RequestMarker X
                    +-- HTTP request Y --> target RequestMarker Y

        +--> SessionVisits proxy
                    |
                    +-- HTTP session A --> target SessionVisits A
                    +-- HTTP session B --> target SessionVisits B
```

`@RequestScope`, `@SessionScope`, and `@ApplicationScope` default to `proxyMode = ScopedProxyMode.TARGET_CLASS`, so the code sample above can inject the concrete classes. Equivalent explicit configuration:

```java
@Scope(value = "request", proxyMode = ScopedProxyMode.TARGET_CLASS)
```

`TARGET_CLASS` uses a class-based proxy; `final` classes or `final` methods are unsuitable for subclass/interception proxying. If using `ScopedProxyMode.INTERFACES`, the injection point must match an interface implemented by the proxy. A bean proxy also does not allow calling the target on a thread that has no active matching scope.

Another option is injecting `ObjectProvider<T>` and looking up the target **at the time of use**; the illustrative snippet below is a conceptually standalone class pair replacing the proxied `RequestMarker` above:

```java
// Register request-scoped component WITHOUT creating a scoped proxy:
@Component
@RequestScope(proxyMode = ScopedProxyMode.NO)
class RequestValue {
    public String value() { return "data in current request"; }
}

@Service
class CurrentRequestService {
    private final ObjectProvider<RequestValue> provider;

    CurrentRequestService(ObjectProvider<RequestValue> provider) {
        this.provider = provider;
    }

    public String read() {
        return provider.getObject().value();
    }
}
```

This snippet requires the corresponding Spring imports (`Component`, `Service`, `RequestScope`, `ScopedProxyMode`, `ObjectProvider`) and must run in a web-aware context; it illustrates the lookup mechanism, not a standalone runnable Java file. Importantly, `provider.getObject()` must be called **inside an active HTTP request**, not once in the constructor and cached in a singleton field. Certain scenarios needing direct request/session reads can inject `HttpServletRequest` or access request attributes via the appropriate API, yet that is a choice about web API coupling and does not change scope rules.

## 9. Lifecycle and cleanup

| Event | Request scope | Session scope | Application scope | WebSocket scope |
| --- | --- | --- | --- | --- |
| First bean access | Created in request | Created in HTTP session | Created in `ServletContext` | Created in WebSocket session |
| Multiple calls in same scope | Reuses target | Reuses target | Reuses target | Reuses target |
| Next HTTP request | Different target | Can be same target if same session | Same target on that instance | Not directly related |
| End of scope | Request ends | Session invalidated/timed out | `ServletContext` stops | Socket session closed/ended |

When Spring manages destruction callbacks for a scope, `@PreDestroy`/`DisposableBean` are invoked according to normal lifecycle rules. For instance, a websocket target is normally destroyed when the connection ends. Do not rely on `@PreDestroy` to guarantee saving critical business data: session timeouts, abnormal restarts, or crashes do not replace transactions/persistence.

If you need to explicitly terminate an HTTP session, use `request.getSession(false)` to fetch an existing session (if any), followed by `session.invalidate()` if appropriate for a logout flow. `getSession(false)` can return `null`; `getSession()` can create a new session. Do not access a `@SessionScope` bean after invalidation on the same execution path assuming it is still the old target.

## 10. Common errors and diagnosis

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| `No Scope registered for scope name 'request'` or similar | Non-web-aware container / missing scope registration | Run in a Spring MVC web context; verify context configuration |
| `No thread-bound request found` | Invoking a request/session-scoped target outside a context-bound HTTP request | Resolve only inside a request; pass needed data as parameters to background tasks |
| Short-lived scope fails to inject into singleton at startup | Missing proxy/provider or bean accesses target too early | Use a scoped proxy or `ObjectProvider`; avoid calling target methods in singleton constructors |
| Session state lost after every HTTP call | HTTP client does not resend session cookie / session expired / app switches instances without shared session | Use a cookie jar; check timeouts and session store strategy |
| Two browser tabs see the same state | Two tabs share the HTTP session/cookie | If per-tab state is truly needed, define a separate tab identifier instead of relying solely on `@SessionScope` |
| Mutable application bean updates incorrectly | Shared object accessed concurrently | Use immutable data, `AtomicLong`, locks, or an appropriate datastore |
| WebSocket bean fails to resolve | STOMP broker not enabled or invoked outside SIMP message context | Verify `@EnableWebSocketMessageBroker`, endpoint, `@MessageMapping`, message headers, and resolution scope |
| `@WebSocketScope` does not compile | Spring Framework 6.2 does not provide that annotation | Use `@Scope("websocket", proxyMode = TARGET_CLASS)` on 6.2 |
| Proxy class fails with `final` method/class | Class-based proxy needs to subclass/override | Use a proxyable class/method or a properly typed interface-based proxy |
| Scoped state disappears after deploy/restart | State resides in RAM/unconfigured session store | Persist mandatory data or use a shared backing store |

**Misconceptions to avoid:**
1. `session` is an HTTP session, not automatically a logged-in user; `websocket` is a STOMP connection session, not an HTTP session.
2. `application` does not mean a distributed global singleton; multiple instances maintain separate state.
3. Scopes manage *bean storage location/lifecycle*, rather than replacing thread synchronization, transactions, security, or data persistence.
4. A scoped proxy keeps a stable reference in a singleton while selecting the target upon method calls; do not extract/retain the raw target beyond its lifecycle.
5. Web scopes in the Spring Servlet stack are not identical to request contexts in WebFlux/Reactor applications; do not mechanically apply `ThreadLocal`-based mechanisms to reactive pipelines.

## 11. Self-check knowledge

1. Send three requests A1, A2 (same `JSESSIONID`), and B1 (different cookie) to the endpoint. Which bean changes across all three, which repeats for A1/A2, and which is shared across all three on a single JVM?
2. A singleton service needs the current request ID for logging. Why is storing the actual request bean in a singleton field wrong? Write a solution using a scoped proxy or provider.
3. Two pods serve the same application. If an `@ApplicationScope` bean holds a counter in RAM, why do the two pods produce different counts?
4. A STOMP connection sends 10 frames to `/app/count`. How many targets does the WebSocket-scoped counter use? When the client reconnects, what changes?
5. Why should `@SessionScope` not be understood as "one instance per user"?

**Verification answers:** (1) The request bean differs across all three requests; the session bean is shared for A1/A2 and differs for B1; the application bean is shared within the same `ServletContext`. (2) The singleton outlives the request, so the target must be resolved at runtime. (3) Each pod has its own `ServletContext` and memory. (4) One target for the connection if using a single scope context and accessing the bean; reconnecting creates a new target. (5) A user can have multiple sessions, and a session may exist without a logged-in user.

## Official Documentation

- Spring Framework — Bean Scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Spring Framework — STOMP WebSocket Scope: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/scope.html
- Spring Framework 6.2 — WebSocket Scope (`@Scope` syntax): https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/scope.html
- Spring Framework — Scoped bean configuration: https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html

