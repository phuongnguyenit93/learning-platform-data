# When Should You Bound by ULP When Comparing Floating-Point Numbers in Java?

## 1. Why Is a Fixed Absolute Error Not Always Enough?

Operations on **float** and **double** use binary floating-point numbers of finite precision. Intermediate and final results may need to be rounded. Therefore, two calculations with the same mathematical answer can still yield two different bit patterns.

Example:

~~~java
double computed = 0.1 + 0.2;
double expected = 0.3;

System.out.println(computed == expected); // false
~~~

The numbers **0.1**, **0.2**, and **0.3** have no exact finite binary representation in `double`. Here the two results sit at **two consecutive `double` values**. That suggests a way to measure discrepancy in steps of the number format itself: **ULP**.

However, two values being only a few ULPs apart **does not by itself prove** the result is accurate enough for business logic. One ULP depends on the magnitude of the value: for very large numbers, a single ULP distance can be huge in physical units; near zero, a single ULP can correspond to a huge proportional difference.

The goal of this lesson is to determine **when bounding error by ULP makes sense**, when to use absolute/relative error instead, and how to write Java checks that avoid false conclusions.

## 2. What Is a ULP?

**ULP** stands for *unit in the last place*. For a finite floating-point value x, **Math.ulp(x)** in Java returns the size of one ULP at x: the positive distance to the next representable value in the direction of **increasing magnitude**. This depends on the type width (**float** or **double**) and the position of x on the number line.

Related methods:

- **Math.ulp(double)** returns double; **Math.ulp(float)** returns float.
- **Math.nextUp(x)** finds the adjacent floating-point number toward positive infinity.
- **Math.nextDown(x)** finds the adjacent number toward negative infinity.
- **Math.nextAfter(start, direction)** finds the adjacent number in the specified direction.
- **Double.toHexString(x)** and **Float.toHexString(x)** display the significand and binary exponent to inspect boundaries.

Some important landmarks:

| Value | ULP in Java | Meaning |
| --- | --- | --- |
| **Math.ulp(1.0)** | **2^−52** | Step above 1 for double |
| **Math.ulp(1.0f)** | **2^−23** | Step above 1 for float |
| **Math.ulp(0.0)** | **Double.MIN_VALUE = 2^−1074** | Smallest subnormal step for double |
| **Math.ulp(0.0f)** | **Float.MIN_VALUE = 2^−149** | Smallest subnormal step for float |
| **Math.ulp(Double.MAX_VALUE)** | **2^971** | ULP size at the largest finite double |
| **Math.ulp(Double.POSITIVE_INFINITY)** | **Infinity** | Special case; do not use as a finite tolerance |
| **Math.ulp(Double.NaN)** | **NaN** | No numeric distance to compare |

Within an interval of values where the binary exponent stays constant (*binade*), representable values are evenly spaced; when crossing into the next exponent interval, the grid step changes. **Subnormal** numbers near zero have a constant absolute spacing equal to **MIN_VALUE**.

### Trap Right at Powers of Two

At **1.0 = 2^0** in double:

~~~text
Math.nextDown(1.0) = 1.0 - 2^-53
1.0                = 1.0
Math.nextUp(1.0)   = 1.0 + 2^-52

Math.ulp(1.0)      = 2^-52
~~~

The distance to the value below **is only half** the distance to the value above. Consequently, the expression **Math.abs(a - b) / Math.ulp(a)** does not count the number of floating-point values between a and b in every case.

Distinguish two meanings commonly grouped under "N ULP error":

1. **Arithmetic distance threshold:** accept when |a − b| does not exceed **N × Math.ulp(reference)** or one ULP at a chosen scale. This is a magnitude threshold in the units of a/b.
2. **Representable-value distance:** accept when going from one value to the other takes at most N valid **nextUp/nextDown** steps. This is an integer step count, which does not always equal the ratio in item 1.

Determine which meaning your test contract intends **before choosing an algorithm**.

## 3. When Should You Set a ULP Bound?

### Suitable Cases

A ULP-based threshold is useful when:

- **Testing low-level numerical algorithms:** you have a reference value and want to measure how many rounding steps an implementation's double/float result deviates from the reference, especially when test criteria or API docs state error in ULPs.
- **Comparing results of two binary arithmetic approaches:** both compute the same quantity with the same units and the same float/double width, and are expected to differ by only a few representable steps.
- **Examining accuracy within a region of comparable magnitude:** you want a tolerance that scales with representation resolution instead of hardcoding a fixed **epsilon = 1e−9** across all scales.
- **Evaluating rounding quality:** verifying that a result is within 0, 1, 2... representable steps of an exact or high-precision reference. This count is especially meaningful when the reference has been rounded to the target type under a known rule.

**Important condition:** you must first know the algorithm's error bound or test contract. There is no default N that fits every function. "Allow 4 ULPs" is a justified decision only if backed by error analysis, API specification, empirical data, or explicit test goals.

### Cases Where You Should Not Rely Solely on ULP

- **Business logic with concrete units and acceptance bounds:** e.g., temperature difference at most 0.01 °C, position at most 1 mm, time at most 1 µs. Absolute thresholds in real units matter more.
- **Relative error is meaningful:** measuring proportional change of a quantity across many orders of magnitude. Relative limits usually express the requirement more clearly.
- **Near-zero domain:** 0 and **Double.MIN_VALUE** are exactly one representable step apart, yet the proportional difference relative to the non-zero value is 100%. A "1 ULP" threshold can be far too lenient if business logic requires the value to truly be non-zero.
- **Numerically unstable algorithms or cancellation:** output can be many ULPs away from the exact result even when absolute error is small, or vice versa. ULP does not replace analyzing the *conditioning* of the problem.
- **Comparing monetary values / identifiers / legal limits that must be exact in decimal:** use a monetary model and explicit rounding rules (e.g., BigDecimal used properly) rather than defaulting to approximate double comparison.
- **Using floating-point numbers as partitioning keys, Map keys, or equality conditions requiring transitivity:** the "close within N ULPs" relation is not transitive. It must not be stuffed arbitrarily into **equals/hashCode**.

For example, if x and y are one ULP apart, and y and z are also one ULP apart, then x and z can be **two ULPs** apart. Then **close(x,y)** and **close(y,z)** can both be true while **close(x,z)** is false.

## 4. Comparing Absolute, Relative, and ULP Tolerances

Three check types serve three types of requirements:

| Comparison method | Common rule | Suitable for |
| --- | --- | --- |
| **Absolute error** | **abs(a−b) ≤ absTol** | Practical threshold in units, especially near zero |
| **Relative error** | **abs(a−b) ≤ relTol × max(abs(a), abs(b))** | Varying magnitudes where error ratio matters |
| **Combined absolute/relative** | **abs(a−b) ≤ max(absTol, relTol × scale)** | Many application tests covering both small and large values |
| **Scale-based ULP threshold** | **abs(a−b) ≤ N × Math.ulp(scale)** | Tolerance matching representation resolution near scale |
| **Exact ULP step count** | **distanceInRepresentableValues(a,b) ≤ N** | Contract permitting at most N float/double steps |

Using **max** instead of relative tolerance alone avoids issues near 0 with a zero relative allowance. Still, **absTol** and **relTol** must be chosen from problem requirements; the formula does not generate valid thresholds by itself.

**Note:** writing the subtraction **a−b** directly can overflow to **Infinity** for two huge finite doubles of opposite signs. With step-based ULP error, you can avoid double subtraction by counting ordered bit-pattern distance. Also never use **Math.ulp(Infinity)** as a tolerance for finite comparisons.

### A Fixed Epsilon Is Not a ULP

In Java, **Math.ulp(1.0)** equals **2^−52** (about 2.22 × 10^−16), and **Math.ulp(1.0f)** equals **2^−23**. There is no **Double.EPSILON** defined as a standard constant in **java.lang.Double**. If you write **EPSILON = 1e−9**, that is merely a programmer-chosen absolute tolerance.

Even if you set **EPSILON = Math.ulp(1.0)**, it only describes resolution near 1.0, not a suitable threshold for all magnitudes.

## 5. How to Use Math.ulp: Scale-Based Threshold with Limits

When two finite `double` numbers a and b are near the same scale, an approximate ULP-level comparison can look like:

~~~java
// Illustrative function, placed inside an application class:
static boolean withinLocalUlps(double a, double b, int maxUlps) {
    if (maxUlps < 0) {
        throw new IllegalArgumentException("maxUlps must be >= 0");
    }
    if (Double.isNaN(a) || Double.isNaN(b)) {
        return false;
    }
    if (a == b) {
        return true; // also treats +0.0 and -0.0 as equal
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double scale = Math.max(Math.abs(a), Math.abs(b));
    double tolerance = maxUlps * Math.ulp(scale);
    return Math.abs(a - b) <= tolerance;
}
~~~

**This is an absolute threshold sized from the ULP at scale**, not an exact count of maxUlps representable steps. It fits when your criterion truly is that arithmetic distance threshold.

Points to control:

1. **maxUlps** must not be negative. If you allow N to be too large, **N × Math.ulp(scale)** can overflow to Infinity; use small, reasonable, verified thresholds.
2. Decide how to handle **NaN** and **Infinity**: the function above rejects NaN; two infinities of the same sign are equal via **==**, whereas an infinity vs. a finite number is not considered close.
3. **+0.0** and **−0.0** are considered equal if you do not distinguish zero's sign. In applications that must distinguish bit representations, use a dedicated rule.
4. At power-of-two boundaries, two representable steps on the smaller-number side can span a distance equal to one **Math.ulp** at the boundary point. Do not call this function "exact N-ULP counting."
5. If a and b have opposite signs, are very far apart, or were `float` values widened to `double`, this ULP scale may not properly express the test contract.

For **float**, use the **Math.ulp(float)** overload and operate on `float` when you want to measure binary32 resolution. Converting `float` to `double` and counting `double` ULPs yields an entirely different scale.

## 6. Counting Representable Steps Accurately

Across a sequence of **finite doubles**, we can map bit patterns to integers ordered monotonically with numeric value, then take the difference of their ordered positions; **BigInteger** keeps the difference from overflowing when the distance exceeds signed `long` range.

Idea for the sign bit:

- Positive **double** bit patterns use unsigned integer ordering monotonic with value.
- Negative double patterns have reversed bit order; they must be mapped into an increasing sequence.
- Both **−0.0** and **+0.0** map to the same position 0 to reflect value comparison; they differ in bits but do not count as a value-difference step.
- Exclude **NaN** and do not count steps to Infinity in this helper. Infinity is handled via **==** in the outer comparison layer.

Accurate illustrative functions for **finite double value steps**, with the rules above:

~~~java
import java.math.BigInteger;

// The following methods are placed inside the same Java class.
static long orderedBits(double x) {
    long bits = Double.doubleToRawLongBits(x);
    return bits < 0 ? Long.MIN_VALUE - bits : bits;
}

static BigInteger ulpSteps(double a, double b) {
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        throw new IllegalArgumentException("Only finite double values");
    }
    return BigInteger.valueOf(orderedBits(a))
            .subtract(BigInteger.valueOf(orderedBits(b)))
            .abs();
}

static boolean withinSteps(double a, double b, long maxSteps) {
    if (maxSteps < 0) {
        throw new IllegalArgumentException("maxSteps must be >= 0");
    }
    if (Double.isNaN(a) || Double.isNaN(b)) {
        return false;
    }
    if (a == b) {
        return true;
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }
    return ulpSteps(a, b)
            .compareTo(BigInteger.valueOf(maxSteps)) <= 0;
}
~~~

The subtraction in **orderedBits** runs on **long** under Java's two's-complement wraparound rules. This transformation uses signed integer ordering after mapping; the final difference is computed with **BigInteger** so extreme distances are not lost. For `float`, write a separate version based on **Float.floatToRawIntBits** and 32-bit width—do not blindly copy the `double` formula as-is.

This is an implementation meant for **engineering tests**. When used in a production library, include boundary tests for negative, positive, zero, subnormal, MIN_NORMAL, MAX_VALUE, NaN, and infinity; the choice to count 0 steps between opposite-signed zeros must match your contract.

## 7. Standalone Compilable and Runnable Java 17+ Example

Create the file **UlpComparisonDemo.java**:

~~~java
import java.math.BigInteger;

public class UlpComparisonDemo {
    static long orderedBits(double x) {
        long bits = Double.doubleToRawLongBits(x);
        return bits < 0 ? Long.MIN_VALUE - bits : bits;
    }

    static BigInteger ulpSteps(double a, double b) {
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            throw new IllegalArgumentException("Only finite values");
        }
        return BigInteger.valueOf(orderedBits(a))
                .subtract(BigInteger.valueOf(orderedBits(b)))
                .abs();
    }

    static boolean withinSteps(double a, double b, long maxSteps) {
        if (maxSteps < 0) {
            throw new IllegalArgumentException("Invalid maxSteps");
        }
        if (Double.isNaN(a) || Double.isNaN(b)) {
            return false;
        }
        if (a == b) {
            return true;
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }
        return ulpSteps(a, b).compareTo(BigInteger.valueOf(maxSteps)) <= 0;
    }

    static boolean withinLocalUlps(double a, double b, int count) {
        if (count < 0) {
            throw new IllegalArgumentException("Invalid count");
        }
        if (Double.isNaN(a) || Double.isNaN(b)) {
            return false;
        }
        if (a == b) {
            return true;
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }
        return Math.abs(a - b)
                <= count * Math.ulp(Math.max(Math.abs(a), Math.abs(b)));
    }

    public static void main(String[] args) {
        double one = 1.0;
        double up = Math.nextUp(one);
        double down = Math.nextDown(one);
        double down2 = Math.nextDown(down);

        System.out.println("ULP(1): " + Double.toHexString(Math.ulp(one)));
        System.out.println("up gap: " + Double.toHexString(up - one));
        System.out.println("down gap: " + Double.toHexString(one - down));
        System.out.println("nextUp steps: " + ulpSteps(one, up));
        System.out.println("down2 steps: " + ulpSteps(one, down2));
        System.out.println("approx 1 ULP includes down2: "
                + withinLocalUlps(one, down2, 1));
        System.out.println("exact 1 ULP includes down2: "
                + withinSteps(one, down2, 1));

        System.out.println("0 to min sub steps: "
                + ulpSteps(0.0, Double.MIN_VALUE));
        System.out.println("-min to +min steps: "
                + ulpSteps(-Double.MIN_VALUE, Double.MIN_VALUE));
        System.out.println("signed zero steps: " + ulpSteps(-0.0, +0.0));
        System.out.println("0.1 + 0.2 to 0.3 steps: "
                + ulpSteps(0.1 + 0.2, 0.3));

        System.out.println("NaN close: "
                + withinSteps(Double.NaN, Double.NaN, 1));
        System.out.println("Infinity self close: "
                + withinSteps(Double.POSITIVE_INFINITY, Double.POSITIVE_INFINITY, 0));
        System.out.println("Infinity vs max close: "
                + withinSteps(Double.POSITIVE_INFINITY, Double.MAX_VALUE, 1));
        System.out.println("float ULP(1): "
                + Float.toHexString(Math.ulp(1f)));
    }
}
~~~

Run command with JDK 17 or later:

~~~bash
javac --release 17 UlpComparisonDemo.java
java UlpComparisonDemo
~~~

Stdout output:

~~~text
ULP(1): 0x1.0p-52
up gap: 0x1.0p-52
down gap: 0x1.0p-53
nextUp steps: 1
down2 steps: 2
approx 1 ULP includes down2: true
exact 1 ULP includes down2: false
0 to min sub steps: 1
-min to +min steps: 2
signed zero steps: 0
0.1 + 0.2 to 0.3 steps: 1
NaN close: false
Infinity self close: true
Infinity vs max close: false
float ULP(1): 0x1.0p-23
~~~

Notable points:

- Two steps from **1.0** to **down2** have a total distance of **2^−52**, equal to **Math.ulp(1.0)**. The scale-based threshold comparison returns **true**, while the **one-step** count returns **false**.
- **0.0** and **Double.MIN_VALUE** are one step apart; the distance near zero is tiny in absolute value yet can be huge proportionally.
- **−Double.MIN_VALUE** and **+Double.MIN_VALUE** are two steps apart when treating **±0.0** as the same value.
- **0.1 + 0.2** differs from **0.3** by exactly one double step in Java 17+; that is a representation illustration, not an automatic license to accept every one-ULP error.
- **Infinity** must not be turned into a finite value via approximate comparison. Two equal infinities still return **true** under the helper's rules; if business logic forbids all infinities, exclude them upfront.

## 8. How Many ULPs Should You Allow?

There is no fixed number for every algorithm. A practical workflow:

1. **Identify the reference value:** this could be a result computed in higher precision, an exact formula rounded to the target type, a validated test dataset, or a library function's contract.
2. **Identify the committed error form:** "at most N representable steps" differs from "at most N × Math.ulp(reference)." State the definition explicitly in tests.
3. **Choose the measurement width:** if data is computed and stored as `float`, measure in `float` ULPs; if `double`, measure in `double` ULPs. Do not let **binary numeric promotion** silently change the scale.
4. **Derive N from error analysis or contract:** a correctly rounded operation may require 0 ULPs relative to a rounded reference; an approximation function may need a different N. Operation count and conditioning affect accumulated error, so "1 ULP for every calculation" is not a rule.
5. **Test boundaries:** zero, subnormals, powers of 2, normal range endpoints, negative values, NaN, infinity, near-max numbers, and cancellation cases.
6. **Add business thresholds if needed:** a ULP limit and an absolute/relative limit may be required **simultaneously**. Do not let one measure replace the other.

For example, for an algorithm computing a distance in meters, the requirement might be: deviation **at most 2 double steps** **and** absolute error **at most 10^−6 m**. Then both conditions must be checked; a result exceeding the meter threshold is rejected even if the ULP distance is tiny.

## 9. Common Scenarios

### Scenario A — Testing Two Implementations of a Math Function

An algorithm is specified to differ by at most **2 ULPs** from the standard double-rounded result. In that case, **counting ULP steps** directly expresses the contract. Tests need negative samples, positive samples, values near 0, and exponent boundaries.

Note: if the documentation defines ULP in terms of **unit spacing at the exact result** rather than representable step count, implement the exact definition stated in the contract; do not substitute integer step counting on your own.

### Scenario B — Testing Results with Relative Error

A positive measurement spans from **10^−8** to **10^8**, requiring a maximum deviation of **0.01%**. A **relative tolerance** condition expresses the requirement better than an arbitrary N ULPs. You can add `absTol` if the near-zero domain needs a suitable physical threshold.

### Scenario C — Checking Loop Convergence

A condition like **Math.abs(next - current) <= N * Math.ulp(current)** only detects changes small relative to the resolution at `current`. It **does not guarantee** the result is near the true solution: the algorithm may have stalled due to rounding, small derivatives, flat regions, or numerical bugs. Combine it with **residual**-based criteria and iteration limits where appropriate.

### Scenario D — Money and Decimal Rounding Rules

Comparing two monetary amounts with a threshold of **0.01** currency units is a problem of units and decimal rules. **BigDecimal** constructed from explicit decimal strings, combined with **setScale** and **RoundingMode** per business rules, usually expresses this accurately. Do not use double ULPs as an accounting rule.

### Scenario E — Two Expressions Producing Adjacent Numbers

**0.1 + 0.2** and **0.3** are one double step apart. If this is simply a test confirming that a numerical implementation produces results within expected rounding error, a one-step bound can be justified. If this value governs a transaction condition or data needing exact base-10 matching, use an appropriate representation and contract instead of accepting it by default.

## 10. NaN, Infinity, Signed Zero: Decide Upfront

Special values do not obey all finite comparison rules.

| Case | Java language behavior | Typical policy in test helpers |
| --- | --- | --- |
| **NaN** | **Double.NaN == Double.NaN** is **false** | Return **false**; if test expects NaN, check **Double.isNaN** separately |
| **+Infinity** vs. **+Infinity** | **== true** | Can return **true** if an infinite result is valid |
| **+Infinity** vs. finite number | **== false** | Do not compute N-ULP distance to infinity |
| **+0.0** vs. **−0.0** | **== true** | Usually the same value, though sign-bit checks may be needed |
| **0.0** vs. **Double.MIN_VALUE** | Different values | Only **one step** apart; still examine near-zero requirements |

If the sign of zero matters, for example **1.0 / +0.0** giving **+Infinity** and **1.0 / −0.0** giving **−Infinity**, use:

~~~java
boolean sameBits = Double.doubleToRawLongBits(a)
        == Double.doubleToRawLongBits(b);
~~~

This snippet illustrates code placed inside a method where **a** and **b** are already defined; it is **not** a standalone Java program. Exact bit comparison also distinguishes NaN payloads; when you only need to detect NaN, **Double.isNaN** is more appropriate.

With **Double.compare(a,b)**, Java orders **−0.0** and **+0.0** differently, whereas the **==** operator treats them as equal. Choose the right comparison for your purpose.

## 11. Why ULP Alone Is Still Not Enough to Judge Correctness

ULP measures differences **in target-format resolution**. It does not say whether the algorithm itself is **numerically stable**, nor does it reflect all constraints of the problem.

### Near Zero and Cancellation

Suppose two nearly equal numbers are subtracted. The result may be tiny in absolute value, yet have huge relative error if the operands already carried prior rounding error. If you use the ULP of the **small result** as the benchmark, even a small absolute deviation can correspond to many ULPs. If you use the ULP of the **large operands**, you may allow far too wide an error. You must know **which output** is meaningful and which scale is valid to measure.

### At Very Large Magnitudes

Near **Double.MAX_VALUE**, one ULP equals **2^971** — an enormous number in absolute units. Two results adjacent on the `double` grid can still differ far too much for an application with tight bounds in meters, seconds, or currency.

### Accumulated Algorithmic Error

Repeated additions, poorly conditioned transformations, and changing operation order can accumulate error. The ULP count of a single operation does not automatically become the ULP bound for an entire long algorithm. If an algorithm contains transcendental operations, read the accuracy specification of the **called API** rather than guessing.

**Principle:** use ULP when it is the defined, explainable, and verifiable unit of error; use business units when acceptance conditions live in the real world.

## 12. Common Mistakes to Avoid

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using **1e−9** for all numbers | Tolerance too loose near zero or too tight at other magnitudes | Choose absTol/relTol per problem, or a justified ULP scale |
| Treating **N × Math.ulp(x)** as exactly N steps in every case | Wrong at power-of-two boundaries | Distinguish arithmetic thresholds from step counting |
| Using double ULPs for results that are actually float | Comparison threshold changes with type | Check calculation/storage width |
| Picking N = 4, 8, or 16 out of habit | Masks bugs without justification | Derive from contract/error analysis |
| Using **Math.ulp(Infinity)** as epsilon | Infinity is not a finite tolerance | Classify NaN/Infinity first |
| Subtracting huge opposite-sign doubles and treating the result as finite arithmetic distance | Subtraction can overflow to Infinity | Use exact step counting or separate domain handling |
| Assuming **0.0** and **MIN_VALUE** are close and always accepting | Relative discrepancy can be huge | Add near-zero threshold or verify non-zero result |
| Changing convergence condition to "differ by at most 1 ULP" | May only confirm the algorithm stalled | Check residual, target accuracy, and business thresholds |
| Using approximate comparison as **equals/hashCode** | Approximate relation is not transitive | Use exact representation/keys or contract-based quantization |
| Ignoring **−0.0**, **NaN**, **Infinity** | Confusing or wrong test results | Define policy for each special case |

## 13. Practice Exercises

**Exercise 1.** At **1.0**, why does **Math.nextUp(1.0) − 1.0** differ from **1.0 − Math.nextDown(1.0)**?

*Answer:* 1.0 sits right on the boundary between two binary exponent intervals; the step above is **2^−52**, while the step below is **2^−53**. **Math.ulp(1.0)** equals the step in the direction of increasing magnitude, which is **2^−52**.

**Exercise 2.** If an allowed bound of **1 ULP** means "at most 1 double step," are **1.0** and **Math.nextDown(Math.nextDown(1.0))** close?

*Answer:* **No**. The two numbers are **two** consecutive values apart, even though their absolute difference equals **Math.ulp(1.0)**.

**Exercise 3.** How many finite double steps apart are **0.0** and **Double.MIN_VALUE**? Should they be accepted as equal in business logic?

*Answer:* **One step**. Whether to accept them must depend on near-zero requirements; one ULP step does not prove the proportional difference is small.

**Exercise 4.** Why should **Math.ulp(1.0)** not be used as a universal epsilon for all double results?

*Answer:* ULP size changes with number magnitude. The ULP at 1.0 does not represent resolution at 1e−100 or 1e100.

**Exercise 5.** An algorithm processing geographic distances requires a maximum error of **0.5 m**. Which criterion should be the primary acceptance condition?

*Answer:* Use absolute error in meters. ULP can be an additional detailed test tool when justified, but does not replace the 0.5 m requirement.

**Exercise 6.** **NaN** appears in both expected and actual. What does **withinSteps(NaN, NaN, 0)** in the example return, and how should you test when the result must be NaN?

*Answer:* **false**. Check **Double.isNaN(actual)** separately when NaN is the expected result.

## 14. Takeaways for Choosing Right

When designing a floating-point comparison, answer in order: **(1) What quantity is being compared? (2) Is there a bound in physical/business units? (3) Is there a relative error criterion? (4) If a ULP bound is desired, is it an arithmetic distance threshold or a representable-value step count? (5) Where do the reference and N come from? (6) How will edge values be handled?**

Bounding by ULP is most valuable in **testing the accuracy of floating-point operations/algorithms of the same type** when error is defined in representation-grid units. It must be paired with an understanding of rounding, algorithmic properties, and business thresholds.

## 15. References

- [Java SE 17 Math API — ulp, nextUp, nextDown, nextAfter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html).
- [Java SE 17 Double API — doubleToRawLongBits, compare, isFinite](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html).
- [Java SE 17 Float API — floatToRawIntBits, MIN_VALUE](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html).
- [Java Language Specification 17 — §4.2.3 Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3).
- [Java Language Specification 17 — §15.21 Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21).
