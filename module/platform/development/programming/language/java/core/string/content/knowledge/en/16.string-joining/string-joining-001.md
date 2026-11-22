# String.join with Arrays or Iterables

## 1. Lesson Objectives

When you have multiple pieces of text such as column names, tags, logical paths, or message components, you often want to join them into **a single string** with the same separator inserted between elements. `String.join(...)` solves that exact case: it takes a `delimiter` and multiple `CharSequence` elements, then returns a new `String`.

After this lesson, you will be able to:
- Choose the right `String.join` overload for **arrays**, **lists/Iterables**, or individual arguments.
- Predict the result when the list is empty, has one element, contains `null`, or uses an empty delimiter.
- Know when to preprocess data before joining and when to switch to `StringJoiner` or `Collectors.joining`.

## 2. The Two Overloads to Know

Since Java 8, the `java.lang.String` class provides two static methods:

```java
public static String join(CharSequence delimiter, CharSequence... elements);

public static String join(
        CharSequence delimiter,
        Iterable<? extends CharSequence> elements);
```

Where:
- `delimiter` is the string/character sequence inserted **between two consecutive elements**; it is not automatically added at the start or end.
- `elements` are the elements to join, in the exact order they are passed or the order in which the `Iterable` iterates over them.
- The return value is a new `String`; the operation does not modify the array, the collection, or the elements themselves.
- `CharSequence` is the interface implemented by `String`, `StringBuilder`, and `StringBuffer`. Therefore, arguments do not strictly have to be of type `String`.

| Input data | Call | Selected overload |
| --- | --- | --- |
| Individual elements | `String.join("-", "A", "B", "C")` | `CharSequence...` |
| `String[]` | `String.join("-", array)` | `CharSequence...`, passing the entire array |
| `List<String>` | `String.join("-", list)` | `Iterable<? extends CharSequence>` |
| `Set<String>` | `String.join("-", set)` | `Iterable<? extends CharSequence>` |
| `Iterable<StringBuilder>` | `String.join("-", items)` | `Iterable<? extends CharSequence>` |

**Syntax distinction:** the `...` in a Java declaration is *varargs*; at the call site, you can pass individual elements or a compatible object array. For `List`, `Set`, or a custom `Iterable`, Java uses the second overload.

## 3. Complete Example: Array, Iterable, and Varargs

Create the file `JoinDemo.java` with the following code (Java 17+):

```java
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class JoinDemo {
    public static void main(String[] args) {
        String[] words = {"Java", "Core", "String"};
        List<String> colors = List.of("đỏ", "xanh", "vàng");
        Set<String> ordered = new LinkedHashSet<>(List.of("A", "B", "C"));

        System.out.println("array: " + String.join(" / ", words));
        System.out.println("list: " + String.join(", ", colors));
        System.out.println("set: " + String.join(" -> ", ordered));
        System.out.println("varargs: " +
                String.join(".", "java", "lang", "String"));
        System.out.println("empty: [" +
                String.join(", ", new String[0]) + "]");
        System.out.println("one: " +
                String.join(" | ", new String[]{"solo"}));
        System.out.println("null item: " +
                String.join(", ", Arrays.asList("A", null, "C")));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 JoinDemo.java
java JoinDemo
```

Expected output:

```text
array: Java / Core / String
list: đỏ, xanh, vàng
set: A -> B -> C
varargs: java.lang.String
empty: []
one: solo
null item: A, null, C
```

Points to observe:
1. The `words` array has three elements, so ` / ` appears **twice**.
2. `colors` is a `List<String>`, processed via `Iterable` without converting to an array.
3. `LinkedHashSet` preserves insertion order `A, B, C`, so the result above has a deterministic order; `HashSet` in general does not guarantee that same order.
4. Calling `String.join(".", "java", "lang", "String")` uses varargs directly.
5. An empty array returns an empty string; the `[]` brackets appear only because we concatenated them in `println` for visibility.
6. A `null` element in the list is converted into the text `"null"`; this operation does not skip elements.

## 4. Joining Mechanism and Result Rules

Consider the call:

```java
String result = String.join(" | ", "A", "B", "C");
```

You can picture the process as `A` + `" | "` + `B` + `" | "` + `C`, producing `"A | B | C"`. The delimiter is inserted **n − 1 times** when there are `n >= 1` elements. `String.join` uses the Java library's internal joining mechanism, so you do not need to manually concatenate in a loop with `result += ...`.

| Case | Example | Return value |
| --- | --- | --- |
| Zero elements | `String.join(",", new String[0])` | `""` |
| One element | `String.join(",", "A")` | `"A"` |
| Multiple elements | `String.join(",", "A", "B")` | `"A,B"` |
| Empty delimiter | `String.join("", "A", "B")` | `"AB"` |
| Multi-character delimiter | `String.join(" -> ", "A", "B")` | `"A -> B"` |
| Empty element | `String.join(",", "A", "", "B")` | `"A,,B"` |
| `null` element | `String.join(",", "A", (CharSequence) null)` | `"A,null"` |

**Note:** `String.join` does **not** automatically trim whitespace, filter out empty elements, deduplicate, sort, or escape delimiter characters inside each element. For example, `String.join(",", "a,b", "c")` returns `"a,b,c"`, which does not preserve the original grouping when split by a plain comma.

### Distinguishing `null` by Position

- `delimiter == null`: throws `NullPointerException`.
- The entire `elements` array or the entire `Iterable` is `null`: throws `NullPointerException`.
- **An element inside** the array/`Iterable` is `null`: that value is represented as the character string `"null"` in the result.

Example distinguishing the two different situations:

```java
String[] values = {"A", null, "C"};
System.out.println(String.join("-", values)); // A-null-C

String[] missingArray = null;
// String.join("-", missingArray); // NullPointerException
```

Do not confuse an exception thrown **before joining** with the behavior of `join`: `List.of("A", null)` itself throws `NullPointerException` because `List.of` does not allow `null` elements. If you want to test a list containing `null`, you can use `Arrays.asList("A", null)`.

## 5. Working with Arrays

`String[]` is the most direct choice:

```java
String[] paths = {"api", "v1", "users"};
String route = String.join("/", paths); // "api/v1/users"
```

`String.join` does not normalize paths or add a leading `/`. If you need an actual filesystem path, consider a path API such as `Path` rather than building OS paths via string joining.

Primitive arrays, such as `int[]`, are **not** compatible with `CharSequence...`. For example, `String.join(",", new int[]{1, 2})` does not compile. To join numbers, you need to convert them to strings:

```java
import java.util.stream.Collectors;
import java.util.stream.IntStream;

String ids = IntStream.of(7, 12, 30)
        .mapToObj(String::valueOf)
        .collect(Collectors.joining("-"));

System.out.println(ids); // 7-12-30
```

This example is a **snippet meant to be placed inside an existing method or program**; to run it standalone, place the statements in `main` and add the shown imports.

## 6. Working with Iterable

`Iterable<? extends CharSequence>` allows using `List<String>`, `Set<String>`, and other iterable collections/objects. There is no need to call `toArray()` just to join elements.

```java
import java.util.List;

List<String> roles = List.of("reader", "editor", "admin");
String description = String.join(" | ", roles);
// "reader | editor | admin"
```

With a `List`, the list order is the joining order. With a `Set`, the order depends on the set implementation:
- `LinkedHashSet` preserves insertion order.
- `TreeSet` iterates in its sorted order.
- `HashSet` does not guarantee iteration order; do not use it when stable output is required.

An object declared only with type `Iterable<String>` can still be passed directly to `String.join`, because the second overload expects `Iterable<? extends CharSequence>`. Elements are iterated over to build the result; `String.join` does not require the collection to support indexed access.

### Iterable Containing a CharSequence Other Than String

```java
import java.util.List;

List<StringBuilder> builders = List.of(
        new StringBuilder("first"),
        new StringBuilder("second")
);

String joined = String.join(" + ", builders);
// "first + second"
```

At the time of joining, the contents of each `StringBuilder` are represented as a string. The resulting `joined` string will not change automatically if you later modify those source `StringBuilder` instances.

## 7. Cleaning Data Before Joining

In real-world data, you may need to remove `null`, trim whitespace, and drop empty items. `String.join` has no parameters to enable these behaviors; preprocess the source beforehand:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<String> raw = Arrays.asList("  Java  ", "", null, "  Core ");
List<String> cleaned = raw.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .filter(value -> !value.isEmpty())
        .toList();

System.out.println(String.join(", ", cleaned)); // Java, Core
```

This is an illustrative snippet meant for `main` or an appropriate method; `Stream.toList()` has existed since Java 16, so it works on Java 17+. Do not remove empty or `null` elements by default in every problem: sometimes an empty slot in the data carries meaning and must be preserved.

If you need conditional separator control, format escaping, or text normalization according to business rules, process them explicitly before calling `join`.

## 8. Choosing String.join, StringJoiner, or Collectors.joining

| Tool | Best suited for | Characteristics |
| --- | --- | --- |
| `String.join` | Already have an array, `Iterable`, or a few separate strings | Concise; only specifies delimiter and elements |
| `StringJoiner` | Adding elements incrementally; need prefix/suffix | Has `add`, delimiter, prefix, suffix |
| `Collectors.joining` | Processing a `Stream<String>` | Combines naturally with `filter`, `map`; has prefix/suffix overload |

Example when surrounding brackets are needed:

```java
import java.util.List;
import java.util.StringJoiner;
import java.util.stream.Collectors;

StringJoiner joiner = new StringJoiner(", ", "[", "]");
joiner.add("A").add("B");
System.out.println(joiner); // [A, B]

String collected = List.of("A", "B").stream()
        .collect(Collectors.joining(", ", "[", "]"));
System.out.println(collected); // [A, B]
```

`String.join` only inserts the delimiter; `String.join(", ", items)` by itself does not produce a `[` prefix or `]` suffix. Nor do you need to turn a `List` into a `Stream` just to call `Collectors.joining` when `String.join` already satisfies the requirement.

## 9. Common Mistakes and How to Avoid Them

1. **Using the wrong element type.** `String.join(",", List.of(1, 2))` is incompatible because `Integer` does not implement `CharSequence`. Convert elements to `String` first.
2. **Assuming `null` is skipped.** A `null` element becomes the text `"null"`; if that is not desired, filter it out first.
3. **Assuming `String.join` strips whitespace automatically.** `" A "` still keeps both spaces; trim explicitly when needed.
4. **Assuming every `Set` has a stable order.** Choose an order-preserving structure or sort explicitly if the output must be reproducible.
5. **Confusing the delimiter with a regular expression.** `String.join` inserts the delimiter literally; it does not interpret `.`, `|`, or `*` as regex.
6. **Using `join` to produce full CSV output.** Values with commas, double quotes, or newlines require CSV rules; `String.join(",", fields)` does not quote or escape automatically.
7. **Repeatedly concatenating strings with `+=` instead of joining.** With an existing collection, `String.join` expresses intent clearly and avoids manually managing leading/trailing delimiters.
8. **Passing an untyped `null` to an overload.** Both overloads accept reference types; declare data with explicit types and check for `null` before calling.

## 10. Practice Exercises

**Exercise 1.** Given `String[] tags = {"java", "core", "api"};`, produce `"java | core | api"` without using a loop.

```java
String[] tags = {"java", "core", "api"};
String result = String.join(" | ", tags);
```

**Exercise 2.** Given `List<String> letters = List.of("x", "y", "z");`, predict the results of `String.join("", letters)` and `String.join("/", List.<String>of())`.

Answer: `"xyz"` and `""`. An empty delimiter inserts no characters between elements; an empty iterable yields an empty string.

**Exercise 3.** With `Arrays.asList("A", "", null, "B")` and delimiter `"-"`, predict the result without filtering the data.

Answer: `"A--null-B"`. The empty element still occupies a position, and `null` is converted to the text `"null"`.

**Exercise 4.** If you want to export multiple fields that may contain commas and newlines in standard CSV format, is `String.join(",", fields)` alone enough?

Answer: Not enough. You need proper CSV quoting/escaping (or a CSV library) before emitting the data; `String.join` only performs character joining.

## 11. Key Takeaways

- **`String[]` or `CharSequence[]` arrays:** use the varargs overload, e.g., `String.join(", ", array)`.
- **`List<String>`, `Set<String>`, or `Iterable<? extends CharSequence>`:** pass directly, e.g., `String.join(", ", list)`.
- **Zero elements:** returns `""`. **`null` element:** produces `"null"`. **`null` delimiter or `null` source:** throws `NullPointerException`.
- **Order:** follows the array or the `Iterable` iteration order; does not sort automatically.
- **Normalization, filtering, adding prefix/suffix, or exporting escaped formats:** requires separate preprocessing or a more suitable tool.

API reference documentation: [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html), [Java SE 17 — StringJoiner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/StringJoiner.html), [Java SE 17 — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).
