# Value Domains and Choosing Types by Business Meaning

When designing attributes for a data model, column names and storage types describe only part of the meaning. We also must define what an attribute represents, which values are allowed to appear, what the unit of measurement is, how much precision must be retained, under what circumstances a value can be absent, and where the system will enforce those rules.

A **value domain** describes the set of valid values that an attribute or group of attributes can take. A value domain can be defined by data type, bounds, units, code catalogs, formatting rules, relationships with other attributes, and business conditions. Choosing the right data type based on business meaning ensures data is stored accurately, queried consistently, validated properly, and exchanged reliably across systems.

For example, product quantity is a non-negative count; monetary price is a quantity with a currency unit and rounding rules; date of birth is a calendar date, not a timestamp with a timezone; an order code is an identifier, not a number for arithmetic. Although these values might be represented as numbers or strings, they carry different meanings and rules.

This lesson explains how to identify value domains from business requirements, select data types, express constraints, and handle error-prone edge cases when translating a logical model into a storage schema.

## 1. What is a value domain?

A value domain is the set of values an attribute is permitted to take according to business definitions. A domain typically includes several components:

- **Representation type:** integer, decimal, string, date/time, Boolean, code, or composite structure.
- **Range:** minimum value, maximum value, or allowed set of values.
- **Unit:** currency, kilograms, meters, percentage, number of items, or another business unit.
- **Precision:** total digits, decimal places, or temporal resolution.
- **Formatting rules:** pattern, length, letter casing, allowed characters.
- **Requiredness:** whether it can be blank or unspecified.
- **Dependency rules:** whether a value is valid when combined with other attributes.
- **Temporal semantics:** whether the value describes a calendar date, an absolute instant, local time, or a duration.

For example, the domain of line-item quantity can be described as follows:

| Component | Rule |
|---|---|
| Meaning | Number of product units ordered in a line item |
| Conceptual type | Quantity |
| Domain | Integer greater than 0 |
| Unit | Piece / unit |
| Precision | Integer |
| Requiredness | Required |
| Validation | Rejects negative numbers, zero, or fractional parts |

The domain of storage temperature differs: decimal number, unit in degrees Celsius, limits per product category, and potentially one decimal place of precision. You cannot choose a type solely because both are numbers.

### 1.1. Distinguishing data type from value domain

A data type defines how a value is represented and which basic operations the system supports. A value domain adds business meaning and specific constraints.

For example, an INTEGER type can hold many negative and positive integers. Yet the `quantity` attribute in an order only allows positive integers. Thus:

- Data type: integer.
- Value domain: integer greater than 0.
- Additional rule: does not exceed the maximum quantity allowed per order.

One data type can be used for many different domains. Two attributes both using VARCHAR(50) does not mean they share the same meaning or rules. Postal code, product code, display name, and phone number can all be stored as strings, yet require different validation rules.

### 1.2. A value domain is more than min and max bounds

An attribute may need to satisfy more conditions than an arithmetic range.

For example, a discount rate might fall between 0 and 100%, yet also depend on promotion type, effective time, and approval authority. A country code may have a fixed length, yet must belong to a recognized code catalog. A contract end date must be greater than or equal to the start date. An email may be syntactically valid yet unverified or no longer permitted for use.

Therefore, define the value domain at the business level first, then allocate rules across data types, database constraints, application checks, or external verification workflows.

## 2. Gathering business meaning before choosing types

### 2.1. Ask what the attribute represents

Attribute names are sometimes ambiguous. For example:

- `amount` could mean amount receivable, collected, refunded, or remaining due.
- `date` could mean creation date, effective date, delivery date, or system recording date.
- `status` could mean order status, payment status, shipping status, or internal processing status.
- `count` could mean number of orders, number of attempts, or number of processed records.
- `rate` could mean percentage, rate per unit time, or interest rate.

Before selecting a type, write one sentence clearly defining the attribute's meaning. If two attributes share the same name with different meanings, use more specific names or record separate definitions in the data dictionary.

### 2.2. Ask about units and conventions

Every measured quantity needs a unit and convention. For example:

- Is weight stored in grams or kilograms?
- Is distance stored in meters or kilometers?
- Does temperature use Celsius or Fahrenheit?
- Which currency is used for monetary amounts?
- Is a percentage stored on a 0–100 scale or 0–1 scale?
- Is duration stored in seconds, milliseconds, or minutes?
- Are dimensions stored in centimeters or millimeters?

Do not rely on column names to implicitly guess units. Two systems both storing `weight = 5` where one interprets kilograms and the other interprets grams can cause serious errors.

### 2.3. Ask about limits and boundary cases

Clarify:

- Minimum and maximum allowed values.
- Are negative numbers allowed?
- Is zero allowed?
- Are decimal fractions allowed?
- Can limits be exceeded in a special state?
- Can the maximum value grow over time?
- Are out-of-domain values rejected, rounded, converted, or queued for handling?

For example, available inventory usually cannot be negative, whereas an inventory adjustment quantity can be negative because it represents an increase or decrease. Do not apply the same domain to two attributes simply because both relate to quantities.

### 2.4. Ask whether data can be absent

Distinguish between:

- Value unknown.
- Not yet collected.
- Not applicable to this case.
- User declined to provide.
- Value not yet verified.
- Value deleted per policy.

These cases may require different representations. A NULL value usually indicates only that no value is stored, without self-explaining why. If the business needs to distinguish these states, an additional status attribute or collection workflow modeling may be required.

## 3. Classifying common value domains

### 3.1. Integer domain

Use integers for count quantities or numerical codes that genuinely require arithmetic operations.

Examples:

- Product quantity.
- Retry count.
- Line item sequence number.
- Number of days in a counting interval.
- Incrementing version number.

Choose a range suitable for the expected maximum value. Smaller integers save space in some DBMSs, yet choosing too small a type can cause overflow as data grows. Base the choice on business limits, growth rate, and system lifecycle.

Codes made up of digits that carry no arithmetic meaning should usually be stored as strings. For example, postal code `01234` needs to preserve its leading zero; employee code `000172` should not be turned into `172` if formatting is part of the code.

### 3.2. Exact decimal domain

Use exact decimal types for quantities that must preserve values according to decimal arithmetic rules, especially currencies, rates, and accounting calculations.

Examples:

- Unit price.
- Invoice total.
- Tax.
- Commission rate.
- Fractional weights.
- Measurements requiring fixed decimal precision.

In many relational DBMSs, DECIMAL or NUMERIC types allow declaring precision and scale. Precision is the total number of digits stored; scale is the number of digits after the decimal point.

For example, `NUMERIC(12, 2)` allows up to 12 total digits, including 2 decimal places. The maximum positive value is `9,999,999,999.99`. The specific numbers must match the business domain.

### 3.3. Floating-point domain

FLOAT, REAL, or DOUBLE PRECISION typically represent real numbers in binary floating-point format. They suit scientific calculations, simulations, measurements, or algorithms that tolerate rounding error.

Do not default to FLOAT for currency or calculations requiring exact reconciliation down to the smallest unit. Some decimal fractions cannot be represented exactly in binary, so addition and comparisons can introduce tiny discrepancies.

If the business requires monetary amounts accurate to the cent or smallest unit, use exact decimals or represent them as integers in the agreed smallest unit.

### 3.4. Character string domain

Strings are used for text data, codes, names, descriptions, and formatted values.

Distinguish:

- Maximum length in characters vs. bytes.
- Whether empty strings are allowed.
- Case sensitivity.
- Whitespace or Unicode normalization.
- Formatting rules or allowed character sets.
- Whether full-text search or accent-insensitive comparison is needed.

CHAR typically suits fixed-length strings depending on DBMS implementation; VARCHAR suits variable-length strings; TEXT is commonly used for long text. Storage details and limits vary across DBMSs, so consult the documentation of the chosen platform.

Do not pick lengths arbitrarily. Person names, addresses, product codes, and notes have different length distributions. Examine real data, relevant standards, and future extensibility.

### 3.5. Boolean domain

Boolean represents two logical values: true and false. However, business domains sometimes need three states: yes, no, and unknown. NULL can represent unknown, provided the meaning of NULL and how to query it are clearly defined.

For example, `is_verified` might mean:
- TRUE: verified.
- FALSE: verified and failed, or not yet verified, depending on definition.
- NULL: no result yet.

If “not submitted for verification”, “pending”, “failed”, and “verified” are distinct states, a single Boolean is insufficient; use an explicit status domain.

### 3.6. Date and time domains

Time carries several distinct meanings:

- Calendar date, such as date of birth or due date.
- Absolute instant, such as when a payment was confirmed.
- Local time in a timezone, such as store opening hours.
- Duration interval, such as processing time.
- Effective interval, such as the start and end dates of a contract's validity.

Do not use a single timestamp type for every case. Date of birth should usually be stored as DATE because no timezone is needed. Transaction timestamps generally require an absolute instant, normalized and displayed in the appropriate timezone. Store opening hours may need both local time and the location's timezone.

### 3.7. Code and lookup domains

Business codes such as order status, product category, country, payment method, or unit of measure can be represented using an enum, a constrained string, or a foreign key referencing a lookup table.

Which approach to choose depends on:
- Whether the list of values is fixed or changes frequently.
- Whether per-value metadata is needed.
- Whether values have time-bound validity.
- Whether multiple systems share the same codes.
- Whether multilingual translations or display labels are needed.
- Whether adding a new value should require redeploying the application.

An enum can be convenient when the value set is small and stable. A reference table is better when the catalog needs governance, descriptions, statuses, display order, or an assigned owner.

### 3.8. Binary and large data domains

Binary data can store file contents, images, or encrypted payloads. However, weigh storing directly in the database vs. storing in object storage and keeping a reference in the data model.

Define maximum size, content type, checksum, retention period, access permissions, and behavior when a file is replaced or deleted. Do not use BLOB fields for all files without clear querying and operational justification.

### 3.9. Flexible structure domains such as JSON

JSON can suit semi-structured data, extensible attributes, or integration payloads whose schema varies by object type. However, using JSON does not eliminate the need for data modeling.

Define:
- Which fields are required.
- Data types and valid domains of each field.
- Which parts of the structure are allowed to vary.
- Which fields need querying, filtering, or indexing.
- How schema versioning is managed.
- Rules for handling unrecognized fields.

If an attribute is frequently used in filters, joins, constraints, or reports, consider promoting it to a strongly typed column. JSON should serve intentional flexibility rather than replacing the entire data model.

## 4. Choosing types by business meaning

The following table illustrates translating business concepts into representation types. Exact type names may differ across PostgreSQL, MySQL, SQL Server, Oracle, or NoSQL systems.

| Business meaning | Conceptual type | Common choices | Things to check |
|---|---|---|---|
| Product quantity | Counting integer | INTEGER or BIGINT | Are 0, negative, or fractional values allowed? |
| Currency | Exact decimal + currency | DECIMAL/NUMERIC or integer minor units | Precision, scale, currency code, and rounding |
| Percentage | Decimal or integer per convention | NUMERIC/DECIMAL | Stored as 0–100 or 0–1? |
| Order code | String identifier | VARCHAR or UUID | Uniqueness scope, mutability |
| Date of birth | Calendar date | DATE | No timezone needed |
| Payment timestamp | Absolute instant | Timestamp with timezone convention | UTC, precision, and clock source |
| Opening hours | Local time + timezone | TIME and timezone identifier | Daylight saving time and location |
| Activation status | Boolean or status | BOOLEAN or status code | Are there unknown/pending states? |
| Email | Text with format rules | VARCHAR/TEXT | Normalization, verification, comparison |
| Geographic coordinates | Measured quantity with unit | Spatial type or decimal numbers | Coordinate reference system and precision |
| File content | Binary data or reference | BLOB or object key | Size, permissions, and lifecycle |
| Extensible attributes | Flexible structured data | JSON/JSONB or document | Schema, validation, and indexing |

### 4.1. Do not use numeric types for every digit-only string

An identifier may consist solely of digits yet have no arithmetic meaning. Examples:
- Postal code.
- Customer code.
- Phone number.
- Tracking number.
- Displayed account number.
- Product code with leading zeros.

Storing these values as strings preserves formatting and prevents meaningless arithmetic. If you need to verify digits-only or a specific pattern, use appropriate validation or constraints.

### 4.2. Do not use strings for quantities requiring calculation

Storing money, quantities, or durations as strings makes comparison, sorting, and arithmetic error-prone. For example, lexicographical sorting of `"100"` and `"20"` does not match numerical order.

If the data is a quantity, choose an appropriate numeric or temporal type. Convert to strings only at the presentation or integration layer when a contract requires it.

### 4.3. Choose precision and scale from business rules

For decimal numbers, determine:
- Expected maximum value.
- Significant decimal places.
- Rounding rules.
- Whether intermediate calculations need higher precision than display precision.
- The smallest unit permitted by the business.

For example, a unit price might be stored to 4 decimal places for calculations, while the payment total is rounded to 2 decimal places per currency rules. Do not round at every intermediate step if the business requires preserving precision until the final step.

### 4.4. Choose types based on growth limits

Do not pick INTEGER merely because current data is small. Forecast:
- Maximum number of records over the lifecycle.
- Daily or annual growth rate.
- Whether values increase monotonically.
- Whether historical data must be imported from other sources.
- Possibility of merging multiple systems.

Choosing a type that is too small can lead to difficult migrations. Choosing an overly large type can also affect index size or performance on some platforms. Base the choice on requirements and DBMS characteristics.

## 5. Units, precision, and rounding rules

### 5.1. Store units alongside quantity meaning

A measurement is incomplete without a unit. You can use explicit column names like `weight_grams`, `distance_meters`, or store the value alongside a unit code.

If multiple units are permitted, normalize to a base unit for calculations and store the unit code when the original unit must be preserved. For example, weight may be entered in kilograms or pounds but converted to grams or kilograms using a consistent rule.

Do not convert silently if the business needs to retain the original value, original unit, and converted result. For auditing, the source and conversion factor can matter.

### 5.2. Currency must accompany currency code

A value of `100.00` does not tell you whether it is 100 USD, 100 EUR, or 100,000 VND. A currency model typically needs both `amount` and `currency_code`.

Valid decimal places depend on currency and business rules. Different currencies have different minor units; some domains also have specific rounding rules for taxes, payments, or accounting.

Example conceptual structure:

| Attribute | Meaning |
|---|---|
| amount | Monetary value per precision/scale convention |
| currency_code | Currency identifier code |
| rounding_rule | Rounding rule if stored per transaction |
| exchange_rate | Exchange rate upon conversion, if any |
| rate_source | Source of exchange rate |
| rate_time | Effective timestamp of the exchange rate |

Not every table needs all of the above fields. Store only what is required to reconstruct the transaction and meet business requirements.

### 5.3. Percentages and ratios

The same 5% rate can be represented as `5` or `0.05`. Standardize the convention across the model and data contracts.

If storing `0.05`, the field can be named `discount_rate` with domain 0 to 1. If storing `5`, the field can be named `discount_percent` with domain 0 to 100. Do not use ambiguous names like `rate` without documenting the definition.

### 5.4. Rounding rules must be explicit

Different rounding methods can produce different results, especially when calculating taxes, discounts, or allocating a total across multiple line items.

Define:
- Round per line or after summing?
- Use half-up, half-even, or another rule?
- How many digits are retained in intermediate calculations?
- How is a one-minor-unit remainder handled during allocation?
- Are rules specific to currency or region?

Do not let each service round using whatever library default it happens to have. Rules must be documented in business specifications and applied consistently.

## 6. Date, time, and timezone types

### 6.1. Calendar dates are not instants

Date of birth, license issue date, or due date are typically calendar dates. They do not represent a specific instant on the timeline and do not need timezone conversion.

Payment timestamp, event receipt timestamp, or record creation timestamp are instants. If stored as calendar dates, the system loses hours, minutes, and ordering among events within the same day.

### 6.2. Absolute instants and local times

An event occurring at an instant can be normalized to UTC for exchange and sorting. When displayed, the system converts to the user's or business location's timezone.

Store opening hours are local time: 09:00 to 18:00 at a location. If a store is in a region with daylight saving time rules, store an appropriate timezone identifier instead of only a fixed UTC offset.

### 6.3. Choosing temporal precision

Not every case requires microseconds. Determine resolution from business needs:

- Calendar date: no time component needed.
- Transaction instant: typically seconds or milliseconds depending on ordering and reconciliation.
- Sensor data: may require higher resolution.
- Appointments: require local time, timezone, and recurrence rules.

Higher precision does not automatically make data more accurate. Clock source, time synchronization, and the meaning of the timestamp still must be defined.

### 6.4. Effective time and recording time

An attribute may need two timestamps:
- When the fact takes effect in the business domain.
- When the system receives or records the fact.

For example, an address change entered on day 10 takes effect from day 1. Storing only one timestamp cannot accurately answer both “since when was the address effective?” and “since when did the system know about it?”.

## 7. NULL, default values, and optional domains

### 7.1. NULL is not 0 or an empty string

NULL usually indicates no defined value. It differs from:
- 0: a specific numeric value.
- Empty string: a string of length 0.
- FALSE: a negative Boolean value.
- A “not applicable” code: a specific business value.
- A default value: a value populated by system rule.

Using 0 instead of NULL can skew calculations and reports. Using an empty string instead of NULL can prevent the system from distinguishing unentered data from data explicitly entered as empty.

### 7.2. Identifying why data is missing

If the business needs to distinguish scenarios, use a status attribute or separate data modeling.

For example, verification date can be:
- NULL because verification has not started.
- Populated when verified.
- A separate status `rejected` when verification fails.

Do not infer every status solely from whether a date is NULL if there are multiple intermediate steps.

### 7.3. Default values must be meaningful

DEFAULT should only be used when there is a valid business default. For example, initial retry count can default to 0. However, `country = VN` is only valid if the process guarantees all new records belong to Vietnam; do not set it as a default simply because most current customers are in Vietnam.

### 7.4. NOT NULL is a business decision

Setting NOT NULL means every valid record must have a value. Determine when it becomes required:
- Immediately upon record creation.
- After completing a workflow step.
- Upon transitioning to a confirmed status.
- Required only for a specific object type or channel.

A field may temporarily lack a value while a record is in draft status, yet be required before submission. If the database cannot express state-dependent conditions via simple constraints, enforce checks inside transactions or application workflows.

## 8. Encoding domains with types and constraints

### 8.1. NOT NULL, CHECK, and UNIQUE constraints

In a relational model, constraints enforce data domains directly at the storage layer.

Illustrative SQL example:

~~~sql
CREATE TABLE order_item (
    order_item_id BIGINT PRIMARY KEY,
    order_id      BIGINT NOT NULL,
    line_number   INTEGER NOT NULL,
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    currency_code VARCHAR(3) NOT NULL,
    sku           VARCHAR(40) NOT NULL,
    CONSTRAINT uq_order_item_order_line
        UNIQUE (order_id, line_number)
);
~~~

The constraints above are syntax examples only. Uniqueness rules for order lines must be designed from actual business requirements; this example does not claim an SKU must be unique within an order. If the same SKU can appear on multiple lines, choose an appropriate line key.

Common constraint types:
- NOT NULL: disallows missing values.
- CHECK: restricts value domain or relationships between fields.
- UNIQUE: ensures uniqueness within the declared scope.
- PRIMARY KEY: unique, non-NULL identifier.
- FOREIGN KEY: ensures references point to valid records.

### 8.2. Using reference tables for governed domains

If a code list evolves with business needs, use a reference table:

~~~sql
CREATE TABLE order_status (
    status_code VARCHAR(20) PRIMARY KEY,
    display_name VARCHAR(80) NOT NULL,
    is_terminal BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
~~~

The orders table references the status code:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status_code VARCHAR(20) NOT NULL,
    CONSTRAINT fk_orders_status
        FOREIGN KEY (status_code)
        REFERENCES order_status(status_code)
);
~~~

In practice, if statuses have transition rules, do not merely check that a code exists. Enforce valid state transitions according to the business workflow—for example, preventing a cancelled order from jumping straight to delivered.

### 8.3. Using domain types when supported by the DBMS

Some relational DBMSs support creating domain types based on a base type with shared constraints.

PostgreSQL example:

~~~sql
CREATE DOMAIN positive_quantity AS INTEGER
    CHECK (VALUE > 0);

CREATE DOMAIN currency_code AS VARCHAR(3)
    CHECK (char_length(VALUE) = 3 AND VALUE ~ '^[A-Z]{3}$');

CREATE TABLE order_line (
    order_line_id BIGINT PRIMARY KEY,
    quantity positive_quantity NOT NULL,
    currency currency_code NOT NULL
);
~~~

Domain types help reuse basic rules across many columns. However, a three-letter regex only checks format; it does not prove the currency code is valid. If you need an authoritative catalog and metadata, use a reference table or corresponding validation mechanism.

Syntax and support for domain types vary across DBMSs. Do not rely on domain types if the application must run across multiple platforms without a compatibility strategy.

### 8.4. Distributing validation between database and application

Not every rule can or should live inside a CHECK constraint. Classify them:

- Simple single-column rules: data type, NOT NULL, CHECK.
- Uniqueness rules: UNIQUE or unique index.
- Referential rules: FOREIGN KEY.
- Multi-record or concurrency rules: transactions, locks, or controlled update mechanisms.
- Rules depending on external services: verification via API or integration workflows.
- Rules depending on state and permissions: business logic within transaction boundaries, combined with necessary constraints.

Application-level validation improves user error messages, yet should not be the sole defense for invariants that must hold across all write paths.

## 9. Value domains across different storage models

Domain semantics must remain consistent even as physical representations change.

### 9.1. Relational databases

The relational model typically provides clear column types, constraints, keys, and reference tables. It fits well when strong structured-data consistency, joins, and database-level domain enforcement are needed.

Considerations:
- Types and syntax differ across DBMSs.
- Enums or domain types can complicate schema changes.
- Complex constraints require balancing performance and maintainability.

### 9.2. Document databases

Document databases can store attributes inside a single document with a flexible structure. However, individual fields still need defined types and valid domains.

Determine:
- Is schema validation enabled?
- Can older documents omit newer fields?
- How does a null value differ from an absent field?
- How is schema versioning managed?
- Which fields must share the same type across all documents?
- How are invalid documents handled?

Document flexibility does not remove the need for value domains. If documents arbitrarily use different types for the same field, consumers must handle multiple cases and become error-prone.

### 9.3. Graph databases

In graph databases, nodes and relationships can carry properties. Properties also need types, domains, and rules. For example, an OWNS edge may have `valid_from`, `valid_to`, and `ownership_share`. Verify that ownership percentages fall within valid bounds and that total shares across relationships satisfy business rules.

### 9.4. Analytical data warehouses

Analytical warehouses typically require types suited for aggregation, time filtering, and historical storage. Determine:
- Do numeric types have sufficient precision?
- Do dates and instants follow consistent conventions?
- Are classification codes standardized?
- Are missing values distinguished from zero values?
- Has data been converted to standard units or currencies?
- Are source, extraction timestamp, and transformation version recorded?

Do not turn all business data into floating-point numbers or strings in an analytical warehouse merely to simplify ingestion. Data types must serve both accuracy and analytical queries.

## 10. End-to-end example: value domains for orders

Suppose a sales system stores orders, order items, payments, and shipments.

### 10.1. Defining domains for attributes

| Attribute | Meaning | Proposed value domain | Conceptual type |
|---|---|---|---|
| order_id | Order identifier | Non-empty, unique in the system | Identifier |
| order_date | Calendar date the order was created | Valid date | Date |
| created_at | Timestamp recorded by system | Absolute instant | Timestamp |
| status | Order status | Governed code set | Reference/enum |
| quantity | Number of items in line | Integer greater than 0 | Integer |
| unit_price | Locked unit price | Non-negative, precision/scale per policy | Decimal |
| currency_code | Currency type | Code from valid catalog | Code |
| discount_rate | Discount ratio | 0 to 1 if using ratio convention | Decimal |
| tracking_code | Shipment tracking code | String following carrier rules | String |
| delivered_at | Successful delivery timestamp | Present when delivery status is delivered | Optional timestamp |

### 10.2. Encoding rules into the schema

PostgreSQL example:

~~~sql
CREATE TABLE orders (
    order_id       UUID PRIMARY KEY,
    order_date     DATE NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL,
    status_code    VARCHAR(20) NOT NULL,
    currency_code  VARCHAR(3) NOT NULL,
    total_amount   NUMERIC(14, 2) NOT NULL
                   CHECK (total_amount >= 0),
    delivered_at   TIMESTAMPTZ NULL,
    CHECK (
        status_code <> 'delivered'
        OR delivered_at IS NOT NULL
    )
);

CREATE TABLE order_items (
    order_item_id UUID PRIMARY KEY,
    order_id      UUID NOT NULL REFERENCES orders(order_id),
    product_id    UUID NOT NULL,
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(14, 4) NOT NULL
                  CHECK (unit_price >= 0),
    line_total    NUMERIC(14, 2) NOT NULL
                  CHECK (line_total >= 0)
);
~~~

This example illustrates selected design choices, not a complete schema. The `status_code = delivered` case should be constrained via a status catalog or state-transition logic. The `total_amount` column may need reconciliation with item sums, taxes, and discounts within the same workflow. Precision of `unit_price` and `line_total` must be confirmed against pricing and rounding policies.

### 10.3. Uncovering ambiguities

Before finalizing types and domains, ask:

- Can an order have a negative value due to adjustments or refunds?
- Can a product be sold by fractional weight?
- Can multiple currencies appear in the same order?
- To how many decimal places are prices stored?
- Is total amount rounded per line or after summing?
- Is order creation time when the user submits the request or when the system confirms it?
- If an order ships in multiple batches, does `delivered_at` represent the first delivery, last delivery, or full-delivery timestamp?
- Can one order have multiple tracking codes?
- Can an order be in `delivered` status while one line remains undelivered?

These questions may lead the model to add shipment entities, payment tables, status history, or different quantity domains. Do not force every concept into one attribute just to keep the schema simple.

## 11. Managing domains as data changes over time

### 11.1. Extensible catalogs

A list of statuses or product categories can evolve over time. If the value set is hardcoded in multiple applications, adding a new value may require coordinated deployments.

Decide:
- Who manages the catalog?
- Does adding a new code require approval?
- Are old codes deleted or simply deprecated?
- How must older consumers handle unrecognized codes?
- Can display labels change or be translated into other languages?

A consumer should handle new values according to a contract rather than assuming a catalog will never change.

### 11.2. Time-effective domains

A value may be valid during a specific time range. For example, tax rates, price lists, or credit limits change by effective date.

Store:
- Value or version.
- Effective start timestamp.
- End timestamp, if any.
- System recording timestamp.
- Source and approver when needed.

Do not overwrite an old value if the business needs to reconstruct which rule applied to a transaction at the time it occurred.

### 11.3. Changing domain rules

If the maximum quantity limit changes from 100 to 500, clarify whether the new rule applies to existing records or only records created after the change. If units or precision change, prepare a migration plan and inspect existing data.

A domain change may require:
1. Checking whether existing data fits the new domain.
2. Defining how to handle values that are no longer valid.
3. Updating constraints and schema.
4. Updating producers/consumers.
5. Validating historical data.
6. Recording rule versions or effective timestamps if needed.

## 12. Common mistakes when choosing types

- **Choosing types by data shape:** seeing all digits and using INTEGER, even though the value is a code.
- **Using FLOAT for currency:** can introduce errors during calculation and reconciliation.
- **Omitting units:** systems interpret kg, grams, meters, or percentages differently.
- **Using timestamps for calendar dates:** causes date shifts across timezone conversions.
- **Storing local time without a timezone:** impossible to determine exact instants when timezone rules change.
- **Using BOOLEAN for multi-state workflows:** loses information about pending, failed, unknown, or not applicable.
- **Using VARCHAR for all data:** loses type checking, arithmetic, and storage-layer constraints.
- **Picking arbitrary lengths:** valid data gets truncated or forces premature migrations.
- **Letting NULL carry multiple meanings:** consumers cannot tell unentered from not applicable or unverified.
- **Using DEFAULT to mask missing data:** produces values that look valid yet are business-wrong.
- **Validating only in the UI:** writes from APIs, imports, or background jobs can violate domains.
- **Using rigid enums for frequently changing catalogs:** adding values becomes hard to deploy.
- **Storing schemaless JSON:** the same field can take different types and meanings across records.
- **Ignoring growth:** numeric ranges or code lengths prove insufficient over the system's lifecycle.
- **Not testing cross-system conversions:** lost leading zeros, wrong precision, or unintended timezone shifts.

## 13. Criteria for validating value domains

A good value domain needs valid examples, invalid examples, and expected system behavior.

**Quantity check**

- Given: an order line requires quantity to be a positive integer.
- When: a user enters 0, -1, or 1.5.
- Then: the system rejects it and reports the applicable rule.

**Currency check**

- Given: an order uses a defined currency and precision.
- When: the system calculates discounts, taxes, and total amount.
- Then: calculations follow rounding rules and can be reconciled.

**Numeric identifier check**

- Given: a postal code has leading zeros.
- When: the data is entered, stored, and exported.
- Then: the code preserves its formatting and is not converted to a number.

**Date and timestamp check**

- Given: a customer has a date of birth and a payment transaction.
- When: data is stored and displayed in another timezone.
- Then: date of birth does not shift days; the transaction timestamp still represents the exact same instant.

**Status domain check**

- Given: an order has a governed status catalog.
- When: a producer emits a new status unrecognized by a consumer.
- Then: the consumer handles it per unknown-value policy, logs an error, or routes it appropriately instead of silently misinterpreting it.

**NULL check**

- Given: a verification date field may have no value before the process starts.
- When: an unverified record is saved.
- Then: the system distinguishes not-started from failed verification or not applicable.

**Growth limit check**

- Given: record volume grows according to lifecycle forecasts.
- When: values approach data type limits.
- Then: the system continues storing valid data or has a migration plan before hitting the limit.

## 14. Checklist before finalizing data types

- [ ] Business definitions written for every important attribute.
- [ ] Valid domains, boundary values, and exception cases defined.
- [ ] Units and representation conventions specified.
- [ ] Types chosen to match operations and data meaning.
- [ ] Precision, scale, and rounding rules defined for decimals.
- [ ] Growth limits and numeric ranges evaluated.
- [ ] Identifiers distinguished from arithmetic quantities.
- [ ] Calendar dates, absolute instants, local times, and durations distinguished.
- [ ] Timezones and temporal precision specified where needed.
- [ ] NULL, empty strings, default values, and unknown states clarified.
- [ ] Code catalogs, owners, and domain extension methods defined.
- [ ] Appropriate constraints placed in both database and application.
- [ ] Cross-system conversions and consumer handling verified.
- [ ] Valid examples, invalid examples, and acceptance criteria documented.
- [ ] Domain changes over time and historical data considered.

The outcome of this step is a value domain definition for attributes, complete with conceptual type, unit, range, precision, requiredness, and validation rules. From there, the design team can select physical types and constraints aligned with business meaning while ensuring data is interpreted consistently across all consuming systems.
