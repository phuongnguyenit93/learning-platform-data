# Choosing Relational, Document, or Hybrid Models Based on Query Needs

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, authorization, backups, and operating relational databases. When storing data with flexible structure, the key question is not merely whether to use a JSON column or add a new table. You must choose a model where data correctness is easy to enforce, common queries can use indexes, updates do not create inconsistencies, and the system can still evolve as requirements change.

MySQL supports both the relational model and the JSON data type. The relational model expresses entities, relationships, and constraints via tables, keys, and foreign keys. The document model stores an aggregate with nested structure inside a single JSON document. The hybrid model keeps core data, relationships, and frequently queried attributes in relational columns, while using JSON for flexible attributes or clearly bounded snapshots.

There is no single best model for every system. Start from how the application reads, filters, joins, updates, and guarantees consistency. Then choose where data lives, design indexes, inspect execution plans, and measure on representative data.

## 1. Three Ways to Organize Data

### 1.1. Relational Model

The relational model splits data into tables with fixed structures. Each entity type has a primary key; relationships between entities are expressed using foreign keys or application-managed reference keys.

Example sales system:

~~~text
customers
  customer_id PK
  name
  email

orders
  order_id PK
  customer_id FK -> customers.customer_id
  created_at
  status

order_items
  order_item_id PK
  order_id FK -> orders.order_id
  product_id FK -> products.product_id
  quantity
  unit_price

products
  product_id PK
  sku
  name
  price
~~~

This model fits when entities have independent meaning, are referenced across multiple business workflows, and require unique constraints, foreign keys, joins, aggregations, and partial updates.

### 1.2. Document Model

The document model stores a business entity along with its nested attributes in one JSON document. For example, a UI configuration might hold a theme, widget list, positions, and per-widget options.

~~~json
{
  "theme": "dark",
  "layout": {
    "columns": 2,
    "density": "compact"
  },
  "widgets": [
    {
      "kind": "sales-chart",
      "position": 1,
      "options": {
        "period": "month",
        "showLegend": true
      }
    },
    {
      "kind": "alerts",
      "position": 2,
      "options": {
        "severity": ["high", "critical"]
      }
    }
  ]
}
~~~

If the application typically loads and saves the entire configuration as one unit, the nested structure reflects aggregate boundaries well. Widgets do not necessarily need to join with many other entities.

### 1.3. Hybrid Model

The hybrid model uses relational columns for stable data requiring constraints, and uses JSON for flexible parts that rarely participate in joins or are only read alongside their owning entity.

Example `products` table:

~~~sql
CREATE TABLE products (
    product_id BIGINT NOT NULL AUTO_INCREMENT,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    category_id BIGINT NOT NULL,
    attributes JSON NOT NULL,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_products_sku (sku),
    KEY ix_products_category (category_id)
) ENGINE = InnoDB;
~~~

The `sku`, `name`, `price`, and `category_id` columns have explicit types, indexes, and constraints. `attributes` holds properties that vary by product type, such as screen size, material, capacity, or technical specifications.

The hybrid model usually fits when the core of the domain has a stable structure while extended attributes vary across product groups or versions.

## 2. Choosing a Model from the Workload

Before creating tables, list the operations the application actually needs:

- Read one entity by ID or load an entire aggregate?
- Filter by which attributes?
- Does that attribute need to join with another table?
- Are unique constraints or foreign keys needed?
- Are grouping, sorting, range scans, or reports needed on that attribute?
- Does a change update a single value or multiple related entities?
- Does the data need to be shared and updated independently by multiple business flows?

### 2.1. When the Relational Model Fits

Prefer relational columns and separate tables when:

- Attributes have stable business meaning and appear in many queries.
- Frequent filtering, joining, grouping, sorting, or range scans are required.
- Values must enforce data types, NOT NULL, UNIQUE, CHECK, or foreign keys.
- Multiple entities reference the same value, such as customer, product, category, or account.
- A subset of data needs independent updates and separate transactions.
- Duplicate prevention or database-level integrity guarantees are required.

For example, customer email must be unique and is used for login. Putting email in a VARCHAR column with a unique index is clearer than searching and validating a JSON path on every operation.

### 2.2. When the Document Model Fits

Prefer JSON documents when:

- Data is typically read or written as a single aggregate.
- Nested attributes vary in structure across entity types.
- Most attributes are only read together with the parent entity.
- Individual nested elements do not need joins with other tables.
- Independent foreign keys or unique constraints are not needed on individual JSON elements.
- The application can validate document structure before writing.

For example, a personal configuration has user-specific preferences. If the application always reads the entire configuration, one document can be simpler than multiple child tables.

### 2.3. When the Hybrid Model Fits

Choose hybrid when:

- Some attributes are stable and require indexes, constraints, or joins.
- Extended parts differ in structure across entity types.
- JSON is accessed primarily alongside its owning row.
- Only a few JSON paths need filtering; generated columns or functional indexes can be created for those paths.
- Snapshots or metadata attached to a relational entity must be stored.

For example, an order keeps `customer_id`, `status`, `created_at`, and `total_amount` in relational columns; the shipping address finalized at order placement can be stored as a JSON snapshot. The snapshot address does not necessarily need to join with the customer's current address.

## 3. Decision Matrix

| Criterion | Relational | JSON Document | Hybrid |
|---|---|---|---|
| Structure | Stable, explicitly declared | Flexible, nested | Stable core, flexible extensions |
| Joins | Strong, direct | Harder, often needs extraction | Uses relational columns for primary joins |
| Foreign keys | Yes | Not directly applicable to JSON paths | Yes for relational part |
| Unique constraints | Direct | Requires extraction or separate checks | Direct for core, add index for JSON scalars |
| Aggregation and reporting | Straightforward | Requires JSON_TABLE or JSON expressions | Straightforward for main metrics |
| Schema evolution | Explicit migrations | Easy to add properties, harder to control variants | Add flexible properties while keeping core stable |
| Independent updates | Per row or table | Usually updates the document | Per entity and extension area |
| Best suited for | Relationship-dense domains | Aggregates read/written together | Mixed domains |

This is a guide for asking the right questions, not a performance leaderboard. A poorly indexed relational model can still be slow; a large document updated constantly can also incur heavy costs.

## 4. Design the Relational Core First

Identify concepts with independent lifecycles and rules before deciding to move data into JSON.

For example:

- Customer has its own identity, email, and status.
- Product has its own SKU, price, and category.
- Order has status, creation time, and owning customer.
- Order item has quantity, price at purchase time, and relationship to the order.

These are relational entities. If all of them were embedded into an order's JSON, it would be hard to guarantee customer existence, SKU uniqueness, per-product analytics, and independent product updates.

### 4.1. A Basic Relational Schema

~~~sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL AUTO_INCREMENT,
    email VARCHAR(254) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE = InnoDB;

CREATE TABLE products (
    product_id BIGINT NOT NULL AUTO_INCREMENT,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_products_sku (sku)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT NOT NULL AUTO_INCREMENT,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(14,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_orders_customer_date (customer_id, created_at),
    KEY ix_orders_status_date (status, created_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
) ENGINE = InnoDB;

CREATE TABLE order_items (
    order_item_id BIGINT NOT NULL AUTO_INCREMENT,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_item_id),
    KEY ix_order_items_order (order_id),
    KEY ix_order_items_product (product_id),
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders (order_id),
    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id)
        REFERENCES products (product_id),
    CONSTRAINT chk_order_items_quantity
        CHECK (quantity > 0)
) ENGINE = InnoDB;
~~~

The `unit_price` value in `order_items` is the price locked in for the order. It does not always equal the current price in `products`. This is an example of an intentional business snapshot: still stored in a relational column because numeric types, aggregations, and frequent queries are needed.

### 4.2. Do Not Turn JSON into a Dumping Ground for Everything

If every attribute sits inside one JSON column, the application must take responsibility for many things the database already handles well:

- Validating the type and presence of each property.
- Enforcing uniqueness across documents.
- Guaranteeing referential relationships.
- Creating indexes for queried paths.
- Handling concurrent updates to properties of the same document.
- Handling reporting and joins across many documents.

JSON does not eliminate schemas; it shifts part of the schema from database DDL to the application's data contract or validation layer.

## 5. What Is JSON in MySQL?

MySQL has a dedicated JSON data type. When writing a value to a JSON column, MySQL validates JSON syntax and stores it in an internal representation optimized for component access. A JSON column is not simply a VARCHAR holding raw JSON strings.

Example:

~~~sql
CREATE TABLE user_preferences (
    user_id BIGINT NOT NULL,
    preferences JSON NOT NULL,
    PRIMARY KEY (user_id)
) ENGINE = InnoDB;
~~~

You can store an object:

~~~sql
INSERT INTO user_preferences (user_id, preferences)
VALUES (
    1,
    JSON_OBJECT(
        'theme', 'dark',
        'language', 'vi',
        'notifications', JSON_OBJECT(
            'email', TRUE,
            'push', FALSE
        )
    )
);
~~~

MySQL verifies the data is valid JSON. However, syntactic JSON validity does not mean the document satisfies business rules. For instance, `theme` could accept an unsupported value without additional validation.

### 5.1. Objects, Arrays, and Scalars

JSON supports these value kinds:

- Object: collection of key/value pairs.
- Array: ordered list.
- String: Unicode text string.
- Number: numeric value.
- Boolean: `true` or `false`.
- Null: JSON's null value.

A JSON column can contain any valid object, array, or scalar. For business data design, clearly specify whether the root document is an object or array and the expected child structure.

### 5.2. JSON Does Not Preserve Original Text Formatting

MySQL parses and stores JSON in an internal representation. Do not rely on whitespace, key ordering, or original formatting to compare JSON strings. If digital signatures over the original payload are required, store the original string separately or canonicalize according to application rules before signing.

### 5.3. SQL NULL Differs from JSON null

SQL NULL indicates no SQL value. JSON null is a value inside the document. Three cases must be distinguished when filtering:

- The JSON column is SQL NULL.
- The path does not exist in the document.
- The path exists and holds JSON null.

~~~sql
SELECT
    JSON_EXTRACT(preferences, '$.nickname') AS nickname_value,
    JSON_TYPE(JSON_EXTRACT(preferences, '$.nickname')) AS nickname_type
FROM user_preferences;
~~~

If the path does not exist, JSON_EXTRACT returns SQL NULL. If the path exists with JSON null, the result is a JSON null value. Define the meanings of missing, null, and empty string clearly in the data contract.

## 6. Reading and Extracting JSON

MySQL provides JSON functions to extract, inspect, and update document components.

### 6.1. JSON_EXTRACT

~~~sql
SELECT JSON_EXTRACT(
    preferences,
    '$.notifications.email'
) AS email_notification
FROM user_preferences
WHERE user_id = 1;
~~~

JSON_EXTRACT returns the JSON value at the path. If an SQL scalar string is needed for display or comparison, use JSON_UNQUOTE or the `->>` operator.

### 6.2. The -> and ->> Operators

~~~sql
SELECT
    preferences->'$.theme' AS theme_json,
    preferences->>'$.theme' AS theme_text
FROM user_preferences;
~~~

`->` is shorthand for JSON_EXTRACT. `->>` is equivalent to JSON_UNQUOTE(JSON_EXTRACT(...)) and returns the scalar representation with JSON quotes stripped.

### 6.3. JSON_CONTAINS_PATH

Check whether one or more paths exist:

~~~sql
SELECT JSON_CONTAINS_PATH(
    preferences,
    'one',
    '$.theme',
    '$.notifications.email'
) AS has_required_path
FROM user_preferences;
~~~

`one` means at least one path exists; `all` means all listed paths must exist.

### 6.4. JSON_CONTAINS

Check whether a candidate is contained in the document or at a path:

~~~sql
SELECT user_id
FROM user_preferences
WHERE JSON_CONTAINS(
    preferences,
    JSON_QUOTE('dark'),
    '$.theme'
);
~~~

With arrays:

~~~sql
SELECT product_id
FROM products
WHERE JSON_CONTAINS(
    attributes,
    JSON_QUOTE('sale'),
    '$.tags'
);
~~~

JSON_CONTAINS compares using JSON semantics. Do not assume it behaves like `LIKE` on text strings.

### 6.5. JSON_TYPE and JSON_LENGTH

~~~sql
SELECT
    JSON_TYPE(attributes) AS root_type,
    JSON_LENGTH(attributes, '$.tags') AS tag_count
FROM products;
~~~

JSON_TYPE identifies the JSON value kind; JSON_LENGTH returns the object/array element count or scalar length per function semantics. These can inspect structure before processing, though they do not replace full validation.

## 7. Updating Documents

### 7.1. JSON_SET

JSON_SET inserts a missing path or replaces an existing path's value:

~~~sql
UPDATE user_preferences
SET preferences = JSON_SET(
    preferences,
    '$.theme', 'light',
    '$.notifications.email', FALSE
)
WHERE user_id = 1;
~~~

### 7.2. JSON_REPLACE

JSON_REPLACE replaces only paths that already exist:

~~~sql
UPDATE user_preferences
SET preferences = JSON_REPLACE(
    preferences,
    '$.theme', 'contrast'
)
WHERE user_id = 1;
~~~

If the path does not exist, JSON_REPLACE does not add it.

### 7.3. JSON_INSERT

JSON_INSERT inserts only paths that do not exist yet:

~~~sql
UPDATE user_preferences
SET preferences = JSON_INSERT(
    preferences,
    '$.density', 'compact'
)
WHERE user_id = 1;
~~~

### 7.4. JSON_REMOVE

~~~sql
UPDATE user_preferences
SET preferences = JSON_REMOVE(
    preferences,
    '$.legacyOption'
)
WHERE user_id = 1;
~~~

### 7.5. JSON_ARRAY_APPEND and JSON_ARRAY_INSERT

Append an element to an array:

~~~sql
UPDATE products
SET attributes = JSON_ARRAY_APPEND(
    attributes,
    '$.tags',
    'featured'
)
WHERE product_id = 10;
~~~

Insert at a specified array position:

~~~sql
UPDATE products
SET attributes = JSON_ARRAY_INSERT(
    attributes,
    '$.tags[0]',
    'new'
)
WHERE product_id = 10;
~~~

Before updating arrays, decide whether duplicates are allowed and who is responsible for deduplication. JSON arrays do not automatically enforce uniqueness across elements.

### 7.6. Updating One Path Is Still a Row UPDATE

JSON functions express partial document updates. MySQL can optimize certain in-place partial updates, yet you should not assume every JSON_SET writes only a few bytes or incurs no row-update cost. InnoDB still locks and versions the row per transaction; concurrent updates to the same row from multiple sessions can still contend.

If multiple flows frequently update independent attributes of the same large document, consider splitting data with independent lifecycles into separate rows or tables.

## 8. Indexing JSON Properties

A JSON column cannot be indexed like an ordinary B-tree across the entire document to serve arbitrary paths. You must choose the specific scalar paths or array memberships to query.

Common options:

1. A generated column extracting the scalar path, then indexing it.
2. A functional index on the JSON extraction expression if supported by your version.
3. A multi-valued index for certain JSON array forms since MySQL 8.0.17.
4. Normalizing values into a child table when joins, foreign keys, unique constraints, or rich reporting are needed.

### 8.1. Generated Column for a Scalar Path

Suppose `products.attributes` contains:

~~~json
{
  "brand": "Acme",
  "color": "black",
  "weight_grams": 850
}
~~~

If queries frequently filter by `brand`, create a generated column:

~~~sql
ALTER TABLE products
ADD COLUMN brand VARCHAR(80)
    GENERATED ALWAYS AS (
        JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand'))
    ) STORED,
ADD INDEX ix_products_brand (brand);
~~~

Queries can use the `brand` column:

~~~sql
SELECT product_id, sku, name
FROM products
WHERE brand = 'Acme';
~~~

A generated column brings a frequently queried path into the schema with an explicit type and index. Decide on VARCHAR length, character set/collation, and handling of missing paths or mistyped values.

### 8.2. Generated Column for Numbers

When extracting numbers, cast to an explicit SQL type:

~~~sql
ALTER TABLE products
ADD COLUMN weight_grams INT
    GENERATED ALWAYS AS (
        CAST(
            JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.weight_grams'))
            AS UNSIGNED
        )
    ) STORED,
ADD INDEX ix_products_weight (weight_grams);
~~~

Do not store numeric columns as strings if range comparisons are needed. String comparisons can give a different order than numbers, such as `'100'` vs. `'20'`.

### 8.3. Functional Index

On MySQL 8.0.13 and later, you can create a functional index:

~~~sql
CREATE INDEX ix_products_brand_expr
ON products (
    (CAST(attributes->>'$.brand' AS CHAR(80)))
);
~~~

The query expression must match the index expression according to optimizer rules. A named generated column is usually easier to read, reuse, and type-check when multiple queries use that same path.

### 8.4. Unique Index for a Scalar JSON Path

If a value inside JSON must be unique, you can extract it into a generated column and create a unique index:

~~~sql
ALTER TABLE products
ADD COLUMN external_code VARCHAR(64)
    GENERATED ALWAYS AS (
        JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.external_code'))
    ) STORED,
ADD UNIQUE KEY uq_products_external_code (external_code);
~~~

Define clearly how missing paths or JSON null behave. Unique indexes allow multiple SQL NULLs in MySQL, so if every product must have `external_code`, add appropriate validation such as a CHECK on path existence and type rules.

Generated columns can be indexed, yet do not turn arbitrary JSON paths into full relations. Do not rely on generated columns to replace foreign keys across JSON paths; store reference keys as relational columns when referential integrity is needed.

### 8.5. Multi-Valued Index for JSON Arrays

MySQL 8.0.17+ supports multi-valued indexes for certain JSON array expressions. For instance, `tags` is a string array:

~~~json
{
  "tags": ["sale", "featured", "summer"]
}
~~~

You can create the index:

~~~sql
CREATE INDEX ix_products_tags
ON products (
    (CAST(attributes->'$.tags' AS CHAR(32) ARRAY))
);
~~~

Membership query:

~~~sql
SELECT product_id, sku, name
FROM products
WHERE 'sale' MEMBER OF (attributes->'$.tags');
~~~

A multi-valued index creates multiple index entries for one row, corresponding to the array elements per the declared expression. It has type and expression limits and is not a universal index for all JSON structures.

### 8.6. Limitations of Multi-Valued Indexes

- Each row can generate many index entries; large arrays bloat index size.
- Cannot be used like an ordinary B-tree index to provide arbitrary sort orders or range queries.
- Does not replace a relational table when array elements need foreign keys, their own attributes, independent updates, or unique constraints.
- Must use supported query expressions so the optimizer can leverage the index.
- Inspect EXPLAIN on your exact MySQL version and realistic data.

If `tags` needs to join with a tag catalog, manage per-tag status, or aggregate many-to-many relationships, a `product_tags` table is usually clearer and easier to constrain than a JSON array.

## 9. JSON_TABLE: Turning Documents into Relational Rows

JSON_TABLE projects JSON data into a set of rows and columns for JOINs, filtering, or aggregation. MySQL has supported JSON_TABLE since 8.0.4.

Suppose a document has an `items` array:

~~~json
{
  "order_id": 9001,
  "items": [
    {"sku": "KB-01", "quantity": 2, "unit_price": 35.50},
    {"sku": "MS-02", "quantity": 1, "unit_price": 18.00}
  ]
}
~~~

Extract the items:

~~~sql
SELECT
    jt.sku,
    jt.quantity,
    jt.unit_price
FROM order_documents AS d,
JSON_TABLE(
    d.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku',
        quantity INT PATH '$.quantity',
        unit_price DECIMAL(12,2) PATH '$.unit_price'
    )
) AS jt
WHERE d.document_id = 1;
~~~

JSON_TABLE turns each element in `$.items[*]` into a row. Columns are extracted by the declared paths. You can use that result to compute totals:

~~~sql
SELECT
    d.document_id,
    SUM(jt.quantity * jt.unit_price) AS document_total
FROM order_documents AS d,
JSON_TABLE(
    d.document,
    '$.items[*]'
    COLUMNS (
        quantity INT PATH '$.quantity',
        unit_price DECIMAL(12,2) PATH '$.unit_price'
    )
) AS jt
GROUP BY d.document_id;
~~~

JSON_TABLE is useful for migrations, reports, or reading documents containing arrays. However, if queries routinely must expand a large array, join with other tables, and aggregate per element, that is a signal to consider normalizing the array into a child table.

### 9.1. Handling Missing Paths and Type Conversion Errors

JSON_TABLE lets you define behavior when a path does not exist or conversion fails using ON EMPTY and ON ERROR clauses. Decide which fields are optional, which are mandatory, and which defaults make sense.

Example declaring required columns:

~~~sql
JSON_TABLE(
    d.document,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(64) PATH '$.sku' ERROR ON EMPTY ERROR ON ERROR,
        quantity INT PATH '$.quantity' ERROR ON EMPTY ERROR ON ERROR
    )
) AS jt
~~~

Validation should match the document contract. Do not use arbitrary DEFAULT values to silently turn malformed data into a fake valid value.

## 10. Constraining JSON Structure

MySQL validates JSON syntax on write to a JSON column, yet business logic often requires extra rules:

- The root must be an object.
- Certain keys must exist.
- Key types must be accurate.
- Values must belong to an allowed enum.
- Numbers must stay within valid bounds.
- Arrays must have bounded element counts or no duplicates.

### 10.1. Checking Types and Paths with CHECK

~~~sql
CREATE TABLE product_metadata (
    product_id BIGINT NOT NULL,
    attributes JSON NOT NULL,
    PRIMARY KEY (product_id),
    CONSTRAINT chk_attributes_object
        CHECK (JSON_TYPE(attributes) = 'OBJECT'),
    CONSTRAINT chk_attributes_brand
        CHECK (
            JSON_CONTAINS_PATH(attributes, 'one', '$.brand')
        )
) ENGINE = InnoDB;
~~~

CHECK constraints are enforced starting in MySQL 8.0.16. Prior to this version, CHECK syntax may be parsed yet not enforced as a constraint. When supporting multiple versions, verify exact version and runtime behavior.

### 10.2. JSON Schema Validation

MySQL 8.0.17+ provides JSON_SCHEMA_VALID to validate documents against supported JSON Schema:

~~~sql
CREATE TABLE user_profiles (
    user_id BIGINT NOT NULL,
    profile JSON NOT NULL,
    PRIMARY KEY (user_id),
    CONSTRAINT chk_profile_schema
        CHECK (
            JSON_SCHEMA_VALID(
                '{
                  "type": "object",
                  "required": ["tier"],
                  "properties": {
                    "tier": {
                      "type": "string",
                      "enum": ["basic", "pro", "enterprise"]
                    }
                  }
                }',
                profile
            )
        )
) ENGINE = InnoDB;
~~~

JSON Schema validation helps centralize part of the data contract in the database. Check the dialect and keywords supported by MySQL; do not assume all modern JSON Schema features are available.

### 10.3. Application Validation Is Still Essential

Database constraints protect data even when multiple clients write. Applications still need validation to return clear error messages, check permissions, and apply user-context rules. Do not rely solely on the UI or a single service if batch jobs, imports, or admin tools also write directly.

## 11. When Should a JSON Array Be Split into a Relational Table?

An array should become a child table if its elements exhibit one or more of these traits:

- Have their own identity.
- Are updated independently.
- Are referenced by multiple documents or entities.
- Require unique constraints or foreign keys.
- Need frequent filtering, joining, grouping, sorting, or reporting.
- Can grow large and do not need to be loaded with the parent document.
- Multiple transactions update different elements and need reduced contention on the same parent row.

### 11.1. Example Turning Tags into a Many-to-Many Relationship

If tags are just small display labels rarely queried, a JSON array may suffice. If tags have a catalog and are used in reporting:

~~~sql
CREATE TABLE tags (
    tag_id BIGINT NOT NULL AUTO_INCREMENT,
    tag_name VARCHAR(80) NOT NULL,
    PRIMARY KEY (tag_id),
    UNIQUE KEY uq_tags_name (tag_name)
) ENGINE = InnoDB;

CREATE TABLE product_tags (
    product_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    PRIMARY KEY (product_id, tag_id),
    KEY ix_product_tags_tag (tag_id, product_id),
    CONSTRAINT fk_product_tags_product
        FOREIGN KEY (product_id)
        REFERENCES products (product_id),
    CONSTRAINT fk_product_tags_tag
        FOREIGN KEY (tag_id)
        REFERENCES tags (tag_id)
) ENGINE = InnoDB;
~~~

Now you can find products by tag, count products per tag, and guarantee tags exist:

~~~sql
SELECT p.product_id, p.sku, p.name
FROM products AS p
JOIN product_tags AS pt
  ON pt.product_id = p.product_id
JOIN tags AS t
  ON t.tag_id = pt.tag_id
WHERE t.tag_name = 'sale';
~~~

The relational model is clearer once each array element has become a business entity.

### 11.2. Order Items Example

If order items require:

- Total revenue by SKU.
- Verifying product existence.
- Per-line updates.
- Joining with warehouse inventory.
- Counting quantities per product.

then an `order_items` table fits better than storing all items inside an `orders` JSON column.

You can still store a JSON snapshot of external requests or payloads for auditing, while business data needing constraints and reporting belongs in relational tables.

## 12. Snapshots, History, and Source-of-Truth Data

Not all duplicated data is bad denormalization. A snapshot can be the right business decision if it represents a point-in-time value.

For example, an order needs to store the shipping address at placement time:

~~~sql
CREATE TABLE orders (
    order_id BIGINT NOT NULL AUTO_INCREMENT,
    customer_id BIGINT NOT NULL,
    shipping_address_snapshot JSON NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY ix_orders_customer_date (customer_id, created_at)
) ENGINE = InnoDB;
~~~

The snapshot address does not automatically change when the customer updates their profile address. It is a point-in-time capture at the transaction moment. To look up the current address, reference a separate `customer_addresses` table.

### 12.1. JSON Snapshots Are Not the Source of Truth for All Queries

If an application stores a copy of product names, prices, and addresses in JSON to render invoices, define:

- At what moment is the snapshot captured?
- Who is allowed to update it?
- Can it be edited after the order completes?
- Do revenue reports use snapshot prices or current prices?
- Should a version or checksum be stored?

Do not use snapshots in place of source tables when current state updates or referential integrity are required.

### 12.2. Event Payloads and Auditing

JSON fits storing external event payloads whose schema evolves across versions. However, if frequent queries filter by `event_type`, `tenant_id`, `occurred_at`, or `actor_id`, consider elevating those fields to relational columns and keeping the remaining payload in JSON.

## 13. Concurrent Updates and Aggregate Boundaries

A JSON document bundles many attributes into one row. This is convenient when attributes are read/written together, but can increase contention if multiple flows update independent parts of the same document.

### 13.1. One Document, Multiple Writers

Suppose a profile has:

~~~json
{
  "notification_settings": {"email": true},
  "display_settings": {"theme": "dark"}
}
~~~

One request updates email notifications; another updates theme. Both UPDATE the same row. InnoDB coordinates row locks and transactions; updates may have to wait for one another.

If two attribute groups have high, independent update rates, splitting them into separate tables can reduce contention and let each transaction lock a smaller scope.

### 13.2. Conditional Updates

When writing JSON based on previously read state, you can use optimistic concurrency via a version column:

~~~sql
ALTER TABLE user_preferences
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
~~~

The application reads the version and then updates:

~~~sql
UPDATE user_preferences
SET preferences = JSON_SET(preferences, '$.theme', 'light'),
    version = version + 1
WHERE user_id = 1
  AND version = 7;
~~~

If affected rows equals 0, the version changed or the row no longer exists; the application must re-read and resolve the conflict. This mechanism is useful when detecting lost updates per the application contract.

### 13.3. JSON Does Not Replace Multi-Table Transactions

If an action updates a JSON document while simultaneously deducting inventory, recording a payment, or creating order items, use an InnoDB transaction so related changes commit or roll back together.

## 14. Document Size and Operational Costs

The larger a document and the more attributes and arrays it contains, the more you must consider:

- Row size and read/write I/O cost.
- Number of paths the application must understand.
- JSON extraction CPU cost in queries.
- Number of additional indexes and storage footprint.
- Number of writers updating the same row.
- Impact on logs, backups, replication, and network payload transfer.

### 14.1. Do Not Stuff Unbounded Data into One Document

Do not place transaction histories, thousands of log entries, or endlessly growing item lists into a single row's JSON array. Loading or updating the document becomes progressively more expensive; a huge row also becomes a contention hotspot.

Split unbounded collections into a child table with a parent key and an index on time or business sequence.

### 14.2. Depth Limits and Validation

MySQL enforces a JSON nesting depth limit and can reject overly deep documents. Applications should enforce a smaller domain-appropriate limit rather than letting data become hard-to-process deep trees.

### 14.3. Do Not Use JSON for Binary Data

JSON fits text-structured data. Large binary content should be stored in BLOBs or object storage; the document can hold metadata and reference identifiers.

## 15. MySQL Version Notes

Several JSON and indexing features were added across releases. When deploying, check `SELECT VERSION()` and the exact version's documentation.

| Feature | Minimum MySQL Version |
|---|---|
| JSON data type | 5.7.8 |
| JSON `->` operator | 5.7.9 |
| JSON `->>` operator | 5.7.13 |
| JSON_TABLE | 8.0.4 |
| Functional index | 8.0.13 |
| Enforced CHECK constraints | 8.0.16 |
| Multi-valued index | 8.0.17 |
| JSON_SCHEMA_VALID | 8.0.17 |
| JSON_VALUE | 8.0.21 |

Examples in this lesson target modern MySQL 8.0. If a system uses an older version, you may need generated columns instead of functional indexes, application validation instead of enforced CHECK constraints, or a different design for JSON arrays.

## 16. Reading Execution Plans for JSON Queries

Do not assume JSON paths are automatically indexed. Inspect the plan of actual queries.

### 16.1. Query Without a Path Index

~~~sql
EXPLAIN
SELECT product_id, sku, name
FROM products
WHERE attributes->>'$.brand' = 'Acme';
~~~

Without a matching functional index or generated column, MySQL may have to read many rows and extract the path to filter.

### 16.2. Query Through a Generated Column

~~~sql
EXPLAIN
SELECT product_id, sku, name
FROM products
WHERE brand = 'Acme';
~~~

Inspect `possible_keys`, `key`, `rows`, `filtered`, and `Extra`. If the optimizer picks `ix_products_brand`, the query can seek via the index instead of evaluating the path on every row.

### 16.3. EXPLAIN ANALYZE

On MySQL 8.0.18+:

~~~sql
EXPLAIN ANALYZE
SELECT product_id, sku, name
FROM products
WHERE brand = 'Acme';
~~~

EXPLAIN ANALYZE executes the query and reports actual rows, loops, and iterator timing. Run on representative data; a tiny lab table cannot prove an index will improve a production workload.

### 16.4. Monitor Write Overhead Too

Adding generated columns or indexes helps certain read queries, yet increases INSERT/UPDATE cost and storage. If `attributes` changes frequently, every index depending on a JSON path must also be maintained.

Measure all of:

- Read query latency and throughput.
- Write duration and updated row counts.
- Index storage size.
- Rate of missing paths or mistyped values.
- Actual number of rows read.

## 17. Modeling Workflow

Apply the following workflow to each data group:

1. List entities and identify independent lifecycles.
2. Determine the grain of each row and one-to-one, one-to-many, or many-to-many relationships.
3. List primary read/write queries, filter columns, joins, grouping, sorting, and ranges.
4. Put keys, relationships, attributes needing uniqueness, and reporting metrics into the relational model.
5. Group flexible attributes read/written together with an aggregate into JSON.
6. Identify JSON paths needing filtering; create generated columns, functional indexes, or multi-valued indexes if appropriate.
7. Split arrays into child tables if elements need keys, foreign keys, independent updates, or frequent reporting.
8. Define validation in both database and application.
9. Define maximum sizes, document versioning, and missing/null policies.
10. Use EXPLAIN and EXPLAIN ANALYZE to verify access paths.
11. Measure read workload, write workload, contention, and storage.
12. Document the source of truth and synchronization rules for any snapshots or derived data.

## 18. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Putting email or SKU in JSON despite uniqueness need | Hard to enforce uniqueness | Use relational columns and unique indexes |
| Embedding product IDs in an array when FKs are needed | Database does not validate per-element references | Use a join table |
| Storing numbers as JSON strings | Comparisons and type casting easily break | Standardize types or use a CASTed generated column |
| Querying many JSON paths without indexes | Reads many rows and evaluates expressions repeatedly | Generated column or functional index |
| Single document holding unbounded history | Huge rows, costly updates and reads | Split child tables by time or key |
| Using JSON arrays for reported many-to-many relations | Hard to join, group, and prevent duplicates | Normalize into a join table |
| Assuming valid JSON means valid business data | Keys may have wrong types or invalid values | CHECK, JSON Schema, and application validation |
| Treating snapshots as current source-of-truth | Current data and snapshot semantics diverge | Define source of truth and snapshot capture time |
| Multiple writers updating the same large document | Row-level contention | Split aggregates or use version checks |
| Indexing every JSON path | Increases storage footprint and write cost | Index only paths with clear workloads |
| Thinking JSON_TABLE is free | Array expansion and row processing still incur cost | Inspect plans; consider relational tables |
| Using JSON for large files or blobs | Payloads hard to query and transfer | BLOB or object storage, keeping metadata in JSON |

## 19. Practice Lab: Choosing a Model for a Product Catalog

Perform on MySQL 8.0 in a lab database. This exercise illustrates all three models: relational, JSON, and hybrid. Use a dedicated schema; do not run on production tables.

### 19.1. Create the Hybrid Table

~~~sql
CREATE TABLE lab_products (
    product_id BIGINT NOT NULL AUTO_INCREMENT,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(150) NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    attributes JSON NOT NULL,
    brand VARCHAR(80)
        GENERATED ALWAYS AS (
            JSON_UNQUOTE(JSON_EXTRACT(attributes, '$.brand'))
        ) STORED,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_lab_products_sku (sku),
    KEY ix_lab_products_brand (brand)
) ENGINE = InnoDB;
~~~

`sku`, `name`, and `price` are core data. `brand` is extracted into a generated column for indexed filtering; other attributes remain flexible inside JSON.

### 19.2. Load Data

~~~sql
INSERT INTO lab_products (sku, name, price, attributes)
VALUES
    (
        'KB-01',
        'Mechanical Keyboard',
        79.90,
        JSON_OBJECT(
            'brand', 'Acme',
            'switch', 'brown',
            'layout', 'US',
            'tags', JSON_ARRAY('office', 'featured')
        )
    ),
    (
        'MS-02',
        'Wireless Mouse',
        29.50,
        JSON_OBJECT(
            'brand', 'Acme',
            'dpi', 1600,
            'color', 'black',
            'tags', JSON_ARRAY('office', 'sale')
        )
    ),
    (
        'HD-03',
        'Headset',
        59.00,
        JSON_OBJECT(
            'brand', 'Northwind',
            'wireless', TRUE,
            'color', 'black',
            'tags', JSON_ARRAY('audio')
        )
    );
~~~

### 19.3. Query a Scalar JSON Property

~~~sql
SELECT
    product_id,
    sku,
    attributes->>'$.color' AS color
FROM lab_products
WHERE attributes->>'$.color' = 'black';
~~~

Read EXPLAIN and observe whether the query uses an index. Currently there is no index for `color`.

### 19.4. Query Through the Generated Column

~~~sql
EXPLAIN
SELECT product_id, sku, name
FROM lab_products
WHERE brand = 'Acme';
~~~

Observe that `key` may be `ix_lab_products_brand`. Compare against querying directly on the JSON path:

~~~sql
EXPLAIN
SELECT product_id, sku, name
FROM lab_products
WHERE attributes->>'$.brand' = 'Acme';
~~~

### 19.5. Query an Array

~~~sql
SELECT product_id, sku
FROM lab_products
WHERE JSON_CONTAINS(
    attributes,
    JSON_QUOTE('sale'),
    '$.tags'
);
~~~

If tag membership queries are frequent and MySQL is 8.0.17+, test a multi-valued index in the lab environment. If tags need a catalog and many-to-many relationships, create `tags`/`product_tags` tables instead of keeping an array.

### 19.6. Create Relational Tables for Tags

~~~sql
CREATE TABLE lab_tags (
    tag_id BIGINT NOT NULL AUTO_INCREMENT,
    tag_name VARCHAR(50) NOT NULL,
    PRIMARY KEY (tag_id),
    UNIQUE KEY uq_lab_tags_name (tag_name)
) ENGINE = InnoDB;

CREATE TABLE lab_product_tags (
    product_id BIGINT NOT NULL,
    tag_id BIGINT NOT NULL,
    PRIMARY KEY (product_id, tag_id),
    KEY ix_lab_product_tags_tag (tag_id, product_id),
    CONSTRAINT fk_lab_product_tags_product
        FOREIGN KEY (product_id)
        REFERENCES lab_products (product_id),
    CONSTRAINT fk_lab_product_tags_tag
        FOREIGN KEY (tag_id)
        REFERENCES lab_tags (tag_id)
) ENGINE = InnoDB;
~~~

Load tags and relationships:

~~~sql
INSERT INTO lab_tags (tag_name)
VALUES ('office'), ('featured'), ('sale'), ('audio');

INSERT INTO lab_product_tags (product_id, tag_id)
SELECT p.product_id, t.tag_id
FROM lab_products AS p
JOIN lab_tags AS t
  ON JSON_CONTAINS(
       p.attributes,
       JSON_QUOTE(t.tag_name),
       '$.tags'
     );
~~~

Compare the `JSON_CONTAINS` query with joining through the relational table. Evaluate readability, indexing, referential integrity checks, and sync overhead if `tags` is still retained in JSON.

### 19.7. JSON_TABLE for Reporting

~~~sql
SELECT
    p.sku,
    jt.tag
FROM lab_products AS p,
JSON_TABLE(
    p.attributes,
    '$.tags[*]'
    COLUMNS (
        tag VARCHAR(50) PATH '$'
    )
) AS jt
ORDER BY p.sku, jt.tag;
~~~

Observe how an array is transformed into multiple rows. If tag-based reporting and joins occur frequently, the `lab_product_tags` table may fit better.

### 19.8. Clean Up Lab Tables

~~~sql
DROP TABLE lab_product_tags;
DROP TABLE lab_tags;
DROP TABLE lab_products;
~~~

Drop only the lab tables just created.

### 19.9. Expected Outcomes

- Explain why `sku` must be a relational column with a unique index.
- Identify when flexible attributes fit inside JSON.
- Create a generated column and read EXPLAIN for the `brand` query.
- Explain why JSON arrays do not automatically provide foreign keys or unique constraints per element.
- Compare JSON_CONTAINS, multi-valued indexes, and join tables.
- Use JSON_TABLE to expand arrays into rows.
- Choose an appropriate model based on query workload, consistency, and updatability.

## 20. Checklist Before Finalizing a Schema

### Data and Domain

- Does each entity have its own identity and lifecycle?
- Which attributes are required, unique, or bounded in domain?
- Which values are point-in-time transaction snapshots?
- What do missing, SQL NULL, JSON null, and default values mean?

### Queries

- Which columns appear in WHERE, JOIN, GROUP BY, and ORDER BY?
- Which JSON paths are queried frequently?
- Do arrays require membership checks, joins, or aggregations?
- Can queries use generated columns, functional indexes, or multi-valued indexes?

### Integrity

- Are foreign keys needed to individual elements?
- Is uniqueness needed across documents?
- Are CHECK or JSON Schema validations needed?
- Do multiple writers update the same document?

### Operations

- Can documents grow unbounded in size?
- Is there a schema versioning or document migration process?
- Can generated data or indexes be rebuilt?
- Can backups, replication, and logging sustain the payload sizes?
- Is read access restriction needed for sensitive fields inside JSON?

## 21. Principles to Remember

- Choose the model from query workload, business relationships, consistency, and data lifecycle.
- Use the relational model for independent entities, keys, foreign keys, unique constraints, and frequent reporting.
- Use JSON documents for aggregates with flexible structure that are usually read/written together and do not need independent relationships per element.
- The hybrid model keeps strongly typed and indexed core columns while using JSON for extended attributes or snapshots.
- Syntactically valid JSON is not necessarily business-valid; validate in both database and application.
- SQL NULL, missing paths, and JSON null are distinct states.
- Do not rely on JSON key order or whitespace to determine content.
- Indexing JSON paths requires an appropriate generated column, functional index, or multi-valued index; there is no universal index across all paths.
- Use relational columns for values requiring foreign keys; do not assume JSON paths enforce referential integrity automatically.
- Split JSON arrays into child tables when elements need identity, independent updates, uniqueness, foreign keys, joins, or reporting.
- JSON_TABLE is useful for turning documents into rows, but is not free; measure cost if used frequently.
- A large document can increase read/write cost and contention if multiple writers update the same row.
- Snapshots are point-in-time data; define the source of truth and synchronization rules clearly.
- Check MySQL version before using functional indexes, CHECK enforcement, multi-valued indexes, JSON Schema validation, or JSON_TABLE.
- Use EXPLAIN and EXPLAIN ANALYZE to verify access paths and timings on representative data.
- Measure read workload, write workload, index storage, contention, and operations before finalizing the model.

Good design does not depend on using more JSON or more relational tables. What matters is placing every piece of data where correctness can be guaranteed and queries run efficiently: relational for entities, keys, and relationships; JSON for flexible structures belonging to an aggregate; and a hybrid model for systems needing both. Let query workloads and business constraints determine the boundary, then verify the choice with execution plans and real measurements.
