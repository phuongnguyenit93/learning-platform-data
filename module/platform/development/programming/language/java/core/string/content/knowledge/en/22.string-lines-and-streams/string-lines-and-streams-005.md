# String.chars(): UTF-16 char Units Zero-Extended to int

## 1. What Is String.chars()?

In Java, `String.chars()` creates an `IntStream` sequentially containing **the value of each UTF-16 code unit (`char`)** in the string. Each `char` value is **widened to `int` by zero-extension**: the upper bits are filled with 0, so the numeric value stays unchanged in the range 0–65,535.

The signature can be seen from `CharSequence` (Java 9+):

~~~java
IntStream chars()
~~~

Simple example:

~~~java
String s = "ABC";
int[] units = s.chars().toArray();
// [65, 66, 67]
~~~

The result is `int[]` because `chars()` returns an `IntStream`, even though each value represents a `char` unit. For the string `"ABC"`, the UTF-16 codes of `'A'`, `'B'`, and `'C'` are 65, 66, and 67 respectively, so we see those three integers.

**Key point to remember:** `chars()` does not promise to return complete Unicode characters (*Unicode code points*) and does not decode surrogate pairs automatically. It reads each UTF-16 code unit present in the string in order, converting the unit's value from `char` (16-bit unsigned) to `int` (32-bit signed, though the value remains non-negative).

## 2. Why Can a char and a Unicode Character Differ?

Java represents a `String` as a sequence of UTF-16 code units. A `char` is 16 bits wide, whereas the Unicode codespace includes code points larger than the 16-bit range.

- Code points in the **BMP** (Basic Multilingual Plane), except the surrogate-reserved range, are represented by a single UTF-16 code unit. Examples are `A` (`U+0041`) and `á` (`U+00E1`).
- Code points **outside the BMP**, from `U+10000` to `U+10FFFF`, require **two UTF-16 units**: a *high surrogate* in `U+D800..U+DBFF` and a *low surrogate* in `U+DC00..U+DFFF`.
- A standalone surrogate unit is **not** a complete Unicode scalar value. An unpaired surrogate can still exist in a `String`; `chars()` will emit that unit's raw value.

Example with the displayed string `A😀B`, where the emoji `😀` has code point `U+1F600`:

| `char` position (UTF-16 index) | UTF-16 unit hex value | Decimal `int` value | Meaning |
|---|---|---|---|
| 0 | `0041` | 65 | `A` |
| 1 | `D83D` | 55,357 | High surrogate of `😀` |
| 2 | `DE00` | 56,832 | Low surrogate of `😀` |
| 3 | `0042` | 66 | `B` |

Therefore:

~~~java
String s = "A\uD83D\uDE00B"; // A😀B
System.out.println(s.length());        // 4 UTF-16 units
System.out.println(s.chars().count()); // 4 int elements
System.out.println(s.codePoints().count()); // 3 code points
~~~

The element count of `chars()` equals the number of UTF-16 code units in the `String`, which equals `s.length()`. Do not infer “4 reader-visible characters” from that result: counting UTF-16 units, Unicode code points, and UI-rendered characters can yield different numbers.

## 3. How char Widens to int

`char` is an **unsigned** 16-bit primitive type. When widening `char` to `int`, Java keeps the low 16 bits and sets the remaining upper bits to 0 (*zero-extension*); this is not a signed conversion (*sign-extension*).

~~~java
char ch = '\u00E1';           // á, code point U+00E1
int asInt = ch;               // 225
int viaStream = "á".chars().findFirst().orElseThrow();
// viaStream == 225
~~~

For `'A'`, the conversion can be visualized as:

~~~text
char: 0000 0000 0100 0001   (0x0041, 65)
int : 0000 0000 0000 0000 0000 0000 0100 0001   (0x00000041, 65)
~~~

For a surrogate unit with its high bit set, the widened `int` **is still a positive number**, for example `0xD83D` becomes `55357`; it does not turn into a negative integer.

Because this is a value widening of a single `char` unit, **it does not combine two `char`s of an emoji into one code point**. To combine a valid surrogate pair into a code point properly, you need a code-point-reading mechanism such as `codePoints()` or the `Character` API.

## 4. Comparing chars(), codePoints(), charAt(), and length()

| API | Result | Unit Processed | Best Use Case |
|---|---|---|---|
| `s.chars()` | `IntStream` | Individual UTF-16 units, widened to `int` | Inspecting/processing code units directly; stream operations on ASCII/BMP text under clear assumptions |
| `s.codePoints()` | `IntStream` | Each valid surrogate pair combined into one code point | Processing Unicode code points, especially with letters or emoji outside the BMP |
| `s.charAt(i)` | `char` | One UTF-16 unit at index `i` | Direct indexed access to a code unit |
| `s.length()` | `int` | Number of UTF-16 units | Checking the logical storage length of the string in `char`s |
| `s.codePointCount(0, s.length())` | `int` | Number of code points in the specified UTF-16 range | Counting code points, counting each valid surrogate pair as one |

For `"A\uD83D\uDE00B"`:

~~~text
UTF-16 code units:  0041 | D83D | DE00 | 0042   → 4 elements
Unicode code points: U+0041 | U+1F600 | U+0042  → 3 elements
~~~

`chars()` and `codePoints()` both return `IntStream`, yet their element values have **different semantics**. The `int` type itself does not tell you whether it holds a code unit or a code point; variable names and the source API help prevent confusion.

Special note: `codePoints()` only combines **valid high/low surrogate pairs**. If a string contains an unpaired surrogate, the method emits that surrogate value as its own `int`; it does not silently clean up malformed data or replace it with the replacement character `U+FFFD`.

## 5. Complete Runnable Java 17+ Example

Create the file **`StringCharsDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.stream.Collectors;

public class StringCharsDemo {
    public static void main(String[] args) {
        // A + 😀 + B. Emoji U+1F600 is encoded using two UTF-16 chars.
        String text = "A\uD83D\uDE00B";

        System.out.println("length = " + text.length());
        System.out.println("chars count = " + text.chars().count());
        System.out.println("chars decimal = "
                + Arrays.toString(text.chars().toArray()));

        String unitsHex = text.chars()
                .mapToObj(unit -> String.format(Locale.ROOT, "%04X", unit))
                .collect(Collectors.joining(" "));
        System.out.println("chars hex = " + unitsHex);

        String pointsHex = text.codePoints()
                .mapToObj(point -> String.format(Locale.ROOT, "U+%04X", point))
                .collect(Collectors.joining(" "));
        System.out.println("code points hex = " + pointsHex);

        System.out.println("code point count = "
                + text.codePoints().count());

        System.out.println("high surrogate = "
                + Character.isHighSurrogate(text.charAt(1)));
        System.out.println("low surrogate = "
                + Character.isLowSurrogate(text.charAt(2)));

        long countA = "banana".chars()
                .filter(unit -> unit == 'a')
                .count();
        System.out.println("count a = " + countA);

        String reconstructed = text.codePoints()
                .collect(
                        StringBuilder::new,
                        StringBuilder::appendCodePoint,
                        StringBuilder::append
                )
                .toString();
        System.out.println("round trip = " + text.equals(reconstructed));
    }
}
~~~

Compile and run:

~~~bash
javac StringCharsDemo.java
java StringCharsDemo
~~~

Output:

~~~text
length = 4
chars count = 4
chars decimal = [65, 55357, 56832, 66]
chars hex = 0041 D83D DE00 0042
code points hex = U+0041 U+1F600 U+0042
code point count = 3
high surrogate = true
low surrogate = true
count a = 3
round trip = true
~~~

Explanation:

1. `length()` and `chars().count()` are both **4** because the emoji occupies two code units.
2. `chars().toArray()` produces **`int[]`**: `[65, 55357, 56832, 66]`. The two middle numbers represent the two UTF-16 halves of the emoji.
3. `mapToObj(...)` converts each number to a hex string; `Collectors.joining(" ")` joins the parts into a readable line.
4. `codePoints()` combines the two valid surrogates into `U+1F600`, so there are only **3** code points.
5. `Character.isHighSurrogate` and `Character.isLowSurrogate` verify the two units at indices 1 and 2.
6. The filter `unit == 'a'` gives 3 for `banana`, because the letter `a` is in the BMP and represented by exactly one UTF-16 unit.
7. `StringBuilder.appendCodePoint` appends code points back into a valid UTF-16 string; since the input has a valid surrogate pair, reconstruction yields a string equal to the original.

In the code, `StringBuilder::appendCodePoint` is used with `IntStream.collect` to accumulate code points, while `StringBuilder::append` combines buffers when needed.

## 6. Direct Operations with IntStream

### 6.1. Iterating Over char Units

~~~java
String s = "ABC";
s.chars().forEachOrdered(unit -> System.out.println(unit));
// 65
// 66
// 67
~~~

Because the source is ordered, `forEachOrdered` preserves traversal order even if the stream is switched to parallel mode. `forEach` on a parallel stream does not guarantee execution order across elements.

### 6.2. Filtering and Counting

~~~java
long digits = "a1b23".chars()
        .filter(unit -> unit >= '0' && unit <= '9')
        .count();
// digits == 3
~~~

This pattern deliberately checks for **ASCII digits** `'0'` through `'9'`. If you need to support digits from multiple Unicode scripts, consider `codePoints().filter(Character::isDigit)` per your business rules; do not equate “ASCII digit” with “every character Unicode considers a digit”.

### 6.3. Creating an Integer Array or Aggregating

~~~java
int[] values = "ABC".chars().toArray();
// [65, 66, 67]

int total = "ABC".chars().sum();
// 198
~~~

`sum()` simply adds the numeric values of the UTF-16 units; it **does not produce a meaningful textual metric**. Arithmetic on code units should be used when the problem genuinely requires those numeric values, such as checking character codes within the ASCII range.

### 6.4. Converting Code Unit Values to Strings for Display

~~~java
String hex = "Az".chars()
        .mapToObj(unit -> String.format(Locale.ROOT, "%04X", unit))
        .collect(Collectors.joining(", "));
// "0041, 007A"
~~~

`mapToObj` transforms `IntStream` into `Stream<String>`; then `Collectors.joining` joins the strings. This is suitable for displaying **code unit values**. If you want to render each Unicode code point as its corresponding character, use `codePoints()` and convert each code point to a string using `Character.toChars(cp)`.

Streams are **single-use**: once a terminal operation like `count()`, `toArray()`, or `forEachOrdered()` has been called, do not reuse the same stream object. To run another computation, call `s.chars()` again.

## 7. Why Should You Not Cast Every int from chars() to “One Unicode Character”?

For ordinary ASCII/BMP text, the following snippet appears to work:

~~~java
String value = "ABC";
value.chars().forEachOrdered(unit -> {
    char c = (char) unit;
    System.out.print(c);
});
// ABC
~~~

However, with data containing non-BMP emoji, each `(char) unit` cast still produces only **half of a surrogate pair**. Processing, checking, deleting, or emitting each half as an independent character can corrupt the surrogate pair:

~~~java
String emoji = "\uD83D\uDE00"; // 😀
int[] units = emoji.chars().toArray();
// [55357, 56832]

// units[0] is a high surrogate; it is not a complete emoji.
boolean high = Character.isHighSurrogate((char) units[0]); // true
~~~

If you need to iterate through each Unicode code point and convert back to a string, use:

~~~java
String source = "A\uD83D\uDE00B";
String joined = source.codePoints()
        .mapToObj(cp -> new String(Character.toChars(cp)))
        .collect(Collectors.joining());
// joined.equals(source) == true, for a source with valid code points
~~~

`Character.toChars(cp)` converts a valid code point into one or two properly formed UTF-16 `char`s. For an unpaired surrogate emitted by `codePoints()`, `Character.toChars(cp)` can still return that single surrogate unit because its value falls within the code point range accepted by the API; it does **not** validate or repair malformed Unicode. If the output must consist of valid Unicode scalar values, detect and reject or replace unpaired surrogates according to your application contract.

If your application needs to slice a string by code point position rather than UTF-16 position, do not blindly increment the `char` index by 1 after every element. You can use `offsetByCodePoints(...)` to translate a code point index into a UTF-16 index:

~~~java
String s = "A\uD83D\uDE00B";
int from = s.offsetByCodePoints(0, 1); // UTF-16 index: 1
int to = s.offsetByCodePoints(0, 2);   // UTF-16 index: 3
String secondCodePoint = s.substring(from, to); // 😀
~~~

In the example above, `s.substring(1, 2)` takes only the high surrogate and produces a string with an unpaired surrogate; to capture the full emoji you must take the UTF-16 range `[1,3)`.

## 8. Counting Code Units, Code Points, and User-Perceived Characters

Three counting concepts are frequently confused:

| Concept | What Does It Count? | Related Tools |
|---|---|---|
| UTF-16 code unit | Each 16-bit `char` | `length()`, `chars().count()` |
| Unicode code point | Each code point; a valid surrogate pair counts as one | `codePoints().count()`, `codePointCount(...)` |
| Grapheme cluster (*perceived character*) | A group of code points displayed as a single user-perceived unit | An appropriate Unicode text segmenter, e.g., a grapheme cluster segmentation API |

An accented letter can be encoded as **one precomposed code point** or **a base letter plus a combining mark**; the two may look nearly identical yet have different code point counts. Emoji with modifiers, zero-width joiners, or country flags can also consist of multiple code points while rendering as a single glyph.

Therefore:

- `chars().count()` is **not** always the number of Unicode characters.
- `codePoints().count()` is also **not** guaranteed to equal the number of user-visible characters.
- When building UIs (limiting user input length, truncating display names, positioning a cursor), clearly define the unit to count and choose the corresponding segmenter.

This is a direct consequence of Java using UTF-16 in `String`, not a quirk specific to `chars()`.

## 9. API and Performance Notes

**`IntStream` is a primitive stream.** `chars()` gives you an `IntStream`, not a `Stream<Character>`. If you need `int[]`, call `toArray()`; if you need an object stream, use `mapToObj` or `boxed()` only when actually needed. Boxing into `Integer` can add overhead compared to staying primitive.

**`chars()` does not mutate `String`.** `String` is immutable; `filter`, `map`, and `count` only build a pipeline or compute a result. Intermediate operations like `filter()` are *lazy* and typically execute only when a terminal operation such as `count()` is invoked.

**Avoid creating a stream if the goal is reading a single unit at a fixed index.** `s.charAt(i)` is clearer for reading a single code unit. For simple loops or tasks requiring UTF-16 index coordination, a `for (int i = 0; i < s.length(); i++)` loop can be easier to control; which option is faster should be measured in the actual context.

**Do not assume every int holds a “complete character”.** This is a Unicode correctness issue, not just a performance one. Using `codePoints()` from the start prevents accidentally splitting non-BMP characters in half.

**Do not use a closed/consumed stream.** Example:

~~~java
var stream = "ABC".chars();
long size = stream.count();  // 3
// stream.sum(); // Error: stream has already been consumed
int sum = "ABC".chars().sum(); // Creates a new stream, result 198
~~~

**Note on empty strings and null.** `"".chars()` is an empty stream, so `count()` returns 0 and `toArray()` returns an empty array. Calling `chars()` on a `null` `String` reference throws `NullPointerException`; if the input can be null, decide how to handle it before creating the stream.

## 10. Common Mistakes and How to Fix Them

1. **Reading `chars()` as a “stream of code points”.** Incorrect: the output is UTF-16 code units promoted to `int`. With non-BMP characters, the element count exceeds the code point count. **Fix:** use `codePoints()` when Unicode code points are required.
2. **Thinking `toArray()` produces `char[]`.** `IntStream.toArray()` returns `int[]`. If you need a `char[]` array containing the code units, use `s.toCharArray()`.
3. **Casting an int to `(char)` and assuming it is a user-visible character.** A surrogate may be only half of a code point. **Fix:** process in pairs or use `codePoints()` and `Character.toChars()`.
4. **Using `length()` to enforce a limit on “visible characters”.** `length()` counts UTF-16 code units. **Fix:** decide first whether the requirement is code units, code points, or grapheme clusters.
5. **Slicing a string by UTF-16 index right between a surrogate pair.** This produces a string containing an unpaired surrogate. **Fix:** determine code point boundaries with `offsetByCodePoints()` or an appropriate API.
6. **Reusing an `IntStream` after a terminal operation.** A stream can only be consumed once. **Fix:** call `s.chars()` again or store the result that needs reuse.
7. **Using an ASCII check for all writing systems.** For instance, `'0' <= unit && unit <= '9'` only matches ASCII digits. **Fix:** use code-point-based logic and Unicode rules when you truly want to support multiple scripts.
8. **Assuming `codePoints()` repairs unpaired surrogates or handles grapheme clusters.** Both assumptions are false. **Fix:** validate malformed Unicode data and choose a grapheme segmenter when display characters matter.

## 11. Quick Self-Check

**Question 1.** What does `"Java".chars().count()` return? — **4**, because each Latin letter here occupies one UTF-16 unit.

**Question 2.** Given `String s = "\uD83D\uDE00";`, what do `s.chars().count()` and `s.codePoints().count()` return? — **2** and **1** respectively: the emoji uses one surrogate pair yet is a single code point.

**Question 3.** What data type does `"A".chars().toArray()` return? — **`int[]`**, containing the value `65`, because the source is an `IntStream`.

**Question 4.** If you need to print the Unicode code point `U+1F600` of an emoji, which API should you start with? — **`codePoints()`**; `chars()` emits `D83D` and `DE00` separately.

**Question 5.** Does `String.chars()` mutate the original string or return `Character` objects? — **No** on both counts: strings are immutable and the stream holds primitive `int` values.

## 12. Key Takeaways

`String.chars()` is a tool for iterating over **UTF-16 `char` units** after **zero-extending** each value to `int` in an `IntStream`. It is appropriate when a task operates at the code unit level, or on ASCII/BMP data with explicit assumptions. When a task needs to process **Unicode code points**, especially text containing emoji or non-BMP characters, choose `String.codePoints()`. When a task needs “one user-visible character”, neither of the above counts may suffice and grapheme cluster handling is required.
