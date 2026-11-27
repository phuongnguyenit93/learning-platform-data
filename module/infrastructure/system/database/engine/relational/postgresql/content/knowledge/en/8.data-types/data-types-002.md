# Choosing Precision and Representing Monetary Values in PostgreSQL

A monetary amount looks simple, such as **125,000 VND** or **19.99 USD**, yet in an application, how it is stored and computed determines the accuracy of invoices, digital wallets, payments, refunds, and financial reports. If you use binary floating-point numbers for money and sum thousands of transactions, binary rounding errors can appear. If you store money as integers without clearly defining the unit, one party may interpret `100` as 100 VND (or 100 dollars), while another interprets it as 100 cents. If rounding happens at the wrong step, two tax calculation methods on the same invoice can differ by a unit of currency.

PostgreSQL provides several relevant data types:

- `NUMERIC` or `DECIMAL`: represents decimal numbers with controlled precision, suitable for many financial calculations.
- `SMALLINT`, `INTEGER`, `BIGINT`: stores integers, capable of representing the **minor unit** of a currency such as cents or đồng.
- `MONEY`: a specialized currency type whose fractional resolution and display formatting are affected by locale.
- `REAL`, `DOUBLE PRECISION`: binary floating-point numbers, suited to many scientific problems but generally **not the default choice for monetary amounts requiring exactness down to each unit**.

This lesson focuses on choosing the right data type for business requirements, defining rounding rules, storing currency units alongside amounts, controlling bounds, and coordinating with the application layer. Examples use PostgreSQL SQL and a bit of Java code to illustrate transferring values without losing precision.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **exact decimal numbers**, **minor-unit integers**, and **binary floating-point numbers**.
2. Explain the meaning of `NUMERIC(p,s)`: precision `p` and scale `s`.
3. Understand why `NUMERIC(12,2)` alone does not guarantee all monetary business rules and does not replace input validation.
4. Choose `BIGINT` to store cents, đồng, or other minor units when the data contract specifies them clearly.
5. Recognize the limitations of the `MONEY` type, especially regarding locales and currencies with different numbers of decimal places.
6. Determine **when, how, and at what level to round** for totals, taxes, fees, discounts, and exchange rates.
7. Design schemas with currency codes, value-domain constraints, and safeguards against directly summing amounts in different currencies.
8. Avoid passing values through `double` or unsafe `Number` types in applications.
9. Design conversion and reconciliation steps when importing, exporting, or migrating how money is stored.
10. Explain why data type precision and business correctness are **two related but distinct concerns**.

The examples assume modern PostgreSQL. Table creation and deletion statements are intended solely for a sandbox database.

---

## 2. Before Choosing a Data Type: What Makes Up "a Monetary Value"?

A monetary value typically requires **at least two components**:

```text
Numeric Value             Currency Unit
   19.99                       USD
  125000                       VND
    1500                       JPY
    1.234                      KWD
```

Storing `19.99` alone without a currency code is not enough to know which currency is meant. In addition, the system must know:

- **Currency unit:** dollars, đồng, yen, dinar, etc.
- **Unit resolution:** how many decimal digits can the system store for each currency?
- **Rounding rule:** round half-up, round down, round up, half-even, or another rule?
- **Value domain:** are negative numbers valid? What is the maximum total amount?
- **Business semantics:** list price, amount due, amount paid, or exchange rate?
- **Effective time:** which exchange rate or tax policy was used for the calculation?
- **Value origin:** entered by client, computed by system, confirmed by payment gateway, or imported data?

For example, `100` can mean:

| Representation | Meaning When the Data Contract Is Explicit |
| --- | --- |
| `amount = 100.00`, `currency = 'USD'` | 100 USD |
| `amount_minor = 100`, `currency = 'USD'` | 100 cents = 1 USD |
| `amount_minor = 100`, `currency = 'VND'` | 100 đồng if the system uses đồng as its minor unit |
| `exchange_rate = 100` | Exchange rate, **not a monetary amount** if missing the currency pair and conversion direction |

**A data type can be arithmetically exact yet wrong in terms of units.** For example, an exact addition between 100 USD and 100 JPY is still a meaningless monetary addition without a currency conversion step.

---

## 3. Comparing Data Types in PostgreSQL

| Data Type | Representation | Strengths | Limitations or Considerations |
| --- | --- | --- | --- |
| `SMALLINT` | 2-byte integer | Compact for small counts | Very narrow range for money |
| `INTEGER` | 4-byte integer | Fast, simple | Easily runs out of range for large monetary amounts or cumulative sums |
| `BIGINT` | 8-byte integer | Exact, suitable for storing minor currency units | Must clearly define scale/currency; arithmetic can overflow |
| `NUMERIC(p,s)` | Controlled-precision decimal | Suitable for money with fractional parts and exact decimal math | Typically uses more resources than integer; converts/rounds to scale |
| `NUMERIC` without `p,s` | Variable-precision decimal | Suitable for intermediate steps or values needing many digits | Does not enforce business limits automatically; still has implementation limits |
| `DECIMAL(p,s)` | Equivalent to `NUMERIC(p,s)` in PostgreSQL | Familiar SQL syntax | Shares the same precision/scale considerations |
| `MONEY` | 8-byte monetary type with fixed fractional precision per locale | Readable/formatted as currency in some contexts | Depends on `lc_monetary`, carries no business currency code, inflexible for multi-currency |
| `REAL` | 4-byte binary floating point | Suited to many measurement problems not requiring exact decimals | Does not represent all decimal numbers accurately |
| `DOUBLE PRECISION` | 8-byte binary floating point | Wider range and precision than `REAL` | Still has representation/comparison error with decimal numbers |

For standard sales or payment systems, the two most commonly considered choices are:

- **`NUMERIC(p,s)`**, e.g. `NUMERIC(18,2)`, if the schema directly represents values in major currency units (USD, đồng, etc.).
- **`BIGINT`**, if the schema represents counts of **minor units** such as cents or đồng under an agreed scale rule.

Do not choose `MONEY` merely because the type name sounds "right for money"; a type name does not automatically substitute for units, exchange rates, business logic, and rounding rules.

---

## 4. NUMERIC(p,s): Precision and Decimal Digits

In PostgreSQL:

```sql
NUMERIC(precision, scale)
```

- **Precision `p`**: the maximum total number of significant decimal digits declared.
- **Scale `s`**: the number of digits retained after the decimal point as declared.
- In the common case where `0 <= s <= p`, up to `p - s` digits can be stored before the decimal point.

Example:

```sql
price NUMERIC(12,2)
```

Visualized as:

```text
       1234567890 . 12
       ----------   --
       10 digits    2 digits
             total precision = 12
```

The largest positive value under this configuration is `9999999999.99`. The minus sign and decimal point do not count toward precision digits.

### 4.1. Reading Common Declarations

| Declaration | Max Integer Digits in Common Form | Scale | Illustrative Scenario |
| --- | ---: | ---: | --- |
| `NUMERIC(10,2)` | 8 | 2 | Retail prices, medium-scale invoices |
| `NUMERIC(12,2)` | 10 | 2 | Larger totals |
| `NUMERIC(18,2)` | 16 | 2 | Financial values with a wide range |
| `NUMERIC(18,4)` | 14 | 4 | Unit prices needing sub-cent fractions during calculation |
| `NUMERIC(24,10)` | 14 | 10 | Certain exchange rates / intermediate calculations |
| `NUMERIC` | Unconstrained by a declared `p,s` | Flexible | Calculations, staging, or when controlled at another layer |

These are **example choices**, not mandatory standards for every system. You must forecast maximum numeric ranges, negative/positive values, accumulation counts, taxes, exchange rates, and future changes.

Modern PostgreSQL also supports scale usages outside `0..p` in certain versions, such as negative scale to round to tens/hundreds. For **monetary columns requiring a fixed number of decimal places**, the standard form with non-negative scale is easiest to understand; do not apply negative scale without analyzing rounding requirements.

### 4.2. What Does PostgreSQL Do When More Decimal Digits Than Scale Are Provided?

This is a key point: **`NUMERIC(p,s)` may round the input value to the declared scale**, rather than always rejecting numbers with too many digits after the decimal point.

Example:

```sql
SELECT
    12.345::NUMERIC(8,2) AS rounded_positive,
    (-12.345)::NUMERIC(8,2) AS rounded_negative,
    12.344::NUMERIC(8,2) AS rounded_down;
```

Under PostgreSQL's default `numeric` rounding rules, the results typically correspond to:

| Input | After Casting to `NUMERIC(8,2)` |
| --- | ---: |
| 12.345 | 12.35 |
| -12.345 | -12.35 |
| 12.344 | 12.34 |

When exactly halfway between two rounding choices, PostgreSQL's `numeric` type generally rounds **away from zero** (*ties away from zero*). That rule must be checked against business requirements or tax/billing regulations, not assumed solely because the database provides it.

### 4.3. When the Integer Part Exceeds Precision

Example:

```sql
-- NUMERIC(5,2) only has room for up to 3 integer digits.
SELECT 999.99::NUMERIC(5,2);
```

This value is valid.

However:

```sql
-- Example expected to error: numeric field overflow.
SELECT 1000.00::NUMERIC(5,2);
```

is invalid because the number of digits before the decimal point exceeds the limit.

Note: rounding can also push a number over the limit. A value close to `999.99` that rounds up to `1000.00` will no longer fit in `NUMERIC(5,2)`.

### 4.4. Exact Decimal Does Not Mean Every Division Has a Finite Result

`NUMERIC` can represent finite decimal numbers accurately within the type's capabilities. Yet `1/3` has no finite decimal representation:

```sql
SELECT
    1::NUMERIC / 3::NUMERIC AS one_third,
    ROUND(1::NUMERIC / 3::NUMERIC, 2) AS rounded_to_cents;
```

PostgreSQL must pick a finite precision when executing division. Therefore, **rules for how many digits to keep and when to round must still be defined** even when all operands are `NUMERIC`.

### 4.5. The NUMERIC Type and Special Values

In modern PostgreSQL versions, `NUMERIC` can support special values like `NaN` and forms of infinity under corresponding conditions. Such values rarely make sense as an authorized payment amount.

If an application receives data directly from external sources, verify that values are **finite**, within the business domain, and properly formatted. Do not treat every value accepted by the parser as a valid monetary amount just because the column type is `numeric`.

---

## 5. Why Not Use FLOAT/DOUBLE PRECISION for Money by Default?

`REAL` and `DOUBLE PRECISION` are stored as **binary floating-point numbers**. Many familiar decimal fractions, such as `0.1`, have no finite binary representation.

Example:

```sql
SELECT
    0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION
        AS binary_float_sum,
    0.3::DOUBLE PRECISION AS expected_float,
    (0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION)
        = 0.3::DOUBLE PRECISION AS exactly_equal;
```

In common floating-point calculations, two close values may **not be strictly equal** due to binary representation/rounding errors. Displayed values may also be shortened by output formatting, so you must never inspect printed text alone to conclude an operation is completely exact.

Meanwhile:

```sql
SELECT
    (0.1::NUMERIC + 0.2::NUMERIC) = 0.3::NUMERIC
        AS exact_decimal_equal;
```

With finite decimal constants represented as `NUMERIC`, the addition in this example is equal under decimal arithmetic.

### 5.1. Are Small Errors Dangerous?

A tiny binary error might be negligible in physics or graphics calculations. For money, however, issues include:

- `=`, `<`, `>` comparisons in "sufficient balance?" checks.
- Repeated tax/fee calculations.
- Accumulating many invoice lines.
- Reconciliation against exact figures from banks/payment gateways.
- Transfers across JSON, JavaScript, drivers, and external systems.
- Different rounding between clients and the database.

For instance, a system collecting money down to the cent may require settlement results **exact to the cent**, not merely "approximately equal within an epsilon".

### 5.2. When Is Floating Point Still Reasonable?

Floating point is well-suited for many problems:

- Scientific measurements, statistics, graphics.
- Probabilities and forecasting models where approximation error is acceptable.
- Optimization computations whose final monetary outcome is still converted using explicitly designed representation/rounding rules.

If a forecasting algorithm uses `double precision` and ultimately produces a **monetary transaction**, the conversion to a transaction value must still have rounding rules, range checks, and currency units.

**Do not use `CAST(double AS numeric)` as a way to restore original monetary precision that was already lost.** Once a `double` value has been created that does not accurately represent the original input, casting only converts the current value's representation per PostgreSQL rules—it has no knowledge of the user's original intent.

---

## 6. Approach A: Storing Monetary Amounts with NUMERIC

An application handling only USD with two decimal places might use:

```sql
CREATE TABLE example_usd_prices (
    price_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    price_usd NUMERIC(18,2) NOT NULL
        CHECK (price_usd >= 0)
);
```

Example operations:

```sql
INSERT INTO example_usd_prices (price_usd)
VALUES (19.99), (125.00)
RETURNING price_id, price_usd;

SELECT SUM(price_usd) AS total_usd
FROM example_usd_prices;
```

Advantages:

1. Easy to read in SQL queries: `19.99` means 19 dollars and 99 cents if the column has a well-defined unit.
2. No need to manually divide/multiply by 100 for ordinary additions.
3. Exact for finite decimals like `0.01`.
4. Can use `SUM`, `ROUND`, `NUMERIC` arithmetic, and constraints directly.
5. Maps cleanly to Java's `BigDecimal`.

Disadvantages or design considerations:

- Scale `2` applies to the whole column and does not flex per currency if multiple currencies share one table.
- If given `19.999`, the column may round on insert instead of rejecting it as "user submitted invalid decimal places".
- The column still needs range rules, currency, and business conditions.
- Numeric operations can consume more resources than integer operations, depending on workload.
- Totals/exchange rates may require higher intermediate precision than the final stored scale.

### 6.1. Do Not Confuse Unit Price Precision with Final Payment Precision

A unit price for goods measured by weight or volume may require higher precision than cents:

```text
Unit price:     0.0150 USD per unit
Quantity:       10.000 units
Line subtotal:  0.1500 USD
Amount payable: 0.15 USD (per rounding rule)
```

If the unit price is stored immediately into `NUMERIC(18,2)`, it could be rounded to `0.02` before multiplying by quantity, distorting the original value.

A common design is:

- `unit_price NUMERIC(18,4)` or a larger scale matching the business domain.
- `quantity NUMERIC(12,3)` or matching the unit of measure.
- Compute line totals with sufficient intermediate precision.
- Round the payable amount to the payment unit at the **designated business milestone**.

Not every "price" field should default to scale 2.

### 6.2. Do Not Store Every Exchange Rate in NUMERIC(18,2)

Exchange rates may require many digits after the decimal point. Keeping only two digits and multiplying by a large amount can introduce substantial error.

Example:

```sql
SELECT
    10000::NUMERIC * 1.234567::NUMERIC AS precise_conversion,
    10000::NUMERIC * 1.23::NUMERIC AS prematurely_rounded;
```

The two results differ. An exchange-rate policy must define **storage precision for rates**, **currency pair**, **conversion direction**, **effective timestamp**, and **result rounding rules**, rather than merely changing a column type.

---

## 7. Approach B: Storing with BIGINT in Minor Currency Units

Another approach is representing money using the **smallest storable whole unit**.

For USD, if the system uses cents as the minor unit:

```text
19.99 USD    -> amount_minor = 1999
0.01 USD     -> amount_minor = 1
100.00 USD   -> amount_minor = 10000
```

For VND, a system using đồng as the minimum unit can establish the convention:

```text
125000 VND   -> amount_minor = 125000
```

This is a **data contract** across systems. You cannot read `amount_minor = 100` and know how many major currency units it represents without knowing the currency and scale.

### 7.1. Integer Table Design

```sql
CREATE TABLE example_usd_balances (
    account_id BIGINT PRIMARY KEY,
    balance_cents BIGINT NOT NULL CHECK (balance_cents >= 0)
);

INSERT INTO example_usd_balances (account_id, balance_cents)
VALUES (1, 10005), (2, 2500);

SELECT
    account_id,
    balance_cents,
    balance_cents::NUMERIC / 100 AS balance_usd
FROM example_usd_balances
ORDER BY account_id;
```

The retrieved data corresponds to:

| Account | `balance_cents` | USD |
| --- | ---: | ---: |
| 1 | 10005 | 100.05 |
| 2 | 2500 | 25.00 |

`BIGINT` uses 8 bytes and provides exact integer arithmetic within valid bounds.

Advantages:

- No binary fractional part in stored values.
- Well-suited for payment systems exchanging values in minor units.
- Easy to compare `balance_cents >= amount_cents` and add/subtract whole integers.
- Often more efficient in storage/computation than numeric when requirements align.

Limitations:

- All clients must agree on the scale.
- When adding a currency with 0 or 3 decimal places, you cannot assume multiplying all amounts by 100 works.
- Multiplication, accumulation, and conversion can **overflow BIGINT**.
- Exchange rates, percentages, and division are not naturally integers; intermediate calculation requires exact decimals followed by rounding.
- If sub-cent unit prices are needed, storing each unit price directly in cents loses precision too early.

### 7.2. Converting from Major Units to Minor Units

If USD uses 2 decimal places:

```sql
SELECT
    19.99::NUMERIC AS usd,
    (19.99::NUMERIC * 100)::BIGINT AS cents;
```

For inputs guaranteed to have at most two decimal places, multiplication yields an integer and converts to `BIGINT`.

However, with:

```sql
SELECT 19.999::NUMERIC * 100 AS not_integral_cents;
```

the result is no longer a whole number of cents. Do not cast directly without specifying a **rounding or rejection policy**.

Explicit rounding example:

```sql
SELECT ROUND(19.999::NUMERIC * 100, 0)::BIGINT
    AS rounded_cents;
```

The result is 2000 cents if policy allows rounding to cents. If the API requires users to submit at most two decimal places, `19.999` should be **rejected prior to conversion**, not silently turned into 20.00.

### 7.3. Avoiding Overflow

The `BIGINT` range is:

```text
-9223372036854775808 ... 9223372036854775807
```

Therefore, an amount stored in cents consumes more integer units than the same amount expressed in USD. A table may store every individual row validly, yet `SUM` or fee multiplications must still be evaluated for numeric range.

PostgreSQL has special type rules for aggregates—such as `SUM(BIGINT)` returning `NUMERIC`—but a **direct `BIGINT + BIGINT` arithmetic expression** still risks overflow.

A safer intermediate calculation when large numbers are needed:

```sql
SELECT
    (9000000000000000000::BIGINT)::NUMERIC
      + (9000000000000000000::BIGINT)::NUMERIC
        AS total_without_bigint_add_overflow;
```

If the result is ultimately converted back to `BIGINT`, verify it still fits within `BIGINT` bounds. Casts or constraints do not expand a type's range.

---

## 8. The MONEY Type: Convenient to View, Not a Default Choice

PostgreSQL includes a dedicated type:

```sql
CREATE TABLE example_money_type (
    id INTEGER PRIMARY KEY,
    amount MONEY
);
```

Example:

```sql
INSERT INTO example_money_type (id, amount)
VALUES (1, 10.25::MONEY);

SELECT amount
FROM example_money_type;
```

The `MONEY` type typically has an 8-byte internal representation with a fixed fractional precision tied to the `lc_monetary` setting. How **monetary strings are displayed and parsed** depends on the configured locale, such as currency symbols and separators.

### 8.1. Why Does lc_monetary Matter?

```sql
SHOW lc_monetary;
```

If one system generates data under one locale setting and exports text-formatted money output to another system with different rules, parsing may behave differently.

Common issues:

- Inflexible when a single table holds currencies requiring 0, 2, or 3 decimal places per row.
- The `money` type does not store the currency's ISO code alongside the value.
- Output formatting depends on configuration and should not be treated as a stable API format.
- Converting/multiplying/dividing with other types requires understanding type and rounding rules; do not use formatted currency strings for calculations.
- When dumping/restoring across environments with different locales, data compatibility and representation issues can arise.

For applications requiring clean JSON APIs, multiple currencies, audit rules, or intermediate calculations with varying scales, `NUMERIC` or `BIGINT` paired with a currency code is generally easier to control.

**Do not treat `MONEY` as a tool that supports exchange rates or automatically distinguishes USD, VND, and JPY.** It is primarily a numeric amount type with locale-specific display formatting.

---

## 9. Different Currencies Have Different Decimal Places

A major mistake in multi-currency schemas is assuming **every currency has 2 decimal places**.

Some common examples in systems based on currency codes:

| Currency | Example Common Minor Unit | Illustrative Decimal Places |
| --- | --- | ---: |
| USD | cent | 2 |
| VND | đồng | 0 |
| JPY | yen | 0 |
| KWD | fils | 3 |

This table only illustrates commonly used currency units; **payment gateways, data format standards, or system contracts may enforce specific scale rules**. Thus, a real schema must confirm conventions across all integrated parties rather than relying solely on the currency name.

### 9.1. A Multi-Currency Definition

You can store metadata for each currency:

```sql
CREATE TABLE currency_definitions (
    code VARCHAR(3) PRIMARY KEY
        CHECK (code ~ '^[A-Z]{3}$'),
    minor_digits SMALLINT NOT NULL
        CHECK (minor_digits BETWEEN 0 AND 3)
);

INSERT INTO currency_definitions (code, minor_digits)
VALUES
    ('USD', 2),
    ('VND', 0),
    ('JPY', 0),
    ('KWD', 3);
```

**Note:** The regex `^[A-Z]{3}$` only validates the three-uppercase-letter format; it **does not prove the code belongs to an active ISO catalog**. Reference tables/standard sources must be governed as configuration data, with controlled changes and history tracking when business rules require it.

### 9.2. Example Wallet Storing BIGINT Minor Units

```sql
CREATE TABLE wallet_balances (
    wallet_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    currency_code VARCHAR(3) NOT NULL
        REFERENCES currency_definitions(code),
    balance_minor BIGINT NOT NULL CHECK (balance_minor >= 0)
);

INSERT INTO wallet_balances (currency_code, balance_minor)
VALUES
    ('USD', 1999),      -- 19.99 USD
    ('VND', 125000),    -- 125000 VND
    ('JPY', 1500),      -- 1500 JPY
    ('KWD', 1234);      -- 1.234 KWD
```

When displaying values in major currency units, use the scale metadata:

```sql
SELECT
    w.wallet_id,
    w.currency_code,
    w.balance_minor,
    c.minor_digits,
    w.balance_minor::NUMERIC
       / POWER(10::NUMERIC, c.minor_digits)
        AS amount_major
FROM wallet_balances AS w
JOIN currency_definitions AS c
  ON c.code = w.currency_code
ORDER BY w.wallet_id;
```

Arithmetic results:

| Currency | `balance_minor` | `minor_digits` | Major Amount |
| --- | ---: | ---: | ---: |
| USD | 1999 | 2 | 19.99 |
| VND | 125000 | 0 | 125000 |
| JPY | 1500 | 0 | 1500 |
| KWD | 1234 | 3 | 1.234 |

In production systems, `currency_definitions` must be treated as critical metadata. If `minor_digits` is changed from 2 to 0 without migrating `balance_minor` data accordingly, **the meaning of stored balances shifts by a factor of 100**. Never modify scales applied to existing balances as if it were a simple UI tweak.

### 9.3. Do Not Directly Sum Different Currencies

Wrong:

```sql
SELECT SUM(balance_minor) AS misleading_total
FROM wallet_balances;
```

The SQL statement executes and returns an integer, yet that total is **monetarily meaningless** because it sums cents, đồng, yen, and fils together.

At minimum, group by currency:

```sql
SELECT
    currency_code,
    SUM(balance_minor) AS total_minor
FROM wallet_balances
GROUP BY currency_code
ORDER BY currency_code;
```

If a converted total in a single reporting currency is needed, you must have **exchange rates defined by pair, timestamp, and conversion direction**, followed by a valid rounding policy.

---

## 10. ROUND Rules: Where to Round Is a Business Decision

PostgreSQL provides the `ROUND` function:

```sql
SELECT
    ROUND(12.345::NUMERIC, 2) AS rounded_two_decimals,
    ROUND((-12.345)::NUMERIC, 2) AS rounded_negative;
```

With `NUMERIC`, the results in this example are `12.35` and `-12.35`.

However, the critical question is not only **how to round**, but also **at which step to round**:

- After each line item?
- After summing all lines?
- After calculating separate fees?
- After applying discounts?
- After currency conversion?
- When generating the final payment transaction?

Two workflows that both use exact decimals can still yield different outcomes.

### 10.1. Round Per Line or Round on the Total?

Suppose there are two line items, each with a taxable amount of `0.05 USD` and an illustrative tax rate of `10%`.

If rounding tax **per line**:

```sql
SELECT
    ROUND(0.05::NUMERIC * 0.10::NUMERIC, 2)
    + ROUND(0.05::NUMERIC * 0.10::NUMERIC, 2)
      AS tax_rounded_per_line;
```

Each line yields tax `0.005`, rounded to `0.01`, totaling `0.02`.

If summing the taxable base first and then rounding:

```sql
SELECT
    ROUND(
        (0.05::NUMERIC + 0.05::NUMERIC)
         * 0.10::NUMERIC,
        2
    ) AS tax_rounded_on_total;
```

The result is `0.01`.

| Workflow | Final Tax |
| --- | ---: |
| Round per line, then sum | 0.02 USD |
| Sum lines, compute tax, round once | 0.01 USD |

This difference **is not a bug in `NUMERIC`**. It is a difference in **business rules**. In real payment/tax systems, you must follow contracts or applicable regulations—never pick one arbitrarily just because it produces a smaller number.

### 10.2. Half-Up, Half-Even, Floor, and Ceiling

Some familiar rounding policies:

| Policy | General Meaning |
| --- | --- |
| Round to nearest, ties away from zero | Example of how `ROUND(numeric, scale)` typically handles exact midpoints |
| Half-even | When exactly halfway between two values, chooses the side with an even last digit per rule |
| Floor | Rounds down toward negative infinity |
| Ceiling | Rounds up toward positive infinity |
| Truncate | Discards fractional part smaller than the target unit per rule |

Example:

```sql
SELECT
    ROUND(2.5::NUMERIC) AS rounded_2_5,
    ROUND((-2.5)::NUMERIC) AS rounded_negative_2_5,
    FLOOR(2.5::NUMERIC) AS floored,
    CEIL(2.5::NUMERIC) AS ceiled,
    TRUNC(2.99::NUMERIC, 0) AS truncated;
```

**`FLOOR` is not the same as `TRUNC` for negative numbers.** For example, `FLOOR(-1.2)` is `-2`, while `TRUNC(-1.2)` is `-1`. Such details matter greatly when calculating fees, refunds, and negative amounts.

If the business requires **half-even**, do not assume PostgreSQL's default `ROUND(numeric, scale)` implements that policy. Build or use separately verified rounding logic, and ensure Java/backend/database match.

### 10.3. Rounding Before SUM Can Distort the Total

Suppose purchased items have a unit price of 0.015 USD and quantity 100. If you round the unit price first:

```sql
SELECT
    ROUND(0.015::NUMERIC, 2) * 100 AS premature_rounding,
    ROUND(0.015::NUMERIC * 100, 2) AS round_final_amount;
```

Under decimal rounding, the two results differ: `2.00` versus `1.50`. Exact arithmetic still cannot rescue a decision to round too early.

Practical rule: **keep sufficient precision in intermediate values, and round only at the designated business milestone**.

---

## 11. Illustrative Schema: Unit Prices More Precise Than Payable Amounts

An order model often includes:

- Potentially non-integer quantities: `quantity NUMERIC(12,3)`.
- Unit prices with 4 decimal places: `unit_price_usd NUMERIC(18,4)`.
- Line totals in USD computed to 2 decimal places: `line_total_usd NUMERIC(18,2)`.

Create an example in a practice schema:

> **Run only on a lab database.** The `DROP TABLE` statements in this section delete prior data for these specific illustrative objects. Do not reuse production table names.

```sql
CREATE SCHEMA IF NOT EXISTS money_lab;

DROP TABLE IF EXISTS money_lab.invoice_lines;

CREATE TABLE money_lab.invoice_lines (
    line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL,
    quantity NUMERIC(12,3) NOT NULL
        CHECK (quantity > 0),
    unit_price_usd NUMERIC(18,4) NOT NULL
        CHECK (unit_price_usd >= 0),
    line_total_usd NUMERIC(18,2)
        GENERATED ALWAYS AS (
            ROUND(quantity * unit_price_usd, 2)
        ) STORED
);
```

In this table:

- `quantity` and `unit_price_usd` retain precision required by the goods.
- `line_total_usd` is a **generated stored column**, computing and storing the result via the expression.
- `ROUND(...,2)` expresses the line-level total calculation rule chosen by this example.
- `NUMERIC(18,2)` on the result column also constrains the final numeric domain.
- The `usd` suffix in column names makes clear this is a single-currency table—**do not mix other currencies into the same column**.

Insert three rows:

```sql
INSERT INTO money_lab.invoice_lines (
    sku, quantity, unit_price_usd
)
VALUES
    ('ITEM-A', 1.000, 19.9900),
    ('ITEM-B', 2.500,  4.2000),
    ('ITEM-C', 100.000, 0.0150)
RETURNING
    sku, quantity, unit_price_usd, line_total_usd;
```

Arithmetic results:

| SKU | Quantity | Unit Price USD | Line Total USD |
| --- | ---: | ---: | ---: |
| ITEM-A | 1.000 | 19.9900 | 19.99 |
| ITEM-B | 2.500 | 4.2000 | 10.50 |
| ITEM-C | 100.000 | 0.0150 | 1.50 |
| **Total** | | | **31.99** |

Total:

```sql
SELECT
    SUM(line_total_usd) AS invoice_total_usd
FROM money_lab.invoice_lines;
```

Result: `31.99`.

### 11.1. Why Not Accept line_total from the API?

If a client sends `quantity`, `unit_price`, and `line_total` simultaneously, the three values might not agree. Letting the database compute the generated column provides **one explicit formula** in this example.

However, a generated column does not handle every policy automatically:

- Unit prices may change over time; invoices must store a snapshot of the locked-in price.
- Discounts and taxes may follow separate calculation workflows.
- Some markets require different rounding rules.
- Negative amounts may be valid in adjustment/refund notes, requiring an explicit model.
- If the currency varies per row, a hardcoded scale-2 expression is no longer right for all rows.

Therefore, this illustrative table fits a lesson on **single-currency USD with a line-level rounding rule**, not a complete multinational invoicing template.

### 11.2. Aggregating Empty Monetary Sets

In PostgreSQL:

```sql
SELECT SUM(line_total_usd) AS total
FROM money_lab.invoice_lines
WHERE sku = 'NOT-EXIST';
```

For a set with zero rows, `SUM` returns **NULL**, not 0. If business reporting requires "zero rows means total is 0", you can explicitly do:

```sql
SELECT
    COALESCE(SUM(line_total_usd), 0::NUMERIC) AS total_usd
FROM money_lab.invoice_lines
WHERE sku = 'NOT-EXIST';
```

Distinguish "no transactions" from "a transaction with value 0" whenever the business requires an audit trail.

---

## 12. Illustrative Schema: Multi-Currency Wallets Using Minor Units

In the lab database, create a currency reference table and a wallets table. Use the `money_lab` schema to avoid colliding with earlier examples:

```sql
CREATE TABLE money_lab.currency_units (
    code VARCHAR(3) PRIMARY KEY
        CHECK (code ~ '^[A-Z]{3}$'),
    minor_digits SMALLINT NOT NULL
        CHECK (minor_digits BETWEEN 0 AND 3)
);

INSERT INTO money_lab.currency_units (code, minor_digits)
VALUES
    ('USD', 2),
    ('VND', 0),
    ('JPY', 0),
    ('KWD', 3);

CREATE TABLE money_lab.wallets (
    wallet_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_label TEXT NOT NULL,
    currency_code VARCHAR(3) NOT NULL
        REFERENCES money_lab.currency_units(code),
    balance_minor BIGINT NOT NULL
        CHECK (balance_minor >= 0)
);
```

Load wallet data:

```sql
INSERT INTO money_lab.wallets (
    owner_label, currency_code, balance_minor
)
VALUES
    ('Alice USD', 'USD', 10005),
    ('Bob USD',   'USD', 2500),
    ('Chi VND',   'VND', 125000),
    ('Dao JPY',   'JPY', 1500),
    ('Em KWD',    'KWD', 1234);
```

View in major units:

```sql
SELECT
    w.owner_label,
    w.currency_code,
    w.balance_minor,
    c.minor_digits,
    w.balance_minor::NUMERIC
        / POWER(10::NUMERIC, c.minor_digits) AS major_amount
FROM money_lab.wallets AS w
JOIN money_lab.currency_units AS c
  ON c.code = w.currency_code
ORDER BY w.wallet_id;
```

The numeric value `10005` means **100.05 USD** when `minor_digits = 2`, while `125000` with VND and scale 0 means **125000 VND**.

### 12.1. Grouping Totals by Currency

```sql
SELECT
    currency_code,
    SUM(balance_minor) AS total_minor
FROM money_lab.wallets
GROUP BY currency_code
ORDER BY currency_code;
```

Do not use:

```sql
-- Example of a calculation meaningless in units, though valid SQL.
SELECT SUM(balance_minor) FROM money_lab.wallets;
```

because it combines different currency units.

### 12.2. Do Not Arbitrarily Change a Currency's minor_digits

If the metadata `USD = 2` is changed to `USD = 0`, all existing USD balances are interpreted differently. This is a critical bug even though zero rows in `wallets` were updated.

In production environments, you must:

- Restrict permissions to modify currency metadata tables.
- Establish standards and versioning for scales used on historical data.
- Plan data migrations before any breaking change.
- Verify integrations with payment gateways and downstream systems.
- Record audits/approvals when metadata affects money.

---

## 13. Computing Taxes, Discounts, and Fees with Appropriate Precision

Monetary calculations often combine multiple kinds of values:

| Data Category | Example Type | Reason |
| --- | --- | --- |
| Final USD price | `NUMERIC(18,2)` | Two decimal places for payable amount |
| Pre-settlement unit price | `NUMERIC(18,4)` | May need sub-cent fractions |
| Quantity | `NUMERIC(12,3)` | Goods measured by weight/volume |
| Tax rate | `NUMERIC(9,6)` | Rate with many decimal digits |
| Discount percentage | `NUMERIC(9,6)` | Not a monetary amount; domain such as 0..1 |
| Exchange rate | `NUMERIC(24,10)` or per business rules | Needs higher precision than final money |
| Settled amount in cents | `BIGINT` | Integer value after rounding |

### 13.1. How Should Rates Be Represented?

You can store rates as decimal numbers:

```sql
SELECT
    120.00::NUMERIC * 0.075::NUMERIC
        AS seven_point_five_percent;
```

Result `9.00000...` depending on display formatting.

Or in basis points (bps):

```text
1 bps = 0.01%
750 bps = 7.50%
```

Computing a fee from `amount_minor`:

```sql
SELECT
    ROUND(
        12345::NUMERIC * 750::NUMERIC / 10000::NUMERIC,
        0
    )::BIGINT AS fee_minor;
```

For an amount of 12345 cents and a 750 bps (7.5%) fee, the pre-rounding decimal value is 925.875 cents, rounded under the illustrative policy to 926 cents.

What matters is **choosing a rounding mechanism that matches the fee contract**, not merely applying an arithmetically valid formula.

### 13.2. Negative Amounts in Refunds and Adjustments

Not all monetary values must be non-negative:

- List prices are typically non-negative.
- Wallet balances in a prepaid model may need to be non-negative.
- Accounting ledger entries may use debit/credit columns or signed amounts.
- Refunds may be represented by negative adjustment rows in a specific model.

Do not blindly apply `CHECK(amount >= 0)` to every table. Instead, constrain each table **according to the field's meaning**.

For example, a ledger entries table might use:

```sql
CREATE TABLE money_lab.ledger_entries (
    entry_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    wallet_id BIGINT NOT NULL
        REFERENCES money_lab.wallets(wallet_id),
    signed_amount_minor BIGINT NOT NULL
        CHECK (signed_amount_minor <> 0),
    operation_key TEXT NOT NULL UNIQUE,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

However, such an entry table **does not by itself guarantee a balanced ledger** or zero-sum entries. Multi-row invariants require dedicated transaction mechanisms and business design.

---

## 14. Foreign Currency Conversion: Rate and Money Are Two Different Quantities

An exchange rate requires at least:

- Source currency.
- Target currency.
- Rate value and multiplication/division direction.
- Effective time and time applied.
- Rate provider source.
- Precision and rounding rules.
- Fee or spread policy, if applicable.

Purely **synthetic** example for illustration: `1 USD = 25,000 VND`. Do not treat this rate as live market data.

Converting `123.45 USD` to VND:

```sql
SELECT
    123.45::NUMERIC AS usd_amount,
    25000::NUMERIC AS illustrative_vnd_per_usd,
    ROUND(123.45::NUMERIC * 25000::NUMERIC, 0)
       AS vnd_amount;
```

Result: `3,086,250 VND` in the example, rounded to 0 decimal places.

When the source money is stored in `minor units` (cents):

```sql
SELECT
    ROUND(
       (12345::NUMERIC / 100::NUMERIC)
       * 25000::NUMERIC,
       0
    )::BIGINT AS vnd_minor;
```

The result is also `3086250`, assuming VND uses scale 0.

### 14.1. Do Not Truncate Exchange Rates to Final Money Scale

If an exchange rate is small, e.g., from currency A to B is `0.0001234567`, `NUMERIC(18,2)` would round it to `0.00` and turn the conversion into 0.

Therefore:

- Store exchange rates with precision/scale suited to requirements.
- Compute intermediate steps with `NUMERIC` at sufficient precision.
- Round the **target monetary amount** according to the target currency's scale and policy.
- Persist the rate, currency pair, and timestamp applied if results must be reproducible later.

### 14.2. Do Not Recompute Past Transactions Using Current Rates

If a transaction was settled yesterday at rate X and today the rate changes to Y, reports of settled amounts must not change simply because the system queries the rate service again.

Data must store a **snapshot** of the calculation parameters at transaction time as required for reconciliation, e.g., `rate_applied`, `source_currency`, `target_currency`, and `converted_amount_minor`.

---

## 15. Transactions and Constraints to Protect Balances

Choosing the right data type is necessary, yet insufficient to protect a wallet against two concurrent update requests.

Suppose two USD wallets in `money_lab.wallets` have balances of 10005 and 2500 cents. We need to transfer 3000 cents from the first wallet to the second.

A conditional UPDATE helps prevent deducting when funds are insufficient:

```sql
UPDATE money_lab.wallets
SET balance_minor = balance_minor - 3000
WHERE owner_label = 'Alice USD'
  AND currency_code = 'USD'
  AND balance_minor >= 3000
RETURNING wallet_id, balance_minor;
```

If no row is returned, the deduction did not take place. **The application must treat this as a business branch to handle**, rather than assuming the SQL statement succeeding means the transfer succeeded.

However, a transfer is not just a deduction: it also credits the recipient, records history, checks currency, and locks against duplicate requests. These steps belong in a single transaction, e.g., at the design level:

```text
BEGIN
  Verify idempotency / request validity
  Confirm both wallets share the same currency
  Lock relevant rows in a consistent order when needed
  Deduct amount_minor conditionally on sufficient balance
  Verify exactly one row was updated
  Credit amount_minor to recipient wallet
  Verify exactly one row was updated
  Write ledger / request result
COMMIT

Any error or failed condition -> ROLLBACK
```

This is a transaction pattern, not a complete SQL script covering full idempotency and reconciliation. Production systems must use controlled transactions, proper locking, and unique keys.

### 15.1. Why Must Currency Be Checked at the Business Layer?

Two wallets can share the same `BIGINT balance_minor` type, while one is USD and the other is VND. Subtracting and adding the same integer `3000` between them without currency conversion is wrong.

The system should model money as a composite structure:

```text
Money {
    currency: 'USD',
    minor_units: 3000
}
```

and only allow adding two values with matching currency/scale. Any cross-currency conversion must go through a conversion operation with an explicit rate and rounding.

### 15.2. Constraints Help, but Do Not Protect the Entire Balance

`CHECK(balance_minor >= 0)` prevents a wallet row from holding a negative balance. However, it does not automatically ensure:

- A transfer has two balanced ledger entries.
- The transaction comes from an authorized actor.
- Client retries do not deduct money twice.
- Currency references and exchange rates are accurate for that timestamp.
- Total revenue matches settled transactions.

Data types, constraints, transactions, isolation levels, idempotency, and auditing must work together.

---

## 16. Importing Monetary Data from CSV, JSON, or External Systems

A very common source of precision bugs does not sit inside PostgreSQL, but occurs **before the data ever reaches the database**.

Example:

1. Client sends the string `"19.99"`.
2. Backend parses it into a `double`.
3. Code performs multiple floating-point operations.
4. The resulting value is converted to `BigDecimal` or `NUMERIC`.
5. The database stores a number altered by intermediate binary representation/rounding.

Even though the final column is `NUMERIC(18,2)`, the original value may already have been distorted prior to storage.

### 16.1. Accept Decimals via String or Decimal-Aware Parsers

For an API receiving monetary amounts in major units, a clear contract can look like:

```json
{
  "currency": "USD",
  "amount": "19.99"
}
```

Decimal string format lets the backend validate:

- Exact number of fractional digits.
- Whether negative signs are allowed.
- Value range.
- Decimal separator character.
- Rules for converting to `BigDecimal` or minor units.

If an API chooses JSON numbers instead of strings, libraries/parsers must be evaluated for precision limits, especially if data passes through JavaScript.

### 16.2. Minor Units in JSON

Another API might use:

```json
{
  "currency": "USD",
  "amount_minor": 1999
}
```

This is very clear if all integrated parties agree that `amount_minor` is an integer scaled per the currency with a safe range limit.

However, JavaScript `Number` only represents integers accurately up to a safe limit (commonly cited as `2^53 - 1`). PostgreSQL's `BIGINT` has a significantly wider range.

Therefore, for very large integers in JSON passing through JavaScript, you may need to send **integer strings**, use BigInt/decimal libraries appropriately, or cap the range in the API contract.

### 16.3. CSVs with Locale-Specific Decimal Separators

A CSV file might contain:

```csv
order_id,currency,amount
1,USD,19.99
2,VND,125000
```

While another file uses decimal commas or locale-specific thousands separators:

```text
19,99
1.234,50
```

You cannot assume PostgreSQL's `NUMERIC` parser automatically understands all locale-specific monetary notations. When ingesting multi-region data:

1. Explicitly define CSV encoding and delimiter.
2. Normalize data into a **canonical decimal string** before casting.
3. Distinguish field delimiters from numeric separators.
4. Validate currency and scale per row.
5. Reconcile row counts and totals after import.
6. Never silently turn unparseable values into 0.

---

## 17. Controlling Input Fractional Digits

A design issue requiring explicit handling: a `NUMERIC(18,2)` column **will round inputs** if a number has more than two decimal places. In some workflows that is desired; in others, it is **invalid data that must be rejected**.

Suppose the API only accepts USD with at most 2 digits after the decimal point.

### 17.1. You Cannot Rely on CHECK After Casting into NUMERIC(18,2)

Example:

```sql
CREATE TABLE money_lab.received_amounts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    amount NUMERIC(18,2) NOT NULL
        CHECK (amount = ROUND(amount, 2))
);
```

If you insert `19.999`, PostgreSQL can already round the value to `20.00` when coercing to the column type, so `CHECK(amount = ROUND(amount,2))` fails to detect that the client sent three decimal places.

This illustrates: **constraints on post-cast values cannot always inspect the original input**.

### 17.2. Validating Before Casting

You can land raw data in `TEXT` staging or validate in the application using a decimal parser:

```sql
CREATE TABLE money_lab.amount_staging (
    source_id TEXT PRIMARY KEY,
    currency_code VARCHAR(3) NOT NULL,
    amount_text TEXT NOT NULL
);
```

Example input:

```sql
INSERT INTO money_lab.amount_staging
    (source_id, currency_code, amount_text)
VALUES
    ('a1', 'USD', '19.99'),
    ('a2', 'USD', '19.999'),
    ('a3', 'USD', '-1.00');
```

In this example **solely for non-negative USD with at most two decimal places**, invalid formats can be detected:

```sql
SELECT *
FROM money_lab.amount_staging
WHERE currency_code = 'USD'
  AND amount_text !~ '^[0-9]+(\.[0-9]{1,2})?$';
```

Results may include `19.999` and `-1.00`.

This regex **only checks input syntax**; it does not verify the `NUMERIC(18,2)` numeric range, permit currency symbols, whitespace, or locales, nor handle all currencies. Do not promote it to production rules without adding business checks, length limits, and conversion error handling.

### 17.3. Do Not Use TEXT as a Long-Term Monetary Type

A text column preserves `"19.999"` for input validation, yet using text as the primary monetary column causes problems:

- Cannot add/subtract properly using numeric operators.
- Easily accumulates inconsistent formats.
- String sorting differs from numerical value sorting.
- Does not block inputs like `'abc'` without extra constraints.
- Incurs conversion overhead in every financial query.

Thus, **TEXT belongs in staging/raw sources**, while business tables should store `NUMERIC` or minor-unit integers per confirmed design.

---

## 18. Java: Using BigDecimal When Interacting with NUMERIC

Java applications connecting to PostgreSQL via JDBC typically use `java.math.BigDecimal` for `NUMERIC/DECIMAL`.

### 18.1. Constructing BigDecimal Properly

Recommended way:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("19.99");
BigDecimal quantity = new BigDecimal("2.5");

BigDecimal raw = price.multiply(quantity);
BigDecimal amount = raw.setScale(2, RoundingMode.HALF_UP);

System.out.println(amount); // 49.98 (per HALF_UP)
```

In this case, `19.99 × 2.5 = 49.975`, which rounds HALF_UP to two decimal places as `49.98`.

Avoid by default:

```java
// Do not use this to build decimal money from a double literal.
BigDecimal amount = new BigDecimal(0.1);
```

Because `0.1` here is a binary `double`, `new BigDecimal(double)` captures the exact value of that binary representation, not the exact decimal string `"0.1"` the author intended.

Better alternatives:

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = BigDecimal.valueOf(0.1);
```

`BigDecimal.valueOf(double)` uses Java's canonical decimal string representation of the double and is generally better than the direct `double` constructor; however, **if the value has already passed through multiple `double` calculations, it cannot restore the original arithmetic intent**. For money, prefer parsing decimals directly from strings from the start.

### 18.2. Rounding Explicitly in the Application

```java
BigDecimal taxRate = new BigDecimal("0.075");
BigDecimal base = new BigDecimal("120.00");

BigDecimal rawTax = base.multiply(taxRate);
BigDecimal tax = rawTax.setScale(2, RoundingMode.HALF_UP);
```

Do not assume every module uses `HALF_UP`. If `HALF_EVEN` or another mode is required, declare it explicitly in domain/business rules and ensure PostgreSQL and the backend apply consistent policies.

In particular, `BigDecimal` division when the decimal expansion is non-terminating requires specifying scale and rounding mode, for example:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal oneThird = one.divide(
    three, 8, RoundingMode.HALF_UP
);
```

If handling for non-terminating results is omitted, division can throw an arithmetic exception.

### 18.3. Passing NUMERIC with JDBC

Example using `PreparedStatement`:

```java
BigDecimal payment = new BigDecimal("19.99");

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO payments (amount_usd) VALUES (?)")) {
    ps.setBigDecimal(1, payment);
    ps.executeUpdate();
}
```

This is a **JDBC code sample**; the `payments` table in this snippet was not created in the lab. The key takeaway is using `setBigDecimal` instead of converting money to `double`.

When reading:

```java
BigDecimal stored = resultSet.getBigDecimal("amount_usd");
```

With a minor-units design, you can use `setLong`/`getLong` alongside a domain money type holding currency + minor amount. Handle `NULL` carefully in JDBC (for example, `getLong` returns 0 for NULL, so check `wasNull()` if the column is nullable).

### 18.4. Do Not Let the Frontend Decide the Final Result Alone

The frontend can display rounded prices, but the backend must calculate/verify payable amounts from approved data. Never blindly trust `total=...` sent by the client, as client logic may be outdated or tampered with.

PostgreSQL constraints protect data types and domains, while authority over pricing, taxes, promotions, and exchange rates is business logic that must be enforced at the appropriate layer.

---

## 19. NUMERIC, BIGINT, and Architectural Decision Order

Selection criteria guide:

| Question | If "Yes" | Recommendation |
| --- | --- | --- |
| Does the system store final amounts in cents/đồng and has infrastructure standardized on minor units? | Yes | Consider `BIGINT` paired with currency code and scale metadata |
| Need to store unit prices with 4–8 fractional digits or detailed exchange rates? | Yes | Consider an appropriate `NUMERIC(p,s)` |
| Are there multiple currencies with different scales? | Yes | Require currency code + scale rules; do not hardcode 2 decimals everywhere |
| Very high speed/storage requirements and integer-only math? | Yes | `BIGINT` is often advantageous if ranges and operations fit |
| Complex division or percentage taxes/fees? | Yes | Compute intermediate values in `NUMERIC`, then quantize per final rules |
| Need to display currency symbols across locales? | Yes | Let the presentation layer format from amount + currency; avoid relying on `MONEY` output |
| Require exactness down to the business's smallest unit? | Yes | Avoid binary floats for settled monetary amounts |
| Dealing with legacy `MONEY` or `FLOAT`? | Yes | Build a migration and reconciliation plan before changing types |

You can use **both representations within the same system** when justified:

- Unit price table: `NUMERIC(18,4)`.
- Settled price table: `NUMERIC(18,2)` or `BIGINT cents`.
- Payment ledger table: `BIGINT minor units`.
- Exchange rate table: `NUMERIC(24,10)`.
- Reporting queries: convert to `NUMERIC` for presentation/calculation.

However, there must be an **explicit conversion contract**, preventing one table from treating `100` as dollars while another treats `100` as cents.

---

## 20. Migrating from FLOAT/MONEY to Clearer Types

Changing a monetary column's type on a table containing existing data is a business change, not merely a DDL syntax tweak.

### 20.1. Questions Before Migrating

1. In **which unit** are existing values stored?
2. If floating point, where is the original source data for reconciliation?
3. How many currencies coexist in the same column?
4. Are there negative values, NULLs, NaNs, Infinity, or out-of-range values?
5. Is rounding to 2, 0, or 3 digits needed depending on currency?
6. What types do existing reports and APIs assume?
7. Are any keys or unique constraints affected?
8. Can writes be paused or a two-phase migration used to avoid race conditions?

### 20.2. Do Not Blindly Cast from DOUBLE to NUMERIC

Illustrative example:

```sql
SELECT
    19.999::DOUBLE PRECISION::NUMERIC(18,2)
        AS decimal_after_float;
```

The result is the value after float representation and rounding/casting, **not guaranteed to reflect the source system's original intent**.

A safer migration workflow typically includes:

```text
Inspect legacy data
      |
      v
Define unit/currency and rounding rules
      |
      v
Create new column/table with appropriate type
      |
      v
Migrate in batches or controlled phases
      |
      v
Reconcile row-by-row data + totals per currency
      |
      v
Update writers/readers/APIs
      |
      v
Cut over formally and monitor
```

### 20.3. Example Converting Decimal USD to Cents

Suppose a staging table has `amount_usd NUMERIC` and the data has already been validated.

```sql
SELECT
    amount_usd,
    ROUND(amount_usd * 100, 0)::BIGINT AS amount_cents
FROM some_validated_usd_staging;
```

This is a **SQL pattern**; `some_validated_usd_staging` was not created in the lab.

It is only appropriate when:

- The currency is genuinely USD.
- `amount_usd` is measured in dollars.
- The rounding policy permits converting to cents.
- The result fits within `BIGINT` bounds.
- Source data has been verified and post-conversion totals are reconciled.

Do not silently turn invalid decimal inputs into rounded numbers when policy requires rejection.

---

## 21. Performance and Storage

Type selection cannot rely on accuracy alone; workload matters as well.

### 21.1. BIGINT and NUMERIC

`BIGINT` has a fixed 8-byte size. `NUMERIC` uses a decimal representation whose size varies with digit count and typically incurs extra CPU cost for certain operations compared to integers.

This can matter when:

- Tables have hundreds of millions of rows.
- There are heavy additions, comparisons, sorts, and indexes on monetary columns.
- Running high-frequency real-time financial aggregations.
- Storage/I/O constraints are strict.

However, **do not switch to BIGINT just because it is faster in a microbenchmark** if doing so compromises unit clarity or forces the application into uncontrolled conversions. The cost of precision errors or business bugs far outweighs a few percent in speed.

### 21.2. Indexes and Filtered Queries

You can index monetary columns when query patterns call for it:

```sql
CREATE INDEX idx_wallets_currency_balance
ON money_lab.wallets (currency_code, balance_minor);
```

A composite index on currency + amount is more useful than amount alone when queries frequently filter by currency.

Example:

```sql
SELECT wallet_id, balance_minor
FROM money_lab.wallets
WHERE currency_code = 'USD'
  AND balance_minor >= 10000
ORDER BY balance_minor;
```

Indexes should be evaluated with `EXPLAIN` and realistic data. On a 5-row lab table, PostgreSQL may pick a sequential scan because it is cheaper, which is completely normal.

### 21.3. Do Not Convert Money to Strings for ORDER BY

Example strings:

```text
'2.00'
'19.00'
'100.00'
```

Lexicographical text sorting differs from numerical sorting. Monetary data should be stored as numeric types paired with currency, while formatting like "100,00 €" or "100.00 USD" belongs in the presentation layer.

---

## 22. Common Mistakes

| Mistake | Why It Is Dangerous | Remedy |
| --- | --- | --- |
| Storing money as `DOUBLE PRECISION` across all transactions | Cannot represent all decimals accurately | Use `NUMERIC` or `BIGINT` minor units per requirements |
| Using `NUMERIC(10,2)` for every monetary field | Currencies differ in scale; unit prices/rates may need more digits | Design scale per quantity and currency |
| Treating `NUMERIC(18,2)` as an "at most 2 input decimals" validator | The type may auto-round before constraints run | Validate prior to casting or use staging |
| Using `MONEY` thinking PostgreSQL stores the currency code | `money` carries no business currency code | Store currency separately; use numeric/minor units where appropriate |
| Storing `100` without stating cents vs. USD | Another system may misinterpret by 100x | Document clearly in column names and API contracts |
| Adding `USD` and `JPY` directly | Wrong in units even if SQL runs | Group by currency, convert using effective rates |
| Calling `ROUND` at every computation step | Can accumulate discrepancies | Round at designated business milestones |
| Assuming `ROUND(numeric)` is half-even | Tie-breaking rules may differ from policy | Specify mode explicitly, implement consistently |
| Parsing money into Java `double` before `BigDecimal` | Introduces binary error into the pipeline | Parse strings directly into `BigDecimal` |
| Using `new BigDecimal(0.1)` | Captures the binary value of the double | Use `new BigDecimal("0.1")` or a decimal parser |
| Using JS Number for large `BIGINT` | Exceeds JavaScript safe integer range | Use strings/BigInt and matching API contracts |
| Using `INTEGER` for large balances | Overflow risk | Estimate numeric bounds, consider `BIGINT` |
| Using `NUMERIC` without value bounds | May allow negative or nonsensical values depending on domain | Add CHECK/NOT NULL and validation |
| Storing exchange rates with only 2 decimal places | Loses precision during conversion | Store rates with adequate precision |
| Recomputing old transactions with new rates | Corrupts historical monetary figures | Store snapshots of applied rates and settled amounts |
| Using one scale for unit price, tax, and final payment | Unit prices and final amounts need different resolution | Separate types/scales by column semantics |
| Ignoring `UPDATE ... RETURNING` | May affect 0 rows without raising an SQL error | Check row count, roll back transaction when needed |
| Relying only on non-negative CHECK without transactions | Can debit one side without crediting the other | Use atomic transactions and concurrency protection |
| Changing currency `minor_digits` directly | All historical balances are misinterpreted | Metadata versioning/migration with reconciliation |

---

## 23. Practice Exercises

### Exercise 1 — Reading Precision and Scale

For `NUMERIC(12,2)`:

1. What is the maximum number of integer digits?
2. Is `9999999999.99` valid?
3. Is `10000000000.00` valid?
4. How does PostgreSQL handle `12.345` when cast to `NUMERIC(12,2)`?
5. Why do the minus sign and decimal point not count toward precision?

### Exercise 2 — NUMERIC vs. DOUBLE PRECISION

Run:

```sql
SELECT
    (0.1::NUMERIC + 0.2::NUMERIC) = 0.3::NUMERIC
        AS numeric_equal,
    (0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION)
        = 0.3::DOUBLE PRECISION AS floating_equal;
```

Explain why the two results can differ, and why you should not rely on float `=` comparisons for settled monetary amounts.

### Exercise 3 — BIGINT in Cents

Given `amount_cents = 1599`:

1. What is the corresponding USD value?
2. After adding 250 cents, what is the new integer?
3. Write SQL using `NUMERIC` to display it with two decimal places.
4. If the same integer 1599 were recorded for VND with scale 0, what VND amount does it represent?

### Exercise 4 — Line-Level vs. Total-Level Rounding

Compute 10% tax on two lines priced at 0.05 USD each. Compare:

- Rounding tax per line to 2 decimal places and then summing.
- Summing the base first, computing tax, and rounding once.

Why are the two results unequal? Who must decide which policy applies?

### Exercise 5 — Unit Price with Four Decimal Places

A product has `quantity = 100`, `unit_price = 0.0150 USD`.

Compute:

```sql
SELECT
    ROUND(0.0150::NUMERIC, 2) * 100
        AS rounded_price_first,
    ROUND(0.0150::NUMERIC * 100, 2)
        AS rounded_total;
```

Explain why storing unit prices directly in `NUMERIC(18,2)` can distort the total amount.

### Exercise 6 — Multi-Currency Table Design

Using `money_lab.currency_units` and `money_lab.wallets`, insert a JPY wallet with `balance_minor = 3500` and a USD wallet with `balance_minor = 3500`.

Write SQL to display each wallet's major amount, group totals by currency, and explain why the two `3500` integers must not be summed directly.

### Exercise 7 — Validating Input Before Casting

Suppose an API receives USD amounts as strings:

```text
"19.99"
"19.999"
"0"
"-1.00"
"abc"
```

If policy requires **non-negative, at most 2 decimal places, dot decimal format**, identify the valid values. Why is defining a `NUMERIC(18,2)` column alone insufficient to block `19.999`?

### Exercise 8 — The MONEY Type

Run:

```sql
SHOW lc_monetary;
SELECT 10.25::MONEY AS sample_money;
```

Explain why output may differ across environments with different locales. Does the `MONEY` type automatically distinguish 10.25 USD from 10.25 EUR?

### Exercise 9 — Java BigDecimal

Compare:

```java
new BigDecimal(0.1)
new BigDecimal("0.1")
BigDecimal.valueOf(0.1)
```

Explain which form preserves the exact intended decimal string and why you should not run a chain of `double` operations before constructing a `BigDecimal` for money.

### Exercise 10 — Checking Type Selection for Exchange Rates

Suppose a (synthetic) exchange rate is `0.0001234567`. Compare:

```sql
SELECT
    0.0001234567::NUMERIC(18,2) AS badly_scaled_rate,
    0.0001234567::NUMERIC(18,10) AS better_scaled_rate;
```

Why is `NUMERIC(18,2)` suitable for a final USD amount yet unsuitable for storing exchange rates in this scenario?

### Exercise 11 — Money Transfer Transaction

Design a workflow to transfer 3000 cents between two USD wallets:

- Verify both wallets use the same currency.
- Verify sufficient funds.
- Debit/credit within the same transaction.
- Verify updated row counts.
- Record a unique request key to prevent duplicate retries.
- Roll back if any step fails.

Explain why `CHECK(balance_minor >= 0)` alone is not enough to guarantee the combined balance of the two wallets is conserved.

### Exercise 12 — Choosing a Storage Model

A system has:

1. Product list prices in USD that can be less than 0.01 USD per unit.
2. Final payment amounts in cents.
3. Exchange rates with 10 decimal places.
4. Currency codes and scales varying by currency.
5. Total reports grouped by currency.

Propose a data type for each component, the rounding point, and a validation rule preventing amounts of different currencies from being summed together.

---

## 24. Checklist Before Shipping Monetary Data Types to Production

| Design Question | Decision Required |
| --- | --- |
| What kind of monetary value is it? | Price, balance, tax, fee, refund, ledger entry, exchange rate |
| Major units or minor units? | Direct `NUMERIC` or `BIGINT` in minor units |
| Where is the currency stored? | Currency code column or foreign key to currency metadata |
| What is the right scale? | Per currency and per field semantics |
| Are sub-payment fractional digits needed? | Larger scale for unit prices/intermediate calculations |
| Maximum numeric range? | Choose appropriate precision, account for overflow |
| Are negative numbers or zero allowed? | Specific `CHECK` constraints per transaction type |
| At which step does rounding occur? | Line, total, tax, fee, conversion, payment |
| Which rounding mode? | Per contract and regulations; consistent across backend/database |
| Must excessive decimal inputs be rejected? | Validate before casting/rounding |
| What types do APIs/drivers use? | BigDecimal, decimal string, or integer minor units |
| Are JavaScript systems involved? | Safe integer limits, how large numbers are serialized |
| Is currency conversion required? | Rate, timestamp, pair, rounding, snapshot |
| Are there multi-step transactions? | Atomic updates, constraints, concurrency, idempotency |
| Is there legacy data? | Migration and reconciliation by currency/batch |
| Are boundary cases tested? | Rounding ties, negatives, overflow, NULLs, invalid inputs |
| Are report totals verified? | Never SUM mixed currencies; reconcile ledger and settlement |

## Conclusion

PostgreSQL provides solid tools for storing monetary data accurately, yet **no single data type solves every financial problem automatically**.

- **`NUMERIC(p,s)`** suits decimal numbers needing exact decimal precision; choose precision/scale according to the quantity and remember that inputs may be rounded when cast to scale.
- **`BIGINT` minor units** suits settled amounts in the smallest currency unit, provided currency and scale are uniformly defined and overflow is controlled.
- **`MONEY`** exists and is useful in certain contexts, but its locale sensitivity and fixed scale make it suboptimal as a default for multi-currency systems.
- **`REAL`/`DOUBLE PRECISION`** do not guarantee exact representation of decimal fractions like `0.1`, so they are generally not used for monetary amounts requiring unit-level reconciliation.
- **Rounding, exchange rates, taxes, currencies, and transactions** are business rules requiring explicit design even when data types are chosen accurately.

A sound design stores **value + unit**, retains sufficient precision in intermediate steps, rounds at the right moment, validates inputs before type conversion, and uses transactions alongside constraints to safeguard monetary changes. With those in place, PostgreSQL becomes a reliable foundation for financial calculations without conflating arithmetic precision with overall business correctness.
