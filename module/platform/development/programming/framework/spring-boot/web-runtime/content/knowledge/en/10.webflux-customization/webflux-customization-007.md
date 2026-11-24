# ReactorResourceFactory and Shared HTTP Resource Lifecycle

## 1. The Problem to Solve

A Spring Boot application running Spring WebFlux often both **receives HTTP requests** via Reactor Netty and **calls other HTTP services** via WebClient. Beneath those convenient HTTP abstractions sit real operating-system and Reactor Netty resources: event-loop threads, connection pools, sockets, buffer memory, and objects that must be cleaned up when the application stops.

If every API call created a fresh set of event loops or connection pools, the application would multiply thread counts, exhaust sockets, lose HTTP keep-alive efficiency, and struggle with clean shutdown. Conversely, if every component relies on global resources without understanding ownership boundaries, closing one `ApplicationContext` can unexpectedly disrupt other HTTP clients or servers in the same JVM.

**ReactorResourceFactory** is Spring Framework's integration point for initializing, accessing, and managing the lifecycle of Reactor Netty resources. It enables HTTP components to **share resources properly** and **release them at the right time**, rather than creating, disposing, or leaking pools indefinitely.

This lesson focuses on three questions:

1. Which resources are shared, and what does "sharing" actually mean?
2. What is the difference between the default global resource mode and `ApplicationContext`-owned resources?
3. How should Spring Boot and WebClient use `ReactorResourceFactory` for safe startup, runtime operation, and shutdown?

This covers **Spring WebFlux and Reactor Netty**, not `DispatcherServlet`/Tomcat Servlet configuration. A WebClient can still be used in a Spring MVC application, but the web server model and server resources must be distinguished accordingly.

## 2. Distinguishing Similarly Named Components

| Component | Role | Scope and key notes |
|---|---|---|
| ReactorResourceFactory | Spring bean managing Reactor Netty resources | Provides LoopResources and ConnectionProvider; follows Spring lifecycle |
| LoopResources | Manages Reactor Netty event-loop resources | Supplies event-loop threads for non-blocking I/O |
| ConnectionProvider | Manages HTTP client connection allocation/reuse | Pooling, connection limits, pending acquire, socket reuse |
| HttpResources | Reactor Netty's global HTTP resource set | Shared within **one JVM**, not across a cluster |
| HttpClient | Configuration of a Reactor Netty HTTP client | Uses event loops and a connection provider; does not mean a single TCP connection |
| ReactorClientHttpConnector | Spring WebClient adapter to Reactor Netty HttpClient | Can take a ReactorResourceFactory and an HttpClient customizer |
| WebClient | Spring's high-level reactive HTTP client API | Built from WebClient.Builder; requests return Publishers |
| HttpHandler / DispatcherHandler | Processes HTTP requests in Spring WebFlux | Does not own HTTP client connection pools just by being a handler |
| NettyReactiveWebServerFactory | Factory creating Boot's embedded Reactor Netty web server | Configures the server and can integrate Reactor resources |
| ApplicationContext | Spring container managing beans and lifecycle | Context close is a key milestone for releasing Spring-managed resources |

**A connection pool is not an event loop.** A pool manages reusing outbound HTTP client connections, whereas an event loop executes non-blocking I/O operations. Both can be used by the same `HttpClient`, yet pool limits and event-loop thread counts mean very different things.

**Global does not mean shared across pods or machines.** Reactor Netty's `HttpResources` is global within a single JVM process. Each container/JVM still owns its own threads and sockets.

### 2.1. Event Loops vs. Worker Threads for Blocking Tasks

Reactor Netty typically uses a finite set of event-loop threads to serve many connections. This works well when I/O callbacks do not block. If a WebFlux controller calls JDBC, a blocking SDK, or `Thread.sleep` directly on an event loop, sharing event loops becomes a bottleneck: other requests stall behind it.

`LoopResources` does not make blocking calls non-blocking. When a blocking dependency is unavoidable, offload it onto an appropriate scheduler such as `Schedulers.boundedElastic()` with concurrency caps and deadlines; prefer reactive libraries whenever possible.

### 2.2. A Connection Pool Is Not a Pool of WebClient Instances

A single built `WebClient` instance can handle many requests. Internally, its connector/`HttpClient` coordinates with `ConnectionProvider` to retain and reuse TCP connections whenever HTTP, proxy, TLS, server, and pooling policies permit.

There is no reason to build a new `WebClient` per request just to call the same upstream. Doing so does not necessarily allocate a new pool if it still uses a shared resource factory, yet it increases object allocation, complicates policy management, and invites bugs if someone later changes how `HttpClient` is constructed.

## 3. Why Should HTTP Resources Be Shared?

HTTP clients often perform relatively expensive work:

- DNS lookups and TCP connection establishment.
- TLS handshakes for HTTPS.
- HTTP/1.1 keep-alive state or HTTP/2 connection setup where supported.
- Buffer allocation and channel registration onto event loops.
- Timeouts, idle connection tracking, connection acquisition, and cleanup.

Reusing valid connections lowers connection overhead and latency. Sharing event loops avoids spawning excessive threads as the number of WebClients or modules grows. However, sharing also means components can contend for resources: one client consuming too many connections or a blocking callback stalling an event loop can degrade other clients and the server.

The goal is not "every component must share everything." The goal is **clear resource ownership and bounds**:

- The HTTP server and multiple HTTP clients in the same app can share one resource set.
- A slow or untrusted upstream may need its own connection provider to isolate pool limits.
- `ApplicationContext`-scoped resources can replace global resources when contexts start and stop multiple times in one JVM.
- Never manually dispose resources still in use by other components.
- Never let client/pool counts grow unbounded per request.

### 3.1. Reuse Scope Does Not Mean One TCP Socket for Every Destination

`ConnectionProvider` can manage pools keyed by remote address and connection settings. A TCP connection to `api-a.example` does not become a connection to `api-b.example`. HTTP keep-alive reuses connections only when endpoint, protocol, and client/server policies match.

When people say "two WebClients share a ConnectionProvider," understand that they share **pool management infrastructure** and its limits—not that every request shares one TCP socket regardless of host.

## 4. Two Resource Strategies: Global vs. ApplicationContext-Managed

### 4.1. Reactor Netty Global Resources

Reactor Netty provides global HTTP resources via `HttpResources`. Default `HttpClient`/`HttpServer` APIs can use this shared event-loop and connection-provider set.

On `ReactorResourceFactory`, **`useGlobalResources`** defaults to `true`. When enabled, the factory delegates to the global HTTP resources. This is usually a sensible default when a JVM hosts a single primary application and wants to reuse Reactor Netty's default event loops and connection pools.

Diagram:

~~~text
JVM Process
  |
  +-- Reactor Netty HttpResources (global in JVM)
  |     +-- LoopResources / event loops
  |     +-- ConnectionProvider / pooled connections
  |
  +-- Spring ApplicationContext
        +-- ReactorResourceFactory (useGlobalResources=true)
        +-- Reactor Netty HTTP server
        +-- WebClient A -> ReactorClientHttpConnector
        +-- WebClient B -> ReactorClientHttpConnector
~~~

In an application with a Spring-managed `ReactorResourceFactory`, the factory's lifecycle also helps ensure global resources are released cleanly when the `ApplicationContext` closes. This is especially useful if an `ApplicationContext` starts and stops inside a long-lived JVM rather than waiting for process exit.

**Important consideration:** `HttpResources` is global across the JVM. If multiple independent `ApplicationContext`s share the global resources, one context shutting down global resources can break another active context. Do not use "global resources with each context shutting down independently" in a multi-context JVM without unified ownership design.

### 4.2. Dedicated Spring-Managed Resources

When `useGlobalResources=false`, `ReactorResourceFactory` creates and manages **its own dedicated `LoopResources` and `ConnectionProvider`** via configured suppliers. Those resources can still be shared among multiple HTTP clients and the server inside that `ApplicationContext` as long as they are wired to the same factory.

Diagram:

~~~text
Spring ApplicationContext
  |
  +-- ReactorResourceFactory (useGlobalResources=false)
  |     +-- Dedicated LoopResources
  |     +-- Dedicated ConnectionProvider
  |
  +-- HTTP server --------------> Factory's LoopResources (when integrated)
  |
  +-- WebClient A --------------> Connector using same factory
  |
  +-- WebClient B --------------> Connector using same factory
  |
  +-- Context close
        +-- Stop accepting requests and complete shutdown phases
        +-- ReactorResourceFactory releases its owned resources
~~~

The benefit is clear ownership tied to the Spring context. This fits applications with dynamic lifecycles in one JVM, integration tests creating and closing many contexts, or workloads needing distinct pools, worker threads, or policies. The trade-off is that you must **wire clients and server explicitly to the dedicated factory**: code elsewhere calling `HttpClient.create()` directly without resource config may still fall back to default global resources.

### 4.3. Selection Comparison

| Factor | useGlobalResources=true | useGlobalResources=false |
|---|---|---|
| Underlying resource set | Global Reactor Netty HttpResources | LoopResources/ConnectionProvider created/managed by factory |
| Natural scope | Same JVM | Components wired to the factory |
| Ease of setup | High; generally a good default | Requires explicit wiring and policies |
| Lifecycle | Tied to global resources; care needed with multiple contexts | Closes with the Spring-managed factory/context |
| Control over pool/event-loop config | Mostly through global mechanisms and supported customizers | Can configure dedicated suppliers and custom settings |
| Isolation from other apps in same JVM | Low if sharing globals | Better when all components are wired properly |
| Misconfiguration risk | Disposing globals while another context uses them | Mixing global and dedicated resources or creating unintended pools |

No single mode fits every deployment. In a Spring Boot microservice running in its own JVM, the global default is usually simple and effective. When lifecycle isolation is needed, use a dedicated factory with explicit resource ownership.

## 5. What Does ReactorResourceFactory Provide and Manage?

The class resides in package:

~~~java
org.springframework.http.client.reactive.ReactorResourceFactory
~~~

It is Spring Framework's integration component for Reactor Netty. Key APIs include:

| API or concept | Meaning |
|---|---|
| setUseGlobalResources(boolean) | Choose global HttpResources vs. dedicated resources |
| setConnectionProviderSupplier(...) | Supply how ConnectionProvider is created when not using globals |
| setLoopResourcesSupplier(...) | Supply how LoopResources is created when not using globals |
| getConnectionProvider() | Access the ConnectionProvider managed by the factory |
| getLoopResources() | Access the LoopResources managed by the factory |
| setShutdownQuietPeriod(Duration) | Configure the quiet period during resource shutdown where supported |
| setShutdownTimeout(Duration) | Cap total resource shutdown wait time where supported |
| start(), stop(), isRunning() | Spring lifecycle integration methods |

These method names belong to Spring Framework used alongside Spring Boot 3.x. When upgrading, consult the exact Javadoc of your running dependency, as defaults, timeouts, and Reactor Netty classes may evolve.

**Do not confuse the factory with an HttpClient or WebClient.** The factory owns/shares resources; `HttpClient` uses resources to drive HTTP transport; `WebClient` is the request API called by your code. Creating a factory alone makes no HTTP requests.

### 5.1. Why Creating the Bean Alone Isn't Always Enough

Spring Boot provides auto-configuration for Reactor Netty where applicable. In a Boot app using `starter-webflux` and the Reactor Netty server, Boot normally creates/wires a `ReactorResourceFactory` according to configuration and bean conditions. If your application declares its own `ReactorResourceFactory` bean, verify that both the server factory and HTTP clients actually wire into that bean.

A third-party library might directly call `HttpClient.create()`, build a new `ConnectionProvider`, or spin up its own event loops. Those objects do not automatically adopt your factory just because a bean of that type exists in the `ApplicationContext`.

Therefore, verify these boundaries:

- Whether the Spring Boot reactive web server actually runs Reactor Netty or another engine.
- Which `ReactorResourceFactory` bean is injected in practice.
- Which `WebClient` instances use a `ReactorClientHttpConnector` bound to that bean.
- Whether third-party SDK `HttpClient`s use global resources or private pools.
- Whether a second factory bean or customizer is creating unintended resources.

## 6. How Do the HTTP Server and WebClient Share Resources?

In Spring Boot WebFlux with Reactor Netty, there are two primary paths:

**Server path:**

~~~text
Reactor Netty HttpServer
    -> accepts connections on server.port
    -> uses LoopResources/event loops for I/O
    -> Spring HttpHandler / WebHandler chain
    -> DispatcherHandler / HandlerMapping / HandlerAdapter
    -> @RestController or functional endpoint
~~~

**Client path:**

~~~text
Spring WebClient
    -> ClientHttpConnector (ReactorClientHttpConnector)
    -> Reactor Netty HttpClient
    -> ConnectionProvider allocates/reuses matching connections
    -> LoopResources processes I/O
    -> response delivered to WebClient as Mono/Flux
~~~

`ConnectionProvider` primarily governs **outbound HTTP client connection pools**. Never describe it as an "inbound server TCP pool" or use the HTTP client's `maxConnections` to infer how many requests the server can accept.

When both paths share `LoopResources`, HTTP server and HTTP client callbacks may execute on the same set of event loops. This fits non-blocking I/O well but requires application code never to block event-loop threads.

### 6.1. Using Boot-Provided WebClient.Builder

When configuring `WebClient` in a Boot app, prefer injecting `WebClient.Builder` to preserve Boot's customizations (codecs, observations, conditional HTTP connector) rather than calling `WebClient.builder()` from scratch every time.

Example:

~~~java
@Bean
WebClient partnerClient(WebClient.Builder builder) {
    return builder.baseUrl("https://partner.example")
            .build();
}
~~~

This is a snippet for a `@Configuration` class or bean factory method; the URL is illustrative, not a live callable endpoint. When using a dedicated factory or ensuring a specific connector is selected, pass a `ReactorClientHttpConnector` configured with that factory as shown below.

Do not construct a fresh `WebClient` inside every request handler just to vary the base URL; for a bounded set of remote endpoints, declare centrally configured client/connector beans and reuse them. If many dynamic base URLs are needed, design URI handling and per-upstream pool limits intentionally.

## 7. Spring Boot 3.x Example: Creating Dedicated Resources and Sharing Them

This example uses Java 17+, Spring Boot 3.x, WebFlux, and default Reactor Netty. Its goal is to show a **single `ReactorResourceFactory` declaration** reused by an HTTP client. A `/proxy/{id}` endpoint calls `/echo/{id}` on the same application over HTTP so it can be tested locally without external APIs.

File structure:

~~~text
src/main/java/dev/example/resources/
    ResourceDemoApplication.java
    SharedResourcesConfiguration.java
    DemoController.java
src/main/resources/
    application.yml
~~~

### 7.1. Dependencies

In a Gradle project already configured with the Spring Boot plugin and repositories (for example, generated via Spring Initializr), add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Do not add `spring-boot-starter-web` to this demo if you want to guarantee the reactive web server runs. When both MVC and WebFlux are on the classpath, Spring Boot follows rules to choose the web application type; seeing `WebClient` in a project does not prove the server is reactive.

### 7.2. Main Class

File `src/main/java/dev/example/resources/ResourceDemoApplication.java`:

~~~java
package dev.example.resources;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceDemoApplication.class, args);
    }
}
~~~

### 7.3. A Shared ReactorResourceFactory

File `src/main/java/dev/example/resources/SharedResourcesConfiguration.java`:

~~~java
package dev.example.resources;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.http.client.reactive.ReactorResourceFactory;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.resources.ConnectionProvider;
import reactor.netty.resources.LoopResources;

@Configuration(proxyBeanMethods = false)
public class SharedResourcesConfiguration {

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        ReactorResourceFactory factory = new ReactorResourceFactory();

        factory.setUseGlobalResources(false);

        factory.setConnectionProviderSupplier(
                () -> ConnectionProvider.builder("shared-demo-pool")
                        .maxConnections(80)
                        .pendingAcquireTimeout(Duration.ofSeconds(2))
                        .build());

        factory.setLoopResourcesSupplier(
                () -> LoopResources.create("shared-demo-http"));

        return factory;
    }

    @Bean
    WebClient localWebClient(
            WebClient.Builder builder,
            ReactorResourceFactory resources) {

        ReactorClientHttpConnector connector =
                new ReactorClientHttpConnector(
                        resources,
                        httpClient -> httpClient
                                .responseTimeout(Duration.ofSeconds(4)));

        return builder
                .baseUrl("http://127.0.0.1:8080")
                .clientConnector(connector)
                .build();
    }
}
~~~

Explanation of each choice:

1. **`useGlobalResources(false)`**: creates a dedicated resource set managed by the factory instead of JVM-global `HttpResources`.
2. **`setConnectionProviderSupplier`**: provides a named `ConnectionProvider` for diagnostics/metrics, bounding connection acquisition and wait duration.
3. **`setLoopResourcesSupplier`**: creates an event-loop resource set with a custom thread name prefix for I/O threads.
4. **`ReactorClientHttpConnector(resources, mapper)`**: when `WebClient` uses this connector, it uses resources from the factory and the mapper configures `HttpClient`—for example, setting response timeout.
5. **Injected `WebClient.Builder`**: retains Boot's general customizations while explicitly setting the connector for this client.
6. **Spring lifecycle manages the factory**: never call dispose directly inside controllers or per request.

The numbers 80 connections, 2s pending-acquire, and 4s response timeout are demo values—**not default values or production recommendations**. Appropriate values depend on remote endpoints, load, latency, connection caps, and SLOs.

`ConnectionProvider.maxConnections` typically caps connections per pool managed by the provider for each target/connection key; do not conclude the entire JVM opens at most 80 sockets across multiple remote endpoints. `pendingAcquireTimeout` limits how long a request waits for an available pooled connection; `responseTimeout` limits waiting for an HTTP response per Reactor Netty semantics. Neither replaces an overall business request deadline.

**Important:** This code demonstrates `WebClient` using the injected factory. In Spring Boot with Reactor Netty, the server factory can also integrate with `ReactorResourceFactory` via matching auto-configuration; verify your stack and version if your goal is proving the client and server share the exact same `LoopResources`. An `HttpClient` created outside Spring can still use global resources.

### 7.4. Controller with a Local Endpoint and a Proxy Endpoint

File `src/main/java/dev/example/resources/DemoController.java`:

~~~java
package dev.example.resources;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    public record Message(String value) {}

    private final WebClient localWebClient;

    public DemoController(
            @Qualifier("localWebClient") WebClient localWebClient) {
        this.localWebClient = localWebClient;
    }

    @GetMapping("/echo/{id}")
    public Mono<Message> echo(@PathVariable long id) {
        return Mono.just(new Message("echo-" + id));
    }

    @GetMapping("/proxy/{id}")
    public Mono<Message> proxy(@PathVariable long id) {
        return localWebClient.get()
                .uri("/echo/{id}", id)
                .retrieve()
                .bodyToMono(Message.class);
    }
}
~~~

Neither endpoint uses JDBC, spawns manual threads, or calls `block()`/`subscribe()`. `/proxy` returns `Mono<Message>` to WebFlux so the HTTP runtime subscribes and writes the result. This example calls back into the same process over HTTP to illustrate client/server interaction; in real projects, the upstream is normally another service.

### 7.5. application.yml and Run Commands

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  main:
    web-application-type: reactive
~~~

We keep port 8080 fixed for the demo because `localWebClient` points to `http://127.0.0.1:8080`. In production or `RANDOM_PORT` tests, do not hardcode a client pointing back to the app's port; inject host/port/config from environment properties or design tests appropriately.

From a project directory with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell you can use:

~~~powershell
.\gradlew.bat bootRun
~~~

Once the app starts, test:

~~~bash
curl -i http://localhost:8080/echo/7
curl -i http://localhost:8080/proxy/7
~~~

Under normal conditions, **both** return HTTP 200 with JSON body:

~~~json
{"value":"echo-7"}
~~~

Headers such as `Date`, `Transfer-Encoding`, and `Content-Length` may vary by OS, Reactor Netty version, HTTP protocol, or codec configuration. Do not treat headers as immutable output. If Spring Security is present in a real project, responses may change due to authentication/authorization.

**Key takeaway:** `/proxy` uses `WebClient`, `WebClient` uses `ReactorClientHttpConnector`, and the connector is constructed with the shared `ReactorResourceFactory` bean. They do not allocate new `ConnectionProvider`/`LoopResources` per request. When the `ApplicationContext` closes cleanly, the factory cleans up the resources it owns.

## 8. Sharing One Factory Across Multiple WebClients

Suppose an application calls two upstream services. If both `WebClient` beans receive a `ReactorClientHttpConnector` wired to the same `ReactorResourceFactory`, they can share the same `ConnectionProvider` and `LoopResources`, while each destination still maintains its own pooled connections under the pooling policy.

Illustrative configuration:

~~~java
@Bean
WebClient catalogClient(
        WebClient.Builder builder, ReactorResourceFactory resources) {
    return builder
            .baseUrl("https://catalog.example")
            .clientConnector(new ReactorClientHttpConnector(
                    resources, client -> client))
            .build();
}

@Bean
WebClient billingClient(
        WebClient.Builder builder, ReactorResourceFactory resources) {
    return builder
            .baseUrl("https://billing.example")
            .clientConnector(new ReactorClientHttpConnector(
                    resources, client -> client))
            .build();
}
~~~

These beans are snippets for a `@Configuration` class importing `WebClient`, `ReactorResourceFactory`, `ReactorClientHttpConnector`, and `Bean`. The two hosts are examples, not claims of live services.

Do not instantiate two independent `ReactorResourceFactory` instances inside each `WebClient` bean. Defining one Spring-managed factory bean and injecting that instance is cleaner. If one upstream requires isolated connection limits, you can use a dedicated `ConnectionProvider` with clear ownership, ensuring proper disposal lifecycle and tests rather than creating anonymous pools inside methods.

### 8.1. Reusing WebClient.Builder After Customizing the Connector

`WebClient.Builder` has stateful builder semantics. Calling `baseUrl`/`filters`/`defaultHeaders`/`clientConnector` mutates that builder instance; when building multiple `WebClient`s, make sure builders or `clone()` are used carefully so settings from one client do not leak into another.

Spring Boot normally injects `WebClient.Builder` in an appropriate scope and supports customizers. For complex multi-client setups, define named beans, test each bean's base URL/connector/timeout/filters, and avoid holding a mutable shared builder in uncontrolled state.

## 9. Resource Lifecycle: Startup, Runtime, Shutdown

### 9.1. Startup

Simplified sequence:

~~~text
Spring Boot start
  |
  +-- Create ApplicationContext
  |
  +-- Create ReactorResourceFactory bean
  |      +-- Choose global / non-global
  |      +-- Create or reference LoopResources
  |      +-- Create or reference ConnectionProvider
  |
  +-- Configure reactive web server factory / HTTP connectors
  |
  +-- Start Reactor Netty server
  |
  +-- Run ApplicationRunner / CommandLineRunner
  |
  +-- ApplicationReadyEvent / readiness availability
  |
  +-- HTTP clients and server operate as needed
~~~

Exact timing of resource creation, lazy initialization, callbacks, and port binding depends on Boot/Spring/Reactor Netty versions and supplier usage. Do not treat the diagram as an immutable bytecode sequence for every app.

**An open TCP port does not prove the entire application is ready.** Do not rely solely on a `LISTEN` socket or one `WebClient` check as your entire readiness signal; evaluate Spring Boot state, warm-up, and essential dependencies per system requirements.

### 9.2. Runtime

While serving requests:

- The HTTP server accepts connections and runs on event loops.
- `WebClient` acquires or creates a connection from the provider when calling an upstream.
- Connections return to the pool when responses/bodies are properly consumed and policies allow reuse.
- Idle connections may be closed by the client/provider, server, or network.
- Event-loop threads remain alive to serve new I/O; they are not created/destroyed per HTTP call.
- The connection provider can cap pending acquisitions; under overload, clients fail with acquire timeouts or pool errors instead of growing sockets without bound.
- Cancellation and error handling must complete or release HTTP client resources per Reactor Netty contracts; never leave response bodies unconsumed.

When using `WebClient.retrieve().bodyToMono(...)`, the framework handles decoding and completing the response with the publisher. With lower-level APIs exposing raw responses, your code must consume or release the body so connections are not held indefinitely.

### 9.3. Graceful Shutdown

Desired sequence when a pod or application stops:

1. Orchestration stops routing new requests to the instance when integrated with readiness/draining.
2. The HTTP server stops accepting new connections and finishes in-flight requests within limits.
3. Business components stop initiating unnecessary outbound requests.
4. Spring lifecycle beans stop in the appropriate phase/order.
5. `ReactorResourceFactory` releases its managed `ConnectionProvider` and `LoopResources`.
6. The JVM exits after cleanup completes or the shutdown deadline expires.

Spring Boot supports graceful shutdown for compatible embedded servers; example config:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

These settings belong to server/application lifecycle; they **do not guarantee** every external call finishes, every socket closes gracefully, or zero timeouts occur. Verify client timeouts, ingress/Kubernetes deadlines, and business shutdown logic.

In containers, `SIGTERM` normally initiates shutdown; if `terminationGracePeriodSeconds` is too short, the process can be forcibly killed before resources finish disposing.

### 9.4. Quiet Period and Total Shutdown Timeout

Some Reactor Netty versions support disposing resources with a **quiet period** and **shutdown timeout**. `ReactorResourceFactory` exposes corresponding setters. The quiet period lets resources wind down smoothly where supported instead of abruptly terminating active work; the timeout caps how long shutdown waits.

Do not equate quiet period with a guarantee that "every request returns 200." Coordinate server graceful shutdown, request deadlines, cancellation, pool disposal, and application shutdown. When tuning, measure actual shutdown times under load and when upstreams hang.

### 9.5. Why Never Call Dispose Manually in a Controller?

If `WebClient A` and `WebClient B` share a `ConnectionProvider`/`LoopResources`, a controller calling dispose after finishing one request can break other clients while the application is still running. Likewise, a scheduled job disposing global HTTP resources can break the embedded HTTP server's socket handling.

Rule: **whoever owns a resource decides when its lifecycle ends**. For resources created by a Spring-managed `ReactorResourceFactory`, the Spring `ApplicationContext`/lifecycle is the natural owner. Never call dispose from request-scoped code.

## 10. Scenarios Requiring Different Sharing Strategies

| Scenario | Approach |
|---|---|
| Single Spring Boot microservice in its own JVM | Usually keep default Reactor Netty global resources |
| Multiple WebClients calling the same upstream group | Use WebClient beans with controlled shared connectors/pools |
| Application started/stopped multiple times in one JVM | Consider `ReactorResourceFactory` with explicit lifecycle management |
| Multiple concurrent ApplicationContexts in one JVM | Avoid context shutdown disposing shared globals; design unified ownership |
| Need to isolate a slow/unreliable upstream | Consider a dedicated connection provider and timeout/bulkhead policies |
| Tests spinning up multiple sequential ApplicationContexts | Ensure contexts close cleanly and resource threads/sockets are cleaned up |
| Library creating its own HttpClient | Verify whether it actually uses the shared factory |
| Spring MVC app using WebClient | Shared Reactor Netty resources still apply to outbound clients, while Servlet server does not become Reactor Netty |
| WebFlux server using a non-Reactor Netty engine | Do not assume the server uses Reactor Netty LoopResources |
| Multi-pod deployment | Each JVM/pod has its own resources; pools are never shared across the network |

Crucially, **isolation is not automatically better than sharing**. Giving every service client its own event loops in a JVM with dozens of downstream modules can inflate thread counts and memory overhead. Usually share event loops and control concurrency with connection limits, timeouts, bulkheads, or upstream-specific policies. Separate event loops only with measured justification.

## 11. Sizing: Event Loops, Connections, and Pending Acquire

### 11.1. LoopResources

Event loops execute I/O callbacks. Do not size worker counts using "one thread per HTTP request"; one event loop multiplexes many channels using non-blocking I/O.

Metrics to observe:

- CPU usage of HTTP event-loop threads.
- Event-loop delay/latency and callback execution time.
- Active connection counts and I/O throughput.
- Rate of blocking operations occurring on event loops.
- Total event loops created across the JVM by different libraries.
- Effective container CPU capacity after accounting for CPU quotas/cgroups.

If the bottleneck is blocking JDBC, downstream timeouts, or CPU saturation, adding more event loops will not solve the root cause. Setting event-loop counts too high increases thread and context-switching overhead.

### 11.2. ConnectionProvider

`ConnectionProvider` typically exposes settings such as:

- `maxConnections`: maximum connections the pool may create within its scope.
- `pendingAcquireTimeout`: wait timeout when the pool cannot immediately issue a connection.
- `pendingAcquireMaxCount`: maximum queued acquire requests.
- `maxIdleTime`: duration a connection may sit idle in the pool.
- `maxLifeTime`: maximum age before a connection is retired from reuse.
- eviction/background maintenance: cleanup of stale connections per configuration.

Exact method names and semantics must be checked against your Reactor Netty version. Options like `maxIdleTime`/`maxLifeTime` strongly affect stability when upstreams or load balancers also enforce idle timeouts.

A provider may maintain pools per remote address/connection config. Setting `maxConnections=80` does not mean the entire JVM opens at most 80 sockets across all upstreams, nor does 80 connections strictly equal 80 concurrent requests across all HTTP protocols.

### 11.3. Interpreting Pool Exhaustion

If requests arrive faster than an upstream responds, the pool can fill and requests queue for acquisition. Raising connection limits sometimes increases concurrency, but can also overload the upstream. Check:

1. Is upstream latency climbing?
2. Are unconsumed response bodies or connections failing to release?
3. Are multi-layer retries amplifying call volume?
4. Is pending acquire timeout too short or too long relative to SLOs?
5. Is DNS/TLS/connect timeout or response timeout the real culprit?
6. Is pooling fragmented across many separate `HttpClient`/`ConnectionProvider` instances?
7. Is concurrency capped at the business layer where needed?

Only adjust `maxConnections` after distinguishing pool saturation from network I/O or downstream capacity limits.

## 12. Which Timeouts Belong to the Reactor Netty HTTP Client?

An HTTP call has multiple stages:

~~~text
Wait for connection from pool
     |
     v
DNS / TCP connect / TLS handshake (if opening new connection)
     |
     v
Send HTTP request
     |
     v
Wait for HTTP response and read body
     |
     v
Complete publisher / release connection
~~~

Common timeouts:

| Type | Protects stage | Example |
|---|---|---|
| Pending acquire timeout | Waiting for pool to supply a connection | `ConnectionProvider.pendingAcquireTimeout` |
| Connect timeout | Opening a new TCP connection | `ChannelOption.CONNECT_TIMEOUT_MILLIS` |
| TLS handshake timeout | Completing TLS negotiation | Matching secure/SSL provider settings |
| HTTP response timeout | Waiting for/reading HTTP response per Reactor Netty semantics | `HttpClient.responseTimeout` |
| Overall business deadline | Entire request chain and retries | Reactive `timeout` / service policy |
| Server idle timeout | Idle connections on the server side | Embedded server / proxy configuration |

Do not mistake `responseTimeout=4s` for a guarantee that "every transaction completes within 4 seconds" when the pipeline also includes DNS, pool acquisition, retries, or business steps. Align timeouts across the end-to-end request model.

**WebClient does not automatically retry every failure by default.** If you add `Retry.backoff` in application code, check whether the operation is idempotent and cap total attempts. `ConnectionProvider` does not prevent duplicate charges or orders when retrying a `POST`.

## 13. Testing Resource Sharing and Cleanup

Meaningful tests:

1. Start the WebFlux/Netty application with the desired resource factory configuration.
2. Call an endpoint via `WebClient` multiple times and verify responses.
3. Verify HTTP keep-alive connection reuse where possible, without assuming every call uses the exact same socket.
4. Create multiple `WebClient`s injected with the same factory and confirm they use the configured provider/loop resources.
5. Apply bounded load to verify `pendingAcquireTimeout` and behavior under pool saturation.
6. Close the `ApplicationContext` after tests and observe threads/sockets/resources being released.
7. Open a new `ApplicationContext` in the same JVM and send requests again; check whether global resources were unexpectedly disposed.
8. When running multiple concurrent contexts, close one context and verify the remaining context still serves requests if required.
9. Simulate unresponsive upstreams to verify timeouts, cancellation, and recovery.
10. Test rolling shutdown under load: traffic drains, in-flight requests finish, and resources dispose within deadlines.

### 13.1. WebTestClient Test Example

For the section 7 demo, you can write an HTTP handler-level test:

~~~java
package dev.example.resources;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@WebFluxTest(controllers = DemoController.class)
class DemoControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void echoEndpointWorks() {
        client.get()
                .uri("/echo/7")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.value").isEqualTo("echo-7");
    }
}
~~~

**Test scope note:** `DemoController` requires a `WebClient` constructor dependency; `@WebFluxTest` creates only an MVC/WebFlux slice, so the test above **needs a `WebClient` bean provided in the test context** (e.g., via `@TestConfiguration`) or mocked appropriately. To run the code as-is without stubs, use `@SpringBootTest` with a real HTTP server and call `/echo` via `WebTestClient`, since the full application configuration supplies `localWebClient`.

Do not confuse testing a controller with testing resource lifecycles. `@WebFluxTest` verifies routing/JSON, but **does not prove Reactor Netty connection pools or event loops were created/closed properly** because it may not start a real web server.

### 13.2. Integration Tests with a Real Server

With `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)`, Boot starts a real server. However, the section 7 demo hardcodes `baseUrl("http://127.0.0.1:8080")`, so testing `/proxy` under `RANDOM_PORT` requires passing the dynamic port into the client. A simple way to observe initial resource behavior is running the demo on port 8080 with `bootRun` and exercising it with `curl`/load tools as shown, rather than assuming `RANDOM_PORT` works with a hardcoded base URL.

In automated integration tests, inject the actual port and build a test client against that URL, or start a mock HTTP upstream on a dynamic port instead of hardcoding 8080. Tests should also close both the context and the mock server, then verify cleanup.

## 14. Metrics and Production Diagnostics

Signals to monitor:

- Active/idle/pending HTTP client connections per remote endpoint and pool.
- Connection acquisition latency, pending queue depth, and acquire timeouts.
- Rates of TCP connect, TLS, and response timeout errors.
- Event-loop thread count and occurrences of blocking callbacks.
- CPU, GC, direct memory, file descriptors, and container socket states.
- New connections vs. reused connections under keep-alive.
- Shutdown duration and failed requests during rolling deployments.

Reactor Netty can export metrics via Micrometer when enabled with matching configuration; Spring Boot Actuator can integrate observability. Do not assume every metric always shares identical names: names depend on Reactor Netty version, metrics registry, instrumentation setup, and client/server type.

Never place URLs with random IDs or sensitive query parameters into unbounded metric tags; high cardinality consumes memory and degrades queries. Prefer URI templates, service names, and bounded-cardinality labels.

### 14.1. When Reactor Netty Threads Remain After Shutdown

If Reactor Netty threads or open sockets persist after context close:

1. Check if any `HttpClient`/`HttpServer` used Reactor Netty global resources outside the factory.
2. Check if third-party libraries created their own `LoopResources`/`ConnectionProvider`.
3. Verify the resource factory bean actually belonged to the closing Spring `ApplicationContext`.
4. Check if multiple `ApplicationContext`s are active, sharing global resources or separate factories.
5. Check if a `Publisher` is still running, never completes, or was not cancelled properly.
6. Check shutdown quiet period/timeout and any application-created schedulers.
7. Use thread dumps, metrics, and socket listings to distinguish event-loop threads from other scheduler pools.

Do not conclude "ReactorResourceFactory is leaking" solely from a thread name. Trace the owning object and verify its actual lifecycle.

### 14.2. Signs of Mixing Global and Dedicated Resources

Suppose an app configures `setUseGlobalResources(false)`, yet an SDK independently calls `HttpClient.create()`. That SDK continues using JVM-global Reactor Netty `HttpResources` while the app's own `WebClient`s use the dedicated factory. Looking only at the resource bean might mislead you into thinking every HTTP call is governed by it.

Inspect actual connectors, `HttpClient` configs, provider/pool counts in metrics, and library lifecycles. When you need to share resources with an SDK, check whether it allows injecting an `HttpClient`/`ConnectionProvider`/`LoopResources`; if not, document that it manages independent resources with its own cleanup policy.

## 15. Common Mistakes When Customizing ReactorResourceFactory

### Mistake 1: Creating a ConnectionProvider per request

~~~java
// Do not place this inside a controller method per request:
ConnectionProvider provider =
        ConnectionProvider.create("one-off");
~~~

A provider is a lifecycle-managed resource. Creating and abandoning one without disposal leaks pools and sockets over time. Use a shared Spring/factory-managed provider, or a dedicated provider with clear ownership if isolation is needed.

### Mistake 2: Assuming a factory bean automatically governs every HttpClient

Only components wired to the factory use its dedicated resource set as designed. `HttpClient.create()` elsewhere can still use globals; SDKs may build completely separate pools. Verify bean wiring and adapters for both server and client.

### Mistake 3: Calling dispose from a request handler

A single request does not own shared provider/loop resources. Disposing there can break all other in-flight requests. Leave closing to Spring lifecycle / the resource owner.

### Mistake 4: Using global resources across multiple contexts without shutdown coordination

One context stopping can dispose JVM-global resources while another context still needs them. In multi-context setups, design a unified shared owner or per-context dedicated factories, and test closing individual contexts.

### Mistake 5: Raising maxConnections infinitely when an upstream is slow

A larger pool does not make an upstream faster. It can increase sockets, memory, and pressure on the dependency. Measure latency, pending acquires, retries, timeouts, and concurrency; consider bulkheads or upstream rate limits.

### Mistake 6: Creating a separate event-loop set for every WebClient

This is usually redundant and increases thread count significantly. Sharing `LoopResources` is a sensible default for non-blocking I/O; isolate event loops only with clear evidence and benchmarks.

### Mistake 7: Running blocking code on the event loop

Calling JDBC or `Thread.sleep` directly inside `flatMap`/`map` can block Reactor Netty threads. Offload blocking work safely or switch to reactive drivers; do not expect a resource factory to fix blocking code.

### Mistake 8: Confusing pool acquire timeout with response timeout

`pendingAcquireTimeout` protects waiting for the pool to issue a connection; `responseTimeout` protects the HTTP response stage per Reactor Netty; add an overall deadline if business logic requires an end-to-end bound.

### Mistake 9: Treating application shutdown as immediate socket closure

In-flight requests, quiet periods, proxy connections, and shutdown phases all take time. Measure real behavior. Do not insert fixed sleeps or hasty dispose calls to "guarantee cleanup" without understanding active requests.

### Mistake 10: Assuming WebFlux always uses Reactor Netty server

WebFlux can run on other supported runtimes. `ReactorResourceFactory` is specific to Reactor Netty; when the server is not Reactor Netty, it can still serve Reactor Netty-based `WebClient`s, but it does not configure other server engines.

### Mistake 11: Calling WebClient.builder() manually everywhere

This can bypass Boot customizers and shared settings. Prefer injecting `WebClient.Builder`, declaring purpose-built client beans, and standardizing timeouts, codecs, and observability.

### Mistake 12: Calling .block() in a reactive endpoint

`.block()` blocks the calling thread and can fail on event loops. Return `Mono`/`Flux` for Spring WebFlux to drive; never force synchronous conversion unless inside a dedicated blocking boundary.

## 16. Pre-Production Design Checklist

- [ ] Confirm the app runs reactive WebFlux and the HTTP runtime is actually Reactor Netty if sharing server resources.
- [ ] Inventory all outbound `WebClient`/`HttpClient` instances and SDKs using Reactor Netty.
- [ ] Choose ownership: global `HttpResources` or `ApplicationContext`-dedicated `ReactorResourceFactory`.
- [ ] If `useGlobalResources=false`, wire every client intended to share resources to that factory.
- [ ] Ensure no extra unintended `ReactorResourceFactory` beans are declared.
- [ ] Keep event loops, connection providers, and individual TCP connections conceptually distinct.
- [ ] Never create or dispose providers/loops per request.
- [ ] Set connection limits, pending-acquire timeouts, and HTTP client response timeouts based on SLOs.
- [ ] Verify connect/TLS/overall deadlines and retry policies independently of connection pooling.
- [ ] Avoid blocking on event-loop threads; enforce separate limits on blocking work.
- [ ] If running multiple `ApplicationContext`s in one JVM, test independent shutdown behavior.
- [ ] Test context close/restart and load tests to catch thread or socket leaks.
- [ ] Monitor active/idle/pending HTTP connections, event-loop latency, CPU, memory, GC, and timeouts.
- [ ] Verify body read/write, cancellation, and connection release on error paths.
- [ ] Align readiness probes, graceful shutdown, and termination deadlines in containers.
- [ ] Never expose metrics with unbounded tag values or sensitive data.

## 17. Self-Check Questions

**Question 1: Is ReactorResourceFactory a WebClient?**  
No. It manages Reactor Netty resources that `WebClient`/`HttpClient` can use; `WebClient` is the API that sends HTTP requests.

**Question 2: Does useGlobalResources=true mean sharing a pool across all pods?**  
No. Global resources are scoped to a single JVM. Separate pods/JVMs have separate thread and socket pools.

**Question 3: Do two WebClients sharing a factory necessarily share a single TCP connection?**  
Not necessarily. They share pool management and event loops; sockets are reused when remote endpoint, protocol, and policy allow.

**Question 4: Why can many Netty threads still appear after creating a dedicated factory?**  
Another library may be using global resources or creating its own `LoopResources`, or multiple contexts may be running. Inspect actual resource ownership, not just bean counts.

**Question 5: Why shouldn't you call dispose after every HTTP request?**  
Because `ConnectionProvider` and `LoopResources` are normally shared across many requests and `WebClient`s; disposing once can break other in-flight requests.

**Question 6: Does setting maxConnections=80 mean at most 80 HTTP requests across the whole app?**  
No. The limit applies to pools managed by the provider per Reactor Netty semantics; inbound server requests, multiple remote endpoints, and HTTP protocols can have different concurrency levels.

**Question 7: Does testing a WebFlux controller with WebTestClient prove resource cleanup?**  
No. A controller slice might not start a real HTTP server; use integration tests covering the `ApplicationContext`, client/server resources, and shutdown to verify cleanup.

**Question 8: Which is better for a small microservice—global or dedicated?**  
Usually the global default suits a standalone JVM: it is simple and reuses resources effectively. Choose dedicated when clear isolation, ownership, or multi-context lifecycles require it.

## 18. Summary

In a Spring WebFlux application using Reactor Netty, **`ReactorResourceFactory` is the lifecycle and sharing coordinator for HTTP resources**—not an HTTP client or controller. It ties together two core resources: **`LoopResources`** for non-blocking event-loop I/O and **`ConnectionProvider`** for HTTP client connection pooling.

By default, Reactor Netty uses **JVM-global `HttpResources`**, which is typically the simplest way to share fixed resources. When you need an independent `ApplicationContext` lifecycle, set `useGlobalResources=false` and supply Spring-managed dedicated resources. The critical condition is ensuring actual `WebClient`/`HttpClient` instances wire into that factory; otherwise, the application can unknowingly mix global and dedicated resources.

Sound design goes beyond bumping pool or event-loop sizes. Establish clear ownership, bounded connections and timeouts, non-blocking code, `ApplicationContext` close tests, and metrics under load. When you know **who creates — who uses — who closes**, you can customize WebFlux and Reactor Netty while keeping the application stable from startup through graceful shutdown.

## 19. Official Documentation for Further Reading

- Spring Framework — WebClient / Reactor Netty resources: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html
- Spring Framework API — ReactorResourceFactory: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/reactive/ReactorResourceFactory.html
- Spring Framework API — ReactorClientHttpConnector: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/reactive/ReactorClientHttpConnector.html
- Spring Boot — Reactive Web Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Boot — Graceful Shutdown: https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html
- Reactor Netty — HTTP Client: https://projectreactor.io/docs/netty/release/reference/http-client.html
- Reactor Netty — ConnectionProvider API: https://projectreactor.io/docs/netty/release/api/reactor/netty/resources/ConnectionProvider.html