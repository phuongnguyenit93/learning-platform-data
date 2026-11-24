# exchangeToMono and exchangeToFlux for per-status branching in Spring WebClient

## 1. When do you need to branch by HTTP status?

Spring WebClient offers two common ways to read a response:

- **retrieve()** fits when successful responses are decoded into a uniform type and 4xx/5xx errors are handled via onStatus or WebClientResponseException.
- **exchangeToMono()** and **exchangeToFlux()** fit when decoding or the business outcome depends directly on the response status, headers, or body kind.

For example, a product lookup API might return:

| HTTP status | Body | Desired client outcome |
| --- | --- | --- |
| 200 OK | Product JSON | Decode into Product |
| 201 Created | Product JSON | Decode into Product |
| 204 No Content | No body | Empty result |
| 404 Not Found | Error JSON or text | Optional.empty or not-found domain result |
| 400 Bad Request | Error JSON | Business exception with error code |
| 503 Service Unavailable | Error body | WebClientResponseException preserving status and body |

If all success statuses return the same data type and default 4xx/5xx errors suffice, retrieve() is usually shorter and easier to read. If 404 must become Optional.empty, 204 must become an empty result, 400 must decode ErrorPayload, and 503 must preserve WebClientResponseException, exchangeToMono() keeps those branches in one place.

For APIs returning multi-element streams such as large lists, NDJSON, or server-sent events, use exchangeToFlux() to inspect the status before emitting data.

## 2. WebClient and ClientResponse

### 2.1. WebClient is a reactive HTTP client

WebClient provides a Reactor-based fluent API that is non-blocking and supports streaming. A request typically follows these steps:

~~~text
WebClient request builder
        |
        v
HTTP request is sent
        |
        v
ClientResponse receives status + headers + body
        |
        v
exchangeToMono / exchangeToFlux callback
        |
        +--> decode body into object
        +--> emit Flux of data
        +--> create error
        +--> intentionally discard body
~~~

ClientResponse lets you read:

- statusCode(): HTTP status as an HttpStatusCode.
- headers(): response headers.
- cookies(): response cookies.
- bodyToMono(Class): decodes the body into at most one object.
- bodyToFlux(Class): decodes the body into a stream of objects.
- releaseBody(): consumes and releases the body when its content is not needed.
- createException(): creates a WebClientResponseException containing status, headers, body, and original request.
- createError(): returns a Mono emitting a WebClientResponseException with response details.

Do not hold onto ClientResponse to use after the callback. Decide how to consume the body inside the exchangeToMono or exchangeToFlux callback.

### 2.2. HttpStatusCode in modern Spring

Spring Framework 6 uses the **HttpStatusCode** abstraction for status APIs. You do not need to force every status into the HttpStatus enum, since a server may return a valid status code that has no corresponding enum constant.

~~~java
HttpStatusCode status = response.statusCode();

if (status.is2xxSuccessful()) {
    // 2xx
} else if (status.is4xxClientError()) {
    // 4xx
} else if (status.is5xxServerError()) {
    // 5xx
}

int code = status.value();
~~~

You can compare exact codes with status.value() == 404 or status.isSameCodeAs(HttpStatus.NOT_FOUND). Checking the 2xx family is more flexible than checking only 200 OK, since an API may return 201 Created or 202 Accepted.

## 3. exchangeToMono(): branching to return a single result

### 3.1. Contract

exchangeToMono accepts a function that processes ClientResponse and requires it to return a Mono:

~~~java
Mono<Product> result = webClient.get()
        .uri("/products/{id}", id)
        .accept(MediaType.APPLICATION_JSON)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Product.class);
            }
            return response.createError();
        });
~~~

This snippet is a basic illustration. The callback receives the response once status and headers are available. The callback must decide what type to decode the body into or whether to turn the response into an error.

The result can be a Mono emitting a value, a Mono completing empty, a Mono emitting an error, or another reactive pipeline built from the decoded data.

### 3.2. Crucial rules about the response body

After the Mono returned by the callback completes, WebClient checks the response body. If the callback has not consumed the body, the framework automatically releases it to prevent memory and connection leaks.

This means:

1. If data is needed, the callback must call bodyToMono, bodyToFlux, or an appropriate decode API.
2. If intentionally skipping the body, you can call releaseBody() to state that intent clearly.
3. After the callback finishes, you cannot pull ClientResponse out and decode the body downstream.
4. The response body is a one-shot source. Do not call bodyToMono twice to both log and decode.
5. If you need to inspect the content and reuse it, decode once into byte[], String, or a DTO and work with that value.

Auto-release is a resource safety net, not a substitute for designing body-handling branches.

### 3.3. 404 as an empty business result

A GET /products/{id} endpoint may treat 404 as product not found rather than a system error:

~~~java
Mono<Optional<Product>> findProduct(String id) {
    return webClient.get()
            .uri("/products/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .exchangeToMono(response -> {
                int status = response.statusCode().value();

                if (status == 404) {
                    return response.releaseBody()
                            .thenReturn(Optional.<Product>empty());
                }

                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToMono(Product.class)
                            .map(Optional::of)
                            .defaultIfEmpty(Optional.<Product>empty());
                }

                return response.createError();
            });
}
~~~

The 404 branch consumes and releases the body and returns Optional.empty(). The 2xx branch decodes Product; if the server returns a success response with an empty body, defaultIfEmpty also returns Optional.empty().

If the business logic must distinguish 404 from 204, use a clearer result type such as a sealed interface or a record with status. Do not merge two statuses if they carry different business meanings.

### 3.4. 204 No Content

204 is a successful response with no content. Do not attempt to decode it into a DTO:

~~~java
if (status == 204) {
    return response.releaseBody()
            .thenReturn(Optional.<Product>empty());
}
~~~

For update APIs that only confirm success, you can return Mono<Void>:

~~~java
Mono<Void> updateProduct(String id, ProductUpdate update) {
    return webClient.put()
            .uri("/products/{id}", id)
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(update)
            .exchangeToMono(response -> {
                if (response.statusCode().is2xxSuccessful()) {
                    return response.releaseBody();
                }
                return response.createError();
            });
}
~~~

If an endpoint can return 200 with a body or 204 without a body, handle the two branches separately to preserve the contract.

### 3.5. 400/422 decoding an error body into a domain exception

Some APIs return a custom error structure:

~~~json
{
  "code": "INVALID_PRODUCT_ID",
  "message": "Product identifier is invalid"
}
~~~

The client can decode the payload and construct a business exception:

~~~java
if (status.is4xxClientError()) {
    return response.bodyToMono(ApiError.class)
            .defaultIfEmpty(new ApiError(
                    "UNKNOWN",
                    "Remote service returned an empty error body"
            ))
            .flatMap(error -> Mono.<Optional<Product>>error(
                    new RemoteApiException(status.value(), error)
            ));
}
~~~

The body has been decoded in this branch. The exception holds the status code and ApiError so the calling layer can decide the appropriate HTTP status, message, or business code.

If a partner API does not guarantee the error body is always valid-schema JSON, you can read it as a String to preserve the raw content:

~~~java
return response.bodyToMono(String.class)
        .defaultIfEmpty("")
        .flatMap(raw -> Mono.<Optional<Product>>error(
                new RemoteApiException(status.value(), raw)
        ));
~~~

Reading as String avoids DTO decode errors when a partner returns plain text or unexpected JSON structure. You still must cap body size via codec configuration and avoid logging sensitive raw error bodies.

### 3.6. 5xx preserving WebClientResponseException

For 5xx errors without custom domain logic, use createError():

~~~java
if (status.is5xxServerError()) {
    return response.createError();
}
~~~

createError() produces a Mono terminating with WebClientResponseException. The exception contains status, headers, body, and the original request; you can inspect the response body when handling the error:

~~~java
.onErrorResume(WebClientResponseException.class, error -> {
    int status = error.getStatusCode().value();
    String body = error.getResponseBodyAsString();
    return Mono.error(new UpstreamUnavailableException(status, body));
})
~~~

This snippet illustrates handling downstream of exchangeToMono. If you want to keep the original exception as-is, no onErrorResume is needed.

### 3.7. Inspecting headers before decoding the body

The callback can choose how to decode based on status and Content-Type:

~~~java
.exchangeToMono(response -> {
    HttpStatusCode status = response.statusCode();
    MediaType contentType = response.headers()
            .contentType()
            .orElse(MediaType.APPLICATION_OCTET_STREAM);

    if (status.is2xxSuccessful()
            && MediaType.APPLICATION_JSON.isCompatibleWith(contentType)) {
        return response.bodyToMono(Product.class);
    }

    return response.createError();
});
~~~

This example requires a successful body to be JSON. In real applications, clearly define accepted media types and how to handle mismatched headers.

## 4. exchangeToFlux(): branching to return a stream

### 4.1. Contract

exchangeToFlux also receives ClientResponse, but the callback returns a Flux:

~~~java
Flux<Product> products = webClient.get()
        .uri("/products")
        .accept(MediaType.APPLICATION_JSON)
        .exchangeToFlux(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToFlux(Product.class);
            }
            return response.createError().flux();
        });
~~~

Use exchangeToFlux when a response can contain zero, one, or many elements:

- A JSON array decoded into individual Product items.
- NDJSON emitting each line as an object.
- Server-sent events emitting each event.
- A long data stream consumed with backpressure.

Do not call collectList() if downstream can process items one by one. Collecting the entire stream into a List increases memory with response size and loses streaming benefits.

### 4.2. 404 returning Flux.empty()

Example where a non-existent product list is treated as an empty list:

~~~java
Flux<Product> listProducts() {
    return webClient.get()
            .uri("/products")
            .accept(MediaType.APPLICATION_JSON)
            .exchangeToFlux(response -> {
                int status = response.statusCode().value();

                if (status == 404) {
                    return response.releaseBody()
                            .thenMany(Flux.empty());
                }

                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToFlux(Product.class);
                }

                return response.createError().flux();
            });
}
~~~

The 404 branch releases the body and emits an empty Flux. The 2xx branch directly returns the decoded stream. Remaining statuses become an error signal.

### 4.3. Handling error streams by status

An API may return one data type on success and a different error body on failure. exchangeToFlux lets you decode the error before emitting an error signal:

~~~java
.exchangeToFlux(response -> {
    if (response.statusCode().is2xxSuccessful()) {
        return response.bodyToFlux(Product.class);
    }

    if (response.statusCode().is4xxClientError()) {
        return response.bodyToMono(ApiError.class)
                .defaultIfEmpty(new ApiError("UNKNOWN", "No error body"))
                .flatMapMany(error -> Flux.error(
                        new RemoteApiException(
                                response.statusCode().value(),
                                error
                        )
                ));
    }

    return response.createError().flux();
});
~~~

bodyToMono reads a single error payload. flatMapMany turns the payload into a Flux terminating with an exception. Do not call bodyToFlux after bodyToMono has already consumed the response.

### 4.4. Backpressure and cancellation

For streaming responses:

- Return the Flux directly from the callback so downstream controls demand.
- Use concatMap when elements must be processed sequentially.
- Only use flatMap when elements can be processed concurrently and concurrency is bounded.
- Do not call subscribe() inside the callback.
- Do not call block() on the WebFlux request path.
- Do not convert Flux to List if the response can be large.
- If the consumer cancels the subscription, cancellation must propagate through the pipeline so the HTTP stream stops per the client connector's mechanism.

For unbounded streams such as SSE, the callback returns a Flux to the consumer; test complete, error, and cancel signals.

## 5. Comparing retrieve, onStatus, and exchangeTo*

| Need | Suitable API |
| --- | --- |
| Decode body to one DTO; default 4xx/5xx to exception | retrieve().bodyToMono() |
| Decode a stream of DTOs | retrieve().bodyToFlux() |
| Customize exceptions for 4xx/5xx while keeping a uniform success body type | retrieve().onStatus(...) |
| 404 becomes Optional.empty, 204 empty result, 400 decodes error DTO | exchangeToMono() |
| Success returns Flux, 404 returns Flux.empty, other errors emit error | exchangeToFlux() |
| Choose different decoders by status or header | exchangeToMono() or exchangeToFlux() |

### 5.1. retrieve() with onStatus

Example of retrieve() with custom error handling:

~~~java
Mono<Product> product = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .onStatus(HttpStatusCode::is4xxClientError, response ->
                response.bodyToMono(ApiError.class)
                        .map(error -> new RemoteApiException(
                                response.statusCode().value(),
                                error
                        )))
        .onStatus(HttpStatusCode::is5xxServerError, response ->
                response.createException())
        .bodyToMono(Product.class);
~~~

retrieve() handles 4xx/5xx statuses by default with WebClientResponseException when no matching status handler applies. onStatus lets you change how exceptions are built. Afterward, the success body is still decoded into Product.

### 5.2. When is exchangeToMono unnecessary?

Do not use exchangeToMono for every request just because it is more flexible. If you only need the body and want 4xx/5xx to become default exceptions, retrieve() expresses intent with less code.

Use exchangeToMono when status changes **the result type or business behavior**, not merely the error message.

### 5.3. Legacy exchange() is deprecated

The older exchange() API returned ClientResponse externally without fully managing body consumption. Since Spring Framework 5.3, exchange() has been deprecated due to memory and connection leak risks if the response body is not handled properly.

Use retrieve(), exchangeToMono(), or exchangeToFlux(). Do not write new code using exchange().

## 6. Response bodies are one-shot: mistakes to avoid

### 6.1. Reading the body twice

Wrong:

~~~java
.exchangeToMono(response ->
        response.bodyToMono(String.class)
                .flatMap(raw -> {
                    log.info("Response: {}", raw);
                    return response.bodyToMono(Product.class);
                })
)
~~~

The first bodyToMono already consumed the body. The second call cannot re-read the response from the start; it may receive an empty body or a decode error.

The right way is to decode once and reuse the value. If you must parse from String, use Mono.fromCallable to handle parsing APIs that throw checked exceptions:

~~~java
.exchangeToMono(response ->
        response.bodyToMono(String.class)
                .flatMap(raw -> Mono.fromCallable(
                        () -> objectMapper.readValue(raw, Product.class)
                ))
)
~~~

If you want to inspect the schema, decode once into JsonNode or an appropriate DTO. Do not log raw bodies in production if they contain tokens, personal data, or sensitive information.

### 6.2. Returning ClientResponse outside the callback

Do not do this:

~~~java
Mono<ClientResponse> responseMono = webClient.get()
        .uri("/products/1")
        .exchangeToMono(Mono::just);
~~~

exchangeToMono is designed for the callback to decide how to process the response. Once the callback finishes, an unconsumed body may be released. Returning ClientResponse outside forces downstream code to depend on a response whose lifecycle has ended.

Instead, return a DTO, Optional, domain result, error, or decoded Flux of data.

### 6.3. Discarding the body without expressing intent

If status 404 is treated as not found and the body is unnecessary:

~~~java
return response.releaseBody()
        .thenReturn(Optional.<Product>empty());
~~~

WebClient has an auto-release mechanism for unconsumed bodies when the callback completes. releaseBody() makes the body-discarding branch explicit and easy to review.

### 6.4. Nested subscribe() calls

Wrong:

~~~java
.exchangeToMono(response -> {
    response.bodyToMono(Product.class).subscribe(this::save);
    return Mono.empty();
})
~~~

subscribe() creates an independent subscription outside the pipeline managed by WebClient. The callback may complete before save finishes; errors and cancellation are no longer propagated properly to the caller.

Right:

~~~java
.exchangeToMono(response ->
        response.bodyToMono(Product.class)
                .flatMap(this::save)
)
~~~

Return a Publisher from the callback so the framework and caller manage the lifecycle.

### 6.5. Using block() on the event loop

Do not call block() in controllers, reactive services, or exchangeTo* callbacks. block() blocks the thread driving reactive I/O and can degrade throughput or cause deadlocks.

In unit tests, StepVerifier is the appropriate choice to verify Mono/Flux without manual blocking.

## 7. Special statuses and headers

### 7.1. 201 Created

201 may often include the newly created resource and a Location header. Read both the body and header if required by business logic:

~~~java
.exchangeToMono(response -> {
    if (response.statusCode().value() == 201) {
        URI location = response.headers().asHttpHeaders().getLocation();

        return response.bodyToMono(Product.class)
                .map(product -> new CreatedProduct(location, product));
    }
    return response.createError();
})
~~~

CreatedProduct is an application-defined result type holding Location and Product. If the API returns 201 with no body, you can use releaseBody() and build a result containing only Location.

### 7.2. 202 Accepted

202 only confirms that the request was accepted for processing; it does not mean the operation has completed. Usually you should read an operation ID or status URL if provided by the API.

Do not treat 202 like 200 if the business layer must wait for the final result.

### 7.3. 206 Partial Content

206 indicates the response contains a partial representation. If the client sent a Range request, inspect Content-Range and process the byte range per contract. Do not decode partial data into a full DTO unless the API is designed that way.

### 7.4. 304 Not Modified

304 typically appears with conditional GET requests. It is not a 2xx status, yet not necessarily a business error either. If the client uses caching:

~~~java
if (status == 304) {
    return response.releaseBody()
            .thenReturn(cachedProduct);
}
~~~

Only use cachedProduct if the cache key, ETag, or Last-Modified matches the current request. If no valid cached representation exists, handle 304 according to a dedicated contract.

### 7.5. Location, ETag, and Retry-After

Headers can be read before consuming the body:

- Location: URI of the created resource or operation.
- ETag: validator for conditional requests.
- Last-Modified: timestamp when the representation changed.
- Retry-After: wait time before retrying, commonly associated with 429 or 503.
- Content-Type: selects the appropriate decoder.
- Content-Length: size information if present, not always supplied.

Do not assume every header is present. Use Optional or null checks per API.

## 8. Retry, timeout, and network errors

exchangeToMono/Flux decides how to turn a response into a result. Retries and timeouts are typically placed outside the constructed publisher:

~~~java
return findProduct(id)
        .timeout(Duration.ofSeconds(3))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
                .filter(this::isTransientFailure));
~~~

Only retry recoverable errors, such as 502, 503, 504, or transient connection failures. Do not retry all 4xx errors because statuses like 400, 401, 403, or 404 usually cannot be fixed by resending the same request.

For POST or operations with side effects, only retry when the API supports an idempotency key or guarantees no duplicate data creation. GET is generally safer for retries, though you should still check the upstream contract.

When receiving 429 or 503 with Retry-After, respect the server's retry policy. Avoid tight retry loops that overload the upstream.

## 9. Runnable Java 17+ example: CatalogClient branching by status

This example uses Spring Boot 3.5.5, Java 17+, and WebFlux. CatalogClient has two methods:

- findProduct(): uses exchangeToMono, returns Optional<Product>, maps 404 to empty, and decodes 4xx error payloads.
- listProducts(): uses exchangeToFlux, streams Product for 2xx, returns Flux.empty() for 404, and creates errors for other statuses.

### 9.1. Project structure

~~~text
webclient-status-branching/
├── pom.xml
└── src/
    ├── main/java/example/catalog/
    │   ├── DemoApplication.java
    │   ├── CatalogProperties.java
    │   ├── CatalogClientConfiguration.java
    │   ├── CatalogClient.java
    │   ├── CatalogController.java
    │   ├── Product.java
    │   ├── ApiError.java
    │   └── RemoteApiException.java
    └── test/java/example/catalog/
        └── CatalogClientTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webclient-status-branching</artifactId>
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

### 9.3. Product.java

~~~java
package example.catalog;

public record Product(String id, String name) {
}
~~~

### 9.4. ApiError.java

~~~java
package example.catalog;

public record ApiError(String code, String message) {
}
~~~

### 9.5. RemoteApiException.java

~~~java
package example.catalog;

public class RemoteApiException extends RuntimeException {

    private final int statusCode;
    private final ApiError error;

    public RemoteApiException(int statusCode, ApiError error) {
        super("Catalog API returned " + statusCode + ": " + error.message());
        this.statusCode = statusCode;
        this.error = error;
    }

    public int statusCode() {
        return statusCode;
    }

    public ApiError error() {
        return error;
    }
}
~~~

### 9.6. CatalogClient.java

~~~java
package example.catalog;

import java.util.Optional;

import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<Optional<Product>> findProduct(String id) {
        return webClient.get()
                .uri("/products/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .exchangeToMono(response -> {
                    HttpStatusCode status = response.statusCode();

                    if (status.value() == 404 || status.value() == 204) {
                        return response.releaseBody()
                                .thenReturn(Optional.<Product>empty());
                    }

                    if (status.is2xxSuccessful()) {
                        return response.bodyToMono(Product.class)
                                .map(Optional::of)
                                .defaultIfEmpty(Optional.<Product>empty());
                    }

                    if (status.is4xxClientError()) {
                        return response.bodyToMono(ApiError.class)
                                .defaultIfEmpty(new ApiError(
                                        "UNKNOWN",
                                        "Remote service returned an empty error body"
                                ))
                                .flatMap(error -> Mono.<Optional<Product>>error(
                                        new RemoteApiException(status.value(), error)
                                ));
                    }

                    return response.createError();
                });
    }

    public Flux<Product> listProducts() {
        return webClient.get()
                .uri("/products")
                .accept(MediaType.APPLICATION_JSON)
                .exchangeToFlux(response -> {
                    HttpStatusCode status = response.statusCode();

                    if (status.value() == 404) {
                        return response.releaseBody()
                                .thenMany(Flux.empty());
                    }

                    if (status.is2xxSuccessful()) {
                        return response.bodyToFlux(Product.class);
                    }

                    return response.createError().flux();
                });
    }
}
~~~

Analysis:

- findProduct checks 404 and 204 before decoding the DTO.
- The 2xx success branch decodes Product; an empty body produces Optional.empty().
- The 4xx branch decodes ApiError and creates RemoteApiException.
- The remaining branch uses createError to retain status/body in WebClientResponseException.
- listProducts returns bodyToFlux directly without collecting the whole list.
- The 404 branch of listProducts releases the body and returns an empty Flux.

### 9.7. CatalogProperties.java

~~~java
package example.catalog;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(String baseUrl) {
}
~~~

### 9.8. CatalogClientConfiguration.java

~~~java
package example.catalog;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogClientConfiguration {

    @Bean
    WebClient catalogWebClient(
            WebClient.Builder builder,
            CatalogProperties properties) {
        return builder.baseUrl(properties.baseUrl()).build();
    }

    @Bean
    CatalogClient catalogClient(WebClient catalogWebClient) {
        return new CatalogClient(catalogWebClient);
    }
}
~~~

### 9.9. CatalogController.java

~~~java
package example.catalog;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/catalog")
public class CatalogController {

    private final CatalogClient catalogClient;

    public CatalogController(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Product>> find(@PathVariable String id) {
        return catalogClient.findProduct(id)
                .map(found -> {
                    if (found.isPresent()) {
                        return ResponseEntity.ok(found.get());
                    }
                    return ResponseEntity.<Product>notFound().build();
                });
    }

    @GetMapping(path = "/stream", produces = MediaType.APPLICATION_NDJSON_VALUE)
    public Flux<Product> stream() {
        return catalogClient.listProducts();
    }
}
~~~

The controller demonstrates using the business results: Optional.empty() is mapped to HTTP 404 on the local API; Flux is returned as NDJSON so clients receive each Product incrementally.

### 9.10. DemoApplication.java

~~~java
package example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.11. application.yml

~~~yaml
catalog:
  base-url: http://localhost:8081
~~~

In real environments, change base-url to the upstream address via environment configuration or proper secret/config management. Never hardcode credentials in source code.

## 10. Testing with MockWebServer and StepVerifier

Spring recommends testing WebClient with a mock web server such as OkHttp MockWebServer or WireMock. A mock server receives real HTTP traffic from WebClient, verifying requests, statuses, headers, and bodies at the transport boundary.

CatalogClientTest.java:

~~~java
package example.catalog;

import java.io.IOException;
import java.util.Optional;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogClientTest {

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
    void decodesProductFrom200Response() {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                .setBody("{\"id\":\"p-1\",\"name\":\"Keyboard\"}"));

        StepVerifier.create(client.findProduct("p-1"))
                .expectNext(Optional.of(new Product("p-1", "Keyboard")))
                .verifyComplete();
    }

    @Test
    void maps204ToEmptyOptional() {
        server.enqueue(new MockResponse().setResponseCode(204));

        StepVerifier.create(client.findProduct("p-1"))
                .expectNext(Optional.empty())
                .verifyComplete();
    }

    @Test
    void maps404ToEmptyOptionalAndIgnoresErrorBody() {
        server.enqueue(new MockResponse()
                .setResponseCode(404)
                .addHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                .setBody("{\"code\":\"NOT_FOUND\",\"message\":\"Missing\"}"));

        StepVerifier.create(client.findProduct("missing"))
                .expectNext(Optional.empty())
                .verifyComplete();
    }

    @Test
    void maps400ToDomainExceptionWithDecodedPayload() {
        server.enqueue(new MockResponse()
                .setResponseCode(400)
                .addHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                .setBody("{\"code\":\"INVALID_ID\",\"message\":\"Bad id\"}"));

        StepVerifier.create(client.findProduct("bad"))
                .expectErrorSatisfies(error -> {
                    assertThat(error).isInstanceOf(RemoteApiException.class);

                    RemoteApiException remote = (RemoteApiException) error;
                    assertThat(remote.statusCode()).isEqualTo(400);
                    assertThat(remote.error().code()).isEqualTo("INVALID_ID");
                    assertThat(remote.error().message()).isEqualTo("Bad id");
                })
                .verify();
    }

    @Test
    void preserves503AsWebClientResponseException() {
        server.enqueue(new MockResponse()
                .setResponseCode(503)
                .addHeader("Content-Type", MediaType.TEXT_PLAIN_VALUE)
                .setBody("temporarily unavailable"));

        StepVerifier.create(client.findProduct("p-1"))
                .expectErrorSatisfies(error -> {
                    assertThat(error).isInstanceOf(WebClientResponseException.class);

                    WebClientResponseException remote =
                            (WebClientResponseException) error;

                    assertThat(remote.getStatusCode().value()).isEqualTo(503);
                    assertThat(remote.getResponseBodyAsString())
                            .contains("temporarily unavailable");
                })
                .verify();
    }

    @Test
    void streamsProductsFrom200Response() {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                .setBody("""
                        [
                          {"id":"p-1","name":"Keyboard"},
                          {"id":"p-2","name":"Mouse"}
                        ]
                        """));

        StepVerifier.create(client.listProducts())
                .expectNext(new Product("p-1", "Keyboard"))
                .expectNext(new Product("p-2", "Mouse"))
                .verifyComplete();
    }

    @Test
    void maps404ListResponseToEmptyFlux() {
        server.enqueue(new MockResponse()
                .setResponseCode(404)
                .setBody("not found"));

        StepVerifier.create(client.listProducts())
                .verifyComplete();
    }
}
~~~

The tests cover 200, 204, 404, 400, 503, and multi-Product streaming branches. StepVerifier asserts onNext, onComplete, and onError without blocking in application code.

### 10.1. Running tests

From the directory containing pom.xml:

~~~bash
mvn test
~~~

### 10.2. Running the application

~~~bash
mvn spring-boot:run
~~~

The local application calls the upstream at localhost:8081 by default. When the upstream is ready:

~~~bash
curl -i http://localhost:8080/catalog/p-1
curl -i -H "Accept: application/x-ndjson" http://localhost:8080/catalog/stream
~~~

The first endpoint returns a Product or HTTP 404 if the upstream returns 404/204. The stream endpoint emits each Product as NDJSON.

## 11. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using retrieve() when result type must vary by status | Hard to express 404 as Optional or error body as another type | Use exchangeToMono |
| Using exchangeToMono for every simple request | More verbose than retrieve() with no benefit | Use retrieve() if only decoding and onStatus are needed |
| Checking only status 200 | Misses 201, 202, or other 2xx statuses | Use is2xxSuccessful when contract allows |
| Decoding a 204 body into a DTO | Decoder receives an empty body | Handle 204 first and return empty/no-content |
| Skipping a 404 body without releasing | Risks holding response resources | Call releaseBody() or decode the body |
| Calling bodyToMono twice | The one-shot body is already consumed | Decode once and transform the value |
| Returning ClientResponse downstream | Response may already be cleaned up when callback ends | Return decoded DTO/domain result or Flux |
| Calling subscribe() inside the callback | Creates an independent pipeline, losing error/cancel handling | Compose with flatMap/then/concatMap |
| Calling block() on the event loop | Blocks I/O threads | Return Mono/Flux and let the framework subscribe |
| Calling createError() and still decoding the body | The body has already been turned into an error | Pick a single handling branch |
| Using bodyToMono for large streams | May buffer too much data | Use bodyToFlux and backpressure |
| Calling collectList() on very large responses | Memory grows with the full response | Process element by element |
| Mapping all errors to 404 | Masks upstream or server failures | Map only statuses with the corresponding business meaning |
| Retrying every exception | Repeats 4xx or non-idempotent operations | Retry conditionally with bounded attempts and backoff |
| Logging raw response bodies | Leaks tokens, PII, or sensitive data | Log status, correlation ID, and filtered metadata |

## 12. Status branching design checklist

Before finalizing a WebClient call, answer these questions:

1. Which statuses can the API return?
2. Which statuses indicate success with a body?
3. Which statuses indicate success without a body, such as 204?
4. Is 404 an error or a normal business result?
5. Do 400/409/422 have an error DTO to decode?
6. Should 5xx preserve WebClientResponseException for retries or observability?
7. Can the response be a JSON array, NDJSON, SSE, or binary stream?
8. Does every branch properly consume, release, or transform the body?
9. Is bodyToMono/bodyToFlux ever called multiple times on the same response?
10. Are timeouts, retries, and cancellation configured per contract?
11. Are boundary statuses tested using a mock HTTP server?
12. Are error bodies and headers inspected without logging sensitive data?

## 13. Key takeaways

- retrieve() is the default choice for simple decoding; onStatus customizes 4xx/5xx errors.
- exchangeToMono() lets you branch by status and return a Mono result.
- exchangeToFlux() lets you branch by status and return a Flux stream.
- HttpStatusCode supports checking status families for 2xx, 4xx, and 5xx.
- The callback must decide how to decode or discard the body; the response body is one-shot.
- If the callback finishes without consuming the body, WebClient automatically releases it to prevent leaks.
- Use releaseBody() when intentionally discarding response content.
- Use createError() to build WebClientResponseException preserving status, headers, body, and request.
- Never return ClientResponse outside the callback, and never call subscribe() or block() inside the pipeline.
- Legacy exchange() has been deprecated since Spring Framework 5.3; use retrieve() or exchangeTo*.
- For large streams, return Flux directly and preserve backpressure.
- Test 2xx, 204, 404, 4xx, 5xx, and streaming branches with MockWebServer and StepVerifier.

**Official documentation:**
- [Spring Framework — WebClient Exchange: exchangeToMono, exchangeToFlux, and response body lifecycle](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html)
- [Spring Framework — WebClient retrieve() and onStatus](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html)
- [Spring Framework Javadoc — WebClient.RequestHeadersSpec](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/reactive/function/client/WebClient.RequestHeadersSpec.html)
- [Spring Framework Javadoc — ClientResponse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/ClientResponse.html)
- [Spring Framework — Testing WebClient with MockWebServer](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
