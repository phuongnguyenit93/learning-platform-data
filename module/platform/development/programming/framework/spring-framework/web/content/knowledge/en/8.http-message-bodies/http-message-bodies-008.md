# RequestBodyAdvice, ResponseBodyAdvice, and Limits of Shared Body Transformation in Spring MVC

## 1. Context: Why Intercept HTTP Bodies?

When multiple Spring MVC endpoints share a common representation requirement, you may want to **adjust newly decoded request data** or **modify responses before they are written to HTTP** without repeating the same code in every controller. For example:

- Normalizing whitespace on a specific request DTO type before validation.
- Adding a JSON `{"data": ...}` wrapper for **a group** of APIs with an explicit response contract.
- Adding metadata/headers based on a policy applied to selected controllers.
- Providing specialized handling for a body type already read by `HttpMessageConverter`.

Spring Web MVC provides two extension points:

- **`RequestBodyAdvice`:** intercepts reading a request body into a Java object, before the object is passed to the controller.
- **`ResponseBodyAdvice<T>`:** intercepts the return object after the response converter has been chosen, but before the converter serializes it to the response body.

These are hooks in **Spring MVC on the Servlet stack**. Spring WebFlux uses a different pipeline/reactive codecs; do not copy these advice classes verbatim to WebFlux. The complete example uses **Java 17, Spring Boot 3.3.5, Spring Framework 6.1.x**, giving the imports, methods, and HTTP outputs an explicit version context.

**Core principle:** Advice lets you share processing at a single point in the MVC pipeline. It does not turn every response type into JSON by itself, is not designed to read every body of every request type, and is no substitute for authorization, Bean Validation, streaming, error mapping, or business logic.

## 2. Placing Both Advices in the Spring MVC Lifecycle

A typical JSON request cycle:

```text
HTTP request / JSON bytes
       |
       v
Servlet Filter(s) / DispatcherServlet
       |
       v
HandlerMapping selects controller method
       |
       v
Argument resolver encounters @RequestBody
       |
       v
Select HttpMessageConverter to read JSON
       |
       v
RequestBodyAdvice.supports(...)
       |
       +--> beforeBodyRead(HttpInputMessage) if body is present
       |         |
       |         v
       |    HttpMessageConverter.read(...)
       |         |
       |         v
       +--> afterBodyRead(Java object)
       |
       +--> handleEmptyBody(...) if body is empty
       |
       v
Bean Validation if parameter uses @Valid/@Validated
       |
       v
Controller method and application logic
       |
       v
Return-value handler selects response media type and converter
       |
       v
ResponseBodyAdvice.supports(...)
       |
       v
ResponseBodyAdvice.beforeBodyWrite(...)
       |
       v
HttpMessageConverter.write(...)
       |
       v
HTTP response / bytes
```

Simplified diagram for learning: resolvers, converters, and the framework have many branches depending on media type, parameter type, and return handling. For malformed JSON bodies, the converter can throw an exception **before** `afterBodyRead`; for empty bodies, `handleEmptyBody` is a separate path. When a body bypasses converters, the corresponding advice may not run at all. <u>Do not assume an advice always runs for every HTTP request/response.</u>

Example controller receiving data:

```java
@PostMapping("/notes")
@ResponseBody
public NoteView create(@Valid @RequestBody NoteInput input) {
    // ...
}
```

This is an illustrative method. `RequestBodyAdvice` can process `NoteInput` **after JSON deserialization and before validation**. `ResponseBodyAdvice` can process `NoteView` **before JSON serialization**. If the controller throws an exception, response output follows exception resolvers/handlers; do not assume it takes the same normal return path of this method.

## 3. RequestBodyAdvice: Responsibilities and Hook Order

The full interface belongs to `org.springframework.web.servlet.mvc.method.annotation.RequestBodyAdvice`. Representative methods in Spring Framework 6.1:

```java
boolean supports(
    MethodParameter methodParameter,
    Type targetType,
    Class<? extends HttpMessageConverter<?>> converterType);

HttpInputMessage beforeBodyRead(
    HttpInputMessage inputMessage,
    MethodParameter parameter,
    Type targetType,
    Class<? extends HttpMessageConverter<?>> converterType) throws IOException;

Object afterBodyRead(
    Object body,
    HttpInputMessage inputMessage,
    MethodParameter parameter,
    Type targetType,
    Class<? extends HttpMessageConverter<?>> converterType);

Object handleEmptyBody(
    Object body,
    HttpInputMessage inputMessage,
    MethodParameter parameter,
    Type targetType,
    Class<? extends HttpMessageConverter<?>> converterType);
```

These signatures are **API excerpts**, requiring imports and a class implementing the interface to compile. `RequestBodyAdviceAdapter` provides default implementations for the last three hooks, so you only need to implement `supports` and override the hooks you want.

### 3.1. supports: The First Scope Filter

`supports(methodParameter, targetType, converterType)` is queried before the advice is applied. It provides:

- `methodParameter`: the controller parameter site, used to check custom annotations or parameter types.
- `targetType`: the actual Java type being read by the converter; may differ from the parameter type (e.g., `HttpEntity<NoteInput>`).
- `converterType`: the converter class chosen by Spring.

If it returns `false`, the advice skips that parameter. If it returns `true`, the appropriate hooks can run. You should **filter at least by endpoint/annotation + data type + converter** when planning to alter objects; this protects APIs with different data contracts.

```java
@Override
public boolean supports(
        MethodParameter parameter, Type targetType,
        Class<? extends HttpMessageConverter<?>> converterType) {
    return parameter.hasParameterAnnotation(NormalizeNote.class)
            && targetType == NoteController.NoteInput.class
            && MappingJackson2HttpMessageConverter.class
                    .isAssignableFrom(converterType);
}
```

This is taken from the complete example below. It only opts in when `@NormalizeNote` is present, the target type is `NoteInput`, and the converter is Jackson JSON-compatible. Never write a global `return true` condition that coerces every `Object` into the same DTO.

### 3.2. beforeBodyRead: Before the Converter Reads Bytes

`beforeBodyRead` receives the `HttpInputMessage` containing headers + the request `InputStream`. The hook can return the original `inputMessage` or **a valid wrapper** providing a different body stream. Any byte modification has consequences:

- If modifying raw JSON, keep JSON valid and keep encoding/charset and media type consistent.
- You cannot assume streams are re-readable: input streams are normally consumed once.
- If byte length changes, the old `Content-Length` is no longer accurate; related headers, content encoding, and integrity signatures must also be considered.
- Payload decryption, decompression, or checksum verification are protocol/security concerns that require explicit design; do not shoehorn them into advice merely because the hook exists.
- Buffering an entire body in RAM to transform it poses size/DoS risks; enforce request limits at the right layer.

In most standard JSON APIs, transforming the **object after conversion** via `afterBodyRead` is easier to verify than manipulating bytes before Jackson.

### 3.3. afterBodyRead: After the Converter, Before the Controller

`afterBodyRead` receives the object successfully parsed by the converter. You can return the original object or a replacement **compatible with the controller parameter type**. For instance, create a new record from the old one using `text.strip()`, then let Bean Validation check the new value.

Crucial point: if input `"   "` is trimmed to `""`, `@NotBlank` then reports a violation. This is a policy that **changes the meaning of input**, so it must be documented in the API contract and applied deliberately. Do not blindly strip all text fields on every DTO—whitespace can be meaningful in passwords, signatures, search queries, or user content.

If the converter fails to parse JSON, there is no valid object to pass to `afterBodyRead`. That case typically leads to `HttpMessageNotReadableException` and HTTP `400` in common configurations.

### 3.4. handleEmptyBody: Truly Empty Request Bodies

`handleEmptyBody` is called on the empty-body branch for requests processed by body readers. The default adapter returns the body as-is (usually `null`). If `@RequestBody` is required, a `null` result can cause Spring to report a missing body. Do not treat JSON `{}`, JSON `null`, a bodyless request, and malformed JSON as identical: they do not necessarily trigger the same hooks.

If the API contract states a body is required, the consistent solution is usually to **return a client error**, not secretly fabricate a default object from an empty body. Only provide defaults when the endpoint explicitly documents it, and verify interaction with `@RequestBody(required = true/false)`.

### 3.5. Supported Data Paths

The Javadoc describes `RequestBodyAdvice` for parameters handled via `@RequestBody` or `HttpEntity`. Do not assume it handles all `@ModelAttribute` bindings, query params, form binding, multipart streams, or manual `request.getInputStream()` reads. `@RequestPart` has its own handling; if you need policies on multipart parts, verify the exact resolver and behavior in your Spring version.

## 4. ResponseBodyAdvice<T>: Intercepting Before Writing the Body

The `org.springframework.web.servlet.mvc.method.annotation.ResponseBodyAdvice<T>` interface has two main methods:

```java
boolean supports(
    MethodParameter returnType,
    Class<? extends HttpMessageConverter<?>> converterType);

T beforeBodyWrite(
    T body,
    MethodParameter returnType,
    MediaType selectedContentType,
    Class<? extends HttpMessageConverter<?>> selectedConverterType,
    ServerHttpRequest request,
    ServerHttpResponse response);
```

These are illustrative signatures of the Spring MVC 6.1 API. The advice runs for `@ResponseBody` and `ResponseEntity` results when MVC uses a converter to write the body; `@RestController` also uses `@ResponseBody` semantics.

- `supports` decides whether to apply to the method return and already-selected converter.
- `beforeBodyWrite` receives the body and metadata **after Spring selects the converter and before calling converter.write**. You can return the original body or another object; only return a type the already-selected converter can still serialize.
- `selectedContentType` already reflects response negotiation; the advice should not arbitrarily assume JSON when the actual response is text/binary.
- `response.getHeaders()` lets you add response headers, though body and header changes must remain consistent.

### Why Can "Wrapping Every Response in {data: ...}" Break?

Suppose a method returns `String`:

```java
@GetMapping(path = "/ping", produces = "text/plain")
public String ping() {
    return "pong";
}
```

Spring may choose `StringHttpMessageConverter`. If a `ResponseBodyAdvice<Object>` replaces the string with `new Envelope<>("pong")`, the converter **selected beforehand** may still expect a `String`. The consequence can be a `ClassCastException`, a write failure, or malformed output. Advice **does not re-run converter selection after you swap the object**.

Therefore, check all of these together:

1. **Endpoint contract** (annotations, package/controller, return type).
2. **Converter type** (`MappingJackson2HttpMessageConverter` when wrapping JSON DTOs).
3. **Actual body type** before modifying.
4. **Response media type**; do not alter outside committed representations.
5. **Null/empty bodies, status, and headers** so contentless responses are not broken.

Even when the converter supports the new object, wrapping in `{"data": ...}` **is a public change to the JSON schema**. Clients and OpenAPI schemas must know about it upfront.

### Relationship with ResponseEntity

`ResponseEntity<T>` lets controllers set status/headers/body. `ResponseBodyAdvice` can intercept the body when the return-value handler writes it via a converter, yet that **does not mean** the advice may silently turn `201` into `200`, swap `Content-Type` arbitrarily, or emit a body on `204 No Content`. Cases like `ResponseEntity<Void>`, `HEAD`, `304`, file downloads, binary streams, or byte ranges must be treated as explicit exclusions from a JSON-wrapping policy.

## 5. Comparing the Two Advices

| Aspect | `RequestBodyAdvice` | `ResponseBodyAdvice` |
| --- | --- | --- |
| Timing | Before/after converter **reads request** | After selecting converter to **write response**, before writing |
| Main input | `HttpInputMessage` or deserialized object | Controller return object, headers/selected media type |
| Scope filter | `supports(MethodParameter, Type, converterType)` | `supports(returnType, converterType)` |
| Hooks to remember | `beforeBodyRead`, `afterBodyRead`, `handleEmptyBody` | `beforeBodyWrite` |
| Good use cases | Normalizing specific parsed DTOs | Intentional JSON DTO wrapping, adding headers |
| Typical risks | Consuming streams, altering input before validation, changing data semantics | Changing return type after converter selection, altering API schema |
| Cannot replace | Authorization, validation, handling all form/multipart types | Global exception mapping, negotiation, serializers for every format |

**The two advices act in different directions.** Request advice is not a "filter for all inbound bytes", and response advice is not a "filter for all outbound bytes". Using each hook for its proper target avoids subtle bugs.

## 6. Runnable Example: Opt-in Normalization and JSON Envelope

The example has three endpoints:

- `POST /api/notes/normalized`: only this endpoint **opts in** to strip whitespace on `NoteInput.text` before `@Valid`; the response is wrapped as `{"data":{"text":"..."}}`.
- `POST /api/notes/plain`: normal JSON input/output, bypassing the normalization/wrapping policies of the two example advices.
- `GET /api/text`: text response via `StringHttpMessageConverter`, keeping plain text unwrapped.

The policy is intentionally scoped narrowly. A new endpoint should never suddenly change its JSON or input simply by sharing `@RestController`.

### 6.1. Project Structure

```text
mvc-body-advice-demo/
├── pom.xml
└── src/main/java/example/bodyadvice/
    ├── BodyAdviceApplication.java
    ├── NormalizeNote.java
    ├── WrapData.java
    ├── NoteController.java
    ├── NormalizeNoteAdvice.java
    └── WrapDataAdvice.java
```

All classes share the `example.bodyadvice` package, so referencing types from other files in the package requires no extra imports.

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
    <groupId>example</groupId>
    <artifactId>mvc-body-advice-demo</artifactId>
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

**`src/main/java/example/bodyadvice/BodyAdviceApplication.java`**

```java
package example.bodyadvice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BodyAdviceApplication {
    public static void main(String[] args) {
        SpringApplication.run(BodyAdviceApplication.class, args);
    }
}
```

### 6.2. Two Annotations Specifying Which Endpoints Opt Into Which Policy

**`NormalizeNote.java`**

```java
package example.bodyadvice;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface NormalizeNote {}
```

**`WrapData.java`**

```java
package example.bodyadvice;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface WrapData {}
```

`@NormalizeNote` is placed on the **parameter** to transform; `@WrapData` is placed on the **method** allowing response wrapping. Runtime retention is required because Spring uses reflection/handler-method metadata to detect these annotations.

### 6.3. Controller: Two Different JSON Contracts, One Text Endpoint

**`NoteController.java`**

```java
package example.bodyadvice;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class NoteController {

    public record NoteInput(@NotBlank String text) {}

    public record NoteOutput(String text) {}

    @PostMapping(path = "/notes/normalized",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    @WrapData
    public NoteOutput normalized(
            @NormalizeNote @Valid @RequestBody NoteInput request) {
        return new NoteOutput(request.text());
    }

    @PostMapping(path = "/notes/plain",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public NoteOutput plain(
            @Valid @RequestBody NoteInput request) {
        return new NoteOutput(request.text());
    }

    @GetMapping(path = "/text",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String text() {
        return "ready";
    }
}
```

`@NotBlank` verifies the string contains non-whitespace content. The controller does not trim input itself. Transformation lives in the request advice, activated only when `@NormalizeNote` is present; `@WrapData` is likewise attached only to the endpoint needing the envelope. There is no database, authentication, or state: responses reflect the input.

### 6.4. Request Advice: After Jackson, Before Validation

**`NormalizeNoteAdvice.java`**

```java
package example.bodyadvice;

import java.lang.reflect.Type;

import org.springframework.core.MethodParameter;
import org.springframework.http.HttpInputMessage;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.servlet.mvc.method.annotation.RequestBodyAdviceAdapter;

@ControllerAdvice(assignableTypes = NoteController.class)
public class NormalizeNoteAdvice extends RequestBodyAdviceAdapter {

    @Override
    public boolean supports(
            MethodParameter parameter,
            Type targetType,
            Class<? extends HttpMessageConverter<?>> converterType) {

        return parameter.hasParameterAnnotation(NormalizeNote.class)
                && targetType == NoteController.NoteInput.class
                && MappingJackson2HttpMessageConverter.class
                        .isAssignableFrom(converterType);
    }

    @Override
    public Object afterBodyRead(
            Object body,
            HttpInputMessage inputMessage,
            MethodParameter parameter,
            Type targetType,
            Class<? extends HttpMessageConverter<?>> converterType) {

        if (body instanceof NoteController.NoteInput note) {
            String text = note.text();
            return new NoteController.NoteInput(
                    text == null ? null : text.strip());
        }
        return body;
    }
}
```

Details:

- `@ControllerAdvice(assignableTypes = NoteController.class)` restricts which controller the advice targets. Inside `supports`, there are two more guard layers: the marker annotation and the converter/DTO type.
- `RequestBodyAdviceAdapter` preserves the default `beforeBodyRead` and `handleEmptyBody`; the example only modifies the object once Jackson has deserialized it.
- `String.strip()` (Java 11+) removes leading/trailing whitespace per `Character.isWhitespace`. It **does not** perform general Unicode normalization, does not sanitize HTML, and does not replace security checks.
- When `text=null`, null is preserved so `@NotBlank` handles it; do not silently substitute a default string.
- The advice returns **a new `NoteInput`**, the exact type required by the controller, not an envelope or arbitrary object that would cause a cast error.
- JSON syntax errors happen in the converter, so do not expect `afterBodyRead` to be called to "fix" broken JSON.

### 6.5. Response Advice: Wrapping Only Marked JSON DTOs

**`WrapDataAdvice.java`**

```java
package example.bodyadvice;

import org.springframework.core.MethodParameter;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyAdvice;

@ControllerAdvice(assignableTypes = NoteController.class)
public class WrapDataAdvice implements ResponseBodyAdvice<Object> {

    public record Envelope<T>(T data) {}

    @Override
    public boolean supports(
            MethodParameter returnType,
            Class<? extends HttpMessageConverter<?>> converterType) {

        return returnType.hasMethodAnnotation(WrapData.class)
                && MappingJackson2HttpMessageConverter.class
                        .isAssignableFrom(converterType);
    }

    @Override
    public Object beforeBodyWrite(
            Object body,
            MethodParameter returnType,
            MediaType selectedContentType,
            Class<? extends HttpMessageConverter<?>> selectedConverterType,
            ServerHttpRequest request,
            ServerHttpResponse response) {

        if (body == null) {
            return null;
        }
        response.getHeaders().add("X-Envelope-Applied", "true");
        return new Envelope<>(body);
    }
}
```

**Why is this example safe within its illustrative scope?** Endpoints marked `@WrapData` only return `NoteOutput` serialized as JSON by Jackson; the new body is `Envelope<NoteOutput>`, which Jackson also handles. We do not wrap text, bytes, `Resource`, or bodyless responses. In a real app, you should also check that the body type belongs to an approved set of DTO/response contracts to avoid accidentally wrapping a new return type if a developer misapplies `@WrapData`.

`beforeBodyWrite` can replace the object, but **cannot change the converter selection made earlier**. When the body is null, the hook keeps it null; it avoids creating `{"data":null}` for intentionally empty responses. The `X-Envelope-Applied` header is only added when the body is actually wrapped.

### 6.6. Running the Application

Open a terminal in the `mvc-body-advice-demo` directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Requires JDK 17+ and working Maven. Spring Boot defaults to `http://localhost:8080` unless a port change is configured.

**Send JSON input with whitespace and opt-in marker:**

```bash
curl -i -X POST http://localhost:8080/api/notes/normalized \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"text":"  Hello MVC  "}'
```

Key parts of the response:

```http
HTTP/1.1 201
Content-Type: application/json
X-Envelope-Applied: true

{"data":{"text":"Hello MVC"}}
```

Step-by-step explanation:

1. Jackson reads JSON into `new NoteInput("  Hello MVC  ")`.
2. `NormalizeNoteAdvice.supports` matches because the parameter has `@NormalizeNote` and the converter is JSON-compatible.
3. `afterBodyRead` returns `new NoteInput("Hello MVC")`.
4. `@Valid` checks `@NotBlank` against the stripped value.
5. The controller returns `new NoteOutput("Hello MVC")` with status `201`.
6. `WrapDataAdvice.supports` matches because the method has `@WrapData` and the writer converter is Jackson.
7. `beforeBodyWrite` returns `new Envelope<>(NoteOutput)` and adds the response header.
8. Jackson writes JSON containing the `data` field.

**Compare the non-opt-in endpoint:**

```bash
curl -i -X POST http://localhost:8080/api/notes/plain \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"text":"  Hello MVC  "}'
```

Main output:

```http
HTTP/1.1 200
Content-Type: application/json

{"text":"  Hello MVC  "}
```

No `X-Envelope-Applied` header appears because the advice does not wrap the response; whitespace is preserved because the parameter lacks `@NormalizeNote`.

**Text endpoint remains untouched:**

```bash
curl -i http://localhost:8080/api/text -H 'Accept: text/plain'
```

Response body:

```text
ready
```

Here `StringHttpMessageConverter` can be chosen. Because the method lacks `@WrapData` and the media type is text, the app does not wrap text as JSON. This is a critical check against converter-selection bugs.

**Validation runs on normalized data:**

```bash
curl -i -X POST http://localhost:8080/api/notes/normalized \
  -H 'Content-Type: application/json' \
  -d '{"text":"   "}'
```

`afterBodyRead` returns `NoteInput("")`, after which `@NotBlank` fails; the response is typically `400 Bad Request`. You cannot assume default error bodies also contain `data`: `@WrapData` applies to the selected handler's return value, whereas exception responses have their own processing pipeline.

**Malformed JSON:**

```bash
curl -i -X POST http://localhost:8080/api/notes/normalized \
  -H 'Content-Type: application/json' \
  --data-binary '{"text":'
```

The converter cannot parse the content; typically returns `400`. `afterBodyRead` has no valid DTO to fix. Actual error headers/JSON body depend on Spring Boot configuration and exception handlers.

In PowerShell, you can test with `Invoke-RestMethod`:

```powershell
Invoke-RestMethod -Method Post -Uri 'http://localhost:8080/api/notes/normalized' -ContentType 'application/json' -Body '{"text":"  Hello MVC  "}'
```

PowerShell displays the parsed JSON object in PowerShell format; to observe raw status/headers/body, use an HTTP tool that displays the raw response.

## 7. Key Limits of Shared Body Transformation

### 7.1. Scope Does Not Automatically Cover All Requests

`RequestBodyAdvice` attaches to bodies handled by resolvers/converters such as `@RequestBody` and `HttpEntity`. It is not a Servlet `Filter` reading every request, and does not by default handle query strings, path variables, session state, general HTML form binding, or bodies read manually by a controller. Whether advice applies in certain other resolvers must be checked for your exact Spring version and implementation; never generalize one observed case into a global guarantee.

If you need to process **raw HTTP requests before MVC routing**, evaluate a Servlet `Filter`. However, Filters also carry risks around stream consumption and filter ordering; never read unbounded bodies into memory just to log or transform them.

### 7.2. Response Advice Is Not Guaranteed to Run for Every Return Type

The response body must pass through an MVC return-value handler using message conversion. A controller rendering a Thymeleaf/JSP view via `ModelAndView` does not take the JSON return path. File streaming, `StreamingResponseBody`, `SseEmitter`, `ResponseBodyEmitter`, WebSockets, early-committed responses, bodyless responses, and servlets writing output directly also have different lifecycles.

If a contract requires consistent content across different transports, build policies specific to each transport. Do not force one `ResponseBodyAdvice<Object>` to span file downloads, SSE, binary, and HTML views.

### 7.3. Converter Selection Happens Before Response Advice

`ResponseBodyAdvice.beforeBodyWrite` runs **after** Spring has selected the converter. When advice swaps a `String` for a `Map` or DTO, the converter chosen for `String` may fail to serialize the new type. Errors can happen even when a JSON mapper is on the classpath. The `supports` guard must verify the converter, return annotation/type, and compatibility of the new body type.

For JSON APIs wanting a consistent envelope, a more contract-safe approach is **having controllers/services return an explicit `ApiResponse<T>` type** per contract, or scoping advice strictly to explicitly declared endpoints. For streaming/binary, keep the original response type and converter.

### 7.4. Media Type, Headers, and Payload Must Stay Consistent

Modifying bytes or objects can alter the representation. Consider:

- Do `Content-Type` and charset match the new body?
- Is an old `Content-Length` still valid if bytes changed? Should the framework/container recalculate it rather than keeping a stale value?
- Do `Content-Encoding`, compression, and checksums need adjustment?
- Do `ETag`, `Last-Modified`, cache validators, and response caching still reflect the new content?
- If the response carries a digital signature or HMAC over **raw bytes**, does transforming before/after signing break integrity?
- Does it change the JSON schema unexpectedly for clients, mobile apps, OpenAPI, and tests?

A "small" change like adding an envelope can break ETags or clients parsing top-level fields. If byte transformation is mandatory, design a layer responsible for headers, streaming, and integrity rather than mutating bodies in a hook alone.

### 7.5. Security: Never Use Advice to Replace Authorization

Advice can normalize/sanitize a chosen set of DTOs, but should never silently alter identity, tenant, permissions, or ownership without service verification. Specifically:

- Never log bodies containing passwords, access tokens, sessions, PII, or financial data.
- Do not expect global normalization to make dangerous data safe. HTML sanitization, SQL parameterization, path safety, and output encoding have distinct rules.
- If input requires raw signature verification, trimming/normalizing before verification can break the signature. Altering bytes after verification can also diverge from the signed payload.
- Do not wrap authentication/authorization errors into HTTP `200 OK` just to fit a `{"data": ...}` shape.
- The server still needs field-restricted input DTOs, Bean Validation, and per-resource authorization.

### 7.6. Validation, Exceptions, and Error Responses

Request advice can modify objects **before validation**, so validators see the transformed values. This order matters when testing. However, advice does not replace `@Valid`, custom validators, or business rules.

A `@ControllerAdvice` used for body advice can also host `@ExceptionHandler`s, yet those are **two distinct mechanisms**. Error responses are produced by handlers/`ProblemDetail`, exception resolvers, or `/error`; they do not automatically share the same wrapping conditions as success bodies. To achieve a uniform error contract, design `@RestControllerAdvice` / `ResponseEntityExceptionHandler` separately, preserving proper status codes and avoiding double wrapping.

### 7.7. Performance, Memory, and Concurrency

Advices are typically Spring singleton beans. Never store per-request state in mutable instance fields because concurrent requests run simultaneously. For request-scoped data, use method arguments, `request.getHeaders()`, scoped components, or request attributes appropriately.

`beforeBodyRead` reading entire streams can increase RAM usage and latency for every request. `ResponseBodyAdvice` allocating new object trees for large responses also increases allocations. For large payloads, prefer appropriate DTOs/streaming/codecs and enforce size limits. Avoid chaining multiple advices with the same responsibility, preventing `{"data":{"data":...}}`.

### 7.8. Ordering Multiple Advices and Idempotency

When multiple `@ControllerAdvice` / `RequestBodyAdvice` / `ResponseBodyAdvice` beans exist, ordering may depend on `@Order` and Spring sorting rules. Design transformations to be independent, or declare explicit ordering when truly required. Test the **actual runtime order** in your version; do not assume a fixed classpath scan order.

Make transformations **idempotent** if the same policy might run more than once. For a JSON envelope, check for `ApiEnvelope` before wrapping or restrict to a single marker/handler. For request normalization, `strip` is idempotent for that operation, though the original unstripped input string is lost—document this clearly in the contract.

### 7.9. Null Bodies, HEAD, 204, and 304

When returning `null` or a bodyless response, forcing an envelope can violate HTTP semantics. In particular, `204 No Content` and `304 Not Modified` must not carry JSON payloads; `HEAD` returns metadata like `GET` without transmitting a response body. Respect status codes, HTTP methods, and special output paths.

Advice hooks may still be consulted on certain `null` branches depending on implementation, but do not rely on them to synthesize bodies for contentless responses. In the example, `if (body == null) return null` preserves the no-body contract.

## 8. When to Use Another Mechanism?

| Specific Problem | Usually Better-Suited Mechanism |
| --- | --- |
| Reading/writing a new body format (binary/protocol) | Narrowly scoped `HttpMessageConverter<T>` restricted by type and media type |
| Customizing how Jackson serializes/deserializes JSON | Jackson `ObjectMapper`, custom serializer/deserializer, `@Json*` |
| Adding a standard response shape to a single endpoint | Return `ResponseEntity<ApiEnvelope<T>>` or an explicit envelope DTO |
| Standardizing errors across controllers | `@RestControllerAdvice` + `@ExceptionHandler` / `ResponseEntityExceptionHandler` |
| Authentication, authorization | Spring Security filters and application services/policies |
| Cross-cutting tracing/headers around every HTTP request | Servlet `Filter` or `HandlerInterceptor` depending on requirements |
| Reading request metadata only and setting request attributes | `HandlerInterceptor` or scoped service |
| Binding query/form params into objects | `@ModelAttribute` + `WebDataBinder`, converters/formatters/validators |
| Streaming downloads/uploads | `Resource`, multipart support, `StreamingResponseBody`, or dedicated I/O |
| Applying an envelope to a group of JSON APIs | `ResponseBodyAdvice` with opt-in and converter guards, after defining schema |
| Adjusting object after JSON parse before `@Valid` | `RequestBodyAdvice.afterBodyRead`, only for explicit DTOs/policies |

Base your decision on **purpose and intervention timing**: raw bytes before routing, object after conversion, response DTO before serialization, or exception response. Each point has its own metadata and limits.

## 9. Common Errors and How to Investigate Them

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| `afterBodyRead` does not run | `supports=false`, controller does not use `@RequestBody`/`HttpEntity`, empty body, or converter threw error | Check parameter, converter, marker, `handleEmptyBody` branch, and exceptions |
| Advice not detected by Spring | Missing `@ControllerAdvice`, package outside component scan, wrong `assignableTypes` scope | Check annotations, component scan, handler class |
| `ClassCastException` while writing response | `ResponseBodyAdvice` changed body to a type incompatible with the chosen converter | Check `selectedConverterType`, `selectedContentType`, and return type |
| JSON still fails with `400` before controller | Jackson failed to parse, missing body, validation failed | Distinguish conversion exceptions from constraint violations |
| Text gets wrapped into an object | `supports` returned true too broadly, missing converter/marker guard | Restrict to Jackson JSON DTO endpoints |
| Another endpoint suddenly changes JSON schema | Global advice applied too broadly | Use opt-in annotations, `@ControllerAdvice` scoping, and contract tests |
| Response wrapped twice | Multiple advices, or handled in both controller and advice | Assign envelope ownership to one place, check wrapper type |
| Wrong headers after changing payload | Incompatible `Content-Type`, length, encoding, ETag | Do not alter raw bytes arbitrarily; verify response wire format |
| Large upload runs server out of memory | `readAllBytes()`, global body buffering | Enforce size limits and choose streaming/multipart properly |
| Advice header appears but response is wrong | Exception, already-committed response, or converter write failed | Check stack traces and write/commit timing |
| Validation does not see original value | `afterBodyRead` mutated/replaced the DTO | Document normalization in contract, test before and after values |
| Error response turned into HTTP 200 | Global envelope logic interfered with status/exception | Preserve error contract and HTTP status, separate exception handling |

A practical investigation workflow:

1. Record request `method`, URL, `Content-Type`, `Accept`, and response status; never log secrets.
2. Confirm the mapping matched and the argument actually went through a converter.
3. Inspect `supports` on request/response advices and which converter was chosen.
4. Check whether the converter parsed the object or threw an error; inspect Bean Validation afterward.
5. Compare the object returned by the controller with the object handed to the converter by advice.
6. Inspect raw response headers/body, including empty bodies, binary, `204`, and error responses.
7. Test **non-opt-in** endpoints to detect unintended side effects.

## 10. Design Criteria for a Shared Advice

Before introducing a shared advice into an application with multiple modules/controllers, confirm:

- **Contract:** Which APIs have published input normalization or output envelopes?
- **Scope:** Which annotations/controllers/DTOs/media types opt in? Are text, HTML, files, and streaming excluded?
- **Converter:** Do bodies before and after transformation remain compatible with the selected converter?
- **Validation:** Does modification occur before or after constraint checks; are empty, null, and malformed values tested?
- **Error path:** Are statuses and schemas preserved for validation errors, authorization errors, and server errors?
- **Transport:** Are headers, charset, content length, cache validators, and signatures preserved?
- **Observability:** Are errors and latency measured without logging sensitive payloads?
- **Concurrency:** Is the advice stateless or thread-safe?
- **Regression tests:** Are both opted-in and non-opted-in endpoints tested across JSON/string/binary/null, for both success and failure?
- **Ownership:** Does a single place own normalization/wrapping, avoiding doing it in both controller and advice?

You do not need to implement every kind of hook. In many systems, **explicit DTOs + validation + controllers returning `ResponseEntity<ApiResponse<T>>`** are sufficient, easy to observe, and have clear contracts. Use advice only when the reuse benefit genuinely outweighs the cost of implicit framework-step transformations.

## 11. Self-Check Questions

1. Does `RequestBodyAdvice.afterBodyRead` run before or after JSON deserialization? Typically before or after `@Valid`?
2. Do missing bodies and malformed JSON always call `afterBodyRead`? Why or why not?
3. Why is a `ResponseBodyAdvice.supports` condition based solely on `@RestController` too broad?
4. Does Spring re-select `HttpMessageConverter` after `beforeBodyWrite` returns an object of a different type?
5. For a method returning `String` using `StringHttpMessageConverter`, why can wrapping it in an `Envelope<String>` record fail?
6. When should you use a `Filter` instead of `RequestBodyAdvice`?
7. If an API returns `204 No Content`, should you force `{"data":null}` into the response?
8. If a request carries an HMAC signature over raw bytes, how does trimming before signature verification affect it?
9. Why doesn't a `@ControllerAdvice` used for body processing automatically standardize responses from every `@ExceptionHandler`?
10. Why must you test endpoints that do not opt into advice when rolling out a new policy?

**Guidance:** (1) After deserialization, before validation. (2) Empty bodies go through `handleEmptyBody`; malformed JSON can fail before `afterBodyRead`. (3) Because controllers can return JSON, strings, binaries, and streams with different converters/contracts. (4) Do not rely on converter selection re-running. (5) The converter may expect a `String`. (6) When raw HTTP processing is needed at the Servlet layer before the MVC pipeline. (7) No, respect bodyless statuses. (8) Raw bytes change, so the signature no longer matches. (9) Exceptions have their own return handlers, statuses, and contracts. (10) To catch cases where advice accidentally alters other APIs.

## 12. References

- [Spring Framework 6.1 — RequestBodyAdvice Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/RequestBodyAdvice.html)
- [Spring Framework 6.1 — RequestBodyAdviceAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/RequestBodyAdviceAdapter.html)
- [Spring Framework 6.1 — ResponseBodyAdvice Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseBodyAdvice.html)
- [Spring Framework 6.1 — RequestResponseBodyMethodProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/RequestResponseBodyMethodProcessor.html)
- [Spring Framework — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html)
- [Spring Framework — @ControllerAdvice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html)
- [Spring Framework — HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)

This lesson describes the mechanism for Spring MVC 6.1 with runnable examples pinned to Spring Boot 3.3.5. When upgrading major Spring versions, check the corresponding signatures and pipeline before copying advice into production.
