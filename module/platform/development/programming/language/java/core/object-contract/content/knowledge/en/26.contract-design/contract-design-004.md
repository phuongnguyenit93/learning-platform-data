# Explicitly Specifying Null Handling, Normalization, and Derived Data in Java Object Contracts

## 1. Why Is This Part of the Object Contract?

An *object contract* defines valid states, the meaning of attributes, and predictable object behavior: how to initialize, read data, compare equality (`equals()`), compute hash codes (`hashCode()`), represent as text (`toString()`), as well as what is allowed to change after creation. Without explicitly stating the three rules for **handling `null`**, **normalizing inputs**, and **managing derived data**, the same business information can produce multiple conflicting states.

For example, should product codes `" ab-17 "` and `"AB-17"` be the same code? Does a `null` note differ from an empty string `""`? Should total amount be stored as an independent field alongside unit price and quantity? There is no universal answer for every system; what matters is **locking in one policy per attribute, enforcing it at the object-creation boundary, and maintaining it consistently throughout the object's lifecycle**.

For a *value object*, that policy governs both `equals()` and `hashCode()`. For an *entity*, you must additionally specify which business identity is used for comparison; you should not implicitly put every field into the comparison.

## 2. Three Decisions to Record in the Contract

| Category | Questions to Answer | Example of a Transparent Decision |
| --- | --- | --- |
| `null` | Is the field required or optional? Does `null` have a distinct meaning from empty/absent? | `sku` and `unitPrice` reject `null`; `note == null` is interpreted as an empty note. |
| Normalization | Where is the value normalized, by what algorithm, and is any information lost? | Strip outer whitespace from SKU, validate ASCII characters, convert lowercase to uppercase with `Locale.ROOT`; do not auto-fix invalid codes. |
| Derived data | Which field is the source of truth, which is computed from the source, and can it be modified independently? | `total = unitPrice × quantity` is computed on method call; no `total` value is accepted from callers. |

### 2.1. `null`: Reject, Normalize, or Preserve?

All options are valid **if they match the data domain semantics**:

1. **Required value:** use `Objects.requireNonNull(value, "field")`, then validate domain conditions (non-empty, non-negative, valid format). `requireNonNull` throws `NullPointerException` with the provided field name when the argument is `null`. If the API specifies that all invalid inputs must become `IllegalArgumentException`, convert the exception explicitly and consistently.
2. **Optional, where absent and empty have the same meaning:** normalize to a single canonical representation, such as `note = note == null ? "" : note.strip()`. Callers observing `note()` then always receive a string, never `null`.
3. **Optional, where absent differs from an empty string:** preserve `null` or model absence separately; clearly document how `null`, `""`, and `"   "` differ. `Objects.equals(a, b)` helps compare nullable values without throwing an NPE.
4. **Optional in return APIs:** consider `Optional<T>` as a return type when clarifying the meaning of absence; do not automatically replace every nullable field with `Optional`, as that complicates the data model, ORM mapping, and serialization.

Do not use `"N/A"`, `0`, `false`, or fake timestamps as default values if those values could be real business data. Do not implicitly equate `null`, empty strings, and whitespace-only strings unless the contract explicitly states they are equivalent.

### 2.2. Normalization: Defining a *Canonical Form*

A good normalization function must be **deterministic**, **stable**, **idempotent** (`normalize(normalize(x)) == normalize(x)` for valid inputs), and aligned with the business domain's notion of equality. Steps may include `strip()`, case conversion, Unicode normalization, unit conversion, time zone disambiguation, or decimal normalization. However, every step can alter the meaning of data.

- **Identifiers with ASCII rules:** you can trim leading/trailing whitespace, allow only `[A-Za-z0-9_-]`, and then convert to uppercase with `Locale.ROOT`. Only do this if the code is **case-insensitive per specification**. Checking characters before transforming prevents accidentally validating characters outside the allowed set.
- **Person names and display text:** do not automatically strip all internal whitespace, remove diacritics, or lowercase just for comparison. Such transformations can lose information.
- **Unicode:** if the data domain treats precomposed and decomposed accented characters as the same character, consider `Normalizer.normalize(text, Normalizer.Form.NFC)`. NFC alone does not solve all language-specific collation rules, letter casing, or Unicode homoglyph issues.
- **Decimal numbers:** `new BigDecimal("10.0").equals(new BigDecimal("10.00"))` is `false` due to differing `scale`, even though `compareTo(...) == 0`. For value objects using `BigDecimal`, decide whether to normalize `scale`, use a separate comparison rule, or preserve the exact original representation.
- **Dates/times and units:** clarify whether to use `Instant` or local time, UTC or a business time zone, meters or centimeters. Only normalize when enough information exists so meaning is not lost.

**Do not treat normalization as "fixing data at all costs".** For an invalid product code, rejecting is usually better than stripping strange characters and unexpectedly merging two different codes into one. If normalization turns two different inputs into the same value, that is a business decision requiring documentation and testing.

### 2.3. Derived Data: A Single Source of Truth

Suppose `total = unitPrice.multiply(quantity)`. If the object simultaneously holds `quantity`, `unitPrice`, **and** an independently assignable `total`, the contract must explain what happens when the three values disagree. The safe approach for inexpensive calculations is **storing only the two inputs and computing `total()` on demand**. That way no stale `total` state can exist.

If the calculation is expensive and needs caching, specify clearly: whether the cache affects `equals()`/`hashCode()` (typically **no**), when the cache is invalidated, how concurrency is handled, and whether the cache is rebuilt after deserialization. For immutable objects, lazy caching can be used in specific cases, but you must evaluate thread safety and overhead; do not invent a cache when the computation is simple.

## 3. Complete Example: Immutable `OrderLine` on Java 17+

Illustrative policy:

- `sku`: required, accepts only ASCII letters, digits, `_`, `-`; trims leading/trailing whitespace; case-insensitive equivalence.
- `note`: optional; `null`, empty string, and whitespace-only strings are treated as the same empty note; preserves case sensitivity for remaining content.
- `quantity`: positive integer; no implicit default value.
- `unitPrice`: non-`null`, non-negative; at most two decimal places. Normalized to `scale = 2` and **rejected** if rounding is needed.
- `total`: equals `unitPrice × quantity`, always computed from current state; not stored as a component.

`record` auto-generates `equals()`, `hashCode()`, and `toString()` from the record components. The *compact* constructor below converts every valid input to its canonical form **before Java automatically assigns the parameters to the final fields**. Thus value comparison operates consistently on normalized fields.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class ObjectContractDemo {
    record OrderLine(String sku, String note, int quantity, BigDecimal unitPrice) {
        public OrderLine {
            sku = normalizeSku(sku);
            note = note == null ? "" : note.strip();

            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }

            unitPrice = Objects.requireNonNull(unitPrice, "unitPrice");
            try {
                unitPrice = unitPrice.setScale(2, RoundingMode.UNNECESSARY);
            } catch (ArithmeticException ex) {
                throw new IllegalArgumentException(
                        "unitPrice must have at most two decimal places", ex);
            }
            if (unitPrice.signum() < 0) {
                throw new IllegalArgumentException("unitPrice must not be negative");
            }
        }

        private static String normalizeSku(String input) {
            String value = Objects.requireNonNull(input, "sku").strip();
            if (!value.matches("[A-Za-z0-9][A-Za-z0-9_-]*")) {
                throw new IllegalArgumentException("invalid sku");
            }
            return value.toUpperCase(Locale.ROOT);
        }

        public BigDecimal total() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    public static void main(String[] args) {
        OrderLine first = new OrderLine(
                " ab-17 ", null, 2, new BigDecimal("10.0"));
        OrderLine second = new OrderLine(
                "AB-17", "   ", 2, new BigDecimal("10.00"));
        OrderLine withNote = new OrderLine(
                "AB-17", "gift", 2, new BigDecimal("10.00"));

        System.out.println("same value: " + first.equals(second));
        System.out.println("same reference: " + (first == second));
        System.out.println("same hash: " + (first.hashCode() == second.hashCode()));
        System.out.println("sku: " + first.sku());
        System.out.println("note: [" + first.note() + "]");
        System.out.println("price: " + first.unitPrice().toPlainString());
        System.out.println("total: " + first.total().toPlainString());
        System.out.println("different note: " + first.equals(withNote));

        Set<OrderLine> lines = new HashSet<>();
        lines.add(first);
        lines.add(second);
        System.out.println("set size: " + lines.size());

        try {
            new OrderLine("  ", null, 1, BigDecimal.ONE);
        } catch (IllegalArgumentException ex) {
            System.out.println("blank sku rejected");
        }
        try {
            new OrderLine("AB-17", "", 1, new BigDecimal("1.234"));
        } catch (IllegalArgumentException ex) {
            System.out.println("too precise price rejected");
        }
    }
}
```

Name the file `ObjectContractDemo.java`. Compile and run on JDK 17 or higher:

```bash
javac -encoding UTF-8 ObjectContractDemo.java
java ObjectContractDemo
```

Deterministic output (independent of random JVM identity hash codes):

```text
same value: true
same reference: false
same hash: true
sku: AB-17
note: []
price: 10.00
total: 20.00
different note: false
set size: 1
blank sku rejected
too precise price rejected
```

**Reading the output:** `first` and `second` are two distinct instances (`== false`), yet after normalization their four corresponding components are equal, so `equals()` returns `true`, their hashes match, and `HashSet` stores only one element. `note` is a component of **value equality**, so the record with note `gift` differs in value; `total()` is computed from the two source components and has `scale = 2`. If the business wants to ignore `note` in comparisons, you must design a different `equals()`/`hashCode()` contract consistently; you cannot use a record's default equality and expect it to skip a component.

The example sets **rejection** rules rather than silent correction: malformed `sku`, non-positive quantity, negative price, or price requiring rounding all fail at initialization. This ensures constructed objects always uphold their *invariants*.

## 4. How Do `equals()`, `hashCode()`, and Normalized Data Relate?

For value objects, select the **components participating in equality** according to the true meaning of the value. If `equals()` relies on the canonical representation of fields, `hashCode()` must use the same components with the same rules. Specifically:

- **Reflexive:** `x.equals(x)` must be `true`.
- **Symmetric:** `x.equals(y)` and `y.equals(x)` must return the same result.
- **Transitive:** if `x.equals(y)` and `y.equals(z)` then `x.equals(z)`.
- **Consistent:** if state relevant to equality does not change, results must remain stable.
- **Against `null`:** `x.equals(null)` must be `false`.
- **Hash contract:** if `x.equals(y)` then `x.hashCode() == y.hashCode()`; the converse is **not** guaranteed due to collisions.

`record` derives these methods from the stored components. In the example, normalizing price to the same `scale` is especially helpful because `BigDecimal.equals()` distinguishes `10.0` from `10.00`; `record` inherits that exact comparison for the `unitPrice` field. When designing a regular class and overriding `equals()`/`hashCode()` manually, apply the same policy to both, and do not include a mutable derived value in the hash if that value is not part of identity/equality.

**Distinguishing entity and value object:** If two entities with the same `sku` but different business fields are still considered the same entity, you need a stable identity key and a separate equality policy. The record illustrated above is a **value object**: every component (`sku`, `note`, `quantity`, `unitPrice`) is meaningful in comparisons.

## 5. Data Stability and the Risks of Allowing Mutable State

For an object already added to a `HashSet` or used as a `HashMap` key, modifying a field used in `equals()`/`hashCode()` can cause lookups to fail or collection behavior to become unpredictable. Therefore, value objects used as keys should be immutable; changing data should create a new instance. The `record` in the example has immutable `String`, `int`, and `BigDecimal` components and returns no references to modifiable structures.

For classes containing `List`, `Date`, arrays, or mutable objects, declaring `final` on the reference is **not enough** for deep immutability; defensive copying and an exposure policy are required. Avoid returning internal arrays directly or retaining references to external collections that can be mutated after initialization.

### 5.1. Distinguishing Source Data from Cached Data

```java
// Illustrative snippet: NOT a standalone program.
// Do not store total independently if quantity/unitPrice can still change freely:
BigDecimal total = unitPrice.multiply(BigDecimal.valueOf(quantity));
// When quantity changes, the old total becomes stale if not updated.
```

In situations requiring mutable objects, every write operation must preserve invariants, update or invalidate dependent caches, and guard concurrent access if shared across threads. A simpler approach is usually making state immutable and recomputing derived fields in the accessor method.

### 5.2. `toString()`, Logging, and Serialization

`toString()` is part of the observable interface: specify how `null`, normalized values, and derived fields are represented, as well as what must **not** be printed due to sensitivity (passwords, tokens, personal data). Default `record.toString()` displays record components, so do not use the default unconditionally with sensitive data. If JSON or a database stores pre-normalized values, the reload path must enforce invariants or report invalid data; do not let constructors, mappers, factories, and deserializers apply different rules.

## 6. Policies That Must Be Tested

| Input Case | Expected in Example | Reason |
| --- | --- | --- |
| `sku = null` | Rejected with `NullPointerException` | Required field, checked with `requireNonNull`. |
| `sku = "  "` | Rejected with `IllegalArgumentException` | After `strip()`, no valid code remains. |
| `sku = " ab-17 "` and `"AB-17"` | Same canonical value `AB-17` | Code is case-insensitive per published policy. |
| `sku` with accents or invalid characters | Rejected | Character set is explicitly restricted. |
| `note = null`, `""`, `"  "` | Same canonical value `""` | Policy merges absent and empty. |
| `note = "Gift"` and `"gift"` | Different | Note is only stripped, case is not changed. |
| `quantity = 0` or negative | Rejected | Condition `quantity > 0`. |
| `unitPrice = null` or negative | Rejected | Required field, non-negative price. |
| `unitPrice = 10.0` and `10.00` | Same representation `10.00` | `BigDecimal` normalized to `scale = 2`. |
| `unitPrice = 1.234` | Rejected; no silent rounding | `RoundingMode.UNNECESSARY` enforces exact precision. |
| Two records equal after normalization | Equal `equals()` and hashes | Value object contract. |
| Same source values, calling `total()` multiple times | Same result | Derived field has no stale cache. |

Rules for `null`, `equals()`/`hashCode()`, post-normalization edge cases, object lifecycle, and reloaded data should all be verified with automated unit tests. If normalization rules change in a new version, assess the impact on map keys, database data, search, API clients, and existing records: changing equality policies can create or resolve business collisions.

## 7. Common Design Mistakes

1. **Letting `null` pass through multiple layers without defining its meaning:** null causes NPEs far from the origin. Validate at the object-creation boundary and publish the policy.
2. **Normalizing on only one creation path:** a factory normalizes, while an ORM/JSON mapper loads raw fields. As a result, the same business object has two representations, making equality and lookup inconsistent.
3. **Arbitrarily coercing empty strings to `null` or vice versa:** erases the business distinction between "not entered" and "intentionally left blank".
4. **Using the default locale for technical keys:** letter casing can vary by host machine/regional settings. For case-insensitive ASCII codes, use `Locale.ROOT` and specify the character set.
5. **Using `BigDecimal.compareTo()` in one place and `equals()` in another without stating a scale rule:** objects can be "equal" in calculations yet distinct in a `HashSet`.
6. **Storing and allowing separate edits to derived values:** easily creates inconsistent state when source data changes.
7. **Putting caches, observation timestamps, or mutable fields into `hashCode()`:** breaks key stability in hash collections.
8. **Using a record as an entity without examining default equality:** records compare all components and do not infer business identity automatically.

## 8. Contract Finalization Checklist

- For **each field**, document required/optional status, meaning of `null`/empty, valid values, and exception types on violation.
- Specify the **normalization algorithm**, execution order, rejected cases, and data that may be merged.
- Identify the **source of truth**; distinguish stored state, derived values, and caches.
- Lock down **equality/identity/hash**, avoiding dependence on mutable fields; check compatibility with collections and serialization.
- Ensure all object creation/loading paths use the same policy, and test edge cases and legacy data versions.

**Core principle:** A valid object must have a well-defined representation; semantically identical inputs must lead to the same canonical state, derived data must match the source, and all `equals()`/`hashCode()` behavior must reflect that policy.

## References

- [Java SE 17 — `Object.equals()` and `Object.hashCode()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)
- [Java SE 17 — `Objects.requireNonNull()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html)
- [Java SE 17 — `BigDecimal` and `RoundingMode`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)
- [Java SE 17 — `String.strip()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#strip())
- [Java Language Specification 17 — Record Classes](https://docs.oracle.com/en/java/javase/specs/jls/se17/html/jls-8.html#jls-8.10)