# Math.pow, Math.sqrt, Math.cbrt, and Choosing the Right Calculation in Java

In Java Core, the three methods **`Math.pow`**, **`Math.sqrt`**, and **`Math.cbrt`** look similar because they all involve exponentiation or roots. However, they are **not completely interchangeable**. The differences lie in **mathematical semantics**, **valid input domains**, **behavior with negative numbers and signed zero**, **`double` limits**, **accuracy**, and the ability to choose a better specialized algorithm.

Example:

```java
double square = Math.pow(3.0, 2.0); // 9.0
double root2 = Math.sqrt(9.0);      // 3.0
double root3 = Math.cbrt(-8.0);     // -2.0

double surprise = Math.pow(-8.0, 1.0 / 3.0);
// surprise is NaN, not -2.0.
```

The snippet above is an **example fragment** that can be placed inside a method. For a negative cube root, `Math.cbrt` clearly knows it is a **real cube root**; `Math.pow` only sees a negative base and a non-integer `double` exponent.

This lesson belongs to the **Math and StrictMath** group: understand how the APIs are designed and choose the right tool before optimizing performance or fixing floating-point inaccuracies.

## 1. API Overview and Return Values

| Operation | Method | Input/Return Types | Meaning |
| --- | --- | --- | --- |
| Arbitrary power | `Math.pow(double a, double b)` | Two `double`s → `double` | Computes `a^b` per floating-point rules |
| Square root | `Math.sqrt(double a)` | `double` → `double` | Non-negative real square root of `a` |
| Cube root | `Math.cbrt(double a)` | `double` → `double` | Real cube root, even for negative `a` |
| 2D distance | `Math.hypot(double x, double y)` | Two `double`s → `double` | Computes `sqrt(x*x+y*y)` while avoiding intermediate overflow/underflow |
| Corresponding functions | `StrictMath.pow/sqrt/cbrt` | Also `double` | Has contracts for result reproducibility as specified by `StrictMath` |

All are **static methods** of the `java.lang.Math` or `java.lang.StrictMath` class; no separate import is needed when called via the class name. For the first three functions, **there are no overloads returning `int` or `long`** for the power or root result. Example:

```java
double answer = Math.sqrt(25);   // 5.0, even though the argument is written as an int literal.
double power = Math.pow(2, 10);  // 1024.0, not type long.
```

These two calls receive `int` literals and automatically **widen** them to `double` before calling the method. Do not rely on writing `Math.pow(2, 10)` to assume the result is an arbitrary exact integer: the return type is always `double`.

## 2. `Math.pow(base, exponent)`: General Exponentiation

`Math.pow(a,b)` represents `a` raised to the power of `b`, where both base and exponent are `double`. For common cases:

```java
double a = Math.pow(2.0, 10.0);  // 1024.0
double b = Math.pow(10.0, -2.0); // 0.01 (binary approximation)
double c = Math.pow(9.0, 0.5);   // 3.0 for this example
double d = Math.pow(-2.0, 3.0);  // -8.0
double e = Math.pow(-2.0, 4.0);  // 16.0
```

The lines above are code fragments used inside a method. Notably, the exponent is **passed and processed as a `double`**, not a "general integer": `Math.pow` does not promise that every integer exponentiation will produce an **exact** integer.

With integer exponents and small integer bases, the result can be represented exactly; with very large numbers, non-integer exponents, or results near the boundary of `double`, the calculation is subject to floating-point rounding rules and limits.

**Do not use `^` as an exponentiation operator in Java.** `2 ^ 3` is a **bitwise XOR** on two integers and gives 1, not 8. To raise to the power of 3, use `Math.pow(2,3)`, repeated multiplication when appropriate, or a custom-designed integer exponentiation method.

## 3. `Math.sqrt(x)`: Square Root and Domain

`Math.sqrt(x)` finds the **non-negative square root** of `x` when `x` is finite and non-negative.

```java
double a = Math.sqrt(9.0);    // 3.0
double b = Math.sqrt(2.0);    // Double closest to square root of 2.
double c = Math.sqrt(0.0);    // +0.0
double d = Math.sqrt(-4.0);   // NaN.
```

For negative numbers other than zero, **no real square root exists**, so `Math.sqrt(-4.0)` returns **`Double.NaN`**. Java does not automatically switch to **complex numbers** nor throw `ArithmeticException`. If an application needs complex square roots, you must use a complex number library and a data type capable of holding real/imaginary parts.

`Math.sqrt` has a **correctly rounded** contract: the result is the `double` value closest to the exact mathematical root under the specified rounding rule. This is a strength of the specialized function; you should not assume `Math.pow(x,0.5)` always has the exact same accuracy guarantees and edge-case behavior.

Pay attention to signed zero:

```java
double negZero = -0.0;
double root = Math.sqrt(negZero);    // -0.0
boolean sameBits = Double.doubleToRawLongBits(root)
        == Double.doubleToRawLongBits(negZero); // true
```

Under IEEE 754, `-0.0` and `+0.0` have different bit patterns even though `-0.0 == +0.0` is `true`. `Math.sqrt(-0.0)` **preserves negative zero**, rather than returning NaN as when the input is `-4.0`.

## 4. `Math.cbrt(x)`: Real Cube Root, Even for Negative Numbers

`Math.cbrt(x)` computes the **real cube root** of `x`. Unlike square roots, a finite negative number still has a real cube root:

```java
double a = Math.cbrt(27.0);  // 3.0
double b = Math.cbrt(-8.0);  // -2.0
double c = Math.cbrt(0.0);   // +0.0
double d = Math.cbrt(-0.0);  // -0.0
```

For example, `(-2)^3 = -8`, so the real cube root of `-8` is `-2`. `Math.cbrt` also **preserves the sign of zero** and behaves with Infinity/NaN according to API rules. It has an accuracy contract **within 1 ULP** along with related semi-monotonicity requirements, unlike `Math.sqrt`'s correctly rounded specification.

Precisely because it supports the negative domain, the specialized `cbrt` function is usually the right choice over `pow(x, 1.0/3.0)` for finding a real cube root, even when `x` is positive: it expresses the exact **mathematical intent** and was designed for that operation.

## 5. Why Is `Math.pow(-8.0, 1.0 / 3.0)` NaN?

In real mathematics, the cube root of -8 is -2. But in Java:

```java
double exponent = 1.0 / 3.0;
double viaPow = Math.pow(-8.0, exponent); // NaN.
double viaCbrt = Math.cbrt(-8.0);        // -2.0.
```

The reason consists of two parts:

1. `1.0 / 3.0` is a `double` **approximation of 1/3**, not an exact fraction with a separate numerator and denominator.
2. With a **finite negative base** and a **finite non-integer exponent**, `Math.pow` by Java's `double` specification returns **NaN**. It does not infer that an exponent close to `1/3` means "take the real cube root and preserve the sign".

Even if you change the code to `Math.pow(-8.0, 0.3333333333333333)`, the result is still NaN because that exponent is not an integer. This is a wrong **API choice**, not a minor decimal printing error.

You should not try to fix it by taking `Math.abs(x)` and always re-attaching a negative sign for **every** real exponent: the right rule also depends on the mathematical nature of the exponent (for example, fractions with even/odd numerators/denominators), domain, and representability. If you want the real cube root, `Math.cbrt` is the appropriate API.

## 6. Squaring, Cubing, and Choosing `pow` vs. Direct Multiplication

For small fixed exponents, explicit multiplication is easy to read and can avoid the cost of calling a general exponentiation method:

```java
double x = 2.5;
double square = x * x;
double cube = x * x * x;
double generic = Math.pow(x, 7.0);
```

However, **do not assume direct multiplication and `Math.pow(x,2.0)` produce identical bit patterns for all inputs**. They can have different special-case rules or rounding/algorithmic differences; in problems requiring bit-for-bit results or a specific numerical standard, test on the actual data domain.

Regarding performance, do not assume "`x*x` is always faster" or "`Math.pow` is always optimized by the CPU" without measuring. The JVM can optimize code differently depending on the environment; when performance matters, benchmark with JMH and representative data.

**More importantly:** with **integers**, using `int * int` can still overflow. Switching to `Math.pow` is not an exact solution; a `double` result only has finite precision.

## 7. Choosing `pow` for Integer Exponents Can Lose Precision

`double` has 53 effective bits of significand, so it **cannot accurately represent every integer larger than `2^53`**. Example:

```java
double n = Math.pow(2.0, 53.0);     // 9007199254740992.0
boolean lost = (n + 1.0 == n);     // true.
```

The mathematical number `2^53 + 1` has no exact `double` representation. When computing `n + 1.0`, the result rounds back to `n` itself. Therefore, you **should not** use `(long) Math.pow(base, exponent)` as an always-exact solution for integer exponentiation:

- If exponentiation produces an integer that cannot be stored accurately in `double`, casting to `long` **cannot recover the lost bits**.
- If the `double` result exceeds the `long` range, conversion from floating-point to integer under Java rules does not behave like exact integer arithmetic; with Infinity and very large values, the cast result can saturate.
- If the exponent is negative, the power value is usually not an integer, so casting easily **truncates the fractional part**.
- If the base is negative with a non-integer real exponent, `pow` may return NaN.

Use `Math.pow` when the data and output have **floating-point** semantics. When you need an absolutely exact integer, choose integer operations with overflow checking or `BigInteger.pow`.

## 8. Exact Integer Exponentiation: `Math.multiplyExact` and `BigInteger.pow`

One approach for `long` is **exponentiation by squaring**, checking for overflow at every multiplication:

```java
static long powExact(long base, int exponent) {
    if (exponent < 0) {
        throw new IllegalArgumentException("negative exponent");
    }
    long result = 1L;
    long factor = base;
    int remaining = exponent;
    while (remaining > 0) {
        if ((remaining & 1) != 0) {
            result = Math.multiplyExact(result, factor);
        }
        remaining >>>= 1;
        if (remaining > 0) {
            factor = Math.multiplyExact(factor, factor);
        }
    }
    return result;
}
```

This is a **method residing in a Java class**, which also appears in the complete program below. The algorithm runs in `O(log exponent)` squaring/multiplication steps, rather than multiplying linearly by the exponent. `Math.multiplyExact` throws `ArithmeticException` when the product falls outside the `long` range.

```java
long valid = powExact(3L, 10); // 59049.
// powExact(2L, 63) throws ArithmeticException because 2^63 > Long.MAX_VALUE.
```

Note that the method intentionally **does not support negative exponents** because the result may be a fraction. Adding `if (remaining > 0)` before the next squaring step avoids an unnecessary multiplication once the algorithm has processed the highest bit; this is important with overflow-checking APIs because an unnecessary intermediate operation could also trigger an exception.

If the output needs to exceed `long`, use:

```java
java.math.BigInteger a = java.math.BigInteger.valueOf(2);
java.math.BigInteger result = a.pow(100); // Exact integer 2^100.
```

`BigInteger.pow(int exponent)` supports **non-negative** exponents, returning an exact integer value within resource limits; it uses no intermediate `double`. Negative exponents are not a `BigInteger` result in general.

## 9. `sqrt` for Checking Perfect Squares

With an `int` or `long`, calling `Math.sqrt(n)` returns a `double`. If the goal is to **display an approximate square root**, this approach makes complete sense.

If the goal is to check whether **`n` is an exact perfect square**, be careful:

```java
long n = 81L;
long root = (long) Math.sqrt(n); // 9 for this example.
boolean square = (root * root == n); // true for n=81.
```

With very large `long` values, the issue gets trickier. A positive `long` might not be exactly representable by `double`, casting the root to `long` might require adjustment, and `root*root` could **overflow** if bounds are not checked. If you truly need to check perfect squares across all `long` boundaries, use a controlled integer square root algorithm or safe division for comparison.

With Java's `Math.sqrt` API, **do not assume** `(long)Math.sqrt(n)` is an exact integer root for every `long`. If the business logic deals with integers and cannot tolerate being off by one unit, define the verification process clearly and test boundaries near `Long.MAX_VALUE`.

## 10. `Math.sqrt` and `Math.pow(x,0.5)` Differ in Intent

Mathematically, for `x >= 0`, `x^0.5` is the square root. However, in Java:

```java
double a = Math.sqrt(9.0);     // 3.0.
double b = Math.pow(9.0, 0.5); // 3.0 in this example.
```

The two approaches do not necessarily have the same **error guarantees or special-value rules** across all combinations. `sqrt` is designed for a specific operation and has a correctly rounded guarantee, so it is the default choice when you actually want a **square root**.

With `Math.pow(x,0.5)`, you are going through a general exponentiation function. Each function has its own rule set for `-0.0`, NaN, Infinity, special exponents, and accuracy; you must rely on **the contract of the called function**, rather than using unconditional algebraic transformations to guess every output.

For `x < 0`, neither real square root nor `pow` with exponent `0.5` produces a finite real number; Java returns NaN in each respective case, rather than creating complex numbers.

## 11. Edge Cases: Negative Numbers, Zero, Infinity, NaN

| Input/Calculation | Illustrative Result | Explanation |
| --- | --- | --- |
| `Math.sqrt(-4.0)` | `NaN` | No real square root of -4 |
| `Math.sqrt(-0.0)` | `-0.0` | Preserves zero sign |
| `Math.cbrt(-8.0)` | `-2.0` | Real cube root exists |
| `Math.cbrt(-0.0)` | `-0.0` | Preserves zero sign |
| `Math.pow(-2.0, 3.0)` | `-8.0` | Odd integer exponent |
| `Math.pow(-2.0, 4.0)` | `16.0` | Even integer exponent |
| `Math.pow(-8.0, 1.0/3.0)` | `NaN` | Negative base, finite non-integer exponent |
| `Math.pow(Double.NaN, 0.0)` | `1.0` | Special rule of `pow`: exponent 0 |
| `Math.sqrt(Double.POSITIVE_INFINITY)` | `+Infinity` | Root of positive infinity |
| `Math.cbrt(Double.POSITIVE_INFINITY)` | `+Infinity` | Cube root of positive infinity |
| `Math.pow(1e200, 2)` | `+Infinity` | Mathematical result exceeds finite `double` range |
| `Math.pow(1e-200, 2)` | `+0.0` | Result too small, underflows to zero |

**Note:** `NaN` is not equal to itself under `==`. To detect NaN, use `Double.isNaN(value)` or `Double.isFinite(value)` when you want to ensure a finite result. To distinguish `+0.0` and `-0.0` bit-for-bit, use `Double.doubleToRawLongBits` instead of `==`.

In some business logic, negative input to `sqrt` should be **explicitly rejected** before calling the function, instead of silently producing NaN and propagating it through later steps:

```java
static double positiveRoot(double x) {
    if (!Double.isFinite(x) || x < 0.0) {
        throw new IllegalArgumentException("root input must be finite and >= 0");
    }
    return Math.sqrt(x);
}
```

This is an **illustrative method**, not a default JDK API. Note that `x < 0.0` still accepts `-0.0` because that comparison is false; if business rules require forbidding negative zero, check the sign bit separately. Define the domain according to application requirements, without assuming Java will throw an exception for you.

## 12. Overflow, Underflow, and Why `Math.hypot` Can Be Better Than `sqrt(x*x+y*y)`

A common mathematical formula for computing 2D vector length is:

```text
length = sqrt(x^2 + y^2)
```

But in `double`:

```java
double x = 1.0e200;
double y = 1.0e200;

double naive = Math.sqrt(x * x + y * y);
double robust = Math.hypot(x, y);
```

In the `naive` formula, the multiplication `x*x` already exceeds the finite `double` range (since `1e400` is too large), so the intermediate result is Infinity. `sqrt(Infinity)` remains Infinity, even though the mathematical vector length is about `1.414e200` and **still fits within the double range**.

`Math.hypot(x,y)` is designed to reduce the risk of **intermediate overflow/underflow** in length calculations. In this case, it returns a finite result. Similarly, with very small data, direct squaring might underflow to 0, whereas `hypot` uses a more stable computation.

Thus, **the right choice is not always pow or sqrt**: sometimes a specialized API like `Math.hypot` is more suitable than chaining `Math.sqrt(Math.pow(x,2)+Math.pow(y,2))`.

## 13. Do Not Create Large Integer Multiplication Just Because Root Returns double

For `int`, multiplication can overflow **before** the result is passed to `Math.sqrt`:

```java
int x = 50_000;
int y = x * x;  // -1794967296: int overflow.
double wrong = Math.sqrt(y); // NaN because y is negative.
```

In the example, `50_000^2 = 2_500_000_000` exceeds `Integer.MAX_VALUE`. The remaining low bits are interpreted by Java as a negative `int`. When passing that negative number into `Math.sqrt`, the result is NaN; the **root cause** is the overflowing integer multiplication, not `sqrt` being "wrong".

If you need to square first as a `long`:

```java
int x = 50_000;
long exactSquare = (long) x * x;  // 2_500_000_000L.
double root = Math.sqrt(exactSquare); // 50000.0 in the example.
```

The `(long)` cast must appear **before the multiplication**, not `(long)(x*x)`; casting after overflow cannot recover the result. If the range can exceed `long`, use `BigInteger` or explicit range checks.

## 14. `Math` or `StrictMath`?

Both `Math` and `StrictMath` provide `pow`, `sqrt`, `cbrt`, and many other operations. They provide nearly equivalent APIs in purpose, but their **implementation contracts and bit reproducibility** have differences:

- **`Math`** can be implemented with platform-specific optimizations, as long as it meets the API's accuracy and semantic requirements.
- **`StrictMath`** aims for reproducible results based on standardized calculation methods for many functions, with stricter rules on reference algorithms. Some functions like `sqrt` guarantee exact rounding.
- Both classes **can return identical results for many inputs**, such as `Math.sqrt(9.0)` and `StrictMath.sqrt(9.0)`, but you should not claim every call is always bit-for-bit identical unless the specification requires it.

```java
double a = StrictMath.pow(2.0, 10.0); // 1024.0.
double b = StrictMath.sqrt(9.0);      // 3.0.
double c = StrictMath.cbrt(27.0);     // 3.0.
```

In everyday applications, `Math` is the straightforward choice. If a system requires **reproducibility of numerical results across multiple environments**, carefully review bit-comparison requirements, the JVM, and the `StrictMath` contract for each operation; use the right types, calculation order, and reference test suites. Simply swapping the class name does not make every other calculation in an application deterministic.

With Java 17, floating-point expressions have consistent language-level constraints, but that does not eliminate rounding errors, special cases, or differences between approximation algorithms.

## 15. Checking `double` Before and After Calculation

A distance, root, or power API exposed to users may need input policies such as:

- Are negative numbers allowed? `cbrt` accepts finite negative numbers; `sqrt` has no real root for negative numbers other than zero.
- Are NaN/Infinity allowed? `Double.isFinite` checks for finite numbers.
- Is an Infinity result acceptable if the operation overflows? If not, check the **output** after the call.
- Is underflow to zero acceptable? With very small numbers, a mathematically non-zero result can still become 0 in `double`.
- Does the result need to be exact to the integer or decimal unit? If so, avoid misusing `double`/`Math.pow`.
- Is the sign of zero required? `-0.0` and `+0.0` compare `==` but have different bits.
- Is a strictly positive number required by **business logic**, even when mathematics allows negative values?

An example guarding the result:

```java
static double finiteSquareRoot(double value) {
    if (!Double.isFinite(value) || value < 0.0) {
        throw new IllegalArgumentException("invalid square root input");
    }
    double result = Math.sqrt(value);
    if (!Double.isFinite(result)) {
        throw new ArithmeticException("non-finite result");
    }
    return result;
}
```

This is a method used in an application class, not a built-in method in `Math`. Choose exception types and messages according to the actual API contract; not every system needs to forbid Infinity or NaN.

## 16. Complete Java 17+ Program

Save the following code as **`PowerRootDemo.java`**:

```java
public class PowerRootDemo {
    static long powExact(long base, int exponent) {
        if (exponent < 0) {
            throw new IllegalArgumentException("negative exponent");
        }
        long result = 1L;
        long factor = base;
        int remaining = exponent;
        while (remaining > 0) {
            if ((remaining & 1) != 0) {
                result = Math.multiplyExact(result, factor);
            }
            remaining >>>= 1;
            if (remaining > 0) {
                factor = Math.multiplyExact(factor, factor);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println("pow2_10=" + Math.pow(2.0, 10.0));
        System.out.println("pow9_half=" + Math.pow(9.0, 0.5));
        System.out.println("sqrt9=" + Math.sqrt(9.0));
        System.out.println("cbrt27=" + Math.cbrt(27.0));
        System.out.println("cbrtNegative=" + Math.cbrt(-8.0));
        System.out.println("powNegativeOdd=" + Math.pow(-2.0, 3.0));
        System.out.println("powNegativeEven=" + Math.pow(-2.0, 4.0));
        System.out.println("powNegativeFractionNaN="
                + Double.isNaN(Math.pow(-8.0, 1.0 / 3.0)));
        System.out.println("sqrtNegativeNaN="
                + Double.isNaN(Math.sqrt(-4.0)));
        System.out.println("sqrtMinusZeroBits="
                + (Double.doubleToRawLongBits(Math.sqrt(-0.0))
                == Double.doubleToRawLongBits(-0.0)));
        System.out.println("cbrtMinusZeroBits="
                + (Double.doubleToRawLongBits(Math.cbrt(-0.0))
                == Double.doubleToRawLongBits(-0.0)));
        System.out.println("powNaNExponentZero="
                + Math.pow(Double.NaN, 0.0));
        System.out.println("powOverflowInfinite="
                + Double.isInfinite(Math.pow(1.0e200, 2.0)));
        System.out.println("powUnderflowZero="
                + (Math.pow(1.0e-200, 2.0) == 0.0));
        System.out.println("sqrtInfinity="
                + Math.sqrt(Double.POSITIVE_INFINITY));
        System.out.println("cbrtInfinity="
                + Math.cbrt(Double.POSITIVE_INFINITY));
        System.out.println("sqrtMinPositive="
                + (Math.sqrt(Double.MIN_VALUE) > 0.0));
        System.out.println("cbrtMinPositive="
                + (Math.cbrt(Double.MIN_VALUE) > 0.0));

        double large = 1.0e200;
        System.out.println("naiveHypotInfinite="
                + Double.isInfinite(Math.sqrt(large * large + large * large)));
        System.out.println("hypotFinite="
                + Double.isFinite(Math.hypot(large, large)));

        int x = 50_000;
        System.out.println("intMultiplyOverflow=" + (x * x));
        System.out.println("powExact3_10=" + powExact(3L, 10));
        try {
            System.out.println("powExact2_63=" + powExact(2L, 63));
        } catch (ArithmeticException ex) {
            System.out.println("powExact2_63=ArithmeticException");
        }
        System.out.println("pow2_53PlusOneLost="
                + (Math.pow(2.0, 53.0) + 1.0 == Math.pow(2.0, 53.0)));
        System.out.println("strictSqrt9=" + StrictMath.sqrt(9.0));
        System.out.println("strictCbrt27=" + StrictMath.cbrt(27.0));
    }
}
```

Compile/run in the directory containing the file:

```bash
javac --release 17 -encoding UTF-8 PowerRootDemo.java
java PowerRootDemo
```

Exact stdout:

```text
pow2_10=1024.0
pow9_half=3.0
sqrt9=3.0
cbrt27=3.0
cbrtNegative=-2.0
powNegativeOdd=-8.0
powNegativeEven=16.0
powNegativeFractionNaN=true
sqrtNegativeNaN=true
sqrtMinusZeroBits=true
cbrtMinusZeroBits=true
powNaNExponentZero=1.0
powOverflowInfinite=true
powUnderflowZero=true
sqrtInfinity=Infinity
cbrtInfinity=Infinity
sqrtMinPositive=true
cbrtMinPositive=true
naiveHypotInfinite=true
hypotFinite=true
intMultiplyOverflow=-1794967296
powExact3_10=59049
powExact2_63=ArithmeticException
pow2_53PlusOneLost=true
strictSqrt9=3.0
strictCbrt27=3.0
```

Some highlights from the program:

1. `pow2_10=1024.0` proves that the result of `Math.pow` is **`double`**, even when the corresponding operation is integer exponentiation.
2. `sqrt9`, `cbrt27` illustrate the two specialized roots; `cbrtNegative=-2.0` while `powNegativeFractionNaN=true` distinguishes negative real-root semantics.
3. `sqrtNegativeNaN=true` and the two `...MinusZeroBits=true` lines show that **non-zero negative** is not the same as **negative zero**.
4. `powNaNExponentZero=1.0` serves as a reminder that `pow` has special rules; not everything can be deduced from simple real-number algebra.
5. `powOverflowInfinite` and `powUnderflowZero` illustrate `double` representation limits.
6. `naiveHypotInfinite=true` while `hypotFinite=true` explains why `Math.hypot` should be used to compute large vector lengths.
7. `intMultiplyOverflow=-1794967296` shows that `int` multiplication can overflow; `powExact3_10=59049` and `powExact2_63=ArithmeticException` illustrate **range-checked** integer exponentiation.
8. `pow2_53PlusOneLost=true` demonstrates that the `double` range cannot accurately represent every large integer.
9. The two lines `strictSqrt9`, `strictCbrt27` illustrate `StrictMath` syntax.

By using `Double.isNaN`/`Double.isInfinite` methods, the program avoids assuming every result is an ordinary finite number.

## 17. Decision Table: Which Method Should You Use?

| Practical Requirement | Choice | Reason |
| --- | --- | --- |
| Compute `a^b` with `double` and arbitrary exponent in valid domain | `Math.pow(a,b)` | General syntax for floating-point |
| Compute square root of `x >= 0` | `Math.sqrt(x)` | Specialized function with correctly rounded guarantee |
| Compute real cube root, even for `x < 0` | `Math.cbrt(x)` | Supports negative bases under cube-root semantics |
| Compute `x*x` or `x*x*x` on `double` | Explicit multiplication when appropriate | Clear for small powers; verify accuracy/performance if critical |
| Compute length `sqrt(x*x+y*y)` with `double` of extreme magnitude | `Math.hypot(x,y)` | Avoids unnecessary intermediate overflow/underflow |
| Compute `3^10` as `long` and fail if exceeding `long` | Multiplication with `Math.multiplyExact` | Does not go through `double` and lose units |
| Compute `2^100` as an exact integer | `BigInteger.pow(100)` | Arbitrary-precision integer, not limited to 64 bits |
| Need `pow`/`cbrt` reproducibility per `StrictMath` contract | `StrictMath` and corresponding QA | Chooses reproducible result semantics |
| Need root of a negative number in complex domain | Complex number library | `Math.sqrt` only returns `double`, does not represent complex numbers |
| Need to check if an integer is an exact perfect square | Integer algorithm with boundary checks | `double` can round large `long` data |

A right choice does not just produce "a number close to what is expected", it must also fit the **input domain, result type, error policy, and failure cases**.

## 18. Common Mistakes When Using `pow`, `sqrt`, `cbrt`

| Mistake/Misconception | Consequence | Correct Approach |
| --- | --- | --- |
| Writing `2 ^ 3` to get 2 to the power of 3 | Java performs bitwise XOR → 1 | Use `Math.pow(2,3)` or appropriate multiplication |
| Computing negative cube root with `Math.pow(x,1.0/3.0)` | Can return NaN | Use `Math.cbrt(x)` |
| Using `Math.sqrt(-4)` expecting an exception | Returns NaN, does not throw `ArithmeticException` | Check domain or `Double.isNaN` |
| Assuming `sqrt(-0.0)` is NaN | Result preserves `-0.0` | Check signed zero when required |
| Using `(long)Math.pow(large, n)` to get an exact integer | Representation error, overflow/saturation on cast | Use `BigInteger.pow` or `multiplyExact` |
| Writing `Math.sqrt(x*x+y*y)` with very large numbers | Intermediate square becomes Infinity | Use `Math.hypot` |
| Casting result after `int * int` overflows | Cannot salvage an already wrong result | Widen before multiplying or use `Math.multiplyExact` |
| Thinking `Math.pow` is always bit-for-bit identical to direct multiplication | Calculation/rounding paths may differ | Choose operations with clear semantics and boundary QA |
| Thinking `Math.sqrt` always returns an integer for large square inputs | Return type is `double` | Use an integer algorithm when exactness is needed |
| Using `== Double.NaN` to detect errors | NaN is not equal to any number, including itself | `Double.isNaN` or `Double.isFinite` |
| Thinking all `Math` and `StrictMath` calls are bit-exact across all inputs | Reproducibility contracts differ by function | Rely on API contract and target tests |
| Prematurely optimizing via algebraic transformations | Can change rounding error, zero, Infinity, NaN | Test special domains and accuracy requirements |

## 19. Self-Check Questions

1. **What type does `Math.pow(2,10)` return?** `double`, value `1024.0`. Java widens `int` arguments to `double`.
2. **Can `^` be used for exponentiation in Java?** No. `^` is XOR.
3. **`Math.sqrt(9)` and `Math.pow(9,0.5)` both yield 3.0 in the example, so are they equivalent in all cases?** Do not assume identical contracts across all rounding and edge cases.
4. **What does `Math.sqrt(-4.0)` produce?** `NaN`, not an exception.
5. **Why is `Math.cbrt(-8.0)` valid?** Because the real cube root of a negative number exists; the result is `-2.0`.
6. **Why does `Math.pow(-8.0,1.0/3.0)` not return `-2.0`?** The `double` exponent is finite but non-integer; with a negative base, `Math.pow` returns NaN per specification.
7. **Does `Math.sqrt(-0.0)` lose the sign bit?** No; the result remains `-0.0`.
8. **What should be used to compute `sqrt(x*x+y*y)` with `x=y=1e200`?** `Math.hypot(x,y)`, because individual squares will overflow.
9. **Does `Math.pow(2.0,53)+1.0` preserve the `+1` unit?** No; at `2^53`, the ULP is already 2.
10. **If you want integer exponentiation without allowing overflow, what should you use?** `Math.multiplyExact` inside an integer multiplication algorithm or `BigInteger.pow`.
11. **Do `Math.sqrt` and `Math.cbrt` treat NaN like ordinary numbers?** No; special values must be checked per floating-point contracts.
12. **Should you choose `Math` or `StrictMath` when bit reproducibility is required?** Check the contract of each function and verify per environment; `StrictMath` aims for stricter reproducible results for many functions.

**Key takeaway:** `Math.pow` is **general `double` exponentiation**, `Math.sqrt` is **specialized square root**, and `Math.cbrt` is **real cube root including negative numbers**. Choose them based on **the nature of the problem**, not just algebraic transformations. When computing vector lengths, use `Math.hypot` to mitigate intermediate overflow; when computing **exact integer** powers, use checked multiplication or `BigInteger.pow`, rather than placing misplaced trust in `double`.
