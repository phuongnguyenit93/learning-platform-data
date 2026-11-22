# Combiner Merging Independent Accumulation Regions in a Custom Collector (Java)

## 1. Background: why does a Collector need a combiner?

In the Java Stream API, `collect` is a terminal operation used to **accumulate** elements into a result: a list, set, Map, string, statistics, or an application-defined domain structure.

With a **custom Collector**, we can specify how to:

1. Create a new **accumulation container**.
2. Add each source element into that container.
3. Merge two containers that were accumulated **independently**.
4. Transform the final container into the desired result.

Step (3) is the job of the **combiner**. It is especially meaningful for parallel streams, because a stream can be split into data partitions, each partition creates and accumulates into its own container, and then the containers are merged together.

For example, a stream of names:

~~~text
Data: [An, Binh, Chi, Dung]

Left partition:  [An, Binh] -> container L = [An, Binh]
Right partition: [Chi, Dung] -> container R = [Chi, Dung]

combiner(L, R) -> [An, Binh, Chi, Dung]
~~~

Here, `combiner` does **not** directly receive a `String` element from the source. It receives **two intermediate accumulation results** of the same type, merges their contents, and returns a container representing the combined result.

**Key mindset:** `accumulator` works with **(container, source element)**; `combiner` works with **(container, container)**. The two parameters of a combiner are not two original elements from the Stream, unless the accumulator type itself happens to match the source element type in a special design.

## 2. Collector structure and Java signatures

The `java.util.stream.Collector<T,A,R>` interface uses three type parameters:

| Symbol | Role | Example |
| --- | --- | --- |
| `T` | Source element type from the Stream | `String` |
| `A` | Intermediate accumulation container type (*mutable accumulation type*) | `ArrayList<String>` |
| `R` | Final result type | `List<String>` |

The key methods of a Collector:

~~~java
Supplier<A> supplier();
BiConsumer<A, T> accumulator();
BinaryOperator<A> combiner();
Function<A, R> finisher();
Set<Collector.Characteristics> characteristics();
~~~

Reading along the flow:

~~~text
supplier() -> empty A

accumulator().accept(A, T)
    -> mutates A with element T

combiner().apply(A_left, A_right)
    -> returns A with both regions merged

finisher().apply(A)
    -> R
~~~

The factory method for creating a custom Collector with a finisher:

~~~java
Collector.of(
        Supplier<A> supplier,
        BiConsumer<A,T> accumulator,
        BinaryOperator<A> combiner,
        Function<A,R> finisher,
        Collector.Characteristics... characteristics)
~~~

This is a signature **describing the type roles**, not parameter declaration syntax that can be pasted verbatim into Java code. The actual syntax is one of the static generic overloads of `Collector.of`. When `A` and `R` are the same, there is an overload without an explicit finisher:

~~~java
Collector.of(supplier, accumulator, combiner, characteristics...)
~~~

This overload creates a Collector with `IDENTITY_FINISH` because the result `R` is the container `A` itself.

**Note on API names:** `Collector.of(...)` belongs to the singular `Collector` interface. In contrast, `Collectors.toList()` and `Collectors.groupingBy()` are built-in factories in the plural `Collectors` utility class.

## 3. Supplier: each accumulation region needs its own container

`supplier()` is responsible for creating a **new container that is initially empty with respect to accumulation**. For example:

~~~java
Supplier<List<String>> supplier = ArrayList::new;
List<String> left = supplier.get();
List<String> right = supplier.get();
~~~

Two calls must return two containers that can accumulate independently. In particular, do not use a shared static list:

~~~java
// WRONG: Returns the same shared object for every partition.
List<String> shared = new ArrayList<>();
Supplier<List<String>> badSupplier = () -> shared;
~~~

A Collector whose supplier returns the same mutable object causes two risks: the accumulation regions are no longer independent, and multiple threads can modify shared state without synchronization. When the combiner tries to merge `left` and `right` while both variables actually point to the same list, `addAll` can duplicate data or lead to wrong results.

The right way:

~~~java
Supplier<List<String>> goodSupplier = ArrayList::new;
~~~

Each call to `get()` creates a new `ArrayList`. In a parallel reduction **without the `CONCURRENT` characteristic**, the Stream framework can generally organize separate containers and merge them only when appropriate. Do not treat the number of created containers as a constant: source splitting and the number of supplier calls are implementation-dependent details.

## 4. Accumulator: container + source element

The accumulator is a `BiConsumer<A,T>`, so it usually **mutates the container** rather than returning one.

~~~java
BiConsumer<List<String>, String> accumulator =
        (list, name) -> list.add(name);
~~~

Meaning:

~~~text
A_left = []
accumulator(A_left, "An")   -> A_left = ["An"]
accumulator(A_left, "Binh") -> A_left = ["An", "Binh"]
~~~

When creating a Collector using `Collector.of`:

~~~java
Collector<String, List<String>, List<String>> collector =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
~~~

This is an example using the **overload without a finisher**. `List::add` is a method reference that can serve as a `BiConsumer` because the returned `boolean` value is ignored in a `void`-returning functional context.

Key distinction:

- `accumulator` returns `void` per the `BiConsumer` contract; it updates `A`.
- `combiner` returns **`A`** per the `BinaryOperator<A>` contract; it must tell the framework which container represents the merged result.

## 5. Combiner: merge two containers and return the resulting container

For a list-accumulating collector:

~~~java
BinaryOperator<List<String>> combiner =
        (left, right) -> {
            left.addAll(right);
            return left;
        };
~~~

It does two things:

1. Adds all elements of `right` into `left`.
2. **Returns `left`** so the framework uses it as the combined accumulator.

Returning `left` here is a valid design choice; not every combiner is required to reuse the left container itself, as long as the result obeys the contract. In mutable collectors, merging into `left` and returning `left` usually avoids allocating an extra result container.

**Do not forget `return left;`**. A lambda that only calls `left.addAll(right)` does not match `BinaryOperator<A>` because `addAll` returns `boolean` (not `List<String>`); and a block lambda that only mutates without a `return` will not satisfy the `A` return signature.

A complete example:

~~~java
Collector<String, List<String>, List<String>> c =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });

List<String> names = Stream.of("An", "Binh", "Chi")
        .collect(c);

System.out.println(names); // [An, Binh, Chi]
~~~

### 5.1. The combiner is not necessarily called on a sequential stream

If you only run:

~~~java
Stream.of("An", "Binh", "Chi").collect(c);
~~~

a typical sequential implementation may use a single container and call the accumulator repeatedly **without needing** the combiner. However, a valid Collector must still provide a proper combiner because the API requires it and switching to `parallel()` may require it to be used.

Do not write code whose correctness depends on the combiner "always being called exactly once" or "never being called". That is not a stable Stream contract.

### 5.2. The combiner may also create a new container

Semantically, a combiner is allowed to return a **new** combined accumulator:

~~~java
BinaryOperator<List<String>> newListCombiner =
        (left, right) -> {
            List<String> merged = new ArrayList<>(left);
            merged.addAll(right);
            return merged;
        };
~~~

This avoids mutating `left`, but copies the container and is usually more expensive. With custom Collectors and aliasing/observability requirements, intermediate object management must be consistent. External code must not hold references and expect them to remain unchanged if the combiner is designed to mutate.

## 6. Three important laws for a correct combiner

### 6.1. Identity — an empty region must not change the result

The container `supplier.get()` acts as the **identity element** of the merge with respect to the result. If `e` is an empty accumulator and `a` is an accumulated accumulator, the result requirement is:

\[
\operatorname{combine}(a,e)\equiv a,\qquad
\operatorname{combine}(e,a)\equiv a.
\]

The symbol `≡` means **equivalent in observable result through the finisher**, not necessarily `==` same reference or same object identity.

Example of merging lists:

~~~text
combine([An, Binh], []) => [An, Binh]
combine([], [An, Binh]) => [An, Binh]
~~~

A combiner is **incorrect** if it always adds a marker element to the result:

~~~java
// Wrong: merging an empty region also alters the data.
(left, right) -> {
    left.add("MERGED");
    left.addAll(right);
    return left;
}
~~~

The result may contain extra `"MERGED"` entries depending on how many splits/merges occurred. You cannot use the "number of combiner calls" to determine how many times a marker appears in the business result.

### 6.2. Associativity — how regions are split/merged must not change the result

For three regions `A`, `B`, `C`, the merge operation must be **associative** with respect to the result:

\[
\operatorname{combine}(\operatorname{combine}(A,B),C)
\equiv
\operatorname{combine}(A,\operatorname{combine}(B,C)).
\]

Example of merging lists while preserving region order:

~~~text
A = [An]
B = [Binh]
C = [Chi]

(A + B) + C = [An, Binh, Chi]
A + (B + C) = [An, Binh, Chi]
~~~

Note: here the merge **may be non-commutative**. `A + B` yields `[An, Binh]`, whereas `B + A` yields `[Binh, An]`. For ordered streams, preserving encounter order is part of the semantics of an ordered Collector. A list combiner can be associative without being commutative.

Do not use subtraction across regions as a general combiner: `(10-3)-2` differs from `10-(3-2)`. If using floating-point math, note that `double` addition is not strictly bitwise associative due to rounding; choose an appropriate algorithm and precision requirement.

### 6.3. Accumulator/combiner compatibility — merging regions is equivalent to direct accumulation

If one region has elements `["An","Binh"]` and another has `["Chi"]`, merging the two regions must produce the same logical result as accumulating all three elements in one region.

~~~text
One region:
supplier -> []
accumulate An -> [An]
accumulate Binh -> [An, Binh]
accumulate Chi -> [An, Binh, Chi]

Two regions:
supplier -> []
accumulate An, Binh -> [An, Binh]
supplier -> []
accumulate Chi -> [Chi]
combine(left, right) -> [An, Binh, Chi]
~~~

Regardless of how many partitions the framework organizes (while still respecting encounter order when required), the business result must be equivalent. To achieve that, **supplier, accumulator, and combiner must form a unified set of rules**.

## 7. Parallel collection diagram

Suppose:

~~~java
List<String> values = List.of("a", "b", "c", "d");
~~~

A parallel execution plan **might** proceed as:

~~~text
                  Stream: [a, b, c, d]
                         /         \
                  [a, b]           [c, d]
                     |                |
                supplier()        supplier()
                     |                |
                  A = []             B = []
                     |                |
                accumulate        accumulate
                a -> [a]          c -> [c]
                b -> [a,b]        d -> [c,d]
                     \                /
                      \              /
                    combiner(A,B)
                          |
                    [a,b,c,d]
                          |
                       finisher
                          |
                     result R
~~~

This is a **conceptual model**, not a promise that the JVM will always create two regions or invoke each callback on a fixed schedule. The source and collector can alter splitting/merging and the degree of parallelism. For a sequential pipeline, there may be only a single accumulator and no actual merge step.

### 7.1. "Independent" means no shared mutable container

For a typical non-`CONCURRENT` collector, each partition accumulates into its own container from the supplier, rather than sharing one `ArrayList` concurrently. The combiner is invoked when partial results need to be merged.

This allows using `ArrayList` — a **non-thread-safe** class — inside a valid parallel collector, provided each container is only used by the framework according to the contract, the supplier creates distinct instances, the combiner is correct, and `CONCURRENT` is not wrongly declared.

Do not infer that any arbitrary external `ArrayList` shared across threads is safe just because a collector can be used in a parallel stream.

## 8. Finisher: transforming A into R after merging

If `A` and `R` have different types, use `Collector.of(..., finisher)`. For example, accumulating into an `ArrayList<String>` but returning an **unmodifiable** `List<String>`:

~~~java
Collector<String, ArrayList<String>, List<String>> copyCollector =
        Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                List::copyOf);

List<String> copy = Stream.of("An", "Binh", "Chi")
        .parallel()
        .collect(copyCollector);
~~~

Here:

- `T = String`.
- `A = ArrayList<String>`.
- `R = List<String>`.
- The combiner **merges `ArrayList<String>` instances**, not final `List<String>` results.
- The finisher `List::copyOf` runs only to produce the final result after the accumulations have been combined, not once per source element.

`List.copyOf` does not accept null elements. With data containing null, the finisher may throw `NullPointerException`; that is the policy of creating the final List, not a bug in the combiner signature.

When a finisher actually transforms `A` to `R`, you must **not** declare the `IDENTITY_FINISH` characteristic. This is an example where `A` and `R` differ, so the finisher is not the identity function.

### 8.1. StringJoiner example for semantic merging

`StringJoiner` is designed to be able to merge two regions:

~~~java
Collector<String, StringJoiner, String> joinerCollector =
        Collector.of(
                () -> new StringJoiner(","),
                StringJoiner::add,
                StringJoiner::merge,
                StringJoiner::toString);

String csv = Stream.of("An", "Binh", "Chi")
        .parallel()
        .collect(joinerCollector);

System.out.println(csv); // An,Binh,Chi
~~~

`StringJoiner::merge` is a built-in combiner and returns `StringJoiner`. It handles delimiter placement when merging regions, avoiding the common mistake of a StringBuilder combiner manually adding a comma even for empty regions or leaving a trailing comma.

For arbitrary data containing comma characters, this example only illustrates delimiter-based joining and **should not be treated as a full CSV writer with escaping/quoting rules**.

## 9. Example of a custom Collector with two metrics and an immutable result

A Collector can accumulate multiple metrics at the same time. For example, each word goes into a container holding the word count and total character count.

~~~java
record WordStats(long count, long characters) {}

final class StatsBox {
    long count;
    long characters;

    void accept(String word) {
        count++;
        characters += word.length();
    }

    StatsBox combine(StatsBox other) {
        count += other.count;
        characters += other.characters;
        return this;
    }

    WordStats finish() {
        return new WordStats(count, characters);
    }
}
~~~

Collector:

~~~java
Collector<String, StatsBox, WordStats> statsCollector =
        Collector.of(
                StatsBox::new,
                StatsBox::accept,
                StatsBox::combine,
                StatsBox::finish);
~~~

Read the combiner carefully:

- It accepts **`StatsBox other`**, not a `String word`.
- It adds two aggregated metric boxes, **without re-invoking the accumulator for each word**.
- It mutates `this` and returns `this` as the merged result.
- With the identity `new StatsBox()`, both integer fields start at 0, so merging an empty region does not change the metrics.

Total word count and total characters are additions of `long` values, which are associative under Java integer arithmetic (subject to overflow for extremely large counts), and independent of data order.

You can use `parallelStream` without `synchronized` in `StatsBox` when using a **non-CONCURRENT** collector, because each region accumulates independently. Do not place the `CONCURRENT` characteristic on this non-thread-safe mutable class.

## 10. Complete Java 17+ program and deterministic stdout

Save as **`CombinerDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.StringJoiner;
import java.util.stream.Collector;
import java.util.stream.Stream;

public class CombinerDemo {
    record WordStats(long count, long characters) {}

    static final class StatsBox {
        long count;
        long characters;

        void add(String word) {
            count++;
            characters += word.length();
        }

        StatsBox merge(StatsBox other) {
            count += other.count;
            characters += other.characters;
            return this;
        }

        WordStats finish() {
            return new WordStats(count, characters);
        }
    }

    public static void main(String[] args) {
        Collector<String, ArrayList<String>, List<String>> listCollector =
                Collector.of(
                        ArrayList::new,
                        ArrayList::add,
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        },
                        List::copyOf);

        List<String> names = Stream.of("An", "Binh", "Chi", "Dung")
                .parallel()
                .collect(listCollector);
        System.out.println("names=" + names);

        try {
            names.add("Lan");
        } catch (UnsupportedOperationException ex) {
            System.out.println("namesUnmodifiable=true");
        }

        Collector<String, StringJoiner, String> joinerCollector =
                Collector.of(
                        () -> new StringJoiner(","),
                        StringJoiner::add,
                        StringJoiner::merge,
                        StringJoiner::toString);

        String joined = Stream.of("An", "Binh", "Chi")
                .parallel()
                .collect(joinerCollector);
        System.out.println("joined=" + joined);

        Collector<String, StatsBox, WordStats> statsCollector =
                Collector.of(
                        StatsBox::new,
                        StatsBox::add,
                        StatsBox::merge,
                        StatsBox::finish);

        WordStats stats = Stream.of("Java", "API", "Stream")
                .parallel()
                .collect(statsCollector);
        System.out.println("stats=" + stats);

        WordStats empty = Stream.<String>empty()
                .collect(statsCollector);
        System.out.println("empty=" + empty);

        StatsBox left = new StatsBox();
        left.add("Java");
        StatsBox right = new StatsBox();
        right.add("API");
        left.merge(right);
        System.out.println("manualMerge=" + left.finish());

        Collector<String, ArrayList<String>, ArrayList<String>> sameType =
                Collector.of(
                        ArrayList::new,
                        ArrayList::add,
                        (a, b) -> {
                            a.addAll(b);
                            return a;
                        });

        List<String> sequential = Stream.of("a", "b", "c")
                .collect(sameType);
        System.out.println("sequential=" + sequential);
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac CombinerDemo.java
java CombinerDemo
~~~

Expected stdout:

~~~text
names=[An, Binh, Chi, Dung]
namesUnmodifiable=true
joined=An,Binh,Chi
stats=WordStats[count=3, characters=13]
empty=WordStats[count=0, characters=0]
manualMerge=WordStats[count=2, characters=7]
sequential=[a, b, c]
~~~

Explanation:

1. `names` preserves exact encounter order because the source is ordered and the collector does not declare `UNORDERED`. Internal splitting/merging is not printed or assumed.
2. `namesUnmodifiable=true` proves the finisher produces an unmodifiable `List` as the result.
3. `joined` uses `StringJoiner::merge`, merging accumulation regions without inserting extra delimiters.
4. `stats` counts the three strings `Java`, `API`, `Stream`; total length is `4+3+6=13`.
5. `empty` shows the supplier creates a valid empty region and the finisher returns 0/0 statistics.
6. `manualMerge` merges two independent regions containing `Java` and `API`; the result has 2 words, 7 characters.
7. `sameType` illustrates the `Collector.of` overload without an explicit finisher when the accumulator type and result type are identical.

The example does not try to guess how many times the combiner runs in a parallel pipeline. The output relies solely on the **Collector contract**, so stdout is verifiable regardless of ForkJoinPool execution scheduling.

## 11. Common combiner mistakes

### 11.1. Not merging data from the right container

~~~java
// WRONG: Drops the entire right partition.
(left, right) -> left
~~~

When run sequentially, the bug may stay hidden because the combiner may not be called. When run in parallel, some elements can disappear from the result.

The right way for a List:

~~~java
(left, right) -> {
    left.addAll(right);
    return left;
}
~~~

### 11.2. Merging with the wrong type or returning the wrong value

~~~java
// WRONG for BinaryOperator<List<String>>:
// (left, right) -> left.addAll(right)
// addAll returns boolean, not List<String>.
~~~

The combiner must return a container of type `A`. Also never return `null` as the merged result: the framework needs to continue using the combined accumulator.

### 11.3. Supplier returning a shared object

~~~java
List<String> shared = new ArrayList<>();

// WRONG:
Collector<String, List<String>, List<String>> unsafe =
        Collector.of(
                () -> shared,
                List::add,
                (a, b) -> {
                    a.addAll(b);
                    return a;
                });
~~~

The supplier does not create independent accumulation regions. This is a fundamental bug that cannot be "fixed" merely by adding `synchronized` arbitrarily to the combiner.

### 11.4. Combiner altering data based on the number of merges

~~~java
// WRONG: adds a separator even when right is an empty region.
(left, right) -> {
    left.append(",");
    left.append(right);
    return left;
}
~~~

If using `StringBuilder` to join strings, the combiner must handle empty regions properly and preserve separator semantics; built-in collectors like `Collectors.joining(",")` or `StringJoiner` are usually less error-prone.

### 11.5. Mutating both containers in a way that causes duplication

~~~java
// WRONG: merges in both directions and can duplicate/alter data.
(left, right) -> {
    left.addAll(right);
    right.addAll(left);
    return left;
}
~~~

Only one resulting accumulator is needed to represent all the data. Do not mutate `right` after adding its contents into `left` if that mutation is not required.

### 11.6. Declaring `CONCURRENT` for a non-thread-safe container

~~~java
// WRONG when A is ArrayList and the accumulator uses list.add:
// Collector.Characteristics.CONCURRENT
~~~

`CONCURRENT` allows the accumulator to be called concurrently on **the same result container** under conditions where the Stream can take advantage of it. Do not declare it if the accumulator/container is not thread-safe. A collector used in a parallel stream **does not have to** have `CONCURRENT`.

### 11.7. Declaring `UNORDERED` even when order is required

If the result is a list and business logic requires preserving encounter order, do not add `Collector.Characteristics.UNORDERED`. This characteristic declares that the result is insensitive to encounter order; the framework may leverage that declaration to execute differently. It is not merely a "speed-up" switch.

### 11.8. Declaring `IDENTITY_FINISH` with a non-identity finisher

If using `List::copyOf` or `StatsBox::finish` to convert `A` to `R`, do not declare `IDENTITY_FINISH`. This characteristic tells the framework it can skip the finisher step because the conversion is an identity in both type and value; declaring it wrongly can corrupt the result or cause type errors at runtime.

## 12. Testing a combiner independently with useful cases

Do not just run in parallel once and eyeball the result. You should verify the desired properties of the Collector with simple tests:

### 12.1. Two non-empty regions

~~~java
List<String> left = new ArrayList<>(List.of("A", "B"));
List<String> right = new ArrayList<>(List.of("C"));

left.addAll(right);
System.out.println(left); // [A, B, C]
~~~

### 12.2. One empty region

~~~java
List<String> empty = new ArrayList<>();
List<String> nonEmpty = new ArrayList<>(List.of("A"));

empty.addAll(nonEmpty);
System.out.println(empty); // [A]
~~~

For an actual combiner, test both when the left region is empty and when the right region is empty. If containers are mutated, create fresh copies for each test case so data from one case does not affect the next.

### 12.3. Three regions and different parenthesizations

~~~text
A = [A], B = [B], C = [C]

combine(combine(A,B),C) -> [A, B, C]
combine(A,combine(B,C)) -> [A, B, C]
~~~

To test this in Java, create **independent** containers for the two parenthesizations; do not reuse containers that have already been mutated. Compare **observable results**, not `==` references.

### 12.4. Comparing sequential and parallel

If a collector is valid, the same source and valid business conditions must yield equivalent results:

~~~java
List<String> source = List.of("A", "B", "C", "D");

List<String> seq = source.stream().collect(listCollector);
List<String> par = source.parallelStream().collect(listCollector);

System.out.println(seq.equals(par)); // true
~~~

In this snippet, `listCollector` is the collector declared earlier in section 10. This kind of test should use an ordered source and a non-`UNORDERED` collector to compare the two lists in exact order. For collectors whose results are order-insensitive such as `Set`, choose an appropriate comparison criterion.

Do not write tests asserting "the combiner is called exactly N times" because the number of regions, merge schedule, and whether the combiner is called at all are implementation details, not a contract to assert.

## 13. Comparison with `reduce` and built-in collectors

`Stream.reduce` and `Stream.collect` are both aggregation operations, but they have different usage patterns:

| Aspect | `reduce(identity, accumulator, combiner)` | `collect(Collector)` |
| --- | --- | --- |
| Accumulation | From aggregated value and element, returns a new aggregated value | `BiConsumer<A,T>` can mutate container A |
| Combiner | Merges two **intermediate result values** | Merges two **accumulation containers A** |
| Mutable state | Should not mutate a shared identity | Collector model supports controlled mutable accumulation |
| Finisher | No separate finisher step in the overload | Can transform A into R |
| Characteristics | Depends on reduce laws | Has `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH` when applicable |

Arithmetic example:

~~~java
int sum = Stream.of(1, 2, 3)
        .reduce(0, Integer::sum);
~~~

For collecting into a list, do not force a mutable `ArrayList` into `reduce` by mutating a shared identity. `collect(Collectors.toList())` or a custom Collector with its own supplier and a proper combiner is the right approach.

**Prefer built-in collectors when they suffice:** `toList`, `toSet`, `toMap`, `groupingBy`, `partitioningBy`, `joining`, `summarizingInt`, `mapping`, `filtering`, `collectingAndThen` already satisfy the required contracts. Write a custom collector when you have a specific need that built-in collectors cannot express clearly or cannot produce the desired result for.

## 14. Distinguishing `CONCURRENT` from "running in parallel"

A `parallel()` Stream can run a non-CONCURRENT collector by using **multiple independent containers** and merging them via the combiner. Meanwhile, a Collector declaring `CONCURRENT` states that its accumulator can receive multiple concurrent calls on a single accumulator result under permitted conditions.

This leads to two mental models:

~~~text
Non-CONCURRENT, parallel:
  supplier -> A1 --- accumulate -> A1
  supplier -> A2 --- accumulate -> A2
                                combine(A1,A2)

CONCURRENT under appropriate conditions:
  a single shared accumulator A can receive
  multiple concurrent accumulator calls
~~~

You cannot conclude that `parallel()` always has exactly two accumulators or that a `CONCURRENT` collector always has one shared accumulator. In particular, for an ordered source and a non-`UNORDERED` collector, the runtime may choose a different organization to preserve ordering semantics.

**Safety rule:** Do not declare a characteristic until you are sure the actual behavior satisfies the contract. Parallel optimization should only be done after collection logic is verified with diverse data.

## 15. Some advanced scenarios to distinguish

### 15.1. Map combiner needs to resolve duplicate keys

If `A` is a `Map<K,V>`, the combiner must bring all entries from the right-region Map into the result Map, while properly handling **keys that appear in both regions**.

~~~java
(left, right) -> {
    right.forEach((key, value) ->
            left.merge(key, value, Integer::sum));
    return left;
}
~~~

The snippet above is only valid when `left`/`right` are `Map<K,Integer>` with keys/values satisfying the `Map.merge` contract and an addition strategy matching the business logic. If you want to keep the first or last entry, you must define an explicit merger; **do not silently overwrite** with `putAll` unless that is the exact rule.

For common cases, `Collectors.toMap(keyMapper, valueMapper, mergeFunction)` already solves the Map problem and is usually better than writing a combiner from scratch.

### 15.2. Set combiner differs from List combiner in ordering

~~~java
(left, right) -> {
    left.addAll(right);
    return left;
}
~~~

The snippet above can apply to `Set<T>` if the types match, but a Set deduplicates elements and does not necessarily have an order. With the same `addAll` merge form, the **result semantics** of Set and List are very different: List preserves multiplicity, while Set keeps unique elements by equality.

### 15.3. Combiner for statistical results

For `StatsBox` in section 9, the combiner adds the metric fields. If adding `min`, `max`, or more complex statistical metrics, you must define the **empty value** for each field and ensure merging two regions is correct. For an arithmetic mean, you typically need to merge **sum and count**, then compute `sum/count` in the finisher; do not average the means of two regions by dividing by 2 if the two regions have different element counts.

### 15.4. Do not rely on combiner logs for performance testing

Logging inside a combiner can be useful while learning and debugging, but the number of times it is called varies with data size, parallelism, and source splitting. Logging can also skew performance measurements. When benchmarking, measure throughput and time with appropriate tools, and avoid side effects in functions meant to be optimized.

## 16. Self-check exercises

**Exercise 1.** In `Collector<String,List<String>,List<String>>`, what kind of data does the combiner receive?

Answer: two `List<String>` instances that are **intermediate accumulation containers**. It does not receive a `String` directly from the source.

**Exercise 2.** What is wrong with the following combiner?

~~~java
(left, right) -> left
~~~

Answer: it discards all data from the `right` region. The bug may stay hidden when a sequential pipeline does not need to merge, but it causes data loss when merging multiple regions.

**Exercise 3.** Is the supplier `() -> sharedList` suitable for a mutable collector executed in parallel?

Answer: no. The regions are not independent, can mutate the same object, and cause race conditions/data duplication. A supplier must create a new container, such as `ArrayList::new`.

**Exercise 4.** Why must the `combiner` of a list collector preserve left/right order even though the merge is not commutative?

Answer: With an ordered stream and a collector that does not declare `UNORDERED`, the result may need to preserve encounter order. Merging `left` then `right` properly is associative without being commutative.

**Exercise 5.** Why should `IDENTITY_FINISH` not be declared for a collector using `List::copyOf`?

Answer: `List::copyOf` creates a result from the accumulation container, not an identity operation on the same object; declaring this characteristic can cause the framework to skip the finisher, resulting in the wrong type or breaking immutability.

**Exercise 6.** In the `StatsBox` example, one branch counts 2 words with 7 total characters; another branch counts 1 word with 6 total characters. What result must the combiner produce?

Answer: a total of 3 words and 13 characters, regardless of which branch is merged first in an associative metric addition.

**Exercise 7.** If the goal is simply to join strings with a comma, should you build a complex custom combiner for StringBuilder?

Answer: usually no. `Collectors.joining(",")` or `StringJoiner` is built in and expresses separator rules correctly.

**Exercise 8.** Is the combiner required to run on a sequential stream?

Answer: no. Never write a program whose result depends on the number of times the combiner is called. What matters is that the merge is correct **if it is called**.

**Exercise 9.** What is the difference between `Accumulator` and `Combiner`?

Answer: accumulator has the form `(A,T) -> void`, used to add each source element into a container; combiner has the form `(A,A) -> A`, used to merge the results of two independently accumulated containers.

## 17. Takeaways

**A combiner is the function that merges two independent accumulation regions in a custom Collector.** It receives two accumulators of the same type `A` and **must return an accumulator `A` containing the merged result**, without dropping data from either side.

A reliable collector has four clear roles:

- `supplier` creates a **new, empty container** each time the framework needs an accumulation region.
- `accumulator` receives `(A,T)` and adds each source element `T` into container `A`.
- `combiner` receives `(A,A)` and merges two containers with rules satisfying **identity**, **associativity**, and accumulator compatibility.
- `finisher` transforms `A` into the result `R` if needed.

Never use a single shared mutable container across regions, never declare `CONCURRENT`/`UNORDERED`/`IDENTITY_FINISH` in violation of the contract, and never depend on how many times the combiner is called. When designed properly, a custom Collector works with both **sequential and parallel streams** while producing equivalent, clear, and verifiable results.
