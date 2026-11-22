# Delimiters and Empty Elements When Joining Multiple Strings in Java

## 1. The Problem to Solve

When joining multiple elements into one string, you normally place a **delimiter** (*separator*) between two consecutive elements. But what happens if one element is an empty string `""`, located at the start, middle, or end of the list? What is the result if the entire list has no elements? And should empty elements be automatically removed before joining?

These questions matter when generating data lines, concatenating arguments, displaying lists, building log strings, or exchanging information with other systems. One extra or missing delimiter can change the **number and positions of data fields**.

Consider three input strings:

```java
String a = "Java";
String b = "";
String c = "String";

String result = String.join("|", a, b, c);
System.out.println(result); // Java||String
```

Two adjacent `|` characters are **not a bug**: they represent that there is **an empty element in the middle**. If you removed `b` before joining, the result `Java|String` would have a different structure.

Core principle: **an empty element is not the same as a non-existent element**.

## 2. How Does `String.join` Place Delimiters?

Since Java 8, `String.join` has two common overloads:

```java
String.join(CharSequence delimiter, CharSequence... elements);
String.join(CharSequence delimiter,
            Iterable<? extends CharSequence> elements);
```

These are **API signatures for reference**, not standalone program declarations. `delimiter` is the separator string, and `elements` is the sequence of elements in the order you supply or the order iterated by the `Iterable`.

With `n` elements, if `n >= 1`, the joining rule is:

```text
element[0] + delimiter + element[1] + ... + delimiter + element[n-1]
```

In other words, there are **n − 1 delimiter insertions between elements**, with nothing automatically added at the start or end. When `n = 0`, the result is the empty string `""`.

```java
System.out.println(String.join(", ", "A", "B", "C")); // A, B, C
System.out.println(String.join(" / ", "A"));         // A
System.out.println(String.join(", ", new String[0]).isEmpty()); // true
```

**Note:** The delimiter can be one or more characters, or even the empty string `""`. The delimiter is copied as **literal** text; `String.join` does not use regular expressions (*regex*) to interpret the delimiter.

### Behavior Table for Empty Elements

In the following table, `<...>` only serves to **make the result boundaries visible**, not characters automatically added by `String.join`.

| Input elements | Delimiter | Result shown inside `<...>` | Meaning |
| --- | --- | --- | --- |
| No elements: `[]` | `","` | `<>` | Nothing to join |
| One element: `["A"]` | `","` | `<A>` | No delimiter needed |
| One empty element: `[""]` | `","` | `<>` | An element exists, but its content is empty |
| Two empty elements: `["", ""]` | `","` | `<,>` | Delimiter sits between two empty strings |
| `["A", "", "B"]` | `","` | `<A,,B>` | Preserves the empty element in the middle |
| `["", "A"]` | `","` | `<,A>` | Leading delimiter **because the first element is empty** |
| `["A", ""]` | `","` | `<A,>` | Trailing delimiter **because the last element is empty** |
| `["", "A", ""]` | `","` | `<,A,>` | Preserves both empty elements at the ends |
| `["A", "", "B"]` | `""` | `<AB>` | No character marks the boundary |

**Distinction:** `String.join(",", new String[0])` and `String.join(",", "")` both return `""`. Looking solely at the resulting string **cannot distinguish an empty list from a list containing a single empty element**. This is an information limit of simple delimiter-based encoding, not an API bug.

## 3. Three Distinct Concepts: No Elements, an Empty Element, and `null`

In Java, the following three cases are not the same:

- **No elements:** a list/array of length 0; e.g., `List.of()`.
- **One empty element:** a list of length 1 containing `""`. This is a valid `String` value with `length() == 0`.
- **One `null` element:** a list of length 1 containing a `null` reference; it is not a `String` object and not the string `"null"`.

By the `String.join` contract, if **an element** is `null`, the API appends the text `"null"` to the result:

```java
String joined = String.join("|", "A", null, "B");
System.out.println(joined); // A|null|B
```

This creates an important consideration: a `null` reference element and a **literal `"null"`** element produce the exact same representation after joining. If your data needs to distinguish an absent value from the four-character string `"null"`, you must use a **separate representation rule** (such as a data format that supports null values) rather than relying on `String.join`.

Additionally:

```java
String.join(",", "A", null);                // "A,null"
String.join(",", "A", "");                  // "A,"
String.join(",", new String[0]);           // ""
String.join(",", new String[]{null});      // "null"
```

The lines above are **illustrative expressions**. The text `"null"` is written when a **null element** appears; however, passing a **null delimiter** or a `null` `elements` array/`Iterable` itself throws `NullPointerException`. Do not confuse "a null element is converted to text" with "all null arguments are accepted."

## 4. Leading or Trailing Delimiters Can Be Completely Valid

A common scenario is wanting to join three fields in order, where the first or last field is allowed to be empty:

```java
String first = "";
String middle = "java";
String last = "";

String line = String.join("|", first, middle, last);
System.out.println("<" + line + ">"); // <|java|>
```

There is a `|` at the start of the line because **there is an empty field before `middle`**. There is a `|` at the end of the line because **there is an empty field after `middle`**. This is not an "extra delimiter inserted by mistake."

If the data requirement is to preserve all three positions, blindly stripping leading/trailing characters with `strip()` or substring logic can destroy information. Nor is `strip()` designed to remove delimiters; it removes leading/trailing whitespace according to `Character.isWhitespace`.

Conversely, when **displaying a list of names** where empty elements represent meaningless data, you may choose to drop them **before calling join**. This must be a deliberate decision based on the problem contract, not a default behavior attributed to the API.

## 5. When to Keep Empty Elements vs. Filter Them Out?

Define the data goal clearly:

| Goal | Policy for `""` | Example |
| --- | --- | --- |
| Columnar data where each position corresponds to a field | **Keep** empty elements | `["A", "", "B"]` → `A||B` |
| Building a display label from **optional** parts | Can drop `""` if blank parts carry no meaning | `["Lan", "", "Nguyen"]` → `Lan Nguyen` |
| Representing blank cells in a fixed record | **Keep** empty elements at the start and end too | `["", "A", ""]` → `|A|` |
| Building paths, URLs, protocol commands | Follow the **corresponding specification**; do not auto-filter | Delimiters can carry semantics |
| Human-readable logs or messages | Decide explicitly whether to preserve fields or only non-empty values | Must not mislead about missing fields |

Example filtering **only empty strings**:

```java
import java.util.List;
import java.util.stream.Collectors;

List<String> parts = List.of("Lan", "", "Nguyen");

String keepAll = String.join(" ", parts);
String skipEmpty = parts.stream()
        .filter(s -> !s.isEmpty())
        .collect(Collectors.joining(" "));

System.out.println("<" + keepAll + ">");  // <Lan  Nguyen>
System.out.println("<" + skipEmpty + ">"); // <Lan Nguyen>
```

This is an **illustrative snippet**; when using `List.of`, elements cannot be `null`. Filtering with `!s.isEmpty()` only removes `""`, **not** `" "` or `"\t"`. If the requirement is to drop whitespace-only elements, you can consider `!s.isBlank()` (Java 11+), though `isBlank` and `isEmpty` have different semantics and should not be swapped casually.

### For `null`: Define an Explicit Policy

If `null` means "no part to display," you can intentionally filter it out:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

List<String> items = Arrays.asList("A", null, "", "B");
String joined = items.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.joining("|"));

System.out.println(joined); // A||B
```

Here `null` is filtered out while empty elements are **kept**, so two consecutive delimiters still appear. If you also want to remove empty elements, add the appropriate filter policy **after** removing `null` to avoid a `NullPointerException`.

Dropping `null` works for some display lists, but may be **incorrect** for fixed-field records; for required fields, you should **fail with an error or use a format that represents null explicitly**.

## 6. `StringJoiner`: Controlling Delimiter, Prefix, Suffix, and Empty Value

`java.util.StringJoiner` is a mutable utility for **accumulating** elements, inserting a delimiter between them, and (if needed) adding a prefix/suffix.

```java
import java.util.StringJoiner;

StringJoiner joiner = new StringJoiner(", ", "[", "]");
joiner.add("A").add("").add("B");
System.out.println(joiner); // [A, , B]
```

`StringJoiner.add("")` still counts as **having added an element**. It does not skip empty strings. Similarly, `add(null)` appends the text `"null"`.

### Nothing Added Yet vs. Added `""`

```java
StringJoiner joiner = new StringJoiner(", ", "[", "]");

System.out.println(joiner); // []
joiner.setEmptyValue("[none]");
System.out.println(joiner); // [none]

joiner.add("");
System.out.println(joiner); // []
joiner.add("B");
System.out.println(joiner); // [, B]
```

Before `add(...)`, `StringJoiner` has no elements and uses `prefix + suffix`, or the **empty value** set by `setEmptyValue(...)`. After `add("")`, it is **no longer considered empty** even though the element's content is `""`: it reverts to the normal representation `prefix + "" + suffix`, which here is `[]`. When `B` is added, the delimiter appears between the empty element and `B`.

**Note:** When no elements have been added, `new StringJoiner(",")` without prefix/suffix returns `""`. If you want to distinguish visually between a list with zero elements and a list with an empty element, use `setEmptyValue` or track the **element count** separately; you cannot expect the string returned by `String.join` to carry that metadata automatically.

`StringJoiner` is useful when the number of elements is not known upfront or when adding incrementally in a loop. For an existing list, `String.join` is usually simpler.

## 7. `Collectors.joining`: Joining from a Stream While Keeping Empty Elements

For `Stream<String>`, Java provides these collectors:

```java
import java.util.stream.Collectors;
import java.util.stream.Stream;

String result = Stream.of("A", "", "B")
        .collect(Collectors.joining("|"));

System.out.println(result); // A||B
```

Common forms:

| API | Meaning |
| --- | --- |
| `Collectors.joining()` | Concatenate directly with no delimiter |
| `Collectors.joining(delimiter)` | Insert delimiter between elements |
| `Collectors.joining(delimiter, prefix, suffix)` | Insert delimiter and wrap result with prefix/suffix |

An **empty** stream with `Collectors.joining("|")` yields `""`; a stream with **one `""` element** also yields `""`. With the prefix/suffix collector, the empty representation follows `StringJoiner`: for example, `Collectors.joining(", ", "[", "]")` on an empty stream returns `"[]"`.

If empty elements need to be dropped, **filter before collecting**:

```java
String display = Stream.of("A", "", "B")
        .filter(s -> !s.isEmpty())
        .collect(Collectors.joining("|"));

System.out.println(display); // A|B
```

Before using a pipeline with potentially `null` elements, establish a policy and add `filter(Objects::nonNull)` when appropriate. `Collectors.joining` does not imply "filter out missing values"; normally, `null` is rendered as `"null"` when passed through `StringJoiner`.

## 8. Complete Java 17 Program

Save the following content to `JoinEmptyDemo.java`. The `<...>` markers are printed **only to make boundaries visible** when a string starts/ends with a delimiter or is completely empty.

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.StringJoiner;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class JoinEmptyDemo {
    public static void main(String[] args) {
        String[] fields = {"", "java", "", "core", ""};
        String joined = String.join("|", fields);
        String[] restored = joined.split(Pattern.quote("|"), -1);
        String[] defaultSplit = joined.split(Pattern.quote("|"));

        System.out.println("joined=<" + joined + ">");
        System.out.println("restored count=" + restored.length);
        System.out.println("restored same=" + Arrays.equals(fields, restored));
        System.out.println("first empty=" + restored[0].isEmpty());
        System.out.println("middle empty=" + restored[2].isEmpty());
        System.out.println("last empty=" + restored[4].isEmpty());
        System.out.println("default split count=" + defaultSplit.length);

        System.out.println("empty collection=<"
                + String.join(",", Collections.<String>emptyList()) + ">");
        System.out.println("one empty=<" + String.join(",", "") + ">");
        System.out.println("two empty=<" + String.join(",", "", "") + ">");
        System.out.println("empty separator=<"
                + String.join("", "A", "", "B") + ">");
        System.out.println("null item=<"
                + String.join("|", "A", null, "B") + ">");

        StringJoiner sj = new StringJoiner(", ", "[", "]");
        System.out.println("joiner no elements=" + sj);
        sj.setEmptyValue("[none]");
        System.out.println("joiner custom empty=" + sj);
        sj.add("");
        System.out.println("joiner one empty=" + sj);
        sj.add("B");
        System.out.println("joiner two elements=" + sj);

        String collected = Stream.of("a", "", "b")
                .collect(Collectors.joining("|"));
        System.out.println("stream=<" + collected + ">");
    }
}
```

Compile and run with **JDK 17 or newer**:

```bash
javac JoinEmptyDemo.java
java JoinEmptyDemo
```

Verified output on Java 21 (also Java 17 compatible):

```text
joined=<|java||core|>
restored count=5
restored same=true
first empty=true
middle empty=true
last empty=true
default split count=4
empty collection=<>
one empty=<>
two empty=<,>
empty separator=<AB>
null item=<A|null|B>
joiner no elements=[]
joiner custom empty=[none]
joiner one empty=[]
joiner two elements=[, B]
stream=<a||b>
```

**How to read the output:**

- `joined=<|java||core|>` confirms that empty elements at the start, middle, and end are preserved.
- `restored count=5` and `restored same=true` confirm that for **this data case**, `split(..., -1)` restores all five elements.
- `default split count=4` shows that `split(regex)` does not preserve **trailing** empty elements by default.
- `empty collection=<>` and `one empty=<>` produce the same string; the original element count can no longer be distinguished.
- `joiner custom empty=[none]`, yet after `add("")` it becomes `[]` because the joiner now has one element, albeit empty.

## 9. Joining Then Splitting Back: Why Are Empty Elements Easily Lost?

If you use a delimiter to **encode multiple fields**, decoding with `String.split` must be well understood.

```java
String text = "A,,B,";
String[] withoutLimit = text.split(",");
String[] keepTrailing = text.split(",", -1);

System.out.println(withoutLimit.length); // 3
System.out.println(keepTrailing.length); // 4
```

`split(regex)` is equivalent to `split(regex, 0)`: Java discards **trailing empty elements** from the resulting array. `split(regex, -1)` preserves trailing empty elements because a negative `limit` applies the pattern without limit and does not discard trailing empty strings.

In the middle of the string, empty elements can still be preserved:

```java
String[] middle = "A,,B".split(",", -1);
// Logical contents: ["A", "", "B"]
```

### `join`'s Delimiter Is Literal Text; `split`'s Delimiter Is a Regex

This is an especially important distinction:

```java
String joined = String.join("|", "A", "", "B"); // A||B
String[] parts = joined.split(
        java.util.regex.Pattern.quote("|"), -1);
```

`String.join("|", ...)` treats `|` as a literal delimiter. However, `split("|")` does not interpret `|` that way: in regex, `|` is the *alternation* operator. Use `Pattern.quote("|")` or an appropriately escaped regex to split on the **exact literal delimiter**. When the delimiter comes from dynamic configuration such as `"."`, `"|"`, or `"||"`, `Pattern.quote(delimiter)` usually prevents errors caused by regex metacharacters.

### `split(..., -1)` Still Does Not Guarantee Round-Trip Recovery for All Inputs

Even when trailing empty elements are preserved, `join` + `split` is **not a general lossless encoding**:

1. **An empty list and a list containing a single empty string both produce `""`.** Splitting `""` by a non-empty delimiter with `limit=-1` yields a single empty string, making it impossible to tell whether there were 0 or 1 elements originally.
2. **Elements that contain the delimiter introduce ambiguity.** For example, `["A,B", "C"]` and `["A", "B", "C"]` both join with `,` to produce `"A,B,C"`.
3. **`null` and literal `"null"` lose their distinction** because `String.join` converts both to the text `"null"`.
4. **An empty delimiter `""` preserves no boundaries.** `["AB"]` and `["A", "B"]` both become `"AB"` when joined with an empty delimiter.

Therefore, `String.join` is great for **simple representation**, not as a serializer that preserves full field metadata, escaping, nullness, and boundaries.

## 10. Do Not Use `String.join` as a General CSV/TSV Serializer

CSV has its own rules covering delimiters, double quotes, escaping, newlines, and empty-field policies. If a data field contains commas, double quotes, or newline characters, `String.join(",", fields)` alone is **not sufficient** to produce valid CSV in all cases.

For example:

```java
String[] fields = {"Nguyen, Lan", "Java"};
System.out.println(String.join(",", fields));
// Nguyen, Lan,Java
```

If you simply call `split(",")` afterward, the result has **three pieces** instead of the original two fields. In standard CSV, a field containing a comma typically must be quoted, and quotes inside the field must also be escaped according to the format. Use an appropriate CSV library/parser when data must be persisted or exchanged between systems. Formats like JSON also define clear rules for empty arrays, `null`, empty strings, and escaping.

**Practical choices:**

- **Grouping display labels:** `String.join`, optionally filtering empty elements for display needs.
- **Simple log concatenation:** `StringJoiner` or `Collectors.joining`; ensure critical fields are not silently dropped when debugging.
- **Fixed-record lines where delimiters cannot appear in fields:** keep all fields, use a literal delimiter, and `split(Pattern.quote(delimiter), -1)` when splitting; still handle the 0 vs. 1 empty-element case.
- **General structured data:** use a format/serializer with explicit escaping, null representation, and field boundaries.

## 11. Common Mistakes

1. **Thinking `String.join` automatically skips `""`.** No: each empty element still occupies a slot and produces delimiters according to the element count.
2. **Thinking a leading/trailing delimiter means `join` added an extra one.** If the first or last element is empty, a delimiter at the boundary of the result is completely accurate.
3. **Failing to distinguish an empty list from a single empty element.** Both can encode to `""`, yet one has 0 elements and the other has 1 element.
4. **Confusing a `null` element with a `null` delimiter.** A null element becomes the text `"null"`; a null delimiter or null element collection throws `NullPointerException`.
5. **Calling `split(",")` and losing trailing empty fields.** If you need to keep them, use `split(",", -1)`.
6. **Using `split("|")` to split on a literal `|`.** `split` expects a regex; use `Pattern.quote("|")`.
7. **Filtering empty elements in positional column data.** Filtering shifts subsequent values into earlier columns; never sacrifice structure just to make a string look cleaner.
8. **Equating `isEmpty()` with `isBlank()`.** `""` is empty; `" "` is not empty, though it may be blank. Their filtering policies differ.
9. **Using `join` then `split` as a lossless encoding.** Data containing delimiters, nulls, or 0/1 empty lists makes round-tripping unreliable.
10. **Building CSV by joining with commas without escaping.** CSV/TSV and data protocols may require quoting, escaping, and newline handling; use format-appropriate tools.

## 12. Self-Check Exercises

Evaluate the following two strings **without running code**:

```java
String first = String.join("-", "", "A", "", "B", "");
String second = String.join("-", "A", "B");
```

Answer:

```text
first  = -A--B-
second = A-B
```

There are five elements in `first`, so there are **four `-` delimiters**, even though the outer elements are empty. `second` has two elements, so there is only one delimiter.

Next, given `String value = "A||B|"`, consider:

- `value.split(java.util.regex.Pattern.quote("|"))` produces **3** elements (`"A"`, `""`, `"B"`) because the trailing empty element is discarded.
- `value.split(java.util.regex.Pattern.quote("|"), -1)` produces **4** elements, including the trailing empty element.
- From the string `"A||B|"` alone, you cannot tell whether the original data was produced by an encoding with escaping; guaranteeing full input reconstruction requires an appropriate representation contract.

**Takeaway:** `String.join` inserts delimiters **between elements** and does not drop empty strings by default. Decide explicitly on your policy for keeping/filtering `""` and `null` before joining; if you need to split back, remember `split`'s regex behavior and `limit=-1`, and do not treat plain string joining as a lossless data format.

### Java 17 API References

- [`String.join` and `String.split` — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`StringJoiner` — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/StringJoiner.html)
- [`Pattern.quote` and `split` limits — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
