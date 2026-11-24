# HttpMessageConverter and Request/Response Body Processing in Spring MVC

## Lesson Objectives

After this lesson, you will be able to:

1. Explain what **HttpMessageConverter** is, where it sits in the Spring MVC pipeline, and how it differs from `Converter`/`ConversionService`.
2. Describe how **@RequestBody** converts HTTP request bytes into Java objects and how **@ResponseBody / @RestController / ResponseEntity** convert Java values into response bodies.
3. Distinguish the **Content-Type** of a sent message from the client's **Accept** header, and understand when HTTP 400, 406, and 415 occur.
4. Identify common converters for JSON, `String`, `byte[]`, `Resource`, forms, and XML; understand the effect of classpath dependencies.
5. Write and run a Java 17+ / Spring Boot 3.3.x application with endpoints that accept JSON, return JSON, plain text, binary data, and a custom media type.
6. Customize converters, configure Jackson, and test with `MockMvc` while preserving default converters.
7. Diagnose deserialization, serialization, validation, encoding, and content negotiation errors in real applications.

**Scope:** Spring MVC on the Servlet stack of **Spring Framework 6.1 / Spring Boot 3.3.x**, Java 17+. Spring WebFlux uses **HttpMessageReader/HttpMessageWriter** and reactive codecs, so do not copy MVC `HttpMessageConverter` configuration verbatim to WebFlux.

## 1. The Problem to Solve: HTTP Transfers Bytes, Java Processes Objects

An HTTP request has a method, target, headers, and body. The body travels over the network as bytes, whereas a controller usually wants to receive a Java DTO. When returning a result, the controller produces a DTO, `String`, `byte[]`, or `Resource`, while the server must emit bytes and an appropriate `Content-Type`.

For example, a client sends:

~~~http
POST /books HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{"title":"Spring MVC","pages":220}
~~~

Yet the controller wants the parameter:

~~~java
NewBookRequest request
~~~

After processing, the controller returns:

~~~java
BookResponse response
~~~

Spring MVC needs two processes:

- **Reading (deserialization):** JSON bytes from the request body -> `NewBookRequest` object.
- **Writing (serialization):** `BookResponse` object -> JSON bytes in the response body.

**HttpMessageConverter** is Spring's standard strategy for performing both tasks. It focuses on representing *HTTP message content*; it is not responsible for business validation, database queries, user authentication, or defining routes.

## 2. Where Does HttpMessageConverter Sit in the Spring MVC Flow?

Simplified flow:

~~~text
HTTP client
  |
  v
Servlet container: Tomcat / Jetty / Undertow
  |
  v
Filters, Spring Security (if configured)
  |
  v
DispatcherServlet
  |
  v
HandlerMapping locates matching controller method
  |
  v
HandlerAdapter / argument resolvers
  |
  +--- @RequestBody ---> HttpMessageConverter.read(...)
  |                        |
  |                        v
  |                  Java request DTO
  |
  v
Controller method -> service -> Java result
  |
  v
Return value handlers
  |
  +--- @ResponseBody / ResponseEntity
  |          |
  |          v
  |   HttpMessageConverter.write(...)
  |          |
  |          v
  |      HTTP response body
  |
  v
Servlet container sends response to client
~~~

Key components:

- **RequestMappingHandlerMapping:** selects the handler method based on path, method, params, headers, and media-type conditions.
- **RequestMappingHandlerAdapter:** invokes the handler method and uses argument resolvers and return-value handlers.
- **RequestResponseBodyMethodProcessor:** handles `@RequestBody` parameters and `@ResponseBody` return values.
- **HttpEntityMethodProcessor:** handles `HttpEntity` and `ResponseEntity`, using message converters for the body when appropriate.
- **ExceptionHandlerExceptionResolver:** can also use message converters when `@ExceptionHandler` returns a response body.

These are the main roles; the actual pipeline also involves interceptors, advice, validation, and exception resolution.

### Message Conversion Does Not Run for Every Parameter

Not all incoming data goes through `HttpMessageConverter`. For example:

~~~java
@GetMapping("/books/{id}")
BookResponse get(@PathVariable long id,
                 @RequestParam(defaultValue = "10") int limit) {
    // ...
}
~~~

`id` and `limit` come from path/query parameters. Spring MVC uses appropriate binding/conversion mechanisms, **not a JSON body converter**, to produce those two values.

Similarly, `@ModelAttribute` primarily uses data binding from request parameters to an object; file uploads and forms follow dedicated Servlet/multipart workflows. Only when the framework needs to read/write an **HTTP message body** for matching method arguments or return values does `HttpMessageConverter` participate.

## 3. Contract of the HttpMessageConverter<T> Interface

In Spring Framework 6.1, the interface lives at:

~~~java
org.springframework.http.converter.HttpMessageConverter<T>
~~~

Core methods:

~~~java
boolean canRead(Class<?> clazz, MediaType mediaType);
boolean canWrite(Class<?> clazz, MediaType mediaType);

List<MediaType> getSupportedMediaTypes();

T read(Class<? extends T> clazz, HttpInputMessage inputMessage)
        throws IOException, HttpMessageNotReadableException;

void write(T value, MediaType contentType,
           HttpOutputMessage outputMessage)
        throws IOException, HttpMessageNotWritableException;
~~~

This is a signature listing for studying the API, **not a standalone compilable Java snippet**; the classes reside in `org.springframework.http` and `org.springframework.http.converter`.

Meaning:

1. **canRead:** can this converter read a given Java type from the request's media type?
2. **read:** reads bytes from `HttpInputMessage` and constructs an object. For instance, `MappingJackson2HttpMessageConverter` uses Jackson's `ObjectMapper` to deserialize JSON.
3. **canWrite:** can this converter represent the returned Java type in the selected media type?
4. **write:** serializes the object to `HttpOutputMessage`. The converter normally sets the appropriate `Content-Type` and writes data to the body.
5. **getSupportedMediaTypes:** the media types this converter advertises support for, customizable in some implementations.

**It is not based on Content-Type alone:** Spring also inspects the **Java type**. A `String` converter supporting `text/plain` likely cannot handle `BookResponse`; Jackson's JSON converter can handle `BookResponse` with `application/json` but will not automatically write arbitrary binary or custom formats.

### Input and Output Are HTTP Wrappers

- **HttpInputMessage** gives access to `HttpHeaders` and `InputStream` for reading the body.
- **HttpOutputMessage** allows setting `HttpHeaders` and writing the body via `OutputStream`.

The **AbstractHttpMessageConverter<T>** class supplies most of the common boilerplate for custom converters. For complex generic types like `List<BookResponse>`, some converters implement `GenericHttpMessageConverter` or `SmartHttpMessageConverter` to preserve `Type`/`ResolvableType` information; avoid erasing generic types by turning every parameter into `Object` or raw `List`.

## 4. Two Directions of Body Handling: @RequestBody and @ResponseBody

### @RequestBody: From Request Body to Java

~~~java
@PostMapping(path = "/books", consumes = MediaType.APPLICATION_JSON_VALUE)
public BookResponse create(@RequestBody NewBookRequest request) {
    // ...
}
~~~

Sequence:

1. `HandlerMapping` checks path, HTTP method, and `consumes` condition.
2. The resolver sees the parameter annotated with `@RequestBody`.
3. The framework inspects the actual `Content-Type`, target type `NewBookRequest`, and registered converters.
4. A matching converter reads the `InputStream` and creates the object.
5. The framework may run Bean Validation for `@Valid` or `@Validated`.
6. If reading and validation succeed, the controller method is invoked.

**`@RequestBody` defaults to `required=true`**. If a required body is missing, `400 Bad Request` can occur. Use `@RequestBody(required=false)` when an endpoint genuinely permits an absent body, and handle `null`/optional explicitly.

Do not use `@RequestBody` just to read query string data. For JSON bodies, `@RequestBody` is the standard choice; for query/path data, use `@RequestParam`/`@PathVariable`.

### @ResponseBody: From Java Value to Response Body

~~~java
@GetMapping("/books/1")
@ResponseBody
public BookResponse get() {
    // ...
}
~~~

After the controller returns `BookResponse`, the return-value handler selects a converter capable of writing `BookResponse` in the response media type and calls `write`. Java objects **do not default to `toString()` to produce JSON**. With Jackson, properties are serialized according to Jackson rules.

**`@RestController`** is semantically equivalent to combining `@Controller` and `@ResponseBody` at the class level, so methods normally write directly to the body without needing `@ResponseBody` individually.

~~~java
@RestController
class BookController {
    @GetMapping("/books/1")
    BookResponse get() {
        // ...
    }
}
~~~

Unlike a `@Controller` without `@ResponseBody`: a returned `String` in a classic MVC controller can be treated as a **view name**, not `text/plain` content. When the goal is returning text, use `@RestController` or `@ResponseBody` and consider `produces`.

### ResponseEntity Also Carries Status and Headers

~~~java
ResponseEntity.status(HttpStatus.CREATED)
        .header("X-Source", "demo")
        .body(bookResponse);
~~~

`ResponseEntity` lets you control status and headers, while the body is still typically written by a converter. You can use `ResponseEntity<Void>` when only status/headers are needed with no body; in that case there is no body object to serialize.

Do not confuse `ResponseEntity` with a converter: `ResponseEntity` is the **HTTP result wrapper**; the converter decides how the body payload inside that wrapper is represented.

## 5. Content-Type and Accept: Distinguish Before Debugging

| Header | Declared by | Meaning |
|---|---|---|
| Request `Content-Type` | Client | Media type of **the body the client is sending** |
| Request `Accept` | Client | Representations the client **wants to receive** in the response |
| Response `Content-Type` | Server | Media type of **the body the server actually returns** |
| Response `Vary` | Server/proxy | Tells caches which request headers vary the representation when applicable |

Example:

~~~http
POST /books HTTP/1.1
Content-Type: application/json
Accept: application/json

{"title":"Java","pages":120}
~~~

- `Content-Type: application/json` helps Spring pick a converter to **read the JSON request**.
- `Accept: application/json` helps Spring pick a representation the client can **receive**.
- Response `Content-Type: application/json` indicates the actual response body is JSON.

A client can send JSON and ask for `text/plain` back; the two headers are independent. Whether that combination is supported depends on mapping conditions, converters, and the endpoint's return type.

### Content-Type Applies to a Message's Body

A `GET` request usually has no body and may not need a request `Content-Type`. Do not set `Content-Type: application/json` on a `GET` just to request JSON back; use **`Accept: application/json`** to express response preference.

### Wildcards, q-values, and Charset

~~~http
Accept: application/json, text/plain;q=0.5
~~~

The client prefers `application/json` over `text/plain`. Spring performs content negotiation based on mapping conditions, return type, writable converters, and media types accepted by the client. If `Accept` is `*/*`, the client accepts any media type, though the server still needs an appropriate converter to write the response.

~~~http
Content-Type: application/json;charset=UTF-8
~~~

This is still JSON, with a charset parameter. Media types and charsets must be interpreted per HTTP and JSON rules; UTF-8 is the standard choice for JSON over the wire. Do not compare `Content-Type` strings using exact `equals("application/json")` because valid parameters may be present.

## 6. consumes, produces, and Media Type Checks at the Handler

Spring MVC supports:

~~~java
@PostMapping(
    path = "/books",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
~~~

- **consumes:** constrains the `Content-Type` of the request body accepted by the handler.
- **produces:** constrains the media type of the response the handler can create, matched against `Accept`.
- **HttpMessageConverter:** performs body reading/writing once a matching handler is selected.

Consequently:

| Request | Endpoint condition | Typical outcome |
|---|---|---|
| `POST` `Content-Type: application/json`, `Accept: application/json` | Both `consumes` and `produces` match | JSON converter reads and writes |
| `POST` `Content-Type: text/plain` | Only `consumes` JSON | `415 Unsupported Media Type` |
| `POST` `Content-Type: application/json`, `Accept: text/plain` | Only `produces` JSON | `406 Not Acceptable` |
| `POST` malformed JSON | Media type matches, parsing fails | `400 Bad Request` |
| `POST` syntactically valid JSON violating `@Valid` | Deserialized, validation fails | `400 Bad Request` |
| `GET` with `Accept: application/json` | Endpoint returns JSON | JSON writer selected if Java type is supported |

**406 and 415 differ:** 415 concerns a **request body type the server cannot accept or read**; 406 concerns a **response type the client asked for that the server cannot produce**. Both can arise either during handler selection (`consumes`/`produces`) or during converter selection.

## 7. Common HttpMessageConverters

Available implementations depend on Spring Framework, Spring Boot, classpath, and configuration.

| Converter | Typical Java types | Common media types | Notes |
|---|---|---|---|
| `MappingJackson2HttpMessageConverter` | DTO, record, `Map`, `List`, JSON object | `application/json`, `application/*+json` | Uses Jackson 2 when dependency is present |
| `StringHttpMessageConverter` | `String` | `text/plain`, matching text media types | Do not use `String` instead of a DTO when structured JSON is wanted |
| `ByteArrayHttpMessageConverter` | `byte[]` | `application/octet-stream` or matching types | Reads/writes raw bytes as-is |
| `ResourceHttpMessageConverter` | `Resource` | Resource/file data | Stream reading/writing tailored to resources |
| `FormHttpMessageConverter` | `MultiValueMap` | `application/x-www-form-urlencoded`; writes multipart | Form submits in Servlet MVC are normally bound via request parameters |
| `MappingJackson2XmlHttpMessageConverter` | DTO/POJO | `application/xml` | Depends on Jackson XML and configuration |
| `SourceHttpMessageConverter` | `javax.xml.transform.Source` | XML media types | Handles XML `Source` when applicable |
| `ProtobufHttpMessageConverter` | Protobuf message | `application/x-protobuf` | Requires Protobuf library |

Depending on the classpath, other converters can also participate (Gson, JSON-B, YAML, CBOR, XML, ...). Do not assume every format is supported just because `spring-boot-starter-web` is present.

### Jackson JSON and Java 17 Records

With Jackson auto-configured in Spring Boot 3.3, simple Java records make great DTOs:

~~~java
public record BookResponse(long id, String title, int pages) {}
~~~

A value:

~~~java
new BookResponse(7L, "Spring MVC", 220)
~~~

is normally serialized as JSON equivalent to:

~~~json
{"id":7,"title":"Spring MVC","pages":220}
~~~

Field order, whitespace, and naming strategies can change depending on Jackson configuration. API tests should assert JSON structure rather than raw strings or property order.

### A String Is Not Automatically a JSON Object

~~~java
@GetMapping(path = "/raw", produces = "application/json")
String raw() {
    return "{\"ok\":true}";
}
~~~

This example easily misleads beginners: `StringHttpMessageConverter` may be chosen to write the `String` under the matching media type, emitting the `String` as literal raw bytes rather than Jackson serializing a DTO. If the string does not contain valid JSON, clients receive an invalid body despite `Content-Type: application/json`.

When you want JSON object output, return a DTO, record, strongly typed `Map`, or `ResponseEntity<DTO>`:

~~~java
record Health(boolean ok) {}

@GetMapping(path = "/health", produces = MediaType.APPLICATION_JSON_VALUE)
Health health() {
    return new Health(true);
}
~~~

This is an illustrative snippet inside a `@RestController` with appropriate imports, not a standalone runnable Java file.

## 8. How Do Forms and Multipart Differ from @RequestBody JSON?

URL-encoded forms and multipart requests use a different processing layer:

~~~http
POST /register HTTP/1.1
Content-Type: application/x-www-form-urlencoded

email=a%40example.com&name=An
~~~

In Servlet MVC, this can be handled using `@RequestParam` or `@ModelAttribute`:

~~~java
@PostMapping(
    path = "/register",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
String register(@RequestParam String email,
                @RequestParam String name) {
    return "accepted";
}
~~~

**Do not** blindly switch it to `@RequestBody MyDto` expecting Jackson's JSON converter to read form data. The Servlet container may parse request parameters beforehand, leaving the request body stream unavailable for a converter to read as expected. Spring Framework recommends `@RequestParam` for form data on the Servlet stack.

For `multipart/form-data`:

~~~java
@PostMapping(
    path = "/upload",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
String upload(@RequestPart("file") MultipartFile file) {
    return file.getOriginalFilename();
}
~~~

This is an illustrative snippet for a controller with multipart enabled; never use the client-supplied filename directly as a storage path. `MultipartResolver`/Servlet multipart handling separates the uploaded parts; `MultipartFile` is processed by multipart infrastructure. A `@RequestPart` containing a JSON DTO can use an **`HttpMessageConverter`** to deserialize **that specific part's content** based on the part's `Content-Type`. Thus, you cannot say all multipart requests bypass converters, nor that all multipart requests go through the JSON converter.

## 9. JSON Serialization/Deserialization: Data Types and Validation

Suppose we have a DTO:

~~~java
public record CreateBookRequest(
        @NotBlank String title,
        @Min(1) int pages
) {}
~~~

With parameter:

~~~java
@Valid @RequestBody CreateBookRequest request
~~~

two steps are required:

1. Jackson reads JSON into `CreateBookRequest`. Malformed JSON or incompatible types can trigger `HttpMessageNotReadableException`.
2. Bean Validation evaluates constraints. When validation fails in normal cases, Spring MVC throws `MethodArgumentNotValidException` and responds with 400.

`@NotBlank` and `@Min` belong to Jakarta Validation; **`spring-boot-starter-validation`** must be in the project. Simply adding `@Valid` without an appropriate validation provider on the classpath does not guarantee constraints are enforced.

### Distinguishing Body-Reading Errors from Business Errors

| Case | Detecting layer | Typical behavior |
|---|---|---|
| Body is not valid JSON | Jackson / converter | 400 |
| JSON body missing when required | Resolver | 400 when `@RequestBody` is required |
| Blank `title`, `pages` equals 0 | Bean Validation after deserialization | 400 |
| Valid `title`, but duplicate product code | Business service | Needs explicit rule, e.g., 409 |
| Client sends `text/plain` to JSON endpoint | Mapping / reader | 415 |
| Client only `Accept`s XML, server only writes JSON | Mapping / writer | 406 |

Do not turn all failures into 500. When a consistent error format is required, use `@RestControllerAdvice` with `@ExceptionHandler` or controlled `ProblemDetail`. Never return stack traces or secrets in responses.

### Jackson Annotations Altering JSON Payloads

~~~java
public record UserView(
        @JsonProperty("display_name") String displayName,
        @JsonIgnore String internalToken
) {}
~~~

This is an illustrative snippet, not a standalone application. If you want responses to exclude sensitive data, **designing a separate public DTO** is better than relying solely on `@JsonIgnore` on business entities. Watch out for entities with circular references, lazy loading, secret fields, and API versioning.

## 10. Complete Spring Boot 3.3.x Example: JSON, Text, Binary, and Custom Media Type

This example brings the main flows together in a Java 17+ application you can run and test with `curl`.

### 10.1. Project Setup and Dependencies

Create a Spring Boot 3.3.x Java 17 project with dependencies in `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is the `dependencies` block to add to a **Gradle project that already declares the Spring Boot plugin, repositories, and Java toolchain**, not a complete `build.gradle`. `starter-web` brings Spring MVC with Jackson JSON; `starter-validation` provides Jakarta Bean Validation; `starter-test` supports `MockMvc`/JUnit.

### 10.2. Runnable Java File in the Project

Create **src/main/java/com/example/converters/ConverterLessonApplication.java**:

~~~java
package com.example.converters;

import java.io.IOException;
import java.math.BigDecimal;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpInputMessage;
import org.springframework.http.HttpOutputMessage;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.AbstractHttpMessageConverter;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ConverterLessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConverterLessonApplication.class, args);
    }

    public record CreateBookRequest(
            @NotBlank String title,
            @Min(1) int pages
    ) {}

    public record BookResponse(long id, String title, int pages) {}

    public record Price(BigDecimal amount) {}

    @Bean
    static HttpMessageConverter<Price> priceTextConverter() {
        return new PriceTextConverter();
    }

    @RestController
    @RequestMapping("/books")
    static class BookController {

        private final AtomicLong ids = new AtomicLong();
        private final Map<Long, BookResponse> books =
                new ConcurrentHashMap<>();

        @PostMapping(
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        ResponseEntity<BookResponse> create(
                @Valid @RequestBody CreateBookRequest request) {
            long id = ids.incrementAndGet();

            BookResponse book =
                    new BookResponse(id, request.title(), request.pages());

            books.put(id, book);

            return ResponseEntity
                    .created(URI.create("/books/" + id))
                    .body(book);
        }

        @GetMapping(
                path = "/{id}",
                produces = MediaType.APPLICATION_JSON_VALUE
        )
        ResponseEntity<BookResponse> get(@PathVariable long id) {
            return ResponseEntity.of(
                    Optional.ofNullable(books.get(id))
            );
        }
    }

    @RestController
    static class FormatController {

        @GetMapping(
                path = "/health-text",
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        String healthText() {
            return "ready";
        }

        @GetMapping(
                path = "/download-bytes",
                produces = MediaType.APPLICATION_OCTET_STREAM_VALUE
        )
        byte[] binary() {
            return new byte[] {65, 66, 67};
        }

        @PostMapping(
                path = "/price",
                consumes = "text/x-price",
                produces = "text/x-price"
        )
        Price echo(@RequestBody Price price) {
            return price;
        }

        @PostMapping(
                path = "/form",
                consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE
        )
        String form(@RequestParam String name) {
            return "received:" + name;
        }
    }

    static final class PriceTextConverter
            extends AbstractHttpMessageConverter<Price> {

        PriceTextConverter() {
            super(new MediaType(
                    "text", "x-price", StandardCharsets.UTF_8));
        }

        @Override
        protected boolean supports(Class<?> type) {
            return Price.class.isAssignableFrom(type);
        }

        @Override
        protected Price readInternal(
                Class<? extends Price> type,
                HttpInputMessage input) throws IOException {
            String raw = new String(
                    input.getBody().readAllBytes(),
                    StandardCharsets.UTF_8
            );

            try {
                return new Price(new BigDecimal(raw.trim()));
            } catch (NumberFormatException ex) {
                throw new HttpMessageNotReadableException(
                        "Price must contain a decimal number",
                        ex,
                        input
                );
            }
        }

        @Override
        protected void writeInternal(
                Price price,
                HttpOutputMessage output) throws IOException {
            output.getBody().write(
                    price.amount().toPlainString()
                            .getBytes(StandardCharsets.UTF_8)
            );
        }
    }
}
~~~

Notable points:

- `@RestController` and `@RequestMapping` define HTTP endpoints, while MVC infrastructure reads/writes bodies automatically.
- **POST /books**: `MappingJackson2HttpMessageConverter` reads JSON into `CreateBookRequest`. `@Valid` validates the input; the controller creates `BookResponse` and returns `201 Created` with a `Location` header.
- **GET /books/{id}**: returns `BookResponse` as JSON if found, or an empty 404 response when `Optional` is empty.
- **GET /health-text**: `StringHttpMessageConverter` writes the `String` `"ready"` as `text/plain`.
- **GET /download-bytes**: `ByteArrayHttpMessageConverter` writes bytes `65, 66, 67` (ASCII `ABC`) as `application/octet-stream`.
- **POST /price**: custom `PriceTextConverter` reads and writes `Price` using media type `text/x-price`; the code illustrates both `canRead`/`canWrite` via `supports()` and supported media types.
- **POST /form**: `application/x-www-form-urlencoded` data is bound by Servlet MVC into `@RequestParam`; this differs from the JSON `@RequestBody` path.
- The in-memory `Map` and `AtomicLong` are for experimentation only. Data disappears on restart; this is not a production persistence layer.

**Compile scope:** This is a complete Java source file for a Spring Boot project with the declared dependencies. Do not compile it with bare `javac` since the Spring/Jackson/Jakarta Validation classpath is required. Endpoints live in two nested static `@RestController` classes, discovered by Spring Boot component scanning when the root package is `com.example.converters`.

### 10.3. Starting and Testing JSON

Run the project from its root directory:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Send JSON on Linux/macOS:

~~~bash
curl -i -X POST http://localhost:8080/books \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"title":"Spring MVC","pages":220}'
~~~

In PowerShell you can use `curl.exe` to avoid the PowerShell alias:

~~~powershell
curl.exe -i -X POST http://localhost:8080/books -H "Content-Type: application/json" -H "Accept: application/json" --data-raw '{\"title\":\"Spring MVC\",\"pages\":220}'
~~~

**PowerShell note:** quoting/escaping behavior in Windows PowerShell 5.1 and PowerShell 7 differs when passing JSON to native binaries. If a one-liner fails to pass the body properly, save the JSON to a UTF-8 file and pass `curl.exe --data-binary "@book.json"` to avoid shell quoting issues.

A typical response for the first POST:

~~~http
HTTP/1.1 201
Location: /books/1
Content-Type: application/json

{"id":1,"title":"Spring MVC","pages":220}
~~~

Do not rely strictly on header order, JSON field order, or whitespace. `id` is `1` only if this is the first record created in the current process.

Then:

~~~bash
curl -i -H 'Accept: application/json' \
  http://localhost:8080/books/1
~~~

Normally returns status 200 and the corresponding JSON object. For an `id` not in the `Map`, the endpoint returns 404.

### 10.4. Text, Binary, Form

Text:

~~~bash
curl -i -H 'Accept: text/plain' \
  http://localhost:8080/health-text
~~~

Response body:

~~~text
ready
~~~

Binary:

~~~bash
curl -i -H 'Accept: application/octet-stream' \
  http://localhost:8080/download-bytes
~~~

The body contains **3 bytes `0x41 0x42 0x43`**, corresponding to ASCII `ABC`. Avoid `curl -i` when inspecting large binary formats as it can print unwanted characters to the terminal; use `-o file.bin` and verify hashes or byte counts instead.

Form:

~~~bash
curl -i -X POST http://localhost:8080/form \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=An'
~~~

Response body:

~~~text
received:An
~~~

### 10.5. Custom Media Type text/x-price

Send:

~~~bash
curl -i -X POST http://localhost:8080/price \
  -H 'Content-Type: text/x-price' \
  -H 'Accept: text/x-price' \
  --data-binary '12.50'
~~~

Output:

~~~http
HTTP/1.1 200
Content-Type: text/x-price;charset=UTF-8

12.50
~~~

`Content-Type` may include a charset parameter depending on the converter. The guaranteed body in this example is **12.50**: `BigDecimal` is written with `toPlainString()`, preserving the parsed input scale.

Try sending:

~~~bash
curl -i -X POST http://localhost:8080/price \
  -H 'Content-Type: text/x-price' \
  --data-binary 'not-a-number'
~~~

The converter throws `HttpMessageNotReadableException` when it cannot parse a `BigDecimal`, usually resulting in HTTP 400. Spring Boot may generate different error bodies depending on configuration and `Accept`; do not hardcode fixed error JSON strings into tests.

### 10.6. Why Does the Custom Converter Apply Only to Price?

`PriceTextConverter` extends `AbstractHttpMessageConverter<Price>`. `supports()` returns `true` only for `Price` or compatible subclasses; its supported media type is `text/x-price`. Therefore this converter will not compete to read/write `BookResponse` JSON or `String` `text/plain`.

A production custom converter also needs to account for body size limits, charset handling, input security, generic `Type` info, streaming, and exception handling. Here the converter is intentionally minimal, prioritizing clarity for a custom media type on an explicit Java type.

## 11. Testing All Four Result Categories with MockMvc

`MockMvc` lets you invoke the Spring MVC pipeline in tests without opening a real TCP listener. With `starter-test` added above, create **src/test/java/com/example/converters/ConverterLessonApplicationTests.java**:

~~~java
package com.example.converters;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ConverterLessonApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void readsJsonAndWritesCreatedJson() throws Exception {
        mvc.perform(post("/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"Spring MVC\",\"pages\":220}"))
            .andExpect(status().isCreated())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.title").value("Spring MVC"))
            .andExpect(jsonPath("$.pages").value(220));
    }

    @Test
    void rejectsUnsupportedRequestMediaType() throws Exception {
        mvc.perform(post("/books")
                .contentType(MediaType.TEXT_PLAIN)
                .content("hello"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void rejectsUnacceptableResponseType() throws Exception {
        mvc.perform(post("/books")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_PLAIN)
                .content("{\"title\":\"Spring MVC\",\"pages\":220}"))
            .andExpect(status().isNotAcceptable());
    }

    @Test
    void rejectsMalformedJson() throws Exception {
        mvc.perform(post("/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{bad-json"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void validatesAfterDeserialization() throws Exception {
        mvc.perform(post("/books")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"\",\"pages\":0}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void writesPlainText() throws Exception {
        mvc.perform(get("/health-text")
                .accept(MediaType.TEXT_PLAIN))
            .andExpect(status().isOk())
            .andExpect(content().string("ready"));
    }

    @Test
    void usesCustomPriceConverter() throws Exception {
        MediaType priceType = MediaType.parseMediaType("text/x-price");

        mvc.perform(post("/price")
                .contentType(priceType)
                .accept(priceType)
                .content("12.50"))
            .andExpect(status().isOk())
            .andExpect(content().string("12.50"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

The tests verify HTTP status, media type, and actual body. They do not depend on JSON property order; asserting via `jsonPath` avoids flakiness if Jackson writes keys in a different order.

**Key distinction:** `MockMvc` tests framework wiring and converters, but does not verify TCP, TLS, or embedded server port binding. To test a real server, use `@SpringBootTest(webEnvironment=RANDOM_PORT)` with an appropriate HTTP client.

## 12. How Spring Selects a Converter When Multiple Choices Exist

Suppose a list of converters is registered. When reading `@RequestBody`, Spring looks for a converter that can handle the parameter's Java type alongside the actual `Content-Type`; the first matching converter in configuration order can be chosen.

When writing `@ResponseBody`, Spring determines the response media type from `Accept`, `produces`, the return value's type, and writable media types. It then picks a matching converter from the list.

A generalized flow:

~~~text
Request body:
  Java target type + request Content-Type
      -> find converter with canRead(...)
      -> read(...)
      -> Java object / read error

Response body:
  Java return type + Accept + produces + supported media types
      -> determine response media type
      -> find converter with canWrite(...)
      -> write(...)
      -> HTTP body / write error
~~~

**Converter order can matter** if multiple converters match the same data type and media type. For example, an overly broad custom JSON converter placed before Jackson can alter how all JSON is serialized. Always keep custom converters' `supports()` and supported media types narrow, and test unrelated endpoints as well.

### Generic Types and List<T>

~~~java
@GetMapping("/book-list")
List<BookResponse> list() {
    // ...
}
~~~

For JSON, the Jackson converter preserves type info via generic converter/`Type` mechanisms passed through the MVC pipeline rather than seeing only raw `List.class`. This enables proper handling of complex structures, nested objects, and generic collections. Never write a converter for raw `Object` just to "support everything."

## 13. Configuration and Extension in Spring Boot

Spring Boot 3.3 auto-configures default converters based on classpath dependencies, including Jackson JSON when `starter-web` includes Jackson. In many cases **no custom converter bean is needed**.

### Option 1: Configure Jackson via Properties

Example:

~~~yaml
spring:
  jackson:
    serialization:
      indent-output: true
~~~

This property tells Jackson to pretty-print JSON. It affects JSON serialization managed by Jackson's mapper, **without** altering `ByteArrayHttpMessageConverter` or `StringHttpMessageConverter`.

When an API serves multiple clients, do not change public JSON data types solely for logging/debugging. Indentation is an example configuration that does not alter data semantics.

### Option 2: Configure ObjectMapper via Boot Customizer

Add a `@Configuration` in your Spring MVC application:

~~~java
import com.fasterxml.jackson.databind.SerializationFeature;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class JsonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer prettyJson() {
        return builder ->
                builder.featuresToEnable(
                        SerializationFeature.INDENT_OUTPUT);
    }
}
~~~

This is an **additional configuration class**, not a standalone runnable Java program. Choose either YAML or code configuration as needed; there is no need to intentionally configure the exact same setting in both places.

To handle specialized Java types, register Jackson modules, serializers, or deserializers via Boot's mapper configuration. Replace an entire converter only when truly necessary and backed by compatibility tests.

### Option 3: Add an HttpMessageConverter Bean

In the full example above:

~~~java
@Bean
static HttpMessageConverter<Price> priceTextConverter() {
    return new PriceTextConverter();
}
~~~

Spring Boot detects beans of type `HttpMessageConverter` and adds them to the converter list via MVC auto-configuration. This is useful for adding a dedicated custom type/media format.

### Option 4: WebMvcConfigurer.extendMessageConverters

When you need to adjust the constructed list, you can use:

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
class ConverterInspectionConfig implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        // Inspect or reorder converters that truly need adjustment.
        // Do not remove default converters without verifying the impact.
    }
}
~~~

This illustrates the extension point configuration. **`extendMessageConverters`** runs on the already-populated list, making it suitable for controlled adjustments.

**Note:** In plain Spring MVC, overriding `configureMessageConverters` and adding converters to the list can prevent default registrations. Spring Boot adds its own auto-configuration and `HttpMessageConverters`; prefer Boot's mechanism or `extendMessageConverters` to avoid losing JSON, `String`, `byte[]`, or other built-in converters.

### @EnableWebMvc Is a Major Decision

If you only want to add a converter, **do not** add `@EnableWebMvc` out of habit. In Spring Boot, `@EnableWebMvc` switches the application to manual MVC control and can disable many auto-configuration features. Weigh its impact on content negotiation, static resources, message converters, and other MVC settings before enabling it.

## 14. Comparing HttpMessageConverter with ConversionService and Jackson

| Component | Where it operates | Example | Goal |
|---|---|---|---|
| `HttpMessageConverter` | Reads/writes entire HTTP bodies | JSON bytes -> `BookRequest` | Body representation and media types |
| `ConversionService` / `Converter<S,T>` | Converts between Java types during binding | Query `"42"` -> `Integer 42` | Java object -> Java object |
| `PropertyEditor`/`Formatter` | Parameter binding and formatting | Query date string -> `LocalDate` | Property conversion/formatting |
| Jackson `ObjectMapper` | Library-level JSON serialization/deserialization | Java record -> JSON | Specific JSON engine |
| `RequestBodyAdvice` | Intercepts around reading the body | Inspect/modify data before or after converter | Cross-cutting logic for reading bodies |
| `ResponseBodyAdvice` | Intercepts before body is written | Wrap response in an API envelope | Cross-cutting logic for writing bodies |
| Filter/Interceptor | Before/after request handling | Tracing, auth, metrics | HTTP request pipeline mechanisms |

`MappingJackson2HttpMessageConverter` **uses Jackson**; Jackson does not replace the entire MVC converter-selection mechanism. A `Converter<String, Long>` in `ConversionService` does not read JSON streams. These concepts often share the word "converter" but solve different problems.

### RequestBodyAdvice and ResponseBodyAdvice

When cross-cutting body interception is needed, Spring MVC provides:

- `RequestBodyAdvice`: intercepts before/after reading a request body via `HttpMessageConverter`.
- `ResponseBodyAdvice`: intercepts a return object before the converter writes the body.

These are powerful mechanisms, but blindly wrapping every response can break `ResponseEntity<byte[]>`, `Resource`, `String`, `ProblemDetail`, file downloads, or streaming. Check `supports()` carefully and test each media type. Never use advice for work that belongs in services or validation.

## 15. When Does a Converter Not Participate?

Know these exceptions so you do not debug the wrong layer:

- **`@RequestParam`/`@PathVariable`:** parameter binding/conversion, not reading a raw HTTP body with a JSON converter.
- **`@ModelAttribute`:** object bound from request parameters, distinct from `@RequestBody` JSON.
- **View rendering:** Controller returns a view name and `ViewResolver` renders a template; this is not a `@ResponseBody` object serialized like REST.
- **`MultipartFile`:** file parts are handled by multipart infrastructure; a JSON DTO `@RequestPart` can still use a converter.
- **`StreamingResponseBody`:** streams data via a callback managed by Spring MVC, rather than serializing a DTO through a standard converter.
- **Responses with no body:** `204 No Content`, `HEAD` responses, or `ResponseEntity<Void>` need no body object serialization.
- **Static resources:** `ResourceHttpRequestHandler` and static resource handling follow their own mechanism.
- **WebFlux:** uses HTTP codecs/readers/writers; Jackson may still be used, but not via the MVC `HttpMessageConverter` pipeline.

If you see a return type where a converter is never invoked, first check whether the controller method uses `@ResponseBody`/`@RestController` or `ResponseEntity`, or goes through view rendering, streaming, multipart, or a dedicated handler instead.

## 16. Common Errors and How to Diagnose Them

### 400 Bad Request

Common causes:

- Unparseable JSON, mismatched field type, syntax missing quotes/commas.
- Required body is empty.
- Bean Validation failed after deserialization.
- Custom converter threw `HttpMessageNotReadableException`.

How to handle:

1. Log and inspect the actual `Content-Type`, the body in a safe test environment, and the target DTO.
2. Identify whether the failure occurred in parsing or validation.
3. Return a structured error response without exposing stack traces.
4. Write tests for malformed JSON, invalid DTOs, and missing bodies.

### 415 Unsupported Media Type

Causes:

- Client sent a `Content-Type` not matching the endpoint's `consumes`.
- No converter can read the target type from the sent media type.
- Custom converter only `supports` one type while the controller expects another.

For example, the endpoint only accepts `application/json`, yet the client sends `text/plain`. The best fix is sending the proper `Content-Type` and JSON body, or intentionally updating the endpoint contract; do not register a wildcard converter supporting every media type indiscriminately.

### 406 Not Acceptable

Causes:

- Request `Accept` is incompatible with `produces`.
- Server has no converter capable of writing the object in the requested media type.

For instance, the client sends `Accept: application/xml` while the server only supports/handles JSON. Do not blindly add XML dependencies to "fix" every 406; verify first whether the API is designed to support XML.

### 500 and Response Writing Errors

Can occur when a converter cannot serialize an object, encounters circular references, hits a Jackson getter exception, or fails mid-stream after partial output. Writing errors occurring after the response is committed cannot be replaced with a clean JSON error body. Design standalone DTOs, avoid circular references, and log with correlation IDs.

### Corrupted Non-ASCII or Diacritic Characters in Text

Check:

- Actual response charset and `Content-Type`.
- Bytes produced by the converter or custom code.
- Source file encoding and how input is read.
- Whether a proxy alters headers or compresses/transforms the body.
- Whether the client is decoding with the wrong charset.

In custom converters, explicitly specify `StandardCharsets.UTF_8`. With modern Jackson JSON, UTF-8 JSON is the standard interchange format. Never re-encode/decode a `String` that Spring has already decoded.

### String Returned, But Not Valid JSON as Expected

Common mistake: a controller returns a `String` containing JSON text with `produces=application/json`, so clients receive raw text or malformed JSON structure. Return an object/record/`Map` and let Jackson serialize it; if raw text is intended, return `text/plain`.

### Right Converter Exists, Yet Is Not Selected

Check:

1. Actual Java target/return type; was it typed as `Object`, `String`, or a generic wrapper?
2. Request `Content-Type` and response `Accept`.
3. `consumes`/`produces` on the mapping.
4. Converter list and registration order.
5. Whether `@EnableWebMvc` or a custom `WebMvcConfigurer` altered defaults.
6. Whether Jackson/XML/Gson/Protobuf dependencies are present.
7. Whether custom `supports()` and supported media types are too narrow or too broad.

## 17. Observing Which Converters Spring MVC Actually Registers

In a Spring Boot MVC app, you can inject `RequestMappingHandlerAdapter` once the context initializes and list the converters:

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter;

@Configuration(proxyBeanMethods = false)
class ConverterDiagnostics {

    @Bean
    ApplicationRunner printMessageConverters(
            RequestMappingHandlerAdapter adapter) {
        return args -> adapter.getMessageConverters().forEach(
                converter -> System.out.println(
                        converter.getClass().getSimpleName()
                )
        );
    }
}
~~~

This is an auxiliary configuration class in a **Spring MVC application**, not a standalone program. Names and ordering depend on classpath dependencies and runtime configuration, so do not assume a fixed stdout list across every app.

During debugging, you can temporarily enable helpful logging:

~~~properties
logging.level.org.springframework.web.servlet.mvc.method.annotation=DEBUG
logging.level.org.springframework.http.converter=DEBUG
~~~

Not every converter emits detailed logs from just these two packages. When deeper tracing is required, inspect real logs and use a debugger. Never leave `DEBUG`/`TRACE` logging of sensitive bodies or user data running continuously in production.

## 18. Security and API Design Around Message Conversion

### Never Serialize Persistence Entities Directly

Entities may hold password hashes, access tokens, lazy-loaded relationships, or internal metadata. Jackson may serialize more fields than the API contract intends; public DTOs strictly bound response payloads.

### Avoid Deserializing Into Overly Generic Types Unnecessarily

If a controller accepts `Object` or `Map<String,Object>` for an endpoint with a fixed schema, validation and type safety are weaker than with a constrained DTO. Choose explicit DTOs and handle unknown properties per your API policy.

### Body Size Limits and JSON Nesting Depth

`HttpMessageConverter` converts data; **it does not replace request size limits, content length limits, JSON nesting depth limits, or resource caps**. For endpoints accepting large payloads, configure appropriate limits at the proxy, server, and parser layers and assess memory risk. The example custom converter using `readAllBytes()` is intended only for small text payloads, not large uploads.

### Content-Type Is Not Proof of Safe Data

A client can declare `application/json` while sending malformed or malicious payloads. Parsers, validation, and services must still validate inputs. Even after successful deserialization, business rules such as access control, transaction state, and quantity limits must be enforced independently.

### Response Content-Type and Caching

When an API supports multiple representations (JSON, XML, text), `Vary: Accept`, `ETag`, and proper cache policies may be needed. Never set a `Content-Type` that contradicts the actual bytes returned. Clients, browsers, and caches rely on this metadata to interpret content.

## 19. Self-Assessment Exercises

**Scenario A:** `POST /books` has `consumes=application/json`. The client sends valid JSON text with `Content-Type=text/plain`. Why can it receive 415?

**Answer:** The server relies on the media type **declared in the header** alongside mapping/converter conditions; it does not sniff the body to guess whether it looks like JSON. Send `Content-Type: application/json`.

**Scenario B:** A client sends `Accept=text/plain` to an endpoint that only `produces=application/json`. The request body is valid JSON. Which error applies?

**Answer:** `406 Not Acceptable`, because the server cannot produce the representation requested by the client, even though the request body's `Content-Type` was valid.

**Scenario C:** A DTO parses JSON successfully, but `@Valid` detects a blank `title`. Did the converter fail to parse?

**Answer:** No. Deserialization succeeded; Bean Validation failed at the next step and typically returns 400.

**Scenario D:** A `GET` method returns the `String` `"hello"` in a `@Controller` without `@ResponseBody`. Is it guaranteed to return `text/plain`?

**Answer:** No. In a view-oriented MVC controller, `String` may be treated as a view name. Use `@RestController`/`@ResponseBody` when you want to return a `String` body.

**Scenario E:** An API returns `BookResponse`, and a developer wants `application/pdf` output. Is changing `produces=application/pdf` enough?

**Answer:** No. You need an actual PDF representation, an appropriate converter or streaming mechanism, and the right `Content-Type`. Adding a media type to the mapping does not automatically turn an object into PDF bytes.

**Scenario F:** Why not use `ConversionService.convert(String, BookResponse.class)` instead of Jackson to read a JSON body?

**Answer:** `ConversionService` is for Java type conversion/binding; HTTP JSON bodies require parsers and converters that support media types, streams, and matching schemas.

**Scenario G:** A custom converter with `canWrite(Object.class, */*)` is registered ahead of Jackson, and suddenly every JSON response changes format. Why?

**Answer:** The converter's support is overly broad, and registration order lets it intercept Jackson's work. Restrict `supports()` to the specific types/formats actually needed and test other endpoints.

**Scenario H:** Can `@RequestPart` be used for JSON metadata inside a multipart request?

**Answer:** Yes. Multipart infrastructure separates the parts, and Spring can apply an `HttpMessageConverter` to the JSON metadata part according to that part's `Content-Type`, while `MultipartFile` handles the file part.

## 20. Application Checklist

- [ ] Distinguish `@RequestBody`/`@ResponseBody` from `@RequestParam`/`@ModelAttribute`.
- [ ] For REST APIs, use strongly typed DTOs/records and appropriate validation constraints.
- [ ] Declare `consumes`/`produces` when the media type contract needs to be explicit.
- [ ] Send accurate `Content-Type` for request bodies; use `Accept` to request response representations.
- [ ] Know that 400 means read/validation failure, 415 means input media type mismatch, and 406 means response media type mismatch.
- [ ] Let Jackson's JSON converter serialize DTOs rather than concatenating JSON strings manually.
- [ ] When adding custom converters, keep Java types and media types narrow; preserve default converters.
- [ ] Do not enable `@EnableWebMvc` just to tweak a small conversion in Spring Boot.
- [ ] Keep form/multipart/streaming flows separate from the JSON body pipeline when designing endpoints.
- [ ] Test JSON, `String`, binary, and at least 400, 406, and 415 error cases.
- [ ] Enforce body size limits and keep sensitive info out of responses.
- [ ] Use logs/`MockMvc` to verify status codes, headers, bodies, and selected converters.

## References

- [Spring Boot 3.3 — Servlet Web Applications, HttpMessageConverters](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Framework 6.1 — HttpMessageConverter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/converter/HttpMessageConverter.html)
- [Spring Framework 6.1 — WebMvcConfigurer Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
- [Spring Framework — @RequestBody and @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)