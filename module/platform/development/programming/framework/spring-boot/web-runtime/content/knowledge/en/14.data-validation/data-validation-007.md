# WebExchangeBindException and Data Validation Errors in Spring WebFlux

## 1. Why Understanding WebExchangeBindException Matters

A Spring WebFlux API commonly receives JSON from an HTTP request, decodes it into a Java DTO, and validates the data before executing business logic. When the DTO fails to satisfy constraints such as @NotBlank, @Email, @Size, or @Min, Spring can raise **WebExchangeBindException**. This is an important signal: client data reached the binding/validation step but failed to meet the contract required by the endpoint.

Points to remember right away:

- **WebExchangeBindException** belongs to the **org.springframework.web.bind.support** package.
- It extends **ServerWebInputException**, and implements **BindingResult** and **ErrorResponse**.
- For standard validation on a DTO argument, this error defaults appropriately to HTTP **400 Bad Request**.
- It holds lists of field errors, global/object errors, the object name, and binding metadata.
- It **differs** from MethodArgumentNotValidException commonly referenced in Spring MVC.
- It also **differs** from HandlerMethodValidationException, which normally appears when Spring Framework 6.1 applies **method validation** because constraints are placed directly on controller parameters or return values.

This lesson uses **Java 17+, Spring Boot 3.3.x, Spring Framework 6.1.x, and Spring WebFlux**. The complete example includes HTTP tests using WebTestClient on embedded Reactor Netty. If a project has only starter-webflux **without** starter-validation, do not assume Jakarta Bean Validation works completely out of the box.

Lesson objectives:

1. Understand precisely where the error occurs in the reactive request pipeline.
2. Know which cases produce WebExchangeBindException and which use other exceptions.
3. Read field errors and global errors without leaking sensitive input.
4. Design HTTP 400 responses with a stable contract.
5. Know when to use @RestControllerAdvice, BindingResult, onErrorResume, and ResponseEntityExceptionHandler.
6. Write and run a WebFlux application validating both synchronous DTOs and Mono<DTO>.
7. Distinguish DTO validation from method parameter validation in Spring 6.1.
8. Test malformed JSON, missing data, violated constraints, Content-Type errors, and business errors.

## 2. Where Validation Sits in the WebFlux HTTP Flow

Overview diagram:

~~~mermaid
flowchart TD
    A["HTTP request / Reactor Netty"] --> B["HttpHandler + WebFilter chain"]
    B --> C["DispatcherHandler"]
    C --> D["HandlerMapping selects method"]
    D --> E["WebFlux RequestMappingHandlerAdapter"]
    E --> F["HttpMessageReader / decode JSON"]
    F --> G["Argument binding"]
    G --> H{"@Valid / @Validated and constraints"}
    H -->|"Valid"| I["Controller method / reactive publisher"]
    H -->|"Single DTO error"| J["WebExchangeBindException"]
    H -->|"Method validation error"| K["HandlerMethodValidationException"]
    F -->|"Malformed JSON"| L["HTTP decoding / input exception"]
    I --> M["Result handling / HTTP response"]
    J --> N["@ExceptionHandler / error handling"]
    K --> N
    L --> N
    N --> O["HTTP error response if uncommitted"]
~~~

The diagram shows the **conceptual** flow, not a rigid stack trace. With an @RequestBody Mono<T> parameter, decoding/validation may happen when the Publisher is subscribed, after the controller method has already returned a pipeline. With a synchronous @RequestBody T, Spring must resolve the argument before calling the method. When method validation applies, the order and chosen exception can differ.

**Data validation is not authentication or authorization.** Syntactically valid email does not prove the email address exists or belongs to the caller. A valid accountId does not prove the user has permission to access that account.

### Steps to Distinguish

1. **Routing**: does the request match @PostMapping and its consumes/produces conditions?
2. **HTTP decoding**: is Content-Type compatible? Can JSON be parsed?
3. **Binding**: can the framework construct the Java/DTO value?
4. **Validation**: does the DTO or method violate any constraint?
5. **Business logic**: does the entity exist, does state permit the operation, is the user authorized?
6. **Response**: how are the HTTP status and error body written before the response commits?

If JSON syntax is invalid, processing may never reach DTO validation. If Content-Type is wrong, the request may receive **415 Unsupported Media Type** before Jackson runs. Do not lump every HTTP 400 or 415 into WebExchangeBindException.

## 3. Definition and Key APIs of WebExchangeBindException

In Spring Framework 6.1, WebExchangeBindException has this structure:

~~~java
package org.springframework.web.bind.support;

// Abbreviated class description, not full source:
public class WebExchangeBindException
        extends ServerWebInputException
        implements BindingResult {
    // ...
}
~~~

It also participates in the framework's ErrorResponse contract. Key APIs to know:

| API | Meaning |
| --- | --- |
| getBindingResult() | Returns the BindingResult wrapped inside the exception |
| getObjectName() | Name of the object being bound/validated |
| hasErrors() | Whether any binding/validation errors exist |
| getErrorCount() | Total count of field and global errors |
| getAllErrors() | Combined list of ObjectErrors/FieldErrors |
| getFieldErrors() | All errors attached to fields |
| getFieldErrors("email") | Errors on the email field |
| getFieldError("email") | First error on the email field if present |
| getGlobalErrors() | Errors relating to the whole object |
| getFieldValue("field") | Binding-related value, which may contain client input |
| getStatusCode() | HTTP status provided by ErrorResponse/ServerWebInputException |
| getBody() | ProblemDetail corresponding to the ErrorResponse mechanism |

In public error responses, you usually only need **field names, controlled error codes/messages**, and an overall error code; never automatically return getFieldValue(), rejectedValue, exception stack traces, or the raw BindingResult to clients.

### FieldError and ObjectError

- **FieldError** represents an error tied to a specific field such as name or age.
- **ObjectError** can express object-level errors, such as a rule involving both startDate and endDate.

A FieldError can carry a field name, rejectedValue, codes, arguments, and defaultMessage. Do not assume **defaultMessage** is a stable translation across languages; many applications require MessageSource and stable public error codes.

## 4. When Does WebExchangeBindException Occur?

Under Spring WebFlux's built-in validation mechanism:

- @Valid or @Validated on a **@RequestBody, @ModelAttribute, or @RequestPart parameter object** can trigger Bean Validation.
- In **argument validation** for a single object, with no adjacent Errors/BindingResult to handle it locally and without method validation superseding it, errors normally produce **WebExchangeBindException**.
- When constraints sit directly on method parameters or return values handled by Spring 6.1 method validation, **HandlerMethodValidationException** is typically used.
- For parameters lacking validation constraints/annotations, decoding an object successfully **does not guarantee** Bean Validation constraints will execute.

Example:

~~~java
@PostMapping("/signup")
public Mono<String> signup(
        @Valid @RequestBody SignupRequest request) {
    return Mono.just("accepted");
}
~~~

This is an illustrative method, not a standalone Java file. With SignupRequest having @NotBlank on name, a request with an empty name is normally rejected via WebExchangeBindException before the controller runs business logic.

Notes when talking about @Valid:

- @Valid itself triggers **nested/argument validation**, not a direct constraint like @Min or @NotBlank.
- A DTO typed as Map or Collection validates differently from a standard command object; do not assume adding @Valid validates every element under identical rules.
- Validation groups with @Validated can be used when create and edit genuinely need different groups; test specifically.
- A validator must be configured with a Jakarta Validation-compatible provider.
- Bean Validation on objects only checks declared invariants; business rules may still require services/databases.

## 5. Comparing with Commonly Confused Exceptions

| Exception | Typical Stack/Source | Core Meaning |
| --- | --- | --- |
| WebExchangeBindException | WebFlux; argument binding/validation | An object argument is invalid |
| HandlerMethodValidationException | Spring Framework 6.1; method validation | One or more parameters/return values violate method constraints |
| MethodArgumentNotValidException | Spring MVC/Servlet | DTO argument validation failed in MVC |
| ServerWebInputException | Spring WebFlux | A family of HTTP input errors; WebExchangeBindException is a subclass |
| DecodingException | Codec/reactive decoding | Content decoding failure, which can be wrapped as an HTTP input error |
| UnsupportedMediaTypeStatusException | WebFlux content type handling | Unsupported request media type; typically 415 |
| ResponseStatusException | Spring WebFlux/controller | Error specifying an HTTP status from code/framework |
| ConstraintViolationException | Jakarta Validation/provider or AOP method validation | Can occur outside controller argument validation pipeline |
| NoSuchElementException / domain exception | Service logic | Can be a business error, not argument validation |

**Do not catch every IllegalArgumentException or Throwable and return HTTP 400.** Doing so can mask serious Java bugs, system failures, or authorization violations.

### Easily Confused Imports

~~~java
// WebFlux binding/validation exception:
import org.springframework.web.bind.support.WebExchangeBindException;

// Method-level controller validation in Spring 6.1:
import org.springframework.web.method.annotation.HandlerMethodValidationException;

// MVC-specific exception (do not use to catch WebFlux WebExchangeBindException):
import org.springframework.web.bind.MethodArgumentNotValidException;
~~~

These three imports are shown to distinguish the APIs, not to imply all three belong in one file. The complete WebFlux demo below **does not import** MethodArgumentNotValidException.

## 6. Which Dependencies Are Needed?

With Spring Boot 3.3 and Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

- starter-webflux: WebFlux, HTTP codecs, and the standard Reactor Netty server.
- starter-validation: Jakarta Bean Validation/Hibernate Validator infrastructure managed by Boot.
- starter-test: JUnit Jupiter, Spring Test, WebTestClient, and standard testing tools.

If you include only starter-webflux and forget starter-validation, constraints such as @NotBlank and @Email may not run as expected. Never mark an endpoint as “validated” merely because @Valid appears in source code.

Java 17 uses the **jakarta.validation** package:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
~~~

In Spring Boot 3.x, do not use javax.validation.* from older versions.

**Watch web stack selection:** If both spring-boot-starter-web (MVC) and spring-boot-starter-webflux are added, Boot defaults to Servlet/MVC unless web application type is explicitly configured. Therefore the WebFlux example uses only starter-webflux.

## 7. Designing a Clear DTO Contract

Example signup form with only three fields:

- name: required and must not be whitespace-only.
- email: required, with basic email format.
- age: at least 18.

Java 17 record:

~~~java
public record SignupRequest(
        @NotBlank(message = "name is required")
        @Size(max = 40, message = "name is too long")
        String name,

        @NotBlank(message = "email is required")
        @Email(message = "email format is invalid")
        String email,

        @Min(value = 18, message = "age must be at least 18")
        int age) {
}
~~~

This snippet belongs in SignupRequest.java with proper package/imports; the complete code is in section 16.

Validation outcomes to distinguish:

| Request input | Expectation | Why |
| --- | --- | --- |
| {"name":"An","email":"an@example.org","age":21} | Valid | All constraints satisfied |
| {"name":"","email":"an@example.org","age":21} | Invalid | @NotBlank on name |
| {"name":"An","email":"bad","age":21} | Invalid | @Email on email |
| {"name":"An","email":"an@example.org","age":17} | Invalid | @Min on age |
| {"name":"","email":"bad","age":16} | Invalid across multiple fields | Errors on name, email, and age |
| {"name":"An","email":"an@example.org"} | Invalid | int age defaults to 0 when missing; @Min rejects it |
| {"name":null,"email":"an@example.org","age":22} | Invalid | @NotBlank rejects null |
| {"name":"An","email":null,"age":22} | Invalid | @NotBlank rejects null |
| {"name":"An","email":"an@example.org","age":"twenty"} | Decode/binding error, usually 400 | JSON string incompatible with int age |

**@Email does not verify that an email exists, can receive mail, or belongs to the user.** If address ownership must be verified, build a separate verification step outside Bean Validation.

### int age and Missing Values

When using primitive int in a record, an omitted JSON field may be defaulted to 0 by the mapper, and then @Min catches it. If you need to distinguish **missing**, explicit null, and 0 at the schema level, use Integer with @NotNull/@Min or appropriate Jackson creator configuration and test all three cases.

### Nested Validation

A DTO containing an Address object can declare:

~~~java
record Address(@NotBlank String street) {}

record OrderRequest(
        @NotNull @Valid Address shippingAddress) {}
~~~

This illustrative snippet requires imports; to validate inside the child object, @Valid on the child property is essential. Without @Valid on a nested property, constraints inside that object may not be evaluated. Avoid deeply nested DTOs without bounds that make validation hard to read and test.

## 8. @Valid on @RequestBody DTO vs. @RequestBody Mono<DTO>

Spring WebFlux supports both **direct object arguments** and **reactive type arguments**:

~~~java
@PostMapping("/sync-argument")
public Mono<String> syncArgument(
        @Valid @RequestBody SignupRequest request) {
    return Mono.just("accepted");
}
~~~

~~~java
@PostMapping("/reactive-argument")
public Mono<String> reactiveArgument(
        @Valid @RequestBody Mono<SignupRequest> request) {
    return request.map(value -> "accepted");
}
~~~

Both snippets are illustrative controller methods.

### Timing Differences

- With a direct object, the framework must read, decode, instantiate, and validate before calling the handler method with the resolved argument.
- With Mono<SignupRequest>, the method receives a Publisher; decoding/validation may complete when the pipeline is subscribed.
- When validation fails inside Mono<SignupRequest>, the error signal flows through the reactive Publisher, so handler code **can** catch it with onErrorResume/onErrorMap if desired.
- A global @ExceptionHandler(WebExchangeBindException.class) handles the error appropriately when propagated to the controller exception-handling framework.
- Do not call subscribe() inside a controller to force validation to run. Always **return** the reactive chain so the framework manages completion and cancellation.

Example handling an error locally as HTTP 400 using an operator:

~~~java
@PostMapping("/local")
public Mono<ResponseEntity<String>> local(
        @Valid @RequestBody Mono<SignupRequest> input) {

    return input
            .map(value -> ResponseEntity.ok("accepted"))
            .onErrorResume(WebExchangeBindException.class,
                    ex -> Mono.just(
                            ResponseEntity.badRequest()
                                    .body("invalid signup data")));
}
~~~

This is an illustrative method requiring corresponding imports. Never return "accepted" with status 200 when validation fails. If the entire system needs a uniform error format, a global @RestControllerAdvice avoids repeating onErrorResume in every controller.

## 9. Method Validation in Spring Framework 6.1

This is the most important point to avoid missing exceptions.

Spring Framework 6.1 includes **built-in method validation** for controller methods. When you attach constraints **directly** to a method parameter, the framework can validate all method arguments instead of only standalone DTOs.

Example:

~~~java
@GetMapping("/pages")
public Mono<PageView> pages(
        @RequestParam(name = "page", defaultValue = "1")
        @Min(1) int page) {
    return Mono.just(new PageView(page));
}
~~~

The @Min(1) constraint sits **directly on the method parameter**. When a client calls /pages?page=0 and method validation applies, Spring can throw **HandlerMethodValidationException**, not WebExchangeBindException.

Distinctions:

| Case | Typically Applied Mechanism | Exception on Failure |
| --- | --- | --- |
| @Valid @RequestBody SignupRequest request, no other direct @Constraint | Argument/object validation | WebExchangeBindException |
| @Valid @ModelAttribute Form form | Argument/object validation | WebExchangeBindException if Errors is not handled locally |
| @Valid @RequestBody Mono<SignupRequest> request | Reactive argument validation | WebExchangeBindException in error signal |
| @RequestParam @Min(1) int page | Method validation | HandlerMethodValidationException |
| @RequestHeader @NotBlank String token | Method validation when conditions apply | HandlerMethodValidationException |
| @Valid DTO **plus** direct @Min on another parameter | Method validation may cover both | HandlerMethodValidationException |
| Malformed JSON | Decoder/input processing | Input/codec error, not WebExchangeBindException by default |
| Unsupported Content-Type | Mapping/codec selection | Usually 415, not DTO validation |

There is no single exception for “every @Valid failure”.

### @Valid Itself Is Not a Constraint

Per Spring documentation, @Valid serves cascading/nested validation. It is **not** in the same category as @NotNull, @Min, or @NotBlank. @Valid alone on an object usually does not force method validation if no other direct constraints are present.

### Avoid Class-Level @Validated When Using Built-In Validation

If @Validated is placed on the controller class, Spring may use AOP method validation instead of the built-in controller method validation mechanism. When intending to use Spring 6.1 built-in method validation, the documentation recommends removing class-level @Validated where appropriate. @Validated still has valid roles for validation groups, service beans, and AOP scenarios—it is not universally wrong.

### Return Value Validation

HandlerMethodValidationException can also represent validation failures on a **return value**. Per Spring 6.1 Javadoc, the status for **input validation errors** is 400; **return-value** validation errors may be 500 because that is a server-side bug. Do not blindly map every HandlerMethodValidationException to 400.

## 10. Accessing Field Errors and Global Errors Properly

To build structured JSON errors, you can iterate:

~~~java
for (FieldError error : exception.getFieldErrors()) {
    String field = error.getField();
    String message = error.getDefaultMessage();
    // Add field and safe message to the response DTO.
}
~~~

~~~java
for (ObjectError error : exception.getGlobalErrors()) {
    String message = error.getDefaultMessage();
    // Used for object-level rules.
}
~~~

The two code blocks above are snippets, not standalone classes.

### Multiple Errors Can Occur on One Field

If a field has both @NotBlank and @Size or a custom validator, a single request can produce **multiple** FieldErrors on the same field. Therefore, instead of:

~~~java
Map<String, String> errors;
~~~

consider:

~~~java
Map<String, List<String>> fieldErrors;
~~~

A list structure preserves all errors. In the complete example, TreeMap gives JSON readable key ordering, though clients **must not depend on JSON object property order**.

### When Do Global Errors Matter?

For example, a request has startDate and endDate; each field is valid individually, yet overall startDate must precede endDate. A custom class-level constraint can emit an **ObjectError**. If a handler only calls getFieldErrors(), object-level errors are silently dropped. Error response contracts should support both fieldErrors and globalErrors.

### Do Not Return rejectedValue for All Errors

FieldError exposes getRejectedValue(), yet the rejected value may be a password, token, address, phone number, email, or payload containing private data. When building public APIs, **never** automatically serialize raw FieldError/BindingResult objects. Return only field names, error codes, and controlled messages.

## 11. HTTP Status and Error Body

When validation fails, there are two separate decisions:

1. **HTTP status**: for invalid input objects, typically 400 Bad Request.
2. **Error representation**: what JSON the client receives to know what to fix.

An API might return:

~~~json
{
  "code": "INVALID_REQUEST",
  "fieldErrors": {
    "age": ["age must be at least 18"],
    "email": ["email format is invalid"],
    "name": ["name is required"]
  },
  "globalErrors": []
}
~~~

This is an **application-defined JSON contract**. It is not a mandatory default body produced by Spring Boot or Spring WebFlux. Do not assume every Boot version returns fieldErrors like this without an @ExceptionHandler.

Good design rules:

- Use stable error codes such as INVALID_REQUEST rather than forcing clients to parse Vietnamese/English exception prose.
- Return HTTP 400 for constraint-violating input; do not return 200 with an error message.
- Do not expose Java class names, bean names, or unnecessary raw rejected values.
- Return both fieldErrors and globalErrors to cover cross-field rules.
- For method validation, use a code like METHOD_VALIDATION_FAILED or unify under INVALID_REQUEST with parameterErrors.
- When multilingual, use MessageSource to resolve messages for a trusted/defined Locale.
- Only include field names belonging to the public contract; do not expose unnecessary internal properties.

## 12. Centralized Handling with @RestControllerAdvice

In WebFlux annotated controllers, @RestControllerAdvice can use @ExceptionHandler to turn WebExchangeBindException into a ResponseEntity.

Abbreviated example:

~~~java
@RestControllerAdvice
public class ApiErrors {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ValidationErrorResponse> invalid(
            WebExchangeBindException ex) {
        // Extract ex.getFieldErrors() and ex.getGlobalErrors()
        // then build a response with status 400.
        return ResponseEntity.badRequest()
                .body(/* public error DTO */);
    }
}
~~~

This is **pseudocode** and does not compile standalone because the DTO/implementation are omitted. The complete sample in section 16 has all imports and no placeholders in real Java files.

When using advice:

- The class must be component-scanned or imported into the context.
- Pick specific exception types; never catch all Throwables and turn bugs into client errors.
- Do not register overlapping advice classes for the same exception without controlling @Order.
- Avoid accessing sensitive input just to build responses.
- Check whether the response is already committed, especially with Flux/SSE streaming.
- Perform error mapping quickly and non-blockingly; never perform synchronous database calls in an exception handler on the event loop.

### Why Not Use ResponseStatusException for Every Validation Error?

ResponseStatusException is useful for signaling errors with explicit HTTP statuses in business flows. However, Bean Validation already provides detailed field errors via WebExchangeBindException. Turning everything into a single ResponseStatusException("Invalid") discards details the client needs to fix the form.

## 13. ResponseEntityExceptionHandler and ProblemDetail

Spring WebFlux also provides **org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler**, supporting mapping many framework exceptions into responses via ErrorResponse/ProblemDetail.

Two valid strategies exist:

- **Strategy A**: @RestControllerAdvice with specific @ExceptionHandler methods returning an application-managed response DTO. Suitable when the API has a custom error contract.
- **Strategy B**: extend ResponseEntityExceptionHandler and override appropriate hooks to customize ProblemDetail, statuses, and message resolution. Suitable when standardizing on Problem Details.

**Do not mechanically combine both strategies with overlapping handlers.** The main example uses A. If switching to ProblemDetail, test response bodies and corresponding HTTP media types; Spring Framework 6.1 provides APIs to customize messages through MessageSource.

Example Problem Details-style payload:

~~~json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Request validation failed"
}
~~~

This example illustrates the concept, not a promise that Spring Boot 3.3 automatically emits this exact JSON for every WebExchangeBindException. Adding fieldErrors or localized messages is an application choice.

## 14. BindingResult/Errors Immediately After a Parameter

In certain WebFlux annotated controllers, you can handle validation errors locally using **Errors or BindingResult** placed **immediately after** the parameter to validate.

Conceptual example:

~~~java
@PostMapping("/form")
public Mono<ResponseEntity<String>> form(
        @Valid @ModelAttribute FormData input,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return Mono.just(
                ResponseEntity.badRequest().body("invalid form"));
    }
    return Mono.just(ResponseEntity.ok("accepted"));
}
~~~

This is a controller snippet requiring FormData and a BindingResult import. When Errors/BindingResult is in the right position and the framework supports local handling, the controller can choose the status/response instead of emitting WebExchangeBindException.

Common mistakes:

- BindingResult is not an object returned from a service.
- With multiple parameters needing validation, place BindingResult immediately after each respective parameter; do not put a single BindingResult at the end of the method expecting it to capture everything.
- With **@RequestBody Mono<T>**, you cannot simply place BindingResult after Mono<T> in the same synchronous style; use reactive error operators or global exception handling.
- If method validation on other parameters also fails, Spring may still throw HandlerMethodValidationException when not all errors map to an adjacent local Errors parameter.
- Returning 200 OK when errors.hasErrors() is true can be misleading in an API; normally choose 400.

## 15. Handling Reactive Error Signals in Mono<DTO>

WebFlux allows reading bodies as Mono<SignupRequest>. In this case, validation exceptions can arise **after** the controller has returned the Publisher. Therefore, think in terms of Reactor signals:

~~~text
HTTP body publisher
  -> decode JSON
  -> validate SignupRequest
  -> Mono<SignupRequest>
       -> onNext(valid DTO) -> business mapping
       -> onError(WebExchangeBindException) -> error strategy
       -> onComplete
~~~

Appropriate operators:

- **onErrorResume**: turns the error into a fallback Publisher, such as ResponseEntity.badRequest().
- **onErrorMap**: converts the error into another exception, preserving the cause for debugging.
- **doOnError**: observes/logs the error **without handling** or replacing it.
- **checkpoint**: aids debugging Reactor assembly in appropriate situations.
- **retry**: **never** blindly retry invalid request-body validation; bad input will not fix itself.

Serious mistake:

~~~java
// Do not do this in a WebFlux controller:
requestMono.subscribe(value -> service.save(value));
return Mono.empty();
~~~

This runs side effects outside the framework-managed HTTP Publisher, preventing errors/cancellations from propagating cleanly to the client and risking race conditions. Use flatMap/map and **return the chain**, letting WebFlux manage subscription.

## 16. Complete Application: Spring Boot 3.3 WebFlux with Validation

This example covers three scenarios:

1. POST /api/signup using @Valid @RequestBody **SignupRequest** directly; per-DTO errors produce WebExchangeBindException.
2. POST /api/signup-async using @Valid @RequestBody **Mono<SignupRequest>**; same validation, but the Publisher flows through the reactive pipeline.
3. GET /api/page?page=0 using **@Min directly on a method parameter**; illustrating HandlerMethodValidationException in Spring 6.1.

An @RestControllerAdvice handles both exception types separately and produces clearly formatted error JSON. Tests use real HTTP rather than direct controller method invocation.

### 16.1 Project Structure

~~~text
webflux-validation-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/validation/
    │   ├── ValidationDemoApplication.java
    │   ├── SignupRequest.java
    │   ├── SignupController.java
    │   ├── ValidationErrorResponse.java
    │   └── ApiErrorHandler.java
    └── test/java/com/example/validation/
        └── ValidationHttpTests.java
~~~

### 16.2 settings.gradle

~~~groovy
rootProject.name = 'webflux-validation-demo'
~~~

### 16.3 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Only starter-webflux is included, not starter-web. Java toolchain 17 fits Spring Boot 3.x and Java records. Other dependency versions (Reactor, Netty, Hibernate Validator) are aligned by Spring Boot dependency management; do not force arbitrary versions manually.

### 16.4 ValidationDemoApplication.java

~~~java
package com.example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationDemoApplication.class, args);
    }
}
~~~

### 16.5 SignupRequest.java

~~~java
package com.example.validation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record SignupRequest(
        @NotBlank(message = "name is required")
        @Size(max = 40, message = "name is too long")
        String name,

        @NotBlank(message = "email is required")
        @Email(message = "email format is invalid")
        String email,

        @Min(value = 18, message = "age must be at least 18")
        int age) {
}
~~~

Constraints on Java record components are read by a compatible Bean Validation provider in Spring Boot 3.3. There is no deliverable email verification code and no database. In production applications, business policy checks and email verification are separate steps.

### 16.6 SignupController.java

~~~java
package com.example.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class SignupController {

    @PostMapping(
            path = "/signup",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<SignupResponse>> signup(
            @Valid @RequestBody SignupRequest request) {

        SignupResponse response = new SignupResponse(
                "accepted", request.name(), request.email());

        return Mono.just(ResponseEntity.status(HttpStatus.CREATED)
                .body(response));
    }

    @PostMapping(
            path = "/signup-async",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<SignupResponse> signupAsync(
            @Valid @RequestBody Mono<SignupRequest> request) {

        return request.map(value -> new SignupResponse(
                "accepted", value.name(), value.email()));
    }

    @GetMapping(path = "/page", produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<PageResponse> page(
            @RequestParam(name = "page", defaultValue = "1")
            @Min(value = 1, message = "page must be at least 1")
            int page) {

        return Mono.just(new PageResponse(page));
    }
}

record SignupResponse(String status, String name, String email) {
}

record PageResponse(int page) {
}
~~~

Do **not** add @Validated at the controller class level in this example. We want Spring Framework 6.1 built-in method validation to handle @Min on page; placing @Validated on the class can switch to AOP validation and complicate exception comparison.

### 16.7 ValidationErrorResponse.java

~~~java
package com.example.validation;

import java.util.List;
import java.util.Map;

public record ValidationErrorResponse(
        String code,
        Map<String, List<String>> fieldErrors,
        List<String> globalErrors) {
}
~~~

The response DTO contains no BindingResult, raw FieldError object, or rejectedValue. It only exposes error codes, field names, and messages intentionally selected by the application.

### 16.8 ApiErrorHandler.java

~~~java
package com.example.validation;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ValidationErrorResponse> invalidDto(
            WebExchangeBindException exception) {

        Map<String, List<String>> fields = new TreeMap<>();

        for (FieldError field : exception.getFieldErrors()) {
            String message = field.getDefaultMessage() == null
                    ? "invalid value"
                    : field.getDefaultMessage();

            fields.computeIfAbsent(
                    field.getField(),
                    key -> new ArrayList<>()
            ).add(message);
        }

        List<String> global = exception.getGlobalErrors()
                .stream()
                .map(error -> error.getDefaultMessage() == null
                        ? "invalid object"
                        : error.getDefaultMessage())
                .toList();

        return ResponseEntity.badRequest().body(
                new ValidationErrorResponse(
                        "INVALID_REQUEST", fields, global));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ValidationErrorResponse> invalidMethod(
            HandlerMethodValidationException exception) {

        ValidationErrorResponse error = new ValidationErrorResponse(
                "METHOD_VALIDATION_FAILED",
                Map.of(),
                List.of("method validation failed"));

        return ResponseEntity.status(exception.getStatusCode())
                .body(error);
    }
}
~~~

Explanation:

- invalidDto collects all FieldErrors, including multiple errors on one field.
- TreeMap gives responses a stable key order when reading logs/tests, though clients should not rely on JSON key ordering.
- global holds object-level errors (if any).
- Method validation uses exception.getStatusCode() instead of hardcoding 400, avoiding mistakenly reporting 400 for return-value errors which may be 500.
- In the example, the method validation response intentionally **does not expose internal details**; if an API needs per-field details, read the ParameterValidationResult list per your contract.
- There is no generic handler for every Exception, so HTTP decode errors or other system failures follow standard handling unless a dedicated policy is defined.

### 16.9 ValidationHttpTests.java

~~~java
package com.example.validation;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ValidationHttpTests {

    @LocalServerPort
    private int port;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
    }

    @Test
    void validDtoReturnsCreated() {
        client().post()
                .uri("/api/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "name", "An",
                        "email", "an@example.org",
                        "age", 21))
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.status").isEqualTo("accepted")
                .jsonPath("$.name").isEqualTo("An");
    }

    @Test
    void invalidDtoReturnsStructuredFieldErrors() {
        client().post()
                .uri("/api/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "name", "",
                        "email", "bad",
                        "age", 16))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_REQUEST")
                .jsonPath("$.fieldErrors.name[0]")
                    .isEqualTo("name is required")
                .jsonPath("$.fieldErrors.email[0]")
                    .isEqualTo("email format is invalid")
                .jsonPath("$.fieldErrors.age[0]")
                    .isEqualTo("age must be at least 18");
    }

    @Test
    void invalidReactiveDtoUsesSameValidationContract() {
        client().post()
                .uri("/api/signup-async")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "name", "",
                        "email", "bad",
                        "age", 16))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_REQUEST");
    }

    @Test
    void invalidMethodParameterHasDifferentErrorCode() {
        client().get()
                .uri("/api/page?page=0")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("METHOD_VALIDATION_FAILED");
    }

    @Test
    void validMethodParameterWorks() {
        client().get()
                .uri("/api/page?page=2")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.page").isEqualTo(2);
    }

    @Test
    void malformedJsonIsStillBadRequest() {
        client().post()
                .uri("/api/signup")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"name\":")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void unsupportedMediaTypeIsRejected() {
        client().post()
                .uri("/api/signup")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("invalid")
                .exchange()
                .expectStatus().isUnsupportedMediaType();
    }
}
~~~

The test uses RANDOM_PORT so the HTTP server binds an available port, and WebTestClient.bindToServer() executes **HTTP over real TCP**. Unlike direct unit invocation, this passes through WebFlux's JSON decoder, argument resolvers, Bean Validation, exception handling, and response encoder.

It does not assert a specific default error body for malformed JSON because that is not WebExchangeBindException under the same contract; the test checks only HTTP status 400. If the application adds a global handler for ServerWebInputException, update the test to match that policy.

The results above are **expectations inferred from source code**, not a report of commands executed in the current environment. On other Spring Boot or Spring Framework versions, re-test exception types and default statuses.

## 17. Running the Project and Sending Requests

In the webflux-validation-demo directory:

~~~bash
gradle clean test
~~~

If using Gradle wrapper:

~~~bash
./gradlew clean test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

After tests pass, run:

~~~bash
gradle bootRun
~~~

By default the server typically listens on port 8080 if unconfigured and the port is available.

### 17.1 Valid Request

~~~bash
curl -i -X POST 'http://127.0.0.1:8080/api/signup' \
  -H 'Content-Type: application/json' \
  -d '{"name":"An","email":"an@example.org","age":21}'
~~~

Expected body with HTTP 201:

~~~json
{"status":"accepted","name":"An","email":"an@example.org"}
~~~

### 17.2 Request Failing Three Fields

~~~bash
curl -i -X POST 'http://127.0.0.1:8080/api/signup' \
  -H 'Content-Type: application/json' \
  -d '{"name":"","email":"bad","age":16}'
~~~

Expected HTTP status: 400. Example body:

~~~json
{
  "code": "INVALID_REQUEST",
  "fieldErrors": {
    "age": ["age must be at least 18"],
    "email": ["email format is invalid"],
    "name": ["name is required"]
  },
  "globalErrors": []
}
~~~

In the DTO, each of the three fields has one constraint guaranteed to fail for this sample input. Array ordering when a single field has **multiple** errors should still never become an API contract without an explicit sort rule.

### 17.3 Method Validation Differs from DTO Validation

~~~bash
curl -i 'http://127.0.0.1:8080/api/page?page=0'
~~~

HTTP 400 with a body like:

~~~json
{
  "code": "METHOD_VALIDATION_FAILED",
  "fieldErrors": {},
  "globalErrors": ["method validation failed"]
}
~~~

This case is not a JSON body error and not WebExchangeBindException under Spring Framework 6.1's method validation mechanism.

### 17.4 Malformed JSON Body

~~~bash
curl -i -X POST 'http://127.0.0.1:8080/api/signup' \
  -H 'Content-Type: application/json' \
  -d '{"name":'
~~~

Normally HTTP 400 because JSON decoding failed. Do not assume the custom invalidDto handler will always execute.

### 17.5 Unsupported Content-Type

~~~bash
curl -i -X POST 'http://127.0.0.1:8080/api/signup' \
  -H 'Content-Type: text/plain' \
  -d 'plain text'
~~~

For an endpoint consuming only application/json, HTTP 415 is expected. Do not tweak validation annotations to fix 415: fix Content-Type, codecs, or the endpoint contract.

## 18. Binding Errors vs. Business Validation Errors

Bean Validation typically handles:

- blank name;
- invalid email format;
- age outside min/max;
- length and patterns;
- cross-field constraints when an appropriate custom validator is present.

Business validation typically handles:

- username already exists;
- no signup quota remaining;
- user lacks permission for a tenant;
- order status does not permit updates;
- referenced resource does not exist;
- market conditions or inventory changed.

Do not perform blocking database lookups inside ConstraintValidator and call it non-blocking just because the app runs WebFlux. For dynamic state, isolate business validation in a reactive service/repository returning appropriate statuses such as 409 Conflict, 404 Not Found, or 403 Forbidden per API semantics.

Example:

~~~java
return repository.existsByEmail(request.email())
        .flatMap(exists -> exists
                ? Mono.error(new ResponseStatusException(
                        HttpStatus.CONFLICT, "email already registered"))
                : repository.save(mapToEntity(request)));
~~~

This is service pseudocode with an undefined repository and mapper; it illustrates **dynamic data constraints** and is not a standalone class. An HTTP 409 is not equivalent to WebExchangeBindException.

## 19. Validation Groups and @Validated

Sometimes the same DTO has different rules between creation and update. Jakarta Bean Validation supports **groups**, while Spring provides @Validated to select specific groups.

Conceptual example:

~~~java
interface Create {}
interface Update {}

class Form {
    @NotBlank(groups = Create.class)
    private String password;

    // getters/setters as required by binding
}
~~~

The snippet above only illustrates the group mechanism. When using @Validated(Create.class) on a DTO parameter, the validator evaluates the selected group.

Avoid:

- Placing @Validated at the controller class level arbitrarily if the goal is Spring 6.1 built-in method validation.
- Switching groups and forgetting the Default group; constraints outside the active group may not run.
- Overloading create/update contracts in one DTO to the point API consumers get confused.
- Testing only the happy path without testing each group and exception type.

In many APIs, splitting CreateRequest and UpdateRequest is simpler and less error-prone than overlapping groups.

## 20. Custom Constraints and Global Object Errors

If you need a rule like startDate <= endDate, you can write a class-level Jakarta constraint with a ConstraintValidator. Whether errors land at object level or field level depends on how ConstraintValidatorContext builds violations.

Contract example:

~~~text
BookingRequest:
  startDate: 2026-12-10
  endDate:   2026-12-09
Validation:
  startDate must not be after endDate
~~~

If the validator produces an object-level violation, WebExchangeBindException can contain **globalErrors**. If the validator calls addPropertyNode("endDate"), the error can appear in **fieldErrors.endDate**. Test precisely where errors are placed instead of assuming every custom constraint produces a global error.

In a reactive environment, ConstraintValidator should execute quickly, synchronously, and non-blockingly. Avoid querying databases or making HTTP calls from validators. When external state is needed, use reactive services in the business layer.

## 21. Internationalizing Validation Messages

The sample annotations use fixed English messages:

~~~java
@NotBlank(message = "name is required")
~~~

In multilingual applications, use message keys and resource bundles:

~~~java
@NotBlank(message = "{signup.name.required}")
~~~

Example key in an appropriate resource:

~~~properties
signup.name.required=Name must not be blank
~~~

How bundles are declared, Locale resolution, and interaction between Bean Validation MessageInterpolator and MessageSource depend on Spring Boot configuration. Do not assume simply creating one properties file covers all locales. Check Accept-Language, fallback locales, and stable error codes consumed by clients.

Some APIs prefer returning **error codes** such as NOT_BLANK or EMAIL_INVALID instead of localized prose. Clients can render their own translations; in that case the server must document all error codes.

### ErrorResponse and MessageSource

Spring Framework 6.1 lets you customize message arguments on ErrorResponse, where WebExchangeBindException carries the error list. When standardizing ProblemDetail, MessageSource can be configured to resolve message codes. Keep links handy to inspect Javadoc for your exact version; never expose raw exception.getMessage() directly to clients.

## 22. Preventing Information Disclosure in Error Responses

A binding error can involve sensitive input such as passwords, tokens, addresses, or personal data. In production:

- Never serialize **exceptions** or **BindingResult** directly into public JSON.
- Never return getRejectedValue() or getFieldValue() for arbitrary fields.
- Never include stack traces, internal bean names, or Java packages in responses.
- Never log full request bodies unless a clear sensitive-data redaction policy is enforced.
- Limit JSON request length, parser depth, and codec buffering appropriately.
- Never let clients specify deserialized class names via uncontrolled polymorphic default typing.
- Messages returned to clients should be safe and controlled by error codes.
- When many field errors occur, avoid unbounded response body growth on abnormal inputs; choose sensible API limits.

Note that Bean Validation custom messages can embed dynamic values in some designs. Review message templates and custom validators so sensitive payloads are never inadvertently reflected.

## 23. Body Size, Decoding, and Other Limits

Spring WebFlux codecs can buffer data when decoding objects. A common Boot setting:

~~~properties
spring.codec.max-in-memory-size=256KB
~~~

This property limits certain codec body-aggregation operations, **not** an absolute limit for every HTTP request/stream. If a client sends huge JSON, DataBufferLimitException or an HTTP input/codec error can occur before Bean Validation even starts.

Cases to distinguish:

| Case | Typical Error Stage | Appropriate Action |
| --- | --- | --- |
| Malformed JSON syntax | Decoder | Fix JSON/request body |
| Wrong Content-Type | Mapping/codec | Fix media type |
| Oversized JSON | Buffering/parser/gateway | Configure clear size limits |
| JSON string value for int | Deserialization/binding | Fix data and schema |
| DTO with name="" | Bean Validation | Fix input per @NotBlank |
| @RequestParam @Min(1) page=0 | Method validation | Fix query parameter |
| Unauthorized user | Authentication/authorization | Return 401/403 per security policy |
| Email duplicates database | Business validation | Return 409 or matching API contract |

Do not use a single @ExceptionHandler(WebExchangeBindException.class) expecting to handle all of the cases above.

## 24. WebFlux vs. MVC: Avoiding Confusion Over Identical Annotations

| Aspect | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Front controller | DispatcherServlet | DispatcherHandler |
| Default server in starter | Tomcat | Reactor Netty |
| Reading HTTP body | HttpMessageConverter | HttpMessageReader / reactive codecs |
| @Valid @RequestBody DTO | Yes | Yes |
| Typical DTO argument validation error | MethodArgumentNotValidException | WebExchangeBindException |
| Spring 6.1 method validation | HandlerMethodValidationException | HandlerMethodValidationException |
| Async request argument body | Servlet MVC has different limits/semantics | @RequestBody Mono<T> supported |
| Common test tool | MockMvc | WebTestClient |
| Middleware mechanism | Servlet Filter / HandlerInterceptor | WebFilter / WebExceptionHandler |

Returning Mono or Flux **does not** automatically turn MVC into WebFlux. Spring Boot normally selects MVC when both starter-web and starter-webflux appear. To diagnose unexpected exceptions, verify WebApplicationType, the dependency tree, and the active front controller first.

In MVC applications, use @ExceptionHandler(MethodArgumentNotValidException.class) for MVC argument validation errors; in WebFlux applications, use WebExchangeBindException. Spring Framework 6.1 method-level validation can use the same HandlerMethodValidationException class in both, yet the underlying pipeline and argument resolution remain distinct.

## 25. Debugging and Observing Validation Errors

### 25.1 Verify the Validation Dependency

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Check that spring-boot-starter-validation and Hibernate Validator appear on the runtime classpath. If a dependency is excluded or present only in test scope, production validation behavior can differ.

### 25.2 Enable Targeted Logging

Example in a local environment:

~~~properties
logging.level.org.springframework.web.reactive.DispatcherHandler=DEBUG
logging.level.org.springframework.web.reactive.result.method.annotation=DEBUG
logging.level.org.springframework.web.server.adapter.HttpWebHandlerAdapter=DEBUG
~~~

Depending on version, different loggers emit more or less detail. Never enable TRACE/raw request logging in production just to track down a small validation error; strip tokens or private info before sharing logs.

### 25.3 Suggested Breakpoints

In an IDE with matching Spring Framework sources:

~~~text
RequestMappingHandlerAdapter.handle(...)
InvocableHandlerMethod.getMethodArgumentValues(...)
AbstractMessageReaderArgumentResolver.readBody(...)
ModelAttributeMethodArgumentResolver.resolveArgument(...)
HandlerMethodValidator.applyArgumentValidation(...)
WebExchangeBindException constructor/getBindingResult
ApiErrorHandler.invalidDto(...)
ApiErrorHandler.invalidMethod(...)
~~~

These are suggested inspection points; methods/overloads can change across patch versions. For @RequestBody Mono<T> requests, set breakpoints inside the reactive pipeline/decoder/validator and remember the Publisher may be subscribed after the method returns.

### 25.4 Trace the Processing Order

Place logs/breakpoints at:

1. Did HandlerMapping match the route?
2. Did the HTTP message reader parse JSON?
3. Did the Bean Validation provider actually execute?
4. Which constraint failed—field or global?
5. Is Spring using argument validation or method validation?
6. Which specific exception handler was chosen?
7. Were status/body written and was the response committed?
8. Did the client receive the expected content type, status, body, and field codes?

## 26. Common Design Pitfalls and Fixes

### Pitfall 1: Using @Valid Without a Provider

Symptom: empty name still reaches the service.

Fix: verify spring-boot-starter-validation is on runtimeClasspath and a global validator is properly configured; write negative tests proving constraints actually execute.

### Pitfall 2: Catching MethodArgumentNotValidException in WebFlux

Symptom: WebFlux endpoint throws a validation error, yet the MVC-oriented @ExceptionHandler does not trigger.

Fix: use WebExchangeBindException from the WebFlux package; if direct method constraints exist, also handle HandlerMethodValidationException.

### Pitfall 3: Handling Only WebExchangeBindException, Ignoring Method Validation

Symptom: invalid DTOs return custom JSON, but /api/page?page=0 returns a different error format.

Fix: understand Spring Framework 6.1 method validation and build a consistent error response across both sources.

### Pitfall 4: Forgetting to Validate Nested DTOs

Symptom: outer request passes even when inner Address.street is empty.

Fix: add @Valid on nested properties and test missing/null nested objects.

### Pitfall 5: Returning the Whole BindingResult

Symptom: response includes rejectedValue, objectName, stack metadata, or sensitive data.

Fix: map FieldError/ObjectError to a public DTO using approved error codes and messages.

### Pitfall 6: Handling via Mono.error and Subscribing Manually

Symptom: errors do not reach the HTTP client, empty 200 responses, race conditions.

Fix: return the reactive chain; use onErrorResume or @RestControllerAdvice.

### Pitfall 7: Assuming Malformed JSON Is WebExchangeBindException

Symptom: syntactically invalid JSON bypasses the invalidDto handler.

Fix: distinguish decoder exceptions from Bean Validation; write dedicated tests for both.

### Pitfall 8: Hardcoding 400 for Every Method Validation Error

Symptom: a controller return value violates a constraint, yet the system blames client input.

Fix: use ex.getStatusCode() or a clear classification policy; return-value errors are normally server responsibility.

### Pitfall 9: Forgetting BindingResult Immediately After the Parameter

Symptom: code intends to handle errors locally, yet Spring still throws an exception.

Fix: place the argument in the right position or use global advice; with Mono<T> use reactive error operators.

### Pitfall 10: Enabling Class-Level @Validated and Expecting Built-In Method Validation

Symptom: exception type differs from expectations when AOP intercepts the method.

Fix: understand AOP validation vs. Spring Framework 6.1 built-in validation; remove class-level @Validated when using the built-in mechanism as documented.

### Pitfall 11: Using Constraints for Dynamic Business Policies

Symptom: validator runs blocking database queries on the Netty event loop, causing latency and timeouts.

Fix: keep syntax validation in Bean Validation; run business checks in a reactive service/repository.

### Pitfall 12: Failing to Test Multiple Errors on One Field

Symptom: response returns only one error because getFieldError() was used instead of getFieldErrors().

Fix: use a field → error list structure and add integration tests submitting multiple invalid fields at once.

### Pitfall 13: Assuming Validation Guarantees Authorization

Symptom: properly formatted tenantId still permits access to the wrong tenant.

Fix: Spring Security/reactive security chains and service/resource-level policies enforce access control.

### Pitfall 14: Writing Tests Calling the Controller Directly

Symptom: new SignupController().signup(...) does not run HTTP codecs or validators.

Fix: use WebTestClient with a WebFlux context or real HTTP; direct invocation tests only isolated method logic.

## 27. Final Practical Checklist

1. Confirm the application runs the Spring WebFlux reactive stack.
2. Confirm spring-boot-starter-validation and a version-aligned Jakarta Validation provider are present.
3. Request DTOs have clear, testable constraints.
4. @Valid/@Validated are placed appropriately on method arguments.
5. Distinguish @Valid on objects from direct @Min/@NotBlank on method parameters.
6. Understand when WebExchangeBindException and HandlerMethodValidationException occur.
7. Never treat malformed JSON, 415, or 404 as Bean Validation errors.
8. Iterate both fieldErrors and globalErrors when building error responses.
9. Never return rejected values, tokens, stack traces, or internal metadata.
10. Use @RestControllerAdvice or ResponseEntityExceptionHandler under a single consistent contract.
11. Keep HTTP statuses accurate: 400 for invalid input, 500 for server return validation failure, 401/403 for security when applicable.
12. With Mono<DTO>, let the framework subscribe; never call subscribe()/block() manually.
13. When using BindingResult, place it immediately after a supported synchronous parameter.
14. Never run blocking I/O inside custom constraints or exception handlers.
15. Test valid DTO, invalid DTO, invalid reactive DTO, method validation, malformed JSON, and wrong Content-Type.
16. Check null/missing/nested objects/validation groups per your actual contract.
17. Set body/codec limits and sanitize sensitive logs.
18. Verify API versions and docs before upgrading Spring Framework 6.x to 7.x.

## 28. Summary

**WebExchangeBindException** is the **object-argument-level** binding/validation error in Spring WebFlux, normally appearing with @Valid @RequestBody, @ModelAttribute, or @RequestPart. It exposes BindingResult, field errors, and global errors, enabling APIs to return HTTP 400 with actionable client guidance without exposing raw input. With Spring Framework 6.1, **HandlerMethodValidationException** is the separate path when method-level constraints apply; applications should understand and test both rather than catching only WebExchangeBindException.

From a design standpoint, validation must stay separate from decoding, authentication/authorization, and dynamic business rules. Real WebFlux HTTP tests, stable error body contracts, non-blocking reactive pipelines, and excluding sensitive rejected values from responses form the foundation of maintainable APIs.

## 29. References

- Spring Framework — WebFlux Validation: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html
- Spring Framework — WebFlux @RequestBody: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework — WebFlux @ModelAttribute: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/modelattrib-method-args.html
- Spring Framework — WebFlux Error Responses: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- Spring Framework 6.1 — WebExchangeBindException API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html
- Spring Framework 6.1 — HandlerMethodValidationException API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework 6.1 — ResponseEntityExceptionHandler API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/reactive/result/method/annotation/ResponseEntityExceptionHandler.html
- Spring Boot 3.3 — Validation: https://docs.spring.io/spring-boot/3.3/reference/io/validation.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Jakarta Bean Validation Specification: https://jakarta.ee/specifications/bean-validation/
