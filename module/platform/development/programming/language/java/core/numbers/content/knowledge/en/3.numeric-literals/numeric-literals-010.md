# Reading Bit Patterns of Hex Literals with the Sign Bit Set in Java

In Java, a hexadecimal literal like `0x8000_0000` often surprises beginners: when printed as an `int`, the result is **-2_147_483_648** rather than positive 2_147_483_648. Similarly, `0xFFFF_FFFF` has the value **-1** as an `int`; yet `0xFFFF_FFFFL` has the value **4_294_967_295** as a `long`.

There is no arbitrary alteration of hex digits happening. What matters is **how many bits the pattern has, whether the type's highest bit is set, and whether we are reading that bit pattern as a signed or unsigned integer**.

## 1. From Hex Digits to Bit Patterns

Hexadecimal has 16 symbols `0`–`9` and `A`–`F`. Each hex digit corresponds to **4 bits**. For example:

| Hex | 4-Bit Binary | Hex Value |
| --- | --- | ---: |
| `0` | `0000` | 0 |
| `7` | `0111` | 7 |
| `8` | `1000` | 8 |
| `F` | `1111` | 15 |

Each hex digit combines into the bit pattern from left to right. For example, `0x8000_0000` corresponds to `10000000 00000000 00000000 00000000` (32 bits): only the bit in the highest position is set. `0xFFFF_FFFF` represents 32 bits all equal to 1.

The `0x` (or `0X`) prefix simply tells the compiler the literal uses **base 16**; the trailing `L` selects type `long`. Underscores `_` only group digits for readability: `0xFFFF_FFFF` and `0xFFFFFFFF` are completely equivalent.

## 2. Ranges of `int` and `long`: Which Bit Is the Sign Bit?

Java uses signed **32-bit** `int` and **64-bit** `long` integer types, with **two's complement** representation. Bit positions are numbered starting from 0 on the right.

| Type | Total Bits | Sign Bit | Pattern with Sign Bit = 0 | Pattern with Sign Bit = 1 |
| --- | ---: | ---: | --- | --- |
| `int` | 32 | bit 31 | Non-negative value | Negative value |
| `long` | 64 | bit 63 | Non-negative value | Negative value |

- `0x7FFF_FFFF`: bit 31 is 0, `int` value equals **2_147_483_647**.
- `0x8000_0000`: bit 31 is 1, `int` value equals **-2_147_483_648** (`Integer.MIN_VALUE`).
- `0xFFFF_FFFF`: all bits are 1, `int` value equals **-1**.
- `0x7FFF_FFFF_FFFF_FFFFL`: bit 63 is 0, `long` value equals **9_223_372_036_854_775_807**.
- `0x8000_0000_0000_0000L`: bit 63 is 1, `long` value equals **-9_223_372_036_854_775_808** (`Long.MIN_VALUE`).
- `0xFFFF_FFFF_FFFF_FFFFL`: all bits are 1, `long` value equals **-1**.

**Important:** a hex literal starting with `8` or `F` does **not automatically** make the entire literal negative. For instance, `0x8` is positive `int` 8, and `0xFF` is positive `int` 255, because the sign bit at position 31 is still 0. Only when the sign bit of the **actual type width** is set does signed interpretation become negative. For `int`, 8 hex digits cover all 32 bits; for `long`, 16 hex digits cover all 64 bits.

## 3. Reading Signed Numbers from Two's Complement Bit Patterns

Imagine the same bit pattern has an **unsigned** value `U` of width `w` bits. The **signed** value is:

```text
signed = U                  if sign bit = 0
signed = U - 2^w            if sign bit = 1
```

For `int` (`w = 32`):

1. `0x8000_0000` has unsigned value `U = 2^31 = 2_147_483_648`. Since bit 31 is 1, the signed value is `2_147_483_648 - 4_294_967_296 = -2_147_483_648`.
2. `0xFFFF_FFFF` has unsigned value `U = 2^32 - 1 = 4_294_967_295`. The signed value is `4_294_967_295 - 4_294_967_296 = -1`.
3. `0xF000_0000` has unsigned value `4_026_531_840`, while its signed value is **-268_435_456**.

For `long` (`w = 64`), `0x8000_0000_0000_0000L` is `-2^63`, and `0xFFFF_FFFF_FFFF_FFFFL` is `-1L`. If the all-ones pattern is interpreted as **unsigned 64-bit**, its value is `2^64 - 1 = 18_446_744_073_709_551_615`; that value cannot fit in a positive signed `long`.

These are **two interpretations of the same bit pattern**. Java does not need to flip bits or alter the literal to print a negative number: the interpretation follows directly from the definition of `int` and `long`.

## 4. Why Can Hex Literals Set the Sign Bit and Remain Valid?

In **decimal** literals, `2_147_483_648` without an `L` suffix normally exceeds the `int` range and causes a compile error. In **non-decimal** literals like hex, Java allows directly describing the 32-bit pattern of an `int`, including having the highest bit set to 1. Therefore, the following snippet is valid:

```java
int a = 0x8000_0000; // -2147483648
int b = 0xFFFF_FFFF; // -1
```

The two lines above are a **code fragment** that can be placed inside a method. Do not assume that `0xFFFF_FFFF` being greater than `Integer.MAX_VALUE` makes Java promote it to `long`: a literal without `L` still belongs to `int`, and is interpreted as a negative number according to its bit pattern. However, a pattern requiring more than 32 **significant** bits cannot be used as an `int` literal—for example, `0x1_0000_0000` (without `L`) is invalid; `0x1_0000_0000L` is a valid `long`.

For `long`, a hex literal with the `L` suffix can describe a 64-bit pattern, including setting bit 63:

```java
long c = 0x8000_0000_0000_0000L; // Long.MIN_VALUE
long d = 0xFFFF_FFFF_FFFF_FFFFL; // -1L
```

The letter `L` specifies **64-bit width**, and does not mean "guaranteed positive value." If bit 63 is 1, a `long` is still a negative number.

## 5. Same Hex Digits, Adding `L` Can Change the Result

An important case is comparing **`0xFFFF_FFFF`** with **`0xFFFF_FFFFL`**:

| Expression | Literal Type | Bit Pattern of Type | Signed Value |
| --- | --- | --- | ---: |
| `0xFFFF_FFFF` | `int` | 32 bits of 1 | -1 |
| `0xFFFF_FFFFL` | `long` | low 32 bits 1, **high 32 bits 0** | 4_294_967_295 |
| `0x8000_0000` | `int` | only bit 31 is 1 | -2_147_483_648 |
| `0x8000_0000L` | `long` | only bit 31 is 1; bit 63 is 0 | 2_147_483_648 |

This is precisely why you must look at **the literal type** before concluding whether hex digits represent a negative or positive number. For example, `0x8000_0000` has bit 31 set, so it is negative for `int`. However, `0x8000_0000L` is `long`: bit 31 is just a value bit, while sign bit 63 is 0, so it is positive.

## 6. Assigning Negative `int` to `long`: Sign Extension vs. Zero Extension

When converting a negative `int` to `long`, Java uses **sign extension**: preserving the arithmetic value by filling the upper bits with 1s. Therefore:

```java
int bits = 0xFFFF_FFFF;                 // -1
long signed = bits;                     // -1L
long unsigned = Integer.toUnsignedLong(bits); // 4294967295L
long masked = bits & 0xFFFF_FFFFL;      // 4294967295L
```

These declarations are a code fragment. For `signed`, the `int` pattern of 32 ones is sign-extended to `0xFFFF_FFFF_FFFF_FFFF` (64 ones), retaining the value `-1L`. For `unsigned` and `masked`, the goal is **interpreting the original 32 bits as an unsigned number**, i.e., filling the upper 32 bits with 0 to get `0x0000_0000_FFFF_FFFF` = `4_294_967_295L`.

Two important ways to convert while preserving bit-pattern information:

- `Integer.toUnsignedLong(bits)`: clearly expresses the intent to treat the 32 bits of `int` as an unsigned value from 0 to `2^32 - 1`.
- `bits & 0xFFFF_FFFFL`: performs a bitwise AND with a **`long`** mask, forcing the operation to 64 bits and keeping only the low 32 bits. Using `bits & 0xFFFF_FFFF` (both operands `int`) still yields a signed `int`; subsequent assignment to `long` will sign-extend it again.

Do not confuse **`long signed = 0xFFFF_FFFF;`** with **`long unsigned = 0xFFFF_FFFFL;`**. In the first case, the literal is `int` -1 which gets sign-extended to `long` -1; in the latter case, the literal itself is positive `long` `4_294_967_295L`.

## 7. Complete Program Runnable on Java 17+

Create the file **`HexSignBitDemo.java`** with the following content:

```java
public class HexSignBitDemo {
    public static void main(String[] args) {
        int largestPositive = 0x7FFF_FFFF;
        int intSignBit = 0x8000_0000;
        int intAllOnes = 0xFFFF_FFFF;

        long widened = intAllOnes;
        long zeroExtended = Integer.toUnsignedLong(intAllOnes);
        long longFromSameDigits = 0xFFFF_FFFFL;
        long longSignBit = 0x8000_0000_0000_0000L;
        long longAllOnes = 0xFFFF_FFFF_FFFF_FFFFL;

        System.out.println("max positive int=" + largestPositive);
        System.out.println("int sign bit=" + intSignBit);
        System.out.println("int all ones=" + intAllOnes);
        System.out.println("int hex=" + String.format("%08X", intSignBit));
        System.out.println("int binary=" + Integer.toBinaryString(intSignBit));
        System.out.println("widened=" + widened);
        System.out.println("widened hex=" + Long.toHexString(widened));
        System.out.println("zero extended=" + zeroExtended);
        System.out.println("zero extended hex=" + Long.toHexString(zeroExtended));
        System.out.println("same digits with L=" + longFromSameDigits);
        System.out.println("long sign bit=" + longSignBit);
        System.out.println("long all ones=" + longAllOnes);
        System.out.println("long all ones unsigned=" + Long.toUnsignedString(longAllOnes));
        System.out.println("unsigned int text=" + Integer.toUnsignedString(intAllOnes));
        System.out.println("unsigned mask=" + (intSignBit & 0xFFFF_FFFFL));
        System.out.println("signed right shift=" + (intSignBit >> 31));
        System.out.println("unsigned right shift=" + (intSignBit >>> 31));
        System.out.println("parse unsigned hex=" + Integer.toUnsignedLong(Integer.parseUnsignedInt("FFFFFFFF", 16)));
    }
}
```

Compile and run from the directory containing the file:

```bash
javac --release 17 -encoding UTF-8 HexSignBitDemo.java
java HexSignBitDemo
```

Stdout output:

```text
max positive int=2147483647
int sign bit=-2147483648
int all ones=-1
int hex=80000000
int binary=10000000000000000000000000000000
widened=-1
widened hex=ffffffffffffffff
zero extended=4294967295
zero extended hex=ffffffff
same digits with L=4294967295
long sign bit=-9223372036854775808
long all ones=-1
long all ones unsigned=18446744073709551615
unsigned int text=4294967295
unsigned mask=2147483648
signed right shift=-1
unsigned right shift=1
parse unsigned hex=4294967295
```

Notable lines:

- `int hex=80000000` and `int binary=1000...` show the **32-bit pattern**; `int sign bit=-2147483648` shows the **signed value** of that exact pattern.
- `widened hex=ffffffffffffffff` illustrates sign extension of `int` -1 to `long`; `zero extended hex=ffffffff` displays without leading zeros, yet its value equals the 64-bit pattern `00000000ffffffff`.
- `same digits with L=4294967295` shows that when the literal is declared as `long` from the outset, sign bit 63 is not set.
- `long all ones=-1` vs. `long all ones unsigned=18446744073709551615` are signed and unsigned displays of **the same 64 all-one bits**.
- `unsigned mask=2147483648` illustrates a `long` mask preserving the unsigned value of `0x8000_0000`.
- `signed right shift=-1` and `unsigned right shift=1` show the difference between `>>` and `>>>` when shifting bits of a negative number.

## 8. Printing Bit Patterns Instead of Only Viewing Decimal Values

`System.out.println(value)` uses the **signed** `int`/`long` value. When you need to observe the bit pattern, use:

```java
int x = 0x8000_0000;
System.out.println(Integer.toHexString(x));    // "80000000"
System.out.println(Integer.toBinaryString(x)); // "10000000000000000000000000000000"
System.out.printf("%08X%n", x);                // 80000000
```

These are statements placed inside `main`. `Integer.toHexString` and `Integer.toBinaryString` return strings representing the bit pattern in the respective base; `printf("%08X%n", x)` requests at least 8 hex characters, padding with leading zeros if needed. For `long`, you can use `Long.toHexString(value)` or `%016X` if you want all 16 hex digits displayed.

Distinguish **display representation** from **stored value**: `Integer.toHexString(-1)` is `"ffffffff"`, with no minus sign, yet `Integer.toString(-1)` is `"-1"`. Just because a hex string has no `-` sign does not mean the current `int` number is positive.

## 9. Signed Right Shift vs. Unsigned Right Shift

When the sign bit is set, the two right-shift operators have different semantics:

```java
int x = 0x8000_0000;
int arithmetic = x >> 31; // -1: fills with 1s on the left.
int logical = x >>> 31;   // 1: fills with 0s on the left.
```

`>>` is **signed (arithmetic) right shift**; `>>>` is **unsigned (logical) right shift**. Both operators work on bit patterns, while the interpretation of the result still depends on the operand's `int` or `long` type. They do not change a variable's type into an "unsigned" type; Java still stores signed `int`/`long`.

To test the sign bit of an `int`, you can write `(x & 0x8000_0000) != 0` or simply `x < 0`. For `long`, use the mask `0x8000_0000_0000_0000L`. Never use `x > 0` to detect whether any bit is set: for example, `-1` has **all bits set** yet is less than 0.

## 10. Parsing Hex from Strings and Preserving Unsigned Interpretation

When a hex value is in text, distinguish signed vs. unsigned parsing:

```java
int signedBits = Integer.parseUnsignedInt("FFFFFFFF", 16);
String unsignedText = Integer.toUnsignedString(signedBits); // "4294967295"
long unsignedValue = Integer.toUnsignedLong(signedBits);   // 4294967295L
long parsedLong = Long.parseLong("FFFFFFFF", 16);           // 4294967295L
```

The snippet above is a valid code fragment inside a method. `Integer.parseUnsignedInt` allows parsing patterns in the 32-bit unsigned range, yet **the result is stored in an `int`**; hence `signedBits` has the signed arithmetic value `-1`. Use `Integer.toUnsignedString` or `Integer.toUnsignedLong` when you want an unsigned interpretation.

`Integer.parseInt("FFFFFFFF", 16)` throws `NumberFormatException` because the corresponding positive hex value exceeds `Integer.MAX_VALUE` under signed parsing. Meanwhile, `Long.parseLong("FFFFFFFF", 16)` succeeds because that value still fits within the positive range of `long`.

For a **64-bit** unsigned pattern larger than `Long.MAX_VALUE`, `Long.parseUnsignedLong("FFFFFFFFFFFFFFFF", 16)` returns the bit pattern stored in `long` (whose signed value is `-1L`); `Long.toUnsignedString(-1L)` displays the unsigned value `18446744073709551615`. If you want a **true positive integer object** holding that value for arbitrary-magnitude arithmetic, use `new java.math.BigInteger("FFFFFFFFFFFFFFFF", 16)`.

## 11. Common Misconceptions

| Misconception | Reality | Correct Reading |
| --- | --- | --- |
| `0x8` is negative because hex starts with 8 | `int` still has bit 31 equal to 0 | `0x8 == 8` |
| `0x8000_0000` is positive 2_147_483_648 | `int` has bit 31 equal to 1 | `-2_147_483_648` |
| `0xFFFF_FFFF` cannot be `int` because it is "too big" | Hex literals can express 32 all-one bits | `int` equal to `-1` |
| Adding `L` always makes a hex pattern positive | `long` also has sign bit 63 | `0xFFFF_FFFF_FFFF_FFFFL == -1L` |
| `long x = 0xFFFF_FFFF;` becomes 4_294_967_295 | Literal has negative `int` type and is sign-extended | `x == -1L` |
| `x & 0xFFFF_FFFF` turns `int` into positive unsigned | AND on two `int`s still yields `int` | Use `Integer.toUnsignedLong(x)` or mask `0xFFFF_FFFFL` |
| `Integer.toHexString(-1)` lacks a minus sign so it is positive | Hex string shows the bit pattern | `"ffffffff"` is the pattern of `int` -1 |
| `>>` and `>>>` are always the same | With sign bit set, left bit-filling differs | `0x80000000 >> 31 == -1`, whereas `>>> 31 == 1` |

## 12. Self-Check

1. **What value does `int x = 0x7FFF_FFFF;` have?** **2_147_483_647**, because bit 31 is not set.
2. **What value does `int x = 0xFFFF_FFFF;` have?** **-1**, because it is 32 all-one bits in two's complement.
3. **Are `long x = 0xFFFF_FFFF;` and `long y = 0xFFFF_FFFFL;` equal?** **No**: `x == -1L`, `y == 4_294_967_295L`.
4. **Do `0x8000_0000` and `0x8000_0000L` have the same arithmetic value?** **No**: `-2_147_483_648` and `2_147_483_648L`, respectively.
5. **What must you do to read `int x = 0xFFFF_FFFF;` as an unsigned number?** Use `Integer.toUnsignedLong(x)` to get `4_294_967_295L`, or `Integer.toUnsignedString(x)` to get the text `"4294967295"`.
6. **Is `0x8000_0000_0000_0000L` negative or positive?** **Negative**, equal to `Long.MIN_VALUE`, because bit 63 is set.

**Conclusion:** when encountering a hex literal with the sign bit set, identify the **literal type (32 or 64 bits)**, locate the **sign bit at position 31 or 63**, and interpret the bit pattern in **two's complement**. If an unsigned value is needed, use unsigned APIs or zero extension; when assigning a negative `int` to `long`, remember that Java **sign-extends**, and does not automatically turn the bit pattern into a positive value.