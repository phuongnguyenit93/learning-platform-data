# Currency, Measured Quantities, and Pairing Values with Units

A number does not speak for itself. The value `100` could be 100,000 VND, 100 USD, 100 grams, 100 kilograms, 100 percent, or 100 items. Storing numbers without attaching units and context allows data to be added, compared, or converted incorrectly without the system ever reporting an error.

In **data modeling**, currency and measured quantities must be treated as typed, unit-aware values. Monetary amounts always go with a currency code; physical measurements always go with a measurement unit and a physical dimension. A selling price per kilogram differs from a selling price per piece. Mass cannot be added directly to volume. When converting currencies or units, the system must also store the rules, exchange rates or conversion factors, effective timestamps, and rounding methods.

This lesson explains how to model monetary values and measured quantities, how to protect consistency with schemas and business rules, and common scenarios in sales, warehousing, and data analytics.

## 1. Why must values be paired with units?

Imagine two products with weights of `2` and `500`, respectively. If you only store these two numbers, a reader cannot tell whether the first weighs 2 kg or 2 g, or whether the second weighs 500 g or 500 kg. Similarly, an amount of `1,000` can represent many different currencies.

A measured value should be understood as a pair:

**Numeric value + measurement unit**

A monetary amount should be understood as:

**Monetary amount + currency code**

In some cases, additional context is required:

- Selling price: monetary amount, currency, pricing unit, and effective timestamp.
- Mass: value, unit, measured object, and measurement timestamp.
- Exchange rate: currency pair, conversion direction, rate, source, and timestamp.
- Temperature: value, scale, and measurement location/timestamp.
- Speed: value, length unit, and time unit.

A design that stores numbers alone without units makes meaning dependent on documentation or implicit conventions in application code. Implicit conventions easily break when new systems, imported data, or reports built by another team are introduced.

### 1.1. Mistakes caused by missing units

- Adding 2 kg and 500 g without converting.
- Comparing 1 liter of water with 900 grams of water as if both numbers shared the same dimension.
- Displaying a price of 20,000 without knowing whether it is VND, USD, or price per piece.
- Summing USD and VND revenue in the same report.
- Converting 100 degrees Fahrenheit to Celsius by multiplying only by a factor, omitting the offset.
- Rounding at each conversion step, causing the total amount to diverge from accounting rules.

These errors are not merely UI bugs. They stem from a data model that fails to capture the value's type, unit, and context.

## 2. Modeling currency

### 2.1. Monetary amounts always accompany a currency code

Do not store an `amount` column without `currency` information. The same numeric value can carry different meanings:

| Value | Currency code | Meaning |
|---:|---|---|
| 100 | VND | 100 Vietnamese dong |
| 100 | USD | 100 US dollars |
| 100 | JPY | 100 Japanese yen |
| 100 | EUR | 100 euros |

Currency units should be represented by a standard code, typically the three-letter ISO 4217 code, rather than storing only display symbols like `$`, `¥`, or `€`. One symbol may be used by multiple currencies; the currency code disambiguates the currency.

Currency names and symbols used for UI display can vary by language or locale. They do not replace currency codes in transaction data.

### 2.2. Do not use binary floating-point numbers for money

Floating-point types such as FLOAT or DOUBLE typically represent numbers in approximate binary form. Many ordinary decimal fractions cannot be represented exactly in this form. When performing repeated additions, multiplications, or divisions, small errors can accumulate and affect monetary totals.

For monetary values and financial calculations, commonly use:

- Exact decimal types such as NUMERIC or DECIMAL.
- Integers in the currency's smallest minor unit, if suitable for the business workflow.

For example, 125,000 VND can be stored as integer `125000` if the storage unit is dong. 12.34 USD can be stored as `1234` cents if the system specifies two decimal digits for USD. Integer storage must accompany the currency code and rules determining the number of minor digits.

Do not assume every currency has two decimal places. Some currency codes have no decimal part, some use three decimal digits, and some have special business handling rules. Manage currency metadata from an authoritative source and validate by currency code.

### 2.3. Choosing NUMERIC or minor units?

| Storage approach | Suitable when | Considerations |
|---|---|---|
| NUMERIC/DECIMAL | Unit prices, taxes, discounts, or calculations requiring decimal precision | Pick sufficient precision/scale; define when rounding occurs |
| Integer minor units | Finalized amounts for settlement or ledger posting | Must know currency and minor-unit digit count |
| FLOAT/DOUBLE | Simulations or real-number analytics not requiring monetary exactness | Never use as canonical representation of reconcilable money |

A system may use NUMERIC for unit prices and intermediate values, then convert to integer minor units when finalizing receivables or payments. Clearly define the rounding point and store the finalized value for reconciliation.

Do not store both monetary representations simultaneously without a synchronization rule. If storing both `amount_decimal` and `amount_minor_units`, designate one field as the source of truth and verify they always match.

### 2.4. Precision, scale, and rounding

Precision is the total number of digits that can be represented; scale is the number of digits after the decimal point. Choosing a NUMERIC type requires considering:

- Expected maximum value.
- Decimal places of unit prices.
- Whether quantities can be fractional.
- How many digits result from multiplying unit price by quantity.
- Required intermediate precision for taxes, discounts, and exchange rates.
- Which rounding rule applies to the final result.

For example, a unit price of 12,345.6789 VND per kg multiplied by 0.375 kg yields an amount with a fractional part. The system must define whether rounding occurs at line level, invoice level, or payment-total level. Different rounding strategies can produce different final totals.

Rounding rules can include:

- Round to nearest, specifying tie-breaking direction when exactly halfway.
- Round up or down per policy.
- Round per line item or only after summing.
- Handling negative numbers for refunds or adjustments.
- Valid decimal places per currency and transaction type.

Do not let each screen or service choose its own rounding behavior. Rules must be standardized and tested with boundary examples.

### 2.5. Distinguishing amounts, unit prices, and rates

The following values can all be NUMERIC yet carry different meanings:

- 100,000 VND: monetary amount.
- 100,000 VND per piece: unit price.
- 10%: percentage rate.
- 1.08: multiplier factor.
- 1.08 USD per EUR: exchange rate in a defined direction.

Do not use generic names like `value` or `rate` lacking units and semantic direction. For example, names like `price_per_kg`, `discount_percent`, `tax_rate`, and `exchange_rate_quote_per_base` are much clearer to readers.

### 2.6. Modeling currency metadata

A currency table can store codes and minor-unit digit counts:

~~~sql
CREATE TABLE currencies (
    currency_code CHAR(3) PRIMARY KEY,
    currency_name VARCHAR(100) NOT NULL,
    minor_unit_digits SMALLINT NOT NULL
        CHECK (minor_unit_digits BETWEEN 0 AND 4),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE payment_postings (
    payment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    currency_code CHAR(3) NOT NULL
        REFERENCES currencies(currency_code),
    minor_unit_digits_at_posting SMALLINT NOT NULL
        CHECK (minor_unit_digits_at_posting BETWEEN 0 AND 4),
    amount_minor_units BIGINT NOT NULL
        CHECK (amount_minor_units >= 0),
    posting_kind VARCHAR(20) NOT NULL
        CHECK (posting_kind IN ('capture', 'refund', 'adjustment')),
    posted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

In this example, `payment_postings` stores finalized amounts in minor units and snapshots the decimal digit count applied at posting time. When creating a posting, the transaction reads `minor_unit_digits` from the `currencies` catalog and saves this snapshot; the application should not supply an arbitrary value. This prevents historical data from being reinterpreted if currency metadata is updated. For display, the application uses `minor_unit_digits_at_posting` to place the decimal separator and format the value. Here the `currencies` table only contains currencies supported for payment with defined minor-unit digit counts. Real data should be loaded and managed from an authoritative currency catalog; never infer digit counts from symbols. Amounts are stored as non-negative magnitudes; `posting_kind` indicates capture, refund, or adjustment. A ledger may use its own sign convention, provided it is consistent.

If high-precision intermediate monetary values must be stored, NUMERIC and `currency_code` can be used:

~~~sql
CREATE TABLE price_quotes (
    price_quote_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    currency_code CHAR(3) NOT NULL
        REFERENCES currencies(currency_code),
    amount NUMERIC(24, 10) NOT NULL CHECK (amount >= 0),
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);
~~~

This example stores high-precision decimal values for calculations. When a price is used in a finalized transaction, apply rounding rules and record the final amount according to the system's accounting policy.

## 3. Modeling measured quantities

### 3.1. Measurements require units

A physical quantity is not just a number. A measurement should contain:

- Numeric value.
- Measurement unit.
- Dimension or quantity kind.
- Measured object.
- Measurement timestamp if the value changes over time.
- Measurement method or device if traceability is needed.

For example, the weight of a package is 12.5 kg. Warehouse temperature is 4 °C at 08:30. Product length is 120 cm. Storing only `12.5`, `4`, or `120` leaves the data lacking the context needed for interpretation.

### 3.2. Dimensions and measurement units

Units belong to a dimension. Some examples:

| Dimension | Example units | Conversion relationship |
|---|---|---|
| Length | m, cm, mm, km | 1 m = 100 cm |
| Mass | kg, g, mg | 1 kg = 1,000 g |
| Volume | L, mL, m³ | 1 L = 1,000 mL |
| Time | s, min, h | 1 h = 3,600 seconds |
| Area | m², cm² | 1 m² = 10,000 cm² |
| Temperature | K, °C, °F | Involves both factor and offset |
| Speed | m/s, km/h | Combines length and time dimensions |

Two values can only be compared or added directly when they share the same dimension and have been converted to the same unit or standard representation.

You cannot add 3 kg to 2 liters because mass and volume are two different dimensions. Converting volume to mass requires additional information about substance density and relevant conditions; there is no universal factor applicable to all substances.

### 3.3. Base units and standard representations

For many quantities, a system can select an internal base unit for storage or calculation. Examples:

- Length standardized in meters.
- Mass standardized in kilograms.
- Time standardized in seconds.
- Volume standardized in cubic meters.

Storing or converting to a base unit supports consistent comparison and aggregation. However, still retain the original unit when it matters to the person entering data, product labels, documents, or traceability.

For example, a user enters `250 cm`. The system can normalize to `2.5 m` for calculations, yet needs the originally entered value and original unit if it wants to display the value exactly as declared by the user.

### 3.4. Linear conversions and offset conversions

Many units convert via a multiplicative factor:

**base value = original value × factor**

Examples:

- 1 kg = 1,000 g.
- 1 km = 1,000 m.
- 1 hour = 3,600 seconds.

However, not every conversion is pure multiplication. Celsius and Fahrenheit temperatures require both a factor and an offset:

**°F = °C × 9/5 + 32**

**K = °C + 273.15**

Therefore, a general conversion table must describe the transformation type or use dedicated logic for units with offsets. A single `factor` column cannot represent every conversion.

### 3.5. Context-dependent units

Some units or conversions require additional context:

- Volume to mass requires density.
- Dimensions converted to billable dimensional weight require carrier rules.
- Packaging units like cartons, boxes, or pallets depend on inner item counts.
- Energy or power units may depend on measurement conditions.

Do not hardcode a global conversion factor if the factor varies by product, batch, temperature, or partner rules. When conversion depends on context, store the context data and the applied rule version.

## 4. Modeling units and quantities in the schema

### 4.1. Dimension and unit catalogs

Units can be managed via a catalog with stable codes, dimensions, and conversion rules to the base unit:

~~~sql
CREATE TABLE measure_dimensions (
    dimension_code VARCHAR(30) PRIMARY KEY,
    dimension_name VARCHAR(100) NOT NULL
);

CREATE TABLE measure_units (
    unit_code VARCHAR(20) PRIMARY KEY,
    dimension_code VARCHAR(30) NOT NULL
        REFERENCES measure_dimensions(dimension_code),
    unit_symbol VARCHAR(20) NOT NULL,
    factor_to_base NUMERIC(30, 15) NOT NULL
        CHECK (factor_to_base > 0),
    offset_to_base NUMERIC(30, 15) NOT NULL DEFAULT 0,
    UNIQUE (unit_code, dimension_code)
);
~~~

The conversion convention of this table is:

**base value = unit value × factor_to_base + offset_to_base**

This convention must be applied consistently and a base unit defined for each dimension. For units with repeating decimal factors or high-precision needs, store factors as exact fractions or use sufficiently high precision per business domain rather than rounding arbitrarily.

### 4.2. Pairing units with measured attributes

Suppose a product has attributes like weight, length, and volume. You can predefine which attribute belongs to which dimension:

The example below assumes the system already has a `products` table and the dimension/unit catalog tables created beforehand.

~~~sql
CREATE TABLE measurement_attributes (
    attribute_code VARCHAR(40) PRIMARY KEY,
    dimension_code VARCHAR(30) NOT NULL
        REFERENCES measure_dimensions(dimension_code),
    UNIQUE (attribute_code, dimension_code)
);

CREATE TABLE product_measurements (
    product_id BIGINT NOT NULL REFERENCES products(id),
    attribute_code VARCHAR(40) NOT NULL,
    dimension_code VARCHAR(30) NOT NULL,
    measured_value NUMERIC(24, 10) NOT NULL,
    unit_code VARCHAR(20) NOT NULL,
    measured_at TIMESTAMPTZ,
    PRIMARY KEY (product_id, attribute_code),
    FOREIGN KEY (attribute_code, dimension_code)
        REFERENCES measurement_attributes(attribute_code, dimension_code),
    FOREIGN KEY (unit_code, dimension_code)
        REFERENCES measure_units(unit_code, dimension_code)
);
~~~

The two composite foreign keys ensure that the attribute and unit belong to the same dimension. For example, if `attribute_code` is `net_weight` with dimension `MASS`, you cannot attach unit `L` belonging to dimension `VOLUME`.

This example assumes each product has one current value per attribute. If multiple measurements, multiple measurement methods, or batch-level history are required, use a separate `measurement_id` and store each measurement rather than using `(product_id, attribute_code)` as the primary key.

### 4.3. Display units and calculation units

Users may enter values in familiar units while the system additionally stores base-unit values for computation. Determine:

- Must the original entered value and original unit be stored?
- Is the base value computed on entry or on query?
- When conversion-factor catalogs change, is historical data recalculated?
- Which unit is used in contracts, product labels, or reports?
- Must display decimal places vary by unit?

If a measurement serves as evidence or inspection data, retain the original value, original unit, timestamp, and measurement method. The base value can be derived data computed under the stored rule version.

### 4.4. Validating values

Some attributes have value domains:

- Goods weight must be greater than or equal to zero.
- Packaging length must be greater than zero.
- Operating temperature must fall within the device's supported range.
- Discount percentage normally falls within a defined range.
- Inventory quantity may be non-negative unless the business permits backorders.

`CHECK` constraints can validate conditions on the same row. Rules depending on unit catalogs, products, or other configurations must be enforced via foreign keys, transactions, triggers, or an appropriate business layer. Do not assume a `CHECK` constraint can arbitrarily query other tables.

## 5. Selling price and pricing units

A price does not consist solely of an amount and currency. It can also be quoted per base unit:

- 25,000 VND per piece.
- 80,000 VND per kg.
- 12 USD per meter.
- 5 EUR per liter.

A price of 80,000 VND/kg is not equivalent to 80,000 VND/g. If a system stores only `amount` and `currency` without a pricing unit, applying the price to a quantity in another unit can be off by orders of magnitude.

A pricing structure should specify:

- Amount.
- Currency code.
- Pricing unit.
- Basis quantity of the pricing unit if not equal to one.
- Effective time interval.
- Applicability scope: product, customer, region, or price list.

For example, a price of 120,000 VND for a 6-bottle box differs from 120,000 VND per bottle. If storing prices per package, explicitly represent `package_quantity = 6` and `package_unit = bottle`.

### 5.1. Example of unit-based pricing

~~~sql
CREATE TABLE product_prices (
    product_price_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id),
    currency_code CHAR(3) NOT NULL
        REFERENCES currencies(currency_code),
    price_amount NUMERIC(24, 10) NOT NULL
        CHECK (price_amount >= 0),
    price_unit_code VARCHAR(20) NOT NULL
        REFERENCES measure_units(unit_code),
    basis_quantity NUMERIC(24, 10) NOT NULL DEFAULT 1
        CHECK (basis_quantity > 0),
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    CHECK (effective_to IS NULL OR effective_to > effective_from)
);
~~~

This example represents an amount for a basis quantity of a unit. If `price_amount` is 120,000 VND, `price_unit_code` is `BOTTLE`, and `basis_quantity` is `6`, the applicable price is 120,000 VND for 6 bottles. When calculating the price for 1 bottle, the system divides using defined precision and rounding rules.

Counting units such as piece, box, or carton also need codes and conversion rules. However, a carton may hold varying quantities depending on product or batch. Thus, not every packaging relationship is a fixed factor in a shared unit catalog; a product-specific packaging specification table may be required.

If each product may have only one active price per currency and pricing unit at a given time, add a mechanism to prevent overlapping effective intervals. Depending on the DBMS, you can use an exclusion constraint over the time range or a transaction/trigger with appropriate locking. A single-row `CHECK` can only verify `effective_to > effective_from`, not detect two overlapping price rows.

### 5.2. Fractional quantities and integer quantities

Not every quantity is an integer. Goods sold by weight can have `0.375 kg`; goods cut by length can have `1.25 m`. Conversely, quantities of devices or tickets must usually be integers.

Data types must reflect the rules:

- Integer for business objects that cannot be subdivided.
- NUMERIC for mass, length, or quantities with fractional parts.
- Never use FLOAT for quantities requiring exact conversion and reconciliation.

If receiving units differ from inventory storage units, explicitly record the conversion. For example, receiving 2 cartons of 12 bottles each increases inventory by 24 bottles. The specification of 12 bottles/carton must be recorded at receipt time in case packaging changes later.

## 6. Currency conversion and exchange rates

### 6.1. Exchange rates have direction

An exchange rate must state how many quote currency units equal one base currency unit. For example:

**1 USD = 25,000 VND**

Here USD is the base currency, VND is the quote currency, and the rate is 25,000 VND per USD. Reversing the direction yields 1/25,000 USD per VND, not the same number.

Field names should clarify direction, such as `quote_per_base`. Do not name a field simply `rate` if the schema lacks `base_currency` and `quote_currency`.

### 6.2. Storing rate source and timestamp

Exchange rates vary by time and source. A converted transaction must know which exchange rate was applied rather than recalculating with the latest rate when viewing history.

An exchange rate table may contain:

~~~sql
CREATE TABLE exchange_rates (
    base_currency_code CHAR(3) NOT NULL
        REFERENCES currencies(currency_code),
    quote_currency_code CHAR(3) NOT NULL
        REFERENCES currencies(currency_code),
    quote_per_base NUMERIC(30, 15) NOT NULL
        CHECK (quote_per_base > 0),
    observed_at TIMESTAMPTZ NOT NULL,
    source_name VARCHAR(100) NOT NULL,
    rate_type VARCHAR(30) NOT NULL,
    PRIMARY KEY (
        base_currency_code,
        quote_currency_code,
        observed_at,
        source_name,
        rate_type
    ),
    CHECK (base_currency_code <> quote_currency_code)
);
~~~

`observed_at` indicates when the exchange rate was recorded. A system may also need effective timestamp, source timezone, rate type (buy/sell/mid), trade date, and data source version. Do not use a single ambiguous timestamp column for both publication time and application time.

### 6.3. Recording the actual exchange rate of a transaction

When an amount is paid or posted in another currency, store:

- Source amount and source currency.
- Target amount and target currency.
- Applied exchange rate and rate direction.
- Source or basis of the rate.
- Application timestamp.
- Rounding rule.

Do not store only the converted amount and discard the original amount. When reconciliation or variance explanation is needed, both the original value and the rate used must be known.

### 6.4. Do not add multiple currencies directly

Revenue of 100 USD and 2,000,000 VND cannot be added to get `2,000,100` as total revenue. To aggregate, select a reporting currency and conversion rules:

1. Select the reporting currency.
2. Select the exchange rate source and rate type.
3. Determine the rate timestamp: transaction time, end of day, end of month, or report date.
4. Convert each amount according to the rules.
5. Round at the appropriate level.
6. Retain audit trail so reports can be reproduced.

In an analytical warehouse, keep both original amounts and amounts converted to the reporting currency. Clearly record rate date, rate type, and rule version.

## 7. Error-prone unit conversion scenarios

### 7.1. Do not mix dimensions

Mass, volume, length, area, and time are distinct dimensions. The system should check dimensions before performing calculations.

Valid operations depend on the quantity kind:

- Add two masses after converting to the same unit.
- Divide mass by volume to compute density.
- Multiply length by width to compute area.
- Never add mass to length.

A syntactically valid numeric value and unit symbol can still be semantically wrong. For example, entering `10 kg` into a length field must be rejected.

### 7.2. Converting volume to mass requires density

For a homogeneous substance under defined conditions:

**mass = volume × density**

However, density depends on substance, temperature, pressure, and composition. One liter of water cannot be converted to the same mass as one liter of oil or one liter of a solution at a different concentration.

If conversion is needed, store density, density unit, measurement conditions, and data source. The result should be recorded as a calculated value with a specific method and timestamp.

### 7.3. Temperature has an offset

You cannot convert Celsius to Fahrenheit by multiplying by 1.8 alone; you must add 32. This shows that units can have affine conversion rules, not merely multiplicative factors.

If the system manages temperatures, pick an internal standard scale and store the original scale when traceability is needed. For temperature-difference calculations, distinguish absolute temperatures from temperature intervals.

### 7.4. Packaging units and product specifications

A box may hold 10 items in one packaging version and 12 items in another. If you only store a fixed conversion factor for the unit `BOX`, historical data can be misinterpreted.

Tie packaging specifications to the product and effective timestamp. Past goods-receipt records must retain the quantity and packaging specification applied at receipt time, even if the manufacturer changes packaging later.

### 7.5. Speed, throughput, and derived quantities

A derived quantity combines multiple units. Examples:

- Speed: km/h or m/s.
- Density: kg/m³.
- Power: W or kW.
- Throughput: items/hour.

The schema should express numerator and denominator units or use a clearly defined derived unit code. Do not store a value `60` labeled simply as `speed` without knowing whether it is 60 km/h or 60 m/s.

## 8. Business rules and consistency checks

### 8.1. Constraints at the right layer

Some rules belong in the schema:

- Currency code must reference the currency catalog.
- Monetary amount is non-negative for payment-collection transactions.
- Unit must belong to the attribute's dimension.
- Measured values must have a unit.
- Effective intervals must have end timestamp after start timestamp.

Rules spanning multiple rows or complex policies may require transactions, triggers, or a business layer. For example, invoice lines and invoice total must reconcile; a selected exchange rate must match the currency pair and timestamp.

Do not repeat `currency_code` on every line if an invoice always has a single currency, unless there is a clear reason. If currency is stored on both header and lines, add constraints ensuring no line has a currency differing from its invoice.

### 8.2. Protecting value and unit as a pair

A `quantity` column must not exist without knowing its unit. If `unit_code` is NULL while `quantity` has a value, the system cannot interpret it. Conversely, having a unit without a value also needs a clear meaning.

You can use a `CHECK` constraint to protect completeness of the value/unit pair:

~~~sql
CHECK (
    (measured_value IS NULL AND unit_code IS NULL)
    OR
    (measured_value IS NOT NULL AND unit_code IS NOT NULL)
)
~~~

For required attributes, put NOT NULL on both value and unit. For optional attributes, the `CHECK` above prevents a half-populated state.

### 8.3. Testing conversions

Conversions to test:

- Zero, negative, and maximum values.
- Base units and smaller/larger units.
- Conversion factors with many decimal places.
- Round-trip conversions and rounding error.
- Temperatures with offsets.
- Units from mismatched dimensions.
- Missing units or invalid currency codes.
- Exchange rates equal to zero, negative, or inverted direction.
- Refund transactions and negative amounts per policy.

A useful test is converting A to B and back to A. The result may differ within an acceptable rounding tolerance; that tolerance must be defined rather than ignoring error.

## 9. Using currency and quantities in reporting

### 9.1. Currency reporting

Never add monetary amounts with different currency codes directly. Reports must pick a standard currency or group and display each currency separately. If converted, clearly state the exchange rate and timestamp.

Metrics such as revenue, profit, inventory value, and receivables may use different conversion timestamps under accounting policies. Do not apply the latest exchange rate to all historical transactions.

### 9.2. Measurement reporting

When aggregating mass or volume, convert to the base unit within the same dimension. If a report compares products with different sales units, clarify whether it compares package counts, base-unit quantities, or converted values.

For example, 10 boxes and 100 pieces cannot be added directly if boxes contain different piece counts. Use the packaging specification in effect at transaction time to convert.

### 9.3. Storing both source and standard values

In analytics, you can store:

- Original measured value.
- Original unit.
- Converted standard value.
- Standard unit.
- Conversion factor or conversion rule version.
- Measurement timestamp and source.

Standard values support aggregation, while source data supports traceability and verification. Do not overwrite source data if conversions can vary by catalog or rule version.

## 10. Evolving currency and unit catalogs

Currency catalogs, unit codes, and conversion rules also have lifecycles. A unit may be retired, a currency code may be replaced, or a product's packaging specification may change.

When updating catalogs:

- Do not reuse a unit code for a different meaning.
- Mark old codes as inactive for new transactions while keeping historical data readable.
- Record effective timestamps for conversion rules.
- Record metadata version or source.
- For amounts stored in minor units, retain the decimal digit count or metadata version applied at posting time.
- Do not automatically recalculate finalized transactions unless required by business rules.
- Prepare a migration and reconciliation plan if old codes must map to new codes.

For example, if a product changes from a 10-piece box to a 12-piece box, past transactions must continue using the 10-piece box specification. The new specification applies only from its new effective timestamp.

## 11. Common mistakes

**Storing monetary amounts without currency codes.** A numeric value alone is insufficient to interpret money. Always attach a currency code to each monetary amount or to a parent entity with a clear single-currency rule.

**Using FLOAT for reconcilable money.** Binary floating-point errors can skew results. Use NUMERIC/DECIMAL or integer minor units per policy.

**Assuming all currencies have two decimal places.** Minor-unit digit count depends on the currency code. Manage metadata and validate by currency.

**Rounding inconsistently across multiple places.** Orders, invoices, and payments can produce different totals. Standardize the rounding level and share common logic.

**Storing quantities without units.** Cannot compare or convert reliably. Measured values must accompany a unit code.

**Treating every unit conversion as multiplying by a factor.** Temperature has an offset; volume to mass requires density; packaging depends on product. Model appropriate conversion rules.

**Adding quantities of different dimensions.** Kilograms and liters cannot be added directly. Validate dimensions before computing.

**Using display symbols as codes.** Symbols can collide or vary by locale. Use stable codes and format symbols in the UI.

**Storing only converted results.** Without original values, original units, and exchange rates, reconciliation becomes difficult. Keep source data and applied rules when traceability is needed.

**Editing catalogs and altering history.** New factors or packaging specs must not unintentionally reinterpret past transactions. Store effective dates and versions.

## 12. Process for designing unit-aware values

When encountering a currency or measured quantity field, follow these steps:

1. **Identify meaning:** is this a monetary amount, unit price, rate, mass, volume, or derived quantity?
2. **Identify units:** which currency codes or unit codes are permitted?
3. **Identify dimension:** which dimension does the quantity belong to, and with which units can it convert?
4. **Identify precision:** value domain, precision, scale, and required decimal places.
5. **Identify rounding rules:** when and how rounding occurs, especially for financial transactions.
6. **Identify context:** unit for unit prices, direction for exchange rates, and timestamp for measurements?
7. **Choose storage:** NUMERIC, integer minor units, original value, or standard value.
8. **Design constraints:** require unit, valid code, matching dimension, and valid value range.
9. **Define history:** which exchange rates, conversion rules, packaging specs, or snapshots applied must be stored?
10. **Test:** test boundary values, round-trip conversions, mismatched-dimension units, and rounding behavior.

## 13. Schema review checklist

- [ ] Every monetary amount has a clear currency code.
- [ ] Binary floating-point types are not used for reconcilable money.
- [ ] Minor-unit decimal digits are determined by currency code.
- [ ] Unit prices specify pricing unit and basis quantity.
- [ ] Precision, scale, and rounding rules are agreed upon.
- [ ] Every measured quantity has a unit code.
- [ ] Units belong to the attribute's correct dimension.
- [ ] Linear conversions and offset conversions are distinguished.
- [ ] Context-dependent conversions store context data.
- [ ] Exchange rates include base, quote, direction, source, and timestamp.
- [ ] Finalized transactions retain actual applied exchange rates and amounts.
- [ ] Reports do not directly add different currencies or dimensions.
- [ ] Source values and conversion rules are preserved when traceability is needed.
- [ ] Catalogs and specifications carry effective timestamps without corrupting history.

## Conclusion

Currency and measured quantities are unit-aware values, not standalone numbers. A monetary amount requires a currency code; a measurement requires a unit and dimension; a unit price also requires a pricing unit; an exchange rate requires conversion direction, source, and timestamp. The data model must capture this information to prevent invalid comparisons, additions, or conversions.

Choose appropriate exact numeric types, specify precision and rounding, manage currency and unit catalogs, and protect value/unit pairs with constraints. When converting, retain original data and applied rules whenever reconciliation is needed. When catalogs or specifications change, use effective timestamps so historical data continues to preserve its true meaning.
