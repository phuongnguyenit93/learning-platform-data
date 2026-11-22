# `toBinaryString`, `toHexString`, and `toUnsignedString` in Java

When you need to display or inspect the **representation of an integer**, Java provides static methods in `Integer` and `Long`. The three most important names are **`toBinaryString`**, **`toHexString`**, and **`toUnsignedString`**:

- `Integer.toBinaryString(int)`: produces a **binary** string (base 2) from the **32-bit pattern** of an `int`.
- `Integer.toHexString(int)`: produces a **hexadecimal** string (base 16), using lowercase `a`–`f`, from the same bit pattern.
- `Integer.toUnsignedString(int)`: produces an **unsigned decimal** string (base 10 by default), treating the same 32 bits as a number in the range `0` to `4_294_967_295`.

Example with the same `int` value:

```java
int value = -1;

System.out.println(Integer.toBinaryString(value));
// 11111111111111111111111111111111

System.out.println(Integer.toHexString(value));
// ffffffff

System.out.println(Integer.toUnsignedString(value));
// 4294967295
```

`value` is still **`int -1`**, and does not automatically turn into an unsigned integer type. These methods **change how bits are presented as a string**; they do not modify the variable's value, do not alter bits in memory, and do not create a primitive `uint` type.

## 1. Properly understanding signed and unsigned before formatting

Java has the primitive integer types `byte` (8 bits), `short` (16 bits), `int` (32 bits), and `long` (64 bits), all signed in standard integer arithmetic. Specifically, `char` is a 16-bit unsigned integer value serving UTF-16 code units.

For `int`, the same **32 bits** can be interpreted as:

- **Signed** in two's complement: `-2_147_483_648` to `2_147_483_647`.
- **Unsigned**: `0` to `4_294_967_295`.

Example of an all-`1` bit pattern:

```text
32 bits:          11111111111111111111111111111111
Hex:              ffffffff
Signed int:       -1
Unsigned 32-bit:  4294967295
```

These are **not three separately stored values**. They are **three ways of presenting the same bit pattern**. The expression `int x = -1;` continues to operate under signed arithmetic if you write `x + 1`, `x < 0`, or `x / 2`. If business logic requires **unsigned comparison/division**, Java provides APIs such as `Integer.compareUnsigned`, `divideUnsigned`, and `remainderUnsigned`; merely calling `toUnsignedString` does not change the semantics of subsequent operations.

### Quick table for `Integer`

| `int` value | `toBinaryString` | `toHexString` | `toUnsignedString` |
| --- | --- | --- | --- |
| `0` | `0` | `0` | `0` |
| `10` | `1010` | `a` | `10` |
| `42` | `101010` | `2a` | `42` |
| `255` | `11111111` | `ff` | `255` |
| `-1` | 32 `1` characters | `ffffffff` | `4294967295` |
| `Integer.MIN_VALUE` | `1` and 31 `0` characters | `80000000` | `2147483648` |

For non-negative `int` numbers, binary and hex strings usually **omit leading zeros**. For negative numbers, the sign bit is 1 and the 32-bit two's complement representation is shown across the full width of the `int` type. That is why `Integer.toBinaryString(-1)` is 32 characters long, whereas `Integer.toBinaryString(1)` is just `"1"`.

## 2. `Integer.toBinaryString(int)`: reading the bit pattern in base 2

Syntax:

```java
String bits = Integer.toBinaryString(42); // "101010"
```

The digits in the string consist only of `0` and `1`; **there is no `0b` prefix** and no separate minus sign. The method treats the bit pattern of `int` as an unsigned 32-bit value and writes it in base 2.

```java
System.out.println(Integer.toBinaryString(10)); // 1010
System.out.println(Integer.toBinaryString(-1));
// 11111111111111111111111111111111
```

Because `int` has 32 bits, a negative value like `-1` corresponds to a two's complement pattern of all `1` bits. **Do not read** the string `111...111` as a signed negative number by looking at the first digit and adding a `-` sign; it is an unsigned binary string representing the original 32 bits.

Special case:

```java
String minBits = Integer.toBinaryString(Integer.MIN_VALUE);
// "10000000000000000000000000000000"
```

The highest bit is 1 and all other bits are 0. With signed semantics, this pattern is `-2^31`; with unsigned semantics, it is `2^31`.

### Want a string that is always 32 bits long?

`toBinaryString` does not add leading zeros for positive numbers. If you need a fixed 32-bit version:

```java
int x = 42;
String bits = Integer.toBinaryString(x);
String padded = "0".repeat(32 - bits.length()) + bits;
// "00000000000000000000000000101010"
```

This style works in Java 17+ and for any `int` whose binary string is at most 32 characters. When a binary protocol needs **raw bytes** rather than `'0'`/`'1'` characters, write actual bytes via `ByteBuffer` or the appropriate I/O API; a binary string is a **display format for reading/debugging**, not an efficient binary data format.

## 3. `Integer.toHexString(int)`: readable hex display

Hex (base 16) groups **every 4 bits into one digit** from `0` to `9` and `a` to `f`:

```java
int x = 42;

System.out.println(Integer.toHexString(x));   // 2a
System.out.println(Integer.toHexString(255)); // ff
System.out.println(Integer.toHexString(-1));  // ffffffff
```

An `int` has at most 8 hex characters, because `32 / 4 = 8`. Hex is more compact than binary, so it is often convenient when inspecting bit masks, color codes, and data addresses/words.

**Syntax note:** The returned string **does not contain `0x`**, contains no separators, and uses lowercase `a`–`f`. `"2a"` is the string returned by the function; if you want a `0x` label in the UI, concatenate it explicitly:

```java
String shown = "0x" + Integer.toHexString(42); // "0x2a"
```

Do not confuse **the string returned by the API** with a Java literal:

```java
int sourceLiteral = 0x2A;       // int literal 42 in Java code
String displayed = Integer.toHexString(sourceLiteral); // "2a"
```

For negative 32-bit patterns, such as `-1`, `Integer.toHexString(-1)` returns `"ffffffff"` because it represents the bits as unsigned, **not `"-1"`**. If you need to write a signed number in base 16, see `Integer.toString(value, 16)` in section 5.

### Displaying all 8 hex digits

`Integer.toHexString(42)` returns `"2a"`, without padding it to `"0000002a"`. If a report format requires exactly 8 digits, you can write:

```java
int x = 42;
String padded = String.format("%08x", x); // "0000002a"
```

`String.format` supports width and zero-padding. For data used in protocols or hashes, **width and letter case must be specified consistently**. In UIs, `%08X` can be used to print uppercase hex if required.

## 4. `Integer.toUnsignedString(int)`: reading 32 bits as an unsigned number

`Integer.toUnsignedString(value)` by default represents an `int` as an **unsigned 32-bit value in base 10**:

```java
int x = -1;
String signed = Integer.toString(x);         // "-1"
String unsigned = Integer.toUnsignedString(x); // "4294967295"
```

The same 32 bits have different interpretations depending on the goal. Mathematical rule for `int x`:

- If `x >= 0`, the unsigned value equals `x`.
- If `x < 0`, the corresponding unsigned value is mathematically `x + 2^32` (which must be computed using a sufficiently wide type).

You can observe the equivalence via widening and masking:

```java
int x = -1;
long u = Integer.toUnsignedLong(x); // 4294967295L
long alsoU = ((long) x) & 0xFFFF_FFFFL; // 4294967295L
```

`Integer.toUnsignedLong` widens with unsigned semantics. **Do not use `(long) x` alone** if you want unsigned decoding, because a signed `int → long` cast will keep `-1L` for `x = -1`.

There is no primitive `uint` in Java. Hence `toUnsignedString` only returns a `String` for display/exchange, while the underlying data remains an `int`. When performing unsigned arithmetic operations, you must use the proper APIs, not just change how you print.

## 5. Differences from `toString(value, radix)` and the radix overload

This is a very common point of confusion. Compare:

```java
int x = -1;

String signedHex = Integer.toString(x, 16);           // "-1"
String unsignedHex = Integer.toUnsignedString(x, 16); // "ffffffff"
String hexBits = Integer.toHexString(x);              // "ffffffff"
```

- `Integer.toString(int, radix)` treats the value as a **signed number**, so when negative it adds `-` and formats the magnitude.
- `Integer.toUnsignedString(int, radix)` treats **the same 32 bits as unsigned**, then converts to the chosen base.
- `Integer.toBinaryString(int)` is equivalent to presenting the `int` pattern as unsigned base 2.
- `Integer.toHexString(int)` is equivalent to presenting the `int` pattern as unsigned base 16.
- `Integer.toOctalString(int)` behaves similarly for base 8, though it is not the central API of this lesson.

```java
System.out.println(Integer.toUnsignedString(10, 8));  // "12"
System.out.println(Integer.toUnsignedString(31, 36)); // "v"
```

The `Integer.toUnsignedString(int, int)` overload accepts a radix. You should proactively use valid radices from `Character.MIN_RADIX` (**2**) to `Character.MAX_RADIX` (**36**). Java uses lowercase Latin letters for digits from 10 to 35. If you want hex, use radix 16; if you want binary, use radix 2. In code that handles source strings yourself, validate the radix instead of assuming the API will warn on every invalid radix the way you expect.

API comparison table:

| Call with `x = -1` | Result | Interpretation |
| --- | --- | --- |
| `Integer.toString(x)` | `"-1"` | Signed, decimal |
| `Integer.toString(x, 16)` | `"-1"` | Signed, hex with minus sign |
| `Integer.toUnsignedString(x)` | `"4294967295"` | Unsigned, decimal |
| `Integer.toUnsignedString(x, 2)` | 32 `'1'` digits | Unsigned, binary |
| `Integer.toBinaryString(x)` | 32 `'1'` digits | Bit pattern, binary |
| `Integer.toUnsignedString(x, 16)` | `"ffffffff"` | Unsigned, hex |
| `Integer.toHexString(x)` | `"ffffffff"` | Bit pattern, hex |

**Key takeaway:** When a value is in the negative range of `int`, the displayed digits depend on choosing **signed** or **unsigned** semantics.

## 6. `Long` versions and 64-bit width

`Long` also provides:

- `Long.toBinaryString(long)`;
- `Long.toHexString(long)`;
- `Long.toUnsignedString(long)`;
- `Long.toUnsignedString(long, int radix)`.

The same principles as `Integer` apply, but working with **64 bits**. The largest 64-bit unsigned number is **`2^64 - 1 = 18_446_744_073_709_551_615`**, exceeding `Long.MAX_VALUE`.

```java
long value = -1L;

System.out.println(Long.toHexString(value));
// ffffffffffffffff (16 f characters)

System.out.println(Long.toUnsignedString(value));
// 18446744073709551615
```

`Long.toBinaryString(-1L)` returns 64 `'1'` digits. For `Long.MIN_VALUE`, the hex pattern is `8000000000000000`; the signed interpretation is `-2^63`, while the unsigned interpretation is `2^63`.

**Do not force a large 64-bit unsigned integer into another `long` to get a positive value**, because primitive `long` does not have a large enough positive range. If you need to work with mathematical values in the 64-bit unsigned range as non-negative numbers, you can use `BigInteger` or the dedicated unsigned operations `Long.compareUnsigned`, `divideUnsigned`, `remainderUnsigned`; choose what fits the problem.

## 7. `byte`/`short` pitfall: sign extension before formatting

The three methods `Integer.toBinaryString`, `Integer.toHexString`, and `Integer.toUnsignedString` accept `int`; **there are no direct overloads for `byte` or `short`**. When passing a `byte`/`short`, Java widens it to `int` before calling the method.

For negative values, primitive widening preserves the **signed value**, which can be observed as **sign extension** (propagating the sign bit into the upper bits):

```java
byte b = -1;

String unexpected = Integer.toBinaryString(b);
// 11111111111111111111111111111111 (32 bits, not 8)

String eightBits = Integer.toBinaryString(b & 0xFF);
// 11111111

int unsignedByte = Byte.toUnsignedInt(b); // 255
```

If you want to represent the exact **8 bits** of a `byte`, mask with `0xFF` before formatting. For `short`, use `0xFFFF` to keep 16 bits:

```java
short s = -1;

String sHex = Integer.toHexString(s & 0xFFFF); // "ffff"
String sBits = Integer.toBinaryString(s & 0xFFFF);
// "1111111111111111"
```

If you want an unsigned value that is easy to compute with, `Byte.toUnsignedInt` and `Short.toUnsignedInt` express the intent clearly. You can also use `Byte.toUnsignedInt(b)` followed by `Integer.toUnsignedString(...)`. Masking is a common approach when working with bit fields, network protocols, or decoding signed bytes into values in `0..255`.

### Mind the output width

`Integer.toBinaryString(b & 0xFF)` still strips **leading zeros** for values like `5` (which becomes `"101"`). If exactly 8 bits are required, combine masking with padding:

```java
byte b = 5;
String raw = Integer.toBinaryString(b & 0xFF); // "101"
String padded = "0".repeat(8 - raw.length()) + raw; // "00000101"
```

Similarly, to get exactly 4 hex characters for a `short`, you can use `String.format("%04x", s & 0xFFFF)`. **Masking** handles the bit width, whereas **padding** handles the display string length; these two steps have different responsibilities.

## 8. Converting an unsigned string back to a bit pattern: `parseUnsignedInt`, `parseUnsignedLong`

If an unsigned string exceeds `Integer.MAX_VALUE` yet still belongs to the unsigned 32-bit range, `Integer.parseInt` will reject it. Use `Integer.parseUnsignedInt` to read the **32-bit pattern**:

```java
int bits = Integer.parseUnsignedInt("4294967295");

System.out.println(bits);                      // -1, signed interpretation
System.out.println(Integer.toUnsignedString(bits)); // 4294967295
System.out.println(Integer.toHexString(bits)); // ffffffff
```

The parser method returns an **`int`**, not a `uint` type. What matters in a round-trip is preserving the **bit pattern**, even though the temporary `int` variable may print as a negative number when interpreted as signed.

With base 16:

```java
int b = Integer.parseUnsignedInt("ffffffff", 16); // bit pattern -1
String output = Integer.toHexString(b); // "ffffffff"
```

The `parseUnsignedInt` APIs still check for **valid digits and the unsigned 32-bit range**. For example, the decimal string `"4294967296"` exceeds the unsigned range and will throw `NumberFormatException`. They do not automatically accept prefixes such as `0x` in the base-16 overload, so prefixes must be specified/stripped according to the input contract.

For `long`, `Long.parseUnsignedLong("18446744073709551615")` returns the bit pattern corresponding to `-1L`, and `Long.toUnsignedString` displays the maximum unsigned string again. If you need to store a 64-bit unsigned value as a non-negative number for general arithmetic, consider `BigInteger`.

### Do not confuse parsing a signed number with parsing a bit pattern

`Integer.parseInt("ffffffff", 16)` throws `NumberFormatException` because the positive value is larger than signed `int` (for a string without a minus sign). `Integer.parseUnsignedInt("ffffffff", 16)` accepts it because it fits in the unsigned 32-bit range, yielding the signed `int` pattern `-1`. This is a difference in **parsing range**, not Java silently overflowing without reporting an error.

## 9. Complete Java 17+ example

Create the file `IntegerFormatsDemo.java`:

```java
public class IntegerFormatsDemo {
    public static void main(String[] args) {
        int number = 42;
        System.out.println("42 binary: " + Integer.toBinaryString(number));
        System.out.println("42 hex: " + Integer.toHexString(number));
        System.out.println("42 unsigned: " + Integer.toUnsignedString(number));

        System.out.println("-1 signed decimal: " + Integer.toString(-1));
        System.out.println("-1 unsigned decimal: " + Integer.toUnsignedString(-1));
        System.out.println("-1 binary: " + Integer.toBinaryString(-1));
        System.out.println("-1 hex: " + Integer.toHexString(-1));
        System.out.println("-1 signed hex: " + Integer.toString(-1, 16));
        System.out.println("-1 unsigned hex: " + Integer.toUnsignedString(-1, 16));

        int min = Integer.MIN_VALUE;
        System.out.println("MIN_VALUE unsigned: " + Integer.toUnsignedString(min));
        System.out.println("MIN_VALUE hex: " + Integer.toHexString(min));
        System.out.println("10 base 8: " + Integer.toUnsignedString(10, 8));
        System.out.println("31 base 36: " + Integer.toUnsignedString(31, 36));

        byte b = -1;
        System.out.println("byte -1 sign extended: " + Integer.toBinaryString(b));
        System.out.println("byte -1 masked: " + Integer.toBinaryString(b & 0xFF));
        System.out.println("byte -1 unsigned: " + Byte.toUnsignedInt(b));

        long big = -1L;
        System.out.println("long -1 unsigned: " + Long.toUnsignedString(big));
        System.out.println("long -1 hex: " + Long.toHexString(big));

        int parsed = Integer.parseUnsignedInt("4294967295");
        System.out.println("unsigned parsed bits: " + parsed);
        System.out.println("unsigned round trip: " + Integer.toUnsignedString(parsed));
        System.out.println("binary parse: " + Integer.parseUnsignedInt("11111111", 2));

        System.out.println("padded hex: " + String.format("%08x", number));
        System.out.println("padded binary: "
            + String.format("%8s", Integer.toBinaryString(number))
                .replace(' ', '0'));
    }
}
```

Compile and run:

```bash
javac IntegerFormatsDemo.java
java IntegerFormatsDemo
```

Verified stdout:

```text
42 binary: 101010
42 hex: 2a
42 unsigned: 42
-1 signed decimal: -1
-1 unsigned decimal: 4294967295
-1 binary: 11111111111111111111111111111111
-1 hex: ffffffff
-1 signed hex: -1
-1 unsigned hex: ffffffff
MIN_VALUE unsigned: 2147483648
MIN_VALUE hex: 80000000
10 base 8: 12
31 base 36: v
byte -1 sign extended: 11111111111111111111111111111111
byte -1 masked: 11111111
byte -1 unsigned: 255
long -1 unsigned: 18446744073709551615
long -1 hex: ffffffffffffffff
unsigned parsed bits: -1
unsigned round trip: 4294967295
binary parse: 255
padded hex: 0000002a
padded binary: 00101010
```

**How to read the program:** The `42` lines illustrate bases; the `-1` group shows that the same 32-bit pattern has different signed/unsigned interpretations; `MIN_VALUE` has the highest bit set to 1; the `byte` group explains sign extension and an 8-bit mask; the `long` group displays 64 bits; `parseUnsignedInt` round-trips back to the unsigned string; the last two lines show that **fixed-width** formatting is not the default behavior of `toBinaryString`/`toHexString`.

## 10. Practical applications and how to choose an API

### Inspecting bit flags and masks

When inspecting an `int` consisting of multiple bit flags, binary/hex helps visualize which bit positions are turned on:

```java
int flags = 0b1010_0101;
String hex = Integer.toHexString(flags);    // "a5"
String bits = Integer.toBinaryString(flags); // "10100101"
```

To analyze specific bits, combine the operators `&`, `|`, `^`, `~`, `<<`, and `>>>` on the integer value. `toBinaryString` only generates a **display string**; it does not replace bitwise operators.

### UIs or logs needing unsigned semantics

Some systems store 32-bit numbers in an `int` while practically treating them as **unsigned IDs/counters**. Use `Integer.toUnsignedString` when displaying so users do not see unwanted negative numbers. However, if ordering comparisons of IDs/counters are also unsigned, use `Integer.compareUnsigned` instead of `<` between two `int`s.

### Binary storage and protocols

`"ffffffff"` is **8 hex characters**, not four `0xFF` bytes. If a protocol truly needs to send bytes, you must convert the bit pattern into a byte array (for example, `ByteBuffer.putInt` with a specified byte order). `toHexString` is useful for debugging, but on its own it **does not determine endianness** (big-endian or little-endian).

For instance, `0x12345678` has the same hex string `"12345678"` whether serialized as big-endian bytes `12 34 56 78` or little-endian bytes `78 56 34 12`. Byte order is decided at the step of reading/writing bytes, not by the method that formats a number into a string.

### Choosing by requirement

| What is needed? | API to consider |
| --- | --- |
| View `int` bits in binary | `Integer.toBinaryString(value)` |
| View `int` bits in hex | `Integer.toHexString(value)` |
| Display signed decimal `int` | `Integer.toString(value)` |
| Display unsigned decimal `int` | `Integer.toUnsignedString(value)` |
| Display unsigned `int` in any radix 2–36 | `Integer.toUnsignedString(value, radix)` |
| Work with `long` values | The corresponding `Long` APIs |
| View exact low 8 bits of a `byte` | Mask `value & 0xFF`, then format/pad |
| Parse back unsigned 32/64 bits | `Integer.parseUnsignedInt` / `Long.parseUnsignedLong` |
| Print hex always with full digits | `String.format("%08x", intValue)` or manual formatting |
| Handle unsigned values in arithmetic | `compareUnsigned`, `divideUnsigned`, `remainderUnsigned`, or a wider type |

Not every negative number should be printed as unsigned: for debt balances, negative temperatures, offsets, or signed coordinates, `Integer.toString` is usually what matches the business semantics. Use `toUnsignedString` when **the data genuinely carries unsigned meaning or when inspecting bits**.

## 11. Common mistakes

1. **"`toBinaryString` returns a binary integer."** False: it returns a `String`, not a new numeric primitive value.
2. **"`toHexString` always includes the `0x` prefix."** False: the result consists only of hex digits.
3. **"`toBinaryString(42)` is always 32 characters long."** False: for positive numbers, leading zeros are omitted; pad if the protocol requires it.
4. **"`Integer.toBinaryString(-1)` returns `"-1"`."** False: it returns the 32 `1` bits of the signed integer -1.
5. **"`toUnsignedString(-1)` turns `int` into a `uint` type."** False: the variable remains `int -1`; only the display changes to `4294967295`.
6. **"`Integer.toString(-1, 16)` is the same as `Integer.toHexString(-1)`."** False: the former returns `"-1"`, while the latter returns `"ffffffff"`.
7. **"Passing `byte -1` to `Integer.toBinaryString` returns 8 bits."** False: `byte` is sign-extended to `int`, yielding 32 bits; mask with `0xFF` to get 8 bits.
8. **"`String.format("%08x", x)` and `toHexString(x)` have the same padding rules."** False: `%08x` requires a minimum width of 8 and pads with zeros, whereas `toHexString` does not pad positive numbers.
9. **"64-bit unsigned always fits in `long` as a positive number."** False: `2^64 - 1` exceeds `Long.MAX_VALUE`; you can only keep the bit pattern and interpret it appropriately.
10. **"`parseUnsignedInt` always returns a non-negative number when calling `System.out.println(int)`."** False: a signed `int` value can be negative; use `toUnsignedString` when printing.
11. **"A hex string containing characters `ff` is two bytes of binary data."** False: those are two characters; an actual conversion to bytes is needed if the protocol requires it.
12. **"After calling `toUnsignedString`, the `<` operator on `int` compares as unsigned."** False: it only produces a display string; `int` comparisons remain signed.
13. **"`Integer.parseInt("ffffffff", 16)` becomes -1 because the string is a bit pattern."** False: a signed parser reading a string without a minus sign sees a number beyond the `int` range and throws an error; use `parseUnsignedInt` to decode bit patterns.
14. **"Using hex always accurately describes network byte order."** False: hex represents a value, whereas endianness belongs to the step of converting to bytes.

## 12. Self-check questions

**1. What does `Integer.toBinaryString(10)` return?** → `"1010"`.

**2. What does `Integer.toHexString(255)` return?** → `"ff"` (without `0x`).

**3. What value does `Integer.toUnsignedString(-1)` give?** → `"4294967295"`; the original variable remains `int -1`.

**4. Why does `Integer.toBinaryString(-1)` have 32 `'1'` characters?** → `-1` is represented in two's complement with all 1 bits across 32 bits.

**5. How does `Integer.toString(-1, 16)` differ from `Integer.toHexString(-1)`?** → One is the signed numeric string `"-1"`, while the other is the hex bit pattern `"ffffffff"`.

**6. How do you get the binary string of `byte -1` in exact 8 bits?** → Use `Integer.toBinaryString(b & 0xFF)`, which for `b=-1` gives `"11111111"`; if `b` is small and positive, pad with extra zeros.

**7. How do you print `int -1` as unsigned 32-bit and then parse it back preserving the bits?** → `String s = Integer.toUnsignedString(-1); int raw = Integer.parseUnsignedInt(s);`; `raw` is the `int -1` bit pattern.

**8. What does `Long.toUnsignedString(-1L)` return?** → `"18446744073709551615"`.

**9. Does `toHexString` determine byte order when writing to a file?** → No; byte order is determined during the step of serializing into bytes.

**10. When should `toUnsignedString` not be used?** → When the data genuinely has signed semantics, such as negative debt or negative temperature; display it according to the proper semantics.

**Takeaway:** `toBinaryString` and `toHexString` turn the **bit pattern** of an `int`/`long` into a base-2/base-16 string, typically under an **unsigned** view. `toUnsignedString` by default represents the same bit pattern in **unsigned decimal**, or a specified radix. These functions **do not modify bits, do not create new unsigned types, and do not alter the semantics of other operations**. For negative `byte`/`short`, handle sign extension by masking before formatting; for fixed-width requirements, add padding.