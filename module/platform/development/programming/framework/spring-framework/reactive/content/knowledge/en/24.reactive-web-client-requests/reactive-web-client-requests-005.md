# Sending Objects via bodyValue in Spring WebClient

## 1. What Problem Does bodyValue Solve?

**WebClient** is Spring WebFlux's reactive HTTP client. When sending POST, PUT, or PATCH requests, applications often need to serialize a Java object into JSON to send in the HTTP body.

For example, given an object:

~~~java
ProductRequest request = new ProductRequest(
    "BK-01",
    "Reactive Guide",
    new BigDecimal("12.50"),
    2
);
~~~

We can send that object using **bodyValue(request)**:

~~~java
Mono<ProductResponse> result = webClient.post()
    .uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

Spring selects the appropriate HTTP message writer to encode the object into the request body. For JSON with Jackson on the classpath, the Java object is serialized to JSON. The application does not need to call ObjectMapper manually to turn the object into a JSON string.

**bodyValue is for a concrete value that is already available**, such as a DTO, record, Map, or collection. When the body source is a Mono/Flux or another reactive producer, use **body(...)** so WebClient consumes the Publisher.

This lesson focuses on:

- Differences between bodyValue(Object) and body(Publisher, elementType).
- How Content-Type, Accept, and HTTP message codecs determine serialization.
- Sending DTOs/records, Maps, form data, and multipart.
- Reading responses with retrieve(), onStatus(), and exchangeToMono().
- Error handling, retries, timeouts, and response body lifecycle.
- Configuring reusable WebClient instances in a Spring Boot application.
- Testing request bodies with MockWebServer and StepVerifier.

## 2. Where Does bodyValue Fit in the Fluent API?

A WebClient request is typically constructed in steps:

~~~text
WebClient
   |
   v
post() / put() / patch()
   |
   v
uri(...)
   |
   v
headers / contentType / accept
   |
   v
bodyValue(object)
   |
   v
retrieve() or exchangeToMono()
   |
   v
bodyToMono(...) / bodyToFlux(...)
~~~

Example:

~~~java
webClient.post()
    .uri("/orders")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(order)
    .retrieve()
    .bodyToMono(OrderResponse.class);
~~~

- **post()** selects the HTTP method.
- **uri(...)** selects the URL/path and URI variables.
- **contentType(...)** describes the format of the request body.
- **accept(...)** describes the response format the client desires.
- **bodyValue(...)** supplies a concrete body value.
- **retrieve()** begins declaring how to process the response.
- **bodyToMono(...)** decodes the response into a Java type.

The result is a **Mono<OrderResponse>**. WebClient preserves the reactive model; there is no need to block in services or controllers.

## 3. How Does bodyValue(Object) Differ from body(Publisher, Class)?

This is the most important distinction.

| API | Input | When to use |
| --- | --- | --- |
| **bodyValue(object)** | A concrete object | Already have a DTO/record/Map to send |
| **body(publisher, Class)** | Publisher such as Mono or Flux | Body is emitted asynchronously |
| **body(publisher, ParameterizedTypeReference)** | Publisher with generic element type | Need to preserve generic type information |
| **body(BodyInserter)** | Custom BodyInserter | Need fine-grained control over writing the body |
| **bodyValue(MultiValueMap<String,String>)** | Key/value form data | Sending application/x-www-form-urlencoded |
| **body(MultipartBodyBuilder.build())** | Multipart parts | Sending fields, JSON parts, and files |

### 3.1. bodyValue Is for a Single Object

~~~java
ProductRequest product = new ProductRequest(
    "BK-01",
    "Reactive Guide",
    new BigDecimal("12.50"),
    2
);

Mono<ProductResponse> response = webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(product)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

The request body is encoded from the ProductRequest object. Serialization only happens when the request is subscribed to and sent; calling bodyValue does not itself execute a synchronous request.

### 3.2. Publishers Must Use body(...)

Do not use:

~~~java
Mono<ProductRequest> productMono = Mono.just(product);

webClient.post()
    .uri("/products")
    .bodyValue(productMono);
~~~

**bodyValue does not accept a Publisher or types supported by ReactiveAdapterRegistry**. Spring may throw IllegalArgumentException because it cannot treat a Publisher as a single object to serialize.

Use:

~~~java
Mono<ProductRequest> productMono = Mono.just(product);

Mono<ProductResponse> response = webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .body(productMono, ProductRequest.class)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

With Flux:

~~~java
Flux<ProductRequest> products = Flux.just(product1, product2);

Mono<Void> sent = webClient.post()
    .uri("/products/import")
    .contentType(MediaType.APPLICATION_STREAM_JSON)
    .body(products, ProductRequest.class)
    .retrieve()
    .bodyToMono(Void.class);
~~~

The Publisher is consumed according to pipeline demand. This is appropriate for progressively emitted data or large streams.

### 3.3. bodyValue Is Not block()

The name bodyValue does not mean a blocking operation. It simply distinguishes the body as a concrete value rather than a Publisher. The request still executes asynchronously and returns a Mono/Flux.

Do not write:

~~~java
ProductResponse response = webClient.post()
    .uri("/products")
    .bodyValue(product)
    .retrieve()
    .bodyToMono(ProductResponse.class)
    .block();
~~~

in a WebFlux controller or reactive service. Return the Publisher to the next calling layer:

~~~java
return webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(product)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

Only consider blocking at imperative/CLI boundaries or in tests when truly necessary.

## 4. Serialization: How Does a Java Object Become an HTTP Body?

WebClient uses **HTTP message codecs** to encode the request body. The codec is chosen based on the object type, Content-Type, and codecs registered in ClientCodecConfigurer.

Example with JSON:

~~~java
ProductRequest request = new ProductRequest(
    "BK-01",
    "Reactive Guide",
    new BigDecimal("12.50"),
    2
);

webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request);
~~~

If Jackson is configured, the JSON may be:

~~~json
{
  "sku": "BK-01",
  "name": "Reactive Guide",
  "price": 12.50,
  "quantity": 2
}
~~~

Spring Boot WebFlux typically provides the Jackson JSON codec when the appropriate dependency is present. In a custom project, check ClientCodecConfigurer and Jackson dependencies if objects are not serialized as expected.

### 4.1. Content-Type and Accept Have Different Meanings

- **Content-Type: application/json**: the request body is sent in JSON format.
- **Accept: application/json**: the client wants the server to return the response in JSON format.

Example:

~~~java
webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .accept(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

Setting both headers explicitly keeps the contract clear and avoids relying on server default behavior.

### 4.2. Do Not Manually Serialize to String Unless Needed

Unnecessary:

~~~java
String json = objectMapper.writeValueAsString(request);

webClient.post()
    .uri("/products")
    .bodyValue(json);
~~~

Here bodyValue receives a String rather than the DTO. The writer may choose how to write a String instead of serializing the object via the JSON codec. If you serialize manually, you must manage Content-Type, encoding, escaping, and serialization errors yourself.

Normally you should pass the original object:

~~~java
webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request);
~~~

### 4.3. DTO, Record, Map, and Collection

bodyValue can accept many object shapes:

~~~java
.bodyValue(new ProductRequest(...))
~~~

~~~java
.bodyValue(Map.of(
    "sku", "BK-01",
    "quantity", 2
))
~~~

~~~java
.bodyValue(List.of(product1, product2))
~~~

For collections, the codec serializes the collection structure into a JSON array if the Content-Type and selected codec match. If you want to emit elements one by one as a stream, use Flux with body(...), rather than collecting the entire list just to use bodyValue.

### 4.4. Null and Empty Bodies

bodyValue is for an actual value; do not pass null. If a request has no body, use the appropriate empty-body API or omit the body step.

Do not use the string "null" to simulate an empty body. JSON null and an HTTP request with no body are two different things.

## 5. Sending Form Data and Multipart

bodyValue can also send form data, though two types must be distinguished.

### 5.1. URL-Encoded Form

Use **MultiValueMap<String,String>**:

~~~java
MultiValueMap<String, String> form =
    new LinkedMultiValueMap<>();

form.add("username", "lan");
form.add("role", "student");

Mono<String> response = webClient.post()
    .uri("/login")
    .bodyValue(form)
    .retrieve()
    .bodyToMono(String.class);
~~~

With MultiValueMap<String,String>, **FormHttpMessageWriter** automatically sets Content-Type to **application/x-www-form-urlencoded**.

Another form uses BodyInserters:

~~~java
Mono<String> response = webClient.post()
    .uri("/login")
    .body(BodyInserters.fromFormData("username", "lan")
        .with("role", "student"))
    .retrieve()
    .bodyToMono(String.class);
~~~

Do not set application/json for a form-urlencoded body.

### 5.2. Multipart Form Data

When a request contains files, text fields, and JSON parts, use **MultipartBodyBuilder**:

~~~java
MultipartBodyBuilder builder = new MultipartBodyBuilder();

builder.part("description", "Product manual");
builder.part("metadata", productRequest)
    .contentType(MediaType.APPLICATION_JSON);
builder.part(
    "file",
    new FileSystemResource("/srv/files/manual.pdf")
);

MultiValueMap<String, HttpEntity<?>> parts = builder.build();

Mono<String> response = webClient.post()
    .uri("/documents")
    .body(BodyInserters.fromMultipartData(parts))
    .retrieve()
    .bodyToMono(String.class);
~~~

The multipart writer generates the boundary and encodes each part. Normally do not manually set the multipart/form-data header to a fixed string because Content-Type must include the boundary matching the body.

Spring determines each part's Content-Type from the selected writer or from the Resource/file extension; you can specify it explicitly when needed.

### 5.3. Multipart Streaming with PartEvent

For large files or when streaming part by part, WebClient supports **PartEvent**. You can combine FormPartEvent and FilePartEvent with Flux.concat and pass it to body(...). This is the streaming multipart path; do not load an entire file into a byte[] just to pass it via bodyValue.

## 6. BodyInserters and bodyValue

**BodyInserters** provides the lower-level API for creating a BodyInserter. bodyValue is a convenient shortcut for the single-object case.

Equivalent examples:

~~~java
.bodyValue(product)
~~~

and:

~~~java
.body(BodyInserters.fromValue(product))
~~~

**BodyInserters.fromValue(...)** is also for a single value. It throws IllegalArgumentException if the object is a Publisher or a type supported by ReactiveAdapterRegistry; in those cases use fromPublisher/fromProducer or WebClient.body(...).

Common APIs:

| API | Purpose |
| --- | --- |
| **BodyInserters.fromValue(value)** | Writes a single value |
| **BodyInserters.fromPublisher(publisher, Class)** | Writes a Publisher with an element class |
| **BodyInserters.fromPublisher(publisher, ParameterizedTypeReference)** | Writes a Publisher with a generic type |
| **BodyInserters.fromProducer(producer, Class)** | Writes a producer supported by ReactiveAdapterRegistry |
| **BodyInserters.fromFormData(...)** | Writes form-urlencoded data |
| **BodyInserters.fromMultipartData(...)** | Writes multipart data |

Do not use **fromObject(...)** in new code; this API has been deprecated since Spring Framework 5.2 in favor of fromValue(...).

## 7. Handling the Response After Sending the Body

Sending the request body is only half of an HTTP operation. WebClient must decode the response or handle the status.

### 7.1. retrieve() and bodyToMono()

Example:

~~~java
Mono<ProductResponse> response = webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

- **retrieve()** declares how to read the response.
- **bodyToMono(ProductResponse.class)** decodes the body into a single object.
- **bodyToFlux(ProductResponse.class)** decodes a stream of objects.
- **toEntity(ProductResponse.class)** retrieves status, headers, and body.
- **toBodilessEntity()** retrieves response metadata when no body is needed.

By default, 4xx or 5xx response statuses cause WebClient to emit **WebClientResponseException** or a corresponding subtype.

### 7.2. Customizing Errors with onStatus()

Example:

~~~java
Mono<ProductResponse> response = webClient.post()
    .uri("/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .retrieve()
    .onStatus(
        HttpStatusCode::is4xxClientError,
        clientResponse -> clientResponse
            .bodyToMono(String.class)
            .defaultIfEmpty("")
            .map(body -> new RemoteApiException(
                clientResponse.statusCode(),
                body
            ))
    )
    .bodyToMono(ProductResponse.class);
~~~

The example assumes a **RemoteApiException** class that takes HttpStatusCode and the error content. onStatus converts error responses into exceptions matching the application contract.

Do not read the error body in one place and then try to read it again downstream. The response body is a stream; consume it exactly once or convert it into the required error data before emitting the exception.

### 7.3. exchangeToMono() When Status Control Is Needed

When you need to decide how to decode differently based on status, use **exchangeToMono()** or **exchangeToFlux()**:

~~~java
Mono<ProductResponse> response = webClient.get()
    .uri("/products/{sku}", sku)
    .exchangeToMono(clientResponse -> {
        if (clientResponse.statusCode().is2xxSuccessful()) {
            return clientResponse.bodyToMono(ProductResponse.class);
        }

        if (clientResponse.statusCode().value() == 404) {
            return Mono.empty();
        }

        return clientResponse.createError();
    });
~~~

This is an example for a product lookup API. exchangeToMono allows controlling how the response is read based on status, headers, or media type. After the Publisher returned from the callback completes, Spring checks and releases any unconsumed body to prevent connection/buffer leaks.

If you need the error body, decode it inside the callback before completing. Do not retain ClientResponse and try to read its body in another pipeline after the callback has finished.

## 8. Configuring and Reusing WebClient

In a Spring Boot application, create a reusable WebClient rather than creating a new one on every call.

Example:

~~~java
@Configuration
public class WebClientConfiguration {

    @Bean
    WebClient inventoryWebClient(
        WebClient.Builder builder
    ) {
        return builder
            .baseUrl("https://inventory.example")
            .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE
            )
            .build();
    }
}
~~~

Service receiving the bean:

~~~java
@Service
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(
        @Qualifier("inventoryWebClient") WebClient webClient
    ) {
        this.webClient = webClient;
    }

    public Mono<ProductResponse> create(ProductRequest request) {
        return webClient.post()
            .uri("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(ProductResponse.class);
    }
}
~~~

Once built, WebClient can be reused across multiple requests. Base URL, default headers, filters, connector, timeouts, and codecs can be configured on the builder.

Do not create a new WebClient on every method call unless there is a specific connector requirement. Reuse enables connection pooling and consistent configuration.

### 8.1. Headers and Authentication

Per-request headers can be added:

~~~java
webClient.post()
    .uri("/api/products")
    .headers(headers -> {
        headers.setBearerAuth(accessToken);
        headers.set("X-Request-Id", requestId);
    })
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

Do not hardcode tokens or secrets in source code. Tokens should come from the security context, a credential provider, or an appropriate secret management mechanism.

### 8.2. URI Variables and Query Parameters

Example:

~~~java
webClient.post()
    .uri(builder -> builder
        .path("/api/products/{sku}")
        .queryParam("notify", true)
        .build(sku))
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .retrieve()
    .bodyToMono(ProductResponse.class);
~~~

Use the URI builder to encode path/query values properly. Avoid manual string concatenation when data may contain special characters.

### 8.3. Shared Filters

Exchange filters can add logging, correlation IDs, authentication, or metrics. Do not log sensitive raw bodies by default. Filters should preserve the response body lifecycle properly and never manually subscribe to the request/response Publisher.

## 9. Timeouts, Retries, and Idempotency

WebClient is a reactive client, yet requests can still fail due to connect timeouts, response timeouts, DNS, TLS, server errors, or network disconnects.

You can apply a timeout to an operation:

~~~java
return webClient.post()
    .uri("/api/products")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(request)
    .retrieve()
    .bodyToMono(ProductResponse.class)
    .timeout(Duration.ofSeconds(5));
~~~

This is an application-layer Publisher timeout. Connect/read timeouts on the transport connector must be configured separately as appropriate; Mono's timeout does not replace all network timeouts.

### 9.1. Retries Are Not Always Safe

Example:

~~~java
return inventoryClient.create(request)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(200))
            .filter(this::isTransientFailure)
    );
~~~

Retries should only apply to clearly defined transient failures. With a POST that creates data, the server may have succeeded while the response was lost; retrying can create duplicate records.

Safeguards:

- Use an **Idempotency-Key** for creation operations if the API supports it.
- Only retry connection/timeout errors consistent with business policy.
- Do not retry validation errors or authorization errors.
- Set attempt limits and backoff.
- Log the correlation ID and idempotency key.

### 9.2. BodyValue and Request Replay

bodyValue takes a concrete object, but resending the request still depends on whether the Publisher and body inserter can recreate the content. Do not assume every body stream is replayable. For bodies coming from a file stream or single-use source, design retries and source reopening properly.

## 10. Runnable Java 17+ Example: Sending a DTO with bodyValue

This example uses **Spring Boot 3.3.5**, Spring Framework 6.1.x, and Java 17. The project illustrates a ProductClient sending a record as JSON via bodyValue and testing the real request with MockWebServer.

Structure:

~~~text
webclient-bodyvalue-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/bodyvalue/
    │           ├── ProductRequest.java
    │           ├── ProductResponse.java
    │           └── ProductClient.java
    └── test/
        └── java/
            └── com/example/bodyvalue/
                └── ProductClientTest.java
~~~

### 10.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>webclient-bodyvalue-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
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

        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### 10.2. ProductRequest.java

~~~java
package com.example.bodyvalue;

import java.math.BigDecimal;

public record ProductRequest(
    String sku,
    String name,
    BigDecimal price,
    int quantity
) {}
~~~

A record is an immutable DTO well suited for representing request data. Jackson in Spring Boot can serialize records to JSON.

### 10.3. ProductResponse.java

~~~java
package com.example.bodyvalue;

public record ProductResponse(
    String id,
    String status
) {}
~~~

### 10.4. ProductClient.java

~~~java
package com.example.bodyvalue;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

public class ProductClient {

    private final WebClient webClient;

    public ProductClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<ProductResponse> create(ProductRequest request) {
        return webClient.post()
            .uri("/products")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(ProductResponse.class);
    }
}
~~~

ProductClient receives an externally configured WebClient. The create method only describes the request and returns a Publisher; it does not block and does not create a new client itself.

### 10.5. ProductClientTest.java

~~~java
package com.example.bodyvalue;

import java.math.BigDecimal;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class ProductClientTest {

    private MockWebServer server;
    private ProductClient client;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void setUp() throws Exception {
        server = new MockWebServer();
        server.start();

        WebClient webClient = WebClient.builder()
            .baseUrl(server.url("/").toString())
            .build();

        client = new ProductClient(webClient);
    }

    @AfterEach
    void tearDown() throws Exception {
        server.shutdown();
    }

    @Test
    void serializesRecordAsJsonRequestBody() throws Exception {
        server.enqueue(
            new MockResponse()
                .setResponseCode(201)
                .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE
                )
                .setBody(
                    "{\"id\":\"P-100\",\"status\":\"created\"}"
                )
        );

        ProductRequest request = new ProductRequest(
            "BK-01",
            "Reactive Guide",
            new BigDecimal("12.50"),
            2
        );

        StepVerifier.create(client.create(request))
            .assertNext(response -> {
                assertEquals("P-100", response.id());
                assertEquals("created", response.status());
            })
            .verifyComplete();

        RecordedRequest recorded =
            server.takeRequest(1, TimeUnit.SECONDS);

        assertNotNull(recorded);
        assertEquals("POST", recorded.getMethod());
        assertEquals("/products", recorded.getPath());
        assertTrue(
            recorded.getHeader("Content-Type")
                .startsWith(MediaType.APPLICATION_JSON_VALUE)
        );
        assertEquals(
            MediaType.APPLICATION_JSON_VALUE,
            recorded.getHeader("Accept")
        );

        JsonNode json = objectMapper.readTree(
            recorded.getBody().readUtf8()
        );

        assertEquals("BK-01", json.get("sku").asText());
        assertEquals("Reactive Guide", json.get("name").asText());
        assertEquals(
            0,
            new BigDecimal("12.50")
                .compareTo(json.get("price").decimalValue())
        );
        assertEquals(2, json.get("quantity").asInt());
    }

    @Test
    void mapsBadRequestToWebClientResponseException() {
        server.enqueue(
            new MockResponse()
                .setResponseCode(400)
                .setHeader(
                    "Content-Type",
                    MediaType.APPLICATION_JSON_VALUE
                )
                .setBody("{\"code\":\"INVALID_PRODUCT\"}")
        );

        ProductRequest request = new ProductRequest(
            "INVALID",
            "Broken Product",
            BigDecimal.ONE,
            1
        );

        StepVerifier.create(client.create(request))
            .expectError(WebClientResponseException.BadRequest.class)
            .verify();
    }
}
~~~

The first test verifies that the response is decoded into ProductResponse and the actual request contains JSON with the expected fields. The second test confirms that retrieve() by default converts HTTP 400 into WebClientResponseException.BadRequest.

### 10.6. Running Tests

Requires JDK 17+ and Maven:

~~~bash
mvn clean test
~~~

Maven runs the JUnit tests. MockWebServer receives the real HTTP request from WebClient, allowing verification of method, path, Content-Type, Accept, and JSON body without calling an external service.

## 11. Example Using WebClient in Spring Boot

When integrating into an application, you can register a bean:

~~~java
@Configuration
public class InventoryClientConfiguration {

    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
            .baseUrl("http://localhost:8081")
            .defaultHeader(
                HttpHeaders.ACCEPT,
                MediaType.APPLICATION_JSON_VALUE
            )
            .build();
    }
}
~~~

Inject into a service:

~~~java
@Service
public class InventoryService {

    private final WebClient inventoryWebClient;

    public InventoryService(
        @Qualifier("inventoryWebClient")
        WebClient inventoryWebClient
    ) {
        this.inventoryWebClient = inventoryWebClient;
    }

    public Mono<ProductResponse> create(ProductRequest request) {
        return inventoryWebClient.post()
            .uri("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(ProductResponse.class);
    }
}
~~~

Controller calling the service:

~~~java
@PostMapping("/products")
public Mono<ProductResponse> create(
    @RequestBody ProductRequest request
) {
    return inventoryService.create(request);
}
~~~

The entire path remains reactive. The controller receives the object from the client request, the service sends that object to another service using bodyValue, and returns the Publisher to WebFlux.

If the target service can return business errors, add onStatus or exchangeToMono according to the target API's contract.

## 12. Common Mistakes and How to Fix Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| IllegalArgumentException when calling bodyValue | Passed a Mono, Flux, or reactive producer | Use body(publisher, Class) |
| Server cannot parse JSON | Wrong Content-Type or missing JSON codec | Set application/json and check the Jackson codec |
| Server receives a JSON string with escaped quotes | Serialized DTO to String then called bodyValue(String) | Pass the original DTO to bodyValue |
| Server returns 415 Unsupported Media Type | Content-Type is not supported by the endpoint | Set the right media type per the API contract |
| Server returns 406 Not Acceptable | Accept does not match responses the server can return | Check Accept and response media types |
| Request body is a form but server expects JSON | Used MultiValueMap<String,String> and FormHttpMessageWriter | Use a JSON DTO or change contract to form-urlencoded |
| Multipart missing boundary | Manually set multipart/form-data Content-Type | Use MultipartBodyBuilder and let the writer generate the boundary |
| Mono does not send the request | Not subscribed or not composed into a pipeline | Return the Publisher to the caller or subscribe at the appropriate boundary |
| WebFlux controller hangs | Called block() on the event loop | Compose Mono/Flux instead of blocking |
| 4xx/5xx becomes an exception | retrieve() emits WebClientResponseException by default | Use onStatus or exchangeToMono if custom behavior is needed |
| Error body cannot be read elsewhere | Body was already consumed or response released | Decode the body inside the same status-handling pipeline |
| Connection/buffer leak | exchange callback fails to consume body and mismanages response | Use exchangeToMono/Flux per contract; let framework release unread bodies |
| Retries create duplicate data | POST succeeded but response was lost | Use an idempotency key and selective retries |
| Large files spike heap usage | Collected file into byte[] or passed entire payload via bodyValue | Use Resource or appropriate streaming Publisher |
| Cannot verify JSON request in tests | Only tested response without capturing request | Use MockWebServer and inspect RecordedRequest |
| Generic type mismatch | Publisher element type was erased or declared incorrectly | Use ParameterizedTypeReference overload when needed |

## 13. Checklist Before Using bodyValue

1. Is the body already a concrete object or a Publisher?
2. If it is Mono/Flux, have you used body(...)?
3. Does the DTO have fields and types matching the API contract?
4. Does Content-Type match the request format?
5. Does Accept match the desired response format?
6. Are required codecs such as Jackson available?
7. Do you truly need to send an entire collection at once or should it stream?
8. If form-urlencoded, is MultiValueMap the right type?
9. If multipart, is MultipartBodyBuilder used to generate the boundary?
10. Is retrieve() sufficient or is exchangeToMono() needed?
11. How are 4xx/5xx handled according to policy?
12. Are retries safe with respect to method and side effects?
13. Are timeouts configured at both application and transport layers?
14. Is the response body consumed/released exactly once?
15. Are there tests verifying the actual request body with MockWebServer?

## 14. Practice Exercises

**Exercise 1 — Single DTO:** Create a ProductRequest record and send it with bodyValue. Inspect the JSON body on MockWebServer.

**Exercise 2 — Map:** Replace the record with Map<String,Object>. Compare the serialized JSON and test optional fields.

**Exercise 3 — Content-Type:** Omit contentType(APPLICATION_JSON), observe the request header and how the server handles it. Then explicitly set the header again.

**Exercise 4 — Publisher:** Replace ProductRequest with Mono<ProductRequest>. Use body(mono, ProductRequest.class) and verify the request is still sent.

**Exercise 5 — Flux:** Send Flux<ProductRequest> with application/stream+json. Compare with a JSON array sent via bodyValue(List).

**Exercise 6 — Form:** Send MultiValueMap<String,String> with bodyValue and verify application/x-www-form-urlencoded.

**Exercise 7 — Multipart:** Use MultipartBodyBuilder to send JSON metadata alongside a file Resource. Inspect the boundary and each part.

**Exercise 8 — Error mapping:** Return a 400 response and use onStatus to map it to RemoteApiException with an error code.

**Exercise 9 — exchangeToMono:** For 404 return Mono.empty; for 2xx decode ProductResponse; for other statuses propagate the exception.

**Exercise 10 — Retry:** Simulate a timeout or 503. Add a bounded retryWhen and verify validation errors are not retried.

**Exercise 11 — Idempotency:** Add Idempotency-Key to a POST request and design the server not to create duplicate records when the client retries.

**Exercise 12 — Reactive pipeline:** Call WebClient from a WebFlux controller, return the Mono directly, and confirm there is no block() on the processing path.

## 15. Key Takeaways

**bodyValue(Object)** is WebClient's shortcut for sending a concrete value such as a DTO, record, Map, or collection. Spring uses HTTP message codecs to serialize the body according to Content-Type. For JSON, pass the original object and set application/json when an explicit contract is needed.

When the body is a **Mono**, **Flux**, or reactive producer, use **body(...)**; bodyValue is not for Publishers and may throw IllegalArgumentException. For form-urlencoded, MultiValueMap<String,String> can be written automatically; for multipart, use MultipartBodyBuilder and body(...).

After sending the request, choose retrieve() for standard responses, onStatus() to customize errors, or exchangeToMono/Flux() when status-driven control is needed. Keep the pipeline reactive, manage the body lifecycle properly, and only retry when operations are safe/idempotent.

## 16. References

- Spring Framework Reference — WebClient Request Body: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-body.html
- Spring Framework API — WebClient: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/reactive/function/client/WebClient.html
- Spring Framework API — BodyInserters: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/reactive/function/BodyInserters.html
- Spring Framework Reference — WebClient retrieve(): https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework Reference — WebClient exchangeToMono/exchangeToFlux: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-exchange.html
- Spring Framework API — ClientCodecConfigurer: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/codec/ClientCodecConfigurer.html
- Spring Boot Reference — WebClient: https://docs.spring.io/spring-boot/reference/io/rest-client.html
- Reactor Reference Guide — Error Handling and Retry: https://projectreactor.io/docs/core/release/reference/
