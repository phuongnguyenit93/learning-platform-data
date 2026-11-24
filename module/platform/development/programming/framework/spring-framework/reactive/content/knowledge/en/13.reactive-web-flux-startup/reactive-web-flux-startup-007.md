# Shutting Down the Server, `ApplicationContext`, and Network Resources in Lifecycle Order in Spring WebFlux

## 1. Why must lifecycles be managed together?

A Spring WebFlux application usually has several long-lived components:

- **HTTP server** accepting connections and handling requests, such as Reactor Netty `HttpServer`.
- **Event loop** coordinating I/O and callbacks on dedicated threads.
- **HTTP client** such as `WebClient`, which may maintain a connection pool to call external services.
- **Spring `ApplicationContext`** creating, wiring, and managing beans such as controllers, services, filters, clients, and resource factories.
- **Per-request resources** such as `DataBuffer`, response bodies, subscriptions, and in-flight tasks.

These components have dependency relationships. An in-flight request may need to call `WebClient`, read a reactive database, and write a response. If you close the connection pool or event loop before requests finish, in-flight requests may fail. If you only close the server and forget resources created by the application itself, threads and connections may continue to exist after the server stops accepting requests.

Managing lifecycles properly means **initializing resources before accepting traffic, stopping new requests first, giving running work time to complete, and then closing shared resources when no one is using them anymore**.

This lesson focuses on Spring Boot WebFlux running Reactor Netty. The concepts of `ApplicationContext`, lifecycle, and resource ownership remain useful when using other reactive servers, though specific APIs of Jetty/Tomcat/Undertow will differ.

## 2. Distinguishing the server, ApplicationContext, and network resources

Three concepts are often lumped together but have different owners and lifecycles.

| Component | Role | Who usually manages its lifecycle? |
|---|---|---|
| `HttpServer` / `DisposableServer` | Binds address/port, accepts connections, and serves HTTP | Reactor Netty or Spring Boot web server lifecycle |
| `ApplicationContext` | Creates beans, manages dependencies, application startup and shutdown | Spring Framework / Spring Boot |
| `LoopResources` | Group of event loops and threads handling I/O | Reactor Netty or `ReactorResourceFactory` |
| `ConnectionProvider` | Manages the outbound connection pool of Reactor Netty HTTP clients | Reactor Netty or `ReactorResourceFactory` |
| `HttpResources` | Shared Reactor Netty resources, including event loops and related client resources | Reactor Netty; can be managed by Spring via a factory |
| `DataBuffer` / Netty `ByteBuf` | Memory holding request/response data | The operator/handler owns the buffer and must release it per rules |

### 2.1. The server is not synonymous with the event loop

`DisposableServer` represents a bound server. When the server is disposed, the server's listener/channel is closed according to the server API. `LoopResources`, by contrast, is the group of event loops used to execute I/O. One application can have multiple servers/clients sharing loop resources.

Therefore, **closing one server does not automatically mean every network resource of the application has been freed**. Conversely, disposing a shared event loop while another server or `WebClient` is still active will break those components.

### 2.2. `ConnectionProvider` primarily serves outbound connections

`ConnectionProvider` manages the pool of Reactor Netty `HttpClient`/`TcpClient`, i.e., connections the application **actively opens to other services**. Inbound connections that the server receives from browsers/clients are managed at the server and Netty channel layer.

Boot can configure sharing of Reactor Netty resources between the server and `WebClient` when the same technology is used and the client is obtained from Boot's auto-configured `WebClient.Builder`. Sharing helps reduce the number of thread groups and avoid creating multiple unnecessary resource pools.

Do not interpret `ConnectionProvider` as the pool of incoming HTTP requests to the server; those are two different communication directions.

### 2.3. `ApplicationContext` and Reactor `Context` are two different concepts

- **Spring `ApplicationContext`** is the container managing singleton beans, dependencies, and application lifecycle. When the context closes, Spring sends stop signals to lifecycle beans and invokes resource destruction callbacks.
- **Reactor `Context`** is metadata attached to a subscription, such as trace ID or tenant ID. It travels along the reactive chain and does not own servers, thread pools, or connection pools.

`contextWrite` or `deferContextual` does not start or close resources. To manage resources, use Spring bean lifecycle, Reactor Netty disposal APIs, or the management mechanism appropriate to that resource.

## 3. Reactor Netty resources you need to know

### 3.1. `LoopResources`

`LoopResources` provides the event loop group and channel factory for Reactor Netty. The event loop receives I/O events and runs callbacks; many connections can share a limited number of threads.

Lifecycle to remember:

- Create loop resources when the application prepares to start.
- Reuse them for servers/clients designed to share.
- Dispose only after the servers/clients using them have stopped.
- If using self-created `LoopResources`, the application is responsible for managing and disposing them.

Do not create a new `LoopResources` per request or per WebClient call. Doing so increases threads and OS resources while making shutdown complicated.

### 3.2. `ConnectionProvider`

`ConnectionProvider` manages the outbound connection pool. A pool can limit active connections, pending acquire requests, and acquire timeouts. These limits protect the application from opening too many connections to the same service.

During shutdown:

1. Stop creating new outbound requests.
2. Allow running requests to finish within the grace period if possible.
3. Dispose the connection provider after the components using the pool have stopped.
4. Ensure retries/reconnects do not keep creating new requests while the application is closing.

If the client and server share resources, do not dispose the pool or loop just because an individual endpoint/server has stopped.

### 3.3. `HttpResources` and global resources

Reactor Netty provides global resources in `reactor.netty.http.HttpResources`. This is a convenient shared mode for applications whose lifecycle matches the JVM lifecycle.

There is an important difference:

- If the application lives until the JVM exits, global resources can usually live with the process.
- If the Spring `ApplicationContext` can be closed and reopened in the same JVM (e.g., integration tests or embedded applications), you need a resource owner that manages shutdown per context.
- When multiple servers/clients share global resources, disposing global resources affects **all** of those components, not just one bean.

Do not call `HttpResources.disposeLoopsAndConnections()` in `@PreDestroy` of an arbitrary service if another service still uses Reactor Netty. Use a Spring-managed `ReactorResourceFactory` or let global resources live with the process when that is the architectural intent.

## 4. `ReactorResourceFactory`: delegating resources to Spring management

Spring Framework provides `ReactorResourceFactory` to manage Reactor Netty resources such as `LoopResources` and `ConnectionProvider` within the `ApplicationContext` lifecycle.

When registered as a Spring bean, the factory can start resources during lifecycle startup and close them during lifecycle shutdown. Spring Boot configures the factory automatically when auto-configuring the Reactor Netty server. If you use the Boot-provided `WebClient.Builder`, the Reactor Netty server and client can share resources.

### 4.1. Using global resources (default)

For typical applications, `useGlobalResources` defaults to `true`. The factory manages global `HttpResources` along the Spring lifecycle. You do not need to call `HttpResources.dispose...` yourself in each service.

If you need to customize shutdown timing, you can declare a bean:

```java
@Configuration(proxyBeanMethods = false)
class ReactorResourceConfiguration {

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        ReactorResourceFactory factory = new ReactorResourceFactory();

        factory.setShutdownQuietPeriod(Duration.ofSeconds(2));
        factory.setShutdownTimeout(Duration.ofSeconds(15));

        return factory;
    }
}
```

The code above is for Spring Framework 6.1+ (package `org.springframework.http.client.ReactorResourceFactory`) and a Spring Boot application using Reactor Netty. Required imports:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.ReactorResourceFactory;
```

`shutdownQuietPeriod` is the quiet period before loop resources shut down; if a new task is submitted during that interval, the wait restarts. `shutdownTimeout` is the maximum limit to wait for disposal to complete. Reactor Netty's defaults are usually 2 seconds quiet period and 15 seconds timeout; choose values according to the application's overall shutdown time.

If Spring Boot already provides the factory automatically, declare a custom bean only when you need to change its configuration. A custom `ReactorResourceFactory` bean is used by Boot to configure the resources of the Reactor Netty server and client.

### 4.2. Using dedicated resources instead of global

You can set `setUseGlobalResources(false)` so the factory creates dedicated resources managed per context:

```java
@Bean
ReactorResourceFactory reactorResourceFactory() {
    ReactorResourceFactory factory = new ReactorResourceFactory();
    factory.setUseGlobalResources(false);
    factory.setShutdownQuietPeriod(Duration.ofSeconds(2));
    factory.setShutdownTimeout(Duration.ofSeconds(15));
    return factory;
}
```

In this mode, servers/clients that need to share the same resources must be configured to use that exact factory. If you create additional `LoopResources` or `ConnectionProvider` somewhere else yourself, you must clearly define who owns and who disposes each instance.

When providing custom suppliers:

```java
factory.setLoopResourcesSupplier(
        () -> LoopResources.create("application-http")
);

factory.setConnectionProviderSupplier(
        () -> ConnectionProvider.builder("application-http")
                .maxConnections(100)
                .build()
);
```

This is advanced configuration. The suppliers above are only used when the factory manages dedicated resources; they have no effect when the factory uses global resources. `maxConnections(100)` is an example and needs to be sized according to load, number of target hosts, and external service limits.

Do not create a new factory or pool for each request handled. Place them at the ApplicationContext level so beans share them and the lifecycle is controlled.

## 5. Startup: initializing resources before accepting traffic

A common startup sequence:

```text
Process starts
    |
    v
Spring ApplicationContext refresh
    |
    v
Create beans and ReactorResourceFactory
    |
    v
Start LoopResources / ConnectionProvider
    |
    v
Start reactive web server and bind port
    |
    v
Application ready
    |
    v
Readiness probe allows accepting traffic
```

Spring Boot manages most of this sequence. When a custom server or resource factory is needed, make sure resources are initialized before the server uses them.

### 5.1. Warmup and first-request startup time

Reactor Netty usually initializes event loops and native transport on demand; the bind operation can pay part of this initialization cost. When first-request latency matters, you can consider warming up the server before advertising readiness.

Reactor Netty API example:

```java
HttpServer httpServer = HttpServer.create()
        .host("127.0.0.1")
        .port(8080);

httpServer.warmup().block();

DisposableServer server = httpServer
        .handle((request, response) ->
                response.sendString(Mono.just("ready\n")))
        .bindNow();
```

This is an illustrative snippet for an application managing `HttpServer` itself. `warmup()` initializes the necessary components according to server configuration, without replacing the `bind()` operation. `block()` here is in the bootstrap phase on the main thread; do not put it on the event loop or in a request handler.

### 5.2. Readiness and liveness

Readiness answers the question: can the instance accept new requests? Liveness answers the question: is the process still running?

Do not mark an instance ready just because the JVM has started. Wait until the server binds and mandatory dependencies are ready. When shutdown begins, readiness should switch to false or the instance needs to be removed from the load balancer before the server closes.

Readiness does not replace draining running requests. It stops new traffic from being routed to the instance; graceful shutdown handles requests already received.

## 6. Shutdown: stopping in the right order

A safe shutdown process usually has these phases:

```text
Receive SIGTERM / close ApplicationContext
              |
              v
Mark instance no longer ready
              |
              v
Stop accepting new requests
              |
              v
Let running requests finish within grace period
              |
              v
Stop background workers and dependent tasks
              |
              v
Close server and client resources
              |
              v
Close database / message clients / remaining beans
              |
              v
ApplicationContext closes completely
              |
              v
Process exits
```

The exact order among beans depends on lifecycle/phase configuration. With Spring Boot, graceful shutdown of the embedded web server happens in an early phase of stopping `SmartLifecycle` beans. This allows the server to stop accepting new requests before dependencies needed to serve requests are closed.

If you write background runner beans or consumers yourself, design their lifecycle so they stop accepting new work and finish in-progress work before dependencies are disposed.

### 6.1. Graceful shutdown in Spring Boot

It can be configured explicitly in `application.properties`:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Or YAML:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
```

During the grace period, Reactor Netty stops accepting new requests at the network layer and gives in-flight requests a chance to complete. When the timeout expires, the application still must proceed with stopping; unfinished requests may be cancelled or connections closed.

`spring.lifecycle.timeout-per-shutdown-phase` is the wait time for one lifecycle phase. This is not a per-HTTP-request timeout or a database timeout. Configuring timeouts on each HTTP client/database client is still necessary.

In modern Spring Boot, graceful shutdown is integrated into the embedded server lifecycle; declaring the property explicitly keeps configuration intentional and easy to verify across environments/versions.

### 6.2. SIGTERM, Docker, and Kubernetes

Graceful shutdown requires the process to receive an appropriate stop signal, usually `SIGTERM`. `SIGKILL` terminates the process immediately and gives the application no chance to run cleanup callbacks. Some Stop actions in an IDE may also not send signals like a production environment does.

In a container/orchestrator:

1. Remove the instance from readiness/load balancer.
2. Wait an appropriate deregistration/endpoint propagation time.
3. Send `SIGTERM` to the process.
4. Let Spring Boot drain requests during the grace period.
5. Only afterward force-stop the process if `terminationGracePeriodSeconds` is exceeded.

The allowed container stop time needs to be larger than the application's drain time plus the time needed for the orchestrator to stop sending new traffic. If the orchestrator's timeout is shorter than the application's timeout, the process may be killed before cleanup completes.

### 6.3. Long requests, streaming, and WebSocket

A typical request may complete in a few milliseconds or a few seconds. Server-Sent Events, WebSocket, and streaming responses can hold connections much longer.

Do not assume every connection will finish by itself within the grace period. A separate policy is needed:

- Clients can reconnect after the server stops.
- Streams can emit a final event or cursor/checkpoint for the client to resume.
- Background tasks need checkpoints or persisted progress state.
- Shutdown timeout must be enough for work permitted to drain.
- If the timeout expires, accept closing the connection and design controlled client retry/reconnect.

Graceful shutdown does not guarantee every infinitely long-lived request is kept open until completion.

## 7. Managing `DisposableServer` yourself without Spring Boot

Spring WebFlux provides the HTTP processing abstraction; if you create a Reactor Netty server yourself, the application must own the lifecycle of `DisposableServer`.

Example:

```java
DisposableServer server = HttpServer.create()
        .host("127.0.0.1")
        .port(8080)
        .handle((request, response) ->
                response.sendString(Mono.just("hello\n")))
        .bindNow();

System.out.println("Listening on port " + server.port());

Runtime.getRuntime().addShutdownHook(new Thread(() -> {
    server.disposeNow(Duration.ofSeconds(10));
}));

server.onDispose().block();
```

Meaning:

- `bindNow()` binds the server and returns `DisposableServer`.
- `port()` returns the port the server is listening on.
- `onDispose()` is a Publisher observing when the server has closed.
- `disposeNow(Duration)` requests closing the channel and waits up to the specified timeout.
- `onDispose().block()` keeps the main thread waiting for the server to finish; this is a lifecycle wait in the bootstrap program, not blocking on the event loop.

`disposeNow()` is a blocking API; call it only on a suitable main/shutdown thread. Do not call it from `HttpHandler`, a controller, or an event-loop callback.

The snippet above demonstrates manual server shutdown. If you need to drain in-flight requests according to a production policy, use Spring Boot's graceful shutdown or implement a drain mechanism suited to the server/channel group and timeout. Do not assume that every `disposeNow()` call waits indefinitely by default for all active requests.

A self-created server can also be managed by Spring through bean lifecycle, but then you must ensure the bean stops in the right phase and resources are not disposed before the server. Avoid creating a server inside a secondary initializer method and forgetting to register a close callback for it.

## 8. Complete Java 17+ example with Spring Boot WebFlux

The following example creates a WebFlux application with a fast endpoint and a 5-second endpoint. When the process receives a shutdown signal, Spring Boot stops accepting new requests, waits for current requests during the grace period, and then closes the Spring-managed Reactor Netty resources.

Structure:

```text
webflux-lifecycle-demo/
├── pom.xml
└── src/main/java/demo/LifecycleDemoApplication.java
└── src/main/resources/application.properties
```

File `pom.xml`:

```xml
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

    <groupId>demo</groupId>
    <artifactId>webflux-lifecycle-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

File `src/main/java/demo/LifecycleDemoApplication.java`:

```java
package demo;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.ReactorResourceFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class LifecycleDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LifecycleDemoApplication.class, args);
    }

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        ReactorResourceFactory factory = new ReactorResourceFactory();

        // Use global Reactor Netty resources and let Spring manage their lifecycle.
        factory.setUseGlobalResources(true);
        factory.setShutdownQuietPeriod(Duration.ofSeconds(2));
        factory.setShutdownTimeout(Duration.ofSeconds(15));

        return factory;
    }
}

@RestController
class LifecycleController {

    @GetMapping("/health")
    Mono<String> health() {
        return Mono.just("ready\n");
    }

    @GetMapping("/slow")
    Mono<String> slow() {
        return Mono.delay(Duration.ofSeconds(5))
                .thenReturn("request completed\n");
    }
}
```

File `src/main/resources/application.properties`:

```properties
server.port=8080
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Run from the project directory with JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

Check the endpoint:

```bash
curl http://localhost:8080/health
```

Body:

```text
ready
```

Send a 5-second request:

```bash
curl http://localhost:8080/slow
```

Body when the request completes:

```text
request completed
```

To observe shutdown, start `/slow`, then send `SIGTERM` to the process while the request is running. If the grace period is long enough, the request can complete and the response is returned before the context finishes closing. Specific shutdown logs vary by Spring Boot version and runtime environment.

**Why does this example manage the lifecycle properly?**

1. `SpringApplication.run(...)` creates the `ApplicationContext` and lets Boot manage the embedded server.
2. `ReactorResourceFactory` is a context bean; the factory manages Reactor Netty global resources.
3. The `/slow` endpoint returns a non-blocking `Mono` using `Mono.delay`; the request does not hold an event-loop thread while waiting.
4. During shutdown, the server stops accepting new requests and gives running requests time to finish.
5. After the server stops per lifecycle, the factory closes resources according to the configured quiet period/timeout.
6. The application does not dispose global resources itself inside a controller or service.

This is an integration pattern for Spring Boot 3.3.5, Spring Framework 6.1, and Java 17. If your project uses another Spring Boot/Spring Framework version, let Boot's BOM manage versions and check the corresponding packages/APIs.

## 9. When to use global resources vs. dedicated resources?

| Situation | Appropriate choice | Reason |
|---|---|---|
| Normal Boot application, one lifecycle tied to the JVM | Global resources via the default factory | Server and WebClient can share event loops, reducing resource count |
| Application with multiple Reactor Netty servers/clients in the same context | One shared resource factory | There is one clear owner for resources |
| Embedded application, context closed/reopened in the same JVM | Spring-managed `ReactorResourceFactory` | Resources can be stopped with the context |
| Need pool/thread isolation between groups of clients or servers | Deliberately configured dedicated resources | Independent limits and lifecycles can be set |
| One component only stops an endpoint while the app still calls WebClient | Stop only the server component | Does not break resources still shared by the client |
| Running tests that create servers manually | Dispose server in teardown | Avoids ports and channels staying alive between tests |

Dedicated-resources mode does not mean every bean must have its own pool. If multiple servers/clients need to share, share one factory or pass the same resource instance to them. Too many pools increase threads, connections, memory, and shutdown complexity.

## 10. Common lifecycle management mistakes

### Mistake 1: Closing only the server and forgetting self-created resources

A `DisposableServer` has stopped, but `LoopResources` or `ConnectionProvider` created by the application itself may still be alive. Non-daemon threads or active connection pools can keep the JVM from exiting.

**How to handle:** identify who creates resources, register an owner in the Spring context, or call dispose in the teardown of the component that owns them.

### Mistake 2: Disposing global resources from a service

A service calling `HttpResources.disposeLoopsAndConnections()` can cause other servers/clients in the same JVM to lose their event loop or pool.

**How to handle:** let `ReactorResourceFactory` manage global resources per context, or dispose only when the application is truly the sole owner and all servers/clients have stopped.

### Mistake 3: Closing ConnectionProvider before requests finish draining

An in-flight request may still need `WebClient` to call another service. If the outbound pool closes first, that request can fail mid-flight.

**How to handle:** stop accepting new requests, wait for current requests to finish within the grace period, and only then close the pool.

### Mistake 4: Calling `.block()` or `disposeNow()` in a request handler

This is a blocking operation. If it runs on an event loop, it can hold the thread serving many connections and stall the entire server.

**How to handle:** return a Publisher from the handler/controller. Use blocking APIs only on the main thread, bootstrap thread, or shutdown thread when waiting is genuinely required.

### Mistake 5: Setting container shutdown timeout shorter than the application timeout

The orchestrator may send SIGKILL while Spring is still draining requests or closing resources.

**How to handle:** coordinate `spring.lifecycle.timeout-per-shutdown-phase`, resource factory timeouts, deregistration time, and `terminationGracePeriodSeconds`.

### Mistake 6: Using `@PreDestroy` to close everything at once

`@PreDestroy` is convenient for a simple bean, but does not by itself express complex drain ordering among server, workers, clients, and databases. Closing dependencies too early can break in-flight requests.

**How to handle:** use appropriate lifecycle phases, `SmartLifecycle` when async stop with callbacks is needed, or rely on Spring Boot's built-in lifecycle. Use `@PreDestroy` only for simple cleanup after dependent components have stopped.

### Mistake 7: Creating new resources per request

Creating a separate `ConnectionProvider`, `LoopResources`, or scheduler on every request causes resources to grow with traffic and makes timely shutdown very hard.

**How to handle:** create resources at the application/context level, share within the designed scope, and set clear pool/concurrency limits.

### Mistake 8: Thinking Reactor Context is a place to store resources for auto-closing

Reactor Context only propagates metadata along a subscription. It is not a lifecycle container and does not automatically call dispose when a request finishes.

**How to handle:** application-scoped resources should be managed by Spring beans; request-scoped resources must have cleanup tied to `using`, `usingWhen`, `doFinally`, or the corresponding resource-owning API.

### Mistake 9: Forgetting `DataBuffer`/`ByteBuf` cleanup when managing buffers yourself

A buffer that is retained or detached from the normal flow may need to be released the exact number of times. If a buffer is discarded without releasing, a memory leak can occur; if released too early, writing the response can fail.

**How to handle:** prefer Spring/Reactor APIs that manage buffers along the pipeline. When retaining, caching, discarding, or holding buffers outside the flow yourself, follow ownership/reference-count rules and use `DataBufferUtils.release` at the right boundary.

### Mistake 10: Stopping the process with SIGKILL and expecting callbacks to run

SIGKILL does not let Spring invoke `stop`, `destroy`, or shutdown hooks. There is no graceful cleanup at the application level.

**How to handle:** the deployment environment must send SIGTERM and allow enough shutdown time; SIGKILL is only the last resort when the timeout has expired.

## 11. Testing and observing lifecycles

Both startup, normal shutdown, and shutdown under traffic need to be tested.

### 11.1. Verifying the server has stopped

With a self-managed server, you can check `DisposableServer.isDisposed()` after calling dispose and waiting on `onDispose()`:

```java
server.dispose();
server.onDispose().block(Duration.ofSeconds(5));

if (!server.isDisposed()) {
    throw new IllegalStateException("Server is still running");
}
```

This is a test/diagnostic snippet for a manual server. `block()` belongs only in tests or coordinator threads; do not call it in a request handler.

### 11.2. Verifying the Spring context closes

In an integration test, create the context, send requests via `WebTestClient` or an HTTP client, and then close the context. Verify the server no longer accepts requests and resource factories/beans are stopped according to lifecycle.

If tests open multiple contexts in the same JVM, pay special attention to global resources and context closing order. Avoid disposing global resources yourself in one test while another test still uses them.

### 11.3. Observing metrics and logs

Useful signals:

- Time from SIGTERM until process exit.
- Number of in-flight requests when shutdown begins.
- Number of requests completed, cancelled, or timed out during the grace period.
- Event-loop threads and connection pools still alive after the context closes.
- Pending connection acquires, timeouts, and active outbound connections during shutdown.
- `RejectedExecutionException`, connection closed errors, or response write errors during the shutdown phase.

Do not log access tokens, sensitive request bodies, or personal data just to debug shutdown. Choose metrics with cardinality-bounded tags; do not use full URIs containing dynamic IDs as tags if that causes metric counts to grow uncontrollably.

## 12. Self-check exercises

**Question 1.** Does closing `DisposableServer` mean all `LoopResources` and `ConnectionProvider` instances in the application have been closed?

**Answer:** No. Server and network resources can be shared. Each resource must be closed by its proper owner and after the servers/clients using it have stopped.

**Question 2.** Which connections does `ConnectionProvider` usually manage?

**Answer:** Outbound connection pools used by Reactor Netty HTTP/TCP clients to call other services. Inbound connections to the server are managed at the server/channel layer.

**Question 3.** What role does `ApplicationContext` play during shutdown?

**Answer:** It coordinates bean lifecycles: sending stop signals, closing resource factories, and invoking destroy callbacks according to lifecycle/phase.

**Question 4.** Can Reactor Context replace `ReactorResourceFactory`?

**Answer:** No. Reactor Context propagates metadata along a subscription; `ReactorResourceFactory` manages resources along the Spring context lifecycle.

**Question 5.** Why must the server stop accepting new requests before closing the WebClient connection pool?

**Answer:** In-flight requests may still need WebClient to call external services. If the pool is closed early, current requests can fail before the response completes.

**Question 6.** Does `spring.lifecycle.timeout-per-shutdown-phase=20s` mean every request gets up to 20 seconds individually?

**Answer:** No. It is the timeout for one shutdown lifecycle phase. Requests remaining when the grace period expires may be cancelled or have their connections closed.

**Question 7.** Why is SIGKILL unsuitable for graceful shutdown?

**Answer:** SIGKILL terminates the process immediately without letting Spring run lifecycle callbacks or resource cleanup.

**Question 8.** If the server and WebClient share global Reactor Netty resources, should a service bean call `HttpResources.disposeLoopsAndConnections()` itself in `@PreDestroy`?

**Answer:** No. That action can break other servers/clients sharing the resources. Let the resource factory manage them per ApplicationContext.

## 13. Production checklist

1. Clearly identify the owners of the server, `LoopResources`, `ConnectionProvider`, WebClient, database pool, and background workers.
2. Prefer Spring Boot auto-configuration; use a `ReactorResourceFactory` bean when resource lifecycle customization is needed.
3. Create resources only at the application/context level; avoid creating them per request.
4. Ensure the server stops accepting new traffic before closing dependencies needed by in-flight requests.
5. Configure graceful shutdown and timeouts matching actual processing times.
6. Coordinate readiness, load balancer deregistration, SIGTERM, and container timeouts.
7. Set separate timeouts for HTTP clients/databases; do not treat the grace period as a timeout for all I/O.
8. Dispose dedicated resources last; do not dispose global resources while other components still use them.
9. Test shutdown during normal requests, slow requests, streaming, and outbound calls.
10. Monitor threads, connection pools, cancelled requests, and process exit duration.
11. For code that manages `DataBuffer`/`ByteBuf` itself, verify ownership and release.
12. Distinguish Spring `ApplicationContext` from Reactor `Context`; each has its own scope and responsibilities.

## 14. Official references

- [Spring Boot — Reactive Web Applications, Reactive Server Resources Configuration](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Framework — ReactorResourceFactory Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/http/client/ReactorResourceFactory.html)
- [Reactor Netty — HTTP Server Reference](https://projectreactor.io/docs/netty/1.1.24/reference/html/#http-server)
- [Reactor Netty — DisposableChannel Javadoc](https://projectreactor.io/docs/netty/1.1.24/api/reactor/netty/DisposableChannel.html)
- [Reactor Netty — HttpResources Javadoc](https://projectreactor.io/docs/netty/1.1.24/api/reactor/netty/http/HttpResources.html)

**Remember:** `ApplicationContext` manages bean lifecycles; the server manages listeners and inbound connections; `ReactorResourceFactory` manages shared event loops and connection resources. During shutdown, stop new traffic, drain running requests, and only then dispose the network resources they depend on.
