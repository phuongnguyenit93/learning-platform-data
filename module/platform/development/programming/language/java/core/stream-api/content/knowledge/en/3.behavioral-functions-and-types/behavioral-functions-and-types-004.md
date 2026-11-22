# Type Inference, Generics, and Handling Compile Errors in a Pipeline

## 1. Why Understand Types When Using the Stream API?

The Java Stream API lets you process data declaratively: pull data from a source, pass it through intermediate operations like `filter` and `map`, and end with `collect` or `reduce`. Pipelines can be **lazy** (deferring execution), yet **the compiler still type-checks** every operation at compile time.

When first learning the Stream API, a short expression can seem puzzling:

```java
List<Integer> doDai = tenKhoaHoc.stream()
    .filter(ten -> ten.length() >= 4)
    .map(String::length)
    .collect(Collectors.toList());
```

Why must `filter` return `boolean`, how can `map` change from `String` to `Integer`, and why must `collect` match `List<Integer>`? That is the work of **generics**, **functional interfaces**, and **type inference**.

This lesson belongs to the **Behavioral Functions and Types** chapter of the `JAVA_STREAM_API` module, focusing on reading types through a pipeline, diagnosing compile errors, and fixing the root cause. This skill is also foundational before working with `groupingBy`, custom collectors, parallel processing, `Spliterator`, and Stream Gatherers.

After this lesson, you will be able to:

- Track the types `T` and `R` across every step in a pipeline.
- Understand how the compiler infers lambda parameter types and `map` results.
- Recognize the roles of `Predicate`, `Function`, `Comparator`, and the `? super` and `? extends` wildcards.
- Fix common errors when combining `filter`, `map`, `flatMap`, `mapToInt`, and `collect`.
- Distinguish **compile-time** errors from **runtime** errors.

## 2. Runnable Example: Tracking Types End-to-End

The following code is compatible with **Java 8 and later**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class KieuTrongPipeline {
    public static void main(String[] args) {
        List<String> tenKhoaHoc = Arrays.asList(
            " Java ", "Go", "Kotlin", "java api"
        );

        List<Integer> doDai = tenKhoaHoc.stream()
            .map(String::trim)
            .filter(ten -> ten.length() >= 4)
            .map(String::length)
            .collect(Collectors.toList());

        System.out.println(doDai); // [4, 6, 8]
    }
}
```

Read the pipeline as a chain of type transitions:

```text
List<String> tenKhoaHoc
       │ stream()
       ▼
Stream<String>
       │ map(String::trim)
       ▼
Stream<String>
       │ filter(ten -> ten.length() >= 4)
       ▼
Stream<String>
       │ map(String::length)
       ▼
Stream<Integer>
       │ collect(Collectors.toList())
       ▼
List<Integer>
```

| Expression | Result type | Reason |
| --- | --- | --- |
| `tenKhoaHoc` | `List<String>` | Each element is a `String` name. |
| `tenKhoaHoc.stream()` | `Stream<String>` | `stream()` preserves the source's element type. |
| `.map(String::trim)` | `Stream<String>` | `trim()` takes a string and returns a string. |
| `.filter(ten -> ten.length() >= 4)` | `Stream<String>` | `filter` only selects or drops elements; it does not change the type. |
| `.map(String::length)` | `Stream<Integer>` | `length()` returns `int`, boxed into `Integer` in `Stream<Integer>`. |
| `.collect(Collectors.toList())` | `List<Integer>` | Collects elements of `Stream<Integer>` into a list. |

Note: `map` and `filter` are lazy intermediate operations. Type inference happens at compile time; actual data traversal occurs when the terminal operation `collect` is called. These two aspects are independent.

## 3. Reading Generic Signatures of Operations

You can think of a `Stream<T>` as a flow of elements of type `T`. Some key signatures (abbreviated from the Java API) are:

```java
// T is the current element type of Stream<T>.
Stream<T> filter(Predicate<? super T> predicate);

<R> Stream<R> map(Function<? super T, ? extends R> mapper);

<R, A> R collect(Collector<? super T, A, R> collector);
```

Meaning:

- `filter` accepts a condition testing a `T` element and returns a stream of **the same type `T`**.
- `map` accepts a transformation function from `T` to `R`; the output is **`Stream<R>`**. `R` may be the same as or different from `T`.
- `collect` accepts a collector capable of processing the stream's elements and producing an aggregated value of type `R`. The letter `A` in `Collector<T, A, R>` is the internal accumulation type, which usually does not need to be written explicitly when using built-in collectors.

For example:

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

List<Integer> doDai = ten.stream()
    .map(String::length)
    .collect(Collectors.toList());
```

From `String::length`, the compiler determines `R = Integer` (after boxing). Therefore, in the final assignment, `List<Integer>` is the matching type.

### 3.1. Functional Interfaces Determine the Lambda's Type

A **functional interface** has exactly one abstract method (Single Abstract Method, SAM). When a lambda or method reference appears inside a Stream call, Java uses the expected parameter type (**target type**) to check it.

| Functional interface | Conceptual method | Commonly used with |
| --- | --- | --- |
| `Predicate<T>` | `boolean test(T value)` | `filter` |
| `Function<T, R>` | `R apply(T value)` | `map` |
| `Consumer<T>` | `void accept(T value)` | `forEach` |
| `Comparator<T>` | `int compare(T a, T b)` | `sorted` |
| `BinaryOperator<T>` | `T apply(T a, T b)` | `reduce` with two values of the same type |

The same lambdas can be written with more explicit types:

```java
import java.util.function.Function;
import java.util.function.Predicate;

Predicate<String> duDai = ten -> ten.length() >= 4;
Function<String, Integer> layDoDai = ten -> ten.length();

List<Integer> ketQua = ten.stream()
    .filter(duDai)
    .map(layDoDai)
    .collect(Collectors.toList());
```

In `.filter(ten -> ten.length() >= 4)`, `ten` is inferred as `String` because the input stream is `Stream<String>`. There is no need to redeclare `String` for each lambda parameter.

### 3.2. Method References Also Need a Target Type

`String::length` is a shorthand equivalent to `s -> s.length()` when the target type is `Function<String, Integer>`.

```java
Function<String, Integer> layDoDai = String::length;
List<Integer> doDai = ten.stream()
    .map(layDoDai)
    .collect(Collectors.toList());
```

A **standalone** method reference cannot be inferred without a target type:

```java
// DOES NOT COMPILE (Java 10+): method reference lacks a target type.
var layDoDai = String::length;
```

The fix is to supply a functional interface:

```java
Function<String, Integer> layDoDai = String::length;
```

The `var` keyword infers its type from the initializer expression; the method reference itself has no concrete type for `var` to infer. In `stream.map(String::length)`, by contrast, `map`'s parameter provides the target type.

## 4. Generics in Pipelines: `T`, `R`, and Wildcards

### 4.1. `Stream<String>` Differs from `Stream<Integer>`

Java checks element types across every call. This example **does not compile**:

```java
List<String> ten = Arrays.asList("Java", "Go");

// WRONG: String::length produces Integer, not String.
List<String> doDai = ten.stream()
    .map(String::length)
    .collect(Collectors.toList());
```

Fix the type of the receiving variable:

```java
List<Integer> doDai = ten.stream()
    .map(String::length)
    .collect(Collectors.toList());
```

Do not cast to hide the error. Ask: "**After the last step of the pipeline, what type is each element actually?**"

### 4.2. Generics Are Invariant

Even though `Integer` is a subtype of `Number`, `Stream<Integer>` is **not** a subtype of `Stream<Number>`.

```java
List<Integer> so = Arrays.asList(1, 2, 3);

// DOES NOT COMPILE:
Stream<Number> luongSo = so.stream();
```

Two valid approaches, depending on your goal:

```java
// Only need to read values as Number:
Stream<? extends Number> luongSo1 = so.stream();

// Need an exact Stream<Number>; explicitly convert each element:
Stream<Number> luongSo2 = so.stream()
    .map(n -> (Number) n);
```

With the first approach, `? extends Number` expresses "some type that is `Number` or a subtype of it". Do not assume that any generic parameterized with a subtype can substitute for the generic parameterized with its supertype.

### 4.3. Why Are There `? super T` and `? extends R`?

The signature of `map` is:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
```

- `? super T` on the **input**: the function can accept `T` or a supertype of `T`.
- `? extends R` on the **output**: the function can return `R` or a subtype of `R`.

Example:

```java
import java.util.function.Function;

Function<CharSequence, String> chuanHoa =
    value -> value.toString().trim();

List<String> ten = Arrays.asList(" Java ", " Go ");
List<String> ketQua = ten.stream()
    .map(chuanHoa)
    .collect(Collectors.toList());

System.out.println(ketQua); // [Java, Go]
```

`chuanHoa` accepts `CharSequence`, which is a supertype (an interface implemented by `String`), so it still works to process `Stream<String>`.

Mnemonic **PECS**: *Producer Extends, Consumer Super*. Inputs that receive/consume `T` are typically flexible with `super`; outputs that produce/emit values are typically flexible with `extends`. This is how to read wildcards in API signatures, not a requirement to write wildcards manually in every pipeline.

### 4.4. Writing Reusable Generic Methods

When passing filters and transformations as parameters, preserve the relationship between source type `T` and target type `R`:

```java
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public static <T, R> List<R> chonVaBienDoi(
        List<T> nguon,
        Predicate<? super T> dieuKien,
        Function<? super T, ? extends R> phepBienDoi) {

    return nguon.stream()
        .filter(dieuKien)
        .map(phepBienDoi)
        .collect(Collectors.toList());
}
```

Invocation:

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

List<Integer> doDai = chonVaBienDoi(
    ten,
    s -> s.length() >= 4,
    String::length
);

System.out.println(doDai); // [4, 6]
```

The compiler infers `T = String` and `R = Integer` from `List<String>` and `String::length`. There is no need to use raw types (`List` or `Stream` without type arguments).

## 5. Common Compile Errors and How to Fix Them

> Snippets marked "DOES NOT COMPILE" are intentionally broken examples for analyzing errors; do not copy them verbatim into a runnable program. Exact error messages may vary depending on your `javac` version or IDE.

### Error 1: `filter` Returns a Non-`boolean` Value

```java
// DOES NOT COMPILE: length() returns int, not boolean.
ten.stream()
    .filter(s -> s.length())
    .collect(Collectors.toList());
```

`filter` expects a `Predicate<String>`. Fix it with a comparison condition:

```java
List<String> ketQua = ten.stream()
    .filter(s -> s.length() >= 4)
    .collect(Collectors.toList());
```

If you want to **get the lengths** instead of **filtering by length**, use `map(String::length)`.

### Error 2: Receiving Variable Type Does Not Match `map`

```java
// DOES NOT COMPILE: collect produces List<Integer>.
List<String> ketQua = ten.stream()
    .map(String::length)
    .collect(Collectors.toList());
```

Change `List<String>` to `List<Integer>`, or change the `map` step so the output is actually strings. Avoid casting to `(List<String>)` because that does not resolve the element type mismatch.

### Error 3: Element Type Widened to `Object`

```java
import java.util.stream.Stream;

Stream<Object> duLieu = Stream.of("Java", 42);

// DOES NOT COMPILE: the method reference requires String,
// but each element is currently seen as Object.
duLieu.map(String::length);
```

One way to handle mixed data is to filter and check the type before casting:

```java
List<Integer> doDai = Stream.<Object>of("Java", 42)
    .filter(String.class::isInstance)
    .map(String.class::cast)
    .map(String::length)
    .collect(Collectors.toList());

System.out.println(doDai); // [4]
```

After `.map(String.class::cast)`, the type is `Stream<String>`, so `String::length` is valid. For homogeneous data, the better solution is to declare the source properly as `List<String>` from the start.

### Error 4: Confusing `map` with `flatMap`

Given a list containing multiple sub-lists:

```java
List<List<String>> nhom = Arrays.asList(
    Arrays.asList("Java", "Kotlin"),
    Arrays.asList("Go")
);
```

`map(List::stream)` creates a **stream of streams**, so assigning to `List<String>` will not compile:

```java
// DOES NOT COMPILE: the result is List<Stream<String>>.
List<String> tatCa = nhom.stream()
    .map(List::stream)
    .collect(Collectors.toList());
```

`flatMap` flattens the sub-streams into a single `Stream<String>`:

```java
List<String> tatCa = nhom.stream()
    .flatMap(List::stream)
    .collect(Collectors.toList());

System.out.println(tatCa); // [Java, Kotlin, Go]
```

Inspect the output type of the expression inside `map`: if it is already `Stream<X>` yet you want individual `X` elements, consider `flatMap`.

### Error 5: Mixing Up `Stream<Integer>` and `IntStream`

`map(String::length)` produces `Stream<Integer>`, whereas `mapToInt(String::length)` produces **`IntStream`**, a stream specialized for primitive `int`.

```java
import java.util.stream.IntStream;

IntStream doDai = ten.stream().mapToInt(String::length);
int tongDoDai = ten.stream().mapToInt(String::length).sum();
```

`IntStream` does **not** have a `collect(Collector)` overload like `Stream<T>`:

```java
// DOES NOT COMPILE: IntStream does not accept a Collector here.
List<Integer> doDai = ten.stream()
    .mapToInt(String::length)
    .collect(Collectors.toList());
```

Fix with `boxed()` to return to `Stream<Integer>`:

```java
List<Integer> doDai = ten.stream()
    .mapToInt(String::length)
    .boxed()
    .collect(Collectors.toList());
```

If you only need the sum, average, or maximum, prefer `sum()`, `average()`, and `max()` on `IntStream` without unnecessary boxing.

### Error 6: Lambda Calling a Method That Throws a Checked Exception

Standard functional interfaces like `Function.apply` **do not declare checked exceptions**. For example, `Files.readAllLines` can throw `IOException`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.List;

List<Path> tep = Arrays.asList(Paths.get("du-lieu.txt"));

// DOES NOT COMPILE: IOException is unhandled.
tep.stream().map(Files::readAllLines);
```

Handle the error inside the lambda—for instance, wrapping it into `UncheckedIOException` to preserve the original cause:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Path> tep = Arrays.asList(Paths.get("du-lieu.txt"));

List<String> cacDong = tep.stream()
    .map(path -> {
        try {
            return Files.readAllLines(path);
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    })
    .flatMap(List::stream)
    .collect(Collectors.toList());
```

This is one error-handling strategy, not the only one. To run the example, `du-lieu.txt` must exist in the working directory or be replaced with an actual file path. For large resources, consider proper resource opening/closing; for instance, `Files.lines` returns an I/O-backed stream that must be closed.

### Error 7: Variable Captured by a Lambda Is Not "Effectively Final"

```java
int doDaiToiThieu = 4;

// DOES NOT COMPILE when the variable is reassigned below.
List<String> ketQua = ten.stream()
    .filter(s -> s.length() >= doDaiToiThieu)
    .collect(Collectors.toList());

doDaiToiThieu = 6;
```

A local variable used by a lambda must be `final` or **effectively final** (never reassigned after initialization).

```java
final int doDaiToiThieu = 4;

List<String> ketQua = ten.stream()
    .filter(s -> s.length() >= doDaiToiThieu)
    .collect(Collectors.toList());
```

Note: this rule concerns **reassigning the local variable/reference**, not making every referenced object immutable. Even so, mutating external state from a lambda makes pipelines harder to reason about and is especially dangerous when switching to parallel processing.

### Error 8: Using Raw Types Loses Generic Information

```java
// Avoid: List without <String>.
List tenKhongKieu = Arrays.asList("Java", "Go");
```

Raw types strip static type checking, typically trigger unchecked warnings, and cause lambda parameters to be seen too broadly. Simply declare the full type:

```java
List<String> ten = Arrays.asList("Java", "Go");

List<Integer> doDai = ten.stream()
    .map(String::length)
    .collect(Collectors.toList());
```

Do not use `@SuppressWarnings("unchecked")` to hide errors without actually restoring proper type constraints.

## 6. How to Diagnose When the IDE Reports "cannot infer type" or "incompatible types"

Messages such as `cannot infer type-variable(s)`, `bad return type in lambda expression`, `invalid method reference`, or `incompatible types` usually point to a **type conflict site**. The exact wording depends on the compiler tool; inspect the failing line along with the "required" and "found" types if shown.

Follow this order:

1. **Verify the source type**: `List<String>`, `List<MyType>`, `Stream<?>`, or raw `List`? The input type determines what the lambda receives.
2. **Break the pipeline step by step**: after `filter`, the type stays the same; after `map`, `flatMap`, or `mapToInt`, the type may change.
3. **Check the lambda/method reference return type**: `boolean` for `filter`; type `R` for `map`; `Stream<R>` for `flatMap`.
4. **Check the target type**: is the `collect` result truly compatible with the `List<R>`, `Set<R>`, or `Map<K, V>` you declared?
5. **Check Java-specific rules**: method references need a target type, lambdas cannot declare checked exceptions, and captured variables must be effectively final.
6. **Add explicit types to isolate the mismatch**: try intermediate variables like `Stream<String>`, `Stream<Integer>`, or `Function<String, Integer>`. Once fixed, you can inline them back if readability stays clear.

Example of splitting a pipeline to pinpoint an error:

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

Stream<String> s1 = ten.stream();
Stream<String> s2 = s1.filter(s -> s.length() >= 4);
Stream<Integer> s3 = s2.map(String::length);
List<Integer> ketQua = s3.collect(Collectors.toList());
```

This snippet consumes the stream only **once** at the end. If you mistakenly declare `Stream<String> s3`, the compiler will point directly at the mismatched `map` step. When more complex inference is needed, you can write the lambda parameter type explicitly:

```java
List<Integer> ketQua = ten.stream()
    .map((String s) -> s.length())
    .collect(Collectors.toList());
```

Explicit types make errors easier to read, though they **cannot fix** a transformation that is fundamentally incompatible with its input.

### Boundary Between Compile-Time Errors and Runtime Errors

| Situation | Classification | Notes |
| --- | --- | --- |
| `filter(s -> s.length())` | Compile error | `Predicate` requires `boolean`. |
| Assigning `List<Integer>` to `List<String>` | Compile error | Incompatible generics. |
| `map(String::length)` on `Stream<Object>` | Compile error | Elements are not guaranteed to be `String`. |
| Calling a method on a `null` element | Runtime error | May throw `NullPointerException`. |
| Reusing a stream after calling `collect` | Runtime error | May throw `IllegalStateException`. |
| `Collectors.toMap` with duplicate keys and no merge function | Runtime error | May throw `IllegalStateException` due to duplicate key. |
| Sharing/mutating external state from a lambda | Logic or concurrency hazard | May still compile yet produce unpredictable results. |

Example of reusing a stream:

```java
Stream<String> luong = ten.stream();
long soLuong = luong.count();

// COMPILES, but you cannot reuse a consumed stream.
List<String> danhSach = luong.collect(Collectors.toList());
```

Correct approach: create a **new stream** from the source whenever another terminal operation is needed.

## 7. When Generics Appear in `reduce` and `collect`

Type inference is not limited to `map`. For instance, after turning names into lengths, types continue to govern the terminal operation:

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

int tong = ten.stream()
    .map(String::length)       // Stream<Integer>
    .reduce(0, Integer::sum);  // Integer, auto-unboxed to int

System.out.println(tong); // 12
```

With a grouping collector:

```java
import java.util.Map;

Map<Integer, List<String>> nhomTheoDoDai = ten.stream()
    .collect(Collectors.groupingBy(String::length));

System.out.println(nhomTheoDoDai.get(4)); // [Java]
```

`String::length` acts as `Function<String, Integer>`, so the map's key type is `Integer`. `groupingBy` returns the matching result structure `Map<Integer, List<String>>`. The compiler checks types even while the pipeline is merely being constructed.

When learning custom collectors, `Spliterator`, parallel streams, or Gatherers, keep applying the same habit: **identify the incoming element type, outgoing element type, and final result type**. Those mechanisms have their own type contracts and lifecycles; do not assume every operation behaves just like `map`.

## 8. Practice Exercises

### Exercise 1: Predict Types and Results

```java
List<String> ma = Arrays.asList(" A1 ", "B22", " C333 ", "D");

List<Integer> ketQua = ma.stream()
    .map(String::trim)
    .filter(s -> s.length() >= 3)
    .map(String::length)
    .collect(Collectors.toList());
```

Write down the data type after each operation and predict the contents of `ketQua`.

### Exercise 2: Find Two Compile Errors

```java
List<String> ten = Arrays.asList("Java", "Go");

List<String> ketQua = ten.stream()
    .filter(s -> s.length())
    .map(String::length)
    .collect(Collectors.toList());
```

Fix the code to obtain a `List<Integer>` containing the lengths of **names with at least 3 characters**.

### Exercise 3: Choose `map` or `flatMap`?

```java
List<List<Integer>> nhomSo = Arrays.asList(
    Arrays.asList(1, 2),
    Arrays.asList(3, 4)
);
```

Write a pipeline producing `List<Integer>` with result `[2, 4, 6, 8]`: flatten the sub-lists and double each number.

<details>
<summary>Answers and explanations</summary>

**Exercise 1:** after `stream()` is `Stream<String>`; after `map(String::trim)` is still `Stream<String>`; after `filter` is still `Stream<String>`; after `map(String::length)` is `Stream<Integer>`; after `collect` is `List<Integer>`. The result is `[3, 4]`, corresponding to `"B22"` and `"C333"`; `"A1"` and `"D"` are dropped because they are shorter than 3 characters.

**Exercise 2:** `filter` must return a boolean; after `map(String::length)`, the list contains `Integer`.

```java
List<Integer> ketQua = ten.stream()
    .filter(s -> s.length() >= 3)
    .map(String::length)
    .collect(Collectors.toList());

// [4]
```

**Exercise 3:** `flatMap` turns `Stream<List<Integer>>` into `Stream<Integer>`, then `map` doubles each element:

```java
List<Integer> ketQua = nhomSo.stream()
    .flatMap(List::stream)
    .map(n -> n * 2)
    .collect(Collectors.toList());

// [2, 4, 6, 8]
```

</details>

## 9. Takeaways

A pipeline is type-checked from left to right:

- `Stream<T>` indicates **the current element type**.
- `filter(Predicate<? super T>)` preserves `T` and requires an expression returning `boolean`.
- `map(Function<? super T, ? extends R>)` changes the element type to `R`.
- `flatMap` is used when each element needs to expand into a sub-stream and then be flattened.
- `collect` must produce a result compatible with **the receiving variable's type**.
- Method references require a target type; raw types, misused wildcards, and checked exceptions can all cause compile errors.

When facing a confusing error, write explicit types at transition points and inspect each lambda one by one. Doing so both fixes errors quickly and keeps pipelines readable and maintainable before moving on to advanced Stream API operations.
