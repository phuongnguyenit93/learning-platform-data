# HttpMessageConverter and Reading/Writing Request–Response Bodies in Spring MVC

## 1. Objectives and Scope

`HttpMessageConverter<T>` is the mechanism Spring Framework uses to **read bytes from an HTTP request body into Java data** and **write Java data to an HTTP response body**. It is the foundational component behind `@RequestBody`, `@ResponseBody`, `@RestController`, `HttpEntity`, and `ResponseEntity` in **Spring Web MVC**.

After this lesson, you will be able to:

1. Explain where reading/writing a body starts and ends within an MVC request.
2. Explain how Spring selects a converter based on Java type, `Content-Type`, `Accept`, and handler conditions.
3. Distinguish between JSON, string, byte array, form data, and binary resource converters.
4. Build a controller that accepts JSON/text/binary and produces a response with the right status, headers, and media type body.
5. Distinguish converter selection errors from deserialization, validation, and response-writing errors; determine when to create a custom converter.
6. Avoid confusion between `@RequestBody`, `@ModelAttribute`, `@RequestPart`, `@ResponseBody`, and view rendering.

The examples use **Java 17, Spring Boot 3.3.5 (Spring Framework 6.1.x)** to bootstrap a Spring MVC application. Spring Boot provides default configuration and common JSON libraries; the explained behavior belongs to Spring MVC. Newer Spring Framework versions may have different converters and configuration APIs, so the specific APIs below are tied to the 6.1 generation.

## 2. What Is an HTTP Body, and What Does a Converter Do?

Example request:

```http
POST /api/messages HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json
X-Request-Id: req-42

{"message":"Hi","copies":2}
```

- `Content-Type` describes **the representation type of the request body sent to the server**.
- `Accept` describes **the representation type of the response body that the client can receive**.
- These two headers carry **media type** information, not Java class structure.
- JSON in a request consists of encoded bytes/characters; a converter must transform it into the object declared by the controller.

If a controller method accepts `EchoInput` and returns `EchoOutput`, the typical path is:

```text
Request bytes (JSON)
        |
        v
Servlet container / HttpServletRequest
        |
        v
DispatcherServlet + HandlerMapping select controller
        |
        v
Argument resolver encounters @RequestBody EchoInput
        |
        v
HttpMessageConverter reads JSON -> EchoInput
        |
        v
(Bean Validation if @Valid is present) -> controller
        |
        v
Controller returns EchoOutput or ResponseEntity<EchoOutput>
        |
        v
Return-value handler + HttpMessageConverter write EchoOutput -> JSON bytes
        |
        v
HTTP response (status + headers + body)
```

Example successful response:

```http
HTTP/1.1 201
Content-Type: application/json
X-Converted-By: spring-mvc

{"echoed":"HiHi","utf16Units":4}
```

Spring does not automatically turn every object into JSON in all cases. Successful reading/writing depends on having a **suitable registered converter**, matching media types, and an object that can be serialized/deserialized. The HTTP examples in this lesson only show key headers; system headers may vary depending on the container and configuration.

### HttpMessageConverter Does Not Handle All HTTP Processing

`HttpMessageConverter` does not directly decide which endpoint is invoked, does not replace authorization or business logic, and does not guarantee Bean Validation by itself. Basic division of responsibilities:

| Component | Responsibility |
| --- | --- |
| `DispatcherServlet` / `HandlerMapping` | Select handler based on URL, HTTP method, `consumes`, `produces`, and other conditions |
| Argument resolver | Produce Java arguments for a method; when needed, ask a converter to read the body |
| `HttpMessageConverter` | Convert between an HTTP body and supported Java types |
| JSON mapper (e.g., Jackson) | Perform JSON serialization/deserialization details for the JSON converter |
| Bean Validation | Check constraints such as `@NotBlank`, `@Min` after binding |
| Return-value handler | Choose how to handle the return value: response body, view, async response… |
| `ResponseEntity` | Package status + headers + body for the response |

## 3. The HttpMessageConverter<T> Interface

In Spring Framework 6.1, the `org.springframework.http.converter.HttpMessageConverter<T>` interface defines the read/write contract. Representative operations are:

```java
boolean canRead(Class<?> clazz, MediaType mediaType);
boolean canWrite(Class<?> clazz, MediaType mediaType);
List<MediaType> getSupportedMediaTypes();
T read(Class<? extends T> clazz, HttpInputMessage inputMessage)
        throws IOException, HttpMessageNotReadableException;
void write(T value, MediaType contentType,
           HttpOutputMessage outputMessage)
        throws IOException, HttpMessageNotWritableException;
```

This is a **simplified API shape for explanation**, not a complete Java interface with full imports/annotations/generic overloads.

Meaning:

- `canRead`: Can the converter read content for the **target Java type** and the request's media type?
- `read`: Read bytes from `HttpInputMessage.getBody()` and create a Java value. If the content is malformed/unconvertible, the converter can throw `HttpMessageNotReadableException`.
- `canWrite`: Can the converter output the object in the desired media type?
- `write`: Serialize the object and write bytes via `HttpOutputMessage.getBody()`, while setting necessary header information.
- `getSupportedMediaTypes`: The set of media types the converter declares it supports; converters can also inspect generic types through extended interfaces.

For example, `List<EchoInput>` requires preserving generic information so Jackson knows the element type. Spring MVC supports specialized converters/interfaces such as `GenericHttpMessageConverter`, rather than inferring from `List.class` alone and guessing.

Converters are held by Spring MVC in the `RequestMappingHandlerAdapter` infrastructure and related response-handling components. On the client side, such as `RestTemplate` or `RestClient`, the concept of message converters also exists, but this lesson focuses on the MVC server side.

## 4. How Does Spring MVC Read a Request Body?

When a request matches the following mapping:

```java
@PostMapping(path = "/messages",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<?> create(@RequestBody EchoInput input) {
    // ...
}
```

Main flow:

1. Handler mapping checks the HTTP method, URL, and `consumes` constraint. `consumes="application/json"` states that the endpoint accepts a JSON body.
2. The argument resolver identifies that the `@RequestBody EchoInput` parameter requires reading the body.
3. MVC iterates over registered message converters to find one capable of reading **`EchoInput` from `application/json`**; in a Boot 3.3.5 setup with Jackson 2, that is typically `MappingJackson2HttpMessageConverter`.
4. The converter retrieves the body as bytes from the request; the JSON mapper creates `EchoInput` and converts matching fields according to Java types.
5. If `@Valid` and a suitable validator are present, Spring checks constraints; the controller only runs after parameter processing succeeds.
6. If the body is required but cannot be read, the method may not be invoked at all, and MVC turns the error into an HTTP response.

`@RequestBody` defaults to `required = true`; you can set `@RequestBody(required = false)` if business logic allows no body, and **you must handle a null value**. Do not confuse a missing request body with an empty JSON object `{}`: an empty object is syntactically valid content, though it may be missing fields or fail validation.

### @RequestBody, HttpEntity, and Other Ways to Receive Data

```java
public void json(@RequestBody EchoInput input) { /* ... */ }
public void both(HttpEntity<EchoInput> request) { /* ... */ }
public void header(@RequestHeader("X-Request-Id") String id,
                   @RequestBody EchoInput input) { /* ... */ }
```

The three methods above are **illustrative signatures** only; they need mapping annotations and must be placed inside a controller to work. `HttpEntity<EchoInput>` holds both `getBody()` and `getHeaders()`, and its body is converted by the argument resolver through a converter; there is no need to place `@RequestBody` on `HttpEntity`. If you only need a single header, `@RequestHeader` alongside `@RequestBody` is usually clearer.

It is important to distinguish:

- `@RequestParam`, `@ModelAttribute`: typically used to bind query/form parameters via `WebDataBinder`, **not** the standard JSON deserialization path of `@RequestBody`.
- `@RequestPart`: used for a part of a multipart request, which can convert a JSON part using an appropriate converter.
- `HttpServletRequest.getInputStream()`: lets you work directly with the body stream when raw bytes are needed; reading the stream yourself can leave no data for the framework to read again.
- `MultipartFile`: uses multipart handling and uploaded file storage, and should not be replaced by a huge `@RequestBody byte[]` for all use cases.

In particular, an `application/x-www-form-urlencoded` body may already have been parsed by the Servlet container when accessing request parameters. For HTML forms, you should normally use `@RequestParam` or `@ModelAttribute` rather than relying on re-reading the same body via `@RequestBody`.

## 5. How Does Spring MVC Write a Response Body?

A controller can return a Java object:

```java
@RestController
public class ProductController {
    @GetMapping(path = "/api/products/7",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public ProductDto findOne() {
        return new ProductDto(7L, "Book");
    }

    public record ProductDto(long id, String name) {}
}
```

Because `@RestController` is equivalent to `@Controller` plus `@ResponseBody` semantics on handler methods, the `ProductDto` value is serialized into the HTTP body. If an appropriate Jackson converter is registered, the corresponding response may be:

```http
HTTP/1.1 200
Content-Type: application/json

{"id":7,"name":"Book"}
```

With a plain `@Controller`, a return value of type `String` **can be interpreted as a view name to render**, depending on the signature/annotations. When you want to return a text or JSON body, use `@ResponseBody`, `@RestController`, or `ResponseEntity` appropriately.

`ResponseEntity<T>` adds status and headers alongside the body:

```java
return ResponseEntity.status(HttpStatus.CREATED)
        .header("X-Created-By", "mvc")
        .body(new ProductDto(7L, "Book"));
```

The return-value handler takes the `ProductDto` object, determines a writable media type (considering `produces`, client `Accept`, and converters), picks a converter, and then writes the bytes. `ResponseEntity` does not bypass converters: **its body still has to be converted into a sendable format**.

When returning `ResponseEntity<Void>` or status `204 No Content`, there is normally no body to serialize. Do not assume an object will still be written to the body of a status that forbids a body. With `ResponseEntity<Resource>`, MVC has a converter and supporting behavior for resources; file downloads, range requests, and streaming require reviewing the specific configuration/Resource type.

### @ResponseBody Does Not Mean "JSON by Default"

If a `String` is returned from `@RestController`, `StringHttpMessageConverter` usually handles the string as text. If an object is returned, a JSON converter can handle it when JSON matches the desired media type. When using `produces = "application/json"`, ensure the content written by the converter is actually valid JSON; do not manually concatenate a JSON-like string and slap a JSON Content-Type on it.

## 6. Common Converters

In Spring Framework 6.1, important ones include:

| Converter | Typical Java Types | Supported Content |
| --- | --- | --- |
| `MappingJackson2HttpMessageConverter` | DTO, record, `Map`, `List<Dto>` | JSON, typically `application/json` and `application/*+json`, when Jackson 2 is present |
| `StringHttpMessageConverter` | `String` | Text, typically `text/plain` and text media types |
| `ByteArrayHttpMessageConverter` | `byte[]` | Raw bytes; the converter may support `*/*` |
| `ResourceHttpMessageConverter` | `Resource` | Resource/file data |
| `FormHttpMessageConverter` | `MultiValueMap` | Reads/writes `application/x-www-form-urlencoded`; supports **writing** multipart |
| `MappingJackson2XmlHttpMessageConverter` | DTO/record if supported by mapper | XML when the Jackson XML dependency is added |
| `SourceHttpMessageConverter` | XML `Source` | Supported XML `Source`s |

The table reflects the Spring Framework 6.x/Jackson 2 ecosystem; do not carry converter names verbatim across major versions without checking version documentation. Support for XML, Protobuf, or third-party libraries depends on the classpath, configuration, and ordering priority. `FormHttpMessageConverter` is **not** the only mechanism for receiving multipart uploads: Spring MVC also has multipart resolution and argument resolvers such as `@RequestPart` / `MultipartFile`.

### Why Can String and byte[] Cause Confusion?

`StringHttpMessageConverter` and `ByteArrayHttpMessageConverter` have relatively broad media type ranges. Therefore:

- With a Java return type of `String`, the text converter may be chosen before the JSON converter depending on configuration/order; the body may be literal characters. Do not treat `"hello"` as a valid JSON string just because the response is labeled with a JSON header.
- With `byte[]`, the returned data consists of actual bytes; if it is a PDF, image, or binary, declare an appropriate `Content-Type` (e.g., `application/pdf` / `application/octet-stream`), and consider `Content-Disposition` for file downloads.
- For JSON DTOs, keeping the response type as a record/DTO lets Jackson handle character escaping, null policies, and proper JSON representation.

## 7. Content-Type, Accept, consumes, and produces

These four names are often mixed up:

| Name | Set By | Primary Meaning |
| --- | --- | --- |
| Request `Content-Type` | Client | What format the request body is being sent in |
| Request `Accept` | Client | Which response media types the client wants/allows |
| Mapping `consumes` | Server/controller | Which request body types the endpoint is matched for |
| Mapping `produces` | Server/controller | Which response media types the endpoint can produce |

Example:

```java
@PostMapping(path = "/reports",
             consumes = MediaType.APPLICATION_JSON_VALUE,
             produces = MediaType.APPLICATION_JSON_VALUE)
public ReportResponse create(@RequestBody ReportRequest request) {
    // ...
}
```

This is an illustrative method; `ReportRequest`/`ReportResponse` are hypothetical DTOs. If a client sends `Content-Type: text/plain`, the JSON mapping does not match: HTTP **415 Unsupported Media Type** is typically returned. If a client sends valid JSON but `Accept: application/xml` and the endpoint only produces JSON, the server may return **406 Not Acceptable**. If a client sends `Content-Type: application/json` but the JSON is syntactically invalid, a converter was chosen but reading fails: typically **400 Bad Request**.

Four distinct aspects:

1. **Endpoint matching:** Spring selects a method whose route and media conditions match.
2. **Reader compatibility:** the Java parameter type + request media type must be readable by a converter.
3. **Writer compatibility:** the Java return type + negotiated response media type must be writable by a converter.
4. **Valid data:** the payload must be parseable, deserializable, and satisfy required constraints.

Do not confuse `Accept` with `Content-Type`: sending JSON in does not mean the client must receive JSON back; the two directions are independent. Media type negotiation can be affected by `ContentNegotiationConfigurer` configuration, headers, registered converters, and handler mappings. In modern APIs, the `Accept` header is the typical mechanism.

Encoding issues also belong to body representation: `Content-Type: text/plain;charset=UTF-8` specifies the text charset; modern JSON typically uses UTF-8. Do not convert binary data into a `String` if exact bytes must be preserved. `String.length()` in Java counts UTF-16 code units, whereas HTTP `Content-Length` refers to **byte count**; the two values are not necessarily equal.

## 8. Complete Runnable Spring MVC Example with Java 17

The example demonstrates three request body forms (JSON/text/binary) and three response forms (JSON/text/binary). This is an executable application; no database is needed.

Structure:

```text
mvc-converters-demo/
├── pom.xml
└── src/main/java/demo/converter/
    ├── ConverterApplication.java
    └── BodyController.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mvc-converters-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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
```

**`src/main/java/demo/converter/ConverterApplication.java`**

```java
package demo.converter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConverterApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConverterApplication.class, args);
    }
}
```

**`src/main/java/demo/converter/BodyController.java`**

```java
package demo.converter;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class BodyController {

    public record EchoInput(@NotBlank String message,
                            @Min(1) int copies) {}

    public record EchoOutput(String echoed, int utf16Units) {}

    @PostMapping(path = "/messages",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<EchoOutput> createMessage(
            @Valid @RequestBody EchoInput input) {

        String echoed = input.message().repeat(input.copies());
        EchoOutput result = new EchoOutput(echoed, echoed.length());

        return ResponseEntity.status(HttpStatus.CREATED)
                .header("X-Converted-By", "spring-mvc")
                .body(result);
    }

    @PostMapping(path = "/plain",
                 consumes = MediaType.TEXT_PLAIN_VALUE,
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> readPlain(@RequestBody String text) {
        return ResponseEntity.ok("text:" + text);
    }

    @PostMapping(path = "/bytes",
                 consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Integer> readBytes(@RequestBody byte[] bytes) {
        return Map.of("byteCount", bytes.length);
    }

    @GetMapping(path = "/download",
                produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<byte[]> download() {
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"sample.bin\"")
                .body(new byte[]{65, 66, 67});
    }

    @GetMapping(path = "/health-text",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String healthText() {
        return "ready";
    }
}
```

Key takeaways for each endpoint:

- `/api/messages`: Jackson JSON converter reads the JSON request into `EchoInput`; `@Valid` checks that message is non-blank and copies is at least 1; the controller builds `EchoOutput`; the JSON converter writes the `201` response with the custom header.
- `/api/plain`: `StringHttpMessageConverter` reads and writes text. The body is plain text only; there is no JSON escaping.
- `/api/bytes`: `ByteArrayHttpMessageConverter` reads bytes without interpreting them as text; the controller returns a `Map` so Jackson writes a JSON response.
- `/api/download`: the controller creates three bytes `65,66,67`, the byte array converter writes them to the HTTP output, and `Content-Disposition` suggests a filename.
- `/api/health-text`: `@RestController` ensures the returned string is the **response body**, not interpreted as a view template name.

Run from the directory containing `pom.xml`, with JDK 17+ and Maven installed:

```bash
mvn spring-boot:run
```

### 8.1. JSON In, JSON Out

```bash
curl -i -X POST http://localhost:8080/api/messages \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"message":"Hi","copies":2}'
```

Expected status, headers, and body:

```http
HTTP/1.1 201
Content-Type: application/json
X-Converted-By: spring-mvc

{"echoed":"HiHi","utf16Units":4}
```

The value `4` here is `"HiHi".length()`, not a universal representation of length for all Unicode strings. The JSON property order here is a typical representation; client tests should compare fields rather than relying on key order.

### 8.2. Text In, Text Out

```bash
curl -s -X POST http://localhost:8080/api/plain \
  -H 'Content-Type: text/plain' \
  -H 'Accept: text/plain' \
  --data-binary 'Hello MVC'
```

Exact response body:

```text
text:Hello MVC
```

`--data-binary` sends the exact text data for the example. If you need to send international characters, ensure UTF-8 is consistent across the client, headers, and converter.

### 8.3. Bytes In, JSON Out

```bash
curl -s -X POST http://localhost:8080/api/bytes \
  -H 'Content-Type: application/octet-stream' \
  -H 'Accept: application/json' \
  --data-binary 'ABC'
```

Response body:

```json
{"byteCount":3}
```

These are the three ASCII bytes `A=65`, `B=66`, and `C=67`. For large uploads, you should not always read the entire body into a `byte[]`; consider payload limits, multipart handling, or dedicated streaming.

### 8.4. Bytes Out, File Download

```bash
curl -s -D headers.txt \
  -o sample.bin \
  http://localhost:8080/api/download
```

The file `sample.bin` contains three bytes `41 42 43` in hex, which is `ABC` in ASCII. Important headers:

```http
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="sample.bin"
```

`-D` only saves response headers to `headers.txt`; `-o` saves the response body to `sample.bin`. Do not use raw terminal output to inspect arbitrary binary data, because bytes may not be readable text.

### 8.5. Data or Media Type Errors

Sending an invalid constraint:

```bash
curl -i -X POST http://localhost:8080/api/messages \
  -H 'Content-Type: application/json' \
  -d '{"message":"","copies":0}'
```

Expected response status is `400 Bad Request` because `@NotBlank` and `@Min(1)` fail. The default error JSON shape can vary depending on Spring Boot configuration and exception handling; do not treat an assumed error JSON body as a contract.

Sending the wrong request media type:

```bash
curl -i -X POST http://localhost:8080/api/messages \
  -H 'Content-Type: text/plain' \
  --data-binary '{"message":"Hi","copies":2}'
```

Typically returns `415 Unsupported Media Type` because the `consumes` mapping only accepts JSON, even though the text content looks like JSON. The server uses the **actual header**, rather than inspecting `{` to guess the format.

Sending a non-matching Accept:

```bash
curl -i -X POST http://localhost:8080/api/messages \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/xml' \
  -d '{"message":"Hi","copies":2}'
```

Typically returns `406 Not Acceptable` because the `produces` mapping only declares JSON. This command illustrates an **output** format not accepted by the client.

### 8.6. Trying with PowerShell

If your shell is PowerShell, you can send a JSON request without relying on Bash line-continuation syntax:

```powershell
Invoke-RestMethod -Method Post -Uri 'http://localhost:8080/api/messages' -ContentType 'application/json' -Body '{"message":"Hi","copies":2}'
```

PowerShell typically deserializes JSON into an object when using `Invoke-RestMethod`, so terminal output is not necessarily the verbatim JSON bytes; use `Invoke-WebRequest` or another HTTP tool if you want to inspect status/headers/raw representation.

## 9. Customizing the Message Converters List

In Spring MVC 6.1, `WebMvcConfigurer` provides two commonly used extension points:

```java
@Override
public void configureMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    // Declare the list intentionally.
}

@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    // Adjust the already-configured list.
}
```

These two methods are **illustrative snippets**, not a full class with imports. In Spring MVC configured via `WebMvcConfigurer`, using `configureMessageConverters` to declare custom converters can **replace the default converter setup**; using `extendMessageConverters` to add to the existing list is generally less risky. With Spring Boot, there is also auto-detection of `HttpMessageConverter` beans; you must check your version's behavior and avoid registering duplicate converters.

Do not alter converter order arbitrarily. If an overly broad converter is placed before the JSON converter and always reports `canRead`/`canWrite` as true for all types, it can be selected by mistake and break normal endpoints.

### Example Converter for text/x-compact

Suppose the application needs a custom media type `text/x-compact` to exchange a single line of text. The sample converter below is split into three snippets; they can be added to **the application in Section 8** in the same `demo.converter` package. This is an optional extension; the application in Section 8 runs independently without these files.

**`CompactLine.java`**

```java
package demo.converter;

public record CompactLine(String value) {}
```

**`CompactLineConverter.java`**

```java
package demo.converter;

import org.springframework.http.HttpInputMessage;
import org.springframework.http.HttpOutputMessage;
import org.springframework.http.MediaType;
import org.springframework.http.converter.AbstractHttpMessageConverter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

public final class CompactLineConverter
        extends AbstractHttpMessageConverter<CompactLine> {

    public CompactLineConverter() {
        super(new MediaType(
                "text", "x-compact", StandardCharsets.UTF_8));
    }

    @Override
    protected boolean supports(Class<?> clazz) {
        return CompactLine.class == clazz;
    }

    @Override
    protected CompactLine readInternal(
            Class<? extends CompactLine> clazz,
            HttpInputMessage input) throws IOException {
        byte[] raw = input.getBody().readAllBytes();
        return new CompactLine(
                new String(raw, StandardCharsets.UTF_8));
    }

    @Override
    protected void writeInternal(
            CompactLine line, HttpOutputMessage output)
            throws IOException {
        output.getBody().write(
                line.value().getBytes(StandardCharsets.UTF_8));
    }
}
```

**`CompactConverterConfiguration.java`**

```java
package demo.converter;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.util.List;

@Configuration
public class CompactConverterConfiguration implements WebMvcConfigurer {

    @Override
    public void extendMessageConverters(
            List<HttpMessageConverter<?>> converters) {
        converters.add(0, new CompactLineConverter());
    }
}
```

**Add the following two methods to `BodyController`**; `org.springframework.web.bind.annotation.GetMapping` is needed (the main file already imports `GetMapping`) along with the `CompactLine` record in the same package:

```java
@PostMapping(path = "/compact",
             consumes = "text/x-compact",
             produces = "text/x-compact")
public CompactLine compact(@RequestBody CompactLine input) {
    return new CompactLine(input.value().toUpperCase(
            java.util.Locale.ROOT));
}

@GetMapping(path = "/compact",
            produces = "text/x-compact")
public CompactLine compactExample() {
    return new CompactLine("hello");
}
```

The two methods are **a snippet to insert into the controller class**, not a standalone Java file. Client:

```bash
curl -s -X POST http://localhost:8080/api/compact \
  -H 'Content-Type: text/x-compact' \
  -H 'Accept: text/x-compact' \
  --data-binary 'hello'
```

Response body:

```text
HELLO
```

Notes on custom converters:

- `supports` only allows `CompactLine`; `new MediaType(...)` narrows the media type. A narrow design prevents contention with default converters.
- `readInternal` reads bytes and decodes UTF-8; `writeInternal` encodes the value as UTF-8. This is a demo converter and **does not yet handle structural validation, length, forbidden characters, or request size limits**.
- `readAllBytes()` loads the entire body into RAM: only use it when requests are already size-limited. Large streams require a different design.
- `extendMessageConverters` preserves the default list; inserting the converter at index 0 in the example ensures the custom media type is handled before broad converters. In real products, review conflicts with already-registered media types.
- If the format is simply JSON with different field naming, **configuring the Jackson ObjectMapper/serializer** is usually more appropriate than writing a converter from scratch.
- A converter is only responsible for the body. The endpoint still needs proper `consumes`/`produces` mappings, validation, and error handling as usual.

## 10. Where Do RequestBodyAdvice and ResponseBodyAdvice Fit?

Spring MVC also provides extension points to intercept around the conversion process:

- `RequestBodyAdvice` can intercept when a request body is about to be read or has just been converted into an object for parameters such as `@RequestBody`/`HttpEntity`, depending on the phase and method the advice implements.
- `ResponseBodyAdvice` is invoked when preparing to write a return value, after a converter has been selected and before the body is written to the response.

Advices are typically declared via `@ControllerAdvice` and have `supports(...)` to select an appropriate scope. They are useful when there is a uniform requirement for an envelope, auditing metadata, or representation adjustment. However:

- You should not use advice to secretly alter a JSON contract without the client knowing.
- If `ResponseBodyAdvice` replaces the object with a type that the selected converter **cannot write**, the request may fail during output. Be especially careful with `String` responses.
- Do not use advice to re-read a request body if the request stream has already been consumed; avoid logging sensitive content.
- Authentication, authorization, request size, and business validation belong in their own places; advice must not be treated as a substitute.

## 11. Common Errors and How to Analyze Them

| Symptom | Typical Stage | Cause to Check |
| --- | --- | --- |
| `415 Unsupported Media Type` | Mapping/selecting request reader | `Content-Type` header does not match `consumes` or no matching converter exists |
| `406 Not Acceptable` | Negotiation/selecting response writer | `Accept` does not match `produces` or no converter can write it |
| `400 Bad Request` | Request conversion or validation | Malformed JSON, missing body, wrong field type, constraint failure |
| `HttpMessageNotReadableException` | Converter reading request | Deserialization failed, data does not follow required structure |
| `MethodArgumentNotValidException` | Validation after creating argument | Object violates Bean Validation when not handled via `BindingResult` |
| `HttpMessageNotWritableException` | Converter writing response | Serialization failed, mapper cannot write object |
| Empty or unexpected response | Return-value processing | Method returns view name instead of body, status `204`, `null` body, different converter selected |
| Garbled Unicode characters | Reading/writing text | Charset mismatch between client and server |
| Corrupted file | Binary representation | Converting bytes to String, wrong media type, or incorrect stream handling |

Some HTTP statuses are **common outcomes**, not absolute guarantees across all configurations. For example, a serialization failure may result in a server error, though an exception handler/custom response can change the status. For accurate diagnosis, record the **request method, URL, Content-Type, Accept, declared DTO return type, mapping consumes/produces, converter list, exception class, and relevant stack trace**. Do not log sensitive raw payloads or secrets.

Short inspection workflow:

1. Use `curl -i` or an equivalent tool to inspect **request/response headers and status**.
2. Check routing and `consumes`/`produces` first.
3. Check the converter for the parameter/return type; remember ordering.
4. Check JSON/form/charset and validation after confirming the converter.
5. Inspect the root cause exception if any, before adding custom advice or converters.
6. When changing configuration, re-test each existing media type to catch unintended side effects.

### Some Classic Mistakes

**Mistake: confusing String with a JSON DTO.**

```java
@GetMapping(produces = "application/json")
@ResponseBody
public String value() {
    return "hello"; // Do not assume the converter will produce a valid JSON string.
}
```

This is an illustrative method. If you want properly formatted JSON, return a DTO/record such as `new MessageResponse("hello")` for the mapper to serialize, or use an explicit representation once you understand the chosen converter. A valid JSON string requires quotes and escaping per the JSON standard; plain text is not automatically JSON.

**Mistake: reading the request stream twice.**

```java
public void handle(@RequestBody byte[] bytes,
                   HttpServletRequest request) {
    // Do not expect request.getInputStream() to still contain the original body.
}
```

This is an illustrative signature only. A request body is normally a single-use stream. A filter that reads the stream earlier can also cause the controller to see an empty body. `ContentCachingRequestWrapper` only caches data **already read through the wrapper**, and does not magically allow arbitrary re-reads of the body. If you need to preserve raw body bytes for signature verification, design the filter/wrapper and size limits carefully.

**Mistake: adding a wildcard converter.** If a custom converter supports `Object.class` and `*/*`, it can steal handling from Jackson or String converters, altering the output of unrelated endpoints. Restrict the class and media type strictly to the new format.

**Mistake: treating message conversion as authentication or schema security.** Deserializing JSON into an entity with sensitive properties can lead to over-posting; always use separate input DTOs, proper validation, and only map allowed fields into the domain model. Never assume the converter protects user data.

## 12. Rules for Choosing a Solution

| Scenario | Usually Appropriate Solution |
| --- | --- |
| Client sends JSON and Java DTO is needed | `@RequestBody` + JSON converter + validation |
| Client sends a literal string | `@RequestBody String` and text media type |
| Client sends moderately sized raw binary | `@RequestBody byte[]`; mind size limits |
| Client sends HTML form | `@RequestParam` / `@ModelAttribute` |
| Client sends multipart file/part | `MultipartFile` / `@RequestPart` and multipart resolver |
| Controller returns JSON data | Return DTO/record via `@RestController` or `ResponseEntity<T>` |
| Return body with specific status/headers | `ResponseEntity<T>` |
| File download | `ResponseEntity<Resource>` or `byte[]` with proper media type and headers |
| Add a custom wire protocol format | Create a narrow `HttpMessageConverter<T>`, register in proper order |
| Only change JSON serialization | Customize Jackson instead of writing a converter from scratch |

Note that converters and `WebDataBinder` type conversion are **two separate areas**. For example, binding form field `age=20` to `int` via the binding infrastructure differs from converting JSON `{"age":20}` into a record via Jackson. Both can use Bean Validation, but they differ in how data enters the object.

## 13. Self-Check Questions and Experiments

1. A client sends `Content-Type: text/plain` to an endpoint with `consumes="application/json"`. What does Spring check before Jackson is called?
2. If a `@RestController` returns a `String`, why shouldn't you automatically conclude the response body is JSON?
3. How do the two directions `canRead` and `canWrite` differ? Can a converter support only one direction?
4. When a client sets `Accept: application/xml`, the server only has a JSON writer, and the endpoint has `produces="application/json"`, why is `406` typically returned?
5. Why can't `@Valid` replace deserialization? Why doesn't successful deserialization guarantee valid data?
6. Why can `ByteArrayHttpMessageConverter` be more suitable than `StringHttpMessageConverter` for PDF/ZIP content?
7. In Spring MVC 6.1, when should you choose `extendMessageConverters` instead of `configureMessageConverters`?
8. Why shouldn't a new `HttpMessageConverter` declare `supports(Object.class)` and `*/*` too broadly?
9. If returning `ResponseEntity<Void>` with status `204`, does Spring need to call a writer to serialize a JSON DTO?
10. What happens if a new converter is placed at the front of the list and reports it can read all Java types regardless of media type?

**Hints:** (1) Mapping `consumes`/request media type. (2) The String converter usually writes text. (3) One direction parses bytes into Java, the other serializes Java to bytes; capability depends on the converter. (4) No representation acceptable to the client. (5) The converter creates the object, the validator checks constraints. (6) Exact bytes must be preserved. (7) To preserve the default converter list and add to it. (8) To avoid unintentionally hijacking handling. (9) There is no body to serialize. (10) The wrong converter can be selected and break existing responses/requests.

## 14. Official Documentation

- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html)
- [Spring Framework 6.2 — Configuring Message Converters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html)
- [Spring Framework — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html)
- [Spring Framework — ResponseEntity](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responseentity.html)
- [Spring Framework 6.1 — HttpMessageConverter API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/converter/HttpMessageConverter.html)
- [Spring Framework 6.1 — MappingJackson2HttpMessageConverter API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/http/converter/json/MappingJackson2HttpMessageConverter.html)
- [Spring Framework 6.1 — WebMvcConfigurer API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)

The references include both 6.x versions and current pages for conceptual lookup, while the code examples use APIs/configuration styles compatible with **Spring Framework 6.1 / Spring Boot 3.3.5**.