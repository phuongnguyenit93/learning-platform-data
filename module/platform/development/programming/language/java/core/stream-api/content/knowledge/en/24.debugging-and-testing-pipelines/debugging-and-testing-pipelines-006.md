# Testing Associativity of `reduce` and `Collector`

## 1. Why Does a Pipeline Pass Sequentially Yet Fail in Parallel?

In **JAVA_STREAM_API**, `filter`, `map`, `reduce`, and `collect` pipelines express data processing declaratively. A pipeline can switch from `stream()` to `parallelStream()` to split work across multiple branches. However, if the aggregation function violates **associativity** or **identity** laws, the result can depend on how the data was partitioned.

~~~text
Source: [10, 3, 2]
Merge op: subtraction

Grouping 1: (10 - 3) - 2 = 5
Grouping 2: 10 - (3 - 2) = 9

Same data, different results because subtraction is not associative.
~~~

Source splitting in the Stream API is not guaranteed to follow any fixed schedule. If a result is correct only when the accumulator runs in one particular execution order, the algorithm can break when element count, JDK version, `Spliterator` splitting behavior, or parallelism changes.

This lesson belongs to the **Debugging and Testing Pipelines** chapter and teaches you how to:

- Verify `identity`, `associativity`, and `accumulator–combiner` compatibility laws for `reduce`.
- Verify `supplier`, `accumulator`, `combiner`, `finisher`, and `Characteristics` of a `Collector`.
- Simulate different source splits and merge trees rather than just calling `parallel()` once.
- Catch counterexamples involving subtraction, flawed averaging, shared mutable state, result ordering, and floating-point numbers.
- Write standalone tests in Java 17+ without external libraries, while understanding the limits of randomized testing and sequential-vs.-parallel comparisons.

**Context:** Examples focus on the Java Stream API, where aggregation typically lives in a terminal `reduce` or `collect`. Ordering, performance, state, and `Spliterator` behavior directly impact whether a pipeline can be verified safe for parallel execution.

## 2. Source Splitting and Merging Model

~~~text
Source [1, 2, 3, 4, 5, 6]
                  │
              Spliterator
              /         \
        [1, 2, 3]     [4, 5, 6]
            │             │
        local reduce  local reduce
            │             │
            6             15
             \           /
                combiner
                    │
                    21
~~~

This is strictly a conceptual diagram. Stream does not promise splitting strictly in half or assigning one thread per chunk. A terminal reduction may combine partial results according to **different parenthesizations**.

**Associativity** allows regrouping parentheses without changing the result:

~~~text
op(op(a, b), c) = op(a, op(b, c))
~~~

**Commutativity** allows swapping operand order:

~~~text
op(a, b) = op(b, a)
~~~

These are two distinct properties. String concatenation is associative, yet not commutative:

~~~text
("A" + "B") + "C" = "A" + ("B" + "C") = "ABC"
"A" + "B" != "B" + "A"
~~~

On an **ordered** source, a collector/reduction can still be correct even with a non-commutative operator if encounter order is preserved. On an `UNORDERED` collector, never rely on input order to decide which record wins when keys collide.

### Thread safety alone does not prove correctness

A data-race-free function can still be **mathematically wrong** if it is not associative. Conversely, associative addition performed against a shared mutable variable inside a callback can lose updates. Therefore, tests must verify **both the combination laws and state design**.

## 3. `identity` and `associativity` Laws for `reduce`

Two-argument overload:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator)
~~~

The `identity` value must be a valid identity element, and `accumulator` must be associative. With `e` as identity and `op` as the operator, useful checks are:

~~~text
op(e, x) = x
op(x, e) = x

op(op(a, b), c) = op(a, op(b, c))
~~~

The `Stream.reduce` contract explicitly states that `accumulator(identity, t)` must equal `t`. For aggregations with a two-sided identity, test `op(t, identity)` as well to catch bugs in empty-branch reasoning and combination logic.

| Aggregation | Valid identity | Associative? | Commutative? | Notes |
| --- | --- | --- | --- | --- |
| `long` addition | `0L` | Yes in Java semantics | Yes | Can overflow if business domain is large |
| `long` multiplication | `1L` | Yes in Java semantics | Yes | Can overflow |
| `Integer::max` | `Integer.MIN_VALUE` | Yes | Yes | Do not use `0` for arbitrary integers |
| `Integer::min` | `Integer.MAX_VALUE` | Yes | Yes | Boundary values may appear in real data |
| `String` concatenation | `""` | Yes | No | Must preserve encounter order |
| Subtraction | No valid two-sided identity | No | No | Never use for parallel reduction |
| `(a + b) / 2` | No valid identity | No | Yes | Never use to aggregate averages |
| `double` addition | Complex for exact bits | Not strictly | Special NaN and signed-zero cases | Rounding varies with grouping |

### Wrong identity with negative values

~~~java
import java.util.List;

public class WrongIdentity {
    public static void main(String[] args) {
        List<Integer> values = List.of(-10, -5, -20);

        int wrong = values.parallelStream()
            .reduce(0, Integer::max);

        var correct = values.parallelStream()
            .reduce(Integer::max);

        System.out.println(wrong);   // 0: not present in source
        System.out.println(correct); // Optional[-5]
    }
}
~~~

`0` is not an identity for `max` over negative numbers because `max(0, -10) != -10`. When a source may be empty, `reduce(Integer::max)` returns `Optional<Integer>`, distinguishing absence from an arbitrary sentinel.

## 4. Testing Laws in Plain Java

The test template below tries many triples with a fixed seed. It verifies two-sided identity and associativity for a `LongBinaryOperator`.

~~~java
import java.util.Random;
import java.util.function.LongBinaryOperator;

public class ReduceLawsTest {

    static void assertLaws(
        long identity,
        LongBinaryOperator operation,
        long seed,
        int trials
    ) {
        Random random = new Random(seed);

        for (int i = 0; i < trials; i++) {
            long a = random.nextInt(2001) - 1000;
            long b = random.nextInt(2001) - 1000;
            long c = random.nextInt(2001) - 1000;

            if (operation.applyAsLong(identity, a) != a
                || operation.applyAsLong(a, identity) != a) {
                throw new AssertionError(
                    "Vi phạm identity với a=" + a
                );
            }

            long left = operation.applyAsLong(
                operation.applyAsLong(a, b), c
            );

            long right = operation.applyAsLong(
                a, operation.applyAsLong(b, c)
            );

            if (left != right) {
                throw new AssertionError(
                    "Vi phạm associativity với a="
                    + a + ", b=" + b + ", c=" + c
                );
            }
        }
    }

    public static void main(String[] args) {
        assertLaws(0L, Long::sum, 2026L, 2000);
        assertLaws(1L, (a, b) -> a * b, 2026L, 2000);

        // This is a broken combination op, not a PASS case:
        // assertLaws(0L, (a, b) -> a - b, 2026L, 2000);

        System.out.println("PASS");
    }
}
~~~

For primitive `long`, Java addition and multiplication wrap on overflow, yet remain associative modulo 2^64. When the business requires **overflow-free mathematical results**, choose safe bounds, check for overflow, or use `BigInteger`.

### Scope of randomized testing

Testing 2,000 triples **does not prove** the laws across the entire input domain. A fixed seed makes failures reproducible, yet you still need boundary cases like negative numbers, `0`, `±1`, extreme values, empty sources, and triples with repeated elements. Whenever a counterexample surfaces, save the input as a dedicated regression test.

## 5. Forcing Different Source Splits Instead of Just Calling `parallel`

A single `parallelStream()` run passing might reflect only **one lucky split schedule**. To test partition independence, force every split index on a small list, reduce both halves, and combine them.

~~~java
import java.util.List;

public class SplitReduceTest {

    static void assertAllSplits(List<Long> input) {
        long reference = input.stream()
            .reduce(0L, Long::sum);

        for (int split = 0; split <= input.size(); split++) {
            long left = input.subList(0, split).stream()
                .reduce(0L, Long::sum);

            long right = input.subList(split, input.size()).stream()
                .reduce(0L, Long::sum);

            long combined = Long.sum(left, right);

            if (reference != combined) {
                throw new AssertionError(
                    "Sai kết quả tại split=" + split
                );
            }
        }
    }

    public static void main(String[] args) {
        assertAllSplits(List.of());
        assertAllSplits(List.of(7L));
        assertAllSplits(List.of(7L, -2L, 5L, 8L, -1L));
        System.out.println("PASS");
    }
}
~~~

`split = 0` and `split = size` are especially important: one branch is empty, so `identity` must accurately represent "no result from this branch."

### Testing two three-branch merge trees

Given three partial results `a`, `b`, and `c`, compare:

~~~text
comb(comb(a, b), c)
comb(a, comb(b, c))
~~~

If they differ, the combiner is not associative. **Never reorder branches** for aggregations sensitive to encounter order, such as string concatenation.

### Parallel smoke test

~~~java
import java.util.List;

List<Long> input = List.of(7L, -2L, 5L, 8L, -1L);

long serial = input.stream().reduce(0L, Long::sum);
long parallel = input.parallelStream().reduce(0L, Long::sum);

System.out.println(serial == parallel); // true
~~~

A parallel smoke test is useful, yet it cannot replace law tests and deliberate split-point checks.


## 6. `reduce` Without Identity: `Optional` Does Not Fix a Broken Operation

The overload without an identity:

~~~java
Optional<T> reduce(BinaryOperator<T> accumulator)
~~~

returns `Optional.empty()` when the source is empty. It avoids inventing a default value outside the domain.

~~~java
import java.util.List;
import java.util.Optional;

public class OptionalReduceDemo {
    public static void main(String[] args) {
        Optional<Integer> max = List.of(-10, -5, -20)
            .parallelStream()
            .reduce(Integer::max);

        Optional<Integer> missing = List.<Integer>of()
            .stream()
            .reduce(Integer::max);

        System.out.println(max);     // Optional[-5]
        System.out.println(missing); // Optional.empty
    }
}
~~~

However, **dropping the identity does not remove the associativity requirement**. `reduce((a, b) -> a - b)` can still fail in parallel streams.

Never design an accumulator that returns `null` to represent "no result yet"; `reduce(BinaryOperator)` can throw `NullPointerException` if the reduced result is null. Rely on the terminal `Optional` or model an explicit state type.

## 7. Three-Argument `reduce`: Testing Compatibility

The overload:

~~~java
<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
)
~~~

is used when input elements have type `T` and the aggregated result has type `U`. `accumulator(U,T)` processes **one source element**; `combiner(U,U)` merges **two partial results**.

Example summing string lengths:

~~~java
import java.util.List;

public class ThreeArgumentReduce {
    public static void main(String[] args) {
        List<String> values = List.of("Java", "Stream", "API");

        int length = values.parallelStream()
            .reduce(
                0,
                (sum, word) -> sum + word.length(),
                Integer::sum
            );

        System.out.println(length); // 13
    }
}
~~~

Three sets of laws must hold:

**Identity for combiner:**

~~~text
comb(identity, u) = u
~~~

**Associativity for combiner:**

~~~text
comb(comb(u, v), w) = comb(u, comb(v, w))
~~~

**Compatibility between accumulator and combiner:**

~~~text
comb(u, acc(identity, t)) = acc(u, t)
~~~

This is essential so that "reducing element `t` in a separate branch and merging" equals "accumulating `t` directly onto partial result `u`."

### Testing compatibility with an executable check

~~~java
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;

public class ReduceCompatibilityTest {
    public static void main(String[] args) {
        int identity = 0;

        BiFunction<Integer, String, Integer> accumulate =
            (sum, word) -> sum + word.length();

        BinaryOperator<Integer> combine = Integer::sum;

        for (int partial : List.of(0, 1, 10, 100)) {
            for (String word : List.of("", "A", "Java")) {
                int viaSeparateBranch = combine.apply(
                    partial,
                    accumulate.apply(identity, word)
                );
                int viaDirectAccumulation =
                    accumulate.apply(partial, word);

                if (viaSeparateBranch != viaDirectAccumulation) {
                    throw new AssertionError(
                        "Compatibility sai: " + partial + "/" + word
                    );
                }
            }
        }

        System.out.println("PASS");
    }
}
~~~

A broken combiner—such as multiplication—merges branches incorrectly even when the accumulator sums each branch's lengths accurately. Compatibility tests catch this immediately without depending on parallel scheduling.

### Three-argument tests must check empty sources too

~~~java
import java.util.List;

int emptyLength = List.<String>of()
    .parallelStream()
    .reduce(0, (sum, word) -> sum + word.length(), Integer::sum);

System.out.println(emptyLength); // 0
~~~

If `identity` is non-zero, an empty source immediately exposes the wrong identity.

## 8. Anti-Pattern: Mutable Identity in `reduce`

`reduce` requires side-effect-free reduction without mutating shared state. Passing a mutable `ArrayList` as `identity` and calling `add` inside the accumulator is a design bug, especially in parallel:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> input = List.of("A", "B", "C");

// ANTI-PATTERN: do not use for parallel collection.
ArrayList<String> wrong = input.parallelStream()
    .reduce(
        new ArrayList<String>(),
        (list, value) -> {
            list.add(value);
            return list;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
~~~

**Problems:**

- `identity` is **a single object instance**, not a factory giving each branch its own container.
- The accumulator mutates that object, introducing side effects and violating reduction's non-interfering/stateless contract.
- Multiple branches can share the same container, or the combiner can merge aliased references that were already mutated.
- Output may duplicate elements, drop elements, or behave unsafely; one passing run proves nothing.

### Fix with `Collector` for mutable reduction

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<String> correct = input.parallelStream()
    .collect(Collectors.toCollection(ArrayList::new));

System.out.println(correct); // [A, B, C]
~~~

`collect` uses a `supplier` to allocate fresh containers, `accumulator` to update each partition's container, and `combiner` to merge them per the `Collector` contract.

If you still want `reduce` to compute an aggregate value, use an **immutable** type and return new instances in accumulator/combiner, or use specialized operations like `mapToLong().sum()`.

## 9. `Collector` Laws: More Than Just an Associative Combiner

A `Collector` is a *mutable reduction* strategy with type:

~~~java
Collector<T, A, R>
~~~

Here `T` is the input element type, `A` is the accumulation container type, and `R` is the final result type. Key components:

| Component | Contract | Common bugs |
| --- | --- | --- |
| `supplier()` | Creates a fresh accumulation container | Returns the same mutable object on every call |
| `accumulator()` | Incorporates an element into container `A` | Mutates source or shared state outside container |
| `combiner()` | Merges two `A` containers into an equivalent one | Drops/duplicates data, reverses order, non-associative merge |
| `finisher()` | Converts container `A` into final result `R` | Drops data, exposes unintended mutable view |
| `characteristics()` | Declares properties the collector truly guarantees | Wrongly declares `UNORDERED`, `CONCURRENT`, or `IDENTITY_FINISH` |

### 9.1. Combiner identity law

For any valid accumulation state `a`, if `e = supplier.get()` is a fresh empty container, combining `a` with `e` must be **equivalent** to `a`:

~~~text
combine(a, supplier()) ≈ a
~~~

Here `≈` means **result equivalence under the collector's contract**, not necessarily identical object references or identical internal mutable state. When testing, pass states through `finisher` or check domain invariants instead of demanding reference equality.

### 9.2. Associativity law of the full `collect` process

For an ordered source `[a,b,c,d]`, both ways of producing the result must be equivalent:

~~~text
Way 1:
  A = supplier()
  acc(A,a), acc(A,b), acc(A,c), acc(A,d)
  result = finish(A)

Way 2:
  L = supplier(); acc(L,a), acc(L,b)
  R = supplier(); acc(R,c), acc(R,d)
  result = finish(combine(L,R))
~~~

Moving the cut to `[a] + [b,c,d]` or `[] + [a,b,c,d]` must still yield equivalent results. A valid combiner **does more than return an object of the right size**; it must preserve every required value and ordering.

### 9.3. Collector characteristics and equivalence semantics

For a **non-UNORDERED** collector, both results on an ordered source must be equivalent with respect to **encounter order**. For an `UNORDERED` collector, order may not matter; e.g., a Map `{"A"→1,"B"→2}` can be checked with `Map.equals` rather than printed string order.

Distinguish carefully: `Collector.Characteristics.UNORDERED` states that **the result does not depend on source order**, not that "any arbitrary merge function is valid."

## 10. Writing a Correct Custom `Collector`: Ordered String Joining

To see accumulator and combiner roles clearly, let's write a string-joining collector. String concatenation is associative **yet not commutative**, so the combiner must preserve left branch followed by right branch.

~~~java
import java.util.List;
import java.util.stream.Collector;

public class OrderedStringCollector {

    static Collector<String, StringBuilder, String> joining() {
        return Collector.of(
            StringBuilder::new,
            (builder, element) -> builder.append(element),
            (left, right) -> left.append(right),
            StringBuilder::toString
        );
    }

    public static void main(String[] args) {
        List<String> words = List.of("A", "B", "C", "D");

        String sequential = words.stream()
            .collect(joining());

        String parallel = words.parallelStream()
            .collect(joining());

        System.out.println(sequential); // ABCD
        System.out.println(parallel);   // ABCD
    }
}
~~~

**Explanation:**

- `supplier()` creates a **new** `StringBuilder` every time.
- `accumulator` appends each element to the end of the builder.
- `combiner` appends the right builder's contents **after** the left builder.
- `finisher` converts the builder to a `String`.
- This collector does **not** declare `UNORDERED` or `CONCURRENT`. Since the result is `String` while the intermediate state is `StringBuilder`, it also must not declare `IDENTITY_FINISH`.

The fact that `StringBuilder` is not thread-safe does **not make this collector wrong**, because the runtime supplies separate containers per partition before combining. Bugs appear only if **one builder is shared across branches** or `CONCURRENT` is falsely declared.

## 11. Testing a `Collector` by Forcing Every Split Point

The following test directly exercises the collector's `supplier`, `accumulator`, `combiner`, and `finisher`. It forces some elements into a left container, the rest into a right container, and combines them.

~~~java
import java.util.List;
import java.util.stream.Collector;

public class CollectorSplitChecks {

    static String collectWithSplit(
        List<String> input,
        int cut,
        Collector<String, StringBuilder, String> collector
    ) {
        StringBuilder left = collector.supplier().get();
        StringBuilder right = collector.supplier().get();

        for (int i = 0; i < cut; i++) {
            collector.accumulator().accept(left, input.get(i));
        }
        for (int i = cut; i < input.size(); i++) {
            collector.accumulator().accept(right, input.get(i));
        }

        StringBuilder merged = collector.combiner()
            .apply(left, right);

        return collector.finisher().apply(merged);
    }

    public static void main(String[] args) {
        List<String> input = List.of("A", "B", "C", "D");
        var collector = OrderedStringCollector.joining();

        String reference = input.stream().collect(collector);

        for (int cut = 0; cut <= input.size(); cut++) {
            String actual = collectWithSplit(input, cut, collector);

            if (!reference.equals(actual)) {
                throw new AssertionError(
                    "Sai tại cut=" + cut + ": " + actual
                );
            }
        }

        System.out.println("PASS");
    }
}
~~~

**Note:** Two **fresh** states are created for every check. Once the combiner runs, it may **mutate** the left/right state, so never reuse them as inputs for subsequent checks.

### Reversed-order combiner

A counterexample:

~~~java
import java.util.stream.Collector;

Collector<String, StringBuilder, String> broken = Collector.of(
    StringBuilder::new,
    (builder, element) -> builder.append(element),
    (left, right) -> right.append(left), // WRONG for ordered streams.
    StringBuilder::toString
);
~~~

When forced to split `["A","B"] + ["C","D"]`, the broken combiner returns `"CDAB"`, whereas a sequential run that skips the combiner returns `"ABCD"`.

This is exactly the kind of bug a single `stream().collect(...)` test misses. Pass `broken` into `CollectorSplitChecks.collectWithSplit`; whenever both branches are non-empty, the output breaks source order.

### Don't test just a single split

For an input of length 4, test `cut = 0,1,2,3,4`. Specifically, `cut = 0` and `cut = 4` test **combiner identity when one branch is empty**. Testing only a middle split easily misses bugs where a combiner drops values when the right container is empty.

## 12. Testing Multiple Merge Trees and Combiner Laws

Forcing one split point tests only two branches. For complex Collectors, also test parenthesizing **three or more** accumulation containers.

~~~text
Ordered source: [A, B] | [C] | [D, E]

Left tree:  combine(combine(L, M), R)
Right tree: combine(L, combine(M, R))
~~~

Both must produce equivalent results per contract. Since `StringBuilder` combiners mutate state, **never reuse the same L/M/R objects** across both trees. Create fresh independent states for each check.

The following test rebuilds states for each tree:

~~~java
import java.util.List;
import java.util.stream.Collector;

public class CollectorTreesTest {

    static StringBuilder part(
        List<String> values,
        Collector<String, StringBuilder, String> collector
    ) {
        StringBuilder result = collector.supplier().get();

        for (String value : values) {
            collector.accumulator().accept(result, value);
        }

        return result;
    }

    static String combineTree(
        List<String> leftPart,
        List<String> midPart,
        List<String> rightPart,
        boolean leftAssociative,
        Collector<String, StringBuilder, String> collector
    ) {
        StringBuilder a = part(leftPart, collector);
        StringBuilder b = part(midPart, collector);
        StringBuilder c = part(rightPart, collector);

        StringBuilder combined = leftAssociative
            ? collector.combiner().apply(
                collector.combiner().apply(a, b), c
            )
            : collector.combiner().apply(
                a, collector.combiner().apply(b, c)
            );

        return collector.finisher().apply(combined);
    }

    public static void main(String[] args) {
        var collector = OrderedStringCollector.joining();
        var left = List.of("A", "B");
        var middle = List.of("C");
        var right = List.of("D", "E");

        String tree1 = combineTree(
            left, middle, right, true, collector
        );
        String tree2 = combineTree(
            left, middle, right, false, collector
        );

        if (!tree1.equals(tree2) || !tree1.equals("ABCDE")) {
            throw new AssertionError("Collector không kết hợp");
        }

        System.out.println("PASS");
    }
}
~~~

**Significance:** This verifies combining twice under different parenthesizations. While it doesn't simulate every concurrent schedule, it is far stronger than comparing a single sequential run against a single parallel run.


## 13. `Collector` Bugs Invisible to a Single Sequential Run

A collector may pass sequentially because only **one container** is allocated and the **combiner is rarely or never invoked**. Once the source splits, hidden assumptions break.

### 13.1. `supplier` returns the same mutable container

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

ArrayList<String> shared = new ArrayList<>();

// ANTI-PATTERN: supplier returns the exact same object across calls.
Collector<String, ArrayList<String>, ArrayList<String>> broken =
    Collector.of(
        () -> shared,
        ArrayList::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
~~~

`supplier` must provide a fresh accumulation container for **each evaluation partition**. If two branches receive the same `ArrayList`, combining aliased references duplicates data or causes concurrency hazards.

**Fix:**

~~~java
Collector<String, ArrayList<String>, ArrayList<String>> correct =
    Collector.of(
        ArrayList::new,
        ArrayList::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
~~~

When a custom collector isn't needed, `Collectors.toCollection(ArrayList::new)` is shorter and safer.

### 13.2. Combiner ignores one branch

~~~java
// Wrong: drops the right branch's data.
// (left, right) -> left
~~~

Such a collector can pass a sequential run yet lose data in parallel. Tests forcing `split = 1` or `split = 2` catch this immediately when the right branch is non-empty.

### 13.3. Combiner accidentally merges a container with itself

If `supplier` returns a shared object or a combiner receives unexpected aliased references, `left.addAll(right)` with `left == right` doubles the data. Thus testing **fresh suppliers** and state ownership is just as vital as testing content associativity.

### 13.4. Finisher drops data

Suppose accumulator gathers everything and combiner works, yet finisher returns only part of the state:

~~~java
// ANTI-PATTERN: drops the last character.
builder -> builder.length() == 0
    ? ""
    : builder.substring(0, builder.length() - 1)
~~~

When testing `Collector<T,A,R>`, invoke the **real finisher** on both the reference run and forced-split runs. Still, you also need an **independent business oracle**, such as expecting `"ABCD"`, because if the finisher makes the exact same bug on both paths, comparing "sequential == split" will still PASS.

### 13.5. Wrong `IDENTITY_FINISH` declaration

`Collector.Characteristics.IDENTITY_FINISH` means the finisher is effectively an identity cast where `A` directly matches `R` per contract. Never declare this flag when:

- State `A` is `StringBuilder` while result `R` is `String`.
- Finisher converts a mutable Map into another value object.
- Finisher performs normalization, validation, or snapshotting.

For example, `OrderedStringCollector.joining()` above has finisher `StringBuilder::toString`, so it **must not have `IDENTITY_FINISH`**. Falsely declaring it can let the framework skip the finisher, leading to type or result errors.

### 13.6. Wrong `CONCURRENT` declaration

`Collector.Characteristics.CONCURRENT` should be declared only when the accumulator is safe to invoke **concurrently on the same container** per contract. A plain `StringBuilder` is not thread-safe; you cannot arbitrarily mark Section 10's collector as concurrent.

`UNORDERED` is not a "free speed flag" either. If the output requires preserving character order `"ABCD"`, never declare `UNORDERED` and expect merges to preserve source order anyway.

## 14. The Average Problem: Why `(a+b)/2` Is Not Associative

A very common averaging mistake is trying this merge function:

~~~java
(a, b) -> (a + b) / 2.0
~~~

Try three values `0, 10, 20`:

~~~text
((0 + 10) / 2 + 20) / 2 = 12.5

(0 + (10 + 20) / 2) / 2 = 7.5

True average of 0, 10, 20 = 10
~~~

"Averaging two numbers" is non-associative and has no valid identity for reducing an arbitrary set of numbers. Moreover, two groups with the same average can have **different element counts**, so you cannot average group averages without weights.

### 14.1. The right state model: `(sum, count)`

The solution is accumulating **sum** and **count**; two partial states merge by summing their respective fields.

~~~java
import java.util.List;

public class AverageWithImmutableState {

    record Stats(long sum, long count) {

        Stats add(int value) {
            return new Stats(
                Math.addExact(sum, value),
                Math.addExact(count, 1L)
            );
        }

        Stats merge(Stats other) {
            return new Stats(
                Math.addExact(sum, other.sum),
                Math.addExact(count, other.count)
            );
        }

        double averageOrThrow() {
            if (count == 0) {
                throw new IllegalStateException("Không có dữ liệu");
            }
            return (double) sum / count;
        }
    }

    static Stats summarize(List<Integer> values, boolean parallel) {
        var stream = parallel
            ? values.parallelStream()
            : values.stream();

        return stream.reduce(
            new Stats(0L, 0L),
            Stats::add,
            Stats::merge
        );
    }

    public static void main(String[] args) {
        List<Integer> values = List.of(0, 10, 20);

        Stats serial = summarize(values, false);
        Stats parallel = summarize(values, true);

        if (!serial.equals(parallel)) {
            throw new AssertionError("Hai mode khác kết quả");
        }

        System.out.println(serial.averageOrThrow()); // 10.0
        System.out.println(summarize(List.of(), false));
        // Stats[sum=0, count=0]
    }
}
~~~

**Why does `Stats` work?**

- Identity is `Stats(0,0)`.
- `merge` adds sums and counts; it is associative on non-overflowing ranges.
- `add` and `merge` return **new records**, never mutating a shared mutable identity.
- Partitioning the source does not affect sum or count when additions succeed.
- An empty source yields count `0`, avoiding treating `0.0` as an observed average.

Standard tools like `Collectors.averagingInt` or `IntStream.average` are usually preferable when you only want the average. The `Stats` example clarifies **how to design valid accumulators and combiners**.

### 14.2. Checking compatibility for `Stats`

Suppose `u = Stats(10,2)` and new element `t = 5`:

~~~text
identity = Stats(0,0)

merge(u, add(identity,5))
= merge(Stats(10,2), Stats(5,1))
= Stats(15,3)

add(u,5)
= Stats(15,3)
~~~

Both paths yield the same result. For production code, test this property over many valid `Stats` instances and random inputs, including overflow-boundary inputs.

## 15. Floating-Point Numbers: Mathematical Associativity vs. Bitwise Equality

`double` addition is subject to IEEE 754 rounding. Changing parenthesization can change the result even though exact real addition is associative.

~~~java
public class FloatingPointAssociativity {
    public static void main(String[] args) {
        double a = 1e16;
        double b = -1e16;
        double c = 1.0;

        double left = (a + b) + c;
        double right = a + (b + c);

        System.out.println(left);  // 1.0
        System.out.println(right); // 0.0
        System.out.println(left == right); // false
    }
}
~~~

A parallel stream summing `double`s can combine partial results using a different tree than sequential addition. Thus, do not demand **bitwise equality** when business rules allow a tolerance. Conversely, never slap `Math.abs(a-b) < epsilon` everywhere blindly.

### Strategies for comparing `double` results

- When magnitudes are known in advance, choose an **absolute tolerance** based on domain requirements.
- When values span widely varying scales, consider **relative tolerance** or combined absolute–relative tolerance.
- Handle `NaN`, infinity, overflow, and `-0.0` explicitly if meaningful for the problem.
- Ensure small tolerances **do not mask** real bugs such as an entire missing group.
- When exact decimal currency is needed, use `BigDecimal` with explicit scale and rounding policies; never model money casually with `double`.

A basic finite comparison helper:

~~~java
public class FloatingComparison {

    static boolean close(double expected, double actual) {
        if (Double.isNaN(expected) || Double.isNaN(actual)) {
            return false;
        }
        if (expected == actual) {
            return true; // Covers +∞ with +∞, -∞ with -∞.
        }
        if (!Double.isFinite(expected) || !Double.isFinite(actual)) {
            return false;
        }

        double absoluteTolerance = 1e-9;
        double relativeTolerance = 1e-9;
        double scale = Math.max(
            Math.abs(expected), Math.abs(actual)
        );

        return Math.abs(expected - actual)
            <= Math.max(absoluteTolerance, relativeTolerance * scale);
    }
}
~~~

The `1e-9` thresholds are **illustrative only**, not a universal standard. Large catastrophic cancellations like `1e16 - 1e16 + 1` can cause huge relative differences; establish precision requirements before picking a tolerance.

### Don't confuse `double` non-associativity with other `Collector` bugs

If a parallel sum of many `double`s differs slightly in the last digits, rounding may explain it. If an entire group is missing, a count is off, or elements are duplicated, that is **not** mere floating-point rounding. Always check **counts**, key sets, per-group sums, and other invariants alongside floating-point comparisons.

## 16. Choose a Test Oracle Based on Result Type

Not every output should be compared with `toString()` or a single traversal order. Identify **what the contract actually guarantees**.

| Result | Usually appropriate comparison | What to avoid |
| --- | --- | --- |
| `long` sum/count | Exact equality within defined range | Ignoring domain overflow |
| `List<T>` from ordered stream | `List.equals` to check content and order | Comparing as a Set when order matters |
| `Set<T>` | `Set.equals` | Demanding identical iterator order |
| `Map<K,V>` | `Map.equals` | Comparing `HashMap` printed strings |
| `ConcurrentMap<K,V>` | `Map.equals` after collection completes | Demanding traversal order, schedule-dependent "last wins" |
| `Optional<T>` | `Optional.equals` or presence and value | Converting `Optional.empty` to null |
| `double` | Precision-policy comparison | Using one arbitrary epsilon for every problem |
| Ordered string-joining collector | Exact string equality | Declaring `UNORDERED` while expecting order |
| Grouped by key | Compare keys, sizes, and group elements per contract | Comparing only group count and ignoring payloads |

Example testing grouping:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class GroupingOracle {
    public static void main(String[] args) {
        List<String> values = List.of("A", "B", "A", "C", "B");

        Map<String, Long> serial = values.stream()
            .collect(Collectors.groupingBy(
                item -> item, Collectors.counting()
            ));

        Map<String, Long> parallel = values.parallelStream()
            .collect(Collectors.groupingBy(
                item -> item, Collectors.counting()
            ));

        if (!serial.equals(parallel)) {
            throw new AssertionError("Nhóm khác nhau");
        }

        if (!Long.valueOf(2L).equals(serial.get("A"))) {
            throw new AssertionError("Sai nhóm A");
        }

        System.out.println("PASS");
    }
}
~~~

Never write `serial.toString().equals(parallel.toString())` because `Map` has no general iteration-order contract. When using `groupingByConcurrent`, lists inside each group are **not guaranteed** to preserve encounter order either; pick an oracle matching business requirements.

### Note on concurrent collectors

`Collectors.toConcurrentMap` has both `CONCURRENT` and `UNORDERED`. If a merge function is order-sensitive, such as `(left,right) -> right`, which record counts as "last" depends on execution scheduling. If business logic requires the latest record, compare `version`/`timestamp` deterministically, or use an ordered collection strategy.


## 17. Investigation Workflow When Sequential and Parallel Differ

If a pipeline returns different outputs across modes, don't just slap `sequential()` on it to hide the bug. Isolate the root cause in order:

1. **Freeze the input:** use a small, immutable list containing negative numbers, duplicate keys, empty sources, and boundary cases. If reading from a file/database, make sure both modes read the same snapshot.
2. **Split the pipeline:** verify `filter`/`map` independently, then test `reduce` or `collect` in isolation. Never mix I/O, normalization, aggregation, and logging into one opaque test.
3. **Check laws:** `identity`, `associativity`, and `compatibility` for `reduce`; `supplier`/`combiner`/`finisher` correctness for `Collector`.
4. **Force partitions:** split at start, middle, and end; check empty branches, singleton branches, and different merge trees.
5. **Audit ordering:** check whether the collector is `UNORDERED`, whether output depends on "first/last" record, and whether your oracle demands ordering the API does not guarantee.
6. **Audit mutable state:** check if mappers/accumulators touch shared variables, mutate the source, or use a supplier returning the same object.
7. **Pick the right comparison:** integers, ordered Lists, Maps, Sets, Optionals, and doubles each have distinct verification rules.

### Quick diagnosis table

| Symptom | Suspect | How to check |
| --- | --- | --- |
| `reduce` fails only when splitting source | Non-associative operator | Compare `(a op b) op c` vs. `a op (b op c)` |
| Empty source returns wrong value | Wrong identity | Test `List.of()` and splits with empty branches |
| Collector misses half the data | Combiner drops a branch | Force a middle split |
| Output contains duplicate elements | Supplier shares state / alias | Verify fresh object created per call |
| String characters are reversed | Combiner merges in wrong order | Force `["A","B"] + ["C","D"]` |
| Duplicate-key records are wrong | Schedule-dependent merge function | Test multiple same-key entries in varied orders |
| Two Maps print differently | Wrong oracle comparison | Use `Map.equals` |
| `double` differs in last digits | Floating-point rounding | Check tolerance and non-float invariants |
| Fails only under concurrency | Unsafe external state | Inspect callbacks and characteristics |
| Wrong result type or skipped conversion | Wrong `IDENTITY_FINISH` flag | Verify `A`, `R`, and finisher |

**Note:** For complex Collectors, comparing two collect calls using the same collector isn't enough; if both share a broken finisher, they can produce equal wrong results. Always include an **independent business oracle**.

## 18. Fixed-Seed Randomized Testing Over All Split Points

We can generate many small lists and test every split index on Section 10's string-joining Collector. `String.join` serves as an independent oracle, avoiding using the collector under test to compute expected values.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public class RandomizedCollectorChecks {
    public static void main(String[] args) {
        Random random = new Random(2026L);
        var collector = OrderedStringCollector.joining();

        for (int trial = 0; trial < 200; trial++) {
            int count = random.nextInt(9);
            List<String> values = new ArrayList<>();

            for (int i = 0; i < count; i++) {
                values.add(
                    String.valueOf((char) ('A' + random.nextInt(4)))
                );
            }

            String expected = String.join("", values);

            for (int split = 0; split <= values.size(); split++) {
                String actual =
                    CollectorSplitChecks.collectWithSplit(
                        values, split, collector
                    );

                if (!expected.equals(actual)) {
                    throw new AssertionError(
                        "trial=" + trial
                        + ", split=" + split
                        + ", input=" + values
                        + ", actual=" + actual
                    );
                }
            }
        }

        System.out.println("PASS");
    }
}
~~~

This tests every split across 200 generated lists. **It is not a formal proof**: the domain covers only characters `A`–`D` and small lengths. To increase confidence, add edge cases, larger domains, `null`s per input policy, and three-or-more-branch splits.

When a counterexample is found, shrink it (*shrinking*) into a minimal regression test, such as `["A","B","C"]` instead of hundreds of elements. For concurrent collectors, sequential split tests won't catch all data races; add proper concurrency tests without relying on thread names or fixed callback schedules.

## 19. Common Reasoning Mistakes

### 19.1. Commutative implies associative

False. `(a+b)/2` is commutative yet not associative; grouping changes the result.

### 19.2. The identity of every aggregation is 0

False. Multiplication uses 1; `int` max uses `Integer.MIN_VALUE`; string joining uses `""`. When no valid identity exists, use the Optional-returning overload or design a dedicated state type.

### 19.3. One parallel run matching sequential proves correctness

False. The source split may not have exercised a broken combiner, or inputs may not have hit boundary cases. Use law tests and forced splits.

### 19.4. Testing only the Collector's combiner is enough

Insufficient. The supplier might share state, the accumulator might have side effects, the finisher might drop data, and characteristics might be wrong.

### 19.5. A mutable `ArrayList` can be `reduce`'s identity

Avoid. `reduce` has no supplier creating per-branch containers; mutable reduction belongs in `collect` or a `Collector`.

### 19.6. If string joining works sequentially, it works in parallel

False. If the combiner appends the right branch before the left, results come out scrambled while sequential execution might skip the combiner.

### 19.7. Different `HashMap` print order means wrong content

Not necessarily. When the contract only requires matching entries, `Map.equals` is the right comparison.

### 19.8. Any `double` discrepancy can be ignored

False. Define a tolerance policy and also verify counts/key sets. Missing data is not floating-point rounding.

### 19.9. A `CONCURRENT` Collector makes Map value lists thread-safe

No. `ConcurrentMap<K,List<V>>` does not automatically make each `List` value safe for concurrent modification after collection.

### 19.10. `sequential()` is a complete fix

Switching to sequential can merely mask a bug. If business logic inherently requires ordered stateful processing, state that explicitly; if parallelism is needed, fix the combination algorithm.

## 20. Pre-Parallelization Checklist

| Check | Passing criterion |
| --- | --- |
| Identity | Valid identity element across the input domain |
| Associativity | Different parenthesizations yield equivalent results |
| Compatibility | Accumulator and combiner of 3-arg `reduce` are compatible |
| Supplier | Allocates fresh containers; no improper shared mutable state |
| Accumulator | Non-interfering with source; no external shared state |
| Combiner | Neither drops nor duplicates; preserves encounter order if needed |
| Finisher | Converts `A → R` faithfully without losing data |
| Characteristics | No false `UNORDERED`, `CONCURRENT`, or `IDENTITY_FINISH` flags |
| Empty source | Returns identity/Optional/collector result per contract |
| Single-element branch | Produces accurate result |
| Multiple splits | Tested split positions and multiple merge trees |
| Numerics | Explicit policies for overflow, `NaN`, `Infinity`, and tolerance |
| Result type | Appropriate oracle for List/Set/Map/Optional |
| Ordering | Never depends on ordering unguaranteed by the API |
| Concurrency | If accumulator is concurrent, state supports it safely |
| Performance | Benchmark only after correctness is established |

## 21. Self-Check Questions and Extended Exercises

1. **What is associativity?** `op(op(a,b),c) = op(a,op(b,c))`.
2. **Are associativity and commutativity the same?** No; string concatenation is associative yet not commutative.
3. **Why is subtraction unsuitable for parallel `reduce`?** Changing parentheses alters the result.
4. **Why is `reduce(0, Integer::max)` wrong for negative numbers?** `0` is not an identity on negative integers.
5. **What does `reduce` without identity return on an empty source?** `Optional.empty()`.
6. **What is the extra law for 3-arg `reduce`?** Compatibility between accumulator and combiner.
7. **What is the compatibility formula?** `comb(u, acc(identity,t)) = acc(u,t)`.
8. **Why avoid a mutable `ArrayList` as `reduce` identity?** Shared state and mutating callbacks violate the contract.
9. **What must a `Collector`'s `supplier` return?** A fresh accumulation container suitable for each evaluation partition.
10. **What must a `combiner` guarantee?** Merging partial states without dropping/duplicating data, preserving order when required.
11. **Why test `split=0` and `split=size`?** Those cases test empty branches and identity handling.
12. **Can a string-joining combiner swap branches?** Not on an ordered stream.
13. **Why allocate fresh states for each merge tree?** Because the combiner may mutate its input containers.
14. **Can you declare `IDENTITY_FINISH` when the finisher turns `StringBuilder` into `String`?** No.
15. **When should `CONCURRENT` be declared?** When the accumulator is safe to invoke concurrently on the same container.
16. **Does `UNORDERED` automatically make any merge function valid?** No; the merge must still be designed to be order-independent.
17. **Why can't `(a+b)/2` merge arbitrary averages?** It is non-associative and ignores group weights.
18. **How do you compute an average accurately from partial results?** Merge `(sum,count)`, then compute `sum/count` at the end.
19. **Why can `double` sums vary across splits?** Rounding error.
20. **How should Maps be compared?** Usually with `Map.equals`, not printed strings.
21. **Do random tests prove every case?** No; they only increase coverage.
22. **Should `peek` be used to count exact callbacks as proof of correctness?** No, due to laziness, short-circuiting, and optimizations.
23. **Why use an independent oracle?** Both execution modes could share the same bug.
24. **What should be verified before benchmarking?** Laws, empty branches, partitions, state isolation, and outputs.
25. **When should a Stream remain sequential?** When the algorithm has ordering constraints not designed for parallel combining; document the constraint clearly.

### Extended Exercise A — Collector for count and sum

Write a Collector accepting integers and returning `Stats(count,sum)`. Verify sequential/parallel equivalence, all splits, and both merge trees. Cross-check against `IntStream.summaryStatistics()`.

### Extended Exercise B — Finding subtraction counterexamples

Generate all triples `a,b,c` in `[-3,3]`, find cases where `(a-b)-c != a-(b-c)`, and write a minimal regression test.

### Extended Exercise C — Broken finisher passing split tests

Create a `StringBuilder` collector whose finisher drops the final character. Both split paths can share the bug; add an independent oracle `String.join("", input)` to expose it.

### Extended Exercise D — Concurrent collector and latest record

Use `toConcurrentMap` with records carrying a `version`. Vary source order and run in parallel. Compare selecting by `version` against an order-blind `(left,right)->right` merge.

### Extended Exercise E — Large and small floating-point numbers

Build a sequence containing very large, very small, and opposite-signed numbers. Measure differences between sequential and parallel sums, define a tolerance policy, and check element counts to distinguish rounding from lost data.

**Remember:** A `reduce` or `Collector` is trustworthy only when **partitioning and combining partial results** leaves the output unchanged within acknowledged numeric limits. Verify **identity**, **associativity**, **compatibility**, independent state, combiner/finisher logic, and characteristics. Comparing sequential vs. parallel is only a starting point; forced splits/trees and an independent business oracle catch subtle bugs that small pipelines easily hide.
