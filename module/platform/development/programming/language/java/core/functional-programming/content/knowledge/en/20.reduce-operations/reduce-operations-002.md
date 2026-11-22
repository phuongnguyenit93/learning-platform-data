# `reduce()` Without an Initial Value and `Optional` Results in Java Stream

In Java Stream, **reduction** is the process of combining multiple elements into a single result, such as computing a sum, finding the maximum value, or concatenating strings. The key point of the **`reduce(BinaryOperator<T>)` overload without an initial value (*identity*)** is that its return type is **`Optional<T>`**, not `T`.

The reason: if the stream is **empty**, there is no first element to serve as the result or as the starting point for combining; Java needs a way to represent "no result". `Optional.empty()` handles that situation without forcing the API to invent a default value such as `0`, `""`, or a dummy object. If the stream has **one element**, the reduction returns that element itself wrapped in an `Optional`, without needing to call the combining function.

Short example:

~~~java
Optional<Integer> sum = java.util.stream.Stream.of(2, 3, 5)
        .reduce(Integer::sum); // Optional[10]
~~~

This is an illustrative snippet inside a method that has imported `java.util.Optional`. How to read it: `Stream<Integer> → reduce(BinaryOperator<Integer>) → Optional<Integer>`.

## 1. Method Signatures and Easily Confused Overloads

In `java.util.stream.Stream<T>`, the two basic overloads are:

~~~java
// Abbreviated API signatures for study; not a standalone Java class.
Optional<T> reduce(BinaryOperator<T> accumulator);
T reduce(T identity, BinaryOperator<T> accumulator);
~~~

Alongside those, there is also a three-argument overload:

~~~java
<U> U reduce(U identity,
             BiFunction<U, ? super T, U> accumulator,
             BinaryOperator<U> combiner);
~~~

This lesson focuses on the **one-parameter overload**. Comparison table:

| Call | Return type | When the source is empty |
| --- | --- | --- |
| `stream.reduce(accumulator)` | `Optional<T>` | `Optional.empty()` |
| `stream.reduce(identity, accumulator)` | `T` | Returns `identity` |
| `stream.reduce(identity, accumulator, combiner)` | `U` | Returns `identity`, subject to the identity/combiner correctness requirements |
| `intStream.reduce(operator)` | `OptionalInt` | `OptionalInt.empty()` |
| `intStream.reduce(identity, operator)` | `int` | Returns `identity` |

In the one-parameter overload, `BinaryOperator<T>` is a functional interface that takes **two values of the same type `T`** and returns a value of type `T`:

~~~java
T apply(T left, T right);
~~~

Therefore, `Stream<Integer>.reduce(Integer::sum)` returns `Optional<Integer>`. `Stream<String>.reduce(String::concat)` returns `Optional<String>`. `Stream<Order>.reduce(...)` returns `Optional<Order>`, and cannot automatically turn into `Optional<Integer>` if the reduction function only accepts and returns `Order`.

## 2. Runnable Example: Empty, Single-Element, and Multi-Element Streams

Create the file `ReduceWithoutIdentityDemo.java`:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

public class ReduceWithoutIdentityDemo {
    public static void main(String[] args) {
        List<Integer> values = List.of(4, 7, 2);

        Optional<Integer> sum = values.stream()
                .reduce(Integer::sum);
        Optional<Integer> maximum = values.stream()
                .reduce(Integer::max);

        Optional<Integer> empty = Stream.<Integer>empty()
                .reduce(Integer::sum);
        Optional<Integer> single = Stream.of(9)
                .reduce(Integer::sum);

        System.out.println("sum=" + sum);
        System.out.println("maximum=" + maximum);
        System.out.println("empty=" + empty);
        System.out.println("single=" + single);
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac --release 17 ReduceWithoutIdentityDemo.java
java ReduceWithoutIdentityDemo
~~~

Stdout:

~~~text
sum=Optional[13]
maximum=Optional[7]
empty=Optional.empty
single=Optional[9]
~~~

Explanation:

1. Source `[4, 7, 2]`: `Integer::sum` combines to 13; `Integer::max` selects 7. Both results are wrapped in `Optional`.
2. **Empty** source: there is no element to produce a result; `Optional.empty()` clearly signals the absence.
3. **Single-element** source: no need to combine with another element; the result is `Optional[9]`.
4. Each `reduce` call obtains **a new stream** from `values` or `Stream.of`. A stream that has already executed a terminal operation must not be reused.

Do not confuse `Optional[13]` with a string containing square brackets: that is how `Optional.toString()` formats a present `Optional`; business code should use the `Optional` API rather than parsing this string.

## 3. Reduction Model Without an Identity

For an **ordered sequential stream**, you can visualize it as:

~~~text
Source: [2, 3, 4, 5]

Start:        current = 2
Element 3:    current = accumulator(2, 3)  → 5
Element 4:    current = accumulator(5, 4)  → 9
Element 5:    current = accumulator(9, 5)  → 14

Result:       Optional[14]
~~~

For a list containing only `[2]`, the result is `Optional[2]`, without calling the accumulator. For the list `[]`, there is no initial `current` and the result is `Optional.empty()`.

This is a **mental model** for the sequential case, not a guarantee that every `reduce` always executes in a left-associative chain like this. Java is allowed to reduce by combining sub-parts of the data, especially with parallel streams. For the result to be correct, the accumulator must satisfy the associativity requirement.

Example observing the order in a **sequential stream**. Create the file `ReduceTraceDemo.java`:

~~~java
import java.util.Optional;
import java.util.stream.Stream;

public class ReduceTraceDemo {
    public static void main(String[] args) {
        Optional<Integer> result = Stream.of(2, 3, 4)
                .reduce((left, right) -> {
                    System.out.println(
                            "combine " + left + " + " + right);
                    return left + right;
                });
        System.out.println("result=" + result);
    }
}
~~~

~~~bash
javac --release 17 ReduceTraceDemo.java
java ReduceTraceDemo
~~~

Stdout on this specific sequential pipeline:

~~~text
combine 2 + 3
combine 5 + 4
result=Optional[9]
~~~

This trace is for **learning the mechanism**, not a pattern to use in production: do not rely on side effects inside the accumulator or assume all reductions invoke the function in that order.

## 4. Why Can't a Default `T` Be Returned for All Cases?

Suppose you want to get the largest element in a `Stream<Integer>`:

~~~java
Optional<Integer> max =
        numbers.stream().reduce(Integer::max);
~~~

On the list `[-9, -3, -12]`, the largest value is `-3`; on the list `[]`, **there is no largest value**. If you arbitrarily pick `0` as the identity and call `reduce(0, Integer::max)`, the result for an all-negative list becomes `0`: wrong data because that identity does not fit the `max` operation over negative numbers.

Example that is wrong for the intent "find max":

~~~java
// numbers is a List<Integer> that may contain negative numbers.
int wrongMax = numbers.stream().reduce(0, Integer::max);
~~~

With `numbers = List.of(-9, -3, -12)`, `wrongMax == 0` even though `0` does not appear in the source at all. Meanwhile, `numbers.stream().reduce(Integer::max)` returns `Optional[-3]`.

Core difference:

- **Without identity**: lets you express "no result yet", without imposing a fabricated value on an empty source.
- **With a valid identity**: suitable when a valid identity element exists for the operation and data type (for example `0` for integer addition, `1` for integer multiplication).
- **Wrong identity**: can skew the result **even when the stream is non-empty**.

Do not choose an overload out of habit; you must check whether the operation has a mathematically and business-valid identity element.

## 5. Distinguishing `Optional.empty()` from `Optional.of(0)`

Both results may print or convert to the same number after calling `orElse(0)`, but **their meaning before conversion is different**:

~~~java
Optional<Integer> empty =
        java.util.stream.Stream.<Integer>empty()
                .reduce(Integer::sum);

Optional<Integer> zero =
        java.util.stream.Stream.of(-3, 3)
                .reduce(Integer::sum);
~~~

Here:

- `empty` is `Optional.empty()`: **no elements and no reduction result**.
- `zero` is `Optional[0]`: **data is present**, and the actual sum is 0.
- `empty.orElse(0)` and `zero.orElse(0)` both return `0`, **losing the ability to distinguish between no data and data summing to 0**.

If the business logic needs to know "whether there were any transactions", do not automatically call `orElse(0)` without thinking. When you only need an arithmetic sum and 0 is a valid identity, the `reduce(0, Integer::sum)` overload or `IntStream.sum()` is usually simpler.

## 6. What to Do with `Optional<T>` After `reduce`?

An `Optional<T>` result lets you handle "present/absent" using intentional APIs:

| API | Usage | Meaning |
| --- | --- | --- |
| `isPresent()` | `result.isPresent()` | Checks whether the result has a value. |
| `isEmpty()` | `result.isEmpty()` | Checks whether there is no result (Java 11+). |
| `ifPresent(consumer)` | `result.ifPresent(System.out::println)` | Runs the action only when a value is present. |
| `map(fn)` | `result.map(Object::toString)` | Transforms the result if a value is present. |
| `orElse(fallback)` | `result.orElse(0)` | Returns a fallback value when empty. |
| `orElseGet(supplier)` | `result.orElseGet(() -> loadDefault())` | Calls the supplier only when empty. |
| `orElseThrow()` | `result.orElseThrow()` | If empty, throws `NoSuchElementException`. |
| `orElseThrow(supplier)` | `result.orElseThrow(() -> new IllegalStateException("empty"))` | If empty, throws a business exception. |

`loadDefault()` in the table is an **illustrative method name**, not a built-in Java API.

Create the file `HandleReducedOptionalDemo.java`:

~~~java
import java.util.List;
import java.util.Optional;

public class HandleReducedOptionalDemo {
    static String describe(List<Integer> values) {
        Optional<Integer> total =
                values.stream().reduce(Integer::sum);
        return total.map(n -> "Tổng = " + n)
                .orElse("Không có dữ liệu");
    }

    public static void main(String[] args) {
        System.out.println(describe(List.of(2, 3)));
        System.out.println(describe(List.of()));
        System.out.println(describe(List.of(-3, 3)));
    }
}
~~~

~~~bash
javac --release 17 HandleReducedOptionalDemo.java
java HandleReducedOptionalDemo
~~~

Stdout:

~~~text
Tổng = 5
Không có dữ liệu
Tổng = 0
~~~

This example preserves the difference between an **empty source** and a **sum equal to zero**. `Optional.map` only runs when the `Optional` has a value; `orElse` provides the message when empty.

Avoid calling `result.get()` before being sure a value is present: on `Optional.empty()`, `get()` throws `NoSuchElementException`. `orElseThrow()` expresses the expectation that a result must exist more clearly and lets you supply a business error message.

### `orElse` vs. `orElseGet`: eager vs. lazy

In:

~~~java
// Illustrative snippet inside a method.
String value = optional.orElse(expensiveFallback());
~~~

Java must evaluate `expensiveFallback()` **before** calling `orElse`, even when `optional` already has a value. With:

~~~java
String value = optional.orElseGet(() -> expensiveFallback());
~~~

the supplier is only invoked when `optional` is empty. Both snippets require a valid `expensiveFallback()` method and `optional` variable in real context; they are not standalone programs.

## 7. Should a Problem Return `Optional` or a Default Value?

Suppose a repository returns a list of scores and a business function needs the **highest score**. Using:

~~~java
Optional<Integer> highest =
        scores.stream().reduce(Integer::max);
~~~

The caller can decide:

- No scores → display "not graded", return HTTP 404/204 depending on the API contract, or throw an error.
- Scores present → use the actual value, including `0` or negative numbers.

If instead of `Optional<Integer>` the API returned an `int` with `0` when empty, the "no scores yet" state could be confused with a valid score of `0`.

Similarly, the **minimum value**, the **highest-priced order**, or a **concatenated string from a list** might have no result if the source is empty. Some operations still have a natural identity (for example, string concatenation has `""` as an identity), but choosing between "no result" and "empty string" must be based on **business semantics**.

If the specific requirement is finding min/max on `Stream<T>`, Java already provides `stream.min(comparator)` and `stream.max(comparator)`, which also return `Optional<T>`; they usually express intent more clearly than a hand-written `reduce`. `reduce` is especially valuable when you need a general combining operation that has no dedicated terminal operation.

## 8. Example: Reducing a Custom Object Type

The identity-less overload preserves the element type `T`. Suppose a stream contains `Order` objects; you can pick the largest order using a function that combines two `Order` instances, without having to invent a "zero-th order".

Create the file `ReduceOrderDemo.java`:

~~~java
import java.util.List;
import java.util.Optional;

public class ReduceOrderDemo {
    record Order(String id, int amount) {}

    static Optional<Order> mostExpensive(List<Order> orders) {
        return orders.stream().reduce(
                (left, right) ->
                        left.amount() >= right.amount() ? left : right);
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 60),
                new Order("B", 140),
                new Order("C", 95)
        );

        System.out.println(mostExpensive(orders)
                .map(Order::id)
                .orElse("none"));
        System.out.println(mostExpensive(List.of())
                .map(Order::id)
                .orElse("none"));
    }
}
~~~

~~~bash
javac --release 17 ReduceOrderDemo.java
java ReduceOrderDemo
~~~

Stdout:

~~~text
B
none
~~~

Type flow:

~~~text
List<Order>
  .stream()                           → Stream<Order>
  .reduce(BinaryOperator<Order>)      → Optional<Order>
  .map(Order::id)                     → Optional<String>
  .orElse("none")                     → String
~~~

If you want the **sum of `amount`** instead of picking an `Order` object, `Stream<Order>.reduce((a,b) -> a.amount() + b.amount())` is a **type error** because `BinaryOperator<Order>` must return `Order`, whereas the sum is an `int`. An appropriate approach is `orders.stream().mapToInt(Order::amount).sum()` for an `int` sum, or `orders.stream().map(Order::amount).reduce(Integer::sum)` if you want an `Optional<Integer>` to distinguish an empty source from a sum of 0.

## 9. Accumulator Requirements: Associativity and No Side Effects

Under the Stream reduction contract, the accumulator must be **associative**, **non-interfering** (does not modify the source), and **stateless** (does not depend on external mutable state).

For three values `a`, `b`, `c`, associativity means:

~~~text
op(op(a, b), c) == op(a, op(b, c))
~~~

Typical suitable examples:

- `Integer::sum` for `int` addition (under Java integer semantics, including wraparound overflow).
- `Integer::max` or `Integer::min` for finding extrema.
- `String::concat` is associative with respect to the concatenated content when strings are non-null, although element order still matters.

**Do not use subtraction** if you need a valid reduction that has the same meaning regardless of grouping:

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

The two groupings produce different results, so `(a,b) -> a - b` does not satisfy associativity. A sequential run may produce a result that looks "right", but a parallel reduction is allowed to split and combine differently.

Do not capture an external mutable `ArrayList` and add elements to it from the accumulator. That creates side effects and risks bugs in parallel execution. If you need to collect elements into a collection, use `collect(Collectors.toList())`, `Stream.toList()`, or an appropriate collector; do not try to use `reduce` to replace a collector with a mutable container.

Additionally, the number of times the accumulator is called and how elements are grouped are not a contract for performing logging, database updates, or incrementing business counters. When controlled side effects are needed, separate them from the reduction and follow an appropriate processing mechanism.

## 10. Comparing Sequential and Parallel Results When the Operation Is Valid

Create the file `ParallelReduceDemo.java`:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.stream.IntStream;

public class ParallelReduceDemo {
    public static void main(String[] args) {
        List<Integer> values = IntStream.rangeClosed(1, 1000)
                .boxed()
                .toList();

        Optional<Integer> sequential = values.stream()
                .reduce(Integer::sum);
        Optional<Integer> parallel = values.parallelStream()
                .reduce(Integer::sum);

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
    }
}
~~~

~~~bash
javac --release 17 ParallelReduceDemo.java
java ParallelReduceDemo
~~~

Stdout:

~~~text
sequential=Optional[500500]
parallel=Optional[500500]
~~~

Because `Integer::sum` is associative under `int` addition semantics, regrouping does not change the reduced value for this data. **Do not infer** that every two-parameter function produces the same result on sequential and parallel streams. Subtraction, operations depending on invocation order, or using shared mutable variables are classic warning signs.

For string concatenation, even though concatenation is associative, it is **not commutative** (`"A" + "B"` differs from `"B" + "A"`). The encounter order of the source still matters. Do not arbitrarily call `unordered()` when the result needs to preserve a meaningful order.

## 11. `null` Rules: Do Not Return `null` from a Reducer

`Optional` **does not represent a "present null" value**. The Java documentation specifies that `reduce(BinaryOperator<T>)` throws `NullPointerException` if the reduction result is `null`. Therefore, **do not use `null` to represent "discard element" or "cannot compute"** from the accumulator.

This example **intentionally violates the contract**; do not use it in production:

~~~java
// Error illustration: the accumulator returns null when called.
java.util.stream.Stream.of("A", "B")
        .reduce((left, right) -> null); // NullPointerException
~~~

`Optional.empty()` is for **the case where there is no reduction value**, not a way to automatically fix a `null` returned by the accumulator. If you need to exclude elements before reducing, use `filter`. If you need to represent a nullable computation result, define a separate contract and handle it before or after the reduction; do not equate it with a null reducer result.

Regarding **null input elements**, a `Stream` may allow nulls, but many operations such as `Integer::sum` will throw due to unboxing or dereferencing. On the other hand, `List.of(...)` does not allow null elements. A safe practice is to specify the input data contract and check/filter nulls **before calling `reduce`**, for example:

~~~java
// Illustration in the context of a Stream<Integer> source.
Optional<Integer> sum = source
        .filter(java.util.Objects::nonNull)
        .reduce(Integer::sum);
~~~

Note: if all elements are removed by `filter`, `sum` will be `Optional.empty()`. That is an intentional change to the dataset. If null data should be rejected as an error rather than ignored, validate the input and fail-fast; do not filter silently.

## 12. Primitive Streams: `OptionalInt`, `OptionalLong`, `OptionalDouble`

Primitive streams have their own **identity-less** `reduce` overloads to avoid boxing:

| Stream | Combining function | Identity-less result |
| --- | --- | --- |
| `IntStream` | `IntBinaryOperator` | `OptionalInt` |
| `LongStream` | `LongBinaryOperator` | `OptionalLong` |
| `DoubleStream` | `DoubleBinaryOperator` | `OptionalDouble` |

Create the file `PrimitiveReduceDemo.java`:

~~~java
import java.util.stream.IntStream;

public class PrimitiveReduceDemo {
    public static void main(String[] args) {
        System.out.println("max="
                + IntStream.of(3, 7, 2).reduce(Integer::max));
        System.out.println("empty="
                + IntStream.empty().reduce(Integer::sum));
        System.out.println("default="
                + IntStream.empty().reduce(Integer::sum).orElse(-1));
        System.out.println("sumWithIdentity="
                + IntStream.empty().reduce(0, Integer::sum));
    }
}
~~~

~~~bash
javac --release 17 PrimitiveReduceDemo.java
java PrimitiveReduceDemo
~~~

Stdout:

~~~text
max=OptionalInt[7]
empty=OptionalInt.empty
default=-1
sumWithIdentity=0
~~~

`OptionalInt` is not the same static type as `Optional<Integer>`; however, both represent the presence/absence of a result and provide operations such as `isPresent`, `orElse`, and `orElseThrow`.

In Java, if the goal is simply the sum of an `IntStream`, `sum()` is usually shorter and clearer than `reduce(0, Integer::sum)`. If you need to **distinguish no elements from a sum of 0**, `IntStream.reduce(Integer::sum)` returning `OptionalInt` is an appropriate choice.

## 13. `reduce`, `min/max`, `sum`, and `collect`: Choosing the Right Terminal Operation

Not every aggregation task should use a manual `reduce`:

| Goal | Usually preferred approach | Result when source is empty |
| --- | --- | --- |
| Reduce with an arbitrary combining operation, no suitable identity | `stream.reduce(op)` | `Optional.empty()` |
| Sum of `int` where 0 is acceptable | `intStream.sum()` | `0` |
| Sum of `int` when you need to know if the source has data | `intStream.reduce(Integer::sum)` | `OptionalInt.empty()` |
| Find largest/smallest element by a criterion | `stream.max(comparator)` / `stream.min(comparator)` | `Optional.empty()` |
| Collect elements into a list | `stream.toList()` or `collect(toList())` | Empty list |
| Build a `Map`/grouping or mutable reduction | `collect(collector)` | Value defined by the collector |
| Count elements | `stream.count()` | `0L` |

Do not confuse `reduce(BinaryOperator<T>)` with `findFirst()`: both can return `Optional<T>`, but `findFirst()` only picks one element in encounter order if present, whereas `reduce` combines data using the supplied operation.

In some situations, `Collectors.reducing(...)` also appears as a downstream collector, but that is a different API from the `Stream.reduce` overload discussed here. When you need to group and then reduce each group, choose the appropriate collector and check the return type carefully — it may nest an `Optional` inside the `Map` values.

## 14. Risks with Infinite Sources and Stream Reuse

Identity-less `reduce` is a **terminal operation** and is **not short-circuiting in the usual sense**: to know the result of a general aggregation, it must process the necessary elements of the source until the source ends. On an infinite stream with no termination point, calling `reduce` to obtain a result may never finish.

Example to avoid executing:

~~~java
// Snippet intentionally illustrating a non-terminating case.
// Do not run this pipeline expecting a finite Optional:
// java.util.stream.Stream.iterate(1, n -> n + 1)
//         .reduce(Integer::sum);
~~~

If the data is bounded by business rules, you can use `limit(n)` **before** `reduce`, but keep in mind that this reduces over the **limited subset of data**, not the entire original source.

Also do not call multiple terminal operations on a single stream:

~~~java
// Incorrect illustration if continuing to reuse the same instance s.
java.util.stream.Stream<Integer> s =
        java.util.stream.Stream.of(1, 2, 3);
java.util.Optional<Integer> sum = s.reduce(Integer::sum);
// s.count(); // Invalid because s has already been consumed.
~~~

If you need both `count` and `sum`, consider primitive `summaryStatistics()`, a composite collector, or recreating the stream from a re-readable source. For one-shot sources like I/O, database cursors, or live data, do not assume they can be re-read without cost or discrepancies.

## 15. Thoroughly Testing Edge Cases

For an important reduction function, at a minimum you should test:

| Data | Case to verify |
| --- | --- |
| `[]` | `Optional.empty()`, with no fabricated value. |
| `[9]` | `Optional[9]`, accumulator does not need to run. |
| `[2, 3, 4]` | `Optional[9]` for addition. |
| `[-9, -3, -12]` | Actual max is `-3`, not a fake identity `0`. |
| `[-3, 3]` | Sum is `Optional[0]`, **distinct from** empty. |
| Multiple records tied for max key | Tie-breaking rule is stable and matches business logic. |
| Parallel source, valid associative operation | Result has the same meaning as the sequential source. |
| Reduction function returns `null` | This is a contract error, not "empty". |
| Data containing null | Clear policy for filtering or rejecting nulls. |
| Very large or infinite source | Appropriate bounds and resource usage. |

Do not automatically treat `Optional.empty()` as an error. Sometimes an empty stream is the normal result of a query after `filter`. It is the responsibility of the business layer to decide whether to represent that absence as a default value, a message, or an exception.

## 16. Common Mistakes When Writing `reduce()` Without an Identity

1. **Assigning the result directly to `T`:** `int sum = stream.reduce(Integer::sum)` is a type error; the actual result is `Optional<Integer>`.
2. **Calling `get()` unconditionally:** `Optional.empty().get()` throws `NoSuchElementException`. Use `orElse`, `orElseThrow`, `ifPresent`, or handle the `Optional` according to the contract.
3. **Treating empty as `0`:** an empty stream and a stream whose sum is 0 are two different states.
4. **Choosing the wrong identity for `max/min`:** `reduce(0, Integer::max)` produces wrong results when all numbers are negative.
5. **Writing a non-associative accumulator:** subtraction or logic that depends on grouping order can produce inconsistent results when run in parallel.
6. **Returning `null` from the accumulator:** this overload requires a valid reduction result; null can cause a `NullPointerException`.
7. **Thinking `Stream<Order>.reduce(...)` can return an integer:** a one-parameter reducer must accept and return the same element type `Order`.
8. **Using the accumulator to replace a mutable collector:** prone to side effects and unsafe shared data.
9. **Reusing a stream after `reduce`:** a terminal operation consumes the stream; create a new stream if the source supports it.
10. **Ignoring element counts:** the reducer does not call the accumulator when the source is empty or has one element, so testing only multi-element inputs can miss bugs.
11. **Assuming the reducer always runs sequentially from left to right:** parallel execution may group differently; rely only on the associative and stateless contract.
12. **Using `reduce` on an infinite source without a termination condition:** it may never return a result.
13. **Confusing `Optional<T>` with `OptionalInt`:** pick the right API for `Stream<T>` versus primitive streams.
14. **Using `orElse(expensive())` thinking the fallback is lazy:** the argument is evaluated eagerly beforehand; use `orElseGet` when deferral is needed.

## 17. Checklist Before Choosing a `reduce` Overload

1. Does the reduction function have the exact type `T × T → T`?
2. On an **empty source**, does the business logic want "no result" or a specific identity?
3. If there is no identity, has the caller handled `Optional<T>`?
4. Is the accumulator **associative**, non-interfering with the source, and free of mutable state?
5. Can the accumulator return `null`, throw an exception, or receive null elements?
6. If run in parallel, will the result still be correct under different groupings?
7. Does this aggregation already have a clearer, dedicated terminal operation, such as `sum`, `min`, `max`, or `collect`?
8. Have you tested an empty source, a single element, boundary values, and an actual value equal to the default identity?

**Key takeaway:** `Stream<T>.reduce(BinaryOperator<T>)` **has no identity**, so it returns `Optional<T>`: empty stream → `Optional.empty()`, one element → `Optional` containing that element, multiple elements → `Optional` containing the reduced value if the operation is valid. Let `Optional` represent the absence of data and use `orElse`/`orElseThrow` only when a clear business policy has been chosen; do not substitute an arbitrary identity or return `null` from the accumulator.