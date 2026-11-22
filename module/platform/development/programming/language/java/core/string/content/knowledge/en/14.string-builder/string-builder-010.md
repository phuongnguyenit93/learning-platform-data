# `StringBuilder.repeat()` with Code Points or `CharSequence` Since Java 21

## 1. Overview and Objectives

Starting in **Java 21**, `java.lang.StringBuilder` adds two `repeat` methods to **repeatedly append** a Unicode code point or a `CharSequence` to the **end of the existing buffer**:

```java
StringBuilder repeat(int codePoint, int count)
StringBuilder repeat(CharSequence cs, int count)
```

Both methods **mutate the `StringBuilder` object itself**, return the same `this` reference for chaining, and **do not erase** existing data. They differ from `String.repeat(int)`, which returns a new `String` and has existed since Java 11.

Example:

```java
StringBuilder builder = new StringBuilder(">");
builder.repeat('*', 3).repeat("ab", 2);
System.out.println(builder); // >***abab
```

After this lesson, you will be able to:
- Accurately distinguish the two overloads `repeat(int, int)` and `repeat(CharSequence, int)`.
- Repeat a Unicode character/emoji by **code point**, rather than accidentally splitting a surrogate pair.
- Repeat a string or multi-character text segment via `CharSequence`.
- Explain `count`, return value, `length()`, and `null`/negative-count cases.
- Know the required Java version, differences from `String.repeat()`, and pre-Java 21 alternatives.

## 2. Two Overloads and Parameter Meanings

| Method | First Parameter | `count` | Effect |
| --- | --- | --- | --- |
| `repeat(int codePoint, int count)` | Integer value of **one Unicode code point** | Number of copies to append | Appends the UTF-16 representation of that code point `count` times. |
| `repeat(CharSequence cs, int count)` | A character sequence, such as `String`, `StringBuilder`, or `StringBuffer` | Number of copies to append | Appends the entire sequence `cs` `count` times. |

Both:
- Are **instance** methods on `StringBuilder`, not `static` methods.
- Have return type `StringBuilder`, actually **the same builder receiving the call**.
- Append at the **end**, not insert at an arbitrary position.
- Require `count >= 0`; if `count == 0`, no content is appended.
- Are available only since **Java 21**. If a program must compile on Java 17, these two overloads cannot be used directly.

Example:

```java
StringBuilder b = new StringBuilder("Hi");

StringBuilder same = b.repeat('!', 2);

System.out.println(b);           // Hi!!
System.out.println(same == b);   // true
```

**Explanation:** `repeat` does not produce a separate builder; it appends two `!` marks to `b`. Comparing `same == b` yields `true` because both variables reference the same object.

## 3. `repeat(int codePoint, int count)` — Repeating a Code Point

In Java, `int codePoint` is a numeric value representing a Unicode code point. For characters in the BMP (Basic Multilingual Plane), the normal UTF-16 representation is **one** `char` long. For a non-BMP code point such as `🚀` (`U+1F680`), the UTF-16 representation requires **two** `char`s (a surrogate pair).

### 3.1. Example with a BMP Code Point

```java
StringBuilder stars = new StringBuilder();
stars.repeat('*', 5);

System.out.println(stars);          // *****
System.out.println(stars.length()); // 5
```

The literal `'*'` has type `char`, which widens to `int` when calling `repeat(int, int)`. Thus each repetition appends an asterisk.

You can also pass a code point value directly:

```java
StringBuilder letters = new StringBuilder();
letters.repeat(65, 2);

System.out.println(letters); // AA
```

**Very important:** `65` is interpreted as code point `U+0041` (letter `A`), **not** converted into the digit string `"65"`. To repeat the text `"65"`, use the `CharSequence` overload:

```java
System.out.println(
        new StringBuilder().repeat("65", 2)); // 6565
```

### 3.2. Example with a Non-BMP Emoji

```java
StringBuilder emoji = new StringBuilder();
emoji.repeat(0x1F680, 2); // U+1F680: 🚀

System.out.println(emoji);                  // 🚀🚀
System.out.println(emoji.length());         // 4
System.out.println(
        emoji.codePointCount(0, emoji.length())); // 2
```

`0x1F680` is **one code point**, yet when encoded into UTF-16 it takes two code units: high surrogate `U+D83D` and low surrogate `U+DE80`. Repeating twice produces **4 code units** yet only **2 code points**.

Index-by-index representation:

| UTF-16 Index in `"🚀🚀"` | Code Unit Value | Belongs to Code Point |
| ---: | --- | --- |
| 0 | `U+D83D` | 1st `🚀` |
| 1 | `U+DE80` | 1st `🚀` |
| 2 | `U+D83D` | 2nd `🚀` |
| 3 | `U+DE80` | 2nd `🚀` |

If `codePoint` has a one-code-unit UTF-16 representation, length increases by `count`; if it has two code units, length increases by `2 * count` (when memory is sufficient). Therefore, **the repeat count does not always equal the increase in `StringBuilder.length()`**.

### 3.3. Valid Code Points, Surrogates, and Untrusted Input

`repeat(int codePoint, int count)` throws `IllegalArgumentException` if the code point **is not a valid Unicode code point** (outside `U+0000..U+10FFFF`) or if `count` is negative.

A Unicode nuance: surrogate values `U+D800..U+DFFF` are considered **valid code points in numeric range** by `Character.isValidCodePoint`, yet are **not standalone Unicode scalar values**. They should not be used as "complete characters" when generating standard external text. If data comes from users and requires a Unicode scalar value, explicitly exclude the surrogate range:

```java
static boolean isUnicodeScalar(int cp) {
    return cp >= 0 && cp <= 0x10FFFF
            && !(cp >= 0xD800 && cp <= 0xDFFF);
}
```

The snippet above is a **helper method** to place inside a Java class; it is not a standalone program. Adding a scalar value check is an **application input policy**, and should not be confused with the full validation contract of the `repeat` API.

## 4. `repeat(CharSequence cs, int count)` — Repeating an Entire Character Sequence

`CharSequence` is a common interface for character sequences; both `String` and `StringBuilder` implement it. The `repeat(CharSequence, int)` overload takes **the entire passed sequence**, not just one character.

```java
StringBuilder b = new StringBuilder("List: ");
b.repeat("ab", 3);

System.out.println(b);          // List: ababab
System.out.println(b.length()); // 12
```

The prefix `"List: "` is 6 code units; `"ab"` is 2, repeated 3 times adds 6, totaling `length() == 12`.

You can pass a `CharSequence` other than `String`:

```java
CharSequence unit = new StringBuilder("XY");
StringBuilder output = new StringBuilder(">");
output.repeat(unit, 2);

System.out.println(output); // >XYXY
```

Here `unit` is read as a character sequence and `output` receives the repeated copies.

### 4.1. Sequences Containing Emojis

```java
StringBuilder b = new StringBuilder();
b.repeat("🚀", 2);

System.out.println(b);          // 🚀🚀
System.out.println(b.length()); // 4
```

Whether passing a 2-code-unit `CharSequence` or code point `0x1F680`, the resulting text in this example is identical. The difference is **parameter semantics**: the `int` overload takes **one code point**, whereas the `CharSequence` overload takes **a sequence of UTF-16 code units**, which may contain multiple code points.

The `CharSequence` overload does not segment into "visible characters", does not normalize Unicode, and does not automatically fix lone surrogates already present in the source data.

### 4.2. `null` Has Specific Behavior

By the Java 21 contract, when `cs == null`, the method repeatedly appends the **four-letter string `"null"`**:

```java
StringBuilder b = new StringBuilder();
b.repeat((CharSequence) null, 2);

System.out.println(b);          // nullnull
System.out.println(b.length()); // 8
```

This is **the text content `"null"`**, not a `NullPointerException` and not ignoring the input. Use an explicit `null` check if the application requires a different policy:

```java
CharSequence input = null;
StringBuilder b = new StringBuilder();

if (input != null) {
    b.repeat(input, 2);
}
System.out.println(b.length()); // 0
```

You cannot pass `null` for the primitive `int codePoint` parameter; the `null` case above applies only to the `CharSequence` overload.

### 4.3. Mutable `CharSequence` Arguments

`String` is immutable, whereas `StringBuilder` or a custom `CharSequence` can change during execution. If the source sequence is modified concurrently during `repeat`, do not assume the result will be a consistent copy as intended. For mutable sources, create a **stable `String` snapshot** first:

```java
StringBuilder source = new StringBuilder("OK");
String snapshot = source.toString();

StringBuilder dest = new StringBuilder();
dest.repeat(snapshot, 3);

System.out.println(dest); // OKOKOK
```

This keeps what is being repeated clear. If **reading `source` to create the snapshot** itself races with a thread mutating `source`, the application still needs an appropriate synchronization mechanism. `StringBuilder` in general **does not guarantee thread-safety**.

## 5. Zero `count`, Negative `count`, and Empty Sequences

### The `count == 0` Case

Repeating `0` times does not change content:

```java
StringBuilder b = new StringBuilder("seed");

b.repeat("XY", 0);
b.repeat('*', 0);

System.out.println(b); // seed
```

An empty sequence also adds no characters:

```java
StringBuilder b = new StringBuilder("X");
b.repeat("", 100);

System.out.println(b); // X
```

### The `count < 0` Case

A negative repeat count is invalid. Both overloads throw `IllegalArgumentException`:

```java
try {
    new StringBuilder().repeat("ab", -1);
} catch (IllegalArgumentException ex) {
    System.out.println("Negative count rejected"); // Prints this line.
}
```

Similarly, `repeat('A', -1)` is invalid.

### Out-of-Range Code Point Case

```java
try {
    new StringBuilder().repeat(0x110000, 1);
} catch (IllegalArgumentException ex) {
    System.out.println("Invalid code point rejected");
}
```

`U+110000` exceeds the Unicode limit `U+10FFFF` and is therefore invalid. Do not rely on the JVM's specific **error message**; check the exception class and business conditions.

### Excessively Large Repeat Counts

With a very large `count` and a long input, the resulting content may require too much memory or exceed internal array size limits. Validate input bounds before generating data:

```java
static void validateRepeatCount(int count, int max) {
    if (count < 0 || count > max) {
        throw new IllegalArgumentException(
                "count must be in [0, " + max + "]");
    }
}
```

The `max` limit depends on the domain; there is no single fixed number suitable for every application. For systems processing untrusted input, control both the **repeat count** and the **size of the repeated segment**.

## 6. Standalone Runnable Java 21+ Program

Save the following code to `StringBuilderRepeatDemo.java`. **Requires JDK 21 or later** to compile:

```java
public class StringBuilderRepeatDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder(">");
        builder.repeat('*', 3).repeat("ab", 2);
        System.out.println("combined = " + builder);

        StringBuilder rocket = new StringBuilder();
        rocket.repeat(0x1F680, 2);
        System.out.println("rocket = " + rocket);
        System.out.println("UTF-16 units = " + rocket.length());
        System.out.println("code points = "
                + rocket.codePointCount(0, rocket.length()));

        System.out.println("int code point = "
                + new StringBuilder().repeat(65, 2));
        System.out.println("text sequence = "
                + new StringBuilder().repeat("65", 2));

        StringBuilder nulls = new StringBuilder();
        nulls.repeat((CharSequence) null, 2);
        System.out.println("null sequence = " + nulls);

        StringBuilder unchanged = new StringBuilder("seed");
        unchanged.repeat("XY", 0);
        System.out.println("zero count = " + unchanged);

        StringBuilder same = new StringBuilder("x");
        boolean sameReference = same.repeat('!', 2) == same;
        System.out.println("same reference = " + sameReference);
        System.out.println("mutable result = " + same);

        try {
            new StringBuilder().repeat("A", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative count rejected");
        }

        try {
            new StringBuilder().repeat(0x110000, 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid code point rejected");
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 StringBuilderRepeatDemo.java
java StringBuilderRepeatDemo
```

Expected output (Unicode-capable terminal):

```text
combined = >***abab
rocket = 🚀🚀
UTF-16 units = 4
code points = 2
int code point = AA
text sequence = 6565
null sequence = nullnull
zero count = seed
same reference = true
mutable result = x!!
negative count rejected
invalid code point rejected
```

**Explanation:** Both overloads operate directly on the builder called. `repeat(0x1F680, 2)` writes two surrogate pairs so `length()` is 4, while the code point count is 2. `repeat(65, 2)` treats `65` as the code point for `A`, whereas `repeat("65", 2)` duplicates the digit string. `null` becomes `"nullnull"`; `count == 0` leaves state unchanged; each `repeat` call returns the builder itself for chaining.

This program is **not** meant for JDK 17: when compiling with Java 17, the two `StringBuilder.repeat` overloads will not be found in the API.

## 7. Comparing `StringBuilder.repeat` and `String.repeat`

| Property | `StringBuilder.repeat` | `String.repeat` |
| --- | --- | --- |
| Available since | Java **21** | Java **11** |
| Typical call | `builder.repeat("ab", 3)` or `builder.repeat('*', 3)` | `"ab".repeat(3)` |
| Receiver object | Mutable `StringBuilder` | Immutable `String` |
| Return value | Returns **the same `StringBuilder`** with repetitions appended | Returns the resulting `String` |
| Previous content | **Preserved**, with repetitions appended at the end | Repeats the content of the receiver string itself |
| Additional input kinds | `int` code point or `CharSequence` | No code point/CharSequence parameter |
| Supports strings with emojis | Yes, represented in UTF-16 | Yes, repeats string as text |

Comparison example:

```java
String text = "ab";
String repeatedText = text.repeat(3);

StringBuilder builder = new StringBuilder(">");
builder.repeat("ab", 3);

System.out.println(text);         // ab
System.out.println(repeatedText); // ababab
System.out.println(builder);      // >ababab
```

If you need an **immutable `String`** with a fixed repeated pattern and do not need to accumulate other parts, `"ab".repeat(3)` is usually very direct. If you are building a multi-part message in a `StringBuilder`, `builder.repeat("ab", 3)` makes the append intent clear without creating an intermediate string solely to append it.

There is no blanket claim that one approach is always faster than the other. Performance depends on data size, JVM version, memory, and usage context.

## 8. Before Java 21: How to Do It?

If an application must support Java 17, you **cannot directly use** `builder.repeat(codePoint, count)` or `builder.repeat(cs, count)`.

### Approach A — `String.repeat` Then `append` (Java 11+)

```java
StringBuilder builder = new StringBuilder(">");
builder.append("ab".repeat(3));

System.out.println(builder); // >ababab
```

If you need to repeat a non-BMP code point on Java 17, convert it to a string first:

```java
int codePoint = 0x1F680;
String unit = new String(Character.toChars(codePoint));

StringBuilder builder = new StringBuilder();
builder.append(unit.repeat(2));

System.out.println(builder); // 🚀🚀
```

`Character.toChars(int)` converts a valid code point into its corresponding UTF-16 `char[]`; for `🚀`, the array has length 2. This is a clear option when turning a code point value into a repeated string.

### Approach B — Loop Calling `append`

```java
StringBuilder builder = new StringBuilder(">");
CharSequence unit = "ab";

for (int i = 0; i < 3; i++) {
    builder.append(unit);
}

System.out.println(builder); // >ababab
```

For a code point:

```java
StringBuilder builder = new StringBuilder();
int cp = 0x1F680;

for (int i = 0; i < 2; i++) {
    builder.appendCodePoint(cp);
}

System.out.println(builder); // 🚀🚀
```

Both examples work prior to Java 21. Calling `appendCodePoint` is appropriate for Unicode code points, instead of converting a non-BMP code point into a single `char`.

If you must run on both Java 17 and Java 21, use the common `append` / `appendCodePoint` approach or define a Java 17-compatible helper method; do not put a Java 21 method in code assuming an older runtime will substitute it automatically.

## 9. Buffer Capacity and Length After Repeating

`StringBuilder.length()` returns the number of **actual UTF-16 code units currently stored**, unlike `capacity()`, which is the reserved buffer capacity. `repeat` can increase `length()` and may cause the builder to expand its backing storage.

If before repeating `builder.length() == L` and the `CharSequence` has `cs.length() == M`, then on a successful repeat:

```text
newLength = L + M * count
```

For the code point overload with UTF-16 representation length `U` (usually `1` or `2`):

```text
newLength = L + U * count
```

That is the length in UTF-16 `char`s, not visually perceived characters.

Example:

```java
StringBuilder b = new StringBuilder("x");
b.repeat("🚀", 3);

System.out.println(b.length()); // 7 (1 + 3*2)
```

You can call `ensureCapacity(int)` before building a large string to reserve space, but only when size has been computed carefully, overflow is controlled, and there is a practical reason. `ensureCapacity` **does not** change content length, does not allow repeating beyond memory limits, and is not mandatory when using `repeat`.

Example checking expected capacity with `long`:

```java
long requested = (long) unit.length() * count;
long newLength = requested + builder.length();

if (newLength > Integer.MAX_VALUE) {
    throw new IllegalArgumentException("Result too large");
}
```

This is an illustrative snippet to place inside a method where `unit`, `count`, and `builder` are already declared. Using `long` prevents negative overflow when multiplying large counts, though **a result within the `int` limit can still be too large for actual resources**, so the application should enforce a smaller bound when appropriate.

## 10. Common Mistakes

| Misconception | Consequence | How to Handle |
| --- | --- | --- |
| Calling `repeat` on `StringBuilder` while compiling with JDK 17. | Method not found. | Use **JDK 21+** or pre-Java 21 `append`/`appendCodePoint` alternatives. |
| Thinking `repeat(65, 2)` produces `"6565"`. | Actually produces `"AA"`. | Pass `"65"` as a `CharSequence` if you want to repeat digit text. |
| Thinking `repeat(int, count)` repeats only a 16-bit `char`. | Easy to mishandle non-BMP emojis. | The `int` value is treated as a **code point**; check `length()` in UTF-16. |
| Thinking `repeat` returns a new builder and leaves the old one untouched. | Mutates the shared object's content. | Remember the method **mutates the receiver** and returns `this`. |
| Thinking `count = 0` creates one copy. | Actually appends nothing. | Use `count > 0` when repetitions are wanted. |
| Passing a negative repeat count. | `IllegalArgumentException`. | Validate the repeat count. |
| Passing a `null` `CharSequence` expecting it to be skipped. | Appends `"null"` text `count` times. | Define a `null` policy and check explicitly if needed. |
| Repeating a mutable sequence being modified concurrently. | Result is no longer predictable from a stable snapshot. | Use a stable snapshot and synchronization when needed. |
| Confusing `length` with `capacity`. | Misjudges actual data size or allocation capacity. | Use `length()` for content, `capacity()` for buffer reserve. |
| Leaving `count` or `cs` size unbounded. | May exceed resources or internal size limits. | Validate sizes according to domain requirements. |

## 11. Self-Check Exercises

### Exercise 1 — Code Point or Numeric Text?

```java
System.out.println(new StringBuilder().repeat(65, 3));
System.out.println(new StringBuilder().repeat("65", 3));
```

**Answer:**

```text
AAA
656565
```

`65` is code point U+0041; `"65"` is two digit characters repeated three times.

### Exercise 2 — Emoji and Length

```java
StringBuilder b = new StringBuilder();
b.repeat(0x1F680, 3);
System.out.println(b.length());
System.out.println(b.codePointCount(0, b.length()));
```

**Answer:** `6` then `3`. Each `🚀` emoji occupies two UTF-16 code units.

### Exercise 3 — Does It Overwrite Previous Content?

```java
StringBuilder b = new StringBuilder("ABC");
b.repeat("-", 2);
System.out.println(b);
```

**Answer:** `ABC--`. `repeat` **appends to the end**, without erasing `ABC`.

### Exercise 4 — `null` and Repeat Count

```java
StringBuilder b = new StringBuilder("X");
b.repeat((CharSequence) null, 2);
System.out.println(b);
```

**Answer:** `Xnullnull`. The `CharSequence` overload converts `null` into `"null"` and repeats it twice.

### Exercise 5 — Distinguishing Java 17 and 21

You need to repeat `"ab"` four times in a `StringBuilder`, but the project requires Java 17. Can you call `builder.repeat("ab", 4)`?

**Answer:** No. This overload exists since **Java 21**. On Java 17, you can write `builder.append("ab".repeat(4))` or a loop calling `append("ab")`.

### Exercise 6 — Handling Risky Input

An application receives `count` from a public API to generate a text report. What should be done before calling `repeat`?

**Answer:** Check `count >= 0`, enforce a maximum bound per resources/business rules, bound the length of the repeated segment, and avoid overflow when estimating capacity. If using user-supplied code points, validate the Unicode range per requirements and consider excluding surrogates when Unicode scalar values are required.

## 12. Summary

- Since **Java 21**, `StringBuilder` has `repeat(int codePoint, int count)` and `repeat(CharSequence cs, int count)`.
- The `int` overload repeats **a Unicode code point**; the `CharSequence` overload repeats **an entire character sequence**.
- Both **append to the end of the current builder**, return the builder itself, and support chaining.
- `count == 0` leaves content unchanged; `count < 0` throws `IllegalArgumentException`. Out-of-range code points are also rejected.
- A `null` `CharSequence` is repeated as the text `"null"`.
- `StringBuilder.length()` counts **UTF-16 code units**; non-BMP code points take two `char`s per repetition.
- `String.repeat(int)` has existed since Java 11, yet **differs** because it returns a `String` instead of mutating a `StringBuilder`.
- For Java 17, use `String.repeat` + `append` or an `append`/`appendCodePoint` loop.

## References

- [Oracle Java SE 21 — `StringBuilder`: `repeat(int,int)` and `repeat(CharSequence,int)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StringBuilder.html)
- [Oracle Java SE 21 — `String.repeat(int)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#repeat(int))
- [Oracle Java SE 21 — `Character` and Unicode code points](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html)
- [Java Language Specification 21 — Unicode escapes and characters](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html)
