# `setParseBigDecimal` and Thread-Safety Limits When Using Formatters Concurrently in Java

`java.text.DecimalFormat` is a flexible floating-point formatter/parser in Java: it supports **decimal symbols, thousands grouping, pattern-based formatting, and locales**. However, two issues must be handled carefully when working with critical data:

1. **Type and precision of parse results.** `DecimalFormat#setParseBigDecimal(true)` instructs the parser to return `BigDecimal` for **ordinary finite numbers**, thereby avoiding converting the parse result through `double` first. This is especially useful for monetary data or long decimals.
2. **Concurrent safety (thread safety).** `DecimalFormat` and `NumberFormat` in standard usage are **not guaranteed to be thread-safe**. You must not share a mutable instance across multiple threads to `format`, `parse`, or mutate configuration concurrently without proper synchronization.

Example of parsing a string following US separator conventions:

```java
java.text.DecimalFormatSymbols symbols =
    java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US);

java.text.DecimalFormat df =
    new java.text.DecimalFormat("#,##0.00", symbols);

df.setParseBigDecimal(true);

Number result = df.parse("1,234.50");
// Actual runtime type of result: BigDecimal; decimal value: 1234.50.
```

This is an **illustrative code snippet** inside a method that declares/handles `ParseException` appropriately. By using `new DecimalFormat(..., symbols)`, we explicitly specify the meaning of commas and dots instead of relying on the environment's default locale.

**Important:** Enabling `setParseBigDecimal(true)` **does not make the formatter thread-safe**, **does not guarantee every input string is valid per business rules**, and **does not turn NaN/infinity into `BigDecimal`**. These limitations are independent of one another.

## 1. Distinguishing formatting (`format`) and parsing (`parse`)

`DecimalFormat` works in two directions:

- **`format(number)`**: takes a numeric value and produces a `String` per the pattern, fractional digit counts, separators, locale, and rounding rules.
- **`parse(text)`**: reads entered text into a `Number` using the formatter's symbols. `Number` is a superclass; the actual value can belong to several different classes.

```java
java.text.DecimalFormat df = new java.text.DecimalFormat(
    "#,##0.00",
    java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US)
);

String display = df.format(1234.5); // "1,234.50"
Number parsed = df.parse("1,234.50");
```

The declared return type of `parse(String)` is **`Number`**, not `BigDecimal` or `Double`. Therefore, to operate safely on a concrete type, you must know the **parser's configuration** and inspect the value before casting.

**Do not infer that the pattern `#,##0.00` automatically forces the parser to accept only exact two fractional digits.** The pattern primarily governs formatting and certain parse rules; parsing can still accept strings that violate an application's input policy. If strict format constraints are needed, validate the input separately.

## 2. What does `setParseBigDecimal(true)` change?

`DecimalFormat#setParseBigDecimal(boolean newValue)` controls how numeric strings are turned into `Number`:

- When **`true`**: for normally parsed finite numeric values, the method returns **`java.math.BigDecimal`**. The value is constructed from the parsed decimal digits rather than being forced through a `double`.
- When **`false`** (typically the default): the parser may return **`Long`** if the integer value fits in a `long`, or **`Double`** when the value does not fit `Long` or has a fractional part. Do not assume every result is always `Double`.
- **Important exception:** `NaN` and `±Infinity` are still represented as **`Double`**, even when `setParseBigDecimal(true)` is enabled.

```java
java.text.DecimalFormat df = new java.text.DecimalFormat(
    "#,##0.00",
    java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US)
);

df.setParseBigDecimal(true);
Number precise = df.parse("1,234.50"); // BigDecimal 1234.50

df.setParseBigDecimal(false);
Number ordinary = df.parse("42");      // Long 42 on the JDK under this parse rule
```

Because the declared return type `Number` stays the same, **you cannot blindly cast to `BigDecimal` based solely on calling `parse`**. You must know how the instance is configured and check for special values.

### Why is `BigDecimal` useful?

`double` has only about 15–17 significant decimal digits, so long numbers can get rounded when passed through binary floating-point. `BigDecimal` represents **decimal** numbers using an arbitrary-precision integer and a scale.

Example string:

```text
9,007,199,254,740,993.00
```

`9007199254740993` is an integer larger than `2^53`, which cannot be represented **exactly** as a `double`. With `setParseBigDecimal(true)` enabled, the parser returns a `BigDecimal` with decimal content **`9007199254740993.00`**. If very large non-integer data goes through `double`, rounding can alter the trailing digits.

**Do not misunderstand:** Enabling `BigDecimal` mode only preserves the precision of **the digits the parser actually read**. If data was already rounded by the sending system, or the input was malformed, the parser cannot recover lost original digits.

## 3. `setParseBigDecimal` is not a NaN and infinity filter

`BigDecimal` does not have `NaN`, `+Infinity`, or `-Infinity` values like `double`. Hence `DecimalFormat` uses `Double` for these special values even when `BigDecimal` parse mode is turned on.

```java
df.setParseBigDecimal(true);

Number nan = df.parse(df.getDecimalFormatSymbols().getNaN());
Number infinity = df.parse(df.getDecimalFormatSymbols().getInfinity());

// nan and infinity have actual runtime type Double, not BigDecimal.
```

The NaN/infinity symbol strings depend on the `DecimalFormatSymbols`/locale configuration. If the parser was created from another locale, do not assume the symbols are always written literally as ASCII `"NaN"` and `"Infinity"`.

For an API that requires returning a finite decimal, you can validate:

```java
Number number = df.parse(text);
if (!(number instanceof java.math.BigDecimal)) {
    throw new IllegalArgumentException("finite decimal required");
}
java.math.BigDecimal value = (java.math.BigDecimal) number;
```

This is an illustrative snippet to place in a method that handles `ParseException`. The `instanceof` check prevents **mistakenly casting `Double.NaN` or infinity to `BigDecimal`**.

Beyond choosing the numeric type, the application must also define what is permitted regarding **magnitude, sign, digit count, and units**. Parsing into `BigDecimal` does not mean the data has been validated by business rules.

## 4. Loss of the `-0.0` sign and differences in `Number`

A subtle edge case: floating-point types have **`+0.0` and `-0.0`** with distinct sign bits, whereas `BigDecimal` **does not store a separate negative zero sign**.

```java
df.setParseBigDecimal(true);
Number zero = df.parse("-0");
// BigDecimal has value 0, without preserving the negative sign of zero.
```

When `setParseBigDecimal(false)` and `isParseIntegerOnly()` is `false`, the parser may return **`Double(-0.0)`**, preserving the zero sign in that case.

Therefore, `BigDecimal` mode cannot be viewed as "always preserving every representation aspect of the string". It preserves the **decimal value** for finite numbers, without retaining every textual marker, floating-point type, or original presentation detail.

If you need to **retain the exact string the user entered** for re-display or auditing, store the original string separately alongside the parsed `BigDecimal` value. The parsed numeric value does not necessarily preserve a leading plus sign, leading zeros, comma grouping, locale symbols, or the `-0`/`0` distinction.

## 5. Be careful with `setParseIntegerOnly` and other settings

`setParseBigDecimal(true)` **does not override every parser option**. For example, `NumberFormat#setParseIntegerOnly(true)` causes the parser to accept only the integer part in many configurations:

```java
java.text.DecimalFormat df = new java.text.DecimalFormat(
    "#,##0.00",
    java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US)
);
df.setParseBigDecimal(true);
df.setParseIntegerOnly(true);

Number value = df.parse("12.75");
// The parser may stop at the decimal separator and read only the integer part.
```

Do not treat enabling `parseBigDecimal` as a guarantee that fractional parts are preserved if other settings block the parser from reading them. Conversely, `setRoundingMode` controls **rounding when formatting**; it does not turn decimal input into a rounded value during parsing.

`DecimalFormat` settings such as pattern, symbols, grouping, `setParseIntegerOnly`, `setParseBigDecimal`, `setMaximumFractionDigits`, and `setRoundingMode` should all be established **before the formatter is used** for its task. Mutating them on an instance shared across threads creates logic bugs and thread-safety hazards.

## 6. `parse(String)` can accept a leading prefix

A dangerous data bug: `DecimalFormat.parse(String)` does not necessarily require **the entire input string** to be consumed. It can read a valid prefix and leave the trailing suffix without throwing an error.

```java
Number parsed = df.parse("1,234.50oops");
// Can parse 1234.50, even though "oops" remains.
```

A parse call that succeeds is **not enough** to prove the string conforms to the input contract.

If the full input must be accepted, use **`ParsePosition`**:

```java
static java.math.BigDecimal parseAll(
        java.text.DecimalFormat format, String input) {

    java.text.ParsePosition position = new java.text.ParsePosition(0);
    Number result = format.parse(input, position);

    if (result == null
            || position.getIndex() != input.length()
            || !(result instanceof java.math.BigDecimal)) {
        throw new IllegalArgumentException("invalid decimal");
    }
    return (java.math.BigDecimal) result;
}
```

The method requires the caller to pass a formatter with `setParseBigDecimal(true)` enabled. It checks three things: parsing did not fail immediately, **the entire string was consumed**, and the actual result is a `BigDecimal` (excluding NaN/infinity). `ParsePosition` avoids `ParseException` because the parser returns `null` with an error index, while this code explicitly throws `IllegalArgumentException` if the contract is not met.

**Limitation:** Consuming the entire string **still does not guarantee commas are grouped properly in every position or that the fractional digit count matches application policy**. If only two decimal digits or strict formatting are allowed, add a corresponding input-string/format-grammar validation step. Do not rely on the formatter pattern alone as a complete validator.

### When should you use `BigDecimal(String)` instead of `DecimalFormat`?

If the input is a **locale-independent** machine format such as `"1234.50"`, consider `new BigDecimal("1234.50")`:

```java
java.math.BigDecimal value = new java.math.BigDecimal("1234.50");
```

This constructor parses decimal strings using `BigDecimal` syntax and does not interpret grouping separators like `"1,234.50"`. `DecimalFormat` is better suited when numbers must be read/written in the **user's locale**; `BigDecimal(String)` is better suited when an API or config file uses a **canonical decimal format**.

## 7. `DecimalFormat` is not thread-safe: where does the problem lie?

`DecimalFormat` is a **mutable** object storing patterns, symbols, parse modes, and related state. The Java documentation requires that if multiple threads access one formatter concurrently, the application must **synchronize externally**.

Unsafe design example:

```java
// Do NOT share like this:
static final java.text.DecimalFormat SHARED =
    new java.text.DecimalFormat("#,##0.00");

// Thread A:
String output = SHARED.format(1234.5);

// Thread B:
Number number = SHARED.parse("1,234.50");
```

These are illustrative snippets, not a standalone file. `static final` only makes the reference unable to be reassigned to another formatter; it **does not** make the `DecimalFormat` object immutable or make its methods thread-safe.

Risks of unsynchronized concurrent access include **corrupted parse/format results, corrupted internal state, or non-deterministic behavior**. Do not write a "race demo" promising it reproduces on every run, since concurrency bugs depend on scheduling, JDK internals, and system load.

Even when multiple threads **only call `format`**, it must not be assumed safe by default. A formatter can use mutable internal state while working; do not rely on a hunch that "read-only" means thread-safe. When formatting/parsing happens alongside changing patterns, symbols, or `setParseBigDecimal` on a shared instance, the hazard becomes even clearer.

## 8. Three ways to use formatters safely across multiple threads

### Approach A — creating local instances: simple and easy to get right

```java
static java.math.BigDecimal parseAmount(String input) {
    java.text.DecimalFormat formatter = makeFormatter();
    return parseAll(formatter, input);
}

static java.text.DecimalFormat makeFormatter() {
    var symbols = java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US);
    var formatter = new java.text.DecimalFormat("#,##0.00", symbols);
    formatter.setParseBigDecimal(true);
    return formatter;
}
```

Illustrative code inside a class containing the corresponding methods. Each call gets its own formatter, with no mutable object shared across threads. This approach fits when **clarity and safety matter more than allocation cost** or when call volume is moderate.

**Pros:** no locks needed; configuration cannot leak across calls. **Cons:** allocates a formatter and symbols on every call. If this is a performance hotspot, measure before optimizing.

### Approach B — `ThreadLocal<DecimalFormat>`: one formatter per thread

```java
private static final ThreadLocal<java.text.DecimalFormat> LOCAL =
    ThreadLocal.withInitial(() -> {
        var symbols =
            java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US);
        var formatter = new java.text.DecimalFormat("#,##0.00", symbols);
        formatter.setParseBigDecimal(true);
        return formatter;
    });

static java.math.BigDecimal parseLocal(String input) {
    return parseAll(LOCAL.get(), input);
}
```

Each thread receives its own `DecimalFormat`. Make sure **not to pass the formatter from one thread to another** and not to mutate options in one call assuming the next call resets automatically. If using long-lived thread pools and objects in `ThreadLocal` have a broad lifecycle, consider calling `LOCAL.remove()` when the usage scope ends, or simply use local formatters for clearer lifecycle management.

`ThreadLocal` only prevents *the same instance* from being accidentally shared if used properly; it **does not turn a mutable formatter into an immutable one**. Relying on state left behind on a thread-local formatter by a previous task in a pool can also cause semantic bugs.

### Approach C — external synchronization when sharing is truly required

```java
private static final java.text.DecimalFormat LOCKED = makeFormatter();

static java.math.BigDecimal parseLocked(String input) {
    synchronized (LOCKED) {
        return parseAll(LOCKED, input);
    }
}

static String formatLocked(java.math.BigDecimal amount) {
    synchronized (LOCKED) {
        return LOCKED.format(amount);
    }
}
```

Every access to the same instance, **including reading/changing settings and calling parse/format**, must coordinate on the same lock. Locking only one method while leaving other usage paths unlocked does not solve the problem.

**Pros:** fits when sharing a single formatter is mandatory. **Cons:** lock contention, threads waiting; error-prone if other code accesses the formatter outside the lock. Avoid exposing the `LOCKED` instance publicly where external code could call it directly.

**Practical recommendation:** Unless there is a specific reason to share, **creating a separate formatter per call or per thread** is usually easier to reason about than sharing one locked formatter.

## 9. Locale, parsing, and precision are three independent decisions

### Locale determines the decimal and grouping separators

`DecimalFormatSymbols` determines the symbols used to read and display numbers. For example, the pattern `#,##0.00` with `Locale.US` displays `1234.50` as `"1,234.50"`, using a **dot** for decimal and a **comma** for grouping. In other locales, symbols can differ, including special whitespace characters.

```java
var symbols = java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US);
var df = new java.text.DecimalFormat("#,##0.00", symbols);
df.setParseBigDecimal(true);
```

**Do not build a formatter using the default locale on the sender and parse assuming US separators on the receiver.** Machine communication formats should be defined independently of UI locales; user-entered data must carry the exact locale and parsing policy.

### Parsing `BigDecimal` does not determine display rounding

```java
var df = new java.text.DecimalFormat(
    "#,##0.00",
    java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US)
);
df.setParseBigDecimal(true);
df.setRoundingMode(java.math.RoundingMode.HALF_UP);

java.math.BigDecimal amount = new java.math.BigDecimal("1.005");

String shown = df.format(amount); // "1.01"
```

`amount` remains `1.005`; the formatter only produces a **rounded string for display**. If you need to store a value rounded to exact two decimal places, use `BigDecimal`'s API, such as `amount.setScale(2, RoundingMode.HALF_UP)`, and define the business policy clearly.

Do not use `df.format(value)` followed by `df.parse(...)` as a core arithmetic rounding mechanism: round-tripping through strings/locales increases complexity and can lose information (such as fractional digit count, negative zero, or other string representation details). Keep **numeric calculation** separate from **display formatting**.

## 10. Standalone runnable Java 17+ program

Create the file `BigDecimalParseDemo.java`:

```java
public class BigDecimalParseDemo {
    static java.text.DecimalFormat makeFormatter() {
        var symbols =
            java.text.DecimalFormatSymbols.getInstance(java.util.Locale.US);
        var format = new java.text.DecimalFormat("#,##0.00", symbols);
        format.setParseBigDecimal(true);
        return format;
    }

    static java.math.BigDecimal parseAll(
            java.text.DecimalFormat format, String s) {

        java.text.ParsePosition pos = new java.text.ParsePosition(0);
        Number number = format.parse(s, pos);

        if (number == null
                || pos.getIndex() != s.length()
                || !(number instanceof java.math.BigDecimal)) {
            throw new IllegalArgumentException("invalid decimal");
        }
        return (java.math.BigDecimal) number;
    }

    public static void main(String[] args) throws Exception {
        var df = makeFormatter();

        Number precise = df.parse("9,007,199,254,740,993.00");
        System.out.println("precise type: "
            + precise.getClass().getSimpleName());
        System.out.println("precise value: "
            + ((java.math.BigDecimal) precise).toPlainString());

        Number cents = df.parse("1,234.50");
        System.out.println("cents: "
            + ((java.math.BigDecimal) cents).toPlainString());

        System.out.println("negative zero: "
            + df.parse("-0").getClass().getSimpleName()
            + " " + df.parse("-0"));

        df.setParseBigDecimal(false);
        Number ordinary = df.parse("9,007,199,254,740,993.00");
        System.out.println("ordinary type: "
            + ordinary.getClass().getSimpleName());
        System.out.println("ordinary value: " + ordinary);
        System.out.println("integer type: "
            + df.parse("42").getClass().getSimpleName());

        df.setParseBigDecimal(true);
        System.out.println("NaN type: "
            + df.parse("NaN").getClass().getSimpleName());
        System.out.println("Infinity type: "
            + df.parse(df.getDecimalFormatSymbols().getInfinity())
                .getClass().getSimpleName());

        java.text.ParsePosition pos = new java.text.ParsePosition(0);
        Number prefix = df.parse("1,234.50oops", pos);
        System.out.println("prefix parsed: " + prefix
            + ", consumed: " + pos.getIndex());

        System.out.println("strict valid: "
            + parseAll(df, "1,234.50").toPlainString());

        try {
            parseAll(df, "1,234.50oops");
        } catch (IllegalArgumentException ex) {
            System.out.println("strict trailing: rejected");
        }
        try {
            parseAll(df, "NaN");
        } catch (IllegalArgumentException ex) {
            System.out.println("strict NaN: rejected");
        }

        df.setRoundingMode(java.math.RoundingMode.HALF_UP);
        System.out.println("formatted: "
            + df.format(new java.math.BigDecimal("1.005")));
        System.out.println("input unchanged: "
            + new java.math.BigDecimal("1.005").toPlainString());
    }
}
```

Compile/run:

```bash
javac BigDecimalParseDemo.java
java BigDecimalParseDemo
```

Stdout verified with the JDK:

```text
precise type: BigDecimal
precise value: 9007199254740993.00
cents: 1234.50
negative zero: BigDecimal 0
ordinary type: Long
ordinary value: 9007199254740993
integer type: Long
NaN type: Double
Infinity type: Double
prefix parsed: 1234.50, consumed: 8
strict valid: 1234.50
strict trailing: rejected
strict NaN: rejected
formatted: 1.01
input unchanged: 1.005
```

**Output explanation:**

1. `BigDecimal` parsing preserves `9007199254740993.00` and `1234.50` in decimal form. `-0` becomes `BigDecimal 0`.
2. When `parseBigDecimal` is disabled, integer values can return `Long`, not always `Double`. For values with fractional parts that cannot return `Long`, the parser can return `Double` and introduce binary error.
3. NaN and infinity remain `Double`; `BigDecimal` parse mode does not convert them into decimal objects.
4. The parser consumed 8 characters of `"1,234.50oops"` and left the suffix; `parseAll` checks the entire input to reject it.
5. `RoundingMode.HALF_UP` affects the **formatted** string `1.005 → "1.01"`, without changing the original `BigDecimal` value.

The example creates a formatter **local to `main`**, without sharing the same instance across multiple threads. That is a safe way to avoid state sharing in the example's scope; in multithreaded services, apply the patterns from section 8.

## 11. Checklist for designing reliable parse/format APIs

- **Define the input format:** which locale's user string is it, or is it a canonical machine-system string?
- **Decide the result type:** `BigDecimal` for finite decimals requiring precision, or `Double` when binary floating-point is acceptable?
- **Check the full string:** use `ParsePosition` and compare `getIndex() == input.length()`; add strict validation if specific grouping or digit counts are required.
- **Reject special values if invalid:** `NaN` and `Infinity` can still return `Double` even with `setParseBigDecimal(true)`.
- **Specify separate rounding rules:** `RoundingMode` for formatting/`BigDecimal.setScale` for arithmetic results per business rules.
- **Isolate formatters from threads:** local instances, properly used `ThreadLocal`, or synchronizing all accesses to a shared instance.
- **Avoid mutating configuration between calls:** do not let thread A change locale/pattern/parse mode while thread B is parsing.
- **Test boundary inputs:** long strings, many fractional digits, negatives, signed zero, NaN, infinity, invalid grouping, strings with suffixes, numbers larger than `double` precision.
- **Monitor performance after correctness:** allocating a formatter each time has a cost, but using an unsynchronized shared instance is the wrong optimization. Pick an alternative only after real benchmarking.

**Concurrent** safety and **arithmetic** precision are two independent problems: enabling `setParseBigDecimal` avoids rounding through `double` when parsing finite numbers, yet cannot eliminate data races. Conversely, locking a formatter does not make decimal data accurate if it still parses to `Double`.

## 12. Common mistakes

1. **"Enabling `setParseBigDecimal(true)` means `parse` always returns `BigDecimal`."** False: NaN/infinity can still be `Double`.
2. **"Disabling `setParseBigDecimal` always returns `Double`."** False: in-range integer values can return `Long`.
3. **"If `parse(String)` succeeds, the entire string was read."** False: the parser may accept only a prefix; use `ParsePosition` when full consumption is required.
4. **"Matching pattern `#,##0.00` guarantees the input string has exact two fractional digits."** False: formatter patterns do not replace business validation.
5. **"`BigDecimal` automatically stores the sign of negative zero."** False: `BigDecimal` has no signed zero like `double`.
6. **"`parseBigDecimal` keeps grouping characters and input locale formatting inside the result object."** False: it parses into a numeric value; to keep the original text, store it separately.
7. **"`setRoundingMode` causes the parser to parse digits into a rounded `BigDecimal`."** False: `setRoundingMode` is used when formatting; to round numeric data, use `BigDecimal.setScale` explicitly.
8. **"`static final DecimalFormat` is safe for multiple threads."** False: `final` only fixes the reference; it does not make a mutable object thread-safe.
9. **"If threads only call `format`, sharing a formatter is safe by default."** False: there is no general thread-safety guarantee.
10. **"`ThreadLocal` is always ideal and needs no state management."** False: long-lived thread pools can retain instances and state across tasks; avoid configuration/lifecycle leaks.
11. **"Synchronize only the `parse` call, and `setParseBigDecimal` needs no lock."** False: every access to the same shared formatter must coordinate under the same mechanism.
12. **"`new BigDecimal(double)` can recover the exact decimal string the user originally typed."** False: a binary-rounded `double` does not hold enough source information.
13. **"Using a singleton formatter is guaranteed to be fastest."** False: synchronization introduces contention; allocation cost vs thread confinement must be benchmarked.
14. **"Use `DecimalFormat` to serialize all numbers to a stable machine format without specifying a locale."** False: the default locale can change and alter numeric characters.

## 13. Self-check

**1. What return type is `DecimalFormat.parse(String)` declared to return?** → `Number`.

**2. What does enabling `setParseBigDecimal(true)` do?** → Parses ordinary finite numeric values into `BigDecimal`, avoiding conversion through `double`.

**3. Are there cases where that mode still returns `Double`?** → Yes: `NaN` and `Infinity`.

**4. If `setParseBigDecimal` is disabled, is the result always `Double`?** → No; the parser can return `Long` for integer values.

**5. Does `parse("1,234.50oops")` returning a number mean the string is completely valid?** → No. You need `ParsePosition` and a check that the entire string was consumed.

**6. Does a two-decimal pattern guarantee validating exact two fractional digits in an input string?** → No; independent format validation is needed if that is mandatory.

**7. Does parsing `"-0"` into `BigDecimal` preserve signed zero?** → No; the `BigDecimal` value equals 0.

**8. Can a `static final DecimalFormat` be used from multiple threads without synchronization?** → No thread-safety guarantee exists; use separate instances or full locking.

**9. What is the simplest way to avoid sharing a mutable formatter across threads?** → Create a local formatter for each call.

**10. Does `setRoundingMode(HALF_UP)` alter the `BigDecimal("1.005")` object after `format`?** → No; only the displayed string is rounded by the formatter.

**Takeaway:** `setParseBigDecimal(true)` makes `DecimalFormat` return **`BigDecimal` for parsed finite decimals**, yet does not apply to `NaN`/infinity, does not validate the whole string on its own, and does not protect against all loss of original presentation. `DecimalFormat` is **mutable and not thread-safe**: each thread/call needs its own formatter or all shared accesses must be synchronized. Separate **input validation, exact parsing, rounded formatting, and concurrency management** into four distinct responsibilities.