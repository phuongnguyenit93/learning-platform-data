# Comparing Collections, Ordering, Duplicates, and Empty Sets in Spring Boot Testing

## 1. Goal: assertions must reflect the collection's true contract

Spring Boot applications frequently return lists of orders, sets of roles, search results, configuration maps, or grouped data from services, repositories, and APIs. Two collections containing some of the same values **do not necessarily share the same meaning**: ordering might matter, elements might be allowed to repeat, and an empty result can mean something completely different from `null`.

When testing, decide four things clearly before writing an assertion:

1. **Structure type:** `List`, `Set`, `Map`, array, or a custom `Iterable`?
2. **Ordering:** must the result preserve exact positions/sequence, or may it come back in any order?
3. **Duplicates:** is the occurrence count of each element part of the contract?
4. **Empty vs. null:** when there are no results, does the contract return an empty collection, `Optional.empty()`, or `null`?

An overly loose assertion can pass even when the system returns extra or missing items. An overly tight assertion can fail when an unguaranteed order validly changes. The goal is to check **the exact properties that need protection**, without forcing every collection into one comparison style.

## 2. Understanding how Java compares List, Set, Map, and Iterable

| Data type | Does `equals` consider order? | Represents duplicates? | Assertion implications |
|---|---|---|---|
| `List` | **Yes**: same size, each element equal at the same index | **Yes** | `assertEquals(expectedList, actualList)` checks both ordering and occurrence counts |
| `Set` | **No**: same set of elements | **No**: duplicates are deduplicated on insertion | `assertEquals(expectedSet, actualSet)` fits when ordering and repetition are not in the contract |
| `Map` | **No**: compares key–value pairs | Keys are unique; values may repeat | `assertEquals(expectedMap, actualMap)` checks mappings, not iteration order |
| Arbitrary `Iterable` | No universal `equals` rule across implementations | Implementation-dependent | `assertIterableEquals` compares **iteration sequence**, but verify that sequence is actually guaranteed |
| Java array | `Object.equals` on arrays typically checks reference identity | Yes | Use `assertArrayEquals` for arrays; do not confuse with `List.equals` |

Example:

```java
List<String> a = List.of("A", "B", "A");
List<String> b = List.of("A", "A", "B");
boolean sameList = a.equals(b); // false: different positions

Set<String> x = Set.of("A", "B");
Set<String> y = Set.of("B", "A");
boolean sameSet = x.equals(y);  // true: same elements
```

`List.equals`, `Set.equals`, and `Map.equals` rely on `equals` of elements, keys, and values. For a custom DTO without data-based equality rules, `assertEquals(List<Dto>, List<Dto>)` can fail even when displayed fields look identical. Where appropriate, Java `record` automatically provides component-based `equals`; for regular classes, consider `equals/hashCode` or assertions that extract contract fields.

**Never treat the iteration order of `HashSet` or `HashMap` as a contract.** They do not guarantee insertion order or sorted order. `LinkedHashSet` and `LinkedHashMap` have defined iteration orders, yet `Set.equals` and `Map.equals` still ignore that order.

## 3. Choosing assertions based on ordering and occurrence counts

| Actual contract | Suitable verification | Example |
|---|---|---|
| Order **matters**, duplicates **matter** | JUnit `assertEquals(List, List)`, `assertIterableEquals`; AssertJ `containsExactly` | `["A", "B", "A"]` matches only that exact sequence |
| Order **does not matter**, duplicates **matter** | AssertJ `containsExactlyInAnyOrder` | `["A", "B", "A"]` matches `["B", "A", "A"]`, but not `["A", "B"]` |
| Order **does not matter**, duplicates **irrelevant** | `Set.equals`, or set membership checks | `{"A", "B"}` equals `{"B", "A"}` |
| Order **matters**, elements **must be unique** | Assert list order **and** uniqueness | Permissions sorted by priority without duplicate entries |
| No results, returns empty collection | `assertNotNull` + `assertTrue(isEmpty())`, AssertJ `isEmpty()` | `[]` is valid whereas `null` violates the contract |

Each check serves a different role:

- `assertEquals(expected, actual)` on `List`: verifies size, positions, and duplicates via `List.equals`.
- JUnit Jupiter's `assertIterableEquals(expected, actual)`: compares elements in iteration order; appropriate for a deterministic sequence, **not** a tool for ignoring order.
- AssertJ's `assertThat(actual).containsExactly(...)`: verifies all elements in exact order with nothing missing or extra.
- `assertThat(actual).containsExactlyInAnyOrder(...)`: compares all elements ignoring order **while still checking duplicate counts**.
- `assertThat(actual).containsOnly(...)`: verifies only allowed/present values, **not suitable for confirming exact duplicate counts** because it ignores duplicate multiplicity differences.
- `assertThat(actual).contains(...)`: verifies the listed elements are present, without guaranteeing the collection contains nothing else.

A very common test bug is calling `actual.containsAll(expected)` to conclude two lists are equivalent. That only asks whether each value in `expected` appears at least once in `actual`; it checks **neither order, duplicate counts, nor extra elements**.

## 4. Java 17+ example with JUnit Jupiter and AssertJ

The following example can be placed in a Spring Boot project using Java 17+ and the `spring-boot-starter-test` dependency (which provides JUnit Jupiter and AssertJ in standard starter test configurations). This is a plain Java test and needs no Spring context.

File: `src/test/java/com/example/testing/CollectionAssertionsTest.java`

```java
package com.example.testing;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertIterableEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CollectionAssertionsTest {

    @Test
    void listComparisonChecksOrderAndDuplicates() {
        List<String> actual = List.of("A", "B", "A");
        List<String> expected = List.of("A", "B", "A");

        assertEquals(expected, actual);
        assertIterableEquals(expected, actual);
        assertThat(actual).containsExactly("A", "B", "A");

        assertNotEquals(expected, List.of("A", "A", "B"));
        assertNotEquals(expected, List.of("A", "B"));
    }

    @Test
    void compareWithoutOrderButKeepDuplicateCounts() {
        List<String> actual = List.of("B", "A", "A");

        assertThat(actual).containsExactlyInAnyOrder("A", "A", "B");
        assertThat(actual).containsOnly("A", "B");
        // containsOnly does not verify that A appears exactly twice.
    }

    @Test
    void setEqualityIgnoresIterationOrderAndRemovesDuplicates() {
        Set<String> actual =
                new LinkedHashSet<>(List.of("B", "A", "B"));

        assertEquals(Set.of("A", "B"), actual);
        assertEquals(2, actual.size());
        assertTrue(actual.contains("A"));
        assertFalse(actual.contains("C"));
    }

    @Test
    void emptyAndNullHaveDifferentMeanings() {
        List<String> actual = new ArrayList<>();

        assertNotNull(actual);
        assertTrue(actual.isEmpty());
        assertThat(actual).isEmpty();
        assertEquals(List.of(), actual);
    }

    @Test
    void mapEqualityChecksKeysAndValuesNotInsertionOrder() {
        Map<String, Integer> actual = new LinkedHashMap<>();
        actual.put("second", 2);
        actual.put("first", 1);

        Map<String, Integer> expected =
                Map.of("first", 1, "second", 2);

        assertEquals(expected, actual);
        assertThat(actual)
                .hasSize(2)
                .containsEntry("first", 1)
                .containsEntry("second", 2);
    }

    @Test
    void anOrderedUniqueListNeedsTwoAssertions() {
        List<String> actual = List.of("admin", "editor", "viewer");

        assertThat(actual).containsExactly("admin", "editor", "viewer");
        assertEquals(actual.size(), new HashSet<>(actual).size());
    }
}
```

With these values and compatible library versions, **all six tests pass**. They print nothing to stdout; Maven/Gradle reports test results according to your runner and project configuration. Passing here does not prove a real application API or repository ran, because these fixtures construct collections directly in the test.

Run with Gradle wrapper (Linux/macOS):

```bash
./gradlew test --tests "com.example.testing.CollectionAssertionsTest"
```

On Windows PowerShell use `.\gradlew.bat test --tests "com.example.testing.CollectionAssertionsTest"`.

With Maven wrapper:

```bash
./mvnw -Dtest=CollectionAssertionsTest test
```

On Windows PowerShell use `.\mvnw.cmd -Dtest=CollectionAssertionsTest test`. These commands assume the project already configures JUnit Platform/Surefire properly; selected test execution details should be verified in the actual run report.

### An anti-pattern: green test that misses missing data

```java
List<String> expected = List.of("A", "A", "B");
List<String> actual = List.of("A", "B");

boolean misleading = actual.containsAll(expected); // true!
```

Reason: both `"A"` and `"B"` are present in `actual`; `containsAll` does not require **two occurrences of `"A"`**. If the business needs duplicates preserved, use `containsExactlyInAnyOrder("A", "A", "B")` or compare suitably sorted lists without losing occurrence counts.

Another anti-pattern:

```java
List<String> actual = List.of("A", "A", "B");
Set<String> normalized = new HashSet<>(actual);

boolean missingEvidence =
        normalized.equals(Set.of("A", "B")); // true
```

Converting `List` to `Set` discards the fact that there were **two `"A"`s**. Do not "normalize" like this when duplicates are meaningful data.

## 5. Checking order when the contract actually requires order

List ordering matters when an API promises sorting by timestamp, score, priority, or when a sequence of events must occur in order.

For example, `GET /orders?sort=createdAt,desc` promises newest orders first. With output mapped to IDs in order:

```java
List<Long> actualIds = List.of(103L, 102L, 101L);
assertThat(actualIds).containsExactly(103L, 102L, 101L);
```

For integration/repository tests, create data with distinct timestamps, add a tie-breaker criterion if timestamps can collide, and require the query to sort (`ORDER BY`, `Sort`, `Pageable`) per the contract. Do not use an arbitrary database order as the expected value.

If the contract only says "return matching orders" without promising an order, `containsExactly` can cause tests to fail unreasonably when the system still returns the right set. In that case, use `containsExactlyInAnyOrder` when occurrence counts matter, or compare sets of IDs when IDs must be unique and order does not matter.

**Warning:** `assertIterableEquals` on two `HashSet`s easily creates assertions depending on unguaranteed iteration order. To compare two `Set`s by content, use `assertEquals(expectedSet, actualSet)` or an appropriate set assertion.

## 6. Clarifying the contract for duplicate elements

A collection containing duplicates is not automatically buggy:
- A cart might hold multiple line items for the same SKU if the business records each add-item event separately.
- An event log might contain the same event name twice.
- A bad `JOIN` query might accidentally duplicate rows in a returned list.
- A list of roles or tags *might* require every value to appear at most once.

When output permits duplicates without guaranteeing order, **occurrence counts are part of the contract**. AssertJ's `containsExactlyInAnyOrder` checks exact element multiplicity, so:

```java
List<String> actual = List.of("item-2", "item-1", "item-1");

assertThat(actual)
        .containsExactlyInAnyOrder("item-1", "item-1", "item-2");
```

Dropping one `"item-1"` or adding an extra `"item-2"` makes the assertion fail.

`containsOnly("item-1", "item-2")` is only suitable when repetition counts **do not need verification**. With `Set`, duplicates are always collapsed by `Set` equality rules; you cannot use set equality to detect a query emitting duplicate rows before being converted into a `Set`.

If the contract requires each value to appear only once, assert that explicitly, for example:

```java
List<String> actual = List.of("READ", "WRITE");
assertEquals(actual.size(), new HashSet<>(actual).size());
```

For lists of objects, uniqueness may be defined by a **business key** (such as `orderId`), not necessarily whole-object `equals`. In that case extract the key and compare the unique key count or frequency per key. Pick the definition of "duplicate" that matches the domain.

## 7. Distinguishing empty sets, null, missing keys, and filtered-out results

An empty list `[]` typically means "request processed, no matching elements found"; `null` can mean "value absent" or a contract violation. They are **not synonymous**.

```java
List<String> emptyResult = List.of();

assertNotNull(emptyResult);
assertTrue(emptyResult.isEmpty());
assertThat(emptyResult).isEmpty();
assertEquals(List.of(), emptyResult);
```

If a value may legally be `null` per the contract, assert `assertNull(actual)` explicitly; do not call `actual.isEmpty()` when it could be null because that throws `NullPointerException`. With `Optional<List<T>>`, distinguish `Optional.empty()` from `Optional.of(List.of())` when the domain gives them different meanings.

For `Map`, **a missing key** differs from **a present key mapped to null** in implementations allowing null values such as `HashMap`. `map.get(key) == null` is not enough to distinguish them; use `containsKey(key)` when the contract cares about key presence.

For Spring Boot APIs:
- No search matches may return HTTP 200 and `[]`, if that is the API contract.
- A single missing resource may require HTTP 404; that is a different case from an empty list.
- HTTP 204 has no response body; do not try to parse `[]` from the body when the contract specifies no content.
- When using `MockMvc` or HTTP tests, check status, JSON shape, and content together. Asserting on a deserialized Java collection **does not automatically prove** the raw status and JSON shape are right.

Do not invent one uniform convention for every endpoint; take expected behavior from each concrete contract and write matching assertions.

## 8. When elements are objects/DTOs: `equals` can make tests wrong or brittle

Suppose a service returns `List<OrderDto>`. `List.equals` compares elements via `equals`, so if `OrderDto` is a regular Java class that does not override `equals`, two objects with identical field values can still be unequal by reference identity.

A simple option for DTOs that do not require mutable behavior is a `record`:

```java
record OrderSummary(long id, String status) {}

List<OrderSummary> expected = List.of(
        new OrderSummary(1L, "PAID"),
        new OrderSummary(2L, "PENDING")
);
List<OrderSummary> actual = List.of(
        new OrderSummary(1L, "PAID"),
        new OrderSummary(2L, "PENDING")
);

assertEquals(expected, actual); // true: record compares components
```

This is an **illustrative code snippet placed inside a class or method with `java.util.List` and `assertEquals` imported**; it is not a standalone Java file like the full test example in section 4.

If the contract only cares about `id` and `status` and not internal metadata, extract just those public fields or use AssertJ `extracting`. Avoid asserting `toString()`, manually serializing to JSON strings (which can depend on property order), or checking reference identity when the goal is value comparison.

If the elements themselves are arrays, `List<byte[]>.equals` compares array references rather than deep byte contents. When array contents are what need protection, use `assertArrayEquals` on arrays or wrap the data in a type with proper value equality.

## 9. Comparing Maps: order does not matter, every key and value does

`Map.equals` verifies that two maps have the same number of entries and each key maps to an equal value. Insertion order into a `LinkedHashMap` does not make them unequal under `equals`.

```java
Map<String, Integer> expected = Map.of("OPEN", 2, "CLOSED", 1);

Map<String, Integer> actual = new LinkedHashMap<>();
actual.put("CLOSED", 1);
actual.put("OPEN", 2);

assertEquals(expected, actual);
assertThat(actual).containsEntry("OPEN", 2);
```

This is an illustrative snippet assuming `Map`, `LinkedHashMap`, and assertions are imported. If a test only checks `containsEntry("OPEN", 2)`, it does not prove the map **has no extra entries**; use `assertEquals(expected, actual)` or full-map assertions when the contract requires an exact match.

A `Map` cannot hold two entries with the same key at the same time: calling `put` again with the same key **overwrites** the previous value. Therefore, if bugs involve duplicate-key rows before grouping, verify the data before the map-grouping step or use a structure that preserves multiplicity.

## 10. Real-world Spring Boot scenarios: choosing test level and assertions

| Scenario | Contract to prove | Core assertion |
|---|---|---|
| `GET /orders` sorted newest first | Right ID order, none missing or extra | List of IDs `containsExactly(...)` |
| Repository `findByStatus` without guaranteed sort | Same orders, independent of order | `containsExactlyInAnyOrder(...)` if counts matter |
| Order ID list must be unique | No duplicate IDs | List size equals unique ID set size, plus expected content |
| Event list allowing duplicates | Exact occurrence count per event | `containsExactlyInAnyOrder(...)` |
| User's set of permissions | Exact permissions, order irrelevant | `assertEquals(expectedSet, actualSet)` |
| No orders found in search results | Returns empty list per contract | `assertNotNull` and `isEmpty()` |
| Counts aggregated by status | Each key maps to right count, no extra entries | `Map.equals` |
| JSON API must return ordered array | HTTP status and JSON array positions | MockMvc/JSONPath index assertions or deserialize then `containsExactly` |
| No elements in API response | HTTP status/shape per contract | Check status and `[]` body vs. empty body per spec |

**Note on databases and collection order:** if a JPA/SQL query has no ordering clause, record order is not guaranteed. Never write a test expecting an order "incidentally observed" on H2 or PostgreSQL. If the product requires ordering, put sorting into the query/`Sort` and assert it. Otherwise, use order-independent assertions that still verify exact count and elements.

**Note on `@SpringBootTest`:** booting a Spring context does not change collection equality rules. Use integration tests only when verifying mapping, repositories, databases, or HTTP contracts. For pure Java collection logic, a standard JUnit unit test is usually faster and clearer.

## 11. Common assertion mistakes

| Mistake | Why it is wrong | How to fix |
|---|---|---|
| Comparing `List` with `containsAll` | Ignores order, extra elements, and duplicate counts | `assertEquals`, `containsExactly`, or `containsExactlyInAnyOrder` per contract |
| Converting a list to a set before comparing when duplicates matter | Loses occurrence counts | Keep as list and check multiplicity |
| `assertIterableEquals` on a `HashSet` | Iteration order is unstable / not in contract | Compare set contents via `assertEquals` |
| Using `containsOnly` to confirm each element appears once | Does not check repeat counts | Use `containsExactlyInAnyOrder` or explicit count checks |
| Only `contains("A")` when output must have a single element | Misses extra elements | `containsExactly("A")` |
| Asserting empty list when code returns `null` | `null` is not empty | Assert non-null and `isEmpty`; or `assertNull` if required |
| Comparing `List<DTO>` when DTO lacks data equality | Compares references instead of values | Use records, proper `equals`, or extract fields to assert |
| Comparing maps via `toString()` order | `Map` usually does not promise iteration order | Compare entries via `Map.equals` |
| Assuming `Set.of("A", "A")` creates a single-element set | `Set.of` rejects duplicates with `IllegalArgumentException` | Supply unique elements, or use appropriate construction if testing deduplication |
| Asserting only size | Same size can still have wrong elements or order | Verify full contents per contract |

## 12. Checklist before finalizing a collection test

- [ ] Identified whether the result is a `List`, `Set`, `Map`, array, or custom `Iterable`.
- [ ] Confirmed whether ordering belongs to the contract or is just incidental.
- [ ] Confirmed whether duplicates are meaningful and whether occurrence counts must be exact.
- [ ] Assertions verify all elements; neither missing nor extra elements can slip through.
- [ ] If uniqueness is required, verified uniqueness by the right business key.
- [ ] Distinguished `null`, empty collection, absent map keys, and empty HTTP bodies per requirements.
- [ ] For objects/DTOs, equality is based on data worth protecting rather than incidental reference identity.
- [ ] For repositories/APIs, separated explicit sorting requirements from unguaranteed ordering.
- [ ] Test is deterministic across machines and CI; does not depend on hash collection iteration order.
- [ ] Ran the right tests and inspected the report before claiming pass on real application code.

**Conclusion:** When comparing collections in Spring Boot, clarify **whether order matters**, **whether occurrence counts matter**, and **how empty differs from null**. `List.equals` and `containsExactly` fit exact ordering; `containsExactlyInAnyOrder` preserves occurrence counts while ignoring order; `Set.equals` and `Map.equals` fit when order is not part of the contract. Good assertions catch missing, extra, and misstructured results matching real business rules.