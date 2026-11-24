# Return-Value Constraints and Server-Side Contract Errors in Spring MVC

## 1. Why validate return values as well?

Usually when thinking about validation in Spring MVC, we think of validating data **sent in by the client**: a `@RequestBody` missing a name, a negative `@RequestParam`, or a form with a malformed email. However, Jakarta Validation also supports checking **method return values**. This is a fundamentally different contract:

- **Input constraint:** requires the caller/client to send data meeting conditions. If the client sends bad input, the response is typically **400 Bad Request**.
- **Return-value constraint:** the method **already ran**, yet the result produced by the server failed to meet its published contract. This is normally a **server-side contract bug or programming/operational error**, so the appropriate HTTP response is typically **500 Internal Server Error**, not 400.

Example of a REST controller returning receipt data:

```java
@GetMapping("/receipts/{id}")
@NotNull
@Valid
public ReceiptView getReceipt(@PathVariable @Min(1) long id) {
    return receiptService.load(id);
}
```

This is an illustrative method snippet, assuming `ReceiptView` has field constraints and `receiptService` exists. Two validation directions can happen on the same method:

1. `@Min(1)` on `id` checks the **input**. If the URL contains `/receipts/0`, the request fails the contract required by the controller.
2. `@NotNull` on the **method itself** requires a non-null return value.
3. `@Valid` on the **method itself** requests checking constraints inside the returned `ReceiptView` object. For instance, the returned DTO has `@NotBlank reference` yet contains `reference=""`.
4. If input is invalid, the server should return 400. If the returned object is invalid, the server should not blame the client; that is a server-side contract failure, so report 500 and do not return the invalid object as successful data.

**Scope:** Spring Framework 6.1–6.2, Spring Boot 3.x, Java 17+, Jakarta Validation 3.x, Servlet Spring MVC. This lesson also distinguishes built-in MVC method validation from service-layer AOP method validation. In Spring Framework prior to 6.1, controller method validation behavior and required configuration differed significantly; do not apply all examples verbatim to Spring 5 or WebFlux.

## 2. What is a "server-side contract" really?

### 2.1. Preconditions and postconditions

A method can define:

- **Precondition / input condition:** must hold **before** the method body is invoked; for example `quantity >= 1`.
- **Postcondition / output condition:** must hold **after** the method body returns; for example, the receipt code must be non-blank and the total line count must be positive.

Illustration:

```java
public record ReceiptView(
        @NotBlank String reference,
        @Positive int lineCount
) {}
```

When the server creates `new ReceiptView("RCPT-17", 2)`, the object satisfies the constraints. When the server creates `new ReceiptView(" ", 0)`, the object **violates the output contract**, even if the incoming request was completely valid.

There are three related yet independent layers:

| Layer | Data checked | Who must fix on error? |
| --- | --- | --- |
| MVC input validation | Query/path/form/JSON after conversion, parameter constraints | Typically the client |
| MVC return-value validation | Value returned by the handler method | Server / system developers |
| Service/domain invariant | Business outcomes, transaction state, and persisted data | Cause-dependent; usually service/domain responsibility |

**A return-contract failure is not a user input error.** The client cannot know about or fix a blank `reference` caused by faulty server mapping. Returning HTTP 400 for this error distorts API semantics, skews metrics, and misleads clients into retrying or editing an already valid request.

### 2.2. Constraints on the method vs. constraints on the DTO

```java
@NotNull
@Valid
public ReceiptView load() {
    // ...
}
```

- `@NotNull` here is a **direct constraint on the method's return value**.
- `@Valid` here is **cascading validation**: descending into the returned object to check its internal constraints.
- `@Valid` **does not forbid null by itself**. In Jakarta Validation, when cascading encounters null, there is no child object to inspect; to forbid null, use `@NotNull`.
- `@NotNull` **does not deeply inspect** fields `reference` or `lineCount`. Checking them requires cascading with `@Valid`.
- Constraints on `ReceiptView` can still be checked when the DTO is used elsewhere, yet annotating the DTO **does not guarantee** every method returning it runs validation automatically without an activation point.

### 2.3. Validation cannot replace every invariant

Returning `@Positive int lineCount` catches a zero result when the domain requires a positive number. However, rules such as "total equals the sum of line items", "only authorized users may view the receipt", and "never leak payment credentials" require business checks, authorization, and careful query design.

Similarly, a return value passing `@NotNull`/`@NotBlank` does not prove the data is **semantically correct**. Bean Validation is a helpful contract guardrail, not a replacement for full domain design.

## 3. How does standard Jakarta Validation support return-value checking?

### 3.1. Common annotations

You can place constraints directly on non-`void` methods:

```java
@NotNull
public ReceiptView load() { /* ... */ }

@Positive
public long calculateCount() { /* ... */ }

@NotBlank
public String createReference() { /* ... */ }
```

The three methods above are **illustrative snippets only**. Real code needs method bodies returning values of the matching type along with proper packages/imports.

Placing a constraint on a method means it applies to the **result**, not the parameters. `@Min(1)` on an `id` parameter remains an input check.

With a DTO:

```java
@NotNull
@Valid
public ReceiptView load() {
    return new ReceiptView(" ", 0);
}
```

When method validation is active and the `Default` group is selected, the provider can detect **two nested violations**: `reference` failing `@NotBlank` and `lineCount` failing `@Positive`.

### 3.2. ExecutableValidator: plain Jakarta API

Jakarta Validation defines `ExecutableValidator` for validating methods and constructors:

```java
ExecutableValidator executable =
        validator.forExecutables();

executable.validateParameters(
        target, method, argumentValues);

executable.validateReturnValue(
        target, method, returnedValue);
```

This is an **API illustration**, assuming `validator`, `target`, `method`, `argumentValues`, and `returnedValue` are already prepared. These methods belong to `jakarta.validation.executable`; they do not depend specifically on Spring or Hibernate Validator.

Conceptually, after the method returns a result, the framework can call `validateReturnValue(...)` to obtain `Set<ConstraintViolation<T>>`. The provider reports violations, while the **framework** decides which exception to throw and which HTTP status to assign.

### 3.3. Property paths for return-value errors

Violations on a method return usually produce a path containing a method node and a **`<return value>`** node, followed by child properties in cascading cases. Conceptual example:

```text
getReceipt.<return value>.reference
getReceipt.<return value>.lineCount
```

Actual strings may include method details and different node names depending on provider/version. Use `ConstraintViolation#getPropertyPath()` metadata to locate errors rather than treating translated messages as stable classification codes.

`jakarta.validation.Path.Node` defines the **`RETURN_VALUE`** node kind. When debugging, seeing this node tells you the constraint concerns output—not every property path comes from a request field.

## 4. Where does Spring MVC 6.1+ trigger return-value validation?

Spring Framework 6.1 added **built-in method validation for MVC handler methods**. It supports constraints placed directly on **method parameters** or **return values** and can cascade via `@Valid`. For controllers not intercepted by AOP method validation, Spring checks:

```text
HTTP request
    |
    v
Routing / argument resolution / deserialization
    |
    v
Method validation on parameters
    |  if invalid -> HandlerMethodValidationException (input)
    v
Controller method is invoked
    |
    v
Controller return value
    |
    v
Method validation on return value
    |  if invalid -> HandlerMethodValidationException (return)
    v
Return-value handler / HttpMessageConverter / response
```

Specifically:

- `@Min(1)` on `@PathVariable long id` can trigger method validation for input.
- `@NotNull` on the method return is also a **direct constraint** and signals MVC to perform method validation.
- `@Valid` on the method return requests cascading. For object results, combining `@NotNull @Valid` is explicit: non-null and check nested fields.
- When a handler has direct method constraints, **method validation** can replace per-argument validation because it covers both parameter constraints and cascaded constraints.
- With only `@Valid` on a command-object parameter and no direct constraints, Spring MVC can use argument-level validation, typically raising `MethodArgumentNotValidException`; do not assume every `@Valid` produces `HandlerMethodValidationException`.

In Spring MVC, method validation errors are typically reported via:

```java
org.springframework.web.method.annotation
        .HandlerMethodValidationException
```

This exception provides `isForReturnValue()` and the corresponding status:

| Violation | `isForReturnValue()` | Default HTTP status |
| --- | --- | --- |
| Constraint on input | `false` | **400 Bad Request** |
| Constraint on method result | `true` | **500 Internal Server Error** |

This 400/500 behavior is an **intentional classification** by Spring. Never write an `@ExceptionHandler(HandlerMethodValidationException.class)` that returns 400 for every case, as doing so hides server bugs.

### 4.1. Role of class-level `@Validated` on controllers

Spring MVC 6.1+ has an important caveat: if `@Validated` is placed on the **controller class**, method validation may execute via an **AOP proxy** instead of MVC's built-in mechanism. Spring documentation recommends **removing class-level `@Validated` from controllers** when wanting the new built-in method validation.

Therefore, the runnable examples below **do not** place `@Validated` on the controller type. This makes `HandlerMethodValidationException` cleanly observable.

### 4.2. What about `@RequestBody` and `@RequestPart`?

If a controller has:

```java
@PostMapping("/receipts")
public void submit(
        @Valid @RequestBody ReceiptInput input) {
    // ...
}
```

and `ReceiptInput` is a command object, Spring normally validates the argument on its own after deserialization, throwing `MethodArgumentNotValidException` if input is invalid. However, if the same handler adds a direct constraint on a parameter or return value, built-in method validation can be chosen, changing the exception path.

This lesson focuses on **return values**, so `BindingResult` is not used to "catch" return errors. `BindingResult`/`Errors` immediately after a parameter handles **argument binding/validation**, not return-value contract errors occurring **after the method body finishes**.

## 5. Hands-on project: validating the contract before returning JSON

We build a REST application with one endpoint:

```text
GET /api/receipts/{id}
```

Intentional scenarios:

- `id = 7` → valid input, returns valid DTO → HTTP 200.
- `id = 0` → `@Min(1)` on path parameter fails → HTTP 400.
- `id = 8` → service/controller produces DTO with `reference=" "` and `lineCount=0` → HTTP 500.
- `id = 9` → controller returns `null`, violating return `@NotNull` → HTTP 500.

Special values 8 and 9 exist only to demonstrate detecting **server-side contract failures**. Production apps must fix the source generating bad data rather than intentionally returning broken objects.

### 5.1. Structure and dependencies

The project uses Spring Boot 3.3.6, Spring Framework 6.1.x, and Java 17.

```text
return-contract-demo/
  settings.gradle
  build.gradle
  src/
    main/java/com/example/returncontract/
      ReturnContractApplication.java
      ReceiptView.java
      ReceiptController.java
      ApiExceptionAdvice.java
    test/java/com/example/returncontract/
      ReceiptControllerTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'return-contract-demo'
```

`build.gradle`:

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

`spring-boot-starter-web` provides Spring MVC, while `spring-boot-starter-validation` provides the Jakarta Validation provider (typically Hibernate Validator). `spring-boot-starter-aop` is not needed for **built-in MVC method validation** in this example. If implementing service-level AOP validation later, proxy/config behavior must be tested separately.

### 5.2. Application

File `src/main/java/com/example/returncontract/ReturnContractApplication.java`:

```java
package com.example.returncontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReturnContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReturnContractApplication.class, args);
    }
}
```

### 5.3. DTO defining the output contract

File `src/main/java/com/example/returncontract/ReceiptView.java`:

```java
package com.example.returncontract;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record ReceiptView(
        @NotBlank String reference,
        @Positive int lineCount
) {}
```

Constraints:

- `@NotBlank` on `reference`: not null, not empty, not whitespace-only.
- `@Positive` on `lineCount`: number must be greater than 0.
- An immutable record defines the result at construction time, yet **does not automatically run validation** inside the constructor. You can construct `new ReceiptView(" ", 0)` in Java; it is only flagged when a Bean Validation trigger runs.

This is crucial: `record` and constraint annotations are separate tools. Never claim a DTO is "safe" merely because `@NotBlank`/`@Positive` appear on record components.

### 5.4. Controller with constraints on parameter and return value

File `src/main/java/com/example/returncontract/ReceiptController.java`:

```java
package com.example.returncontract;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ReceiptController {

    // @Min checks input; @NotNull and @Valid check return.
    @GetMapping("/receipts/{id}")
    @NotNull
    @Valid
    public ReceiptView getReceipt(
            @PathVariable("id") @Min(1) long id) {

        if (id == 8) {
            // Intentionally violate two constraints inside the DTO.
            return new ReceiptView(" ", 0);
        }

        if (id == 9) {
            // Intentionally violate the @NotNull constraint on the method.
            return null;
        }

        return new ReceiptView("RCPT-" + id, 2);
    }
}
```

Here **there is no class-level `@Validated`**, so the controller uses Spring MVC 6.1+'s built-in method validation. With `id = 0`, input fails `@Min(1)`; the method body should not run as a valid invocation. With `id = 8` or `9`, the method runs and returns an object/`null` violating constraints; Spring can block the invalid result before JSON writing occurs.

Returning `null` from a `@RestController` handler should not be used to represent "not found" in real APIs. When a resource is not found, return an explicit business result/exception such as HTTP 404; the `id = 9` branch exists solely to test return `@NotNull`.

### 5.5. Exception handler separating input 400 and output 500

File `src/main/java/com/example/returncontract/ApiExceptionAdvice.java`:

```java
package com.example.returncontract;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<Map<String, String>> handleMethodValidation(
            HandlerMethodValidationException exception) {

        if (exception.isForReturnValue()) {
            // Return-value violation: server-side contract failure.
            // Production: log/metric/correlation-id in a safe place.
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of(
                            "code", "SERVER_CONTRACT_VIOLATION",
                            "message", "Unable to complete request"
                    ));
        }

        // Input violation: request data failed conditions.
        return ResponseEntity
                .badRequest()
                .body(Map.of(
                        "code", "INVALID_REQUEST",
                        "message", "Invalid request parameter"
                ));
    }
}
```

The handler's most important check is **`exception.isForReturnValue()`**. Spring already distinguishes return vs. input inside the exception itself and defaults to HTTP 500/400; the example defines custom JSON bodies while **preserving error semantics**.

In production, record server-side return-contract failures in logs/metrics with a request ID and investigation context; do not echo internal property paths, internal values, or stack traces to clients. Even if a constraint message is useful to developers, end users have no way to fix a broken output DTO.

### 5.6. HTTP requests and outcomes

Start the app:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

**Valid output:**

```bash
curl -i http://localhost:8080/api/receipts/7
```

Expected HTTP **200 OK** and JSON:

```json
{
  "reference": "RCPT-7",
  "lineCount": 2
}
```

**Invalid input parameter:**

```bash
curl -i http://localhost:8080/api/receipts/0
```

Expected HTTP **400 Bad Request**:

```json
{
  "code": "INVALID_REQUEST",
  "message": "Invalid request parameter"
}
```

**Server builds invalid DTO:**

```bash
curl -i http://localhost:8080/api/receipts/8
```

Expected HTTP **500 Internal Server Error**:

```json
{
  "code": "SERVER_CONTRACT_VIOLATION",
  "message": "Unable to complete request"
}
```

**Server returns null violating contract:**

```bash
curl -i http://localhost:8080/api/receipts/9
```

Expected HTTP **500 Internal Server Error** with the same `SERVER_CONTRACT_VIOLATION` code.

These JSON bodies are the **contract defined by `ApiExceptionAdvice` in the demo**, not a mandatory default shape across all Spring apps. Removing the advice lets Spring MVC use its default error response or another handler depending on configuration. The foundational rule to remember is that **input** and **return** errors are fundamentally different in nature.

## 6. Testing via MockMvc: identifying the responsible side

File `src/test/java/com/example/returncontract/ReceiptControllerTest.java`:

```java
package com.example.returncontract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReceiptControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validReturnValueProducesHttp200() throws Exception {
        mvc.perform(get("/api/receipts/7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.reference").value("RCPT-7"))
            .andExpect(jsonPath("$.lineCount").value(2));
    }

    @Test
    void invalidInputProducesHttp400() throws Exception {
        mvc.perform(get("/api/receipts/0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
    }

    @Test
    void invalidNestedOutputProducesHttp500() throws Exception {
        mvc.perform(get("/api/receipts/8"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code")
                    .value("SERVER_CONTRACT_VIOLATION"));
    }

    @Test
    void nullOutputProducesHttp500() throws Exception {
        mvc.perform(get("/api/receipts/9"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code")
                    .value("SERVER_CONTRACT_VIOLATION"));
    }
}
```

Run:

```bash
./gradlew test
```

All **four tests are expected to pass** in the example setup. They distinguish:

- Happy path with a contract-compliant DTO.
- Input error caused by the caller → 400.
- Nested bean failure inside the return value → 500.
- Null return value violating `@NotNull` → 500.

`MockMvc` tests verify **real MVC behavior**, rather than just calling `new ReceiptView(...)` and inspecting annotations. A manually constructed DTO without `Validator#validate` or method validation will not report violations on its own.

If you want to verify the exact exception instead of only the HTTP body, tests can check that `MvcResult#getResolvedException()` is `HandlerMethodValidationException` and `isForReturnValue()` has the expected value. Do not inspect raw interpolated messages to guess input vs. output, as language/bundles can change.

## 7. Distinguishing output validation from input validation

### 7.1. Shared ground: using Jakarta constraints

Both input and output can use:

```java
@NotNull
@NotBlank
@Size
@Positive
@Valid
```

The difference lies **not in annotation names** but in **constraint placement** and **lifecycle phase**.

Example:

```java
@PostMapping("/calculate")
@Positive
public int calculate(
        @RequestParam @Min(1) int quantity) {
    return quantity - 5;
}
```

This is an illustrative method. With `quantity = 1`, input satisfies `@Min(1)`, yet the method returns `-4`, violating `@Positive` on the return value. You cannot call this "the user sent a wrong quantity". Responsibility lies with `calculate`'s logic or the contract the server published.

### 7.2. Return values are checked after side effects

Example of a service:

```java
@Transactional
@NotNull
public ReceiptView saveReceipt(ReceiptInput input) {
    repository.save(...);
    return null;
}
```

This is **illustrative pseudocode**, not standalone compilable code: `ReceiptInput`, `repository`, and `@Transactional` are assumed to exist in the application. The key point is that return validation executes **after the method body runs**. Database writes, message publishing, or external calls may already have happened.

**Do not conclude that return-value constraints automatically guarantee rollback.** With Spring AOP, transaction advice and method-validation advice have a specific ordering; an error raised after transaction advice completes may not roll back an already committed transaction. External side effects outside the database—such as emails, Kafka, or object storage—are not undone just because a method return violated Bean Validation.

Therefore, enforce critical invariants inside service/domain logic before writing data; treat return validation as a **detection guardrail**, not your sole transaction-integrity mechanism.

### 7.3. Return validation does not guarantee the response is completely safe

For handlers returning plain DTOs, Spring MVC can validate the method return before serialization and body writing. Other output types need separate consideration:

- `ResponseEntity<Dto>` is a response wrapper; a constraint placed on the method may apply to the **wrapper** rather than automatically descending into the inner `Dto`. Do not assume `@Valid` always unwraps every wrapper without an appropriate value extractor.
- `StreamingResponseBody`, `ResponseBodyEmitter`, SSE, and streaming responses can start writing data incrementally; detecting an error after the response is **already committed** cannot simply flip the HTTP status to 500.
- `Callable`, `CompletableFuture`, and async types have distinct lifecycles/processing paths; test your exact version and adapters before claiming method-return constraints cover the final outcome.
- Jackson serialization can still fail after return validation PASSES. A DTO valid under Bean Validation does not guarantee converter serialization succeeds.

The demo intentionally returns a **direct synchronous record DTO** so the validation point is clearly observable.

## 8. Service method validation with AOP: a separate path

At the regular Spring service layer, method validation via an **AOP proxy** differs from built-in MVC method validation.

**Illustrative** example of a Spring-managed service:

```java
package com.example.returncontract;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class ReceiptService {

    @NotNull
    @Valid
    public ReceiptView fetch(boolean breakContract) {
        if (breakContract) {
            return new ReceiptView(" ", 0);
        }
        return new ReceiptView("RCPT-SERVICE", 3);
    }
}
```

To enable service method validation, the application needs a Jakarta Validation provider, `MethodValidationPostProcessor`, and a suitable AOP proxy. In Spring Boot with the validation starter, the processor is normally auto-configured; plain Java/Spring Framework apps may need to register it manually. When using AOP proxying, ensure required AOP dependencies are present; `spring-boot-starter-aop` can be added in service-level setups to make the intent explicit.

When calling the **Spring bean proxy** of `ReceiptService`:

```java
receiptService.fetch(true);
```

default AOP method validation normally throws:

```java
jakarta.validation.ConstraintViolationException
```

With `MethodValidationPostProcessor#setAdaptConstraintViolations(true)`, another path is:

```java
org.springframework.validation.method.MethodValidationException
```

Meanwhile, the built-in MVC 6.1+ controller in our main example uses:

```java
org.springframework.web.method.annotation.HandlerMethodValidationException
```

Distinctions:

| Trigger point | Mechanism | Typical exception |
| --- | --- | --- |
| Built-in Spring MVC method validation | Handler method (Framework 6.1+) | `HandlerMethodValidationException` |
| Default Spring service method validation | AOP proxy + type-level `@Validated` | `ConstraintViolationException` |
| Spring service method validation with adapter | AOP + `adaptConstraintViolations=true` | `MethodValidationException` |
| Direct Jakarta API | `Validator#forExecutables()` | Returns violation set; caller decides action |
| Standalone `@Valid @RequestBody` command object | Argument validation | `MethodArgumentNotValidException` |

**Never write a global handler catching every `ConstraintViolationException` and returning 400 by default.** If that exception is a service return-contract violation, 400 misassigns blame. An AOP exception can hold multiple `ConstraintViolation`s covering both inputs and outputs; classify by origin, property path, metadata, and boundary contract.

### 8.1. Self-invocation and proxy caveats

Example:

```java
@Service
@Validated
public class InternalCallExample {

    public void outer() {
        inner();  // internal call, does not go through proxy
    }

    @NotNull
    public String inner() {
        return null;
    }
}
```

This is a **counterexample** highlighting a limitation. Calling `this.inner()` normally bypasses the Spring AOP proxy, so return validation on `inner` is not applied by the interceptor. Similarly, objects instantiated with `new` outside the Spring container are not protected by AOP, and `private`/`final` methods have interception limitations depending on proxy type.

If an output contract is a mandatory business invariant, **do not rely solely on AOP annotations** on methods that may be called internally; design domain logic and tests accordingly.

### 8.2. Do not confuse service class-level `@Validated` with controllers

For services, type-level `@Validated` is the standard way to select beans for `MethodValidationPostProcessor`. For Spring MVC 6.1+ controllers, the same class-level annotation can switch validation to an **AOP proxy**, diverging from built-in MVC validation. Thus, the advice "every class with constraints needs `@Validated`" is false.

## 9. Group-based return-value validation

Like input validation, Jakarta Validation supports **validation groups** for outputs. Example:

```java
public interface PublicApi {}

public record ReceiptView(
        @NotBlank(groups = PublicApi.class) String reference,
        @Positive(groups = PublicApi.class) int lineCount
) {}
```

If return validation runs only with `Default`, constraints belonging exclusively to `PublicApi` are **not evaluated automatically**. You can select groups via framework-supported mechanisms or directly through the Jakarta API:

```java
ExecutableValidator executable = validator.forExecutables();

Set<ConstraintViolation<ReceiptService>> violations =
        executable.validateReturnValue(
                receiptService,
                method,
                returned,
                PublicApi.class
        );
```

This snippet uses `jakarta.validation.executable.ExecutableValidator`, `jakarta.validation.ConstraintViolation`, and `java.util.Set`; `validator`/`receiptService`/`method`/`returned` are assumed ready. In real applications, pick groups explicitly per API contract and verify whether your Spring version/validation path reads `@Validated(Group.class)` at the intended location.

**Group sequences** (`@GroupSequence`) define ordering across groups; unlike an unordered array of groups, they enforce checking order. Avoid accidentally skipping `Default` constraints when switching to a custom group.

Also do not confuse `@Valid` with group-specific constraints: `@Valid` is a cascading marker and has no `groups` attribute. To convert groups when cascading into nested objects, Jakarta Validation provides `@ConvertGroup` at valid cascade sites; use it only when business requirements clearly call for it.

## 10. How to handle server-side contract errors properly?

### 10.1. Status codes: do not blame the client

| Outcome | Usually appropriate HTTP | Reason |
| --- | --- | --- |
| Client sends `id=0` violating `@Min(1)` | 400 | Caller can fix input |
| Client sends malformed JSON | 400 | Parser could not read input |
| Controller returns DTO with blank field violating `@NotBlank` | 500 | Server broke output contract |
| Service returns null violating `@NotNull` | 500 | Server failed postcondition |
| Resource does not exist (valid business outcome) | 404 | Not necessarily a contract error |
| Client not authorized to view resource | 403/404 per policy | Authorization differs from Bean Validation |
| Serialization fails | Typically 500 if response uncommitted | Can happen after validation |
| Async/streaming error after response committed | Cannot always change status | Needs dedicated protocol/observability |

HTTP 500 does not reveal the **detailed cause** of the bug. It signals that the system could not fulfill the request per its contract. When a return constraint reflects an unmet business invariant, investigate data generation, DTO mapping, services, and transactions instead of telling the frontend to "fix a field" that did not originate from the frontend.

### 10.2. Stable error body without leaking data

A suitable client response:

```json
{
  "code": "SERVER_CONTRACT_VIOLATION",
  "message": "Unable to complete request"
}
```

You can include a `correlationId`/trace ID if logging is designed properly. Never return:

- Contents of unvalidated objects such as tokens or personal data.
- Stack traces, internal Java classes, internal field paths, SQL, or service endpoints.
- Raw `ConstraintViolation#getInvalidValue()` for sensitive data.
- EL/validator messages that may embed request data or internals.

On the server side, log **enough cause to investigate**, including request ID, method, violation kind (return/input), timestamp, deployment version, and context scrubbed of sensitive data.

### 10.3. Alerts and metrics

Return-contract errors should be treated as **bugs to detect and fix**:

1. Dedicated metric such as `server_return_contract_violations_total`, grouped by endpoint/service.
2. Error logs with correlation ID to trace between controller and service.
3. Alerts on rising error rate/volume, avoiding log spam when a single bug fires in bursts.
4. Regression tests for the exact object/path/condition that triggered the violation.
5. Review DTO mapping and commit/serialization ordering when side effects exist.

Never use return validation as a silent mechanism to "turn server errors into default data". Replacing `null` with a placeholder object just to satisfy `@NotNull` can mask business bugs if that object does not reflect reality.

## 11. Assumptions that easily go wrong

**Mistake 1 — Treating every validation error as an input error.** Return constraints are placed by the server on server-produced values; failures are usually 500, not 400.

**Mistake 2 — Putting only `@Valid` on a return value and thinking null is forbidden.** Cascading skips null. Use `@NotNull` if the contract requires a non-null result.

**Mistake 3 — Putting only `@NotNull` on a return value and thinking nested fields are checked.** `@NotNull` only guarantees an object exists. Add `@Valid` to cascade into field constraints.

**Mistake 4 — Missing a method validation trigger.** Annotations on methods may exist in source code, yet calls outside a Spring proxy or manual validator will not run checks. Spring MVC 6.1+ has its own built-in path; service AOP requires a proper bean/proxy.

**Mistake 5 — Putting `@Validated` on every controller.** Controller class-level `@Validated` can switch to AOP, changing exceptions/lifecycles and breaking tests expecting `HandlerMethodValidationException`.

**Mistake 6 — Catching `HandlerMethodValidationException` and always returning 400.** Must check `isForReturnValue()`; output errors default to 500.

**Mistake 7 — Catching every `ConstraintViolationException` and returning 400.** In service AOP, the exception may be a postcondition violation. Classify properly by boundary and contract.

**Mistake 8 — Confusing `@Valid @RequestBody` with return validation.** One is Bean Validation on the deserialized request object; the other is method validation on the controller's returned value.

**Mistake 9 — Relying on violation count or order to classify root causes.** Constraint order is not guaranteed; use node kind/path and metadata instead of guessing from the first item.

**Mistake 10 — Thinking return validation rolls back all side effects.** The method has already executed; transaction advice/async/events can have separate lifecycles. Enforce invariants before commit and understand AOP advice ordering.

**Mistake 11 — Assuming `@Valid` deeply inspects every `ResponseEntity`/async wrapper.** Method return type contracts and value extractor support differ from payloads inside wrappers. Test the exact return type.

**Mistake 12 — Claiming every return error becomes 500 even after response commit.** With streaming/async, the status may already be sent; design pre-/post-commit checks and error reporting accordingly.

**Mistake 13 — Putting `@NotNull` on a primitive return and thinking it checks null.** Primitive types cannot be null; rules like `@Positive`/`@Min` are more useful for numeric checks.

**Mistake 14 — Using validation in place of 404 and authorization.** Missing resources, expired tokens, and insufficient permissions carry distinct semantics; do not turn valid business-flow outcomes into contract violations.

**Mistake 15 — Testing beans with `new` and claiming MVC was tested.** Built-in Spring MVC tests must invoke through `MockMvc`/`DispatcherServlet`; service AOP tests must invoke through a Spring bean proxy. Calling Java methods directly does not prove interceptors ran.

**Mistake 16 — Returning internal constraint details to clients.** Diagnostics belong in protected logs/metrics; clients receive status 500 and a generic message.

## 12. Checklist when designing endpoints with a return contract

1. Clearly define **preconditions** and **postconditions**: what the client must supply, what the server promises to return.
2. Put input constraints on DTOs/parameters; put appropriate return constraints on the **method** or output DTO.
3. If the return must be a non-null object with valid fields, consider `@NotNull @Valid` on the method, with corresponding constraints on fields/record components.
4. For Spring MVC 6.1+, choose built-in method validation where suitable; avoid adding class-level `@Validated` on controllers out of habit.
5. For services, verify `MethodValidationPostProcessor`, Spring AOP proxies, self-invocation, and default exception types.
6. Classify exceptions/statuses: `HandlerMethodValidationException.isForReturnValue()` is key to distinguishing HTTP 500 from 400 in MVC.
7. Never return error messages containing internal data; provide stable API error codes, request correlation IDs, and safe logging.
8. Do not replace domain/transaction logic with return validation; verify critical invariants before committing or executing side effects.
9. When using `ResponseEntity`, async/streaming, or custom converters, explicitly test validation/serialization timing and whether status is already committed.
10. Write tests for 200 (valid output), 400 (invalid input), 500 (invalid output), null results, and nested results.
11. When adding validation groups, verify the right group is selected on the method return and nested constraints; `Default` is not automatically added to custom groups.
12. Monitor return-contract failures as server-side bugs, with alerts and root-cause remediation workflows.

**Conclusion:** Validation does not only protect the server from bad input; it also helps the server self-verify its **output contract**. In Spring MVC 6.1+, constraints on method returns can produce `HandlerMethodValidationException` with **HTTP 500** (`isForReturnValue() = true`), distinct from incoming parameter errors that typically return **HTTP 400**. Combining `@NotNull`, `@Valid`, output DTOs, and `MockMvc` tests catches contract-violating return data before treating a request as successfully completed. Still, return validation remains a detection mechanism—it does not replace transaction control, business invariants, serialization, or safe error handling.

## References

- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): argument validation, method validation, return values, and controller-level `@Validated`.
- [Spring Framework 6.2 — HandlerMethodValidationException](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html): `getStatusCode()` 400/500 and `isForReturnValue()`.
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): service AOP, `MethodValidationPostProcessor`, exceptions.
- [Spring Framework — MVC Return Values](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/return-types.html): MVC return value types, wrappers, and async.
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): executable validation, return values, cascading, constraints, and groups.
