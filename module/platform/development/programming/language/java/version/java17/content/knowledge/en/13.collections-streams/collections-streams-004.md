# Distinguishing `Stream.toList` from `Collectors.toList` in Java 17

## 1. Why Are There Two Ways to Turn a Stream into a List?

The Stream API provides two familiar ways to collect elements into a list:

~~~java
List<String> a = names.stream()
        .filter(name -> !name.isBlank())
        .toList();

List<String> b = names.stream()
        .filter(name -> !name.isBlank())
        .collect(Collectors.toList());
~~~

Both return an object with declared type `List<String>`, but **the contracts of the two APIs are different**:

- `Stream.toList()` was introduced in Java 16 and returns an **unmodifiable** `List`.
- `Collectors.toList()` has existed since Java 8 and is a `Collector` passed to `collect`. The API documentation **makes no guarantees** on the implementation type, mutability, serializability, or thread safety of the resulting list.

Therefore, do not choose purely out of habit or because a current JDK version happens to return an `ArrayList`. Choose based on what the program must guarantee: an unmodifiable list, a mutable list, or a specific collection type.

After this lesson, you should be able to:

1. Distinguish the `Stream.toList()` method from the `Collectors.toList()` collector.
2. State accurately the differences in mutability and API guarantees.
3. Use `Collectors.toCollection(ArrayList::new)` when a modifiable `ArrayList` is needed.
4. Use `Collectors.toUnmodifiableList()` when you want a collector that produces an unmodifiable list.
5. Understand element ordering, null element handling, shallow unmodifiability, and the single-use lifecycle of a Stream.
6. Choose the right API for Java 17 and your project's JDK compatibility level.

## 2. Two APIs with Different Roles

### 2.1. `Stream.toList()`

`toList()` is a **terminal operation** declared directly on the `Stream<T>` interface. It consumes the stream and returns a list:

~~~java
List<Integer> numbers = Stream.of(3, 1, 4, 1, 5)
        .filter(n -> n % 2 == 1)
        .toList();

System.out.println(numbers); // [3, 1, 1, 5]
~~~

The return type is `List<T>`. The resulting list is unmodifiable: calling content-modifying methods such as `add`, `remove`, `set`, `clear`, or corresponding mutator methods throws `UnsupportedOperationException`.

~~~java
List<String> names = Stream.of("An", "Binh").toList();

// names.add("Chi"); // UnsupportedOperationException
// names.set(0, "Anh"); // UnsupportedOperationException
~~~

This method is suitable when you want to collect a pipeline's output and publish a list whose recipients cannot add, remove, or replace elements through the List API.

The Javadoc also notes that the returned list may be a **value-based object**. Do not rely on instance identity, compare it with `==`, use `System.identityHashCode`, or synchronize (`synchronized`) on the instance itself. Compare contents using `equals` and use a separate lock object if synchronization is needed.

### 2.2. `Collectors.toList()`

`Collectors.toList()` is a **factory method** on the `java.util.stream.Collectors` utility class. It returns a `Collector`, which is passed to the `Stream.collect(...)` terminal operation:

~~~java
List<Integer> numbers = Stream.of(3, 1, 4, 1, 5)
        .filter(n -> n % 2 == 1)
        .collect(Collectors.toList());
~~~

The key point is that `Collectors.toList()` **does not directly return a List**. It returns an object describing how to collect stream elements into a list. `collect` is the operation that consumes the stream and returns the list.

The Javadoc for `Collectors.toList()` explicitly states there are no guarantees on:

- The concrete implementation type of the list.
- Whether the list is modifiable.
- Serializability.
- Thread safety when accessed concurrently by multiple threads.

If tighter control over the output list type is needed, the API documentation points to `Collectors.toCollection(Supplier)`.

### 2.3. Direct Comparison Table

| Criterion | `Stream.toList()` | `Collectors.toList()` |
|---|---|---|
| Available since | Java 16 | Java 8 |
| How to call | `stream.toList()` | `stream.collect(Collectors.toList())` |
| Role | Terminal operation on Stream | Factory creating a Collector |
| Return type of the call itself | `List<T>` | `Collector<T, ?, List<T>>` |
| Mutability of the resulting List | **Unmodifiable** | **Not guaranteed by the API** |
| Concrete implementation type | Not guaranteed | Not guaranteed |
| Encounter order | Preserves order if the stream has an encounter order | Preserves order if the stream has an encounter order |
| Usable with parallel streams | Yes | Yes |
| Available in Java 17 | Yes | Yes |
| Use when | You want an unmodifiable List with concise syntax | You are already using collectors or composing with another collector; do not rely on mutability |

**Selection rule:** if an unmodifiable List is needed, `Stream.toList()` expresses that intent directly. If a mutable List is needed, do not assume `Collectors.toList()` always creates an `ArrayList`; request the concrete collection explicitly with `toCollection`.

## 3. Examples Demonstrating Mutability Differences

### 3.1. List from `Stream.toList()`

~~~java
import java.util.List;
import java.util.stream.Stream;

public class Main {
    public static void main(String[] args) {
        List<String> result = Stream.of("red", "green", "blue")
                .toList();

        System.out.println(result); // [red, green, blue]

        // result.add("black"); // UnsupportedOperationException
    }
}
~~~

The list can still be read, iterated, sized, and passed to methods accepting a `List`. What is blocked are structural modifications or element replacements.

### 3.2. List from `Collectors.toList()`

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class Main {
    public static void main(String[] args) {
        List<String> result = Stream.of("red", "green", "blue")
                .collect(Collectors.toList());

        System.out.println(result);
    }
}
~~~

You should not write logic that depends on `result.add(...)` succeeding in this snippet. The current JDK may return a mutable implementation, but the contract of `Collectors.toList()` does not promise it. Another implementation could legitimately return an unmodifiable List and still conform to the API.

### 3.3. When You Truly Need a Mutable `ArrayList`

Specify the implementation explicitly with `Collectors.toCollection`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> names = Stream.of("An", "Binh")
        .collect(Collectors.toCollection(ArrayList::new));

names.add("Chi");
names.set(0, "Anh");

System.out.println(names); // [Anh, Binh, Chi]
~~~

Here, the supplier `ArrayList::new` requests creating an `ArrayList` for collection. Both the type and mutability intent are stated explicitly.

If you just need a mutable List and the exact implementation does not matter, you can use any suitable mutable collection. The essential rule is **never rely on a guarantee the API does not provide**.

### 3.4. Creating a Mutable Copy from an Unmodifiable List

If you already have a result from `Stream.toList()` and later need to modify it:

~~~java
List<String> immutableResult = Stream.of("An", "Binh").toList();
List<String> editable = new ArrayList<>(immutableResult);

editable.add("Chi");
~~~

`new ArrayList<>(...)` creates a new modifiable list. This is a **shallow** copy: the elements inside are still the same objects referenced by the original list.

## 4. Do Not Confuse "Unmodifiable" with Deep Immutability

`Stream.toList()` returns an unmodifiable List. This applies to the **structure of the list**, not that every object inside the list is also immutable.

Example:

~~~java
import java.util.List;

class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }

    void rename(String newName) {
        this.name = newName;
    }

    String name() {
        return name;
    }
}

Person person = new Person("An");
List<Person> people = List.of(person);

person.rename("Anh");
System.out.println(people.get(0).name()); // Anh
~~~

The list does not allow replacing or adding elements, but the `Person` object inside can still change state. Neither `Stream.toList()` nor `Collectors.toUnmodifiableList()` automatically creates deep copies of elements.

If you want data to remain unchanged end-to-end, design elements to be immutable, create defensive copies, or switch to data types with an appropriate immutability contract.

## 5. `Collectors.toUnmodifiableList()`: The Third Option

Java 17 also offers `Collectors.toUnmodifiableList()`, added in Java 10. It creates a collector for an unmodifiable list:

~~~java
List<String> names = Stream.of("An", "Binh", "Chi")
        .collect(Collectors.toUnmodifiableList());

// names.add("Dung"); // UnsupportedOperationException
~~~

Comparing all three options:

| API | Mutability contract | Notes |
|---|---|---|
| `Stream.toList()` | Unmodifiable | Concise terminal operation since Java 16 |
| `Collectors.toList()` | No guarantee | Do not rely on mutability |
| `Collectors.toUnmodifiableList()` | Unmodifiable | Explicit collector for an unmodifiable result |

`Collectors.toUnmodifiableList()` does not accept `null` elements; if collection encounters null, it throws `NullPointerException`. For `Stream.toList()` and `Collectors.toList()`, do not extrapolate a universal null policy solely from the running implementation; if null is part of the data contract, validate and specify the behavior explicitly.

### 5.1. When to Use Which Option?

- Use `stream.toList()` when collecting results and you want an unmodifiable List.
- Use `collect(Collectors.toUnmodifiableList())` when building a collector pipeline and you want to state an unmodifiable result policy explicitly; remember this collector rejects null.
- Use `collect(Collectors.toCollection(ArrayList::new))` when you need a mutable ArrayList.
- Use `collect(Collectors.toList())` when you need a general list collector without relying on concrete type or mutability.

Do not mechanically convert every legacy `Collectors.toList()` to `Stream.toList()`. Check whether downstream code mutates the list, relies on implementation specifics, or needs compatibility with older JDK versions.

## 6. Element Ordering and Encounter Order

A stream may or may not have an **encounter order**. With an ordered source like `List`, both collection approaches preserve order as long as the pipeline maintains encounter order.

~~~java
List<Integer> source = List.of(5, 2, 9, 1);

List<Integer> a = source.stream()
        .filter(n -> n > 1)
        .toList();

List<Integer> b = source.stream()
        .filter(n -> n > 1)
        .collect(Collectors.toList());

System.out.println(a); // [5, 2, 9]
System.out.println(b); // [5, 2, 9]
~~~

Do not assume the output List is always sorted in ascending order. Collecting to a List preserves encounter order; it does not call `sorted()` automatically.

### 6.1. Streams Without an Encounter Order

With unordered sources like `HashSet`, or after calling `unordered()`, do not rely on any specific order of elements in the List:

~~~java
List<String> values = someSet.stream()
        .unordered()
        .toList();
~~~

The result is still a List, but there is no guarantee that the order matches insertion order or any other specific order. If order is a business requirement, use an ordered source or sort explicitly:

~~~java
List<String> sorted = someSet.stream()
        .sorted()
        .toList();
~~~

### 6.2. Parallel Streams

Both `toList()` and `collect(Collectors.toList())` can be used with parallel streams:

~~~java
List<Integer> values = IntStream.range(0, 1_000)
        .parallel()
        .boxed()
        .toList();
~~~

If the source has an encounter order and the pipeline preserves ordering, these terminal operations preserve that order in the result. With unordered streams, do not assume a specific order.

Do not create an external `ArrayList` and call parallel `forEach` to append elements:

~~~java
// Unsafe when multiple threads add to an ArrayList concurrently:
// List<Integer> result = new ArrayList<>();
// IntStream.range(0, 1000).parallel().forEach(result::add);
~~~

Let the Stream framework perform reduction using `toList` or an appropriate collector. `Collectors.toList()` does not need to be a concurrent collector to be used safely in framework-managed parallel collection.

## 7. Streams Are Single-Use

Both `toList()` and `collect(...)` are **terminal operations**. Once a stream has been consumed, the same instance cannot be reused to create another list:

~~~java
Stream<String> stream = Stream.of("A", "B", "C");

List<String> first = stream.toList();

// List<String> second = stream.collect(Collectors.toList());
// IllegalStateException: stream has already been operated upon or closed.
~~~

If two independent results are needed, create a new stream from a re-iterable source:

~~~java
List<String> source = List.of("A", "B", "C");

List<String> first = source.stream().toList();
List<String> second = source.stream().collect(Collectors.toList());
~~~

Not every stream source can be recreated. For example, a stream reading from an input or external resource may be tied to a single-open resource; in that case decide whether to collect once and reuse the List, or reopen the source according to its API.

## 8. Stream Pipelines and Choosing a Terminal Operation

Both collection approaches sit at the end of a pipeline, after intermediate operations such as `filter`, `map`, `distinct`, and `sorted`:

~~~java
List<String> result = orders.stream()
        .filter(order -> order.total() > 0)
        .map(Order::code)
        .distinct()
        .sorted()
        .toList();
~~~

If an unmodifiable List is needed, `toList()` fits well. If the pipeline needs another collector such as grouping, partitioning, or mapping, use specialized collectors:

~~~java
Map<String, List<Order>> byCustomer = orders.stream()
        .collect(Collectors.groupingBy(Order::customerId));
~~~

Not every collection step should end with a List. Choose a terminal operation that reflects the required result shape:

| Need | Terminal operation |
|---|---|
| Unmodifiable List | `stream.toList()` |
| General List collector | `stream.collect(Collectors.toList())` |
| Mutable ArrayList | `stream.collect(Collectors.toCollection(ArrayList::new))` |
| Unmodifiable List via Collector, no nulls | `stream.collect(Collectors.toUnmodifiableList())` |
| Set | `stream.collect(Collectors.toSet())` or a more specific collector |
| Map | `stream.collect(Collectors.toMap(...))` |
| Array | `stream.toArray(...)` |
| Sum/count/statistics | `sum()`, `count()`, `summaryStatistics()` on an appropriate primitive stream |

## 9. Java Version Compatibility

`Collectors.toList()` has existed since Java 8, while `Stream.toList()` was added in Java 16. Therefore:

- Projects targeting Java 17 can use both.
- Projects that must run on Java 8 or Java 11 cannot call `Stream.toList()`.
- If compiled with `javac --release 11`, calls to `Stream.toList()` will not be recognized in the target API.
- `Collectors.toList()` remains a compatible option for code supporting older JDKs, though you still should not rely on the mutability of the list.

Example compiling with Java 17:

~~~bash
javac --release 17 Main.java
java Main
~~~

No preview flags are required for any API in this lesson.

## 10. Performance: Do Not Choose Based on Guesswork

`Stream.toList()` is a direct method on Stream and the implementation can optimize based on the stream source. `Collectors.toList()` goes through the collector mechanism. However, the API does not guarantee a specific performance level or internal implementation across all JDKs.

When choosing:

1. Prioritize the right mutability contract and result type.
2. Keep the pipeline readable and avoid collecting data if only an aggregation is needed.
3. If performance truly matters, benchmark on your JDK and representative application data; do not infer from API call counts alone.
4. Avoid calling `toList()` and then copying to another List if you can collect directly into the target collection.

For example, if a mutable `ArrayList` is needed from the start:

~~~java
List<String> result = source.stream()
        .filter(this::accepted)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

There is no need to create an intermediate unmodifiable List via `toList()` only to copy it into an `ArrayList`.

## 11. Complete Example Running on Java 17

The following program illustrates all three approaches: `Stream.toList()`, `Collectors.toList()`, and `Collectors.toCollection(ArrayList::new)`.

Create file `Main.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class Main {
    public static void main(String[] args) {
        List<String> source = List.of("An", "Binh", "Chi");

        // List guaranteed unmodifiable by the Stream.toList() contract.
        List<String> unmodifiable = source.stream()
                .filter(name -> !name.isBlank())
                .toList();

        // General collector; mutability is not guaranteed.
        List<String> collected = source.stream()
                .filter(name -> !name.isBlank())
                .collect(Collectors.toList());

        // Explicitly request a mutable ArrayList.
        ArrayList<String> editable = source.stream()
                .filter(name -> !name.isBlank())
                .collect(Collectors.toCollection(ArrayList::new));

        System.out.println(unmodifiable);
        System.out.println(collected);
        editable.add("Dung");
        System.out.println(editable);

        // Unmodifiable collector, rejects null elements.
        List<String> fixed = Stream.of("Java", "17")
                .collect(Collectors.toUnmodifiableList());
        System.out.println(fixed);
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 Main.java
java Main
~~~

Output:

~~~text
[An, Binh, Chi]
[An, Binh, Chi]
[An, Binh, Chi, Dung]
[Java, 17]
~~~

No check here relies on whether `collected` is modifiable, because the `Collectors.toList()` contract does not guarantee it. Only `editable` was created with the `ArrayList::new` supplier, so the code can rely on adding elements to it.

## 12. Common Pitfalls

### 12.1. Thinking `Collectors.toList()` Always Returns an ArrayList

There is no such guarantee in the Javadoc. If the code requires an `ArrayList`, use `Collectors.toCollection(ArrayList::new)`.

### 12.2. Calling `add` on a `Stream.toList()` Result

~~~java
List<Integer> numbers = Stream.of(1, 2, 3).toList();
// numbers.add(4); // UnsupportedOperationException
~~~

If modification is needed, create a mutable copy or collect directly with `toCollection`.

### 12.3. Assuming Unmodifiable Means Deeply Immutable

The list disallows changing element positions, but objects inside may still be mutable. Immutability design must consider both elements and externally accessible references.

### 12.4. Reusing the Same Stream

A stream can only be consumed once. Create a new pipeline from a re-iterable source or store the result in a collection and reuse that collection.

### 12.5. Assuming Ordering When the Source Is Unordered

An output List does not manufacture a business ordering by itself. If sorting is needed, use `sorted()` or a source with an encounter order.

### 12.6. Ignoring Version Differences

`Stream.toList()` does not exist in Java 8/11. If a library must support those runtimes, choose a compatible API or raise the JDK baseline per project decisions.

### 12.7. Using `Collectors.toUnmodifiableList()` When Data Contains Null

This collector rejects null. If data may contain null, establish a policy: reject the input, filter out nulls with `filter(Objects::nonNull)`, or choose a collection with a matching null contract.

## 13. Practice Exercises

### Exercise 1 — Choose the API by Requirement

For each requirement, choose the appropriate API:

1. Collect a pipeline into a List solely to return to a caller for reading.
2. Collect into an `ArrayList` and then call `add` and `remove`.
3. Must support Java 11.
4. Need an unmodifiable List via a collector with no null data.

**Suggested answers:**

1. `stream.toList()`.
2. `collect(Collectors.toCollection(ArrayList::new))`.
3. `collect(Collectors.toList())` or an appropriate collector available since Java 8.
4. `collect(Collectors.toUnmodifiableList())`.

### Exercise 2 — Predict the Error

~~~java
List<Integer> values = Stream.of(1, 2, 3).toList();
values.remove(Integer.valueOf(2));
~~~

What happens?

**Answer:** the operation throws `UnsupportedOperationException` because the List returned by `Stream.toList()` is unmodifiable.

### Exercise 3 — Write an Explicit Mutable Result

Write a pipeline that filters positive numbers from `List<Integer> source` and collects into an `ArrayList<Integer>` to append 0 afterward.

~~~java
ArrayList<Integer> result = source.stream()
        .filter(n -> n > 0)
        .collect(Collectors.toCollection(ArrayList::new));
result.add(0);
~~~

### Exercise 4 — Compare Ordering

Given the source `List.of(4, 1, 3, 2)`. Collect using both approaches and explain why both preserve `[4, 1, 3, 2]` when no operation alters encounter order. Then add `sorted()` and predict the result.

**Answer:** initially both preserve the source order; after `sorted()`, the result is `[1, 2, 3, 4]`.

### Exercise 5 — Distinguish Unmodifiable List and Mutable Elements

Create a `Counter` class with an increment method. Place an instance in a `stream.toList()` result; try adding a new element and try incrementing the existing Counter. Explain why the first operation is blocked while the second can still succeed.

**Answer:** the List disallows structural modifications, but the reference to the `Counter` object still points to the same mutable object. An unmodifiable List is not deeply immutable.

### Exercise 6 — Check Java Compatibility

Explain why `Stream.toList()` compiles with `--release 17` but is unavailable in the `--release 11` target API. Rewrite it using `collect(Collectors.toList())` for a project targeting Java 11.

## 14. Completion Criteria

You have mastered this lesson when you can:

1. State the exact introduction versions: `Collectors.toList()` in Java 8, `Stream.toList()` in Java 16.
2. Explain that `Stream.toList()` returns an unmodifiable List.
3. Explain that `Collectors.toList()` does not guarantee implementation type, mutability, serializability, or thread safety.
4. Write `stream.collect(Collectors.toList())` correctly and distinguish it from `stream.toList()`.
5. Use `Collectors.toCollection(ArrayList::new)` when a mutable ArrayList is needed.
6. Distinguish `Collectors.toUnmodifiableList()` and its null policy.
7. Explain encounter order, parallel streams, and single-use stream consumption.
8. Distinguish unmodifiable collections from deep immutability of elements.
9. Choose an API matching JDK 17 or older runtime compatibility requirements.

## 15. Official Documentation

- [Java SE 17 API — `Stream.toList()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): unmodifiable List contract, value-based caveat, and element ordering.
- [Java SE 17 API — `Collectors.toList()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList()): List collector and lack of type/mutability guarantees.
- [Java SE 17 API — `Collectors.toCollection(Supplier)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier)): specifying the collection implementation to create.
- [Java SE 17 API — `Collectors.toUnmodifiableList()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList()): collector producing an unmodifiable List.

**Key takeaway:** `Stream.toList()` guarantees an unmodifiable List; `Collectors.toList()` only requests collecting into a List without guaranteeing implementation or mutability; `Collectors.toCollection(ArrayList::new)` is the way to explicitly request a mutable ArrayList. Choose based on the required contract and verify your project's target Java version.
