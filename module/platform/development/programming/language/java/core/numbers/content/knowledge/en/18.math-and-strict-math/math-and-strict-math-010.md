# Distinguishing Reproducibility Requirements of Math and StrictMath in Java

Java has two math utility classes in `java.lang`: `Math` and `StrictMath`. Both provide corresponding functions such as `sin`, `cos`, `log`, `exp`, `pow`, `sqrt`, and `hypot`. However, when **cross-platform result reproducibility** is required, you cannot conclude that the two classes share an identical contract.

**Key difference:** For certain floating-point functions, `Math` allows different implementations to produce `double` values that *differ in low bits* as long as they satisfy the specified error bounds and properties. For the **group of `StrictMath` functions bound to the `fdlibm` algorithm**, Java specifies a reference calculation method to help produce **the exact same bit-for-bit results for the same inputs** across compliant Java implementations.

This topic belongs to **Math and StrictMath** in Java Core. The lesson separates "same formula", "numerically close enough", "same bits", and "entire program reproducibility", explains the Java 17+ context, and guides how to choose the appropriate API.

## 1. Three Levels of "Reproducibility" to Distinguish

| Requirement Level | Meaning | How to Evaluate |
| --- | --- | --- |
| Numerical accuracy | Computed value lies within the function's allowable error bound | Compare against mathematical reference and `ulp`/tolerance bounds |
| Bitwise function reproducibility | Same **bit-identical arguments** produce return values with the same bit representation per spec | Compare `Double.doubleToRawLongBits` or `doubleToLongBits` depending on goal |
| Whole-program reproducibility | Same data and execution contract produce consistent entire calculations/output strings | Must control algorithms, operation order, data, threads, formatting, and versions/dependencies |

A method that is **accurate within 1 ulp** can still have **two different bit answers** if the spec permits either adjacent value around the mathematical result. Thus "high accuracy" does not automatically imply "bit-for-bit reproducible".

Conversely, bit-identical results across runs do not automatically prove business correctness. An algorithm can be consistent while still using an unstable formula, wrong data types, or failing to reflect real requirements.

## 2. `Math`: Prioritizes Spec-Compliant Accuracy, Allows Implementation Optimizations

According to the API documentation, certain corresponding functions in `Math` **are not required to give bit-for-bit identical results across all implementations**. This allows the JVM to leverage platform libraries or faster CPU instructions, provided results still obey each function's contract.

For example, `Math.sin(double)` requires results accurate within **1 ulp** and satisfying *semi-monotonicity*. Other functions may have limits of 1 ulp, 2 ulp, or require **correct rounding** depending on the method; you must not apply a single number to every member of `Math`.

The concept of `ulp` (*unit in the last place*) refers to the spacing between representable floating-point values near a given value. For example:

~~~java
System.out.println(Math.ulp(1.0));
// 2.220446049250313E-16
~~~

This spacing depends on the magnitude of the number; it is not equivalent to a fixed decimal epsilon across the entire `double` domain.

**Understanding "allowed to differ" properly:**

- It does not mean `Math` always differs from `StrictMath`.
- It does not mean a JVM always picks a "less accurate" approximation.
- It does not mean `Math.sin(x)` can return arbitrary values; accuracy requirements and function properties still apply.
- It does not guarantee using `Math` is always faster than `StrictMath`: actual performance depends on JDK/JIT/CPU, the called function, and the workload.

Many real implementations may delegate directly to `StrictMath` for certain functions or produce identical results on a test dataset. **A test producing equal results on the current machine does not upgrade the API contract into a cross-platform guarantee.**

## 3. `StrictMath`: Group of Functions Defined via `fdlibm`

`StrictMath` was designed to support portability/reproducibility. Java specifies that certain math functions use semantics corresponding to **`fdlibm` (Freely Distributable Math Library) version 5.3**, understood as algorithms ported to Java and executed under Java arithmetic rules.

According to the Java SE 21 API, the group of functions bound to `fdlibm` algorithms includes:

- Trigonometric and inverse: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`.
- Exponential/logarithmic: `exp`, `log`, `log10`, `expm1`, `log1p`, `pow`.
- Hyperbolic: `sinh`, `cosh`, `tanh`.
- Other functions in the group: `cbrt`, `hypot`.

With **identical input bits** and a spec-compliant implementation, these functions have a reference calculation rule, making them more suitable when you need **bit-for-bit stable results across Java platforms**.

**Do not state that every single method of `StrictMath` uses `fdlibm`.** Members such as `abs`, `min`, `max`, `nextUp`, `copySign`, `sqrt`, or integer methods have their own contracts; some are exact/correctly rounded or have explicit bit rules without needing `fdlibm` algorithms. Read each function's documentation when strict reproducibility is required.

Nor should you state that `StrictMath` returns "absolutely exact mathematical values" for `sin` or `log`. Results remain approximate `double` values. What it adds is a **specified calculation rule**, not turning binary64 into infinite-precision real numbers.

## 4. Direct Comparison of the Two Classes

| Question | `Math` | `StrictMath` |
| --- | --- | --- |
| Has corresponding trig/exp/log functions? | Yes | Yes |
| Functions return real numbers represented as `double`? | Yes | Yes |
| Must obey NaN, infinity, signed zero rules per function? | Yes | Yes |
| All corresponding functions required bit-identical across all JVMs? | **No**; some functions allow implementation freedom within spec bounds | **`fdlibm` group has reference algorithms** for reproducibility |
| Can produce the same bit result on the current JVM? | Possibly | Possibly |
| Always runs faster than the other class? | No guarantee | No guarantee |
| Choosing the class alone guarantees *entire program* reproducibility? | No | No |

Example:

~~~java
double x = 0.7;
double a = Math.sin(x);
double b = StrictMath.sin(x);
~~~

On some JVMs, `a` and `b` may match bit-for-bit; on other implementations, `Math.sin` may return an answer within its `ulp` bound that differs in low bits from `StrictMath.sin`. **Do not write portable tests asserting `a == b` for all x and all JVMs** based solely on the two method names.

If you need bitwise protocol tests based on `sin`, use `StrictMath.sin` and pin the inputs (including `double` bits), rather than generalizing from a benchmark set that happened to match.

## 5. Java 17+ and JEP 306: `strictfp` Is Not Synonymous with `StrictMath`

Since **Java 17**, **JEP 306 — Restore Always-Strict Floating-Point Semantics** brought the language and JVM back to *always-strict* floating-point semantics. Primitive operations like addition, subtraction, multiplication, and division on `float`/`double` all use strict floating-point semantics; the `strictfp` keyword no longer alters how these expressions are evaluated on Java 17+.

This **does not erase library contract differences**:

- `strictfp` (keyword) relates to execution semantics of floating-point expressions in Java code; on Java 17+, those semantics are always strict.
- `StrictMath` is an **API class** with functions having specific `fdlibm` algorithmic requirements.
- `Math` still has certain functions permitted to use platform-specific optimizations within allowable error bounds.

In other words, code running on Java 17+ **does not automatically turn a `Math.sin` call into a `StrictMath.sin` call** just because floating-point arithmetic is always-strict. Do not treat the `strictfp` keyword as a substitute for choosing the right API or designing a reproducible pipeline.

## 6. "Same Input" Means Same *Bits*, Not Just Strings That Look Alike

Results depend on the exact bits of the argument. `0.7` in Java source code is rounded to a binary64 value. When testing reproducibility, if one system parses a string differently, casts from `float` to `double`, or rounds before calling the function, the **input bits** can differ.

~~~java
double fromDouble = 0.7;
double fromFloat = (double) 0.7f;
boolean equalBits = Double.doubleToLongBits(fromDouble)
        == Double.doubleToLongBits(fromFloat); // false
~~~

Even though when displayed with `%.1f` both may look like `0.7`, their bit representations differ. `StrictMath.sin` is not responsible for making **two arguments with different bits** produce the same result.

When storing data to reproduce a calculation, determine:

1. Whether inputs are stored as `double` binary64, `float` binary32, or decimal.
2. Whether the interchange format guarantees round-tripping, e.g., `Double.toString` + `Double.parseDouble`.
3. Whether any type conversions, unit changes, normalization, or rounding happen before the calculation.
4. Whether NaN/infinity/signed zero states and special bit-handling policies exist.

`Double.doubleToRawLongBits` preserves the raw bits of a value for diagnostics. `Double.doubleToLongBits` normalizes NaNs to a canonical representation when comparing floating-point numbers per Java conventions; choosing the bit-inspection API depends on the goal. For signed zeros, both can distinguish `+0.0` and `-0.0`.

## 7. Complete Java 17+ Example: Fixed Results and Bit Inspection

Create file `ReproducibleMathDemo.java`:

~~~java
public class ReproducibleMathDemo {
    static String bits(double x) {
        return "0x" + Long.toHexString(Double.doubleToRawLongBits(x));
    }

    public static void main(String[] args) {
        double angle = 0.7;
        double a = StrictMath.sin(angle);
        double b = StrictMath.sin(angle);

        System.out.println("strict sin hex = "
                + Double.toHexString(a));
        System.out.println("strict sin bits = " + bits(a));
        System.out.println("repeat strict identical = "
                + (Double.doubleToLongBits(a)
                == Double.doubleToLongBits(b)));
        System.out.println("strict sin(-0) bits = "
                + bits(StrictMath.sin(-0.0)));
        System.out.println("strict log(1) = "
                + StrictMath.log(1.0));
        System.out.println("strict log(-1) is NaN = "
                + Double.isNaN(StrictMath.log(-1.0)));
        System.out.println("strict sqrt(4) = "
                + StrictMath.sqrt(4.0));
        System.out.println("math sqrt(4) = "
                + Math.sqrt(4.0));
        System.out.println("ulp(1) = " + Math.ulp(1.0));
        System.out.println("nextUp(1) = " + StrictMath.nextUp(1.0));

        double x = 1.0e16, y = -1.0e16, z = 1.0;
        System.out.println("left grouped = " + ((x + y) + z));
        System.out.println("right grouped = " + (x + (y + z)));

        System.out.println("strict abs(minInt) = "
                + StrictMath.abs(Integer.MIN_VALUE));
        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException ex) {
            System.out.println("addExact overflow caught");
        }
    }
}
~~~

Compile/run:

~~~bash
javac ReproducibleMathDemo.java
java ReproducibleMathDemo
~~~

Stdout verified with Java:

~~~text
strict sin hex = 0x1.49d6e694619b8p-1
strict sin bits = 0x3fe49d6e694619b8
repeat strict identical = true
strict sin(-0) bits = 0x8000000000000000
strict log(1) = 0.0
strict log(-1) is NaN = true
strict sqrt(4) = 2.0
math sqrt(4) = 2.0
ulp(1) = 2.220446049250313E-16
nextUp(1) = 1.0000000000000002
left grouped = 1.0
right grouped = 0.0
strict abs(minInt) = -2147483648
addExact overflow caught
~~~

Reading the output with the right focus:

- The two `strict sin` lines let you observe both the hexadecimal representation of `double` and the **raw bits** of `StrictMath.sin(0.7)` under `fdlibm` semantics.
- `repeat strict identical = true` confirms two calls with the same input in the program yield identical bits; **testing on one machine alone does not prove every implementation does so**, the portability guarantee comes from the `StrictMath` specification.
- `sin(-0.0)` preserves the negative sign of 0, visible in the sign bit of binary64.
- `log(-1.0)` returns NaN and `sqrt(4.0)` returns 2.0 per function contracts; two easily observed results do not mean every input to `Math` and `StrictMath` will give identical bits.
- The two `left grouped` and `right grouped` lines illustrate that **different addition orders can give different results**, even using Java 17+ strict operations.
- `abs(Integer.MIN_VALUE)` still produces `Integer.MIN_VALUE` because the `int` range lacks the corresponding positive value. `addExact` throws when addition overflows, unrelated to trigonometric "reproducibility".

**Note:** the functions guaranteed reproducible are those whose API contract binds them like `fdlibm`. Do not take a few simple output lines of other functions as proof that the entire API is specified by the same algorithm.

## 8. Operation Order Can Still Break Whole-Program Reproducibility

Even when **each call to `StrictMath.sin`** gives identical bits for identical inputs, the program's output still depends on how operations are combined.

Example:

~~~java
double x = 1.0e16;
double y = -1.0e16;
double z = 1.0;

double left = (x + y) + z;  // 1.0
double right = x + (y + z); // 0.0
~~~

Floating-point addition is **not associative** the way ideal mathematical real numbers are: moving parentheses changes where rounding occurs. Java 17 always-strict specifies how expressions are evaluated, but **does not make two expressions with different evaluation orders equivalent**.

For parallel pipelines, `reduce`/`sum` results can be affected if addition order changes due to partitioning or traversal order. For algorithms requiring bitwise reproducibility, control reduction order, grouping, and accumulation strategy, or use an appropriate stable summation algorithm.

Similarly, replacing `a * b + c` with `Math.fma(a,b,c)` changes the rounding rule: `fma` multiplies and adds with a single rounding at the final result per spec, which can differ from doing two separate operations. Do not assume refactoring to a "mathematically equivalent" formula guarantees the **same bits**.

**Whole-program reproducibility requirements** also encompass random sources, seeds, data sorting, null/NaN handling, type conversions, locale during string formatting, version dependencies, and potential algorithm changes.

## 9. NaN, ±Infinity, ±0, and Bitwise Checks

Special floating-point values highlight the difference between mathematical comparison and bitwise comparison:

~~~java
double negativeZero = -0.0;

boolean numericallyEqual = (negativeZero == 0.0); // true
boolean sameBits = Double.doubleToRawLongBits(negativeZero)
        == Double.doubleToRawLongBits(+0.0);      // false

boolean nanEquality = (Double.NaN == Double.NaN); // false
boolean nanDetected = Double.isNaN(Double.NaN);  // true
~~~

When the argument is negative 0, some functions preserve the sign per contract, e.g., `StrictMath.sin(-0.0)` returns negative 0. With NaN handling, raw payloads can differ, and `Double.doubleToLongBits` normalizes NaNs; decide whether "bitwise identity" includes NaN payloads.

`StrictMath` results can also be NaN or infinity according to the function's domain; strict reproducibility **does not guarantee every computation yields a finite number**. Non-finite data must be validated per application semantics. You can use `Double.isFinite` when constraints require finite numbers.

If results are serialized to JSON or another system that does not support NaN/infinity as ordinary numbers, choose an explicit transport convention. That is a data-contract issue, not solved automatically by `StrictMath`.

## 10. When Should You Choose `Math`, and When `StrictMath`?

**Prefer `Math`** when you need math functions accurate per API requirements, care about performance/throughput, and **do not demand bit-for-bit reproducibility** for trig/exp/log functions across platforms. UI calculations, graphics, and many simulations or statistical tasks that accept specified error tolerances are usually a good fit after evaluating specific requirements.

**Consider `StrictMath`** when the problem requires bitwise matching for functions bound to `fdlibm`: reproducing results in cross-platform testing, exchanging numerical results between JVMs complying with the same specification, or an algorithmic component where result bits serve as output data.

Still, do not equate `StrictMath` with:

- **"Always slower."** Speed depends on the function and implementation; benchmark actual workloads.
- **"More mathematically accurate than `Math`."** It guarantees a reference algorithm for a set of functions, without turning `double` into infinite-precision arithmetic.
- **"All StrictMath methods use fdlibm."** Only the set of functions listed/defined in the documentation is bound accordingly.
- **"The same source code on two machines guarantees bit-identical output for the whole app."** Data, operation order, parallel algorithms, and other components can still differ.

A sensible approach is using `Math` for general needs, identifying **which exact points genuinely require strict reproducibility**, and choosing `StrictMath` for the appropriate calls at those points. Selection must rest on each function's actual contract, not unconditionally on the name "Strict".

## 11. Testing and Diagnostics When Bit-for-Bit Is Needed

### Testing Two Floating-Point Values

~~~java
static boolean sameCanonicalBits(double a, double b) {
    return Double.doubleToLongBits(a) == Double.doubleToLongBits(b);
}
~~~

This is an **illustrative method** and must be placed in a class; it uses the **canonical** representation for NaNs. If distinguishing payloads is required, use `Double.doubleToRawLongBits`. If only checking whether values are **approximately equal** within an error bound, bitwise comparison is inappropriate: two numbers 1 ulp apart will be treated as different.

### Testing "Close Enough"

If results do not require absolute reproducibility and only need error within an allowable bound, define tolerance based on value domain, magnitude, and function properties. For `Math` functions specifying error in `ulp`, design tests matching each function's contract rather than applying one fixed epsilon to every function and value.

### Recording Reproducibility Test Traces

Record the applicable Java/API version, architecture, input/output bits or hexadecimal representations, algorithms, and seeds if randomness is involved. When verifying across environments, run the same input vector suite and compare according to problem requirements:

1. **Bitwise:** compare hex/bits, handling NaNs and signed zeros intentionally.
2. **Numerical tolerance:** compare within error bounds with NaN/infinity handled separately.
3. **Business logic:** verify allowed/disallowed outcomes (e.g., thresholds, units, data models).

Do not mix all three assertion styles into a single test without clearly documenting success criteria.

## 12. Common Mistakes

1. **Thinking Java 17 always-strict forces all `Math.sin`, `Math.log` to be bit-identical across all platforms.** False: primitive expression semantics and library function contracts are two separate layers.
2. **Thinking `strictfp` and `StrictMath` are the same mechanism.** False: one is a language modifier, the other is an API class.
3. **Thinking every `StrictMath` method is implemented directly via `fdlibm`.** False: documentation specifies an explicit list.
4. **Treating `Math.sin(x) == StrictMath.sin(x)` on one JVM as portable proof.** False: coincidental match in practice does not replace documentation guarantees.
5. **Assuming `StrictMath` is always more accurate than `Math`.** The primary goal is algorithmic reproducibility for the corresponding function set, not a promise of "infinite precision".
6. **Applying a 1 ulp bound to every function in `Math`.** Each method has its own requirement, which may be 0.5, 1, 2 ulp, or exact to the bit.
7. **Controlling only one function while forgetting addition/reduction order.** Different operation groupings can lead to different bit results.
8. **Ignoring input bits, signed zero, and NaN.** Two strings that print similarly do not necessarily produce the same binary64; two zeros are equal under `==` yet differ in bits.
9. **Refactoring expressions to `Math.fma`, changing calculation methods, or altering pipeline structure without checking reproducibility.** The number and locations of roundings can change.
10. **Failing to benchmark before asserting which class is faster.** JIT, CPU, algorithm, and input distribution determine actual performance.
11. **Using `Double.toString`/low-precision formatting to prove bitwise equality.** Formatted output can hide discrepancies; use bits or hex when needed.
12. **Achieving bitwise reproducibility while forgetting business logic validity.** A stable result with the wrong formula or unit is still a bug.

## 13. Self-Check Questions

**1.** Why can `Math.sin(x)` differ from `StrictMath.sin(x)` in low bits?

**Answer:** `Math.sin` has an error/property contract that allows implementation choices within bounds; `StrictMath.sin` uses the specified `fdlibm` algorithmic semantics for reproducibility.

**2.** Does Java 17 always-strict mean every method in `Math` must return the same bits on every CPU?

**Answer:** No. JEP 306 governs floating-point expression semantics of the language/JVM; it does not remove the implementation freedom described in the `Math` API.

**3.** Is `StrictMath.sin` mathematically exact simply because of the name "Strict"?

**Answer:** No. Results remain `double` approximations; its key feature is adhering to a reference algorithm for cross-platform reproducibility.

**4.** Why does `(1e16 + -1e16) + 1` differ from `1e16 + (-1e16 + 1)`?

**Answer:** Binary64 addition can round at each step and is not associative; the two groupings produce `1.0` and `0.0`.

**5.** When should `Double.doubleToRawLongBits` be used instead of `==`?

**Answer:** When the criterion is bit patterns, including distinguishing `-0.0` from `+0.0` and NaN payloads if preserved. `==` expresses numeric equality, not bit identity.

**6.** Is a program using `StrictMath.log` and `StrictMath.sin` sufficient to guarantee whole-program reproducibility?

**Answer:** Not yet. You must still control input bits, calculation order, type conversions, output data, randomness, parallelism, and other pipeline components.

## References

- [Java SE 21 — StrictMath](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StrictMath.html): list of `fdlibm`-bound methods and per-method special rules.
- [Java SE 21 — Math](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html): accuracy in `ulp`, semi-monotonicity, and implementation flexibility.
- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): strict semantics changes in Java 17+.
- [Java SE 21 — Double](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html): `toHexString`, `doubleToRawLongBits`, `doubleToLongBits`, and NaN/zero handling.
- [Java Language Specification `15.4 and `4.2.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.4): floating-point expressions and evaluation rules.
