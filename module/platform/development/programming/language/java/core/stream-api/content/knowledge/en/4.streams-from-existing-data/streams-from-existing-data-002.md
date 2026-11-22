# Creating a Stream from an Array with `Arrays.stream`

In the **Streams from Existing Data** chapter of **JAVA_STREAM_API**, `Arrays.stream` is the direct way to bring data already stored in a Java array into a declarative processing pipeline. Instead of manually writing loops to filter, transform, or aggregate elements, you can create a Stream from an array and combine operations like `filter`, `map`, `reduce`, `collect`, and other terminal operations.

The key point to understand clearly is that **the array is the data source**, whereas **the Stream is an object describing a single processing pass over that data**. `Arrays.stream` does not turn an array into a collection and does not create a copy of the entire array immediately when called. The created Stream uses lazy evaluation and follows the rule that each Stream may only be used for one pipeline.

## 1. How Does `Arrays.stream` Work?

`Arrays` is a utility class in `java.util`. Its `stream` methods take an array or an index range of an array and return a *sequential stream* whose elements come from that array.

The example below is a complete Java program:

~~~java
import java.util.Arrays;
import java.util.List;

public class ArraysStreamDemo {
    public static void main(String[] args) {
        String[] names = {"Lan", "Minh", "Linh", "An"};

        List<String> result = Arrays.stream(names)
                .filter(name -> name.length() >= 4)
                .map(String::toUpperCase)
                .sorted()
                .toList();

        System.out.println(result); // [LINH, MINH]
    }
}
~~~

Data flow:

~~~text
String[] names
      |
      v
Arrays.stream(names)  -> Stream<String>
      |
      v
filter(length >= 4)   -> "Minh", "Linh"
      |
      v
map(toUpperCase)      -> "MINH", "LINH"
      |
      v
sorted()              -> "LINH", "MINH"
      |
      v
toList()              -> List<String>
~~~

`filter`, `map`, and `sorted` are intermediate operations; `toList` is the terminal operation that triggers processing and produces the result. `Stream.toList()` has been available since Java 16 and creates an unmodifiable list. If studying on Java 8–15, you can replace `.toList()` with `.collect(Collectors.toList())`; you need `import java.util.stream.Collectors;` and should not assume that this collector's result is always mutable.

## 2. Common Forms of `Arrays.stream`

The API specifically supports object arrays and three primitive array types: `int[]`, `long[]`, and `double[]`.

| Input data | Example | Returned Stream type |
| --- | --- | --- |
| Reference array `T[]` | `Arrays.stream(new String[]{"A", "B"})` | `Stream<String>` |
| `int[]` array | `Arrays.stream(new int[]{1, 2})` | `IntStream` |
| `long[]` array | `Arrays.stream(new long[]{1L, 2L})` | `LongStream` |
| `double[]` array | `Arrays.stream(new double[]{1.5, 2.5})` | `DoubleStream` |
| A slice of `T[]` | `Arrays.stream(items, from, to)` | `Stream<T>` |
| A slice of `int[]`, `long[]`, `double[]` | `Arrays.stream(numbers, from, to)` | `IntStream`, `LongStream`, `DoubleStream` respectively |

Representative signatures:

~~~java
static <T> Stream<T> stream(T[] array)
static <T> Stream<T> stream(T[] array, int startInclusive, int endExclusive)

static IntStream stream(int[] array)
static IntStream stream(int[] array, int startInclusive, int endExclusive)

static LongStream stream(long[] array)
static LongStream stream(long[] array, int startInclusive, int endExclusive)

static DoubleStream stream(double[] array)
static DoubleStream stream(double[] array, int startInclusive, int endExclusive)
~~~

There are no overloads for `Arrays.stream(byte[])`, `Arrays.stream(short[])`, `Arrays.stream(char[])`, `Arrays.stream(float[])`, or `Arrays.stream(boolean[])`. You need to use alternative approaches if the input has those types; see section 8.

## 3. Creating `Stream<T>` from an Object Array

`String[]`, `Integer[]`, `Customer[]`, or any reference-type array can create a `Stream<T>`. From there, operations like `map`, `filter`, `distinct`, `sorted`, and `collect` are chained just like with a Stream from a Collection.

Suppose an array records sold product names, with elements having extra whitespace or duplicates:

~~~java
import java.util.Arrays;
import java.util.List;

String[] soldProducts = {"  Pen", "Notebook", "Pen", " ", "Book", "  Notebook"};

List<String> uniqueNames = Arrays.stream(soldProducts)
        .map(String::trim)
        .filter(name -> !name.isEmpty())
        .distinct()
        .sorted()
        .toList();

System.out.println(uniqueNames); // [Book, Notebook, Pen]
~~~

In this pipeline, `map` normalizes strings, `filter` removes empty strings, `distinct` removes duplicate elements, and `sorted` sorts them. Intermediate operations do not return a new array; they describe how data will be processed when the terminal operation `toList` runs.

If the goal is to **count occurrences** instead of deduplicating, you can feed the array Stream into a collector:

~~~java
import java.util.Arrays;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

String[] states = {"new", "done", "new", "waiting", "done", "new"};

Map<String, Long> counts = Arrays.stream(states)
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));

System.out.println(counts.get("new"));     // 3
System.out.println(counts.get("done"));    // 2
System.out.println(counts.get("waiting")); // 1
~~~

This is an example of chaining `Arrays.stream` with `collect` and `groupingBy`. Do not rely on the iteration order of keys in the default `Map` returned by `groupingBy`.

### Handling `null` Elements in a Reference Array

An array itself can contain `null` elements; that does not prevent creating a Stream. However, operations like `String::trim` or `String::length` will fail if they receive a `null` value.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

String[] labels = {"java", null, "stream"};

List<String> upper = Arrays.stream(labels)
        .filter(Objects::nonNull)
        .map(String::toUpperCase)
        .toList();

System.out.println(upper); // [JAVA, STREAM]
~~~

Clearly distinguish between **an array containing `null` elements** and **the array reference variable itself being `null`**. For example, `Arrays.stream((String[]) null)` throws a `NullPointerException` immediately when creating the Stream.

## 4. Streaming Only Part of an Array with `startInclusive` and `endExclusive`

When only a slice of elements is needed, you can pass two indices to `Arrays.stream(array, startInclusive, endExclusive)`. This range has the form **[startInclusive, endExclusive)**:

- Includes the element at `startInclusive`.
- Excludes the element at `endExclusive`.
- Element count equals `endExclusive - startInclusive` when the range is valid.
- Valid indices satisfy `0 <= startInclusive <= endExclusive <= array.length`.

Example:

~~~java
import java.util.Arrays;

int[] dailyOrders = {4, 8, 3, 10, 5};

// Take only elements at index 1, 2, 3.
int subtotal = Arrays.stream(dailyOrders, 1, 4).sum();

System.out.println(subtotal); // 21 = 8 + 3 + 10
~~~

Index table:

| Index | 0 | 1 | 2 | 3 | 4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Value | 4 | **8** | **3** | **10** | 5 |
| `Arrays.stream(dailyOrders, 1, 4)` | Skip | Take | Take | Take | Skip |

Two common boundary cases:

~~~java
long emptyCount = Arrays.stream(dailyOrders, 2, 2).count(); // 0
int allSum = Arrays.stream(dailyOrders, 0, dailyOrders.length).sum(); // 30
~~~

If an index is negative, exceeds the array length, or `startInclusive > endExclusive`, the method throws a range-check exception. **Do not misunderstand the third parameter as the number of elements to take**: `Arrays.stream(array, 1, 4)` selects up to before index 4, not four elements starting from position 1.

A slice Stream is suitable when processing a window with known indices in an array. It differs from `skip`/`limit` in that the range is determined right when creating the Stream from the source.

## 5. `IntStream`, `LongStream`, `DoubleStream`, and the Benefits of Primitive Streams

For primitive numeric arrays, `Arrays.stream` returns the matching **primitive stream**; each element does not have to be auto-boxed into `Integer`, `Long`, or `Double` just to pass through the pipeline.

Example:

~~~java
import java.util.Arrays;
import java.util.IntSummaryStatistics;

int[] prices = {120, 80, 200, 100};

// Only include prices >= 100, then take 10% of each element's value.
int discountedUnits = Arrays.stream(prices)
        .filter(price -> price >= 100)
        .map(price -> price / 10)
        .sum();

IntSummaryStatistics stats = Arrays.stream(prices)
        .summaryStatistics();

System.out.println(discountedUnits); // 42
System.out.println(stats.getCount()); // 4
System.out.println(stats.getSum());   // 500
System.out.println(stats.getMin());   // 80
System.out.println(stats.getMax());   // 200
System.out.println(stats.getAverage()); // 125.0
~~~

Each call to `Arrays.stream(prices)` creates **a new Stream**, so computing `discountedUnits` and `stats` as two separate pipelines is valid. The same `IntStream` variable must not run two terminal operations.

Primitive streams provide several direct aggregation operations:

| Stream type | Useful terminal operation examples |
| --- | --- |
| `IntStream` | `sum()`, `average()`, `min()`, `max()`, `summaryStatistics()` |
| `LongStream` | `sum()`, `average()`, `min()`, `max()`, `summaryStatistics()` |
| `DoubleStream` | `sum()`, `average()`, `min()`, `max()`, `summaryStatistics()` |

`average()` returns `OptionalDouble` because an empty array has no average value:

~~~java
double average = Arrays.stream(new double[]{8.0, 9.5, 7.0})
        .average()
        .orElse(0.0);

double emptyAverage = Arrays.stream(new double[0])
        .average()
        .orElse(Double.NaN);
~~~

Choosing a fallback value like `0.0` or `Double.NaN` is a business decision. Also note that `sum()` on `int`/`long` can overflow when the sum exceeds the type's range, while `double` arithmetic is subject to floating-point rounding error.

### When Is `boxed()` Needed?

If you want to use a collector that operates on objects, you can convert an `IntStream` into `Stream<Integer>` via `boxed()`:

~~~java
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

int[] ages = {16, 18, 21, 17, 25};

Map<Boolean, Long> adultCounts = Arrays.stream(ages)
        .boxed()
        .collect(Collectors.partitioningBy(
                age -> age >= 18,
                Collectors.counting()
        ));

System.out.println(adultCounts.get(true));  // 3
System.out.println(adultCounts.get(false)); // 2
~~~

Boxing creates wrapper objects for primitive values during processing and can increase allocation/memory overhead. For problems that only need sum, min, max, or average, prefer `IntStream`/`LongStream`/`DoubleStream` directly.

## 6. Multidimensional Arrays: A Stream of Rows First

With `int[][]`, the element-level data type of the outer array is `int[]`. Therefore:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

int[][] batches = {
        {2, 4},
        {5},
        {6, 8}
};

Stream<int[]> rows = Arrays.stream(batches); // Stream of each subarray
~~~

The snippet above is not yet an `IntStream` containing the numbers 2, 4, 5, 6, 8. To *flatten* the rows into a single stream of numbers, use `flatMapToInt`:

~~~java
int total = Arrays.stream(batches)
        .flatMapToInt(Arrays::stream)
        .sum();

System.out.println(total); // 25
~~~

Here `Arrays::stream` receives each `int[]` and creates an `IntStream` for that row. `flatMapToInt` concatenates the sub-Streams in encounter order, and then `sum` performs the aggregation.

With `String[][]`, the rows form a `Stream<String[]>` and can be flattened using `flatMap`:

~~~java
String[][] teams = {
        {"Lan", "An"},
        {"Minh", "Linh"}
};

long people = Arrays.stream(teams)
        .flatMap(Arrays::stream)
        .count();

System.out.println(people); // 4
~~~

If there are `null` rows, you need to filter out or handle those rows before calling `Arrays.stream` on each row.

## 7. Where Do `Arrays.stream` and `Stream.of` Differ?

For a reference array such as `String[]`, both approaches below can create a `Stream<String>` traversing the array elements:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

String[] values = {"A", "B", "C"};

Stream<String> first = Arrays.stream(values);
Stream<String> second = Stream.of(values);
~~~

However, **with primitive arrays**, the result differs very importantly:

~~~java
int[] numbers = {10, 20, 30};

int total = Arrays.stream(numbers).sum();    // IntStream -> 60

long arrays = Stream.of(numbers).count();    // Stream<int[]> -> 1
~~~

In this case, `Stream.of(numbers)` receives **a single `int[]` object** as an element rather than expanding the numbers 10, 20, 30 into three separate elements. If you want to work with each number of `int[]`, use `Arrays.stream(numbers)` or `IntStream.of(numbers)`.

Some API selection points:

| Goal | Suitable approach |
| --- | --- |
| Have `String[]` and want `Stream<String>` | `Arrays.stream(strings)` |
| Have `int[]` and want `IntStream` | `Arrays.stream(ints)` |
| Take only an index slice of an array | `Arrays.stream(array, from, to)` |
| Want a Stream from a few loose elements (no source array) | `Stream.of(x, y, z)` |
| Want a `Stream<int[]>` containing the whole `int[]` array | `Stream.of(ints)` |

Keeping the whole array as a single element can be useful in certain nested data structures, but it is inappropriate if the goal is to process individual numbers.

## 8. Primitive Array Types Without Overloads

`Arrays.stream` only directly supports `int[]`, `long[]`, and `double[]` among primitives. For `byte[]`, `short[]`, and `char[]`, you can access elements by index using `IntStream.range`:

~~~java
import java.util.stream.IntStream;

byte[] bytes = {1, 2, 3};

int byteSum = IntStream.range(0, bytes.length)
        .map(index -> bytes[index])  // byte is widened to int
        .sum();

System.out.println(byteSum); // 6
~~~

A similar pattern works for `short[]` and `char[]` when you want to process values as integers. For `char[]`, remember that `char` is a UTF-16 code unit; a Unicode character outside the Basic Multilingual Plane can consist of two `char`s. If the original data is a `String` and the goal is to process Unicode code points, consider `String.codePoints()` instead of iterating over each `char`.

`float[]` can convert each element to `double`:

~~~java
float[] measures = {1.5f, 2.5f};

double sum = IntStream.range(0, measures.length)
        .mapToDouble(index -> measures[index])
        .sum();

System.out.println(sum); // 4.0
~~~

`boolean[]` does not have a dedicated primitive stream for booleans. You can iterate by index to `filter`/`count`, or map to a type suited to your needs:

~~~java
boolean[] active = {true, false, true, true};

long activeCount = IntStream.range(0, active.length)
        .filter(index -> active[index])
        .count();

System.out.println(activeCount); // 3
~~~

The approaches above are **workaround strategies**, not overloads provided by `Arrays.stream`.

## 9. Laziness, Lifecycle, and Mutating the Source Array

### Single-Use Streams

The array continues to exist after the pipeline finishes; a Stream object that has executed a terminal operation cannot be reused.

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] values = {3, 5, 7};

IntStream first = Arrays.stream(values);
long count = first.count(); // 3

// Wrong: first.sum(); // May throw IllegalStateException

int sum = Arrays.stream(values).sum(); // Correct: new Stream, result 15
~~~

To compute multiple metrics in a single pass, `summaryStatistics` or an appropriate aggregating collector can reduce repeated traversal. If the source is a re-readable array, calling `Arrays.stream(array)` again to create another pipeline is valid.

### Laziness Does Not Mean the Array Is Copied

~~~java
int[] values = {1, 2, 3};

int answer = Arrays.stream(values)
        .filter(value -> value > 1)
        .map(value -> value * 10)
        .sum();

System.out.println(answer); // 50
~~~

`filter` and `map` describe transformations; elements are processed when `sum` triggers the pipeline. `Arrays.stream` uses the existing array source and does not automatically create an independent snapshot upon creation.

Therefore, **do not modify the source array while the pipeline is executing**, especially when running in parallel. The Stream *non-interference* principle requires that functions in the pipeline do not interfere with the data source. The fact that an array is mutable does not grant license to modify it arbitrarily while a Stream is traversing it.

If you must process a stable state while another place might edit the array, you can create a copy beforehand:

~~~java
int[] snapshot = Arrays.copyOf(values, values.length);
int stableSum = Arrays.stream(snapshot).sum();
~~~

In return, copying costs extra memory and time proportional to the array length.

### Resource Closing and Parallel Processing

A Stream from an ordinary in-memory array does not hold files or I/O connections, so it does not require `try-with-resources` like `Files.lines`. However, the **one Stream per pipeline** rule still applies.

Because an array has a known size, the `Spliterator` created from it can support efficient range splitting; when data and computation are large enough, you can try `parallel()`:

~~~java
long count = Arrays.stream(new int[]{1, 2, 3, 4, 5, 6})
        .parallel()
        .filter(n -> n % 2 == 0)
        .count();

System.out.println(count); // 3
~~~

`parallel()` does not guarantee faster execution: small data can be slower due to splitting and thread coordination overhead. Functions in the pipeline must not share unsafe mutable state; result combining operations must obey appropriate associativity conditions. Advanced operations such as custom collectors or Stream Gatherers in JDKs that support them also follow Stream lifecycle and state/performance constraints.

## 10. Common Mistakes and How to Avoid Them

| Symptom or code pattern | Problem | Solution |
| --- | --- | --- |
| `Arrays.stream((int[]) null)` | Array reference is `null` | Check input or use an empty-array convention before calling. |
| `Arrays.stream(new byte[]{1, 2})` | No overload for `byte[]` | Use `IntStream.range` by index or convert data to an appropriate type. |
| `Stream.of(intArray).count() == 1` | The single Stream element is the entire `int[]` | Use `Arrays.stream(intArray)` if you want individual numbers. |
| `Arrays.stream(arr, 2, 5)` thinking it takes 5 elements | Confusing end index with count | Identify range [2, 5), which has only 3 elements. |
| Calling `count()` then `sum()` on the same `IntStream` | Reusing a finished Stream | Create a new Stream from the array or aggregate together in one pass. |
| `Arrays.stream(matrix).count()` on `int[][]` | Counts rows, not all inner numbers | `flatMapToInt(Arrays::stream).count()`. |
| `map(String::length)` when array contains `null` | Calling a method on `null` | Use `filter(Objects::nonNull)` or define a missing-data handling convention. |
| Modifying array elements from another task during parallel traversal | Source interference, which can lead to wrong or unstable results | Do not mutate the source while traversing; use a copy if needed. |

When choosing a Stream from an array in real applications, determine beforehand the **array type**, **whether to process the whole array or a slice**, the **desired terminal operation**, and the **acceptable cost**. These four factors are usually enough to choose between `Arrays.stream`, `IntStream.range`, single-pass aggregation, or storing a snapshot.

## 11. Self-Check Exercises

**Exercise 1.** Predict the output and explain why:

~~~java
String[] colors = {"red", "blue", "yellow", "purple"};
long n = Arrays.stream(colors, 1, 3).count();
System.out.println(n);
~~~

**Answer:** `2`, because the index range is [1, 3), meaning elements at positions 1 and 2: "blue", "yellow".

**Exercise 2.** Given the following `int[]` array, write a pipeline to compute the sum of even numbers greater than 10:

~~~java
int[] nums = {8, 12, 15, 20, 24, 9};
~~~

**Suggested solution:**

~~~java
int result = Arrays.stream(nums)
        .filter(n -> n > 10 && n % 2 == 0)
        .sum();

System.out.println(result); // 56 = 12 + 20 + 24
~~~

**Exercise 3.** Why do the two expressions below differ?

~~~java
int[] values = {1, 2, 3};

long a = Arrays.stream(values).count();
long b = java.util.stream.Stream.of(values).count();
~~~

**Answer:** `a == 3` because `Arrays.stream(values)` is an `IntStream` of three numbers; `b == 1` because `Stream.of(values)` is a Stream with a single element of type `int[]`.

**Exercise 4.** Given a multidimensional array, compute the sum of all elements without writing nested loops:

~~~java
int[][] matrix = {{1, 2}, {3, 4}, {5}};
~~~

**Solution:**

~~~java
int total = Arrays.stream(matrix)
        .flatMapToInt(Arrays::stream)
        .sum();

System.out.println(total); // 15
~~~

**Key takeaway:** Use `Arrays.stream(array)` to start a pipeline from an existing array; reference arrays create `Stream<T>`, while `int[]`/`long[]`/`double[]` create the corresponding primitive stream. Use the [startInclusive, endExclusive) overload to select a slice, `flatMapToInt` or `flatMap` to flatten multidimensional arrays, and create a new Stream from the array whenever another processing pass is needed.
