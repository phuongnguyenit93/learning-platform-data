# Asserting Exceptions, Causes, and Meaningful Messages with JUnit Jupiter and Spring Boot

A test that only verifies "an error occurred" is rarely enough. On failure paths, you need to know **whether the exception is the right type**, **whether the underlying cause was preserved**, **whether the message matches the contract**, and if the error crosses HTTP, **whether the client receives the right status and body**. This lesson shows how to write exception assertions in JUnit Jupiter and then verify how Spring Boot translates exceptions into API responses.

Core principle: **construct failing input deliberately → invoke the exact operation under test → catch the specific exception → verify message, cause, and important side effects**. Assertions must prove the specified behavior, rather than catching an overly broad exception type just to get a green test.

## 1. Four layers of information to distinguish

| Information | How to observe | What does it prove? | Limitations |
| --- | --- | --- | --- |
| **Exception type** | `assertThrows`, `assertThrowsExactly`, `getClass()` | Code throws the expected error category | Does not prove the reason or message is right |
| **Message** | `exception.getMessage()` | Error detail for readers/logs or a promised contract | Message wording may vary by data, library, or locale |
| **Cause** | `exception.getCause()`, `Caused by` chain | High-level error preserves the low-level source of failure | Valid exceptions may legitimately have no cause |
| **HTTP contract** | `MockMvc`/HTTP client: status, code, body | Client receives a standardized error from the web layer | Does not directly expose the Java exception object |

Example: the string `"abc"` cannot be parsed as an integer. `Integer.parseInt("abc")` throws `NumberFormatException`. A service can wrap that into `InvalidQuantityException` with message `"Quantity must be an integer"` and **cause** `NumberFormatException`. Meanwhile, the API returns `HTTP 400` with code `INVALID_QUANTITY`. These are distinct pieces of evidence, and each layer needs appropriate assertions.

Do not confuse **message** with **cause**: `getMessage()` returns the descriptive string; `getCause()` returns another `Throwable` (or `null`). Having the same message does not mean two exceptions share the same root cause. A business error detected directly during validation often needs no cause.

## 2. Choosing the right JUnit Jupiter assertion

JUnit Jupiter provides these APIs in `org.junit.jupiter.api.Assertions`. For expected errors thrown by code under test, the following three patterns form the foundation.

### 2.1. `assertThrows`: accepts the specified type or any subclass

```java
InvalidQuantityException error = assertThrows(
        InvalidQuantityException.class,
        () -> service.parse("abc")
);
assertEquals("Quantity must be an integer", error.getMessage());
```

The second parameter is an `Executable` (lambda or method reference). JUnit executes it; if no exception is thrown or an exception of an incompatible type is thrown, the assertion fails. If the exception matches the specified type or **a subclass** of it, the assertion succeeds and **returns the actual thrown exception** so you can inspect `getMessage()`, `getCause()`, and extra fields.

For instance, `assertThrows(RuntimeException.class, ...)` would accept both `NullPointerException` and a domain exception if both extend `RuntimeException`. That is usually too broad: a test could stay green due to an unrelated bug instead of the intended business validation error.

### 2.2. `assertThrowsExactly`: requires the exact exception class

```java
InvalidQuantityException error = assertThrowsExactly(
        InvalidQuantityException.class,
        () -> service.parse("0")
);
assertEquals("Quantity must be greater than 0", error.getMessage());
```

`assertThrowsExactly` succeeds only if the thrown exception has **the exact** specified class; subclasses are rejected. Use it when the concrete exception class is part of the contract or when you need to catch accidental substitution with another error type. Use `assertThrows` when the contract permits valid subclasses.

**Choose by contract, not by generic "strictness":** if a library intentionally defines an exception family extending `BusinessException`, forcing `assertThrowsExactly(BusinessException.class, ...)` is too rigid. Conversely, requiring only `Exception.class` is usually too loose.

### 2.3. `assertDoesNotThrow`: non-throwing happy path

```java
int quantity = assertDoesNotThrow(() -> service.parse("12"));
assertEquals(12, quantity);
```

Verifying no exception is thrown is helpful on valid paths, yet **not enough to prove the result is right**. Pair it with assertions on the returned value or effects. In the runnable examples below, those two lines verify both "no error thrown" and "exact quantity returned".

### 2.4. The *assertion* failure message parameter vs. the *exception* message

```java
assertThrows(
        InvalidQuantityException.class,
        () -> service.parse("0"),
        "Zero input must be rejected"
);
```

The third argument to `assertThrows` is the **diagnostic message displayed if the assertion itself fails**, not an instruction for JUnit to compare against `exception.getMessage()`. To verify the exception's message, capture the returned `error` variable and call `assertEquals`, `assertTrue`, or another assertion on it.

## 3. Checking messages: match the contract without creating brittle tests

Different comparison styles fit different contracts:

| Check style | When to use | Example |
| --- | --- | --- |
| **Exact match** | Message is a stable contract owned by your team | `assertEquals("Quantity must be greater than 0", error.getMessage())` |
| **Partial check** | Message embeds dynamic data and only a stable phrase matters | `assertTrue(error.getMessage().contains("Quantity"))` |
| **Structural/field check** | API exposes dedicated error codes, fields, or parameters | Assert `errorCode`, `field`, `status` instead of full prose wording |
| **Skip message text** | Message is produced by runtime/driver/library and not in contract | Assert only type, cause, or stable application-owned fields |

Messages from `NumberFormatException`, JDBC errors, Hibernate, drivers, or the JDK can change across versions and implementations. Avoid matching verbatim messages from those dependencies unless that exact text is a contract you need to protect. When changing languages or adding localization, unit tests should not break over unguaranteed wording; stable error codes are usually a better fit for APIs.

Example of a message containing a dynamic ID:

```java
assertNotNull(error.getMessage());
assertTrue(error.getMessage().contains("order-42"));
```

This is purely an **illustrative snippet** for an exception mentioning `order-42`, not an expectation from the quantity service below. When a message is fixed by contract, `assertEquals` catches accidental typos, wording regressions, or unintended sensitive details.

Proper error messages must also **not leak** passwords, tokens, SQL statements, internal details, or stack traces into HTTP responses. Web-layer tests should verify public codes/statuses/bodies rather than copying raw infrastructure exception messages.

## 4. Checking cause: did the high-level error preserve its root origin?

Java supports *exception chaining*: a new exception can retain the original exception via `super(message, cause)`. This preserves diagnostic detail for logging while presenting callers with a clear domain exception.

```java
try {
    return Integer.parseInt(raw);
} catch (NumberFormatException cause) {
    throw new InvalidQuantityException(
            "Quantity must be an integer", cause);
}
```

This is an **excerpt of exception-wrapping logic**; section 5 provides the full service. When `raw="abc"`, the outer class is `InvalidQuantityException`, and `getCause()` is `NumberFormatException`.

Appropriate assertions:

```java
InvalidQuantityException error = assertThrowsExactly(
        InvalidQuantityException.class,
        () -> service.parse("abc")
);
assertEquals("Quantity must be an integer", error.getMessage());
assertInstanceOf(NumberFormatException.class, error.getCause());
```

`assertInstanceOf` verifies the cause has the expected type, including subclasses if any. If the exact cause class is a strict contract, compare `error.getCause().getClass()` after checking non-null. Do not assert the verbatim message of `NumberFormatException`, as that is a Java runtime detail.

An exception can have multiple cause layers:

```text
OrderWorkflowException
    Caused by: QuantityMappingException
        Caused by: NumberFormatException
```

When higher layers wrap errors multiple times, check **the right level**. `getCause()` returns the direct cause, not automatically the root cause. Assert the cause chain only when wrapping is genuinely promised by the contract; avoid coupling tests deeply to internal framework exception names.

`getSuppressed()` is a different relationship from `getCause()`: in `try-with-resources` scenarios, resource-closing errors may be attached as *suppressed exceptions*. Do not call `getCause()` and assume every thrown error is reflected there.

## 5. Complete example: checking business errors and Spring Boot HTTP contracts

The sample project uses Java 17+, Spring Boot 3.3.5, JUnit Jupiter, and Gradle Groovy DSL. Scenario: an endpoint accepts a string `raw` representing an order quantity. Business rules are defined **before writing tests**:

1. `raw` is `null`, empty, or whitespace-only: reject with `InvalidQuantityException`, message `Quantity is required`. Detected directly, **no cause expected**.
2. `raw` cannot be parsed as a Java `int` (such as `abc`, `1.5`, or out-of-range numbers): reject with `InvalidQuantityException`, message `Quantity must be an integer`, **with `NumberFormatException` as cause**.
3. Parsed integer is `<= 0`: reject with `InvalidQuantityException`, message `Quantity must be greater than 0`, no cause expected.
4. Valid positive integer: return the parsed quantity without throwing.
5. For the HTTP endpoint, `InvalidQuantityException` translates into **HTTP 400** with JSON containing `code="INVALID_QUANTITY"` and the appropriate `message`. The response must not expose the cause or stack trace.

These are the contract rules for this lesson, not the default behavior of every Spring Boot API. Because the example calls `Integer.parseInt`, strings with extra spaces like `" 12 "` are treated as invalid format; if a system needs to accept them, add trimming rules and matching tests.

### 5.1. Project layout

```text
settings.gradle
build.gradle
src/main/java/com/example/exceptionassertion/ExceptionAssertionApplication.java
src/main/java/com/example/exceptionassertion/InvalidQuantityException.java
src/main/java/com/example/exceptionassertion/QuantityService.java
src/main/java/com/example/exceptionassertion/QuantityController.java
src/main/java/com/example/exceptionassertion/QuantityExceptionHandler.java
src/test/java/com/example/exceptionassertion/QuantityServiceTest.java
src/test/java/com/example/exceptionassertion/QuantityHttpTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'exception-assertion'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Requires JDK 17 and a compatible Gradle Wrapper in the project; `spring-boot-starter-test` supplies the core test dependencies including JUnit Jupiter, Spring Test, and common assertion libraries.

**`src/main/java/com/example/exceptionassertion/ExceptionAssertionApplication.java`**

```java
package com.example.exceptionassertion;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExceptionAssertionApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExceptionAssertionApplication.class, args);
    }
}
```

**`src/main/java/com/example/exceptionassertion/InvalidQuantityException.java`**

```java
package com.example.exceptionassertion;

public class InvalidQuantityException extends RuntimeException {
    public InvalidQuantityException(String message) {
        super(message);
    }

    public InvalidQuantityException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

The single-argument constructor is for directly detected validation errors. The two-argument constructor preserves the original exception: `super(message, cause)` makes `getCause()` assertions meaningful. Do not merely append `cause.getMessage()` to the message string and discard the cause.

**`src/main/java/com/example/exceptionassertion/QuantityService.java`**

```java
package com.example.exceptionassertion;

import org.springframework.stereotype.Service;

@Service
public class QuantityService {
    public int parse(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new InvalidQuantityException("Quantity is required");
        }

        final int quantity;
        try {
            quantity = Integer.parseInt(raw);
        } catch (NumberFormatException cause) {
            throw new InvalidQuantityException(
                    "Quantity must be an integer", cause);
        }

        if (quantity <= 0) {
            throw new InvalidQuantityException("Quantity must be greater than 0");
        }

        return quantity;
    }
}
```

`String.isBlank()` exists since Java 11+, so it works on Java 17. `null` is checked first thanks to the short-circuit `||` operator. `Integer.parseInt` throws `NumberFormatException` for non-numeric strings or values outside `int` range. Values like `0` or `-2` parse fine, so their exception is a **business rule violation** rather than a parsing error; hence `cause` is `null`.

**`src/main/java/com/example/exceptionassertion/QuantityController.java`**

```java
package com.example.exceptionassertion;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class QuantityController {
    private final QuantityService service;

    public QuantityController(QuantityService service) {
        this.service = service;
    }

    @GetMapping("/api/quantities/parse")
    public ParsedQuantity parse(@RequestParam("raw") String raw) {
        return new ParsedQuantity(service.parse(raw));
    }

    public record ParsedQuantity(int value) {
    }
}
```

The controller invokes the service and returns JSON `{"value":12}` for valid input. When the service throws `InvalidQuantityException`, Spring MVC routes it to the handler below.

**`src/main/java/com/example/exceptionassertion/QuantityExceptionHandler.java`**

```java
package com.example.exceptionassertion;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class QuantityExceptionHandler {
    @ExceptionHandler(InvalidQuantityException.class)
    public ResponseEntity<ApiError> handleInvalidQuantity(
            InvalidQuantityException exception) {
        return ResponseEntity.badRequest().body(
                new ApiError("INVALID_QUANTITY", exception.getMessage()));
    }

    public record ApiError(String code, String message) {
    }
}
```

`@RestControllerAdvice` **handles** the exception into an HTTP response. Thus `MockMvc.perform(...)` with `raw=abc` is expected to receive status `400` and matching JSON rather than letting `InvalidQuantityException` propagate directly out to the test. When the `raw` query parameter itself is omitted, Spring MVC handles binding via `MissingServletRequestParameterException`; this example **only** configures a handler for `InvalidQuantityException` and does not promise `INVALID_QUANTITY` JSON for every 400 error.

### 5.2. Unit test verifying exact type, message, and cause

**`src/test/java/com/example/exceptionassertion/QuantityServiceTest.java`**

```java
package com.example.exceptionassertion;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrowsExactly;

class QuantityServiceTest {
    private final QuantityService service = new QuantityService();

    @Test
    void acceptsPositiveInteger() {
        int actual = assertDoesNotThrow(() -> service.parse("12"));
        assertEquals(12, actual);
    }

    @ParameterizedTest
    @ValueSource(strings = {"abc", "1.5", "2147483648"})
    void wrapsInvalidNumberWithOriginalCause(String raw) {
        InvalidQuantityException exception = assertThrowsExactly(
                InvalidQuantityException.class,
                () -> service.parse(raw));

        assertAll(
                "invalid quantity parsing",
                () -> assertEquals(
                        "Quantity must be an integer", exception.getMessage()),
                () -> assertInstanceOf(
                        NumberFormatException.class, exception.getCause())
        );
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "   "})
    void rejectsAbsentQuantityWithoutTechnicalCause(String raw) {
        InvalidQuantityException exception = assertThrowsExactly(
                InvalidQuantityException.class,
                () -> service.parse(raw));

        assertEquals("Quantity is required", exception.getMessage());
        assertNull(exception.getCause());
    }

    @ParameterizedTest
    @ValueSource(strings = {"0", "-2"})
    void rejectsNonPositiveQuantityWithoutTechnicalCause(String raw) {
        InvalidQuantityException exception = assertThrowsExactly(
                InvalidQuantityException.class,
                () -> service.parse(raw));

        assertEquals("Quantity must be greater than 0", exception.getMessage());
        assertNull(exception.getCause());
    }
}
```

Key points in the tests:

- `assertThrowsExactly` locks the exact exception class per domain rules; the returned exception is captured to check message/cause.
- `assertAll` groups assertions on **the same exception**. If one check fails, JUnit still evaluates the remaining checks in the group and reports multiple failures together; it does not make an exception "valid" just because one check passes.
- `assertInstanceOf(NumberFormatException.class, exception.getCause())` proves error wrapping preserves the right cause type without coupling to changeable JDK wording.
- `assertNull(exception.getCause())` is a requirement **of this example** for directly detected validation errors; not every domain exception must forbid a cause.
- `@ParameterizedTest` exercises multiple representative inputs for the same rule; letters, decimals, and `int`-overflowing numbers must all satisfy the same contract.

Each test instantiates `QuantityService` directly, so these are **unit tests** for Java logic and do not prove Spring wiring, controller mapping, or HTTP exception handling. Having `@Service` on the class does not make a unit test boot a Spring context.

### 5.3. Spring Boot test with MockMvc: checking errors handled into HTTP

**`src/test/java/com/example/exceptionassertion/QuantityHttpTest.java`**

```java
package com.example.exceptionassertion;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class QuantityHttpTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void convertsDomainExceptionIntoClientError() throws Exception {
        mockMvc.perform(get("/api/quantities/parse")
                        .param("raw", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.code").value("INVALID_QUANTITY"))
                .andExpect(jsonPath("$.message")
                        .value("Quantity must be an integer"));
    }

    @Test
    void returnsParsedValueOnSuccess() throws Exception {
        mockMvc.perform(get("/api/quantities/parse")
                        .param("raw", "12"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.value").value(12));
    }

    @Test
    void rejectsMissingRequestParameter() throws Exception {
        mockMvc.perform(get("/api/quantities/parse"))
                .andExpect(status().isBadRequest());
    }
}
```

`@SpringBootTest` loads the example's application context; `@AutoConfigureMockMvc` provides `MockMvc` to execute the Spring MVC pipeline using simulated request/response objects **without opening a real network port**. The first two tests exercise the controller, handler, and response. The third test checks only status 400 from binding when `raw` is missing; it does not assume that response includes `INVALID_QUANTITY`.

In APIs with a custom error format (such as RFC 9457 `ProblemDetail` or a company schema), assertions must follow **the contract the API actually publishes**. Once a handler turns an exception into a `ResponseEntity`, writing `assertThrows(InvalidQuantityException.class, () -> mockMvc.perform(...))` misses the point: the exception has already been handled, so the observable outcome at this layer is the **HTTP response**. Check the raw Java exception in unit/service tests, or inspect the resolved exception only when appropriate.

### 5.4. Running and interpreting results

From the project directory with Gradle Wrapper, run:

```bash
./gradlew test
./gradlew test --tests com.example.exceptionassertion.QuantityServiceTest
./gradlew test --tests com.example.exceptionassertion.QuantityHttpTest
./gradlew bootRun
```

On Windows, use `gradlew.bat` instead of `./gradlew`. `test` runs JUnit tests; `bootRun` starts the application. If the Gradle Wrapper has not been generated yet, create it using a Gradle version compatible with Spring Boot 3.3.x before running wrapper commands.

With unmodified code and matching configuration, all tests are **expected** to PASS. This is an expectation inferred from the code, **not an observed execution log**. Gradle has no fixed stdout format because output depends on Gradle version, cache state, and environment.

When the app runs on the default port 8080, you can inspect HTTP responses with:

```bash
curl -i "http://localhost:8080/api/quantities/parse?raw=abc"
curl -i "http://localhost:8080/api/quantities/parse?raw=12"
```

For the error request, expect **status 400** and a JSON body equivalent to `{"code":"INVALID_QUANTITY","message":"Quantity must be an integer"}`; for the valid request, expect status 200 and JSON body `{"value":12}`. Headers and JSON key ordering can vary by runtime; do not assert raw full-response text just because serialization ordering differs.

### 5.5. Experiment to verify your assertions actually catch bugs

In a **temporary test copy**, omit the `cause` parameter when wrapping the exception:

```java
} catch (NumberFormatException cause) {
    throw new InvalidQuantityException("Quantity must be an integer");
}
```

Keep the message unchanged. Unit test `wrapsInvalidNumberWithOriginalCause` will FAIL on the `getCause()` assertion, even though the exception type and message still match. This demonstrates why stopping at `assertThrows` is insufficient.

Next, change the domain message from `"Quantity must be an integer"` to `"Invalid quantity"`. The message-checking tests will FAIL, and the HTTP test will FAIL on `jsonPath("$.message")`. If the message text is a promised contract, that is a bug worth catching. If only `code` is promised, consider dropping exact prose assertions at the HTTP layer so UI copy improvements do not break tests. After experimenting, revert the code.

## 6. Common scenarios where exception assertions go wrong

### 6.1. Wrapping multiple statements inside `assertThrows`

```java
assertThrows(RuntimeException.class, () -> {
    int value = Integer.parseInt("not-a-number");
    service.parse(Integer.toString(value));
});
```

This test **passes because of `NumberFormatException`** during input setup, before `service.parse` is ever called. Broad assertions and broad lambda bodies cause tests to validate the wrong thing. Instead, prepare inputs outside (when needed) and put only **the target operation** inside the lambda:

```java
String input = "0";
InvalidQuantityException error = assertThrowsExactly(
        InvalidQuantityException.class,
        () -> service.parse(input));
assertEquals("Quantity must be greater than 0", error.getMessage());
```

These two snippets are **excerpts meant for when `service` and JUnit imports are already in place**, not standalone Java programs.

### 6.2. Catching `Exception` or `RuntimeException` too broadly

```java
assertThrows(RuntimeException.class, () -> service.parse("abc"));
```

If the implementation changes to dereference a `null` object and throws `NullPointerException`, this test still passes. Choose the domain exception published by the contract. When frameworks or drivers may validly throw multiple subclasses, select the superclass **deliberately** and assert distinguishing details rather than locking an arbitrary exact class.

### 6.3. Calling a method without asserting the error

```java
@Test
void invalidInput() {
    service.parse("abc");
}
```

This does not test for an expected exception. Without `assertThrows`, the exception causes the test to **fail**. A test name does not turn an uncaught error into expected behavior. Conversely, using `try/catch` and ignoring the exception can pass without checking the right type; JUnit assertions are clearer.

### 6.4. Asserting internal-layer messages in too much detail

For `NumberFormatException`, the message may embed the raw input string or JDK-specific phrasing. Do not write tests relying on that wording when you only need to know parsing failed; check that `NumberFormatException` is the cause and verify the **application message** defined by your service.

When error responses standardize on `code` and `message`, clients should rely on the stable `code` for programmatic branching. Wording may vary by UI localization; exact message assertions only belong when the API genuinely guarantees that exact wording.

### 6.5. Confusing `getCause()` with the thrown exception type

For parsing `abc`:

```text
Thrown exception: InvalidQuantityException
exception.getCause(): NumberFormatException
exception.getMessage(): "Quantity must be an integer"
```

`assertThrows(NumberFormatException.class, () -> service.parse("abc"))` will **FAIL** because `NumberFormatException` was caught and wrapped. The right test asserts the outer exception is `InvalidQuantityException` and then asserts the cause is `NumberFormatException`.

If a system intentionally lets a low-level infrastructure exception propagate untouched, that is a different contract requiring a different test. Never guess that a low-level Java exception must be the final exception callers see.

## 7. Exceptions in asynchronous code and wrapper classes

With `CompletableFuture`, a task exception can surface through a wrapper when calling `join()`. **Illustrative snippet for a test with `service`**:

```java
CompletableFuture<Integer> future =
        CompletableFuture.supplyAsync(() -> service.parse("abc"));

CompletionException asyncFailure = assertThrows(
        CompletionException.class,
        future::join);

InvalidQuantityException domainFailure = assertInstanceOf(
        InvalidQuantityException.class,
        asyncFailure.getCause());
assertInstanceOf(
        NumberFormatException.class,
        domainFailure.getCause());
```

This snippet requires importing `java.util.concurrent.CompletableFuture`, `java.util.concurrent.CompletionException`, and JUnit assertions; it is a supplementary fragment, not a standalone file. `join()` must be called **inside** the asserted block: merely starting the future does not guarantee the task's exception is thrown on the test thread. `Future.get()` can throw `ExecutionException`; the exact wrapper depends on the synchronization API used.

For Spring async methods, event listeners, reactive streams, or message consumers, successfully scheduling a task does not prove the inner task succeeded. Tests must **observe the actual completion point or error signal** per that mechanism's contract, then check outer exceptions and causes at the proper layer. Never assume every framework wraps errors in the same exception class.

## 8. Checked exceptions, custom exceptions, and the HTTP layer

Java distinguishes checked exceptions (such as `IOException`) from unchecked exceptions (`RuntimeException` and subclasses). Both can be tested with `assertThrows`, because JUnit's `Executable` lambda is allowed to throw `Throwable`. What matters is the actual contract: a method might declare `throws IOException`, while an HTTP controller handles it and returns a status instead of letting it escape.

| Test location | Preferred assertions | Why |
| --- | --- | --- |
| Java parser/service validation | `assertThrowsExactly` / `assertThrows`, message, cause, state | Direct observation of Java exceptions |
| Repository/integration service | Standardized error type and transaction/data state | DB exception wrappers can vary; rollback needs observation |
| Spring MVC with `@RestControllerAdvice` | `MockMvc`: status, error code, JSON fields | Exception is translated into HTTP by the handler |
| HTTP via real web server | HTTP client: status, body, side effects | Checks the out-of-process client perspective |
| Async/future | `join()`/`get()` result, wrapper, and cause | Failure may occur after the initial call returns |

**Do not assume every HTTP error should return 400.** Input validation usually maps to 400; state conflicts may require 409; missing resources may require 404; genuine server errors typically require 5xx. Decide based on the API contract. For `InvalidQuantityException` in our example, the handler explicitly defines 400.

In real applications, logging should preserve stack traces and causes for internal diagnostics when appropriate, while client responses expose only necessary information. Good tests protect both: **causes are not lost in services** and **internal details do not leak into responses**.

## 9. What should and should not be asserted?

Use the following matrix when reviewing an error test:

| Case | Minimum meaningful assertions | Add if part of the contract |
| --- | --- | --- |
| Missing data | Exact domain exception, message or error code | No data mutation; `null` cause if required |
| Unparseable input | Domain exception and cause of type `NumberFormatException` | User-facing guidance message; safe handling of raw input |
| Business rule violation | Domain exception or allowed subclass | Error code, failing field, threshold value, unchanged state |
| Wrapped infrastructure failure | Application exception and root cause | Retryability, transaction rollback, logging context |
| Exception handled by Spring MVC | HTTP status and JSON error code | Content-Type, public message, no stack trace leak |
| Valid happy path | `assertDoesNotThrow` and right return value | Side effects and system state |

When **one rule has multiple failure branches**, test each branch. `raw=null` differs from `raw="abc"`: the first throws with no cause, while the second catches a parsing error with a cause. If you only write one test for "invalid input", you might miss a branch throwing `NullPointerException` or forgetting to wrap `NumberFormatException`.

### Should you assert stack traces?

Usually **do not compare full stack traces**: line numbers, proxies, JIT frames, frameworks, and configurations can change. When origin matters, preserve `cause`, error class/error code, and durable data. Database-originated errors can vary by database/driver; test business contracts through business error codes rather than vendor-specific exception details.

### Should you assert exact messages everywhere?

No. Exact messages make sense when your team owns both the code and the contract, such as `"Quantity is required"`. For external libraries or localized messages, rely on type, error code, or stable structured fields. If a spec requires exact user-facing wording, assert that wording at the right UI/API layer while accounting for the active locale.

## 10. Process for writing valuable exception tests

1. **State the error contract clearly.** Which inputs must be rejected? Which exception type? Which message or error code? Should a cause be preserved? Should data remain unmodified on failure?
2. **Prepare inputs outside the lambda.** Put only the target call inside `assertThrows`/`assertThrowsExactly` so setup mistakes are not miscounted as successes.
3. **Pick exception type strictness.** Exact class when critical; subclass when allowed by contract. Do not use overly broad types just to pass.
4. **Inspect the caught exception.** Verify `getMessage()` when stable, `getCause()` when preservation is required, and post-failure invariants/state as appropriate.
5. **Test the externally exposed layer.** When Spring handles exceptions, use `MockMvc` or an HTTP client to assert status/code/body rather than assuming the exception still propagates directly.
6. **Test with deliberate faults.** Temporarily drop `cause`, alter the message, or swap the exception class in the failure branch; a well-designed test should turn red on the matching assertion.
7. **Run the test alone and with the full suite.** Distinguish setup errors, dependency issues, state leaks, transactions, and assertions. One passing test does not cover untested cases.

## 11. Self-check exercises

**Exercise A:** For `service.parse("abc")`, is `assertThrows(NumberFormatException.class, ...)` correct? **No**: the service wraps `NumberFormatException` inside `InvalidQuantityException`. Assert the outer exception and then verify the cause.

**Exercise B:** For `service.parse("0")`, why does asserting `getCause() == null` make sense in the example? Because the failure is a **positive-quantity rule violation** detected directly, not a caught infrastructure exception. That belongs to the example's contract, not a universal rule for every domain exception.

**Exercise C:** Does a test writing only `assertThrows(RuntimeException.class, () -> service.parse("abc"))` catch a regression where the code starts throwing `NullPointerException`? **Not reliably**: `NullPointerException` is also a `RuntimeException`, so it would be accepted. Require the specific exception and assert key cause/message details.

**Exercise D:** `MockMvc` receives status 400 and JSON `INVALID_QUANTITY`; should you also add `assertThrows(InvalidQuantityException.class, () -> mockMvc.perform(...))`? **No, not for a scenario handled by advice.** Here the contract is expressed through the HTTP response. Test the Java exception directly in service tests.

**Exercise E:** A future runs `service.parse("abc")` asynchronously; does creating the future and letting the test finish prove the failure was observed? **No.** You must wait and observe the outcome via `join()`, `get()`, or an equivalent mechanism, then inspect the wrapper/cause.

### Checklist before signing off on an exception test

- Did you check the right **exception type**, accounting for exact type vs. subclass?
- Does the lambda inside `assertThrows` contain only **the operation expected to fail**, avoiding setup failures?
- Are message checks limited to parts that are actually a **stable contract**?
- When wrapping occurs, does `getCause()` have the right type and cause chain?
- For direct business errors, does the test avoid assuming a cause must always exist?
- Are there test inputs for **each failure branch** (missing, malformed, rule violation, out-of-bounds)?
- Are there assertions that data/state remained unchanged on failure when required?
- For REST APIs, were status, error code, JSON body, and absence of leaked details verified at the HTTP layer?
- Does the test fail if you deliberately change the **error type, cause, or message** protected by the contract?

**Key takeaway:** a good exception assertion verifies **the right error, the right cause, and the right public information**. JUnit Jupiter helps check `Throwable` at the Java layer; Spring Boot tests must also verify how errors are translated into the HTTP contract. Combining checks at the right scopes lets tests catch both business bugs and exception-handling/presentation bugs.
