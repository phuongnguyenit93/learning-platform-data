# Normalization policy for `BigDecimal` `scale` before storing or comparing

## 1. Why is a normalization policy needed?

In Java, two `BigDecimal` objects can represent **the same mathematical value** yet have **different `scale` values**:

```java
BigDecimal a = new BigDecimal("1.0");  // scale = 1
BigDecimal b = new BigDecimal("1.00"); // scale = 2

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
```

`compareTo` only considers ordering/numeric value, while `equals` also requires the same `scale`. This difference can cause unexpected results when using `BigDecimal` as a `HashMap` key, a `HashSet` element, identity data, a value persisted in a database, or a field in a record compared with `equals`.

**Lesson objective:** establish a consistent policy to decide *when* to normalize `scale`, *how* to normalize it, and *at which boundary* (before storing, before comparing, when creating keys, when exchanging data), without losing information or silently altering values.

No single normalization approach fits every business domain. Three common goals are very different:

1. **Comparing numeric values:** `1.0` and `1.00` are considered equal; `compareTo` can be used directly.
2. **Creating a unique representation for identities/keys:** two equal numeric values need to map to the same `BigDecimal` form; consider `stripTrailingZeros`.
3. **Storing with a fixed number of decimal places:** for example monetary amounts with 2 decimal digits; `setScale(2, ...)` is needed according to a validation or rounding policy.

Confusing these three goals often causes subtle data or logic bugs.

## 2. Understanding `scale`, `precision`, and equality

`BigDecimal` stores a value in the form:

\[
\text{value} = \text{unscaledValue} \times 10^{-\text{scale}}
\]

Examples:

| Initialization string | `precision()` | `scale()` | Numeric value |
| --- | ---: | ---: | ---: |
| `"1.0"` | 2 | 1 | 1 |
| `"1.00"` | 3 | 2 | 1 |
| `"12.30"` | 4 | 2 | 12.3 |
| `"0.0000"` | 1 | 4 | 0 |
| `"1000.00"` | 6 | 2 | 1000 |

**Precision** is the number of significant digits in the representation, whereas **scale** determines the decimal point position. `MathContext(6)` limits the significant digits of an arithmetic operation; it is not a "6 digits after the decimal point" policy for storing data. To enforce a fixed scale, use `setScale`.

Key methods:

- `a.compareTo(b) == 0`: equal in **numeric value**, ignoring differences in scale.
- `a.equals(b)`: equal in both **numeric value and scale**.
- `a.hashCode()`: corresponds to `equals`; therefore numbers equal under `compareTo` with different scales usually have different hash codes.
- `a.stripTrailingZeros()`: removes redundant trailing zeros from the representation; may produce a negative scale.
- `a.setScale(targetScale, roundingMode)`: creates an object with the requested scale; may simply append zeros or require discarding digits.
- `a.toPlainString()`: outputs a decimal string without exponential notation; not a key-normalization operation.

`BigDecimal` is immutable: every transforming method returns a new object or value. You must use the returned value; calling `amount.setScale(2, ...)` without reassigning it will not modify `amount`.

## 3. Policy A — Only comparing numeric values

If the business question is "do these two numbers have the same magnitude?", **no normalization is needed before comparing**:

```java
BigDecimal supplied = new BigDecimal("10.500");
BigDecimal expected = new BigDecimal("10.5");

boolean sameNumericValue = supplied.compareTo(expected) == 0; // true
boolean greater = supplied.compareTo(expected) > 0;            // false
```

Use `compareTo` for `>`, `<`, `>=`, `<=`, or numeric equality. Do not use `equals` when scale has no business meaning.

Do not round or force scale just to "help comparison" if you need to compare original values:

```java
BigDecimal x = new BigDecimal("1.004");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.compareTo(y) == 0); // false
```

If both were rounded to 2 decimal places with `HALF_EVEN`, both would become `1.00`. Comparing after rounding is a **different business decision**, because it intentionally discards differences in the thousandths place. Be explicit about whether you are comparing original values or quantized values.

### Why can `HashSet` and `TreeSet` give different results?

`HashSet` and `HashMap` use the element's or key's `equals`/`hashCode`; therefore `new BigDecimal("1.0")` and `new BigDecimal("1.00")` are treated as two distinct keys. `TreeSet` with natural ordering uses `compareTo`; therefore those two values occupy the same sort position and the second one is not added. This is a crucial trait of `BigDecimal`: its natural ordering is **inconsistent with `equals`**.

Do not replace `HashSet` with `TreeSet` merely to avoid normalization. Define the dataset's equality rule first, then choose the appropriate implementation.

## 4. Policy B — Normalizing by numeric value for keys

When a system wants `1`, `1.0`, and `1.00` to be **the same key**, every value can be reduced to a canonical form using `stripTrailingZeros()`:

```java
BigDecimal a = new BigDecimal("1.0").stripTrailingZeros();
BigDecimal b = new BigDecimal("1.00").stripTrailingZeros();

System.out.println(a.equals(b)); // true
```

The following normalization helper handles `0` consistently and rejects `null` explicitly:

```java
import java.math.BigDecimal;
import java.util.Objects;

public static BigDecimal numericKey(BigDecimal input) {
    BigDecimal normalized =
            Objects.requireNonNull(input, "input").stripTrailingZeros();
    return normalized.signum() == 0 ? BigDecimal.ZERO : normalized;
}
```

This is an **illustrative method**; place it in a Java class or use the same-named method in the complete program in section 7.

Two notes when applying this:

**1. `stripTrailingZeros()` can produce a negative scale.**

```java
BigDecimal canonical = new BigDecimal("1000.00").stripTrailingZeros();

System.out.println(canonical.toString());      // 1E+3
System.out.println(canonical.toPlainString()); // 1000
System.out.println(canonical.scale());         // -3
```

Negative scale is valid and does not indicate an error. Do not assume the normalized form will always have `scale >= 0`. If fixed decimal digits are required, use Policy C in the next section.

**2. Display strings and `BigDecimal` keys do not share the exact same contract.**

`canonical.toPlainString()` in the example above outputs `"1000"`. Recreating `new BigDecimal("1000")` produces `scale == 0`; it is *numerically equal* but not `equals` to the canonical value with scale `-3`. Therefore, when reading keys from strings or external systems, **re-normalize both sides** whenever comparing with `equals` or using hash keys. Do not treat `toPlainString` as a scale-preserving round-trip.

The `numericKey` policy fits lookup keys, deduplication, and grouping data by **numeric value**. Apply it consistently on inserts, lookups, and when restoring data from storage. Never normalize only one data path.

## 5. Policy C — Enforcing a fixed `scale` before storing

Many storage models constrain the number of fractional digits, such as a SQL `DECIMAL(18,2)` column or a currency type with two decimal places. At this point, the policy can be:

- Valid values must be **represented exactly** at the target scale, or else rejected.
- Or values may be **rounded** according to a published business rule, then stored at the target scale.

### 5.1. Strict policy: no information loss allowed

```java
BigDecimal amount = new BigDecimal("12.3");
BigDecimal storage = amount.setScale(2, RoundingMode.UNNECESSARY);
// 12.30
```

`UNNECESSARY` requires that no non-zero digits need to be discarded. `12.3` becomes `12.30`, and `12.3400` becomes `12.34` exactly. However, `12.345` cannot be stored exactly at scale 2, so it throws `ArithmeticException`.

Use this when inputs must strictly obey a contract, such as product prices accepting cents as the smallest unit. If input data has finer granularity than permitted, a transparent validation error is better than truncating or silently rounding.

### 5.2. Policy permitting rounding

```java
BigDecimal raw = new BigDecimal("2.345");
BigDecimal stored = raw.setScale(2, RoundingMode.HALF_EVEN);
// 2.34
```

With `HALF_EVEN`, midpoints round toward the even last digit:

| Value | `setScale(2, HALF_EVEN)` |
| --- | --- |
| `2.345` | `2.34` |
| `2.355` | `2.36` |
| `12.3` | `12.30` |

Choose `RoundingMode` based on business, legal, or data-exchange contract rules: `HALF_EVEN` is not the right default for every currency or transaction. For example, `DOWN` truncates toward 0, which differs from `FLOOR` for negative numbers. Do not call `setScale(2)` without a rounding mode if inputs might require rounding: that overload can throw `ArithmeticException`.

**Principle:** clearly separate "validating that data has a valid scale" from "allowing conversion of a value to a valid scale." These two paths should have distinct method names and error handling.

## 6. Placing rules at the right system boundaries

### 6.1. Before writing to a database

Suppose column `amount DECIMAL(18,2)` holds up to 18 total decimal digits, of which 2 are fractional digits. It allows at most 16 integer digits. A safe persistence flow should:

1. Determine the domain's scale and rounding rule.
2. Validate input/nulls, out-of-range values, and other business rules.
3. Apply `setScale(2, UNNECESSARY)` if exact preservation is needed, or `setScale(2, selectedMode)` if rounding is allowed.
4. Verify that the normalized value fits the column's `precision` and range.
5. Write via JDBC/ORM with an appropriate decimal type; read back and verify if the contract demands exact equivalence.

For example, an ORM annotation `@Column(precision = 18, scale = 2)` only describes the expected column; rounding, casting, or rejection behavior across databases and drivers can vary. **Do not rely on the database to silently pick a rounding policy on behalf of the application.** In particular, the `scale` of a `BigDecimal` read back through JDBC may reflect the column/driver type rather than preserving the original input's representation.

For measurements, scientific results, or ratios with variable precision, forcing scale 2 will lose data. Choose schema, scale, and storage rules appropriate to each value type.

### 6.2. Before creating keys for `Map`, `Set`, caches, or grouping

If identity is based on numeric value:

```java
Map<BigDecimal, String> labels = new HashMap<>();
labels.put(numericKey(new BigDecimal("5.0")), "five");

String found = labels.get(numericKey(new BigDecimal("5.00")));
// "five"
```

This embedded snippet requires `import java.util.Map; import java.util.HashMap;` and the `numericKey` method defined earlier. Centralize normalization in constructors, factories, value objects, or data access layers so every insertion and lookup follows the same contract.

If scale carries business meaning—for instance measurement `"1.0"` has different resolution from `"1.00"`—**do not normalize away scale** when designing identities, audit logs, or equality checks.

### 6.3. Before comparing objects containing `BigDecimal`

A `record`, value object, or DTO with auto-generated `equals` inherits `BigDecimal.equals` behavior. Therefore:

- If scale is part of data identity, keep `BigDecimal` as-is and use `equals` normally.
- If only numeric value determines equality, normalize at object construction and keep it immutable; if implementing `equals` manually, implement a matching `hashCode`.
- For one-off numeric comparisons, use `compareTo` directly without modifying stored data.

Do not implement `equals` using `compareTo` while keeping `BigDecimal`'s default `hashCode`; that violates the contract that equal objects must have the same hash code.

### 6.4. When exchanging JSON or strings

If a system requires a text representation with **exactly two fractional digits**, use `setScale(2, ...)` followed by `toPlainString()` during serialization/output. If a system requires **a canonical decimal form by value**, you can output `numericKey(value).toPlainString()` and require the receiver to re-apply the normalization rule.

JSON permits numbers to be written with varying digit strings; serializers, parsers, and consuming languages may handle scale differently or convert to floating point. If trailing zeros or original strings must be preserved for signing or auditing, define the schema and encoding explicitly (potentially using JSON strings if the protocol allows) rather than relying on implicit library behavior.

## 7. Complete Java 17+ example

Save the file **`BigDecimalScalePolicyDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;

public class BigDecimalScalePolicyDemo {
    private static final int MONEY_SCALE = 2;

    // Key policy: same numeric value -> same normalized BigDecimal.
    static BigDecimal numericKey(BigDecimal input) {
        BigDecimal normalized =
                Objects.requireNonNull(input, "input").stripTrailingZeros();
        return normalized.signum() == 0 ? BigDecimal.ZERO : normalized;
    }

    // Strict storage policy: reject any value requiring rounding.
    static BigDecimal strictAmount(BigDecimal input) {
        return Objects.requireNonNull(input, "input")
                .setScale(MONEY_SCALE, RoundingMode.UNNECESSARY);
    }

    // Storage policy allowing rounding (business example only).
    static BigDecimal roundedAmount(BigDecimal input) {
        return Objects.requireNonNull(input, "input")
                .setScale(MONEY_SCALE, RoundingMode.HALF_EVEN);
    }

    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");

        System.out.println("numeric equals: " + (a.compareTo(b) == 0));
        System.out.println("object equals: " + a.equals(b));
        System.out.println("raw set size: "
                + new HashSet<>(List.of(a, b)).size());
        System.out.println("canonical set size: "
                + new HashSet<>(List.of(numericKey(a), numericKey(b))).size());

        BigDecimal thousand = numericKey(new BigDecimal("1000.00"));
        System.out.println("canonical text: " + thousand.toPlainString());
        System.out.println("canonical scale: " + thousand.scale());
        System.out.println("zero scale: "
                + numericKey(new BigDecimal("0.0000")).scale());

        System.out.println("strict amount: "
                + strictAmount(new BigDecimal("12.3")).toPlainString());

        try {
            strictAmount(new BigDecimal("12.345"));
        } catch (ArithmeticException ex) {
            System.out.println("reject excessive decimals");
        }

        System.out.println("round 2.345: "
                + roundedAmount(new BigDecimal("2.345")).toPlainString());
        System.out.println("round 2.355: "
                + roundedAmount(new BigDecimal("2.355")).toPlainString());
    }
}
```

Run with JDK 17 or later:

```bash
javac BigDecimalScalePolicyDemo.java
java BigDecimalScalePolicyDemo
```

Output:

```text
numeric equals: true
object equals: false
raw set size: 2
canonical set size: 1
canonical text: 1000
canonical scale: -3
zero scale: 0
strict amount: 12.30
reject excessive decimals
round 2.345: 2.34
round 2.355: 2.36
```

In the program, `numericKey` normalizes representations for stable numeric `equals`/hash behavior, while `strictAmount` and `roundedAmount` enforce **two different storage policies**. `toPlainString` determines text representation; `setScale` determines scale, and possibly rounding. These three responsibilities must not be conflated.

## 8. Edge cases that must be tested

**Zero and minus signs:** `new BigDecimal("0.0000").stripTrailingZeros()` becomes `BigDecimal.ZERO` with scale 0. If the system must preserve the verbatim input (for example `-0.00` in an incoming message), store the raw text separately; numeric normalization does not preserve all textual details.

**Negative scale:** `1000.00` after `stripTrailingZeros` can become `1E+3`, scale `-3`. This is a valid number; accept it when used as a canonical key, or use a fixed-scale policy if storage cannot handle that representation meaning.

**High scale with only trailing zeros:** `new BigDecimal("1.2300").setScale(2, UNNECESSARY)` becomes `1.23` without losing value. Counting fractional characters in the source text to reject anything over two digits differs from this "no information loss" policy; explicitly choose one of the two.

**Values near rounding boundaries:** test values such as `2.345`, `2.355`, negative numbers, and very small values. Do not use the same rounding mode out of habit for every domain. Ensure pre-rounding or post-rounding comparisons match the contract.

**Reading/writing across multiple systems:** canonicalize at the same boundary on both input and query paths; account for SQL `DECIMAL`, JSON, serializers, caches, and distributed keys having different policies.

**Collections:** test insertion/lookup in `HashMap`, `HashSet`, and `TreeSet` with `1`, `1.0`, and `1.00` to verify the intended equality rule.

**`double` input:** avoid `new BigDecimal(0.1)` when the intent is exact decimal `0.1`; conversion from `double` can already carry error before any scale normalization takes place.

**Null/exceptions:** decide whether `null` is valid. The example functions use `Objects.requireNonNull` to fail clearly. With `RoundingMode.UNNECESSARY`, `ArithmeticException` signals input violating the contract; handle it as a validation error rather than replacing with 0 or silently rounding.

## 9. Policy decision table

| Need | Approach | Notes |
| --- | --- | --- |
| Compare numeric value, ignore scale | `a.compareTo(b) == 0` | No input transformation needed |
| Compare both value and scale | `a.equals(b)` | `1.0` differs from `1.00` |
| Hash key consistent by numeric value | `numericKey(a)` before insert/lookup | Normalize on all sides; may yield negative scale |
| Store at exact scale 2, no data loss | `a.setScale(2, UNNECESSARY)` | Throws exception if rounding is needed |
| Store at scale 2, rounding allowed | `a.setScale(2, selectedMode)` | Mode must follow business contract |
| Canonical numeric string without exponent | `numericKey(a).toPlainString()` | When re-parsing, normalize if used as a key |
| Preserve original input resolution/representation | Keep `BigDecimal` and/or raw string | Do not strip trailing zeros unconditionally |

## 10. Self-check exercises

1. Why is `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` `false`, while `compareTo` gives `0`? What happens when inserting both into a `HashSet`?
2. Write a key-building function for a numeric-value counter so that `1000`, `1000.0`, and `1E+3` collide to the same key. Check the scale of the canonical value.
3. Design a `DECIMAL(18,2)` money storage API with two clear paths: (a) only exact values allowed; (b) rounding allowed per a defined rule. What happens to input `12.345` in each path?
4. A measurement system needs to distinguish resolution between `1.0` and `1.00`. Should `stripTrailingZeros` be called immediately when reading data? Why?
5. Why does `numericKey(x).toPlainString()` not automatically guarantee that `new BigDecimal(resultString).equals(numericKey(x))` for every integer ending in multiple zeros?

Hints: (1) `equals` also compares scale; `HashSet` keeps 2 elements if unnormalized. (2) apply `stripTrailingZeros` consistently to every key; integer 1000 can have scale `-3`. (3) strict path rejects; rounding path picks a result per mode, e.g., `HALF_EVEN` gives `12.34`. (4) no, because scale carries measurement meaning. (5) `toPlainString` does not encode negative scale, so re-normalization after parsing is required if using `BigDecimal.equals`.

**Practical conclusion:** name and document the policy explicitly at boundaries. Use `compareTo` for numeric comparisons; numeric-identity keys can use `stripTrailingZeros`; fixed-scale persistence uses `setScale` with an explicit data-loss rule. Normalize only when you are certain scale carries no meaningful information in the domain being processed.

Reference documentation: [Java SE 17 — `BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html), especially `compareTo`, `equals`, `hashCode`, `stripTrailingZeros`, `setScale`, and `toPlainString`.
