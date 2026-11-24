# Validating @RequestBody with @Valid and @Validated

**Module:** Spring Framework – reactive  
**Parent topic:** Binding and validation

## Learning objectives

After this lesson, you can:

1. Explain the processing chain from an HTTP JSON body through the message codec, Java object, and Jakarta Bean Validation in Spring WebFlux.
2. Use `@Valid` to trigger DTO validation and nested validation; use `@Validated` when you need to select a validation group.
3. Write semantically accurate constraints such as `@NotNull`, `@NotBlank`, `@NotEmpty`, `@Size`, `@Email`, `@Positive`, and `@Pattern`.
4. Distinguish `WebExchangeBindException` from `HandlerMethodValidationException` and request body read/decoding errors.
5. Return structured HTTP 400 errors, read field errors, and test with `WebTestClient`.
6. Handle nested DTOs, collections, validation groups, and cases that need a custom validator while keeping the reactive pipeline intact.

## 1. At which stage is the request body validated?

When a client sends JSON to a WebFlux endpoint, the request body must pass through these steps:

```text
HTTP request body (JSON bytes)
          |
          v
  HttpMessageReader / codec
          |
          v
  Deserialize into Java DTO
          |
          v
  Bean Validation (@Valid / @Validated)
          |
          +---- valid ----> Controller handles Mono/Flux
          |
          +---- invalid --> WebExchangeBindException
                                  |
                                  v
                              HTTP 400
```

`@RequestBody` asks WebFlux to read the body and convert it to the parameter type using an `HttpMessageReader`. For JSON, the codec usually uses Jackson. Once the object has been created, `@Valid` or `@Validated` asks Spring to apply Bean Validation to that object.

These two steps have different purposes:

- **Deserialization/binding:** Is the JSON syntactically valid and convertible to the expected Java types? For example, can the string `"abc"` be converted to an `Integer`?
- **Validation:** Does the created object satisfy the business rules declared with constraints? For example, age must be greater than 0, email must have a valid format, name must not be blank.

If the JSON has invalid syntax, lacks a convertible type, or has a field that cannot be deserialized, the error occurs **before Bean Validation**. `@Valid` cannot fix malformed JSON. Only if the object is created successfully but violates `@NotBlank` or `@Positive` is it a Bean Validation error.

Spring WebFlux supports `@RequestBody` with both direct objects and reactive wrappers such as `Mono<T>`. When using `Mono<T>`, reading the body is represented inside the reactive pipeline; the controller can continue processing with `map`/`flatMap` without needing `block()`.

## 2. Preparing dependencies and namespace

With Spring Boot 3, Bean Validation uses the **Jakarta** namespace:

- `jakarta.validation.Valid`
- `jakarta.validation.constraints.NotBlank`
- `jakarta.validation.constraints.NotNull`
- `jakarta.validation.Validator`

Do not mix `javax.validation.*` annotations from the legacy ecosystem into a Boot 3 project.

Spring WebFlux needs a Bean Validation implementation on the classpath. With Spring Boot, add `spring-boot-starter-validation` to get a validator implementation, usually Hibernate Validator:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Without a Bean Validation provider, annotations may still compile because the API is present transitively, but validation is not fully configured as expected. In WebFlux, when a provider is on the classpath, Spring can register a default validator for controller method arguments. You can customize the validator globally via `WebFluxConfigurer` or locally via `@InitBinder`.

## 3. @Valid: triggering validation on an object

`@Valid` is a Jakarta Bean Validation annotation. When placed before a `@RequestBody` parameter, Spring checks the deserialized object against the constraints on the DTO:

```java
@PostMapping("/accounts")
public Mono<AccountResponse> create(
        @Valid @RequestBody Mono<CreateAccountRequest> body) {

    return body.map(request ->
            new AccountResponse(request.name(), request.email()));
}
```

This is a **WebFlux illustrative snippet**. `CreateAccountRequest` and `AccountResponse` are application-defined DTOs. `@Valid` requests object validation; `Mono` represents the asynchronous body. When the data is invalid, the body pipeline terminates with a validation error and the controller does not execute the success path.

`@Valid` does not contain its own validation rule and is not itself a constraint. It marks that **cascade validation** into the object is needed. The specific rules live on constraint annotations such as `@NotBlank`, `@Email`, or custom constraints.

### 3.1. DTO example using a Java record

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.util.List;

public record CreateAccountRequest(
        @NotBlank(message = "name is required")
        @Size(max = 80, message = "name must be at most 80 characters")
        String name,

        @NotBlank(message = "email is required")
        @Email(message = "email must be valid")
        String email,

        @NotNull(message = "age is required")
        @Positive(message = "age must be positive")
        Integer age,

        @NotNull(message = "address is required")
        @Valid
        AddressRequest address,

        @NotEmpty(message = "tags must contain at least one value")
        List<@NotBlank(message = "tag must not be blank") String> tags
) {
    public record AddressRequest(
            @NotBlank(message = "city is required")
            String city,

            @NotBlank(message = "country is required")
            String country
    ) {}
}
```

This is a complete DTO for the example. Jakarta Validation supports annotations on record components; Spring/Jackson can deserialize JSON into records in Java 17+ applications.

`@Valid` on `address` triggers checking the constraints inside `AddressRequest`. If `@Valid` is omitted, the address object can be created, but the `city`/`country` constraints are not cascaded from the parent DTO.

For `tags`, `@NotEmpty` checks that the list has at least one element; the type-use annotation `List<@NotBlank String>` checks that each string is not empty or all whitespace. The two levels of checks solve two different problems.

### 3.2. Commonly used constraints

| Constraint | Checks | Notes |
| --- | --- | --- |
| `@NotNull` | Value is not null | Does not check for empty string or whitespace. |
| `@NotBlank` | String is not null and has at least one non-whitespace character | Only for `CharSequence`. |
| `@NotEmpty` | String, collection, map, or array is not empty | A string containing only whitespace can still be considered non-empty. |
| `@Size(min, max)` | Length/size is within range | Normally null is accepted; combine with `@NotNull` if the field is required. |
| `@Email` | Email format according to the validator | Does not verify that the mailbox exists or that the sender owns the email. |
| `@Positive` | Number is greater than 0 | Null is valid per constraint semantics; combine with `@NotNull` if required. |
| `@PositiveOrZero` | Number is greater than or equal to 0 | Suitable for quantities that can be 0. |
| `@Min` / `@Max` | Minimum/maximum numeric value | Used for numeric types; does not replace null checks. |
| `@Pattern(regexp)` | String matches the regular expression | Null is valid; combine with `@NotNull`/`@NotBlank` if needed. |
| `@Past` / `@Future` | Date/time before or after the present | Pay attention to clock/time zone and the date-time type used. |

Examples:

- `@NotNull Integer age` only guarantees a value is present; `0` is still valid.
- `@Positive Integer age` rejects 0 and negative numbers; however, if age is null, this constraint does not report an error on its own.
- `@NotBlank String name` rejects null, `""`, and whitespace-only strings.
- `@Size(max = 80) String name` limits length, but null is still valid if there is no other constraint.

**Choose constraints by the meaning of the data.** Do not use `@NotEmpty` instead of `@NotBlank` when the field is a person's name or a code that needs real characters. Do not use a default number like 0 to represent “no data” if 0 is also a valid value.

## 4. @Validated: selecting validation groups

`@Validated` belongs to Spring: `org.springframework.validation.annotation.Validated`. In the context of a controller parameter, it also triggers Bean Validation like `@Valid`, while letting you specify **validation groups**.

A single DTO can be used for multiple operations. For example, when creating an account, the name must be checked as required; when doing a partial update, the name might not be sent. Validation groups allow applying different sets of constraints depending on the operation.

```java
public interface Create {}
public interface Update {}

public record AccountInput(
        @NotBlank(groups = Create.class,
                  message = "name is required when creating")
        @Size(max = 80, message = "name is too long")
        String name,

        @NotBlank(groups = {Create.class, Update.class},
                  message = "email is required")
        @Email(groups = {Create.class, Update.class},
               message = "email must be valid")
        String email
) {}
```

In the example, `@Size` does not declare a group, so it belongs to `Default`; constraints with `groups` run only in the selected group.

To run both the default group and the Create group:

```java
@PostMapping("/accounts")
public Mono<AccountResponse> create(
        @Validated({Default.class, Create.class})
        @RequestBody Mono<AccountInput> body) {

    return body.map(input ->
            new AccountResponse(input.name(), input.email()));
}
```

You need to import `jakarta.validation.groups.Default` and Spring's `Validated`. If you use only `@Validated(Create.class)`, constraints belonging to `Default` are not run automatically, unless the group is declared to inherit or is included in the list. Clearly determine which groups must run for each operation.

### 4.1. How to choose between @Valid and @Validated?

| Need | Usage |
| --- | --- |
| Validate a DTO against the default group | `@Valid @RequestBody ...` |
| Cascade validation to a child object | `@Valid` on field/record component |
| Select the Create/Update group for a parameter | `@Validated(Create.class)` |
| Select multiple groups | `@Validated({Default.class, Create.class})` |
| Enable method validation for a service bean | `@Validated` at class level can be used with the appropriate method validation/AOP mechanism |

In a controller, use `@Valid` when only default validation is needed; use `@Validated` on a parameter when groups are needed. The two annotations are not “strong/weak” levels of the same check. They serve two different needs.

`@Validated` at the **class level** has a different meaning from `@Validated` on a body parameter: it can enable method validation via an AOP proxy. Spring WebFlux also supports method validation for controller methods; if constraints are declared directly on parameters such as `@Min`, Spring can validate the entire method and use `HandlerMethodValidationException`. Do not add class-level `@Validated` out of habit if you do not need AOP validation at the controller/service level.

## 5. WebFlux supports reactive @RequestBody types

In WebFlux, `@RequestBody` can receive a DTO directly or a reactive wrapper:

```java
@PostMapping("/sync-shape")
public Mono<AccountResponse> create(
        @Valid @RequestBody CreateAccountRequest request) {
    return accountService.create(request);
}

@PostMapping("/reactive-shape")
public Mono<AccountResponse> createReactive(
        @Valid @RequestBody Mono<CreateAccountRequest> request) {
    return request.flatMap(accountService::create);
}
```

The two methods above are **independent illustrative snippets**; do not put both on the same mapping in a real controller. `Mono<CreateAccountRequest>` fits when you want the body to participate in the reactive chain with `map`/`flatMap`. Both approaches can trigger validation.

Do not call `block()` to get the DTO from a Mono inside a controller. Doing something like `request.block()` blocks the thread and loses the benefit of reactive request handling. Compose the processing with publishers instead.

### 5.1. Collections and wrapper DTOs

Automatic validation at the method-argument level is designed for command objects. A container such as `Map` or `Collection` is not treated like a simple DTO that can automatically cascade in the same way. If an API receives a list of multiple elements, wrap it in a DTO with explicit rules:

```java
public record BatchCreateRequest(
        @NotEmpty(message = "items must not be empty")
        List<@Valid CreateItemRequest> items
) {}

public record CreateItemRequest(
        @NotBlank(message = "sku is required")
        String sku,

        @Positive(message = "quantity must be positive")
        int quantity
) {}
```

This is an **illustrative snippet**. `@Valid` on the list element requests cascading to each `CreateItemRequest`; `@NotEmpty` checks that the list has elements. If the body is a stream of separate JSON records (`Flux<T>`), you need to design per-element validation in the pipeline or use an appropriate wrapper; do not assume annotations on a container will automatically validate each event as desired.

## 6. Validation errors in WebFlux

When validation of an individual command object such as `@Valid @RequestBody Mono<CreateAccountRequest>` fails, WebFlux raises `WebExchangeBindException`. By default this error maps to HTTP **400 Bad Request** and contains a `BindingResult` with the list of field/global errors.

There are two exceptions to distinguish:

| Exception | When it usually occurs | Contents |
| --- | --- | --- |
| `WebExchangeBindException` | Validation of a single command object parameter such as `@RequestBody` or `@ModelAttribute` | `BindingResult` for one object, including field errors and global errors. |
| `HandlerMethodValidationException` | Method validation triggered by direct constraints on a parameter or return value | Validation results grouped by method parameters; may include nested `@Valid`. |

`@Valid` itself **is not a constraint annotation**, so having only `@Valid` on a body object usually leads to individual validation and `WebExchangeBindException`. If the method has direct constraints such as `@Min(1)` on `@RequestParam` or `@PathVariable`, method validation may apply to the entire method; in that case, nested body errors can appear inside `HandlerMethodValidationException`.

An application may need to handle **both** exceptions, depending on the controller signature. Do not assume every `@Valid`-related error always produces the same exception type across all method signatures.

### 6.1. Reading field errors from WebExchangeBindException

```java
@ExceptionHandler(WebExchangeBindException.class)
public ResponseEntity<ApiValidationError> handleBodyValidation(
        WebExchangeBindException exception) {

    List<FieldViolation> violations =
            exception.getFieldErrors().stream()
                    .map(error -> new FieldViolation(
                            error.getField(),
                            error.getDefaultMessage()))
                    .sorted(Comparator.comparing(FieldViolation::field))
                    .toList();

    return ResponseEntity.badRequest().body(
            new ApiValidationError("VALIDATION_FAILED", violations));
}
```

This is an **illustrative snippet inside `@RestControllerAdvice`**. `getFieldErrors()` returns errors attached to individual fields; `getGlobalErrors()` returns object-level errors, such as a custom class-level constraint. `getBindingResult()` gives access to the full binding/validation information.

Do not put the entire request object, sensitive values, or stack traces into error responses. Return only controlled field names and public messages. Internal logs can include additional correlation IDs and exception details according to the security policy.

### 6.2. Handling HandlerMethodValidationException

When method validation applies, `HandlerMethodValidationException` contains results grouped by method parameter. You can:

- Use WebFlux's `ResponseEntityExceptionHandler` as a base class for `@ControllerAdvice` and customize the response.
- Handle it directly with `@ExceptionHandler(HandlerMethodValidationException.class)`.
- Iterate over `getAllValidationResults()` or use the visitor `visitResults(...)` to classify path variables, request parameters, request headers, model attributes, and other parameters.

Do not force every result to become a body DTO field name. An error could be in the `page` query parameter or the `X-Version` header; the response should preserve the true error source so the client knows which part of the request to fix.

### 6.3. BindingResult immediately after the parameter

You can handle validation directly inside the controller using `Errors` or `BindingResult`, but with WebFlux `@RequestBody`, when declaring this way, the body must be resolved to a direct object rather than `Mono<T>`:

```java
@PostMapping("/accounts/local-errors")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateAccountRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body("Request validation failed");
    }

    return ResponseEntity.status(HttpStatus.CREATED)
            .body(new AccountResponse(request.name(), request.email()));
}
```

This is an **illustrative snippet**. `BindingResult` must stand immediately after the validated parameter for Spring to attach the corresponding errors. If the body is declared as `Mono<CreateAccountRequest>`, do not use this way of receiving `BindingResult`; let the error flow through the reactive pipeline and handle `WebExchangeBindException` in an advice or with an appropriate operator.

## 7. Distinguishing deserialization errors from validation errors

Consider the same `/accounts` endpoint:

**Case A – Syntactically valid JSON, but violates constraints:**

```json
{
  "name": " ",
  "email": "not-an-email",
  "age": -2,
  "address": {
    "city": "",
    "country": "VN"
  },
  "tags": []
}
```

Jackson can deserialize the body into the DTO. Bean Validation then reports `name`, `email`, `age`, `address.city`, and `tags` as invalid. This is a validation error, usually `WebExchangeBindException` and HTTP 400.

**Case B – JSON that cannot be deserialized:**

```json
{
  "name": "Lan",
  "email": "lan@example.com",
  "age": "twenty"
}
```

`age` expects `Integer`, but the JSON supplies a string that cannot be converted. The codec/Jackson fails before there is a complete DTO to validate. This is a request body reading/decoding error, usually represented by an exception in the `ServerWebInputException`/message decoding family; it is not `@Positive` or `@NotBlank` reporting an error.

**Case C – Missing body or wrong media type:**

If `@RequestBody` is required and the body is missing, or the Content-Type is unsupported, the request can be rejected before Bean Validation. Check `required`, `Content-Type`, and the matching message reader. Do not return the same “field invalid” message for every 400 error if the client needs to know whether they sent malformed JSON, missed the body, or violated a field rule.

## 8. A runnable Spring Boot 3.3.5 program

The example below uses **Java 17+**, **Maven**, **Spring Boot 3.3.5**, WebFlux, and Hibernate Validator via the validation starter. The controller receives the body as a `Mono`, the DTO uses a record, and the advice converts field errors into a structured JSON response.

Structure:

```text
webflux-request-validation/
├── pom.xml
└── src/main/java/demo/
    ├── ValidationApplication.java
    ├── CreateAccountRequest.java
    ├── AccountController.java
    └── ApiValidationAdvice.java
```

### 8.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-request-validation</artifactId>
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
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

### 8.2. ValidationApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationApplication.class, args);
    }
}
```

### 8.3. CreateAccountRequest.java

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record CreateAccountRequest(
        @NotBlank(message = "name is required")
        @Size(max = 80, message = "name must be at most 80 characters")
        String name,

        @NotBlank(message = "email is required")
        @Email(message = "email must be valid")
        String email,

        @NotNull(message = "age is required")
        @Positive(message = "age must be positive")
        Integer age,

        @NotNull(message = "address is required")
        @Valid
        Address address
) {
    public record Address(
            @NotBlank(message = "city is required")
            String city,

            @NotBlank(message = "country is required")
            String country
    ) {}
}
```

### 8.4. AccountController.java

```java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import jakarta.validation.Valid;

@RestController
public class AccountController {
    public record AccountResponse(
            String status,
            String name,
            String email) {}

    @PostMapping(
            value = "/accounts",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<AccountResponse>> create(
            @Valid @RequestBody Mono<CreateAccountRequest> body) {

        return body.map(request ->
                ResponseEntity.status(HttpStatus.CREATED).body(
                        new AccountResponse(
                                "created",
                                request.name(),
                                request.email())));
    }
}
```

### 8.5. ApiValidationAdvice.java

```java
package demo;

import java.util.Comparator;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;

@RestControllerAdvice
public class ApiValidationAdvice {
    public record FieldViolation(String field, String message) {}
    public record ApiValidationError(
            String code,
            List<FieldViolation> violations) {}

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiValidationError> handleBodyValidation(
            WebExchangeBindException exception) {

        List<FieldViolation> violations =
                exception.getFieldErrors().stream()
                        .map(error -> new FieldViolation(
                                error.getField(),
                                error.getDefaultMessage()))
                        .sorted(Comparator.comparing(FieldViolation::field))
                        .toList();

        return ResponseEntity.badRequest().body(
                new ApiValidationError("VALIDATION_FAILED", violations));
    }
}
```

### 8.6. Running the application

In the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Send a valid body:

```bash
curl -i -X POST http://localhost:8080/accounts \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","email":"lan@example.com","age":25,"address":{"city":"Hanoi","country":"VN"}}'
```

A successful result has status **201 Created** and a body like:

```json
{
  "status": "created",
  "name": "Lan",
  "email": "lan@example.com"
}
```

Send a body that violates constraints:

```bash
curl -i -X POST http://localhost:8080/accounts \
  -H "Content-Type: application/json" \
  -d '{"name":" ","email":"bad","age":-2,"address":{"city":"","country":"VN"}}'
```

The response has status **400 Bad Request**, with a structured body:

```json
{
  "code": "VALIDATION_FAILED",
  "violations": [
    {"field": "address.city", "message": "city is required"},
    {"field": "age", "message": "age must be positive"},
    {"field": "email", "message": "email must be valid"},
    {"field": "name", "message": "name is required"}
  ]
}
```

The list is sorted by field name in the advice for stable output. The actual fields that appear depend on the input data and which constraints were violated. If constraints are added for address or age, the response will include the corresponding violations.

Send JSON with the wrong type:

```bash
curl -i -X POST http://localhost:8080/accounts \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","email":"lan@example.com","age":"twenty","address":{"city":"Hanoi","country":"VN"}}'
```

The request fails at the deserialization step; it is not handled as a `@Positive` error. The default response is still 4xx, but the exception belongs to the body reading/decoding category. If the API needs a consistent error contract, add a separate handler for input/decoding errors.

## 9. Testing with WebTestClient

`WebTestClient` tests the WebFlux HTTP contract without manually calling controller methods. The example below goes in a separate test file and needs the `spring-boot-starter-test` dependency in test scope.

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class AccountControllerTest {
    @Autowired
    WebTestClient client;

    @Test
    void validBodyCreatesAccount() {
        client.post()
                .uri("/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "Lan",
                          "email": "lan@example.com",
                          "age": 25,
                          "address": {
                            "city": "Hanoi",
                            "country": "VN"
                          }
                        }
                        """)
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.status").isEqualTo("created")
                .jsonPath("$.name").isEqualTo("Lan");
    }

    @Test
    void invalidBodyReturnsFieldErrors() {
        client.post()
                .uri("/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": " ",
                          "email": "bad",
                          "age": -2,
                          "address": {
                            "city": "",
                            "country": "VN"
                          }
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_FAILED")
                .jsonPath("$.violations").isArray()
                .jsonPath("$.violations[0].field")
                    .isEqualTo("address.city");
    }
}
```

Run tests:

```bash
mvn test
```

The tests confirm two important contracts: a valid body returns 201 and a constraint-violating body returns 400 with a list of errors. Do not check only whether the controller method was called; check the HTTP status and JSON response that the client actually receives.

## 10. Custom validators and business rules

Bean Validation fits synchronous object-checking rules: requiredness, length, format, value ranges, and simple relationships between fields. When more complex rules are needed, you can create a custom constraint annotation and a `ConstraintValidator`.

Conceptual example:

```java
@Target({ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = SupportedCodeValidator.class)
public @interface SupportedCode {
    String message() default "code is not supported";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

This is an **illustrative annotation skeleton**; you need to import the Jakarta Validation types and define `SupportedCodeValidator`. The validator can check format rules or a local list of allowed values. Avoid making synchronous database or HTTP calls inside `isValid`: the Bean Validation validator is a synchronous API, not a reactive publisher. If a rule needs to query inventory, check whether a username already exists, or call an external service, perform it in the service layer with `Mono/Flux` after the request DTO passes structural validation.

Example of checking whether a username exists:

```java
return body.flatMap(request ->
        accountRepository.existsByEmail(request.email())
                .flatMap(exists -> exists
                        ? Mono.error(new EmailAlreadyUsedException())
                        : accountService.create(request)));
```

This is an **illustrative snippet**; the repository and service need to return reactive publishers. This rule depends on current data, so it is handled asynchronously in the pipeline and can return 409 conflict per the API contract. `@Email` checks only the email's form, not whether the email is already registered.

### 10.1. Validation does not replace security

Do not use validation as a substitute for authentication/authorization. A `role` field can be syntactically valid, yet the user is not allowed to choose that role themselves. Permission checks must rely on the authenticated principal and server-side policy. Similarly, length or format limits do not replace injection protection, request body size limits, rate limits, or upload controls.

### 10.2. Validation does not guarantee data remains unchanged after the check

A DTO that is valid at the time the request arrives does not guarantee that the database state is still valid when writing. For example, two concurrent requests can both pass the “email does not exist yet” check before either request writes data. Unique constraints in the database and conflict handling are still necessary. Bean Validation is an input validation layer, not a transaction or data-locking mechanism.

## 11. Customizing the Validator in WebFlux

If the application needs a custom global validator, implement `WebFluxConfigurer`:

```java
@Configuration
public class ValidationConfig implements WebFluxConfigurer {
    private final Validator validator;

    public ValidationConfig(Validator validator) {
        this.validator = validator;
    }

    @Override
    public Validator getValidator() {
        return validator;
    }
}
```

This is an **illustrative configuration snippet**; `Validator` here is Spring's validation abstraction or a Jakarta-backed implementation depending on the project configuration. When you only need to add a local validator for a controller or advice, you can use `@InitBinder` and `WebDataBinder.addValidators(...)`.

Do not create a new `ValidatorFactory` for every request. The validator is normally managed at the application context level and reused; a custom validator must be safe for concurrent calls if the bean is shared.

## 12. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Forgetting `spring-boot-starter-validation` | No suitable Bean Validation provider | Add the validation starter and check runtime dependencies. |
| Using `javax.validation.*` in Boot 3 | Mismatch with the Jakarta namespace | Use `jakarta.validation.*`. |
| Thinking `@Valid` defines rules by itself | No constraints are present to check | Add `@NotBlank`, `@Email`, `@Positive`, or a custom constraint. |
| Using only `@Positive` for a required field | Null can still be valid | Combine with `@NotNull` if null is unacceptable. |
| Using `@NotEmpty` for a person's name | Whitespace-only strings can still pass | Use `@NotBlank`. |
| Forgetting `@Valid` on child objects | Nested constraints are not cascaded | Put `@Valid` on the field/record component. |
| Thinking `@Valid` and `@Validated` are strong/weak levels | Choosing the wrong annotation for the goal | `@Valid` for default validation; `@Validated` for groups and Spring validation use cases. |
| Selecting the Create group but forgetting Default | Constraints in Default do not run | Add `Default.class` or design clear group inheritance. |
| Thinking every request body error is WebExchangeBindException | JSON decode errors are misclassified | Distinguish binding/validation from decoding/input exceptions. |
| Putting constraints directly on parameters while handling only WebExchangeBindException | Method validation can throw HandlerMethodValidationException | Handle both exceptions according to the method signature. |
| Using `@Valid` on `Mono<List<T>>` and expecting all elements to validate automatically | A container is not an ordinary command object | Use a wrapper DTO with `@Valid` on elements or validate each item in the pipeline. |
| Using BindingResult after a `Mono<T>` body | Not the supported way to resolve body and errors in WebFlux | Use a direct body object with BindingResult right after, or reactive Mono and an exception handler. |
| Calling `block()` in a controller to obtain the DTO | Blocks the reactive request-processing thread | Use `map`/`flatMap` and return a publisher. |
| Querying the DB inside a ConstraintValidator | Synchronous validator can block the event loop | Move I/O-dependent checks into a reactive service. |
| Returning stack traces or the entire request in a 400 error | Leaks internal/sensitive information | Return only public fields and messages, with controlled internal logging. |
| Thinking `@Email` verifies that the address exists | The constraint only checks format | Verify ownership through an email confirmation flow if required by business rules. |
| Thinking a valid DTO means the database will surely accept it | Race conditions/database constraints can still occur | Keep unique constraints and handle conflicts in the persistence layer. |

## 13. Self-check questions

**Question 1.** What does `@Valid @RequestBody Mono<CreateAccountRequest> body` do?  
**Answer:** WebFlux reads the body via the message reader, deserializes it into the DTO, applies Bean Validation to the object, and passes the result into the Mono pipeline. If the object violates constraints, the pipeline reports a validation error instead of running the success branch.

**Question 2.** Does `@Valid` validate email format on its own?  
**Answer:** No. `@Valid` triggers validation/cascading; `@Email` on the email field is needed to check the format.

**Question 3.** What is the main difference between `@Valid` and `@Validated(Create.class)`?  
**Answer:** `@Valid` triggers default validation and cascading. `@Validated` is a Spring annotation that can select the Create group so only constraints belonging to that group run.

**Question 4.** Does `@Positive Integer age` reject null?  
**Answer:** Not necessarily. Combine with `@NotNull` if age is required.

**Question 5.** What exception is usually raised for a validation error on a single body DTO in WebFlux?  
**Answer:** `WebExchangeBindException`, mapped by default to HTTP 400 Bad Request.

**Question 6.** When a method has `@Min(1)` directly on a query parameter, which exception might validation use?  
**Answer:** `HandlerMethodValidationException`, because Spring applies method validation to the entire method, which can also include nested constraints via `@Valid`.

**Question 7.** What kind of error is JSON sending `"age": "twenty"` when the DTO declares Integer?  
**Answer:** A deserialization/binding error occurring before Bean Validation. `@Positive` does not yet have a valid Integer object to check.

**Question 8.** Why should you not use a database query inside `ConstraintValidator.isValid()`?  
**Answer:** Bean Validation is a synchronous API; a blocking query can block a WebFlux thread. Use the service layer and compose reactive publishers for rules requiring I/O.

**Question 9.** To validate constraints inside an Address DTO nested within the request, what is needed?  
**Answer:** Put `@Valid` on the address field/record component; if address is also required, combine with `@NotNull`.

**Question 10.** With `@Validated(Create.class)`, do constraints in the Default group run automatically?  
**Answer:** Not automatically. Add `Default.class` to the group list or design the group to extend Default.

## Takeaways

- **`@RequestBody` deserializes first, Bean Validation runs second.** Wrong JSON type/syntax is a decode error; a created object violating constraints is a validation error.
- **`@Valid` triggers validation and cascading**, while constraints such as `@NotBlank`, `@Email`, `@Positive` define specific rules.
- **`@Validated` allows selecting validation groups** such as Create/Update; note that the Default group does not run automatically if you select only another group.
- For a single body DTO, WebFlux usually throws `WebExchangeBindException` and returns HTTP 400. If method-level constraints are active, also handle `HandlerMethodValidationException`.
- Use `Mono<DTO>` to keep the body in the reactive pipeline; do not `block()`. With `BindingResult`, place it immediately after a direct body parameter; WebFlux does not use that approach with `Mono<T>`.
- Use custom constraints for synchronous rules. Checks needing a database/HTTP call belong in a reactive service; validation does not replace authorization, transactions, or database constraints.

### References

1. [Spring Framework 6.2 – WebFlux Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html): parameter-level and method-level validation, `WebExchangeBindException`, `HandlerMethodValidationException`.
2. [Spring Framework 6.2 – @RequestBody in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html): reactive body, `@Valid`/`@Validated`, and `BindingResult`.
3. [Spring Boot – Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): Bean Validation provider, `spring-boot-starter-validation`, and method validation.
4. [Spring Framework – Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): constraints, groups, and custom validators.
5. [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): annotation contracts, groups, cascading, and `ConstraintValidator`.
6. [Spring Framework 6.2 – WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html): RFC 9457, `ProblemDetail`, and HTTP error handling.
