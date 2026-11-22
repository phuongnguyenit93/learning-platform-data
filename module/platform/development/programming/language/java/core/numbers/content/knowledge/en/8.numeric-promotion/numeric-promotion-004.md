# Assigning constant expressions in byte, short, or char range in Java

In Java, arithmetic operations on `byte`, `short`, and `char` are normally **promoted to at least `int`**. The result of `byte + byte` is `int`, so it normally cannot be assigned directly back to `byte`. However, Java allows a useful exception: when the right-hand expression is a **compile-time constant expression** and its value fits in the target type `byte`, `short`, or `char`, the compiler can **implicitly narrow the type in an assignment context**.

Example:

~~~java
byte quantity = 100;      // valid, int constant 100 fits in byte range
byte total = 100 + 20;    // valid, int constant expression 120 fits in byte
short high = 32000 + 767;// valid, int constant 32767 fits in short
char letter = 'A' + 1;    // valid, int constant 66 converts to char 'B'
~~~

This rule does not mean every small numeric value is automatically cast by Java. The compiler must verify the **expression type**, **constancy**, and **representable range**. Knowing the value at runtime is not enough.

## 1. Ranges of target types

| Type | Bits | Integer range | In-range examples | Out-of-range examples |
| --- | ---: | ---: | --- | --- |
| `byte` | 8, signed | -128 to 127 | -128, 0, 127 | -129, 128 |
| `short` | 16, signed | -32768 to 32767 | -32768, 32767 | -32769, 32768 |
| `char` | 16, unsigned | 0 to 65535 | 0, 65, 65535 | -1, 65536 |

In text semantics, `char` is a **UTF-16 code unit**, which may not hold a full Unicode character when surrogate pairs are used. In this topic, we examine the 16-bit integer range of `char` to understand the conversion mechanism.

For decimal integer literals without an `L` suffix, the default type is `int` if the value is representable in `int`. The minus sign is a unary operator. All of the following declarations are valid:

~~~java
byte minByte = -128;
byte maxByte = 127;
short minShort = -32768;
short maxShort = 32767;
char firstChar = 0;
char lastChar = 65535;
~~~

Even though the source expressions have type `int`, the values are constants and representable in the target types. The compiler accepts the assignments without requiring a cast.

## 2. Assignment conversion rules (JLS §5.2)

In an **assignment context**, an expression of type `byte`, `short`, `char`, or `int` that is a **constant expression** can be narrowed to `byte`, `short`, or `char` when the final value is **representable in the target type**.

Let's analyze an assignment in order:

1. Determine the **source expression type**. For example, `100 + 20` has type `int` due to binary numeric promotion.
2. Check whether the expression is a **compile-time constant** according to the language specification.
3. Determine the value of the **entire expression**, not just each individual operand.
4. Compare against the target type's range. If out of range, implicit narrowing under this exception is not allowed.

Example with the same number 128:

~~~java
short okShort = 128;      // valid: 128 is within short range
char okChar = 128;        // valid: 128 is within char range
// byte badByte = 128;    // compile error: 128 > 127
~~~

And negative numbers:

~~~java
byte low = -128;          // valid
short negative = -128;    // valid
// char badChar = -128;   // error: char does not store negative values
~~~

**Source type restriction:** the exception above does not automatically apply to expressions of type `long`, `float`, or `double`, even if the mathematical value is very small.

~~~java
// byte a = 42L;          // error: long literal
// short b = 42.0;        // error: double literal
// char c = 65L;          // error: long literal

byte a = 42;             // valid: int constant fits in byte range
short b = 42;            // valid
char c = 65;             // valid: UTF-16 code for 'A'
~~~

There are no primitive `unsigned byte` or `unsigned short` types in Java. The fact that `char` is unsigned does not mean any negative number can be converted to `char` while preserving its value.

## 3. Constant expressions are not just single literals

A **constant expression** can be formed using literals and operators permitted by Java, as well as references to qualifying constant variables. Java can compute the result before running the program.

~~~java
byte sum = 20 + 30;           // 50
byte product = 6 * 7;         // 42
short shifted = 1 << 14;      // 16384
char next = 'A' + 1;          // 'B', numeric code 66
byte selected = (8 > 3) ? 10 : 20; // 10
~~~

`'A' + 1` is an expression of type `int`; however, its constant value is 66, which fits in `char`, so the assignment is accepted. This assignability does not change the type of the `+` operator.

Boundary cases:

~~~java
byte edge = 127;                  // valid
// byte tooHigh = 127 + 1;        // error: result is 128
short shortEdge = 32760 + 7;      // valid: 32767
// short tooHighShort = 32760 + 8; // error: 32768
char charEdge = 65535;            // valid
// char tooHighChar = 65535 + 1;   // error: 65536
// char negativeChar = 'A' - 66;   // error: -1
~~~

Both operands of `127 + 1` are very small, but the **result 128** exceeds the `byte` limit. With bitwise shifts, the result must also be checked:

~~~java
byte flag = 1 << 6;          // 64, valid
// byte overflow = 1 << 7;   // 128, compile error
~~~

The result of the shift has type `int` in both lines. Only the first line has a constant value fitting within the target type's range.

## 4. `final` and constant variable are not quite the same

A **constant variable** in the JLS is a `final` variable of primitive type or `String` initialized with a constant expression. For integral types, references to constant variables can participate in new constant expressions.

~~~java
final int MAX = 127;
byte maxByte = MAX;             // valid

final int BASE = 40;
byte answer = BASE + 2;        // valid: constant expression 42

final short LETTER_CODE = 65;
char letter = LETTER_CODE;     // valid: short constant with value 65

final char DOT = '.';
byte dotCode = DOT;            // valid: '.' has code 46, fits in byte range
~~~

The line `char letter = LETTER_CODE` is valid because it is a constant expression of type `short` whose value fits in `char`. An ordinary `short` variable is not allowed to be implicitly assigned to `char` solely because of its current value.

Conversely:

~~~java
int mutable = 42;
// byte a = mutable;          // error: mutable is not a compile-time constant

final int runtime = Integer.parseInt("42");
// byte b = runtime;          // error: final but not a constant variable
byte b = (byte) runtime;      // explicit cast, range check needed
~~~

`final` only prevents reassigning the variable. The value of `runtime` must come from a method call, and method calls are not among the permitted forms of constant expressions. Even though anyone knows `Integer.parseInt("42")` returns 42, the compiler does not use that knowledge to apply the narrowing exception.

Another pair of examples:

~~~java
final int COMPILE_TIME = 100 + 20;
byte x = COMPILE_TIME;          // valid

final int RUN_TIME = Math.abs(-120);
// byte y = RUN_TIME;           // error: not a constant expression
byte y = (byte) RUN_TIME;       // syntactically valid, check value
~~~

So when encountering a "possible lossy conversion" error, ask **whether the variable is a constant variable** before blindly adding a cast.

## 5. Connection to numeric promotion

In binary arithmetic operations, `byte`, `short`, and `char` are normally promoted to at least `int`. For example, `byte + byte` produces an `int` result even when the actual sum is very small.

~~~java
byte left = 10;
byte right = 20;
int total = left + right;          // valid
// byte wrong = left + right;      // error: non-constant int
byte explicit = (byte) (left + right); // syntactically valid, must check range
~~~

Even though you know the sum is 30, `left` and `right` are ordinary variables, so `left + right` is not a constant expression.

Compare:

~~~java
final byte left = 10;
final byte right = 20;
byte sum = left + right;          // valid because int constant expression equals 30
~~~

**The type of `left + right` is still `int`.** The compiler permits narrowing at assignment only because the constant result 30 fits in `byte`; there is no special rule making `final byte + final byte` have type `byte`.

A very common point of confusion is **compound assignment**:

~~~java
byte count = 120;
// count = count + 10;           // error: int -> byte does not auto-narrow
count += 10;                    // valid, but result will be -126
~~~

`+=` has a conversion mechanism back to the left-hand side's type with an effect similar to a cast, except that the left-hand side is evaluated only once. Because `120 + 10 = 130` is outside the `byte` range, the value stored in `count` is -126. This rule **is not** the constant narrowing exception that checks whether the value is in range; therefore `+=` can cause overflow and still compile.

## 6. Assignment context differs from passing method arguments

This exception applies when **initializing variables, using assignment, or initializing array elements**. However, a **method invocation context** has different conversion rules: a constant `int` argument does not automatically narrow to `byte` just to match a method parameter.

Example program saved as `InvocationExample.java`:

~~~java
class InvocationExample {
    static void consume(byte value) {
        System.out.println(value);
    }

    public static void main(String[] args) {
        byte local = 42;          // valid: assignment context
        consume(local);           // valid: byte -> byte
        consume((byte) 42);       // valid: explicit cast
        // consume(42);           // error: int literal does not automatically become byte
    }
}
~~~

Conclusion: the fact that `byte b = 42` is valid syntax does not mean `consume(42)` is also valid. For method calls, provide an expression of a compatible type or an appropriate explicit conversion.

In an array initializer, each element is checked under an assignment context:

~~~java
byte[] signedSamples = {0, 127, -128};
char[] letters = {'A', 66};
// byte[] badSamples = {128};    // compile error: element outside byte range
~~~

Assigning element 66 into the `char[]` array also relies on the `int` constant 66 fitting within the `char` range.

## 7. Explicit casts and risk of value loss

If an expression is not constant or a constant exceeds the range, you can write a cast to narrow it, but casting does not guarantee preserving the mathematical value. Narrowing integer conversion discards the high bits; `byte` and `short` are then interpreted as signed numbers.

~~~java
byte wrappedByte = (byte) 128;          // -128
short wrappedShort = (short) 32768;    // -32768
char wrappedChar = (char) -1;          // numeric value 65535
~~~

These lines **compile**, yet the values have changed. For counts, sizes, limits, or IDs, silent wrapping can create business logic bugs.

When the source is a runtime-computed `int`, check before casting if you need to preserve the exact signed numeric value:

~~~java
static byte checkedByte(int value) {
    if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
        throw new IllegalArgumentException("Ngoai mien byte: " + value);
    }
    return (byte) value;
}
~~~

This is an **illustrative method snippet**, placed inside a Java class. For `short`, check `Short.MIN_VALUE` and `Short.MAX_VALUE`; for `char`, check 0–65535. **Unsigned** data in protocols has its own semantics: keep it in a sufficiently wide type or perform bit conversions per the specification, rather than assuming it matches signed `byte` or `short` ranges.

## 8. Complete Java 17+ example

Create the file `ConstantNarrowingDemo.java`:

~~~java
public class ConstantNarrowingDemo {
    static final int BASE = 40;
    static final short LETTER_CODE = 65;

    public static void main(String[] args) {
        byte literal = 127;
        byte arithmetic = 100 + 20;
        short shortMax = 32_760 + 7;
        char nextLetter = 'A' + 1;
        byte fromFinal = BASE + 2;
        char fromShort = LETTER_CODE;

        System.out.println("literal: " + literal);
        System.out.println("arithmetic: " + arithmetic);
        System.out.println("shortMax: " + shortMax);
        System.out.println("nextLetter: " + nextLetter);
        System.out.println("fromFinal: " + fromFinal);
        System.out.println("fromShort: " + fromShort);

        int runtime = Integer.parseInt("42");
        byte narrowed = checkedByte(runtime);
        System.out.println("narrowed: " + narrowed);

        byte wrapped = (byte) (127 + 1);
        System.out.println("wrapped: " + wrapped);

        byte count = 120;
        count += 10;
        System.out.println("compound: " + count);
    }

    static byte checkedByte(int value) {
        if (value < Byte.MIN_VALUE || value > Byte.MAX_VALUE) {
            throw new IllegalArgumentException("Ngoai mien byte: " + value);
        }
        return (byte) value;
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac ConstantNarrowingDemo.java
java ConstantNarrowingDemo
~~~

Exact output:

~~~text
literal: 127
arithmetic: 120
shortMax: 32767
nextLetter: B
fromFinal: 42
fromShort: A
narrowed: 42
wrapped: -128
compound: -126
~~~

Cases to distinguish:

- `BASE + 2` has type `int`, yet is treated as a constant expression equal to 42 because `BASE` is a constant variable. Narrowing to `byte` is valid.
- `Integer.parseInt("42")` is called at runtime; variable `runtime`, even though currently 42, is still not a constant variable. The `checkedByte` method checks the range before casting.
- `(byte) (127 + 1)` is cast because 128 exceeds the `byte` range and yields -128; direct assignment `byte wrapped = 127 + 1` would fail to compile.
- `count += 10` is valid due to compound assignment rules and wraps from 130 to -126.

## 9. Quick comparison table

| Code snippet | Valid? | Reason |
| --- | --- | --- |
| `byte b = 127;` | Yes | int constant 127 fits in byte |
| `byte b = 128;` | No | constant 128 exceeds byte |
| `short s = 32767;` | Yes | constant fits in short |
| `short s = 32768;` | No | constant exceeds short |
| `char c = 65535;` | Yes | constant fits in char |
| `char c = -1;` | No | char does not store negative numbers |
| `byte b = 60 + 60;` | Yes | int constant expression equals 120 |
| `byte b = 60 + 70;` | No | constant expression equals 130, out of range |
| `byte b = 42L;` | No | long constant is excluded from the exception |
| `final int n = 42; byte b = n;` | Yes | n is a constant variable |
| `int n = 42; byte b = n;` | No | n is not a constant variable |
| `byte b = (byte) 128;` | Yes | Explicit cast; b equals -128 |
| `byte b = 120; b += 10;` | Yes | Compound assignment; b equals -126 |

## 10. Practice questions and answers

**Question 1.** Why does `byte a = 50 + 70;` compile, while `int x = 50; byte b = x + 70;` does not?  
**Answer:** The first addition is an `int` constant expression resulting in 120, which fits in `byte`. The second addition contains an ordinary variable `x`, so it is not a constant expression.

**Question 2.** Is `final int X = 200; byte b = X;` valid?  
**Answer:** No. `X` is a constant variable, but its constant value 200 exceeds `Byte.MAX_VALUE` which is 127.

**Question 3.** Why is `char c = 'A' + 1;` valid even though `'A' + 1` has type `int`?  
**Answer:** The entire expression is a constant equal to 66, which fits in `char`. Implicit narrowing conversion at assignment produces `'B'`.

**Question 4.** Is `final int x = Integer.parseInt("12"); short s = x;` valid?  
**Answer:** No. `x` is `final` but initialized with a method call, so it is not a constant variable; implicit narrowing from `int` to `short` is not allowed.

**Question 5.** Distinguish `short s = 32767 + 1;` and `short s = (short) (32767 + 1);`.  
**Answer:** The first reports an error because constant 32768 is outside the `short` range; the second casts explicitly so it compiles, but the stored value becomes -32768 rather than preserving 32768.

## 11. Key takeaways

- Constant expression narrowing from `byte`/`short`/`char`/`int` to `byte`, `short`, or `char` only occurs in an **appropriate assignment context** and when the value is representable.
- Numeric promotion still applies: `byte + byte` is normally `int`, even if an in-range **constant** expression can be assigned back to `byte`.
- `final` does not automatically mean constant variable; the initializer must be a constant expression.
- Passing arguments to methods, compound assignment, and casting follow different rules; in particular, casts or `+=` can lose numeric value.
- When encountering a "possible lossy conversion" error, check the **source type, constancy, and result range** before deciding whether to use a wider type, change logic, or perform a checked cast.