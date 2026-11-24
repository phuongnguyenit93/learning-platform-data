# HttpMessageConverter, Generics, and ParameterizedTypeReference in Synchronous HTTP Clients

## 1. What Will You Learn in This Lesson?

In a Spring application, an HTTP call does more than send/receive bytes. Spring needs to know the **target Java type** and the **HTTP body media type** to select a converter between JSON, text, byte array, XML, or form data and Java objects. When an API returns `List<Book>` or `ApiEnvelope<List<Book>>`, `Class<List>` is insufficient to describe the inner element type due to **Java type erasure**. For this reason, Spring provides **`ParameterizedTypeReference<T>`** to preserve generic type metadata at runtime for compatible HTTP APIs.

This topic sits in the **synchronous HTTP clients** group. The focus is on:

- **`RestClient`** (Spring Framework 6.1+, synchronous fluent API; the modern choice in Spring 6.2/Boot 3.5).
- **`RestTemplate`** (long-standing synchronous API, still widely used in projects).
- **`HttpMessageConverter`**, **`GenericHttpMessageConverter`**, and **`MappingJackson2HttpMessageConverter`** for Java ↔ HTTP body conversion.
- Differences among `Class<T>`, `Type`, `ParameterizedTypeReference<T>`, `ResolvableType`, and Jackson `TypeReference` (not the same class).
- Request `Content-Type` vs `Accept`, response `Content-Type`, status errors, converter errors, DTO mapping, and nested generics.
- **Java 17+, Spring Framework 6.2, Spring Boot 3.5** examples testable standalone with **`MockRestServiceServer`**, without calling the live Internet.

**Expected outcome:** decode JSON `[{"id":1,"title":"Spring"}]` into a properly typed **`List<Book>`**; decode `ApiEnvelope<List<Book>>` while preserving `Book`; know how to diagnose `LinkedHashMap cannot be cast to Book`, media type mismatches, and body serialization errors.

### 1.1. Exact Scope

`RestClient` and `RestTemplate` are **blocking/synchronous HTTP clients**. Converters here typically read/write via `InputStream`/`OutputStream`. **`WebClient`** is a reactive client using `HttpMessageReader`/`HttpMessageWriter` and codecs; it also has `ParameterizedTypeReference` overloads, but **does not use synchronous `HttpMessageConverter` through the same pipeline**. Do not mix the two mechanisms when configuring.

This lesson uses JSON examples because JSON is ubiquitous; `HttpMessageConverter` does not mean “only the Jackson converter”. A request can go through String, byte array, form, XML, or custom converters.

## 2. End-to-End HTTP Message Conversion Mechanics

~~~text
Java request object / HttpEntity
          |
          | RestClient.body(obj) or RestTemplate.exchange(...)
          v
Request headers: Content-Type / Accept
          |
          v
HttpMessageConverter.canWrite(targetType, mediaType)
          |
          v
HttpMessageConverter.write(...) -> HTTP bytes
          |
          v
Remote HTTP server
          |
          v
Status + headers + HTTP response body
          |
          v
Requested response Java type (Class<T> / Type via ParameterizedTypeReference)
          |
          v
Converter.canRead(targetType, response Content-Type)
          |
          v
Converter.read(...) -> Java value
~~~

In a synchronous request/response, the thread calling `retrieve().body(...)` or `exchange(...)` typically **waits for I/O and body reading to finish**. You can configure thread pools, timeouts, connection pooling, and concurrency budgets; do not call a blocking REST client on a WebFlux event-loop thread.

**Outbound and inbound paths are independent:**
- **Request write**: Java object → bytes. Spring selects a converter based on **request body type**, `Content-Type`, and the converter list.
- **Response read**: bytes → Java object. Spring needs the **target type** and **response `Content-Type`** to pick a converter.
- HTTP status (2xx/4xx/5xx) is handled by the client/error handler before or alongside body conversion depending on the API/call path.

### 2.1. RestClient Does Not Send a Request Just by Calling retrieve()

In Spring 6.2:

~~~java
RestClient.ResponseSpec spec = client.get()
        .uri("/books")
        .retrieve();

// Only the terminal operation actually reads the response:
List<Book> books = spec.body(BOOK_LIST);
~~~

This is an illustrative snippet: `client`, `Book`, and `BOOK_LIST` must be declared. Spring docs state that `retrieve()` itself causes no side effects; only terminal methods `body(...)`, `toEntity(...)`, and `toBodilessEntity()` execute the request. Do not assume the network call already fired right after `retrieve()`.

With RestTemplate, calls like `getForObject` or `exchange` execute inside that method itself.

## 3. What Is HttpMessageConverter?

`org.springframework.http.converter.HttpMessageConverter<T>` is Spring's interface for reading/writing HTTP bodies:

~~~java
boolean canRead(Class<?> clazz, MediaType mediaType);
boolean canWrite(Class<?> clazz, MediaType mediaType);
List<MediaType> getSupportedMediaTypes();
T read(Class<? extends T> clazz, HttpInputMessage inputMessage);
void write(T t, MediaType contentType, HttpOutputMessage outputMessage);
~~~

These are **simplified signatures** for illustration, not the verbatim interface source across every version (nullable annotations, overloads, and declared exceptions are omitted).

Common converters:

| Converter | Input/Output | Typical Media Types | Points to Remember |
| --- | --- | --- | --- |
| `StringHttpMessageConverter` | `String` ↔ text | `text/plain`, `text/*` | Does not parse JSON into a DTO even if the string contains JSON |
| `ByteArrayHttpMessageConverter` | `byte[]` ↔ bytes | `*/*`, typically writes octet-stream | Used for small bounded binary data |
| `ResourceHttpMessageConverter` | `Resource` ↔ stream/file response | Depends on resource/media type | Not a JSON parser |
| `FormHttpMessageConverter` | Form URL-encoded, writes multipart | `application/x-www-form-urlencoded`, multipart | Multipart has multiple parts; distinguish maps and files |
| `MappingJackson2HttpMessageConverter` | DTO/collection ↔ JSON | `application/json`, `application/*+json` | Relies on Jackson ObjectMapper and Type metadata |
| `MarshallingHttpMessageConverter` | XML via marshaller | `application/xml`/`text/xml` | Depends on dependencies/config |
| Custom converter | Binary/protobuf/vendor media | e.g., `application/x-my-format` | Must specify canRead/canWrite and ordering carefully |

**There is no immutable fixed list** across all applications: the classpath, Spring Boot auto-configuration, client builders, and custom registrations determine the actual converters. Spring MVC server-side configuration and RestClient/RestTemplate client-side configuration may differ.

### 3.1. Why Is GenericHttpMessageConverter Important?

The base `HttpMessageConverter` interface takes **`Class`**, such as `Book.class` or `List.class`. `Class<List>` cannot represent the full type `List<Book>` because generic type parameters are erased at runtime.

`GenericHttpMessageConverter<T>` extends this interface to work with Java reflection **`Type`**:

~~~java
boolean canRead(Type type, Class<?> contextClass, MediaType mediaType);
T read(Type type, Class<?> contextClass, HttpInputMessage inputMessage);
boolean canWrite(Type type, Class<?> clazz, MediaType mediaType);
~~~

These are also simplified signatures. When a converter supports generics, it can see `List<Book>`, `Map<String, List<Book>>`, or `ApiEnvelope<List<Book>>` instead of just raw `List`.

**However:** `ParameterizedTypeReference` only **carries type information**; it does not parse JSON by itself. You need a converter that actually understands the media type and generic shape, typically the Jackson JSON converter on the classpath. If the response is `text/html` or the service returns an HTML error page, even a valid type reference cannot turn HTML into `Book`.

## 4. Content-Type, Accept, and Response Type: Three Different Concepts

| Header/API | Where It Lives | Meaning |
| --- | --- | --- |
| Request `Content-Type: application/json` | Request from client | Outgoing bytes are formatted as JSON |
| Request `Accept: application/json` | Request from client | Client wants to receive a JSON response |
| Response `Content-Type: application/json` | Response from server | Actual response bytes are JSON |
| `body(Book.class)` | Java client code | Expects to parse body into Book |
| `body(new ParameterizedTypeReference<List<Book>>() {})` | Java client code | Expects to parse body into List with Book elements |

**POST example:**

~~~java
Book result = client.post()
        .uri("/books")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .body(new Book(3L, "Reactive"))
        .retrieve()
        .body(Book.class);
~~~

This is a snippet assuming an already configured `client`. The converter **writes JSON** from Book for the request, the server processes it, and the converter **reads JSON** from the response back into Book. `Accept` does not set request body `Content-Type`, and request `Content-Type` cannot force the remote server to return JSON.

When a server returns JSON while declaring `Content-Type: text/plain`, converter selection may differ; do not fix it by forcing `List.class` or skipping validation. Fix the HTTP contract upstream or configure an intentional custom converter with thorough tests.

## 5. Java Type Erasure and the List.class Problem

Suppose the upstream returns:

~~~json
[
  {"id": 1, "title": "Spring"},
  {"id": 2, "title": "Jackson"}
]
~~~

You want `List<Book>` but write:

~~~java
List<?> books = client.get()
        .uri("/books")
        .retrieve()
        .body(List.class);
~~~

Jackson receives only raw `List`; JSON object elements normally become `LinkedHashMap`, not `Book`. If you cast:

~~~java
@SuppressWarnings("unchecked")
List<Book> wrong = (List<Book>) (List<?>) books;
Book first = wrong.get(0);  // May throw ClassCastException
~~~

The compiler cannot guarantee elements are actually Book once generic types are erased, so the error usually surfaces only when retrieving/casting an element.

### 5.1. Why Is There No `List<Book>.class`?

In Java, class literals can only be written as `Book.class` or `List.class`, never `List<Book>.class`:

~~~java
Class<Book> one = Book.class;
Class<List> many = List.class;
// Class<List<Book>> typed = List<Book>.class; // Invalid Java syntax
~~~

Spring did not forget an overload: Java has no class literal for a **parameterized type**. To retain the `Book` parameter, you must pass a Java `Type` or an object holding that Type.

### 5.2. Non-Generic Object Case

If the single response is:

~~~json
{"id":1,"title":"Spring"}
~~~

then `Book.class` is sufficient:

~~~java
Book book = client.get()
        .uri("/books/1")
        .retrieve()
        .body(Book.class);
~~~

You do not need `ParameterizedTypeReference<Book>` for non-generic DTOs. Use a type reference only when representing `List<Book>`, `Page<Book>`, `Map<String, Book>`, nested envelopes, or resolved type variables.

## 6. ParameterizedTypeReference<T>: Capturing the Full Type

`org.springframework.core.ParameterizedTypeReference<T>` uses an **anonymous subclass** to capture generic metadata from its superclass signature:

~~~java
ParameterizedTypeReference<List<Book>> type =
        new ParameterizedTypeReference<List<Book>>() {};
~~~

**The trailing `{}` braces are essential**: you are creating an anonymous subclass whose superclass carries the `List<Book>` type parameter; Spring uses reflection to capture the target type.

Then with RestClient:

~~~java
List<Book> books = client.get()
        .uri("/books")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(type);
~~~

Or to capture status, headers, and body:

~~~java
ResponseEntity<List<Book>> response = client.get()
        .uri("/books")
        .retrieve()
        .toEntity(type);

HttpStatusCode status = response.getStatusCode();
List<Book> list = response.getBody();
~~~

`ResponseEntity.getBody()` can return **null** when no body exists or the contract permits it, so do not dereference `response.getBody().size()` without a null policy. `retrieve().body(type)` can also return null on 204/empty body responses.

### 6.1. Nested Generics

An API uses an envelope:

~~~json
{
  "data": [
    {"id":1,"title":"Spring"},
    {"id":2,"title":"Jackson"}
  ],
  "traceId": "rid-42"
}
~~~

With DTO:

~~~java
public record ApiEnvelope<T>(T data, String traceId) {}
~~~

The type must preserve **both generic layers**:

~~~java
ParameterizedTypeReference<ApiEnvelope<List<Book>>> type =
        new ParameterizedTypeReference<ApiEnvelope<List<Book>>>() {};

ApiEnvelope<List<Book>> envelope = client.get()
        .uri("/books/envelope")
        .retrieve()
        .body(type);
~~~

If you only pass `ApiEnvelope.class`, Jackson may decode `data` as raw `List<LinkedHashMap>`, losing the `Book` layer.

### 6.2. Generics Beyond List

Examples:

~~~java
ParameterizedTypeReference<Map<String, List<Book>>> mapType =
        new ParameterizedTypeReference<Map<String, List<Book>>>() {};

ParameterizedTypeReference<List<ApiEnvelope<Book>>> listEnvelopeType =
        new ParameterizedTypeReference<List<ApiEnvelope<Book>>>() {};
~~~

Note that `Map<String, List<Book>>` requires a JSON object with property names matching String keys, while `List<ApiEnvelope<Book>>` requires a JSON array where each element has the ApiEnvelope structure. **Accurate type metadata cannot compensate for a mismatched JSON shape**.

### 6.3. Do Not Capture an Unresolved Type Variable as a Concrete Type

Anti-pattern in a generic utility:

~~~java
public <T> T fetch(String path) {
    ParameterizedTypeReference<T> type =
            new ParameterizedTypeReference<T>() {};
    return client.get().uri(path).retrieve().body(type);
}
~~~

This is an illustrative method inside a class with `RestClient client`. `T` is an erased **type variable**, so the anonymous subclass here cannot tell whether the caller actually wants `List<Book>` or `ApiEnvelope<Book>`. Never assume `T` will be inferred completely at runtime.

The proper approach is for the caller to pass a **resolved type token**:

~~~java
public <T> T fetch(String path, ParameterizedTypeReference<T> type) {
    return client.get().uri(path).retrieve().body(type);
}
~~~

At the call site:

~~~java
List<Book> books = fetch(
        "/books", new ParameterizedTypeReference<List<Book>>() {});
~~~

Or if runtime composition is needed, use `ParameterizedTypeReference.forType(Type)` with a properly constructed Java reflection Type. Never build `List<T>` on an unresolved type variable.

### 6.4. `Type` and `ParameterizedTypeReference.forType`

When a library has produced a `java.lang.reflect.Type` from an actual generic method, you can bridge it:

~~~java
Type type = SomeApi.class
        .getDeclaredMethod("listBooks")
        .getGenericReturnType();

ParameterizedTypeReference<?> ref =
        ParameterizedTypeReference.forType(type);
~~~

This is an **illustrative snippet**; `SomeApi` must define the matching method and handle `NoSuchMethodException`. If `listBooks` truly returns `List<Book>`, the reflection Type carries that type. If the method returns an unresolved type variable `T` in context, `forType` cannot guess Book automatically.

Spring also provides `ResolvableType` to inspect generic type hierarchies and combine Type metadata. It is not a JSON decoder.

## 7. RestClient: Typed Response Calls

`RestClient` was added in Spring Framework 6.1, so the examples apply directly to **Spring Framework 6.2 / Spring Boot 3.5**; do not assume compatibility with Spring Boot 3.0 (Spring Framework 6.0).

Creating the client:

~~~java
RestClient client = RestClient.builder()
        .baseUrl("https://api.example.com")
        .defaultHeader("X-App", "demo")
        .build();
~~~

`api.example.com` is an example hostname with no live service. Once built, `RestClient` can be reused across threads; do not create a new client for every request when connection pooling and consistent configuration are needed.

**GET with generic:**

~~~java
ParameterizedTypeReference<List<Book>> type =
        new ParameterizedTypeReference<>() {};

List<Book> books = client.get()
        .uri("/books")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(type);
~~~

**Getting ResponseEntity:**

~~~java
ResponseEntity<List<Book>> entity = client.get()
        .uri("/books")
        .retrieve()
        .toEntity(type);
~~~

**POST with DTO body:**

~~~java
Book created = client.post()
        .uri("/books")
        .contentType(MediaType.APPLICATION_JSON)
        .body(new Book(3L, "REST"))
        .retrieve()
        .body(Book.class);
~~~

**When endpoint returns no body:**

~~~java
ResponseEntity<Void> response = client.delete()
        .uri("/books/{id}", 3)
        .retrieve()
        .toBodilessEntity();
~~~

Do not call `body(Void.class)` expecting to receive a `Void` instance. `toBodilessEntity()` is clearer when only status/headers are needed.

### 7.1. RestClient retrieve() and exchange() Are Not the Same

- `retrieve()` uses terminal operations to decode via converters, along with appropriate status handlers. By default, 4xx/5xx statuses can produce `RestClientResponseException` before business logic processes a success DTO.
- `exchange((request, response) -> ...)` provides lower-level access to the HTTP response and streams, suited for custom/streaming/advanced response handling. With the low-level exchange callback, **retrieve's default status handlers do not apply automatically in the same way**; the caller must explicitly check status/errors/cleanup.
- `retrieve()` alone does not send the request; `body(...)`, `toEntity(...)`, `toBodilessEntity()` are terminal.

Example intercepting a domain error by status with retrieve:

~~~java
Book book = client.get().uri("/books/{id}", 99)
        .retrieve()
        .onStatus(status -> status.value() == 404,
                (request, response) -> {
                    throw new IllegalArgumentException("Book not found");
                })
        .body(Book.class);
~~~

This snippet assumes an existing client. In production, use exceptions/domain policies with clear HTTP status, request ID, and retry rules; never swallow status 500 and return an empty Book.

## 8. RestTemplate: Using exchange with ParameterizedTypeReference

Legacy projects often write:

~~~java
RestTemplate template = new RestTemplate();
Book book = template.getForObject(
        "https://api.example.com/books/1", Book.class);
~~~

For generics, `getForObject(url, List.class)` **does not carry `Book`**, so use `exchange`:

~~~java
ParameterizedTypeReference<List<Book>> type =
        new ParameterizedTypeReference<>() {};

ResponseEntity<List<Book>> response = template.exchange(
        "https://api.example.com/books",
        HttpMethod.GET,
        null,
        type
);

List<Book> books = response.getBody();
~~~

`RestTemplate.exchange(..., HttpMethod, HttpEntity<?>, ParameterizedTypeReference<T>)` preserves `List<Book>` when a generic-capable converter is present. There is no identical `getForObject(url, ParameterizedTypeReference)` overload; choose the right API.

When request headers are needed:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.setAccept(List.of(MediaType.APPLICATION_JSON));
HttpEntity<Void> request = new HttpEntity<>(headers);

ResponseEntity<List<Book>> response = template.exchange(
        "https://api.example.com/books",
        HttpMethod.GET,
        request,
        type
);
~~~

If there is a generic request body, `RequestEntity` or `HttpEntity<T>` and matching overloads can be used; inspect **both serialization** (request) and deserialization (response).

### 8.1. RestTemplate Is Not “Wrong”, and RestClient Is Not Automatically “Faster”

Both are synchronous HTTP clients; RestClient is the newer fluent API, while RestTemplate has a broad ecosystem and stable existing code. Changing syntax from RestTemplate to RestClient **does not eliminate blocking I/O**. Measure latency, request factories, connection pools, retry policies, and networking before claiming performance gains.

Use `WebClient` when reactive composition is truly needed, and never block the result on a Reactor event loop. `ParameterizedTypeReference` also appears in `WebClient.bodyToMono(type)`/`bodyToFlux(type)`, though its conversion implementation differs.

## 9. How Do RestClient and RestTemplate Select a Converter?

For a JSON `application/json` response and target `ApiEnvelope<List<Book>>`, the client iterates its configured converters to find one capable of reading the target type/media type. The generic Jackson converter uses the full Type to instantiate `ApiEnvelope`, `List`, and `Book`. If the Jackson dependency is missing or the converter was removed from the list, parsing will fail even with a valid TypeReference.

Conversely, if the response is `text/plain` and you call `body(String.class)`, the String converter handles it without needing Jackson.

### 9.1. How to Inspect Actually Registered Converters

~~~java
RestTemplate template = new RestTemplate();
template.getMessageConverters()
        .forEach(c ->
            System.out.println(c.getClass().getSimpleName()));
~~~

This snippet runs in a Java class with appropriate imports and Spring Web dependencies. The printed list varies by classpath and Spring version; **do not assume a fixed stdout**. When configuring RestClient via its builder, you can inspect or customize the converter list via callback:

~~~java
RestClient configured = RestClient.builder()
        .messageConverters(converters -> {
            // Intentionally inspect/modify list.
            converters.forEach(c ->
                    System.out.println(c.getClass().getName()));
        })
        .build();
~~~

**Do not blindly clear default converters.** Calling `converters.clear()` and registering only `StringHttpMessageConverter` will break JSON DTO reading/writing.

### 9.2. Converter Ordering and Media Types

Adding an overly broad custom converter (e.g., `canRead(..., */*)` for Object) ahead of Jackson can intercept Jackson and misparse bodies. Register exact media types and only the classes the converter knows how to handle, testing both serialization/deserialization and status/headers. Avoid overriding Jackson's `supportedMediaTypes` to `*/*` to “fix” an upstream sending the wrong Content-Type, as that can silently read an HTML error page as JSON and hinder diagnostics.

### 9.3. Boot Auto-Configuration

Spring Boot 3.x configures builders, ObjectMapper, and customizers based on starters. Calling **`RestClient.builder()` directly** can **bypass Boot customizations** present on Boot's pre-configured `RestClient.Builder` bean.

In Boot 3.5, pattern:

~~~java
@Configuration
class ClientConfiguration {

    @Bean
    CatalogClient catalogClient(RestClient.Builder builder) {
        RestClient rest = builder
                .baseUrl("https://api.example.com")
                .build();
        return new CatalogClient(rest);
    }
}
~~~

This is an illustrative class; `CatalogClient` is defined in the hands-on section, and the example URL must be replaced by a trusted/configured production endpoint. With multiple RestClients, configure builders cleanly without mutating a shared builder concurrently after build.

## 10. Jackson ObjectMapper vs ParameterizedTypeReference: How Do They Differ?

**Two solutions at different API layers:**

| Concept | Unit | Purpose |
| --- | --- | --- |
| `Class<Book>` | Java reflection | A single concrete class |
| `Type`/`ParameterizedType` | Java reflection | Describes `List<Book>`, nested generics |
| `ParameterizedTypeReference<T>` | Spring Core | Carries `Type` through generic Spring APIs |
| `ResolvableType` | Spring Core | Resolves/analyzes generics |
| `TypeReference<T>` | Jackson | Carries generic metadata for `ObjectMapper.readValue` |
| `JavaType` | Jackson | Jackson's type model for deserialization |
| `HttpMessageConverter` | Spring Web | Converts HTTP bytes ↔ Java objects |
| `ObjectMapper` | Jackson | JSON ↔ Java objects |

If you only have a JSON string/byte array and invoke Jackson directly:

~~~java
ObjectMapper mapper = new ObjectMapper();

List<Book> books = mapper.readValue(
        json,
        new com.fasterxml.jackson.core.type.TypeReference<List<Book>>() {});
~~~

This is a snippet assuming an existing `String json`; different namespace and use case from Spring's `ParameterizedTypeReference`. When using RestClient/RestTemplate, you normally **do not call `ObjectMapper.readValue` manually**: let the converter handle content-type, headers, and TypeToken.

If you must build a JavaType:

~~~java
JavaType type = mapper.getTypeFactory()
        .constructCollectionType(List.class, Book.class);

List<Book> books = mapper.readValue(json, type);
~~~

This is a pure Jackson example outside the request client abstraction. In large systems, maintain a consistently configured `ObjectMapper` for Java time, naming, modules, date formats, and polymorphic type restrictions; avoid creating a new Mapper per request unnecessarily.

## 11. Runnable Practice: Java 17 + Spring Boot 3.5

The exercise focuses on a **synchronous HTTP client** without needing to start a real REST server. `MockRestServiceServer` answers requests sent by `RestClient` and `RestTemplate` through a mock `ClientHttpRequestFactory`. This allows accurate testing of converters/type references without network, tokens, hostnames, or external APIs.

Use **Spring Boot 3.5.x / Spring Framework 6.2.x** and Java 17+, package `com.example.demo`.

### 11.1. Dependencies

Create a Maven project via Spring Initializr (Spring Boot 3.5.x, Java 17) selecting:
- Spring Web (for Spring Web, RestClient/RestTemplate, Jackson JSON).
- Spring Boot Starter Test (JUnit Jupiter, Spring Test/MockRestServiceServer).

In the Spring Initializr-generated `pom.xml`, the dependencies section looks like:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This is **a fragment** of `pom.xml`, not a standalone Maven file. Spring Initializr manages parent, Java version, Maven plugins, and version management. `spring-boot-starter-web` includes the ability to run a Servlet HTTP server if needed, though the tests here use a **mock outgoing HTTP client** with no socket-listening server required.

Structure:

~~~text
src/main/java/com/example/demo/
    DemoApplication.java
    Book.java
    ApiEnvelope.java
    CatalogClient.java
src/test/java/com/example/demo/
    CatalogClientTest.java
    RestTemplateGenericTest.java
~~~

### 11.2. DemoApplication.java

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

This Boot app can be started with `./mvnw spring-boot:run`. However, **unit/integration-style client tests do not need to start DemoApplication**; they instantiate RestClient and MockRestServiceServer directly to isolate converter behavior.

### 11.3. Book.java

~~~java
package com.example.demo;

public record Book(long id, String title) {}
~~~

Jackson 2.x bundled in Spring Boot 3.5 handles Java records natively via constructors/components when JSON keys match `id` and `title`.

### 11.4. ApiEnvelope.java

~~~java
package com.example.demo;

public record ApiEnvelope<T>(T data, String traceId) {}
~~~

`T` can be `Book`, `List<Book>`, or another type. The JSON field `traceId` illustrates response metadata and is **not** part of Java's generic mechanism.

### 11.5. CatalogClient.java — RestClient Using Proper Type Tokens

~~~java
package com.example.demo;

import java.util.List;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestClient;

public final class CatalogClient {

    private static final ParameterizedTypeReference<List<Book>>
            BOOK_LIST = new ParameterizedTypeReference<>() {};

    private static final ParameterizedTypeReference<
            ApiEnvelope<List<Book>>> ENVELOPE =
            new ParameterizedTypeReference<>() {};

    private final RestClient client;

    public CatalogClient(RestClient client) {
        this.client = client;
    }

    public Book findOne(long id) {
        return client.get()
                .uri("/books/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(Book.class);
    }

    public List<Book> findAll() {
        return client.get()
                .uri("/books")
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(BOOK_LIST);
    }

    public ResponseEntity<List<Book>> findAllWithMetadata() {
        return client.get()
                .uri("/books")
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .toEntity(BOOK_LIST);
    }

    public ApiEnvelope<List<Book>> findEnvelope() {
        return client.get()
                .uri("/books/envelope")
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(ENVELOPE);
    }

    public Book create(Book book) {
        return client.post()
                .uri("/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(book)
                .retrieve()
                .body(Book.class);
    }
}
~~~

Key points:

1. `BOOK_LIST` and `ENVELOPE` are **static, immutable, resolved** type references. Reused without allocating an anonymous subclass on every HTTP call.
2. `findOne` uses `Book.class` because there are no generics.
3. `findAll` uses `List<Book>` and `findEnvelope` uses nested `ApiEnvelope<List<Book>>`, avoiding `LinkedHashMap`.
4. `findAllWithMetadata` retains HTTP status/headers in ResponseEntity; can still return a null body per contract.
5. `create` must set request `Content-Type` so the converter serializes Book to JSON; `Accept` only describes the expected response.
6. Callers must define policies for null bodies, 404/500, timeouts, retries, and malformed JSON. The demo does not auto-retry because GET and POST have different idempotency.
7. **RestClient is blocking**; do not call it from a WebFlux event loop without offloading.
8. No external URLs are hardcoded in the class; baseUrl is supplied in tests so tests remain deterministic.

### 11.6. CatalogClientTest.java — MockRestServiceServer Verifying Exact Types

~~~java
package com.example.demo;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class CatalogClientTest {

    MockRestServiceServer server;
    CatalogClient catalog;

    @BeforeEach
    void setup() {
        RestClient.Builder builder = RestClient.builder()
                .baseUrl("https://catalog.test");

        server = MockRestServiceServer.bindTo(builder).build();
        catalog = new CatalogClient(builder.build());
    }

    @Test
    void singleDtoUsesClass() {
        server.expect(requestTo("https://catalog.test/books/1"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withSuccess(
                        """
                        {"id":1,"title":"Spring"}
                        """,
                        MediaType.APPLICATION_JSON));

        Book book = catalog.findOne(1);
        assertNotNull(book);
        assertEquals(1, book.id());
        assertEquals("Spring", book.title());
        server.verify();
    }

    @Test
    void genericListKeepsBookElementType() {
        server.expect(requestTo("https://catalog.test/books"))
                .andRespond(withSuccess(
                        """
                        [{"id":1,"title":"Spring"},
                         {"id":2,"title":"Jackson"}]
                        """,
                        MediaType.APPLICATION_JSON));

        List<Book> books = catalog.findAll();

        assertNotNull(books);
        assertEquals(2, books.size());
        assertEquals(Book.class, books.get(0).getClass());
        assertEquals("Jackson", books.get(1).title());
        server.verify();
    }

    @Test
    void nestedGenericEnvelopeKeepsBookType() {
        server.expect(
                requestTo("https://catalog.test/books/envelope"))
                .andRespond(withSuccess(
                        """
                        {"data":[{"id":7,"title":"Generic"}],
                         "traceId":"rid-42"}
                        """,
                        MediaType.APPLICATION_JSON));

        ApiEnvelope<List<Book>> envelope = catalog.findEnvelope();

        assertNotNull(envelope);
        assertEquals("rid-42", envelope.traceId());
        assertEquals(Book.class, envelope.data().get(0).getClass());
        assertEquals("Generic", envelope.data().get(0).title());
        server.verify();
    }

    @Test
    void responseEntityHasStatusAndTypedBody() {
        server.expect(requestTo("https://catalog.test/books"))
                .andRespond(withSuccess(
                        """
                        [{"id":1,"title":"Spring"}]
                        """,
                        MediaType.APPLICATION_JSON));

        ResponseEntity<List<Book>> response =
                catalog.findAllWithMetadata();

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals(Book.class,
                response.getBody().get(0).getClass());
        server.verify();
    }

    @Test
    void postSerializesRequestAndDeserializesResponse() {
        server.expect(requestTo("https://catalog.test/books"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(content().contentType(
                        MediaType.APPLICATION_JSON))
                .andExpect(content().json(
                        """
                        {"id":3,"title":"REST"}
                        """))
                .andRespond(withSuccess(
                        """
                        {"id":3,"title":"REST"}
                        """,
                        MediaType.APPLICATION_JSON));

        Book created = catalog.create(new Book(3, "REST"));

        assertEquals("REST", created.title());
        assertEquals(3, created.id());
        server.verify();
    }

    @Test
    void http404IsNotAnEmptyBook() {
        server.expect(requestTo("https://catalog.test/books/99"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body(
                            """
                            {"message":"not found"}
                            """));

        assertThrows(RestClientResponseException.class,
                () -> catalog.findOne(99));
        server.verify();
    }
}
~~~

**Why does this test prove the lesson?**

- Does not hit `https://catalog.test` over DNS: `MockRestServiceServer.bindTo(builder)` **attaches the mock request factory before `builder.build()`**. Building RestClient first and binding afterward would cause the test to miss the configured factory.
- The list test checks the **runtime class of elements** via `Book.class`, not just size or strings.
- The nested generic test verifies `Book` **inside** `ApiEnvelope<List<Book>>`.
- The POST test verifies both **outgoing request `Content-Type` + JSON** and incoming JSON DTO.
- The HTTP 404 test verifies status errors are not swallowed as an “empty Book”.
- `server.verify()` requires all expected mock HTTP requests to be executed.
- JUnit tests are not performance benchmarks or live end-to-end API integrations; they test client conversion code/URIs/statuses using mocks.
- Any unused imports (if flagged by an IDE) can be cleaned by a formatter; normal Java compilers do not fail on them.

### 11.7. RestTemplateGenericTest.java — Legacy API Equivalent

~~~java
package com.example.demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class RestTemplateGenericTest {

    @Test
    void exchangeWithParameterizedTypeReference() {
        RestTemplate template = new RestTemplate();
        MockRestServiceServer server =
                MockRestServiceServer.bindTo(template).build();

        server.expect(requestTo("https://catalog.test/books"))
                .andRespond(withSuccess(
                        """
                        [{"id":1,"title":"Spring"}]
                        """,
                        MediaType.APPLICATION_JSON));

        ParameterizedTypeReference<List<Book>> type =
                new ParameterizedTypeReference<>() {};

        ResponseEntity<List<Book>> result = template.exchange(
                "https://catalog.test/books",
                HttpMethod.GET,
                null,
                type);

        assertNotNull(result.getBody());
        assertEquals(Book.class,
                result.getBody().get(0).getClass());
        server.verify();
    }
}
~~~

This test shows **both** synchronous HTTP clients support reading generic types when using the right API and converters.

### 11.8. Running Tests

In the Maven project:

~~~bash
./mvnw test
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd test
~~~

If Maven Wrapper is missing but Maven is installed: `mvn test`.

**Expected result when dependencies/config match and tests run successfully**: 7 passing tests (6 `CatalogClientTest`, 1 `RestTemplateGenericTest`), with no external network calls. Adding other test classes or changing versions/dependencies may change the total test count. Never claim these tests were executed if you have not actually run them on a project.

You can start the Boot app:

~~~bash
./mvnw spring-boot:run
~~~

The app is just a Spring Boot skeleton; it **does not expose a `/books` endpoint** and makes no automatic HTTP requests. Only the tests provide responses via the mock server so the exercise remains self-contained.

## 12. Diagnosing Generic Type Errors with a Small Test

To see `List.class` lose type info:

~~~java
Object raw = new ObjectMapper().readValue(
        """
        [{"id":1,"title":"Spring"}]
        """,
        List.class);

List<?> list = (List<?>) raw;

System.out.println(list.get(0).getClass().getName());
~~~

With default Jackson 2.x and a JSON array of objects as above, stdout will be:

~~~text
java.util.LinkedHashMap
~~~

This Java snippet needs `ObjectMapper` and `List` imported; it can run inside a method in any project with Jackson. This is a **local Jackson experiment** requiring no HTTP, since the error comes from raw generic types rather than networking.

Using the proper type token:

~~~java
List<Book> typed = new ObjectMapper().readValue(
        """
        [{"id":1,"title":"Spring"}]
        """,
        new com.fasterxml.jackson.core.type.TypeReference<List<Book>>() {});
System.out.println(typed.get(0).getClass().getName());
~~~

Expected result:

~~~text
com.example.demo.Book
~~~

For RestClient/RestTemplate, use **Spring ParameterizedTypeReference** instead of Jackson TypeReference so the client passes the full `java.lang.reflect.Type` to `HttpMessageConverter`.

## 13. Generic Request Bodies: When Is a Type Token Needed?

When a **response** is `List<Book>`, a type token is essential for the deserializer to instantiate the right element objects. For a **request**, generic payloads can also matter when the converter decides serialization based on the generic type or type annotations.

Example list request body:

~~~java
List<Book> books = List.of(
        new Book(1, "Spring"),
        new Book(2, "Jackson"));

ResponseEntity<Void> response = client.post()
        .uri("/books/import")
        .contentType(MediaType.APPLICATION_JSON)
        .body(books)
        .retrieve()
        .toBodilessEntity();
~~~

Jackson can usually serialize `List<Book>` properly based on the elements' **runtime values**. However, with complex generic containers, polymorphism, empty collections, type-dependent custom serializers, or generic envelopes, specifying the generic type explicitly may be necessary rather than relying on raw runtime classes.

Spring RestClient also provides the `body(Object, ParameterizedTypeReference)` overload for request bodies in Spring 6.2. Illustrative structure:

~~~java
ParameterizedTypeReference<List<Book>> type =
        new ParameterizedTypeReference<>() {};

client.post()
        .uri("/books/import")
        .contentType(MediaType.APPLICATION_JSON)
        .body(books, type)
        .retrieve()
        .toBodilessEntity();
~~~

This snippet requires an already configured `RestClient client`. A type token does not guarantee the remote API accepts that JSON; schema/validation/status tests are still required.

## 14. Common MediaType and Converter Errors

### 14.1. Server Returns the Wrong Content-Type

Server returns:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html

<html>upstream error</html>
~~~

Caller executes:

~~~java
Book book = client.get().uri("/books/1")
        .retrieve().body(Book.class);
~~~

You will not magically get a valid Book. Spring may report no suitable converter found or another decoding error depending on pipeline/version. Safely log **status, content type, request ID, and endpoint**, and fix the upstream contract.

### 14.2. Raw List → LinkedHashMap

Symptom:

~~~text
java.lang.ClassCastException:
java.util.LinkedHashMap cannot be cast to com.example.demo.Book
~~~

Fix: use `ParameterizedTypeReference<List<Book>>` in `RestTemplate.exchange` or `RestClient.retrieve().body(type)`. Never suppress unchecked casts or loop-cast Map directly to Book.

### 14.3. JSON Does Not Match DTO

~~~json
{"identifier":1,"name":"Spring"}
~~~

While DTO expects:

~~~java
public record Book(long id, String title) {}
~~~

Align the schema, use `@JsonProperty` when needed, or update the DTO. A type reference does not rename fields. If numeric values overflow, JSON is malformed, required fields are missing, or enums are unknown, ObjectMapper/validation can still fail or assign defaults depending on config.

### 14.4. Jackson Missing from Classpath

If a project only has spring-web without a JSON converter/Jackson, `body(Book.class)` for JSON may not work as expected. With Spring Boot MVC starter, Jackson is included automatically; if managing dependencies manually, add and register the converter.

### 14.5. Generic TypeReference at the Wrong Level

An `ApiEnvelope<List<Book>>` response cannot be read properly using:

~~~java
new ParameterizedTypeReference<List<Book>>() {}
~~~

because the root JSON is an object with `data`, not an array. Use a TypeReference **matching the root schema**. Likewise, `ApiEnvelope<Book>` differs from `ApiEnvelope<List<Book>>` in the data field.

### 14.6. 204 No Content

A **204** status response has no body. `body(Book.class)` cannot “invent an empty Book”; handle null/ResponseEntity or use `toBodilessEntity()` for endpoints whose contract returns an empty body.

### 14.7. Error Responses Do Not Necessarily Use the Success DTO Converter

If the upstream returns status 400 with problem JSON, `retrieve()` by default throws `RestClientResponseException`. Do not assume `body(Book.class)` parses a Book from an error body. Use `onStatus`, `RestClientResponseException`, or proper API error deserialization.

### 14.8. 415 and 406 Are Not Always Client-Side Parser Issues

- **415 Unsupported Media Type** typically happens when the server rejects the request/body `Content-Type`.
- **406 Not Acceptable** typically happens when the server cannot produce a representation matching the request `Accept` header.
- **Client-side converter/decoding errors** happen when the client cannot read the body for the given media type/target type, even on status 200.

Distinguish **which side** failed. Do not “fix” 415 by increasing timeouts or “fix” 406 by changing `List<Book>` to `List.class`.

## 15. Configuring Custom HttpMessageConverter: When Should You and When Should You Not?

If an API uses a binary/proprietary media type, you can implement a custom converter. However, most JSON APIs should use the existing Jackson converter and tune `ObjectMapper` sensibly.

Illustrative pseudo-pattern:

~~~java
RestClient custom = RestClient.builder()
        .messageConverters(list -> {
            list.add(0, myConverter);
        })
        .build();
~~~

`myConverter` is a real instance implementing `HttpMessageConverter<T>` with accurate media-type and class matching. Never place a custom converter with `canRead(Object.class, */*)` ahead of Jackson.

If you need a custom generic converter, consider `GenericHttpMessageConverter<T>` or an appropriate base class; handle `Type` with Jackson/Gson rather than **ignoring generic element types**.

### 15.1. Configuring JSON via ObjectMapper

Illustrative Jackson example:

~~~java
ObjectMapper mapper = new ObjectMapper()
        .findAndRegisterModules();

MappingJackson2HttpMessageConverter converter =
        new MappingJackson2HttpMessageConverter(mapper);
~~~

This is a snippet in code with Jackson dependencies/imports. Constructing a brand new `ObjectMapper` arbitrarily can **lose Boot's configuration**: Java time settings, naming strategies, property inclusion, unknown-fields policies, custom serializers, and security restrictions. In Spring Boot, prefer Boot's customized `ObjectMapper` bean or `Jackson2ObjectMapperBuilder`/customizers.

If using `@JsonTypeInfo`/polymorphic deserialization, restrict trusted subtypes and avoid broad Jackson default typing on untrusted data. `ParameterizedTypeReference` is not a polymorphism security mechanism.

### 15.2. Do Not Arbitrarily Alter Converters Globally Across All Clients

Each RestClient/RestTemplate has its own message converters configuration; changing the converter list in one place does not automatically alter all other clients. Spring MVC servers use converters via request mapping adapters. Spring WebFlux uses a separate codec infrastructure. Align client/server content negotiation policies, but do not assume every instance shares the same converter list.

## 16. Synchronous HTTP Clients and Production Operations

Even with the right converter/type reference, a client can still fail due to:
- Network/remote service timeouts;
- Connection pool exhaustion, DNS/TLS/connect delays;
- Oversized payloads parsed into huge collections;
- 429/503/retry storms;
- Error bodies containing PII/credentials if logged carelessly;
- SSRF if taking unvalidated upstream URLs from users;
- Missing rate limiting/circuit breakers;
- Unbounded threads performing blocking I/O;
- Jackson/schema version mismatches between client and server.

### 16.1. Setting Appropriate Connect/Read Timeouts

Example using Spring's request factory:

~~~java
SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory();
factory.setConnectTimeout(3_000); // milliseconds
factory.setReadTimeout(5_000);

RestClient client = RestClient.builder()
        .requestFactory(factory)
        .baseUrl("https://api.example.com")
        .build();
~~~

This is a runnable Spring Web illustrative config, not proof that `SimpleClientHttpRequestFactory` is optimal for every workload. For high-concurrency production, choose Apache HttpComponents/JDK client with connection pooling per your infrastructure, and measure pending acquires, max connections, connection TTL, and TLS costs.

**Separate:**
- Connect timeout bounds connection establishment;
- Read timeout bounds waiting to read data per the HTTP client factory's semantics;
- Business deadline bounds the overall operation, often enforced at an outer layer;
- Retries should be bounded, with backoff, and used only when safe/idempotent.

### 16.2. Do Not Parse an Unbounded Response into a List

`body(new ParameterizedTypeReference<List<Book>>() {})` is great when an endpoint returns **a finite JSON array with a reasonable size limit**. But if an API returns millions of items, it still materializes the entire collection in memory. `ParameterizedTypeReference` is **not** a streaming parser.

For large datasets:
- Upstream pagination: endpoints returning bounded Page/limit/next cursor.
- NDJSON/chunked streaming: consider `RestClient.exchange` + a bounded streaming parser, or reactive `WebClient.bodyToFlux` when architecture fits.
- Files: use `Resource`/streaming output, not `body(byte[].class)` for multi-GiB files.
- Enforce max response bytes/timeouts and guard against huge JSON objects.

### 16.3. Observability

Collect metrics per endpoint:
- 2xx/4xx/5xx statuses, retry counts, and timeout reasons.
- p50/p95/p99 HTTP latency, queue wait, upstream network time.
- Payload sizes, JSON decoding time/allocations.
- Connection pool active/idle/pending counts.
- Thread counts and blocking worker saturation.
- Serialization/deserialization failures by media type/schema version.
- Trace/correlation IDs, without logging bodies, tokens, or sensitive user data.

Do not treat converter failures as simply “null body”; let metrics/error policies reflect the concrete cause.

## 17. Quick Decision Table

| HTTP Input | Java Target | Recommended Usage |
| --- | --- | --- |
| `{"id":1,"title":"Spring"}` | `Book` | `body(Book.class)` |
| `[{"id":1,...}]` | `List<Book>` | `body(new ParameterizedTypeReference<List<Book>>() {})` |
| `{"data":[...],"traceId":"..."}` | `ApiEnvelope<List<Book>>` | `body(new ParameterizedTypeReference<ApiEnvelope<List<Book>>>() {})` |
| `{"items":{"a":[...]}}` | `Map<String, List<Book>>` | `ParameterizedTypeReference<Map<String,List<Book>>>` if actual JSON shape matches |
| `hello` with `text/plain` | `String` | `body(String.class)` |
| Small binary bytes | `byte[]` | `body(byte[].class)` + hard size limit |
| No body / HTTP 204 | No DTO needed | `toBodilessEntity()` |
| HTTP status + headers + typed body | `ResponseEntity<List<Book>>` | `toEntity(ParameterizedTypeReference<List<Book>>)` |
| RestTemplate generic GET | `ResponseEntity<List<Book>>` | `exchange(..., type)` |
| Streaming response/huge payload | Stream/chunks/pagination | Avoid full `collectList`; choose bounded-memory APIs |

## 18. Mistakes to Avoid

1. **Confusing `HttpMessageConverter` with Jackson ObjectMapper.** Converters manage HTTP media types and read/write bodies; Jackson is just one JSON implementation.
2. **Confusing `Accept` with `Content-Type`.** Accept expresses desired response formats; Content-Type describes actual request/response bytes.
3. **Using `List.class` and casting to `List<Book>`.** Does not overcome Java erasure; yields `LinkedHashMap` for JSON objects.
4. **Using `new ParameterizedTypeReference<T>() {}` inside a generic method expecting it to know the caller's type.** T is unresolved; pass the type token from the caller.
5. **Using `ApiEnvelope.class` for `ApiEnvelope<List<Book>>`.** Loses the generic type of the data field.
6. **Reading a JSON response with a converter when response Content-Type is `text/html`.** Fix the contract or handling.
7. **Calling `ObjectMapper.readValue` manually after RestClient already decoded.** Avoid unnecessary double parsing.
8. **Placing a custom converter matching every media type ahead of default converters.** Can hijack requests/responses meant for the right converter.
9. **Confusing `RestClient` with reactive.** It is synchronous; `WebClient` is non-blocking reactive.
10. **Scaling connection threads indefinitely to mask slowness.** Use timeouts, bounded pools, and respect upstream capacity.
11. **Assuming ParameterizedTypeReference caps JSON array size.** It only preserves type, not item count or memory.
12. **Skipping tests for 204, 404, malformed JSON, and wrong media types.** Happy-path generic tests are necessary but insufficient for production.
13. **Assuming Boot 3.0 includes RestClient.** RestClient debuted in Spring Framework 6.1; use Boot 3.2+ or verify dependency versions.
14. **Copying WebFlux converter configs onto RestClient.** Reactive codecs and synchronous converters are separate abstractions.
15. **Passing arbitrary user URLs to RestClient.** Can cause SSRF; control domains/schemes, redirects, and trusted endpoints.
16. **Logging raw error bodies.** Upstreams can return PII/secrets; log safe metadata instead of entire payloads.

## 19. Review Questions

**1. Why does `getForObject(..., List.class)` often return `List<LinkedHashMap>`?**

Because `List.class` has no `Book` type parameter. Jackson deserializes JSON objects into Maps when no explicit element target class is available.

**2. Does `ParameterizedTypeReference` parse JSON itself?**

No. It stores a Java `Type`; an `HttpMessageConverter` supporting the target type/media type (typically Jackson) parses the bytes.

**3. What does `GenericHttpMessageConverter` add?**

It provides overloads working with `Type` in addition to `Class`, enabling inspection of generic element/field types.

**4. When is `Book.class` sufficient?**

When the response is a non-generic concrete `Book` object matching the JSON schema.

**5. How does the newer Spring 6.2 REST client retrieve `List<Book>`?**

`restClient.get().uri(...).retrieve().body(new ParameterizedTypeReference<List<Book>>() {})`.

**6. What is the equivalent in RestTemplate?**

`restTemplate.exchange(url, HttpMethod.GET, null, new ParameterizedTypeReference<List<Book>>() {})`.

**7. What is the difference between Jackson TypeReference and Spring ParameterizedTypeReference?**

Both retain generic type metadata, but belong to different API layers/libraries. Jackson TypeReference is for ObjectMapper; Spring ParameterizedTypeReference is for Spring client APIs.

**8. Can a `<T> T fetch()` method use `new ParameterizedTypeReference<T>() {}` to infer T from the call site?**

Not reliably. T is an unresolved type variable inside the method; callers must supply a Class/ParameterizedTypeReference or a resolved Type.

**9. Why does `body(List.class)` return a result while `Book b = list.get(0)` throws an error?**

Compile-time generics are erased; the runtime List actually holds `LinkedHashMap`, not Book.

**10. Does `Accept: application/json` force the server to return JSON?**

It is only a content-negotiation preference. The server may return an error or another representation; the client must check HTTP status and actual `Content-Type`.

**11. Does `RestClient.retrieve()` hit the network immediately?**

Per the Spring 6.2 reference, `retrieve()` alone does not execute the request; a terminal `body(...)`, `toEntity(...)`, or `toBodilessEntity()` call is required.

**12. Why do type tokens not replace paging or size limits?**

They describe the target type, while byte counts and item counts can still be huge. Separate pagination/streaming/caps are required.

## 20. Pre-Production Checklist

1. Clearly identify whether the HTTP client is **RestClient**, **RestTemplate**, or WebClient; configure the matching converter/codec stack.
2. Check Spring versions: RestClient from 6.1, examples use Framework 6.2/Boot 3.5.
3. Design DTOs/records to match JSON schemas, field names, nullability, date/time formats, and unknown-fields policies.
4. For generic/nested responses, always pass a resolved `ParameterizedTypeReference<T>` at the right API layer.
5. Ensure Jackson or the appropriate converter is on the classpath and in the client's converter list.
6. Set `Accept` and `Content-Type` according to the request/response contract; do not force `*/*` to mask errors.
7. Handle statuses, headers, null/204, and 4xx/5xx; define explicit exception mapping, retries, and idempotency.
8. Configure connect/read/overall timeouts and connection pool/concurrency budgets.
9. Reject arbitrary URLs or unsafe redirects causing SSRF; allowlist outbound hosts.
10. Enforce max response bytes/element counts, pagination, or bounded streaming for large payloads.
11. Never serialize secrets or log sensitive request/response bodies; implement tracing/observability with redaction.
12. Use `MockRestServiceServer` to test converters, runtime generic element classes, nested DTOs, POST JSON, status errors, and malformed media types.
13. Run integration tests against real upstreams when verifying proxies, TLS, network timeouts, and content negotiation.
14. Do not treat migrating RestTemplate → RestClient as switching from blocking to non-blocking; measure actual requirements.

## 21. References

- [Spring Framework 6.2 — REST Clients (RestClient, RestTemplate, ParameterizedTypeReference)](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html)
- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html)
- [Spring Framework 6.2 — RestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/RestClient.html)
- [Spring Framework 6.2 — RestTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/RestTemplate.html)
- [Spring Framework 6.2 — GenericHttpMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/converter/GenericHttpMessageConverter.html)
- [Spring Framework 6.2 — HttpMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/converter/HttpMessageConverter.html)
- [Spring Framework 6.2 — ParameterizedTypeReference Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/ParameterizedTypeReference.html)
- [Spring Framework 6.2 — MockRestServiceServer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html)
- [Spring Boot 3.5 — REST clients auto configuration](https://docs.spring.io/spring-boot/3.5/reference/io/rest-client.html)
- [Oracle Java — Type Erasure](https://docs.oracle.com/javase/tutorial/java/generics/erasure.html)
