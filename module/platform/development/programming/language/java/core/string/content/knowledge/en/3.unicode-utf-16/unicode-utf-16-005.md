# Java String Can Contain Unpaired Surrogates

In Java, a `String` stores a **sequence of UTF-16 code units**. Each code unit corresponds to a 16-bit `char`. Java **does not enforce** that every `String` represents a valid sequence of Unicode characters: a string can still contain a standalone **high surrogate** or **low surrogate** without a matching partner. This condition is called an *unpaired surrogate* or *unpaired surrogate code unit*.

This is an important detail when slicing strings, iterating over strings, computing lengths, comparing, and transcoding to UTF-8. A `String` can be completely valid as a **Java type**, yet hold an **ill-formed UTF-16** sequence.

## 1. Distinguishing `char`, UTF-16 Code Unit, Code Point, and Unicode Scalar Value

- **`char` in Java:** a 16-bit unsigned integer value, from `0x0000` to `0xFFFF`. `String.length()` counts these `char` code units, not displayed characters.
- **Unicode code point:** a position in the code space `U+0000` to `U+10FFFF`. Java typically represents a code point as an `int`.
- **Unicode scalar value:** a code point **not in** the surrogate range `U+D800`–`U+DFFF`; these are the values that can be encoded as an individual Unicode character in UTF-8.
- **UTF-16:** a BMP scalar value outside the surrogate range uses one code unit; a scalar value from `U+10000` to `U+10FFFF` uses **two code units**, a high surrogate followed by a low surrogate.

Surrogate ranges:

| Group | UTF-16 value range | Role |
|---|---|---|
| High surrogate (*leading surrogate*) | `U+D800`–`U+DBFF` | First code unit of a pair |
| Low surrogate (*trailing surrogate*) | `U+DC00`–`U+DFFF` | Second code unit of a pair |
| Valid pair | High followed by Low | Together represent one non-BMP scalar value |
| Unpaired | High not followed by Low; or Low not immediately preceded by High | Cannot form a scalar value from that code unit |

For example, the emoji 😀 has code point `U+1F600`. In UTF-16, it uses two `char`s: `U+D83D` (*high*) and `U+DE00` (*low*). Thus, a `String` containing only this emoji has `length() == 2`, while `codePointCount(0, length()) == 1`.

UTF-16 formula when encoding a non-BMP code point (to understand the mechanism):

```text
x    = codePoint - 0x10000
high = 0xD800 + (x >>> 10)
low  = 0xDC00 + (x & 0x3FF)
```

Surrogate code units **do not represent standalone characters**. A high surrogate `U+D83D` alone is not the emoji 😀. Do not confuse the surrogate code unit `U+D83D` with the emoji code point `U+1F600`.

## 2. Why Does Java Still Allow a `String` to Contain Unpaired Surrogates?

The `String` API operates on sequences of UTF-16 code units, and several operations accept or return those code units without enforcing well-formedness across the entire string. A `char` can hold a value in the surrogate range; Java does not forbid putting that `char` into a `String`.

There are at least three ways an unpaired surrogate can appear:

### Creating directly from a `char`

```java
char high = (char) 0xD83D;
char low = (char) 0xDE00;

String onlyHigh = String.valueOf(high);
String onlyLow = new String(new char[] {low});
```

Each string above is one code unit long, yet does not form a complete surrogate pair.

### Slicing in the middle of a valid pair

```java
String emoji = new String(Character.toChars(0x1F600)); // Two UTF-16 code units
String firstHalf = emoji.substring(0, 1);              // Standalone high surrogate
String secondHalf = emoji.substring(1, 2);             // Standalone low surrogate
String restored = firstHalf + secondHalf;               // Pair recombined in the right order
```

Both `substring` and `charAt` use **code unit indices**. They do not guarantee that boundaries align with code point boundaries. Both `firstHalf` and `secondHalf` are `String`s that can be created and stored normally, even though each string is ill-formed UTF-16. When concatenated in the right order, `restored` again contains a valid pair.

### Appending code units with `StringBuilder` or receiving existing data

```java
StringBuilder builder = new StringBuilder();
builder.append((char) 0xD83D);
builder.append('X');
String malformed = builder.toString();
```

In `malformed`, the high surrogate precedes `X`, with no matching low surrogate. Data truncated by another system or APIs operating on `char` can also carry this condition. Successfully creating a `String` object does not validate well-formed Unicode.

Note: after slicing or concatenating strings, the same code unit can transition from unpaired to valid or vice versa depending on **the two adjacent code units**, because pairing depends on order.

## 3. How Do Counting and Iteration APIs Behave?

| API | Unit and behavior | What to remember |
|---|---|---|
| `length()` | Number of UTF-16 code units | A non-BMP code point usually takes 2 |
| `charAt(i)` | Gets one code unit at index `i` | May return half of a pair |
| `substring(begin, end)` | Slices by code unit index | May split a pair in half |
| `chars()` | Stream of `char` values widened to `int` | Does not combine surrogate pairs |
| `codePointAt(i)` | Combines High+Low when a valid pair is at that position; otherwise returns the single code unit's value | May return a value in the surrogate range |
| `codePoints()` | Combines valid pairs into one `int`; for unpaired code units, emits that code unit value itself | **Not** a well-formed Unicode check |
| `codePointCount(begin, end)` | Counts a valid pair as one, and an unpaired code unit as one | A result is still returned when the string is ill-formed |
| `offsetByCodePoints(index, delta)` | Moves according to how Java recognizes code points in a UTF-16 string | Useful for avoiding splitting valid pairs, but does not fix already broken data |

A common point of confusion: `Character.isValidCodePoint(0xD83D)` returns `true` because the value lies within `0x0000`–`0x10FFFF` accepted by this API. However, `U+D83D` **is not a Unicode scalar value** because it belongs to the surrogate range. Therefore, **checking `isValidCodePoint` alone is not enough** to confirm a value can be encoded as an independent Unicode character.

You can check whether an `int` value is a scalar value with the condition:

```java
static boolean isUnicodeScalarValue(int cp) {
    return Character.isValidCodePoint(cp)
            && !(cp >= 0xD800 && cp <= 0xDFFF);
}
```

That condition applies to **a single `int` code point**. For a `String`, you must iterate and check the pairing of UTF-16 code units.

## 4. Checking Whether a `String` Is Well-Formed UTF-16

Left-to-right validation rules:

1. When encountering a **high surrogate**, there must be a next character and it must be a **low surrogate**; consume both.
2. When encountering a **low surrogate** without a high surrogate immediately before it, the string is **invalid**.
3. When encountering a `char` in neither group, continue normally.
4. Reaching the end of the string with no errors means the UTF-16 sequence is well-formed; an empty string is also valid.

With `n = s.length()`, the algorithm runs in `O(n)` time and uses `O(1)` extra memory.

### Standalone Runnable Java 17+ Example

Save the entire program to **`UnpairedSurrogateDemo.java`**:

```java
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.StringJoiner;

public class UnpairedSurrogateDemo {
    public static boolean isWellFormedUtf16(String s) {
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);

            if (Character.isHighSurrogate(ch)) {
                if (i + 1 == s.length()
                        || !Character.isLowSurrogate(s.charAt(i + 1))) {
                    return false;
                }
                i++; // Handled both high and low surrogates
            } else if (Character.isLowSurrogate(ch)) {
                return false; // Standalone low surrogate
            }
        }
        return true;
    }

    private static String units(String s) {
        StringJoiner result = new StringJoiner(" ");
        for (int i = 0; i < s.length(); i++) {
            result.add(String.format("U+%04X", (int) s.charAt(i)));
        }
        return result.toString();
    }

    private static String codePointValues(String s) {
        StringJoiner result = new StringJoiner(" ");
        s.codePoints().forEach(cp ->
                result.add(String.format("U+%04X", cp)));
        return result.toString();
    }

    private static String utf8EncodingStatus(String s) {
        CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try {
            encoder.encode(CharBuffer.wrap(s));
            return "OK";
        } catch (CharacterCodingException ex) {
            return "malformed input";
        }
    }

    public static void main(String[] args) {
        String emoji = new String(Character.toChars(0x1F600));
        String high = emoji.substring(0, 1);
        String low = emoji.substring(1, 2);
        String restored = high + low;
        String mixed = "A" + high + "B";

        System.out.println("emoji.length(): " + emoji.length());
        System.out.println("emoji.codePointCount(): "
                + emoji.codePointCount(0, emoji.length()));
        System.out.println("emoji units: " + units(emoji));
        System.out.println("high units: " + units(high));
        System.out.println("low units: " + units(low));
        System.out.println("high codePoints: " + codePointValues(high));
        System.out.println("emoji well-formed: " + isWellFormedUtf16(emoji));
        System.out.println("high well-formed: " + isWellFormedUtf16(high));
        System.out.println("low well-formed: " + isWellFormedUtf16(low));
        System.out.println("restored well-formed: " + isWellFormedUtf16(restored));
        System.out.println("mixed well-formed: " + isWellFormedUtf16(mixed));
        System.out.println("UTF-8 emoji: " + utf8EncodingStatus(emoji));
        System.out.println("UTF-8 high: " + utf8EncodingStatus(high));
        System.out.println("high isValidCodePoint: "
                + Character.isValidCodePoint(high.charAt(0)));
        System.out.println("high isSurrogate: "
                + Character.isSurrogate(high.charAt(0)));
    }
}
```

Compile and run commands:

```bash
javac -encoding UTF-8 UnpairedSurrogateDemo.java
java UnpairedSurrogateDemo
```

Output:

```text
emoji.length(): 2
emoji.codePointCount(): 1
emoji units: U+D83D U+DE00
high units: U+D83D
low units: U+DE00
high codePoints: U+D83D
emoji well-formed: true
high well-formed: false
low well-formed: false
restored well-formed: true
mixed well-formed: false
UTF-8 emoji: OK
UTF-8 high: malformed input
high isValidCodePoint: true
high isSurrogate: true
```

**Reading the output:** `high.codePoints()` still produces an integer element `0xD83D`; that **does not confirm the string is well-formed**. The UTF-8 encoder in `REPORT` mode rejects the unpaired surrogate because it does not represent a Unicode scalar value. When `high` and `low` are combined in the right order, the same two code units form a valid pair again.

The `isWellFormedUtf16` function checks the validity of **the code unit sequence**, not whether the data has linguistic meaning or is renderable in the current font.

## 5. Consequences When Encoding to UTF-8 or Exchanging Data

UTF-8 encodes Unicode scalar values. A standalone surrogate in a `String` has no valid UTF-8 representation as an independent character. During conversion, the result depends on **the API and error-handling policy**:

- **`REPORT` policy:** the encoder throws `MalformedInputException` (a subclass of `CharacterCodingException`), as shown in the program above. This is the right choice when invalid data must be detected.
- **`REPLACE` policy:** the encoder replaces the invalid portion with the configured replacement bytes; the converted data then no longer preserves the unpaired surrogate. One should not assume the encoder's replacement bytes always represent one fixed Unicode character.
- **Convenience methods such as `getBytes(StandardCharsets.UTF_8)`:** may replace invalid data instead of throwing an error; do not treat this method's successful return as proof that the original string was well-formed.

In the reverse direction, when **decoding** malformed UTF-8 bytes, a decoder may *report* or replace with `U+FFFD` (*replacement character*) depending on the API/policy. **U+FFFD is a valid scalar value**, completely different from a standalone high or low surrogate. Never call an unpaired surrogate `U+FFFD`.

Serialization to JSON, XML, API communication, or storage must also consider the receiving library's contract. Some libraries may reject, replace, or escape according to their own rules; do not assume every system behaves the same way automatically. If the system requires well-formed Unicode, validate or set an explicit error-handling policy **before the data-transfer boundary**.

### Should unpaired surrogates be replaced automatically?

It depends on business requirements:

- **Reject** ill-formed data: appropriate when preserving exact meaning and data integrity is critical.
- **Replace each unpaired code unit with U+FFFD:** appropriate when display must continue and data loss is acceptable; must be done accurately per pair/code unit.
- **Keep** the code unit sequence as-is for investigation or internal processing: only do this when downstream steps understand ill-formed UTF-16 behavior.

Do not fix this by deleting *all* `char`s in the surrogate range: doing so deletes **valid pairs** too and corrupts every character outside the BMP. Nor should you arbitrarily pair an unpaired surrogate with a distant surrogate: a valid pair must be **high immediately followed by low**.

## 6. Slicing Strings Safely at Code Point Boundaries

If the input string is already well-formed and you need to slice the first few code points, `offsetByCodePoints` helps find the UTF-16 index aligned with pair boundaries:

```java
String text = "A" + new String(Character.toChars(0x1F600)) + "B";
int end = text.offsetByCodePoints(0, 2);
String prefix = text.substring(0, end); // Contains A and emoji 😀
System.out.println(prefix.codePointCount(0, prefix.length())); // 2
```

If replaced with `text.substring(0, 2)`, the result contains `A` and **the emoji's high surrogate**, missing the low surrogate: this is an ill-formed string. Slicing by code point count also **does not automatically repair** an input string that already contains unpaired surrogates.

Additionally, *a code point is not the same as a user-perceived character* (*grapheme cluster*). For example, a letter with combining marks or an emoji formed from multiple code points may require higher-level text segmentation. `offsetByCodePoints` solves **UTF-16 surrogate pair boundaries**, not the full set of grapheme segmentation rules.

## 7. Common Misconceptions

| Claim/assumption | Why it is wrong | Correct way to think |
|---|---|---|
| “`String` always contains valid Unicode.” | `String` can still hold unpaired surrogates. | When Unicode validity is needed, check well-formed UTF-16 explicitly. |
| “A `char` is always a displayed character.” | It is only a 16-bit code unit. | Non-BMP characters have two `char`s; a grapheme can have multiple code points. |
| “`length()` counts code points.” | `length()` counts UTF-16 code units. | Use `codePointCount` for Java's API count; note unpaired surrogates are still counted. |
| “`codePoints()` only emits Unicode scalar values.” | This stream can emit unpaired surrogate values. | Check well-formed UTF-16 or exclude `D800`–`DFFF` when testing scalar values. |
| “`Character.isValidCodePoint` is enough for validation.” | It returns `true` for numbers in the surrogate range. | Exclude `U+D800`–`U+DFFF` when checking for a scalar value. |
| “Slicing with `substring` always falls between complete characters.” | Boundaries are measured in code units. | Consider `offsetByCodePoints` if the target unit is code points. |
| “An emoji turning into `?`/`�` is just a font issue.” | Data replacement may have occurred during failed transcoding. | Distinguish original code units, encoded bytes, decoder, and font. |
| “Deleting all surrogates fixes the data.” | Deletes valid pairs as well. | Iterate pair by pair and handle only **unpaired** surrogates. |

## 8. Practice Scenario

Given a string constructed as follows:

```java
String face = new String(Character.toChars(0x1F600));
String a = face.substring(0, 1);
String b = face.substring(1, 2);
String c = "x" + a + b + "y";
String d = a + "x" + b;
```

1. What are `a.length()`, `b.length()`, and `face.length()` respectively?
2. Are the strings `face`, `a`, `b`, `c`, and `d` well-formed UTF-16?
3. What is the value of `c.codePointCount(0, c.length())`?
4. If `d` is encoded to UTF-8 using a `CharsetEncoder` with `CodingErrorAction.REPORT`, will the operation succeed?

**Answers:** (1) `1`, `1`, `2`. (2) `face` and `c` are well-formed; `a`, `b`, and `d` are not well-formed because they contain unpaired surrogates. (3) `3` code points: `x`, emoji, `y`. (4) No; high and low are separated by `x` so they do not form a pair, and the encoder reports malformed input.

**Key takeaway:** Java's `String` type holds a sequence of UTF-16 code units; a string's existence **does not guarantee** it is well-formed UTF-16. A valid surrogate pair requires **adjacent high + low** in order. When slicing or iterating, know whether the API handles `char` or code points; when converting to UTF-8 or interfacing with other systems, explicitly define a policy to **report, replace, or reject** unpaired surrogates.