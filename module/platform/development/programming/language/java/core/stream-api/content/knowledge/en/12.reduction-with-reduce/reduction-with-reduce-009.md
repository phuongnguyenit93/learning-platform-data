# Verifying Reductions on Empty Sources and Parallel Pipelines

## 1. Lesson goals

In the **Java Stream API**, a *reduction* combines multiple elements into a single result: a total amount, a product of quantities, a maximum score, a joined string, or a statistical value. The `reduce` method is a **terminal operation**, ending a pipeline that may include lazy steps such as `filter` and `map`.

Writing a `reduce` that works for a sequential stream is **not enough** to claim it is correct. There are two cases where bugs easily surface:

- **Empty source:** the result must be sensibly defined when there are no elements, including when data is completely filtered out by `filter`.
- **Parallel pipeline:** Java can split the source into multiple parts, reduce each part, and use `combiner` to merge the results. An operation dependent on parenthesization order or using a wrong `identity` can return a different result.

This lesson belongs to the **Reduction with reduce** chapter of the **`JAVA_STREAM_API`** module. It provides foundational knowledge for learning `collect`, grouping, custom collectors, `Spliterator`, and parallel processing, while identifying limits related to state, resources, and performance.

After this lesson, you will be able to:

1. Distinguish the three overloads of `Stream.reduce` and the `reduce` forms of primitive streams.
2. Verify results on an empty stream and a single-element stream.
3. Determine the **identity** (neutral element), **associativity**, and compatibility condition between `accumulator` and `combiner`.
4. Explain why summing or `max` works correctly in parallel, whereas subtraction or adding with a wrong identity does not.
5. Write runnable verifications in Java 8, comparing sequential and parallel results without relying on log order or lambda invocation count.

## 2. Reduction mechanism: from a sequence of elements to a single value

Consider summing integers:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> so = Arrays.asList(2, 4, 6, 8);

int tong = so.stream()
    .reduce(0, Integer::sum);

System.out.println(tong); // 20
```

In the pipeline above:

- `0` is the **identity**, the starting value and neutral element of addition.
- `Integer::sum` is the **accumulator**, adding the current result with the next element.
- `reduce` is a terminal operation, returning `int` after completing the combining operation.

On a sequential stream, you can visualize the calculation:

```text
seed = 0
0 + 2 = 2
2 + 4 = 6
6 + 6 = 12
12 + 8 = 20
```

Yet with a parallel stream, the implementation can perform the equivalent:

```text
          [2, 4, 6, 8]
            /       \
         [2, 4]    [6, 8]
           │          │
          6          14
            \        /
             6 + 14
                │
               20
```

**There is no guarantee the JVM always chooses the exact split shown in the diagram.** What must be guaranteed is that when the operation meets `reduce`'s contract, how elements are grouped does not alter the logical result.

## 3. Three overloads of `Stream.reduce`

### 3.1. Without providing identity: returns `Optional<T>`

Concise signature:

```java
Optional<T> reduce(BinaryOperator<T> accumulator);
```

Example:

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<Integer> tong = Stream.of(2, 4, 6)
    .reduce(Integer::sum);

System.out.println(tong.orElse(-1)); // 12
```

The operation uses the first element as the initial accumulated value. If the stream is **empty**, there is no element to start from, so the result is `Optional.empty()`.

### 3.2. With identity of the same element type: returns `T`

Signature:

```java
T reduce(T identity, BinaryOperator<T> accumulator);
```

Example:

```java
int tong = Stream.of(2, 4, 6)
    .reduce(0, Integer::sum);

System.out.println(tong); // 12
```

When there are no elements, the reduction returns **identity**. The identity must fit the operation and, in parallel processing, must be a true identity element.

### 3.3. With identity and a different result type: returns `U`

Signature:

```java
<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
);
```

Here:

- `T` is the stream element type.
- `U` is the accumulated result type, which can differ from `T`.
- `accumulator` combines a `U` result with a `T` element to create a new `U`.
- `combiner` merges **two** accumulated `U` results, especially important in parallel processing.

Example of total character count across multiple strings:

```java
import java.util.Arrays;
import java.util.List;

List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

int tongKyTu = ten.stream()
    .reduce(
        0,
        (soKyTu, chuoi) -> soKyTu + chuoi.length(),
        Integer::sum
    );

System.out.println(tongKyTu); // 12
```

The source has type `Stream<String>` while the result is `Integer`. In this example, accumulated results are character counts, so the combiner adds them together.

When only total length is needed, the specialized form `ten.stream().mapToInt(String::length).sum()` is usually easier to read. The three-parameter overload is helpful for understanding the contract when input and accumulation types differ.

### 3.4. `reduce` on primitive streams

`IntStream`, `LongStream`, and `DoubleStream` have two common forms:

```java
// IntStream
int reduce(int identity, IntBinaryOperator op);
OptionalInt reduce(IntBinaryOperator op);

// Similarly: LongStream → long / OptionalLong
//            DoubleStream → double / OptionalDouble
```

Example:

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;

int tongCoIdentity = IntStream.of(2, 4, 6)
    .reduce(0, Integer::sum);

OptionalInt tongKhongIdentity = IntStream.of(2, 4, 6)
    .reduce(Integer::sum);

System.out.println(tongCoIdentity);              // 12
System.out.println(tongKhongIdentity.orElse(-1)); // 12
```

Using a primitive stream avoids boxing `int` into `Integer` for ordinary arithmetic. It does not change the algebraic requirements of the reduction.

## 4. Verifying on empty sources

**An empty source is a mandatory test case.** A source may start empty or become empty after `filter`:

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<Integer> khongIdentity = Stream.<Integer>empty()
    .reduce(Integer::sum);

int coIdentity = Stream.<Integer>empty()
    .reduce(0, Integer::sum);

System.out.println(khongIdentity.isPresent()); // false
System.out.println(coIdentity);                 // 0
```

Result table:

| Pipeline on empty source | Return type | Result |
| --- | --- | --- |
| `Stream.<Integer>empty().reduce(Integer::sum)` | `Optional<Integer>` | `Optional.empty()` |
| `Stream.<Integer>empty().reduce(0, Integer::sum)` | `Integer` | `0` |
| `IntStream.empty().reduce(Integer::sum)` | `OptionalInt` | `OptionalInt.empty()` |
| `IntStream.empty().reduce(0, Integer::sum)` | `int` | `0` |
| `LongStream.empty().reduce(1L, (a, b) -> a * b)` | `long` | `1L` |
| `Stream.<String>empty().reduce("", String::concat)` | `String` | `""` |
| `Stream.<String>empty().reduce(0, (n, s) -> n + s.length(), Integer::sum)` | `Integer` | `0` |

**Never automatically interpret a result of `0` as "data present".** For addition, `0` is a valid identity element, so it does not carry enough information to distinguish empty from an actual sum of 0.

If business logic needs to distinguish the two states, use the overload returning `Optional` or check data appropriately:

```java
Optional<Integer> tong = Stream.<Integer>empty()
    .reduce(Integer::sum);

if (tong.isPresent()) {
    System.out.println("Data present, sum = " + tong.get());
} else {
    System.out.println("No data yet");
}
```

You can replace `get()` with `orElse` or `orElseThrow` depending on the application contract.

### 4.1. Empty case after a filter

```java
List<Integer> diem = Arrays.asList(3, 4, 5);

Optional<Integer> tongDiemDat = diem.stream()
    .filter(d -> d >= 6)
    .reduce(Integer::sum);

System.out.println(tongDiemDat.isPresent()); // false
```

Although the initial source is non-empty, after the filter there are no elements. Therefore, check the output **after the entire pipeline**, not just `list.isEmpty()` on the source.

## 5. Identity element must match the operation

For a binary operation `op`, an identity `e` must satisfy:

```text
op(e, x) == x
op(x, e) == x
```

for every valid value `x` in the operation's domain. This is a **two-sided** identity element, enabling results from separate groups to merge accurately.

| Reduction | Reasonable identity | Why |
| --- | --- | --- |
| Integer addition | `0` | `0 + x = x + 0 = x` |
| Integer multiplication | `1` | `1 * x = x * 1 = x` |
| String concatenation | `""` | `"" + x = x + "" = x` |
| Maximum over all `int` | `Integer.MIN_VALUE` | `max(MIN_VALUE, x) = x` |
| Minimum over all `int` | `Integer.MAX_VALUE` | `min(MAX_VALUE, x) = x` |
| Boolean AND | `true` | `true && x = x` |
| Boolean OR | `false` | `false || x = x` |

Choosing the right identity **must fit the data domain and result contract**. For `max`, if the source is empty and you need to know "there is no maximum value", `IntStream.max()` returning `OptionalInt` is usually more sensible than `reduce(Integer.MIN_VALUE, Math::max)`.

### 5.1. Wrong identity: the bug may only surface in parallel execution

```java
List<Integer> so = Arrays.asList(1, 2, 3);

// WRONG: 10 is not the identity of addition.
int sai = so.stream().reduce(10, Integer::sum);

System.out.println(sai); // 16, instead of the true sum 6
```

In a parallel stream, the identity can be used for multiple groups. If each group adds `10`, the final result can be wrong in a different way. **Do not rely on a specific number of groups** because the source-splitting strategy depends on the implementation.

Correct:

```java
int tong = so.parallelStream()
    .reduce(0, Integer::sum);

System.out.println(tong); // 6
```

Another example: if you try to find the largest number over the entire integer domain with `reduce(0, Math::max)`, all-negative data yields the wrong result:

```java
int sai = java.util.stream.IntStream.of(-9, -4, -7)
    .reduce(0, Math::max);

System.out.println(sai); // 0; not -4

int dung = java.util.stream.IntStream.of(-9, -4, -7)
    .max()
    .orElseThrow(() -> new IllegalStateException("Empty source"));

System.out.println(dung); // -4
```

The `max()` form both has clear semantics and handles an empty source explicitly.

## 6. Associativity determines parallelizability

An operation `op` is associative when:

```text
op(op(a, b), c) == op(a, op(b, c))
```

In the **non-overflowing** integer addition example, changing parenthesization does not change the result:

```text
(2 + 4) + 6 = 2 + (4 + 6) = 12
```

Therefore, addition with identity `0` fits parallel `reduce` within an arithmetic domain having deterministic results.

### 6.1. Subtraction is not associative

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Hence, this is an unsafe reduction when expecting identical results between sequential and parallel execution:

```java
List<Integer> so = Arrays.asList(1, 2, 3, 4);

int tuanTu = so.stream()
    .reduce(0, (a, b) -> a - b);

int songSong = so.parallelStream()
    .reduce(0, (a, b) -> a - b);

System.out.println(tuanTu); // -10
System.out.println(songSong); // No common result guaranteed
```

One run might happen to match expectations; that **does not prove** the reduction is valid. You must check the associativity law rather than just observing a few outputs.

### 6.2. Associativity does not imply commutativity

String concatenation is associative:

```text
("A" + "B") + "C" == "A" + ("B" + "C") == "ABC"
```

Yet not commutative: `"A" + "B"` differs from `"B" + "A"`. With an **ordered source**, a valid `reduce` using string concatenation still preserves the result in encounter order, even when executed in parallel.

```java
import java.util.Arrays;

List<String> chu = Arrays.asList("A", "B", "C");

String tuanTu = chu.stream().reduce("", String::concat);
String songSong = chu.parallelStream().reduce("", String::concat);

System.out.println(tuanTu);  // ABC
System.out.println(songSong); // ABC
```

Repeated string concatenation is often inefficient because it creates many `String` objects. For collecting strings, `Collectors.joining()` is usually more appropriate. Do not rely on log output order or lambda execution order to infer result order.

## 7. Three-parameter overload: verifying accumulator and combiner

With `Stream<T>.reduce(U identity, accumulator, combiner)`, **all three** conditions must hold:

1. **Identity is neutral for combiner:** `combiner(identity, u) == u` (and the other direction, if the combining operation requires a two-sided identity).
2. **Combiner is associative:** groups can be merged in multiple ways while still obtaining an equivalent result.
3. **Accumulator is compatible with combiner:** for every valid accumulated `u` and element `t`:

```text
combiner(u, accumulator(identity, t))
    == accumulator(u, t)
```

Correct example — summing string lengths:

```java
import java.util.Arrays;
import java.util.List;

List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

int tongTuanTu = ten.stream()
    .reduce(
        0,
        (n, s) -> n + s.length(),
        Integer::sum
    );

int tongSongSong = ten.parallelStream()
    .reduce(
        0,
        (n, s) -> n + s.length(),
        Integer::sum
    );

System.out.println(tongTuanTu);  // 12
System.out.println(tongSongSong); // 12
```

Because `accumulator(0, "Go") = 2`, then `combiner(u, 2) = u + 2`, matching `accumulator(u, "Go") = u + 2`. Similarly for every other string.

### 7.1. A wrong combiner can be hidden in sequential mode

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

// WRONG: combiner subtracts two partial sums.
int sai = ten.parallelStream()
    .reduce(
        0,
        (n, s) -> n + s.length(),
        (a, b) -> a - b
    );
```

In sequential mode, the combiner may not be called, so testing `ten.stream()` alone is not enough to expose the bug. In parallel mode, the combiner can be used to merge results; subtraction fails the contract.

Fix it with `Integer::sum` or, when you only need to count characters, use:

```java
int tong = ten.parallelStream()
    .mapToInt(String::length)
    .sum();
```

## 8. Why does an identity containing a prefix easily yield wrong results?

Suppose you want to concatenate labels with the prefix "Code: ":

```java
List<String> ma = Arrays.asList("A", "B", "C");

// WRONG for parallel reduce: "Code: " is not the identity of concat.
String ketQua = ma.parallelStream()
    .reduce("Code: ", String::concat);
```

In sequential mode, you might see `"Code: ABC"`. In parallel processing, if each branch starts with `"Code: "`, the prefix can appear multiple times. The right way: use identity `""` and prepend the prefix **once** after the reduction.

```java
String maGhep = ma.parallelStream()
    .reduce("", String::concat);

String ketQua = "Code: " + maGhep;
System.out.println(ketQua); // Code: ABC
```

When processing many strings, using a dedicated collector is usually more sensible:

```java
import java.util.stream.Collectors;

String ketQua = ma.parallelStream()
    .collect(Collectors.joining("", "Code: ", ""));

System.out.println(ketQua); // Code: ABC
```

This is an example of the boundary between `reduce` and `collect`: a collector is designed to accumulate into an appropriate structure, whereas `reduce` requires accumulated values to satisfy associativity and identity laws.

## 9. Do not mutate a shared accumulation object inside `reduce`

An anti-pattern is using a mutable object such as `ArrayList` as the identity and adding elements to it directly:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

// DO NOT USE, especially with parallelStream().
List<Integer> sai = Arrays.asList(1, 2, 3, 4)
    .parallelStream()
    .reduce(
        new ArrayList<Integer>(),
        (list, n) -> {
            list.add(n); // Mutates the accumulation object itself.
            return list;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
```

The problem: the identity is a single reference that may be used in multiple branches; `add` and `addAll` mutate state, which can cause race conditions, duplicated elements, wrong results, or runtime errors. Reduction does not guarantee creating a fresh copy of the identity for each branch.

If you need to collect multiple elements into a list, use `collect`:

```java
import java.util.stream.Collectors;

List<Integer> dung = Arrays.asList(1, 2, 3, 4)
    .parallelStream()
    .collect(Collectors.toList());

System.out.println(dung); // [1, 2, 3, 4]
```

A collector has a `supplier` mechanism to create an appropriate accumulation container per segment when needed and a `combiner` to merge them. Using a contract-compliant collector lowers the risk of unintended shared state.

Also avoid incrementing an external counter inside `accumulator`:

```java
// DO NOT USE: side effect on external state.
java.util.concurrent.atomic.AtomicInteger soLanGoi =
    new java.util.concurrent.atomic.AtomicInteger();

int tong = Arrays.asList(1, 2, 3).parallelStream()
    .reduce(0, (a, b) -> {
        soLanGoi.incrementAndGet();
        return a + b;
    });
```

Although `AtomicInteger` can update concurrently without data races, the lambda invocation count is an execution detail, not the business definition of a sum. Compute the count with `count()` if you truly need to count elements.

## 10. Verifying correctness with targeted tests

Several simple test cases are very helpful:

| Test case | Data | What to verify |
| --- | --- | --- |
| Empty | `[]` | Overload with identity returns identity; without identity returns empty Optional. |
| Single element | `[7]` | Reduction returns the right value; identity does not corrupt it. |
| Multiple elements | `[1, 2, 3, 4]` | Result is correct according to the operation. |
| Negatives and 0 | `[-3, 0, 7, -2]` | Do not use a non-neutral identity like `0` for max on a negative domain. |
| Filtered out completely | `[2, 4, 6]` with `filter(n -> n < 0)` | Empty pipeline is handled properly. |
| Ordered source | `["A", "B", "C"]` | Combining operation matches ordering expectations. |
| Parallel | Same dataset in `parallelStream()` mode | Logical result is consistent when the operation obeys the laws. |
| Different groupings | `(a op b) op c` vs `a op (b op c)` | Check associativity before trusting a parallel reduction. |

**Note:** running `parallelStream()` a few times and seeing identical results **does not prove** the operation obeys the associativity law. Data size, CPU core count, and source-splitting strategy may keep the bug from appearing yet. Algebraic checks and edge cases must accompany execution tests.

### 10.1. Choosing an independent “oracle”

For addition, you can compute the expected sum with a simple loop for comparison; do not reuse the exact same `reduce` expression and treat it as independent evidence.

```java
long mongDoi = 0L;
for (int so : Arrays.asList(-3, 0, 7, -2)) {
    mongDoi += so;
}
System.out.println(mongDoi); // 2
```

In this example, `long` and small numbers are used to avoid overflow during verification. In real production code, clearly define numeric-range requirements and overflow handling.

### 10.2. Comparing two groupings without running in parallel

Associativity is a mathematical property. You can check several specific value triples first:

```java
import java.util.function.IntBinaryOperator;

IntBinaryOperator cong = Integer::sum;
IntBinaryOperator tru = (a, b) -> a - b;

boolean congKetHop =
    cong.applyAsInt(cong.applyAsInt(10, 3), 2)
    == cong.applyAsInt(10, cong.applyAsInt(3, 2));

boolean truKetHop =
    tru.applyAsInt(tru.applyAsInt(10, 3), 2)
    == tru.applyAsInt(10, tru.applyAsInt(3, 2));

System.out.println(congKetHop); // true
System.out.println(truKetHop);  // false
```

A passing example does not prove the law **for all values**, yet a single failing counterexample is enough to refute it.

## 11. Complete verification program (Java 8+)

The following snippet needs no testing library. It verifies empty sources, single-element sources, multi-element sources, an independent sum, sequential/parallel pipelines, and the three-parameter overload.

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import java.util.stream.LongStream;
import java.util.stream.Stream;

public class KiemChungReduce {
    private static void yeuCau(boolean dung, String thongBao) {
        if (!dung) {
            throw new AssertionError(thongBao);
        }
    }

    private static long tinhTong(List<Integer> so, boolean songSong) {
        LongStream stream = so.stream()
            .mapToLong(Integer::longValue);

        if (songSong) {
            stream = stream.parallel();
        }

        return stream.reduce(0L, Long::sum);
    }

    public static void main(String[] args) {
        Optional<Integer> khongIdentity =
            Stream.<Integer>empty().reduce(Integer::sum);

        int coIdentity = Stream.<Integer>empty()
            .reduce(0, Integer::sum);

        yeuCau(!khongIdentity.isPresent(),
            "Empty source must return Optional.empty()");
        yeuCau(coIdentity == 0,
            "Empty source must return identity 0");

        List<List<Integer>> cacCa = Arrays.asList(
            Collections.<Integer>emptyList(),
            Collections.singletonList(7),
            Arrays.asList(1, 2, 3, 4),
            Arrays.asList(-3, 0, 7, -2),
            Arrays.asList(0, 0, 0)
        );

        for (List<Integer> ca : cacCa) {
            long mongDoi = 0L;
            for (int n : ca) {
                mongDoi += n;
            }

            yeuCau(tinhTong(ca, false) == mongDoi,
                "Wrong sequential result for " + ca);
            yeuCau(tinhTong(ca, true) == mongDoi,
                "Wrong parallel result for " + ca);
        }

        List<String> ten = Arrays.asList(
            "Java", "Go", "Kotlin"
        );

        int tuanTu = ten.stream().reduce(
            0, (n, s) -> n + s.length(), Integer::sum);

        int songSong = ten.parallelStream().reduce(
            0, (n, s) -> n + s.length(), Integer::sum);

        yeuCau(tuanTu == 12 && songSong == 12,
            "Wrong total length");

        System.out.println("PASS: valid reduce cases");
    }
}
```

When run on a Java 8+ environment, a correct program will print:

```text
PASS: valid reduce cases
```

Testing both empty sources and multiple execution modes helps catch common bugs. It does not substitute for proving identity, associativity, and combiner compatibility across the **entire actual data domain**.

## 12. Floating-point numbers, overflow, and precision

### 12.1. `double` addition is not bitwise associative

Floating-point numbers have rounding error. Example:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

double trai = (a + b) + c;
double phai = a + (b + c);

System.out.println(trai); // 1.0
System.out.println(phai); // 0.0
```

Therefore, with `DoubleStream.reduce(0.0, Double::sum)`, how elements are grouped can affect the trailing bits of the result. For approximate calculations, define a **tolerance** or acceptable error margin. When exact decimals are required for currency, consider `BigDecimal` and explicit rounding rules.

Note: `DoubleStream.sum()` may use compensated summation to reduce error, so do not assume it performs the exact same addition steps as `reduce(0.0, Double::sum)`.

### 12.2. Integer overflow

`IntStream.reduce(0, Integer::sum)` or `IntStream.sum()` can overflow `int` if the sum exceeds the 32-bit range. Convert to `long` **before adding**:

```java
import java.util.stream.IntStream;

long tong = IntStream.of(
        1_500_000_000, 1_500_000_000
    )
    .asLongStream()
    .reduce(0L, Long::sum);

System.out.println(tong); // 3000000000
```

`long` still has limits. When the required value domain exceeds `long`, `BigInteger` can be used:

```java
import java.math.BigInteger;
import java.util.stream.Stream;

BigInteger tong = Stream.of(
        BigInteger.valueOf(Long.MAX_VALUE),
        BigInteger.ONE
    )
    .reduce(BigInteger.ZERO, BigInteger::add);

System.out.println(tong); // 9223372036854775808
```

Each `BigInteger` addition creates a new result without mutating `identity`, fitting the stateless reduction mindset.

## 13. When to use `reduce`, and when to use `collect`?

`reduce` is appropriate when you can **combine values into a new value** via an operation satisfying the laws:

- Sum, product, min, max on a valid domain.
- Simple string concatenation if performance is not an issue.
- Reducing immutable objects with a valid combining operation.

`collect` is appropriate when you need to **accumulate into a mutable result area** or complex structure:

- Lists, sets, maps.
- `groupingBy`, `partitioningBy`, `joining`.
- Custom collectors whose `supplier`, `accumulator`, and `combiner` are designed for mutable results.

For example, the same total length can be written as:

```java
int dungReduce = ten.stream()
    .reduce(0, (n, s) -> n + s.length(), Integer::sum);

int deDocHon = ten.stream()
    .mapToInt(String::length)
    .sum();

System.out.println(dungReduce == deDocHon); // true
```

Not every problem needs a hand-written `reduce`. When the API already offers `sum`, `min`, `max`, `count`, or an appropriate collector, using them makes intent clearer and reduces the chance of writing a buggy combiner.

## 14. Common mistakes

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Empty source returns a meaningless assumed value | Arbitrary identity chosen | Determine the true identity, or use the overload returning `Optional` |
| Sequential result is right, parallel is wrong | Non-associative operation, wrong combiner, or non-neutral identity | Check the three laws of `reduce` |
| Prefix appears multiple times with `parallelStream()` | Prefix placed in the identity of string concatenation | Use `""` as identity and add prefix after reduction, or `Collectors.joining` |
| `reduce(0, Math::max)` returns 0 when all numbers are negative | 0 is not neutral for max over the entire `int` domain | Use `max()` returning `OptionalInt`, or a domain-appropriate identity |
| List gets duplicated / concurrency error in parallel reduce | Shared `ArrayList` mutated inside accumulator | Use `collect(toList())` |
| Tested only with 1 element so no bug was seen | Associativity across multiple branches not checked | Add multi-element cases, test different groupings |
| Exact equality comparison between sequential and parallel `double` results | Floating-point error depends on merge order | Use tolerance-based checks per business rules |
| `int` sum unexpectedly turns negative | Numeric overflow | Choose an appropriate `long` or `BigInteger` domain |
| Assuming lambda invocation count equals element count | Implementations may group/evaluate differently | Verify the final result; avoid relying on side effects |

## 15. Practice exercises

### Exercise 1 — Empty source

Predict the result and return type:

```java
Optional<Integer> a = Stream.<Integer>empty()
    .reduce(Integer::sum);

int b = Stream.<Integer>empty()
    .reduce(0, Integer::sum);

int c = java.util.stream.IntStream.empty()
    .reduce(1, (x, y) -> x * y);
```

When should you use `Optional` instead of assigning an identity?

### Exercise 2 — Identify the identity

Given reductions on `IntStream`: addition, multiplication, taking the max of all `int` values. Choose the right identity for each operation and explain why `0` is unsuitable for `max` when the source has negative numbers.

### Exercise 3 — Prove an operation fails in parallel

Explain why `(a - b) - c` differs from `a - (b - c)`. Write a triple of numbers as a counterexample. Can you conclude subtraction is a valid combiner from a single `parallelStream()` run?

### Exercise 4 — Fix the combiner

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

int ketQua = ten.parallelStream().reduce(
    0,
    (n, s) -> n + s.length(),
    (a, b) -> a - b
);
```

Fix it into a valid reduction and explain using the compatibility formula with the accumulator.

### Exercise 5 — Safer summation

Given `int[] giaoDich = {1_500_000_000, 1_500_000_000};`, write a reduction pipeline so the exact result is `3_000_000_000L`. Why can calling `IntStream.sum()` before converting to `long` not recover the result?

### Reference answers

**Exercise 1:** `a` is `Optional.empty()`, `b == 0`, `c == 1`. Use `Optional` when business logic needs to recognize the absence of data, such as no maximum score in an empty set.

**Exercise 2:** addition uses `0`, multiplication uses `1`, max over the entire `int` domain uses `Integer.MIN_VALUE`. For a possibly empty source, `IntStream.max()` returning `OptionalInt` is usually clearer because it distinguishes missing data.

**Exercise 3:** choose `a = 10`, `b = 3`, `c = 2`: `(10 - 3) - 2 = 5` while `10 - (3 - 2) = 9`. A single run proves nothing; the associativity law has been refuted by a counterexample.

**Exercise 4:**

```java
int ketQua = ten.parallelStream().reduce(
    0,
    (n, s) -> n + s.length(),
    Integer::sum
);

System.out.println(ketQua); // 12
```

Because `Integer.sum(u, 0 + s.length()) == u + s.length()`, the combiner is compatible with the accumulator; `0` is neutral for addition.

**Exercise 5:**

```java
long tong = java.util.Arrays.stream(giaoDich)
    .asLongStream()
    .reduce(0L, Long::sum);

System.out.println(tong); // 3000000000
```

Each element must be converted to `long` before addition; converting after `IntStream.sum()` has already overflowed cannot repair the data.

## 16. Key takeaways

A reliable `reduce` must be correct for **empty sources** and **all valid element groupings**:

- No identity → result can be `Optional.empty()`.
- With identity → empty source returns identity; identity must be genuinely neutral for the operation.
- The combining operation must have **associativity**; the three-parameter overload also requires the accumulator to be compatible with the combiner.
- Do not mutate shared state inside `reduce`; when mutable structure accumulation is needed, prefer `collect`.
- Test empty sources, single elements, multiple elements, negative/0 data, and parallel pipelines; verify algebraic laws rather than just looking at a single run's output.
- For floating-point numbers and large integers, consider error tolerance and overflow requirements before claiming an exact result.

Understanding these conditions helps you use `reduce` properly in Java Stream API pipelines, even when execution transitions from sequential to parallel.
