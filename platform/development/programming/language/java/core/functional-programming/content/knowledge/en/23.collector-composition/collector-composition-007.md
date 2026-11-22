# `Collectors.collectingAndThen()` for Finishing Results in Java

## 1. Problem: collected results need an additional finishing step

In Java Streams, `collect(...)` can aggregate multiple elements into a list, Map, sum, statistics, or another result object. Sometimes the direct output of a collector **is not yet the final form** that the business logic wants to receive.

For example: we need to collect names into a `List<String>` and return a list that does not allow structural modification; group data by key and make **each list in the group** unable to add/remove elements; or find the object with the highest score, then get that object's name and throw an error when there are no elements.

A sequential way to write it:

~~~java
List<String> temporary = names.stream()
        .collect(Collectors.toCollection(ArrayList::new));

List<String> result = List.copyOf(temporary);
~~~

This approach is reasonable, but when logic accepts a `Collector` as a parameter — especially as a downstream of `groupingBy` — combining "collecting" and "finishing" into one collector can be clearer and more reusable. Java provides:

~~~java
Collectors.collectingAndThen(downstream, finisher)
~~~

**`collectingAndThen` is a composite collector:** it uses a child collector (`downstream`) to accumulate the result first, then applies a finishing function (`finisher`) to that result.

After this lesson, you should be able to:

1. Read the contract of `collectingAndThen(downstream, finisher)` and the two phases of collecting → finishing correctly.
2. Distinguish a **collector's finisher** from `Stream.map`, `Collectors.mapping`, and `Function.andThen`.
3. Choose an unmodifiable `List` output clearly using `List.copyOf`, understanding its limits regarding `null` and mutable elements.
4. Use `collectingAndThen` as a downstream in `groupingBy` to finish **each group**.
5. Convert `Optional<T>` from `maxBy`/`minBy` into another value or throw a defined error.
6. Understand that the finisher can change the result type; understand that `Collector.Characteristics.IDENTITY_FINISH` no longer applies.
7. Identify cases where `collectingAndThen` is unnecessary, exceptions, memory cost, parallel pipelines, and the responsibility of keeping data immutable.
8. Compile, run standalone **Java 17+** examples, and practice exercises with empty cases, `null`, and multiple groups.

## 2. Generic signature and type meaning

### 2.1. API signature

According to the generic type model, the method is:

~~~java
public static <T, A, R, RR> Collector<T, A, RR> collectingAndThen(
        Collector<T, A, R> downstream,
        Function<R, RR> finisher)
~~~

This is an **illustrative signature of the Java library**, not a method you need to implement yourself. The type parameters mean:

| Symbol | Role |
| --- | --- |
| `T` | The input element type of the Stream |
| `A` | The internal accumulation structure type (accumulation type) of the downstream |
| `R` | The result type that the downstream produces after completion |
| `RR` | The final result type after the finisher is applied |
| `Collector<T,A,RR>` | The composite collector, accepting `T` and returning `RR` |

Important point: `R` **can differ from `RR`**. The finisher is not only for wrapping a List; it can turn an `Optional<Work>` into a `String`, a list of `Work` into a `Summary`, or a statistics object into a business report.

In practice, callers usually do not need to write `A` because the compiler infers generics from the downstream collector and finisher. When an example nests multiple collectors, you can extract them into variables with explicit types to make the code easier to read and compiler errors easier to understand.

### 2.2. Two-stage diagram

~~~text
Stream<T>
   |
   v
downstream Collector<T, A, R>
   |  [downstream's supplier + accumulator + combiner + finisher]
   v
Intermediate result R
   |
   v
Function<R, RR> finisher
   |
   v
Final result RR
~~~

Example:

~~~java
List<String> result = Stream.of("A", "B")
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));
~~~

`toCollection(ArrayList::new)` accumulates elements into an `ArrayList`. After the downstream finishes, `List.copyOf` creates a structurally unmodifiable `List` based on the current state.

This is a **code snippet inside a method** with imports `java.util.List`, `java.util.ArrayList`, `java.util.stream.Stream`, and `java.util.stream.Collectors`. There is no automatic console printing operation.

### 2.3. Finisher is not a lambda run on each element

If you want to convert lowercase to uppercase **for each name**, use `map`:

~~~java
List<String> names = Stream.of("an", "binh", "chi")
        .map(String::toUpperCase)
        .toList();
~~~

If you want to transform **the entire result after it has been collected**, use `collectingAndThen`:

~~~java
List<String> names = Stream.of("an", "binh", "chi")
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf));
~~~

The finisher in the second example receives **a List**, not each individual `String`. In normal collection without grouping, the finishing step is applied to the downstream's result after all necessary accumulation and combining are done, not once per input element.

Do not use a finisher to pretend to replace `map`: it is both at the wrong processing layer and may require collecting all data before transforming it.

## 3. Internal mechanism of the collector

### 3.1. Review of Collector components

Conceptually, a `Collector<T,A,R>` has these main components:

- **supplier:** creates the accumulation container `A`.
- **accumulator:** adds an element `T` into `A`.
- **combiner:** combines two accumulated results, especially important for parallel processing.
- **finisher:** transforms the accumulated state `A` into `R`.
- **characteristics:** describes properties such as `CONCURRENT`, `UNORDERED`, and `IDENTITY_FINISH`.

`collectingAndThen` does not require you to rewrite the supplier/accumulator/combiner steps yourself. It **delegates collection to the downstream**, then adds a new finisher layer applied to the result `R`.

Since the downstream may also have its own finisher, the conceptual order is:

~~~text
supplier -> accumulator (multiple times) -> combiner (when needed)
         -> downstream finisher
         -> collectingAndThen finisher
~~~

Note that this is a **logical model**; the Stream framework may optimize execution depending on collector characteristics. Do not rely on the number of internal method calls or specific thread ordering to perform business side effects.

### 3.2. The `IDENTITY_FINISH` characteristic

A collector marked with `Collector.Characteristics.IDENTITY_FINISH` allows skipping the finisher step because the accumulated result can be used directly under the corresponding contract. However, `collectingAndThen` is created **to add a finishing step**, so it does not preserve the downstream's `IDENTITY_FINISH` characteristic, even if the original downstream had it.

This ensures the finishing function remains in the logical path of the composite collector.

Other characteristics may be inherited from the downstream according to the contract of `collectingAndThen`, but **do not** infer that the returned List is thread-safe, or that side effects in the finisher will automatically be synchronized by the framework. Safe behavior must be based on the entire collector contract, result type, and post-collection usage.

### 3.3. An example of changing the output type

~~~java
long totalCharacters = Stream.of("An", "Binh", "Chi")
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                words -> words.stream()
                        .mapToLong(String::length)
                        .sum()));

System.out.println(totalCharacters); // 9
~~~

The finisher receives `List<String>` and returns `Long` (via boxing), so the `collect(...)` result is assigned to primitive `long` via unboxing. However, if the goal is **only** to count characters, a simpler/more efficient way is:

~~~java
long totalCharacters = Stream.of("An", "Binh", "Chi")
        .mapToLong(String::length)
        .sum();
~~~

This is an **example of the technique's limits**: just because you can use `collectingAndThen` does not mean you should collect an intermediate List for every aggregation.

## 4. Finishing a list with `List.copyOf`

### 4.1. When an unmodifiable result is needed

~~~java
List<String> result = Stream.of("Java", "Stream")
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));

// result.add("Lambda"); // At runtime: UnsupportedOperationException.
~~~

First, the downstream accumulates into an `ArrayList`; next, `List.copyOf` creates a structurally **unmodifiable** List at the time of finishing. Callers cannot arbitrarily add/remove/modify elements through List mutation methods.

The snippet is presented to illustrate the separation: *collect mutably internally* then *return a non-modifiable result externally*. If you only need an unmodifiable List, there are shorter APIs (section 6), so you do not always need to write collectingAndThen.

### 4.2. `List.copyOf` is a structural snapshot, not a deep copy

~~~java
StringBuilder builder = new StringBuilder("old");

List<StringBuilder> result = Stream.of(builder)
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));

builder.append("-new");
System.out.println(result.get(0)); // old-new
~~~

The `result` list does not allow modifying element references via the List API, but the `StringBuilder` inside is still a **mutable object**. `List.copyOf` does not automatically deep-copy the data of every element. If data immutability down to the inner object level is required, choose immutable elements or create a meaningful business deep copy.

`List.copyOf` may also reuse the instance when the input is already a suitable unmodifiable List, so do not assert that it must always allocate a brand-new List by identity.

### 4.3. Important `null` policy

`List.copyOf` **does not accept null elements**. For example:

~~~java
List<String> result = Stream.of("A", null)
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));
~~~

When the `List.copyOf` finisher runs, the example throws `NullPointerException`. The downstream `toCollection(ArrayList::new)` allows null, but **the finishing step** has a different contract.

If you want an unmodifiable List that **allows null** (on Java 17), `Stream.toList()` has a more suitable contract. If you want to reject null and return an unmodifiable List, you can use `Collectors.toUnmodifiableList()` without needing an extra finisher.

Do not arbitrarily use `filter(Objects::nonNull)` to hide invalid data unless dropping null elements is an official business decision.

### 4.4. Protecting the List after collection does not protect all related data

A method may return an unmodifiable List while still exposing mutable objects inside, or have external state modified when callbacks run. You need to distinguish clearly:

| What you want | Does `List.copyOf` solve it? |
| --- | --- |
| Callers cannot `add/remove/set` directly on the List | Yes |
| Structural changes to a mutable source List affecting the result | No, with a proper structural snapshot |
| A `StringBuilder` element having its state changed via another reference | No |
| An object containing the List automatically becoming thread-safe | No |
| A null element being accepted | No |
| Returning a new List identity at all costs | Not guaranteed |

## 5. A different finisher type: `Optional` to business value

### 5.1. `Collectors.maxBy` returns `Optional<T>`

~~~java
Optional<Integer> largest = Stream.of(4, 9, 2)
        .collect(Collectors.maxBy(Integer::compareTo));

System.out.println(largest); // Optional[9]
~~~

This is a snippet requiring imports for `Optional`, `Stream`, and `Collectors`. `maxBy` cannot always return an `Integer` value directly, because the Stream might be empty; so it returns `Optional<Integer>`.

If the business rule requires "there must be at least one element", you can finish with `Optional::orElseThrow` or an equivalent lambda:

~~~java
int largest = Stream.of(4, 9, 2)
        .collect(Collectors.collectingAndThen(
                Collectors.maxBy(Integer::compareTo),
                value -> value.orElseThrow()));

System.out.println(largest); // 9
~~~

The final result is no longer `Optional<Integer>` but `Integer`, which is assigned to `int`.

### 5.2. Defining a policy for empty input

~~~java
int largest = Stream.<Integer>empty()
        .collect(Collectors.collectingAndThen(
                Collectors.maxBy(Integer::compareTo),
                value -> value.orElseThrow()));
~~~

The snippet above **intentionally throws `NoSuchElementException`** because there is no largest element. This is a valid policy **if** the domain does not allow an empty set and has defined the error to return to the caller. If an empty set is normal, you should choose:

~~~java
Optional<Integer> largest = Stream.<Integer>empty()
        .collect(Collectors.maxBy(Integer::compareTo));
~~~

Or choose a domain-approved default value, with a clear explanation. Do not force an Optional into a value and throw an error just to make code shorter.

### 5.3. When the final value is a field of an object

~~~java
record Work(String title, int points) {}

String topTitle = works.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.maxBy(
                        Comparator.comparingInt(Work::points)),
                optional -> optional.orElseThrow().title()));
~~~

This is a **snippet inside a class/method** with a `works` variable of type `List<Work>` and imports `Comparator`, `Collectors`. The finisher receives `Optional<Work>`, enforces element presence per policy, then returns `String`. The complete example in section 9 verifies this case.

If you only want to get a single maximum value and do not need to build a Collector to nest into another API, `stream.max(comparator).orElseThrow()` is usually shorter. `collectingAndThen` is especially useful when you need **a complete collector as the downstream** of another collector.

## 6. Avoiding overuse: comparing with shorter APIs

Some results can be created directly using a terminal operation or a specialized collector:

| Goal | Direct way | When to use `collectingAndThen`? |
| --- | --- | --- |
| Unmodifiable List, Java 16+ | `stream.toList()` | Need a `Collector` to nest into `groupingBy`/another API |
| Unmodifiable List, no nulls | `collect(toUnmodifiableList())` | Need an additional finishing step beyond existing collectors |
| Sum of integers | `mapToInt(...).sum()` | Finisher genuinely needs to transform a complex collected result |
| Element count | `count()` | Need to convert another downstream collector into a domain result |
| Maximum value | `max(comparator)` | Need to package as a collector as a structural component |
| Specific mutable List type | `collect(toCollection(ArrayList::new))` | After collecting, need a finishing operation with its own contract |

**Minimal example:**

~~~java
List<String> direct = Stream.of("A", "B").toList();
~~~

In Java 17, this List is unmodifiable and can contain null. There is no need to write `collectingAndThen(toList(), List::copyOf)` just to get an unmodifiable List, especially if null is valid data.

### 6.1. `Collectors.toList()` does not guarantee mutability

~~~java
List<String> names = Stream.of("A", "B")
        .collect(Collectors.toList());
~~~

The Javadoc of `Collectors.toList()` **makes no guarantees on concrete type, mutability, serializability, or thread safety**. Therefore, if you want `List.copyOf` to make the unmodifiable output explicit, using `collectingAndThen(Collectors.toList(), List::copyOf)` is a viable pattern for non-null data, but you must not claim that downstream `toList()` always returns a mutable `ArrayList`.

If you need an internal mutable `ArrayList` by contract, choose `toCollection(ArrayList::new)`. The `List.copyOf` finisher then does not depend on an incidental implementation detail of the `toList()` collector.

### 6.2. `Collections.unmodifiableList` differs from `List.copyOf`

~~~java
List<String> backing = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(backing);
List<String> snapshot = List.copyOf(backing);

backing.add("B");

System.out.println(view);     // [A, B]
System.out.println(snapshot); // [A]
~~~

`Collections.unmodifiableList` returns **a view that cannot be modified through the wrapper**, but can reflect structural changes in the backing source. `List.copyOf` gives an unmodifiable structural snapshot against the mutable backing list in the example. Neither makes mutable elements deeply immutable.

If you use `collectingAndThen(toCollection(ArrayList::new), Collections::unmodifiableList)`, the newly collected backing list is usually not exposed separately, but the finisher still creates a **view**, not a deep snapshot guarantee. Choose `List.copyOf` when you want a clear structural snapshot contract without nulls.

## 7. `collectingAndThen` as a downstream of `groupingBy`

### 7.1. Without grouping directly, it only finishes one result

With:

~~~java
List<String> result = source.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf));
~~~

The finisher operates on the final List of **the entire collect operation**. It does not process each element and does not create a separate result per key, because there is no grouping step.

### 7.2. Nesting inside `groupingBy` finishes each group

Example:

~~~java
Map<String, List<String>> byTeam = people.stream()
        .collect(Collectors.groupingBy(
                Person::team,
                Collectors.collectingAndThen(
                        Collectors.mapping(
                                Person::name,
                                Collectors.toList()),
                        List::copyOf)));
~~~

This is a snippet inside a class with `record Person(String name, String team) {}`, a `people` variable of type `List<Person>`, and imports `Map`, `Collectors`, `List`. The flow for each group key:

~~~text
All input Person elements
         |
         v
groupingBy(Person::team)
         |
         +-- Team A --> mapping(Person::name) --> toList()
         |                                    --> List.copyOf()
         |
         +-- Team B --> mapping(Person::name) --> toList()
                                              --> List.copyOf()
~~~

`Collectors.mapping` turns **each `Person` into a name** before the downstream receives it; `collectingAndThen` turns **a collected List of names for a group** into an unmodifiable List.

**Important:** `List.copyOf` in the downstream only protects **the value Lists**; it does not automatically make the `Map` containing the groups unmodifiable. You can still `put` a new group if the resulting Map allows it, depending on the chosen map factory/collector contract. If you want both the Map and each List to be unmodifiable, you need to design **two-level** protection.

### 7.3. Choose `TreeMap` if you want clear key ordering

~~~java
Map<String, List<String>> byTeam = people.stream()
        .collect(Collectors.groupingBy(
                Person::team,
                TreeMap::new,
                Collectors.collectingAndThen(
                        Collectors.mapping(
                                Person::name,
                                Collectors.toList()),
                        List::copyOf)));
~~~

This is an example requiring `TreeMap` to be imported. `TreeMap` sorts keys according to natural ordering or a provided comparator. Thus printing the `Map` can have a deterministic group order, instead of assuming `groupingBy` by default returns `HashMap` or preserves insertion order.

With `Collectors.mapping(Person::name, toList())`, the order of names in each group on an ordered Stream usually reflects the corresponding encounter order, without automatically sorting the names. If names need to be sorted alphabetically, add appropriate logic (for example, collecting in the downstream and sorting in the finisher), while noting cost and null policy.

### 7.4. Per-group statistics using a finisher

A finisher can create a **group summary** rather than just a List:

~~~java
record Summary(int count, int highest) {}

Map<String, Summary> reports = works.stream()
        .collect(Collectors.groupingBy(
                Work::group,
                TreeMap::new,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        items -> new Summary(
                                items.size(),
                                items.stream()
                                     .mapToInt(Work::points)
                                     .max()
                                     .orElseThrow()))));
~~~

This is an illustrative snippet inside a class defining `Work` with `group()`/`points()` accessors, a `Summary` record, a `works` variable of type `List<Work>`, and corresponding imports. Each group has an accumulated List; the finisher computes the element count and highest score, then creates a record.

**Trade-off:** this approach requires **collecting each group into a List**, then iterating over the List to compute the maximum. For large data, you can use a `summarizingInt` downstream or a suitable custom collector to avoid storing all objects, then convert `IntSummaryStatistics` into a record via the finisher. Correctness and data cost should be evaluated together.

### 7.5. Two-level finishing: each List and the entire Map

A pattern seen in APIs returning read-only data:

~~~java
Map<String, List<String>> immutableTopLevel =
        people.stream().collect(
                Collectors.collectingAndThen(
                        Collectors.groupingBy(
                                Person::team,
                                Collectors.collectingAndThen(
                                        Collectors.mapping(
                                                Person::name,
                                                Collectors.toList()),
                                        List::copyOf)),
                        Map::copyOf));
~~~

The `List.copyOf` step finishes **each group List**; the `Map.copyOf` step finishes **the overall Map**. `Map.copyOf` creates an unmodifiable Map with the mappings at copy time, but **does not promise to preserve the iteration order of the source Map**. It rejects null keys and values; `List.copyOf` rejects null elements. If key ordering is an API requirement, design a snapshot/Map type with an appropriate ordering contract, rather than assuming `Map.copyOf` preserves `TreeMap` order.

## 8. `mapping`, `filtering`, and `collectingAndThen`: distinguishing layers

Composite collectors often appear together but answer different questions:

| Collector | Which layer does it run at? | Usage example |
| --- | --- | --- |
| `mapping(mapper, downstream)` | Transforms **each element** before the downstream collects | Person → name, then collect names |
| `filtering(predicate, downstream)` | Decides whether each element enters the downstream | Keep only qualifying Work in each group |
| `flatMapping(mapper, downstream)` | Expands each element into a Stream of multiple elements | Each Work → list of tags |
| `collectingAndThen(downstream, finisher)` | Finishes **the downstream's result** | List of names → unmodifiable List |
| `groupingBy(classifier, downstream)` | Splits elements by key; calls downstream for each group | Group Work items by group |
| `teeing(downstream1, downstream2, merger)` | Logically collects in parallel into two results then merges | Count + max → Summary |

### Easily confused example

~~~java
Collectors.mapping(Work::title, Collectors.toList())
~~~

It turns **each Work** into a `String` and then collects. Whereas:

~~~java
Collectors.collectingAndThen(
        Collectors.toList(),
        items -> items.size())
~~~

It collects **the entire List** and then returns the size. If the goal is only to count, `Collectors.counting()` is usually cleaner and does not require keeping objects in memory.

Both collectors can be combined in `groupingBy` when you need both to transform elements and finish the final result, but you should not create deeply nested pipelines just to show off technique.

## 9. Complete Java 17 program and stdout verification

The program below demonstrates three useful cases: creating an unmodifiable List, finishing results **by group**, and turning `Optional<Work>` into the Work's title. It also checks two error branches: an empty set with `orElseThrow` and null data with `List.copyOf`.

Create the file **`CollectingAndThenDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectingAndThenDemo {

    record Work(String group, String title, int points) {}
    record Summary(int count, int highest) {}

    public static void main(String[] args) {
        List<Work> input = List.of(
                new Work("core", "A", 10),
                new Work("web", "B", 20),
                new Work("core", "C", 30),
                new Work("web", "D", 40)
        );

        // 1. Collect into ArrayList, finish into an unmodifiable List.
        List<String> titles = input.stream()
                .map(Work::title)
                .collect(Collectors.collectingAndThen(
                        Collectors.toCollection(ArrayList::new),
                        List::copyOf));
        System.out.println("titles=" + titles);

        try {
            titles.add("E");
        } catch (UnsupportedOperationException ex) {
            System.out.println("titles-add=blocked");
        }

        // 2. Finish each group's List after mapping.
        Map<String, List<String>> byGroup = input.stream()
                .collect(Collectors.groupingBy(
                        Work::group,
                        TreeMap::new,
                        Collectors.collectingAndThen(
                                Collectors.mapping(
                                        Work::title,
                                        Collectors.toList()),
                                List::copyOf)));
        System.out.println("groups=" + byGroup);

        // 3. Transform the List in each group into a Summary record.
        Map<String, Summary> summaries = input.stream()
                .collect(Collectors.groupingBy(
                        Work::group,
                        TreeMap::new,
                        Collectors.collectingAndThen(
                                Collectors.toList(),
                                items -> new Summary(
                                        items.size(),
                                        items.stream()
                                             .mapToInt(Work::points)
                                             .max()
                                             .orElseThrow()))));
        System.out.println("summaries=" + summaries);

        // 4. Transform Optional<Work> into String.
        String top = input.stream()
                .collect(Collectors.collectingAndThen(
                        Collectors.maxBy(
                                Comparator.comparingInt(Work::points)),
                        optional -> optional.orElseThrow().title()));
        System.out.println("top=" + top);

        // 5. No Work: orElseThrow defines the error policy.
        try {
            Stream.<Work>empty()
                    .collect(Collectors.collectingAndThen(
                            Collectors.maxBy(
                                    Comparator.comparingInt(Work::points)),
                            optional -> optional.orElseThrow().title()));
        } catch (NoSuchElementException ex) {
            System.out.println("empty=failed");
        }

        // 6. List.copyOf finisher rejects null elements.
        try {
            Stream.of("A", null)
                    .collect(Collectors.collectingAndThen(
                            Collectors.toCollection(ArrayList::new),
                            List::copyOf));
        } catch (NullPointerException ex) {
            System.out.println("null=rejected");
        }
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac -encoding UTF-8 CollectingAndThenDemo.java
java CollectingAndThenDemo
~~~

**Exact stdout:**

~~~text
titles=[A, B, C, D]
titles-add=blocked
groups={core=[A, C], web=[B, D]}
summaries={core=Summary[count=2, highest=30], web=Summary[count=2, highest=40]}
top=D
empty=failed
null=rejected
~~~

### 9.1. Why does `titles` preserve the order A, B, C, D?

The `List<Work>` source has an encounter order, `map(Work::title)` preserves order, and then the `toCollection(ArrayList::new)` downstream collects the titles sequentially. `List.copyOf` creates an unmodifiable List with the same element order. Thus `titles=[A, B, C, D]`.

### 9.2. Why is `titles.add("E")` blocked?

The `List.copyOf` finisher returns an unmodifiable List. Calling `add` throws `UnsupportedOperationException` and the program prints `titles-add=blocked`. This blocking comes from **the chosen finisher**, not from `Collectors.toList()` or an inherent property of every List.

### 9.3. Why are the two groups ordered core, web?

`groupingBy(Work::group, TreeMap::new, downstream)` uses `TreeMap` as the result Map; the key `"core"` comes before `"web"` according to the natural ordering of `String`. Each group uses `mapping(Work::title, toList())` to collect titles, then `List.copyOf` finishes that group's List. Therefore `groups={core=[A, C], web=[B, D]}`.

The fact that the inner List cannot be modified does not automatically guarantee the outer Map cannot be modified. Here `TreeMap` is still a mutable Map; an API needing a two-level immutability boundary must be designed separately.

### 9.4. Why is Summary created for each group?

The core group has two Work items with `points=10,30`, and the web group has `points=20,40`. The finisher on each group List creates `Summary[count=2, highest=30]` or `Summary[count=2, highest=40]`. It does not run once per Work, but on **the collected result for the corresponding group**.

### 9.5. Why is top D, and why does an empty set cause an error?

`maxBy(comparingInt(Work::points))` returns `Optional<Work>`. The element with the highest points is D with 40 points; the finisher extracts `title`, so it prints `top=D`. When the source is empty, `maxBy` returns `Optional.empty()`; the `orElseThrow` policy leads to `NoSuchElementException`, which is caught to print `empty=failed`.

### 9.6. Why is null rejected?

`toCollection(ArrayList::new)` can collect `null` into an `ArrayList`, but the `List.copyOf` finisher step does not allow null. The exception arises at finishing time and is caught to print `null=rejected`. This shows that the downstream and the finisher can have **different contracts**.

## 10. Empty input, `null`, exceptions, and side effects

### 10.1. An empty Stream can still have a finished result

~~~java
List<String> result = Stream.<String>empty()
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));

System.out.println(result); // []
~~~

The downstream creates an empty list, and the finisher turns it into an empty unmodifiable List. An empty set **is not inherently an error** for `collectingAndThen`; an error only occurs if the downstream or finisher cannot handle the empty state, such as `Optional::orElseThrow`.

### 10.2. A finisher can throw an exception

~~~java
List<String> result = Stream.of(" A ", " B ")
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                values -> {
                    if (values.size() != 2) {
                        throw new IllegalArgumentException("Expected two");
                    }
                    return List.copyOf(values);
                }));
~~~

This is a snippet with a two-element source, so it does not throw the size-check error. But if the input values violate the rule, the finisher can throw an unchecked exception; `Stream.collect` propagates the exception to the caller. **There is no automatic rollback** for side effects that already occurred before the finishing step.

If validation can be performed **before or during collection** more efficiently, consider doing it early; you do not have to collect all data just to check every condition.

### 10.3. Do not put important side effects in a finisher

Do not use a finisher to send emails, record payments, write to a database, or mutate shared state just because "after collect it must run exactly once." With parallel processing, data grouping, and collector lifecycles are more complex; side-effecting operations need clear transaction/idempotency contracts. Using a finisher to **create a result object** or perform predictable normalization is more appropriate.

### 10.4. When using a parallel Stream

~~~java
List<Integer> numbers = IntStream.range(0, 100)
        .parallel()
        .boxed()
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));
~~~

This is a snippet inside a method, requiring `java.util.stream.IntStream` to be imported. The Stream framework collects and combines results according to the collector contract and then finishes. With an ordered source and an encounter-order-compatible collector, the output List preserves the order of numbers `0..99`. However, an unmodifiable result **does not mean element objects are always deeply immutable**, and does not allow inferring safety for any shared mutable state outside the pipeline.

If you only need an unmodifiable List, `IntStream.range(0,100).boxed().toList()` from Java 16+ is usually shorter. Do not use `parallel().forEach(sharedArrayList::add)` to replace a collector yourself: a shared mutable accumulator can race.

## 11. Efficiency: the cost of collecting then finishing

### 11.1. An intermediate list may be created

With:

~~~java
List<String> output = names.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf));
~~~

The downstream creates an `ArrayList`, and the finisher creates a structurally unmodifiable List at copy time. This can incur extra allocation and reference copying, especially when the list is very large. Do not treat `collectingAndThen` as the default memory-optimal solution.

When you only need to return an unmodifiable List, `Stream.toList()` or `Collectors.toUnmodifiableList()` can be clearer and allow the implementation to use an appropriate strategy. Do not assert that one option is unconditionally faster; benchmark with real data, JDK, pipeline, and element characteristics when performance is a goal.

### 11.2. Counting and finding the maximum do not necessarily need a List

For example, `groupingBy(..., collectingAndThen(toList(), items -> items.size()))` works, but `groupingBy(..., counting())` does not need to store all group elements just to count them.

If you want a record containing count and maximum, you can do:

~~~java
record ScoreSummary(long count, int highest) {}

Map<String, ScoreSummary> summaries = works.stream()
        .collect(Collectors.groupingBy(
                Work::group,
                Collectors.collectingAndThen(
                        Collectors.summarizingInt(Work::points),
                        stats -> new ScoreSummary(
                                stats.getCount(),
                                stats.getMax()))));
~~~

This is a snippet inside a class with `Work` and an appropriate `works` variable. `summarizingInt` collects statistics; the finisher converts `IntSummaryStatistics` into a record with fewer fields. You need to define a policy for empty groups if using statistics outside `groupingBy`: `IntSummaryStatistics.getMax()` has a sentinel when there are no values, so you should not assign business meaning to it without checking `getCount()`.

### 11.3. Avoid keeping external references to a mutable accumulator

If a finisher returns the mutable accumulator directly and other code holds a reference, the result can change after collect. When the goal is to freeze the structure, create an appropriate unmodifiable snapshot rather than handing out a modifiable List and asking parties to "self-discipline" and not modify it.

At the same time, do not deep-copy every object out of habit if the domain only needs a structural copy; design the level of immutability according to real requirements.

## 12. Common mistakes and fixes

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Using `collectingAndThen` to process each element | Finisher receives downstream's result `R`, not `T` | `Stream.map` or `Collectors.mapping` |
| Thinking `List.copyOf` deep-copies every element | Only creates a structural snapshot, can share mutable elements | Immutable elements or deep-copy when needed |
| Using `List.copyOf` with null and expecting to keep null | `List.copyOf` rejects null | Choose an appropriate null policy; `Stream.toList()` allows null |
| Believing `Collectors.toList()` always returns a mutable ArrayList | Javadoc does not guarantee implementation/mutability | `toCollection(ArrayList::new)` if needed |
| Calling `Optional.orElseThrow` on potentially empty data | Can throw `NoSuchElementException` | Define a fallback or keep Optional |
| Assuming locking child Lists also locks the outer Map | Mutable levels are independent | Finish both each List and the Map if needed |
| Expecting `Map.copyOf` to preserve TreeMap order | Map copy does not guarantee iteration order | Choose a Map/view with its own ordering contract |
| Using a finisher to compute a sum from a very large List | Unnecessarily stores intermediate elements | `summingInt`/`summarizingInt`/reduction |
| Thinking the finisher can be any callback type | Finisher must be `Function<R,RR>` and type-compatible | Declare the downstream result type properly |
| Using `collectingAndThen` just to call a shorter `toList()` | Complicates the API, may cost a copy | `Stream.toList()` when the contract matches |
| Using parallel `forEach` to mutate a shared List | Has a race condition | Use a collector/`toList` |
| Relying on side effects in a finisher to ensure transactions | Collectors have no business rollback | Design transaction/idempotency outside Stream |
| Handling errors when collection is incomplete as if a result exists | Exceptions can stop collect before finisher | Catch at appropriate boundaries and test error cases |

### 12.1. When should you extract a collector into a variable?

If nesting has too many levels, explicit types can help readability:

~~~java
Collector<String, ?, List<String>> immutableList =
        Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf);

List<String> result = Stream.of("A", "B").collect(immutableList);
~~~

This is a snippet inside a method, requiring `java.util.stream.Collector`, `Collectors`, `Stream`, and `List`/`ArrayList` to be imported. Defining the name `immutableList` expresses the intent to create an unmodifiable List at **the structural level**, without guaranteeing deep immutability. Name responsibilities clearly and avoid creating generic helpers broader than required.

## 13. Self-practice exercises

### Exercise 1 — Turn a List into unmodifiable

Collect `Stream.of("An","Binh")` into an `ArrayList`, then use `collectingAndThen` and `List.copyOf`. Print the list and try `add("Chi")` inside a `try/catch`. Explain why `UnsupportedOperationException` comes from the finisher's result, not from an inherent feature of every `Collector`.

### Exercise 2 — What types do downstream and finisher have?

Analyze:

~~~java
Collector<String, ?, List<String>> c =
        Collectors.collectingAndThen(
                Collectors.toCollection(ArrayList::new),
                List::copyOf);
~~~

State `T`, `R`, `RR` in this case; explain why `A` is wildcarded and the compiler can infer the accumulator type. Since there is no big difference between `R` and `RR` here, give an example that genuinely changes the type (such as `Optional<Work> -> String`).

### Exercise 3 — Max and empty input

Use `Collectors.maxBy(Integer::compareTo)`, finishing with `value -> value.orElseThrow()`. Test with `[3,8,5]` and an empty Stream. Clearly state why only one case produces a result and the other throws `NoSuchElementException`.

### Exercise 4 — Grouping and member names

Create `record Person(String team,String name) {}`. Use `groupingBy(Person::team, collectingAndThen(mapping(Person::name,toList()), List::copyOf))`. For each group, try modifying the resulting List and observe the exception. Next, try adding a new key to the Map (if the Map type allows) to see the two different levels.

### Exercise 5 — Both Map and List unmodifiable

Finish the Lists per group and then use an outer-level finisher `Map::copyOf`. Explain why both the Map and Lists block modification through their respective APIs; also note that `Map.copyOf` does not guarantee preserving iteration order, and mutable element objects still need their own policy.

### Exercise 6 — Compute statistics by group

Create record `Summary(long count,int highest)`. Use `groupingBy` combined with `summarizingInt`, then `collectingAndThen` to turn statistics into the record. Compare with collecting the whole group using `toList` and iterating again. State memory pros/cons.

### Exercise 7 — Distinguish processing layers

Compare `mapping(Person::name,toList())` with `collectingAndThen(toList(), List::copyOf)`. Which one processes each element, and which one processes the collected List? Write a pipeline combining both, then explain the processing order.

### Exercise 8 — Null policy

Given source `["A", null, "B"]`. Use `toCollection(ArrayList::new)` and `List.copyOf` in the finisher; predict `NullPointerException`. Choose another approach if you need to keep null in an unmodifiable List, and another approach if business logic wants to reject null early.

### Exercise 9 — Parallel collect

Compare the result order from `IntStream.range(0,100).parallel().boxed().toList()` and a pipeline using `collectingAndThen(toCollection(ArrayList::new), List::copyOf)`. Check the two Lists with `equals`; do not use `parallel().forEach(System.out::println)` to measure data order.

### Exercise 10 — Over-refactoring

Given:

~~~java
long count = records.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.toList(),
                list -> (long) list.size()));
~~~

Propose rewriting with `records.stream().count()`, or `Collectors.counting()` if needed as a downstream of `groupingBy`. Explain the benefit of reducing intermediate collections and clarifying intent.

## 14. Self-check questions

1. **What does `collectingAndThen` take?** A downstream Collector and a `Function` to finish the downstream result.
2. **Does the finisher receive each element `T` or the result `R`?** The result `R` already collected by the downstream.
3. **Must `R` and `RR` be the same type?** No; the finisher can turn `Optional<Work>` into `String` or statistics into a record.
4. **Is `IDENTITY_FINISH` preserved in the composite collector?** No, due to the added finishing step.
5. **In `groupingBy`, does the downstream finisher run per Work or per group?** On the downstream result of each group.
6. **Does `List.copyOf` accept null?** No.
7. **Does `List.copyOf` deep-copy a StringBuilder inside the List?** No.
8. **Does `List.copyOf` protect the outer Map when used as a downstream of groupingBy?** No.
9. **Is `Optional::orElseThrow` reasonable for an empty Stream?** Only if the business policy accepts an error when there are no elements.
10. **Do you need collectingAndThen just to get an unmodifiable List from a simple Stream?** Not necessarily; `Stream.toList()` on Java 17 is usually simpler.
11. **How do you finish both the Map and child Lists as unmodifiable?** Use a finisher at each layer, with null and ordering controls if required.
12. **Is using a finisher to create a counter on a large List optimal?** Not automatically; there are usually more efficient counting/aggregating collectors.

## 15. Code review checklist

1. What type does `downstream` return? Is the finisher declared to accept **that exact type `R`**?
2. Does the finisher produce `RR` matching the caller's contract, or is it just changing types out of convenience?
3. Is the goal to process **each element** or **the collected result**? Is `mapping`/`map` being confused with `collectingAndThen`?
4. If an unmodifiable List is needed, could `Stream.toList()`/`toUnmodifiableList()` be used more simply?
5. If using `List.copyOf`, can the data contain null and are element objects mutable?
6. If nested in `groupingBy`, the finisher applies per group; does the outer Map need separate protection?
7. If group ordering is needed, was an appropriate Map factory chosen instead of relying on default `groupingBy`?
8. If using `Map.copyOf`, is iteration order preservation being assumed?
9. Is there a risk of emptiness causing `Optional.orElseThrow` to throw an exception? Is that the right policy?
10. Are you accumulating an entire List just to compute `count`, `sum`, or `max` when direct collectors exist?
11. If running in parallel, are side effects in lambdas/finishers controlled and is shared mutable state avoided?
12. Are implementation details of `Collectors.toList()` being relied upon instead of the Javadoc contract?
13. Are there unit tests covering normal results, multiple groups, empty groups, null, ordering, and mutability?

## 16. Summary and references

**`Collectors.collectingAndThen(downstream, finisher)` creates a composite collector: first the downstream collects data into `R`, then the finisher turns `R` into `RR`.** It is suitable when a collector's output needs an explicit finishing step, especially as **a downstream of `groupingBy`** or when converting `Optional`/statistics into a business value.

Distinguish the layers: `map`/`Collectors.mapping` processes each element; `collectingAndThen` processes **the collected result**. You can use `List.copyOf` to return an unmodifiable List, but it **rejects null and does not deep-copy elements**. If grouping data, finishing child Lists does not automatically make the outer Map unmodifiable; the Map needs its own policy. `Map.copyOf` also does not guarantee preserving iteration order.

Finally, do not use `collectingAndThen` for every pipeline: `Stream.toList()`, `toUnmodifiableList()`, `count()`, `summingInt()`, or `summarizingInt()` can be more direct, readable, and require less intermediate storage. Choose the technique based on **the data contract to be returned**, especially result type, mutability, null handling, performance, and exception lifecycle.

Official documentation: Java SE 17 Javadoc for `java.util.stream.Collectors` (sections `collectingAndThen`, `mapping`, `groupingBy`, `summarizingInt`, `maxBy`), `java.util.stream.Collector` and `Collector.Characteristics`, `java.util.stream.Stream`, `java.util.List.copyOf`, `java.util.Map.copyOf`, and `java.util.Optional`.
