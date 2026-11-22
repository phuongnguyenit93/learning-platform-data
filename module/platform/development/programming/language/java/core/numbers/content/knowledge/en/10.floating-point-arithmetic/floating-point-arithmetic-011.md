# Always-Strict Since Java 17 and the Historical Role of `strictfp`

Starting in **Java SE 17**, `float` and `double` floating-point expressions are evaluated **always under strict semantics** (*always-strict floating-point semantics*). This is the change introduced by **JEP 306 – Restore Always-Strict Floating-Point Semantics**. Therefore, on Java 17 and newer, adding or removing the `strictfp` keyword **does not change the evaluation result of a floating-point expression**.

Before Java 17, especially from Java 1.2 through Java 16, `strictfp` had an effect: it required computations within its scope to adhere strictly to the standard `float`/`double` value sets, instead of allowing some JVMs to use intermediate value sets with an **extended-exponent range**. The change in Java 17 removes this divergence.

Key example:

```java
static double ordinary(double x) {
    return x * 2.0 / 2.0;
}

static strictfp double legacyStrict(double x) {
    return x * 2.0 / 2.0;
}
```

Both methods above have **identical floating-point semantics on Java 17+**. `strictfp` is still accepted in source code for compatibility, though modern compilers may warn that this modifier is no longer required.

This lesson belongs to the **Floating-Point Arithmetic** section of the **Java core – numbers** module. The focus is understanding what "strict" means, why `strictfp` used to exist, what actually changed in Java 17, and what **always-strict does not guarantee**.

## 1. What Does "Strict Floating-Point" Actually Mean?

Java uses IEEE 754 binary floating-point representations:

| Type | Binary Format | Significand Precision | Exponent and Value Range |
| --- | --- | --- | --- |
| `float` | binary32, 32-bit | 24 bits including hidden bit | Range corresponding to binary32 |
| `double` | binary64, 64-bit | 53 bits including hidden bit | Range corresponding to binary64 |

Under **strict** evaluation, every expression of type `float` only takes values representable by standard `float`; every expression of type `double` only takes values representable by standard `double`. Corresponding IEEE 754 operations produce results according to the specified format and rounding rules, without silently keeping an intermediate value set with a larger exponent than the expression's type.

For example, with `double`:

```java
double x = Double.MAX_VALUE;
double result = (x * 2.0) / 2.0;
// result is Infinity, it does not return to x.
```

At step `x * 2.0`, the mathematical value exceeds the **finite** range of `double`, so the result is `+Infinity`. Then `Infinity / 2.0` remains `Infinity`.

This example illustrates the difference between idealized real-number math and floating-point evaluation with a finite exponent range. You must not interpret `(x * 2) / 2 == x` as an always-true identity when using `double`.

**Strict does not mean infinite precision.** Finite results can still be rounded; `0.1` and `0.2` have no exact finite binary representation; operations can overflow to infinity or underflow to subnormal numbers/signed zero. Strict only ensures **evaluation rules are tightly specified**; it does not turn `float`/`double` into `BigDecimal`.

## 2. Brief Three-Stage History of Java Floating-Point

| Stage | Default Behavior | Role of `strictfp` |
| --- | --- | --- |
| Java 1.0–1.1 | Always used strict semantics | No mode split like in Java 1.2 yet |
| Java 1.2–16 | Could use strict or a mode allowing intermediate value sets with **extended exponent** where permitted by the spec | Required strict evaluation within the declared scope |
| **Java 17 and newer** | **All `float`/`double` expressions are always-strict** | Kept for backward source compatibility; no longer affects computation |

### 2.1. The Java 1.0 and 1.1 Era

Early versions of Java required floating-point operations to have strict semantics. This served the goal of ensuring programs had well-defined behavior across different execution environments.

### 2.2. From Java 1.2 to Java 16: Why `strictfp` Was Introduced

Certain older CPU families had hardware characteristics that made exact strict mode significantly expensive. Therefore, starting in Java 1.2, the specification allowed some **non-FP-strict** `float` or `double` computations to use **extended-exponent** value sets:

- `float-extended-exponent value set`: **same significand precision bits** as `float`, but an extended exponent range.
- `double-extended-exponent value set`: **same significand precision bits** as `double`, but an extended exponent range.

Common misconception: these historical value sets were specified with a **larger exponent range**, **not a guarantee of extra significand precision bits**. Do not summarize inaccurately that "without strict, Java was allowed to keep all calculations at arbitrary 80-bit precision".

With non-strict computation, when hardware/JVM was allowed to use an extended exponent range, an intermediate result could avoid overflowing or underflowing at a point where strict computation had already hit infinity or zero. That could create differences in final results across historical environments.

`strictfp` was introduced so programmers could **explicitly request strict evaluation** on a suitable class/interface or method, preventing variation for expressions within that scope.

### 2.3. Since Java 17: JEP 306 Restores Always-Strict

Hardware and JVM implementations evolved, making the accommodation for legacy hardware unnecessary. **JEP 306** unified the semantics once again:

- Java floating-point operations are no longer allowed to use extended-exponent intermediate value sets in place of standard `float`/`double`.
- Every Java floating-point expression is evaluated strictly, **whether or not `strictfp` is present**.
- The `strictfp` keyword is retained for source compatibility, yet creates no "stricter mode" for marked methods/classes.

This is a change in the **language and virtual machine specifications**, not merely a compiler option or a HotSpot-specific optimization flag.

## 3. How `strictfp` Was Used in Older Java Code

In versions where `strictfp` had an effect, this modifier was typically placed on an appropriate **class**, **interface**, or **method** so floating-point expressions within that scope had strict semantics.

Syntax example:

```java
public strictfp class LegacyCalculator {
    public double calculate(double x, double y) {
        return (x * y) / 3.0;
    }
}
```

Or:

```java
public class LegacyCalculator {
    public static strictfp double calculate(double x, double y) {
        return (x * y) / 3.0;
    }
}
```

The two snippets above are **independent declaration examples**; do not place two `public` classes with the same name in one file. In Java 17+, the modifier remains syntactically valid yet **does not alter evaluation semantics**. For newly written Java 17+ code, there is normally no need to add `strictfp` just to get strict results.

Not every position in Java accepts the `strictfp` modifier; for instance, it is not a modifier for an individual variable. When reviewing legacy code, check the target Java version to understand the historical reason for the modifier.

## 4. Example of Intermediate Exponent Difference

Consider the calculation:

```java
double x = Double.MAX_VALUE;
double value = x * 2.0 / 2.0;
```

Under **strict** evaluation, the result of `x * 2.0` is `Infinity`. Thus the final result remains `Infinity`, even though in idealized real-number math `(x × 2) ÷ 2 = x`.

In the historical model permitting **extended-exponent**, some cases could hold an intermediate with a larger exponent, preventing the multiplication from overflowing immediately in the intermediate value. When subsequent steps brought the value back into the standard range, the result could differ.

Note three caveats when using this example:

1. It describes **why historical evaluation modes could differ**, **not a claim** that every pre-Java 17 JVM definitely returned a different value.
2. Non-strict code on Java 1.2–16 could still be evaluated strictly in many environments. Permitting an extended exponent range did not compel a JVM to use it.
3. In **Java 17+**, you neither need nor can use `strictfp` to toggle between these two modes: **only strict semantics exist**.

Therefore, when analyzing a numerical discrepancy reported on an older JVM, check the **Java version**, CPU/JVM, and whether source code had `strictfp`; do not apply "strictfp changes the result" reasoning to a pure modern Java 17+ program.

## 5. How Does Strict Differ from Numerical Exactness?

Even when always strict:

```java
double sum = 0.1 + 0.2;
System.out.println(sum == 0.3); // false
```

`0.1` and `0.2` cannot be represented exactly with binary64's finite bits. Each operation rounds according to the appropriate IEEE 754 rule. Strict requires an operation to produce the **representable rounded result**, not a result equal to infinite-precision mathematical real numbers.

### Things Unchanged by Always-Strict

- `float` still has about 24 bits of binary precision; `double` still has about 53 bits.
- `NaN`, `+Infinity`, `-Infinity`, `+0.0`, and `-0.0` still exist and behave according to Java's floating-point rules.
- Floating-point division by zero can still produce infinity/NaN rather than `ArithmeticException`.
- Addition and multiplication results can still change when changing **evaluation order** due to rounding and overflow.
- You must not use `double` instead of `BigDecimal` for currency or business logic needing exact decimals simply because Java 17 is always-strict.

### Strict and Expression Evaluation Order

```java
double big = 1e16;

double left = (big + 1.0) - big; // 0.0
double right = (big - big) + 1.0; // 1.0
```

Around `1e16`, a difference of 1 is too small for `double` to distinguish after adding to `big`, so `(big + 1.0)` rounds back to `big`. However, `big - big` gives 0 exactly, and adding 1 then gives 1.0.

**Always-strict does not make floating-point addition associative like mathematical real numbers.** It only determines the result corresponding to the expression and evaluation order specified by Java. Changing parentheses, changing accumulation order, or changing algorithms can still alter the result.

## 6. Strict Does Not Mean "Every Approach Produces the Same Bits"

Since Java 17, Java's floating-point operators and corresponding conversions have strict evaluation rules. However, if two programs **do not use the same operations or the same algorithm**, they are not forced to yield the same bit-level results.

### 6.1. `Math.fma` Differs from Separate Multiply-Then-Add

`Math.fma(a, b, c)` (*fused multiply-add*) evaluates the product and sum with **a single final rounding**, rather than rounding after multiplication and then rounding again after addition. It can yield a different result from `a * b + c` even on Java 17+:

```java
double epsilon = Math.ulp(1.0);
double a = 1.0 + epsilon;
double b = 1.0 - epsilon;

double separate = a * b - 1.0;
double fused = Math.fma(a, b, -1.0);

System.out.println(separate == 0.0); // true
System.out.println(fused < 0.0);      // true
```

Because the exact product of the two operands is `1 - epsilon²`, standalone multiplication rounds to 1.0 and subtraction then yields 0.0. `fma` rounds only once after the final sum and preserves the tiny negative residual.

**This difference is not a violation of always-strict.** `Math.fma` is a distinct operation with explicit rules. An optimization must not arbitrarily replace `a*b+c` with `Math.fma(a,b,c)` if doing so alters observable results.

### 6.2. `Math` and `StrictMath` Are Not `strictfp`

The name `StrictMath` is easily confused with the `strictfp` modifier.

- **`strictfp`** is a historical language modifier concerning how **expressions** within its scope are evaluated.
- **`Math`** is a mathematical library class providing `sin`, `cos`, `log`, `sqrt`, `fma`, etc. Rounding and accuracy contracts depend on **each method**.
- **`StrictMath`** is a library class designed for reproducibility requirements of methods specified in a strict manner, especially many transcendental functions tied to historical reference algorithms.

Java 17 always-strict **does not mean every call to `Math.sin` and `StrictMath.sin` must produce identical bits** in all situations. Read each method's specific contract, especially when an algorithm requires bitwise reproducibility across different environments.

Nor should you assume replacing all `Math` calls with `StrictMath` is necessary or solves all errors; it addresses a specific class of math library requirements, not algorithm design or numeric type selection.

### 6.3. Parallelism and Accumulation Order

Two threads summing the same data in two different orders can get different floating-point results. Always-strict does not compel `parallelStream().sum()` and a sequential loop to evaluate additions with the exact same expression tree if the API permits algorithmic differences.

When reproducibility is required, control **operation order**, chunking strategy, accumulation algorithm, and library calls. `strictfp` in Java 17 does not make these decisions for you.

## 7. How Does Java 17+ Handle Overflow, Underflow, NaN, and Signed Zero?

Strict evaluation still includes special IEEE 754 values:

| Expression | Result in Java 17+ | What to Understand |
| --- | --- | --- |
| `Double.MAX_VALUE * 2.0` | `Infinity` | Overflow of `double` finite range |
| `Double.MIN_VALUE / 2.0` | `+0.0` | Underflow from smallest positive subnormal |
| `-Double.MIN_VALUE / 2.0` | `-0.0` | Underflow preserves sign |
| `1.0 / 0.0` | `Infinity` | Floating-point division by 0 does not throw ArithmeticException |
| `0.0 / 0.0` | `NaN` | Operation has no defined real numeric result |
| `0.1 + 0.2 == 0.3` | `false` | Binary floating-point still rounds |
| `Math.fma(a,b,c)` vs. `a*b+c` | Can differ | Different number of rounding steps |

`Double.MIN_VALUE` **is not the smallest negative double**; it is the smallest positive non-zero `double`. This is a very useful underflow test case.

For very small yet still representable values, Java supports **subnormal numbers** and **gradual underflow**, and must not arbitrarily "flush to zero" every number below the normal threshold. In Java 17+, strict rules for `float`/`double` continue to apply in these regions.

## 8. How Does the Compiler Handle `strictfp` on Java 17+?

A Java 17+ program can still declare:

```java
public class LegacyStrictDemo {
    public static strictfp double twice(double x) {
        return x * 2.0;
    }
}
```

This is a standalone source snippet and the file name must be `LegacyStrictDemo.java`. With modern `javac`, the declaration can produce a warning like:

```text
[strictfp] as of release 17, all floating-point expressions
are evaluated strictly and 'strictfp' is not required
```

The exact message/path/line number depends on the tool version, so do not treat this warning string as **program stdout**. It is a **compile-time** warning, not the output of floating-point operators.

### Should You Remove `strictfp` from Legacy Code?

If **deploying and compiling exclusively for Java 17 and newer**, you can usually remove the redundant modifier without changing `float`/`double` operation semantics. However:

1. Confirm the build scope truly targets Java 17+ only.
2. If the same source still needs compatibility with Java 8/11 or pre-17 releases, do not rush to delete `strictfp` where floating-point reproducibility might depend on that modifier.
3. Test floating-point-sensitive algorithms before and after refactoring, especially if simultaneously changing operation order, `Math`/`StrictMath` functions, or `fma` methods.
4. There is no need to add `strictfp` to "patch" `0.1 + 0.2` error or to force programs to throw an exception on infinity.

The appropriate explanation in a modern code review is: **the modifier is still accepted for compatibility, yet does not make calculations stricter on Java 17+**.

## 9. Standalone Runnable Java 17+ Program

Save the file **`AlwaysStrictDemo.java`**:

```java
public class AlwaysStrictDemo {
    static double ordinary(double x) {
        return x * 2.0 / 2.0;
    }

    static strictfp double legacyStrict(double x) {
        return x * 2.0 / 2.0;
    }

    public static void main(String[] args) {
        double large = Double.MAX_VALUE;

        double plain = ordinary(large);
        double marked = legacyStrict(large);

        System.out.println("plain-infinite=" +
                Double.isInfinite(plain));
        System.out.println("marked-infinite=" +
                Double.isInfinite(marked));
        System.out.println("same-bits=" +
                (Double.doubleToLongBits(plain)
                        == Double.doubleToLongBits(marked)));

        double big = 1e16;
        System.out.println("round-left=" + ((big + 1.0) - big));
        System.out.println("round-right=" + ((big - big) + 1.0));
        System.out.println("decimal-equal=" + (0.1 + 0.2 == 0.3));

        double epsilon = Math.ulp(1.0);
        double a = 1.0 + epsilon;
        double b = 1.0 - epsilon;
        double separate = a * b - 1.0;
        double fused = Math.fma(a, b, -1.0);

        System.out.println("separate-zero=" + (separate == 0.0));
        System.out.println("fused-negative=" + (fused < 0.0));

        System.out.println("positive-underflow=" +
                (Double.MIN_VALUE / 2.0));
        System.out.println("negative-underflow=" +
                (-Double.MIN_VALUE / 2.0));
        System.out.println("nan-check=" +
                Double.isNaN(0.0 / 0.0));
    }
}
```

Compile/run on JDK 17 or newer:

```bash
javac AlwaysStrictDemo.java
java AlwaysStrictDemo
```

**Note:** `javac` may emit a warning that `strictfp` is unnecessary. That warning is compiler output, **not part of the stdout below**.

Program stdout:

```text
plain-infinite=true
marked-infinite=true
same-bits=true
round-left=0.0
round-right=1.0
decimal-equal=false
separate-zero=true
fused-negative=true
positive-underflow=0.0
negative-underflow=-0.0
nan-check=true
```

Interpretation:

- Both methods with and without `strictfp` yield the same result on the `double` overflow calculation in Java 17+: `Infinity`.
- `round-left` and `round-right` yield different results because **parentheses change the order of operations**, unrelated to the modifier.
- `decimal-equal=false` proves always-strict **does not eliminate binary representation error**.
- `separate-zero=true` and `fused-negative=true` show that `Math.fma` (one rounding) is not equivalent to multiply-then-subtract with two roundings.
- Underflow can yield positive or negative zero; NaN can still arise from `0.0/0.0`.

Do not present an example that only runs on Java 17+ and deduce that older JVMs **definitely** returned different results without `strictfp`. Older JVMs could still choose strict evaluation where the historical specification permitted.

## 10. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Java 17 removed the `strictfp` keyword from syntax." | The modifier is still accepted for compatibility, yet has no effect on floating-point evaluation. |
| "Adding `strictfp` in Java 17 makes results more accurate." | All expressions are already strict; the modifier adds no precision bits. |
| "`strictfp` used to guarantee all calculations in infinite real precision." | It only controlled `float`/`double` value sets and proper rounding; results still have rounding error. |
| "Historical non-strict mode always used more significand bits." | The historical mechanism was specified via **extended exponent** with the same significand bits, not arbitrary precision expansion. |
| "Every pre-17 JVM gave different results when omitting `strictfp`." | Extended-exponent mode was **permitted**, not mandatory on every JVM. |
| "Always-strict makes `double` addition associative." | `(a+b)+c` can still differ from `a+(b+c)` due to rounding. |
| "Always-strict makes `Math.fma(a,b,c)` identical to `a*b+c`." | `fma` has one rounding, while the separate expression has two. |
| "`strictfp` and `StrictMath` are the same feature." | A language modifier and a library class are two separate mechanisms. |
| "Strict means all `Math`/`StrictMath` calls are bitwise identical." | You must check each method's contract and algorithm. |
| "Always-strict enables exact decimal currency math with `double`." | `BigDecimal` or smallest-unit integers remain more appropriate when decimal exactness is required. |
| "A `strictfp` compile-time warning is a runtime error." | It is a compiler warning; the program can still run. |

## 11. Applying in Applications and Testing

### 11.1. When Upgrading Java Versions

An older project migrating from Java 8/11 to Java 17 should:

- Inspect places using `strictfp` and note the historical reason, if any.
- Cross-check results in algorithms sensitive to overflow/underflow, subnormal numbers, iterative calculations, and threshold conditions.
- Do not blame every numerical change during a Java upgrade on JEP 306: library changes, algorithms, aggregation order, data types, or application code can also alter results.
- If code uses `Math.sin`, `Math.log`, etc., and needs strict result reproducibility, check the specific API contract rather than merely adding a modifier.

### 11.2. When Designing New Java 17+ Code

The normal choice is **not to use `strictfp`**. Focus on:

1. Choosing the right type—`float`, `double`, `BigDecimal`, or integer—based on data semantics.
2. Defining acceptable error tolerances and comparison rules.
3. Validating `NaN` and infinity with `Double.isFinite` or `Float.isFinite` if the domain requires finite values.
4. Controlling operation order, parallel accumulation, and calls such as `Math.fma`.
5. Testing boundaries near overflow, subnormals, and signed zero when algorithms are sensitive to them.

### 11.3. When Bit-Level Reproducibility Across Machines or Runs Is Required

Always-strict **narrows the source of differences that used to come from intermediate exponent modes**. However, a "bit-for-bit identical results" guarantee for an entire application still depends on:

- Whether identical expressions and bit-for-bit identical input data are used.
- Computation order and rounding steps (e.g., FMA vs. separate multiply/add).
- Whether called library functions guarantee deterministic results under a specific contract.
- Parallelism models, reduction order, and algorithmic changes.

Tightly defined primitive operations **do not automatically make an entire numerical pipeline deterministic** if the pipeline still leaves algorithmic choices open.

## 12. Self-Check Questions

1. Why is Java 17 called **always-strict**, and how does it differ from the default mode permitting extended exponents in Java 1.2–16?
2. Did historical `strictfp` expand significand bits, or only **restrict intermediate exponent range expansion**? Explain the true mechanism.
3. On Java 17+, do two methods with and without `strictfp` containing the same `double` expression require two separate computation modes? Why might the compiler warn?
4. Why does `Double.MAX_VALUE * 2.0 / 2.0` not return `Double.MAX_VALUE` under strict semantics?
5. Why does `(1e16 + 1.0) - 1e16` differ from `(1e16 - 1e16) + 1.0`? Does always-strict change that?
6. Explain the difference between `Math.fma(a,b,c)` and `a*b+c` in terms of **number of rounding steps**.
7. Should you replace all `Math` calls with `StrictMath` to "enable `strictfp`" in Java 17? State the true role of each name.
8. A Java 8 application has `strictfp` on exponent-sensitive calculations. When upgrading to Java 17 and wanting to remove the modifier, what should you check?
9. Why does always-strict not make `0.1 + 0.2 == 0.3` become `true`?
10. If a Java 17 application sums values in different orders across different workers, can result differences appear even though all expressions are strict?

## 13. Memory Checklist

- **Java 17+ is always strict:** there is no longer a toggle between two floating-point evaluation modes via `strictfp`.
- **`strictfp` is historical and for source compatibility** on Java 17+; it brings no higher precision.
- **Java 1.2–16 allowed extended-exponent value sets** in non-strict contexts; same significand precision, wider exponent range.
- **Strict does not eliminate rounding**, overflow, underflow, signed zero, Infinity, or NaN.
- **Expressions and operation order still matter**; `Math.fma` differs from separate multiply-then-add.
- **`StrictMath` is a library API**, not a mechanism to activate the `strictfp` modifier.
- **Test reproducibility at the full-algorithm level**, not just by looking at a modifier on one method.
- For data needing **exact decimals**, you still must use an appropriate numeric model such as `BigDecimal`, rather than relying on `strictfp`.

### Specification Sources for Further Reading

- [JEP 306 – Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306).
- [Java Language Specification, Java SE 17 – §15.4 Floating-point Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.4).
- [Java Virtual Machine Specification, Java SE 17 – §2.8 Floating-Point Arithmetic](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.8).

**Conclusion:** Java 17 did not "make floating-point numbers infinitely accurate"; rather, it **removed the difference between strict/non-strict evaluation modes formerly permitted for legacy hardware**. `strictfp` still appears in legacy code but does not alter expression results in Java 17+. When assessing floating-point correctness, pay attention to representation range, rounding, operation order, library APIs, and algorithms.