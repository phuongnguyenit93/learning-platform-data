# Declaring `@Scope` and Web Scope Annotations in the Spring Framework

## 1. Objective and context

In the Spring Core Container, **scope (bean scope)** determines how many actual objects correspond to a bean definition, where those objects come from, and in which context they exist. The same class can be declared with different scopes to satisfy different state management requirements.

After this lesson, you will be able to:

- Declare scope using `@Scope` on `@Component` classes or on `@Bean` methods.
- Accurately distinguish `singleton`, `prototype`, `request`, `session`, `application`, and `websocket`.
- Use the specialized annotations `@RequestScope`, `@SessionScope`, and `@ApplicationScope`.
- Explain why a singleton needs a **scoped proxy** or `ObjectProvider` when using a short-lived bean.
- Recognize errors from accessing a scope outside an HTTP context, state-sharing issues, and proxy limitations.

The coverage focuses on the Spring Framework IoC mechanism and web scopes in **Servlet/Spring MVC** applications. Examples run on Java 17 and Spring Boot 3.3.x (Spring Framework 6.1.x).

## 2. What does Scope actually control?

Spring stores a **bean definition** describing how to create a bean. Scope dictates how the container supplies an instance for each resolution of that definition. Scope does **not** alter Java access modifiers, make an object thread-safe, or automatically synchronize data across JVMs.

| Scope | Quantity / Sharing Boundary | End of Lifecycle | Where Available? |
| --- | --- | --- | --- |
| `singleton` | One instance per **bean definition within one Spring IoC container** | When the container closes | Every Spring context |
| `prototype` | A new instance when the container is asked to create/fetch the bean | Spring does not automatically invoke prototype destruction callbacks after handing the bean to the caller | Every Spring context |
| `request` | One instance per HTTP request, per bean definition | End of request | Web-aware `ApplicationContext` |
| `session` | One instance per HTTP `HttpSession`, per bean definition | When session is invalidated/timed out | Web-aware `ApplicationContext` |
| `application` | One instance per `ServletContext` of the web application | When the web application shuts down | Web-aware `ApplicationContext` |
| `websocket` | One instance per WebSocket session in a STOMP messaging app | When the WebSocket session ends | Web context with STOMP/WebSocket scope support |

**Two common points of confusion:**

1. Spring's `singleton` is one instance **within a container**, not necessarily a JVM-wide singleton, nor synonymous with the Java singleton design pattern.
2. `application` is bound to the **`ServletContext`**. It can be shared across multiple Spring `ApplicationContext`s using the same `ServletContext`, unlike per-context `singleton`. It does not share data across application instances running on multiple machines.

Web scopes only work when the corresponding scope has been registered and the current context is active. For instance, loading `@RequestScope` in a plain Java `AnnotationConfigApplicationContext` can trigger an error saying the scope was not found; accessing a request bean outside an HTTP request typically leads to `ScopeNotActiveException`.

## 3. `@Scope` syntax

`@Scope` resides in the `org.springframework.context.annotation` package. The annotation applies to **Spring-managed bean types** or **`@Bean` factory methods**.

### 3.1. Placing on `@Component`

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class ImportJobState {
    // Each time the container requests the prototype bean, a new instance is created.
}
~~~

`ConfigurableBeanFactory.SCOPE_PROTOTYPE` equals the string `"prototype"`. For singleton, you can use `ConfigurableBeanFactory.SCOPE_SINGLETON` or omit `@Scope` since it is the default.

### 3.2. Placing on a `@Bean` method

~~~java
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

@Configuration(proxyBeanMethods = false)
public class JobConfiguration {
    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public JobToken jobToken() {
        return new JobToken();
    }

    public static class JobToken {
    }
}
~~~

The snippet above illustrates declaring a prototype bean; the `JobConfiguration` class can be discovered by Spring or registered as a configuration. `@Scope` must sit on the **definition** actually registered with Spring. Placing `@Scope` on an object created with `new` without registering the bean has no lifecycle management effect.

### 3.3. Choosing a proxy when declaring scope

~~~java
import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;

@Component
@Scope(value = "request", proxyMode = ScopedProxyMode.TARGET_CLASS)
public class RequestAuditContext {
    public String description() {
        return "Information tied to the current request";
    }
}
~~~

Both `@Scope("request")` and `@Scope(scopeName = "request")` are valid: `value` and `scopeName` are aliases. The `proxyMode` attribute specifies whether a proxy object is created and which proxy type:

| `ScopedProxyMode` | Meaning |
| --- | --- |
| `DEFAULT` | Follows component-scan default configuration; typically results in no scoped proxy |
| `NO` | Creates no proxy; directly receives the target when the scope is active |
| `INTERFACES` | Interface-based proxy (JDK dynamic proxy); injection point should use an interface |
| `TARGET_CLASS` | Class-based proxy, suited for injecting by concrete type; has limitations with `final` classes/methods |

Plain `@Scope` does not automatically enable a scoped proxy. Simply adding `@Scope("request")` alone does not solve the problem of a singleton depending on a request-scoped bean.

## 4. Three specialized annotations for web scopes

The Spring Framework provides **composed annotations** in `org.springframework.web.context.annotation`. They are clearer semantic shorthands for `@Scope` and work on both component classes and `@Bean` methods.

| Annotation | Scope Equivalent | Default `proxyMode` | When to Use |
| --- | --- | --- | --- |
| `@RequestScope` | `@Scope("request")` | `TARGET_CLASS` | Store temporary data for one HTTP request |
| `@SessionScope` | `@Scope("session")` | `TARGET_CLASS` | Store state specific to one HTTP session |
| `@ApplicationScope` | `@Scope("application")` | `TARGET_CLASS` | Shared state within one `ServletContext` |

**Very important point:** `@RequestScope` is not completely identical to `@Scope("request")` if you overlook `proxyMode`. The specialized annotation **creates a class-based scoped proxy by default**; plain `@Scope("request")` does not. The same applies to session and application.

### 4.1. `@RequestScope`: one target per HTTP request

~~~java
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestCorrelation {
    private final String requestId = UUID.randomUUID().toString();

    public String getRequestId() {
        return requestId;
    }
}
~~~

A single request calling `getRequestId()` multiple times on the scoped proxy receives the same `requestId` from the same target. The next HTTP request uses a new target. Do not confuse this with `@RequestParam`: `@RequestParam` extracts an HTTP request parameter value for a controller; `@RequestScope` changes **the lifecycle of a Spring bean**.

A request-scoped bean is useful for holding validated request-specific data, temporary computation state, or trace IDs along a call chain. Data needed across multiple HTTP requests should not be stored here.

### 4.2. `@SessionScope`: one target per HTTP session

~~~java
import java.io.Serial;
import java.io.Serializable;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.SessionScope;

@Component
@SessionScope
public class SessionVisitCounter implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final AtomicInteger visits = new AtomicInteger();

    public int nextVisit() {
        return visits.incrementAndGet();
    }
}
~~~

HTTP requests carrying the same session ID access the same session-scoped target. Different users with different sessions get separate beans. Implementing `Serializable` is an appropriate choice if the application requires HTTP session serialization/passivation/replication, though it also depends on internal fields and session infrastructure.

A single session can receive **multiple concurrent requests** (multiple tabs or AJAX), so a session-scoped bean is not thread-safe by default. The example uses `AtomicInteger` to update the counter more safely than `int++`.

Session scope **does not authenticate users by itself**: it relies on the HTTP session. Do not treat bean scope as a substitute for Spring Security, and avoid storing excessively sensitive data in the session.

### 4.3. `@ApplicationScope`: one target per `ServletContext`

~~~java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.ApplicationScope;

@Component
@ApplicationScope
public class LocalApplicationMetrics {
    private final AtomicLong requests = new AtomicLong();

    public long nextRequest() {
        return requests.incrementAndGet();
    }
}
~~~

All sessions within the same web application/`ServletContext` see the same counter. If you launch two application instances on two different JVMs, each instance has its own counter. State that must stay consistent across a cluster of machines should use a database, Redis, or an appropriate coordination system.

`@ApplicationScope` is intended for state truly scoped to a web application. For most stateless services, regular `singleton` is sufficient and simpler.

### 4.4. Customizing the proxy on specialized annotations

The specialized annotations have a `proxyMode` attribute:

~~~java
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.web.context.annotation.RequestScope;
import org.springframework.stereotype.Component;

@Component
@RequestScope(proxyMode = ScopedProxyMode.NO)
public class TemporaryBuffer {
    public String read() {
        return "temporary";
    }
}
~~~

When setting `NO`, ensure the target is retrieved **inside a valid request**, such as through `ObjectProvider<TemporaryBuffer>` directly inside the request-handling method. If you want a JDK proxy, have the bean implement an interface, annotate `@RequestScope(proxyMode = ScopedProxyMode.INTERFACES)`, and inject via that interface.

## 5. Scoped proxy: why can a singleton bean still invoke the right per-request bean?

Controllers and services in Spring MVC are normally `singleton`. Directly injecting a **request-scoped target** into a singleton constructor would force Spring to resolve the dependency when constructing the singleton, when no request usually exists; or a short-lived target would be retained for too long. A scoped proxy resolves this lifecycle mismatch.

~~~text
Singleton Controller (created at startup)
    |
    | field requestCorrelation
    v
Scoped Proxy (stable reference in singleton)
    |
    | on each method invocation
    v
Looks up target for the current HTTP request
    |-- Request A --> Target A
    |-- Request B --> Target B
    '-- Request C --> Target C
~~~

One proxy is injected into the singleton; each valid method call is forwarded to the target of the **current scope context**. Consequently:

- Creating the singleton does not force the request target to be created immediately.
- Within the same request, accesses to the same bean definition normally receive the same target.
- On another request or session, the same proxy dependency field can route to a different target.
- The proxy **does not create an HTTP request by itself**. Invoking the proxy from a thread with no bound request can still fail.

Typical usage:

~~~java
import org.springframework.stereotype.Service;

@Service
public class AuditService {
    private final RequestCorrelation requestCorrelation;

    public AuditService(RequestCorrelation requestCorrelation) {
        this.requestCorrelation = requestCorrelation;
    }

    public String describe() {
        // Field holds the proxy; target is selected at call time.
        return "request=" + requestCorrelation.getRequestId();
    }
}
~~~

The `AuditService` snippet depends on the `RequestCorrelation` class declared in section 4.1; this is code integrated into a Spring MVC application, not a standalone runnable Java program.

**Choosing `TARGET_CLASS` or `INTERFACES`?** When injecting by concrete class, `TARGET_CLASS` is usually convenient. Do not rely on `final` classes or `final` methods needing proxy interception; subclass-based proxying cannot override final methods. With a clear interface, `INTERFACES` allows designing against abstractions. Avoid treating a scoped proxy as a target object for identity-based caching or accessing state when no scope is active.

## 6. When you do not want a scoped proxy: `ObjectProvider`

`ObjectProvider<T>` (package `org.springframework.beans.factory`) allows **fetching the bean at the moment it is needed**. This is useful for prototypes or request beans with `proxyMode = NO`.

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class BufferService {
    private final ObjectProvider<TemporaryBuffer> provider;

    public BufferService(ObjectProvider<TemporaryBuffer> provider) {
        this.provider = provider;
    }

    public String inspectCurrentRequest() {
        TemporaryBuffer buffer = provider.getObject();
        return buffer.read();
    }
}
~~~

This snippet uses the `TemporaryBuffer` class from section 4.4 and must be called inside an active HTTP request. `ObjectProvider` does not create a scope by itself and does not automatically carry request context to another thread.

With prototype:

~~~java
@Component
@Scope("prototype")
public class WorkUnit {
}

@Service
public class WorkFactory {
    private final ObjectProvider<WorkUnit> provider;

    public WorkFactory(ObjectProvider<WorkUnit> provider) {
        this.provider = provider;
    }

    public boolean getTwoDifferentInstances() {
        return provider.getObject() != provider.getObject();
    }
}
~~~

When `WorkUnit` is truly a prototype bean, the method above returns `true`. If a `WorkUnit` were injected directly into a singleton via constructor and stored in a field, the singleton would receive only one prototype instance at injection time. This is the fundamental distinction between **scope defining bean creation** and **when a dependency is resolved**.

## 7. Complete Spring Boot Example: request, session, application, and prototype

The following application puts all classes in **a single Java file** so it can be run and verified immediately. Spring Boot 3.3.x uses Spring Framework 6.1.x. The inner components are `public static` nested classes so component scanning picks them up; target classes are not declared `final`.

Project structure:

~~~text
scope-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── scopes/
                        └── ScopeDemoApplication.java
~~~

### 7.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>scope-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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
~~~

### 7.2. `src/main/java/com/example/scopes/ScopeDemoApplication.java`

~~~java
package com.example.scopes;

import java.io.Serial;
import java.io.Serializable;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.annotation.ApplicationScope;
import org.springframework.web.context.annotation.RequestScope;
import org.springframework.web.context.annotation.SessionScope;

@SpringBootApplication
public class ScopeDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ScopeDemoApplication.class, args);
    }

    @Component
    @RequestScope
    public static class RequestIdentity {
        private final String id = UUID.randomUUID().toString();

        public String id() {
            return id;
        }
    }

    @Component
    @SessionScope
    public static class SessionCounter implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final AtomicInteger counter = new AtomicInteger();

        public int next() {
            return counter.incrementAndGet();
        }
    }

    @Component
    @ApplicationScope
    public static class ApplicationCounter {
        private final AtomicInteger counter = new AtomicInteger();

        public int next() {
            return counter.incrementAndGet();
        }
    }

    @Component
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public static class PrototypeTicket {
    }

    @RestController
    public static class ScopeController {
        private final RequestIdentity requestIdentity;
        private final SessionCounter sessionCounter;
        private final ApplicationCounter applicationCounter;
        private final ObjectProvider<PrototypeTicket> tickets;

        public ScopeController(
                RequestIdentity requestIdentity,
                SessionCounter sessionCounter,
                ApplicationCounter applicationCounter,
                ObjectProvider<PrototypeTicket> tickets) {
            this.requestIdentity = requestIdentity;
            this.sessionCounter = sessionCounter;
            this.applicationCounter = applicationCounter;
            this.tickets = tickets;
        }

        @GetMapping("/scopes")
        public Map<String, Object> scopes() {
            String first = requestIdentity.id();
            String second = requestIdentity.id();

            PrototypeTicket ticketA = tickets.getObject();
            PrototypeTicket ticketB = tickets.getObject();

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("requestId", first);
            result.put("sameRequestBean", first.equals(second));
            result.put("sessionCalls", sessionCounter.next());
            result.put("applicationCalls", applicationCounter.next());
            result.put("distinctPrototypeTickets", ticketA != ticketB);
            return result;
        }
    }
}
~~~

**Dependency explanation:** `ScopeController` is a singleton by default. `RequestIdentity`, `SessionCounter`, and `ApplicationCounter` are injected as scoped proxies thanks to the specialized annotations. `PrototypeTicket` uses `ObjectProvider` so each `getObject()` call creates a new target.

### 7.3. Running and observing

Requirements: JDK 17 or newer and Maven 3.9.x. From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

In another terminal, call the endpoint sequentially:

~~~bash
# First request: save session cookie.
curl -s -c cookies.txt http://localhost:8080/scopes

# Second request: reuse the same HTTP session.
curl -s -b cookies.txt -c cookies.txt http://localhost:8080/scopes

# Third request: do not send the old session cookie.
curl -s http://localhost:8080/scopes
~~~

Each response is JSON containing five fields:

~~~json
{
  "requestId": "UUID-generated-from-request",
  "sameRequestBean": true,
  "sessionCalls": 1,
  "applicationCalls": 1,
  "distinctPrototypeTickets": true
}
~~~

**The JSON above is an illustrative representation**, not fixed stdout: `requestId` is a dynamically generated UUID and the counters vary with access order, prior calls, and restart timing. The observations to verify are:

1. `sameRequestBean` is always `true` within each HTTP request, because the same request target is accessed twice.
2. `requestId` typically differs across requests since each new target generates a new UUID (UUIDs have an extremely low collision probability; more deterministic tests should compare object identity within the same scope).
3. `sessionCalls` increments from 1 to 2 when called again with the same `JSESSIONID` cookie; a client without the old cookie starts a separate session with counter 1.
4. `applicationCalls` continues incrementing across requests, even across two different sessions, while running in the same application instance.
5. `distinctPrototypeTickets` is always `true` because two prototype fetches receive two different Java objects.

You can open a private/incognito browser window to observe session independence. If the application runs behind a load balancer across multiple JVMs without session affinity or a shared session store, session behavior and the application counter will also depend on deployment infrastructure.

## 8. `websocket` scope: a special case

In a **Spring Messaging application with STOMP over WebSocket**, a `websocket`-scoped target lives for one WebSocket session. In Spring Framework 6.x, you can declare:

~~~java
import org.springframework.context.annotation.Scope;
import org.springframework.context.annotation.ScopedProxyMode;
import org.springframework.stereotype.Component;

@Component
@Scope(scopeName = "websocket", proxyMode = ScopedProxyMode.TARGET_CLASS)
public class SocketConversationState {
    private int messages;

    public int nextMessage() {
        return ++messages;
    }
}
~~~

The snippet above is an **illustrative component**, effective only when the application has configured a STOMP WebSocket message broker and the corresponding `websocket` scope; it cannot run standalone like a plain Java `main()`. The bean should be accessed in a message-handling flow that has an active WebSocket session. If multiple messages in the same session can be processed concurrently, you must protect mutable state accordingly.

**Version note:** Spring Framework **7.0** adds the `@WebSocketScope` annotation with `proxyMode` defaulting to `TARGET_CLASS`. In the Spring Framework **6.1.x / Boot 3.3.x** project of the example above, use `@Scope("websocket", proxyMode = ...)`; do not import `@WebSocketScope` from the 7.x API into a 6.x project.

WebSocket scope is not synonymous with HTTP `session`: a WebSocket session has its own connection lifecycle, whereas an HTTP session is managed by the Servlet container. One HTTP session can be associated with multiple WebSocket connections.

## 9. Conditions for web scopes to function

In a request flow handled by **Spring MVC `DispatcherServlet`**, Spring normally already puts request attributes into the appropriate context; you do not need to register a listener manually for the common case.

In a Servlet application where requests are processed **outside `DispatcherServlet`**, `RequestContextListener` or `RequestContextFilter` may be needed to bind the request to the processing thread per Spring's guidance. This requires a properly configured Servlet environment. Web scopes do not exist by default in a plain Java IoC context.

Do not assume that a new thread or `@Async` task automatically carries the request/session context. Example:

~~~java
// Illustrates the problem: when running on a thread without a request context,
// calling the scoped proxy can raise ScopeNotActiveException.
executor.execute(() -> requestCorrelation.getRequestId());
~~~

If asynchronous processing is needed, **extract the required immutable data during the current request**, then pass it explicitly to the task. Do not use a scoped proxy to mask a missing context. For WebFlux/reactive processing, consider its own context storage model; do not assume Servlet MVC's `ThreadLocal` behavior applies.

## 10. Lifecycle, bean destruction, and state management

- Spring normally creates singletons at context startup (unless lazy). Singletons can have init/destroy callbacks tied to the container lifecycle.
- Prototypes are initialized and dependency-injected by Spring when fetched; the container does not automatically run destruction callbacks for each handed-out prototype. The caller must proactively clean up resources.
- Request/session/application/WebSocket scopes manage targets according to their respective contexts. Callbacks such as `@PreDestroy` can run when the scope destroys the target under supported lifecycles, depending on the request/session/context closing/destroying normally.
- A scoped proxy is an intermediary object that can be long-lived; it is the **actual target** that carries request- or session-scoped state.
- Scope does not provide synchronization locks. Session/application beans with mutable state must handle concurrent access when multiple requests or threads exist.

Do not use bean scopes as a place to store all long-lived business data. State that needs querying, recovery after restart, or sharing across multiple instances belongs in an appropriate storage system. Always watch out for cross-user information leaks if request/session state is accidentally placed in a singleton/application bean.

## 11. Common errors and diagnosis

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| `No Scope registered for scope name 'request'` | Context does not support/register web scopes | Use an appropriate `WebApplicationContext`; check the Servlet environment and configuration |
| `ScopeNotActiveException` or `No thread-bound request found` | Retrieving a request-scoped target outside a bound HTTP request | Access only inside a valid request or pass needed data to other threads |
| Injecting a request bean into a singleton fails at startup | Unproxied `@Scope("request")`, target resolved with no request | Use `@RequestScope`, choose a `proxyMode`, or use `ObjectProvider` |
| Same prototype across every service call | Prototype was injected once via constructor into a singleton | Use `ObjectProvider.getObject()` when a new instance is needed |
| `@SessionScope` field changes unexpectedly | Multiple requests in one session concurrently modify mutable state | Design immutably or synchronize/make thread-safe as needed |
| `@ApplicationScope` is not shared across pods | One `ServletContext` per deployed instance | Move shared state to persistence/distributed store |
| Proxy class fails or `final` method is not intercepted | Using `TARGET_CLASS` on hard-to-proxy types/methods | Remove `final` at interception points or use an appropriate interface proxy |
| Data lost between two requests | Using `@RequestScope` for data that must live longer | Choose session or durable storage depending on needs |
| Applied `@Scope` yet sees no effect | Object created with `new` or class not registered as a Spring bean | Register `@Component`/`@Bean` in the right package and fetch the object from the container |
| `@WebSocketScope` import does not exist | Using Spring Framework 6.x while the annotation belongs to 7.0+ | On 6.x, use `@Scope("websocket", proxyMode = ...)` |

A pragmatic debugging approach is to verify **(1)** whether the bean is registered, **(2)** what the scope name is, **(3)** whether a proxy is created, **(4)** whether the current thread/request/session is active, and **(5)** whether a target is accidentally retained directly inside a singleton.

## 12. Criteria for choosing a scope

- **Pure, stateless service:** keep the default `singleton`; low overhead and clear lifecycle.
- **Each bean request represents a fresh job/state:** consider `prototype` with `ObjectProvider`, while managing cleanup yourself.
- **Data living strictly for one HTTP request:** `@RequestScope`, especially when multiple processing layers need request-specific context.
- **Data needing retention within one HTTP session:** `@SessionScope` after weighing memory, timeouts, distribution, serialization, and concurrency.
- **Data tied to one web application/`ServletContext`:** `@ApplicationScope` when exact `ServletContext` semantics are needed; global state across JVMs must move to shared storage.
- **Data tied to a STOMP WebSocket session:** `websocket` scope in an appropriately configured environment.

Self-check knowledge: Why can a singleton controller use a `@RequestScope` bean for different requests without recreating the controller? Why does directly injecting a prototype into a singleton fail to yield a new prototype on each method call? Why doesn't `@SessionScope` guarantee thread safety? If you can explain all three using **dependency resolution timing, proxy delegation, and scope boundaries**, you have mastered the core mechanism.

## 13. Official Documentation

- [Spring Framework 6.1 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-scopes.html)
- [`@RequestScope` Javadoc (Spring Framework 6.1)](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/web/context/annotation/RequestScope.html)
- [Spring Framework 6.2 — WebSocket Scope](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/scope.html)
- [`@WebSocketScope` Javadoc (Spring Framework 7.0+)](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketScope.html)
