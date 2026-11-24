# Choosing the Reactor Netty, JDK, Jetty, or HttpComponents Connector

**Module:** Spring Framework – reactive  
**Parent topic:** Connections and Timeouts

## Learning Objectives

After this lesson, you will be able to:

1. Explain the role of `ClientHttpConnector` in WebClient and distinguish between the outbound HTTP client and the WebFlux server runtime.
2. Compare Reactor Netty, JDK HttpClient, Jetty, and Apache HttpComponents 5 in terms of dependencies, connection pooling, timeouts, HTTP/2, and configurability.
3. Choose a connector based on load, SLA, dependencies, and system operational requirements.
4. Configure a connector explicitly using `WebClient.Builder.clientConnector` while preserving Spring Boot customizers.
5. Configure connection pools, pending acquire limits, connect/response timeouts, TLS, proxies, and redirects.
6. Distinguish between pool acquire timeout, connect timeout, response read timeout, and overall deadline.
7. Manage the lifecycle of connection providers, HTTP clients, and executors.
8. Test WebClient through a real connector using MockWebServer and Reactor Test.

## 1. What Is ClientHttpConnector?

`WebClient` is Spring's reactive HTTP client API. It provides a fluent API to build requests, write bodies, receive responses, and convert data into `Mono` or `Flux`.

`ClientHttpConnector` is the transport-layer integration abstraction. It bridges Spring's request/response abstraction with a concrete HTTP client engine. As a result, business code using WebClient does not need to change when the underlying transport changes:

```text
Application
   |
   v
WebClient
   |
   v
ClientHttpConnector
   |
   +---- ReactorClientHttpConnector
   +---- JdkClientHttpConnector
   +---- JettyClientHttpConnector
   +---- HttpComponentsClientHttpConnector
   |
   v
HTTP / TLS / connection pool / socket
   |
   v
Remote server
```

The connector affects how connections are opened and reused, TLS, proxies, protocols, timeouts, and background resources. It does not change the business contract of the remote API.

Two sides must be distinguished:

- **WebClient connector:** sends outbound HTTP requests from the application.
- **WebFlux server runtime:** receives inbound requests from clients into the application.

An application can use Reactor Netty as its server while using JDK HttpClient for outbound WebClient calls. The two choices are independent; changing the WebClient connector does not automatically change the server serving endpoints.

## 2. Comparing the Four Connectors

| Connector | Engine | Strengths | Considerations |
| --- | --- | --- | --- |
| Reactor Netty | Reactor Netty / Netty | Native reactive support, detailed pool and transport tuning, natural integration with Reactor | Adds Netty dependencies; requires tuning pools and timeouts for load. |
| JDK | `java.net.http.HttpClient` | Built in since JDK 11, minimal dependencies, supports HTTP/2 and TLS | Fewer public APIs for pool control; some timeouts must be set at the request/publisher level. |
| Jetty | Jetty HttpClient via Jetty Reactive HttpClient | Fits systems already running Jetty, has its own connection configuration and lifecycle | Requires compatible Jetty dependencies and start/stop lifecycle management. |
| HttpComponents | Apache HttpComponents 5 Async Client | Rich connection manager and pooling, async HTTP engine | Requires Apache 5 async dependencies and lifecycle management. |

There is no single best connector for every application. Consider:

- Which engine does the system already use, and do you want to minimize new dependencies?
- Do you need pool control per host or per route?
- Are there requirements for HTTP/2, proxies, mutual TLS, or a custom truststore?
- Do you need separate timeouts for acquire, connect, read, and write?
- Do you want to reuse an existing client/connection manager or create a dedicated client?
- Which engine does the operations team already have metrics, tracing, and troubleshooting experience with?

## 3. Default Connector and Explicit Configuration

When using `spring-boot-starter-webflux`, Spring Boot provides a `WebClient.Builder` already configured by customizers. The standard WebFlux starter brings Reactor Netty onto the classpath, making it a common choice.

If no connector is specified, Spring Framework may select an implementation based on the HTTP client present on the classpath. Changing dependencies can change the selected transport. When the transport is an operational decision, configure it explicitly:

```java
WebClient client = WebClient.builder()
        .clientConnector(connector)
        .build();
```

In a Boot application, start from the injected builder and clone it when custom configuration is needed:

```java
@Bean
WebClient catalogWebClient(
        WebClient.Builder builder,
        ClientHttpConnector connector) {

    return builder.clone()
            .baseUrl("https://catalog.example.com")
            .clientConnector(connector)
            .build();
}
```

`clone()` creates a separate builder without modifying the shared prototype builder. This preserves Boot-registered customizers such as codecs, observation, or filters.

Do not call `WebClient.create()` arbitrarily in applications that require centralized configuration. A manually created builder can bypass application customizers, default headers, filters, codecs, and observation.

## 4. Reactor Netty

### 4.1. When to Choose It?

Reactor Netty is suitable when the application already uses Reactor/WebFlux and wants a native reactive HTTP client. It provides detailed configuration for connection pools, pending acquires, connect/response timeouts, channel handlers, proxies, TLS, redirects, HTTP/2, compression, and metrics.

It is a sensible default choice for many WebFlux applications, especially when outbound load tuning and pool observability are required.

### 4.2. Configuring the Connection Pool

```java
ConnectionProvider provider = ConnectionProvider.builder("catalog-pool")
        .maxConnections(100)
        .pendingAcquireMaxCount(500)
        .pendingAcquireTimeout(Duration.ofSeconds(10))
        .maxIdleTime(Duration.ofSeconds(30))
        .maxLifeTime(Duration.ofMinutes(5))
        .evictInBackground(Duration.ofSeconds(60))
        .build();
```

- `maxConnections` limits the number of connections in the pool.
- `pendingAcquireMaxCount` limits the number of requests waiting for a connection.
- `pendingAcquireTimeout` limits the time spent waiting for an available connection.
- `maxIdleTime` limits the idle age.
- `maxLifeTime` limits the maximum lifetime.
- `evictInBackground` enables periodic checks and eviction of connections that are no longer suitable.

A bounded pool caps the number of connections and the wait queue. When the pool runs out of connections and the queue is full or waits too long, requests can fail during acquire. Increasing the pool size does not make the remote server process faster; an overly large pool can overload the remote service.

Choose limits based on the number of hosts/routes, concurrency, latency, and the remote service's quota. Do not assume 100 is the right number for every environment.

### 4.3. Connect and Response Timeouts

```java
HttpClient httpClient = HttpClient.create(provider)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
        .responseTimeout(Duration.ofSeconds(10))
        .compress(true);
```

`CONNECT_TIMEOUT_MILLIS` limits the time to establish a TCP connection. `responseTimeout` limits the duration between network read operations while receiving a response according to Reactor Netty's semantics; it is not an overall deadline. `compress(true)` enables compression based on negotiation and the capabilities of both peers.

If you need channel-level read/write timeouts, you can add handlers in `doOnConnected`:

```java
HttpClient httpClient = HttpClient.create(provider)
        .doOnConnected(connection ->
                connection.addHandlerLast(new ReadTimeoutHandler(15))
                        .addHandlerLast(new WriteTimeoutHandler(15)));
```

This is a lower-level configuration than the HTTP layer. Timeout handlers act on the I/O channel; choose values appropriate for streaming and long-lived endpoints.

### 4.4. Creating WebClient and Managing the Pool

```java
@Bean(destroyMethod = "dispose")
ConnectionProvider catalogConnectionProvider() {
    return ConnectionProvider.builder("catalog-pool")
            .maxConnections(100)
            .pendingAcquireMaxCount(500)
            .pendingAcquireTimeout(Duration.ofSeconds(10))
            .maxIdleTime(Duration.ofSeconds(30))
            .maxLifeTime(Duration.ofMinutes(5))
            .build();
}

@Bean
WebClient catalogWebClient(
        WebClient.Builder builder,
        ConnectionProvider catalogConnectionProvider) {

    HttpClient httpClient = HttpClient.create(catalogConnectionProvider)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
            .responseTimeout(Duration.ofSeconds(10));

    return builder.clone()
            .baseUrl("https://catalog.example.com")
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .build();
}
```

Spring manages the lifecycle of the custom pool and calls `dispose` when the bean is destroyed. WebClient is created once and reused; do not create a new pool per request.

If using the default Reactor Netty global resources, multiple clients can share event loop and connection resources. Do not dispose global resources while the application still has requests running. With a custom provider, manage its lifecycle via the bean/application context.

### 4.5. Proxy, TLS, and HTTP/2

A proxy can be configured on `HttpClient`:

```java
HttpClient httpClient = HttpClient.create(provider)
        .proxy(proxy -> proxy
                .type(ProxyProvider.Proxy.HTTP)
                .host("proxy.internal")
                .port(8080));
```

TLS can be configured via an SSL context:

```java
HttpClient httpClient = HttpClient.create(provider)
        .secure(ssl -> ssl.sslContext(sslContext));
```

`sslContext` must use valid trust material, such as a truststore containing an internal CA. Do not disable certificate or hostname verification as a quick fix for TLS errors.

Reactor Netty can configure `HttpProtocol.H2` when the client, TLS/ALPN, and server support HTTP/2. With HTTPS, ALPN is typically used to negotiate the protocol. Setting the protocol does not guarantee that the target server supports it.

## 5. JDK HttpClient

### 5.1. When to Choose It?

`JdkClientHttpConnector` uses `java.net.http.HttpClient`, available since JDK 11. This is worth considering when you want to reduce third-party dependencies, the application has already standardized on JDK HttpClient, you need HTTP/2/TLS per JDK capabilities, and you do not need the specialized pool options of Netty or Apache.

### 5.2. Configuration

```java
java.net.http.HttpClient jdkClient =
        java.net.http.HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .version(java.net.http.HttpClient.Version.HTTP_2)
                .followRedirects(
                        java.net.http.HttpClient.Redirect.NORMAL)
                .build();

ClientHttpConnector connector =
        new JdkClientHttpConnector(jdkClient);

WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example.com")
        .clientConnector(connector)
        .build();
```

The JDK builder allows configuring connect timeout, HTTP version, redirects, proxy selector, SSL context/parameters, authenticator, and executor.

### 5.3. Known Limitations

JDK HttpClient does not provide a public API equivalent to Reactor Netty `ConnectionProvider` for setting global max connections, max pending acquires, or idle eviction. Connection reuse is managed by the implementation.

Connect timeout is set on `HttpClient`. Request timeout can be configured on `java.net.http.HttpRequest`, but `JdkClientHttpConnector` does not provide the same set of read/write/pool options as Reactor Netty.

You can set a reactive deadline at the WebClient layer:

```java
Mono<CatalogItem> result = client.get()
        .uri("/items/7")
        .retrieve()
        .bodyToMono(CatalogItem.class)
        .timeout(Duration.ofSeconds(12));
```

`Mono.timeout` cancels the subscription when the deadline is exceeded. This is a deadline for the publisher in the application; it does not replace connect timeout and is not a separate configuration for socket read. If you need deep pool tuning or per-layer timeouts, consider another engine.

## 6. Jetty

### 6.1. When to Choose It?

The Jetty connector is suitable when the organization already operates Jetty, wants to reuse Jetty HttpClient knowledge/configuration, or needs Jetty's HTTP client features.

Spring integrates via `JettyClientHttpConnector` and Jetty Reactive HttpClient. Dependencies must be compatible with the Jetty line supported by the Spring Framework version in use. Do not arbitrarily mix Jetty major versions in the same application.

### 6.2. Configuring the Client

```java
org.eclipse.jetty.client.HttpClient jettyClient =
        new org.eclipse.jetty.client.HttpClient();

jettyClient.setConnectTimeout(5_000);
jettyClient.setIdleTimeout(15_000);
jettyClient.setMaxConnectionsPerDestination(64);
jettyClient.start();

ClientHttpConnector connector =
        new JettyClientHttpConnector(jettyClient);

WebClient client = WebClient.builder()
        .baseUrl("https://catalog.example.com")
        .clientConnector(connector)
        .build();
```

`setConnectTimeout` limits the time to open a connection; `setIdleTimeout` sets the idle timeout according to Jetty's semantics; `setMaxConnectionsPerDestination` limits connections to a destination. Call `start` before sending requests.

In a Spring application, declare a bean to manage the lifecycle:

```java
@Bean(initMethod = "start", destroyMethod = "stop")
org.eclipse.jetty.client.HttpClient jettyHttpClient() {
    org.eclipse.jetty.client.HttpClient client =
            new org.eclipse.jetty.client.HttpClient();

    client.setConnectTimeout(5_000);
    client.setIdleTimeout(15_000);
    client.setMaxConnectionsPerDestination(64);
    return client;
}
```

Inject the Spring-managed client into the connector. Do not call `stop` after each request; the client is reused and only stops when the application context closes.

Method names and options may differ across major versions. Consult the Javadoc for the exact Jetty line selected by your application's dependencies.

## 7. Apache HttpComponents 5

### 7.1. When to Choose It?

`HttpComponentsClientHttpConnector` integrates WebClient with Apache HttpComponents 5 Async Client. Choose it when the application already uses Apache HttpClient, needs a connection manager with total/per-route limits, wants to configure connections/TLS/proxies through the Apache ecosystem, or needs an async engine independent of Reactor Netty.

You must use the **HttpComponents 5 async** line compatible with Spring Framework. Blocking Apache HttpClient 4.x is not the client this connector requires.

### 7.2. Connection Manager and Timeouts

```java
ConnectionConfig connectionConfig = ConnectionConfig.custom()
        .setConnectTimeout(Timeout.ofSeconds(5))
        .build();

PoolingAsyncClientConnectionManager manager =
        PoolingAsyncClientConnectionManagerBuilder.create()
                .setMaxConnTotal(200)
                .setMaxConnPerRoute(50)
                .setDefaultConnectionConfig(connectionConfig)
                .build();

RequestConfig requestConfig = RequestConfig.custom()
        .setResponseTimeout(Timeout.ofSeconds(15))
        .build();

CloseableHttpAsyncClient apacheClient =
        HttpAsyncClients.custom()
                .setConnectionManager(manager)
                .setDefaultRequestConfig(requestConfig)
                .build();

apacheClient.start();

ClientHttpConnector connector =
        new HttpComponentsClientHttpConnector(apacheClient);
```

`setMaxConnTotal` limits total connections; `setMaxConnPerRoute` limits connections per route; `setConnectTimeout` configures connection establishment time; `setResponseTimeout` configures the response timeout. Call `start` before sending requests.

### 7.3. Lifecycle Management

`CloseableHttpAsyncClient` must be started and closed according to its lifecycle. You can let Spring manage it:

```java
@Bean(initMethod = "start", destroyMethod = "close")
CloseableHttpAsyncClient apacheAsyncClient() {
    PoolingAsyncClientConnectionManager manager =
            PoolingAsyncClientConnectionManagerBuilder.create()
                    .setMaxConnTotal(200)
                    .setMaxConnPerRoute(50)
                    .build();

    return HttpAsyncClients.custom()
            .setConnectionManager(manager)
            .build();
}

@Bean
ClientHttpConnector apacheConnector(
        CloseableHttpAsyncClient apacheAsyncClient) {
    return new HttpComponentsClientHttpConnector(apacheAsyncClient);
}
```

If the application creates the connection manager/client manually outside Spring, the application must close them on shutdown. Do not create a new async client per request.

## 8. Comparing Timeouts by Layer

The word “timeout” can refer to several different durations:

| Timeout | Measured Duration | Configuration Examples |
| --- | --- | --- |
| Pool acquire | Waiting to borrow a connection from the pool | Reactor Netty `pendingAcquireTimeout`; Apache pool manager has corresponding configuration. |
| Connect | Establishing a TCP connection to the destination | Reactor Netty `CONNECT_TIMEOUT_MILLIS`; JDK `connectTimeout`; Jetty `setConnectTimeout`; Apache `ConnectionConfig`. |
| TLS handshake | Completing TLS negotiation | Depends on connector/engine and SSL configuration. |
| Response/read | Waiting for a response or subsequent read data | Reactor Netty `responseTimeout`; Jetty idle timeout; Apache response timeout. |
| Write | Writing the request body to the transport | Depends on engine and channel/request configuration. |
| Overall deadline | Total time the application waits for the publisher to complete | Reactor `Mono.timeout`/`Flux.timeout` or caller-layer deadline. |

A request might wait 8 seconds for the pool, 2 seconds to connect, and then 10 seconds to read the response. If you only set an overly large overall timeout, the application holds resources longer than intended. If you set individual timeouts too short, large uploads or valid streaming responses may be cut off.

With WebClient, `timeout(Duration)` on the publisher is useful for setting an overall deadline. It cancels the publisher when the limit is exceeded, but it does not replace pool acquire timeout, connect timeout, or engine idle/read timeouts.

For infinite streams such as SSE, a whole-stream timeout is usually inappropriate. Consider idle timeouts between events, heartbeats, and cancellation according to the stream's contract.

## 9. TLS, Proxy, Redirect, and HTTP/2

### 9.1. TLS

The connector must verify the certificate chain and hostname of the remote server. For an internal CA, configure a truststore or SSL context containing the approved CA.

Do not use a trust-all manager or disable hostname verification in production. Doing so removes server authentication and can open the door to man-in-the-middle attacks.

If mutual TLS is required, the client must have the appropriate key material/client certificate. How key/trust stores are loaded depends on the connector; manage secrets with a secret store and do not log passwords/private keys or commit them to source control.

### 9.2. Proxy

A proxy can be configured at the engine or JDK HttpClient level. Clearly define which destinations the proxy applies to, how authentication works, and internal bypass rules. Proxy timeouts and DNS resolution can introduce latency different from direct connections.

Do not log proxy credentials or authorization headers in debug logs. Place proxy host/port in environment configuration rather than hard-coding them in source code.

### 9.3. Redirect

The redirect policy determines whether the client automatically follows 3xx responses. Consider the number of hops, how method/body are handled per status code, and the risk of forwarding credentials or sensitive data to another origin.

Do not assume every redirect is safe for POST requests with a body or requests carrying an authorization header.

### 9.4. HTTP/2

HTTP/2 multiplexes multiple streams over a single connection and has its own flow control. This can reduce the number of connections, but it does not eliminate concurrency limits, pools, timeouts, or backpressure in the application.

HTTP/2 requires support from both client and server; HTTPS typically uses ALPN to negotiate the protocol. Configuring a connector to request HTTP/2 does not force the target server to support it. Monitor the negotiated protocol when debugging.

## 10. Connection Pools and Reusing WebClient

A built `WebClient` is immutable and suitable for reuse across many requests. Create singleton clients per destination or clearly defined configuration group.

A pool should have limits on maximum connections, pending acquire requests, acquire wait time, idle time, lifetime, and connections per host/route if the engine supports it.

If a remote service only allows 40 connections, configuring a pool of 500 can cause the system to exert pressure beyond quota. If the pool is too small, requests may wait long for acquire even when the remote server still has capacity.

Separate pools by dependency when destinations have different SLAs. For example, a payment API has a short deadline and low quota; a reporting API has large responses and long durations. Sharing one pool can allow slow workloads to occupy connections needed by critical workloads.

Do not create a new WebClient on every service call just to change the URI. Use a base URL, URI templates, or separate clients when different transport policies are needed.

## 11. Observability, Logging, and Resources

Metrics to observe:

| Metric | Meaning |
| --- | --- |
| Active/idle connections | Number of connections in use and idle. |
| Pending acquire | Number of requests waiting for a connection. |
| Acquire latency | Time to borrow a connection from the pool. |
| Connect latency | Time to establish a connection. |
| Response latency | Time to receive a response. |
| Timeout count | Number of requests exceeding deadlines/timeouts at each layer. |
| Connection errors | DNS, connect, TLS, or socket errors. |
| Retry count | Number of times the client retries a request. |
| Response status | Distribution of 2xx, 4xx, and 5xx by destination. |

If wire logging is enabled, request/response bodies may contain tokens, personal data, or business payloads. Enable it only under control, mask sensitive data, and turn it off after diagnosis.

Lifecycle by connector:

- Reactor Netty custom `ConnectionProvider` needs to be disposed when the application shuts down.
- JDK HttpClient is managed by the JDK; custom executors provided by the application require their own lifecycle.
- Jetty HttpClient needs to be started before use and stopped when the context closes.
- Apache CloseableHttpAsyncClient needs to be started and closed; the accompanying connection manager must also be released.

Do not close the client after each request because the client/pool is shared. Conversely, do not leave custom thread pools or connection managers alive after the application shuts down.

## 12. Spring Boot 3.3.5 Application with Reactor Netty

The example uses **Java 17+**, **Maven**, **Spring Boot 3.3.5**, and WebFlux. The application creates a singleton WebClient to a catalog service using a bounded connection pool and explicit timeouts. Tests use MockWebServer to verify requests/responses without calling external Internet services.

Structure:

```text
webclient-connector-demo/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/demo/
│   ├── ConnectorDemoApplication.java
│   ├── CatalogProperties.java
│   ├── CatalogWebClientConfig.java
│   ├── CatalogItem.java
│   └── CatalogClient.java
└── src/test/java/demo/CatalogClientTest.java
```

### 12.1. pom.xml

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
    <artifactId>webclient-connector-demo</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>4.12.0</version>
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
```

### 12.2. application.properties

```properties
catalog.base-url=https://catalog.example.com
```

In a deployment environment, replace the URL with service discovery or the corresponding environment configuration. Do not hard-code credentials in this file.

### 12.3. ConnectorDemoApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConnectorDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConnectorDemoApplication.class, args);
    }
}
```

### 12.4. CatalogProperties.java

```java
package demo;

import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(URI baseUrl) {}
```

### 12.5. CatalogWebClientConfig.java

```java
package demo;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;
import io.netty.channel.ChannelOption;

@Configuration
public class CatalogWebClientConfig {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogConnectionProvider() {
        return ConnectionProvider.builder("catalog-pool")
                .maxConnections(100)
                .pendingAcquireMaxCount(500)
                .pendingAcquireTimeout(Duration.ofSeconds(10))
                .maxIdleTime(Duration.ofSeconds(30))
                .maxLifeTime(Duration.ofMinutes(5))
                .build();
    }

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            ConnectionProvider catalogConnectionProvider,
            CatalogProperties properties) {

        HttpClient httpClient = HttpClient
                .create(catalogConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 5_000)
                .responseTimeout(Duration.ofSeconds(10));

        return builder.clone()
                .baseUrl(properties.baseUrl().toString())
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

The pool bean has a dedicated name so metrics and logs are easy to distinguish. `destroyMethod = "dispose"` releases the custom provider when the Spring context closes. The builder is cloned to configure the catalog client specifically while preserving Boot customizers.

### 12.6. CatalogItem.java

```java
package demo;

public record CatalogItem(long id, String name) {}
```

### 12.7. CatalogClient.java

```java
package demo;

import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class CatalogClient {
    private final WebClient client;

    public CatalogClient(WebClient catalogWebClient) {
        this.client = catalogWebClient;
    }

    public Mono<CatalogItem> findById(long id) {
        return client.get()
                .uri("/items/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(CatalogItem.class)
                .timeout(Duration.ofSeconds(12));
    }
}
```

`retrieve()` converts 4xx/5xx statuses into `WebClientResponseException` by default. `timeout` sets a deadline for the publisher from subscription until the body is decoded. It complements Reactor Netty's connect/response timeouts rather than replacing them.

If you want custom error mapping, you can add `onStatus`:

```java
.retrieve()
.onStatus(status -> status.value() == 429,
        response -> response.bodyToMono(String.class)
                .defaultIfEmpty("Rate limited")
                .map(RateLimitedException::new))
.bodyToMono(CatalogItem.class)
```

`RateLimitedException` is an application-defined exception. Read the response body only once and convert it into controlled error information.

### 12.8. CatalogClientTest.java

```java
package demo;

import java.util.concurrent.TimeUnit;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogClientTest {

    @Test
    void sendsRequestAndDecodesJsonResponse() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.start();
            server.enqueue(new MockResponse()
                    .setResponseCode(200)
                    .addHeader(
                            "Content-Type",
                            MediaType.APPLICATION_JSON_VALUE)
                    .setBody("""
                            {"id":7,"name":"Keyboard"}
                            """));

            WebClient webClient = WebClient.builder()
                    .baseUrl(server.url("/").toString())
                    .clientConnector(new ReactorClientHttpConnector(
                            HttpClient.create()))
                    .build();

            CatalogClient client = new CatalogClient(webClient);

            StepVerifier.create(client.findById(7))
                    .expectNext(new CatalogItem(7, "Keyboard"))
                    .verifyComplete();

            RecordedRequest request =
                    server.takeRequest(1, TimeUnit.SECONDS);

            assertThat(request).isNotNull();
            assertThat(request.getMethod()).isEqualTo("GET");
            assertThat(request.getPath()).isEqualTo("/items/7");
            assertThat(request.getHeader("Accept"))
                    .contains(MediaType.APPLICATION_JSON_VALUE);
        }
    }

    @Test
    void mapsServerErrorToWebClientResponseException() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.start();
            server.enqueue(new MockResponse()
                    .setResponseCode(503)
                    .setBody("temporarily unavailable"));

            WebClient webClient = WebClient.builder()
                    .baseUrl(server.url("/").toString())
                    .clientConnector(new ReactorClientHttpConnector(
                            HttpClient.create()))
                    .build();

            CatalogClient client = new CatalogClient(webClient);

            StepVerifier.create(client.findById(8))
                    .expectErrorMatches(error ->
                            error instanceof
                                    org.springframework.web.reactive.function.client
                                            .WebClientResponseException exception
                                    && exception.getStatusCode().value() == 503)
                    .verify();
        }
    }
}
```

MockWebServer receives requests like a local HTTP server and returns predefined responses. The test uses the Reactor Netty connector like the application configuration, but the base URL points to the test server. `StepVerifier` verifies the decoded result and the HTTP 503 error.

Run the tests:

```bash
mvn test
```

The first test verifies the GET method, `/items/7` path, Accept header, and that the JSON body is decoded into the record. The second test verifies that a 503 response becomes a `WebClientResponseException`. The tests do not call the Internet and do not depend on a real catalog service.

## 13. Common Mistakes and How to Handle Them

| Mistake | Consequence | How to Handle |
| --- | --- | --- |
| Thinking the WebClient connector is the server connector | Changing the outbound client while expecting the inbound server to change | Configure the client connector and server runtime independently. |
| Leaving connector selection implicit when operational stability is required | Classpath changes can change the implementation | Configure `clientConnector` explicitly. |
| Creating a new WebClient for every request | Increases objects and can repeatedly create pools/thread resources | Create singleton beans/clients per destination. |
| Creating an unbounded or overly large pool | The remote service can become overloaded | Set max connections, pending acquire limits, and timeouts. |
| Setting only an overall timeout | Requests can wait too long on pool/connect before failing | Set separate timeouts for acquire/connect/response and an overall deadline. |
| Confusing response timeout with overall deadline | Streams can continue for a long time while data keeps arriving | Choose idle/read timeouts and overall deadlines for their intended purpose. |
| Using `Mono.timeout` instead of all socket timeouts | Cannot control each transport layer | Combine publisher timeouts with engine configuration. |
| Using the JDK connector while expecting Netty's pool tuning API | No equivalent option in the JDK public API | Accept JDK-managed pooling or choose an engine with the needed pool control. |
| Using Apache HttpClient 4 with the HttpComponents 5 connector | Incompatible APIs | Use the right version of Apache HttpComponents 5 Async Client. |
| Mixing multiple Jetty major versions | Binary or API incompatibility errors | Align Jetty Reactive HttpClient and Jetty core with the Spring-supported line. |
| Forgetting to start the Jetty/Apache async client | Requests can fail because the client is not running | Manage init/start and destroy/stop/close via Spring beans. |
| Not disposing a custom Reactor ConnectionProvider | Keeps connections/resources after shutdown | Let Spring call dispose when the application context closes. |
| Disposing global Reactor resources while the app is running | Other clients may be affected | Only dispose global resources during coordinated lifecycle shutdown. |
| Disabling TLS certificate verification | Connections lose server authentication | Configure the right truststore/CA and keep hostname verification. |
| Enabling wiretap logging with full payloads | May expose tokens or personal data | Enable debug logging selectively and mask sensitive data. |
| Retrying every POST or upload | Causes duplicate side effects when the server has already processed the request | Retry per idempotency contract, with bounded attempts and backoff. |
| Configuring HTTP/2 without checking ALPN/server | The client may still negotiate HTTP/1.1 or fail | Verify the negotiated protocol and server capabilities. |
| Sharing one pool for dependencies with different SLAs | Slow workloads can starve connections for critical workloads | Separate WebClient/pools by dependency or policy group. |

## 14. Self-Check Questions

**Question 1.** What is the role of `ClientHttpConnector`?  
**Answer:** It connects WebClient to the actual HTTP client engine to perform outbound requests, manage transport, and translate responses back to Spring's abstraction.

**Question 2.** Is the WebClient connector the same as the WebFlux server connector?  
**Answer:** No. The WebClient connector sends outbound requests; the server runtime receives inbound requests. The two configurations are independent.

**Question 3.** When should you choose Reactor Netty?  
**Answer:** When you need native reactive support, detailed pool and transport tuning, and the application already uses Reactor/WebFlux.

**Question 4.** What are the advantages of the JDK connector?  
**Answer:** It uses java.net.http.HttpClient built into JDK 11+, reduces dependencies, and supports HTTP/2; in return, it has fewer public pool tuning APIs.

**Question 5.** What lifecycle requirements do Jetty and Apache clients have?  
**Answer:** Jetty HttpClient requires start/stop; Apache CloseableHttpAsyncClient requires start/close. Manage them through the Spring bean lifecycle.

**Question 6.** How does pool acquire timeout differ from connect timeout?  
**Answer:** Acquire timeout is the time spent waiting for an available connection from the pool; connect timeout is the time spent establishing a new connection to the server.

**Question 7.** Is Reactor Netty's `responseTimeout` an overall deadline?  
**Answer:** No. It controls network read intervals according to Reactor Netty's semantics; an overall deadline can be added using Mono/Flux timeout.

**Question 8.** Why should you avoid calling `WebClient.create()` arbitrarily in a Boot application?  
**Answer:** A manually created client can bypass builder customizers, codecs, filters, and observation configured by Boot.

**Question 9.** Should you disable TLS verification to fix certificate errors?  
**Answer:** No. Install the proper CA/truststore and verify hostnames; disabling validation removes server authentication.

**Question 10.** Can every request be retried on timeout?  
**Answer:** No. The server may have already processed the request before the client timed out. Retry only when the operation is idempotent or uses an idempotency key with an appropriate backoff policy.

## Key Takeaways

- `ClientHttpConnector` is WebClient's outbound transport boundary; it is independent of the WebFlux server runtime.
- Reactor Netty fits when native reactive support and deep pool/transport tuning are needed; JDK reduces dependencies; Jetty and Apache are useful when systems have already standardized on those engines.
- Configure the connector explicitly via `WebClient.Builder.clientConnector` when you want stable transport behavior across environments.
- Distinguish pool acquire, connect, response/read, and overall deadline. One timeout does not replace timeouts at other layers.
- Create reusable WebClient and pool instances; manage the lifecycle of `ConnectionProvider`, Jetty HttpClient, and Apache async client properly.
- Keep TLS verification enabled, validate proxy/HTTP2 configuration, monitor pool/latency/errors, and retry only when semantics allow.

### References

1. [Spring Framework – WebClient Builder](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): WebClient.Builder, ClientHttpConnector, and client configuration.
2. [Spring Framework – ReactorClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/reactive/ReactorClientHttpConnector.html): Reactor Netty integration.
3. [Spring Framework – JdkClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/reactive/JdkClientHttpConnector.html): JDK HttpClient integration.
4. [Spring Framework – JettyClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/reactive/JettyClientHttpConnector.html): Jetty Reactive HttpClient integration.
5. [Spring Framework – HttpComponentsClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/reactive/HttpComponentsClientHttpConnector.html): Apache HttpComponents async client integration.
6. [Reactor Netty Reference](https://projectreactor.io/docs/netty/release/reference/http-client.html): pools, timeouts, TLS, proxies, and HTTP client configuration.
7. [JDK HttpClient API](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP/2, connect timeout, proxy, SSL, and redirects.
8. [Jetty HttpClient Documentation](https://jetty.org/docs/jetty/12/programming-guide/client/http.html): Jetty client configuration and lifecycle.
9. [Apache HttpComponents 5 – Async Client](https://hc.apache.org/httpcomponents-client-5.3.x/asyncclient5/): async client and pooling connection manager.
