# Validating @RequestBody and @RequestPart After Deserialization in Spring MVC

## 1. The problem: HTTP data becomes an object before it can be validated

A Spring MVC API can receive JSON directly using `@RequestBody` or receive a **JSON part inside a multipart request** using `@RequestPart`. Both ways of receiving input have different HTTP structures, yet share one very important principle:

> **Spring must read the data, choose a converter, and deserialize it into a Java object before Bean Validation can check the constraints on that object.**

For example, an order creation endpoint:

```java
@PostMapping("/orders")
public void create(@Valid @RequestBody OrderRequest request) {
    // Called only after JSON has been parsed and validation has completed.
}
```

And an endpoint uploading a document with metadata:

```java
@PostMapping("/documents")
public void upload(
        @Valid @RequestPart("metadata") DocumentMetadata metadata,
        @RequestPart("attachment") MultipartFile attachment) {
    // JSON metadata has been converted to a Java object and validated.
}
```

The two snippets above are **illustrative controller methods**, not a complete program yet. The learning goal here is the timing of validation and the error-handling path, not just memorizing annotation syntax.

**Scope:** Spring Framework 6.1–6.2, Spring Boot 3.x, Java 17+, Servlet Spring MVC with Jakarta Validation (package `jakarta.validation`). Spring WebFlux responses/exceptions differ from what this lesson describes.

Outcomes to distinguish:

- **Malformed** JSON → cannot create the object yet, Bean Validation has not run; typically `HttpMessageNotReadableException` and HTTP 400.
- **Syntactically valid JSON that violates constraints** → the object was created, `@Valid`/`@Validated` runs; typically `MethodArgumentNotValidException` and HTTP 400.
- Multipart **missing a required part** → the resolver has no input to create the argument; typically `MissingServletRequestPartException` and HTTP 400.
- A JSON part with a **Content-Type lacking a matching converter** → may produce `HttpMediaTypeNotSupportedException` and HTTP 415.
- Multipart metadata deserialized successfully but **failing constraints** → `MethodArgumentNotValidException` and HTTP 400, similar to `@RequestBody`.
- A controller with **direct constraints on method parameters** requiring method validation (Spring MVC 6.1+) → validation may go through `HandlerMethodValidationException` instead of the per-argument validation path.

## 2. Two data paths: @RequestBody and @RequestPart

### 2.1. Plain JSON body with @RequestBody

Request:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{
  "customer": "Lan",
  "quantity": 2,
  "address": {
    "city": "Hue"
  }
}
```

Flow:

```text
HTTP application/json
    |
    v
@RequestBody argument resolver
    |
    v
HttpMessageConverter (typically MappingJackson2HttpMessageConverter)
    |
    v
Java Object: OrderRequest(customer="Lan", quantity=2, ...)
    |
    v
@Valid / @Validated -> Jakarta Validation provider
    |
    +-- Has violations -> BindingResult/MethodArgumentNotValidException
    |
    +-- No violations -> controller is invoked
```

`@RequestBody` tells Spring: **read the HTTP request body and convert it into the argument type**. You should not use `@RequestBody` for normal HTML forms if you want to leverage `@ModelAttribute` data binding, because the Servlet API's reading of form parameters may leave the body unavailable for the converter to read again.

### 2.2. Multipart with @RequestPart

When uploading a file with metadata, the HTTP request is no longer a single JSON object; it consists of multiple parts with their own names and media types:

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=BOUNDARY

--BOUNDARY
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Minutes","revision":1}
--BOUNDARY
Content-Disposition: form-data; name="attachment"; filename="note.txt"
Content-Type: text/plain

Hello
--BOUNDARY--
```

Flow:

```text
HTTP multipart/form-data
    |
    v
MultipartResolver / servlet multipart parsing
    |
    +-- Part "metadata" (Content-Type: application/json)
    |        |
    |        v
    |   @RequestPart("metadata")
    |        |
    |        v
    |   HttpMessageConverter -> DocumentMetadata
    |        |
    |        v
    |   @Valid -> Jakarta Validation
    |
    +-- Part "attachment" (file bytes)
             |
             v
       @RequestPart("attachment") MultipartFile
             |
             v
       File metadata/stream; content is not automatically validated
```

**Key point:** `@RequestPart` can use `HttpMessageConverter` to read each part like a small message body. Therefore, for JSON metadata, both `@RequestBody` and `@RequestPart` go through a deserialize step followed by validation. By contrast, `MultipartFile` is a file upload abstraction; `@Valid` on metadata **does not validate** the attachment's filename, actual format, size, or malicious content.

### 2.3. @RequestParam, @RequestPart, and @RequestBody are not arbitrarily interchangeable

| Need | Choose | Why |
| --- | --- | --- |
| Receive a JSON object as the entire body | `@RequestBody OrderRequest` | Converter reads the request body |
| Receive JSON metadata inside multipart | `@RequestPart("metadata") DocumentMetadata` | Converter reads the JSON **part** and creates the DTO |
| Receive a simple text form value in multipart | `@RequestParam String title` | Parameter conversion suffices; no JSON converter needed |
| Receive a file in multipart | `@RequestPart MultipartFile` or `@RequestParam MultipartFile` | Spring provides dedicated file support |
| Receive a form with multiple regular properties | `@ModelAttribute` | Form DataBinder/constructor/property binding |
| Receive the entire multipart request via `@RequestBody` | Usually **do not** choose | Multipart already has a parts structure and dedicated resolvers |

If the client sends metadata as a **plain text string without a JSON media type**, `@RequestPart DocumentMetadata` will not automatically treat it as JSON in all configurations. Always send Content-Type `application/json` for the metadata part rather than relying on the content looking like JSON.

## 3. Two separate phases: conversion and validation

### 3.1. Data conversion step

Spring selects an appropriate `HttpMessageConverter` based on the **target Java type** and the **Content-Type**. In a Spring Boot Web project with Jackson, JSON is usually read by `MappingJackson2HttpMessageConverter`.

Example DTO:

```java
public record OrderRequest(String customer, Integer quantity) {}
```

Request:

```json
{
  "customer": "Lan",
  "quantity": 2
}
```

Jackson can instantiate the record `new OrderRequest("Lan", 2)`. This is **only deserialization**; it does not imply the business rule "quantity must be positive" has been checked.

If the JSON is malformed:

```text
{"customer":"Lan","quantity":
```

the converter has no valid `OrderRequest` to hand over. The typical handling path is `HttpMessageNotReadableException`, not a `@Positive` violation. If the JSON is syntactically valid but passes an incompatible type (for example, an object instead of an integer), the converter can also fail before Bean Validation; exact behavior depends on Jackson configuration and the DTO types.

### 3.2. Bean Validation step

Only after the argument has been created and the handler argument resolver decides to apply validation does Spring invoke the validator to check annotations:

```java
public record OrderRequest(
        @NotBlank String customer,
        @NotNull @Positive Integer quantity
) {}
```

- `@NotBlank`: `customer` must not be null, empty, or whitespace-only.
- `@NotNull`: `quantity` must have a non-null value.
- `@Positive`: the number must be positive; `@Positive` itself treats null as valid per its contract, so `@NotNull` is needed to forbid a missing field.
- `@Valid` placed on the **controller parameter** tells Spring to validate the DTO; putting constraints only on the record while omitting `@Valid`/`@Validated` at the boundary does not mean Spring will automatically run all constraints.
- When the object is valid, the controller is invoked; when invalid, it is normally rejected before entering the controller body, unless `BindingResult` is used or the method validation path handles it differently.

### 3.3. Validation can cascade into nested objects

```java
public record Address(
        @NotBlank String city
) {}

public record OrderRequest(
        @NotBlank String customer,
        @NotNull @Positive Integer quantity,
        @NotNull @Valid Address address
) {}
```

`@NotNull` checks that `address` is present, and `@Valid` requests **cascading** into `Address` to check `city`. If only `@NotNull Address address` is present, an `Address` object can exist with an empty `city` without being checked.

Likewise, do not think `@Valid` forbids null by itself: `@Valid` triggers cascading when there is an object to inspect, whereas the non-null constraint is `@NotNull`'s job.

## 4. When does Spring MVC automatically validate arguments?

Spring MVC supports Jakarta Validation via `@Valid` or Spring's `@Validated`, but you need to understand the conditions under which they apply.

### 4.1. @Valid @RequestBody

```java
@PostMapping("/orders")
public ResponseEntity<Void> create(
        @Valid @RequestBody OrderRequest request) {
    // ...
}
```

With a **regular command object** and no overriding method validation mechanism, Spring uses argument validation after deserialization. On violation, `MethodArgumentNotValidException` is thrown by default; if `BindingResult`/`Errors` is placed immediately after the argument, the controller can receive the result and handle it itself.

### 4.2. @Valid @RequestPart

```java
@PostMapping(
        path = "/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public ResponseEntity<Void> upload(
        @Valid @RequestPart("metadata") DocumentMetadata metadata,
        @RequestPart("attachment") MultipartFile attachment) {
    // ...
}
```

If the metadata part has an appropriate JSON Content-Type, the converter constructs `DocumentMetadata` and the validator checks its constraints. If metadata is invalid, the **same `MethodArgumentNotValidException`** as with `@RequestBody` can occur in the regular argument validation path.

`@RequestPart("attachment")` requires this part to be present by default; however, "present" is different from "non-empty file content", "safe file type", or "valid filename". Those conditions require dedicated validation at the upload/service layer.

### 4.3. @Validated selects validation groups

Jakarta's `@Valid` takes no group parameters. When a DTO declares constraints belonging to Create/Update groups, Spring's `@Validated` can be used:

```java
public interface Create {}

public record OrderRequest(
        @NotBlank(groups = Create.class) String customer
) {}

@PostMapping("/orders")
public void create(
        @Validated(Create.class) @RequestBody OrderRequest request) {
    // ...
}
```

These are illustrative snippets; marker types and endpoints must be placed in proper files/packages. Selecting `Create` does not automatically include the `Default` group unless appropriate group inheritance/sequencing is configured. Do not put `@Validated` at the **controller class** level merely to perform argument validation; since Spring MVC 6.1, type-level annotation can activate a different AOP method validation path, which is unnecessary for simple argument examples.

### 4.4. When @Valid is not enough to trigger method validation

Spring MVC 6.1+ distinguishes:

1. **Per-argument validation** for `@ModelAttribute`, `@RequestBody`, and `@RequestPart` command objects annotated with `@Valid`/`@Validated`.
2. **Method validation** when there is a direct constraint on a parameter or return value, such as `@Min`, `@NotBlank`, or `@NotNull` placed on a handler method parameter; this mechanism also checks nested constraints via `@Valid` when applicable.

Therefore, a controller like the following can use **`HandlerMethodValidationException`** instead of `MethodArgumentNotValidException` when the direct parameter `page` is invalid:

```java
@GetMapping("/search")
public String search(@RequestParam @Min(1) int page) {
    return "page=" + page;
}
```

`@Valid` is **not a constraint annotation** and by itself does not force the entire handler to use method validation; `@Min`, however, is a constraint. Do not infer from a controller having `@Valid` that every validation error will be `HandlerMethodValidationException`; the path depends on the **signature structure**.

## 5. Hands-on Spring Boot 3.3 project, Java 17+

We implement two testable endpoints:

- `POST /api/orders`, `application/json`, `@Valid @RequestBody OrderRequest`.
- `POST /api/documents`, `multipart/form-data`, `@Valid @RequestPart("metadata") DocumentMetadata` alongside file `@RequestPart("attachment") MultipartFile`.

Goal: observe valid requests (201), JSON object/metadata violating constraints (400), malformed JSON (400), missing multipart part (400), and JSON part with wrong media type (415 in the sample setup).

### 5.1. Gradle configuration

File `settings.gradle`:

```groovy
rootProject.name = 'request-validation-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

- `spring-boot-starter-web` includes Spring MVC and standard Jackson JSON support.
- `spring-boot-starter-validation` brings in the Jakarta Validation API and provider (typically Hibernate Validator); Jackson alone will **not** automatically trigger `@NotBlank`/`@Positive` constraints.
- In a typical Spring Boot Servlet Web app, multipart support is auto-configured where appropriate. If you manually configure `MultipartResolver` or disable multipart, re-check the file-receiving mechanism.

Source layout:

```text
src/
  main/
    java/com/example/requestvalidation/
      RequestValidationApplication.java
      Address.java
      OrderRequest.java
      DocumentMetadata.java
      ApiController.java
      ApiValidationAdvice.java
  test/
    java/com/example/requestvalidation/
      ApiControllerTest.java
```

### 5.2. Entry point

File `src/main/java/com/example/requestvalidation/RequestValidationApplication.java`:

```java
package com.example.requestvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(RequestValidationApplication.class, args);
    }
}
```

### 5.3. DTOs and nested constraints

File `src/main/java/com/example/requestvalidation/Address.java`:

```java
package com.example.requestvalidation;

import jakarta.validation.constraints.NotBlank;

public record Address(
        @NotBlank String city
) {}
```

File `src/main/java/com/example/requestvalidation/OrderRequest.java`:

```java
package com.example.requestvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record OrderRequest(
        @NotBlank String customer,
        @NotNull @Positive Integer quantity,
        @NotNull @Valid Address address
) {}
```

File `src/main/java/com/example/requestvalidation/DocumentMetadata.java`:

```java
package com.example.requestvalidation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record DocumentMetadata(
        @NotBlank String title,
        @NotNull @Positive Integer revision
) {}
```

All three records use Jakarta APIs. Separate DTOs for HTTP help avoid deserializing/binding directly into JPA entities or objects with internal fields like `ownerId`, `approved`, or `admin`.

For records, the Jakarta provider reads constraints on record components/fields/accessors according to supported metadata. Records do not need public setters. Use annotations at locations supported by the spec and test with your project's provider.

### 5.4. Controller receiving two request types

File `src/main/java/com/example/requestvalidation/ApiController.java`:

```java
package com.example.requestvalidation;

import jakarta.validation.Valid;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api")
public class ApiController {

    @PostMapping(
        path = "/orders",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Map<String, Object>> createOrder(
            @Valid @RequestBody OrderRequest request) {

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("customer", request.customer());
        body.put("quantity", request.quantity());
        body.put("city", request.address().city());

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(body);
    }

    @PostMapping(
        path = "/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public ResponseEntity<Map<String, Object>> upload(
            @Valid @RequestPart("metadata") DocumentMetadata metadata,
            @RequestPart("attachment") MultipartFile attachment) {

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("title", metadata.title());
        body.put("revision", metadata.revision());
        body.put(
                "filename",
                Objects.toString(attachment.getOriginalFilename(), "")
        );

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(body);
    }
}
```

This is a **demo**, with no order/file persistence yet. In particular, never use `attachment.getOriginalFilename()` directly to construct a file write path in production. The filename is client-supplied metadata and untrusted. This endpoint only shows the JSON part being converted + validated; checking file size, magic bytes, malware, upload permissions, and storage belong to a separate process.

There is no `@Validated` on the class and no direct constraints on other method parameters. As a result, the example focuses on **argument validation** and `MethodArgumentNotValidException` rather than forcing the controller through AOP/built-in method validation.

### 5.5. Error handling distinguishing parse vs. validation

File `src/main/java/com/example/requestvalidation/ApiValidationAdvice.java`:

```java
package com.example.requestvalidation;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiValidationAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> validationFailed(
            MethodArgumentNotValidException exception) {

        List<Map<String, String>> fields =
                exception.getBindingResult()
                        .getFieldErrors()
                        .stream()
                        .map(this::toFieldError)
                        .toList();

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("code", "VALIDATION_ERROR");
        body.put("errors", fields);

        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> unreadable(
            HttpMessageNotReadableException exception) {

        // Do not return exception.getMessage() directly to the client:
        // it can expose Java/JSON structure or internal data.
        Map<String, String> body = Map.of(
                "code", "INVALID_PAYLOAD",
                "message", "Unable to read request body or JSON part"
        );
        return ResponseEntity.badRequest().body(body);
    }

    private Map<String, String> toFieldError(FieldError error) {
        return Map.of(
                "field", error.getField(),
                "message", Objects.toString(
                        error.getDefaultMessage(), "Invalid value"
                )
        );
    }
}
```

Distinguish the two handlers:

- `MethodArgumentNotValidException`: the object was created and Bean Validation returned field violations. For example, `customer=" "`, `quantity=0`, or metadata `revision=0`.
- `HttpMessageNotReadableException`: the converter could not deserialize the input, such as truncated JSON or an incompatible data shape. Do not fabricate a `FieldError` and call it `@Positive` if parsing did not even succeed.
- Missing multipart parts and unsupported media types are left to **Spring MVC's default exception handling** in the demo because they are resolver/converter errors, not `ConstraintViolation`s. Production can add dedicated handlers for `MissingServletRequestPartException` and `HttpMediaTypeNotSupportedException`.

This advice returns only `FieldError`s. Custom **class-level constraints** can produce `ObjectError`s (global errors), so `getGlobalErrors()` should be considered when building a complete error contract. If the controller has direct method constraints, `HandlerMethodValidationException` must also be handled. Having a generic handler does not replace understanding the actual cause of each error.

## 6. Running HTTP requests and expected results

Start the application after generating the Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows you can use `gradlew.bat bootRun`. With default configuration, the server listens on `http://localhost:8080`.

### 6.1. Valid JSON body

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customer":"Lan","quantity":2,"address":{"city":"Hue"}}'
```

Expected HTTP: `201 Created`. Illustrative body:

```json
{
  "customer": "Lan",
  "quantity": 2,
  "city": "Hue"
}
```

Steps performed: converter reads JSON → creates `OrderRequest` and `Address` → `@Valid` checks constraints → controller executes.

### 6.2. Syntactically valid JSON violating constraints

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customer":" ","quantity":0,"address":{"city":""}}'
```

Expected HTTP: `400 Bad Request`, error code `VALIDATION_ERROR`:

```json
{
  "code": "VALIDATION_ERROR",
  "errors": [
    {"field": "customer", "message": "must not be blank"},
    {"field": "quantity", "message": "must be greater than 0"},
    {"field": "address.city", "message": "must not be blank"}
  ]
}
```

**Note:** the exact text in `message` depends on the provider, locale, and bundle; the order of items in `errors` should also not be treated as a contract. The JSON body above illustrates the **three error paths**; stable tests should look up the needed fields or assert the error code rather than asserting exact ordering or exact English text.

### 6.3. Unparseable JSON

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customer":"Lan","quantity":'
```

Expected HTTP: `400 Bad Request` with body:

```json
{
  "code": "INVALID_PAYLOAD",
  "message": "Unable to read request body or JSON part"
}
```

At this point **there is no** valid DTO on which to run `@NotBlank`/`@Positive`. If the controller logs `validation failed` for this scenario, re-examine the exception path.

### 6.4. Multipart with JSON metadata and file

```bash
curl -i -X POST http://localhost:8080/api/documents \
  -F 'metadata={"title":"Minutes","revision":1};type=application/json' \
  -F 'attachment=@note.txt;type=text/plain'
```

The command above assumes `note.txt` exists in the working directory. When metadata is valid, expected HTTP is `201 Created`:

```json
{
  "title": "Minutes",
  "revision": 1,
  "filename": "note.txt"
}
```

The `type=application/json` part on the metadata field is **important**: it sets the media type of **that part**, not forcing the entire request to `application/json`. The overall request remains `multipart/form-data`.

### 6.5. Invalid JSON metadata

```bash
curl -i -X POST http://localhost:8080/api/documents \
  -F 'metadata={"title":"","revision":0};type=application/json' \
  -F 'attachment=@note.txt;type=text/plain'
```

Expected result: `400 Bad Request` with `code = VALIDATION_ERROR`, violating fields `title` and `revision`. Whether a file is sent or not does not alter those two constraints in `DocumentMetadata`.

### 6.6. Metadata part with wrong Content-Type

For example, trying to send JSON bytes as text:

```bash
curl -i -X POST http://localhost:8080/api/documents \
  -F 'metadata={"title":"Minutes","revision":1};type=text/plain' \
  -F 'attachment=@note.txt;type=text/plain'
```

With default converters and target `DocumentMetadata`, there is typically no converter to read `text/plain` into that type: result **415 Unsupported Media Type**. This is not a `@NotBlank` violation. Converter selection happens **before** validation.

### 6.7. Missing part

If multipart only includes `attachment` and omits the part named `metadata`, `@RequestPart("metadata")` defaults to `required=true`; Spring usually reports `MissingServletRequestPartException` → HTTP 400. Unlike valid JSON metadata with `title=""`: one case has **no argument**, while the other has an **argument that violates a constraint**.

## 7. Testing Spring MVC with MockMvc

File `src/test/java/com/example/requestvalidation/ApiControllerTest.java`:

```java
package com.example.requestvalidation;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validJsonBodyPassesDeserializationAndValidation()
            throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "customer": "Lan",
                          "quantity": 2,
                          "address": {"city": "Hue"}
                        }
                        """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.customer").value("Lan"))
            .andExpect(jsonPath("$.quantity").value(2))
            .andExpect(jsonPath("$.city").value("Hue"));
    }

    @Test
    void invalidObjectFailsValidationAfterJsonIsRead()
            throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "customer": " ",
                          "quantity": 0,
                          "address": {"city": ""}
                        }
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors").isArray());
    }

    @Test
    void malformedJsonIsNotBeanValidationFailure()
            throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"customer\":\"Lan\",\"quantity\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("INVALID_PAYLOAD"));
    }

    @Test
    void validMultipartJsonPartIsValidated() throws Exception {
        MockMultipartFile metadata = jsonPart(
                "{\"title\":\"Minutes\",\"revision\":1}"
        );
        MockMultipartFile attachment = filePart();

        mvc.perform(multipart("/api/documents")
                .file(metadata)
                .file(attachment))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title").value("Minutes"))
            .andExpect(jsonPath("$.revision").value(1))
            .andExpect(jsonPath("$.filename").value("note.txt"));
    }

    @Test
    void invalidMultipartMetadataFailsBeanValidation()
            throws Exception {
        MockMultipartFile metadata = jsonPart(
                "{\"title\":\"\",\"revision\":0}"
        );

        mvc.perform(multipart("/api/documents")
                .file(metadata)
                .file(filePart()))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"));
    }

    @Test
    void missingMetadataPartIsMissingArgumentNotConstraintError()
            throws Exception {
        mvc.perform(multipart("/api/documents")
                .file(filePart()))
            .andExpect(status().isBadRequest());
    }

    @Test
    void wrongContentTypeForJsonPartIsUnsupported()
            throws Exception {
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata",
                "",
                MediaType.TEXT_PLAIN_VALUE,
                "{\"title\":\"Minutes\",\"revision\":1}"
                        .getBytes(StandardCharsets.UTF_8)
        );

        mvc.perform(multipart("/api/documents")
                .file(metadata)
                .file(filePart()))
            .andExpect(status().isUnsupportedMediaType());
    }

    private static MockMultipartFile jsonPart(String json) {
        return new MockMultipartFile(
                "metadata",
                "",
                MediaType.APPLICATION_JSON_VALUE,
                json.getBytes(StandardCharsets.UTF_8)
        );
    }

    private static MockMultipartFile filePart() {
        return new MockMultipartFile(
                "attachment",
                "note.txt",
                MediaType.TEXT_PLAIN_VALUE,
                "Hello".getBytes(StandardCharsets.UTF_8)
        );
    }
}
```

Run:

```bash
./gradlew test
```

**Expected:** all seven tests PASS in the described setup. They verify the **HTTP pipeline** rather than merely calling `validator.validate(...)` manually:

- Valid JSON request body.
- Constraint violations after JSON is read successfully.
- Malformed JSON distinct from Bean Validation.
- Valid multipart JSON metadata.
- Multipart metadata violating constraints.
- Missing metadata part.
- Metadata part without a matching media type converter.

`MockMultipartFile` is a Spring Test utility: it creates a named part with a content type and byte content; it is not a file loaded from disk and does not require a real `note.txt`. In `curl`, by contrast, `@note.txt` requires the local file to exist. Thus, the tests do not depend on the filesystem.

Do not assert `FieldError` order if an input violates multiple constraints at once. Check the list of fields by name or use predicates for stricter tests. In this lesson, the tests separate **error categories** using `VALIDATION_ERROR` vs. `INVALID_PAYLOAD`, while the multipart media type test verifies HTTP 415.

## 8. Catching errors in the controller with BindingResult

Not every `@Valid` violation has to throw an exception. For `@RequestBody` and `@RequestPart` in the argument validation path, you can declare `Errors` or `BindingResult` **immediately after the argument being validated**:

```java
@PostMapping("/manual")
public ResponseEntity<String> manual(
        @Valid @RequestBody OrderRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body("Invalid data");
    }
    return ResponseEntity.ok("Valid");
}
```

Similarly for a JSON part:

```java
@PostMapping(
        path = "/manual-upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public ResponseEntity<String> manualUpload(
        @Valid @RequestPart("metadata") DocumentMetadata metadata,
        BindingResult errors,
        @RequestPart("attachment") MultipartFile attachment) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body("Invalid metadata");
    }
    return ResponseEntity.ok("Valid");
}
```

These are **illustrative methods**, not part of the runnable source in section 5. `BindingResult` must stand immediately after the corresponding `OrderRequest` or `DocumentMetadata`. Putting a `@RequestParam` or file parameter in between may prevent Spring from associating `BindingResult` with the right argument.

**Limitation:** `BindingResult` mainly lets you inspect **binding/validation errors** once the converter has created the argument. It does not guarantee the controller method will be reached if the JSON is malformed, a required part is missing, or no converter can read the media type. Those failures happen earlier.

In Spring MVC 6.1+ method validation, if there are direct constraints on other parameters, Spring only invokes the controller if all validation errors belong to parameters that have an adjacent `Errors` parameter; if any error is not handled that way, `HandlerMethodValidationException` can occur. Therefore, when extending a controller signature, re-run tests covering exception paths.

## 9. A closer look at exception types

| Scenario | Phase | Typical exception | Typical HTTP |
| --- | --- | --- | --- |
| Valid JSON, `@NotBlank` fails | Argument Bean Validation | `MethodArgumentNotValidException` | 400 |
| Malformed JSON | JSON deserialization | `HttpMessageNotReadableException` | 400 |
| JSON has incompatible type and Jackson cannot convert | JSON deserialization | `HttpMessageNotReadableException` | 400 |
| Multipart JSON metadata violates `@Positive` | Argument Bean Validation | `MethodArgumentNotValidException` | 400 |
| Multipart missing required `metadata` or `attachment` | Part resolution | `MissingServletRequestPartException` | 400 |
| Metadata part is `text/plain` while target only has JSON converter | Message conversion | `HttpMediaTypeNotSupportedException` | 415 |
| HTTP body has Content-Type not matching `consumes` | Handler mapping/content negotiation | `HttpMediaTypeNotSupportedException` or similar error | 415 |
| Incoming data exceeds multipart limits | Multipart parsing/config | `MaxUploadSizeExceededException` or `MultipartException` | Config-dependent, often 413 for size limit |
| Controller has direct method constraints | MVC built-in method validation | `HandlerMethodValidationException` | 400 for invalid input |
| Validator invoked manually via `Validator#validate` | Jakarta API | Returns `Set<ConstraintViolation<?>>` | Does not generate HTTP response automatically |

The table describes typical paths in **Servlet Spring MVC**, not a guarantee that every version/configuration produces the exact same exception. For instance, another converter, custom resolver, or global exception handler can change the outcome. In Spring WebFlux, argument validation errors typically belong to a different hierarchy, such as `WebExchangeBindException`.

Also do not equate `@RequestPart` with `@RequestParam` when receiving JSON: if you use `@RequestParam String metadata` and call Jackson manually, Spring will not automatically apply `@Valid` from the String parameter onto the `DocumentMetadata` object you construct inside the controller. You must invoke the validator manually if you choose to deserialize that way.

## 10. Validation groups and complex input structures

### 10.1. Selecting groups instead of only @Valid

`@Valid` normally validates under the `Default` group. If you need to check rules specific to a Create operation:

```java
public interface Create {}

public record DocumentMetadata(
        @NotBlank(groups = Create.class) String title,
        @Positive(groups = Create.class) Integer revision
) {}

@PostMapping("/documents")
public void upload(
        @Validated(Create.class)
        @RequestPart("metadata") DocumentMetadata metadata) {
    // ...
}
```

This is an **illustrative snippet**, not part of the runnable project above; it requires importing `org.springframework.validation.annotation.Validated` and related annotations. Selecting `Create` does not implicitly include `Default`. If you want `revision` to be non-null, you need `@NotNull(groups = Create.class)`.

Selecting groups on the **parameter** expresses the endpoint's intent. There is no need to place `@Validated` on the controller class, because doing so can switch the controller to AOP method validation in Spring MVC 6.1+, producing a different exception path from built-in method validation.

### 10.2. Validating nested objects and collections

`@Valid` placed on a nested field or collection element cascades constraints:

```java
public record Shipment(
        @NotBlank String reference,
        @NotEmpty
        java.util.List<@Valid PackageItem> items
) {}

public record PackageItem(
        @NotBlank String sku,
        @Positive int quantity
) {}
```

This is a DTO structure example requiring imports for `jakarta.validation.constraints.NotEmpty` and related annotations. When the controller receives `@Valid @RequestBody Shipment`, the provider can traverse into each `PackageItem` and check `sku`/`quantity`.

**Note on top-level collections:** Spring MVC argument validation for `@RequestBody`/`@RequestPart` focuses on **command objects** and does not automatically treat `@Valid List<Dto>` or `Map<...>` at the top level identically to a wrapper DTO across all validation paths. If receiving a JSON array, consider using a wrapper record like `Shipment` or checking method validation and testing explicitly; do not assume `@Valid` on a top-level collection always behaves identically to a bean object.

### 10.3. File uploads require separate rules

At a minimum, a production multipart endpoint needs to check:

- `MultipartFile#isEmpty()` and `getSize()` against business limits, in addition to configuring upload limits in the web server/framework.
- File extensions do **not** prove the actual content type. `getContentType()` is a client-supplied value.
- Do not use `getOriginalFilename()` as a storage path without normalizing and verifying it; guard against path traversal/overwrites.
- Scan for malicious content if required by the system.
- Authenticate and authorize before writing files, and assign a storage name independent of the client's filename.
- Persist metadata only after required conditions are satisfied; manage transactions/compensation when combining file storage with a database.

`@Valid @RequestPart("metadata")` only guarantees that **the constraints you placed on metadata** were checked. A file is not automatically safe just because the request went through the same controller.

## 11. Security, resilience, and contract stability

### 11.1. Do not return raw parser messages to clients

`HttpMessageNotReadableException#getMessage()` can contain technical details about classes, fields, or data content. Returning this message directly couples the API to Jackson/Spring versions and can leak internal details. The demo handler returns `INVALID_PAYLOAD` with a generic message, while the server can log details according to policy (never logging passwords/tokens/raw uploads).

### 11.2. Do not use translated messages as the sole error code

Bean Validation messages depend on locale, bundle, and provider. Clients should not have to parse the string `"must not be blank"` to know which field failed. A more stable approach is returning:

```json
{
  "code": "VALIDATION_ERROR",
  "errors": [
    {
      "field": "quantity",
      "message": "must be greater than 0"
    }
  ]
}
```

In larger APIs, you can add a `fieldErrorCode` such as `POSITIVE_REQUIRED`, a request correlation ID, and map to a Problem Details structure (`ProblemDetail`/RFC 9457) per organizational policy. Do not let clients depend on the ordering of items in `errors`.

### 11.3. Do not bind input directly to sensitive entities

Even though `@RequestBody` uses Jackson and `@RequestPart` uses a converter for metadata, the receiving object should still be an **input DTO with an allowed set of fields**. Do not accept an entity containing `admin`, `role`, or `ownerId` directly and rely solely on `@Valid`; validation does not replace authorization or mass-assignment policies.

### 11.4. Resource control

Large bodies, deeply nested JSON, many multipart parts, or oversized files can consume CPU/RAM/disk before the controller is invoked. Limit request size, max upload size, part count, and configure Jackson/parser settings appropriately for deployment risks. DTO validation happens after deserialization, so it is not the first line of defense against oversized payloads.

### 11.5. Be careful with Optional/required=false

`@RequestBody(required = false)` or `@RequestPart(required = false)` can allow a null argument when input is absent. Attaching `@Valid` alone does not create a non-null constraint for a null argument. If the API requires the data, usually keep the default `required=true` and use `@NotNull` on **fields inside the DTO**. Do not conflate "missing body" with "missing field inside the body".

## 12. Checking common mistakes

**Mistake 1 — Thinking @Valid parses JSON.** `@Valid` only invokes the validator. Jackson/HttpMessageConverter must construct the object first; malformed JSON cannot be fixed by validation annotations.

**Mistake 2 — Sending a JSON part with Content-Type text/plain.** With `@RequestPart DocumentMetadata`, the converter needs a matching media type; lacking a JSON Content-Type can cause HTTP 415.

**Mistake 3 — Putting @Valid on MultipartFile and thinking the file is safe.** File content, name, size, and type require separate checks and policy enforcement.

**Mistake 4 — Conflating HttpMessageNotReadableException with MethodArgumentNotValidException.** One is a deserialization error, the other is Bean Validation. Use distinct error codes.

**Mistake 5 — Forgetting @Valid on the controller parameter or nested object.** Constraints on a DTO do not always run automatically; nested objects require cascading in the right places.

**Mistake 6 — Forgetting @NotNull when using @Positive/@Min.** Some constraints allow null per the spec; a missing field can slip through if no other constraint is present.

**Mistake 7 — Placing BindingResult in the wrong position.** `BindingResult` must immediately follow the corresponding argument. If input fails to deserialize, the controller still may not run to read the result.

**Mistake 8 — Using @RequestParam String metadata and expecting metadata validation.** If metadata remains a String, Bean Validation cannot see the DTO fields. Use `@RequestPart` with a converter or deliberately deserialize/validate manually.

**Mistake 9 — Confusing method validation with argument validation.** Adding `@Min` directly onto a handler parameter can switch to `HandlerMethodValidationException` (Spring MVC 6.1+). Always test the actual exception path.

**Mistake 10 — Adding @Validated at the controller class level like AOP services.** Spring MVC 6.1+ has built-in method validation; type-level `@Validated` can cause the AOP path to be used. Avoid unintended mixing.

**Mistake 11 — Asserting validation always runs after all middleware.** Authentication, request filtering, multipart parsing, content negotiation, and message conversion can reject a request before any DTO exists. Observe the pipeline stage by stage.

**Mistake 12 — Not testing error inputs by layer.** A single "status 400" test does not distinguish parse errors, missing parts, and constraint violations. Assert both the error code and the request type.

**Mistake 13 — Using a DTO/Entity containing sensitive fields.** Bean Validation does not stop clients from supplying unauthorized values into deserializable fields. Control the DTO, authorization, and DTO → domain mapping.

**Mistake 14 — Trusting upload Content-Type.** That is client-supplied metadata; never use it as the sole proof that a file is safe.

## 13. Checklist for implementing endpoints properly

1. Identify the media type of the whole request: `application/json` or `multipart/form-data`.
2. For direct JSON, use `@RequestBody`; for JSON metadata inside multipart, use `@RequestPart("metadata")` and send a JSON Content-Type for the part.
3. Use dedicated DTOs; never deserialize directly into domain/JPA entities with sensitive fields.
4. Place `@NotBlank`, `@NotNull`, `@Positive`, and `@Valid` for nested objects.
5. Attach `@Valid` or `@Validated(Group.class)` to the argument that needs validation.
6. Do not apply `@Validated` at the controller class level out of habit unless AOP is intentionally desired.
7. If handling violations inside the controller, place `BindingResult`/`Errors` **immediately after** that argument.
8. Handle `MethodArgumentNotValidException`, `HttpMessageNotReadableException`, and multipart resolver errors separately; account for `HandlerMethodValidationException` when direct method constraints exist.
9. Give input validation errors a stable error code and clear field names; avoid leaking raw parser exceptions.
10. Independently validate file size, extension, actual MIME, content, original filename, permissions, and storage.
11. Use `MockMvc` to test at least valid JSON, rule-violating JSON, malformed JSON, valid multipart, rule-violating metadata, missing part, and wrong media type.
12. Verify Jakarta Validation/Spring Boot dependency compatibility, `MultipartResolver` configuration, and active converters when deploying.

**Conclusion:** `@RequestBody` reads the **entire request body**, whereas `@RequestPart` reads **individual parts** of a multipart request; both can use `HttpMessageConverter` to construct Java objects, after which `@Valid`/`@Validated` triggers Jakarta Bean Validation. Distinguish **deserialization/conversion errors** from **constraint violations**, and treat file upload checks as a separate layer of responsibility. Doing so gives your API consistent responses, clear tests, and fewer false assumptions about when validation actually runs.

## References

- [Spring Framework 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html): converters, Bean Validation, and `BindingResult`.
- [Spring Framework 6.2 — Multipart](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): JSON metadata with `@RequestPart`, `MultipartFile`, validation.
- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): argument validation vs. method validation, two exception types.
- [Spring Framework 6.2 — Message Converters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html): request deserialization by media type.
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): `@Valid`, constraints, cascading, and groups.
