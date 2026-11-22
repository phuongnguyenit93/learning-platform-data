# StringJoiner.add, merge, and setEmptyValue in Java

When you need to join multiple pieces of text into a delimiter-separated string, Java provides `java.util.StringJoiner`. Instead of manually tracking "is this the last element?", you supply a **delimiter**, and optionally a **prefix** and **suffix**. Each time you call `add(...)`, the joiner records another element. `merge(...)` combines the contents of another joiner, while `setEmptyValue(...)` specifies how to display a joiner **when no elements have been added**.

The three methods are closely related but serve distinct purposes:

- `add(CharSequence)`: adds **one element**; empty strings can be added and `null` values follow a specific rule.
- `merge(StringJoiner)`: appends the **inner contents** of another joiner if that joiner is non-empty, **without carrying over the source's prefix/suffix**.
- `setEmptyValue(CharSequence)`: changes the display string **only when no elements have ever been added**; it is not `clear()` and does not erase existing content.

Understanding what "empty" means in `StringJoiner` is key to avoiding extra delimiters, accidentally inserting `"null"`, or misusing `merge`.

## 1. Creating a StringJoiner: delimiter, prefix, suffix

The `StringJoiner` class belongs to the `java.util` package:

```java
import java.util.StringJoiner;

StringJoiner plain = new StringJoiner(", ");
StringJoiner decorated = new StringJoiner(", ", "[", "]");
```

This is an illustrative snippet meant to be placed inside a Java method. The two common constructors:

| Constructor | Meaning | Example output after adding A, B |
|---|---|---|
| `new StringJoiner(delimiter)` | Delimiter only, empty prefix/suffix | `A, B` |
| `new StringJoiner(delimiter, prefix, suffix)` | Delimiter, optional prefix and suffix | `[A, B]` |

`delimiter` appears only **between elements**; it is never added automatically before the first element or after the last element. `prefix` and `suffix` wrap the **resulting content** once the joiner has elements. If no elements have been added and `setEmptyValue` has not been called, `toString()` returns `prefix + suffix` (with the one-argument constructor, both strings are empty so the result is `""`).

Examples:

```text
new StringJoiner(", ")             nothing added yet → ""
new StringJoiner(", ", "[", "]")   nothing added yet → "[]"
new StringJoiner(" / ", "<", ">")  nothing added yet → "<>"
```

**Do not confuse prefix/suffix with elements.** In `new StringJoiner(",", "[", "]")`, the square brackets are merely the outer display shell of the result; they do not count as two elements of the joiner. Constructor arguments `delimiter`, `prefix`, and `suffix` must all be non-`null`; passing `null` results in `NullPointerException`.

### Example 1: Joining Parts and Chaining Calls

Save as **`StringJoinerAddDemo.java`**:

```java
import java.util.StringJoiner;

public class StringJoinerAddDemo {
    public static void main(String[] args) {
        StringJoiner names = new StringJoiner(", ", "[", "]");

        System.out.println("initial: " + names);

        names.add("An").add("Binh").add("Chi");

        System.out.println("joined: " + names);
        System.out.println("length: " + names.length());
        System.out.println("content: " + names.toString());

        StringJoiner plain = new StringJoiner(" | ");
        plain.add("Java").add("Core");
        System.out.println("plain: " + plain);
    }
}
```

Compile and run with JDK 17+ in the directory containing the file:

```bash
javac StringJoinerAddDemo.java
java StringJoinerAddDemo
```

**Stdout:**

```text
initial: []
joined: [An, Binh, Chi]
length: 15
content: [An, Binh, Chi]
plain: Java | Core
```

Counting `length()`: `[` is 1, `An` is 2, `, ` is 2, `Binh` is 4, `, ` is 2, `Chi` is 3, and `]` is 1; totaling **15 UTF-16 code units**. `StringJoiner.length()` measures the length of the **resulting string**, including prefix, elements, delimiters, and suffix, not the number of elements. The API has no `size()` method for element count.

`add(...)` returns **the joiner itself** for fluent method chaining; it does not create a new `StringJoiner` on each addition.

## 2. `add(CharSequence)`: Exactly One Element per Call

Primary signature:

```java
public StringJoiner add(CharSequence newElement)
```

For example, `joiner.add("red").add("green")` holds two elements. When producing the result, the joiner inserts exactly one delimiter between these two elements. An element can be a `String`, `StringBuilder`, or another `CharSequence` implementation. With mutable inputs, treat the data as **added according to its content at the time of the call**, without expecting later mutations of the source object to automatically update what was added.

### Empty String `""` Still Counts as an Element

`joiner.add("")` **marks the joiner as having an element**, even though the visible characters added have length 0. If you subsequently add another element, the delimiter appears in between:

```java
StringJoiner j = new StringJoiner("|", "<", ">");
j.add("").add("A");
```

The result of `j.toString()` is `"<|A>"`, not `"<A>"`. Because the first element is an empty string, the second element is `"A"`, and the delimiter `|` sits between them.

This leads to an important distinction:

- **Never called `add`:** the joiner is considered empty according to its internal state.
- **Called `add("")`:** the joiner **is no longer empty**, even though without prefix/suffix `toString()` may still look like an empty string.

Do not use `toString().isEmpty()` alone as a reliable test for "no elements added yet"; the two states are not equivalent.

### A `null` Argument Becomes the Text `"null"`

By the `add(CharSequence)` contract, if `newElement == null`, it appends the four characters `n`, `u`, `l`, `l`. It does **not** skip the element and does not throw `NullPointerException`.

**`StringJoinerEdgeDemo.java`**

```java
import java.util.StringJoiner;

public class StringJoinerEdgeDemo {
    public static void main(String[] args) {
        StringJoiner first = new StringJoiner("|", "<", ">");
        System.out.println("empty: " + first);
        first.add("");
        System.out.println("after empty string: " + first);
        first.add("A");
        System.out.println("after A: " + first);

        StringJoiner second = new StringJoiner(",", "[", "]");
        second.add(null).add("");
        System.out.println("null and empty: " + second);
    }
}
```

```bash
javac StringJoinerEdgeDemo.java
java StringJoinerEdgeDemo
```

**Stdout:**

```text
empty: <>
after empty string: <>
after A: <|A>
null and empty: [null,]
```

`add(null)` is usually not what business logic wants. If you want to **skip `null` elements**, filter explicitly before calling:

```java
if (value != null) {
    joiner.add(value);
}
```

If you want to replace `null` with another label, explicitly use `Objects.toString(value, "(missing)")` or an appropriate conversion rule. Do not rely on `StringJoiner` to guess your missing-data policy.

## 3. `setEmptyValue(...)`: The State When No Elements Have Been Added

Signature:

```java
public StringJoiner setEmptyValue(CharSequence emptyValue)
```

When no elements have been added, `setEmptyValue` replaces the string returned by `toString()` and the value used for `length()`. This is the **entire display value** for the empty state, **not wrapped again by prefix/suffix**.

For example, a joiner with `[` and `]` shells displays `[]` by default. If you call `setEmptyValue("(none)")`, the displayed string becomes `(none)`, **not** `[(none)]`.

Once an element has been added, `setEmptyValue` no longer affects the display output of the current joiner. Even if that element is `""`, the joiner is still considered to have an element.

### Example 2: Before and After Adding Elements

**`StringJoinerEmptyValueDemo.java`**

```java
import java.util.StringJoiner;

public class StringJoinerEmptyValueDemo {
    public static void main(String[] args) {
        StringJoiner tags = new StringJoiner(", ", "[", "]");

        System.out.println("default empty: " + tags);

        tags.setEmptyValue("(none)");
        System.out.println("custom empty: " + tags);
        System.out.println("empty length: " + tags.length());

        tags.add("");
        System.out.println("after add empty: " + tags);
        System.out.println("after add empty length: " + tags.length());

        tags.setEmptyValue("(changed)");
        System.out.println("after setting again: " + tags);

        tags.add("Java");
        System.out.println("after Java: " + tags);
    }
}
```

```bash
javac StringJoinerEmptyValueDemo.java
java StringJoinerEmptyValueDemo
```

**Stdout:**

```text
default empty: []
custom empty: (none)
empty length: 6
after add empty: []
after add empty length: 2
after setting again: []
after Java: [, Java]
```

At the `add("")` step, the joiner transitions from "no elements yet" to "one empty element added." The result `[]` looks like the default state, yet **it no longer applies `emptyValue`**, and the length of the result is 2. After adding `"Java"`, the delimiter `", "` sits between the two elements, producing `"[, Java]"`.

`setEmptyValue(...)` returns the same joiner so it can be chained with `add(...)`:

```java
String result = new StringJoiner(", ", "[", "]")
        .setEmptyValue("(none)")
        .add("A")
        .add("B")
        .toString(); // "[A, B]"
```

This is an illustrative snippet. Calling `setEmptyValue(null)` is invalid and throws `NullPointerException`, unlike `add(null)`. There is no `StringJoiner.clear()` or `reset()` to revert a joiner that already has elements back to the unpopulated state; create a new joiner when you need a fresh joining pass.

### When Should You Set `emptyValue`?

- Filter lists with no active conditions: `"(none)"` or an empty string per UI standards.
- Display string for an element collection: default `"[]"` when prefix/suffix are square brackets.
- Log-line joining output with no items: can use `"N/A"` if the data contract specifies it clearly.

The deciding factor is **the meaning of a list with no elements**. Do not use `setEmptyValue` as a substitute for checking empty elements or null elements.

## 4. `merge(StringJoiner)`: Source Contents Merged as One Part

Signature:

```java
public StringJoiner merge(StringJoiner other)
```

`merge(other)` takes the **inner contents** of `other` and appends them to the receiving joiner. It ignores **the source's prefix and suffix**. If `other` is a joiner **with no elements yet**, the call **does not change the contents** of the receiving joiner, even if `other.setEmptyValue(...)` has a custom value.

If `other` already has elements, the joined text of the source elements is added **as a single composite element** of the target joiner. Therefore:

- The **source joiner's** delimiter between source elements **is preserved inside the imported content**.
- The **target joiner's** delimiter separates this composite part from existing parts in the target.
- The **source's** prefix/suffix **are not copied**.
- The **target's** prefix/suffix **are still used** when building the final string.
- The call returns **the target joiner itself**; you can continue chaining `add()` or `merge()`.

Common misconception: `merge` does **not** iterate over each source element and replace every source delimiter with the target delimiter. With source `"B+C"` and target using `" | "`, the imported content still retains `+`.

### Example 3: Merging with Different Delimiters and Wrappers

**`StringJoinerMergeDemo.java`**

```java
import java.util.StringJoiner;

public class StringJoinerMergeDemo {
    public static void main(String[] args) {
        StringJoiner target =
                new StringJoiner(" | ", "<", ">").add("A");

        StringJoiner source =
                new StringJoiner("+", "[", "]").add("B").add("C");

        System.out.println("target before: " + target);
        System.out.println("source before: " + source);

        target.merge(source);
        System.out.println("target merged: " + target);
        System.out.println("source visible: " + source);

        target.add("D");
        System.out.println("target after D: " + target);
    }
}
```

```bash
javac StringJoinerMergeDemo.java
java StringJoinerMergeDemo
```

**Stdout:**

```text
target before: <A>
source before: [B+C]
target merged: <A | B+C>
source visible: [B+C]
target after D: <A | B+C | D>
```

Explanation: the source has two elements, whose inner representation without wrappers is `"B+C"`. On merge, the target joiner adds **one composite element** `"B+C"` after `"A"`, using the target delimiter `" | "`, while the source's prefix/suffix `[` and `]` do not appear in the target. After `add("D")`, the target has one more independent element, so it appends the target delimiter again.

**Do not infer element count from the displayed output:** the `+` in `"B+C"` is now part of **one merged content unit** in the target, not a separator managed by the target between two separate elements. `StringJoiner` has no public API to return the element list for re-parsing the original structure.

### `merge` Is Not Concatenating Two Strings Including Their Wrappers

Suppose:

```java
StringJoiner a = new StringJoiner(",", "{", "}").add("X");
StringJoiner b = new StringJoiner(";", "[", "]").add("Y");
a.merge(b);
```

The result of `a.toString()` is `"{X,Y}"`, not `"{X,[Y]}"`. If you genuinely want to keep the source's full decorated output as a **text element**, use `a.add(b.toString())`. These two operations have different meanings:

- `a.merge(b)`: imports the **inner contents** of the source joiner.
- `a.add(b.toString())`: adds the **full display string**, including the source prefix/suffix, as a new element.

Both are illustrative snippets; choose based on the output structure you want to build.

## 5. Merging a Joiner with No Elements vs. a Joiner That Called `add("")`

This edge case often yields surprising results. Under the `merge` contract, "other empty" means **no elements have been added**, not "`toString()` displays an empty string." A custom `emptyValue` exists purely for display and **never becomes content to merge**.

For example:

- Source has added nothing, `source.setEmptyValue("SOURCE_EMPTY")`: `target.merge(source)` leaves `target` unchanged.
- Source has called `source.add("")`: `source` **is no longer empty**, and `merge` adds one element with empty content to `target`.
- If `target` has no elements yet but has `setEmptyValue(...)`, merging an empty element also causes `target` **to stop using `emptyValue`**.

### Example 4: The Difference Appears When Adding the Next Element

**`StringJoinerMergeEmptyDemo.java`**

```java
import java.util.StringJoiner;

public class StringJoinerMergeEmptyDemo {
    public static void main(String[] args) {
        StringJoiner target = new StringJoiner(",", "{", "}")
                .setEmptyValue("TARGET_EMPTY");

        StringJoiner source = new StringJoiner(";", "[", "]")
                .setEmptyValue("SOURCE_EMPTY");

        System.out.println("target initially: " + target);
        System.out.println("source initially: " + source);

        target.merge(source);
        System.out.println("merge untouched: " + target);

        source.add("");
        System.out.println("source with empty member: " + source);
        target.merge(source);
        System.out.println("merge empty member: " + target);

        target.add("X");
        System.out.println("after X: " + target);
    }
}
```

```bash
javac StringJoinerMergeEmptyDemo.java
java StringJoinerMergeEmptyDemo
```

**Stdout:**

```text
target initially: TARGET_EMPTY
source initially: SOURCE_EMPTY
merge untouched: TARGET_EMPTY
source with empty member: []
merge empty member: {}
after X: {,X}
```

The final line `"{,X}"` proves that `target` now holds **one merged empty element**, even though at the `"{}"` step it looked just like the state with no elements. Do not test "has an element been added yet?" by comparing `toString()` against `prefix + suffix`; the same display text can correspond to two different logical states.

## 6. Using `add` vs. `merge`, and the Difference in Intent

| Need | Choice | Why |
|---|---|---|
| Add a single value `"A"` | `add("A")` | Records exactly one element |
| Add an element that may contain the delimiter | `add(value)` | Does not split `value` into multiple parts |
| Import contents already joined by another joiner | `merge(other)` | Keeps source's internal delimiter and strips source's wrapper |
| Keep the entire source output including prefix/suffix | `add(other.toString())` | Treats the entire source string as one element |
| Transfer individual elements from a dataset | Loop `add(value)` on the original input data | Avoids relying on joined text that lost element boundaries |
| Represent a list with no elements | `setEmptyValue(text)` | Changes only how the empty state is displayed |
| Skip `null` elements | Filter manually before `add` | `add(null)` appends `"null"` by default |
| Discard an old joiner and start fresh | Create a `new StringJoiner(...)` | There is no `clear()` method |

A useful example is combining multiple groups of values. If the groups share the **same delimiter**, merging usually yields readable output like concatenating lists. If the groups use **different delimiters**, the source's representation is preserved inside the merged part, so you must evaluate whether the output still satisfies your data contract.

## 7. Comprehensive Example: Joining Multiple Data Groups

Suppose a program builds a report line made of keyword groups. Each group uses delimiter `", "`, while the overall report uses delimiter `" / "`. When merging groups, each group's joined text becomes one part of the overall report.

**`StringJoinerReportDemo.java`**

```java
import java.util.StringJoiner;

public class StringJoinerReportDemo {
    public static void main(String[] args) {
        StringJoiner basics = new StringJoiner(", ")
                .add("String")
                .add("StringBuilder");

        StringJoiner collections = new StringJoiner(", ")
                .add("List")
                .add("Map");

        StringJoiner result = new StringJoiner(" / ", "Topics: ", ".")
                .setEmptyValue("No topics");

        result.merge(basics);
        result.merge(collections);

        System.out.println("result: " + result);
        System.out.println("basics: " + basics);
        System.out.println("collections: " + collections);

        StringJoiner empty = new StringJoiner(", ")
                .setEmptyValue("Nothing here");

        StringJoiner otherReport = new StringJoiner(" / ", "Topics: ", ".")
                .setEmptyValue("No topics");
        otherReport.merge(empty);

        System.out.println("empty report: " + otherReport);
    }
}
```

```bash
javac StringJoinerReportDemo.java
java StringJoinerReportDemo
```

**Stdout:**

```text
result: Topics: String, StringBuilder / List, Map.
basics: String, StringBuilder
collections: List, Map
empty report: No topics
```

`, ` appears **inside** each group and ` / ` separates **groups** in the report. Prefix `"Topics: "` and suffix `"."` belong to `result`, not to the two source joiners. `empty` has `setEmptyValue("Nothing here")` yet has no elements, so `merge` does not bring `"Nothing here"` into the report, and the report keeps its own emptyValue `"No topics"`.

The example shows that `merge` works well for combining **already-joined segments**, though it does not replace a grouped data model when you still need to query individual elements later.

## 8. Other Important Edge Cases

### 8.1. Delimiter, prefix, suffix, and emptyValue can be empty strings

`new StringJoiner("")` is valid: adding `"A"` then `"B"` produces `"AB"`, with no separator characters. `new StringJoiner(",", "", "")` is also valid. `setEmptyValue("")` is valid and is commonly used when the UI wants to display nothing for an empty list.

The difference is between the **empty string `""`** and **`null`**: the constructor requires non-null delimiter/prefix/suffix; `setEmptyValue(null)` throws `NullPointerException`, whereas `add(null)` appends `"null"`. `merge(null)` is also invalid.

### 8.2. Elements Already Containing the Delimiter Are Not Escaped

If the delimiter is `", "` and an element is `"An, Binh"`, the joiner treats `"An, Binh"` as **one element**, without splitting or escaping its contents:

```java
StringJoiner j = new StringJoiner(", ", "[", "]");
j.add("An, Binh").add("Chi");
// toString(): "[An, Binh, Chi]"
```

In this example, you cannot tell from the output whether the joiner had **two** or **three** elements. `StringJoiner` is **not** a standard CSV builder: it does not add double quotes or escape delimiters, quotes, or newlines. If you need data that can be parsed back unambiguously, use a format and escaper/parser suited for that purpose.

### 8.3. Prefix and Suffix Do Not Have to Be Bracket Pairs

`new StringJoiner(":", "id=", ";")` can produce `"id=A:B;"` after adding `"A"` and `"B"`. The joiner does not validate the semantics of decorative strings; you decide whether the format is valid for your protocol.

### 8.4. `toString()` Is an Immutable String at the Moment of the Call

`StringJoiner` is mutable. After `String snapshot = joiner.toString();`, subsequent `add(...)` calls mutate the joiner, **not** the `String` snapshot object already obtained. Store the snapshot if you want to log it or pass a fixed value to an API; do not expect `snapshot` to update alongside the joiner.

### 8.5. `length()` Is the UTF-16 Code Unit Count, Not the Element Count

`StringJoiner.length()` returns the length of the display string in its current state. If the joiner is still empty and has an `emptyValue`, it uses the **`emptyValue` length**. Once elements are present, it counts prefix, content, delimiters, and suffix.

For example, the emoji 😊 is a non-BMP Unicode code point that takes **two UTF-16 code units**:

**`StringJoinerUnicodeDemo.java`**

```java
import java.util.StringJoiner;

public class StringJoinerUnicodeDemo {
    public static void main(String[] args) {
        String smile = "\uD83D\uDE0A";
        StringJoiner j = new StringJoiner("|", "(", ")")
                .add(smile)
                .add("A");

        String text = j.toString();
        System.out.println("units: " + j.length());
        System.out.println("code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("contains smile: " + text.contains(smile));
    }
}
```

```bash
javac StringJoinerUnicodeDemo.java
java StringJoinerUnicodeDemo
```

**Stdout:**

```text
units: 6
code points: 5
contains smile: true
```

`(`, `|`, `A`, `)` each take one code unit, and the emoji takes two: 6 code units total, yet 5 code points. `StringJoiner` joins character sequences; it **does not count grapheme clusters** or normalize Unicode.

### 8.6. Sharing a Joiner Across Multiple Threads

`StringJoiner` is a mutable object that **provides no internal synchronization guarantees** like a thread-safe container. If multiple threads call `add`/`merge` on **the same instance**, you must manage ownership and synchronization or give each thread its own joiner and combine results in a controlled manner. Nor does `merge` turn multiple business operations into a synchronized transaction.

## 9. Choosing Between StringJoiner, String.join, Collectors.joining, and StringBuilder

These tools are related but differ in level of control:

| Tool | Example | Best suited when |
|---|---|---|
| `StringJoiner` | `new StringJoiner(", ", "[", "]").add("A").add("B")` | Adding incrementally, setting prefix/suffix, merging joined groups, and customizing `emptyValue` |
| `String.join(...)` | `String.join(", ", "A", "B")` | Elements are already on hand and you want quick delimiter joining |
| `Collectors.joining(...)` | `stream.collect(Collectors.joining(", ", "[", "]"))` | Joining `CharSequence` values in a Stream pipeline |
| `StringBuilder` | `builder.append(...)` | Needing full control over building/editing a string, not just delimiter-separated elements |

`String.join` has no incremental `add` or `merge` API on a `StringJoiner` object of your own; `Collectors.joining` produces a final result via a collector, especially well-suited for Streams. When you need a custom empty representation, `StringJoiner.setEmptyValue` is convenient, whereas with `String.join` or a collector you may have to handle the empty rule in surrounding logic.

**Example `JoiningAlternativesDemo.java`:**

```java
import java.util.List;
import java.util.StringJoiner;
import java.util.stream.Collectors;

public class JoiningAlternativesDemo {
    public static void main(String[] args) {
        List<String> values = List.of("A", "B", "C");

        StringJoiner joiner = new StringJoiner(";", "<", ">");
        values.forEach(joiner::add);

        String direct = String.join(";", values);
        String collected = values.stream()
                .collect(Collectors.joining(";", "<", ">"));

        System.out.println("joiner: " + joiner);
        System.out.println("String.join: " + direct);
        System.out.println("collector: " + collected);
    }
}
```

```bash
javac JoiningAlternativesDemo.java
java JoiningAlternativesDemo
```

**Stdout:**

```text
joiner: <A;B;C>
String.join: A;B;C
collector: <A;B;C>
```

Pick the tool based on actual requirements; there is no need to wrap a `StringJoiner` around every two- or three-part concatenation. `StringBuilder` is helpful when mixing structural logic, escaping, formatting, and more complex edits.

## 10. Performance and Input Data

`StringJoiner` avoids manual delimiter tracking and reduces logic bugs when a list has 0, 1, or many elements. Still, do not treat it as automatically optimal for every problem. For very large data volumes, benchmark with a representative workload; the format may call for a streaming serializer or writer instead of assembling everything into one in-memory string.

Key notes:

1. **Avoid manual `String += item + delimiter` in long loops** when `StringJoiner` or an appropriate builder works. That pattern risks trailing-delimiter cleanup bugs or reliance on JVM optimizations.
2. **Choose an explicit null strategy** before calling `add`, especially when data comes from databases, files, HTTP, or user input.
3. **Do not rely on order from an unordered collection.** `StringJoiner` preserves the order in which you call `add`; it does not sort the source.
4. **When merging multiple groups**, delimiters inside each group remain intact. Standardize the structure if the output is consumed by a machine-readable protocol.
5. **Mind UTF-16 lengths**: byte-size limits for files or networks must be measured on the charset-encoded bytes, not via `length()`.
6. **Do not use `setEmptyValue` as a reset mechanism.** To build a new record, instantiate a new joiner.
7. **Do not join untrusted text into special syntaxes without escaping.** `StringJoiner` only concatenates; it does not prevent injection or guarantee valid JSON/CSV/SQL.

## 11. Common Mistakes

| Misconception | Consequence | Fix |
|---|---|---|
| `add(null)` skips the element | Output contains `"null"` | Filter nulls or replace with a contract-defined label |
| `add("")` is the same as adding nothing | Delimiter appears on the next addition; `emptyValue` stops applying | Distinguish an empty element from an empty list |
| `setEmptyValue("(none)")` still adds prefix/suffix | Output differs from expectation | `emptyValue` is the entire output when nothing has been added |
| `setEmptyValue` clears previously added items | Actual contents remain unchanged | Create a new joiner to reset |
| `merge` copies source's prefix/suffix too | Unexpected wrappers inserted or omitted | Use `merge` for inner content; `add(other.toString())` for wrappers included |
| `merge` replaces source's delimiter with target's | Result contains mixed delimiters | Understand the source body is added as one composite part |
| Merging an empty joiner with `emptyValue` merges that `emptyValue` | Output lacks the source label | `emptyValue` is not an element |
| `length()` is the element count | Miscounts, especially with prefixes/emojis | `length()` is the UTF-16 length of the resulting string |
| Delimiters inside an element are escaped automatically | CSV/logs fail to parse back accurately | Escape manually or use an appropriate serializer |
| Treating `toString()` as a live reference to the joiner | Snapshot does not update automatically | Call `toString()` again when a fresh value is needed |
| Treating `StringJoiner` as thread-safe | Races when mutating the same instance concurrently | Manage ownership or synchronize externally |
| Passing `null` to `setEmptyValue`/`merge` | Throws `NullPointerException` | Validate non-null arguments |

## 12. Knowledge Self-Check

Predict the output of the following program before running it:

**`StringJoinerSelfCheck.java`**

```java
import java.util.StringJoiner;

public class StringJoinerSelfCheck {
    public static void main(String[] args) {
        StringJoiner left = new StringJoiner("|", "[", "]")
                .setEmptyValue("EMPTY");

        StringJoiner right = new StringJoiner("-", "{", "}")
                .setEmptyValue("NO ITEMS");

        System.out.println(left);
        left.merge(right);
        System.out.println(left);

        right.add("A").add("B");
        left.merge(right);
        System.out.println(left);

        left.add("");
        System.out.println(left);

        left.setEmptyValue("CHANGED");
        System.out.println(left);

        System.out.println(right);
    }
}
```

```bash
javac StringJoinerSelfCheck.java
java StringJoinerSelfCheck
```

**Stdout:**

```text
EMPTY
EMPTY
[A-B]
[A-B|]
[A-B|]
{A-B}
```

Explanation:

1. `left` has never had `add` called, so `toString()` returns `"EMPTY"`, bypassing `[` and `]` in the custom empty state.
2. `right` has not added anything yet, so `left.merge(right)` adds nothing; `left` remains empty.
3. After `right.add("A").add("B")`, `right`'s inner content inside its shell is `"A-B"`. `left.merge(right)` imports that as one element, displaying `"[A-B]"`.
4. `left.add("")` adds a second, empty element, inserting the target delimiter `|` into the result: `"[A-B|]"`.
5. `setEmptyValue("CHANGED")` has no effect because `left` already has elements.
6. `right` still displays `"{A-B}"`; it does not lose its elements simply because it was merged into `left`.

**Takeaway:** `add` adds one element; `merge` imports **another joiner's inner contents** (excluding the source wrapper); and `setEmptyValue` specifies the **display string when no elements exist**. Establishing clear policies for `null`, empty strings, delimiters inside data, and empty lists keeps multi-part joining with `StringJoiner` accurate and maintainable.
