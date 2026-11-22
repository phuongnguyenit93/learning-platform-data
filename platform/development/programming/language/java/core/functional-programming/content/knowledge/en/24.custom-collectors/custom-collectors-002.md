# Supplier Creates a New Accumulation Container in a Custom Collector (Java Stream)

In `Stream.collect(...)`, a **Collector** gathers multiple input elements into an aggregated result: a list, a set, a summary table, or a business structure. When building your own `Collector<T,A,R>`, the first component to understand is **`Supplier<A>` — a function that creates a new, independent *accumulation container* in a proper initial state**.

`Supplier` does not take elements from the stream and does not turn a `T` into an `R`. Its job is to **provide an `A` object that the accumulator can update**. In parallel mode, Stream may need multiple accumulation containers and combine them; therefore, writing a supplier incorrectly can cause data loss, duplication, race conditions, or results that depend on how work is split.

This lesson focuses on *the supplier creating a new accumulation container*, then places it in relation to `accumulator`, `combiner`, `finisher`, and the important constraints when processing in parallel. Examples use **Java 17+**.

## 1. The Four Components of a `Collector<T,A,R>`

A general collector has three type parameters:

- **`T`**: the input element type of the stream.
- **`A`**: the **intermediate accumulation container** type. This is where state is stored as each element is received.
- **`R`**: the final result type, which may be the same as or different from `A`.

The main components:

| Component | Functional Type | Role |
| --- | --- | --- |
| `supplier()` | `Supplier<A>`, `() -> A` | Creates a **new** container `A` in its initial state, used when accumulation is needed. |
| `accumulator()` | `BiConsumer<A,T>`, `(A,T) -> void` | Updates a container `A` when receiving an element `T`. |
| `combiner()` | `BinaryOperator<A>`, `(A,A) -> A` | Merges the results of two accumulation containers, returning a container `A` holding the combined state. |
| `finisher()` | `Function<A,R>`, `A -> R` | Converts container `A` into the final result `R`. |

Example of collecting a `Stream<String>` into a list:

~~~text
T = String
A = ArrayList<String>        (mutable accumulation container)
R = List<String>             (published result)

supplier        () -> new ArrayList<String>()
accumulator     (list, element) -> list.add(element)
combiner        (left, right) -> { left.addAll(right); return left; }
finisher        list -> List.copyOf(list)
~~~

The lines above are a **type and behavior diagram**, not standalone executable calls. `List.copyOf` creates a result list that does not support modification operations and does not accept null elements; this model is intended for non-null input data.

`A` is the temporary container, `R` is the output contract. **Supplier only creates `A`; it does not need to and should not create `R` itself**, except in the case where `A = R` and the collector uses identity finish.

## 2. What Does `Supplier<A>` Mean in Code?

`java.util.function.Supplier<T>` is a functional interface with one method:

~~~java
T get();
~~~

It takes no input parameters. Some common suppliers:

~~~java
// Illustrative snippet inside a Java method.
java.util.function.Supplier<java.util.ArrayList<String>> lists =
        java.util.ArrayList::new;

java.util.function.Supplier<java.util.HashMap<String, Integer>> maps =
        java.util.HashMap::new;
~~~

The method reference form `ArrayList::new` is a **constructor reference**: each call to `lists.get()` creates a new `ArrayList`. Semantically equivalent to `() -> new ArrayList<String>()`.

A supplier **should not return `null`**. If the collector does not have a valid container, the accumulator and combiner cannot fulfill their contracts. The initial state of `A` must also represent "no elements collected yet," without pre-populated business data that would be duplicated when there are multiple containers.

### Example verifying that two calls create two separate containers

Create the file `FreshSupplierDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public class FreshSupplierDemo {
    public static void main(String[] args) {
        Supplier<List<String>> supplier = ArrayList::new;

        List<String> first = supplier.get();
        List<String> second = supplier.get();

        first.add("An");
        second.add("Bình");

        System.out.println("same object=" + (first == second));
        System.out.println("first=" + first);
        System.out.println("second=" + second);
    }
}
~~~

~~~bash
javac --release 17 FreshSupplierDemo.java
java FreshSupplierDemo
~~~

Stdout:

~~~text
same object=false
first=[An]
second=[Bình]
~~~

`first` and `second` have the same **type**, but are **two different objects**. Adding `"An"` to the first list does not affect the second list. This independence is an essential part of a custom collector: the containers created by the supplier must have their own state, able to be accumulated and merged without accidentally sharing a mutable buffer.

## 3. Creating a Complete Collector with `Collector.of(...)`

This is the main factory when writing your own collector. The overload with a finisher has the form:

~~~java
// Conceptual signature for learning, not a standalone Java class.
static <T, A, R> Collector<T, A, R> of(
        Supplier<A> supplier,
        BiConsumer<A, T> accumulator,
        BinaryOperator<A> combiner,
        Function<A, R> finisher,
        Collector.Characteristics... characteristics);
~~~

Suppose you want to collect a `Stream<String>` into a list, but the output is an unmodifiable copy:

~~~java
Collector<String, List<String>, List<String>> collector =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                List::copyOf);
~~~

This snippet requires importing `Collector`, `ArrayList`, and `List`, which is used in the next complete program.

Create the file `CustomListCollectorDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;
import java.util.stream.Stream;

public class CustomListCollectorDemo {
    public static void main(String[] args) {
        Collector<String, List<String>, List<String>> collector =
                Collector.of(
                        ArrayList::new,
                        List::add,
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        },
                        List::copyOf);

        List<String> names = Stream.of("An", "Bình", "Chi")
                .collect(collector);

        System.out.println(names);
        System.out.println(names.getClass().getSimpleName());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 CustomListCollectorDemo.java
java CustomListCollectorDemo
~~~

The first output line is always:

~~~text
[An, Bình, Chi]
~~~

**Note on the `getClass().getSimpleName()` line:** the concrete implementation class name of the list returned by `List.copyOf` is not part of the API contract and may vary across JDKs. Therefore, **do not rely on that class name in tests or business logic**. The example above only expects checking the list line as a deterministic result; if you want stdout to be completely implementation-independent, remove the `System.out.println(names.getClass().getSimpleName());` statement.

To verify unmodifiability, you can actively try `names.add("Dũng")` inside a `try/catch(UnsupportedOperationException)`; there is no need to do this in production logic.

In this collector:

1. `ArrayList::new` creates an empty `List<String>` container.
2. `List::add` puts each string into that container.
3. `combiner` merges elements from the right container into the left one and **returns** the left one.
4. `List::copyOf` creates the result list `R` from container `A`.

Do not mark `IDENTITY_FINISH` for a collector with `finisher = List::copyOf`: the finisher **is not an identity operation**, even though both `A` and `R` are declared as `List<String>`.

## 4. Why Must a Supplier Create a New Container, Especially in Parallel?

With sequential streams, learners often imagine a collector only needs one `ArrayList` or one counter. However, a **parallel** collection can split the data and create multiple accumulation containers:

~~~text
Source: [A, B, C, D]

Supplier.get() ──→ container L (empty) ── accumulator(A), accumulator(B)
Supplier.get() ──→ container R (empty) ── accumulator(C), accumulator(D)

combiner(L, R) ──→ merged container [A, B, C, D]
finisher(merged container) ──→ result
~~~

This is a **conceptual diagram**, not a JDK guarantee to create exactly two containers or split the source as illustrated. The number of times the supplier is called can vary by source, implementation, parallel mode, and how the collector is used. A sequential pipeline typically needs one container, but you should not write logic that depends on the call count as an API contract.

**The supplier must guarantee creating an independent container each time.** Having Stream create separate containers and merge them with the combiner allows non-concurrent collectors to process in parallel without having multiple workers concurrently modify a single `ArrayList`.

Do not think that adding `.parallel()` automatically makes every accumulator thread-safe. Proper behavior must rely on the collector's contract and its `Characteristics`.

## 5. Critical Mistake: Returning the Same Shared Object

This is an **incorrect** pattern:

~~~java
// Incorrect illustration: every time the supplier is called, it returns the SAME list.
List<String> shared = new ArrayList<>();

Collector<String, List<String>, List<String>> broken =
        Collector.of(
                () -> shared,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                List::copyOf);
~~~

This snippet is inside a method with imports and should not be executed to predict its outcome. It violates the "empty, independent container when needed" contract:

- The second creation still sees elements from the first container.
- With a parallel stream, two tasks can concurrently call `add` on a non-thread-safe `ArrayList`.
- When `left == right`, `left.addAll(right)` appends the list to itself, which can duplicate data and break the reduction/merging semantics.
- If the collector is reused across multiple `collect` calls, state from the previous call persists, causing results to **leak data between collections**.

**The proper fix** is to put object creation inside the supplier body:

~~~java
// Correct: each call to get creates a new container.
() -> new ArrayList<String>()
// Equivalent:
ArrayList::new
~~~

Another subtle confusion:

~~~java
// Incorrect: the object was created once before the supplier is called.
ArrayList<String> existing = new ArrayList<>();
Supplier<ArrayList<String>> supplier = () -> existing;
~~~

Using lambda syntax does not make the result "new". Ask **does each call to `get()` actually create a new object?**, rather than just seeing `() ->`.

## 6. The Accumulation Container Must Start in a Neutral State

Simply creating different objects is not enough. The supplier needs to provide **the right empty/neutral state for the accumulation and combination operations**:

- Collecting a list: a new list with no elements yet.
- Counting: a new counter starting at `0`.
- Summing: an initial sum value of `0` (and a type with sufficient capacity if needed).
- Product: an initial product value of `1`.
- Finding min/max: needs a *no data yet* state or proper sentinel, without imposing a value that could skew the result.
- Multi-metric statistics: counter `0`, sum `0`, min/max in an unobserved state or appropriate initial values.

If the supplier returns a container pre-populated with a default record, every parallel container gets that extra record; when the combiner merges them, the default record is repeated multiple times. Therefore, the supplier should not read/write data that depends on the number of workers or execution timing.

### Custom statistics container example

Create the file `StatsCollectorDemo.java`:

~~~java
import java.util.List;
import java.util.stream.Collector;

public class StatsCollectorDemo {
    record Sale(int amount) {}
    record Result(long count, long sum, double average) {}

    static final class Acc {
        long count;
        long sum;

        void add(Sale sale) {
            count++;
            sum += sale.amount();
        }

        Acc merge(Acc other) {
            count += other.count;
            sum += other.sum;
            return this;
        }

        Result finish() {
            return new Result(
                    count,
                    sum,
                    count == 0 ? 0.0 : (double) sum / count);
        }
    }

    static Collector<Sale, Acc, Result> collector() {
        return Collector.of(
                Acc::new,
                Acc::add,
                Acc::merge,
                Acc::finish);
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale(10), new Sale(20), new Sale(30));

        Result normal = sales.stream().collect(collector());
        Result parallel = sales.parallelStream().collect(collector());
        Result empty = List.<Sale>of().stream().collect(collector());

        System.out.println("normal=" + normal);
        System.out.println("parallel=" + parallel);
        System.out.println("empty=" + empty);
    }
}
~~~

~~~bash
javac --release 17 StatsCollectorDemo.java
java StatsCollectorDemo
~~~

Stdout:

~~~text
normal=Result[count=3, sum=60, average=20.0]
parallel=Result[count=3, sum=60, average=20.0]
empty=Result[count=0, sum=0, average=0.0]
~~~

Analyzing the role of the supplier closely:

1. `Acc::new` creates a **new `Acc` object**. Both `long` fields are initialized by Java to `0`, so the initial state is neutral for summing and counting.
2. `Acc::add` receives a `Sale` and updates the container: increments count, adds amount to sum.
3. `Acc::merge` merges two `Acc` containers by adding count and sum, then returns the left container.
4. `Acc::finish` converts `A = Acc` into `R = Result`. The `Result` record represents a clean snapshot without exposing the mutable container.
5. On an empty stream, an appropriate initial accumulation state is still created and the finisher produces `Result[count=0, sum=0, average=0.0]`. If the business requirement wants "no average" instead of 0.0, change the **result contract**, for example `OptionalDouble`, rather than assuming 0.0 means an actual observation.

This collector produces the same result when processed sequentially or in parallel because adding counts and sums is associative under Java integer semantics, the containers are independent, and there is no external mutable state. However, `long` can still overflow if the data exceeds its representable range; if overflow checking is desired, a separate approach must be designed.

## 7. Reading the Contract of the Two `Collector.of` Overloads

In Java there are two common factories:

~~~java
// With a separate finisher: A can differ from R.
Collector.of(supplier, accumulator, combiner, finisher, characteristics...)

// Without a separate finisher: container A is used as result R (identity finish).
Collector.of(supplier, accumulator, combiner, characteristics...)
~~~

These are **illustrative API notations**, not complete Java calls.

In the overload without a finisher, `A` and `R` are the same type and the collector carries the `IDENTITY_FINISH` characteristic. For example, `Collector.of(ArrayList::new, List::add, combiner)` returns the accumulated list container as the result. No copying is needed if the contract allows returning a mutable list.

In the overload with a finisher, **do not manually attach `IDENTITY_FINISH`** if the finisher transforms the data, even if the declared input/output types match. Attaching the wrong characteristic can cause the framework to skip the finisher or perform an invalid cast.

### Example without a finisher: returning the accumulation container directly

Create the file `IdentityFinishDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.stream.Collector;
import java.util.stream.Stream;

public class IdentityFinishDemo {
    public static void main(String[] args) {
        Collector<String, ArrayList<String>, ArrayList<String>> collector =
                Collector.of(
                        ArrayList::new,
                        ArrayList::add,
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        });

        ArrayList<String> result =
                Stream.of("A", "B", "C").collect(collector);

        System.out.println(result);
        System.out.println(collector.characteristics().contains(
                Collector.Characteristics.IDENTITY_FINISH));
    }
}
~~~

~~~bash
javac --release 17 IdentityFinishDemo.java
java IdentityFinishDemo
~~~

Stdout:

~~~text
[A, B, C]
true
~~~

This is the case where `A = R = ArrayList<String>`. The supplier still must create a **new** container on each call; identity finish only means the final result is the accumulated container itself, and does **not** allow the supplier to return the same shared instance across calls.

## 8. Do Not Confuse with the `Stream.collect(supplier, accumulator, combiner)` Overload

Java Stream also has a **terminal operation** that accepts three functions directly:

~~~java
// Conceptual signature of Stream<T>.
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner);
~~~

It is easy to confuse `Collector.of` and `Stream.collect` because both have the words "supplier, accumulator, combiner", but the **combiner signatures differ**:

- In `Collector.of(...)`, the combiner is `BinaryOperator<A>`: **returns a container `A`** after combining.
- In `stream.collect(supplier, accumulator, combiner)`, the combiner is `BiConsumer<R,R>`: **returns `void`**, updating the target container with the contents of the source container.

Create the file `DirectCollectDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

public class DirectCollectDemo {
    public static void main(String[] args) {
        ArrayList<String> result = Stream.of("An", "Bình", "Chi")
                .collect(
                        ArrayList::new,
                        ArrayList::add,
                        ArrayList::addAll);

        System.out.println(result);
    }
}
~~~

~~~bash
javac --release 17 DirectCollectDemo.java
java DirectCollectDemo
~~~

Stdout:

~~~text
[An, Bình, Chi]
~~~

Here `ArrayList::new` still ensures a new accumulation container, `ArrayList::add` adds an element, and `ArrayList::addAll` merges containers. The method reference `ArrayList::addAll` points to a Java method returning `boolean`, yet it can still be used as a `BiConsumer` because the return value is discarded under the compatibility rules for method references/statement expressions. If that syntax is confusing for your team, use the lambda `(left, right) -> left.addAll(right)` for the `void` combiner.

The direct API is useful for simple mutable reductions that do not need a separate finisher. `Collector.of` is useful when you want to define a reusable collector, declare characteristics, and have an independent `finisher`.

## 9. Supplier in Sequential, Parallel, and Grouping Processing

One misconception is assuming the supplier **is always called exactly once**. That is not something to rely on:

- In a **typical sequential** pipeline, the framework may use one container for all the data.
- In a **parallel** pipeline, the framework may create multiple containers so that processing partitions accumulate independently and are later combined.
- With `groupingBy(classifier, downstreamCollector)`, the downstream supplier may create a separate accumulation container for each group to be processed.
- With characteristics such as `CONCURRENT`, execution behavior may differ; do not infer the supplier call count or the number of threads using the same container from a simple example.

Example of grouping data:

~~~java
// Illustrative snippet, assuming employees: List<Employee>.
Map<String, List<Employee>> byDepartment = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.toList()));
~~~

In this `groupingBy`, the downstream collector needs list containers for each group; they are not **one shared list** for all departments. When a custom downstream is needed, the custom collector's supplier must create the proper new container that each group and each partition can use.

If you want to provide a **Map type** for `groupingBy` or `toMap`, the `mapSupplier` parameter in the corresponding overloads must also provide a **new Map**. It is the same in principle, but it is a supplier for the **Map container** (not always the same `A` type of a direct custom collector).

## 10. How Do `CONCURRENT`, `UNORDERED`, and `IDENTITY_FINISH` Relate?

The `Collector.Characteristics` affect how Stream is allowed to use the collector:

| Characteristic | Key Meaning | Relation to Supplier |
| --- | --- | --- |
| `IDENTITY_FINISH` | Finisher is an identity operation; running the finisher can be skipped. | Container `A` is also result `R`; supplier still needs a new container. |
| `UNORDERED` | Result does not depend on the encounter order of elements. | Must not be declared if accumulation order matters to the result. |
| `CONCURRENT` | Accumulator can be called concurrently on the same accumulation container. | Container and updates must be safe for concurrent accumulation; do not attach if only using `ArrayList`/plain `long` counters. |

**Creating a new container does not mean that container is thread-safe.** An independent `ArrayList` fits the partitioned-accumulation-then-combine model of a non-concurrent collector, but is not safe when multiple threads actually call `add` on the same instance. Incorrectly marking `CONCURRENT` on a collector using an unsynchronized `ArrayList` creates data hazards.

Conversely, `CONCURRENT` **is not required** for a collector to run with `parallelStream()`. Many non-concurrent collectors still work in parallel by accumulating in separate containers and then using the combiner.

Be careful with `UNORDERED`: a collector that appends a list in input encounter order usually **cares about encounter order**, so it should not be marked unordered just to attempt optimization. `CONCURRENT` also does not by itself decide whether processing ignores encounter order: the framework also considers whether the source is ordered or unordered and other characteristics.

## 11. Contract Constraints to Uphold

A valid supplier must be compatible with the accumulator and combiner. Check the following:

**A. Fresh container:** different calls to `supplier.get()` create accumulation containers with **independent** state, without sharing internal mutable structures. Immutable shared constants inside the container are acceptable, provided they do not cause shared mutable state.

**B. Neutral container:** if no elements are added to the container, the result after the finisher corresponds to the result of an **empty stream**. When merged with an already-accumulated container, an empty container does not corrupt the result.

**C. Combiner compatibility:** combining two containers must be equivalent to adding all corresponding elements into one container, following the encounter order/collector rules. Proper **associativity** is required so that how groups are split does not change the meaning.

**D. Non-interference with source and statelessness:** the accumulation function does not modify the collection being traversed or rely on external mutable state. The supplier should also not read changing shared state that breaks independence between containers.

**E. Never return null:** the supplier must return a valid `A` object. If an empty result needs to be represented by `Optional.empty()`, a `hasValue` flag, or a count of 0, record it via **state inside the container**, not by using a null container reference.

**F. Clean finishing:** if `A` is a mutable structure while `R` needs to be immutable, use the finisher to create a snapshot or appropriate copy; do not falsely declare `IDENTITY_FINISH` to skip the conversion step.

## 12. Example Verifying a Correct Supplier Across Multiple `collect` Calls

A properly designed collector can reuse the **collector definition** across multiple collections on different streams without leaking data. Create the file `ReusableCollectorDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;
import java.util.stream.Stream;

public class ReusableCollectorDemo {
    public static void main(String[] args) {
        Collector<String, ArrayList<String>, ArrayList<String>> collector =
                Collector.of(
                        ArrayList::new,
                        ArrayList::add,
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        });

        List<String> first = Stream.of("A", "B")
                .collect(collector);
        List<String> second = Stream.of("C")
                .collect(collector);

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("shared=" + (first == second));
    }
}
~~~

~~~bash
javac --release 17 ReusableCollectorDemo.java
java ReusableCollectorDemo
~~~

Stdout:

~~~text
first=[A, B]
second=[C]
shared=false
~~~

Across the two `collect` calls, the supplier creates a new container; the second result does not contain A/B from the first. **Reusing a valid `Collector` is different from reusing a `Stream`**: a stream that has already executed a terminal operation cannot be reused, whereas a stateless collector definition can be used for many independent streams.

The `ReusableCollectorDemo` example uses mutable output and identity finish; in APIs requiring immutability, there should be a finisher that creates an independent copy.

## 13. Avoid Confusing Container Creation with Single-Element Creation

Methods with easily confused signatures:

~~~text
Supplier<A>                   : ()  -> A       (creates the accumulation container)
BiConsumer<A,T>               : (A,T) -> void (adds an element to the container)
Function<T,R>                 : T   -> R       (transforms a single element)
BinaryOperator<A>             : (A,A) -> A     (merges two containers)
Function<A,R>                 : A   -> R       (finalizes the container)
~~~

For example, `ArrayList::new` can be a container supplier. But `User::new` is only appropriate when **container `A` is actually a User** and its state/behavior has accumulation semantics. Do not use a constructor reference just because you see `new`; you must understand that **what is created is the aggregated state**, not the result object for each element.

If the goal is to map each `String` to a `User`, use `map(User::new)` in the stream and choose a collector afterward. In `Collector.of`, the supplier does not receive the `String` flowing through the pipeline; the **accumulator** is what receives each element.

## 14. Comparing Custom Collectors with Built-in Collectors

Java has many collectors that already solve the accumulation container problem:

| Goal | Usually Preferred Approach | Reason |
| --- | --- | --- |
| Collect elements into a list | `Collectors.toList()` or `Stream.toList()` | No need to write supplier/combiner/finisher yourself. |
| Need a specific mutable list | `Collectors.toCollection(ArrayList::new)` | Supplier is passed directly, collection type is explicit. |
| Collect into a set | `Collectors.toSet()` or `toCollection(HashSet::new)` | Handles the container using built-in APIs. |
| Create a `Map<K,V>` | `Collectors.toMap(...)` | Supports merge function and map supplier. |
| Grouping | `Collectors.groupingBy(...)` | Creates appropriate accumulation containers per group. |
| Numeric statistics | `Collectors.summarizingInt(...)` | Provides a statistics container and verified merge logic. |
| Custom aggregation algorithm or specialized result | `Collector.of(...)` | You control `A`, supplier, accumulator, combiner, and finisher. |

Example of choosing the collection type with a supplier in the built-in API:

~~~java
// Inside a method where List, ArrayList, and Collectors are imported.
ArrayList<String> names = source.stream()
        .collect(java.util.stream.Collectors.toCollection(
                ArrayList::new));
~~~

Here `source` is an illustrative `Collection<String>`. `toCollection(ArrayList::new)` already handles using a supplier to create the container; there is no need to write a custom collector just to ensure the result is an `ArrayList`.

Custom collectors are valuable when rich state is needed (such as count/sum/min/max combined with business conditions, a graph structure, or a snapshot DTO). If you only need to sum integers, APIs like `mapToInt(...).sum()` or `summingInt(...)` are usually clearer.

## 15. Common Mistakes with `Supplier<A>`

1. **Returning the same pre-created instance:** `() -> sharedList` makes containers non-independent.
2. **Initializing non-neutral state:** pre-adding elements or a non-zero count, leading to duplication after the combiner.
3. **Returning `null`:** the accumulator has no container `A` to operate on, causing an error.
4. **Thinking the supplier receives each `T`:** the supplier takes no arguments; the accumulator receives `(A,T)`.
5. **Thinking the supplier is only called once:** parallel execution and downstream collectors may need multiple containers.
6. **Assuming `ArrayList::new` makes a collector concurrent:** a new container is not equivalent to thread-safety for a container accessed concurrently.
7. **Marking `CONCURRENT` on a plain counter or `ArrayList`:** easily causes race conditions when Stream shares a container.
8. **Marking `IDENTITY_FINISH` when there is a copy/transform step:** can cause the finisher not to be used.
9. **Writing the wrong combiner type:** `Collector.of` requires `BinaryOperator<A>` returning `A`; the three-argument `Stream.collect` requires `BiConsumer<R,R>` updating a container.
10. **Not merging state in the combiner:** sequential runs appear correct, but parallel results lose data.
11. **Modifying an external container after obtaining an expected immutable result:** must distinguish between having/not having a finisher and the type `R`.
12. **Using external mutable state in supplier/accumulator:** can create dependencies between runs and non-reproducible results.
13. **Reusing a consumed stream:** a collector can be reused; a stream cannot be reused.
14. **Relying on the supplier call count to count data batches:** the number of containers is not a stable business metric.
15. **Not testing an empty source:** with an empty source, the neutrality of the supplier and finisher is most clearly revealed.

## 16. Checklist Before Writing a Supplier

- What are the types `T`, `A`, `R`? Do they need to be different?
- Does the supplier truly **create a new container on every call**?
- Is the new container in a **neutral state** and free of mutable buffers shared with other containers?
- For an empty stream, does the result after the finisher follow the business rules?
- Does the accumulator update container `A` accurately for each `T`?
- Does the combiner fully merge two containers, have associativity, and return `A` properly?
- If `A` is mutable and `R` needs to be immutable, does the finisher create an appropriate snapshot?
- Have `CONCURRENT`, `UNORDERED`, or `IDENTITY_FINISH` been accidentally declared incorrectly?
- Do sequential and parallel results have the same meaning? Do two independent `collect` calls avoid state leakage?
- Is there a built-in collector (`toCollection`, `groupingBy`, `summarizingInt`) that expresses the goal more clearly?

**Remember:** `Supplier<A>` of a custom collector **creates a new, independent, neutral accumulation container**. It does not process input elements, does not decide the merging policy, and must not return the same shared container. When combined properly with the accumulator, combiner, and finisher, the supplier enables the collector to work validly on empty, sequential, and parallel streams alike.
