# Comparing Floating-Point Numbers with Requirement-Appropriate Tolerance — Java 17+

## 1. Objective

When working with `float` and `double`, computed results can differ slightly from the expected mathematical value due to **finite binary representation and rounding**. Therefore, checking whether two computed results are "close enough" must use an **acceptable tolerance derived from real requirements**, not an arbitrary `epsilon` constant.

~~~java
double sum = 0.1 + 0.2;
System.out.println(sum);        // 0.30000000000000004
System.out.println(sum == 0.3); // false
~~~

Goals of this lesson:

- Distinguish **exact equality comparison** from **approximate equality comparison**.
- Know when to choose **absolute tolerance**, **relative tolerance**, or a combined approach.
- Understand how to handle values near 0, very large values, `NaN`, `Infinity`, and `-0.0`.
- Know when **not to use tolerance** and instead switch to integers or `BigDecimal`.
- Write and test an approximate comparison function in Java 17+.

**Core principle:** "Close" only has meaning when defined in terms of **units of measurement, instrument/data precision, and the margin of difference the business logic accepts**.

## 2. Why `==` Usually Does Not Express What You Mean

`==` checks whether two `double` values are equal according to Java floating-point rules; it **does not implicitly allow any tolerance**.

~~~java
double actual = 0.1 + 0.2;
double expected = 0.3;

System.out.println(actual == expected); // false
System.out.println(actual - expected);  // 5.551115123125783E-17
~~~

`0.1`, `0.2`, and `0.3` cannot be represented exactly in finite binary. The sum and the literal `0.3` can end up as **two adjacent `double` values**.

However, **`==` is not always wrong**. It is appropriate when you need to compare an exact represented value intentionally, such as clearly specified finite numeric states or sentinel values. When the requirement is "the difference does not exceed an allowed margin of error", define a dedicated approximate comparison.

**Distinction:**

| Requirement | Approach |
|---|---|
| Two primitive values must be strictly equal per Java | `a == b` |
| Two measurements are acceptable if within 0.05 mm | Absolute tolerance **0.05 mm** |
| Acceptable error depends on the magnitude of the quantity | Relative tolerance |
| Need to accept differences both near 0 and at very large scales | Combined absolute + relative tolerance |
| Decimal currency must be exact to the cent | Integer model in cents or `BigDecimal` with explicit rounding |
| Need to compare a large integer ID or counter | `int`/`long`/`BigInteger`, never float/double |

## 3. Absolute Tolerance

Two values `a` and `b` are considered close under absolute tolerance `absTol` when:

\[
|a-b| \le \text{absTol}
\]

For example, a sensor measuring length with a maximum allowed deviation of **0.05 mm**:

~~~java
double targetMm = 12.0;
double measuredMm = 12.04;
double allowedErrorMm = 0.05;

boolean acceptable =
        Math.abs(measuredMm - targetMm) <= allowedErrorMm;
System.out.println(acceptable); // true
~~~

If the measurement is `12.08` mm, the difference exceeds 0.05 mm and fails.

**Advantage:** easy to explain in real-world units (`mm`, `°C`, `s`, `V`). **Limitation:** the same absolute tolerance can be overly permissive for very small numbers or overly strict for very large numbers.

For example, whether an error of 0.05 m is appropriate depends on whether you are measuring a component a few millimeters wide or a distance of kilometers.

**Never forget units:** if `a` is measured in meters and `b` in millimeters, you must **convert to the same unit before comparing**. The difference function itself has no awareness of units.

## 4. Relative Tolerance

Relative tolerance evaluates the difference relative to the **scale of the values**. A commonly used symmetric rule is:

\[
|a-b| \le \text{relTol}\times\max(|a|,|b|)
\]

Example:

~~~java
double a = 1_000_000_000.0;
double b = 1_000_000_001.0;
double relativeTolerance = 1e-8;

double difference = Math.abs(a - b);
double scale = Math.max(Math.abs(a), Math.abs(b));
boolean close = difference <= relativeTolerance * scale;

System.out.println(close); // true
~~~

The absolute difference is 1, yet relative to a scale of 1 billion it is only about `1e-9`; an allowance of `1e-8` accepts it.

**Advantage:** the error margin automatically scales with magnitude. **Major limitation:** when one value is 0, a purely relative formula is extremely strict:

~~~java
double a = 4e-10;
double b = 0.0;
double relTol = 1e-5;

// |a-b| = 4e-10; relTol * max(|a|, |b|) = 4e-15
// Result: not close under this relative-only rule.
~~~

If the business logic considers `4e-10` close enough to 0 to accept, you need an **absolute threshold near 0**. That is why many applications combine both tolerances.

## 5. Combining Absolute and Relative Tolerance

A common choice when you want "close enough by at least one criterion":

\[
|a-b| \le \max(\text{absTol},\,\text{relTol}\times\max(|a|,|b|))
\]

Equivalent check:

~~~java
difference <= absTol || difference <= relTol * scale
~~~

Interpretation:

- **Near 0:** `absTol` handles small differences that have absolute significance.
- **At large scales:** `relTol` lets the allowed difference grow with the quantity's magnitude.
- **Intermediate region:** uses whichever criterion gives the wider threshold.

| Case | absTol | relTol | What is checked |
|---|---:|---:|---|
| `0.1+0.2` vs `0.3` | `1e-12` | `1e-12` | Tiny computation error |
| `4e-10` vs `0` | `1e-9` | `1e-5` | Accepts near-zero via absolute threshold |
| `1e9` vs `1e9+1` | `0.01` | `1e-8` | Accepts deviation scaled to large magnitude |
| `12.04` vs `12.0` mm | `0.05` | `0` | Fixed instrument tolerance of 0.05 mm |

**This is an example rule, not a theorem that OR is always right for every domain.** Some systems require satisfying **both** constraints simultaneously, or need a one-sided bound check (only allowed above/below a value); in those cases, write the exact business policy.

## 6. Illustrative Java 17 Function: `nearlyEqualFinite`

The function below is intended for **two finite numbers** and two non-negative, finite thresholds. It **intentionally returns false** if an input is `NaN` or `Infinity`.

~~~java
static boolean nearlyEqualFinite(
        double a, double b, double absTol, double relTol) {
    if (!Double.isFinite(absTol) || !Double.isFinite(relTol)
            || absTol < 0 || relTol < 0 || relTol > 1) {
        throw new IllegalArgumentException("invalid tolerances");
    }

    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    if (a == b) {
        return true; // Includes +0.0 and -0.0
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));

    return difference <= absTol || difference <= relTol * scale;
}
~~~

Usage:

~~~java
System.out.println(
        nearlyEqualFinite(0.1 + 0.2, 0.3, 1e-12, 1e-12)
); // true

System.out.println(
        nearlyEqualFinite(1.0, 1.1, 1e-12, 1e-12)
); // false
~~~

**Policy choices in this function:**

1. Negative, `NaN`, or Infinite thresholds, or `relTol > 1`, are **invalid arguments**, so it throws `IllegalArgumentException`.
2. Both inputs must be **finite**; even two matching Infinities return `false` because this is not a comparison of two finite measured quantities.
3. Values equal under `==` are accepted; `+0.0` and `-0.0` are therefore considered close.
4. Otherwise, the difference must fall within **at least one of the two thresholds**.

**Arithmetic limitations:** `a-b` can still overflow to Infinity if `a` and `b` are finite yet extremely large with opposite signs; `double` multiplication and subtraction can also underflow/round. This function is designed to **illustrate and serve controlled domains**, not replace a numerically rigorous comparison algorithm across all binary64 extremes. For extreme values, specify and test separately.

## 7. Choose Tolerance Based on Requirements, Not Habit

There is no magic number like **`1e-6`**, **`1e-9`**, or **`1e-12`** that is right for every problem.

Answer these questions:

1. **What quantity is being measured?** Length, money, probability, pressure, time, coordinates, temperature?
2. **What are the units and value range?** Meters or millimeters, seconds or nanoseconds, around 0 or in the billions?
3. **What is the input error?** Sensor resolution, data rounding, algorithm accuracy?
4. **What is the consequence of a false acceptance?** A minor display glitch, or billing errors and safety alerts?
5. **What is the comparison used for?** Checking computation results, software testing, clustering data, or control decisions?
6. **Should the boundary itself be included?** `<=` allows exact boundary equality, whereas `<` does not.

For instance, if a sensor has a rated accuracy of ±0.05 mm, a **domain-grounded** choice is `absTol = 0.05` mm after unit conversion, rather than defaulting to `Double.MIN_VALUE` or `1e-12`.

For testing numerical algorithms, thresholds should consider **algorithmic error**, problem conditioning, and number formatting—not just the number of digits displayed.

## 8. Understanding `Math.ulp` and Resolution

`Math.ulp(x)` represents the size of one unit in the last place of the floating-point format at value `x` as defined by the API. It is useful for inspecting the **representable spacing** near a number.

~~~java
double one = 1.0;
double next = Math.nextUp(one);

System.out.println(next);          // 1.0000000000000002
System.out.println(Math.ulp(one)); // 2.220446049250313E-16
System.out.println(next == one);   // false
~~~

`Math.nextUp(1.0)` is the representable `double` value immediately following 1.0. At 1.0, that spacing equals `Math.ulp(1.0)`.

**Do not confuse `Double.MIN_VALUE` with a universal epsilon**: `Double.MIN_VALUE` is the smallest positive non-zero value representable as a `double`, not a "general machine error" around arbitrary values.

Comparing by ULP count can be useful when testing floating-point algorithms, but requires separate rules for negative numbers, zero, subnormals, Infinity, NaN, and magnitude. It **does not automatically replace** business tolerances like 0.05 mm.

## 9. `NaN`, Infinity, and Signed Zero

### `NaN`

~~~java
double nan = Double.NaN;
System.out.println(nan == nan);       // false
System.out.println(Double.isNaN(nan)); // true
~~~

`NaN` is not equal even to itself under `==`. Consequently, checking `Math.abs(a-b) <= tolerance` does not provide a meaningful closeness rule when an operand is NaN. You must **establish an explicit policy**: reject, return false, or throw an error.

### Infinity

~~~java
System.out.println(Double.POSITIVE_INFINITY
        == Double.POSITIVE_INFINITY); // true
~~~

The `==` operator returns true for matching Infinities, whereas `nearlyEqualFinite` above **intentionally returns false** because it only compares finite quantities. There is no single universal choice: it depends on the software contract.

### Signed Zero

~~~java
System.out.println(+0.0 == -0.0); // true
~~~

`+0.0` and `-0.0` can have different bit representations and produce opposite-signed Infinity reciprocals, yet `==` treats them as equal. If business logic must distinguish **zero signs or bit patterns**, use a dedicated API instead of approximate comparison.

**Takeaway:** separate **input validation** (`Double.isFinite`) from **approximate comparison**.

## 10. When `float`/`double` Is Not the Right Solution

Using a tolerance is not a way to legitimize an incorrect data model.

**Currency:** If you must add `0.1 + 0.2` with exact decimal precision, consider:

~~~java
java.math.BigDecimal amount =
        new java.math.BigDecimal("0.1")
                .add(new java.math.BigDecimal("0.2"));

System.out.println(amount); // 0.3
~~~

Constructing `BigDecimal` from a decimal string preserves the exact input value. Use `BigDecimal.compareTo` when comparing **numeric values**, and define `scale`/`RoundingMode` for division or monetary business rules.

**IDs / counters:** Keep `long` or `BigInteger`, and do not convert to `double` for "approximate comparison": large integers can lose precision when converted to floating-point.

**Safety limits:** For a constraint like "temperature must not exceed 80 °C", you need a clear **boundary comparison policy**, rather than replacing it with `nearlyEqual(temp, 80)` and treating every value near 80 as safe. Tolerance can make sense for sensor uncertainty, but must align with measurement uncertainty, fail-safe mechanisms, and real safety requirements.

## 11. Error Accumulation and Post-Loop Comparison

~~~java
double total = 0.0;
for (int i = 0; i < 10; i++) {
    total += 0.1;
}

System.out.println(total);        // 0.9999999999999999
System.out.println(total == 1.0); // false
~~~

Each addition can round once. Tests relying strictly on `total == 1.0` can fail even when the algorithm's error lies within acceptable bounds.

~~~java
System.out.println(
        nearlyEqualFinite(total, 1.0, 1e-12, 1e-12)
); // true
~~~

However, **do not widen tolerance excessively** just to make tests pass. If an algorithm is supposed to yield an exact result (such as handling monetary amounts in cents), fix the **computational model**. For numerical algorithms, thresholds should come from an **error budget** and representative data.

## 12. Common Mistakes

| Mistake / misconception | Why is it dangerous? | How to handle it |
|---|---|---|
| `0.1 + 0.2 == 0.3` is always true | Binary64 rounds | Specified tolerance, or exact decimal |
| Always set epsilon to `1e-9` | Units and numeric domains vary | Choose threshold per problem |
| Use only relative tolerance near zero | Relative threshold approaches 0 | Combine with an absolute threshold |
| Use only absolute tolerance for huge values | Can be overly strict | Consider relative tolerance |
| Assume `Double.MIN_VALUE` is a universal epsilon | It is the smallest positive non-zero double | Check `Math.ulp` and allowed error |
| Skip validating negative/NaN/Infinity tolerances | Comparison condition becomes meaningless | Validate thresholds first |
| Treat NaN as close to NaN because both are the same state | Not a finite number | Define an explicit NaN policy |
| Use `==` with Infinity and treat as valid measurement | Infinity is not finite | Use `Double.isFinite` when needed |
| Compare quantities in different units | Wrong conclusion despite valid syntax | Convert to the same unit |
| Accept overly large deviations due to wide `relTol` | False positives | Ground thresholds in business limits |
| Use tolerance for money or integer IDs | Masks wrong numeric model | `long` in fixed minor units or `BigDecimal` |
| Fail to test at the tolerance boundary | Bugs from `<` vs `<=` and rounding | Test right at boundaries and extremes |
| Treat the sample helper as universal for all `double`s | Overflow/underflow in `a-b` and multiplication | Specialized algorithm when required |

## 13. Complete Standalone Java 17 Example

Create a file named **`FloatingPointToleranceDemo.java`**:

~~~java
import java.math.BigDecimal;

public final class FloatingPointToleranceDemo {
    private FloatingPointToleranceDemo() {}

    static boolean nearlyEqualFinite(
            double a, double b, double absTol, double relTol) {
        if (!Double.isFinite(absTol) || !Double.isFinite(relTol)
                || absTol < 0 || relTol < 0 || relTol > 1) {
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

    public static void main(String[] args) {
        double computed = 0.1 + 0.2;
        System.out.println("computed=" + computed);
        System.out.println("exact equality=" + (computed == 0.3));
        System.out.println("decimal near="
                + nearlyEqualFinite(computed, 0.3, 1e-12, 1e-12));
        System.out.println("decimal too strict="
                + nearlyEqualFinite(computed, 0.3, 1e-18, 0));
        System.out.println("different number="
                + nearlyEqualFinite(computed, 0.4, 1e-12, 1e-12));

        System.out.println("near zero absolute="
                + nearlyEqualFinite(4e-10, 0.0, 1e-9, 0.0));
        System.out.println("near zero relative only="
                + nearlyEqualFinite(4e-10, 0.0, 0, 1e-5));

        System.out.println("large relative="
                + nearlyEqualFinite(1e9, 1e9 + 1, 0, 1e-8));
        System.out.println("large absolute only="
                + nearlyEqualFinite(1e9, 1e9 + 1, 0.01, 0));
        System.out.println("large different="
                + nearlyEqualFinite(1e9, 1e9 + 100, 0.01, 1e-8));

        System.out.println("sensor acceptable="
                + nearlyEqualFinite(12.04, 12.0, 0.05, 0));
        System.out.println("sensor rejected="
                + nearlyEqualFinite(12.08, 12.0, 0.05, 0));

        double next = Math.nextUp(1.0);
        System.out.println("next double=" + next);
        System.out.println("ULP at one=" + Math.ulp(1.0));
        System.out.println("next exact=" + (next == 1.0));

        double total = 0;
        for (int i = 0; i < 10; i++) {
            total += 0.1;
        }
        System.out.println("repeated sum=" + total);
        System.out.println("repeated near one="
                + nearlyEqualFinite(total, 1.0, 1e-12, 1e-12));

        System.out.println("signed zero="
                + nearlyEqualFinite(0.0, -0.0, 0, 0));
        System.out.println("NaN near="
                + nearlyEqualFinite(Double.NaN, Double.NaN, 1e-6, 1e-6));
        System.out.println("Infinity near="
                + nearlyEqualFinite(Double.POSITIVE_INFINITY,
                        Double.POSITIVE_INFINITY, 1e-6, 1e-6));

        BigDecimal decimal = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("decimal exact sum=" + decimal);
        System.out.println("decimal compare="
                + (decimal.compareTo(new BigDecimal("0.3")) == 0));

        try {
            nearlyEqualFinite(1.0, 1.0, -1.0, 1e-6);
        } catch (IllegalArgumentException ex) {
            System.out.println("bad tolerance=" + ex.getMessage());
        }
    }
}
~~~

**Requirements:** JDK 17 or later. Open terminal in the directory containing the file. No Maven, Gradle, or external libraries beyond the JDK needed.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 FloatingPointToleranceDemo.java
java -cp . FloatingPointToleranceDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\FloatingPointToleranceDemo.java
java -cp . FloatingPointToleranceDemo
~~~

**Exact expected stdout:**

~~~text
computed=0.30000000000000004
exact equality=false
decimal near=true
decimal too strict=false
different number=false
near zero absolute=true
near zero relative only=false
large relative=true
large absolute only=false
large different=false
sensor acceptable=true
sensor rejected=false
next double=1.0000000000000002
ULP at one=2.220446049250313E-16
next exact=false
repeated sum=0.9999999999999999
repeated near one=true
signed zero=true
NaN near=false
Infinity near=false
decimal exact sum=0.3
decimal compare=true
bad tolerance=invalid tolerances
~~~

### How to Read the Output

1. `computed` and `exact equality`: two nearby decimal expressions that do not share the same binary64 representation.
2. `decimal near=true` yet `decimal too strict=false`: **choosing the tolerance affects the conclusion**; there is no single globally correct threshold.
3. `near zero absolute=true` / `relative only=false`: absolute thresholds play a crucial role around zero.
4. `large relative=true` yet `large absolute only=false`: a difference of 1 can be small at a scale of 1 billion.
5. The two sensor lines demonstrate setting thresholds in **mm**, not language defaults.
6. `Math.nextUp` and `Math.ulp` show that representable `double` values are spaced apart by a finite step.
7. Repeatedly adding 0.1 can accumulate rounding error; approximate comparison accepts deviation within the defined rule.
8. `NaN` and Infinity are rejected by the **finite-only** function; signed zeros are accepted.
9. `BigDecimal` from strings allows exact decimal addition in the example.
10. Negative tolerance is rejected so it does not silently return meaningless results.

## 14. Exercises with Answers

### Exercise A — Approximate Equality

~~~java
double result = 0.1 + 0.2;
System.out.println(result == 0.3);
System.out.println(nearlyEqualFinite(result, 0.3, 1e-12, 1e-12));
~~~

**Answer:**

~~~text
false
true
~~~

`nearlyEqualFinite` was defined above. `==` compares exact binary values, while the function allows a small declared deviation.

### Exercise B — Near 0

Two results `a = 5e-10`, `b = 0`. Business logic accepts a maximum deviation of `1e-9` (same units).

**Answer:**

~~~java
boolean accepted = nearlyEqualFinite(5e-10, 0.0, 1e-9, 0.0);
System.out.println(accepted); // true
~~~

In this case, absolute tolerance accurately expresses the requirement.

### Exercise C — Large Values

Two numbers are `1_000_000_000` and `1_000_000_001`. A relative difference of `1e-8` is allowed.

**Answer:**

~~~java
boolean accepted =
        nearlyEqualFinite(1e9, 1e9 + 1, 0, 1e-8);
System.out.println(accepted); // true
~~~

### Exercise D — NaN Data

~~~java
double x = Double.NaN;
System.out.println(x == x);
System.out.println(nearlyEqualFinite(x, x, 1e-3, 1e-3));
~~~

**Answer:**

~~~text
false
false
~~~

The function in this lesson has a policy of **rejecting non-finite numbers**.

### Exercise E — When Should Tolerance Not Be Used?

Requirement: add decimal monetary values `0.1` and `0.2`, then compare with `0.3` exactly.

**Answer:** do not "loosen epsilon" to validate money; use integers in the smallest currency unit when appropriate or `BigDecimal` from strings:

~~~java
BigDecimal sum = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));
boolean exact = sum.compareTo(new BigDecimal("0.3")) == 0;
~~~

### Exercise F — Designing Boundary Tests

If the allowed tolerance is 0.05 mm, which values should be tested?

**Answer:** at minimum test a difference of 0, a difference smaller than the threshold, values right below/above the boundary, and a difference larger than the threshold; also test negative numbers, zero, and non-finite data per policy. Since `0.05` itself has no exact binary representation, if the contract demands an exact decimal boundary, a decimal model may be needed instead of expecting `double` bits to align exactly with mathematical boundaries.

## 15. Checklist and Conclusion

- [ ] Distinguish exact `==` from requirement-based approximate comparison.
- [ ] Understand that the source of `float`/`double` discrepancies is finite binary representation and rounding.
- [ ] Know how to choose **absolute tolerance** based on units/data resolution.
- [ ] Know how to choose **relative tolerance** when the value range varies in scale.
- [ ] Understand why near-zero values require an absolute threshold.
- [ ] Explicitly define **OR/AND** for the two thresholds according to the error-acceptance policy.
- [ ] Never impose a single epsilon across every problem.
- [ ] Validate finiteness and validity of thresholds.
- [ ] Distinguish `Double.MIN_VALUE` from ULP/resolution.
- [ ] Understand that `NaN`, Infinity, and signed zeros require explicit policies.
- [ ] Never use tolerance to compare currency, IDs, or data requiring absolute precision.
- [ ] Know that subtraction `a-b` also carries rounding/overflow risks at extremes.
- [ ] Run `FloatingPointToleranceDemo.java` with `javac`/`java` on Java 17+ and verify exact stdout.

**Conclusion:** Floating-point "close enough" comparison does not start from `1e-9`; it starts from the question **"what deviation is acceptable, in what units, and at what scale?"**. Based on the answer, choose absolute tolerance, relative tolerance, or a combination of both, handle `NaN`/Infinity explicitly, and test boundary cases. If the requirement is exact decimal or integer precision, choose an **exact data model** instead of using tolerance to mask errors.
