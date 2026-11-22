# `parseUnsignedInt` and `parseUnsignedLong` in Java

## 1. Goal: reading strings representing **unsigned** integers

Java has **signed** primitives `int` (32-bit) and `long` (64-bit), yet binary protocols, system data, checksums, identifiers, or bit fields can describe the same 32/64 bits as an **unsigned integer**.

The two methods:

- `Integer.parseUnsignedInt(String s)`
- `Long.parseUnsignedLong(String s)`

**parse a character string containing an unsigned value** and place the **corresponding bit pattern** into a primitive `int` or `long`. They also have overloads accepting a **radix** (`radix`) and overloads reading a **slice of a `CharSequence`** by index.

Notable point: Java **does not have separate `uint` or `ulong` primitives**. Therefore, an unsigned mathematical value in the upper half of the range is stored in `int`/`long` as a **negative number when interpreted as signed**. This is intentional behavior and does not mean parsing failed.

Example:

~~~java
int bits32 = Integer.parseUnsignedInt("4294967295");
long bits64 = Long.parseUnsignedLong("18446744073709551615");

System.out.println(bits32);                    // -1
System.out.println(bits64);                    // -1
System.out.println(Integer.toUnsignedString(bits32)); // 4294967295
System.out.println(Long.toUnsignedString(bits64));    // 18446744073709551615
~~~

This is **illustrative code**, not a standalone Java program. The two `-1` values are merely the **signed interpretation** of all-1s bit patterns. The `toUnsignedString` methods display the same bits as unsigned values in text form.

**Key takeaway:** `parseUnsigned...` parses **unsigned strings**; it does not create a new unsigned integer type. To compare, divide, take remainders, or print with unsigned semantics, you must continue using the appropriate unsigned APIs.

## 2. Representable range and meaning of bit patterns

| Primitive storing result | Width | Typical signed range | Unsigned value range accepted by parser |
|---|---:|---|---|
| `int` | 32 bits | `-2147483648` to `2147483647` | `0` to `4294967295` (`2^32 - 1`) |
| `long` | 64 bits | `-9223372036854775808` to `9223372036854775807` | `0` to `18446744073709551615` (`2^64 - 1`) |

Important thresholds:

- `Integer.MAX_VALUE = 2147483647`: largest positive signed `int` value.
- `2147483648`: first unsigned value exceeding the positive signed `int` range, stored with bit pattern `0x80000000` and printed as `-2147483648` when signed.
- `4294967295`: largest 32-bit unsigned value, bit pattern `0xFFFFFFFF`, printed as `-1` when signed.
- `Long.MAX_VALUE = 9223372036854775807`.
- `9223372036854775808`: first unsigned value exceeding the positive signed `long` range, bit pattern `0x8000000000000000` and printed as `Long.MIN_VALUE` when signed.
- `18446744073709551615`: largest 64-bit unsigned value, all-1s bit pattern, printed as `-1L` when signed.

When the parser accepts a value `u` within the unsigned range of width `N`:

\[
\text{stored signed} =
\begin{cases}
u & 0 \le u < 2^{N-1}\\
u - 2^N & 2^{N-1} \le u < 2^N
\end{cases}
\]

The formula explains two ways of interpreting **the same bit pattern**; it is not a rule that "Java automatically subtracted `2^N` in the protocol." The negative value you see is the signed representation of the result.

If the input string is `"4294967296"` or `"18446744073709551616"`, it **exceeds the respective unsigned range** and the parser throws `NumberFormatException`. The parser **does not take the remainder modulo `2^N` to silently accept out-of-range strings**.

## 3. Overloads and return types

### `Integer.parseUnsignedInt`

~~~java
static int Integer.parseUnsignedInt(String s)
static int Integer.parseUnsignedInt(String s, int radix)
static int Integer.parseUnsignedInt(
        CharSequence s, int beginIndex, int endIndex, int radix)
~~~

These are **abbreviated API signatures** for reading, not declarations you need to write yourself in Java.

- Without `radix`: uses **base 10**.
- With `radix`: interprets digits in the **specified base**.
- With `CharSequence` and indices: parses only the slice **`[beginIndex, endIndex)`**, meaning it includes `beginIndex` and **excludes** the character at `endIndex`.
- The result is primitive **`int`**, not `long` or a separate unsigned object.

### `Long.parseUnsignedLong`

~~~java
static long Long.parseUnsignedLong(String s)
static long Long.parseUnsignedLong(String s, int radix)
static long Long.parseUnsignedLong(
        CharSequence s, int beginIndex, int endIndex, int radix)
~~~

Similarly, the result is primitive **`long`** with the corresponding 64-bit pattern.

The two `CharSequence` overloads exist in modern JDKs and **work in Java 17+**. They are useful when you need to extract numbers from a multi-field record without creating an intermediate `substring` solely to call the parser. The source data must still be valid within the index range; if the `CharSequence` is mutated concurrently during parsing, stable behavior should not be assumed.

### Reference comparison

| Method | Accepted string range | Returns |
|---|---|---|
| `Integer.parseInt` | 32-bit signed integer | `int` |
| `Integer.parseUnsignedInt` | 32-bit unsigned integer | `int` |
| `Long.parseLong` | 64-bit signed integer | `long` |
| `Long.parseUnsignedLong` | 64-bit unsigned integer | `long` |

A string with value 4,000,000,000 is valid for `Integer.parseUnsignedInt` but invalid for `Integer.parseInt`, because it exceeds `Integer.MAX_VALUE`. **Having the same return type does not mean the two parsers check the same input range.**

## 4. Java 17+ example: signed and unsigned boundaries

Create file `UnsignedParsingBasicsDemo.java`:

~~~java
public class UnsignedParsingBasicsDemo {
    public static void main(String[] args) {
        int intMaxBits = Integer.parseUnsignedInt("4294967295");
        int intHighBits = Integer.parseUnsignedInt("2147483648");
        long longMaxBits =
                Long.parseUnsignedLong("18446744073709551615");
        long longHighBits =
                Long.parseUnsignedLong("9223372036854775808");

        System.out.println("intMaxSigned=" + intMaxBits);
        System.out.println("intMaxUnsigned="
                + Integer.toUnsignedString(intMaxBits));
        System.out.println("intHighSigned=" + intHighBits);
        System.out.println("intHighUnsigned="
                + Integer.toUnsignedString(intHighBits));

        System.out.println("longMaxSigned=" + longMaxBits);
        System.out.println("longMaxUnsigned="
                + Long.toUnsignedString(longMaxBits));
        System.out.println("longHighSigned=" + longHighBits);
        System.out.println("longHighUnsigned="
                + Long.toUnsignedString(longHighBits));
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac UnsignedParsingBasicsDemo.java
java UnsignedParsingBasicsDemo
~~~

Output:

~~~text
intMaxSigned=-1
intMaxUnsigned=4294967295
intHighSigned=-2147483648
intHighUnsigned=2147483648
longMaxSigned=-1
longMaxUnsigned=18446744073709551615
longHighSigned=-9223372036854775808
longHighUnsigned=9223372036854775808
~~~

**Explanation:** the same variable `intMaxBits` can be displayed as `-1` or `4294967295`, depending on the choice of signed/unsigned interpretation when converting to text. No operation "fixes" the bits inside the variable: `Integer.toUnsignedString` simply applies **unsigned formatting rules**.

## 5. Radices from 2 to 36 and digit characters

When specifying `radix`, Java supports valid bases from `Character.MIN_RADIX` (2) to `Character.MAX_RADIX` (36). Characters `0..9` represent values 0..9; in bases greater than 10, `A..Z` or `a..z` can represent values from 10 to 35 according to Java's digit parsing rules.

Some examples:

~~~java
int binary = Integer.parseUnsignedInt("1010", 2);  // 10
int hex = Integer.parseUnsignedInt("ff", 16);      // 255
int base36 = Integer.parseUnsignedInt("Z", 36);    // 35
long maxHex = Long.parseUnsignedLong(
        "FFFFFFFFFFFFFFFF", 16); // all-1s 64-bit pattern, signed -1
~~~

This is an illustrative snippet. When printing as unsigned:

~~~java
Integer.toUnsignedString(hex, 16);    // "ff"
Long.toUnsignedString(maxHex, 16);   // "ffffffffffffffff"
~~~

Base `10` is the default for the `String`-only overload. **Do not confuse radix with text prefixes**: `parseUnsignedInt("0xFF", 16)` does not automatically strip `0x`. If a protocol string has a `0x` prefix, you must validate and strip the prefix first, then parse the digit portion in base 16.

Similarly, `0b` is not automatically recognized. `Integer.parseUnsignedInt("0007")` in base 10 returns 7; leading zeros **do not automatically turn the string into base 8**.

### Unicode digits and protocol constraints

The parser uses Java/Unicode digit recognition rules; you should not assume every valid input **consists strictly of ASCII** across all radices. If a network protocol or security format requires strictly ASCII `0-9` or `0-9A-Fa-f`, you must **validate the allowed character set** before parsing, rather than relying solely on `NumberFormatException`.

This differs from how **Java source-code literal** syntax accepts forms like `0xFF`, `0b1010`, or underscores `1_000`. The parser processes **runtime strings**, not Java literals.

## 6. Valid inputs, plus signs, and cases that must be rejected

For unsigned parsers, a string may have a **leading plus sign `+`** and valid digits, yet **does not accept a minus sign `-` as a negative value**.

Some base-10 examples:

| `String` | `parseUnsignedInt` | Reason |
|---|---|---|
| `"0"` | `0` | Lower bound |
| `"42"` | `42` | Positive number within range |
| `"+42"` | `42` | Leading `+` sign is valid |
| `"0007"` | `7` | Leading zeros |
| `"4294967295"` | `-1` when printed signed | At the 32-bit unsigned upper bound |
| `"4294967296"` | Throws `NumberFormatException` | Exceeds 32-bit unsigned range |
| `"-1"` | Throws `NumberFormatException` | Minus sign is not accepted |
| `" 42"` | Throws `NumberFormatException` | Does not automatically trim whitespace |
| `"4_2"` | Throws `NumberFormatException` | Underscores in runtime strings are invalid |
| `"0xFF"` at radix 10 | Throws `NumberFormatException` | Does not automatically understand base prefixes |

For `Long.parseUnsignedLong`, `"18446744073709551615"` is valid, whereas `"18446744073709551616"` exceeds the upper bound and throws `NumberFormatException`.

**Distinguish data errors from programming errors:**

- `NumberFormatException` indicates the string cannot be parsed into a valid value within the specified range and radix.
- A radix outside 2..36 makes the operation invalid; do not pass user-supplied radices directly into the API without validation.
- With the `CharSequence` slice overload, out-of-bounds indices or an invalid range are read-range errors that need separate control.
- Do not rely on the **exception message text** as an error-handling protocol: JDK versions may phrase errors differently.

You should explicitly decide whether the application allows leading/trailing whitespace, plus signs, extra zeros, uppercase/lowercase hex letters, or Unicode digit forms. The parser does not replace **the protocol's data-formatting rules**.

## 7. Java 17+ example: catching parse errors and validating ranges

Create file `UnsignedInputValidationDemo.java`:

~~~java
public class UnsignedInputValidationDemo {
    static void checkInt(String source) {
        try {
            int bits = Integer.parseUnsignedInt(source);
            System.out.println("int[" + source + "]="
                    + Integer.toUnsignedString(bits));
        } catch (NumberFormatException ex) {
            System.out.println("int[" + source + "]=INVALID");
        }
    }

    static void checkLong(String source) {
        try {
            long bits = Long.parseUnsignedLong(source);
            System.out.println("long[" + source + "]="
                    + Long.toUnsignedString(bits));
        } catch (NumberFormatException ex) {
            System.out.println("long[" + source + "]=INVALID");
        }
    }

    public static void main(String[] args) {
        checkInt("4294967295");
        checkInt("4294967296");
        checkInt("-1");
        checkInt("+42");
        checkInt(" 42");
        checkInt("4_2");
        checkInt("0xFF");

        checkLong("18446744073709551615");
        checkLong("18446744073709551616");
        checkLong("-1");
    }
}
~~~

~~~bash
javac UnsignedInputValidationDemo.java
java UnsignedInputValidationDemo
~~~

Output:

~~~text
int[4294967295]=4294967295
int[4294967296]=INVALID
int[-1]=INVALID
int[+42]=42
int[ 42]=INVALID
int[4_2]=INVALID
int[0xFF]=INVALID
long[18446744073709551615]=18446744073709551615
long[18446744073709551616]=INVALID
long[-1]=INVALID
~~~

The example catches `NumberFormatException` specifically and displays the **unsigned value** or the `INVALID` status. Real-world applications should provide contextual errors such as which field failed, which range is allowed, and may restrict length/character sets prior to parsing to reject inputs incompatible with the protocol.

You should not swallow all exceptions with `catch (Exception)` and return `0`: that mixes valid zeros with malformed strings, hides bugs, and makes diagnosis difficult.

## 8. Using the `CharSequence` overload for part of a string

Since Java 9, the following overloads allow parsing **an index range** of a string directly:

~~~java
Integer.parseUnsignedInt(text, beginIndex, endIndex, radix)
Long.parseUnsignedLong(text, beginIndex, endIndex, radix)
~~~

The data is treated as the character sequence `text[beginIndex .. endIndex-1]`. For example, a record storing 16-bit hex in `"id=FFFF;"` has its numeric portion starting at index 3 and ending **before** index 7.

Create file `UnsignedRadixSliceDemo.java`:

~~~java
public class UnsignedRadixSliceDemo {
    public static void main(String[] args) {
        int binary = Integer.parseUnsignedInt("1010", 2);
        int hex = Integer.parseUnsignedInt("ff", 16);
        int base36 = Integer.parseUnsignedInt("Z", 36);

        String record = "id=FFFF;";
        int sliced = Integer.parseUnsignedInt(record, 3, 7, 16);

        long longHex =
                Long.parseUnsignedLong("FFFFFFFFFFFFFFFF", 16);

        System.out.println("binary=" + binary);
        System.out.println("hex=" + hex);
        System.out.println("base36=" + base36);
        System.out.println("slice=" + sliced);
        System.out.println("hexBack="
                + Integer.toUnsignedString(hex, 16));
        System.out.println("longHex="
                + Long.toUnsignedString(longHex, 16));
    }
}
~~~

~~~bash
javac UnsignedRadixSliceDemo.java
java UnsignedRadixSliceDemo
~~~

Output:

~~~text
binary=10
hex=255
base36=35
slice=65535
hexBack=ff
longHex=ffffffffffffffff
~~~

You must **verify the field boundaries `beginIndex`/`endIndex` yourself** before using them on variable-length records. If a string has delimiters, do not hardcode fixed offsets when the format can vary. Using the slice overload avoids allocating an extra `substring` in some scenarios, though it is **not guaranteed** to be faster for every input/JVM; measure if performance is an actual requirement.

## 9. Parsing unsigned does not make arithmetic operators unsigned

After parsing, the variable is still a signed `int` or `long`. Therefore:

~~~java
int a = Integer.parseUnsignedInt("4294967295");
int b = 2;

System.out.println(a);           // -1
System.out.println(a > b);       // false: signed comparison!
System.out.println(a / b);       // 0: signed division (-1 / 2)
~~~

This is an illustrative snippet. If you want the meaning "4,294,967,295 is greater than 2", `a > b` is inappropriate. Java provides unsigned APIs:

| Goal | 32-bit form | 64-bit form |
|---|---|---|
| Compare | `Integer.compareUnsigned(a,b)` | `Long.compareUnsigned(a,b)` |
| Divide | `Integer.divideUnsigned(a,b)` | `Long.divideUnsigned(a,b)` |
| Remainder | `Integer.remainderUnsigned(a,b)` | `Long.remainderUnsigned(a,b)` |
| Display decimal | `Integer.toUnsignedString(a)` | `Long.toUnsignedString(a)` |
| Display other radix | `Integer.toUnsignedString(a,radix)` | `Long.toUnsignedString(a,radix)` |

For a 32-bit pattern, `Integer.toUnsignedLong(a)` converts the **32-bit unsigned value** to a non-negative `long`, because the entire 0..4294967295 range fits inside `long`.

For a 64-bit pattern, **it is impossible to store all 64-bit unsigned values as positive numbers in a primitive `long`**. If the problem requires the exact positive magnitude of numbers exceeding `Long.MAX_VALUE`, use `BigInteger` or an unsigned string representation.

### Java 17+ example: unsigned comparison, division, and remainder

Create file `UnsignedArithmeticDemo.java`:

~~~java
public class UnsignedArithmeticDemo {
    public static void main(String[] args) {
        int a = Integer.parseUnsignedInt("4294967295");
        int two = 2;

        System.out.println("signedValue=" + a);
        System.out.println("unsignedValue="
                + Integer.toUnsignedString(a));
        System.out.println("signedCompare=" + (a > two));
        System.out.println("unsignedCompare="
                + (Integer.compareUnsigned(a, two) > 0));
        System.out.println("unsignedDivision="
                + Integer.divideUnsigned(a, two));
        System.out.println("unsignedRemainder="
                + Integer.remainderUnsigned(a, two));
        System.out.println("widenedUnsigned="
                + Integer.toUnsignedLong(a));

        long big = Long.parseUnsignedLong("18446744073709551615");
        System.out.println("bigUnsigned="
                + Long.toUnsignedString(big));
        System.out.println("bigCompare="
                + (Long.compareUnsigned(big, 1L) > 0));
        System.out.println("bigDivision="
                + Long.toUnsignedString(Long.divideUnsigned(big, 2L)));
        System.out.println("bigRemainder="
                + Long.toUnsignedString(Long.remainderUnsigned(big, 2L)));
    }
}
~~~

~~~bash
javac UnsignedArithmeticDemo.java
java UnsignedArithmeticDemo
~~~

Output:

~~~text
signedValue=-1
unsignedValue=4294967295
signedCompare=false
unsignedCompare=true
unsignedDivision=2147483647
unsignedRemainder=1
widenedUnsigned=4294967295
bigUnsigned=18446744073709551615
bigCompare=true
bigDivision=9223372036854775807
bigRemainder=1
~~~

Only the **interpretation of the bit pattern** changes, not the primitive type. Note that `Integer.divideUnsigned` returns **`int`** and `Long.divideUnsigned` returns **`long`**: if an unsigned quotient itself exceeds the signed range, printing it directly with `println` can still look negative; use `toUnsignedString` when proper unsigned display is needed.

**Addition, subtraction, and multiplication on `int`/`long`** still compute at fixed width modulo `2^32`/`2^64` on overflow as defined by Java. Unsigned parsing does not prevent wraparound. If you need unsigned range checks without wraparound, you must write explicit checking logic or choose a sufficiently wide numeric type.

## 10. `BigInteger` when exact mathematical values outside the signed range are needed

For 32-bit unsigned values, a straightforward way to obtain a **non-negative value in a primitive** is:

~~~java
int bits = Integer.parseUnsignedInt("4294967295");
long unsignedMagnitude = Integer.toUnsignedLong(bits); // 4294967295
~~~

For 64-bit unsigned values, use `BigInteger` if the program needs to compute the **exact mathematical magnitude** of 18,446,744,073,709,551,615:

~~~java
String text = "18446744073709551615";
long bits = Long.parseUnsignedLong(text);
java.math.BigInteger magnitude =
        new java.math.BigInteger(Long.toUnsignedString(bits));
~~~

This is an illustrative snippet. `new BigInteger(text)` can also parse that large unsigned decimal string because `BigInteger` is not limited to 64 bits. However, `Long.parseUnsignedLong` remains useful if the primary goal is holding **64 bits** for exchange in Java structures/protocols.

### Java 17+ example: comparing exact values and wraparound

Create file `UnsignedBigIntegerDemo.java`:

~~~java
import java.math.BigInteger;

public class UnsignedBigIntegerDemo {
    public static void main(String[] args) {
        String maxUnsigned = "18446744073709551615";

        long bits = Long.parseUnsignedLong(maxUnsigned);
        BigInteger exact = new BigInteger(maxUnsigned);
        BigInteger recovered =
                new BigInteger(Long.toUnsignedString(bits));

        System.out.println("storedSigned=" + bits);
        System.out.println("recovered=" + recovered);
        System.out.println("matches=" + exact.equals(recovered));
        System.out.println("exactPlusOne="
                + exact.add(BigInteger.ONE));
        System.out.println("longPlusOneUnsigned="
                + Long.toUnsignedString(bits + 1L));
    }
}
~~~

~~~bash
javac UnsignedBigIntegerDemo.java
java UnsignedBigIntegerDemo
~~~

Output:

~~~text
storedSigned=-1
recovered=18446744073709551615
matches=true
exactPlusOne=18446744073709551616
longPlusOneUnsigned=0
~~~

The line `longPlusOneUnsigned=0` is **wraparound**: an all-1s 64-bit pattern plus 1 becomes an all-0s 64-bit pattern. `BigInteger` continues representing the incremented result accurately. Which option is right depends on the protocol: checksums/bit fields may intentionally work modulo `2^64`, whereas money/quantity/record calculations must have a policy that does not lose value.

## 11. Converting back and forth and true round-trips

If a field is defined as **32-bit unsigned** or **64-bit unsigned**, design a clear processing pipeline:

1. **String input:** parse with `Integer.parseUnsignedInt` / `Long.parseUnsignedLong` using the specified radix.
2. **Storage:** keep the bit pattern in `int` / `long`.
3. **Computation:** use signed/unsigned APIs according to the desired semantics.
4. **Text output:** use `Integer.toUnsignedString` / `Long.toUnsignedString` with the desired radix.
5. **Verification:** check whether string → bit pattern → string → bit pattern round-trips preserve the value/bits.

Example:

~~~java
int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
String out = Integer.toUnsignedString(bits, 16); // "ffffffff"
int parsedAgain = Integer.parseUnsignedInt(out, 16);
boolean sameBits = bits == parsedAgain; // true
~~~

The round-trip here preserves the **bit** value, but **does not preserve the uppercase/lowercase casing of the original string**. If a protocol requires uppercase hex or fixed padding of 8/16 digits, format separately; `toUnsignedString` does not insert leading zeros and typically outputs lowercase letters according to the radix.

**Mandatory boundary tests:** `0`, `1`, signed max, unsigned min above signed max, unsigned max, string exceeding upper bound by 1, radices 2/10/16, prefixes, leading plus, whitespace, invalid characters.

## 12. Common pitfalls and how to avoid them

| Misconception | Reality |
|---|---|
| "`parseUnsignedInt` returns a `uint` type." | Java has no `uint` primitive; the result is still `int`. |
| "Parsing `4294967295` into `-1` loses data." | No: the 32-bit pattern is intact, just displayed as signed. |
| "`parseUnsignedLong` returns `BigInteger` when exceeding `Long.MAX_VALUE`." | No: it returns `long` holding the 64-bit pattern; use `BigInteger` if a positive magnitude wider than signed is needed. |
| "`parseUnsignedInt("4294967296")` turns into 0." | No: the parser rejects values exceeding the unsigned range with `NumberFormatException`. |
| "Unsigned parsers allow a minus sign because the result can be negative." | No: `"-1"` is rejected; negative numbers when printed are the signed interpretation of the bit pattern. |
| "You can pass `"0xFF"` directly to radix 16." | No: the `0x` prefix must be handled before parsing. |
| "Underscores in Java literals also work in String parsing." | No: `"1_000"` is not a valid digit string for the parser. |
| "`parseUnsignedInt` automatically trims whitespace." | No: a normalize/trim policy outside the parser is required if allowed. |
| "Using the `>` operator after parsing performs unsigned comparison." | No: `int`/`long` still compare as signed; use `compareUnsigned`. |
| "Using `/` performs unsigned division because the number was parsed unsigned." | No: use `divideUnsigned` when unsigned semantics are needed. |
| "Unsigned parsing prevents overflow during addition." | No: it only checks bounds **at parse time**; subsequent operations need their own policy. |
| "`Integer.toUnsignedString` must return the exact same string as input." | No: the value/bits are preserved, though formatting may change, e.g., uppercase hex becoming lowercase. |

## 13. Checklist for integrating into real applications

1. **Determine width and semantics:** is the field signed or unsigned, 32-bit or 64-bit?
2. **Determine radix:** 10, 16, or another base; does the string have a prefix?
3. **Define input format:** are `+` signs, leading zeros, whitespace, or Unicode digits allowed? If not, validate beforehand.
4. **Use the right parser:** `Integer.parseUnsignedInt` or `Long.parseUnsignedLong`; do not use `parseInt`/`parseLong` if protocol values can exceed signed max.
5. **Catch `NumberFormatException` at the input boundary:** turn it into a specific field error, never silently substitute 0.
6. **Keep unsigned intent clear:** variable names like `unsignedBits` or structural documentation; readers must not mistake signed `-1` for an error.
7. **Use unsigned comparison/division/remainder when needed:** `compareUnsigned`, `divideUnsigned`, `remainderUnsigned`.
8. **Use appropriate string output methods:** `toUnsignedString` rather than raw signed printing when displaying unsigned numbers.
9. **Control subsequent arithmetic overflow:** use `BigInteger` when mathematical magnitude must not be lost; or document bit-width modulo if intended by the protocol.
10. **Test boundaries, radices, and round-trips:** at minimum unsigned max, unsigned max + 1, values with the sign bit set, invalid characters, and all permitted formats.

## 14. Self-check exercises

1. Why does `Integer.parseUnsignedInt("4294967295")` return an `int` that prints as `-1` yet still succeeds?
2. Can `Integer.parseInt("4294967295")` be used instead? Why or why not?
3. What type does `Long.parseUnsignedLong("18446744073709551615")` return, and what number does it print as signed?
4. Does the 32-bit unsigned parser automatically take modulo on `"4294967296"`?
5. What does `Integer.parseUnsignedInt("FF", 16)` return? Can `"0xFF"` with the same radix be parsed directly?
6. How do `Integer.parseUnsignedInt("+42")` and `Integer.parseUnsignedInt("-42")` differ?
7. Why does `Integer.parseUnsignedInt("4294967295") > 0` evaluate to `false` even though the unsigned value is a large positive number?
8. If you need to divide 32-bit unsigned max by 2, which API should you call?
9. If you need to add 1 to 64-bit unsigned max **while preserving the exact mathematical result**, which type should you choose?
10. Why might `toUnsignedString(bits, 16)` not reproduce the exact casing of the original hex input string?

**Answer hints:** (1) An all-1s 32-bit pattern is unsigned max but signed `-1`. (2) No, it exceeds `Integer.MAX_VALUE`. (3) Primitive `long`, prints signed `-1`. (4) No, throws `NumberFormatException`. (5) 255; `"0xFF"` needs the prefix stripped. (6) `+42` is valid, `-42` is invalid. (7) Operator `>` on `int` is signed; use `Integer.compareUnsigned`. (8) `Integer.divideUnsigned(bits, 2)`. (9) `BigInteger`. (10) The method returns a normalized numeric representation in the radix, not preserving original text formatting.

**Key takeaway:** `parseUnsignedInt` and `parseUnsignedLong` validate the **unsigned string range** yet still return signed primitives `int`/`long` **preserving the bit pattern**. When displaying the true unsigned magnitude, use `toUnsignedString`; when comparing, dividing, or taking remainders unsigned, use the corresponding APIs. If exact arithmetic beyond 64 unsigned bits is required, use `BigInteger`.
