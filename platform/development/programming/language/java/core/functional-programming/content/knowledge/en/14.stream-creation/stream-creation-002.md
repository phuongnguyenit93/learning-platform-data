# Creating Streams with `Stream.of()`, `Stream.empty()`, and `Stream.ofNullable()`

## 1. Goal

In Java, `java.util.stream.Stream<T>` represents a sequence of elements for performing data-processing operations in a declarative style. When you need to **create a stream** from a few values, from a source with no elements, or from a value that might be `null`, the three common factory methods are:

- `Stream.of(...)`: creates a stream containing **the provided elements**, including a single `null` element if the appropriate overload is selected and `null` is passed in.
- `Stream.empty()`: creates a stream **with no elements**.
- `Stream.ofNullable(value)`: creates a stream **with exactly one element when `value != null`**, or **empty when `value == null`**; added in **Java 9**.

All three methods are **static factory methods** on the `Stream` interface. They create a stream, but do not by themselves turn data into a collection or execute intermediate operations such as `map` or `filter` as soon as those are added to the pipeline.

Understanding this distinction accurately helps avoid confusing **“having no elements”** with **“having one element that is null”**, handle optional input, and understand arrays/varargs correctly.

## 2. Comparing API Signatures and Element Counts

The core signatures (abbreviated for readability):

```java
static <T> Stream<T> of(T t)
static <T> Stream<T> of(T... values)
static <T> Stream<T> empty()
static <T> Stream<T> ofNullable(T t) // Java 9+
```

These are **illustrative signatures**, not a standalone compilable Java class.

| Call | Element count | Meaning |
| --- | ---: | --- |
| `Stream.of("a")` | 1 | One element `"a"` |
| `Stream.of("a", "b")` | 2 | Two elements in order `a`, `b` |
| `Stream.of()` | 0 | No varargs arguments; empty stream |
| `Stream.empty()` | 0 | Empty stream, stating intent clearly |
| `Stream.ofNullable("a")` | 1 | Non-null value present |
| `Stream.ofNullable(null)` | 0 | Value absent |
| `Stream.of((String) null)` | 1 | **Has one null element** |
| `Stream.of("a", null)` | 2 | Two elements, the second element is null |

Saying “empty stream” means a stream containing no elements: `count() == 0`. A stream containing only a single `null` element still has a size of one element. **Null is not an automatic signal for a Stream to skip an element.**

Note that `Stream.of()` with no arguments and `Stream.empty()` both create an empty stream; `empty()` usually expresses intent more clearly when data is known to be absent. With complex generics, you can specify the type explicitly using `Stream.<String>empty()` or `Stream.<String>of()`.

## 3. `Stream.of()`: From One or More Elements

### 3.1. Single Element and Multiple Elements

Use `Stream.of(value)` when you want a stream with one element; use `Stream.of(a, b, c)` when you already have a few elements:

```java
Stream<String> one = Stream.of("Java");
Stream<String> many = Stream.of("Java", "Kotlin", "Scala");
```

This is a code snippet placed inside a method with `import java.util.stream.Stream`. When a terminal operation such as `toList()` or `count()` is called, these elements are processed in the encounter order of a sequential stream from the `of` source.

Complete Java 17+ example, saved in `StreamFactoryDemo.java`:

```java
import java.util.List;
import java.util.stream.Stream;

public class StreamFactoryDemo {
    public static void main(String[] args) {
        List<String> names = Stream.of("An", "Binh", "Chi")
                .map(String::toUpperCase)
                .toList();

        System.out.println(names);
        System.out.println(Stream.of("x").count());
        System.out.println(Stream.of().count());
        System.out.println(Stream.empty().count());
        System.out.println(Stream.ofNullable("Java").count());
        System.out.println(Stream.ofNullable((String) null).count());
    }
}
```

Run:

```bash
javac StreamFactoryDemo.java
java StreamFactoryDemo
```

Result:

```text
[AN, BINH, CHI]
1
0
0
1
0
```

Explanation:

- `Stream.of("An", "Binh", "Chi")` has three elements; `map(String::toUpperCase)` transforms each string; `toList()` collects the result.
- `Stream.of("x")` has exactly one element.
- `Stream.of()` and `Stream.empty()` have 0 elements.
- `Stream.ofNullable("Java")` has one element; `Stream.ofNullable((String) null)` is empty.

The `Stream.toList()` method was added in **Java 16**, so the standalone runnable programs here require **Java 17+** as stated.

### 3.2. `Stream.of()` with null: Choosing the Overload Intentionally

Java has two overloads: `of(T)` and `of(T...)`. Therefore, calling bare `Stream.of(null)` can be interpreted as a **null varargs array** rather than a single null element value; overload resolution and compiler warnings make this statement prone to misunderstanding. Do not use it to represent a possibly absent value.

To test **a single element that is null**, write explicitly:

```java
Stream<String> singleNull = Stream.of((String) null);
```

To **produce no element** if the value is null:

```java
String maybeNull = null;
Stream<String> zeroOrOne = Stream.ofNullable(maybeNull);
```

The two streams above differ in element count. If processed with `map(String::length)`, the stream containing null can throw a `NullPointerException` when the terminal operation runs, whereas `ofNullable(null)` does not invoke the mapper because there are no elements.

Do not confuse `Stream.of((String) null)` with `Optional.of(null)`: `Optional.of(null)` throws `NullPointerException`; a stream can contain null at the source, but many downstream operations cannot tolerate null. **Being able to contain** does not mean **should contain**.

## 4. `Stream.empty()`: Representing No Elements

`Stream.empty()` is suitable when a processing branch has nothing to emit, such as an API that must return `Stream<String>` when no results are found.

Example:

```java
static Stream<String> tagsFor(boolean enabled) {
    if (!enabled) {
        return Stream.empty();
    }
    return Stream.of("java", "stream");
}
```

This is **a method inside a class**, requiring `Stream` to be imported; when `enabled == false`, the result has 0 elements. Choosing an empty stream allows the caller to continue calling `map`, `filter`, `flatMap`, and terminal operations without receiving `null`.

An important case regarding generic types:

```java
Stream<String> none = Stream.empty();
Stream<Integer> noNumbers = Stream.empty();
Stream<String> explicit = Stream.<String>empty();
```

Java usually infers `T` from the assignment context. If inference runs into trouble in a compound expression or complex overloaded method, use the type witness `Stream.<String>empty()` to clarify intent.

**No element computation takes place** when calling `count()` on an empty stream; terminal operations like `forEach` have no elements to pass to the Consumer. Using `empty()` does not mean there is an “empty object” at the first element position.

### When a Missing-Data Branch Should Not Throw an Error

Save `EmptyStreamDemo.java`:

```java
import java.util.stream.Stream;

public class EmptyStreamDemo {
    static Stream<String> permissions(boolean active) {
        return active
                ? Stream.of("READ", "WRITE")
                : Stream.empty();
    }

    public static void main(String[] args) {
        System.out.println(permissions(true).toList());
        System.out.println(permissions(false).toList());
        System.out.println(
                permissions(false).map(String::length).count());
    }
}
```

Run:

```bash
javac EmptyStreamDemo.java
java EmptyStreamDemo
```

Output:

```text
[READ, WRITE]
[]
0
```

In the empty case, `map(String::length)` does not need to process any value. Note that according to the Stream specification, an implementation may skip certain intermediate operations if it knows they do not affect the terminal result (especially with `count()` on a sized source), so **do not use side effects of `map` to verify whether it ran**. To test practical behavior, evaluate the observable values/output according to the pipeline contract.

## 5. `Stream.ofNullable()`: 0 or 1 Element from a Single Value

`Stream.ofNullable(T t)` was added in Java 9 because the need to convert a possibly null value into a stream arises frequently, especially when combined with `flatMap`:

```text
value != null  → Stream.of(value)  → 1 element
value == null  → Stream.empty()    → 0 elements
```

Equivalent in element count and value to the conditional expression:

```java
static <T> Stream<T> zeroOrOne(T value) {
    return value == null ? Stream.empty() : Stream.of(value);
}
```

This is a complete generic method body, though it needs to be placed inside a class with `import java.util.stream.Stream`. In Java 9+, you usually just call `Stream.ofNullable(value)` for clarity.

When you have the result of a lookup that might be null:

```java
String nickname = findNickname(); // May return null.
Stream<String> stream = Stream.ofNullable(nickname);
```

This snippet assumes `findNickname()` already exists. If the nickname is absent, the stream is empty; if present, it has one string. There is no need to create a collection just to pass a nullable input into a pipeline.

### Java 17+ Example Filtering Nulls with `flatMap`

Create `NullableFlatMapDemo.java`:

```java
import java.util.List;
import java.util.stream.Stream;

public class NullableFlatMapDemo {
    public static void main(String[] args) {
        List<String> raw = List.of("Java", "Stream", "API");

        List<Integer> lengths = raw.stream()
                .map(word -> word.equals("Stream") ? null : word)
                .flatMap(Stream::ofNullable)
                .map(String::length)
                .toList();

        System.out.println(lengths);
        System.out.println(lengths.size());
    }
}
```

Run:

```bash
javac NullableFlatMapDemo.java
java NullableFlatMapDemo
```

Output:

```text
[4, 3]
2
```

Step by step:

1. `raw.stream()` creates a stream from the three elements of the list.
2. `map` turns `"Stream"` specifically into `null` to simulate a lookup with no result.
3. `flatMap(Stream::ofNullable)` replaces each element with a 0- or 1-element stream: null data emits **0**, present data emits **1**.
4. `map(String::length)` only sees `"Java"` and `"API"`, and converts them into `4` and `3`.

`flatMap` is useful because it flattens the small streams produced from each element into a single stream of results. If you used `map(Stream::ofNullable)` instead of `flatMap`, the result would be a stream containing **inner `Stream<String>` objects**, which is completely different from a `Stream<String>` ready for further processing.

In cases where you only need to remove nulls from an existing stream, `filter(Objects::nonNull)` is also a clear option:

```java
Stream<String> values = Stream.of("A", null, "B");
Stream<String> nonNull = values.filter(java.util.Objects::nonNull);
```

This is a declaration snippet inside a method. With `ofNullable`, each nullable input becomes a small stream, suitable when already in a `flatMap` chain or wanting to convert a single nullable value into a stream.

## 6. Common Pitfall: `Stream.of(array)` and Varargs Behavior

`Stream.of(T... values)` uses varargs, so a reference array can be passed as the list of elements. With a `String[]` array:

```java
String[] names = {"An", "Binh"};
Stream<String> eachName = Stream.of(names);
```

Normally the compiler chooses the varargs overload using the `String[]` array as the elements, creating a stream of **two strings**.

Conversely, when you want a stream with **one element that is the array object itself**:

```java
String[] names = {"An", "Binh"};
Stream<Object> oneArray = Stream.of((Object) names);
```

Casting to `Object` makes the single argument be treated as an object holding the array, so the stream has **1 element of type `Object`** pointing to the array. Choosing the target type and overload is therefore very important.

Especially with **primitive arrays**:

```java
int[] numbers = {1, 2, 3};
Stream<int[]> arrayAsElement = Stream.of(numbers);
```

The type of the stream is `Stream<int[]>`, which has only **one element that is the `int[]` array**; not three `Integer` elements. Java generics do not accept primitive types as type arguments, so `T` here is `int[]`. To create a stream of integers directly from a primitive array, use `Arrays.stream(numbers)` to get an `IntStream`, or use `IntStream.of(1, 2, 3)`. Those factories belong to the primitive stream family, distinct from `Stream<T>`.

### Complete Example to Observe Element Counts

Save `StreamArrayDemo.java`:

```java
import java.util.Arrays;
import java.util.stream.Stream;

public class StreamArrayDemo {
    public static void main(String[] args) {
        String[] names = {"An", "Binh"};
        int[] numbers = {1, 2, 3};

        System.out.println(Stream.of(names).count());
        System.out.println(Stream.of((Object) names).count());
        System.out.println(Stream.of(numbers).count());
        System.out.println(Arrays.stream(numbers).sum());
        System.out.println(Stream.of("A", "B").toList());
    }
}
```

Run:

```bash
javac StreamArrayDemo.java
java StreamArrayDemo
```

Output:

```text
2
1
1
6
[A, B]
```

When you have a **reference** array and want a stream of each element, `Arrays.stream(referenceArray)` also expresses intent clearly and avoids overload confusion. Do not pass a **null reference array** to the varargs overload and expect it to be “0 elements”: a null array is not an empty array. If you want no elements, use `Stream.empty()` or handle the null source with an explicit branch. `Stream.ofNullable(array)` requires type consideration: if you pass the whole array as a single value, you may create a stream of **one array**, not a stream of each element in the array.

## 7. Nulls, Downstream Operations, and Common Errors

A key point to remember is that Stream factories handle null differently:

- `Stream.of((String) null)`: has one null element.
- `Stream.of("A", null)`: has both `"A"` and null.
- `Stream.empty()`: has no elements.
- `Stream.ofNullable(null)`: has no elements.
- `Stream.ofNullable("A")`: has one element `"A"`.

Because a stream from `of` can contain null, downstream operations like `map(String::length)` or `String::toUpperCase` will throw a `NullPointerException` if they actually encounter null. Some other operations also require non-null elements; for example, `findFirst()`/`findAny()` produce an `Optional` and cannot hold a null value as the selected element. Do not assume that every terminal operation handles null just because the Stream source allows null.

Create `NullStreamDemo.java`:

```java
import java.util.stream.Stream;

public class NullStreamDemo {
    public static void main(String[] args) {
        Stream<String> oneNull = Stream.of((String) null);
        Stream<String> noElement = Stream.ofNullable((String) null);

        System.out.println(oneNull.count());
        System.out.println(noElement.count());

        System.out.println(
                Stream.of((String) null)
                        .map(value -> value == null ? 0 : value.length())
                        .toList());

        System.out.println(
                Stream.ofNullable((String) null)
                        .map(String::length)
                        .toList());
    }
}
```

Run:

```bash
javac NullStreamDemo.java
java NullStreamDemo
```

Output:

```text
1
0
[0]
[]
```

Because the mapper in the third call **handles null**, the result is a list containing one element, `0`; in the fourth call, the mapper does not run because the stream is empty. This is fundamentally different from passing null expecting the method to skip it automatically.

Do not use `Stream.ofNullable((String) null).findFirst().orElse(...)` to conclude that the stream had a null element: the source was already empty, so there is no element to select. Conversely, `Stream.of((String) null).findFirst()` can throw `NullPointerException` because `Optional` does not accept a null element as a present value.

## 8. Evaluation Timing, Pipelines, and Laziness

The methods `Stream.of`, `Stream.empty`, and `Stream.ofNullable` **create the stream source**. Intermediate transformations, such as `map` or `filter`, are generally executed when a terminal operation requests data. This does not mean every argument expression passed to the factory is deferred.

Example:

```java
Stream<String> stream = Stream.of(loadName());
```

Suppose `loadName()` is a method returning `String`. Java evaluates the argument `loadName()` **immediately when `Stream.of` is called**, and only then creates a stream with one element holding the computed value. Attaching `map` afterward is the part of the pipeline that can be evaluated lazily.

To defer **creating the stream/source value** until it is actually needed, you can store a `Supplier<Stream<String>>`:

```java
Supplier<Stream<String>> supplier =
        () -> Stream.of(loadName());
```

This is a code snippet inside a method with `Supplier` and `Stream` imported; the call to `loadName()` is inside the lambda body, so it is only executed when `supplier.get()` is called. When you need a re-creatable source, call `supplier.get()` to obtain a **new stream** each time, instead of trying to reuse an already-consumed stream.

A stream is not a collection that can be traversed arbitrarily multiple times: after a terminal operation, do not reuse the same stream for a second terminal operation. For example, `Stream<String> s = Stream.of("A"); s.count(); s.toList();` is incorrect usage; the later call can throw `IllegalStateException` because the stream has already been operated upon or closed.

When using `Stream.of("A", "B")` on a sequential stream, the source has an encounter order matching the argument order. With a parallel pipeline, you must consider the ordering contract of each terminal operation; do not rely on the side-effect order of `forEach` to infer data order in a parallel stream.

## 9. Choosing a Factory by Business Intent

| Situation | Appropriate creation method | Reason |
| --- | --- | --- |
| Have a single value guaranteed non-null | `Stream.of(value)` | Clearly one element |
| Have multiple individual values | `Stream.of(a, b, c)` | Simple for small data |
| No elements to emit | `Stream.empty()` | Conveys empty intent most clearly |
| Have a single object that may be null | `Stream.ofNullable(value)` | Null becomes 0 elements, non-null becomes 1 |
| Have a reference array to traverse element by element | `Arrays.stream(values)` or `Stream.of(values)` | Produces a stream of each element; note the array must not be null |
| Have a primitive `int[]` array | `Arrays.stream(intArray)` | Produces an `IntStream` of each integer |
| Want a stream containing the array itself as one element | `Stream.of((Object) values)` | Explicitly states the element type is the array as `Object` |
| Want to remove null elements from an existing stream | `filter(Objects::nonNull)` | Removes nulls in the pipeline |
| Want to map each input to zero-or-one output | `flatMap(x -> Stream.ofNullable(...))` | Flattens 0- or 1-element streams |

In an API, if a method returns a stream and a case genuinely has no data, prefer returning `Stream.empty()` instead of `null`. The caller can then always compose and use the Stream API consistently.

Note that `List.of(...)` does not accept null elements, whereas a stream created with `Stream.of("A", null)` can contain null. Converting back and forth between collections and streams requires checking each API's null contract separately, especially when using collectors or converting back to a collection.

## 10. Common Misconceptions

1. **“`Stream.of(null)` definitely gives a stream containing one null.”** Do not write this ambiguously due to the varargs overload. If you want one null element, write `Stream.of((String) null)`; if you want to skip null, use `Stream.ofNullable(value)`.
2. **“`Stream.empty()` contains one empty element.”** False: the element count is 0, with no placeholder value.
3. **“`Stream.ofNullable(null)` gives a stream with one null.”** False: the result is empty.
4. **“One null element and zero elements are the same.”** False: `count()` differs; mappers, predicates, and terminal operations can also behave differently.
5. **“`Stream.of(array)` always contains the single array itself.”** Not true for reference arrays when the normal varargs overload applies; whereas primitive arrays such as `int[]` usually produce one `int[]` element.
6. **“`Stream.of(intArray)` gives an `IntStream`.”** False: if you want a primitive stream of each integer, use `Arrays.stream(intArray)` or `IntStream.of(...)`.
7. **“`ofNullable` works on all Java 8.”** False: it requires Java 9+; Java 8 typically uses a conditional expression returning `Stream.empty()` or `Stream.of(value)`.
8. **“After creating a Stream, you can call multiple terminal operations.”** False: a stream is used for only one chain of operations with a terminal operation; create a new stream when you want to process again.
9. **“Operations on a stream are always lazy even when calling a method to produce the input value.”** False: the argument expression of `Stream.of(load())` is evaluated before the `of` call executes.
10. **“The factory has no nulls in its input, so all transformations are safe.”** Data can produce nulls in `map`/`flatMap` or from other parts of the pipeline. Each stage needs a clear contract.
11. **“`map(Stream::ofNullable)` flattens data.”** False: `map` produces elements that are sub-streams; `flatMap(Stream::ofNullable)` is what flattens them.
12. **“`Stream.empty()` is only for String.”** False: it is a generic factory and works with any reference element type.

## 11. Self-Check Exercises

Predict the element count and result values in Java 17:

```java
String value = null;

long a = Stream.of((String) null).count();
long b = Stream.ofNullable(value).count();
long c = Stream.<String>empty().count();
long d = Stream.of("A", "B").count();

List<String> words = Stream.of("A", null, "B")
        .flatMap(Stream::ofNullable)
        .toList();
```

The code snippet above is placed inside a method and requires importing `java.util.stream.Stream` along with `java.util.List`.

**Answer:** `a = 1`; `b = 0`; `c = 0`; `d = 2`; `words = ["A", "B"]`. Because `Stream.of((String) null)` contains one null element, `count()` equals 1; `ofNullable(null)` and `empty()` contain nothing; `flatMap(Stream::ofNullable)` removes the null branch while keeping the remaining values.

Extended exercise: with `String[] names = {"Lan", "Mai"}`, compare `Stream.of(names).count()` with `Stream.of((Object) names).count()`. The results are **2** and **1**, respectively. If replaced with `int[] nums = {1, 2}`, `Stream.of(nums).count()` equals **1**, while `Arrays.stream(nums).count()` equals **2**.

## 12. Takeaways

When creating a stream, ask: **How many elements does the source have, and should null be treated as an element or as absence?**

- **`of(values...)`** — the provided values are elements; be careful with null and array overloads.
- **`empty()`** — no elements, no sentinel needed.
- **`ofNullable(value)`** — **0 or 1** element; null is equivalent to having no elements.

Also check the stream's element type: `Stream<String>` is different from `Stream<String[]>` and `IntStream`. Only after choosing the right factory can the downstream pipeline properly perform the intended operations on the desired elements.

**References:** Java SE `java.util.stream.Stream` (`of`, `empty`, `ofNullable` factories), `java.util.Arrays.stream`, `java.util.stream.IntStream`; Java Language Specification on overload resolution, varargs, and method invocation evaluation order.
