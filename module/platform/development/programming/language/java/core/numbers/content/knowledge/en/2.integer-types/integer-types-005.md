# `char` as an Unsigned Integer Representing a UTF-16 Code Unit

## 1. Why Does `char` Belong to the Integral Types?

In Java, `char` is a **16-bit unsigned primitive type** with an integer value range of **0 to 65,535** (corresponding to `0x0000` to `0xFFFF`). The language specification classifies `char` among the *integral types* alongside `byte`, `short`, `int`, and `long`. `Character.SIZE` is `16`, `Character.MIN_VALUE` is `'\u0000'` (integer value 0), and `Character.MAX_VALUE` is `'\uFFFF'` (integer value 65,535).

However, the primary purpose of `char` is **not to store a count**. Each `char` value is interpreted as **one UTF-16 code unit**. It can represent a common character such as `'A'`, `'7'`, `'中'`, or half of a *surrogate pair*. Its “unsigned integer” nature explains how Java stores, compares, and performs arithmetic on this type; its “UTF-16 code unit” nature explains **what part of Unicode text it represents**.

Three concepts must be distinguished:

- **Numeric value of `char`:** an integer from 0 to 65,535.
- **UTF-16 code unit:** a 16-bit element of a UTF-16 sequence; this is what `char` directly represents.
- **Unicode character by code point:** a Unicode value from `U+0000` to `U+10FFFF`, excluding the surrogate range that is not a *Unicode scalar value*. Many code points require **two** UTF-16 code units, so they cannot fit into a single `char`.

For example, `'A'` is both a `char` carrying the integer value 65 and a UTF-16 code unit representing the code point `U+0041`. Meanwhile, the emoji 😀 (`U+1F600`) requires **two** `char` values: `0xD83D` and `0xDE00`. Therefore, the claim that “one `char` is always one complete Unicode character” is **false**.

## 2. Value Range and Arithmetic Behavior

### 2.1. How Does Unsigned Differ from `byte` and `short`?

`byte` and `short` are 8-bit and 16-bit **signed** integers, which can hold negative values. `char` also has 16 bits, but is **unsigned**:

| Type | Bits | Minimum Value | Maximum Value | Primary Purpose |
|---|---:|---:|---:|---|
| `byte` | 8 | −128 | 127 | Small integers, byte data |
| `short` | 16 | −32,768 | 32,767 | 16-bit signed integers |
| `char` | 16 | 0 | 65,535 | UTF-16 code unit |
| `int` | 32 | −2,147,483,648 | 2,147,483,647 | General-purpose integers |

This means `char` **does not natively represent negative numbers**. You cannot assign `-1` to a `char` variable via an implicit narrowing assignment. When casting `(char) -1`, the result has numeric value `65535` (keeping the low 16 bits), not a negative `char`. Such a cast is an arithmetic conversion and does not produce a valid text character for ordinary use.

### 2.2. How Does `char` Participate in Numeric Operations?

In most arithmetic operations, Java performs *binary numeric promotion*, converting `char` to `int` before computing:

~~~java
char letter = 'A';
int code = letter;           // widening conversion: 65
int nextCode = letter + 1;   // addition has type int: 66
char next = (char) (letter + 1); // cast back to char: 'B'
~~~

The snippet above is **illustrative** (not a standalone runnable program). Note that `char next = letter + 1;` **does not compile** if `letter` is a `char` variable: the expression `letter + 1` has type `int` and requires an explicit narrowing conversion. Do not infer from `char` being an integral type that every arithmetic result stays `char`.

A constant expression can be an exception to the assignment rule: `char capitalA = 65;` or `char capitalA = '\u0041';` are both valid because the constant value fits within the `char` range. However, `int number = 65; char letter = number;` is invalid without a cast, even though the runtime value is 65.

When comparing `char` values with `<`, `>`, or `==`, Java compares their **numeric/code-unit values**, not a natural language's collation rules. For example, `'A' < 'a'` is `true` because 65 is less than 97; that does not mean it is the right way to sort people's names, Vietnamese text, or `Locale`-sensitive strings. For natural language sorting, use `Collator` instead of comparing individual `char`s.

### 2.3. Standalone Example: Observing Numeric Values

Create the file `CharIntegralDemo.java`:

~~~java
public class CharIntegralDemo {
    public static void main(String[] args) {
        char letter = 'A';
        char digit = '7';
        char han = '\u4E2D'; // U+4E2D: the character 中
        char max = Character.MAX_VALUE;

        System.out.println("bits=" + Character.SIZE);
        System.out.println("range=" + (int) Character.MIN_VALUE
                + ".." + (int) max);
        System.out.println("A=" + (int) letter);
        System.out.println("Han=" + (int) han);
        System.out.println("digitValue=" + (digit - '0'));
        System.out.println("A+1=" + (letter + 1));
        System.out.println("next=" + (char) (letter + 1));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac CharIntegralDemo.java
java CharIntegralDemo
~~~

Exact output:

~~~text
bits=16
range=0..65535
A=65
Han=20013
digitValue=7
A+1=66
next=B
~~~

Explanation:

1. `Character.SIZE` gives the logical 16-bit width of `char`; it does not mean every character in a file always takes exactly two bytes. Text encoding on disk may be UTF-8 or another encoding.
2. `'A'` has integer value 65; `'\u4E2D'` has integer value 20,013.
3. `'7'` has code value 55, **not** integer 7. `'7' - '0'` gives 7 because ASCII digits are consecutive; this technique should only be used when input is guaranteed to be `'0'` through `'9'`.
4. `letter + 1` has type `int` so it prints `66`; casting back to `char` prints `B`.

## 3. UTF-16: Code Units, Code Points, and Surrogate Pairs

### 3.1. Unicode Code Points Are Not Identical to `char`

Unicode assigns **code points** to text elements; the **UTF-16** encoding uses one or two 16-bit code units for each *Unicode scalar value*.

- Within the **BMP** (*Basic Multilingual Plane*, `U+0000`–`U+FFFF`), code points **outside the surrogate range** are represented by **one** code unit, corresponding to one `char`. For example: `U+0041` (`A`), `U+00E9` (`é`), `U+4E2D` (`中`).
- Code points in the **supplementary planes**, from `U+10000` to `U+10FFFF`, require **two** UTF-16 code units: a *high surrogate* and a *low surrogate*. For example: 😀 `U+1F600` = `D83D DE00`.
- The range `U+D800`–`U+DFFF` is reserved for surrogates. These are **valid values of type `char`**, yet each by itself **is not an independent Unicode scalar value**.

| Code Unit Range | Role |
|---|---|
| `0000`–`D7FF` | One BMP code point outside surrogates |
| `D800`–`DBFF` | **High surrogate**: first half of a pair |
| `DC00`–`DFFF` | **Low surrogate**: second half of a pair |
| `E000`–`FFFF` | One BMP code point outside surrogates |

The term “code unit” describes the representation structure. A `char` element holding `0xD83D` is completely valid as a Java type, yet does not stand alone for the emoji 😀. To work with the code point `U+1F600`, use `int`.

### 3.2. Mechanism for Combining Two Code Units

For a code point `U` from `0x10000` to `0x10FFFF`, let `U' = U - 0x10000`:

- High surrogate = `0xD800 + (U' >>> 10)`.
- Low surrogate = `0xDC00 + (U' & 0x3FF)`.

For `U+1F600`, `U' = 0xF600`, giving high surrogate `0xD83D` and low surrogate `0xDE00`. In practice, use the APIs `Character.toChars(codePoint)` to create the pair and `Character.toCodePoint(high, low)` to recover the code point; do not hand-write the formula unless you are building an encoding library.

Java provides `Character.isHighSurrogate(char)`, `Character.isLowSurrogate(char)`, `Character.isSurrogatePair(char, char)`, `Character.isSupplementaryCodePoint(int)`, and `Character.charCount(int)` to inspect and manipulate them properly.

### 3.3. Why Does One Emoji Increase `String.length()` by 2?

In Java, `String.length()` returns **the number of UTF-16 code units**, not the number of code points and certainly not guaranteed to equal the number of visible characters. `String.charAt(index)` retrieves **one** code unit; `String.codePointAt(index)` retrieves the code point starting at that UTF-16 index and combines a valid surrogate pair when possible.

Standalone example, create the file `Utf16PairDemo.java`:

~~~java
public class Utf16PairDemo {
    public static void main(String[] args) {
        String smile = new String(Character.toChars(0x1F600));
        String text = "A" + smile + "Z";

        System.out.println("units=" + text.length());
        System.out.println("points="
                + text.codePointCount(0, text.length()));
        System.out.printf("pair=%04X %04X%n",
                (int) text.charAt(1), (int) text.charAt(2));
        System.out.printf("pointAt1=U+%X%n", text.codePointAt(1));
        System.out.println("validPair=" + Character.isSurrogatePair(
                text.charAt(1), text.charAt(2)));
        System.out.println("pointUnits="
                + Character.charCount(text.codePointAt(1)));
        System.out.println("sameSmile="
                + smile.equals(text.substring(1, 3)));
    }
}
~~~

~~~bash
javac Utf16PairDemo.java
java Utf16PairDemo
~~~

Exact output:

~~~text
units=4
points=3
pair=D83D DE00
pointAt1=U+1F600
validPair=true
pointUnits=2
sameSmile=true
~~~

The string has three code points `A`, 😀, `Z` but four code units: `0041 D83D DE00 005A`. Indices `1` and `2` belong together to **one** code point 😀. `text.substring(1, 3)` captures both code units, whereas `substring(1, 2)` takes only the high surrogate and creates a string without a complete emoji.

Specifically, `charAt(2)` returns the **low surrogate**, while `codePointAt(2)`, because it starts directly at the low surrogate without looking backward to pair with the preceding high surrogate, returns the low surrogate value as an `int`. Therefore, you must pass the **starting index of the code point** when using `codePointAt`.

## 4. Iterating a String Properly When Characters Are Outside the BMP

The following common loop reads one **code unit** at a time:

~~~java
for (int i = 0; i < text.length(); i++) {
    char unit = text.charAt(i);
    // Only appropriate when intentionally processing UTF-16 code units.
}
~~~

This is an **illustrative code snippet**, assuming `text` is already declared. If the goal is to process each **Unicode code point**, advance the index by `Character.charCount(codePoint)`:

~~~java
for (int i = 0; i < text.length();) {
    int codePoint = text.codePointAt(i);
    // Process codePoint as an int.
    i += Character.charCount(codePoint);
}
~~~

This is also an **illustrative snippet**. For ordinary string data, you can use `text.codePoints()` to obtain an `IntStream`, though you should understand the rule for lone surrogates explained in the next section.

### Standalone Example: Iterating by Code Point

Create the file `CodePointIterationDemo.java`:

~~~java
public class CodePointIterationDemo {
    public static void main(String[] args) {
        String text = "A"
                + new String(Character.toChars(0x1F642))
                + "\u00E9";

        System.out.println("units=" + text.length());
        System.out.println("points=" + text.codePoints().count());

        for (int i = 0; i < text.length();) {
            int cp = text.codePointAt(i);
            System.out.printf("index=%d codePoint=U+%X%n", i, cp);
            i += Character.charCount(cp);
        }
    }
}
~~~

~~~bash
javac CodePointIterationDemo.java
java CodePointIterationDemo
~~~

Exact output:

~~~text
units=4
points=3
index=0 codePoint=U+41
index=1 codePoint=U+1F642
index=3 codePoint=U+E9
~~~

`U+1F642` is a code point outside the BMP so it occupies two code units at UTF-16 indices `1` and `2`; `é` (in single code-point form `U+00E9`) starts at index `3`. If you need to move by code points without manually summing code-unit counts, Java also provides `String.offsetByCodePoints`.

Do not use `text.length()` as the count of “human-visible characters”, such as validating a display name of at most 20 characters: `length()` counts UTF-16 code units, `codePointCount` counts code points, while a **grapheme cluster** is what closely corresponds to a user-perceived character.

## 5. One Code Point Is Not Necessarily One Visible Character

Even after moving from `char` to code points, text character counting is not yet complete:

- The letter `é` can be **one code point** `U+00E9`, or two code points `U+0065` (`e`) and `U+0301` (combining acute accent).
- Some emoji are formed from multiple code points joined with `U+200D` (*zero-width joiner*), variation selectors, or other components, yet render as a single icon.
- Vietnamese text and other languages can have combining diacritics, character boundary rules, and language-dependent sorting.

Therefore:

| Question | Appropriate Concept/API |
|---|---|
| How many UTF-16 units? | `String.length()` |
| Get the code unit at a UTF-16 index? | `String.charAt(index)` |
| What code point starts at this UTF-16 position? | `String.codePointAt(index)` |
| How many code points in a UTF-16 range? | `String.codePointCount(0, length)` |
| Iterate over code points | `String.codePoints()` or `codePointAt` + `Character.charCount` |
| Count visible text elements, splitting by grapheme clusters? | An *extended grapheme cluster* segmentation algorithm conforming to the applicable Unicode standard and data version |
| Compare/sort strings by language? | `Collator`/`Locale` rules, not `char` numeric order |

Unicode normalization, such as NFC/NFD via `java.text.Normalizer`, may be necessary to handle equivalent strings at the representation level. However, **normalization** and **grapheme segmentation** are two different operations: normalization does not suddenly turn `char` counting into visible character counting.

## 6. Unicode Escapes, `char` Literals, and External Data

### 6.1. Writing `char` Literals

A `char` literal uses **single quotes** and holds exactly one UTF-16 code unit, such as `'A'`, `'7'`, `'\n'`, `'\u4E2D'`. String literals use double quotes, such as `"A"`, `"ABC"`. Characters outside the BMP like 😀 cannot fit inside a standalone `char` literal because they need two code units; use `String` and `Character.toChars(0x1F600)` when constructing strings from code points.

Familiar escapes such as `'\n'`, `'\t'`, `'\\'`, and `'\''` are all valid `char` literals. Note that Java processes **Unicode escapes `\uXXXX` very early**, before tokenization. Thus writing the Unicode escape for a newline `U+000A` directly in Java source can unexpectedly split a source line; when you need a newline character, use `'\n'` instead of its Unicode escape.

A `char` is only a code-unit value; it does not mean all text will be stored in files as UTF-16. When writing files, sending over the network, or converting strings to `byte[]`, choose an explicit charset such as `StandardCharsets.UTF_8`. Do not take a `char` and assume casting to `byte` always preserves the character; casting can lose high bits and is not UTF-8 encoding at all.

### 6.2. Lone Surrogates Can Exist

A Java `String` can contain an **unpaired** high surrogate or low surrogate. That is a string of UTF-16 code units, yet **not a complete valid sequence of Unicode scalar values**. In that case:

- `String.length()` still counts code units, including lone surrogates.
- `String.codePointAt` and `String.codePoints()` combine **valid pairs**; for an unpaired surrogate, they may return the surrogate value itself as an `int`.
- `Character.isValidCodePoint(int)` only checks whether the number lies in the code point range `U+0000`–`U+10FFFF`; it does not exclude surrogate values. Checking for a *Unicode scalar value* requires excluding the range `U+D800`–`U+DFFF`.
- When exchanging data between systems or exporting to another charset, you need a policy for handling invalid input instead of assuming every `String` contains only valid scalar code points.

Standalone example, create the file `UnpairedSurrogateDemo.java`:

~~~java
public class UnpairedSurrogateDemo {
    public static void main(String[] args) {
        char high = (char) 0xD83D;
        String broken = String.valueOf(high);
        int cp = broken.codePointAt(0);

        System.out.println("units=" + broken.length());
        System.out.printf("returned=U+%X%n", cp);
        System.out.println("high=" + Character.isHighSurrogate(high));
        System.out.println("validCodePoint="
                + Character.isValidCodePoint(cp));
        System.out.println("scalar=" + isScalarValue(cp));
    }

    private static boolean isScalarValue(int cp) {
        return cp >= 0 && cp <= 0x10FFFF
                && !(cp >= 0xD800 && cp <= 0xDFFF);
    }
}
~~~

~~~bash
javac UnpairedSurrogateDemo.java
java UnpairedSurrogateDemo
~~~

Exact output:

~~~text
units=1
returned=U+D83D
high=true
validCodePoint=true
scalar=false
~~~

This example shows the difference between **the code point range accepted by the API** and **a valid scalar code point representing Unicode**. Use `int` for code points and validate surrogate pairs when data sources may be corrupted.

## 7. When Should You Use `char`, and When Should You Not?

**Use `char`** when the program genuinely needs to handle **a single UTF-16 code unit**, interact with `charAt`, `char[]` buffers, corresponding character APIs, or simple ASCII symbols in a character-restricted protocol. For example, checking delimiters like `','` or `':'` is a reasonable use case.

**Use `int` for code points** when the task needs to iterate, classify, or transform Unicode text beyond the BMP; combine `codePointAt`/`codePoints` with `Character` methods that accept `int`, such as `Character.isLetter(int codePoint)`. Some Unicode utilities have overloads taking `char` that will miss characters outside the BMP: when full Unicode coverage is needed, choose the `int` overload.

**Use `String` for text** such as personal names, content strings, emails, identifiers, or any arbitrary symbol. `String` can hold multiple code units and still needs proper operations as required: iterating code points, normalization, grapheme segmentation, and locale-sensitive comparison.

**Use `int`, `long`, `BigInteger` for general integer quantities** instead of repurposing `char` merely because it is unsigned. `char` has arithmetic properties, but its type name and APIs express the meaning of a **text code unit**, not a general non-negative count.

### Four Common Mistakes

1. **“`char` can hold every Unicode character because it has 16 bits.”** False: Unicode has code points outside the BMP that require two UTF-16 units.
2. **“`String.length()` is the number of characters the user sees.”** False: it is the number of UTF-16 code units; the count of code points or grapheme clusters can differ.
3. **“`charAt(i)` always returns a complete character.”** False: it can return a high/low surrogate. When iterating code points, advance `i` by `Character.charCount(cp)`.
4. **“`char` is unsigned, so use it instead of `unsigned short` everywhere.”** Inappropriate: the `char` type is tied to code units; when handling a 16-bit unsigned protocol field, usually decode it into `int` to compute and clearly represent the 0..65535 range.

## 8. Self-Check Quiz

1. How many bits does `char` have, and what is its integer range?
2. Why is `char letter = 'A'; int n = letter + 1;` valid, whereas `char next = letter + 1;` is not?
3. Why does `"A😀Z".length()` equal `4`, while the number of Unicode code points in the string is `3`?
4. How does `String.charAt` differ from `String.codePointAt`? Why should code points be stored in `int`?
5. Can a string with a lone high surrogate exist in Java? Does `Character.isValidCodePoint` guarantee there are no lone surrogates?
6. When limiting a display name's length by perceived characters, should you count UTF-16 code units, code points, or grapheme clusters?

**Suggested answers:** (1) 16 bits, 0–65,535; (2) addition promotes to `int`, and narrowing requires an explicit cast; (3) the emoji is outside the BMP and occupies 2 code units; (4) `charAt` reads one code unit, `codePointAt` pairs valid surrogates to read a code point, and `int` can hold values above `U+FFFF`; (5) lone surrogates can exist, and `isValidCodePoint` checks the numeric range so it is insufficient to exclude surrogates; (6) choose grapheme cluster segmentation appropriate to Unicode and product requirements.

**Remember:** `char` **is a 16-bit unsigned integer in Java's mechanics**, while also **being a UTF-16 code unit in text semantics**. In modern Unicode, one code point can require two `char`s and one visible character can require multiple code points.
