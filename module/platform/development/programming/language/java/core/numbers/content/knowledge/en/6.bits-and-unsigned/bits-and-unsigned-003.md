# Shift Distance Masking by `int` or `long` in Java

When you write `1 << 32` in Java, the result is **1**, not `0` or `4_294_967_296`. Yet `1L << 32` equals **4_294_967_296**. The difference comes from the rule for bitwise shift operators: **Java uses only the low 5 bits of the shift distance if the promoted left operand is `int`, and the low 6 bits if the left operand is `long`**.

This rule applies to all three operators: `<<`, `>>`, and `>>>`. It explains why shift distances like `32`, `64`, `40`, or even `-1` still compile and execute, sometimes giving very counterintuitive results.

## 1. What Do Shift Operators Work On?

Java has three bitwise shift operators on integers:

| Operator | Name | How bits are manipulated |
| --- | --- | --- |
| `a << n` | Left shift | Moves bits left, fills vacated right positions with `0`; bits shifted past the width are discarded |
| `a >> n` | Signed right shift | Moves bits right, fills vacated left positions with the original sign bit |
| `a >>> n` | Unsigned right shift | Moves bits right, fills vacated left positions with `0` |

In `a << n`, `a >> n`, or `a >>> n`, **`a` is the left operand containing the bit pattern to shift**, and **`n` is the right operand specifying how many positions to shift**. Both must have suitable integer types: `byte`, `short`, `char`, `int`, or `long` (or their corresponding unboxed wrappers). You cannot directly shift `float`, `double`, or `boolean`.

Java applies **unary numeric promotion separately to each operand**. A left operand of type `byte`, `short`, or `char` is promoted to `int`; if the left operand is already `int`, the shift result is `int`; if it is `long`, the result is `long`. The type of the right operand does not change the result type.

For negative numbers, the bits are represented in two's complement. `>>` can retain `1` bits on the left while `>>>` brings in `0` bits; however, **the shift-distance masking rule remains the same**.

## 2. Core Rule: Keep Only the Low 5 or 6 Bits of the Shift Distance

For a left operand whose promoted type is `int` (32 bits):

```text
effectiveDistance = distance & 0x1F
                  = distance & 31
```

For a `long` left operand (64 bits):

```text
effectiveDistance = distance & 0x3F
                  = distance & 63
```

Here `&` is bitwise AND. The mask `0x1F` has its low 5 bits set to `1`, and `0x3F` has its low 6 bits set to `1`. Consequently, the actual shift range for each operation is:

- **`int`: 0 through 31**, regardless of the original value of the right operand.
- **`long`: 0 through 63**, regardless of the original value of the right operand.

Examples of how shift distances are reduced:

| Written `n` | `int`: `n & 31` | `long`: `n & 63` |
| ---: | ---: | ---: |
| 0 | 0 | 0 |
| 1 | 1 | 1 |
| 31 | 31 | 31 |
| 32 | 0 | 32 |
| 33 | 1 | 33 |
| 40 | 8 | 40 |
| 63 | 31 | 63 |
| 64 | 0 | 0 |
| 65 | 1 | 1 |
| -1 | 31 | 63 |
| -32 | 0 | 32 |
| -64 | 0 | 0 |

In other words, for **integer shift distances**, the result of `&` above is equivalent to taking the non-negative remainder modulo 32 or 64. However, remember **the exact rule in Java is bitmasking**, because negative values are also interpreted naturally: `-1 & 31 == 31`; `-1 & 63 == 63`.

**There is no automatic exception for a shift distance larger than the width or for a negative shift distance.** An expression like `1 << -1` is valid and has an effective shift distance of 31, not a reverse shift by 1 bit.

## 3. Distinguishing `1 << 32` and `1L << 32`

Two expressions that look very close but have left operands of different types:

```java
int a = 1 << 32;      // int shift: 32 & 31 == 0  => 1
long b = 1L << 32;    // long shift: 32 & 63 == 32 => 4294967296
```

These are two illustrative statements you can place inside a Java method. The literal `1` defaults to `int`; the `L` suffix creates a `long` literal. Thus `1 << 32` is effectively the same as `1 << 0`, whereas `1L << 32` places the `1` bit at position 32 of a 64-bit pattern.

Further comparison:

| Expression | Effective shift distance | Result |
| --- | ---: | ---: |
| `1 << 0` | 0 (int) | 1 |
| `1 << 31` | 31 (int) | -2_147_483_648 |
| `1 << 32` | 0 (int) | 1 |
| `1 << 33` | 1 (int) | 2 |
| `1 << 40` | 8 (int) | 256 |
| `1 << 64` | 0 (int) | 1 |
| `1L << 31` | 31 (long) | 2_147_483_648 |
| `1L << 32` | 32 (long) | 4_294_967_296 |
| `1L << 40` | 40 (long) | 1_099_511_627_776 |
| `1L << 63` | 63 (long) | `Long.MIN_VALUE` |
| `1L << 64` | 0 (long) | 1 |
| `1L << 65` | 1 (long) | 2 |

`1 << 31` yields a negative value because bit 31 is the **sign bit** of `int`, not because shifting by 31 bits is invalid. Similarly, `1L << 63` sets the sign bit of `long`. The bit is placed in the right position; when printed in signed decimal, Java displays the corresponding negative number.

## 4. The Left Operand Determines the Mask, Even When the Right Operand Is `long`

Consider this code:

```java
long distance = 40L;
int a = 1 << distance;  // 256: 40 & 31 == 8
long b = 1L << distance; // 1099511627776: 40 & 63 == 40
```

These are two statements placed in a Java method. The right operand `distance` has type `long` in **both** expressions; that **does not cause** `1 << distance` to become `long`. The first result is still `int`, because the left operand comes from the `int` literal `1`.

Distinguish between:

- `long result = 1 << 40;`: the shift finishes as `int`, and the result 256 is then widened to `long`; you get **256L**.
- `long result = 1L << 40;`: the shift happens in `long`; you get **1_099_511_627_776L**.
- `long result = ((long) 1) << 40;`: casts the left operand to `long` before shifting, so it behaves like the second case.
- `long result = (long) (1 << 40);`: casts **after** shifting, so you still get **256L**.

This is the same principle—"promotion must happen before the operation"—seen in integer arithmetic. The target variable's type cannot change the mask already applied to the shift distance.

## 5. `byte`, `short`, and `char` Also Use the 5-Bit Rule

Operands of type `byte`, `short`, and `char` are promoted to **`int`** before shifting. They do not use separate masks like `& 7` for `byte` or `& 15` for `short`.

```java
byte b = 1;
short s = 1;
char c = 1;

int a = b << 32; // 1: operates in int, 32 & 31 == 0.
int d = s << 33; // 2: operates in int, 33 & 31 == 1.
int e = c << 40; // 256: operates in int, 40 & 31 == 8.
```

This is a valid snippet inside a method. The result type of each shift is `int`. To assign back to a `byte` or `short` variable, a narrowing cast is usually needed and can discard bits. Compound assignments like `b <<= n` have an implicit conversion back to the original variable's type; they still do not mask the shift distance to an 8-bit width.

For example: `byte b = -1; int result = b >>> 1;` performs `>>>` on the **promoted `int` -1**, so the result is `2_147_483_647`; it is not an unsigned shift of an 8-bit-only pattern giving 127. If the requirement is to treat a byte as an unsigned 8-bit value, first use `b & 0xFF` to interpret the byte as an `int` from 0 to 255, and then compute on that range.

## 6. How Are Negative Shift Distances Handled?

Java does not interpret `<< -1` as "shift right by one bit". It applies the normal mask to the negative number in two's complement representation:

```java
int intShift = 1 << -1;  // Equivalent to 1 << 31 => Integer.MIN_VALUE.
long longShift = 1L << -1; // Equivalent to 1L << 63 => Long.MIN_VALUE.
```

These are illustrative statements placed inside a Java method. Since `-1` has all low bits equal to `1`, `-1 & 31 == 31` and `-1 & 63 == 63`. Another example:

```java
int x = 1 << -32; // -32 & 31 == 0  => 1.
long y = 1L << -32; // -32 & 63 == 32 => 4294967296.
```

Do not use negative shift distances to express the opposite shift direction, and do not rely on implicit masking to "fix" invalid input. If the requirement allows only bit positions from 0 to 31 (or 63), explicitly validate the input value before shifting.

## 7. All Three Operators `<<`, `>>`, `>>>` Apply the Same Shift Distance Mask

The shift distance mask does not depend on shift direction or fill-bit policy. For `int`, `x << 32`, `x >> 32`, and `x >>> 32` all have an effective shift distance of **0**, because `32 & 31 == 0`. Therefore:

```java
int x = -1;
int left = x << 32;       // -1: no shift.
int arithmetic = x >> 32; // -1: no shift.
int logical = x >>> 32;   // -1: no shift.
int logicalOne = x >>> 1; // 2147483647: fills 0 on the left when shifting by 1.
```

These are illustrative statements. `>>` preserves sign during right shift; `>>>` fills with 0. When the effective shift distance is 0, both return the same bit pattern of `x` without losing the sign.

For `long`, a shift distance of `32` is **not** reduced to 0:

```java
long x = -1L;
long a = x >> 32;  // -1L: sign 1 bits are shifted in.
long b = x >>> 32; // 4294967295L: high 32 bits are filled with 0.
long c = x >>> 64; // -1L: because 64 & 63 == 0.
```

With `x = -1L`, the initial pattern has all 64 bits set to 1. Unsigned right shift by 32 bits leaves only the low 32 bits set to 1, so `x >>> 32` is a positive `long` equal to `4_294_967_295`. Meanwhile `x >>> 64` **does not shift at all** because the effective shift distance is 0. This is an important case when processing binary data or splitting a 64-bit value into parts.

## 8. Complete, Compilable, and Runnable Java 17+ Example

Create the file **`ShiftDistanceDemo.java`**:

```java
public class ShiftDistanceDemo {
    public static void main(String[] args) {
        int count = 40;
        long longCount = 40L;
        byte small = 1;

        System.out.println("intCount32=" + (1 << 32));
        System.out.println("intCount33=" + (1 << 33));
        System.out.println("intCount40=" + (1 << count));
        System.out.println("intCount64=" + (1 << 64));
        System.out.println("intCountMinus1=" + (1 << -1));
        System.out.println("longCount32=" + (1L << 32));
        System.out.println("longCount40=" + (1L << count));
        System.out.println("longCount64=" + (1L << 64));
        System.out.println("longCount65=" + (1L << 65));
        System.out.println("longCountMinus1=" + (1L << -1));
        System.out.println("intLeftLongRight=" + (1 << longCount));
        System.out.println("byteLeft=" + (small << 32));
        System.out.println("intEffective40=" + (count & 0x1F));
        System.out.println("longEffective40=" + (count & 0x3F));
        System.out.println("intSignBit=" + (1 << 31));
        System.out.println("longSignBit=" + (1L << 63));
        System.out.println("unsignedIntShift32=" + (-1 >>> 32));
        System.out.println("unsignedIntShift1=" + (-1 >>> 1));
        System.out.println("unsignedLongShift32=" + (-1L >>> 32));
        System.out.println("signedLongShift32=" + (-1L >> 32));
        System.out.println("intShift40Binary=" + Integer.toBinaryString(1 << count));
    }
}
```

In the directory containing the file, run:

```bash
javac --release 17 -encoding UTF-8 ShiftDistanceDemo.java
java ShiftDistanceDemo
```

Exact stdout:

```text
intCount32=1
intCount33=2
intCount40=256
intCount64=1
intCountMinus1=-2147483648
longCount32=4294967296
longCount40=1099511627776
longCount64=1
longCount65=2
longCountMinus1=-9223372036854775808
intLeftLongRight=256
byteLeft=1
intEffective40=8
longEffective40=40
intSignBit=-2147483648
longSignBit=-9223372036854775808
unsignedIntShift32=-1
unsignedIntShift1=2147483647
unsignedLongShift32=4294967295
signedLongShift32=-1
intShift40Binary=100000000
```

Explanation of easily confused lines:

- `intCount32=1`, `intCount64=1`: both 32 and 64 give an effective shift distance of 0 on `int`.
- `intCount40=256` vs `longCount40=1099511627776`: same number 40, but one masks with `&31` and the other masks with `&63`.
- `intCountMinus1=-2147483648` and `longCountMinus1=-9223372036854775808`: `-1` is masked to 31 or 63 and sets the exact sign bit.
- `intLeftLongRight=256`: a `long` right operand **does not** turn an `int` left operand's shift into a 64-bit shift.
- `byteLeft=1`: `byte` is promoted to `int`, so shift distance 32 is also reduced to 0.
- `unsignedIntShift32=-1`: `>>>` does not alter the bit pattern when the effective shift distance is 0; `unsignedLongShift32=4294967295` shows that `long` actually shifts 32 bits.

## 9. Consequences When Creating Bit Masks

In programs with on/off flags, you may need to build a bit pattern with only bit position `index` set:

```java
int intMask = 1 << index;     // For index 0..31.
long longMask = 1L << index;  // For index 0..63.
```

This snippet is illustrative code in a scope where `index` is defined. Do not replace `1L` with `1` in the second expression, because `long longMask = 1 << 40;` gives **256L**, setting bit 8 rather than bit 40.

When `index` comes from input or a loop, **you must explicitly check the range** to avoid silent masking. Example helper method to access a bit of a `long`:

```java
static boolean isBitSet(long flags, int index) {
    if (index < 0 || index >= Long.SIZE) {
        throw new IllegalArgumentException("bit index must be 0..63");
    }
    long mask = 1L << index;
    return (flags & mask) != 0L;
}
```

This is a **method** that must be placed inside a Java class. `Long.SIZE` equals 64. The method explicitly checks `index` from 0 to 63, then builds the mask with `long`, so even position 63 (the sign bit) is checked accurately via bitwise AND. Without the check, `index = 64` would wrap to 0 and accidentally test bit 0; `index = -1` would wrap to 63. Both can cause bugs in permission logic, feature flags, or binary data handling.

For 32-bit bitmasks, use `Integer.SIZE` (32) to check `0 <= index && index < 32`. Having the mask `1 << 31` be a negative `int` value **does not make it wrong**: bitwise AND and OR still operate properly on the bit pattern.

## 10. Large Left Shifts Do Not Report Overflow

In `<<`, bits shifted out of the left operand's width are discarded. Beyond shift-distance masking, there is also potential **information loss from left shifting**, even when the effective shift distance is within valid bounds.

```java
int highBit = 1 << 31;        // Integer.MIN_VALUE.
int lostBit = highBit << 1;   // 0: highest bit is pushed out of 32 bits.
long retained = ((long) highBit) << 1; // -4294967296L: sign-extended before shifting.
long positive = 1L << 32;     // 4294967296L.
```

The code above shows illustrative declarations. `highBit` is already a negative `int`, so sign-extending `highBit` to `long` and shifting yields a negative number; it does not recover positive `2^31`. To construct `2^32`, start from `1L << 32`.

Left shift does not throw `ArithmeticException` when bits are lost or when the sign bit changes. Do not treat `x << n` as unconditional multiplication by `2^n`: the result matches mathematical multiplication only when the needed value can still be accurately represented in the result type and is unaffected by discarded bits.

## 11. Common Situations in Code and How to Fix Them

| Written code | Common misconception | How to understand / fix |
| --- | --- | --- |
| `1 << 32` | Expecting an `int` to represent `2^32` | Effective shift 0, result 1; use `1L << 32` if you want `2^32` |
| `1L << 64` | Thinking the shift yields 0 | `64 & 63 == 0`; result 1 |
| `1 << -1` | Thinking it shifts the other way or throws | `-1 & 31 == 31`; result `Integer.MIN_VALUE` |
| `long x = 1 << 40;` | Thinking target `long` makes left operand 64-bit | `int` expression evaluates to 256 before assignment; use `1L << 40` |
| `1 << 40L` | Thinking `long` right operand makes whole expression `long` | Left operand is `int`, so mask `& 31`, result 256 |
| `byte b = 1; b << 32` | Thinking `byte` masks shift distance with `& 7` | `byte` is promoted to `int`, mask `& 31` |
| `-1 >>> 32` | Thinking it definitely becomes non-negative | Effective shift 0, still `int` -1 |
| `-1L >>> 32` | Thinking result matches the `int` expression | `long` shifts 32 bits, returning `4_294_967_295L` |
| `1L << index` with `index = 64` | Thinking invalid index will error | Effective shift 0; validate index explicitly |

## 12. Self-Check Questions

1. **What is `1 << 32`?** **1**, because the left operand is `int` and `32 & 31 == 0`.
2. **What is `1L << 32`?** **4_294_967_296**, because the left operand is `long`, and 32 is an actual valid shift distance.
3. **What is `1 << 40`?** **256**, because `40 & 31 == 8`, i.e., a left shift by 8 bits.
4. **What is `1L << 40`?** **1_099_511_627_776**, since `40 & 63 == 40`.
5. **Does `1 << 40L` return `int` or `long`?** **`int`**, because the result type depends on the left operand, not the `long` type of the shift distance.
6. **What does `1L << -1` yield?** **`Long.MIN_VALUE`**, because `-1 & 63 == 63`.
7. **Is `-1 >>> 32` different from `-1`?** **No**, because the effective shift distance is 0. However, `-1L >>> 32` yields **`4_294_967_295L`**.
8. **Does shifting a `byte` mask the shift distance to 8 bits?** **No**: before shifting, `byte` is promoted to `int`; the rule is still `& 31`.
9. **Why must `index` be validated when creating a bitmask?** Because negative or out-of-width indices are silently masked, potentially checking or setting the wrong bit without raising an error.

**Remember:** with `<<`, `>>`, and `>>>`, always **look at the left operand's type after promotion** to know the effective shift distance: **`int` uses `distance & 31`; `long` uses `distance & 63`**. A `long` right operand does not make the result wider; large or negative shift distances are masked rather than rejected. When working with bitmasks or bit-index inputs, determine the desired width and validate index bounds explicitly.