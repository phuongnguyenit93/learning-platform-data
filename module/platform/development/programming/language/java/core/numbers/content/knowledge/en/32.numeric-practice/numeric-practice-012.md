# Completing an Integrated Example with Boundary Data Tests — Java Core Numbers

## 1. Objectives and Final Deliverable

This practice completes **a standalone Java 17 program** combining multiple Java numeric concepts in a single processing flow: parsing decimal inputs, converting to integer minor units, validating quantities, multiplying and adding with overflow detection, calculating tax with explicit rounding rules, formatting results, and testing boundary data.

Illustrative problem: calculating the total for **one invoice line**. Inputs consist of a decimal unit price as a string, a quantity as a string, and a tax rate as a string. Outputs are three `long` integer values: subtotal, tax, and total, all measured in **cents**. The algorithm includes an automated test suite requiring no external libraries, producing deterministic results when run on JDK 17 or newer.

Specific verification requirements:

- Unit price is non-negative, ASCII digits only; at most two fractional digits. Strings with negative signs, commas, whitespace, or exponents are rejected.
- Quantity is a positive integer within the `int` range, unsigned and with no fractional part.
- Tax rate lies between 0 and 1 and has at most four decimal places; e.g., 0.075 means 7.5%.
- Every multiplication and addition producing a `long` result must **detect overflow**, never silently wrap around.
- Tax rounds to cents using **HALF_EVEN** (rounding to the nearest even integer on exact midpoints).
- Malformed or out-of-range inputs are rejected; out-of-range numbers during conversion or calculation report errors.
- The test suite covers normal cases, valid boundary values, values just outside the boundary, half-step rounding cases, NaN, infinity, and overflow.

This is a numeric data design example, **not a real-world invoicing or tax system**: cents and tax rates are purely illustrative and do not represent rules of any specific country or currency.

## 2. Defining the Contract Before Writing Code

| Component | Input type | Rule | Stored type after validation |
| --- | --- | --- | --- |
| Unit price | String | Pattern `[0-9]+(?:\\.[0-9]{1,2})?`, non-negative | long cents |
| Quantity | String | Digits only, value 1 to Integer.MAX_VALUE | int |
| Tax rate | String | From 0 to 1, at most 4 decimal places | BigDecimal |
| Subtotal | long cents times int | Does not exceed long | long |
| Tax | Subtotal × rate | HALF_EVEN to cents; fits in long | long |
| Total | Subtotal + tax | Does not exceed long | long |

Some input examples:

| Unit price | Quantity | Tax | Expected |
| --- | --- | --- | --- |
| 19.99 | 3 | 0.075 | Valid: 59.97 + 4.50 = 64.47 |
| 0.05 | 1 | 0.1 | Tax 0.5 cents, HALF_EVEN → 0 cents |
| 0.15 | 1 | 0.1 | Tax 1.5 cents, HALF_EVEN → 2 cents |
| 1.000 | 1 | 0 | Rejected: format has 3 decimal places |
| -0.01 | 1 | 0 | Rejected: negative unit price |
| 1.00 | 0 | 0 | Rejected: quantity must be positive |
| 1.00 | 2147483648 | 0 | Rejected: exceeds int range |
| 92233720368547758.08 | 1 | 0 | Rejected: cents exceed Long.MAX_VALUE |

**Note:** The policy "at most two decimal digits in the **input string**" differs from "lossless numeric conversion to cents." Under the chosen policy, `1.000` is rejected even though it has the same numeric value as `1.00`. To allow extra trailing zeros, update the specification and corresponding tests.

## 3. Processing Flow: Validate First, Calculate Later

~~~text
raw price ----------> syntax check --------------> BigDecimal
                                                   |
                                                   v
                                      movePointRight(2)
                                                   |
                                                   v
                                          longValueExact()
                                                   |
                                                   v
                                              unitCents
                                                   |
raw quantity -------> syntax check -----------> BigInteger
                                                   |
                                                   v
                                             intValueExact()
                                                   |
                                                   v
                                               quantity
                                                   |
                        Math.multiplyExact(unitCents, quantity)
                                                   |
                                                   v
                                             subtotalCents
                                                   |
raw tax rate -------> check 0..1 --------------> BigDecimal
                                                   |
                        subtotal × tax rate (exact decimal)
                                                   |
                                  setScale(0, HALF_EVEN)
                                                   |
                                      longValueExact()
                                                   |
                                                   v
                                                taxCents
                                                   |
                                 Math.addExact(subtotal, tax)
                                                   |
                                                   v
                                               totalCents
~~~

We do not pass monetary inputs through `double`, because decimal numbers like 0.1 cannot be represented exactly in binary64. Additions/multiplications on `long` only happen once inputs have passed exact validation; whenever out of range, the program reports an error instead of producing a wrong value that still happens to be a valid `long`.

## 4. Complete Java 17 Source Code

Create the file **NumericBoundaryLab.java** with the following content. This is **a complete program**, including both business logic and test suite, requiring no JUnit, Maven, or external libraries.

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class NumericBoundaryLab {
    record Receipt(long subtotalCents, long taxCents, long totalCents) {}

    private static int passed;

    static long parsePriceCents(String raw) {
        if (raw == null || raw.length() > 40 ||
                !raw.matches("[0-9]+(?:\\.[0-9]{1,2})?")) {
            throw new IllegalArgumentException("Invalid price format");
        }
        return new BigDecimal(raw).movePointRight(2).longValueExact();
    }

    static int parseQuantity(String raw) {
        if (raw == null || raw.length() > 20 ||
                !raw.matches("[0-9]+")) {
            throw new IllegalArgumentException("Invalid quantity format");
        }
        int quantity = new BigInteger(raw).intValueExact();
        if (quantity < 1) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        return quantity;
    }

    static BigDecimal parseRate(String raw) {
        if (raw == null || raw.length() > 8 ||
                !raw.matches("(?:0(?:\\.[0-9]{1,4})?|1(?:\\.0{1,4})?)")) {
            throw new IllegalArgumentException(
                    "Rate must be 0..1 with <=4 decimals");
        }
        return new BigDecimal(raw);
    }

    static Receipt quote(String price, String quantity, String rate) {
        long unitCents = parsePriceCents(price);
        int units = parseQuantity(quantity);
        BigDecimal taxRate = parseRate(rate);

        long subtotal = Math.multiplyExact(unitCents, (long) units);
        long tax = BigDecimal.valueOf(subtotal)
                .multiply(taxRate)
                .setScale(0, RoundingMode.HALF_EVEN)
                .longValueExact();
        long total = Math.addExact(subtotal, tax);
        return new Receipt(subtotal, tax, total);
    }

    static int exactInt(double value) {
        if (!Double.isFinite(value) ||
                value < Integer.MIN_VALUE ||
                value > Integer.MAX_VALUE ||
                value != Math.rint(value)) {
            throw new IllegalArgumentException("Not an exact int");
        }
        return (int) value;
    }

    static String money(long cents) {
        return BigDecimal.valueOf(cents, 2).toPlainString();
    }

    static void same(Receipt receipt, long subtotal, long tax, long total) {
        if (receipt.subtotalCents() != subtotal ||
                receipt.taxCents() != tax || receipt.totalCents() != total) {
            throw new AssertionError("Unexpected receipt: " + receipt);
        }
    }

    static void check(String name, Runnable test) {
        try {
            test.run();
            passed++;
        } catch (RuntimeException | AssertionError ex) {
            throw new AssertionError("FAILED: " + name, ex);
        }
    }

    static void rejects(String name, Class<? extends RuntimeException> expected,
                        Runnable test) {
        check(name, () -> {
            try {
                test.run();
            } catch (RuntimeException actual) {
                if (expected.isInstance(actual)) return;
                throw new AssertionError("Wrong exception: " + actual);
            }
            throw new AssertionError("Expected " + expected.getSimpleName());
        });
    }

    public static void main(String[] args) {
        check("normal", () -> same(quote("19.99", "3", "0.075"), 5997, 450, 6447));
        check("zero price", () -> same(quote("0.00", "3", "0.075"), 0, 0, 0));
        check("HALF_EVEN even tie", () -> same(quote("0.05", "1", "0.1"), 5, 0, 5));
        check("HALF_EVEN odd tie", () -> same(quote("0.15", "1", "0.1"), 15, 2, 17));
        check("no tax", () -> same(quote("1.00", "2", "0"), 200, 0, 200));
        check("max cents", () -> same(quote("92233720368547758.07", "1", "0"),
                Long.MAX_VALUE, 0, Long.MAX_VALUE));
        check("int upper", () -> { if (exactInt(2147483647.0) != Integer.MAX_VALUE)
                throw new AssertionError(); });
        check("int lower", () -> { if (exactInt(-2147483648.0) != Integer.MIN_VALUE)
                throw new AssertionError(); });
        check("int normal", () -> { if (exactInt(42.0) != 42)
                throw new AssertionError(); });

        rejects("negative price", IllegalArgumentException.class,
                () -> quote("-0.01", "1", "0"));
        rejects("price too many decimals", IllegalArgumentException.class,
                () -> quote("1.000", "1", "0"));
        rejects("price exponent", IllegalArgumentException.class,
                () -> quote("1E3", "1", "0"));
        rejects("price comma", IllegalArgumentException.class,
                () -> quote("1,00", "1", "0"));
        rejects("price space", IllegalArgumentException.class,
                () -> quote(" 1.00", "1", "0"));
        rejects("price null", IllegalArgumentException.class,
                () -> quote(null, "1", "0"));
        rejects("quantity zero", IllegalArgumentException.class,
                () -> quote("1.00", "0", "0"));
        rejects("quantity negative", IllegalArgumentException.class,
                () -> quote("1.00", "-1", "0"));
        rejects("quantity decimal", IllegalArgumentException.class,
                () -> quote("1.00", "1.5", "0"));
        rejects("tax over one", IllegalArgumentException.class,
                () -> quote("1.00", "1", "1.01"));
        rejects("tax too many digits", IllegalArgumentException.class,
                () -> quote("1.00", "1", "0.12345"));
        rejects("tax negative", IllegalArgumentException.class,
                () -> quote("1.00", "1", "-0.1"));
        rejects("price cents overflow", ArithmeticException.class,
                () -> quote("92233720368547758.08", "1", "0"));
        rejects("quantity int overflow", ArithmeticException.class,
                () -> quote("1.00", "2147483648", "0"));
        rejects("subtotal long overflow", ArithmeticException.class,
                () -> quote("92233720368547758.07", "2", "0"));
        rejects("total long overflow", ArithmeticException.class,
                () -> quote("92233720368547758.07", "1", "1"));
        rejects("fractional double", IllegalArgumentException.class,
                () -> exactInt(12.9));
        rejects("NaN", IllegalArgumentException.class,
                () -> exactInt(Double.NaN));
        rejects("Infinity", IllegalArgumentException.class,
                () -> exactInt(Double.POSITIVE_INFINITY));
        rejects("double out of int range", IllegalArgumentException.class,
                () -> exactInt(2147483648.0));
        rejects("int addition overflow", ArithmeticException.class,
                () -> Math.addExact(Integer.MAX_VALUE, 1));

        Receipt demo = quote("19.99", "3", "0.075");
        System.out.println("subtotal=" + money(demo.subtotalCents()) +
                ", tax=" + money(demo.taxCents()) +
                ", total=" + money(demo.totalCents()));
        System.out.println("PASS " + passed + " boundary cases");
    }
}
~~~

**How to run:**

~~~bash
javac NumericBoundaryLab.java
java NumericBoundaryLab
~~~

**Output when the program passes all tests:**

~~~text
subtotal=59.97, tax=4.50, total=64.47
PASS 30 boundary cases
~~~

If a test returns the wrong result or a conversion fails to throw the expected exception, the `check` method throws an `AssertionError` containing the case name. The program stops with an error instead of printing the final PASS line.

The test suite uses plain Java, making it convenient for a directly runnable lesson. In a real project, each group can be moved to JUnit 5 and an automated pipeline; the assertion logic and boundary data still apply.

## 5. Explaining Each Layer of Protection

### 5.1. Syntax validation before parsing

`parsePriceCents` rejects null, strings longer than 40 characters, and strings not matching a non-negative ASCII decimal pattern with at most two digits after the dot. Reason for checking before `new BigDecimal(raw)`: BigDecimal accepts many mathematically valid syntaxes, such as exponents, that the illustrative application's contract **disallows**.

Inputs such as `1E3`, `1,00`, ` 1.00`, or `-0.00` are rejected under the chosen policy. Note that in terms of **numeric value**, `-0.00` may equal 0; forbidding the minus sign is a syntax decision, not a negative-number comparison.

Limiting length before parsing avoids ingesting unnecessarily long numeric strings in this problem. For applications with multilingual UIs, a strict ASCII pattern may be unsuitable; valid formats must be clearly published, such as how decimal and grouping separators are entered.

### 5.2. Converting decimal to cents without rounding

`new BigDecimal(raw).movePointRight(2).longValueExact()` performs two critical operations:

- `movePointRight(2)` multiplies the decimal value by 100 in exact decimal representation, without rounding.
- `longValueExact()` succeeds only if the value after multiplying by 100 is an integer within `long` range; otherwise it throws `ArithmeticException`.

Here **format** validity has already been checked separately. With an input unit price having at most two decimal places, the cents result is guaranteed to be an integer. Yet the **`long` range** check is still required because the string could contain a huge number.

The upper bound of `long` is 9223372036854775807 cents. Therefore, price `92233720368547758.07` with quantity 1 and tax 0 is still valid; `92233720368547758.08` exceeds by one cent and is rejected.

### 5.3. Never silently narrow quantity from BigInteger to int

`parseQuantity` parses the string via `BigInteger` and then calls `intValueExact()`. This allows distinguishing:

- `"0"`: valid syntax, **invalid business domain** because it must be greater than 0.
- `"-1"`: invalid syntax because minus signs are disallowed.
- `"1.5"`: invalid syntax because quantity must be an integer.
- `"2147483648"`: valid non-negative integer syntax, yet **exceeds `int` range**, causing `intValueExact()` to throw ArithmeticException.

Using `Integer.parseInt` can also reject numbers outside `int` range, though the message/error type differs. Using BigInteger clarifies two stages: understand the integer value first, then verify target type bounds.

### 5.4. Overflow-checked multiplication and addition

`Math.multiplyExact(unitCents, (long) units)` returns a `long` or throws ArithmeticException if the mathematical product exceeds `long` range. Casting quantity to `long` is done **before multiplication**; even though multiplying two `int`s could work when the result fits in `int`, you must never compute an overflowed `int` result and then assign it to `long`.

`Math.addExact(subtotal, tax)` is used after tax is calculated to prevent total overflow. For example, a unit price yielding exactly `Long.MAX_VALUE` cents and quantity 2 must be rejected at the multiplication step, rather than producing a negative result. A `Long.MAX_VALUE` cents value with quantity 1 and 100% tax rate is rejected at the addition step, because doubling exceeds `long`.

If business logic truly requires numbers larger than `long`, convert operands to `BigInteger` **before calculating**, instead of wrapping an already-overflowed `long` in `BigInteger`.

### 5.5. Computing tax in BigDecimal and rounding exactly once

Subtotal is already in integer cents. To compute tax in decimal, use:

~~~java
BigDecimal.valueOf(subtotal)
        .multiply(taxRate)
        .setScale(0, RoundingMode.HALF_EVEN)
        .longValueExact();
~~~

This snippet sits inside `quote`. `BigDecimal.valueOf(long)` constructs an exact decimal from `long`. Multiplying by the tax rate is also exact; only then do we round to **integer cents** using the specified rule. `HALF_EVEN` handles exact midpoints between two integers by choosing the even integer.

Two key boundary inputs:

- 5 cents × 10% = **0.5 cents** → rounded by HALF_EVEN to **0 cents** (0 is even).
- 15 cents × 10% = **1.5 cents** → becomes **2 cents** (2 is even).

If you change the rule to HALF_UP or DOWN, results at these boundary points can differ. Tests must align with the **actual policy**, not merely check whether the calculation runs.

An example with 7.5% tax on 5997 cents: 5997 × 0.075 = 449.775 cents, rounded HALF_EVEN to **450 cents**, i.e., 4.50. Total is 5997 + 450 = 6447 cents, i.e., 64.47.

### 5.6. Converting back to decimal only for display

`money(long cents)` uses:

~~~java
BigDecimal.valueOf(cents, 2).toPlainString()
~~~

This creates a decimal representation with scale 2 from integer cents. Hence 5997 cents becomes 59.97, 450 cents becomes 4.50, and 0 cents becomes 0.00. This string uses a decimal dot and no currency code, solely to illustrate display without losing cents.

If the system requires locale formatting or currency codes, handle that at the presentation layer with appropriate rules; do not parse formatted display strings back to perform core calculations.

## 6. Test Suite: Why Are Boundary Data Needed Instead of Only Typical Cases?

Only testing unit price 19.99 and quantity 3 cannot catch dangerous bugs such as overflow, parsers accepting malformed syntax, or wrong rounding at exact midpoints.

The 30 cases in the program are grouped as follows:

| Group | Key cases | What is verified |
| --- | --- | --- |
| Valid invoices | Normal, zero unit price, zero tax | Subtotal, tax, total computation |
| Rounding | 0.5 and 1.5 cents | Both branches of HALF_EVEN |
| Numeric range boundaries | Long.MAX_VALUE cents | In-range boundary value accepted |
| double → int conversion | 42, Integer.MIN_VALUE, Integer.MAX_VALUE | Finite integer values within range |
| Price format | Negative, 3 decimal places, exponent, comma, whitespace, null | Reject out-of-contract inputs |
| Quantity format | 0, negative, fractional | Reject out-of-domain or malformed inputs |
| Tax domain | >1, negative, >4 decimal places | Reject out-of-range/precision rates |
| Conversion overflow | Price cents exceeding long, quantity exceeding int | No silent data loss |
| Calculation overflow | subtotal/total exceeding long | Math.multiplyExact and Math.addExact |
| Floating-point | 12.9, NaN, infinity, out of int range | Validate before casting |
| int addition | Integer.MAX_VALUE + 1 | Math.addExact throws instead of wrapping |

Automatic case counting via `passed` helps detect when the program did not execute the expected number of tests. It does not replace a professional test runner, yet **actively fails fast** if any expectation is violated.

### Testing values on both sides of each boundary

For a range `[min, max]`, the dataset should include **min**, **max**, **just-inside values**, and **just-outside values**, if the source type can represent them.

Example for quantity:

| Input | Expected |
| --- | --- |
| "0" | Invalid because quantity must be >= 1 |
| "1" | Valid |
| "2147483647" | Valid int value, yet invoice total may still overflow |
| "2147483648" | Cannot convert exactly to int |
| "-1" | Invalid syntax |
| "1.0" | Invalid because rule accepts integer digits only |

An input with a valid quantity can still produce a total exceeding `long`, so validating each field individually **is not enough**; you must keep checking every operation producing derived data.

## 7. Identifying Error Types and Designing Messages

The illustrative program uses:

- `IllegalArgumentException` for inputs failing syntax or business domain rules, such as negative unit price or zero quantity.
- `ArithmeticException` thrown by `intValueExact`, `longValueExact`, or `Math.*Exact` when a value/result cannot be represented accurately.

Both must be caught and translated into appropriate messages at the API or UI layer. Never expose raw technical exceptions containing sensitive data directly to external callers in real applications.

`rejects(name, expectedType, runnable)` is a helper checking the **expected exception type**: if the operation does not throw or throws the wrong type, the case fails. This prevents writing flawed tests where "any exception counts as passing."

However, checking only exception type may be insufficient in large software. You can add specific business error codes and verify exact fields, error codes, and appropriate messages; avoid locking tests to entire stack traces since those change during refactoring.

## 8. Distinguishing Type-Conversion Tests from Money Handling

The `exactInt(double)` method in the program is a standalone check reusing knowledge about **potentially lossy casts**:

~~~java
static int exactInt(double value) {
    if (!Double.isFinite(value) ||
            value < Integer.MIN_VALUE ||
            value > Integer.MAX_VALUE ||
            value != Math.rint(value)) {
        throw new IllegalArgumentException("Not an exact int");
    }
    return (int) value;
}
~~~

It rejects NaN, infinity, numbers outside `int` range, and numbers with fractional parts. Only after passing all conditions does it cast.

Why not check after casting?

~~~java
int wrongA = (int) 12.9;        // 12: fractional part lost
int wrongB = (int) Double.NaN;  // 0: NaN origin lost
~~~

Both `12` and `0` are valid `int` values, yet do not prove the source was the corresponding integer. Even assigning that result to `long` afterward cannot recover the original input.

If decimal data must be exact right from user input, never route it through `double` before this step. Use `BigDecimal` from a string and `intValueExact()`.

## 9. Stronger Test Suites: Controlled Expansion Ideas

The current 30-case suite proves key branches, yet **does not mean every possible input is covered**. Appropriate expansion directions:

### 9.1. Parameterized tests

Instead of repeating statements per price, create a data table containing input, expected error type/result, and iterate over each row. When moving to JUnit 5, organize parameterized tests with `@ParameterizedTest` and matching data sources.

### 9.2. Property-based tests

For instance, for any valid unit price, positive quantity, and 0 tax rate:

- `subtotal == total` when calculation fits in `long`.
- `tax == 0`.
- `subtotal >= 0` per input domain.
- Result in cents must be an integer `long`, with no fractional cents.

With tax rates from 0 to 1 and non-negative subtotal, rounded tax is non-negative; total is non-negative if there is no overflow. These properties are more general than a few concrete numbers, while noting you must **exclude or expect exceptions on overflowing calculations**.

### 9.3. Structural input tests

Try null, empty string, Unicode digits if the contract allows ASCII only, multiple dots, plus signs, minus signs, thousands separators, exponents, leading/trailing whitespace, and extremely long strings. A parser may accept more than the contract permits, so merely succeeding in constructing a `BigDecimal` does not prove input validity.

### 9.4. Rounding boundary tests

Besides 0.5 and 1.5 cents, examine values just below, right at, and just above midpoints, along with cases having even/odd retained digits. Separately test rounding timing: **each invoice line before summing** differs from **summing lines then rounding the total**. Never change policies without updating tests.

### 9.5. Performance and resource tests

Measure how the system handles multi-line lists; limit input sizes before parsing `BigInteger`/`BigDecimal` to prevent CPU/memory abuse. Performance tests need a stable environment and should not be mixed directly into correctness suites with fixed stdout.

## 10. Common Mistakes Prevented by This Example

**Mistake 1 — Using double for money and comparing with ==.** Decimals like 0.1 are not represented exactly in binary64. The example stores `long` cents and computes rates with `BigDecimal`.

**Mistake 2 — Converting decimal numbers to int/long via cast or intValue().** Can truncate fractional parts or overflow. The code uses `longValueExact` and `intValueExact`.

**Mistake 3 — Assigning an already-overflowed calculation to a wider type.** `long x = intA * intB` can still overflow `int` before assignment. The code uses `long` arithmetic and `Math.multiplyExact`.

**Mistake 4 — Believing valid individual fields guarantee a valid total.** A unit price of `Long.MAX_VALUE` cents and quantity 2 overflows in subtotal. Every derived calculation also needs protection.

**Mistake 5 — Rounding uncontrollably at multiple steps.** Policy and rounding timing must be chosen explicitly. Here only tax is rounded to cents once using HALF_EVEN.

**Mistake 6 — Ignoring half-step boundaries.** Testing 0.5/1.5 cents distinguishes HALF_EVEN from other modes.

**Mistake 7 — Equating "parseable" with "permitted input."** BigDecimal accepts many number notations; apps may forbid exponents, minus signs, commas, or whitespace.

**Mistake 8 — Catching all exceptions and returning 0 money.** Invalid data is not zero. Reject controllably instead of turning errors into valid transactions.

**Mistake 9 — Writing only happy paths.** The test suite needs valid values at the boundary and just outside the boundary, NaN/Infinity, overflow, null inputs, and bad quantities.

**Mistake 10 — Editing code and only looking at final stdout.** Tests should assert subtotal, tax, and total independently. An accidentally matching total does not guarantee components are right.

## 11. Self-Practice Exercises

1. **Changing price policy:** Allow the string `"1.000"` when its numeric value converts to cents without loss. Update the parser and tests; distinguish syntax conditions from value conditions.
2. **Business cap:** Set maximum quantity to 10,000 instead of `Integer.MAX_VALUE`; add tests where 10,000 is valid and 10,001 is rejected.
3. **Configurable rounding:** Pass `RoundingMode` into `quote` while permitting only business-approved modes. Demonstrate a 0.5-cent case changing results when the mode changes.
4. **Multi-line calculation:** Write a function summing multiple `Receipt`s with `Math.addExact`, explicitly choosing whether tax rounds per line or on the total.
5. **Error classification:** Create distinct error codes for syntax, value domain, `long` overflow, and disallowed rounding; write tests verifying each kind.
6. **Reproducible randomness:** Generate supplementary test data using a `Random` with a fixed seed while keeping handwritten boundary cases. Random data does not replace known counterexamples.
7. **Storage and display:** Test locale-aware currency formatting in the UI while keeping integer cents for computation; avoid parsing formatted strings back.

### Solution sketch for multi-line calculation

Suppose three `Receipt` objects have been calculated, and the policy is **tax rounded per line**, then the totals are:

~~~java
long subtotal = 0L;
long tax = 0L;
for (NumericBoundaryLab.Receipt r : receipts) {
    subtotal = Math.addExact(subtotal, r.subtotalCents());
    tax = Math.addExact(tax, r.taxCents());
}
long total = Math.addExact(subtotal, tax);
~~~

This is an **illustrative code snippet**, requiring the `receipts` variable to be declared in the same package/context with access to the record, and following the per-line tax-rounding policy. If business rules mandate calculating tax only on the whole invoice total, both algorithm and tests will differ. Never assume the two approaches always yield the same result.

## 12. Checklist When Finalizing the Integrated Example

- Are **input syntax**, **business domain**, **units**, and **storage types** clearly defined?
- Are source values preserved accurately until all checks finish?
- Do narrowing conversions use **Exact** methods or range/fractional checks?
- Do calculations use `Math.*Exact` where integer types can overflow?
- Is **permitted rounding** clearly distinguished from **disallowed data loss**?
- Have you tested right at and just outside min/max values, as well as rounding midpoints?
- Have you tested null, invalid strings, and NaN/Infinity when inputs are floating-point?
- Do tests genuinely fail if values or exception types are wrong?
- Do tests compile and run via `javac`/`java` on JDK 17 with deterministic output?
- If upgrading to a production application, have resource limits, real tax/currency rules, API errors, and system observability been considered?

**Conclusion:** A sound numeric example is more than a money formula. It also encompasses an **input contract**, **exact conversion**, **overflow detection**, **transparent rounding**, **appropriate data types**, and **a runnable boundary-data test suite**. The program above demonstrates that entire chain on a small problem, from raw strings through integer cents and 30 automated verification cases.
