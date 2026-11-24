# Disposing Custom Network Resources and Avoiding Per-Request Pools in Spring WebClient

## 1. The Problem: HTTP Clients Own Long-Lived Resources

A WebClient request looks very short in code:

~~~java
webClient.get()
    .uri("/users/42")
    .retrieve()
    .bodyToMono(User.class);
~~~

Underneath, however, a reactive HTTP client can use many resources that outlive a single request:

- **Connection pool:** holds and reuses TCP connections to remote hosts.
- **Event loop:** threads handling non-blocking I/O.
- **DNS resolver:** performs hostname resolution.
- **TLS resources:** supports handshakes and connection encryption.
- **Executor or scheduler:** runs background HTTP client tasks.
- **Buffer pool:** manages memory regions for reading/writing bytes.
- **HTTP client/connector:** configures and coordinates these resources.

These resources are created to serve many requests. A connection is returned to the pool after the response is consumed and can be used by the next request.

A common design mistake is creating a new \`ConnectionProvider\`, \`HttpClient\`, or \`WebClient\` on every service call and forgetting to close resources. The result can be too many pools, event loops, sockets, and threads; connections are not reused; and the application suffers increased memory, file descriptors, and handshake times.

**Principle:** create the HTTP client and pool at application scope or downstream-service scope, reuse them across many requests, and let Spring manage the resource lifecycle. Only create a dedicated pool when there is a clear isolation or custom configuration reason.

## 2. Distinguishing WebClient, ClientHttpConnector, HttpClient, and ConnectionProvider

These classes have different responsibilities:

| Component | Role |
| --- | --- |
| \`WebClient\` | Application-level API to build and execute HTTP requests |
| \`WebClient.Builder\` | Configures WebClient before building |
| \`ClientHttpConnector\` | Bridge between WebClient and a concrete HTTP client library |
| \`ReactorClientHttpConnector\` | Connector integrating Reactor Netty with WebClient |
| Reactor Netty \`HttpClient\` | Configures requests, TLS, timeouts, protocols, and client behavior |
| \`ConnectionProvider\` | Manages pools, acquisition, and connection reuse |
| \`LoopResources\` | Manages Reactor Netty's event-loop resources |
| \`ReactorResourceFactory\` | Manages LoopResources and ConnectionProvider along the Spring ApplicationContext lifecycle |

Model:

~~~text
Service / Controller
        |
        v
Reusable WebClient
        |
        v
ClientHttpConnector
        |
        v
ReactorClientHttpConnector
        |
        v
Reactor Netty HttpClient
        |
        +-------------------------+
        |                         |
        v                         v
ConnectionProvider          LoopResources
        |                         |
        v                         v
Connection pool             Event-loop threads
        |                         |
        +------------+------------+
                     |
                     v
              Network / Remote API
~~~

\`WebClient\` is not synonymous with a single TCP connection. One WebClient can use a pool containing many connections to one or more remote hosts. Multiple WebClients can also share a connector or resource factory.

## 3. How Is the Pool Reused?

When using Reactor Netty, \`HttpClient.create()\` participates by default in global resources in \`HttpResources\`. These resources include shared event loops and connection pools.

Typical flow:

1. A request needs to connect to a remote host.
2. \`ConnectionProvider\` looks for an idle connection in that host's pool.
3. If a suitable connection exists, the request reuses it.
4. If none exists and the pool has capacity, the client opens a new connection.
5. If the pool has reached its limit, the request can wait in the pending-acquire queue.
6. Once the response is completely read or properly released, the connection can be returned to the pool.
7. The next request to the same host can reuse that connection.

Pools are organized per remote host, typically based on hostname and port. A pool can hold multiple connections; connections are not closed immediately after each successful response.

Reuse reduces TCP connection establishment, TLS handshakes, socket creation/teardown overhead, open file descriptor counts, and pressure on event loops.

### Does a New WebClient Always Mean a New Pool?

Not necessarily. If multiple WebClients use Reactor Netty global resources, they can share the global pool. However, creating a WebClient on every request still increases allocations and easily leads to misconfigured resources when the application adds custom connectors or providers.

The most severe problem is **creating a new ConnectionProvider or LoopResources on every request**. Each provider can create its own pool, preventing requests from sharing connections with one another.

## 4. Using the Spring Boot-Provided WebClient.Builder

In Spring Boot WebFlux, inject the auto-configured \`WebClient.Builder\`:

~~~java
@Service
public class UserClient {

    private final WebClient webClient;

    public UserClient(WebClient.Builder builder) {
        this.webClient = builder
            .baseUrl("https://api.example.com")
            .build();
    }

    public Mono<User> findUser(String id) {
        return webClient.get()
            .uri("/users/{id}", id)
            .retrieve()
            .bodyToMono(User.class);
    }
}
~~~

Spring Boot provides a pre-configured builder to share HTTP resources and codec setup in a way compatible with the server. When using Reactor Netty for both server and client, resources can be shared.

Recommended organization:

- Build WebClient once in a constructor or bean configuration.
- Keep WebClient in a singleton service.
- Each method only creates a request specification and executes the request.
- Use the same WebClient for multiple requests to the same downstream.
- If multiple clients are needed, build multiple WebClients from the builder while preserving resource sharing where possible.

Once built, \`WebClient\` is immutable and suitable for reuse. \`WebClient.Builder\` holds mutable configuration state; do not mutate the same builder concurrently across requests. If configuration variants are needed, use \`builder.clone()\` or configure separately at startup.

### A Shared WebClient Bean

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    WebClient partnerWebClient(WebClient.Builder builder) {
        return builder
            .baseUrl("https://api.example.com")
            .build();
    }
}
~~~

The service receives that bean via constructor:

~~~java
@Service
public class PartnerService {

    private final WebClient partnerWebClient;

    public PartnerService(WebClient partnerWebClient) {
        this.partnerWebClient = partnerWebClient;
    }

    public Mono<String> status() {
        return partnerWebClient.get()
            .uri("/health")
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

There is no need to create a pool for every call to \`status()\`.

## 5. Anti-Pattern: Creating a New Pool per Request

The example below illustrates the design mistake:

~~~java
public Mono<String> callPartner() {
    ConnectionProvider provider =
        ConnectionProvider.builder("per-request").build();

    HttpClient httpClient = HttpClient.create(provider);

    WebClient client = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .baseUrl("https://api.example.com")
        .build();

    return client.get()
        .uri("/health")
        .retrieve()
        .bodyToMono(String.class);
}
~~~

Each time the method is called:

- A new \`ConnectionProvider\` is created.
- A new pool is created instead of reusing an existing pool.
- A new WebClient and connector are created.
- If the provider is not disposed, resources may remain alive longer than intended.
- If the provider is disposed after each request, the pool never gets a chance to reuse connections across requests.

Even if you add \`doFinally(signal -> provider.dispose())\`, creating and destroying a pool per request still causes overhead and defeats the benefits of pooling.

### Distinguishing a New WebClient from a New Pool

Creating a new WebClient does not automatically create a new pool if it shares global resources. Still, repeatedly creating WebClient instances is unnecessary allocation and makes code harder to manage.

Creating a new \`ConnectionProvider\` directly creates a new resource pool. Creating a new \`LoopResources\` can also spawn additional event-loop threads.

Create these resources at startup or when configuring a downstream, then reuse them.

## 6. When to Use Global Reactor Netty Resources?

This is the appropriate default for most applications:

~~~java
HttpClient httpClient = HttpClient.create();

WebClient webClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .build();
~~~

\`HttpClient.create()\` participates in global Reactor Netty resources, including event loops and connection pools. This is the mode recommended by Spring Framework because shared resources keep event-loop concurrency stable.

Advantages:

- No need to manage a provider manually for each WebClient.
- Multiple clients can share global resources.
- Connection pools are reused.
- No need to close global resources after every request.
- Suits applications whose lifetime matches the process lifetime.

Global resources usually live until the process exits. If an application can start/stop multiple times within the same JVM, such as embedded environments or Spring containers created and closed repeatedly, lifecycle integration is needed so resources close when the ApplicationContext ends.

**Do not call \`HttpResources.disposeLoopsAndConnections()\` arbitrarily.** That operation can shut down resources still in use by other Reactor Netty clients/servers.

## 7. ReactorResourceFactory Manages Lifecycle in Spring

\`ReactorResourceFactory\` is a Spring-managed resource factory for Reactor Netty. It manages:

- \`LoopResources\`: event-loop threads.
- \`ConnectionProvider\`: connection pool.
- Shutdown wait durations.
- Starting and stopping resources along with \`ApplicationContext\`.

This class implements \`SmartLifecycle\`, \`InitializingBean\`, and \`DisposableBean\`. Therefore, when declared as a Spring bean, resource lifecycles can be managed alongside the application.

### Managing Global Resources

If you want to use global resources while tying shutdown to ApplicationContext:

~~~java
@Configuration(proxyBeanMethods = false)
public class ReactorResourceConfiguration {

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        return new ReactorResourceFactory();
    }
}
~~~

By default, \`useGlobalResources\` is \`true\`. The factory manages initializing and stopping global Reactor Netty resources according to Spring's lifecycle.

In a typical Spring Boot WebFlux application, Boot already configures HTTP resources and `WebClient.Builder` for sharing. Check existing configuration before registering another factory yourself.

### Managing Independent Resources

If you need a dedicated pool or want to separate a client's lifecycle from global resources:

~~~java
@Bean
ReactorResourceFactory reactorResourceFactory() {
    ReactorResourceFactory factory = new ReactorResourceFactory();
    factory.setUseGlobalResources(false);
    return factory;
}
~~~

When \`useGlobalResources=false\`, the factory manages its own independent resources. The application must ensure all clients/servers meant to use this resource set are configured consistently.

Do not create a new factory per request. A factory is an application-level bean or an infrastructure unit with a clear lifecycle.

## 8. Configuring a Custom ConnectionProvider

When you need control over connection counts, wait times, or connection ages, you can create a custom provider:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("partner-api")
        .maxConnections(40)
        .pendingAcquireMaxCount(80)
        .pendingAcquireTimeout(Duration.ofSeconds(5))
        .maxIdleTime(Duration.ofSeconds(20))
        .maxLifeTime(Duration.ofMinutes(5))
        .evictInBackground(Duration.ofSeconds(60))
        .build();
~~~

Configuration properties:

| Property | Meaning |
| --- | --- |
| \`maxConnections\` | Maximum connections in a pool |
| \`pendingAcquireMaxCount\` | Maximum requests allowed to wait when the pool cannot grant a connection yet |
| \`pendingAcquireTimeout\` | Maximum wait time to borrow a connection from the pool |
| \`maxIdleTime\` | Duration a connection is allowed to remain idle |
| \`maxLifeTime\` | Maximum lifetime of a connection |
| \`evictInBackground\` | Interval for checking and evicting connections no longer eligible for use |

### maxConnections

Limits active connections in the pool. The value should balance expected concurrency, downstream connection limits, latency, the number of hosts the application calls, and process socket/file descriptor resources.

Setting it too low can cause many pending requests and timeouts. Setting it too high can overload the downstream or create unnecessary connections.

### pendingAcquireMaxCount and pendingAcquireTimeout

When the pool is full, new requests may wait for a connection to be returned.

- \`pendingAcquireMaxCount\` bounds the queue.
- \`pendingAcquireTimeout\` bounds the wait time.

If the queue is unbounded, sudden traffic spikes can cause many requests to wait concurrently and retain significant state in memory. Set limits aligned with the SLA.

### maxIdleTime and maxLifeTime

- \`maxIdleTime\` limits how long a connection sits unused.
- \`maxLifeTime\` limits the total age of a connection, even when still being reused.

When setting \`maxIdleTime\`, choose a value less than or equal to the target server's idle timeout. This reduces the chance of the client borrowing a connection the server has already actively closed.

### evictInBackground

The pool can scan connections periodically to remove those no longer suitable. The eviction interval should balance cleanup responsiveness with scanning cost.

Do not arbitrarily set overly short timeouts because connections may be closed and reopened constantly, causing extra TCP/TLS handshakes.

## 9. Passing a Custom ConnectionProvider into ReactorResourceFactory

If the application needs a custom pool, let the factory manage the provider:

~~~java
@Bean
ReactorResourceFactory reactorResourceFactory() {
    ReactorResourceFactory factory = new ReactorResourceFactory();

    factory.setUseGlobalResources(false);

    factory.setConnectionProviderSupplier(() ->
        ConnectionProvider.builder("partner-api")
            .maxConnections(40)
            .pendingAcquireMaxCount(80)
            .pendingAcquireTimeout(Duration.ofSeconds(5))
            .maxIdleTime(Duration.ofSeconds(20))
            .maxLifeTime(Duration.ofMinutes(5))
            .evictInBackground(Duration.ofSeconds(60))
            .build()
    );

    factory.setShutdownQuietPeriod(Duration.ofSeconds(2));
    factory.setShutdownTimeout(Duration.ofSeconds(15));

    return factory;
}
~~~

Key points:

- \`setUseGlobalResources(false)\` must be set if you want the factory to manage independent resources.
- \`setConnectionProviderSupplier\` creates the provider within the factory's lifecycle.
- The supplier only creates the provider when resources need initialization, not for each HTTP request.
- Spring invokes lifecycle stop when the ApplicationContext closes.
- Do not manually call \`dispose()\` or \`disposeLater()\` on a provider owned by the factory.

According to Spring Framework 6.2 Javadoc, a custom `ConnectionProvider` supplier is ignored when the factory still uses global resources or when a provider has already been set directly.

## 10. Connecting a Custom Resource Factory to WebClient

Spring Framework supports a \`ReactorClientHttpConnector\` constructor accepting a \`ReactorResourceFactory\` and a function to customize \`HttpClient\`.

~~~java
@Bean
WebClient partnerWebClient(
        WebClient.Builder builder,
        ReactorResourceFactory reactorResourceFactory) {

    Function<HttpClient, HttpClient> mapper = httpClient ->
        httpClient
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
            .responseTimeout(Duration.ofSeconds(10));

    ClientHttpConnector connector =
        new ReactorClientHttpConnector(
            reactorResourceFactory,
            mapper
        );

    return builder
        .baseUrl("https://api.example.com")
        .clientConnector(connector)
        .build();
}
~~~

Here:

- The factory owns the pool and event-loop resources.
- The mapper adds timeouts to Reactor Netty `HttpClient`.
- The connector links `HttpClient` to `WebClient`.
- `WebClient` is built once as a bean.
- Subsequent requests reuse the same client and the same pool.

If using Spring Boot, continue injecting \`WebClient.Builder\` to preserve codecs and Boot configurations. When providing a custom \`ReactorResourceFactory\`, understand that the factory can affect both the application's Reactor Netty server and client.

## 11. Complete Java 17+ Example with Spring Boot WebFlux

The example builds a WebClient calling JSONPlaceholder:

- Uses Spring Boot 3.5.0 and Java 17+.
- Uses a \`ReactorResourceFactory\` bean.
- Uses a custom `ConnectionProvider` capped at 40 connections.
- Uses a singleton WebClient.
- Requests to the downstream reuse the pool.
- Spring manages shutdown of the resource factory.

Structure:

~~~text
webclient-resource-lifecycle/
├── pom.xml
└── src/main/
    ├── java/com/example/resources/
    │   ├── ResourceLifecycleApplication.java
    │   ├── HttpClientConfiguration.java
    │   ├── PartnerService.java
    │   └── PartnerController.java
    └── resources/
        └── application.properties
~~~

File \`pom.xml\`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webclient-resource-lifecycle</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
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

File \`src/main/java/com/example/resources/ResourceLifecycleApplication.java\`:

~~~java
package com.example.resources;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceLifecycleApplication.class, args);
    }
}
~~~

File \`src/main/java/com/example/resources/HttpClientConfiguration.java\`:

~~~java
package com.example.resources;

import java.time.Duration;
import java.util.function.Function;

import io.netty.channel.ChannelOption;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.ReactorClientHttpConnector;
import org.springframework.http.client.ReactorResourceFactory;
import org.springframework.http.client.reactive.ClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
public class HttpClientConfiguration {

    @Bean
    ReactorResourceFactory reactorResourceFactory() {
        ReactorResourceFactory factory = new ReactorResourceFactory();

        factory.setUseGlobalResources(false);

        factory.setConnectionProviderSupplier(() ->
            ConnectionProvider.builder("partner-api")
                .maxConnections(40)
                .pendingAcquireMaxCount(80)
                .pendingAcquireTimeout(Duration.ofSeconds(5))
                .maxIdleTime(Duration.ofSeconds(20))
                .maxLifeTime(Duration.ofMinutes(5))
                .evictInBackground(Duration.ofSeconds(60))
                .build()
        );

        factory.setShutdownQuietPeriod(Duration.ofSeconds(2));
        factory.setShutdownTimeout(Duration.ofSeconds(15));

        return factory;
    }

    @Bean
    WebClient partnerWebClient(
            WebClient.Builder builder,
            ReactorResourceFactory reactorResourceFactory) {

        Function<HttpClient, HttpClient> mapper = httpClient ->
            httpClient
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
                .responseTimeout(Duration.ofSeconds(10));

        ClientHttpConnector connector =
            new ReactorClientHttpConnector(
                reactorResourceFactory,
                mapper
            );

        return builder
            .baseUrl("https://jsonplaceholder.typicode.com")
            .clientConnector(connector)
            .build();
    }
}
~~~

File \`src/main/java/com/example/resources/PartnerService.java\`:

~~~java
package com.example.resources;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class PartnerService {

    public record PartnerUser(
        long id,
        String name,
        String username,
        String email
    ) {}

    private final WebClient partnerWebClient;

    public PartnerService(WebClient partnerWebClient) {
        this.partnerWebClient = partnerWebClient;
    }

    public Mono<PartnerUser> findUser(long id) {
        return partnerWebClient.get()
            .uri("/users/{id}", id)
            .retrieve()
            .bodyToMono(PartnerUser.class);
    }
}
~~~

File \`src/main/java/com/example/resources/PartnerController.java\`:

~~~java
package com.example.resources;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/partner")
public class PartnerController {

    private final PartnerService partnerService;

    public PartnerController(PartnerService partnerService) {
        this.partnerService = partnerService;
    }

    @GetMapping("/users/{id}")
    public Mono<PartnerService.PartnerUser> getUser(
            @PathVariable long id) {
        return partnerService.findUser(id);
    }
}
~~~

File \`src/main/resources/application.properties\`:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Run from the project directory with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Call the endpoint:

~~~bash
curl -i http://localhost:8080/api/partner/users/1
~~~

Expected response format:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
~~~

~~~json
{
  "id": 1,
  "name": "Leanne Graham",
  "username": "Bret",
  "email": "Sincere@april.biz"
}
~~~

Calling the endpoint multiple times continues using the same WebClient bean and the same `ConnectionProvider`. Specific connections can be reused if still valid, not closed by the server, and the previous response was completely consumed.

This example connects to an external demo service; running it requires network access and an available JSONPlaceholder service.

## 12. Configuring Timeouts at the Right Layer

No single timeout suits every scenario. Reactor Netty has timeouts at different stages:

| Timeout | Controls | Commonly Used API |
| --- | --- | --- |
| Pool acquire timeout | Wait time to borrow a connection from the pool | \`pendingAcquireTimeout\` |
| Connect timeout | Time to establish a TCP connection | \`CONNECT_TIMEOUT_MILLIS\` |
| Response timeout | Wait interval between response read operations per Reactor Netty configuration | \`HttpClient.responseTimeout\` |
| Read timeout | Duration with no read data per configured handler | \`ReadTimeoutHandler\` |
| Write timeout | Duration with no write activity per configured handler | \`WriteTimeoutHandler\` |
| Reactive deadline | Time limit of a publisher/operation at the Reactor layer | \`Mono.timeout\` or \`Flux.timeout\` |

### Connect Timeout

~~~java
HttpClient client = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000);
~~~

If the TCP connection is not established within 5 seconds, the connect operation fails.

### Response Timeout

~~~java
HttpClient client = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(10));
~~~

This timeout belongs to the HTTP client layer. For long response streams, choose a value appropriate for the wait time between data reads; do not treat it as the maximum lifetime for every stream.

### Read/Write Timeout

~~~java
HttpClient client = HttpClient.create()
    .doOnConnected(connection -> connection
        .addHandlerLast(new ReadTimeoutHandler(10))
        .addHandlerLast(new WriteTimeoutHandler(10)));
~~~

These handlers operate at the connection scope and can affect long-lived streams. Do not set short timeouts if the API allows response bodies or uploads to sit idle for long periods.

### Reactive Timeout

~~~java
return partnerWebClient.get()
    .uri("/users/{id}", id)
    .retrieve()
    .bodyToMono(PartnerService.PartnerUser.class)
    .timeout(Duration.ofSeconds(15));
~~~

\`Mono.timeout\` limits the duration of the publisher it wraps. It does not replace configuring explicit pool acquire, TCP connect, or response I/O timeouts.

## 13. Connection Pooling Does Not Replace Consuming the Response Body

A connection can only be reused after the response has been properly handled. If the application receives a \`ClientResponse\` and ignores the body without consuming or releasing it, connections/buffers may be held longer than expected.

Standard usage with \`retrieve()\`:

~~~java
Mono<User> user = webClient.get()
    .uri("/users/42")
    .retrieve()
    .bodyToMono(User.class);
~~~

When the endpoint has no response body:

~~~java
Mono<Void> result = webClient.delete()
    .uri("/users/42")
    .retrieve()
    .toBodilessEntity()
    .then();
~~~

When using \`exchangeToMono()\`, read the body or release it explicitly:

~~~java
Mono<Void> result = webClient.get()
    .uri("/health")
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.releaseBody();
        }
        return response.createError();
    });
~~~

Do not hold onto the response body or \`DataBuffer\` longer than necessary. If the client cancels mid-response read, the connection may be closed instead of returned to the pool; that behavior is necessary to protect connection integrity.

## 14. When to Dispose ConnectionProvider?

There are two different resource ownership scenarios.

### Shared Provider Managed by Reactor Netty

If using \`HttpClient.create()\` with global resources, do not dispose the provider after each request. Resources may be shared by multiple clients/servers.

Only the component owning the lifecycle of global resources should stop them, typically when the process exits or when the Spring-managed resource factory closes the ApplicationContext.

### Custom Provider Created by the Application

\`ConnectionProvider\` provides these APIs:

- \`dispose()\`: initiates fire-and-forget disposal.
- \`disposeLater()\`: returns \`Mono<Void>\` to observe the disposal process; must be subscribed to trigger.
- \`disposeWhen(remoteAddress)\`: requests pool disposal for a specific remote address if supported by the implementation.

Standalone example, outside any controller/event loop:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("standalone-client")
        .maxConnections(20)
        .build();

HttpClient httpClient = HttpClient.create(provider);

// Perform the necessary requests here.

provider.disposeLater().block();
~~~

\`block()\` here only illustrates a standalone program waiting for shutdown on a regular coordinating thread. Never call \`block()\` on an event loop or inside a reactive controller.

In a Spring application, prefer letting \`ReactorResourceFactory\` manage the provider. Do not both let the factory own the provider and manually dispose it in another bean.

## 15. Graceful Shutdown and ApplicationContext Lifecycle

When the application stops, in-flight requests need time to complete before network resources are closed.

Spring Boot supports graceful shutdown for embedded web servers. You can configure the wait timeout per lifecycle phase:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

In `ReactorResourceFactory`, there are two separate settings:

- \`setShutdownQuietPeriod(Duration)\`: quiet period before stopping `LoopResources`; if a new task arrives during this window, the quiet period resets.
- \`setShutdownTimeout(Duration)\`: maximum time to wait for resource disposal to complete.

Example:

~~~java
factory.setShutdownQuietPeriod(Duration.ofSeconds(2));
factory.setShutdownTimeout(Duration.ofSeconds(15));
~~~

These are two related yet distinct layers:

- Server graceful shutdown gives in-flight inbound requests time to finish.
- `ReactorResourceFactory` shutdown stops client pools and event-loop resources managed by the factory.

Do not close the pool immediately at the start of shutdown if outbound requests are still using it. Let Spring's lifecycle coordinate the shutdown order of components.

After a resource factory stops/restarts, the factory may create new `LoopResources` and `ConnectionProvider` instances. Do not retain a reference to an old provider and keep using it after a lifecycle restart.

## 16. When Using a Connector Other Than Reactor Netty

WebClient can use multiple HTTP client implementations. Each type has its own resource lifecycle:

| Connector | Main Resources | Management Approach |
| --- | --- | --- |
| Reactor Netty | ConnectionProvider, LoopResources | Global HttpResources or ReactorResourceFactory |
| Jetty Reactive HttpClient | Executor, ByteBufferPool, Scheduler, and HttpClient | JettyResourceFactory or start/stop lifecycle |
| Apache HttpComponents | CloseableHttpAsyncClient and connection manager | Start/close per client lifecycle |
| JDK HttpClient | HttpClient and custom executor | Manage the executor if supplied by the application |

### Jetty

Jetty \`HttpClient\` can create its own `Executor`, `ByteBufferPool`, and `Scheduler`. If multiple clients need to share resources or close them when the ApplicationContext ends, use \`JettyResourceFactory\` with \`JettyClientHttpConnector\`.

### Apache HttpComponents

When creating \`CloseableHttpAsyncClient\` manually, start and close it according to the application lifecycle. Never create a new async client/connection manager for every request.

### JDK HttpClient

If supplying a custom `Executor` to JDK HttpClient, manage that executor as an application resource. Do not create a new executor or thread pool on every WebClient call.

**General rule:** understand who creates the resource, who shares the resource, who owns the resource, and who is responsible for closing the resource.

## 17. Monitoring the Connection Pool

When Micrometer metrics are enabled for a Reactor Netty pool, you can monitor metrics such as:

| Metric | Meaning |
| --- | --- |
| \`reactor.netty.connection.provider.total.connections\` | Total active and idle connections |
| \`reactor.netty.connection.provider.active.connections\` | Number of connections currently in use |
| \`reactor.netty.connection.provider.idle.connections\` | Number of idle connections in the pool |
| \`reactor.netty.connection.provider.pending.connections\` | Number of requests waiting for a connection |
| \`reactor.netty.connection.provider.max.connections\` | Connection limit |
| \`reactor.netty.connection.provider.pending.connections.time\` | Wait time to acquire a connection |

You can enable metrics on the provider when the application has Micrometer:

~~~java
ConnectionProvider provider =
    ConnectionProvider.builder("partner-api")
        .maxConnections(40)
        .metrics(true)
        .build();
~~~

With Spring Boot, you can add \`spring-boot-starter-actuator\` to integrate Micrometer and export metrics to your chosen monitoring system.

Signs to watch:

- Pending connections rising steadily: the pool may be too small or the downstream is responding slowly.
- Active connections frequently hitting max: check concurrency and response body hold times.
- High idle connections not decreasing: review idle eviction and pool demand.
- Pool acquire timeouts rising: connections may not be released, downstream is too slow, or pool is undersized.
- Total connections growing abnormally with request count: check whether multiple providers/pools are being created.

Do not merely increase `maxConnections` when you see a pending queue. First determine whether the bottleneck is downstream, response consumption, concurrency, or pool configuration.

## 18. Common Mistakes

1. **Creating ConnectionProvider in a controller:** every request can create a separate pool. Create the provider in application configuration and reuse it.
2. **Not disposing custom providers:** pools, connections, and resources can remain alive after no longer needed. Let Spring manage them via `ReactorResourceFactory` or dispose during lifecycle shutdown.
3. **Disposing the provider after every request:** destroys pooling benefits and causes constant connection/TLS handshakes.
4. **Calling global `HttpResources.disposeLoopsAndConnections` while other clients still use it:** breaks other clients/servers sharing those resources.
5. **Confusing creating a new WebClient with creating a new pool:** a new WebClient can still use the global pool; a new provider/`LoopResources` creates a separate resource pool.
6. **Calling `WebClient.Builder.build()` in every method:** recreates objects/configuration and easily leads to separate connectors. Build a shared client bean or field.
7. **Using `ConnectionProvider.newConnection()` for normal traffic:** every acquisition opens a new connection without pooling.
8. **Setting `maxConnections` too high:** can overload the downstream or operating system.
9. **Not bounding `pendingAcquireMaxCount`:** queues can grow excessively when the downstream is slow.
10. **Setting `pendingAcquireTimeout` too long:** requests can wait long and tie up resources. Choose based on SLA.
11. **Setting `maxIdleTime` larger than the server's idle timeout:** the client can borrow connections already closed by the server.
12. **Setting `maxIdleTime` too low:** connections close/reopen constantly, increasing handshakes and latency.
13. **Not configuring `maxLifeTime` for long-lived connections:** some intermediary infrastructure may require periodic connection rotation.
14. **Confusing pool acquire timeout with connect timeout:** one waits for a pool slot, the other waits for the TCP handshake.
15. **Confusing `responseTimeout` with overall request deadline:** response timeout belongs to response I/O; use reactive timeout if a whole-operation deadline is needed.
16. **Setting `ReadTimeoutHandler` too short for streams:** valid responses or uploads can be closed while idle.
17. **Not consuming or releasing the response body:** connections may not be returned to the pool promptly.
18. **Creating a provider and connector without tying to Spring lifecycle:** the ApplicationContext closes while custom resources remain alive.
19. **Leaving the factory on global resources while expecting a custom provider supplier to apply:** the custom supplier is ignored while global resources remain enabled.
20. **Registering multiple `ReactorResourceFactory` beans unintentionally:** can create multiple resource sets and make it hard to tell which client/server uses which.
21. **Holding references to a provider across lifecycle restarts:** the factory can create new instances; old references are no longer valid.
22. **Calling `block()` to await disposal on an event loop:** can deadlock or stall I/O. Let reactive lifecycle manage shutdown.
23. **Retrying non-idempotent requests on connection errors:** the server may have already processed the request before the client received an error; require an idempotency key and clear retry policy.
24. **Checking only WebClient count without checking ConnectionProvider count:** multiple WebClients can share a pool; monitor metrics and where providers are created.
25. **Not testing shutdown:** resources may close too early or the process may fail to exit because threads/resources remain active.

## 19. Pre-Deployment Checklist

- Is WebClient built at application scope or recreated in every request?
- Is the builder injected from Spring Boot and used properly?
- Which connector is in use: Reactor Netty, Jetty, Apache, or JDK?
- Is the HTTP client using global resources or custom resources?
- Is a separate pool genuinely needed or is the default pool sufficient?
- If using a custom pool, where is `ConnectionProvider` created and who owns it?
- Does `ConnectionProvider` bound max connections and pending acquires?
- Are acquire, connect, response, and overall operation timeouts distinguished?
- Does `maxIdleTime` align with the downstream's idle timeout?
- Are response bodies consumed or released?
- Are active/idle/pending connection metrics available?
- Is there a shutdown lifecycle for custom providers, event loops, executors, and clients?
- Have you avoided disposing global resources while other clients still use them?
- Have concurrent load and shutdown while requests are in flight been tested?
- Is it confirmed that the number of pools does not grow with the number of requests?

## 20. Self-Check Questions

**1.** What is `ConnectionProvider` used for? Manages the connection pool and connection allocation/reuse for the HTTP client.

**2.** Is WebClient a single TCP connection? No. It is a client API; the connector and HTTP backend manage connection resources.

**3.** Why should you not create a `ConnectionProvider` per request? Because each provider can create a separate pool, losing reuse and increasing sockets/resources.

**4.** Which resources does Reactor Netty's `HttpClient.create()` use by default? Global Reactor Netty `HttpResources`, including event loops and connection pools.

**5.** What are the benefits of Spring Boot's `WebClient.Builder`? It is auto-configured to share HTTP resources and appropriate codec configurations.

**6.** What does `ReactorResourceFactory` manage? `LoopResources` and `ConnectionProvider` along the lifecycle of the Spring `ApplicationContext`.

**7.** What does `setUseGlobalResources(false)` mean? The factory manages independent resources instead of using global `HttpResources`.

**8.** When is `setConnectionProviderSupplier` needed? When the factory needs to create a custom `ConnectionProvider` within its lifecycle.

**9.** Should you call `provider.dispose()` after every request? No. Doing so breaks pooling and destroys reuse.

**10.** How does `pendingAcquireTimeout` differ from connect timeout? One waits for a connection in the pool; the other waits to establish a TCP connection.

**11.** How should `maxIdleTime` be chosen? Less than or equal to the target server's idle timeout to reduce stale connections.

**12.** When should `ConnectionProvider.newConnection()` be used? When you intentionally want each acquisition to open a new connection; unsuitable for normal traffic needing pooling.

**13.** When using a custom provider in Spring, what is a good management approach? Register the provider in `ReactorResourceFactory` and let Spring's lifecycle close resources.

**14.** Can global `HttpResources` be disposed inside any arbitrary service? No. That operation affects every client/server using global resources.

**15.** Why must response bodies be consumed or released? To free buffers and allow connections to be returned to the pool when appropriate.

**16.** Does `ReactorResourceFactory` create new resources after a lifecycle restart? Yes; references to old resources should not continue to be used.

**Key Takeaways:** WebClient and connection pools are long-lived resources. Use a singleton WebClient built from Spring Boot's builder; let Reactor Netty reuse global resources when appropriate. If a custom pool is needed, create `ConnectionProvider` at application scope and let `ReactorResourceFactory` manage its lifecycle. Do not create or dispose a pool per request. Configure pool limits, layer-appropriate timeouts, consume response bodies, and verify metrics/shutdown to prevent resource leaks.

**Official Documentation:**
- [Spring Framework 6.2 — WebClient Configuration and Resources](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html)
- [Spring Framework 6.2 — ReactorResourceFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/ReactorResourceFactory.html)
- [Spring Framework 6.2 — ReactorClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/reactive/ReactorClientHttpConnector.html)
- [Spring Boot 3.5 — Calling REST Services and WebClient Runtime](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html)
- [Spring Boot 3.5 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html)
- [Reactor Netty — HTTP Client, Connection Pool and Disposal](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [Reactor Netty — ConnectionProvider Javadoc](https://projectreactor.io/docs/netty/release/api/reactor/netty/resources/ConnectionProvider.html).