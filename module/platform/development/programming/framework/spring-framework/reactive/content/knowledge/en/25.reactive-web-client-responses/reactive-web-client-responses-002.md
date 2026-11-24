# toEntity and accessing status, headers, and body in Spring WebClient

## 1. Why is toEntity needed?

When making HTTP calls with Spring WebClient, sometimes retrieving only the body content is not enough. The application also needs to know what status the server returned, which headers it sent, whether there is an ETag or correlation ID, and what Java type the body was decoded into.

`retrieve().bodyToMono(Product.class)` returns a publisher of the decoded body. This approach is concise when you only care about the data.

`retrieve().toEntity(Product.class)` returns `Mono<ResponseEntity<Product>>`. ResponseEntity bundles three parts of an HTTP response:

- **Status:** the HTTP status code, such as 200, 201, 206, or 404.
- **Headers:** metadata such as Content-Type, ETag, Location, Cache-Control, Retry-After, and X-Request-Id.
- **Body:** the content decoded by the codec into the requested Java type.

Official example:

~~~java
Mono<ResponseEntity<Person>> result = client.get()
    .uri("/persons/{id}", id)
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .toEntity(Person.class);
~~~

This is still a reactive API. The request is not executed simply because `retrieve()` was called; execution happens when the publisher is subscribed to. Do not call `block()` in a reactive controller or service.

**When should toEntity be used?** When business decisions need to combine status, headers, and body in a single result: handling ETag, reading Location after creating a resource, inspecting Retry-After, recording a request ID, or forwarding status/headers from an upstream in an API gateway.

## 2. What does ResponseEntity<T> contain?

`ResponseEntity<T>` is a response type containing status, headers, and body. With WebClient, it represents the response received from the server after the body has been decoded.

~~~java
ResponseEntity<Product> response = ...;

HttpStatusCode status = response.getStatusCode();
int statusValue = status.value();

HttpHeaders headers = response.getHeaders();
String requestId = headers.getFirst("X-Request-Id");
MediaType contentType = headers.getContentType();

Product body = response.getBody();
~~~

Important APIs:

| API | Return value | Purpose |
| --- | --- | --- |
| `getStatusCode()` | `HttpStatusCode` | Get the status via Spring's abstraction |
| `getStatusCode().value()` | `int` | Get the numeric HTTP status code |
| `getHeaders()` | `HttpHeaders` | Read response headers |
| `getBody()` | `T` | Get the decoded body |
| `hasBody()` | `boolean` | Check whether the response entity has a body |
| `getStatusCode().is2xxSuccessful()` | `boolean` | Check the 2xx status family |
| `getStatusCode().is4xxClientError()` | `boolean` | Check the 4xx status family |
| `getStatusCode().is5xxServerError()` | `boolean` | Check the 5xx status family |

Use `HttpStatusCode` instead of assuming every status is a known `HttpStatus` constant. HTTP can have extension status codes; `value()` always lets you retrieve the numeric code.

Headers returned from a response entity should be treated as read-only data. If you need to build a new response, copy allowed headers into a new entity; do not rely on mutating the received entity's headers directly.

## 3. Reading status, headers, and body in the same pipeline

Example of a client fetching a product and capturing status, ETag, request ID, and body:

~~~java
Mono<ProductSnapshot> snapshot = webClient.get()
    .uri("/products/{id}", 42)
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .toEntity(Product.class)
    .map(response -> {
        int status = response.getStatusCode().value();
        String etag = response.getHeaders().getETag();
        String requestId =
            response.getHeaders().getFirst("X-Request-Id");

        Product product = response.getBody();

        return new ProductSnapshot(
            status,
            etag,
            requestId,
            product
        );
    });
~~~

DTOs used in the example:

~~~java
public record Product(
    long id,
    String name,
    BigDecimal price
) {
}

public record ProductSnapshot(
    int status,
    String etag,
    String requestId,
    Product product
) {
}
~~~

`map` only transforms a value already inside the publisher. If handling the body requires calling another asynchronous service, use `flatMap`:

~~~java
Mono<ProductView> view = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .toEntity(Product.class)
    .flatMap(response -> {
        Product product = response.getBody();

        if (product == null) {
            return Mono.error(
                new IllegalStateException("Product response has no body")
            );
        }

        String requestId =
            response.getHeaders().getFirst("X-Request-Id");

        return auditService.record(
                response.getStatusCode(),
                requestId
            )
            .thenReturn(new ProductView(
                response.getStatusCode().value(),
                product
            ));
    });
~~~

Do not call `block()` to obtain the ResponseEntity before processing it. Keeping the entire chain inside Mono lets WebFlux manage subscription, errors, and cancellation.

## 4. GET example with toEntity

~~~java
Mono<ResponseEntity<Product>> getProduct(long id) {
    return webClient.get()
        .uri("/products/{id}", id)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .toEntity(Product.class);
}
~~~

When subscribed, WebClient sends a GET request. The JSON response is decoded by the codec into `Product`, while the status and headers are placed into the ResponseEntity.

Suppose the server returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "product-42-v3"
X-Request-Id: req-7f21

{"id":42,"name":"Keyboard","price":79.90}
~~~

You can read:

~~~java
response.getStatusCode().value();              // 200
response.getHeaders().getETag();                // "product-42-v3"
response.getHeaders().getFirst("X-Request-Id"); // req-7f21
response.getBody().name();                      // Keyboard
~~~

The illustrative values show that the body is a decoded Java object, no longer a raw JSON string. If you need the raw body for debugging, you can read it as `String.class` or handle errors via `WebClientResponseException`; you cannot read the same response body again as an independent stream after it has been consumed.

## 5. Distinguishing bodyToMono and toEntity

Both approaches decode the response body, but they return different data:

~~~java
Mono<Product> bodyOnly = webClient.get()
    .uri("/products/42")
    .retrieve()
    .bodyToMono(Product.class);

Mono<ResponseEntity<Product>> withMetadata = webClient.get()
    .uri("/products/42")
    .retrieve()
    .toEntity(Product.class);
~~~

| Criterion | `bodyToMono(Product.class)` | `toEntity(Product.class)` |
| --- | --- | --- |
| Decoded body | Yes | Yes |
| Status code | Not included in result | Yes |
| Response headers | Not included in result | Yes |
| Publisher type | `Mono<Product>` | `Mono<ResponseEntity<Product>>` |
| Best suited when | Only data is needed | Both HTTP metadata and data are needed |

If the service needs to inspect ETag, Location, Retry-After, or status, `toEntity` is usually clearer. If it only needs Product for business computation, `bodyToMono` avoids an extra wrapper layer.

Both consume the response body in their respective ways. Do not call `bodyToMono` after `toEntity` on the same response expecting to read the body a second time.

## 6. 4xx/5xx statuses: the most common pitfall

By default, `retrieve()` turns response statuses in the 4xx or 5xx range into a `WebClientResponseException` error. This remains true when the terminal operation is `toEntity`.

Example:

~~~java
Mono<ResponseEntity<Product>> result = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .toEntity(Product.class);
~~~

If the server returns 404, the publisher emits a `WebClientResponseException.NotFound` error by default; the application does not receive a ResponseEntity on which to call `getStatusCode()` in the success branch.

Therefore, if you want to treat 404 as a normal HTTP result, you need to customize the status handler.

### 6.1. Keeping 404 as a ResponseEntity

~~~java
Mono<ResponseEntity<Product>> result = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .onStatus(
        status -> status.value() == 404,
        response -> Mono.empty()
    )
    .toEntity(Product.class);
~~~

When the status is 404, the callback returns `Mono.empty()` so that the status is not converted into an exception. The response is forwarded to the next step and `toEntity` can return a ResponseEntity with status 404.

If the 404 response has no body, `getBody()` may be null. Check before accessing fields:

~~~java
return result.map(response -> {
    if (response.getStatusCode().value() == 404) {
        return ProductLookup.notFound();
    }

    Product product = response.getBody();
    return product == null
        ? ProductLookup.empty()
        : ProductLookup.found(product);
});
~~~

Only suppress 404 when it is an intentional business branch. If the 404 error body contains JSON incompatible with `Product`, decoding the body as Product can still fail. When you need to read an error representation, decode it into an error DTO or handle it with `exchangeToMono`.

### 6.2. Converting 4xx/5xx into a business exception

~~~java
Mono<ResponseEntity<Product>> result = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .onStatus(
        HttpStatusCode::is4xxClientError,
        response -> response.bodyToMono(String.class)
            .defaultIfEmpty("")
            .map(body -> new RemoteApiException(
                response.statusCode().value(),
                body
            ))
    )
    .onStatus(
        HttpStatusCode::is5xxServerError,
        response -> response.bodyToMono(String.class)
            .defaultIfEmpty("")
            .map(body -> new RemoteApiException(
                response.statusCode().value(),
                body
            ))
    )
    .toEntity(Product.class);
~~~

Simple exception:

~~~java
public class RemoteApiException extends RuntimeException {
    private final int status;
    private final String responseBody;

    public RemoteApiException(int status, String responseBody) {
        super("Remote API returned HTTP " + status);
        this.status = status;
        this.responseBody = responseBody;
    }

    public int getStatus() {
        return status;
    }

    public String getResponseBody() {
        return responseBody;
    }
}
~~~

Inside the `onStatus` callback, the error body is consumed as a String to construct the exception. Because the callback emits an error, `toEntity` does not produce a success ResponseEntity. Choose a stable error representation rather than returning a raw body that might contain sensitive information to a public API.

### 6.3. Reading WebClientResponseException

If you keep the default handling, you can catch the error downstream:

~~~java
return webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .toEntity(Product.class)
    .onErrorResume(
        WebClientResponseException.class,
        error -> {
            log.warn(
                "Remote status={}, body={}",
                error.getStatusCode().value(),
                error.getResponseBodyAsString()
            );
            return Mono.error(error);
        }
    );
~~~

`WebClientResponseException` provides the status code, response headers, and the response body stored as bytes. Do not log the entire body if it may contain tokens, personal data, or confidential information.

## 7. Reading common headers

Response headers help the application understand metadata and drive subsequent behavior.

| Header | Reader API | Meaning |
| --- | --- | --- |
| Content-Type | `getContentType()` | Data type of the response body |
| Content-Length | `getContentLength()` | Body length if provided by the server |
| ETag | `getETag()` | Validator for the representation |
| Last-Modified | `getLastModified()` | Timestamp when the representation was modified |
| Location | `getLocation()` | URI of a related resource, commonly used with 201/redirect |
| Cache-Control | `getCacheControl()` | Caching policy |
| Retry-After | `getFirst("Retry-After")` | Suggested retry delay |
| X-Request-Id | `getFirst("X-Request-Id")` | Server-supplied correlation/request identifier |

Example of reading Location and ETag:

~~~java
return webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new CreateProduct("Mouse", new BigDecimal("25.50")))
    .retrieve()
    .toEntity(Product.class)
    .map(response -> {
        URI location = response.getHeaders().getLocation();
        String etag = response.getHeaders().getETag();
        Product created = response.getBody();

        return new CreatedProduct(
            response.getStatusCode(),
            location,
            etag,
            created
        );
    });
~~~

Status 201 and Location typically indicate where the newly created resource resides. Do not assume every server sends Location; check for null before using it.

### 7.1. Multi-valued headers

A header can contain multiple values. Use `get(name)` to obtain a list or `getFirst(name)` when the contract specifies only the first value is needed:

~~~java
List<String> warnings =
    response.getHeaders().get("Warning");

String requestId =
    response.getHeaders().getFirst("X-Request-Id");
~~~

Do not arbitrarily join multi-valued headers into a single string if the header's rules require handling each value separately.

### 7.2. Headers can be restricted by CORS

If WebClient runs on the server, the Java application can read the response headers sent by the server. If JavaScript in a browser calls an API directly, the browser only gives JavaScript access to response headers exposed via CORS.

For a browser client that needs to read custom headers, the server must configure `Access-Control-Expose-Headers`, for example:

~~~http
Access-Control-Expose-Headers: ETag, X-Request-Id, Retry-After
~~~

This is a browser CORS restriction, not a limitation of `ResponseEntity` in server-side Java WebClient.

## 8. Generic body: ParameterizedTypeReference

Java type erasure means `List<Product>.class` does not exist. When the body has nested generics, use `ParameterizedTypeReference<T>` to preserve type information for the codec.

Example response:

~~~json
{
  "data": [
    {"id": 1, "name": "Keyboard", "price": 79.90},
    {"id": 2, "name": "Mouse", "price": 25.50}
  ],
  "page": 1,
  "total": 2
}
~~~

DTO:

~~~java
public record PageResult<T>(
    List<T> data,
    int page,
    int total
) {
}
~~~

WebClient:

~~~java
ParameterizedTypeReference<PageResult<Product>> type =
    new ParameterizedTypeReference<>() {};

Mono<ResponseEntity<PageResult<Product>>> result =
    webClient.get()
        .uri("/products?page=1")
        .retrieve()
        .toEntity(type);
~~~

Do not use `PageResult.class` if you want the decoder to know the exact generic argument is Product. If you only need a list of elements of the same type, `toEntityList(Product.class)` is a more convenient API.

## 9. toEntityList: getting ResponseEntity<List<T>>

When the server returns a finite JSON array and the application also needs HTTP metadata, use `toEntityList`:

~~~java
Mono<ResponseEntity<List<Product>>> result =
    webClient.get()
        .uri("/products")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .toEntityList(Product.class);
~~~

The result contains the status code, response headers, and the decoded list of Product items.

`toEntityList` must aggregate the elements into a List. Do not use it for an unbounded feed or a very large response if you can process elements incrementally via streaming.

If the response is a wrapper like `PageResult<Product>`, use `toEntity(ParameterizedTypeReference)` instead of `toEntityList`.

## 10. toBodilessEntity: only status and headers needed

Some endpoints return no body, such as a successful DELETE with 204 No Content or a request that only needs the status and Location.

~~~java
Mono<ResponseEntity<Void>> deleteProduct(String id) {
    return webClient.delete()
        .uri("/products/{id}", id)
        .retrieve()
        .toBodilessEntity();
}
~~~

`toBodilessEntity()` returns status and headers in ResponseEntity<Void>, while releasing/consuming the response body according to this API's contract. This is the appropriate choice when no body decoding is needed.

Do not use `toEntity(String.class)` just to discard the body when the goal is retrieving metadata; `toBodilessEntity` expresses intent more clearly.

## 11. toEntityFlux: keeping the body as a stream

When the response body is a large or unbounded stream, you can use `toEntityFlux`:

~~~java
Mono<ResponseEntity<Flux<Product>>> result =
    webClient.get()
        .uri("/products/stream")
        .accept(MediaType.parseMediaType("application/x-ndjson"))
        .retrieve()
        .toEntityFlux(Product.class);
~~~

The outer result is a Mono because the status and headers are determined when the response arrives. The inner body remains a Flux so each Product can be consumed incrementally.

Example:

~~~java
return result.flatMapMany(entity -> {
    log.info(
        "Stream status={}, requestId={}",
        entity.getStatusCode().value(),
        entity.getHeaders().getFirst("X-Request-Id")
    );

    Flux<Product> body = entity.getBody();
    return body == null ? Flux.empty() : body;
});
~~~

**The body Flux must be consumed in a timely manner.** The response holds connection resources until the body is read or released. Do not obtain a ResponseEntity<Flux<T>> and abandon the body; doing so can hold connections and resources longer than expected.

Key differences:

| API | Body type | How it handles the body |
| --- | --- | --- |
| `toEntity(Product.class)` | `Product` | Decodes a single object |
| `toEntityList(Product.class)` | `List<Product>` | Aggregates into a list |
| `toEntityFlux(Product.class)` | `Flux<Product>` | Consumes element by element |
| `toBodilessEntity()` | `Void` | Retrieves only status and headers |

## 12. Using status to drive control flow

Status is not just for logging. It can determine the next business branch.

~~~java
Mono<ProductLookup> lookup(String id) {
    return webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .onStatus(
            status -> status.value() == 404,
            response -> Mono.empty()
        )
        .toEntity(Product.class)
        .map(response -> {
            if (response.getStatusCode().value() == 404) {
                return ProductLookup.notFound();
            }

            Product body = response.getBody();
            return body == null
                ? ProductLookup.empty()
                : ProductLookup.found(body);
        });
}
~~~

This example intentionally suppresses 404 and then distinguishes the status after receiving the entity. Other 4xx and 5xx statuses retain default error handling.

For APIs returning 304 Not Modified, the response typically has no new body. The client can use ETag/conditional requests and handle status 304 separately. Verify the behavior of the HTTP connector, cache layer, and status handler before designing caching; do not assume 304 is always handled like 200.

If status logic becomes complex enough that each status needs a different body type, consider `exchangeToMono` instead of cramming every branch into `onStatus`.

## 13. When to use exchangeToMono instead of retrieve().toEntity?

`retrieve()` suits the common flow: declare the request, customize error statuses if needed, and decode the response as a body or ResponseEntity.

`exchangeToMono` gives direct access to `ClientResponse` to choose how to decode based on status or headers:

~~~java
Mono<ProductResult> result = webClient.get()
    .uri("/products/{id}", id)
    .accept(MediaType.APPLICATION_JSON)
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            String requestId =
                response.headers().asHttpHeaders()
                    .getFirst("X-Request-Id");

            return response.bodyToMono(Product.class)
                .map(product ->
                    ProductResult.success(requestId, product));
        }

        if (response.statusCode().value() == 404) {
            return response.releaseBody()
                .thenReturn(ProductResult.notFound());
        }

        return response.createError();
    });
~~~

Points to remember:

- The `exchangeToMono` callback is responsible for deciding how to consume the body.
- You can decode the body differently for 2xx, 404, or error statuses.
- After the callback publisher completes, Spring checks and releases the body if it was not consumed.
- Do not return `ClientResponse` outside and expect to decode the body in another pipeline after the callback has completed.
- If the body has been consumed inside the callback, do not read it again.

Choose `toEntity` when you want a straightforward ResponseEntity. Choose `exchangeToMono` when the response needs branching logic by status, headers, or representation.

## 14. Handling network errors and decode errors

Not all WebClient errors are HTTP error statuses.

| Error type | Example | How to handle |
| --- | --- | --- |
| HTTP error status | 404, 429, 500 | WebClientResponseException or onStatus |
| Network/connect error | DNS, connection refused, TLS | Handle WebClientRequestException or transport error |
| Timeout | Upstream responds too slowly | Set timeout per SLA and classify timeouts |
| Decode error | Malformed JSON, wrong field type | Handle codec/DecodingException |
| Application error | Validation or domain error | Map to business exception |

Timeout example:

~~~java
Mono<ResponseEntity<Product>> result = webClient.get()
    .uri("/products/{id}", id)
    .retrieve()
    .toEntity(Product.class)
    .timeout(Duration.ofSeconds(3))
    .onErrorMap(
        TimeoutException.class,
        error -> new UpstreamTimeoutException("Catalog timed out", error)
    );
~~~

The timeout here applies to the entire Mono. If you need to limit connection, response, or individual stage durations, configure the connector/client appropriately; a Reactor timeout on Mono does not replace all transport timeouts.

Do not catch every Throwable and turn it into `Mono.empty()`. That loses information about HTTP errors, network errors, timeouts, and decode errors.

## 15. Avoiding blocking and managing the response body properly

`toEntity` is reactive. In a WebFlux controller/service, compose publishers:

~~~java
Mono<ProductView> view =
    productClient.getProduct(id)
        .map(response -> new ProductView(
            response.getStatusCode().value(),
            response.getHeaders().getETag(),
            response.getBody()
        ));
~~~

Avoid:

~~~java
Product product = productClient.getProduct(id)
    .block()
    .getBody();
~~~

`block()` can block the event loop and hurt WebFlux scalability. If you need to use a synchronous API in another application, place a deliberate blocking boundary; do not call it on the reactive request path.

The HTTP body is a stream consumed according to the response contract. `toEntity` has already decoded the body into an object; there is no second response stream to read again. With `toEntityFlux`, you must subscribe/consume the body Flux and let cancellation propagate to the transport when downstream stops.

When you need to read a response error body, use an `onStatus` callback or `WebClientResponseException`; do not try to read the same body in multiple independent branches.

## 16. Forwarding status and headers from upstream

An API gateway might want to forward part of a response from upstream:

~~~java
Mono<ResponseEntity<Product>> upstream =
    productClient.getProduct(id);
~~~

A controller can return ResponseEntity so Spring writes the status, headers, and body to the application's own HTTP response. However, you should not blindly forward all headers.

Choose headers carefully:

- You can forward ETag, Last-Modified, Cache-Control, or Location when semantics fit.
- Do not arbitrarily forward Content-Length, Transfer-Encoding, Connection, or hop-by-hop headers.
- Do not expose Set-Cookie, Server, internal trace metadata, or sensitive upstream headers.
- Check the API gateway's CORS, authentication, and caching policies.

Example creating a new response with only allowed headers:

~~~java
return productClient.getProduct(id)
    .map(remote -> {
        HttpHeaders headers = new HttpHeaders();

        String etag = remote.getHeaders().getETag();
        if (etag != null) {
            headers.setETag(etag);
        }

        String requestId =
            remote.getHeaders().getFirst("X-Request-Id");
        if (requestId != null) {
            headers.set("X-Request-Id", requestId);
        }

        return new ResponseEntity<>(
            remote.getBody(),
            headers,
            remote.getStatusCode()
        );
    });
~~~

This is an illustrative header allowlist. A real API gateway needs to define its header contract and handle null bodies or bodiless statuses consistently.

## 17. Complete Java 17+ Spring Boot WebFlux demo

The demo uses Spring Boot 3.5.6, Java 17, and WebClient. A MockWebServer in tests simulates the upstream to verify response status, headers, and body without depending on a public API.

### 17.1. Project structure

~~~text
webclient-to-entity-demo/
  build.gradle
  src/
    main/java/demo/
      DemoApplication.java
      Product.java
      ProductClient.java
    main/resources/
      application.properties
    test/java/demo/
      ProductClientTest.java
~~~

### 17.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
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

### 17.3. application.properties

~~~properties
spring.application.name=webclient-to-entity-demo
catalog.base-url=http://localhost:9090
~~~

When tests run, DynamicPropertySource replaces the base URL with MockWebServer's URL.

### 17.4. DemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 17.5. Product.java

~~~java
package demo;

import java.math.BigDecimal;

public record Product(
    long id,
    String name,
    BigDecimal price
) {
}
~~~

### 17.6. ProductClient.java

~~~java
package demo;

import java.util.List;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ProductClient {
    private final WebClient webClient;

    public ProductClient(
            WebClient.Builder builder,
            Environment environment) {
        String baseUrl = environment.getRequiredProperty("catalog.base-url");
        this.webClient = builder.baseUrl(baseUrl).build();
    }

    public Mono<ResponseEntity<Product>> getProduct(String id) {
        return webClient.get()
            .uri("/products/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .toEntity(Product.class);
    }

    public Mono<ResponseEntity<Product>> getProductAllowing404(String id) {
        return webClient.get()
            .uri("/products/{id}", id)
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .onStatus(
                status -> status.value() == 404,
                response -> Mono.empty()
            )
            .toEntity(Product.class);
    }

    public Mono<ResponseEntity<List<Product>>> getProducts() {
        return webClient.get()
            .uri("/products")
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .toEntityList(Product.class);
    }

    public Mono<ResponseEntity<Void>> deleteProduct(String id) {
        return webClient.delete()
            .uri("/products/{id}", id)
            .retrieve()
            .toBodilessEntity();
    }

    public Mono<ResponseEntity<ProductEnvelope<List<Product>>>> getEnvelope() {
        ParameterizedTypeReference<ProductEnvelope<List<Product>>> type =
            new ParameterizedTypeReference<>() {};

        return webClient.get()
            .uri("/products/envelope")
            .accept(MediaType.APPLICATION_JSON)
            .retrieve()
            .toEntity(type);
    }

    public record ProductEnvelope<T>(
        T data,
        int total
    ) {
    }
}
~~~

The `getProduct` method is the core example: the result preserves status, headers, and Product. `getProductAllowing404` shows how to suppress 404 specifically. `getProducts` illustrates lists; `deleteProduct` retrieves only metadata; `getEnvelope` preserves generic types via ParameterizedTypeReference.

### 17.7. ProductClientTest.java

~~~java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.io.IOException;
import java.math.BigDecimal;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ProductClientTest {
    private static final MockWebServer UPSTREAM = startServer();

    private static MockWebServer startServer() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        } catch (IOException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "catalog.base-url",
            () -> UPSTREAM.url("/").toString()
        );
    }

    @AfterAll
    static void stopServer() throws IOException {
        UPSTREAM.shutdown();
    }

    @Autowired
    ProductClient client;

    @Test
    void toEntityExposesStatusHeadersAndDecodedBody() throws Exception {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(206)
            .addHeader("Content-Type", "application/json")
            .addHeader("ETag", "\"product-7-v2\"")
            .addHeader("X-Request-Id", "req-7")
            .setBody("""
                {"id":7,"name":"Monitor","price":199.90}
                """));

        ResponseEntity<Product> response =
            client.getProduct("7").block(Duration.ofSeconds(3));

        assertNotNull(response);
        assertEquals(HttpStatus.PARTIAL_CONTENT, response.getStatusCode());
        assertEquals("\"product-7-v2\"", response.getHeaders().getETag());
        assertEquals("req-7",
            response.getHeaders().getFirst("X-Request-Id"));
        assertEquals(
            new Product(7, "Monitor", new BigDecimal("199.90")),
            response.getBody()
        );

        RecordedRequest request =
            UPSTREAM.takeRequest(1, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/products/7", request.getPath());
        assertEquals(
            "application/json",
            request.getHeader("Accept")
        );
    }

    @Test
    void defaultRetrieveTreats404AsException() {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(404)
            .addHeader("Content-Type", "text/plain")
            .setBody("product not found"));

        StepVerifier.create(client.getProduct("missing"))
            .expectErrorSatisfies(error -> {
                WebClientResponseException responseError =
                    assertInstanceOf(
                        WebClientResponseException.class,
                        error
                    );

                assertEquals(404,
                    responseError.getStatusCode().value());
                assertEquals(
                    "product not found",
                    responseError.getResponseBodyAsString()
                );
            })
            .verify();
    }

    @Test
    void onStatusCanKeep404AsResponseEntity() {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(404)
            .addHeader("X-Request-Id", "req-missing"));

        ResponseEntity<Product> response =
            client.getProductAllowing404("missing")
                .block(Duration.ofSeconds(3));

        assertNotNull(response);
        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
        assertEquals("req-missing",
            response.getHeaders().getFirst("X-Request-Id"));
        assertNull(response.getBody());
    }

    @Test
    void toEntityListKeepsResponseMetadata() {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(200)
            .addHeader("Content-Type", "application/json")
            .addHeader("X-Page", "1")
            .setBody("""
                [
                  {"id":1,"name":"Keyboard","price":79.90},
                  {"id":2,"name":"Mouse","price":25.50}
                ]
                """));

        ResponseEntity<List<Product>> response =
            client.getProducts().block(Duration.ofSeconds(3));

        assertNotNull(response);
        assertEquals(200, response.getStatusCode().value());
        assertEquals("1", response.getHeaders().getFirst("X-Page"));
        assertEquals(2, response.getBody().size());
    }

    @Test
    void toBodilessEntityReturnsStatusAndHeaders() {
        UPSTREAM.enqueue(new MockResponse()
            .setResponseCode(204)
            .addHeader("X-Request-Id", "delete-7"));

        ResponseEntity<Void> response =
            client.deleteProduct("7").block(Duration.ofSeconds(3));

        assertNotNull(response);
        assertEquals(204, response.getStatusCode().value());
        assertEquals("delete-7",
            response.getHeaders().getFirst("X-Request-Id"));
        assertNull(response.getBody());
    }
}
~~~

The tests use `block(Duration)` at the test boundary to get synchronous results for assertions; production code still returns Mono. `StepVerifier` verifies error branches without blocking threads.

### 17.8. Running the tests

From the project directory:

~~~bash
./gradlew test
~~~

Or:

~~~bash
gradle test
~~~

The first test verifies status 206, ETag, request ID, Product body, and Accept request header. The second test verifies that 404 is WebClientResponseException by default. The third test verifies that onStatus can preserve 404 as a ResponseEntity. The last two tests verify toEntityList and toBodilessEntity.

MockWebServer simulates the upstream locally so tests do not depend on Internet access or external services.

## 18. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming toEntity always returns ResponseEntity even on 404/500 | Default error branch is overlooked | Use onStatus to map or suppress specific statuses |
| Calling retrieve() and expecting the request to run | No terminal extraction operation yet | Call toEntity, bodyToMono, toBodilessEntity, or equivalent |
| Using bodyToMono when ETag/Location is needed | Status/headers are lost from the result | Use toEntity |
| Using toEntity when only the body is needed | Unnecessary wrapper | Use bodyToMono |
| Reading getBody() without checking null | NullPointerException on bodiless responses | Check body before using it |
| Using List.class for generic JSON | Element type is lost | Use toEntityList or ParameterizedTypeReference |
| Using toEntityList for unbounded streams | Aggregates data and increases memory | Use toEntityFlux or bodyToFlux |
| Calling block in a WebFlux controller/service | Blocks the event loop | Compose Mono/Flux with map/flatMap |
| Calling onStatus returning Mono.empty for all errors | Accidentally treats 4xx/5xx as normal responses | Suppress only the specific status handled by business logic |
| Reading the error body multiple times | Body is already consumed or unavailable | Decode once in onStatus or use WebClientResponseException |
| Logging every response body | Can leak PII, tokens, or secrets | Log status, request ID, and allowed metadata |
| Forwarding all upstream headers | Can leak hop-by-hop or internal headers | Use a header allowlist |
| Using toEntityFlux but ignoring the body Flux | Holds connections/resources unnecessarily | Consume or cancel the body according to lifecycle |
| Catching all errors into Mono.empty | Hides HTTP, network, timeout, and decode errors | Classify exceptions and preserve root causes |
| Assuming every status is an HttpStatus enum value | Inflexible with extension status codes | Use HttpStatusCode and value() |

## 19. Checklist when using toEntity

Before using it in a service, determine:

1. Are status and headers genuinely needed alongside the body?
2. Does the body target type match the response Content-Type?
3. Should 4xx/5xx statuses become exceptions by default or be kept as ResponseEntity?
4. If suppressing 404, is the error body compatible with the target type?
5. Can the response have no body?
6. Do you need to read ETag, Location, Retry-After, or correlation ID?
7. Is the body an object, list, generic envelope, or stream?
8. Should toEntityList, toEntityFlux, or toBodilessEntity be used?
9. Are there timeouts, retries, or error mappings per upstream SLA?
10. Are you blocking on the reactive request path?
11. If forwarding headers, is an allowlist used?
12. Are status, headers, body, empty body, and error statuses tested?

| Need | Suitable API |
| --- | --- |
| Get object and HTTP metadata | `retrieve().toEntity(Type.class)` |
| Get single body | `retrieve().bodyToMono(Type.class)` |
| Get list and metadata | `retrieve().toEntityList(Type.class)` |
| Get generic wrapper | `toEntity(new ParameterizedTypeReference<...>() {})` |
| Get only status and headers | `retrieve().toBodilessEntity()` |
| Keep stream body in ResponseEntity | `retrieve().toEntityFlux(Type.class)` |
| Branch decoding by status | `exchangeToMono` / `exchangeToFlux` |
| Map HTTP errors | `retrieve().onStatus(...)` |

## 20. Self-check questions with answers

**Question 1.** What type does `toEntity(Product.class)` return?

**Answer:** `Mono<ResponseEntity<Product>>`. When the publisher emits its result, ResponseEntity contains status, headers, and decoded Product.

**Question 2.** Which API is called to get the status code?

**Answer:** `response.getStatusCode()`; use `value()` if an integer is needed.

**Question 3.** Where do you read ETag and request ID?

**Answer:** `response.getHeaders().getETag()` and `getFirst("X-Request-Id")`.

**Question 4.** Does `toEntity` turn 404 into a ResponseEntity by default?

**Answer:** No. `retrieve()` maps 4xx/5xx to WebClientResponseException by default. Use `onStatus` to suppress or map specific statuses.

**Question 5.** How do you keep 404 as a normal response?

**Answer:** Add `onStatus(status -> status.value() == 404, response -> Mono.empty())` before `toEntity`. Then check the status and a potentially null body.

**Question 6.** When should `bodyToMono` be used instead of `toEntity`?

**Answer:** When only the body is needed and status/headers are not required in the result.

**Question 7.** Why use `ParameterizedTypeReference`?

**Answer:** To preserve generic type information, such as PageResult<Product> or ApiEnvelope<List<Product>>, so the codec decodes into the right type.

**Question 8.** How does `toEntityList` differ from `toEntityFlux`?

**Answer:** toEntityList aggregates the body into a List; toEntityFlux keeps the body as a Flux for streaming processing.

**Question 9.** When DELETE returns 204 and only metadata is needed, what should be used?

**Answer:** `retrieve().toBodilessEntity()`, which returns `Mono<ResponseEntity<Void>>`.

**Question 10.** Should `block()` be called in a WebFlux service to read a ResponseEntity?

**Answer:** No. Return Mono and compose; only use block at intentional synchronous boundaries such as tests or CLIs.

**Question 11.** How does `exchangeToMono` differ from `retrieve().toEntity`?

**Answer:** exchangeToMono grants access to ClientResponse to decide how to decode based on status/headers; retrieve().toEntity is the shorthand path for a standard response entity.

**Question 12.** Why should the Flux body in ResponseEntity<Flux<T>> not be ignored?

**Answer:** An unconsumed body can hold connections and resources. Consume or cancel the publisher according to its lifecycle.

## 21. Key takeaways and official documentation

- `retrieve().toEntity(Type.class)` returns `Mono<ResponseEntity<T>>`.
- ResponseEntity provides the status code, response headers, and decoded body.
- `getStatusCode()` returns `HttpStatusCode`; `getHeaders()` reads metadata; `getBody()` retrieves the object.
- By default, 4xx/5xx from retrieve() produces WebClientResponseException, even when the terminal operation is toEntity.
- Use `onStatus` to map errors or suppress specific statuses with Mono.empty().
- Check for null body when the response has no content.
- Use `ParameterizedTypeReference` for generic types.
- Use `toEntityList` for finite lists, `toEntityFlux` for streams, and `toBodilessEntity` when no body is needed.
- Use `exchangeToMono` when decoding control based on status and headers is required.
- Do not block on the reactive request path; consume the body once and manage publisher lifecycle.
- Only forward response headers using an allowlist in an API gateway.

Official documentation:

1. [Spring Framework Reference — WebClient retrieve()](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): toEntity, bodyToMono, bodyToFlux, and default 4xx/5xx handling.
2. [Spring Framework Reference — WebClient exchangeToMono/exchangeToFlux](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html): accessing ClientResponse and managing the response body.
3. [Spring Framework Javadoc — WebClient.ResponseSpec](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/client/WebClient.ResponseSpec.html): toEntity, toEntityList, toEntityFlux, toBodilessEntity, and onStatus.
4. [Spring Framework Javadoc — ResponseEntity](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseEntity.html): status, headers, and body.
5. [Spring Framework Javadoc — HttpStatusCode](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/HttpStatusCode.html): status abstraction and status family checks.
6. [Spring Framework Javadoc — WebClientResponseException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/client/WebClientResponseException.html): status, headers, and error response body.
7. [Spring Framework Reference — WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): configuring WebClient, connectors, and codecs.
8. [Spring Framework Reference — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing HTTP client/server exchanges.
