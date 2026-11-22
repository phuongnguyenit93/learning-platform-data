# Shift Distance Limits by Operand Type in Java

> **Java core — language-basics / Bitwise operators**  
> **Environment:** JDK 17+, standard library only.  
> **Goal:** Know how Java determines the actual shift distance from the **type of the left operand after numeric promotion**, explain why 32/64-bit shifts or negative shift counts do not throw errors, and avoid data loss caused by widening to `long` too late.

## 1. Bit-Shift Operators and Their Two Operands

Java has three bit-shift operators for integral types:

| Operator | Meaning | Example |
| --- | --- | --- |
| `x << n` | Left shift, fills 0 bits on the right | `1 << 3` → 8 |
| `x >> n` | **Signed** right shift, preserves the sign bit on the left | `-8 >> 1` → -4 |
| `x >>> n` | **Unsigned** right shift, fills 0 bits on the left | `-8 >>> 1` → 2147483644 |

In `x << n`, `x` is the **value being shifted**, and `n` is the **shift distance**. Both must be integral types (or unboxed wrappers); `float`, `double`, and `boolean` cannot be used as shift operands.

**Do not assume Java uses the shift distance verbatim.** Java takes only a specific number of low bits of `n`, determined by the promoted type of the **left** operand.

## 2. The Most Important Rule: `int` Uses the Low 5 Bits, `long` Uses the Low 6 Bits

| Left operand type **after unary numeric promotion** | Width | Low bits of shift distance used | Effective shift distance |
| --- | ---: | --- | --- |
| `int` | 32 bits | Low 5 bits, mask `0x1F` | `n & 0x1F`, from 0 to 31 |
| `long` | 64 bits | Low 6 bits, mask `0x3F` | `n & 0x3F`, from 0 to 63 |
| `byte`, `short`, `char` | Promoted to `int` | **Low 5 bits**, not 3 or 4 bits | `n & 0x1F` |

Memorable examples:

~~~java
int a = 1;
System.out.println(a << 31); // -2147483648
System.out.println(a << 32); // 1, because 32 & 31 == 0
System.out.println(a << 33); // 2, because 33 & 31 == 1

long b = 1L;
System.out.println(b << 32); // 4294967296
System.out.println(b << 64); // 1, because 64 & 63 == 0
System.out.println(b << 65); // 2, because 65 & 63 == 1
~~~

**Key point:** `1 << 32` equals **1**, not 0; whereas `1L << 32` equals **4294967296**. Java does not automatically throw an exception when the shift distance reaches or exceeds the bit width.

This is a rule that extracts **the low bits of the shift distance**, not a validation mechanism that checks `n <= 31` or `n <= 63` and rejects out-of-range cases.

## 3. Negative Shift Distances Are Still Masked

Java **does not report an error** just because a shift distance is negative; negative integers also have a bit pattern, and Java still masks the low bits:

~~~java
int intEffective = -1 & 0x1F;  // 31
long longEffective = -1 & 0x3F; // 63

int highInt = 1 << -1;   // same as 1 << 31: -2147483648
long highLong = 1L << -1; // same as 1L << 63: -9223372036854775808
~~~

| Expression | Effective shift distance | Result |
| --- | ---: | ---: |
| `1 << 0` | 0 | 1 |
| `1 << 31` | 31 | -2147483648 |
| `1 << 32` | 0 | 1 |
| `1 << 33` | 1 | 2 |
| `1 << -1` | 31 | -2147483648 |
| `1L << 32` | 32 | 4294967296 |
| `1L << 63` | 63 | -9223372036854775808 |
| `1L << 64` | 0 | 1 |
| `1L << -1` | 63 | -9223372036854775808 |

Do not rely on the shift operator's automatic masking as a way to "validate" input. If your domain only allows `0 <= n && n < 32` or `0 <= n && n < 64`, **check the bounds first** before shifting; otherwise, invalid inputs can silently turn into a completely different shift distance.

## 4. The **Left** Operand's Type Determines the Width, Not the Target Variable

The two operands of a shift operator undergo *unary numeric promotion* separately. The type of the **promoted left operand** is the result type; the right operand only supplies the shift distance.

~~~java
int x = 1;

long tooLate = x << 40;        // int shifted by 40 -> 40 & 31 = 8 -> 256
long correct = ((long) x) << 40; // long shifted by 40 -> 1099511627776
~~~

`tooLate` has type `long` on the **destination variable**, yet the shift itself is performed as `int` before assignment. Even `(long) (x << 40)` casts **after the shift**, so it still produces 256.

Use `1L` or cast the left side **before shifting** when you need a 64-bit range:

~~~java
long bit40 = 1L << 40;    // 1099511627776
long bit40b = (long) 1 << 40; // same result
~~~

The **right operand's** type does not widen the left result to `long`:

~~~java
int value = 1;
long distance = 33L;
int shifted = value << distance; // 2: 33 & 31 = 1
~~~

**Conclusion:** In `left << distance`, look at **the type of `left`**, not the type of `distance` or the destination variable's type.

## 5. `byte`, `short`, and `char` Are Promoted to `int`

Even though `byte` is 8 bits and `short`/`char` are 16 bits, shifts still follow the **32-bit rule** because the left operand is promoted to `int` before the operation:

~~~java
byte small = 1;
short brief = 1;
char ch = 1;

int a = small << 8;  // 256, not 0
int b = brief << 16; // 65536
int c = ch << 32;    // 1, because 32 & 31 = 0
~~~

`byte result = small << 8;` does not compile when `small` is a variable: the expression has type `int`, which cannot be implicitly assigned to `byte`. If you cast back to `byte` after shifting, the high bits can be truncated:

~~~java
byte narrowed = (byte) (small << 8); // 0
~~~

Do not think "shifting a `byte` by more than 8 bits masks modulo 8"—the shift returns `int`; narrowing to 8 bits happens only if you cast back to `byte`.

## 6. The Masking Rule Applies to `<<`, `>>`, and `>>>` Alike

Not just left shift: all three operators use the low 5/6 bits of the shift distance.

~~~java
int x = -8;
int signed = x >> 33;   // -4, because 33 & 31 = 1
int unsigned = x >>> 33; // 2147483644, also shifts by 1 bit
~~~

`>>` preserves the sign bit when shifting right; `>>>` fills 0 bits from the left. They can yield very different values when `x` is negative, but **the shift-distance masking rule is identical**.

| Expression | Result | Why |
| --- | ---: | --- |
| `-8 >> 1` | -4 | Right-shifts negative number, preserving sign |
| `-8 >> 33` | -4 | 33 becomes 1 |
| `-8 >>> 1` | 2147483644 | Fills 0 from the left |
| `-8 >>> 33` | 2147483644 | 33 becomes 1 |
| `1 >>> 32` | 1 | 32 becomes 0 |
| `1L >>> 64` | 1 | 64 becomes 0 |

This does not mean shifts "cannot lose bits." Left shifts can push high bits out of the representable width, producing negative results or data loss; Java does not automatically throw an overflow exception for shifts.

## 7. Runnable Java 17+ Program

Create the file **ShiftDistanceDemo.java**:

~~~java
public final class ShiftDistanceDemo {
    public static void main(String[] args) {
        int one = 1;
        long wide = 1L;

        System.out.println("int31=" + (one << 31));
        System.out.println("int32=" + (one << 32));
        System.out.println("int33=" + (one << 33));
        System.out.println("intMinusOne=" + (one << -1));

        System.out.println("long32=" + (wide << 32));
        System.out.println("long63=" + (wide << 63));
        System.out.println("long64=" + (wide << 64));
        System.out.println("long65=" + (wide << 65));
        System.out.println("longMinusOne=" + (wide << -1));

        long tooLate = one << 40;
        long correct = ((long) one) << 40;
        System.out.println("lateWiden=" + tooLate);
        System.out.println("earlyWiden=" + correct);

        long distance = 33L;
        int intWithLongDistance = one << distance;
        System.out.println("longDistanceOnInt=" + intWithLongDistance);

        byte small = 1;
        short brief = 1;
        char ch = 1;
        System.out.println("byteShift=" + (small << 8));
        System.out.println("shortShift=" + (brief << 16));
        System.out.println("charShift32=" + (ch << 32));
        System.out.println("narrowedByte=" + (byte) (small << 8));

        int negative = -8;
        System.out.println("signedRight33=" + (negative >> 33));
        System.out.println("unsignedRight33=" + (negative >>> 33));
        System.out.println("unsignedNoShift=" + (one >>> 32));
        System.out.println("longUnsignedNoShift=" + (wide >>> 64));

        System.out.println("maskedIntMinusOne=" + (-1 & 0x1F));
        System.out.println("maskedLongMinusOne=" + (-1 & 0x3F));
    }
}
~~~

Open a terminal in the directory containing the file and run (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 ShiftDistanceDemo.java
java ShiftDistanceDemo
~~~

**Exact expected stdout:**

~~~text
int31=-2147483648
int32=1
int33=2
intMinusOne=-2147483648
long32=4294967296
long63=-9223372036854775808
long64=1
long65=2
longMinusOne=-9223372036854775808
lateWiden=256
earlyWiden=1099511627776
longDistanceOnInt=2
byteShift=256
shortShift=65536
charShift32=1
narrowedByte=0
signedRight33=-4
unsignedRight33=2147483644
unsignedNoShift=1
longUnsignedNoShift=1
maskedIntMinusOne=31
maskedLongMinusOne=63
~~~

The lines `int32=1` and `long64=1` demonstrate that Java **masks the shift distance** rather than clamping or stopping at the 32/64 boundary. `lateWiden=256` and `earlyWiden=1099511627776` prove you must widen the left operand before shifting. `byteShift`, `shortShift`, and `charShift32` prove that `byte`/`short`/`char` follow the `int` rule.

## 8. Checklist and Exercises

| If you need to... | Remember... |
| --- | --- |
| Shift an `int` | Effective shift distance is `n & 0x1F` |
| Shift a `long` | Effective shift distance is `n & 0x3F` |
| Shift `byte`/`short`/`char` | Left operand is promoted to `int` before shifting |
| Set bit 40 | Use `1L << 40`, not `1 << 40` |
| Validate shift-distance input | Check the specific range before executing the shift |
| Right-shift negative numbers | Distinguish sign-preserving `>>` from zero-filling `>>>` |

**Exercise 1.** Predict `1 << 32`, `1 << 33`, `1L << 32`, and `1L << 64`. Explain why the results differ based on the left operand's type.

**Exercise 2.** Compare `long x = 1 << 40;` and `long y = 1L << 40;`. Why does only one of them actually shift by 40 bits in `long`?

**Exercise 3.** Given `byte b = 1;`, compute `b << 8`, state the result type, and explain `(byte)(b << 8)`.

**Exercise 4.** Given `int n = -8;`, compute `n >> 33` and `n >>> 33`. What effective shift distance do both operations use?

**Exercise 5.** If a system requires the shift count to be between 0 and 31, why should you not simply execute `value << userCount` without validating `userCount`?

### Key Takeaways

**Java uses only the low 5 bits of the shift distance for `int` and the low 6 bits for `long`.** `byte`, `short`, and `char` promote to `int` before shifting. This rule applies to all three operators (`<<`, `>>`, `>>>`), including negative or oversized shift counts; they never throw an error on their own. If you need 64 bits, make the **left operand** a `long` before the shift.
