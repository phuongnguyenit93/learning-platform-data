# Table of Widening, Narrowing, and Numeric Promotion in Java

## 1. Three Concepts to Distinguish

When using Java's primitive numeric types, it is not just a matter of "assigning a smaller number to a larger number." You must identify **the type of each operand**, **the type in which the operation is performed**, and **the type of the variable receiving the result**:

- **Widening primitive conversion**: converting to a type allowed to widen implicitly, for example `int → long`. It is not necessarily strictly exact when the target type is `float` or `double`.
- **Narrowing primitive conversion**: converting to a type that may lose value range or digits, for example `int → byte` or `double → int`. Usually requires an explicit cast.
- **Numeric promotion**: automatically promoting operand types before computing, for example `byte + byte` is computed as `int`.

This lesson serves as a reference for `byte`, `short`, `char`, `int`, `long`, `float`, and `double` in Java 17+, including conversion tables, exceptions, integer and floating-point arithmetic, standalone program examples, common pitfalls, and exercises. `boolean` **does not convert to numbers or vice versa** under this mechanism.

## 2. Widening Primitive Conversion Table

The following assignments are valid **without a cast**:

| From Type | Can Widen To |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |
| `double` | No wider primitive numeric type |
| `boolean` | Does not participate in numeric conversion |

Mnemonic diagram:

~~~text
byte → short → int → long → float → double
               ↑
char ──────────┘
~~~

**There is no widening `byte → char` or `short → char`.** `char` is a **16-bit unsigned** type storing UTF-16 code units from 0 to 65535; `short` is a **16-bit signed** type from -32768 to 32767. Having the same bit width does not mean the two types implicitly convert to each other.

### Does Widening Always Preserve the Exact Value?

**No.** Widening between compatible integer types (`byte → short/int/long`, `short → int/long`, `char → int/long`, `int → long`) always preserves the exact value. `int → double` also preserves every `int` exactly, because `double` has a 53-bit significand, more than `int`'s 32 bits. `float → double` preserves the *stored binary float value* exactly, but does not recover a decimal number that was previously rounded.

Conversely, `int → float`, `long → float`, and `long → double` can lose significant bits because the target type lacks sufficient precision. The compiler still permits widening; it does not guarantee that rounding will not occur.

### Java 17 Example: Widening Loses Precision

Create the file `WideningDemo.java`:

~~~java
public class WideningDemo {
    public static void main(String[] args) {
        byte source = 100;
        short s = source;
        long exact = s;
        double d = exact;

        System.out.println("long = " + exact);
        System.out.println("double = " + d);

        int largeInt = 16_777_217;
        float f = largeInt;
        System.out.println("int = " + largeInt);
        System.out.println("float = " + f);
        System.out.println("float back = " + (int) f);

        long largeLong = 9_007_199_254_740_993L;
        double rounded = largeLong;
        System.out.println("long back = " + (long) rounded);
    }
}
~~~

~~~bash
javac WideningDemo.java
java WideningDemo
~~~

Output:

~~~text
long = 100
double = 100.0
int = 16777217
float = 1.6777216E7
float back = 16777216
long back = 9007199254740992
~~~

`float` has a 24-bit significand, so it cannot represent every `int` above the `2^24` threshold exactly. `double` cannot represent every `long` above the `2^53` threshold exactly. Widening can be **type**-safe without being **precision**-safe.

## 3. Narrowing Primitive Conversion Table

Narrowing paths require a cast in most situations:

| From | Typical Narrowing Targets | Consequences to Consider |
| --- | --- | --- |
| `short` | `byte`, `char` | Loss of high bits, sign may change |
| `char` | `byte`, `short` | Loss of bits or change in sign interpretation |
| `int` | `byte`, `short`, `char` | Keeps low bits according to target width |
| `long` | `byte`, `short`, `char`, `int` | Discards high bits |
| `double` | `float` | May round, underflow to zero, or overflow to infinity |
| `float/double` | `int`, `long` and smaller integer types | Truncates fractional part, special rules for NaN/out-of-range |

Signed integer types use two's complement representation. When narrowing from `int` to `byte`, Java keeps the low 8 bits and interprets them as a signed byte. Thus `(byte) 130` equals `-126`, not 127, and throws no exception. `(char) -1` keeps the low 16 bits and becomes code unit number `65535`.

### Casting from float/double to Integer Is Not Nearest Rounding

`(int) 3.99` is `3`; `(int) -3.99` is `-3`. The rule truncates the fractional part **toward 0**. For `NaN`, converting to `int`/`long` yields 0. For values exceeding the `int`/`long` range, converting directly to that type produces the min/max bound in the corresponding direction; for `byte`/`short`/`char`, there is a subsequent integer narrowing step, so the result **is not simply clamped at the smaller type's bounds**.

### Java 17 Example: Narrowing and Special Values

Create the file `NarrowingDemo.java`:

~~~java
public class NarrowingDemo {
    public static void main(String[] args) {
        int n = 130;
        byte b = (byte) n;
        char c = (char) -1;

        System.out.println("byte = " + b);
        System.out.println("char code = " + (int) c);
        System.out.println("3.99 -> int = " + (int) 3.99);
        System.out.println("-3.99 -> int = " + (int) -3.99);
        System.out.println("NaN -> int = " + (int) Double.NaN);
        System.out.println("infinity -> int = "
                + (int) Double.POSITIVE_INFINITY);
        System.out.println("1000 -> byte = " + (byte) 1000);
    }
}
~~~

~~~bash
javac NarrowingDemo.java
java NarrowingDemo
~~~

Output:

~~~text
byte = -126
char code = 65535
3.99 -> int = 3
-3.99 -> int = -3
NaN -> int = 0
infinity -> int = 2147483647
1000 -> byte = -24
~~~

When real rounding is needed, use `Math.round` or `BigDecimal.setScale` with an appropriate rounding mode; do not substitute a cast and expect the same rules. Also do not use a cast to check value-range safety, because Java does not automatically throw an error when bits are discarded.

## 4. Unary Numeric Promotion

The unary arithmetic operators `+x`, `-x`, and the bitwise complement operator `~x` (for integer types) apply **unary numeric promotion**:

| Original Type | Type After Promotion |
| --- | --- |
| `byte`, `short`, `char` | `int` |
| `int` | `int` |
| `long` | `long` |
| `float` | `float` |
| `double` | `double` |

For example, `byte x = 5; int y = -x;` is valid, because `-x` has type `int`. `byte y = -x;` is invalid if `x` is a runtime `byte` variable without a cast, even though the value `-5` fits in a `byte`.

`~charValue` also has type `int`. The logical operator `!` applies to `boolean`, not numeric promotion. Likewise, `boolean` does not convert to 0 or 1 in arithmetic calculations.

## 5. Binary Numeric Promotion: Type Selection Table for Two Operands

In binary arithmetic operations such as `+`, `-`, `*`, `/`, and `%`, Java selects the computation type in order:

1. If either is `double` → use `double`.
2. Otherwise, if either is `float` → use `float`.
3. Otherwise, if either is `long` → use `long`.
4. Otherwise → use `int`.

| Expression | Computation/Result Type |
| --- | --- |
| `byte + byte` | `int` |
| `byte + short` | `int` |
| `short + char` | `int` |
| `int + long` | `long` |
| `long + float` | `float` |
| `float + double` | `double` |
| `int / int` | `int` |
| `int / double` | `double` |
| `char * byte` | `int` |

Numeric comparison operators such as `<` and `>=` also use numeric promotion to compare, but **the result of the comparison is boolean**. Do not mechanically apply the "arithmetic result type" table to every operator. For string concatenation, the `+` operator also has string concatenation semantics distinct from numeric addition.

### Java 17 Example: Integer Division and Expression Type

Create the file `NumericPromotionDemo.java`:

~~~java
public class NumericPromotionDemo {
    public static void main(String[] args) {
        byte a = 10;
        short b = 20;
        int sum = a + b;
        char letter = 'A';
        int nextCode = letter + 1;
        float mixed = 1L + 0.5f;

        System.out.println("byte + short = " + sum);
        System.out.println("char + int = " + nextCode);
        System.out.println("long + float = " + mixed);
        System.out.println("5 / 2 = " + (5 / 2));
        System.out.println("assigned double = " + (double) (5 / 2));
        System.out.println("5 / 2.0 = " + (5 / 2.0));
    }
}
~~~

~~~bash
javac NumericPromotionDemo.java
java NumericPromotionDemo
~~~

Output:

~~~text
byte + short = 30
char + int = 66
long + float = 1.5
5 / 2 = 2
assigned double = 2.0
5 / 2.0 = 2.5
~~~

**The receiving variable's type does not retroactively change the type of an operation that already happened.** `double d = 5 / 2;` performs integer division first (yielding 2), then widens from `int` to `double` (2.0). To get 2.5, convert **an operand before the division**: `5 / 2.0` or `(double) 5 / 2`.

## 6. Overflow Before Widening to the Target Variable

A trap:

~~~java
// Demonstration snippet: the result already overflows int before assignment.
long wrong = 50_000 * 50_000;
~~~

Both literals are `int`, so `50_000 * 50_000` is an `int` multiplication that overflows before being widened to `long`. To avoid this, use a `long` literal `50_000L * 50_000`, or cast one operand **before multiplying**.

### Java 17 Example: Overflow Due to Operand Types

Create the file `OverflowDemo.java`:

~~~java
public class OverflowDemo {
    public static void main(String[] args) {
        long wrong = 50_000 * 50_000;
        long correct = 50_000L * 50_000;

        System.out.println("int first = " + wrong);
        System.out.println("long first = " + correct);

        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("overflow detected");
        }
    }
}
~~~

~~~bash
javac OverflowDemo.java
java OverflowDemo
~~~

Output:

~~~text
int first = -1794967296
long first = 2500000000
overflow detected
~~~

The `+`, `-`, and `*` operations on `int`/`long` do not normally throw an overflow error; the two's complement result wraps around modulo the bit width. When silent overflow is unacceptable, `Math.addExact`, `subtractExact`, and `multiplyExact` help detect errors for `int`/`long`.

## 7. Bit Shift Operations Use Their Own Rules

The shift operators `<<`, `>>`, and `>>>` do not use binary numeric promotion like addition. **Each operand undergoes unary numeric promotion independently**, and the result type follows the promoted left-hand operand (`int` or `long`).

- `byte b = 1; b << 8` yields an `int` result = 256.
- `1L << 40` shifts a `long` and gives 1099511627776.
- `1 << 32` equals `1 << 0` because only the low 5 bits of the shift distance are used for `int`.
- `1L << 64` equals `1L << 0` because only the low 6 bits are used for `long`.

### Java 17 Example: Shift and Promotion

Create the file `ShiftDemo.java`:

~~~java
public class ShiftDemo {
    public static void main(String[] args) {
        byte x = 1;
        int result = x << 8;
        long wide = 1L << 40;

        System.out.println("byte shift = " + result);
        System.out.println("long shift = " + wide);
        System.out.println("1 << 32 = " + (1 << 32));
        System.out.println("-1 >>> 1 = " + (-1 >>> 1));
    }
}
~~~

~~~bash
javac ShiftDemo.java
java ShiftDemo
~~~

Output:

~~~text
byte shift = 256
long shift = 1099511627776
1 << 32 = 1
-1 >>> 1 = 2147483647
~~~

The bitwise operators `&`, `|`, and `^` between integers follow their own appropriate numeric promotion rules; when both operands are `boolean`, they also act as boolean operators, **with no conversion from `boolean` to `int`**.

## 8. Exception: Narrowing Constant int in Assignment

In **assignment conversion**, a *constant expression* of type `int` can be implicitly assigned to `byte`, `short`, or `char` if **the constant value fits in the range** of the target type:

~~~java
// Valid syntax demonstration, not a standalone program.
byte max = 127;
short s = 1 + 2;
char latinA = 65;
final int LIMIT = 100;
byte fromConstant = LIMIT;
~~~

However:

~~~java
// Compilation error demonstration, do not run this block as-is.
byte invalid = 128;      // Constant exceeds byte range
int value = 127;
byte fromValue = value;   // value is not a constant expression
byte x = 10;
byte result = x + 1;     // x + 1 has type int
~~~

A `final int` initialized with a suitable constant expression can participate in this rule; a regular `int` variable cannot be implicitly narrowed simply because its runtime value happens to fit within the `byte` range.

### Java 17 Example: In-Range Constant and Casting a Variable

Create the file `ConstantAssignmentDemo.java`:

~~~java
public class ConstantAssignmentDemo {
    public static void main(String[] args) {
        byte max = 127;
        short computed = 1 + 2;
        char ascii = 65;
        final int LIMIT = 100;
        byte fromConstant = LIMIT;

        int runtime = 127;
        byte explicit = (byte) runtime;

        System.out.println("byte = " + max);
        System.out.println("short = " + computed);
        System.out.println("char code = " + (int) ascii);
        System.out.println("final constant = " + fromConstant);
        System.out.println("cast variable = " + explicit);
    }
}
~~~

~~~bash
javac ConstantAssignmentDemo.java
java ConstantAssignmentDemo
~~~

Output:

~~~text
byte = 127
short = 3
char code = 65
final constant = 100
cast variable = 127
~~~

**The constant assignment exception does not automatically apply to method invocation.** Given a method `takeByte(byte x)`, calling `takeByte(1)` is invalid if that is the only overload; you must use `takeByte((byte) 1)` or pass a `byte` variable.

## 9. Compound Assignment and ++ Have Implicit Narrowing

`byte b = 120; b += 10;` is valid, even though the expression `b + 10` has type `int`. Compound assignment has semantics similar to `b = (byte) (b + 10)`, except that the left-hand operand is evaluated only once. This permits **implicit narrowing** and can produce overflow. `++` and `--` on smaller integer types can also cause values to wrap around.

### Java 17 Example: += Does Not Guarantee Range Safety

Create the file `CompoundAssignmentDemo.java`:

~~~java
public class CompoundAssignmentDemo {
    public static void main(String[] args) {
        byte b = 120;
        b += 10;

        short s = 32767;
        s++;

        int i = Integer.MAX_VALUE;
        i += 1L;

        System.out.println("byte += = " + b);
        System.out.println("short++ = " + s);
        System.out.println("int += long = " + i);
    }
}
~~~

~~~bash
javac CompoundAssignmentDemo.java
java CompoundAssignmentDemo
~~~

Output:

~~~text
byte += = -126
short++ = -32768
int += long = -2147483648
~~~

Conversely, `b = b + 10` reports a compilation error if `b` is a `byte` variable because assigning a runtime `int` to a `byte` lacks a cast. The fact that `+=` compiles does not mean the result stays in range. For data requiring safety, compute in a wider type and check bounds before casting.

## 10. Method Invocation, Overloading, Boxing, and the Ternary Operator

**Method invocation conversion** allows valid primitive widening, but **does not apply the `int` constant narrowing exception from assignment**. Overload resolution also depends on precedence rules among applicable methods, boxing/unboxing, varargs, and signature specificity.

### Java 17 Example: Widening When Choosing an Overload

Create the file `OverloadDemo.java`:

~~~java
public class OverloadDemo {
    static String choose(long x) {
        return "long";
    }
    static String choose(float x) {
        return "float";
    }
    static String choose(double x) {
        return "double";
    }

    public static void main(String[] args) {
        System.out.println("int -> " + choose(5));
        System.out.println("float -> " + choose(5.0f));
        System.out.println("double -> " + choose(5.0));
    }
}
~~~

~~~bash
javac OverloadDemo.java
java OverloadDemo
~~~

Output:

~~~text
int -> long
float -> float
double -> double
~~~

`choose(5)` can widen `int` to `long`, `float`, or `double`; among these overloads, `long` is the more specific choice. `Integer`, `Long`, and `Double` are **wrapper reference types**, not primitives; they have their own boxing/unboxing rules. For example, `Integer i = 10; long x = i;` is valid due to unboxing `int` and then widening to `long`, whereas `Long l = Integer.valueOf(10);` is not widening between two wrappers. Unboxing a `null` wrapper can throw `NullPointerException`.

The ternary operator `condition ? a : b` has its own **numeric conditional expression** rules, with exceptions involving `byte`/`short`/`char` and in-range `int` constants. Therefore, you cannot blindly apply the `a + b` table to all ternary expressions. Check the types of each branch, constant cases, and the JLS version when you need to deduce the exact result type.

## 11. BigDecimal Does Not Automatically Participate in Numeric Promotion

`BigDecimal` is a **class**, not part of the primitive promotion system:

- `0.1 + 0.2` is a `double` operation, not exact decimal addition.
- `new BigDecimal("0.1").add(new BigDecimal("0.2"))` performs decimal `BigDecimal` addition.
- Java does not allow the `BigDecimal + int` operator. Use `add` and construct the `BigDecimal` operand explicitly.
- Java also does not automatically convert an overflowed `int`/`long` operation to `BigInteger` or `BigDecimal`.
- `new BigDecimal(0.1)` preserves the exact approximate binary `double` value received, which can differ from the decimal 0.1 the user intended; prefer the exact decimal string constructor when the problem requires it.

For currency or decimal values requiring exactness, choose the appropriate numeric type **before performing operations**, rather than waiting until data is lost and casting the result afterward.

## 12. Quick Decision Table

| Code or Scenario | Result / Rule |
| --- | --- |
| `long l = someInt;` | Widening int→long, preserves value |
| `float f = someInt;` | Valid widening, may lose precision |
| `byte b = 127;` | Valid due to constant int assignment exception |
| `byte b = 128;` | Compile error: out of range |
| `int i = someLong;` | Compile error without cast |
| `byte a = 1, b = 2; int c = a+b;` | Addition uses int |
| `double d = 5/2;` | 2.0, because int division happens first |
| `double d = 5/2.0;` | 2.5, because there is a double operand |
| `long r = 50000*50000;` | Overflows int before widening to long |
| `long r = 50000L*50000;` | long multiplication, result 2500000000 |
| `byte b = 120; b += 10;` | Result -126 due to implicit narrowing |
| `int i = (int)3.99;` | 3, truncates fraction toward 0 |
| `char c = (char)-1;` | char code = 65535 |
| `int s = 1 << 32;` | 1 because only low 5 bits of shift distance are used |
| `boolean b = (boolean)1;` | Invalid, boolean does not participate in numeric conversion |

This table applies directly to primitive types. Cases involving boxing, wrappers, generics, overloading, the ternary operator, and special constants require checking their corresponding rules.

## 13. Common Mistakes

1. **"Widening is always exact."** Not true for int→float or long→double with large numbers.
2. **"A receiving long variable forces the operation to long."** No: int can overflow before assignment.
3. **"byte + byte is byte."** No: binary promotion produces int.
4. **"char is equivalent to short."** No: char is unsigned, short is signed.
5. **"Casting double to int rounds to nearest."** No: truncates the fractional part toward 0.
6. **"A narrowing cast automatically checks for out-of-range values."** No: integers can silently have high bits truncated.
7. **"`+=` is safer than `= a+b`."** No: it performs implicit narrowing.
8. **"An in-range int constant is narrowed in every context."** The assignment exception does not apply to normal method invocation.
9. **"Bit shifts use binary promotion like addition."** No: the result type is based on the unary-promoted left operand.
10. **"Boolean can be cast to int."** Java does not support this.
11. **"Wrappers can convert implicitly like primitives."** Boxing/unboxing and reference widening have separate rules.
12. **"Java automatically chooses BigDecimal when decimal numbers appear."** No: you must use the BigDecimal API explicitly.

## 14. Exercises and Answers

**Question 1.** Do `int i = 16_777_217; float f = i;` produce the exact same value?

**Answer:** No. Float can represent 16,777,216 without keeping 16,777,217 exact.

**Question 2.** Why does `byte x=10, y=20; byte sum=x+y;` fail to compile?

**Answer:** `x+y` has type int; use `int sum=x+y` or cast after verifying the range.

**Question 3.** What is `double result=5/2;` equal to, and how do you fix it?

**Answer:** 2.0; use `5/2.0` or `(double)5/2` to get 2.5.

**Question 4.** What do `(byte)130`, `(char)-1`, and `(int)-3.99` evaluate to?

**Answer:** -126, char code 65535, and -3.

**Question 5.** What values do `byte b=120; b+=10;` and `short s=32767; s++;` produce?

**Answer:** b is -126, s is -32768; compound assignment/increment can narrow implicitly.

**Question 6.** Does `long p=50_000*50_000;` equal `2_500_000_000L`?

**Answer:** No; int multiplication overflows first. Use `50_000L*50_000`.

**Question 7.** Why is `byte b=127;` valid while `int n=127; byte b=n;` is not?

**Answer:** An in-range int constant expression has an assignment exception, whereas a regular int variable requires a cast.

**Question 8.** What number does `1 << 32` produce?

**Answer:** 1, because int shift only considers the low 5 bits of the shift distance, so 32 is equivalent to 0.

## 15. Takeaways

- **Widening** is allowed implicitly, but can lose precision when converting from large integers to floating-point.
- **Narrowing** usually requires a cast; integers discard high bits, floating-point to integer truncates the fraction toward 0 and has boundary rules.
- **Unary promotion** promotes byte/short/char to int; **binary promotion** prioritizes double, float, long, then int before the operation.
- **Operand types determine the operation before assignment**, so a double receiving integer division or a long receiving an overflowed int multiplication still retains the intermediate error.
- **Constant narrowing in assignment**, compound assignment, shift operators, overloading, the ternary operator, and boxing/unboxing are exceptions that must be checked individually.
- For exact decimal arithmetic or integers exceeding long, use BigDecimal/BigInteger proactively through the API rather than expecting primitive promotion to handle it automatically.

Standard reference: Java Language Specification for Java SE 17 — `5.1.2 Widening Primitive Conversion`, `5.1.3 Narrowing Primitive Conversion`, `5.2 Assignment Contexts`, `5.6 Numeric Contexts`, `15.15 Unary Operators`, `15.17 Multiplicative Operators`, `15.18 Additive Operators`, `15.19 Shift Operators`, `15.25 Conditional Operator`, and `15.26 Assignment Operators`.
