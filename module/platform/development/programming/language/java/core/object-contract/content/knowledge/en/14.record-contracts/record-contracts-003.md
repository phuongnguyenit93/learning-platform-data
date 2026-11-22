# Comparing float or double Components Using Wrapper Class Rules in Java Records

## Objectives

In Java 17+, a `record` comes with generated `equals(Object)`, `hashCode()`, and `toString()` from its components (record components). For a primitive `float` or `double` component, **the record's equality comparison follows the comparison semantics of the corresponding wrapper class** (`Float.compare` or `Double.compare`), rather than applying the arithmetic `==` operator directly.

This lesson helps you:

- Understand why two records containing `NaN` can still be `equals` to each other, even though `NaN == NaN` is `false`.
- Understand why `+0.0` and `-0.0` **differ according to `record.equals`**, even though `+0.0 == -0.0` is `true`.
- Grasp how primitive `float`/`double` components and reference `Float`/`Double` components are compared.
- Understand the meaning of `hashCode`, consistency of the equality relation, and using records in `HashSet`/`HashMap`.
- Know when a custom domain equality policy is needed, such as treating both signed zeros as one value or performing approximate comparisons.

## 1. The Record equals Contract

Given a declaration:

```java
record Measurement(float level, double precision) {}
```

the compiler provides essential methods by default, including `equals(Object)` and `hashCode()`. According to the `java.lang.Record` specification, a default equality comparison between two records requires:

1. The compared object belongs to **the same record class**.
2. Corresponding components are all equal according to the rule for the **type** of each component.
3. For reference-type components, the result is equivalent to `Objects.equals(componentA, componentB)`.
4. For primitive-type components, the result is equivalent to the `compare` method of the **corresponding wrapper class** returning `0`. For `float` and `double`, this is `Float.compare(a, b) == 0` or `Double.compare(a, b) == 0`.

The description above is the **semantic rule**; the JVM is not required to actually allocate wrapper objects (boxing) or literally call those exact methods at runtime. The internal algorithm may be optimized or changed, as long as the result conforms to the contract.

Because the two components have types `float` and `double`, you can picture the `equals` logic like this:

```java
// PSEUDOCODE to explain semantics; not code the compiler is required to emit.
boolean equivalent(Measurement a, Measurement b) {
    return Float.compare(a.level(), b.level()) == 0
            && Double.compare(a.precision(), b.precision()) == 0;
}
```

The snippet above assumes `a` and `b` are both non-`null` and of the same `Measurement` class. In practice, `record.equals` also handles the same-object, `null`, and different-class cases according to the `Object.equals` contract.

**Why not use `==` for two floating-point components?** Because `==` does not form an equivalence relation for all IEEE 754 values, particularly with `NaN`. `equals` must preserve reflexivity (an object equals itself), symmetry, and transitivity. Wrapper-style comparison handles edge cases consistently.

## 2. How `==` Differs from `Float.compare` and `Double.compare`

Java has special floating-point values:

- `Float.NaN` and `Double.NaN`: Not a Number.
- `+0.0` and `-0.0`: two zero values with different signs.
- `Float.POSITIVE_INFINITY`, `Float.NEGATIVE_INFINITY`, and the corresponding `Double` values.

Comparing with the arithmetic operator and with wrapper class rules differs in important cases:

| Two Values | Primitive Operator `a == b` | `Float.compare` / `Double.compare` returns `0`? | Two same-class records holding only this value `equals` each other? |
| --- | --- | --- | --- |
| `1.5` and `1.5` | `true` | Yes | Yes |
| `+0.0` and `-0.0` | `true` | **No** | **No** |
| `NaN` and `NaN` | **`false`** | Yes | Yes |
| `+Infinity` and `+Infinity` | `true` | Yes | Yes |
| `-Infinity` and `+Infinity` | `false` | No | No |

### 2.1. NaN: `==` Does Not Equal Itself, Yet Record equals Does

```java
double a = Double.NaN;
double b = Double.NaN;

System.out.println(a == b);                  // false
System.out.println(Double.compare(a, b) == 0); // true
```

With the `==` operator, a NaN is always **unequal** to any value, including NaN. With `Double.compare`, NaNs are treated as the same value group for the wrapper class's equality relation; hence the comparison returns `0`. `Float.compare` shares the corresponding property.

For records, this is important: a record containing NaN still equals itself and can equal another record of the same class whose corresponding components are NaN.

### 2.2. Signed Zero: `==` Treats Them as Equal, Record equals Distinguishes Them

```java
double positiveZero = +0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero);              // true
System.out.println(Double.compare(positiveZero, negativeZero)); // 1
```

`Double.compare(+0.0, -0.0)` returns a **positive** number; here the example produces `1`. Similarly, `Double.compare(-0.0, +0.0)` returns a negative number. The wrapper rule orders `-0.0` lower than `+0.0`.

The two zeros can produce different behavior in arithmetic operations: `1.0 / +0.0` is positive infinity, while `1.0 / -0.0` is negative infinity. Distinguishing them in the equality relation makes sense when preserving exact floating-point representation matters.

### 2.3. This Is Representation Comparison, Not Approximate Comparison

`Float.compare` and `Double.compare` do **not** check whether "two numbers are close enough". They have a specific ordering and equality rule for IEEE 754 values, including NaN and the two signed zeros.

For example, `0.1 + 0.2` and `0.3` can differ due to binary representation; a record by default **does not automatically apply an epsilon** to treat them as equal. If you want an "approximately equal" policy, check separately using rules appropriate for the numerical problem; do not assume records apply rounding mechanisms.

## 3. Complete Java 17+ Example: Records with float and double

Create the file **`RecordFloatingEqualityDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

public class RecordFloatingEqualityDemo {
    record Measurement(float level, double precision) {}

    public static void main(String[] args) {
        Measurement nanA =
                new Measurement(Float.NaN, Double.NaN);
        Measurement nanB =
                new Measurement(Float.NaN, Double.NaN);

        Measurement positive =
                new Measurement(+0.0f, +0.0d);
        Measurement negative =
                new Measurement(-0.0f, +0.0d);

        System.out.println("Float.NaN == Float.NaN: "
                + (Float.NaN == Float.NaN));
        System.out.println("Double.NaN == Double.NaN: "
                + (Double.NaN == Double.NaN));
        System.out.println("nanA.equals(nanB): "
                + nanA.equals(nanB));
        System.out.println("nanA equals itself: "
                + nanA.equals(nanA));
        System.out.println("nan hashes equal: "
                + (nanA.hashCode() == nanB.hashCode()));

        System.out.println("+0.0f == -0.0f: "
                + (+0.0f == -0.0f));
        System.out.println("positive.equals(negative): "
                + positive.equals(negative));
        System.out.println("Float.compare(+0.0f, -0.0f) == 0: "
                + (Float.compare(+0.0f, -0.0f) == 0));

        Set<Measurement> measurements = new HashSet<>();
        measurements.add(nanA);
        measurements.add(nanB);
        measurements.add(positive);
        measurements.add(negative);

        System.out.println("set size: " + measurements.size());
        System.out.println("set contains equal NaN record: "
                + measurements.contains(
                        new Measurement(Float.NaN, Double.NaN)));
    }
}
```

Compile and run:

```bash
javac RecordFloatingEqualityDemo.java
java RecordFloatingEqualityDemo
```

**Exact output:**

```text
Float.NaN == Float.NaN: false
Double.NaN == Double.NaN: false
nanA.equals(nanB): true
nanA equals itself: true
nan hashes equal: true
+0.0f == -0.0f: true
positive.equals(negative): false
Float.compare(+0.0f, -0.0f) == 0: false
set size: 3
set contains equal NaN record: true
```

Step-by-step explanation:

1. `nanA` and `nanB` are **two separate record objects**, yet they belong to the same class and their components are equivalent per `Float.compare`/`Double.compare`. `equals` returns `true`.
2. When `equals` is `true`, the contract requires equal `hashCode`s. Therefore, `nanA.hashCode() == nanB.hashCode()` is `true`. There is no need to know the specific hash number.
3. `positive` and `negative` differ only in the sign of zero in `level`. Because `Float.compare(+0.0f, -0.0f) != 0`, they are **not equal** according to `equals`.
4. `HashSet` retains only one of the two equivalent `nanA`/`nanB` records, while retaining both the positive-zero and negative-zero records. Total element count is **3**.
5. `HashSet.contains` uses the record's `hashCode` and `equals`, thereby finding a new record with equivalent NaN components.

Point to remember: **do not replace record comparison by separately comparing primitive components with `==`**, because that can yield a different answer.

## 4. Float/Double Object Components: Same Wrapper Class Rules

A record can also declare a **reference-type** component `Float` or `Double`:

```java
record WrappedMeasurement(Float level, Double precision) {}
```

For reference components, `record.equals` uses semantics equivalent to `Objects.equals`. Because `Float.equals(Object)` and `Double.equals(Object)` follow rules similar to `Float.compare`/`Double.compare` regarding NaN and signed zero, we still have:

- Two wrapper objects containing NaN are equivalent: **equal**.
- One wrapper object containing `+0.0` and one containing `-0.0`: **not equal**.
- Both components `null`: equal with respect to that component.
- One side `null`, the other non-`null`: different.

**Important difference:** Primitive `float`/`double` components cannot be `null`; `Float`/`Double` components can be `null`. If using wrappers as record components, decide clearly whether `null` is allowed in the business domain.

### 4.1. Runnable Example: Wrappers and null

**File `RecordWrappedFloatingDemo.java`:**

```java
import java.util.Objects;

public class RecordWrappedFloatingDemo {
    record WrappedMeasurement(Float level, Double precision) {}

    public static void main(String[] args) {
        WrappedMeasurement nanA =
                new WrappedMeasurement(Float.NaN, Double.NaN);
        WrappedMeasurement nanB =
                new WrappedMeasurement(Float.NaN, Double.NaN);
        WrappedMeasurement plus =
                new WrappedMeasurement(+0.0f, +0.0d);
        WrappedMeasurement minus =
                new WrappedMeasurement(-0.0f, +0.0d);
        WrappedMeasurement noValueA =
                new WrappedMeasurement(null, null);
        WrappedMeasurement noValueB =
                new WrappedMeasurement(null, null);

        System.out.println("nan wrapped equal: "
                + nanA.equals(nanB));
        System.out.println("wrapped zero signs equal: "
                + plus.equals(minus));
        System.out.println("null components equal: "
                + noValueA.equals(noValueB));
        System.out.println("one null differs: "
                + noValueA.equals(
                        new WrappedMeasurement(null, 1.0)));

        System.out.println("Float.equals for NaN: "
                + Float.valueOf(Float.NaN).equals(
                        Float.valueOf(Float.NaN)));
        System.out.println("Double.equals for signed zeros: "
                + Double.valueOf(+0.0d).equals(
                        Double.valueOf(-0.0d)));
        System.out.println("Objects.equals(null, null): "
                + Objects.equals(null, null));
    }
}
```

```bash
javac RecordWrappedFloatingDemo.java
java RecordWrappedFloatingDemo
```

**Exact output:**

```text
nan wrapped equal: true
wrapped zero signs equal: false
null components equal: true
one null differs: false
Float.equals for NaN: true
Double.equals for signed zeros: false
Objects.equals(null, null): true
```

If parameters are not allowed to be `null`, you can validate in a compact constructor:

```java
record StrictMeasurement(Float level, Double precision) {
    StrictMeasurement {
        java.util.Objects.requireNonNull(level);
        java.util.Objects.requireNonNull(precision);
    }
}
```

This declaration snippet only illustrates validation in a constructor. It can be placed in an appropriate Java file; with a compact constructor, the components are assigned automatically after the constructor body runs successfully.

## 5. NaN Has Multiple Bit Representations Yet Compares as Equivalent

IEEE 754 data can have many **bit patterns** meaning NaN. When `Float.equals`/`Double.equals` and `Float.compare`/`Double.compare` compare, NaNs are treated in a **canonical** form for equality purposes. Thus NaNs with different payloads are still considered equivalent under default `record.equals`.

You can relate this to standard methods:

- `Float.floatToIntBits(value)` normalizes NaN bit patterns into a single canonical form; `Double.doubleToLongBits(value)` does similarly.
- `Float.floatToRawIntBits(value)` and `Double.doubleToRawLongBits(value)` provide raw bit access without actively normalizing NaN; preserving a specific payload across operations/conversions can depend on the environment and how the value is processed.
- `Float.compare`/`Double.compare` have equality rules consistent with the wrapper classes, in which all NaNs are considered equal.

**Do not infer that default records preserve or distinguish NaN payloads.** Records with `float`/`double` components compare using wrapper class semantics. If business data requires distinguishing individual bit patterns, you need a **separate representation model** (such as storing bits in an `int`/`long` component) and clearly define how the data is collected and stored.

## 6. A Record's hashCode Is Compatible with equals, Yet Has No Fixed Formula

`record` comes with generated `hashCode()` based on the components. Because a record generates `equals` for NaN and signed zero using wrapper class rules, `hashCode` must align with the same equality relation:

```text
If a.equals(b) == true
then a.hashCode() == b.hashCode() must be true.
```

Consequently, two records containing NaN are equivalent and have the same hash. Conversely, two records differing in a signed zero component are not `equals` to each other; their hashes **may** differ, though they are not required to differ (collisions are still valid).

Do not rely on an **exact hash value** or assume the record's hash generation algorithm is always `Objects.hash(component1, component2, ...)`. The specification permits record implementations to use another algorithm as long as it obeys the contract. Nor is a hash a memory address, security key, or unique identifier.

### 6.1. Why Do HashMap and HashSet Recognize NaN?

`HashSet`/`HashMap` use the key's `hashCode` together with `equals`. If a record is created with NaN in floating-point components, two records with the same components equivalent under record rules will be recognized as the same key/value. This is the benefit of records using a reflexive and consistent equality relation.

Do not apply a confused rule:

```java
record Reading(double value) {}

Reading x = new Reading(Double.NaN);
Reading y = new Reading(Double.NaN);

// x.equals(y) is true.
// x.value() == y.value() is false.
```

The snippet above is illustrative code placed in a context with an appropriate record declaration and method. The difference does not violate the contract: **record objects** and **mathematical comparison on primitives** follow two different equality policies.

## 7. When Is a "+0.0 Equals -0.0" Policy Needed?

Many business domains treat `+0.0` and `-0.0` as **the same zero value**, ignoring its sign. If so, the record's default behavior may not fit. Instead of overriding `equals` arbitrarily, a simple approach is to **normalize inputs** in the constructor and keep the generated `equals/hashCode` intact.

### 7.1. Normalizing Zero in a Compact Constructor

**File `NormalizedZeroRecordDemo.java`:**

```java
import java.util.HashSet;
import java.util.Set;

public class NormalizedZeroRecordDemo {
    record Reading(float value, double correction) {
        Reading {
            if (value == 0.0f) {
                value = 0.0f; // Normalize -0.0f to +0.0f as well.
            }
            if (correction == 0.0d) {
                correction = 0.0d; // Normalize -0.0d to +0.0d as well.
            }
        }
    }

    public static void main(String[] args) {
        Reading negative =
                new Reading(-0.0f, -0.0d);
        Reading positive =
                new Reading(+0.0f, +0.0d);
        Reading nanA =
                new Reading(Float.NaN, Double.NaN);
        Reading nanB =
                new Reading(Float.NaN, Double.NaN);

        System.out.println("zeros equal after normalization: "
                + negative.equals(positive));
        System.out.println("zero hashes equal: "
                + (negative.hashCode() == positive.hashCode()));
        System.out.println("stored float is positive zero: "
                + (Float.floatToIntBits(negative.value())
                        == Float.floatToIntBits(+0.0f)));
        System.out.println("stored double is positive zero: "
                + (Double.doubleToLongBits(negative.correction())
                        == Double.doubleToLongBits(+0.0d)));
        System.out.println("NaN values remain equal: "
                + nanA.equals(nanB));

        Set<Reading> values = new HashSet<>();
        values.add(negative);
        values.add(positive);
        values.add(nanA);
        values.add(nanB);
        System.out.println("set size: " + values.size());
    }
}
```

```bash
javac NormalizedZeroRecordDemo.java
java NormalizedZeroRecordDemo
```

**Exact output:**

```text
zeros equal after normalization: true
zero hashes equal: true
stored float is positive zero: true
stored double is positive zero: true
NaN values remain equal: true
set size: 2
```

Because the condition `value == 0.0f` is true for both positive zero and negative zero, the assignment `value = 0.0f` brings both to positive zero. The compact constructor body mutates the parameter variables before Java assigns them to the component fields; the record then uses the default `equals/hashCode` consistently.

**Trade-off:** This normalization **discards the sign information of zero**. It is appropriate when the application decides zero's sign has no meaning, but inappropriate if they must be distinguished in arithmetic, signal analysis, or exact IEEE 754 data storage.

### 7.2. What If Other Fields Need Normalization?

Other normalizations can be applied in the constructor (e.g., checking `Double.isFinite` to forbid NaN/infinity, or quantizing to domain units) if application requirements are clear. The critical condition is that **the same normalized state must produce the same `equals`/`hashCode` relation**.

Do not override `equals` to treat both zeros as equal while leaving the default `hashCode`: if the hashes of two differently signed zeros differ, the record violates the "equal implies equal hash" contract. Normalizing in the constructor preserves the default pair of methods intact.

## 8. Approximate Comparison Should Not Be Turned into equals

In numerical computation, people sometimes use an error tolerance:

```java
Math.abs(a - b) <= epsilon
```

This is a simple approximate check, **not** an ideal equivalence relation for `equals(Object)`. It can be **non-transitive**: with `epsilon = 1.0`, `0.0` is close to `0.6`, `0.6` is close to `1.2`, yet `0.0` is not close to `1.2`.

If that approximate relation is put into `equals`, two values the application treats as equal can be difficult to assign a valid hash to, and `equals` can lose transitivity — affecting key-based collections.

Separate them:

- `record.equals`: consistent according to clear rules, reflexive, symmetric, and transitive.
- A separate method like `approximatelyEquals`: a tolerance-based numerical check for the application, not used in place of `equals` in `HashMap`/`HashSet`.

### 8.1. Example of a Separate Approximate Equality Check

**File `ApproximateComparisonDemo.java`:**

```java
public class ApproximateComparisonDemo {
    record Reading(double value) {
        boolean approximatelyEquals(Reading other, double epsilon) {
            if (other == null || !Double.isFinite(value)
                    || !Double.isFinite(other.value())
                    || !Double.isFinite(epsilon) || epsilon < 0) {
                return false;
            }
            return Math.abs(value - other.value()) <= epsilon;
        }
    }

    public static void main(String[] args) {
        Reading a = new Reading(0.0);
        Reading b = new Reading(0.6);
        Reading c = new Reading(1.2);

        System.out.println("a approximately b: "
                + a.approximatelyEquals(b, 1.0));
        System.out.println("b approximately c: "
                + b.approximatelyEquals(c, 1.0));
        System.out.println("a approximately c: "
                + a.approximatelyEquals(c, 1.0));
        System.out.println("a.equals(b): " + a.equals(b));
    }
}
```

```bash
javac ApproximateComparisonDemo.java
java ApproximateComparisonDemo
```

**Exact output:**

```text
a approximately b: true
b approximately c: true
a approximately c: false
a.equals(b): false
```

This simple check is only suitable for finite examples of reasonable numeric scale. For very large/small quantities, a formula based on absolute and relative tolerances and overflow/underflow control may be needed, depending on the problem domain. The approximation policy should still remain **separate from `equals`**.

## 9. Common Pitfalls When Using Records with Floating-Point Numbers

| Misconception | Correct Explanation |
| --- | --- |
| "`record.equals` compares `double` components using `==`." | It follows semantics equivalent to `Double.compare`, distinguishing signed zero and recognizing NaNs as equivalent. |
| "Because `Double.NaN == Double.NaN` is `false`, a record containing NaN does not equal itself." | `record.equals` must be reflexive and uses wrapper class rules, so a record containing NaN still equals itself. |
| "`+0.0 == -0.0` so two records holding these zeros are equal." | Under default record behavior, `+0.0` and `-0.0` **differ**. |
| "`Double.compare` is an approximate check." | No; it is an ordered comparison, with special rules for NaN and signed zero. |
| "You can compare hashes to prove two records are equal." | No; hash collisions are permitted to occur. |
| "Records with `Double` and `double` components behave identically." | Special value comparison semantics are similar, but `Double` allows `null` while `double` does not. |
| "To make differently signed zeros equal, just override equals." | `hashCode` must be synchronized; it is usually easier to verify by normalizing inputs and keeping default methods. |
| "Comparing difference less than epsilon works as equals for hash keys." | An approximate relation can be non-transitive, making it unsuitable as general `equals`. |
| "You can rely on the exact hash number of a record across all JDKs." | The specification does not guarantee a fixed hash algorithm across implementations/runs. |

### Checklist When Designing a Record with float or double

1. Can that component receive `NaN`, `+Infinity`, `-Infinity`, or signed zero?
2. Does the business domain want to **distinguish** differently signed zeros, or normalize both to one value?
3. If NaN can be received, should all NaNs be treated as equivalent? The record default is **yes**.
4. Is an approximate check needed in a **separate method**?
5. Does a record with a `Float`/`Double` component need `null` handling?
6. If overriding `equals`, have `hashCode` compatibility, reflexivity, symmetry, and transitivity been proven?
7. If storing in a `HashSet` or `HashMap`, have signed zero and NaN cases been tested?

## 10. Self-Check

**Question 1.** Given `record R(double x) {}`. Are two `new R(Double.NaN)` objects `equals` to each other?  
**Answer:** Yes. A record's default equality semantics for `double` are equivalent to `Double.compare`; NaNs are considered equal.

**Question 2.** What does `new R(+0.0).equals(new R(-0.0))` return?  
**Answer:** `false`. `Double.compare(+0.0, -0.0)` does not return `0`.

**Question 3.** Why does `Double.NaN == Double.NaN` return `false`, yet records containing NaN can return `equals == true`?  
**Answer:** The primitive `==` operator follows IEEE 754 floating-point comparison rules. Default records use wrapper class comparison semantics to form a valid equality relation under the `equals` contract.

**Question 4.** If a record contains `Float f` and both objects have `f == null`, is that component considered equal?  
**Answer:** Yes. Reference components are compared equivalently to `Objects.equals(null, null)`. However, the record must still consider all remaining components and the exact record class.

**Question 5.** How can a record treat `+0.0` and `-0.0` as equal while still using generated `equals/hashCode`?  
**Answer:** Normalize both to the same zero (e.g., `+0.0`) in the compact constructor, so the actual fields stored in the record are identical under default rules.

**Question 6.** Should `approximatelyEquals` with a fixed tolerance be implemented as `equals(Object)`?  
**Answer:** No. Approximate equality can violate transitivity, causing data structures relying on `equals/hashCode` to behave contrary to their contract.

## Key Takeaway

**Records compare `float` and `double` components using rules equivalent to `Float.compare`/`Double.compare`, not the primitive `==` operator.** Therefore, NaN is equivalent to NaN, while `+0.0` differs from `-0.0` in default `record.equals`. `Float`/`Double` components use `Objects.equals` rules and additionally support `null`. The specification requires `hashCode` to be consistent with `equals` without fixing a specific hash number. If the application wants different rules, define the business domain semantics, prefer normalizing inputs and keeping `equals/hashCode` consistent; use a separate method for approximate comparisons.