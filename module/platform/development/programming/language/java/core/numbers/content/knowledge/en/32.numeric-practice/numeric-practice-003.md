# Reading and Writing Numbers in Multiple Bases and Unsigned Forms in Java

## 1. Goal: Same Value, Multiple Representations

A number can be **read from a string** or **formatted to a string** in multiple bases (radices): binary (base 2), octal (base 8), decimal (base 10), hexadecimal (base 16), or bases from 2 to 36. Meanwhile, Java has **signed** `int` and `long`, but no separate `unsigned int`/`unsigned long` primitive integer types.

Therefore, when working with bit masks, addresses, protocols, checksums, IDs from other systems, or binary fields in files, you must distinguish three things:

1. **Mathematical value**: for example, the positive number 4,294,967,295.
2. **Bit pattern stored in memory**: for example, 32 bits all set to `1`.
3. **Interpretation and presentation**: that same 32-bit pattern is `-1` as a signed `int`, but `4294967295` under unsigned interpretation.

In this lesson, "reading" primarily means **parsing text or extracting bits from data**; "writing" means **formatting to text or converting back to the appropriate bit representation**. The right approach depends on the protocol: it dictates the radix, bit width, signedness, leading zeros, byte order, and how invalid data is handled.

## 2. Radix and Digit Values

In base `r`, each digit at position `k` contributes `digit × r^k`. For example:

\[
(1010)_2=1\cdot2^3+0\cdot2^2+1\cdot2^1+0=10.
\]

And:

\[
(\text{FF})_{16}=15\cdot16+15=255.
\]

Basic table:

| Decimal value | Binary (2) | Octal (8) | Hex (16) |
| ---: | ---: | ---: | --- |
| 10 | `1010` | `12` | `A` |
| 15 | `1111` | `17` | `F` |
| 16 | `10000` | `20` | `10` |
| 255 | `11111111` | `377` | `FF` |
| 256 | `100000000` | `400` | `100` |

Java allows radix **2..36** in `Integer.parseInt`, `Long.parseLong`, and many conversion APIs. Digits `0`–`9` have values 0–9; letters `a`–`z` (or `A`–`Z`) have values 10–35 during parsing. For example, `z` in base 36 represents 35.

The radix is a **rule for reading strings**, not something that changes the integer value after parsing. After:

~~~java
int x = Integer.parseInt("FF", 16);
// x == 255
~~~

`x` does not "carry base 16" inside the `int` type; it simply stores the number 255. When you need to display hex, you must format it into a hex string.

## 3. Reading Signed Numbers: parseInt, parseLong, and BigInteger

### 3.1. Parsing from text with a specified radix

~~~java
int binary = Integer.parseInt("1010", 2); // 10
int octal = Integer.parseInt("377", 8);  // 255
int hex = Integer.parseInt("FF", 16);    // 255
int base36 = Integer.parseInt("z", 36);  // 35

long large = Long.parseLong("7FFFFFFFFFFFFFFF", 16);
// 9223372036854775807L == Long.MAX_VALUE
~~~

You can pass signed numbers with a leading `+` or `-`:

~~~java
int a = Integer.parseInt("-FF", 16); // -255
int b = Integer.parseInt("+1010", 2); // 10
~~~

However, `Integer.parseInt("FFFFFFFF", 16)` **throws `NumberFormatException`**: that positive hex string represents 4,294,967,295, which is outside the signed `int` range. It does **not** automatically treat `FFFFFFFF` as `-1`. To interpret the bit pattern as unsigned, use `parseUnsignedInt` (Section 5).

Key point: signed parsing APIs try to read a **signed mathematical value** within `int` or `long` range, not automatically accept a two's complement bit string.

### 3.2. Prefixes 0x/0b are not accepted by default by parseInt

~~~java
Integer.parseInt("FF", 16);       // 255
Integer.parseInt("0xFF", 16);     // NumberFormatException
Integer.parseInt("0b1010", 2);   // NumberFormatException
Integer.decode("0xFF");          // 255
Integer.decode("#FF");           // 255
Integer.decode("0377");          // 255: leading 0 indicates octal
~~~

`parseInt(text, radix)` requires valid digits for the given radix, except that `+`/`-` signs are supported; it does not automatically handle literal prefixes `0x`, `0b`. `Integer.decode`/`Long.decode` have rules to recognize `0x`, `0X`, `#`, or a leading `0` for octal, but **should not be considered a general parser for binary `0b` literals**.

For text formats following a protocol, the most controllable approach is to validate the prefix separately (if any), determine the radix, and parse the digit portion with the right API. Be especially careful with numbers having leading zeros: `Integer.parseInt("010",10) == 10`, whereas `Integer.decode("010") == 8`.

### 3.3. Literal syntax in source code differs from runtime text

When writing Java directly:

~~~java
int binaryLiteral = 0b1010; // 10
int hexLiteral = 0xFF;      // 255
int octalLiteral = 0377;   // 255: legacy octal syntax
int grouped = 1_000_000;   // 1000000
~~~

Prefixes and underscores are **processed by the Java compiler in source code**. That does not mean `Integer.parseInt("0b1010",2)` or `Integer.parseInt("1_000_000",10)` will accept them. Input strings containing `_` must be validated against a schema before stripping grouping characters; do not blindly strip invalid characters from external data.

### 3.4. BigInteger for values exceeding int/long range

~~~java
import java.math.BigInteger;

BigInteger huge = new BigInteger("FFFFFFFFFFFFFFFF", 16);
// 18446744073709551615, larger than Long.MAX_VALUE

BigInteger base36 = new BigInteger("Z", 36);
// 35

String backToHex = huge.toString(16);
// "ffffffffffffffff"
~~~

`BigInteger(String, radix)` is useful when the **mathematical value** exceeds 64 bits or when exact operations on large integers must be controlled. `BigInteger` supports negative numbers, so `new BigInteger("-FF",16)` yields -255. It does not automatically enforce an "unsigned 64-bit" convention for every value: the application must still check contract ranges when needed.

## 4. Writing Signed Numbers in Multiple Bases

Use `Integer.toString(value, radix)`, `Long.toString(value, radix)`:

~~~java
int n = 255;

String binary = Integer.toString(n, 2); // "11111111"
String octal = Integer.toString(n, 8);  // "377"
String decimal = Integer.toString(n, 10); // "255"
String hex = Integer.toString(n, 16);   // "ff"
String base36 = Integer.toString(35, 36); // "z"
~~~

Specialized methods are also available:

~~~java
Integer.toBinaryString(255); // "11111111"
Integer.toOctalString(255);  // "377"
Integer.toHexString(255);    // "ff"

Long.toBinaryString(255L);  // "11111111"
Long.toHexString(255L);     // "ff"
~~~

**Distinguish negative numbers:** `Integer.toString(-1,16)` returns `"-1"` (a negative number in base 16), whereas `Integer.toHexString(-1)` returns `"ffffffff"`, which is the **32-bit pattern** interpreted as unsigned. These are two different formatting goals.

If an interface requires uppercase `A`–`F` characters, you can use `toUpperCase(Locale.ROOT)` on the hex string or an appropriate formatter:

~~~java
String upperHex = Integer.toHexString(255)
        .toUpperCase(java.util.Locale.ROOT); // "FF"
~~~

Watch the width: `Integer.toHexString(5)` produces `"5"`, without automatically prepending `00000005`. If you need 8 digits for 32 bits, format explicitly or pad with length checks, for example:

~~~java
String hex32 = String.format(java.util.Locale.ROOT,
        "%08X", 5); // "00000005"
~~~

`%X` in `Formatter` is **hexadecimal**, not binary. Do not use `%b` to print binary: in Java `Formatter`, `%b` is a boolean conversion (true/false according to rules), not base 2.

## 5. Reading and Writing Unsigned int (unsigned 32-bit)

Java does not have a dedicated `uint32` primitive type. For unsigned 32-bit values `0..4294967295`, you can use **`int` as a 32-bit container**, then use unsigned APIs when interpretation is needed.

### 5.1. Reading a 32-bit pattern with parseUnsignedInt

~~~java
int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
// bits == -1 when viewed as a signed int.
// But 32 bits all set to 1 correspond to unsigned 4294967295.
~~~

`Integer.parseUnsignedInt(text, radix)` accepts a **non-negative** integer value in `[0, 2^32 - 1]` for the given radix, and returns an `int` holding the exact 32 bits. Because `int` is signed, the resulting value may appear negative.

- `Integer.parseUnsignedInt("FFFFFFFF",16)` yields `-1`.
- `Integer.parseUnsignedInt("80000000",16)` yields `Integer.MIN_VALUE`.
- `Integer.parseUnsignedInt("100000000",16)` throws `NumberFormatException` because it is larger than 32 bits.
- Strings with a minus sign like `"-1"` are not valid unsigned values; do not use them to represent `0xFFFFFFFF`.

### 5.2. Writing as unsigned

~~~java
int bits = -1;

String signed = Integer.toString(bits); // "-1"
String unsignedDec = Integer.toUnsignedString(bits); // "4294967295"
String unsignedHex = Integer.toUnsignedString(bits, 16); // "ffffffff"
String unsignedBin = Integer.toUnsignedString(bits, 2);
// 32 '1' characters
~~~

`Integer.toHexString(bits)` also represents the bit pattern as unsigned hex, so for `-1` it yields `"ffffffff"`. However, `Integer.toString(bits,16)` differs: `"-1"`.

To perform 32-bit unsigned arithmetic within a representable positive numeric range, convert to `long`:

~~~java
int rawBits = -1;
long unsignedValue = Integer.toUnsignedLong(rawBits);
// 4294967295L
~~~

Because `long` has 64 bits, the entire unsigned 32-bit range fits in **signed long**. This is a convenient option when you need to compare, add, or output a `uint32` field, as long as you continue managing potential overflow when added or multiplied values exceed `Long.MAX_VALUE`.

### 5.3. Unsigned comparison and division

The same bits `-1` are smaller than `1` as signed, but as unsigned they are `4294967295` (greater than 1):

~~~java
int bits = -1;

int signedCompare = Integer.compare(bits, 1); // < 0
int unsignedCompare = Integer.compareUnsigned(bits, 1); // > 0

int quotient = Integer.divideUnsigned(bits, 2); // 2147483647
int remainder = Integer.remainderUnsigned(bits, 2); // 1
~~~

`compareUnsigned` returns negative/0/positive according to comparison rules, and **does not promise to always return exactly -1 or 1 across all implementations**. Check `< 0`, `== 0`, `> 0` instead of relying on a specific numeric value.

Primitive addition/subtraction/multiplication still operate on bits modulo \(2^{32}\). If the contract requires **reporting an error when an unsigned operation exceeds 2^32-1**, widen to `long` before computing and check the range, or use `BigInteger` when calculations can exceed `long`. Do not assume ordinary `a + b` automatically detects unsigned overflow.

## 6. Reading and Writing Unsigned long (unsigned 64-bit)

Unsigned 64-bit range:

\[
0 \le u \le 2^{64}-1=18446744073709551615.
\]

The signed `long` range only goes up to `9223372036854775807`. Therefore, **it is impossible to represent the entire unsigned 64-bit range as a positive `long` value**.

### 6.1. Holding the bit pattern in long

~~~java
long bits = Long.parseUnsignedLong("18446744073709551615");
// bits == -1L when viewed as a signed long

String unsignedDec = Long.toUnsignedString(bits);
// "18446744073709551615"

String unsignedHex = Long.toUnsignedString(bits, 16);
// "ffffffffffffffff"
~~~

`Long.parseUnsignedLong` accepts non-negative values within the 64-bit range and returns the exact bit pattern. Larger strings, such as `"18446744073709551616"`, throw `NumberFormatException`.

`Long.parseLong("18446744073709551615")` **does not** succeed: it is a positive value exceeding `Long.MAX_VALUE`. If you want to store the exact positive value rather than just the bit pattern, choose `BigInteger`.

### 6.2. Interpreting an unsigned 64-bit value as a positive BigInteger

~~~java
long bits = -1L;

java.math.BigInteger unsigned =
        new java.math.BigInteger(Long.toUnsignedString(bits));
// 18446744073709551615

String hex = unsigned.toString(16);
// "ffffffffffffffff"
~~~

This is an easy-to-understand way: convert the bit pattern into an unsigned decimal string, then parse it into a positive `BigInteger`. There are more efficient ways based on two 32-bit halves or a byte array with `new BigInteger(1, bytes)`, but you must be careful with **width, byte order, and sign**.

Example range check when converting back to unsigned long:

~~~java
BigInteger maxUnsignedLong = BigInteger.ONE.shiftLeft(64)
        .subtract(BigInteger.ONE);

BigInteger candidate = new BigInteger("18446744073709551615");

if (candidate.signum() < 0
        || candidate.compareTo(maxUnsignedLong) > 0) {
    throw new IllegalArgumentException("Out of uint64 range");
}

// longValue() returns the low 64 bits (may be negative when viewed as signed long).
long storageBits = candidate.longValue();
String roundTrip = Long.toUnsignedString(storageBits);
~~~

Here `longValue()` is only safe **under a bit-pattern storage contract** and **after checking** that `candidate` lies in `[0,2^64-1]`. It does not interpret a large unsigned value as a positive long. Meanwhile, `longValueExact()` will throw an error for unsigned values larger than `Long.MAX_VALUE`, even though they are valid in uint64.

### 6.3. Unsigned long comparison and division

~~~java
long allOnes = -1L;

boolean greaterThanOne =
        Long.compareUnsigned(allOnes, 1L) > 0; // true

long q = Long.divideUnsigned(allOnes, 2L);
// When viewed as signed long: 9223372036854775807

long r = Long.remainderUnsigned(allOnes, 2L); // 1
~~~

Comparison operators `<`, `>` on primitive `long` use **signed semantics**, which are unsuitable for comparing unsigned values that have the sign bit set. If data comes from a protocol defining uint64, prefer `Long.compareUnsigned`, `divideUnsigned`, `remainderUnsigned`, and `toUnsignedString` for correct handling.

## 7. Unsigned Byte and Short: Reading Binary Files

A byte in Java (`byte`) is signed, ranging `-128..127`, whereas a `uint8` field in a binary file ranges `0..255`.

~~~java
byte raw = (byte) 0xFF; // raw == -1 when viewed as a signed byte

int unsignedByte = Byte.toUnsignedInt(raw); // 255
int masked = raw & 0xFF; // 255
~~~

The `& 0xFF` operation strips the sign-extended bits when converting `byte` to `int`. `Byte.toUnsignedInt` expresses the intent more clearly. For 16-bit unsigned `short`, use `Short.toUnsignedInt(rawShort)` for range `0..65535`.

With `DataInputStream`:

~~~java
// in is a valid, open DataInputStream:
int u8 = in.readUnsignedByte();  // 0..255
int u16 = in.readUnsignedShort(); // 0..65535, big-endian byte order
~~~

This snippet sits inside a method with a `DataInputStream in` variable; it may throw `IOException`, including EOF. With `ByteBuffer`, you must specify `ByteOrder.BIG_ENDIAN` or `LITTLE_ENDIAN` per format, then call `getInt()`/`getLong()` to obtain the bits and use unsigned APIs to interpret them. **Endianness** determines how bytes are assembled into multi-byte numbers, while **signed/unsigned** determines how the value is read after assembly: these are two separate concerns.

### 7.1. Fixed-width hex output

In a protocol, each byte is often displayed as **two hex digits**, each 32-bit number as **eight hex digits**, and each 64-bit number as **16 hex digits**. For example:

~~~java
byte b = (byte) 0x0A;

String byteHex = String.format(java.util.Locale.ROOT,
        "%02X", Byte.toUnsignedInt(b)); // "0A"

String intHex = String.format(java.util.Locale.ROOT,
        "%08X", 5); // "00000005"
~~~

Padding can be important to preserve the exact width of a file/protocol. `Integer.toHexString(5)` returns `"5"`, losing the "8-digit" structure if the receiver expects a fixed-width 32-bit field. Conversely, padding does not increase mathematical precision; it is purely a presentation convention.

## 8. Complete Java 17+ Program

The following program demonstrates both signed parsing/formatting and unsigned parsing/formatting, widening unsigned int to long, unsigned comparison/division, BigInteger for uint64, and input errors. Create the file **`RadixUnsignedDemo.java`**:

~~~java
import java.math.BigInteger;
import java.util.Locale;

public class RadixUnsignedDemo {
    public static void main(String[] args) {
        int value = Integer.parseInt("FF", 16);

        System.out.println("hex FF -> dec: " + value);
        System.out.println("255 -> binary: " + Integer.toString(value, 2));
        System.out.println("255 -> octal: " + Integer.toString(value, 8));
        System.out.println("35 -> base36: " + Integer.toString(35, 36));
        System.out.println("decode 0xFF: " + Integer.decode("0xFF"));

        int bits = Integer.parseUnsignedInt("FFFFFFFF", 16);
        System.out.println("int signed storage: " + bits);
        System.out.println("int unsigned dec: "
                + Integer.toUnsignedString(bits));
        System.out.println("int unsigned hex: "
                + Integer.toUnsignedString(bits, 16));
        System.out.println("int unsigned as long: "
                + Integer.toUnsignedLong(bits));
        System.out.println("int compareUnsigned to 1: "
                + Integer.compareUnsigned(bits, 1));
        System.out.println("int divideUnsigned by 2: "
                + Integer.divideUnsigned(bits, 2));
        System.out.println("int remainderUnsigned by 2: "
                + Integer.remainderUnsigned(bits, 2));

        long longBits = Long.parseUnsignedLong(
                "18446744073709551615");
        System.out.println("long signed storage: " + longBits);
        System.out.println("long unsigned dec: "
                + Long.toUnsignedString(longBits));
        System.out.println("long unsigned hex: "
                + Long.toUnsignedString(longBits, 16));
        System.out.println("unsigned long BigInteger: "
                + new BigInteger(Long.toUnsignedString(longBits)));

        System.out.println("hex padded: "
                + String.format(Locale.ROOT, "%08X", bits));
        System.out.println("byte unsigned: "
                + Byte.toUnsignedInt((byte) 0xFF));
        System.out.println("binary padded: "
                + String.format(Locale.ROOT, "%8s",
                        Integer.toBinaryString(5)).replace(' ', '0'));

        try {
            Integer.parseInt("FFFFFFFF", 16);
        } catch (NumberFormatException ex) {
            System.out.println("signed hex overflow: NumberFormatException");
        }

        try {
            Integer.parseUnsignedInt("100000000", 16);
        } catch (NumberFormatException ex) {
            System.out.println("unsigned int overflow: NumberFormatException");
        }

        try {
            Long.parseUnsignedLong("18446744073709551616");
        } catch (NumberFormatException ex) {
            System.out.println("unsigned long overflow: NumberFormatException");
        }
    }
}
~~~

Run:

~~~bash
javac RadixUnsignedDemo.java
java RadixUnsignedDemo
~~~

Output:

~~~text
hex FF -> dec: 255
255 -> binary: 11111111
255 -> octal: 377
35 -> base36: z
decode 0xFF: 255
int signed storage: -1
int unsigned dec: 4294967295
int unsigned hex: ffffffff
int unsigned as long: 4294967295
int compareUnsigned to 1: 1
int divideUnsigned by 2: 2147483647
int remainderUnsigned by 2: 1
long signed storage: -1
long unsigned dec: 18446744073709551615
long unsigned hex: ffffffffffffffff
unsigned long BigInteger: 18446744073709551615
hex padded: FFFFFFFF
byte unsigned: 255
binary padded: 00000101
signed hex overflow: NumberFormatException
unsigned int overflow: NumberFormatException
unsigned long overflow: NumberFormatException
~~~

Quick explanation table:

| Program line | What is verified |
| --- | --- |
| `hex FF -> dec: 255` | Hex parsing converts to numeric value, does not "keep radix" in variable |
| `int signed storage: -1` | `FFFFFFFF` is stored as a 32-bit all-`1` pattern |
| `int unsigned dec: 4294967295` | Same bits formatted in unsigned 32-bit domain |
| `int unsigned as long: 4294967295` | `long` is wide enough to hold uint32 as a positive number |
| `long signed storage: -1` | Largest uint64 does not fit in positive signed long |
| `unsigned long BigInteger: 18446744073709551615` | `BigInteger` stores the full positive value |
| `NumberFormatException` lines | Parser rejects values exceeding the defined range rather than wrapping when reading text |
| `hex padded`, `binary padded` | Radix and display width are two separate policies |

The output is deterministic because the lesson uses no randomness, and the example uses standard Java 17 APIs. Do not replace `Long.parseUnsignedLong` with `Long.parseLong` in the max uint64 example: signed long will throw an out-of-range error.

## 9. Round-trip: Reading and Writing Without Changing Value or Bit Pattern

### 9.1. Signed round-trip

For an `int x` and a valid radix from 2 to 36:

~~~java
int x = -255;
int radix = 16;

String text = Integer.toString(x, radix); // "-ff"
int parsed = Integer.parseInt(text, radix); // -255
~~~

The signed string reflects the **mathematical value** of `x`.

### 9.2. Unsigned round-trip by bit pattern

~~~java
int originalBits = -1;
int radix = 16;

String wireText = Integer.toUnsignedString(originalBits, radix);
// "ffffffff"

int restoredBits = Integer.parseUnsignedInt(wireText, radix);
// -1, same bit pattern as originalBits

boolean sameBits = restoredBits == originalBits; // true
~~~

For `long`, substitute `Long.toUnsignedString` and `Long.parseUnsignedLong`. This is a round-trip of the **bit pattern**, not a guarantee that the signed value displays as positive.

You can write a property test:

~~~java
for (int radix = Character.MIN_RADIX;
        radix <= Character.MAX_RADIX; radix++) {
    int value = -123456789;
    String text = Integer.toUnsignedString(value, radix);
    int reconstructed = Integer.parseUnsignedInt(text, radix);
    if (reconstructed != value) {
        throw new AssertionError("Mismatch at radix " + radix);
    }
}
~~~

Place this snippet inside a valid method. For broader testing, pick boundaries `0`, `1`, `-1`, `Integer.MIN_VALUE`, `Integer.MAX_VALUE`, and several fixed-seed random values. Remember `MIN_RADIX=2` and `MAX_RADIX=36`.

### 9.3. Leading zeros, letter case, and canonical form

Reading both `"000A"` and `"a"` in radix 16 yields value 10, but formatting back with `Integer.toString(10,16)` usually gives `"a"`, **failing to restore the exact original width/casing**.

If you need to transmit data as exactly 4 uppercase hex characters, you must separately store or specify **fixed width = 4**, **case = uppercase**, **prefix = none**, and an input validation policy. Numeric parsing/formatting cannot automatically preserve text-layout details that were discarded.

If a format uses `0x`, `0b`, or grouping characters, the parser must strip/validate them explicitly. Do not mix "value string" with "display format" without a contract.

## 10. Testing and Diagnosing Input Data

### 10.1. Cases that must be validated

The APIs `parseInt`, `parseLong`, `parseUnsignedInt`, `parseUnsignedLong` can throw `NumberFormatException` when:

- The string contains digits invalid for the radix: e.g. `"2"` in base 2, `"G"` in base 16.
- The value exceeds the corresponding signed/unsigned range.
- There are no digits to parse, such as an empty string.
- There is a prefix the API does not accept, e.g. `"0xFF"` with `parseInt(...,16)`.
- A minus sign appears in non-negative unsigned data per contract.
- The radix is outside the supported range (for parsers with a radix parameter).

`null` is also not a valid numeric string; depending on the overload/JDK, the API may throw `NumberFormatException` or a related error. At application boundaries, explicitly check for null before parsing to provide clear validation messages instead of relying on internal library messages.

Example:

~~~java
static int parseHexUnsigned32(String input) {
    if (input == null || !input.matches("[0-9A-Fa-f]{1,8}")) {
        throw new IllegalArgumentException("Expected 1..8 hex digits");
    }
    return Integer.parseUnsignedInt(input, 16);
}
~~~

This is a **method** that must be placed in a Java class. It intentionally accepts only ASCII hex without prefix, without whitespace, without a negative sign, and at most 8 digits. Depending on your format, you may need to require **exactly 8 digits** rather than 1..8.

Note that some Java parsing APIs accept Unicode digit characters according to `Character.digit`; if the protocol requires strict ASCII, validate the alphabet yourself first. Never assume "parsing succeeded" implies the input used the exact character set specified by the protocol.

### 10.2. Formatting must reflect type and width

For the number `-1`:

| Method | String |
| --- | --- |
| `Integer.toString(-1, 16)` | `-1` |
| `Integer.toHexString(-1)` | `ffffffff` |
| `Integer.toUnsignedString(-1)` | `4294967295` |
| `Long.toString(-1L, 16)` | `-1` |
| `Long.toHexString(-1L)` | `ffffffffffffffff` |
| `Long.toUnsignedString(-1L)` | `18446744073709551615` |

If you send a 32-bit field as 64-bit hex, the extra `f` digits can make the receiver think the value is larger. Ensure **32/64 width**, **signedness**, and **radix** match the schema. Do not take `toHexString` of a `long` that was sign-extended from an `int` and expect to always get 8 characters.

### 10.3. Endianness and unsigned are two different layers

For example, two bytes `01 00`:

- 16-bit big-endian: `0x0100 = 256`.
- 16-bit little-endian: `0x0001 = 1`.

Both can be interpreted as unsigned 16-bit after assembly. If reading from `ByteBuffer`, select `order(ByteOrder.LITTLE_ENDIAN)` or `order(ByteOrder.BIG_ENDIAN)` per the protocol, then use `Short.toUnsignedInt` or corresponding methods. Do not try to fix a byte-order bug using `toUnsignedString`; it only changes **sign interpretation**, not byte order.

## 11. Common Mistakes

1. **Assuming Java has dedicated uint32/uint64 primitives.** It does not; use `int`/`long` as bit containers with unsigned APIs, or use `long`/`BigInteger` for positive values that must be preserved.
2. **Reading `FFFFFFFF` with `Integer.parseInt(...,16)`.** It exceeds signed int; to get 32 bits all set to 1, use `parseUnsignedInt`.
3. **Using `Long.parseLong` for max uint64.** `18446744073709551615` exceeds signed long; use `parseUnsignedLong` or `BigInteger`.
4. **Assuming `parseInt("0xFF",16)` accepts prefixes.** It does not; `decode` has its own rules, or strip the prefix first then parse.
5. **Confusing literal syntax with runtime parsing.** `0b1010` and `1_000` are valid in Java source, not automatically valid in parsed strings.
6. **Using `Integer.toString(-1,16)` to output a bit pattern.** It produces `-1`; use `toHexString`/`toUnsignedString` to display unsigned bits.
7. **Comparing two uint32 values stored in int using `>`/`<`.** When the sign bit is set, signed ordering differs from unsigned ordering; use `compareUnsigned`.
8. **Dividing uint64 using `/` on long.** When the bit pattern has a negative signed value, signed division is wrong; use `Long.divideUnsigned`.
9. **Converting uint64 to BigInteger via `BigInteger.valueOf(bits)` when bits is negative.** That creates a negative BigInteger; for a positive unsigned value, use `new BigInteger(Long.toUnsignedString(bits))` or construct from bytes with positive signum.
10. **Using `intValueExact`/`longValueExact` to extract the bit pattern of a large uint64.** They reject values exceeding the signed range even if valid as unsigned. Check the unsigned range first, then take only the low 64 bits per contract.
11. **Forgetting leading zeros.** Parsers do not automatically retain the original digit count; format as fixed-width if the protocol requires it.
12. **Confusing hex uppercase/lowercase with different values.** Radix-16 parsers accept both A–F and a–f, though canonical output may be lowercase only.
13. **Assuming unsigned handling automatically handles byte order.** It does not; endianness is determined during byte assembly/reading.
14. **Assuming successful parsing means input normalization is already valid.** You may still need to check ASCII, prefix, sign, whitespace, width, and fixed format.
15. **Using primitive addition as if it automatically reports unsigned overflow.** It can wrap; if wrapping is disallowed, check range using a wider type/`BigInteger`.
16. **Using `%b` in `String.format` for binary output.** `%b` is for boolean formatting; use `Integer.toBinaryString`.
17. **Forgetting the boundary between bit encoding and mathematical value.** The same `-1` can mean different things depending on width and signedness; document these in the API.

## 12. Practice Questions with Answers

**Question 1.** What is the value of `Integer.parseInt("101101",2)`?

**Answer:** 45, because `32+8+4+1=45`.

**Question 2.** Do `Integer.parseInt("FF",16)` and `Integer.parseUnsignedInt("FF",16)` differ?

**Answer:** No, both return int 255. Differences appear for values with the sign bit set or exceeding signed int range, such as `FFFFFFFF`.

**Question 3.** Why does `Integer.parseUnsignedInt("FFFFFFFF",16)` return `-1`?

**Answer:** The method stores the 32-bit all-`1` pattern in a signed `int`; those same bits are interpreted as -1 when signed and 4294967295 when unsigned.

**Question 4.** To get a positive uint32 value from `int raw = -1;`, what should you use?

**Answer:** `long u = Integer.toUnsignedLong(raw);` gives `4294967295L`.

**Question 5.** To preserve the exact positive arithmetic value of the largest unsigned long, which type should you use?

**Answer:** `BigInteger`, e.g., `new BigInteger("18446744073709551615")`. `Long.parseUnsignedLong` only stores the 64-bit pattern in `long` (whose signed view is -1).

**Question 6.** Why does `Integer.toString(-1,16)` differ from `Integer.toHexString(-1)`?

**Answer:** The first represents the **signed number -1** as `"-1"`; the second represents the **unsigned 32-bit pattern** as `"ffffffff"`.

**Question 7.** Should you use `Integer.decode("010")` to read a decimal string `010` from a user?

**Answer:** No if the contract requires decimal; `decode("010")` interprets octal and yields 8. Use `parseInt("010",10)` to get 10.

**Question 8.** A protocol requires exactly four uppercase hex digits for a 16-bit field with value 10. What is the standard output?

**Answer:** `000A`. `Integer.toHexString(10)` only gives `"a"`; use formatting with padding and uppercase.

**Question 9.** Is `Long.compareUnsigned(-1L,1L) > 0` true or false?

**Answer:** True, because `-1L` has all 64 bits set to `1`, interpreted as `2^64-1` in unsigned comparison.

**Question 10.** In a file, byte `0xFF` is read as `byte -1`. How do you compute the count 255?

**Answer:** `Byte.toUnsignedInt(raw)` or `raw & 0xFF` gives int 255.

## 13. Official Documentation

- [`Integer` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): `parseInt`, `parseUnsignedInt`, `toUnsignedString`, `toUnsignedLong`, `compareUnsigned`, `divideUnsigned`, and `decode`.
- [`Long` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Long.html): `parseUnsignedLong`, `toUnsignedString`, `compareUnsigned`, `divideUnsigned`.
- [`BigInteger` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): multi-radix parsing/formatting and large integer arithmetic.
- [`Byte` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Byte.html): `toUnsignedInt` and unsigned byte interpretation.
- [`DataInputStream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readUnsignedByte`, `readUnsignedShort`.

**Remember:** Clearly specify the **radix for parsing/formatting**, **bit width**, **signed vs. unsigned**, and **output rules**. For unsigned 32-bit, use `int` as a bit container and `Integer.toUnsignedLong` when a positive number is needed; for unsigned 64-bit, use `long` to hold bits and `BigInteger` when a positive mathematical value larger than `Long.MAX_VALUE` is needed. Pay attention to prefixes, leading zeros, endianness, and out-of-range errors when reading external inputs.
