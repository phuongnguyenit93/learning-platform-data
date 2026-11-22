# `StringJoiner` with `delimiter`, `prefix`, and `suffix` in Java

When you need to join multiple values into a single string, you often want to place a **delimiter between elements** and sometimes add a **prefix**/**suffix** wrapping the entire result. For example, from the elements `"Lan"`, `"Mai"`, and `"An"`, the desired output might be `"[Lan, Mai, An]"`.

`java.util.StringJoiner` is designed for this exact case. Instead of manually tracking "have I added the first element yet?" to insert a comma, you declare the joining rule once and then call `add(...)` repeatedly. Specifically, the three concepts **delimiter**, **prefix**, and **suffix** have three completely different roles:

- **`delimiter`:** appears **between** elements; never appears automatically at the start or end of the list.
- **`prefix`:** stands **before the entire** element content.
- **`suffix`:** stands **after the entire** element content.

A `StringJoiner` is a *mutable* object used to accumulate content; the result from `toString()` is a `String` to use or store.

## 1. Initializing a `StringJoiner`

Two commonly used constructors:

```java
StringJoiner joiner = new StringJoiner(", ");
StringJoiner wrapped = new StringJoiner(", ", "[", "]");
```

The full constructor has the signature:

```java
StringJoiner(CharSequence delimiter, CharSequence prefix, CharSequence suffix)
```

The constructor taking only a delimiter is equivalent to using empty strings for prefix and suffix. These configuration parameters **must not be `null`**: passing `null` for delimiter, prefix, or suffix causes the constructor to throw `NullPointerException`.

Examples:

```text
new StringJoiner(", ")         -> "A, B, C"
new StringJoiner(", ", "[", "]") -> "[A, B, C]"
new StringJoiner(" | ", "{", "}") -> "{A | B | C}"
```

This illustrates the result **after** calling `add("A")`, `add("B")`, and `add("C")` on each respective joiner.

`StringJoiner` does not know the list of elements on its own. It only knows how to join the strings you pass sequentially via `add(...)`.

### Example 1: Configure Once, Add Multiple Elements

Create `StringJoinerBasicsDemo.java`:

```java
import java.util.StringJoiner;

public class StringJoinerBasicsDemo {
    public static void main(String[] args) {
        StringJoiner joiner = new StringJoiner(" | ", "{", "}");

        System.out.println(joiner);

        joiner.add("alpha")
              .add("beta")
              .add("gamma");

        System.out.println(joiner);
        System.out.println(joiner.length());
        System.out.println(joiner.toString().equals("{alpha | beta | gamma}"));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac StringJoinerBasicsDemo.java
java StringJoinerBasicsDemo
```

Output:

```text
{}
{alpha | beta | gamma}
22
true
```

When no elements have been added yet, `toString()` returns `prefix + suffix`, which here is `{}`. After three `add` calls, the delimiter `" | "` appears only **between** elements; `{` and `}` each appear once wrapping the entire content.

`length()` returns the number of UTF-16 code units of the **current resulting representation**, equivalent to `toString().length()`. It does not return the count of elements passed to `add`.

## 2. State Before and After Each `add`

With the configuration:

```java
StringJoiner joiner = new StringJoiner(", ", "[", "]");
```

The steps behave as follows:

| Moment | Contents of `joiner.toString()` |
| --- | --- |
| Before calling `add` | `[]` |
| After `add("A")` | `[A]` |
| After `add("B")` | `[A, B]` |
| After `add("C")` | `[A, B, C]` |

**The delimiter never appears before the first element or automatically after the last element.** This is the key advantage over manual concatenation that easily leaves an extra or missing separator:

```java
StringBuilder builder = new StringBuilder("[");
for (String name : names) {
    builder.append(name).append(", ");
}
builder.append("]");
```

The snippet above is illustrative only and assumes `names` already exists. If the list has elements, it can leave a trailing `", "` before `]`. `StringJoiner` handles placing the delimiter **between** elements automatically; you do not need to trim the final delimiter or maintain a "has element" flag.

To build the right mental model, picture `StringJoiner` storing element contents in the order added, then assembling the string with the delimiter and wrapper when requested. **Do not rely on internal JDK memory structures**; what your program relies on is the API contract and the `toString()` result.

## 3. Distinguishing the Outer Wrapper from Individual Element Content

`prefix` and `suffix` wrap **the entire string**. They do not wrap each value added with `add`. The four configurations below all receive the same two elements `"A"` then `"B"`:

| Delimiter | Prefix | Suffix | Result |
| --- | --- | --- | --- |
| `", "` | `""` | `""` | `A, B` |
| `" / "` | `"["` | `"]"` | `[A / B]` |
| `":"` | `"user="` | `";"` | `user=A:B;` |
| `""` | `"<"` | `">"` | `<AB>` |

If the requirement is `[A], [B]`, you must create already-wrapped elements, such as `joiner.add("[" + item + "]")` with delimiter `", "`. Using prefix/suffix `"["` and `"]"` produces `[A, B]`, representing a single group.

**Wrappers are literal text.** `StringJoiner` does not check for matched bracket syntax, does not parse delimiters, and does not escape commas or quotes inside elements. You can create plain text labels with a prefix, but if you need valid CSV, JSON, SQL, or URLs, use an API or encoder built for that format.

## 4. The State When No Elements Have Been Added

Before `add` is called, a joiner with prefix/suffix returns `prefix + suffix`. For example, `new StringJoiner(", ", "[", "]")` returns `"[]"` when `toString()` is called before the first `add`. You can use `setEmptyValue(...)` to replace the **entire** representation when no elements exist; that value is not wrapped again by prefix/suffix.

```java
StringJoiner names = new StringJoiner(" / ", "<", ">");
System.out.println(names); // <>

names.setEmptyValue("(none)");
System.out.println(names); // (none)

names.add("");
System.out.println(names); // <>

names.add("Mai");
System.out.println(names); // < / Mai>
```

`add("")` still records **one element**. Even though the first element has no characters, after that `add` call the result no longer uses `emptyValue`; when `"Mai"` is added, the delimiter appears at the boundary between the two elements. You should distinguish "no elements added yet" from "one empty element added," especially when representing positional data fields.

The lesson `StringJoiner.add, merge, and setEmptyValue` analyzes these state transitions in depth, how `merge` handles an empty source or one that called `add("")`, and the difference between `merge(other)` and `add(other.toString())`. In this lesson, focus on the **output shape** determined by delimiter, prefix, and suffix.

## 5. Complete Program: Joining Display Labels

Save as `JoinerEnvelopeDemo.java` and run with JDK 17 or newer:

```java
import java.util.List;
import java.util.StringJoiner;

public class JoinerEnvelopeDemo {
    public static void main(String[] args) {
        StringJoiner filters = new StringJoiner(" ; ", "Filters: [", "]");
        System.out.println(filters);

        filters.add("status=OPEN").add("level=HIGH");
        System.out.println(filters);

        StringJoiner names = new StringJoiner(" / ", "<", ">");
        names.setEmptyValue("(none)");
        System.out.println(names);
        names.add("").add("Mai");
        System.out.println(names);

        List<String> tags = List.of("java", "core");
        StringJoiner decoratedTags = new StringJoiner(", ");
        for (String tag : tags) {
            decoratedTags.add("[" + tag + "]");
        }
        System.out.println(decoratedTags);
    }
}
```

```bash
javac -encoding UTF-8 JoinerEnvelopeDemo.java
java JoinerEnvelopeDemo
```

Output:

```text
Filters: []
Filters: [status=OPEN ; level=HIGH]
(none)
< / Mai>
[java], [core]
```

`Filters: []` is the representation of a **joiner with no elements yet** using its configured prefix/suffix. After two `add` calls, the delimiter `" ; "` appears exactly once in the middle. The line `< / Mai>` shows that the delimiter can appear right near the start when **the first element is an empty string**; the outer wrapper is still inserted only once. The last line wraps each tag in the element passed to `add`, rather than using the outer joiner's wrapper.

## 6. Limitations and Tool Selection

- The constructor requires delimiter, prefix, and suffix to be **non-`null`**, though `""` is valid. A `null` argument to `add(null)` is rendered as `"null"`; if you want to omit nulls, filter beforehand.
- `StringJoiner.length()` returns the number of UTF-16 code units in the current display text, including wrappers and delimiters (or `emptyValue` when no elements exist); this is neither the element count nor the UTF-8 byte count.
- `StringJoiner` is mutable across `add` calls, but a `String` already returned by `toString()` does not change when the joiner receives new elements.
- When you already have a complete array/`Iterable` and only need a delimiter, `String.join` is shorter. When data is already in a `Stream` with `map`/`filter`, using `Collectors.joining(delimiter, prefix, suffix)` usually makes sense. Choose `StringJoiner` when you need to add parts incrementally and control wrappers as you go.

## 7. Self-Check

**Exercise 1.** Given:

```java
StringJoiner j = new StringJoiner("|", "(", ")");
j.add("A").add("B").add("C");
```

The result of `j.toString()` is `"(A|B|C)"`. Three elements produce two delimiters; prefix and suffix each appear once.

**Exercise 2.** With `new StringJoiner(":", "user=", ";")`, before `add` the result is `"user=;"`, and after `add("A").add("B")` it is `"user=A:B;"`. Prefix/suffix can be arbitrary text, not necessarily a pair of brackets.

**Exercise 3.** A joiner `new StringJoiner("-", "[", "]")` has `setEmptyValue("EMPTY")` set, followed by `add("")` and `add("X")`. The three prints before and after those calls produce:

```text
EMPTY
[]
[-X]
```

`add("")` moves the joiner out of its empty (no-elements) state; `-` is inserted before the next element `"X"`.

## 8. Key Takeaways

`delimiter` sits **between elements**; `prefix` and `suffix` wrap **the entire result**. When no elements have been added, the default output is `prefix + suffix` unless `setEmptyValue` is set. An empty element `""` still counts as added; filtering, escaping, and content validation remain the application's responsibility.

Reference documentation: [Oracle Java SE 17 — StringJoiner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/StringJoiner.html).
