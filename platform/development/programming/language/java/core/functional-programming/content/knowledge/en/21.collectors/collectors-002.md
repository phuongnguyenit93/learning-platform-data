# `Stream.toList()` Returns an Unmodifiable List

## 1. The problem: collecting data from a Stream into a List

In Java, Streams are commonly used to **transform, filter, and sort** data, then collect the result into a list. Since **Java 16**, the `java.util.stream.Stream<T>` interface provides a terminal operation:

```java
List<T> toList();
```

Example:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> names = Stream.of("Lan", "Minh", "An")
        .filter(name -> name.length() >= 3)
        .toList();

System.out.println(names); // [Lan, Minh]
```

`toList()` **consumes the stream** and returns a `List<T>` containing the elements of the stream. If the source has an *encounter order*, the result preserves that order. However, there is an important condition:

**The list returned by `Stream.toList()` is *unmodifiable*: any call to a mutating method on the list will throw `UnsupportedOperationException`.**

This does not just mean "you cannot `add`/`remove` to change the number of elements". It also means **you cannot replace an element at an existing index with `set`, sort the list in place with `sort`, or apply `replaceAll`**. A "fixed-size" list that still allows `set` is a different concept; `Stream.toList()` has a stricter contract.

Distinctions to keep clear in this lesson:

- **Unmodifiable List** ≠ **immutable elements inside**.
- **Unmodifiable result list** ≠ **unmodifiable original source**.
- `Stream.toList()` ≠ `Collectors.toList()` ≠ `Collectors.toUnmodifiableList()`.
- `Stream.toList()` can contain `null` elements; some other ways of creating unmodifiable lists **do not** allow `null`.

## 2. Terminal operation: when is the data collected?

`Stream.toList()` is a **terminal operation**, meaning an operation that ends the pipeline. Intermediate operations such as `filter`, `map`, and `sorted` are built lazily, whereas `toList` requires consuming the source to produce the result.

```java
List<Integer> squares = Stream.of(1, 2, 3, 4)
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .toList();

System.out.println(squares); // [4, 16]
```

Here:

1. The source provides `1,2,3,4`.
2. `filter` keeps `2,4`.
3. `map` transforms them into `4,16`.
4. `toList` performs the collection and returns `List<Integer>` in encounter order.

`toList` does not return a new Stream to chain `map` onto. Once a terminal operation has been called, the stream is consumed and cannot be reused:

```java
Stream<Integer> numbers = Stream.of(1, 2, 3);
List<Integer> first = numbers.toList();

// WRONG at runtime: the stream has already been consumed.
// List<Integer> second = numbers.toList();
```

If you need to run two pipelines, create **two streams** from a source capable of supplying data again:

```java
List<Integer> values = List.of(1, 2, 3);
List<Integer> first = values.stream().toList();
long count = values.stream().count();
```

This snippet runs validly because each call to `values.stream()` creates a new stream.

## 3. How should "unmodifiable" be understood accurately?

Consider:

```java
List<String> letters = Stream.of("A", "B").toList();
```

All of the following are **mutating operations** on the resulting list and are not supported:

| Method | Intent | Result with `Stream.toList()` |
| --- | --- | --- |
| `letters.add("C")` | Add an element | `UnsupportedOperationException` |
| `letters.add(0, "C")` | Insert at an index | `UnsupportedOperationException` |
| `letters.remove("A")` | Remove an element | `UnsupportedOperationException` |
| `letters.clear()` | Remove all elements | `UnsupportedOperationException` |
| `letters.set(0, "X")` | Replace element at an index | `UnsupportedOperationException` |
| `letters.sort(...)` | Sort *in place* | `UnsupportedOperationException` |
| `letters.replaceAll(...)` | Replace elements with new values | `UnsupportedOperationException` |
| `letters.removeIf(...)` | Remove elements matching a condition | `UnsupportedOperationException` |
| `letters.listIterator().set(...)` | Replace via iterator | `UnsupportedOperationException` |

**Do not confuse "unmodifiable" with "fixed-size".** For example, `Arrays.asList("A","B")` creates a fixed-size list: `add`/`remove` are blocked, but `set(0,"X")` can still succeed. `Stream.toList()` blocks `set` as well.

**Read-only** actions remain valid:

```java
List<String> letters = Stream.of("A", "B").toList();

System.out.println(letters.size()); // 2
System.out.println(letters.get(0)); // A
System.out.println(letters.contains("B")); // true
System.out.println(letters.stream().map(String::toLowerCase).toList());
// [a, b]
```

An unmodifiable list can still be **read, iterated, filtered, and used as input for a new pipeline**. It just cannot be modified directly.

## 4. Complete Java 17 program: verifying the contracts

Create the file **`StreamToListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamToListDemo {
    static final class Box {
        private String value;

        Box(String value) {
            this.value = value;
        }

        void rename(String next) {
            this.value = next;
        }

        @Override
        public String toString() {
            return value;
        }
    }

    public static void main(String[] args) {
        List<String> names = Stream.of("Lan", "Minh", "An")
                .filter(name -> name.length() >= 3)
                .toList();
        System.out.println("Names: " + names);

        try {
            names.add("Hoa");
        } catch (UnsupportedOperationException ex) {
            System.out.println("add: blocked");
        }

        try {
            names.set(0, "Mai");
        } catch (UnsupportedOperationException ex) {
            System.out.println("set: blocked");
        }

        try {
            names.sort(Comparator.naturalOrder());
        } catch (UnsupportedOperationException ex) {
            System.out.println("sort: blocked");
        }

        try {
            names.remove("Lan");
        } catch (UnsupportedOperationException ex) {
            System.out.println("remove: blocked");
        }

        System.out.println("Names after attempts: " + names);

        // Want a list that can add/remove/modify: create a mutable copy.
        List<String> mutable = new ArrayList<>(names);
        mutable.add("Hoa");
        mutable.set(0, "Mai");
        System.out.println("Mutable: " + mutable);

        // toList accepts null elements in the Stream.
        List<String> nullable = Stream.of(
                "A", (String) null, "B").toList();
        System.out.println("Null preserved: " + nullable);

        try {
            Stream.of("A", (String) null, "B")
                    .collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException ex) {
            System.out.println("toUnmodifiableList null: blocked");
        }

        // Explicitly collect into a mutable ArrayList.
        List<String> collectedMutable = Stream.of("P", "Q")
                .collect(Collectors.toCollection(ArrayList::new));
        collectedMutable.add("R");
        System.out.println("Collector mutable: " + collectedMutable);

        // toList is a separate result in terms of list structure.
        ArrayList<String> source = new ArrayList<>(List.of("A", "B"));
        List<String> snapshot = source.stream().toList();
        List<String> liveView = Collections.unmodifiableList(source);
        source.add("C");
        System.out.println("Source now: " + source);
        System.out.println("Stream result: " + snapshot);
        System.out.println("Live view: " + liveView);

        // The list cannot be modified, but the objects inside can be mutable.
        Box first = new Box("OLD");
        Box second = new Box("SECOND");
        List<Box> boxes = Stream.of(first, second).toList();
        first.rename("NEW");
        System.out.println("Mutable elements: " + boxes);

        // Stream has encounter order -> toList preserves encounter order.
        List<String> ordered = IntStream.rangeClosed(1, 4)
                .parallel()
                .mapToObj(n -> "N" + n)
                .toList();
        System.out.println("Parallel ordered: " + ordered);

        // A new transformation creates a new list without modifying names.
        List<String> sortedCopy = names.stream()
                .sorted()
                .toList();
        System.out.println("Sorted copy: " + sortedCopy);
        System.out.println("Original names: " + names);

        // An empty stream still produces an unmodifiable list.
        List<String> empty = Stream.<String>empty().toList();
        System.out.println("Empty: " + empty);
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 StreamToListDemo.java
java StreamToListDemo
```

**Exact expected stdout:**

```text
Names: [Lan, Minh]
add: blocked
set: blocked
sort: blocked
remove: blocked
Names after attempts: [Lan, Minh]
Mutable: [Mai, Minh, Hoa]
Null preserved: [A, null, B]
toUnmodifiableList null: blocked
Collector mutable: [P, Q, R]
Source now: [A, B, C]
Stream result: [A, B]
Live view: [A, B, C]
Mutable elements: [NEW, SECOND]
Parallel ordered: [N1, N2, N3, N4]
Sorted copy: [Lan, Minh]
Original names: [Lan, Minh]
Empty: []
```

### Checking each result group

**Mutation group:** `names` keeps `[Lan, Minh]`. Each operation `add`, `set`, `sort`, `remove` throws `UnsupportedOperationException` and is caught individually, so four `blocked` lines appear. The `names` result remains unchanged.

**Mutable group:** `new ArrayList<>(names)` copies the element references into a separate modifiable list. Adding Hoa and setting the first element to Mai yields `[Mai, Minh, Hoa]`. The original list remains `[Lan, Minh]`.

**`null` group:** `Stream.of("A", (String) null, "B").toList()` can collect null elements as well. `Collectors.toUnmodifiableList()` rejects null and throws `NullPointerException`; the program catches the error to continue.

**Collector group:** `Collectors.toCollection(ArrayList::new)` creates a genuinely mutable `ArrayList` as requested. Adding R produces `[P, Q, R]`.

**Snapshot/view group:** After `source.add("C")`, the `snapshot` collected by the stream still has two elements. `Collections.unmodifiableList(source)` is an **unmodifiable view** that reflects changes to the original list, so it also displays C.

**Mutable object group:** `boxes` does not allow structural changes through list mutators, but `first.rename("NEW")` changes the state of the `Box` referenced by the list. Therefore, when printed, `[NEW, SECOND]` is shown.

**Order group:** `IntStream.rangeClosed(1,4)` has an encounter order; even though map may execute in parallel, `toList()` preserves the order `N1, N2, N3, N4`. `names.stream().sorted().toList()` creates a separate result; it does not call `List.sort` on the original list.

**Empty group:** `Stream.<String>empty().toList()` returns a list with no elements. Do not infer that this empty list has a specific implementation class or that `==` can be used to identify a canonical instance.

## 5. Comparing `Stream.toList()` with `Collectors.toList()`

Both of the following approaches can produce a `List<String>` with the same data:

```java
List<String> direct = Stream.of("A", "B").toList();

List<String> viaCollector = Stream.of("A", "B")
        .collect(Collectors.toList());
```

However, their **mutability contracts** differ:

| Criterion | `Stream.toList()` | `Collectors.toList()` |
| --- | --- | --- |
| Available since | Java 16 | Java 8 |
| How it is called | Direct terminal on Stream | `collect` with a collector |
| Result type | `List<T>` | `List<T>` |
| Encounter order | Preserved if the source has encounter order | Collector guarantees preserving encounter order of an ordered source |
| Can the list be modified? | **No; all mutators are blocked** | **No guarantee** on mutability |
| Implementation type guarantee | No | No |
| Serializable guarantee | No | No |
| Thread-safe guarantee | No | No |

**Important:** On many JDK versions, `Collectors.toList()` currently happens to return a mutable `ArrayList`. However, the Javadoc **does not guarantee** mutability or any specific implementation. Therefore, do not write logic that relies on `Collectors.toList()` always returning a mutable list across all JDKs/implementations.

If you need a mutable list of a specific type, state your intent explicitly:

```java
List<String> mutable = Stream.of("A", "B")
        .collect(Collectors.toCollection(ArrayList::new));

mutable.add("C");
System.out.println(mutable); // [A, B, C]
```

Or create a mutable copy from the `toList` result:

```java
List<String> mutable = new ArrayList<>(
        Stream.of("A", "B").toList());

mutable.add("C");
```

In the snippets above, `ArrayList` must be imported from `java.util`. Both strategies fit depending on how the code is organized: collect directly into a mutable collection, or collect into an unmodifiable one first and copy when modification is genuinely needed.

### Is `Collectors.toList()` the same as `Collectors.toUnmodifiableList()`?

No. The name `Collectors.toList` **makes no promise** about mutable/unmodifiable. `Collectors.toUnmodifiableList()` (Java 10+) has a contract to **return an unmodifiable list** and **not accept null elements**.

Choose the API by its *contract*, not by observing the collection's class name in a single run.

## 6. Comparing `Stream.toList()` with `Collectors.toUnmodifiableList()`

Both can produce an unmodifiable list. However, they differ in usage and **null policy**:

```java
List<String> allowsNull = Stream.of(
        "A", (String) null, "B").toList();

System.out.println(allowsNull); // [A, null, B]
```

Whereas:

```java
// Throws NullPointerException because the collector forbids null elements.
List<String> disallowsNull = Stream.of(
        "A", (String) null, "B")
        .collect(Collectors.toUnmodifiableList());
```

The second snippet is an intentional runtime error example; it will **not** continue running unless the exception is caught. When writing a complete program, validate data or use `try/catch` if there is a clear error-handling policy.

Table:

| Criterion | `Stream.toList()` | `Collectors.toUnmodifiableList()` |
| --- | --- | --- |
| Version | Java 16+ | Java 10+ |
| Usage | `stream.toList()` | `stream.collect(...)` |
| Result | Unmodifiable `List<T>` | Unmodifiable `List<T>` |
| Null elements | **Allowed** | **Not allowed** |
| Can `add`, `remove`, `set` | No | No |
| Guaranteed to be a specific class | No | No |

If null is invalid data, you can **validate beforehand** and report a clearer error, or use the null-forbidding collector as an additional check layer. If null is valid in your application, do not replace `toList()` with `toUnmodifiableList()` without considering the contract change.

### `List.of` and `List.copyOf`

`List.of(...)` (Java 9+) creates an unmodifiable list and **rejects null**. `List.copyOf(collection)` (Java 10+) also creates an unmodifiable result and **rejects null** in the input collection.

```java
List<String> a = List.of("A", "B");
List<String> b = List.copyOf(a);

System.out.println(a); // [A, B]
System.out.println(b); // [A, B]
```

Do not assume `a == b` must be true or false: unmodifiable/value-based APIs may reuse instances depending on the implementation. Use `equals` when comparing contents.

## 7. An unmodifiable list does not mean all elements are immutable

This is an important point in API design:

```java
class Ticket {
    private String status;

    Ticket(String status) {
        this.status = status;
    }

    void setStatus(String status) {
        this.status = status;
    }

    @Override
    public String toString() {
        return status;
    }
}
```

If a List contains mutable `Ticket` instances:

```java
Ticket ticket = new Ticket("NEW");
List<Ticket> tickets = Stream.of(ticket).toList();

ticket.setStatus("DONE");
System.out.println(tickets); // [DONE]
```

These snippets are **illustrative code to be placed in an appropriate class/method context**. `tickets` does not allow adding/removing/replacing elements, yet the `ticket` object still changes state from `NEW` to `DONE`. The list holds **references to objects**, not deep copies of those objects.

Therefore, distinguish between:

- **Unmodifiable collection:** membership/positions/element references cannot be changed through the collection.
- **Immutable element:** the state of each element cannot be changed through its normal API.
- **Deep immutability:** the entire object graph reachable from the structure is immutable by contract.
- **Thread safety:** does not follow automatically just because the list cannot be modified.

`Stream.toList()` only provides an **unmodifiable list** contract. It does not turn mutable objects into immutable records, does not clone each element, and does not guarantee object contents are safe when multiple threads mutate them.

### Using records and defensive copies when needed

`record` helps define value-oriented data clearly, but **a record containing a reference to a mutable list** can still expose mutations through that list.

Example:

```java
record Order(String id, List<String> items) {
    Order {
        items = List.copyOf(items);
    }
}
```

The compact constructor creates an unmodifiable list copy; this protects the list structure. `List.copyOf` rejects null elements, which is an intentional choice. If the elements of `items` are themselves mutable objects, you still need to consider deeper-level copying or an immutable model.

## 8. Does the result reflect changes to the source list?

When running:

```java
ArrayList<String> source = new ArrayList<>(List.of("A", "B"));
List<String> result = source.stream().toList();

source.add("C");

System.out.println(source); // [A, B, C]
System.out.println(result); // [A, B]
```

`result` is a separate result list in terms of **the collected element structure**. Adding a new element to `source` **after `toList` completes** does not automatically add that element to `result`.

However, when elements are mutable objects, **references to elements** can still point to the same object; mutating an object through the source can cause both the source and the result to observe the new value. This is a "shallow snapshot" in practical terms, not a deep snapshot of all state.

### `Collections.unmodifiableList(source)` is a view

`Collections.unmodifiableList(source)` has different semantics: it creates a **view** that prevents modification through the view, but changes to the source collection are still reflected through the view.

```java
ArrayList<String> source = new ArrayList<>(List.of("A", "B"));
List<String> view = Collections.unmodifiableList(source);

source.add("C");
System.out.println(view); // [A, B, C]
```

You need to import `java.util.Collections` and `java.util.ArrayList`. Do not confuse a view with `Stream.toList`. Both block `view.add(...)`/`result.add(...)`, but they behave differently when the source is updated **after** creating the result.

**Do not modify the source list while streaming** if the source does not support appropriate concurrent modification. The Stream *non-interference* rule requires avoiding modifying the source during pipeline execution; demonstrating updates **after the terminal operation** is a different scenario.

## 9. Want a mutable list: three safe options

### Option 1 — `Collectors.toCollection(ArrayList::new)`

This is the clearest way to express it right in the pipeline:

```java
List<String> values = Stream.of("B", "A")
        .sorted()
        .collect(Collectors.toCollection(ArrayList::new));

values.add("C");
values.set(0, "X");
System.out.println(values); // [X, B, C]
```

`Collectors.toCollection` uses the `ArrayList::new` factory to create the target collection, so the mutability of `ArrayList` is something you can rely on.

### Option 2 — Copy from `toList`

```java
List<String> values = new ArrayList<>(
        Stream.of("A", "B").toList());

values.remove("A");
System.out.println(values); // [B]
```

Suitable when an intermediate API needs to return an unmodifiable list and only some callers need a mutable copy.

### Option 3 — Choose a different data structure when a List is not needed

If the requirement is lookup by key, a `Map` may be better than a List. If the requirement is numeric aggregation, `sum`/`reduce` can skip creating a list altogether. Do not create a collection just to sum numbers and discard it.

```java
int total = Stream.of(10, 20, 30)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(total); // 60
```

Designing around the business goal avoids unnecessary intermediate steps and the mistake of "collect then try to mutate".

## 10. Using `sorted`, `map`, and `filter` to produce new results

When a list cannot be modified, transformations should produce a **new list**:

```java
List<String> original = Stream.of("c", "a", "b").toList();

List<String> sorted = original.stream()
        .sorted()
        .toList();

List<String> upper = original.stream()
        .map(String::toUpperCase)
        .toList();

System.out.println(original); // [c, a, b]
System.out.println(sorted);   // [a, b, c]
System.out.println(upper);    // [C, A, B]
```

`sorted` in a pipeline **is not the same** as `List.sort` mutating the list itself. It builds a stream in sorted order and then `toList` creates the result list. All three lists in the example can be unmodifiable lists; you can still transform data by starting a new pipeline.

If you need to exclude an element:

```java
List<String> withoutA = original.stream()
        .filter(value -> !value.equals("a"))
        .toList();

System.out.println(withoutA); // [c, b]
```

This is a **non-mutating** approach, very convenient when working with data shared across multiple layers of an application.

## 11. Ordering, parallel streams, and `toList`

A stream with an encounter order, such as from a `List` or `IntStream.range`, produces a `toList` result in that order, even when the stream executes in parallel:

```java
List<String> ids = java.util.stream.IntStream
        .rangeClosed(1, 5)
        .parallel()
        .mapToObj(n -> "ID-" + n)
        .toList();

System.out.println(ids);
// [ID-1, ID-2, ID-3, ID-4, ID-5]
```

However, this **does not mean** mapper calls execute sequentially in the same order. Intermediate operations can run on multiple threads; `toList` is responsible for collecting the results in the encounter order of an ordered stream.

If the source is unordered such as a `HashSet`, or `unordered()` has been called to relax ordering, you should not rely on a specific result order for business logic. Use `sorted` when you want an explicit order.

### Unmodifiable is not automatically thread-safe for the whole application

Having multiple threads **read** a safely published list with immutable elements is usually easier to manage than sharing a mutable `ArrayList`. However, `Stream.toList` does not by itself solve reference publication across threads (*safe publication*) or concurrent mutation of the elements inside.

Do not use `parallelStream().forEach(result::add)` to collect into an external list without synchronization. To build a list, `map(...).toList()` or an appropriate collector is better. If you truly need to update shared state, design clear synchronization and ownership.

## 12. Can you rely on the class name, serializability, or identity of the result?

The Javadoc for `Stream.toList()` **does not guarantee a specific implementation type** or serializability of the resulting list. In addition, the returned list **may be value-based**, meaning you should not use reference equality `==`, `System.identityHashCode`, or use the object itself as a synchronization lock for application logic.

What you should do:

```java
List<String> a = Stream.of("A", "B").toList();
List<String> b = Stream.of("A", "B").toList();

System.out.println(a.equals(b)); // true
```

`equals` checks list contents according to the contract. Do not write `a == b` assuming it will always be true or false: instance reuse and the implementation class are not commitments to rely on in business code.

Likewise, do not cast:

```java
// DO NOT assume the result is an ArrayList.
// ArrayList<String> a = (ArrayList<String>) Stream.of("A").toList();
```

If you need an `ArrayList`, explicitly construct an `ArrayList` or collect into `Collectors.toCollection(ArrayList::new)`.

## 13. Generics and type inference differences

`Stream.toList()` returns `List<T>` based on **the type T of the source stream**. Meanwhile, `Collectors.toList()` is a generic collector and certain assignment contexts can help the compiler infer types differently.

Example:

```java
List<CharSequence> values =
        Stream.<CharSequence>of("A", "B").toList();
```

Here we explicitly specify `T = CharSequence` so the result has type `List<CharSequence>`. If you write `Stream.of("A","B")`, Java typically infers `Stream<String>`; `List<String>` is not a subtype of `List<CharSequence>` because Java generics are *invariant* in their type parameter.

Another way is to specify the type at an intermediate step:

```java
List<CharSequence> values = Stream.of("A", "B")
        .<CharSequence>map(s -> s)
        .toList();
```

These two snippets are **two separate alternatives**; do not declare the same `values` variable in the same scope. When refactoring from `collect(Collectors.toList())` to `toList()`, you may need to adjust the source type, use an explicitly typed variable, or add a mapper, rather than just replacing the method chain.

This is a **compile-time type** error, unrelated to runtime list mutability.

## 14. Cost and rationale for choosing the API

`Stream.toList()` often makes code more concise when the goal is genuinely a result list that **does not need to be modified**. Avoid choosing it based on the assumption that it "always uses less memory" or "is always faster" than `collect(Collectors.toList())`. Optimization depends on the JDK, source type, size, preceding transformations, and the JVM.

Some guidelines:

- If you only need a **readable list**, `toList()` is clear, concise, and has an unmodifiable contract.
- If you need a **specific mutable list**, use `Collectors.toCollection(ArrayList::new)`.
- If you need **unmodifiable and null-forbidding**, use `Collectors.toUnmodifiableList()` (or another API with the same verified policy).
- If you **do not need a list** and only need `sum`, `count`, or `max`, call the appropriate terminal operation.
- If you want to optimize performance, benchmark with a representative workload rather than relying on the internal class of the result.

Do not treat unmodifiable as "no testing needed": test mutability, null cases, result ordering, and element immutability according to your API requirements.

## 15. Common mistakes

| Mistake or assumption | Issue | How to handle |
| --- | --- | --- |
| `stream.toList().add(x)` | Result is unmodifiable | Create an `ArrayList` or use `toCollection` |
| `stream.toList().set(0,x)` | `set` is also a mutator and is blocked | Copy to mutable or create a new list via `map` |
| `list.sort(...)` on `toList` result | In-place sorting is not supported | `list.stream().sorted(...).toList()` |
| "Unmodifiable" means `set` still works | Confused with a fixed-size list | Distinguish unmodifiable and fixed-size |
| "`Collectors.toList` is always mutable" | No contract guarantee | Use `toCollection(ArrayList::new)` |
| "`toList` disallows null" | Actually `toList` allows null | Distinguish from `toUnmodifiableList`/`List.of` |
| "Unmodifiable list means child objects are immutable" | Only restricts operations through the list | Use immutable models/defensive copies when needed |
| "Adding to source updates `toList` result" | Result is not a live view of the source | Re-create stream if a fresh snapshot is needed |
| "`unmodifiableList(source)` is a snapshot" | It is a view reflecting source changes | Copy first if structural independence is needed |
| "`toList` returns `ArrayList`" | Implementation is not guaranteed | Do not cast or rely on class name |
| "Use `==` to compare two `toList` results" | Identity is unreliable for value-based lists | Use `equals` |
| "Stream can still be used after `toList`" | Terminal operation has consumed the stream | Create a new stream |
| "Parallel `toList` loses order" | If source is ordered, result preserves encounter order | Distinguish result order from mapper order |
| "Unmodifiable list is always thread-safe" | Mutable elements/safe publication are still issues | Review the entire data and threading model |

## 16. Practice exercises

1. Create `Stream.of("A","B").toList()`. Try `add`, `set`, `remove`, and `sort` in turn and record the exceptions. Why does "cannot change size" not fully describe the contract?
2. Use `List.of("A","B")` and compare its mutability with `Arrays.asList("A","B")` and `Stream.of("A","B").toList()`.
3. Fix `stream.toList().add("C")` in two ways: `new ArrayList<>(stream.toList())` and `stream.collect(Collectors.toCollection(ArrayList::new))`. Use a **new stream** for each approach.
4. Create a stream containing `(String) null`. Compare `toList` with `collect(Collectors.toUnmodifiableList())`, using `try/catch` to verify the behavior.
5. Use `Collectors.toList` and print the class name in a run to observe it. Why must that observation not be used as a contract for API mutability?
6. From the source `List.of("c","a","b")`, create a new `sorted` list and a new `uppercase` list using `stream().sorted().toList()` and `stream().map(...).toList()`, without modifying the source.
7. Create `List<Box> boxes = Stream.of(box).toList()` where `Box` has a setter. Try modifying `Box` after creating the list. Explain why the list membership does not change yet it displays the new value.
8. Create a source `ArrayList` along with both `source.stream().toList()` and `Collections.unmodifiableList(source)`. After adding an element to `source`, compare the two results.
9. Try creating `List<CharSequence>` from `Stream.of("A","B").toList()`. Fix it with `Stream.<CharSequence>of(...)`; state the reason regarding generic invariance.
10. With `IntStream.rangeClosed(1,100).parallel().mapToObj(n -> "ID"+n).toList()`, explain why the result is still ordered while logging inside the mapper should not have a fixed expected stdout.
11. If a record contains `List<MutableItem>`, does `List.copyOf` make the `MutableItem` instances immutable? Propose a better data model/defensive copy.
12. When aggregating orders, compare `orders.stream().mapToInt(Order::amount).sum()` with collecting all amounts into a list and summing later. In which cases is a list actually needed?

## 17. Checklist before using `Stream.toList()`

- Is the target Java version at least **Java 16**?
- Does the caller need to **add/remove/replace/sort** the resulting list?
- Have you distinguished **unmodifiable list** from **fixed-size list**?
- Does the source contain `null` elements? What is the downstream null policy?
- Are the elements in the list immutable or mutable? Is deep immutability required?
- Is there an expectation for data to update with the source after the terminal operation completes?
- Is preserving encounter order or sorting by business criteria required?
- If mutable is needed, have you explicitly used `ArrayList`/`toCollection(ArrayList::new)`?
- Are you depending on internal class, serializability, or identity of the resulting list?
- Are you reusing a stream after a terminal operation or placing dangerous side effects in a parallel pipeline?
- Have you tested **empty data, null, mutable elements, mutation operations, and parallel order**?

**Conclusion:** `Stream.toList()` (Java 16+) collects elements into an **unmodifiable** `List<T>`, forbidding not only size changes but also `set`, `sort`, `replaceAll`, and all other mutators. It preserves encounter order when the source is ordered and can contain null, but **does not freeze the state of element objects**. When a mutable list is needed, explicitly choose `Collectors.toCollection(ArrayList::new)` or copy into an `ArrayList`; when null must be forbidden, use an appropriate contract such as `Collectors.toUnmodifiableList()`.
