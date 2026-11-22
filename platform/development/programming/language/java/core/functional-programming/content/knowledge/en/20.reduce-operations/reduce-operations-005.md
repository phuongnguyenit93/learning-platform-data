# Three-Argument `reduce()`: `identity`, `accumulator`, and `combiner` in Java

## 1. Why Does Three-Argument `reduce` Exist?

In functional programming, **reduction** is the process of combining multiple elements of a data stream into a single result value. Examples include computing a sum, computing the total length of strings, or aggregating order information into a summary record.

With `Stream<T>` in Java, `reduce` has several forms. The three-argument form is especially important when:

- **The source element type `T` differs from the accumulated result type `U`.** For example, each element is a `String` while the result is an `Integer`, or each element is an `OrderLine` while the result is a `Summary`.
- **You need to describe how to merge two separate accumulated results**, especially when the Stream may run in parallel.
- **You want a concrete result even when the Stream is empty**, thanks to the initial value `identity`.

The API signature on `java.util.stream.Stream<T>`:

```java
<U> U reduce(
        U identity,
        java.util.function.BiFunction<U, ? super T, U> accumulator,
        java.util.function.BinaryOperator<U> combiner);
```

Reading the signature in plain words: from a `Stream<T>`, the result is a `U`; `identity` is the neutral value of type `U`; `accumulator` takes the current result (`U`) and a source element (`T`) to produce a new `U` result; `combiner` takes **two `U` results** and combines them into one `U`.

A short example:

```java
int lengthSum = java.util.stream.Stream.of("aa", "bbb", "c")
        .reduce(
                0,                                // identity: Integer
                (sum, text) -> sum + text.length(), // U + T → U
                Integer::sum                      // U + U → U
        );

System.out.println(lengthSum); // 6
```

Here `T = String` and `U = Integer`, so the two-argument form `reduce(identity, accumulator)` (which requires `T` and the result to have the same type in `Stream<T>`) cannot directly replace this example. The three-argument form allows accumulating a type **different** from the source element type.

## 2. What Roles Do the Three Components Play?

### `identity` — the neutral value

`identity` is the initial accumulated state and must be the **identity (neutral) element** of the `combiner` operation: combining with it must not change the result.

For integer addition, the identity is `0`:

```text
0 + x = x
x + 0 = x
```

For multiplication, the identity is `1`:

```text
1 × x = x
x × 1 = x
```

For a summary containing record count, quantity, and revenue, the identity can be `Summary(0, 0, 0)`: when no elements have been processed yet, all three metrics are 0.

`identity` is also the **return value for an empty Stream**:

```java
int value = java.util.stream.Stream.<String>empty()
        .reduce(0, (sum, s) -> sum + s.length(), Integer::sum);

// value = 0
```

In parallel processing, do not think of `identity` as a value added only once at the beginning of the entire Stream. Sub-branches may each start from their own `identity`, and then the branch results are merged by `combiner`. Therefore, choosing a non-neutral `identity` can cause serious errors.

### `accumulator` — folding one element into the existing state

General form:

```text
accumulator: (U state, T element) -> U nextState
```

Example:

```java
(sum, text) -> sum + text.length()
```

The first argument is the accumulated total length (`Integer`); the second argument is the next string (`String`). The return value is a new total (`Integer`).

In order aggregation, `accumulator` can increment the line count, add the quantity, and add the revenue of **one** line into the existing summary.

You should not think of `accumulator` as "only running in sequential mode." It is also used to reduce elements within the branches of parallel processing. When two partial results need to be merged, that responsibility belongs to `combiner`.

### `combiner` — merging two accumulated states

General form:

```text
combiner: (U partialLeft, U partialRight) -> U merged
```

For example, `Integer::sum` adds two separately computed total lengths. For `Summary`, `combiner` adds each summary field.

Conceptual diagram for a Stream with four elements:

```text
                   Stream<T>
               t1  t2  t3  t4
                    │
           ┌────────┴────────┐
           │                 │
      left branch       right branch
     identity + t1       identity + t3
                + t2                + t4
           │                 │
          U1                U2
           └────────┬────────┘
                    ▼
              combiner(U1,U2)
                    │
                    ▼
                 result U
```

This is a **mental model**, not a guarantee that Java always splits a Stream into exactly two branches or calls `combiner` once. How partitioning works, how many times `combiner` is called, and in what order depend on the source, pipeline, and execution strategy. With a sequential Stream, `combiner` is often not called at all; therefore, testing only in sequential mode is **not sufficient** to catch a broken `combiner`.

## 3. How Does Three-Argument `reduce` Differ from the Other Overloads?

| Overload | Result | When to use |
| --- | --- | --- |
| `Optional<T> reduce(BinaryOperator<T> op)` | `Optional<T>` | No `identity` provided; Stream may be empty |
| `T reduce(T identity, BinaryOperator<T> op)` | `T` | Elements and accumulated result have the same type `T` |
| `<U> U reduce(U identity, BiFunction<U, ? super T, U> accumulator, BinaryOperator<U> combiner)` | `U` | Result `U` can differ from source type `T`; need to describe how to merge branch results |

Comparison:

```java
// Same type Integer: two-argument overload.
int sum = java.util.stream.Stream.of(1, 2, 3)
        .reduce(0, Integer::sum);

// Different types: String -> Integer, three-argument overload.
int totalChars = java.util.stream.Stream.of("a", "bb", "ccc")
        .reduce(0, (n, s) -> n + s.length(), Integer::sum);

// Without identity: may return Optional.empty().
java.util.Optional<Integer> max =
        java.util.stream.Stream.<Integer>empty()
                .reduce(Integer::max);
```

These snippets are standalone illustrations and require importing the appropriate types if not written fully qualified. In terms of intent, the total-length example also has a very clear linear expression: `mapToInt(String::length).sum()`. There is no need to use a more complex overload if a built-in operation expresses the business logic directly and is easier to maintain.

## 4. Three Rules for Correct Reduction — Especially with `parallelStream()`

A reduction may be executed under many different groupings. For the result to be **correct and consistent**, the following constraints must be satisfied.

### 4.1. `identity` is neutral with respect to `combiner`

For every valid accumulated result `u`:

```text
combiner(identity, u) = u
combiner(u, identity) = u
```

When merging arithmetic sums with addition, `0` is neutral; `10` is not neutral.

**Wrong:**

```java
int wrong = java.util.stream.Stream.of(1, 2, 3)
        .reduce(10, Integer::sum, Integer::sum);
```

When processed sequentially, this may yield `16` because it starts from `10` and adds `1 + 2 + 3`. However, `10` is **not neutral** for addition, so parallel branches can each introduce `10` into the sum once per branch, producing a different result. There is no single fixed parallel result guaranteed or predictable here. Fix it by using identity `0`.

### 4.2. `combiner` is associative

For `u1`, `u2`, `u3`:

```text
combiner(combiner(u1, u2), u3)
    = combiner(u1, combiner(u2, u3))
```

Integer addition (under Java integer semantics) is associative; subtraction in general is **not**:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

If `combiner` is not associative, changing the grouping can change the result. With floating-point numbers `double`/`float`, be careful: floating-point addition is not bit-exact associative due to rounding, so different merge orders can introduce small discrepancies. When calculating money, consider using the smallest integer unit or `BigDecimal` and defining a rounding policy.

### 4.3. `accumulator` is compatible with `combiner`

This is a very important rule of the three-argument form. For an accumulated result `u` and a source element `t`, the following must hold:

```text
combiner(u, accumulator(identity, t))
    = accumulator(u, t)
```

Interpretation: if you process `t` separately starting from the neutral state and then merge it into `u`, the result must be the same as folding `t` directly into `u`. This allows the Stream to split elements into branches and merge them without changing the meaning of the computation.

Total-length example:

```text
identity = 0
accumulator(u, text) = u + text.length()
combiner(a, b) = a + b

combiner(u, accumulator(0, "abc"))
= u + (0 + 3)
= u + 3
= accumulator(u, "abc")
```

For a multi-field summary, `combiner` must merge **the exact fields that `accumulator` updates**; if `accumulator` increments the line count but `combiner` forgets to add the right branch's line count, sequential execution may still look right while parallel execution is wrong.

Both functions must also be **non-interfering** with the source and satisfy **statelessness** per the Stream contract: do not let the result depend on a shared mutable counter, unintentionally modified data, or side effects that must happen in a specific order.

## 5. Java 17 Example: Aggregating Orders into an Immutable Record

Suppose each source element is an order line:

```text
Line(sku, quantity, unitPrice)
```

We want a `Summary` result consisting of:

- `lines`: number of processed lines.
- `units`: total item quantity.
- `revenue`: revenue = sum of `quantity × unitPrice` (in an agreed integer currency unit).

In this case:

```text
T = Line
U = Summary
identity = Summary(0, 0, 0)

accumulator(Summary, Line) -> new Summary
combiner(Summary, Summary) -> new Summary
```

Choosing an **immutable record** lets each branch work on its own aggregated value without mutating a shared accumulator. Creating a new `Summary` for each element has allocation overhead, but it is clear in intent, state-safe, and easy to test. If the input is very large and performance is critical, consider `collect` with a contract-compliant mutable container or specialized aggregation, rather than arbitrarily turning `reduce` into shared-state mutation.

### Complete program

Create the file `ThreeArgumentReduceDemo.java`:

```java
import java.util.List;
import java.util.Objects;
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;
import java.util.stream.Stream;

public class ThreeArgumentReduceDemo {
    record Line(String sku, int quantity, long unitPrice) {}

    record Summary(long lines, long units, long revenue) {}

    private static final Summary ZERO = new Summary(0, 0, 0);

    private static final BiFunction<Summary, Line, Summary> ACCUMULATE =
            (summary, line) -> new Summary(
                    summary.lines() + 1,
                    summary.units() + line.quantity(),
                    summary.revenue() + (long) line.quantity()
                            * line.unitPrice());

    private static final BinaryOperator<Summary> COMBINE =
            (left, right) -> new Summary(
                    left.lines() + right.lines(),
                    left.units() + right.units(),
                    left.revenue() + right.revenue());

    static Summary summarize(Stream<Line> lines) {
        return lines.reduce(ZERO, ACCUMULATE, COMBINE);
    }

    static void expect(Object expected, Object actual, String name) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    name + ": expected=" + expected
                            + ", actual=" + actual);
        }
    }

    static List<Line> sample() {
        return List.of(
                new Line("A", 2, 100),
                new Line("B", 3, 70),
                new Line("C", 1, 200),
                new Line("D", 4, 25));
    }

    static void runTests() {
        List<Line> lines = sample();
        Summary expected = new Summary(4, 10, 710);

        expect(expected, summarize(lines.stream()),
                "sequential summary");
        expect(expected, summarize(lines.parallelStream()),
                "parallel summary");
        expect(ZERO, summarize(Stream.<Line>empty()),
                "empty stream");
        expect(new Summary(1, 2, 200),
                summarize(lines.stream().limit(1)),
                "single row");

        // identity must be neutral with respect to combiner.
        expect(expected, COMBINE.apply(ZERO, expected),
                "left identity");
        expect(expected, COMBINE.apply(expected, ZERO),
                "right identity");

        // Compatibility between accumulator and combiner.
        Line one = lines.get(0);
        Summary partial = new Summary(5, 9, 500);
        expect(ACCUMULATE.apply(partial, one),
                COMBINE.apply(partial,
                        ACCUMULATE.apply(ZERO, one)),
                "accumulator/combiner compatibility");

        int totalLength = Stream.of("aa", "bbb", "c")
                .reduce(0,
                        (sum, word) -> sum + word.length(),
                        Integer::sum);
        expect(6, totalLength, "different source/result types");

        int squareSum = Stream.of(1, 2, 3, 4)
                .reduce(0, (sum, n) -> sum + n * n, Integer::sum);
        expect(30, squareSum, "squares");
    }

    public static void main(String[] args) {
        runTests();

        List<Line> lines = sample();
        Summary sequential = summarize(lines.stream());
        Summary parallel = summarize(lines.parallelStream());
        Summary empty = summarize(Stream.<Line>empty());

        int totalLength = Stream.of("aa", "bbb", "c")
                .reduce(0,
                        (sum, word) -> sum + word.length(),
                        Integer::sum);
        int squareSum = Stream.of(1, 2, 3, 4)
                .reduce(0, (sum, n) -> sum + n * n, Integer::sum);

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("empty=" + empty);
        System.out.println("lengths=" + totalLength);
        System.out.println("squares=" + squareSum);
        System.out.println("tests=PASS");
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac ThreeArgumentReduceDemo.java
java ThreeArgumentReduceDemo
```

Expected stdout:

```text
sequential=Summary[lines=4, units=10, revenue=710]
parallel=Summary[lines=4, units=10, revenue=710]
empty=Summary[lines=0, units=0, revenue=0]
lengths=6
squares=30
tests=PASS
```

### Verifying the calculation

Sample lines:

| SKU | Quantity | Unit price | Revenue |
| --- | ---: | ---: | ---: |
| A | 2 | 100 | 200 |
| B | 3 | 70 | 210 |
| C | 1 | 200 | 200 |
| D | 4 | 25 | 100 |
| **Total** | **10** | | **710** |

Since there are four lines, `lines=4`. Both `ACCUMULATE` and `COMBINE` return a **new record**, without overwriting the `Summary` object passed in. The total summary is formed with field-by-field addition, making it suitable for independent branches to produce partial results and then merge them.

The constant `ZERO = new Summary(0, 0, 0)` is a reusable initial state because it is immutable. By contrast, using the same mutable `ArrayList` or `StringBuilder` as `identity` will easily corrupt data, especially when branches run in parallel.

The `runTests()` method checks sequential, parallel, empty Stream, single-row, both sides of identity, accumulator/combiner compatibility, and different source-type examples. The tests explicitly throw `AssertionError`, so the JVM flag `-ea` is **not** needed.

## 6. Why Does Running in Parallel Still Produce the Same Result?

Following the mathematical model, consider the four sample lines split into two groups:

```text
Group 1: A, B
  Summary(lines=2, units=5, revenue=410)

Group 2: C, D
  Summary(lines=2, units=5, revenue=300)

Combiner:
  Summary(2+2, 5+5, 410+300)
= Summary(4, 10, 710)
```

If Java splits them into different groups, `COMBINE` remains valid because it adds independent sums and `ZERO` is neutral. The grouping order does not affect the result of adding these integers (as long as overflow does not occur).

**Note:** this is a model for reasoning, not a prediction of how a specific implementation will split and merge. Do not print logs inside `combiner` to deduce for certain how `parallelStream` behaves across all JVMs and data sizes.

A Stream source having an encounter order does not force three-argument reduction to traverse on a single thread or maintain an observable call order for `accumulator`. The `ACCUMULATE`/`COMBINE` logic must be designed so that the result conforms to the contract; the summary additions here do not need to rely on order.

## 7. Anti-Patterns to Avoid

### Mistake 1 — non-neutral `identity`

```java
int wrong = Stream.of(1, 2, 3)
        .reduce(100, Integer::sum, Integer::sum);
```

`100` gets counted as part of the result, and parallel processing can introduce `identity` into separate branches. If the requirement is the sum of elements, you must choose `0`, not `100`. If you truly need to add a fixed fee of 100 only **once**, compute the sum with identity `0` and add 100 **after `reduce`**.

### Mistake 2 — `accumulator` and `combiner` do not share the same meaning

```java
// Semantically wrong when combiner forgets to add the right-hand state.
int count = Stream.of("a", "bb", "ccc")
        .reduce(0,
                (n, s) -> n + 1,
                (left, right) -> left);
```

Sequential execution may return `3`; when elements are reduced across multiple branches, `combiner` can discard one branch's result. The compatibility condition in section 4 is not satisfied. Fix it with `Integer::sum`.

### Mistake 3 — using a non-associative operation

```java
int value = Stream.of(1, 2, 3)
        .reduce(0,
                (left, right) -> left - right,
                (left, right) -> left - right);
```

Subtraction is not associative; the result depends on grouping and merge order. Moreover, `0` is not a two-sided identity for subtraction (`0 - x` differs from `x`). This example **violates the reduction contract**, even though the program compiles.

### Mistake 4 — mutating a mutable object inside `accumulator`

```java
// Counterexample: DO NOT use reduce like this.
java.util.List<String> wrong = Stream.of("a", "b", "c")
        .reduce(
                new java.util.ArrayList<String>(),
                (list, item) -> {
                    list.add(item); // Mutation on the accumulated state.
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
```

This is problematic code: the same mutable `identity` object can be accessed by multiple branches; shared state, interactions between `accumulator` and `combiner`, and associativity requirements become dangerous. Do not use three-argument `reduce` as a way to append data into a single list via side effects.

**The right solution for mutable accumulation:**

```java
java.util.List<String> values = Stream.of("a", "b", "c")
        .collect(
                java.util.ArrayList::new,
                java.util.ArrayList::add,
                java.util.ArrayList::addAll);
```

`collect(supplier, accumulator, combiner)` is designed for **mutable reduction**: `supplier` creates independent containers as needed; `accumulator` updates a container; `combiner` merges containers. For a simple output `List`, you can use `stream.toList()` if an unmodifiable list from Java 16 onward is acceptable. These approaches should not be confused with `reduce(identity, ...)`.

### Mistake 5 — relying on side effects to verify invocation count

```java
// Do not write logic that relies on a shared counter in accumulator.
java.util.concurrent.atomic.AtomicInteger calls =
        new java.util.concurrent.atomic.AtomicInteger();

int result = Stream.of(1, 2, 3)
        .reduce(0,
                (sum, value) -> {
                    calls.incrementAndGet();
                    return sum + value;
                },
                Integer::sum);
```

In a small test, a counter might record how many times `accumulator` was called, but using this result as a business contract is misguided. A Stream may split work, combine in various ways, or optimize other steps in the pipeline. You should test the **final aggregated value**, without depending on logs, threads, or internal call order.

### Mistake 6 — ignoring overflow and precision

```java
int total = Stream.of(Integer.MAX_VALUE, 1)
        .reduce(0, Integer::sum, Integer::sum);
```

The `int` result will overflow under Java integer semantics. This is not a bug in the `reduce` API, but a risk when choosing the accumulation type and operation. For large sums, consider accumulating with `long`, `BigInteger`, or `BigDecimal` according to business domain requirements. Choose a sufficiently wide type **before** adding; casting to `long` after `int` has already overflowed does not recover the correct value.

Example:

```java
long safeTotal = Stream.of(Integer.MAX_VALUE, 1)
        .reduce(0L,
                (sum, n) -> sum + n.longValue(),
                Long::sum);

// 2147483648
```

`0L` ensures `U = Long`; do not perform `int` addition before widening to `long`. Even so, `long` also has limits; check for overflow when data may exceed its range.

## 8. `reduce` or `collect`?

Both `reduce` and `collect` are terminal operations, but they fit different kinds of reduction.

| Criterion | `reduce(identity, accumulator, combiner)` | `collect(supplier, accumulator, combiner)` |
| --- | --- | --- |
| Result state | Suited for immutable values | Suited for mutable containers |
| Single-element step | `BiFunction<U,T,U>` **returns** a new `U` | `BiConsumer<R,T>` **updates** container `R` |
| Merging two partial results | `BinaryOperator<U>` **returns** `U` | `BiConsumer<R,R>` **merges mutable containers** |
| Initialization | One `identity` value `U` | `Supplier<R>` creates containers |
| Examples | Immutable summary, total string length | `ArrayList`, `HashMap`, grouping records |
| Parallel execution | Needs neutral identity and valid associative operations | Needs supplier/accumulator/combiner to obey the collector contract and be safe under concurrent use |

For quantity/revenue aggregation problems, three-argument `reduce` is a good tool to **explain the transformation from `Line` to `Summary`**. However, for some common statistics, the JDK provides shorter solutions:

```java
long units = lines.stream()
        .mapToLong(Line::quantity)
        .sum();
```

In the snippet above, `lines` is a `List<Line>` and `Line` is the illustrative record in the complete program. If you only need total quantity, `mapToLong(...).sum()` is clearer than building a multi-field `Summary`.

For grouping by key, `Collectors.groupingBy(...)` or an appropriate collector is usually easier to use than a `reduce` with a mutable `Map` structure, provided it meets thread-safety needs and actual ordering characteristics.

## 9. Testing the Aggregation Contract

A test suite for three-argument `reduce` should verify both **values** and **mathematical rules**:

| Case | What to verify |
| --- | --- |
| Empty Stream | Result equals `identity`, not an unexpected `null` |
| Single element | `accumulator(identity, t)` gives the right result |
| Multiple elements | Aggregates all fields accurately without dropping data |
| Two-sided identity | Both `combiner(identity,u)` and `combiner(u,identity)` equal `u` |
| Associative combiner | Merging states under different groupings yields the same result |
| Accumulator/combiner compatibility | Merging a single element into `u` equals folding the element directly |
| Sequential vs. parallel | Results match when the operation satisfies the laws and numeric bounds |
| Overflow, null, invalid data | Explicit handling policy per business domain |
| Mutable state | No unsafe shared state or unwanted side effects |

With `Summary`, you can also test the associativity of `combiner`:

```java
// Illustrative snippet inside class ThreeArgumentReduceDemo.
Summary a = new Summary(1, 2, 200);
Summary b = new Summary(1, 3, 210);
Summary c = new Summary(2, 5, 300);

Summary leftGrouped = COMBINE.apply(COMBINE.apply(a, b), c);
Summary rightGrouped = COMBINE.apply(a, COMBINE.apply(b, c));

expect(leftGrouped, rightGrouped, "associativity");
```

This kind of test helps isolate bugs in `combiner` before trying `parallelStream()`. For large datasets, tests should not compare only `count()` or a single field; they must check **all fields** produced by `accumulator`.

## 10. Subtle Notes on Types, Ordering, and Performance

**Type `U` differing from `T` does not automatically convert data.** If `T = OrderLine` and `U = Summary`, `accumulator` itself must translate line data into `Summary`. Generics only express the type contract; they do not automatically know how to compute revenue, quantity, or application state.

**Do not confuse `combiner` with a map step.** `combiner` takes **two `U`s**, not a `U` and a `T`. If `combiner` only knows how to handle a `T` element, the program has no valid way to merge two separately accumulated results.

**Do not assume `combiner` is only used in parallel Streams.** In the programming model, `combiner` is a required part of three-argument reduction. Even though a specific sequential pipeline might not invoke it, the method must be correct to satisfy the contract and in case execution changes.

**Do not allow modifying the source while reduction is running.** Lambdas should be non-interfering: do not add/remove elements of the traversed source, especially an `ArrayList`, inside `accumulator`. Doing so can corrupt results or throw `ConcurrentModificationException` and is not safe for parallel Streams.

**Immutable values are clear, but they have a cost.** A new `Summary` record is created on each accumulation and merge. With large datasets, allocation overhead can be significant; measure with an appropriate benchmark and choose `collect` or specialized aggregation if performance is genuinely required. Do not use `parallel()` as an excuse to ignore associativity or thread-safety constraints.

**If ordering is part of the result**, such as concatenating strings without reversing order, use an associative operation and a source with an appropriate encounter order, or a collector that guarantees proper handling. Do not rely on the lambda invocation order observed via `System.out.println` to determine result contents.

**Floating-point precision** differs from integer precision. When summing `double`, changing grouping order can alter rounding differences. For currency, rounding policy, units, and numeric types must be clearly defined; choosing a `reduce` overload does not solve that problem on its own.

## 11. Practice Exercises

1. Given `Stream.of("Java", "Stream", "API")`. Use `reduce(0, accumulator, combiner)` to compute the total length; predict the result `13`. Write a test comparing `stream()` and `parallelStream()`.
2. Write a record `Stats(long items, long chars)` and a method using three-argument `reduce` to count the number of strings and total length in a single pass. Build `identity`, `accumulator`, and `combiner`; prove neutrality and associativity.
3. In `ThreeArgumentReduceDemo`, add a line `new Line("E", 5, 10)`. Update the expected summary, and test both sequential and parallel execution. Revenue increases by `50`, quantity increases by `5`, and line count increases by `1`.
4. Intentionally change `combiner` to `new Summary(left.lines(), left.units() + right.units(), left.revenue() + right.revenue())`. Explain why the sequential result can still be right while parallel is wrong, and write a test for the bug.
5. Try `identity` as `new Summary(1,0,0)` and explain why the result can be wrong when the Stream is split; fix it back to the neutral `identity`.
6. Compare `reduce` returning an immutable `Summary` with `collect` into an `ArrayList`; distinguish between a `BiFunction` returning a new state and a `BiConsumer` mutating a container.
7. Sum very large numbers using `Stream<Integer>.reduce(0L, (sum, n) -> sum + n.longValue(), Long::sum)` and verify the result with `Integer.MAX_VALUE` and `1`.

## 12. Summary

`Stream.reduce(identity, accumulator, combiner)` is **three-argument reduction** capable of turning a `Stream<T>` into a `U` result of a different type from the source elements:

- `identity` is the neutral value of the accumulated state and the result for an empty Stream.
- `accumulator` takes a `U` state and a `T` element, returning a `U` state.
- `combiner` merges **two `U` states** — especially critical when the Stream can be split for parallel processing.

A correct reduction requires **a neutral `identity`, an associative `combiner`, and an `accumulator` compatible with `combiner`**, along with functions that have no source-interfering side effects. Prefer immutable state for `reduce`; use `collect` when the goal is accumulating into a mutable container. Understanding these contracts matters more than just memorizing syntax, because they determine whether the result remains correct when the source is empty, when groupings differ, or when switching from sequential to parallel execution.
