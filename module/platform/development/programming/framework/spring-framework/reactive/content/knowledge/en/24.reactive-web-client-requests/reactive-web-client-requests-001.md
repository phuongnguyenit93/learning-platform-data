# WebClient and the Role of ClientHttpConnector in Spring WebFlux

## 1. What Problem Does WebClient Solve?

Spring WebFlux provides **WebClient** to call HTTP services using the reactive model. Its API is fluent, based on Reactor, and supports asynchronous request/response handling, streaming, and composition with Mono/Flux.

For example, a service that retrieves product information from a catalog:

~~~java
Mono<Product> product = webClient.get()
        .uri("/products/{id}", "p-1")
        .retrieve()
        .bodyToMono(Product.class);
~~~

This code describes the request and how to decode the response. It does not specify which networking library sends the HTTP request. The I/O execution lives under another abstraction: **ClientHttpConnector**.

WebClient separates two concerns:

- **Spring's API and HTTP processing layer:** building the URI, method, headers, body, filters, status handling, encoding/decoding data, and returning Mono/Flux.
- **Transport layer:** opening connections, DNS, TCP, TLS, connection pooling, proxies, sending/receiving bytes, timeouts, and adapting responses from the underlying HTTP client into Spring's abstraction.

Thanks to this separation, the same WebClient code can be used with Reactor Netty, JDK HttpClient, Jetty Reactive HttpClient, or Apache HttpComponents without rewriting the API-calling business logic.

## 2. What Is ClientHttpConnector?

ClientHttpConnector is an interface in the org.springframework.http.client.reactive package. It is the abstraction that allows an underlying HTTP client to connect to an origin server and provides the mechanism to send a ClientHttpRequest and receive a ClientHttpResponse.

Core contract:

~~~java
Mono<ClientHttpResponse> connect(
        HttpMethod method,
        URI uri,
        Function<? super ClientHttpRequest, Mono<Void>> requestCallback
);
~~~

Three key parameters:

- **HttpMethod:** GET, POST, PUT, PATCH, DELETE...
- **URI:** the target address built by WebClient.
- **requestCallback:** a callback that prepares and writes the request via ClientHttpRequest; the callback returns a Mono<Void> signaling that writing the request has completed.

The return value is Mono<ClientHttpResponse>. The connector is responsible for bridging Spring's standard request/response API with the specific API of the underlying HTTP library.

### 2.1. What Does a Connector Do?

A real-world connector typically coordinates:

1. Creating or acquiring an appropriate connection from the transport.
2. Resolving the hostname and establishing a network connection when needed.
3. Performing the TLS handshake for HTTPS.
4. Applying connection pool, proxy, and HTTP client protocol configuration.
5. Writing the method, URI, headers, and body provided by Spring.
6. Receiving the status, headers, and response body.
7. Converting data into ClientHttpResponse and DataBuffer for WebClient to process further.
8. Propagating connection errors, TLS errors, timeouts, and cancellation through the reactive publisher.

The connector does **not** make business decisions such as whether status 404 means a product does not exist, nor does it choose the Product DTO to decode JSON. Those responsibilities belong to WebClient, codecs, and application code.

### 2.2. A Connector Is Not a Codec

Distinction:

| Component | Responsibility |
| --- | --- |
| WebClient | Fluent API to build requests and compose responses |
| ExchangeFunction | Executes an HTTP exchange through the filter chain |
| ExchangeFilterFunction | Pre/post-exchange logic such as auth headers, correlation ID, logging |
| ClientHttpConnector | Adapter between Spring's HTTP abstraction and the underlying HTTP client |
| ClientHttpRequest / ClientHttpResponse | Spring's request/response abstraction |
| HttpMessageWriter / HttpMessageReader | Encodes/decodes bodies by media type |
| DataBuffer | Unit of request/response data buffering in Spring |

For example, when WebClient sends JSON: the codec serializes the Java object into DataBuffers before the connector writes the data to the transport. When the response arrives, the connector provides the response body as DataBuffers; the codec reads the JSON and converts it into a Product.

Changing the connector does not mean changing the JSON codec. Nor should DTO parsing logic be placed in a custom connector.

## 3. Processing Flow from WebClient to the Network and Back

~~~text
Application service
       |
       v
WebClient request spec
(method, URI, headers, body)
       |
       v
ExchangeFilterFunction chain
(authentication, tracing, metrics)
       |
       v
ExchangeFunction
       |
       v
ClientHttpConnector
       |
       v
Underlying HTTP client
(Reactor Netty / JDK / Jetty / Apache)
       |
       v
DNS, TCP, TLS, pool, HTTP I/O
       |
       v
ClientHttpResponse + DataBuffer stream
       |
       v
HTTP message readers / codecs
(JSON, String, byte[], SSE...)
       |
       v
Mono<T> / Flux<T>
       |
       v
Application
~~~

In short:

- WebClient knows **what request to send**.
- ClientHttpConnector knows **which HTTP transport to use to send it**.
- Codecs know **how to convert the body between Java objects and HTTP bytes**.
- Reactor represents the process as a Publisher so the caller can compose and cancel it.

A request may not yet run at the time the Mono is built. With a typical cold publisher, I/O begins upon subscription.

## 4. Common ClientHttpConnector Implementations

Spring Framework supports multiple implementations. Spring Boot can automatically select a connector based on dependencies on the classpath.

| Connector | Underlying HTTP client | When appropriate |
| --- | --- | --- |
| ReactorClientHttpConnector | Reactor Netty HttpClient | WebFlux reactive stack, connection pool, Netty resources, and rich transport configuration |
| JdkClientHttpConnector | java.net.http.HttpClient | Wanting to use the built-in JDK HTTP client available since Java 11, reducing external transport dependencies |
| JettyClientHttpConnector | Jetty Reactive HttpClient | Systems already using Jetty or wanting to share Jetty resources |
| HttpComponentsClientHttpConnector | Apache HttpComponents HttpClient 5.x | Systems standardized on Apache HTTP client or needing HttpComponents capabilities |

There is no single best connector for every system. Evaluate protocol, proxy, TLS, pooling, observability, resource lifecycle, dependency footprint, and operational practices.

### 4.1. ReactorClientHttpConnector

This connector is based on Reactor Netty. It can accept a configured HttpClient:

~~~java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(5));

ClientHttpConnector connector =
        new ReactorClientHttpConnector(httpClient);

WebClient client = WebClient.builder()
        .clientConnector(connector)
        .build();
~~~

This is the common choice in Spring Boot WebFlux applications because spring-boot-starter-webflux brings Reactor Netty in as a default dependency.

Key capabilities of Reactor Netty:

- ConnectionProvider for pool management.
- Event loop and non-blocking network I/O.
- Connect timeout and response timeout.
- TLS configuration.
- Proxy configuration.
- HTTP/1.1 and HTTP/2 depending on configuration, transport, and server.
- Connection and request metrics when appropriate observability is enabled.

### 4.2. JdkClientHttpConnector

This connector uses the JDK's java.net.http.HttpClient:

~~~java
HttpClient jdkClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();

ClientHttpConnector connector =
        new JdkClientHttpConnector(jdkClient);

WebClient client = WebClient.builder()
        .clientConnector(connector)
        .build();
~~~

JDK HttpClient is built in since Java 11 and supports HTTP/1.1, HTTP/2, TLS, proxy, and an async API. The Spring adapter translates its requests/responses into the ClientHttpConnector abstraction.

Note: Reactor Netty-specific options such as ConnectionProvider or ChannelOption do not apply directly to the JDK connector. Configuration must follow the API of the corresponding underlying HTTP client.

### 4.3. JettyClientHttpConnector

The Jetty connector uses Jetty Reactive HttpClient. It is useful when the system already uses Jetty and wants to manage resources on the same platform.

~~~java
HttpClient jettyClient = new HttpClient();
JettyClientHttpConnector connector =
        new JettyClientHttpConnector(jettyClient);
~~~

The snippet above illustrates creating a connector from a Jetty client; in a real application you need to configure, start/stop, and manage resources according to the documentation of the Jetty version in use. The Jetty client and JettyResourceFactory have their own lifecycle; do not create a new client per HTTP request.

### 4.4. HttpComponentsClientHttpConnector

Spring provides a connector for Apache HttpComponents HttpClient 5.x:

~~~java
ClientHttpConnector connector =
        new HttpComponentsClientHttpConnector();

WebClient client = WebClient.builder()
        .clientConnector(connector)
        .build();
~~~

The default implementation creates and starts a CloseableHttpAsyncClient. When providing a client manually, the application must manage its lifecycle and close resources at the appropriate time. Do not leave async clients or connection managers alive indefinitely after the ApplicationContext closes.

### 4.5. Boot Auto-Detected Connector

Spring Boot automatically selects a ClientHttpConnector based on dependencies present on the classpath. In Spring Boot 3.5, the typical priority order is:

1. Reactor Netty.
2. Jetty Reactive Streams client.
3. Apache HttpClient.
4. JDK HttpClient.

If multiple implementations are present, the higher-priority connector is selected. spring-boot-starter-webflux pulls in Reactor Netty by default.

If you want precise control, declare your own ClientHttpConnector bean or select the connector through the appropriate Boot configuration. Do not rely on guessing "which dependencies happen to be on the machine" to predict production transport; verify the dependency tree and runtime configuration.

## 5. WebClient.Builder and Request Configuration

### 5.1. Creating a WebClient

There are two common approaches:

~~~java
WebClient simple = WebClient.create();

WebClient withBaseUrl =
        WebClient.create("https://catalog.example.com");

WebClient configured = WebClient.builder()
        .baseUrl("https://catalog.example.com")
        .defaultHeader(HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
        .build();
~~~

A built WebClient is immutable. To create another client from an existing configuration, use mutate():

~~~java
WebClient catalogClient = WebClient.builder()
        .baseUrl("https://catalog.example.com")
        .build();

WebClient adminClient = catalogClient.mutate()
        .defaultHeader("X-Client-Name", "admin")
        .build();
~~~

The first client is not modified when creating the second client.

### 5.2. Using the WebClient.Builder Provided by Spring Boot

In a Spring Boot application, you should inject the auto-configured WebClient.Builder:

~~~java
@Service
public class CatalogService {

    private final WebClient webClient;

    public CatalogService(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("https://catalog.example.com")
                .build();
    }
}
~~~

Boot's builder may carry shared configurations such as connectors, codecs, and observation. The builder is a stateful object: mutations on a builder affect subsequent clients built from that builder. If you need multiple independent variants, clone the builder before modifying it.

Calling WebClient.create() is still valid, but that approach does not automatically pick up customizations that Spring Boot has applied to WebClient.Builder.

### 5.3. baseUrl, defaultHeader, and defaultRequest

~~~java
WebClient client = WebClient.builder()
        .baseUrl("https://api.example.com/v1")
        .defaultHeader(HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE)
        .defaultHeader("X-Application", "inventory")
        .defaultRequest(request -> {
            // Common request metadata can be added here.
        })
        .build();
~~~

baseUrl avoids repeating the host/path prefix. defaultHeader applies a default header to requests, unless a specific request overrides it according to the builder's rules.

Do not put a user's access token into defaultHeader on a singleton client shared across multiple users. Credentials should be attached per request or obtained from the appropriate security context to avoid token leakage between users.

### 5.4. URI Builder and Query Parameters

~~~java
Mono<String> result = client.get()
        .uri(uriBuilder -> uriBuilder
                .path("/products")
                .queryParam("category", "keyboard")
                .queryParam("page", 0)
                .build())
        .retrieve()
        .bodyToMono(String.class);
~~~

The URI builder properly encodes paths and query parameters. Avoid concatenating URL strings manually when input data contains spaces, Vietnamese diacritics, the & character, or reserved characters.

## 6. How to Send Requests and Receive Responses

### 6.1. retrieve()

retrieve() is a concise way when you want to extract the body and use default status handling:

~~~java
Mono<Product> product = client.get()
        .uri("/products/{id}", "p-1")
        .retrieve()
        .bodyToMono(Product.class);
~~~

By default, 4xx/5xx responses are converted into WebClientResponseException. You can add onStatus:

~~~java
Mono<Product> product = client.get()
        .uri("/products/{id}", id)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                response -> response.createException()
                        .map(NotFoundException::new))
        .bodyToMono(Product.class);
~~~

This is an illustrative snippet; NotFoundException is an application-defined exception.

### 6.2. exchangeToMono()

When you need custom control over the response based on status, use exchangeToMono:

~~~java
Mono<Product> product = client.get()
        .uri("/products/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Product.class);
            }
            if (response.statusCode().value() == 404) {
                return response.releaseBody()
                        .then(Mono.empty());
            }
            return response.createError();
        });
~~~

exchangeToMono provides ClientResponse so you can handle status, headers, and body as desired. If you do not read the body, you must ensure the response is properly released/consumed so the connection can be reused.

Do not retain ClientResponse and return it outside to be used after the callback finishes. Decode the body inside the callback or convert it into an explicitly owned data type.

### 6.3. bodyToMono and bodyToFlux

- bodyToMono(Product.class): decodes a body into at most one object.
- bodyToFlux(Product.class): reads a sequence of elements from a streaming body, such as NDJSON or a compatible media type.
- bodyToMono(String.class): reads the entire body into a String; unsuitable for infinite or very large responses.
- bodyToMono(byte[].class): aggregates the body into a byte array; consider payload size.

For small JSON arrays, you can use Flux or Mono<List<T>> depending on the contract. For large payloads or continuous streams, avoid aggregating the entire response in memory.

### 6.4. Request Body

~~~java
Mono<OrderResponse> created = client.post()
        .uri("/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateOrderRequest("p-1", 2))
        .retrieve()
        .bodyToMono(OrderResponse.class);
~~~

bodyValue is used when an object or value is already available. For a Publisher, use body:

~~~java
Flux<OrderResponse> result = client.post()
        .uri("/orders/bulk")
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(orderPublisher, OrderRequest.class)
        .retrieve()
        .bodyToFlux(OrderResponse.class);
~~~

The second snippet assumes the upstream supports NDJSON and the corresponding streaming contract. Content-Type must match the format accepted by the server.

## 7. Filters: Where to Place Shared WebClient Logic

ExchangeFilterFunction allows inserting logic before and after an HTTP exchange without duplicating code across service methods.

### 7.1. Adding a Correlation ID

~~~java
ExchangeFilterFunction correlationFilter =
        (request, next) -> {
            ClientRequest filtered = ClientRequest.from(request)
                    .header("X-Correlation-Id", UUID.randomUUID().toString())
                    .build();

            return next.exchange(filtered);
        };
~~~

The filter creates a new ClientRequest and forwards it to the next filter. If the request already has a correlation ID from upstream, preserve that ID instead of always generating a new one.

### 7.2. Logging Request and Response Metadata

~~~java
ExchangeFilterFunction loggingFilter =
        ExchangeFilterFunction.ofRequestProcessor(request -> {
            log.debug("HTTP {} {}", request.method(), request.url());
            return Mono.just(request);
        });
~~~

You can use ofResponseProcessor to observe status and headers. Do not log Authorization, Cookie, tokens, passwords, or entire bodies containing sensitive data.

If a filter needs to read the response body for logging, remember that the body is a single-read stream. It must be buffered and the response reconstructed properly; uncontrolled body reading can leave downstream consumers with no data.

### 7.3. Adding Filters to the Builder

~~~java
WebClient client = WebClient.builder()
        .filter(correlationFilter)
        .filter(loggingFilter)
        .build();
~~~

Filters are executed in a chain. A filter can modify the request, invoke the next filter, and then observe or transform the response when the publisher emits a result.

Do not use filters as the place to hold all endpoint business logic. Keep filters for cross-cutting concerns such as authentication, tracing, metrics, or standard headers.

## 8. The Role of Codecs and Memory Limits

WebClient uses HTTP message codecs to serialize requests and deserialize responses. Spring provides codecs for JSON, String, byte[], form data, multipart, and common media types.

Example of configuring Jackson codec and buffer limits:

~~~java
WebClient client = WebClient.builder()
        .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(2 * 1024 * 1024))
        .build();
~~~

Spring limits by default the amount of data buffered in memory for aggregating codecs; the Framework 6.2 documentation specifies a default of 256 KB for default codecs. Exceeding the limit may raise DataBufferLimitException.

Increase the limit only when the use case truly requires it. For large files, streaming upload/download is usually better than raising the limit to hundreds of MB.

### 8.1. DataBuffer and Ownership

The response body is a stream of DataBuffers. When using a Netty-based connector, buffers may use pooled direct memory. If you manually read/retain buffers outside the callback lifecycle, you must understand retain/release and ownership rules.

Prefer bodyToMono/bodyToFlux and standard codecs so Spring manages buffers. Only manipulate DataBuffers directly when there is a specific requirement, and test success, error, and cancellation paths to avoid memory leaks.

## 9. Transport Configuration with Reactor Netty

### 9.1. Connection Timeout and Response Timeout

Timeouts have distinct meanings:

| Timeout | Limit |
| --- | --- |
| Connect timeout | Time to establish the TCP connection |
| TLS handshake timeout | Time to complete TLS negotiation |
| Response timeout | Time waiting for response data according to transport policy |
| Read timeout | Period without reading data according to the configured handler |
| Write timeout | Time to write data according to the configured handler |
| Mono.timeout(...) | Time the request publisher is allowed to run before being timed out/canceled |

Do not lump everything into a single timeout number. A request downloading a large file may need a long total duration while still requiring appropriate connection and idle limits.

### 9.2. ConnectionProvider and Pool

~~~java
ConnectionProvider provider = ConnectionProvider.builder("catalog-pool")
        .maxConnections(50)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .maxIdleTime(Duration.ofSeconds(20))
        .maxLifeTime(Duration.ofMinutes(5))
        .build();

HttpClient httpClient = HttpClient.create(provider)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3000)
        .responseTimeout(Duration.ofSeconds(5));

ClientHttpConnector connector =
        new ReactorClientHttpConnector(httpClient);
~~~

Meaning:

- maxConnections limits the number of connections managed by the pool.
- pendingAcquireTimeout limits how long a caller waits to acquire a connection when the pool is at capacity.
- maxIdleTime limits the idle age of a connection.
- maxLifeTime limits the total lifetime of a connection.
- CONNECT_TIMEOUT_MILLIS sets the limit for establishing a connection.
- responseTimeout sets the response read timeout according to Reactor Netty semantics.

The numbers above are starting examples only, not sizing suitable for every workload. Base them on concurrency, upstream quotas, latency, request duration, and load testing.

When creating a ConnectionProvider manually, you must dispose of it when the ApplicationContext closes. In typical applications, using global Reactor Netty resources or a Spring-managed resource factory reduces the risk of unnecessarily creating multiple separate event loops/pools.

### 9.3. Do Not Create a WebClient per Request

Do not do this:

~~~java
public Mono<Product> find(String id) {
    WebClient client = WebClient.builder().build();
    return client.get().uri("/products/{id}", id)
            .retrieve().bodyToMono(Product.class);
}
~~~

Repeatedly creating new clients makes it difficult to share connectors, pools, event loops, filters, and metrics. Typically you should create a long-lived WebClient bean per upstream or configuration group.

A single WebClient can be used concurrently by many requests because WebClient itself is immutable. Avoid storing per-user mutable state inside a singleton WebClient object.

## 10. TLS, Proxy, Authentication, and Network Security

### 10.1. HTTPS and Certificate Validation

For HTTPS endpoints, the connector performs the TLS handshake and validates certificates according to the underlying HTTP client's configuration. Never disable certificate validation just "to make requests work."

If the upstream uses an internal CA, configure an appropriate trust store/SSL context. Verify hostnames and certificate chains, and maintain a certificate rotation process.

### 10.2. Proxy

Each transport has its own proxy API. Reactor Netty, JDK HttpClient, Jetty, and Apache HttpComponents do not share a native proxy configuration. Choose a connector according to required capabilities and configure the proxy on the right client.

### 10.3. Authorization Header

A Bearer token can be added per request:

~~~java
Mono<Product> result = client.get()
        .uri("/products/{id}", id)
        .headers(headers -> headers.setBearerAuth(accessToken))
        .retrieve()
        .bodyToMono(Product.class);
~~~

Do not store a user's token in defaultHeader of a singleton WebClient shared by multiple users. Use token relay or the security context properly, and ensure tokens never appear in logs.

### 10.4. SSRF and Target URL Control

If users can input a URL and the backend uses WebClient to call that URL, the application can be abused for SSRF. Control scheme, hostname, port, and path using an allowlist; consider blocking loopback, private IPs, link-local, and metadata endpoints depending on the use case.

Do not rely solely on checking the hostname string before DNS resolution; consider DNS rebinding and redirects. Never let users directly control the connector's proxy or credentials.

## 11. Error Handling, Retry, and Cancellation

### 11.1. HTTP Status Is Not a Transport Error

There are two distinct error groups:

- **Transport error:** DNS, connection refused, TLS failure, connect/read timeout, socket reset.
- **HTTP response error:** server returns 400, 401, 404, 429, or 500.

A 404 response is still a completed HTTP exchange at the transport layer. retrieve() by default turns 4xx/5xx statuses into WebClientResponseException; exchangeToMono allows custom status handling.

### 11.2. Conditional Retry

~~~java
Mono<Product> product = client.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .filter(error ->
                        error instanceof WebClientRequestException));
~~~

This example only retries request/transport errors, not every 4xx/5xx. In production, you need retry limits, jitter, timeouts, and metrics.

Do not blindly retry POST requests that create orders or payments. If the request reached the server but the response was lost, retrying can create duplicate side effects. Use an idempotency key or deduplication contract if business rules allow retries.

### 11.3. Cancellation

If the caller cancels the subscription, cancellation propagates down to WebClient and the connector. The transport can abort the request/response reading and release the corresponding resources.

Do not call subscribe() on your own inside a service if the caller needs lifecycle control. Return Mono/Flux so the controller, scheduler, or owning component decides subscription.

## 12. Observability: Metrics, Tracing, and Logging

WebClient can integrate with ObservationRegistry/Micrometer to record HTTP client observations. When metrics/tracing are properly enabled, you can observe:

- Request count and status.
- Latency.
- Connection pool active/idle/pending.
- Connection errors, timeouts, and retries.
- Upstream service name.
- Trace/span ID to link requests across multiple services.

Do not use full URLs or unique IDs as metric tags if doing so causes high cardinality. Never log tokens, cookies, or sensitive bodies.

You can use ExchangeFilterFunction to add a business correlation ID, but the tracing framework should manage trace/span lifecycles instead of manually generating independent trace IDs for every request.

## 13. Runnable Project: Java 17+ and Spring Boot 3.5.16

This example creates a small application with a WebClient calling a catalog upstream. To run without Internet access:

- The application exposes the demo endpoint /mock-upstream/products/{id}.
- CatalogClient uses WebClient and ClientHttpConnector to call that endpoint over real HTTP.
- The endpoint /catalog/products/{id} returns the upstream result.
- Integration tests use MockWebServer to verify requests/responses through a real connector.

The learning point is that the WebClient API stays the same while the connector decides the transport. The demo application uses the Reactor Netty connector and a configured pool.

### 13.1. Project Structure

~~~text
webclient-connector-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/example/client/
    │   │   ├── DemoApplication.java
    │   │   ├── Product.java
    │   │   ├── WebClientConfiguration.java
    │   │   ├── CatalogClient.java
    │   │   ├── CatalogController.java
    │   │   └── MockUpstreamController.java
    │   └── resources/application.yml
    └── test/java/example/client/
        └── CatalogClientIntegrationTest.java
~~~

### 13.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
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
~~~

spring-boot-starter-webflux provides WebClient, Reactor Netty, and WebFlux. spring-boot-starter-test provides JUnit 5, AssertJ, and Spring test. MockWebServer creates a simulated HTTP upstream to test real transport without calling external services.

### 13.3. DemoApplication.java

~~~java
package example.client;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 13.4. Product.java

~~~java
package example.client;

public record Product(String id, String name) {
}
~~~

### 13.5. WebClientConfiguration.java

~~~java
package example.client;

import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.reactive.ClientHttpConnector;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
public class WebClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogConnectionProvider() {
        return ConnectionProvider.builder("catalog-pool")
                .maxConnections(50)
                .pendingAcquireTimeout(Duration.ofSeconds(2))
                .maxIdleTime(Duration.ofSeconds(20))
                .maxLifeTime(Duration.ofMinutes(5))
                .build();
    }

    @Bean
    ClientHttpConnector catalogConnector(
            ConnectionProvider catalogConnectionProvider) {

        HttpClient httpClient = HttpClient
                .create(catalogConnectionProvider)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3000)
                .responseTimeout(Duration.ofSeconds(5));

        return new ReactorClientHttpConnector(httpClient);
    }

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            ClientHttpConnector catalogConnector,
            Environment environment) {

        String baseUrl =
                environment.getRequiredProperty("catalog.base-url");

        return builder.clone()
                .baseUrl(baseUrl)
                .clientConnector(catalogConnector)
                .defaultHeader(
                        HttpHeaders.ACCEPT,
                        MediaType.APPLICATION_JSON_VALUE)
                .build();
    }
}
~~~

Explanation:

- ConnectionProvider manages a dedicated pool for the catalog upstream.
- CONNECT_TIMEOUT_MILLIS limits the time to establish a connection.
- responseTimeout sets the response read limit according to Reactor Netty.
- ReactorClientHttpConnector bridges HttpClient with Spring's abstraction.
- WebClient.Builder remains responsible for base URL, headers, codecs, and the request API.
- destroyMethod dispose releases the pool when the Spring ApplicationContext closes.

In large applications, consider splitting pools by upstream or SLA group. Do not create a new pool for each request.

### 13.6. CatalogClient.java

~~~java
package example.client;

import org.springframework.stereotype.Component;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient catalogWebClient) {
        this.webClient = catalogWebClient;
    }

    public Mono<Product> findById(String id) {
        return webClient.get()
                .uri("/products/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .exchangeToMono(response -> {
                    if (response.statusCode().is2xxSuccessful()) {
                        return response.bodyToMono(Product.class);
                    }

                    if (response.statusCode().value() == 404) {
                        return response.releaseBody()
                                .then(Mono.empty());
                    }

                    return response.createError();
                });
    }
}
~~~

CatalogClient handles the response according to business rules:

- 2xx: decodes JSON into Product.
- 404: releases the body and returns Mono.empty().
- Other statuses: emits WebClientResponseException via createError().

The connector does not decide that 404 means Mono.empty(); that is CatalogClient's policy.

### 13.7. CatalogController.java

~~~java
package example.client;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class CatalogController {

    private final CatalogClient catalogClient;

    public CatalogController(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @GetMapping("/catalog/products/{id}")
    public Mono<ResponseEntity<Product>> find(
            @PathVariable String id) {

        return catalogClient.findById(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(
                        ResponseEntity.<Product>notFound().build());
    }
}
~~~

The controller only composes the Mono and converts the result into the application's HTTP response. It never calls block().

### 13.8. MockUpstreamController.java

~~~java
package example.client;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/mock-upstream")
public class MockUpstreamController {

    @GetMapping("/products/{id}")
    public Mono<ResponseEntity<Product>> find(
            @PathVariable String id) {

        if ("p-1".equals(id)) {
            return Mono.just(ResponseEntity.ok(
                    new Product("p-1", "Keyboard")));
        }

        return Mono.just(
                ResponseEntity.<Product>notFound().build());
    }
}
~~~

This is an in-process simulated upstream so the demo works without Internet access. In production, the base URL will point to the real catalog service and this mock endpoint should be removed from deployment.

### 13.9. application.yml

~~~yaml
server:
  port: 8080

catalog:
  base-url: http://localhost:8080/mock-upstream
~~~

By default the application runs on port 8080 and WebClient calls the mock-upstream endpoint over HTTP. Tests will override catalog.base-url with the MockWebServer address.

### 13.10. CatalogClientIntegrationTest.java

~~~java
package example.client;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class CatalogClientIntegrationTest {

    private static final MockWebServer UPSTREAM = startUpstream();

    private static MockWebServer startUpstream() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        } catch (IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    @DynamicPropertySource
    static void catalogProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "catalog.base-url",
                () -> UPSTREAM.url("/").toString());
    }

    @Autowired
    WebTestClient webTestClient;

    @AfterAll
    static void stopUpstream() throws IOException {
        UPSTREAM.shutdown();
    }

    @Test
    void forwardsRequestAndDecodesProduct() throws Exception {
        UPSTREAM.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("""
                        {"id":"p-1","name":"Keyboard"}
                        """));

        webTestClient.get()
                .uri("/catalog/products/p-1")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("p-1")
                .jsonPath("$.name").isEqualTo("Keyboard");

        RecordedRequest request =
                UPSTREAM.takeRequest(1, TimeUnit.SECONDS);

        assertThat(request).isNotNull();
        assertThat(request.getMethod()).isEqualTo("GET");
        assertThat(request.getPath()).isEqualTo("/products/p-1");
        assertThat(request.getHeader("Accept"))
                .contains("application/json");
    }

    @Test
    void mapsUpstream404ToEmptyAndApplication404() throws Exception {
        UPSTREAM.enqueue(new MockResponse()
                .setResponseCode(404)
                .setBody("not found"));

        webTestClient.get()
                .uri("/catalog/products/missing")
                .exchange()
                .expectStatus().isNotFound();

        RecordedRequest request =
                UPSTREAM.takeRequest(1, TimeUnit.SECONDS);

        assertThat(request).isNotNull();
        assertThat(request.getPath())
                .isEqualTo("/products/missing");
    }
}
~~~

The two tests cover two layers:

1. WebTestClient sends a request into the application via a mock WebFlux exchange.
2. CatalogClient performs real HTTP network I/O via ReactorClientHttpConnector to MockWebServer.
3. MockWebServer records the method, path, and Accept header.
4. The Spring codec decodes JSON into Product.
5. Status 404 is converted by CatalogClient into Mono.empty(), after which the controller returns 404.

This is an integration test of WebClient/connector and the Spring context, though the inbound request from WebTestClient is still a mock exchange; the outbound call to MockWebServer is real HTTP.

### 13.11. Running the Project

In the directory containing pom.xml:

~~~bash
mvn test
~~~

Start the application:

~~~bash
mvn spring-boot:run
~~~

Retrieve an existing product:

~~~bash
curl -i http://localhost:8080/catalog/products/p-1
~~~

Response body:

~~~json
{"id":"p-1","name":"Keyboard"}
~~~

Non-existent product:

~~~bash
curl -i http://localhost:8080/catalog/products/missing
~~~

The result is HTTP 404. This is the controller's behavior after CatalogClient receives 404 from the mock upstream.

If tests use MockWebServer, the expected result is:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is the expected result when tests pass, not the stdout of an actual Maven run. Run mvn test in the project to verify on your environment.

## 14. When Should You Change the Connector?

Do not switch connectors just to "speed things up." Before changing, identify where the problem lies:

- Is the pool exhausted because maxConnections is too low?
- Are requests waiting on the pool too long due to pending acquire?
- Is DNS or TCP connect slow?
- Is the TLS handshake slow?
- Is the server responding slowly?
- Is the codec aggregating an overly large body?
- Is a filter reading the body twice?
- Is the upstream rate-limiting?
- Is the event loop blocked by application code?

The connector is one part of the request path. Changing the connector can change the resource model, timeouts, proxy, TLS, and metrics; it does not automatically fix slow queries, slow servers, or bad retry policies.

### 14.1. Signs You Need to Tune the Pool

- Pending acquires increase continuously.
- Active connections frequently hit maxConnections.
- Latency increases as concurrency increases.
- Many requests wait to acquire a connection even though the upstream responds quickly.

Increasing the pool can raise load on the upstream and consume sockets/file descriptors. Coordinate with upstream quotas, instance count, and actual client count.

### 14.2. Signs You Need to Check Timeouts

- Connection refused or DNS failure: check connect timeout and network.
- Slow TLS handshake: check certificate chain, proxy, and TLS setup.
- Slow responses: check upstream, response timeout, and tracing.
- Long-running streaming responses: do not use a short overall timeout as if it were a small JSON request.
- Pool acquire timeout: check connection saturation and pending queue.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking WebClient opens sockets itself | Misunderstanding the transport's role | Check which ClientHttpConnector is in use |
| Thinking ClientHttpConnector decodes JSON | Mixing transport with codecs | Use HttpMessageReader/Writer and ExchangeStrategies |
| Creating a WebClient per request | Inability to share pools/resources effectively | Use a long-lived WebClient bean |
| Thinking changing connectors has no operational impact | Timeouts, pools, TLS, and metrics change | Test the transport and manage resources |
| Using Reactor Netty ChannelOption for the JDK connector | Wrong abstraction configuration | Use the underlying HTTP client's API |
| Not disposing custom ConnectionProvider | Resource leaks on context restarts | Manage lifecycle with a Spring bean |
| Creating unnecessary multiple event loops/pools | Wastes threads, memory, and sockets | Share global resources or a resource factory |
| Raising maxConnections without load testing | Overloads the upstream | Measure pending/active pool metrics and upstream quotas |
| Using one timeout for all request types | Cuts off valid streams or waits too long | Separate connect, response, idle, and overall timeouts |
| Using retrieve() without handling status | 4xx/5xx become WebClientResponseException | Use onStatus or exchangeToMono |
| Reading response body in a filter without reconstructing it | Downstream consumers lose the body | Avoid consuming or clone/rebuild the response properly |
| Aggregating large files into byte[] | Increases heap usage and risks OOM | Stream DataBuffer/Flux |
| Disabling TLS certificate validation | Opens the door to MITM | Configure trust store properly |
| Logging Authorization/Cookie | Credential leakage | Redact headers and bodies |
| Retrying non-idempotent POST | Creates duplicate side effects | Use idempotency keys and retry policies |
| Calling block() on the event loop | Blocks processing of other requests | Compose Mono/Flux |
| Calling subscribe() inside a service | Loses cancellation/error ownership | Return the Publisher to the caller |
| Letting users enter arbitrary target URLs | Risk of SSRF | Allowlist scheme/host/port/path |
| Thinking mock WebTestClient checks the connector | No inbound network I/O | Use MockWebServer or live HTTP integration tests |

## 16. WebClient and Connector Review Checklist

Before taking a client to production:

1. Is WebClient reused as a bean instead of created per request?
2. Which connector is Spring Boot auto-selecting on the classpath?
3. Do you need to override the connector for proxy, TLS, pooling, or protocol reasons?
4. Does the connector use an appropriate resource lifecycle?
5. Does the connection pool have appropriate maxConnections and pendingAcquireTimeout?
6. Are connect, response, read/write, and overall timeouts separated?
7. Is codec maxInMemorySize suitable for response sizes?
8. Are large files streamed instead of aggregated?
9. Do filters avoid reading the response body twice?
10. Are Authorization headers and cookies protected from logs?
11. Are TLS certificate/hostname verification kept enabled?
12. Are target URLs controlled to prevent SSRF?
13. Do retries have appropriate limits and idempotency?
14. Are 4xx/5xx error statuses mapped according to the business contract?
15. Do metrics observe pool, latency, status, and timeouts?
16. Do tests verify method, URI, headers, body, and transport behavior?
17. Are custom resources closed when the ApplicationContext stops?

## 17. Key Takeaways

- WebClient is a fluent reactive HTTP API; ClientHttpConnector is the adapter to the HTTP client transport.
- The connector contract takes method, URI, and a request callback, and returns Mono<ClientHttpResponse>.
- WebClient handles request/response semantics, filters, and codecs; the connector performs transport I/O.
- Spring supports Reactor Netty, JDK HttpClient, Jetty Reactive HttpClient, and Apache HttpComponents.
- Spring Boot 3.5 auto-detects connectors by dependency, prioritizing Reactor Netty, Jetty, Apache, then JDK.
- Use Boot's builder bean to retain codec, connector, and observation configuration; clone the builder when independent variants are needed.
- ReactorClientHttpConnector can accept an HttpClient configured with pool, timeouts, TLS, and proxy.
- ConnectionProvider and event-loop resources must be properly shared and lifecycle-managed.
- Separate connect timeout, response timeout, read/write timeout, and Mono.timeout.
- Codec maxInMemorySize protects memory; stream large responses instead of aggregating.
- Filters are suited for tracing, auth headers, metrics, and metadata logging.
- retrieve() fits simple flows; exchangeToMono fits custom status/body handling.
- HTTP status errors differ from transport errors; retries must consider idempotency.
- Test connectors with MockWebServer or live HTTP; do not infer network behavior from mock exchanges.

**Official documentation:**
- [Spring Framework 6.2 — WebClient](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html)
- [Spring Framework 6.2 — WebClient Configuration, Client Connector, Resources and Timeouts](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html)
- [Spring Framework 6.2 — ClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/reactive/ClientHttpConnector.html)
- [Spring Framework 6.2 — ReactorClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/reactive/ReactorClientHttpConnector.html)
- [Spring Framework 6.2 — JdkClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/reactive/JdkClientHttpConnector.html)
- [Spring Framework 6.2 — JettyClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/reactive/JettyClientHttpConnector.html)
- [Spring Framework 6.2 — HttpComponentsClientHttpConnector Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/client/reactive/HttpComponentsClientHttpConnector.html)
- [Spring Boot 3.5 — Calling REST Services and WebClient Runtime](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html)
- [Spring Boot 3.5.16 — ClientHttpConnectorBuilder Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/http/client/reactive/ClientHttpConnectorBuilder.html)
