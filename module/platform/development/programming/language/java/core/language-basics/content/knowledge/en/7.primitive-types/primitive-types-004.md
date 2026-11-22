# `char` as an Unsigned UTF-16 Code Unit — Java 17+

In Java, `char` is one of the eight **primitive types**. It stores **exactly one 16-bit unsigned UTF-16 code unit**, that is, an integer value from **0 to 65,535** (`0x0000` to `0xFFFF`).

Common point of confusion: **one `char` is not synonymous with a complete Unicode character or a user-perceived character**. Some Unicode code points are represented by two UTF-16 code units, and some displayed characters are formed from multiple code points.

## 1. What Does `char` Store?

| Expression | Value / meaning | Note |
| --- | --- | --- |
| `char c = 'A';` | A `char` containing code `0x0041`, i.e., 65 | Single quotes create a character literal |
| `char c = '\u00E9';` | A `char` containing code `0x00E9`, i.e., 233 (é) | Unicode escape in source code |
| `char min = Character.MIN_VALUE;` | `0` (`0x0000`) | There are no negative `char` values |
| `char max = Character.MAX_VALUE;` | `65_535` (`0xFFFF`) | Not the largest Unicode code point |
| `int n = 'A';` | `65` | Widening conversion from `char` to `int` |
| `int n = 'A' + 1;` | `66` | Arithmetic operations usually promote `char` to `int` |
| `String s = "A";` | String consisting of one UTF-16 code unit | `String` is a reference type, unlike `char` |

Unlike `byte`, `short`, `int`, and `long`, which are **signed** integer types, `char` is an **unsigned** integer type. Casting `char` to `int` produces a value in the range 0–65,535, never interpreted as negative.

A `char` can hold a **surrogate code unit** (`0xD800`–`0xDFFF`). This code unit **is not itself an independent Unicode scalar value**; it can be one half of a surrogate pair representing a code point outside the BMP.

## 2. Runnable Java 17+ Program

Create a UTF-8 file named **`CharUtf16Demo.java`**:

~~~java
public class CharUtf16Demo {
    public static void main(String[] args) {
        char letter = 'A';
        char accented = '\u00E9';
        char max = Character.MAX_VALUE;
        char wrapped = (char) (max + 1);

        int rocketCodePoint = 0x1F680;
        String rocket = new String(Character.toChars(rocketCodePoint));

        System.out.println("letter=" + letter);
        System.out.println("letterCode=" + (int) letter);
        System.out.println("accentedCode=" + (int) accented);
        System.out.println("charMin=" + (int) Character.MIN_VALUE);
        System.out.println("charMax=" + (int) max);
        System.out.println("wrapped=" + (int) wrapped);
        System.out.println("letterPlusOne=" + (letter + 1));

        System.out.println("rocketUnits=" + rocket.length());
        System.out.println(
                "rocketPoints=" + rocket.codePointCount(0, rocket.length()));
        System.out.println(
                "highSurrogate=" + Character.isHighSurrogate(rocket.charAt(0)));
        System.out.println(
                "lowSurrogate=" + Character.isLowSurrogate(rocket.charAt(1)));
        System.out.printf("rocketCodePoint=U+%X%n", rocket.codePointAt(0));

        String combining = "e\u0301";
        System.out.println("combiningUnits=" + combining.length());
        System.out.println(
                "combiningPoints="
                + combining.codePointCount(0, combining.length()));
    }
}
~~~

Open **PowerShell (Windows)** or **Bash (Linux/macOS)** in the directory containing the file:

~~~bash
java -version
javac -version
javac -encoding UTF-8 CharUtf16Demo.java
java CharUtf16Demo
~~~

**Expected output:**

~~~text
letter=A
letterCode=65
accentedCode=233
charMin=0
charMax=65535
wrapped=0
letterPlusOne=66
rocketUnits=2
rocketPoints=1
highSurrogate=true
lowSurrogate=true
rocketCodePoint=U+1F680
combiningUnits=2
combiningPoints=2
~~~

**Output explanation:**

- `'A'` carries code 65; `'\u00E9'` is translated into the letter é before the code is parsed, with code unit 233.
- `Character.MAX_VALUE + 1` is computed as `int` yielding 65,536; casting back to `char` takes the low 16 bits, resulting in `0`. This is a **lossy cast**, not Java automatically creating a negative `char`.
- `letter + 1` has result type `int`, so the print statement outputs the number `66` instead of the letter `B`.
- U+1F680 (🚀) is greater than `0xFFFF`; `Character.toChars` creates **two `char` values**, a high surrogate and a low surrogate. Therefore `String.length()` returns `2`, whereas `codePointCount` returns `1`.
- The string `"e\u0301"` consists of `e` and a combining acute accent (two code points), which can render as **one** character. Thus both `length()` and `codePointCount()` equal 2 even though the eye sees a single accented letter.

The example intentionally prints only **ASCII, numbers, and booleans** for special Unicode values so the output is easy to compare across terminals with different font configurations.

## 3. Distinguishing Code Units, Code Points, and Displayed Characters

| Concept | Unit | Example |
| --- | --- | --- |
| **UTF-16 code unit** | A 16-bit value, exact capacity of `char` | Letter `A`: 1 unit; 🚀: 2 units |
| **Unicode code point** | A value of the form `U+XXXX` or `U+XXXXX/XXXXXX` | 🚀 is one code point `U+1F680` |
| **Grapheme cluster** (displayed character) | A cluster perceived by the user as one character | `e` + combining acute accent can render as one letter é |

UTF-16 represents code points from **U+0000 to U+FFFF** (Basic Multilingual Plane — BMP), excluding the surrogate range, using **one code unit**. Code points **U+10000 to U+10FFFF** are represented using a **pair of two code units** (*surrogate pair*).

Formula for a code point `cp` in the range U+10000…U+10FFFF:

~~~text
v = cp - 0x10000
high = 0xD800 + (v >> 10)
low  = 0xDC00 + (v & 0x3FF)
~~~

You do not need to write the calculation above in normal work: Java provides the APIs `Character.toChars(int codePoint)` and `String.codePointAt(int index)`.

### Recommended APIs

| What do you want to do? | API / syntax | Returns |
| --- | --- | --- |
| Get the number of UTF-16 code units in a string | `text.length()` | Number of code units |
| Read one code unit | `text.charAt(i)` | `char`, possibly a surrogate |
| Read the code point starting at a code unit position | `text.codePointAt(i)` | `int` containing the code point |
| Count code points in a string | `text.codePointCount(0, text.length())` | Number of code points |
| Convert a code point to UTF-16 | `Character.toChars(cp)` | A `char[]` array of 1 or 2 elements |
| Iterate over code points | `text.codePoints()` | `IntStream` of code points |

**Important:** The indices for `charAt` and `codePointAt` are still **UTF-16 code unit positions**, not code point indices. If you need to traverse a string containing emojis, use `codePoints()` or `offsetByCodePoints(...)` to avoid splitting a surrogate pair in half.

`codePointCount` does not guarantee counting the exact number of *grapheme clusters*: a visible character can contain multiple code points (combining marks, joined emoji sequences). If a UI needs to count character clusters, you must choose a text segmentation algorithm suitable for the product's requirements.

## 4. Common Mistakes

| Code / assumption | Result | Correct understanding |
| --- | --- | --- |
| `char c = 'A';` | Valid | One code unit |
| `char c = 65;` | Valid | An `int` constant in the `char` range can be assigned at declaration |
| `char c = -1;` | Compile error | Outside the 0–65,535 range |
| `char c = 65536;` | Compile error | Exceeds `Character.MAX_VALUE` |
| `char c = (char) -1;` | Valid, value 65,535 | Cast keeps the low 16 bits |
| `char c = 'AB';` | Compile error | A character literal cannot contain two code units |
| `char c = '🚀';` | Compile error | This code point requires two code units |
| `char c = '\uD83D';` | Syntactically valid | Only **one high surrogate**, not the full 🚀 |
| `String s = "🚀";` | Valid | `s.length()` equals 2 |
| `text.length()` equals the number of visible characters | Not always true | `length()` counts code units |

Because `char` is a primitive integer type in arithmetic, the result of addition/subtraction on `char` typically has type `int`:

~~~java
char c = 'A';
int nextCode = c + 1;     // 66.
char nextChar = (char) (c + 1); // 'B'.
~~~

Do not cast blindly if the operation could exceed the range or split a surrogate pair.

### How Does `char` Differ from `String`?

`'A'` is a `char`, whereas `"A"` is a `String`. A `String` can be 0, 1, or many UTF-16 code units long; a `char` is always exactly **one** code unit. You cannot call `.length()` on a `char`, and you cannot place a non-BMP emoji into a single `char` literal.

## 5. Exercises

1. **Predict:** What do `(int) 'A'` and `'A' + 2` produce?  
   *Answer:* 65 and 67.
2. **Limits:** Why is `char c = 65535;` allowed, whereas `char c = 65536;` is not?  
   *Answer:* `char` only holds 16 unsigned bits, at most 65,535.
3. **Emoji:** Why does `"🚀".length()` equal 2 while `codePointCount` equals 1?  
   *Answer:* U+1F680 is encoded as a surrogate pair, consisting of two code units.
4. **Text traversal:** To retrieve a Unicode code point that might be outside the BMP, should you choose `charAt` or `codePointAt`?  
   *Answer:* `codePointAt` (with a valid code unit index).
5. **Combining marks:** If a string renders as one letter but has two code points, is `codePointCount` guaranteed to return 1?  
   *Answer:* No; for example, `"e\u0301"` has two code points.

## Study Checklist

- [ ] `char` is a **16-bit unsigned UTF-16 code unit**, range 0–65,535.
- [ ] `char` differs from a Unicode code point and differs from a grapheme cluster.
- [ ] A surrogate pair made of **two `char` values** can represent a code point outside the BMP.
- [ ] `String.length()` counts UTF-16 code units, not necessarily visible characters.
- [ ] Operations with `char` usually promote to `int`; narrowing back to `char` can lose information.
- [ ] Know how to use `Character.toChars`, `String.codePointAt`, and `codePointCount` when working with Unicode.

**Conclusion:** When you need to store **a single UTF-16 code unit**, `char` is the exact choice. When you need to store **any Unicode code point**, use `int` alongside `Character`'s Unicode APIs; when processing **text**, use `String` and avoid assuming "one `char` = one character seen by the eye."
