# Compatibility Requirements Between Accumulator and Combiner in Stream.reduce()

In the Java Stream API, **reduce** combines multiple elements into **a single aggregated result** according to rules provided by the programmer. The three-argument reduce form is especially useful when **the input element type T differs from the result type U**. However, to reduce data correctly in both sequential and parallel streams, you cannot simply pick an accumulator and combiner so that the code compiles: the two functions must be **algebraically compatible**, and the combiner must have an identity element and be associative.

If the accumulator processes an element with one meaning while the combiner merges group results with another meaning, the reduce operation may run sequentially and produce the right number, yet **a parallel stream can produce the wrong result or depend on how groups are split**. This is a logical bug that Java's generics system does not detect on its own.

This lesson explains the API signature, the formal compatibility equation, the role of identity and associativity, testing via simulated partitioning, counterexamples, immutable reduction, and when to switch to collect. The complete example uses Java 17+ and includes stdout verified by actual execution.

## 1. The three-argument reduce form

Signature in Stream<T>:

~~~java
<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
);
~~~

Where:

| Component | Type | Meaning |
| --- | --- | --- |
| **identity** | U | Initial/neutral value for partial reductions |
| **accumulator** | BiFunction<U, ? super T, U> | Accumulates an element T into a result U |
| **combiner** | BinaryOperator<U> | Merges two results U of already-reduced parts |
| **result** | U | Final aggregated value |

Example summing string lengths:

~~~java
List<String> words = List.of("Java", "Go", "Lambda", "API");

int totalLength = words.stream().reduce(
    0,
    (total, word) -> total + word.length(),
    Integer::sum
);
System.out.println(totalLength); // 15
~~~

Here T = String, U = Integer.

- **0** is the identity for Integer addition.
- **(total, word) -> total + word.length()** is the accumulator; it takes Integer and String, and returns Integer.
- **Integer::sum** is the combiner; it takes two Integers and returns Integer.

The three values have compatible signatures, but more importantly **they express the same computation**: the total length of all elements, whether elements are processed in a single group or multiple groups.

Standalone illustration snippets in this lesson need imports and to be placed inside a valid class/method; the complete program section contains full imports and a main method.

## 2. Three algebraic laws to follow

For the three-argument reduce, check:

1. **The identity is neutral with respect to the combiner.**
2. **The combiner is associative.**
3. **The accumulator is compatible with the combiner.**

In addition, callbacks provided to Stream must be **stateless** and **non-interfering** per the Stream processing contract: do not modify the source, and do not depend on shared mutable data in a way that causes results to differ across invocations.

### 2.1. Neutral identity

For any accumulated result u, a proper identity must not change the value when combined with u. You can visualize this as:

~~~text
combiner(identity, u) = u
combiner(u, identity) = u
~~~

Integer addition has identity 0. Multiplication has identity 1. String concatenation has the empty string as identity.

~~~java
BinaryOperator<Integer> combine = Integer::sum;
int identity = 0;

System.out.println(combine.apply(identity, 7)); // 7
System.out.println(combine.apply(7, identity)); // 7
~~~

Choose the identity according to the **combiner**, not an arbitrary value just because you want to add a fixed number to the sum.

### 2.2. Associative combiner

Associativity means changing the parenthesization when combining three results does not change the meaning of the result:

~~~text
combiner(combiner(a, b), c)
    =
combiner(a, combiner(b, c))
~~~

For addition:

~~~text
(2 + 3) + 4 = 2 + (3 + 4) = 9
~~~

For string concatenation:

~~~text
("A" + "B") + "C"
    =
"A" + ("B" + "C")
~~~

But subtraction is not associative:

~~~text
(9 - 4) - 2 = 3
9 - (4 - 2) = 7
~~~

Therefore, using subtraction as the combiner of an aggregation is usually inappropriate. Java allows you to write a lambda returning Integer, but **does not prove associativity for you**.

### 2.3. The compatibility equation: the most important requirement

The compatibility condition between accumulator and combiner is expressed as:

~~~text
combiner(u, accumulator(identity, t))
    =
accumulator(u, t)
~~~

Where u is a value of type U and t is an element of type T.

**Explanation of each side:**

- **accumulator(identity, t)**: processes element t alone in a partial reduction starting from identity.
- **combiner(u, accumulator(identity, t))**: merges the newly computed partial result with the existing partial result u.
- **accumulator(u, t)**: processes t directly into result u without creating a separate part.

Both ways must yield the same value under the contract of the computation.

Example of total length: u = 10, t = "Go", identity = 0.

~~~text
accumulator(0, "Go") = 2
combiner(10, 2) = 12
accumulator(10, "Go") = 12
~~~

Both sides equal 12. This means merging a partition containing only "Go" produces the exact same result as adding "Go" directly to the current total.

## 3. Why sequential and parallel can use two different merging strategies

To visualize, when sequentially reducing the four words Java, Go, Lambda, API, we can describe it as:

~~~text
0 + length("Java")   = 4
4 + length("Go")     = 6
6 + length("Lambda") = 12
12 + length("API")   = 15
~~~

In a parallel stream, the source **may** be split and processed locally:

~~~text
Part A: ["Java", "Go"]     -> 6
Part B: ["Lambda", "API"]  -> 9

Merge: combiner(6, 9)      -> 15
~~~

This is only an illustrative model; the JVM does not guarantee the exact split or the exact order of combiner calls shown in the diagram above. If the algebraic laws hold, changing how valid groups are split does not change the result.

**Do not think of a parallel stream as merely multiple threads concurrently modifying a single total variable.** It can produce results for individual parts and then combine those parts using the combiner. Therefore, a reduce operation that appears to work fine sequentially can still fail if the combiner is inconsistent.

## 4. Counterexample: adding accumulator but subtracting combiner

Suppose:

~~~java
List<String> words = List.of("Java", "Go");

int result = words.parallelStream().reduce(
    0,
    (total, word) -> total + word.length(),
    (left, right) -> left - right
);
~~~

The accumulator sums the lengths, while the combiner subtracts two partial sums. Both function signatures are valid, yet **the semantics are wrong**.

If all data is processed by a single reduction part:

~~~text
0 + 4 + 2 = 6
~~~

If split into two parts:

~~~text
partA = 0 + 4 = 4
partB = 0 + 2 = 2

wrongCombiner(partA, partB) = 4 - 2 = 2
~~~

The result 2 differs from 6. You should not run parallel repeatedly hoping to "accidentally" observe 2; **simulating the partitioning yourself** already proves the incompatibility.

Testing the equation with u = 4, t = "Go":

~~~text
combiner(4, accumulator(0, "Go")) = 4 - 2 = 2
accumulator(4, "Go")              = 4 + 2 = 6
~~~

Since the two sides are not equal, the triple is broken.

**Fix with a proper combiner:**

~~~java
int correct = words.parallelStream().reduce(
    0,
    (total, word) -> total + word.length(),
    Integer::sum
);
~~~

When using addition in both the accumulator and the combiner, the result of the two partitions is 4 + 2 = 6.

## 5. Counterexample: non-neutral identity

This snippet appears to add 10 to the total length:

~~~java
int value = List.of("Java", "Go").stream().reduce(
    10,
    (total, word) -> total + word.length(),
    Integer::sum
);
~~~

For the sequential reduction pass in the example, the value is:

~~~text
10 + 4 + 2 = 16
~~~

However, when the source is split into two separate parts, each part may start from identity = 10:

~~~text
partA = 10 + 4 = 14
partB = 10 + 2 = 12
combined = 14 + 12 = 26
~~~

**Identity 10 is not neutral for addition**, because combiner(10, u) = 10 + u, which does not equal u. The discrepancy between 16 and 26 is not a Java bug, but the result of invalid reduce arguments.

To add a base offset of 10 exactly **once**, use identity 0 to reduce and add 10 afterward:

~~~java
int result = 10 + words.parallelStream().reduce(
    0,
    (total, word) -> total + word.length(),
    Integer::sum
);
~~~

When the data is split into multiple parts, each part uses the valid identity 0, and the base value is added only to the final sum.

## 6. Different T and U can still be compatible

The compatibility condition **does not require the accumulator and combiner to have the same signature**, because they have different responsibilities.

For Stream<String> reduced to Integer:

~~~java
int total = words.stream().reduce(
    0,
    (sum, word) -> sum + word.length(),
    Integer::sum
);
~~~

The accumulator takes Integer and String; the combiner takes two Integers. They perform different operations on their arguments, yet are compatible with respect to the "total length" result.

Another example: Stream<Integer> reduced to Long:

~~~java
long total = numbers.parallelStream().reduce(
    0L,
    (sum, number) -> sum + number.longValue(),
    Long::sum
);
~~~

Here T is Integer and U is Long. Using Long reduces the risk of int overflow for large sums, though long still has limits. If values outside the long range can occur, you need to design another appropriate numeric type or overflow check.

### 6.1. Formatted string concatenation

~~~java
String labels = words.parallelStream().reduce(
    "",
    (result, word) -> result + "[" + word + "]",
    String::concat
);
~~~

The output is a string of labels "[Java][Go]..." in the appropriate encounter order. The identity is the empty string. The accumulator turns word into a formatted segment and appends it; the combiner concatenates two completed segments.

Key point: **compatibility does not mean "the operations look the same"**. It means that adding an element and merging partitions express **the exact same aggregation**.

## 7. Associativity is different from commutativity

An operation can be associative without being commutative.

String concatenation is associative:

~~~text
("A" + "B") + "C" = "A" + ("B" + "C")
~~~

But not commutative:

~~~text
"A" + "B" = "AB"
"B" + "A" = "BA"
~~~

Parallel reduction does not require every combiner to be commutative. However, if the result depends on element order, **the encounter order of the source and operations** must match the business requirement.

With an ordered stream, compatible String concatenation can produce results in source order. With an unordered source, you should not assume the resulting string has a single fixed order.

### 7.1. Subtraction and division are unsuitable when regrouping

~~~text
(10 - 5) - 2 = 3
10 - (5 - 2) = 7
~~~

If the requirement is to take an initial number and subtract the **sum** of the elements, compute the sum using associative addition and subtract once:

~~~java
int result = initial - numbers.stream()
    .mapToInt(Integer::intValue)
    .sum();
~~~

If the requirement is an algorithm that **strictly depends on step-by-step order**, a sequential loop with controlled state may be clearer and more faithful to the contract than forcing it into a parallel reduce.

### 7.2. Floating-point is not strictly associative

Addition on double/float has rounding errors. Under floating-point arithmetic, two parenthesizations can produce slightly different numbers:

~~~text
(a + b) + c
a + (b + c)
~~~

Different groupings in parallel reduction can change the addition order and the observed error. Do not write tests for double sums requiring bit-for-bit equality across all execution strategies if the data is order-sensitive. For monetary domains, consider BigDecimal with an explicit precision/rounding policy or an appropriate smallest-unit integer.

For int/long addition, overflow can make the value mathematically incorrect; check bounds and use Math.addExact when overflow is not permitted.

## 8. Do not let the accumulator or combiner modify the source or global state

The Stream contract requires behavioral parameters to be non-interfering and stateless. Do not modify the Collection being traversed from inside a callback:

~~~java
// WRONG: source is a mutable collection currently being traversed by the Stream.
source.parallelStream().reduce(
    0,
    (sum, value) -> {
        source.add(value);
        return sum + 1;
    },
    Integer::sum
);
~~~

This snippet intentionally illustrates an error and requires source to be declared in a real context. Consequences can include unexpected mutations, ConcurrentModificationException, or unreliable results.

Similarly, an external counter does not become pure just by using AtomicInteger:

~~~java
AtomicInteger counter = new AtomicInteger();

int result = values.parallelStream().reduce(
    0,
    (sum, value) -> sum + value + counter.incrementAndGet(),
    Integer::sum
);
~~~

The number of invocations, ordering, and thread scheduling can alter the result. AtomicInteger only solves atomic increment, not algebraic compatibility.

Let the value U hold **the result state to be computed**, instead of relying on mutable global variables.

## 9. Do not use a mutable identity with reduce

A well-known mistake is using a StringBuilder as the identity and mutating it in place:

~~~java
// WRONG: mutable identity, accumulator/combiner mutate the object.
StringBuilder text = words.parallelStream().reduce(
    new StringBuilder(),
    (builder, word) -> builder.append(word),
    (left, right) -> left.append(right)
);
~~~

Although Java allows this to compile, it is not an immutable-value reduction: it uses the same mutable identity object and mutates it across branches. With a parallel stream, this can cause data races, duplicated data, or incorrect ordering.

**This is not properly fixed just by adding synchronized.** The issue also lies in the reduction contract, aliasing, and the fact that the same mutable container can be merged with itself.

### 9.1. Approach 1: reduce with immutable values

~~~java
String joined = words.stream().reduce(
    "",
    (result, word) -> result + word,
    String::concat
);
~~~

String is immutable; each concatenation returns a new String value, which is algebraically sound. However, repeated String concatenation can incur significant copying overhead on large data.

### 9.2. Approach 2: collect with a mutable container

~~~java
String joined = words.parallelStream().collect(
    StringBuilder::new,
    (builder, word) -> builder.append(word),
    StringBuilder::append
).toString();
~~~

Stream.collect(supplier, accumulator, combiner) is designed for **mutable reduction**. The supplier creates a container per part, the accumulator adds an element to a container, and the combiner merges containers. Do not return the same static StringBuilder from the supplier for all branches.

Differences in types:

| Operation | Accumulator | Combiner | Usage |
| --- | --- | --- | --- |
| Three-argument reduce | BiFunction<U,T,U> | BinaryOperator<U> | Produces a U value from result and element |
| Three-argument collect | BiConsumer<R,T> | BiConsumer<R,R> | Mutates container R created by supplier |
| Two-argument reduce | BinaryOperator<T> | Same operator used in reduction | Accumulates elements of the same type T |

With collect, you must follow the supplier/accumulator/combiner contract and ensure non-interference with the source. A **per-group** mutable container is a different concept from a shared mutable identity in reduce.

## 10. Checking the three laws with small code snippets

### 10.1. Identity

~~~java
int identity = 0;
BinaryOperator<Integer> combiner = Integer::sum;
int u = 7;

System.out.println(combiner.apply(identity, u) == u); // true
System.out.println(combiner.apply(u, identity) == u); // true
~~~

### 10.2. Associativity

~~~java
int a = 3, b = 4, c = 5;
int left = combiner.apply(combiner.apply(a, b), c);
int right = combiner.apply(a, combiner.apply(b, c));
System.out.println(left == right); // true
~~~

### 10.3. Compatibility

~~~java
BiFunction<Integer, String, Integer> accumulator =
    (sum, word) -> sum + word.length();

int u = 10;
String t = "Go";

int left = combiner.apply(
    u, accumulator.apply(identity, t));
int right = accumulator.apply(u, t);

System.out.println(left == right); // true
~~~

Testing a few values makes the rules clear to read, **but does not prove the laws hold for all inputs**. For critical code, use property-based testing to check many values, empty inputs, boundary values, relevant order variations, and different partitions.

### 10.4. Simulated partition testing

~~~java
int partA = List.of("Java").stream()
    .reduce(0, accumulator, combiner);
int partB = List.of("Go").stream()
    .reduce(0, accumulator, combiner);

int combined = combiner.apply(partA, partB);
System.out.println(combined); // 6
~~~

If subtraction is used to merge partA and partB, combined = 2, which differs from the sequential reduction 6. This testing approach reproduces the bug **independently of thread count**, helping detect mismatches even when the current machine schedules parallel execution differently.

## 11. Complete Java 17+ program

The following exercise executes both valid operations and invalid counterexamples **with deterministic results**. The code uses two simulated parts to demonstrate combiner/identity bugs without requiring Java's parallel stream to happen to split in a specific way.

Create the file **ReduceCompatibilityDemo.java**:

~~~java
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.BinaryOperator;
import java.util.stream.IntStream;

public class ReduceCompatibilityDemo {
    static int totalLength(List<String> words, boolean parallel) {
        var source = parallel ? words.parallelStream() : words.stream();
        return source.reduce(
            0,
            (total, word) -> total + word.length(),
            Integer::sum
        );
    }

    public static void main(String[] args) {
        List<String> words = List.of("Java", "Go", "Lambda", "API");
        BiFunction<Integer, String, Integer> accumulator =
            (total, word) -> total + word.length();
        BinaryOperator<Integer> combiner = Integer::sum;
        int identity = 0;

        int u = 10;
        String t = "Go";
        int left = combiner.apply(u, accumulator.apply(identity, t));
        int right = accumulator.apply(u, t);
        System.out.println("compatibility=" + (left == right));
        System.out.println("sequential=" + totalLength(words, false));
        System.out.println("parallel=" + totalLength(words, true));

        int partA = List.of("Java").stream()
            .reduce(0, accumulator, combiner);
        int partB = List.of("Go").stream()
            .reduce(0, accumulator, combiner);
        System.out.println("correct-merge=" + combiner.apply(partA, partB));
        System.out.println("wrong-merge=" + (partA - partB));

        int wrongIdentitySequential = List.of("Java", "Go").stream()
            .reduce(10, accumulator, combiner);
        int wrongIdentitySplit =
            (10 + "Java".length()) + (10 + "Go".length());
        System.out.println("wrong-identity-sequential=" +
            wrongIdentitySequential);
        System.out.println("wrong-identity-split=" + wrongIdentitySplit);

        String labels = words.parallelStream().reduce(
            "",
            (text, word) -> text + "[" + word + "]",
            String::concat
        );
        System.out.println("labels=" + labels);

        long sum = IntStream.rangeClosed(1, 1_000)
            .boxed().parallel()
            .reduce(0L, (total, number) -> total + number, Long::sum);
        System.out.println("sum1000=" + sum);

        String joined = words.parallelStream().collect(
            StringBuilder::new,
            (builder, word) -> builder.append(word),
            StringBuilder::append
        ).toString();
        System.out.println("collected=" + joined);
    }
}
~~~

Compile and run commands with JDK 17 or later:

~~~bash
javac ReduceCompatibilityDemo.java
java ReduceCompatibilityDemo
~~~

**Exact stdout:**

~~~text
compatibility=true
sequential=15
parallel=15
correct-merge=6
wrong-merge=2
wrong-identity-sequential=16
wrong-identity-split=26
labels=[Java][Go][Lambda][API]
sum1000=500500
collected=JavaGoLambdaAPI
~~~

Explanation:

- **compatibility=true:** both sides of the equation with u=10, t="Go" equal 12.
- **sequential=15** and **parallel=15:** the sum of the four lengths 4+2+6+3 is correct in both processing modes.
- **correct-merge=6:** merges two independent partitions using addition.
- **wrong-merge=2:** merges the same two partitions using subtraction; this is an intentionally illustrated wrong result.
- **wrong-identity-sequential=16:** a single addition pass starting from 10, then adding 4 and 2.
- **wrong-identity-split=26:** each partition starts from 10, then the results 14 and 12 are added together.
- **labels:** immutable String with empty identity and concat combiner suitable for joining labels of an ordered stream.
- **sum1000=500500:** reduces 1000 Integers into a Long, giving the sum 1+2+...+1000.
- **collected:** uses collect and StringBuilder to accumulate strings via a container instead of mutating the reduce identity.

In the example, the invalid paths are simulated explicitly, **rather than running an invalid parallel reduce and claiming stdout will always be 2 or 26**. This is a presentation style that can be tested deterministically on JDK 17.

## 12. How do one- and two-argument reduce relate?

Stream also has overloads:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator);
Optional<T> reduce(BinaryOperator<T> accumulator);
~~~

The two-argument form works with **T as both the source element and the accumulated result**, using a single BinaryOperator to reduce. The form without identity returns Optional<T> because there may be no elements.

~~~java
int sum = Stream.of(2, 3, 4)
    .reduce(0, Integer::sum);
~~~

With three arguments, when T and U differ, we separate the role of adding an element T to U from the role of merging two U results. The two functions must agree with each other through the compatibility equation. The other overloads must still obey their respective identity/associativity laws to be used correctly.

## 13. Choosing the right type U and considering other APIs

### 13.1. Counting elements only

~~~java
long count = words.parallelStream().reduce(
    0L,
    (total, word) -> total + 1L,
    Long::sum
);
~~~

This approach can be algebraically valid, but **Stream.count()** expresses the intent more concisely and can sometimes be optimized better.

### 13.2. Summing lengths only

~~~java
long total = words.stream()
    .mapToLong(String::length)
    .sum();
~~~

This approach is usually simpler than three-argument reduce when the goal is purely a numeric sum, and avoids some boxing of intermediate results.

### 13.3. Multiple statistics in one result U

An immutable record can be used:

~~~java
record Summary(long count, long length) {}

Summary result = words.parallelStream().reduce(
    new Summary(0, 0),
    (summary, word) -> new Summary(
        summary.count() + 1,
        summary.length() + word.length()
    ),
    (left, right) -> new Summary(
        left.count() + right.count(),
        left.length() + right.length()
    )
);
~~~

The identity is (0,0). The accumulator adds one element: count+1, length+word.length. The combiner sums the corresponding fields of two Summary instances. The compatibility equation holds component-wise if there are no arithmetic errors.

However, creating a new record for every element can incur significant allocation on very large datasets. If performance is needed, you can use a properly designed mutable collector or an appropriate standard statistics utility, after measuring.

## 14. Common mistakes

**Mistake 1 — combiner has a different meaning from accumulator:** an adding accumulator with a subtracting combiner may compile and run fine sequentially, but fails when partitioned.

**Mistake 2 — non-neutral identity:** each partition may apply the identity again, causing the offset to be counted multiple times.

**Mistake 3 — non-associative operator:** subtraction, division, and order-dependent steps are unsuitable for arbitrary regrouping.

**Mistake 4 — confusing T with U:** when reducing Stream<String> to Integer, the combiner must merge two Integers, not two Strings.

**Mistake 5 — testing only sequentially:** the combiner may be called rarely or not at all in sequential execution; test multiple ways of splitting and merging.

**Mistake 6 — using a mutable identity in reduce:** sharing the same StringBuilder/ArrayList breaks the reduction model. Use an immutable U or collect.

**Mistake 7 — side effects in the accumulator:** do not modify the source Collection, global variables, or databases from callbacks when the number of invocations is not guaranteed.

**Mistake 8 — assuming associative means commutative:** String concatenation is associative but not commutative; you still need to care about encounter order.

**Mistake 9 — forgetting floating-point arithmetic:** the order of double additions can cause rounding discrepancies; test tolerances according to requirements.

**Mistake 10 — using large-scale String concatenation without considering performance:** being algebraically valid does not mean optimal execution; consider Collectors.joining or StringBuilder in collect.

**Mistake 11 — using reduce for every aggregation:** count, mapToLong().sum(), min/max, and collect can be clearer.

**Mistake 12 — assuming a fixed parallel schedule:** do not rely on thread count or how many times the combiner runs to prove correctness.

**Mistake 13 — ignoring overflow and null values:** out-of-range values, null elements, or exceptions prevent the pipeline from meeting its business contract.

**Mistake 14 — treating type-checking as proof of reduction:** the compiler checks signatures, not identity, associativity, or compatibility.

## 15. Three-argument reduce review checklist

| Question | Check |
| --- | --- |
| What are T and U? | T is the input element; U is the aggregated value |
| Is identity valid? | Combining with identity does not change U |
| Is combiner associative? | Grouping with both parenthesizations yields the same meaning |
| Is accumulator compatible? | combiner(u, accumulator(identity,t)) = accumulator(u,t) |
| Any identity mutation? | Do not mutate a shared U object; use collect if needed |
| Modifies source or global state? | Callbacks are stateless and non-interfering |
| Does result depend on order? | Check encounter order and the operation |
| Any rounding error or overflow? | Verify numeric type, precision, and bounds |
| Tested multiple partitions? | Compare sequential, parallel, and simulated group merging |
| Is there a better-fitting API? | count, sum, collect, or another collector |

## 16. Self-check questions

1. Why does accumulator take U and T while combiner takes U and U?
2. Interpret both sides of the compatibility equation using total string length.
3. Why is summing lengths compatible with Integer::sum?
4. Why is identity=10 wrong when the combiner is addition?
5. Why can an adding accumulator with a subtracting combiner compile yet still be wrong?
6. How can you simulate two partitions for testing without depending on parallel stream scheduling?
7. How do associativity and commutativity differ?
8. Why is a mutable StringBuilder better suited for collect than reduce?
9. When should you use mapToLong(...).sum() instead of three-argument reduce?
10. For a record Summary(count,length), what identity, accumulator, and combiner could you use?
11. Why does synchronized not by itself fix the mutable identity problem?
12. Why can a double sum change slightly when split into groups?
13. Why must callbacks not modify the Collection currently being processed?
14. If you switch a sequential stream to parallel, which contracts will you check?

**Conclusion:** For Stream.reduce(identity, accumulator, combiner), **processing an element directly with the accumulator must be equivalent to processing the element in its own partition and then merging via the combiner**. To guarantee this, you need a neutral identity, an associative combiner, and a valid compatibility equation, while keeping callbacks non-interfering with the source and free of reliance on shared state. When you need to build a mutable container, use collect or a Collector with the appropriate contract.