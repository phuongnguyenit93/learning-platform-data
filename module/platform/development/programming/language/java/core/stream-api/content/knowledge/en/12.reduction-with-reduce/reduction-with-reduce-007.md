# Why Should You Not Use a Mutable Container as the identity of `reduce`?

In the **Java Stream API**, `reduce` is used to combine multiple elements into **a single value** according to a combining operation. For instance, computing a sum, finding a maximum value, or merging immutable results. When wanting to gather elements into an `ArrayList`, `HashMap`, or `StringBuilder`, many developers try passing an empty container as the `identity` parameter and mutating it directly inside the accumulator.

That is a major trap in the **Reduction with reduce** chapter: `identity` is **an initial value participating in the mathematical contract of reduction**, not a factory called to create a new container. If the accumulator mutates that object, the pipeline may accidentally produce the expected result sequentially, yet create duplicate elements, lose data, or suffer contention when switched to parallel execution.

The standard solution is: **`reduce` is for combining immutable values; `collect` is for accumulating into mutable containers**. You should understand the reason from the API contract rather than merely swapping method names.

## 1. Distinguishing a reduced value from an accumulation container

A Stream pipeline can consist of a source, lazy intermediate operations (`filter`, `map`, ...), and a terminal operation (`reduce`, `collect`, ...). The terminal operation triggers processing; afterward, the same `Stream` object cannot be reused.

| Criterion | `reduce` | `collect` |
| --- | --- | --- |
| Primary purpose | Combines elements or partial results into a single **value**. | Accumulates elements into a **mutable container**. |
| Initialization | Takes `identity` as a **value** of the result type. | Takes a `supplier` that **creates a new container** when needed. |
| Accumulation operation | Semantically returns a new accumulated result. | Typically mutates the accumulation segment's container and returns `void`. |
| Merging branches | `BinaryOperator` returning a combined value. | Three-parameter `Stream.collect` uses `BiConsumer`; `Collector.of` uses `BinaryOperator` returning the merged container. |
| Typical examples | Sums, products, min/max selection, `BigDecimal::add`. | `List`, `Set`, `Map`, `groupingBy`, custom collectors. |

**Mutable** means the internal state of an object can change after creation. `ArrayList.add`, `HashMap.put`, and `StringBuilder.append` are operations that mutate the object. In contrast, `Integer`, `String`, and `BigDecimal` are immutable types: operations typically create a new result value.

## 2. Three overloads of `reduce` and the meaning of `identity`

Conceptual signatures on `Stream<T>`:

```java
Optional<T> reduce(BinaryOperator<T> accumulator);

T reduce(T identity, BinaryOperator<T> accumulator);

<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
);
```

- **Without identity:** `reduce(BinaryOperator<T>)` returns `Optional<T>`, because an empty stream has no elements to return.
- **With identity and same type:** `reduce(T, BinaryOperator<T>)` returns `T`; `identity` is the result when the source is empty and serves as the identity element of the combining operation.
- **With identity and different result type:** `reduce(U, BiFunction<U,T,U>, BinaryOperator<U>)` allows elements of type `T` to be accumulated into a value of type `U`. The combiner merges **two** `U` values.

Valid example with immutable values:

```java
import java.util.stream.Stream;

int sum = Stream.of(2, 4, 6).reduce(0, Integer::sum);
int emptySum = Stream.<Integer>empty().reduce(0, Integer::sum);

System.out.println(sum);      // 12
System.out.println(emptySum); // 0
```

`0` is the identity element of addition: `0 + x = x + 0 = x`. `Integer::sum` does not mutate any `Integer`; it returns a new `int` value. Data can be split into groups to compute partial sums and then combined regardless of split boundaries, provided the sum does not exceed the numeric type's range.

### How does `identity` differ from `Supplier`?

```text
reduce(identity, accumulator, combiner)
       |
       +-- identity is a VALUE passed into the reduce call

collect(supplier, accumulator, combiner)
        |
        +-- supplier.get() can be called multiple times
            to create SEPARATE CONTAINERS for accumulation segments
```

When `identity` is the number 0 or an empty string, sharing that value causes no issue because we do not mutate it. However, when `identity` is **a reference to a mutable list**, parallel branches can receive **that exact same reference** as their starting point. There is no mechanism that automatically copies the list whenever a branch starts.

## 3. Wrong example: using `ArrayList` as identity and calling `add`

The following code **compiles but violates the reduction contract**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

// WRONG EXAMPLE: do not use in applications.
List<String> result = Stream.of("A", "B", "C")
    .reduce(
        new ArrayList<String>(),
        (acc, item) -> {
            acc.add(item);  // Mutates the identity itself or the partial result
            return acc;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
```

When run sequentially, this code may print `[A, B, C]`. That output easily creates the impression that the approach is valid. Yet both the accumulator and the combiner **mutate the input object** and return it back.

When run in parallel, an execution may split the source into `[A]`, `[B]`, `[C]` and start accumulating from the exact same list object passed as `identity`. Possible outcomes:

1. Two branches call `add` concurrently on a non-thread-safe `ArrayList`, causing contention and unreliable results.
2. When the combiner receives two results pointing to **that very same list**, `left.addAll(right)` can copy the list into itself, creating duplicate entries.
3. On some runs, the result may look right; on others, the order, count, or contents may be wrong. No guarantee can be relied upon.

You do not need to run a test to consider this a bug: the code **already violates the contract** even if a small example happens to produce the expected output.

### The same mistake with `StringBuilder`

```java
import java.util.stream.Stream;

// WRONG EXAMPLE: StringBuilder::append mutates the left-hand object.
StringBuilder text = Stream.of("a", "b", "c")
    .parallel()
    .reduce(
        new StringBuilder(),
        StringBuilder::append,
        StringBuilder::append
    );
```

`StringBuilder` is great as a mutable buffer **inside a collector**, but unsuitable for a `reduce` that mutates the identity directly as above. Adding manual synchronization or switching to `StringBuffer` does not fix the identity and combiner contract: two intermediate result variables can still refer to the same object and be merged repeatedly.

## 4. Why it is wrong: the laws of reduction

For `reduce` to work properly with how Streams are permitted to split and merge, the functions must satisfy conditions on **identity, associativity, and accumulator/combiner compatibility**.

Let:

- `e`: identity of type `U`;
- `A(u, t)`: accumulator folding source element `t` of type `T` into partial result `u` of type `U`;
- `C(u1, u2)`: combiner merging two partial results of type `U`.

In terms of values, the following must hold:

| Condition | Meaning |
| --- | --- |
| `C(e, u) = u` | Identity is a left identity element. |
| `C(u, e) = u` | Identity is a right identity element. |
| `C(C(a, b), c) = C(a, C(b, c))` | Combiner is *associative*. |
| `C(u, A(e, t)) = A(u, t)` | Accumulator is compatible with combiner. |

Equality here means **equivalence in result value**, not necessarily that two objects share the same memory address. For `reduce`, the behavioral functions must also be **non-interfering** with the source and **stateless** (not relying on shared mutable state) per Stream API requirements.

Example summing string lengths into an `int`:

```java
import java.util.stream.Stream;

int totalLength = Stream.of("Java", "Stream", "API")
    .parallel()
    .reduce(
        0,
        (length, word) -> length + word.length(),
        Integer::sum
    );

System.out.println(totalLength); // 13
```

Here, `T = String`, `U = Integer`, `e = 0`. The accumulator takes a string's length and adds it to the total; the combiner adds two totals. For the values in the example, every split and merge yields 13.

### How does a mutable container break the contract?

If `e` is an `ArrayList` and `A(e, t)` calls `e.add(t)`, **`e` itself is no longer empty after the call**. The identity has changed state, so it is no longer a stable identity element for merging partial results. The fact that the combiner can be invoked on two references pointing to the same list further destroys the independence of merging.

The core issue is not merely that “`ArrayList` is not thread-safe”. Even in a sequential pipeline, mutating the caller-supplied identity makes the result depend on the mutation history of that object; if reused with the same mutated identity, accumulated results can carry over data from the previous run.

Example:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> seed = new ArrayList<>();

// WRONG EXAMPLE: after the first reduction, seed has been mutated.
List<String> one = Stream.of("A").reduce(
    seed,
    (acc, item) -> { acc.add(item); return acc; },
    (left, right) -> { left.addAll(right); return left; }
);

System.out.println(seed); // [A] in this sequential execution
// Reusing seed in another reduce will carry over old data.
```

Do not patch the bug with `synchronizedList`, `CopyOnWriteArrayList`, or `AtomicReference` while keeping the same `reduce` structure. Synchronization may reduce contention on shared state, but it **does not replace the identity and combining rules** that reduction requires.

## 5. Right approach: `collect` with a supplier creating independent containers

If the goal is collecting elements into a mutable list, use `collect`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> result = Stream.of("A", "B", "C")
    .parallel()
    .collect(
        ArrayList::new,             // Supplier: creates a new list
        List::add,                  // BiConsumer: adds an element
        List::addAll                // BiConsumer: merges lists
    );

System.out.println(result); // [A, B, C]
```

In the `Stream.collect(supplier, accumulator, combiner)` overload:

1. **Supplier** has type `Supplier<R>`, called to create a new container. When the pipeline is split into parts, containers can be initialized independently.
2. **Accumulator** has type `BiConsumer<R, T>`, updating the segment's container with a source element.
3. **Combiner** has type `BiConsumer<R, R>`, transferring data from one container into another when merging results. No return value is needed.

`List::add` and `List::addAll` have `boolean` return values, which are ignored in a `BiConsumer` context. The result of this collector preserves the encounter order of an ordered source under the appropriate accumulation contract; do not apply that assumption to a custom collector declaring `UNORDERED` or to an unordered source.

### Shorter approach with `Collectors`

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

List<String> items = Stream.of("A", "B", "C")
    .parallel()
    .collect(Collectors.toList());

ArrayList<String> editable = Stream.of("A", "B", "C")
    .collect(Collectors.toCollection(ArrayList::new));
```

`Collectors.toList()` **does not guarantee** the implementation type or mutability of the resulting list. When you need a guaranteed mutable `ArrayList`, use `toCollection(ArrayList::new)`. Since Java 16, `Stream.toList()` provides an unmodifiable list; do not choose it if subsequent code must `add` or `remove`.

The core difference: in `collect`, **mutation is a designed part of the contract**, with supplier and combiner coordinating so accumulation remains correct even when the stream is split.

## 6. The `Collector.of` case: combiner returns the container

When building a **custom collector**, the `Collector.of` signature differs from the `Stream.collect` overload above. The accumulator is still a `BiConsumer`, but the combiner is a `BinaryOperator<A>` and must **return** the merged container:

```java
import java.util.ArrayList;
import java.util.stream.Collector;
import java.util.stream.Stream;

Collector<String, ArrayList<String>, ArrayList<String>> toArrayList =
    Collector.of(
        ArrayList::new,             // Supplier<ArrayList<String>>
        ArrayList::add,             // BiConsumer<ArrayList<String>, String>
        (left, right) -> {
            left.addAll(right);
            return left;            // BinaryOperator<ArrayList<String>>
        }
    );

ArrayList<String> values = Stream.of("A", "B", "C")
    .parallel()
    .collect(toArrayList);

System.out.println(values); // [A, B, C]
```

Here `left.addAll(right)` **is allowed** because the collector uses **independent accumulation containers** created by the supplier. The combiner merges partial containers, and `reduce`'s identity plays no role in this process.

A user-written collector must also satisfy the **collector's** identity and associativity contracts. The `supplier` must never return **the same shared list** across calls:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> shared = new ArrayList<>();

// WRONG EXAMPLE: every supplier call returns the exact same container.
List<String> broken = Stream.of("A", "B", "C").parallel()
    .collect(
        () -> shared,
        List::add,
        List::addAll
    );
```

Renaming `reduce` to `collect` **is not enough** if a shared container is still used. The supplier in a collector must satisfy the requirement of creating an appropriate accumulation container for independent calls.

## 7. When is `reduce` still the right choice?

`reduce` fits well when result values are **combined without mutating the input objects**.

### Summing with `BigDecimal`

```java
import java.math.BigDecimal;
import java.util.stream.Stream;

BigDecimal amount = Stream.of(
        new BigDecimal("12.30"),
        new BigDecimal("4.70"),
        new BigDecimal("1.25")
    )
    .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(amount); // 18.25
```

`BigDecimal.add` returns a result `BigDecimal` without mutating either operand. With `BigDecimal.ZERO` as the identity, having the accumulation rule and combiner use the same addition has clear semantics. For problems involving a `MathContext` and specific rounding rules, numerical associativity after each rounding step still needs to be evaluated when running in parallel.

### Immutable string concatenation

```java
import java.util.stream.Stream;

String joined = Stream.of("Java", "-", "Stream")
    .reduce("", String::concat);

System.out.println(joined); // Java-Stream
```

`String` is immutable and the empty string is the identity of concatenation. However, `reduce` with `String::concat` can create many intermediate strings, especially on large data. To join many strings efficiently, use `Collectors.joining`, which legitimately uses a mutable accumulator inside the collector:

```java
import java.util.stream.Collectors;
import java.util.stream.Stream;

String joined = Stream.of("Java", "Stream", "API")
    .collect(Collectors.joining(", "));

System.out.println(joined); // Java, Stream, API
```

### What if the result type is mutable, yet the accumulator does not mutate it?

In theory, an object of a **mutable type** can still be used in a reduction **if every step treats it as an immutable value**: never mutating the identity or intermediate objects, creating a new object on each combine step, and upholding all laws in section 4. For example:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

List<String> values = Stream.of("A", "B", "C").reduce(
    new ArrayList<String>(),
    (existing, item) -> {
        List<String> copy = new ArrayList<>(existing);
        copy.add(item);
        return copy;
    },
    (left, right) -> {
        List<String> copy = new ArrayList<>(left);
        copy.addAll(right);
        return copy;
    }
);

System.out.println(values); // [A, B, C]
```

This snippet **does not mutate** the input lists inside the accumulator and combiner, so it avoids the shared-identity trap. However, every added element copies the existing contents: allocation and copying costs can grow sharply with sequence length. Therefore, **`collect` remains the more natural and efficient choice when the goal is building a mutable list**.

## 8. Parallelism exposes the bug, but the bug existed beforehand

In a parallel pipeline, the Stream API is permitted to split the source and merge results in a tree:

```text
Data source:          A   B   C   D
                       \ /     \ /
Independent branches:  R1       R2
                        \      /
Final result:          combine(R1, R2)
```

There is no guarantee that there will be exactly two branches, or that branches run in a fixed order. Hence, the reduction must be valid under arbitrary splitting and merging. When the accumulator mutates a shared identity, `R1` and `R2` can actually be **the very same object**, destroying the required independence.

Conversely, `collect` creates containers via a supplier, so each accumulation segment can keep its **own** state and then merge in a controlled way. That is why the API separates `reduce` and `collect`.

Other limitations to keep in mind:

- `parallel()` does not automatically guarantee faster execution. Effectiveness depends on the source's `Spliterator`, data volume, combining cost, and system load.
- Intermediate operations `map` and `filter` are lazy; do not use their side effects to record every element, as optimizations or short-circuiting may occur.
- Floating-point `double` does not have strict associativity due to rounding; parallel addition can differ in the last few bits from sequential execution.
- A terminal operation consumes the stream. To run both `reduce` and `collect` on the same collection source for comparison, create **two fresh streams**.
- With I/O sources such as `Files.lines`, use `try-with-resources`; terminal operations do not automatically close resources.

## 9. Table for choosing an approach by goal

| Goal | Recommended approach | Reason |
| --- | --- | --- |
| Sum `int`, `long` values | `IntStream.sum()`, `LongStream.sum()`, or an appropriate `reduce` | Produces a single numeric result; no mutable container needed. |
| Sum `BigDecimal` | `reduce(BigDecimal.ZERO, BigDecimal::add)` | `BigDecimal` is an immutable value. |
| Find minimum/maximum element | `min`/`max` or `reduce(BinaryOperator.minBy/maxBy(...))` | Selection between values. |
| Collect elements into a `List` | `collect(Collectors.toList())` | Collector manages accumulation and merging. |
| Need a mutable `ArrayList` | `collect(Collectors.toCollection(ArrayList::new))` | Explicitly specifies the factory and container type. |
| Collect elements into a `Set` | `collect(Collectors.toSet())` | Performs deduplication under set semantics. |
| Group elements by key | `collect(Collectors.groupingBy(...))` | Accumulates multiple containers per group. |
| Join many strings | `collect(Collectors.joining(...))` | Avoids repeated immutable string concatenation. |
| Create a custom collector | `Collector.of(supplier, accumulator, combiner, ...)` | Controls new container creation and result merging. |

## 10. Signs that a `reduce` is wrong

When reviewing a pipeline with `reduce`, examine patterns such as:

1. **Identity is `new ArrayList<>()`, `new HashMap<>()`, `new StringBuilder()`** and the accumulator calls `add`, `put`, or `append` on it.
2. Accumulator **returns the very object it just mutated**, instead of representing a value-based combining operation.
3. Combiner calls `left.addAll(right)`/`left.putAll(right)` while `left` and `right` could both refer to the identity.
4. A mutable object declared outside the pipeline is written to by the lambda, such as a shared list or counter.
5. Sequential execution produces the right output, but adding `parallel()` causes duplicate elements, fluctuating counts, or exceptions.
6. Someone suggests adding `synchronized` just to keep the broken reduction structure intact.

These signs do not mean every use of a mutable type in `reduce` is forbidden. You must evaluate **state-mutation behavior** and the laws of reduction; if you need to pour data into a container, `collect`'s design is more suitable.

## 11. Self-check exercises

**Exercise 1 — Spot the bug.** Given:

```java
List<Integer> result = numbers.parallelStream().reduce(
    new ArrayList<Integer>(),
    (list, n) -> { list.add(n); return list; },
    (left, right) -> { left.addAll(right); return left; }
);
```

Point out where the accumulator and combiner mutate state, why the identity can be shared, and why merely synchronizing `list.add` is insufficient. Rewrite it using `collect(ArrayList::new, List::add, List::addAll)`.

**Exercise 2 — Pick the right overload.** Compute the total length of `Stream.of("a", "bb", "ccc")` using `reduce(0, (sum, s) -> sum + s.length(), Integer::sum)`. Explain why the accumulator is `BiFunction<Integer, String, Integer>` and the combiner is `BinaryOperator<Integer>`. Predict the result as **6**.

**Exercise 3 — Choose a collector.** Collect product names from a stream into a list guaranteed to be mutable. Why is `Collectors.toCollection(ArrayList::new)` more suitable than mutating an `ArrayList` inside `reduce`? Distinguish it from `Stream.toList()` (Java 16+).

**Exercise 4 — Cost.** Compare a reduction returning a fresh copy of a `List` after each element against `collect` accumulating into separate lists and merging. Which approach allocates more objects when the element count is very large? When should an immutable result value such as `BigDecimal` still be used with `reduce`?

**Key takeaway:** `reduce` takes **an identity value** and requires combining operations to obey mathematical laws, even when the Stream is split and merged in parallel. Directly mutating an `ArrayList`, `HashMap`, or `StringBuilder` used as the identity breaks independence and can produce wrong results. When you want to build a mutable container, use `collect` with a supplier creating distinct containers and a valid combiner.
