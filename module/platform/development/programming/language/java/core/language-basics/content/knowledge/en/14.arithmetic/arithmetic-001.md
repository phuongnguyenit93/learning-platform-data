# Addition, Subtraction, Multiplication, Division, and Remainder in Java

> **Java core — language-basics / Arithmetic**  
> **Requirements:** JDK 17 or later; a standalone Java file with no external libraries.  
> **Objectives:** Correctly use the five arithmetic operators `+`, `-`, `*`, `/`, `%`; predict types and results, distinguish between integer and floating-point division, understand remainder sign, division by zero, and the limits of integers and floating-point numbers.

## 1. The Five Basic Arithmetic Operations

Given `int a = 10, b = 3;`:

| Operator | Meaning | Example | Result |
| --- | --- | --- | ---: |
| `+` | Addition | `a + b` | 13 |
| `-` | Subtraction | `a - b` | 7 |
| `*` | Multiplication | `a * b` | 30 |
| `/` | Division | `a / b` | 3 |
| `%` | Remainder | `a % b` | 1 |

~~~java
int a = 10;
int b = 3;

int sum = a + b;
int difference = a - b;
int product = a * b;
int quotient = a / b;
int remainder = a % b;
~~~

**Important note:** For two integers, `10 / 3` produces **3**, not 3.333...; `10 % 3` produces **1** because `10 = 3 * 3 + 1`. The `%` operator returns the **remainder of the division**, not a percentage.

`+` is also used for **string concatenation**:

~~~java
System.out.println("sum=" + 10 + 3);   // sum=103
System.out.println("sum=" + (10 + 3)); // sum=13
~~~

Parentheses distinguish numeric addition before string concatenation.

## 2. Data Types Determine the Division

When **both operands are integers**, `/` performs **integer division**: the result drops the fractional part toward zero.

~~~java
int integerResult = 7 / 2;           // 3
double stillThree = 7 / 2;           // 3.0: integer division happens before assignment.
double fractional = 7.0 / 2;         // 3.5
double byCast = (double) 7 / 2;      // 3.5
~~~

To keep the fractional part, convert **at least one operand** to `float` or `double` **before the division**. Assigning the result of integer division to a `double` variable **does not restore** the discarded decimal part.

For `byte`, `short`, and `char`, Java performs *binary numeric promotion*: smaller operands are promoted to `int` if there is no `long`/`float`/`double` operand. For example:

~~~java
byte x = 5, y = 2;
var value = x / y; // Type int, value 2.
~~~

General type rule for binary arithmetic operations: if `double` is present → `double`; otherwise, if `float` is present → `float`; otherwise, if `long` is present → `long`; otherwise `int`.

## 3. Remainder `%` and Negative Numbers

For integers and a non-zero divisor, Java guarantees the relationship:

~~~text
a == (a / b) * b + (a % b)
~~~

Integer division takes the integer part toward zero. **The remainder takes the sign of the dividend** (or is 0), and is not always non-negative:

| Expression | Quotient `/` | Remainder `%` |
| --- | ---: | ---: |
| `7 / 3` and `7 % 3` | 2 | 1 |
| `-7 / 3` and `-7 % 3` | -2 | -1 |
| `7 / -3` and `7 % -3` | -2 | 1 |
| `-7 / -3` and `-7 % -3` | 2 | -1 |

If you need a **non-negative modulo with a positive divisor**, such as a circular index from 0 to `size - 1`, you can use `Math.floorMod(a, positiveSize)`:

~~~java
System.out.println(-7 % 3);           // -1
System.out.println(Math.floorMod(-7, 3)); // 2
~~~

You should not replace `floorMod` with `a % b` without considering negative inputs. With floating-point operands, Java also allows `%` (for example, `7.5 % 2.0` equals `1.5`); the result follows **floating-point remainder** semantics, not an always-non-negative modulo rule.

## 4. Operator Precedence and Parentheses

`*`, `/`, and `%` have the **same precedence level**, higher than `+` and `-`. Binary arithmetic operators at the same level associate from left to right:

~~~java
int first = 2 + 3 * 4;      // 14: 2 + (3 * 4)
int second = (2 + 3) * 4;  // 20
int third = 20 / 5 * 2;    // 8: (20 / 5) * 2
int fourth = 20 / (5 * 2); // 2
~~~

Parentheses explicitly express grouping. **Precedence does not mean operand evaluation order**: Java evaluates the operands of ordinary arithmetic operations from left to right, even when the expression is grouped by `*`/`/` precedence.

Avoid cramming multiple increment/decrement operations or side-effecting calls into a long expression. Extract intermediate variables when a calculation needs to be audited.

## 5. Division by Zero, Overflow, and Precision

### Integer Division or Remainder with 0

~~~java
int x = 10;
int zero = 0;
// int q = x / zero; // Throws ArithmeticException at runtime.
// int r = x % zero; // Also throws ArithmeticException.
~~~

When the integer divisor is 0, both `/` and `%` cause an `ArithmeticException`. Check the divisor condition before computing if it comes from untrusted input.

### Floating-Point Numbers Handle 0 Differently

~~~java
double zero = 0.0;
double infinity = 1.0 / zero; // Infinity
double notANumber = zero / zero; // NaN
~~~

These operations use floating-point numbers and **do not throw `ArithmeticException`**. If the application only accepts finite results, use `Double.isFinite(result)`; do not assume every `double` result is an ordinary finite number.

### `int` Overflow and Floating-Point Precision Error

~~~java
int overflow = Integer.MAX_VALUE + 1; // -2147483648
long safe = (long) Integer.MAX_VALUE + 1; // 2147483648
~~~

An overflowing `int` **does not automatically promote to `long`**. You need to widen one operand to a wider type **before the calculation**; for integer addition that must be exact and needs overflow detection, you can use `Math.addExact`.

Binary floating-point numbers are often **approximations**:

~~~java
double value = 0.1 + 0.2; // Prints 0.30000000000000004.
~~~

For monetary amounts requiring exact decimal digits, consider `BigDecimal` created from a string with explicit rounding rules. Do not attempt to fix precision errors by casting to `int` when you need to preserve the fractional part.

## 6. Standalone Runnable Java 17+ Program

Create the file **ArithmeticOperatorsDemo.java**:

~~~java
public final class ArithmeticOperatorsDemo {
    public static void main(String[] args) {
        int a = 10;
        int b = 3;
        System.out.println("add=" + (a + b));
        System.out.println("subtract=" + (a - b));
        System.out.println("multiply=" + (a * b));
        System.out.println("intDivide=" + (a / b));
        System.out.println("intRemainder=" + (a % b));

        System.out.println("realDivide=" + (7.0 / 2));
        double assignedAfterDivision = 7 / 2;
        System.out.println("assignedAfterDivision="
                + assignedAfterDivision);

        System.out.println("negativeDivide=" + (-7 / 3));
        System.out.println("negativeRemainder=" + (-7 % 3));
        System.out.println("negativeDivisorRemainder=" + (7 % -3));
        System.out.println("floorMod=" + Math.floorMod(-7, 3));

        System.out.println("precedence=" + (2 + 3 * 4));
        System.out.println("parentheses=" + ((2 + 3) * 4));
        System.out.println("floatRemainder=" + (7.5 % 2.0));

        int zero = 0;
        try {
            System.out.println("invalid=" + (a / zero));
        } catch (ArithmeticException ex) {
            System.out.println("integerZero=ArithmeticException");
        }
        try {
            System.out.println("invalidRemainder=" + (a % zero));
        } catch (ArithmeticException ex) {
            System.out.println("integerRemainderZero=ArithmeticException");
        }

        double realZero = 0.0;
        System.out.println("floatingZero=" + (1.0 / realZero));
        System.out.println("zeroOverZero=" + (realZero / realZero));

        System.out.println("overflow=" + (Integer.MAX_VALUE + 1));
        System.out.println("widenBeforeAdd="
                + ((long) Integer.MAX_VALUE + 1));
        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("addExactOverflow=ArithmeticException");
        }

        System.out.println("decimalApproximation=" + (0.1 + 0.2));
        System.out.println("stringAdd=" + ("sum=" + 10 + 3));
    }
}
~~~

Compile/run using Bash, PowerShell, or Command Prompt in the directory containing the file:

~~~bash
javac -encoding UTF-8 ArithmeticOperatorsDemo.java
java ArithmeticOperatorsDemo
~~~

**Exact expected output:**

~~~text
add=13
subtract=7
multiply=30
intDivide=3
intRemainder=1
realDivide=3.5
assignedAfterDivision=3.0
negativeDivide=-2
negativeRemainder=-1
negativeDivisorRemainder=1
floorMod=2
precedence=14
parentheses=20
floatRemainder=1.5
integerZero=ArithmeticException
integerRemainderZero=ArithmeticException
floatingZero=Infinity
zeroOverZero=NaN
overflow=-2147483648
widenBeforeAdd=2147483648
addExactOverflow=ArithmeticException
decimalApproximation=0.30000000000000004
stringAdd=sum=103
~~~

**Reading the output:** `intDivide` discards the fractional part; `realDivide` keeps the fractional part because there is a `double` operand; `negativeRemainder` and `floorMod` differ when the dividend is negative; integer division by 0 throws an exception, while floating-point division by 0 can produce `Infinity`/`NaN`; `widenBeforeAdd` prevents overflow before computing.

## 7. Applying This to Real-World Problems

| Scenario | Appropriate Approach |
| --- | --- |
| Computing integer sums or products | Choose `int`/`long` with sufficient range; check for overflow if exactness is mandatory |
| Computing averages or ratios with a fractional part | Convert an operand to `double` before `/` |
| Computing integer quotient and remainder | Use `/` and `%`; document the policy for negative numbers |
| Creating a circular index from negative numbers, positive divisor | Use `Math.floorMod` |
| Divisor may be 0 | Validate input before division/remainder |
| Floating-point number must be finite | Check `Double.isFinite` |
| Currency with exact decimal rules | Consider `BigDecimal` with explicit scale/rounding |

**Exercise 1.** Predict `9 / 4`, `9 % 4`, and `9.0 / 4`; explain the type of each result.

**Exercise 2.** Compute `-9 / 4`, `-9 % 4`, and `Math.floorMod(-9, 4)`. Distinguish between remainder and non-negative modulo.

**Exercise 3.** Given `int a = 7, b = 0;`. Write a check so `a / b` is not executed when `b == 0`.

**Exercise 4.** Why does `long result = Integer.MAX_VALUE + 1;` still hold a negative value? Fix it by converting one operand to `long` before adding.

**Exercise 5.** Predict `2 + 3 * 4` and `(2 + 3) * 4`. Explain what the parentheses change.

### Key Takeaways

**`+`, `-`, `*`, `/`, `%` are the five basic arithmetic operations.** For integers, division discards the fractional part and `%` takes the remainder with the sign of the dividend. Operand types determine the operation's type; operator precedence and parentheses determine grouping. Keep **0 in the divisor, integer overflow, and floating-point precision** in mind to avoid unexpected results.