# `null` Policy for the Delimiter, Element Collection, and Individual Elements When Joining Strings in Java

## 1. Why Distinguish Three Kinds of `null`?

When joining multiple parts into one string, Java lets you use `String.join(...)` with a **delimiter** (separator string) and an **element collection** via varargs or `Iterable`. There are three independent places where `null` can appear:

1. **`null` delimiter:** the string used to separate elements does not exist.
2. **`null` element collection:** the varargs array or `Iterable` object itself does not exist.
3. **`null` individual element:** the collection exists, but an item inside it is `null`.

The three cases **do not share the same behavior**. According to the Java 17 API:

| `null` location | Example | Result |
| --- | --- | --- |
| Delimiter | `String.join(null, "A", "B")` | Throws `NullPointerException`. |
| Varargs array `elements` | `String.join(",", (CharSequence[]) null)` | Throws `NullPointerException`. |
| `Iterable elements` | `String.join(",", (Iterable<? extends CharSequence>) null)` | Throws `NullPointerException`. |
| An element in varargs | `String.join(",", "A", null, "B")` | `"A,null,B"`. |
| An element in `Iterable` | `String.join(",", Arrays.asList("A", null, "B"))` | `"A,null,B"`. |

**Short rule:** `String.join` requires **the delimiter and element collection to be non-`null`**, whereas if **an individual element** is `null`, it is represented by the character string `"null"`.

This matters greatly when exporting data, writing logs, constructing configuration strings, or converting lists to strings. The literal string `"null"` does not necessarily carry the same meaning as your application's original `null` value.

## 2. Two Overloads of `String.join`

Since Java 8, `String` has two overloads:

```java
public static String join(
        CharSequence delimiter,
        CharSequence... elements)

public static String join(
        CharSequence delimiter,
        Iterable<? extends CharSequence> elements)
```

### 2.1. Varargs Overload

```java
String result = String.join(" | ", "Java", "Core", "String");
System.out.println(result); // Java | Core | String
```

`elements` is represented as a `CharSequence[]` array when the call is processed. Usually, you do not need to create the array manually; just list the arguments.

### 2.2. `Iterable` Overload

```java
import java.util.List;

List<String> words = List.of("Java", "Core", "String");
String result = String.join(" | ", words);

System.out.println(result); // Java | Core | String
```

This is an `Iterable` with three elements. The `null`-handling contract for **elements** matches the varargs overload: a `null` item is appended as the text `"null"`.

Note: `List.of(...)` **does not accept `null` elements**. If you need to demonstrate an `Iterable` that actually contains `null`, you can use `Arrays.asList(...)` or a collection that permits `null`:

```java
import java.util.Arrays;
import java.util.List;

List<String> words = Arrays.asList("Java", null, "String");
System.out.println(String.join(" | ", words));
// Java | null | String
```

**Clear distinction:** the error when attempting `List.of("A", null)` comes from **`List.of`**, not from `String.join`. `String.join` accepts `null` items if the collection already holds them.

## 3. First Case: A `null` Delimiter

The delimiter is the text inserted **between consecutive elements**, such as `","`, `"; "`, or `" | "`. If the delimiter is `null`, `String.join` throws `NullPointerException`:

```java
String separator = null;

// Throws NullPointerException:
String value = String.join(separator, "A", "B");
```

Key characteristics:
- `null` is not automatically treated as an empty string.
- `null` is not automatically treated as a comma.
- You should not use the literal text `"null"` as a fallback delimiter unless business rules explicitly specify it.
- **An empty delimiter `""` is valid** and is distinct from a `null` delimiter.

Empty delimiter example:

```java
System.out.println(String.join("", "A", "B", "C")); // ABC
```

### Choosing a Policy for User-Supplied Delimiters

If a missing delimiter is an input error, **fail fast**:

```java
import java.util.Objects;

static String joinRequiredDelimiter(
        CharSequence delimiter,
        Iterable<? extends CharSequence> parts) {
    Objects.requireNonNull(delimiter, "delimiter");
    Objects.requireNonNull(parts, "parts");
    return String.join(delimiter, parts);
}
```

The snippet above is a **helper method meant to be placed inside a Java class**, not a standalone runnable file. When the delimiter or element collection is `null`, the error message points out which argument violated the contract.

If the product genuinely wants a missing delimiter to mean "no separator character," normalize it **deliberately** beforehand:

```java
String effectiveDelimiter =
        delimiter == null ? "" : delimiter.toString();

String result = String.join(effectiveDelimiter, "A", "B");
```

When `delimiter == null`, the result is `"AB"`. This is an **application-chosen policy**, not the default behavior of `String.join`.

## 4. Second Case: The Entire Element Collection Is `null`

The element collection can be passed as a `CharSequence[]` or an `Iterable<? extends CharSequence>`. If the collection object itself does not exist, `String.join` has no data source to iterate over and throws `NullPointerException`.

### 4.1. `null` Varargs Array

```java
CharSequence[] parts = null;

// Throws NullPointerException:
String result = String.join(",", parts);
```

### 4.2. `null` `Iterable`

```java
Iterable<String> parts = null;

// Throws NullPointerException:
String result = String.join(",", parts);
```

However, an **empty element collection** is completely valid:

```java
System.out.println("[" + String.join(",") + "]"); // []
System.out.println("[" + String.join(",", java.util.List.<String>of()) + "]");
// []
```

Both lines above print `[]` because we explicitly added square brackets; the actual return value of `String.join` is the **empty string `""`**, not the string `"[]"`.

| Input | Example | Result |
| --- | --- | --- |
| `null` collection | `(CharSequence[]) null` | `NullPointerException` |
| Collection with 0 elements | `new CharSequence[0]` | `""` |
| Collection with 1 empty element | `new CharSequence[]{""}` | `""` |
| Collection with 1 `null` element | `new CharSequence[]{null}` | `"null"` |

**Important:** an empty collection and a collection with a single empty string produce the exact same text `""` after joining. Therefore, `String.join` is **not a storage format capable of fully recovering the original list** in all situations.

### Policies for a `null` Collection

Three common choices:

- **Fail with an error:** the input is required; use `Objects.requireNonNull(parts)`.
- **Treat as an empty collection:** only when the business contract allows it. For example, convert `null` to `List.of()` before joining.
- **Distinguish "no data yet" from "empty list":** do not collapse both into `""` if the application needs to preserve that distinction. Use a separate data type or status field.

Example of explicitly treating a `null` list as empty:

```java
static String joinOrEmpty(
        String delimiter,
        java.util.List<String> parts) {
    java.util.Objects.requireNonNull(delimiter, "delimiter");
    return String.join(
            delimiter,
            parts == null ? java.util.List.<String>of() : parts);
}
```

The method still fails if the delimiter is `null`, but allows `parts` to be absent and returns an empty string. That is **an optional design**; do not apply it by default when data is mandatory.

## 5. Third Case: Individual Elements May Be `null`

When an item in the collection is `null`, `String.join` appends the **four characters** `n`, `u`, `l`, `l`:

```java
String result = String.join("|", "A", null, "B");
System.out.println(result); // A|null|B
```

Similarly with `Iterable`:

```java
java.util.List<String> parts =
        java.util.Arrays.asList("A", null, "B");

System.out.println(String.join("|", parts)); // A|null|B
```

This is **not** equivalent to any of the following behaviors:
- Skipping the `null` element → `"A|B"`.
- Replacing the `null` element with an empty string → `"A||B"`.
- Throwing an exception immediately upon encountering a `null` element.
- Inserting a nullable value that can be restored verbatim after splitting.

If `"null"` can also be a valid user-supplied string, the joined output **cannot tell them apart**:

```java
String a = String.join(",", "A", (CharSequence) null);
String b = String.join(",", "A", "null");

System.out.println(a);          // A,null
System.out.println(b);          // A,null
System.out.println(a.equals(b)); // true
```

**This is information loss**, not a bug in `String.join`. When a system needs to distinguish an absent value from the literal text `"null"`, use an encoding with explicit rules (such as JSON with typed `null` and quoted `"null"` strings) instead of using the joined result as the primary storage format.

### Overload Gotcha When Passing a `null` Literal

Because `String.join` has both varargs and `Iterable` overloads, a call using an untyped `null` such as:

```java
// Avoid because overload resolution can be ambiguous:
// String.join(",", null);
```

Can cause overload resolution issues or interpret `null` as the entire array/collection rather than a single element. **Declare or cast explicitly to state your intent**:

```java
System.out.println(String.join("|", (CharSequence) null));
// null  (a null element is converted to the text "null")

// Throws NullPointerException: the entire varargs array is null.
// String.join("|", (CharSequence[]) null);

// Throws NullPointerException: the entire Iterable is null.
// String.join("|", (Iterable<? extends CharSequence>) null);
```

What differs is **the type at the argument position** and which overload Java selects, not merely writing the keyword `null`.

## 6. Distinguishing Empty Elements, `null` Elements, and Elements Containing Delimiters

Consider delimiter `","`:

| Input list | `String.join(",", ...)` result | Notes |
| --- | --- | --- |
| `["A", "B"]` | `"A,B"` | Normal |
| `["A", null, "B"]` | `"A,null,B"` | `null` value becomes the text `"null"` |
| `["A", "", "B"]` | `"A,,B"` | Empty position is preserved |
| `["A", "null", "B"]` | `"A,null,B"` | Indistinguishable from a `null` element |
| `["A,B", "C"]` | `"A,B,C"` | Data contains the delimiter; not escaped automatically |
| `[]` | `""` | No elements |
| `[""]` | `""` | One empty element; same result as an empty collection |

`String.join` is **not a CSV encoder**. It does not quote values containing delimiters, does not escape quotes, and does not produce a safely recoverable nullable representation. If you are working with CSV, JSON, TSV, or standard data exchange formats, use an encoder built for that format.

Example with a comma inside the data:

```java
System.out.println(String.join(",", "New York, NY", "USA"));
// New York, NY,USA
```

You cannot split this result back into the exact two original parts using `split(",")` alone. Choosing a different delimiter sometimes reduces collisions, but **does not replace escaping/quoting**.

## 7. Four Common Policies for `null` Elements

If your business requirements differ from `String.join`'s default, you must process elements **before joining**.

Using a list that actually contains `null`:

```java
java.util.List<String> parts =
        java.util.Arrays.asList("A", null, "B");
```

### Policy A — Keep the Default: Literal `"null"`

```java
String output = String.join("|", parts);
System.out.println(output); // A|null|B
```

Suitable for some logs or manual inspection where you accept `"null"` as plain text and do not need to recover original data types.

### Policy B — Drop `null` Items

```java
import java.util.Objects;
import java.util.stream.Collectors;

String output = parts.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.joining("|"));

System.out.println(output); // A|B
```

**Impact:** the number of positions in the output string decreases. If elements represent fixed data columns (e.g., order ID, date, recipient), dropping an item shifts subsequent columns out of alignment.

### Policy C — Replace `null` with an Empty String

```java
import java.util.stream.Collectors;

String output = parts.stream()
        .map(x -> x == null ? "" : x)
        .collect(Collectors.joining("|"));

System.out.println(output); // A||B
```

This keeps the element's slot between delimiters, but cannot distinguish `null` from an empty string that already existed in the original data.

### Policy D — Replace with a Meaningful Placeholder

```java
import java.util.stream.Collectors;

String output = parts.stream()
        .map(x -> x == null ? "<missing>" : x)
        .collect(Collectors.joining("|"));

System.out.println(output); // A|<missing>|B
```

A placeholder is appropriate only if the business contract defines it clearly, and if the literal string `"<missing>"` can appear in real data, an escaping/disambiguation mechanism is still required.

### Policy E — Forbid `null` Elements (Fail Fast)

```java
import java.util.Objects;
import java.util.stream.Collectors;

String output = parts.stream()
        .map(x -> Objects.requireNonNull(x, "part"))
        .collect(Collectors.joining("|"));
```

For the list `["A", null, "B"]`, this throws `NullPointerException` with message `"part"`. This approach fits when **every element must have data** and you want to catch errors at the business boundary rather than silently emitting the text `"null"`.

**No single policy is best in all situations.** Decide explicitly whether you need to preserve element count, column positions, `null` information, or recoverability of original values.

## 8. Standalone Java 17+ Program

Save the following content into `JoinNullPolicyDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.StringJoiner;
import java.util.function.Supplier;
import java.util.stream.Collectors;

public class JoinNullPolicyDemo {
    private static void showResult(String label, Supplier<String> action) {
        try {
            System.out.println(label + " = " + action.get());
        } catch (NullPointerException ex) {
            System.out.println(label + " = NullPointerException");
        }
    }

    public static void main(String[] args) {
        List<String> parts = Arrays.asList("A", null, "B");

        System.out.println("varargs = ["
                + String.join("|", "A", null, "B") + "]");
        System.out.println("iterable = ["
                + String.join("|", parts) + "]");
        System.out.println("single null = ["
                + String.join("|", (CharSequence) null) + "]");
        System.out.println("empty varargs = ["
                + String.join("|") + "]");
        System.out.println("empty iterable = ["
                + String.join("|", List.<String>of()) + "]");
        System.out.println("empty member = ["
                + String.join("|", "A", "", "B") + "]");

        showResult("null delimiter",
                () -> String.join((CharSequence) null, "A", "B"));
        showResult("null array",
                () -> String.join("|", (CharSequence[]) null));
        showResult("null iterable",
                () -> String.join("|",
                        (Iterable<? extends CharSequence>) null));

        System.out.println("joiner = ["
                + new StringJoiner("|").add(null).add("B") + "]");

        String skip = parts.stream()
                .filter(Objects::nonNull)
                .collect(Collectors.joining("|"));
        System.out.println("skip null = [" + skip + "]");

        String asEmpty = parts.stream()
                .map(x -> x == null ? "" : x)
                .collect(Collectors.joining("|"));
        System.out.println("null as empty = [" + asEmpty + "]");

        String placeholder = parts.stream()
                .map(x -> x == null ? "<missing>" : x)
                .collect(Collectors.joining("|"));
        System.out.println("placeholder = [" + placeholder + "]");
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac -encoding UTF-8 JoinNullPolicyDemo.java
java JoinNullPolicyDemo
```

Output:

```text
varargs = [A|null|B]
iterable = [A|null|B]
single null = [null]
empty varargs = []
empty iterable = []
empty member = [A||B]
null delimiter = NullPointerException
null array = NullPointerException
null iterable = NullPointerException
joiner = [null|B]
skip null = [A|B]
null as empty = [A||B]
placeholder = [A|<missing>|B]
```

**Output explanation:**
- Both varargs and `Iterable` insert the text `"null"` for a `null` element.
- A `null` cast to `CharSequence` is **one element**, so it produces `"null"`.
- An empty collection yields an empty string, while a middle empty element preserves two delimiters.
- The delimiter, varargs array, and `Iterable` object must not be `null`.
- `StringJoiner.add(null)` also appends the text `"null"`.
- The `skip`, `asEmpty`, and `placeholder` policies transform the list differently **before joining**.

The program intentionally catches `NullPointerException` in each experiment to demonstrate behavior; it is not recommending `try/catch` as a replacement for input validation in production code.

## 9. How Do `StringJoiner` and `Collectors.joining` Relate?

`StringJoiner` is a useful complementary tool when you need to add elements incrementally or want a prefix/suffix:

```java
import java.util.StringJoiner;

StringJoiner joiner = new StringJoiner(", ", "[", "]");
joiner.add("A");
joiner.add(null);
joiner.add("B");

System.out.println(joiner.toString()); // [A, null, B]
```

With `StringJoiner`:
- The delimiter passed to the constructor must not be `null`; if it is `null`, it throws `NullPointerException`.
- `add((CharSequence) null)` inserts the text `"null"`.
- The three-argument constructor also requires non-`null` `prefix` and `suffix`.
- When no elements have been added yet, the default representation is `prefix + suffix`; you can configure `setEmptyValue` if needed.

Example distinguishing empty vs. one empty element:

```java
StringJoiner empty = new StringJoiner(",", "[", "]");
System.out.println(empty); // []

StringJoiner oneBlank = new StringJoiner(",", "[", "]");
oneBlank.add("");
System.out.println(oneBlank); // []
```

Even though the external representation looks identical, the "an element has been added" state differs. When exact structural recovery is required, neither `StringJoiner` nor `String.join` should be treated as a structured encoder.

`Collectors.joining(delimiter)` is commonly used after `stream()`. It lets the application **filter**, **map**, or **validate** inputs before joining:

```java
String result = parts.stream()
        .filter(java.util.Objects::nonNull)
        .collect(java.util.stream.Collectors.joining(","));
```

If `parts` is `null`, calling `parts.stream()` already throws `NullPointerException` before `Collectors.joining` ever runs. If you need to treat a `null` list as empty, that choice must happen **before calling `stream()`**.

Do not assume that merely using a Stream changes the `null` rules automatically. The clearest policy is applying explicit `filter`/`map`/validation according to your application contract.

## 10. Designing an API with a Clear `null` Policy

A robust string-joining design typically settles three questions upfront:

**(A) Is the delimiter required?** If yes, require non-`null`. If not, decide on an explicit default such as `""` or `", "`.

**(B) Is the element collection required?** Distinguish *missing list* (`null`), *existing empty list*, and *contains empty elements* if business logic cares about the difference.

**(C) What does `null` on an individual element mean?** Choose among: input error, drop item, keep slot with empty string, placeholder, or typed recoverable representation.

Example of an API that **forbids `null` at every level**, suitable for configuration fields requiring complete data:

```java
static String strictJoin(
        CharSequence delimiter,
        Iterable<? extends CharSequence> elements) {
    java.util.Objects.requireNonNull(delimiter, "delimiter");
    java.util.Objects.requireNonNull(elements, "elements");

    java.util.StringJoiner joiner =
            new java.util.StringJoiner(delimiter);

    for (CharSequence element : elements) {
        joiner.add(java.util.Objects.requireNonNull(
                element, "element"));
    }
    return joiner.toString();
}
```

This is a **helper method** to place inside a Java class. Unlike default `String.join`, it **fails with an error** on a `null` element instead of turning it into `"null"`.

Another option is **skipping `null`**:

```java
static String skipNulls(
        CharSequence delimiter,
        Iterable<? extends CharSequence> elements) {
    java.util.Objects.requireNonNull(delimiter, "delimiter");
    java.util.Objects.requireNonNull(elements, "elements");

    java.util.StringJoiner joiner =
            new java.util.StringJoiner(delimiter);
    for (CharSequence element : elements) {
        if (element != null) {
            joiner.add(element);
        }
    }
    return joiner.toString();
}
```

For example, input `["A", null, "B"]` produces `"A,B"` when the delimiter is `","`. If data has positional columns, **weigh the consequences of dropping a column** before choosing this policy.

## 11. Notes When Handling External Data

Common scenarios:

| Scenario | Policy to consider | Why? |
| --- | --- | --- |
| Read-only logs | Placeholder for `null` or keep default `"null"`, if acceptable | Readable, though it does not preserve data types. |
| Joining user-facing labels | Filter `null` or replace with user-friendly text | Avoids exposing confusing `"null"` text to users. |
| Positional column data | Do not silently drop `null` | Dropping an item shifts column positions. |
| Config where every part is required | Fail fast on missing delimiter/collection/element | Catches missing data early. |
| CSV/JSON export | Use a format-appropriate encoder | Needs proper escaping, delimiters, quotes, and typed `null`. |
| Strings that must parse back to a list | Use a recoverable schema/encoding | `String.join` does not preserve enough info to invert every case. |

A string like `"A,null,B"` does not reveal whether the middle element was originally Java `null` or the string `"null"`. Likewise, `"A,,B"` may contain an empty element, yet if the delimiter appears inside real data, splitting with `split` also cannot guarantee reconstructing the original list.

If the output is used to build SQL, shell commands, CSV, or file paths, **do not treat string joining as escaping or injection protection**. Use parameterized APIs or context-specific encoders.

## 12. Self-Check Exercises

### Exercise 1 — Three Kinds of `null`

```java
String.join(",", (CharSequence) null);
String.join(",", (CharSequence[]) null);
String.join(",", (Iterable<? extends CharSequence>) null);
```

**Answer:** The first call produces the string `"null"`; the second and third calls throw `NullPointerException`. Casting distinguishes **one element** from **the entire element collection**.

### Exercise 2 — Empty Delimiter vs. `null`

```java
System.out.println(String.join("", "A", "B"));
// String.join(null, "A", "B");
```

**Answer:** The first line prints `AB`. The commented line, if executed, throws `NullPointerException` because a `null` delimiter is invalid.

### Exercise 3 — `List.of` and `Arrays.asList`

```java
java.util.List<String> a =
        java.util.Arrays.asList("A", null, "B");
// java.util.List<String> b = java.util.List.of("A", null, "B");
```

**Answer:** `Arrays.asList` creates a list containing a `null` element; `List.of` does not allow `null` elements and throws `NullPointerException` upon creation. That is the contract of the collection factory, not `String.join`.

### Exercise 4 — Drop Element or Keep Position?

Positional input `["id-1", null, "ACTIVE"]`. If you drop `null` before joining with `";"`, what is the output and what is the risk?

**Answer:** `"id-1;ACTIVE"`. The "second column" slot disappears, which can cause a receiver to misassign `ACTIVE` to the wrong column. If the format must preserve column count, use a schema and encoding with clear rules; do not drop items on your own.

### Exercise 5 — Can the String `"null"` Be Distinguished from Java `null`?

```java
String a = String.join(",", "A", (CharSequence) null);
String b = String.join(",", "A", "null");
System.out.println(a.equals(b));
```

**Answer:** `true`. Their text results are identical. `String.join` does not preserve the original nullable type.

### Exercise 6 — Choosing a UI Policy

An application joins display names from user-entered items. If an item is missing, should it default to displaying `"null"`?

**Answer:** Do not default to that automatically. Define the UI requirement: omit the missing item, use a clear placeholder, or report an error. If the application needs to store and restore original data, store a structure that preserves nullability rather than relying on a joined string.

## 13. Summary

- `String.join` has two main overloads: **varargs `CharSequence...`** and **`Iterable<? extends CharSequence>`**.
- **`null` delimiter → `NullPointerException`.**
- **Entire varargs array or `Iterable` object is `null` → `NullPointerException`.**
- **Individual element is `null` → appends the text `"null"`**, neither skipping the element nor throwing an error automatically.
- **Empty collection → empty string**; empty elements still participate in joining and can produce two consecutive delimiters.
- `StringJoiner.add(null)` also appends `"null"`; `Collectors.joining` lets you apply explicit `filter`/`map` policies before joining.
- Distinguish `null` from the string `"null"`, as well as values containing the delimiter, when data recovery is needed.
- Define separate `null` policies for the **delimiter**, **element collection**, and **individual elements** based on your business contract rather than relying solely on defaults.

## References

- [Java SE 17 — `String.join(CharSequence, CharSequence...)` and `String.join(CharSequence, Iterable)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java SE 17 — `StringJoiner`: constructors and `add(CharSequence)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/StringJoiner.html)
- [Java SE 17 — `Collectors.joining`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html)
- [Java SE 17 — `List.of` and `Arrays.asList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)
