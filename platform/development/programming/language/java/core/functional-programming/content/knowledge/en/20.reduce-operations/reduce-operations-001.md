# Reduction Operations Combining Multiple Elements into One Result in Java Stream

## 1. What is Reduction?

**Reduction** is an operation that combines multiple elements into **a single summary result**. Instead of keeping a list of results like `map` or filtering out elements like `filter`, `reduce` takes a combining operation and applies it to compute a sum, product, maximum value, or a statistics object.

For example, with an ordered source:

~~~text
Source: [2, 3, 4]
Sum: 0 + 2 + 3 + 4 = 9
Product: 1 × 2 × 3 × 4 = 24
Max: max(max(2, 3), 4) = 4
~~~

Placed in a Java method:

~~~java
List<Integer> values = List.of(2, 3, 4);
int sum = values.stream().reduce(0, Integer::sum);
int product = values.stream().reduce(1, (a, b) -> a * b);
~~~

This snippet requires `import java.util.List;`. `reduce` is a **terminal operation** of Stream: the call asks the framework to compute a single result, consuming the corresponding Stream. The two addition/multiplication operations in the example return `9` and `24`, respectively.

Java 17 provides three important overloads:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator)

Optional<T> reduce(BinaryOperator<T> accumulator)

<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

These are **API signatures for explanation**, not complete code to place inside a class. They serve, respectively: (1) a combining operation with a neutral value (identity) and result type T, (2) a combining operation without an identity value so it needs to represent the empty source case, and (3) an aggregation operation with a result type U different from the source element type T.

**Study principle:** `reduce` is not just a shorthand loop. A correct reduce operation must satisfy the requirements for **identity**, **associativity**, **non-interference with the source**, and the ability to handle an **empty Stream**.

## 2. reduce(identity, accumulator) — used when an identity element exists

Addition:

~~~java
int total = List.of(2, 3, 4).stream()
        .reduce(0, Integer::sum);
// 9
~~~

- `identity = 0`: the starting value and also the **identity** (neutral) element for addition.
- `accumulator = Integer::sum`: a function that takes two `Integer` values and returns their sum.
- The result type is `Integer` (unboxed to `int` in the line above).

You can understand the sequential computation logically:

| Step | Accumulated | Element | New result |
| --- | ---: | ---: | ---: |
| Start | 0 | — | 0 |
| 1 | 0 | 2 | 2 |
| 2 | 2 | 3 | 5 |
| 3 | 5 | 4 | 9 |

However, this is an easy-to-understand diagram for **sequential** execution, not a promise that every reduce call runs on a single fixed execution schedule. The framework can split and merge groups when executing in parallel if the accumulator satisfies the contract.

### 2.1. Choosing the right identity

For an operator `op`, the identity `e` must satisfy:

~~~text
op(e, x) == x
op(x, e) == x
~~~

for values in the domain under consideration (within the semantics of the operation). For example:

| Combining operation | Valid identity | Why |
| --- | --- | --- |
| Number addition | `0` | `0+x=x` |
| Number multiplication | `1` | `1*x=x` |
| String concatenation | `""` | `"".concat(s)=s` |
| Merging two statistics (count,total) | `Stats(0,0)` | Does not increase count or total |

Do not use an arbitrary identity. If you write `reduce(10, Integer::sum)`, the result for `[2,3,4]` is 19, not 9. If you write `reduce(0, (a,b)->a*b)`, every product is forced to 0.

Especially with parallel reduction, a non-neutral identity can be applied across multiple processing partitions, causing incorrect results in ways that are hard to notice in sequential tests.

### 2.2. Empty Stream with an identity

~~~java
int emptySum = List.<Integer>of().stream()
        .reduce(0, Integer::sum);
// 0
~~~

Because there are no source elements to accumulate, this overload returns the **identity**. This is a meaningful value for addition; it is neither an exception nor `null`.

## 3. reduce(BinaryOperator) without identity — returns Optional<T>

Some problems do not have a natural identity value. For example, finding the **maximum element** in a collection that may be empty:

~~~java
Optional<Integer> largest = List.of(2, 3, 4).stream()
        .reduce(Integer::max);
// Optional[4]
~~~

This snippet requires `import java.util.Optional;`. On a non-empty source, `Integer::max` combines values into the largest value. On an empty source:

~~~java
Optional<Integer> emptyMax = List.<Integer>of().stream()
        .reduce(Integer::max);
// Optional.empty()
~~~

If there are no elements, you cannot claim "max is 0": a source of all negative numbers still has a negative max, whereas an empty source **has no max**. Therefore, instead of inventing a fake identity, Java returns `Optional<T>` so the caller can decide the policy:

~~~java
int max = largest.orElseThrow();
int fallback = emptyMax.orElse(-1);
~~~

Choose a default value `-1` only when it is valid in the business semantics. If an empty source is an error, you can use `orElseThrow(...)`; if an empty source is a normal case, keep the `Optional` and handle it explicitly at the boundary.

**Note on null:** reducing the result to `null` is not a valid way to model an Optional result. A reduction that returns `null` can lead to a `NullPointerException`; design operators and data types to avoid null or provide a dedicated representation for missing data.

## 4. Associativity — the most important condition for merging groups

A combining operation `op` is **associative** if:

~~~text
(a op b) op c == a op (b op c)
~~~

Why is this needed? With a parallel Stream, the framework can split the source:

~~~text
[2, 3, 4]
 /   |   \
2    3    4       (groups are reduced independently)
 \   |   /
(2 + 3) + 4 = 9  (combining the group results)
~~~

This is a conceptual model and does not describe the exact thread splitting in every JDK.

### 4.1. Integer addition and identity 0

`Integer::sum` is associative with identity 0 under Java's int addition semantics, so the reduced result is 9 for the small dataset above even when partitioned.

However, **associativity of int addition does not guarantee no overflow**. Java integer results can overflow the representable range. For large counts or money, choose an appropriate data type and overflow policy, such as `Math.addExact`, `long`, or `BigDecimal` depending on the problem.

### 4.2. Subtraction is not associative

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

These are two different results. Therefore, do not write:

~~~java
// Counterexample of the parallel reduction contract:
int difference = List.of(10, 3, 2).parallelStream()
        .reduce(0, (a, b) -> a - b);
~~~

This line is syntactically valid, but it does not satisfy the associative operator requirement of reduction. When the framework splits into groups, the result can deviate from the left-to-right subtraction the programmer envisioned.

If the business logic truly requires subtracting a sequence of numbers in order, design an explicit ordered operation or transform the expression into an associative reduction when mathematically possible.

### 4.3. Floating-point numbers require caution

With `double`, addition can produce different results when changing grouping due to rounding errors:

~~~text
(1.0e16 + (-1.0e16)) + 1.0 = 1.0
1.0e16 + ((-1.0e16) + 1.0) = 0.0
~~~

In problems requiring strict floating-point arithmetic, do not assume every form of parallel reduce gives bit-for-bit identical results to sequential iteration. You may need a more numerically stable summation algorithm or an exact numeric type suited to the domain.

## 5. Stateless and non-interfering: do not turn reduce into a side-effect channel

The accumulator should take its arguments and return a new result based on them, without depending on shared mutable state. Avoid:

~~~java
// Counterexample: using the accumulator to mutate external state.
// int[] sum = {0};
// numbers.stream().reduce(0, (a,b) -> {
//     sum[0] += b;
//     return a + b;
// });
~~~

The variable `sum[0]` is not part of the return value from reduce; when running in parallel, such side effects easily cause race conditions and have no contract guaranteeing the expected execution count.

Instead, use the **return value from reduce** as the result:

~~~java
int sum = numbers.stream().reduce(0, Integer::sum);
~~~

With mutable elements, do not modify the source Collection inside the callback while iterating. This does not mean mutable objects cannot be processed, but if you want to update external state, design a separate API/action with a clear contract for threading, errors, and ordering.

## 6. Three-argument overload: reduce(identity, accumulator, combiner)

When the source has type `T` but the result has type `U`, use:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

The three components have different roles:

| Component | Parameters | Return value | Role |
| --- | --- | --- | --- |
| Identity | None | U | Empty/neutral aggregate |
| Accumulator | U, T | U | Merges one source element into the current result |
| Combiner | U, U | U | Merges two partial results |

When running in parallel, the framework can accumulate each partition independently and then use the combiner to merge the U aggregates.

### 6.1. Example: summing string lengths

~~~java
List<String> names = List.of("An", "Binh", "Chi");

int letterCount = names.parallelStream().reduce(
        0,
        (subtotal, name) -> subtotal + name.length(),
        Integer::sum);
// 9
~~~

This snippet requires `java.util.List`. Here `T=String`, `U=Integer`, identity is 0, the accumulator adds the length of one name, and the combiner adds two subtotals. The total is 2 + 4 + 3 = 9.

A style closer to the intent if you only need the total length:

~~~java
int letterCount = names.parallelStream()
        .mapToInt(String::length)
        .sum();
~~~

Learning the three-argument overload is necessary when the aggregated value has a different type from the source elements and there is no equivalent simple terminal operation.

### 6.2. The combiner must be compatible with the accumulator

It is not enough if `accumulator` produces the right result in a sequential pipeline while `combiner` discards part of the aggregate. The Javadoc states the compatibility condition:

~~~text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
~~~

for a matching aggregate result U and element T.

In addition, the combiner must be **associative**, the identity must be neutral for the combiner, and the functions must be stateless/non-interfering. If the combiner only returns the left parameter, the right-side work can be lost when the framework merges groups.

**Do not use a dummy combiner just to bypass a compilation error** with the intention that "I will only run sequentially." Your API may be called on a parallel Stream later; designing it properly from the start is safer.

## 7. Reducing into an immutable statistics record

Reduction can return an object containing **multiple metrics**, not just a single number.

Java 17 record example:

~~~java
record Stats(long orderCount, long totalAmount) {
    Stats combine(Stats other) {
        return new Stats(
                orderCount + other.orderCount,
                totalAmount + other.totalAmount);
    }
}
~~~

This is a **type** declaration, which must be placed inside a class or at a valid top-level scope. If each order has a `long amount()` method, we can create a `Stats` for each order:

~~~java
Stats stats = orders.parallelStream()
        .map(order -> new Stats(1, order.amount()))
        .reduce(new Stats(0, 0), Stats::combine);
~~~

- `Stats(0,0)` is the identity for adding two statistics.
- `Stats::combine` is the merge operation, adding the order count and total amount.
- The record is immutable at the level of its primitive components in the example. `combine` creates a **new** record rather than mutating a shared `Stats` object.
- Neither map nor reduce modifies the source Collection.
- With the sample data in section 9, the result is `Stats[orderCount=3, totalAmount=85000]`.

This is a sound example of **value-based reduction** for parallel Stream. Do not use a mutable `ArrayList` or `HashMap` object as a shared identity and mutate it in the accumulator: that style of reduction easily violates the reduce contract when partitioning.

## 8. How does reduce differ from collect?

**reduce**: a value aggregation operation where a new result is formed by an associative operator.

**collect**: a mutable reduction designed to build containers, allowing controlled accumulation (with supplier/accumulator/combiner or a Collector).

Counterexample to avoid:

~~~java
// DO NOT use parallel reduce like this:
// List<String> unsafe = words.parallelStream().reduce(
//     new ArrayList<String>(),
//     (list, word) -> { list.add(word); return list; },
//     (left, right) -> { left.addAll(right); return left; });
~~~

Here the mutable identity can be used as input to multiple reduction partitions; the accumulator mutates in place and loses safety in a parallel context. Having a combiner does not turn mutating a shared identity into a valid reduction.

If you want a new list:

~~~java
List<String> upper = words.parallelStream()
        .map(String::toUpperCase)
        .toList();
~~~

If you need a mutable list or a Map grouped by key, `collect(Collectors.toList())`, `collect(Collectors.groupingBy(...))`, or an appropriate Collector is usually better.

When you only need **counting/summing/finding min/max**, you should also consider `count()`, `sum()`, `min()`, and `max()`; using general-purpose reduce is not a goal in itself.

## 9. Complete Java 17 program and verified stdout

Create the file **StreamReduceDemo.java**. This standalone program demonstrates all three overloads with concrete data, the empty case, total amount, and a statistics object:

~~~java
import java.util.List;
import java.util.Optional;

public class StreamReduceDemo {
    record Order(String code, int quantity, long unitPrice) {
        long amount() { return quantity * unitPrice; }
    }

    record Stats(long orderCount, long totalAmount) {
        Stats combine(Stats other) {
            return new Stats(
                    orderCount + other.orderCount,
                    totalAmount + other.totalAmount);
        }
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(2, 3, 4);
        int sum = numbers.stream().reduce(0, Integer::sum);
        int product = numbers.stream().reduce(1, (a, b) -> a * b);
        Optional<Integer> largest = numbers.stream().reduce(Integer::max);
        int emptySum = List.<Integer>of().stream().reduce(0, Integer::sum);
        Optional<Integer> emptyMax = List.<Integer>of().stream().reduce(Integer::max);

        System.out.println("sum=" + sum);
        System.out.println("product=" + product);
        System.out.println("largest=" + largest.orElseThrow());
        System.out.println("empty sum=" + emptySum);
        System.out.println("empty max present=" + emptyMax.isPresent());

        List<Order> orders = List.of(
                new Order("A", 2, 15_000),
                new Order("B", 1, 25_000),
                new Order("C", 3, 10_000)
        );

        long total = orders.stream()
                .map(Order::amount)
                .reduce(0L, Long::sum);

        Stats stats = orders.parallelStream()
                .map(order -> new Stats(1, order.amount()))
                .reduce(new Stats(0, 0), Stats::combine);

        List<String> names = List.of("An", "Binh", "Chi");
        int letterCount = names.parallelStream().reduce(
                0,
                (subtotal, name) -> subtotal + name.length(),
                Integer::sum);

        System.out.println("total=" + total);
        System.out.println("stats=" + stats);
        System.out.println("letters=" + letterCount);
        System.out.println("parallel sum=" +
                numbers.parallelStream().reduce(0, Integer::sum));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac --release 17 StreamReduceDemo.java
java StreamReduceDemo
~~~

**Stdout verified through compilation and execution:**

~~~text
sum=9
product=24
largest=4
empty sum=0
empty max present=false
total=85000
stats=Stats[orderCount=3, totalAmount=85000]
letters=9
parallel sum=9
~~~

Explanation:

1. `sum=9` is 2+3+4, with identity 0.
2. `product=24` is 2×3×4, with identity 1.
3. `largest=4` shows that reduce without an identity returns a populated Optional.
4. `empty sum=0` and `empty max present=false` show the difference between the overload with an identity and the overload without an identity on an empty Stream.
5. `total=85000` because the three orders have amounts of 30,000, 25,000, and 30,000, respectively.
6. `stats=Stats[orderCount=3, totalAmount=85000]` shows two metrics aggregated into a new record.
7. `letters=9` because the lengths of An, Binh, and Chi are 2, 4, and 3.
8. `parallel sum=9` demonstrates addition with a proper identity and an associative combining operation.

Records are fully supported in Java 17; the snippets noted as **standalone illustrations** are not runnable standalone files, whereas `StreamReduceDemo.java` is a complete program.

## 10. Common reduce mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using identity 0 for multiplication | Product becomes 0 | Identity must be 1 |
| Using a non-neutral identity | Wrong result, especially when partitioned | Prove both identity equalities |
| Using subtraction as a parallel accumulator | Result depends on grouping | Choose an associative combining operation |
| Ignoring empty Optional from reduce without identity | Easy to assume a value is always present | Use `orElse...`/`orElseThrow...` meaningfully |
| Using null as the reduction result | Can cause NullPointerException | Design an appropriate value type |
| Mutating a mutable identity object | Fails in parallel, race conditions, or lost elements | Use collect or value-based reduce |
| Combiner returns one side and drops the other | Loses aggregates from some partitions | Merge both U results properly |
| Treating double addition as exact under any grouping | Rounding errors | Choose an appropriate algorithm and numeric type |
| Summing long/int that may overflow without checking | Domain-incorrect result | Choose a larger type / check for overflow |
| Using reduce in place of every terminal operation | Harder-to-read code, possible boxing | Use sum, count, max, min when appropriate |
| Reusing the same Stream after reduce | IllegalStateException or contract violation | Create a new Stream from the source |

### 10.1. Not every concatenation should be reduced manually

String concatenation example:

~~~java
String text = List.of("A", "B", "C").stream()
        .reduce("", String::concat);
// "ABC"
~~~

String concatenation is associative with respect to string order, but repeated `String::concat` can create many intermediate strings. For large lists or delimiters, `Collectors.joining(",")` is usually used instead of writing reduce manually.

### 10.2. Reduce is a terminal operation

After calling `reduce`, the Stream instance is consumed and cannot be reused to call `count()` or `toList()`. If the source is a Collection, create a new Stream when another computation is needed.

### 10.3. Parallel is not guaranteed to be faster

Splitting the source, accumulating, and combining multiple partial sums has overhead. For small datasets, `parallelStream().reduce(...)` can be slower than `stream().reduce(...)`. Before optimizing, ensure the operator satisfies the contract and measure with a representative benchmark rather than relying on intuition.

## 11. Checklist when designing a reduction operation

Check in order:

1. Should the result be **a single value** or a mutable container?
2. Is there a more expressive specialized terminal operation such as `sum`, `count`, `max`, or `min`?
3. Is there a truly neutral **identity**? If not, use the overload returning Optional.
4. Is the accumulator **associative**, **stateless**, and **non-interfering**?
5. If using the three-argument overload, does the combiner take and properly merge **two U results**?
6. Is `combiner(u, accumulator(identity,t))` compatible with `accumulator(u,t)`?
7. Is a mutable object being shared across computation partitions? If so, review it or switch to Collector.
8. What do an empty source, a single-element source, a multi-element source, and boundary data return?
9. Does the computation risk integer overflow or floating-point rounding error?
10. Can the pipeline run in parallel, and does actual performance justify using parallel?

## 12. Self-check exercises

**Exercise 1.** What does `List.of(5,6,7).stream().reduce(0,Integer::sum)` return? **Answer:** 18, because 0 is the identity for addition.

**Exercise 2.** What does `List.<Integer>of().stream().reduce(Integer::max)` return? **Answer:** `Optional.empty()`, because there is no maximum element.

**Exercise 3.** Why is `reduce(0,(a,b)->a*b)` invalid for computing a product? **Answer:** 0 is not the identity for multiplication; 1 is needed.

**Exercise 4.** In a `Stream<String>` reduced to `Integer`, what two types does the combiner receive? **Answer:** two aggregated Integers, not two Strings.

**Exercise 5.** If a subtraction `(a,b)->a-b` runs as expected on a sequential source, is it safe to enable parallel? **Answer:** no, because it is not associative.

**Exercise 6.** Can reduce be used with a `Stats(orderCount,totalAmount)` record? **Answer:** yes, if the identity and combine perform an associative merge of both fields without mutating shared state.

**Exercise 7.** Why should collect be used when building a mutable list? **Answer:** collectors are designed for mutable reduction; using reduce with an in-place mutated mutable identity easily violates the contract.

**Exercise 8.** Given three strings of lengths 2, 4, and 3, what does `reduce(0,(sum,s)->sum+s.length(),Integer::sum)` return? **Answer:** 9.

## 13. Official documentation

- [Java SE 17 — Stream.reduce and identity/associativity/combiner contracts](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).
- [Java SE 17 — BinaryOperator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/BinaryOperator.html).
- [Java SE 17 — BiFunction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/BiFunction.html).
- [Java SE 17 — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).
- [Java SE 17 — Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html).

**Conclusion:** `reduce` combines multiple elements into **a single result** using an operator with a clear contract. The overload with an identity returns the starting value if the Stream is empty; the overload without an identity returns `Optional<T>`; the three-argument overload supports a result type U different from the source type T and uses a combiner to merge partial results. Designing a proper reduction requires **a neutral identity, an associative combining operation, stateless/non-interfering functions, and transparent handling of empty sources**, especially when using parallel Stream.
