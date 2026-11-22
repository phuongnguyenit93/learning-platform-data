# Integer Overflow, Type Conversions, and Bytecode Operation Semantics

In Java, an `int` addition can produce a negative number even when both operands are positive; casting an `int` to `byte` can change both the sign and the value; and casting to `long` **after** the operation has already overflowed does not recover the lost information. This is **specified semantics** defined by the Java Language Specification (JLS) and the Java Virtual Machine Specification (JVMS), not a random bug of the CPU or HotSpot.

Goal of this lesson: understand exactly how JVM integers are represented and processed; trace **the type of each operand → operation → result → type conversion**; read the corresponding bytecode instructions; and choose ways to detect overflow when data must not be lost.

## 1. The Integer Picture in Java and in the JVM

### Data Types, Widths, and Value Ranges

| Java Type | Bits | Value Range | Characteristics |
| --- | ---: | --- | --- |
| `byte` | 8 | -128 to 127 | Signed integer |
| `short` | 16 | -32,768 to 32,767 | Signed integer |
| `char` | 16 | 0 to 65,535 | *Unsigned* integer value, usually representing a UTF-16 code unit |
| `int` | 32 | -2,147,483,648 to 2,147,483,647 | Common integer type in JVM operations |
| `long` | 64 | -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 | 64-bit signed integer type |

`boolean` is a distinct type, not an integer, and cannot be added or cast numerically with a numeric cast. `float`/`double` are floating-point types with IEEE 754 semantics and do not use the same modulo-style overflow as `int`/`long`.

Signed integer values are interpreted in **two's complement**. For example, the 32-bit pattern `0xFFFF_FFFF` represents `-1` when viewed as a signed `int`; the same bit pattern can be read by unsigned APIs as `4,294,967,295`. Changing the interpretation **does not change** the stored bits.

In the JVM **operand stack**, many operations on `byte`, `short`, `char`, and `boolean` use the `int` computational type; the smaller declared types still exist in field descriptors, arrays, method signatures, and narrowing/conversion steps to the target type. The JVM does not have a complete separate family of addition instructions `badd`, `sadd`, `cadd` for the three smaller types. `long` has its own instruction family `ladd`, `lsub`, `lmul`, etc.

For example, correct reasoning must ask: "At the **time the addition is performed**, are the operands `int` or `long`?", rather than only looking at the type of the variable receiving the result.

## 2. `int` and `long` Overflow Is a Deterministic Rule

For integer operators such as `+`, `-`, `*`, and unary negation `-x`, Java keeps the **low 32 bits** of the mathematical result if the operation has type `int`, or the **low 64 bits** if it has type `long`. These bits are then interpreted using two's complement.

You can think of it as:

- Compute the full-width mathematical sum/product.
- Take the result modulo `2^32` for `int` or `2^64` for `long`.
- Interpret the resulting bit pattern as a **signed** number of the corresponding type.

Example:

```java
int largest = Integer.MAX_VALUE;  // 2_147_483_647
int wrapped = largest + 1;        // -2_147_483_648
long wide = Long.MAX_VALUE + 1;    // -9_223_372_036_854_775_808
```

The three lines above are an **illustrative snippet**, not a standalone file. The operation `largest + 1` has type `int`; the mathematical result `2_147_483_648` exceeds `int`, the low 32-bit pattern is `0x8000_0000`, which is interpreted as `Integer.MIN_VALUE`.

| Integer Operation | Overflow Behavior | Exception due to *overflow*? |
| --- | --- | --- |
| `iadd`/`ladd`; `isub`/`lsub`; `imul`/`lmul` | Truncates to the low 32/64 bits | No |
| `ineg`/`lneg`, e.g., `-Integer.MIN_VALUE` | Remains `Integer.MIN_VALUE` / `Long.MIN_VALUE` | No |
| `iinc` on an `int` local variable | Adds a constant and keeps the low 32 bits | No |
| Integer division `idiv`/`ldiv` with divisor `-1` and minimum dividend | Result still equals `MIN_VALUE` | No |
| Integer division or remainder with divisor `0` | No valid integer result | **`ArithmeticException`** |
| Narrowing conversion `i2b`, `i2s`, `i2c`, `l2i` | Discards high bits | No, even if value is lost |
| `Math.addExact`, `Math.multiplyExact`, etc. | Checks overflow per API contract | **`ArithmeticException`** on overflow |

There is no default mode such as "checked arithmetic" that forces every `iadd` instruction to throw an error on overflow. The compiler or JVM may optimize how execution happens, but the **observable result** of an integer expression must still follow Java semantics.

### Common Pitfall: Overflow Is Not Floating-Point Arithmetic

`double x = Double.MAX_VALUE * 2;` can become `Infinity` instead of wrapping around to a negative number. `double a = 1.0 / 0.0;` returns `Infinity`, whereas `int a = 1 / 0;` may be caught at compile time in a constant expression or cause an `ArithmeticException` when executed at runtime; to observe runtime behavior, use a variable for the divisor. Do not apply `iadd` rules to `fadd`, `dadd`, or `ddiv`.

## 3. When Converting to `long`: Conversion Timing Determines Right vs. Wrong

Consider multiplying two values:

```java
int amount = 1_500_000_000;
long wrong = amount * 2;
long correct = (long) amount * 2;
```

- `amount * 2` is computed as `int`, overflowing to **`-1_294_967_296`**; assigning it to `long` only sign-extends the *already wrong* negative value.
- `(long) amount * 2` converts the first operand to `long` **before multiplying**, so the multiplication is `long` and yields **`3_000_000_000`**.

The same issue occurs with parentheses:

```java
int max = Integer.MAX_VALUE;
long tooLate = (long) (max + 1); // -2147483648
long inTime = (long) max + 1;    //  2147483648
```

**Rule:** the type of the **operation being performed** determines the width; the type of the variable on the left-hand side of `=` cannot fix an operation that has already overflowed.

Converting early to `long` helps reduce the risk, but `long` also has a 64-bit limit and will still overflow if its value range is exceeded. For large monetary amounts, safety counters, data sizes, or multi-step multiplications, you need to clearly determine the input range and consider using `Math.*Exact` or `BigInteger`.

### Promotion for Small Types

For common binary arithmetic operations (`+`, `-`, `*`, `/`, `%`), `byte`, `short`, and `char` undergo **binary numeric promotion** to at least `int` before computation. Example:

```java
byte a = 100;
byte b = 20;
// byte c = a + b; // Compile ERROR: a+b has type int
int sum = a + b;   // valid, sum = 120
byte c = (byte) (a + b); // syntactically valid, but may lose data
```

Notable exceptions in assignment contexts:

- `byte b = 127;` compiles: an `int` constant that fits in `byte` is allowed to be narrowed by the constant assignment rule.
- `byte b = 128;` compile error: constant is outside the `byte` range.
- `byte b = 127; b++;` is valid; the increment includes a conversion step back to `byte`, and the result becomes `-128`.
- `byte b = 127; b += 1;` is also valid; compound assignment includes an implicit cast to the left-hand side type. In contrast, `b = b + 1;` requires an explicit cast because the result of the addition is `int`.

The fact that a constant is accepted by the compiler does not eliminate runtime overflow rules. Similarly, a constant integer expression may be precomputed by the compiler, yet it must still preserve the overflow rules of the integer type.

## 4. Integer Type Conversions: Keep Low Bits, Then Determine Signed or Unsigned

**Widening** from a narrower integer type to a wider integer type:

- `byte`/`short`/`int` are signed; widening to a type with more bits uses **sign extension**.
- `char` is unsigned; widening to `int`/`long` uses **zero extension**.
- Widening from an integer to a wider integer preserves **value**; conversely, widening `int → float` or `long → double` can lose **precision**, because floating-point types have a finite number of significand bits.

**Narrowing** from a wider integer type to a narrower type:

- `int → byte` keeps the low 8 bits; `int → short`/`char` keeps the low 16 bits.
- `long → int` keeps the low 32 bits; converting `long` to `byte`/`short`/`char` may correspond to two narrowing steps in bytecode.
- The target types `byte` and `short` read the sign bit using two's complement; `char` treats the resulting 16 bits as an **unsigned** number.
- Integer narrowing **does not automatically check** whether the value fits in the target. `(byte) 130` is `-126`, without throwing an exception.

Bit-level examples:

| Expression | Retained Bits | Value |
| --- | --- | ---: |
| `(byte) 130` | `0x82` (8 bits) | -126 |
| `(byte) 255` | `0xFF` (8 bits) | -1 |
| `(short) 65535` | `0xFFFF` (16 bits) | -1 |
| `(char) (-1)` | `0xFFFF` (16 bits) | 65535 |
| `(int) 0x1_0000_0001L` | `0x0000_0001` (32 bits) | 1 |
| `(long) (byte) 255` | `0xFFFF_FFFF_FFFF_FFFF` | -1 |

The last one demonstrates **narrowing first and then widening**: casting to `byte` turns `255` into `-1`, and widening to `long` only preserves `-1`, without recovering `255`. If you receive a raw protocol byte that needs to be interpreted in the 0–255 range, you typically use `value & 0xFF` when `value` is a `byte` promoted to `int`, or `Byte.toUnsignedInt(value)`.

### Java 17 Example: Type Conversions and Bit Loss

Create **`NarrowingConversions.java`**:

```java
public class NarrowingConversions {
    public static void main(String[] args) {
        System.out.println("byte130=" + (byte) 130);
        System.out.println("byte255=" + (byte) 255);
        System.out.println("short65535=" + (short) 65535);
        System.out.println("charMinus1=" + (int) (char) -1);
        System.out.println("longToInt=" + (int) 0x1_0000_0001L);

        byte counter = 127;
        counter++;
        System.out.println("counter=" + counter);

        byte raw = (byte) 255;
        System.out.println("unsignedByte=" + Byte.toUnsignedInt(raw));
    }
}
```

Compile and run:

```bash
javac --release 17 NarrowingConversions.java
java NarrowingConversions
```

**Exact stdout**:

```text
byte130=-126
byte255=-1
short65535=-1
charMinus1=65535
longToInt=1
counter=-128
unsignedByte=255
```

Key point: `byte`, `short`, and `char` have the same potential to lose high bits when narrowing, but they interpret the sign bit **differently**. `Byte.toUnsignedInt` only changes the representation of the value to a positive `int`; it does not alter the original byte.

## 5. Converting `float`/`double` to Integers Is Not Simply "Keep the Low Bits"

Java has a two-stage rule for narrowing from floating-point to integer types:

1. Convert to `int` or `long` by **rounding toward 0** if it is a finite number within the representable range. `NaN` yields **0**; too large / +∞ yields `MAX_VALUE`; too small / −∞ yields the corresponding `MIN_VALUE`.
2. If the target type is `byte`, `short`, or `char`, continue **narrowing** from `int` using the keep-low-bits rule.

This is different from "casting `double` directly to `byte` by just taking 8 bits of the fractional part". For example, `(byte) 130.5`: first `(int) 130.5 = 130`, then `(byte) 130 = -126`.

Create the file **`FloatingToInteger.java`**:

```java
public class FloatingToInteger {
    public static void main(String[] args) {
        System.out.println("positive=" + (int) 3.9);
        System.out.println("negative=" + (int) -3.9);
        System.out.println("NaN=" + (int) Double.NaN);
        System.out.println("plusInfinity=" + (int) Double.POSITIVE_INFINITY);
        System.out.println("minusInfinity=" + (int) Double.NEGATIVE_INFINITY);
        System.out.println("doubleToByte=" + (byte) 130.5);
    }
}
```

```bash
javac --release 17 FloatingToInteger.java
java FloatingToInteger
```

**Stdout**:

```text
positive=3
negative=-3
NaN=0
plusInfinity=2147483647
minusInfinity=-2147483648
doubleToByte=-126
```

Understand carefully: casting `double` to `int` **does not throw `ArithmeticException`** for out-of-range values; that is why it is very dangerous if the input data must be exact. If the application needs to detect NaN/infinite values, out-of-range values, or fractional parts, check explicitly *before casting*.

In the reverse direction, `int → float` can also round and lose precision, even though it is called a **widening primitive conversion** in the type system. For example, `(float) 16_777_217` becomes `16_777_216.0` due to the number of significand bits in `float`; "widening" does not always mean "every bit of the value is preserved" when converting from integer to floating-point.

## 6. Integer Division, Sign of the Remainder, and Edge Cases

Java divides two integers with the quotient **rounded toward 0** (truncation toward zero), not rounded down toward negative infinity:

| Expression | Value |
| --- | ---: |
| `7 / 3` | 2 |
| `-7 / 3` | -2 |
| `7 / -3` | -2 |
| `-7 % 3` | -1 |
| `7 % -3` | 1 |
| `Integer.MIN_VALUE / -1` | -2,147,483,648 |
| `Integer.MIN_VALUE % -1` | 0 |

A non-zero remainder has the same sign as the **dividend**. Therefore, `-7 % 3` is `-1`, not `2`. If you need floor-directed division (for example, date/time calculations or bucketing with negative numbers), see `Math.floorDiv` and `Math.floorMod`; do not alter the rules of `/` and `%` using mathematical reasoning that omits the rounding behavior.

**Special case**: `Integer.MIN_VALUE / -1` has the mathematical quotient `2147483648`, which cannot be represented by `int`. According to the JLS/JVMS, the result is **`Integer.MIN_VALUE`**, without throwing an overflow exception. The same applies to `Long.MIN_VALUE / -1L`.

Integer division by **0** raises `ArithmeticException`; valid runtime example:

```java
int divisor = 0;
try {
    System.out.println(42 / divisor);
} catch (ArithmeticException ex) {
    System.out.println("division by zero");
}
```

This is an **illustrative snippet inside a method**, not a standalone program. The output of `catch` is `division by zero`. For `double`, `42.0 / 0.0` yields `Infinity`, unlike the integer division rule. The corresponding bytecode instructions are `idiv`/`ldiv` versus `ddiv`/`fdiv`.

## 7. Bit Shifts Are Not Infinite-Width Multiplication/Division

Shift operators work on fixed-size bit patterns:

- `<<` left shift, shifting `0`s into the low bits. High bits are discarded, so it can change the sign or lose data.
- `>>` **signed** right shift: shifts copies of the sign bit in from the left (sign extension).
- `>>>` **unsigned** right shift: shifts `0` bits in from the left (zero fill); it does not change the Java type to unsigned.
- With a left operand of type `int`, the shift distance uses only the **low 5 bits** of the distance: effectively `distance & 0x1F` (modulo 32).
- With a left operand of type `long`, only the **low 6 bits** are used: `distance & 0x3F` (modulo 64).
- `byte`/`short`/`char` on the left-hand side undergo **unary numeric promotion** to `int` before shifting; the type of the right-hand side does not make the result of `int << 1L` become `long`.

Example:

```java
System.out.println(1 << 32);   // 1: 32 & 31 = 0
System.out.println(1L << 64);  // 1: 64 & 63 = 0
System.out.println(-1 >> 1);   // -1
System.out.println(-1 >>> 1);  // 2147483647
```

You can see the corresponding bytecode instructions: `ishl`/`lshl`, `ishr`/`lshr`, `iushr`/`lushr`. When decoding a binary field, checksum, or ARGB color, always specify the **type width** and explicit masking operations; a shift greater than 31 for `int` does not mean all bits disappear.

### Unsigned Is an Interpretation, Not a New Java Type

`int` remains a 32-bit signed type; Java provides APIs such as `Integer.compareUnsigned`, `Integer.divideUnsigned`, `Integer.toUnsignedLong`, and `Integer.toUnsignedString`. For example, `Integer.toUnsignedLong(-1)` is `4294967295L`. Shifting with `>>>` also only operates on the existing 32/64 bits; it does not give an `int` variable extra storage range.

## 8. From Java Source to JVM Instructions: Seeing the Exact Sequence of Operations and Casts

The JVM typically executes logic using an **operand stack**: load values, place operands onto the stack, an opcode pops operands and pushes the result, and then it may cast or return. For `int`, a value on the stack has type `int`; for `long`, it uses type `long`.

Table of some core opcodes in JVMS 17:

| Opcode | Meaning | Notes |
| --- | --- | --- |
| `iadd`, `isub`, `imul`; `ladd`, `lsub`, `lmul` | Add, subtract, multiply `int`/`long` | 32/64-bit wrap; no exception on overflow |
| `ineg`/`lneg` | Negate integer | `-MIN_VALUE == MIN_VALUE` |
| `iinc` | Increment `int` local variable by a signed constant | Wraps; this opcode works on a local variable, not arbitrary variables/objects |
| `idiv`/`ldiv`; `irem`/`lrem` | Divide, remainder `int`/`long` | Divisor `0` throws `ArithmeticException` |
| `i2l` | `int → long` | Sign extension; the widening itself is exact |
| `l2i` | `long → int` | Keeps low 32 bits |
| `i2b`, `i2s` | `int → byte/short` | Keeps 8/16 bits then **sign-extends back to int on the stack** |
| `i2c` | `int → char` | Keeps 16 bits then **zero-extends back to int on the stack** |
| `f2i`, `d2i`, `f2l`, `d2l` | Floating-point → integral | Rounds toward 0; NaN to 0; out-of-range values are clamped |
| `ishl`, `ishr`, `iushr` | Shift `int` | Uses only low 5 bits of shift distance |
| `lshl`, `lshr`, `lushr` | Shift `long` | Uses only low 6 bits of shift distance |

It is especially important to distinguish the **bytecode operand stack value type** from the **Java type of an expression/variable**. For example, `i2b` does not create a separate "byte" operand stack type: according to the instruction specification, it narrows to 8 bits and then sign-extends to **int** on the stack; the generated code still guarantees that the value fits within the `byte` range.

### Standalone Program That Can Be Disassembled with `javap`

Create the file **`IntegerBytecode.java`**:

```java
public class IntegerBytecode {
    public static int add(int a, int b) {
        return a + b;
    }

    public static byte narrow(int value) {
        return (byte) value;
    }

    public static long tooLate(int a, int b) {
        return (long) (a + b);
    }

    public static long inTime(int a, int b) {
        return (long) a + b;
    }

    public static int unsignedShift(int value, int bits) {
        return value >>> bits;
    }

    public static int divide(int a, int b) {
        return a / b;
    }

    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        System.out.println("add=" + add(max, 1));
        System.out.println("narrow=" + narrow(130));
        System.out.println("tooLate=" + tooLate(max, 1));
        System.out.println("inTime=" + inTime(max, 1));
        System.out.println("unsignedShift=" + unsignedShift(-1, 1));
        System.out.println("divide=" + divide(-7, 3));
    }
}
```

Commands with **JDK 17+ supporting `--release 17`**:

```bash
javac --release 17 IntegerBytecode.java
java IntegerBytecode
javap -c -p IntegerBytecode
```

**Stdout of `java IntegerBytecode`**:

```text
add=-2147483648
narrow=-126
tooLate=-2147483648
inTime=2147483648
unsignedShift=2147483647
divide=-2
```

With the command `javap -c -p IntegerBytecode`, omitting offset addresses and necessary load/return details, the main opcode sequences in the methods look like:

```text
add:           iload_0, iload_1, iadd, ireturn
narrow:        iload_0, i2b, ireturn
tooLate:       iload_0, iload_1, iadd, i2l, lreturn
inTime:        iload_0, i2l, iload_1, i2l, ladd, lreturn
unsignedShift: iload_0, iload_1, iushr, ireturn
divide:        iload_0, iload_1, idiv, ireturn
```

This is a **schematic of the notable opcodes**, not the verbatim full `javap` output. A compiler may choose a different sequence while still conforming to Java; the `javap` output will include offsets as well as the `main` method.

The crux: in `tooLate`, the `iadd` opcode executes **before** `i2l`; by the time `i2l` runs, the addition has already wrapped. In `inTime`, each operand is widened with `i2l`, and then `ladd` adds two `long`s, so `2147483648` does not exceed the 64-bit range.

### Tracing `iadd` on the Operand Stack

Example calling `add(2147483647, 1)` (below is only the relevant part of the `add` method frame):

| Point in Time | Operand stack, bottom to top | Explanation |
| --- | --- | --- |
| Before first instruction | `[]` | `a` and `b` are in local variables |
| After `iload_0` | `[2147483647]` | Loads `a` of type `int` |
| After `iload_1` | `[2147483647, 1]` | Loads `b` of type `int` |
| After `iadd` | `[-2147483648]` | 32-bit addition, keeps low bits in two's complement |
| After `ireturn` | Frame's stack ends | Returns `int` result to caller |

If you read bytecode and see `i2l` *after* `iadd`, you must not infer that it is a `long` addition just because the method returns `long`.

### `javap` Shows the Mechanism, Not a One-to-One Source-to-Opcode Guarantee

- An `a++` operation may be emitted by the compiler as `iinc` when it is a suitable `int` local variable; incrementing a field/array may require different load, add, and store opcodes.
- The compiler is allowed to constant-fold constant expressions, so not every source line containing `+` will generate `iadd`.
- The JIT may change the CPU instructions executed, but the observable result of the operation must preserve the JVM/Java contract.

Treat `javap -c` as a way to inspect the **concrete bytecode** generated by the compiler, while the JLS/JVMS is the source that defines the **mandatory semantics**.

## 9. When Overflow Is an Error: Checking via APIs and Range Checks

If business requirements do not accept wrapping, detect it before/after via APIs instead of hoping the JVM will report an error automatically:

- `Math.addExact(a, b)`, `subtractExact`, `multiplyExact`: perform integer arithmetic with overflow checking, throwing `ArithmeticException` if the result exceeds the range.
- `Math.incrementExact`, `decrementExact`, `negateExact`: check overflow for the corresponding operations; for example, `Math.negateExact(Integer.MIN_VALUE)` throws an error.
- `Math.toIntExact(longValue)`: narrows `long → int` with range checking instead of a cast that silently drops the high 32 bits.
- For results that may exceed `long`, consider `BigInteger` or an appropriate data model; for monetary values with fractional parts, also consider `BigDecimal` or a smallest-unit integer convention.

Create **`CheckedArithmetic.java`**:

```java
public class CheckedArithmetic {
    public static void main(String[] args) {
        try {
            System.out.println(Math.addExact(Integer.MAX_VALUE, 1));
        } catch (ArithmeticException ex) {
            System.out.println("add overflow detected");
        }

        try {
            System.out.println(Math.toIntExact(3_000_000_000L));
        } catch (ArithmeticException ex) {
            System.out.println("narrowing overflow detected");
        }

        System.out.println("valid=" + Math.multiplyExact(6, 7));
    }
}
```

```bash
javac --release 17 CheckedArithmetic.java
java CheckedArithmetic
```

**Stdout**:

```text
add overflow detected
narrowing overflow detected
valid=42
```

The two errors above are reported because we **called checked APIs**, not because the JVM detects overflow by default for `iadd` or `l2i`.

### Bounds Checking Without Creating Overflow Inside the Check Expression

A common warning when checking array slices, offsets, or buffers:

```java
// May be wrong if offset + length overflows int:
if (offset + length > capacity) {
    throw new IllegalArgumentException("out of bounds");
}
```

This is a snippet without sufficient safety conditions if the values are untrusted. For `int` values representing non-negative offset/length/capacity, a safer check rejects negative inputs and keeps the subtraction within range:

```java
if (capacity < 0 || offset < 0 || length < 0
        || offset > capacity || length > capacity - offset) {
    throw new IllegalArgumentException("out of bounds");
}
```

Because `offset <= capacity` is checked before the subtraction side, `capacity - offset` is non-negative and does not overflow within the non-negative `int` range. The `||` condition short-circuits from left to right, so the subtraction is only evaluated when the preceding conditions allow it.

A similar issue arises with `count * elementSize`, `end = start + duration`, computing hash indices, monotonically increasing sequence numbers, or converting timestamps to smaller units: **the check itself must also be overflow-safe**.

## 10. Common Mistakes When Reading Source or Bytecode

| Misconception | Correct Fact |
| --- | --- |
| "When `int` overflows, the JVM throws `ArithmeticException`" | `iadd`/`isub`/`imul` wrap; only integer division/remainder by 0 throws, or use checked APIs |
| "Assigning the result to `long` prevents overflow" | If the `int` operation finishes before widening, the lost part cannot be recovered |
| "`byte + byte` has type `byte`" | Binary numeric promotion makes ordinary addition produce `int` |
| "`(byte)255` becomes 255 but stores fewer bits" | The result is `-1` because the low bits `0xFF` are interpreted as signed |
| "`char` is a signed 16-bit integer" | `char` represents an **unsigned** integer value 0–65535 |
| "`i2b` pushes an independent 8-bit byte value onto the stack" | It narrows, then sign-extends back to an **int** value on the operand stack |
| "`(int) Double.NaN` throws an error" | The result is `0`; infinite/out-of-range values are clamped, without throwing an overflow exception |
| "`>>>` turns `int` into an unsigned type" | It only shifts bits with zero-fill; the result type is still `int` |
| "Left-shifting an `int` by 32 positions produces 0" | The shift distance is masked to 5 bits, so `1 << 32` equals `1` |
| "`-7 / 3` is `-3` like floor division" | Java integer division rounds toward 0, resulting in `-2` |
| "If the source has an addition, `javap` always has `iadd`" | The compiler can constant-fold, use another opcode, or optimize with equivalent semantics |

## 11. Workflow for Analyzing an Integer Operation

When an operation produces an unexpected result, go top-down:

1. **Identify the version and source types:** are the values `byte`/`short`/`char`/`int`/`long` or floating-point? Which `--release` and APIs apply?
2. **Parenthesize according to evaluation order:** determine whether addition/multiplication happens before or after the cast.
3. **Apply promotion:** does the operation produce `int`, `long`, or floating-point? Is there unboxing or a constant expression?
4. **Compute the mathematical result:** if it is `int`/`long`, keep the low 32/64 bits when addition/multiplication/subtraction can overflow.
5. **Apply subsequent casts:** narrowing keeps the low bits; signed widening sign-extends, `char` zero-extends.
6. **If dividing or shifting:** remember integer division truncates toward 0; shifts mask 5/6 bits of the shift distance; distinguish `>>` from `>>>`.
7. **Cross-check with bytecode:** `javac --release 17` + `javap -c -p`; trace `iadd`, `i2l`, `ladd`, `i2b`, etc., in exact order.
8. **Assess the risk:** is wrapping an intentional design (e.g., hashes/bit flags) or a bug (e.g., sizes, money, bounds checks)? If it is a bug, use checked APIs, a wide-enough range, or a big-number type.

### Quick Self-Check

| Java 17 Expression | Result | Reason |
| --- | --- | --- |
| `Integer.MAX_VALUE + 1` | `-2147483648` | `int` 32-bit wrap |
| `(long) (Integer.MAX_VALUE + 1)` | `-2147483648L` | `int` addition first, then `i2l` |
| `(long) Integer.MAX_VALUE + 1` | `2147483648L` | Widen first, `long` addition |
| `(byte) 0xFF` | `-1` | Keep 8 bits, then interpret as signed |
| `(char) -1` | `65535` | Keep 16 bits and interpret as unsigned |
| `(int) Double.NaN` | `0` | Float/double → integer rule |
| `-7 % 3` | `-1` | Remainder takes sign of dividend |
| `1 << 32` | `1` | Low 5 bits of shift distance are `0` |
| `-1 >>> 1` | `2147483647` | Zero-fill right shift |
| `Math.addExact(Integer.MAX_VALUE, 1)` | Throws `ArithmeticException` | API actively checks for overflow |

## 12. Primary References (Java SE 17)

- [JLS §4.2.1 — Integral Types and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.1): ranges of `byte`, `short`, `int`, `long`, `char`.
- [JLS `5.1.2 — Widening Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.2) and [`5.1.3 — Narrowing Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.3): signed/unsigned widening, bit loss, floating-point → integer.
- [JLS `5.6 — Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.6) and [`15.26.2 — Compound Assignment Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.26.2): promotion, compound assignment.
- [JLS `15.17 — Multiplicative Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.17) and [`15.18 — Additive Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.18): integer division, remainder, wrap on addition/multiplication.
- [JLS §15.19 — Shift Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.19): masking shift distance and shift types.
- [JVMS §2.11.3–§2.11.4](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.3): overview of arithmetic and conversion instructions; [JVMS §6.5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5) describes each opcode `iadd`, `i2b`, `l2i`, `idiv`, `iushr` in detail.
- [Java SE 17 `Math` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html) and [`Integer` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html): checked arithmetic, floor division, unsigned interpretation.
- [`javap` tool guide Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): how to read actual compiled bytecode.

**Core rule:** determine **the type and width at the exact moment the operation is performed**, and only then consider the type conversion steps. When reading bytecode, the order of `iadd`/`i2l`/`ladd` explains why two expressions that look similar in source can produce different results. There is no automatic overflow check for ordinary integer operations; choose actively if value loss is not permitted.
