# Testing Ordering, Extreme Elements, and `Optional` Results

> **Chapter:** Debugging and Testing Pipelines  
> **Module:** `JAVA_STREAM_API` — learning declarative data processing with the Java Stream API through lazy pipelines, `filter`, `map`, `reduce`, and `collect`; practicing grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers while recognizing state, resource, and performance limits.

A Stream pipeline can return **the right element count in the wrong order**, find **the highest score while picking the wrong record on a tie**, or pass on populated inputs yet throw an exception when the result is `Optional.empty()`. Therefore, testing Java Streams goes beyond checking a printed list; it must verify the **committed semantics** of each operation.

This lesson focuses on three testing areas: **encounter order**, **extreme elements `min`/`max`**, and **potentially absent `Optional` results**. We will build a dataset with tied scores and filtered-out records, write assertions independent of thread scheduling, and compare sequential and parallel Streams.

All standalone code in this lesson uses **Java 17 or higher**. No preview features or external libraries beyond the JDK are needed.

## 1. Define the Test Contract Before Writing Code

Suppose the system manages evaluation tickets with:

| Ticket ID | Score | Active? | Role |
| --- | ---: | --- | --- |
| `T-01` | 80 | Yes | First ticket in the source list. |
| `T-02` | 95 | Yes | Tied for highest score with `T-03`. |
| `T-03` | 95 | Yes | Used to test tie-breaking. |
| `T-04` | 65 | Yes | Tied for lowest active score with `T-06`. |
| `T-05` | 40 | No | Must be excluded before finding extremes. |
| `T-06` | 65 | Yes | Used to test tie-breaking at the low score. |

Report rules:

1. Process only records with `active == true`.
2. Ticket list preserves **source appearance order** when the pipeline only uses `filter` and `map`.
3. Ranking list is ordered by **score descending, ticket ID ascending**; tied scores must produce a deterministic result.
4. **Lowest-scoring** ticket: score ascending, breaking ties by ID ascending.
5. **Highest-scoring** ticket: score descending, breaking ties by ID ascending.
6. If no tickets remain after filtering, `findFirst`, `findAny`, `min`, and `max` all return `Optional.empty()`, never synthesizing a fake object.

For the table above, expected results are:

```text
Active tickets order: [T-01, T-02, T-03, T-04, T-06]
Ranking (score DESC, id ASC): [T-02, T-03, T-01, T-04, T-06]
findFirst: T-01
Lowest-scoring ticket:  T-04 (65)
Highest-scoring ticket: T-02 (95)
Min / max score: 65 / 95
```

**Do not apply a single test criterion to every operation.** A `findAny` result may be **any** active ticket, whereas `findFirst` must be `T-01` on an ordered `List` source. That difference is part of the API contract, not a bug.

## 2. Testing Order: `filter`, `map`, `toList`

With a `List`, a Stream has an **encounter order** matching the list's element order. Standard `filter` and `map` operations do not alter the relative order of remaining elements.

```java
import java.util.List;

record Ticket(String id, int score, boolean active) {}

List<Ticket> tickets = List.of(
        new Ticket("T-01", 80, true),
        new Ticket("T-02", 95, true),
        new Ticket("T-03", 95, true),
        new Ticket("T-04", 65, true),
        new Ticket("T-05", 40, false),
        new Ticket("T-06", 65, true)
);

List<String> activeIds = tickets.stream()
        .filter(Ticket::active)
        .map(Ticket::id)
        .toList();

System.out.println(activeIds);
// [T-01, T-02, T-03, T-04, T-06]
```

Testing **order** should compare the full list:

```java
List<String> expected = List.of(
        "T-01", "T-02", "T-03", "T-04", "T-06");

if (!activeIds.equals(expected)) {
    throw new AssertionError("Wrong element order");
}
```

Checking only `activeIds.size() == 5` is insufficient: a pipeline that accidentally calls `sorted()` would also return five elements while violating the input-order requirement.

### Element order differs from callback invocation order

Example:

```java
List<String> parallelIds = tickets.parallelStream()
        .filter(Ticket::active)
        .map(Ticket::id)
        .toList();

System.out.println(parallelIds);
// [T-01, T-02, T-03, T-04, T-06]
```

With an ordered `List` source and a pipeline that preserves encounter order, `Stream.toList()` preserves the output order, even in parallel mode. This does **not** mean `map` calls for individual elements execute in that exact order or on the same thread.

Avoid placing mandatory side effects inside `map`, `filter`, or `peek` and testing via log order: pipelines can optimize away intermediate steps or short-circuit. Assert **output values**, never scheduling traces.

## 3. `findFirst` and `findAny`: Testing Two Different Contracts

`findFirst()` returns the first element **in encounter order** if the source is ordered. `findAny()` is allowed to return **any matching element**, giving the runtime freedom to optimize, especially in parallel.

```java
import java.util.Optional;

Optional<Ticket> first = tickets.stream()
        .filter(Ticket::active)
        .findFirst();

Optional<Ticket> any = tickets.parallelStream()
        .filter(Ticket::active)
        .findAny();

System.out.println(first.map(Ticket::id).orElse("NONE")); // T-01
// No guarantee that any is T-01 or any specific ID.
```

Proper test assertions:

```java
// findFirst has a specific expected value because the List source is ordered.
check(first.isPresent(), "Must have an active ticket");
check(first.orElseThrow().id().equals("T-01"), "Wrong findFirst");

// findAny only needs to be some element satisfying the predicate.
check(any.isPresent(), "findAny must not be empty on this source");
check(any.orElseThrow().active(), "findAny returned inactive ticket");
check(activeIds.contains(any.orElseThrow().id()),
        "findAny returned a ticket outside the matching set");
```

`check(...)` is a helper method defined in the complete program in Section 7; the snippet above illustrates how to phrase assertions.

**Do not write** `check(any.orElseThrow().id().equals("T-01"))`: that turns a common implementation coincidence into a strict requirement, creating flaky tests or breaking the spec.

If the source is marked `unordered()` or inherently lacks an encounter order, `findFirst` cannot guarantee the "first" element under application ordering rules. When you genuinely need "earliest by timestamp," **sort by timestamp plus a tie-breaker** or use a source with a defined order.

## 4. Testing `min` and `max` with Tied Scores

`Stream.min(comparator)` and `Stream.max(comparator)` return `Optional<T>`. When **multiple elements compare equal under the comparator**, checking only the score does not prove the right record was chosen according to business rules.

Suppose you compare by score alone:

```java
import java.util.Comparator;

Comparator<Ticket> byScore = Comparator.comparingInt(Ticket::score);

Optional<Ticket> highestScore = tickets.stream()
        .filter(Ticket::active)
        .max(byScore);

check(highestScore.isPresent(), "No highest score found");
check(highestScore.orElseThrow().score() == 95, "Wrong max score");
```

Here `T-02` and `T-03` both have score 95. If the comparator inspects only score, the two tickets **compare equal**, so getting one specific ID cannot be treated as a contract that holds across splitting strategies or input reorderings.

### Specify an explicit tie-breaker

For **lowest score** with ascending ID on ties:

```java
Comparator<Ticket> minOrder = Comparator
        .comparingInt(Ticket::score)
        .thenComparing(Ticket::id);

Ticket lowest = tickets.stream()
        .filter(Ticket::active)
        .min(minOrder)
        .orElseThrow();

System.out.println(lowest.id()); // T-04
```

For **highest score** when you also want ascending ID on ties, `max` must prefer **the smaller ID** among equal-scoring tickets. One way to express this is reversing the secondary comparator:

```java
Comparator<Ticket> maxOrder = Comparator
        .comparingInt(Ticket::score)
        .thenComparing(Ticket::id, Comparator.reverseOrder());

Ticket highest = tickets.stream()
        .filter(Ticket::active)
        .max(maxOrder)
        .orElseThrow();

System.out.println(highest.id()); // T-02
```

Reason: `max` picks the element considered "greatest" by the comparator. At score 95, `Comparator.reverseOrder()` makes `"T-02"` compare greater than `"T-03"` for maximum selection.

Do not write `Comparator.comparingInt(Ticket::score).thenComparing(Ticket::id)` and call `max` **expecting the smallest ID**: that comparator selects the **largest** ID when scores tie.

### Using `sorted(...).findFirst()` to follow ranking order directly

Once you have a ranking rule **score descending, ID ascending**, you can write:

```java
Comparator<Ticket> ranking = Comparator
        .comparingInt(Ticket::score)
        .reversed()
        .thenComparing(Ticket::id);

List<String> rankingIds = tickets.stream()
        .filter(Ticket::active)
        .sorted(ranking)
        .map(Ticket::id)
        .toList();

System.out.println(rankingIds);
// [T-02, T-03, T-01, T-04, T-06]
```

`sorted(ranking).findFirst()` selects `T-02`, matching `max(maxOrder)` on this data. However, if you only need **a single extreme element**, `min`/`max` is usually better because it avoids sorting the entire stream like `sorted` does.

## 5. Testing Extremes Must Filter Invalid Data First

Row `T-05` has score 40 but is inactive. Therefore:

```java
int allMin = tickets.stream()
        .mapToInt(Ticket::score)
        .min()
        .orElseThrow();
// 40 — wrong if the problem considers only active tickets.

int activeMin = tickets.stream()
        .filter(Ticket::active)
        .mapToInt(Ticket::score)
        .min()
        .orElseThrow();
// 65 — right per requirement.
```

When testing, include at least **one filtered-out record that would change the result if filtering were forgotten**. If test data has only `active == true`, both the fixed version and a buggy version missing `filter` will pass.

Similarly, test sources containing **two tied extreme values** to catch missing tie-breakers. Tests should be crafted to separate correct code from buggy code, not just produce nice numbers.

## 6. `Optional<T>` and `OptionalInt`: Test the Absent Branch Too

The following operations may yield no result:

| Operation | Result type | When is it empty? |
| --- | --- | --- |
| `stream.findFirst()` | `Optional<T>` | Stream has no elements after filtering. |
| `stream.findAny()` | `Optional<T>` | Stream has no elements. |
| `stream.min(comparator)` | `Optional<T>` | No elements to compare. |
| `stream.max(comparator)` | `Optional<T>` | No elements to compare. |
| `intStream.min()` | `OptionalInt` | No `int` values. |
| `intStream.max()` | `OptionalInt` | No `int` values. |
| `longStream.average()` | `OptionalDouble` | No elements to average. |

Example with non-empty source that becomes **empty after filtering**:

```java
Optional<Ticket> none = tickets.stream()
        .filter(Ticket::active)
        .filter(t -> t.score() > 100)
        .findFirst();

check(none.isEmpty(), "No score > 100 can exist");
```

### `orElse`, `orElseGet`, and `orElseThrow`

```java
String label = none.map(Ticket::id).orElse("(none)");
System.out.println(label); // (none)

Ticket fallback = none.orElseGet(
        () -> new Ticket("NONE", 0, false));
System.out.println(fallback.id()); // NONE
```

`orElse(defaultValue)` eagerly evaluates its argument when called, whereas `orElseGet(supplier)` invokes the supplier only if the `Optional` is empty. That distinction is worth testing when creating the fallback is expensive or has side effects.

When **absence is a business error**, use:

```java
Ticket required = tickets.stream()
        .filter(t -> t.active() && t.id().equals("T-02"))
        .findFirst()
        .orElseThrow(() ->
                new IllegalStateException("Ticket T-02 not found"));
```

Never call `get()` or `getAsInt()` on an unchecked `Optional` just because your sample dataset happens to be non-empty. Include tests for both **an empty source** and **a source emptied by filters**.

### `OptionalInt` is not `Optional<Integer>`

```java
import java.util.OptionalInt;

OptionalInt highest = tickets.stream()
        .filter(Ticket::active)
        .mapToInt(Ticket::score)
        .max();

System.out.println(highest.orElse(-1)); // 95

OptionalInt absent = tickets.stream()
        .filter(t -> t.active() && t.score() > 100)
        .mapToInt(Ticket::score)
        .max();

System.out.println(absent.isEmpty());   // true
System.out.println(absent.orElse(-1));  // -1
```

The value `-1` here is merely **this example's fallback policy**, not a default `max` returned automatically by Java when empty. In a system where valid scores are 0–100, `-1` may serve as a "no data" sentinel; in other domains, keep `OptionalInt` or return a dedicated message.

## 7. Complete Java 17+ Program with Test Suite

Save the following code as `StreamOrderingOptionalTests.java`. It uses `record`, `List.of`, `Stream.toList`, and `Optional.isEmpty`, all standard in Java 17. Each test throws `AssertionError` explicitly on failure, so **`-ea` does not need to be enabled**.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public class StreamOrderingOptionalTests {

    record Ticket(String id, int score, boolean active) {
        Ticket {
            Objects.requireNonNull(id, "id");
            if (id.isBlank()) {
                throw new IllegalArgumentException("ID phải có nội dung");
            }
            if (score < 0 || score > 100) {
                throw new IllegalArgumentException("Điểm ngoài miền 0..100");
            }
        }
    }

    // Ranking: score descending, ID ascending.
    private static final Comparator<Ticket> RANK_ORDER =
            Comparator.comparingInt(Ticket::score)
                    .reversed()
                    .thenComparing(Ticket::id);

    // min: lowest score; smallest ID on ties.
    private static final Comparator<Ticket> MIN_ORDER =
            Comparator.comparingInt(Ticket::score)
                    .thenComparing(Ticket::id);

    // max: highest score; smallest ID on ties.
    private static final Comparator<Ticket> MAX_ORDER =
            Comparator.comparingInt(Ticket::score)
                    .thenComparing(Ticket::id, Comparator.reverseOrder());

    static List<Ticket> fixture() {
        return List.of(
                new Ticket("T-01", 80, true),
                new Ticket("T-02", 95, true),
                new Ticket("T-03", 95, true),
                new Ticket("T-04", 65, true),
                new Ticket("T-05", 40, false),
                new Ticket("T-06", 65, true)
        );
    }

    static Stream<Ticket> active(
            List<Ticket> source, boolean parallel) {
        Objects.requireNonNull(source, "source");
        Stream<Ticket> stream =
                parallel ? source.parallelStream() : source.stream();
        return stream.filter(Ticket::active);
    }

    static List<String> rankedIds(
            List<Ticket> source, boolean parallel) {
        return active(source, parallel)
                .sorted(RANK_ORDER)
                .map(Ticket::id)
                .toList();
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void testEncounterOrder() {
        List<Ticket> data = fixture();
        List<String> expected = List.of(
                "T-01", "T-02", "T-03", "T-04", "T-06");
        List<String> expectedRanking = List.of(
                "T-02", "T-03", "T-01", "T-04", "T-06");

        for (boolean parallel : new boolean[] {false, true}) {
            List<String> ids = active(data, parallel)
                    .map(Ticket::id)
                    .toList();
            check(ids.equals(expected), "Sai encounter order");
            check(rankedIds(data, parallel).equals(expectedRanking),
                    "Sai thứ tự xếp hạng");

            Optional<Ticket> first =
                    active(data, parallel).findFirst();
            check(first.isPresent(), "Thiếu phiếu đầu tiên");
            check(first.orElseThrow().id().equals("T-01"),
                    "findFirst không giữ encounter order");

            Optional<Ticket> any = active(data, parallel).findAny();
            check(any.isPresent(), "findAny không được rỗng");
            check(any.orElseThrow().active(), "findAny trả phiếu inactive");
            check(expected.contains(any.orElseThrow().id()),
                    "findAny nằm ngoài tập đầu vào hợp lệ");
            // Never require findAny to equal T-01.
        }
    }

    static void testExtremes() {
        List<Ticket> data = fixture();
        for (boolean parallel : new boolean[] {false, true}) {
            Ticket minimum = active(data, parallel)
                    .min(MIN_ORDER).orElseThrow();
            Ticket maximum = active(data, parallel)
                    .max(MAX_ORDER).orElseThrow();

            check(minimum.id().equals("T-04"), "Sai min/tie-break");
            check(minimum.score() == 65, "Sai điểm min");
            check(maximum.id().equals("T-02"), "Sai max/tie-break");
            check(maximum.score() == 95, "Sai điểm max");

            OptionalInt minScore = active(data, parallel)
                    .mapToInt(Ticket::score).min();
            OptionalInt maxScore = active(data, parallel)
                    .mapToInt(Ticket::score).max();

            check(minScore.orElse(-1) == 65, "Sai OptionalInt min");
            check(maxScore.orElse(-1) == 95, "Sai OptionalInt max");
        }

        // If the comparator only checks score, the tied ticket's ID
        // is not something we are allowed to assert.
        Ticket tied = data.stream()
                .filter(Ticket::active)
                .max(Comparator.comparingInt(Ticket::score))
                .orElseThrow();
        check(tied.score() == 95, "Sai cực trị theo điểm");
    }

    static void testOptionalAbsent() {
        List<Ticket> source = fixture();
        Optional<Ticket> none = source.stream()
                .filter(t -> t.active() && t.score() > 100)
                .findFirst();
        check(none.isEmpty(), "Điều kiện bất khả thi vẫn có kết quả");
        check(none.map(Ticket::id).orElse("NONE").equals("NONE"),
                "Sai fallback");

        List<Ticket> empty = List.of();
        check(active(empty, false).findFirst().isEmpty(),
                "Nguồn rỗng có findFirst");
        check(active(empty, true).findAny().isEmpty(),
                "Nguồn rỗng có findAny");
        check(active(empty, false).min(MIN_ORDER).isEmpty(),
                "Nguồn rỗng có min");
        check(active(empty, true).max(MAX_ORDER).isEmpty(),
                "Nguồn rỗng có max");

        OptionalInt noScore = active(empty, false)
                .mapToInt(Ticket::score).max();
        check(noScore.isEmpty(), "Nguồn rỗng có OptionalInt max");
        check(noScore.orElse(-1) == -1, "Sai giá trị mặc định");

        // Non-empty source completely emptied by filter.
        List<Ticket> onlyInactive =
                List.of(new Ticket("T-X", 0, false));
        check(active(onlyInactive, true).findFirst().isEmpty(),
                "Nguồn bị lọc hết mà vẫn có phiếu");

        // Optional.stream() yields 0 or 1 element for downstream processing.
        check(none.stream().map(Ticket::id).toList().isEmpty(),
                "Optional rỗng phải cho Stream rỗng");
        check(active(source, false).min(MIN_ORDER)
                .stream().map(Ticket::id).toList()
                .equals(List.of("T-04")), "Optional có giá trị");

        // orElseGet invokes the supplier only when Optional is empty.
        AtomicInteger fallbackCalls = new AtomicInteger();
        Ticket present = active(source, false).findFirst()
                .orElseGet(() -> {
                    fallbackCalls.incrementAndGet();
                    return new Ticket("NONE", 0, false);
                });
        check(present.id().equals("T-01"), "Sai phần tử có sẵn");
        check(fallbackCalls.get() == 0, "Supplier chạy khi đã có giá trị");

        Ticket replacement = none.orElseGet(() -> {
            fallbackCalls.incrementAndGet();
            return new Ticket("NONE", 0, false);
        });
        check(replacement.id().equals("NONE"), "Sai fallback rỗng");
        check(fallbackCalls.get() == 1, "Supplier không chạy đúng một lần");

        boolean thrown = false;
        try {
            none.orElseThrow(NoSuchElementException::new);
        } catch (NoSuchElementException expected) {
            thrown = true;
        }
        check(thrown, "orElseThrow không ném lỗi cho Optional rỗng");
    }

    static void testPermutationInvariants() {
        List<Ticket> reversed = new ArrayList<>(fixture());
        Collections.reverse(reversed);

        // First encountered element depends on encounter order.
        check(active(reversed, false).findFirst()
                .orElseThrow().id().equals("T-06"),
                "Đảo nguồn phải đổi findFirst");

        // Ranking and tie-broken extremes must not depend
        // on input element positions.
        List<String> expectedRanking = List.of(
                "T-02", "T-03", "T-01", "T-04", "T-06");
        for (boolean parallel : new boolean[] {false, true}) {
            check(rankedIds(reversed, parallel).equals(expectedRanking),
                    "Ranking đổi khi đảo nguồn");
            check(active(reversed, parallel).min(MIN_ORDER)
                    .orElseThrow().id().equals("T-04"),
                    "Min đổi khi đảo nguồn");
            check(active(reversed, parallel).max(MAX_ORDER)
                    .orElseThrow().id().equals("T-02"),
                    "Max đổi khi đảo nguồn");
        }
    }

    public static void main(String[] args) {
        testEncounterOrder();
        testExtremes();
        testOptionalAbsent();
        testPermutationInvariants();

        System.out.println("Thứ tự active: "
                + active(fixture(), false).map(Ticket::id).toList());
        System.out.println("Xếp hạng: " + rankedIds(fixture(), false));
        System.out.println("Phiếu cao nhất: "
                + active(fixture(), false).max(MAX_ORDER)
                .orElseThrow().id());
        System.out.println("ALL STREAM TESTS PASS");
    }
}
```

To practice on a machine with JDK 17 or higher:

```text
javac StreamOrderingOptionalTests.java
java StreamOrderingOptionalTests
```

Expected output:

```text
Thứ tự active: [T-01, T-02, T-03, T-04, T-06]
Xếp hạng: [T-02, T-03, T-01, T-04, T-06]
Phiếu cao nhất: T-02
ALL STREAM TESTS PASS
```

This is a self-contained illustrative program and test suite for learners; **it does not claim the program was compiled or executed** during Markdown authoring. Checks in `main` throw `AssertionError` explicitly so failures surface without depending on the JVM's `-ea` setting.

## 8. Matrix of Boundary Cases to Test

| Category | Scenario | Correct conclusion |
| --- | --- | --- |
| Encounter order | `List` source, `filter` then `map` | `toList()` preserves the order of remaining elements. |
| Parallel | Same `List` source, `parallelStream().toList()` | **Output** order preserves encounter order; lambda execution order is unguaranteed. |
| `findFirst` | `List` with matching elements | Exact first element in source order. |
| `findAny` | Same data, especially parallel | Result belongs to the predicate-matching set; do not force a fixed ID. |
| `min`/`max` | Two tied elements | Must test tie-breaking rules if business requires a specific ID. |
| Filter before extreme | Inactive record has smaller score than active ones | `min` considers only valid records. |
| Empty source | Zero elements | `findFirst`, `findAny`, `min`, `max` return `Optional.empty()`. |
| Empty after filter | Source initially non-empty | Search and extreme results are still empty `Optional`s. |
| Primitive | `IntStream.max()` on empty source | `OptionalInt.empty()`, never a default `0` or `-1`. |
| `orElseGet` | Optional already has a value | Supplier is never invoked. |
| Reversed source | Reversed `List` | `findFirst` may change; tie-broken ranking and extremes must keep their rule. |
| Unordered Map/Set | Source without encounter order | Do not assert a fixed traversal order when the API promises none. |

**Key principle:** assertions in a test suite must come from real requirements, not from a single observed run. For instance, never snapshot `parallelStream().forEach(System.out::println)` output and demand all subsequent runs print in that exact schedule.

## 9. Permutation Invariance Testing and Determinism

When the goal is "pick the highest-scoring ticket, breaking ties by smallest ID," the result **must not change** if you merely reverse records in the list. This is a **permutation invariance test** (*metamorphic testing*).

```text
Source A: T-01, T-02, T-03, T-04, T-05, T-06
Source B: T-06, T-05, T-04, T-03, T-02, T-01

max with tie-break:       T-02 on both sources
min with tie-break:       T-04 on both sources
ranking with tie-break:   same sorted list
findFirst:                T-01 on A, T-06 on B
```

These are four **distinct** statements. Asserting `findFirst(A) == findFirst(B)` misunderstands source semantics; asserting "max returns any 95-point ticket" when the contract mandates smallest ID makes the test **too weak**.

### Testing a total-order rule

For ranking output to be deterministic, the comparator should distinguish all cases that matter. In the sample data, `score` and `id` define a tie-broken order. If two records have both the same `score` and the same `id` yet differ in another important attribute, the comparator still treats them as equal.

In that case, clarify:

- Are two records with the same ID allowed to exist?
- If so, which attribute determines their relative order?
- When the comparator returns `0`, does that mean the two records are **business-equivalent**, or simply missing a tie-breaker?

Never tack on arbitrary `thenComparing` clauses just to make output look stable. Tie-breakers must reflect a real business rule or stable identifier.

## 10. When Should You Avoid Asserting a Specific Order?

### `forEach` on a parallel stream

```java
List.of("A", "B", "C").parallelStream()
        .forEach(System.out::print);
```

Never assert that console output is always `ABC`. `forEach` makes no encounter-order guarantee on parallel pipelines.

When consumption order must be preserved:

```java
List.of("A", "B", "C").parallelStream()
        .forEachOrdered(System.out::print); // ABC
```

`forEachOrdered` preserves order when the source has encounter order, though earlier computation steps still need not run sequentially. When testing data, prefer a **returned value** like `toList()` over asserting console print order.

### `unordered()` and unordered sources

```java
List<String> result = List.of("C", "A", "B").stream()
        .unordered()
        .toList();
```

`unordered()` allows dropping encounter-order constraints; never assert the result always keeps the same order, even if some runs happen to return `[C, A, B]`. Similarly, iterating a `HashSet` is not a contract you can rely on as a business ordering criterion.

When a **deterministic** order is needed, add a domain-appropriate `sorted(comparator)` before collecting. Never rely on `HashMap` order, hash codes, thread lists, or a single run's output as a source of truth.

## 11. Debugging Pipelines: Inspect by Stage Without Altering Semantics

A complex pipeline is best debugged using **intentional intermediate outputs**. For example, before calling `min`, materialize the list of valid elements:

```java
List<Ticket> eligible = tickets.stream()
        .filter(Ticket::active)
        .toList();

check(eligible.size() == 5, "Wrong filter step");
check(eligible.stream().map(Ticket::id).toList().equals(
        List.of("T-01", "T-02", "T-03", "T-04", "T-06")),
        "Wrong post-filter order");

Ticket minimum = eligible.stream()
        .min(minOrder)
        .orElseThrow();
check(minimum.id().equals("T-04"), "Wrong min");
```

In this snippet, `tickets`, `Ticket`, `check`, and `minOrder` refer to names from earlier examples. `eligible` is a **materialized list**, so you can open fresh Streams multiple times to inspect each stage. Never hold one `Stream<Ticket> s` variable and call `s.toList()` followed by `s.min(...)`: a Stream cannot be reused after a terminal operation.

### `peek` provides conditional observation only

```java
List<String> ids = tickets.stream()
        .filter(Ticket::active)
        .peek(t -> System.out.println("active: " + t.id()))
        .map(Ticket::id)
        .toList();
```

In a sequential run, `peek` can help watch elements flow through the pipeline. However, never treat log line counts as a correctness requirement: Streams may optimize intermediate stages when terminal results are unaffected. In parallel streams, logs can appear in any order. **Test production code by its output values**, using `peek` strictly as a diagnostic aid.

### Should you use JUnit?

The complete program in Section 7 uses `check` so it runs standalone without external libraries. In real projects, split each case into separate tests using a framework like JUnit:

- One test for encounter order.
- One test for `findFirst` and another for `findAny`.
- One test for `min`/tie-break and another for `max`/tie-break.
- Tests for empty `Optional`, empty sources, and fallbacks.
- Tests comparing sequential vs. parallel and input permutations.

Do not assert the number of worker threads created or callback invocation counts during `findAny`: those are implementation details, not the Stream API result contract.

## 12. Common Mistakes

| Mistake | Consequence | Fix / How to test |
| --- | --- | --- |
| Checking element count without checking order | Wrongly sorted pipeline still passes | Compare full output list when order is required. |
| Forcing `findAny` to return the first element | Test violates contract; flaky in parallel | Check result is in the predicate-matching set. |
| Assuming `max` picks smallest ID when comparator checks score only | Tied result is unspecified per requirements | Add a tie-breaker to the comparator. |
| Calling `max` with ascending score + ascending ID expecting smallest ID | Actually picks the largest ID on ties | Reverse the ID comparator or use ranking + `findFirst`. |
| Forgetting `filter` before `min` | Invalid records can become extremes | Include an inactive fixture with an extreme low/high score. |
| Calling `Optional.get()` without emptiness check | `NoSuchElementException` | Use `isPresent`, `orElseGet`, or `orElseThrow` with an explicit policy. |
| Treating `orElse(-1)` as `OptionalInt`'s built-in default | Misunderstands API and can mask missing data | Check `isEmpty` before choosing a business sentinel. |
| Forgetting empty-after-filter tests | Passes only when source has matching items | Add empty source and all-filtered-out source tests. |
| Using parallel `forEach` order as expected output | Test depends on thread scheduling | Use `forEachOrdered` when order matters, or assert `toList()`. |
| Using `HashSet` and expecting fixed `findFirst` | Source has no deterministic encounter order | Sort source or use an ordered `List`. |
| Reusing the same Stream after a terminal operation | `IllegalStateException` | Open a new Stream from a re-traversable source. |
| Turning functional tests into performance checks | Single-run timing proves nothing about correctness | Separate semantic tests from benchmarks; use proper tools when measuring. |

## 13. Self-Practice Exercises

**Exercise 1 — Order after filtering.** With `List.of(4, 1, 6, 2, 5)`, filter even numbers and double them. What is `toList()` on a sequential Stream?

```java
List<Integer> values = List.of(4, 1, 6, 2, 5);
List<Integer> result = values.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 2)
        .toList();
// [8, 12, 4]
```

**Exercise 2 — `findFirst` vs. `findAny`.** With `List.of("A", "B", "C")`, what must `findFirst` return? Can you assert `parallelStream().findAny()` is always `"A"`?

**Answer:** `findFirst()` on an ordered source must return `"A"`; `findAny()` may return any element in the list and makes no guarantee to always return `"A"`.

**Exercise 3 — Tied scores.** Given three tickets: `X` with 90 points, `A` with 90 points, and `Z` with 85 points. Find the highest-scoring ticket, picking ascending ID on ties.

```java
Ticket best = tickets.stream()
        .max(Comparator.comparingInt(Ticket::score)
                .thenComparing(Ticket::id, Comparator.reverseOrder()))
        .orElseThrow();
// With X=90, A=90, Z=85: best.id() is "A".
```

In this snippet, `tickets` refers to the mini-exercise's list, not the fixture from Section 7.

**Exercise 4 — No data.** If `List.of(5, 10, 20).stream().filter(n -> n > 30).findFirst()` returns an empty Optional, what does `.orElse(-1)` evaluate to?

**Answer:** `-1`. That value is supplied by the caller; Stream never returns `-1` automatically when nothing is found.

**Exercise 5 — Primitive extremes.** What type does `IntStream.empty().min()` return, and what happens if you immediately call `getAsInt()`?

**Answer:** It returns `OptionalInt.empty()`; calling `getAsInt()` when empty throws `NoSuchElementException`. Check `isPresent`, use `orElse`, or use `orElseThrow` per business rules.

**Exercise 6 — Reversing the source.** Reverse the order of all tickets in Section 1. Do `min`, `max` with tie-breaking comparators, and the ranking list change? Does `findFirst` change?

**Answer:** Extremes and ranking do not change because the comparators specify rules independent of position. `findFirst` changes with encounter order: the first active ticket in the reversed list is `T-06`.

**Exercise 7 — Turning an Optional into a Stream.** Given `Optional<Ticket> best`, create a list of 0 or 1 IDs without `if (best.isPresent())`.

```java
List<String> ids = best.stream()
        .map(Ticket::id)
        .toList();
```

With `Optional.empty()`, the list is empty; with a present Optional, the list contains one ID. `Optional.stream()` has been available since Java 9.

## 14. Key Takeaways

- **Encounter order** is a property of the source and pipeline: on a `List`, `filter`/`map`/`toList` preserve remaining element order; parallel callback execution order may differ.
- `findFirst` follows encounter order on ordered sources; `findAny` only promises a valid matching element, **not** the first element.
- `min`/`max` require comparators matching **business criteria and tie-breaking**. If comparing score alone, never assert a fixed ID on ties.
- `Optional` and `OptionalInt` can be empty after filtering or on empty sources; test both present and absent branches and specify fallback or exception policies clearly.
- Solid tests cover **order comparison**, **tied extreme checks**, **empty `Optional`s**, **input permutations**, and **sequential/parallel cross-checks**, never asserting behaviors the API does not guarantee.
