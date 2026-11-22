# `Arrays.stream()` with Object Arrays and Primitive Arrays in Java

## 1. Goal and Problem to Solve

In Java, arrays such as `String[]`, `User[]`, or `int[]` are fixed-length structures for storing elements. Operations for processing each element, filtering, mapping, aggregating, and computing statistics are often more convenient when expressed using the **Stream API**.

The utility class `java.util.Arrays` provides `Arrays.stream(...)` to create a stream from an existing array. For example:

~~~java
String[] words = {"Java", "Stream", "Lambda"};
List<String> selected = Arrays.stream(words)
        .filter(s -> s.length() > 4)
        .toList();

System.out.println(selected); // [Stream, Lambda]
~~~

With a primitive array:

~~~java
int[] numbers = {3, 6, 9};
int total = Arrays.stream(numbers).sum();

System.out.println(total); // 18
~~~

Although they share the same name `Arrays.stream`, **the result type depends on the array type**. Object arrays produce `Stream<T>`; supported primitive numeric arrays produce specialized *primitive streams*. Understanding this helps you choose the right operations such as `map`, `mapToInt`, `sum`, `boxed`, and `toArray`.

This lesson uses **Java 17+**. `Arrays.stream` was introduced in Java 8; `Stream.toList()` appeared in Java 16, so all standalone examples below run on JDK 17 or later.

## 2. Important Overloads of `Arrays.stream`

Signatures to remember (abbreviated):

~~~java
// Reference array: T can be String, User, Integer, ...
static <T> Stream<T> arraysStream(T[] array);
static <T> Stream<T> arraysStream(
        T[] array, int startInclusive, int endExclusive);

// Directly supported primitive arrays:
static IntStream arraysStream(int[] array);
static IntStream arraysStream(
        int[] array, int startInclusive, int endExclusive);

static LongStream arraysStream(long[] array);
static LongStream arraysStream(
        long[] array, int startInclusive, int endExclusive);

static DoubleStream arraysStream(double[] array);
static DoubleStream arraysStream(
        double[] array, int startInclusive, int endExclusive);
~~~

**Note:** `arraysStream` above is a placeholder name used to present the signatures; the actual API name must be written as **`Arrays.stream`**, not `Arrays.arraysStream`. In the JDK, these overloads belong to the `java.util.Arrays` class.

| Input | Return type of `Arrays.stream(...)` | Some typical operations |
| --- | --- | --- |
| `String[]` | `Stream<String>` | `filter`, `map`, `toList` |
| `User[]` | `Stream<User>` | `filter`, `map(User::name)` |
| `Integer[]` | `Stream<Integer>` | `mapToInt(Integer::intValue)` |
| `int[]` | `IntStream` | `sum`, `average`, `min`, `max`, `mapToObj` |
| `long[]` | `LongStream` | `sum`, `average`, `boxed` |
| `double[]` | `DoubleStream` | `sum`, `average`, `summaryStatistics` |

There are no direct overloads for `byte[]`, `short[]`, `char[]`, `float[]`, or `boolean[]`. `Arrays.stream(new byte[]{1, 2})` will not compile. When you need to process those array types, choose an appropriate approach such as `IntStream.range(0, a.length).map(i -> a[i])` to traverse a `byte[]`/`short[]`/`char[]` array as `int` values, or create an index-based stream to map to the appropriate type. Do not assume Java has a standard `ByteStream` or `FloatStream`.

## 3. With Object Arrays: `T[] -> Stream<T>`

An object array is an array whose elements belong to a **reference type**, such as `String`, `Integer`, `Person`, or `String[]`. `Arrays.stream(T[])` creates a `Stream<T>` with the same elements and encounter order as the source array.

~~~java
String[] names = {"An", "Binh", "Chi"};

List<String> upperNames = Arrays.stream(names)
        .map(String::toUpperCase)
        .toList();

System.out.println(upperNames); // [AN, BINH, CHI]
~~~

`Arrays.stream(names)` does not eagerly build a result list; it creates a **source pipeline** from the array. `map(String::toUpperCase)` is an intermediate operation; `toList()` triggers traversal and collects the results.

### 3.1. Working with Record Types or Application-Defined Classes

Suppose:

~~~java
record Person(String name, int age) {}

Person[] people = {
    new Person("An", 20),
    new Person("Binh", 17),
    new Person("Chi", 25)
};

List<String> adults = Arrays.stream(people)
        .filter(person -> person.age() >= 18)
        .map(Person::name)
        .toList();

System.out.println(adults); // [An, Chi]
~~~

The types progress step by step:

~~~text
Person[] -> Stream<Person>
         -> filter(...) : Stream<Person>
         -> map(Person::name) : Stream<String>
         -> toList() : List<String>
~~~

`Arrays.stream` does not automatically turn each object into one of its properties; `map` is the decisive step that changes the type from `Person` to `String`.

### 3.2. With Wrapper Arrays such as `Integer[]`

`Integer[]` is an **object** array, not an `int` array, so:

~~~java
Integer[] boxedNumbers = {2, 4, 6};

Stream<Integer> objects = Arrays.stream(boxedNumbers);
int total = Arrays.stream(boxedNumbers)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(total); // 12
~~~

`Stream<Integer>` does not have a direct `sum()` method. To compute a primitive sum, you need `mapToInt` or an appropriate `Collectors.summingInt`. If `Integer[]` contains a `null` element, `Integer::intValue` will throw a `NullPointerException` when it encounters that element, unless nulls are filtered or handled beforehand.

## 4. With `int[]`: Produces `IntStream`, Not `Stream<Integer>`

`Arrays.stream(int[])` produces **`java.util.stream.IntStream`**. An `IntStream` holds `int` values with primitive semantics, providing aggregation methods such as `sum`, `average`, `min`, `max`, and `summaryStatistics` without boxing each element into an `Integer` inside the primitive pipeline.

~~~java
int[] values = {2, 5, 8, 11};

int sum = Arrays.stream(values).sum();
long count = Arrays.stream(values).filter(n -> n % 2 != 0).count();
int maximum = Arrays.stream(values).max().orElseThrow();

System.out.println(sum);     // 26
System.out.println(count);   // 2
System.out.println(maximum); // 11
~~~

Because `IntStream` is a primitive stream, commonly used conversion APIs include:

~~~java
int[] source = {1, 2, 3};

IntStream primitiveStream = Arrays.stream(source);
List<Integer> asList = Arrays.stream(source).boxed().toList();
List<String> labels = Arrays.stream(source)
        .mapToObj(i -> "N" + i)
        .toList();

System.out.println(asList);  // [1, 2, 3]
System.out.println(labels);  // [N1, N2, N3]
~~~

- `boxed()` converts each `int` to an `Integer` and returns `Stream<Integer>`.
- `mapToObj(...)` transforms each `int` into any object, such as `String`.
- `IntStream.toArray()` creates a new `int[]`, not `Integer[]`.
- `map(...)` directly on `IntStream` still returns an `IntStream` when the mapper is an `IntUnaryOperator`.

You can use `IntStream.range(0, array.length)` if you need the **index** of each element rather than just its value.

## 5. With `long[]` and `double[]`

### 5.1. `long[] -> LongStream`

~~~java
long[] fileSizes = {10L, 20L, 35L};

long total = Arrays.stream(fileSizes).sum();
long count = Arrays.stream(fileSizes).count();

System.out.println(total); // 65
System.out.println(count); // 3
~~~

`LongStream` has operations such as `mapToObj`, `boxed`, `sum`, `average`, `min`, and `max`. `average()` returns **`OptionalDouble`**, because the array may be empty and the average calculation has no result in that case.

### 5.2. `double[] -> DoubleStream`

~~~java
double[] temperatures = {2.5, 3.5, 4.0};

double total = Arrays.stream(temperatures).sum();
double average = Arrays.stream(temperatures).average().orElseThrow();

System.out.println(total); // 10.0
System.out.println(average > 3.0); // true
~~~

`DoubleStream` has `summaryStatistics()` which returns `DoubleSummaryStatistics` with element count, sum, min, max, and average. Floating-point arithmetic can have representation errors; values like `NaN` and infinity also affect aggregations. In domains requiring exact decimal precision (such as currency), `double` should not be used arbitrarily; choose an appropriate numeric model.

### 5.3. Why Doesn't Java Have a Primitive Stream for Every Primitive?

The standard JDK only provides three specialized primitive streams: `IntStream`, `LongStream`, and `DoubleStream`. Smaller numeric types like `byte`, `short`, and `char` can be widened to `int` via numeric promotion during mapping, but `boolean[]` requires a different explicit modeling approach (such as iterating over indices and using `mapToObj(i -> flags[i])`). There is no `BooleanStream` in the standard Stream API.

## 6. Slicing an Array with `Arrays.stream(array, startInclusive, endExclusive)`

All four overload families in section 2 have a form that accepts start/end indices. The extracted range is:

\[
[\text{startInclusive}, \text{endExclusive})
\]

That is, **the element at the start index is included, and the element at the end index is excluded**.

~~~java
String[] names = {"A", "B", "C", "D"};

List<String> slice = Arrays.stream(names, 1, 3).toList();
System.out.println(slice); // [B, C]
~~~

Primitive arrays work similarly:

~~~java
int[] numbers = {10, 20, 30, 40};

int[] slice = Arrays.stream(numbers, 1, 3).toArray();
System.out.println(Arrays.toString(slice)); // [20, 30]
~~~

For an array of length `n`, a valid range satisfies `0 <= startInclusive <= endExclusive <= n`. The range `[k,k)` has 0 elements. Out-of-bounds or misordered indices cause an index check error rather than silently taking the "remaining" elements.

The benefit of this overload: you can create a stream directly over a **contiguous range** of an array without having to copy that range into a new array first. However, the result from a terminal operation like `toArray()` or `toList()` is a newly created result; do not confuse the stream source with the materialized output structure.

If you need elements matching a **condition**, use `filter`; if you need a known **index range**, the overload taking `start/end` expresses the intent more clearly.

## 7. Distinguishing from `Stream.of(array)` and `Arrays.asList(array).stream()`

This is a very common source of bugs, especially when switching from an object array to a primitive array.

### 7.1. Object Array `String[]`

~~~java
String[] words = {"a", "b"};

Stream<String> a = Arrays.stream(words);
Stream<String> b = Stream.of(words);
Stream<String> c = Arrays.asList(words).stream();
~~~

In this case, all three traverse the two elements `"a"` and `"b"`. `Stream.of(words)` uses the varargs overload with `String[]` and treats the array's elements as the stream elements. `Arrays.asList(words)` returns a fixed-size list backed by the array, and then `stream()` creates a stream from that list.

Even though the pipelines may yield the same values, they do not have the same intermediate structure: `Arrays.stream` is the direct way from an array, without creating an intermediate `List`.

### 7.2. Primitive Array `int[]`: An Important Difference

~~~java
int[] nums = {1, 2, 3};

IntStream a = Arrays.stream(nums);
Stream<int[]> b = Stream.of(nums);

System.out.println(a.count()); // 3
System.out.println(b.count()); // 1
~~~

`Arrays.stream(nums)` sees **three `int` numbers**; `Stream.of(nums)` sees **one element, which is the `int[]` array itself**. Similarly:

~~~java
List<int[]> oneArray = Arrays.asList(nums);
System.out.println(oneArray.size()); // 1
~~~

`Arrays.asList(int[])` does not automatically box each number into an `Integer`. To get a `List<Integer>`, use:

~~~java
List<Integer> boxed = Arrays.stream(nums).boxed().toList();
System.out.println(boxed); // [1, 2, 3]
~~~

Therefore, if the source is `int[]`, do not replace `Arrays.stream(ints)` with `Stream.of(ints)` without checking the types.

### 7.3. `Arrays.stream` vs. `IntStream.of`

If you only need to create a primitive stream from an `int[]` array, `IntStream.of(nums)` also has a varargs overload accepting `int...` and produces the same values as `Arrays.stream(nums)`. However, `Arrays.stream(nums, from, to)` is the direct API for restricting to an array **index range**.

## 8. Multidimensional Arrays and Flattening

A two-dimensional array in Java is actually an **array of arrays**. For example, `String[][]` is an array where each element has type `String[]`.

~~~java
String[][] blocks = {
    {"A", "B"},
    {"C"}
};

Stream<String[]> rows = Arrays.stream(blocks);
List<String> flat = Arrays.stream(blocks)
        .flatMap(Arrays::stream)
        .toList();

System.out.println(flat); // [A, B, C]
~~~

`Arrays.stream(blocks)` returns `Stream<String[]>`, and does not automatically flatten it into `Stream<String>`. `flatMap(Arrays::stream)` turns each `String[]` into a `Stream<String>` and concatenates them. If you want to preserve the row/column structure, do not flatten; process each row intentionally.

With `int[][]`:

~~~java
int[][] matrix = {{1, 2}, {3, 4}};

int total = Arrays.stream(matrix)
        .flatMapToInt(Arrays::stream)
        .sum();

System.out.println(total); // 10
~~~

`Arrays.stream(matrix)` returns `Stream<int[]>`. Use `flatMapToInt` because each `Arrays.stream(int[])` is an **`IntStream`**, not a `Stream<Integer>`.

Arrays with `null` rows require separate handling; `Arrays.stream(null)` does not create an empty Stream and will throw an error. If the data may actually contain null rows, consider filtering with `Objects::nonNull` before flattening.

## 9. Data Source, Laziness, and Array Mutability

### 9.1. Intermediate Operations Are Lazy

~~~java
String[] words = {"a", "bbb"};

Stream<Integer> lengths = Arrays.stream(words)
        .map(s -> s.length()); // Pipeline is set up.

List<Integer> result = lengths.toList(); // Starts traversing and collecting.
System.out.println(result); // [1, 3]
~~~

`map` does not precompute all lengths when `lengths` is declared. Intermediate operations are generally only executed when a terminal operation consumes the pipeline. Do not call `toList()` and then `count()` on the same `lengths` variable: a Stream can only be consumed once.

Some terminal operations can optimize by not traversing every element if the size is already known and the pipeline requirements allow it; do not rely on side effects in `map` to prove that work ran.

### 9.2. `Arrays.stream` Does Not Automatically Copy the Source Array

`Arrays.stream(array)` creates a stream from the **original array**, without turning it into an immutable copy. This has two consequences:

- Creating a `Stream` does not mean all values have been "snapshotted". Modifying the source array while the pipeline is in use can affect what is observed and violates the **non-interference** requirement; avoid modifying the source during traversal.
- For an array of mutable objects, the element references received are references to the original objects. A `map` returning objects or `toList()` containing those references is **not a deep copy**.

Safe example:

~~~java
String[] names = {"An", "Binh"};
List<String> snapshot = Arrays.stream(names).toList();

names[0] = "Chi";
System.out.println(snapshot); // [An, Binh]
~~~

`snapshot` is a collected result list containing the original `String` references; replacing the element at index 0 in the array after collection does not change the corresponding element in the list. With shared mutable objects, changing **object state** is a different matter. `Stream.toList()` returns an unmodifiable list by contract, while whether the element objects themselves are mutable is a separate concern.

### 9.3. Null: A Null Array Differs from Null Elements

~~~java
String[] words = {"a", null, "c"};

List<String> safe = Arrays.stream(words)
        .filter(java.util.Objects::nonNull)
        .map(String::toUpperCase)
        .toList();

System.out.println(safe); // [A, C]
~~~

An array can contain `null` elements; `Arrays.stream(words)` still creates a Stream, but the method reference `String::toUpperCase` will throw a `NullPointerException` if it encounters an unhandled null element.

Conversely, if the array variable itself is `null`:

~~~java
String[] missing = null;
// Arrays.stream(missing); // Throws NullPointerException.
~~~

`Arrays.stream` has no rule that treats a **null array** as an empty array. If the source data is optional, check and return `Stream.empty()` or define a clear non-null input contract.

## 10. Combining Primitive Streams with Aggregations

With an `int[]` array, use `IntStream` directly to obtain statistics:

~~~java
int[] samples = {3, 7, 10};

int sum = Arrays.stream(samples).sum();
double average = Arrays.stream(samples).average().orElse(0.0);
int max = Arrays.stream(samples).max().orElseThrow();

System.out.println(sum);      // 20
System.out.println(average > 6); // true
System.out.println(max);      // 10
~~~

**Why read the array three times?** Each terminal operation consumes the stream; to run independent terminal operations, we create a new stream. When you want multiple statistics in a single pass, use `summaryStatistics()`:

~~~java
IntSummaryStatistics stats = Arrays.stream(samples)
        .summaryStatistics();

System.out.println(stats.getCount()); // 3
System.out.println(stats.getSum());   // 20
System.out.println(stats.getMin());   // 3
System.out.println(stats.getMax());   // 10
~~~

You must import `java.util.IntSummaryStatistics` when using this in a standalone example.

`min()`, `max()`, and `average()` on primitive Streams return `OptionalInt`, `OptionalLong`, or `OptionalDouble` depending on the method. Do not blindly call `getAsInt()`/`getAsDouble()` on an array that might be empty; use `orElse`, `orElseThrow` with an appropriate message, or check `isPresent`.

## 11. Standalone Java 17+ Example with Deterministic Stdout

Create the file **`ArraysStreamDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Objects;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ArraysStreamDemo {
    record Person(String name, int age) {}

    public static void main(String[] args) {
        String[] words = {" Java ", "API", "Stream"};
        List<String> trimmed = Arrays.stream(words)
                .map(String::trim)
                .toList();
        System.out.println("objects=" + trimmed);

        List<String> slice = Arrays.stream(words, 1, 3)
                .map(String::trim)
                .toList();
        System.out.println("slice=" + slice);

        Person[] people = {
                new Person("An", 20),
                new Person("Binh", 17),
                new Person("Chi", 25)
        };
        List<String> adults = Arrays.stream(people)
                .filter(p -> p.age() >= 18)
                .map(Person::name)
                .toList();
        System.out.println("adults=" + adults);

        int[] values = {2, 5, 8, 11};
        IntSummaryStatistics stats = Arrays.stream(values)
                .summaryStatistics();
        System.out.println("intSum=" + stats.getSum());
        System.out.println("oddCount=" + Arrays.stream(values)
                .filter(n -> n % 2 != 0).count());
        System.out.println("boxed=" + Arrays.stream(values)
                .boxed().toList());
        System.out.println("intSlice=" + Arrays.toString(
                Arrays.stream(values, 1, 3).toArray()));

        System.out.println("ofPrimitiveCount=" + Stream.of(values).count());
        System.out.println("arrayPrimitiveCount=" + Arrays.stream(values).count());

        long[] longs = {10L, 20L, 35L};
        System.out.println("longSum=" + Arrays.stream(longs).sum());

        double[] doubles = {2.5, 3.5, 4.0};
        System.out.println("doubleSum=" + Arrays.stream(doubles).sum());

        String[][] blocks = {{"A", "B"}, {"C"}};
        System.out.println("flatObjects=" + Arrays.stream(blocks)
                .flatMap(Arrays::stream).toList());

        int[][] matrix = {{1, 2}, {3, 4}};
        System.out.println("flatIntSum=" + Arrays.stream(matrix)
                .flatMapToInt(Arrays::stream).sum());

        String[] nullable = {"a", null, "c"};
        System.out.println("nonNull=" + Arrays.stream(nullable)
                .filter(Objects::nonNull)
                .toList());

        int[] empty = {};
        System.out.println("emptyAverage=" + Arrays.stream(empty)
                .average().orElse(0.0));
    }
}
~~~

Compile/run:

~~~bash
javac ArraysStreamDemo.java
java ArraysStreamDemo
~~~

Expected stdout:

~~~text
objects=[Java, API, Stream]
slice=[API, Stream]
adults=[An, Chi]
intSum=26
oddCount=2
boxed=[2, 5, 8, 11]
intSlice=[5, 8]
ofPrimitiveCount=1
arrayPrimitiveCount=4
longSum=65
doubleSum=10.0
flatObjects=[A, B, C]
flatIntSum=10
nonNull=[a, c]
emptyAverage=0.0
~~~

The results have a deterministic order because all sources here are ordered arrays, the pipelines are sequential, and no asynchronous callbacks are used. `Arrays.stream` creates a separate stream source for each terminal operation; cases needing multiple calculations like `sum` and `count` can create a new stream or use summary statistics.

## 12. Parallel Streams and Performance Optimization Choices

A stream created from `Arrays.stream(array)` is normally **sequential**:

~~~java
int[] numbers = {1, 2, 3, 4};
int total = Arrays.stream(numbers).parallel().sum();
System.out.println(total); // 10
~~~

`parallel()` changes how the pipeline may be executed, not the type from `IntStream` to `Stream<Integer>`. Suitably designed aggregations like `sum` often work well with parallel execution, but **parallel is not faster by default**: splitting cost, combining cost, array size, work per element, and the runtime environment determine effectiveness.

If order matters when performing side effects, `forEach` on a parallel stream does not guarantee encounter order. `forEachOrdered` enforces ordering but can reduce the benefits of parallelism:

~~~java
Arrays.stream(new String[]{"A", "B", "C"})
        .parallel()
        .forEachOrdered(System.out::println);
~~~

For business data processing, prefer pure `map`/`reduce`/`collect` and do not modify the source array during traversal. For `double`, the results of floating-point operations can be affected by summation order and rounding rules; do not assume every floating-point pipeline yields bitwise-identical results across all execution modes.

## 13. Common Mistakes and How to Fix Them

| Mistake | Problem | Fix |
| --- | --- | --- |
| Assigning `Arrays.stream(intArray)` to `Stream<Integer>` | The result is `IntStream`, not `Stream<Integer>` | Use `IntStream` or `.boxed()` |
| Writing `Arrays.stream(new byte[]{1,2})` | There is no overload for `byte[]` | Traverse indices with `IntStream.range` and map |
| Using `Stream.of(intArray)` expecting a stream of `int`s | It has one element of type `int[]` | Use `Arrays.stream(intArray)` or `IntStream.of` |
| Calling `sum()` on `Stream<Integer>` | Reference streams do not have `sum()` | Use `mapToInt(Integer::intValue).sum()` |
| Treating `endExclusive` as the last included index | The range is half-open | `Arrays.stream(a, 1, 3)` takes indices 1, 2 |
| Assuming `Arrays.stream(matrix)` automatically flattens a 2D array | Each element of the source is a subarray | Use `flatMap(Arrays::stream)` or `flatMapToInt` |
| Assuming `Arrays.stream(array)` copies the array immediately | The stream reads data from the source array without snapshotting immediately | Avoid modifying the source during traversal; copy explicitly if needed |
| Passing a `null` array variable | Throws `NullPointerException` | Check the array or design non-null inputs |
| Calling `String::trim` on a null element | A method reference requires a non-null receiver | `filter(Objects::nonNull)` first |
| Reusing the same Stream after a terminal operation | A Stream is single-use | Create a new stream or aggregate in one pass |
| Calling `average().getAsDouble()` on an empty array | There is no average | Use `orElse`/`orElseThrow` appropriately |
| Assuming `parallel()` is faster by default | There is scheduling overhead and workload dependency | Measure and verify correctness before optimizing |

## 14. Self-Check Exercises

**Exercise 1.** Given `int[] numbers = {4, 8, 12};`, what type does `Arrays.stream(numbers)` return? What type does `Stream.of(numbers)` return?

**Answer:** `Arrays.stream(numbers)` returns an `IntStream` containing 3 numbers; `Stream.of(numbers)` is a `Stream<int[]>` containing 1 element, which is the array.

**Exercise 2.** Given `String[] colors = {"red", "green", "blue", "white"};`, what is the result of `Arrays.stream(colors, 1, 3).toList()`?

**Answer:** `[green, blue]`; index 3 is not included.

**Exercise 3.** What do you use to turn an `int[]` into a `List<Integer>`?

**Answer:** `Arrays.stream(array).boxed().toList()`. `boxed()` converts `IntStream` to `Stream<Integer>`.

**Exercise 4.** Given `Integer[] values = {1, 2, 3};`, why can't you call `Arrays.stream(values).sum()`?

**Answer:** `Integer[]` is a reference array, so it produces `Stream<Integer>`, which does not have `sum()`. Use `Arrays.stream(values).mapToInt(Integer::intValue).sum()`.

**Exercise 5.** To compute the sum of an `int[][]`, do you use `flatMap` or `flatMapToInt`?

**Answer:** `Arrays.stream(matrix).flatMapToInt(Arrays::stream).sum()`. The mapper returns `IntStream`, so `flatMapToInt` is required.

**Exercise 6.** If `String[] a = null;`, does `Arrays.stream(a)` become an empty Stream?

**Answer:** No. Passing a null array causes a `NullPointerException`; you must check or replace it with an empty array according to the API policy.

**Exercise 7.** What does `Arrays.stream(new int[0]).average()` return?

**Answer:** An empty `OptionalDouble`. There is no average value; you can use `orElse(0.0)` if 0 is a business-appropriate default value.

## Key Takeaways

**`Arrays.stream` turns an existing array into a Stream for use with the Stream API.** The array type determines the Stream type:

- `T[] -> Stream<T>` for object arrays.
- `int[] -> IntStream`, `long[] -> LongStream`, `double[] -> DoubleStream` for the three directly supported primitive types.
- The `Arrays.stream(array, startInclusive, endExclusive)` form traverses only a half-open index range `[start, end)`.
- `boxed()` converts a primitive stream into a reference stream; `mapToInt` and its variants convert back when primitive operations are needed.
- `Stream.of(intArray)` is not equivalent to `Arrays.stream(intArray)` in type or element count; multidimensional arrays require explicit `flatMap`.
- A Stream is a single-use pipeline, does not automatically copy the entire source array, and requires proper null handling as well as avoiding source interference during traversal.

Knowing the output type of each overload is the key to safely combining arrays with `filter`, `map`, `flatMap`, `sum`, `collect`, and statistical operations.
