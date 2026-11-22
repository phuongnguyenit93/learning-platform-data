# BigDecimal.equals() considers both value and scale

## Learning objectives

In Java, two `BigDecimal` instances can represent the **same numeric value** yet **not be equal under `equals(Object)`**. The reason is that `BigDecimal.equals()` considers **both value and `scale`**, whereas `compareTo()` determines ordering by numeric value. This difference directly affects `hashCode()`, `HashSet`, `HashMap`, `TreeSet`, verifying calculation results, and designing objects that hold money or decimal numbers.

After this lesson, you can accurately explain and predict the results of `equals`, `compareTo`, and `hashCode`; choose the right comparison for the purpose; handle changes caused by `stripTrailingZeros()` and `setScale()`; test zero cases and arrays/collections containing `BigDecimal`; and design keys that use numeric-value equality if the application requires it.

## 1. A BigDecimal consists of an unscaled value and a scale

A `BigDecimal` decimal number is represented by an **unscaled integer** (`unscaledValue`, of type `BigInteger`) and a **scale** (of type `int`). Its numeric value is:

```text
value = unscaledValue × 10^(-scale)
```

Examples:

| Representation | `unscaledValue()` | `scale()` | Numeric value |
| --- | ---: | ---: | ---: |
| `new BigDecimal("2")` | `2` | `0` | `2` |
| `new BigDecimal("2.0")` | `20` | `1` | `2` |
| `new BigDecimal("2.00")` | `200` | `2` | `2` |
| `new BigDecimal("0.00")` | `0` | `2` | `0` |
| `new BigDecimal("1E+3")` | `1` | `-3` | `1000` |

Therefore, **scale is not merely about displayed decimal places**: it is a component of the numeric representation. Scale **can be negative**; for example, `1E+3` has `scale() == -3`. Two `BigDecimal` values with different scales can have the same numeric value.

The values `2.0` and `2.00` show this difference clearly:

```text
2.0  = 20  × 10^(-1)
2.00 = 200 × 10^(-2)

Same numeric value: 2
Different (unscaled value, scale) representations:
(20, 1) versus (200, 2)
```

Distinguishing **representation** from **numeric value** is the key to this lesson.

## 2. `equals()` compares representation; `compareTo()` compares numeric value

By `BigDecimal`'s contract:

- `a.equals(b)` returns `true` when `b` is a `BigDecimal` with **the same numeric value and the same scale**. For example, `2.0` equals `2.0`, but **does not equal** `2.00` under `equals`.
- `a.compareTo(b) == 0` confirms that **two numeric values are equal**, even if their scales differ. `2.0` and `2.00` have `compareTo` equal to `0`.
- `compareTo` returns a negative number, `0`, or a positive number depending on whether `a` is less than, equal to, or greater than `b`. Do not rely on the exact magnitude of the negative/positive number returned.
- `a.equals(null)` returns `false`. `a.compareTo(null)` throws `NullPointerException`; the argument must be a non-`null` `BigDecimal`.
- `equals` only recognizes a proper `BigDecimal` object; it does not treat `String "2.0"` or `Integer 2` as equal to a `BigDecimal`.

Side by side:

| Comparison | Result | Explanation |
| --- | --- | --- |
| `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` | `false` | Scales are `1` and `2` respectively |
| `new BigDecimal("2.0").compareTo(new BigDecimal("2.00")) == 0` | `true` | Same numeric value `2` |
| `new BigDecimal("2").equals(new BigDecimal("2.0"))` | `false` | Scale `0` versus `1` |
| `new BigDecimal("0.0").equals(new BigDecimal("0.00"))` | `false` | Both are zero, but scales differ |
| `new BigDecimal("0.00").compareTo(BigDecimal.ZERO) == 0` | `true` | Both values are zero |
| `new BigDecimal("2.0").equals(new BigDecimal("2.0"))` | `true` | Same representation under `equals` rules |

This is the special case described in the Java documentation as **natural ordering inconsistent with equals**: two values with `compareTo == 0` do not necessarily have `equals == true`. Never automatically substitute one method for the other.

## 3. Runnable example: seeing both equality relations in full

Save this Java 17+ program to **`BigDecimalEqualityDemo.java`**:

```java
import java.math.BigDecimal;

public class BigDecimalEqualityDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        BigDecimal c = new BigDecimal("2.0");

        System.out.println("a: " + a.toPlainString());
        System.out.println("b: " + b.toPlainString());
        System.out.println("a scale: " + a.scale());
        System.out.println("b scale: " + b.scale());
        System.out.println("a unscaled: " + a.unscaledValue());
        System.out.println("b unscaled: " + b.unscaledValue());

        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("a.compareTo(b) == 0: "
                + (a.compareTo(b) == 0));
        System.out.println("a.equals(c): " + a.equals(c));

        BigDecimal zeroOne = new BigDecimal("0.0");
        BigDecimal zeroTwo = new BigDecimal("0.00");
        System.out.println("zeroOne.equals(zeroTwo): "
                + zeroOne.equals(zeroTwo));
        System.out.println("zeroOne.compareTo(zeroTwo) == 0: "
                + (zeroOne.compareTo(zeroTwo) == 0));

        BigDecimal difference = b.subtract(a);
        System.out.println("difference: "
                + difference.toPlainString());
        System.out.println("difference.equals(ZERO): "
                + difference.equals(BigDecimal.ZERO));
        System.out.println("difference.compareTo(ZERO) == 0: "
                + (difference.compareTo(BigDecimal.ZERO) == 0));
    }
}
```

Compile and run:

```bash
javac BigDecimalEqualityDemo.java
java BigDecimalEqualityDemo
```

**Exact output:**

```text
a: 2.0
b: 2.00
a scale: 1
b scale: 2
a unscaled: 20
b unscaled: 200
a.equals(b): false
a.compareTo(b) == 0: true
a.equals(c): true
zeroOne.equals(zeroTwo): false
zeroOne.compareTo(zeroTwo) == 0: true
difference: 0.00
difference.equals(ZERO): false
difference.compareTo(ZERO) == 0: true
```

Analyzing two key details:

1. `b.subtract(a)` computes `2.00 - 2.0`. The result has **numeric value 0**, but its scale is `2`, so `toPlainString()` displays `0.00`. `BigDecimal.ZERO` has scale `0`; hence `difference.equals(BigDecimal.ZERO)` returns `false`.
2. To ask "is the result equal to **zero**?", use `difference.signum() == 0` or `difference.compareTo(BigDecimal.ZERO) == 0`. `signum()` returns `-1`, `0`, or `1` according to the numeric sign, independent of scale.

**Do not misunderstand:** `BigDecimal`'s `equals` is not a "bug." It has a **specific contract**, in which scale is meaningful. Bugs occur when an application needs numeric-value equality yet uses `equals` without realizing the difference.

## 4. Why does `hashCode()` also distinguish scale?

`BigDecimal.hashCode()` is consistent with `BigDecimal.equals()`: if two `BigDecimal` instances are equal under `equals`, their hashes must be equal. Because `equals` treats `2.0` and `2.00` as **different**, their hash codes are **allowed** to differ; the Java implementation produces different hashes for this pair.

You can think of it according to this model:

```text
equals(BigDecimal):
  participating in comparison: numeric value + scale

hashCode(BigDecimal):
  must be compatible with all components that determine equals
```

**Do not infer the converse:** `a.hashCode() == b.hashCode()` does not prove `a.equals(b)`. Hash code collisions are legal.

This difference affects structures like `HashSet` or `HashMap` because they use both `hashCode` and `equals` when identifying elements/keys. If you put `new BigDecimal("2.0")` as a key and then look up `new BigDecimal("2.00")`, they are not the same key under `HashMap`'s semantics.

### 4.1. `HashSet` and `TreeSet` do not produce the same result

`HashSet` relies on `equals/hashCode`; `TreeSet` with natural ordering relies on `compareTo` to recognize two equivalent elements during sorting/searching.

Save to **`BigDecimalCollectionsDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class BigDecimalCollectionsDemo {
    public static void main(String[] args) {
        BigDecimal twoOneDecimal = new BigDecimal("2.0");
        BigDecimal twoTwoDecimals = new BigDecimal("2.00");
        BigDecimal twoThreeDecimals = new BigDecimal("2.000");

        Set<BigDecimal> hashSet = new HashSet<>();
        hashSet.add(twoOneDecimal);
        hashSet.add(twoTwoDecimals);

        Set<BigDecimal> treeSet = new TreeSet<>();
        treeSet.add(twoOneDecimal);
        treeSet.add(twoTwoDecimals);

        System.out.println("hashSet size: " + hashSet.size());
        System.out.println("treeSet size: " + treeSet.size());
        System.out.println("hashSet contains 2.000: "
                + hashSet.contains(twoThreeDecimals));
        System.out.println("treeSet contains 2.000: "
                + treeSet.contains(twoThreeDecimals));
        System.out.println("2.0 equals 2.00: "
                + twoOneDecimal.equals(twoTwoDecimals));
        System.out.println("2.0 compares as 2.00: "
                + (twoOneDecimal.compareTo(twoTwoDecimals) == 0));
    }
}
```

Run:

```bash
javac BigDecimalCollectionsDemo.java
java BigDecimalCollectionsDemo
```

**Exact output:**

```text
hashSet size: 2
treeSet size: 1
hashSet contains 2.000: false
treeSet contains 2.000: true
2.0 equals 2.00: false
2.0 compares as 2.00: true
```

**Why?**

- `hashSet.add(2.0)` and `hashSet.add(2.00)` keep two distinct elements: `equals` returns `false`.
- `treeSet.add(2.0)` followed by `treeSet.add(2.00)` leaves only one element under natural ordering: `compareTo` returns `0`.
- `treeSet.contains(2.000)` also returns `true` because its numeric value is equivalent under the tree's comparator, even though `2.000` is not `equals` to the `2.0` element inside.

This is a documented characteristic of `BigDecimal`. Under the general contract of `Set`, a comparator inconsistent with `equals` can produce surprising behavior. `TreeMap` with natural ordering exhibits the same difference relative to `HashMap`.

**Usage rule:** Before choosing `HashSet`, `TreeSet`, `HashMap`, or `TreeMap`, decide whether the application treats "same number, different scale" as **one** or **two** distinct values. Do not swap collection types and assume keys will be handled identically.

## 5. When do you need `equals`, and when do you need `compareTo`?

Choose according to **the meaning you need to check**:

| Need | Appropriate approach | Reason |
| --- | --- | --- |
| Do two `BigDecimal`s have the same numeric representation and scale? | `a.equals(b)` | Scale is part of the condition |
| Are two `BigDecimal`s equal in numeric value? | `a.compareTo(b) == 0` | Ignores scale differences |
| Check whether a numeric value is 0? | `a.signum() == 0` | Unaffected by `0`, `0.0`, `0.00` |
| Check whether a number is greater than a threshold? | `a.compareTo(threshold) > 0` | Numeric ordering comparison |
| Check whether a number is less than or equal to a threshold? | `a.compareTo(threshold) <= 0` | Numeric ordering comparison |
| Look up a key in `HashMap<BigDecimal, ...>`? | Normalize keys upfront or standardize scale | `HashMap` uses `equals/hashCode` |
| Compare a value just to display a certain number of decimal places? | Inspect `scale()`, combined with appropriate formatting | Numeric equality does not express display requirements |

Example:

```java
BigDecimal actual = new BigDecimal("100.00");
BigDecimal expected = new BigDecimal("100.0");

// Check mathematical value:
boolean sameAmount = actual.compareTo(expected) == 0; // true

// Check representation including scale:
boolean sameRepresentation = actual.equals(expected); // false
```

This is an **illustrative snippet** to embed in a method or a program with `import java.math.BigDecimal;`.

**Note on `null`:** `actual.compareTo(expected)` requires both references to be valid. If data can be `null`, explicitly decide what `null` means in the business domain and check beforehand. Never default `null` to zero.

## 6. `stripTrailingZeros()`: normalizing for value-based comparison

`stripTrailingZeros()` returns a `BigDecimal` with the same numeric value after removing unnecessary trailing `0` digits from the unscaled decimal representation. For example:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.stripTrailingZeros()); // 2
System.out.println(b.stripTrailingZeros()); // 2
```

The two normalized results have the same representation under `equals`. In many cases, you can normalize right at the system boundary if you need **a single canonical representation per numeric value**.

However, there are **two important caveats**:

1. Normalization can change `scale`, including to a **negative number**. `new BigDecimal("1000.00").stripTrailingZeros()` may print as `1E+3` with scale `-3`, rather than `1000.00`. When you need a decimal string without scientific notation, use `toPlainString()`; when you need a fixed number of digits, choose a dedicated `setScale`/formatting rule.
2. `new BigDecimal("0.000").stripTrailingZeros()` normalizes to `BigDecimal.ZERO` (scale `0`). This is helpful when normalizing zero, though it can drop information about the original precision/scale.

Therefore, **do not use `stripTrailingZeros` if the original scale carries meaning that must be preserved**, such as the number of decimal places entered by a user or formatting required by a data protocol.

### 6.1. Runnable normalization example

**File `BigDecimalNormalizationDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalNormalizationDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");

        BigDecimal normalizedA = a.stripTrailingZeros();
        BigDecimal normalizedB = b.stripTrailingZeros();

        System.out.println("normalized equal: "
                + normalizedA.equals(normalizedB));
        System.out.println("normalized a: " + normalizedA.toString());
        System.out.println("normalized a scale: "
                + normalizedA.scale());

        BigDecimal large =
                new BigDecimal("1000.00").stripTrailingZeros();
        System.out.println("large normalized: " + large.toString());
        System.out.println("large normalized scale: "
                + large.scale());
        System.out.println("large plain: " + large.toPlainString());

        BigDecimal zero =
                new BigDecimal("0.000").stripTrailingZeros();
        System.out.println("normalized zero scale: " + zero.scale());

        BigDecimal aligned =
                new BigDecimal("2.0").setScale(2);
        System.out.println("aligned: " + aligned.toPlainString());
        System.out.println("aligned equals b: " + aligned.equals(b));

        BigDecimal rounded =
                new BigDecimal("2.005").setScale(
                        2, RoundingMode.HALF_UP);
        System.out.println("rounded: " + rounded.toPlainString());
    }
}
```

```bash
javac BigDecimalNormalizationDemo.java
java BigDecimalNormalizationDemo
```

**Exact output:**

```text
normalized equal: true
normalized a: 2
normalized a scale: 0
large normalized: 1E+3
large normalized scale: -3
large plain: 1000
normalized zero scale: 0
aligned: 2.00
aligned equals b: true
rounded: 2.01
```

`stripTrailingZeros()` preserves **numeric value** while potentially changing the representation. Calling `setScale(2)` on `2.0` adds a decimal zero digit without changing the value, so `2.00.equals(2.00)` is `true`. Conversely, bringing `2.005` to scale `2` forces rounding: for example, using `RoundingMode.HALF_UP` yields `2.01`.

**Be careful with `setScale` without a rounding mode:** `new BigDecimal("2.005").setScale(2)` throws `ArithmeticException` because a non-zero fractional part would need to be discarded without rounding. This is a feature designed to prevent silent data loss. Only set a target scale after agreeing on the business rounding policy.

## 7. Objects containing BigDecimal: choosing a consistent equals/hashCode policy

The issue does not only appear when comparing two `BigDecimal`s directly. If a business class has a `BigDecimal amount` field, you must decide **whether scale participates in the enclosing class's equality definition**.

### Option A: scale is meaningful

If you want to distinguish `2.0` and `2.00` (e.g., preserving the original representation as part of the data), the enclosing class's `equals` can use `amount.equals(other.amount)`, while `hashCode` uses `amount.hashCode()` or `Objects.hash(...)` with the corresponding fields. Keys with different scales will then be treated as distinct.

### Option B: only numeric value is meaningful

If you want `2.0` and `2.00` to be **the same key**, the enclosing class's `equals` can use `compareTo() == 0`. However, **`hashCode` must normalize under that same relation**.

Typical wrong approach:

```java
// Wrong if equals uses compareTo == 0:
@Override
public int hashCode() {
    return amount.hashCode();
}
```

Because `amount.hashCode()` still considers scale, two objects deemed equal by the enclosing class can have different hashes. This violates the `equals/hashCode` contract.

A correct approach is to use the `stripTrailingZeros()` value for hashing.

### 7.1. Complete program: keys equal by numeric value

**File `NumericAmountKeyDemo.java`:**

```java
import java.math.BigDecimal;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class NumericAmountKeyDemo {
    static final class AmountKey {
        private final BigDecimal amount;

        AmountKey(BigDecimal amount) {
            this.amount = Objects.requireNonNull(amount);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof AmountKey other)) {
                return false;
            }
            return amount.compareTo(other.amount) == 0;
        }

        @Override
        public int hashCode() {
            return amount.stripTrailingZeros().hashCode();
        }
    }

    public static void main(String[] args) {
        AmountKey first = new AmountKey(new BigDecimal("2.0"));
        AmountKey second = new AmountKey(new BigDecimal("2.00"));
        AmountKey third = new AmountKey(new BigDecimal("2.000"));
        AmountKey different =
                new AmountKey(new BigDecimal("3.00"));

        System.out.println("first.equals(second): "
                + first.equals(second));
        System.out.println("hashes equal: "
                + (first.hashCode() == second.hashCode()));
        System.out.println("first.equals(different): "
                + first.equals(different));

        Set<AmountKey> amounts = new HashSet<>();
        amounts.add(first);
        amounts.add(second);
        System.out.println("set size: " + amounts.size());
        System.out.println("set contains third: "
                + amounts.contains(third));
    }
}
```

```bash
javac NumericAmountKeyDemo.java
java NumericAmountKeyDemo
```

**Exact output:**

```text
first.equals(second): true
hashes equal: true
first.equals(different): false
set size: 1
set contains third: true
```

Here `AmountKey` defines equality **by numeric value**, not by scale. Two numbers equal under `compareTo` are reduced to the same canonical representation by `stripTrailingZeros`, so their hash codes match. Since `BigDecimal` is immutable and the `amount` field is `final`, the key does not change value after creation.

**Business note:** If a monetary key also needs to include the **currency code** (e.g., VND, USD), comparing `BigDecimal` alone is not enough: `2 USD` does not equal `2 VND`. In that case, `equals` and `hashCode` must combine both the amount under the chosen policy **and** the currency unit.

## 8. Scale is useful data, not "garbage" to strip away

Many systems genuinely want to preserve scale:

- An input of `2.00` may imply the user provided a number to **two decimal places**.
- Accounting systems or pricing rules may require displaying exact **two digits after the decimal point**.
- The result of a `BigDecimal` operation can retain scale according to the operation's rules, so two numerically equal results do not necessarily share the same scale.
- When exchanging data, `toString()` and `toPlainString()` format differently; formatting/scale choices should follow the protocol, not `equals`.

Do not apply "normalize every `BigDecimal`" mechanically. Separate **mathematical value** from **precision, rounding, and display rules**.

In calculations and tests, always ask what you actually need to check:

```text
Question A: Does this number equal that number?
    → compareTo == 0

Question B: Do two BigDecimals have the same scale/representation?
    → equals

Question C: Is this number equal to zero?
    → signum == 0

Question D: Are exactly two decimal places needed?
    → business setScale/rounding/formatting policy
```

`equals` and `compareTo` are not meant to replace rounding or formatting.

## 9. Pitfalls from how BigDecimal is constructed

The difference between constructing from a string and from a `double` can make comparison problems harder to understand.

```java
BigDecimal fromText = new BigDecimal("0.1");
BigDecimal fromDouble = new BigDecimal(0.1);
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
```

- `fromText` represents the exact decimal number `0.1` (scale `1`).
- The binary floating-point `double 0.1` cannot represent decimal `0.1` exactly; `new BigDecimal(0.1)` creates the exact value of **that binary `double` value**, not exact `0.1`.
- `BigDecimal.valueOf(0.1)` uses the canonical string representation of `double` to create the `BigDecimal`, so in this case its value and scale match `new BigDecimal("0.1")`.

Short verification snippet (place inside a `main` method with `BigDecimal` imported):

```java
System.out.println(fromText.equals(fromDouble));  // false
System.out.println(fromText.compareTo(fromDouble) == 0); // false
System.out.println(fromText.equals(fromValueOf)); // true
```

**Distinction:** The `2.0` and `2.00` case differs **only by scale** while having the same numeric value. By contrast, `new BigDecimal(0.1)` and `new BigDecimal("0.1")` can **differ in numeric value too**, so `compareTo` does not return `0` either. When monetary/price data originates from decimal numbers, prefer constructing from decimal strings or a controlled decimal conversion pipeline.

## 10. Common mistakes and fixes

| Code or assumption | Problem | How to handle it |
| --- | --- | --- |
| `actual.equals(new BigDecimal("0"))` to check if numeric result is zero | `0.00` is not `equals` to `0` | Use `actual.signum() == 0` or `compareTo(ZERO) == 0` |
| Expecting `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` to be `true` | `equals` checks scale | Use `compareTo == 0` if only value matters |
| Assuming `HashMap<BigDecimal, V>` treats `2.0` and `2.00` as the same key | HashMap uses `equals/hashCode` | Normalize keys or use a consistent wrapper |
| Using `TreeSet<BigDecimal>` and expecting `HashSet`-like behavior | TreeSet uses `compareTo` | Pick the structure matching the desired equality definition |
| Wrapper `equals` uses `compareTo` while `hashCode` uses `amount.hashCode()` | Can violate contract | Hash the normalized value |
| Calling `stripTrailingZeros()` expecting scale to always be non-negative | Result can be `1E+3` with scale `-3` | Define normalization and formatting policies explicitly |
| Assuming `setScale(2)` is always safe | Throws an exception if rounding is required | Pick a `RoundingMode` per requirements |
| Assuming `new BigDecimal(0.1)` equals decimal `0.1` | `double` input has representation error | Construct from decimal string or proper conversion pipeline |

## 11. Self-check

**Question 1.** Given:

```java
BigDecimal x = new BigDecimal("5.0");
BigDecimal y = new BigDecimal("5.00");
```

Predict `x.equals(y)`, `x.compareTo(y) == 0`, and `x.scale()`, `y.scale()`.

**Answer:** `false`, `true`; scales are `1` and `2` respectively.

**Question 2.** Given `BigDecimal result = new BigDecimal("0.000");`. Which check clearly expresses that the numeric value is zero?

**Answer:** `result.signum() == 0` (or `result.compareTo(BigDecimal.ZERO) == 0`). `result.equals(BigDecimal.ZERO)` returns `false` because the scales differ.

**Question 3.** What scale can `new BigDecimal("1000.00").stripTrailingZeros()` have, and how does it display via `toString()`?

**Answer:** Scale `-3` and string `1E+3`. `toPlainString()` gives `1000`, without preserving the original `1000.00` representation.

**Question 4.** Two `BigDecimal` wrapper keys use `compareTo == 0` in `equals`. Why can't `hashCode` simply return `amount.hashCode()`?

**Answer:** Because two numbers with the same value and different scales can have different `BigDecimal.hashCode()` values. The wrapper considers them equal yet produces different hashes, violating the contract; you must use a normalized hash or another consistent policy.

**Question 5.** After adding `2.0` and `2.00` to a `HashSet<BigDecimal>` and a `TreeSet<BigDecimal>` (natural ordering), how many elements are in each set?

**Answer:** `HashSet` has `2` and `TreeSet` has `1`, because the two structures use two different equivalence relations in this case.

**Question 6.** If business logic **must preserve exactly 2 decimal places** for an amount, is calling `stripTrailingZeros()` on the source data appropriate?

**Answer:** Not as a default choice. It can discard the scale that must be kept. Define and apply scale, rounding, and display rules according to business requirements.

## Summary

**`BigDecimal.equals()` considers both numeric value and scale; `BigDecimal.compareTo() == 0` considers numeric value.** Thus `2.0` and `2.00` return `false` under `equals` yet `true` under `compareTo`. `hashCode` is compatible with `equals`, so hash-based structures treat them as two distinct keys; sorted structures using `compareTo` treat them as equivalent. When comparing numeric values, use `compareTo` or `signum`; when storing numeric-value keys in hash structures, normalize or build a wrapper with synchronized `equals/hashCode`. Always consider whether scale is important domain data before altering it.
