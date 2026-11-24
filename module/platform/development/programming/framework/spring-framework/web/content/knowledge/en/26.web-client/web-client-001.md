# WebClient.Builder, ClientHttpConnector, and Underlying HTTP Libraries

## 1. Goals and Big Picture

`WebClient` is the HTTP client in Spring WebFlux: applications use it to call external APIs using the reactive model, typically returning `Mono<T>` (0–1 element) or `Flux<T>` (multiple elements). Three key layers of responsibility should be separated:

- **`WebClient.Builder`** configures the client API at the Spring level: base URL, default headers/cookies, filters, codecs, connector, and observability; `build()` creates a reusable `WebClient`.
- **`ClientHttpConnector`** is Spring's connection contract (`org.springframework.http.client.reactive.ClientHttpConnector`). It bridges WebClient with the actual HTTP library and turns send/receive operations into reactive `ClientHttpRequest`/`ClientHttpResponse` instances.
- **The underlying HTTP library (transport/engine)** performs the actual I/O: TCP/TLS, proxy, connection pool, event loop or executor, timeouts, and HTTP/1.1–HTTP/2 depending on engine capabilities and configuration.

Simplified flow:

```text
Application code
  → WebClient (URI, headers, filters, encoder/decoder)
    → ExchangeFunction
      → ClientHttpConnector
        → Reactor Netty / JDK HttpClient / Jetty / Apache HttpComponents
          → HTTP(S) network and target server
```

**Key takeaway:** `WebClient.Builder` determines *how the client is configured*; `ClientHttpConnector` determines *which transport is used*; the engine determines *how connections and I/O behave*. Choosing a connector does not replace the JSON codec, and increasing codec limits does not change the connect timeout.

## 2. When to Use It and What Dependencies Are Needed?

WebClient fits asynchronous HTTP calls, reactive processing pipelines, calling multiple services, or streaming data. You can use it in a Spring MVC application, but you must never call `block()` on a WebFlux/Reactor Netty event loop thread. For applications that only need a synchronous API, `RestClient` may be simpler.

At minimum, you need Spring WebFlux (`org.springframework:spring-webflux`), Project Reactor, and a compatible HTTP transport. In a Spring Boot application, `spring-boot-starter-webflux` is the standard way to get WebClient together with Reactor Netty. If the project already has a version manager (Spring Boot BOM), let the BOM select compatible versions. Do not randomly mix different generations of Spring, Reactor, Netty, Jetty, or HttpComponents.

| Engine | Spring Connector | Best Fit | Notes |
| --- | --- | --- | --- |
| Reactor Netty | `ReactorClientHttpConnector` | Common choice for WebFlux apps; strong event loop and pooling | Requires `reactor-netty-http`; configured via `reactor.netty.http.client.HttpClient` |
| Java JDK HttpClient | `JdkClientHttpConnector` | Want to use `java.net.http.HttpClient` built into modern JDKs | Does not mean dropping Reactor at the WebClient API layer |
| Jetty | `JettyClientHttpConnector` | System already uses Jetty or needs Jetty client customization | Requires the appropriate Jetty Reactive HTTP client library and lifecycle management |
| Apache HttpComponents | `HttpComponentsClientHttpConnector` | Standardized on Apache HttpClient 5 async | Use the **async** client and corresponding Apache dependencies |

Spring Boot can auto-detect a connector based on the classpath; in Boot versions supporting the options above, the typical precedence is Reactor Netty → Jetty → Apache → JDK. **That is Boot's auto-configuration behavior**, and should not be assumed as a fixed contract across all Spring Framework versions or plain `WebClient.builder()`. When a specific transport is required, configure it explicitly.

## 3. WebClient.Builder: Application Configuration

Example inside a Spring application with WebFlux:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class CatalogClientConfig {

    @Bean
    WebClient catalogClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.example.org")
                .defaultHeader("Accept", MediaType.APPLICATION_JSON_VALUE)
                .defaultHeader("X-Client", "spring-learning")
                .codecs(config -> config.defaultCodecs()
                        .maxInMemorySize(1024 * 1024))
                .build();
    }
}
```

The snippet above configures a Spring bean using `WebClient.Builder`; the host `catalog.example.org` is only an illustrative address, not a live test endpoint. Key components:

- `baseUrl(...)` serves as the root for relative URIs, e.g., `.uri("/books/{id}", 7)`. An absolute URI can override the base URL. Manage slashes/paths intentionally, especially when the base URL includes a path.
- `defaultHeader(...)` and `defaultCookie(...)` provide default values; headers on an individual request can be configured separately.
- `defaultUriVariables(...)` and `uriBuilderFactory(...)` define URI expansion, encoding rules, and URI variables; never concatenate unvalidated input directly into a URL.
- `defaultRequest(...)` customizes every request; `filter(...)` adds an `ExchangeFilterFunction` for cross-cutting concerns such as correlation IDs, authentication, timing, and error handling.
- `codecs(...)` / `exchangeStrategies(...)` adjust body encoders/decoders; `maxInMemorySize` relates to *in-memory content buffer* size, not connection pool capacity.
- `clientConnector(...)` attaches a configured transport directly; `observationRegistry(...)` supports metrics/tracing when needed.

**Mutability:** The builder is **mutable/stateful**; calling `defaultHeader`/`filter` on the same builder affects clients `build()` produces afterward. A built WebClient is designed to be immutable and safe to share across threads; using `webClient.mutate().filter(...).build()` creates a **new** client without modifying the old one. If you need multiple configurations derived from a shared builder, consider `builder.clone()`. Do not create a new WebClient per request.

**In Spring Boot:** inject the Boot auto-configured `WebClient.Builder` to inherit configured codecs, HTTP resources, customizers, and observability. Boot typically provides a prototype-scoped builder, though each builder instance itself remains mutable. Calling `WebClient.create()` or `WebClient.builder()` directly will not automatically pick up all Boot customizations.

Example of mutating a client while preserving the original:

```java
WebClient publicApi = WebClient.builder()
        .baseUrl("https://example.org")
        .build();

WebClient privateApi = publicApi.mutate()
        .defaultHeader("X-Api-Version", "2")
        .build();
// publicApi keeps the original configuration; privateApi adds the default header.
```

## 4. How Does ClientHttpConnector Work?

The `ClientHttpConnector` interface defines a low-level operation shaped like:

```java
Mono<ClientHttpResponse> connect(
        HttpMethod method,
        URI uri,
        Function<? super ClientHttpRequest, Mono<Void>> requestCallback);
```

This signature is an **API excerpt to understand the contract**, not a standalone runnable program. WebClient invokes the connector through the exchange layer when a request is subscribed to. The connector prepares the native HTTP request, lets the callback write headers/body, sends it through the engine, and adapts the response back to Spring's reactive types.

The connector does **not** decide how JSON DTOs are serialized, how business errors are mapped, or what retry policy applies. Those belong to WebClient codecs, filters, and the Reactor pipeline. Errors can originate at different layers:

- URI construction or codec errors: typically from application code or data.
- `WebClientResponseException`: the HTTP server returned a 4xx/5xx error status under default `retrieve()`.
- `WebClientRequestException`: I/O/transport, DNS, connection, TLS, etc., failures before a valid HTTP response is received.
- `DataBufferLimitException`: the buffered body exceeds the decoder limit; increase `maxInMemorySize` only with good reason, and consider streaming for large payloads.

## 5. Configuring Reactor Netty: Pooling, Connect Timeout, and Response Timeout

`ReactorClientHttpConnector` is a familiar choice. With Reactor Netty, you can configure `HttpClient` first and pass it into the Builder:

```java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
class PaymentsHttpConfig {

    @Bean
    WebClient paymentsClient(WebClient.Builder builder) {
        ConnectionProvider pool = ConnectionProvider.builder("payments-pool")
                .maxConnections(100)
                .pendingAcquireTimeout(Duration.ofSeconds(2))
                .build();

        HttpClient httpClient = HttpClient.create(pool)
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
                .responseTimeout(Duration.ofSeconds(5));

        return builder
                .baseUrl("https://payments.example.org")
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
```

This is a **Spring bean configuration example**, not a request sent to the example host. In production systems, you must **manage the lifecycle of custom `ConnectionProvider` instances** (dispose on application shutdown) and avoid creating unbounded per-request or per-bean pools. For many Spring Boot applications, letting clients use the shared, Boot-managed Reactor Netty resources is even more appropriate; only isolate pools when independent limits between upstreams are needed. If using `ReactorResourceFactory` with custom resources, tie its lifecycle to the `ApplicationContext`.

Distinguishing timeouts:

| Setting | Meaning | Example |
| --- | --- | --- |
| `CONNECT_TIMEOUT_MILLIS` (Netty) | Time limit to establish the TCP connection | 3 seconds |
| `pendingAcquireTimeout` (pool) | Wait time to acquire a connection when the pool is busy | 2 seconds |
| `responseTimeout` (Reactor Netty) | Transport-level response processing/read timeout as defined by the engine | 5 seconds |
| `Mono.timeout(Duration)` | Time limit on the **publisher** using the Reactor clock; does not replace socket/pool settings | `.timeout(Duration.ofSeconds(8))` |

Timeouts do not guarantee that total wall-clock time from invocation to result is a fixed sum. DNS, TLS, streaming, and retries each have distinct characteristics. Configure clear timeout budgets aligned with your SLA, measure them, and handle failures. For long-lived streams (SSE), an overly short fixed timeout can cut off valid connections.

**Do not confuse `reactor.netty.http.client.HttpClient` with `java.net.http.HttpClient`**: they are two different types meant for two different connectors.

## 6. Switching Engines to JDK HttpClient

When you need the JDK HTTP engine, you do not have to rewrite API call code; swap the connector:

```java
import java.net.http.HttpClient;
import java.time.Duration;

import org.springframework.http.client.reactive.JdkClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

HttpClient jdk = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();

WebClient client = WebClient.builder()
        .baseUrl("https://example.org")
        .clientConnector(new JdkClientHttpConnector(jdk))
        .build();
```

This is a Java 17+ configuration snippet in a project with Spring WebFlux; the client only performs I/O when a request is called and subscribed to. The JDK client has its own configuration rules for timeouts, proxies, SSL, and redirects; you cannot transplant Netty's `ChannelOption` or `ConnectionProvider` to the JDK client. Choose a connector based on operational requirements, environment, compatibility, and real benchmarks rather than assuming one connector is always faster than another.

## 7. Full Runnable Example: Local HTTP Server → WebClient → Reactor Netty

The following standalone example demonstrates attaching a connector to the Builder and actually receiving HTTP data, **without depending on the Internet**. Using Gradle with Java 17+, project structure:

```text
build.gradle
src/main/java/demo/WebClientDemo.java
```

`build.gradle` (Groovy DSL; uses a BOM to align versions):

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework:spring-webflux'
    implementation 'io.projectreactor.netty:reactor-netty-http'
}

application {
    mainClass = 'demo.WebClientDemo'
}
```

`src/main/java/demo/WebClientDemo.java`:

```java
package demo;

import com.sun.net.httpserver.HttpServer;
import io.netty.channel.ChannelOption;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

public final class WebClientDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/hello", exchange -> {
            byte[] data = "Hello WebClient".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, data.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(data);
            }
        });
        server.start();

        try {
            HttpClient transport = HttpClient.create()
                    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
                    .responseTimeout(Duration.ofSeconds(3));

            WebClient webClient = WebClient.builder()
                    .baseUrl("http://127.0.0.1:"
                            + server.getAddress().getPort())
                    .clientConnector(
                            new ReactorClientHttpConnector(transport))
                    .defaultHeader("X-Lesson", "webclient")
                    .build();

            String result = webClient.get()
                    .uri("/hello")
                    .retrieve()
                    .bodyToMono(String.class)
                    .block(Duration.ofSeconds(5)); // only in main demo

            System.out.println(result);
        } finally {
            server.stop(0);
        }
    }
}
```

Run with Gradle inside the example directory:

```bash
./gradlew run
```

On Windows PowerShell use `.\gradlew.bat run`; this requires an existing Gradle wrapper, or use `gradle run` if Gradle is installed. The stdout printed by the program itself is **exact**:

```text
Hello WebClient
```

Gradle and library logging may print additional lines of their own. The JDK HTTP server opens a random port on loopback, avoiding reliance on public APIs, and shuts down when finished. The result is received when `block(...)` subscribes to the publisher; **do not use `block()` in a WebFlux request handler running on the event loop**.

If building the Java project using the module path instead of the traditional classpath, you may need to declare the `jdk.httpserver` module; the Gradle example above uses the regular classpath.

## 8. Using the Configured Client

Suppose we have a `WebClient catalogClient` pointing to an API returning JSON. Java record DTO:

```java
record Book(long id, String title) {}
```

Example query and status handling:

```java
import org.springframework.http.HttpStatusCode;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

// Placed inside a method/service that receives catalogClient from Spring.
Mono<Book> request = catalogClient.get()
        .uri("/books/{id}", 42)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                response -> response.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .map(body -> new IllegalArgumentException(
                                "Book 42 not found: " + body)))
        .bodyToMono(Book.class);

return request;
```

This is a **fragment inside a method returning `Mono<Book>`**, not a standalone Java file. When returning it in a Java service, place the record in the appropriate package/scope. By default, `retrieve()` turns HTTP 4xx/5xx into `WebClientResponseException`; `onStatus(...)` customizes specific cases. When you need to inspect status/headers/body together, look at `exchangeToMono` / `exchangeToFlux` and make sure to consume or release the response body properly.

Calling `get().uri(...).retrieve().bodyToMono(...)` only **creates a publisher**; it requires a WebFlux-managed subscriber, `subscribe()` at an appropriate application boundary, or `block()` in a synchronous/demo program to actually execute I/O. In a WebFlux controller, return the `Mono` directly so the runtime subscribes; do not manually call `subscribe()` per request and drop error signals.

### Filters: Cross-Cutting Logic Across Requests

```java
WebClient client = WebClient.builder()
        .filter((request, next) -> {
            // Do not log Authorization, Cookie, or sensitive body.
            System.out.println("HTTP " + request.method()
                    + " " + request.url().getPath());
            return next.exchange(request);
        })
        .build();
```

Filters execute as a chain; registration order can affect authentication, retries, and logging. If a filter reads the response itself, it must handle/release the body properly; if it simply passes `ClientResponse` along, let WebClient consume it. Do not install a filter that logs full URLs when query strings contain secrets or personal data.

## 9. Operations and Common Pitfalls

1. **Adding only `spring-webflux` without a compatible HTTP engine:** at runtime the desired connector may not be found or expected engine features may be missing. Check the dependency tree and actual connector, especially after excluding Netty.
2. **Thinking `build()` sends a request:** `build()` only creates the client; the Reactive pipeline executes upon subscription.
3. **Mutating a shared builder later:** configuration "leaks" into other clients built afterward; clone the builder or create stable client beans.
4. **Creating an `HttpClient`/pool per request:** causes connection/thread/resource churn. Reuse WebClient and manage pool/event loop lifecycles.
5. **Blocking the event loop with `block()` or blocking I/O inside `map`:** destroys throughput and can trigger `IllegalStateException`; keep the pipeline non-blocking or offload blocking work to an appropriate scheduler when truly needed.
6. **Confusing HTTP 500 with a connect error:** 500 is a server response, whereas connect/DNS/TLS are transport errors; apply different retry policies and be careful with non-idempotent POSTs.
7. **Setting only `Mono.timeout`:** that does not change the engine's connect/pool/response timeouts, nor does it establish a retry policy.
8. **Increasing `maxInMemorySize` indefinitely upon `DataBufferLimitException`:** risks excessive memory growth; for large responses, prefer streaming `Flux<DataBuffer>`/`Flux<T>` and release buffers when handling them manually.
9. **Disabling TLS verification to "fix" certificates:** unsafe. Configure trust stores/certificates properly and follow proxy policies.
10. **Using user input as an arbitrary URL:** opens SSRF risks; restrict host/scheme/IP against policy before sending. Never write tokens or sensitive data to logs.
11. **Configuring a custom connector and forgetting auto-configuration:** changes to resources/SSL/metrics or customizers may no longer flow through Boot configuration as expected. Verify with integration tests and actual configuration.

### Production Readiness Checklist

- Identify the actual engine/connector on the classpath and how Boot initializes it.
- Use the Spring Boot-provided `WebClient.Builder` to inherit shared configuration; keep clients as reusable beans.
- Define connect, pending acquire, response, and end-to-end timeouts aligned with your SLA.
- Size pools according to upstream count and load; manage shutdown for self-created resources.
- Bound codecs/buffering, and test behavior with large responses and streaming.
- Handle 4xx/5xx, transport errors, and conditional retries; avoid retrying requests with side effects when idempotency is lacking.
- Verify HTTPS, proxies, certificates, secret headers, logging, metrics/tracing, and SSRF controls.

## 10. Knowledge Check

**Question 1.** Does increasing `maxInMemorySize` fix a connect timeout error?  
**Answer:** No. That is a body buffer limit at the codec layer; connect timeouts belong to the transport layer.

**Question 2.** Why can two WebClients created from the same `WebClient.Builder` end up with different configurations?  
**Answer:** The builder is mutable; each `build()` snapshots its current configuration. Use `clone()` or separate builders if you want independent configuration branches.

**Question 3.** To switch from Reactor Netty to JDK HttpClient, must you rewrite all `get()/retrieve()/bodyToMono()` code?  
**Answer:** No. Swap the `ClientHttpConnector` (and engine configuration). The application-facing WebClient API remains largely unchanged.

**Question 4.** Why shouldn't you call `block()` inside a WebFlux controller?  
**Answer:** It blocks an event loop thread handling many requests, defeating non-blocking benefits and risking rejection by Reactor. Return `Mono`/`Flux` to the runtime.

## Official Documentation

- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [Spring Framework — WebClient Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html)
- [Spring Framework — retrieve() and Error Handling](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html)
- [Spring Boot — Calling REST Services / WebClient](https://docs.spring.io/spring-boot/reference/io/rest-client.html)
