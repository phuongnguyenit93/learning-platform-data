# Converting Results to an Array with `toArray`

In the **Traversal, Search, and Matching** chapter of the **Java Stream API**, many pipelines start from a collection, array, or data generator, pass through `filter`, `map`, and `flatMap`, and then need to return a result that can be passed to a legacy API, stored in a field, or accessed by index. **`toArray` is a terminal operation used to end a pipeline and collect output elements into an array.**

This operation looks simple, but there are three common pitfalls: `Stream.toArray()` does not automatically create a typed array like `String[]`; the `Stream.toArray(String[]::new)` form uses an *array generator* to allocate a reference array of the right type; and `IntStream`, `LongStream`, and `DoubleStream` have their own `toArray()` methods returning the corresponding primitive arrays.

This lesson explains data types, usage, common errors, element ordering, and memory overhead when using `toArray` in a declarative pipeline.

## 1. When Should You Convert a Stream to an Array?

Suppose you have filtered a list of product codes and normalized them to uppercase. An external system requires a `String[]` parameter rather than a `Stream<String>` or `List<String>`. You can finish the pipeline with `toArray(String[]::new)`:

~~~java
import java.util.Arrays;
import java.util.List;

public class ToArrayDemo {
    public static void main(String[] args) {
        List<String> codes = Arrays.asList(" pen ", "book", "", "notebook");

        String[] result = codes.stream()
                .map(String::trim)
                .filter(code -> !code.isEmpty())
                .map(String::toUpperCase)
                .toArray(String[]::new);

        System.out.println(Arrays.toString(result));
        // [PEN, BOOK, NOTEBOOK]
    }
}
~~~

Each part of the pipeline has a clear role:

1. `codes.stream()` creates a Stream from the list.
2. `map(String::trim)` strips leading and trailing whitespace from each code.
3. `filter` removes empty codes.
4. `map(String::toUpperCase)` produces uppercase strings.
5. `toArray(String[]::new)` **executes the pipeline** and returns a `String[]` array.

The result `result` is an ordinary Java array: it has `length`, supports `result[0]` indexing, has a fixed size once created, and allows replacing elements by index if desired.

## 2. Distinguishing the Three Important Ways to Call `toArray`

| Source | Call | Return Type | Purpose |
| --- | --- | --- | --- |
| `Stream<T>` | `stream.toArray()` | `Object[]` | When only a general object array is needed. |
| `Stream<T>` | `stream.toArray(T[]::new)` | `T[]` matching the array type created by the generator | When a specific reference array type such as `String[]` or `Employee[]` is needed. |
| `IntStream` | `stream.toArray()` | `int[]` | Collect `int` values without boxing. |
| `LongStream` | `stream.toArray()` | `long[]` | Collect `long` values. |
| `DoubleStream` | `stream.toArray()` | `double[]` | Collect `double` values. |

For `Stream<T>`, the generator overload has the generic signature:

~~~java
<A> A[] toArray(java.util.function.IntFunction<A[]> generator)
~~~

The `generator` function receives an `int` size and constructs a corresponding array, such as `size -> new String[size]`. This is commonly shortened to the method reference `String[]::new`.

The core point is that **the return type of `toArray` depends on the overload and the Stream type**. Having input elements that “are all strings” does not make the parameterless overload infer `String[]`.

## 3. Parameterless `toArray()`: Always Works with `Object[]`

For an object Stream, the shortest call is:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

Object[] result = Stream.of("Lan", "Minh", "An")
        .filter(name -> name.length() >= 3)
        .toArray();

System.out.println(Arrays.toString(result)); // [Lan, Minh]
~~~

Even though all elements are `String`, this overload's result has runtime array type `Object[]`. You must not cast it directly to `String[]`:

~~~java
Object[] objects = Stream.of("Lan", "Minh").toArray();

// Fails at runtime: Object[] is not String[].
String[] names = (String[]) objects; // ClassCastException
~~~

**The fix** is to instruct the Stream to allocate the right array type when collecting the result:

~~~java
String[] names = Stream.of("Lan", "Minh")
        .toArray(String[]::new);
~~~

If you already have a valid `Object[]` and genuinely want to create a new string array, you can use `Arrays.copyOf(objects, objects.length, String[].class)` when every element is compatible; however, in a fresh pipeline, `toArray(String[]::new)` is clearer and more direct.

Avoid unsafe casts or `@SuppressWarnings` to hide array type mismatches.

## 4. `toArray(String[]::new)`: The Right Array Type at the Endpoint

Example with user names:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

String[] names = Stream.of("An", "Bình", "Chi", "Dũng")
        .filter(name -> name.length() >= 3)
        .toArray(String[]::new);

System.out.println(Arrays.toString(names)); // [Bình, Chi, Dũng]
System.out.println(names.length);            // 3
~~~

`String[]::new` is an **array constructor reference**, semantically equivalent to:

~~~java
String[] names = Stream.of("Lan", "Minh")
        .toArray(size -> new String[size]);
~~~

For custom types, the exact same pattern applies:

~~~java
record Employee(String id, String department) {}

Employee[] developers = employees.stream()
        .filter(e -> "DEV".equals(e.department()))
        .toArray(Employee[]::new);
~~~

The last snippet assumes `employees` is a collection of `Employee`; `record` syntax requires Java 16 or later. On Java 8, replace `record` with a regular class, and `toArray(Employee[]::new)` still works.

### The Generator Must Supply a Proper Array

`toArray(IntFunction<A[]>)` may call the generator whenever it needs arrays for data partitions or merging results, especially during parallel execution. Therefore:

- The generator should only **allocate a new array of the requested size**.
- Do not assume the generator is called only once or always receives the final element count of the entire pipeline.
- Do not log business events, increment shared counters, or return the same shared array to produce side effects.
- Prefer `String[]::new`, `Employee[]::new`, or `size -> new MyType[size]` because they are concise and satisfy the contract.

The array must have a runtime type compatible with the elements to be stored. When code declares a Stream containing objects of mixed types, do not try to force them into a narrower array type solely via the array generator.

## 5. Three Common Type Errors

### 5.1. `ClassCastException` When Casting `Object[]` to `String[]`

~~~java
Object[] source = Stream.of("a", "b").toArray();
String[] wrong = (String[]) source; // Fails at runtime.
~~~

The issue is not the individual elements `"a"` and `"b"`, but **the type of the array itself**. Java arrays carry a runtime component type, and an already-created `Object[]` cannot be turned into a `String[]` by casting.

### 5.2. `ArrayStoreException` When an Element Does Not Match the Array Type

~~~java
import java.util.stream.Stream;

Stream<Object> mixed = Stream.of("A", 42);

// May compile, but 42 cannot be stored into String[].
String[] wrong = mixed.toArray(String[]::new); // ArrayStoreException
~~~

The type parameter `<A>` on the generator overload lets you choose the output array, but **does not convert elements to type `A`**. If every element must be a string, safely produce a `Stream<String>`, validating or transforming each element before collecting the array:

~~~java
String[] converted = Stream.<Object>of("A", 42)
        .map(String::valueOf)
        .toArray(String[]::new);

System.out.println(Arrays.toString(converted)); // [A, 42]
~~~

Here `map(String::valueOf)` converts each element to a string. If the problem requires discarding non-string elements, replace it with an explicit type-checking step; the two approaches have different business meanings.

### 5.3. Generic Arrays Cannot Use `new T[n]`

Inside a generic method, Java disallows directly creating `new T[n]` due to *type erasure*. The standard solution is **asking the caller to supply the generator**:

~~~java
import java.util.Collection;
import java.util.function.IntFunction;
import java.util.function.Predicate;

public static <T> T[] selectToArray(
        Collection<T> source,
        Predicate<? super T> predicate,
        IntFunction<T[]> arrayFactory) {

    return source.stream()
            .filter(predicate)
            .toArray(arrayFactory);
}
~~~

How to call it:

~~~java
String[] selected = selectToArray(
        Arrays.asList("Lan", "An", "Minh"),
        name -> name.length() >= 3,
        String[]::new
);

// selected = ["Lan", "Minh"]
~~~

In this example, the caller specifies that the result array must have runtime type `String[]`. That frees the generic method from unsafe array casts.

## 6. Primitive Streams: `int[]` vs `Integer[]`

This is a very important distinction between `Stream<Integer>` and `IntStream`.

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;
import java.util.stream.Stream;

// Object stream: returns Integer[] when using a generator.
Integer[] boxed = Stream.of(1, 2, 3)
        .toArray(Integer[]::new);

// IntStream: toArray() returns int[] directly.
int[] primitive = IntStream.of(1, 2, 3)
        .toArray();

System.out.println(Arrays.toString(boxed));     // [1, 2, 3]
System.out.println(Arrays.toString(primitive)); // [1, 2, 3]
~~~

The two arrays print identically but differ in type and storage:

| Characteristic | `Integer[]` | `int[]` |
| --- | --- | --- |
| Elements | References to `Integer` objects | Primitive `int` values |
| Can contain `null` | Yes | No |
| Usable with APIs expecting `int[]` | Not directly compatible | Suitable |
| Boxing/unboxing | May occur | Unnecessary when working with primitives |
| Memory footprint | Usually higher depending on allocation and object sharing | Usually more compact |

Converting from `Stream<Integer>` to `int[]`:

~~~java
import java.util.List;

List<Integer> counts = Arrays.asList(2, 4, 6);

int[] values = counts.stream()
        .mapToInt(Integer::intValue)
        .toArray();
~~~

If the data can contain `null`, `Integer::intValue` will throw `NullPointerException` upon encountering it. Define a policy to filter or replace `null` before unboxing.

Converting from `IntStream` to `Integer[]`:

~~~java
Integer[] values = IntStream.range(1, 4)
        .boxed()
        .toArray(Integer[]::new);
// [1, 2, 3]
~~~

Similarly, `LongStream.toArray()` returns `long[]` and `DoubleStream.toArray()` returns `double[]`.

> You **cannot** call `Stream<Integer>.toArray(int[]::new)` to get `int[]`: `Stream<T>`'s generic overload expects an object array (`A[]`), while `int[]` is a primitive array. Convert to `IntStream` with `mapToInt` and then call `toArray()`.

## 7. `toArray` Is a Terminal Operation: Executes the Pipeline Once

`filter`, `map`, and many intermediate operations only build a description of the pipeline. `toArray` **triggers traversal and materializes the result**:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

Stream<String> pipeline = Stream.of("lan", "minh", "an")
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase);

String[] result = pipeline.toArray(String[]::new); // [LAN, MINH]

// Wrong: the pipeline has already ended; this Stream object cannot be reused.
long count = pipeline.count(); // IllegalStateException (typically)
~~~

If you need both the array and another metric like element count, obtain that information from the collected result:

~~~java
String[] result = Stream.of("lan", "minh", "an")
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase)
        .toArray(String[]::new);

int count = result.length; // 2
~~~

For a collection source that can be traversed multiple times, you can also create **a fresh Stream** for each computation when needed. Never invoke multiple terminal operations on the same Stream object.

A key difference from search operations like `findFirst` or matching operations like `anyMatch` is that `toArray` **must collect all output results**, never stopping early just because one matching element was found. If you only need the first few elements, place a limit before `toArray`.

## 8. Element Order in the Result Array

For a Stream with an *encounter order* (defined traversal order), `toArray` builds the array **in encounter order**:

~~~java
import java.util.Arrays;
import java.util.List;

List<Integer> numbers = Arrays.asList(5, 1, 4, 2);

Integer[] selected = numbers.stream()
        .filter(n -> n % 2 == 0)
        .toArray(Integer[]::new);

System.out.println(Arrays.toString(selected)); // [4, 2]
~~~

`filter` does not sort data. If ascending order is needed, apply `sorted()` before `toArray`:

~~~java
Integer[] ascending = numbers.stream()
        .filter(n -> n % 2 == 0)
        .sorted()
        .toArray(Integer[]::new);

System.out.println(Arrays.toString(ascending)); // [2, 4]
~~~

A **parallel** Stream that still has an encounter order must also preserve that order in `toArray`'s result:

~~~java
Integer[] selected = numbers.parallelStream()
        .filter(n -> n > 1)
        .toArray(Integer[]::new);

// Preserves the List's encounter order: [5, 4, 2]
~~~

Conversely, if the source has no encounter order (such as some Streams created from a `HashSet`) or the pipeline deliberately calls `unordered()`, **there is no guarantee of element order**. Avoid assuming `parallel()` always scrambles order, or that `toArray` sorts elements automatically.

If order is part of the API contract, ensure the source is ordered or use `sorted` with an explicit business key.

## 9. Empty Arrays, `null`, and Other Data Shapes

### 9.1. When No Element Passes the Filter

~~~java
String[] empty = Stream.of("A", "B")
        .filter(text -> text.length() > 5)
        .toArray(String[]::new);

System.out.println(empty.length); // 0
~~~

The result is **a zero-length array**, not `null`. Callers can safely iterate over it with a loop or `Arrays.stream(empty)` without checking whether the array reference itself exists.

### 9.2. `null` Elements May Be Retained

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

String[] names = Stream.of("Lan", null, "Minh")
        .toArray(String[]::new);

System.out.println(Arrays.toString(names)); // [Lan, null, Minh]
~~~

`toArray` does not remove `null`. If downstream consumers reject `null` elements, handle them deliberately:

~~~java
import java.util.Objects;

String[] nonNull = Stream.of("Lan", null, "Minh")
        .filter(Objects::nonNull)
        .toArray(String[]::new);
~~~

Note: calling `map(String::trim)` before filtering out `null` will fail inside `map`.

### 9.3. Two-Dimensional Arrays from Nested Data

You can use `toArray` on both the inner and outer Streams:

~~~java
import java.util.Arrays;
import java.util.List;

List<List<String>> groups = Arrays.asList(
        Arrays.asList("a", "b"),
        Arrays.asList("c")
);

String[][] matrix = groups.stream()
        .map(group -> group.stream()
                .map(String::toUpperCase)
                .toArray(String[]::new))
        .toArray(String[][]::new);

System.out.println(Arrays.deepToString(matrix)); // [[A, B], [C]]
~~~

Because `map` is used at the outer layer, each group remains a separate row. Using `flatMap` instead can merge values into a one-dimensional array; choose the structure based on whether group boundaries must be preserved.

## 10. Distinguishing `Stream.toArray` from `Collection.toArray`

Java has multiple APIs named `toArray` that take different arguments:

~~~java
import java.util.Arrays;
import java.util.List;

List<String> names = Arrays.asList("Lan", "Minh");

// Convert directly from Collection to array (Collection API).
String[] fromCollection = names.toArray(new String[0]);

// Convert Stream pipeline result to array (Stream API).
String[] fromStream = names.stream()
        .filter(name -> name.length() > 3)
        .toArray(String[]::new);
~~~

You cannot write `stream.toArray(new String[0])` on `Stream<String>` because the Stream overload takes **`IntFunction<A[]>`**, not an already-allocated array object. Meanwhile `Collection.toArray(T[])` is Collection's array-accepting overload.

Since Java 11, `Collection` also has a `toArray(IntFunction<T[]>)` overload so you may see `names.toArray(String[]::new)`; that does not give the two APIs the same pipeline-processing contract.

If the data is already a collection and you only need a direct copy into an array, the collection API can be simpler. When you need `filter`, `map`, `flatMap`, or declarative transformations before obtaining the array, use `Stream.toArray`.

## 11. `toArray` or `collect` / `toList`?

Both `toArray` and collection-gathering terminal operations **materialize** the output data, though the resulting types differ.

| Criterion | `toArray(String[]::new)` | `collect(Collectors.toList())` | `Stream.toList()` (Java 16+) |
| --- | --- | --- | --- |
| Result | `String[]` array | `List<String>` | `List<String>` |
| Size after creation | Fixed length | Implementation-dependent; often mutable with `Collectors.toList()` though no specific collection type is guaranteed by the API | Unmodifiable list |
| Index access | `array[i]` | `list.get(i)` | `list.get(i)` |
| Fits APIs requiring arrays | Yes | Requires extra conversion | Requires extra conversion |
| Available since | Java 8 | Java 8 | Java 16 |

**Choose an array** when integration interfaces require an array, when working directly with `int[]` / `long[]` / `double[]`, or when a fixed-length result structure is desired. **Choose a List** when working against collection contracts, needing collection methods, or passing data around as `List<T>`.

Both approaches incur the cost of holding all output in memory. A naturally *lazy* Stream loses its element-by-element streaming advantage once all results are gathered into a large array.

## 12. Source Limits and Memory Overhead

Java arrays have an `int` length and must allocate enough memory to hold all elements or references to them. Consequently, `toArray` is unsuitable for collecting **unbounded infinite sources**.

Terminating example:

~~~java
import java.util.Arrays;
import java.util.stream.Stream;

Integer[] firstFive = Stream.iterate(0, n -> n + 1)
        .limit(5)
        .toArray(Integer[]::new);

System.out.println(Arrays.toString(firstFive)); // [0, 1, 2, 3, 4]
~~~

Dangerous example:

~~~java
// Do not run this snippet: the Stream has no natural stopping point.
Object[] forever = Stream.generate(() -> "event")
        .toArray();
~~~

The pipeline above tries to collect every element from an unbounded source. It cannot produce a normal finite result array; the program may run forever or exhaust resources before finishing.

Important cost considerations:

- **Time:** typically must process all output elements of the pipeline, plus the cost of `filter`, `map`, `sorted`, and upstream operations.
- **Memory:** requires space for the result array; some pipelines, especially with `sorted`, `distinct`, or parallel execution, may also require intermediate buffers.
- **Unknown upfront size:** if filters drop many elements or the source does not report a size, the runtime may need to accumulate and allocate buffers before building the final array. Do not build logic around how many times the generator is called.
- **Data volume:** `toArray` can throw `OutOfMemoryError` or array-size limit errors if the source exceeds allocation/representation limits. Never use `toArray` to load entire log files or unbounded datasets.
- **Parallelism:** `parallel()` does not guarantee faster execution. Collecting an ordered result may require chunking and merging; use parallel processing only when work is large enough, functions are independent, and real performance measurements justify it.
- **I/O sources:** if the Stream backs a resource like `Files.lines`, manage closing it with `try-with-resources`. `toArray` does not automatically replace closing I/O resources.

If you only need to test a condition, matching operations like `anyMatch` avoid creating an array; if you only need a few initial elements, place `limit(n)` before `toArray`. If you need a single aggregate value, `count`, `sum`, `reduce`, or `collect` with a suitable collector avoids retaining every element.

## 13. Practical Case: Filtering Records Before Calling a Legacy API

Suppose a legacy library exposes the method:

~~~java
void submitUserIds(String[] ids);
~~~

Application data is in a `List<User>` with an `active` field. We need to submit the IDs of active users, preserving input order and omitting null or empty IDs.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class UserExportDemo {

    static class User {
        private final String id;
        private final boolean active;

        User(String id, boolean active) {
            this.id = id;
            this.active = active;
        }

        String getId() { return id; }
        boolean isActive() { return active; }
    }

    static void submitUserIds(String[] ids) {
        System.out.println(Arrays.toString(ids));
    }

    public static void main(String[] args) {
        List<User> users = Arrays.asList(
                new User("U-10", true),
                new User("U-20", false),
                new User(null, true),
                new User("U-30", true)
        );

        String[] ids = users.stream()
                .filter(User::isActive)
                .map(User::getId)
                .filter(Objects::nonNull)
                .filter(id -> !id.isEmpty())
                .toArray(String[]::new);

        submitUserIds(ids); // [U-10, U-30]
    }
}
~~~

Here `toArray(String[]::new)` clearly satisfies the contract with the external API. Filtering runs **before** creating the array so ineligible records do not need to be kept. The source is a `List` with encounter order, so `U-10` remains before `U-30`.

If data comes from a large database, do not assume `users.stream()` streams directly from the database: the example operates on an in-memory `List<User>`. When handling large data volumes, consider pagination, capping ID counts, or designing APIs that accept batches.

## 14. Quick Error Troubleshooting Table

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| `ClassCastException: [Ljava.lang.Object; ...` | Casting `Stream.toArray()` result from `Object[]` to `String[]` | Call `toArray(String[]::new)` directly on the Stream. |
| `ArrayStoreException` | Generator creates an array whose component type cannot hold certain values | Ensure the array type matches actual elements or convert elements before collecting. |
| `NullPointerException` when converting `Integer` to `int` | Unboxing a `null` element inside `mapToInt` | Handle `null` before unboxing. |
| Does not compile with `toArray(new String[0])` on a Stream | Confusing Collection's overload with Stream's | Use `toArray(String[]::new)`. |
| Does not compile with `toArray(int[]::new)` on `Stream<Integer>` | Stream's generic overload does not create primitive arrays | Use `mapToInt(...).toArray()`. |
| `IllegalStateException` when calling a subsequent terminal operation | Reusing the same Stream object that already ran `toArray` | Create a new Stream from a reusable source, or use the collected array itself. |
| Result consumes too much RAM | `toArray` collects all data and may allocate intermediate buffers | Limit input, process in batches, or use an aggregating terminal operation. |
| Output order does not match expectations | Source lacks encounter order or pipeline altered ordering | Check the source's contract; if needed, use `sorted` with an explicit key. |

## 15. Self-Check Exercises

**Exercise 1.** Distinguish the array types and results:

~~~java
Object[] a = Stream.of("x", "y").toArray();
String[] b = Stream.of("x", "y").toArray(String[]::new);
int[] c = IntStream.of(1, 2).toArray();
~~~

**Answer:** `a` is `Object[]`, `b` is `String[]`, `c` is `int[]`. Contents of `a` and `b` are identical, but the runtime types of the two arrays differ.

**Exercise 2.** Fix the snippet below to produce `int[]`:

~~~java
List<Integer> values = Arrays.asList(3, 5, 7);
Integer[] result = values.stream().toArray(Integer[]::new);
~~~

**Answer:** Use `mapToInt` to switch from an object Stream to an `IntStream`:

~~~java
int[] result = values.stream()
        .mapToInt(Integer::intValue)
        .toArray();
~~~

**Exercise 3.** Given `Stream.of("abc", "x", "de", "four")`, what is the result below?

~~~java
String[] result = Stream.of("abc", "x", "de", "four")
        .filter(s -> s.length() >= 3)
        .map(String::toUpperCase)
        .toArray(String[]::new);
~~~

**Answer:** The array `["ABC", "FOUR"]` because `filter` retains only `"abc"` and `"four"`, and `map` converts them to uppercase. `toArray` collects the post-transformation elements in encounter order.

**Exercise 4.** Why does this snippet fail to terminate normally?

~~~java
String[] result = Stream.generate(() -> "OK")
        .toArray(String[]::new);
~~~

**Answer:** `generate` creates an unbounded source; `toArray` attempts to collect the entire stream and has no stopping boundary. If only 100 elements are needed, add `limit(100)` before `toArray(String[]::new)`.

**Exercise 5.** Does `Stream.toArray(String[]::new)` guarantee the array generator is called only once?

**Answer:** No. The generator may be invoked as needed to allocate arrays for partitions or merging results. Therefore `String[]::new` is a safe expression; never use the generator to count traversals or update shared state.

## 16. Key Takeaways

- `Stream.toArray()` returns `Object[]`; do not cast this result to a specific array type.
- `Stream.toArray(String[]::new)` or `toArray(size -> new String[size])` creates a properly typed array; elements must still be compatible with the requested array type.
- `IntStream.toArray()`, `LongStream.toArray()`, and `DoubleStream.toArray()` produce `int[]`, `long[]`, and `double[]`; to use them, convert to the corresponding primitive stream pipeline.
- `toArray` is a terminal operation that triggers and ends a pipeline, collecting all finite results into an array; it has no automatic stopping mechanism on infinite sources.
- Respect the contracts for **data types**, **ordering**, **element count**, **Stream lifecycle**, and **memory** when deciding to materialize results as an array.

**Main Idea:** When the result must be an array, choose the `toArray` overload based on **the array type you need to receive**, rather than relying on inferred element types. For object Streams, `toArray(MyType[]::new)` is clear and safe; for primitive numeric Streams, use the parameterless `toArray()` overload on `IntStream`, `LongStream`, or `DoubleStream`.
