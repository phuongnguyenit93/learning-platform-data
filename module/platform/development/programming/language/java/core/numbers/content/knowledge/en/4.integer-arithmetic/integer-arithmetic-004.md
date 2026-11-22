# Integer Division or Remainder by Zero in Java

## 1. Core Rule

For integer types in Java, **a divisor (right-hand operand) equal to `0` in division `/` or remainder `%` always throws `ArithmeticException` when the operation executes**. Java does not produce a valid quotient or remainder for these expressions.

```java
int a = 12;
int zero = 0;

// Both operations below throw ArithmeticException at runtime:
// int quotient = a / zero;
// int remainder = a % zero;
```

Immediate points to remember:

- `12 / 0` does **not** return infinity for integers; the operation fails.
- `12 % 0` does **not** return `0` or `12`; the operation also fails.
- `0 / 0` and `0 % 0` **both** throw an error. A dividend of `0` does not save the operation.
- Check the **right-hand operand** (`divisor == 0`), not just the dividend.
- `ArithmeticException` is an **unchecked exception** (a subclass of `RuntimeException`). Declaring `throws` or `catch` is not mandatory, but the program must define how to handle inputs that might be `0`.

This rule applies to Java **integer arithmetic**, including division/remainder performed as `int` or `long` after *numeric promotion*. Do not infer integer behavior from the behavior of `double`/`float`.

## 2. Why Are Division and Remainder by Zero Undefined?

For integers `a` and `b != 0`, Java defines the integer quotient `q = a / b` via division truncated toward **0**. The remainder `r = a % b` accompanies the quotient and satisfies the identity (in Java integer arithmetic):

```text
a = b * q + r
q = a / b
r = a % b
```

For example:

```java
System.out.println(17 / 5);    // 3
System.out.println(17 % 5);    // 2
System.out.println(-17 / 5);   // -3
System.out.println(-17 % 5);   // -2
```

Here `17 = 5 * 3 + 2`, and `-17 = 5 * (-3) + (-2)`. With `%` on integers, a non-zero remainder has the same sign as the **dividend** (numerator), not necessarily positive.

If `b = 0`, no unique integer quotient can be determined under division semantics. The formula `a = b * q + r` no longer provides a meaningful division operation; Java **explicitly rejects both `/` and `%` when the divisor is zero**. Therefore, computing `a % 0` is not a "safer" way to handle `a / 0`.

You do not need to memorize a fixed text error message: what you can rely on is the **exception type `java.lang.ArithmeticException`**; the exact message string is implementation-defined.

## 3. When Does the Error Occur and How Does It Affect Program Flow?

The exception occurs **when the JVM executes an integer division/remainder whose actual divisor evaluates to `0`**. For example, a parameter or intermediate calculation might become `0`:

```java
static int averagePerGroup(int total, int groups) {
    return total / groups; // groups == 0 -> ArithmeticException.
}
```

If the exception is not caught at an appropriate place, normal execution flow is interrupted and the exception propagates up the call stack. If unhandled, the execution thread terminates with an error; the application does not receive a "default quotient" value.

An operation that **is not executed** cannot throw an exception from itself. For example:

```java
int divisor = 0;
if (divisor != 0) {
    int q = 10 / divisor; // Not executed in the current case.
}
```

A short-circuit condition protects the operation if placed in the right order:

```java
int divisor = 0;
boolean valid = divisor != 0 && 100 / divisor > 5;
// valid == false; the 100 / divisor side is skipped.
```

Here `&&` evaluates the right-hand side only when the left-hand side is `true`. If replaced with `&` on two boolean operands, **both sides** are evaluated and the division can throw an exception. Also avoid reversing the order to `100 / divisor > 5 && divisor != 0`: the division already runs before the divisor is checked.

Conditional expressions are only safe if **the divisor checked is the exact same divisor used in the operation** and cannot change unexpectedly between check and use. For local numeric values, capture the value to be used into a single variable if the original read comes from a mutable source.

## 4. Which Integer Types Are Subject to This Rule?

Integer operations on `byte`, `short`, `char`, and `int` undergo *numeric promotion* to `int`; if a `long` operand is present (with no floating-point operands), the operation runs in `long`. Both `int` and `long` division/remainder throw `ArithmeticException` if the divisor is `0`.

```java
byte a = 12;
byte b = 0;
long big = 12L;
long longZero = 0L;

// int x = a / b;       // ArithmeticException at runtime (int division).
// int y = a % b;       // ArithmeticException at runtime (int remainder).
// long z = big / longZero; // ArithmeticException (long division).
// long r = big % longZero; // ArithmeticException (long remainder).
```

Compound assignment operators are not exempt either:

```java
int count = 10;
int zero = 0;

// count /= zero; // ArithmeticException; count does not receive a valid quotient.
// count %= zero; // ArithmeticException; no valid remainder is produced.
```

In addition to operators, APIs performing integer division/remainder such as `Math.floorDiv(a, b)`, `Math.floorMod(a, b)`, `Integer.divideUnsigned(a, b)`, and `Integer.remainderUnsigned(a, b)` also reject a zero divisor. With `BigInteger`, `divide(BigInteger.ZERO)` and `remainder(BigInteger.ZERO)` likewise throw `ArithmeticException`. **A wider bit width or arbitrary-precision integer capability does not make division by zero valid.**

A small but useful note: `Math.floorDiv`/`Math.floorMod` have different rounding and sign rules from regular integer division for some negative operands, but the non-zero divisor requirement **still holds**.

## 5. Distinguishing Integer vs. Floating-Point Division by Zero

With the same `/` or `%` symbol, behavior differs when the expression is evaluated as `double` or `float`. For Java floating-point arithmetic following IEEE 754:

| Expression | Operation type | Result |
| --- | --- | --- |
| `10 / 0` | Integer (`int`) | `ArithmeticException` at runtime |
| `10L / 0L` | Integer (`long`) | `ArithmeticException` at runtime |
| `10 % 0` | Integer remainder | `ArithmeticException` at runtime |
| `0 / 0` | Integer | `ArithmeticException` at runtime |
| `10.0 / 0` | Floating-point (`double`) | `Infinity` |
| `-10.0 / 0.0` | Floating-point | `-Infinity` |
| `0.0 / 0.0` | Floating-point | `NaN` |
| `10.0 % 0` | Floating-point remainder | `NaN` |

In `10.0 / 0`, the operand `10.0` has type `double`, so `0` is promoted to `double` and the division follows floating-point semantics. Conversely, `10 / 0` has only integer operands and does not automatically switch to floating-point division.

```java
System.out.println(Double.isInfinite(10.0 / 0)); // true
System.out.println(Double.isNaN(0.0 / 0.0));     // true
System.out.println(Double.isNaN(10.0 % 0));      // true
```

**Do not convert to `double` solely to avoid the exception** if the problem requires exact integers. `Infinity` or `NaN` can propagate into subsequent calculations and corrupt business meaning. If the rule is "the number of groups must be greater than 0", enforce that rule instead of changing types.

## 6. Handling It Properly in Applications

### 6.1. Validate the Divisor Before Computing

If `0` is **invalid input**, reject it early with a clear message:

```java
static int dividePositiveGroups(int total, int groups) {
    if (groups <= 0) {
        throw new IllegalArgumentException("groups must be positive");
    }
    return total / groups;
}
```

Here we check `<= 0` because **business logic** requires a positive group count; strictly to prevent a language-level division-by-zero error, only `groups == 0` is needed. Negative numbers are valid divisors in Java integer division, though they may be invalid in a group-counting problem.

If both quotient and remainder are needed, compute them only after confirming the divisor:

```java
static String describeDivision(int total, int groups) {
    if (groups == 0) {
        return "Cannot divide when group count is 0";
    }
    int quotient = total / groups;
    int remainder = total % groups;
    return "Quotient=" + quotient + ", remainder=" + remainder;
}
```

The return value in the `groups == 0` case is an **application design decision**, not a default arithmetic result from Java. Other systems may choose to report an error, prompt for re-entry, or use a return type representing an absent calculation result.

### 6.2. Catch the Exception at an Appropriate Handling Boundary

When the divisor may come from external data or another component, you can catch `ArithmeticException` at a point where the application knows how to report and recover:

```java
int total = 10;
int groups = 0;
try {
    int perGroup = total / groups;
    System.out.println(perGroup);
} catch (ArithmeticException ex) {
    System.out.println("Cannot divide by zero");
}
```

If early input validation is possible, pre-checking is usually clearer to read. **Avoid catching `ArithmeticException` too broadly and ignoring it**, because other arithmetic errors exist and programming bugs could be masked. When no valid recovery is possible, letting the exception propagate to an error-handling layer is preferable to inventing a fake value like `0`.

### 6.3. Avoid Hazards with Dynamically Computed Divisors

A divisor can arise from an intermediate calculation:

```java
int users = 8;
int activeUsers = 8;
int inactiveUsers = users - activeUsers; // 0

if (inactiveUsers != 0) {
    int average = 100 / inactiveUsers;
    System.out.println(average);
}
```

When the data source can change concurrently, read the divisor once, validate it, and then use **that exact value**:

```java
int currentDivisor = getCurrentDivisor();
if (currentDivisor != 0) {
    int result = 100 / currentDivisor;
    System.out.println(result);
}
```

`getCurrentDivisor()` in the second snippet is an **application-defined illustrative function**, not a standard Java API. Calling the data source a second time inside the division could read a value that has changed to `0`. In concurrent programs, synchronization is also required when related data must remain consistent across an operation.

## 7. Standalone Java 17+ Example and Exact Output

Create a file **`IntegerDivisionByZeroDemo.java`**:

```java
public class IntegerDivisionByZeroDemo {
    public static void main(String[] args) {
        int numerator = 10;
        int validDivisor = 3;
        int zero = 0;

        System.out.println("10 / 3 = " + (numerator / validDivisor));
        System.out.println("10 % 3 = " + (numerator % validDivisor));

        try {
            int quotient = numerator / zero;
            System.out.println(quotient);
        } catch (ArithmeticException ex) {
            System.out.println("10 / 0 -> ArithmeticException");
        }

        try {
            int remainder = numerator % zero;
            System.out.println(remainder);
        } catch (ArithmeticException ex) {
            System.out.println("10 % 0 -> ArithmeticException");
        }

        try {
            int zeroOverZero = zero / zero;
            System.out.println(zeroOverZero);
        } catch (ArithmeticException ex) {
            System.out.println("0 / 0 -> ArithmeticException");
        }

        boolean canDivide = zero != 0;
        System.out.println("valid divisor? " + canDivide);
        System.out.println("floating / zero infinite = "
                + Double.isInfinite(10.0 / zero));
        System.out.println("floating % zero NaN = "
                + Double.isNaN(10.0 % zero));
    }
}
```

Compile and run:

```bash
javac IntegerDivisionByZeroDemo.java
java IntegerDivisionByZeroDemo
```

Output:

```text
10 / 3 = 3
10 % 3 = 1
10 / 0 -> ArithmeticException
10 % 0 -> ArithmeticException
0 / 0 -> ArithmeticException
valid divisor? false
floating / zero infinite = true
floating % zero NaN = true
```

Because the program **catches each exception individually**, the remaining examples continue to execute. This is purely an example illustrating the difference between integer and floating-point operations. In business code, validating data ranges and reporting errors per actual requirements is usually clearer.

## 8. Common Misconceptions

1. **"Only division by 0 fails; remainder by 0 returns the dividend."** False: for integers, both `/ 0` and `% 0` throw `ArithmeticException`.
2. **"If the dividend is 0, `0 / 0` will equal 0."** False: the divisor is still `0`, so the division is invalid.
3. **"Java automatically returns `Infinity` on a divide-by-zero error."** `Infinity`/`NaN` behavior applies only to floating-point operations; integer division throws an exception.
4. **"Changing the receiving variable to `double` is enough."** False: `double x = 10 / zero;` still evaluates `10 / zero` as `int` before assigning, so the exception still occurs. There must be a floating-point operand **inside the expression** to use floating-point semantics.
5. **"Checking `divisor != 0` on the right side of `&&` is safe."** False if the division comes first; evaluation order determines whether the division runs.
6. **"`Math.floorMod(a, 0)` or `BigInteger.divide(BigInteger.ZERO)` handles it automatically."** False: integer division/remainder APIs also reject a zero divisor.
7. **"Catching any `ArithmeticException` and returning `0` solves it."** There is no default quotient/remainder of `0`. Returning a fallback value must be an explicit system rule.

**Key Takeaway:** For integer operations in Java, verify that **the divisor is non-zero before executing both `/` and `%`**. If a zero divisor is invalid data, handle it as an input error or a no-result condition. Floating-point numbers have `Infinity`/`NaN` under different rules, which do not change the invalidity of integer division by zero.

**Specifications:** [JLS §15.17.2 — Division Operator /](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.17.2), [JLS §15.17.3 — Remainder Operator %](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.17.3), [Java SE 21 — ArithmeticException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ArithmeticException.html).
