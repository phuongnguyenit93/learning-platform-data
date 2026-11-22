# Creating IntStream from String.chars and String.codePoints

When working with strings in the **Java Stream API**, there are two very convenient methods for feeding character data into a pipeline: `String.chars()` and `String.codePoints()`. Both return an `IntStream`, yet they **differ in data unit**: one traverses UTF-16 *code units*, while the other traverses Unicode *code points*.

This lesson belongs to the **Streams from Existing Data** section of the **JAVA_STREAM_API** module. Beyond creating Stream sources, we will practice `filter`, `map`, `collect`, counting, and reconstructing strings; at the same time, we will identify boundaries around Unicode, lazy pipelines, state, and performance. The distinction between code unit, code point, and user-perceived character directly determines whether text processing is correct.

## 1. Why Are Two Ways to Traverse Strings Needed?

Java represents the contents of a `String` according to UTF-16 rules at the API level. Most common characters, such as `A`, `7`, `ắ`, or `中`, can be represented by **one** UTF-16 code unit. Symbols in supplementary Unicode planes, such as the emoji `😀` (U+1F600), require a **surrogate pair** consisting of two UTF-16 code units.

Therefore, three concepts must be kept distinct:

| Concept | Meaning | Example with `😀` |
| --- | --- | --- |
| UTF-16 code unit | A 16-bit value represented in Java via `char` | Two values: `0xD83D` and `0xDE00` |
| Unicode code point | A value assigned by Unicode to a symbol or text component | One value: `U+1F600` |
| Grapheme cluster | A unit a user may perceive as a single character | Typically seen as one emoji `😀` |

One code point **does not always equal** one grapheme cluster. For example, `e` combined with an acute accent can be represented by two code points, while a reader sees one accented character. Emoji joined by a zero-width joiner (*ZWJ*) can also consist of multiple code points yet render as a single glyph.

In Java:

- `String.length()` counts **UTF-16 code units**.
- `String.chars()` emits each **UTF-16 code unit** into an `IntStream` as an `int`.
- `String.codePoints()` emits each **code point** into an `IntStream`, combining valid surrogate pairs into one value.
- `String.codePointCount(beginIndex, endIndex)` counts the number of code points within a UTF-16 index range.

These APIs have been available since Java 8 via the `CharSequence` interface. Complete examples in this lesson use Java 17 for convenience with `Stream.toList()`.

## 2. `String.chars()`: Traversing Each UTF-16 Code Unit

`chars()` creates an `IntStream` from a string. Each element is a `char` value zero-extended to an unsigned `int` (range `0` to `65535`). For emojis or supplementary symbols, **each half of the surrogate pair** is emitted into the stream as a separate number.

Directly runnable example:

```java
import java.util.Arrays;
import java.util.stream.IntStream;

public class StringCharsDemo {
    public static void main(String[] args) {
        String text = "A😀B";

        try (IntStream units = text.chars()) {
            System.out.println(Arrays.toString(units.toArray()));
        }

        System.out.println(text.length());
    }
}
```

Output:

```text
[65, 55357, 56832, 66]
4
```

Explanation:

| UTF-16 code unit position | Representation | Decimal value |
| --- | --- | ---: |
| 0 | `A` (`U+0041`) | 65 |
| 1 | High surrogate (`0xD83D`) | 55357 |
| 2 | Low surrogate (`0xDE00`) | 56832 |
| 3 | `B` (`U+0042`) | 66 |

The two values `55357` and `56832` work together to represent the emoji `😀`. If you use `chars()` to count "characters" in this string, the result is **4 code units**, even though we see three simple symbols: `A`, `😀`, and `B`.

### 2.1. When to Use `chars()`?

`chars()` is useful when business logic genuinely operates on **UTF-16 code units** or when the data is guaranteed to use only basic characters, such as an ASCII code string defined by a protocol.

For example, checking whether a product code follows the rule **only uppercase unaccented Latin letters and ASCII digits**:

```java
String code = "AB12Z9";

boolean validAsciiCode = !code.isEmpty()
    && code.chars().allMatch(c ->
        (c >= 'A' && c <= 'Z')
        || (c >= '0' && c <= '9')
    );

System.out.println(validAsciiCode); // true
```

The requirement scope is intentionally restricted to ASCII; therefore iterating by `char` does not distort the meaning. If the input contains non-ASCII letters or emojis, the expression rejects it according to the example's policy.

Conversely, when a problem asks to **process all Unicode letters** or "traverse each Unicode symbol", `chars()` can split a supplementary-plane symbol in half and make the check fail.

## 3. `String.codePoints()`: Traversing by Unicode Code Point

`codePoints()` also returns an `IntStream`, but when it encounters a **valid high surrogate immediately followed by a low surrogate**, it combines the two code units into one code point.

```java
import java.util.Arrays;

public class StringCodePointsDemo {
    public static void main(String[] args) {
        String text = "A😀B";

        System.out.println(Arrays.toString(text.chars().toArray()));
        System.out.println(Arrays.toString(text.codePoints().toArray()));

        System.out.println("length = " + text.length());
        System.out.println("chars count = " + text.chars().count());
        System.out.println("codePoints count = " + text.codePoints().count());
        System.out.println(
            "codePointCount = " + text.codePointCount(0, text.length())
        );
    }
}
```

Output:

```text
[65, 55357, 56832, 66]
[65, 128512, 66]
length = 4
chars count = 4
codePoints count = 3
codePointCount = 3
```

The number `128512` equals `0x1F600`, which is the code point of `😀`. Thus, for this string, `codePoints().count()` is more appropriate if the goal is to **count Unicode code points**.

Be precise with terminology: `codePoints().count()` counts **code points**, and does not guarantee counting the exact number of user-perceived characters. Combining marks and multi-component emojis are examined in section 7.

### 3.1. Comparing the Two Methods

| Criterion | `chars()` | `codePoints()` |
| --- | --- | --- |
| Return type | `IntStream` | `IntStream` |
| Unit emitted | One UTF-16 code unit | One Unicode code point for valid surrogate pairs |
| `A` | One element `65` | One element `65` |
| `😀` | Two elements `55357`, `56832` | One element `128512` |
| Automatically merges combining marks into display characters? | No | No |
| Best suited for | `char`/UTF-16 processing or explicit ASCII protocols | Filtering, classifying, and transforming Unicode code points |
| Needs a terminal operation to traverse? | Yes | Yes |

**Note:** Basic non-ASCII characters like `ê` usually occupy only one UTF-16 code unit, but that does not make `chars()` a general-purpose Unicode tool. The difference shows most clearly with supplementary code points.

## 4. Applying `filter`, `map`, and Aggregations on `IntStream`

Because both methods return `IntStream`, they support primitive-specialized operations such as `filter`, `map`, `mapToObj`, `distinct`, `count`, `anyMatch`, `toArray`, and `collect`.

### 4.1. Counting Unicode Letters and Digits

Given a string containing accented Latin letters, digits, and an emoji, we can use `Character.isLetter(int)` and `Character.isDigit(int)` on each code point:

```java
String input = "Học Java 17 😀";

long letters = input.codePoints()
    .filter(Character::isLetter)
    .count();

long digits = input.codePoints()
    .filter(Character::isDigit)
    .count();

boolean containsEmojiCodePoint = input.codePoints()
    .anyMatch(cp -> cp == 0x1F600);

System.out.println(letters);                  // 7
System.out.println(digits);                   // 2
System.out.println(containsEmojiCodePoint);   // true
```

Letter count explanation: `Học` has 3 letters; `Java` has 4, totaling **7**. The two digits are `1` and `7`. The emoji is not counted as a letter or digit.

`Character.isLetter(int)` operates on code points; with `chars()`, a Unicode letter in a supplementary plane would be split into surrogates and might **not** be recognized accurately.

### 4.2. Converting a Set of Code Points into a List

Suppose we want each code point as an independent `String`, for presentation or further processing:

```java
import java.util.List;

String text = "A😀B";

List<String> symbols = text.codePoints()
    .mapToObj(cp -> new String(Character.toChars(cp)))
    .toList();

System.out.println(symbols); // [A, 😀, B]
```

`Character.toChars(int)` converts a valid code point into one or two `char` values. The `new String(...)` constructor then builds the corresponding string. For valid Unicode data, this method preserves supplementary symbols intact.

You cannot mechanically replace it with:

```java
// Wrong if the goal is to keep supplementary symbols intact:
List<String> pieces = text.chars()
    .mapToObj(c -> String.valueOf((char) c))
    .toList();
```

In the `chars()` version, the emoji is split into two strings containing individual surrogates. Neither string represents a complete emoji on its own.

### 4.3. Filtering and Rebuilding a String with `collect`

A simple cleaning rule: keep only **Unicode letters or digits**, dropping spaces, punctuation, and emojis. For a string whose characters are already in precomposed normalized form:

```java
String raw = "Café_2026 😀";

String cleaned = raw.codePoints()
    .filter(Character::isLetterOrDigit)
    .collect(
        StringBuilder::new,
        StringBuilder::appendCodePoint,
        StringBuilder::append
    )
    .toString();

System.out.println(cleaned); // Café2026
```

In `IntStream.collect(supplier, accumulator, combiner)`:

1. `StringBuilder::new` creates the result accumulator.
2. `StringBuilder::appendCodePoint` appends each retained code point, including code points requiring surrogate pairs.
3. `StringBuilder::append` joins accumulators when combining results is needed.

`StringBuilder` is a stateful object, but the state resides **inside accumulators managed by `collect`**. This is a different pattern from arbitrarily mutating a shared `StringBuilder` from parallel lambdas. For full text normalization requirements, Unicode normalization and business rules must be added; the example above only demonstrates filtering code point categories.

### 4.4. `map` on Code Points and Uppercase Conversion Limits

`Character.toUpperCase(int)` can map **each code point to one code point**:

```java
String value = "abc";

String upper = value.codePoints()
    .map(Character::toUpperCase)
    .collect(
        StringBuilder::new,
        StringBuilder::appendCodePoint,
        StringBuilder::append
    )
    .toString();

System.out.println(upper); // ABC
```

This illustrates `map` on `IntStream`, but it **does not fully replace** `String.toUpperCase(Locale)`. Some Unicode rules turn **one character into multiple characters** or depend on locale; `Character.toUpperCase(int)` only yields a single return value. When the goal is uppercasing real text, choose the string API with an appropriate `Locale`:

```java
import java.util.Locale;

String normalized = value.toUpperCase(Locale.ROOT);
```

## 5. Distinguishing `int` vs. `char` When Handling Results

`IntStream` holds `int`, so you must know whether a number represents a **UTF-16 code unit** or a **Unicode code point** before converting it back to a string.

Dangerous example:

```java
String text = "😀";

// Code point U+1F600 does not fit in the 16 bits of char.
int cp = text.codePoints().findFirst().orElseThrow();
char truncated = (char) cp;

System.out.println(cp);                         // 128512
System.out.println(Integer.toHexString(truncated)); // f600
```

Casting `(char) cp` discards the high bits; the result `0xF600` is **not** the `😀` symbol. When creating a string from a code point, use `Character.toChars` or `StringBuilder.appendCodePoint`.

To print Unicode codes in a readable format:

```java
String text = "A😀B";

text.codePoints().forEachOrdered(cp ->
    System.out.printf("U+%04X%n", cp)
);
```

Output:

```text
U+0041
U+1F600
U+0042
```

`forEachOrdered` preserves the encounter order of an ordered source. In a sequential pipeline, `forEach` also usually follows order; when switching to parallel, `forEach` does not guarantee action order, whereas `forEachOrdered` enforces an ordering constraint.

## 6. String Indexing Still Counts in UTF-16

`codePoints()` produces a stream of code points, yet **does not change how `String` indexing works**. Methods like `charAt`, `substring`, `codePointAt`, and `codePointCount` use indices measured in UTF-16 code units at the positions specified in the API.

Consider the string `"A😀B"`:

```java
String text = "A😀B";

System.out.println(text.length());      // 4
System.out.println(text.charAt(0));     // A

int emojiStartOffset = text.offsetByCodePoints(0, 1);
int letterBOffset = text.offsetByCodePoints(0, 2);

System.out.println(emojiStartOffset);   // 1
System.out.println(letterBOffset);      // 3
System.out.println(
    Integer.toHexString(text.codePointAt(emojiStartOffset))
);                                       // 1f600
System.out.println(text.charAt(letterBOffset)); // B
```

`offsetByCodePoints(beginIndex, codePointOffset)` translates a **number of code points** into a **UTF-16 index**. In the example, the third visible item is `B`, yet it sits at `char` position `3`, because the emoji occupies two code units.

Avoid assuming that the `k`-th item in `codePoints()` equals `charAt(k)`. If processing code must slice a string by user-visible positions, even code point indices may be insufficient when the string contains combining marks or emoji sequences.

## 7. Two Unicode Boundaries to Recognize

### 7.1. A Code Point Is Not Necessarily a Display Character

The two strings below may look identical on screen:

```java
String composed = "\u00E9";      // é: one code point U+00E9
String decomposed = "e\u0301";   // e + combining acute accent U+0301

System.out.println(composed.codePoints().count());   // 1
System.out.println(decomposed.codePoints().count()); // 2
System.out.println(composed.equals(decomposed));     // false
```

Because `decomposed` has two code points, `codePoints().filter(Character::isLetter)` can **strip the combining mark**: `e` is a letter, whereas `U+0301` is a *mark*, not a letter under that check. Results can lose accents if you use a letter filter as a general-purpose "sanitization" solution.

If an application needs to compare canonically equivalent Unicode strings, consider normalizing with `java.text.Normalizer`; if it needs to traverse **grapheme clusters** as user-perceived characters, use an appropriate text segmentation algorithm such as `BreakIterator` or a Unicode-capable library suited to the application version. You cannot deduce the number of grapheme clusters solely from `codePoints().count()`.

### 7.2. Strings Containing Unpaired Surrogates

A Java `String` can contain an **unpaired surrogate** that is not paired with a matching code unit to form a valid pair. In that case, `codePoints()` **cannot** produce a valid Unicode scalar value from it; per the API contract, the unpaired code unit is emitted as a separate `int` value.

```java
String malformed = new String(new char[] {(char) 0xD83D});

int[] values = malformed.codePoints().toArray();
System.out.println(java.util.Arrays.toString(values)); // [55357]

boolean hasUnpairedSurrogate = malformed.codePoints()
    .anyMatch(cp -> cp >= 0xD800 && cp <= 0xDFFF);

System.out.println(hasUnpairedSurrogate); // true
```

The range `U+D800` to `U+DFFF` is reserved for surrogates and is **not a valid Unicode scalar value** when standing alone. `Character.isValidCodePoint(int)` only checks whether a value is within the Unicode code point range, so it is **not enough** to confirm a valid scalar value: surrogate values still fall within that numeric range. If input data may be malformed, define a policy to reject, replace, or handle it separately before interpreting and exporting Unicode to other formats.

## 8. Lazy Pipelines, Short-Circuiting, and Resources

`chars()` and `codePoints()` create `IntStream` sources. Intermediate operations `filter`, `map`, and `peek` express processing steps, yet the pipeline is only consumed when calling a **terminal operation** such as `count`, `toArray`, `anyMatch`, or `collect`.

```java
String text = "A😀B";

var selected = text.codePoints()
    .filter(Character::isLetter); // Source not consumed yet.

long numberOfLetters = selected.count(); // 2

// Do not call selected.toArray() again:
// The Stream has already been consumed. To read again, create a new text.codePoints().
```

Some terminal operations can **short-circuit**. For example:

```java
String text = "A😀B";

boolean hasEmojiGrinningFace = text.codePoints()
    .anyMatch(cp -> cp == 0x1F600);
```

`anyMatch` can stop once it finds a matching code point without scanning the entire string. Therefore, do not attach mandatory side effects to `filter`/`map` and assume they always execute for every element.

An ordinary `String` source is not tied to an external resource that needs closing, so `try-with-resources` is not required just for calling `text.chars()` or `text.codePoints()`. This differs from Streams opened on files, such as `Files.lines(...)`, which must be closed properly. The snippets in section 2 using `try-with-resources` are still valid, though **optional** for `String` sources.

## 9. Performance and Alternatives

`IntStream` is a Stream for primitive `int`, thereby avoiding boxing every element as in `Stream<Integer>`. Even so, a pipeline still has setup and processing overhead; you cannot assume a Stream is faster than a loop by default.

| Task | Option worth considering | Notes |
| --- | --- | --- |
| Count Unicode code points | `text.codePoints().count()` or `text.codePointCount(0, text.length())` | Use accurate terminology; not the grapheme cluster count. |
| Process ASCII codes unit by unit | `text.chars()` | Only sensible when requirements truly constrain the input. |
| Filter code points by Unicode property | `text.codePoints().filter(Character::isLetter)` | Watch out for combining marks and other Unicode categories. |
| Read/modify specific positions | `charAt`, `codePointAt`, `offsetByCodePoints`, or a loop | Be clear whether indices are UTF-16 or code points. |
| Obtain a list/array of code points | `codePoints().toArray()` | `int[]` avoids boxing; convert deliberately if objects are needed. |
| Rebuild a string | `StringBuilder.appendCodePoint` in `collect` | Avoid casting `int` to `char` for supplementary values. |
| Text with complex visual/linguistic structure | Dedicated Unicode segmentation/normalization APIs | Code points do not equal grapheme clusters. |

For short strings and simple logic, a loop over `char` can be clearer and lighter. For strings containing supplementary characters where code point processing is needed, a loop can also use `codePointAt` combined with `Character.charCount`; it is only slightly longer than a pipeline:

```java
String text = "A😀B";

for (int offset = 0; offset < text.length();) {
    int cp = text.codePointAt(offset);
    System.out.printf("U+%04X%n", cp);
    offset += Character.charCount(cp);
}
```

The loop above iterates through each code point following `String.codePointAt` conventions, including handling unpaired surrogates. If you need to process huge numbers of strings in performance-sensitive code, compare with representative data and proper benchmarking, such as **JMH**, after JVM warm-up.

Do not enable `parallel()` just to process a short string. Partitioning data, combining results, and maintaining order can cost more than per-code-point operations. Techniques such as `Spliterator`, custom collectors, or Stream Gatherers are valuable in more complex problems, but unnecessary for most character-filtering examples in this lesson.

## 10. Common Errors and How to Fix Them

| Error | Consequence | Fix |
| --- | --- | --- |
| Using `chars().count()` and calling it the Unicode character count | Counts supplementary emojis as two units | Use `codePoints().count()` if you need code point count; grapheme segmentation if you need display characters. |
| Using `(char) cp` for every code point | Truncates high bits of supplementary symbols | Use `Character.toChars` or `appendCodePoint`. |
| Using `String.length()` as a code point index | Wrong position after surrogate pairs | Use `offsetByCodePoints` or traverse code points properly. |
| Using `Character.isLetter` thinking all accented words stay intact | Loses combining marks in some strings | Consider Unicode normalization and mark categories as required. |
| Treating every `codePoints()` value as a valid Unicode scalar | Misses unpaired surrogates from malformed strings | Define a handling policy for unpaired surrogates. |
| Treating `Character.toUpperCase(int)` as complete uppercasing | Misses multi-character or locale-dependent mappings | Use `String.toUpperCase(Locale)` for real text. |
| Reusing the same `IntStream` for multiple terminal operations | `IllegalStateException` | Call `text.codePoints()` again to create a new pipeline. |
| Converting `int` to `Integer` en masse when only counting/filtering | Increases boxing and potentially memory cost | Use `IntStream` operations directly. |

## 11. Practice Exercises

### Exercise 1: Comparing Counts in Two Units

Given the string `"A😀B🚀"`, predict the results of `length()`, `chars().count()`, and `codePoints().count()`. Print the `int[]` arrays from both Streams and explain the difference. Verify with `codePointCount(0, text.length())`.

### Exercise 2: Identifier Code Rule

Design a method taking a code string that returns `true` if the code is **non-empty** and contains only ASCII uppercase letters `A-Z` and digits `0-9`. Use `chars().allMatch(...)` and test `"AB12"`, `"A-B"`, `"É9"`, `""`, and `"A😀"`. Explain why this is an ASCII requirement, distinct from allowing all Unicode letters.

### Exercise 3: Filtering by Code Point

Given the string `"Lập trình Java 17 😀"`, use `codePoints()` to count letters, digits, and whitespace. Write a `filter` + `collect` pipeline to retain letters and digits, then observe how Vietnamese diacritics are handled in precomposed and decomposed forms.

### Exercise 4: Keeping Supplementary Symbols Intact

Given the string `"A🚀B😀C"`, convert each code point into a small string using `mapToObj` and inspect the resulting list. Try doing the same with `chars()` to show why emojis get split in half.

### Exercise 5: Unnormalized Text

Compare `"\u00E9"` and `"e\u0301"` using `equals`, `codePoints().count()`, and `Character.isLetter`. Explain when Unicode normalization is needed and why one code point does not necessarily correspond to one character on screen.

### Exercise 6: Malformed Input Data

Create a `String` containing a high surrogate without a matching low surrogate. Inspect `chars().toArray()` and `codePoints().toArray()`. Propose a way to detect data without valid Unicode scalars before exporting it to an external system.

## 12. Self-Check Questions

- Why does `String.chars()` return an `IntStream`, and what do its elements represent?
- For a string containing `😀`, how do `chars()` and `codePoints()` differ in the number of elements they emit?
- Why should you not cast the `int` from `codePoints()` to `char` when rebuilding a string?
- Why is `codePoints().count()` not always equal to the number of characters a user sees?
- When is `chars()` a simple, correct choice for a processing rule?
- Why does a character-filtering pipeline usually not need `parallel()`?

**Key takeaway:** `String.chars()` traverses **UTF-16 code units**, whereas `String.codePoints()` traverses **Unicode code points** by combining valid surrogate pairs. Choose the unit of processing based on requirements; use `IntStream` for filtering and aggregating, while remembering that user-visible text can be more complex than individual code points.
