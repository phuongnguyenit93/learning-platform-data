# BigInteger: `bitLength`, `bitCount`, `testBit`, `setBit`, and `shift` in Java

`java.math.BigInteger` represents **arbitrary-precision signed integers**, instead of being confined to 32 bits (`int`) or 64 bits (`long`). Beyond adding, subtracting, and multiplying large numbers, this class supports **inspecting and modifying bits**.

Methods to master:

| Method | Purpose |
| --- | --- |
| `bitLength()` | Number of bits in the minimal two's complement representation, **excluding the sign bit** |
| `bitCount()` | Number of bits **differing from the sign bit** in two's complement representation |
| `testBit(n)` | Checks whether the bit at index `n` equals 1 |
| `setBit(n)` | Returns a new value with bit `n` set to 1 |
| `clearBit(n)` | Returns a new value with bit `n` set to 0 |
| `flipBit(n)` | Returns a new value with bit `n` toggled |
| `shiftLeft(n)` | Left shift; for positive `n`, equivalent to multiplying by \(2^n\) |
| `shiftRight(n)` | Arithmetic right shift, **sign-extending**; for positive `n`, equivalent to floor division by \(2^n\) |

**Core point:** `BigInteger`'s bitwise operations use an **infinite sign-extension two's complement** model. Negative numbers have high bits treated as 1, not 0. Therefore `BigInteger.bitCount(-1)` equals **0** rather than 32 or 64; and `shiftRight` on negative numbers can yield a different result from `divide`.

## 1. Initializing `BigInteger` and Immutability

```java
import java.math.BigInteger;

BigInteger a = BigInteger.valueOf(45);
BigInteger fromBinary = new BigInteger("101101", 2); // 45
BigInteger huge = new BigInteger("123456789012345678901234567890");
BigInteger zero = BigInteger.ZERO;
BigInteger one = BigInteger.ONE;
```

`BigInteger` is **immutable**: operations do not mutate the existing object; they return the result object/value.

```java
BigInteger x = BigInteger.valueOf(5); // 101₂
x.setBit(1); // result 7 is discarded; x is still 5
System.out.println(x); // 5

x = x.setBit(1);
System.out.println(x); // 7
```

Writing `x.shiftLeft(10);` and ignoring the return value is usually a bug. When a variable needs updating, use `x = x.shiftLeft(10);`.

"Arbitrary precision" does not mean infinite resources: huge numbers can run out of memory or exceed implementation size limits. Bit positions still use `int` parameters.

## 2. Bit Indices: Counted Right to Left, Starting at 0

`45` has positive binary representation `101101₂`:

```text
Position: 5 4 3 2 1 0
Bit:      1 0 1 1 0 1
          ^       ^ ^
        bit 5   bit 2/0
```

Bit 0 is the lowest bit, with weight \(2^0=1\). Bit 5 has weight \(2^5=32\). The set positions in 45 are `0, 2, 3, 5`.

```java
BigInteger x = BigInteger.valueOf(45);
System.out.println(x.testBit(0)); // true
System.out.println(x.testBit(1)); // false
System.out.println(x.testBit(5)); // true
System.out.println(x.testBit(6)); // false
```

`toString(2)` prints characters with the **most significant bit first**, whereas `testBit(0)` reads the **least significant bit**; do not directly use character positions in the string as bit indices.

For positive numbers, higher bits beyond the significant length are 0. For negative numbers, higher bits are **1** under sign-extended two's complement rules.

## 3. `bitLength()`: Width Excluding the Sign Bit

Per Java 17 Javadoc, `bitLength()` returns **the number of bits in the minimal two's complement representation, excluding one sign bit**. For non-negative numbers, that is simply the number of binary digits needed to represent the magnitude, except zero returns 0.

| Value | Binary | `bitLength()` |
| ---: | --- | ---: |
| 0 | 0 | 0 |
| 1 | 1 | 1 |
| 7 | 111 | 3 |
| 8 | 1000 | 4 |
| 45 | 101101 | 6 |
| 127 | 1111111 | 7 |
| 128 | 10000000 | 8 |
| \(2^{100}\) | 1 followed by 100 zeros | 101 |

```java
System.out.println(BigInteger.ZERO.bitLength()); // 0
System.out.println(BigInteger.valueOf(45).bitLength()); // 6
System.out.println(BigInteger.ONE.shiftLeft(100).bitLength()); // 101
```

For `x > 0`, you can picture the result as \(\lfloor\log_2(x)\rfloor+1\). **Do not** convert huge numbers to `double` and take a logarithm to compute bit count, because that conversion can lose precision or become Infinity.

### How Are Negative Numbers Different?

Negative numbers follow two's complement, with infinitely many 1 bits at higher positions. For `x < 0`, `bitLength(x)` equals the binary length of `-x-1`:

| Value | `bitLength()` | Hint |
| ---: | ---: | --- |
| -1 | 0 | `-(-1)-1 = 0` |
| -2 | 1 | Complement value is 1 |
| -3 | 2 | Complement value is 2 |
| -4 | 2 | Complement value is 3 |
| -8 | 3 | Complement value is 7 |
| -45 | 6 | Complement value is 44 |
| -128 | 7 | Fits 8-bit signed representation |
| -129 | 8 | Does not fit 8-bit signed representation |

```java
System.out.println(BigInteger.valueOf(-1).bitLength()); // 0
System.out.println(BigInteger.valueOf(-8).bitLength()); // 3
System.out.println(BigInteger.valueOf(-45).bitLength()); // 6
```

**Do not use `bitLength() == 0` to check if a value equals 0:** `-1` also has `bitLength` equal to 0! To check for zero, use `x.signum() == 0` or `x.equals(BigInteger.ZERO)`.

### `bitLength` Does Not Directly Give Signed Serialization Byte Count

`BigInteger.valueOf(128).bitLength()` equals 8, yet a two's complement signed byte encoding must have a **0 sign bit** separate from bit 7 being 1, so `toByteArray()` can output an extra leading 0 byte. When transmitting binary data, specify signed/unsigned, fixed vs. variable byte count, byte order, and padding. Do not mechanically use `bitLength()/8` as the signed byte-array length.

## 4. `bitCount()`: Counting Bits Differing from the Sign Bit

For **non-negative** numbers, the sign bit is 0, so `bitCount()` equals the count of 1 bits in the binary representation:

```java
BigInteger x = BigInteger.valueOf(45); // 101101₂
System.out.println(x.bitCount()); // 4
```

For **negative** numbers, high bits are infinitely 1. The Javadoc does not ask to count infinite 1 bits, but rather to count **bits differing from the sign bit**—that is, the finite number of 0 bits in the negative number's two's complement representation.

| Value | `bitLength()` | `bitCount()` | Explanation |
| ---: | ---: | ---: | --- |
| 0 | 0 | 0 | No 1 bits |
| 45 | 6 | 4 | Four 1 bits |
| -1 | 0 | 0 | All bits are 1 |
| -2 | 1 | 1 | One 0 bit differs from sign |
| -3 | 2 | 1 | One 0 bit differs from sign |
| -4 | 2 | 2 | Two 0 bits differ from sign |
| -8 | 3 | 3 | Three 0 bits differ from sign |
| -45 | 6 | 3 | `~(-45) = 44 = 101100₂` has three 1 bits |

For `x < 0`, you can think of `x.not()` as the non-negative number `-x-1`. Then `x.bitCount()` equals the number of 1 bits in this positive complement.

```java
BigInteger neg = BigInteger.valueOf(-45);
System.out.println(neg.bitCount()); // 3
System.out.println(neg.not().bitCount()); // 3
```

### Do Not Confuse `Integer.bitCount` with `BigInteger.bitCount`

```java
System.out.println(Integer.bitCount(-1)); // 32
System.out.println(BigInteger.valueOf(-1).bitCount()); // 0
```

`Integer.bitCount(int)` counts 1 bits in a **32-bit machine word**. `BigInteger.bitCount()` counts bits **differing from the sign bit** in the arbitrary-precision integer model. These are two completely different contracts, not a Java bug.

If your problem genuinely requires counting 1 bits in the **low 64 bits**, specify the width, mask exact 64 bits, and use an appropriate popcount algorithm.

## 5. `testBit(n)`: Reading a Bit with Sign Extension

`testBit(n)` returns `true` if bit `n` is 1, `false` if it is 0.

```java
BigInteger x = new BigInteger("101101", 2);
System.out.println(x.testBit(0));   // true
System.out.println(x.testBit(1));   // false
System.out.println(x.testBit(5));   // true
System.out.println(x.testBit(100)); // false
```

With negative numbers:

```java
BigInteger minusOne = BigInteger.ONE.negate();
System.out.println(minusOne.testBit(0));   // true
System.out.println(minusOne.testBit(100)); // true
```

**High bits of a negative number do not automatically become 0.** Thus if a negative number represents a finite set of bit flags, you can easily misread flags at large positions as being set.

`testBit(-1)` throws `ArithmeticException` because **a negative bit address is invalid**. This rule also applies to `setBit(-1)`, `clearBit(-1)`, and `flipBit(-1)`.

## 6. `setBit`, `clearBit`, `flipBit`: Producing Modified Values

| Method | Rule | Bitwise equivalent |
| --- | --- | --- |
| `setBit(n)` | Sets bit `n` to 1 | OR with \(2^n\) |
| `clearBit(n)` | Clears bit `n` to 0 | AND with NOT \(2^n\) |
| `flipBit(n)` | Flips bit `n` | XOR with \(2^n\) |

Example `x = 45 = 101101₂`:

```java
BigInteger x = BigInteger.valueOf(45);

BigInteger set = x.setBit(1);     // 47 = 101111₂
BigInteger clear = x.clearBit(2); // 41 = 101001₂
BigInteger flip = x.flipBit(3);   // 37 = 100101₂

System.out.println(x);     // 45 (unchanged)
System.out.println(set);   // 47
System.out.println(clear); // 41
System.out.println(flip);  // 37
```

`setBit(n)` on an already-1 bit, or `clearBit(n)` on an already-0 bit, **does not change the value**. `flipBit(n)` toggles the state; flipping twice at the same position restores the original value.

### Constructing High Bits

```java
BigInteger twoTo100 = BigInteger.ZERO.setBit(100);
System.out.println(twoTo100.bitLength()); // 101
```

The result is \(2^{100}\), totally different from primitive `1 << 100`: because `int` shift operators use only the low 5 bits of the shift count, `1 << 100` equals `1 << 4`, giving **16**. With `BigInteger`, use `setBit(100)` or `BigInteger.ONE.shiftLeft(100)`.

### On Negative Numbers, `set`/`clear` Can Have Counterintuitive Results

```java
BigInteger negOne = BigInteger.ONE.negate();
System.out.println(negOne.setBit(100)); // -1
System.out.println(negOne.clearBit(3)); // -9
```

In `-1`, every bit is 1; setting bit 100 changes nothing. Clearing bit 3 subtracts weight 8 from `-1` in two's complement, yielding `-9`. When using `BigInteger` as a **bitset**, prefer non-negative numbers or mask to a defined width; otherwise sign extension causes confusion.

## 7. `shiftLeft(n)`: Exact Left Shift

For shift distance `n >= 0`, `shiftLeft(n)` corresponds to multiplying by \(2^n\):

```java
BigInteger x = BigInteger.valueOf(45);
System.out.println(x.shiftLeft(3)); // 360 = 45 * 8
System.out.println(BigInteger.valueOf(-13).shiftLeft(2)); // -52
```

```text
45      =    101101₂
45 << 3 = 101101000₂ = 360
```

There is no 32/64-bit wrap-around like with `int` and `long` primitives. However, huge shift results can consume large amounts of memory or exceed implementation limits. `shiftLeft(0)` keeps the value unchanged. This remains an operation on an immutable `BigInteger`: the original object is not mutated.

## 8. `shiftRight(n)`: Arithmetic Right Shift and Floor Rounding

For `n >= 0`, `shiftRight(n)` has **arithmetic right shift** semantics with sign-bit extension. By value, it equals:

\[
\operatorname{floor}\left(\frac{x}{2^n}\right).
\]

For non-negative numbers:

```java
System.out.println(BigInteger.valueOf(45).shiftRight(2)); // 11
```

However, for **negative numbers**, distinguish this from `BigInteger` division:

```java
BigInteger neg = BigInteger.valueOf(-13);

System.out.println(neg.shiftRight(2)); // -4
System.out.println(neg.divide(BigInteger.valueOf(4))); // -3
```

Because \(-13/4=-3.25\), `shiftRight(2)` rounds **toward negative infinity** to -4, whereas `divide(4)` truncates the quotient **toward zero** to -3.

| Original number | Operation | Result |
| --- | --- | ---: |
| 13 | `shiftRight(2)` | 3 |
| -13 | `shiftRight(2)` | -4 |
| -13 | `divide(4)` | -3 |
| 45 | `shiftRight(2)` | 11 |
| 45 | `shiftRight(100)` | 0 |
| -13 | `shiftRight(100)` | -1 |

```java
System.out.println(BigInteger.valueOf(45).shiftRight(100)); // 0
System.out.println(BigInteger.valueOf(-13).shiftRight(100)); // -1
```

Right-shifting a negative number very far yields -1 because the sign bit remains 1. If you need **integer division truncated toward zero** on negative numbers, do not substitute `shiftRight` for `divide` unless you have proved there is no remainder or that floor rules are desired.

## 9. Negative Shift Distances and Error Cases

The Javadoc for `shiftLeft(int)` and `shiftRight(int)` accepts **negative shift distances**, reversing the shift direction:

| API | Meaning |
| --- | --- |
| `x.shiftLeft(3)` | Shift left 3 |
| `x.shiftRight(3)` | Shift right 3 |
| `x.shiftLeft(-3)` | Shift right 3 |
| `x.shiftRight(-3)` | Shift left 3 |

```java
BigInteger x = BigInteger.valueOf(45);
System.out.println(x.shiftLeft(-2)); // 11, same value as x.shiftRight(2)
```

**Negative shift distance differs from negative bit index**:

- `x.shiftLeft(-1)` is valid, turning into a right shift.
- `x.testBit(-1)`, `x.setBit(-1)`, `x.clearBit(-1)`, and `x.flipBit(-1)` throw `ArithmeticException`.

Do not rely on `1 << 100` or primitive shift-count masking rules to reason about `BigInteger.shiftLeft(100)`. Those APIs differ in width and semantics.

For huge indices, even though the parameter type is `int`, the program must stay bounded by memory/time budgets; do not allocate billions of bits just because a user supplied a syntactically valid `n`.

## 10. `getLowestSetBit` and Fixed-Width Masks

The helper method `getLowestSetBit()` finds the position of the lowest 1 bit, or -1 when the value is zero:

```java
System.out.println(BigInteger.valueOf(40).getLowestSetBit()); // 3 (40 = 101000₂)
System.out.println(BigInteger.ZERO.getLowestSetBit());       // -1
```

For operations on the **low `n` bits**, you can construct a mask with value \(2^n-1\):

```java
int n = 4;
BigInteger mask = BigInteger.ONE.shiftLeft(n).subtract(BigInteger.ONE);
// mask = 15 = 1111₂

BigInteger lastFour = BigInteger.valueOf(-1).and(mask);
// 15: takes only the low four bits of -1
```

When `n == 0`, the mask is zero. The application must ensure `n >= 0` and not excessively large. After masking, the value is interpreted as a **non-negative bitvector**, avoiding confusion from the infinite sign bits of negative integers.

Know the difference in modeling types: `BigInteger` is used when needing signed **integer values** or huge powers of two; `java.util.BitSet` may be more appropriate when modeling a frequently changing set of non-negative bit positions.

## 11. Standalone Runnable Java 17+ Program

Create file **`BigIntegerBitDemo.java`**:

```java
import java.math.BigInteger;

public class BigIntegerBitDemo {
    public static void main(String[] args) {
        BigInteger x = BigInteger.valueOf(45);
        BigInteger negative = x.negate();

        System.out.println("positiveBinary=" + x.toString(2));
        System.out.println("positiveBitLength=" + x.bitLength());
        System.out.println("positiveBitCount=" + x.bitCount());
        System.out.println("negativeBinary=" + negative.toString(2));
        System.out.println("negativeBitLength=" + negative.bitLength());
        System.out.println("negativeBitCount=" + negative.bitCount());

        BigInteger minusOne = BigInteger.ONE.negate();
        System.out.println("minusOneBitLength=" + minusOne.bitLength());
        System.out.println("minusOneBitCount=" + minusOne.bitCount());
        System.out.println("minusEightBitLength=" +
                BigInteger.valueOf(-8).bitLength());
        System.out.println("minusEightBitCount=" +
                BigInteger.valueOf(-8).bitCount());

        System.out.println("testBit0=" + x.testBit(0));
        System.out.println("testBit1=" + x.testBit(1));
        System.out.println("testBit5=" + x.testBit(5));
        System.out.println("highNegativeBit=" + minusOne.testBit(100));

        System.out.println("setBit1=" + x.setBit(1));
        System.out.println("clearBit2=" + x.clearBit(2));
        System.out.println("flipBit3=" + x.flipBit(3));
        System.out.println("originalUnchanged=" + x);
        System.out.println("highBitLength=" +
                BigInteger.ZERO.setBit(100).bitLength());

        System.out.println("shiftLeftThree=" + x.shiftLeft(3));
        System.out.println("shiftRightTwo=" + x.shiftRight(2));
        BigInteger minusThirteen = BigInteger.valueOf(-13);
        System.out.println("negativeShiftRight=" +
                minusThirteen.shiftRight(2));
        System.out.println("negativeDivide=" +
                minusThirteen.divide(BigInteger.valueOf(4)));
        System.out.println("negativeShiftDistance=" + x.shiftLeft(-2));
        System.out.println("farPositiveShift=" + x.shiftRight(100));
        System.out.println("farNegativeShift=" +
                minusThirteen.shiftRight(100));

        System.out.println("lowestSetBit40=" +
                BigInteger.valueOf(40).getLowestSetBit());
        System.out.println("lowestSetBitZero=" +
                BigInteger.ZERO.getLowestSetBit());
        System.out.println("negativeClearBit3=" + minusOne.clearBit(3));
        System.out.println("negativeBit3AfterClear=" +
                minusOne.clearBit(3).testBit(3));

        try {
            x.testBit(-1);
            System.out.println("negativeBitIndex=missed");
        } catch (ArithmeticException ex) {
            System.out.println("negativeBitIndex=ArithmeticException");
        }

        BigInteger mask = BigInteger.ONE.shiftLeft(4)
                .subtract(BigInteger.ONE);
        System.out.println("lowFourMask=" + mask);
        System.out.println("maskedNegative=" +
                BigInteger.valueOf(-1).and(mask));
        System.out.println("primitiveShift100=" + (1 << 100));
    }
}
```

Compile and run:

```bash
javac BigIntegerBitDemo.java
java BigIntegerBitDemo
```

Output:

```text
positiveBinary=101101
positiveBitLength=6
positiveBitCount=4
negativeBinary=-101101
negativeBitLength=6
negativeBitCount=3
minusOneBitLength=0
minusOneBitCount=0
minusEightBitLength=3
minusEightBitCount=3
testBit0=true
testBit1=false
testBit5=true
highNegativeBit=true
setBit1=47
clearBit2=41
flipBit3=37
originalUnchanged=45
highBitLength=101
shiftLeftThree=360
shiftRightTwo=11
negativeShiftRight=-4
negativeDivide=-3
negativeShiftDistance=11
farPositiveShift=0
farNegativeShift=-1
lowestSetBit40=3
lowestSetBitZero=-1
negativeClearBit3=-9
negativeBit3AfterClear=false
negativeBitIndex=ArithmeticException
lowFourMask=15
maskedNegative=15
primitiveShift100=16
```

Key lines:

- `negativeBitCount=3` and `minusOneBitCount=0`: `bitCount` on negative numbers counts bits **differing from the sign**, not 1 bits in 32/64 bits.
- `highNegativeBit=true`: bit 100 of -1 equals 1 because of **sign extension**.
- `negativeShiftRight=-4` vs. `negativeDivide=-3`: right shift uses **floor**, integer division uses **truncate toward zero**.
- `primitiveShift100=16` differs from setting bit 100 in `BigInteger`.
- `negativeBitIndex=ArithmeticException`: negative bit index is rejected, even though **negative shift distances** are allowed.

## 12. Common Mistakes and Checklist

| Claim | Correct understanding |
| --- | --- |
| "`bitCount(-1)` has infinitely many 1 bits so it returns infinity." | Javadoc counts bits **differing from the sign bit**; result is 0. |
| "`BigInteger.bitCount(-1)` matches `Integer.bitCount(-1)`." | False: results are 0 and 32 respectively. |
| "`bitLength() == 0` only happens for zero." | False: -1 also returns 0. |
| "`toString(2)` of a negative number prints full two's complement." | False: it prints a minus sign and magnitude, not infinite sign extension. |
| "Bit 100 of -1 must be 0 because -1 is small." | False: negative numbers have high bits equal to 1. |
| "`setBit(n)` mutates the current object." | False: `BigInteger` is immutable; store the returned result. |
| "`1 << 100` creates bit 100." | False: `int` masks the shift count; result is 16. |
| "`shiftRight(2)` and `divide(4)` are always equal." | False when negative and there is a remainder. |
| "`shiftLeft(-2)` will throw an exception." | False: negative shift distances reverse direction; **negative bit indices** are rejected. |
| "Shifting a negative number right far enough gives 0." | False: it gives -1 due to sign extension. |
| "`BigInteger` can never run out of storage capacity." | Still bounded by memory and object size. |
| "`bitLength()/8` gives the required signed byte count." | Must account for sign, padding, and encoding. |

Checklist:

1. **Know whether inputs can be negative:** if using as bit flags, consider width masking or a non-negative convention.
2. **Count bits accurately:** `bitLength` measures length excluding sign; `bitCount` counts bits differing from sign.
3. **Validate indices:** `testBit`/`setBit`/`clearBit`/`flipBit` require non-negative `n`.
4. **Remember immutability:** use `x = x.setBit(n)` instead of discarding the result.
5. **Use `BigInteger` for high bits:** `BigInteger.ONE.shiftLeft(n)`, not `1 << n`.
6. **For negative numbers, distinguish floor and truncate:** `shiftRight` cannot replace `divide` in all cases.
7. **Bound resources:** large `n` can exhaust memory even when syntactically valid.
8. **Serialize per contract:** choose signed/unsigned, endianness, width, and leading padding explicitly.

**Key takeaway:** All bitwise methods of `BigInteger` rely on **signed two's complement integers with infinite sign-bit extension**. Most misunderstandings come from applying intuition for a fixed-size `int`/`long` machine word to arbitrary-precision integers.

Official reference: [Oracle Java 17 BigInteger Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html).