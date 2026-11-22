# Types Inferred from Literals and Numeric Operations with `var` in Java

> **Java core — language-basics / Inference with var**  
> **Environment:** JDK 17+; a standalone Java file using only the standard library.  
> **Goal:** Accurately predict the **static type** inferred for `var` from literals, arithmetic operations, casts, and conditional expressions; avoid integer division, overflow before widening, and the misconception that `var` automatically picks the smallest type.

## 1. `var` Takes the Type of the Expression, Rather Than Guessing from the Value

When declaring a local variable with `var`, the compiler infers the type from **the initializer expression at compile time**:

~~~java
var count = 10;     // int, not byte even though 10 is very small.
var distance = 10L; // long.
var ratio = 2.5;    // double.
var precise = 2.5f; // float.
var symbol = 'A';   // char.
~~~

`var` is **not a dynamic type**. After `var count = 10;`, the variable `count` has a fixed `int` type; `count = 2.5;` does not compile because `double` cannot be implicitly converted to `int`.

**Rule of thumb:** To predict `var result = expression;`, first determine **the type of `expression` according to Java's rules**. The inferred type is that exact expression type.

## 2. Default Types of Numeric Literals

| Literal | Type of the Literal | Notes |
| --- | --- | --- |
| `10`, `1_000`, `0xFF`, `0b1010` | `int` | An integer literal without a suffix defaults to `int` if within range |
| `10L`, `10l` | `long` | Prefer uppercase `L` to avoid confusing `l` with the digit 1 |
| `2.5`, `2.5d`, `1e3` | `double` | A floating-point literal defaults to `double` |
| `2.5f`, `2.5F` | `float` | Requires the `f` or `F` suffix for the literal to be `float` |
| `'A'` | `char` | A character literal is neither `String` nor `int` |
| `(byte) 10`, `(short) 10` | `byte`, `short` | The cast determines the type of the initializer expression |

~~~java
var a = 1_000;        // int.
var b = 1_000L;       // long.
var c = 1e3;          // double (value 1000.0).
var d = 1e3f;         // float.
var e = (byte) 10;    // byte.
~~~

Do not confuse **type** with **how it prints** or value magnitude: `1000` and `1000L` have the same mathematical value but different types. A large decimal integer literal outside the `int` range requires an appropriate suffix such as `2147483648L`; writing `var n = 2147483648;` does not make Java automatically guess `long`.

## 3. Operations Determine the Type of `var` Before Assignment

For binary arithmetic operators such as `+`, `-`, `*`, `/`, and `%`, Java applies **binary numeric promotion** to the operands before computing:

1. If either is `double` → result type is `double`.
2. Otherwise, if either is `float` → result type is `float`.
3. Otherwise, if either is `long` → result type is `long`.
4. Otherwise → result type is `int` (even for `byte`, `short`, or `char` operands).

| Initializer Expression | Inferred Type with `var` | Example Result |
| --- | --- | --- |
| `2 + 3` | `int` | `5` |
| `2 + 3L` | `long` | `5` |
| `2 + 3.5f` | `float` | `5.5` |
| `2L + 3.5` | `double` | `5.5` |
| `(byte) 10 + (short) 20` | `int` | `30` |
| `'A' + 1` | `int` | `66` |
| `7 / 2` | `int` | `3` |
| `7 / 2.0` | `double` | `3.5` |

Example:

~~~java
var sum = (byte) 10 + (short) 20; // int, not byte/short.
var afterChar = 'A' + 1;          // int, not char.
var mixed = 2 + 3L;               // long.
~~~

`var` is not the reason `byte + short` becomes `int`: **the operator rules themselves** determine that type. `var` simply adopts the type that was already determined.

## 4. Integer Division Pitfall

~~~java
var whole = 7 / 2;       // int: 3, not 3.5.
var fraction = 7 / 2.0;  // double: 3.5.
var byCast = (double) 7 / 2; // double: 3.5.
~~~

When both operands of `/` are integer types, Java performs integer division, truncating the fractional part toward 0. Writing `double result = 7 / 2;` still produces **3.0**: integer division **already occurred before** the result was converted to `double` for assignment.

To perform floating-point division, make **at least one operand** a floating-point type **before the division sign**, using a literal like `2.0` or a cast like `(double) 7`.

Do not rely on `var` expecting Java to pick a type “capable of keeping the fractional part”: `var` preserves the exact expression type and does not alter the operation.

## 5. Overflow Before Widening Pitfall

Even when the target variable is `long`, an `int` calculation can overflow **before assignment**:

~~~java
var overflow = Integer.MAX_VALUE + 1;    // int: -2147483648.
var exact = (long) Integer.MAX_VALUE + 1; // long: 2147483648.
var lateCast = (long) (Integer.MAX_VALUE + 1); // long: -2147483648.
~~~

- `Integer.MAX_VALUE + 1`: both operands are `int`, the `int` addition overflows, and then `var` infers `int`.
- `(long) Integer.MAX_VALUE + 1`: the cast widens the first **operand** to `long` before the addition; the `long` result does not overflow.
- `(long) (Integer.MAX_VALUE + 1)`: the addition already overflowed inside the parentheses, and only afterward is the wrong value cast to `long`.

**Takeaway:** If you need a wider type, widen one operand **before the operation**, rather than just casting the already-computed result.

## 6. Conditional Expressions and Type Casting

The type of the ternary operator `condition ? a : b` depends on the typing rules for its two branches:

~~~java
var mixedConditional = true ? 1 : 2.0; // double, value 1.0.
var castFirst = (float) 3;             // float, value 3.0f.
~~~

In the first example, the `int` and `double` branches give the expression type `double`, even though the condition always selects the `1` branch. `var` infers `double` **from the type of the expression**, not from the branch that executes.

**Note:** Java has additional rules for numeric conditional expressions (especially involving constant literals and small types), so do not mechanically apply the addition table to **every** `?:` operator. For complex expressions, inspect the specific typing rules of `?:` or write an explicit type/cast when precision matters.

## 7. Runnable Java 17+ Program

Create a file named **VarNumericInferenceDemo.java**:

~~~java
public final class VarNumericInferenceDemo {
    private static String kind(byte x)   { return "byte"; }
    private static String kind(short x)  { return "short"; }
    private static String kind(char x)   { return "char"; }
    private static String kind(int x)    { return "int"; }
    private static String kind(long x)   { return "long"; }
    private static String kind(float x)  { return "float"; }
    private static String kind(double x) { return "double"; }

    public static void main(String[] args) {
        var integer = 12;
        var bigInteger = 12L;
        var singlePrecision = 1.25f;
        var doublePrecision = 1.25;
        var letter = 'A';

        System.out.println("literals=" + kind(integer)
                + "," + kind(bigInteger)
                + "," + kind(singlePrecision)
                + "," + kind(doublePrecision)
                + "," + kind(letter));

        var bytes = (byte) 10 + (short) 20;
        var afterChar = 'A' + 1;
        var longSum = 2 + 3L;
        var floatSum = 2 + 3.5f;
        var doubleSum = 2L + 3.5;

        System.out.println("smallSum=" + bytes + ":" + kind(bytes));
        System.out.println("charSum=" + afterChar + ":" + kind(afterChar));
        System.out.println("mixedKinds=" + kind(longSum)
                + "," + kind(floatSum) + "," + kind(doubleSum));

        var integerDivision = 7 / 2;
        var realDivision = 7 / 2.0;
        System.out.println("division=" + integerDivision
                + ":" + kind(integerDivision) + ","
                + realDivision + ":" + kind(realDivision));

        var overflow = Integer.MAX_VALUE + 1;
        var exact = (long) Integer.MAX_VALUE + 1;
        var lateCast = (long) (Integer.MAX_VALUE + 1);
        System.out.println("overflow=" + overflow + ":"
                + kind(overflow));
        System.out.println("exact=" + exact + ":" + kind(exact));
        System.out.println("lateCast=" + lateCast + ":" + kind(lateCast));

        var conditional = true ? 1 : 2.0;
        var narrow = (byte) 10;
        System.out.println("conditional=" + conditional + ":"
                + kind(conditional));
        System.out.println("explicitCast=" + narrow + ":"
                + kind(narrow));
    }
}
~~~

Compile and run in the directory containing the file (Bash, PowerShell, or Command Prompt):

~~~bash
javac -encoding UTF-8 VarNumericInferenceDemo.java
java VarNumericInferenceDemo
~~~

**Exact expected output:**

~~~text
literals=int,long,float,double,char
smallSum=30:int
charSum=66:int
mixedKinds=long,float,double
division=3:int,3.5:double
overflow=-2147483648:int
exact=2147483648:long
lateCast=-2147483648:long
conditional=1.0:double
explicitCast=10:byte
~~~

The `kind(...)` overloads allow the program to print **the type chosen by the compiler**, rather than guessing types via `toString()` or how numbers are formatted. From the output, you can inspect the expression's type and its actual value separately.

## 8. Good Habits and Exercises

| Decision to Make | Recommendation |
| --- | --- |
| Want `long` right from the literal | Write the `L` suffix, e.g. `var n = 10L;` |
| Want `float` right from the literal | Use `f`/`F`, e.g. `var f = 1.5f;` |
| Want division with a fractional part | Convert an operand to `double` before the division |
| Want a sum not to overflow `int` | Promote an operand to `long` before addition/multiplication |
| Inferred type is hard to spot from the initializer | Use an explicit type declaration or an intentional cast |
| Comparing floating-point results | Consider precision and rounding rules, do not rely solely on literal appearance |

**Exercise 1.** Predict the types of `var a = 7;`, `var b = 7L;`, `var c = 7f;`, and `var d = 7.0;`. Do all variables have the same arithmetic value? Do they have the same type?

**Exercise 2.** Given `var a = (byte) 5 + (short) 6;`, what is the type of `a` and why is it not `byte`/`short`?

**Exercise 3.** Evaluate `var quotient = 9 / 4;` and `var preciseQuotient = 9.0 / 4;`. What are the types and values of the two variables?

**Exercise 4.** Compare `var a = Integer.MAX_VALUE + 1;`, `var b = (long) Integer.MAX_VALUE + 1;`, and `var c = (long) (Integer.MAX_VALUE + 1);`. Point out exactly where overflow occurs.

**Exercise 5.** Given `var result = false ? 1 : 2.0;`, what is the type of `result`? Does it depend on which branch runs?

### Takeaway

**`var` does not change Java's numeric calculation rules: it only infers the static type from the initializer expression.** Literals default to `int` or `double` without a suffix; operations apply numeric promotion; integer division and overflow happen **before** the value is assigned. When accuracy matters, choose the right literal, cast, and operands **before the operation**, rather than expecting `var` to automatically pick an appropriate type.