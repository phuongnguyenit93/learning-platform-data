# Never Change Exactness Rules Just to Shorten Runtime

## 1. The Core Problem

A numeric calculation in Java can be slow because of data types, object allocation counts, algorithms, memory access patterns, or operation counts. When optimizing, switching from `BigDecimal` to `double`, lowering `MathContext.precision`, replacing `long` with `int`, or moving where rounding occurs often makes code shorter and *may* make it faster. However, if the application before and after produces different results for the same inputs, it is no longer an equivalent optimization: **the computation contract has changed**.

Consider three monetary line items as exact decimal strings:

```text
0.005
0.005
0.005
```

If the contract requires **summing all lines exactly, then rounding the total to 2 decimal places using `HALF_UP`**, the result is `0.02`. If an "optimization" rounds **each line** before summing, the result is `0.03`. You cannot call these two approaches equivalent because they implement two different business policies.

**Lesson goals:** define the exactness contract of numeric operations; identify semantic changes during optimization; prioritize improvements that preserve results; measure performance properly; and verify both correctness and performance gains in Java 17+.

This lesson belongs to the **Performance in Java Core - Numbers** topic. The focus is numeric computation within a Java program. Data contracts with databases or APIs are an extension you must cross-check when deciding storage and exchange rules.

## 2. What Does "Correct" Mean: Arithmetic Contracts Before Benchmarks

There is no universal concept of "fast and accurate enough". Before modifying code, clearly answer the requirements below:

| Contract attribute | Question to lock down | Example |
| --- | --- | --- |
| **Data domain** | Negative, positive, 0, very large/very small; any NaN/infinity? | Quantities must be non-negative, defined upper bound |
| **Type and representation range** | `int`, `long`, `BigInteger`, `double`, `BigDecimal`? | Sum must not exceed `long` range |
| **Precision** | Absolute exactness, finite precision, or quantified error? | Decimal values must be exact to 0.01 units |
| **Rounding point** | Round per unit, per line, or at end of calculation? | `HALF_UP` once when finalizing total |
| **Rounding mode** | `HALF_EVEN`, `HALF_UP`, `DOWN`, `UNNECESSARY`...? | Reject data with more than 2 digits after decimal point |
| **Scale/format** | Value only, or representation too (`1.0` differs from `1.00`)? | Store money with `scale = 2` |
| **Overflow/exceptions** | Wrap around, saturate, or must throw error on overflow? | `Math.addExact` rejects overflow |
| **Order and reproducibility** | Must results match bit-for-bit, or stay within error tolerance? | Same input produces same output on target environment |
| **Special values** | Are `NaN`, `+0.0`, `-0.0`, `Infinity` accepted? | Statistics must not silently drop `NaN` |
| **Units/semantics** | Cents, VND, milliseconds, percentages, ratios, or counts? | Never silently switch units when changing storage type |

You must decide which criterion tests **equivalence**:

- **Equal arithmetically:** `BigDecimal.compareTo(other) == 0` when scale does not matter.
- **Equal in representation too:** `BigDecimal.equals(other)` when scale is also part of the contract.
- **Equal to a specified number of digits:** apply rounding/scale at the defined boundary, then compare.
- **Bounded error:** e.g., scientific formulas permitting absolute or relative error below a carefully specified threshold; this threshold must be approved by the problem domain, not inferred from runtime.
- **Matching error behavior too:** the same invalid inputs must continue to be rejected; overflow or non-exact division must not be turned into a bogus result.

An optimization is considered **contract-preserving** only when it satisfies every meaningful attribute. A benchmark cannot prove an incorrect calculation has become right.

## 3. Why Can Switching `BigDecimal` to `double` Break the Contract?

IEEE 754 `double` is a binary floating-point number with finite precision. Many decimal fractions such as `0.1` and `0.2` are not exactly representable in finite binary.

```java
import java.math.BigDecimal;

BigDecimal exact = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));

BigDecimal viaDouble = BigDecimal.valueOf(0.1 + 0.2);

System.out.println(exact.toPlainString());     // 0.3
System.out.println(viaDouble.toPlainString()); // 0.30000000000000004
```

This is an *embedded* snippet that needs to be placed inside `main` or another method. `BigDecimal.valueOf(double)` converts an already-existing `double` result into decimal form per `Double.toString`; it **does not recover** the exact values of the two original decimal operands.

If business logic demands an exact decimal sum, replacing `BigDecimal` with `double` merely to reduce allocations is a wrong change. If the business domain from the outset allows a documented binary error margin, `double` may be a valid choice; however, that is a **contract decision**, not an arbitrary optimization.

### 3.1. `MathContext.precision` is not a "smaller is faster and better" knob

```java
import java.math.MathContext;
import java.math.RoundingMode;

BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal p6 = one.divide(
        three, new MathContext(6, RoundingMode.HALF_EVEN));
BigDecimal p12 = one.divide(
        three, new MathContext(12, RoundingMode.HALF_EVEN));

// p6  = 0.333333
// p12 = 0.333333333333
```

Reducing precision changes the number of significant digits and can alter results in subsequent steps. If a problem demands 12 significant digits, changing to 6 just to save CPU **violates the contract**. `MathContext.UNLIMITED` can throw `ArithmeticException` when division has no finite decimal representation, such as `1 / 3`; do not return 0 or an ungrounded approximation to evade the exception.

### 3.2. `setScale` is not equivalent to `round(MathContext)`

- `setScale(2, HALF_EVEN)` determines **two digits after the decimal point**.
- `round(new MathContext(2, HALF_EVEN))` determines **two significant digits**.

For `123.45`, the first preserves `123.45` (already scale 2), whereas the second rounds to roughly `120`. Never swap the two APIs for each other even if it might reduce operations.

### 3.3. Do not remove `RoundingMode.UNNECESSARY`

```java
new BigDecimal("1.234").setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException because significant digits would be discarded.
```

If the policy is to **reject** numbers with too many significant fractional digits, changing to `setScale(2, HALF_UP)` accepts data that was previously rejected. That is a business validation change. Data being processed "more smoothly" does not prove the result is right.

## 4. Rounding Placement Is Part of the Contract

Data: three lines `0.005`, `0.005`, `0.005`, rounding mode `HALF_UP`, output scale 2.

**Policy A — round the final total:**

```java
BigDecimal total = new BigDecimal("0.005")
        .add(new BigDecimal("0.005"))
        .add(new BigDecimal("0.005"))
        .setScale(2, RoundingMode.HALF_UP);
// 0.02
```

**Policy B — round each line before summing:**

```java
BigDecimal line = new BigDecimal("0.005")
        .setScale(2, RoundingMode.HALF_UP); // 0.01

BigDecimal total = line.add(line).add(line); // 0.03
```

Both approaches can have valid business reasons. Yet they are **not interchangeable**. Do not pull `setScale()` into a loop, hoist it out of a loop, or move settlement timing without confirming rounding requirements.

`BigDecimal.add` **without passing a `MathContext`** is exact addition within representation and resource limits. If each `add` step receives a `MathContext`, an addition can round at each step; reordering or omitting the context can change the result. The same applies to `multiply`, `divide`, and `pow` with a context.

### 4.1. Double rounding

If a pipeline rounds to an intermediate precision and then calls `setScale` for display, dropped intermediate digits can cause the final rounding to diverge from rounding once on the exact mathematical value. Therefore, if you want "extra precision for speed", prove the error bound of the entire pipeline. There is no fixed number of guard digits suitable for all calculations.

### 4.2. `stripTrailingZeros()` and representation can also carry semantics

```java
BigDecimal left = new BigDecimal("1.0");
BigDecimal right = new BigDecimal("1.00");

System.out.println(left.compareTo(right) == 0); // true
System.out.println(left.equals(right));          // false
```

Normalizing with `stripTrailingZeros` can work well for numeric keys, but it changes `scale` and the results of `equals`/`hashCode`; values like `1000.00` can become `1E+3` (negative scale). Do not unconditionally strip trailing zeros to reduce size/cost when the application needs to preserve measurement units, input text, JSON outputs, or scale-sensitive keys.

## 5. Never Trade Overflow Rules for Speed

`int` and `long` are finite-range integers. In Java, ordinary integer addition/multiplication can overflow and wrap around under two's complement representation. If the contract **requires detecting overflow**, use `Math.addExact`, `Math.multiplyExact`, `Math.subtractExact` for the appropriate type:

```java
long current = 5_000L;
long incoming = 7_525L;
long cents = Math.addExact(current, incoming);

BigDecimal amount = BigDecimal.valueOf(cents, 2);
System.out.println(amount.toPlainString()); // 125.25
```

Storing **minor units** in `long` can be an efficient and exact design for fixed-scale domains (such as cents), **provided** these conditions hold:

1. All input values can be converted **exactly** to minor units.
2. The system's rounding policy is applied properly at the conversion boundary.
3. Minimum/maximum values and all intermediate calculations never exceed the `long` range.
4. Division, rates/taxes, and remainders are handled per the contract without silently using integer division.
5. Formatting, storage, and communication preserve the expected unit and `scale`.

For example, `BigDecimal.valueOf(cents, 2)` creates a decimal value from cents without going through `double`. If the contract requires variable fractional digits or values exceeding the `long` range, storing minor units in `long` may be **inappropriate**.

### 5.1. When integers exceeding `long` range are needed

Use `BigInteger` for exact calculations that do not overflow a fixed width:

```java
import java.math.BigInteger;

BigInteger factorial = BigInteger.ONE;
for (int n = 2; n <= 21; n++) {
    factorial = factorial.multiply(BigInteger.valueOf(n));
}
System.out.println(factorial); // 51090942171709440000
```

`21!` exceeds `Long.MAX_VALUE`. Replacing `BigInteger` with `long` to go faster without range validation will corrupt the value. Conversely, if the entire data domain is firmly proven to fit within `long`, you can consider a `long` design with checked arithmetic, boundary tests, and explicitly documented invariants.

**Atomicity does not cure overflow:** `AtomicLong.incrementAndGet()` protects concurrent updates yet still wraps around if it exceeds `long` bounds. When counters must never overflow, combine domain rules with appropriate conditional updates.

## 6. Floating-Point Numbers, Addition Order, and Reproducibility

With `float`/`double`, addition is not always mathematically associative when rounding occurs:

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
```

The expression `b + c` loses `1.0` due to the magnitude gap. Thus, replacing a sequential loop with parallel reduction, reordering elements, or pairing terms to "increase throughput" **can change the result**, even without changing the `double` type.

Questions to examine in the contract:

- Is bit-for-bit reproducibility required across runs, or only error within an approved tolerance?
- Is summation defined according to element order?
- Are `NaN`, `Infinity`, signed zero (`-0.0`/`+0.0`), and overflow/underflow supported?
- Is a more stable algorithm needed, such as compensated summation or pairwise summation, to reduce error?
- Are compiler/JVM transformations and math libraries in the target JDK specified appropriately?

Techniques that improve numerical stability may *reduce error*, yet if they alter legacy outputs they still must be verified against the contract. If the contract demands bit-identical results with the old algorithm, "more accurate" can still be a breaking change.

Java 17 always uses strict floating-point semantics per language rules (*always-strict floating-point semantics*); that does not turn `double` into an exact decimal number and does not make addition associative.

### 6.1. Even with `BigDecimal`, calculation order and context still matter

Exact `BigDecimal` addition, without `MathContext`, generally preserves the same mathematical value regardless of how additions are grouped; however, `scale` representation and object creation can still matter to APIs. When `MathContext` is applied at intermediate steps, evaluation order can change individual roundings. Therefore, never reorder operations, parallelize, or vectorize while ignoring defined rounding points.

## 7. Optimizations to Consider Before Reducing Exactness

The following improvements generally preserve computation rules better, **yet still require verification against the specific contract**.

### 7.1. Choose a better algorithm

Avoid recomputing the same unchanged value; use precomputation/caching for pure functions as long as the cache key includes **every semantic parameter**: operands, rounding mode, precision, scale, units, and rule version. For inputs with very large numbers, inspect algorithmic complexity, loop limits, and memory rather than truncating digits.

If a report needs min/max/count, `IntStream.summaryStatistics()` can perform a single pass instead of building multiple streams; however, preserve empty-stream handling and sum overflow behavior, and do not rely on initial min/max values when count is 0.

### 7.2. Eliminate unnecessary allocations and conversions

**Better when data is already the right type:**

```java
static BigDecimal sumAmounts(List<BigDecimal> values) {
    BigDecimal total = BigDecimal.ZERO;
    for (BigDecimal value : values) {
        total = total.add(value); // exact, without converting through double
    }
    return total;
}
```

The method above requires `import java.math.BigDecimal; import java.util.List;` and is an *embedded* method. `BigDecimal` is immutable so additions may create new objects; you cannot "mutate" an existing object with `+=`.

If inputs arrive as `String`, parse **once at the boundary** into the right type; avoid repeatedly converting `BigDecimal -> String -> double -> BigDecimal` on the hot path. You can keep shared constants/contexts for the same policy:

```java
static final MathContext MONEY_MC =
        new MathContext(18, RoundingMode.HALF_EVEN);
```

`MathContext` is immutable and can be reused when calculation rules are identical. However, never change the constant's precision or rounding mode just to reduce cost.

### 7.3. Separate numeric computation from formatting and I/O

If a workload sums one million values, do not call `toPlainString()`, formatters, or logging on every addition unless the contract requires per-step logging. Perform computations first and format at the **output boundary**. However, if the contract requires per-line rounding/normalization, never defer `setScale` to the end merely because fewer objects are created.

Moving allocation, serialization, logging, and DB access out of the CPU hot zone can yield gains without altering numeric results.

### 7.4. Use primitives within proven domains, with checked arithmetic

If rules operate on integers and the range is proven, `int`/`long` can avoid object overhead. However:

- `int` has a smaller range than `long`; casting `long` to `int` can truncate data.
- `long` is an integer and cannot represent fractions directly; use fixed units with a contract-approved factor.
- `Math.addExact`/`multiplyExact` help preserve overflow detection rules.
- Never use integer division if business logic previously permitted fractions.
- Do not assume switching to primitives is automatically faster: measure in practice.

### 7.5. Tune storage and data structures, not the math

For large datasets, sequential access patterns, CPU cache capacity, array/collection choices, boxing frequency, I/O batching, and concurrency can dictate performance. Choosing an appropriate structure must still guarantee ordering, null handling, duplicate handling, and data semantics.

For example, `Arrays.stream(intArray).sum()` uses `int` and can overflow; if the sum requires `long`, widen properly (`mapToLong`) and check overflow appropriately. Do not pick an API solely because its syntax is shorter.

## 8. Complete Java 17+ Example: Seeing Contract Changes

Create the file **`ExactnessPerformanceDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

public class ExactnessPerformanceDemo {

    // Contract A: exact addition, rounding only at the final total.
    static BigDecimal roundAtTotal(List<String> values) {
        BigDecimal total = BigDecimal.ZERO;
        for (String text : values) {
            total = total.add(new BigDecimal(text));
        }
        return total.setScale(2, RoundingMode.HALF_UP);
    }

    // Contract B: rounding each line before summing.
    static BigDecimal roundPerItem(List<String> values) {
        BigDecimal total = BigDecimal.ZERO;
        for (String text : values) {
            total = total.add(
                    new BigDecimal(text).setScale(2, RoundingMode.HALF_UP));
        }
        return total.setScale(2, RoundingMode.HALF_UP);
    }

    public static void main(String[] args) {
        List<String> amounts = List.of("0.005", "0.005", "0.005");

        System.out.println("round at total = "
                + roundAtTotal(amounts).toPlainString());
        System.out.println("round per item = "
                + roundPerItem(amounts).toPlainString());

        System.out.println("exact sum = "
                + new BigDecimal("0.1").add(new BigDecimal("0.2"))
                        .toPlainString());
        System.out.println("double sum = "
                + BigDecimal.valueOf(0.1 + 0.2).toPlainString());

        long cents = Math.addExact(5_000L, 7_525L);
        System.out.println("checked minor units = "
                + BigDecimal.valueOf(cents, 2).toPlainString());

        try {
            new BigDecimal("1.234")
                    .setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("strict scale = rejected");
        }

        BigDecimal first = new BigDecimal("1.0");
        BigDecimal second = new BigDecimal("1.00");
        System.out.println("numeric compare = "
                + (first.compareTo(second) == 0));
        System.out.println("structural equals = "
                + first.equals(second));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ExactnessPerformanceDemo.java
java ExactnessPerformanceDemo
```

Deterministic stdout:

```text
round at total = 0.02
round per item = 0.03
exact sum = 0.3
double sum = 0.30000000000000004
checked minor units = 125.25
strict scale = rejected
numeric compare = true
structural equals = false
```

What the program proves:

1. **Rounding timing is semantic.** Both functions use the same data, scale, and `HALF_UP`, yet each rounds at a different boundary and yields a different result.
2. **Switching to `double` does not preserve decimals.** Even `0.1 + 0.2` already produces a different value.
3. **Using `long` with minor units can be correct when the domain is fixed.** `Math.addExact` makes the overflow contract explicit, and `BigDecimal.valueOf(cents, 2)` restores the two-decimal-place representation without passing through `double`.
4. **`UNNECESSARY` is a rejection rule.** Changing it to another rounding mode alters which inputs the system accepts.
5. **Numeric value and representation are two separate concepts.** `compareTo` treats `1.0` and `1.00` as equal, whereas `equals` does not. Do not strip scale to "optimize cache" if the application needs to distinguish them.

This is proof of **correctness**, not a benchmark: no conclusions about fast/slow execution times can be drawn from this program's stdout.

## 9. Meaningful Benchmarks After Locking Down the Contract

An optimization workflow should proceed in order:

1. **Write the output and error-handling specification:** types, value ranges, scale, precision, rounding mode, rounding timing, overflow, and exceptions.
2. **Create a reference dataset:** typical values and edge cases. Keep independently computed expected values whenever possible.
3. **Measure baseline:** record JDK environment, CPU, heap size, input size, concurrency level, throughput/latency/GC.
4. **Optimize one clear factor:** algorithm, allocation, formatting, data structure, synchronization cost, or I/O.
5. **Run contract tests first:** verify results, errors, scale, precision, and boundary conditions.
6. **Re-measure under the same workload:** inspect median, distribution, and noise; retain an optimization only when the gain is clear and correctness is preserved.
7. **Document the decision:** why the change is safe, domain limits, and conditions requiring re-benchmarking.

### 9.1. Why not measure once with `System.nanoTime()`?

The JVM performs JIT compilation, class loading, warmup, GC, and profile-guided optimizations. A single run often mixes startup overhead with unrelated factors. The compiler can also eliminate calculations that do not affect output (*dead-code elimination*); timing such a loop can make a flawed approach look "blazingly fast".

In Java, JMH is the microbenchmarking library commonly used to control warmup, repeated iterations, JVM forks, concurrent load, and result consumption via `Blackhole`. Yet even JMH only answers **the performance of the measured workload**; it does not prove arithmetic equivalence.

### 9.2. Separate benchmark setup cost from production cost

For example, comparing `BigDecimal` against a `long` minor-units algorithm requires:

- Preparing data **outside the measured region** if only benchmarking addition; or including parsing/formatting if that is part of the actual processing path.
- Using identical inputs and unit rules, with consistent overflow handling.
- Evaluating rounding policy on inputs that are not multiples of the minor unit.
- Ensuring the measurement loop consumes results so the JVM cannot eliminate work.
- Testing medium sizes, large sizes, and boundary values.
- Measuring GC/allocation if the optimization's goal is object reduction, and measuring tail latency if the system is latency-sensitive.

Never measure the new method solely on "clean" numbers while testing the old method on numbers needing many rounding digits; differing workloads do not prove the new method is superior.

## 10. Regression Testing: What Must Be Compared?

Write tests right at the boundaries observable by the business domain.

**Decimal cases to include:**

| Input / characteristic | Goal |
| --- | --- |
| `"0.1" + "0.2"` | Detect conversion through `double` |
| `0.005` repeated 3 times | Detect changed rounding point |
| `"1.0"` and `"1.00"` | Distinguish numeric value from scale |
| `1.234` with scale 2 + `UNNECESSARY` | Preserve rejection behavior |
| `Long.MAX_VALUE + 1` with `Math.addExact` | Verify overflow is rejected |
| Negative numbers and midpoints like `-2.345`, `2.345`, `2.355` | Verify rounding mode |
| Very small and very large values | Verify precision/scale/exponent and type bounds |
| Non-terminating division like `1/3` | Verify `MathContext` and exceptions |
| `NaN`, ±infinity, `-0.0` if using `double` | Verify rules for special values |

If the contract requires exactness to the cent, compare **contract-normalized values and scales**, rather than taking `doubleValue()` of two `BigDecimal` instances and using `==`. If the contract requires preserving representation, verify `equals`, `scale()`, or output strings. If the contract permits tolerance, define absolute/relative error appropriately near 0, at extremes, and for `NaN` and infinity.

You can apply **differential testing**: run both the baseline and optimized versions on the same dataset and compare outputs under the specified equivalence relation. This catches regressions, though a buggy baseline does not automatically become the right standard; when in doubt, check business requirements or an independent oracle.

### 10.1. Correctness tests and performance tests have different jobs

- Unit/property tests: confirm correctness, data ranges, exceptions, and rounding.
- Benchmarks: confirm timing/resources, variance, and scalability.
- Integration tests: confirm data types, database scale, serialization, and the full pipeline.
- Concurrency tests: confirm shared state and processing order do not drop or alter data under the contract.

A benchmark that runs fast and throws no exceptions can still output wrong numbers. A unit test that passes on a few inputs still does not prove production performance.

## 11. Making Decisions When an Optimization Changes Results

There are cases where the runtime gains are so large that the business wants to accept lower precision. This can be valid **only with an explicit contract change**, such as replacing "absolute exactness" with "relative error below threshold X over domain Y", with agreed evaluation methods and failure handling.

When proposing such a change, state clearly:

1. **Before:** current input, output, and error rules.
2. **After:** new type/precision/rounding/error tolerance, and which inputs change results.
3. **Impact:** money, taxes, quota limits, comparison decisions, downstream APIs, formatting, and auditing.
4. **Acceptance level:** who has authority to approve the contract change; migration/backfill procedures for already-stored data.
5. **Evidence:** differential tests, error analysis, and benchmarks on real workloads.
6. **Recovery plan:** feature flags, API versioning, or rollback if needed.

If there is no request or approval to change the contract, keep the existing standard and seek safer optimizations. Never silently sacrifice exactness to hit a throughput target or shave off a few milliseconds.

## 12. Common Pitfalls

| Optimization mistake | Consequence | Right approach |
| --- | --- | --- |
| Replacing `BigDecimal` with `double` without checking requirements | Different decimal values, rounding/overflow/NaN issues | Confirm error tolerance first; keep BigDecimal if exactness is needed |
| Lowering `MathContext` for speed | Loses significant digits in current and downstream steps | Keep contract precision; optimize other costs |
| Moving `setScale` from end into the loop | Changes rounding point, corrupts total | Preserve rounding boundaries |
| Changing `HALF_EVEN` to `HALF_UP` arbitrarily | Different results at midpoints | Rounding mode follows business rules |
| Dropping `UNNECESSARY` | Accepts inputs previously rejected | Preserve validation |
| Switching `BigInteger` to `long` without range checks | Integer overflow | Switch only when range is proven, use checked arithmetic |
| Using `int` for large sums to save memory | Overflows `int` range | Size types properly from inputs and sums |
| Parallelizing `double` reduction while expecting bit-identical output | Different addition order, different result | Specify order or valid tolerance |
| Calling `stripTrailingZeros` everywhere | Loses required scale/representation | Normalize only at contract-approved boundaries |
| `BigDecimal.valueOf(doubleSum)` to "fix" double error | Only converts existing error to decimal form | Compute directly from exact decimal data |
| Benchmarking without numeric tests | Broken optimization can look faster | Place correctness gate before performance gate |
| Timing a single run with `nanoTime()` | Easily skewed by JIT/GC/OS noise | Benchmark with warmup, forks, multiple samples, and proper workload |
| Benchmarking parsing in old version but skipping parsing in new version | Unfair comparison | Measure same processing boundaries and same inputs |
| Relying on output from a few "clean" numbers | Misses boundary bugs | Test negatives, zero, large, tiny, ties, overflow, precision |

## 13. Applied Exercises

1. A development team wants to replace all `BigDecimal` usage in a tax system with `double` because benchmarks are faster. What must you ask and verify before accepting?
2. There are 1,000 data rows, each `0.005` units. Calculate the total under "round each line with HALF_UP" and "round once at total". How do the two results differ? Which policy is right if an invoice is defined as the sum of rounded line items?
3. A `sum` function currently uses `Math.addExact` to reject overflow. Does switching to ordinary `+` addition preserve the contract? Construct a boundary case.
4. A floating-point metric is aggregated using `double`; the new version uses `parallelStream()` for addition. Why is a difference in the last digit not always a bug, yet cannot simply be ignored either?
5. When can you use `long` counting cents instead of `BigDecimal` in a pricing system? List the conversion, overflow, and rounding rules.
6. If `"1.0"` and `"1.00"` are used as `HashMap` keys, could replacing them with `stripTrailingZeros()` in a new code path affect lookups?
7. Plan a benchmark for a function processing 10 million values, distinguishing parsing, arithmetic, logging, and serialization costs; propose contract tests before measuring.

**Hints:** (1) verify rounding, scale, units, error tolerance, domain, serialization, and boundary inputs; do not rely solely on benchmarks. (2) per-line rounds to `0.01` so total is `10.00`; rounding total `5.000` gives `5.00`. If the invoice defines the sum of rounded lines, `10.00` is right. (3) does not preserve contract: `Long.MAX_VALUE + 1` wraps with `+`, whereas `addExact` throws `ArithmeticException`. (4) `double` addition is non-associative, so differences are acceptable only if the error/reproducibility contract allows them. (5) fixed scale, sufficient range, exact conversion, checked arithmetic, and transparent rounding rules. (6) yes, because `equals/hashCode` treat scale as part of identity. (7) measure the same pipeline with warmup/forks; verify correctness against an oracle first.

## 14. Takeaways for Performance Decisions

A successful arithmetic optimization must have **two independent proofs**: (1) results, errors, and representations satisfy the defined contract; (2) runtime or resources actually improve under a representative workload. Changes such as lowering precision, swapping numeric types, moving rounding points, or dropping overflow checks can alter the problem itself; never make them merely to reduce runtime.

Prioritize algorithmic improvements, avoid redundant conversions, isolate formatting/I/O, choose suitable data structures, cache pure results with complete keys, and benchmark under controlled conditions. When trading off exactness is necessary, define it as an **intentional contract change**, with explicit scope, error bounds, tests, and approval.

Java 17 references:
- [`BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), [`MathContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html), [`RoundingMode`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html).
- [`BigInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html), [`Math`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html), [`Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html).
- [Java Language Specification §15, §17](https://docs.oracle.com/javase/specs/jls/se17/html/index.html) for numeric expression and Java execution rules.
