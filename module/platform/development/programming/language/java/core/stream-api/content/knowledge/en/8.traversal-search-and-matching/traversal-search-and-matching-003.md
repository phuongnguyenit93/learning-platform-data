# Finding Elements with `findFirst` and `findAny`

In the **Java Stream API**, operations like `filter`, `map`, `distinct`, `sorted`, and slicing operations describe how to select, transform, and order data in a *lazy* pipeline. When the goal is simply **finding a matching element**, the two commonly used terminal operations are `findFirst()` and `findAny()`. They look similar because both return `Optional<T>`, but they offer two different contracts regarding **encounter order**.

The key point to grasp is: **`findFirst()` requires the first element in encounter order if that order exists; `findAny()` may choose any element**. This difference affects result determinism, parallelization capability, and sometimes performance.

## 1. Two Short-Circuiting Terminal Operations

For `Stream<T>`, the simplified signatures are:

```java
Optional<T> findFirst();
Optional<T> findAny();
```

These are two **short-circuiting terminal operations**. Once a valid result is found, they can terminate without needing to process the entire data source.

| Criterion | `findFirst()` | `findAny()` |
| --- | --- | --- |
| Meaning | Gets the **first element in encounter order**, if any. | Gets **any element**, if any. |
| Ordered source | Must respect encounter order. | Not constrained to pick the first element. |
| Unordered source | May return any element. | May return any element. |
| Result on empty stream | `Optional.empty()` | `Optional.empty()` |
| Short-circuiting capability | Yes. | Yes. |
| Parallel processing | May incur coordination overhead to preserve order. | Often has more optimization opportunities when order does not matter. |

Both methods have existed since **Java 8**. Both return `Optional` because a stream may contain no elements after filtering. For `IntStream`, `LongStream`, and `DoubleStream`, the corresponding APIs return `OptionalInt`, `OptionalLong`, and `OptionalDouble`.

### First Example

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

public class FindExample {
    public static void main(String[] args) {
        List<String> names = Arrays.asList("An", "Binh", "Chi", "Dung");

        Optional<String> first = names.stream()
            .filter(name -> name.length() >= 4)
            .findFirst();

        Optional<String> any = names.stream()
            .filter(name -> name.length() >= 4)
            .findAny();

        System.out.println(first.orElse("Not found")); // Binh
        System.out.println(any.orElse("Not found"));   // May be Binh or Dung
    }
}
```

The list has encounter order `An → Binh → Chi → Dung`. After `filter`, the matching elements in order are `Binh → Dung`, so `findFirst()` **must** return `Binh`. `findAny()` is allowed to return `Binh` or `Dung`; in a given sequential run, it often returns the first element too, but **that is not a contract to rely on**.

## 2. Encounter Order Is Determined by Source and Pipeline

**Encounter order** is the logical order in which the stream receives elements from its source and through intermediate operations. It is not synonymous with CPU execution order, nor is it automatically ascending order by value.

Common sources:

| Source | Has Defined Encounter Order? | Notes |
| --- | --- | --- |
| `List.stream()`, `ArrayList.stream()` | Yes. | Follows position in the list. |
| `Arrays.stream(array)`, `Stream.of(...)` | Yes. | Follows order in the array or arguments. |
| `LinkedHashSet.stream()` | Yes. | Follows iteration order of `LinkedHashSet`, typically insertion order. |
| `TreeSet.stream()` | Yes. | Follows the comparator's ordering or natural order. |
| `HashSet.stream()` | No guaranteed encounter order. | Do not use `findFirst` to infer a stable element. |
| `Stream.generate(supplier)` | No guaranteed encounter order. | Values are generated as the pipeline requests them. |

For example, `findFirst()` is not an operation for finding the minimum value:

```java
import java.util.Arrays;

System.out.println(
    Arrays.asList(30, 10, 20).stream().findFirst().get()
); // 30
```

If the problem requires the **smallest value**, you can use `min` or sort before searching:

```java
import java.util.Arrays;

int smallest = Arrays.asList(30, 10, 20).stream()
    .min(Integer::compareTo)
    .orElseThrow(IllegalStateException::new);

System.out.println(smallest); // 10
```

`min` usually does less work than `sorted().findFirst()` when only the smallest value is needed: `min` traverses to reduce to one value, whereas `sorted` has to inspect and organize all elements to guarantee ascending order. `min` is **not** a short-circuiting terminal operation on normal data; it still needs to compare the remaining elements.

### Intermediate Operations Can Change Logical Order

```java
import java.util.Arrays;

Integer originalFirst = Arrays.asList(30, 10, 20).stream()
    .findFirst().orElse(-1);

Integer sortedFirst = Arrays.asList(30, 10, 20).stream()
    .sorted()
    .findFirst().orElse(-1);

System.out.println(originalFirst); // 30
System.out.println(sortedFirst);   // 10
```

`filter` preserves the relative order of remaining elements for an ordered stream. `sorted` establishes a new order based on a comparator. `unordered()` **removes the ordering constraint** from the pipeline; this does not necessarily change the order immediately in a single run, but from that point onward you must not expect `findFirst` to retain the first element of the original source.

Example:

```java
import java.util.Arrays;
import java.util.Optional;

Optional<Integer> result = Arrays.asList(30, 10, 20).parallelStream()
    .unordered()
    .findFirst();

// May be 30, 10, or 20: encounter order is no longer guaranteed.
```

When business logic asks for “first”, you must define **first according to what order**: insertion order, timestamp, priority, or index. If the input does not yet have that order, sort or select with a comparator first.

## 3. Result Is `Optional<T>`: Handling the Not-Found Case Too

Both methods return `Optional<T>`. This is a type-level signal that the result **may be absent**:

```java
import java.util.Arrays;
import java.util.Optional;

Optional<String> found = Arrays.asList("A", "BB", "CCC").stream()
    .filter(text -> text.length() > 10)
    .findFirst();

System.out.println(found.isPresent());       // false
System.out.println(found.orElse("None")); // None
```

Common ways to handle it:

| Usage | Meaning |
| --- | --- |
| `ifPresent(action)` | Perform an action only if an element is present. |
| `orElse(defaultValue)` | Return a precomputed fallback value when empty. |
| `orElseGet(supplier)` | Compute a fallback value **on demand** via a `Supplier`. |
| `orElseThrow(...)` | Throw an explicit error if a mandatory element is missing. |
| `map(transform)` | Transform the value inside `Optional` if it exists. |

Example handling the result without blindly calling `get()`:

```java
import java.util.Arrays;
import java.util.Optional;

Optional<String> task = Arrays.asList("open", "closed", "pending").stream()
    .filter(value -> value.startsWith("pend"))
    .findFirst();

String label = task.map(String::toUpperCase)
    .orElseGet(() -> "NO_TASK");

System.out.println(label); // PENDING
```

`Optional.get()` throws `NoSuchElementException` if empty. Only use it when you are certain a value exists or have already checked `isPresent()`; in most situations, `orElse`, `orElseThrow`, and `ifPresent` express intent more clearly.

**Do not use a `null` element as the result value.** If the element selected by either `find*` operation is `null`, they throw `NullPointerException`. When a source might contain `null`, filter first:

```java
import java.util.Arrays;
import java.util.Objects;

String value = Arrays.asList(null, "A", "B").stream()
    .filter(Objects::nonNull)
    .findFirst()
    .orElse("n/a");

System.out.println(value); // A
```

### Versions for Primitive Streams

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt firstLarge = IntStream.of(5, 8, 13, 21)
    .filter(n -> n > 10)
    .findFirst();

System.out.println(firstLarge.orElse(-1)); // 13
```

`OptionalInt` keeps the integer value within the primitive API, avoiding boxing to `Integer`. For floating-point and long integers, use `DoubleStream.findFirst`/`findAny` or `LongStream.findFirst`/`findAny` respectively.

## 4. Why Are These Called Short-Circuiting Terminal Operations?

A Stream pipeline consists of a source, lazy intermediate steps, and a terminal operation. `findFirst` or `findAny` can determine the result **before traversing the entire source**.

```java
import java.util.Arrays;

String firstEvenText = Arrays.asList(3, 7, 8, 10, 12).stream()
    .filter(n -> n % 2 == 0)
    .map(n -> "even-" + n)
    .findFirst()
    .orElse("none");

System.out.println(firstEvenText); // even-8
```

When running sequentially on an ordered list, this simple pipeline can finish after encountering `8`; results from `10` or `12` are not needed. However, **short-circuiting does not promise a fixed number of lambda invocations**: the JVM is allowed to optimize the pipeline; in parallel mode, some later elements may already have been processed by the time a result is chosen.

Therefore, writing `peek(System.out::println)` to “confirm every element was processed” is wrong. Do not use `filter`, `map`, or `peek` to execute mandatory side effects on *all* elements such as sending payment requests, recording ledger entries, or updating external counters.

### When Must Many Elements Be Traversed?

`findFirst()` does not automatically have O(1) complexity. If you need the first matching element and it lies very late, the pipeline has to inspect preceding elements. If no element matches in a finite source, the pipeline must exhaust the entire source:

```java
import java.util.stream.IntStream;

int number = IntStream.rangeClosed(1, 1_000_000)
    .filter(n -> n == 999_999)
    .findFirst()
    .orElse(-1);

System.out.println(number); // 999999
```

`sorted()` is also a **stateful** intermediate operation, typically having to read the entire finite source before returning the first element of the sorted result. `distinct()`, `skip()`, `limit()`, and operations preserving encounter order can also affect how many elements must be traversed. Placing `limit` before or after `filter` can even change the **meaning**:

```java
import java.util.Arrays;

Integer a = Arrays.asList(1, 3, 8, 10).stream()
    .limit(2).filter(n -> n % 2 == 0)
    .findFirst().orElse(-1);

Integer b = Arrays.asList(1, 3, 8, 10).stream()
    .filter(n -> n % 2 == 0).limit(2)
    .findFirst().orElse(-1);

System.out.println(a); // -1: only inspects the first two elements 1, 3
System.out.println(b); // 8: takes at most two even elements
```

## 5. Infinite Streams and Search Conditions

`Stream.iterate` and `Stream.generate` can create unbounded sources. Both `find*` operations **can stop early**, but are not guaranteed to find a result. The deciding factor is whether a matching element actually appears at a finite position and whether preceding steps can supply that element.

```java
import java.util.stream.Stream;

long found = Stream.iterate(1L, n -> n + 1)
    .filter(n -> n % 7 == 0)
    .findFirst()
    .orElse(-1L);

System.out.println(found); // 7
```

Conversely, the snippet below **should not be executed** because it has no terminating condition:

```java
// DO NOT RUN:
// Stream.generate(() -> 0)
//     .filter(n -> n == 1)
//     .findFirst();
```

If you need to cap the number of source elements inspected, place `limit(n)` in the right position before `filter`:

```java
import java.util.stream.IntStream;

int result = IntStream.iterate(0, n -> n + 2)
    .limit(100)
    .filter(n -> n > 500)
    .findFirst()
    .orElse(-1);

System.out.println(result); // -1, since the first 100 numbers are 0, 2, ..., 198
```

Note: `filter(...).limit(100)` is not equivalent to `limit(100).filter(...)`. If an infinite source never satisfies `filter`, the first version may **never terminate** because it can never produce 100 post-filter elements. With infinite sources, also avoid placing `sorted` before `findFirst` unless the input to be sorted is bounded.

## 6. `findFirst` and `findAny` in Parallel Processing

The sharpest difference appears with `parallelStream()` or `parallel()`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

List<Integer> numbers = Arrays.asList(10, 20, 30, 40, 50, 60);

Optional<Integer> first = numbers.parallelStream()
    .filter(n -> n >= 20)
    .findFirst();

Optional<Integer> any = numbers.parallelStream()
    .filter(n -> n >= 20)
    .findAny();

System.out.println(first.orElse(-1)); // Always 20
System.out.println(any.orElse(-1));   // May be 20, 30, 40, 50, or 60
```

With a source that has encounter order, `findFirst` must return the earliest matching element in that order, even if another thread finishes processing a later element sooner. This may require additional coordination among branches. `findAny` permits selecting a matching element from any branch and thus often opens up optimization opportunities.

**Do not infer from this example that `findAny` will always return different results or always run faster.** In some environments and data sizes, it may return the same element across multiple runs or be slower due to parallel setup overhead. Only judge performance gains by measuring on realistic workloads.

| Need | Suitable Choice | Why |
| --- | --- | --- |
| Get the earliest valid record in list order | `findFirst` | Order is part of the requirement. |
| Get any error record for investigation | `findAny` | Only one result is needed; order does not matter. |
| Get the event with the earliest timestamp | `min(comparator)` if source is not sorted by time; `findFirst` if already sorted | “First” must be based on business order. |
| Only check whether an error record exists | `anyMatch(predicate)` | Returns `boolean` directly instead of creating `Optional`. |
| Need all matching records | `filter(...).collect(...)` | Do not use `find*` when you need the complete result set. |

### What Does `unordered()` Mean?

On an ordered source, `unordered()` allows dropping the obligation to preserve encounter order in subsequent steps. In a parallel pipeline with `findAny`, the ordering constraint is already unnecessary for selecting a result; hence adding `unordered()` does not necessarily bring a noticeable improvement. Conversely, `unordered().findFirst()` destroys the “first” meaning of the original source.

Do not use `unordered()` merely as a speed trick if business requirements demand an order-stable result.

## 7. Business Example: Selecting an Event to Process

Suppose a list of messages arrives in order of receipt. When you need the **earliest error message**, use `findFirst`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

public class EventSelection {
    public static void main(String[] args) {
        List<String> events = Arrays.asList(
            "INFO: started",
            "WARN: retry",
            "ERROR: timeout",
            "ERROR: connection reset"
        );

        Optional<String> firstError = events.stream()
            .filter(message -> message.startsWith("ERROR:"))
            .findFirst();

        firstError.ifPresent(System.out::println);
        // ERROR: timeout
    }
}
```

If the requirement is merely “find any error to display a sample”, you can switch the terminal operation to `findAny`. In that case, **do not rely on** always receiving `ERROR: timeout`, especially if switching to a parallel stream later.

With input data from a `HashSet`, calling `findFirst` does not establish a reliable chronological order. To find the earliest by timestamp, carry the timestamp on each element and use `min(comparator)`, or sort by timestamp before calling `findFirst`.

### Searching Large Files and Managing Resources

Streams obtained from `Files.lines` can hold I/O resources. Therefore, even though `findFirst` stops early upon seeing a matching line, you still must **close the stream**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

public class FindInLog {
    public static Optional<String> firstError(Path file) throws IOException {
        try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
            return lines.filter(line -> line.startsWith("ERROR:"))
                .findFirst();
        }
    }
}
```

Terminal operations **do not automatically close** all streams. `try-with-resources` ensures the resource is closed when a result is found, when nothing matches, and when an exception occurs.

## 8. Common Misconceptions

| Misconception | Problem | Correct Practice |
| --- | --- | --- |
| “`findFirst` always returns the smallest element.” | Encounter order is not the same as ascending value order. | Use `min` or sort by the desired criterion. |
| “`findAny` is always the first element when run sequentially.” | The API does not guarantee that selection behavior. | Use `findFirst` if order matters. |
| “`findFirst` on `HashSet` produces a stable result.” | The source has no guaranteed encounter order. | Use an ordered source or sort with an explicit comparator. |
| Calling `optional.get()` immediately after `find*`. | May throw `NoSuchElementException`. | Use `orElse`, `ifPresent`, or `orElseThrow`. |
| Assuming `findAny` is always faster. | Cost depends on source, data, filter condition, parallelism, and ordering. | Benchmark on the actual workload. |
| Using `peek` to process every element before `find*`. | Short-circuiting pipelines may skip remaining elements. | Separate mandatory side-effect processing from the search step. |
| Calling `count()` or `findAny()` next on the same stream. | Stream is already consumed after a terminal operation. | Create a new stream from the source if another operation is needed. |
| Using `find*` with `null` elements. | Selecting a `null` element throws `NullPointerException`. | Filter with `Objects::nonNull` when data allows `null`. |
| Assuming `findFirst` always stops quickly on infinite streams. | It may never encounter a matching element. | Set bounds and design clear terminating conditions. |

A `Stream` can only be operated on by one terminal operation. Example:

```java
import java.util.stream.Stream;

Stream<Integer> stream = Stream.of(1, 2, 3);
stream.findFirst();

// Invalid: the stream has already been operated upon.
// stream.findAny(); // IllegalStateException

// If you need to search again, create a new pipeline from the source:
System.out.println(Stream.of(1, 2, 3).findAny().orElse(-1));
```

## 9. Selection Checklist and Self-Check

When designing searches with the Java Stream API, review:

1. **Do you want to check existence or retrieve an element?** To check existence only, choose `anyMatch`; if you need an element, consider `findFirst` or `findAny`.
2. **How is “first” defined?** Determine whether the source has encounter order; if you need the smallest or latest value, usually use a comparator/`min`/`max`.
3. **Do you actually need a deterministic element?** If any match is fine, `findAny` fits; if the result must be order-stable, use `findFirst`.
4. **Can the pipeline terminate?** Consider source length, position of matching elements, `sorted`, `filter`, `limit`, and stateful intermediate steps.
5. **How is an empty result handled?** Use `Optional` APIs according to business semantics; do not call `get()` without ensuring presence.
6. **Will it run in parallel?** Keep lambdas free of mutable external state, avoid assuming call counts or execution order, and measure performance when needed.
7. **Does the source hold resources?** For files and some I/O sources, use `try-with-resources`.

### Practice Exercises

**Exercise 1.** Given `[7, 3, 12, 18, 4]`, write a pipeline to find the **first even number**. The right answer in encounter order is `12`, not `4`. Then use `min` to find the **smallest even number** and compare the two results.

**Exercise 2.** Create a `List<String>` containing several error codes. Write `findFirst` to retrieve the first error in list order and `parallelStream().findAny()` to retrieve any error. Verify that the element returned by `findAny` always matches the condition, but **do not write a test requiring it to always be the exact same code**.

**Exercise 3.** Use `IntStream.iterate(0, n -> n + 2)` to create an infinite sequence of even numbers, apply `limit(100)`, filter numbers greater than `500`, and call `findFirst`. Explain why the result is empty. Try changing `limit(100)` to `limit(300)` and predict the result.

**Exercise 4.** Given a list that may contain `null`, write a pipeline that removes `null`, filters non-empty strings, and retrieves the first valid string. Handle the result with `orElse` instead of `Optional.get()`.

**Key Takeaway:** `findFirst` is the choice when **order matters**; `findAny` fits when **any matching element is acceptable**. Both can short-circuit and return `Optional`, while early stopping, result determinism, and actual performance depend on the source, encounter order, pipeline, and execution mode.
