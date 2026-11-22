# Converting `char` with `byte` or `short` in Java

## 1. Why are conversions between 8- and 16-bit types error-prone?

In Java, `char`, `byte`, and `short` are all **integral primitive types**, yet they do not represent the same value range.

| Type | Size | Signed? | Integer range | Primary role |
|---|---:|---|---|---|
| `byte` | 8 bits | Yes | `-128` to `127` | Byte data, 8-bit integer |
| `short` | 16 bits | Yes | `-32768` to `32767` | 16-bit signed integer |
| `char` | 16 bits | **No** | `0` to `65535` | **One UTF-16 code unit** |

The most important point is that **`char` and `short` are both 16 bits wide yet differ in how they interpret the highest bit**. For `short`, the highest bit participates in representing the sign; for `char`, all 16 bits form a value from 0 to 65535. Meanwhile, `byte` is only 8 bits and is also a signed type.

Therefore, conversions between `char` and `byte` or `short` are classified as **narrowing primitive conversions** under Java's rules, even though `short` and `char` are both 16 bits. There is no direct *widening primitive conversion* between these pairs of types.

Note: "narrowing" in the specification does not only mean fewer bits. It can also mean **the target value range does not contain every value of the source range**. For example, `char` accepts `40000` while `short` cannot hold the positive integer `40000`, even though both are 16 bits.

## 2. Implicit conversion and explicit conversion

For **ordinary variables**, Java does not permit direct assignment from `byte` or `short` to `char`, nor from `char` to `byte`/`short`:

~~~java
byte b = 65;
short s = 65;
char c = 'A';

// Does not compile:
// char fromByte = b;
// char fromShort = s;
// byte fromChar = c;
// short otherFromChar = c;
~~~

This is an **illustrative snippet** intentionally containing commented-out error lines. Assignments between these types require an **explicit cast**:

~~~java
char fromByte = (char) b;
char fromShort = (char) s;
byte fromChar = (byte) c;
short otherFromChar = (short) c;
~~~

The two snippets share the same variable context; they are not standalone programs.

A cast merely says "perform the conversion according to Java's rules." It **does not guarantee the arithmetic value is preserved**, does not check whether the data makes sense as a valid character, and is not a text-decoding operation.

### Important exception: constant expressions

Java allows **narrowing of constant expressions upon assignment** in certain cases: a constant expression of type `byte`, `short`, `char`, or `int` whose value lies within the target type's range can be assigned without a cast:

~~~java
char letter = 65;   // int constant 65 fits in char
byte small = 65;    // int constant 65 fits in byte
short number = 'A'; // char constant 65 fits in short
~~~

By contrast:

~~~java
int variable = 65;
// char invalid = variable; // does not compile: int variable cannot be implicitly narrowed
~~~

This explains why `char c = 65;` is valid while `int n = 65; char c = n;` is invalid. Do not conclude from constant syntax that Java supports implicit conversion between `byte`, `short`, and `char` variables.

## 3. From `byte` to `char`: negative numbers become large values

A signed `byte` takes negative values from `-128` to `-1`. When cast to `char`, Java converts according to the rule **widen from `byte` to `int`, then narrow to `char`**, which is equivalent in result to keeping the low 16 bits after sign extension.

For example:

~~~java
byte b = -1;
char c = (char) b;
// (int) c == 65535; hex code of c is FFFF
~~~

Because `b` equals `-1`, when sign-extended to `int`, the high twenty-four bits are also 1. Narrowing down to 16 bits produces `0xFFFF`. `char` interprets `0xFFFF` as **65535**, not `-1`.

| Source `byte` | 8-bit hex | `(int) (char) b` value | `char` hex |
|---:|---|---:|---|
| `0` | `00` | `0` | `0000` |
| `65` | `41` | `65` | `0041` |
| `127` | `7F` | `127` | `007F` |
| `-1` | `FF` | `65535` | `FFFF` |
| `-128` | `80` | `65408` | `FF80` |

**Warning:** Casting a negative `byte` directly to `char` will **not** give you an unsigned 0-to-255 interpretation of that byte. If you are processing binary data and want the **unsigned byte** value, use:

~~~java
byte b = (byte) 0xFF;
int unsigned = Byte.toUnsignedInt(b); // 255
int masked = b & 0xFF;               // 255
char unit = (char) unsigned;         // U+00FF if you genuinely want that code unit
~~~

This is an illustrative snippet. `Byte.toUnsignedInt(b)` and `b & 0xFF` yield an `int` value from 0 to 255. Casting onward to `char` only makes sense when you are **genuinely mapping that numeric value to a UTF-16 code unit**, not decoding UTF-8 or determining a character in an arbitrary charset.

## 4. From `short` to `char`: same bits, different sign meaning

`short` and `char` are both 16 bits. When converting `short` to `char`, Java keeps the low 16 bits, but `char` always interprets them as an **unsigned** value.

For example:

~~~java
short s = -1;
char c = (char) s;
// (int) c == 65535 (0xFFFF)
~~~

Some illustrative values:

| Source `short` | 16-bit hex | `char` value after cast |
|---:|---|---:|
| `0` | `0000` | `0` |
| `65` | `0041` | `65` |
| `32767` | `7FFF` | `32767` |
| `-32768` | `8000` | `32768` |
| `-1` | `FFFF` | `65535` |

A negative `short` does not become a "negative-number character." It becomes a code unit with the same 16-bit pattern and an unsigned numeric value. Java provides `Short.toUnsignedInt(shortValue)` to interpret a `short`'s 16-bit pattern as an `int` from 0 to 65535.

For instance, `Short.toUnsignedInt((short) -1)` equals 65535, matching `(int) (char) ((short) -1)` in **numeric value**. However, when the goal is processing unsigned 16-bit binary numbers, `int` usually expresses the intent much more clearly than `char`; reserve `char` for APIs dealing with UTF-16 code units.

## 5. From `char` to `byte`: loses high 8 bits and can flip sign

When casting `char` down to `byte`, Java keeps the **lowest 8 bits**. The result is interpreted as an **8-bit signed** integer:

~~~java
char c1 = '\u0041'; // 'A' = 65
char c2 = '\u00FF'; // 255
char c3 = '\u0100'; // 256

byte b1 = (byte) c1; // 65
byte b2 = (byte) c2; // -1 (0xFF)
byte b3 = (byte) c3; // 0  (0x0100 -> 0x00)
~~~

Example table:

| Source `char` | 16-bit hex | `(byte) c` | Explanation |
|---:|---|---:|---|
| `65` | `0041` | `65` | Within signed `byte` range |
| `127` | `007F` | `127` | Largest positive value of `byte` |
| `128` | `0080` | `-128` | Target byte's sign bit is 1 |
| `255` | `00FF` | `-1` | Keeps `FF`, signed interpretation |
| `256` | `0100` | `0` | High 8 bits discarded |
| `65535` | `FFFF` | `-1` | All low 8 bits are 1 |

This is a **numeric data conversion**. If `char` represents a Unicode character, casting to `byte` **does not mean converting the character to UTF-8**. UTF-8 uses an encoding algorithm and may require multiple bytes for a single code point. The encoding section later gives a concrete example.

## 6. From `char` to `short`: values above 32767 become negative

From `char` (0..65535) to `short` (-32768..32767), Java preserves the 16 bits and interprets them as a signed integer:

~~~java
char a = (char) 32767;
char b = (char) 32768;
char c = (char) 65535;

short s1 = (short) a; // 32767
short s2 = (short) b; // -32768
short s3 = (short) c; // -1
~~~

No bits are dropped when converting `char` to `short`, since both are 16 bits wide. However, the **mathematical value can change sign** due to how the highest bit is interpreted. You can think of the equivalent formula:

- For `c <= 32767`: `(short) c` keeps the numeric value.
- For `c >= 32768`: `(short) c` equals `(int) c - 65536`.

Why is a cast needed even though the bit count does not decrease? Because values like `65535` are inside `char`'s range yet outside `short`'s range. Java requires making the change in sign interpretation explicit.

## 7. All four conversions in a complete Java 17+ program

Create the file `CharByteShortDemo.java`:

~~~java
public class CharByteShortDemo {
    public static void main(String[] args) {
        byte b = 65;
        short s = 65;
        char a = 'A';

        System.out.println("byteToChar=" + (int) (char) b);
        System.out.println("shortToChar=" + (int) (char) s);
        System.out.println("charToByte=" + (byte) a);
        System.out.println("charToShort=" + (short) a);

        byte negativeByte = -1;
        short negativeShort = -1;
        System.out.printf("negativeByteToChar=U+%04X%n",
                (int) (char) negativeByte);
        System.out.printf("negativeShortToChar=U+%04X%n",
                (int) (char) negativeShort);

        char ff = (char) 0x00FF;
        char highBit = (char) 0x8000;
        System.out.println("FFToByte=" + (byte) ff);
        System.out.println("FFToShort=" + (short) ff);
        System.out.println("8000ToShort=" + (short) highBit);
    }
}
~~~

Compile and run in the directory containing the file using JDK 17 or later:

~~~bash
javac CharByteShortDemo.java
java CharByteShortDemo
~~~

Exact output:

~~~text
byteToChar=65
shortToChar=65
charToByte=65
charToShort=65
negativeByteToChar=U+FFFF
negativeShortToChar=U+FFFF
FFToByte=-1
FFToShort=255
8000ToShort=-32768
~~~

Starting from `65`, all four conversion directions preserve the value because it lies in the common range of all three types. However, `-1` converts to `char` 65535; `char` 255 narrowed to `byte` becomes -1; `char` 32768 converted to `short` becomes -32768. These results do not depend on how the screen displays characters; they come from integer rules.

## 8. When bytes from network or files are used as unsigned numbers

Many binary formats define an **unsigned** 8-bit or 16-bit field. Since Java has no dedicated `unsigned byte` or `unsigned short` primitive, programmers commonly store raw bits in `byte`/`short` and interpret them using `int`:

- `Byte.toUnsignedInt(byteValue)` returns values 0..255.
- `Short.toUnsignedInt(shortValue)` returns values 0..65535.
- `byteValue & 0xFF` is equivalent in value to reading an unsigned byte.
- `shortValue & 0xFFFF` is equivalent in value to reading an unsigned short.

Create the file `UnsignedNumbersDemo.java`:

~~~java
public class UnsignedNumbersDemo {
    public static void main(String[] args) {
        byte rawByte = (byte) 0xFF;
        short rawShort = (short) 0xFFFF;

        int unsignedByte = Byte.toUnsignedInt(rawByte);
        int unsignedShort = Short.toUnsignedInt(rawShort);

        char directByteCast = (char) rawByte;
        char unsignedByteAsChar = (char) unsignedByte;

        System.out.println("signedByte=" + rawByte);
        System.out.println("unsignedByte=" + unsignedByte);
        System.out.println("maskedByte=" + (rawByte & 0xFF));
        System.out.printf("directByteCast=U+%04X%n",
                (int) directByteCast);
        System.out.printf("unsignedByteAsChar=U+%04X%n",
                (int) unsignedByteAsChar);

        System.out.println("signedShort=" + rawShort);
        System.out.println("unsignedShort=" + unsignedShort);
        System.out.println("maskedShort=" + (rawShort & 0xFFFF));
        System.out.printf("directShortCast=U+%04X%n",
                (int) (char) rawShort);
    }
}
~~~

~~~bash
javac UnsignedNumbersDemo.java
java UnsignedNumbersDemo
~~~

Output:

~~~text
signedByte=-1
unsignedByte=255
maskedByte=255
directByteCast=U+FFFF
unsignedByteAsChar=U+00FF
signedShort=-1
unsignedShort=65535
maskedShort=65535
directShortCast=U+FFFF
~~~

**Important difference:** a direct cast `(char) rawByte` when the raw byte is `-1` produces `U+FFFF`; converting through `Byte.toUnsignedInt` first and then casting produces `U+00FF`. The two results differ even though both start from the byte bit pattern `FF`.

For a raw `short`, casting to `char` and interpreting as unsigned 16-bit yield the same number 0..65535, yet the **data semantics** remain different: an unsigned 16-bit measurement or protocol field does not automatically become a Unicode character.

## 9. Numeric conversion is not text encoding or decoding

`char` is **one UTF-16 code unit**, while `byte` is **one 8-bit data unit**. Casting between them only executes the primitive conversion rules from the earlier sections. A cast **knows nothing about charsets** and does not perform UTF-8/UTF-16 algorithms.

For example, the letter `é` is code point `U+00E9`. When encoded in UTF-8, it uses **two bytes `C3 A9`**, not just a single byte `E9`. Each of those UTF-8 bytes, when read into a primitive `byte`, has signed values `-61` and `-87` (respectively).

If you cast each byte to `char`, Java merely sign-extends/narrows bits: `(char) (byte) 0xC3` gives `U+FFC3`, and `(char) (byte) 0xA9` gives `U+FFA9`. The result is **not** the text `é`.

To decode properly, use a charset API:

~~~java
import java.nio.charset.StandardCharsets;

public class Utf8DecodeDemo {
    public static void main(String[] args) {
        byte[] encoded = {(byte) 0xC3, (byte) 0xA9};
        String decoded = new String(encoded, StandardCharsets.UTF_8);

        System.out.println("decoded=" + decoded);
        System.out.println("units=" + decoded.length());
        System.out.printf("unit=U+%04X%n", (int) decoded.charAt(0));
        System.out.printf("wrongFirst=U+%04X%n",
                (int) (char) encoded[0]);
        System.out.printf("wrongSecond=U+%04X%n",
                (int) (char) encoded[1]);
    }
}
~~~

~~~bash
javac Utf8DecodeDemo.java
java Utf8DecodeDemo
~~~

Output:

~~~text
decoded=é
units=1
unit=U+00E9
wrongFirst=U+FFC3
wrongSecond=U+FFA9
~~~

Only after decoding the `byte[]` with `StandardCharsets.UTF_8` does it become the proper `String`. When you need to turn a string into bytes according to a charset, use `text.getBytes(StandardCharsets.UTF_8)`. This is an essential rule for files, JSON, HTTP, and network data.

Note that `char` represents only **one UTF-16 code unit**, so even when decoded properly, a Unicode code point outside the BMP (such as an emoji) can occupy **two** `char` values in a `String`. Do not treat an arbitrary byte or char as "one user-visible character."

## 10. Arithmetic with `char`, `byte`, and `short` is promoted

In most arithmetic expressions, `byte`, `short`, and `char` are **promoted to `int`**. Therefore:

~~~java
byte b = 1;
short s = 2;
char c = 'A';

int sum = b + s + c;     // int: 1 + 2 + 65 = 68
int nextCode = c + 1;    // int: 66

// Does not compile:
// char next = c + 1;
// byte smallSum = b + 1;
~~~

This is an illustrative snippet (invalid statements are commented out). Even though `char` is an unsigned integer type, the result of `c + 1` has type `int`. Casting back to `char` can wrap around to the low 16 bits:

~~~java
char max = Character.MAX_VALUE;     // 65535
char wrapped = (char) (max + 1);    // 0
~~~

An explicit cast does not check for overflow. For ordinary arithmetic, keep the result in `int` and check the range before casting to a narrower type; `Math.toIntExact` only checks `long`-to-`int` conversions, **not** `int`-to-`char`/`byte`/`short` conversions.

### How to check the range instead of truncating bits?

Suppose an API receives `int codeUnit` and must return a `char` preserving its value:

~~~java
if (codeUnit < Character.MIN_VALUE || codeUnit > Character.MAX_VALUE) {
    throw new IllegalArgumentException("out of char range");
}
char unit = (char) codeUnit;
~~~

This illustrative snippet ensures the numeric value lies in 0..65535 before casting. However, "within the `char` range" **does not necessarily mean a complete Unicode scalar value**: the range `U+D800`–`U+DFFF` consists of surrogate code units, which must appear in pairs when representing code points outside the BMP.

For signed `byte` and `short`, check `Byte.MIN_VALUE`/`Byte.MAX_VALUE` or `Short.MIN_VALUE`/`Short.MAX_VALUE` in the same way. If you want to interpret an unsigned byte, check 0..255 or use `Byte.toUnsignedInt` on the raw byte.

## 11. Data-loss examples and round-trip properties

A *round-trip* is converting from type A to type B and then back to A. Not every round-trip preserves the value.

Create the file `NarrowingRoundTripDemo.java`:

~~~java
public class NarrowingRoundTripDemo {
    public static void main(String[] args) {
        char original = '\u0100'; // 256
        byte narrowed = (byte) original; // 0
        char restored = (char) narrowed; // 0

        char small = 'A';
        byte smallByte = (byte) small;
        char smallRestored = (char) smallByte;

        short negativeShort = -1;
        char unsignedUnit = (char) negativeShort;
        short sameBits = (short) unsignedUnit;

        System.out.println("original=" + (int) original);
        System.out.println("narrowed=" + narrowed);
        System.out.println("restored=" + (int) restored);
        System.out.println("smallRoundTrip=" + (small == smallRestored));
        System.out.println("shortBitsRoundTrip=" + (negativeShort == sameBits));
        System.out.println("charUnsignedValue=" + (int) unsignedUnit);
    }
}
~~~

~~~bash
javac NarrowingRoundTripDemo.java
java NarrowingRoundTripDemo
~~~

Output:

~~~text
original=256
narrowed=0
restored=0
smallRoundTrip=true
shortBitsRoundTrip=true
charUnsignedValue=65535
~~~

In the first example, `char` with value 256 loses its high bit when converted through `byte` and cannot recover the original information. In the second example, `'A'` equals 65, which lies in `byte`'s safe range, so it is preserved. In the third example, going from `short -1` to `char 65535` and back to `short -1` preserves the **bit pattern**, though the intermediate numeric value differs.

Make sure to distinguish clearly:

- **Preserving bit pattern:** keeping bits within a given width.
- **Preserving numeric value:** the arithmetic result matches the original.
- **Preserving text:** code points/characters retain the same meaning after encoding/decoding.

A conversion can preserve a bit pattern while changing the numeric value, or lose data without any exception.

## 12. Common mistakes and how to avoid them

| Misconception | Reality |
|---|---|
| "`char` and `short` are both 16 bits so they can be assigned directly." | No: their numeric ranges differ; a cast is required when working with variables. |
| "`byte` to `char` is widening because `char` has 16 bits." | There is no direct `byte → char` widening; a cast is mandatory. |
| "`(char) (byte) -1` equals 255." | Wrong: it equals 65535 (`U+FFFF`); for unsigned byte 255, use `Byte.toUnsignedInt` first. |
| "`(short) (char) 65535` equals 65535." | Wrong: the `short` result is -1. |
| "`(byte) '\u0100'` throws an overflow error." | Wrong: the primitive cast yields 0 after discarding the high 8 bits. |
| "Casting bytes to char will read UTF-8 properly." | Wrong: a decoder is needed, such as `new String(bytes, StandardCharsets.UTF_8)`. |
| "The result of `char + 1` is still `char`." | Wrong: the expression is promoted to `int`. |
| "`Math.toIntExact` checks casting `int` to `byte`." | Wrong: this API only converts `long → int`. |
| "One `char` equals one visible Unicode character." | Wrong: `char` is one UTF-16 code unit; one code point may need two code units. |

## 13. Checklist when converting `char` with `byte`/`short`

1. **Identify the data:** are you doing arithmetic, reading a binary field, handling a UTF-16 code unit, or decoding text?
2. **Identify sign interpretation:** `byte`/`short` are signed, `char` is unsigned. Can the input be negative?
3. **Check valid range:** is the input guaranteed to lie within the target type's representable range when values must be preserved?
4. **Check the goal:** do you want to preserve the **numeric value**, preserve the **bit pattern**, or recover **text**? Those three goals demand different approaches.
5. **Choose the right API:** `Byte.toUnsignedInt`/`Short.toUnsignedInt` to read unsigned values; charset decoders to read bytes into strings; casts only when you truly want Java numeric conversion.
6. **Test boundaries:** `-128`, `-1`, `0`, `127`, `128`, `255`, `256`, `32767`, `32768`, `65535`, plus multi-byte Unicode / surrogate pairs when handling text.

## 14. Self-check

1. Why can a `short` variable not be assigned directly to a `char` even though both are 16 bits?
2. Is `(int) (char) ((byte) -1)` equal to 255 or 65535? Explain.
3. What does `(byte) ((char) 256)` equal? What information is lost?
4. What does `(short) ((char) 0x8000)` equal, and why?
5. If a protocol transmits byte `0xFF` representing unsigned number 255, should you use `(char) rawByte` or `Byte.toUnsignedInt(rawByte)` for calculations?
6. Why can a UTF-8 sequence of two bytes `C3 A9` not recover the letter `é` via two `(char)` casts?
7. Does `char c = 65;` compile? What about `int x = 65; char c = x;`?
8. What numeric value does `char max = Character.MAX_VALUE; char next = (char) (max + 1);` produce?

**Answer hints:** (1) Different ranges and sign interpretation mean there is no widening between `short` and `char`. (2) 65535 due to sign extension of `byte -1` before narrowing to 16 bits. (3) 0, losing the high eight bits. (4) -32768, preserving the bit pattern `8000` while `short` is signed. (5) `Byte.toUnsignedInt`. (6) UTF-8 is a multi-byte encoding and must be decoded with a charset. (7) The first compiles because constant 65 fits in `char`; the second does not compile without a cast. (8) 0 because the cast keeps the low 16 bits.

**Remember:** Between `char` and `byte` or `short`, Java requires an **explicit cast** for variables because their value ranges and sign interpretations differ. Casting can preserve bits, flip signs, or drop bits; when handling unsigned binary values use the unsigned reading APIs, and when handling text use an appropriate charset decoder.
