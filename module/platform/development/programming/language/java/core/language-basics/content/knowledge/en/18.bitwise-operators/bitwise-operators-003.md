# Left Shift `<<` in Java 17+

The **left shift** operator `a << n` shifts the bits of `a` to the left by a given number of positions, filling **0 bits on the right** and **discarding bits that overflow past the type's width**.

~~~java
int value = 3;             // 0000...0011
int shifted = value << 2;  // 0000...1100 = 12
~~~

For small integers without overflow, `a << n` typically yields `a * 2^n`. However, **this is not an overflow-checked multiplication**: when shifting discards high bits or changes the sign bit, the result can become negative, zero, or differ from mathematical expectations.

**Lesson focus:** understanding *which bits are shifted*, *the result's data type*, *32/64-bit width*, *masked shift distances*, and *overflow*.

## 1. How Does a Bit Left Shift Happen?

Illustrative example on the **low 8 bits** (purely for readability):

~~~text
Before: 0000 0101   (5)
                << 1
After:  0000 1010   (10)
                << 2 from value 5
After:  0001 0100   (20)
~~~

Each bit moves `n` positions to the left, and the newly vacated low positions are filled with `0`. Bits that cross past the left edge **are lost**.

In Java, the operand actually used for the shift is a **32-bit `int` or 64-bit `long`**, after applying *unary numeric promotion*. There is no shift executed directly on an 8-bit `byte` register merely because the source variable is a `byte`.

| Expression | `int` result | Illustrative low bit pattern |
| --- | ---: | --- |
| `3 << 2` | 12 | `0000 0011 → 0000 1100` |
| `5 << 1` | 10 | `0000 0101 → 0000 1010` |
| `-3 << 1` | −6 | `1111 1101 → 1111 1010` (low 8 bits) |
| `0 << 12` | 0 | All bits are 0 |
| `1 << 0` | 1 | No shift |

For a negative number, the value is represented in **two's complement**. `-3 << 1` produces `-6` because the two's complement pattern shifted left by one bit still carries that exact value. Do not mistake `<<` for a "twice less than" comparison: it is **a bit-shift operator**.

## 2. Standalone Runnable Java 17+ Program

Create a UTF-8 file **`LeftShiftDemo.java`**:

~~~java
import java.math.BigInteger;

public class LeftShiftDemo {
    static String typeOf(int unused) {
        return "int";
    }

    static String typeOf(long unused) {
        return "long";
    }

    static String bits8(int value) {
        String s = Integer.toBinaryString(value & 0xFF);
        return "0".repeat(8 - s.length()) + s;
    }

    static String bits32(int value) {
        String s = Integer.toBinaryString(value);
        return "0".repeat(32 - s.length()) + s;
    }

    public static void main(String[] args) {
        System.out.println("== basic shifts ==");
        System.out.println("threeShiftTwo=" + (3 << 2));
        System.out.println("fiveShiftOne=" + (5 << 1));
        System.out.println("negativeShift=" + (-3 << 1));
        System.out.println("zeroShift=" + (0 << 12));
        System.out.println("oneShiftZero=" + (1 << 0));
        System.out.println("fiveBits8=" + bits8(5));
        System.out.println("tenBits8=" + bits8(5 << 1));
        System.out.println("negativeBits8=" + bits8(-3));
        System.out.println("negativeShiftBits8=" + bits8(-3 << 1));

        System.out.println("== promoted types ==");
        byte small = 3;
        short medium = 6;
        char letter = 'A';
        long large = 3L;
        System.out.println("byteResultType=" + typeOf(small << 2));
        System.out.println("byteShiftValue=" + (small << 2));
        System.out.println("shortResultType=" + typeOf(medium << 1));
        System.out.println("charShift=" + (letter << 1));
        System.out.println("longResultType=" + typeOf(large << 2));

        System.out.println("== shift distances ==");
        long distance = 33L;
        System.out.println("intByLongCount=" + (1 << distance));
        System.out.println("intBy32=" + (1 << 32));
        System.out.println("intBy33=" + (1 << 33));
        System.out.println("intByMinusOne=" + (1 << -1));
        System.out.println("longBy64=" + (1L << 64));
        System.out.println("longBy65=" + (1L << 65));

        System.out.println("== sign and overflow ==");
        System.out.println("intSignBit=" + (1 << 31));
        System.out.println("intSignBitPattern=" + bits32(1 << 31));
        System.out.println("longSignBit=" + (1L << 63));
        System.out.println("highBitShiftOne=" + (0x40000000 << 1));
        System.out.println("highBitShiftTwo=" + (0x40000000 << 2));
        System.out.println("maxIntShiftOne=" + (Integer.MAX_VALUE << 1));
        System.out.println("minIntShiftOne=" + (Integer.MIN_VALUE << 1));
        System.out.println("widenBeforeShift="
                + ((long) Integer.MAX_VALUE << 1));
        System.out.println("widenAfterShift="
                + ((long) (Integer.MAX_VALUE << 1)));

        byte narrow = 100;
        narrow <<= 1;
        System.out.println("compoundByte=" + narrow);
        System.out.println("compoundByteBits=" + bits8(narrow));

        System.out.println("== bit masks ==");
        int read = 1 << 0;
        int write = 1 << 1;
        int execute = 1 << 2;
        int permissions = read | execute;
        System.out.println("readAllowed=" + ((permissions & read) != 0));
        System.out.println("writeAllowed=" + ((permissions & write) != 0));
        System.out.println("executeAllowed=" + ((permissions & execute) != 0));
        System.out.println("groupedExpression=" + (1 << (2 + 1)));

        System.out.println("== big integers ==");
        System.out.println("bigShift="
                + BigInteger.ONE.shiftLeft(40));
    }
}
~~~

Open PowerShell (Windows) or Bash (Linux/macOS) in the directory containing the file; use **JDK 17 or later**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 LeftShiftDemo.java
java LeftShiftDemo
~~~

**Exact expected stdout** of the `java LeftShiftDemo` command alone:

~~~text
== basic shifts ==
threeShiftTwo=12
fiveShiftOne=10
negativeShift=-6
zeroShift=0
oneShiftZero=1
fiveBits8=00000101
tenBits8=00001010
negativeBits8=11111101
negativeShiftBits8=11111010
== promoted types ==
byteResultType=int
byteShiftValue=12
shortResultType=int
charShift=130
longResultType=long
== shift distances ==
intByLongCount=2
intBy32=1
intBy33=2
intByMinusOne=-2147483648
longBy64=1
longBy65=2
== sign and overflow ==
intSignBit=-2147483648
intSignBitPattern=10000000000000000000000000000000
longSignBit=-9223372036854775808
highBitShiftOne=-2147483648
highBitShiftTwo=0
maxIntShiftOne=-2
minIntShiftOne=0
widenBeforeShift=4294967294
widenAfterShift=-2
compoundByte=-56
compoundByteBits=11001000
== bit masks ==
readAllowed=true
writeAllowed=false
executeAllowed=true
groupedExpression=8
== big integers ==
bigShift=1099511627776
~~~

The two `-version` commands have no fixed expected output because they depend on the installed JDK build. The program requires no third-party libraries.

## 3. Result Type: `int` or `long`, Not Necessarily the Original Variable's Type

Java applies **unary numeric promotion** to each operand independently before shifting:

- Left operands of type `byte`, `short`, or `char` are promoted to `int`; the result of `<<` has type **`int`**.
- A left operand of type `int` yields **`int`**; `long` yields **`long`**.
- The right operand provides the **shift distance** and does not determine the result type. It may also be `long`.
- There is no direct `<<` operator for `float`, `double`, `boolean`, or `String`.

~~~java
byte b = 3;
int x = b << 2; // 12, int type.
// byte invalid = b << 2; // Error: cannot implicitly assign int to byte.

long y = 3L << 2; // 12L, long type.
int z = 1 << 33L; // 2, not long.
~~~

**Binary numeric promotion** (as used in arithmetic addition) is not applied to infer the type of a shift operator. For instance, `1 << 33L` still returns `int`, because the **left** operand has type `int`.

### `<<=` and Conversion Back to the Left-Hand Variable's Type

The compound assignment `x <<= n` performs a left shift and assigns the result back to the type of `x`, potentially **narrowing** the value:

~~~java
byte value = 100;
value <<= 1; // Valid, byte result is -56.
~~~

The shift produces `int 200`, which is then cast back to `byte` under compound assignment rules. `byte` has range -128..127, so the low bit pattern `11001000` is interpreted as **-56**.

Conversely, `value = value << 1;` does not compile without an explicit cast because the shift expression has type `int`.

## 4. Shift Distance Depends on the Left Operand's Type

Java uses only the **low 5 bits** (`n & 31`) of the shift distance when the left side is `int`, and the **low 6 bits** (`n & 63`) when the left side is `long`. Narrower operands (`byte`/`short`/`char`) are promoted to `int` before this rule applies.

~~~java
System.out.println(1 << 32);   // 1, because the effective shift distance is 0.
System.out.println(1 << 33);   // 2, because the effective shift distance is 1.
System.out.println(1L << 64);  // 1, because the effective shift distance is 0.
System.out.println(1 << -1);   // -2147483648, because -1 & 31 is 31.
~~~

Negative or out-of-width shift distances are still masked and do not automatically throw an error. If `n` comes from external input and the domain only allows bit positions 0–31 or 0–63, you must validate the range before shifting. A dedicated lesson on shift distance limits explores masking, left-hand types, and casting before versus after shifting.

## 5. Sign Bit and Overflow: `<<` Is Not Always Safe Doubling

`int` is 32 bits and `long` is 64 bits, both as **two's complement** integers. When `<<` pushes a 1 bit into the sign position or drops significant high bits, the signed value can change unexpectedly:

~~~java
System.out.println(1 << 31); // Integer.MIN_VALUE = -2147483648.
System.out.println(1L << 63); // Long.MIN_VALUE.
System.out.println(0x40000000 << 1); // -2147483648.
System.out.println(0x40000000 << 2); // 0: the high bit has been discarded.
~~~

Explaining `1 << 31`:

~~~text
int 1:
00000000000000000000000000000001

Left shift 31:
10000000000000000000000000000000
^
Highest bit = 1; interpreted as signed int it is -2147483648.
~~~

When the mathematical result fits within the type's range without losing significant bits, shifting left by `n` positions matches multiplying by `2^n`. However, for `int`, values exceeding the range are **truncated to the low 32 bits**; for `long`, to the low 64 bits. `<<` **does not throw `ArithmeticException` on overflow**.

Example:

~~~java
int x = Integer.MAX_VALUE;
System.out.println(x << 1); // -2, not 4294967294.
~~~

If you need overflow-checked multiplication, use `Math.multiplyExact` with appropriate operands/types; if you need a result larger than `int`, widen the type **before** shifting:

~~~java
int x = Integer.MAX_VALUE;
long correct = ((long) x) << 1; // 4294967294.
long tooLate = (long) (x << 1); // -2: int already overflowed before the cast.
~~~

`BigInteger.ONE.shiftLeft(40)` is an option when you need arbitrarily large integers not restricted to 32 or 64 bits (still subject to machine resources).

## 6. Application: Creating Bit Masks

`1 << k` sets the `k`-th bit (0-indexed, right to left) to 1; this is useful for status flags:

~~~java
int READ = 1 << 0;       // 001.
int WRITE = 1 << 1;      // 010.
int EXECUTE = 1 << 2;    // 100.

int flags = READ | EXECUTE; // 101.
boolean canRead = (flags & READ) != 0;   // true.
boolean canWrite = (flags & WRITE) != 0; // false.
~~~

The `|` operator combines flags, and `&` checks bits. `<<` produces the exact bit position needed.

**Limitation:** for `int`, bit 31 is the sign bit (`1 << 31` is negative); for `long`, bit 63 is the sign bit. This remains completely valid for **bit patterns** and `&`, but it breaks if you compare masks using `> 0`: a negative value with its bit set is still a valid bit mask. As a rule, test with `(flags & mask) != 0`.

If `k` comes from input, verify `0 <= k && k < 32` when using `int` or `0 <= k && k < 64` when using `long`, because Java **masks** the shift distance rather than reporting an error.

## 7. Precedence, Parentheses, and Comparison with Right Shifts

The `<<` operator has **lower precedence than `+` and `-`**, but **higher precedence than relational comparisons** such as `<` or `>=`.

~~~java
int a = 1 << 2 + 1;     // 1 << (2 + 1) = 8.
int b = (1 << 2) + 1;   // 4 + 1 = 5.
boolean check = (1 << 3) > 5; // true.
~~~

Use explicit parentheses in expressions mixing multiple operators, especially with bit masks.

| Operator | Shift direction | Newly inserted bits |
| --- | --- | --- |
| `x << n` | Left | Fills 0 on the right |
| `x >> n` | Right, sign-preserving | Fills sign bit on the left |
| `x >>> n` | Right, unsigned | Fills 0 on the left |

`<<` has no separate "unsigned left shift" variant `<<<`. Both negative and positive numbers are shifted left by the exact same bit rule. Whether the result is read as signed or unsigned comes from the **`int` or `long` type**, not from the operator choosing a "signed" or "unsigned" left shift.

## 8. Common Mistakes to Avoid

| Misconception | Fact |
| --- | --- |
| "`x << 1` is always mathematically identical to `x * 2`." | It can overflow and lose bits |
| "`byte b; b << 1` returns a `byte`." | The result has type `int` after promotion |
| "`1 << 32` gives 0 because all 32 bits are shifted out." | The result is **1** due to shift distance masking |
| "`1L << 64` gives 0." | The result is **1** because the shift distance is masked modulo 64 |
| "Negative shift distances throw an exception." | The low bits of the shift distance are still used |
| "`1 << 31` is positive `2147483648`." | Returns `Integer.MIN_VALUE` (negative) |
| "Casting to `long` after shifting fixes `int` overflow." | You must cast **before** shifting |
| "`byteValue <<= 1` and `byteValue = byteValue << 1` are equally valid." | The second form requires an explicit cast |
| "`<<` throws an exception if the sign bit changes." | No; overflow truncates to the type's width |
| "`1 << k` works arbitrarily with `k > 31` to allocate extra bits." | No; use `1L`/`BigInteger` according to the required range |

## 9. Self-Check Exercises

1. What is `3 << 2`?  
   *Answer:* **12** (`3 × 4`), without overflow.
2. What does `-3 << 1` produce?  
   *Answer:* **-6** in `int` two's complement.
3. What is the type of `byte b = 3; var x = b << 2;`?  
   *Answer:* `int`.
4. What are `1 << 32`, `1 << 33`, and `1 << -1` respectively?  
   *Answer:* **1**, **2**, **-2147483648**.
5. What are `1L << 64` and `1L << 65`?  
   *Answer:* **1L**, **2L**.
6. Why does `0x40000000 << 2` equal 0?  
   *Answer:* The high 1 bit is shifted beyond the 32-bit width.
7. Given `int x = Integer.MAX_VALUE; long y = (long) (x << 1);` — what is `y`?  
   *Answer:* **-2** because overflow occurs before the cast.
8. How do you construct bit 40 of a `long`?  
   *Answer:* `1L << 40` (not `1 << 40`).
9. Why should bit masks be tested with `(flags & mask) != 0` instead of `> 0`?  
   *Answer:* A mask can have the sign bit set, making the result negative even though the bit is present.

## Checklist

- [ ] Understand that `<<` shifts bits left, inserts 0s on the right, and discards bits overflowing on the left.
- [ ] Remember that after promotion, the result has type `int` or `long` based on the left operand.
- [ ] Know the shift distance limits: `int` uses the low 5 bits, `long` uses the low 6 bits.
- [ ] Recognize that sign-bit changes and overflow **do not throw errors automatically**.
- [ ] Widen to `long` **before** shifting if you need a range wider than `int`.
- [ ] Understand that compound assignment `<<=` can narrow the result back to the original variable's type.
- [ ] Use `1 << k` or `1L << k` as bit masks and validate `k` against the required range.
- [ ] Use parentheses to clarify expressions combining shifts, addition, and comparisons.

**Conclusion:** `<<` is a **bit-shift operator**, not unconditional exact multiplication. Always check the **left operand's type**, **effective shift distance**, **bits that could be lost**, and **sign bit** before reasoning about a shift's result.
