# BigInteger: Creating from String, Radix, long, or Byte Array

> **Java core – numbers · BigInteger**  
> **Goal:** Choose the right way to initialize `java.math.BigInteger` from decimal text, radix-based text, `long` primitive, signed `byte[]` binary data, and unsigned binary data; read big-endian/two's complement properly, handle signs, invalid input, byte widths, and verify round-trip conversions.

## 1. What Problem Does BigInteger Solve?

Primitive integer types in Java have fixed widths:

| Type | Width | Value range |
| --- | ---: | --- |
| `byte` | 8 bits | −128 to 127 |
| `short` | 16 bits | −32,768 to 32,767 |
| `int` | 32 bits | −2³¹ to 2³¹−1 |
| `long` | 64 bits | −2⁶³ to 2⁶³−1 |

`BigInteger` is an **arbitrary-precision integer** class in `java.math`. It is not fixed to 32 or 64 bits like `int`/`long`; very large values are handled using multiple internal bits, within the resource and implementation limits of the JVM.

```java
import java.math.BigInteger;

BigInteger x = new BigInteger("123456789012345678901234567890");
BigInteger y = BigInteger.valueOf(10L);
BigInteger sum = x.add(y);

System.out.println(sum);
// 123456789012345678901234567900
```

**There is no `+` operator for two `BigInteger` objects.** Use `add`, `subtract`, `multiply`, `divide`, and other methods. `BigInteger` is **immutable**: `add` returns a new value instead of modifying `x`.

A `BigInteger` can be constructed through several paths. Choosing an API must be based on **the source data's type and encoding**, not just the desired value:

| Available data | API to use | Key point to understand |
| --- | --- | --- |
| Decimal digit string | `new BigInteger(text)` | Allows leading `+`/`-` sign |
| Base 2–36 digit string | `new BigInteger(text, radix)` | Must specify radix; does not auto-detect `0x` |
| Primitive `long` | `BigInteger.valueOf(number)` | Preserves the signed value of `long` |
| `byte[]` encoded as signed two's complement | `new BigInteger(bytes)` | Big-endian; sign bit of first byte matters |
| `byte[]` containing **unsigned** magnitude | `new BigInteger(1, bytes)` | Positive signum; does not treat high bit as sign |
| Magnitude and sign passed separately | `new BigInteger(signum, magnitude)` | Signum −1, 0, +1; magnitude is big-endian unsigned |
| Only a slice within `byte[]` | Constructors with `off,len` (Java 9+) | No need to allocate a subarray to call constructor |

**Decision question for byte arrays:** "Is this a signed integer in two's complement, or an unsigned byte sequence representing a magnitude?" These two interpretations can produce **opposite-signed** results from the exact same bytes.

## 2. Creating from a Decimal String

The most common constructor:

```java
BigInteger decimal = new BigInteger("123456789012345678901234567890");
BigInteger negative = new BigInteger("-255");
BigInteger positive = new BigInteger("+255");

System.out.println(decimal);  // 123456789012345678901234567890
System.out.println(negative); // -255
System.out.println(positive); // 255
```

`new BigInteger(String)` reads a **decimal radix 10** string by default. The string consists of an optional leading `+` or `-` sign, followed by at least one valid digit. Do not pass an empty string or a sign alone.

The following strings are cases to distinguish:

| Input | Result |
| --- | --- |
| `"123"` | 123 |
| `"+123"` | 123 |
| `"-123"` | −123 |
| `"000123"` | 123, leading zeros stripped |
| `"-0"` | 0, no "negative zero" state like float |
| `""` | `NumberFormatException` |
| `"+"` | `NumberFormatException` |
| `"12.0"` | `NumberFormatException` |
| `" 123 "` | `NumberFormatException` due to extra characters |
| `"1_000"` | `NumberFormatException` under standard parser rules |

**BigInteger represents integers only.** It does not silently truncate the fractional part of a decimal string or accept a decimal point like `BigDecimal`. If the source is `"12.5"` and business logic genuinely permits fractional parts, use a type/conversion flow designed for scaled decimals rather than forcing data into `BigInteger` by stripping characters.

### Unicode Digits

The character-to-digit mapping rule uses `Character.digit(char, radix)`, which can accept certain Unicode digit characters. If a protocol only allows **ASCII `0..9`**, you must **validate separately** before or alongside parsing. Success of `new BigInteger(text)` does not by itself prove the token contains only ASCII.

## 3. Creating from a String by Radix (Base)

Use the constructor:

```java
BigInteger binary = new BigInteger("101101", 2); // 45
BigInteger octal = new BigInteger("77", 8);      // 63
BigInteger hex = new BigInteger("FF", 16);       // 255
BigInteger base36 = new BigInteger("ZZ", 36);    // 1295
```

`radix` must be between **2 and 36**. Decimal digits and valid letters are converted via `Character.digit`. Letter `A`/`a` is 10 in base 16, `F`/`f` is 15, and `Z`/`z` is 35 in base 36.

Signed examples:

```java
System.out.println(new BigInteger("-FF", 16));  // -255
System.out.println(new BigInteger("+100", 2));  // 4
System.out.println(new BigInteger("000101", 2)); // 5
```

**Common pitfall: prefixes are not automatically stripped.**

```java
// new BigInteger("0xFF", 16); // NumberFormatException
// new BigInteger("0b101", 2); // NumberFormatException
```

These are **runtime string data**, not Java literals in source code. For radix 16, pass the digit string `"FF"` (and sign if present), **do not pass `"0x"`**. If the protocol allows prefixes, strip and validate the prefix before passing the digit string to the constructor.

Example parsing a fixed-prefix format:

```java
static BigInteger parsePrefixedHex(String text) {
    if (text == null || !text.startsWith("0x")) {
        throw new IllegalArgumentException("Expected 0x prefix");
    }
    return new BigInteger(text.substring(2), 16);
}
```

This is an **illustrative method**, needing to be placed in a class. It intentionally accepts only lowercase `0x` at the start and **unsigned** digits after the prefix; if you need to accept `-0xFF` or `0XFF`, you must define that syntax and check separately. Do not use a `replace` call that deletes `0x` everywhere, as it can accept malformed strings.

### toString(radix) Is the Reverse Conversion

```java
BigInteger n = new BigInteger("255");
System.out.println(n.toString(2));  // 11111111
System.out.println(n.toString(16)); // ff
System.out.println(n.toString(10)); // 255
```

`toString(radix)` uses **lowercase** letters for bases greater than 10 and does not prepend `0x`/`0b`. With a valid radix, they can serve as both ends of a round-trip pair:

```java
BigInteger original = new BigInteger("-12345678901234567890");
String encoded = original.toString(16);
BigInteger restored = new BigInteger(encoded, 16);

System.out.println(original.equals(restored)); // true
```

Use `equals` to compare object **values**, do not use `==` to check whether two variables hold the same number.

## 4. Creating from `long`: Use `BigInteger.valueOf(long)`

If the input is already a `long` primitive, use the static factory:

```java
long id = 9_000_000_000L;
BigInteger bigId = BigInteger.valueOf(id);

System.out.println(bigId); // 9000000000
```

There is no corresponding public `BigInteger(long)` constructor:

```java
// BigInteger wrong = new BigInteger(123L); // Does not compile
BigInteger correct = BigInteger.valueOf(123L);
```

`valueOf` preserves the **signed value** of `long`, including negative and positive bounds:

```java
BigInteger low = BigInteger.valueOf(Long.MIN_VALUE);
BigInteger high = BigInteger.valueOf(Long.MAX_VALUE);

System.out.println(low); // -9223372036854775808
System.out.println(high); // 9223372036854775807
```

If the input is `int`, Java widens `int` to `long` automatically when calling `BigInteger.valueOf`:

```java
int count = 12;
BigInteger n = BigInteger.valueOf(count);
```

The method does not "guess" that the original value was outside `long` range: if a `long` operation overflowed **before** the call, `valueOf` only receives the post-overflow value.

```java
long a = Long.MAX_VALUE;
long wrong = a + 1; // overflows to Long.MIN_VALUE

BigInteger alreadyLost = BigInteger.valueOf(wrong);
BigInteger exact = BigInteger.valueOf(a).add(BigInteger.ONE);

System.out.println(alreadyLost); // -9223372036854775808
System.out.println(exact);       // 9223372036854775808
```

**Keep data exact from the start:** for integer literals outside the `long` range, create from a **decimal string** instead of forcing a literal into `long` first. For calculations that might overflow, convert operands to `BigInteger` **before performing addition/multiplication**.

### `valueOf` Is Not a String Parser

`BigInteger.valueOf("123")` **does not exist**. Use:

```java
BigInteger fromText = new BigInteger("123");
BigInteger fromPrimitive = BigInteger.valueOf(123L);
```

Unlike `Integer.valueOf(String)` or `Long.valueOf(String)`, `BigInteger` uses the `String` constructor for parsing.

## 5. Creating from `byte[]`: Java Assumes Signed Two's Complement by Default

The constructor:

```java
BigInteger n = new BigInteger(byteArray);
```

assumes the array represents a **signed two's complement integer** in **big-endian** order: the element at index 0 is the most significant byte.

Single-byte examples:

```text
Byte hex    8 bits            BigInteger(byte[])
---------------------------------------------------
0x00        00000000                0
0x01        00000001                1
0x7F        01111111              127
0x80        10000000             -128
0xFF        11111111               -1
```

In Java:

```java
byte[] bytes = {(byte) 0xFF};
BigInteger signed = new BigInteger(bytes);
System.out.println(signed); // -1
```

**Why does `0xFF` become −1 instead of 255?** The highest bit of the first byte is the sign bit in an 8-bit two's complement representation. An all-1s bit pattern represents −1.

Multiple bytes follow the same rule:

```java
BigInteger positive128 = new BigInteger(
        new byte[] {0x00, (byte) 0x80});
BigInteger negative256 = new BigInteger(
        new byte[] {(byte) 0xFF, 0x00});

System.out.println(positive128); // 128
System.out.println(negative256); // -256
```

With `[00,80]`, the leading `00` byte keeps the sign bit at 0; the value is 128. With `[FF,00]`, the 16-bit pattern `11111111 00000000` is −256 in two's complement.

**Do not strip a leading `00` byte in signed encoding if the next byte has its high bit set to 1.** Stripping `00` from `[00,FF]` turns 255 into −1.

## 6. Unsigned Byte Arrays: The `(signum, magnitude)` Constructor

Many protocols send an **unsigned magnitude** as a byte array: an octet `0xFF` means 255 rather than −1. In that case use:

```java
byte[] unsignedMagnitude = {(byte) 0xFF};
BigInteger n = new BigInteger(1, unsignedMagnitude);
System.out.println(n); // 255
```

The constructor `BigInteger(int signum, byte[] magnitude)` takes:

- `signum = 1`: non-negative/positive value with the byte array's magnitude;
- `signum = -1`: negative value with the byte array's magnitude;
- `signum = 0`: valid only when the entire magnitude represents **0**.

The `magnitude` array holds a big-endian **unsigned integer magnitude**. Java `byte` values may look negative when cast or printed directly, but the constructor reads the **8-bit pattern** of each byte as an octet of the magnitude.

Example:

```java
byte[] mag = {(byte) 0xFF};

System.out.println(new BigInteger(mag));    // -1: signed two's complement
System.out.println(new BigInteger(1, mag)); // 255: positive magnitude
System.out.println(new BigInteger(-1, mag));// -255: negative magnitude
```

These are **three different interpretations** of the exact same byte `FF`. Read the source format's contract before choosing a constructor.

### Invalid Signum Causes Errors

```java
// new BigInteger(0, new byte[] {1});
// NumberFormatException: signum is 0 but magnitude is nonzero

// new BigInteger(2, new byte[] {1});
// NumberFormatException: signum is not in -1,0,1
```

An empty or all-zero magnitude array represents the value **0** even when the passed signum is +1 or −1:

```java
BigInteger zero = new BigInteger(1, new byte[0]);
System.out.println(zero);        // 0
System.out.println(zero.signum());// 0
```

`BigInteger` has no separate negative zero or positive zero integer values.

### Do Not Confuse Signum with a Sign Byte

The first argument in `new BigInteger(1, bytes)` is **the sign itself** supplied by the caller; it is not taken from the high bit of the byte data. If your protocol already encodes the sign inside a two's complement byte array, **do not** arbitrarily pass `signum=1` because doing so turns negative numbers positive.

## 7. Big-Endian Structure: Most Significant Byte Comes First

Big-endian with unsigned bytes `{0x01,0x00}`:

\[
1\times256 + 0=256
\]

```java
byte[] bytes = {0x01, 0x00};
System.out.println(new BigInteger(1, bytes)); // 256
```

If your source is **little-endian**, the least significant byte comes first. Never pass a little-endian array directly to `BigInteger` constructors and expect the right numeric value.

Example of the number `0x0102 = 258`:

```java
byte[] bigEndian = {0x01, 0x02};
byte[] littleEndian = {0x02, 0x01};

System.out.println(new BigInteger(1, bigEndian));     // 258
System.out.println(new BigInteger(1, littleEndian)); // 513
```

If the protocol is little-endian, reorder the bytes **according to the specification** or use a byte reader with the chosen endianness before converting to `BigInteger`. Do not reverse bytes unconditionally: some fields are already big-endian, some fields are only one byte, and some fields use signed two's complement.

### `ByteBuffer` and `toByteArray`

`ByteBuffer` has its own byte-order configuration for multi-byte primitive reads. However, `BigInteger(byte[])` **does not accept `ByteBuffer` and does not inspect a buffer's `ByteOrder`**. Only after obtaining a `byte[]` in the desired order should you pass it to the appropriate constructor.

When reading from a buffer with position/limit, verify which bytes belong to the token and do not accidentally include headers/checksums in the number.

## 8. Java 9+: Constructors Reading a Slice of `byte[]`

Java 9 added two offset/length constructors, both present in Java 17:

```java
new BigInteger(byte[] val, int off, int len);
new BigInteger(int signum, byte[] magnitude, int off, int len);
```

- `off`: starting element index in the array (zero-based).
- `len`: **number of bytes to read**, **not the ending index**.
- Both versions treat the selected bytes as **big-endian**.
- The version without signum reads **signed two's complement**.
- The version with signum reads **unsigned magnitude** with an external sign.

Example of a buffer with header/trailer bytes:

```java
byte[] packet = {0x55, 0x00, (byte) 0x80, 0x66};

// Take 2 bytes at [1,3): 00 80, signed = 128
BigInteger value = new BigInteger(packet, 1, 2);

// Take exact 1 byte at [2,3): 80, unsigned magnitude = 128
BigInteger positive = new BigInteger(1, packet, 2, 1);

System.out.println(value);    // 128
System.out.println(positive); // 128
```

If using the signed constructor with `off=2,len=1`, there is only byte `80` and the result is **−128**:

```java
System.out.println(new BigInteger(packet, 2, 1)); // -128
```

This is a mistake **very hard to catch if you only test data whose leading bit is 0**.

Out-of-bounds indices throw `IndexOutOfBoundsException`. For two's complement data, an empty slice does not describe a valid number and can throw `NumberFormatException`; for the signum/magnitude constructor, an empty magnitude is a valid zero.

A slice-reading constructor avoids forcing **the caller to allocate a subarray** just to parse. It **does not guarantee zero internal allocation**, and does not guarantee safety if the array is mutated concurrently while the constructor reads: callers must keep data stable during the call.

## 9. `toByteArray()`: Reverse Encoding in Two's Complement, Not Unsigned Magnitude

The method `value.toByteArray()` returns **minimal big-endian signed two's complement** bytes. `BigInteger.valueOf(255).toByteArray()` is `00 FF`, while `BigInteger.valueOf(-1).toByteArray()` is `FF`. The `00` byte protects the sign of positive numbers with the high bit set; this array is not an unsigned magnitude. A `new BigInteger(value.toByteArray())` round-trip restores the **numeric value** accurately, but does not promise to preserve the original input length.

## 10. Fixed-Width Unsigned Data: Clear Contract Required

For a two-byte unsigned field `FF FF`, `new BigInteger(bytes)` gives -1, while `new BigInteger(1,bytes)` gives 65535. When **writing** N unsigned bytes, you must verify the number is non-negative and fits in `0..2^(8N)-1`, strip the `00` sign-guard byte if present, and then left-pad with `00` up to N bytes. Never truncate significant data or forget the zero case; detailed signed/unsigned fixed-width codecs and round-trips are practiced in the dedicated `toByteArray` lesson.

## 11. Beware of ASCII/UTF-8 Data: String Bytes Are NOT Numeric Values

If you have numeric text `"123"`, you might think:

```java
byte[] textBytes = "123".getBytes(
        java.nio.charset.StandardCharsets.UTF_8);
BigInteger wrong = new BigInteger(textBytes);
```

However, the UTF-8 bytes for the three characters `'1','2','3'` are `0x31,0x32,0x33`. `new BigInteger(textBytes)` will interpret **these three bytes as a big-endian binary integer**, rather than performing decimal string parsing.

The right way:

```java
BigInteger fromDecimal = new BigInteger("123");
```

Conversely, if a byte array comes from a protocol transmitting **binary numeric values**, do not turn it into `new String(bytes, UTF_8)` and parse decimal: byte `0xFF` or many control bytes are not valid text digits.

**Selection rule:** determine whether the input is **text representing a number** or **a bit pattern representing a number**. These two cannot be swapped just because both end up inside a `byte[]` at the network layer.

## 12. Error Handling When Creating `BigInteger`

Errors to distinguish by source type:

| Source and situation | Error / handling |
| --- | --- |
| `new BigInteger("12X")` radix 10 | `NumberFormatException` |
| `new BigInteger("FF", 1)` radix outside 2..36 | `NumberFormatException` |
| `new BigInteger("")` | `NumberFormatException` |
| `new BigInteger("0xFF",16)` | `NumberFormatException` |
| `new BigInteger(new byte[0])` | `NumberFormatException` |
| `new BigInteger(0,new byte[]{1})` | `NumberFormatException` |
| `new BigInteger(2,new byte[]{1})` | `NumberFormatException` |
| `byte[]` constructor with out-of-range off/len | `IndexOutOfBoundsException` |
| `null` object argument | `NullPointerException` |
| Value too large exceeding implementation/resource capacity | May fail with limit/`ArithmeticException` or resource error; do not treat as infinite |

Example:

```java
try {
    BigInteger n = new BigInteger("0xFF", 16);
} catch (NumberFormatException ex) {
    System.out.println("Invalid numeric token");
}
```

Do not catch all `RuntimeException`s and return `BigInteger.ZERO`. The value 0 is completely valid, so it **must not** be used as a generic fallback code for malformed tokens when business logic needs to distinguish empty/invalid data from a real zero.

If input comes from users or the network, consider limiting the number of digits/bytes before parsing to protect CPU/memory, and verifying radix, sign, endianness, and field length.

## 13. `BigInteger` Does Not Make Every Reverse Conversion Safe

Creating a `BigInteger` from `long` preserves the exact value; however, reading back into `long` can lose data if the `BigInteger` exceeds the `long` range:

```java
BigInteger huge = BigInteger.valueOf(Long.MAX_VALUE)
        .add(BigInteger.ONE);

System.out.println(huge);             // 9223372036854775808
System.out.println(huge.longValue()); // -9223372036854775808
```

`longValue()` retains the low-order bits matching conversion rules and **does not throw an error automatically**. If you need to preserve the value or fail, use:

```java
try {
    long checked = huge.longValueExact();
} catch (ArithmeticException ex) {
    System.out.println("Value outside long range");
}
```

Similarly, there are `intValueExact()`, `shortValueExact()`, and `byteValueExact()`. When a `BigInteger` input was created from a very long `String` or an unsigned field exceeding signed bounds, **do not** automatically convert back to `int`/`long` just because legacy business code used primitives.

A `BigInteger` can hold an unsigned 64-bit value from an 8-byte array `FF FF FF FF FF FF FF FF`, equivalent to `18446744073709551615`, yet its `longValue()` is −1. This is **the same low bits interpreted as signed**, not a parser bug.

## 14. Immutability, `equals`, and Common Constants

`BigInteger` instances are immutable. Example:

```java
BigInteger a = new BigInteger("123");
BigInteger b = a.add(BigInteger.ONE);

System.out.println(a); // 123
System.out.println(b); // 124
```

Built-in constants: `BigInteger.ZERO`, `BigInteger.ONE`, `BigInteger.TWO` (available since Java 9), and `BigInteger.TEN`. They are suitable for expressing fixed values without repeatedly parsing strings:

```java
BigInteger zero = BigInteger.ZERO;
BigInteger power = BigInteger.TWO.pow(16);
System.out.println(power); // 65536
```

Use `equals` to check value equality:

```java
BigInteger x = new BigInteger("255");
BigInteger y = new BigInteger(1, new byte[]{(byte) 0xFF});

System.out.println(x.equals(y)); // true
```

The `==` operator compares **object references**, not numeric content. `BigInteger.valueOf` may reuse objects for certain values; **do not rely on identity/caching** to check whether two numbers are equal.

## 15. Complete Java 17+ Demo with Verified Stdout

Save the file as **`BigIntegerConstructionDemo.java`**:

```java
import java.math.BigInteger;

public class BigIntegerConstructionDemo {
    private static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder();
        for (byte value : bytes) {
            out.append(String.format("%02x", value & 0xff));
        }
        return out.toString();
    }

    public static void main(String[] args) {
        BigInteger decimal =
                new BigInteger("123456789012345678901234567890");
        BigInteger negative = new BigInteger("-255");
        BigInteger hexNumber = new BigInteger("FF", 16);
        BigInteger binary = new BigInteger("101101", 2);
        BigInteger base36 = new BigInteger("ZZ", 36);
        BigInteger fromLong = BigInteger.valueOf(Long.MIN_VALUE);

        System.out.println("decimal = " + decimal);
        System.out.println("negative = " + negative);
        System.out.println("hex = " + hexNumber);
        System.out.println("binary = " + binary);
        System.out.println("base36 = " + base36);
        System.out.println("long minimum = " + fromLong);
        System.out.println("255 to hex = "
                + hexNumber.toString(16));

        byte[] oneByte = {(byte) 0xff};
        BigInteger signed = new BigInteger(oneByte);
        BigInteger unsigned = new BigInteger(1, oneByte);
        BigInteger prefixed = new BigInteger(
                new byte[] {0x00, (byte) 0xff});
        BigInteger negativeBytes = new BigInteger(
                new byte[] {(byte) 0xff, 0x00});

        System.out.println("0xff signed = " + signed);
        System.out.println("0xff magnitude = " + unsigned);
        System.out.println("00ff signed = " + prefixed);
        System.out.println("ff00 signed = " + negativeBytes);
        System.out.println("255 encoded = "
                + hex(unsigned.toByteArray()));
        System.out.println("-1 encoded = "
                + hex(signed.toByteArray()));
        System.out.println("0 encoded = "
                + hex(BigInteger.ZERO.toByteArray()));

        byte[] packet = {0x55, 0x00, (byte) 0x80, 0x66};
        BigInteger rangeSigned =
                new BigInteger(packet, 1, 2);
        BigInteger rangeMagnitude =
                new BigInteger(1, packet, 2, 1);
        System.out.println("range signed = " + rangeSigned);
        System.out.println("range magnitude = " + rangeMagnitude);
        System.out.println("bytes round-trip = "
                + unsigned.equals(
                        new BigInteger(unsigned.toByteArray())));
        System.out.println("empty magnitude = "
                + new BigInteger(1, new byte[0]));

        try {
            new BigInteger("0xFF", 16);
        } catch (NumberFormatException ex) {
            System.out.println("prefix: rejected");
        }
        try {
            new BigInteger("1_000");
        } catch (NumberFormatException ex) {
            System.out.println("underscore: rejected");
        }
        try {
            new BigInteger("FF", 1);
        } catch (NumberFormatException ex) {
            System.out.println("radix: rejected");
        }
        try {
            new BigInteger(new byte[0]);
        } catch (NumberFormatException ex) {
            System.out.println("empty signed bytes: rejected");
        }
        try {
            new BigInteger(0, new byte[] {1});
        } catch (NumberFormatException ex) {
            System.out.println("signum mismatch: rejected");
        }
        try {
            new BigInteger(packet, 3, 2);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("range: rejected");
        }
        try {
            BigInteger.valueOf(Long.MAX_VALUE)
                    .add(BigInteger.ONE).longValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("long exact: rejected");
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 BigIntegerConstructionDemo.java
java BigIntegerConstructionDemo
```

**Stdout verified with a program compiled using `javac --release 17`:**

```text
decimal = 123456789012345678901234567890
negative = -255
hex = 255
binary = 45
base36 = 1295
long minimum = -9223372036854775808
255 to hex = ff
0xff signed = -1
0xff magnitude = 255
00ff signed = 255
ff00 signed = -256
255 encoded = 00ff
-1 encoded = ff
0 encoded = 00
range signed = 128
range magnitude = 128
bytes round-trip = true
empty magnitude = 0
prefix: rejected
underscore: rejected
radix: rejected
empty signed bytes: rejected
signum mismatch: rejected
range: rejected
long exact: rejected
```

### How to Read the Results

1. `new BigInteger("...")` retains long decimal integers, `new BigInteger("FF",16)` yields 255, and `valueOf(Long.MIN_VALUE)` preserves the negative `long` bound accurately.
2. The same byte `FF` is read as **−1** when using the signed constructor, but **255** when using signum +1.
3. `00 FF` is the positive signed encoding of 255; `FF 00` represents signed −256.
4. `toByteArray()` does not promise one byte for 255; it must prepend `00` to preserve the positive sign.
5. Constructors with `off,len` allow reading a byte region without `Arrays.copyOfRange` on the caller side.
6. Strings with prefixes/underscores, invalid radix, empty signed arrays, invalid signum, out-of-bounds ranges, and unsafe `long` conversions each have distinct failure modes.

## 16. Common Mistakes to Avoid

| Mistake | Correct understanding |
| --- | --- |
| "BigInteger has a constructor taking long" | Use `BigInteger.valueOf(long)` |
| "valueOf accepts a string like Integer.valueOf" | BigInteger parses strings with `new BigInteger(String)` |
| "BigInteger(String) automatically recognizes `0xFF`" | Default radix is 10; for hex pass `"FF",16` |
| "`new BigInteger("1_000")` works like Java literal `1_000`" | Runtime parser does not understand underscores like source syntax |
| "Creating from String cannot exceed long limits" | Decimal strings can be many times longer than the `long` range |
| "The byte value 0xFF is always 255" | `BigInteger(byte[])` interprets signed `FF` as −1 |
| "Passing a little-endian byte array directly works" | BigInteger constructors use big-endian |
| "`new BigInteger(1,bytes)` still infers sign from the high bit" | Signum=1 forces **positive magnitude** interpretation |
| "`toByteArray` returns fixed N-byte unsigned magnitude" | It returns signed two's complement of variable length |
| "A leading `00` byte is always redundant" | It may be required to preserve a positive sign when the next byte has high bit 1 |
| "Empty signed array and empty magnitude behave the same" | Empty signed is rejected; empty magnitude can yield zero |
| "Offset,length means start/end positions" | `len` is byte count, not `endIndex` |
| "BigInteger means infinite resources" | Still bound by memory, CPU, and JVM support |
| "`big.longValue()` is always safe" | Can truncate bits; use `longValueExact()` if integrity is required |
| "Comparing BigInteger with ==" | Use `equals` or `compareTo` by value |
| "Can create BigInteger from UTF-8 bytes of a numeric string" | Character-encoding bytes are not numeric representation bytes |
| "Converting to BigInteger after overflow fixes overflow" | Operands must be converted **before** potentially overflowing operations |

## 17. Exercises with Solutions

**Exercise 1.** Create a `BigInteger` from the decimal number `"987654321098765432109876543210"` without going through `long`.  
**Solution:** `new BigInteger("987654321098765432109876543210")`; no conversion step to a primitive.

**Exercise 2.** What is the value of `new BigInteger("101101",2)`?  
**Solution:** `32+8+4+1=45`. Binary strings do not take the `0b` prefix.

**Exercise 3.** What is the value of `new BigInteger("FF",16)`? Why is `"0xFF"` different?  
**Solution:** 255. The radix-16 constructor does not strip the `0x` prefix; `new BigInteger("0xFF",16)` throws `NumberFormatException`.

**Exercise 4.** How do you construct from `Long.MIN_VALUE`?  
**Solution:** `BigInteger.valueOf(Long.MIN_VALUE)`. No need to build a string; there is no `BigInteger(long)` constructor.

**Exercise 5.** What do `new BigInteger(new byte[]{(byte)0x80})` and `new BigInteger(1,new byte[]{(byte)0x80})` equal?  
**Solution:** −128 and +128. The bit pattern `80` is negative in signed two's complement, while its unsigned magnitude is 128.

**Exercise 6.** Why is `new BigInteger(new byte[]{0x00,(byte)0xFF})` equal to 255?  
**Solution:** The leading `00` byte has sign bit 0, so the 16-bit pattern `00FF` is +255. Dropping `00` leaves `FF`, which is read as −1 under the signed constructor.

**Exercise 7.** What value does big-endian unsigned byte array `{0x01,0x00}` represent?  
**Solution:** `0x0100 = 256`. Use `new BigInteger(1,bytes)` if the data contract is unsigned magnitude.

**Exercise 8.** Does `new BigInteger(0,new byte[]{1})` evaluate to 0?  
**Solution:** No; it throws `NumberFormatException` because `signum=0` conflicts with a nonzero magnitude.

**Exercise 9.** Given `byte[] packet={0x55,0x00,(byte)0x80,0x66}`, which bytes does `new BigInteger(packet,1,2)` read?  
**Solution:** Bytes at indices 1 and 2 (`00 80`), giving 128; `len=2` is the length, not the ending index.

**Exercise 10.** Is `BigInteger.valueOf(255).toByteArray()` guaranteed to contain only one byte `FF`?  
**Solution:** No; it returns `00 FF` in signed form, because a lone `FF` represents −1.

**Exercise 11.** A two-byte network field contains `FF FF` and is defined as unsigned. Which constructor and value apply?  
**Solution:** `new BigInteger(1,new byte[]{(byte)0xFF,(byte)0xFF})`, yielding 65535. The signed constructor would yield −1.

**Exercise 12.** Do `new BigInteger("-0")` and `new BigInteger(1,new byte[0])` have different values?  
**Solution:** No. Both are integer zero; `BigInteger` has no ±0 like floating-point.

**Exercise 13.** How do you convert a very large `BigInteger` to `long` **without data loss**?  
**Solution:** Use `longValueExact()`. If unrepresentable in `long`, the method throws `ArithmeticException` instead of silently dropping bits.

**Exercise 14.** Why is `new BigInteger("123".getBytes(UTF_8))` not equivalent to `new BigInteger("123")`?  
**Solution:** The first reads the byte pattern `31 32 33` as a binary number; the second parses three decimal digits into 123.

**Exercise 15.** A program computes `BigInteger.valueOf(a+b)` with large `long`s `a` and `b`. When can this go wrong?  
**Solution:** If `a+b` overflows **before being converted to `BigInteger`**; fix it to `BigInteger.valueOf(a).add(BigInteger.valueOf(b))`.

## 18. Checklist for Choosing How to Create `BigInteger`

1. **Identify the source format:** decimal text, other-radix text, primitive `long`, signed byte array, or unsigned byte array?
2. **For `String`:** decide on radix 2–36, sign policy, whitespace, prefix, ASCII/Unicode digits, and length limit.
3. **For `long`:** use `valueOf(long)`, but ensure prior arithmetic has not overflowed.
4. **For signed `byte[]`:** use `new BigInteger(bytes)` and understand big-endian two's complement.
5. **For unsigned `byte[]`:** use `new BigInteger(1,bytes)` or signum per contract, without inferring sign from the first byte.
6. **For a byte subarray:** `(off,len)` constructors from Java 9+, noting `len` is count and the input must stay stable while read.
7. **When serializing back to `byte[]`:** `toByteArray()` is signed and variable-length; custom rules are needed if the protocol is unsigned/fixed-width.
8. **Do not mix ASCII bytes and binary bytes:** the byte encoding character `'1'` is not the integer 1.
9. **Check specific error cases:** invalid parse/radix/empty signed bytes, bad signum, bad indices, null, exceeding resource limits.
10. **When converting back to primitives:** use `*ValueExact` methods if business logic cannot lose information.
11. **Compare using `equals`**, do not use `==` for two `BigInteger`s.
12. **Use boundary test cases:** 0, −1, 127, 128, 255, 256, `long` min/max, empty array, leading byte `80`/`FF`, little-/big-endian, and values exceeding field width.

### References

- [BigInteger — Javadoc Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html)
- [Character.digit — Javadoc Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html#digit(char,int))
- [ByteBuffer and ByteOrder — Javadoc Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)

**Key takeaway:** `BigInteger` can be initialized from large decimal numbers, text in bases 2–36, `long`, or `byte[]`. For byte arrays, you must distinguish **signed two's complement** from **unsigned sign-magnitude**, preserve **big-endian** order, and determine the sign byte. This is what decides whether the program reads the right value, not merely constructor syntax differences.