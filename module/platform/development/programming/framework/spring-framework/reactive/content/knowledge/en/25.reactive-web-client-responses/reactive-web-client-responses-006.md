# Consuming or releasing the body on every handling branch

When using **Spring WebClient**, each HTTP response has a body read reactively. The body may contain JSON, text, binary data, or a long stream. An unconsumed or unreleased response body can hold onto a DataBuffer, preventing the connection from being properly reused or creating resource pressure. Therefore, every response-handling branch needs a clear decision: **decode the body**, **drain and release the body**, or **forward the response intact for downstream to consume**.

This rule is especially important when using APIs that access the response directly, such as **exchangeToMono**, **exchangeToFlux**, **ExchangeFilterFunction**, or **ExchangeFunction**. When using **retrieve()**, WebClient provides standard body extraction and status handling steps, though custom status handlers must still be designed properly.

This lesson focuses on the WebClient body lifecycle, handling success/error/not-found/empty responses, writing safe filters and retries, and a Java 17 example with tests for every branch.

## 1. Learning objectives

After this lesson, you can:

1. Explain why a response body must be consumed or released.
2. Distinguish **retrieve()** from **exchangeToMono()** and **exchangeToFlux()**.
3. Use **bodyToMono**, **bodyToFlux**, **toEntity**, **toBodilessEntity**, and **releaseBody** for their intended purposes.
4. Handle success, 404, 204, and 4xx/5xx statuses without abandoning the body.
5. Understand the exact meaning of **onStatus** when a handler returns **Mono.empty()**.
6. Write an **ExchangeFilterFunction** so it only keeps a response when downstream will continue consuming it.
7. Handle bodies across all error, retry, timeout, and cancellation branches.
8. Avoid reading the body multiple times or returning **ClientResponse** outside **exchangeToMono** for deferred decoding.
9. Distinguish **releaseBody()** from **bodyToMono(Void.class)**.
10. Test lifecycle behavior using MockWebServer, Reactor Test, and WebClient.

## 2. Why must a response body be handled?

WebClient is a reactive HTTP client. The response body is typically delivered as a byte stream and decoded incrementally through codecs. With Reactor Netty, bytes may reside in pooled direct memory. The framework needs to know when the body has been fully read or when the remainder can be discarded.

If a branch receives a response and ignores the body:

- Buffers may not be released on time.
- The connection may not return to the pool for reuse.
- Subsequent requests may have to open new connections.
- When many responses are abandoned, memory, sockets, or the connection pool can come under pressure.
- Retries may fire new requests while the previous response has not been fully handled.

Every response body is a lifecycle-bound resource. Reading the status or headers does not mean the body has been consumed.

### 2.1. Three valid choices for each branch

| Decision | How to do it | When appropriate |
| --- | --- | --- |
| Decode body | bodyToMono, bodyToFlux, toEntity, or body(BodyExtractor) | Application needs response data |
| Discard body | releaseBody() or toBodilessEntity() | Only status/headers are needed, or deciding to discard the response |
| Forward response | Return ClientResponse to downstream | A filter wants the caller to continue reading the body |

Never read the body and also expect another component to re-read the same body from the start. The body is a one-shot stream; once consumed, the publisher cannot be replayed like an ordinary Java object.

### 2.2. Reading headers without consuming the body

The following example only checks status:

~~~java
return webClient.get()
    .uri("/api/items/42")
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return Mono.just(response.statusCode().value());
        }
        return Mono.just(response.statusCode().value());
    });
~~~

The callback does not read the body. With exchangeToMono, Spring automatically releases any unconsumed body once the callback publisher completes. This is a helpful safety net, but if the code intends to discard the body, calling releaseBody() explicitly makes intent clearer and easier to review.

If using a raw ExchangeFunction or a filter that retains/replaces responses, the responsibility to forward or release must be clearly defined on every branch.

## 3. APIs for reading and releasing the body

### 3.1. bodyToMono and bodyToFlux

Use bodyToMono(Type.class) when the response contains a single object or a body to decode into one value:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(Product.class);
~~~

Use bodyToFlux(Type.class) when the body represents a stream of elements and the codec/media type supports it:

~~~java
Flux<Product> products = webClient.get()
    .uri("/products")
    .retrieve()
    .bodyToFlux(Product.class);
~~~

These publishers consume the body when subscribed to and data is demanded. If the caller does not subscribe, the request is not executed under normal reactive semantics. If the caller subscribes and cancels early, handling of the remainder depends on the transport and cancellation lifecycle; taking a single element should not be equated with draining the entire response.

### 3.2. toEntity and toBodilessEntity

toEntity(Product.class) returns a ResponseEntity<Product> containing status, headers, and decoded body:

~~~java
Mono<ResponseEntity<Product>> entity = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .toEntity(Product.class);
~~~

toBodilessEntity() returns status and headers without retaining a body. It consumes/releases the body and fits endpoints where the application only cares about metadata:

~~~java
Mono<ResponseEntity<Void>> result = webClient.delete()
    .uri("/products/{id}", id)
    .retrieve()
    .toBodilessEntity();
~~~

If you need the body, do not use toBodilessEntity() and try to decode it again afterward.

### 3.3. releaseBody()

ClientResponse.releaseBody() returns Mono<Void> and consumes the body to release content the application does not need:

~~~java
Mono<Void> discarded = response.releaseBody();
~~~

Use it in a branch that has decided to discard the body, such as 404 mapped to Optional.empty or a filter rejecting a response based purely on status.

releaseBody() does not return the body to subsequent code. Once the publisher completes, the response body has been handled for discard.

### 3.4. bodyToMono(Void.class) is not the same as releaseBody()

You may encounter:

~~~java
response.bodyToMono(Void.class)
~~~

Spring documentation notes that if the response actually has content, this may cause the connection to be closed rather than returned to the pool, because the body content is not drained the way releaseBody() does. When the goal is to discard the body and release content, prefer releaseBody() or toBodilessEntity().

If the API guarantees the response has no body, bodyToMono(Void.class) may fit, but it should not be used as a general substitute for releasing.

## 4. retrieve(): the common handling path

retrieve() fits when the logic is mainly calling an endpoint and decoding the body. Example:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .bodyToMono(Product.class);
~~~

By default, 4xx or 5xx response statuses are mapped to WebClientResponseException. WebClient constructs the exception with status, headers, request, and the response body read into the exception. Thus, error bodies are also handled by default rather than left abandoned.

### 4.1. Reading the error body in onStatus

When the remote API returns an error DTO, you can decode the body and build a business exception:

~~~java
Mono<Product> product = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .onStatus(HttpStatusCode::isError, response ->
        response.bodyToMono(ApiError.class)
            .defaultIfEmpty(new ApiError("remote error"))
            .map(error ->
                new RemoteServiceException(error.message())
            )
    )
    .bodyToMono(Product.class);
~~~

The onStatus handler returns Mono<? extends Throwable>. The example above reads the body into ApiError before creating the exception, so the body has been consumed.

If the error body is not needed, you can release it and return an exception:

~~~java
.onStatus(
    status -> status.value() == 503,
    response -> response.releaseBody()
        .thenReturn(new RemoteUnavailableException())
)
~~~

This branch explicitly discards the body before emitting the error.

### 4.2. Meaning of Mono.empty() in onStatus

This rule is very easy to misunderstand:

~~~java
.onStatus(
    status -> status.value() == 404,
    response -> Mono.empty()
)
.bodyToMono(Product.class);
~~~

Mono.empty() in an onStatus handler means **do not generate an error signal for that status**. WebClient treats the response as normal and continues passing the response to the downstream body extraction step. It does not automatically mean "discard the response body."

Therefore, if you want to read a 404 body as a DTO, you can suppress the status error and decode downstream. If you want to discard the body and return Optional.empty, use exchangeToMono with releaseBody() to state both decisions explicitly.

Do not read the body inside onStatus, return Mono.empty(), and expect the downstream bodyToMono to still see the original content. The body is consumed once.

### 4.3. onStatus returning an exception without reading the body

When a custom handler returns an error without consuming the body, WebClient runs cleanup for status handlers to release the unconsumed body. However, in code review, intent should be made explicit:

- Need error details: decode the body in the handler.
- Do not need error details: call releaseBody before creating the exception.
- Want to treat the status as a normal response: return Mono.empty and let downstream decode the body.

Writing explicitly avoids forcing readers to know internal cleanup details.

## 5. exchangeToMono(): every branch inside the callback

exchangeToMono lets you inspect status/headers and then decide how to decode. It is a good fit when success, 404, 204, and errors have different body contracts.

Example:

~~~java
Mono<Optional<Product>> findProduct(String id) {
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

            return response.createError();
        });
}
~~~

Each branch makes a clear body decision:

- 2xx: decode into Product.
- 404: discard the body via releaseBody and return Optional.empty.
- Other statuses: createError builds an error from the response and handles the error body.

After the publisher returned by the callback completes, Spring checks the response body. If the callback did not consume the body, Spring automatically releases the unread portion to prevent memory/connection leaks. However, the body cannot be decoded further downstream after the callback finishes.

### 5.1. 204 No Content

For endpoints that can return 204, do not try to decode a DTO:

~~~java
if (response.statusCode().value() == 204) {
    return response.toBodilessEntity()
        .thenReturn(Optional.empty());
}
~~~

toBodilessEntity() captures status/headers and discards any body if present. For 204 under HTTP semantics, the server should not send response content; this style still makes clear that the code needs no body.

### 5.2. Do not return ClientResponse to decode after the callback

Do not write:

~~~java
Mono<ClientResponse> responseMono = webClient.get()
    .uri("/products/42")
    .exchangeToMono(response -> Mono.just(response));

return responseMono.flatMap(response ->
    response.bodyToMono(Product.class)
);
~~~

exchangeToMono manages the response lifecycle inside the callback. When the callback publisher completes without consuming the body, the framework releases the body. Consequently, downstream code receives a response that can no longer read the body as intended.

Decode or release right inside the callback:

~~~java
return webClient.get()
    .uri("/products/42")
    .exchangeToMono(response ->
        response.bodyToMono(Product.class)
    );
~~~

### 5.3. createError and createException

- createException() produces Mono<WebClientResponseException> containing status, headers, request, and the read body.
- createError() creates a publisher emitting the corresponding exception, convenient in exchangeToMono branches.
- If a custom exception type is needed, decode the error DTO and build the business exception.
- If the body is not needed, call releaseBody before creating the application exception.

Do not call createException() twice on the same response expecting to read the body twice. The body is a single-use resource.

## 6. exchangeToFlux(): handling streams and status

exchangeToFlux applies the same principle to multi-element responses:

~~~java
Flux<Product> products = webClient.get()
    .uri("/products")
    .exchangeToFlux(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToFlux(Product.class);
        }

        return response.createError().flux();
    });
~~~

The success branch converts the body into Flux<Product>. The error branch creates an error from the response. When the callback Flux completes, any unconsumed response body is automatically released.

If downstream consumes only part of the stream and cancels, the transport receives cancellation. For data that must be discarded completely, choose releaseBody() in the callback instead of creating a body Flux and letting nobody subscribe.

Example of an endpoint returning a stream when the client only needs metadata:

~~~java
Mono<Integer> statusOnly = webClient.get()
    .uri("/exports")
    .exchangeToMono(response ->
        response.releaseBody()
            .thenReturn(response.statusCode().value())
    );
~~~

This branch neither decodes the stream nor retains DataBuffers for downstream.

## 7. Handling in ExchangeFilterFunction

A client filter runs between the WebClient request and the exchange function. The filter receives the response before the caller reads the body.

### 7.1. Modify only the request, forward the response intact

If a filter only adds a request header, there is no need to read the body:

~~~java
ExchangeFilterFunction addClientHeader =
    (request, next) -> {
        ClientRequest updated = ClientRequest.from(request)
            .header("X-Client-App", "catalog")
            .build();

        return next.exchange(updated);
    };
~~~

The response is forwarded intact to the caller. The caller is responsible for decoding or releasing the body via retrieve/exchangeTo.

### 7.2. Filter rejecting error responses without needing the body

If a filter decides to convert all error statuses into a generic exception, it must release the body before emitting the error:

~~~java
ExchangeFilterFunction rejectErrorStatus =
    (request, next) -> next.exchange(request)
        .flatMap(response -> {
            if (response.statusCode().isError()) {
                HttpStatusCode status = response.statusCode();

                return response.releaseBody()
                    .then(Mono.error(
                        new RemoteStatusException(status)
                    ));
            }

            // Success response is forwarded for the caller to read the body.
            return Mono.just(response);
        });
~~~

The success branch returns the response to downstream; the filter does not read the body. The error branch discards the body and emits an exception; no response is forwarded further.

### 7.3. Filter needing the error body content

If the filter needs the error content to construct an exception:

~~~java
ExchangeFilterFunction mapRemoteErrors =
    (request, next) -> next.exchange(request)
        .flatMap(response -> {
            if (!response.statusCode().isError()) {
                return Mono.just(response);
            }

            return response.bodyToMono(ApiError.class)
                .defaultIfEmpty(new ApiError("unknown remote error"))
                .flatMap(error ->
                    Mono.error(
                        new RemoteServiceException(error.message())
                    )
                );
        });
~~~

The body is decoded in the filter, and then the filter emits an error. Do not return an already-consumed response for the caller to read again.

### 7.4. Filter inspecting the body and still wanting to forward

If a filter needs to read the body for logging while the caller still needs the body, the filter must design bounded buffering and body reconstruction. Reading the body into byte[] can aggregate the entire payload, so it only fits small responses with clear size limits.

For large files/streams, do not enable full-body logging. Prefer logging status, filtered headers, duration, content length, and correlation ID. When payload inspection is required, use specialized instrumentation with size limits and masking.

## 8. Branch matrix: checking every path

Before writing code, list all status outcomes and the corresponding body decision:

| Scenario | Need body data? | Action |
| --- | --- | --- |
| 200 JSON | Yes | bodyToMono DTO |
| 200 stream | Yes | bodyToFlux and consume on demand |
| 201 Created | Yes or no | bodyToMono/toEntity or toBodilessEntity |
| 204 No Content | No | toBodilessEntity/releaseBody |
| 404 treated as empty | No | releaseBody then return empty |
| 404 needing detailed message | Yes | decode error body then map |
| 401/403 | Possibly not | decode error or release then create exception |
| 429/503 retry | Depends | consume/decode or release before emitting retry error |
| Unexpected 5xx | May need diagnostics | createError or decode error DTO |
| Unexpected status | No | releaseBody then emit error |
| Filter modifying only request | Do not read response | forward original response downstream |
| Filter blocking response | Depends | consume or release before returning error |

Every row is an independent branch. Do not let a status pass through a return Mono.just(response) branch if no downstream component takes responsibility for reading the body.

## 9. Retry, timeout, cancellation, and decode errors

### 9.1. Retrying after an error status

Retries create a new subscription/request. If an error response is converted into an exception for retry, the previous response's body must be handled before the retry proceeds.

Example using exchangeToMono:

~~~java
Mono<Product> loadWithRetry(String id) {
    return webClient.get()
        .uri("/products/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Product.class);
            }

            if (response.statusCode().value() == 503) {
                return response.releaseBody()
                    .then(Mono.error(new RetryableRemoteException()));
            }

            return response.createError();
        })
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
                .filter(RetryableRemoteException.class::isInstance)
        );
}
~~~

The 503 branch releases the body before the error reaches the retry operator. Other status branches use createError to read the response and emit an exception. Do not retry every error blindly; distinguish transient errors, validation errors, authorization errors, and decode errors.

### 9.2. Timeout

timeout can cancel a publisher that is reading the body. Cancellation must propagate to the transport to stop receiving data. If code holds a DataBuffer directly or opens a file/channel, it must clean up on cancellation lifecycle.

Do not catch a timeout and abandon an active publisher/body without knowing which resources remain held. Set reasonable timeouts based on API type, body size, and SLA.

### 9.3. Decode errors

If bodyToMono or bodyToFlux emits a decode error, the codec is responsible for managing DataBuffers per its contract. Application code should not manually release buffers already consumed by the codec. If using bodyToFlux(DataBuffer.class) directly, the application assumes ownership at the DataBuffer level and must release after reading or forwarding properly.

### 9.4. Cancellation while reading a stream

If the caller cancels the stream mid-way, do not keep holding the subscription or cache the body for reuse. With a raw DataBuffer stream, release each received buffer and ensure discarded buffers are cleaned up if the pipeline has operators that can drop elements.

If the intent is to discard the entire response from the start, use releaseBody() rather than subscribing partially and cancelling.

## 10. Reading DataBuffer directly

Normally decode the body into a DTO/String. Only receive DataBuffer directly when byte-level processing, proxying, checksumming, or streaming to a file is needed.

Example calculating the size of each buffer:

~~~java
Mono<Long> countBytes(ClientResponse response) {
    return response.bodyToFlux(DataBuffer.class)
        .map(buffer -> {
            try {
                return (long) buffer.readableByteCount();
            }
            finally {
                DataBufferUtils.release(buffer);
            }
        })
        .reduce(0L, Long::sum);
}
~~~

Here the code consumes the DataBuffer itself, so it releases it in finally. Do not release the buffer again in a downstream operator. If handing the buffer off to a writer or API that takes ownership, let the receiver manage it per contract.

Do not use collectList() to hold all DataBuffers. For large files, write each buffer to a file or update a digest and release immediately.

## 11. Java 17 example: WebClient handling every branch

The example uses Spring Boot 3.3.5 and Java 17. The client has two call patterns:

- findProduct uses exchangeToMono: 2xx decodes DTO, 404 releases and returns Optional.empty, other statuses create an error.
- getProductWithRetrieve uses retrieve: reads error DTO in onStatus and builds a business exception.

### 11.1. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 11.2. DTO and exception

~~~java
package demo;

record Product(String id, String name) {}
record ApiError(String message) {}

class RemoteServiceException extends RuntimeException {
    RemoteServiceException(String message) {
        super(message);
    }
}
~~~

### 11.3. ProductClient.java

~~~java
package demo;

import java.util.Optional;

import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
class ProductClient {

    private final WebClient client;

    ProductClient(WebClient client) {
        this.client = client;
    }

    Mono<Optional<Product>> findProduct(String id) {
        return client.get()
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

                return response.createError();
            });
    }

    Mono<Product> getProductWithRetrieve(String id) {
        return client.get()
            .uri("/products/{id}", id)
            .retrieve()
            .onStatus(HttpStatusCode::isError, response ->
                response.bodyToMono(ApiError.class)
                    .defaultIfEmpty(new ApiError("remote error"))
                    .map(error ->
                        new RemoteServiceException(error.message())
                    )
            )
            .bodyToMono(Product.class);
    }

    Mono<Integer> statusOnly(String id) {
        return client.get()
            .uri("/products/{id}", id)
            .exchangeToMono(response ->
                response.releaseBody()
                    .thenReturn(response.statusCode().value())
            );
    }
}
~~~

Taking WebClient directly in the constructor lets tests supply a local base URL. In a Spring Boot application, create a WebClient bean configured with WebClient.Builder and inject it into the client service.

### 11.4. ProductClientTest.java

~~~java
package demo;

import java.io.IOException;
import java.util.Optional;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProductClientTest {

    private MockWebServer server;
    private ProductClient client;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        WebClient webClient = WebClient.builder()
            .baseUrl(server.url("/").toString())
            .build();

        client = new ProductClient(webClient);
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void successBranchDecodesBody() {
        server.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"id\":\"p-1\",\"name\":\"Keyboard\"}"));

        StepVerifier.create(client.findProduct("p-1"))
            .expectNext(Optional.of(
                new Product("p-1", "Keyboard")
            ))
            .verifyComplete();
    }

    @Test
    void notFoundBranchReleasesBodyAndReturnsEmpty() {
        server.enqueue(new MockResponse()
            .setResponseCode(404)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"message\":\"not found\"}"));

        StepVerifier.create(client.findProduct("missing"))
            .expectNext(Optional.empty())
            .verifyComplete();
    }

    @Test
    void unexpectedStatusBecomesWebClientResponseException() {
        server.enqueue(new MockResponse()
            .setResponseCode(502)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"message\":\"gateway failed\"}"));

        StepVerifier.create(client.findProduct("p-2"))
            .expectErrorSatisfies(error -> {
                assertTrue(error instanceof WebClientResponseException);
                WebClientResponseException responseError =
                    (WebClientResponseException) error;
                assertEquals(502, responseError.getStatusCode().value());
                assertTrue(
                    responseError.getResponseBodyAsString()
                        .contains("gateway failed")
                );
            })
            .verify();
    }

    @Test
    void retrieveCustomStatusHandlerConsumesErrorDto() {
        server.enqueue(new MockResponse()
            .setResponseCode(503)
            .addHeader("Content-Type", "application/json")
            .setBody("{\"message\":\"catalog unavailable\"}"));

        StepVerifier.create(
                client.getProductWithRetrieve("p-3")
            )
            .expectErrorSatisfies(error -> {
                assertTrue(error instanceof RemoteServiceException);
                assertEquals(
                    "catalog unavailable",
                    error.getMessage()
                );
            })
            .verify();
    }

    @Test
    void statusOnlyBranchDiscardsBody() {
        server.enqueue(new MockResponse()
            .setResponseCode(202)
            .addHeader("Content-Type", "text/plain")
            .setBody("accepted"));

        StepVerifier.create(client.statusOnly("p-4"))
            .expectNext(202)
            .verifyComplete();
    }
}
~~~

The tests verify the success branch, 404 body discard, unexpected status conversion to WebClientResponseException with body, custom status handler decoding error DTO, and the status-only branch releasing the body.

Run tests:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

The example uses MockWebServer to produce local responses; no external service calls are needed. The tests verify branch-handling behavior, though they do not replace load tests for connection pools or memory under high load.

## 12. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Reading status and ignoring response body | Buffers/connections may not be released promptly | Decode or call releaseBody on the branch |
| Using exchangeToMono and returning ClientResponse downstream | Body may be auto-released when the callback finishes | Decode or release right inside the callback |
| Thinking Mono.empty in onStatus discards the body | Downstream still receives the response and may try to decode the body | Understand it suppresses the error; use releaseBody to discard |
| Calling bodyToMono twice | Body is a one-shot stream; the second call lacks expected data | Decode once into a DTO and share the object |
| Using bodyToMono(Void.class) to discard a large body | Connection may close if the response actually has content | Use releaseBody or toBodilessEntity |
| Filter reading the body and returning the old response | Downstream receives an already-consumed body | Create a new response with buffered body (small bodies only) or do not inspect body |
| Filter returning Mono.error while abandoning the body | Response is not forwarded and body is unhandled | Call releaseBody before emitting the error |
| Filter reading success body while still returning ClientResponse | Caller has no body left to decode | Only read if the filter owns the result, or rebuild within bounds |
| Retrying before the error response is handled | Connection and buffers from the previous attempt may remain held | Decode/release body before emitting the retryable error |
| Using bodyToFlux followed by take(1) to discard the whole body | Stream cancels after one part; not equivalent to draining | Use releaseBody when no content is needed |
| Using createException and reading the body again | Body was already consumed to build the exception | Use the data stored in the exception |
| Logging the entire error body | Can leak tokens, personal data, and large payloads | Log status, request ID, and filtered messages |
| Aggregating error bodies without bounds | Memory can spike when upstream returns large error payloads | Cap decoder limits, read only small DTOs, or release |
| Calling subscribe inside a filter | Creates a subscription detached from the request lifecycle | Return the composed publisher |
| Not testing 204/404/error branches | Bodies may be overlooked on rare branches | Build a branch matrix and test each branch |

## 13. Checklist for reviewing every response branch

For every piece of code receiving ClientResponse, check in order:

1. **Success:** is the body decoded via bodyToMono/bodyToFlux/toEntity or forwarded to the caller?
2. **No content:** is toBodilessEntity/releaseBody used when no body is needed?
3. **Not found:** is returning empty, an error DTO, or WebClientResponseException intentional?
4. **4xx/5xx:** is the body decoded into an exception or released before emitting the error?
5. **Unexpected status:** does the default branch call createError or releaseBody?
6. **Filter:** is a success response forwarded intact downstream? Do blocking branches release?
7. **Retry:** is the previous response consumed/released before retrying?
8. **Cancellation:** does the publisher stop cleanly and are self-managed buffers released?
9. **Single consumption:** are multiple body extraction methods ever called on the same response?
10. **Memory:** are large payloads aggregated or full bodies logged?
11. **Connection:** is releaseBody used instead of bodyToMono(Void.class) when draining is needed?
12. **Tests:** do all status branches test both body-present and body-empty cases as appropriate?

**Key takeaway:** every HTTP response body must have a clear owner. Decode the body if data is needed; call releaseBody or toBodilessEntity if discarding; forward the response intact if downstream will read it. With exchangeToMono/exchangeToFlux, handle the body right inside the callback because Spring auto-releases unread content after the callback finishes. With retrieve/onStatus, remember that Mono.empty only suppresses the error and lets subsequent decoding continue. Write a branch matrix, test every branch, and avoid reading the body multiple times.

## References

- Spring Framework — WebClient Exchange: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Spring Framework — WebClient Retrieve: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework — ClientResponse API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ClientResponse.html
- Spring Framework — ExchangeFilterFunction API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ExchangeFilterFunction.html
- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
