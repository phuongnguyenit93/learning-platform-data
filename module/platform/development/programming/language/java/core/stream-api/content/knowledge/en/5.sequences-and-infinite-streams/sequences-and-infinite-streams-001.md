# Creating Number Ranges with range and rangeClosed

When you need to number a list, iterate over array indices, generate test IDs, or compute over a consecutive sequence of numbers, you often write a `for` loop. The **Java Stream API** provides a way to declare a number range directly using **`range`** and **`rangeClosed`**. These two methods let you express the exact set of values to process, and then combine them with `filter`, `map`, `reduce`, `collect`, or other terminal operations.

This lesson belongs to the **Sequences and Infinite Streams** chapter of the **JAVA_STREAM_API** module and focuses on creating **finite sequences** with `IntStream` and `LongStream`. Unlike `Stream.iterate` or `Stream.generate`, which can produce non-terminating sequences, `range` and `rangeClosed` define both endpoints of the interval right when constructing the source. The goal is to understand inclusive/exclusive bounds, use the right data types, avoid *off-by-one* errors, and apply Stream laziness and resource limits.

## 1. Why Do We Need a Range-Based Stream Source?

Consider a simple requirement: take the integers from 1 to 5, compute their sum, and create names for five processing steps.

With a loop, you control the counter variable directly:

~~~java
int sum = 0;
for (int number = 1; number <= 5; number++) {
    sum += number;
}
System.out.println(sum); // 15
~~~

With Streams, **sequence generation** is separated from **sequence processing**:

~~~java
import java.util.stream.IntStream;

int sum = IntStream.rangeClosed(1, 5).sum();
System.out.println(sum); // 15
~~~

`IntStream.rangeClosed(1, 5)` describes the sequence `1, 2, 3, 4, 5`; `sum()` requests the total sum. If you only want 1 to 4, use `IntStream.range(1, 5)`. This is the most important difference between the two APIs.

## 2. How Do range and rangeClosed Differ?

Both methods are **static factory methods** on `IntStream` and `LongStream`:

~~~java
IntStream.range(int startInclusive, int endExclusive)
IntStream.rangeClosed(int startInclusive, int endInclusive)

LongStream.range(long startInclusive, long endExclusive)
LongStream.rangeClosed(long startInclusive, long endInclusive)
~~~

The parameter names clearly state the bounds:

- `startInclusive`: **includes** the start point.
- `endExclusive`: **excludes** the end point.
- `endInclusive`: **includes** the end point.

Using mathematical notation, for `a <= b`:

- `range(a, b)` corresponds to **`[a, b)`** — closed on the left, open on the right.
- `rangeClosed(a, b)` corresponds to **`[a, b]`** — closed at both ends.

| Call | Generated values | Element count |
|---|---|---|
| `IntStream.range(2, 6)` | `2, 3, 4, 5` | 4 |
| `IntStream.rangeClosed(2, 6)` | `2, 3, 4, 5, 6` | 5 |
| `IntStream.range(5, 5)` | None | 0 |
| `IntStream.rangeClosed(5, 5)` | `5` | 1 |
| `IntStream.range(6, 5)` | None | 0 |
| `IntStream.rangeClosed(6, 5)` | None | 0 |
| `IntStream.range(-2, 2)` | `-2, -1, 0, 1` | 4 |

The number of elements for a valid range is determined by:

- `range(start, end)`: `end - start` elements when `start < end`, otherwise 0.
- `rangeClosed(start, end)`: `end - start + 1` elements when `start <= end`, otherwise 0.

The formulas above are **mathematical** in meaning. If you compute them yourself using `int` or `long` in a program, subtraction or addition can overflow with extreme bounds. When you only need the element count, use `count()`; when performing calculations yourself, choose an appropriate numeric type and guard against overflow.

### Visualizing on a Number Line

~~~text
range(2, 6)
    2 --- 3 --- 4 --- 5 --- (6)
    ^                         ^
  take 2                    drop 6

rangeClosed(2, 6)
    2 --- 3 --- 4 --- 5 --- 6
    ^                         ^
  take 2                    take 6
~~~

Mnemonic: **`range` excludes the endpoint; `rangeClosed` keeps the endpoint**. The word *Closed* in mathematics corresponds to a closed interval with an included boundary.

## 3. Complete Java Example: Generating, Aggregating, and Numbering

The following code runs on **Java 8 and above**; all examples use the core Stream API without requiring `Stream.toList()` from newer JDKs.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class RangeOverviewDemo {
    public static void main(String[] args) {
        // 2, 3, 4, 5: the endpoint 6 is excluded.
        List<Integer> halfOpen = IntStream.range(2, 6)
            .boxed()
            .collect(Collectors.toList());

        // 2, 3, 4, 5, 6: the endpoint 6 is included.
        List<Integer> closed = IntStream.rangeClosed(2, 6)
            .boxed()
            .collect(Collectors.toList());

        // The sequence 1..10 has a sum of 55.
        int sum = IntStream.rangeClosed(1, 10).sum();

        // Convert indices 0..size-1 into names numbered 1..size.
        List<String> names = Arrays.asList("Alice", "Bob", "Charlie");
        List<String> numbered = IntStream.range(0, names.size())
            .mapToObj(index -> (index + 1) + ". " + names.get(index))
            .collect(Collectors.toList());

        System.out.println(halfOpen);
        System.out.println(closed);
        System.out.println(sum);
        System.out.println(numbered);
    }
}
~~~

Output:

~~~text
[2, 3, 4, 5]
[2, 3, 4, 5, 6]
55
[1. Alice, 2. Bob, 3. Charlie]
~~~

There are three noteworthy operations:

1. `IntStream.range(...)` and `rangeClosed(...)` return an **`IntStream`**, i.e., a stream of primitive `int` values.
2. `boxed()` converts the `int` elements into `Integer` so a collector can build a `List<Integer>`.
3. `mapToObj(...)` transforms each `int` value into an object (here a `String`), and `collect` creates a `List<String>`.

In Java 16+, you can replace `collect(Collectors.toList())` with `toList()` if you want an unmodifiable list. The contract of `Collectors.toList()` makes no specific guarantee about the mutability of the returned list; choose the appropriate collector if your application needs a collection with deterministic characteristics.

## 4. Number Ranges Are Primitive Streams, Not Stream<Integer>

Java has three primitive Stream families: `IntStream`, `LongStream`, and `DoubleStream`. However, **only `IntStream` and `LongStream` provide `range` and `rangeClosed`**. There is no `DoubleStream.range(...)` in the standard API.

| Input | Returned Stream type | Example |
|---|---|---|
| `IntStream.range(0, 3)` | `IntStream` | `0, 1, 2` |
| `IntStream.rangeClosed(0, 3)` | `IntStream` | `0, 1, 2, 3` |
| `LongStream.range(0L, 3L)` | `LongStream` | `0L, 1L, 2L` |
| `LongStream.rangeClosed(0L, 3L)` | `LongStream` | `0L, 1L, 2L, 3L` |

Thanks to primitive streams, arithmetic operations typically avoid **boxing/unboxing** overhead between `int` and `Integer`. You can directly use:

~~~java
import java.util.stream.IntStream;

long quantity = IntStream.range(0, 100).count();     // 100
int maximum = IntStream.rangeClosed(1, 5)
    .max()
    .orElseThrow(IllegalStateException::new);        // 5
double average = IntStream.rangeClosed(1, 5)
    .average()
    .orElseThrow(IllegalStateException::new);        // 3.0
~~~

`count()` returns `long`, whereas `sum()` on `IntStream` returns `int` and `sum()` on `LongStream` returns `long`. `average()` returns `OptionalDouble` because the sequence can be empty; `max()` and `min()` return `OptionalInt` or `OptionalLong` respectively.

### Converting Types When Objects Are Needed

You cannot directly assign an `IntStream` to a `Stream<Integer>` variable:

~~~java
// Invalid because IntStream is different from Stream<Integer>:
// Stream<Integer> values = IntStream.range(1, 4);
~~~

Use `boxed()` or `mapToObj(...)` instead:

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> numbers = IntStream.range(1, 4)
    .boxed()
    .collect(Collectors.toList()); // [1, 2, 3]

List<String> labels = IntStream.rangeClosed(1, 3)
    .mapToObj(number -> "Step " + number)
    .collect(Collectors.toList()); // [Step 1, Step 2, Step 3]
~~~

With `LongStream`, `boxed()` and `mapToObj(...)` are also available. Keep primitive streams as long as appropriate when the main goal is numeric computation, and convert to object streams only when you need to create richer data types.

## 5. Common Case: Zero-Based Indexing

In Java, valid positions in an array or `List` with `n` elements are **`0` to `n - 1`**. Therefore, `range(0, n)` is the natural choice:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;

List<String> colors = Arrays.asList("red", "green", "yellow");

IntStream.range(0, colors.size())
    .forEach(index ->
        System.out.println(index + ": " + colors.get(index))
    );
~~~

Output:

~~~text
0: red
1: green
2: yellow
~~~

In this case, `range(0, colors.size())` gives the exact 3 indices: 0, 1, and 2. If you wrote `rangeClosed(0, colors.size())`, the Stream would also emit index **3**, leading to an `IndexOutOfBoundsException` when calling `colors.get(3)`.

For an empty list, `range(0, 0)` naturally produces an empty sequence without special-case handling. If you only need to iterate over **values** without needing the index, writing `colors.stream()` is usually simpler. Additionally, repeated `get(index)` calls work best with structures that support efficient indexed access like `ArrayList` or arrays; using the same approach with `LinkedList` can incur high traversal cost.

### Turning Positions into Structured Elements

Example creating display records with both position and value:

~~~java
List<String> descriptions = IntStream.range(0, colors.size())
    .mapToObj(index -> "Item " + (index + 1) + ": " + colors.get(index))
    .collect(java.util.stream.Collectors.toList());
~~~

`mapToObj` takes a function from `int` to an object `R`. This is a classic example of how a **range source** combines with a **Function** in a pipeline.

## 6. When to Use rangeClosed?

`rangeClosed` is suitable when the business requirement explicitly states that **both the first and last day/value are included**:

- A sequence of natural numbers from 1 to 10.
- Trial rounds from attempt 1 to attempt `n`.
- Days of the month if represented by day numbers from 1 to the last day.
- Tier levels from the lowest level to the highest level, inclusive of both ends.

Example summing from 1 to `n`:

~~~java
int n = 10;
int result = IntStream.rangeClosed(1, n).sum();
System.out.println(result); // 55
~~~

When `n = 0`, `rangeClosed(1, 0)` is empty and `sum()` returns 0. If the business logic allows negative `n`, you must define a clear handling policy; returning 0 by default for an empty sequence might mask invalid input.

Example representing the days of a known month:

~~~java
import java.time.YearMonth;
import java.util.stream.IntStream;

YearMonth month = YearMonth.of(2024, 2);

IntStream.rangeClosed(1, month.lengthOfMonth())
    .mapToObj(month::atDay)
    .forEach(System.out::println);
~~~

In the leap year 2024, February has 29 days, so the pipeline emits dates from `2024-02-01` to `2024-02-29`. `month::atDay` converts each valid day number into a `LocalDate`. Here `rangeClosed` expresses the *include the last day* rule more clearly than adding 1 to the upper bound of `range`.

## 7. Using LongStream.range and rangeClosed for Large Ranges

If the input is `long` or exceeds what `int` can represent, use `LongStream`:

~~~java
import java.util.stream.LongStream;

long from = 3_000_000_000L;
long toInclusive = 3_000_000_003L;

LongStream.rangeClosed(from, toInclusive)
    .forEach(System.out::println);
~~~

Output:

~~~text
3000000000
3000000001
3000000002
3000000003
~~~

`IntStream` only generates `int` values, ranging from `Integer.MIN_VALUE` to `Integer.MAX_VALUE`. `LongStream` supports a wider `long` range, but it is still **finite**, not arbitrary-precision integers.

Do not confuse the element type with the aggregated result type:

~~~java
// Sum from 1 to 100000 is 5_000_050_000, which exceeds Integer.MAX_VALUE.
long safeSum = IntStream.rangeClosed(1, 100_000)
    .asLongStream()
    .sum(); // 5000050000
~~~

If you call `IntStream.rangeClosed(1, 100_000).sum()`, the returned sum is `int` and can **overflow**. `asLongStream()` converts the elements to `long` before summing, but `long` also has a limit: a sum that is too large can still overflow. For precision requirements beyond `long`, consider `BigInteger` or an arithmetic formula with overflow checks.

## 8. Lazy Evaluation: Ranges Can Be Large Without Pre-allocating Arrays

Calling `IntStream.range(1, 1_000_000)` **does not pre-allocate a `List` containing nearly one million objects**. The range is represented as a **source** from which the Stream pulls elements as the pipeline processes them.

~~~java
import java.util.stream.IntStream;

IntStream numbers = IntStream.rangeClosed(1, 1_000_000)
    .filter(number -> number % 17 == 0);

// Up to here, only the source and condition are described; not all numbers have been traversed.

int first = numbers.findFirst()
    .orElse(-1);

System.out.println(first); // 17
~~~

`findFirst()` is a terminal operation capable of **short-circuiting**. Because the source is in ascending order and the first element divisible by 17 is 17, this pipeline does not need to traverse all one million numbers.

~~~mermaid
flowchart LR
    A["IntStream.rangeClosed(1, 1_000_000)"] --> B["filter(n % 17 == 0)"]
    B --> C["findFirst()"]
    C --> D["OptionalInt: 17"]
~~~

Two points to distinguish:

1. **Creating a range with range/rangeClosed** only sets up the source; by itself it is not a terminal operation.
2. **Collecting into a `List`, calling `toArray()`, or using `forEach`** may require traversing a large number of elements, consuming memory or time. Laziness does not make large results free.

For example, `LongStream.range(0L, 1_000_000_000_000L).limit(3).toArray()` only requests the first three elements. If you remove `limit(3)`, collecting all one trillion values into an array is impractical and will exceed Java's maximum array size limit.

### range Is Finite; iterate/generate Can Be Infinite

`range` and `rangeClosed` always describe a finite numeric interval according to the given bounds. Conversely:

~~~java
import java.util.stream.IntStream;

// Theoretically infinite decreasing sequence, taking the first 5 elements.
IntStream.iterate(10, n -> n - 2)
    .limit(5)
    .forEach(System.out::println); // 10, 8, 6, 4, 2
~~~

`IntStream.iterate(seed, operator)` (Java 8+) has no stopping limit in this form of call; the pipeline needs `limit` or a terminal operation that can complete according to its logic. With code that runs long enough, addition/subtraction on `int` in `iterate` can also overflow and wrap around. When **both ends are known and the step increment is 1**, `range` or `rangeClosed` communicates the intent more clearly and is easier to control.

## 9. Common Off-by-One and Overflow Errors

### 9.1. Using rangeClosed for Collection Sizes

~~~java
List<String> names = java.util.Arrays.asList("Alice", "Bob");

// Wrong: 0, 1, 2; index 2 is invalid for a 2-element list.
// IntStream.rangeClosed(0, names.size()).forEach(i -> names.get(i));

// Correct: 0, 1.
IntStream.range(0, names.size()).forEach(i -> names.get(i));
~~~

If you want to display 1-based numbering, use `index + 1` during presentation instead of generating an extra invalid element.

### 9.2. Missing the Last Value of a Business Range

~~~java
// Violates the requirement "from 1 to 10, including 10".
long nineNumbers = IntStream.range(1, 10).count(); // 9

// Meets the requirement.
long tenNumbers = IntStream.rangeClosed(1, 10).count(); // 10
~~~

A design tip: use `range(0, size)` when referring to **indices**, and use `rangeClosed(1, lastNumber)` when referring to **numbers from 1 to the last number**.

### 9.3. Adding 1 to Simulate rangeClosed

~~~java
int end = Integer.MAX_VALUE;

// Dangerous: end + 1 overflows int to Integer.MIN_VALUE.
// IntStream.range(1, end + 1);

IntStream correct = IntStream.rangeClosed(1, end);
System.out.println(correct.limit(3).boxed()
    .collect(java.util.stream.Collectors.toList())); // [1, 2, 3]
~~~

`rangeClosed` does not require the caller to manually add 1 to the upper bound, so it handles the case where `endInclusive` equals `Integer.MAX_VALUE`. Similarly, `LongStream.rangeClosed(..., Long.MAX_VALUE)` is the right way to express the bound; however, you must still consider whether the terminal operation can complete or whether overflow occurs during aggregation.

### 9.4. Assuming a Range Automatically Decreases When start Is Greater Than end

~~~java
long empty = IntStream.rangeClosed(5, 1).count(); // 0
~~~

`rangeClosed(5, 1)` **does not generate** `5, 4, 3, 2, 1`. Both methods have a fixed step increment of 1 and return an empty Stream when the bounds are in reverse order. For a decreasing sequence of known length, you can map an increasing range:

~~~java
IntStream.rangeClosed(0, 4)
    .map(index -> 5 - index)
    .forEach(System.out::println); // 5, 4, 3, 2, 1
~~~

The formula `5 - index` is safe for this small example. With extreme bounds, you need to compute using an appropriate numeric type to avoid overflow in the mapping expression.

### 9.5. Creating a Very Large Range and Forcing Full Collection

~~~java
// Risk of excessive memory and time consumption:
// int[] all = IntStream.range(0, Integer.MAX_VALUE).toArray();

// When only a few elements are needed:
int[] prefix = IntStream.range(0, Integer.MAX_VALUE)
    .limit(5)
    .toArray(); // [0, 1, 2, 3, 4]
~~~

Correct bounds are **not enough**: you must consider the terminal operation and the result size. `count()`, `sum()`, `findFirst()`, `limit()`, and `toArray()` have different resource requirements.

## 10. Combining range with Stream Operations

A number range is just a **data source**. You can attach intermediate and terminal operations to solve real problems.

| Problem | Suggested pipeline | Result |
|---|---|---|
| Count elements from 0 to 99 | `IntStream.range(0, 100).count()` | `100L` |
| Sum of even numbers from 2 to 10 | `IntStream.rangeClosed(1, 10).filter(n -> n % 2 == 0).sum()` | `30` |
| Squares from 1 to 4 | `IntStream.rangeClosed(1, 4).map(n -> n * n)` then collect | `1, 4, 9, 16` |
| Check whether 1..20 contains a multiple of 7 | `IntStream.rangeClosed(1, 20).anyMatch(n -> n % 7 == 0)` | `true` |
| Take the first 3 numbers of a large range | `LongStream.range(0L, 1_000_000_000L).limit(3)` | `0, 1, 2` |
| Generate version labels | `IntStream.rangeClosed(1, 3).mapToObj(i -> "v" + i)` | `v1, v2, v3` |

Example summing even numbers:

~~~java
int sumOfEvens = IntStream.rangeClosed(1, 10)
    .filter(number -> number % 2 == 0)
    .sum();

System.out.println(sumOfEvens); // 30
~~~

Example generating labels:

~~~java
List<String> versions = IntStream.rangeClosed(1, 3)
    .mapToObj(i -> "v" + i)
    .collect(java.util.stream.Collectors.toList());

System.out.println(versions); // [v1, v2, v3]
~~~

When processing with `parallel()`, a range source is often well suited for work splitting because its bounds are known. Even so, **a parallel Stream is not automatically faster**: splitting, combining, preserving order, and task overhead determine efficiency. Avoid side effects on shared state and only enable parallelism when there is a practical reason, benchmarked on a representative workload.

## 11. Practice Exercise: Numbering Hypothetical Workdays

An application displays a list of five workdays from Monday to Friday, numbered from 1 to 5. Requirements:

1. Create a Stream containing indices 0 to 4 using `range`.
2. Use `mapToObj` to get the corresponding day name and prepend a 1-based ordinal number.
3. Build a `List<String>` and print the list.
4. Rewrite the ordinal generation using `rangeClosed(1, 5)`.
5. Explain why `range(0, names.size())` is safe when `names` is empty.

**Reference Solution (Java 8+):**

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class RangePractice {
    public static void main(String[] args) {
        List<String> weekdays = Arrays.asList(
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"
        );

        List<String> fromIndexes = IntStream.range(0, weekdays.size())
            .mapToObj(i -> (i + 1) + ". " + weekdays.get(i))
            .collect(Collectors.toList());

        List<String> fromOrdinal = IntStream.rangeClosed(1, weekdays.size())
            .mapToObj(number -> number + ". " + weekdays.get(number - 1))
            .collect(Collectors.toList());

        System.out.println(fromIndexes);
        System.out.println(fromIndexes.equals(fromOrdinal)); // true
    }
}
~~~

Output:

~~~text
[1. Monday, 2. Tuesday, 3. Wednesday, 4. Thursday, 5. Friday]
true
~~~

In the first approach, the variable `i` is a **0-based index**, so 1 is added when displaying. In the second approach, `number` is already a **1-based ordinal number**, so 1 must be subtracted when accessing the List. When `weekdays` is empty, both `range(0, 0)` and `rangeClosed(1, 0)` return an empty Stream, so there is no out-of-bounds index access.

**Self-Check:**

- How many elements does `IntStream.range(3, 3)` have? — **0**.
- How many elements does `IntStream.rangeClosed(3, 3)` have? — **1**, which is the number 3.
- Does `IntStream.rangeClosed(3, 1)` emit 3, 2, 1? — **No**, the Stream is empty.
- What type does `IntStream.range(0, 10).count()` return? — **`long`**, with value `10L`.
- Does `rangeClosed(1, Integer.MAX_VALUE)` need 1 added to the bound? — **No**, and you should not do so.
- What type of Stream does `IntStream.range(1, 100).mapToObj(i -> "ID-" + i)` return? — **`Stream<String>`**.

## 12. Key Takeaways Before Moving to Other Sequences

**`IntStream.range(start, end)`** and **`LongStream.range(start, end)`** include `start` and exclude `end`. **`rangeClosed(start, end)`** includes both. Both create **finite, consecutive integer sequences increasing by one**, and create a Stream source rather than requiring all values to be stored in memory upfront.

When designing a pipeline, answer four questions: **is the upper bound included**, **is the numeric type `int` or `long`**, **how large can the result be**, and **how much time/memory does the terminal operation need**. From a range source, you can apply `filter`, `map`, `reduce`, `collect`, grouping, or numeric computations; when you need an infinite sequence, an arbitrary step size, or a different element-generation rule, continue learning about `iterate` and `generate` along with appropriate stopping limits.
