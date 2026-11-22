# Collectors.joining in Stream Processing

`Collectors.joining` is a collector used at the terminal step of a `Stream` to **join text elements into a single `String`**. It is especially useful when data must pass through `filter`, `map`, or `sorted` operations before combining: instead of manually iterating, concatenating strings, and managing delimiters, you describe the entire process as a pipeline.

This lesson focuses on joining multiple parts with `Collectors.joining`, controlling delimiters and wrappers, and handling situations that can produce unexpected results.

## 1. Basic Usage

The `joining` methods live in `java.util.stream.Collectors`. The three most commonly used overloads:

| Expression | Result | Meaning |
| --- | --- | --- |
| `Collectors.joining()` | `"ABC"` | Concatenate directly with no delimiter. |
| `Collectors.joining(", ")` | `"A, B, C"` | Insert `", "` **between** consecutive elements. |
| `Collectors.joining(", ", "[", "]")` | `"[A, B, C]"` | Insert delimiter and wrap the **entire result** with prefix and suffix. |

Example with ordered data:

```java
List<String> parts = List.of("A", "B", "C");

String text = parts.stream()
        .collect(Collectors.joining(" - "));
// text = "A - B - C"
```

This is an **illustrative snippet**: to run it standalone, place it inside a Java method and import `java.util.List` and `java.util.stream.Collectors`. A complete program is in Section 4.

Elements in the stream must be compatible with `CharSequence` (usually `String`). Thus you can directly collect a `Stream<String>` or `Stream<CharSequence>`; for `Stream<Integer>` or an object stream, convert each element to a string before collecting.

## 2. Understanding the Parameters Correctly

### 2.1. `joining()`: Direct Concatenation

`Stream.of("Ja", "va", " 17").collect(Collectors.joining())` produces `"Java 17"`. The collector does not automatically add spaces, commas, or newline characters.

### 2.2. `joining(delimiter)`: Separator in Between

With `joining(" | ")`, `" | "` appears between elements, never automatically at the start or end. The delimiter is **plain text**, not a regular expression (regex); for instance, `joining(".")` inserts a literal dot, without the "any character" meaning a dot has in regex.

To join into multiple lines, use `joining("\n")`. The result contains newline characters between elements. If an element already contains `\n`, that character is preserved; `joining` does not normalize content automatically.

### 2.3. `joining(delimiter, prefix, suffix)`: Wrap the Result Once

`Stream.of("x", "y").collect(Collectors.joining(", ", "(", ")"))` returns `"(x, y)"`.

- `delimiter` is inserted **between** elements.
- `prefix` is inserted **once before the entire** string.
- `suffix` is inserted **once after the entire** string.

Therefore, `joining(", ", "[", "]")` produces list-style `[a, b]`; it does not produce `[a], [b]`. If you need to format each element individually, format them with `map` before `collect`.

## 3. Mechanism in a Stream Pipeline

Consider the following pipeline:

```java
String result = Stream.of("  Mai ", "", " Nam ", "  Lan ")
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .collect(Collectors.joining(" / "));
// result = "Mai / Nam / Lan"
```

Logical flow:

1. `Stream.of(...)` provides the source elements in their declared order.
2. `map(String::trim)` produces a version of **each** string with leading/trailing spaces removed.
3. `filter(s -> !s.isEmpty())` drops strings that are empty after trimming.
4. `collect(Collectors.joining(" / "))` is the **terminal operation**: the stream is consumed and the remaining strings are joined into one result.

`map` and `filter` are intermediate operations; they execute only when the terminal operation is invoked. `joining` handles delimiter insertion and accumulation into a final value, so there is no need to concatenate manually with `reduce((a, b) -> a + ", " + b)`.

Once `collect` runs, that stream cannot be reused for another terminal operation; to compute another result, create a new stream from the source. The source list is not modified by the pipeline above.

## 4. Standalone Java 17+ Program

Save with the exact filename `JoiningDemo.java` (using UTF-8):

```java
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class JoiningDemo {
    record Member(String team, String name) {}

    public static void main(String[] args) {
        List<String> fruits = List.of("táo", "cam", "lê");

        System.out.println(fruits.stream()
                .collect(Collectors.joining()));
        System.out.println(fruits.stream()
                .collect(Collectors.joining(" | ")));
        System.out.println(fruits.stream()
                .collect(Collectors.joining(", ", "[", "]")));

        System.out.println(Stream.<String>empty()
                .collect(Collectors.joining(", ", "[", "]")));
        System.out.println(Stream.of("", "")
                .collect(Collectors.joining(",")));

        List<String> rawNames =
                Arrays.asList("  An  ", null, "", " Bình ", "  Chi ");

        String cleanNames = rawNames.stream()
                .filter(Objects::nonNull)
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .collect(Collectors.joining(" / "));
        System.out.println(cleanNames);

        String numbers = Stream.of(10, 20, 30)
                .map(i -> Integer.toString(i))
                .collect(Collectors.joining(" + ", "(", ")"));
        System.out.println(numbers);

        List<Member> members = List.of(
                new Member("Backend", "An"),
                new Member("Frontend", "Bình"),
                new Member("Backend", "Chi")
        );

        Map<String, String> namesByTeam = members.stream()
                .collect(Collectors.groupingBy(
                        Member::team,
                        LinkedHashMap::new,
                        Collectors.mapping(
                                Member::name,
                                Collectors.joining(", ")
                        )
                ));

        namesByTeam.forEach((team, names) ->
                System.out.println(team + ": " + names));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 JoiningDemo.java
java JoiningDemo
```

Expected output (the fifth line has only **a single comma**):

```text
táocamlê
táo | cam | lê
[táo, cam, lê]
[]
,
An / Bình / Chi
(10 + 20 + 30)
Backend: An, Chi
Frontend: Bình
```

**Explanation of notable cases:**

- The first three statements differ only in the `joining` overload: direct concatenation; adding a separator; or also adding square brackets.
- An empty stream with `joining(", ", "[", "]")` still returns `"[]"`. The wrappers are not omitted simply because there are no elements.
- A stream with **two empty strings** is not an empty stream: one `","` delimiter still appears between the two elements.
- `Objects::nonNull` is placed **before** `String::trim` to avoid invoking a method on a `null` reference. Afterward, `filter` drops empty strings.
- `Integer` values are converted to `String` with `map` before entering the collector.
- `Collectors.mapping(Member::name, Collectors.joining(", "))` uses `joining` as a **downstream collector** of `groupingBy`. Each group gets its own joined name string; `LinkedHashMap` preserves first-appearance order of the groups in this sequential example.

## 5. Edge Cases to Know

| Input or operation | Result / behavior to remember |
| --- | --- |
| `Stream.<String>empty().collect(joining())` | Empty string `""`. |
| `Stream.<String>empty().collect(joining(",", "{", "}"))` | `"{}"`: prefix and suffix are still added. |
| `Stream.of("a").collect(joining(","))` | `"a"`: no delimiter because there is only one element. |
| `Stream.of("", "").collect(joining("-"))` | `"-"`: two empty elements have one delimiter between them. |
| `Stream.of("a", "b").collect(joining(""))` | `"ab"`: an empty delimiter acts like direct concatenation. |
| `Stream.of("a", null, "b").collect(joining(","))` | `"a,null,b"`: `null` is rendered as the text `"null"`. |
| `Stream.of("a", "b").collect(joining(",", "[", "]"))` | `"[a,b]"`, with no trailing comma. |

The expressions in the table use `Collectors.joining` in the shorthand `joining` form for readability. In real code, call `Collectors.joining(...)` in full or add `import static java.util.stream.Collectors.joining;`.

### 5.1. Handling `null` According to Business Meaning

`Collectors.joining` does not remove `null` elements. When a `null` element reaches the collector, the text `"null"` can appear in the output. Choose how to handle it **before** joining:

```java
// Skip null values:
String a = Stream.of("An", null, "Bình")
        .filter(Objects::nonNull)
        .collect(Collectors.joining(", "));
// "An, Bình"

// Replace null values with an explicit label:
String b = Stream.of("An", null, "Bình")
        .map(s -> s == null ? "(missing)" : s)
        .collect(Collectors.joining(", "));
// "An, (missing), Bình"
```

Do not use `map(String::trim)` or `map(Object::toString)` when the source may contain `null` without filtering or handling `null` first.

### 5.2. Empty Elements, Whitespace, and Delimiters

`joining` does not automatically trim whitespace, drop empty strings, deduplicate, or sort. For example, `" An "` and `"Bình "` with `joining(", ")` keep the spaces inside the elements. When normalizing, the usual order is **filter null → normalize with map → filter empty → join**.

If an element already contains the separator character (for example, the name `"An, Bình"`), `joining(",")` keeps the comma inside the name intact. It does not escape or quote for CSV. When exporting CSV/TSV or formats requiring escaping, apply the format's rules to **each value** before joining; you cannot assume the output of `joining(",")` is valid CSV.

### 5.3. Element Order

`joining` concatenates in **encounter order** if the stream has a defined order. `List.stream()` and `Stream.of(...)` are sources that normally preserve this order. If you start from a source with no guaranteed order (such as `HashSet`), or explicitly use `unordered()`, do not assume the resulting string follows a specific order.

When a deterministic order is required, use an ordered source or call `sorted()` / `sorted(comparator)` as appropriate before `collect`. On a parallel stream from a source with an encounter order, `joining` still collects results in encounter order, though parallelizing small datasets usually offers no speed benefit; there is no need to replace the collector with a `StringBuilder` shared across threads.

## 6. Joining Data After `map` and Inside Other Collectors

`joining` accepts elements that have already been turned into text. This lets you control how **each** object is displayed before inserting delimiters:

```java
record Product(String code, int quantity) {}

List<Product> products = List.of(
        new Product("P01", 2),
        new Product("P02", 5)
);

String summary = products.stream()
        .map(p -> p.code() + " x" + p.quantity())
        .collect(Collectors.joining("; ", "Order: ", "."));
// "Order: P01 x2; P02 x5."
```

This is an illustrative snippet placed in a context where `List` and `Collectors` are already imported. `map` creates a string representation for each `Product`; prefix `"Order: "` and suffix `"."` wrap the entire result string rather than each individual product.

Inside `groupingBy`, the downstream collector can be `Collectors.mapping(..., Collectors.joining(...))`, as in the program in Section 4. The idea is: **group objects → extract the display attribute in each group → join the attributes within each group**. This differs from calling `joining` once across the whole stream, which produces only a single combined `String`.

## 7. Choosing Between `Collectors.joining` and Other Joining Approaches

| Tool | When to use |
| --- | --- |
| `stream.collect(Collectors.joining(...))` | You already have a `Stream` pipeline with `filter`/`map`/`sorted` and need a single combined string at the end. |
| `String.join(delimiter, elements)` | You already have strings in an `Iterable` or as separate string arguments and do not need a stream pipeline. |
| `StringJoiner` | You want to add elements step by step manually while still getting delimiter, prefix, and suffix support. |
| `StringBuilder` | You have custom concatenation flow or layout, conditional insertions, or need fine-grained control over each append operation. |

Both `String.join` and `Collectors.joining` support delimiters, but `String.join` does not integrate `filter`/`map` operations into a terminal collector. Compared to manually reducing strings with `+`, `Collectors.joining` directly expresses the goal of joining text and uses an appropriate accumulator.

The result of `joining` is always logically a new `String`; it does not modify the source `String` values. Collecting an entire stream into one string requires holding the result in memory. If the dataset is huge and needs continuous output to a file/socket, consider writing sequentially to a `Writer`/`BufferedWriter` instead of accumulating all text into a single `String`.

## 8. Common Mistakes and How to Fix Them

**Mistake 1 — Joining a stream of integers directly**

```java
// Does not compile: joining requires elements compatible with CharSequence.
// Stream.of(1, 2, 3).collect(Collectors.joining(", "));

// Correct:
String result = Stream.of(1, 2, 3)
        .map(String::valueOf)
        .collect(Collectors.joining(", "));
// "1, 2, 3"
```

**Mistake 2 — Expecting prefix/suffix to wrap each element**

`joining(", ", "[", "]")` joins into `"[a, b]"`. If you want `"[a], [b]"`, use:

```java
String result = Stream.of("a", "b")
        .map(s -> "[" + s + "]")
        .collect(Collectors.joining(", "));
// "[a], [b]"
```

**Mistake 3 — Extra delimiters caused by empty input elements**

With `Stream.of("a", "", "b")`, `joining(",")` produces `"a,,b"` because empty elements still count. Filter with `filter(s -> !s.isEmpty())` if business rules want to omit them; for whitespace-only strings, you may need `trim` or `strip` before filtering.

**Mistake 4 — Output order changes between runs**

Check the source's ordering; a `HashSet` does not guarantee encounter order. If reproducible ordered output is needed, use a `List` or sort explicitly before joining.

**Mistake 5 — Treating the delimiter as data-format syntax**

`joining` only inserts text; it does not escape quotes, commas, or newlines inside a value or protect against SQL injection. When generating CSV, JSON, SQL, or HTML, use an encoder/library suited for the output format; in particular, never build SQL statements containing user input using `joining`.

## 9. Self-Check Your Understanding

Suppose:

```java
List<String> words = List.of(" java ", "", "stream", " java ");
String output = words.stream()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .distinct()
        .collect(Collectors.joining(" + ", "<", ">"));
```

`output` equals `"<java + stream>"`: `trim` removes outer whitespace, `filter` drops the empty string, `distinct` keeps the first occurrence of each string in encounter order, and then `joining` inserts `" + "` and wraps the entire result with `<` and `>`.

When reading a `Collectors.joining` pipeline, determine in turn **the elements remaining after intermediate operations**, **their order**, **the delimiter**, and then **prefix/suffix**. Those four factors determine almost every string-joining outcome.
