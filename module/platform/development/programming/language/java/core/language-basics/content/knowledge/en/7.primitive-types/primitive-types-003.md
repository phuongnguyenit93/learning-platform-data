# Signed Integers and Two's Complement Representation in Java

> **Java core — language-basics / Primitive Types**  
> **Environment:** JDK 17 or later; no external libraries required.  
> **Goal:** Understand the sign bit and the **two's complement** rule of `byte`, `short`, `int`, and `long`; manually read a bit pattern as a positive/negative number; recognize overflow, sign extension, and the difference between signed and unsigned right shifts.


## 1. Why Can the Same Bit Pattern Represent a Negative Number?

Java's four signed integer types have fixed widths: `byte` **8 bits**, `short` **16 bits**, `int` **32 bits**, `long` **64 bits**. With `n` bits, the value range is `-2^(n-1)` to `2^(n-1)-1`. The previous lesson used these ranges to choose types and recognize conversions; here we explore **why** two's complement produces them.

At a fixed width, a highest bit of 1 indicates a negative value in **two's complement**. However, you must not read the remaining seven bits as magnitude and prepend a minus sign (*sign-magnitude*). For example, the `byte` pattern `1000_0000` has the value **-128**, whereas `0111_1111` is **127**. `char` is also 16 bits wide, but it is an **unsigned UTF-16 code unit**, not following the range of `short`.

## 2. How to Read a Two's Complement Bit Pattern

Do not merely treat the highest bit as a sign and add the magnitude of the remaining bits as in *sign-magnitude*. For `n`-bit two's complement, the rule for reading a bit pattern is:

- If the highest bit is **0**, the value equals the unsigned value of the bit pattern.
- If the highest bit is **1**, take the **unsigned** value of the bit pattern and **subtract 2^n**.

Example at **8-bit** width:

| Bit pattern | Unsigned value | Signed `byte` value |
| --- | ---: | ---: |
| `0000_0000` | 0 | 0 |
| `0000_0101` | 5 | 5 |
| `0111_1111` | 127 | 127 |
| `1000_0000` | 128 | -128 |
| `1111_1011` | 251 | -5 |
| `1111_1111` | 255 | -1 |

For example, `1111_1011` is 251 when interpreted as unsigned; as an 8-bit signed `byte`, the value is **251 - 256 = -5**.

### Forming a Negative Representation by Inverting Bits and Adding 1

To find the bit pattern of **-5** from **+5** in 8 bits:

~~~text
+5:                  0000 0101
Invert each bit:     1111 1010
Add 1:               1111 1011    => -5
~~~

Inverting bits and adding one illustrates two's complement when the bit width **is fixed**. Java has a **single representation of 0** in two's complement: `0000_0000`; there is no separate "negative zero" for integers.

Because the bit pattern space is split in half, an 8-bit type has a minimum value of **-128** while its maximum value is only **127**. There is no `+128` of type `byte`. Therefore, `-Byte.MIN_VALUE` computed at `int` width yields 128; casting the result back to `byte` yields -128.

## 3. Verification Java 17+ Program

Create the file **TwosComplementDemo.java**:

~~~java
public final class TwosComplementDemo {
    private static String bits8(int value) {
        String bits = Integer.toBinaryString(value & 0xFF);
        return "0".repeat(8 - bits.length()) + bits;
    }

    public static void main(String[] args) {
        byte five = 5;
        byte minusFive = -5;
        byte highBit = (byte) 0x80;

        System.out.println("five=" + bits8(five));
        System.out.println("minusFive=" + bits8(minusFive));
        System.out.println("minusOne=" + bits8(-1));
        System.out.println("highBit=" + bits8(highBit));
        System.out.println("byteRange=" + Byte.MIN_VALUE
                + ".." + Byte.MAX_VALUE);

        System.out.println("highBitAsByte=" + highBit);
        System.out.println("signExtendedHex="
                + Integer.toHexString(highBit));
        System.out.println("maskedHex="
                + Integer.toHexString(highBit & 0xFF));
        System.out.println("unsignedByteFF="
                + Byte.toUnsignedInt((byte) 0xFF));

        int max = Integer.MAX_VALUE;
        System.out.println("overflow=" + (max + 1));
        try {
            Math.addExact(max, 1);
        } catch (ArithmeticException exception) {
            System.out.println("addExact=overflow");
        }

        System.out.println("signedShift=" + (-8 >> 1));
        System.out.println("unsignedShift=" + (-8 >>> 1));
        System.out.println("intMinusOneHex="
                + Integer.toHexString(-1));
    }
}
~~~

Compile and run in Bash, PowerShell, or Command Prompt from the directory containing the file:

~~~bash
javac -encoding UTF-8 TwosComplementDemo.java
java TwosComplementDemo
~~~

**Expected output (exact):**

~~~text
five=00000101
minusFive=11111011
minusOne=11111111
highBit=10000000
byteRange=-128..127
highBitAsByte=-128
signExtendedHex=ffffff80
maskedHex=80
unsignedByteFF=255
overflow=-2147483648
addExact=overflow
signedShift=-4
unsignedShift=2147483644
intMinusOneHex=ffffffff
~~~

The `bits8` method takes the **low 8 bits** using `& 0xFF` and pads leading zeros. This is important because `Integer.toBinaryString(-5)` does not return an 8-bit string: the parameter is an `int`, so the representation of -5 has **32 bits**.

## 4. Sign Extension, Casting, and Bit Patterns

When converting a negative integer from a narrower type to a wider type, Java performs **sign extension**: the new leading bits are filled with the sign bit.

Example:

~~~java
byte b = (byte) 0x80; // 1000_0000, signed is -128.
int n = b;             // n is still -128.
~~~

In `byte`, `b` has the 8-bit pattern `1000_0000`. After assigning to `int`, `n` has the 32-bit pattern `0xFFFF_FF80` (hex: `ffffff80` when printed via `Integer.toHexString`).

Conversely, `b & 0xFF` produces the `int` value **128**, because the mask keeps only the low 8 bits and clears the higher bits of the result. That is how to view an 8-bit pattern from an unsigned perspective; it **does not turn the `byte` type into unsigned**.

| Java expression | Value / result | Why |
| --- | --- | --- |
| `(byte) 0xFF` | -1 | Keeps low 8 bits: `11111111` |
| `(byte) 0x80` | -128 | 8-bit sign bit is 1 |
| `((byte) 0xFF) & 0xFF` | 255 | The `&` operation occurs in `int` and applies the mask |
| `Byte.toUnsignedInt((byte) 0xFF)` | 255 | Interprets the 8 bits as unsigned |
| `Integer.toHexString(-1)` | `ffffffff` | Full 32-bit representation of `int` -1 |

**Note on literals:** `0xFF` in Java is by itself an `int` literal with the value **255**, not `byte` -1. Only after the cast `(byte) 0xFF` are the low 8 bits interpreted as -1. Similarly, the literal `0xFFFF_FFFF` is the `int` value -1 because it fills all 32 bits with sign bit 1.

## 5. Arithmetic, Overflow, and Negation

For Java integers, the results of `int`/`long` operations have a fixed width. If a limit is exceeded, ordinary integer arithmetic **wraps around modulo 2^n**; Java does not automatically throw an exception just because addition overflows.

Example:

~~~java
int max = Integer.MAX_VALUE;  // 2147483647
int wrapped = max + 1;
System.out.println(wrapped);  // -2147483648
~~~

Before addition, the bit pattern of `max` is `0x7FFF_FFFF`. Adding 1 gives `0x8000_0000`, which is read as **Integer.MIN_VALUE** in two's complement.

To **detect** overflow for `int`/`long` addition, subtraction, or multiplication, use `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`: these methods throw `ArithmeticException` when the representable range is exceeded.

### Two Notable Cases

- `-Integer.MIN_VALUE` is still **Integer.MIN_VALUE** when computed as `int`: the corresponding positive value `2147483648` is outside the `int` range. `Math.negateExact(Integer.MIN_VALUE)` throws `ArithmeticException`.
- `Math.abs(Integer.MIN_VALUE)` also produces the **negative value** Integer.MIN_VALUE. Do not assume `abs` always returns a non-negative number at the minimum boundary of an integer type.

In expressions containing `byte` or `short`, many arithmetic operators **promote to `int`** before computing. Thus `-Byte.MIN_VALUE` (in an ordinary arithmetic expression) is `int` **128**, not an overflowed `byte`; only after casting `(byte)` are 8 bits kept, becoming -128.

## 6. Bit Shifts `>>` and `>>>`

For negative numbers:

- `x >> k`: **arithmetic right shift**, filling 1 bits on the left to **preserve the sign bit**.
- `x >>> k`: **logical right shift**, filling 0 bits on the left; for negative numbers, the result can be a large positive number.

Example from `TwosComplementDemo`:

~~~java
System.out.println(-8 >> 1);  // -4
System.out.println(-8 >>> 1); // 2147483644
~~~

`-8` in `int` is `0xFFFF_FFF8`. Arithmetic shift by one bit gives `0xFFFF_FFFC` (-4); logical shift by one bit gives `0x7FFF_FFFC` (2147483644).

Both operators work on the **operand width after promotion rules**. If you shift a `byte`, the expression uses `int` first; do not assume the result of `>>>` has an 8-bit width.

## 7. Common Traps and Fixes

| Misconception or symptom | The truth |
| --- | --- |
| "The highest bit is 1, so take the remaining 7 bits and add a minus sign." | False: Java uses **two's complement**, not sign-magnitude |
| "`0xFF` is `byte` -1." | False: this literal is `int` 255; `(byte) 0xFF` is -1 |
| "A negative `byte` variable widens to a positive `int`." | False: widening preserves the signed value via **sign extension** |
| "`Integer.MAX_VALUE + 1` throws an error automatically." | False: ordinary `int` addition overflows, giving Integer.MIN_VALUE |
| "`Math.abs` is always non-negative." | False at Integer.MIN_VALUE/Long.MIN_VALUE |
| "`>>` and `>>>` produce the same result on negative numbers." | False: one fills the sign bit, the other fills 0 |
| "`char` is signed 16-bit like `short`." | False: `char` is an **unsigned** UTF-16 code unit |

## 8. Practice Exercises

**Exercise 1:** Use the 8-bit rule to find the two's complement representation of -6. Check with `Integer.toBinaryString((-6) & 0xFF)`; if you want exactly 8 characters, how many leading zeros do you need to add?

**Exercise 2:** Classify `0x7F`, `0x80`, and `0xFF` when used as `int`, then predict the result of each expression after casting `(byte)`.

**Exercise 3:** Why does `int n = (byte) 0xFF;` give `n = -1`, whereas `int n = 0xFF;` gives `n = 255`? Describe the step of narrowing to 8 bits and sign-extending back to 32 bits.

**Exercise 4:** Evaluate `Integer.MAX_VALUE + 1` and `Math.addExact(Integer.MAX_VALUE, 1)`. Which one yields a value, and which one throws an error?

**Exercise 5:** For the number `-8`, draw the four bytes of `int`, then perform `>> 1` and `>>> 1`; explain the two different outputs.

### Key Takeaways

**Java's `byte`/`short`/`int`/`long` are all signed and represented in two's complement.** With `n` bits, a pattern with highest bit 1 is read as the **unsigned value minus 2^n**; the range is **-2^(n-1) to 2^(n-1)-1**. Widening negative types preserves the sign; narrowing keeps the low bits; integer operations can overflow without throwing an error unless checked APIs are used; `>>` and `>>>` differ in how they fill bits during a right shift.
