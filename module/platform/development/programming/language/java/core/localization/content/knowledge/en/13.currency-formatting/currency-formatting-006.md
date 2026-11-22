# Separating BigDecimal Value, Currency Code, and Rounding Policy in Java

When handling money in a Java application, a value like `12.345 USD` actually contains **three independent pieces of information**:

1. **Numeric value:** the monetary amount represented accurately, typically using `BigDecimal`.
2. **Currency unit:** the currency code, typically using `java.util.Currency` with ISO 4217 codes such as `USD`, `VND`, `JPY`, `KWD`.
3. **Rounding policy:** when to round, to how many decimal places or what monetary increment, using `RoundingMode` and the appropriate business rule.

These three dimensions **are not interchangeable**. `BigDecimal` alone does not know whether the unit is US dollars or Vietnamese dong. `Currency` performs no rounding. `RoundingMode` does not by itself decide the number of digits, the rounding boundary, or applicable tax rules. A safe financial system must model all three while distinguishing **computational amounts**, **settled/payable amounts**, and **locale-formatted display strings**.

## 1. Why separate these three components?

Consider two cases:

~~~text
Invoice A: 12.345 USD
Invoice B: 12.345 KWD
~~~

The same value `12.345` has different default fraction digits for `USD` and `KWD` according to the currency data Java provides. Whether to round or keep the precision must depend on **the calculation rule and intended use**, not merely on the number of digits visible to the user.

Similarly:

~~~text
10.00 USD + 5.00 USD → valid addition
10.00 USD + 5.00 VND → cannot add directly as the same unit
~~~

Converting from USD to VND requires **an exchange rate, timestamp, rate source, and conversion/rounding policy**. `Currency` holds no exchange rate, and `BigDecimal` does not convert currencies on its own.

| Component | Primary Java API | Question it answers | What it is not responsible for |
| --- | --- | --- | --- |
| Numeric value | `BigDecimal` | How many units are there, and what is the arithmetic result? | Does not determine currency or settlement rules |
| Currency code | `Currency` | Which currency does the number belong to? | Does not convert currencies, does not round on its own |
| Rounding rule | `RoundingMode`, `setScale`, mode-aware division | How many digits to keep and which direction to pick? | Does not determine exchange rates, taxes, or rounding milestones |
| Display formatting | `NumberFormat` / `DecimalFormat` + `Locale` | How should the amount be displayed to a reader? | Does not alter the underlying amount when used solely for formatting |

Core principle: **a meaningful monetary value must be paired with its currency unit**, and rounding rules must be specified at the proper business boundaries.

## 2. BigDecimal: exact decimal representation

`java.math.BigDecimal` represents a decimal value using an arbitrary-precision integer unscaled value and a `scale` (the number of digits to the right of the decimal point in the representation). Mathematically, the value is `unscaledValue × 10^(-scale)`.

Example:

~~~java
BigDecimal a = new BigDecimal("12.345");
BigDecimal b = new BigDecimal("0.015");

BigDecimal sum = a.add(b); // 12.360
~~~

In a program that imports `java.math.BigDecimal`, the sum has an exact arithmetic value. The result preserves scale according to addition rules, yet still carries no `USD` or `VND` information.

### Do not use double to construct human-entered monetary amounts

Example:

~~~java
BigDecimal safe = new BigDecimal("0.1");  // exact 0.1
BigDecimal exactBinary = new BigDecimal(0.1);
~~~

`new BigDecimal(0.1)` takes **the exact binary value stored by double**, which is not equal to 0.1 in base 10; thus the resulting BigDecimal has many digits. Common construction paths:

- `new BigDecimal("0.1")`: uses a validated decimal string.
- `BigDecimal.valueOf(0.1)`: uses the canonical string representation of `double`, generally better than the `double` constructor directly, but **cannot recover any precision already lost beforehand**.
- `BigDecimal.valueOf(12345, 2)`: constructs `123.45` from an integer unscaled value and a specified scale; suitable when a protocol sends minor units according to an **agreed scale**.

Example using integer minor units:

~~~java
BigDecimal amount = BigDecimal.valueOf(12345, 2); // 123.45
~~~

However, do not assume `2` is a fixed scale for **every currency**. A protocol may transmit an integer amount in minor units, yet the divisor must be specified by the communication contract per currency or per API version; `Currency.getDefaultFractionDigits()` does not replace an API specification.

### Scale and precision are two different concepts

| Concept | Example | Meaning |
| --- | --- | --- |
| `scale()` | `new BigDecimal("12.340").scale() == 3` | Three digits after the decimal point in the representation |
| `precision()` | `new BigDecimal("12.340").precision() == 5` | Five significant digits in the decimal coefficient |
| Numeric value | `12.34` and `12.340` | Equal according to `compareTo`, despite different scales |
| `MathContext` | `new MathContext(5, HALF_EVEN)` | Controls **precision** of operations, not a policy of always keeping 2 decimal places |

`setScale(2, RoundingMode.HALF_EVEN)` specifies the number of fractional digits. `round(new MathContext(5, ...))` limits the number of significant digits. For money, these two operations serve different purposes and must not be substituted mechanically.

## 3. Currency: currency codes and currency metadata

`java.util.Currency` represents a currency unit recognized by the JDK.

~~~java
import java.util.Currency;

Currency usd = Currency.getInstance("USD");
Currency vnd = Currency.getInstance("VND");
Currency jpy = Currency.getInstance("JPY");
Currency kwd = Currency.getInstance("KWD");

System.out.println(usd.getCurrencyCode());         // USD
System.out.println(usd.getDefaultFractionDigits()); // 2
System.out.println(vnd.getDefaultFractionDigits()); // 0
System.out.println(jpy.getDefaultFractionDigits()); // 0
System.out.println(kwd.getDefaultFractionDigits()); // 3
~~~

The snippet above illustrates typical results from the JDK's currency data; codes and data may be updated across versions and runtimes. When a product relies on time-effective currency metadata, check the data version and corresponding legal/business policies.

`Currency.getInstance(code)` expects a **currency code**, not a formatted monetary string. For an invalid or unsupported code, it may throw `IllegalArgumentException`; `null` throws `NullPointerException`. For input from users or APIs, validate and handle errors rather than accepting an arbitrary bad code.

### getDefaultFractionDigits() is only metadata

`Currency.getDefaultFractionDigits()` returns the default number of fraction digits defined in the JDK's currency data; the API may return `-1` when a standard number of fraction digits does not apply or is undefined.

**Do not equate this number with the mandatory rounding policy for every business operation.**

- A tax calculation in USD may require more than 2 intermediate decimal places.
- A settlement in VND is typically finalized to whole dong, yet prior calculations may involve fractional parts.
- A cash flow may need to round to a **specific value increment**, not just choose a number of decimal places. For instance, rounding to multiples of `0.05` is not equivalent to `setScale(2, mode)`.
- Accounting methods, payment gateway policies, and legal regulations may differ; confirm them rather than inferring from `Currency`.

`Currency.getSymbol(locale)` and `getDisplayName(locale)` are for **presentation**, not storage identifiers. The `$` symbol can refer to multiple currencies; codes `USD` and `CAD` are distinct.

### Currency code is not locale

`Locale.forLanguageTag("en-US")` is a language/region context. `Currency.getInstance("USD")` is a currency unit. A user viewing a Vietnamese interface may view values denominated in USD, JPY, or EUR.

Do not infer currency solely from locale when the user or transaction contract already specifies a currency code. `Currency.getInstance(locale)` can be useful for obtaining the default currency associated with a matching region, yet it **does not prove which currency is used for a specific transaction**.

## 4. RoundingMode: specifying behavior, not just a result

Given the number `2.345` to round to 2 decimal places:

~~~java
BigDecimal value = new BigDecimal("2.345");

value.setScale(2, RoundingMode.HALF_UP);   // 2.35
value.setScale(2, RoundingMode.HALF_EVEN); // 2.34
~~~

This is an illustrative snippet inside a method that imports `java.math.BigDecimal` and `java.math.RoundingMode`. Both differing results **can be valid** depending on the contract. An application must not arbitrarily change modes just to make numbers look “nicer.”

### Modes to understand

| RoundingMode | Basic meaning | Notes |
| --- | --- | --- |
| `UP` | Increases magnitude, away from 0 if digits must be discarded | Not the same as `CEILING` for negative numbers |
| `DOWN` | Decreases magnitude, toward 0 | Not the same as `FLOOR` for negative numbers |
| `CEILING` | Toward (+∞) | For negative numbers, may move closer to 0 |
| `FLOOR` | Toward (-∞) | For negative numbers, may move farther from 0 |
| `HALF_UP` | Nearest neighbor; if equidistant, away from 0 | Common, though not automatically a legal standard |
| `HALF_DOWN` | Nearest neighbor; if equidistant, toward 0 | Check tie examples carefully |
| `HALF_EVEN` | Nearest neighbor; at midpoint, chooses even kept last digit | Commonly called “banker's rounding” |
| `UNNECESSARY` | Rejects any case that requires rounding | Throws `ArithmeticException` if precision would be lost |

Rounding negative numbers must be tested separately: `RoundingMode.CEILING` does not mean “always increase absolute value,” it means toward (+∞). Likewise, `HALF_UP` is not simply adding `0.5` and truncating for all numbers and scales.

Another midpoint example: `new BigDecimal("2.355").setScale(2, HALF_EVEN)` becomes `2.36` because the hundredths digit `6` is even. Do not interpret `HALF_EVEN` as “always rounds down”; at a tie, it picks the side whose kept digit is even.

### Avoid implicit rounding

You may allow amounts to retain high scale during intermediate calculations, and round only at designated boundaries such as **finalizing an order**, **recording the payable amount**, **computing line-item tax**, or **generating reports**.

A flawed design is having every `add`, `multiply`, `divide`, or `Money` constructor automatically apply `setScale(currency.getDefaultFractionDigits(), HALF_UP)` without a business reason. That discards intermediate precision and can yield different totals when operation order changes.

## 5. Rounding policies also include timing and rounding increment

A useful `RoundingPolicy` must describe more than `RoundingMode`:

- **Which calculation:** tax, fee, discount, payment total, currency conversion, interest.
- **When to round:** per line item, per unit, per tax category, or on the total.
- **Increment/step:** `scale=2`, `scale=0`, or multiples of `0.05` depending on context.
- **Mode:** `HALF_UP`, `HALF_EVEN`, `DOWN`, etc.
- **Handling refunds, negative amounts, and remainders:** must align with business requirements.
- **Legal or contractual specifications:** where applicable, must be reviewed by the business owner.

Two rounding approaches can both be “correct according to the mode,” yet produce different totals because **the rounding timing differs**:

~~~text
Value 1: 0.005 USD
Value 2: 0.005 USD

Round each value with HALF_UP, scale 2:
0.005 → 0.01
0.005 → 0.01
Total: 0.02 USD

Add first, then round with HALF_UP, scale 2:
0.005 + 0.005 = 0.010
Rounded total: 0.01 USD
~~~

The difference is not a `BigDecimal` bug; it is a consequence of policy. You must explicitly specify whether business calculations round per line or on the total, especially for taxes, discounts, and splitting bills among multiple people.

### Step-based rounding is not just setScale

If a cash policy requires a `0.05` increment, `setScale(2, ...)` alone still permits `10.01` or `10.02`—it **does not enforce multiples of 0.05**.

A conceptual representation:

~~~text
amount / 0.05 → round number of step units → multiply back by 0.05
~~~

This is only a process description; an actual implementation must use `BigDecimal` and confirm rules for negative numbers, ties, when the rule applies, the step size, and what results must be preserved. Do not apply cash rounding increments to bank transfers simply because the transactions share the same currency code.

## 6. Building a Money value object with Java 17

One way to enforce invariants is to wrap `BigDecimal` and `Currency` in an immutable type and have the settlement operation accept an **explicit rounding rule**. Java 17 supports `record`, which suits illustrating this model.

Create the file **`MoneyDimensionsDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Objects;

public class MoneyDimensionsDemo {
    record Money(BigDecimal amount, Currency currency) {
        Money {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");
        }

        Money add(Money other) {
            Objects.requireNonNull(other, "other");
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("Currency mismatch");
            }
            return new Money(amount.add(other.amount), currency);
        }

        Money rounded(int scale, RoundingMode mode) {
            return new Money(amount.setScale(scale, mode), currency);
        }

        String displayRaw() {
            return currency.getCurrencyCode() + " " + amount.toPlainString();
        }
    }

    public static void main(String[] args) {
        Currency usd = Currency.getInstance("USD");
        Currency vnd = Currency.getInstance("VND");
        Currency kwd = Currency.getInstance("KWD");

        System.out.println("Digits USD="
                + usd.getDefaultFractionDigits()
                + ", VND=" + vnd.getDefaultFractionDigits()
                + ", KWD=" + kwd.getDefaultFractionDigits());

        Money a = new Money(new BigDecimal("12.345"), usd);
        Money b = new Money(new BigDecimal("0.015"), usd);

        System.out.println("Exact sum: " + a.add(b).displayRaw());
        System.out.println("Settled sum: " + a.add(b)
                .rounded(2, RoundingMode.HALF_EVEN).displayRaw());

        BigDecimal tie = new BigDecimal("2.345");
        System.out.println("HALF_UP: "
                + tie.setScale(2, RoundingMode.HALF_UP));
        System.out.println("HALF_EVEN: "
                + tie.setScale(2, RoundingMode.HALF_EVEN));

        System.out.println("One third: "
                + BigDecimal.ONE.divide(
                        new BigDecimal("3"),
                        2,
                        RoundingMode.HALF_UP));

        try {
            a.add(new Money(new BigDecimal("100"), vnd));
        } catch (IllegalArgumentException ex) {
            System.out.println("Mismatch: " + ex.getMessage());
        }

        try {
            tie.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("Precision loss: rejected");
        }

        System.out.println("String construction: "
                + new BigDecimal("0.1").toPlainString());
        System.out.println("Double construction exact 0.1: "
                + (new BigDecimal(0.1)
                        .compareTo(new BigDecimal("0.1")) == 0));
    }
}
~~~

Compile/run (Java 17 or later):

~~~bash
javac -encoding UTF-8 MoneyDimensionsDemo.java
java MoneyDimensionsDemo
~~~

Stdout verified against the JDK:

~~~text
Digits USD=2, VND=0, KWD=3
Exact sum: USD 12.360
Settled sum: USD 12.36
HALF_UP: 2.35
HALF_EVEN: 2.34
One third: 0.33
Mismatch: Currency mismatch
Precision loss: rejected
String construction: 0.1
Double construction exact 0.1: false
~~~

**Explanation:**

1. `Currency` holds the currency code and default fraction-digits metadata; the three codes in the example report `2`, `0`, and `3` respectively.
2. The two USD amounts are added **exactly**: `12.345 + 0.015 = 12.360`. Addition does not drop fractional digits automatically.
3. `rounded(2, HALF_EVEN)` returns a **new Money** with amount `12.36`; the original instance is unchanged. Choosing `2` here is the example's settlement policy, not something to infer automatically for every calculation.
4. `2.345` sits halfway between `2.34` and `2.35`; `HALF_UP` picks `2.35`, while `HALF_EVEN` picks `2.34`.
5. Dividing `1/3` highlights a point requiring a mode/scale decision: `divide(..., 2, HALF_UP)` returns `0.33`.
6. Adding USD and VND is rejected, preventing silent mixing of units.
7. `UNNECESSARY` throws an error if setting the scale would require discarding significant digits.
8. `new BigDecimal("0.1")` preserves the exact decimal 0.1; `new BigDecimal(0.1)` reflects binary approximation and is not equal to exact 0.1.

`displayRaw()` intentionally prints a stable machine-readable format `USD 12.36` for easy testing; this is **not** a localized UI format. The currency code and amount are stored separately in the record, while rounding rules are passed in when needed.

**Limitations of this example:** the record does not replace a production money library. It does not store per-operation policies, nor does it solve exchange rates, banking rules, fees, cash rounding, currency metadata history, maximum bounds, or remainder allocation. Its purpose is to clearly demonstrate the three independent responsibilities.

## 7. Arithmetic: preserve precision until the allowed rounding boundary

### Addition and subtraction

Use `add`/`subtract` for two amounts with the same currency code. When using a Money wrapper, enforce a currency check on addition and subtraction.

~~~java
BigDecimal subtotal = new BigDecimal("10.005")
        .add(new BigDecimal("1.005")); // 11.010
~~~

The snippet above has not rounded or applied a currency settlement policy; it is valid when the business retains three intermediate decimal places.

### Multiplying unit price by quantity or rate

~~~java
BigDecimal unitPrice = new BigDecimal("1.235");
BigDecimal quantity = new BigDecimal("3");
BigDecimal exactLine = unitPrice.multiply(quantity); // 3.705
~~~

If the business requires `scale=2`, you must specify whether to round `unitPrice` before multiplying or `exactLine` after multiplying. The two approaches can yield different results, so a consistent business rule and test cases are required.

### Division

Some decimal divisions do not have a terminating representation. For example:

~~~java
BigDecimal.ONE.divide(new BigDecimal("3"));
~~~

can throw `ArithmeticException` because `1/3` is a non-terminating decimal and cannot be represented exactly as a finite `BigDecimal`. You must specify precision/scale and a rounding mode when the business permits rounding:

~~~java
BigDecimal third = BigDecimal.ONE.divide(
        new BigDecimal("3"), 4, RoundingMode.HALF_EVEN);
// 0.3333
~~~

Do not catch every `ArithmeticException` and substitute 0. Non-terminating division, division by zero, and `UNNECESSARY` failures represent distinct scenarios; error handling must match the cause.

### Splitting an amount into multiple parts

If you split `10.00 USD` among three people, an exact finite division in cents does not exist (`10.00 / 3`). Rounding each share to `3.33` for all three yields only `9.99`. You need an auditable **remainder allocation** policy—for example, two shares receive `3.33` and the final share receives `3.34`, so the sum equals exactly `10.00`.

This is a clear illustration: `BigDecimal` guarantees exact arithmetic for the requested operation, but **does not define fairness or monetary allocation on its own**.

## 8. BigDecimal.equals() and compareTo() are not equivalent

Two amounts can have equal numeric values while differing in scale:

~~~java
BigDecimal x = new BigDecimal("12.30");
BigDecimal y = new BigDecimal("12.300");

x.compareTo(y) == 0; // true: same numeric value
x.equals(y);         // false: different scale
~~~

This matters when using `BigDecimal` as a `Map` key, a `Set` element, or a component of `record Money`: a record's default `equals` delegates to the `equals` of its components, so `Money(12.30, USD)` and `Money(12.300, USD)` are not necessarily equal under `equals`.

Reasonable solutions depending on the business domain:

- Normalize scale at **persistence/transmission boundaries** if the contract requires a unique representation.
- Compare numeric values with `compareTo` when asking only about arithmetic equality, while ensuring currencies match.
- Preserve input scale when that information is meaningful, such as declared precision.
- Be cautious with `stripTrailingZeros()`: it can produce a negative scale, for instance representing `1000` in scientific form. Do not apply it blindly to every monetary record.

Never let an implicit comparison rule treat valid equal amounts as different or vice versa.

## 9. Display formatting is separate from stored monetary amounts

When the UI needs to print an amount by region, use `NumberFormat` or `DecimalFormat` with `Locale`, while explicitly specifying the **transaction's `Currency`** instead of assuming the locale's default currency is always right:

~~~java
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;

NumberFormat formatter = NumberFormat.getCurrencyInstance(
        Locale.forLanguageTag("vi-VN"));
formatter.setCurrency(Currency.getInstance("USD"));
String ui = formatter.format(new java.math.BigDecimal("1234.50"));
~~~

This is an **illustrative snippet**, not a standalone program; exact output depends on localization/JDK data and formatter configuration. When using `setCurrency`, note carefully that the `NumberFormat` API **is not required to adjust the number of fraction digits automatically to the new currency**. If an application needs consistent policy-driven display, configure the appropriate fraction-digit properties and test them.

Important: **formatting an amount does not mean settling that amount**. A formatter may round a value for display while the underlying amount retains more digits. Never use a formatted UI string as the source of truth for summing totals or posting to a ledger.

### Do not confuse currency symbols with currency codes

Symbols such as `$`, `¥`, and `kr` can belong to multiple currency units or render differently across locales. When transmitting data across systems or auditing, keep codes like `USD`, `VND`, `JPY`, or an agreed currency identifier. Generate symbols only in the presentation layer.

### Locale and exchange rates are independent concerns

An amount of `100 USD` displayed to a user in Vietnam does not automatically convert to VND. Converting currencies requires a published exchange rate:

~~~text
convertedAmount = sourceAmount × exchangeRate
~~~

You must specify the source currency, target currency, rate, rate direction, timestamp/source, and rounding policy. `Currency` has no method to convert between USD and VND.

## 10. Persistence, APIs, and data exchange contracts

An easily auditable data design separates the fields:

~~~json
{
  "amount": "1234.50",
  "currency": "USD"
}
~~~

Here `amount` is a canonical decimal string specified by the API and `currency` is the currency code. Using a string prevents clients or intermediate libraries from converting the value into floating-point types with insufficient precision for the business. This is **one API design choice**, not a claim that every protocol must use strings.

If an API uses integer minor units:

~~~json
{
  "minorUnits": 123450,
  "currency": "USD",
  "scale": 2
}
~~~

then the amount is `1234.50 USD` under the contract `minorUnits × 10^(-scale)`. Never rely solely on the field name `minorUnits` and guess a scale of 2 for every currency. Even for the same currency, some payment systems have specialized scale rules by API version or channel; follow that system's documentation.

### Databases

Typical columns are `DECIMAL/NUMERIC` for the amount and `CHAR(3)` or `VARCHAR(3)` for the ISO currency code (depending on the DBMS). Avoid `FLOAT/DOUBLE` for monetary amounts requiring decimal precision.

Conceptual schema example:

~~~sql
CREATE TABLE invoice_amount (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(20, 6) NOT NULL,
    currency_code CHAR(3) NOT NULL
);
~~~

This is an **SQL illustration**; syntax, data types, and limits vary by database. `DECIMAL(20,6)` means 20 total precision digits and a scale of 6—**not a monetary settlement policy**. Design precision/scale based on maximum values, intermediate quantities, and product constraints. Do not let the database silently round or truncate values when the application has not defined that behavior.

When posting money to a ledger or emitting payment events, store the policy or calculation version needed for future reconciliation—especially for taxes, currency conversions, or transactions refunded years later.

## 11. Monetary validation and rounding policies

A production-ready `Money` model should consider:

- `amount` and `currency` are non-`null`.
- The currency code is in the system's valid/accepted list, not merely syntactically valid.
- Digit limits and value bounds align with the database, APIs, and payment providers.
- Allowing or forbidding negative amounts by **operation type**—do not ban all negatives because refunds and adjustments can be negative.
- Whether `amount=0` is allowed, per specification.
- Pre-rounding versus settled states, avoiding automatic rounding on every operation.
- Ensuring additions/subtractions do not mix currencies; conversions must use an explicit rate.
- Centralizing rounding logic at a single business boundary and testing it thoroughly.
- Documenting scale/step/mode in communication contracts, including version changes if any.
- Ensuring settled values do not exceed limits accepted by downstream systems.

If a system handles only USD, a simple policy may suffice; when expanding to JPY, VND, KWD, or cash payments, never assume the existing USD policy still holds.

## 12. Common pitfalls

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| `new BigDecimal(0.1)` for user-entered prices | Receives the exact double approximation, not decimal 0.1 | Construct from decimal strings or agreed integer + scale |
| Storing only amount and omitting currency | Unknown whether USD or VND | Always store the currency code alongside the value |
| Using currency symbol as an identifier | `$` does not distinguish multiple currencies | Use ISO 4217 codes |
| Adding USD and VND | Sum has invalid units | Reject or convert transparently first |
| Using `getDefaultFractionDigits()` as the rounding rule for every calculation | Loses needed fractional precision, can miscalculate tax/fees | Separate metadata from business policy |
| Rounding every intermediate step using defaults | Totals depend on processing order | Define exact rounding boundaries |
| Confusing precision with scale | Incorrect level of preserved accuracy | Use `MathContext` and `setScale` for their intended purposes |
| Calling `divide` without a mode on non-terminating division | `ArithmeticException` | Choose business scale/precision and rounding mode |
| Using `equals` to compare `BigDecimal` numeric values | `12.30` differs from `12.300` | Check currency and use `compareTo` for numeric comparison |
| Treating a rounded UI format as the official amount | Incorrect settlement or loss of audit trail | Keep the original value and a separate settlement step |
| Ignoring negative numbers | Bugs with refunds, `CEILING`/`FLOOR` | Test negative numbers and refund rules |
| Assuming `scale=2` means cash rounding to 0.05 | Can yield 10.02, not a multiple of 0.05 | Use a step-based rounding policy |
| Using `double` for money in JSON/DB | Loss of decimal precision in some systems | Decimal string / minor-units contract, `DECIMAL` column |
| Inferring transaction currency from locale | Picks the wrong unit for the transaction | Currency is independent business data |
| Omitting policy version | Hard to reproduce amounts on historical invoices | Record necessary calculation rules and history |

## 13. Testing precision-sensitive cases

A strong test matrix should cover **values**, **currency**, **scale**, **mode**, and **rounding timing**, not just `1.23`:

| Input / scenario | Expectation or assertion |
| --- | --- |
| `2.345` → scale 2, `HALF_UP` | `2.35` |
| `2.345` → scale 2, `HALF_EVEN` | `2.34` |
| `2.355` → scale 2, `HALF_EVEN` | `2.36` |
| `-2.345` → scale 2, `HALF_UP` | `-2.35` |
| `-2.345` → scale 2, `HALF_EVEN` | `-2.34` |
| `1 / 3` → scale 2, `HALF_UP` | `0.33` |
| `1 / 3` → exact division without mode | May throw `ArithmeticException` |
| `12.30` vs `12.300` | `compareTo==0`, `equals==false` |
| `12.345 USD + 0.015 USD` | `12.360 USD` before rounding |
| `USD + VND` | Rejected |
| `0.005 + 0.005`, line-item rounding vs total rounding | `0.02` vs `0.01` under HALF_UP scale 2 |
| `VND`, `JPY`, `KWD` | Verify currency-specific policy, do not assume scale 2 |
| `1000.00` with small DB bounds | Verify bounds and write behavior without truncation |
| Increment `0.05` | Every settled number must be an exact multiple of `0.05` |
| Sum of allocation among three people | Sum of parts must equal the original amount |
| Format with another `Locale` | Underlying amount/currency remains unchanged |

Useful property-based tests: addition does not alter the currency code; amounts do not change when merely formatted; settling a second time with the same scale/mode leaves settled amounts unchanged; the sum of allocated parts matches the original total; every transaction crossing API/DB boundaries preserves exact numeric value and currency.

If rounding rules are governed by legal regulations or payment-network standards, obtain test cases confirmed by the business owner; Java knowledge alone cannot substitute for an official specification.

## 14. Self-assessment exercises

**Question 1.** Why is using `BigDecimal` alone insufficient to represent money?

**Answer:** `BigDecimal` only holds a numeric value; it has no knowledge of currency code, rounding timing, monetary increments, exchange rates, or business policies.

**Question 2.** `Currency.getDefaultFractionDigits()` returns `0` for VND. Must every calculation in VND immediately truncate to whole integers?

**Answer:** No. That is default fraction-digit metadata. Tax or discount calculations may retain intermediate fractional precision; transaction settlement and rounding depend on business rules.

**Question 3.** Does rounding `new BigDecimal("2.345")` to scale 2 with `HALF_EVEN` and `HALF_UP` give the same result?

**Answer:** No. `HALF_EVEN` returns `2.34`; `HALF_UP` returns `2.35`.

**Question 4.** Why can `new BigDecimal("1").divide(new BigDecimal("3"))` throw an error?

**Answer:** `1/3` has a non-terminating decimal expansion and cannot be stored exactly as a finite `BigDecimal` without specifying scale/precision and a rounding mode.

**Question 5.** When a user opens the UI in the `vi-VN` locale, does an invoice amount automatically convert from USD to VND?

**Answer:** No. Locale only affects display/formatting context; converting currencies requires an exchange rate and explicit conversion rules.

**Practice exercise.** Extend `MoneyDimensionsDemo` with a `RoundingPolicy(scale, mode)` type and two distinct policies: per-line rounding with `HALF_UP` and total rounding with `HALF_EVEN`. Provide three values with thousandths digits and demonstrate the difference. Add tests for negative numbers, currency mismatch, `UNNECESSARY`, and the sum-conservation invariant after allocation. Explain which business scenarios call for each policy.

## 15. Official references

- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): decimal arithmetic, scale, precision, `setScale`, `divide`, `equals`, and `compareTo`.
- [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): rounding modes and rules.
- [Java SE 17 — MathContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html): significant-digit limits and rounding.
- [Java SE 17 — Currency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Currency.html): currency codes, symbols, and default fraction digits.
- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): locale-aware number and currency formatting.

**Conclusion:** A reliable monetary representation is **an exact BigDecimal value + an explicit Currency code + an explicit business rounding policy**. Do not equate scale with precision, currency metadata with settlement rules, or formatted UI strings with computational data. Define **when to round, at what granularity, and with which mode** before writing financial calculations.
