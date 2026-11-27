# Stream.toList Since Java 16 and Unmodifiable Lists

Since Java 16, `Stream` has had the terminal method `toList()` to collect stream elements into a `List`. Because this method was standardized before Java 17, Java 17 programs can use it directly without enabling preview features:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> names = Stream.of("An", "Bình", "Chi")
        .map(String::toUpperCase)
        .toList();

System.out.println(names);
```

Output:

```text
[AN, BÌNH, CHI]
```

The most important point about `Stream.toList()` is that **the returned list is unmodifiable**. You can read, iterate, get its size, or check for elements; however, operations that alter its structure or replace elements will throw `UnsupportedOperationException`.

This is an important difference to keep in mind when migrating legacy code from `collect(Collectors.toList())` to `toList()`. Some older code called `add`, `remove`, or `sort` immediately after collecting a stream. If you switch to `toList()` while keeping those operations, the program will throw an exception at runtime.

## 1. What Is Stream.toList()?

`toList()` is a **terminal operation** on `java.util.stream.Stream<T>`. It consumes the stream and returns an object whose declared type is `List<T>` containing the elements produced by the pipeline.

```java
List<Integer> squares = Stream.of(1, 2, 3, 4)
        .map(number -> number * number)
        .toList();

System.out.println(squares); // [1, 4, 9, 16]
```

Key characteristics:

- **Available since Java 16:** stable and ready to use in Java 17.
- **Terminal operation:** after calling `toList()`, the stream has been consumed and cannot be reused.
- **Returns `List<T>`:** does not guarantee a specific implementation class such as `ArrayList`.
- **Unmodifiable:** mutator operations always throw `UnsupportedOperationException`.
- **Preserves encounter order if the stream is ordered:** for streams with an encounter order, the list reflects that order.
- **May be value-based:** do not rely on the object identity of the returned list.

The name `toList()` looks similar to the `Collectors.toList()` collector, but these are two different APIs. One is a direct method on `Stream`; the other is a collector passed to `collect(...)`. More importantly, the mutability contracts of their results **are not the same**.

### 1.1. Example from Pipeline to List

```java
import java.util.List;
import java.util.stream.Stream;

public class StreamToListBasic {
    public static void main(String[] args) {
        List<String> result = Stream.of("java", "stream", "list")
                .filter(word -> word.length() >= 5)
                .map(String::toUpperCase)
                .toList();

        System.out.println(result);
        System.out.println(result.size());
        System.out.println(result.get(0));
    }
}
```

Output:

```text
[STREAM]
1
STREAM
```

The intermediate operations `filter` and `map` build the pipeline; `toList()` executes the pipeline and collects the results into a list. You can use the list afterward wherever a `List` is accepted, without keeping the stream open.

### 1.2. toList() Consumes the Stream

Streams are designed to be used only once. After a terminal operation, you cannot invoke another terminal operation on the same stream:

```java
Stream<String> stream = Stream.of("A", "B", "C");

List<String> first = stream.toList();

// Wrong: the stream has already been consumed.
// long count = stream.count();
```

If you need two different results, build a new pipeline from a reusable source or create a new stream:

```java
List<String> all = Stream.of("A", "B", "C").toList();
long count = Stream.of("A", "B", "C").count();
```

Do not store a `Stream` to share or reuse it like a collection. If you need data that can be traversed multiple times, collect it into an appropriate collection.

## 2. What Does an Unmodifiable List Mean?

A `List` returned by `toList()` still supports standard read operations:

```java
List<String> languages = Stream.of("Java", "Kotlin", "Scala")
        .toList();

System.out.println(languages.size());          // 3
System.out.println(languages.get(1));          // Kotlin
System.out.println(languages.contains("Java")); // true

for (String language : languages) {
    System.out.println(language);
}
```

However, operations that modify the list are not allowed:

```java
List<String> languages = Stream.of("Java", "Kotlin", "Scala")
        .toList();

languages.add("Go");             // UnsupportedOperationException
languages.remove("Kotlin");      // UnsupportedOperationException
languages.set(0, "Java 17");     // UnsupportedOperationException
languages.clear();               // UnsupportedOperationException
```

Each line causes an exception independently. At runtime, once `add` throws an exception, the subsequent lines in the same execution flow will not run unless the exception is caught.

### 2.1. Which Methods Are Affected?

The contract of `Stream.toList()` specifies that mutator methods always throw `UnsupportedOperationException`. This applies not only to `add` and `remove`, but also to modifications through other APIs:

| Operation | Result on a list from toList() |
| --- | --- |
| `add(element)` | Throws `UnsupportedOperationException`. |
| `addAll(collection)` | Throws `UnsupportedOperationException`. |
| `remove(element)` | Throws `UnsupportedOperationException`. |
| `remove(index)` | Throws `UnsupportedOperationException`. |
| `removeAll(...)` / `retainAll(...)` | Throws `UnsupportedOperationException`. |
| `clear()` | Throws `UnsupportedOperationException`. |
| `set(index, element)` | Throws `UnsupportedOperationException`. |
| `replaceAll(operator)` | Throws `UnsupportedOperationException`. |
| `sort(comparator)` | Throws `UnsupportedOperationException`. |
| `Iterator.remove()` | Throws `UnsupportedOperationException`. |
| `ListIterator.add(...)` / `set(...)` | Throws `UnsupportedOperationException`. |

In particular, do not rely on assumptions like "if the list is empty then `clear()` is a no-op so it won't fail" or "`remove` of a nonexistent element might return `false`". The contract of this list specifies that mutator operations always throw an exception.

Example:

```java
List<String> empty = Stream.<String>empty().toList();

// Still must not call mutators on an unmodifiable list.
// empty.clear();
```

Read methods such as `size`, `isEmpty`, `get`, `contains`, `iterator`, and `toArray` can still be used normally.

### 2.2. Exceptions Occur at Runtime

`UnsupportedOperationException` is an unchecked exception (`RuntimeException`). The compiler does not force you to declare `throws` or use `try/catch`.

```java
List<Integer> values = Stream.of(1, 2, 3).toList();

try {
    values.add(4);
} catch (UnsupportedOperationException ex) {
    System.out.println("List is unmodifiable");
}
```

In real-world applications, you should not use `try/catch` to test whether a collection is modifiable. Design clearly upfront: if a read-only result is needed, use `toList()`; if modification is needed, create a mutable collection.

## 3. Comparing Stream.toList() with Collectors.toList()

This is an essential topic when upgrading to Java 16/17 or refactoring legacy pipelines.

### 3.1. Stream.toList()

```java
List<String> names = Stream.of("An", "Bình", "Chi")
        .toList();
```

The result is an **unmodifiable** list. Elements cannot be added, removed, or replaced.

### 3.2. collect(Collectors.toList())

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> names = Stream.of("An", "Bình", "Chi")
        .collect(Collectors.toList());
```

`Collectors.toList()` makes no guarantees about:

- The concrete implementation type of the list.
- Whether the list is modifiable.
- Serializability or thread safety.

In common JDK implementations, this collector typically produces a modifiable `ArrayList`. However, **you should not rely on that implementation behavior as an API guarantee**. If a program strictly requires a mutable list or a specific type, request it explicitly using `Collectors.toCollection(ArrayList::new)`.

### 3.3. Contract Comparison Table

| Criterion | `Stream.toList()` | `collect(Collectors.toList())` |
| --- | --- | --- |
| Available since | Java 16 | Java 8 |
| How to call | `stream.toList()` | `stream.collect(Collectors.toList())` |
| Declared return type | `List<T>` | `List<T>` |
| Mutability | **Unmodifiable** | No guarantee on mutability |
| Implementation type | Not guaranteed | Not guaranteed |
| Element order | Encounter order if the stream has an encounter order | Per collector characteristics and stream encounter order |
| Suitable when | Only a list result for reading/iterating is needed | A general-purpose collector is needed; if mutability is required, specify the collection explicitly |

Do not replace every `collect(Collectors.toList())` with `toList()` without checking downstream code. If subsequent code calls `result.add(...)`, `result.sort(...)`, or passes the list to an API that intends to mutate it, that change can cause runtime failures.

## 4. Which Approach Should You Use When a Mutable List Is Needed?

If elements need to be added, removed, or sorted in place, you can choose one of the following approaches.

### 4.1. Collectors.toCollection(ArrayList::new) When an ArrayList Is Needed

This is the explicit choice when a new `ArrayList` is required:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> names = Stream.of("An", "Bình", "Chi")
        .collect(Collectors.toCollection(ArrayList::new));

names.add("Dũng");
names.remove("An");
names.sort(String.CASE_INSENSITIVE_ORDER);

System.out.println(names);
```

The collector accepts the `ArrayList::new` supplier, so the target collection type is explicitly requested. The created list is modifiable per the `ArrayList` contract.

### 4.2. Creating an ArrayList from a toList() Result

If a pipeline already uses `toList()` and a need to modify arises later:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> readOnly = Stream.of("A", "B", "C").toList();
List<String> editable = new ArrayList<>(readOnly);

editable.add("D");
editable.set(0, "Updated");

System.out.println(readOnly); // [A, B, C]
System.out.println(editable); // [Updated, B, C, D]
```

The `ArrayList(Collection<? extends E>)` constructor creates a new list containing the elements of the source collection. Modifying `editable` does not alter the structure of `readOnly`.

### 4.3. Sorting Without Mutating the Original List

If you want a sorted result while keeping the original list intact, you can create a mutable copy:

```java
List<String> original = Stream.of("pear", "apple", "orange").toList();

List<String> sorted = new ArrayList<>(original);
sorted.sort(String.CASE_INSENSITIVE_ORDER);

System.out.println(original); // [pear, apple, orange]
System.out.println(sorted);   // [apple, orange, pear]
```

Or sort directly in the pipeline before collecting:

```java
List<String> sorted = Stream.of("pear", "apple", "orange")
        .sorted(String.CASE_INSENSITIVE_ORDER)
        .toList();
```

The second approach produces a list already in the desired order with no need to mutate it after collection.

## 5. Distinguishing toList(), toUnmodifiableList(), and List.copyOf()

Java has multiple APIs that create unmodifiable lists. They share a similar goal but differ in their starting input and certain contract details.

### 5.1. Collectors.toUnmodifiableList()

This collector was added in Java 10:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> names = Stream.of("An", "Bình", "Chi")
        .collect(Collectors.toUnmodifiableList());
```

The result is unmodifiable. Unlike `Stream.toList()`, `Collectors.toUnmodifiableList()` **does not accept null elements**; if the stream contains null, the collector throws `NullPointerException`.

### 5.2. List.copyOf(...)

If you already have a collection and want to create an unmodifiable list from its elements:

```java
import java.util.ArrayList;

List<String> source = new ArrayList<>();
source.add("Java");
source.add("Kotlin");

List<String> snapshot = List.copyOf(source);
```

`List.copyOf` creates an unmodifiable list from the elements of the source collection. This method does not accept null; if the source contains null, it throws `NullPointerException`.

### 5.3. Selection Table

| API | Input | Result | Null |
| --- | --- | --- | --- |
| `stream.toList()` | Stream | Unmodifiable list | In JDK 17, null elements emitted by the stream are retained |
| `stream.collect(Collectors.toList())` | Stream | List; no guarantee on mutability or implementation | Should not infer the contract solely from the current implementation |
| `stream.collect(Collectors.toUnmodifiableList())` | Stream | Unmodifiable list | Throws `NullPointerException` if there is a null element |
| `List.copyOf(collection)` | Collection | Unmodifiable list | Throws `NullPointerException` if the collection contains null |
| `Collections.unmodifiableList(list)` | List | Unmodifiable view | Depends on backing collection |
| `new ArrayList<>(collection)` | Collection | Modifiable ArrayList | ArrayList allows null |

When null is a valid part of the data, pay special attention: you cannot replace `Stream.toList()` with `Collectors.toUnmodifiableList()` or `List.copyOf()` without re-checking the null policy.

## 6. Unmodifiable Does Not Mean Deeply Immutable

An unmodifiable list prevents operations that alter the **list structure** or replace elements. It does not automatically make the objects inside immutable.

Example:

```java
import java.util.List;
import java.util.stream.Stream;

class User {
    private String name;

    User(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    void rename(String newName) {
        this.name = newName;
    }
}

public class ShallowUnmodifiable {
    public static void main(String[] args) {
        User user = new User("An");
        List<User> users = Stream.of(user).toList();

        // Cannot replace the element in the list:
        // users.set(0, new User("Bình"));

        // But the User object inside is still mutable:
        users.get(0).rename("Bình");

        System.out.println(users.get(0).name()); // Bình
    }
}
```

The list still holds the same reference to the `User` object; `rename` mutates that object's state. This is a **shallow unmodifiable collection**, not a deeply immutable object graph.

If deeply immutable data is needed, design the elements to be immutable or create appropriate copies. `Stream.toList()` does not clone individual elements and cannot know how to clone an arbitrary object.

### 6.1. Does Modifying the Source After Collecting Change the Result List?

`toList()` is a terminal operation that produces a result collection from the elements emitted by the stream; it does not return a live view of the source collection.

```java
List<String> source = new ArrayList<>(List.of("A", "B"));

List<String> result = source.stream().toList();
source.add("C");

System.out.println(source); // [A, B, C]
System.out.println(result); // [A, B]
```

In this example with immutable strings, `result` still contains the original two elements. If the elements are mutable objects, both collections may still hold references to the same object; mutating that object will still be visible through both collections.

## 7. Distinguishing Unmodifiable List from Unmodifiable View

The phrase "unmodifiable" can easily lead learners to think every API produces the same kind of result. Distinguish them carefully:

- `stream.toList()`: collects elements into an unmodifiable result list.
- `List.copyOf(source)`: creates an unmodifiable list from the elements of a source collection.
- `Collections.unmodifiableList(source)`: creates an **unmodifiable view** over a backing collection. If other code mutates the backing collection, the view reflects those changes.

View example:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> backing = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(backing);

// Cannot modify through the view:
// view.add("C");

// But code holding backing can still modify it:
backing.add("C");

System.out.println(view); // [A, B, C]
```

If an unmodifiable snapshot is needed, consider `List.copyOf` or `stream.toList()` depending on the source. If you need to provide a read-only view while letting the owner of the backing collection continue updating the data, `Collections.unmodifiableList` may be appropriate.

## 8. Encounter Order: Ordering of the Result List

A stream may or may not have an **encounter order**. `toList()` preserves that order if the stream is ordered:

```java
List<String> ordered = Stream.of("first", "second", "third").toList();
System.out.println(ordered);
```

Output:

```text
[first, second, third]
```

With a parallel stream that has an encounter order, `toList()` still returns elements in encounter order:

```java
List<Integer> values = List.of(1, 2, 3, 4, 5);

List<Integer> result = values.parallelStream()
        .map(number -> number * 10)
        .toList();

System.out.println(result); // [10, 20, 30, 40, 50]
```

Do not infer ordering from the completion order of parallel tasks; the stream framework manages results according to the source's encounter order if that order is preserved.

Conversely, if a pipeline has no encounter order, do not rely on the list's order:

```java
List<Integer> result = List.of(5, 1, 4, 2, 3)
        .stream()
        .unordered()
        .toList();
```

In this case, if the application requires a deterministic order, call `sorted()` before `toList()`:

```java
List<Integer> sorted = List.of(5, 1, 4, 2, 3)
        .stream()
        .unordered()
        .sorted()
        .toList();

System.out.println(sorted); // [1, 2, 3, 4, 5]
```

## 9. Parallel Streams and Thread Safety

`toList()` works with both sequential and parallel streams:

```java
List<Integer> result = java.util.stream.IntStream.rangeClosed(1, 1000)
        .parallel()
        .boxed()
        .toList();
```

However, distinguish three separate concerns:

1. **Parallel execution:** processing steps in the pipeline can run concurrently.
2. **Unmodifiable list:** modifying the list via mutators is disallowed.
3. **Thread safety:** does not mean every inner element or every concurrent access pattern is safe.

The API documentation for `Stream.toList()` notes that if a pipeline is parallel, the returned list may not be thread-safe. Do not treat unmodifiability as proof that the object or its inner elements are safe for all concurrent scenarios. If sharing across multiple threads is needed, define clear data publication rules, element thread safety, and proper synchronization.

## 10. Value-Based Lists and Avoiding Identity Reliance

The Javadoc for `Stream.toList()` states that the returned list **may be value-based**. Callers should not make assumptions about the identity of returned instances.

Avoid writing logic that depends on:

- Reference comparison `==` to determine whether two `toList()` results are "the same list".
- `System.identityHashCode(list)` as a business identifier.
- Using the list itself as a monitor in `synchronized(list)`.

For example, do not rely on:

```java
List<String> first = Stream.of("A", "B").toList();
List<String> second = Stream.of("A", "B").toList();

// Do not use identity to check whether two results have the same data.
boolean sameReference = first == second;

// To compare contents, use equals:
boolean sameContents = first.equals(second);
```

`equals` compares contents according to the `List` contract; `==` checks whether two references point to the exact same object. When working with value-based collections, focus on **the values contained in the list**, not the identity of the list object.

## 11. Handling Null Elements

`Stream.toList()` does not enforce a null-rejection rule like `Collectors.toUnmodifiableList()` or `List.copyOf()`. In the JDK 17 implementation, if a stream emits null, the resulting list retains that element:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> values = Stream.of("A", null, "C").toList();

System.out.println(values.size());       // 3
System.out.println(values.get(1));       // null
```

This does not mean nulls should appear arbitrarily in every pipeline. If null elements are invalid in the business domain, validate or filter them explicitly:

```java
List<String> names = Stream.of("An", null, "Bình")
        .filter(java.util.Objects::nonNull)
        .toList();
```

Conversely, `Collectors.toUnmodifiableList()` and `List.copyOf()` throw `NullPointerException` if the input contains null. When swapping list-collection APIs, check the data's null policy to avoid unexpected behavior changes.

## 12. Primitive Data Types

`Stream.toList()` is a method on `Stream<T>` (reference stream). Specialized streams `IntStream`, `LongStream`, and `DoubleStream` have their own APIs; to use `toList()` for primitive values, you generally must box them:

```java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> numbers = IntStream.rangeClosed(1, 5)
        .boxed()
        .toList();

System.out.println(numbers); // [1, 2, 3, 4, 5]
```

If you only need a primitive array, there is no need to box into `List<Integer>`:

```java
int[] numbers = IntStream.rangeClosed(1, 5).toArray();
```

Choose `boxed().toList()` when downstream APIs require `List<Integer>`. Choose `toArray()` when you want to keep primitive data and work with arrays.

## 13. Real-World Scenario: Collecting Query Results for Read-Only Use

Suppose a service reads order data and returns a list of results to a caller. If the caller only needs to iterate and display them, an unmodifiable list is appropriate:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.stream.Stream;

record OrderSummary(long id, BigDecimal total) {}

class OrderService {
    List<OrderSummary> summaries() {
        return Stream.of(
                new OrderSummary(101, new BigDecimal("120.00")),
                new OrderSummary(102, new BigDecimal("250.00")),
                new OrderSummary(103, new BigDecimal("80.00"))
        )
        .filter(order -> order.total().signum() > 0)
        .toList();
    }
}

public class OrderReport {
    public static void main(String[] args) {
        OrderService service = new OrderService();
        List<OrderSummary> orders = service.summaries();

        for (OrderSummary order : orders) {
            System.out.println(
                    order.id() + ": " + order.total()
            );
        }
    }
}
```

The caller receives a `List<OrderSummary>` for reading. If business requirements prohibit the caller from adding or removing orders in the result, `toList()` expresses that intent accurately. If the caller needs to edit a separate display copy, it can construct `new ArrayList<>(orders)`.

Note: an unmodifiable list does not replace data access control or database-layer data protection. It only restricts operations on the returned result collection.

## 14. Safely Migrating Legacy Code to toList()

When refactoring:

```java
List<String> result = source.stream()
        .filter(this::isValid)
        .map(this::toDisplayName)
        .collect(Collectors.toList());
```

You can change it to:

```java
List<String> result = source.stream()
        .filter(this::isValid)
        .map(this::toDisplayName)
        .toList();
```

Before switching, however, inspect the lines that use `result` afterward:

```java
result.add("Other");
result.remove(0);
result.sort(String.CASE_INSENSITIVE_ORDER);
```

If these operations are part of the required behavior, there are two approaches:

**Approach A — Request a mutable list directly in the pipeline**

```java
List<String> result = source.stream()
        .filter(this::isValid)
        .map(this::toDisplayName)
        .collect(Collectors.toCollection(ArrayList::new));
```

**Approach B — Collect a read-only result, then create a mutable copy where modification is needed**

```java
List<String> collected = source.stream()
        .filter(this::isValid)
        .map(this::toDisplayName)
        .toList();

List<String> result = new ArrayList<>(collected);
result.add("Other");
```

Approach A clearly shows right at the pipeline that the result needs to be an `ArrayList`. Approach B is helpful when you want to preserve a read-only result and only a later step needs a mutable copy.

## 15. Common Errors and Fixes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Calling `add()` after `toList()` throws `UnsupportedOperationException`. | The list from `Stream.toList()` is unmodifiable. | Use `Collectors.toCollection(ArrayList::new)` or copy into `new ArrayList<>(result)`. |
| `set()` or `sort()` also throws an exception. | Replacement/sorting operations are mutators. | Create a mutable list before modifying. |
| Switching `Collectors.toList()` to `toList()` breaks legacy code at runtime. | Legacy code relied on the mutability of the current collector implementation. | Determine the required contract and choose the corresponding API rather than relying on incidental implementation behavior. |
| Reusing the stream after `toList()` fails. | `toList()` already consumed the stream. | Create a new stream from the source or retain the collected collection for reuse. |
| Replacing `toList()` with `List.copyOf()` causes an NPE. | `List.copyOf()` does not accept null. | Check whether null is valid; choose the matching API or filter/validate first. |
| Thinking objects inside the list are also immutable. | Unmodifiable only restricts operations on the list itself. | Use immutable elements or make deep copies if required by the domain. |
| Relying on order from an unordered stream. | Source/pipeline lacks an encounter order. | Use `sorted()` or an ordered source if deterministic results are needed. |
| Using `==` to compare two lists created from streams. | Identity is not a content contract; lists may be value-based. | Use `equals()` to compare contents. |
| Assuming unmodifiable means thread-safe. | Unmodifiability and thread safety are separate concepts. | Evaluate thread safety of the collection and elements; design synchronization when needed. |

## 16. Practice Exercises

### Exercise 1 — Observe an Unmodifiable List

Write a program that creates a list from:

```java
List<String> values = Stream.of("Java", "Kotlin", "Scala").toList();
```

Try calling `add`, `remove`, `set`, and `clear` and note the exceptions. Then call `size`, `get`, `contains`, and iterate with a `for-each` loop.

### Exercise 2 — Choose the Right API for a Mutable List

Given a pipeline that filters and transforms a list of products. After collecting, the program must add a promotional product and sort the result. Write a version using `Collectors.toCollection(ArrayList::new)`, and explain why `toList()` is unsuitable if you want to modify the result directly.

### Exercise 3 — Compare Collectors

Create three results from the same stream:

- `stream.toList()`
- `stream.collect(Collectors.toList())`
- `stream.collect(Collectors.toUnmodifiableList())`

Compare their mutability contracts. Do not conclude `Collectors.toList()` always returns an `ArrayList` just because a specific JDK release happens to do so.

### Exercise 4 — Test Null Handling

Try creating a stream with a null element and collecting with `toList()`, then try `Collectors.toUnmodifiableList()` and `List.copyOf()`. Explain the difference in null policy.

### Exercise 5 — Unmodifiable or Deeply Immutable?

Create a mutable `Person` class with a rename method. Collect a `List<Person>` using `toList()`, try replacing an element in the list, and try renaming the object obtained via `get(0)`. Explain why the two operations produce different outcomes.

### Exercise 6 — Encounter Order

Create a sequential stream, a parallel stream from `List.of(1, 2, 3, 4, 5)`, and a stream with `unordered()` called on it. Collect each stream with `toList()`. State when you can rely on encounter order and when `sorted()` is required.

## 17. Official Java 17 Documentation

- [Java SE 17 API — Stream.toList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): method contract, release introduced, unmodifiability, encounter order, and value-based note.
- [Java SE 17 API — Collectors.toList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList()): collector contract and lack of guarantees on list type, mutability, serializability, and thread safety.
- [Java SE 17 API — Collectors.toUnmodifiableList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList()): collector producing an unmodifiable list and handling null.
- [Java SE 17 API — List.copyOf()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): creating an unmodifiable list from a source collection.
- [Java SE 17 API — Collections.unmodifiableList(...)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): unmodifiable view over a backing list.

`Stream.toList()` is the natural choice when a pipeline needs to produce a `List` result for reading and iterating. If the program needs to add, remove, replace, or sort the list directly, request a mutable collection explicitly. Distinguish the contract of `toList()` from `Collectors.toList()`, and remember that **an unmodifiable list does not make the objects inside it immutable**.
