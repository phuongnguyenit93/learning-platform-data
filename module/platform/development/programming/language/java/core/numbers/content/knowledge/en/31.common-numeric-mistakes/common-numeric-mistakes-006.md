# Mistake: Comparing Floating-Point Numbers with an Arbitrary Epsilon

When programming with `double` or `float`, many developers replace `a == b` with `Math.abs(a - b) < 1e-9` and assume that solves all floating-point inaccuracies. That is a mistake: **there is no single absolute epsilon suitable for every value, operation, measurement unit, and business requirement**. A threshold that is too small rejects results that ought to be considered equivalent; a threshold that is too large treats genuinely different values as equal. With `NaN`, infinity, huge numbers, or overflowing subtraction, the naive formula carries additional traps.

This lesson belongs to the **Common Numeric Mistakes** section of Java Core - Numbers. Its goal is to understand the root causes of IEEE 754 error, distinguish **exact** comparison from **approximate comparison with a meaningful threshold**, apply absolute/relative/ULP errors in the right contexts, handle special values, and know when to choose `BigDecimal`.

## 1. Why Might 0.1 + 0.2 Not Equal 0.3?

`float` and `double` are binary floating-point types following IEEE 754. Most decimal fractions such as 0.1 and 0.2 have no exact finite representation in base 2. Java stores the nearest representable binary value; each operation can round according to the type's rules.

~~~java
double a = 0.1 + 0.2;
double b = 0.3;

System.out.println(a);      // 0.30000000000000004
System.out.println(b);      // 0.3
System.out.println(a == b); // false
~~~

This is an illustrative snippet used inside a Java method. The result of `a == b` is not a language bug: it tests equality of **two currently represented `double` values**, not whether "two idealized mathematical formulas on paper mean the same thing".

Some calculations produce exact results, such as small integers or fractions whose denominators are powers of 2. Therefore, claiming that "`double` can never use `==`" is also inaccurate. What matters is **the intended definition of equality** and **the origin of each value**.

## 2. An Arbitrary Epsilon Causes Two Opposite Bugs

A widespread pattern:

~~~java
static boolean almostEqualWrong(double a, double b) {
    return Math.abs(a - b) < 1e-9;
}
~~~

This method uses an **absolute error** threshold of `1e-9` in the data's units. It may fit if the system **has a matching accuracy contract**; it is not naturally right for every problem.

**Bug 1 — threshold too tight:** Suppose two large computed results differ by roughly `0.5` units due to an approved approximation process allowing up to one unit of error. An epsilon of `1e-9` will report "different", even though the application domain considers them equivalent.

**Bug 2 — threshold too wide:** If you are comparing a `1e-10` difference from a sensor capable of resolving `1e-12`, an epsilon of `1e-9` erases a meaningful distinction. Likewise, an absolute threshold of `0.01` used to compare monetary amounts can accidentally treat two amounts differing by less than a cent as equal even when a payment contract requires exact values.

What makes a threshold "wide" or "tight" depends on at least:
- **Units and scale:** meters, micrometers, seconds, percentages, or currency do not share one sensible absolute tolerance.
- **Input error:** instrument resolution, measurement precision, or data source accuracy.
- **Chain of operations:** number of additions/subtractions/multiplications/divisions, conditioning of the problem, digit cancellation, overflow/underflow risks.
- **Consequences of misclassification:** plotting charts, sensor alerts, authorization decisions, billing, or algorithm stopping criteria.

**An epsilon must come from requirements, not from a number picked because it looked familiar online.**

## 3. Three Concepts to Keep Separate: Machine Epsilon, Tolerance, and ULP

| Term | Meaning | Pitfall |
|---|---|---|
| Machine epsilon (for `double`, about `2.22 × 10^-16` around 1.0) | Relative representation spacing around 1.0 for binary floating-point numbers | Not the right threshold for all operations |
| Absolute tolerance (`absTol`) | Maximum difference measured in **data units** | Must be chosen by context; does not scale with magnitude |
| Relative tolerance (`relTol`) | Maximum difference ratio relative to a reference magnitude | Needs a policy near 0 and guards against absurdly large differences |
| ULP (*unit in the last place*) | Spacing between adjacent representable values at a given scale | Measures machine resolution at that magnitude, not business correctness |

`Math.ulp(1.0)` returns approximately `2.220446049250313E-16`; `Math.ulp(0.0)` returns `Double.MIN_VALUE` (about `4.9E-324`, the *smallest nonzero* positive `double`). `Double.MIN_VALUE` is **not** the smallest negative number: the name is easy to misinterpret.

Do not assume a 1- or 2-ULP error is always acceptable. An ill-conditioned computation can drift by many ULPs; conversely, two numbers separated by a single ULP can represent distinct value codes that must remain distinct (e.g., data keys or computation states).

## 4. Absolute Tolerance: When Does It Fit?

Checking against an absolute threshold:

\[
|a - b| \leq \varepsilon_{\text{abs}}
\]

`absTol` is measured in the same units as `a` and `b`. For instance, if a length-measuring device has a contract **accepting deviation of at most 0.01 meters**, then `absTol = 0.01` can be a well-justified domain rule.

~~~java
boolean within = Math.abs(actualMeters - targetMeters) <= 0.01;
~~~

This snippet illustrates code inside a method; it assumes `actualMeters` and `targetMeters` are finite values and `0.01` is genuinely the allowable deviation. Do not apply this formula blindly to arbitrary `double`s without input checks.

Strengths: easy to understand, works well near 0, and has clear units. Limitations: a `0.01` deviation is huge for measurements around `0.001` yet tiny for measurements in the billions.

When comparing internal calculation results, do not pick `absTol` merely because the UI displays six decimal places. **How many digits a user wants to see** and **how much error a calculation permits** are two separate requirements.

## 5. Relative Tolerance: When Magnitudes Vary Widely

A common criterion for nonzero values is:

\[
|a-b| \leq \varepsilon_{\text{rel}} \cdot \max(|a|, |b|)
\]

`relTol` is a dimensionless ratio, e.g., `1e-6` corresponds to roughly one part per million of the reference magnitude. It scales the threshold with magnitude.

For example, `a = 1_000_000_000.5` and `b = 1_000_000_000.0`: the absolute difference is `0.5`. With `relTol = 1e-9`, the relative threshold is roughly `1.0`, so they are treated as "nearly equal". This **can be completely wrong in business terms** if a `0.5` difference matters. Hence, relative comparison is not automatically correct either.

Near 0, a purely relative criterion often falls short: comparing `0.0` with `1e-13` using `relTol = 1e-9` gives a threshold around `1e-22`, reporting "different". If the intent is to allow input noise near 0 up to `absTol = 1e-12`, combine both forms.

## 6. Combining Absolute and Relative Tolerances with Control

A common criterion for **finite `double` values** is:

\[
|a-b| \leq \max\left(\varepsilon_{\text{abs}},
\varepsilon_{\text{rel}}\max(|a|,|b|)\right)
\]

Meaning: a difference is accepted when it **lies within the absolute threshold** or **within the magnitude-scaled relative threshold**. Using `max` here corresponds to a logical OR between the two error tests; do not confuse it with requiring *both* thresholds simultaneously (AND). Choosing OR vs. AND is a domain decision; this formula is **one suggested policy**, not a universal definition of equality.

Java 17 helper example:

~~~java
static boolean close(double a, double b, double absTol, double relTol) {
    if (!Double.isFinite(absTol) || absTol < 0.0
            || !Double.isFinite(relTol) || relTol < 0.0
            || relTol >= 1.0) {
        throw new IllegalArgumentException("invalid tolerances");
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }
    if (a == b) {
        return true;
    }
    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return difference <= absTol || difference <= relTol * scale;
}
~~~

This is a **method snippet** to place inside a Java class. The constraint `0 <= relTol < 1` is a **safety policy of this example** so overly huge relative tolerances are rejected; it is not a general Java mandate. `absTol` and `relTol` come from system requirements rather than hard-coding an arbitrary epsilon inside the helper.

Design choices explicitly declared:
- `NaN` and both infinities are rejected. If business logic wants `+Infinity` equal to itself, define that explicitly before using this policy.
- `+0.0` and `-0.0` are treated as equal (`a == b` is `true`). If the sign of zero matters, a different check is required.
- Uses `<=` so exact boundary points are accepted. `<` is a different rule and must not be silently swapped between tests and production code.
- With `absTol = 0` and `relTol = 0`, the helper reduces to exact numeric equality for finite values, except that it still rejects `NaN` and infinity.

**Arithmetic limits of the formula:** If `a` and `b` are huge with opposite signs, `a-b` can overflow to infinity even though both inputs are finite; e.g., `Double.MAX_VALUE - (-Double.MAX_VALUE)`. With the helper's `relTol < 1` and finite `absTol` policy, such far-apart values are still classified as "different", so subtraction overflow does not cause a wrong result to be accepted. However, do not treat this helper as an invariant numeric library for every need; if you need ultra-tight relative comparisons across extreme ranges, design an algorithm that guards overflow/underflow and evaluates conditioning.

## 7. Standalone Java 17+ Example

Create `FloatingCompareDemo.java`:

~~~java
import java.math.BigDecimal;

public final class FloatingCompareDemo {
    static boolean close(double a, double b, double absTol, double relTol) {
        if (!Double.isFinite(absTol) || absTol < 0.0
                || !Double.isFinite(relTol) || relTol < 0.0
                || relTol >= 1.0) {
            throw new IllegalArgumentException("invalid tolerances");
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) return false;
        if (a == b) return true;
        double difference = Math.abs(a - b);
        double scale = Math.max(Math.abs(a), Math.abs(b));
        return difference <= absTol || difference <= relTol * scale;
    }

    public static void main(String[] args) {
        double calculated = 0.1 + 0.2;
        System.out.println("exact binary comparison = "
                + (calculated == 0.3));
        System.out.println("domain tolerance = "
                + close(calculated, 0.3, 1e-12, 1e-12));
        System.out.println("near zero = "
                + close(1e-13, 0.0, 1e-12, 1e-9));
        System.out.println("different measurements = "
                + close(1.001, 1.0, 1e-5, 1e-6));
        System.out.println("large relative = "
                + close(1e9 + 0.5, 1e9, 1e-6, 1e-9));
        System.out.println("large absolute only = "
                + close(1e9 + 0.5, 1e9, 1e-6, 0.0));
        System.out.println("NaN = "
                + close(Double.NaN, Double.NaN, 1e-12, 1e-9));
        System.out.println("infinities = "
                + close(Double.POSITIVE_INFINITY,
                        Double.POSITIVE_INFINITY, 1e-12, 1e-9));
        System.out.println("signed zeros = "
                + close(+0.0, -0.0, 0.0, 0.0));

        double next = Math.nextUp(1.0);
        System.out.println("adjacent = " + (next > 1.0));
        System.out.println("one ulp = "
                + ((next - 1.0) == Math.ulp(1.0)));

        System.out.println("nontransitive a,b = "
                + close(0.0, 0.75, 1.0, 0.0));
        System.out.println("nontransitive b,c = "
                + close(0.75, 1.5, 1.0, 0.0));
        System.out.println("nontransitive a,c = "
                + close(0.0, 1.5, 1.0, 0.0));

        BigDecimal money = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("decimal equality = "
                + money.equals(new BigDecimal("0.3")));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 FloatingCompareDemo.java
java FloatingCompareDemo
~~~

Verified output:

~~~text
exact binary comparison = false
domain tolerance = true
near zero = true
different measurements = false
large relative = true
large absolute only = false
NaN = false
infinities = false
signed zeros = true
adjacent = true
one ulp = true
nontransitive a,b = true
nontransitive b,c = true
nontransitive a,c = false
decimal equality = true
~~~

Takeaways from the example:

- `0.1 + 0.2` differs from `0.3` in binary representation, yet can be treated as close once **an allowable error level is defined**.
- `1e9 + 0.5` and `1e9` exceed absolute threshold `1e-6` yet fall within relative threshold `1e-9`. That holds only for this helper's policy, not automatically for financial decisions.
- `NaN` and infinity are classified by explicit rules rather than letting subtraction produce `NaN` silently.
- Approximate equality can be non-transitive: `0.0` is close to `0.75` and `0.75` is close to `1.5`, yet `0.0` is not close to `1.5`.

## 8. Approximate Equality Is Not Transitive: Never Use It as Key equals

This is one of the most important reasons not to use an arbitrary epsilon everywhere.

Suppose `absTol = 1.0` and `relTol = 0`:

~~~text
a = 0.00
b = 0.75
c = 1.50

close(a, b) == true  (difference 0.75)
close(b, c) == true  (difference 0.75)
close(a, c) == false (difference 1.50)
~~~

In mathematics, an **equivalence relation** must be reflexive, symmetric, and transitive. The relation "within epsilon of each other" is in general **not transitive**, so it is not a valid `equals()` definition for objects used as keys.

Consequences of using `close(a,b)` as a class's `equals()`:

- There is no standard way to write a `hashCode()` that is both useful and satisfies the hash/equality contract across overlapping "neighborhoods" over the entire domain.
- `HashSet`/`HashMap` can yield unstable results depending on insertion order, violating equality expectations.
- A `Comparator` returning 0 for "close" pairs can break consistency and the ordering invariants `TreeSet`/`TreeMap` rely on.

**Solution:** if values need to be grouped by resolution, define an explicit **quantization/bucketing rule with fixed boundaries**, and compare bucket keys under a true equivalence relation; points near bucket edges can land in different buckets, so state the semantics clearly. Never turn a non-transitive approximate threshold into global `equals`.

When used strictly to *check a single arithmetic result* against a defined expectation, `close` is very useful. Suitability depends on **the role of the comparison**.

## 9. NaN, Infinity, and Signed Zero

IEEE 754 includes special values; an arbitrary epsilon does not handle them properly in all situations.

| Value | With Java Arithmetic Operators | What Must Be Decided |
|---|---|---|
| `Double.NaN` | `NaN == NaN` is `false`; `NaN < x` and `NaN > x` are both `false` | Reject, represent missing data, or apply a custom rule? |
| `+Infinity` and `-Infinity` | Same-sign infinities are `==`; subtraction/division can yield infinity/`NaN` | Is infinity allowed in the business domain? |
| `+0.0` and `-0.0` | `+0.0 == -0.0` is `true` | Does zero's sign carry meaning? |
| Two huge opposite-sign `double`s | `a - b` can become Infinity from overflow | Avoid jumping to conclusions from a single subtraction |
| Very small numbers near 0 | Subnormal values and rounding/underflow exist | Corresponding absolute tolerance or algorithm design |

Do not do the following without defining a policy:

~~~java
return Math.abs(a - b) <= epsilon;
~~~

If both `a` and `b` are `+Infinity`, `a - b` is `NaN`; comparing with epsilon evaluates to `false`, even though `a == b` returns `true`. If `NaN` arises during computation, silently getting `false` can hide the root error; depending on the application, check and report invalid data.

For **sorting/collection keys**, `Double.compare(a,b)` establishes a total order per Java rules: `-0.0` comes before `+0.0`, and `NaN` is ordered after positive infinity. This differs from `a == b` (which treats both zeros as equal and `NaN` as unequal to itself). Wrapper `Double.equals()` also defines semantics suited for hash collections. Do not replace a sorting comparator with a non-transitive epsilon check.

## 10. Math.ulp and Math.nextUp: Measuring Representation Spacing

`Math.ulp(x)` returns the size of one unit in the last place (*unit in the last place*) around `x`, depending on magnitude. `Math.nextUp(x)` returns the next `double` value toward positive infinity.

~~~java
double x = 1.0;
double next = Math.nextUp(x);

System.out.println(next > x);              // true
System.out.println(next - x == Math.ulp(x)); // true
~~~

Near `1.0`, the gap between two adjacent `double`s is about `2.22e-16`. At other scales, the gap can be larger or smaller. Around `1e16`, for instance, `double` cannot represent every consecutive integer: the step between representable values is already greater than 1.

ULPs are valuable when evaluating the **numerical quality of a floating-point algorithm** against a same-type reference result, especially when you understand rounding rules and input domains.

However:
- An algorithm accumulating error over many steps can differ from the ideal result by far more than a few ULPs; do not pick "4 ULPs" just because you saw it in a sample test.
- Two tiny values differing by a few ULPs may be orders of magnitude smaller than real-world measurement resolution.
- ULPs do not replace defining business tolerances; many layers separate machine error from measurement/data error.
- If checking distance by bit representation, handle negative numbers, signed zero, `NaN`, and infinity carefully. Do not cast `double` to `long` and subtract two `long`s to compute ULP distance.

ULPs are a tool for *diagnosing and quantifying machine resolution*, not another universal epsilon.

## 11. Error and Algorithm Conditioning

Not only **how numbers are stored**, but also **the structure of computations** affects error. For example, subtracting two nearly equal numbers can leave the remainder with huge relative error due to loss of significant digits (*catastrophic cancellation*) when inputs were already rounded.

~~~java
double x = 1e16;
double y = x + 1.0;

System.out.println(x == y); // true
~~~

At the `1e16` scale, adding 1 may leave the `double` representation unchanged because the ULP step already exceeds 1. If you later compute `y - x`, getting 0 does not prove no original mathematical change occurred; information was lost when representing `y`. No choice of epsilon can **recover lost digits**.

Ways to improve depend on the problem:
- Choose a more numerically stable algorithm, e.g., formulas avoiding subtraction of nearly equal quantities, or using `Math.fma` when it reduces rounding error in fused multiply-add.
- Rescale or normalize units where appropriate, while preserving business interpretation.
- Use higher precision or `BigDecimal` if exact decimal arithmetic is required and performance permits.
- Estimate or bound error from step counts and data characteristics instead of picking a number that "feels safe".

For numerical algorithm regression tests, the **expected value** usually needs to come from a higher-quality reference source than the computation under test, and the tolerance must match the algorithm's expected accuracy.

## 12. When to Use ==, Double.compare, or BigDecimal?

| Need | Appropriate Choice | Why |
|---|---|---|
| Check a flag/status encoded with exact defined `double` constants | `==`, after clear `NaN`/zero policies | No need to merge neighboring values |
| Check an approximate result of an operation within allowable error | `close(a,b,absTol,relTol)` per data domain | Threshold chosen from requirements |
| Sort `Double`s and use as sorted collection keys | `Double.compare` / consistent comparator | Preserves valid ordering rules |
| Counts, IDs, timestamps as integers within integer limits | `int`/`long` or suitable type | Avoids pushing integer problems into floating point needlessly |
| Money/decimal quotas requiring exactness | `BigDecimal` from strings or integer minor units | Clear decimal representation and rounding policies |
| Test numerical function quality near `double` limits | ULP + error/conditioning analysis | Evaluates near machine representation level |

Decimal calculation example:

~~~java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal expected = new BigDecimal("0.3");

System.out.println(a.add(b).equals(expected)); // true
~~~

`BigDecimal` does not automatically guarantee exact representation for all infinite operations: `divide` may require `RoundingMode` and `MathContext`. In addition, `BigDecimal.equals()` also checks `scale`: `2.0` is not `equals()` to `2.00`, even though `compareTo() == 0`. Choose the appropriate equality semantics.

Avoid `new BigDecimal(0.1)` if you want exact decimal 0.1: the `double` constructor preserves the actual binary value, which may not match the intended decimal representation. Use `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)` depending on the data source.

## 13. How to Set Epsilon in Unit Tests

In numerical testing, do not pick an epsilon just to "turn tests green". A good test includes:

1. **Explain the expected accuracy:** does error come from binary representation, the algorithm, or input source precision?
2. **Separate absolute and relative tolerances:** for results that can approach 0, a justified absolute threshold is usually needed; for results spanning many orders of magnitude, test relative tolerance.
3. **Test boundary cases:** near 0, very large/small numbers, negatives, signed zeros, `NaN`, infinity, operations in cancellation regions.
4. **Test values that must remain distinguishable:** avoid widening epsilon just so failing cases pass as "equal".
5. **Do not use approximate equality as a collection invariant:** if testing data structures requiring uniqueness or ordering, define clear key/`Comparator` semantics.
6. **Report actual error on failure:** print `actual`, `expected`, `difference`, allowed threshold, and unit for easy diagnosis.

For example, if a length-measurement problem specifies a maximum tolerance of `0.001 m`, write the test with `absTol = 0.001` documented as "one-millimeter measurement tolerance". An approximation accurate to `1e-8` relative error can use `relTol = 1e-8` if proven/verified for the domain; do not grab both numbers from unrelated problems and combine them at random.

With test frameworks providing `double` assertions taking a `delta`, read the contract carefully: `delta` is usually an **absolute** error and does not automatically enforce relative or combined policies. Switching assertion frameworks does not solve the origin of threshold selection.

## 14. Common Mistakes to Eliminate

1. **Hard-coding `1e-9` everywhere:** no single absolute threshold fits every value domain.
2. **Using `Double.MIN_VALUE` as a general epsilon:** this is the smallest positive `double`, not typical rounding error near 1.0.
3. **Applying `Math.ulp(1.0)` to all numbers:** representation spacing depends on magnitude; nor does it reflect business rules.
4. **Using only relative tolerance for values near 0:** the threshold shrinks toward 0 and may fail to accept meaningful absolute errors.
5. **Skipping `NaN`/infinity checks:** `Math.abs(a-b)` can be `NaN` or `Infinity`; the boolean comparison silently evaluates to false without explaining why.
6. **Using `==` or `Double.compare()` in place of approximate checks:** those APIs have their own semantics; exact comparison does not express allowable error.
7. **Using approximate comparison as `equals()`/`Comparator`:** transitivity is not guaranteed; it can break map/set contracts.
8. **Treating tolerance as a fix for unstable algorithms:** epsilon cannot recover data lost to cancellation/rounding.
9. **Changing units while keeping the same absolute threshold:** `0.001 m` must become `1 mm` when converting data from meters to millimeters if representing the same tolerance.
10. **Ignoring subtraction overflow:** two huge finite operands of opposite signs can produce an infinite difference; evaluate edge cases and input domains.
11. **Equating display precision with computational precision:** printing 2 decimal places does not prove the computation is accurate within `0.005`.
12. **Picking epsilon by raising it until tests pass:** that can mask real bugs or shift deviations that ought to be caught.

## 15. Self-Check Exercises

**Exercise 1 — threshold too wide**

Two measurements differ by `0.0005` meters, and the formal requirement allows at most `0.0001` meters. Is `Math.abs(a-b) < 0.001` appropriate?

**Answer:** No. A 0.001-meter threshold is far wider than the specified 0.0001-meter tolerance; it accepts an invalid value. Use the threshold matching the contract, checking edge cases and units.

**Exercise 2 — relative tolerance and large numbers**

`a = 1e9 + 0.5`, `b = 1e9`. Under `relTol = 1e-9` and `absTol = 1e-6` in the Section 6 helper, are the two numbers close?

**Answer:** Yes, because the relative threshold of about 1.0 exceeds the difference of 0.5. That merely reflects a **policy permitting 1 part per billion relative to magnitude**, not confirmation that the two numbers should be treated as equivalent in every business domain.

**Exercise 3 — transitivity**

With absolute threshold 1, compare `0.0`, `0.75`, and `1.5`. Why cannot this rule be used to implement `equals()`?

**Answer:** Adjacent pairs are "close", yet the outer pair is not "close". The relation is non-transitive, so it is not a proper equivalence relation for `equals()` or collection keys.

**Exercise 4 — NaN**

Is `Double.NaN == Double.NaN` `true` or `false`? If you want to reject invalid data before approximate comparison, what should you check?

**Answer:** `false`. Use `Double.isFinite(a)`/`Double.isFinite(b)` if the rule must reject both `NaN` and both infinities.

**Exercise 5 — rounding and exact equality**

A currency system requires exact decimals from strings `"0.1"` and `"0.2"`. Should you use `double` and add an epsilon?

**Answer:** No. Use `BigDecimal` constructed from strings, specifying `scale` and `RoundingMode` per contract when needed. `BigDecimal` represents decimal data accurately; it does not replace designing rounding rules.

**Exercise 6 — numbers at scale 1e16**

`double x = 1e16; double y = x + 1.0;`. If `x == y` is `true`, can you pick an epsilon to recover the exact difference of 1?

**Answer:** No. The addition rounded to the exact same representable value; information about adding 1 is lost. You must change the representation type or computation method when the problem genuinely requires distinguishing integer units at this scale.

## 16. Summary and Standard References

Do not ask "what epsilon should I use for Java?". Ask: **what units, what numerical scale, what error is allowable, and what happens if two distinct numbers are treated as equal?**

- `==` is useful when exact equality under defined floating-point semantics is intended.
- `absTol` fits when there is an allowable unit-based deviation; `relTol` handles varying magnitudes; **combining thresholds still needs quantitative justification**.
- `Math.ulp`/`Math.nextUp` help understand machine representation resolution, not automatically determine business tolerances.
- Approximate comparison is **non-transitive** and cannot replace `equals()` or comparators for data structures.
- For exact decimals, integer minor units or `BigDecimal` are usually better suited than an arbitrary epsilon.

Official documentation:
- [Double — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): IEEE 754, `NaN`, signed zero, `Double.compare`, `Double.isFinite`, and wrapper semantics.
- [Math — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `ulp`, `nextUp`, `fma`, and accuracy of floating-point functions.
- [Java Language Specification SE 17, `4.2.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): representation of `float`/`double`, special values, and floating-point behavior.
- [BigDecimal — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): decimal arithmetic, `equals`, `compareTo`, and contract-based rounding.
