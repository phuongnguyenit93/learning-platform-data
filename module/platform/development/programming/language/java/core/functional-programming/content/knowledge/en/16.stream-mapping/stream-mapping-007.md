# Combining Optional and Stream Without Calling get() Recklessly

In Java, `Optional<T>` expresses **a result that may be present or absent**, whereas `Stream<T>` represents **a pipeline for processing elements**. The two APIs combine very naturally when you need to transform data, search, filter, or skip non-existent results. The key approach is to **describe how presence/absence is handled using Optional and Stream operations**, rather than calling `get()` on an Optional without being certain a value exists.

For example, if a repository returns `Optional<User>` for each user ID, you can turn `Stream<Optional<User>>` into `Stream<User>` with `flatMap(Optional::stream)`. Unfound IDs automatically become **zero elements**, while found results become **one element**. That way, there is no need for `isPresent()` followed by `get()` on each item.

Key techniques in this article:

- `Optional.map`, `filter`, and `flatMap` to handle a value that may be missing.
- `Optional.stream()` (Java 9+) to convert an Optional into a Stream of **0 or 1 element**.
- `Stream.map(...)` combined with `Stream.flatMap(Optional::stream)` to drop absent results and continue the pipeline.
- `Stream.findFirst()`/`findAny()` returning an Optional; terminating with `ifPresent`, `orElse`, `orElseGet`, `or`, or `orElseThrow` according to the business contract.
- Handling null at data boundaries, avoiding nested Optionals, and avoiding unnecessary side effects.

The complete examples use **Java 17+**, with `javac`/`java` commands and deterministic stdout.

## 1. Why is calling get() recklessly dangerous?

An `Optional<T>` has two states: **holding a non-null value** or **empty**. `Optional.get()` returns the value when present, but **throws `NoSuchElementException` if the Optional is empty**.

This is an error-prone pattern:

```java
Optional<String> value = Optional.empty();
String text = value.get(); // throws NoSuchElementException
```

This is a **snippet that intentionally causes a runtime exception**, not a recommended approach.

Another pattern compiles, but easily leads to repetitive code:

```java
String display;
if (value.isPresent()) {
    display = value.get();
} else {
    display = "Không có";
}
```

This is an illustrative snippet, assuming `value` of type `Optional<String>` already exists. This style is not logically wrong within this simple scope, but it can be written more concisely and directly:

```java
String display = value.orElse("Không có");
```

**Not every call to `get()` is wrong.** When it has been proven for certain that the Optional has a value in a specific context, `get()` can be valid. However, when working with pipelines or APIs that may return empty, operations such as `map`, `flatMap`, `ifPresent`, and `orElseThrow` usually communicate intent better, avoiding manual checking and unwrapping at every step.

## 2. Distinguishing map, flatMap, and filter on Optional

Suppose:

```java
Optional<String> name = Optional.of("  Lan  ");
```

This snippet requires `import java.util.Optional;`.

### Optional.map: transform the value if present

```java
Optional<String> trimmed = name.map(String::strip);
// Optional containing "Lan"
```

`map` only invokes the transformation function when the Optional has a value. When the Optional is empty, the result remains empty. If the mapper returns `null`, `Optional.map` creates an empty Optional for that result; it does not create a present Optional containing null.

### Optional.filter: keep or discard based on a condition

```java
Optional<String> nonBlank = trimmed.filter(s -> !s.isEmpty());
// Contains "Lan" because "Lan" is not empty.
```

`filter` keeps the original Optional if the condition is true, and returns an empty Optional if false; for an Optional that is already empty, the predicate is not called.

### Optional.flatMap: avoid nested Optionals

When the transformation function already returns `Optional<R>`, use `flatMap` instead of `map` if you want an `Optional<R>` result:

```java
static Optional<Integer> parseInteger(String raw) {
    try {
        return Optional.of(Integer.parseInt(raw));
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
}
```

This is an **illustrative method snippet** that requires `import java.util.Optional;` and belongs to a class. When used:

```java
Optional<Optional<Integer>> nested =
        Optional.of("42").map(MyClass::parseInteger);
Optional<Integer> flat =
        Optional.of("42").flatMap(MyClass::parseInteger);
```

`MyClass` in the illustrative snippet is the name of the class containing `parseInteger`, which should be replaced with the actual class name. `map` wraps a result that is already an Optional inside another Optional layer; `flatMap` directly returns the Optional produced by the mapper. **Unlike `map`, the function passed to `Optional.flatMap` must not return null**: if the mapper returns null, Java throws `NullPointerException`.

## 3. Optional.stream(): a bridge of 0 or 1 element

Since Java 9, `Optional<T>` has the method `Stream<T> stream()`:

| Optional state | `optional.stream()` produces |
| --- | --- |
| `Optional.of("Java")` | A Stream with exactly one element `"Java"` |
| `Optional.empty()` | An empty Stream |
| `Optional.ofNullable(null)` | An empty Stream |

Thus, you do not need to check the Optional yourself and create `Stream.of(value)` or `Stream.empty()`.

```java
List<Optional<String>> maybeNames = List.of(
        Optional.of("Lan"),
        Optional.empty(),
        Optional.of("Mai")
);

List<String> names = maybeNames.stream()
        .flatMap(Optional::stream)
        .toList();
// [Lan, Mai]
```

This snippet requires `import java.util.List;` and `import java.util.Optional;`; `Stream.toList()` has been available since Java 16. `flatMap(Optional::stream)` converts each Optional into a 0/1-element Stream and then **flattens the sub-Streams** into a single output Stream.

Do not confuse this with:

```java
Stream<Stream<String>> nestedStreams =
        maybeNames.stream().map(Optional::stream);
```

When using `map`, each Optional element is converted into **a sub-Stream**, so the output type is `Stream<Stream<String>>`. When using `flatMap`, the elements of the sub-Streams are flattened into `Stream<String>`.

**Note:** `Optional.stream()` does not validate the business validity of the inner value; it only converts the present/empty state into 1/0 elements. If you want to remove blank or duplicate strings, continue with `filter`, `map`, and `distinct`.

## 4. Java 17 program: from a list of Optionals to a list of values

Save as **`OptionalStreamBasicsDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.Optional;

public class OptionalStreamBasicsDemo {
    public static void main(String[] args) {
        List<Optional<String>> values = List.of(
                Optional.of(" Java "),
                Optional.empty(),
                Optional.of("Kotlin"),
                Optional.of("Java"),
                Optional.of("   ")
        );

        List<String> cleaned = values.stream()
                .flatMap(Optional::stream)
                .map(String::strip)
                .filter(s -> !s.isBlank())
                .map(s -> s.toUpperCase(Locale.ROOT))
                .distinct()
                .toList();

        System.out.println("cleaned=" + cleaned);
        System.out.println("presentCount=" + values.stream()
                .flatMap(Optional::stream)
                .count());
        System.out.println("emptyAsStream="
                + Optional.<String>empty().stream().count());
        System.out.println("singleAsStream="
                + Optional.of("Java").stream().count());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 OptionalStreamBasicsDemo.java
java OptionalStreamBasicsDemo
```

**Exact stdout:**

```text
cleaned=[JAVA, KOTLIN]
presentCount=4
emptyAsStream=0
singleAsStream=1
```

Explanation:
1. The initial five Optionals consist of **four present Optionals** and one empty Optional. Therefore `presentCount` is 4, including the string containing only whitespace.
2. `flatMap(Optional::stream)` removes the empty Optional from the result stream without calling `get()`.
3. `strip`, `filter`, `toUpperCase`, and `distinct` produce two unique values `JAVA` and `KOTLIN` in the first-encountered order of the source List.
4. `Optional.empty().stream().count()` equals 0; a present Optional produces a Stream with exactly 1 element.

Because `List.of` does not allow null elements, the example uses **`Optional.empty()` as an element** instead of null. Avoid creating a `List<Optional<T>>` containing **null Optional references**: calling `Optional::stream` on a null reference will throw an exception.

## 5. Stream.map(repository::find) followed by flatMap(Optional::stream)

A real-world scenario: for each ID, the repository returns `Optional<User>`; not every ID exists.

Pipeline pattern:

```java
List<User> users = ids.stream()
        .map(repository::findById)   // Stream<Optional<User>>
        .flatMap(Optional::stream)   // Stream<User>
        .toList();
```

This is an illustrative snippet: `ids`, `repository`, and `User` need to be declared in the application; `repository.findById` must have the return type `Optional<User>`.

At each step:
- `ids.stream()` emits the IDs.
- `map(repository::findById)` calls the repository for each ID, producing an Optional each time.
- `flatMap(Optional::stream)` **skips** empty Optionals and **keeps** the found Users.
- `toList()` creates the result list. If the Stream has an encounter order (for example, a List source), the result preserves the encounter order of the present Users.

Do not write:

```java
// INTENTIONALLY WRONG: a missing ID will cause NoSuchElementException.
List<User> users = ids.stream()
        .map(repository::findById)
        .map(Optional::get)
        .toList();
```

Besides being error-prone, the snippet above also mixes the responsibilities of "a lookup that may fail" and "unwrapping data guaranteed to exist" in the pipeline. When you need to **fail immediately** if an ID does not exist, you can use `orElseThrow` with a message identifying the ID; when you want to **skip non-existent IDs**, `flatMap(Optional::stream)` is more appropriate.

## 6. Java 17 program: repository returning Optional and Stream filtering data

Create the file **`OptionalStreamRepositoryDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.Optional;

public class OptionalStreamRepositoryDemo {
    record User(String id, String name, boolean active) {}

    private static final Map<String, User> USERS = Map.of(
            "u1", new User("u1", "Lan", true),
            "u2", new User("u2", "Minh", false),
            "u3", new User("u3", "Mai", true)
    );

    static Optional<User> findById(String id) {
        return Optional.ofNullable(USERS.get(id));
    }

    public static void main(String[] args) {
        List<String> ids = List.of("u1", "missing", "u2", "u3", "u1");

        List<String> activeNames = ids.stream()
                .map(OptionalStreamRepositoryDemo::findById)
                .flatMap(Optional::stream)
                .filter(User::active)
                .map(User::name)
                .distinct()
                .toList();

        long foundCount = ids.stream()
                .map(OptionalStreamRepositoryDemo::findById)
                .flatMap(Optional::stream)
                .count();

        String firstFoundName = ids.stream()
                .map(OptionalStreamRepositoryDemo::findById)
                .flatMap(Optional::stream)
                .map(User::name)
                .findFirst()
                .orElse("Không có");

        String missingName = findById("missing")
                .map(User::name)
                .orElse("Khách");

        System.out.println("activeNames=" + activeNames);
        System.out.println("foundCount=" + foundCount);
        System.out.println("firstFound=" + firstFoundName);
        System.out.println("missingName=" + missingName);
    }
}
```

Compile/run with JDK 17+:

```bash
javac -encoding UTF-8 OptionalStreamRepositoryDemo.java
java OptionalStreamRepositoryDemo
```

**Exact stdout:**

```text
activeNames=[Lan, Mai]
foundCount=4
firstFound=Lan
missingName=Khách
```

Explanation:
1. `Map.get` may return null when an ID does not exist; `Optional.ofNullable` turns that result into an empty Optional.
2. The `ids` source has five items. The ID `"missing"` is not found, while `"u1"` appears twice; the total number of found items is **4**.
3. Filtering by `active` removes User `"Minh"`; `distinct` after `map(User::name)` removes the duplicate `"Lan"` name, so the result is `[Lan, Mai]`.
4. `findFirst()` returns an Optional based on the first result of the ordered Stream; `orElse("Không có")` guarantees a String is always returned even if there are no Users.
5. For a single Optional, `findById("missing").map(User::name).orElse("Khách")` is simpler than creating an entire Stream.

**Choose the semantics clearly:** `flatMap(Optional::stream)` **skips** missing results. If a missing ID is a data error that must be reported, you should not silently ignore it; use a result API with error details or `orElseThrow` according to business requirements.

## 7. findFirst, findAny, and the Optional-returning workflow

The terminal operations `findFirst()` and `findAny()` return `Optional<T>`. This reminds the caller that the source may be empty or no matching value may be found.

```java
Optional<String> first = List.of("Java", "Kotlin")
        .stream()
        .filter(s -> s.startsWith("K"))
        .findFirst();
```

This illustrative snippet requires `import java.util.List;` and `import java.util.Optional;`. In the example, `first` contains `"Kotlin"`. If you change the condition to `startsWith("Z")`, the result is empty.

You can terminate according to your needs:

```java
first.ifPresent(System.out::println);
String display = first.orElse("Không tìm thấy");
String strict = first.orElseThrow(
        () -> new IllegalStateException("Yêu cầu có kết quả"));
```

These snippets assume `first` has a value as in the previous example; therefore `ifPresent` prints `Kotlin`, and `display` and `strict` receive `"Kotlin"`. When the Optional is empty, `ifPresent` performs no action, `orElse` returns the fallback, and `orElseThrow` throws the exception created by the supplier.

On a Stream with an encounter order, `findFirst()` must respect the encounter order; `findAny()` may return any matching element, which is especially useful when running in parallel and **the first element is not required**.

**Watch out for null:** `findFirst()`/`findAny()` can throw `NullPointerException` if the selected element is null, because Optional cannot hold a null value. If the Stream might contain null, filter with `filter(Objects::nonNull)` before using Optional-returning terminal operations.

## 8. How Optional.map and flatMap differ from Stream.map and flatMap

| API | Input target | Function passed in | Result |
| --- | --- | --- | --- |
| `Optional<T>.map(f)` | Optional with 0/1 value | `T -> R` | `Optional<R>` |
| `Optional<T>.flatMap(f)` | Optional with 0/1 value | `T -> Optional<R>` | `Optional<R>` |
| `Stream<T>.map(f)` | Stream with 0..n elements | `T -> R` | `Stream<R>` |
| `Stream<T>.flatMap(f)` | Stream with 0..n elements | `T -> Stream<R>` | `Stream<R>` |
| `Optional<T>.stream()` | Optional with 0/1 value | No function argument | `Stream<T>` containing 0/1 element |

`flatMap` in Optional and Stream shares the general idea of "flattening the container layer returned by the mapper", but **the container types are different**. Some typical valid pairs:

```java
Optional<String> normalized =
        Optional.of(" java ").map(String::strip);

Stream<String> found =
        Stream.of(Optional.of("A"), Optional.empty())
                .flatMap(Optional::stream);
```

These are illustrative snippets requiring `Optional` and `Stream` imports. In `Optional.flatMap`, the mapper must return a non-null Optional; in `Stream.flatMap`, the mapper must return a Stream (per the API contract; for a null result, Stream treats it as an empty Stream). Avoid mixing them up as if they were the same kind of function.

### When you need to return multiple values from an Optional

`Optional.stream()` only has **0 or 1 value**. If an inner value can expand into multiple values, convert it into a Stream and use `Stream.flatMap` accordingly:

```java
List<String> words = Optional.of("Java Kotlin")
        .stream()
        .flatMap(s -> java.util.Arrays.stream(s.split(" ")))
        .toList();
// [Java, Kotlin]
```

The example above uses `Optional.stream()` to start with 0/1 string, then `Stream.flatMap` flattens the split list of words. If the Optional is empty, the pipeline naturally produces an empty list.

## 9. Do not use get() when handling nullable data: Optional.ofNullable and Stream.ofNullable

When the input is a **nullable `T` reference**, rather than an `Optional<T>`, there are two ways to create a 0/1-element Stream in Java 9+:

```java
Stream<String> a = Optional.ofNullable(value).stream();
Stream<String> b = Stream.ofNullable(value);
```

This is an illustrative snippet with `value` of type `String` and imports for `Optional` and `Stream`. Both create an empty Stream if `value == null`, or a single-element Stream if non-null.

- Use **`Optional.ofNullable(value)`** when you want to represent absence in an API or have further Optional processing steps.
- Use **`Stream.ofNullable(value)`** when you only want to feed a nullable value into a Stream without creating an Optional as an intermediate data representation.

Example of cleaning a nullable string:

```java
List<String> cleaned = Stream.ofNullable(raw)
        .map(String::strip)
        .filter(s -> !s.isBlank())
        .toList();
```

With `raw == null`, the result is an empty list; because there are no elements, `String::strip` does not run and therefore does not throw `NullPointerException`. With `raw = " Java "`, the result is `[Java]`. With `raw = "   "`, the result is empty due to `filter`.

**Be careful when using `Stream.of(value)`:** with a nullable reference variable, `Stream.of(value)` can create a Stream containing one **null element** instead of an empty Stream. In that case, `map(String::strip)` will throw an error. `Stream.ofNullable` is more appropriate if the intent is to drop null.

## 10. Avoiding nested Optionals when chaining multiple steps

Suppose a function returns an Optional because parsing may fail:

```java
static Optional<Integer> parsePositive(String raw) {
    try {
        int number = Integer.parseInt(raw);
        return number > 0 ? Optional.of(number) : Optional.empty();
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
}
```

This is an illustrative method that requires `import java.util.Optional;`.

If you write:

```java
Optional<Optional<Integer>> nested =
        Optional.of("12").map(MyClass::parsePositive);
```

you create an **Optional nested inside an Optional**. Here `MyClass` is the name of the class containing `parsePositive`; replace it with the actual class name. To get `Optional<Integer>` as the result, use:

```java
Optional<Integer> number =
        Optional.of("12").flatMap(MyClass::parsePositive);
```

For multiple strings in a Stream:

```java
List<Integer> numbers = List.of("12", "bad", "-2", "5")
        .stream()
        .map(MyClass::parsePositive)
        .flatMap(Optional::stream)
        .toList();
// [12, 5]
```

These are three **illustrative snippets**, not standalone files; just choose the right class name containing `parsePositive`.

- `Optional.flatMap` fits **a single input Optional** and a function returning Optional.
- `Stream.map(...).flatMap(Optional::stream)` fits **multiple elements** and a function returning Optional.
- `Stream.filter(Optional::isPresent).map(Optional::get)` can work when coded carefully and without null Optionals; however, `flatMap(Optional::stream)` is shorter, avoids manual Optional unwrapping, and clearly expresses the intent to discard empty values.

## 11. Java 17 program: parsing potentially invalid data without calling get

Save as **`OptionalParsePipelineDemo.java`**:

```java
import java.util.List;
import java.util.Optional;

public class OptionalParsePipelineDemo {
    static Optional<Integer> parsePositive(String raw) {
        if (raw == null) {
            return Optional.empty();
        }

        try {
            int number = Integer.parseInt(raw.strip());
            return number > 0
                    ? Optional.of(number)
                    : Optional.empty();
        } catch (NumberFormatException ex) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        List<String> input = List.of("12", "bad", "-2", "5", "20", " 7 ");

        List<Integer> parsed = input.stream()
                .map(OptionalParsePipelineDemo::parsePositive)
                .flatMap(Optional::stream)
                .toList();

        List<Integer> evens = input.stream()
                .map(OptionalParsePipelineDemo::parsePositive)
                .flatMap(Optional::stream)
                .filter(value -> value % 2 == 0)
                .toList();

        Optional<Optional<Integer>> nested =
                Optional.of("12").map(OptionalParsePipelineDemo::parsePositive);

        Optional<Integer> flattened =
                Optional.of("12").flatMap(OptionalParsePipelineDemo::parsePositive);

        System.out.println("parsed=" + parsed);
        System.out.println("evens=" + evens);
        System.out.println("nestedPresent=" + nested.isPresent());
        System.out.println("flattened=" + flattened.orElse(-1));
        System.out.println("invalid="
                + parsePositive("bad").orElse(-1));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 OptionalParsePipelineDemo.java
java OptionalParsePipelineDemo
```

**Exact stdout:**

```text
parsed=[12, 5, 20, 7]
evens=[12, 20]
nestedPresent=true
flattened=12
invalid=-1
```

In the `input` list, `"bad"` does not parse into a number and `"-2"` does not satisfy the positive rule, so both become empty Optionals. `" 7 "` is stripped and parsed into `7`. The string `"12"` succeeds; `map` creates a nested Optional, whereas `flatMap` flattens it as desired.

**Scope of the illustration:** the `parsePositive` method treats both "not a number" and "non-positive number" as absence. In an application that needs detailed error messages, a result type carrying the failure reason is usually better than erasing all causes with `Optional.empty()`.

## 12. Terminating Optional with orElse, orElseGet, or, and orElseThrow

Once you have an `Optional<T>`, you have several ways to handle it instead of `get()`:

| Method | When Optional has a value | When Optional is empty |
| --- | --- | --- |
| `ifPresent(action)` | Runs action with the value | Does not perform action |
| `ifPresentOrElse(action, emptyAction)` | Runs action | Runs emptyAction |
| `orElse(value)` | Returns the inner value | Returns the provided fallback |
| `orElseGet(supplier)` | Returns the inner value | Calls supplier and returns its result |
| `or(supplierOfOptional)` | Keeps the existing Optional | Calls supplier and takes the fallback Optional |
| `orElseThrow()` | Returns the inner value | Throws `NoSuchElementException` |
| `orElseThrow(exceptionSupplier)` | Returns the inner value | Throws the exception created by supplier |
| `stream()` | Creates a single-element Stream | Creates an empty Stream |

**Distinguishing fallback evaluation:** the argument expression `orElse(fallback())` is evaluated before calling the method, even when the Optional has a value. `orElseGet(() -> fallback())` only calls fallback when the Optional is empty. `or` (Java 9+) returns an **Optional**, not a raw value; the supplier for `or` must return a **non-null** Optional.

Use `orElseThrow` when **absence is an error that must be reported clearly**. That is a deliberate way to enforce a required condition, unlike `get()` which lacks checks or a custom message.

## 13. Java 17 program: controlled fallback

Create the file **`OptionalFallbackDemo.java`**:

```java
import java.util.Optional;

public class OptionalFallbackDemo {
    static String fallback() {
        System.out.println("Tính fallback");
        return "guest";
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("Lan");

        System.out.println("orElse=" + present.orElse(fallback()));
        System.out.println("orElseGet="
                + present.orElseGet(OptionalFallbackDemo::fallback));

        Optional<String> missing = Optional.empty();
        System.out.println("missing="
                + missing.orElseGet(OptionalFallbackDemo::fallback));

        Optional<String> recovered = Optional.<String>empty()
                .or(() -> Optional.of("backup"));
        System.out.println("recovered=" + recovered.orElse("none"));

        try {
            Optional.<String>empty()
                    .orElseThrow(() -> new IllegalArgumentException("missing"));
        } catch (IllegalArgumentException ex) {
            System.out.println("error=" + ex.getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 OptionalFallbackDemo.java
java OptionalFallbackDemo
```

**Exact stdout:**

```text
Tính fallback
orElse=Lan
orElseGet=Lan
Tính fallback
missing=guest
recovered=backup
error=missing
```

The first time, `fallback()` runs immediately because it is the argument to `orElse`. `orElseGet` on the Optional containing `"Lan"` does **not** call the supplier. For the empty Optional, the supplier is called to return `"guest"`. `or` uses a fallback Optional, and `orElseThrow` reports an error intentionally.

If an expensive fallback is not needed, `orElse("Khách")` is clear and reasonable. It is not necessary to replace every `orElse` call with `orElseGet`.

## 14. Notes on null, null Optionals, and errors in pipelines

**Optional cannot contain null**, yet a variable of type `Optional<T>` can still be assigned a `null` reference. When using:

```java
List<Optional<String>> values = List.of(
        Optional.of("A"),
        Optional.empty()
);
```

you have a list that contains no null Optional references. If a source from a legacy API might pass in `null` instead of `Optional.empty()`, then `flatMap(Optional::stream)` will throw `NullPointerException` when it encounters a null element. Normalize the data or fix the source API so it does not return null instead of an empty Optional.

**Do not confuse an empty Optional with an exception.** An unfound Optional is an expected state if the business contract allows it; a failed parse or a query with a system error may require a full error report. If you catch every exception and return `Optional.empty()`, you may hide real failures.

**Map is not equivalent to flatMap:** `Optional.map` wraps a non-null result in an Optional; `Optional.flatMap` requires the mapper to return a non-null Optional. `Stream.flatMap(Optional::stream)` applies directly only to a Stream **of Optionals**, not a Stream of regular objects.

**Avoid mutating the source inside lambdas:** with Stream, prefer stateless and non-interfering functions. Mapping an ID to a repository with I/O may require error handling, timeouts, and performance management; using Stream does not automatically provide asynchronous processing or retry mechanisms.

## 15. Ordering, performance, and parallel processing

For a `List` with an encounter order, the pipeline:

```java
List<String> results = ids.stream()
        .map(repository::findById)
        .flatMap(Optional::stream)
        .map(User::name)
        .toList();
```

preserves the order of present results according to the source IDs (assuming no step breaks the encounter order). This is an **illustrative snippet** with `ids`, `repository`, and `User` declared in the application.

With `parallelStream()`, mapper calls may execute on multiple threads, yet `toList()` on a Stream with an encounter order still preserves the result order. That **does not guarantee the repository is thread-safe**, does not guarantee the order of external data calls, and does not automatically make I/O faster. Avoid putting a non-thread-safe client or shared mutable state into a parallel pipeline.

If the list is large and most Optionals are empty, `flatMap(Optional::stream)` produces the right result in terms of dropping absences, but it is not a guarantee of optimal performance for every workload. Measure in a realistic context rather than assuming these operators are always faster than a loop.

## 16. Quick decision patterns

| Need | Pattern to use |
| --- | --- |
| Have one Optional, want to transform the value if present | `optional.map(f)` |
| Have one Optional, processing function returns Optional | `optional.flatMap(f)` |
| Have one Optional, want to filter by a condition | `optional.filter(p)` |
| Have many Optionals, want to drop empty Optionals | `optionals.stream().flatMap(Optional::stream)` |
| Each item may look up an Optional from a repository | `ids.stream().map(repo::find).flatMap(Optional::stream)` |
| Stream may have no elements, want first value or default | `stream.findFirst().orElse(defaultValue)` |
| Absence is a business error | `optional.orElseThrow(() -> new ...)` |
| Fallback needs lazy evaluation | `optional.orElseGet(() -> createFallback())` |
| Want a fallback Optional | `optional.or(() -> otherOptional())` |
| Have a nullable value to put into a Stream | `Stream.ofNullable(value)` |

The names `f`, `p`, `repo`, `otherOptional`, and `createFallback` are **illustrative placeholders** that need to be declared appropriately in actual code. The goal is to choose the operator that accurately expresses intent, rather than forcing every problem into a long, hard-to-read pipeline.

## 17. Common mistakes and exercises

Common mistakes:

1. **Calling `get()` right after `findFirst()`** without handling an empty Stream.
2. **Calling `map(Optional::get)`** on a Stream containing empty Optionals.
3. **Using `map(Optional::stream)` and forgetting to flatten**, creating a Stream of Streams.
4. **Using `Optional.map` when the function returns Optional**, creating an unnecessary `Optional<Optional<R>>`.
5. **Assuming `Optional.stream` can return many elements**; it only produces 0 or 1 element.
6. **Using `orElse(expensiveFallback())` and believing the fallback only runs when empty**.
7. **Assuming `orElseGet` returns an Optional**; it actually returns a value `T`; `or` is what returns an Optional.
8. **Assuming `Stream.of(null)` is equivalent to `Stream.ofNullable(null)`**; one can contain a null element, while the other returns an empty Stream.
9. **Assuming an empty repository Optional means a system error**; it may simply mean not found, depending on the contract.
10. **Ignoring business errors with `flatMap(Optional::stream)`** when all IDs are required to exist.
11. **Using a parallel stream with a non-thread-safe repository** or relying on side-effect ordering.
12. **Assuming `List<Optional<T>>` is mandatory**; sometimes an API returning `Stream<T>` or a richer result set is more suitable.

**Question 1.** What does `Optional.empty().stream().count()` equal?

**Answer:** `0`.

**Question 2.** What does `List.of(Optional.of("A"), Optional.empty(), Optional.of("B")).stream().flatMap(Optional::stream).toList()` produce?

**Answer:** `[A, B]`; the empty Optional produces no element.

**Question 3.** When `findById` returns `Optional<User>`, should you use `map(Optional::get)` or `flatMap(Optional::stream)` if the goal is to skip non-existent IDs?

**Answer:** `flatMap(Optional::stream)`, because it turns an empty Optional into an empty Stream instead of throwing an exception via `get()`.

**Question 4.** If absence is a mandatory error that must be known, should you use `flatMap(Optional::stream)`?

You should not silently ignore it. You can use `orElseThrow` with a message containing the ID or a result type that represents failure.

**Question 5.** Given `Optional.of("12")` and `parsePositive(String)` returning `Optional<Integer>`, should you use `map` or `flatMap` to receive `Optional<Integer>`?

**Answer:** `flatMap`, because `map` will create a nested Optional.

**Question 6.** What does `Stream.ofNullable(null).count()` equal?

**Answer:** `0`; no null element is put into the Stream.

**Question 7.** How does `orElse` differ from `orElseGet` when the fallback has a side effect?

`orElse(f())` evaluates `f()` before being called, even if the Optional has a value. `orElseGet(() -> f())` only calls `f()` if the Optional is empty.

**Question 8.** Why can `findFirst()` still throw `NullPointerException` even though it returns an Optional?

Because Optional cannot hold null; if the Stream contains null and the selected element is null, the terminal operation cannot create a valid present Optional. Filter out null before using the terminal operation.

**Takeaway:** For **a single Optional**, use `map`/`filter`/`flatMap` and terminate with `orElse`, `orElseGet`, `or`, or `orElseThrow` according to business semantics. For **a Stream of Optionals**, use **`flatMap(Optional::stream)`** to turn "present or absent" into "one or zero elements", avoiding reckless calls to `get()`.
