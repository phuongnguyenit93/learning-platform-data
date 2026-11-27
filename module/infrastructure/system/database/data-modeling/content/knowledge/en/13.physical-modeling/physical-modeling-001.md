# Translating a Logical Model to Data Types and DBMS Limits

## 1. From Logical Model to Physical Model

In the `DATABASE_DATA_MODELING` module, learners practice turning business requirements into a verifiable data model: identifying entities, relationships, constraints, normalization, keys, and indexes, then deploying them into a physical schema. The transition from a **logical model** to a **physical model** is where concepts like "order ID", "amount", and "order timestamp" are mapped to specific data types, constraint syntax, and the actual capabilities of a database management system (DBMS).

- **The logical model** answers: what does the data represent, how do objects relate, what values are valid, and what business rules must always hold? It is not yet tied to a specific DBMS product.
- **The physical model** answers: which tables/collections/nodes/edges to create, which data types and lengths to use, how to enforce keys and constraints, which indexes are needed, and whether storage and queries can meet real-world load.
- **The implementation specification** must explicitly state the product, version, storage engine, charset/collation, data assumptions, and scaling policy. Two DBMSs that both support "SQL" can still have different data type semantics.

```mermaid
flowchart LR
    A["Business requirements"] --> B["Logical model: entities, relationships, invariants"]
    B --> C["Choose DBMS, version, storage policy"]
    C --> D["Data types, keys, constraints, indexes"]
    D --> E["DDL and migrations"]
    E --> F["Verify data, limits, query plans"]
    F -. "Identify gaps" .-> B
```

**Principle:** physical types must preserve the *meaning* and *invariants* defined in the logical model. Choosing a smaller type, dropping constraints, or turning a relationship into a JSON string just for SQL convenience can allow the system to accept invalid states.

## 2. Establish a "Data Contract" Before Choosing Types

Suppose a sales system has four logical entities:

| Entity | Attributes and Meaning | Relationships, Invariants |
|---|---|---|
| `Customer` | Customer ID, email, display name, creation timestamp | Email is required; uniqueness rule follows business policy |
| `Product` | Product ID, SKU, product name | SKU must not be duplicated |
| `PurchaseOrder` | Order ID, customer, status, currency, creation timestamp | Each order belongs to exactly one customer; status belongs to an allowed set |
| `OrderLine` | Order, line number, product, quantity, unit price at checkout | An order has many lines; line number is unique **within an order**; quantity is positive; unit price is non-negative |

The unit price on an order line is a **transaction price snapshot**, not the current price on the product catalog. Keeping it in `OrderLine` is a business decision: future product price changes must not rewrite purchase history.

For each attribute, the following information should be documented before writing DDL:

| Question | Example Decision to Document |
|---|---|
| What is the value domain? | `quantity` is a positive integer; `unit_price` is non-negative, with at most two decimal places if the currency policy allows |
| Can it be missing? | `Customer.email` is required; `delivery_date` may be unknown |
| Where do constraints live? | `order_status` follows an allowed status set; `customer_id` must exist in the customer table |
| Current and projected scale? | Number of orders in 5 years; max lines per order; SKU and name lengths |
| What are the comparison rules? | Is SKU case-sensitive? Should email comparisons be case-insensitive? |
| What are the read/write patterns? | Query the 20 most recent orders per customer; look up order lines by product; write and update ratios |
| What is the data policy? | Confirmed orders must preserve history; timestamps are stored against a unified time reference |

Lengths, precision, and `NULL` allowability must **not** be arbitrary numbers picked while writing the schema. They must come from the data contract, sample data, and growth projections.

## 3. Mapping Logical Attributes to Physical Types

The table below uses **PostgreSQL 16** as a reference to illustrate; type names and semantics must be re-evaluated if a different DBMS is chosen.

| Logical Data Type | PostgreSQL Types Typically Considered | Decisions Required |
|---|---|---|
| Integer identifier | `INTEGER`, `BIGINT`, `GENERATED ... AS IDENTITY` | Maximum record count; whether the ID carries business meaning; how IDs are generated when distributed |
| Global identifier | `UUID` | Generation strategy, index size, and fragmentation caused by insertion order |
| Integer quantity | `SMALLINT`, `INTEGER`, `BIGINT` | Can it be negative; upper bound; can additions/sums overflow |
| Price, money, rates requiring decimal precision | `NUMERIC(p,s)` / `DECIMAL(p,s)` | Total digits `p`, decimal digits `s`, rounding policy, and currency unit |
| Measurements tolerating representation error | `REAL`, `DOUBLE PRECISION` | Acceptable margin of error; do not use by default for money |
| Short strings with business limits | `VARCHAR(n)` | Character limit, Unicode normalization, collation, and comparison |
| Variable-length text | `TEXT` | Application-tier content limit, DBMS limit, and search requirements |
| Calendar date | `DATE` | Whether a timezone applies; e.g., date of birth, expected delivery date |
| Point-in-time event | `TIMESTAMPTZ` | Input/output rules by timezone; a point in time is not "local wall-clock time" |
| Time on a clock | `TIME` or another temporal type depending on semantics | Whether date and timezone are needed to handle DST |
| Boolean | `BOOLEAN` | Whether it is strictly two states or needs an "unknown" state |
| Binary data | `BYTEA` | Size limits, store in DB vs. store in object storage and keep a reference |
| Flexible, structured attributes | `JSONB` | Need for schema validation, path lookups, constraints against other entities |

### 3.1. Integer Width and Growth Values

In PostgreSQL, `SMALLINT` uses 2 bytes, `INTEGER` uses 4 bytes, and `BIGINT` uses 8 bytes; their ranges are roughly ±3.2×10⁴, ±2.1×10⁹, and ±9.2×10¹⁸ respectively. Choosing `SMALLINT` for order line numbers only makes sense if the business guarantees no order exceeds 32,767 lines. `BIGINT` suits long-lived auto-incrementing IDs, though it uses more memory and does not by itself solve ID allocation across multiple writers.

For UUID identifiers, decide on the standard and whether generation happens in the application or database. Randomly generated UUIDs can scatter B-tree inserts more than sequential IDs; in return, they are convenient when multiple systems generate IDs independently. This is a **trade-off driven by write volume and architecture**, not a single ID type optimal for every system.

### 3.2. Monetary Amounts: Precision vs. Magnitude

`NUMERIC(p,s)` uses `p` significant digits, of which `s` digits are after the decimal point. For example, `NUMERIC(14,2)` allows up to 12 integer digits and 2 fractional digits. If a price or calculation produces fractional digits beyond `s`, the DBMS may round according to its own rules; the application must agree on a rounding policy before writing.

Do not use `FLOAT`/`DOUBLE` to directly represent monetary amounts that require exact addition, subtraction, and reconciliation down to the smallest unit. Another option is storing an integer count of the smallest unit (such as cents), which requires explicitly specifying the decimal places per currency; not all currencies have two decimal places. For multi-currency systems, store the **currency code** alongside the amount and never add different currencies without converting under a well-defined rule.

### 3.3. Strings, Unicode, and Uniqueness Rules

`VARCHAR(50)` limits string length according to DBMS rules, **which does not mean 50 bytes on disk**. Unicode characters can occupy multiple bytes, and a single visual character may consist of multiple code points. Data limits, index key length limits, and comparison behavior depend on charset/collation.

On PostgreSQL, there is no default reason to choose between `TEXT` and `VARCHAR` thinking "one must be faster"; `VARCHAR(n)` is useful when `n` is genuinely a business constraint. `CHAR(n)` can pad trailing spaces and cause surprises during comparisons; use it only when fixed-width semantics are clearly understood.

In particular, a plain `UNIQUE(email)` **does not guarantee** that `A@example.com` and `a@example.com` are treated as the same. You must finalize a normalization and collation policy, or use a case-insensitive comparison/unique key mechanism appropriate for the DBMS. The same applies to SKUs with diacritics, uppercase letters, and whitespace.

### 3.4. Dates, Times, and Timezones

- `DATE` represents a **calendar date**, suitable for dates of birth or expected delivery dates; by itself it is not a point on a timeline.
- PostgreSQL `TIMESTAMPTZ` represents a **point in time** and converts its display representation to the session timezone; it does not store the original input timezone name per row. To preserve a user-selected timezone, store an additional identifier such as `Asia/Ho_Chi_Minh`.
- `TIMESTAMP WITHOUT TIME ZONE` stores date-time without timezone semantics; use it for local schedules only when the business logic clearly defines how the timezone is applied, and never assume it is UTC.

Date and time handling involves Daylight Saving Time (DST) edge cases, where a local hour may not exist or may occur twice. Avoid blindly adding "24 hours" to express every "add one calendar day" operation. API designs must state clearly whether an input value is a point in time, a calendar date, or a local time.

## 4. Mapping Relationships and Invariants to Keys and Constraints

Turning entities into tables is only the start. You must preserve the *exact relationships* and *valid value sets*:

| Logical Model | Typical Relationship Implementation |
|---|---|
| One `Customer` has many `PurchaseOrder` | `purchase_order.customer_id` is `NOT NULL` and a `FOREIGN KEY` referencing `customer.customer_id` |
| One `PurchaseOrder` has many `OrderLine` | `order_line.order_id` is a foreign key; the pair (`order_id`, `line_no`) is the primary key |
| One product appears on many order lines | `order_line.product_id` is a foreign key referencing `product` |
| Pure many-to-many relationship | Junction table containing two foreign keys, usually with a unique key on the pair; add attributes when the relationship carries its own data |
| True one-to-one relationship | Foreign key combined with `UNIQUE`, or a primary key that is simultaneously a foreign key |
| Required attributes / value sets | `NOT NULL`, `CHECK`, foreign key to a lookup table, or equivalent mechanisms |

A **primary key** identifies a row; a **candidate/unique key** protects business uniqueness; a **foreign key** protects links. They serve different purposes. An auto-generated `order_id` does not replace the rule "line numbers do not repeat within the same order".

Do not default to `ON DELETE CASCADE` for every relationship. For sales history, deleting a customer or product must probably not wipe out all past orders. Deletion, anonymization, archiving, and retention policies must be decided by business requirements.

Note that `CHECK` does not replace `NOT NULL`: in SQL, a check expression that evaluates to `UNKNOWN` due to `NULL` may not be treated as a violation. You should also examine how different DBMSs handle `UNIQUE` on nullable columns.

## 5. Example DDL Implementation on PostgreSQL 16

This example uses 64-bit integer primary keys, exact decimal unit prices, finite order statuses, and indexes driven by common queries. Assume this is a **starter schema** for a sales context, not yet including payments, shipping addresses, taxes, promotions, or state transition history.

```sql
CREATE TABLE customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email       VARCHAR(254) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_customer_email UNIQUE (email)
);

CREATE TABLE product (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku        VARCHAR(64) NOT NULL,
    name       VARCHAR(200) NOT NULL,
    CONSTRAINT uq_product_sku UNIQUE (sku)
);

CREATE TABLE purchase_order (
    order_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id    BIGINT NOT NULL,
    order_status   VARCHAR(16) NOT NULL DEFAULT 'DRAFT',
    currency_code  VARCHAR(3) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivery_date  DATE,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customer(customer_id),
    CONSTRAINT ck_order_status
        CHECK (order_status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    CONSTRAINT ck_order_currency_shape
        CHECK (currency_code ~ '^[A-Z]{3}$')
);

CREATE TABLE order_line (
    order_id    BIGINT NOT NULL,
    line_no     SMALLINT NOT NULL,
    product_id  BIGINT NOT NULL,
    quantity    INTEGER NOT NULL,
    unit_price  NUMERIC(14, 2) NOT NULL,
    CONSTRAINT pk_order_line PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_order(order_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_line_product
        FOREIGN KEY (product_id) REFERENCES product(product_id),
    CONSTRAINT ck_line_no_positive CHECK (line_no > 0),
    CONSTRAINT ck_quantity_positive CHECK (quantity > 0),
    CONSTRAINT ck_unit_price_nonnegative CHECK (unit_price >= 0)
);

-- Supports a customer's order list page ordered by time.
CREATE INDEX idx_order_customer_created
    ON purchase_order (customer_id, created_at DESC);

-- Supports querying order lines by product and checking references on delete.
CREATE INDEX idx_line_product
    ON order_line (product_id);
```

Reading this schema through its business meaning:

1. `customer_id`, `product_id`, and `order_id` are surrogate keys. `email` and `sku` still require their own unique constraints because technical IDs do not prevent two customers from sharing an email or two products from sharing an SKU.
2. The primary key (`order_id`, `line_no`) allows `line_no = 1` to appear in multiple orders, but never twice **within the same order**. `SMALLINT` places a technical ceiling on line sequence numbers; if line counts could exceed 32,767, choose a wider type.
3. `NUMERIC(14,2)` expresses the two-decimal-place policy in this example. `unit_price` belongs to the currency recorded in `purchase_order.currency_code`; multi-currency arithmetic must have clear semantics before implementation. The currency `CHECK` here only verifies **three uppercase letters**, not whether it is a currently valid ISO 4217 code. If you need to validate against an active list of currency codes, use a reference table with a foreign key or an equivalent catalog synchronization mechanism.
4. `UNIQUE(email)` does not yet define a case-insensitive comparison policy. Agree on email storage rules before taking the schema to production.
5. `FOREIGN KEY` prevents inserting order lines referencing nonexistent customers, orders, or products. `ON DELETE RESTRICT` on order lines prevents deleting an order while lines still exist. Business operations such as transitioning `DRAFT → CONFIRMED` still require application logic or additional constraints: a status `CHECK` only restricts the **current value**, not the **transition order**.

If the order total is computed from its lines, do not add `total_amount` as an arbitrary duplicate column. When storing a total is needed for fast queries or accounting compliance, define the synchronization policy, rounding rules, taxes/discounts, and where responsibility for maintaining the total invariant resides.

## 6. Checking DBMS Capabilities: Same Idea, Different Syntax and Semantics

Do not port DDL verbatim between products simply by renaming data types. The table below is a **comparison guide**, not a substitute for the documentation of the actual deployed version/engine:

| Requirement | PostgreSQL 16 | MySQL 8.0, InnoDB | SQL Server 2022 |
|---|---|---|---|
| Auto-generated numeric ID | `GENERATED ... AS IDENTITY` | `AUTO_INCREMENT` | `IDENTITY(1,1)` |
| Exact decimal | `NUMERIC(p,s)` / `DECIMAL(p,s)` | `DECIMAL(p,s)` | `DECIMAL(p,s)` |
| Unicode string | `VARCHAR`/`TEXT` with appropriate DB encoding | `VARCHAR`/`TEXT` with a charset such as `utf8mb4` | Usually `NVARCHAR`, or `VARCHAR` with an appropriate UTF-8 collation |
| Point-in-time with timezone semantics | `TIMESTAMPTZ` | Must explicitly specify `TIMESTAMP`, `DATETIME`, and session/app conversion | `DATETIMEOFFSET` |
| Boolean type | `BOOLEAN` | `BOOLEAN` is an alias for `TINYINT(1)` | `BIT` |
| UUID | `UUID` | Typically `BINARY(16)` or `CHAR(36)` by convention | `UNIQUEIDENTIFIER` |
| JSON | `JSONB` or `JSON` | `JSON` | SQL Server 2022 typically stores JSON in strings and processes it via JSON functions |
| `CHECK` constraints | Supported | Enforced in versions 8.0.16 and later | Supported |

Common pitfalls caused by differences:

- **Constraint syntax:** `currency_code ~ '^[A-Z]{3}$'` is PostgreSQL's regular expression operator, not standard SQL. When porting to MySQL or SQL Server, rewrite it or use a currency lookup table, then test that the constraint is actually enforced.
- **Temporal types:** PostgreSQL `TIMESTAMPTZ`, MySQL `TIMESTAMP`, and SQL Server `DATETIMEOFFSET` are not completely equivalent. In SQL Server, the historical `TIMESTAMP` type name is a synonym for `ROWVERSION`, **not** a date-time type.
- **Unicode and comparison:** charsets/collations can cause two different strings to compare as equal, affecting `UNIQUE`, `ORDER BY`, lookups, and indexes. MySQL's `BOOLEAN` is a tiny integer type, so 0/1 value bounds may require explicit control.
- **`NULL` and `UNIQUE`:** different DBMSs handle uniqueness of null values differently. A design like "email is optional, but unique when present" must be verified against the specific product.
- **Foreign keys and indexes:** not every DBMS automatically creates an index on the referencing foreign key column. Inspect query plans, delete/update operations, and engine behavior rather than assuming everything optimizes itself.

### Version-Specific Limits to Look Up

When choosing types and building migrations, check the official documentation for the exact DBMS/version/engine regarding:

1. **Data length and row size:** column limits, row limits, string/JSON/LOB value sizes, column count, and practical row counts.
2. **Precision and numeric ranges:** maximum digits for `DECIMAL/NUMERIC`, rounding/casting behavior, date-time range, timezones, and `NULL` handling.
3. **Index limits:** key length in bytes, column count, supported index types, collations, indexable types, and write overhead.
4. **Constraint capabilities:** whether `CHECK` is enforced, which engines support foreign keys, generated columns, deferred constraints, partial/filtered indexes, and schema change capabilities.
5. **Operational capacity:** table/index size, partitioning, connection/transaction limits, log growth, and lock duration during migrations.

For example, `VARCHAR(255)` looks small in terms of "character count", yet index key length can become an issue if the charset uses multiple bytes per character and the DBMS enforces index limits in bytes. Because thresholds vary by version and configuration, measure against the **actual configuration** instead of writing down a universal limit for all DBMSs.

## 7. Indexes and Physical Layout Must Derive from Queries

An index serves a specific access path; every index adds storage and write overhead. Start with queries whose frequency and latency matter, for example:

```sql
-- Goal: 20 most recent orders for a customer.
EXPLAIN
SELECT order_id, order_status, created_at
FROM purchase_order
WHERE customer_id = 1001
ORDER BY created_at DESC
LIMIT 20;
```

The `(customer_id, created_at DESC)` index is proposed because the filter uses `customer_id` and results must be sorted by `created_at` descending. However, not every execution will use the index: PostgreSQL chooses a plan based on statistics, row count, and selectivity. Use `EXPLAIN` to inspect the plan; only run `EXPLAIN ANALYZE` in an appropriate test environment when you accept **actually executing** the query and paying its cost.

The primary key `(order_id, line_no)` usually serves retrieving lines within an order well; finding *all lines for a product* by `product_id` requires a different access path, hence `idx_line_product`. Do not index every column just because it frequently appears in the table.

For large tables, consider partitioning, compression, historical archiving, and reorganizing physical layout **after** gathering evidence from real workloads. Partitioning does not replace key or constraint design. Some DBMSs have special rules for unique keys, foreign keys, and partition pruning on partitioned tables; check them before adopting partitioning.

## 8. Verification After Translating to the Physical Model

Translation is only complete when the actual schema protects the defined requirements. On PostgreSQL, you can first inspect metadata:

```sql
SELECT column_name,
       data_type,
       is_nullable,
       character_maximum_length,
       numeric_precision,
       numeric_scale
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'order_line'
ORDER BY ordinal_position;
```

Next, test behavior in a staging/test database using data with realistic distributions:

| Test Scenario | Expected Outcome |
|---|---|
| Insert a line with `quantity = 0` or `unit_price < 0` | DBMS rejects via `CHECK` |
| Insert a line for a nonexistent `order_id` or `product_id` | DBMS rejects via `FOREIGN KEY` |
| Insert two lines with the same (`order_id`, `line_no`) | DBMS rejects via primary key |
| Insert an order with `order_status = 'UNKNOWN'` | DBMS rejects via `CHECK` |
| Insert an amount exceeding `NUMERIC(14,2)` range | DBMS rejects or applies a rounding rule that must be explicitly verified at the boundary |
| Write/read a timestamp across two different session timezones | Same **actual point in time**, displayed in different timezone offsets |
| Insert two emails differing only in letter case | Verify and align result with the agreed comparison policy |
| Query a customer's latest orders on large data | Inspect `EXPLAIN`, latency, read I/O, and index write overhead |

**Boundary testing** includes empty strings and Unicode, values near numeric limits, `NULL` data, month-end dates, DST transitions, missing foreign keys, and duplicate records after normalization. **Migration testing** includes converting legacy data to new types, running application queries before/after, rollback capability, and lock duration on large tables.

For type changes on a live system, compare old and new value domains and find violating rows before applying `ALTER TABLE`. Narrowing `VARCHAR`, reducing `NUMERIC` precision/scale, or implicitly shifting timezones can cause data loss even when the DDL syntax is valid.

## 9. When Not Using a Relational Database

The goal of data modeling remains protecting semantics; the implementation depends on query needs and DBMS limits:

| System Type | Translating Logical to Physical | Risks/Limits to Verify |
|---|---|---|
| **Document** | An order can be a document embedding order metadata and an array of order lines; store transaction price as a snapshot | Document size limits, nesting depth, array updates, indexing nested fields, schema validation, and references to customers/products |
| **Graph** | Customers, orders, and products are nodes; purchase/contains relationships are edges with appropriate properties | Supported property types, uniqueness and cardinality support, cost of traversing high-degree nodes, transaction boundaries |
| **Analytical/columnar** | Sales events go into fact tables, customers/products/dates into dimensions at a declared grain | Ingestion latency, duplicate events, dimension keys, slowly changing dimensions (SCD), partitioning, column encoding, numeric precision |

For example, `OrderLine` in an OLTP relational system is designed to control transactions; in an analytical warehouse it may become a fact table at the grain of **one order line per order**. Grain, price history, and currency must be preserved. Copying an OLTP table structure straight into a fact table without defining grain and transformation rules easily leads to double-counting revenue.

Document databases are not automatically faster than relational ones, graph databases do not automatically fit every many-to-many relationship, and storing JSON does not absolve you from schema validation. Every DBMS has its own boundaries around size, transactions, indexes, consistency, and schema evolution.

## 10. Physical Model Handoff Checklist

A deployment-ready design must at minimum answer the following points:

- **Traceability to logical model:** every table, column, key, and constraint maps back to a confirmed entity, attribute, or business rule.
- **Type semantics:** every attribute has an explicit type, bounds, `NULL` policy, measurement/currency unit, precision, timezone, and comparison rules.
- **DBMS compatibility:** version, engine, charset/collation, and limits directly impacting the schema are confirmed; DDL has been tested on the target product.
- **Relational integrity:** primary keys, unique keys, foreign keys, delete/update behaviors, and historical rules match business requirements.
- **Access paths:** indexes are justified by concrete queries; query plans, read/write load, and storage footprint have been measured.
- **Evolution:** migrations, legacy data handling plans, boundary tests, and observability as data grows are in place.

### Self-Practice

Suppose a product initially sells only in VND, but after six months must support JPY and USD, accept orders from multiple timezones, and allow a single order to have hundreds of thousands of lines during wholesale events.

1. Identify three assumptions in the example DDL that need re-evaluation before scaling: `NUMERIC(14,2)` and currency rules, `SMALLINT` for `line_no`, and how delivery dates/order times are interpreted.
2. Separate changes driven by **business requirements** from changes driven by **data type/DBMS limits**. For instance, JPY and USD having different minor-unit rules is a business decision; the range of `SMALLINT` is a physical type limit.
3. Propose safe migrations and corresponding boundary test cases. Consider the difference between the point-in-time `created_at` and the calendar date `delivery_date`; do not automatically convert all dates into timestamps.

Only when you can explain *why* each data type, constraint, and index was chosen—and point out what happens when the data domain exceeds assumptions—does the physical model become a truly verified implementation of the logical model.
