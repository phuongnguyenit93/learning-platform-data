# Choosing a Terminal Operation by Goal and Early-Stopping Needs

In the Java Stream API, intermediate steps such as `filter`, `map`, and `sorted` mainly describe **how to process** elements; the **terminal operation** determines **what kind of result** the program needs. Choosing the right terminal operation makes code state its intent clearly, avoids unnecessary data traversal, and controls when a pipeline can stop early.

This lesson belongs to the **Traversal, Search, and Matching** chapter of the **JAVA_STREAM_API** module. It connects the lazy pipeline model to `reduce` and `collect` aggregations, grouping Collectors, finite/infinite sources, parallel processing, and performance limits. The focus is a practical question: *Do you want to know if a matching element exists, get one element, get all elements, count, compute a value, or perform an action?* Each goal leads to a different terminal operation.

## 1. The Terminal Operation Determines Consumption Requirements

A typical pipeline consists of **source → zero or more intermediate operations → terminal operation**:

```java
List<String> names = Arrays.asList("An", "Binh", "Chi", "Dung");

boolean hasLongName = names.stream()            // Source
    .map(String::trim)                           // Intermediate, lazy
    .filter(name -> name.length() >= 4)         // Intermediate, lazy
    .anyMatch(name -> name.startsWith("B"));     // Terminal: asks yes or no only

System.out.println(hasLongName); // true
```

`anyMatch` does not need to build a list of names matching both conditions. As soon as `Binh` is found, the terminal has enough proof to return `true`. In a sequential pipeline, the remaining elements do not need to be inspected. This is an example of **early stopping** (*short-circuiting*).

Distinguish two ideas:

- **Laziness:** intermediate operations generally do not traverse the source when they are attached to the pipeline.
- **Short-circuiting:** once the terminal starts consuming, certain operations can return a result **before reading the entire source**.

Not every terminal short-circuits. `collect(toList())` must collect every remaining element; `sum()` must add every value emitted by the pipeline. Conversely, `findFirst`, `findAny`, and the three `match` operations can finish after part of the source when conditions align.

> **Terminology note:** `limit` and `takeWhile` are **short-circuiting intermediate operations**; they are not terminal operations. They can help a terminal that needs all downstream data finish on a very long or infinite initial source.

## 2. Quick Selection Table by Goal

| Goal | Terminal Operation to Choose | Return Type | Can Short-Circuit? |
| --- | --- | --- | --- |
| Does **at least one** element satisfy the condition? | `anyMatch(predicate)` | `boolean` | Yes, upon encountering a matching element |
| Do **all** elements satisfy the condition? | `allMatch(predicate)` | `boolean` | Yes, upon encountering a failing element |
| Do **no** elements satisfy the condition? | `noneMatch(predicate)` | `boolean` | Yes, upon encountering a matching element |
| Get the **first element** in source order? | `findFirst()` | `Optional<T>` | Yes, once the first element is determined |
| Need **any single** matching element? | `findAny()` | `Optional<T>` | Yes, once one element is found |
| Need **all** elements after filtering/transforming? | `collect(collector)`; or `toList()` from Java 16 | Collection or collected value | Typically must inspect all output |
| Need to know **how many** elements? | `count()` | `long` | Can optimize using known size; not a search-short-circuiting terminal |
| Need the **smallest/largest**? | `min(comparator)` / `max(comparator)` | `Optional<T>` | Typically must inspect all output |
| Need the **sum/accumulation of a value**? | `sum()` on primitive Stream, `reduce(...)` | Number, value, or `Optional` | Typically must inspect all output |
| Need **grouping, statistics, target structure**? | `collect(Collectors.groupingBy(...))`, `collect(...)` | `Map`, `List`, etc. | Typically must inspect all output |
| Need to **perform an action** on elements? | `forEach(action)` / `forEachOrdered(action)` | `void` | Typically must traverse all output |

**Selection rule:** If the result only needs a **yes/no answer**, prefer `anyMatch`, `allMatch`, or `noneMatch` over `filter(...).collect(...).isEmpty()`. If the result needs **one element**, prefer `findFirst` or `findAny` over collecting the whole list just to take its first item.

## 3. `anyMatch`, `allMatch`, and `noneMatch`: Three Different Logical Questions

Matching operations take a `Predicate<T>` and return a `boolean`:

```java
List<Integer> scores = Arrays.asList(45, 68, 82, 91);

boolean hasExcellent = scores.stream()
    .anyMatch(score -> score >= 90); // true: 91 exists

boolean allPassed = scores.stream()
    .allMatch(score -> score >= 50); // false: 45 fails

boolean noneNegative = scores.stream()
    .noneMatch(score -> score < 0); // true: no negative numbers
```

| Operation | When can it decide immediately? | If exhausted without hitting a stopping condition |
| --- | --- | --- |
| `anyMatch(p)` | Sees **one true element** → `true` | `false` |
| `allMatch(p)` | Sees **one false element** → `false` | `true` |
| `noneMatch(p)` | Sees **one true element** → `false` | `true` |

On an **empty Stream**, there are no elements to test:

```java
boolean any = Stream.<Integer>empty()
    .anyMatch(n -> n > 0);  // false

boolean all = Stream.<Integer>empty()
    .allMatch(n -> n > 0);  // true

boolean none = Stream.<Integer>empty()
    .noneMatch(n -> n > 0); // true
```

`allMatch` returns `true` on an empty Stream because **there is no counterexample**; `noneMatch` also returns `true` because no element matches the predicate. This is a logical rule (*vacuous truth*), not a bug.

**Common mistake:** using `allMatch` to check “list is non-empty and all are valid”. `allMatch` alone **cannot check non-emptiness**. If the source is a `List`, combine `!list.isEmpty()` and `list.stream().allMatch(...)`; if the source is a single-use Stream, you need a processing design that checks emptiness and the condition together, such as gathering the information with a suitable collector.

## 4. `findFirst` and `findAny`: Ordering Requirements Determine the Choice

Both search operations return `Optional<T>`, because a result may not exist.

```java
List<String> employees = Arrays.asList("An", "Binh", "Chi", "Duc");

Optional<String> firstMatching = employees.stream()
    .filter(name -> name.length() >= 3)
    .findFirst();
// Optional[Binh]

Optional<String> anyMatching = employees.parallelStream()
    .filter(name -> name.length() >= 3)
    .findAny();
// May be Binh, Chi, or Duc; do not rely on a specific choice.
```

**Choose `findFirst`** when the requirement is “the first record in a meaningful order”: earliest transaction, first error in a sorted set, or first record of a `List`. `findFirst` respects **encounter order** if the source is ordered.

**Choose `findAny`** when you just need **any matching element** to process next. It is allowed to disregard order, especially in parallel pipelines, which can yield performance benefits.

**Do not infer “first” on a source without encounter order.** For example, `HashSet.stream()` promises no traversal order. If you want the element with the smallest value, it is better to use `min(comparator)` instead of assuming `findFirst` returns the minimum element.

### Handling `Optional` Safely

```java
String result = employees.stream()
    .filter(name -> name.startsWith("Z"))
    .findFirst()
    .orElse("Not found");

System.out.println(result); // Not found
```

Common ways to read an `Optional`:

- `isPresent()` and `get()` are appropriate only when presence is guaranteed; calling `get()` on `Optional.empty()` throws `NoSuchElementException`.
- `orElse(defaultValue)` provides a fallback value; the `defaultValue` expression is evaluated before the method call.
- `orElseGet(supplier)` computes the fallback value only when the `Optional` is actually empty.
- `orElseThrow(...)` intentionally signals an error when no result is found.

A Stream containing `null` elements can cause `NullPointerException` if `findFirst` or `findAny` selects a `null` element (because `Optional` does not represent a present `null` value). If data may contain `null`, filter first:

```java
Optional<String> first = Arrays.asList(null, "Binh", "Chi")
    .stream()
    .filter(Objects::nonNull)
    .findFirst(); // Optional[Binh]
```

## 5. When All Results Are Needed: `collect`, `count`, `min`, `max`, and `reduce`

`findFirst` or `anyMatch` is unsuitable if the goal is outputting a **complete list**. Choose a terminal representing the result the user needs:

```java
List<Integer> prices = Arrays.asList(40, 120, 85, 200, 120);

List<Integer> expensive = prices.stream()
    .filter(price -> price >= 100)
    .collect(Collectors.toList()); // [120, 200, 120]

long expensiveCount = prices.stream()
    .filter(price -> price >= 100)
    .count(); // 3

Optional<Integer> highest = prices.stream()
    .max(Integer::compareTo); // Optional[200]

int total = prices.stream()
    .mapToInt(Integer::intValue)
    .sum(); // 565
```

Just to **count**, use `count()` instead of `collect(toList()).size()`: the latter allocates an unnecessary data structure. To **sum numbers**, `mapToInt(...).sum()` usually expresses intent clearer than `reduce(0, Integer::sum)` while avoiding boxing/unboxing during summation.

When a custom reduction rule is needed:

```java
int sumOfSquares = prices.stream()
    .map(price -> price * price)
    .reduce(0, Integer::sum);
```

`reduce` must use a combining operation that obeys the Stream contract. When running in parallel, the accumulator must be **associative**, with a valid **identity** value. Order-dependent operations like subtraction cannot simply be plugged into a parallel reduction expecting sequential-loop semantics.

### `collect` to Build Structures or Complex Aggregations

```java
Map<Integer, Long> countsByLength = Arrays.asList(
        "An", "Binh", "Chi", "Dung", "Minh")
    .stream()
    .collect(Collectors.groupingBy(
        String::length,
        Collectors.counting()
    ));
// {2=1, 3=1, 4=3} (do not rely on Map key iteration order).
```

`collect` suits building lists, sets, groups, or statistical summaries. Java 16 introduced `stream.toList()`, returning an **unmodifiable** List. `Collectors.toList()` promises neither a specific List implementation nor mutability. When you need a target that supports adding/removing, use `collect(Collectors.toCollection(ArrayList::new))`.

**Important note on early stopping:** most of the aggregations above require all output elements to determine their result. `count()` can be an **optimization** exception: if the source has a known size and intermediate steps do not change element counts, Java can return the result without traversing individual elements. Thus, even with a terminal operation, never rely on side effects inside `peek` or `map` to ensure every lambda ran.

## 6. `forEach`/`forEachOrdered`: Use When the Goal Is an Action

`forEach` and `forEachOrdered` return `void`: they are meant for performing actions at the consumption boundary, such as printing output, writing to a managed sink, or passing each element to another component.

```java
List<String> messages = Arrays.asList("A", "B", "C");

messages.stream().forEach(System.out::println);
// With an ordered sequential Stream: A, B, C.

messages.parallelStream().forEach(System.out::println);
// Print order is not guaranteed.

messages.parallelStream().forEachOrdered(System.out::println);
// Preserves encounter order: A, B, C.
```

`forEachOrdered` preserves **action execution order** when the Stream has encounter order, though it may add coordination overhead. It does not convert all preceding intermediate operations into sequential processing.

If you need to **build a list**, use `collect` rather than mutating an external List from `forEach`:

```java
List<Integer> input = Arrays.asList(1, 2, 3, 4);

// Unsafe if used on parallelStream:
// List<Integer> shared = new ArrayList<>();
// input.parallelStream().forEach(n -> shared.add(n * 2));

List<Integer> doubled = input.parallelStream()
    .map(n -> n * 2)
    .collect(Collectors.toList()); // [2, 4, 6, 8]
```

`ArrayList` does not support concurrent writes from multiple threads that way. Meanwhile, `peek` is an **intermediate** operation, not a tool guaranteeing every logging/auditing action will execute. For code with side effects, design thread safety, failure handling, and execution order properly.

## 7. Short-Circuiting Depends on Everything Before the Terminal

A short-circuiting terminal **does not guarantee** always returning quickly. Inspect the steps preceding it.

```java
int firstEven = IntStream.rangeClosed(1, 1_000_000)
    .filter(n -> n % 2 == 0)
    .findFirst()
    .orElse(-1); // 2
```

On an ordered sequential source, `findFirst` only needs to advance to `2`. However, if you add a step that must consume the entire source before emitting results:

```java
int smallest = IntStream.rangeClosed(1, 1_000_000)
    .sorted()
    .findFirst()
    .orElse(-1); // 1
```

With an ordinary `sorted` step on a source not known to be sorted, traversing and sorting typically require the entire input. The example above uses `IntStream.rangeClosed`, which is inherently sorted; an implementation might exploit that source property to optimize. **Do not use this example alone to benchmark sorting cost.** The takeaway is that having `findFirst` at the end does not erase the cost of a stateful step before it.

Other upstream steps to examine:

- `filter(p)`: early stopping helps only when a matching element appears. If no matching element ever appears in an infinite source, `filter(p).findFirst()` does not terminate.
- `distinct()`: may need to track seen values; combining with `limit(n)` stops only once `n` distinct values are found.
- `sorted()`: typically a blocking step needing the entire input before emitting sorted elements; especially dangerous with infinite sources.
- `limit(n)`: an intermediate step letting downstream terminals that need all remaining elements process at most `n` elements **after the limit**, provided upstream steps supply enough data.
- `takeWhile(p)` (Java 9+): on a source with encounter order, stops at the first element failing `p`; on an infinite source where `p` is always true, it will not help termination.

| Pipeline | Can return a result? | Explanation |
| --- | --- | --- |
| `Stream.generate(() -> "x").findAny()` | Yes | Source can supply one element immediately. |
| `IntStream.iterate(1, n -> n + 1).anyMatch(n -> n == 5)` | Yes | Encounters value `5` after finitely many steps. |
| `Stream.generate(() -> 1).allMatch(n -> n == 1)` | Does not terminate via normal traversal | No counterexample appears and the source has no endpoint. |
| `Stream.generate(() -> 1).anyMatch(n -> n == 2)` | Does not terminate via normal traversal | No element making the predicate true appears. |
| `Stream.generate(() -> 1).limit(5).count()` | Yes | Pipeline is bounded; terminal may also optimize when size is known. |
| `Stream.generate(() -> 1).distinct().limit(2).count()` | Does not terminate via normal traversal | Only one distinct value exists, so two elements are never reached. |

When working with infinite sources, only run full-consumption terminals like `collect`, `count`, `sum`, or `reduce` **after ensuring the pipeline has a stopping point**. Even so, `limit(10)` is not a timeout: if a source blocks on fetching or never lets enough elements pass filters, the pipeline can still wait indefinitely.

## 8. When Running in Parallel: Performance, Ordering, and Side Effects

Parallel Streams can process multiple elements concurrently. `anyMatch`/`allMatch`/`noneMatch` retain the same result contract as sequential mode, though multiple predicates may have been invoked on different elements before short-circuiting halts work. **There is no guarantee** each lambda is invoked only up to the exact deciding element.

```java
List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5, 6);

boolean hasEven = numbers.parallelStream()
    .anyMatch(n -> n % 2 == 0); // true

Optional<Integer> firstEven = numbers.parallelStream()
    .filter(n -> n % 2 == 0)
    .findFirst(); // Optional[2]

Optional<Integer> anyEven = numbers.parallelStream()
    .filter(n -> n % 2 == 0)
    .findAny(); // One of 2, 4, 6
```

On an ordered `List`, `findFirst` must preserve the concept of “first”; `findAny` may return any matching element, giving parallel execution more freedom to optimize. `forEachOrdered` preserves action order, whereas `forEach` does not.

Key principles:

1. Lambdas in a pipeline should **never mutate shared state** and must not depend on thread scheduling.
2. Never call `unordered()` if business output requires “first”, such as the earliest element by timestamp.
3. Do not assume `parallelStream()` is faster: splitting overhead, task cancellation, ordering constraints, and stateful steps can outweigh the gains.
4. When performance matters, benchmark on representative data and environments; for very small lists, sequential is usually simpler.

## 9. Complete Example: Choosing the Right Terminal for Each Requirement

The snippet below runs on Java 8+, reuses the same `List` source, and creates **a fresh Stream for each query**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

public class TerminalChoiceDemo {
    public static void main(String[] args) {
        List<String> products = Arrays.asList(
            "pen", "book", "ruler", "eraser"
        );

        // Is there at least one name of 5 or more characters?
        boolean hasLongName = products.stream()
            .anyMatch(name -> name.length() >= 5);

        // Are all names non-empty?
        boolean allNamed = products.stream()
            .allMatch(name -> !name.isEmpty());

        // Do no names contain digits?
        boolean noDigit = products.stream()
            .noneMatch(name -> name.matches(".*\\d.*"));

        // First name of 5 or more characters in List order.
        Optional<String> firstLong = products.stream()
            .filter(name -> name.length() >= 5)
            .findFirst();

        // How many names are longer than 3 characters?
        long count = products.stream()
            .filter(name -> name.length() > 3)
            .count();

        // Collect all names longer than 3 characters, preserving List order.
        List<String> selected = products.stream()
            .filter(name -> name.length() > 3)
            .collect(Collectors.toList());

        // Total number of characters across all names.
        int totalLength = products.stream()
            .mapToInt(String::length)
            .sum();

        System.out.println("Has long name: " + hasLongName);
        System.out.println("All named: " + allNamed);
        System.out.println("No digits: " + noDigit);
        System.out.println("First long name: " + firstLong.orElse("None"));
        System.out.println("Names > 3 chars: " + count);
        System.out.println("Selected names: " + selected);
        System.out.println("Total chars: " + totalLength);
    }
}
```

Output:

```text
Has long name: true
All named: true
No digits: true
First long name: ruler
Names > 3 chars: 3
Selected names: [book, ruler, eraser]
Total chars: 18
```

Each terminal returns the exact data type needed: `boolean` for logical queries, `Optional` for searches, `long` for counting, `List` for collection, and `int` for summation.

## 10. Common Misconceptions

| Misconception | What to Do Instead |
| --- | --- |
| Using `filter(p).collect(toList()).isEmpty()` just to ask yes/no | Use `anyMatch(p)` (or `noneMatch(p)` for a negative question) |
| Using `filter(p).count() > 0` to test for a matching element | Use `anyMatch(p)` to enable early stopping |
| Using `findAny` and treating the result as the first element | Use `findFirst` on a source with appropriate encounter order |
| Using `findFirst` on `HashSet` to get the smallest value | Use `min(comparator)` or establish an explicit order |
| Expecting `allMatch` on an empty source to return `false` | Remember that `allMatch` on empty returns `true` |
| Calling `Optional.get()` without checking | Use `orElse`, `orElseGet`, or `orElseThrow` appropriately |
| Using `forEach` to add into a shared `ArrayList` in a parallel stream | Use `collect` with library-managed accumulation |
| Thinking every terminal stops early automatically | Check each terminal's contract and preceding stateful steps |
| Thinking `count()` always calls every `peek` | Never rely on side effects in intermediate steps |
| Running `allMatch` infinitely when every element matches | Add a finite bound or an achievable stopping condition |
| Reusing one Stream for multiple terminals | Create a new Stream from the source for each computation |

## 11. Self-Check Questions

**Exercise 1 — Choosing an operation.** Given one million orders, you only need to know whether **any order** exceeds 10 million VND. Choose `count() > 0`, `collect(toList()).isEmpty()`, or `anyMatch`?

```java
boolean hasLargeOrder = amounts.stream()
    .anyMatch(amount -> amount > 10_000_000L);
```

**Answer:** `anyMatch` directly expresses the existence question and can stop early upon finding one matching order. `count` must determine the post-filter count in the general case.

**Exercise 2 — Results on an empty Stream.** Predict:

```java
boolean a = Stream.<Integer>empty().anyMatch(n -> n > 0);
boolean b = Stream.<Integer>empty().allMatch(n -> n > 0);
boolean c = Stream.<Integer>empty().noneMatch(n -> n > 0);
Optional<Integer> d = Stream.<Integer>empty().findFirst();
```

**Answer:** `a = false`, `b = true`, `c = true`, `d = Optional.empty()`.

**Exercise 3 — Ordered search.** Given `List<Integer> values = Arrays.asList(9, 4, 6, 2);`, get the **first even number by List position**; when running in parallel, which terminal is needed?

```java
Optional<Integer> first = values.parallelStream()
    .filter(n -> n % 2 == 0)
    .findFirst(); // Optional[4]
```

**Answer:** `findFirst` preserves encounter order; `findAny` is allowed to return `4`, `6`, or `2`.

**Exercise 4 — Infinite source.** Does `Stream.generate(() -> 1).noneMatch(n -> n == 2)` terminate? How do you check the first 100 values?

```java
boolean noneInSample = Stream.generate(() -> 1)
    .limit(100)
    .noneMatch(n -> n == 2); // true
```

**Answer:** There is no stopping condition on the original infinite source, because `2` never appears; the terminal can never know it has traversed everything. `limit(100)` narrows the question to a finite sample.

**Exercise 5 — Collecting vs acting.** To build a `List<String>` containing uppercase names from a large `List` run in parallel, should you use `forEach` to append to a shared List or `collect`?

```java
List<String> upperNames = names.parallelStream()
    .map(String::toUpperCase)
    .collect(Collectors.toList());
```

**Answer:** Use `collect` to produce output data. Adding concurrently into an `ArrayList` from multiple threads can cause race conditions and wrong results.

## Key Takeaways

In **JAVA_STREAM_API**, start from the **business question** to choose a terminal: `anyMatch`/`allMatch`/`noneMatch` for logical answers; `findFirst`/`findAny` for a single element; `collect` for result structures; `count`, `min`/`max`, `sum`, or `reduce` for aggregations; and `forEach` when the goal is genuinely an action. Early stopping helps only when the pipeline can supply sufficient proof and is not blocked by an upstream step. When switching to parallel Streams, preserve ordering requirements, avoid shared state, and evaluate performance with real measurements.
