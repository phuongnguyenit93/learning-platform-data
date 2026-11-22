# Reducing Strings, Value Objects, and Aggregated Results

## 1. From many elements to a meaningful single result

In the **Reduction with reduce** chapter of **JAVA_STREAM_API**, `reduce` is a terminal operation that combines multiple elements into a single result. The output can be a number, a string, an **immutable value object**, or an **aggregated summary containing multiple metrics**. Once we understand the contract of `reduce`, we can continue pairing it with declarative `filter`/`map` pipelines and lazy data sources, including parallel processing.

Examples:

- A set of keywords into a single display string.
- Monetary amounts in the same currency into a total amount.
- Multiple sales records into a result containing order count, units, and revenue.
- Multiple scores into statistics containing count, sum, minimum, maximum, and average.

~~~text
Source          Intermediate steps               Terminal reduce
[ x1, x2, x3 ] ─► filter ─► map ──────────────────► COMBINE INTO RESULT
                                                        │
                          ┌─────────────────────────────┼────────────────────────┐
                          ▼                             ▼                        ▼
                       String                  Money / Value Object       Summary / Report
~~~

`reduce` is not just “adding numbers”. It defines **how to merge two identically structured results** or **how to fold an element into an aggregated result**. For an expression to be right when a pipeline is split and merged, we must obey rules for *identity*, *associativity*, independence, and the *combiner*.

The examples use **Java 17+**, primarily with `List`, `record`, `BigDecimal`, and Streams. They focus on correctness of the combining operation first, and discuss performance afterward.

## 2. Three forms of reduce and return types

`Stream<T>` has three important overloads:

~~~java
Optional<T> reduce(BinaryOperator<T> accumulator);

T reduce(T identity, BinaryOperator<T> accumulator);

<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
);
~~~

| Form | Result | When appropriate |
| --- | --- | --- |
| `reduce(operator)` | `Optional<T>` | There is no natural identity or an empty source should be represented. |
| `reduce(identity, operator)` | `T` | Elements and result share type `T`, with a valid identity. |
| `reduce(identity, accumulator, combiner)` | `U` | Input has type `T` while aggregated output has type `U`. |

Example with integers:

~~~java
import java.util.List;
import java.util.Optional;

public class ReduceOverloads {
    public static void main(String[] args) {
        List<Integer> values = List.of(3, 4, 5);

        Optional<Integer> one = values.stream().reduce(Integer::sum);
        int two = values.stream().reduce(0, Integer::sum);

        long three = values.stream().reduce(
            0L,
            (sum, value) -> sum + value,
            Long::sum
        );

        System.out.println(one.orElseThrow()); // 12
        System.out.println(two);                // 12
        System.out.println(three);              // 12
    }
}
~~~

The third form allows the result to be `Long` while the input elements are `Integer`. It is especially useful when computing an aggregated structure of a different type from the source data. For ordinary integer sums, primitive streams like `mapToLong(...).sum()` can be more concise and avoid boxing.

### What does an empty source return?

~~~java
import java.util.List;
import java.util.Optional;

List<String> empty = List.of();

Optional<String> noValue = empty.stream().reduce(String::concat);
String emptyText = empty.stream().reduce("", String::concat);

// noValue == Optional.empty()
// emptyText.equals("") == true
~~~

The form without identity returns an `Optional` to represent **no elements to reduce**. The form with identity returns the identity itself when the source is empty. Choosing the identity therefore directly affects the business meaning of the result.

## 3. Mathematical contract: identity, associativity, and compatibility

### 3.1. Identity must be truly neutral

For a combining operation `op` on type `T`, identity `e` must satisfy:

~~~text
op(e, x) = x
op(x, e) = x
~~~

Examples:

| Combining operation | Appropriate identity | Quick check |
| --- | --- | --- |
| Integer addition | `0` | `0 + x = x + 0 = x` |
| Integer multiplication | `1` | `1 * x = x * 1 = x` |
| String concatenation | `""` | `"".concat(x) = x.concat("") = x` |
| `BigDecimal` addition | `BigDecimal.ZERO` | `0 + amount = amount` in numeric value |
| Merging sets via union | Empty set | `empty ∪ S = S ∪ empty = S` |

**Common mistake:** using a “nice-looking default” value instead of an identity.

~~~java
import java.util.List;

// Incorrect for computing a regular sum:
int wrong = List.of(2, 3).stream().reduce(10, Integer::sum);
// wrong == 15, not 5.

// Correct:
int total = List.of(2, 3).stream().reduce(0, Integer::sum);
// total == 5.
~~~

The identity of a value object may require additional context, such as **currency** or **unit of measure**. A `Money(0, "USD")` is only a valid identity for Money values in the same USD currency and an addition operation that allows adding USD.

### 3.2. The combining operation must be associative

For values `a`, `b`, `c`:

~~~text
op(op(a, b), c) = op(a, op(b, c))
~~~

Take string concatenation with `String::concat` as an example:

~~~text
("Java" + " Stream") + " API"
=
"Java" + (" Stream" + " API")
=
"Java Stream API"
~~~

A parallel Stream is allowed to reduce separate parts of the data and then merge the results. Therefore, a combining operation **dependent on parenthesization** can return different results when grouped differently.

Subtraction is a **non-associative** example:

~~~java
import java.util.List;

int result = List.of(10, 3, 2).stream()
    .reduce(0, (a, b) -> a - b);

System.out.println(result); // -15 in this sequential pipeline.
~~~

This is not an appropriate reduction when you want consistent results on a parallel stream. Moreover, `0` is not a two-sided identity for subtraction because `0 - x` differs from `x`.

### 3.3. Three-parameter reduce also requires compatibility

With input type `T` and accumulated result type `U`, `accumulator` and `combiner` must coordinate consistently. For every intermediate result `u` and element `t`, we need:

~~~text
combiner(u, accumulator(identity, t)) = accumulator(u, t)
~~~

`combiner` must also have `identity` as its identity and be associative. This rule ensures that an element processed in a separate branch and then merged into the overall result yields the exact same result as processing directly on the overall result.

We will apply this exact principle to aggregated objects in the following examples.

## 4. Joining strings with reduce: from a list to text

With `String`, concatenation is a natural example because `String` is immutable: each concatenation creates a new result value.

~~~java
import java.util.List;

public class StringReduce {
    public static void main(String[] args) {
        List<String> words = List.of("Java", " ", "Stream", " ", "API");

        String text = words.stream()
            .reduce("", String::concat);

        System.out.println(text); // Java Stream API
    }
}
~~~

`""` is the identity. `String::concat` is associative: different parenthesizations do not alter the character sequence when element order is preserved.

This example works well to **explain the principles of reduce**; on very large data, consider `Collectors.joining()` because `String` immutability means each concatenation can copy the already-accumulated string.

### 4.1. Reducing strings after a cleanup step

~~~java
import java.util.List;

List<String> tags = List.of("  Java ", "", " Stream ", " API  ");

String joined = tags.stream()
    .map(String::strip)
    .filter(text -> !text.isEmpty())
    .reduce("", String::concat);

System.out.println(joined); // JavaStreamAPI
~~~

In this example, `filter` drops empty strings; `map` cleans whitespace; `reduce` concatenates the remainder. The pipeline is lazy until the terminal `reduce` runs.

If you want to join words with a meaningful delimiter, you cannot simply write `reduce("", (a, b) -> a + ", " + b)`: for the first element, that would place a leading comma at the start of the string.

### 4.2. Joining with a delimiter without an identity

~~~java
import java.util.List;

List<String> cities = List.of("Hanoi", "Da Nang", "Ho Chi Minh City");

String label = cities.stream()
    .reduce((left, right) -> left + " | " + right)
    .orElse("(no location)");

System.out.println(label); // Hanoi | Da Nang | Ho Chi Minh City
~~~

Without an identity, when the source is empty, `reduce` returns `Optional.empty()`. With non-empty input strings, merging with `" | "` between groups is associative; when the stream has an encounter order, the result preserves source order.

If elements may be empty strings, you must clarify whether they should be kept; an empty string between two delimiters may still be a valid business value. Do not automatically filter empty strings if the requirement is to preserve the field count.

### 4.3. Choosing the right approach for long strings

In applications, if the goal is simply joining strings with a delimiter, using a dedicated collector is usually more efficient and clearer:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> cities = List.of("Hanoi", "Da Nang", "Ho Chi Minh City");

String joined = cities.stream()
    .collect(Collectors.joining(" | "));

System.out.println(joined); // Hanoi | Da Nang | Ho Chi Minh City
~~~

`Collectors.joining` uses a mutable string accumulation mechanism inside the collector under contract, avoiding repeatedly concatenating a large string as `reduce` does. It also supports `joining(delimiter, prefix, suffix)`.

| String problem | Suggested approach |
| --- | --- |
| Illustrating `reduce` and associativity laws | `reduce("", String::concat)` |
| Joining a few strings with a custom rule, small source | `reduce(BinaryOperator)` if the combining rule is genuinely associative |
| Joining many strings with a delimiter | `Collectors.joining(delimiter)` |
| Needing to mutate text buffers during traversal | An appropriate collector instead of using a mutable `StringBuilder` as `reduce` identity |

## 5. Reducing immutable value objects

A *value object* describes a business-domain value through its attributes, such as a monetary amount, a length, or a vector. When using `reduce`, this data type should have a combining operation that **returns a new object** rather than mutating the object currently in use.

We define `Money` with an amount and a currency. Addition is only valid when both monetary amounts share the same currency.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public class MoneyReduce {
    record Money(BigDecimal amount, String currency) {
        Money {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");
        }

        Money plus(Money other) {
            if (!currency.equals(other.currency())) {
                throw new IllegalArgumentException(
                    "Cannot add two different currencies"
                );
            }

            return new Money(amount.add(other.amount()), currency);
        }
    }

    public static void main(String[] args) {
        List<Money> payments = List.of(
            new Money(new BigDecimal("125000"), "VND"),
            new Money(new BigDecimal("24900"), "VND"),
            new Money(new BigDecimal("100"), "VND")
        );

        Money zero = new Money(BigDecimal.ZERO, "VND");

        Money total = payments.stream().reduce(zero, Money::plus);

        System.out.println(total);
        // Money[amount=150000, currency=VND]
    }
}
~~~

**Why is this style appropriate?**

- `Money` is a record with immutable `BigDecimal` and `String` components; `plus` creates a new record.
- Identity `Money(BigDecimal.ZERO, "VND")` preserves the value of any `Money` of the same currency when added.
- For valid amounts in the same currency, `BigDecimal` addition is associative in **mathematical value**, because it is exact decimal addition with no rounding error in `BigDecimal.add` when no rounding `MathContext` is imposed.
- The mapper does not mutate source objects and does not update shared variables.

**Business limitation:** Multi-currency data must be converted using an exchange rate and appropriate rounding rules **before summing**, or grouped by currency using a collector. Do not pick `Money(0, "VND")` as the identity for mixed USD/VND data and skip currency conversion.

### 5.1. Reduce without identity when a zero value cannot be picked by default

If the source's currency is only known from the first element itself, there is no need to “guess” an identity:

~~~java
import java.util.Optional;

// payments is List<Money> from the MoneyReduce example.
Optional<Money> total = payments.stream()
    .reduce(Money::plus);
~~~

When `payments` is empty, the result is `Optional.empty()`. The application can keep the “no amount” state, require a default currency to be supplied, or throw an error if a transaction must have an amount.

Do not replace `Optional.empty()` with a fake monetary amount if doing so loses business information.

### 5.2. Notes on BigDecimal

`BigDecimal.add` does not automatically convert currencies. In addition, `BigDecimal.equals` also distinguishes **scale**:

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0); // true: same numeric value.
System.out.println(a.equals(b));         // false: different scale.
~~~

If the system requires monetary representations with consistent scale, place a normalization policy at the value object layer or input boundary. Do not infer from a single printout that every format detail is preserved in the intended sense.

## 6. From input records to an aggregated result of a different type

A program may need to report multiple metrics in a single traversal: total order lines, number of units, and revenue. Source elements are `OrderLine`, while the accumulated value is `SalesSummary`. This is an ideal case for **three-parameter reduce**.

~~~java
import java.math.BigDecimal;
import java.util.List;

public class SalesSummaryReduce {
    record OrderLine(String sku, int quantity, BigDecimal unitPrice) {
        BigDecimal lineTotal() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    record SalesSummary(
        long lineCount,
        long units,
        BigDecimal revenue
    ) {
        static SalesSummary zero() {
            return new SalesSummary(0L, 0L, BigDecimal.ZERO);
        }

        SalesSummary add(OrderLine line) {
            return new SalesSummary(
                lineCount + 1,
                units + line.quantity(),
                revenue.add(line.lineTotal())
            );
        }

        SalesSummary combine(SalesSummary other) {
            return new SalesSummary(
                lineCount + other.lineCount(),
                units + other.units(),
                revenue.add(other.revenue())
            );
        }
    }

    public static void main(String[] args) {
        List<OrderLine> lines = List.of(
            new OrderLine("BOOK", 2, new BigDecimal("19.90")),
            new OrderLine("PEN", 3, new BigDecimal("5.25"))
        );

        SalesSummary summary = lines.parallelStream().reduce(
            SalesSummary.zero(), // identity: empty aggregated state.
            SalesSummary::add,    // accumulator: folds OrderLine into Summary.
            SalesSummary::combine // combiner: merges two Summaries.
        );

        System.out.println(summary);
        // SalesSummary[lineCount=2, units=5, revenue=55.55]
    }
}
~~~

Explanation of each component:

1. `SalesSummary.zero()` creates an empty result: 0 lines, 0 units, 0 revenue.
2. `SalesSummary::add` is a `BiFunction<SalesSummary, OrderLine, SalesSummary>`. It creates a new object after folding in one more line.
3. `SalesSummary::combine` is a `BinaryOperator<SalesSummary>`. It merges results created by different branches.
4. Both operations keep state immutable, independent of the parallel stream's execution schedule.

If `a` is any summary and `line` is a single line item, then:

~~~text
combine(a, add(zero, line)) = add(a, line)
~~~

Both sides add exactly one line, that line's quantity, and its line amount. This is the **compatibility condition** between accumulator and combiner.

**Note:** The example assumes `quantity` is non-negative, `unitPrice` is valid, and all monetary values share the same currency. In a real system, validate input data, check `long` addition limits, and confirm conversion/rounding policies before concluding the aggregation is valid.

### 6.1. Sequential variant

~~~java
// Within the context of SalesSummaryReduce with List<OrderLine> lines:
SalesSummary summary = lines.stream().reduce(
    SalesSummary.zero(),
    SalesSummary::add,
    SalesSummary::combine
);
~~~

The three-parameter form also runs sequentially. Even so, the design must still satisfy the combiner contract because the code may switch to a parallel stream or be reused with another source.

### 6.2. When only a single metric is needed

If the requirement is solely total revenue, building a multi-field `SalesSummary` may be unnecessary:

~~~java
import java.math.BigDecimal;

// OrderLine is defined in the example class above.
BigDecimal total = lines.stream()
    .map(OrderLine::lineTotal)
    .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

On large datasets, choosing between primitive terminals, `reduce`, and `collect` depends on value types, aggregation needs, and object creation cost. There is no need for a complex summary if the output is just a simple sum.

## 7. Aggregating multiple numeric metrics and handling empty sets

Suppose a classroom needs statistics for graded assignments: count, total score, minimum score, maximum score, and average score. We can use **an immutable record** with `add` and `merge` methods.

~~~java
import java.util.List;
import java.util.OptionalDouble;
import java.util.OptionalInt;

public class ScoreStatisticsReduce {
    record Stats(long count, long sum, int min, int max) {
        static Stats empty() {
            return new Stats(
                0L,
                0L,
                Integer.MAX_VALUE,
                Integer.MIN_VALUE
            );
        }

        Stats add(int score) {
            return new Stats(
                count + 1,
                sum + score,
                Math.min(min, score),
                Math.max(max, score)
            );
        }

        Stats merge(Stats other) {
            return new Stats(
                count + other.count(),
                sum + other.sum(),
                Math.min(min, other.min()),
                Math.max(max, other.max())
            );
        }

        OptionalDouble average() {
            return count == 0
                ? OptionalDouble.empty()
                : OptionalDouble.of((double) sum / count);
        }

        OptionalInt minimum() {
            return count == 0
                ? OptionalInt.empty()
                : OptionalInt.of(min);
        }

        OptionalInt maximum() {
            return count == 0
                ? OptionalInt.empty()
                : OptionalInt.of(max);
        }
    }

    public static void main(String[] args) {
        List<Integer> scores = List.of(8, 5, 9, 6);

        Stats stats = scores.parallelStream().reduce(
            Stats.empty(),
            Stats::add,
            Stats::merge
        );

        System.out.println(stats.count()); // 4
        System.out.println(stats.sum()); // 28
        System.out.println(stats.minimum().orElseThrow()); // 5
        System.out.println(stats.maximum().orElseThrow()); // 9
        System.out.println(stats.average().orElseThrow()); // 7.0

        Stats empty = List.<Integer>of().stream().reduce(
            Stats.empty(),
            Stats::add,
            Stats::merge
        );

        System.out.println(empty.count()); // 0
        System.out.println(empty.average()); // OptionalDouble.empty
    }
}
~~~

`Integer.MAX_VALUE` and `Integer.MIN_VALUE` here are merely **internal neutral values** so `Math.min` and `Math.max` can combine with an empty summary. They are **not** exposed as real metrics when `count == 0`. Both `minimum()` and `maximum()` return an `Optional` to represent the absence of observations.

If you only need `count/sum/min/max/average` statistics for integers, Java already provides a dedicated solution:

~~~java
import java.util.IntSummaryStatistics;
import java.util.List;

IntSummaryStatistics stats = List.of(8, 5, 9, 6).stream()
    .mapToInt(Integer::intValue)
    .summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 28
System.out.println(stats.getMin());     // 5
System.out.println(stats.getMax());     // 9
System.out.println(stats.getAverage()); // 7.0
~~~

In typical applications, **prefer built-in operations/collectors** when they already provide the exact output required. Use a record with `reduce` when there are additional domain metrics or the aggregated result requires a custom type.

## 8. String concatenation and reduce in parallel execution

Some combining operations are **associative yet non-commutative**. For example, string concatenation:

~~~text
"a" + "b" = "ab"
"b" + "a" = "ba"
~~~

Concatenation is associative over string structure, yet changing **element order** changes the result. With an ordered stream and a contract-compliant reduction, parallel `reduce` still preserves the corresponding order semantics. We do not need callbacks to run in strict chronological order; the final result depends on **encounter order**, not thread scheduling.

~~~java
import java.util.List;

List<String> letters = List.of("J", "A", "V", "A");

String text = letters.parallelStream()
    .reduce("", String::concat);

System.out.println(text); // JAVA
~~~

If `unordered()` is called beforehand, the encounter-order constraint is dropped. For position-dependent concatenation, **do not rely on the result always being "JAVA"**.

~~~java
String textWithoutOrder = letters.parallelStream()
    .unordered()
    .reduce("", String::concat);

// textWithoutOrder contains the concatenated letters;
// character order is no longer guaranteed by the pipeline.
~~~

If business logic requires a sorted string, establish the order explicitly before joining:

~~~java
String sortedText = letters.parallelStream()
    .sorted()
    .collect(java.util.stream.Collectors.joining());

System.out.println(sortedText); // AAJV
~~~

### 8.1. Side effects do not substitute for return values

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> shared = new ArrayList<>();

String text = List.of("a", "b", "c").parallelStream()
    .reduce(
        "",
        (acc, value) -> {
            shared.add(value); // WRONG: mutation outside reduce, not thread-safe.
            return acc + value;
        }
    );
~~~

In this example, `text` is the output of `reduce`, whereas `shared` is an out-of-contract side effect. With a parallel stream, writing to a shared `ArrayList` can create race conditions. Do not use a `reduce` callback to collect elements into a list; let an appropriate terminal operation or collector produce the result.

### 8.2. What must not be put inside an accumulator

Do not update databases, send emails, write files, or increment business counters inside an accumulator just to “guarantee every element is processed”. When a pipeline runs in parallel, accumulator and combiner may be invoked on a different schedule than sequential execution. Work requiring transactions or side effects should be organized separately, with appropriate idempotency and error handling.

## 9. Serious mistake: reduce with a mutable identity

Code that looks “right” at first glance sequentially:

~~~java
import java.util.ArrayList;
import java.util.List;

// ILLUSTRATING THE WRONG WAY: do not use in a real pipeline.
List<String> broken = List.of("a", "b", "c").parallelStream()
    .reduce(
        new ArrayList<String>(),
        (acc, item) -> {
            acc.add(item);  // Mutates shared mutable identity.
            return acc;
        },
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
~~~

`reduce` requires a **non-interfering, stateless** accumulation, and `identity` must act as an identity element. With a mutable `ArrayList` identity shared across computation segments, the accumulator repeatedly mutates the same object. Branches can race to write, and the combiner can receive references pointing to the same list. Wrong results or erratic behavior can occur.

To collect a list, use `collect`:

~~~java
import java.util.List;
import java.util.stream.Collectors;

List<String> good = List.of("a", "b", "c").parallelStream()
    .collect(Collectors.toList());
~~~

If a mutable `ArrayList` is needed:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

ArrayList<String> mutable = List.of("a", "b", "c").parallelStream()
    .collect(Collectors.toCollection(ArrayList::new));
~~~

Collectors create accumulation containers under the *mutable reduction* contract and merge them properly. That is the job of `collect`, and should not be simulated by mutating an identity in `reduce`.

## 10. Arithmetic limits that easily make reduce wrong

### 10.1. Integer addition can overflow

~~~java
import java.util.List;

int wrapped = List.of(Integer.MAX_VALUE, 1).stream()
    .reduce(0, Integer::sum);

// wrapped == Integer.MIN_VALUE due to int overflow.
~~~

If the value domain can be large, pick an appropriate type and guard against overflow:

~~~java
long safe = List.of(Integer.MAX_VALUE, 1).stream()
    .mapToLong(Integer::longValue)
    .sum();

// safe == 2147483648
~~~

`long` still has limits. `Math.addExact` can detect overflow, while `BigInteger` / `BigDecimal` fit when results must exceed primitive ranges. For additions that can overflow even though the final mathematical sum fits in range, the result or exception can also depend on grouping; do not automatically assume overflow-checked addition is a safe parallel combining operation for all input domains.

### 10.2. Floating-point numbers are not strictly associative

Mathematically, addition is associative. With IEEE 754 floating-point numbers, rounding can cause:

~~~text
(a + b) + c  !=  a + (b + c)
~~~

Example:

~~~java
double a = 1e16;
double b = -1e16;
double c = 1.0;

double left = (a + b) + c;  // 1.0
double right = a + (b + c); // 0.0

System.out.println(left == right); // false
~~~

Hence, `DoubleStream.sum()` and floating-point reductions can yield rounding discrepancies depending on accumulation/grouping order. When strict precision is required, consider data representation, acceptable tolerance, and specialized summation algorithms. Do not use `double` as the default representation for money requiring decimal exactness.

### 10.3. Invalid combining or state dependence

An operation such as “taking the average of two averages” does not yield the true average when groups have different sizes:

~~~text
Group A: [10, 20, 30]  → average 20
Group B: [100]         → average 100

Average of two averages = (20 + 100) / 2 = 60    (wrong)
Overall average         = (10 + 20 + 30 + 100)/4 = 40 (right)
~~~

To combine averages correctly, you must keep at least **sum** and **count** in the summary, and compute the average after the reduction finishes. That is why a record like `Stats(count, sum, ...)` is more reliable than storing only an `average` value.

## 11. reduce or collect? Choose by the nature of the result

`reduce` uses value combining, usually suited for **immutable** objects and combining operations with a clear identity. `collect` uses accumulation into mutable containers through a supplier, accumulator, and combiner.

| Requirement | Suggestion | Reason |
| --- | --- | --- |
| Summing `int`/`long` numbers | `mapToInt(...).sum()`, `mapToLong(...).sum()` | Uses primitive terminals, avoiding boxing. |
| Joining a few strings to understand combining | `reduce("", String::concat)` | Clear identity and associativity. |
| Joining large text with a delimiter | `Collectors.joining(...)` | Supports efficient string accumulation. |
| Adding immutable `Money` of the same currency | `reduce(zero, Money::plus)` | Proper value-object semantics. |
| Record result with multiple custom metrics | `reduce(identityU, accumulator, combiner)` | Directly produces an immutable aggregated result. |
| Standard numeric statistics | `summaryStatistics()`, `summarizingLong(...)` | The library already provides suitable solutions. |
| Creating a `List` or `Map` | `collect(toList())`, `collect(toMap(...))` | Has an appropriate mutable accumulation mechanism. |
| Grouping by key | `groupingBy(...)` / `groupingByConcurrent(...)` when appropriate | Essentially collects multiple results per group. |

If a `reduce` creates many intermediate immutable objects and performance becomes an issue, a custom collector can be considered. However, the collector must still uphold the corresponding identity/associativity rules, and characteristics such as `CONCURRENT` should only be declared when the accumulator/container genuinely supports concurrent updates under the contract.

In parallel processing practice, **result correctness** must always be proved before measuring speed.

## 12. Stream lifecycle, empty sources, and null

### 12.1. reduce triggers a lazy pipeline

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> pipeline = List.of(2, 4, 6).stream()
    .filter(n -> n > 2)
    .map(n -> n * 10);

// Up to here, no elements need to be processed.
int total = pipeline.reduce(0, Integer::sum); // 100
~~~

`reduce` is a terminal operation; once called, `pipeline` has been consumed and no other terminal operation may be run on that same Stream. With a finite source, reduction normally must traverse all remaining data to compute the result; on an unbounded infinite Stream, a summing-style `reduce` may never terminate.

### 12.2. Avoid null in elements and combined results

With `reduce(BinaryOperator)`, a `null` intermediate result does not properly represent “no result”; it can cause a `NullPointerException`. If the input data contains nulls or the combining logic could return null, establish a filtering or transformation policy before `reduce`.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<String> words = Arrays.asList("Java", null, "Stream");

String text = words.stream()
    .filter(Objects::nonNull)
    .reduce("", String::concat);

System.out.println(text); // JavaStream
~~~

Do not pick `null` as the identity to “save effort” designing an identity element. Identity must be a valid value that is neutral with respect to the combining operation.

### 12.3. Resource-backed sources must still be closed

With a Stream from a file:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countChars(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
            .mapToLong(String::length)
            .sum();
    }
}
~~~

This example uses `sum()` instead of `reduce` because only total length is needed. Crucially, `try-with-resources` manages the resource held by `Files.lines`. Neither `reduce` nor other terminal operations replace the obligation to close the source resource.

## 13. Verifying the correctness of a reduction

Before switching from sequential to parallel, verify properties that can be tested on small data:

1. **Identity:** Combining with identity on either side produces the same value.
2. **Associativity:** Different groupings yield the same result under the chosen arithmetic/data model.
3. **Compatibility:** For three-parameter `reduce`, processing one element separately and combining equals processing that element directly on an existing summary.
4. **Empty source:** Does it return `identity` or `Optional.empty` with the right business meaning?
5. **Independence:** Do mapper/accumulator/combiner avoid mutating the source and shared mutable state?
6. **Value range:** Are there overflows, rounding, or numeric type limits to control?
7. **Ordering:** Is the combining operation order-sensitive? If so, do the source and pipeline preserve encounter order?

Example illustrating invariants for `String::concat`:

~~~java
public class ReduceLawsCheck {
    public static void main(String[] args) {
        String a = "Java";
        String b = " Stream";
        String c = " API";
        String e = "";

        if (!e.concat(a).equals(a) || !a.concat(e).equals(a)) {
            throw new AssertionError("Invalid identity");
        }

        String left = a.concat(b).concat(c);
        String right = a.concat(b.concat(c));
        if (!left.equals(right)) {
            throw new AssertionError("Combining operation is not associative");
        }

        System.out.println(left); // Java Stream API
    }
}
~~~

This example checks an illustrative case, not a formal proof for all input values. For business reductions, test many edge cases: empty, single element, duplicate values, large values, skewed group sizes, and different combining orders.

## 14. Self-check questions

1. **What does `reduce("", String::concat)` return on an empty Stream?** Empty string because `""` is the identity.
2. **What does `reduce(String::concat)` return on an empty Stream?** `Optional.empty()` because there is no identity.
3. **Why is `reduce(10, Integer::sum)` unsuitable for computing a regular sum?** Because `10` is not the identity of addition; the result gets that value added to it.
4. **Is string concatenation associative? Is it commutative?** Associative in character order; not commutative because `"ab"` differs from `"ba"`.
5. **Why should a mutable `StringBuilder` not be the identity of `reduce`?** The accumulator mutates a shared object, violating the reduction contract and risking races/bad merges in parallel.
6. **When the source is `Stream<OrderLine>` and the result is `SalesSummary`, which overload is used?** `reduce(identityU, accumulator, combiner)`.
7. **What is the combiner of three-parameter `reduce` used for?** Merging two accumulated results of type `U`, especially when processing parallel branches.
8. **Is computing an average by averaging group averages correct?** Not in general; you must carry both the sum and the count of each group.
9. **When processing an empty set of scores, should min/max be returned as a sentinel value as if it were real data?** No; return an `Optional` or a result type preserving the no-observations state.
10. **When you only need to join a large list with commas, choose `reduce` or `Collectors.joining`?** Usually `Collectors.joining`.
11. **Can you use `unordered()` before a string-concatenating `reduce` and still demand source-order output?** No; `unordered` drops the encounter-order guarantee.
12. **Why can parallel `double` addition differ from sequential?** Because floating-point addition has rounding error and is not strictly associative.
13. **When is `BigDecimal` needed in a value object?** When the business domain requires exact decimal values, combined with explicit scale and currency policies.
14. **Can a Stream that already ran `reduce` be reused to call `count`?** No; a fresh Stream must be created from the source.
15. **If the result is a mutable `List`, should you use `reduce` with an `ArrayList` identity?** No; use `collect` with an appropriate collector.

**Key takeaway:** `reduce` is a reduction **from multiple elements to a single value**: a string, a value object, or an immutable summary. Choose the right overload, define a neutral identity, ensure associativity and accumulator/combiner compatibility, and then consider performance. Use `collect` when mutable reduction is needed, keep `Optional` when an empty source is meaningful, and control numeric limits when aggregating large data or running in parallel.
