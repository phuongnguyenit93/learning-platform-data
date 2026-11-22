# Normalizing Data Before Comparison in Java

## 1. Why Is Normalization Needed?

When defining **equality semantics** between two Java objects, we first need to answer: “Should these two different representations be considered the same value under business rules?”. The answer depends on the data type and the purpose of the comparison.

For example:

- `"  Alice "` and `"alice"` may be the same **username** if the system specifies trimming leading/trailing whitespace and ignoring case; however, for a password, those two strings should **not** be automatically treated as identical.
- `new BigDecimal("1.0")` and `new BigDecimal("1.00")` have the same numeric value, yet `BigDecimal.equals()` returns `false` because their `scale` differs.
- Two Unicode encodings such as `"é"` (precomposed character) and `"e\u0301"` (letter e plus combining accent) may look identical, yet direct `String.equals()` returns `false` because the code point sequences differ.
- `2026-01-01T00:00:00Z` and `2026-01-01T07:00:00+07:00` represent the exact same absolute instant; if the problem cares about “the same point in time”, compare representations converted to `Instant` instead of comparing raw strings.

**Normalization (normalization/canonicalization)** is transforming an input representation according to a **chosen rule**, producing a canonical form so that representations permitted to be equivalent become the same comparable value.

A common model:

```text
Raw data A ──normalize N──► N(A) ─┐
                                  ├── compare by value ──► equal/different
Raw data B ──normalize N──► N(B) ─┘
```

Here `N` must be a rule belonging to the data domain itself. There is no universal normalization function that applies correctly to all strings, numbers, currencies, times, or identifiers.

## 2. Choose Equality Semantics Before Choosing Transformations

Determine what is **meaningful in the business domain**:

| Data domain | Example equality relation | Caveat |
| --- | --- | --- |
| Case-insensitive username | `" ALICE "` and `"alice"` may be treated as one, if policy allows stripping whitespace and ignoring case | Unicode rules and allowed characters must be published and stable. |
| Password/secret | Equal only under the designed password verification mechanism | Do not arbitrarily `trim()`, lowercase, or strip accents and lose user input information. |
| Product code, warehouse code | Depends on specification: may need to preserve case and leading zeros | `"00012"` is not by default equal to `"12"`. |
| Decimal number representing numeric value | `1.0` and `1.00` are equal if only numeric value matters | `BigDecimal.equals()` distinguishes `scale`; numeric value and representation precision may carry different meanings. |
| Monetary amount | Same value **and** same currency unit | `100 VND` differs from `100 USD`; do not compare only the numeric part. |
| Event timestamp | Two inputs representing the same `Instant` | Do not equate “same local wall-clock time” with “same instant”. |
| Issued identifier | Usually must match identifier as issued by the issuing system | Do not arbitrarily strip separators, leading zeros, or prefixes. |

In Java, normalization **does not happen automatically** when using `==` or `equals()`:

- `==` between two references checks **object identity**, never normalizing contents.
- `String.equals()` compares strings by UTF-16 code units in a case-sensitive manner and does not automatically normalize Unicode.
- `Objects.equals(a, b)` only provides `null`-safe comparison; when both are non-null, it calls `a.equals(b)`.
- A class with a custom `equals()` can compare by canonical form if that is part of the class's equality contract.

The design conclusion must be clear: **normalization should only be applied when it matches the chosen meaning of the equality relation**.

## 3. What Properties Does a Good Canonical Form Need?

### 3.1. Consistent and Deterministic

The same input under the same policy must yield the same canonical form. Avoid letting `equals()` depend on the machine's default locale, current time, randomly changing configuration, or externally mutable data.

### 3.2. Stable Under Re-application

Usually **idempotence** is desired:

```text
N(N(x)) = N(x)
```

For example, a username that has already had leading/trailing whitespace stripped, been lowercased, and NFC-normalized should not continue changing when processed again by the same rule. The rule must be verified against the set of inputs accepted by the system.

### 3.3. Do Not Merge Values That Must Stay Distinct

If `N(a) == N(b)`, the system will tend to treat `a` and `b` as equal. That is valid only when the business domain truly permits it. For instance, stripping all Vietnamese diacritics can conflate distinct names or codes; deleting all spaces can turn `"A B"` into `"AB"` even when those are two independent identifiers.

This is a **semantic** change, not cosmetic string cleanup.

### 3.4. Handle Invalid Data and `null` Explicitly

Determine in advance whether `null`, empty strings, or whitespace-only strings are accepted. They can be rejected right in the constructor using `Objects.requireNonNull` and `IllegalArgumentException`. If input can be `null`, specify whether `null` means missing data or a special value; do not silently convert `null` to `""` if the two states have different meanings.

### 3.5. Preserve the `equals` and `hashCode` Contract

If a class compares by `canonicalValue`, it must compute `hashCode()` from **the exact same normalized components**.

```text
a.equals(b) == true  ⇒  a.hashCode() == b.hashCode()
```

The converse is not required because hash codes may collide. At the same time, the components used for comparison and hashing should be **immutable while the object is used as a key** in a `HashMap` or an element of a `HashSet`.

## 4. String Normalization: Decide Each Step Explicitly

### 4.1. Trimming Boundary Whitespace

- `String.trim()` only removes leading/trailing characters with code points less than or equal to U+0020.
- `String.strip()` (Java 11+) considers whitespace according to `Character.isWhitespace`, which is usually more appropriate for many Unicode texts; however, it **does not handle every space-like character**, such as certain no-break spaces.
- Do not automatically remove or collapse whitespace **inside** a string unless business rules specify it. `"Van An"` differs from `"VanAn"` in many systems.

### 4.2. Uppercase and Lowercase

`toLowerCase(Locale.ROOT)` is useful when an identifier rule needs lowercasing **independent of the environment's default locale**. Calling `toLowerCase()` with no arguments can produce varying results depending on the host locale, especially for cases like the letter I in Turkish.

However, lowercasing with `Locale.ROOT` **is not full Unicode case folding** for every language; matching personal names, natural-language search strings, or protocol standards may require dedicated rules (`Collator`, the relevant Unicode standard, or a specialized library).

### 4.3. Unicode Normalization

`java.text.Normalizer` supports:

- **NFC:** canonical composition form; often useful when canonically equivalent Unicode representations should compare equal.
- **NFD:** canonical decomposition form.
- **NFKC/NFKD:** compatibility normalization forms, which can merge additional characters that differ only in compatibility representation; this is a stronger transformation that can erase meaningful distinctions.

Example for a username allowing case-insensitivity and accepting canonically equivalent Unicode representations:

```java
static String normalizeHandle(String input) {
    String trimmed = input.strip();
    String lowered = trimmed.toLowerCase(java.util.Locale.ROOT);
    return java.text.Normalizer.normalize(
            lowered, java.text.Normalizer.Form.NFC);
}
```

The snippet above is an **illustrative helper**, embedded into the complete program in section 6. The order of transformations is part of the policy and must stay consistent across all input, query, and update paths. Apply this only when the application has chosen this username policy; it is not a universal normalization algorithm for emails, URLs, or personal names.

**Security note:** NFC does not eliminate visually similar characters with different Unicode code points (confusables), nor does it automatically protect against all name-spoofing cases. Identity systems need an allowed-character policy and proper uniqueness checks.

## 5. Normalizing Other Data Types

### 5.1. `BigDecimal`: Numeric Value and Scale

`BigDecimal` stores a decimal value together with a `scale`:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

// a.equals(b) => false: different scale
// a.compareTo(b) == 0 => true: same numeric value
```

This illustrative snippet requires `import java.math.BigDecimal;`. If the desired equality relation **compares only numeric value**, you can:

1. Compare directly using `a.compareTo(b) == 0` wherever numeric equality is needed.
2. Produce a canonical value with `stripTrailingZeros()` and then use `equals()/hashCode()` on the canonical form inside a value object.

`stripTrailingZeros()` can produce a power-of-10 representation, such as turning `600.0` into a form with a negative scale; do not rely on the printed string to judge it. For zero, you can normalize to `BigDecimal.ZERO`. Do not round before comparing unless domain rules permit it; rounding can merge values that must stay distinct.

### 5.2. Floating-Point `double` and Tolerance

Do not put a rule like “`Math.abs(a-b) < epsilon`” into a value object's `equals()` by default: this kind of approximate closeness can be **non-transitive**. For example, with `epsilon = 0.1`, `a = 0.00` is close to `b = 0.06` and `b` is close to `c = 0.12`, yet `a` is not close to `c`. That violates the `equals` contract.

If the problem requires tolerance, use a separately named method such as `approximatelyEqual(a, b, tolerance)` for numerical algorithms; or design a quantization step on fixed boundaries if you **genuinely** want bucketed equality. When comparing floating-point numbers, also define rules for `NaN` and `-0.0`, since `Double.equals()` has different semantics from primitive `==`.

### 5.3. Dates and Times

If the requirement is “same instant on the timeline”, convert values carrying an offset/zone to `Instant`:

```java
Instant a = OffsetDateTime.parse(
        "2026-01-01T00:00:00Z").toInstant();
Instant b = OffsetDateTime.parse(
        "2026-01-01T07:00:00+07:00").toInstant();

// a.equals(b) => true
```

The illustrative snippet above requires `import java.time.Instant;` and `import java.time.OffsetDateTime;`. Conversely, an appointment “9 AM in Hanoi” or a `LocalDate` may need to be compared by local date/time, not necessarily by `Instant`. Do not arbitrarily apply a timezone without understanding the source data.

### 5.4. Identifiers and Structured Formats

For phone numbers, emails, URLs, file paths, customer codes, or international codes, “reasonable-looking” transformations can introduce errors:

- Email: the local part and provider policies have varying constraints; do not blindly remove dots or “+tag” suffixes for every address.
- Phone number: normalizing to international format requires knowing the country and numbering rules; stripping non-digits is not enough to identify the number.
- URL/path: case sensitivity, slashes, percent-encoding, query parameters, or relative paths can change the resource identifier.
- Product code: hyphens, prefixes, and leading zeros may be part of the code itself.

Only use normalizations defined by the specification/data domain and appropriate libraries.

## 6. Standalone Runnable Java 17+ Example: Canonical Username and Decimal Numbers

Create the file **`NormalizationEqualityDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.Normalizer;
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class NormalizationEqualityDemo {

    static final class UserHandle {
        private final String submitted;
        private final String canonical;

        UserHandle(String submitted) {
            this.submitted = Objects.requireNonNull(
                    submitted, "submitted");
            this.canonical = normalizeHandle(submitted);
            if (canonical.isEmpty()) {
                throw new IllegalArgumentException("Blank handle");
            }
        }

        private static String normalizeHandle(String input) {
            String trimmed = input.strip();
            String lower = trimmed.toLowerCase(Locale.ROOT);
            return Normalizer.normalize(lower, Normalizer.Form.NFC);
        }

        String displayValue() {
            return submitted;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof UserHandle handle)) {
                return false;
            }
            return canonical.equals(handle.canonical);
        }

        @Override
        public int hashCode() {
            return canonical.hashCode();
        }
    }

    static BigDecimal normalizeAmount(BigDecimal input) {
        Objects.requireNonNull(input, "input");
        if (input.signum() == 0) {
            return BigDecimal.ZERO;
        }
        return input.stripTrailingZeros();
    }

    public static void main(String[] args) {
        String decomposed = "  CAFE\u0301  ";
        String composed = "café";

        System.out.println("raw text equal: "
                + decomposed.equals(composed));

        UserHandle first = new UserHandle(decomposed);
        UserHandle second = new UserHandle(composed);
        Set<UserHandle> handles = new HashSet<>();
        handles.add(first);

        System.out.println("same reference: " + (first == second));
        System.out.println("same normalized value: "
                + first.equals(second));
        System.out.println("same hash: "
                + (first.hashCode() == second.hashCode()));
        System.out.println("set contains second: "
                + handles.contains(second));

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");
        System.out.println("raw BigDecimal equals: " + a.equals(b));
        System.out.println("numeric compareTo zero: "
                + (a.compareTo(b) == 0));
        System.out.println("canonical BigDecimal equals: "
                + normalizeAmount(a).equals(normalizeAmount(b)));

        System.out.println("null safe equal: "
                + Objects.equals(null, null));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac NormalizationEqualityDemo.java
java NormalizationEqualityDemo
```

Expected output:

```text
raw text equal: false
same reference: false
same normalized value: true
same hash: true
set contains second: true
raw BigDecimal equals: false
numeric compareTo zero: true
canonical BigDecimal equals: true
null safe equal: true
```

**Why is this right?**

1. `"  CAFE\u0301  "` and `"café"` do not match under `String.equals()` because they differ in whitespace, case, and Unicode accent representation.
2. The `UserHandle` constructor normalizes once and stores `canonical` as `final`. After `strip()`, lowercasing with `Locale.ROOT`, and NFC, both obtain the canonical form `"café"`.
3. Two `new UserHandle(...)` calls create two distinct objects (`==` is `false`), yet the class's `equals()` compares `canonical` and therefore returns `true`.
4. `hashCode()` is also based on `canonical`, so the hashes match. Thus `HashSet.contains(second)` returns `true` after adding `first`.
5. Two `BigDecimal` instances have the same numeric value but different scales, so direct `equals()` returns `false`; `compareTo` and the `stripTrailingZeros()` normalization function express the “same numeric value” rule.
6. `Objects.equals(null, null)` returns `true`; this is a null-handling utility, not automatic value normalization.

In the program, `displayValue()` preserves the user's input for display; in a real system, both the raw value and the canonical form can be stored for lookup/uniqueness. Avoid displaying the canonical key instead of the original if doing so strips formatting the user wishes to keep.

## 7. Where Should Normalization Happen in an Application?

**At the input boundary:** read, validate, and transform to the canonical form before constructing a value object or persisting to the database. The canonical form should be immutable inside the object; `equals()` and `hashCode()` become concise, fast, and consistent.

**At lookup points:** transform queries using **the exact same rule** used when storing. If usernames are stored in NFC + lowercase form but queried differently, a valid value may not be found.

**At the data layer:** align application rules with unique indexes, collations, or canonical keys in the database. Java's `String.equals()` and database string comparisons may have different semantics; checking duplicates only in Java without a consistent database mechanism can produce duplicate data under concurrent access.

**When policies change:** versioning of the normalization transformation can affect legacy data, key collisions, or login behavior. If Unicode rules, case sensitivity, or whitespace handling change, plan a migration and conflict detection instead of silently altering `equals()`.

### Why Not Re-normalize Arbitrarily Inside Every `equals()` Call?

In theory you could normalize inside `equals()`, yet doing so easily incurs extra cost, duplicates logic, and risks forgetting to keep `hashCode()` in sync. If the transformation depends on environment-varying locale/config or mutable data, equality results and hash codes can even become unstable. For objects used as keys in collections, compute `canonical` once under a fixed policy in the constructor/factory.

## 8. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `trim()/lowercase` on only one side | Two equivalent inputs may still differ | Normalize both inputs consistently or store the canonical form. |
| `equals()` compares canonical, `hashCode()` uses raw string | Breaks hash contract; `HashSet`/`HashMap` misbehave | Both use the same canonical fields. |
| Calling `toLowerCase()` with no arguments | Result can vary with default locale | Use `Locale.ROOT` if business rules require locale-independent comparison. |
| Choosing NFKC or stripping accents “to match easily” | Accidentally merges values that must remain distinct | Apply only transformations permitted by specification; test edge cases. |
| Conflating null and empty string | Loses the distinction between “not provided” and “provided as empty” | Define an explicit validation/null policy. |
| Comparing `BigDecimal.equals()` when domain cares only about numeric value | `1.0` and `1.00` are treated as different | Use `compareTo` or canonical amount per policy. |
| Using epsilon in `equals()` | Can violate transitivity | Use a dedicated approximate comparison function or a designed quantization. |
| Checking uniqueness only in the application | Two concurrent requests can create semantically duplicate data | Use a unique constraint/index aligned with the canonical key. |
| Mutating the canonical value after inserting into `HashMap` | Cannot find the key again in the expected bucket | Design an immutable value object or immutable key. |

## 9. Self-Check

**Question 1.** If a system treats usernames as case-insensitive while passwords are sensitive to every character, may the same `strip().toLowerCase(Locale.ROOT)` be applied to both?

**Answer:** No. Equality semantics are decided by the data domain; normalizing a password by username rules can change its meaning and lose information.

**Question 2.** Why do two objects with equal `canonical` values need a `hashCode()` based on canonical?

**Answer:** Because Java's contract requires two objects equal under `equals()` to have the same `hashCode()`. Hash collections rely on this for accurate lookups.

**Question 3.** What does `new BigDecimal("10.0").equals(new BigDecimal("10.00"))` return? If only numeric value matters, how should they be compared?

**Answer:** `false` because of differing `scale`. You can use `a.compareTo(b) == 0` or compare canonical `BigDecimal` values according to the chosen rule.

**Question 4.** Does Unicode NFC normalization make every pair of visually similar characters equal?

**Answer:** No. NFC handles canonical Unicode equivalence; it does not handle all lookalike characters or every language-specific matching requirement.

**Question 5.** Can `Math.abs(a - b) < 0.1` be used as a general `Object.equals()` implementation for all floating-point numbers?

**Answer:** No. Approximate closeness may not be transitive, violating the `equals()` contract.

**Takeaway:** **Define equality semantics first; normalize strictly according to those semantics; ensure `equals()` and `hashCode()` use the same immutable canonical form.**