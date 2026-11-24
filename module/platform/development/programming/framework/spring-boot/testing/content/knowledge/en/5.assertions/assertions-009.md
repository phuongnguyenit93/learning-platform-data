# Soft Assertions and Controlled Scope of Use

When testing a returned object, an HTTP response, or a database record, we often need to verify **multiple properties at once**. With standard assertions, the first failing check throws an error and subsequent statements never run. If you simply want to see *every field of the same outcome that is wrong*, fixing one failure and rerunning just to uncover the next is inefficient.

**Soft assertions** collect multiple assertion failures and report them together at the end of a group. In Java/Spring Boot, the two common mechanisms are **JUnit Jupiter's `assertAll`** and **AssertJ's `SoftAssertions`/`assertSoftly`**. Use them in a controlled scope: only group checks that are **independent, safe, and still meaningful even if another check fails**. Foundational preconditions—such as a non-null response, expected HTTP status, valid JSON parsing, or record existence—should still be checked **fail-fast**.

This lesson explains the mechanics, differences, application in unit/web/integration tests, runnable Java 17+ examples, common mistakes, and how to decide grouping scope.

## 1. Fail-fast vs. soft assertions: control-flow differences

Suppose an order quote must have these values:

| Field | Expected value | Actual value in a buggy case |
|---|---:|---:|
| `subtotalVnd` | 600,000 | 600,000 |
| `shippingVnd` | 0 | 30,000 |
| `payableVnd` | 600,000 | 630,000 |
| `currency` | `VND` | `VND` |

With sequential **fail-fast** assertions:

```java
assertEquals(600_000L, quote.subtotalVnd());
assertEquals(0L, quote.shippingVnd());
assertEquals(600_000L, quote.payableVnd());
assertEquals("VND", quote.currency());
```

When `shippingVnd` is actually 30,000, the second line throws; the remaining two assertions never run. The report does not immediately show that `payableVnd` is also wrong, even though both may stem from the same fee-calculation bug.

With JUnit Jupiter **`assertAll`**:

```java
assertAll("Order quote",
        () -> assertEquals(600_000L, quote.subtotalVnd()),
        () -> assertEquals(0L, quote.shippingVnd()),
        () -> assertEquals(600_000L, quote.payableVnd()),
        () -> assertEquals("VND", quote.currency()));
```

JUnit executes each supplied `Executable`, collects failures, and reports them together; on the example data, you see both `shippingVnd` and `payableVnd` mismatches. **The test still FAILS** if even a single assertion fails. Soft assertions never turn a failure into a "partial pass" and never fix or ignore business bugs.

Both snippets above are **excerpts inside a test method where `quote` exists**. A complete example with imports, package, class, and data appears in the hands-on section.

### Differences in responsibility

- **Assertion:** states one condition that must hold, such as "payable equals 600,000".
- **Fail-fast:** stops where an assertion throws, useful when remaining checks become meaningless if the earlier condition failed.
- **Soft/grouped assertion:** evaluates independent checks and aggregates failures, useful for exposing multiple discrepancies in a single result snapshot.
- **Test case:** a scenario with setup, action, and expected behavior. Multiple independent scenarios should still be separate test cases even if each uses soft assertions internally.

Never equate "collecting failures" with "continuing no matter what happens": setup errors, exceptions when calling dependencies, a `NullPointerException` from reading a missing field, or operations with side effects are not made safe by soft assertions.

## 2. JUnit Jupiter: `Assertions.assertAll`

JUnit Jupiter provides `assertAll`, accepting a group of `Executable`s (usually lambdas). Each `Executable` runs so JUnit can collect errors and report them, typically as OpenTest4J's `MultipleFailuresError` when multiple failures occur. Exact rendering depends on the JUnit version, build plugin, and IDE.

Illustrative snippet:

```java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;

assertAll("Quote fields",
        () -> assertEquals(600_000L,
                quote.subtotalVnd(), "subtotalVnd"),
        () -> assertEquals(0L,
                quote.shippingVnd(), "shippingVnd"),
        () -> assertEquals(600_000L,
                quote.payableVnd(), "payableVnd"),
        () -> assertEquals("VND",
                quote.currency(), "currency"));
```

The two `import` lines show required file imports, while the `assertAll` block sits inside a test method.

### Why does each condition need its own lambda?

Common mistake:

```java
assertAll("Quote",
        () -> {
            assertEquals(0L, quote.shippingVnd());
            assertEquals(600_000L, quote.payableVnd());
        });
```

If the first assertion fails, **that lambda** terminates before running the second assertion. `assertAll` moves on to other lambdas, but cannot rescue statements after a failure inside the same lambda. Write instead:

```java
assertAll("Quote",
        () -> assertEquals(0L, quote.shippingVnd()),
        () -> assertEquals(600_000L, quote.payableVnd()));
```

Now both conditions are checked independently. JUnit also allows small nested groups like `assertAll("Amounts", ...)` and `assertAll("Metadata", ...)` when a test checks many fields and grouping aids readability. Avoid creating excessive nesting levels for a short test.

**Pros:** uses JUnit's built-in `Assertions` directly, ideal for small fixed groups. **Limits:** authors must wrap each check in its own lambda to aggregate properly; an error thrown while preparing inputs before `assertAll` still halts the test immediately.

## 3. AssertJ: `SoftAssertions` and `assertSoftly`

AssertJ offers a fluent API across many value types, collections, and objects. In standard Spring Boot projects, `spring-boot-starter-test` puts AssertJ on the test classpath. Two key usage patterns:

### Manual style: remember to call `assertAll()`

```java
SoftAssertions softly = new SoftAssertions();

softly.assertThat(quote.subtotalVnd())
        .as("subtotalVnd").isEqualTo(600_000L);
softly.assertThat(quote.shippingVnd())
        .as("shippingVnd").isZero();
softly.assertThat(quote.payableVnd())
        .as("payableVnd").isEqualTo(600_000L);
softly.assertThat(quote.currency())
        .as("currency").isEqualTo("VND");

softly.assertAll();
```

Requires `import org.assertj.core.api.SoftAssertions;`. Each call via `softly.assertThat` records failures on that `softly` instance. **`softly.assertAll()` at the end is mandatory** to throw the accumulated failures. Forgetting it can cause a test to pass even when assertions failed.

### Recommended style: `assertSoftly` auto-aggregates

```java
assertSoftly(softly -> {
    softly.assertThat(quote.subtotalVnd())
            .as("subtotalVnd").isEqualTo(600_000L);
    softly.assertThat(quote.shippingVnd())
            .as("shippingVnd").isZero();
    softly.assertThat(quote.payableVnd())
            .as("payableVnd").isEqualTo(600_000L);
    softly.assertThat(quote.currency())
            .as("currency").isEqualTo("VND");
});
```

Requires `import static org.assertj.core.api.SoftAssertions.assertSoftly;`. Upon normal completion of the callback, `assertSoftly` aggregates failures at the end of the block, reducing the risk of forgetting `assertAll`.

**Note:** only assertions invoked through **`softly.assertThat(...)`** are collected into this group. Calling standard AssertJ `assertThat(...)` or JUnit `assertEquals(...)` inside the callback still fails fast immediately. If any statement throws an unexpected exception due to missing data, soft assertions cannot guarantee all remaining fields are evaluated. Never store `SoftAssertions` in a static field shared across tests or threads.

## 4. Runnable example: order quote pricing in Java 17+

To distinguish the mechanisms, we use one production class for two valid-quote tests plus a separate test verifying invalid input.

**Business rules:** given a positive quantity and non-negative unit price, subtotal equals quantity times unit price; orders of 500,000 VND or more receive free shipping, while below that threshold shipping is 30,000 VND; payable equals subtotal plus shipping, and currency is always `VND`. Invalid quantities must be rejected.

### 4.1. Production file

Create **`src/main/java/com/example/shop/pricing/OrderPricing.java`**:

```java
package com.example.shop.pricing;

public final class OrderPricing {

    public record Quote(long subtotalVnd,
                        long shippingVnd,
                        long payableVnd,
                        String currency) {
    }

    public Quote quote(int quantity, long unitPriceVnd) {
        if (quantity <= 0 || unitPriceVnd < 0) {
            throw new IllegalArgumentException("Invalid quantity or price");
        }

        long subtotal = Math.multiplyExact((long) quantity, unitPriceVnd);
        long shipping = subtotal >= 500_000L ? 0L : 30_000L;
        long payable = Math.addExact(subtotal, shipping);

        return new Quote(subtotal, shipping, payable, "VND");
    }
}
```

`record` is a Java 17 feature. `Math.multiplyExact` and `Math.addExact` throw `ArithmeticException` on `long` overflow, avoiding silent negative monetary wraparound.

### 4.2. Complete test file

Create **`src/test/java/com/example/shop/pricing/OrderPricingTest.java`**:

```java
package com.example.shop.pricing;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.SoftAssertions.assertSoftly;
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderPricingTest {
    private final OrderPricing pricing = new OrderPricing();

    @Test
    void softAssertionsCheckAllFieldsOfFreeShippingQuote() {
        OrderPricing.Quote quote = pricing.quote(2, 300_000L);

        assertSoftly(softly -> {
            softly.assertThat(quote.subtotalVnd())
                    .as("subtotalVnd").isEqualTo(600_000L);
            softly.assertThat(quote.shippingVnd())
                    .as("shippingVnd").isZero();
            softly.assertThat(quote.payableVnd())
                    .as("payableVnd").isEqualTo(600_000L);
            softly.assertThat(quote.currency())
                    .as("currency").isEqualTo("VND");
        });
    }

    @Test
    void junitAssertAllChecksAllFieldsOfPaidShippingQuote() {
        OrderPricing.Quote quote = pricing.quote(2, 200_000L);

        assertAll("Quote below free-shipping threshold",
                () -> assertEquals(400_000L,
                        quote.subtotalVnd(), "subtotalVnd"),
                () -> assertEquals(30_000L,
                        quote.shippingVnd(), "shippingVnd"),
                () -> assertEquals(430_000L,
                        quote.payableVnd(), "payableVnd"),
                () -> assertEquals("VND",
                        quote.currency(), "currency"));
    }

    @Test
    void rejectsZeroQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> pricing.quote(0, 300_000L));
    }
}
```

These files include full `package`, `class`, and imports; they are compatible with Java 17+ when the project provides JUnit Jupiter and AssertJ, such as via `spring-boot-starter-test`. These are **plain Java unit tests** needing no `@SpringBootTest`, application context, or database.

Run with Maven Wrapper from the module directory:

```bash
./mvnw -Dtest=OrderPricingTest test
```

Or Gradle Wrapper when the `test` task uses JUnit Platform:

```bash
./gradlew test --tests "com.example.shop.pricing.OrderPricingTest"
```

On Windows, use `mvnw.cmd` or `gradlew.bat`. These two commands are alternatives depending on build tool; there is no need to run both. Expected outcome: **3 tests pass, 0 failures**; exact build tool output depends on configuration and plugin versions, with no fixed business stdout.

The two quote tests verify **four properties of a single result produced by one call**; the zero-quantity test is an independent scenario, so it lives in its own method. This isolates failures by behavior while still collecting multiple mismatches on the same quote.

## 5. Seeing the benefit through two deliberate mismatches

Suppose `quote = pricing.quote(2, 300_000L)` returns `shippingVnd = 0` and `payableVnd = 600_000`. If a temporary test specifies wrong expectations:

```java
assertSoftly(softly -> {
    softly.assertThat(quote.shippingVnd())
            .as("shippingVnd").isEqualTo(30_000L);
    softly.assertThat(quote.payableVnd())
            .as("payableVnd").isEqualTo(630_000L);
});
```

This snippet **deliberately makes the test FAIL**, using a `quote` created elsewhere; **do not keep it in the main suite**. The meaningful result is **one failing test reporting two mismatches**: actual shipping 0 vs. expected 30,000, and actual payable 600,000 vs. expected 630,000. Exact exception formatting and stack traces vary by AssertJ/IDE/runner.

Self-verification exercise: first observe both **two mismatches**; then fix expectations back to 0 and 600,000 so the test passes. If using manual `new SoftAssertions()`, try removing `softly.assertAll()` locally to see how missing it causes a **false positive**; then restore aggregation before committing.

## 6. Choosing the right scope in Spring Boot

### 6.1. Web/MVC: verifying a single HTTP response

In `@WebMvcTest` or `@SpringBootTest` with `MockMvc`, a safe strategy is:

1. Perform the request **once**.
2. Check **fail-fast** that the status matches (e.g., HTTP 200), body exists, JSON parses cleanly, and minimal schema holds.
3. Use **soft assertions** to compare business fields on the **validated response**.
4. When a test fails, distinguish foundational failures from field-value mismatches.

**Illustrative example inside a test that already declares and configures `MockMvc mockMvc`, `ObjectMapper objectMapper`, endpoint `GET /api/quotes`, and matching imports:**

```java
MvcResult result = mockMvc.perform(
        get("/api/quotes")
                .param("quantity", "2")
                .param("unitPriceVnd", "300000"))
        .andExpect(status().isOk())
        .andReturn();

JsonNode json = objectMapper.readTree(
        result.getResponse().getContentAsString());
assertTrue(json.isObject(), "Body must be a JSON object");

assertSoftly(softly -> {
    softly.assertThat(json.has("subtotalVnd"))
            .as("subtotalVnd exists").isTrue();
    softly.assertThat(json.path("subtotalVnd").asLong())
            .as("subtotalVnd").isEqualTo(600_000L);
    softly.assertThat(json.path("shippingVnd").asLong())
            .as("shippingVnd").isZero();
    softly.assertThat(json.path("payableVnd").asLong())
            .as("payableVnd").isEqualTo(600_000L);
    softly.assertThat(json.path("currency").asText())
            .as("currency").isEqualTo("VND");
});
```

This snippet is **not a standalone runnable file**: endpoint, JSON shape, injections, `MvcResult`, `JsonNode`, and imports depend on your application's version/framework. In practice, check both **presence and data type** of each field before converting; `asLong()`/`asText()` on a JSON tree can return defaults for missing or wrongly typed nodes, making errors harder to read. Gatekeeping schema or type checks should remain fail-fast before value comparisons.

If the HTTP status is 401/403/500, the test should fail immediately on status; continuing to compare `payableVnd` on an error response makes no sense. For authorization or data-leak checks, write dedicated tests focused on the security contract rather than burying them inside a huge soft-assertion block.

### 6.2. Repository/integration: checking one retrieved record

Suppose a repository saved an order and you reload it to verify `status`, `currency`, and `total`. Verify **the record exists** first:

```java
OrderEntity stored = repository.findById(orderId)
        .orElseThrow(() -> new AssertionError("Order was not persisted"));

assertSoftly(softly -> {
    softly.assertThat(stored.getStatus())
            .as("status").isEqualTo(OrderStatus.PENDING);
    softly.assertThat(stored.getCurrency())
            .as("currency").isEqualTo("VND");
    softly.assertThat(stored.getTotalVnd())
            .as("totalVnd").isEqualTo(600_000L);
});
```

This is an **implementation pattern for an application integration test declaring `OrderEntity`, `OrderStatus`, `repository`, and `orderId`**; it does not compile standalone. If the record is absent, `"Order was not persisted"` communicates the **root cause** far better than cascading `NullPointerException`s from getters. Soft assertions do not replace verifying transactions, migrations, locking, or constraints with an appropriate database.

### 6.3. Service/DTO: snapshot after one action

A service returning a DTO can have fields like `id`, `status`, `total`, and `currency` checked together if they all come from one service call with no further side effects. This is the sweet spot: **one action, one snapshot, multiple independent properties**.

Do not design a single test that creates an order, charges payment, cancels the order, and issues a refund while throwing every assertion into one soft block. Distinct stages with dependent preconditions and side effects need fail-fast checkpoints or separate risk-focused tests.

## 7. When to use soft assertions vs. fail-fast?

| Scenario | Choice | Why |
|---|---|---|
| Multiple fields of the same successfully parsed JSON/DTO | Soft/grouped | Collects all independent mismatches together |
| Subtotal, shipping, payable, currency in one quote result | Soft/grouped | Reveals multiple symptoms of a pricing bug |
| Wrong HTTP status, unreadable body | Fail-fast | Later checks lack a valid foundation |
| Null object, missing DB record | Fail-fast | Prevents null dereferences and cascading errors |
| Authorization, critical side effects, transactions | Separate tests and fail-fast at boundaries | High-risk bugs need crisp signals |
| Different scenarios: happy path, error, timeout, retry | Separate test methods | Each scenario has its own setup and expected behavior |
| Multiple inputs sharing one business rule | `@ParameterizedTest` | Per-invocation names and inputs are clearer than one giant test |
| Complex object needing full structural comparison | Consider object/recursive comparison | Clearer than dozens of repetitive assertions |
| Checking workflow step order | Fail-fast per step | Subsequent steps may be meaningless if an earlier step failed |

**Decision question:** "If assertion A fails, does assertion B still measure something meaningful and safe?" If **yes**, soft grouping adds value. If **no**, check A fail-fast before entering the group, or split tests.

### Example to avoid

```java
assertSoftly(softly -> {
    softly.assertThat(response).isNotNull();
    softly.assertThat(response.getCustomer().getName())
            .isEqualTo("Lan");
});
```

If `response` or `getCustomer()` is null, the second statement throws `NullPointerException`. The soft assertion on the line above **does not protect** later getters. Better approach:

```java
assertNotNull(response, "response must exist");
assertNotNull(response.getCustomer(), "customer must exist");

assertSoftly(softly -> {
    softly.assertThat(response.getCustomer().getName())
            .as("customer.name").isEqualTo("Lan");
    softly.assertThat(response.getCustomer().isActive())
            .as("customer.active").isTrue();
});
```

These two snippets illustrate the thinking in a hypothetical test where `response` exists; they need JUnit's `assertNotNull` and AssertJ's `assertSoftly` imported. Foundational preconditions are checked fail-fast, and only safely independent fields are grouped.

## 8. Technical limits and anti-patterns to avoid

1. **Forgetting `softly.assertAll()`** when using `new SoftAssertions()`. Accumulated failures will silently fail to fail the test. Prefer `assertSoftly` or guarantee the closing call runs.
2. **Mixing regular assertions into a soft block** while assuming all failures are collected. Standard JUnit `assertEquals` and AssertJ `assertThat` still fail fast immediately.
3. **Putting multiple assertions inside one `assertAll` `Executable`**. The first failing assertion aborts the rest of that lambda; split into separate lambdas.
4. **Grouping dependent checks without preconditions:** before asserting `customer.name`, verify `customer` exists. Avoid noisy secondary exceptions.
5. **Sharing a `SoftAssertions` instance across tests or threads.** Failures accumulate across contexts and produce nondeterministic results. Create a fresh instance per test/block.
6. **Grouping non-contract fields** such as random timestamps or unnecessary generated IDs. Those assertions add maintenance burden without protecting real requirements.
7. **Cramming too many behaviors into one test.** A report listing 30 mismatches does not replace focused tests with clear names, fixtures, and boundaries. Split scenarios before piling on assertions.
8. **Assuming soft assertions increase test coverage.** They improve *observing multiple mismatches in one run*, not data coverage, path coverage, or real dependency integration. Unit tests with mocked repositories still do not prove SQL or transactions.
9. **Using failure collection to gloss over dangerous side effects.** When payment or authorization goes wrong, tests should stop and assert at critical boundaries rather than executing further state mutations just to gather more failures.
10. **Omitting labels and messages.** Use `assertAll("Quote fields", ...)`, `"payableVnd"`, or `as("payableVnd")` so another reader scanning logs immediately sees which field failed.

## 9. Verifying soft assertions are used properly

Follow this short workflow:

1. Write one clearly named scenario with one action producing a concrete outcome.
2. Place fail-fast guards for HTTP status, parsing, object existence, and required preconditions.
3. List the **independent** properties to check on that snapshot.
4. Pick `assertAll` for a small JUnit group, or `assertSoftly` for AssertJ fluent checks and `as(...)` labels.
5. Confirm every condition is truly soft-grouped, with no unexpected fail-fast assertions inside.
6. Temporarily introduce two deliberate mismatches locally: verify two failures are reported and the test FAILS; restore expectations so it PASSES.
7. Run the test standalone and with the full suite to confirm no ordering or shared-state dependence.
8. Keep assertion counts purposeful; split overly broad tests by behavior or use parameterized tests.

## 10. Pre-commit checklist

- [ ] The test checks multiple properties of **one outcome**, rather than unrelated workflows.
- [ ] HTTP/parse/null/record-existence preconditions are checked fail-fast when required.
- [ ] Every soft check remains meaningful even when another soft check fails.
- [ ] With JUnit `assertAll`, independent checks live in separate lambdas.
- [ ] With AssertJ, all grouped checks use `softly.assertThat`.
- [ ] `SoftAssertions.assertAll()` is called if using manual style, or `assertSoftly` is used instead.
- [ ] No `SoftAssertions` instance is shared across tests or threads.
- [ ] Authorization, transaction, and critical side-effect checks have dedicated tests and clear boundaries.
- [ ] Assertion labels and messages pinpoint the failing field or scenario.
- [ ] The suite **fails when expectations are deliberately wrong** and **passes when code and expectations match**.

**Remember:** soft assertions fit **multiple independent observations on a validated snapshot**; fail-fast fits **foundational preconditions, high-risk checks, and dependent steps**. Both JUnit Jupiter's `assertAll` and AssertJ's `assertSoftly` are valuable when kept within clear test boundaries and never allowed to mask root failures.
