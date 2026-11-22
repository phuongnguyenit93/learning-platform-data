# `Collectors.toList()` Does Not Guarantee Implementation Type or Mutability

## 1. Problem and Objectives

When working with Java Streams, we often collect results using:

~~~java
List<String> names = Stream.of("An", "Binh", "Chi")
        .collect(Collectors.toList());
~~~

This line creates a `List<String>` containing the elements from the Stream. However, from its signature and Javadoc, **you cannot conclude that the list is definitely an `ArrayList`, definitely mutable, serializable, or thread-safe**. The `Collectors.toList()` contract does not guarantee those four properties. A specific current JDK build may return an `ArrayList` and allow calling `add`, but that is **not an API guarantee** that a program should depend on.

This lesson belongs to the *Collecting Results* group and addresses the question: **when you need a List with a specific property, which collector or terminal operation should you choose?**

After this lesson, learners should be able to:

1. Accurately explain the contract of `Collectors.toList()` and the limitations of testing on a single JVM.
2. Distinguish `collect(Collectors.toList())` from `Stream.toList()`, `Collectors.toUnmodifiableList()`, and `Collectors.toCollection(ArrayList::new)`.
3. Choose a **mutable List**, **unmodifiable List**, specific implementation type, or intentional structural snapshot.
4. Understand `null` policies, encounter order, duplicate elements, generics, and parallel Streams.
5. Distinguish an unmodifiable List from **immutable elements**, and a `Collections.unmodifiableList` view from `List.copyOf`.
6. Avoid casting to `ArrayList`, relying on the runtime class, calling `add` when not guaranteed, and substituting APIs with different contracts just because they share the name `toList`.
7. Run a standalone Java 17 program, compare outputs, and complete practice exercises.

## 2. The Contract of `Collectors.toList()`

### 2.1. It Is a Collector, Not a List Method

~~~java
List<String> result = Stream.of("b", "a", "b")
        .collect(Collectors.toList());
~~~

In the example above, `Collectors.toList()` creates a `Collector` used as an argument to the `Stream.collect(...)` terminal operation. The result is a `List<String>`. With an ordered source `Stream.of(...)`, the elements have the order `[b, a, b]`. The collector does not automatically remove duplicates or sort.

For example, if you want to deduplicate and sort, you must express those operations explicitly:

~~~java
List<String> result = Stream.of("b", "a", "b")
        .distinct()
        .sorted()
        .collect(Collectors.toList());

System.out.println(result); // [a, b]
~~~

These snippets are code fragments placed inside a method, requiring imports for `java.util.List`, `java.util.stream.Stream`, and `java.util.stream.Collectors`.

### 2.2. Four Unguaranteed Properties

The `Collectors.toList()` Javadoc states **there are no guarantees** on:

| Property | What You Must Not Infer |
| --- | --- |
| **Type** | That the returned List is definitely `ArrayList`, `LinkedList`, or any specific class |
| **Mutability** | That `add`, `remove`, or `set` will definitely succeed or definitely be blocked |
| **Serializability** | That the List can always be Java-serialized |
| **Thread safety** | That the List can be modified or read/written concurrently from multiple threads without synchronization |

These four properties are independent. A mutable `ArrayList` is normally not thread-safe; an unmodifiable List can contain mutable elements; and serializability is not determined solely by the `List` interface name.

**Design implication:** `List<T>` is a static type that syntactically allows writing `list.add(value)`, but whether the call succeeds depends on the contract of the actual object. When an API only promises `List` without promising mutability, code must not treat `add` as guaranteed behavior.

### 2.3. `getClass()` Does Not Elevate an Implementation into a Contract

~~~java
List<String> result = Stream.of("A")
        .collect(Collectors.toList());
System.out.println(result.getClass().getName());
~~~

This is **illustrative code with no fixed stdout according to the specification**. On one JDK, it may print a specific class name, but the Javadoc does not require every JDK/version to return that class.

Similarly, seeing `result.add("B")` succeed on a personal machine is not enough to write a library that promises that behavior. If mutability is required, choose an explicit collection source; if unmodifiability is needed, use an API with the corresponding guarantee.

## 3. Comparing Easily Confused Ways to Collect a List

| API on Java 17 | Result Type | List Mutability Guarantee | What to Remember |
| --- | --- | --- | --- |
| `stream.collect(Collectors.toList())` | `List<T>` | **Not guaranteed** | No promise of concrete type, serialization, or thread safety |
| `stream.toList()` | `List<T>` | **Unmodifiable** | Since Java 16; may contain `null` |
| `stream.collect(Collectors.toUnmodifiableList())` | `List<T>` | **Unmodifiable** | Since Java 10; rejects `null` elements |
| `stream.collect(Collectors.toCollection(ArrayList::new))` | `ArrayList<T>` or `List<T>` variable | **Mutable ArrayList** | Selects implementation via supplier |
| `stream.collect(Collectors.toCollection(LinkedList::new))` | `LinkedList<T>` or `List<T>` variable | **Mutable LinkedList** | Choose only when genuinely needed |

**Similar names do not mean identical contracts.** `Stream.toList()` is a terminal operation on `Stream`, whereas `Collectors.toList()` is a factory for a `Collector`, used with `collect(...)`.

### 3.1. Use `Collectors.toList()` When No Extra Guarantees Are Needed

~~~java
List<String> words = Stream.of("Java", "Lambda")
        .collect(Collectors.toList());
System.out.println(words); // [Java, Lambda]
~~~

If you only read, count, iterate, or pass the list to code that does not rely on mutation or a specific type, this collector is reasonable. There is no need to replace it across an entire codebase just because the Javadoc does not guarantee mutability.

However, if your API requires that callers **cannot modify** the result, `Collectors.toList()` is also unsuitable because it **does not guarantee unmodifiability**.

### 3.2. `Stream.toList()` Guarantees Unmodifiability

~~~java
List<String> words = Stream.of("Java", "Lambda").toList();

// The following call throws UnsupportedOperationException at runtime:
// words.add("Stream");
~~~

`Stream.toList()` from Java 16 onward returns an unmodifiable List. You must not replace `toList()` with `collect(Collectors.toList())` and continue claiming the caller cannot modify it.

Unmodifiable **does not mean** the class must be `List.of(...)`, nor does it automatically make the objects inside immutable.

### 3.3. `Collectors.toUnmodifiableList()` and the Null Rule

~~~java
List<String> words = Stream.of("Java", "Lambda")
        .collect(Collectors.toUnmodifiableList());
~~~

This collector creates an unmodifiable List and **rejects `null` values**, throwing `NullPointerException` if encountered. This is a practical difference from `Stream.toList()`, which allows null elements in Java 17.

### 3.4. Need a Mutable `ArrayList`: Use `toCollection`

~~~java
ArrayList<String> words = Stream.of("Java", "Lambda")
        .collect(Collectors.toCollection(ArrayList::new));

words.add("Stream");
System.out.println(words); // [Java, Lambda, Stream]
~~~

The `ArrayList::new` factory is the explicit way to state the collection type to create. `ArrayList` supports mutation; for example, `add` is guaranteed by the ArrayList contract absent exceptional factors like running out of memory.

If you only want to expose the interface, you can still write:

~~~java
List<String> words = Stream.of("Java", "Lambda")
        .collect(Collectors.toCollection(ArrayList::new));
~~~

The variable is `List<String>` while the supplier creates an `ArrayList`. This helps the external API reduce implementation coupling while internal logic knows the list is mutable.

### 3.5. Choose `LinkedList` Only with Good Reason

~~~java
LinkedList<String> words = Stream.of("A", "B")
        .collect(Collectors.toCollection(LinkedList::new));
~~~

`LinkedList` is not inherently better than `ArrayList`. Consider access patterns, size, memory, frequency of insertions/deletions, and benchmark on a representative workload when performance truly matters.

## 4. Complete Java 17 Program

Create the file **`ListCollectorsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ListCollectorsDemo {
    public static void main(String[] args) {
        // 1. Collect a List without depending on class or mutability.
        List<String> collected = Stream.of("b", "a", "b")
                .collect(Collectors.toList());
        System.out.println("collected=" + collected);

        // 2. Explicitly require a mutable ArrayList.
        List<String> mutable = Stream.of("b", "a")
                .collect(Collectors.toCollection(ArrayList::new));
        mutable.add("c");
        System.out.println("mutable=" + mutable);

        // 3. Stream.toList() guarantees unmodifiability.
        List<String> immutable = Stream.of("b", "a").toList();
        try {
            immutable.add("c");
        } catch (UnsupportedOperationException ex) {
            System.out.println("toList-add=blocked");
        }

        // 4. toUnmodifiableList() also disallows modification.
        List<String> unmodifiable = Stream.of("b", "a")
                .collect(Collectors.toUnmodifiableList());
        try {
            unmodifiable.set(0, "x");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable-set=blocked");
        }

        // 5. Distinguish null policies.
        System.out.println(
                "nullable=" + Stream.of("x", null, "z").toList()
        );
        try {
            Stream.of("x", null)
                    .collect(Collectors.toUnmodifiableList());
        } catch (NullPointerException ex) {
            System.out.println("collector-null=rejected");
        }

        // 6. Unmodifiable view and structural snapshot.
        List<String> backing = new ArrayList<>(List.of("A"));
        List<String> view = Collections.unmodifiableList(backing);
        List<String> snapshot = List.copyOf(backing);
        backing.add("B");
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        // 7. An unmodifiable List can still hold mutable objects.
        StringBuilder builder = new StringBuilder("old");
        List<StringBuilder> readonly = Stream.of(builder).toList();
        builder.append("-new");
        System.out.println("element=" + readonly.get(0));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ListCollectorsDemo.java
java ListCollectorsDemo
~~~

**Exact Stdout (Java 17):**

~~~text
collected=[b, a, b]
mutable=[b, a, c]
toList-add=blocked
unmodifiable-set=blocked
nullable=[x, null, z]
collector-null=rejected
view=[A, B]
snapshot=[A]
element=old-new
~~~

### Output Explanation

1. `collected=[b, a, b]`: collects source elements in order without deduplication. Neither the concrete class nor `add` is tested because they are not guaranteed by the collector.
2. `mutable=[b, a, c]`: the supplier creates an `ArrayList`, so `add` is valid.
3. `toList-add=blocked`: `Stream.toList()` creates an unmodifiable List; calling `add` throws `UnsupportedOperationException`.
4. `unmodifiable-set=blocked`: `Collectors.toUnmodifiableList()` also rejects `set`.
5. `nullable=[x, null, z]`: `Stream.toList()` allows null elements.
6. `collector-null=rejected`: `Collectors.toUnmodifiableList()` rejects null with `NullPointerException`.
7. `view=[A, B]`: `Collections.unmodifiableList` is a view over a mutable source, reflecting the addition of `B` through the original reference.
8. `snapshot=[A]`: `List.copyOf` creates an unmodifiable result matching the structure at copy time; adding `B` to the source does not change the snapshot.
9. `element=old-new`: the unmodifiable list disallows structural modification, but `StringBuilder` remains mutable.

The program demonstrates **guaranteed** API behavior, except specifically that the collected result `[b,a,b]` relies on the encounter order of `Stream.of`. It does not use `getClass()` or mutating `Collectors.toList()` to draw a conclusion without a contract.

## 5. Unmodifiable, Immutable, and Snapshot Are Not the Same

### 5.1. Unmodifiability Is at the List Level

~~~java
StringBuilder builder = new StringBuilder("A");
List<StringBuilder> list = Stream.of(builder).toList();

builder.append("B");
System.out.println(list.get(0)); // AB
~~~

`list.add(...)` is unsupported, but mutating `builder` still works. The List holds references to elements; it **does not create a deep copy**. Therefore, if the contract requires truly immutable data, you must control both the element type and external references.

### 5.2. `Collections.unmodifiableList` Is a View

~~~java
List<String> backing = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(backing);

backing.add("B");
System.out.println(view); // [A, B]
~~~

The wrapper disallows modification **through the view**, but if the backing list changes via another reference, users of the view can see the change. This is not a snapshot.

### 5.3. `List.copyOf` Provides a Structural Snapshot

~~~java
List<String> source = new ArrayList<>(List.of("A"));
List<String> snapshot = List.copyOf(source);

source.add("B");
System.out.println(snapshot); // [A]
~~~

With a mutable ArrayList source, the snapshot structure does not change after `B` is added to the source. However, `List.copyOf` only copies element references; it does not deep-copy mutable objects. It also rejects null. If the source is already a suitable unmodifiable List, Java may return the same instance instead of creating a new object; **do not rely on distinct object identity**.

### 5.4. Combining a Collector with a Finishing Step

~~~java
List<String> result = Stream.of("A", "B")
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));
~~~

The first step creates an `ArrayList` via the supplier; the second step creates an unmodifiable List via `List.copyOf`. This approach is useful when custom finishing logic is needed, but if you only need an unmodifiable List that rejects null, `Collectors.toUnmodifiableList()` is usually shorter.

Do not build complex collector chains just to replace a simple `Stream.toList()` call when there is no additional requirement.

## 6. Null Policy Is a Separate Choice

| Collection Method | Null Policy |
| --- | --- |
| `Stream.toList()` | May contain `null` on Java 17 |
| `Collectors.toUnmodifiableList()` | Rejects `null` |
| `Collectors.toCollection(ArrayList::new)` | Allows `null`, per the ArrayList contract |
| `List.of(...)` | Rejects `null` |
| `List.copyOf(...)` | Rejects `null` elements |
| `Collectors.toList()` | Should not build null requirements by guessing the implementation class |

Snippet requiring a **mutable list that allows null**:

~~~java
List<String> values = Stream.of("A", null, "B")
        .collect(Collectors.toCollection(ArrayList::new));
values.add(null);
~~~

If null data must be rejected, state the policy explicitly in the API. Do not arbitrarily add `filter(Objects::nonNull)` if dropping null elements could hide invalid data: **skipping** and **failing** are two different behaviors.

### 6.1. Nullability and Unmodifiability Are Independent

A List can be **unmodifiable yet contain null**, such as `Stream.of("A", null).toList()`. A mutable List such as ArrayList may also contain no nulls simply because the input data has none. Do not infer null policy solely from mutability.

## 7. Encounter Order, Duplicates, and Parallel Results

### 7.1. The Collector Does Not Sort or Deduplicate

~~~java
List<String> input = List.of("B", "A", "B");

List<String> result = input.stream()
        .collect(Collectors.toList());

System.out.println(result); // [B, A, B]
~~~

If you need `[A, B]`, use:

~~~java
List<String> result = input.stream()
        .distinct()
        .sorted()
        .collect(Collectors.toList());
~~~

`distinct` removes duplicate elements according to `equals`; `sorted` orders by natural order, provided the element type supports comparison and the data is compatible.

### 7.2. Unordered Sources Do Not Give Arbitrary Fixed Order

~~~java
Set<String> set = new HashSet<>(List.of("A", "B", "C"));
List<String> result = set.stream()
        .collect(Collectors.toList());
~~~

This is a code fragment inside a method, requiring imports for `java.util.Set` and `HashSet`. `HashSet` does not guarantee encounter order, so **do not write a specific stdout** for the collected element order. To get alphabetical order, call `sorted()` before `collect(...)`.

### 7.3. Parallel Collect Differs from a Thread-Safe List

~~~java
List<Integer> numbers = IntStream.range(0, 100)
        .parallel()
        .boxed()
        .collect(Collectors.toList());
~~~

The Stream framework coordinates collecting results according to the collector and source order; running the pipeline in parallel **does not make the resulting list guaranteed thread-safe**. You should not share it for concurrent mutation across threads without proper synchronization.

Anti-pattern:

~~~java
List<Integer> shared = new ArrayList<>();
IntStream.range(0, 100)
        .parallel()
        .forEach(shared::add);
~~~

A shared `ArrayList` mutated from multiple threads risks race conditions, missing elements, and inconsistent state. Replace it with:

~~~java
List<Integer> numbers = IntStream.range(0, 100)
        .parallel()
        .boxed()
        .toList();
~~~

If you need a mutable result, use `collect(Collectors.toCollection(ArrayList::new))`. Do not use `parallel().forEach` to build a collection outside the pipeline.

## 8. Do Not Cast the Result to `ArrayList`

Risky snippet:

~~~java
ArrayList<String> values = (ArrayList<String>)
        Stream.of("A", "B").collect(Collectors.toList());
~~~

It may run on a JDK that currently returns ArrayList, but it is **not guaranteed by contract**. If the implementation changes, the cast can throw `ClassCastException`. Casting also does not turn an unknown List into a mutable or thread-safe one.

Explicit approach:

~~~java
ArrayList<String> values = Stream.of("A", "B")
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Or when copying from a List returned by another API:

~~~java
List<String> external = service.getNames();
List<String> mutableCopy = new ArrayList<>(external);
mutableCopy.add("new");
~~~

The second snippet is an **illustrative example**, requiring `service.getNames()` to be defined in a real application. A structural copy guarantees the new list is mutable, though object element references are still shared.

## 9. Differences in Generic Type Inference

The two APIs can also differ in how generics are inferred.

~~~java
List<CharSequence> a = Stream.of("A", "B")
        .collect(Collectors.toList());
~~~

In Java 17, the compiler can infer the collector's type from the target type in the `collect` call.

However:

~~~java
// Error: Stream<String>.toList() returns List<String>.
List<CharSequence> b = Stream.of("A", "B").toList();
~~~

`List<String>` is not a subtype of `List<CharSequence>` because Java generics are invariant (*invariance*). Fix it with an explicit element type:

~~~java
List<CharSequence> b =
        Stream.<CharSequence>of("A", "B").toList();
~~~

Do not use raw `List` or cast `(List<CharSequence>)(List<?>)...` to bypass the compiler. The fact that one API has different type inference capabilities does not change the fact that `Collectors.toList()` still does not guarantee mutability or class.

## 10. Downstream Collector in `groupingBy`

`Collectors.toList()` is useful as a downstream collector:

~~~java
record Person(String name, String team) {}

List<Person> people = List.of(
        new Person("An", "A"),
        new Person("Binh", "B"),
        new Person("Chi", "A")
);

Map<String, List<Person>> groups = people.stream()
        .collect(Collectors.groupingBy(
                Person::team,
                Collectors.toList()));
~~~

This is a code fragment inside a class and method, requiring imports for `List`, `Map`, and `Collectors`. Group A members include An and Chi; group B includes Binh. However, the List for **each group** also only carries the guarantees of `Collectors.toList()`: no guarantee of mutability or concrete type.

If each group needs to be a mutable ArrayList:

~~~java
Map<String, List<Person>> groups = people.stream()
        .collect(Collectors.groupingBy(
                Person::team,
                Collectors.toCollection(ArrayList::new)));
~~~

Similarly, `groupingBy` does not guarantee a specific Map type in overloads without a map factory. If an API requires a specific map implementation, use the overload that accepts an explicit supplier. With nested data, unmodifiability at the List level does not automatically protect the Map and vice versa; define the contract for each level.

## 11. API Selection Table by Goal

| You Want | Choose | Why |
| --- | --- | --- |
| Collect a List for reading only, no concrete type needed | `collect(Collectors.toList())` | Does not require missing guarantees |
| Unmodifiable List, Java 16+, may contain null | `stream.toList()` | Guarantees unmodifiability |
| Unmodifiable collector that rejects null | `collect(Collectors.toUnmodifiableList())` | Clear guarantee and null policy |
| Mutable ArrayList | `collect(Collectors.toCollection(ArrayList::new))` | Supplier determines type |
| Mutable LinkedList | `collect(Collectors.toCollection(LinkedList::new))` | Supplier determines type |
| Mutable copy from an external List | `new ArrayList<>(external)` | Creates an independent, structurally mutable copy |
| Unmodifiable structural snapshot, no nulls | `List.copyOf(source)` | Does not reflect later structural mutations |
| Unmodifiable view over a backing List | `Collections.unmodifiableList(source)` | Blocks writes via view, not a snapshot |
| Grouping with a downstream List | `groupingBy(key, toList())` or `toCollection` | Choose the contract for each group's List |

**There is no single best option for all code.** `Collectors.toList()` is appropriate when you do not depend on properties it does not promise. The mistake is **attributing to it a guarantee that the Javadoc does not make**.

## 12. Common Mistakes

### 12.1. Calling `add` Assuming It Always Works

~~~java
List<String> result = values.stream()
        .collect(Collectors.toList());

// Do not rely on the following line always succeeding:
result.add("new");
~~~

If adding elements is required, choose `toCollection(ArrayList::new)` or a mutable copy. If you only need to collect, changing the collector is unnecessary.

### 12.2. Casting Based on the Current Implementation

~~~java
ArrayList<String> a = (ArrayList<String>)
        values.stream().collect(Collectors.toList());
~~~

This risks `ClassCastException` when the environment changes. Choose an explicit supplier or remove the class dependency.

### 12.3. Assuming Unmodifiable Means Deeply Immutable

~~~java
List<StringBuilder> list =
        Stream.of(new StringBuilder("A")).toList();
list.get(0).append("B"); // Element mutates.
~~~

The List disallows adding/removing/replacing elements via the List API, but element objects can mutate. If true immutability is required, design immutable element types or deep-copy.

### 12.4. Assuming Parallel Streams Return a Thread-Safe List

`parallel()` is a way of organizing pipeline execution, not a request for a thread-safe result List. `Collectors.toList()` does not promise a concurrent-safe result. Evaluate synchronization whenever a List is actually shared across threads.

### 12.5. Confusing `List.copyOf` with a View

`List.copyOf(source)` creates an unmodifiable result matching the current structure of `source`. `Collections.unmodifiableList(source)` is a wrapper looking into the backing list. If the source changes afterward, the view reflects it while the snapshot does not reflect structural changes.

### 12.6. Replacing `Stream.toList()` with the Similarly Named Collector

Changing `stream.toList()` to `stream.collect(Collectors.toList())` can lose the unmodifiability guarantee. Conversely, replacing the collector with the method can break code that relies on mutating the list. Read the contract before refactoring.

## 13. Exercises and Hints

**Exercise 1 — State the contract accurately.** For `Stream.of("A","B").collect(Collectors.toList())`, name the four properties that are not guaranteed. Answer: concrete implementation, mutability, serializability, thread safety.

**Exercise 2 — Mutable List.** Collect `["Java","Stream"]` and add `"API"`. Write `Collectors.toCollection(ArrayList::new)`; the result is `[Java, Stream, API]`. Explain why `Collectors.toList()` should not be the basis of a guarantee that `add` always succeeds.

**Exercise 3 — Unmodifiable.** Collect using `Stream.toList()`, and test `add` and `set` inside `try/catch (UnsupportedOperationException)`. Compare with the contract of `Collectors.toList()`.

**Exercise 4 — Null policy.** With `Stream.of("A",null,"B")`, test `toList()`, `toUnmodifiableList()`, and `toCollection(ArrayList::new)`. State the result or exception, and choose the appropriate approach when business logic allows null.

**Exercise 5 — View and snapshot.** Create a single-element `ArrayList`, create `Collections.unmodifiableList` and `List.copyOf`, then add an element to the backing list. Predict the contents of both lists.

**Exercise 6 — Mutable elements.** Collect a `StringBuilder` with `Stream.toList()` and then modify the `StringBuilder` content. Explain why the result still changes and suggest switching to `String` if a value snapshot is needed.

**Exercise 7 — Ordered and unordered.** Compare the resulting Lists from `List.stream()` and `HashSet.stream()`; explain why you cannot assert the order of a HashSet. Add `sorted()` to obtain a deterministic order.

**Exercise 8 — Parallel.** Run `IntStream.range(0,1000).parallel().boxed().toList()`; verify size 1000 and the first/last elements. Compare with using `parallel().forEach(shared::add)` on a shared ArrayList and state the risks.

**Exercise 9 — Grouping.** Create `record Person(String name,String team)`. Group using `groupingBy(Person::team,toList())`, then using `groupingBy(Person::team,toCollection(ArrayList::new))`. When is the second form needed?

**Exercise 10 — Generics.** Try `List<CharSequence> x = Stream.of("a").collect(Collectors.toList());` and `List<CharSequence> y = Stream.of("a").toList();`. Explain the type inference difference and fix the second line using `Stream.<CharSequence>of("a").toList()`.

**Exercise 11 — API design.** A service returns a list to a frontend or plugin. Before choosing how to collect it, determine whether the caller may modify it, whether nulls are needed, whether a snapshot is needed, whether elements are mutable, and whether the list is shared across threads. Write tests for the guarantees you actually require.

## 14. Review Checklist

1. Are you using `Collectors.toList()` or `Stream.toList()`? The two APIs do not share the same mutability contract.
2. Is `add`/`remove`/`set` required to always succeed? If so, choose an explicit mutable collection.
3. Are you casting the collector result to `ArrayList` because you observed `getClass()`?
4. Is an unmodifiable List required for the caller? If so, use an API with an explicit guarantee.
5. Do you understand the `null` policy? `toUnmodifiableList` and `List.copyOf` reject null.
6. Do you need a snapshot or an unmodifiable view? They are two different concepts.
7. Are the elements mutable objects? An unmodifiable List does not deep-copy.
8. Is serializability or thread safety required? `Collectors.toList()` guarantees neither.
9. Does the source have an encounter order? If a deterministic order is needed, is an appropriate `sorted` step included?
10. Are you using `parallel().forEach` to mutate a shared collection?
11. Do you have Lists created by `groupingBy(...,toList())`? Do not assume the nested Lists are mutable.
12. Does the code depend on the contract or on implementation details of one JDK build?

## 15. Summary and References

**`Collectors.toList()` returns a List without guaranteeing concrete type, mutability, serializability, or thread safety.** Even though a current implementation may return a mutable `ArrayList`, do not write code that depends on it.

When you need an **unmodifiable List**, `Stream.toList()` from Java 16 onward has a clear contract and may contain null; `Collectors.toUnmodifiableList()` is also unmodifiable but rejects null. When you need a **mutable ArrayList**, use `Collectors.toCollection(ArrayList::new)` or create `new ArrayList<>(source)`. When you need a **structural snapshot**, consider `List.copyOf`; when you need an unmodifiable wrapper that reflects a backing list, use `Collections.unmodifiableList`.

Finally, **unmodifiable does not mean deeply immutable**, and collecting with a parallel Stream does not guarantee the resulting list is safe for concurrent mutation. Choose based on API requirements rather than behavior observed in a single environment.

**Authoritative sources:** Java SE 17 Javadoc for `java.util.stream.Collectors` (`toList`, `toUnmodifiableList`, `toCollection`, `groupingBy`), `java.util.stream.Stream.toList`, `java.util.List.copyOf`, `java.util.Collections.unmodifiableList`, and `java.util.ArrayList`.
