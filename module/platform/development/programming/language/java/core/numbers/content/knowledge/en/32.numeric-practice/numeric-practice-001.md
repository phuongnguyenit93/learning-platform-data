# Practice: Writing a Verification Table for Result Types of Numeric Expressions in Java

## 1. Practice Objectives

When reading a Java expression such as `byte + short`, `int / int`, `long + float`, or `1 << 33`, we need to answer **two different questions**:

1. **What is the expression's type at compile time (*compile-time type*)?**
2. **What is its runtime value (*runtime value*)**, and is there a possibility of data loss, rounding, or overflow?

Java does not automatically keep the smallest type of the operands. Many operations on `byte`, `short`, or `char` produce an `int` result. Integer division does not suddenly become a floating-point number just because the mathematical result has a remainder. Addition involving `float` and `long` can produce `float`, even though `long` holds more digits. Understanding the exact **type inference rules** helps you avoid compile errors, choose appropriate casts, and detect arithmetic bugs.

This practice covers:

- A step-by-step process for building a verification table per expression.
- A reference table of numeric promotion rules and common exceptions.
- A **standalone Java 17+ program**, where each result is assigned to a variable with an **explicitly declared type**, so the compiler verifies it.
- Expressions that **do not compile**, analyzing why and how to fix them.
- Exercises to fill in the table yourself, with answers for both types and values.

## 2. Defining the Verification Table

A useful table needs at least these columns:

| Expression | Operand types | Applied rule | Result type | Runtime value / notes |
| --- | --- | --- | --- | --- |
| `a + b` | `byte` + `short` | Binary numeric promotion | `int` | Depends on values of `a`, `b` |
| `a / b` | `int` / `int` | Integer division | `int` | Discards fractional part toward 0 |
| `a + b` | `long` + `float` | Binary numeric promotion | `float` | May lose precision when converting `long` to `float` |

Do not infer types from how `System.out.println` displays them. For example, a printed value `3` could come from `byte`, `int`, `long`, `float`, or `double` (with different display formats in some cases). Rely on **expression syntax and type rules**; the runtime result is only a supplementary verification step.

With `var`, Java also determines a concrete type at compile time. `var` is not a dynamic numeric type, and it does not choose the result type based on the magnitude of the runtime value.

## 3. Rule 1: Types of Literals and Variables

| Syntax | Type | Explanation |
| --- | --- | --- |
| `123` | `int` | An integer literal without a suffix defaults to `int` if valid |
| `123L` | `long` | Suffix `L` or `l`; prefer `L` for readability |
| `1.5` | `double` | A literal with a decimal point defaults to `double` |
| `1.5f` | `float` | Suffix `f` or `F` |
| `1.5d` | `double` | Suffix `d` or `D` |
| `1e3` | `double` | Scientific notation of a floating-point literal |
| `'A'` | `char` | Character literal; the numeric Unicode code unit value of `'A'` is 65 |
| `true` | `boolean` | Not a numeric type |
| `"123"` | `String` | String, not a number |

The `-` sign in `-123` is a **unary operator** applied to the literal, not part of a regular integer literal. The two special values `-2147483648` and `-9223372036854775808L` are supported by the language under the rules for decimal literals and unary minus; do not infer that any out-of-range integer is valid.

Example:

~~~java
int whole = 12;
long large = 12L;
float measure = 12.5f;
double ratio = 12.5;

var inferredWhole = 10 / 4;  // int, value 2
var inferredRatio = 10 / 4.0; // double, value 2.5
~~~

`var` is inferred as **`int`** and **`double`** in the last two statements. There is no automatic conversion based on the result value.

## 4. Rule 2: Binary Numeric Promotion

For common binary arithmetic operators such as `+`, `-`, `*`, `/`, and `%`, Java uses *binary numeric promotion*. After unboxing (if needed), the general rule is:

1. If either operand is `double` → the result has type `double`.
2. Otherwise, if either operand is `float` → the result has type `float`.
3. Otherwise, if either operand is `long` → the result has type `long`.
4. Otherwise, for the remaining smaller integer types, the result has type **`int`**.

| Left operand | Right operand | Type of `left + right` |
| --- | --- | --- |
| `byte` | `byte` | `int` |
| `byte` | `short` | `int` |
| `char` | `int` | `int` |
| `int` | `int` | `int` |
| `int` | `long` | `long` |
| `long` | `float` | `float` |
| `float` | `double` | `double` |
| `long` | `double` | `double` |

A common pitfall: **`long + float` returns `float`**, not `long` and not necessarily `double`. `float` is a 32-bit floating-point type and may not preserve all digits of a large `long`. The result type is determined by **promotion rules**, not by which type "holds more numbers."

For `byte`, `short`, `char`, addition usually produces `int`:

~~~java
byte b = 10;
short s = 20;
char c = 'A';

int sum = b + s;    // int, value 30
int next = c + 1;   // int, value 66
~~~

The statement `byte bad = b + s;` does not compile without a cast: the result is `int` and cannot be implicitly assigned to `byte`.

## 5. Rule 3: Unary Promotion, Bitwise, and Shift

The unary operators `+`, `-`, `~` perform **unary numeric promotion**. With `byte`, `short`, or `char`, the operand is promoted to `int`:

~~~java
byte b = 10;

int positive = +b; // 10
int negative = -b; // -10
int bits = ~b;     // -11
~~~

Shift operators (`<<`, `>>`, `>>>`) do not use binary numeric promotion like addition. They promote each operand according to separate rules; **the result type equals the type of the left operand after unary promotion**:

| Expression | Result type | Value |
| --- | --- | --- |
| `(byte) 3 << 1` | `int` | `6` |
| `1 << 3` | `int` | `8` |
| `1L << 3` | `long` | `8` |
| `1 << 33` | `int` | `2` |
| `1L << 33` | `long` | `8589934592` |
| `~(short) 0` | `int` | `-1` |

For `int`, Java only uses the **low 5 bits** of the shift distance; therefore `1 << 33` is equivalent to `1 << 1`, resulting in `2`. For `long`, it uses the **low 6 bits** of the shift distance, so `1L << 33` is `8589934592`.

Do not infer the shift result type from the right operand's type: `1 << 3L` still has type `int` because the left operand is `int`. However, it is best to only use shift distances valid for your business logic, rather than relying on Java ignoring high bits for *validation*.

## 6. Rule 4: Integer Division and Creating Floating-Point Numbers

| Expression | Type | Result |
| --- | --- | --- |
| `7 / 2` | `int` | `3` |
| `-7 / 2` | `int` | `-3` |
| `7L / 2` | `long` | `3` |
| `7 / 2.0` | `double` | `3.5` |
| `7 / 2.0f` | `float` | `3.5` |
| `(double) 7 / 2` | `double` | `3.5` |
| `(double) (7 / 2)` | `double` | `3.0` |

The difference in the last two rows is **evaluation order**:

~~~java
int numerator = 7;
int denominator = 2;

double right = (double) numerator / denominator; // 3.5
double tooLate = (double) (numerator / denominator); // 3.0
~~~

In `tooLate`, `numerator / denominator` has already performed integer division and produced 3 **before the cast**. Casting `3` to `double` only produces `3.0` and does not recover the remainder.

Integer division by 0 throws `ArithmeticException` at runtime. Floating-point division by 0 may return infinity or `NaN` according to floating-point semantics; do not treat the two cases as the same.

## 7. Rule 5: Comparison, Conditional, and Ternary Operator

Arithmetic comparison operators such as `<`, `<=`, `>`, `>=`, and `==` apply the necessary operand conversion rules, but **the result type is `boolean`**.

~~~java
int i = 7;
long l = 9L;
boolean smaller = i < l;  // true
boolean equal = i == l;   // false
~~~

The conditional operator `condition ? left : right` has multiple rules and **does not always mechanically apply the binary numeric promotion table**.

| Expression | Result type | Why |
| --- | --- | --- |
| `true ? 7 : 0.5` | `double` | Two branches have `int` and `double` |
| `true ? 7 : 9L` | `long` | Two branches have `int` and `long` |
| `true ? (byte) 1 : 2` | `byte` | Special rule: `int` literal `2` is a constant expression representable in `byte` |
| `true ? 1 : 2.0f` | `float` | Two branches have `int` and `float` |

The rule for a `byte` branch and an `int` literal can make the result `byte`, not `int`; this is why you need to learn the specific rules for conditional expressions rather than applying the `+` promotion table.

You must also distinguish **the type of the expression** from **the evaluated branch**: `condition` determines which branch runs, but the expression type is determined at compile time from the types of both branches and the rules of `?:`.

## 8. Important Exceptions: Assignment, Compound Assignment, ++ and --

An assignment itself has a type corresponding to the variable on the left if valid. Some syntax forms also have **implicit narrowing conversion** that normal addition does not have.

~~~java
byte b = 127;
b += 1; // Compiles; b becomes -128 (byte overflow).
~~~

For compound assignment, `b += 1` has semantics similar to `b = (byte) (b + 1)`, except the left-hand side is evaluated only once. Therefore:

~~~java
byte b = 100;

// byte wrong = b + 1; // Does not compile: b + 1 is int.
b += 1;                // Compiles, value of b is 101.
b++;                   // Compiles, increments b by 1.
~~~

Similarly, for a `byte` variable, the expression `b++` has **type `byte`** (the postfix result is the old value) even though the intermediate arithmetic addition is performed according to promotion rules.

| Syntax | Expression type / behavior |
| --- | --- |
| `b + 1` where `b` is `byte` | `int` |
| `b += 1` where `b` is `byte` | Valid compound assignment, result has type `byte` |
| `b++` where `b` is `byte` | Type `byte`, returns old value then updates |
| `++b` where `b` is `byte` | Type `byte`, returns new value |
| `byte k = 1 + 2;` | Compiles because constant expression equals 3 within `byte` range |
| `byte k = b + 2;` | Does not compile because `b` is a variable, expression has type `int` |

Do not think `b += 1` checks for overflow. When exceeding `Byte.MAX_VALUE`, the result can wrap around. If business logic requires overflow detection, design a check or use a wider representation before narrowing the type.

## 9. Autoboxing, Unboxing, and Numeric Object Types

Java has wrapper classes such as `Integer`, `Long`, `Float`, and `Double`. With arithmetic operators, wrappers can be **unboxed** into primitives before promotion:

~~~java
Integer boxed = 5;
int result = boxed + 1; // int, value 6
~~~

Do **not** conclude that `Integer + int` produces `Integer`; the addition expression has type `int`. If a wrapper is `null`, an expression requiring unboxing can throw `NullPointerException`:

~~~java
Integer missing = null;
try {
    int result = missing + 1;
    System.out.println(result);
} catch (NullPointerException ex) {
    System.out.println("null unboxing");
}
~~~

`String` is a different case: the `+` operator performs string concatenation when one operand is used in string concatenation.

~~~java
String message = "count=" + 7; // "count=7", type String
~~~

Do not use the `+` operator directly between two `BigDecimal` or two `BigInteger` values. These are **objects**, not numeric primitives:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

BigDecimal decimal = new BigDecimal("0.1")
        .add(new BigDecimal("0.2")); // BigDecimal, exact 0.3

BigInteger integer = BigInteger.ONE.add(
        BigInteger.valueOf(2)
); // BigInteger, value 3
~~~

The type of the call `decimal.add(...)` is determined by the **method signature**; binary numeric promotion is not applied to those two objects.

## 10. Complete Verification Table: Concrete Types + Values

Assume the initial variables:

~~~java
byte b = 10;
short s = 20;
char c = 'A';
int i = 7;
long l = 9L;
float f = 2.5f;
double d = 0.5;
Integer boxed = 5;
~~~

Completed table:

| Expression | Result type | Value | Short reason |
| --- | --- | --- | --- |
| `b + s` | `int` | `30` | `byte` and `short` promoted to `int` |
| `c + 1` | `int` | `66` | `char` promoted to `int` |
| `i + l` | `long` | `16` | Has `long` |
| `l + f` | `float` | `11.5` | Has `float`, no `double` |
| `f + d` | `double` | `3.0` | Has `double` |
| `-b` | `int` | `-10` | Unary numeric promotion |
| `~b` | `int` | `-11` | Bitwise complement of `int` 10 |
| `b << 1` | `int` | `20` | Shift uses left operand type after promotion |
| `1 << 33` | `int` | `2` | `int` shift distance only uses low 5 bits |
| `1L << 33` | `long` | `8589934592` | Left operand is `long` |
| `i / 2` | `int` | `3` | Integer division |
| `i / 2.0` | `double` | `3.5` | Has `double` |
| `i < l` | `boolean` | `true` | Comparison |
| `true ? i : d` | `double` | `7.0` | Two branches `int` and `double` |
| `true ? (byte) 1 : 2` | `byte` | `1` | Special case of `?:` |
| `Math.round(2.6f)` | `int` | `3` | Overload taking `float` returns `int` |
| `Math.round(2.6d)` | `long` | `3` | Overload taking `double` returns `long` |
| `"n=" + i` | `String` | `n=7` | String concatenation |
| `boxed + 1` | `int` | `6` | Unbox then add |
| `new BigDecimal("0.1").add(new BigDecimal("0.2"))` | `BigDecimal` | `0.3` | Method `add` returns `BigDecimal` |

Values and types are determined by Java semantics, not because the table lists matching wrapper names. The next section has a **compilable** program that uses explicitly declared variables to force the compiler to verify the types above.

## 11. Standalone Java 17+ Program to Confirm the Table

Create the file `NumericExpressionTypeTable.java`:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

public class NumericExpressionTypeTable {
    static void row(String expression, String resultType, Object value) {
        System.out.println(expression + " | " + resultType + " | " + value);
    }

    public static void main(String[] args) {
        byte b = 10;
        short s = 20;
        char c = 'A';
        int i = 7;
        long l = 9L;
        float f = 2.5f;
        double d = 0.5;
        Integer boxed = 5;

        // Type is actually checked when javac assigns the result to the variable.
        int sumSmall = b + s;
        int sumChar = c + 1;
        long sumLong = i + l;
        float sumFloat = l + f;
        double sumDouble = f + d;
        int unaryMinus = -b;
        int bitComplement = ~b;
        int shifted = b << 1;
        int maskedShift = 1 << 33;
        long longShift = 1L << 33;
        int integerDivision = i / 2;
        double realDivision = i / 2.0;
        boolean compare = i < l;
        double conditional = true ? i : d;
        byte specialConditional = true ? (byte) 1 : 2;
        int roundedFloat = Math.round(2.6f);
        long roundedDouble = Math.round(2.6d);
        String concatenated = "n=" + i;
        int unboxed = boxed + 1;
        BigDecimal exactDecimal = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        BigInteger exactInteger = BigInteger.ONE
                .add(BigInteger.valueOf(2));

        row("b + s", "int", sumSmall);
        row("c + 1", "int", sumChar);
        row("i + l", "long", sumLong);
        row("l + f", "float", sumFloat);
        row("f + d", "double", sumDouble);
        row("-b", "int", unaryMinus);
        row("~b", "int", bitComplement);
        row("b << 1", "int", shifted);
        row("1 << 33", "int", maskedShift);
        row("1L << 33", "long", longShift);
        row("i / 2", "int", integerDivision);
        row("i / 2.0", "double", realDivision);
        row("i < l", "boolean", compare);
        row("true ? i : d", "double", conditional);
        row("true ? (byte) 1 : 2", "byte", specialConditional);
        row("Math.round(2.6f)", "int", roundedFloat);
        row("Math.round(2.6d)", "long", roundedDouble);
        row("\"n=\" + i", "String", concatenated);
        row("boxed + 1", "int", unboxed);
        row("BigDecimal.add", "BigDecimal", exactDecimal);
        row("BigInteger.add", "BigInteger", exactInteger);

        byte nearLimit = 127;
        byte before = nearLimit++;
        row("nearLimit++ (old)", "byte", before);
        row("nearLimit (new)", "byte", nearLimit);
    }
}
~~~

Run:

~~~bash
javac NumericExpressionTypeTable.java
java NumericExpressionTypeTable
~~~

Stdout:

~~~text
b + s | int | 30
c + 1 | int | 66
i + l | long | 16
l + f | float | 11.5
f + d | double | 3.0
-b | int | -10
~b | int | -11
b << 1 | int | 20
1 << 33 | int | 2
1L << 33 | long | 8589934592
i / 2 | int | 3
i / 2.0 | double | 3.5
i < l | boolean | true
true ? i : d | double | 7.0
true ? (byte) 1 : 2 | byte | 1
Math.round(2.6f) | int | 3
Math.round(2.6d) | long | 3
"n=" + i | String | n=7
boxed + 1 | int | 6
BigDecimal.add | BigDecimal | 0.3
BigInteger.add | BigInteger | 3
nearLimit++ (old) | byte | 127
nearLimit (new) | byte | -128
~~~

### Why Does the Program Verify the Types?

Each variable has an explicit type such as `long sumLong = i + l;`, `float sumFloat = l + f;`, or `byte specialConditional = true ? (byte) 1 : 2;`. The compiler ensures **the result is assignable** to that declared type, while expression rules determine the actual type. To distinguish an expression's type from allowed implicit assignment conversions (such as `int` to `long`), you still need to analyze according to the rules in sections 3–9, rather than relying solely on the assignment compiling successfully.

Passing a primitive variable into the `Object value` parameter of `row` causes it to be **boxed** for printing. Therefore, if you change the function to print `value.getClass()`, you are inspecting the **wrapper class after boxing**, not the original primitive type inference mechanism. The type column here is written explicitly based on compile-time analysis.

## 12. Cases That Do Not Compile and How to Fix Them

The following examples are **intentionally wrong**; do not paste them into `NumericExpressionTypeTable.java`:

~~~java
byte b = 10;
short s = 20;

byte sum = b + s;
// ERROR: b + s has type int, cannot be implicitly converted to byte.

float f = 2.5;
// ERROR: literal 2.5 is double, cannot be implicitly converted to float.

int whole = 3 / 2.0;
// ERROR: expression has type double, cannot be implicitly converted to int.

BigDecimal decimal =
        new BigDecimal("1") + new BigDecimal("2");
// ERROR: the + operator does not support two BigDecimals.
~~~

How to fix:

~~~java
byte b = 10;
short s = 20;

int sum = b + s;                     // Avoid narrowing cast if not needed.
float f = 2.5f;                      // float literal.
double quotient = 3 / 2.0;          // Preserve fractional part.

BigDecimal decimal = new BigDecimal("1")
        .add(new BigDecimal("2"));   // Use the add method.
~~~

This is an illustrative snippet; place it inside an appropriate method/class and add `import java.math.BigDecimal;` if used standalone.

A cast like `byte sum = (byte) (b + s);` will make it compile, but **does not guarantee** the sum is within the `byte` range. If preserving the exact sum matters, use a wider type (`int`); if enforcing range limits matters, check before casting.

## 13. Advanced Edge Cases When Determining Types

### `Math` Has Multiple Overloads

`Math.round(float)` returns `int`, `Math.round(double)` returns `long`. Therefore, the literal suffix changes the return type:

~~~java
int a = Math.round(2.6f);
long b = Math.round(2.6);
~~~

`Math.pow(2, 3)` returns `double` because the overload of `Math.pow` takes two `double`s and returns `double`, even though the input literals have type `int`. Check the **method signature** instead of applying arithmetic operator rules yourself.

### Overflow Does Not Automatically Promote Types

~~~java
int overflowed = Integer.MAX_VALUE + 1;
System.out.println(overflowed); // -2147483648

long preserved = (long) Integer.MAX_VALUE + 1;
System.out.println(preserved);  // 2147483648
~~~

In the first addition, both operands are `int`, so the operation still returns `int` and wraps around. **Assigning** the result of `Integer.MAX_VALUE + 1` to a `long` variable also does not fix the bug if the addition was already performed in `int`. To perform addition in a wider type, convert at least one operand **before the addition**.

### Loss of Precision When the Result Type Is Floating-Point

~~~java
long exact = 9_007_199_254_740_993L;
float changed = exact + 0.0f;
System.out.println(changed); // a float approximation, does not preserve all digits
~~~

The type rule still produces `float`. `float` cannot hold every large integer representable by `long`. You should also not conclude which operand is "wider" solely from storage bit count: floating-point has a wide magnitude range but finite integer precision.

### `var` Does Not Fix a Wrong Operation

~~~java
var quotient = 7 / 2;       // int, value 3
var precise = 7 / 2.0;      // double, value 3.5
var joined = "n=" + 7;      // String
~~~

`var` only omits writing the type name of the local variable; expression type rules remain unchanged.

### Constant Expressions Can Narrow on Assignment

~~~java
byte a = 1 + 2;   // Valid: constant int expression with value 3.

int n = 1;
 // byte b = n + 2; // Invalid: n is not a constant variable.
~~~

The implicit narrowing rule for constant expressions also depends on the assignment form and value range. It **does not change the type of the expression** `1 + 2` from `int` to `byte`; it only means the compiler allows converting the constant result to `byte` in that specific context.

## 14. How to Build Your Own Table to Diagnose Real Bugs

Follow this process:

1. **Record the type of each operand**: integer literal, floating-point literal, primitive variable, wrapper, or object?
2. **Identify the operator or method call**: binary operation, unary, shift, comparison, `?:`, assignment, or overloaded method?
3. **Apply the right rule**: do not use the `+` table for shift operators or `?:`; do not use numeric promotion for `BigDecimal.add`.
4. **Write down the compile-time type** *before* computing the value.
5. **Compute the value** using integer division rules, overflow, casts, evaluation order, and floating-point limits.
6. **Verify with compiled code**: use typed assignments, look for invalid conversion errors, and use output to check values.
7. **Note warnings** when a calculation can lose digits, overflow, unbox null, or differ from the expected mathematical expression.

Sample example:

| Expression | Identification | Type | Value | Warning |
| --- | --- | --- | --- | --- |
| `(double) (7 / 2)` | Divide `int` first, cast later | `double` | `3.0` | Fractional part already lost |
| `(double) 7 / 2` | `double` divided by `int` | `double` | `3.5` | No integer division |
| `Integer.MAX_VALUE + 1` | `int + int` | `int` | `-2147483648` | Overflow |
| `Math.round(2.6f)` | `float` overload | `int` | `3` | Does not return `float` |

## 15. Exercise: Fill In the Type and Value Table Yourself

Determine **the expression's type** first, then compute the value. Assume:

~~~java
byte b = 4;
short s = 6;
char c = 'B';        // 66
int i = 9;
long l = 5L;
float f = 0.5f;
double d = 2.0;
Integer boxed = 3;
~~~

| No. | Expression | Your predicted type | Your predicted value |
| ---: | --- | --- | --- |
| 1 | `b + s` | ? | ? |
| 2 | `c - 1` | ? | ? |
| 3 | `i / 2` | ? | ? |
| 4 | `i / 2.0f` | ? | ? |
| 5 | `l + f` | ? | ? |
| 6 | `f + d` | ? | ? |
| 7 | `~b` | ? | ? |
| 8 | `b << 2` | ? | ? |
| 9 | `1L << 5` | ? | ? |
| 10 | `i > l` | ? | ? |
| 11 | `true ? b : 2.0` | ? | ? |
| 12 | `boxed * 2` | ? | ? |
| 13 | `"value=" + i` | ? | ? |
| 14 | `Math.round(3.6f)` | ? | ? |
| 15 | `Math.pow(2, 3)` | ? | ? |

Answers:

| No. | Correct type | Value | Rule |
| ---: | --- | --- | --- |
| 1 | `int` | `10` | `byte + short` promoted to `int` |
| 2 | `int` | `65` | `char` promoted to `int` |
| 3 | `int` | `4` | Integer division 9/2 |
| 4 | `float` | `4.5` | Has `float` operand |
| 5 | `float` | `5.5` | `long + float` produces `float` |
| 6 | `double` | `2.5` | Has `double` |
| 7 | `int` | `-5` | Unary `~` on `int` 4 |
| 8 | `int` | `16` | Left shift operand promoted to `int` |
| 9 | `long` | `32` | Left shift on `long` |
| 10 | `boolean` | `true` | Comparison `9 > 5` |
| 11 | `double` | `4.0` | Two branches `byte` and `double` |
| 12 | `int` | `6` | Unbox `Integer` then multiply |
| 13 | `String` | `value=9` | String concatenation |
| 14 | `int` | `4` | `Math.round(float)` returns `int` |
| 15 | `double` | `8.0` | `Math.pow(double, double)` returns `double` |

### Try Modifying to Understand Deeper

- Replace `l = 5L` with a very large `long`, try `l + f`, and observe the error caused by `float`.
- Replace `i / 2` with `(double) i / 2`, compare the type and value.
- Replace `b + s` with `b += s` and predict both the expression type and the overflow risk.
- Replace `Math.round(3.6f)` with `Math.round(3.6)`: the value is still 4, but **the return type changes from `int` to `long`**.
- Try an `Integer` wrapper equal to `null` in `boxed + 1` and explain the runtime exception.

**Conclusion:** to verify numeric expressions in Java, always start from **the operand types and the rules of each operator**, then compute the value and evaluate overflow/loss-of-precision risks. A verification table must clearly distinguish compile-time type, runtime value, and assignment style to avoid inferring types from a single output line.
