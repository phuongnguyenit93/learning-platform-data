# Collector<T,A,R> and the Roles of the Three Type Parameters in Java Stream

In the Java Stream API, `Collector<T,A,R>` is the contract that describes how to **collect multiple input elements into a single result**. Built-in collectors such as `Collectors.toList()`, `joining()`, and `groupingBy()` handle many common cases. However, when you need custom aggregation rules, you can create a **custom collector** using `Collector.of(...)` or by implementing the `Collector` interface directly.

The most important point for reading and designing a collector properly is understanding **the three type parameters `T`, `A`, and `R`**:

- **`T` — input element type:** the type of **each individual element** entering the collector.
- **`A` — mutable accumulation type:** the type of the **intermediate accumulation state** that the collector creates and updates while traversing the Stream.
- **`R` — result type:** the type of the **final result** returned by `stream.collect(collector)`.

**`T`, `A`, and `R` can be the same, but they do not have to be.** For example, collecting a Stream of strings into a comma-joined string can have `T=String`, `A=StringJoiner`, and `R=String`. When accumulating into an ArrayList and returning that same ArrayList, you can have `A=R=ArrayList<String>`. When accumulating statistics through a mutable class and returning an immutable record, `A` and `R` are also different.

This lesson progresses from the data model and component functions of a Collector to runnable Java 17 code, the meaning of `IDENTITY_FINISH`/`CONCURRENT`/`UNORDERED`, parallel processing, and common pitfalls.

## 1. Three types: read them as three distinct roles

Consider the problem of joining normalized person names:

```java
List<String> names = List.of("Lan", "Mai", "Minh");
String display = names.stream()
        .collect(Collectors.joining(" | "));
```

This is a code snippet inside a method, requiring imports for `java.util.List` and `java.util.stream.Collectors`. `joining` is a built-in collector; the result is `"Lan | Mai | Minh"`.

To understand how a custom collector does similar work, you can picture:

| Role | Example type | Why |
| --- | --- | --- |
| `T` | `String` | The Stream feeds in each name `"Lan"`, `"Mai"`, `"Minh"`. |
| `A` | `StringJoiner` | A container that can append names and merge two containers. |
| `R` | `String` | The application needs a string for display, not a `StringJoiner`. |

You can write the resulting collector type as:

```java
Collector<String, StringJoiner, String>
```

This is an **illustrative parameterized type**, not a variable declaration or a standalone program.

Note: **`A` is not the type of each newly added element**, nor is it always the type returned to the caller. `A` is the state used by `supplier`, `accumulator`, and `combiner` **during collection**. Once collection finishes, `finisher` can convert `A` to `R`.

## 2. Four fundamental components of a Collector

At its core, a Collector defines four functions:

1. **Supplier** creates a new container/accumulation state of type `A`.
2. **Accumulator** adds an element `T` into the state `A`.
3. **Combiner** merges two states `A` into a single `A`.
4. **Finisher** transforms the final state `A` into a result of type `R`.

The corresponding functional forms:

```java
Supplier<A> supplier()
BiConsumer<A, T> accumulator()
BinaryOperator<A> combiner()
Function<A, R> finisher()
```

These are **conceptual signatures**, not complete Java code. In `Collector<T,A,R>`, these methods have broader generic forms in the actual API; the notation above makes it easier to see the types going in and out.

<escape>**Data flow diagram:**</escape>

```text
       Stream<T> — elements T
                    |
              supplier() -> A
                    |
          accumulator(A, T) -> void
                    |
          multiple A in parallel?
                    |
             combiner(A, A) -> A
                    |
               finisher(A) -> R
                    |
          stream.collect(...) -> R
```

With a sequential Stream, the framework may not need to call the combiner. With a parallel Stream, it may create multiple separate `A` states and then call the combiner to merge them. Therefore, **do not write a dummy combiner or have it throw `UnsupportedOperationException` just because sequential testing did not trigger it**.

### Important points about the signatures

- `accumulator` is a `BiConsumer<A,T>`: it accepts the state and an element, and **returns no value**. It is designed to mutate the state.
- `combiner` is a `BinaryOperator<A>`: it accepts two states and **returns one state**. Typically, it merges data from the second state into the first state and returns the first state.
- `finisher` is a `Function<A,R>`: conversion is only needed when `A` and `R` do not share the same identity result.
- `supplier` must create an appropriate state each time it is requested; do not return an inadvertently shared mutable singleton object.

## 3. Two important overloads of Collector.of

Java provides commonly used factory overloads:

```java
static <T, R> Collector<T, R, R> of(
    Supplier<R> supplier,
    BiConsumer<R, T> accumulator,
    BinaryOperator<R> combiner,
    Collector.Characteristics... characteristics
)

static <T, A, R> Collector<T, A, R> of(
    Supplier<A> supplier,
    BiConsumer<A, T> accumulator,
    BinaryOperator<A> combiner,
    Function<A, R> finisher,
    Collector.Characteristics... characteristics
)
```

These are **API signatures presented for learning**, not standalone runnable code.

**The three-function form** (supplier, accumulator, combiner) fits when **the accumulation state itself is the result**: `A=R`. This overload carries the `IDENTITY_FINISH` characteristic; no type-converting finisher needs to be supplied.

**The four-function form** (with finisher) fits when **the accumulation state must be transformed before returning**: `A` can differ from `R`. For example, after counting and summing in a mutable state, the finisher creates an immutable `record` holding the count/sum/average values.

Both overloads also accept an optional `Characteristics...` varargs list, but **do not attach `CONCURRENT` or `UNORDERED` unless your logic satisfies the contract**.

## 4. Java 17 Example: T=String, A=StringJoiner, R=String

Create the file **`JoiningCollectorDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.StringJoiner;
import java.util.stream.Collector;

public class JoiningCollectorDemo {

    static Collector<String, StringJoiner, String> upperNames() {
        return Collector.of(
                () -> new StringJoiner(" | "),
                (joiner, name) -> joiner.add(
                        name.toUpperCase(Locale.ROOT)),
                StringJoiner::merge,
                StringJoiner::toString
        );
    }

    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Mai", "Minh");

        String sequential = names.stream().collect(upperNames());
        String parallel = names.parallelStream().collect(upperNames());
        String empty = List.<String>of().stream().collect(upperNames());

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("empty=[" + empty + "]");
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 JoiningCollectorDemo.java
java JoiningCollectorDemo
```

**Exact stdout:**

```text
sequential=LAN | MAI | MINH
parallel=LAN | MAI | MINH
empty=[]
```

Reading the types along the data flow:

1. `T=String`: each `name` is a String from the list.
2. `A=StringJoiner`: `supplier` creates `new StringJoiner(" | ")`; `accumulator` calls `add` after converting the name to uppercase.
3. `combiner` uses `StringJoiner.merge` to merge the accumulated parts.
4. `R=String`: `finisher` uses `StringJoiner.toString` to return the resulting string, instead of handing a `StringJoiner` object to the caller.

The `List` source has encounter order, and this collector does not declare `UNORDERED`, so the joined string preserves encounter order during both sequential and parallel collection in accordance with the contract. An empty `StringJoiner` produces `""`, so when printed inside square brackets, the result is `empty=[]`.

**Avoid a common misconception:** A parallel Stream may execute the accumulator step across multiple threads, but that does not mean the `StringJoiner` in this example is shared for concurrent modification by multiple threads. This is a **non-concurrent** collector; the framework can use independent states and then combine them.

## 5. When T, A, and R are all different

An application has a Stream of `Sale` transaction records and wants to aggregate them into an immutable `Report`. The accumulation state can be a mutable `Summary` class with count and sum.

| Role | Type | Job |
| --- | --- | --- |
| `T` | `Sale` | Single record with `amount`. |
| `A` | `Summary` | Tracks count and total during collection. |
| `R` | `Report` | Final result record with computed mean, no setters. |

**Choosing `A` does not have to match the final object.** You can keep a minimal state sufficient to build the result, avoiding allocating a new Report object every time a record is added.

### Complete Java 17 example: custom statistics collector

Save as **`SaleSummaryCollectorDemo.java`**:

```java
import java.util.List;
import java.util.stream.Collector;

public class SaleSummaryCollectorDemo {
    record Sale(String code, int amount) {}
    record Report(long count, long total, double average) {}

    static final class Summary {
        private long count;
        private long total;

        void add(Sale sale) {
            count++;
            total += sale.amount();
        }

        Summary merge(Summary other) {
            count += other.count;
            total += other.total;
            return this;
        }

        Report finish() {
            double average = count == 0 ? 0.0 : (double) total / count;
            return new Report(count, total, average);
        }
    }

    static Collector<Sale, Summary, Report> summarizingSales() {
        return Collector.of(
                Summary::new,
                Summary::add,
                Summary::merge,
                Summary::finish
        );
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", 10),
                new Sale("B", 20),
                new Sale("C", 30)
        );

        Report sequential = sales.stream().collect(summarizingSales());
        Report parallel = sales.parallelStream().collect(summarizingSales());
        Report empty = List.<Sale>of().stream().collect(summarizingSales());

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("empty=" + empty);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 SaleSummaryCollectorDemo.java
java SaleSummaryCollectorDemo
```

**Exact stdout:**

```text
sequential=Report[count=3, total=60, average=20.0]
parallel=Report[count=3, total=60, average=20.0]
empty=Report[count=0, total=0, average=0.0]
```

Detailed explanation:

- `Summary::new` creates **a new accumulator**. The default value of both `long` fields is 0.
- `Summary::add` receives a `Sale` and updates count/total; it does not return `Summary` because it matches the `BiConsumer<Summary,Sale>` signature.
- `Summary::merge` receives the second state, adds it into the first state, and returns the first state. This is a `BinaryOperator<Summary>`.
- `Summary::finish` creates a new `Report`. `Report` is a Java 17 record with accessors and a stable string representation.
- `average=0.0` when empty is **this example's own convention**, not a requirement for every statistics collector. If business logic needs to distinguish no data from an average of 0, return `OptionalDouble` or a separate state.

This collector does not declare `CONCURRENT`; the separate states of each parallel branch are merged using `merge`. Adding count and total for small datasets satisfies the associativity requirement. For large datasets, **`long` can still overflow**; production code needs an appropriate arithmetic policy.

## 6. A=R and IDENTITY_FINISH: when no result type conversion is needed

Another collector might gather strings into an `ArrayList<String>` and return **the accumulated list itself**. In that case:

```text
T = String
A = ArrayList<String>
R = ArrayList<String>
```

You can create the collector using the overload without a separate finisher. With this overload, `Collector.of` provides the **`IDENTITY_FINISH`** characteristic. That means the result of type `R` is effectively the state of type `A`, requiring no meaningful transformation.

Conversely, if you need an **unmodifiable `List<String>`** after accumulation, `A` can still be `ArrayList<String>` while `R` is a `List<String>` created via `List.copyOf`. That collector **does not** have `IDENTITY_FINISH`, because the finisher must actually run to produce the new result.

### Java 17 program: comparing both results

Save as **`CollectorFinishDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

public class CollectorFinishDemo {

    static Collector<String, ArrayList<String>, ArrayList<String>>
    mutableListCollector() {
        return Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
    }

    static Collector<String, ArrayList<String>, List<String>>
    readOnlyListCollector() {
        return Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                list -> List.copyOf(list)
        );
    }

    public static void main(String[] args) {
        List<String> source = List.of("A", "B");

        var mutableCollector = mutableListCollector();
        var readOnlyCollector = readOnlyListCollector();

        ArrayList<String> mutable =
                source.parallelStream().collect(mutableCollector);
        List<String> readOnly =
                source.parallelStream().collect(readOnlyCollector);

        mutable.add("C");

        System.out.println("mutable=" + mutable);
        System.out.println("readOnly=" + readOnly);
        System.out.println("mutableIdentityFinish="
                + mutableCollector.characteristics().contains(
                    Collector.Characteristics.IDENTITY_FINISH));
        System.out.println("readOnlyIdentityFinish="
                + readOnlyCollector.characteristics().contains(
                    Collector.Characteristics.IDENTITY_FINISH));

        try {
            readOnly.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("readOnlyAdd=UnsupportedOperationException");
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 CollectorFinishDemo.java
java CollectorFinishDemo
```

**Exact stdout:**

```text
mutable=[A, B, C]
readOnly=[A, B]
mutableIdentityFinish=true
readOnlyIdentityFinish=false
readOnlyAdd=UnsupportedOperationException
```

In the `mutableListCollector` factory, the accumulator holds an `ArrayList` and the final result is that very list. With `readOnlyListCollector`, the finisher calls `List.copyOf`, producing a List that rejects mutating operations like `add`. The elements in this example are non-null strings; `List.copyOf` rejects null elements.

**Two notes on types:**

1. `List<String>` in `R` is only the **static type** of the result. Mutability depends on the contract of the actual runtime object. `List.copyOf` provides an unmodifiable result; `Collectors.toList()` **does not guarantee** returning a mutable ArrayList.
2. **Do not add `IDENTITY_FINISH` to a collector whose finisher converts `A` into a different object.** When this characteristic is declared, the Stream framework is permitted to skip calling the finisher under valid circumstances. Declaring it falsely breaks the contract and can lead to type errors or unexpected results.

## 7. Rules for supplier, accumulator, and combiner in parallel execution

A parallel Stream can split elements into multiple work chunks. A non-concurrent collector typically operates according to this model:

```text
                   Stream<T>
                  /         \
       supplier() -> A1    supplier() -> A2
       accumulate T        accumulate T
                  \         /
                 combine(A1,A2) -> A
                          |
                    finisher(A) -> R
```

This is a **conceptual diagram**; it does not promise that the Stream splits into exactly two tasks or calls the methods the exact number of times drawn.

### Key requirements

**Supplier:** each time it creates a new state, it must provide a valid initial container (the identity of the combination operation). Avoid:

```java
// INTENTIONALLY FLAWED BY DESIGN:
ArrayList<String> shared = new ArrayList<>();
Collector<String, ?, ?> broken = Collector.of(
        () -> shared,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
```

This is a warning snippet requiring the relevant imports; the flaw is that **the supplier returns the same shared object** for multiple tasks. During merging, there is a risk of adding a list to itself, duplicating data, or causing concurrent modification races across threads. This pattern is not a valid collector for general aggregation.

**Accumulator:** updates the state created by the supplier; must not modify the Stream source, rely on a global mutable counter, or perform side effects that depend on exact thread execution order.

**Combiner:** must be correct for any valid split. For example, with `ArrayList`:

```java
(left, right) -> {
    left.addAll(right);
    return left;
}
```

This pattern combines the contents of two states into a single state to return. For sequences that must preserve encounter order, the combiner must append right after left. Do not swap the order just because "parallel runs unordered" — **execution order** and **encounter order** are two different concepts.

**Finisher:** transforms the final state into the result; do not assume it will be called per element or per subtask. If you need to convert to immutable data, do it in the finisher and do not declare `IDENTITY_FINISH`.

## 8. Two conditions: associativity and identity

A correct Collector must have mutually compatible components so that collection does not depend on how the Stream framework splits and merges work.

- **Identity:** when combining an accumulated result with a new empty container from the supplier, the result must be semantically equivalent to the original result.
- **Associativity:** different ways of grouping and combining states must yield semantically equivalent results, regardless of grouping order.

For example, with string joining:

```text
merge(merge(A, B), C) == merge(A, merge(B, C))
```

The `==` symbol here denotes **equivalence in result content** in the diagram, **not a requirement that two Java objects share the same reference**.

For `Summary` counting/summing, the merge operation:

```java
count += other.count;
total += other.total;
```

is associative in the additive sense of the example data and has an empty state `count=0,total=0`. For order-sensitive operations (such as string joining), the combiner must also respect the appropriate order if the collector is not `UNORDERED`.

**Do not compute an average directly by averaging two sub-averages** while ignoring sample counts: for instance, one group has 1 element of 100, and the other group has 9 elements of 0; the true overall average is 10, not `(100+0)/2 = 50`. Store count/sum in `A`, and compute the average in `finisher`.

## 9. The three common Characteristics

`Collector.Characteristics` describes guarantees that the Stream framework can use for optimization.

| Characteristic | Meaning | When to be cautious |
| --- | --- | --- |
| `IDENTITY_FINISH` | The accumulation state can be used directly as the final result | Do not declare if `finisher` actually converts A to R |
| `UNORDERED` | The result does not depend on encounter order | Do not mark if joining strings or keeping the "first occurrence" |
| `CONCURRENT` | Accumulator may be called concurrently on the **same** state A | The state must genuinely support thread-safe updates |

There is no general flag named `PARALLEL`: **a non-concurrent collector can still be used safely with a parallel stream** because each subtask has its own state and the combiner merges them.

### CONCURRENT does not mean every Collector should have it

If `A=ArrayList` and the accumulator calls `add`, you must not declare `CONCURRENT` just because the pipeline runs in parallel; `ArrayList` is not safe for concurrent updates. If `A` has operations that are safe when called concurrently and the logic does not depend on order, `CONCURRENT` and `UNORDERED` may be appropriate depending on the case.

### When characteristics and source combine

With a concurrent collector, the Stream framework can use a single shared state for concurrent accumulation under suitable conditions; this depends on either the `UNORDERED` characteristic or the Stream lacking encounter order. If the conditions for concurrent reduction on a shared container are not met, the framework can split states as usual.

**Characteristics are contracts, not arbitrary performance hints.** Marking them incorrectly can cause race conditions, wrong ordering, or skipped finishers.

## 10. Java 17 Example: Concurrent element-counting Collector

You can build a simple collector that counts elements using a `LongAdder` state (from `java.util.concurrent.atomic`), which supports atomic updates distributed across threads. This example intentionally ignores encounter order, so it can declare `CONCURRENT` and `UNORDERED`.

Create the file **`ConcurrentCountCollectorDemo.java`**:

```java
import java.util.List;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.Collector;

public class ConcurrentCountCollectorDemo {
    static Collector<String, LongAdder, Long> counter() {
        return Collector.of(
                LongAdder::new,
                (adder, value) -> adder.increment(),
                (left, right) -> {
                    left.add(right.sum());
                    return left;
                },
                LongAdder::sum,
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED
        );
    }

    public static void main(String[] args) {
        List<String> letters = List.of("A", "B", "C", "D", "E");

        long sequential = letters.stream().collect(counter());
        long parallel = letters.parallelStream().collect(counter());
        long empty = List.<String>of().stream().collect(counter());

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("empty=" + empty);
        System.out.println("identityFinish=" + counter().characteristics()
                .contains(Collector.Characteristics.IDENTITY_FINISH));
    }
}
```

Run:

```bash
javac -encoding UTF-8 ConcurrentCountCollectorDemo.java
java ConcurrentCountCollectorDemo
```

**Exact stdout:**

```text
sequential=5
parallel=5
empty=0
identityFinish=false
```

Here `T=String`, `A=LongAdder`, `R=Long`. The accumulator only increments the counter without reading the `String` value; that is an intentional choice because the task only counts elements.

`CONCURRENT` fits because `LongAdder.increment()` supports calls from multiple threads, `UNORDERED` fits because counting does not depend on order, and `IDENTITY_FINISH` is absent because `finisher` returns a `Long` from the `LongAdder` state. In application code, `Collectors.counting()` is a simpler choice if you only need to count; the goal here is to learn the three types `T,A,R` and collector characteristics accurately.

`LongAdder.sum()` is not a strictly atomic snapshot when concurrent updates are still in progress. However, the framework only calls the finisher after accumulation for the result has completed, so reading the final sum in this collector is appropriate. Do not expose the state externally and call `sum()` between updates if you need a linearizable snapshot.

## 11. Comparing Collector<T,A,R> with three-argument Stream.collect

Alongside `collect(Collector)`, the Stream object has an overload:

```java
<R> R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R,R> combiner
)
```

This is a conceptual API signature. Note the differences:

- The **`Stream.collect(supplier, accumulator, combiner)`** form does not take a separate finisher. The collection container itself is the result: think of it as `A=R`.
- The **`Stream.collect(Collector<T,A,R>)`** form can use any suitable collector, including collectors where `A` differs from `R` via a finisher and collectors with `Characteristics`.
- The combiner in three-argument `Stream.collect` is a `BiConsumer<R,R>` that mutates the target container and **returns no value**. The combiner in `Collector` is a `BinaryOperator<A>`, which must **return the merged state**.

Example snippet requiring `List` and `ArrayList` imports:

```java
ArrayList<String> names = List.of("A", "B", "C")
        .stream()
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );
```

Here the three arguments are passed **directly to `Stream.collect`**, not `Collector.of`. This approach works when the goal is to build a container directly. If you want to normalize names, produce an immutable statistics report, or reuse the same logic across multiple pipelines, `Collector<T,A,R>` with an explicit finisher is usually a better fit.

Do not confuse `reduce` with `collect`:
- `reduce` describes a value-combining operation whose identity and operator must generally be stateless and associative.
- `collect` is designed for **mutable reduction**, in which the accumulator mutates a dedicated state created by the supplier.

A `reduce` call that uses `new ArrayList<>()` as its identity and mutates it in the accumulator can violate the contract, especially when run in parallel. That does not make it a valid collector just because both APIs "combine elements".

## 12. Scenarios for choosing types T, A, and R

| Problem | T | A | R | Notes |
| --- | --- | --- | --- | --- |
| Collect into ArrayList and return the List itself | `String` | `ArrayList<String>` | `ArrayList<String>` | Can use `IDENTITY_FINISH` |
| Join strings with a delimiter | `String` | `StringJoiner` | `String` | Finisher calls `toString` |
| Aggregate sales into a report | `Sale` | `Summary` | `Report` | Finisher computes average |
| Count into a long | `String` | `LongAdder` | `Long` | Can be concurrent if contract holds |
| Group by region | `Order` | Map/group container | `Map<String,List<Order>>` | Standard collector is usually suitable |
| Collect then return an unmodifiable List | `String` | `ArrayList<String>` | `List<String>` | Finisher `List.copyOf` |

In the generic type `Collector<T,A,R>`, **choose `T` from the Stream's elements first**. Next, ask "what state must be kept to build the result?" to choose `A`, and "what does the caller ultimately want to receive?" to choose `R`. Do not start by forcing all three types to be the same just for brevity.

For example, if the final goal is an average, `T` might be a `Purchase` with an amount, `A` needs **count and sum**, and `R` is a `double` or `OptionalDouble` per the application's contract. Do not hastily pick `A=Double` and try to merge unweighted sub-averages.

## 13. Step-by-step guide to designing a custom collector

1. **Define the business result `R`.** For example, a `Report` with count, total, and average, or a normalized `String`.
2. **Identify the input element `T`.** This is the element **after** the pipeline's `filter`/`map` operations, not necessarily the original source object.
3. **Design the state `A`.** Keep only the data needed to aggregate; prefer a simple state structure with clearly named fields.
4. **Write a supplier that creates a valid identity state.** Each call must be able to create a clean, independent state if the collector is not concurrent.
5. **Write an accumulator that updates state and checks for nulls.** Each element passing through the collector must contribute to the state exactly once when accumulated.
6. **Write a combiner and verify associativity.** Test merging states across different split patterns.
7. **Write a finisher to convert `A` to `R` if needed.** For example, `List.copyOf`, `StringJoiner.toString`, or constructing an immutable record.
8. **Choose Characteristics carefully.** Do not use `IDENTITY_FINISH` when there is a conversion, do not use `CONCURRENT` with non-thread-safe state, and do not use `UNORDERED` if order is required.
9. **Test three inputs:** a multi-element Stream, a single-element Stream, and an empty Stream.
10. **Run both sequential and parallel** on the same dataset to compare result contents if the application uses parallelism.
11. **Measure performance when needed**; do not assume a custom collector is faster than a built-in one. If the requirement can be written concisely with `toList`, `joining`, `groupingBy`, or `summarizingInt`, consider using the standard collector.

In particular, **do not declare `CONCURRENT` merely hoping for a speedup**. If the state uses locks or requires preserving order, performance may not meet expectations.

## 14. Common mistakes

1. **Confusing `A` and `R`:** `A` is the internal accumulation state, while `R` is the result the caller receives.
2. **Assuming `T` always equals the original collection's element type:** after `map`, the collector receives the transformed Stream's element type.
3. **Using a supplier that returns a mutable singleton:** multiple tasks can share state and merge incorrectly.
4. **Stubbing out the combiner with an exception:** sequential pipelines may run, but parallel ones can fail.
5. **Non-associative or order-reversing combiner:** the result depends on how the Stream splits tasks.
6. **Mixing up `Collector.of` and three-argument `Stream.collect`:** their combiners have different types and return contracts.
7. **Forgetting a finisher when `A` differs from `R`:** the caller gets the wrong type or the code fails to compile.
8. **Incorrectly adding `IDENTITY_FINISH`:** this can cause the framework to skip a required finisher.
9. **Adding `CONCURRENT` to ArrayList/StringJoiner:** concurrent updates on the same state are unsafe.
10. **Adding `UNORDERED` to algorithms that keep the first occurrence or join strings in order:** this can break output order guarantees.
11. **Computing an average by taking the unweighted mean of sub-averages:** wrong when groups have different sizes.
12. **Returning a mutable state and continuing to use it as a shared global:** loses lifecycle control and thread safety.
13. **Assuming the finisher always runs:** with `IDENTITY_FINISH`, the framework can skip it.
14. **Assuming a concurrent collector is guaranteed to be faster:** it still depends on workload, contention, data, and core count.
15. **Failing to test an empty Stream:** supplier/finisher must produce a meaningful empty result.
16. **Not managing numeric overflow:** `long` counts and sums still have limits.
17. **Writing a custom collector when a standard collector already fits:** increases complexity and bug risk.
18. **Relying on thread or iteration order to print stdout in parallel demos:** thread scheduling has no ordering guarantees.

## 15. Self-check

**Question 1.** In `Collector<String,StringJoiner,String>`, which types represent the element, state, and result?

**Answer:** `T=String`, `A=StringJoiner`, `R=String`. The finisher typically calls `toString()` to convert A to R.

**Question 2.** Why must `Collector<Sale,Summary,Report>` have a finisher when Summary is a mutable class and Report is an immutable record?

Because `A=Summary` differs from `R=Report`. The finisher constructs `Report` from the aggregated state, such as computing average from count and total.

**Question 3.** What does a custom Collector's combiner return?

**Answer:** A state `A`, matching the `BinaryOperator<A>` type. It is different from the void `BiConsumer<R,R>` combiner of the three-argument `Stream.collect` overload.

**Question 4.** When can `IDENTITY_FINISH` be declared?

When the accumulated result can directly serve as the final result under the contract; no actual conversion step from A to R is needed. Do not declare it if you need `List.copyOf`, record construction, or `StringJoiner.toString`.

**Question 5.** Should a collector using `ArrayList` as A be marked `CONCURRENT`?

**No**, if the accumulator calls `add` directly on the same ArrayList. ArrayList is not safe for concurrent updates by multiple threads. A non-concurrent collector can still collect in parallel using separate states and a combiner.

**Question 6.** Why does an averaging collector usually use a state with `count` and `sum` instead of just an average field?

Because the combiner must merge data with proper weights. Knowing only the average of two groups is not enough to derive the combined average if the group sizes differ.

**Question 7.** When should you choose `Collectors.summarizingInt` or `Collectors.joining` instead of creating a new Collector?

When the built-in API already expresses the business contract accurately and handles empty cases, combining, and finishing appropriately; using standard collectors reduces code and implementation bugs.

**Question 8.** If an original List contains `Sale`, after `.map(Sale::amount)` what type `T` does the Collector receive?

After `map`, the Stream contains `Integer` if `amount()` returns `int` and object `map` is used. Thus, a collector on that Stream has `T=Integer`, not `Sale`. If `mapToInt` is used, you get an `IntStream` with specialized collect APIs, no longer an object `Stream<Integer>` in the same way.

**Takeaway:** In `Collector<T,A,R>`, **T is the input data**, **A is the accumulation state**, and **R is the final result**. Supplier creates A, accumulator adds T to A, combiner merges As, and finisher converts A to R if needed. Designing these three roles properly — along with identity, associativity, and Characteristics — is the foundation for custom collectors that are both easy to understand and correct in sequential or parallel execution.
