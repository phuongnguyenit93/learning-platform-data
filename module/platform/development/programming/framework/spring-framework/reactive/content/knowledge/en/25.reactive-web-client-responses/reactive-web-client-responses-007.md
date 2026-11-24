# Distinguishing connection, timeout, codec, and status errors when reading WebClient responses

## 1. Identifying which layer the error comes from

`WebClient` is Spring WebFlux's reactive HTTP client. A request can fail at several stages:

~~~text
Application calls WebClient
        |
        v
  Build request / encode body
        |
        v
  Acquire connection from pool
        |
        v
  DNS -> TCP connect -> TLS
        |
        v
  Send request to server
        |
        v
  Receive HTTP status + headers
        |
        v
  Read response body
        |
        v
  Codec decodes bytes into DTO
        |
        v
  Application receives result
~~~

Four categories to distinguish:

1. **Connection/transport error**: the client failed to establish or maintain the HTTP exchange; usually no complete HTTP response was received.
2. **Timeout**: a stage such as waiting for a connection, connecting, TLS, or reading the response exceeded its allowed duration.
3. **Codec error**: a response/body arrived, but Spring could not read or convert the bytes into the Java type requested by the application.
4. **HTTP status error**: the server or gateway returned an error-class status, typically 4xx or 5xx.

A crucial point is that **HTTP 504 and a client-side timeout are not the same error**. HTTP 504 is an actual response from a gateway. A client-side timeout can happen before receiving any status or while reading the body.

## 2. Quick identification table

| Category | Common signs | Is there an HTTP status? | Examples |
| --- | --- | --- | --- |
| Connection/transport | `WebClientRequestException`, root cause is IOException or network error | Usually no | Connection refused, DNS failure, TLS handshake failure, connection reset |
| Timeout | `TimeoutException`, `ReadTimeoutException`, `ConnectTimeoutException`, `PoolAcquireTimeoutException` | Depends on stage | Waiting on connection pool, connect too slow, response did not arrive in time |
| Codec | `DecodingException`, `CodecException`, `UnsupportedMediaTypeException`, `DataBufferLimitException` | May have received 2xx | Malformed JSON, Content-Type without matching decoder, body exceeds buffer limit |
| HTTP status | `WebClientResponseException` and subclasses | Yes | 400, 401, 404, 429, 500, 503, 504 |

The exception class name is the first clue, not the complete diagnosis. Some Reactor Netty timeouts may sit inside the cause chain of `WebClientRequestException`. Inspect both the outermost exception and the deepest root cause.

## 3. Connection errors: WebClientRequestException

`WebClientRequestException` is Spring's exception for failures related to executing the request. It holds request metadata such as:

- HTTP method.
- URI.
- Request headers.
- Root cause exception, which usually reveals the specific transport failure.

Common causes:

| Root cause / symptom | Meaning |
| --- | --- |
| `UnknownHostException` | DNS failed to resolve the hostname |
| `ConnectException: Connection refused` | Host is reachable, but no service is listening on that port, or a firewall actively rejected it |
| `ConnectTimeoutException` | Failed to establish a TCP connection within the allowed time |
| `SSLException` | TLS/certificate/handshake problem |
| `PrematureCloseException` | Connection closed before the response completed |
| `IOException` | I/O error while sending or receiving data |
| `WebClientRequestException` | Spring wrapper for request execution failures retaining request metadata |

### 3.1. Connection refused differs from HTTP 503

**Connection refused** occurs at the connection layer. The client received no HTTP status from the target service.

**HTTP 503 Service Unavailable** is an HTTP response with status and headers. The server or gateway received the request at some level and actively replied that the service is temporarily unavailable.

The two situations call for different troubleshooting:

- Connection refused: check hostname, port, service process, network route, firewall, container/service discovery, and connection pool.
- HTTP 503: check service health, overload, maintenance, gateway policy, `Retry-After`, and load limits.

Similarly, a gateway returning HTTP 502/504 is still a response with a status. Do not lump them together with the client failing to connect to the gateway.

### 3.2. Reading request metadata and root cause

~~~java
try {
    client.get()
            .uri("/v1/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class)
            .block(Duration.ofSeconds(5));
}
catch (WebClientRequestException ex) {
    log.warn("Request failed: method={}, uri={}, cause={}",
            ex.getMethod(),
            ex.getUri(),
            ex.getMostSpecificCause().getClass().getSimpleName());
    throw ex;
}
~~~

This is an example at a synchronous boundary or in tests. In a reactive service, compose error signals with `doOnError`, `onErrorMap`, or `onErrorResume` instead of calling `block()`.

Do not log all request headers if Authorization, Cookie, or API keys are present. URIs may also contain tokens or personal data in query strings; redact before logging.

## 4. Timeouts: identifying which stage timed out

A WebClient request has multiple timing boundaries. Configuring a single generic timeout can hide the real cause.

### 4.1. Timeout stages

| Stage | Common configuration / exception | Meaning |
| --- | --- | --- |
| DNS | Resolver query timeout; e.g., `UnknownHostException` or resolver error | Failed to resolve IP address in time |
| Connection pool | `pendingAcquireTimeout` / `PoolAcquireTimeoutException` | Could not acquire an idle connection from the pool |
| TCP connect | `CONNECT_TIMEOUT_MILLIS` / `ConnectTimeoutException` | Failed to establish TCP connection in time |
| TLS handshake | `handshakeTimeout` / SSL error | Failed to complete TLS negotiation |
| Response/read | `responseTimeout`, `ReadTimeoutHandler` / read timeout error | Server did not send response data within the allowed window |
| Publisher-level | `Mono.timeout(Duration)` / `TimeoutException` | Reactive operation did not emit a signal within the specified time |

For Reactor Netty, current documentation notes these notable defaults:

- Pending connection acquire timeout: 45 seconds.
- TCP connect timeout: 30 seconds.
- TLS handshake timeout: 10 seconds.
- DNS query timeout: 5 seconds.
- `responseTimeout` is not set by default.

Actual values depend on connector, resolver, and application configuration. If using JDK HttpClient, Jetty, or Apache HttpComponents instead of Reactor Netty, configuration and exceptions may differ.

### 4.2. Configuring connection timeout and response timeout

With Reactor Netty:

~~~java
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
        .responseTimeout(Duration.ofSeconds(5));

WebClient client = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .build();
~~~

- `CONNECT_TIMEOUT_MILLIS` limits the time to establish a TCP connection.
- `responseTimeout` configures the timeout for Reactor Netty's response/read phase.
- Neither configuration is an overall deadline for the entire business operation.

If the application uses a dedicated connection pool, you can configure the wait time to acquire a connection:

~~~java
ConnectionProvider provider = ConnectionProvider.builder("partner-api")
        .maxConnections(50)
        .pendingAcquireTimeout(Duration.ofSeconds(2))
        .build();

HttpClient httpClient = HttpClient.create(provider)
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
        .responseTimeout(Duration.ofSeconds(5));
~~~

Only create a dedicated pool when operationally justified. A bounded connection pool controls concurrency; pending acquire timeout helps requests fail fast when the pool is saturated.

### 4.3. Timeout at the Reactor Publisher level

You can place a deadline on the operation:

~~~java
Mono<Product> product = client.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(8));
~~~

Reactor's `timeout` applies to the Publisher from subscription and covers execution until the next signal arrives. For a single-result `Mono`, this is commonly used as an overall request deadline. For a streaming `Flux`, timeout applies to the interval between signals; it is not necessarily a total duration cap for the whole stream.

Use dedicated connector timeouts for each phase and add a Publisher timeout as an overall cap aligned with SLA. Do not set an overly short timeout and retry aggressively, as that can increase load on an already slow service.

### 4.4. ReadTimeoutHandler and WriteTimeoutHandler

When channel-level read/write control in Netty is needed:

~~~java
HttpClient httpClient = HttpClient.create()
        .doOnConnected(connection -> connection
                .addHandlerLast(new ReadTimeoutHandler(10))
                .addHandlerLast(new WriteTimeoutHandler(10)));
~~~

These handlers are scoped to the channel layer. Understand how they interact with connection pooling and multiple requests sharing a connection before applying globally. For most standard WebClient request/response calls, starting with connect timeout and response timeout is easier to reason about.

### 4.5. HTTP 504 differs from TimeoutException

| Scenario | How to identify |
| --- | --- |
| Gateway returns 504 | `WebClientResponseException.GatewayTimeout` or `WebClientResponseException` with status 504 |
| Reactor timeout | `java.util.concurrent.TimeoutException` |
| Netty read timeout | Usually `ReadTimeoutException` in the cause chain |
| Connect timeout | May have `ConnectTimeoutException` in the cause chain |
| Pool acquire timeout | May have `PoolAcquireTimeoutException` |

If the gateway returns 504, the client received an HTTP response. If Reactor times out before a response arrives, the client has no status to read. This is an important distinction for logging, retries, and SLA measurement.

## 5. Codec errors: response arrived, but the body cannot be decoded

Codecs convert HTTP data into Java types. Example:

~~~java
Mono<Product> product = client.get()
        .uri("/v1/products/{id}", id)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(Product.class);
~~~

Spring selects a decoder based on the target type and the response Content-Type. A request can receive status 200 and still fail while reading the body.

### 5.1. Malformed JSON or mismatched data types

Server returns:

~~~json
{
  "id": "not-a-number",
  "name": "WebFlux"
}
~~~

While the DTO declares:

~~~java
public record Product(long id, String name) {
}
~~~

Jackson cannot convert the string `not-a-number` into a `long`. The failure is represented via `DecodingException` or a related codec exception, depending on the decoder and version.

Check:

- Whether the JSON is valid.
- Whether field names match the contract.
- Whether data types are compatible.
- Whether nullable/missing fields are supported.
- Whether the DTO has constructors/record components/accessors recognized by Jackson.
- Whether the server returned an HTML page or proxy content instead of JSON.

### 5.2. Incompatible Content-Type

For instance, the server returns JSON while declaring `Content-Type: text/plain`, while the client requests `Product.class`. Spring may fail to find a matching decoder and emit `UnsupportedMediaTypeException`.

Distinguish two cases:

- **Client codec cannot read response media type**: a client-side codec error.
- **Server returns HTTP 415 Unsupported Media Type**: an HTTP status response from the server, typically regarding a request media type the server does not accept.

Similarly, HTTP 406 Not Acceptable is a server-returned status when it cannot satisfy the client's requested representation; it is not the same as a client-side JSON decoder failure.

### 5.3. DataBufferLimitException

Spring enforces a buffer limit to prevent loading an overly large response into memory. For default codecs, the default limit is 256 KiB. When a body requiring aggregation exceeds the limit, you may see:

~~~text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
~~~

If the payload is legitimate and business requirements need a larger buffer, you can increase the limit:

~~~java
WebClient client = WebClient.builder()
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(2 * 1024 * 1024))
        .build();
~~~

This configuration raises the limit to 2 MiB for default codecs. Do not raise it indefinitely to hide bugs. For large files, JSON streams, or continuous data, use a streaming API like `bodyToFlux` instead of aggregating the entire response into one object.

### 5.4. Codec error is not a connection error

When the client has received status 200 and headers, yet the JSON is malformed, that is a decode error. The server may still be healthy and the TCP connection intact.

How to investigate:

1. Record the status and response Content-Type.
2. Verify whether the response body adheres to the contract.
3. Check the target DTO and registered decoders.
4. Check buffer limits.
5. Compare the actual body in a test environment against the expected payload.
6. Never log bodies containing tokens, PII, or sensitive data.

## 6. HTTP error statuses: WebClientResponseException

When using `retrieve()`, Spring converts 4xx and 5xx responses into `WebClientResponseException` by default. Several common statuses have dedicated subclasses:

| Status | Common subclass | Meaning |
| --- | --- | --- |
| 400 | `WebClientResponseException.BadRequest` | Invalid request |
| 401 | `WebClientResponseException.Unauthorized` | Missing or invalid authentication |
| 403 | `WebClientResponseException.Forbidden` | Insufficient permissions |
| 404 | `WebClientResponseException.NotFound` | Resource not found |
| 409 | `WebClientResponseException.Conflict` | State conflict |
| 415 | `WebClientResponseException.UnsupportedMediaType` | Server rejects the request media type |
| 429 | `WebClientResponseException.TooManyRequests` | Rate limited |
| 502 | `WebClientResponseException.BadGateway` | Gateway received invalid upstream response |
| 503 | `WebClientResponseException.ServiceUnavailable` | Service temporarily unavailable |
| 504 | `WebClientResponseException.GatewayTimeout` | Gateway did not receive timely upstream response |

This exception holds HTTP response data such as status, headers, and response body. You can read it:

~~~java
catch (WebClientResponseException ex) {
    log.warn("Partner API returned status={}, body={}",
            ex.getStatusCode(),
            redact(ex.getResponseBodyAsString()));
    throw ex;
}
~~~

In production, log only error codes or redacted fields. Never log the raw response body if it may contain tokens, emails, addresses, payment details, or personal data.

### 6.1. Customizing errors with onStatus

`onStatus` lets you map statuses to domain exceptions:

~~~java
Mono<Product> product = client.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> response.createException()
                        .map(ex -> new ProductNotFoundException(id, ex)))
        .onStatus(
                HttpStatusCode::is5xxServerError,
                response -> response.createException())
        .bodyToMono(Product.class);
~~~

This is an illustrative snippet, assuming `ProductNotFoundException` has a constructor taking ID and cause. `response.createException()` builds an exception containing response status, headers, and body.

If the `onStatus` handler returns `Mono.empty()`, the response is treated as normal and body reading continues downstream. Only do this when business logic genuinely treats that status as a normal outcome.

### 6.2. Reading the error body into a DTO

~~~java
public record ApiError(String code, String message) {
}

.onStatus(
        HttpStatusCode::is4xxClientError,
        response -> response.bodyToMono(ApiError.class)
                .defaultIfEmpty(new ApiError(
                        "UNKNOWN", "No error details"))
                .map(error -> new PartnerApiException(
                        response.statusCode(), error)))
~~~

This is an illustrative snippet requiring an application-defined `PartnerApiException` type. Consider cases where the error body is invalid JSON or has the wrong Content-Type: then a decode failure may mask the original status. If you must preserve the status in every situation, call `response.createException()` and read the raw body safely in the exception-handling layer.

## 7. retrieve() or exchangeToMono()?

### 7.1. retrieve(): the default for standard requests

~~~java
Mono<Product> result = client.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class);
~~~

Use when 2xx responses decode into a fixed type and 4xx/5xx are treated as errors by default.

### 7.2. exchangeToMono(): when status dictates how to read the body

~~~java
Mono<Product> result = client.get()
        .uri("/v1/products/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Product.class);
            }

            if (response.statusCode().value() == 404) {
                return Mono.empty();
            }

            return response.createError();
        });
~~~

Use when different statuses require decoding the body into different types or when 404 is an empty result per contract.

After the Publisher returned by the callback completes, Spring inspects the response body. If the callback did not consume the body, Spring releases it to avoid memory and connection leaks. Therefore, do not keep `ClientResponse` intending to read the body later downstream outside the callback.

### 7.3. Do not read the response body twice

The response body is a stream. Once you have read the body into a DTO or String, you cannot assume it can be read again intact. If you need to log the error body, read it once, convert it into the required representation, and continue processing.

## 8. Handling reactive errors without hiding the root cause

### 8.1. onErrorMap: converting exceptions into domain exceptions

~~~java
Mono<Product> result = client.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .onErrorMap(
                WebClientRequestException.class,
                ex -> new PartnerUnavailableException(
                        "Cannot reach partner API", ex));
~~~

Preserve the original cause in the domain exception. Do not construct a new exception solely from a message, as that loses the root cause, stack trace, and metadata needed for investigation.

Reactor Netty timeouts may sit inside `WebClientRequestException`. If you want to classify timeouts separately, inspect the cause chain before converting every request exception into PartnerUnavailable.

### 8.2. onErrorResume: conditional fallback

~~~java
Mono<Product> result = client.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .onErrorResume(
                WebClientResponseException.NotFound.class,
                ex -> Mono.empty());
~~~

Only use a fallback when it reflects business semantics. Do not turn every error into `Mono.empty()`:

~~~java
// Anti-pattern: loses connection, timeout, codec, and status error details.
.onErrorResume(Exception.class, ex -> Mono.empty())
~~~

The snippet above prevents callers from distinguishing a missing resource from a dead service, a timeout, or a corrupted response.

### 8.3. Logging without altering the outcome

~~~java
Mono<Product> result = client.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .doOnError(error ->
                log.warn("Product request failed: type={}",
                        error.getClass().getSimpleName()));
~~~

`doOnError` only observes the error and preserves the error signal. Do not use its side effect to subscribe again or fire a second request.

## 9. Retry: only retry recoverable errors

Not every error should be retried.

| Error category | Should retry? | Reason |
| --- | --- | --- |
| Transient DNS, connection reset, certain transport failures | Possibly | If the cause is transient and the request is safe to repeat |
| Timeout | Possibly | Though the server may have already processed the request before the response was lost |
| HTTP 429 | Possibly | Follow `Retry-After` or the API's backoff policy |
| HTTP 502/503/504 | Possibly | Usually transient gateway/upstream failures |
| HTTP 400/401/403/404/422 | Usually no | Usually requires fixing input, authentication, or permissions |
| Codec/JSON parse error | No | Retrying the same payload usually yields the same error |
| DataBufferLimitException | No | Requires handling size/streaming or buffer configuration |

Bounded retry example for transient statuses:

~~~java
Retry retryPolicy = Retry.backoff(2, Duration.ofMillis(200))
        .filter(error ->
                error instanceof WebClientResponseException response
                && Set.of(502, 503, 504)
                        .contains(response.getStatusCode().value()));

Mono<Product> product = client.get()
        .uri("/v1/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .retryWhen(retryPolicy);
~~~

This is an illustrative example, requiring imports for `reactor.util.retry.Retry` and `java.util.Set`. It only retries specific HTTP statuses; transport timeouts require a separate policy based on the cause chain and operation type.

For POST or create/update operations, a timeout does not prove the server has not processed the request. Retrying may create duplicate data. Only retry when the API supports an idempotency key or guarantees idempotency.

Do not retry indefinitely. Use a small retry count, exponential backoff, jitter, an overall deadline, and concurrency limits. When the server sends `Retry-After`, respect that policy instead of retrying immediately.

## 10. Configuring WebClient for timeouts and codecs

A WebClient can configure connector timeouts and codec limits:

~~~java
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3_000)
        .responseTimeout(Duration.ofSeconds(5));

WebClient client = WebClient.builder()
        .clientConnector(
                new ReactorClientHttpConnector(httpClient))
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .maxInMemorySize(2 * 1024 * 1024))
        .build();
~~~

This configuration caps TCP connect timeout at 3 seconds, sets Reactor Netty response timeout to 5 seconds, and raises the default codec buffer limit to 2 MiB.

In a Spring Boot application, create a WebClient bean per external API, pulling base URLs and timeouts from configuration rather than hardcoding a new client per endpoint. Choose timeouts suited to each service's SLA and payload characteristics.

If the response is large or streaming, prefer:

~~~java
Flux<Event> events = client.get()
        .uri("/v1/events")
        .retrieve()
        .bodyToFlux(Event.class);
~~~

rather than aggregating all data into `Mono<List<Event>>` unnecessarily. This reduces memory pressure and enables backpressure-driven processing.

## 11. Observability: what to log to classify errors?

A useful log entry should include:

- Target service or client name.
- HTTP method.
- Route template or redacted URI.
- Correlation/trace ID.
- Request duration.
- HTTP status if available.
- Exception class and root cause class.
- Timeout phase if identifiable.
- Retry count.
- Response size or payload metadata if needed.

Example:

~~~text
partner-api GET /v1/products/{id} status=503 error=WebClientResponseException
partner-api GET /v1/products/{id} status=none error=WebClientRequestException cause=ConnectException
partner-api GET /v1/products/{id} status=200 error=DecodingException
partner-api GET /v1/products/{id} status=none error=ReadTimeoutException
~~~

Never log Authorization, Cookie, tokens, sensitive query strings, or raw response bodies. When investigating codec issues, use redacted sample payloads in a test environment.

Metrics should separate HTTP status codes, transport failures, timeouts by phase, codec failures, retry counts, latency by service/route, and connection pool pending acquires.

## 12. Runnable Java 17+ program: reproducing all four error categories

The program below starts a local HTTP server using the JDK and calls it with WebClient. No internet access or external APIs are needed.

| Endpoint | Behavior |
| --- | --- |
| `/ok` | Returns valid JSON and HTTP 200 |
| `/status` | Returns JSON and HTTP 503 |
| `/bad-json` | Returns HTTP 200 with malformed JSON |
| `/slow` | Delays the response to reproduce a response timeout |
| Closed port | No listening server, reproducing connection refused |

The program classifies exceptions via their cause chain and asserts expected outcomes.

### 12.1. Project structure

~~~text
webclient-error-demo/
  pom.xml
  src/main/java/example/errors/WebClientErrorDemo.java
~~~

Requirements: **JDK 17+**, **Maven 3.6.3+**, **Spring Boot 4.1.2**. The Boot BOM manages compatible Spring Framework, Reactor Netty, and codec versions.

### 12.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>webclient-error-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 12.3. WebClientErrorDemo.java

~~~java
package example.errors;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeoutException;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import org.springframework.core.codec.CodecException;
import org.springframework.core.codec.DecodingException;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.UnsupportedMediaTypeException;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Mono;
import reactor.netty.http.client.HttpClient;

public final class WebClientErrorDemo {

    public record Product(long id, String name) {
    }

    private static void send(
            HttpExchange exchange,
            int status,
            String contentType,
            String body) throws IOException {

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);

        exchange.getResponseHeaders().set(
                "Content-Type", contentType);

        exchange.sendResponseHeaders(status, bytes.length);

        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private static boolean hasCause(
            Throwable error, Class<?> expectedType) {

        for (Throwable current = error;
             current != null;
             current = current.getCause()) {

            if (expectedType.isInstance(current)) {
                return true;
            }
        }

        return false;
    }

    private static boolean hasCauseNamed(
            Throwable error, String simpleName) {

        for (Throwable current = error;
             current != null;
             current = current.getCause()) {

            if (current.getClass().getSimpleName()
                    .equals(simpleName)) {
                return true;
            }
        }

        return false;
    }

    private static String classify(Throwable error) {
        if (hasCause(error, WebClientResponseException.class)) {
            return "HTTP_STATUS";
        }

        if (hasCause(error, TimeoutException.class)
                || hasCauseNamed(error, "ReadTimeoutException")
                || hasCauseNamed(error, "ConnectTimeoutException")
                || hasCauseNamed(error, "PoolAcquireTimeoutException")) {
            return "TIMEOUT";
        }

        if (hasCause(error, DecodingException.class)
                || hasCause(error, CodecException.class)
                || hasCause(error, DataBufferLimitException.class)
                || hasCause(error, UnsupportedMediaTypeException.class)) {
            return "CODEC";
        }

        if (hasCause(error, WebClientRequestException.class)
                || hasCause(error, IOException.class)) {
            return "CONNECTION";
        }

        return "OTHER";
    }

    private static void expectFailure(
            String label,
            Mono<?> publisher,
            String expectedCategory) {

        try {
            publisher.block(Duration.ofSeconds(3));
            throw new AssertionError(
                    label + " should have failed as " + expectedCategory);
        }
        catch (RuntimeException error) {
            String actual = classify(error);

            if (!expectedCategory.equals(actual)) {
                throw new AssertionError(
                        label + ": expected " + expectedCategory
                                + " but got " + actual,
                        error);
            }

            System.out.println(label + "=" + actual);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService serverExecutor =
                Executors.newCachedThreadPool();

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.setExecutor(serverExecutor);

        server.createContext("/ok", exchange ->
                send(exchange, 200, "application/json",
                        "{\"id\":7,\"name\":\"demo\"}"));

        server.createContext("/status", exchange ->
                send(exchange, 503, "application/json",
                        "{\"code\":\"TEMP_UNAVAILABLE\"}"));

        server.createContext("/bad-json", exchange ->
                send(exchange, 200, "application/json",
                        "{\"id\":\"not-a-number\",\"name\":"));

        server.createContext("/slow", exchange -> {
            try {
                Thread.sleep(400);
                send(exchange, 200, "application/json",
                        "{\"id\":8,\"name\":\"slow\"}");
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                exchange.close();
            }
        });

        server.start();

        int closedPort;
        try (ServerSocket socket = new ServerSocket(
                0, 0, InetAddress.getByName("127.0.0.1"))) {
            closedPort = socket.getLocalPort();
        }

        try {
            String baseUrl = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            WebClient client = WebClient.builder()
                    .baseUrl(baseUrl)
                    .build();

            HttpClient shortResponseTimeout = HttpClient.create()
                    .responseTimeout(Duration.ofMillis(100));

            WebClient slowClient = WebClient.builder()
                    .baseUrl(baseUrl)
                    .clientConnector(
                            new ReactorClientHttpConnector(
                                    shortResponseTimeout))
                    .build();

            Product product = client.get()
                    .uri("/ok")
                    .retrieve()
                    .bodyToMono(Product.class)
                    .block(Duration.ofSeconds(3));

            System.out.println("ok=" + product);

            expectFailure(
                    "status",
                    client.get()
                            .uri("/status")
                            .retrieve()
                            .bodyToMono(Product.class),
                    "HTTP_STATUS");

            expectFailure(
                    "codec",
                    client.get()
                            .uri("/bad-json")
                            .retrieve()
                            .bodyToMono(Product.class),
                    "CODEC");

            expectFailure(
                    "timeout",
                    slowClient.get()
                            .uri("/slow")
                            .retrieve()
                            .bodyToMono(Product.class),
                    "TIMEOUT");

            WebClient unreachable = WebClient.builder()
                    .baseUrl("http://127.0.0.1:" + closedPort)
                    .build();

            expectFailure(
                    "connection",
                    unreachable.get()
                            .uri("/")
                            .retrieve()
                            .bodyToMono(Product.class),
                    "CONNECTION");
        }
        finally {
            server.stop(0);
            serverExecutor.shutdownNow();
        }
    }
}
~~~

### 12.4. Running the program

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=example.errors.WebClientErrorDemo
~~~

**Expected stdout:**

~~~text
ok=Product[id=7, name=demo]
status=HTTP_STATUS
codec=CODEC
timeout=TIMEOUT
connection=CONNECTION
~~~

Explanation:

- `/ok` returns valid JSON so the codec builds Product.
- `/status` returns HTTP 503 so `retrieve()` emits `WebClientResponseException`.
- `/bad-json` returns HTTP 200 with malformed body, so the error lies in the decoder.
- `/slow` takes 400 ms, exceeding the dedicated client's 100 ms response timeout.
- The closed port causes TCP connect to be refused; Spring wraps the request error and preserves the transport cause.

This is a local demo and makes no internet calls. Timeout classification inspects the cause chain because wrapper exceptions can vary across connectors, versions, and operating systems.

## 13. Testing WebClient in applications

Beyond a local server, `MockWebServer`, WireMock, or a mock connector can be used to test:

- HTTP 200 with valid JSON.
- HTTP 400/404/429/503/504.
- Error response body matching the error schema.
- Unsupported response Content-Type.
- Malformed JSON or mismatched field types.
- Body exceeding `maxInMemorySize`.
- Connection reset and timeouts.
- Redirect and proxy behavior if used by the application.
- Retry counts and idempotency keys.
- Cancellation when the caller no longer needs the response.

Use `StepVerifier` on Publishers when verifying error signals without blocking:

~~~java
StepVerifier.create(service.findProduct(id))
        .expectError(WebClientResponseException.NotFound.class)
        .verify();
~~~

This is an illustrative snippet requiring the Reactor Test dependency and a service configured to leave 404 as `WebClientResponseException.NotFound`.

For timeouts and transport errors, integration tests against a real connector are valuable because simple mock responses do not reproduce DNS, TCP, TLS, pooling, and network delays.

## 14. Common mistakes when handling WebClient exceptions

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating every error as WebClientResponseException | Misses connection and codec failures | Classify by exception type and cause chain |
| Treating HTTP 504 as a Reactor timeout | Confuses a gateway response with a client timeout | Check status code first |
| Treating every WebClientRequestException as connection refused | Loses distinction between DNS, TLS, reset, and timeout | Inspect root cause |
| Catching only TimeoutException | Misses Netty timeouts wrapped inside request exceptions | Inspect both cause chain and phase |
| Raising maxInMemorySize to fix every codec error | May hide oversized payload bugs and raise memory pressure | Determine whether it is a decode error or buffer limit |
| Equating HTTP 415 with UnsupportedMediaTypeException | Confuses server status with client decoder selection error | Check exception class and status |
| Using onErrorResume(Exception.class, empty) | Loses the original error and turns outages into empty results | Fallback only for specific exceptions |
| Retrying all errors | Amplifies load, repeats side effects, and prolongs outages | Retry transient errors with bounds |
| Retrying POST on timeout without an idempotency key | Can create duplicate data | Use an idempotency contract |
| Reading the error body multiple times | Body stream is no longer intact | Consume once and retain needed representation |
| Logging all headers/bodies | Can leak tokens and PII | Redact and log only needed fields |
| Setting only a Reactor timeout | Cannot tell which phase was slow | Configure separate timeouts for pool/connect/response |
| Not setting a response timeout | Requests may wait too long for a response | Choose timeouts per SLA |
| Using bodyToMono for large responses | Aggregates many bytes into memory | Use bodyToFlux or streaming |
| Testing only status 200 | Misses error handling, timeouts, and codec failures | Test all four error categories |

## 15. Checklist before deploying a WebClient client to production

- [ ] Know which connector is used: Reactor Netty, JDK HttpClient, Jetty, or Apache HttpComponents.
- [ ] Distinguish WebClientRequestException and WebClientResponseException.
- [ ] Record the root cause rather than logging only the outermost message.
- [ ] Separate timeouts for DNS, pool acquire, connect, TLS, response, and Publisher deadline as needed.
- [ ] Configure response timeout aligned with SLA.
- [ ] Set connection pool and pending acquire limits suitable for concurrency.
- [ ] Handle 4xx/5xx with onStatus or exchangeToMono.
- [ ] Verify response Content-Type and DTO contract.
- [ ] Handle DecodingException and UnsupportedMediaTypeException explicitly.
- [ ] Set an appropriate maxInMemorySize; prefer streaming for large payloads.
- [ ] Never log Authorization, Cookie, tokens, or sensitive raw bodies.
- [ ] Retry only transient errors with bounds/backoff.
- [ ] Respect Retry-After for 429 or services that specify it.
- [ ] Never retry non-idempotent operations without an idempotency key.
- [ ] Use fallbacks only for specific business errors; never swallow all exceptions.
- [ ] Test HTTP status, connection failures, timeouts, codecs, and error response bodies.
- [ ] Monitor status, error class, root cause, latency, retries, and pool metrics.

## 16. Self-check

**Question 1.** What does `WebClientResponseException` indicate?

The client received an HTTP response, and Spring represents the error status and response data in the exception.

**Question 2.** How does `WebClientRequestException` differ from `WebClientResponseException`?

The request exception holds request metadata and usually represents a failure while executing the request; the response exception holds actual HTTP response data such as status, headers, and body.

**Question 3.** Does connection refused have an HTTP status?

No. The TCP connection was refused before the client received an HTTP response from the service.

**Question 4.** Is HTTP 503 a connection error?

No. It is an HTTP response with status 503; the server or gateway answered the request.

**Question 5.** Why can HTTP 200 still cause WebClient to emit an error?

The body may be invalid JSON, the Content-Type may lack a matching decoder, the data may be incompatible with the DTO, or it may exceed the buffer limit.

**Question 6.** What does `DecodingException` typically indicate?

A content error while the decoder reads the stream, such as a JSON parse failure or data incompatible with the target type.

**Question 7.** Is `DataBufferLimitException` a connection error?

No. It indicates the data requiring buffering exceeded the configured limit of the codec/reader.

**Question 8.** How do `responseTimeout` and `Mono.timeout` differ?

responseTimeout belongs to Reactor Netty's response/read phase; Mono.timeout sets a deadline on the Publisher from subscription until a signal arrives.

**Question 9.** How does HTTP 504 differ from `TimeoutException`?

504 is a response from a gateway; TimeoutException is a timeout signal emitted by the client/reactive pipeline.

**Question 10.** When should `exchangeToMono` be used?

When you need to decide how to decode the response by status, or treat statuses like 404 as empty results per contract.

**Question 11.** Should every WebClient exception be retried?

No. Only retry transient errors, cap retry attempts, use backoff, and ensure the operation is safe to repeat.

**Question 12.** Why inspect the cause chain?

Timeouts and transport exceptions may be wrapped in Spring or connector exceptions. The root cause identifies the exact failing stage.

## 17. Official references

- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): WebClient overview, request/response, and core APIs.
- [Spring Framework — retrieve()](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): default 4xx/5xx creating WebClientResponseException and customizing onStatus.
- [Spring Framework — Exchange](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html): exchangeToMono, exchangeToFlux, and response body cleanup.
- [Spring Framework — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): codec limits, connector, and timeout configuration.
- [WebClientRequestException JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClientRequestException.html): request method, URI, headers, and request failure metadata.
- [WebClientResponseException JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClientResponseException.html): status, response headers, body, and status-specific subclasses.
- [DecodingException JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/codec/DecodingException.html): content decode error.
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): DataBuffer, codecs, and buffer lifecycle.
- [Reactor Netty — HTTP Client Timeout Configuration](https://projectreactor.io/docs/netty/release/reference/http-client.html#timeout-configuration): pool acquire, connect, response, TLS, and DNS timeouts.
- [Reactor Core — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): reactive error handling, retry, and fallback.

**Key takeaway:** an HTTP error status means a response was received; a connection error means the HTTP exchange did not complete; timeouts require identifying the phase; codec errors occur when converting response bytes into Java types. Check status first, then the exception and cause chain; configure timeouts per stage, preserve root causes, retry conditionally, and never turn every error into an empty result.