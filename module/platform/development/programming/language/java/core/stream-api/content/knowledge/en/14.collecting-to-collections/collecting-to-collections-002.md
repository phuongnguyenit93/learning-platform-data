# Collecting with Stream.toList and Distinguishing Its Contract from Collector

In the **Collecting into Collections** chapter of the **Java Stream API**, a declarative pipeline typically starts from a data source, filters with `filter`, transforms with `map`, possibly flattens with `flatMap`, and then needs to keep the result for subsequent steps. Since **Java 16**, `Stream.toList()` is a concise way to turn output elements into a `List`.

However, similar-looking syntax **does not mean the same contract**: `stream.toList()` returns an **unmodifiable** list, whereas `stream.collect(Collectors.toList())` returns a `List` whose specification **does not guarantee** the implementation type or mutability. If the application needs a modifiable `ArrayList`, it should explicitly request one via `Collectors.toCollection(ArrayList::new)`. Additionally, `Collectors.toList()` is a **Collector**, so it can be nested inside `groupingBy`, `mapping`, or other collection steps, whereas `Stream.toList()` is a **terminal operation** on Stream.

This lesson covers all of those differences, how to choose the right API, and the pitfalls related to `null`, element ordering, immutability, parallel processing, and memory.

## 1. Starting from a Concrete Pipeline

Suppose an application has a list of members across multiple teams. We want to get the names of active members in the `DEV` team, keeping their original order:

~~~java
import java.util.List;

public class MemberListDemo {
    record Member(String name, String team, boolean active) {}

    public static void main(String[] args) {
        List<Member> members = List.of(
                new Member("Lan", "DEV", true),
                new Member("Minh", "QA", true),
                new Member("An", "DEV", false),
                new Member("Huy", "DEV", true)
        );

        List<String> activeDevelopers = members.stream()
                .filter(Member::active)
                .filter(member -> "DEV".equals(member.team()))
                .map(Member::name)
                .toList();

        System.out.println(activeDevelopers); // [Lan, Huy]
    }
}
~~~

The pipeline reads from left to right:

1. `members.stream()` creates a Stream of `Member`s from a `List`.
2. The two `filter` operations keep only active members of the `DEV` team.
3. `map(Member::name)` converts `Stream<Member>` into `Stream<String>`.
4. `toList()` triggers the pipeline, collecting the remaining strings into a `List<String>`.

`filter` and `map` are *lazy* intermediate operations; `toList` is a terminal operation. After calling `toList()`, that Stream object has been consumed and another terminal operation cannot be called on it.

**Important:** `activeDevelopers` prints like a regular list, but any operation that modifies this list is unsupported.

~~~java
activeDevelopers.add("Hoa");       // UnsupportedOperationException
activeDevelopers.remove("Lan");     // UnsupportedOperationException
activeDevelopers.set(0, "Linh");    // UnsupportedOperationException
~~~

If you only need to read the result, iterate, look up elements, or pass it to an API that does not modify its input, this contract is appropriate.

## 2. Four Frequently Confused Ways to Collect

| Syntax | Available since Java | Contract for the result |
| --- | --- | --- |
| `stream.toList()` | Java 16 | Returns an **unmodifiable** `List`; no guarantee of implementation class or serializability. |
| `stream.collect(Collectors.toList())` | Java 8 | Returns a `List`; **no guarantee** of concrete type, mutability, serializability, or thread-safety. |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | Java 8 | Returns the result from `ArrayList::new`, so it is known to be an `ArrayList` and elements can be added, removed, or modified. |
| `stream.collect(Collectors.toUnmodifiableList())` | Java 10 | Returns an **unmodifiable** `List` and **does not accept `null` elements**. |

A comparison table by practical need:

| Requirement | Appropriate choice |
| --- | --- |
| Read-only result, wanting concise syntax | `toList()` |
| Need to pass a Collector into `groupingBy` or `mapping` | `Collectors.toList()` or another suitable collector |
| Must have a list that allows adding/removing | `Collectors.toCollection(ArrayList::new)` |
| Must be an unmodifiable list with no `null`s | `Collectors.toUnmodifiableList()` |
| Need another collection type, such as `LinkedList` | `Collectors.toCollection(LinkedList::new)` |
| Need a `Set` instead of a `List` | `Collectors.toSet()` or `Collectors.toCollection(LinkedHashSet::new)` |

Do not conclude that `Collectors.toList()` "always returns a mutable `ArrayList`". Many current JDK versions use a mutable implementation, but this is **not an API guarantee**. If mutability is part of a method's contract, express it through an explicit collector choice.

## 3. What Does Stream.toList() Guarantee?

Under the API contract of `Stream.toList()`:

- **Output elements are collected into a `List`.** For a Stream with an *encounter order*, the list preserves the order in which elements are encountered.
- **The list is *unmodifiable*.** Mutating methods such as `add`, `remove`, `set`, and `sort` on the returned list will throw `UnsupportedOperationException`.
- **No guarantee of a specific implementation class**, serializability, or properties outside the published contract.
- **The result object may be *value-based*.** Do not rely on reference equality `==`, `System.identityHashCode`, or synchronizing on that list's monitor lock.
- **`null` elements are accepted.** Do not equate the contract of `Stream.toList` with `List.of` or `Collectors.toUnmodifiableList`.

Example with `null`:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<String> values = Stream.<String>of("Java", null, "Stream")
        .toList();

System.out.println(values);        // [Java, null, Stream]
System.out.println(values.size()); // 3
~~~

The result is still unmodifiable, even though it contains `null`.

### Unmodifiable Is Different from "Deep Immutability"

The list cannot change its **structure or the element references at its positions**, but `toList()` **does not automatically deep-copy** the objects inside the list.

~~~java
import java.util.List;

class Box {
    int value;
    Box(int value) { this.value = value; }
}

Box box = new Box(10);
List<Box> boxes = java.util.stream.Stream.of(box).toList();

box.value = 99;

System.out.println(boxes.get(0).value); // 99
// boxes.add(new Box(20)); // UnsupportedOperationException
~~~

When `Box` is mutated via another reference, the list still holds **that same Box object**. Therefore, `toList()` is suitable for protecting list structure, but does not automatically create an immutable snapshot of the entire object graph.

If you need data independent of the source, create immutable DTOs or intentional copies inside `map` before collecting the list.

## 4. Collectors.toList() Is a Collector, Not a Stream Method

Both of the following statements collect output elements into a `List`:

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> a = Stream.of("Lan", "Minh", "An")
        .filter(name -> name.length() >= 3)
        .toList();

List<String> b = Stream.of("Lan", "Minh", "An")
        .filter(name -> name.length() >= 3)
        .collect(Collectors.toList());
~~~

Both have the contents `[Lan, Minh]`. But their API mechanisms differ:

- `Stream.toList()` is a **terminal operation** belonging to the `Stream<T>` interface. It does not take a Collector object.
- `Stream.collect(...)` is a **terminal operation** that accepts a Collector or specific collection functions.
- `Collectors.toList()` is a **factory method that creates a `Collector` object** of general type `Collector<T, ?, List<T>>`; the factory call itself does not traverse any data.
- A Collector specifies how to create an accumulation container, accept each element, combine intermediate results, and finish the result. Because of this, Collectors can be composed into a more complex collector.

Diagram:

~~~text
Stream<T> → filter/map → toList()                → List<T>
                       [terminal operation]

Stream<T> → filter/map → collect(toList())       → List<T>
                       [terminal operation]
                              ↑
                    Collector created by
                       Collectors.toList()
~~~

You **cannot** pass `Stream::toList` in place of a Collector where a `Collector` object is required. This is why many `groupingBy` examples use `Collectors.toList()` even when `Stream.toList()` is available outside.

## 5. When Do You Need a Modifiable List?

Suppose a user filters a list of names and then wants to append a default option `"Other"` at the end for UI display. In that case, **being able to add elements** is part of the contract.

The clearest way is to use `Collectors.toCollection`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

ArrayList<String> options = Stream.of("Java", "Kotlin", "Scala")
        .filter(language -> language.length() >= 5)
        .collect(Collectors.toCollection(ArrayList::new));

options.add("Other");

System.out.println(options); // [Kotlin, Scala, Other]
~~~

Another approach if you already have a read-only result list:

~~~java
List<String> readOnly = Stream.of("Java", "Kotlin")
        .toList();

List<String> editable = new ArrayList<>(readOnly);
editable.add("Other");
~~~

The difference: `editable` is a **new list** that can be modified; `readOnly` remains unmodifiable. This conversion is appropriate when you genuinely need to provide **both versions**. If you simply need a mutable list from the start, collecting directly with `toCollection(ArrayList::new)` expresses intent more clearly and avoids an extra copy step.

Do not write:

~~~java
// Do not rely on the mutability of this result:
List<String> names = Stream.of("A", "B")
        .collect(Collectors.toList());

names.add("C"); // Success is not guaranteed by the API.
~~~

When calling a method that requires a concrete `ArrayList` instead of `List`, choose the corresponding factory; do not cast the result of `toList()` or `Collectors.toList()` to `ArrayList`.

## 6. Unmodifiable Collection and Rules for null

`Stream.toList()` and `Collectors.toUnmodifiableList()` both produce unmodifiable lists, but differ on **`null` elements**:

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> accepted = Stream.<String>of("A", null, "B")
        .toList(); // Valid; contains null.

// Throws NullPointerException during collect:
List<String> rejected = Stream.<String>of("A", null, "B")
        .collect(Collectors.toUnmodifiableList());
~~~

`Collectors.toUnmodifiableList()` is designed to reject `null`. Similarly, `List.of(...)` (Java 9+) and `List.copyOf(...)` (Java 10+) do not accept `null` elements.

If the output is required to be free of `null`, you can filter explicitly before collecting:

~~~java
import java.util.Objects;

List<String> clean = Stream.<String>of("A", null, "B")
        .filter(Objects::nonNull)
        .collect(Collectors.toUnmodifiableList());

System.out.println(clean); // [A, B]
~~~

However, **filtering `null` is not always the right policy**. For accounting data, business ID lists, or transaction codes, silently dropping an element can corrupt reports. When `null` indicates invalid data, validating and rejecting the data is more transparent.

### Difference from Collections.unmodifiableList

A way to create an unmodifiable list prior to Java 16 was:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(source);

source.add("C");
System.out.println(view); // [A, B, C]
~~~

`Collections.unmodifiableList(source)` creates an **unmodifiable view over a mutable list**. When `source` changes, the view reflects that change. This is not evidence that a `Stream.toList()` result is also a live view over the source; these methods have different contracts.

If you need an unmodifiable snapshot that contains no `null`, `List.copyOf(source)` is a suitable choice; if you already have a Stream pipeline and need `null` support, `Stream.toList()` satisfies that contract.

## 7. Ordering, Duplicates, and Parallel Streams

For sources with an *encounter order*, such as `List`, both `Stream.toList()` and `collect(Collectors.toList())` preserve the element encounter order in an ordered pipeline:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> numbers = Arrays.asList(5, 2, 5, 1);

List<Integer> kept = numbers.stream()
        .filter(n -> n >= 2)
        .toList();

System.out.println(kept); // [5, 2, 5]
~~~

**Duplicates are not removed automatically.** To keep only distinct elements, explicitly use `distinct()`; to sort, use `sorted()`:

~~~java
List<Integer> sortedDistinct = numbers.stream()
        .distinct()
        .sorted()
        .toList();

System.out.println(sortedDistinct); // [1, 2, 5]
~~~

In a parallel pipeline, order is still preserved **if the Stream has an encounter order** and operations do not drop that constraint:

~~~java
List<Integer> parallelResult = numbers.parallelStream()
        .filter(n -> n >= 2)
        .toList();

System.out.println(parallelResult); // [5, 2, 5]
~~~

`parallel()` **does not automatically make a list unordered**. Conversely, if the source has no defined order, such as certain `Set` types, or the pipeline explicitly calls `unordered()`, you must not rely on the collected element order.

Nor should you assume `toList()` or `Collectors.toList()` automatically creates a `TreeSet`, sorts, or guarantees uniqueness. The collection contract must be chosen explicitly when those properties matter.

## 8. Why Is a Collector Needed for Grouping and Mapping?

One of the biggest practical differences is **Collector composability**. Suppose we need to group member names by department.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Member(String name, String department, boolean active) {}

// Assume members is a List<Member> with valid data.
Map<String, List<String>> namesByDepartment = members.stream()
        .filter(Member::active)
        .collect(Collectors.groupingBy(
                Member::department,
                Collectors.mapping(
                        Member::name,
                        Collectors.toList()
                )
        ));
~~~

Here `Collectors.groupingBy` requires a **downstream Collector** to collect member names for each department. `Collectors.mapping` transforms `Member` into `String` before handing it to `Collectors.toList()`. We cannot directly replace `Collectors.toList()` with `Stream.toList()` in that position, because `Stream.toList()` is not a Collector.

Processing diagram:

~~~text
Stream<Member>
    |
    +-- filter(active)
    |
    +-- groupingBy(department)
            |
            +-- mapping(name)
                    |
                    +-- Collectors.toList()
                           |
                           +-- List<String> for each department
~~~

If each group's list must be **unmodifiable and contain no `null`**, you can use `Collectors.toUnmodifiableList()` downstream:

~~~java
Map<String, List<String>> immutableGroupLists = members.stream()
        .filter(Member::active)
        .collect(Collectors.groupingBy(
                Member::department,
                Collectors.mapping(
                        Member::name,
                        Collectors.toUnmodifiableList()
                )
        ));
~~~

Note: the inner collector creates unmodifiable lists; **that does not automatically make the outer Map unmodifiable**. Protecting the Map structure itself requires a separate decision, and the `null` policy should be reviewed.

If you need a mutable `ArrayList` in each group:

~~~java
Map<String, ArrayList<String>> editableGroupLists = members.stream()
        .collect(Collectors.groupingBy(
                Member::department,
                Collectors.mapping(
                        Member::name,
                        Collectors.toCollection(ArrayList::new)
                )
        ));
~~~

This example assumes `java.util.ArrayList` is imported and there are no `null` group keys. With standard `groupingBy`, `null` grouping keys are not accepted; normalize or handle the data beforehand if the grouping field can be null.

## 9. The Collector Concept and Important Characteristics

`Collector<T, A, R>` describes how to perform a *mutable reduction* on elements of type `T` through an accumulation container of type `A` to produce a result of type `R`.

A Collector can have:

| Component | Role |
| --- | --- |
| `supplier` | Provides a new accumulation container. |
| `accumulator` | Incorporates an input element into the container. |
| `combiner` | Merges two accumulation containers. |
| `finisher` | Transforms the container into the final result. |
| `characteristics` | Describes properties such as `CONCURRENT`, `UNORDERED`, or `IDENTITY_FINISH`. |

For example, `Collectors.toCollection(ArrayList::new)` accepts a caller-specified supplier and uses it during collection. With `parallelStream()`, the API can create separate accumulation containers and merge them. You should not manually add elements to a shared `ArrayList` from a parallel `forEach` to mimic a Collector.

Collector characteristics should only be inferred from **the contract published by the collector**, not from method names or container classes you happen to observe in a specific JDK. Specifically:

- `CONCURRENT` relates to concurrent accumulation capability per the Collector contract; do not assume every Collector works that way.
- `UNORDERED` indicates the collector does not promise to preserve encounter order in the result.
- `IDENTITY_FINISH` allows skipping a separate result conversion step under the conditions of the contract.

You do not need to build custom Collectors for everyday `toList` usage. However, understanding the Collector structure explains why `Collectors.toList()` is passed to `collect(...)` and why collectors can be nested with `groupingBy`, `mapping`, `filtering`, or `collectingAndThen`.

## 10. Generics and Type Inference of Stream.toList()

`Stream.toList()` returns `List<T>`, where `T` is already the element type of the **current Stream**. Java generics are not covariant between `List<String>` and `List<CharSequence>`.

Example:

~~~java
import java.util.List;
import java.util.stream.Stream;

// Stream.of("A", "B") has element type String.
// List<CharSequence> wrong = Stream.of("A", "B").toList();
// Compilation error: List<String> is not a List<CharSequence>.

List<CharSequence> valid = Stream.<CharSequence>of("A", "B")
        .toList();
~~~

You can alternatively use a type-widening transformation step if the pipeline needs a broader type:

~~~java
List<CharSequence> widened = Stream.of("A", "B")
        .map(value -> (CharSequence) value)
        .toList();
~~~

This is unrelated to list mutability, and instead depends on **the type `T` carried by the Stream**. With `collect(Collectors.toList())`, generic type inference of the Collector can be more flexible in some contexts, though explicit signatures and type-safe compilation should be preferred over invalid list casts.

## 11. Laziness, Lifecycle, and Infinite Sources

`filter`, `map`, and `flatMap` are typically *lazy* intermediate operations. `toList()` and `collect(...)` are terminal operations: they trigger the pipeline to produce a result.

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<String> pipeline = Stream.of(" java ", " stream ")
        .map(String::trim);

// Only here does the pipeline need to compute the entire output.
List<String> result = pipeline.toList();

System.out.println(result); // [java, stream]

// Do not reuse a pipeline that has already terminated.
// long count = pipeline.count();
~~~

You cannot call `toList` and then follow with `count` on **the same Stream object**. If the source is a re-traversable collection, create a new Stream; if you need the size of the just-collected list, use `result.size()`.

Because `toList` must collect the entire result, **unbounded infinite sources** are a hazard:

~~~java
import java.util.List;
import java.util.stream.Stream;

List<Long> firstFive = Stream.iterate(1L, n -> n + 1)
        .limit(5)
        .toList();

System.out.println(firstFive); // [1, 2, 3, 4, 5]
~~~

Conversely:

~~~java
// Do not run in an application: no finite termination point.
List<String> neverFinished = Stream.generate(() -> "event")
        .toList();
~~~

If a filter never lets elements through, `filter(...).limit(n).toList()` may still fail to terminate on an infinite source because `limit` counts **output elements after the filter**, not input checks.

If the source is tied to a resource such as `Files.lines`, use `try-with-resources` to close the resource. Calling `toList` or `collect` does not replace I/O resource management.

## 12. Memory, Performance, and Choosing a Terminal Operation

Both `toList()` and `collect(Collectors.toList())` collect and retain **all output elements** in memory. The method name does not turn collection into bounded-memory streaming.

- For results of tens or hundreds of elements, using `toList()` is usually simple and readable.
- For millions of elements, memory cost scales with the number of retained elements; element objects themselves also occupy additional memory.
- A pipeline with `sorted` or `distinct` can allocate intermediate memory alongside the final result; `parallel` also incurs splitting/merging overhead.
- `Stream.toList()` can leverage size information and implementation strategies for optimization, but the API **does not promise** it is always faster or uses less memory than a Collector in every scenario.
- If you only need count, sum, extrema, or existence checks, terminal operations like `count`, `sum`, `min`, `max`, `anyMatch`, or `reduce` can avoid retaining all elements.
- If you need a working list for further modification, `toCollection(ArrayList::new)` expresses the requirement more accurately than calling `toList()` and attempting to modify the result.

Example when you only need to know whether any order is overdue:

~~~java
boolean hasOverdue = orders.stream()
        .anyMatch(order -> order.isOverdue());
~~~

This can short-circuit as soon as an overdue order is found; there is no need to build a list of all overdue orders just to check a condition. The example assumes `orders` is a collection of objects supporting `isOverdue()`.

Using parallel Streams should only be based on data size and benchmark measurements. Parallelism does not turn an unmodifiable list into a mutable one, nor does it guarantee gains for very small pipelines.

## 13. API Design: The List Contract Belongs to the Returner

Consider a public service method:

~~~java
List<String> findActiveIds();
~~~

The signature `List<String>` alone **does not tell the caller** whether the list may be modified. If using `Stream.toList()` in the implementation, communicate the contract "the returned list is unmodifiable" through API documentation.

Example:

~~~java
/**
 * Returns a filtered list of IDs in encounter order.
 * The returned list does not support modification.
 */
public List<String> findActiveIds() {
    return users.stream()
            .filter(User::active)
            .map(User::id)
            .toList();
}
~~~

In this example, `users` and `User` are assumed service components. List unmodifiability helps the service prevent callers from adding or removing elements **on the returned List object**. It does not freeze the state of the element objects if they are mutable.

If the contract requires a modifiable list, the implementation can use:

~~~java
public List<String> findEditableActiveIds() {
    return users.stream()
            .filter(User::active)
            .map(User::id)
            .collect(Collectors.toCollection(ArrayList::new));
}
~~~

Both methods should also document expectations regarding `null`, ordering, duplicates, and element mutability if those properties matter to callers.

## 14. Common Errors and How to Identify Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| `UnsupportedOperationException` when calling `add` or `set` | The list from `Stream.toList()` is unmodifiable | If modification is needed, collect with `toCollection(ArrayList::new)` or create `new ArrayList<>(result)`. |
| `ClassCastException` when casting result to `ArrayList` | `toList()` does not guarantee an implementation class | Use the `List` interface or a factory requesting `ArrayList` from the start. |
| Code works on current JDK but relies on mutating `Collectors.toList()` | The API does not guarantee mutability for this collector | Use `Collectors.toCollection(ArrayList::new)`. |
| `NullPointerException` with `toUnmodifiableList()` | The collector rejects `null` | Validate the source; filter, transform, or reject `null` per business rules. |
| Cannot use `Stream.toList()` inside `groupingBy` | `groupingBy` requires a downstream `Collector` | Use `Collectors.toList()` or `Collectors.toUnmodifiableList()`. |
| Unstable list ordering | Unordered Stream source or encounter order was lost | Use an ordered source or `sorted` with an explicit key. |
| List is unmodifiable but element properties still change | `toList` does not deep-copy objects | Create immutable DTOs or copies when a data snapshot is needed. |
| Memory spikes when running `toList()` | Collects entire result; input is too large | Limit input, process in batches, or choose an aggregating terminal operation. |
| `IllegalStateException` when calling another terminal operation | Reusing a Stream that already ran `toList()` | Create a new Stream from a re-readable source or use the collected list. |

## 15. Self-Check Exercises

### Exercise 1 — Can the List Be Modified?

~~~java
List<String> values = Stream.of("A", "B")
        .toList();

values.add("C");
~~~

**Answer:** No. `Stream.toList()` returns an unmodifiable list. Calling `add` throws `UnsupportedOperationException`. If you need to add elements, collect directly into an `ArrayList` with `Collectors.toCollection(ArrayList::new)`.

### Exercise 2 — Is Collectors.toList() Guaranteed to Be an ArrayList?

~~~java
List<String> values = Stream.of("A", "B")
        .collect(Collectors.toList());
~~~

**Answer:** No. `Collectors.toList()` only promises that the result is a `List`. The specification does not guarantee implementation type, mutability, serializability, or thread-safety. Do not design APIs based on observing a concrete class in one JDK version.

### Exercise 3 — Choosing a Collector for Groups

Requirement: from `Stream<Member>`, group member names by department, where each group is an unmodifiable list and the source is guaranteed to have no `null` names.

**Answer:**

~~~java
Map<String, List<String>> namesByDepartment = members.stream()
        .collect(Collectors.groupingBy(
                Member::department,
                Collectors.mapping(
                        Member::name,
                        Collectors.toUnmodifiableList()
                )
        ));
~~~

`toUnmodifiableList` is a downstream Collector; `Stream.toList()` cannot be passed directly in this position. The outer Map has its own contract.

### Exercise 4 — How Does null Differ?

~~~java
List<String> a = Stream.<String>of("A", null).toList();
List<String> b = Stream.<String>of("A", null)
        .collect(Collectors.toUnmodifiableList());
~~~

**Answer:** `a` is created successfully and contains `null`; creating `b` throws `NullPointerException` because `toUnmodifiableList` does not accept `null`.

### Exercise 5 — Does an Unmodifiable List Protect Child Objects?

A `List<Box>` is created by `Stream.of(box).toList()`. Then the caller executes `box.value = 42`. Does the value read from `list.get(0).value` change?

**Answer:** Yes. The list holds a reference to the same `Box` object. Unmodifiability applies only to methods that mutate the **list**, and does not make element objects immutable.

### Exercise 6 — Result After a Parallel Stream

~~~java
List<Integer> nums = List.of(3, 1, 3, 2);
List<Integer> result = nums.parallelStream()
        .filter(n -> n >= 2)
        .toList();
~~~

**Answer:** `[3, 3, 2]`. `List` is a source with encounter order, `filter` preserves order, and `toList` collects in encounter order, even when the pipeline uses `parallelStream()`. The result contains duplicates because `distinct()` was not called.

## 16. Key Takeaways

- `Stream.toList()` is a terminal operation **since Java 16**, returning an **unmodifiable** list that can contain `null`.
- `Collectors.toList()` is a **Collector factory** from Java 8; the result is a `List`, but the API does not guarantee implementation class or mutability.
- To get a **mutable** list of a known type, use `Collectors.toCollection(ArrayList::new)`. To get an unmodifiable list that rejects `null`, use `Collectors.toUnmodifiableList()`.
- Inside `groupingBy`, `mapping`, and nested collectors, pass a **Collector object**, not `Stream.toList()`.
- Unmodifiability only protects the structure of the `List`; it does not automatically deep-copy the objects inside.
- Both `toList()` and `collect(...)` trigger the pipeline and collect the full output; consider order, duplicates, source lifecycle, and memory before choosing.

**Main idea:** Choose the collection approach based on **the result's contract**: whether the list may be modified, whether `null` is allowed, whether a Collector is needed for nesting, and whether order must be preserved. `Stream.toList()` provides a simple contract for read-only results; `Collectors` provides more configurable and composable collection mechanisms.
