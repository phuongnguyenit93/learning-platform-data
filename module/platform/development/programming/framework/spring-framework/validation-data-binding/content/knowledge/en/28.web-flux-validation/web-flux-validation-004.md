# @Valid or @Validated with Request Objects in Spring WebFlux

## 1. The Problem: Request Bound, but Is the Data Valid?

With Spring WebFlux, a client may send JSON to create a registration:

```http
POST /tickets/sync HTTP/1.1
Content-Type: application/json

{
  "title": "",
  "copies": 0,
  "owner": {"email": ""}
}
```

This JSON can be decoded into a Java object, yet **it fails the data contract**: blank title, copies below 1, and empty registrant email. Successfully reading JSON does not mean validation succeeded.

Spring WebFlux can apply **Jakarta Validation** when a controller declares:

```java
@PostMapping("/tickets")
public Mono<TicketView> create(
        @Valid @RequestBody TicketRequest request) {
    // ...
}
```

or use Spring `@Validated` to select validation groups:

```java
@PostMapping("/tickets/publish")
public Mono<TicketView> publish(
        @Validated(Publish.class)
        @RequestBody TicketRequest request) {
    // ...
}
```

The snippets above only illustrate signatures; `TicketRequest`, `TicketView`, and `Publish` must be defined. They help answer key questions:

- How do `@Valid` and `@Validated` compare and differ?
- Should annotations go **on the request parameter**, on fields/record components, or on the controller class?
- How do validation timing and error catching change between `@RequestBody TicketRequest` and `@RequestBody Mono<TicketRequest>`?
- When is the error `WebExchangeBindException` vs `HandlerMethodValidationException`?
- How are `@ModelAttribute`, `@RequestPart`, `BindingResult`, or groups used?
- How do you test with `WebTestClient` to distinguish JSON parsing, missing body, invalid fields, and method constraints?

**Scope:** Spring WebFlux on the reactive stack, Java 17+, Spring Framework 6.1+/6.2.x, and Jakarta Validation (`jakarta.validation.*`); runnable example uses Spring Boot 3.5.6. Reactor's `Mono`/`Flux` are the publisher types; do not use Servlet MVC's `MockMvc` or `MultipartFile` to replace WebFlux APIs.

## 2. Three Distinct Layers: Decode, Binding, and Validation

A request body passes through this conceptual flow:

```text
HTTP request
    |
    v
Router/DispatcherHandler (WebFlux annotated controller)
    |
    v
HttpMessageReader reads JSON per Content-Type
    |
    v
Instantiate TicketRequest via Jackson
    |
    v
Jakarta Validation if parameter has @Valid/@Validated
    |
    +-- valid --> invoke handler (or emit value on Mono)
    |
    +-- invalid --> WebExchangeBindException (typically HTTP 400)
    |
    v
Handler returns Mono/Flux/value
    |
    v
Response writer
```

Three error categories to separate clearly:

1. **Read/binding failure:** malformed JSON, unconvertible type, missing body, unsupported content type. This usually belongs to decoding errors / `ServerWebInputException` or other WebFlux input errors; it does not necessarily produce a `ConstraintViolation`.
2. **Request object validation failure:** JSON decoded cleanly, but `@NotBlank`, `@Min`, `@NotNull`, `@Valid` cascade, etc. detect violations. For standard individual argument validation, WebFlux raises `WebExchangeBindException`.
3. **Method validation failure:** A direct `@Constraint` is present on a handler parameter or return value, e.g., `@Min(1) @RequestParam int copies`. WebFlux's built-in method validation may handle the whole method and raise `HandlerMethodValidationException`.

**Important:** Both validation exception types can result in status **400** for invalid input, yet their mechanisms and result structures differ. If a constraint sits on the handler's return value, a postcondition violation should not be turned into a 400 client error.

## 3. `@Valid` and `@Validated`: Nature, Placement, and Groups

### 3.1. `@Valid` belongs to Jakarta Validation

Standard imports for Spring Boot 3+:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
```

`@Valid` requests **cascaded validation** into an object. Spring WebFlux recognizes `@Valid` on a request argument to trigger validation after deserialization/binding. Specific rules reside on the DTO type:

```java
public record CreateUser(
        @NotBlank String name,
        @Min(18) int age) {
}
```

If a controller has `@Valid @RequestBody CreateUser request`, the provider evaluates `name` and `age`. `@Valid` is not `@NotNull`: `@Valid` itself has no message, min/max, or validator enforcing "object must be present".

With nested DTOs:

```java
public record Address(@NotBlank String city) {}

public record CreateUser(
        @NotBlank String name,
        @Valid @NotNull Address address) {}
```

`@NotNull` requires `address` to be non-null; `@Valid` descends into `Address.city`. Placing `@Valid` without `@NotNull` skips a null property during cascade (if business rules forbid null, add a separate constraint).

### 3.2. Spring's `@Validated` can select groups

Import:

```java
import org.springframework.validation.annotation.Validated;
```

`@Validated` on a **request argument** also triggers validation while supporting group/hint selection:

```java
@PostMapping("/publish")
public Mono<ResponseEntity<?>> publish(
        @Validated(Publish.class)
        @RequestBody ArticleRequest body) {
    // ...
}
```

Custom group definition example:

```java
public interface Publish {}

public record ArticleRequest(
        @NotBlank String title,
        @NotBlank(groups = Publish.class) String reference) {}
```

If only `Publish.class` is requested, the `@NotBlank` constraint on `title` (which belongs to `Default`) **does not run automatically**, unless group inheritance or a sequence is configured. This is a common pitfall when first learning groups.

To enforce both basic rules and publish-step rules:

```java
@Validated({Default.class, Publish.class})
@RequestBody ArticleRequest body
```

importing `jakarta.validation.groups.Default` and `Publish` in scope. `@Validated` is not "stronger" than `@Valid` in constraint count; it lets you **select groups**.

### 3.3. Do not confuse parameter-level `@Validated` with class-level AOP

```java
@RestController
@Validated
class UserController {
    // ...
}
```

Placing `@Validated` **on the controller class** has a different meaning: when Spring configures `MethodValidationPostProcessor`, the controller may undergo method validation via an **AOP proxy**. With Spring Framework 6.1+'s built-in handler method validation, Spring docs recommend **omitting class-level `@Validated` from controllers** when using WebFlux's integrated method validation mechanism.

Conversely, `@Validated(Create.class)` **solely on `@RequestBody`** selects DTO validation groups and does not mean creating an AOP proxy. Do not confuse this with `@Service @Validated` in the service layer.

## 4. Choosing the Right Request Argument in WebFlux

### 4.1. `@Valid @RequestBody Dto` (direct object)

```java
@PostMapping("/sync")
public Mono<String> sync(
        @Valid @RequestBody TicketRequest request) {

    return Mono.just(request.title());
}
```

Spring WebFlux reads the request body via `HttpMessageReader` (usually JSON/Jackson), instantiates the object, and validates constraints before invoking the handler under non-reactive argument resolution. Invalid data typically produces `WebExchangeBindException`, defaulting to HTTP 400. Returning `Mono<String>` **does not force** the request parameter to be `Mono<Dto>`.

Advantage: clean signature, convenient when business logic is straightforward. Note: parsing/binding to obtain `Dto` happens before handler invocation; the controller cannot use operators on the request body to catch errors that already occurred earlier.

### 4.2. `@Valid @RequestBody Mono<Dto>` (request publisher)

```java
@PostMapping("/reactive")
public Mono<String> reactive(
        @Valid @RequestBody Mono<TicketRequest> ticketMono) {

    return ticketMono.map(TicketRequest::title)
            .onErrorResume(WebExchangeBindException.class,
                    ex -> Mono.just("invalid"));
}
```

WebFlux supports reading the body as a reactive type. Under this declaration, decoding/validation can emit errors **inside the publisher**; the handler can intercept them with `onErrorResume` or other operators, provided the chain **is returned** and subscribed properly by the runtime.

**Never call `.block()`** inside a WebFlux handler just to extract the DTO: doing so can block the event loop, hurt throughput, or cause runtime failures. Use `map`/`flatMap`/`onErrorResume` to compose asynchronous logic. `@Valid` remains effective on a `Mono<Dto>` argument under WebFlux's request binding contract; the major difference is **how errors propagate**.

Scope note: request-body validation examples mainly target a single request DTO. For `Flux<Dto>`/JSON streaming or per-element collection constraints, verify exact message reader and validator behavior for your version; do not assume `List<@Valid Dto>` or every `Flux` element is validated identically across all configurations.

### 4.3. `@Valid @ModelAttribute Dto` (form/query binding)

```java
@PostMapping(path = "/form",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public Mono<ResponseEntity<?>> form(
        @Valid @ModelAttribute TicketForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return Mono.just(ResponseEntity.badRequest().build());
    }
    return Mono.just(ResponseEntity.ok().build());
}
```

`@ModelAttribute` in WebFlux binds form fields, query parameters, and relevant request values via `WebDataBinder`. `BindingResult` sits **immediately after** the validated object, allowing the controller to handle errors **instead of throwing an exception**. With `@ModelAttribute Mono<TicketForm>`, errors must be handled via the publisher rather than placing `BindingResult` next to a reactive wrapper.

Since `TicketForm` is not yet defined here, this is an illustrative fragment. The full runnable section provides a real `TicketForm` class.

### 4.4. `@Valid @RequestPart Dto` (JSON part of multipart)

```java
@PostMapping(path = "/multipart",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<String> multipart(
        @Valid @RequestPart("metadata") Metadata metadata,
        @RequestPart("file") FilePart file) {

    return Mono.just(metadata.label());
}
```

Use `@RequestPart` when a client sends a `metadata` part with `Content-Type: application/json` alongside a file part. WebFlux uses `FilePart`/`Part`, **not Servlet MVC's `MultipartFile`**. `@Valid` on `metadata` runs validation after conversion. This is an illustrative fragment; `Metadata` must be defined and `org.springframework.http.codec.multipart.FilePart` must be imported.

Do not put `@NotBlank` directly on `FilePart`: `@NotBlank` is for `CharSequence`. To enforce file size limits or inspect content, build a dedicated reactive verification step and configure appropriate decoder/upload limits.

## 5. Quick Selection Table

| Input Data | Appropriate Declaration | Validation Mechanism |
| --- | --- | --- |
| Single JSON DTO | `@Valid @RequestBody CreateDto dto` | Bean Validation on DTO before invocation |
| Single JSON DTO read reactively | `@Valid @RequestBody Mono<CreateDto> dtoMono` | Validation when publisher is consumed; catch `WebExchangeBindException` via operators |
| JSON DTO with groups | `@Validated({Default.class, Publish.class}) @RequestBody CreateDto` | Bean Validation with selected groups |
| Form/query object | `@Valid @ModelAttribute FormDto` | WebDataBinder + Bean Validation |
| Form with in-handler error handling | `@Valid @ModelAttribute FormDto, BindingResult errors` | Local; `BindingResult` immediately after DTO |
| JSON part of multipart | `@Valid @RequestPart("metadata") MetaDto` | Part converter + Bean Validation |
| Query scalar with direct constraint | `@RequestParam @Min(1) int count` | WebFlux built-in method validation (6.1+) |
| Constraints only on DTO fields, no `@Valid` on argument | `@RequestBody CreateDto dto` | Do not expect automatic Bean Validation from field annotations alone |
| Service method managed by Spring AOP | `@Service @Validated` with method constraints | Proxy method validation, not request argument resolver |

This table describes scenarios without class-level `@Validated` on the controller and with a Jakarta Validation provider present. Mixed constraints, `BindingResult`, or decoding errors can alter the actual exception raised.

## 6. What Happens When a Request Misses a Field or Contains Blank Values?

Consider the DTO:

```java
public record TicketRequest(
        @NotBlank String title,
        @Min(1) int copies) {}
```

Corresponding JSON requests:

| JSON | Java Data After Decode | Result |
| --- | --- | --- |
| `{"title":"Book","copies":2}` | title = `"Book"`, copies = `2` | Valid |
| `{"title":"","copies":2}` | title = `""` | `@NotBlank` fails |
| `{"title":"   ","copies":2}` | title is all whitespace | `@NotBlank` fails |
| `{"copies":2}` | title = `null` | `@NotBlank` fails |
| `{"title":"Book"}` | copies = `0` for primitive `int` | `@Min(1)` fails |
| `{"title":"Book","copies":0}` | copies = `0` | `@Min(1)` fails |
| `{"title":"Book","copies":"abc"}` | Cannot convert string to `int` | Decoding/binding error, not a plain `@Min` violation |
| Malformed JSON syntax | Cannot instantiate object | Request read error, never reaches constraints |

**Note:** The table entry for primitive `int` reflects typical JSON binding behavior when a numeric field is omitted, though Jackson settings, constructors, primitive-null handling, and custom deserializers can change how errors are reported. When you need to distinguish "omitted `copies`" from "sent `copies=0`", use `Integer` + `@NotNull` and `@Min(1)`, or enforce an explicit parsing policy.

`@Min`/`@Size` generally treat `null` as valid: combine with `@NotNull` to reject missing values. `@NotBlank` already forbids both `null` and whitespace-only strings. Do not substitute `@NotEmpty` for `@NotBlank` if whitespace-only strings must be rejected.

### 6.1. Cascading with nested request DTOs

```java
public record Owner(@NotBlank String email) {}

public record TicketRequest(
        @NotBlank String title,
        @NotNull @Valid Owner owner) {}
```

- `@NotNull` on `owner` catches a missing object.
- `@Valid` on `owner` triggers deep validation of `Owner.email`.
- `@NotBlank` on `Owner.email` catches empty/whitespace strings.
- If `@NotBlank` is placed on `Owner` while `@Valid` is forgotten on the parent property, validation starting from `TicketRequest` will not cascade into the nested object.

### 6.2. Collections and elements

```java
public record BulkRequest(
        @NotEmpty List<@Valid TicketRequest> tickets) {}
```

The provider checks that the `tickets` container is non-empty (`@NotEmpty`) and, due to `@Valid` on the type argument, cascades into each `TicketRequest`. An appropriate collection value extractor is required (modern Jakarta Validation providers include built-in extractors for `List`). To **forbid null elements**, add `@NotNull` to the type argument: `List<@NotNull @Valid TicketRequest>`.

**Do not automatically equate** `@Valid List<TicketRequest>` with every `List<@Valid TicketRequest>` scenario: annotation placement, container extraction, validation groups, and whether the framework chooses method validation must all be checked per DTO/source/version. In practice, prefer an explicit wrapper request DTO, especially when an API needs multiple fields and collection-level constraints.

## 7. Standalone Runnable Example: Spring Boot 3.5.6 + WebFlux + Java 17

The following example demonstrates five scenarios:

1. **Individual DTO validation:** `POST /tickets/sync` uses `@Valid @RequestBody TicketRequest`.
2. **Validation groups:** `POST /tickets/publish` uses `@Validated({Default.class, Publish.class})`.
3. **Reactive body validation:** `POST /tickets/reactive` accepts `Mono<TicketRequest>` and handles validation errors in the reactive chain.
4. **Direct method constraint:** `GET /tickets/count?n=0` uses `@Min` on a scalar query parameter, showing the exception difference.
5. **Form binding:** `POST /tickets/form` uses `@ModelAttribute` + `BindingResult`.

The application returns sample data only, without accessing a database or creating transactions. The goal is to clarify the **validation boundary**, not to design a full ticketing system.

### 7.1. Directory structure

```text
webflux-request-validation/
├── pom.xml
├── src/main/java/demo/webflux/
│   ├── WebFluxValidationApplication.java
│   ├── TicketRequest.java
│   ├── TicketForm.java
│   ├── TicketController.java
│   └── ValidationErrorAdvice.java
└── src/test/java/demo/webflux/
    └── TicketControllerTest.java
```

### 7.2. `pom.xml` file

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-request-validation</artifactId>
    <version>1.0-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-validation</artifactId>
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

**Explanation:**
- Use only `spring-boot-starter-webflux`; **do not** add `spring-boot-starter-web` to the same demo. When both MVC and WebFlux starters are present, Spring Boot normally picks the Servlet MVC application type.
- `spring-boot-starter-validation` provides the Jakarta Validation provider (typically Hibernate Validator); without a provider, do not assume validation annotations are enforced.
- `spring-boot-starter-test` and `reactor-test` support JUnit/Spring Test and reactive testing. All transitive versions are managed by the Boot parent.
- Spring Boot `3.5.6` is a specific released version in the Boot 3.5 line using Spring Framework 6.2.x, not necessarily the newest release at the time you read this.

### 7.3. `WebFluxValidationApplication.java` file

```java
package demo.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxValidationApplication.class, args);
    }
}
```

### 7.4. `TicketRequest.java` file

```java
package demo.webflux;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record TicketRequest(
        @NotBlank(message = "title.blank")
        String title,

        @Min(value = 1, message = "copies.min")
        int copies,

        @NotNull(message = "owner.required")
        @Valid
        Owner owner,

        @NotBlank(
                groups = Publish.class,
                message = "reference.blank")
        String reference) {

    public interface Publish {}

    public record Owner(
            @NotBlank(message = "owner.email.blank")
            String email) {}
}
```

- `title`, `copies`, and `owner` belong to the `Default` group.
- `reference` belongs to `TicketRequest.Publish` and only runs when that group is requested.
- `Owner` is a nested DTO; `@Valid` on the parent triggers checking `email`.
- `@NotNull` on `owner` enforces object presence; `@Valid` alone does not replace `@NotNull`.

### 7.5. `TicketForm.java` file

```java
package demo.webflux;

import jakarta.validation.constraints.NotBlank;

public class TicketForm {

    @NotBlank(message = "title.blank")
    private String title;

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
```

This DTO is for `application/x-www-form-urlencoded`; Spring WebFlux can instantiate it via the default constructor and bind the form field `title` using the setter.

### 7.6. `TicketController.java` file

```java
package demo.webflux;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.groups.Default;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.support.WebExchangeBindException;
import reactor.core.publisher.Mono;

import java.util.Map;

@RestController
@RequestMapping("/tickets")
public class TicketController {

    // 1. @Valid: validate the Default group of the request DTO.
    @PostMapping(
        path = "/sync",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Map<String, Object>> sync(
            @Valid @RequestBody TicketRequest body) {

        return Mono.just(Map.of(
                "title", body.title(),
                "copies", body.copies()));
    }

    // 2. @Validated: include the Publish group alongside Default.
    @PostMapping(
        path = "/publish",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Map<String, Object>> publish(
            @Validated({Default.class, TicketRequest.Publish.class})
            @RequestBody TicketRequest body) {

        return Mono.just(Map.of(
                "reference", body.reference(),
                "title", body.title()));
    }

    // 3. Accept Mono<DTO>, catch WebExchangeBindException in the chain.
    @PostMapping(
        path = "/reactive",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<Map<String, Object>>> reactive(
            @Valid @RequestBody Mono<TicketRequest> bodyMono) {

        return bodyMono
                .map(body -> ResponseEntity.ok(
                        Map.<String, Object>of("title", body.title())))
                .onErrorResume(
                        WebExchangeBindException.class,
                        error -> Mono.just(
                                ResponseEntity.badRequest()
                                        .body(Map.<String, Object>of(
                                                "error", "reactive.invalid"))));
    }

    // 4. Direct @Min constraint: handler method validation.
    @GetMapping("/count")
    public Mono<Map<String, Integer>> count(
            @RequestParam("n") @Min(1) int n) {

        return Mono.just(Map.of("n", n));
    }

    // 5. @ModelAttribute + BindingResult handles errors locally.
    @PostMapping(
        path = "/form",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public Mono<ResponseEntity<Map<String, Object>>> form(
            @Valid @ModelAttribute TicketForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return Mono.just(ResponseEntity.badRequest()
                    .body(Map.<String, Object>of(
                            "error", "form.invalid")));
        }

        return Mono.just(ResponseEntity.ok(
                Map.<String, Object>of("title", form.getTitle())));
    }
}
```

The code above **does not place `@Validated` on the controller class**, letting WebFlux 6.2 handle method validation natively on `count()`. The `@Validated` annotation on **`publish()`'s parameter** only selects validation groups for `TicketRequest`.

In `reactive()`, `Mono<TicketRequest>` holds the payload after deserialization/validation. The `onErrorResume(WebExchangeBindException.class, ...)` operator returns a clear error without blocking the event loop. In `sync()`/`publish()`, DTO resolution happens before the handler is invoked, so the global exception handler receives the error.

### 7.7. `ValidationErrorAdvice.java` file

```java
package demo.webflux;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

import java.util.Map;

@RestControllerAdvice
public class ValidationErrorAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<Map<String, String>> invalidRequest(
            WebExchangeBindException error) {

        return ResponseEntity.badRequest()
                .body(Map.of("error", "request.invalid"));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<Map<String, String>> invalidMethod(
            HandlerMethodValidationException error) {

        return ResponseEntity.status(error.getStatusCode())
                .body(Map.of("error", "method.invalid"));
    }
}
```

The advice illustrates both validation exception types:
- `WebExchangeBindException` for validation of a single request DTO; the example returns `{"error":"request.invalid"}`.
- `HandlerMethodValidationException` when the direct `@Min` constraint triggers built-in method validation; `getStatusCode()` distinguishes invalid input (usually 400) from return contract violations (potentially 500).

The messages `"request.invalid"` and `"method.invalid"` are **application-chosen strings**, not mandatory Spring default bodies. Real applications should return structured field errors/`ProblemDetail` with stable codes, without exposing sensitive data in responses.

## 8. Comprehensive Testing with `WebTestClient`

Spring WebFlux uses `WebTestClient` to send requests and verify responses. You can test against a mock application context without opening a real HTTP port using `@SpringBootTest` combined with `@AutoConfigureWebTestClient`.

### 8.1. `TicketControllerTest.java` file

```java
package demo.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest
@AutoConfigureWebTestClient
class TicketControllerTest {

    @Autowired
    WebTestClient client;

    private static final String VALID = """
            {
              "title": "Book",
              "copies": 2,
              "owner": {"email": "a@example.com"}
            }
            """;

    @Test
    void validDtoIsAccepted() {
        client.post().uri("/tickets/sync")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(VALID)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Book")
                .jsonPath("$.copies").isEqualTo(2);
    }

    @Test
    void blankTitleIsRejected() {
        client.post().uri("/tickets/sync")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"title":"  ","copies":2,
                         "owner":{"email":"a@example.com"}}
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("request.invalid");
    }

    @Test
    void quantityBelowMinimumIsRejected() {
        client.post().uri("/tickets/sync")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"title":"Book","copies":0,
                         "owner":{"email":"a@example.com"}}
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("request.invalid");
    }

    @Test
    void nestedOwnerMustBeValid() {
        client.post().uri("/tickets/sync")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"title":"Book","copies":1,
                         "owner":{"email":""}}
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("request.invalid");
    }

    @Test
    void missingOwnerIsRejected() {
        client.post().uri("/tickets/sync")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"title":"Book","copies":1}
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("request.invalid");
    }

    @Test
    void defaultGroupDoesNotRequirePublishReference() {
        client.post().uri("/tickets/sync")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(VALID)
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void publishGroupRequiresReference() {
        client.post().uri("/tickets/publish")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(VALID)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("request.invalid");
    }

    @Test
    void publishWithReferenceIsAccepted() {
        client.post().uri("/tickets/publish")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"title":"Book","copies":2,
                         "owner":{"email":"a@example.com"},
                         "reference":"T-100"}
                        """)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.reference").isEqualTo("T-100");
    }

    @Test
    void reactiveBodyHandlesInvalidRequestInPipeline() {
        client.post().uri("/tickets/reactive")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"title":"","copies":2,
                         "owner":{"email":"a@example.com"}}
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("reactive.invalid");
    }

    @Test
    void reactiveBodyAcceptsValidRequest() {
        client.post().uri("/tickets/reactive")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(VALID)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Book");
    }

    @Test
    void methodConstraintUsesDifferentValidationBranch() {
        client.get().uri("/tickets/count?n=0")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("method.invalid");
    }

    @Test
    void methodConstraintAcceptsValidQuery() {
        client.get().uri("/tickets/count?n=2")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.n").isEqualTo(2);
    }

    @Test
    void formBindingResultHandlesBlankTitle() {
        client.post().uri("/tickets/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("title", " "))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("form.invalid");
    }

    @Test
    void formAcceptsValidTitle() {
        client.post().uri("/tickets/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("title", "Book"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Book");
    }
}
```

### 8.2. Running tests

```bash
mvn test
```

**Expected result:** 14 test passes (in a Maven/JDK 17 environment able to download dependencies). Test names directly describe each scenario; test execution order is not guaranteed and should not be asserted via fixed stdout.

| Test Group | What It Proves |
| --- | --- |
| `validDtoIsAccepted` | `@Valid` on request object accepts valid input |
| `blankTitleIsRejected`, `quantityBelowMinimumIsRejected` | Field constraints run after JSON decode |
| `nestedOwnerMustBeValid`, `missingOwnerIsRejected` | `@Valid` cascade and `@NotNull` fulfill their respective roles |
| `defaultGroupDoesNotRequirePublishReference` | `Default` does not automatically run `Publish` group constraints |
| `publishGroupRequiresReference`, `publishWithReferenceIsAccepted` | `@Validated` selects both Default and Publish |
| Two reactive body tests | Validation errors on `Mono<DTO>` can be handled via `onErrorResume` |
| Two direct `@Min` tests | Handler method validation uses its own exception branch |
| Two form tests | `@ModelAttribute` + `BindingResult` handles errors locally |

The codes `request.invalid`, `method.invalid`, `reactive.invalid`, and `form.invalid` are designed to clearly distinguish **error paths** when inspecting the JSON response.

### 8.3. Why use `WebTestClient` instead of `MockMvc`?

`WebTestClient` is compatible with reactive WebFlux and supports asserting status, headers, JSONPath, body, and publisher behavior. `MockMvc` belongs to Spring MVC Servlet test infrastructure. In a Spring Boot project with both MVC and WebFlux dependencies, the configured application type may no longer be reactive; to ensure this example runs true WebFlux, declare only `spring-boot-starter-webflux` in the application scope.

## 9. Trying Requests with `curl`

Start the server:

```bash
mvn spring-boot:run
```

### 9.1. Valid input with `@Valid`

```bash
curl -i -X POST \
  http://localhost:8080/tickets/sync \
  -H 'Content-Type: application/json' \
  -d '{"title":"Book","copies":2,"owner":{"email":"a@example.com"}}'
```

Expected HTTP **200** and body:

```json
{"title":"Book","copies":2}
```

### 9.2. Blank title

```bash
curl -i -X POST \
  http://localhost:8080/tickets/sync \
  -H 'Content-Type: application/json' \
  -d '{"title":"","copies":2,"owner":{"email":"a@example.com"}}'
```

Expected HTTP **400** and JSON:

```json
{"error":"request.invalid"}
```

`@NotBlank` on `title` fails; the global advice catches `WebExchangeBindException`. Removing `@Valid` from the controller argument would stop field validation from running on the standard request-object path.

### 9.3. `Publish` group and required `reference`

```bash
curl -i -X POST \
  http://localhost:8080/tickets/publish \
  -H 'Content-Type: application/json' \
  -d '{"title":"Book","copies":2,"owner":{"email":"a@example.com"}}'
```

Expected HTTP **400** because `@Validated({Default.class, Publish.class})` also evaluates `@NotBlank(groups=Publish.class)` on `reference`. Sending the same body to `/tickets/sync` is valid under `Default`.

### 9.4. Reactive request body with local error handling

```bash
curl -i -X POST \
  http://localhost:8080/tickets/reactive \
  -H 'Content-Type: application/json' \
  -d '{"title":"","copies":2,"owner":{"email":"a@example.com"}}'
```

Expected HTTP **400**, but the body is:

```json
{"error":"reactive.invalid"}
```

Reason: `bodyMono.onErrorResume(WebExchangeBindException.class, ...)` handles the error signal from the publisher. This is an application-level mapping, **not** something Spring WebFlux forces every controller to return.

### 9.5. Direct scalar constraint

```bash
curl -i 'http://localhost:8080/tickets/count?n=0'
```

Expected HTTP **400**, JSON:

```json
{"error":"method.invalid"}
```

With Spring WebFlux 6.2, `@Min(1)` placed directly on parameter `n` triggers **method validation** and the `HandlerMethodValidationException` branch. Looking only at status 400 does not tell you whether request-object validation or method validation ran.

## 10. Errors and Exceptions: Identifying the Right Source

### 10.1. `WebExchangeBindException`

Spring WebFlux typically raises `org.springframework.web.bind.support.WebExchangeBindException` when a request DTO is bound successfully but validation fails. This exception carries `BindingResult` with `FieldError` and `ObjectError`.

Example of specific error handling in `@RestControllerAdvice`:

```java
@ExceptionHandler(WebExchangeBindException.class)
public ResponseEntity<Map<String, Object>> errors(
        WebExchangeBindException exception) {

    var fields = exception.getFieldErrors().stream()
            .map(e -> Map.of(
                    "field", e.getField(),
                    "message", String.valueOf(e.getDefaultMessage())))
            .toList();

    return ResponseEntity.badRequest()
            .body(Map.of("errors", fields));
}
```

This is an **illustrative replacement** for the `invalidRequest()` handler in `ValidationErrorAdvice.java`; import Spring/Java collections as in context. Do not add a duplicate handler for the same exception type in the same controller advice. Do not expose raw `rejectedValue` in responses when it may contain sensitive data.

### 10.2. `HandlerMethodValidationException`

When a handler method has a `@Constraint` **directly** on a parameter or return value, Spring Framework 6.1+ built-in method validation may **supersede** individual argument validation, covering cascaded `@Valid` constraints as well. This produces `HandlerMethodValidationException`.

Example:

```java
@PostMapping("/mixed")
public Mono<String> mixed(
        @RequestParam("n") @Min(1) int n,
        @Valid @RequestBody TicketRequest body) {

    return Mono.just(body.title());
}
```

If `n=0` or the DTO is invalid, method validation can detect all applicable errors together. `@Valid` alone is **not** a direct constraint; it does not automatically switch a DTO-only handler to method validation.

`HandlerMethodValidationException` holds results per method parameter; you can iterate `getAllValidationResults()` or use a visitor by argument kind. Applications must distinguish input failures (usually 400) from return value failures (usually 500) to avoid returning misleading errors.

### 10.3. Decode/parse errors vs validation

| Input Data | Point of Failure | Typical Error Type |
| --- | --- | --- |
| Valid JSON, field `title=""` | Bean Validation | `WebExchangeBindException` if handler only needs argument validation |
| Direct `@Min(1)` on query parameter, n=0 | Handler method validation | `HandlerMethodValidationException` |
| Required `@RequestBody` with empty body | Request body resolution | `ServerWebInputException`/corresponding input error path |
| Malformed JSON structure | Jackson/HttpMessageReader | Input read error, typically `ServerWebInputException` |
| Unsupported HTTP `Content-Type` | HTTP message codec/content negotiation | `UnsupportedMediaTypeStatusException`, typically 415 |
| Form missing field with `@NotBlank` | DTO binding + validation | `WebExchangeBindException` or local `BindingResult` |
| Required `@RequestParam` missing | Argument resolution | Missing request value error, not an `@Min` violation |

**Do not write `@ExceptionHandler(ValidationException.class)` and return 400 for everything.** Some `ValidationException` subtypes indicate provider misconfiguration or backend contract errors, not bad request data.

## 11. `BindingResult`/`Errors` in WebFlux

### 11.1. With a non-reactive DTO argument

```java
@PostMapping("/form")
public Mono<ResponseEntity<?>> create(
        @Valid @ModelAttribute TicketForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return Mono.just(ResponseEntity.badRequest().build());
    }
    return Mono.just(ResponseEntity.ok().build());
}
```

This is an illustrative snippet. The validated object must appear **immediately before** `BindingResult`. The controller can inspect errors locally and choose a response instead of letting an exception escape. Using `@Valid @RequestBody Dto` followed immediately by `Errors` is also supported by WebFlux in appropriate cases; that DTO cannot be `Mono<Dto>`.

### 11.2. With reactive wrapper `Mono<Dto>`

Do not write signatures like:

```java
public Mono<?> bad(
        @Valid @RequestBody Mono<TicketRequest> ticket,
        BindingResult errors) {
    // Do not use BindingResult here as for a resolved DTO.
}
```

This is an **illustrative anti-pattern**, not code to put into a project. With a reactive request wrapper, decoding/validation is emitted asynchronously; a trailing `BindingResult` cannot represent "already resolved errors" when the method is invoked. Use `onErrorResume(WebExchangeBindException.class, ...)` or let the exception reach a global handler.

### 11.3. When method validation is enabled

If a handler has direct `@Constraint` annotations on one or more method parameters, Spring method validation can cooperate with `Errors`/`BindingResult`. However, the controller is only invoked if **all** validation errors belong to parameters that have an immediately following `Errors` to handle them. If an error occurs on another parameter lacking a local errors channel, `HandlerMethodValidationException` can be thrown.

Do not treat `BindingResult` as a "catch-all variable for every error in the method", and do not treat `BindingResult` behavior in AOP-proxied services as if it were the Spring WebFlux argument resolver contract.

## 12. When Are Custom Validation Groups Useful?

Example workflow for a post:

- **Draft:** requires title; reference code may be absent.
- **Publish:** additionally requires reference code, while still respecting basic rules.

In `TicketRequest`, the `reference` field declares:

```java
@NotBlank(
    groups = Publish.class,
    message = "reference.blank")
String reference
```

In `/sync`, which uses only `@Valid`, `Default` constraints run and `reference` is not required. The `/publish` endpoint uses:

```java
@Validated({Default.class, TicketRequest.Publish.class})
@RequestBody TicketRequest body
```

so both rule sets take effect together.

Do not assume `@Validated(Publish.class)` implies `Default`. If you want ordered validation where step 2 skips if step 1 fails, you can use Jakarta Validation **group sequences** (and understand group cascading rules). For a multi-state API, defining group interfaces is part of the validation contract; name groups after business lifecycle stages rather than controller classes.

### 12.1. Groups and nested objects

If the parent DTO has `@Valid Owner owner`, the provider cascades groups into the nested object per Jakarta Validation rules. In the example, both `Default` and `Publish` were selected. If only `Publish` is selected, `Owner`'s `Default` constraints do not run automatically. Group conversion via `@ConvertGroup` can be used to switch groups across a cascade edge, but add it only when clearly required and tested.

### 12.2. Groups do not replace authorization

Just because a request body uses `@Validated(Admin.class)` does not mean the caller has admin privileges. Validation checks **data**, while authorization checks **permissions**. Decisions like whether a user may publish must be enforced in the security/service layer rather than relying solely on validation groups.

## 13. WebFlux and Blocking Validation

**Spring WebFlux's non-blocking I/O does not turn all handler code into non-blocking code.**

Standard Bean Validation executes synchronously and suits fast constraints like `@NotBlank`, `@Size`, `@Min`, regex patterns, or in-memory field checks. However, a custom `ConstraintValidator` making blocking database or HTTP calls can stall the event loop if the provider executes it on the reactive request thread.

- Keep DTO-attached `ConstraintValidator` implementations **fast, non-blocking, and side-effect free**.
- Rules requiring asynchronous I/O (duplicate email in DB, permission checks via API, remaining quota) should run in reactive services using `Mono`/`Flux` and reactive repositories/clients.
- Never call `.block()` inside a `ConstraintValidator` or reactive handler to "fetch validation results".
- Do not confuse passing validation with transaction/business invariants: data may be syntactically valid yet invalid against current system state.

Illustrative example of an async business step after request-object validation:

```java
@PostMapping("/create")
public Mono<ResponseEntity<?>> create(
        @Valid @RequestBody Mono<TicketRequest> bodyMono) {

    return bodyMono
            .flatMap(service::checkAndSave)
            .map(saved -> ResponseEntity.ok().build());
}
```

This is a **non-standalone fragment**, assuming a reactive `service.checkAndSave(TicketRequest)` returning `Mono<?>`. The proper order is parse → DTO Bean Validation → business/authorization checks → persist. Add a dedicated `onErrorResume` for business errors if needed, without swallowing all error signals into a success response.

## 14. Configuring Providers and Custom Validators

### 14.1. Required dependencies

In Spring Boot 3.x, adding `spring-boot-starter-webflux` alone does not guarantee a Bean Validation provider is present. Therefore the example includes:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

This brings in the matching Hibernate Validator. When upgrading from Spring Boot 2.x, note that the namespace moved from `javax.validation.*` to `jakarta.validation.*`; do not mix the two annotation sets in Boot 3+.

### 14.2. Global and local configuration

Spring WebFlux supports configuring a global `Validator` via WebFlux config or a local validator via `@InitBinder` in a controller/`@ControllerAdvice`. Conceptual example:

```java
@InitBinder
public void initBinder(WebDataBinder binder) {
    binder.addValidators(new MyFastTicketValidator());
}
```

This is an illustrative fragment. `MyFastTicketValidator` must implement `org.springframework.validation.Validator`, with `supports(Class<?>)` returning true for accepted types and `validate(Object, Errors)` adding appropriate errors. Applying a validator to the wrong type can cause exceptions or unexpected validation behavior.

Do not replace the global Jakarta Validation provider just because one field needs a new check; consider a custom `@Constraint`/`ConstraintValidator` if it is a reusable data rule across multiple DTOs.

### 14.3. When to use programmatic validation?

Beyond controller annotations, you can inject `jakarta.validation.Validator` to validate DTOs in a layer outside the HTTP boundary:

```java
Set<ConstraintViolation<TicketRequest>> violations =
        validator.validate(request);

if (!violations.isEmpty()) {
    // Convert to a domain/API error per custom policy.
}
```

This is an illustrative fragment, assuming `validator` and `request` are provided. `Validator.validate(...)` returns a set of violations and **does not throw `WebExchangeBindException`**. That exception is created by Spring WebFlux's request binding integration; it is not an API output of Jakarta Validation itself.

## 15. Common Mistakes and Fixes

| Mistake | Why It Fails | How to Fix |
| --- | --- | --- |
| Putting `@NotBlank` in DTO but forgetting `@Valid`/`@Validated` on argument | Request object validation may not be triggered | Annotate the DTO argument in the right place |
| Importing `javax.validation.Valid` in Boot 3+ | Wrong API generation namespace | Use `jakarta.validation.Valid` |
| Using `@Validated(Publish.class)` assuming `Default` still always runs | Groups do not automatically include each other | Specify both `Default.class` and `Publish.class` when needed |
| Placing `@Valid` on parent DTO but forgetting `@Valid` on nested property | Provider is not instructed to cascade to child | Place `@Valid` on the edge that needs cascading |
| Putting only `@Valid` on nested child while expecting non-null enforcement | Null is skipped during cascade | Add `@NotNull` |
| Expecting `@Valid` alone to throw `HandlerMethodValidationException` | `@Valid` is not a direct `@Constraint` | Distinguish individual argument vs method validation |
| Adding `@Min` on `@RequestParam` while catching only `WebExchangeBindException` | Handler switches to method validation | Also handle `HandlerMethodValidationException` |
| Calling `.block()` to unwrap `Mono<T>` body in handler | Can block the event loop | Use `map`/`flatMap`/`onErrorResume` |
| Placing `BindingResult` after `Mono<Dto>` | Reactive body is not synchronously resolved | Catch errors in the reactive pipeline |
| Putting `@Validated` on controller class just to pick DTO groups | Can enable an AOP proxy for method validation | Put `@Validated(groups)` on the specific request argument |
| Using `MockMvc` to test a reactive WebFlux app | Testing the wrong stack | Use `WebTestClient` |
| Including both `spring-boot-starter-web` and `webflux` while thinking WebFlux runs | Boot usually picks Servlet MVC when both are present | Use only the WebFlux starter for a pure reactive app |
| Putting `@NotBlank` on numbers or complex DTOs | No validator exists for the target type | Use `@Min`, `@NotNull`, or a custom constraint |
| Treating malformed JSON as a Bean Validation violation | Decoding may fail before DTO instantiation | Separate parsing exceptions from validation exceptions |
| Calling blocking DB in custom `ConstraintValidator` | Can stall the event loop | Move I/O business checks to a reactive service |

## 16. WebFlux Request Validation Debug Checklist

1. **Check application type:** Are you truly running Spring WebFlux/reactive, or was the Servlet MVC starter accidentally added?
2. **Check dependencies:** Are `spring-boot-starter-validation` and a Jakarta Validation provider present?
3. **Check imports:** Do constraints and `@Valid` come from `jakarta.validation`?
4. **Check annotation placement:** Is `@Valid`/`@Validated` on the request argument, or only inside the DTO?
5. **Check request body:** Is the JSON valid, `Content-Type: application/json` accurate, and are fields decodable?
6. **Check nested constraints:** Is `@Valid` on the parent property and `@NotNull` wherever null must be rejected?
7. **Check groups:** Are you running `Default`, a custom group, or both? Does `@Validated(Group.class)` omit `Default`?
8. **Check parameter type:** Is the DTO a direct object or `Mono<Dto>`? If reactive, are publisher errors handled by the subscriber/handler?
9. **Check direct method constraints:** Are there `@Min`, `@NotBlank`, or return constraints? If so, account for `HandlerMethodValidationException`.
10. **Check class-level `@Validated`:** Did you accidentally trigger AOP method validation on the controller, causing unexpected exceptions?
11. **Check BindingResult:** Is the argument a non-reactive DTO with `BindingResult` immediately after it?
12. **Check exception advice:** Is an overly broad handler masking the real exception type or returning 400 for server return errors?
13. **Check non-blocking runtime:** Do any custom validators call a DB or `.block()`?
14. **Check tests:** Does `WebTestClient` actually exercise the WebFlux controller, asserting status and categorized errors rather than just a generic 400?

## 17. Reinforcement Exercises

1. Remove `@Valid` from `TicketController.sync` and send `title=""`. Compare with before removing the annotation and explain the validation path.
2. Send `owner=null`, then `owner={"email":""}`. Explain which constraint detects each case.
3. Use only `@Validated(TicketRequest.Publish.class)` on `publish`. Send a body with `title=""` and `reference="T-1"`; explain why `Default` constraints may not run.
4. Change `/reactive` from `Mono<TicketRequest>` to `TicketRequest` while keeping a similar `onErrorResume`. Why can you no longer handle argument resolver errors with an operator on a publisher that is no longer the argument?
5. Add `@NotBlank` directly on an `@RequestParam("code") String code` in `sync` (adjusted signature). Send an invalid JSON DTO; which branch will the validation exception take?
6. Write an `@RestControllerAdvice` returning `ProblemDetail` and a list of `FieldError` entries for `WebExchangeBindException`, while also classifying `HandlerMethodValidationException`.
7. Add an `@ModelAttribute` form with two fields `title` and `copies`; put `@Min(1)` on the form field. Use `WebTestClient` to test valid and invalid forms.
8. Try sending JSON with `copies="not-a-number"` to identify the parsing/binding exception rather than assuming it is an `@Min` failure.
9. Refactor a constraint validator calling a blocking repository into reactive service validation and compare execution timing.
10. Add `@RequestPart("metadata")` accepting `Metadata` alongside `FilePart`. Send valid and invalid JSON metadata; ensure Servlet `MultipartFile` is not used.
11. Add custom groups `Draft` and `Publish`, and experiment with `@GroupSequence` or `@ConvertGroup` when staged checks are needed.
12. Write tests distinguishing both WebFlux validation exceptions: invalid DTO argument vs invalid direct parameter constraint. Why might both return HTTP 400 while the error contract should still identify each type?

**Remember:**

- `@Valid` on a request DTO: triggers cascade/Bean Validation for the `Default` group.
- `@Validated(groups)` on a request DTO: triggers validation with your chosen groups/hints.
- `@RequestBody Mono<Dto>`: validation can emit errors inside the publisher, so handle them with reactive operators.
- `@ModelAttribute Dto + BindingResult`: handles binding/validation errors locally on the resolved argument.
- Direct `@Constraint` on method parameters/return values: can trigger **WebFlux method validation** and switch the exception to `HandlerMethodValidationException`.
- Class-level `@Validated` on a controller: differs from parameter-level groups and can enable an **AOP proxy**; it is not required for WebFlux built-in method validation to work.

## 18. Official Documentation

- [Spring Framework 6.2 — WebFlux `@RequestBody` and validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — WebFlux validation of handler methods](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Spring Framework 6.2 — WebFlux `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — WebFlux `@RequestPart` multipart](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Framework — Reactive WebFlux error responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html)
- [Spring Framework — `WebExchangeBindException` JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html)
- [Spring Framework — `HandlerMethodValidationException` JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring Boot 3.5 — Testing Spring Boot WebFlux with `WebTestClient`](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Jakarta Validation — Specification 3.0](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)