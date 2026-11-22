# Java 9 Additions: ofNullable, iterate, takeWhile, and dropWhile

In the **JDK Compatibility** chapter of the **Java Stream API**, Java version changes directly affect how pipelines are written. Java 8 introduced Streams and familiar operations such as `filter`, `map`, `flatMap`, `reduce`, and `collect`; **Java 9 added four important tools** for handling nullable elements, generating sequences with a stopping condition, and working with the **prefix** of a Stream.

The four additions in this lesson are:

1. `Stream.ofNullable(value)`: creates a Stream with **one** element if the value is non-`null`, or an empty Stream if it is `null`.
2. `Stream.iterate(seed, hasNext, next)`: generates a sequential series following a state-transition rule, **with a termination condition**.
3. `takeWhile(predicate)`: on an ordered Stream, **takes the longest prefix** of contiguous elements matching the predicate.
4. `dropWhile(predicate)`: on an ordered Stream, **drops the longest prefix** of contiguous elements matching the predicate, then keeps the remainder.

We will distinguish them from `Stream.of`, `filter`, `limit`, and `skip`; implement examples **runnable on Java 9**; and analyze pitfalls with sources lacking encounter order, infinite sources, parallel processing, and upgrading/downgrading JDK versions.

## 1. Version Map: Which APIs Exist Since Java 9?

| API | First Version | Main Purpose |
| --- | --- | --- |
| `Stream.ofNullable(T)` | **Java 9** | Converts a possibly `null` value into a Stream of 0 or 1 element |
| `Stream.iterate(T, Predicate, UnaryOperator)` | **Java 9** | Generates a sequence with a condition checked before emitting an element |
| `IntStream.iterate(seed, hasNext, next)` and primitive variants | **Java 9** | Generates a primitive sequence with a stopping point |
| `Stream.takeWhile(Predicate)` | **Java 9** | Takes a prefix matching a condition |
| `Stream.dropWhile(Predicate)` | **Java 9** | Drops a prefix matching a condition |
| `Optional.stream()` | **Java 9** | Converts an Optional into a Stream of 0 or 1 element; related to `ofNullable` |
| `Stream.iterate(seed, next)` | Java 8 | Generates a sequence without a stopping condition inside the overload |
| `Stream.of`, `filter`, `limit`, `skip` | Java 8 | Foundational operations for comparison |

**Point of distinction:** `Stream.toList()` only exists since **Java 16**, not Java 9. Therefore, the compilable Java 9 program in this lesson uses `collect(Collectors.toList())`. `List.of(...)` exists since **Java 9**, so it is permitted in examples targeting Java 9. If a project's codebase must remain Java 8-compatible, these Java 9 APIs must also be replaced with equivalent solutions.

This lesson discusses **standard APIs in `java.util.stream`**. They require no external libraries or preview features, though the project must compile and run in an environment supporting the corresponding APIs.

## 2. Stream.ofNullable: null Becomes 0 Elements, Not One null Element

Before Java 9, code often had to branch:

~~~java
String code = maybeCode();

Stream<String> codes = code == null
        ? Stream.empty()
        : Stream.of(code);
~~~

Since Java 9:

~~~java
Stream<String> codes = Stream.ofNullable(code);
~~~

The contract of `Stream.ofNullable(x)` is very specific:

| Value of `x` | Elements in Stream | `count()` |
| --- | --- | ---: |
| `"JAVA"` | One element `"JAVA"` | 1 |
| `""` | One empty-string element | 1 |
| `null` | No elements | 0 |
| Any non-`null` object | One element equal to that object | 1 |

Minimal example:

~~~java
import java.util.stream.Stream;

System.out.println(Stream.ofNullable("Java").count()); // 1
System.out.println(Stream.ofNullable((String) null).count()); // 0
System.out.println(Stream.ofNullable("").count()); // 1
~~~

An empty `String` is **not** `null`; `ofNullable` does not automatically check for empty strings, length, valid codes, or business content.

### How Does ofNullable Differ from map and filter?

Suppose a record has an optional email field. With `map` alone:

~~~java
List<String> emails = users.stream()
        .map(User::email)
        .collect(Collectors.toList());
~~~

If `email()` returns `null`, the Stream still has **a null element** corresponding to that user, unless another step removes it.

With `ofNullable` and `flatMap`:

~~~java
List<String> emails = users.stream()
        .flatMap(user -> Stream.ofNullable(user.email()))
        .collect(Collectors.toList());
~~~

Each user produces **0 or 1 email**; cases where `email == null` do not pass an element downstream.

A nearly equivalent expression:

~~~java
List<String> emails = users.stream()
        .map(User::email)
        .filter(java.util.Objects::nonNull)
        .collect(Collectors.toList());
~~~

Choose according to intent:

- `map(...).filter(Objects::nonNull)` is easy to read when you already have a general transformation step and need to filter nulls.
- `flatMap(user -> Stream.ofNullable(...))` concisely expresses that **a record may produce no output element**.
- `Optional.ofNullable(value).stream()` also converts 0/1 elements and exists since Java 9, useful if the system already uses `Optional`; there is no need to create a new `Optional` solely to use `ofNullable`.

**Do not use `ofNullable` to silently drop mandatory missing data.** If an email, customer ID, or transaction ID must exist, validate and report errors per the business contract before collecting.

## 3. Practical Example: Attaching Optional Information to Output Data

Suppose each event may or may not have a trace ID:

~~~java
final class Event {
    final String service;
    final String traceId;

    Event(String service, String traceId) {
        this.service = service;
        this.traceId = traceId;
    }
}
~~~

We only want the list of present trace IDs:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<Event> events = Arrays.asList(
        new Event("auth", "T-01"),
        new Event("search", null),
        new Event("billing", "T-03")
);

List<String> traceIds = events.stream()
        .flatMap(event -> Stream.ofNullable(event.traceId))
        .collect(Collectors.toList());

System.out.println(traceIds); // [T-01, T-03]
~~~

`flatMap` flattens each sub-stream created by `ofNullable`, so records without a trace ID do not occupy a slot in the result list. Dropping those slots is **intentional** here; if you must preserve one result per event, use a DTO with a nullable field or `Optional` inside the result object instead of dropping elements.

**Note on the source:** `List.of` does not accept a `null` **list element**, but an `Event` object inside the list can still have `traceId = null`. The example uses `Arrays.asList` for illustration; all `Event` items in the list are non-`null`.

## 4. iterate: From Unbounded Sequences to Sequences with a Stopping Condition

Java 8 provides:

~~~java
Stream<T> iterate(T seed, UnaryOperator<T> next)
~~~

Example:

~~~java
import java.util.stream.IntStream;

int total = IntStream.iterate(1, n -> n + 1)
        .limit(5)
        .sum();

System.out.println(total); // 15
~~~

The two-parameter overload generates `1, 2, 3, ...` where the source itself **has no declared finite termination condition**. `limit(5)` is the intermediate operation ensuring the `sum()` terminal only needs the first five numbers.

Java 9 adds the overload:

~~~java
Stream<T> iterate(
        T seed,
        Predicate<? super T> hasNext,
        UnaryOperator<T> next)
~~~

For primitive streams, corresponding overloads exist on `IntStream`, `LongStream`, and `DoubleStream`. Example:

~~~java
int total = IntStream.iterate(
                1,
                n -> n <= 5,
                n -> n + 1)
        .sum();

System.out.println(total); // 15
~~~

The sequence here follows a **check-before-emit** rule:

~~~text
seed = 1
hasNext(1) = true  -> emit 1
next(1) = 2
hasNext(2) = true  -> emit 2
...
hasNext(5) = true  -> emit 5
next(5) = 6
hasNext(6) = false -> terminate, do NOT emit 6
~~~

If `hasNext(seed)` is already `false`, the Stream is **empty from the start**.

### The Stopping Condition Is hasNext, Not filter

~~~java
import java.util.stream.IntStream;

int[] numbers = IntStream.iterate(
        10,
        n -> n < 10,
        n -> n + 1
).toArray();

System.out.println(numbers.length); // 0
~~~

`hasNext` determines **whether to continue generating elements**, unlike `filter`, which only decides **whether to keep or discard an already generated element**. If you only apply `filter(n -> n < 10)` to an infinite source that keeps increasing past 10, finding all outputs via `collect` may still fail to terminate.

### Boundary Mistakes

~~~java
IntStream.iterate(1, n -> n < 5, n -> n + 1)
// Emits 1, 2, 3, 4; does NOT include 5.

IntStream.iterate(1, n -> n <= 5, n -> n + 1)
// Emits 1, 2, 3, 4, 5.
~~~

Choose `<` or `<=` according to the problem's half-open or closed interval contract. Do not use `peek` or print logs to infer `hasNext`/`next` execution order in a parallel pipeline.

## 5. iterate with LocalDate: Generating a Calendar Over a Date Range

A practical example is generating consecutive dates without a loop outside the Stream:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

LocalDate start = LocalDate.of(2026, 11, 15);
LocalDate endExclusive = LocalDate.of(2026, 11, 19);

List<LocalDate> days = Stream.iterate(
                start,
                day -> day.isBefore(endExclusive),
                day -> day.plusDays(1))
        .collect(Collectors.toList());

System.out.println(days);
// [2026-11-15, 2026-11-16, 2026-11-17, 2026-11-18]
~~~

The name `endExclusive` makes it clear that day 19 is **not** in the result. If day 19 should be included, the condition can be `!day.isAfter(endInclusive)` with an `endInclusive` variable.

`LocalDate` is an immutable object; each `plusDays(1)` creates a new date. This avoids sharing a mutable calendar object and updating it across multiple elements.

### Not Necessarily Faster Than range or a Loop

For a simple integer sequence, `IntStream.range(0, n)` or `rangeClosed` usually expresses the range better and provides a Spliterator source that splits easily:

~~~java
int[] values = IntStream.rangeClosed(1, 5).toArray();
// [1, 2, 3, 4, 5]
~~~

`iterate` is especially suitable when **the next element is computed from the previous state** rather than a simple integer range: dates, incrementing versions, algorithm states, or progress of a finite process. A sequence depending on the previous element is typically harder to parallelize effectively than an index-splittable source.

## 6. takeWhile: Taking a Contiguous Prefix, Not Filtering All Matching Elements

`takeWhile(predicate)` is an intermediate operation available since Java 9. On a **Stream with encounter order**, it keeps the **longest prefix** of contiguous elements satisfying the predicate; upon encountering the first element that fails, it stops taking subsequent elements into the result.

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<Integer> values = List.of(2, 4, 7, 8, 10);

List<Integer> prefix = values.stream()
        .takeWhile(n -> n % 2 == 0)
        .collect(Collectors.toList());

System.out.println(prefix); // [2, 4]
~~~

Even though `8` and `10` are also even, they **do not appear** because element `7` terminated the prefix.

Direct comparison with `filter`:

~~~java
List<Integer> allEven = values.stream()
        .filter(n -> n % 2 == 0)
        .collect(Collectors.toList());

System.out.println(allEven); // [2, 4, 8, 10]
~~~

| Operation | Which Elements Are Emitted? | On `[2,4,7,8,10]`, even predicate |
| --- | --- | --- |
| `filter(p)` | Every element satisfying `p` across the entire source | `[2,4,8,10]` |
| `takeWhile(p)` | Elements satisfying `p` **contiguously at the start** | `[2,4]` |
| `limit(2)` | The first two elements, regardless of condition | `[2,4]` in this example; different in nature |

**Do not replace `filter` with `takeWhile` merely to stop early**, unless the problem genuinely calls for a prefix or it is proven that no needed element exists after the first failing element.

## 7. takeWhile on Sorted Data: Segmenting by a Timestamp Cutoff

A useful scenario: logs/events sorted in **ascending timestamp order**, where only events before a cutoff are needed.

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.stream.Collectors;

final class DatedEvent {
    final LocalDate date;
    final String code;

    DatedEvent(LocalDate date, String code) {
        this.date = date;
        this.code = code;
    }
}

List<DatedEvent> events = List.of(
        new DatedEvent(LocalDate.of(2026, 11, 15), "A"),
        new DatedEvent(LocalDate.of(2026, 11, 16), "B"),
        new DatedEvent(LocalDate.of(2026, 11, 18), "C")
);

LocalDate cutoff = LocalDate.of(2026, 11, 17);

List<String> beforeCutoff = events.stream()
        .takeWhile(e -> e.date.isBefore(cutoff))
        .map(e -> e.code)
        .collect(Collectors.toList());

System.out.println(beforeCutoff); // [A, B]
~~~

Because the events are in ascending chronological order, after encountering day 18 (not before the cutoff), we know **all subsequent elements will also fail**, so taking the prefix can stop.

However, if the source is **not sorted**:

~~~text
2026-11-15 -> A
2026-11-18 -> C
2026-11-16 -> B
~~~

`takeWhile(e -> e.date.isBefore(cutoff))` collects only `A`, **skipping B** even though B is before the cutoff. When you need **all events before the cutoff** from an unsorted source, use `filter` instead of `takeWhile`.

You can call `sorted(comparator)` before `takeWhile` if the data is unordered, but `sorted` is a stateful operation that may need to materialize all elements to sort. For large sources, the right solution is usually reading a source **already sorted by the storage layer** or querying via a time index.

## 8. dropWhile: Dropping the Prefix, Keeping the Remainder Intact

`dropWhile(predicate)` is the counterpart to `takeWhile` on an ordered Stream: it drops elements **contiguously from the start** that satisfy the predicate. Once it encounters the first failing element, it keeps that element **and all subsequent elements**, even if later elements satisfy the predicate again.

~~~java
List<Integer> values = List.of(2, 4, 7, 8, 10);

List<Integer> suffix = values.stream()
        .dropWhile(n -> n % 2 == 0)
        .collect(Collectors.toList());

System.out.println(suffix); // [7, 8, 10]
~~~

Element `7` is the transition point:

~~~text
Source:     [2, 4, | 7, 8, 10]
dropWhile:  drop   | keep all starting from 7
Result:            [7, 8, 10]
~~~

Compare with `filter(n -> n % 2 != 0)`:

~~~java
List<Integer> oddOnly = values.stream()
        .filter(n -> n % 2 != 0)
        .collect(Collectors.toList());

System.out.println(oddOnly); // [7]
~~~

The two results differ greatly. `dropWhile` is not an operation to "remove all even numbers."

### Practical Example: Skipping Consecutive Header Lines at the Start of a File

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> lines = Arrays.asList(
        "# exported-by=system",
        "# format=csv",
        "id,name",
        "1,Lan",
        "# comment in body",
        "2,An"
);

List<String> body = lines.stream()
        .dropWhile(line -> line.startsWith("#"))
        .collect(Collectors.toList());

System.out.println(body);
// [id,name, 1,Lan, # comment in body, 2,An]
~~~

This matches the requirement to **skip leading comment lines**, not to remove every comment. The `# comment in body` line is still kept because it comes after the `id,name` line that first failed the predicate.

If the file format permits comments at **any position**, use `filter(line -> !line.startsWith("#"))`; that is a different problem.

## 9. Edge Cases of takeWhile and dropWhile

For an ordered Stream, given predicate `p`:

| Input Sequence Relative to `p` | `takeWhile(p)` | `dropWhile(p)` |
| --- | --- | --- |
| Empty Stream | Empty | Empty |
| First element fails | Empty | Keeps all |
| All elements match | Keeps all | Empty |
| Some initial elements match, then one fails | Keeps exact matching prefix | Keeps from first failing element to the end |

For a finite ordered Stream, the data can be split into **two parts by the same predicate**: the prefix kept by `takeWhile` and the suffix kept by `dropWhile`. However, **you cannot invoke two terminal operations on the same already-consumed Stream object**. If you want both parts, create two new Streams from a re-traversable source, or implement partitioning in a single pass.

Do not attempt:

~~~java
Stream<Integer> stream = values.stream();

List<Integer> prefix = stream.takeWhile(p).collect(Collectors.toList());
// Cannot continue reusing stream:
List<Integer> suffix = stream.dropWhile(p).collect(Collectors.toList());
~~~

Both are intermediate operations, but the first `collect` terminal consumed the Stream, so reusing the same `stream` is invalid.

## 10. Encounter Order Determines the Meaning of takeWhile/dropWhile

**The easiest mistake when using Java 9:** the "longest prefix" meaning is only guaranteed when the Stream has an **encounter order**.

Sources that typically have encounter order:

- `List.stream()` and `List.parallelStream()`.
- `IntStream.range(...)` or `LongStream.range(...)`.
- Sources with `Spliterator.ORDERED` adhering to contract.

Sources that may **not** have encounter order:

- `HashSet.stream()`, which by contract does not guarantee a consistent iteration order.
- A Stream that explicitly called `unordered()`.
- Certain custom Spliterators or collectors that do not declare `ORDERED`.

For an **unordered** Stream, the Java API permits `takeWhile` to select **any subset of elements satisfying the predicate**, not bound to a unique prefix because no order is defined. `dropWhile` may drop any subset of elements satisfying the predicate; elements that fail the predicate must still be retained.

~~~java
import java.util.Set;

Set<Integer> set = Set.of(2, 4, 7, 8, 10);

List<Integer> output = set.parallelStream()
        .takeWhile(n -> n % 2 == 0)
        .collect(Collectors.toList());

// Must NOT assume output is always [2, 4]
// or always contains all even numbers.
~~~

This is not a random bug; it is a **permitted part of the API contract**. Using `takeWhile`/`dropWhile` for "records before/after a cutoff" requires **explicit ordering**, typically a source sorted by key or timestamp.

### unordered() Is Not a Harmless Optimization Switch

~~~java
List<Integer> values = List.of(2, 4, 7, 8, 10);

List<Integer> result = values.parallelStream()
        .unordered()
        .takeWhile(n -> n % 2 == 0)
        .collect(Collectors.toList());
~~~

Although `unordered()` can reduce some coordination constraints, it simultaneously **drops the guarantee of taking the prefix in list order**. Only use it when business logic does not care about a prefix; if you just need all elements matching the predicate, `filter` is the operation that expresses the right intent.

## 11. Parallel Streams and the Cost of Maintaining Prefixes

`takeWhile` and `dropWhile` can be used in parallel pipelines, but evaluate **semantic correctness first, performance second**.

~~~java
import java.util.stream.IntStream;

int[] prefix = IntStream.range(0, 100)
        .parallel()
        .takeWhile(n -> n < 10)
        .toArray();

// For an ordered range source: [0,1,2,3,4,5,6,7,8,9].
~~~

To preserve the exact prefix in an ordered Stream, the runtime may have to coordinate work units before and after the cutoff point. This makes `takeWhile`/`dropWhile` on an ordered parallel stream **more expensive** than a sequential pipeline in many scenarios.

Do not assume that:

- Switching `stream()` to `parallelStream()` is always faster.
- `takeWhile` always invokes the predicate only once per observed element under every execution strategy.
- The **execution** order of predicates or mappers always matches the encounter order.
- `dropWhile` skips all work before the cutoff on a source without random access; many sources still must be traversed to locate the split point.

If you need an exact limit of "the first 100 elements", use `limit(100)` on an ordered source. If you need "every matching element", use `filter`. If you need the initial slice before a cutoff on a sorted source, `takeWhile` fits.

## 12. Distinguishing Count-Based Operations from Condition-Based Operations

| Need | Method | Scope of Effect |
| --- | --- | --- |
| Keep only a non-null value from one value | `Stream.ofNullable` | 0 or 1 element |
| Generate from seed while condition holds | `iterate(seed, hasNext, next)` | Source with a stopping condition |
| Keep every element matching predicate regardless of position | `filter(predicate)` | Entire traversed dataset |
| Take contiguously from start while predicate holds | `takeWhile(predicate)` | Prefix of an ordered Stream |
| Drop contiguously from start while predicate holds | `dropWhile(predicate)` | Dropped prefix, suffix retained |
| Take at most the first N elements | `limit(n)` | Element count |
| Skip the first N elements | `skip(n)` | Element count |

For example, `limit` and `takeWhile` can both return `[1,2,3]` on a dataset, but that **does not make them equivalent**. `limit(3)` ignores values; `takeWhile(n -> n < 4)` depends on the condition and ordering.

### Combining Methods According to Purpose

~~~java
import java.util.stream.IntStream;

// Generate numbers from 1 to 100 (inclusive), take while less than 8,
// then remove even numbers:
int[] result = IntStream.iterate(1, n -> n <= 100, n -> n + 1)
        .takeWhile(n -> n < 8)
        .filter(n -> n % 2 != 0)
        .toArray();

// [1, 3, 5, 7]
~~~

Here both `iterate` and `takeWhile` have bounds, yet the two conditions serve **two different goals**: the source is allowed to generate up to 100, whereas the specific pipeline only needs initial numbers before 8. In real code, if only `1..7` are needed, the stopping condition of `iterate` can be expressed directly to avoid an extra stage.

## 13. Infinite Sources, Lazy Evaluation, and Termination Rules

Two-parameter `Stream.iterate(seed, next)` typically produces a source with no declared termination point, whereas `iterate(seed, hasNext, next)` allows checking a stopping condition.

~~~java
import java.util.stream.Stream;

long count = Stream.iterate(1, n -> n <= 5, n -> n + 1)
        .count();

System.out.println(count); // 5
~~~

However, **having three parameters does not automatically guarantee a finite source**: if `hasNext` is always `true`, the source still may not terminate.

~~~java
// Do not call unbounded collect()/count() on this source:
Stream<Integer> endless = Stream.iterate(
        0,
        n -> true,
        n -> n + 1
);
~~~

Nor should you rely on an external mutable counter to "force" a predicate to stop. A stateful predicate or source interference can break the contract of Stream operations, especially under parallel execution.

### Overflow and Stopping Conditions

If generating `int` values near `Integer.MAX_VALUE` and continuously adding `1`, values can overflow into negative numbers. A predicate like `n <= end` can start evaluating true again and make the generator run unexpectedly.

For a regular integer range, prefer `IntStream.range`/`rangeClosed` when suitable. For a sequence computed from the previous element, verify the numeric domain, stopping condition, and overflow-free state transition, or use a sufficiently wide numeric type.

### Laziness Does Not Mean takeWhile Makes File Reading Safe

`ofNullable`, `iterate`, `takeWhile`, and `dropWhile` participate in the Stream pipeline, but they do not solve **resource closing**. With a `Files.lines(path)` source, even when `takeWhile` or `findFirst` stops early, the I/O source still requires `try-with-resources`.

## 14. Complete Integrated Example, Compilable with Java 9

The program below uses **only APIs available in Java 9 or earlier**, so it can compile with `javac --release 9` on a modern JDK. We have a list of events **already sorted in ascending date order**; trace ID may be null.

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class Java9StreamAdditionsDemo {

    static final class Event {
        final LocalDate date;
        final String service;
        final String traceId;

        Event(LocalDate date, String service, String traceId) {
            this.date = date;
            this.service = service;
            this.traceId = traceId;
        }
    }

    public static void main(String[] args) {
        List<Event> events = List.of(
                new Event(LocalDate.of(2026, 11, 15), "auth", "T-01"),
                new Event(LocalDate.of(2026, 11, 16), "search", null),
                new Event(LocalDate.of(2026, 11, 17), "auth", "T-03"),
                new Event(LocalDate.of(2026, 11, 19), "billing", null)
        );

        // ofNullable: an Event without a traceId emits 0 elements.
        List<String> traces = events.stream()
                .flatMap(e -> Stream.ofNullable(e.traceId))
                .collect(Collectors.toList());

        // 3-arg iterate: Nov 15, 16, 17, 18 (excluding Nov 19).
        List<LocalDate> days = Stream.iterate(
                        LocalDate.of(2026, 11, 15),
                        day -> day.isBefore(
                                LocalDate.of(2026, 11, 19)),
                        day -> day.plusDays(1))
                .collect(Collectors.toList());

        LocalDate cutoff = LocalDate.of(2026, 11, 17);

        // takeWhile: keep only events before Nov 17.
        List<String> before = events.stream()
                .takeWhile(e -> e.date.isBefore(cutoff))
                .map(e -> e.service)
                .collect(Collectors.toList());

        // dropWhile: drop the part before Nov 17, keep the remainder.
        List<String> fromCutoff = events.stream()
                .dropWhile(e -> e.date.isBefore(cutoff))
                .map(e -> e.service)
                .collect(Collectors.toList());

        System.out.println("traces=" + traces);
        System.out.println("days=" + days);
        System.out.println("before=" + before);
        System.out.println("fromCutoff=" + fromCutoff);
    }
}
~~~

Output:

~~~text
traces=[T-01, T-03]
days=[2026-11-15, 2026-11-16, 2026-11-17, 2026-11-18]
before=[auth, search]
fromCutoff=[auth, billing]
~~~

Test commands on a machine with a JDK supporting the `--release` option:

~~~bash
javac --release 9 Java9StreamAdditionsDemo.java
java Java9StreamAdditionsDemo
~~~

**Why does the example use multiple distinct Streams?** Each `events.stream()` call creates a new Stream from the re-traversable `List`. Reusing a Stream object on which a terminal operation was already called is invalid.

**Why not use `Stream.toList()`?** Because that method only exists since Java 16; it would make the example **no longer compilable targeting Java 9**.

## 15. Application to Large Files: Ordering Conditions and I/O Lifecycle

Suppose a log file has lines in ascending chronological order, each starting with a standard timestamp. We want the segment before a business cutoff.

Diagram:

~~~text
Files.lines(...) -> parseLine -> takeWhile(event < cutoff) -> collect
       |                                        |
  I/O must be closed                  requires sorted input
~~~

Both conditions must be ensured:

1. **Ordering:** the file truly has ascending timestamps; otherwise, `takeWhile` misses older events located after a newer event.
2. **Lifecycle:** `Files.lines` must be closed even if the pipeline only reads a prefix.

An illustrative version on strings with confirmed ordering:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> readBeforeMarker(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {
        return lines
                .takeWhile(line -> !line.equals("--END-SECTION--"))
                .collect(Collectors.toList());
    }
}
~~~

This example retrieves lines **before a marker**, not a timestamp parser: `takeWhile` keeps the exact prefix before the `--END-SECTION--` line and does **not** include the marker. If the marker appears first, the result is empty. If there is no marker, all lines are collected into the List.

For extremely large files, even with proper source closing, `collect(toList())` can still consume substantial memory if the prefix is long. You can replace the terminal with an aggregation such as `count` or `reduce` when only statistics are needed.

If the requirement is to **skip leading file headers** with `dropWhile`, the entire pipeline must likewise be placed inside `try-with-resources`. Never return a lazy Stream out of a `try` block that already closed the source.

## 16. Codebase Migration: Java 8 and Java 9

When a project must still run on Java 8, **do not directly call** APIs that only appeared in Java 9. Common migration patterns:

### 16.1. ofNullable in Java 8

Java 9:

~~~java
Stream<String> result = Stream.ofNullable(maybeValue);
~~~

Java 8:

~~~java
Stream<String> result = maybeValue == null
        ? Stream.empty()
        : Stream.of(maybeValue);
~~~

In a `flatMap` pipeline:

~~~java
.flatMap(user -> user.email() == null
        ? Stream.<String>empty()
        : Stream.of(user.email()))
~~~

The form `map(User::email).filter(Objects::nonNull)` also exists since Java 8 and may be clearer when only removing null elements.

### 16.2. Finite iterate in Java 8

Java 9:

~~~java
IntStream.iterate(1, n -> n <= 5, n -> n + 1)
~~~

For a simple integer sequence, Java 8 can use:

~~~java
IntStream.rangeClosed(1, 5)
~~~

Or for a uniformly increasing sequence with a known element count:

~~~java
IntStream.iterate(1, n -> n + 1).limit(5)
~~~

However, `limit(5)` only knows **how many elements to take**, not how to replace an arbitrary condition such as "take until the state has finished" in all problems. For sources with complex stopping conditions in Java 8, a custom `Iterator`/`Spliterator` or an explicit loop may be needed.

### 16.3. takeWhile/dropWhile on Java 8

Java 8 **does not have** these two methods. Only replace with `filter` when the business requirement is truly "take every element matching the predicate", not "take/drop a prefix".

Example:

~~~text
Source: [2, 4, 7, 8]

takeWhile(even) -> [2, 4]
filter(even)    -> [2, 4, 8]

dropWhile(even) -> [7, 8]
filter(odd)     -> [7]
~~~

To preserve exact prefix semantics in Java 8, use a stateful iterator, a sequential loop, or a dedicated Spliterator implementation; test the path hitting the first failing element and the elements after it.

### 16.4. Check the Toolchain, Not Just the Machine's java Version

If code must run on Java 8 while a developer uses a newer JDK, merely having a newer JDK **does not mean** Java 9 APIs are allowed. Configure the right compatibility level for the build.

On a modern JDK:

~~~bash
javac --release 8 MyJava8Source.java
javac --release 9 Java9StreamAdditionsDemo.java
~~~

`--release` controls the language level and platform APIs usable when compiling for the target version. The Java 9 example in section 14 **will not** compile with `--release 8` because the Java 9 APIs do not exist in the target release.

Conversely, setting only an old syntax level while still allowing linking against newer JDK APIs can lead to failures on older runtimes. Therefore, consider **compiler, target API, and deployment runtime together**.

Do not upgrade an entire module to a newer version just to use one convenience method if the project has constraints requiring an older JDK. Weigh compatibility workarounds against a planned JDK upgrade.

## 17. Common Errors and How to Fix Them

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| `cannot find symbol: ofNullable` or `takeWhile` | Compiling with Java 8 target API | Use `--release 9` or higher if JDK upgrade is permitted, or write the Java 8 equivalent pattern |
| `NoSuchMethodError` on an older runtime | Code calls an API absent in the running runtime | Align compiler target and deployment runtime |
| `ofNullable(null)` drops records needing audit | Treating null as skippable data while business logic requires an error | Validate mandatory fields upfront or retain a separate missing-data status |
| `iterate` misses the last element | Using `<` instead of `<=` in hasNext | Clarify closed/half-open interval and test boundary values |
| `iterate` does not terminate | Predicate always true or counter overflows back into the valid range | Ensure a finite stopping condition and safe numeric domain |
| `takeWhile` misses later matching values | Using prefix semantics instead of full-source filtering | Use `filter` if the data lacks the required ordering/monotonicity |
| `dropWhile` retains unwanted later elements | Drops only the prefix, not all predicate-matching elements | Use `filter` if all such elements must be removed |
| Prefix results vary on an unordered stream | Source lacks encounter order or `unordered()` was called | Pick an ordered/`sorted` source or switch business logic to `filter` |
| Parallel pipeline is slower | Coordination overhead to determine the prefix of an ordered source | Benchmark and consider keeping it sequential |
| `IllegalStateException` when reusing a Stream | A terminal operation already ran on the same Stream | Create a new Stream from a re-traversable source |
| File remains unclosed after taking prefix | Terminal operation does not close I/O sources | Wrap `Files.lines` in `try-with-resources` |
| Old log lines missed after cutoff | File is not actually sorted by timestamp | Validate ordering, use `filter`, or sort as required |

## 18. Self-Check Exercises

### Exercise 1 — ofNullable with null and Empty String

~~~java
long a = Stream.ofNullable((String) null).count();
long b = Stream.ofNullable("").count();
~~~

**Answer:** `a = 0` and `b = 1`. `ofNullable` only checks for `null`, not empty strings.

### Exercise 2 — iterate Boundary

~~~java
int[] data = IntStream.iterate(2, n -> n < 7, n -> n + 2)
        .toArray();
~~~

**Answer:** `[2, 4, 6]`. `hasNext(8)` is false so 8 is not emitted. If the initial seed fails the predicate, the Stream is empty.

### Exercise 3 — Does takeWhile Pick 8?

~~~java
List<Integer> source = List.of(2, 4, 7, 8, 10);

List<Integer> result = source.stream()
        .takeWhile(n -> n % 2 == 0)
        .collect(Collectors.toList());
~~~

**Answer:** `[2, 4]`, without 8 and 10. `takeWhile` only takes the even prefix before 7, unlike `filter`.

### Exercise 4 — Does dropWhile Remove Trailing Even Numbers?

~~~java
List<Integer> result = List.of(2, 4, 7, 8, 10).stream()
        .dropWhile(n -> n % 2 == 0)
        .collect(Collectors.toList());
~~~

**Answer:** `[7, 8, 10]`. After 7, the entire suffix is kept, including even numbers.

### Exercise 5 — Choosing an Operation by Requirement

An event source is **not sorted by time**, and you need **all events before 2026-12-01**. Should you use `takeWhile` or `filter`?

**Answer:** `filter(event -> event.time().isBefore(cutoff))` if all matching events are required. `takeWhile` is only right when you want a prefix or the source is guaranteed to be ordered such that the condition can never become true again after the first failure.

### Exercise 6 — Using parallel and unordered

Given a `HashSet` of integers, calling `parallelStream().takeWhile(n -> n < 5)`. Is the result guaranteed to contain all numbers less than 5?

**Answer:** No. The Stream has no guaranteed encounter order; `takeWhile` is allowed to take a subset of the predicate-matching elements. Use `filter(n -> n < 5)` if all numbers less than 5 are needed.

### Exercise 7 — Is the Program Truly Java 9 Compatible?

~~~java
List<Integer> values = IntStream.range(0, 10)
        .boxed()
        .toList();
~~~

**Answer:** Not source code using only Java 9 APIs; `Stream.toList()` appeared in Java 16. On Java 9, use `collect(Collectors.toList())`.

### Exercise 8 — Closing a File with dropWhile

~~~java
long count = Files.lines(path)
        .dropWhile(line -> line.startsWith("#"))
        .count();
~~~

**Answer:** Missing source lifecycle management. Use:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    long count = lines
            .dropWhile(line -> line.startsWith("#"))
            .count();
}
~~~

`count()` does not close the Stream automatically, even after traversing all lines.

## 19. Takeaways

- **Java 9** added `Stream.ofNullable`, the `iterate(seed, hasNext, next)` overload, and the `takeWhile`/`dropWhile` operations.
- `ofNullable` emits **0 or 1 element**; it fits skipping optional values, **not** automatically validating mandatory missing data.
- Three-argument `iterate` checks `hasNext` **before emitting an element**, so upper/lower bounds must be set accurately and non-terminating conditions avoided.
- `takeWhile` **takes the contiguous prefix** matching a condition; `dropWhile` **drops the contiguous prefix** matching a condition, keeping the first failing element and all elements after it.
- `filter` applies to **every element**; `limit`/`skip` count elements. Do not substitute one for another when business requirements differ.
- On **unordered streams**, the two prefix operations no longer guarantee selecting the exact prefix as with an ordered `List`. `parallel()` does not automatically erase encounter order, but can make prefix preservation costly.
- Intermediate operations remain lazy; I/O sources still require `try-with-resources` even when the pipeline stops early.
- For Java 9 compatibility, avoid later APIs such as `Stream.toList()` (Java 16); use `javac --release 9` and verify the deployment target runtime.

**Main point:** These four APIs clearly model **absence of a value**, **stopping points of sequence generators**, and **prefix boundaries of ordered data**. Using their exact contracts — especially differences from `filter` and encounter order constraints — yields declarative pipelines that are easy to understand, predictable, and accurately compatible with the JDK version your project supports.