# Integer Division by Zero Causes ArithmeticException — Java 17+

## 1. The Phenomenon to Understand

In Java, **integer division using the `/` operator with a divisor equal to 0** throws `java.lang.ArithmeticException` when the expression is evaluated.

~~~java
int numerator = 10;
int denominator = 0;

// int result = numerator / denominator;
// If executed: ArithmeticException due to integer division by 0.
~~~

This is a **runtime exception**, not a special integer result like `Infinity`. There is no `int` or `long` value that represents the quotient of integer division by 0.

A controlled handling example:

~~~java
int numerator = 10;
int denominator = 0;

try {
    int quotient = numerator / denominator;
    System.out.println(quotient);
} catch (ArithmeticException ex) {
    System.out.println("Cannot divide integers by zero");
}
~~~

**Expected output:**

~~~text
Cannot divide integers by zero
~~~

**Main takeaway:** you must **ensure the divisor is non-zero before dividing**, or have an explicit error-handling contract. `try/catch` can handle the exception, but it **does not make division by 0 a valid calculation**.

## 2. Which Integer Types Are Subject to This Rule?

In Java 17+, division uses the operand types after *binary numeric promotion* rules. For integer types, when the divisor is 0, both `/` and `%` throw `ArithmeticException`.

| Case | Expression Type | Divisor Equal to 0 | Result |
|---|---|---|---|
| `int / int` | `int` | `10 / 0` | `ArithmeticException` |
| `long / long` | `long` | `10L / 0L` | `ArithmeticException` |
| `byte / byte` | `int` | Two `byte`s, divisor equal to 0 | `ArithmeticException` |
| `short / short` | `int` | Two `short`s, divisor equal to 0 | `ArithmeticException` |
| `char / int` | `int` | `int` divisor equal to 0 | `ArithmeticException` |
| `int % int` | `int` | `10 % 0` | `ArithmeticException` |
| `long % long` | `long` | `10L % 0L` | `ArithmeticException` |

Valid example when the divisor is non-zero:

~~~java
byte a = 9;
byte b = 2;

int quotient = a / b; // byte is promoted to int during division
int remainder = a % b;

System.out.println(quotient);  // 4
System.out.println(remainder); // 1
~~~

**Do not confuse the causes:** if the compiler rejects `byte result = a / b;`, that is an issue of **converting `int` back to `byte`**. If `a / b` executes with `b == 0`, that is an issue of **integer division by 0**.

## 3. Remainder `%` Also Rejects a Zero Divisor

Many people only check `/` and overlook `%`:

~~~java
int count = 10;
int groupSize = 0;

// int quotient = count / groupSize;  // Throws ArithmeticException
// int remainder = count % groupSize; // Also throws ArithmeticException
~~~

With a non-zero divisor, the two operations are linked via Java's quotient and remainder rule. For example:

~~~java
System.out.println(10 / 3); // 3
System.out.println(10 % 3); // 1
~~~

However, neither quotient nor remainder is **defined as a normal integer value when the divisor is 0**.

A system splitting data into batches may need both `items / batchSize` and `items % batchSize`. **Validate `batchSize > 0` once at the boundary** before both operations; do not wait for an exception to happen mid-way after other state has already been updated.

## 4. Completely Different from Floating-Point Division

If at least one operand is `float` or `double`, division uses floating-point arithmetic. Dividing by zero in floating-point can return **Infinity**, **-Infinity**, or **NaN**, and does not throw `ArithmeticException` just because the divisor is 0.

~~~java
System.out.println(10.0 / 0.0);  // Infinity
System.out.println(-10.0 / 0.0); // -Infinity
System.out.println(0.0 / 0.0);   // NaN
~~~

Comparison:

| Expression | Rule | Result |
|---|---|---|
| `10 / 2` | Integer division | `5` |
| `10 / 0` | Integer division | `ArithmeticException` |
| `10L / 0L` | `long` division | `ArithmeticException` |
| `10.0 / 2.0` | `double` division | `5.0` |
| `10.0 / 0.0` | `double` division | `Infinity` |
| `-10.0 / 0.0` | `double` division | `-Infinity` |
| `0.0 / 0.0` | `double` division | `NaN` |

**Do not mechanically "fix" integer division by 0 by casting to `double`.** An Infinity or NaN value can severely corrupt downstream results if business logic requires finite values.

If the result must be finite, check the input divisor and after the calculation check `Double.isFinite(result)` according to your application contract.

## 5. Checking the Divisor Before Performing Division

The most readable approach is a **guard clause**:

~~~java
static int divideNonZero(int numerator, int denominator) {
    if (denominator == 0) {
        throw new IllegalArgumentException("denominator must not be zero");
    }
    return numerator / denominator;
}
~~~

Here `IllegalArgumentException` is an **API design decision** to report invalid input. If you omit the check and perform the division, Java throws `ArithmeticException` on its own.

The two cases have different contracts:

- **Invalid argument:** proactively throw `IllegalArgumentException`, letting callers know the input was rejected.
- **Operation encounters an illegal arithmetic condition:** let `ArithmeticException` be thrown, or catch the exception if there is a recovery policy.

What matters is **consistency** and documenting for callers what they need to handle.

### Example Without an Exception: Execute Only When Valid

~~~java
int numerator = 10;
int denominator = 0;

if (denominator != 0) {
    int quotient = numerator / denominator;
    System.out.println(quotient);
} else {
    System.out.println("No valid quotient");
}
~~~

**Expected output:**

~~~text
No valid quotient
~~~

There is no "default quotient" that the language decides for you. If the application wants to return a fallback value, you must **explicitly define** when the fallback is used and distinguish it from an actual computed result.

## 6. Do Not Use `0` as a Fallback Quotient When 0 Is Valid Data

An API like the following easily causes business bugs:

~~~java
static int unsafeFallback(int a, int b) {
    return b == 0 ? 0 : a / b;
}
~~~

For `1 / 2`, the **actual** integer quotient is also 0. Therefore the caller cannot distinguish:

- `0` from the valid division `1 / 2`;
- `0` from the invalid division `1 / 0` silently replaced.

If having no quotient is a normal situation, you can use `OptionalInt`:

~~~java
static java.util.OptionalInt tryDivide(int a, int b) {
    return b == 0
            ? java.util.OptionalInt.empty()
            : java.util.OptionalInt.of(a / b);
}
~~~

Usage:

~~~java
System.out.println(tryDivide(1, 2).orElse(-1)); // 0
System.out.println(tryDivide(1, 0).isEmpty());  // true
~~~

`OptionalInt.empty()` expresses **no result**, unlike `OptionalInt.of(0)` which represents a valid quotient of 0.

**Note:** the `tryDivide` method above handles a zero divisor, but does not check for `Integer.MIN_VALUE / -1` quotient overflow. If business logic requires an exact mathematical result within the int range, add a check as shown below.

## 7. Quotient Overflow Is Different from Division by 0

The case `Integer.MIN_VALUE / -1` returns `-2147483648` without **throwing an exception**, even though the mathematical quotient `2147483648` lies outside the `int` range. A guard checking only `b == 0` **does not guarantee** the quotient is always exact.

~~~java
static int divideExactInt(int a, int b) {
    if (b == 0) throw new IllegalArgumentException("zero denominator");
    if (a == Integer.MIN_VALUE && b == -1)
        throw new ArithmeticException("int quotient overflow");
    return a / b;
}
~~~

This is a business policy that separates **invalid divisor** from **out-of-range quotient**. The overflow lesson covers `Math.*Exact` and `BigInteger` in general; this lesson focuses on the error contract when dividing.

## 8. `Math.floorDiv` and `Math.floorMod` Also Require a Non-Zero Divisor

Java provides the methods:

~~~java
System.out.println(Math.floorDiv(-7, 2)); // -4
System.out.println(Math.floorMod(-7, 2)); // 1
~~~

They differ from `/` and `%` in quotient/remainder rules for negative numbers. However, **neither method allows integer division by 0**:

~~~java
int divisor = 0;
// Math.floorDiv(7, divisor); // ArithmeticException
// Math.floorMod(7, divisor); // ArithmeticException
~~~

`Math.floorDiv` is not a "zero-safe version" of `/`. If using `floorDiv` for timestamp handling, grid partitioning, or group indexing, you must still validate the input divisor.

## 9. Short-Circuiting Protects an Integer Division Expression

The logical operator `&&` evaluates its right-hand side only if the left-hand side is `true`. We can take advantage of that:

~~~java
int denominator = 0;
boolean largeQuotient = (denominator != 0)
        && (10 / denominator > 3);

System.out.println(largeQuotient); // false, division is not executed
~~~

A false left-hand side makes Java **skip** the expression `10 / denominator > 3`, so no division by 0 occurs.

Similarly, `||` can skip the right-hand side when the left-hand side is `true`:

~~~java
boolean invalidOrLarge = (denominator == 0)
        || (10 / denominator > 3);

System.out.println(invalidOrLarge); // true, division is not executed
~~~

**Do not confuse `&&` with `&`, or `||` with `|` on booleans:** the `&` and `|` operators **evaluate both operands**. Changing `&&` to `&` in the guard example can cause the division to execute and throw an error.

If logic is critical or has multiple operations, separating into an explicit `if` is usually easier to read than a nested boolean expression.

## 10. Wrapper `Integer` Can Throw a Different Error Before Division

Java allows using wrappers via *auto-unboxing*:

~~~java
Integer boxedNumerator = 10;
Integer boxedDenominator = 2;

System.out.println(boxedNumerator / boxedDenominator); // 5
~~~

But if the divisor is `null`:

~~~java
Integer boxedDenominator = null;
// int value = 10 / boxedDenominator;
// Runtime: NullPointerException when unboxing null.
~~~

This is a **`NullPointerException`**, not `ArithmeticException`. Therefore, distinguish:

| Divisor Value | When Computing `10 / boxedDenominator` |
|---|---|
| `Integer.valueOf(2)` | Returns `5` |
| `Integer.valueOf(0)` | Unboxes to 0 then throws `ArithmeticException` |
| `null` | Throws `NullPointerException` during unboxing |

A simple input-handling policy:

~~~java
static int divideNullable(int numerator, Integer denominator) {
    if (denominator == null) {
        throw new IllegalArgumentException("denominator is missing");
    }
    if (denominator == 0) {
        throw new IllegalArgumentException("denominator must not be zero");
    }
    return numerator / denominator;
}
~~~

After the guards, the compiler still auto-unboxes the wrapper when dividing. But you have clearly separated **missing data** from **value 0**.

## 11. When an Exception Occurs, Prior Side Effects Do Not Automatically Roll Back

Java evaluates parts of an expression in the language-specified order. Division by 0 can make execution **stop mid-way**:

~~~java
int count = 0;
int denominator = 0;

try {
    int value = (++count) / denominator;
    System.out.println(value);
} catch (ArithmeticException ex) {
    System.out.println("counter after failure=" + count);
}
~~~

**Expected output:**

~~~text
counter after failure=1
~~~

`++count` already incremented the counter before division encountered the 0 divisor. `catch` **does not restore** `count` to 0.

For critical data, **validate all relevant inputs before making state changes**, or use an appropriate transaction/rollback mechanism. `try/catch` only controls exception handling flow; it does not automatically turn a group of operations into an *atomic transaction*.

## 12. Choosing Handling: Pre-Check, Throw Exception, or Return Status?

| Business Requirement | Usually Appropriate Approach |
|---|---|
| Divisor must always be non-zero | Check `b != 0` at the boundary; reject invalid input |
| This is a programming bug with no recovery path | Let the exception propagate to the layer responsible for handling it |
| User may enter an invalid divisor | Validate, show a meaningful error, and let them re-enter |
| "No result" is a valid state | `OptionalInt` or a status-bearing result type |
| Just need Java integer division | `a / b`, after ensuring `b != 0` |
| Need `int` quotient that must not overflow | Also check `a == MIN_VALUE && b == -1` |
| Want floating-point division | Choose `double`/`float` operands; still check finiteness when needed |
| Want division with floor semantics | `Math.floorDiv` and validate non-zero divisor |

**Do not swallow an exception and silently return 0** unless the application has a clear, documented, and tested fallback policy.

## 13. Complete Java 17 Program — Runnable

Save the file with the exact name **`IntegerDivideByZeroDemo.java`**:

~~~java
import java.math.BigInteger;
import java.util.OptionalInt;

public final class IntegerDivideByZeroDemo {
    private IntegerDivideByZeroDemo() {}

    static int divideNonZero(int a, int b) {
        if (b == 0) {
            throw new IllegalArgumentException("denominator must not be zero");
        }
        return a / b;
    }

    static int divideExactInt(int a, int b) {
        if (b == 0) {
            throw new IllegalArgumentException("zero denominator");
        }
        if (a == Integer.MIN_VALUE && b == -1) {
            throw new ArithmeticException("int quotient overflow");
        }
        return a / b;
    }

    static OptionalInt tryDivide(int a, int b) {
        return b == 0 ? OptionalInt.empty() : OptionalInt.of(a / b);
    }

    static int divideNullable(int a, Integer b) {
        if (b == null) {
            throw new IllegalArgumentException("denominator is missing");
        }
        if (b == 0) {
            throw new IllegalArgumentException("denominator must not be zero");
        }
        return a / b;
    }

    public static void main(String[] args) {
        System.out.println("valid quotient=" + (10 / 3));
        System.out.println("valid remainder=" + (10 % 3));
        System.out.println("long quotient=" + (10L / 2L));

        byte small = 9;
        byte two = 2;
        System.out.println("byte division=" + (small / two));

        int zero = 0;
        try {
            int result = 10 / zero;
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("int / zero=ArithmeticException");
        }

        try {
            int result = 10 % zero;
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("int % zero=ArithmeticException");
        }

        try {
            long result = 10L / (long) zero;
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("long / zero=ArithmeticException");
        }

        try {
            System.out.println(Math.floorDiv(10, zero));
        } catch (ArithmeticException ex) {
            System.out.println("floorDiv zero=ArithmeticException");
        }

        System.out.println("floating positive=" + (10.0 / 0.0));
        System.out.println("floating negative=" + (-10.0 / 0.0));
        System.out.println("floating undefined=" + (0.0 / 0.0));

        System.out.println("guarded normal=" + divideNonZero(10, 2));
        try {
            divideNonZero(10, zero);
        } catch (IllegalArgumentException ex) {
            System.out.println("guarded invalid=" + ex.getMessage());
        }

        System.out.println("optional valid zero="
                + tryDivide(1, 2).orElse(-1));
        System.out.println("optional no result=" + tryDivide(1, 0).isEmpty());

        boolean safeAnd = (zero != 0) && (10 / zero > 2);
        boolean safeOr = (zero == 0) || (10 / zero > 2);
        System.out.println("short circuit and=" + safeAnd);
        System.out.println("short circuit or=" + safeOr);

        Integer boxedZero = Integer.valueOf(0);
        Integer missing = null;
        try {
            int result = 10 / boxedZero;
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("boxed zero=ArithmeticException");
        }
        try {
            int result = 10 / missing;
            System.out.println(result);
        } catch (NullPointerException ex) {
            System.out.println("boxed null=NullPointerException");
        }
        try {
            divideNullable(10, missing);
        } catch (IllegalArgumentException ex) {
            System.out.println("nullable rejected=" + ex.getMessage());
        }

        System.out.println("min / -1=" + (Integer.MIN_VALUE / -1));
        System.out.println("min widened="
                + (((long) Integer.MIN_VALUE) / -1));
        try {
            divideExactInt(Integer.MIN_VALUE, -1);
        } catch (ArithmeticException ex) {
            System.out.println("checked overflow=" + ex.getMessage());
        }
        BigInteger exact = BigInteger.valueOf(Long.MIN_VALUE)
                .divide(BigInteger.valueOf(-1));
        System.out.println("big exact=" + exact);

        int count = 0;
        try {
            int result = (++count) / zero;
            System.out.println(result);
        } catch (ArithmeticException ex) {
            System.out.println("counter after failure=" + count);
        }
    }
}
~~~

**Requirements:** JDK 17+; terminal opened in the directory containing the file. No Maven/Gradle or libraries outside the JDK needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 IntegerDivideByZeroDemo.java
java -cp . IntegerDivideByZeroDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\IntegerDivideByZeroDemo.java
java -cp . IntegerDivideByZeroDemo
~~~

**Exact expected output:**

~~~text
valid quotient=3
valid remainder=1
long quotient=5
byte division=4
int / zero=ArithmeticException
int % zero=ArithmeticException
long / zero=ArithmeticException
floorDiv zero=ArithmeticException
floating positive=Infinity
floating negative=-Infinity
floating undefined=NaN
guarded normal=5
guarded invalid=denominator must not be zero
optional valid zero=0
optional no result=true
short circuit and=false
short circuit or=true
boxed zero=ArithmeticException
boxed null=NullPointerException
nullable rejected=denominator is missing
min / -1=-2147483648
min widened=2147483648
checked overflow=int quotient overflow
big exact=9223372036854775808
counter after failure=1
~~~

### Explaining the Key Results

1. `10 / 3` and `10 % 3` work normally because the divisor is 3, resulting in quotient 3 and remainder 1.
2. `byte` is promoted to `int` when dividing; `9 / 2` gives 4.
3. `int / zero`, `int % zero`, `long / zero`, and `Math.floorDiv` all raise `ArithmeticException`.
4. `double` divided by 0 returns Infinity/-Infinity/NaN; that semantics **differs from integer types**.
5. The guard proactively throws `IllegalArgumentException` with a specific message.
6. `OptionalInt` separates a valid integer quotient of 0 from the no-quotient case.
7. `&&` and `||` avoid evaluating the division thanks to short-circuiting.
8. Wrapper `Integer.valueOf(0)` causes divide-by-zero error; `null` wrapper causes unboxing error before dividing.
9. `MIN_VALUE / -1` is an **overflow case that does not throw automatically**; use a separate check or a sufficiently wide type.
10. The counter increments before division fails; `catch` does not roll back earlier side effects.

## 14. Common Mistakes

| Misconception / Error | Why Is It Wrong? | How to Handle It |
|---|---|---|
| `10 / 0` returns Infinity | That is the floating-point rule, not integer | Check that divisor is non-zero |
| `10 % 0` is still valid | Integer remainder also disallows divisor 0 | Validate before both `/` and `%` |
| `long a = 10L / 0L` is safe because `long` is wide | Wider range does not allow division by 0 | Same exception rule |
| `Math.floorDiv(10, 0)` is safe | `floorDiv` does not support divisor 0 | Validate input |
| `10.0 / 0.0` is the fix for integer division | An Infinity result can violate business rules | Use floating-point only when it fits the model |
| `int result = 10 / boxed;` with null boxed | Unboxing null causes `NullPointerException` | Check null separately |
| Catching every `RuntimeException` and returning 0 | Hides other bugs and blurs cases | Catch the specific type or validate |
| Using 0 to represent both quotient 0 and failed division | Loses the "no result" state | `OptionalInt` / explicit error model |
| Using `&&` as if it were `&` | `&` evaluates both sides | Use `&&` when a guard is needed |
| Assuming no exception always means exact quotient | `MIN_VALUE/-1` overflows specially | Check for overflow |
| Catching an exception will undo all side effects | `catch` does not roll back | Validate beforehand or use transactions/rollback |
| Batch splitting without checking `batchSize` | Batch size 0 will cause an error | Require `batchSize > 0` |

## 15. Exercises and Answers

### Exercise A — Both Operators Fail When Divisor Is 0

~~~java
int numerator = 8;
int denominator = 0;
// System.out.println(numerator / denominator);
// System.out.println(numerator % denominator);
~~~

**Answer:** if each line runs, both integer division and integer remainder throw `ArithmeticException`. Perform `denominator != 0` beforehand.

### Exercise B — Guarding with Logic

~~~java
int b = 0;
boolean condition = (b != 0) && (12 / b > 2);
System.out.println(condition);
~~~

**Answer:** `false`; Java does not evaluate the right-hand side of `&&` because the left-hand side is false.

### Exercise C — Should You Automatically Return 0?

Suppose an API returns an `int` result of 0 when the divisor is 0. Why is that dangerous?

**Answer:** `1 / 2` also has a valid quotient of 0. Callers cannot distinguish a valid result from an error. You can reject the input with an exception or return a status-bearing type like `OptionalInt`.

### Exercise D — Nullable Wrapper

~~~java
Integer b = null;
// int result = 12 / b;
~~~

**Answer:** if executed, a `NullPointerException` occurs due to auto-unboxing `null`, not an `ArithmeticException` from division by 0.

### Exercise E — int Overflow

~~~java
System.out.println(Integer.MIN_VALUE / -1);
~~~

**Answer:** `-2147483648`, **no** error thrown. If overflow is unacceptable, check this case and use a wider type when needed.

### Exercise F — Distinguishing Floating-Point

~~~java
System.out.println(5.0 / 0.0);
System.out.println(0.0 / 0.0);
~~~

**Answer:**

~~~text
Infinity
NaN
~~~

They are not valid integer values.

## 16. Closing Checklist

- [ ] Know that `int` and `long` division by 0 throws `ArithmeticException`.
- [ ] Know that `%` with a zero divisor also throws `ArithmeticException`.
- [ ] Understand that `byte`, `short`, and `char` are usually promoted to `int` when dividing.
- [ ] Distinguish integer division by 0 from floating-point returning Infinity/NaN.
- [ ] Know how to use `if (denominator == 0)` or a guard clause to reject input.
- [ ] Do not use `0` as an ambiguous fallback value if 0 is a valid result.
- [ ] Know `OptionalInt` when an absent result is normal.
- [ ] Know `Math.floorDiv`/`Math.floorMod` also do not support a zero divisor.
- [ ] Use `&&`/`||` properly to avoid evaluating an invalid division.
- [ ] Distinguish a 0 wrapper causing `ArithmeticException` from a null wrapper causing `NullPointerException`.
- [ ] Understand the special overflow exception `MIN_VALUE / -1`.
- [ ] Do not assume `catch` undoes side effects that already occurred.
- [ ] Run `IntegerDivideByZeroDemo.java` on JDK 17+ and compare against exact expected output.

**Conclusion:** In Java 17+, **integer division or remainder with a zero divisor** causes `ArithmeticException` at evaluation time; it is not Infinity. Safe design is to **validate input early**, distinguish missing data from zero, choose an explicit error/no-result contract, and avoid masking invalid cases with ambiguous fallback values.