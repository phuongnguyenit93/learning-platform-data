# decimal, float, double, and Monetary Data in Apache Cassandra

In Apache Cassandra, the three types `decimal`, `float`, and `double` can all store values with fractional parts, but they **do not share the same semantics regarding precision**. `decimal` represents decimal numbers with arbitrary precision subject to resource limits, whereas `float` and `double` are IEEE 754 **binary** floating-point numbers subject to rounding error. This distinction is especially critical for **prices, taxes, balances, exchange rates, and reconciliation**.

This lesson belongs to the **Data Types** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module. The module's goal is to understand Cassandra as a distributed wide-column database—choosing partition keys, designing query-driven tables, read/write consistency levels, replication, compaction, repair, and connecting from Java. Within that context, choosing numeric types is part of the data contract: **the numeric type must preserve business semantics, while the keys and table must serve the intended queries**.

## 1. Quick Comparison Table

| Criterion | `decimal` | `float` | `double` |
|---|---|---|---|
| Numeric model | Exact decimal, variable precision | IEEE 754 binary32 | IEEE 754 binary64 |
| Base value size | Varies with value and scale | 4 bytes | 8 bytes |
| Precision | Preserves the exact decimal represented, within practical resource limits | ~6–9 significant decimal digits | ~15–17 significant decimal digits |
| Is `0.1` represented exactly? | Yes | No | No |
| Java Driver 4.x | `BigDecimal` | `float`/`Float` | `double`/`Double` |
| Strengths | Monetary calculations, taxes, rates following decimal rules | Measurements/telemetry needing space savings where approximation is acceptable | Scientific computing, coordinates, statistics needing higher approximate precision |
| Pitfalls to avoid | Does not automatically enforce scale, rounding mode, or business bounds | Precision error, digit loss at large magnitudes | Precision error still exists; cannot replace exact monetary amounts |

**Do not interpret "double is twice as precise as float" as "double is completely exact."** Both have a finite set of representable numbers. `double` usually gives a closer approximation, yet still fails to preserve every decimal fraction exactly.

Other types may be better suited for related data:

- `bigint`: monetary amounts converted into **minor units** as 64-bit integers, e.g., 19.90 USD as 1,990 cents when currency rules permit.
- `int`, `bigint`: measurements **scaled by a fixed factor** before storage, e.g., 23.875 °C as 23,875 millidegrees Celsius.
- `varint`: integers exceeding 64 bits; holds no fractional part.
- `text`: currency codes like `USD`, `VND`, or transaction identifiers with leading zeros.

## 2. Understanding the Difference Between Decimal and Floating-Point Numbers

### 2.1. `decimal`: Exact Decimal Values

A decimal number can be interpreted in terms of two components:

\[
\text{value} = \text{unscaled integer} \times 10^{-\text{scale}}
\]

For example, 19.90 is represented by the unscaled integer 1990 and a scale of 2. Java's `BigDecimal` uses the corresponding **unscaled value + scale** model; CQL `decimal` uses a variable-precision decimal type.

Key points to remember:

- Storing `19.90` as `decimal` preserves that exact decimal value rather than a base-2 approximation.
- CQL declares **`decimal`**, not `decimal(18, 2)` as in some relational DBMSs. Cassandra **does not automatically enforce an 18-digit cap or a scale of 2**.
- A rule like "every USD amount must have at most two decimal places" must be **enforced in the application/data contract**.
- `decimal` does not have "infinite" memory or speed; very long numbers increase storage footprint and computation cost.

The following example represents the same numeric value with different scales:

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("19.9");   // unscaled = 199, scale = 1
BigDecimal b = new BigDecimal("19.90");  // unscaled = 1990, scale = 2

System.out.println(a.compareTo(b) == 0); // true: numeric values are equal
System.out.println(a.equals(b));         // false: scales differ
~~~

When comparing **monetary values**, you typically need `compareTo()` or consistent scale normalization; never blindly call `equals()` when data may carry different scales.

### 2.2. `float` and `double`: Exact in Binary, Approximate in Decimal

IEEE 754 stores numbers as a sign, a significand, and a binary exponent. A fraction such as \(1/2\) or \(1/8\) has a finite binary representation, whereas \(1/10\) does not. Consequently, `0.1` can only be rounded to the nearest representable `float` or `double`.

~~~java
double sumDouble = 0.1 + 0.2;
System.out.println(sumDouble);              // 0.30000000000000004
System.out.println(sumDouble == 0.3);       // false

float sumFloat = 0.1f + 0.2f;
System.out.println(sumFloat);               // often prints 0.3
System.out.println(sumFloat == 0.3f);       // may evaluate to true in this case

BigDecimal sumDecimal = new BigDecimal("0.1")
    .add(new BigDecimal("0.2"));
System.out.println(sumDecimal);             // 0.3
~~~

Sometimes `float` *displays* a "clean" result, but that is rounded string formatting—it does not mean decimal arithmetic was performed exactly. Never infer the safety of a financial calculation from the printed output of a single example.

Useful boundary limits:

| Property | `float` | `double` |
|---|---:|---:|
| Effective significand bits (including implicit bit) | 24 | 53 |
| Range of consecutive integers exactly representable around 0 | Up to \(2^{24}=16,777,216\) | Up to \(2^{53}=9,007,199,254,740,992\) |
| Beyond that threshold | Consecutive integers become indistinguishable | Consecutive integers become indistinguishable |

For example, casting the integer 16,777,217 to a Java `float` can yield 16,777,216. This affects equality checks, large aggregations, and intermediate JSON encoding. For exact integers, use an appropriate integer type; for money, use `decimal` or minor-unit integer storage.

### 2.3. Precision vs. Scale and Rounding Rules

Three concepts play distinct roles:

- **Precision**: total number of significant digits in a value. In Java `BigDecimal`, `new BigDecimal("123.45").precision()` equals 5.
- **Scale**: number of digits to the right of the decimal point in the `BigDecimal` model. For 123.45, the scale is 2.
- **Rounding mode**: the rule for choosing a result when digits must be dropped: `HALF_UP`, `HALF_EVEN`, `DOWN`, `CEILING`, etc. The rule is determined by business policy.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("10.005");

System.out.println(amount.setScale(2, RoundingMode.HALF_UP));   // 10.01
System.out.println(amount.setScale(2, RoundingMode.HALF_EVEN)); // 10.00
~~~

Both results can be valid under different calculation contracts. Cassandra knows nothing about tax policies, accounting rules, or how to handle fractional cents: **the application must standardize the rounding mode, when rounding occurs, and the currency unit**.

## 3. Which Type to Choose for Monetary Data?

### 3.1. Strategy A: `decimal` + Currency Code

Use this when you need to represent monetary amounts explicitly as decimals—such as a unit price of 19.90, a tax rate of 0.075, multi-digit exchange rates, or amounts handled with business-defined scales.

~~~cql
CREATE TABLE prices_by_sku_currency (
    sku text,
    currency_code text,
    effective_from timestamp,
    unit_price decimal,
    tax_rate decimal,
    PRIMARY KEY ((sku, currency_code), effective_from)
) WITH CLUSTERING ORDER BY (effective_from DESC);

INSERT INTO prices_by_sku_currency (
    sku, currency_code, effective_from, unit_price, tax_rate
) VALUES (
    'SKU-001', 'USD', '2026-11-21T00:00:00Z', 19.90, 0.075
);

SELECT effective_from, unit_price, tax_rate
FROM prices_by_sku_currency
WHERE sku = 'SKU-001' AND currency_code = 'USD'
LIMIT 1;
~~~

Here:

- `unit_price decimal` stores the exact unit price 19.90; `tax_rate decimal` stores the 7.5% rate in exact decimal form.
- `currency_code text` is mandatory to interpret the money; the number 19.90 alone is **insufficient** to indicate USD, EUR, or another unit.
- The partition key `(sku, currency_code)` groups price history by SKU and currency; `effective_from DESC` supports fetching the latest price from a single partition.
- If a SKU has an unbounded price history, you must account for partition size, retention duration, and data splitting under heavy load. That is a query-driven table design problem; `decimal` does not solve key design.

**Do not** concatenate strings for tax math or store money as `"19.90"` solely to retain trailing zeros. Strings are suited for **input/output formatting**, whereas `BigDecimal`/`decimal` are suited for **computed numeric values**.

### 3.2. Strategy B: `bigint` in Minor Currency Units

In many payment systems, instead of storing 19.90 USD as a decimal, you can store **1,990 cents** as a `bigint`. Values are counted in integers, so addition and subtraction in minor units have zero floating-point error.

~~~cql
CREATE TABLE ledger_entries_by_account_currency_day (
    account_id uuid,
    currency_code text,
    entry_day date,
    entry_at timestamp,
    entry_id uuid,
    amount_minor bigint,
    description text,
    PRIMARY KEY (
        (account_id, currency_code, entry_day),
        entry_at, entry_id
    )
) WITH CLUSTERING ORDER BY (entry_at DESC, entry_id ASC);
~~~

For instance, a credit of 19.90 USD might be `amount_minor = 1990`, while a debit of 5.00 USD might be `amount_minor = -500`. Business logic must define what positive/negative signs mean and whether the value includes taxes or fees.

**Not every currency has two decimal places.** The number of minor-unit digits depends on the currency code and applicable business standard; many currencies have zero fractional digits, and some have three. Look up the scale from a system-controlled currency table/policy rather than blindly multiplying every amount by 100.

In Java, convert with explicit validation:

~~~java
import java.math.BigDecimal;

BigDecimal usdAmount = new BigDecimal("19.90");
int usdMinorDigits = 2; // Per system currency convention.

long cents = usdAmount
    .movePointRight(usdMinorDigits)
    .longValueExact();

System.out.println(cents); // 1990
~~~

`longValueExact()` throws an error if the conversion leaves a fractional part beyond the minor unit or overflows 64 bits. This catches invalid data, such as a request to store 19.999 USD in a system that only accepts cents without a rounding rule.

**Strengths** of `bigint` minor units: consistent addition/subtraction, fixed size, and straightforward reconciliation once minor units are standardized. **Limitations**: cannot directly store multi-digit exchange rates, sub-unit fractional amounts, or totals exceeding 64-bit bounds. Those cases require distinct representations per data type.

### 3.3. Comparing the Two Monetary Strategies

| Design Question | `decimal` | `bigint` minor units |
|---|---|---|
| Price 19.90 USD | `19.90` | `1990` cents |
| Can it store an exchange rate like `0.000123456789`? | Yes, within application-accepted range and scale | Only if converted to a specifically defined integer unit |
| Scale rules | Application controls decimal scale | Application controls minor-unit digits per currency |
| Rounding risk | During calculations/converting results to target scale | When converting from decimal amounts to minor units |
| Range limits | Resource/representation dependent | 64-bit signed integer |
| Choose when | Prices, taxes, rates, exact decimal quantities | Settled transactions in minor units, monetary accumulations within 64-bit bounds |

For **a single monetary figure acting as the canonical data**, typically pick **one representation** and define conversion rules. Do not write both `amount_decimal` and `amount_minor` as independent sources of truth without a consistency enforcement mechanism; if they diverge, it is hard to tell which is right.

## 4. Why Not Use `float` or `double` for Money?

Suppose you need to sum millions of `0.01` values to compute a total. With `double`, tiny errors can accumulate during addition; accumulation strategy and operation order can even change the trailing digits. With `float`, the error can be larger due to fewer significand bits.

The real danger is not merely extra digits appearing in a UI: the exact same formula can produce **different boundary rounding results**, cause `==` comparisons to fail, or cause two services to compute slightly different penny amounts. Therefore:

1. **Never use `float`/`double` to store canonical values for money, prices, payables, taxes, or balances requiring reconciliation.**
2. Use `BigDecimal` from data parsing through calculations and binding to CQL `decimal`, or use `long` in minor units under explicit rules.
3. Compute taxes/fees/discounts with sufficient intermediate precision and then **round at a well-defined business step**, such as per invoice line item or at the invoice total. Those two policies can yield different results.
4. When splitting an amount across multiple parts, define a **remainder allocation rule**; three times 3.33 does not sum back to 10.00.

Example of splitting 10.00 USD among three people:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal total = new BigDecimal("10.00");
BigDecimal first = total.divide(
    BigDecimal.valueOf(3), 2, RoundingMode.DOWN
); // 3.33
BigDecimal second = first;                 // 3.33
BigDecimal third = total.subtract(first).subtract(second); // 3.34

System.out.println(first.add(second).add(third)); // 10.00
~~~

Who receives the remainder is a **business policy**, not a built-in Cassandra rule.

## 5. What Data Fits `float` and `double`?

Not every decimal number is money or requires exact reconciliation. `float` and `double` play an important role in telemetry, numerical analysis, and science.

| Data | Typically Suitable Type | Reason |
|---|---|---|
| Sensor temperature with ±0.1 °C tolerance | `float` | Physical measurement noise exceeds representational error |
| Geographic coordinates for geometric calculations | `double` | Requires higher approximate precision than `float` |
| Metrics, probabilities, model scores | `float` or `double` | Depends on required significant digits and algorithm |
| Lab measurements required to keep exact 4 decimal places by regulation | `decimal` or scaled integer | Easier to apply exact quantization rules |
| Product prices, invoices, taxes requiring reconciliation | `decimal` or `bigint` minor units | Must be exact under decimal/currency rules |
| Item quantities that are whole numbers | `int`/`bigint` | Avoids meaningless fractional values |

Example telemetry table designed for the query "fetch readings by device and hour":

~~~cql
CREATE TABLE telemetry_by_device_hour (
    device_id uuid,
    hour_bucket timestamp,
    measured_at timestamp,
    sample_id uuid,
    temperature_c float,
    latitude double,
    longitude double,
    PRIMARY KEY ((device_id, hour_bucket), measured_at, sample_id)
) WITH CLUSTERING ORDER BY (measured_at DESC, sample_id ASC);

SELECT measured_at, sample_id, temperature_c, latitude, longitude
FROM telemetry_by_device_hour
WHERE device_id = 123e4567-e89b-12d3-a456-426614174000
  AND hour_bucket = '2026-11-21T01:00:00Z'
LIMIT 100;
~~~

Here `float` fits approximate temperatures; `double` fits latitude/longitude requiring more significant digits. Both are **data columns**, while the partition key and clustering key are chosen to match the query pattern. If you need to find all readings inside a geographic region, you must design a separate access path; using `double` does not automatically provide spatial search.

**Input validation:** before writing measurements in Java, check `Float.isFinite(value)` or `Double.isFinite(value)` if the domain does not accept `NaN` or infinity. Special values and sensor faults must be handled per the data contract; never silently turn missing readings into `0`.

**Practical limitation:** if changes are very small relative to the current magnitude, `float` can lose the ability to distinguish consecutive samples. For example, adding `1` to a value above \(2^{24}\) may leave the stored `float` unchanged. For measurements needing exact fixed-step increments, consider storing scaled integers.

## 6. Java Driver 4.x: Mapping and Safe Read/Write Operations

With the Apache Cassandra Java Driver 4.x, common mappings are:

| CQL | Java | Prepared Statement | `Row` Getter |
|---|---|---|---|
| `decimal` | `BigDecimal` | `setBigDecimal(index, value)` | `getBigDecimal(column)` |
| `float` | `float` | `setFloat(index, value)` | `getFloat(column)` |
| `double` | `double` | `setDouble(index, value)` | `getDouble(column)` |
| `bigint` (minor currency units) | `long` | `setLong(index, value)` | `getLong(column)` |

### 6.1. Calculating Prices and Storing decimal

Assume `session` is a `CqlSession` already connected to the cluster and using the right keyspace. The snippet below writes an effective price and tax rate into `prices_by_sku_currency`:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;

// CqlSession session = ...; // Configured outside this example.

BigDecimal unitPrice = new BigDecimal("19.90");
BigDecimal taxRate = new BigDecimal("0.075"); // 7.5%
int quantity = 3;

// Use BigDecimal throughout the calculation.
BigDecimal subtotal = unitPrice.multiply(BigDecimal.valueOf(quantity));
BigDecimal tax = subtotal.multiply(taxRate)
    .setScale(2, RoundingMode.HALF_EVEN); // Example policy.
BigDecimal total = subtotal.add(tax);

System.out.println(subtotal); // 59.70
System.out.println(tax);      // 4.48
System.out.println(total);    // 64.18

PreparedStatement insertPrice = session.prepare(
    "INSERT INTO prices_by_sku_currency "
  + "(sku, currency_code, effective_from, unit_price, tax_rate) "
  + "VALUES (?, ?, ?, ?, ?)");

BoundStatement bound = insertPrice.boundStatementBuilder()
    .setString(0, "SKU-001")
    .setString(1, "USD")
    .setInstant(2, Instant.parse("2026-11-21T00:00:00Z"))
    .setBigDecimal(3, unitPrice)
    .setBigDecimal(4, taxRate)
    .build();

session.execute(bound);
~~~

Note: `total` in the example is computed in Java and is not automatically stored in the price table. If the business needs to persist invoices, build a **query-driven invoice table** with clear keys, currency metadata, finalized totals, and calculation provenance.

### 6.2. Reading Prices Back Without Converting to double

~~~java
import com.datastax.oss.driver.api.core.cql.Row;

PreparedStatement findLatest = session.prepare(
    "SELECT unit_price, tax_rate "
  + "FROM prices_by_sku_currency "
  + "WHERE sku = ? AND currency_code = ? LIMIT 1");

Row row = session.execute(
    findLatest.bind("SKU-001", "USD")
).one();

if (row != null && !row.isNull("unit_price")) {
    BigDecimal latestPrice = row.getBigDecimal("unit_price");
    // Keep as BigDecimal for downstream calculations; avoid latestPrice.doubleValue().
}
~~~

**Never construct a `BigDecimal` from a `double` that has already lost precision**:

~~~java
BigDecimal bad = new BigDecimal(0.1);         // Carries binary error of 0.1
BigDecimal good = new BigDecimal("0.1");      // Exact 0.1

double alreadyRounded = 0.1 + 0.2;
BigDecimal notRepaired = BigDecimal.valueOf(alreadyRounded);
// 0.30000000000000004: type conversion cannot recover the original data.
~~~

`BigDecimal.valueOf(0.1)` produces the decimal representation `0.1` because it converts the `double` to its string form first; however, if the `double` is already the **result of an imprecise calculation**, converting it to `BigDecimal` cannot recover the original ideal decimal value. Therefore, ingest money from strings or minor integer units and keep exact types throughout the entire flow.

### 6.3. Validating Scale at the Write Boundary

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

static BigDecimal requireTwoFractionDigits(BigDecimal amount) {
    // Only accepts values representable accurately with at most 2 decimal places.
    return amount.setScale(2, RoundingMode.UNNECESSARY);
}

BigDecimal valid = requireTwoFractionDigits(new BigDecimal("12.30"));

// requireTwoFractionDigits(new BigDecimal("12.345"))
// throws ArithmeticException, because rounding would be required.
~~~

This example helper applies only to a currency domain defined with scale = 2. For currencies with other scales, retrieve the expected value from business configuration. Applications can translate this exception into a clear validation error instead of silently truncating digits.

## 7. How Do Access Patterns in Cassandra Relate to Numeric Types?

The two data groups above have distinct access patterns:

1. **Price history:** look up by `sku + currency_code`, fetch the latest effective time → table `prices_by_sku_currency` with clustering `effective_from DESC`.
2. **Telemetry:** look up by `device_id + hour_bucket`, fetch recent samples → table `telemetry_by_device_hour` with clustering `measured_at DESC`.

`decimal` does not by itself enable querying "all products priced under 100 USD" across the cluster; nor does `double` make querying "all devices with temperature over 35 °C" efficient. Cassandra is designed to read by a **known partition key**, then apply valid conditions on clustering columns; other search patterns require a separate access model, index, or analytical engine evaluated for the workload.

If you frequently need to fetch orders by customer and date, design a table with the matching partition key; **the monetary amount is a non-key data column in the row**, chosen as `decimal` or `bigint` for numeric correctness. Using an amount as a partition key typically creates hard-to-control access patterns and does not solve customer lookups.

Do not use floating-point numbers as an "exact lookup key": because measurements involve rounding error, two seemingly equivalent values may not compare equal after conversion. If you must query by measurement buckets, model deterministic quantization buckets or keys under consistent rules with a matching query-driven table.

## 8. Retries, Consistency, and Reconciliation: Cassandra Does Not Round for the Application

Apache Cassandra is a distributed system: a write can succeed on some replicas even when the application receives a timeout. For monetary data, the following requirements must be designed independently of numeric types:

- **Idempotency:** retrying the same transaction must use the **same ID and primary key**. Generating a new `entry_id` on every retry can create duplicate rows for one transaction.
- **Read/write consistency:** consistency levels like `LOCAL_QUORUM` control how many replicas must acknowledge an operation, but **do not turn mutations across multiple partitions into an ACID financial transaction**.
- **Overwrites and concurrency:** two clients reading a balance, adding, and writing back can lose an update. `decimal` and `bigint` do not automatically provide atomic addition.
- **Counters:** the specialized `counter` type has different write/retry semantics and is unsuitable as a ledger requiring exact per-event reconciliation.
- **Event sourcing:** for financial workloads, you typically need to persist transaction records with stable identifiers, enforce business-level deduplication, and derive/aggregate balances through a controlled process.

Compaction manages SSTables and repair synchronizes replicas; **neither mechanism fixes monetary amounts miscalculated due to `double` or inconsistent rounding**. For data subject to retention or auditing, you must also evaluate TTL, retention policies, and deletion rules per business requirements.

A production financial ledger carries additional guarantees for transaction durability, duplicate prevention, and cross-account reconciliation. Cassandra can participate in such an architecture only with proper constraints and workflows; a table like `ledger_entries_by_account_currency_day` is a **query-design example**, not a complete ledger solution.

## 9. Common Mistakes When Using decimal, float, and double

| Mistake | Consequence | Solution |
|---|---|---|
| Storing `19.90` USD as `double` | Binary precision errors can appear in calculations | Use `decimal`/`BigDecimal` or `bigint` minor units |
| Using `new BigDecimal(0.1)` for money | Introduces the `double` approximation into `BigDecimal` | Parse decimal strings or integer minor units |
| Assuming `decimal` caps at two decimal places | Allows storing `19.999` even if business only allows cents | Validate scale and rounding at the write boundary |
| Rounding after each step while another service rounds the total | Reconciliation mismatch between services | Define rounding timing and policy explicitly |
| Converting every currency by a factor of 100 | Wrong values for currencies whose minor-unit scale is not 2 | Use per-currency minor-unit rules |
| Calling `BigDecimal.doubleValue()` and continuing math | Destroys previously preserved precision | Keep `BigDecimal` across the entire pipeline |
| Updating a `bigint` balance via concurrent read-modify-write | Lost updates possible | Design event/idempotency or proper concurrency control |
| Trying to query price/metric across partitions by changing column type | Queries still miss the partition key | Design a query table or evaluated index per workload |
| Assuming old `double` records can be cast to `decimal` to recover original values | Historical rounding errors remain | Backfill from original source data and reconciliation rules |
| Using `float` to store large exact integers | Consecutive integers may round to the same value | Use `int`/`bigint`/`varint` |

## 10. Schema Migration When float/double Was Previously Used for Money

A system that previously stored monetary amounts in `float` or `double` may need to migrate to `decimal` or `bigint` minor units. A sound approach includes:

1. **Define monetary rules**: currency codes, scales, taxes/fees, line-item vs. invoice-total rounding, time zones for cutoff dates, and reversal handling.
2. **Identify authoritative source data**: original invoices, source events with exact amounts, or payment gateway records. Do not assume converting historical `double` values to `BigDecimal` recovers the original intent.
3. **Create a new query-aligned table/write path** with the right types rather than assuming an in-place `ALTER` can safely convert populated columns.
4. **Update Java codecs and validation**: parse from strings/integer units, use `setBigDecimal` or `setLong`, and validate scale, overflow, and currency.
5. **Backfill and reconcile**: verify transaction counts, totals by period and currency, boundary cases, refunds, and duplicate IDs; execute a controlled read/write cutover.
6. **Maintain retry idempotency** during transition and verify no services still write to the old schema/codec before decommissioning.

The hardest part is usually **recovering financial semantics**, not column-alteration syntax. A `double` value near 19.90 may have gone through multiple different rounding steps; the migration must define valid canonical values for reconciliation.

## 11. Self-Check Exercises

**Exercise 1 — Choosing a type.** A service ingests sensor temperatures with ±0.5 °C error at 100,000 samples/second for trend analytics only. Should you prefer `float` or `decimal`? Explain based on required precision and data cost.

**Hint:** `float` is usually sufficient for this sensor resolution; benchmark and confirm the measurement range before finalizing. Partitioning keys by device/time still determine how efficiently recent samples are read.

**Exercise 2 — Catching rounding truncation.** A price from an API arrives as the string `"12.345"`, and the currency has two minor-unit digits. What should you do before writing to `bigint`?

**Hint:** apply or reject according to the agreed rounding policy; never silently truncate to 1234 cents. If policy forbids sub-cent fractions, use `setScale(2, UNNECESSARY)` followed by `movePointRight(2).longValueExact()`.

**Exercise 3 — Identifying numeric provenance.** Java computes `double result = 0.1 + 0.2;` and then creates `BigDecimal.valueOf(result)`. Is the new value strictly equal to `new BigDecimal("0.3")`?

**Answer:** no; the intermediate result already contains floating-point error and cannot be repaired simply by changing types.

**Exercise 4 — Fixing a query.** A table stores `customer_id` as partition key, `paid_at` as clustering key, and `amount decimal` as a data column. If you want to query all transactions with `amount > 100` across all customers, does changing `amount` to `double` solve it?

**Answer:** no. You need an access path/data model built for that query, or an index/analytical system proven suitable for the workload.

## 12. Checklist Before Finalizing Numeric Types

- [ ] Is the value **money/exact data** or a **measurement where approximation is acceptable**?
- [ ] For money, have **currency code, scale, minor unit, rounding policy, and rounding step** been defined?
- [ ] If using `decimal`, does the application validate scale/range rather than assuming Cassandra enforces it?
- [ ] If using `bigint` minor units, are `longValueExact()`, conversion factors, and 64-bit overflow checked?
- [ ] Does Java construct `BigDecimal` from **exact numeric strings** and preserve that type through all monetary math?
- [ ] If using `float`/`double`, have acceptable error tolerances, measurement ranges, and abnormal values (`NaN`/infinity) been verified?
- [ ] Do column types match Java Driver methods (`setBigDecimal`/`setFloat`/`setDouble`/`setLong`)?
- [ ] Do the table's partition key and clustering columns support **actual queries** and bound partition growth?
- [ ] Are retries, transaction IDs, concurrent updates, and reconciliation handled **independently of numeric type selection**?
- [ ] If legacy floating-point data exists, are authoritative sources and a migration/reconciliation plan in place?

**Remember:** choose **`decimal`** when exact decimal values must be preserved—especially for prices, exchange rates, and taxes; choose **`bigint` in minor currency units** when the domain has clear integer units; use **`float`/`double`** for measurements or calculations that tolerate approximation. In Cassandra, **numeric precision** and **proper distributed query patterns** must be designed together; replication, consistency, and repair cannot substitute for this decision.
