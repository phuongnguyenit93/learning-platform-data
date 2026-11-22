# Creating Primitive Sources from Arrays, Ranges, and Generators

In Java programs, we frequently process sequences of numbers such as test scores, product quantities, element indices, timestamps, or measurement data. With the **Java Stream API**, instead of always converting them into `List<Integer>` or `List<Double>`, you can create **primitive streams** directly from **arrays**, **number ranges**, or **value generators**.

This lesson belongs to the **Primitive Streams** chapter of the **JAVA_STREAM_API** module. You will learn how to choose between `IntStream`, `LongStream`, and `DoubleStream`, create finite or unbounded sources, connect sources with `filter`, `map`, `reduce`, and `collect` pipelines, and recognize limits regarding state, resources, and performance. This lays the groundwork for deeper understanding of `Spliterator`, parallel processing, and pipeline extension mechanisms such as Stream Gatherers.

## 1. Three primitive Stream types in Java

`java.util.stream` provides three specialized interfaces for primitive numeric types:

| Stream Type | Element Type | Source Example | Useful Operations |
|---|---|---|---|
| `IntStream` | `int` | `IntStream.of(1, 2)` | `sum()`, `average()`, `min()`, `max()` |
| `LongStream` | `long` | `LongStream.range(1L, 5L)` | `sum()`, `average()`, `min()`, `max()` |
| `DoubleStream` | `double` | `DoubleStream.of(1.5, 2.5)` | `sum()`, `average()`, `min()`, `max()` |

**There is no `FloatStream`, `ShortStream`, or `ByteStream` in the standard API.** Values smaller than `int` can be processed using `IntStream`; `float` values can be fed into `DoubleStream` when appropriate, keeping floating-point representation caveats in mind.

Compared to `Stream<Integer>`, `Stream<Long>`, and `Stream<Double>`, primitive streams allow many arithmetic operations to work directly on `int`, `long`, and `double` values. This generally avoids the **boxing/unboxing** cost of wrapping primitive numbers into wrapper objects. Specific performance benefits still depend on the pipeline and actual data.

Example:

~~~java
import java.util.stream.IntStream;

int sum = IntStream.of(10, 20, 30)
    .filter(n -> n >= 20)
    .sum();

System.out.println(sum); // 50
~~~

`IntStream.of(...)` is the **source**; `filter(...)` is an **intermediate** operation; `sum()` is a **terminal** operation. Lazy pipeline rules and the single-use lifecycle still apply just as with `Stream<T>`.

## 2. Map of source creation methods

There are three main groups within the scope of this lesson:

~~~mermaid
flowchart TD
    A["Primitive Stream Sources"] --> B["From arrays or existing values"]
    A --> C["From consecutive integer ranges"]
    A --> D["From value generation rules"]
    B --> E["Arrays.stream / of"]
    C --> F["IntStream.range / rangeClosed"]
    C --> G["LongStream.range / rangeClosed"]
    D --> H["iterate: next element from previous"]
    D --> I["generate: pull value from Supplier"]
    E --> J["filter / map / sum / average / toArray"]
    F --> J
    G --> J
    H --> J
    I --> J
~~~

| Need | Preferred API | Source Kind |
|---|---|---|
| Already have an `int[]`, `long[]`, or `double[]` array | `Arrays.stream(array)` | Finite |
| Only have a few fixed numbers | `IntStream.of(...)`, `LongStream.of(...)`, `DoubleStream.of(...)` | Finite |
| Need indices from 0 to `size - 1` | `IntStream.range(0, size)` | Finite |
| Need numbers from 1 to `n`, including `n` | `IntStream.rangeClosed(1, n)` | Finite |
| Each next element depends on the previous one | `IntStream.iterate(seed, next)` | Potentially infinite |
| Need a sequence iterating up to a stopping condition | `IntStream.iterate(seed, hasNext, next)` (Java 9+) | Has termination condition |
| Each element comes from an independent provider | `DoubleStream.generate(supplier)` | Potentially infinite |
| Need random numbers with a defined range and size | `Random.ints(size, origin, bound)` or corresponding family | Finite |

**Note:** `range` and `rangeClosed` exist only on **`IntStream` and `LongStream`**. There is no `DoubleStream.range()` in the standard Java Stream API.

## 3. Creating a Stream from primitive arrays with Arrays.stream

The most common way when data is already stored in an array is to use the overloads of `java.util.Arrays.stream`:

~~~java
import java.util.Arrays;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

int[] quantities = {2, 4, 6};
long[] timestamps = {1_000L, 2_000L, 3_000L};
double[] temperatures = {21.5, 22.0, 20.5};

IntStream quantitiesStream = Arrays.stream(quantities);
LongStream timestampsStream = Arrays.stream(timestamps);
DoubleStream temperaturesStream = Arrays.stream(temperatures);

System.out.println(quantitiesStream.sum());           // 12
System.out.println(timestampsStream.max().orElse(-1L)); // 3000
System.out.println(temperaturesStream.average().orElse(Double.NaN)); // 21.3333...
~~~

Each `Arrays.stream(array)` call returns a Stream whose element type matches the array type. The same array can create **multiple independent Streams**, though each Stream object should be consumed **only once**.

### 3.1. Reading only a slice of an array

`Arrays.stream` also has overloads accepting `startInclusive` and `endExclusive`:

~~~java
import java.util.Arrays;

int[] scores = {10, 20, 30, 40, 50};

int sum = Arrays.stream(scores, 1, 4)
    .sum();

System.out.println(sum); // 20 + 30 + 40 = 90
~~~

The index range `[1, 4)` includes positions **1, 2, 3**. Position 4 is excluded.

- `Arrays.stream(array, 0, array.length)` reads the entire array.
- `Arrays.stream(array, 2, 2)` returns an empty Stream.
- Invalid bounds (e.g., `from > to` or out of array bounds) trigger an index check error rather than silently shrinking to a valid slice.

This follows the same **half-open** boundary convention as `IntStream.range(start, end)` and generally helps reduce *off-by-one* errors.

### 3.2. Avoid confusing Stream<int[]> with IntStream

`Stream.of(array)` behaves differently from `Arrays.stream(array)` when `array` is a primitive array:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

int[] values = {1, 2, 3};

long wrongCount = Stream.of(values).count(); // 1
long rightCount = Arrays.stream(values).count(); // 3

System.out.println(wrongCount); // 1: a single element of type int[]
System.out.println(rightCount); // 3: three elements of type int
~~~

Here `Stream.of(values)` creates a **`Stream<int[]>`** containing the entire array as **one element**. If you want to process individual `int` numbers, use `Arrays.stream(values)` or `IntStream.of(values)`.

### 3.3. Source arrays and state mutation

`Arrays.stream(array)` creates a source backed by the supplied array; do not assume it is an immutable copy of the data. Modifying the array while the pipeline is traversing it can violate **non-interference** requirements and lead to unpredictable results, especially in parallel processing.

If you need a point-in-time snapshot of the data, copy it first and then create the source from the copy:

~~~java
import java.util.Arrays;

int[] measurements = {5, 7, 9};
int[] snapshot = Arrays.copyOf(measurements, measurements.length);

int total = Arrays.stream(snapshot).sum(); // 21
~~~

Copying incurs memory overhead proportional to the array size. Use it only when you need to stabilize the source data or protect against external mutations.

## 4. Creating a Stream from existing values: of and empty

When you only need a few literal values directly, `of(...)` is more concise than allocating a separate array:

~~~java
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

int totalItems = IntStream.of(2, 3, 5).sum();             // 10
long largestId = LongStream.of(10L, 20L, 30L).max()
    .orElse(-1L);                                           // 30
double totalWeight = DoubleStream.of(0.5, 1.25, 2.0).sum(); // 3.75

System.out.println(totalItems);
System.out.println(largestId);
System.out.println(totalWeight);
~~~

`of` has a single-value overload and a **varargs** overload. You can also pass an array of the matching type:

~~~java
int[] values = {4, 5, 6};
int[] copyOfValuesAsResult = IntStream.of(values).toArray();

System.out.println(java.util.Arrays.toString(copyOfValuesAsResult)); // [4, 5, 6]
~~~

To represent a source with no elements:

~~~java
long count = IntStream.empty().count(); // 0
int sum = IntStream.empty().sum();      // 0
boolean hasValue = IntStream.empty().findFirst().isPresent(); // false
~~~

`IntStream.empty()`, `LongStream.empty()`, and `DoubleStream.empty()` avoid allocating an empty array. However, an aggregate operation on an empty Stream does not always return 0: `average()`, `min()`, and `max()` return empty `Optional` variants without a value.

## 5. Creating numeric ranges with range and rangeClosed

`IntStream` and `LongStream` provide consecutive number range sources with a step increment of **1**.

~~~java
IntStream.range(int startInclusive, int endExclusive)
IntStream.rangeClosed(int startInclusive, int endInclusive)

LongStream.range(long startInclusive, long endExclusive)
LongStream.rangeClosed(long startInclusive, long endInclusive)
~~~

In mathematical notation:

- `range(a, b)` generates numbers from `a` up to **before `b`**, corresponding to `[a, b)`.
- `rangeClosed(a, b)` generates numbers from `a` up to **and including `b`**, corresponding to `[a, b]`.

| Example | Values | Element Count |
|---|---|---|
| `IntStream.range(1, 5)` | `1, 2, 3, 4` | 4 |
| `IntStream.rangeClosed(1, 5)` | `1, 2, 3, 4, 5` | 5 |
| `IntStream.range(5, 5)` | Empty | 0 |
| `IntStream.rangeClosed(5, 5)` | `5` | 1 |
| `LongStream.rangeClosed(-2L, 1L)` | `-2, -1, 0, 1` | 4 |
| `IntStream.rangeClosed(6, 3)` | Empty | 0 |

When `start >= end`, `range` returns an empty sequence; when `start > end`, `rangeClosed` returns an empty sequence. Neither **automatically generates a descending sequence** when the start point is greater than the end point.

### 5.1. Indexing elements in a list

Valid positions in a `List` of `n` elements are `0` to `n - 1`. Therefore, `range(0, n)` is particularly well suited for index-based processing:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.stream.IntStream;

List<String> names = Arrays.asList("An", "Binh", "Chi");

IntStream.range(0, names.size())
    .mapToObj(index -> (index + 1) + ". " + names.get(index))
    .forEach(System.out::println);
~~~

Output:

~~~text
1. An
2. Binh
3. Chi
~~~

Do not use `rangeClosed(0, names.size())` for indices: it emits `names.size()` as well and will cause an `IndexOutOfBoundsException` when accessing that non-existent last index.

For a `List` with slow indexed access like `LinkedList`, calling `get(index)` repeatedly can be inefficient. If the position is not needed, `names.stream()` is usually clearer and more appropriate.

### 5.2. Generating sequential ordinal values, including the final value

~~~java
int sum1To5 = IntStream.rangeClosed(1, 5).sum(); // 15
long count = LongStream.range(100L, 105L).count(); // 5

System.out.println(sum1To5);
System.out.println(count);
~~~

Use `rangeClosed` when the business requirement states “from 1 **through** 5”, or “days from the 1st **to the last day of the month**”.

### 5.3. Numeric type limits and overflow

Do not simulate a closed range by always writing `range(start, end + 1)`, because `end + 1` can overflow at `Integer.MAX_VALUE` or `Long.MAX_VALUE`.

~~~java
import java.util.stream.IntStream;

int last = Integer.MAX_VALUE;

int[] tail = IntStream.rangeClosed(last - 2, last)
    .toArray();

System.out.println(java.util.Arrays.toString(tail));
// [2147483645, 2147483646, 2147483647]
~~~

Distinguish between **the ability to describe a source** and **the ability to collect or aggregate the entire source**. A massive range is valid as a source, yet `toArray()` may be unsuitable due to memory/array-size limits.

In particular, `IntStream.sum()` returns `int` and `LongStream.sum()` returns `long`: both can overflow when the sum exceeds the representable range. For example, to sum many `int` values whose total exceeds `int`, convert to `long` **before** summing:

~~~java
long safeSum = IntStream.rangeClosed(1, 100_000)
    .asLongStream()
    .sum();

System.out.println(safeSum); // 5000050000
~~~

`asLongStream()` widens each `int` value to `long`; it does not turn `long` into an arbitrary-precision integer. If the sum can still exceed `long`, another approach and numeric type (such as `BigInteger`) is needed.

## 6. iterate: generating the next element from the previous one

When you want an **arithmetic progression with a step other than 1**, a **geometric progression**, or a numeric sequence where the next element depends on the previous one, use `iterate`.

The two-argument overloads have existed since **Java 8**:

~~~java
IntStream.iterate(int seed, IntUnaryOperator next)
LongStream.iterate(long seed, LongUnaryOperator next)
DoubleStream.iterate(double seed, DoubleUnaryOperator next)
~~~

`seed` is the initial value. The `next` function computes the next value from the preceding one. This form describes a **sequential, ordered, and potentially unbounded source**: it has no built-in stopping condition.

### 6.1. Arithmetic progression

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] evens = IntStream.iterate(0, n -> n + 2)
    .limit(6)
    .toArray();

System.out.println(Arrays.toString(evens)); // [0, 2, 4, 6, 8, 10]
~~~

Values are generated in sequence:

~~~text
seed = 0
next(0) = 2
next(2) = 4
next(4) = 6
...
limit(6) -> take only 6 values
~~~

**`limit(6)` is critical**: calling `toArray()` on an unbounded `iterate` source without a limiting operation prevents the pipeline from ever finishing collection and can exhaust resources until an error occurs.

### 6.2. Geometric progression

~~~java
long[] powersOfTwo = LongStream.iterate(1L, n -> n * 2)
    .limit(6)
    .toArray();

System.out.println(java.util.Arrays.toString(powersOfTwo));
// [1, 2, 4, 8, 16, 32]
~~~

The example limits to six elements so no overflow occurs; if multiplication continues unbounded, `long` will eventually overflow.

### 6.3. iterate with a stopping condition (Java 9+)

Java 9 added the three-argument overload:

~~~java
IntStream.iterate(int seed, IntPredicate hasNext, IntUnaryOperator next)
LongStream.iterate(long seed, LongPredicate hasNext, LongUnaryOperator next)
DoubleStream.iterate(double seed, DoublePredicate hasNext, DoubleUnaryOperator next)
~~~

`hasNext` is tested against each candidate value to decide **whether to emit that value into the Stream**. Once false, the Stream terminates and that value is not emitted.

~~~java
int[] numbers = IntStream.iterate(
        3,               // seed
        n -> n <= 15,    // emit only values <= 15
        n -> n + 3       // next element
    )
    .toArray();

System.out.println(java.util.Arrays.toString(numbers));
// [3, 6, 9, 12, 15]
~~~

The difference from `rangeClosed(3, 15)` is that `iterate` above has a step of **3**, not 1. When you already have a contiguous range increasing by 1, `range` or `rangeClosed` is usually shorter and clearer.

**Watch out for stopping conditions and overflow:** if the `next` function overflows before `hasNext` can stop it, the next value can become unexpected. For data near integer limits, choose a verifiable step expression or control the total element count beforehand with a safe index range.

### 6.4. Why not use DoubleStream.iterate to count exact steps?

~~~java
double[] fractions = DoubleStream.iterate(0.0, x -> x + 0.1)
    .limit(4)
    .toArray();
~~~

This sequence logically represents `0.0, 0.1, 0.2, 0.3`, yet binary floating-point numbers can produce representations such as `0.30000000000000004`. If the **number of steps** must be exact, generate integer indices first and then map them:

~~~java
double[] values = IntStream.range(0, 4)
    .mapToDouble(i -> i / 10.0)
    .toArray();
~~~

The latter has exactly four steps and avoids accumulating error through repeated addition, though `double` itself **still cannot represent every decimal number exactly**. For money or calculations requiring exact decimal arithmetic, establish integer unit conventions or use `BigDecimal`.

## 7. generate: pulling each value from a Supplier

`generate` is suitable when values are supplied by a **generator function** (*supplier*). Unlike `iterate`, there is no previous-element parameter:

~~~java
IntStream.generate(IntSupplier supplier)
LongStream.generate(LongSupplier supplier)
DoubleStream.generate(DoubleSupplier supplier)
~~~

Each supplier returns a corresponding primitive value via `getAsInt()`, `getAsLong()`, or `getAsDouble()`.

### 7.1. Generating a constant value

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] defaults = IntStream.generate(() -> -1)
    .limit(4)
    .toArray();

System.out.println(Arrays.toString(defaults)); // [-1, -1, -1, -1]
~~~

`generate(() -> -1)` creates an **unbounded** source, yet `limit(4)` causes the pipeline to pull only the four needed values.

A source produced by `generate` is **sequential, unordered** by the API contract. `unordered` here does not mean the displayed output is always randomly shuffled; it means the API does not promise an *encounter order* that downstream operations must preserve.

### 7.2. Simulated data from a random generator

~~~java
import java.util.Random;

Random random = new Random(42L);

int[] diceRolls = IntStream.generate(() -> random.nextInt(6) + 1)
    .limit(5)
    .toArray();

System.out.println(java.util.Arrays.toString(diceRolls));
// Five values from 1 to 6 (duplicates possible).
~~~

`Random(42L)` uses a deterministic seed, which is useful when you want reproducible examples or tests. For generating a **random sample with a fixed element count and value range**, `Random.ints(...)` in the next section is usually shorter.

Because `Random` shares mutable state, **do not blindly turn on `parallel()` for a supplier sharing a single mutable object** and expect the same call order or count as a sequential pipeline. For parallel streams, choose thread-safe generators and architectures; also never use ordinary random generators for security tokens or passwords.

### 7.3. Distinguishing iterate and generate

| Feature | `iterate` | `generate` |
|---|---|---|
| Starts with | `seed` | `Supplier` |
| Next value | Function taking the previous value | Supplier returning a new value |
| Encounter order | Ordered | Unordered |
| Default source | Potentially unbounded | Unbounded |
| How to bound | `limit` or overload with `hasNext` | `limit`, `takeWhile`, or suitable short-circuiting operation |
| Best suited for | Mathematical sequences, recurrence rules | Default values, simulations, data feeds |

`takeWhile` (Java 9+) can truncate a source based on a condition, yet on an **unordered** source, its element selection behavior differs from an ordered source. When you need “exactly N values”, `limit(N)` is the clearer choice.

## 8. Generating random numbers with dedicated source APIs

`java.util.Random` has provided primitive Stream creation methods since Java 8:

~~~java
Random.ints()
Random.ints(long streamSize)
Random.ints(long streamSize, int randomNumberOrigin, int randomNumberBound)

Random.longs(...)
Random.doubles(...)
~~~

The corresponding overloads can generate **unbounded** sources or **finite sources of length `streamSize`**. For overloads taking `origin` and `bound`, the value range is typically **`[origin, bound)`**: lower bound inclusive, upper bound exclusive.

Complete example:

~~~java
import java.util.Arrays;
import java.util.Random;

public class RandomPrimitiveSources {
    public static void main(String[] args) {
        Random random = new Random(123L);

        // 6 dice rolls: each number in [1, 7), i.e., 1..6.
        int[] rolls = random.ints(6, 1, 7).toArray();

        // 3 double values in [0.0, 1.0).
        double[] samples = random.doubles(3, 0.0, 1.0).toArray();

        System.out.println(Arrays.toString(rolls));
        System.out.println(Arrays.toString(samples));
    }
}
~~~

The call `ints(6, 1, 7)` returns a **6-element** `IntStream`, and `doubles(3, 0.0, 1.0)` returns a **3-element** `DoubleStream`. Specific values depend on the seed and draw sequence; elements may repeat. This is random sampling and does not guarantee “six distinct values”.

Besides `Random`, Java provides `SplittableRandom` with `ints`, `longs`, and `doubles` methods, designed so generators can be split when building parallel algorithms. Choosing a generator should be based on statistical requirements, reproducibility, thread safety, and security level; **`Random` and `SplittableRandom` are not cryptographic generators**.

## 9. Stream sources and transformations to primitive types

Data is not always available as `int[]` or `double[]`. Sometimes the source is a `Stream<T>` containing business objects:

~~~java
import java.util.Arrays;
import java.util.List;

class Order {
    private final long amount;

    Order(long amount) {
        this.amount = amount;
    }

    long amount() {
        return amount;
    }
}

List<Order> orders = Arrays.asList(
    new Order(120_000L),
    new Order(80_000L),
    new Order(50_000L)
);

long total = orders.stream()
    .mapToLong(Order::amount)
    .sum();

System.out.println(total); // 250000
~~~

`mapToLong` converts an object Stream into a `LongStream`; `mapToInt` and `mapToDouble` play corresponding roles. This is a **continuation source from an existing pipeline**, not an initial array/range/generator, yet it is a vital bridge when learning declarative data processing.

If you need to return to an object Stream:

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> boxed = IntStream.rangeClosed(1, 3)
    .boxed()
    .collect(Collectors.toList());

System.out.println(boxed); // [1, 2, 3]
~~~

`boxed()` converts `IntStream` to `Stream<Integer>`; the same applies to `long` and `double`. Boxing can incur extra memory and allocation costs; keep Streams primitive when the purpose is solely numeric calculation.

## 10. Lazy evaluation, bounding, and source lifecycle

Creating a source **does not mean all elements have already been computed**. Intermediate operations are typically *lazy*, and only the terminal operation requests the needed data:

~~~java
import java.util.stream.IntStream;

IntStream pipeline = IntStream.iterate(1, n -> n + 1)
    .filter(n -> n % 5 == 0)
    .limit(3);

System.out.println("Pipeline declared");

int[] result = pipeline.toArray();
System.out.println(java.util.Arrays.toString(result));
~~~

Output:

~~~text
Pipeline declared
[5, 10, 15]
~~~

The pipeline is described first; `toArray()` triggers computing the first three numbers divisible by 5.

### 10.1. Choose where to place limit carefully

~~~java
int[] a = IntStream.iterate(1, n -> n + 1)
    .filter(n -> n % 2 == 0)
    .limit(3)
    .toArray(); // [2, 4, 6]

int[] b = IntStream.iterate(1, n -> n + 1)
    .limit(3)
    .filter(n -> n % 2 == 0)
    .toArray(); // [2]
~~~

Both terminate, yet **`filter → limit`** takes three results matching the condition, whereas **`limit → filter`** inspects only the first three source elements and then filters them.

### 10.2. Some pipelines cannot complete

The examples below **should not be run** without a stopping mechanism or resource bound:

~~~java
// Unbounded source, terminal operation wants to count every element:
// IntStream.generate(() -> 1).count();

// Sorting an entire unbounded source before taking a few elements:
// IntStream.iterate(0, n -> n + 1)
//     .sorted()
//     .limit(5)
//     .toArray();
~~~

`limit(5)` **placed after** `sorted()` does not save an unbounded source: `sorted` must inspect the entire source before it can return sorted results. With unbounded sources, check stateful intermediate operations and truncation points very carefully.

### 10.3. Do not reuse a consumed Stream

~~~java
IntStream stream = IntStream.rangeClosed(1, 5);
int sum = stream.sum(); // 15

// Wrong: reusing the same terminated Stream object.
// long count = stream.count();

// Right: create a new Stream from a recreatable source.
long count = IntStream.rangeClosed(1, 5).count(); // 5
~~~

A Stream serves only one terminal pipeline. If you want to read multiple times from an array, create multiple Streams from the array; if the source comes from a stateful generator, each recreation may produce **different data**. When comparing the same data is required, manage snapshots or appropriate seeds/generation strategies.

## 11. Performance, state, and parallel processing

Primitive streams generally reduce boxing, yet **do not automatically guarantee being faster than loops**. Execution time and memory also depend on source creation, element count, operations, short-circuiting capability, and actual JDK implementation.

### 11.1. Finite and unbounded sources

- `Arrays.stream(array)` traverses an existing array; the main data storage cost already exists in the array.
- `range` and `rangeClosed` represent mathematical sequences without needing to pre-allocate an array holding every number.
- `iterate` generates values from previous ones; when computation has sequential dependencies, parallelizability may be limited.
- `generate` pulls data from a supplier; if the supplier holds mutable state or uses external resources, correctness and termination must be controlled.

Do not collect a huge source into `toArray()` just to count or sum: `count()` or `sum()` is usually clearer in intent and avoids storing all elements. Even so, `sum()` still has overflow limits and floating-point operations have rounding error.

### 11.2. Side effects in suppliers and mappers

With Streams, do not rely on a supplier or intermediate lambda being invoked **an exact number of times**, **in a specific order**, or **on a specific thread** unless there is a contract guaranteeing it.

The following example carries risk if used as a business ID generator:

~~~java
java.util.concurrent.atomic.AtomicInteger counter =
    new java.util.concurrent.atomic.AtomicInteger();

int[] ids = IntStream.generate(counter::incrementAndGet)
    .parallel()
    .limit(10)
    .toArray();
~~~

Although `AtomicInteger` increments the variable atomically, using a shared counter in a parallel unordered source makes the contents and order of results unpredictable. When you need exact `1..10`, **`IntStream.rangeClosed(1, 10)`** expresses the requirement directly and is easier to verify.

### 11.3. When to consider parallel?

`IntStream.range(...)` and `LongStream.range(...)` are typically favorable for splitting because their bounds are known. However, enabling `parallel()` incurs scheduling, coordination, and result-combining overhead. Consider it only when the workload is sufficiently large, has minimal side effects, can split independently, and shows measured benefit.

With a random generator or an I/O source, do not assume enabling parallel always increases throughput. If work depends on order or source state, the processing design may need to change before yielding performance gains.

## 12. Complete application example: sensor measurement analysis

Suppose an application receives an array of temperatures from a sensor and needs to compute the average, filter values above a threshold, and generate a sequence of sample reading labels. We use three source creation approaches: array, range, and simulated generator.

**Java 17+ example** (the code uses Stream APIs available since Java 8):

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;

public class PrimitiveStreamSourcesDemo {
    public static void main(String[] args) {
        double[] temperatures = {21.5, 23.0, 19.5, 25.0, 22.0};

        // 1. From array: compute average, handling empty case.
        double average = Arrays.stream(temperatures)
            .average()
            .orElse(Double.NaN);

        // 2. From array: filter readings of 23 degrees C or higher.
        double[] hotReadings = Arrays.stream(temperatures)
            .filter(t -> t >= 23.0)
            .toArray();

        // 3. From range: each element corresponds to an array index.
        String[] labels = IntStream.range(0, temperatures.length)
            .mapToObj(i -> "Reading " + (i + 1) + ": " + temperatures[i])
            .toArray(String[]::new);

        // 4. From generator: create 3 default values for demonstration.
        double[] defaults = DoubleStream.generate(() -> 20.0)
            .limit(3)
            .toArray();

        System.out.printf(Locale.ROOT, "Average: %.2f%n", average);
        System.out.println("Above threshold: " + Arrays.toString(hotReadings));
        System.out.println("Labels: " + Arrays.toString(labels));
        System.out.println("Defaults: " + Arrays.toString(defaults));
    }
}
~~~

Output:

~~~text
Average: 22.20
Above threshold: [23.0, 25.0]
Labels: [Reading 1: 21.5, Reading 2: 23.0, Reading 3: 19.5, Reading 4: 25.0, Reading 5: 22.0]
Defaults: [20.0, 20.0, 20.0]
~~~

The same dataset is used across **three separate pipelines** created from `Arrays.stream(temperatures)` and `IntStream.range(...)`, while `DoubleStream.generate(...)` is an independent simulated source. Never reuse a Stream after a terminal operation has been invoked on it.

In real sensor processing, you must determine whether `NaN`, infinity, missing data, or I/O exceptions are acceptable; do not treat `Double.NaN` as a valid temperature if business rules require clean data.

## 13. Practice exercises and solutions

**Exercise 1 — From an array:** Given `int[] numbers = {3, 5, 7, 9, 11};`, take the three elements at positions 1, 2, 3 and compute their sum.

~~~java
int[] numbers = {3, 5, 7, 9, 11};

int sum = java.util.Arrays.stream(numbers, 1, 4)
    .sum();

System.out.println(sum); // 5 + 7 + 9 = 21
~~~

**Exercise 2 — From a range:** Generate even numbers from 2 to 12, inclusive. You can use `rangeClosed` combined with `filter`:

~~~java
int[] evens = IntStream.rangeClosed(2, 12)
    .filter(n -> n % 2 == 0)
    .toArray();

System.out.println(java.util.Arrays.toString(evens));
// [2, 4, 6, 8, 10, 12]
~~~

**Exercise 3 — From iterate:** Generate five powers of 3 starting from 1:

~~~java
int[] powers = IntStream.iterate(1, n -> n * 3)
    .limit(5)
    .toArray();

System.out.println(java.util.Arrays.toString(powers));
// [1, 3, 9, 27, 81]
~~~

**Exercise 4 — From generate:** Generate four `2.5` values:

~~~java
double[] values = DoubleStream.generate(() -> 2.5)
    .limit(4)
    .toArray();

System.out.println(java.util.Arrays.toString(values));
// [2.5, 2.5, 2.5, 2.5]
~~~

**Self-check questions:**

1. What does `Arrays.stream(new int[] {1, 2}).count()` return? — **2**.
2. What does `Stream.of(new int[] {1, 2}).count()` return? — **1** because the element is a single `int[]`.
3. How do `IntStream.range(2, 5)` and `rangeClosed(2, 5)` differ? — The former **excludes 5**, while the latter **includes 5**.
4. Does `DoubleStream.range(0, 10)` exist? — **No**, not in the standard Java Stream API.
5. Does `IntStream.iterate(1, n -> n * 2)` terminate on its own? — **No**, this form requires an appropriate limit.
6. How many numbers does `IntStream.generate(() -> 3).limit(4)` emit? — **4**, all equal to 3.
7. What does `average()` on an empty primitive Stream return? — An **empty `OptionalDouble`**.
8. Is `IntStream.rangeClosed(1, 100_000).sum()` reliable for computing the exact sum? — **No**, the sum exceeds the representational capacity of `int`; consider `asLongStream().sum()`.

## 14. Takeaways and choosing a source

Choose a source according to **the nature of the data to be produced**:

- **Data already in an array:** `Arrays.stream(int[]/long[]/double[])` or `IntStream.of(array)`.
- **A few fixed values:** `of(...)`; no values uses `empty()`.
- **A consecutive integer range:** `IntStream.range`, `rangeClosed`, or the `LongStream` counterparts.
- **A rule based on the previous element:** `iterate(seed, next)`; if a stopping condition is needed, use the three-argument overload from Java 9.
- **A source providing independent values one by one:** `generate(supplier)`; for random numbers, consider `Random.ints/longs/doubles` and finite overloads.

Regardless of the source, you still must decide on the **termination condition**, **numeric type and overflow risk**, **lambda state/side effects**, and **cost of the terminal operation**. Mastering these factors helps combine `filter`, `map`, `reduce`, and `collect` properly, and progress toward grouping, custom collectors, `Spliterator`, parallel Streams, and Stream Gatherers in a controlled manner.
