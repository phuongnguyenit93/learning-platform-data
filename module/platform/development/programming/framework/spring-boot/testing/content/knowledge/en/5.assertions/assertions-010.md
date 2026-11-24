# Writing Valuable Assertions: Avoiding Tautologies, Weak Checks, and Implementation Coupling

> **Module:** Spring Boot – testing  
> **Parent topic:** Assertion  
> **Objective:** Write assertions that verify the true behavioral contract, are strong enough to catch regressions, report clearly on failure, and remain resilient to refactoring that preserves behavior. Examples use Java 17+, JUnit Jupiter, AssertJ, Mockito, and Spring Boot.

## 1. An assertion is a falsifiable promise

In automated testing, an **assertion** compares the observed behavior of the subject under test (*actual*) against an independent expectation (*expected*) derived from requirements or system contracts. If behavior is wrong, at least one meaningful assertion must fail.

A test can **run green while proving nothing**:

```java
@Test
void misleadingTest() {
    int result = 2 + 2;
    assertTrue(true);
    assertEquals(result, result);
}
```

Both assertions pass for any value of `result`. Even changing addition to subtraction would not be caught. This snippet illustrates a JUnit test method inside a test class with proper imports, **not a standalone Java program**.

For the contract "2 + 2 = 4", write:

```java
@Test
void addsTwoNumbers() {
    int actual = calculator.add(2, 2);
    assertEquals(4, actual);
}
```

Here `4` is the expectation from requirements and `actual` is the output of the **code under test**. This snippet is illustrative and assumes `calculator` exists; a runnable project appears in section 4.

To self-review an assertion, ask three questions:

1. **If the method returns the wrong result, will the assertion fail?** If replacing the output with `null`, `0`, empty, an off-by-one boundary, or a wrong status still passes, the assertion may be too weak.
2. **Is `expected` independent of `actual`?** If `expected` is derived from the same result or the same function under test, the test becomes circular verification.
3. **Does the assertion target the observable contract?** If changing internal ordering, class names, auto-generated IDs, or log wording leaves the feature correct, the test should not fail unless those details themselves belong to the contract.

**A good assertion is sensitive to real bugs without being oversensitive to irrelevant details.** Never measure test quality by counting lines of `assertEquals`.

## 2. Three kinds of assertions to avoid

### 2.1. Always-true assertions (tautologies)

Bad examples:

```java
assertTrue(true);
assertEquals(actual, actual);
assertNotNull(new Object());
assertTrue(result == null || result != null);
assertEquals(items.size(), items.size());
```

These expressions lack an independent *oracle*—a standard for telling right from wrong. Even after invoking production code, comparing a result against itself protects no logic.

A subtler case:

```java
int expected = service.calculateTotal(cart);
int actual = service.calculateTotal(cart);
assertEquals(expected, actual);
```

If the method is consistently buggy, calling it twice still returns the same wrong value and passes. **Never use the output of the method under test to construct `expected`**, except when deliberately testing determinism/idempotency alongside other assertions establishing the contract.

A very common mocking mistake:

```java
when(repository.findById(7L)).thenReturn(Optional.of(book));
assertEquals(Optional.of(book), repository.findById(7L));
```

This test only verifies that Mockito returns the value you just stubbed. If the subject under test is `service`, you must **call the service** and assert the service's output or effect. A mock is a substituted dependency, not proof that the service works.

### 2.2. Overly weak assertions

These assertions can fail in extreme cases yet still allow many wrong behaviors:

```java
assertNotNull(receipt);             // Receipt might have total = 0.
assertTrue(total.signum() >= 0);    // Any non-negative number passes.
assertFalse(responseBody.isEmpty()); // An error JSON is also non-empty.
assertTrue(statusCode < 500);       // 400/404 would also pass.
assertDoesNotThrow(() -> service.quote(lines)); // Total is never checked.
```

These assertions are **syntactically valid** and can make sense when "non-null", "non-throwing", or "no server error" is literally the whole requirement. However, if the contract says "an order of 100.00 receives a 10.00 discount and pays 90.00", they are insufficient.

Replace them with meaningful outcomes:

```java
Quote actual = service.quote(List.of(
        new CartLine("SKU-1", new BigDecimal("100.00"), 1)));

assertAll("quote at discount threshold",
        () -> assertEquals(new BigDecimal("100.00"), actual.subtotal()),
        () -> assertEquals(new BigDecimal("10.00"), actual.discount()),
        () -> assertEquals(new BigDecimal("90.00"), actual.total()));
```

This is an illustrative snippet inside a test class with required imports. Complete `Quote`, `CartLine`, and `QuoteService` classes are defined in section 4. Because both the discount rule and final total belong to the contract, checking all three fields catches different classes of mistakes.

### 2.3. Assertions coupled to irrelevant details

Examples:

- An interface only asks for an **unordered** product list, yet the test asserts an exact order; a valid query change breaks the test.
- An API returns any unique DB-generated ID, yet the test requires the ID to be `1`; running alongside other data breaks the test.
- The contract specifies amount 90.00, yet the test demands JSON whitespace and key order matching one hardcoded string; a valid serializer update breaks the test.
- The requirement only requires sending a confirmation email, yet the test asserts **three** internal helper methods were called in a fixed sequence even though external behavior is unchanged.
- The test asserts exact machine clock `Instant.now()` instead of injecting a fixed `Clock` or checking real timestamp properties.
- The test asserts full stack traces, log wording, or internal implementation class names that are not part of any public contract.

Rule: **assert observable outcomes at the exact boundary under test**. Only assert ordering, timestamps, formatting, call counts, or internal names when they are **genuinely part of the requirement**.

## 3. Turning requirements into fault-detecting assertions

Before writing code, translate each requirement into concrete input/output examples or observable state changes.

Suppose a cart quoting feature has these rules:

1. Each line item: `unitPrice × quantity`.
2. Subtotal is the sum of all lines, rounded to two decimal places using `HALF_UP`.
3. If subtotal is **100.00 or higher**, apply a **10%** discount; below the threshold, no discount.
4. Payable total is `subtotal - discount`.
5. Empty carts, non-positive quantities, and negative unit prices are invalid.

Design an example table **before writing assertions**:

| Scenario | Input | Subtotal | Discount | Total | What it catches |
| --- | --- | ---: | ---: | ---: | --- |
| Below threshold | 1 × 99.99 | 99.99 | 0.00 | 99.99 | Applying discount prematurely |
| At threshold | 1 × 100.00 | 100.00 | 10.00 | 90.00 | `>= 100` boundary check |
| Above threshold | 1 × 120.00 | 120.00 | 12.00 | 108.00 | Percentage calculation |
| Multiple quantity | 3 × 20.00 | 60.00 | 0.00 | 60.00 | Ignoring `quantity` |
| Multiple lines | 2 × 40.00 + 1 × 20.00 | 100.00 | 10.00 | 90.00 | Summing only the first line |
| Empty cart | `[]` | — | — | — | Must reject invalid input |
| Quantity `0` | 1 line with quantity 0 | — | — | — | Must reject non-positive quantity |

A test with only `assertNotNull(quote)` **cannot distinguish** 90.00, 100.00, and 0.00. A test verifying all three `Quote` fields and exercising both sides of the threshold catches far more regressions.

Do not copy the production pricing formula verbatim into tests to compute expected values blindly. For small tabular cases, calculate expected values **independently from the business rules** and keep them explicit in the test. For complex formulas, use reviewed golden examples, an independent reference model, property-based testing, or domain invariants as appropriate.

## 4. Runnable Java 17 / Spring Boot 3.5 / JUnit Jupiter project

You can use the project below for hands-on practice. It clarifies the quote contract while showing how **assertions in unit tests, MVC slice tests, and integration tests must inspect each layer's proper boundary**.

Maven project layout:

```text
assertion-quality/
├── pom.xml
└── src/
    ├── main/java/com/example/quality/
    │   ├── AssertionQualityApplication.java
    │   ├── CartLine.java
    │   ├── Quote.java
    │   ├── QuoteService.java
    │   └── QuoteController.java
    └── test/java/com/example/quality/
        ├── QuoteServiceTest.java
        ├── QuoteControllerSliceTest.java
        └── QuoteIntegrationTest.java
```

### 4.1. Maven

```xml
<!-- pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>assertion-quality</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

The test starter provides JUnit Jupiter, AssertJ, Mockito, Spring Test, and standard test helpers. This project omits databases and security; bugs in those components lie outside this demonstration's scope. Spring Boot 3.5 uses `jakarta.*` packages where Jakarta APIs apply, and Spring Framework 6.2 provides `@MockitoBean`.

### 4.2. Application code

```java
// AssertionQualityApplication.java
package com.example.quality;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AssertionQualityApplication {
    public static void main(String[] args) {
        SpringApplication.run(AssertionQualityApplication.class, args);
    }
}
```

```java
// CartLine.java
package com.example.quality;

import java.math.BigDecimal;

public record CartLine(String sku, BigDecimal unitPrice, int quantity) {}
```

```java
// Quote.java
package com.example.quality;

import java.math.BigDecimal;

public record Quote(BigDecimal subtotal, BigDecimal discount,
                    BigDecimal total) {}
```

```java
// QuoteService.java
package com.example.quality;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class QuoteService {
    private static final BigDecimal THRESHOLD = new BigDecimal("100.00");
    private static final BigDecimal RATE = new BigDecimal("0.10");

    public Quote quote(List<CartLine> lines) {
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("Cart must not be empty");
        }
        for (CartLine line : lines) {
            if (line == null || line.unitPrice() == null
                    || line.unitPrice().signum() < 0
                    || line.quantity() <= 0) {
                throw new IllegalArgumentException("Invalid cart line");
            }
        }

        BigDecimal subtotal = lines.stream()
                .map(line -> line.unitPrice()
                        .multiply(BigDecimal.valueOf(line.quantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add)
                .setScale(2, RoundingMode.HALF_UP);

        BigDecimal discount = subtotal.compareTo(THRESHOLD) >= 0
                ? subtotal.multiply(RATE).setScale(2, RoundingMode.HALF_UP)
                : new BigDecimal("0.00");

        return new Quote(subtotal, discount, subtotal.subtract(discount));
    }
}
```

```java
// QuoteController.java
package com.example.quality;

import java.util.List;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class QuoteController {
    private final QuoteService service;

    public QuoteController(QuoteService service) {
        this.service = service;
    }

    @PostMapping("/checkout/quote")
    public Quote quote(@RequestBody List<CartLine> lines) {
        return service.quote(lines);
    }
}
```

The service keeps two decimal places per this example's contract. The controller accepts a JSON array and returns a JSON object containing `subtotal`, `discount`, and `total`. On valid requests, default HTTP status is **200 OK**. In a real project, define proper validation and error mapping (such as HTTP 400 for invalid input); this example asserts input errors at **the service layer**, without claiming the controller already handles 400 responses.

### 4.3. Unit tests: assert business values, not just non-null

```java
// QuoteServiceTest.java
package com.example.quality;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.*;

class QuoteServiceTest {
    private final QuoteService service = new QuoteService();

    @ParameterizedTest
    @CsvSource({
        "99.99, 99.99, 0.00, 99.99",
        "100.00, 100.00, 10.00, 90.00",
        "120.00, 120.00, 12.00, 108.00"
    })
    void appliesDiscountAtTheCorrectBoundary(
            String price, String expectedSubtotal,
            String expectedDiscount, String expectedTotal) {

        Quote actual = service.quote(List.of(
                new CartLine("SKU-1", new BigDecimal(price), 1)));

        assertAll("quote must follow the business rules",
                () -> assertEquals(new BigDecimal(expectedSubtotal),
                        actual.subtotal(), "subtotal"),
                () -> assertEquals(new BigDecimal(expectedDiscount),
                        actual.discount(), "discount"),
                () -> assertEquals(new BigDecimal(expectedTotal),
                        actual.total(), "total"));
    }

    @Test
    void accountsForAllLinesAndQuantities() {
        Quote actual = service.quote(List.of(
                new CartLine("A", new BigDecimal("40.00"), 2),
                new CartLine("B", new BigDecimal("20.00"), 1)));

        assertEquals(new Quote(
                new BigDecimal("100.00"),
                new BigDecimal("10.00"),
                new BigDecimal("90.00")), actual);
    }

    @Test
    void rejectsEmptyCartWithRelevantException() {
        IllegalArgumentException error = assertThrowsExactly(
                IllegalArgumentException.class,
                () -> service.quote(List.of()));

        assertEquals("Cart must not be empty", error.getMessage());
    }

    @Test
    void rejectsNonPositiveQuantity() {
        assertThrowsExactly(IllegalArgumentException.class,
                () -> service.quote(List.of(
                        new CartLine("A", new BigDecimal("20.00"), 0))));
    }

    @Test
    void rejectsNegativePrice() {
        assertThrowsExactly(IllegalArgumentException.class,
                () -> service.quote(List.of(
                        new CartLine("A", new BigDecimal("-1.00"), 1))));
    }
}
```

**Why are these assertions valuable?**

- Three data rows test **below threshold, right at threshold, and above threshold**; if a developer accidentally changes `>=` to `>`, the 100.00 case fails.
- The multi-line test fails if the service reads only the first line, ignores `quantity`, or miscalculates the discount.
- `assertEquals(new Quote(...), actual)` relies on **component-based record equality**; it checks all three monetary fields without manual field-by-field repetition. If `Quote` were replaced with a regular class lacking value-based `equals`, assert each field or use AssertJ field extraction.
- `assertThrowsExactly` asserts **the exact exception class**; `assertThrows` allows subclasses and fits when the contract only requires an exception family.
- Exact message `"Cart must not be empty"` should only be asserted if treated as part of the contract or important diagnostic behavior. When wording may change for localization or editing, asserting the exception type and a stable error code is less brittle.
- It does not assert helper names or how many times stream `map` ran; those are internal implementation details.

In this example, the calculation for `100.00` returns `Quote(100.00, 10.00, 90.00)` per `BigDecimal` value representation. **These are fixed test contract values, not Maven stdout.**

### 4.4. MVC slice: assert status, JSON contract, and meaningful request binding

`@WebMvcTest` loads only the MVC layer and mocks the service. Because the service **does not run for real**, a slice test must assert that the controller binds requests properly and returns the right HTTP status and serialization—never claim a mocked return value proves the discount formula works.

```java
// QuoteControllerSliceTest.java
package com.example.quality;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(QuoteController.class)
class QuoteControllerSliceTest {
    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    QuoteService service;

    @Test
    void bindsRequestAndRendersQuoteContract() throws Exception {
        when(service.quote(anyList())).thenReturn(new Quote(
                new BigDecimal("100.00"),
                new BigDecimal("10.00"),
                new BigDecimal("90.00")));

        mockMvc.perform(post("/checkout/quote")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                [{"sku":"A","unitPrice":100.00,"quantity":1}]
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subtotal").value(100.0))
                .andExpect(jsonPath("$.discount").value(10.0))
                .andExpect(jsonPath("$.total").value(90.0));

        verify(service).quote(argThat(lines ->
                lines.size() == 1
                && "A".equals(lines.get(0).sku())
                && new BigDecimal("100.00")
                        .compareTo(lines.get(0).unitPrice()) == 0
                && lines.get(0).quantity() == 1));
    }
}
```

**Important step:** `verify` is meaningful here because it protects **the controller → service boundary** and parsed request fields. Writing only `verify(service).quote(anyList())` would let a controller passing a malformed list pass. Still, do not verify local variables, private helpers, or interactions outside the contract.

`jsonPath("$.total").value(90.0)` checks the **numeric JSON value** seen by clients without locking JSON key ordering or whitespace. It does not check every detail of serialization on its own; the other key fields are verified alongside it.

### 4.5. Integration: assert real values flowing across layers

```java
// QuoteIntegrationTest.java
package com.example.quality;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class QuoteIntegrationTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void apiReturnsPriceCalculatedByRealService() throws Exception {
        mockMvc.perform(post("/checkout/quote")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                [{"sku":"A","unitPrice":100.00,"quantity":1}]
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subtotal").value(100.0))
                .andExpect(jsonPath("$.discount").value(10.0))
                .andExpect(jsonPath("$.total").value(90.0));
    }
}
```

No `@MockitoBean` is used here: the real controller and real service are wired together by Spring. If the 10% calculation breaks, this test turns red. `MockMvc` executes requests through Spring MVC test infrastructure **without opening a real HTTP socket**. When you need to test real networking or the servlet container, choose `@SpringBootTest(webEnvironment = RANDOM_PORT)` and an HTTP client; that choice governs integration scope rather than whether assertions are strong or weak.

### 4.6. Running

Requires JDK 17+ and Maven available. From the directory containing `pom.xml`:

```bash
mvn test
mvn -Dtest=QuoteServiceTest test
mvn -Dtest=QuoteControllerSliceTest test
mvn -Dtest=QuoteIntegrationTest test
```

The three test classes comprise **9 test invocations**: the parameterized test executes 3 times, plus four other unit methods, one MVC slice method, and one integration method → **9 test invocations** in total (3 + 4 + 1 + 1 = 9). That count changes as tests are added or edited. Maven prints `BUILD SUCCESS` when passing; do not rely on exact log text because environments, paths, timings, and dependency versions vary. The fixed business numbers in assertions are the trustworthy oracle.

## 5. Effective assertions by value type

### 5.1. Integers, strings, and booleans

Choose exact equality when the contract demands exact values:

```java
assertEquals(3, actualCount);
assertEquals("PAID", actualStatus);
assertTrue(actualActive);
```

However, `assertTrue(actualActive)` is only meaningful if `active` is the behavior under test and the inputs make `true` the **expected** outcome. When unrelated to the code under test, boolean checks quickly degenerate into trivial checks.

For strings, match the contract: if an exact message is required, use `assertEquals("...", actual)`; if valid dynamic content exists, assert stable fields or properties. Do not use `contains("OK")` as a success criterion if an error payload can also contain `"OK"`.

### 5.2. `BigDecimal` and floating-point numbers

`BigDecimal.equals` distinguishes both **numeric value and scale**:

```java
assertFalse(new BigDecimal("90.0").equals(new BigDecimal("90.00")));
assertEquals(0,
        new BigDecimal("90.0").compareTo(new BigDecimal("90.00")));
```

If the contract requires storing/returning **2 decimal places**, `assertEquals(new BigDecimal("90.00"), actual)` fits when output has scale 2. If only numeric monetary value matters, use:

```java
assertEquals(0, actual.compareTo(new BigDecimal("90.00")));
```

These snippets require importing `BigDecimal` and JUnit assertions; `actual` is a variable from the active test, not standalone code. In AssertJ, `assertThat(actual).isEqualByComparingTo("90.00")` expresses numeric comparison fluently.

For `double`/`float`, binary arithmetic can introduce tiny discrepancies:

```java
assertEquals(0.3, calculator.calculateRate(), 1e-10);
```

This illustrates a contract allowing a `1e-10` tolerance—always establish tolerance from requirements first. **Never pick a huge delta** like `100.0` that turns every answer into "close enough", and never rely on tolerances where money requires deterministic rounding. For pricing and money, prefer `BigDecimal` with an explicit rounding policy.

### 5.3. Collections: order and duplicates

Suppose an API returns a set of SKUs whose ordering is not guaranteed:

```java
assertThat(actualSkus).containsExactlyInAnyOrder("A", "B", "C");
```

This uses AssertJ (`import static org.assertj.core.api.Assertions.assertThat;`). It checks every element, including duplicate counts, **without enforcing order**. If the contract genuinely requires sorting by price or name, use `containsExactly(...)` to protect order. Never use `contains("A")` when the requirement is "return exactly these three SKUs, no more and no less".

Be careful with `Set`: converting output into a `Set` removes duplicates before assertions can detect duplication bugs. If duplicates would be a bug, assert on the raw `List`/response or check element count explicitly.

### 5.4. Exceptions: right type, right condition

Weak assertion:

```java
assertThrows(Exception.class, () -> service.quote(List.of()));
```

This can pass due to an unrelated exception. In our example, the contract specifies `IllegalArgumentException`:

```java
IllegalArgumentException error = assertThrowsExactly(
        IllegalArgumentException.class,
        () -> service.quote(List.of()));
assertEquals("Cart must not be empty", error.getMessage());
```

`assertThrows(IllegalArgumentException.class, ...)` is also valid when subclasses are permitted. Pick `assertThrowsExactly` when **the exact class** is part of the contract. Avoid asserting stack traces or prose error messages that can legitimately change without altering error-handling behavior.

Specifically, put **only the operation under test** inside the lambda:

```java
// Wrong target: exception happens while building test data, before service runs.
assertThrows(IllegalArgumentException.class, () -> {
    var input = createInvalidDataThatThrows();
    service.quote(input);
});
```

This illustrative snippet uses a hypothetical helper. The test can pass without ever invoking `service.quote`. When the failure source matters, build fixtures beforehand and limit the lambda to the target invocation:

```java
List<CartLine> invalid = List.of(
        new CartLine("A", new BigDecimal("20.00"), 0));
assertThrowsExactly(IllegalArgumentException.class,
        () -> service.quote(invalid));
```

### 5.5. Time, UUIDs, and dynamic data

Common mistake:

```java
assertEquals(Instant.now(), actual.createdAt());
```

Two clock calls happen at different instants, making the test fail intermittently. When exact timestamps belong to the contract, **inject a `Clock`** and freeze it.

Complete two-file Java example that can be added to the same project:

```java
// src/main/java/com/example/quality/ExpiryPolicy.java
package com.example.quality;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public class ExpiryPolicy {
    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public Instant expiry() {
        return Instant.now(clock).plus(Duration.ofHours(24));
    }
}
```

```java
// src/test/java/com/example/quality/ExpiryPolicyTest.java
package com.example.quality;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ExpiryPolicyTest {
    @Test
    void expiresExactlyOneDayAfterCreation() {
        Clock fixed = Clock.fixed(
                Instant.parse("2030-01-01T00:00:00Z"), ZoneOffset.UTC);

        assertEquals(
                Instant.parse("2030-01-02T00:00:00Z"),
                new ExpiryPolicy(fixed).expiry());
    }
}
```

The result here is **exact and independent of the real system clock**. For UUIDs, never assert a fixed hardcoded UUID string when the contract only requires validity and uniqueness. Inject a deterministic generator via constructor when testing exact output, or check format and uniqueness as needed.

### 5.6. JSON/HTTP: assert the contract, avoid brittle snapshots

When checking endpoints, ask:

- Is the exact status `200`, `201`, `400`, or `404`?
- Is `Content-Type` right?
- Are all required business fields, values, and types correct?
- For errors, do clients get the stable error code/format specified by contract?
- Are headers like `Location`, `ETag`, or `Retry-After` asserted only when required?

You rarely need to assert **raw JSON strings with fixed key ordering, whitespace, and indentation**. Use JSONPath, structural JSON comparison, or typed DTO assertions. At the same time, avoid checking only a non-empty body or a 200–499 status range that misses contract violations.

For example, when resource creation specifies `201 Created`, asserting only `status().is2xxSuccessful()` is too weak: it would miss returning 200 by mistake. Conversely, if the contract allows 200 **or** 204, do not force 200 based on personal preference.

### 5.7. Side effects and mock interactions

A service's contract may be to **publish exactly one event** rather than returning a value. In that case, interaction assertions are valuable:

```java
verify(eventPublisher).publish(argThat(event ->
        "ORDER_PAID".equals(event.type())
        && orderId.equals(event.orderId())));
```

This is an illustrative snippet assuming `eventPublisher` and `orderId` exist in the test class and the event type exposes `type()` and `orderId()`. If publication count is required, add `verify(eventPublisher, times(1))...`; `verify` without `times` checks for one matching invocation by default. Never verify every internal method just to inflate assertion counts: valid refactoring will break such tests.

Also distinguish **mocked effects** from **real effects**. `verify(repository).save(...)` proves a call on a mock, **not that data committed to the database**. To prove real persistence, write an integration test, re-query the repository, or inspect DB state in a proper environment.

## 6. Ways a test can turn "false green" despite having assertions

### 6.1. Assertions checking the wrong subject

```java
Quote quote = service.quote(lines);
assertEquals(expectedTotal, expectedTotal);
```

The service was called, yet `quote` is never inspected. Assertions must observe the real return value, exception, state mutation, or boundary interaction of the call under test.

### 6.2. Assertions that never execute

```java
if (Boolean.getBoolean("run.extra.assertions")) {
    assertEquals(expected, actual);
}
```

If that property is unset, the assertion silently skips. When a condition is a valid prerequisite, use `Assumptions`/`@EnabledIf...` deliberately so runs are recorded as **skipped**, instead of silently bypassing assertions and reporting pass.

With asynchronous callbacks:

```java
CompletableFuture.runAsync(() -> assertEquals(expected, actual));
```

The test method can finish before the future completes; the assertion can fail on another thread without the test waiting or reporting the error. Standard pattern:

```java
CompletableFuture<Void> future =
        CompletableFuture.runAsync(
                () -> assertEquals(expected, actual));
future.join(); // Ensure we wait; failures inside the task are propagated.
```

Both snippets are illustrations inside a test class (requiring `java.util.concurrent.CompletableFuture` and `expected`/`actual`). With Reactor, Kafka, async HTTP, or listeners, use appropriate test utilities to **await the expected state/effect and assert it**; avoid fixed `Thread.sleep(...)` calls that cause flaky tests.

### 6.3. Assertions after an early return

```java
if (result == null) {
    return;
}
assertEquals(expected, result.value());
```

When `result == null`, the test returns cleanly and passes. If `null` is a failure, write:

```java
assertNotNull(result, "result must exist");
assertEquals(expected, result.value());
```

In AssertJ, calling `assertThat(result).isNotNull()` before field checks makes sense too; however, **`isNotNull()` alone is too weak** when `value` must also match. Never use an early `return` to dodge missing data.

### 6.4. Fixtures and expected values produced by the same buggy logic

If `expected` is computed using the same function, mapper, or utility under test, both `actual` and `expected` can share the exact same bug and pass. Supply **independent examples**, reviewed contract fixtures, or another oracle. Do not blindly ban all test helpers: helpers that build valid input fixtures are great, whereas **helpers computing expected outputs with the algorithm under test** are risky.

### 6.5. Failing assertions caught and swallowed

```java
try {
    assertEquals(expected, actual);
} catch (AssertionError ignored) {
    // Wrong: the test passes even though the assertion failed.
}
```

Never swallow `AssertionError`. If you genuinely need to test that a custom assertion helper fails as intended, assert its failure using an appropriate API and clearly mark that the test checks **the test helper**, not domain behavior.

## 7. Right level of detail: test against the contract

Consider a code change: a service switches from `Stream` to `List`, or replaces an internal cache while still returning the right total.

| Assertion | Should that change break it? | Assessment |
| --- | --- | --- |
| `assertEquals(90.00, quote.total())` using proper money type | No | Protects output without locking implementation |
| `verify(helper).sumUsingStream(...)` | No, if helper is internal/optional | Brittle; verifies the wrong boundary |
| Asserting index 1 of a list with no ordering contract | No | Easily breaks under valid reordering |
| Asserting public API error code `INVALID_CART` | Yes, if the code changes | Reasonable when error code is in contract |
| Asserting log text contains a private method name | Usually no | Logs do not represent user-facing behavior |
| Asserting emails sent = 1 | Yes, if 2 were sent | Reasonable when sending exactly one email is the contract |
| Asserting DB-generated order ID = 1 | Usually no | Shared data and sequences can differ |
| Asserting the returned ID can retrieve the right order | Yes | Verifies the real behavior of the ID |

Therefore there is no universal rule like "always use `assertEquals`", "never verify mocks", or "never assert messages". **The deciding question is which requirement would be violated if the assertion failed.**

### 7.1. Minimal yet sufficient

Not every test needs to assert every field. A test named `returns404WhenBookMissing` only needs to verify status 404 and the relevant error contract; it should not check internal logs, traces, or timing. Conversely, a test named `calculatesDiscountAtThreshold` that only asserts no exception was thrown is insufficient.

The sweet spot is: **each test describes one concrete behavior, its assertions prove that behavior, and related invariants are clearly covered**.

### 7.2. `assertAll` and failure messages

JUnit Jupiter lets you group assertions using `assertAll`:

```java
assertAll("quote fields",
        () -> assertEquals(new BigDecimal("100.00"), quote.subtotal()),
        () -> assertEquals(new BigDecimal("10.00"), quote.discount()),
        () -> assertEquals(new BigDecimal("90.00"), quote.total()));
```

Unlike three sequential assertions (which stop at the first failure), `assertAll` runs every executable and aggregates multiple mismatches for easier diagnosis. **It does not make assertions stronger by itself**: if all three compare `actual` to `actual`, they remain three tautologies. Use meaningful failure messages such as `"discount for exactly 100.00"` rather than `"test failed"`.

## 8. Verifying assertion strength with controlled fault injection

Pick a small change that breaks behavior without breaking compilation, and check whether your tests catch it.

For example, change a line in `QuoteService`:

```java
// Correct:
subtotal.compareTo(THRESHOLD) >= 0

// Deliberately wrong to test the assertion:
subtotal.compareTo(THRESHOLD) > 0
```

If the assertion at threshold `100.00` is strong enough, the test fails: expected discount `10.00` vs. actual `0.00`, expected total `90.00` vs. actual `100.00`.

Try other hypothetical "mutants" locally and then restore the right code:

| Hypothetical mutation | Test that should fail |
| --- | --- |
| Sum only the first line item | `accountsForAllLinesAndQuantities` |
| Ignore `quantity` | `accountsForAllLinesAndQuantities` |
| Change discount rate `0.10` to `0.05` | `100.00` and `120.00` cases |
| Always return discount `0.00` | Threshold-and-above cases |
| Remove empty-cart check | `rejectsEmptyCartWithRelevantException` |
| Controller drops `discount` from JSON | MVC slice / integration JSON contract |
| Controller passes altered data into service | MVC slice `argThat` binding assertion |

This is the mindset behind **mutation testing**: not merely asking "was this line executed?" but "would the test stop a wrong change?". Tools like PIT can generate mutants automatically for Java, though no tool guarantees every business rule is covered. When injecting mutants, **never commit broken code**; treat it strictly as a check on test suite quality.

### 8.1. Assessing tests that break under valid refactoring

If renaming a private helper, reordering JSON map fields, compile timings, or reordering an unordered collection breaks tests, review the assertions before forcing production code changes. Such failures often show tests pinned to implementation details.

Conversely, if changing a public output or business semantics leaves all tests green, the suite is missing boundary cases or an independent expected oracle.

## 9. Choosing assertions by Spring Boot test level

| Level | Preferred observations | Misplaced assertions |
| --- | --- | --- |
| **Unit** | Calculated values, state, exceptions, commands sent to collaborators | Asserting Spring context beans when no context runs; verifying private helpers |
| **MVC slice** | URL/status/headers, request binding, JSON/validation contract, collaborator calls at the boundary | Claiming real service logic works while the service is mocked |
| **Repository slice** | Entity mappings, query results, constraints/transactions on an appropriate test DB | Asserting `save` returns non-null without verifying re-queried data |
| **Integration** | End-to-end results across real beans, state changes, transactions, error handling | Asserting only Mockito stubs instead of real components |
| **E2E** | External client journeys and observable outcomes, config/deploy bugs | Asserting internal classes or brittle environment-specific constants |

Example for repositories: if the requirement is "save a book and load it back by ID", the meaningful assertion **re-queries and verifies matching title/owner**; `assertNotNull(repository.save(book))` alone can pass even when mappings or read queries are broken. For payment E2E: beyond success status, verify the order moved to the right status and no duplicate transaction occurred per contract.

**Do not use two test layers to prove the exact same thing with the exact same mock.** Different layers should catch different classes of bugs; while expected business values may appear in both unit and integration tests, the execution paths exercised are different.

## 10. Assertion review checklist before merging

For every important test, verify:

- [ ] Test name and requirement align: "what does this test protect?".
- [ ] The target method, endpoint, or flow is actually invoked.
- [ ] `expected` is established independently from rules, reviewed examples, or the contract.
- [ ] No `assertTrue(true)`, `assertEquals(x, x)`, comparing a mock with its own stub, or assertions gated behind unsafe early `return`s.
- [ ] Not stopping at `assertNotNull`/`is2xxSuccessful`/`doesNotThrow` when the contract requires specific contents/values.
- [ ] Covers normal cases, boundary cases, and key invalid-input cases.
- [ ] Exceptions are verified accurately per contract; lambdas wrap only the operation under test.
- [ ] For async/callback tests, outcomes are awaited and observed before asserting.
- [ ] Collections, JSON, time, and numbers match domain semantics: ordered when required, justified tolerances, fixed clocks, no hardcoded dynamic IDs.
- [ ] Mockito `verify` checks meaningful boundaries/side effects without coupling to private internals.
- [ ] If a behavior-preserving refactor breaks the test, check whether assertions are brittle.
- [ ] You can name at least one concrete bug that would force this test to fail.
- [ ] In Spring Boot tests, you know which components are real and which are mocked.

## 11. Self-assessment exercises

**Exercise 1.** What is wrong with the pricing test below?

```java
Quote quote = service.quote(lines);
assertNotNull(quote);
assertTrue(quote.total().signum() >= 0);
```

**Answer:** It checks neither discount nor total per contract; an implementation always returning `0.00` passes. Replace with explicit expected values for subtotal/discount/total and include threshold cases.

**Exercise 2.** You used `assertThrows(RuntimeException.class, ...)` to test an empty cart. What is the risk?

**Answer:** A `NullPointerException` or unrelated runtime error would also pass because it extends `RuntimeException`. If the contract specifies `IllegalArgumentException`, assert that type; use `assertThrowsExactly` when the exact class must be enforced.

**Exercise 3.** An API returns products A, B, C in arbitrary order. Is `containsExactly("A", "B", "C")` appropriate?

**Answer:** No, if order is not part of the contract. Use `containsExactlyInAnyOrder` to verify all elements without enforcing order.

**Exercise 4.** Why is `assertEquals(Instant.now(), saved.createdAt())` unstable?

**Answer:** The two clock reads happen at different moments. Inject `Clock.fixed`, or assert a bounded time window when a range is the actual contract.

**Exercise 5.** A `MockMvc` test stubs the service to return `90.00` and asserts JSON `total` is `90.00`. Does that prove the service calculated the discount correctly?

**Answer:** Not yet. It proves controller routing and serialization of the mocked response. You still need unit or integration tests exercising the real service logic.

**Exercise 6.** You replace `>=` with `>` in the discount rule. A test suite with `subtotal = 120.00` but no `100.00` case stays green. What is missing?

**Answer:** A boundary test **right at the `100.00` threshold**. Boundary values are critical for comparison conditions.

**Exercise 7.** If the public requirement is "each paid order emits exactly one event", is verifying the call to the event publisher an implementation detail?

**Answer:** No, when that emission is the observable outcome at the event boundary. Verify one call with the right event type and order ID; do not verify the sequence of private helpers outside the contract.

## 12. References

- [JUnit 5 User Guide – Assertions](https://docs.junit.org/5.13.1/user-guide/index.html): `assertEquals`, `assertAll`, `assertThrows`, `assertThrowsExactly`, `assertDoesNotThrow`, and core assertions.
- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): scope of `@WebMvcTest`, `@SpringBootTest`, `@AutoConfigureMockMvc`, and `@MockitoBean`.
- [Spring Framework – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): testing Spring MVC requests and responses without a real HTTP server.
- [AssertJ Core Documentation](https://assertj.github.io/doc/): fluent assertions, collections, and semantic comparisons.
- [PIT Mutation Testing](https://pitest.org/): controlled fault injection to evaluate test suite bug-catching strength.

**Learning takeaway:** A good assertion is a meaningful commitment: if the business contract is broken, it must fail; if only valid internal implementation details change, it should continue to pass. Always write **expected values independently, specifically, at the right boundaries, and aligned with the contract**.
