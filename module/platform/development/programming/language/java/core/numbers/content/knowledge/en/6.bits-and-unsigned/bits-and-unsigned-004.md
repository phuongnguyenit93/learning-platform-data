# Sign Extension When Promoting `byte` or `short` in Java

In Java, `byte` and `short` are **signed integers**. When converting from `byte`/`short` to a wider integer type such as `int` or `long`, Java preserves the **arithmetic value**. For negative numbers in two's complement representation, that requires **sign extension**: filling the newly added bits on the left with `1` bits. For non-negative values, the new bits are `0`.

This behavior is critical when handling binary bytes, color codes, network data, files, and bitmasks. If you want to interpret an 8- or 16-bit pattern as an **unsigned number**, you must interpret it explicitly, such as `b & 0xFF`, `s & 0xFFFF`, `Byte.toUnsignedInt(b)`, or `Short.toUnsignedInt(s)`.

## 1. What Do `byte` and `short` Represent?

| Java Type | Bit Width | Signed Value Range | Sign Bit |
| --- | ---: | --- | --- |
| `byte` | 8 | -128 to 127 | Bit 7 |
| `short` | 16 | -32768 to 32767 | Bit 15 |
| `int` | 32 | -2147483648 to 2147483647 | Bit 31 |
| `long` | 64 | -9223372036854775808 to 9223372036854775807 | Bit 63 |
| `char` | 16 | 0 to 65535 | No sign bit |

Java uses **two's complement** representation for signed integer types. For example, a byte consisting of eight bits `1111_1111` is understood as `-1` when viewed as a `byte`, yet can also be understood as `255` under the *unsigned 8-bit* convention.

In Java, **there is no primitive `unsigned byte` or `unsigned short`**. Raw data is often stored in `byte`/`short`; the programmer must explicitly choose between signed and unsigned interpretation when computing.

### Illustrating two ways to interpret the same byte

```text
Original bits:            1111 1111
Read as signed byte:             -1
Read as unsigned 8-bit:         255

Original bits:            1000 0000
Read as signed byte:           -128
Read as unsigned 8-bit:         128
```

The two views do not alter the original eight bits; they only change their **arithmetic meaning**. Even in Java source code, the literal `0xFF` has type `int` and value `255`; to store those eight bits in a `byte`, a cast is required:

```java
byte raw = (byte) 0xFF; // bits 11111111, byte value = -1
```

## 2. How Sign Extension Works When Widening to `int` and `long`

When widening a signed integer value from `byte` to `short`, `int`, or `long`, Java **preserves the signed value**. In two's complement binary representation, the added bits on the left are filled with the sign bit of the source value:

- If the source value's sign bit is `0` (non-negative value), `0` bits are added.
- If the sign bit is `1` (negative value), `1` bits are added.

For example, `byte b = -128` has original bits `1000_0000`. When promoted to `int`:

```text
byte -128 (8 bits):
                            1000 0000
int -128  (32 bits):
1111 1111 1111 1111 1111 1111 1000 0000
          24 new bits = all 1 bits
```

The result is interpreted as `-128` in `int`, **not +128**. Sign extension preserves the negative value instead of treating the old sign bit as an ordinary data bit.

For `byte b = 5`, the original bits are `0000_0101`; when promoted to `int`, all 24 added bits are `0` and the result remains `5`.

### Standard Results Table

| Expression | Decimal Value | 32-bit Pattern in Hex |
| --- | ---: | --- |
| `(int) (byte) 0x7F` | 127 | `0x0000007F` |
| `(int) (byte) 0x80` | -128 | `0xFFFFFF80` |
| `(int) (byte) 0xFF` | -1 | `0xFFFFFFFF` |
| `(int) (short) 0x7FFF` | 32767 | `0x00007FFF` |
| `(int) (short) 0x8000` | -32768 | `0xFFFF8000` |
| `(int) (short) 0xFFFF` | -1 | `0xFFFFFFFF` |

Here, the casts from `int` literals to `byte`/`short` **narrow the bit width first**, and then the outer `(int)` cast performs sign extension. Do not read this cast chain as a "sign-ignoring" operation.

## 3. Sign Extension vs. Zero Extension

**Zero extension** fills the left positions with `0` bits when widening. For negative `byte`/`short` values, ordinary integer conversion performs **sign extension**. If the data is actually an 8- or 16-bit unsigned number, you must strip the sign-extended bits to obtain the bit pattern as a positive number.

For `byte b = (byte) 0xFF`:

```text
b as byte:         1111 1111             (signed -1)

Normal promotion:
int b:              FFFFFFFF             (signed -1)

Keep low eight bits, fill remaining bits with 0:
b & 0xFF:           000000FF             (unsigned 255)
```

Using the AND operator:

```java
byte b = (byte) 0xFF;
int signed = b;             // -1: sign extension
int unsigned = b & 0xFF;    // 255: keeps low eight bits

short s = (short) 0xFFFF;
int signedShort = s;        // -1
int unsignedShort = s & 0xFFFF; // 65535
```

The key point is that `& 0xFF` **does not turn `byte` into an unsigned type**; it creates an `int` expression whose result is in the range `0..255`. For `short` and `& 0xFFFF`, the result is in `0..65535`.

### Why Does the Mask Work?

In `b & 0xFF`, `b` is promoted to `int` **before** the AND operation occurs. If `b == -1`, the bits after promotion are `0xFFFFFFFF`. The mask `0x000000FF` keeps the low eight bits and clears the high 24 bits:

```text
0xFFFFFFFF   // b = -1 after sign extension
0x000000FF   // mask
----------
0x000000FF   // 255
```

For `short`, the mask `0x0000FFFF` keeps the low 16 bits and clears the high 16 bits. The mask must match **the width of the original data**: `0xFF` for byte, `0xFFFF` for short.

## 4. The `Byte.toUnsignedInt` and `Short.toUnsignedInt` APIs

Java provides built-in methods to convert signed values into their corresponding unsigned values:

| Method | Input signed value | Returned `int` value |
| --- | --- | --- |
| `Byte.toUnsignedInt((byte) -1)` | -1 | 255 |
| `Byte.toUnsignedInt((byte) -128)` | -128 | 128 |
| `Byte.toUnsignedInt((byte) 127)` | 127 | 127 |
| `Short.toUnsignedInt((short) -1)` | -1 | 65535 |
| `Short.toUnsignedInt((short) -32768)` | -32768 | 32768 |

`Byte.toUnsignedInt(b)` is equivalent in result to `b & 0xFF`; `Short.toUnsignedInt(s)` is equivalent to `s & 0xFFFF`. These methods communicate intent clearly when readers encounter binary-data processing code.

```java
byte byteData = (byte) 0x80;
short shortData = (short) 0x8000;

int unsignedByte = Byte.toUnsignedInt(byteData);     // 128
int unsignedShort = Short.toUnsignedInt(shortData);  // 32768
```

Note: `Byte.toUnsignedInt` accepts **`byte`**, not any integer. `Short.toUnsignedInt` accepts **`short`**. When you want to inspect the low eight bits of an `int` value, `value & 0xFF` is usually more direct and clearer than casting temporarily to `byte` and calling the method.

Do not confuse `Integer.toUnsignedLong(int)` with the APIs above: it interprets **all 32 bits** of an `int` in the range `0..4294967295` and returns a `long`; it does not replace taking only the low 8 or 16 bits of data.

## 5. `char` Is Zero-Extended: A Contrast Case

`char` has 16 **unsigned** bits. When `char` is promoted to `int`, Java fills the upper bits with `0` and keeps the value in `0..65535`. Conversely, `short` is a **signed** type, so two values with the same 16 bits can produce different `int` results.

```java
short signed = (short) 0xFFFF;  // -1
char unsigned = (char) 0xFFFF; // 65535

int fromShort = signed;   // -1, int pattern is FFFFFFFF
int fromChar = unsigned;  // 65535, int pattern is 0000FFFF
```

`char` in Java represents a **UTF-16 code unit**; the example above merely uses its unsigned representation to contrast bit extension behavior. You should not use `char` as a general-purpose substitute for unsigned integers across APIs.

### Casting a Negative `byte` to `char`: A Subtle Detail

`byte` cannot automatically widen to `char` because the value ranges of the two types do not subsume each other under widening primitive conversion rules. An explicit cast can produce a surprising result:

```java
byte minusOne = -1;
// char invalid = minusOne; // compile error: cast required

char castDirectly = (char) minusOne;      // 65535 (0xFFFF)
char lowEightBits = (char) (minusOne & 0xFF); // 255 (0x00FF)
```

When casting a negative `byte` directly to `char`, converting from the signed value into `char`'s 16-bit range produces `0xFFFF` in the case of `-1`. If the goal is to convert **an unsigned byte** into a code unit with value `0..255`, mask with `& 0xFF` first.

## 6. Unary/Binary Numeric Promotion Rules and Bit Operations

Not only assignments like `int x = b;` trigger sign extension. Java performs **numeric promotion** for many operators:

- `b + 1`, `b - 1`, `b * 2`: `byte` is promoted to `int` before computation.
- `~b`: the bitwise complement operator operates on the promoted `int` value.
- `b << 1`, `b >> 1`, and `b >>> 1`: the left operand `byte`/`short` is promoted to `int` before shifting.
- `b & mask`, `b | mask`, `b ^ mask`: bit manipulation operates on the result after binary numeric promotion.

Example with `byte b = -1`:

```java
byte b = -1;
int promoted = b;     // -1, bits FFFFFFFF
int complement = ~b;  // 0, because ~FFFFFFFF = 00000000
int shifted = b >> 1; // -1, arithmetic right shift preserves sign bit
```

If a learner only pictures `b` as eight bits `11111111`, they might mispredict the result of a shift or `~b`; most of these expressions **already operate on a 32-bit `int`**.

### `>>` and `>>>` When the Source Is a Negative `byte`

`>>` performs a right shift preserving the sign bit of the promoted type; `>>>` performs a logical right shift and fills with `0`. However, **`>>>` does not automatically restrict the shift to the original eight bits**:

```java
byte b = -1;
int arithmetic = b >> 1;          // -1
int logicalOnInt = b >>> 1;       // 2147483647 (0x7FFFFFFF)
int logicalOnByte = (b & 0xFF) >>> 1; // 127 (0x7F)
```

Why doesn't `b >>> 1` give 127? `b` became `0xFFFFFFFF` of type `int`, so the 32-bit logical shift gives `0x7FFFFFFF`. To shift an **unsigned 8-bit value**, apply `& 0xFF` **before shifting**.

The same rule applies to `short`: `(s & 0xFFFF) >>> 1` shifts an unsigned 16-bit value as intended.

## 7. Combining Multiple Bytes into an Unsigned Integer

When combining two bytes from a file or network protocol into a 16-bit **unsigned** number, you must keep the low eight bits of **each byte** before combining.

Suppose the high byte has bits `1000_0000` (`0x80`) and the low byte is `1111_1111` (`0xFF`). The desired 16-bit unsigned value is `0x80FF` = `33023`.

```java
byte high = (byte) 0x80;  // -128
byte low = (byte) 0xFF;   // -1

int combined = ((high & 0xFF) << 8) | (low & 0xFF);
// combined = 0x80FF = 33023
```

Step by step:

1. `high & 0xFF` turns the pattern `0x80` into `128` of type `int`.
2. Left shift by eight bits: `128 << 8` becomes `0x8000` (32768).
3. `low & 0xFF` turns the pattern `0xFF` into `255`.
4. Bitwise OR `0x8000 | 0x00FF` yields `0x80FF` (33023).

**Common mistake:** writing `(high << 8) | low` without masking causes `low = -1` to sign-extend to `0xFFFFFFFF`, pulling the entire OR result to `-1`—the wrong value.

For protocol data, the **byte order** (*big endian/little endian*) convention must still be known from the specification. The example above assumes `high` is the most significant byte; sign extension is only one part of decoding binary data properly.

## 8. Complete Java 17+ Example and Output

Create the file **`SignExtensionDemo.java`**:

```java
public class SignExtensionDemo {
    public static void main(String[] args) {
        byte minusOne = (byte) 0xFF;
        byte minus128 = (byte) 0x80;
        short shortMinusOne = (short) 0xFFFF;
        short shortMin = (short) 0x8000;

        System.out.println("byteSigned=" + (int) minusOne);
        System.out.printf("byteBitsInt=%08X%n", (int) minusOne);
        System.out.println("byteUnsigned=" + (minusOne & 0xFF));
        System.out.println("byteUnsignedAPI=" + Byte.toUnsignedInt(minusOne));
        System.out.println("byte128Signed=" + (int) minus128);
        System.out.println("byte128Unsigned=" + Byte.toUnsignedInt(minus128));

        System.out.println("shortSigned=" + (int) shortMinusOne);
        System.out.printf("shortBitsInt=%08X%n", (int) shortMin);
        System.out.println("shortUnsigned=" + (shortMinusOne & 0xFFFF));
        System.out.println("shortUnsignedAPI=" + Short.toUnsignedInt(shortMin));

        char chars = (char) 0xFFFF;
        System.out.printf("charBitsInt=%08X%n", (int) chars);
        System.out.println("castByteToChar=" + (int) (char) minusOne);
        System.out.println("maskedByteToChar=" + (int) (char) (minusOne & 0xFF));

        System.out.println("arithmeticShift=" + (minusOne >> 1));
        System.out.println("logicalShiftInt=" + (minusOne >>> 1));
        System.out.println("logicalShiftByte=" + ((minusOne & 0xFF) >>> 1));
        System.out.println("bitwiseComplement=" + (~minusOne));

        byte high = (byte) 0x80;
        byte low = (byte) 0xFF;
        int combined = ((high & 0xFF) << 8) | (low & 0xFF);
        int wrongCombined = (high << 8) | low;
        System.out.println("combinedUnsigned16=" + combined);
        System.out.println("combinedWithoutMask=" + wrongCombined);

        System.out.println("signedComparison=" + (minusOne == 0xFF));
        System.out.println("unsignedComparison=" + ((minusOne & 0xFF) == 0xFF));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac SignExtensionDemo.java
java SignExtensionDemo
```

**Exact output:**

```text
byteSigned=-1
byteBitsInt=FFFFFFFF
byteUnsigned=255
byteUnsignedAPI=255
byte128Signed=-128
byte128Unsigned=128
shortSigned=-1
shortBitsInt=FFFF8000
shortUnsigned=65535
shortUnsignedAPI=32768
charBitsInt=0000FFFF
castByteToChar=65535
maskedByteToChar=255
arithmeticShift=-1
logicalShiftInt=2147483647
logicalShiftByte=127
bitwiseComplement=0
combinedUnsigned16=33023
combinedWithoutMask=-1
signedComparison=false
unsignedComparison=true
```

When executed, `printf("%08X")` prints eight hex digits of the `int` representation. Thus `FFFFFFFF` proves that the negative sign of byte `-1` expanded to 32 bits; `0000FFFF` for `char` shows that the high 16 bits were filled with `0`.

## 9. Common Misconceptions

| Misconception | Correct Rule |
| --- | --- |
| "`byte b = (byte) 0xFF` makes `int x = b` equal 255." | `byte` is signed: `b == -1`; when promoted to `int` it stays `-1` due to sign extension. |
| "Casting `(int) b` strips the sign." | Widening casts preserve the signed value and extend the sign bit. |
| "`b & 0xFF` makes `b` unsigned." | `b` is unchanged; the expression produces a positive **`int`** from the low eight bits. |
| "`Short.toUnsignedInt(s)` sign-extends." | The API interprets `short` as **16 unsigned bits** and returns an `int` in 0..65535. |
| "`byte` and `char` are both 8 bits." | `byte` is 8-bit signed; `char` is a 16-bit unsigned UTF-16 code unit. |
| "`(char) (byte) 0xFF` has value 255." | Casting byte `-1` directly to char produces `65535`; mask first if you want 255. |
| "`b >>> 1` shifts exactly eight bits of the byte." | `b` is promoted to 32-bit `int` first; to shift unsigned 8-bit, mask beforehand. |
| "Combining two bytes with `(high << 8) | low` is always right." | Negative `low` sign-extends; mask each byte so high bits are not polluted. |
| "`(byte) 0xFF` creates a new unsigned byte type." | Casting to `byte` keeps only the low eight bits and interprets them as signed: result `-1`. |
| "Sign extension turns a negative value into a positive number." | Sign extension **preserves negative values** when converting to a wider integer type. |

## 10. Checklist for Auditing Bit-Handling Code

1. **Identify the source type:** 8-bit signed `byte`, 16-bit signed `short`, 16-bit unsigned `char`. The source type determines whether sign bits or `0` bits are added.
2. **Determine the data semantics:** is the data genuinely a signed number or raw 8/16 bits to be read as unsigned?
3. **Spot promotion points:** `int i = b`, `b + 1`, `b >> 1`, `b & mask` can all operate on a sign-extended `int`.
4. **Switch to unsigned interpretation before computing if needed:** for byte use `b & 0xFF` or `Byte.toUnsignedInt(b)`; for short use `s & 0xFFFF` or `Short.toUnsignedInt(s)`.
5. **When shifting/combining bytes:** mask each component before shifting/ORing; pay attention to the byte order specified by the data format.
6. **Verify using fixed-width hex:** `%08X` for `int`, comparing bit patterns against arithmetic results; distinguish signed values from raw bit patterns.

**Remember:** promoting a negative `byte`/`short` to `int`/`long` performs **sign extension**, preserving the negative value by padding with `1` bits. When you want to read the original bits as an **unsigned** number, apply a **mask** or an **unsigned API** before any operations where width and sign could affect the result.