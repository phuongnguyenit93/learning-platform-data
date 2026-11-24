# Comparing Objects by Property and Recursive Comparison in Spring Boot Testing

## 1. Learning objectives

A test often needs to verify that the output of a service, controller, or repository **matches on its important properties**, rather than being the exact same memory reference as an expected object. When data structures include nested objects, lists, timestamps, auto-generated IDs, or types with special equality rules such as `BigDecimal`, choosing the right assertion determines how reliable the test is.

After this lesson, you will be able to:
- Distinguish `isSameAs`, `isEqualTo`, property-by-property checks, `extracting`, and `usingRecursiveComparison`.
- Use AssertJ to check fields/properties of a single object; project fields from a list using `extracting`, `tuple`, and `flatExtracting`.
- Compare entire object graphs, including collection elements, with mismatch reports pointing to nested field paths.
- Explicitly configure ignored fields (IDs, timestamps), collection ordering, `null` handling, comparators, and strict type checking.
- Avoid "false green" assertions caused by ignoring too many fields, asserting wrong ordering, relying on misleading `equals`, or comparing database values with `BigDecimal.equals`.
- Apply these comparisons cleanly in Spring Boot unit, slice, and integration tests.

Context: Java 17+, JUnit Jupiter 5, AssertJ Core 3.27.x (for example, Maven using Spring Boot 3.5.7 manages `assertj-core` 3.27.6). All runnable code in the hands-on section consists of **JUnit tests without booting a Spring context**, because assertions fundamentally check Java values. In Spring Boot tests, the same assertion patterns apply after obtaining results from `@SpringBootTest`, `@WebMvcTest`, or `@DataJpaTest`.

## 2. Five ways to interpret "equal"

Suppose a service returns two `OrderView` objects with identical content created independently:

| Assertion | Meaning | When to use |
| --- | --- | --- |
| `assertThat(actual).isSameAs(expected)` | Both variables point to **the exact same instance** (`==`) | Identity contracts, caches, singletons, reference preservation |
| `assertThat(actual).isEqualTo(expected)` | Uses the type's `equals` semantics | Value objects/records whose `equals` matches the contract |
| `assertThat(actual.getStatus()).isEqualTo("PAID")` | Directly checks a single value | Only one property is the behavior under verification |
| `assertThat(actual).extracting(...).isEqualTo(...)` | Projects properties from one object or multiple elements | Only one or a small group of key fields matter; clear projection |
| `assertThat(actual).usingRecursiveComparison().isEqualTo(expected)` | Traverses field structure and compares nested contents | DTOs, response snapshots, or graphs needing **many fields** checked |

### 2.1. Identity differs from equality

```java
record Money(String currency, long minorUnits) {}

Money a = new Money("VND", 50_000);
Money b = new Money("VND", 50_000);

// a == b is false: two independently created objects.
// a.equals(b) is true because record generates equals from components.
// AssertJ:
assertThat(a).isEqualTo(b);
assertThat(a).isNotSameAs(b);
```

This is an **illustrative snippet** meant to live inside a Java method with `org.assertj.core.api.Assertions.assertThat` imported. A `record` generates `equals`/`hashCode` from its components; a regular Java class that does not override `equals` inherits `Object.equals`, so two instances with identical fields can still fail `isEqualTo`.

### 2.2. Do not force every model to override `equals` just for tests

JPA entities often use ID/identity or custom `equals` rules; DTOs might use Java records, while objects from a REST client might not override `equals`. When a test only needs to check response fields, projection or recursive comparison is appropriate; do not alter domain `equals` semantics solely to make `assertEquals(expected, actual)` turn green.

Key distinction:
- **`equals` is part of the type's semantics** (which may only care about ID).
- **Recursive comparison is a policy of a specific assertion** (which may compare all fields except ID/timestamp).
- **Property extraction explicitly selects a projection** (such as comparing only name and status).

No single comparison style is "best" for every goal. Choose according to the contract being verified.

## 3. Property-based comparison: direct accessors, `extracting`, and `satisfies`

### 3.1. Direct access via getters/accessors

With response records:

```java
record Address(String city, String street) {}
record Buyer(String name, Address address) {}
record OrderView(long id, String status, Buyer buyer) {}

// Illustrative code inside a test method:
var order = new OrderView(101L, "PAID",
        new Buyer("An", new Address("Hanoi", "Trang Tien")));

assertThat(order.status()).isEqualTo("PAID");
assertThat(order.buyer().address().city()).isEqualTo("Hanoi");
```

Pros: easy to read, type-checked at compile time, and IDE rename refactoring updates accessors safely. Cons: verbose when checking dozens of fields.

### 3.2. Using `extracting(Function)`

```java
assertThat(order)
        .extracting(OrderView::status)
        .isEqualTo("PAID");

assertThat(order)
        .extracting(o -> o.buyer().address().city())
        .isEqualTo("Hanoi");
```

`extracting` does not convert the object to a string. It **extracts the selected value** so an appropriate assertion can be applied. Lambdas and method references are compile-time type-checked; this is a good default when models expose public accessors.

### 3.3. Using string field/property paths

```java
assertThat(order)
        .extracting("buyer.address.city")
        .isEqualTo("Hanoi");

assertThat(order)
        .hasFieldOrPropertyWithValue("status", "PAID");
```

String paths allow concise nested path expressions. AssertJ resolves properties/fields and can access non-public fields under default settings; it is not JSONPath. For a `record`, component names are also JVM field names even though accessors like `city()` are not JavaBean `getCity()` getters. Resolution can also be affected by reflection/JPMS policies; lambdas are usually clearer.

Risk: a typo like `"buyer.adress.city"` is only caught at runtime. After refactoring, the compiler cannot rename string paths. Avoid long string paths when accessors express the contract concisely.

### 3.4. Multiple assertions on a single object

```java
assertThat(order).satisfies(o -> {
    assertThat(o.id()).isPositive();
    assertThat(o.status()).isEqualTo("PAID");
    assertThat(o.buyer().name()).isEqualTo("An");
});
```

`satisfies` works well for 2–4 heterogeneous conditions, such as ensuring a newly generated ID is positive, status matches, and buyer name is normalized. When you want to see **all failures** in a single run instead of stopping at the first failure, consider `SoftAssertions` and remember to call `assertAll()`.

### 3.5. Using `as(...)` to describe failure meaning

```java
assertThat(order.status())
        .as("status of order %s", order.id())
        .isEqualTo("PAID");
```

This description accompanies the failure message, which is useful when multiple objects share similar structures. Avoid putting access tokens, passwords, or sensitive data into labels or logs.

## 4. Collection projections: `extracting`, tuples, and ordering

A list response often needs comparison of **specific properties of each element**. Constructing full expected objects can be verbose and inadvertently turn the test into a copy of the implementation.

### 4.1. Extracting a single property

```java
var orders = List.of(
        new OrderView(101L, "PAID", buyer),
        new OrderView(102L, "PENDING", buyer)
);

assertThat(orders)
        .extracting(OrderView::id)
        .containsExactly(101L, 102L);
```

This performs a `List<OrderView> → List<Long>` projection and asserts the ID list. `containsExactly` checks **all elements, exact values, and exact order**. If the API does not guarantee order, use `containsExactlyInAnyOrder` rather than relying on an accidental PK order from a query.

### 4.2. Extracting multiple properties with `tuple`

```java
import static org.assertj.core.api.Assertions.tuple;

assertThat(orders)
        .extracting("id", "status")
        .containsExactly(
                tuple(101L, "PAID"),
                tuple(102L, "PENDING"));
```

Each element yields a `Tuple` containing values in the listed field order. Because string paths carry refactoring risk, AssertJ also provides a type-safe overload taking multiple `Function`s:

```java
assertThat(orders)
        .extracting(OrderView::id, OrderView::status)
        .containsExactly(
                tuple(101L, "PAID"),
                tuple(102L, "PENDING"));
```

This snippet is **an illustration inside a test that already defines `orders`**. When comparing a few clear columns, tuples are often much easier to read than building full objects and ignoring many fields.

### 4.3. `extracting` vs. `flatExtracting` on nested collections

Suppose `OrderView` has `List<Line> lines`:
- `extracting(OrderView::lines)` on `List<OrderView>` produces **one list of lines per element**.
- `flatExtracting(OrderView::lines)` flattens all nested lists into one sequence of elements that can be asserted directly.

```java
// Inside a test with ordersWithLines defined:
assertThat(ordersWithLines)
        .flatExtracting(OrderView::lines)
        .extracting(Line::sku)
        .contains("BK-1", "PN-2");
```

Only use `flatExtracting` when the goal truly concerns the combined collection of child items **regardless of which order owns them**. If the rule is "each order must have its own lines", flattening loses the parent–child relationship; assert per order or use recursive comparison on the tree instead.

### 4.4. Choosing the right collection semantics

| Assertion | What it checks |
| --- | --- |
| `contains(...)` | Contains the stated elements; extra elements allowed |
| `containsOnly(...)` | Contains only the stated elements (no order check; watch duplicate semantics) |
| `containsExactly(...)` | Exact elements, exact order, including duplicate counts |
| `containsExactlyInAnyOrder(...)` | Exact elements and duplicate counts; order ignored |
| `anySatisfy(...)` | At least one element satisfies the checks |
| `allSatisfy(...)` | Every element satisfies the checks |

For REST endpoints with an advertised `ORDER BY`/sort parameter, ordering is part of the contract and should be asserted with `containsExactly`. For queries returning lists without `ORDER BY`, ordering is unguaranteed: never write assertions depending on the incidental order seen on H2 or CI.

## 5. Recursive comparison: traversing the object tree

`usingRecursiveComparison()` creates a deep field-by-field comparison that walks nested objects and collections. For example:

```text
OrderView
├── id
├── status
├── buyer
│   ├── name
│   └── address
│       ├── city
│       └── street
├── lines [Line("BK-1"), Line("PN-2")]
│   ├── sku
│   ├── quantity
│   └── price
├── total
├── createdAt
└── traceId
```

If `buyer.address.city` differs between actual and expected, recursive comparison reports the exact differing field path. AssertJ compares deep structure rather than relying solely on the root object's `equals`. However, for standard types such as `java.lang.String`, `BigDecimal`, and `Instant`, AssertJ applies appropriate value comparison or comparators instead of reflecting into private JDK internals.

### 5.1. Default comparison

```java
assertThat(actual)
        .usingRecursiveComparison()
        .isEqualTo(expected);
```

When matching fields hold equal values and collections match order under default rules, the assertion passes. Even if root objects have different types with matching field structures, recursive comparison can still compare them (more lenient by default than `equals`). That is helpful when comparing a DTO with an entity, though it can hide mismatched object types. If the type itself is part of the contract, add `withStrictTypeChecking()` or check `isInstanceOf(...)` separately.

### 5.2. Intentionally ignoring volatile fields

```java
assertThat(actual)
        .usingRecursiveComparison()
        .ignoringFields("id", "createdAt", "traceId")
        .isEqualTo(expected);
```

This helps when IDs, audit timestamps, or correlation IDs are auto-generated while the test targets business rules and response structure. Nested paths are also supported, such as `"buyer.address.street"`. After ignoring an ID, **keep a separate check** if the contract requires the ID to exist or be valid.

Do not use overly broad ignores like `ignoringFieldsMatchingRegexes(".*")` just to make a test pass: the assertion can become vacuous. When only 2–3 properties matter, `extracting` is usually safer and clearer.

### 5.3. Collection ordering: default and when to ignore

For `List`, element order affects deep comparison by default. If the domain treats line items as an unordered set:

```java
assertThat(actual)
        .usingRecursiveComparison()
        .ignoringCollectionOrderInFields("lines")
        .isEqualTo(expected);
```

`ignoringCollectionOrder()` ignores ordering across **all collections** inside the object; only use it when ordering is irrelevant everywhere. `ignoringCollectionOrderInFields("lines")` is narrower and still protects lists where order matters, such as timelines, workflow steps, or sorted search results.

Ignoring collection order is computationally more expensive; matching many elements can require pairwise comparisons (commonly around \(O(n^2)\) in typical cases). For large lists, assert projections with stable keys or grouped checks, and only disable order checking where needed.

### 5.4. `null` does not mean "ignore all missing fields"

Different APIs have distinct meanings:

| Configuration | Which fields are skipped? | Caveat |
| --- | --- | --- |
| Default | `null` is still compared against `null`/non-null | Often best for complete contracts |
| `ignoringActualNullFields()` | Fields that are `null` **in actual** | Can easily mask a service returning missing data |
| `ignoringExpectedNullFields()` | Fields that are `null` **in expected** | Works for partial expected templates, but skips checking those fields |
| `ignoringActualEmptyOptionalFields()` | Empty `Optional` fields **in actual** | Distinct from null; apply only with clear justification |

Actual and expected are **not symmetric** under these options. `ignoringExpectedNullFields()` is particularly useful when `expected` specifies only a subset of response fields, though if only a few fields matter, `extracting`/`satisfies` usually expresses intent more clearly.

### 5.5. Custom comparators for special data types

`BigDecimal.equals` distinguishes scale: `new BigDecimal("120.0")` is **not equal** to `new BigDecimal("120.00")` via `equals`, even though they are numerically equal. When the domain only cares about numeric value:

```java
assertThat(new BigDecimal("120.0"))
        .isEqualByComparingTo("120.00");

// When total is a field inside an object:
assertThat(actual)
        .usingRecursiveComparison()
        .withComparatorForFields(BigDecimal::compareTo, "total")
        .isEqualTo(expected);
```

Configure per-field comparators when different fields follow different policies. `withComparatorForType(BigDecimal::compareTo, BigDecimal.class)` applies to every `BigDecimal` field in the comparison; use it when the entire domain shares that semantics. For money, never ignore currency or mutate numbers arbitrarily: `100 USD` does not equal `100 VND`.

For `Instant`/`LocalDateTime` when bounded drift is valid due to clock/database precision, configure a comparator with a tolerance **defined by requirements**; do not pick arbitrary large tolerances. Fields like tokens, hashes, versions, and IDs need exact matches, not approximate comparisons.

### 5.6. What if `equals` is overridden?

In AssertJ 3.27.x, recursive comparison defaults to comparing application types field-by-field even if a type overrides `equals`; standard Java/JDK types use their own comparison rules. If you **want** to honor overridden `equals` on fields, AssertJ provides `usingOverriddenEquals()`. Once enabled, you can still force specific fields or types back to deep comparison with `ignoringOverriddenEqualsForFields(...)` or `ignoringOverriddenEqualsForTypes(...)`.

State the contract explicitly:
- If `Address.equals` only compares postcode, using `equals` would miss differences in street.
- If the test needs every address detail, recursive field comparison is right.
- If a type is a value object whose `equals` already captures the full contract, using `isEqualTo` or explicitly enabling `usingOverriddenEquals()` makes sense.

Avoid legacy APIs like `isEqualToComparingFieldByFieldRecursively` when `usingRecursiveComparison()` is available; the newer API offers better configuration and clearer mismatch reporting.

### 5.7. Cyclic references and JPA proxies

AssertJ's recursive comparison handles object graphs with cycles, but that does not mean you should throw an **entire entity graph** into an assertion. With Hibernate/JPA:
- Lazy relationships may trigger unexpected initialization, extra SQL/N+1 queries, or `LazyInitializationException`.
- Hibernate proxies, bidirectional associations, entity `equals/hashCode`, and audit fields can make tests slow or hard to read.
- Comparing a contract-defined DTO projection is usually cleaner than comparing every field of a managed entity.
- If persistence tests need to verify real relationships, load the required state within the transaction and assert meaningful fields/associations rather than relying on internal proxy fields.
- Objects holding streams, sockets, threads, locks, or framework beans should never be recursively compared like data models.

## 6. Hands-on runnable lab: Maven + JUnit 5 + AssertJ

This section is a **complete, copy-and-run lab**; every test passes when files and dependencies are set up properly. It uses Java records to demonstrate nested structures and distinguishes `equals` from recursive comparison policies.

### 6.1. Layout

```text
assertion-lab/
├── pom.xml
└── src/test/java/com/example/assertions/
    └── OrderComparisonTest.java
```

Maven does not require an application main class to run pure JUnit tests. When integrating into a real Spring Boot application, place tests in the corresponding test source set and add `@SpringBootTest` only when the verified behavior actually needs a Spring context.

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>assertion-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
</project>
```

`spring-boot-starter-test` puts JUnit Jupiter and AssertJ on the test classpath. With the Spring Boot parent/BOM, there is no need to pin the AssertJ version manually. If a project uses a different Spring Boot/AssertJ version, inspect the dependency tree to confirm the resolved version:

```bash
mvn dependency:tree -Dincludes=org.assertj:assertj-core
mvn -q -Dtest=OrderComparisonTest test
mvn -q test
```

Tests succeed when Maven exits with code 0; log lines and stdout depend on Maven/JDK/environment, so do not assert a fixed stdout string.

### 6.3. `src/test/java/com/example/assertions/OrderComparisonTest.java`

```java
package com.example.assertions;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.assertj.core.api.SoftAssertions;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;

class OrderComparisonTest {

    record Address(String city, String street) {}
    record Buyer(String name, Address address) {}
    record Line(String sku, int quantity, BigDecimal price) {}

    record OrderView(
            Long id,
            String status,
            Buyer buyer,
            List<Line> lines,
            BigDecimal total,
            Instant createdAt,
            String traceId) {}

    private static OrderView actualOrder() {
        return new OrderView(
                101L,
                "PAID",
                new Buyer("An", new Address("Hanoi", "Trang Tien")),
                List.of(
                        new Line("BK-1", 2, new BigDecimal("50.00")),
                        new Line("PN-2", 1, new BigDecimal("20.00"))),
                new BigDecimal("120.00"),
                Instant.parse("2026-11-08T06:00:00Z"),
                "request-actual");
    }

    private static OrderView sameBusinessData() {
        return new OrderView(
                999L, // different database-generated ID
                "PAID",
                new Buyer("An", new Address("Hanoi", "Trang Tien")),
                List.of(
                        new Line("BK-1", 2, new BigDecimal("50.00")),
                        new Line("PN-2", 1, new BigDecimal("20.00"))),
                new BigDecimal("120.0"), // different scale from actual
                Instant.parse("2026-11-08T07:00:00Z"),
                "request-expected");
    }

    @Test
    void checksSelectedProperties() {
        OrderView actual = actualOrder();

        assertThat(actual.status()).isEqualTo("PAID");
        assertThat(actual)
                .extracting(OrderView::status)
                .isEqualTo("PAID");
        assertThat(actual)
                .extracting("buyer.address.city")
                .isEqualTo("Hanoi");
        assertThat(actual)
                .hasFieldOrPropertyWithValue("status", "PAID");
        assertThat(actual.id()).as("generated ID").isPositive();
    }

    @Test
    void projectsListToValuesAndTuples() {
        OrderView paid = actualOrder();
        OrderView pending = new OrderView(
                102L, "PENDING", paid.buyer(), List.of(),
                BigDecimal.ZERO, paid.createdAt(), "request-two");
        List<OrderView> orders = List.of(paid, pending);

        assertThat(orders)
                .extracting(OrderView::id)
                .containsExactly(101L, 102L);

        assertThat(orders)
                .extracting("id", "status")
                .containsExactly(
                        tuple(101L, "PAID"),
                        tuple(102L, "PENDING"));

        assertThat(paid.lines())
                .extracting(Line::sku)
                .containsExactly("BK-1", "PN-2");
    }

    @Test
    void comparesNestedObjectsIgnoringGeneratedFields() {
        OrderView actual = actualOrder();
        OrderView expected = sameBusinessData();

        // Record.equals() sees differing ID/time/traceId/BigDecimal scale.
        assertThat(actual).isNotEqualTo(expected);

        // Ignore only generated fields and define scale semantics for total.
        assertThat(actual)
                .usingRecursiveComparison()
                .ignoringFields("id", "createdAt", "traceId")
                .withComparatorForFields(BigDecimal::compareTo, "total")
                .isEqualTo(expected);
    }

    @Test
    void ignoresOrderOnlyForLineItems() {
        OrderView original = actualOrder();

        OrderView reversed = new OrderView(
                original.id(),
                original.status(),
                original.buyer(),
                List.of(original.lines().get(1), original.lines().get(0)),
                original.total(),
                original.createdAt(),
                original.traceId());

        assertThat(reversed)
                .usingRecursiveComparison()
                .ignoringCollectionOrderInFields("lines")
                .isEqualTo(original);
    }

    @Test
    void expectedNullFieldsCanMeanUnspecified() {
        OrderView actual = actualOrder();
        OrderView expected = new OrderView(
                null,
                "PAID",
                actual.buyer(),
                actual.lines(),
                actual.total(),
                null,
                null);

        assertThat(actual)
                .usingRecursiveComparison()
                .ignoringExpectedNullFields()
                .isEqualTo(expected);

        // Because ID was excluded from recursive comparison,
        // verify the ID contract independently:
        assertThat(actual.id()).isNotNull().isPositive();
    }

    @Test
    void actualNullFieldsCanBeIgnoredButShouldBeIntentional() {
        OrderView complete = actualOrder();
        OrderView incomplete = new OrderView(
                complete.id(),
                complete.status(),
                complete.buyer(),
                complete.lines(),
                complete.total(),
                complete.createdAt(),
                null);

        assertThat(incomplete)
                .usingRecursiveComparison()
                .ignoringActualNullFields()
                .isEqualTo(complete);

        // The comparison above does not prove traceId is present.
        assertThat(incomplete.traceId()).isNull();
    }

    @Test
    void comparesNumericValueRatherThanBigDecimalScale() {
        BigDecimal one = new BigDecimal("120.0");
        BigDecimal two = new BigDecimal("120.00");

        assertThat(one).isNotEqualTo(two); // BigDecimal.equals checks scale
        assertThat(one).isEqualByComparingTo("120.00");
    }

    @Test
    void softAssertionsCollectIndependentFailures() {
        OrderView actual = actualOrder();

        SoftAssertions softly = new SoftAssertions();
        softly.assertThat(actual.status()).isEqualTo("PAID");
        softly.assertThat(actual.buyer().name()).isEqualTo("An");
        softly.assertThat(actual.lines())
                .extracting(Line::quantity)
                .containsExactly(2, 1);
        softly.assertAll();
    }
}
```

### 6.4. Analyzing each test and its outcome

| Test | What is proven | What is **not** proven |
| --- | --- | --- |
| `checksSelectedProperties` | Accessor, field/property extraction, and ID assertion | Entire object graph, DB persistence |
| `projectsListToValuesAndTuples` | List projection; count, order, and ID/status pairs | Every field of each item |
| `comparesNestedObjectsIgnoringGeneratedFields` | Equivalent business structure across nested fields regardless of ID/time/trace and `total` scale | Whether generated ID/time are actually valid unless asserted separately |
| `ignoresOrderOnlyForLineItems` | Line contents independent of ordering | Line ordering (intentionally ignored) |
| `expectedNullFieldsCanMeanUnspecified` | Expected can serve as a partial template; ID checked separately | Values of `createdAt`/`traceId` |
| `actualNullFieldsCanBeIgnoredButShouldBeIntentional` | How ignoring actual nulls behaves; test also asserts null explicitly | Must not be read as confirming all required fields are present |
| `comparesNumericValueRatherThanBigDecimalScale` | Numeric equality across different scales | Specific decimal places required for display/DB storage |
| `softAssertionsCollectIndependentFailures` | Independent conditions and `assertAll()` | Does not replace deep comparison if the entire graph is the contract |

Looking at the examples shows: **no single recursive comparison alone protects every contract**. It shines when verifying many fields; after ignoring dynamic fields, still assert their independent contracts separately.

### 6.5. Trying an intentionally failing assertion to learn how to read diffs

In a copy of the test, change `city` in expected to `"Hue"` while keeping the recursive assertion. Run:

```bash
mvn -Dtest=OrderComparisonTest#comparesNestedObjectsIgnoringGeneratedFields test
```

When expected differs from actual at `buyer.address.city`, the test must **FAIL**. AssertJ normally prints the field path and actual/expected values (exact formatting depends on the version). Meaning of the diff:

```text
buyer.address.city:
  actual   = "Hanoi"
  expected = "Hue"
```

The block above **illustrates the diff meaning, not verbatim stdout**. After experimenting, restore `"Hanoi"` so the suite returns to PASS. When diagnosing failures, read the failing field path before modifying `equals` or adding `ignoringFields`.

## 7. Placing assertions at the right place in Spring Boot

AssertJ syntax stays the same between unit and integration tests, but **the observed subject** and the meaning of passing differ.

### 7.1. Service/domain unit tests

Prefer:
- Return values and business invariants: status, amounts, line quantities, ownership.
- Projections of key fields: `extracting` or `satisfies`.
- Recursive comparison when a service builds a DTO with a relatively stable tree.
- Never assert entire Spring beans, proxies, repository objects, or internal framework state.

Example service returning `OrderView`:
```java
// Illustrative code inside a test; service and request come from the real application.
OrderView actual = service.createOrder(request);

assertThat(actual.id()).isPositive();
assertThat(actual)
        .usingRecursiveComparison()
        .ignoringFields("id", "createdAt", "traceId")
        .isEqualTo(expectedOrder);
```

In the snippet above, `service`, `request`, and `expectedOrder` are variables **from a real project**, not a continuation of the standalone file in section 6. When ignoring a generated ID, keep a check like `isPositive()`/`isNotNull()` appropriate to the contract.

### 7.2. Web slice: verify the JSON contract first

With `@WebMvcTest` and `MockMvc`, the primary focus is HTTP status, headers, JSON paths, validation, and exception mapping. When working directly with JSON:

```java
// Illustrative code with MockMvc injected in @WebMvcTest:
mvc.perform(get("/orders/101"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("PAID"))
        .andExpect(jsonPath("$.buyer.address.city").value("Hanoi"));
```

This snippet needs static imports `get`, `status`, and `jsonPath` in a real Spring MVC test class. Do not parse JSON into an object solely for recursive comparison if 2–3 JSONPaths already express the contract cleanly; likewise, do not compare every response field via a rigid snapshot if the API includes dynamic traces, links, or timestamps.

When comparing a JSON snapshot is genuinely valuable, deserialize into a DTO and use AssertJ. Be mindful of missing fields, `null` fields, numeric types, and array ordering—JSONPath/JSON structural assertions and recursive Java object comparison are not completely equivalent.

### 7.3. Repository/JPA slice: verify persisted and reloaded data

In `@DataJpaTest`, fetch the entity from the repository after `flush` and, when needed, `clear` the persistence context to avoid reading back the same managed instance already in memory. Then compare **the fields the database must preserve**. Example:

```java
// Illustrative snippet: repository and entityManager injected in a JPA test.
repository.saveAndFlush(entity);
entityManager.clear();
var loaded = repository.findById(entity.getId()).orElseThrow();

assertThat(loaded.getStatus()).isEqualTo("PAID");
assertThat(loaded.getLines())
        .extracting(OrderLineEntity::getSku)
        .containsExactlyInAnyOrder("BK-1", "PN-2");
```

This is an **illustrative pattern**, not standalone runnable code because the entity/repository/`EntityManager` belong to the project. Only use `containsExactly` on lines when mappings and queries define `@OrderColumn`, `@OrderBy`, or an ordering contract; by default, collection relationships do not guarantee "insertion order".

Avoid recursive comparison over an entire entity graph when entities involve lazy proxies, bidirectional relations, soft-delete flags, versions, audit fields, or internal persistence state. Map to a DTO first or assert meaningful fields and associations directly.

### 7.4. Integration tests: observable outcomes across layers

When `@SpringBootTest` tests an order-creation flow through controller/service/repository:
1. Send the request and capture the response.
2. Assert response status/headers/contract.
3. Load persisted state from the repository in an appropriate transaction.
4. Assert persisted business fields, associations, and important side effects.
5. Ignore only genuinely non-deterministic fields; if a field has rules (non-null ID, timestamp within range), assert those separately.

A recursive comparison on the response DTO **does not prove** transaction commit, unique constraints, emitted events, or database writes. Conversely, verifying the loaded entity equals expected does not prove the controller returned the right HTTP contract. Every assertion must match an observable boundary.

## 8. Advanced configuration and limits to understand

### 8.1. Comparing only specific fields with `comparingOnlyFields`

When an object is large and you only want a subset of its structure rather than ignoring ten unrelated fields:

```java
assertThat(actual)
        .usingRecursiveComparison()
        .comparingOnlyFields("status", "buyer.address.city")
        .isEqualTo(expected);
```

This restricts the comparison to the listed fields; use it only when **that exact subset is the contract**, because any unlisted fields will not be flagged if wrong. Prefer `extracting` if there are only two scalar fields and direct access is clearer.

### 8.2. Type checking

```java
assertThat(actual)
        .usingRecursiveComparison()
        .withStrictTypeChecking()
        .isEqualTo(expected);
```

When actual and expected differ in types, strict mode rejects incompatible types; it does not require every field to be "the same instance". If comparing a JPA entity against a DTO, decide deliberately whether you want to prove **matching business data** or **matching types**. Testing DTO projections is usually more stable than forcing strict type checks across entity graphs.

### 8.3. Field comparators and type comparators

Common APIs:
- `withComparatorForFields(comparator, "total")`: applies only to specific field paths.
- `withComparatorForType(comparator, SomeType.class)`: applies to all fields matching that type under AssertJ rules.
- `withEqualsForFields(predicate, "field")` and `withEqualsForType(predicate, Type.class)`: define custom equality without requiring an ordering comparator.

For example, monetary amounts rounded to 2 decimal places have different equality rules from temperature tolerances. Comparators must reflect domain logic—never configure arbitrary tolerances just to avoid failures.

### 8.4. Comparing collections of objects without `equals`

If a list-level assertion uses `contains(expectedObject)`, element matching normally relies on `equals`. For POJOs that do not override `equals`, the assertion can fail even when fields match. You can use:

```java
assertThat(actualList)
        .usingRecursiveFieldByFieldElementComparator()
        .contains(expectedElement);
```

This is an **illustration**: `actualList` and `expectedElement` are supplied by the test. `usingRecursiveFieldByFieldElementComparator()` configures how each **element** is compared in an iterable assertion; it is **different** from `assertThat(actualObject).usingRecursiveComparison().isEqualTo(expectedObject)` on a full object graph. When you need detailed field-path mismatch messages across an object, object-level recursive comparison is usually better.

### 8.5. Performance and determinism

- Large graphs, cyclic relationships, order-ignored collections, and complex custom comparators can slow tests down.
- Clocks/dates, random UUIDs, auto-generated IDs, lazy queries, and concurrent mutations make snapshots non-repeatable.
- Use a fixed clock, isolated test data, explicitly ordered SQL, constant fixtures, and stable projections.
- Never rely on `HashMap`/`HashSet` iteration order; when order is not in the contract, use order-independent assertions.
- If large objects contain sensitive fields, diff messages can print the whole graph: choose narrower assertions or representations that omit secrets.
- Do not confuse "deep comparison" with cloning/copying. Recursive assertions only **read and compare values** (aside from getter/lazy-loading side effects); they do not copy objects.

## 9. Choosing assertions by requirement scenario

| Test requirement | Good starting choice | Explanation |
| --- | --- | --- |
| Result returns status `PAID` | `assertThat(actual.status()).isEqualTo("PAID")` | Single value, clear contract |
| API returns list ordered by `createdAt` | `extracting(...).containsExactly(...)` | Ordering is a requirement |
| API returns ID set with unguaranteed order | `extracting(...).containsExactlyInAnyOrder(...)` | Avoids depending on unadvertised ordering |
| Nested buyer/address/lines DTO must match most fields | `usingRecursiveComparison().isEqualTo(expected)` | Checks full structure and reports diffs |
| DTO has server-generated ID/timestamp | Recursive `ignoringFields(...)` + separate ID/time checks | Prevents field ignores from hiding contracts |
| Entity/DTO have different classes but same business data | Projection or recursive with explicit type policy | Avoids forcing entity `equals` to match DTO |
| `BigDecimal("1.0")` vs `BigDecimal("1.00")` must match numerically | `isEqualByComparingTo` or field comparator | `equals` distinguishes scale |
| `lines` order irrelevant while `timeline` order matters | `ignoringCollectionOrderInFields("lines")` | Keeps order checks where required |
| Expected object only populates a few fields | `extracting` or `ignoringExpectedNullFields()` | Limits "null = anything goes" risk |
| One test should report failures across multiple properties | `SoftAssertions` + `assertAll()` | Collects failures; do not forget the final call |
| JPA entity has lazy relationships | Assert scalars/projections, map what is needed | Avoids traversing graphs outside transactions |
| REST JSON has 3 key fields | MockMvc `jsonPath` assertions | Clear HTTP contract |
| Integration outcome has multiple side effects | Assertions for HTTP + persisted state + events | Recursive DTO comparison does not replace side effects |

## 10. Common mistakes and fixes

### 10.1. Using `isEqualTo` on a POJO that does not override `equals`

**Symptom:** two objects print identical field values yet the assertion fails. **Cause:** `Object.equals` compares reference identity. **Fix:** decide whether the type should be a value object (implementing `equals`), or whether the test simply needs recursive comparison or projection. Do not mechanically alter domain models solely to appease a test.

### 10.2. Using recursive comparison while ignoring too many fields

**Symptom:** test still passes even when response omits amount, currency, or status. **Cause:** overly broad `ignoringFieldsMatchingRegexes` or `ignoringExpectedNullFields` hides fields. **Fix:** only ignore ID/audit fields with justification, and assert remaining invariants separately; when only one projection matters, assert directly.

### 10.3. Confusing actual and expected when ignoring nulls

**Symptom:** swapping the two objects changes test behavior. **Cause:** `ignoringActualNullFields` and `ignoringExpectedNullFields` are asymmetric. **Fix:** stick to `assertThat(actual) ... isEqualTo(expected)`, name variables `actual`/`expected`, and add tests for disallowed nulls.

### 10.4. Assuming repository return order is fixed

**Symptom:** CI fails intermittently or on a different database. **Cause:** SQL lacks `ORDER BY`. **Fix:** if the contract requires ordering, add sorting to the query and use `containsExactly`; otherwise use `containsExactlyInAnyOrder` or ignore collection order **only on the relevant field**.

### 10.5. Comparing money with `equals` without checking scale

**Symptom:** `10.0` and `10.00` are treated as unequal. **Fix:** use `isEqualByComparingTo` or a comparator; if scale belongs to the display/storage contract, keep exact scale checks rather than ignoring it.

### 10.6. Comparing object graphs containing JPA proxies/lazy fields

**Symptom:** slow tests, unexpected SQL, `LazyInitializationException`. **Fix:** clarify the contract under test, load required associations, map to a DTO, or assert persistence fields directly.

### 10.7. Confusing `extracting`, `flatExtracting`, and recursive comparison

**Symptom:** flattening a list loses order-to-line ownership; checking only SKU misses quantity/total bugs. **Fix:** ask whether you need to check *a list of values*, *tuples of element fields*, or *the whole object tree*. Use projections/tuples for narrow contracts and recursive comparison when relationships and many fields matter.

### 10.8. Assertions tightly coupled to implementation

**Symptom:** behavior-preserving refactoring breaks tests because a private field was renamed or internal entity structure changed. **Fix:** prefer API outputs, public accessors, and domain invariants. Recursive comparison on DTOs is more stable than on internal Spring components or entity proxies.

### 10.9. Test passes even though data was never saved

**Symptom:** service returns the right DTO while repository save did not happen or rolled back. **Cause:** asserting only the return object. **Fix:** add integration tests checking real DB state/events at the boundary; unit assertions are not responsible for proving infrastructure persistence.

### 10.10. Forgetting `assertAll()` on `SoftAssertions`

**Symptom:** soft assertions fail to fail the test as expected. **Fix:** call `softly.assertAll()` or use `SoftAssertions.assertSoftly(...)` so checks are always finalized.

## 11. Reading assertion failures and improving tests

When a recursive comparison fails:
1. Locate **the failing path**: e.g., `buyer.address.city`, `lines[1].sku`, `total`.
2. Inspect **actual/expected values** and types; for numbers/money, check precision and scale.
3. Inspect **assertion configuration**: ignored fields, ignored ordering, null policy, type comparators, or strict mode.
4. Check **inputs** and outputs at the boundary: was the bug in service rules, web mapping, SQL, or the test fixture?
5. Fix the code or `expected` **according to the contract**. Only add ignores or comparators if the business genuinely does not care about that difference.

Structure tests using Given / When / Then:
- **Given:** build `expected` from requirements, never by serializing/copying `actual`.
- **When:** call the subject under test once at a meaningful boundary.
- **Then:** narrow assertions for critical rules, recursive comparison when full structure matters, plus separate checks for fields with special policies.

Avoid cloning `actual` to create `expected` with almost identical fields: when the implementation has a bug, `expected` copies the bug too. Build `expected` from independent, clearly named values.

## 12. Self-check exercises

1. An API returns two orders with no guaranteed ordering. Verify both ID and status for each order using `extracting("id", "status")` and `containsExactlyInAnyOrder(tuple(...), tuple(...))`. Why is `containsExactly` inappropriate?
2. `OrderView` has `createdAt` and `traceId` changing on every request. Write a recursive assertion ignoring just those two fields, then add assertions verifying `createdAt` is non-null or within an acceptable range. If you also ignored `total`, what contract would the test lose?
3. The `lines` list is in reverse order. Run first with default recursive comparison, then with `ignoringCollectionOrderInFields("lines")`. Explain when each test is valid under two different contracts.
4. For `BigDecimal("42.0")` and `BigDecimal("42.00")`, test `equals`, `compareTo`, and `isEqualByComparingTo`. If the system requires exactly 2 decimal places, should scale still be ignored?
5. Write a test demonstrating `ignoringExpectedNullFields()` where expected only sets `status`, then deliberately make `actual.status` wrong. The test must FAIL; why must `status` not be left `null` in `expected`?
6. Refactor an assertion that recursively compares an entire entity graph into a repository projection containing only `id`, `status`, `buyerName`, and `total`. Compare clarity and stability regarding proxies/lazy loading.

Completion criteria: you can explain **which object, which fields, and which semantics** are being compared, and identify whether any ignored fields require separate assertions.

## 13. Project adoption checklist

- [ ] Is `actual` the real output of the unit/service/web/repository, and `expected` built independently from requirements?
- [ ] When only a few properties matter, were direct accessors/`extracting` considered?
- [ ] When comparing the whole tree, does `usingRecursiveComparison` match DTO/domain semantics?
- [ ] Are there auto-generated IDs/times/traces? Are they ignored in the smallest possible scope and asserted separately where needed?
- [ ] Does the collection have an ordering contract? Were `containsExactly` or `containsExactlyInAnyOrder` chosen deliberately?
- [ ] Do `BigDecimal`, date/time, floating-point, or currency fields require custom comparators?
- [ ] Could `ignoringActualNullFields` or `ignoringExpectedNullFields` skip required fields?
- [ ] Are type differences between actual and expected intentional? Is `withStrictTypeChecking` needed?
- [ ] Do JPA proxies, lazy relationships, or cycles make recursive comparison overly broad?
- [ ] Do test failures clearly pinpoint what broke (`as(...)`/field path) without leaking secrets?
- [ ] If using `SoftAssertions`, is `assertAll()` always called?
- [ ] Do assertions verify behavior at the right boundary without inferring DB/HTTP/transaction correctness solely from DTO equality?

**Practical conclusion:** check **individual properties** when a contract covers a few clear values; check **projections/tuples** when collections need stable columns; use **recursive comparison** when most of a nested structure is the contract. Every choice around ignoring fields, nulls, ordering, comparators, or types must have a business reason and be weighed against fault-detection strength.

## 14. Official references

- AssertJ Core — documentation and Extracting / Field by Field Recursive Comparison: https://assertj.github.io/doc/
- AssertJ 3.27.6 — `RecursiveComparisonAssert` API: https://javadoc.io/doc/org.assertj/assertj-core/3.27.6/org/assertj/core/api/RecursiveComparisonAssert.html
- AssertJ 3.27.6 — `AbstractObjectAssert` API: https://javadoc.io/doc/org.assertj/assertj-core/3.27.6/org/assertj/core/api/AbstractObjectAssert.html
- Spring Boot 3.5 — Testing: https://docs.spring.io/spring-boot/3.5/reference/testing/index.html
- JUnit 5 — User Guide: https://docs.junit.org/5.11.4/user-guide/
- Java 17 — Record classes: https://docs.oracle.com/en/java/javase/17/language/records.html
