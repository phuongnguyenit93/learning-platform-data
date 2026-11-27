# Boundary Test Suites, Invalid Data, and Acceptance Criteria

## 1. Goals of a Data Test Suite

A feature accepting input data must clearly define three things:

1. What data is accepted?
2. What data must be rejected, and how does the system respond?
3. What evidence demonstrates that the feature meets business requirements?

Testing only a few "normal" examples is rarely sufficient. Bugs cluster around boundaries: quantity equal to 0, strings right at the length limit, an end date equal to the start date, `null` values, whitespace-only strings, or inputs that look valid individually yet violate a combined rule.

In Java 17, a systematic test suite can combine:

- **Equivalence partitioning:** dividing the input domain into groups expected to behave identically.
- **Boundary-value analysis:** focusing on values right on and immediately adjacent to boundaries.
- **Negative testing:** supplying malformed, missing, out-of-bounds, or inconsistent data.
- **JUnit 5:** example-based tests, parameterized tests, and exception assertions.
- **Property-based/fuzz testing:** exploring wide input spaces via invariants or generative strategies.
- **Acceptance criteria:** specifying observable, verifiable conditions for acceptance.
- **Traceability:** linking requirements, acceptance criteria, test cases, and execution results.

A strong test suite covers both success paths and failure paths. Asserting only that a constructor throws on `null` does not prove that valid boundary values are still accepted.

## 2. Starting from the Contract and Input Domain

### 2.1. Write the Contract Before Writing Tests

Suppose a feature creating an order line has these rules:

- `SKU` is required; after trimming leading/trailing whitespace, it must have 3 to 20 uppercase ASCII letters, digits, or hyphens.
- `quantity` is an integer from 1 through 1000.
- `unitPrice` is required, non-negative, and has at most two decimal places.
- `lineTotal` equals `unitPrice` multiplied by `quantity`.
- Valid data is stored in an immutable object.

These rules form the contract used to design tests. Given only "validate order line", a test author would have to guess which inputs are valid.

### 2.2. Distinguishing Required and Optional Conditions

For each field, specify:

| Property | Questions to answer |
|---|---|
| Presence | Is the field required? |
| Nullability | Is `null` allowed? |
| Blankness | Are empty or whitespace-only strings allowed? |
| Format | Is there a pattern or set of allowed values? |
| Range | What are the minimum and maximum values? |
| Length | Measured in bytes, UTF-16 code units, Unicode code points, or graphemes? |
| Precision | Do decimal numbers have scale or rounding limits? |
| Relationship | Does the field depend on another field? |
| Mutability | Can the caller mutate the data after creating the object? |
| Normalization | Should trimming, canonicalization, or conversion occur before validation? |

Never write tests by guessing what `null` or empty strings mean. For example, "notes" might allow `null`, whereas "order ID" might be mandatory.

### 2.3. Separating Boundary Validation from Domain Invariants

At the API/controller layer, validation primarily provides user-friendly request errors: missing fields, malformed syntax, oversized payloads, or unsupported enum values.

In domain objects, constructors or factories enforce invariants so objects remain valid whether constructed from an HTTP request, batch job, message consumer, test, or internal code.

At the persistence/database layer, constraints protect data against race conditions and concurrent writers. For instance, checking in Java that a customer code does not exist yet does not replace a database unique constraint.

Each of the three layers has a distinct purpose. The test suite should verify the contract each layer owns.

## 3. Equivalence Partitioning

### 3.1. Concept

An input domain can be huge or infinite. You do not need to test every value when many inputs share the same expected behavior under the contract. Partition them into equivalence classes, then select representative inputs from each class.

For example, with valid `quantity` from 1 through 1000:

| Partition | Value range | Expected result |
|---|---|---|
| Below range | Integers less than 1 | Reject |
| Valid | 1 through 1000 | Accept |
| Above range | Integers greater than 1000 | Reject |
| Wrong type at API | String, decimal, object | Reject per parsing contract |
| Missing/`null` | Omitted or `null` | Depends on contract; this example rejects |

Picking a representative from each partition keeps the suite concise and purposeful. However, boundaries still require dedicated tests.

### 3.2. Partitioning Strings

For `SKU`:

| Partition | Example | Result |
|---|---|---|
| Null | `null` | Reject |
| Empty | `""` | Reject |
| Whitespace only | `"   "` | Reject |
| Too short | `"A1"` | Reject |
| Valid length, valid characters | `"AB-100"` | Accept |
| Lowercase allowed via normalization | `" ab-100 "` | Normalize then accept |
| Internal space | `"AB 100"` | Reject |
| Disallowed character | `"AB_100"` | Reject |
| Too long | String longer than 20 characters | Reject |

Allowing lowercase via normalization must be explicitly stated in the contract. If the contract requires pre-uppercased input, tests should reject lowercase rather than normalizing it.

### 3.3. Partitioning Dates

For a date range requiring `end >= start`:

- `end` before `start`: invalid.
- `end` equals `start`: valid if same-day ranges are allowed.
- `end` after `start`: valid.
- `start` is `null` or `end` is `null`: reject if both are required.
- Unparseable date string at the API boundary: return a format error.

If the domain requires `end` to be strictly after `start`, change the rule to `end > start`. Even a slight wording difference—"after" vs. "not before"—changes the boundary tests.

### 3.4. Partitioning Collections

For a list of participants:

- `null` collection.
- Empty collection.
- Collection with one valid element.
- Collection at the maximum allowed size.
- Collection exceeding the limit.
- Contains a `null` element.
- Contains a blank element.
- Contains duplicate elements.
- Mix of valid and invalid elements.

Never assume an empty collection is always invalid. An optional tag list may allow empty; an order's line-item list may require at least one item.

## 4. Boundary-Value Analysis

### 4.1. Basic Rule

For a closed valid interval `[min, max]`, the most important test points are typically:

- `min - 1`: immediately below the lower bound.
- `min`: exact lower bound.
- `min + 1`: immediately inside the lower bound.
- `max - 1`: immediately inside the upper bound.
- `max`: exact upper bound.
- `max + 1`: immediately above the upper bound.

For `quantity` from 1 through 1000:

| Value | Result |
|---:|---|
| 0 | Reject |
| 1 | Accept |
| 2 | Accept |
| 999 | Accept |
| 1000 | Accept |
| 1001 | Reject |

Representative mid-range values can be added to check normal processing, but they never replace these six boundary points.

### 4.2. String Length Boundaries

If `SKU` length is 3 to 20:

- 2 characters: reject.
- 3 characters: accept.
- 4 characters: accept.
- 19 characters: accept.
- 20 characters: accept.
- 21 characters: reject.

If the limit is defined in Unicode code points, do not measure with `String.length()`, which counts UTF-16 code units. Use:

~~~java
int codePoints = value.codePointCount(0, value.length());
~~~

If the requirement refers to user-perceived characters, consider grapheme clusters; one visible character can span multiple code points. Never pick a unit of measurement without checking the contract.

### 4.3. Monetary and Precision Boundaries

If an amount must be non-negative with at most two decimal places, test:

- Smallest negative value at the supported scale.
- Zero.
- Small positive value.
- Maximum allowed business limit.
- Exceeding the business limit.
- Scales 0, 1, and 2.
- Scale 3.
- Numerically equal values with different scales.

For example, `new BigDecimal("1.0")` and `new BigDecimal("1.00")` are numerically equal under `compareTo`, yet `equals` returns `false` because their scales differ. Tests must reflect the contract: capping fractional digits vs. requiring an exact scale are two different rules.

### 4.4. Date and Time Boundaries

For timestamps or dates:

- Immediately before the allowed cutoff.
- Exactly on the cutoff.
- Immediately after the cutoff.
- Midnight transitions in the business time zone.
- End of month and start of next month.
- Leap days.
- Conversions between UTC and business time zones.

Never call `LocalDate.now()` directly in tests when expectations depend on the current time. Inject a `Clock` to fix time.

### 4.5. Combined Boundaries

With multiple fields, testing each boundary in isolation can still miss cross-field bugs:

- Valid `start` and valid `end`, yet `end` precedes `start`.
- Valid `quantity` and valid `price`, yet their product exceeds a limit.
- Valid country code, yet postal code is invalid for that country.
- Valid discount, yet greater than the subtotal.
- Valid currency, yet unsupported for the chosen payment method.

These are cross-field invariants. Include tests for business-meaningful combinations.

## 5. Invalid Data Test Suites

### 5.1. Error Categories to Cover

| Category | Examples | Test question |
|---|---|---|
| Missing data | Field omitted from request | Is the field required? |
| Null | JSON `null` or Java `null` | Is `null` permitted? |
| Blank | `""`, `"   "` | Does blank behave differently from `null`? |
| Invalid format | Code contains disallowed characters | Is it rejected before persistence? |
| Out of range | Negative number or above max | Are bounds applied inclusively or exclusively? |
| Invalid precision | Amount has too many decimal places | Reject or round per contract? |
| Oversized | Payload, string, or collection too large | Are resource limits enforced? |
| Inconsistent | End date before start date | Are cross-field rules enforced? |
| Duplicates | Repeated IDs or items | Are duplicates allowed? |
| Unusual Unicode | Control chars, combining marks, confusables | How is the Unicode policy enforced? |
| Encoding/parsing error | Unparseable date or number | Is the error response consistent? |
| Invalid state | Disallowed state transition | Are invalid transitions rejected? |
| Malicious input | Deeply nested payload, injection string | Does validation protect the boundary properly? |

### 5.2. Null and Absent Are Not Always Equivalent

In JSON APIs, three states may carry distinct meanings:

1. Field is absent.
2. Field is present with value `null`.
3. Field is present with an empty string or default value.

In partial-update (`PATCH`) APIs, absent may mean "keep existing", `null` may mean "clear field", while an empty string may be invalid. Tests should clearly capture each state's contract.

Do not lump absent, `null`, and blank into one test if the system must treat them differently.

### 5.3. Syntax Errors vs. Semantic Errors

A string can be syntactically valid yet semantically invalid:

- `"2026-02-31"` matches an ISO date pattern yet is not a valid calendar date.
- A code matches the pattern yet does not exist in the catalog.
- A currency code has valid syntax yet is unsupported by the product.
- An email parses validly yet the address is unverified.

Separate parsing tests, domain validation tests, and external reference checks. Do not force one regex to carry every validation layer.

### 5.4. Resource Limits

Invalid data also includes excessively large inputs:

- Strings exceeding limits.
- Arrays with millions of elements.
- Deeply nested JSON structures.
- Oversized file uploads.
- Item counts whose calculation or processing exceeds budgets.

These limits protect system resources and should be checked at the boundary before allocating large structures or performing expensive work. Tests should verify early rejection and controlled error responses.

## 6. Designing Executable Test Cases

### 6.1. What Information Does a Test Case Need?

A test case specification can include:

| Field | Content |
|---|---|
| ID | Stable test identifier |
| Requirement | Linked requirement or rule |
| Input | Concrete input data |
| Preconditions | Required state before the test |
| Action | Operation executed |
| Expected result | Expected outcome or exception |
| Observable evidence | HTTP response, persisted state, event, or output |
| Priority | Importance level |

A test case should never simply say "test bad data". It must specify which input is invalid, which rule it violates, and how the system must respond.

### 6.2. Positive and Negative Tests

For each rule, include:

- At least one valid case.
- One or more representative invalid cases.
- Points immediately adjacent to boundaries.
- Interaction tests with related rules where applicable.

Example for `quantity`:

| Test ID | Input | Expected |
|---|---:|---|
| QTY-001 | 1 | Accept |
| QTY-002 | 1000 | Accept |
| QTY-003 | 0 | Reject |
| QTY-004 | -1 | Reject |
| QTY-005 | 1001 | Reject |

### 6.3. Expected Results Must Be Specific

Never write expected results like "show error". Specify:

- Which exception type the constructor throws.
- Which HTTP status code the API returns per contract.
- Which error code appears in the response.
- That invalid data is not persisted.
- That no events or side effects are emitted when validation fails.
- Whether other valid fields are preserved.

Avoid asserting fragile details of exception messages unless the exact message is part of the public contract. Asserting exception types and stable error codes couples tests far less tightly to internal phrasing.

## 7. JUnit 5 for Data Testing

### 7.1. One Test per Clear Behavior

JUnit Jupiter uses the `@Test` annotation:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class QuantityTest {

    @Test
    void acceptsMinimumQuantity() {
        Quantity quantity = new Quantity(1);

        assertEquals(1, quantity.value());
    }
}
~~~

Test names describe the condition and outcome. When a test fails, the name makes reports understandable without immediately opening the source file.

### 7.2. Asserting Exceptions with assertThrows

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class QuantityTest {

    @Test
    void rejectsZero() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Quantity(0)
        );
    }
}
~~~

`assertThrows` returns the caught exception instance, allowing you to inspect error codes or messages when required by the contract:

~~~java
IllegalArgumentException exception = assertThrows(
        IllegalArgumentException.class,
        () -> new Quantity(0)
);
assertEquals("quantity must be between 1 and 1000",
        exception.getMessage());
~~~

Do not lock down internal phrasing if the API only guarantees the exception type. If callers branch on error conditions, design stable error codes rather than relying on prose messages.

### 7.3. Parameterized Tests

When multiple inputs share the same behavior, use `@ParameterizedTest` to avoid duplication:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class QuantityInvalidInputTest {

    @ParameterizedTest
    @ValueSource(ints = {-1, 0, 1001, 5000})
    void rejectsOutOfRangeValues(int value) {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Quantity(value)
        );
    }
}
~~~

Parameterized tests are especially effective for boundary values, format variants, and invalid input partitions.

### 7.4. Using CsvSource for Tabular Test Data

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class QuantityBoundaryTest {

    @ParameterizedTest
    @CsvSource({
            "1, true",
            "2, true",
            "999, true",
            "1000, true",
            "0, false",
            "-1, false",
            "1001, false"
    })
    void validatesBoundary(int value, boolean expectedValid) {
        if (expectedValid) {
            assertEquals(value, new Quantity(value).value());
        } else {
            assertThrows(
                    IllegalArgumentException.class,
                    () -> new Quantity(value)
            );
        }
    }
}
~~~

This example demonstrates tabular test representation. In real suites, you can separate positive and negative tests for clearer failure reports, or use `assertDoesNotThrow` for valid cases.

### 7.5. MethodSource for Complex Test Data

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class AccountCodeTest {

    static Stream<Arguments> invalidCodes() {
        return Stream.of(
                Arguments.of(""),
                Arguments.of("  "),
                Arguments.of("A1"),
                Arguments.of("AB_100"),
                Arguments.of("AB 100"),
                Arguments.of("A".repeat(21))
        );
    }

    @ParameterizedTest
    @MethodSource("invalidCodes")
    void rejectsInvalidCodes(String code) {
        assertThrows(
                IllegalArgumentException.class,
                () -> AccountCode.of(code)
        );
    }
}
~~~

`MethodSource` fits cases needing multiple arguments, sample objects, or programmatically generated inputs.

### 7.6. assertAll for Independent Conditions

~~~java
import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;

assertAll(
        () -> assertEquals("AC-100", account.code()),
        () -> assertEquals("An", account.displayName()),
        () -> assertEquals(1, account.quantity())
);
~~~

`assertAll` executes all assertions independently and reports all failures in one run. Do not use it to group dependent steps; if an earlier step failing renders later assertions meaningless, split the test or assert sequentially.

### 7.7. assertDoesNotThrow for Valid Values

~~~java
assertDoesNotThrow(() -> new Quantity(1000));
~~~

Usually, it is even better to capture the created object and assert its state:

~~~java
Quantity quantity = assertDoesNotThrow(() -> new Quantity(1000));
assertEquals(1000, quantity.value());
~~~

This verifies both that no exception was thrown and that the value was stored properly.

## 8. Example Domain Model and Boundary Test Suite

### 8.1. The Quantity Class

~~~java
public record Quantity(int value) {
    public Quantity {
        if (value < 1 || value > 1000) {
            throw new IllegalArgumentException(
                    "quantity must be between 1 and 1000"
            );
        }
    }
}
~~~

The compact constructor enforces the invariant on every instantiation path.

### 8.2. Testing Every Boundary

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class QuantityTest {

    @Test
    void acceptsLowerAndUpperBounds() {
        assertEquals(1, new Quantity(1).value());
        assertEquals(1000, new Quantity(1000).value());
    }

    @Test
    void acceptsValuesImmediatelyInsideBounds() {
        assertEquals(2, new Quantity(2).value());
        assertEquals(999, new Quantity(999).value());
    }

    @Test
    void rejectsValuesImmediatelyOutsideBounds() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new Quantity(0)
        );
        assertThrows(
                IllegalArgumentException.class,
                () -> new Quantity(1001)
        );
    }
}
~~~

Grouping tests by meaning clarifies which tests need updating if boundaries change.

### 8.3. Testing Null and Blank Separately

For strings, `null` and blank are distinct partitions:

~~~java
@Test
void rejectsNullCode() {
    assertThrows(
            NullPointerException.class,
            () -> AccountCode.of(null)
    );
}

@ParameterizedTest
@ValueSource(strings = {"", " ", "   ", "\t", "\n"})
void rejectsBlankCode(String value) {
    assertThrows(
            IllegalArgumentException.class,
            () -> AccountCode.of(value)
    );
}
~~~

Select whitespace characters according to the contract. If the code uses `strip()` and `isBlank()`, add tests covering Unicode whitespace characters that the system must handle.

## 9. Testing Normalization and Unicode

### 9.1. Verify Inputs Are Canonicalized Properly

If the contract allows stripping and uppercasing:

~~~java
@ParameterizedTest
@CsvSource({
        "' ac-100 ', AC-100",
        "ac-100, AC-100",
        "AC-100, AC-100"
})
void normalizesAccountCode(String input, String expected) {
    assertEquals(expected, AccountCode.of(input).value());
}
~~~

Tests must assert the stored canonical value, not merely that construction did not throw.

### 9.2. Verify Normalization Idempotence

If a normalization function's contract is idempotent:

~~~java
String once = normalize(input);
String twice = normalize(once);
assertEquals(once, twice);
~~~

This property catches normalization functions that keep mutating values on repeated passes.

### 9.3. Test Unicode Using the Chosen Measurement Unit

If the limit counts Unicode code points:

~~~java
int count = value.codePointCount(0, value.length());
~~~

Include tests with:

- ASCII characters.
- Characters outside the Basic Multilingual Plane.
- Characters with combining marks.
- Canonically equivalent NFC and NFD strings.
- Control characters if forbidden by policy.
- Look-alike characters with different code points if identifiers are security-sensitive.

Do not use a single "accented Vietnamese" test to conclude that all Unicode cases are handled. Tie tests to the specific normalization form, character policy, and length-counting rule.

### 9.4. Do Not Depend on the Default Locale

For identifiers using `Locale.ROOT`, tests should confirm results stay unchanged even if the JVM default locale changes. You can save the old locale, switch locale inside the test, and restore it in `finally`; avoid running tests in parallel if they mutate the global default locale.

Alternatively, inspect the helper directly to verify `Locale.ROOT` is always passed, and test inputs whose case mappings vary by locale to prove consistent behavior.

## 10. Testing Dates and Times Deterministically

### 10.1. Avoid Depending on the Real Clock

Tests like the following can become flaky across midnight:

~~~java
assertTrue(expiry.isAfter(LocalDate.now()));
~~~

If a constructor or service reads current time implicitly, outcomes depend on when the test runs and the host time zone.

### 10.2. Injecting Clock

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-15T10:00:00Z"),
        ZoneOffset.UTC
);
~~~

The service receives `Clock` via its constructor:

~~~java
final class ExpiryPolicy {
    private final Clock clock;

    ExpiryPolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    boolean isExpired(Instant expiry) {
        return !expiry.isAfter(clock.instant());
    }
}
~~~

Boundary test:

~~~java
@Test
void treatsExactExpiryInstantAsExpired() {
    Instant now = Instant.parse("2026-01-15T10:00:00Z");
    Clock clock = Clock.fixed(now, ZoneOffset.UTC);
    ExpiryPolicy policy = new ExpiryPolicy(clock);

    assertTrue(policy.isExpired(now.minusNanos(1)));
    assertTrue(policy.isExpired(now));
    assertFalse(policy.isExpired(now.plusNanos(1)));
}
~~~

Define the exact behavior when time equals expiry: the example above treats `expiry <= now` as expired. Adjust expected outcomes if your contract differs.

### 10.3. Testing Time Zones and DST

When business rules depend on local calendar dates, specify the time zone explicitly via `ZoneId` rather than relying on the machine default. Test timestamps such as:

- Immediately before and after midnight in the business time zone.
- DST transitions if the time zone observes daylight saving time.
- Leap days.
- Month-end and year-end transitions.

Not every system needs DST tests; include them when the domain operates in DST-observing zones or performs local-time calculations.

## 11. Cross-Field Testing and Decision Tables

### 11.1. Decision Tables

When outcomes depend on multiple conditions, a decision table ensures combinations are not overlooked:

| `start` present? | `end` present? | `end >= start`? | Result |
|---|---|---|---|
| No | Yes | N/A | Reject |
| Yes | No | N/A | Reject |
| Yes | Yes | No | Reject |
| Yes | Yes | Yes | Accept |

With many boolean conditions, you do not always need every Cartesian combination if some are impossible or equivalent. Document the rationale for test selection.

### 11.2. Testing Combined Ranges

~~~java
public record DateRange(LocalDate start, LocalDate end) {
    public DateRange {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");
        if (end.isBefore(start)) {
            throw new IllegalArgumentException(
                    "end must not be before start"
            );
        }
    }
}
~~~

~~~java
@Test
void acceptsSameDayRange() {
    LocalDate day = LocalDate.of(2026, 5, 10);
    assertEquals(day, new DateRange(day, day).end());
}

@Test
void rejectsEndBeforeStart() {
    LocalDate start = LocalDate.of(2026, 5, 11);
    LocalDate end = LocalDate.of(2026, 5, 10);

    assertThrows(
            IllegalArgumentException.class,
            () -> new DateRange(start, end)
    );
}
~~~

### 11.3. Pairwise Testing

When there are many independent fields with multiple values, the full Cartesian product can explode test counts. Pairwise testing picks a subset of tests ensuring every pair of values across any two parameters appears at least once.

Pairwise testing works well when failures stem from two-factor interactions, but it does not replace targeted tests for critical invariants involving three or more factors. Specific business rules still require explicit tests.

## 12. Testing APIs with Invalid Data

### 12.1. Define the HTTP Contract

For an order-creation API, you might specify:

- Valid request: returns success status and creates the resource.
- Malformed JSON: returns parsing error per API contract.
- Missing/`null` required field: returns validation error.
- Out-of-range `quantity`: returns field-level error.
- Non-existent reference: returns appropriate business error.
- Payload exceeding size limit: rejected before deep processing.

There is no single HTTP status code valid for all APIs; follow your product contract. Typically, client syntax/validation errors map to `4xx`, while system failures map to `5xx`. Tests must match the published API contract.

### 12.2. Verify the Response Body, Not Just the Status

A useful validation response might look like:

~~~json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "quantity",
      "code": "OUT_OF_RANGE",
      "message": "quantity must be between 1 and 1000"
    }
  ]
}
~~~

This JSON is an illustrative schema, not a mandatory standard. Tests should verify:

- Status code.
- Stable error code.
- Affected field.
- No stack traces or internal implementation leaks.
- No created resources or side effects when the request is rejected.

If user-facing messages may be localized, assert on error codes and fields rather than brittle literal message text.

### 12.3. Verify Zero Side Effects

When validation fails, confirm:

- No new row is written to the database.
- No message or event is published.
- No funds are debited or inventory modified.
- No downstream service is invoked if validation must occur beforehand.

This is a vital part of negative testing. Verifying that the API returned `400` while the database still persisted corrupt data is insufficient.

### 12.4. Test Parsing Errors and Validation Errors Separately

Malformed JSON differs from syntactically valid JSON with invalid values:

```json
{"quantity":
```

versus:

```json
{"quantity": 0}
```

The first is a parse error; the second is a validation error. If the API distinguishes them in its error contract, tests should confirm they are not conflated.

## 13. Testing Data at the Persistence Boundary

### 13.1. Java Validation Does Not Replace Database Constraints

Two concurrent requests can both check "email does not exist yet" and then both insert. When uniqueness is a data invariant, the database needs a unique constraint or an appropriate transaction mechanism.

Integration tests should confirm:

- A valid insert succeeds.
- A duplicate insert is rejected according to contract.
- Concurrent inserts do not produce duplicates.
- Transactions roll back when a constraint fails.

Never mock the repository and conclude the constraint works; run integration tests against the actual database engine or a matching test container.

### 13.2. Verify Precision and Column Lengths

If Java allows wider data than the database schema, failures surface only at persistence time. Align contracts across:

- Column length.
- Numeric precision and scale.
- Nullability.
- Unique constraints.
- Foreign key constraints.
- Check constraints.

Boundary tests should verify that maximum-length/precision values save and round-trip intact, while exceeding limits fails cleanly.

### 13.3. Do Not Rely on Database Defaults

If code relies on database default time zones, collations, or case sensitivity, test behavior can differ between developer machines and production. Configure them explicitly and run integration tests against an engine/version matching production.

## 14. Property-Based Testing and Fuzz Testing

### 14.1. Limitations of Example-Based Testing

JUnit parameterized tests work well for known cases. Yet large input spaces can hide edge cases nobody anticipated.

Property-based testing checks an invariant across many automatically generated inputs. Libraries such as jqwik or similar tools can be added if approved by the project; they are external test dependencies, not part of JDK 17.

### 14.2. Example: Normalization Idempotence Property

For a `normalize` function:

```text
normalize(normalize(x)) == normalize(x)
~~~

This property can be exercised across hundreds of generated strings. If it fails, normalization may be unstable or contain a Unicode edge-case bug.

### 14.3. Example: Range Property

For the `Quantity` constructor:

- Every integer from 1 through 1000 succeeds in constructing an object.
- Every integer below 1 or above 1000 is rejected.
- The stored value always equals the valid input.

This simple property can test random integers or even run exhaustively over a bounded integer subset, though there is no need to loop over billions of values in routine test suites.

### 14.4. Fuzzing Parsing Logic

Fuzz tests can generate:

- Random Unicode strings.
- Malformed JSON.
- Very long strings.
- Control characters.
- Deeply nested structures.
- Huge numbers or scientific-notation exponents.

The goal goes beyond "does not crash". Define expected behavior: safe rejection, no hangs, bounded resource usage, and zero side effects.

### 14.5. Seeds and Reproducibility

Generative tests must log the seed or failing input for reproduction. Without deterministic replay, fuzzing findings are hard to turn into regression tests.

When a failing input is discovered:

1. Save the minimal failing input.
2. Write a deterministic test reproducing it.
3. Fix the root cause.
4. Keep the regression test in the suite.

## 15. Acceptance Criteria

### 15.1. Acceptance Criteria vs. Test Cases

Acceptance criteria describe the conditions a feature must satisfy to be accepted. Test cases are concrete mechanisms to verify those conditions.

Good criteria are:

- Observable.
- Unambiguously pass/fail.
- Tied to business behavior.
- Independent of unnecessary implementation details.
- Inclusive of both valid and invalid inputs where applicable.

### 15.2. Writing in Given–When–Then Format

Example:

~~~text
Given quantity is an integer from 1 through 1000
When the order line is created
Then the line is accepted and preserves the quantity

Given quantity is 0
When the order line is created
Then creation is rejected with OUT_OF_RANGE

Given the request contains an invalid quantity
When the API receives the request
Then no order line is persisted
~~~

Given–When–Then aligns authors, developers, testers, and product owners on the exact expected behavior.

### 15.3. Sample Acceptance Criteria

For order-line creation:

| ID | Acceptance criterion | Evidence |
|---|---|---|
| AC-01 | Valid SKU after normalization is accepted | Unit tests verifying canonical value |
| AC-02 | Null, blank, or invalid-pattern SKU is rejected | Parameterized negative tests |
| AC-03 | Quantity 1 through 1000 is accepted | Boundary tests at 1, 2, 999, 1000 |
| AC-04 | Out-of-range quantity is rejected | Tests at 0, -1, 1001 |
| AC-05 | Unit price is non-negative and matches contract scale | Decimal boundary tests |
| AC-06 | Input collections/arrays cannot mutate object state after creation | Defensive-copy tests |
| AC-07 | Invalid requests return the published error contract | API integration tests |
| AC-08 | Invalid requests persist no data and emit no events | Persistence/message integration tests |
| AC-09 | Valid values at database limits persist and read back accurately | Persistence boundary test |
| AC-10 | Validation is independent of test-runner clock/locale | Fixed `Clock` and locale-specific tests |

### 15.4. Avoid Vague Criteria

Vague:

- "The system handles data well."
- "Do not allow overly long input."
- "Dates must be valid."
- "Errors must be friendly."

More concrete:

- "After normalization, SKU must have 3 to 20 Unicode code points and contain only the defined character set."
- "End date must not precede start date; equal dates are accepted."
- "Requests with invalid quantity return error code `OUT_OF_RANGE` and create no order."
- "Payloads exceeding 1 MiB are rejected before invoking business services."

Include concrete limits in acceptance criteria only after the product/domain has decided them. Test authors should not invent business rules.

## 16. Requirements and Test Traceability Matrix

### 16.1. Why Traceability Matters

When a requirement changes, the team needs to know which tests are affected and which features are impacted. A traceability matrix links:

```text
Requirement
    |
    v
Acceptance Criterion
    |
    v
Test Case
    |
    v
Automated Test / Manual Evidence
    |
    v
Execution Result
~~~

### 16.2. Example Matrix

| Requirement | Acceptance criteria | Test IDs | Test type |
|---|---|---|---|
| SKU normalization | AC-01 | SKU-001..SKU-004 | Unit |
| SKU validation | AC-02 | SKU-005..SKU-012 | Parameterized unit |
| Quantity range | AC-03, AC-04 | QTY-001..QTY-006 | Boundary unit |
| Price precision | AC-05 | PRICE-001..PRICE-008 | Unit |
| Defensive copy | AC-06 | IMM-001..IMM-003 | Unit |
| API error contract | AC-07 | API-VAL-001..API-VAL-005 | Integration |
| No side effects | AC-08 | API-VAL-006, DB-VAL-001 | Integration |
| Database limits | AC-09 | DB-VAL-002..DB-VAL-004 | Persistence |
| Deterministic rules | AC-10 | TIME-001..TIME-004 | Unit |

IDs here illustrate suite organization. Real projects should follow their team's test ID conventions.

### 16.3. Do Not Measure Quality Solely by Test Count

A hundred tests repeating the same happy path can be worth less than ten tests covering boundaries and cross-field rules. Evaluate a suite by asking:

- Does every key rule have tests?
- Are boundaries covered?
- Do negative paths verify zero side effects?
- Are non-JVM constraints covered by integration tests?
- Are tests deterministic and reproducible?
- When a requirement changes, is it obvious which tests need updating?

Code coverage is a supplementary signal; it does not prove acceptance criteria are fully verified.

## 17. Test Suite Completion Criteria

A data test suite can be considered ready for acceptance when:

1. Every business rule has at least one valid test and appropriate invalid tests.
2. Lower and upper boundary values are explicitly tested.
3. Null, absent, blank, and malformed inputs are distinguished per contract.
4. Cross-field invariants have tests.
5. Normalization is verified against concrete outputs and required properties.
6. Mutable inputs cannot alter object state after creation.
7. API errors return status/code/field matching the contract.
8. Negative requests produce no unintended side effects.
9. Database constraints are verified at the integration level where relevant.
10. Time, locale, and time zone are fixed in tests requiring determinism.
11. Tests run stably without depending on execution order or uncontrolled environment data.
12. Acceptance criteria have linked evidence and traceability to tests.

These are planning criteria for a feature, not an excuse to write low-value tests merely to hit a metric.

## 18. Organizing Test Suites and Shared Test Data

### 18.1. Separating Tests by Rule

Example layout:

~~~text
src/test/java/
└── com/acme/order/
    ├── QuantityTest.java
    ├── AccountCodeTest.java
    ├── MoneyTest.java
    ├── DateRangeTest.java
    ├── OrderLineTest.java
    ├── OrderApiValidationTest.java
    └── OrderPersistenceTest.java
~~~

Separating by domain rule or test layer helps maintainers locate the exact tests to update when contracts evolve.

### 18.2. Test Data Builders

When objects have many fields, a test builder supplies valid defaults and lets tests override only the field under inspection:

~~~java
final class OrderLineFixture {
    private String sku = "AB-100";
    private int quantity = 2;
    private BigDecimal unitPrice = new BigDecimal("10.00");

    OrderLineFixture withSku(String value) {
        this.sku = value;
        return this;
    }

    OrderLineFixture withQuantity(int value) {
        this.quantity = value;
        return this;
    }

    OrderLineFixture withUnitPrice(BigDecimal value) {
        this.unitPrice = value;
        return this;
    }

    OrderLine build() {
        return new OrderLine(sku, quantity, unitPrice);
    }
}
~~~

In a test:

~~~java
OrderLine line = new OrderLineFixture()
        .withQuantity(1000)
        .build();
~~~

Fixtures must have valid defaults. If a default accidentally violates a new rule, many unrelated tests can break. Keep builders simple and avoid hiding complex business logic inside fixtures.

### 18.3. Avoid Shared Mutable Test Data

Never share a mutable `List` or `Map` across tests if any test might modify it. Create fresh fixtures per test or use immutable collections. Isolated tests flake far less when run in parallel.

### 18.4. Keep Real Data Out of Test Data

Use synthetic, deterministic, non-sensitive test data. Never copy real customer records, tokens, emails, or production payloads into test fixtures or logs. When realistic data is needed, generate synthetic data sharing the same technical properties.

## 19. Diagnosing Failing Tests

### 19.1. Distinguishing Code Bugs from Test Bugs

When a boundary test fails:

1. Inspect the exact expected/actual values and input.
2. Check whether the contract changed.
3. Verify the test uses the correct measurement unit (bytes, code points, scale, time zone).
4. Check whether normalization runs before or after validation per the contract.
5. Check whether the test depends on host locale, time, or default time zone.
6. Check whether shared state was mutated by another test.

Never tweak expected values just to make a test pass without confirming the requirement.

### 19.2. Flaky Tests

Common causes:

- Reading system time directly.
- Using unseeded random inputs.
- Depending on test execution order.
- Sharing files, databases, or resources across tests.
- Running parallel tests that mutate global state.
- Depending on host locale, time zone, or environment settings.

Fix flakiness with fixed clocks, recorded seeds, isolated fixtures, proper cleanup, and explicit environment configuration.

### 19.3. Failures Appearing Only at the Database or API Layer

If unit tests pass while integration tests fail:

- Compare validation across DTO, domain, and database layers.
- Check column precision/length and collation.
- Inspect transactions and constraints.
- Check JSON deserialization and absent/null semantics.
- Check encoding and time zones.

Never add workarounds inside a domain constructor just to silence a database failure when the real cause is schema or mapping mismatch.

## 20. Complete Example: Acceptance Criteria and Tests for OrderLine

### 20.1. Domain Contract

~~~java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Objects;

public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice
) {
    public OrderLine {
        sku = normalizeSku(sku);

        if (quantity < 1 || quantity > 1000) {
            throw new IllegalArgumentException(
                    "quantity must be between 1 and 1000"
            );
        }

        unitPrice = Objects.requireNonNull(
                unitPrice,
                "unitPrice must not be null"
        );

        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                    "unitPrice must not be negative"
            );
        }

        if (unitPrice.scale() > 2) {
            throw new IllegalArgumentException(
                    "unitPrice must have at most two decimal places"
            );
        }
    }

    private static String normalizeSku(String rawSku) {
        Objects.requireNonNull(rawSku, "sku must not be null");
        String value = rawSku.strip().toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z0-9-]{3,20}")) {
            throw new IllegalArgumentException("sku has invalid format");
        }
        return value;
    }

    public BigDecimal lineTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

This example fixes a maximum scale of 2 without rounding. In a real domain, that decision comes from currency rules and the business contract.

### 20.2. Acceptance Criteria

~~~text
AC-01: A valid SKU is trimmed and uppercased using locale-independent rules.
AC-02: Null, blank, malformed, too-short and too-long SKUs are rejected.
AC-03: Quantity 1 and 1000 are accepted.
AC-04: Quantity 0, negative and greater than 1000 are rejected.
AC-05: Unit price is required and cannot be negative.
AC-06: Unit price with scale greater than 2 is rejected.
AC-07: Line total equals unit price multiplied by quantity.
AC-08: Invalid input does not create or persist an order line.
~~~

### 20.3. Boundary and Invalid Data Tests

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class OrderLineTest {

    @Test
    void normalizesSku() {
        OrderLine line = new OrderLine(
                " ab-100 ",
                1,
                new BigDecimal("10.00")
        );

        assertEquals("AB-100", line.sku());
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 2, 999, 1000})
    void acceptsQuantityInsideAndAtBounds(int quantity) {
        OrderLine line = new OrderLine(
                "AB-100",
                quantity,
                new BigDecimal("10.00")
        );

        assertEquals(quantity, line.quantity());
    }

    @ParameterizedTest
    @ValueSource(ints = {-1, 0, 1001, 5000})
    void rejectsQuantityOutsideBounds(int quantity) {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderLine(
                        "AB-100",
                        quantity,
                        new BigDecimal("10.00")
                )
        );
    }

    @ParameterizedTest
    @ValueSource(strings = {"", " ", "AB", "AB_100", "AB 100"})
    void rejectsInvalidSku(String sku) {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderLine(
                        sku,
                        1,
                        new BigDecimal("10.00")
                )
        );
    }

    @Test
    void rejectsNullSku() {
        assertThrows(
                NullPointerException.class,
                () -> new OrderLine(
                        null,
                        1,
                        new BigDecimal("10.00")
                )
        );
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderLine(
                        "AB-100",
                        1,
                        new BigDecimal("-0.01")
                )
        );
    }

    @Test
    void rejectsPriceWithTooManyFractionDigits() {
        assertThrows(
                IllegalArgumentException.class,
                () -> new OrderLine(
                        "AB-100",
                        1,
                        new BigDecimal("10.001")
                )
        );
    }

    @Test
    void calculatesLineTotal() {
        OrderLine line = new OrderLine(
                "AB-100",
                3,
                new BigDecimal("10.25")
        );

        assertEquals(
                new BigDecimal("30.75"),
                line.lineTotal()
        );
    }
}
~~~

### 20.4. Verifying Example Consistency

Under the contract above:

- `" ab-100 "` is stripped and uppercased to `"AB-100"`.
- `"AB"` is rejected as too short.
- `"AB_100"` is rejected because underscore is outside the pattern.
- Quantities 1 and 1000 are accepted.
- Quantities 0 and 1001 are rejected.
- Negative values are rejected.
- Scale 3 is rejected without rounding.

When the contract changes, update acceptance criteria and corresponding tests together.

## 21. Practice Exercises

### Exercise 1 — Building Equivalence Partitions

Pick a field such as `username`, `quantity`, or `discount`. List valid and invalid partitions and select at least one representative value per partition. Explain why values within a partition share equivalent behavior.

### Exercise 2 — Building a Boundary Matrix

For a range from 5 through 50, write tests for 4, 5, 6, 49, 50, and 51. Add one mid-range value. Document expected results clearly.

### Exercise 3 — Distinguishing Absent/Null/Blank

Design a profile-update API. Define the semantics of an omitted field, `null`, empty string, and whitespace-only string. Write tests for each case.

### Exercise 4 — Testing Unicode

Construct canonically equivalent NFC/NFD inputs, inputs with non-BMP code points, and inputs with combining marks. Decide whether length limits count code units or code points, then write tests.

### Exercise 5 — Testing Money

Create a `Money` value object with currency and `BigDecimal`. Specify scale, rounding, and range rules. Write tests for zero, negative, maximum bound, maximum scale, and excessive scale.

### Exercise 6 — Cross-Field Invariants

Create `DateRange` and `DiscountPolicy`. Write decision tables for input combinations, including `end` before `start` and `discount` greater than `subtotal`.

### Exercise 7 — Testing Defensive Copying

Create a class accepting a `List` and a byte array. Mutate inputs after construction and mutate values returned from accessors. Assert the object's state does not change.

### Exercise 8 — Parameterized Tests

Convert the `quantity` and `SKU` test suites to `@ParameterizedTest`, `@ValueSource`, `@CsvSource`, or `@MethodSource`. Name tests to clearly indicate the data partition.

### Exercise 9 — Fixed Clock

Write an expiration policy accepting `Clock`. Test before, equal to, and after expiry using `Clock.fixed`. Never rely on the real clock in assertions.

### Exercise 10 — API Negative Tests

Send requests with bad format, missing fields, and out-of-range values. Assert status, error code, and field, and verify zero database writes or emitted events.

### Exercise 11 — Acceptance Criteria

Write at least five Given–When–Then acceptance criteria for a resource-creation feature. Link each criterion to test IDs and observable evidence.

### Exercise 12 — Regressions from Fuzz Inputs

Generate unusual Unicode or JSON strings. Whenever a failing input is found, save it as a deterministic test to prevent regressions.

## 22. Self-Check Questions

1. How does equivalence partitioning reduce test count?
2. Which points should boundary-value analysis test for a closed interval?
3. Why is testing exact min/max more valuable than testing only a mid-range value?
4. How do `null`, absent, and blank differ in APIs?
5. How do syntax/format errors differ from semantic errors?
6. When is cross-field validation needed?
7. Why must negative tests verify the absence of side effects?
8. What kinds of test inputs fit `@ParameterizedTest` well?
9. When should `@MethodSource` be used instead of `@ValueSource`?
10. What does `assertThrows` verify?
11. When should you assert on exception messages vs. error codes?
12. Why should expiration tests avoid using the real system clock?
13. What are the limitations of pairwise testing?
14. How does property-based testing differ from example-based testing?
15. Why must fuzz tests record seeds or failing inputs for replay?
16. How do acceptance criteria differ from test cases?
17. How does a traceability matrix help when requirements change?
18. Why does high code coverage not guarantee adequate boundary coverage?
19. Why are database unique constraints still needed even when Java checks beforehand?
20. How do you prevent a test suite from depending on locale, time zone, and execution order?

## 23. References

- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): Jupiter, parameterized tests, assertions, and test lifecycle.
- [JUnit 5 API — Assertions](https://junit.org/junit5/docs/current/api/org.junit.jupiter.api/org/junit/jupiter/api/Assertions.html): `assertThrows`, `assertAll`, `assertDoesNotThrow`, and assertion APIs.
- [JUnit 5 API — ParameterizedTest](https://junit.org/junit5/docs/current/api/org.junit.jupiter.params/org/junit/jupiter/params/ParameterizedTest.html): declaring parameterized tests.
- [Java SE 17 API — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): fixable clocks for deterministic testing.
- [Java SE 17 API — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): length, code points, and string operations.
- [Java SE 17 API — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): Unicode normalization.
- [Java SE 17 API — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): scale, precision, `compareTo`, and decimal arithmetic.
- [ISTQB Glossary](https://glossary.istqb.org/): testing terminology such as equivalence partitioning, boundary value analysis, and acceptance testing.

A valuable boundary test suite starts from a clear contract. Partition inputs into equivalence classes, test immediately below, at, and above boundaries, add negative cases for `null`, blank, format, and cross-field rules, and verify both outputs and side effects. Use JUnit 5 to structure repeatable tests, fix time and locale when needed, and link every acceptance criterion to concrete evidence. In doing so, your test suite proves application behavior for both valid and invalid data on Java 17.
