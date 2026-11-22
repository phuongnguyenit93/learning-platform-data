# `findFirst()` and `findAny()` in Java Stream

## 1. Goal: finding one element instead of collecting all

In the Stream API, `findFirst()` and `findAny()` are two **terminal operations** used to find one element from a stream. Both can **short-circuit**: once a result can be returned, the pipeline does not necessarily have to traverse the entire source.

For example, suppose you need to find the first product priced at 100 or more:

~~~java
record Product(String code, int price) {}

List<Product> products = List.of(
        new Product("A", 80),
        new Product("B", 120),
        new Product("C", 150));

Optional<Product> firstEligible = products.stream()
        .filter(p -> p.price() >= 100)
        .findFirst();

System.out.println(firstEligible.map(Product::code).orElse("none")); // B
~~~

`filter` decides which elements meet the condition. `findFirst` selects the **first** matching element **by encounter order** if the source has an order. The result is not a `Product` directly, but an `Optional<Product>`, because there may be no matching product.

If the requirement is simply “get **any** matching product” without caring which one, `findAny()` expresses that intent better:

~~~java
Optional<Product> anyEligible = products.stream()
        .filter(p -> p.price() >= 100)
        .findAny();
~~~

`findAny()` does not promise to return `"B"`. It may return any matching element; in many sequential runs you might *observe* the first element, but you should not rely on that as a program contract.

**Scope to master:** return types, element ordering, short-circuiting behavior, sequential and parallel execution, handling empty streams or nulls, choosing between the two operations, as well as common misconceptions when using them in a Stream pipeline.

## 2. API Signatures and Optional Results

On `java.util.stream.Stream<T>`:

~~~java
Optional<T> findFirst();
Optional<T> findAny();
~~~

The signatures take no parameters: **filtering before finding** is expressed using intermediate operations such as `filter`, `map`, `distinct`, and `sorted`.

~~~java
List<String> words = List.of("Java", "API", "Stream");

Optional<String> first = words.stream().findFirst();
Optional<String> anyLong = words.stream()
        .filter(s -> s.length() > 4)
        .findAny();
~~~

If the stream is empty, both return `Optional.empty()`. If the stream has a selected element, the result is an `Optional` containing that element. For example:

~~~java
System.out.println(Stream.<String>empty().findFirst().isEmpty()); // true
System.out.println(Stream.<String>empty().findAny().isPresent()); // false
~~~

You should not call `get()` immediately without knowing whether the Optional has a value, because `Optional.get()` can throw `NoSuchElementException`. Common patterns:

~~~java
String firstName = words.stream()
        .findFirst()
        .orElse("unknown");

words.stream()
        .findFirst()
        .ifPresent(System.out::println);

String required = words.stream()
        .findFirst()
        .orElseThrow(() -> new IllegalStateException("No name available"));
~~~

- `orElse(value)` returns the fallback value if the Optional is empty.
- `orElseGet(supplier)` invokes the supplier to produce the fallback value only when the Optional is empty, making it suitable for expensive computations.
- `ifPresent(consumer)` runs the action only when a value is present.
- `orElseThrow(...)` expresses the contract that not finding a value is a business error.

For `IntStream`, `LongStream`, and `DoubleStream`, the corresponding return types are **`OptionalInt`, `OptionalLong`, and `OptionalDouble`**:

~~~java
OptionalInt firstPositive = IntStream.of(-2, 0, 7, 9)
        .filter(n -> n > 0)
        .findFirst();

System.out.println(firstPositive.orElse(-1)); // 7
~~~

`OptionalInt` has `getAsInt()` and `orElse(int)`, unlike `Optional<Integer>`. Do not assume `IntStream.findFirst()` returns `Optional<Integer>`; the primitive API avoids intermediate boxing where possible.

## 3. Encounter order: what does “first” mean?

**Encounter order** is the element order defined by the source and pipeline. For example:

- `List`, arrays, `IntStream.range`, and `Stream.of(...)` generally have a well-defined source order.
- `HashSet` does not guarantee an element encounter order; the order observed in a given run is not a contract.
- `TreeSet` has an iteration order according to the set's comparator/ordering; a stream from it has the corresponding order.
- The `sorted` operation establishes an order according to a comparator/ordering, while `unordered()` drops the requirement to preserve encounter order for the rest of the pipeline.

With an ordered source:

~~~java
List<String> letters = List.of("C", "A", "B");

System.out.println(letters.stream()
        .findFirst().orElse("-"));         // C

System.out.println(letters.stream()
        .sorted()
        .findFirst().orElse("-"));         // A
~~~

In the example above, `findFirst` selects the first element **of the stream at the point the terminal is called**: before `sorted` it is `"C"`; after `sorted` it is `"A"`. It does not automatically find the minimum value; rather, it respects the established order.

For a `Stream` **without an encounter order**, `findFirst` has no stable, meaningful “first” to respect. By API contract, in this case it may return any element. Therefore, `findFirst()` does not turn a `HashSet` into an ordered source.

## 4. `findFirst()`: guaranteeing order when order exists

`findFirst()` has a clear meaning when you want the earliest matching element in source order.

~~~java
List<Integer> scores = List.of(40, 55, 70, 85);

Optional<Integer> firstPass = scores.stream()
        .filter(score -> score >= 60)
        .findFirst();

System.out.println(firstPass.orElse(-1)); // 70
~~~

Because `scores` is an ordered `List`, `70` is the first element that meets the condition. `85` also matches but is not selected.

### 4.1. Combining `map`, `filter`, and `findFirst`

~~~java
List<String> raw = List.of("  ", " Java ", " API ");

Optional<String> firstNonBlank = raw.stream()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .findFirst();

System.out.println(firstNonBlank.orElse("none")); // Java
~~~

Data flow:

~~~text
"  "     -> trim: ""      -> filter: drop
" Java " -> trim: "Java"  -> filter: keep -> findFirst: return "Java"
" API "  -> does not necessarily need to be processed in this sequential pipeline
~~~

`findFirst` is a terminal operation, so it returns `Optional<String>`, not `Stream<String>`. If you want to process further after finding, use Optional APIs such as `map`, `filter`, `flatMap`, or `stream`, or build a new pipeline from the source.

### 4.2. When you need the minimum value instead of the first

Do not replace `min()` with `findFirst()` on an unsorted source:

~~~java
List<Integer> values = List.of(9, 3, 5);

int first = values.stream().findFirst().orElseThrow(); // 9
int minimum = values.stream().min(Integer::compare).orElseThrow(); // 3
~~~

You could use `sorted().findFirst()` to pick the smallest element, but `sorted` typically requires processing/sorting the data and is more expensive than finding it directly with `min` when only an extremum is needed. Choose the API that accurately describes your intent.

## 5. `findAny()`: any element, with no guarantee of being first

`findAny()` is designed with intentionally **nondeterministic** semantics for element selection when multiple elements match. This allows implementations to take advantage of parallel execution or unordered sources.

~~~java
List<Integer> numbers = List.of(10, 20, 30, 40);

Optional<Integer> chosen = numbers.parallelStream()
        .filter(n -> n >= 20)
        .findAny();

boolean valid = chosen
        .map(n -> n >= 20)
        .orElse(false);

System.out.println(valid); // true
~~~

In this program, you should not hardcode expectations of printing `20`, `30`, or `40`, because which element is chosen is not guaranteed. We check the required property instead: any present value must satisfy the filter condition.

`findAny()` is **not synonymous with** uniformly distributed random selection. There is no contract regarding probability, alternation order, diversity, or returning a different element on each call. The same data and runtime may repeatedly return the same value.

Even on a **sequential stream with an encounter order**, `findAny` still does not guarantee selecting the first element. Many implementations may behave like `findFirst` in simple cases, but code must not rely on that observed behavior.

### 5.1. When there is only one candidate, the result is deterministic

~~~java
List<String> words = List.of("apple", "key", "banana");

String found = words.stream()
        .filter("key"::equals)
        .findAny()
        .orElse("missing");

System.out.println(found); // key
~~~

There is only one matching element, so `findAny`, if it completes successfully with a value, will select `"key"`. This is an example with stable printed output while still using the “any” semantics properly.

## 6. Short-circuiting and lazy evaluation

Both `findFirst` and `findAny` are **short-circuit terminal operations**. Once the result can be determined, they do not require processing all source elements.

Sequential example:

~~~java
List<String> items = List.of("no", "yes", "later");

Optional<String> found = items.stream()
        .filter("yes"::equals)
        .findFirst();

System.out.println(found.orElse("-")); // yes
~~~

Logically, the sequential pipeline can stop after finding `"yes"`. The element `"later"` does not need to be inspected to decide the result. However, distinguish **result semantics** from **guarantees on callback invocation counts**: the API does not allow relying on side effects in intermediate operations to determine the correctness of the entire program.

In a parallel pipeline, some workers may already have processed or be processing other elements before the terminal selects a result. Therefore, even though the terminal short-circuits logically, you must not assume:

- Mappers and predicates run only once.
- Callbacks execute sequentially from left to right in all modes.
- `findAny` returns the element “processed first” in wall-clock time.
- Adding `peek` for logging will produce exactly one line.

### 6.1. Infinite streams

With infinite sources, short-circuiting is very useful:

~~~java
int firstMultipleOfSeven = IntStream.iterate(1, n -> n + 1)
        .filter(n -> n % 7 == 0)
        .findFirst()
        .orElseThrow();

System.out.println(firstMultipleOfSeven); // 7
~~~

This is a deterministic sequential example because the condition has a matching element at a finite position. However, **short-circuiting does not guarantee that every pipeline will terminate**: if an infinite stream has no elements satisfying the condition, the search may never complete. For example, `IntStream.iterate(1, n -> n + 1).filter(n -> n < 0).findFirst()` should not be used as a termination demo, because expecting it to stop has no basis.

With parallelism, infinite sources and certain stateful operations such as `sorted`, `distinct`, and `limit` can interact in complex ways; do not use “findFirst is short-circuiting” as a blanket reason to assume every combination is lightweight or will terminate.

## 7. Parallelism: the most important difference

Compare the two pipelines:

~~~java
List<Integer> values = IntStream.rangeClosed(1, 1_000)
        .boxed()
        .toList();

Optional<Integer> first = values.parallelStream()
        .filter(n -> n > 500)
        .findFirst();

Optional<Integer> any = values.parallelStream()
        .filter(n -> n > 500)
        .findAny();

System.out.println(first.orElse(-1)); // 501
System.out.println(any.isPresent());  // true
~~~

`findFirst` must return `501` because the source is an ordered list and `501` is the earliest matching element. `findAny` only has to return some number in `501..1000`, so we only print `isPresent()` in the example for deterministic stdout.

### 7.1. Why can `findAny` be advantageous for parallel execution?

To return the first element in encounter order, `findFirst` may have to coordinate across tasks to confirm that no matching element lies before a provisional result. `findAny` is allowed to accept a matching element from any branch, so it can avoid part of that ordering constraint.

This is an **optimization opportunity**, not a promise that `findAny` is always faster than `findFirst`. Performance depends on source size and characteristics, predicate cost, splittability of the source, core count, load, and coordination overhead. For small pipelines, sequential execution can be faster than parallel.

### 7.2. What does `unordered()` mean?

~~~java
Optional<Integer> result = values.parallelStream()
        .unordered()
        .filter(n -> n > 500)
        .findFirst();
~~~

`unordered()` allows the pipeline to **no longer maintain encounter order**. In that context, calling `findFirst` is no longer required to return `501`, because the stream no longer has an encounter order to base “first” on. If you genuinely only need any element, `findAny` expresses that intent more directly.

Conversely, if business logic requires “the first record by priority order,” you should not add `unordered()` as an optimization when doing so sacrifices correctness.

### 7.3. Result order and execution order are different

A parallel pipeline with an encounter order can still execute callbacks on elements in different orders. `findFirst` guarantees **the selected element respects source order**, not that the predicate is only executed from the start up to the result position and that all threads stop immediately.

Therefore, avoid using callbacks with side effects to count or record the exact number of elements checked. If you want to record data-volume metrics, use a metric design independent of the terminal's element selection.

## 8. Handling not found: Optional

If all elements are filtered out, both return an empty Optional:

~~~java
List<Integer> numbers = List.of(1, 3, 5);

Optional<Integer> even = numbers.stream()
        .filter(n -> n % 2 == 0)
        .findFirst();

System.out.println(even.isEmpty()); // true
System.out.println(even.orElse(-1)); // -1
~~~

Several appropriate patterns depending on business logic:

~~~java
// Use a simple fallback.
int number = even.orElse(0);

// Compute an expensive fallback only when needed.
int fromFallback = even.orElseGet(() -> 0);

// Not finding one is an error-handling case.
int required = even.orElseThrow(
        () -> new IllegalArgumentException("No matching element"));
~~~

The `orElseThrow` line in the example above will throw an exception because `even` is empty; do not run it in a demo program expected to produce normal stdout unless you intentionally handle the error. `orElseGet(() -> 0)` illustrates a Supplier lambda, though if the fallback is just the constant `0`, `orElse(0)` is usually clearer.

Another scenario:

~~~java
Optional<String> first = Stream.of("An", "Binh")
        .filter(s -> s.length() >= 3)
        .findFirst();

String label = first.map(String::toUpperCase).orElse("NONE");
System.out.println(label); // BINH
~~~

Here `Optional.map` runs **after** an element has already been selected. It is not `Stream.map` applied to each element before `findFirst`. Distinguish the container before the dot to understand what data remains at each stage.

## 9. Null and errors: can throw NullPointerException

An easily overlooked point: `findFirst` and `findAny` require a present result to be represented by `Optional<T>`, and `Optional` cannot hold a `null` value. Therefore, **if the selected element is null**, the find operation can throw `NullPointerException`.

~~~java
List<String> values = java.util.Arrays.asList(null, "Java");

// values.stream().findFirst(); // NullPointerException:
// the first element of the ordered List is null.
~~~

To skip nulls:

~~~java
Optional<String> firstNonNull = values.stream()
        .filter(java.util.Objects::nonNull)
        .findFirst();

System.out.println(firstNonNull.orElse("none")); // Java
~~~

With `findAny`, if the source contains nulls, you cannot assume it will “automatically skip” nulls. It may select null and fail. Handle null conditions before calling the terminal, or use a source guaranteed to be non-null.

If you want to turn **a nullable value** into a 0- or 1-element stream, Java 9+ provides `Stream.ofNullable(value)`:

~~~java
String value = null;
System.out.println(Stream.ofNullable(value).findFirst().isEmpty()); // true
~~~

`Stream.ofNullable(null)` is an empty Stream; whereas `Stream.of((String) null)` creates a Stream with one null element, and `findFirst` on it can throw an error.

Besides null errors, mappers/predicates before the terminal can throw exceptions. `findFirst` and `findAny` **do not automatically turn exceptions into Optional.empty()**. An empty Optional means no element was selected during normal completion, not “any error is ignored.”

## 10. Other easily confused operations

| Purpose | API | Result |
| --- | --- | --- |
| Get the first element by encounter order | `findFirst()` | `Optional<T>` |
| Get any matching element | `findAny()` | `Optional<T>` |
| Check if at least one element matches | `anyMatch(predicate)` | `boolean` |
| Check if all elements match | `allMatch(predicate)` | `boolean` |
| Check if no element matches | `noneMatch(predicate)` | `boolean` |
| Find the minimum/maximum element | `min(comparator)` / `max(comparator)` | `Optional<T>` |
| Take at most `n` elements | `limit(n)` | `Stream<T>` |
| Create a list of all elements | `toList()` | `List<T>` |
| Count elements | `count()` | `long` |

### 10.1. When only asking “does it exist?”, `anyMatch` is usually clearer

~~~java
List<String> users = List.of("An", "Binh", "Chi");

boolean exists = users.stream()
        .anyMatch(s -> s.startsWith("B"));

System.out.println(exists); // true
~~~

You could write:

~~~java
boolean exists = users.stream()
        .filter(s -> s.startsWith("B"))
        .findAny()
        .isPresent();
~~~

But if you only need a boolean, `anyMatch` states the goal directly. When you need the **matching object** for subsequent steps, `findFirst` or `findAny` is more appropriate.

### 10.2. `limit(1)` does not have the same result type as `findFirst()`

~~~java
Stream<String> firstAsStream = Stream.of("A", "B").limit(1);
Optional<String> firstAsOptional = Stream.of("A", "B").findFirst();
~~~

`limit(1)` is an intermediate operation returning `Stream<String>` (for further composition). `findFirst()` is a terminal returning `Optional<String>` and consumes the pipeline. Do not swap them arbitrarily if downstream code expects a different type.

### 10.3. `findFirst` does not sort automatically

~~~java
int first = Stream.of(8, 3, 5).findFirst().orElseThrow(); // 8
int min = Stream.of(8, 3, 5).min(Integer::compare).orElseThrow(); // 3
~~~

If the requirement is “first by priority order,” control the source order or sort intentionally. If the requirement is an extremum, using `min`/`max` is usually more suitable.

### 10.4. A Stream cannot be reused after a terminal operation

~~~java
Stream<String> once = Stream.of("A", "B");
String selected = once.findFirst().orElse("-");

// Do not call once.findAny() next: the stream has already been consumed.
~~~

To use two independent terminals, create **two new streams** from a reusable source (such as a `List`), or design an appropriate aggregation.

## 11. Complete Java 17+ Example and Verifiable Stdout

Save as **`FindOperationsDemo.java`**:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class FindOperationsDemo {
    record Item(String code, int price) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A", 40),
                new Item("B", 70),
                new Item("C", 90),
                new Item("D", 60));

        Optional<Item> first = items.stream()
                .filter(item -> item.price() >= 60)
                .findFirst();
        System.out.println("first=" +
                first.map(Item::code).orElse("none"));

        Optional<Item> any = items.parallelStream()
                .filter(item -> item.price() >= 60)
                .findAny();
        boolean anyEligible = any
                .map(item -> item.price() >= 60)
                .orElse(false);
        System.out.println("anyEligible=" + anyEligible);

        String singleAny = Stream.of("a", "key", "b")
                .filter("key"::equals)
                .findAny()
                .orElse("missing");
        System.out.println("singleAny=" + singleAny);

        boolean empty = Stream.<String>empty()
                .findFirst()
                .isEmpty();
        System.out.println("empty=" + empty);

        String sortedFirst = List.of("z", "a", "b")
                .stream()
                .sorted()
                .findFirst()
                .orElse("-");
        System.out.println("sortedFirst=" + sortedFirst);

        OptionalInt primitive = IntStream.of(2, 5, 8)
                .filter(n -> n > 5)
                .findFirst();
        System.out.println("primitiveFirst=" + primitive.orElse(-1));

        int firstMultipleOfSeven = IntStream.iterate(1, n -> n + 1)
                .filter(n -> n % 7 == 0)
                .findFirst()
                .orElseThrow();
        System.out.println("multipleOfSeven=" + firstMultipleOfSeven);

        boolean exists = items.stream()
                .anyMatch(item -> item.price() >= 80);
        System.out.println("exists80=" + exists);

        Optional<String> firstNonNull = Stream.of("A", "B", "C")
                .filter(s -> s.startsWith("B"))
                .findFirst();
        System.out.println("firstB=" + firstNonNull.orElse("-"));
    }
}
~~~

Compile and run:

~~~bash
javac FindOperationsDemo.java
java FindOperationsDemo
~~~

**Deterministic stdout:**

~~~text
first=B
anyEligible=true
singleAny=key
empty=true
sortedFirst=a
primitiveFirst=8
multipleOfSeven=7
exists80=true
firstB=B
~~~

Explanation:

1. `first=B` because item `B` is the first element with a price of at least 60 in the ordered list.
2. `anyEligible=true`: parallel `findAny` may select `B`, `C`, or `D`, but every candidate satisfies the condition. We intentionally do not print the selected code to avoid depending on scheduling.
3. `singleAny=key` because there is only one candidate after `filter`.
4. `empty=true` because an empty stream leads to `Optional.empty()`.
5. `sortedFirst=a` because `sorted()` establishes a new order before finding.
6. `primitiveFirst=8` gets an `OptionalInt` from `IntStream`; 8 is the only candidate greater than 5.
7. `multipleOfSeven=7` illustrates a short-circuit terminal on a stream generated with `iterate`, given a finite solution exists.
8. `exists80=true` illustrates using `anyMatch` when only a boolean is needed.
9. `firstB=B` shows filtering and finding the first element by encounter order.

There are no external dependencies; the example uses JDK 17+ and avoids printing nondeterministic selection details from `parallelStream().findAny()`.

## 12. When to use `findFirst` and when to use `findAny`?

**Use `findFirst`** when order has business meaning, such as:

- The first record by timestamp, priority order, or an established sort order.
- A rule to “pick the earliest matching candidate.”
- A UI that needs reproducible, stable selection across runs on the same ordered source.

~~~java
Optional<String> preferred = List.of("basic", "pro", "enterprise")
        .stream()
        .filter(s -> !s.equals("basic"))
        .findFirst();

// preferred contains "pro".
~~~

**Use `findAny`** when you only need one valid candidate and there is no priority rule on order; this is especially sensible with parallel streams or sources that inherently have no encounter order.

~~~java
Optional<Integer> anyEven = List.of(1, 2, 3, 4)
        .parallelStream()
        .filter(n -> n % 2 == 0)
        .findAny();

// Contract: may be 2 or 4, no specific choice.
~~~

If business logic genuinely requires a “random” result, use an explicit random mechanism with the desired distribution; `findAny` is not a random selection API.

If the source is a `HashSet` and you need a meaningful “first element,” define a comparator or switch to an ordered structure first. If adding `sorted`, weigh the cost, as sorting everything just to take one extremum is often unnecessary.

## 13. Common Mistakes

| Mistake | Why it is wrong | How to handle it |
| --- | --- | --- |
| Assuming `findAny` always returns the first element on a sequential stream | The API does not promise this | Use `findFirst` when encounter order is needed |
| Assuming `findFirst` always gives the same result on a `HashSet` | The source has no guaranteed encounter order | Choose an ordered source or sort explicitly |
| Printing a specific value from parallel `findAny` as expected output | The choice may vary with execution scheduling | Verify properties of the returned element |
| Calling `optional.get()` when no value is present | Throws `NoSuchElementException` | Use `orElse`/`orElseThrow`/`ifPresent` appropriately |
| Treating an empty Optional as a swallowed exception | Errors in callbacks do not become Optional.empty | Handle exceptions according to their own contract |
| Assuming a `null` result is safely wrapped by Optional | Selecting a null element causes `NullPointerException` | Filter out nulls or normalize data |
| Placing required side effects in `filter`/`map` then calling `findFirst` | The pipeline may short-circuit; parallel may process multiple branches | Avoid designing side effects that depend on callback call counts |
| Using `findFirst` to get the min of an unsorted source | “First” is different from “smallest” | Use `min` or sort according to business logic |
| Using `findAny().isPresent()` when only checking a condition | Valid but more verbose and less direct in intent | Use `anyMatch(predicate)` |
| Calling a second terminal on the same Stream | The Stream has already been consumed | Create a new Stream from the source |
| Thinking short-circuit guarantees completion on an infinite stream | There may be no element matching the condition | Ensure a stopping condition, use `limit` when appropriate |
| Using `unordered()` and still expecting `findFirst` to return the priority element | The encounter order constraint has been dropped | Keep an ordered source and use `findFirst` |

## 14. Self-Check Exercises

**Question 1.** Given `List.of(4, 8, 12)`, what does `stream().filter(n -> n > 5).findFirst()` return?

**Answer:** `Optional[8]`. The list is ordered and 8 is the first element satisfying the condition.

**Question 2.** With the same list, is `parallelStream().filter(n -> n > 5).findAny()` required to return 8?

**Answer:** No. It may return 8 or 12; the only constraint is that the selected element satisfies the predicate.

**Question 3.** Why is `findFirst` on an unordered `Set` not synonymous with “the smallest element”?

**Answer:** A Set does not guarantee an encounter order; finding the first is not comparing values. If you need the smallest, use `min(comparator)`.

**Question 4.** What does `Stream.empty().findFirst()` return?

**Answer:** `Optional.empty()` (when the element type is inferred from context), not `null`.

**Question 5.** Given `IntStream.range(1, 10)`, find the first number divisible by 3. What do you use and what is the result type?

**Answer:** `IntStream.range(1, 10).filter(n -> n % 3 == 0).findFirst()` returns an `OptionalInt` containing 3.

**Question 6.** Suppose there are 1 million records in a parallel stream. When `findFirst` finds a result at an early position, is the predicate guaranteed to run only up to that exact position?

**Answer:** No. A parallel pipeline may process additional elements in other branches before confirming the first result in encounter order; you must not rely on callback invocation counts to infer how many elements were inspected.

**Question 7.** You want to know whether there is at least one person aged 18 or older, without needing to retrieve that person. What do you use?

**Answer:** `people.stream().anyMatch(p -> p.age() >= 18)` directly expresses the existence question. If you need to return the matching person themselves, use `findFirst` or `findAny` after `filter`.

**Question 8.** How do `Stream.ofNullable(null).findAny()` and `Stream.of((String) null).findAny()` differ?

**Answer:** The first expression searches on an empty Stream and thus returns an empty Optional; the second has a null element selected and can throw `NullPointerException`.

## 15. Takeaways

`findFirst()` and `findAny()` are both terminal operations that return **`Optional<T>`** (or the corresponding primitive Optional) and can short-circuit:

- **`findFirst()`** selects the first element by **encounter order**, if the stream is ordered.
- **`findAny()`** selects any element, with **no guarantee** of being the first, and is not a random selection with a defined distribution.
- When the stream is empty, they return `Optional.empty()`; if the selected element is `null`, they can throw `NullPointerException`.
- With parallel streams, `findFirst` may need to maintain ordering constraints, whereas `findAny` has more freedom; actual performance must be measured.
- Short-circuiting does not mean callbacks will be invoked a fixed number of times, nor does it guarantee every infinite source will terminate.
- If you only need a boolean answer to “is there a matching element?”, **`anyMatch`** is usually clearer.

Choose `findFirst` when order is a real requirement, choose `findAny` when any matching element will do, and handle Optionals/exceptions according to a clear contract.