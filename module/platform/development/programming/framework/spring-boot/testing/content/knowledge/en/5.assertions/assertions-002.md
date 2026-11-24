# JUnit Assertions and Grouping Multiple Verification Conditions

A test does not become useful just because a method was called without throwing an error. An **assertion** is where a test states precisely what must be true: the result, error, data structure, or side effect that a caller is entitled to expect. In Spring Boot applications, knowing how to choose assertions and group related checks helps tests report discrepancies clearly, reduces root-cause investigation time, and avoids over-constraining implementation details.

JUnit Jupiter (JUnit 5) provides assertions in `org.junit.jupiter.api.Assertions` such as `assertEquals`, `assertTrue`, `assertThrows`, and especially `assertAll` to verify **multiple independent conditions in a single scenario**. This lesson explains how to choose assertions, failure behavior, how to group checks, exception handling, collection comparisons, and web test scenarios in Spring Boot.

**After this lesson, you will be able to:**

- Write Given–When–Then tests with purposeful assertions, distinguishing object value from object identity.
- Use appropriate assertions for numbers, strings, collections, arrays, exceptions, and non-throwing outcomes.
- Understand how `assertAll` runs `Executable` lambdas and aggregates multiple failures, in contrast to sequential `assertEquals` calls.
- Group related assertions by behavior without turning a test into a hard-to-diagnose script.
- Apply JUnit 5 and Spring MVC `MockMvc` to verify HTTP outcome properties.
- Recognize common mistakes: swapped expected/actual arguments, misleading `BigDecimal` comparisons, vague `assertTrue` checks, overly coupled details, time dependence, and mock-only assertions.

## 1. Where do assertions belong in a test?

A clear test usually follows three steps:

1. **Given (Arrange):** Set up initial data and state matching a specific requirement.
2. **When (Act):** Execute the action or public call under test.
3. **Then (Assert):** Check the output, exception, mutated state, or outbound port interaction if that is a promised outcome.

Example requirement: "When registering a name with leading/trailing whitespace, the system trims the whitespace, activates the profile, and assigns the USER role." A good test invokes the real registration behavior and then checks **the name, status, and roles**. Whether the controller calls a helper named `normalizeName` or the service uses `String.strip` is not a public contract, unless a specific requirement mandates that mechanism.

A **failing assertion** fails the test (typically with `AssertionFailedError` or a composite assertion failure). An **unexpected exception** during the action also fails the test, even if there are no assertions afterward. Therefore, verify meaningful behavior rather than writing redundant checks just to have many assertions.

Illustrative skeleton:

```java
// Illustrative skeleton: data/action are values prepared in a concrete test.
var result = service.perform(action);       // When
assertEquals(expected, result.value());      // Then
```

This is an illustrative snippet, not a standalone compilable program. Full examples later declare real classes and types.

## 2. Commonly used JUnit Jupiter assertions

Most tests statically import from `org.junit.jupiter.api.Assertions`:

```java
import static org.junit.jupiter.api.Assertions.*;
```

In production-grade test suites, explicit imports make dependencies clear to readers, though wildcard imports remain valid in learning examples.

| Assertion | Meaning | Notes |
|---|---|---|
| `assertEquals(expected, actual)` | Two values are equal per `equals`/corresponding overload | Arguments are **expected first, actual second**; watch `BigDecimal` and floats |
| `assertNotEquals(unexpected, actual)` | Two values differ | Being different does not guarantee the value is the right one |
| `assertTrue(condition)`, `assertFalse(condition)` | Boolean condition is true or false | Prefer a specialized assertion if it gives a clearer failure message |
| `assertNull(value)`, `assertNotNull(value)` | Null check | `not null` alone is rarely enough to protect a business outcome |
| `assertSame(expected, actual)` | Same object reference | Not equivalent to `equals`; use only when identity is part of the contract |
| `assertNotSame(unexpected, actual)` | Different object references | Two distinct instances can still be equal by value |
| `assertArrayEquals(expected, actual)` | Compares array contents, including primitive arrays | `assertEquals` on arrays usually checks reference identity |
| `assertIterableEquals(expected, actual)` | Compares Iterable elements in order | If order is not required, choose an order-independent check |
| `assertLinesMatch(expectedLines, actualLines)` | Line-by-line comparison with JUnit pattern support | Intended for structured multi-line output |
| `assertInstanceOf(Type.class, value)` | Checks runtime type and returns cast value | Only lock a concrete type when the type is part of the contract |
| `assertThrows(Type.class, executable)` | Action must throw the specified type or a subclass | Returns the caught exception for further checks if needed |
| `assertThrowsExactly(Type.class, executable)` | Must throw **that exact** exception class | Stricter; consider whether subclasses should be rejected |
| `assertDoesNotThrow(executable)` | Action must not throw | Usually pair with asserting the business result if any |
| `assertAll(heading, executable...)` | Evaluates conditions and aggregates multiple failures | Not for ignoring errors; groups checks for the same behavior |
| `assertTimeout(duration, executable)` | Completion time does not exceed the given duration | Does not abort the task on timeout; sensitive to CI speed |

Overloads also accept a failure **message** as a `String` or `Supplier<String>`. A supplier is only evaluated when the assertion fails, avoiding string-building overhead on passing paths.

Example with a scoped message:

```java
assertEquals("Linh", profile.displayName(),
        () -> "Normalized name must be Linh");
```

When a test fails, the report points straight to the mismatched field. Avoid generic messages like `"test failed"` that do not help find the cause.

## 3. Why sequential assertions can hide other failures

Consider a registered profile with three requirements: normalized name, enabled status, and USER role. Sequential assertions are valid:

```java
assertEquals("Linh", profile.displayName());
assertTrue(profile.enabled());
assertIterableEquals(List.of("USER"), profile.roles());
```

However, if the first check fails, JUnit stops the test method right there; the next two checks **never run**. After fixing the name bug, the next run may reveal a status or role bug. For a result object with multiple related attributes, this lengthens the fix-and-rerun loop.

`assertAll` solves that exact problem:

```java
assertAll("profile after registration",
        () -> assertEquals("Linh", profile.displayName()),
        () -> assertTrue(profile.enabled()),
        () -> assertIterableEquals(List.of("USER"), profile.roles()));
```

JUnit runs all provided `Executable` lambdas, **collects any failing assertions**, and reports them as a single composite failure when multiple errors occur. Remaining lambdas still get checked even if an earlier condition failed. The report typically includes the group heading and each individual failure; exact formatting depends on the JUnit/IDE version.

**Important points to understand accurately:**

- `assertAll` does not guess which fields to check; you still have to write meaningful assertions.
- It does not change business logic or turn a failing test into a passing one. If one or more checks fail, the entire test fails.
- Lambdas should be independent and **only read the produced result**. Do not let the first lambda mutate data needed by the second.
- If the main action `service.register(...)` throws an exception **before** `assertAll`, the grouped assertions do not run; the exception still fails the test. That is the right behavior when the success path is expected not to throw.
- On unrecoverable fatal errors (such as fatal JVM errors), do not assume every lambda will necessarily finish; `assertAll` is primarily meant for normal assertion failures.
- Do not bundle every test of a module into one giant `assertAll`. A test should express one behavior/scenario; group related properties of the **same outcome**.

## 4. Complete Java 17+ example: profile registration service

Suppose a Spring Boot 3.x module using Java 17+ has `spring-boot-starter-web` and `spring-boot-starter-test`. Requirements:

- Leading and trailing whitespace is stripped from the name.
- Successful registration creates a profile with `enabled=true`.
- Regular users receive role `USER`; administrators receive `USER` and `ADMIN` in that order.
- A `null`, empty, or whitespace-only name is rejected with `IllegalArgumentException`.

Create **`src/main/java/com/example/assertions/ProfileService.java`**:

```java
package com.example.assertions;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ProfileService {
    public Profile register(String name, boolean admin) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }

        String normalized = name.strip();
        List<String> roles = admin
                ? List.of("USER", "ADMIN")
                : List.of("USER");

        return new Profile(normalized, true, roles);
    }

    public record Profile(
            String displayName,
            boolean enabled,
            List<String> roles) {
    }
}
```

A `record` generates accessors `displayName()`, `enabled()`, and `roles()`; no JavaBean getters like `getDisplayName()` are needed. `String.strip` and `String.isBlank` exist since Java 11+, so Java 17 runs them cleanly. `List.of` returns an immutable list; that is a simple choice for the example, not a universal requirement for every application.

Create test file **`src/test/java/com/example/assertions/ProfileServiceTest.java`**:

```java
package com.example.assertions;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertIterableEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProfileServiceTest {
    private final ProfileService service = new ProfileService();

    @Test
    void registersNormalUserWithExpectedState() {
        ProfileService.Profile profile =
                service.register("  Linh  ", false);

        assertAll("normal user profile",
                () -> assertEquals("Linh", profile.displayName()),
                () -> assertTrue(profile.enabled()),
                () -> assertIterableEquals(
                        List.of("USER"), profile.roles()));
    }

    @Test
    void registersAdminWithBothRoles() {
        ProfileService.Profile profile =
                service.register("An", true);

        assertAll("admin profile",
                () -> assertEquals("An", profile.displayName()),
                () -> assertAll("roles and status",
                        () -> assertTrue(profile.enabled()),
                        () -> assertFalse(profile.roles().isEmpty())),
                () -> assertIterableEquals(
                        List.of("USER", "ADMIN"), profile.roles()));
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "  \t  "})
    void rejectsBlankNames(String invalidName) {
        assertThrows(IllegalArgumentException.class,
                () -> service.register(invalidName, false));
    }
}
```

**Reading each test:**

- `registersNormalUserWithExpectedState` checks three conditions of the same registration behavior; if both the name and roles are wrong, `assertAll` can surface both in one run.
- `registersAdminWithBothRoles` illustrates **nested `assertAll`**. The `roles and status` group contains two assertions; the outer group still covers all properties of the result.
- `rejectsBlankNames` uses `@ParameterizedTest` with `@NullAndEmptySource` and `@ValueSource` to test different invalid input forms. Each input produces a separate parameterized invocation. `assertThrows` proves the real service throws as promised.
- Because these only test pure logic, these unit tests **do not need `@SpringBootTest`**. The runtime `@Service` annotation does not prevent testing directly with `new`.

Note that `@NullAndEmptySource` supplies `null` and `""`; `@ValueSource` adds strings containing spaces/tabs. `String.isBlank` catches all of these. If the exception message is not part of the contract, **do not assert verbatim** `"name must not be blank"`, since rewording should not break tests. If an API exposes a public error code or fixed message, assert that code/message at the appropriate boundary.

## 5. Why `assertAll` is better than one `assertTrue` with combined expressions

A hard-to-diagnose test pattern:

```java
// Anti-pattern: if it fails, it is hard to tell which field is wrong.
assertTrue(profile.enabled()
        && profile.displayName().equals("Linh")
        && profile.roles().contains("USER"));
```

Because three conditions are collapsed into one boolean, the failure report only sees `false`. With `assertAll` and specialized assertions:

```java
assertAll("registered profile",
        () -> assertTrue(profile.enabled()),
        () -> assertEquals("Linh", profile.displayName()),
        () -> assertTrue(profile.roles().contains("USER"),
                "Profile must have USER role"));
```

Each discrepancy gets context. In particular, `assertEquals` displays **expected** and **actual** values; `assertTrue` only sees a boolean so it needs a message indicating what was expected. If the full role list and its order are part of the contract, `assertIterableEquals` expresses that more accurately than `contains`.

However, do not overuse `assertAll` just to always have many assertions: if a test only needs to verify that HTTP returns `403`, one status assertion is enough. **Multiple assertions are only meaningful when each assertion protects a property that actually needs verification.**

## 6. Reading composite failures and choosing groupings

Suppose, **purely to illustrate a failure**, the actual data has name "Linh" and `enabled=true`, while the test expects "An" and `enabled=false`:

```java
// Anti-pattern intentionally failing; DO NOT add to the passing suite in section 4.
assertAll("profile after registration",
        () -> assertEquals("An", profile.displayName()),
        () -> assertFalse(profile.enabled()),
        () -> assertIterableEquals(List.of("USER"), profile.roles()));
```

JUnit can report a `MultipleFailuresError` containing two mismatches: expected name "An" but got "Linh", and expected status false but got true. The role condition still executes; if it matches, no failure is reported for roles. The exact message formatting and stack trace depend on the JUnit and IDE version, so tests should not depend on the exact rendered string of `MultipleFailuresError`.

**Group by business meaning, not by line count.** For example, verifying order details:

```java
// Illustration: order and receipt are results already produced in the When step.
assertAll("confirmed order",
        () -> assertAll("order details",
                () -> assertEquals("CONFIRMED", order.status()),
                () -> assertEquals(2, order.lines().size())),
        () -> assertAll("receipt",
                () -> assertEquals("VND", receipt.currency()),
                () -> assertTrue(receipt.total().signum() >= 0)));
```

This is an **illustrative snippet**, not a standalone Java file: `order` and `receipt` types are not defined in this example. The benefit of nested groups is contextual failure reporting. If the checks cover two independent features (e.g., registration and account deletion), write **two separate tests** so each has its own cause and fixture.

When a test requires sequential state-changing steps, do not cram every step into one `assertAll`: verifying after each step may need to fail early so it does not corrupt inputs for the next step. `assertAll` works best for multiple **independent conditions on the same outcome**.

## 7. `assertThrows`, `assertThrowsExactly`, and `assertDoesNotThrow`

Testing error behavior is also contract testing. `assertThrows` accepts the expected exception type and a lambda containing the action that must throw:

```java
IllegalArgumentException error = assertThrows(
        IllegalArgumentException.class,
        () -> service.register("  ", false));
```

It returns **the caught exception instance**. Only assert its code/message/properties afterward if those details are actually specified.

Distinguish them:

- `assertThrows(RuntimeException.class, executable)` **accepts** `RuntimeException` and any matching subclass.
- `assertThrowsExactly(RuntimeException.class, executable)` accepts **only the exact class `RuntimeException`**; if the code throws `IllegalArgumentException`, the assertion fails.
- `assertDoesNotThrow(() -> operation())` confirms the action does not throw, and the value-returning overload returns the result.

Proper usage with the service:

```java
ProfileService.Profile result = assertDoesNotThrow(
        () -> service.register("Mai", false));
assertEquals("Mai", result.displayName());
```

However, a test that calls `register` and asserts its output will already fail if an unexpected exception occurs. `assertDoesNotThrow` is useful when "does not throw" is specifically what you want to emphasize, or when wrapping an execution block with a custom failure message. Do not use it as a replacement for output assertions.

**Common mistake:** placing `assertThrows` around a different method than the one under test, or invoking the method before entering the lambda. You must pass the lambda:

```java
assertThrows(IllegalArgumentException.class,
        () -> service.register("", false));
```

Do not call `service.register("", false)` beforehand and pass its result into the assertion; the exception will escape before JUnit can inspect its type.

## 8. Comparing collections, arrays, object identity, and currency

Assertions that look similar often carry different semantics:

### 8.1. Comparing arrays and lists

```java
int[] expected = {1, 2, 3};
int[] actual = {1, 2, 3};
assertArrayEquals(expected, actual);

List<String> roles = List.of("USER", "ADMIN");
assertIterableEquals(List.of("USER", "ADMIN"), roles);
```

`assertArrayEquals` checks array contents; `assertEquals` on two distinct arrays usually checks identity because Java arrays do not override `equals`. For `Iterable`, `assertIterableEquals` compares corresponding elements in iteration order.

If the business only requires two roles to exist **without specifying order**, asserting exact order can make tests brittle. In that case, you can use set-based comparison:

```java
assertEquals(Set.of("USER", "ADMIN"), Set.copyOf(profile.roles()));
```

The example above requires `import java.util.Set;` if placed in a separate Java file. Consider duplicates: converting to a `Set` removes duplicates, so this approach **cannot** detect duplicated roles. If duplicates are disallowed, assert the size as well or use an appropriate multiset comparison.

### 8.2. Comparing object value and identity

```java
String first = new String("hi");
String second = new String("hi");

assertEquals(first, second);   // Same string value
assertNotSame(first, second);  // Two distinct objects
```

`assertSame` is appropriate when returning the exact same object instance is part of the requirement, such as a cache contract; normally, testing content/value matters more. Avoid asserting singleton/identity when the product only promises value equality.

### 8.3. Comparing `BigDecimal` and floating-point numbers

`BigDecimal.equals` compares **scale** as well:

```java
BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");

assertNotEquals(a, b);         // equals differs because scales are 1 and 2
assertEquals(0, a.compareTo(b)); // Numeric values are equal
```

This example needs `import java.math.BigDecimal;`. If scale is not part of the contract, use `compareTo` or AssertJ's `isEqualByComparingTo`; if two decimal places must be preserved, assert the scale too.

For `double` floating-point calculations, do not assert exact equality when the algorithm has rounding error:

```java
assertEquals(0.3, 0.1 + 0.2, 0.0000001);
```

`delta` is a tolerance chosen per the requirements; do not arbitrarily choose a huge delta that lets meaningful discrepancies pass. For business monetary calculations, usually use `BigDecimal` with an explicit rounding rule rather than relying on `double`.

## 9. Grouping assertions in Spring Boot HTTP tests

An HTTP result has multiple meaningful conditions: status, content type, JSON fields, and error codes. In Spring MVC, `MockMvc` provides `andExpect` for individual `ResultMatcher`s and `andExpectAll` to aggregate checks. **MockMvc's `andExpectAll` is not `Assertions.assertAll`**, though both serve to report multiple discrepancies on a single result.

To test end-to-end at the MVC layer, create **`src/main/java/com/example/assertions/ProfileController.java`**:

```java
package com.example.assertions;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/profiles")
public class ProfileController {
    private final ProfileService service;

    public ProfileController(ProfileService service) {
        this.service = service;
    }

    @PostMapping
    public ProfileService.Profile register(
            @RequestParam String name,
            @RequestParam(defaultValue = "false") boolean admin) {
        return service.register(name, admin);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ErrorResponse invalidName(IllegalArgumentException ignored) {
        return new ErrorResponse("INVALID_NAME");
    }

    public record ErrorResponse(String code) {
    }
}
```

Create **`src/test/java/com/example/assertions/ProfileControllerWebTest.java`**:

```java
package com.example.assertions;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProfileController.class)
@Import(ProfileService.class)
class ProfileControllerWebTest {
    @Autowired
    MockMvc mvc;

    @Test
    void registrationReturnsExpectedHttpContract() throws Exception {
        mvc.perform(post("/api/profiles")
                .param("name", "  Linh  ")
                .param("admin", "true"))
            .andExpectAll(
                status().isOk(),
                content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON),
                jsonPath("$.displayName").value("Linh"),
                jsonPath("$.enabled").value(true),
                jsonPath("$.roles[0]").value("USER"),
                jsonPath("$.roles[1]").value("ADMIN"));
    }

    @Test
    void invalidNameReturnsPublicErrorCode() throws Exception {
        mvc.perform(post("/api/profiles")
                .param("name", "   "))
            .andExpectAll(
                status().isBadRequest(),
                jsonPath("$.code").value("INVALID_NAME"));
    }
}
```

Here:

- `@WebMvcTest(ProfileController.class)` builds a context containing the MVC infrastructure needed for the controller instead of starting all application components.
- `@Import(ProfileService.class)` brings the real, simple service into the slice; there is no need to mock the logic we want to protect.
- `andExpectAll` checks the published HTTP properties; if multiple matchers fail, the test result can display multiple failures.
- `@ExceptionHandler` in the example turns the business error into HTTP 400; Spring does not automatically convert **every** `IllegalArgumentException` from a service into a 400 response without a suitable mapping mechanism.
- The `@PostMapping` method defaults to HTTP 200 because the example does not configure `@ResponseStatus(CREATED)`. If the API design specifies 201, update the contract, controller, and test accordingly.

**Prerequisites to run:** the module must have a `@SpringBootApplication` class discoverable by Spring Boot tests under standard package layout and the declared dependencies; if Spring Security is enabled, configure mock principals/CSRF and permissions according to the real contract. Do not disable security just to make tests pass. In apps with Spring Security, POST requests can be rejected if a CSRF token is missing; that is a test security configuration issue, not an `assertAll` bug.

Also distinguish web slice tests from integration tests: `@WebMvcTest` can verify routing and JSON, but it does not prove persistence/transactions across the full application. When you need to verify real persisted data, choose the appropriate test level.

## 10. `assertAll` does not mean "the more checks, the better"

There are two sides to grouping assertions.

**Good:** Checking multiple properties of **the same result object** or one response: name, status, roles; status, content type, error code. Each assertion is relatively independent and failure messages are clear.

**Problematic:** Placing multiple state-changing actions inside lambdas—such as creating an order, charging payment, and canceling the order—then checking results. If charging fails, the cancel lambda still runs inside `assertAll` and can leave confusing state or cause unintended side effects. For multiple interdependent actions, split into separate tests or allow failing fast at critical preconditions.

Example **to avoid**:

```java
// Anti-pattern: multiple operations with side effects inside one assertion group.
assertAll("entire workflow",
        () -> assertTrue(paymentService.charge(order)),
        () -> assertTrue(shippingService.dispatch(order)),
        () -> assertTrue(refundService.refund(order)));
```

This is **non-standalone illustrative code**; variables `order`, `paymentService`, `shippingService`, and `refundService` are not declared. Moreover, "charge, ship, and refund" is not a sensible test scenario unless the business explicitly requires that flow.

**Better approach:** arrange and act once, capture the result, and group **read-only** checks; when sequential actions are required, split tests or verify preconditions first. A test's output must be easy to understand when it fails.

Some practical observations:

- A test with **one behavioral objective** may have multiple assertions.
- A test is not required to have literally one assertion.
- If an assertion group has 20–30 unrelated properties, the test may be covering too many contracts.
- If a group contains duplicate assertions checking the same meaning, remove the redundancy.
- If a test needs to access private fields or inspect internal helpers just to add more assertions, question whether those are real requirements.

## 11. Common mistakes when writing assertions

### 11.1. Swapping `expected` and `actual`

```java
assertEquals("Linh", profile.displayName()); // Correct: expected first
```

When swapped, the test can still catch errors, but IDE failure reports show expected and actual reversed, making diagnosis confusing.

### 11.2. Overly generic assertions

```java
assertNotNull(profile); // Does not prove name, status, or roles.
```

If the contract requires full properties, assert each meaningful part. With objects initialized with defaults, checking only non-null can miss major bugs.

### 11.3. Comparing data types with the wrong semantics

```java
assertEquals(new BigDecimal("10.00"), new BigDecimal("10.0"));
```

This snippet **intentionally fails** because `BigDecimal.equals` compares scale too. If you want numeric equality, use `compareTo`; if scale is a requirement, assert the exact scale.

### 11.4. Using `assertTrue` with complex boolean expressions

```java
assertTrue(a != null && a.isValid() && a.getCount() == 2);
```

This is an **illustrative snippet**; variable `a` is not declared. The test can fail without pinpointing which condition failed. Split into specialized assertions, add messages, or use `assertAll`.

### 11.5. Pinning details outside the contract

Avoid asserting full stack traces, debug logs, private method names, unguaranteed JSON field ordering, or entire response snapshots when the API only guarantees specific fields. Such tests often break on valid refactoring.

### 11.6. Asserting only what a mock was stubbed to return

```java
// Anti-pattern: serviceMock is a mock stubbed to return "ok".
assertEquals("ok", serviceMock.process(input));
```

If the subject under test is itself a mock, no real logic runs. Mocks/fakes belong on **external dependencies** outside the test scope; the business component being protected must be the real implementation.

### 11.7. Catching exceptions too broadly or without verifying meaning

`assertThrows(Exception.class, ...)` is too broad and often accepts unrelated infrastructure errors. Prefer the specific error type defined by the contract, such as `IllegalArgumentException` or a domain exception. Use `assertThrowsExactly` only when the exact exception class matters; using it too strictly breaks tests on valid subclasses.

### 11.8. Arbitrary timeout assertions

`assertTimeout(Duration.ofMillis(10), ...)` can fail on slow CI even when the algorithm is right. For functional tests, do not turn a random machine's runtime speed into a contract. If performance/SLA is a requirement, measure it in a suitable environment with sufficient samples and a clearly defined budget.

### 11.9. Mutually dependent conditions in `assertAll`

If the first lambda mutates `profile` and the second reads `profile` afterward, grouping them can yield surprising results. Only use `assertAll` for independent checks on already-produced data; do not treat lambda execution order as a business execution tool.

### 11.10. Skipping boundary and error cases

A test using only typical valid inputs can miss `null`, empty strings, duplicates, or out-of-range boundaries. Use `@ParameterizedTest` for variants of the same rule, and `assertThrows` for required errors.

## 12. Time assertions: using the right scope

JUnit Jupiter provides `assertTimeout` and `assertTimeoutPreemptively`. They behave differently:

- `assertTimeout(duration, executable)` runs the action and checks elapsed time after it completes; it **does not interrupt the task** when the deadline passes.
- `assertTimeoutPreemptively(duration, executable)` runs the task in a separate thread and can fail the test as soon as the limit is exceeded. Changing threads has consequences for `ThreadLocal`, transaction contexts, and thread-bound components.
- In Spring tests using `@Transactional`, the new thread may **not participate in the test-managed transaction**. Therefore, be very careful with `assertTimeoutPreemptively` if the action has database side effects: expected rollbacks may not occur.

Illustrative syntax example:

```java
import java.time.Duration;
import static org.junit.jupiter.api.Assertions.assertTimeout;

// Inside a @Test method, with a prepared service:
assertTimeout(Duration.ofSeconds(2),
        () -> service.register("Lan", false));
```

This is an illustrative snippet: do not copy the two-second limit as a default SLA; any limit must have a justification. In particular, pure business logic tests from section 4 do not need timeouts added just to "look thorough".

When testing business time rules (such as voucher expiration), **inject a `Clock`** to fix the point in time and test boundaries instead of waiting on a real clock. These are two distinct test types: one measures **execution duration**, while the other verifies **time-based business rules**.

## 13. Running the examples in a Spring Boot module

In a Gradle project with the Spring Boot plugin/BOM configured, the needed dependencies are:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-test` in Spring Boot 3.x provides JUnit Jupiter, AssertJ, Mockito, and common Spring Test utilities. If the module already declares these dependencies, do not duplicate them. The Java files in sections 4 and 9 must be placed in their matching paths/packages; the project needs proper Spring Boot test bootstrapping and security configuration for the web slice to run.

Run from a project with the Gradle wrapper:

```bash
./gradlew test --tests com.example.assertions.ProfileServiceTest --tests com.example.assertions.ProfileControllerWebTest
```

On Windows PowerShell, use `.\gradlew.bat`. If the project has multiple Gradle modules, replace the `test` task with the exact test task path of the module containing the examples, keeping the `--tests` filters. To run all tests in the module, invoke the corresponding `test` task without filters.

**Expected outcome:** The `ProfileServiceTest` unit tests verify the three profile conditions, invalid inputs throw `IllegalArgumentException`, and the web slice responds with HTTP 200/400 per the illustrative controller. If the tests pass in a properly configured project, Gradle reports `BUILD SUCCESSFUL`. This is the **expected outcome inferred from the code**, not a claim of execution on a specific repository; there is no fixed business stdout because the examples are JUnit tests.

Inspect the Gradle-generated report at `build/reports/tests/test/index.html` and machine-readable data at `build/test-results/test/` (paths relative to the module's build directory). When an assertion fails, read expected/actual and the group heading before diving deeper into the stack trace.

## 14. Practice exercises

### Exercise A — fixing a hard-to-diagnose test

Given a `Profile` object after registration. Test snippet:

```java
assertTrue(profile.enabled()
        && profile.roles().contains("USER")
        && profile.displayName().equals("Linh"));
```

Rewrite it using `assertAll("registered profile", ...)` with three independent assertions. Hint: `assertTrue` for status/role and `assertEquals` for name. When deliberately changing the name to "Minh" and removing the "USER" role, observe how many failures JUnit displays; do not rely on exact stack trace strings.

### Exercise B — distinguishing value vs. identity comparison

With `new String("hi")` creating two distinct objects with equal content, do `assertEquals` and `assertSame` produce the same or different results? Explain why. Then compare `BigDecimal("1.0")` against `BigDecimal("1.00")` using `equals` and `compareTo`.

### Exercise C — testing error paths

Write a parameterized test for names `null`, `""`, `" "`, and `"\t"`. Use `assertThrows(IllegalArgumentException.class, ...)`. If an additional requirement states the API must return error code `INVALID_NAME`, decide whether you need unit tests, web tests, or both to protect the right boundary.

### Exercise D — deciding whether to group or split tests

A scenario creates an account, sends an email, activates via callback, and checks an invoice. If each step depends on the previous one, should all actions go into a single `assertAll`? Why or why not? Hint: distinguish **multiple properties of one outcome** from **multiple actions with side effects**.

## 15. Checklist for writing and reviewing assertions

- [ ] The test describes a rule/behavior worth protecting, not just calling a method.
- [ ] With `assertEquals`, `expected` comes before `actual`, using appropriate comparison semantics (numeric value, scale, identity).
- [ ] Specialized assertions express expectations more clearly than a long `assertTrue` expression.
- [ ] Boundaries, invalid inputs, state, or side effects are checked when part of the contract.
- [ ] `assertAll` groups independent conditions of the **same outcome**; lambdas have no unintended side effects.
- [ ] Failing assertions include group headings and messages sufficient to locate what went wrong.
- [ ] `assertThrows` checks the right error type and the right action; messages are pinned only when part of the contract.
- [ ] Collection comparisons accurately account for ordering and duplicates.
- [ ] Private helpers, debug logs, and internal call counts are not asserted unless part of the contract.
- [ ] No arbitrary timeouts or preemptive timeouts causing transaction/thread issues.
- [ ] Unit tests do not boot Spring unnecessarily; web slice tests verify HTTP responses when needed.
- [ ] Test failures aid diagnosis, and valid refactoring does not break tests unnecessarily.

**Key takeaway:** `assertAll` lets you see **multiple discrepancies of the same outcome in a single run**, while test quality comes from choosing the right conditions to protect. Good assertions carry business meaning, report clear messages, match data semantics, and stay stable alongside the code across many changes.