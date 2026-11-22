# appendCodePoint and Non-BMP Data in StringBuilder

When building Java strings from Unicode data, not every "character" fits in a single `char`. A code point outside the **Basic Multilingual Plane (BMP)**, such as the emoji 😊 (`U+1F60A`), requires **two UTF-16 code units**. If you cast that code point to `char` and call `StringBuilder.append(char)`, the data is truncated. `StringBuilder.appendCodePoint(int)` is the API designed for adding **a single Unicode code point** to the string builder, using one or two UTF-16 code units depending on the code point value.

The goal of this lesson is to understand the mechanism, know when to use `appendCodePoint` instead of `append`, distinguish non-BMP data from surrogate pairs, validate input values, and avoid confusing code points with display character clusters (*grapheme clusters*).

## 1. BMP, Code Points, `char`, and UTF-16

A **Unicode code point** is a numeric value denoted `U+XXXX`, within the range `U+0000` to `U+10FFFF`. Java typically represents code point values using `int`. Java's `char` holds only **a single 16-bit UTF-16 code unit**, so it cannot directly hold every Unicode code point.

Unicode divides the code point space into *planes*. The **BMP**, or Plane 0, covers `U+0000`–`U+FFFF`. The remaining planes contain code points greater than `U+FFFF`, called **supplementary code points**. Some emojis, historical scripts, musical symbols, and mathematical characters belong to the supplementary planes.

In UTF-16:

- A BMP code point **not in the surrogate range** (`U+D800`–`U+DFFF`) is represented by **one code unit**.
- A non-BMP code point (`U+10000`–`U+10FFFF`) is represented by **two code units**: a *high surrogate* (`0xD800`–`0xDBFF`) and a *low surrogate* (`0xDC00`–`0xDFFF`).
- The surrogate range is reserved specifically for UTF-16 encoding. A value such as `U+D800` is not a valid **Unicode scalar value** to stand alone as a complete Unicode text character.

Examples:

| Code point | Representation | UTF-16 code units | Notes |
|---|---|---:|---|
| `U+0041` | `A` | 1 | Latin letter in the BMP |
| `U+00E9` | `é` | 1 | Precomposed character in the BMP |
| `U+1F60A` | 😊 | 2 | Non-BMP emoji: `D83D DE0A` |
| `U+1F1FB` | Regional indicator V | 2 | One half of the 🇻🇳 flag |
| `U+1F1F3` | Regional indicator N | 2 | The other half of the 🇻🇳 flag |

One flag emoji 🇻🇳 has **two non-BMP code points**, totaling **four UTF-16 code units**, yet is usually rendered as **one grapheme cluster**. Thus: **code unit count ≠ code point count ≠ user-perceived character count**.

## 2. What Does `StringBuilder.appendCodePoint(int)` Do?

Method signature:

```java
StringBuilder appendCodePoint(int codePoint)
```

This is an illustrative API signature; `StringBuilder` actually returns the builder itself to support method chaining such as `builder.appendCodePoint(cp).append("...")`.

For a code point value within the API's valid range:

1. If it belongs to the BMP (including lone surrogate codes at the API level), the method appends **one `char` code unit**.
2. If it is a non-BMP code point, the method converts it into a **UTF-16 surrogate pair** and appends **two code units in the proper order**.
3. The builder's length increases by the **number of code units** appended. The builder's content changes; the method returns a reference to **the same builder**.
4. If the value is outside the Unicode code point range accepted by Java, such as `-1` or `0x110000`, the method throws `IllegalArgumentException`.

Therefore, starting with an empty builder:

```java
StringBuilder builder = new StringBuilder();
builder.appendCodePoint(0x41);       // A: appends 1 char
builder.appendCodePoint(0x1F60A);    // 😊: appends 2 chars
```

After both calls, `builder.length() == 3` whereas `builder.codePointCount(0, builder.length()) == 2`. The length returned by `StringBuilder.length()` is the number of **UTF-16 code units**, not the number of code points.

`appendCodePoint` **does not perform Unicode normalization**, does not check grapheme cluster boundaries, and does not change letter case. Its job is to append *a single code point value* according to UTF-16 rules.

## 3. Complete Example: Appending Non-BMP Code Points

Save as **`AppendCodePointDemo.java`**:

```java
public class AppendCodePointDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder();
        builder.append('A')
                .appendCodePoint(0x1F60A)
                .append('B');

        System.out.println("UTF-16 units: " + builder.length());
        System.out.println("Code points: "
                + builder.codePointCount(0, builder.length()));

        System.out.printf("charAt(1): U+%04X%n",
                (int) builder.charAt(1));
        System.out.printf("charAt(2): U+%04X%n",
                (int) builder.charAt(2));
        System.out.printf("codePointAt(1): U+%X%n",
                builder.codePointAt(1));

        System.out.println("valid surrogate pair: "
                + Character.isSurrogatePair(
                        builder.charAt(1), builder.charAt(2)));

        String expected = "A\uD83D\uDE0AB";
        System.out.println("content matches: "
                + builder.toString().equals(expected));
    }
}
```

Compile and run on JDK 17+:

```bash
javac AppendCodePointDemo.java
java AppendCodePointDemo
```

**Stdout:**

```text
UTF-16 units: 4
Code points: 3
charAt(1): U+D83D
charAt(2): U+DE0A
codePointAt(1): U+1F60A
valid surrogate pair: true
content matches: true
```

Explanation:

- `A` takes one code unit, the emoji takes two, and `B` takes one: total `length() == 4`.
- `codePointCount(...)` recognizes the valid surrogate pair and counts the emoji as **one code point**, so the total code point count is 3.
- `charAt(1)` and `charAt(2)` return the two UTF-16 halves `D83D` and `DE0A` respectively. Neither is a separate emoji on its own.
- `codePointAt(1)` reads the code point starting at UTF-16 offset `1`, returning `U+1F60A`.
- `toString()` produces a string containing the exact code units that were appended. Compared to a literal written with the surrogate pair `"\uD83D\uDE0A"`, the contents are equal according to `String.equals()`.

**Do not confuse indices:** the `index` parameter of `codePointAt(index)` is also a **UTF-16 code unit offset**. It is not "the index-th code point". If you need to advance by code points, see `offsetByCodePoints(...)` later in the lesson.

## 4. Distinguishing `append(int)`, `append(char)`, and `appendCodePoint(int)`

The three methods have **different meanings**. When an `int` variable holds a code point, this is a very common mistake:

```java
int smile = 0x1F60A;

new StringBuilder().append(smile);          // appends the digits "128522"
new StringBuilder().append((char) smile);   // loses the upper bits of the int
new StringBuilder().appendCodePoint(smile); // appends the UTF-16 units of emoji 😊
```

This is an illustrative snippet. `append(int)` converts the integer into **decimal text**. `append((char) smile)` performs a narrowing cast, keeping only the lower 16 bits and failing to represent the full `U+1F60A` code point. Only `appendCodePoint(smile)` preserves the non-BMP code point properly.

Runnable example **`AppendOverloadsDemo.java`**:

```java
public class AppendOverloadsDemo {
    public static void main(String[] args) {
        int smile = 0x1F60A;

        StringBuilder asNumber = new StringBuilder().append(smile);
        StringBuilder asChar = new StringBuilder().append((char) smile);
        StringBuilder asCodePoint = new StringBuilder()
                .appendCodePoint(smile);

        System.out.println("append(int): " + asNumber);
        System.out.println("append(char) units: " + asChar.length());
        System.out.printf("append(char) value: U+%04X%n",
                (int) asChar.charAt(0));
        System.out.println("appendCodePoint units: "
                + asCodePoint.length());
        System.out.printf("appendCodePoint value: U+%X%n",
                asCodePoint.codePointAt(0));
        System.out.println("correct smile: "
                + asCodePoint.toString().equals("\uD83D\uDE0A"));
    }
}
```

```bash
javac AppendOverloadsDemo.java
java AppendOverloadsDemo
```

**Stdout:**

```text
append(int): 128522
append(char) units: 1
append(char) value: U+F60A
appendCodePoint units: 2
appendCodePoint value: U+1F60A
correct smile: true
```

The discrepancy is **data loss**, not just a display difference. After casting `(char) smile`, the value `U+1F60A` has become `U+F60A` and cannot be recovered by `append`.

If you already have a **complete and valid `String`** containing an emoji, `builder.append(string)` also preserves all of its code units. `appendCodePoint` is most useful when **the input is an `int` representing a code point**, such as results from iterating `codePoints()` or raw Unicode code point data.

## 5. Input Validation and Lone Surrogates

`Character.isValidCodePoint(int)` checks whether a numeric value lies in the range `U+0000` to `U+10FFFF`. However, **this range includes the surrogate codes `U+D800`–`U+DFFF`**, so a `true` result from `isValidCodePoint` **is not sufficient** to conclude that the input is a *Unicode scalar value* able to stand alone in valid text.

Distinguish:

- **Code point within Java's valid range:** `0 <= cp <= 0x10FFFF`. `Character.isValidCodePoint(cp)` checks this.
- **Unicode scalar value:** a valid code point **not in the surrogate range** `0xD800..0xDFFF`.
- **Assigned code point:** yet another concept; not every scalar value has a character assigned in the JDK's Unicode version.
- **Valid grapheme cluster for UI:** requires Unicode segmentation rules, and may consist of multiple scalar values.

`appendCodePoint` accepts surrogate values within Java's code point range and will append a lone surrogate `char` if you pass `0xD800`. Structurally `StringBuilder` can hold that code unit, but that is **not** how to construct a valid Unicode scalar sequence. When data comes from external systems, validate it according to your intended use.

Example **`SafeCodePointDemo.java`**:

```java
public class SafeCodePointDemo {
    private static boolean isScalarValue(int codePoint) {
        return Character.isValidCodePoint(codePoint)
                && !(codePoint >= 0xD800 && codePoint <= 0xDFFF);
    }

    private static void appendScalar(StringBuilder builder, int codePoint) {
        if (!isScalarValue(codePoint)) {
            throw new IllegalArgumentException(
                    "Not a Unicode scalar value");
        }
        builder.appendCodePoint(codePoint);
    }

    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder();

        appendScalar(builder, 0x41);
        appendScalar(builder, 0x1F60A);

        System.out.println("units: " + builder.length());
        System.out.println("points: "
                + builder.codePointCount(0, builder.length()));

        System.out.println("surrogate in numeric range: "
                + Character.isValidCodePoint(0xD800));
        System.out.println("surrogate accepted as scalar: "
                + isScalarValue(0xD800));

        try {
            appendScalar(builder, 0xD800);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected lone surrogate");
        }

        try {
            builder.appendCodePoint(0x110000);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected out-of-range value");
        }

        System.out.println("builder unchanged: "
                + builder.toString().equals("A\uD83D\uDE0A"));
    }
}
```

```bash
javac SafeCodePointDemo.java
java SafeCodePointDemo
```

**Stdout:**

```text
units: 3
points: 2
surrogate in numeric range: true
surrogate accepted as scalar: false
rejected lone surrogate
rejected out-of-range value
builder unchanged: true
```

`appendScalar` is a **custom wrapper function** designed to enforce a stricter input contract than `appendCodePoint`. Java does not automatically enforce a "no surrogate code points" policy for all string construction. If you must handle data containing lone surrogates, decide explicitly: reject it, replace with the replacement character `U+FFFD`, or preserve the code unit for a specific technical purpose.

**Note:** `Character.isValidCodePoint` also does not check whether a character is "assigned", nor does it validate a grapheme cluster or language-specific text content.

## 6. Building Strings from a Code Point Array or `codePoints()` Stream

A common use case is receiving data as Unicode integers and constructing text. When the input list consists of validated *scalar values*, you can append each value:

```java
int[] codePoints = {0x41, 0x1F60A, 0x42};
StringBuilder builder = new StringBuilder();
for (int cp : codePoints) {
    builder.appendCodePoint(cp);
}
String text = builder.toString();
```

This is an illustrative snippet; the resulting `text` is `"A😊B"` and has `length() == 4`. If you need a constructor rather than a builder, `new String(int[] codePoints, int offset, int count)` also accepts code point data and encodes it to UTF-16 per the API. A builder is beneficial when data arrives incrementally or needs to combine multiple kinds of elements.

With `String.codePoints()`, each stream value is an `int` representing a code point per Java rules. You can rebuild the string with `appendCodePoint`. Note, however, that when the source contains a **lone surrogate**, `codePoints()` can still yield that lone code unit as an element. Rebuilding faithfully preserves the source data, which does not imply the source was a complete Unicode scalar sequence.

**Runnable example `CodePointRoundTripDemo.java`:**

```java
public class CodePointRoundTripDemo {
    public static void main(String[] args) {
        String original = "A\uD83D\uDE0AB";

        StringBuilder rebuilt = new StringBuilder();
        original.codePoints().forEach(rebuilt::appendCodePoint);

        System.out.println("same content: "
                + original.contentEquals(rebuilt));
        System.out.println("UTF-16 units: " + rebuilt.length());
        System.out.println("code points: "
                + rebuilt.codePointCount(0, rebuilt.length()));

        int index = rebuilt.offsetByCodePoints(1, 1);
        System.out.println("after emoji offset: " + index);
        System.out.printf("code point at 1: U+%X%n",
                rebuilt.codePointAt(1));
    }
}
```

```bash
javac CodePointRoundTripDemo.java
java CodePointRoundTripDemo
```

**Stdout:**

```text
same content: true
UTF-16 units: 4
code points: 3
after emoji offset: 3
code point at 1: U+1F60A
```

In this example, `offsetByCodePoints(1, 1)` starts at UTF-16 offset `1` (right before the emoji), advances past one code point, and returns offset `3` (right after the surrogate pair). Calling `substring(1, 2)` would split the emoji in half, whereas `substring(1, 3)` captures it completely.

Java method reference note: using the method reference `rebuilt::appendCodePoint` as an `IntConsumer` is valid; even though the method returns `StringBuilder`, the return value is ignored by the consumer interface.

## 7. Appending Multiple Code Points May Still Form Just One Grapheme Cluster

`appendCodePoint` processes **one code point at a time**, and does not create or segment "one visible character" in the UI sense. Several important combinations:

- The letter `e` (`U+0065`) and a combining acute accent (`U+0301`) are **two code points**, yet are normally grouped into **one extended grapheme cluster**.
- The flag 🇻🇳 consists of two **regional indicators** `U+1F1FB` and `U+1F1F3`, totaling two code points and four UTF-16 code units, yet **one cluster** under segmentation rules.
- The family emoji 👨‍👩‍👧‍👦 consists of four person emojis and three `U+200D` (*Zero Width Joiner*) characters, totaling seven code points and 11 UTF-16 code units, typically forming one grapheme cluster.

You can build these combinations with consecutive `appendCodePoint(...)` calls. The method does not merge seven code points into one code point; it simply encodes each value and appends the code units.

Example **`GraphemeBuilderDemo.java`**:

```java
import java.util.regex.Pattern;

public class GraphemeBuilderDemo {
    private static final Pattern GRAPHEME = Pattern.compile("\\X");

    private static void show(String name, StringBuilder builder) {
        long clusters = GRAPHEME.matcher(builder).results().count();
        System.out.println(name
                + ": units=" + builder.length()
                + ", points=" + builder.codePointCount(0, builder.length())
                + ", clusters=" + clusters);
    }

    public static void main(String[] args) {
        StringBuilder accented = new StringBuilder();
        accented.appendCodePoint(0x65).appendCodePoint(0x301);

        StringBuilder flag = new StringBuilder();
        flag.appendCodePoint(0x1F1FB).appendCodePoint(0x1F1F3);

        StringBuilder family = new StringBuilder();
        int[] codePoints = {
                0x1F468, 0x200D, 0x1F469, 0x200D,
                0x1F467, 0x200D, 0x1F466
        };
        for (int cp : codePoints) {
            family.appendCodePoint(cp);
        }

        show("accented", accented);
        show("flag", flag);
        show("family", family);
    }
}
```

```bash
javac GraphemeBuilderDemo.java
java GraphemeBuilderDemo
```

**Stdout (Java 17+):**

```text
accented: units=2, points=2, clusters=1
flag: units=4, points=2, clusters=1
family: units=11, points=7, clusters=1
```

Java regex `\X` supports **Unicode extended grapheme cluster** segmentation. In a Java string literal, you must write `"\\X"` so the regex engine receives `\X`. Segmentation results can be affected by the Unicode data version in the JDK, especially for newer emojis; meanwhile, the code unit and code point counts in the examples above do not depend on fonts.

Even a single cluster does not necessarily render as **a single glyph**, because fonts and rendering platforms control glyph shaping. When designing string truncation by "user-perceived characters", use grapheme cluster boundaries from an appropriate library rather than using `appendCodePoint` or `length()` as a display-character counter.

## 8. Avoiding Breaking Surrogate Pairs When Editing `StringBuilder`

`StringBuilder` is **mutable**: you can insert, delete, replace, or reverse its content. However, many builder editing APIs still operate on **UTF-16 code unit indices**, so they can create lone surrogates if applied inside a pair.

Consider a builder containing `"A😊B"` with code units at offsets:

```text
Offset: 0      1        2       3
        A   high-D83D low-DE0A   B
UTF-16 boundaries: 0 | 1 | 2 | 3 | 4
```

- `builder.delete(1, 3)` deletes both emoji code units, keeping `"AB"`.
- `builder.delete(1, 2)` deletes only the high surrogate, leaving a lone low surrogate.
- `builder.setCharAt(1, 'X')` replaces the high surrogate with `X`, also leaving a lone low surrogate.
- `builder.insert(2, "...")` can insert between the high and low surrogates; avoid placing insertion points there if data must remain valid.

**Example `BuilderBoundaryDemo.java`:**

```java
public class BuilderBoundaryDemo {
    public static void main(String[] args) {
        StringBuilder safe = new StringBuilder("A\uD83D\uDE0AB");
        safe.delete(1, 3);
        System.out.println("safe result: " + safe);

        StringBuilder broken = new StringBuilder("A\uD83D\uDE0AB");
        broken.delete(1, 2);

        System.out.println("broken units: " + broken.length());
        System.out.println("lone low surrogate: "
                + Character.isLowSurrogate(broken.charAt(1)));

        StringBuilder original = new StringBuilder("A\uD83D\uDE0AB");
        int end = original.offsetByCodePoints(1, 1);
        original.delete(1, end);
        System.out.println("code point deletion: " + original);
    }
}
```

```bash
javac BuilderBoundaryDemo.java
java BuilderBoundaryDemo
```

**Stdout:**

```text
safe result: AB
broken units: 3
lone low surrogate: true
code point deletion: AB
```

`offsetByCodePoints(1, 1)` moves the position from offset 1 past one full code point, giving end = 3 in this example. This is a better choice for operations slicing **by code point**, though it can still split between a base letter and a combining mark. If you need to preserve **grapheme clusters**, determine grapheme boundaries before editing.

**About `reverse()`:** `StringBuilder.reverse()` has special handling to keep the proper order within valid surrogate pairs, but that does not mean reversing always preserves multi-code-point grapheme clusters (such as e + combining mark, or composite emojis). Do not use `reverse()` as a "user-perceived character" reverser across all writing systems.

## 9. Length Limits, Capacity, and Input Handling

Because a builder stores data as UTF-16 at the API level:

- `length()` and `capacity()` measure **numbers of `char` code units**, not code points, grapheme clusters, or UTF-8 output bytes.
- `appendCodePoint(0x1F60A)` increases `length()` by **2**, not 1.
- `ensureCapacity(n)` asks the builder to prepare a minimum capacity in **UTF-16 code units**; it does not increase `length()` and does not automatically add content.
- If you need a limit of "at most N code points", checking `builder.length() <= N` alone is wrong. With non-BMP text, `length` can exceed the code point count.
- If limiting bytes for a protocol or file, encode with the target charset (for example UTF-8) and measure the byte count. Byte count differs from code units, code points, and graphemes.

Inputs from external sources can be negative, exceed `U+10FFFF`, be lone surrogates, or be unassigned code points in the current Unicode version. The acceptance policy must be defined by the **application's contract**. This lesson used `appendScalar` to reject lone surrogates, whereas a raw UTF-16 data processor might need a different policy to preserve information.

### Choosing an API by Data Shape

| Available Input | Appropriate API | Notes |
|---|---|---|
| A code point as an `int` | `appendCodePoint(cp)` | Validate scalar value if building valid Unicode text |
| A UTF-16 code unit as a `char` | `append(ch)` | May be one half of a surrogate pair |
| A complete `String` | `append(text)` | Preserves the string's code unit sequence |
| A UTF-16 `char[]` array | `append(chars)` | Responsible for protecting surrogate pairs if source may be invalid |
| An `int[]` code point array | Loop `appendCodePoint(cp)`, or `String(int[],...)` constructor | Do not cast an `int[]` array directly to `char[]` |
| A `String.codePoints()` stream | Loop `appendCodePoint` or `new String(codePoints, ...)` | Source may contain lone surrogates; a validation policy is needed |
| Need to edit by visible character | Segment graphemes first | One cluster can contain multiple code points |

For builders used across multiple threads, also keep in mind that `StringBuilder` is **not synchronized**; synchronize access or choose an appropriate structure if a mutable builder is actually shared. This is independent of the Unicode behavior of `appendCodePoint`.

## 10. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
|---|---|---|
| `builder.append(0x1F60A)` to add an emoji | Appends the digit string `"128522"` | `appendCodePoint(0x1F60A)` |
| `builder.append((char) 0x1F60A)` | Keeps only lower 16 bits, losing the non-BMP code point | Keep `int` and use `appendCodePoint` |
| Assuming `appendCodePoint` always increments length by 1 | Miscounts length when supplementary code points exist | Non-BMP code points add 2 code units |
| Thinking `Character.isValidCodePoint` checks for scalar values | Surrogate `U+D800` is still considered within the code point range | Explicitly exclude `0xD800..0xDFFF` if data requires scalars |
| Checking only `cp >= 0` | Values `cp > 0x10FFFF` throw `IllegalArgumentException` | Validate upper bound and surrogates per policy |
| Accessing `charAt(i)` as a code point | May read only a high or low surrogate | Use `codePointAt(i)` and `offsetByCodePoints(...)` |
| Calling `delete(i, i+1)` to delete an emoji | May delete only half of a surrogate pair | Compute proper code point/grapheme boundaries |
| Treating two flag code points as two user-perceived characters | A flag can be one grapheme cluster | Segment graphemes using Unicode rules |
| Thinking `appendCodePoint` automatically normalizes to NFC | The code point sequence is appended verbatim | Use `Normalizer` separately when required |
| Bounding content by `capacity` or relying on `length` to count code points | Miscounts units | Clearly define UTF-16 units, code points, clusters, or bytes |
| Thinking a builder holding lone surrogates will immediately throw | `StringBuilder` allows code unit sequences that do not form valid Unicode scalar text | Validate/preserve/replace per input contract |

## 11. Self-Check

Predict the output of **`AppendCodePointSelfCheck.java`** before running it:

```java
public class AppendCodePointSelfCheck {
    public static void main(String[] args) {
        int cp = 0x1F60A;

        StringBuilder a = new StringBuilder();
        a.appendCodePoint(cp);
        a.appendCodePoint(0x41);

        System.out.println(a.length());
        System.out.println(a.codePointCount(0, a.length()));
        System.out.println(Character.isSupplementaryCodePoint(cp));
        System.out.println(a.codePointAt(0) == cp);

        StringBuilder b = new StringBuilder();
        b.append(cp);
        System.out.println(b.toString());

        StringBuilder c = new StringBuilder();
        c.append((char) cp);
        System.out.println(c.length());
        System.out.println(c.codePointAt(0) == cp);
    }
}
```

```bash
javac AppendCodePointSelfCheck.java
java AppendCodePointSelfCheck
```

**Stdout:**

```text
3
2
true
true
128522
1
false
```

Explanation: `a` holds the emoji (two code units, one code point) and the letter `A` (one code unit, one code point). `b.append(cp)` selects the integer overload and converts it to digits. `c.append((char) cp)` truncates the upper bits of the `int`, so the read-back value cannot equal `U+1F60A`.

**Three questions when choosing an API:**

1. Is the value in hand **a UTF-16 `char`**, **an `int` code point**, or **a complete string**?
2. Could the value be non-BMP or a lone surrogate, and does the application contract require a valid Unicode scalar sequence?
3. Does the problem count, bound, or delete by **code unit**, **code point**, **grapheme cluster**, or **encoded byte** count?

When the input is a valid code point and the goal is building a Unicode string, `StringBuilder.appendCodePoint(int)` properly encodes non-BMP values into surrogate pairs. The rest of correctness lies in validating inputs, choosing operation boundaries, and accurately defining "character" for your requirements.
