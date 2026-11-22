# Collectors.joining(): Joining Strings with a Delimiter in Java Stream

## 1. Lesson Objectives

When a Stream contains multiple strings, we often want to collect all elements into **a single result string**: a comma-separated list of names, a slash-joined path, or display content enclosed in square brackets. Java provides the `java.util.stream.Collectors.joining(...)` collector for this need.

Example:

```text
Stream:  "Lan"  "Minh"  "An"
                    |
         joining(", ")
                    v
String:  "Lan, Minh, An"
```

Key takeaways:

- `joining()` concatenates consecutive elements without inserting a delimiter.
- `joining(delimiter)` inserts the delimiter **between** elements, without automatically adding it at the beginning or end.
- `joining(delimiter, prefix, suffix)` adds an opening prefix and closing suffix around the joined string.
- `joining` is a **collector** used in the `collect(...)` terminal operation; it is not a `map` transformation and does not modify the source.
- Elements passed to `joining` must have a type compatible with `CharSequence`, such as `String`. For a Stream of numbers or business objects, you need to convert each element to a string first.
- The resulting order depends on the stream's **encounter order**; if business logic requires a deterministic order, you need to establish an explicit order before joining.

This lesson belongs to the **collecting results** section of Java functional programming: instead of manually declaring a string variable and concatenating in a loop, we express the join operation using a collector with a clear contract.

## 2. Three Main Overloads and Their Meanings

The conceptual API signatures:

```java
Collectors.joining()
Collectors.joining(CharSequence delimiter)
Collectors.joining(
        CharSequence delimiter,
        CharSequence prefix,
        CharSequence suffix)
```

These are **API call descriptions**, not user-defined methods in a Java program. All three create a collector that accepts `CharSequence` elements and produces a `String` value.

With the data `["A", "B", "C"]`:

| Collector | Result | Meaning |
| --- | --- | --- |
| `joining()` | `"ABC"` | Direct concatenation |
| `joining(",")` | `"A,B,C"` | Comma between elements |
| `joining(", ")` | `"A, B, C"` | Comma and space |
| `joining(" / ")` | `"A / B / C"` | Custom delimiter |
| `joining(", ", "[", "]")` | `"[A, B, C]"` | Adds prefix and suffix |
| `joining(" - ", "<", ">")` | `"<A - B - C>"` | Arbitrary surrounding format |

The delimiter is not added to the end of the string. For example, three elements will have exactly two `", "` insertions; one element will have no delimiter at all.

Unlike `Stream<String>.toList()`, the result after `collect(joining(...))` is **a single `String`**, not a list containing individual elements. The resulting String is immutable by Java's contract.

## 3. Standalone Java 17+ Example: All Overloads, Single Element, and Empty Stream

Create the file `JoiningBasicsDemo.java`:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class JoiningBasicsDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Minh", "An");

        System.out.println("plain=" +
                names.stream().collect(Collectors.joining()));

        System.out.println("comma=" +
                names.stream().collect(Collectors.joining(", ")));

        System.out.println("bracket=" +
                names.stream()
                        .collect(Collectors.joining(" | ", "[", "]")));

        System.out.println("one=" +
                Stream.of("Lan")
                        .collect(Collectors.joining(", ", "[", "]")));

        System.out.println("empty=" +
                Stream.<String>empty()
                        .collect(Collectors.joining(", ")));

        System.out.println("empty framed=" +
                Stream.<String>empty()
                        .collect(Collectors.joining(", ", "[", "]")));
    }
}
```

Compile/run on JDK 17+:

```bash
javac JoiningBasicsDemo.java
java JoiningBasicsDemo
```

Expected output:

```text
plain=LanMinhAn
comma=Lan, Minh, An
bracket=[Lan | Minh | An]
one=[Lan]
empty=
empty framed=[]
```

Explanation:

1. `names.stream()` creates a Stream whose encounter order matches the order in the `List`.
2. Each `collect(Collectors.joining(...))` call collects the elements into a single string. Each time here creates a **new stream** from `names`, without reusing a consumed stream.
3. `joining(", ")` does not automatically place a comma at the start or end.
4. With **a single element**, `joining(", ", "[", "]")` still returns `"[Lan]"`; the delimiter does not appear because there is no pair of elements to separate.
5. With **an empty stream**, `joining(", ")` returns an empty string `""`. When a prefix/suffix is present, the returned string contains only the prefix and suffix, which here is `"[]"`.
6. The `Stream.<String>empty()` method uses the `<String>` type witness to explicitly show the element type; in many contexts the compiler can infer the type automatically.

**Commonly overlooked point:** `joining(",", "[", "]")` on an empty stream does **not** return an empty string; it returns `"[]"`, which is very convenient when you want to display an explicit frame.

## 4. `joining` Is a Terminal Collection, Not an Intermediate Operation

Stream operations are generally divided into:

- **Intermediate:** `map`, `filter`, `distinct`, `sorted`, ... create a new pipeline and are usually lazily evaluated.
- **Terminal:** `collect`, `count`, `toList`, ... trigger pipeline processing to produce a result or side effect according to the contract.

Therefore:

```java
String joined = names.stream()
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase)
        .collect(Collectors.joining(", "));
```

This is a code snippet inside a method, assuming `names` is `List<String>` and `Collectors` is imported. The steps are:

```text
Source List<String>
    └─ stream()             Stream<String>
       └─ filter(...)       Stream<String>
          └─ map(...)       Stream<String>
             └─ collect(joining(", ")) -> String
```

The collector performs the joining **after** the elements have passed through the filtering and transformation operations and are emitted to the collector. If an object needs to be displayed in a specific format, converting it to a string should be done before the collector.

Note: a `Stream` object **can only be used for a single consuming pipeline**; you cannot take the same `Stream` and call `collect(joining())` twice. With a source collection, call `names.stream()` each time to create a new stream.

## 5. Non-String Data: Convert to CharSequence Before Joining

`Collectors.joining(...)` accepts elements of type `CharSequence` (usually `String`). Therefore, you cannot directly join a `Stream<Integer>` or `Stream<Product>` without converting them according to the intended display format.

Wrong type:

```java
// Counter-example intentionally DOES NOT compile if numbers is Stream<Integer>:
String text = numbers.collect(Collectors.joining(", "));
```

To fix it, add `map` to produce a String:

```java
String text = numbers
        .map(n -> Integer.toString(n))
        .collect(Collectors.joining(", "));
```

The two snippets above are **examples in the context where the `numbers` variable has type `Stream<Integer>`**, not standalone programs. For a primitive `IntStream`, the `mapToObj(...)` method converts it into an object stream:

```java
String numbersText = java.util.stream.IntStream.of(3, 1, 4)
        .mapToObj(Integer::toString)
        .collect(Collectors.joining(" - "));
```

The result is `"3 - 1 - 4"`. This is a code snippet inside a method where `Collectors` is imported. `IntStream.map(...)` only returns an `IntStream`, it does not convert numbers to Strings; `mapToObj(...)` is required when you want to use a string-joining collector.

### Complete Program: Joining Data After Filtering, Sorting, and Transforming

Save `JoiningPipelineDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class JoiningPipelineDemo {
    record Employee(String name, String team, boolean active) {}

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee("Lan", "Dev", true),
                new Employee("Minh", "Ops", false),
                new Employee("An", "Dev", true),
                new Employee("Lan", "Ops", true),
                new Employee("Hoa", "Dev", true)
        );

        String activeNames = employees.stream()
                .filter(Employee::active)
                .map(Employee::name)
                .distinct()
                .sorted()
                .collect(Collectors.joining(" | "));

        Map<String, String> namesByTeam = employees.stream()
                .filter(Employee::active)
                .collect(Collectors.groupingBy(
                        Employee::team,
                        TreeMap::new,
                        Collectors.mapping(
                                Employee::name,
                                Collectors.joining(" / ")
                        )
                ));

        System.out.println("active=" + activeNames);
        System.out.println("Dev=" + namesByTeam.get("Dev"));
        System.out.println("Ops=" + namesByTeam.get("Ops"));
    }
}
```

Run:

```bash
javac JoiningPipelineDemo.java
java JoiningPipelineDemo
```

Output:

```text
active=An | Hoa | Lan
Dev=Lan / An / Hoa
Ops=Lan
```

Analysis:

- `filter(Employee::active)` keeps only active employees.
- `map(Employee::name)` converts `Stream<Employee>` to `Stream<String>`, which is a valid type for `joining`.
- `distinct()` removes duplicate names according to `equals`; `sorted()` ensures alphabetical order of Strings before joining.
- `groupingBy(...)` groups records by team; `Collectors.mapping(Employee::name, joining(" / "))` is a **downstream collector** that converts each Employee to a String and then joins the names within each group.
- `TreeMap::new` specifies a Map ordered by key if you need to iterate by team, though the example prints the two keys individually so it does not depend on how the Map is rendered. With an ordered `List` source and the collector here, the names within each group preserve their encounter order.
- If you only need a single string of all employees, `groupingBy` is not needed; the `joining` collector is sufficient.

**Key mindset:** the data type flowing through each stage determines where you place `map`. Before `map(Employee::name)` it is `Employee`, after it is `String`; the joining collector receives strings and does not automatically know which property to extract from Employee.

## 6. Delimiter, Prefix, and Suffix Must Be in the Right Positions

With the code:

```java
String result = Stream.of("red", "green", "blue")
        .collect(Collectors.joining(", ", "[", "]"));
```

the result is:

```text
[red, green, blue]
```

Character positions:

```text
prefix       delimiter   delimiter      suffix
  [    red      ,      green     ,      blue    ]
```

There is no delimiter at the start, nor is there a delimiter right before the suffix. Therefore, there is no need to manually handle "omit the comma if it is the last element".

Each parameter is a `CharSequence`:

- `delimiter`: the separator placed between **elements**; it can be a comma, space, newline, or a multi-character string.
- `prefix`: the string placed before the joined content.
- `suffix`: the string placed after the joined content.

Example:

```java
String lines = Stream.of("first", "second")
        .collect(Collectors.joining("\n", "START\n", "\nEND"));
```

The actual result contains newlines:

```text
START
first
second
END
```

This is an illustrative snippet placed inside a method where `Stream` and `Collectors` are imported. `\n` is a newline character; when printed to the console, the system may display it as separate lines. If you need an OS-specific line separator, consider `System.lineSeparator()`; for a file format that requires a fixed newline, use the exact character required by that format.

Note: `joining` **does not automatically escape** delimiters inside the data. If a name is `"a,b"` and the delimiter is a comma, it keeps the comma inside the name as-is. To export CSV, SQL, JSON, or machine-readable formats, you must apply the proper **escaping/quoting** rules of that format, and not treat `joining(",")` as a complete CSV/JSON generator.

## 7. Empty Stream: No Elements, Yet Still Produces a Result

Three different cases:

| Source | Collector | Result |
| --- | --- | --- |
| Empty | `joining()` | `""` |
| Empty | `joining(";")` | `""` |
| Empty | `joining(";", "(", ")")` | `"()"` |
| Contains one empty string `""` | `joining(";")` | `""` |
| Contains two empty strings `"", ""` | `joining(";")` | `";"` |
| Contains one element `"A"` | `joining(";")` | `"A"` |

In particular, **an empty result string does not necessarily prove that the stream had no elements**. A stream with exactly one element that is an empty string also produces `""` when there is no prefix/suffix. If you must distinguish between these states, you need to retain the element count in another structure rather than just looking at the joined String.

In real-world APIs, you can handle the case of no records according to the display contract, such as returning `"No data"` when the input is empty. However, `joining` itself does not add that fallback label; you need to design a post-collect processing step or choose a different format.

## 8. Null Values: Do Not Assume They Are Automatically Skipped

With a stream containing null, `joining` **does not automatically skip that element**. With an implementation following the contract of `StringJoiner`, a null value may be represented as the literal `"null"` when joined. If business logic does not want this text to appear, **define an explicit null policy**: filter out, replace with a label, or reject the data.

Factories like `List.of(...)` do not accept null elements. To demonstrate nullable data, use a list that allows null.

Create the file `JoiningNullDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class JoiningNullDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>();
        values.add("A");
        values.add(null);
        values.add("B");

        String raw = values.stream()
                .collect(Collectors.joining(", "));

        String skipNull = values.stream()
                .filter(Objects::nonNull)
                .collect(Collectors.joining(", "));

        String placeholder = values.stream()
                .map(value -> value == null ? "(missing)" : value)
                .collect(Collectors.joining(" | "));

        System.out.println("raw=" + raw);
        System.out.println("skip=" + skipNull);
        System.out.println("placeholder=" + placeholder);
    }
}
```

Run:

```bash
javac JoiningNullDemo.java
java JoiningNullDemo
```

Output:

```text
raw=A, null, B
skip=A, B
placeholder=A | (missing) | B
```

The approaches above carry different business meanings:

1. **Keep as-is:** the word `null` is included in the joined string. For many systems, this causes confusion because a null value cannot be distinguished from a real string whose content is `"null"`.
2. **Filter out:** `filter(Objects::nonNull)` completely removes null elements. Reasonable when null simply means "no name".
3. **Replace:** `map(...)` turns null into a specific placeholder. Reasonable when you need to preserve input positions or produce a clear message.
4. **Reject:** if null is invalid data, validate and throw an appropriate exception before producing the result, rather than silently filtering it out.

You must distinguish between a **null element** and a **null delimiter/prefix/suffix parameter**. The overloads of `Collectors.joining` require valid configuration parameters and may throw a `NullPointerException` when passed null; do not pass null as a delimiter expecting Java to treat it as an empty string. If no delimiter is needed, use `joining()` or `joining("")`.

## 9. Element Order Directly Affects the Result String

`Collectors.joining(", ")` does not sort elements on its own. If the source is a `List` with an encounter order, the string follows that order:

```java
String first = List.of("Z", "A", "M").stream()
        .collect(Collectors.joining(", "));

String second = List.of("Z", "A", "M").stream()
        .sorted()
        .collect(Collectors.joining(", "));
```

These are two declaration snippets inside a method with `List` and `Collectors` imported. Result:

```text
first  = Z, A, M
second = A, M, Z
```

With a source that **has no encounter order** or when `unordered()` is explicitly called, you should not rely on a fixed joining order. In particular, sources like `HashSet` do not provide a stable traversal order for business logic. If a display string with a deterministic order is required, call `sorted()` with an appropriate comparator before collecting.

With an **ordered stream**, the `joining` collector preserves the encounter order of elements in the result, even when the pipeline may execute in parallel. However, do not infer from the final string that side effects such as `peek(System.out::println)` are guaranteed to occur in that order in a parallel stream. To debug, inspect the output result rather than using log order as the source of truth.

Another point: `distinct()` works according to equality rules; `sorted()` can change the order before joining; `filter()` can reduce the number of delimiters because elements are removed. When changing the position of stages, you need to know what **final data** will reach the collector.

## 10. Combining `joining` with Other Collectors

### 10.1. `mapping(..., joining(...))` When Grouping

When grouping by a key:

```java
Map<String, String> byTeam = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::team,
                Collectors.mapping(
                        Employee::name,
                        Collectors.joining(", ")
                )
        ));
```

This illustrative snippet assumes an `Employee` type with `team()` and `name()`, a collection `employees`, and imports for `Map` and `Collectors`. The name strings are joined **within each group**. This is a form of downstream collector: `groupingBy` partitions into groups and `mapping` transforms the element type before `joining` produces each group's result.

Note that the order of the Map **keys** is determined by the Map type and Map supplier; `groupingBy` itself does not promise to return a Map with a special key order. If you want keys sorted in order, choose a supplier such as `TreeMap::new`; if you need to preserve the encounter order of names within a group, also check the source and upstream operations.

### 10.2. `filtering(..., joining(...))` as a Downstream Collector

Since Java 9, `Collectors.filtering(predicate, downstream)` can filter elements **inside the collector**, for example when you need to keep a group even if no elements match the filter:

```java
Collectors.groupingBy(
        Employee::team,
        Collectors.filtering(
                Employee::active,
                Collectors.mapping(
                        Employee::name,
                        Collectors.joining(", ")
                )
        )
)
```

This is an **illustrative collector expression**, in the context of an appropriate `Employee` class. It differs from `stream.filter(...).collect(groupingBy(...))`: filtering before `groupingBy` may prevent a key from being created if no elements remain for that key; using downstream filtering can preserve a group seen before filtering, though the joined value for that group may be an empty string.

### 10.3. Adding Prefix/Suffix per Group

When you want a value like `"[An, Hoa]"` for each group, pass the prefix/suffix to the downstream collector:

```java
Collectors.mapping(
        Employee::name,
        Collectors.joining(", ", "[", "]")
)
```

For a group with no names to collect, the resulting value is `"[]"` instead of `""`. Choosing which format to use is a display API decision.

## 11. Comparison with `String.join` and `StringJoiner`

For the same goal of joining strings, Java has three common APIs:

| API | When to use | Result |
| --- | --- | --- |
| `Collectors.joining(delimiter)` | You already have a `Stream<? extends CharSequence>` or a pipeline that needs filter/map/sort before joining | `String` via `collect` |
| `String.join(delimiter, elements...)` or `String.join(delimiter, Iterable)` | You already have an array/collection of `CharSequence`, with no Stream processing needed | Direct `String` |
| `StringJoiner` | You want to add elements step by step in imperative code, with delimiter/prefix/suffix | Builder object, retrieve string via `toString()` |

Example with an existing list of names:

```java
String result = String.join(", ", List.of("Lan", "An"));
```

The result is `"Lan, An"`. Requires importing `List`; there is no need to create a Stream for this. `String.join` does not have a separate overload for prefix and suffix like the three-argument collector.

Using `StringJoiner`:

```java
StringJoiner joiner = new StringJoiner(", ", "[", "]");
joiner.add("Lan");
joiner.add("An");
String output = joiner.toString();
```

The result is `"[Lan, An]"`. This illustrative snippet requires importing `java.util.StringJoiner`.

Internally, `joining` also uses an appropriate string accumulation mechanism, but when using Stream you should focus on the Collector contract rather than depending on the implementation. In a pipeline, `joining` helps avoid manually managing a mutable variable and handling comma separation by index.

## 12. Do Not Replace with Careless Manual String Concatenation

An error-prone approach:

```java
String text = names.stream()
        .reduce("", (acc, item) -> acc + ", " + item);
```

This is a code snippet inside a method assuming `names` is a String collection. With `["Lan","An"]`, the result is `", Lan, An"`: there is an **extra leading delimiter**. Trying to fix it manually with an empty accumulator check makes the code more complex and error-prone when an element is actually an empty string.

Moreover, `String` is immutable. Repeated string concatenation in a reduce operation can create many intermediate objects and incur unnecessary overhead. `Collectors.joining(", ")` expresses the exact intent, provides an appropriate accumulation strategy, and has a mechanism to combine partial results when the Stream framework needs it.

In some problems, `StringBuilder` can be used manually; however, it requires managing delimiters and state. For a pipeline that is already a Stream, `joining` is usually the clearest choice.

**Do not use a shared `StringBuilder` or `StringJoiner` and mutate it from `parallelStream().forEach(...)`.** This introduces order dependency, risks race conditions if the object is not thread-safe, and loses the benefits of a properly contracted Collector.

## 13. Performance, Parallel Streams, and Large Data

`joining` is generally easy to maintain and suitable for moderate-sized input data. However, it creates **a single final result string**, so sufficient memory is needed for the joined content. With millions of records or extremely long strings, consider **streaming output** to a file/writer in the required format instead of holding everything in RAM; in that case, writing and delimiter handling need to be designed specifically.

Some performance considerations:

1. `joining` avoids suboptimal consecutive `String` concatenation in a reduce loop.
2. `map`, `filter`, `sorted`, and `distinct` placed before the collector can change the data volume and cost, with sorting sometimes being significantly expensive.
3. With a parallel stream, the collector/framework may create partial results and then combine them; this does not mean string joining is automatically faster than sequential. Partitioning, joining/combining, and memory overhead can be substantial.
4. With a stream that has an encounter order, the resulting string must preserve that order. If the source is unordered, you cannot rely on a fixed joining order.
5. Long inputs, delimiters, and elements all contribute to the String length. Creating a very large string has JVM memory/capacity limits.
6. If you only need to join a small existing list, `String.join` can be more concise than constructing a Stream.

Prioritize **correct format and correct order** first, then measure performance on representative data.

## 14. Common Mistakes and How to Avoid Them

1. **Mistaking `joining` for a built-in operation on String.** It is a Collector: you need `stream.collect(Collectors.joining(...))`.
2. **Calling `joining(", ")` directly on `Stream<Integer>`.** Wrong type; convert to String using `map(n -> Integer.toString(n))` or `mapToObj(...)` for a primitive stream.
3. **Manually inserting leading/trailing delimiters with reduce.** Easy to get extra delimiters; use `joining(delimiter)` to insert only between elements.
4. **Forgetting that an empty stream produces an empty string.** If a prefix/suffix is present, the result is prefix + suffix, such as `"[]"`.
5. **Assuming an empty result string means there were no elements.** A single `""` element can also produce an empty string.
6. **Assuming null will be skipped by default.** You must explicitly choose `filter(Objects::nonNull)`, a `map` placeholder, or validation.
7. **Unclear ordering.** The collector does not `sorted()` automatically; with an unordered source, the joined result may change order.
8. **Using `joining(",")` to generate complete CSV/JSON.** There is no automatic escaping or quoting; you must use proper formatter rules or a standard library.
9. **Reusing the same Stream after collect.** A consumed Stream cannot be reused; create a new Stream from the source.
10. **Confusing `joining` with `toList`.** `joining` produces a String, losing element boundaries at the data-structure level.
11. **Believing groups in `groupingBy` always have a fixed key order.** Choose an appropriate Map supplier if you need to print in key order.
12. **Attaching side effects to a mapper just to count elements.** Streams may optimize or run in parallel; design separate statistics rather than relying on log counts.
13. **Assuming parallel is faster.** String joining requires reorganizing data; benchmark when truly needed.
14. **Mixing formatting labels with input data.** Prefix, suffix, and delimiter should be explicit formatting decisions; element names may contain the delimiter and require escaping in machine-readable formats.

## 15. Self-Check Exercise

Given the code snippet inside a Java 17 method, with `List`, `Stream`, and `Collectors` imported:

```java
List<String> words = List.of("pear", "apple", "kiwi");

String a = words.stream()
        .collect(Collectors.joining("|"));

String b = words.stream()
        .sorted()
        .collect(Collectors.joining(", ", "<", ">"));

String c = words.stream()
        .filter(w -> w.length() > 4)
        .collect(Collectors.joining("-"));

String d = Stream.<String>empty()
        .collect(Collectors.joining(";", "[", "]"));

String e = words.stream()
        .map(String::length)
        .map(String::valueOf)
        .collect(Collectors.joining(","));
```

Questions:

1. What are the values of `a` and `b`?
2. Why does `c` have no delimiter when only one element matches?
3. Is the result `d` an empty String?
4. What data type does `e` join in the final stage, and what is its result?
5. If `map(String::valueOf)` is removed from the pipeline creating `e`, what happens?

**Answers:**

1. `a = "pear|apple|kiwi"`. After `sorted()` in natural order, `b = "<apple, kiwi, pear>"`.
2. Only `"apple"` has a length greater than 4, so `c = "apple"`. There is no pair of elements between which to insert `"-"`.
3. `d = "[]"`, because the prefix and suffix are still preserved with an empty stream.
4. `map(String::length)` produces a `Stream<Integer>` with values 4, 5, 4; `map(String::valueOf)` converts them to strings, so `e = "4,5,4"`.
5. Without converting numbers to strings, `joining(",")` does not accept `Integer` as a `CharSequence`; the program will not compile.

## 16. Summary Rules

When you want to **collect strings into a single delimited value**, the common pattern is:

```java
String text = source.stream()
        .filter(/* appropriate condition */)
        .map(/* convert each element to String */)
        .collect(Collectors.joining(", ", "[", "]"));
```

This is an **illustrative syntax template**; the comments in `filter`/`map` must be replaced with valid lambdas or method references in real code.

Check each item in order:

- **Input type:** elements before `joining` must be compatible with `CharSequence`.
- **Elements actually joined:** the result of `map/filter/distinct/sorted`, not always the original elements.
- **Order:** the collector follows encounter order; for stability, ensure a deterministic source or call `sorted()`.
- **Formatting:** the delimiter is only between elements, prefix/suffix surround the whole result, and an empty stream can still return prefix + suffix.
- **Null and escaping:** choose an explicit handling policy according to output requirements.
- **Result type:** `collect(joining(...))` returns `String`; it does not modify the input collection.

**Remember:** `Collectors.joining(", ")` is the centralized, delimiter-safe way to join string elements in a Stream; `Collectors.joining(", ", "[", "]")` adds framing; `map(...)` and earlier stages determine **what data** gets joined. It is a result-collection tool, not a formatter for all data-export standards.

**References:** Java SE API `java.util.stream.Collectors.joining`, `Collectors.mapping`, `Collectors.groupingBy`, `java.util.stream.Stream.collect`, `java.lang.String.join`, and `java.util.StringJoiner`.
