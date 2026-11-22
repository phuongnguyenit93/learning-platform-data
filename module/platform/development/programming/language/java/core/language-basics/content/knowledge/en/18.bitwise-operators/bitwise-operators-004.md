# Signed `>>` and Unsigned `>>>` Right Shifts — Java 17+

## 1. Goal and Most Important Difference

Java has two **right-shift** operators:

- **`>>` — signed right shift** (*signed/arithmetic right shift*): shifts bits to the right and fills the newly vacated left positions with the **sign bit** of the operand after promotion. Negative numbers keep their sign bit 1.
- **`>>>` — unsigned right shift** (*unsigned/logical right shift*): shifts bits to the right and **always fills with 0 bits** on the left. For negative numbers, the result can become a very large positive number.

~~~java
int number = -8;
System.out.println(number >> 2);  // -2
System.out.println(number >>> 2); // 1073741822
~~~

Both operate on **bit representations**; they are not the `>` comparison operator, nor do they convert `int` into a new unsigned primitive type.

**Key topics to grasp:** bit filling, `int`/`long` widths, shift-distance masking rules, promotion of smaller integer types, compound shift assignment, bit-extraction use cases, and differences from integer division.

## 2. Inspecting Bits via Hexadecimal

In Java, `int` uses **32 bits** and `long` uses **64 bits**, with negative numbers represented in **two's complement**. For `int n = -8`:

~~~text
n        = 11111111 11111111 11111111 11111000  (0xFFFFFFF8)
n >> 2   = 11111111 11111111 11111111 11111110  (0xFFFFFFFE = -2)
n >>> 2  = 00111111 11111111 11111111 11111110  (0x3FFFFFFE = 1073741822)
~~~

Four easily verifiable observations:

1. The leftmost bit of `-8` is **1**.
2. `-8 >> 2` fills in **two `1` bits** on the left.
3. `-8 >>> 2` fills in **two `0` bits** on the left.
4. The result of `>>>` is still **type `int`**, differing only in bit values. There is no `uint` primitive type in Java.

Printing in hex with the JDK:

~~~java
System.out.println(Integer.toHexString(-8));        // fffffff8
System.out.println(Integer.toHexString(-8 >> 2));   // fffffffe
System.out.println(Integer.toHexString(-8 >>> 2));  // 3ffffffe
~~~

`Integer.toHexString` formats the bits of an `int` as unsigned hexadecimal, which is very handy for checking bit operations.

## 3. For Non-Negative Numbers, `>>` and `>>>` Are Usually the Same

~~~java
int number = 24;

System.out.println(number >> 2);  // 6
System.out.println(number >>> 2); // 6
~~~

Because the highest bit of a non-negative `int` is 0, `>>` fills with 0 bits just like `>>>`.

| `int` value | `>> 2` | `>>> 2` | Notes |
|---:|---:|---:|---|
| `24` | `6` | `6` | Same 0-bit fill |
| `8` | `2` | `2` | Same result |
| `0` | `0` | `0` | Zero stays zero |
| `-8` | `-2` | `1073741822` | Differs due to sign bit |
| `-1` | `-1` | `1073741823` | Shifted by 2 bits |

**Scope of this rule:** "the same" here applies to **non-negative** `int`/`long` values when using the same shift distance. For negative numbers and an effective positive shift distance, the two operators fill bits differently.

## 4. `>>`: Signed Right Shift

The rule for `x >> n` fills new high bits with the sign bit of `x` after type promotion rules are applied. For negative numbers, the sign bit remains 1 after shifting; for non-negative numbers, the sign bit is 0.

~~~java
System.out.println(-8 >> 1); // -4
System.out.println(-8 >> 2); // -2
System.out.println(-1 >> 5); // -1
~~~

A common property: for `int`/`long` and an effective shift distance `n`, `x >> n` corresponds to dividing by `2^n` and **taking the floor** toward negative infinity. For odd negative numbers, this **differs from integer division `/`**, which truncates toward zero:

~~~java
System.out.println(-7 / 2);           // -3
System.out.println(-7 >> 1);          // -4
System.out.println(Math.floorDiv(-7, 2)); // -4
~~~

**Do not replace `x / 2` with `x >> 1` if you need truncation toward zero on negative numbers.** For non-negative integers, both yield the same result when the divisor is a power of 2.

## 5. `>>>`: Unsigned (Logical) Right Shift

`x >>> n` always fills with 0 bits on the left. For a negative `int`, the result becomes a non-negative `int` whenever you shift by at least one bit:

~~~java
int negative = -8;
System.out.println(negative >>> 1); // 2147483644
System.out.println(negative >>> 2); // 1073741822
~~~

For example, `-1` has all 32 bits equal to 1:

~~~java
System.out.println(-1 >>> 1); // 2147483647
~~~

`>>>` is useful when you want to treat a bit pattern as an **unsigned value** for shifting, such as extracting data bits from an `int`. It does not change a variable's type into an unsigned type, nor does it let you represent the full 32-bit unsigned range as positive `int` values **without additional handling**.

Java 17 provides several APIs for interpreting `int` as unsigned, such as `Integer.toUnsignedLong`, `Integer.compareUnsigned`, and `Integer.divideUnsigned`.

~~~java
System.out.println(Integer.toUnsignedLong(-8)); // 4294967288
System.out.println(Integer.divideUnsigned(-8, 4)); // 1073741822
~~~

When doing unsigned division by `4 = 2^2`, `Integer.divideUnsigned(-8, 4)` equals `-8 >>> 2`. When the divisor is not a power of two, do not mechanically replace division with shifts.

## 6. `int` and `long`: Different Widths

| Left operand type after promotion | Shift width | Bits used to determine shift distance |
|---|---:|---|
| `int` | 32 bits | **Low 5 bits** of the shift distance |
| `long` | 64 bits | **Low 6 bits** of the shift distance |

~~~java
int a = -8;
long b = -8L;

System.out.println(a >>> 2); // 1073741822
System.out.println(b >>> 2); // 4611686018427387902
~~~

The two expressions differ because `long` has **64 bits**, so filling the top two bits with 0 leaves 62 bits representing the result.

~~~java
System.out.println(Long.toHexString(-8L >> 2));  // fffffffffffffffe
System.out.println(Long.toHexString(-8L >>> 2)); // 3ffffffffffffffe
~~~

**Use the `L` literal suffix when you want a 64-bit shift.** Do not compute the shift on an `int` and then assign it to a `long` expecting the same result as shifting a `long` from the start.

## 7. Shift Distance Is Masked Before Computing

Both `>>` and `>>>` use only the **low 5 bits** of the shift count if the left operand is `int`, or the **low 6 bits** if it is `long`. For example:

~~~java
System.out.println(-8 >>> 32);   // -8: 32 & 31 = 0.
System.out.println(-8 >>> 34);   // 1073741822: effective shift of 2 bits.
System.out.println(-8L >>> 66);  // 4611686018427387902: 66 & 63 = 2.
System.out.println(1 >> -1);     // 0: -1 & 31 = 31.
~~~

Negative or oversized shift distances do not automatically throw exceptions. If the shift count comes from user-supplied data, validate its bounds before shifting, because masked bits can make invalid inputs produce seemingly valid results. The lesson on shift distance limits examines that rule in full; here, the key observation is that **`>>` and `>>>` still fill bits differently when the effective shift distance is the same**.

## 8. `byte`, `short`, and `char` Are Promoted to `int` Before Shifting

Shift operators apply *unary numeric promotion* to **each operand independently**; the result type of the shift expression is the type of the **left operand after promotion**. Unlike addition, the right operand **does not promote the left operand to `long`** merely because the shift count has type `long`.

~~~java
byte small = -8;
int result = small >>> 2;

System.out.println(result); // 1073741822
~~~

`small` is **sign-extended from `byte` to `int`** first, becoming `0xFFFFFFF8`; then `>>>` shifts across 32 bits. Java does not shift directly on 8 bits to produce an 8-bit unsigned number.

For `char`, because `char` stores an **unsigned UTF-16 code unit**, widening to `int` produces a value from 0 to 65535, so the `int` sign bit stays 0:

~~~java
char codeUnit = '\uFF80';
System.out.println(codeUnit >> 4);  // 4088
System.out.println(codeUnit >>> 4); // 4088
~~~

For negative `short` values, the operand likewise undergoes sign-extension to `int` before shifting.

### `>>>=`: Compound Shift Assignment with Implicit Narrowing

~~~java
byte small = -8;
small >>>= 2;
System.out.println(small); // -2
~~~

The underlying model of `small >>>= 2` is to perform the shift in `int`, then **narrow** the result back to `byte` (keeping the low 8 bits). Thus the assigned result is -2, whereas the expression `small >>> 2` assigned to an `int` gives 1073741822.

~~~java
// small = small >>> 2; // COMPILE ERROR: right-hand expression is int
small = (byte) (small >>> 2); // With explicit cast, though note the current value of small
~~~

The `op=` rule has another subtlety: **the left-hand side is evaluated only once**. Do not mechanically rewrite compound assignments involving array indices or methods with side effects into the expanded assignment form.

## 9. Bit Shifting Is Not Always Arithmetic Division

| Expression | With `x = -7` | Explanation |
|---|---:|---|
| `x / 2` | `-3` | Integer division, truncates toward 0 |
| `x >> 1` | `-4` | Signed shift, corresponds to floor |
| `x >>> 1` | `2147483644` | 32-bit shift with zero-fill |

Using `>>>` instead of integer division is **especially dangerous** if data can be negative: it interprets the bits as unsigned, yielding a drastically different result.

For **non-negative** integers, `x >> n` and `x >>> n` usually match the quotient of dividing by `2^n` when `n` is within a reasonable range. Even so, **prefer `/` when the code is meant to express division**: it is easier to read and prevents maintainers from misreading sign or shift-distance behavior.

## 10. Using `>>>` to Extract Bit Fields

Suppose an `int` packs 4 bytes:

~~~text
0x12 34 AB CD
~~~

To extract the second byte from the right (`0xAB`):

~~~java
int packed = 0x1234ABCD;
int extracted = (packed >>> 8) & 0xFF;

System.out.println(extracted); // 171 (0xAB)
~~~

Step by step:

1. `packed >>> 8` shifts the bits so `0xAB` moves into the low 8-bit position.
2. `& 0xFF` keeps the **low 8 bits** and clears all other bits.
3. The result is 171, the unsigned value of byte `0xAB`.

Similarly, extracting the **sign bit** from an `int`:

~~~java
int signed = Integer.MIN_VALUE;
int highBit = signed >>> 31;
System.out.println(highBit); // 1
~~~

If you used `signed >> 31`, the result would be **-1** because `>>` fills all left bits with 1. This is why `>>>` is generally preferred when handling bit structures and flags.

**Note:** bit extraction does not validate that the input data is valid. For protocols, verify the length, data type, and bit-field positions before shifting and masking.

## 11. Operator Precedence and Parentheses

`>>` and `>>>` belong to the **shift operators** group; they have lower precedence than `+`/`-`, but higher precedence than comparison and bitwise boolean operators. Add parentheses to make your intent explicit:

~~~java
int flags = 0x80000000;
boolean topBitSet = (flags >>> 31) == 1;
System.out.println(topBitSet); // true
~~~

With masks:

~~~java
int byteValue = (packed >>> 8) & 0xFF;
~~~

Parentheses around the shift clarify **shift first, mask second**, even though shifts have higher precedence than `&`.

Do not confuse `>>`/`>>>` in **arithmetic expressions** with the `>` characters appearing in generic syntax like `Map<String, List<Integer>>`: those are two distinct syntactic contexts.

## 12. Common Pitfalls and How to Handle Them

| Misconception / bug | Why it is wrong | Correct approach |
|---|---|---|
| `>>` and `>>>` are identical | High-bit fill differs for negative numbers | Choose based on signed vs. bitwise intent |
| `-8 >>> 2` is `-2` | `>>>` fills 0s, giving 1073741822 | Use `-8 >> 2` to preserve the sign |
| `>>>` turns `int` into an unsigned primitive | Java has no `uint` primitive type | Use unsigned APIs if needed |
| `-7 >> 1` equals `-7 / 2` | Signed shift floors; integer division truncates toward 0 | Use `/` if truncation toward 0 is needed |
| `int x; x >>> 32` yields 0 | `int` shift distance is masked to 5 bits | Validate the shift distance if needed |
| `long x` uses a 32-bit shift | `long` uses 64 bits | Check the left operand's type |
| `byte >>> 2` shifts in 8 bits | `byte` is promoted to a 32-bit `int` | Account for sign-extension |
| `byte b; b >>>= 2` returns a large unsigned byte | Compound assignment narrows back to `byte` | Inspect the intermediate `int` value |
| `x >>> 2` always means unsigned `x / 4` | Only true for 32/64-bit unsigned bits and power-of-two divisors | Use `divideUnsigned` where appropriate |
| Using `>>>` to check for negative numbers | `>>>` changes the result's sign bit when shifting | Use `x < 0` when testing sign |
| Writing `flags >>> 31 == 1` unparenthesized | Easy to misread precedence | Write `(flags >>> 31) == 1` |
| Assuming shifts are always faster than division | JVM/JIT optimizes arithmetic itself | Prioritize clear semantics; benchmark if needed |
| Using negative shift counts as a business feature | Java masks the bits, which can surprise callers | Validate `n >= 0` and appropriate bounds |

## 13. Standalone Runnable Java 17 Program

Create the exact file **`SignedUnsignedShiftDemo.java`**:

~~~java
public final class SignedUnsignedShiftDemo {
    private SignedUnsignedShiftDemo() {}

    static void showInt(String label, int value) {
        System.out.println(label + "=" + value
                + ",hex=" + Integer.toHexString(value));
    }

    public static void main(String[] args) {
        showInt("positive >>2", 8 >> 2);
        showInt("positive >>>2", 8 >>> 2);

        showInt("negative original", -8);
        showInt("negative >>2", -8 >> 2);
        showInt("negative >>>2", -8 >>> 2);
        showInt("negative >>>1", -8 >>> 1);
        showInt("all ones >>>1", -1 >>> 1);

        showInt("MIN >>1", Integer.MIN_VALUE >> 1);
        showInt("MIN >>>1", Integer.MIN_VALUE >>> 1);

        long wide = -8L;
        System.out.println("long >>2=" + (wide >> 2));
        System.out.println("long >>>2=" + (wide >>> 2));
        System.out.println("long >>2 hex="
                + Long.toHexString(wide >> 2));
        System.out.println("long >>>2 hex="
                + Long.toHexString(wide >>> 2));

        showInt("int >>>32", -8 >>> 32);
        showInt("int >>>34", -8 >>> 34);
        System.out.println("long >>>66=" + (wide >>> 66));
        System.out.println("negative shift=" + (1 >> -1));

        byte small = -8;
        showInt("byte >>>2 promoted", small >>> 2);
        small >>>= 2;
        System.out.println("byte >>>=2=" + small);

        char codeUnit = '\uFF80';
        System.out.println("char >>4=" + (codeUnit >> 4));
        System.out.println("char >>>4=" + (codeUnit >>> 4));

        System.out.println("negative division=" + (-7 / 2));
        System.out.println("negative >>1=" + (-7 >> 1));
        System.out.println("negative >>>1=" + (-7 >>> 1));
        System.out.println("floorDiv=" + Math.floorDiv(-7, 2));

        System.out.println("unsigned long view="
                + Integer.toUnsignedLong(-8));
        System.out.println("unsigned /4="
                + Integer.divideUnsigned(-8, 4));

        int packed = 0x1234ABCD;
        int extracted = (packed >>> 8) & 0xFF;
        System.out.println("extracted byte=" + extracted);

        int sign = Integer.MIN_VALUE;
        System.out.println("top bit unsigned=" + (sign >>> 31));
        System.out.println("top bit signed=" + (sign >> 31));
        System.out.println("top bit set=" + ((sign >>> 31) == 1));
    }
}
~~~

**Requirements:** JDK 17 or later, terminal opened in the directory containing the file; no Maven, Gradle, or external libraries needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 SignedUnsignedShiftDemo.java
java -cp . SignedUnsignedShiftDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\SignedUnsignedShiftDemo.java
java -cp . SignedUnsignedShiftDemo
~~~

### Exact expected stdout

~~~text
positive >>2=2,hex=2
positive >>>2=2,hex=2
negative original=-8,hex=fffffff8
negative >>2=-2,hex=fffffffe
negative >>>2=1073741822,hex=3ffffffe
negative >>>1=2147483644,hex=7ffffffc
all ones >>>1=2147483647,hex=7fffffff
MIN >>1=-1073741824,hex=c0000000
MIN >>>1=1073741824,hex=40000000
long >>2=-2
long >>>2=4611686018427387902
long >>2 hex=fffffffffffffffe
long >>>2 hex=3ffffffffffffffe
int >>>32=-8,hex=fffffff8
int >>>34=1073741822,hex=3ffffffe
long >>>66=4611686018427387902
negative shift=0
byte >>>2 promoted=1073741822,hex=3ffffffe
byte >>>=2=-2
char >>4=4088
char >>>4=4088
negative division=-3
negative >>1=-4
negative >>>1=2147483644
floorDiv=-4
unsigned long view=4294967288
unsigned /4=1073741822
extracted byte=171
top bit unsigned=1
top bit signed=-1
top bit set=true
~~~

### How to Verify the Output

1. **Non-negative values:** `8 >> 2` and `8 >>> 2` both equal 2.
2. **Negative values:** `-8 >> 2` keeps its negative sign (hex `fffffffe`), whereas `-8 >>> 2` fills with 0 (hex `3ffffffe`).
3. **High sign bit:** `MIN_VALUE >> 1` fills with bit 1; `MIN_VALUE >>> 1` fills with 0.
4. **Width:** shifting a `long` yields a different result from `int`; `Long.toHexString` shows 16 hex digits when full width is set.
5. **Shift distance masking:** `int >>> 32` shifts by 0; `int >>> 34` shifts by 2; `long >>> 66` also shifts by 2.
6. **Promotion:** `byte >>> 2` is evaluated as `int`; `byte >>>= 2` converts the result back to `byte`.
7. **Division:** `-7 / 2` is -3, differing from `-7 >> 1` which is -4.
8. **Unsigned API:** `Integer.toUnsignedLong(-8)` gives 4294967288, and unsigned division by 4 gives 1073741822.
9. **Bit extraction:** shifting `packed` then `& 0xFF` yields `0xAB = 171`; the highest bit of `MIN_VALUE` is isolated as 1 using `>>>`.

## 14. Exercises with Answers

### Exercise A — Negative Value with Both Shifts

~~~java
int x = -16;
System.out.println(x >> 2);
System.out.println(x >>> 2);
~~~

**Answer:**

~~~text
-4
1073741820
~~~

Because `-16` in hex is `0xfffffff0`; a two-bit logical right shift produces `0x3ffffffc`.

### Exercise B — Extracting a Byte

Given `int packed = 0x12AB34CD;`, extract the byte at bit positions 16–23 (`0xAB`) as a number from 0 to 255.

**Answer:**

~~~java
int extracted = (packed >>> 16) & 0xFF;
System.out.println(extracted); // 171
~~~

### Exercise C — Effect of Masking

~~~java
System.out.println(-1 >>> 32);
System.out.println(-1 >>> 33);
~~~

**Answer:**

~~~text
-1
2147483647
~~~

On `int`, a shift count of 32 becomes 0; 33 becomes 1.

### Exercise D — Promoted Byte

~~~java
byte b = -1;
int result = b >>> 1;
System.out.println(result);
~~~

**Answer:** `2147483647`. Byte `-1` is sign-extended to `int` `0xffffffff`, then `>>> 1` turns it into `0x7fffffff`.

### Exercise E — Shift vs. Integer Division

~~~java
int x = -9;
System.out.println(x / 2);
System.out.println(x >> 1);
~~~

**Answer:**

~~~text
-4
-5
~~~

Integer division truncates toward 0, whereas signed right shift by 1 bit corresponds to floor.

### Exercise F — Choosing the Right Operator

To extract the highest sign bit of `int flags` as **0 or 1**, which expression should you use?

**Answer:** `(flags >>> 31) & 1` or simply `flags >>> 31`. On `int`, a 31-bit logical right shift leaves only the original highest bit at the lowest position; the result is 0 or 1. `flags >> 31`, by contrast, would return 0 or -1.

## 15. Checklist and Conclusion

- [ ] Understand that `>>` fills with the sign bit, while `>>>` fills with zero on the left.
- [ ] Know that both operators give the same result for non-negative integers with the same shift distance.
- [ ] Can explain `-8 >> 2 = -2` and `-8 >>> 2 = 1073741822` on your own.
- [ ] Remember that `int` is 32 bits and `long` is 64 bits.
- [ ] Know that `int` masks 5 bits of the shift distance and `long` masks 6 bits.
- [ ] Know that `byte`/`short`/`char` are promoted to `int` before shifting.
- [ ] Distinguish an `int`-typed `byte >>> 2` expression from `byte >>>= 2` which narrows back to `byte`.
- [ ] Do not confuse `>>` with integer division truncating toward 0 on negative numbers.
- [ ] Know that `>>>` is useful for extracting bits and treating bit patterns as unsigned.
- [ ] Understand that `>>>` does not create a new unsigned primitive type.
- [ ] Use parentheses when combining shifts and masks; account for sign-extension before type conversion.
- [ ] Validate shift counts if business logic forbids negative or out-of-width values.
- [ ] Run `SignedUnsignedShiftDemo.java` with Java 17+ and verify against the exact stdout.

**Conclusion:** `>>` preserves the sign by filling with the sign bit; `>>>` shifts logically by filling with 0 bits. The most noticeable difference is on **negative numbers**, alongside **32/64-bit widths, shift-distance masking, numeric promotion, and compound assignment**. Use `>>>` intentionally when working with bit patterns or unsigned bit views, and use division operators when your goal is truly arithmetic—especially with negative numbers.
