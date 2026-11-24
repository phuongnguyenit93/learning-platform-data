# ExchangeFilterFunction and Client-Side Filter Chains in Spring WebFlux

## 1. Role of ExchangeFilterFunction

`WebClient` is Spring WebFlux's reactive HTTP client. Applications often need to apply the same processing across many requests: attaching an access token, adding a correlation ID, logging, measuring latency, standardizing headers, mapping errors, or refreshing tokens.

`ExchangeFilterFunction` lets you encapsulate that processing into filters and register them on `WebClient.Builder`. Filters sit between the code calling WebClient and the `ExchangeFunction` that executes the HTTP exchange.

~~~text
Service / Repository
       |
       v
WebClient fluent API
       |
       v
Filter A -> Filter B -> Filter C
       |
       v
ExchangeFunction
       |
       v
ClientHttpConnector
       |
       v
HTTP client / Network
       |
       v
ClientResponse
       |
       v
Filter C -> Filter B -> Filter A
       |
       v
retrieve() / exchangeToMono()
       |
       v
Mono<T> / Flux<T>
~~~

Filters intervene at the logical request/response layer. Connection pools, TLS, proxies, socket timeouts, and HTTP transport remain the responsibility of the client connector.

## 2. The Filter Contract

### 2.1. Functional Interface

`ExchangeFilterFunction` resides in the package:

~~~java
org.springframework.web.reactive.function.client.ExchangeFilterFunction
~~~

Primary method:

~~~java
Mono<ClientResponse> filter(
    ClientRequest request,
    ExchangeFunction next
);
~~~

- `request` is the current request, including method, URL, headers, attributes, and body inserter.
- `next` is the next step in the chain; at the end of the chain, it performs the HTTP exchange via the connector.
- The return value is a Publisher emitting `ClientResponse` or an error signal.
- The filter only runs when the Publisher is subscribed to.

Pass-through filter:

~~~java
ExchangeFilterFunction passThrough =
    (request, next) -> next.exchange(request);
~~~

### 2.2. What a Filter Can Do

1. Modify the request and call `next.exchange(modifiedRequest)`.
2. Observe the request before sending.
3. Observe the response with `doOnNext` or `flatMap`.
4. Return a different response if the application contract permits.
5. Emit an error without sending the request.
6. Read, consume, or release the response body.
7. Resend the request under a bounded retry/refresh policy.

Filters fit cross-cutting concerns at the HTTP client boundary. Use-case business rules should live in the service/domain layer.

## 3. Ordering in the Filter Chain

### 3.1. Registering Filters

~~~java
WebClient client = WebClient.builder()
    .filter(filterA)
    .filter(filterB)
    .filter(filterC)
    .build();
~~~

`WebClient.Builder.filter` appends a filter to the end of the list. If the registration order is A, B, C:

- Request flows: A → B → C → connector.
- Response returns: connector → C → B → A.

Filter A is the outermost layer. It invokes B via `next`; B invokes C; C invokes the connector. When the response returns, each filter can process the response before handing it to the enclosing layer.

### 3.2. Observing Order in Code

~~~java
ExchangeFilterFunction first = (request, next) -> {
    log.info("A: request");
    return next.exchange(request)
        .doOnNext(response -> log.info("A: response"));
};

ExchangeFilterFunction second = (request, next) -> {
    log.info("B: request");
    return next.exchange(request)
        .doOnNext(response -> log.info("B: response"));
};

WebClient client = WebClient.builder()
    .filter(first)
    .filter(second)
    .build();
~~~

Logs appear in order:

~~~text
A: request
B: request
B: response
A: response
~~~

### 3.3. andThen, Inserting, and Removing Filters

`ExchangeFilterFunction.andThen` creates a composite filter in which the current filter is applied before the passed filter:

~~~java
ExchangeFilterFunction combined = filterA.andThen(filterB);
~~~

You can reorder the list using `filters`:

~~~java
WebClient client = WebClient.builder()
    .filter(loggingFilter)
    .filter(metricsFilter)
    .filters(filters -> filters.add(0, requestIdFilter))
    .build();
~~~

`add(0, ...)` places the filter at the front of the chain. Configure the list before building the client.

## 4. Modifying ClientRequest

### 4.1. Request Is Immutable

Do not mutate the request directly. Create a copy with `ClientRequest.from(request)`:

~~~java
ExchangeFilterFunction addHeader = (request, next) -> {
    ClientRequest updated = ClientRequest.from(request)
        .headers(headers ->
            headers.set("X-Client-Name", "catalog-service"))
        .build();

    return next.exchange(updated);
};
~~~

`headers.set` replaces existing values. The `header(name, value)` method can append a new value to an existing header. The new request preserves method, URL, body inserter, and attributes unless changed.

### 4.2. ofRequestProcessor

~~~java
ExchangeFilterFunction userAgentFilter =
    ExchangeFilterFunction.ofRequestProcessor(request -> {
        ClientRequest updated = ClientRequest.from(request)
            .headers(headers ->
                headers.set(HttpHeaders.USER_AGENT, "orders-client/1.0"))
            .build();

        return Mono.just(updated);
    });
~~~

`ofRequestProcessor` turns a `ClientRequest`-processing function into a request-only filter.

### 4.3. Conditional Application

~~~java
ExchangeFilterFunction conditionalHeader = (request, next) -> {
    if (request.url().getPath().startsWith("/internal/")) {
        ClientRequest updated = ClientRequest.from(request)
            .headers(headers ->
                headers.set("X-Internal-Client", "true"))
            .build();

        return next.exchange(updated);
    }

    return next.exchange(request);
};
~~~

For use-case-specific rules, a request attribute is usually clearer than checking URLs with overly broad string matching.

## 5. Request Attributes and Reactor Context

### 5.1. Attributes Are Not HTTP Headers

`ClientRequest` has attributes for passing internal metadata between caller and filter. Attributes do not automatically become HTTP headers and are not sent over the network.

The caller attaches request ID and operation name:

~~~java
client.get()
    .uri("/products/{id}", id)
    .attribute("requestId", requestId)
    .attribute("operationName", "product.lookup")
    .retrieve()
    .bodyToMono(Product.class);
~~~

The filter reads the attribute and turns the request ID into a header:

~~~java
ExchangeFilterFunction requestIdFilter = (request, next) -> {
    String requestId = request.attribute("requestId")
        .map(String::valueOf)
        .orElseGet(() -> UUID.randomUUID().toString());

    ClientRequest updated = ClientRequest.from(request)
        .headers(headers -> headers.set("X-Request-Id", requestId))
        .build();

    return next.exchange(updated);
};
~~~

This is how you pass per-request metadata without storing the request ID in a mutable field of a singleton filter.

### 5.2. When to Use Reactor Context?

Reactor Context is suited when metadata needs to flow across multiple Publishers and be read at multiple points in a reactive chain. Request attributes are suited when a filter needs to read metadata from the `ClientRequest` itself.

Do not use `ThreadLocal` to pass request IDs in reactive applications: callbacks may run on different threads and multiple requests may interleave on the same thread.

## 6. Processing ClientResponse

### 6.1. ofResponseProcessor

~~~java
ExchangeFilterFunction responseStatusFilter =
    ExchangeFilterFunction.ofResponseProcessor(response -> {
        log.info("Downstream returned {}", response.statusCode());
        return Mono.just(response);
    });
~~~

The filter merely observes the status and returns the response unchanged for WebClient to continue processing. It does not read the body, so the caller can still decode the body.

### 6.2. Measuring Latency

~~~java
ExchangeFilterFunction timingFilter = (request, next) -> {
    long started = System.nanoTime();

    return next.exchange(request)
        .doOnNext(response -> {
            long elapsedMs =
                (System.nanoTime() - started) / 1_000_000;

            log.info("HTTP {} completed with {} in {} ms",
                request.method(), response.statusCode(), elapsedMs);
        });
};
~~~

`doOnNext` only observes the response. The body continues downstream, where `retrieve()` or `exchangeToMono()` decides how to decode it.

### 6.3. 4xx/5xx Statuses

When a filter returns the response intact, `retrieve()` applies its status handlers; by default 4xx/5xx statuses become `WebClientResponseException`.

When using `exchangeToMono` or `exchangeToFlux`, the caller directly checks status and chooses how to decode or emit an error.

Spring provides the `ExchangeFilterFunctions.statusError` utility:

~~~java
ExchangeFilterFunction serverErrorFilter =
    ExchangeFilterFunctions.statusError(
        HttpStatusCode::is5xxServerError,
        response -> new DownstreamServiceException(
            "Downstream service returned a server error")
    );
~~~

`DownstreamServiceException` is an application-defined exception. Only use this filter when you want a uniform error policy across every request of a client. If individual endpoints interpret statuses differently, handling them in the service is more flexible.

## 7. Response Body Ownership

### 7.1. Filters Must Consume or Forward the Body

`ClientResponse` holds a body stream. When a filter processes a response, it must:

- Consume the body completely if the filter is responsible for reading the body.
- Release the body if the content is not needed.
- Or return the original response so downstream code can consume it.

Never read the body inside a filter and then return the original response as if the body were still intact. The body is a stream that can typically be consumed only once.

### 7.2. Reading the Body to Log and Returning the Response Is Wrong

Incorrect example:

~~~java
return next.exchange(request)
    .flatMap(response ->
        response.bodyToMono(String.class)
            .doOnNext(body -> log.info("body={}", body))
            .thenReturn(response)
    );
~~~

The filter has already consumed the body into a String. When the caller later invokes `bodyToMono` to decode a DTO, there is no body left to read; it may see an empty body or an error.

Logging the entire response body can also expose tokens, personal data, or huge payloads. Prefer logging status, latency, request ID, and normalized error codes.

### 7.3. If Discarding the Body, Release It

If a filter decides to discard the response and not pass it to the caller:

~~~java
return next.exchange(request)
    .flatMap(response -> {
        if (response.statusCode().is3xxRedirection()) {
            return response.releaseBody()
                .then(Mono.error(
                    new IllegalStateException("Redirect is not allowed")));
        }

        return Mono.just(response);
    });
~~~

`releaseBody` consumes/releases the body so connections and buffers can be properly reused.

### 7.4. Reading the Body and Building a New Response

If you genuinely need to inspect the body and still let downstream read it again, read it once and construct a new response:

~~~java
return next.exchange(request)
    .flatMap(response ->
        response.bodyToMono(String.class)
            .defaultIfEmpty("")
            .map(body -> ClientResponse.from(response)
                .body(body)
                .build())
    );
~~~

This example is for small bodies. It aggregates the entire response into a String, increasing memory usage and potentially altering charset/streaming behavior. Do not use it for large files, infinite NDJSON, or streaming responses.

### 7.5. exchangeToMono and exchangeToFlux

~~~java
Mono<Product> product = client.get()
    .uri("/products/{id}", id)
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(Product.class);
        }

        return response.createError();
    });
~~~

After the Publisher returned from the callback completes, Spring checks the response body. If the body was not consumed, the framework releases it to prevent memory/connection leaks. Therefore, you cannot retain the response and try to decode the body in a downstream step after the callback has finished.

## 8. Authentication and Token Refresh

### 8.1. Attaching a Bearer Token

A token provider can supply tokens asynchronously:

~~~java
public interface TokenProvider {
    Mono<String> currentAccessToken();
}
~~~

Filter attaching a Bearer token:

~~~java
ExchangeFilterFunction bearerTokenFilter(TokenProvider tokens) {
    return (request, next) ->
        tokens.currentAccessToken()
            .map(token -> ClientRequest.from(request)
                .headers(headers -> headers.setBearerAuth(token))
                .build())
            .flatMap(next::exchange);
}
~~~

The token is acquired within the reactive pipeline without blocking. If a request already carries a special Authorization header, define clearly whether the filter is allowed to overwrite it. Do not log tokens.

### 8.2. Basic Authentication

~~~java
WebClient client = WebClient.builder()
    .filter(ExchangeFilterFunctions.basicAuthentication(
        "service-user", "service-password"))
    .build();
~~~

Credentials must come from a secret manager or secure configuration. Never hardcode credentials in source code or logs.

### 8.3. Refreshing the Token on 401

The pattern below releases the 401 response body, fetches a new token, and resends the request once through downstream filters:

~~~java
ExchangeFilterFunction refreshOnUnauthorized(
    TokenProvider tokens
) {
    return (request, next) -> next.exchange(request)
        .flatMap(response -> {
            if (response.statusCode().value()
                    != HttpStatus.UNAUTHORIZED.value()) {
                return Mono.just(response);
            }

            return response.releaseBody()
                .then(tokens.refreshAccessToken())
                .flatMap(token -> {
                    ClientRequest retryRequest =
                        ClientRequest.from(request)
                            .headers(headers ->
                                headers.setBearerAuth(token))
                            .build();

                    return next.exchange(retryRequest);
                });
        });
}
~~~

Provider interface:

~~~java
public interface TokenProvider {
    Mono<String> currentAccessToken();
    Mono<String> refreshAccessToken();
}
~~~

For production use, add:

- Only refresh for requests using an appropriate authentication mechanism.
- Do not loop refresh infinitely if the retry still receives 401.
- Synchronize/coalesce refreshes when multiple requests hit token expiration simultaneously.
- Use a dedicated client for the token endpoint so the refresh filter does not recursively invoke itself.
- Handle expired refresh tokens and authentication failures.
- Do not resend single-use stream request bodies if the body is non-replayable.
- Only retry write operations when an idempotency key or deduplication mechanism is in place.

`next` inside a filter represents the portion of the chain downstream of the current filter. Calling `next.exchange(retryRequest)` does not re-run the current filter itself, though it still passes through filters after it.

## 9. Logging, Tracing, and Observability

### 9.1. Log Metadata Instead of Bodies

A logging filter should focus on HTTP method, operation name/route template, request ID, response status, processing duration, and exception type if the exchange fails.

~~~java
ExchangeFilterFunction safeLoggingFilter() {
    return (request, next) -> {
        String operation = request.attribute("operationName")
            .map(String::valueOf)
            .orElse("outbound-http");

        String requestId = request.headers()
            .getFirst("X-Request-Id");

        long started = System.nanoTime();

        log.debug("Outbound {} operation={} requestId={}",
            request.method(), operation, requestId);

        return next.exchange(request)
            .doOnNext(response -> {
                long elapsed =
                    (System.nanoTime() - started) / 1_000_000;

                log.info("Outbound operation={} status={} elapsedMs={}",
                    operation, response.statusCode(), elapsed);
            })
            .doOnError(error ->
                log.warn("Outbound operation={} failed with {}",
                    operation, error.getClass().getSimpleName()));
    };
}
~~~

Do not log query strings, request bodies, response bodies, cookies, or Authorization headers by default. URLs can contain emails, tokens, or account IDs; use operation names/route templates to keep sensitive data out of logs.

### 9.2. Micrometer Observation

Spring supports WebClient observation via `ObservationRegistry`. When Micrometer Observation and tracing are properly configured, prefer standard mechanisms to collect metrics/spans rather than building custom logging/tracing systems inside every filter.

Avoid high-cardinality metric tags such as user IDs, order IDs, full URLs, or exception messages.

### 9.3. Do Not Use ThreadLocal

Filters are singletons shared across many requests. Do not store the current request ID, user, or token in mutable fields. Obtain data from request attributes, Reactor Context, or thread-safe providers.

## 10. Error Handling, Timeouts, and Retries

### 10.1. Filters Can Short-Circuit

If a filter does not invoke `next.exchange`, the HTTP request is never sent:

~~~java
ExchangeFilterFunction blockDisallowedHost = (request, next) -> {
    if (request.url().getHost().equals("blocked.example")) {
        return Mono.error(
            new IllegalArgumentException("Host is not allowed"));
    }

    return next.exchange(request);
};
~~~

This mechanism can enforce host policies. In real applications, normalize hostnames and consider redirects, DNS rebinding, and proxy configurations when security policies require it.

### 10.2. Retry Only Recoverable Errors

Do not retry every exception. Transient DNS failures or connection resets may be recoverable; 400, unrefreshed 401, business 404, or validation failures generally gain nothing from resending the exact same request.

~~~java
return client.get()
    .uri("/catalog/{id}", id)
    .retrieve()
    .bodyToMono(Product.class)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .maxBackoff(Duration.ofSeconds(1))
            .filter(this::isTransientFailure)
    );
~~~

`isTransientFailure` must be defined by the application based on actual exceptions/statuses. Two retries mean up to three total attempts including the initial try.

Placing retries in the service/use case usually makes evaluating idempotency and deadlines easier. If retries live inside a filter, the policy might accidentally apply to login, upload, payment, and other write requests.

### 10.3. Non-Replayable Request Bodies

A request body may be a single-use Publisher, file stream, or data from a non-rereadable source. Resending a request does not mean the body can be replayed.

Before retrying, verify that the body can be recreated, the server has not performed side effects, write operations carry an idempotency key, retries are bounded, and the caller is still waiting for a response.

### 10.4. Timeouts Belong to Multiple Layers

| Timeout type | Typical configuration location |
| --- | --- |
| DNS/connect timeout | HTTP client connector |
| Response/read timeout | Reactor Netty or corresponding connector |
| Entire Publisher timeout | Reactor `timeout` |
| Business deadline | Service/use case |
| Proxy idle timeout | Reverse proxy/API gateway |

A filter can attach a timeout to the Publisher, but connection and TLS handshake timeouts must be configured on the connector. Do not use a single timeout to replace all limits.

## 11. Immutable WebClient, Builder, and mutate

### 11.1. WebClient Is Immutable After Build

After calling `build()`, WebClient has an immutable configuration and can be shared in singleton services. Do not create a new client per request without special justification, as doing so loses connection pool and shared configuration benefits.

### 11.2. Creating Derived Clients with mutate

~~~java
WebClient baseClient = WebClient.builder()
    .filter(requestIdFilter)
    .filter(loggingFilter)
    .build();

WebClient authenticatedClient = baseClient.mutate()
    .filter(bearerTokenFilter)
    .build();
~~~

`authenticatedClient` inherits `baseClient`'s configuration and adds the filter. The original client is unchanged.

Filters can be inserted at specific positions:

~~~java
WebClient clientWithAuthFirst = baseClient.mutate()
    .filters(filters -> filters.add(0, bearerTokenFilter))
    .build();
~~~

Filter position affects request and response ordering; test whenever changing the chain.

### 11.3. When to Create Multiple WebClients?

You can create separate clients by dependency or security boundary:

- Catalog API: dedicated base URL, token, and timeouts.
- Payment API: dedicated credentials, retry, and idempotency policy.
- Public API: carries no internal credentials.
- Token endpoint: separate client to prevent the refresh filter from looping onto itself.

Clients may share a connector or connection provider when properly configured, but should not share headers/credentials across different trust boundaries.

## 12. Filters and Other WebClient Extension Points

| Mechanism | When to use? |
| --- | --- |
| `ExchangeFilterFunction` | Cross-cutting concerns on logical request/response |
| `defaultHeader` / `defaultRequest` | Simple default headers or request customizations |
| `retrieve().onStatus(...)` | Mapping status to exception on a single request |
| `exchangeToMono` / `exchangeToFlux` | Need decoding control based on status/headers |
| `ClientHttpConnector` | Configuring HTTP engine, TLS, proxy, and transport |
| `ExchangeStrategies` / codec config | Tuning encoding/decoding and memory limits |
| `Micrometer Observation` | Standard metrics, traces, and observations |

Do not use filters to solve problems where connectors or codecs already provide the proper extension point. For example, changing the TLS trust store belongs in HTTP client connector configuration; filters only see higher-level requests/responses.

## 13. Complete Spring Boot 3.5.7 + Java 17 Example

The application below has two endpoints:

- `GET /internal/greetings/{name}`: endpoint simulating a downstream service.
- `GET /api/greetings/{name}`: calls the internal endpoint via a WebClient configured with a request ID filter and a logging filter.

An integration test uses MockWebServer to verify filter ordering and request attributes.

### 13.1. Project Structure

~~~text
webclient-filter-demo/
├── pom.xml
├── src/main/resources/
│   └── application.properties
├── src/main/java/example/webclient/
│   ├── WebClientFilterApplication.java
│   ├── WebClientConfiguration.java
│   ├── ClientFilters.java
│   ├── GreetingService.java
│   ├── GreetingController.java
│   └── GreetingResponse.java
└── src/test/java/example/webclient/
    └── ExchangeFilterFunctionTest.java
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
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webclient-filter-demo</artifactId>
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

### 13.3. application.properties

~~~properties
server.port=8080
logging.level.example.webclient=INFO
~~~

When deploying multiple services, replace the localhost base URL with the real downstream service URL. The localhost value is solely for running the single-process demo.

### 13.4. WebClientFilterApplication.java

~~~java
package example.webclient;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebClientFilterApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebClientFilterApplication.class, args);
    }
}
~~~

### 13.5. GreetingResponse.java

~~~java
package example.webclient;

public record GreetingResponse(
    String message,
    String requestId
) {}
~~~

### 13.6. ClientFilters.java

~~~java
package example.webclient;

import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;

public final class ClientFilters {

    private static final Logger log =
        LoggerFactory.getLogger(ClientFilters.class);

    private ClientFilters() {
    }

    public static ExchangeFilterFunction requestId() {
        return (request, next) -> {
            String requestId = request.attribute("requestId")
                .map(String::valueOf)
                .orElseGet(() -> UUID.randomUUID().toString());

            ClientRequest updated = ClientRequest.from(request)
                .headers(headers ->
                    headers.set("X-Request-Id", requestId))
                .build();

            return next.exchange(updated);
        };
    }

    public static ExchangeFilterFunction safeLogging() {
        return (request, next) -> {
            String operation = request.attribute("operationName")
                .map(String::valueOf)
                .orElse("outbound-http");

            String requestId = request.headers()
                .getFirst("X-Request-Id");

            long started = System.nanoTime();

            log.debug("Outbound {} operation={} requestId={}",
                request.method(), operation, requestId);

            return next.exchange(request)
                .doOnNext(response -> {
                    long elapsedMs =
                        (System.nanoTime() - started) / 1_000_000;

                    log.info(
                        "Outbound operation={} status={} elapsedMs={}",
                        operation, response.statusCode(), elapsedMs);
                })
                .doOnError(error ->
                    log.warn(
                        "Outbound operation={} failed with {}",
                        operation,
                        error.getClass().getSimpleName()));
        };
    }
}
~~~

The `requestId()` filter generates or reads the request ID from the attribute, then sets the header using `headers.set` to avoid duplicating values. The `safeLogging()` filter logs method, operation, status, and latency; it neither reads the body nor logs credentials.

### 13.7. WebClientConfiguration.java

~~~java
package example.webclient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfiguration {

    @Bean
    WebClient greetingWebClient(
        WebClient.Builder builder,
        @Value("${demo.remote-base-url:http://localhost:8080}") String baseUrl
    ) {
        return builder
            .baseUrl(baseUrl)
            .filter(ClientFilters.requestId())
            .filter(ClientFilters.safeLogging())
            .build();
    }
}
~~~

Spring Boot supplies a `WebClient.Builder` configured per the application context. Each call to `filter` appends a filter to the end of the chain. Once built, the client is injected and reused.

### 13.8. GreetingService.java

~~~java
package example.webclient;

import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class GreetingService {

    private final WebClient client;

    public GreetingService(WebClient greetingWebClient) {
        this.client = greetingWebClient;
    }

    public Mono<GreetingResponse> greet(String name) {
        String requestId = UUID.randomUUID().toString();

        return client.get()
            .uri("/internal/greetings/{name}", name)
            .attribute("requestId", requestId)
            .attribute("operationName", "greeting.lookup")
            .retrieve()
            .bodyToMono(GreetingResponse.class);
    }
}
~~~

The service does not add the `X-Request-Id` header itself. It passes metadata via request attributes; the filter is responsible for converting the attribute into an HTTP header.

### 13.9. GreetingController.java

~~~java
package example.webclient;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class GreetingController {

    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/internal/greetings/{name}")
    public GreetingResponse internal(
        @PathVariable String name,
        @RequestHeader(
            value = "X-Request-Id",
            required = false
        ) String requestId
    ) {
        return new GreetingResponse(
            "Hello, " + name,
            requestId
        );
    }

    @GetMapping("/api/greetings/{name}")
    public Mono<GreetingResponse> greeting(
        @PathVariable String name
    ) {
        return service.greet(name);
    }
}
~~~

When calling `/api/greetings/Linh`, the controller calls WebClient to `/internal/greetings/Linh`. The request ID is attached to the header by the filter, and the downstream endpoint echoes that ID in the response.

### 13.10. ExchangeFilterFunctionTest.java

~~~java
package example.webclient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.io.IOException;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

class ExchangeFilterFunctionTest {

    private MockWebServer server;

    @BeforeEach
    void startServer() throws IOException {
        server = new MockWebServer();
        server.start();
    }

    @AfterEach
    void stopServer() throws IOException {
        server.shutdown();
    }

    @Test
    void filtersRunInRegistrationOrder() throws Exception {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("ok"));

        List<String> events = new CopyOnWriteArrayList<>();

        ExchangeFilterFunction first = (request, next) -> {
            events.add("first:request");

            ClientRequest updated = ClientRequest.from(request)
                .headers(headers -> headers.set("X-First", "yes"))
                .build();

            return next.exchange(updated)
                .doOnNext(response -> events.add("first:response"));
        };

        ExchangeFilterFunction second = (request, next) -> {
            events.add("second:request");

            return next.exchange(request)
                .doOnNext(response -> events.add("second:response"));
        };

        WebClient client = WebClient.builder()
            .baseUrl(server.url("/").toString())
            .filter(first)
            .filter(second)
            .build();

        String body = client.get()
            .uri("/probe")
            .attribute("requestId", "req-123")
            .retrieve()
            .bodyToMono(String.class)
            .block(Duration.ofSeconds(3));

        RecordedRequest recorded =
            server.takeRequest(3, TimeUnit.SECONDS);

        assertEquals("ok", body);
        assertNotNull(recorded);
        assertEquals("yes", recorded.getHeader("X-First"));

        assertEquals(
            List.of(
                "first:request",
                "second:request",
                "second:response",
                "first:response"
            ),
            events
        );
    }

    @Test
    void requestIdFilterAddsAttributeAsHeader() throws Exception {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "text/plain")
            .setBody("accepted"));

        WebClient client = WebClient.builder()
            .baseUrl(server.url("/").toString())
            .filter(ClientFilters.requestId())
            .build();

        String body = client.get()
            .uri("/probe")
            .attribute("requestId", "trace-456")
            .retrieve()
            .bodyToMono(String.class)
            .block(Duration.ofSeconds(3));

        RecordedRequest recorded =
            server.takeRequest(3, TimeUnit.SECONDS);

        assertEquals("accepted", body);
        assertNotNull(recorded);
        assertEquals("trace-456",
            recorded.getHeader("X-Request-Id"));
    }
}
~~~

The first test verifies that the first filter runs before the second filter on the request path; the response returns in reverse order; the header added by the filter reaches the simulated HTTP server; and the caller still decodes the body.

The second test verifies that the request attribute is converted into an actual header. MockWebServer enables testing HTTP requests without depending on external services.

### 13.11. Running the Application

Requires JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Call the endpoint:

~~~bash
curl -i http://localhost:8080/api/greetings/Linh
~~~

Expected body:

~~~json
{
  "message": "Hello, Linh",
  "requestId": "a-uuid-that-changes-per-call"
}
~~~

The actual request ID is a UUID generated while the service runs; the value will differ on each call. In the application logs, the filter logs operation, status, and processing time.

Run tests:

~~~bash
mvn test
~~~

Both filter tests use MockWebServer and do not require running the Spring Boot application. Additional application tests can be added to verify that `/api/greetings` calls `/internal/greetings` as configured.

## 14. Common Mistakes When Writing ExchangeFilterFunction

**Mistake 1 — Forgetting to call `next.exchange(request)`.** The request never reaches the connector. If intentionally short-circuiting, return a valid response or error.

**Mistake 2 — Calling `next.exchange` multiple times unintentionally.** Can send duplicate requests. Only call it again under an explicit retry/refresh policy.

**Mistake 3 — Mutating ClientRequest directly.** Requests are immutable; use `ClientRequest.from(request).build()`.

**Mistake 4 — Reading the response body to log and returning the original response.** Downstream has no body left to decode. Log metadata only, or build a new response after reading a bounded body.

**Mistake 5 — Discarding a response body without releasing it.** Can prevent connections/buffers from being properly reused. Call `response.releaseBody()` if the filter drops the response.

**Mistake 6 — Logging Authorization or Cookie.** Can leak credentials into logs. Redact or omit sensitive headers.

**Mistake 7 — Using ThreadLocal for request IDs.** Reactive chains can switch threads. Use request attributes or Reactor Context.

**Mistake 8 — Storing tokens/request IDs in mutable fields of a singleton filter.** Concurrent requests will overwrite one another's data. Load data per request or from thread-safe providers.

**Mistake 9 — Retrying every status and exception.** Can retry 400/401/404 or repeat side effects. Only retry transient errors per policy.

**Mistake 10 — Refreshing a token without releasing the 401 response.** The old body can hold connections/buffers. Release the body before sending the new request.

**Mistake 11 — Refreshing tokens without bounds.** The new token might still be rejected, creating a loop. Attempt refresh/replay only once per request.

**Mistake 12 — Resending a non-replayable body.** Publishers/file streams may already be consumed. Only replay when the body can be recreated and the operation is safe.

**Mistake 13 — Applying the same refresh filter to the token endpoint.** Token-acquisition requests can trigger the filter itself, causing recursion. Use a separate WebClient for authentication endpoints.

**Mistake 14 — Confusing request and response order.** The first filter runs first on send, while responses return in reverse order. Test the chain with an event log.

**Mistake 15 — Modifying the filter list after build.** A built WebClient is immutable. Use `mutate()` to create a derived client.

**Mistake 16 — Putting business rules into filters.** Filters become hard to test and understand. Keep filters for shared HTTP concerns.

**Mistake 17 — Using filters instead of connector timeouts/TLS.** Filters do not configure sockets or TLS handshakes. Use ClientHttpConnector and the underlying HTTP client.

**Mistake 18 — Calling `block()` or `subscribe()` inside a filter.** Breaks reactive composition, risks deadlocks, or loses error propagation. Return a Publisher and let the caller manage subscriptions.

## 15. Filter Chain Design Checklist

Before taking a filter to production, check:

1. Which cross-cutting concern does this filter serve?
2. Does it need to modify requests, observe responses, or both?
3. Does the filter always invoke `next.exchange` when not short-circuiting?
4. Is registration order correct with respect to authentication, logging, metrics, and retries?
5. Does request mutation preserve method, URL, body, and attributes?
6. Does per-request metadata use attributes/Context instead of mutable fields?
7. Is the response body properly forwarded, consumed, or released?
8. Are sensitive bodies, tokens, cookies, or query strings kept out of logs?
9. Do retries filter for transient errors, cap attempts, and respect idempotency?
10. Does token refresh release the 401 body and limit retries to one attempt?
11. Is the request body replayable?
12. Does the token endpoint use a separate client if needed to avoid recursion?
13. Are timeouts configured at both the connector layer and service deadline?
14. Are request/response filter ordering tested with MockWebServer or a mock ExchangeFunction?
15. Are standard metrics/tracing in place to avoid building duplicate observability?

## 16. Self-Check Exercises

1. Where does `ExchangeFilterFunction` sit in WebClient? **Between the WebClient calling API and the ExchangeFunction executing the HTTP exchange.**
2. What parameters does a filter's primary method take? **ClientRequest and ExchangeFunction next.**
3. What does `next.exchange(request)` mean? **Passes the request to the next filter or the connector at the end of the chain.**
4. If A then B are registered, in what order does the request travel? **A → B → connector.**
5. In what order does the response return? **Connector → B → A.**
6. Can ClientRequest be mutated directly? **No; create a copy with ClientRequest.from.**
7. What is `ofRequestProcessor` used for? **Creating a filter from a function that processes ClientRequest.**
8. What is `ofResponseProcessor` used for? **Creating a filter from a function that processes ClientResponse.**
9. Do request attributes automatically become HTTP headers? **No; a filter must explicitly convert them into headers if they need to be sent over the network.**
10. May a filter read the response body and return the old response? **No; the body has already been consumed.**
11. If a filter drops a response, what must be done with the body? **Release the body using response.releaseBody().**
12. How does `retrieve()` handle 4xx/5xx by default? **Converts them into WebClientResponseException unless a custom status handler is configured.**
13. When is `exchangeToMono` appropriate? **When you need to inspect status/headers and choose how to decode the response.**
14. Does `mutate()` modify the original WebClient? **No; it creates a builder for a derived client.**
15. Should Authorization headers be logged? **No; protect or redact credentials.**
16. Should every POST be retried? **No; consider idempotency and body replayability.**
17. Why must token refresh release the 401 body? **So it does not hold the response body/connection before sending a new request.**
18. Do filters replace TLS/connection pool configuration? **No; those belong to ClientHttpConnector and the HTTP client.**

## 17. Key Takeaways and References

- **`ExchangeFilterFunction`** is a functional interface for intercepting WebClient's logical HTTP exchanges.
- The first registered filter runs first on the request path; responses return in reverse order.
- Use `ClientRequest.from` to create a new request; use request attributes for per-request metadata.
- `ofRequestProcessor` and `ofResponseProcessor` fit single-responsibility filters.
- Filters handling responses must consume, release, or forward the body. Never read a body to log and return the old response.
- `response.releaseBody()` is necessary when a filter drops a response body; token refresh must release the 401 before retrying.
- `retrieve()` and `exchangeToMono/Flux` have different status/body handling mechanisms.
- WebClient is immutable after build; use `mutate()` to create derived clients.
- Retries must be conditional, bounded, deadline-aware, idempotent, and compatible with body replayability.
- Do not log sensitive credentials/bodies; use appropriate request IDs, metrics, and tracing.
- Filters handle HTTP concerns; connectors handle transport, TLS, proxies, and connection pools.

Official documentation:

1. [Spring Framework 6.2 Reference — WebClient Filters](https://docs.spring.io/spring/reference/6.2/web/webflux-webclient/client-filter.html): registering filters, request mutation, mutate, response body ownership, and token refresh.
2. [Spring Framework 6.2 Reference — WebClient Exchange](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-exchange.html): exchangeToMono, exchangeToFlux, and automatic release of unconsumed response bodies.
3. [Spring Framework 6.2 Reference — WebClient Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-builder.html): Builder, connector, codecs, filter chain, and client immutability.
4. [Spring Framework Javadoc — ExchangeFilterFunction](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/client/ExchangeFilterFunction.html): filter, andThen, ofRequestProcessor, and ofResponseProcessor.
5. [Spring Framework Javadoc — WebClient.Builder](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/client/WebClient.Builder.html): filter, filters, clientConnector, and builder settings.
6. [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html): request/response workflow, codecs, testing, and observability.
