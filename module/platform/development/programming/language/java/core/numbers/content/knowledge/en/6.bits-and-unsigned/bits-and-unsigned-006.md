# `Byte.toUnsignedInt`, `Short.toUnsignedInt`, and `Integer.toUnsignedLong`

Java has the integer types `byte` (8 bits), `short` (16 bits), and `int` (32 bits) with **signed** (two's complement) representation. However, many image formats, binary files, IDs, and network protocols define data fields as **unsigned** integers. The following three static methods read the full bit pattern as a non-negative value in a wider type, rather than misinterpreting the sign bit:

- `Byte.toUnsignedInt(byte value)`: keeps the low 8 bits, returns an `int` from **0 to 255**.
- `Short.toUnsignedInt(short value)`: keeps the low 16 bits, returns an `int` from **0 to 65,535**.
- `Integer.toUnsignedLong(int value)`: keeps the low 32 bits, returns a `long` from **0 to 4,294,967,295**.

These APIs have been available since Java 8 and work in Java 17+. They reinterpret the same data bits using a **value of a wider type**; they do not modify the input variable and do not introduce primitive `unsigned byte`, `unsigned short`, or `unsigned int` types in Java.

## 1. Why Convert to an Unsigned Value?

The bit pattern `1111_1111` (hex `0xFF`) has two interpretations:

- Java `byte`: **−1**, because the highest bit is the sign bit in two's complement.
- 8-bit unsigned integer: **255**, because all eight bits carry positive weight.

The same distinction occurs with `short` and `int`. For example, `0xFFFF` is `short -1` yet unsigned 16-bit `65535`; `0xFFFF_FFFF` is `int -1` yet unsigned 32-bit `4294967295`.

| Method | Input | Signed Input Range | Result Type | Unsigned Result Range |
| --- | --- | ---: | --- | ---: |
| `Byte.toUnsignedInt(b)` | `byte` (8 bits) | −128…127 | `int` | 0…255 |
| `Short.toUnsignedInt(s)` | `short` (16 bits) | −32,768…32,767 | `int` | 0…65,535 |
| `Integer.toUnsignedLong(i)` | `int` (32 bits) | −2,147,483,648…2,147,483,647 | `long` | 0…4,294,967,295 |

You must choose the method based on **the width of the original data type**. `Byte.toUnsignedInt` does not substitute for `Short.toUnsignedInt` when you have 16 bits; `Integer.toUnsignedLong` is not merely another way of casting `int` to `long`.

## 2. Zero Extension Mechanism and Bitmasks

Casting a negative `byte` to `int` or a negative `int` to `long` in Java performs **sign extension**: the new bits on the left copy the sign bit (1 for negative numbers). The three methods above aim to preserve the **unsigned** value of the exact original 8/16/32 bits, so they discard the `1` bits introduced by sign extension.

The result can be understood as equivalent to the following bitwise AND operations:

~~~java
int u8 = Byte.toUnsignedInt(b);        // equals b & 0xFF
int u16 = Short.toUnsignedInt(s);     // equals s & 0xFFFF
long u32 = Integer.toUnsignedLong(i); // equals ((long) i) & 0xFFFF_FFFFL
~~~

The snippet above is **illustrative code**: it assumes `b`, `s`, and `i` have already been declared as `byte`, `short`, and `int`, respectively. With `b & 0xFF`, the AND keeps the low 8 bits after `byte` is promoted to `int`. With `s & 0xFFFF`, it keeps the low 16 bits. With `i`, the mask must have type `long` (suffix `L`) to produce a positive number wide enough to hold 32 bits.

If the input is already non-negative, the result equals the input value itself. If the input is negative, the unsigned arithmetic result equals the signed value plus `2^8`, `2^16`, or `2^32`, respectively. This is a **value interpretation** rule, not an operation that mutates the original variable.

| Expression | Corresponding Signed Value | Unsigned Result |
| --- | ---: | ---: |
| `Byte.toUnsignedInt((byte) 0x80)` | −128 | 128 |
| `Byte.toUnsignedInt((byte) 0xFF)` | −1 | 255 |
| `Short.toUnsignedInt((short) 0x8000)` | −32768 | 32768 |
| `Short.toUnsignedInt((short) 0xFFFF)` | −1 | 65535 |
| `Integer.toUnsignedLong(0x8000_0000)` | −2147483648 | 2147483648 |
| `Integer.toUnsignedLong(0xFFFF_FFFF)` | −1 | 4294967295 |

Note: `Byte`, `Short`, and `Integer` are **wrapper classes**; these methods are `static`, so call them directly as shown in the table above without `new Byte(...)`.

## 3. Compilable and Runnable Java 17+ Example

Create the file `UnsignedConversionsDemo.java`:

~~~java
public class UnsignedConversionsDemo {
    public static void main(String[] args) {
        byte b = (byte) 0xFF;
        short s = (short) 0x8001;
        int i = 0xFFFF_FFFE;

        System.out.println("byte signed: " + b);
        System.out.println("byte unsigned: " + Byte.toUnsignedInt(b));
        System.out.println("short signed: " + s);
        System.out.println("short unsigned: " + Short.toUnsignedInt(s));
        System.out.println("int signed: " + i);
        System.out.println("int unsigned: " + Integer.toUnsignedLong(i));

        System.out.println("byte mask: " + (b & 0xFF));
        System.out.println("short mask: " + (s & 0xFFFF));
        System.out.println("int mask: " + (i & 0xFFFF_FFFFL));

        byte[] packet = {
            (byte) 0xFE, (byte) 0xDC, (byte) 0xBA, (byte) 0x98
        };
        int raw32 =
                (Byte.toUnsignedInt(packet[0]) << 24)
              | (Byte.toUnsignedInt(packet[1]) << 16)
              | (Byte.toUnsignedInt(packet[2]) << 8)
              | Byte.toUnsignedInt(packet[3]);
        long packetUnsigned = Integer.toUnsignedLong(raw32);

        System.out.printf("packet=0x%08X, unsigned=%d%n",
                raw32, packetUnsigned);

        System.out.println("signed compare: " + (-1 < 1));
        System.out.println("unsigned compare: "
                + (Integer.compareUnsigned(-1, 1) > 0));
    }
}
~~~

Compile and run:

~~~bash
javac UnsignedConversionsDemo.java
java UnsignedConversionsDemo
~~~

Output:

~~~text
byte signed: -1
byte unsigned: 255
short signed: -32767
short unsigned: 32769
int signed: -2
int unsigned: 4294967294
byte mask: 255
short mask: 32769
int mask: 4294967294
packet=0xFEDCBA98, unsigned=4275878552
signed compare: true
unsigned compare: true
~~~

Explanation:

- `0xFF` has all 8 bits equal to 1. As a `byte` it equals `-1`; via `Byte.toUnsignedInt` it is `255`.
- `0x8001` has the 16-bit sign bit equal to 1. As a `short` it equals `-32767`; via `Short.toUnsignedInt` it is `32769`.
- `0xFFFF_FFFE` as an `int` is `-2`; via `Integer.toUnsignedLong` it is `4294967294L`.
- The `mask` lines show that properly typed bitwise AND gives the same results as the explicit APIs. Expressing this with the method calls is often easier to read and states intent more clearly.

## 4. Reading Binary Fields from a Byte Array

Suppose a protocol specifies an **unsigned 32-bit, big-endian** ID consisting of four bytes `FE DC BA 98`. A Java `byte[]` still holds all the bits, yet elements starting with a 1 bit will print as negative numbers.

In the example:

1. `Byte.toUnsignedInt(packet[k])` turns each element into a number 0–255 before combining.
2. `<< 24`, `<< 16`, and `<< 8` position each byte properly, and `|` combines all 32 bits. `raw32` has the bit pattern `0xFEDCBA98` (which can look negative if printed as a signed `int`).
3. `Integer.toUnsignedLong(raw32)` converts this 32-bit pattern to a positive `long` `4275878552L`, matching the protocol's unsigned ID definition.

A 16-bit big-endian field can also be assembled:

~~~java
// byte[] data contains at least two elements, in big-endian order.
int unsigned16 = (Byte.toUnsignedInt(data[0]) << 8)
               | Byte.toUnsignedInt(data[1]);
~~~

This is illustrative code depending on `data`. If you already read the whole field with `ByteBuffer.getShort()`, use `Short.toUnsignedInt(shortValue)`; if read with `ByteBuffer.getInt()`, use `Integer.toUnsignedLong(intValue)`. The byte order (**big-endian/little-endian**) is dictated by the data format; the `toUnsigned...` methods do not reverse byte order automatically.

In the `<< 24` operation in the example, the intermediate `int` result may be negative yet still retains the exact bits for combining; the subsequent `Integer.toUnsignedLong` step then interprets the entire field as an unsigned number. There is no need to force each byte to `long` just because the highest bit of `raw32` is 1.

## 5. Comparing, Computing, and Unsigned Range Limits

For unsigned 8/16-bit values, an `int` is wide enough to hold the entire result. For unsigned 32-bit values, you need `long` because signed `int` maxes out at `2147483647`.

For example, `Integer.toUnsignedLong(-1) + 1` gives `4294967296L`, a valid `long` addition; however, that number has **exceeded the unsigned 32-bit range**. If writing back to a 32-bit field, check `0 <= value && value <= 0xFFFF_FFFFL` for the `long value` variable before casting `(int) value`. Casting down to `int` takes the low 32 bits, and the result can appear negative when printed using Java's signed representation. Casting `4294967296L` to `int` produces `0`: this is **data loss** if you did not validate the range first.

Signed and unsigned comparisons also differ:

~~~java
int a = -1;
int b = 1;
boolean signedLess = a < b;                         // true
boolean unsignedGreater = Integer.compareUnsigned(a, b) > 0; // true
boolean sameViaLong =
        Integer.toUnsignedLong(a) > Integer.toUnsignedLong(b); // true
~~~

This is standalone illustrative code inside a valid block/method. Signed `-1` is less than `1`, but the bits `0xFFFF_FFFF` representing unsigned 32-bit `4294967295` are greater than `1`. Do not use the `<` operator between two signed `int`s when the protocol requires **unsigned** ordering.

When data genuinely has signed semantics (negative deltas, negative temperatures, signed numbers in a specification), keep the signed interpretation. Unsigned conversion is a choice driven by **source data semantics**, not a trick to make all negative numbers disappear.

## 6. Common Mistakes and How to Avoid Them

### 6.1. Confusing Casting with Unsigned Conversion

~~~java
byte b = (byte) 0xFF;
int signedByte = (int) b;                  // -1: sign extension
int unsignedByte = Byte.toUnsignedInt(b); // 255

int i = -1;
long signedInt = (long) i;                   // -1
long unsignedInt = Integer.toUnsignedLong(i); // 4294967295
~~~

Casting `byte` to `int` and `int` to `long` preserves the **signed value**. The snippets in the common-mistakes section are inline examples, not standalone Java programs.

### 6.2. Placing the Mask Suffix in the Wrong Spot

~~~java
int i = -1;
long wrong = (long) (i & 0xFFFF_FFFF);     // -1
long correct = ((long) i) & 0xFFFF_FFFFL; // 4294967295
long preferred = Integer.toUnsignedLong(i); // 4294967295
~~~

`0xFFFF_FFFF` without `L` is an `int` constant with all 1 bits, i.e., `-1`. `i & -1` still yields `i`; casting to `long` afterward still sign-extends. Use the `long` mask `0xFFFF_FFFFL`, or simply use `Integer.toUnsignedLong`.

### 6.3. Shifting Bits Before Handling Sign Extension

For a negative `byte`, Java promotes the operand to `int` before shifting. `>>` shifts in `1` sign bits; `>>>` shifts in `0` bits yet **does not automatically create a primitive unsigned type**. A clear way to extract the high nibble of a byte is:

~~~java
byte encoded = (byte) 0xF0;
int highNibble = Byte.toUnsignedInt(encoded) >>> 4; // 15
~~~

If you shift a negative `byte` and use the result immediately without masking the right number of bits, the `1` bits from sign extension can interfere. Control the 8 bits before manipulating them.

### 6.4. Failing to Validate Data When Narrowing Back

These three methods produce values that accommodate the entire unsigned range via **type widening**. Nothing stops you from performing additions, multiplications, or casts that push the result outside the intended range. When storing back into 8/16/32 bits, validate whether the value matches the specification; a cast by itself can truncate high bits.

### 6.5. Confusing Unsigned 32-Bit with Unsigned 64-Bit

`Integer.toUnsignedLong` converts an unsigned **32-bit** value to a positive `long`, while Java's `long` is still a **signed 64-bit** type. It does not produce a positive value wide enough to hold the entire unsigned 64-bit range; for that case you may need `Long.compareUnsigned`, `Long.toUnsignedString`, or `BigInteger`.

`char` has an integer range of 0–65535 but carries **UTF-16 character** semantics. An unsigned 16-bit data field already stored in a `short` should still be read with clear intent using `Short.toUnsignedInt`.

## 7. Self-Practice Questions

**1.** If `byte b = (byte) 0x80`, what are `(int) b` and `Byte.toUnsignedInt(b)`?  
**Answer:** `-128` and `128`. Same low 8 bits, different extension and interpretation.

**2.** If `short s = (short) 0xFFFF`, what is the result of `Short.toUnsignedInt(s)`?  
**Answer:** `65535`, because all 16 bits are 1.

**3.** What does `Integer.toUnsignedLong(Integer.MIN_VALUE)` equal?  
**Answer:** `2147483648L`, corresponding to only bit 31 being 1 in unsigned 32-bit.

**4.** Why can `(long) (i & 0xFFFF_FFFF)` be wrong when `i` is negative?  
**Answer:** The mask is `int -1`, so it does not clear the sign bit; casting to `long` afterward still sign-extends. Use `0xFFFF_FFFFL` with `long` or `Integer.toUnsignedLong(i)`.

**5.** Which APIs can extract an unsigned number from big-endian byte data `FE DC BA 98`?  
**Answer:** Use `Byte.toUnsignedInt` on each byte to assemble the 32 bits, then `Integer.toUnsignedLong` to interpret the whole field as `4275878552L`.

## 8. Key Takeaways

- Start from the **original data width**: `byte` → `Byte.toUnsignedInt`; `short` → `Short.toUnsignedInt`; `int` → `Integer.toUnsignedLong`.
- The result is a **non-negative value in a wider type**, without changing the input variable or the low-bit representation.
- When manipulating bits, distinguish sign extension from masking; for unsigned 32-bit values, use a `long` mask constant if not using the API.
- When reading binary formats, follow the width and endianness in the specification; when comparing or writing back, validate the unsigned range and choose the appropriate comparison method.