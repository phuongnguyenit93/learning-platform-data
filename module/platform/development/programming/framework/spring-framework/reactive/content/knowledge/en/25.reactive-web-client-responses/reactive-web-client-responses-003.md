# Handling onStatus and mapping HTTP errors in Spring WebClient

WebClient is Spring WebFlux's reactive HTTP client. When calling a remote API, the client may receive a successful response, an HTTP error response such as 404 or 503, or no response at all due to connection failures, timeouts, or decoding errors. These cases must be clearly distinguished so the service layer handles them properly.

With WebClient, the two commonly used APIs are retrieve() and exchangeToMono()/exchangeToFlux(). When using retrieve(), you can register an **onStatus** callback to convert an HTTP status into an application exception. Without a registered callback, WebClient converts 4xx and 5xx responses into WebClientResponseException by default. When you need to branch response handling by status, read different bodies, or treat 404 as an empty result, exchangeToMono() is often easier to control.

This lesson belongs to **Reading WebClient Responses**, focusing on onStatus, reading error bodies safely, mapping HTTP errors to domain exceptions, distinguishing HTTP errors from transport/codec errors, and testing client behavior.

## 1. Learning objectives

After this lesson, you can:

- Describe the request-response lifecycle when using WebClient.retrieve().
- Explain the role and signature of ResponseSpec.onStatus().
- Understand WebClient's default behavior for 4xx and 5xx statuses.
- Map HTTP statuses into business-meaningful exceptions.
- Read error bodies safely and avoid consuming the response body twice.
- Distinguish Mono.empty() inside onStatus from turning the response into Mono.empty().
- Use onRawStatus() for non-standard status codes.
- Choose between retrieve() and exchangeToMono()/exchangeToFlux().
- Distinguish HTTP errors, connection errors, timeouts, and decode errors.
- Design conditional retries and respect Retry-After.
- Write a Java 17+ example with Spring Boot WebFlux and MockWebServer.

## 2. Basic WebClient response lifecycle

A WebClient request is typically created via a builder, sent, and then converted into a Java type:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", productId)
    .retrieve()
    .bodyToMono(Product.class);
~~~

Main steps:

1. WebClient builds the HTTP request from method, URI, headers, and body.
2. The HTTP connector sends the request over the network.
3. The server returns status, headers, and body.
4. retrieve() creates a ResponseSpec to configure how the response is handled.
5. bodyToMono() or bodyToFlux() selects a codec to decode the response body.
6. The publisher emits data or emits an error downstream.

HTTP status and body content are two separate parts. A 404 response can still contain JSON describing the error; a 204 response may have no body; a 503 response may contain HTML from a reverse proxy instead of the API's JSON.

Do not look solely at the body to decide whether a request succeeded. Check the status with onStatus or exchangeToMono before decoding as a success type.

## 3. Default behavior of retrieve()

If you call retrieve() without registering a status handler, WebClient treats responses with 4xx or 5xx status as errors by default. It emits WebClientResponseException, containing the status, headers, request, and any response body that was read.

~~~java
Mono<Product> result = webClient.get()
    .uri("/products/{id}", productId)
    .retrieve()
    .bodyToMono(Product.class);
~~~

If the server returns 200 with valid JSON, the publisher emits Product. If the server returns 404, the publisher emits WebClientResponseException.NotFound. If the server returns 503, the publisher emits WebClientResponseException.ServiceUnavailable.

Some useful methods on WebClientResponseException:

- getStatusCode(): the status as an HttpStatusCode.
- getHeaders(): response headers.
- getResponseBodyAsString(): the body read as a string.
- getResponseBodyAsByteArray(): the body as a byte array.
- getRequest(): the request that caused the error response.
- getMessage(): general exception message.

Specific subclasses may reflect standard statuses, but application code should generally rely on getStatusCode() or map to custom business exceptions. Do not depend on every status having a named subclass.

### Default does not mean every error is a WebClientResponseException

WebClientResponseException represents a received HTTP error response. The following errors are not necessarily WebClientResponseException:

| Scenario | Typical error category |
| --- | --- |
| Server returns 404 | WebClientResponseException.NotFound if using default |
| Server returns 503 | WebClientResponseException.ServiceUnavailable if using default |
| DNS resolution fails | WebClientRequestException or connector error |
| TCP connection refused | WebClientRequestException or connector error |
| Request timeout | TimeoutException or connector exception |
| Malformed JSON response body | DecodingException / codec error |
| Downstream cancels subscription | Cancellation, not an HTTP error |

onStatus is only invoked when WebClient has received a ClientResponse and needs to evaluate its status. If there is no HTTP response, there is no status for onStatus to handle.

## 4. What is onStatus()?

ResponseSpec.onStatus() registers a status predicate and a corresponding response handler function.

General signature:

~~~java
ResponseSpec onStatus(
    Predicate<HttpStatusCode> statusPredicate,
    Function<ClientResponse, Mono<? extends Throwable>> exceptionFunction
);
~~~

Two components:

- **statusPredicate:** receives an HttpStatusCode and returns true if the status should be handled.
- **exceptionFunction:** receives ClientResponse and returns a Mono containing the exception to emit downstream.

Example:

~~~java
Mono<Product> result = webClient.get()
    .uri("/products/{id}", productId)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        response -> response.createException())
    .bodyToMono(Product.class);
~~~

This example still emits WebClientResponseException for 404, but shows how to register a custom handler. When you need to convert to a business exception, map the exception produced by createException().

### The callback must return a Mono of Throwable

The callback function does not return an exception directly:

~~~java
.onStatus(
    HttpStatusCode::is5xxServerError,
    response -> response.createException()
        .map(error -> new CatalogUnavailableException(error)))
~~~

createException() produces Mono<WebClientResponseException>. map() transforms it into Mono<CatalogUnavailableException>, which is compatible with the Mono<? extends Throwable> type required by onStatus.

Do not call block() inside the callback. WebClient is reactive; return a publisher so the framework composes it with the request lifecycle.

### Multiple status handlers

Multiple onStatus handlers can be registered:

~~~java
.retrieve()
.onStatus(
    status -> status.value() == 404,
    response -> response.createException()
        .map(ProductNotFoundException::new))
.onStatus(
    HttpStatusCode::is4xxClientError,
    response -> response.createException()
        .map(CatalogClientException::new))
.onStatus(
    HttpStatusCode::is5xxServerError,
    response -> response.createException()
        .map(CatalogUnavailableException::new))
.bodyToMono(Product.class);
~~~

Place specific handlers before general handlers. For custom handlers, WebClient applies the first handler whose predicate matches. If a broad 4xx handler is placed before 404, the subsequent 404 handler will not receive that response.

The default retrieve() handler processes 4xx/5xx when no custom handler matches.

## 5. onStatus() maps HTTP statuses to domain exceptions

You should not let every service layer depend directly on WebClientResponseException if the application needs a stable error contract. You can convert statuses into exceptions with domain or upstream-service semantics.

Example rules:

| Status from remote API | Application exception |
| --- | --- |
| 404 Not Found | ProductNotFoundException |
| 400 Bad Request | CatalogClientException or request error |
| 401/403 | CatalogAuthorizationException |
| 409 Conflict | CatalogConflictException |
| 429 Too Many Requests | CatalogRateLimitedException |
| 5xx | CatalogUnavailableException |

Mapping example:

~~~java
private RuntimeException mapError(
        String productId,
        WebClientResponseException error) {

    int status = error.getStatusCode().value();

    if (status == 404) {
        return new ProductNotFoundException(productId, error);
    }

    if (status == 429) {
        String retryAfter =
            error.getHeaders().getFirst(HttpHeaders.RETRY_AFTER);

        return new CatalogRateLimitedException(retryAfter, error);
    }

    if (error.getStatusCode().is5xxServerError()) {
        return new CatalogUnavailableException(
            error.getStatusCode(), error);
    }

    return new CatalogClientException(
        error.getStatusCode(), error);
}
~~~

At the client boundary, this mapping decouples vendor HTTP details from business services. A service can handle ProductNotFoundException without knowing how the remote API formats error codes or JSON structures.

You do not have to create a separate exception class for every status. Only create distinct types when the application handles them differently, such as returning 404, prompting the user to re-authenticate, waiting on a rate limit, or retrying a transient upstream failure.

## 6. How to read the error body?

Remote APIs often return a JSON error body:

~~~json
{
  "code": "PRODUCT_NOT_FOUND",
  "message": "No product exists with the supplied identifier"
}
~~~

There are two common ways to retrieve that information.

### Approach 1: createException() and read the body from the exception

~~~java
.onStatus(
    HttpStatusCode::isError,
    response -> response.createException()
        .map(error -> {
            log.warn("Catalog returned HTTP {}", error.getStatusCode());
            return new CatalogClientException(
                error.getStatusCode(), error);
        }))
~~~

createException() builds a WebClientResponseException and stores the status, headers, and any response body read. The application can then retrieve the body via getResponseBodyAsString() or getResponseBodyAsByteArray().

Advantages:

- No need to know in advance whether the error body is JSON.
- Information is still preserved when a reverse proxy returns HTML or plain text.
- Easy for general error mapping.

If you need to parse the body according to a specific schema, you can use getResponseBodyAs(RemoteError.class) with an appropriate codec supported by the exception, or read the body directly inside the callback.

### Approach 2: decode the body directly inside the callback

~~~java
.onStatus(
    HttpStatusCode::is4xxClientError,
    response -> response.bodyToMono(RemoteError.class)
        .defaultIfEmpty(new RemoteError("UNKNOWN", "Request failed"))
        .map(body -> new RemoteApiException(
            response.statusCode(),
            body.code(),
            body.message())))
~~~

This approach fits when the remote API guarantees a stable JSON error schema. However, if the body is empty or invalid JSON, decoding may emit a codec error instead of the intended business exception. Clearly decide how to fall back for empty, malformed, or wrong-content-type bodies.

### Do not read the response body twice

The response body is a single-consumption stream. If the callback has already called bodyToMono(RemoteError.class), downstream bodyToMono(Product.class) cannot be expected to read the same body again.

Similarly, after calling createException(), the body has already been collected into the exception. Do not invoke another body reader on the same response expecting it to remain intact.

If you need to keep the raw body and parse it multiple times, collect the body once at the boundary and then parse from the stored byte array/string; mind memory limits and avoid storing sensitive data.

## 7. Special meaning of Mono.empty() in onStatus()

A common point of confusion is that the onStatus callback can return Mono.empty().

~~~java
.retrieve()
.onStatus(
    status -> status.value() == 404,
    response -> Mono.empty())
.bodyToMono(Product.class);
~~~

Here, Mono.empty() means **do not turn this response into an exception**. WebClient continues processing the response as a normal response and passes the body to the subsequent bodyToMono(Product.class) step.

It does not mean:

- Discard the body.
- Automatically create an empty Product.
- Automatically convert 404 into Optional.empty().
- Automatically ignore all error statuses.
- Automatically release the body without further handling.

If the 404 response has a JSON error body, bodyToMono(Product.class) will still attempt to decode that body into Product. This may fail or produce an object with missing fields depending on the structure and decoder.

### When you want 404 to mean not found

If 404 must be treated as an absent result, exchangeToMono() is usually used to branch on status and control body consumption:

~~~java
public Mono<Optional<Product>> findOptional(String id) {
    return webClient.get()
        .uri("/products/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Product.class)
                    .map(Optional::of)
                    .defaultIfEmpty(Optional.empty());
            }

            if (response.statusCode().value() == 404) {
                return response.releaseBody()
                    .thenReturn(Optional.empty());
            }

            return response.createException()
                .flatMap(error ->
                    Mono.<Optional<Product>>error(mapError(id, error)));
        });
}
~~~

In the 404 branch, releaseBody() consumes/releases the body without attempting to decode it into Product, and then returns Optional.empty(). For other statuses, the code creates an exception and maps it according to standard rules.

This is a critical distinction: onStatus(... -> Mono.empty()) only skips converting the status into an exception; exchangeToMono() lets you decide the exact return value per response.

## 8. onRawStatus() for non-standard status codes

onStatus() accepts an HttpStatusCode predicate. When integrating with an upstream that uses non-standard status codes or when you want to match raw integers directly, you can use onRawStatus().

~~~java
.retrieve()
.onRawStatus(
    statusCode -> statusCode == 599,
    response -> response.createException()
        .map(UpstreamNetworkException::new))
.bodyToMono(Product.class);
~~~

599 is not a standard HTTP status code in the standard list, yet some proxies or internal systems use it as an extended error code. Only use onRawStatus when the upstream contract explicitly defines that code.

Do not use raw status to replace standard predicates if HttpStatusCode::is4xxClientError or is5xxServerError already expresses the intent.

## 9. retrieve() or exchangeToMono()/exchangeToFlux()?

Both approaches are valid, but suit different levels of control.

| Criterion | retrieve() + onStatus() | exchangeToMono()/exchangeToFlux() |
| --- | --- | --- |
| Goal | Read the body into a target type after declaring status handlers | Branch the entire response handling manually |
| Default 4xx/5xx handling | Yes, into WebClientResponseException | Check status manually |
| Exception mapping | Use onStatus | Create exceptions inside callback |
| 404 as empty | Possible, but requires understanding Mono.empty() and body | Explicit, can call releaseBody() |
| Multiple response schemas | Possible, but less intuitive | Well-suited |
| Inspecting headers/status to choose body type | Possible via status callbacks; response body is still handled by the downstream body reader | Free to read status, headers, and body per branch |
| Code length | Usually shorter | Usually longer, with explicit branches |

Use retrieve() when successful responses have one stable schema and errors can be mapped with onStatus.

Use exchangeToMono()/exchangeToFlux() when:

- 404 means Optional.empty().
- 204 has no body and needs special handling.
- 202 returns a different schema than 200.
- Headers like Location, Retry-After, or ETag must be read before deciding.
- Some statuses require parsing the body while others require discarding it.
- Different result types must be returned depending on status.

### Body release rules

With exchangeToMono()/exchangeToFlux(), the callback must handle the body properly. If not reading the body, release the body or return a publisher so the framework manages release according to the API lifecycle. Do not keep ClientResponse to use after the callback publisher completes; the response body may already have been released.

## 10. HTTP error mapping differs from transport and codec errors

onStatus is not the place to handle every error when making an HTTP call.

### HTTP error response

The server returned a response, such as 404, 429, or 503. onStatus can map these statuses into custom exceptions.

### Network/connectivity error

There is no response status if DNS fails, connection is refused, or the connection resets before headers arrive. These errors typically surface as WebClientRequestException or connector exceptions.

They can be handled separately:

~~~java
return catalogClient.findById(id)
    .onErrorMap(
        WebClientRequestException.class,
        error -> new CatalogConnectionException(error));
~~~

Do not turn every error into ProductNotFoundException or CatalogUnavailableException just because it originated from the same call.

### Timeout

A timeout can be placed on the Reactor pipeline:

~~~java
return catalogClient.findById(id)
    .timeout(Duration.ofSeconds(3));
~~~

A publisher timeout differs from an HTTP 504 returned by a server. One is a client-side wait limit; the other is a response status from a server/proxy.

### Codec/decoding error

If the server returns 200 but the body is not valid JSON for Product, the decoder emits an error. onStatus does not run because the status is not an error. Handle decode errors at the boundary if the application needs a distinct domain exception, while preserving cause details for investigation.

## 11. Conditional retry and Retry-After

Not every HTTP error should be retried. Some statuses reflect permanent errors or invalid requests:

- 400: invalid request; resending the same request usually does not help.
- 401/403: requires updated credentials or permissions.
- 404: resource does not exist.
- 409: conflict must be resolved.
- 429: can be retried after the server-requested interval.
- 5xx: may be transient, though not all 5xx errors are safe to retry.

Retries also depend on the HTTP method and idempotency. GET is generally safer than POST; POST can cause duplicate side effects if the request reached the server but the response was lost. Only retry POST when the API supports an idempotency key or has clear replay semantics.

Selective retry example for GET:

~~~java
return catalogClient.findById(id)
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .filter(CatalogUnavailableException.class::isInstance));
~~~

This example only retries errors mapped to CatalogUnavailableException. Do not retry ProductNotFoundException or other 4xx errors.

For 429, read Retry-After from headers. The header may specify a number of seconds or an HTTP-date. The client should respect the retry time provided by the server, apply a maximum retry limit, and use appropriate jitter. Do not use a short fixed backoff that ignores Retry-After.

In addition, set an overall request timeout and cap the retry count. Unbounded retries can amplify load on an upstream that is already struggling.

## 12. Exception mapping at the client boundary vs. API boundary

A WebClient client typically lives in a service calling a remote system. It maps HTTP errors into internal exceptions:

~~~text
Remote HTTP response
        |
        v
WebClient onStatus()
        |
        v
Domain / integration exception
        |
        v
Application service
        |
        v
Controller / API boundary
        |
        v
Current application's HTTP response
~~~

For example, the upstream returns 404 ProductNotFound. The current application might:

- Return 404 if its own API models that same resource.
- Return 502 if the error means an external dependency failed to fulfill its contract.
- Return a different business outcome if the domain treats a missing product as a normal state.

Do not automatically copy upstream statuses to the end client. The current API's status must reflect the contract and responsibilities of the current API.

`@RestControllerAdvice` can be used to map domain exceptions to application responses. Keep raw upstream response details in controlled logs, and never return stack traces or sensitive bodies to the end client.

## 13. Complete Java 17+ example with Spring Boot WebFlux

This example builds a CatalogClient calling a remote catalog service. It:

- Returns Product when the upstream returns 200.
- Maps 404 to ProductNotFoundException.
- Maps 429 to CatalogRateLimitedException and preserves Retry-After.
- Maps 5xx to CatalogUnavailableException.
- Maps remaining 4xx statuses to CatalogClientException.
- Provides findOptional() so 404 becomes Optional.empty() via exchangeToMono().

### Project structure

~~~text
webclient-status-demo/
├── pom.xml
└── src
    ├── main/java/com/example/catalog
    │   ├── CatalogDemoApplication.java
    │   ├── CatalogClientConfiguration.java
    │   ├── CatalogClient.java
    │   ├── Product.java
    │   └── CatalogExceptions.java
    └── test/java/com/example/catalog
        └── CatalogClientTests.java
~~~

### pom.xml

~~~xml
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
  <artifactId>webclient-status-demo</artifactId>
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
~~~

Spring Boot 3.3.5 manages compatible Spring Framework and Reactor versions. MockWebServer 4.12.0 is used only in tests to simulate a remote HTTP server.

### Product.java

~~~java
package com.example.catalog;

public record Product(String id, String name) {
}
~~~

### CatalogExceptions.java

~~~java
package com.example.catalog;

import org.springframework.http.HttpStatusCode;

class ProductNotFoundException extends RuntimeException {
    private final String productId;

    ProductNotFoundException(String productId, Throwable cause) {
        super("Product not found: " + productId, cause);
        this.productId = productId;
    }

    String getProductId() {
        return productId;
    }
}

class CatalogRateLimitedException extends RuntimeException {
    private final String retryAfter;

    CatalogRateLimitedException(String retryAfter, Throwable cause) {
        super("Catalog rate limit exceeded", cause);
        this.retryAfter = retryAfter;
    }

    String getRetryAfter() {
        return retryAfter;
    }
}

class CatalogUnavailableException extends RuntimeException {
    private final HttpStatusCode statusCode;

    CatalogUnavailableException(
            HttpStatusCode statusCode,
            Throwable cause) {
        super("Catalog service is unavailable", cause);
        this.statusCode = statusCode;
    }

    HttpStatusCode getStatusCode() {
        return statusCode;
    }
}

class CatalogClientException extends RuntimeException {
    private final HttpStatusCode statusCode;

    CatalogClientException(
            HttpStatusCode statusCode,
            Throwable cause) {
        super("Catalog rejected the request", cause);
        this.statusCode = statusCode;
    }

    HttpStatusCode getStatusCode() {
        return statusCode;
    }
}
~~~

The exceptions keep WebClientResponseException as their cause so the integration layer can inspect the original status, headers, and body. Do not return the raw cause to API callers.

### CatalogClient.java

~~~java
package com.example.catalog;

import java.util.Optional;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.core.publisher.Mono;

public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<Product> findById(String productId) {
        return webClient.get()
            .uri("/products/{id}", productId)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .onStatus(
                HttpStatusCode::is4xxClientError,
                response -> response.createException()
                    .map(error -> mapError(productId, error)))
            .onStatus(
                HttpStatusCode::is5xxServerError,
                response -> response.createException()
                    .map(error -> mapError(productId, error)))
            .bodyToMono(Product.class);
    }

    public Mono<Optional<Product>> findOptional(String productId) {
        return webClient.get()
            .uri("/products/{id}", productId)
            .accept(MediaType.APPLICATION_JSON)
            .exchangeToMono(response -> {
                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToMono(Product.class)
                        .map(Optional::of)
                        .defaultIfEmpty(Optional.empty());
                }

                if (response.statusCode().value() == 404) {
                    return response.releaseBody()
                        .thenReturn(Optional.empty());
                }

                return response.createException()
                    .flatMap(error ->
                        Mono.<Optional<Product>>error(
                            mapError(productId, error)));
            });
    }

    private RuntimeException mapError(
            String productId,
            WebClientResponseException error) {

        int status = error.getStatusCode().value();

        if (status == 404) {
            return new ProductNotFoundException(productId, error);
        }

        if (status == 429) {
            String retryAfter =
                error.getHeaders().getFirst(HttpHeaders.RETRY_AFTER);

            return new CatalogRateLimitedException(retryAfter, error);
        }

        if (error.getStatusCode().is5xxServerError()) {
            return new CatalogUnavailableException(
                error.getStatusCode(), error);
        }

        return new CatalogClientException(
            error.getStatusCode(), error);
    }
}
~~~

Key points:

1. findById() uses retrieve() and two onStatus handlers to separate 4xx from 5xx.
2. createException() collects the status, headers, and raw body into WebClientResponseException before mapping to a custom exception.
3. mapError() classifies 404, 429, 5xx, and other 4xx responses.
4. findOptional() uses exchangeToMono() to handle 404 as Optional.empty(); releaseBody() ensures the error body is not mistakenly decoded as Product.
5. The success body is only decoded after status handlers do not convert the response into an exception.

### CatalogClientConfiguration.java

~~~java
package com.example.catalog;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class CatalogClientConfiguration {

    @Bean
    WebClient catalogWebClient(WebClient.Builder builder) {
        String baseUrl = System.getProperty(
            "catalog.base-url", "http://localhost:8081");
        return builder.baseUrl(baseUrl).build();
    }

    @Bean
    CatalogClient catalogClient(WebClient catalogWebClient) {
        return new CatalogClient(catalogWebClient);
    }
}
~~~

The base URL can be passed via a system property at startup, e.g., -Dcatalog.base-url=https://catalog.example. In production, configure endpoints and credentials using proper configuration/secret management; never hardcode credentials in source code.

### CatalogDemoApplication.java

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogDemoApplication.class, args);
    }
}
~~~

### CatalogClientTests.java

~~~java
package com.example.catalog;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

import java.io.IOException;
import java.util.Optional;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.test.StepVerifier;

class CatalogClientTests {

    private MockWebServer server;
    private CatalogClient client;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        WebClient webClient = WebClient.builder()
            .baseUrl(server.url("/").toString())
            .build();

        client = new CatalogClient(webClient);
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void returnsProductForSuccessfulResponse() throws Exception {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"id\":\"p-1\",\"name\":\"Keyboard\"}"));

        StepVerifier.create(client.findById("p-1"))
            .expectNext(new Product("p-1", "Keyboard"))
            .verifyComplete();

        RecordedRequest request = server.takeRequest();
        assertEquals("GET", request.getMethod());
        assertEquals("/products/p-1", request.getPath());
    }

    @Test
    void maps404ToProductNotFound() {
        server.enqueue(new MockResponse()
            .setResponseCode(404)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"code\":\"NOT_FOUND\"}"));

        StepVerifier.create(client.findById("missing"))
            .expectError(ProductNotFoundException.class)
            .verify();
    }

    @Test
    void maps5xxToCatalogUnavailable() {
        server.enqueue(new MockResponse()
            .setResponseCode(503)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"message\":\"temporarily unavailable\"}"));

        StepVerifier.create(client.findById("p-1"))
            .expectErrorSatisfies(error -> {
                CatalogUnavailableException mapped =
                    assertInstanceOf(
                        CatalogUnavailableException.class, error);
                assertEquals(503, mapped.getStatusCode().value());
            })
            .verify();
    }

    @Test
    void maps429AndPreservesRetryAfter() {
        server.enqueue(new MockResponse()
            .setResponseCode(429)
            .addHeader("Retry-After", "5")
            .addHeader("Content-Type", "application/json")
            .setBody("{\"code\":\"RATE_LIMITED\"}"));

        StepVerifier.create(client.findById("p-1"))
            .expectErrorSatisfies(error -> {
                CatalogRateLimitedException mapped =
                    assertInstanceOf(
                        CatalogRateLimitedException.class, error);
                assertEquals("5", mapped.getRetryAfter());
            })
            .verify();
    }

    @Test
    void mapsOther4xxToCatalogClientException() {
        server.enqueue(new MockResponse()
            .setResponseCode(400)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"code\":\"INVALID_QUERY\"}"));

        StepVerifier.create(client.findById("p-1"))
            .expectError(CatalogClientException.class)
            .verify();
    }

    @Test
    void treats404AsEmptyWhenUsingOptionalContract() {
        server.enqueue(new MockResponse()
            .setResponseCode(404)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"code\":\"NOT_FOUND\"}"));

        StepVerifier.create(client.findOptional("missing"))
            .expectNext(Optional.empty())
            .verifyComplete();
    }
}
~~~

Run tests from the directory containing pom.xml:

~~~bash
mvn -q test
~~~

If all six tests pass, Maven exits with code 0. MockWebServer lets you inspect the real requests WebClient sends and simulate upstream statuses/bodies without running a separate catalog service.

## 14. Error body inspection and memory limits

createException() must collect the response body to construct WebClientResponseException. Consequently, the error body is also subject to codec memory limits. If an upstream returns an excessively large error body, reading may emit DataBufferLimitException before exception mapping completes.

You can configure the limit on WebClient:

~~~java
WebClient client = WebClient.builder()
    .baseUrl("https://catalog.example")
    .codecs(configurer ->
        configurer.defaultCodecs()
            .maxInMemorySize(256 * 1024))
    .build();
~~~

256 KiB is just an example. Choose a limit based on valid response/error body sizes and concurrency levels. Do not raise the limit indefinitely just to avoid errors; a misbehaving upstream could return a huge payload and exhaust client memory.

If you only need status and headers, consider discarding the body or using exchangeToMono() with releaseBody(). If you must log the body, limit its length and strip sensitive data.

## 15. Logging and security when mapping errors

An upstream error body can contain:

- Internal database details or stack traces.
- Tokens, queries, or user data.
- HTML from a proxy/gateway.
- Content that does not match the schema expected by the application.

Do not return the raw getResponseBodyAsString() to the end client. Log in a controlled manner:

- Upstream name and route.
- HTTP status.
- Correlation ID or trace ID.
- Parsed business error code.
- Request ID from the upstream if available.
- A redacted and length-limited snippet of the body if truly necessary.

Never log Authorization, Cookie, API keys, raw request bodies, or sensitive response bodies. Internal exceptions may retain the cause for debugging, but serializers should not automatically turn the entire cause into JSON responses.

## 16. Common mistakes and fixes

1. **Assuming retrieve() automatically returns a business exception.** By default it returns WebClientResponseException for 4xx/5xx; use onStatus to map.
2. **Checking status only inside bodyToMono().** On error statuses, the body reader may not run because retrieve already turned the response into an exception. Register handlers before bodyToMono.
3. **Returning an exception directly from the onStatus callback.** The callback must return Mono<? extends Throwable>; use Mono.error(...) or createException().map(...).
4. **Calling block() inside onStatus.** This blocks the reactive pipeline. Compose publishers using map/flatMap.
5. **Placing a broad 4xx handler before 404.** Specific handlers after it may never be called. Place specific predicates before broad predicates.
6. **Thinking Mono.empty() discards the body.** It only prevents the response from becoming an exception; the body is still processed by the downstream bodyToMono/bodyToFlux.
7. **Thinking Mono.empty() automatically produces Optional.empty().** To turn 404 into empty, use exchangeToMono(), releaseBody(), and then return Optional.empty().
8. **Reading the response body twice.** The body is a single-read stream. Pick either createException() or bodyToMono(ErrorDto.class), not both on the same body.
9. **Assuming the error body is always JSON.** Proxies can return HTML or plain text; createException() captures the raw body more safely when the schema is uncertain.
10. **Mapping all 4xx responses to the same error.** 404, 409, 429, and 401/403 have different semantics; create separate exceptions only when handling differs.
11. **Using onStatus to handle DNS or connection refused.** There is no ClientResponse when a request receives no HTTP response. Handle WebClientRequestException separately.
12. **Using onStatus to handle malformed JSON in a 200 response.** That is a codec/decode error, not a status error.
13. **Retrying every exception.** This can retry permanent failures or cause duplicate side effects. Only retry transient errors and idempotent operations.
14. **Ignoring Retry-After.** For 429, read and respect the server-requested wait interval.
15. **Returning raw upstream bodies to the caller.** This can leak internal details; return normalized error codes/messages.
16. **Not limiting error body size.** Large error bodies can consume significant memory; configure an appropriate maxInMemorySize.
17. **Using exchangeToMono() and forgetting to handle the body.** Decode or release the body on every branch.
18. **Keeping ClientResponse to use after the callback finishes.** Response/body lifecycles are bounded; convert into domain values or exceptions right inside the callback.
19. **Equating upstream status codes with your own API's statuses.** The API boundary must enforce your own application's contract.
20. **Only unit-testing mapError.** Also test real HTTP responses, bodies, status handlers, and actual requests using MockWebServer.

## 17. WebClient error mapping design checklist

Before shipping an HTTP client, determine:

- **Success schema:** which type is a 2xx response decoded into?
- **Default behavior:** which exception do unhandled 4xx/5xx responses become?
- **Status mapping:** which statuses need custom business exceptions?
- **Handler order:** do specific predicates come before general predicates?
- **Error body:** is the schema stable, or could it be empty or HTML?
- **Body ownership:** does the callback consume the body exactly once?
- **Empty semantics:** is 404 an error, Optional.empty(), or another domain result?
- **Alternative API:** is retrieve() sufficient, or is exchangeToMono()/exchangeToFlux() needed?
- **Raw status:** does the upstream use extended statuses requiring onRawStatus()?
- **Transport errors:** are DNS, connection, and timeout errors handled separately?
- **Codec errors:** are malformed JSON and DataBufferLimitException observed?
- **Retry:** are only transient errors and idempotent operations retried?
- **Rate limit:** is Retry-After read and the retry count bounded?
- **Security:** are tokens, PII, and stack traces stripped from logs/responses?
- **Testing:** does MockWebServer verify 2xx, 404, 429, 5xx, other 4xx, and optional 404?

## 18. Self-check exercises

**Exercise 1.** retrieve() receives status 404 with no onStatus handler. What is the typical default exception?  
**Answer:** WebClientResponseException.NotFound, which is a subclass of WebClientResponseException.

**Exercise 2.** What parameters does onStatus accept?  
**Answer:** A Predicate<HttpStatusCode> to select statuses and a Function<ClientResponse, Mono<? extends Throwable>> to produce the exception.

**Exercise 3.** Why does the onStatus callback return a Mono of an exception?  
**Answer:** Because reading the response body is asynchronous and must be composed into the reactive pipeline.

**Exercise 4.** What does an onStatus handler returning Mono.empty() mean?  
**Answer:** The response is not converted into an exception; the body continues to be processed by the downstream bodyToMono/bodyToFlux.

**Exercise 5.** When you want 404 to become Optional.empty(), what approach should you use?  
**Answer:** Use exchangeToMono(), check for status 404, call releaseBody(), and return Optional.empty().

**Exercise 6.** What is the benefit of createException()?  
**Answer:** It creates a WebClientResponseException containing status, headers, request, and raw response body, even when the body is not valid JSON.

**Exercise 7.** Does onStatus handle DNS failures?  
**Answer:** No. There is no HTTP response and thus no status; handle WebClientRequestException or connector errors instead.

**Exercise 8.** What happens if a response returns 200 with malformed JSON?  
**Answer:** The codec emits a decode error; onStatus does not run because the status is not an HTTP error.

**Exercise 9.** Why should a 404 handler be placed before a general 4xx handler?  
**Answer:** The first handler whose predicate matches is applied; a general predicate placed first will also capture 404.

**Exercise 10.** Should 404 be retried?  
**Answer:** Usually not; a missing resource is not a transient error. Only retry if the domain has special semantics.

**Exercise 11.** Which header does 429 typically provide to guide retries?  
**Answer:** Retry-After; the value may be a number of seconds or an HTTP-date.

**Exercise 12.** Why should you not return the raw upstream response body to users?  
**Answer:** The body may contain internal details, sensitive data, or stack traces; normalize it into safe error codes.

## 19. Key takeaways

retrieve() converts 4xx/5xx responses into WebClientResponseException by default. onStatus() lets you match statuses using Predicate<HttpStatusCode> and map ClientResponse into a Mono of an exception. createException() is a general-purpose option when you need to preserve status, headers, and raw body; bodyToMono(ErrorDto.class) fits when the upstream has a stable error schema.

Mono.empty() from onStatus only skips turning the response into an exception; it does not automatically discard the body or produce Optional.empty(). When 404 needs to represent an absent result, exchangeToMono() lets you branch by status, release the body, and return the appropriate value.

onStatus only handles HTTP response statuses. DNS, connection, timeout, and decode errors belong to separate categories. Retries should be based on error type, idempotency, and Retry-After. Finally, map upstream errors into domain exceptions at the client boundary, and let the API boundary decide the status and message that fit the application's contract.

### References

- Spring Framework, [WebClient – retrieve() and exchangeToMono()](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html).
- Spring Framework, [WebClient – Request and Response Body](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html).
- Spring Framework Javadoc, [WebClient.ResponseSpec](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClient.ResponseSpec.html).
- Spring Framework Javadoc, [ClientResponse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ClientResponse.html).
- Spring Framework Javadoc, [WebClientResponseException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClientResponseException.html).
- Spring Framework, [WebClient Configuration and Codecs](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html).
- Project Reactor, [Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- OkHttp, [MockWebServer](https://square.github.io/okhttp/4.x/mockwebserver/okhttp3.mockwebserver/).
