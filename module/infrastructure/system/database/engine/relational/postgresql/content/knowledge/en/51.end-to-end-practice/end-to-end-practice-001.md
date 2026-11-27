# Building an Order Management Database with Schemas and Constraints

An order management system needs to store customers, products, inventory, orders, individual line items, and payments. These data sets are tightly interrelated: an order must belong to a customer, a line item must point to a valid product, quantity must be positive, the price at the time of purchase must be preserved, and inventory stock must not become negative. Relying solely on application code for validation risks creating inconsistent data if a bug occurs in an API, worker, or administrative script.

PostgreSQL enables modeling these rules directly in the database using schemas, primary keys, foreign keys, unique constraints, check constraints, defaults, generated columns, and indexes. Transactions combined with constraints ensure that multiple related changes are committed or rolled back together. This lesson builds an order management model from scratch, explains design decisions, and practices creating orders, reserving inventory, processing payments, querying, testing, and safely evolving the schema.

## 1. Defining Requirements and Business Rules

Before creating tables, describe the data and the invariants the system must uphold. A foundational model consists of six entities:

| Entity | Information Stored | Key Relationships |
|---|---|---|
| customers | Customers and contact email | One customer has many orders |
| products | SKU, name, current price, and active sales status | One product appears in many order line items |
| inventory | Sellable stock quantity | Each product has one inventory record |
| orders | Order, buyer, status, currency, and shipping address | One order has many line items and many payment attempts |
| order_items | Product, quantity, and price captured at order placement | Each line belongs to one order and references one product |
| payments | Payment requests or recorded payment events | One order may have multiple payment attempts |

Initial business rules:

1. Each customer has a non-empty email; emails are compared case-insensitively.
2. Each product has a non-empty SKU; SKUs cannot duplicate regardless of letter case.
3. Product prices are non-negative. A discontinued product remains in the database to preserve order history.
4. Inventory quantities are non-negative.
5. An order must belong to an existing customer and have a unique order number.
6. Each order line item has a quantity greater than 0, a non-negative unit price at purchase time, and no duplicate product within the same order.
7. An order stores a snapshot of the product's name, SKU, and price at placement time. Subsequent changes to product name or price must not alter historical orders.
8. Each order creation request carries a stable idempotency key so clients can retry without creating duplicate orders.
9. Creating the order, reserving inventory, and writing order line items must occur within a single transaction.
10. Payments require a provider reference code to identify duplicate callbacks or webhooks.

This is an illustrative model for a store using a single currency per order. If the system requires multiple warehouses, multiple shipping addresses, regional taxes, coupons, returns, or multi-currency payments, it can be extended with dedicated tables. Avoid cramming all data into a single large table or a single JSONB column just to reduce table count.

## 2. Designing the Schema and Relationships

In PostgreSQL, a schema is a namespace containing objects such as tables, views, sequences, functions, and types. Isolating application tables into a dedicated schema prevents name collisions with extensions or system objects and supports object-group access control.

Create the schema:

    CREATE SCHEMA shop;

The name `shop` is used throughout this lesson. In a real-world application, a schema might be named after a bounded context or business module, such as `sales`, `catalog`, or `commerce`.

### Relationship Diagram

    customers 1 ─────── N orders
                           │
                           │ 1
                           │
                           N
                       order_items N ─────── 1 products
                                                   │
                                                   │ 1
                                                   │
                                                   1
                                               inventory

    orders 1 ─────── N payments

Each order can have multiple line items. A product can appear across many different orders. The `inventory` table holds the current stock count, while `order_items` stores historical data captured at purchase time. The `payments` table separates payment attempts from the order because a single order can have failed attempts, a successful attempt, or refunds.

### Choosing Primary Keys

Tables use `bigint GENERATED ALWAYS AS IDENTITY` so PostgreSQL generates auto-incrementing numeric keys. Identity columns are the modern declaration tied to a PostgreSQL-managed sequence. Internal numeric keys are compact and convenient for foreign keys and joins.

Do not use email, SKU, or `order_number` as primary keys because business values can change or require normalization. They can still be protected using unique constraints or unique indexes.

UUIDs can be used as primary keys if IDs must be generated across multiple nodes without depending on a central sequence. In this example, UUID is used for the idempotency key because the key represents a client request intent, while numeric keys remain suitable for internal relationships.

## 3. Creating the Customers and Products Tables

### The `customers` Table

    CREATE TABLE shop.customers (
        customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        email text NOT NULL,
        full_name text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT customers_email_not_blank
            CHECK (btrim(email) <> ''),
        CONSTRAINT customers_name_not_blank
            CHECK (btrim(full_name) <> '')
    );

`NOT NULL` prevents SQL `NULL` values. `CHECK` prevents empty strings or whitespace-only strings. These two rules are distinct: an empty string is not `NULL`, so `NOT NULL` alone is insufficient.

Emails are typically treated as case-insensitive for login workflows. Create a unique index on the normalized expression:

    CREATE UNIQUE INDEX customers_email_ci_uq
        ON shop.customers (lower(btrim(email)));

This index both accelerates lookups by normalized email and prevents two records with `User@example.com` and `user@example.com`. A standard unique constraint on a `text` column distinguishes those two strings under default comparison rules.

In large systems, define an explicit email normalization policy. Do not arbitrarily alter Unicode rules or local-part/domain handling unless specified by business requirements.

### The `products` Table

    CREATE TABLE shop.products (
        product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        sku text NOT NULL,
        product_name text NOT NULL,
        description text,
        unit_price numeric(12, 2) NOT NULL,
        currency char(3) NOT NULL DEFAULT 'VND',
        is_active boolean NOT NULL DEFAULT true,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT products_sku_not_blank
            CHECK (btrim(sku) <> ''),
        CONSTRAINT products_name_not_blank
            CHECK (btrim(product_name) <> ''),
        CONSTRAINT products_price_nonnegative
            CHECK (unit_price >= 0),
        CONSTRAINT products_currency_format
            CHECK (btrim(currency) ~ '^[A-Z]{3}$')
    );

    CREATE UNIQUE INDEX products_sku_ci_uq
        ON shop.products (lower(btrim(sku)));

`numeric(12,2)` stores exact decimal values to two decimal places, making it far more suitable than floating-point types for monetary prices. Do not use `real` or `double precision` for monetary amounts requiring exact reconciliation because they represent binary approximations.

`is_active` indicates whether a product is actively sold. Once a product appears in an order, mark it inactive instead of deleting it. The foreign key in `order_items` will protect historical references.

`currency` is stored to identify the price's monetary unit. Production systems must verify that the product currency matches the order currency inside the order-creation transaction. A `CHECK` constraint cannot query another table to enforce that rule.

### The `inventory` Table

    CREATE TABLE shop.inventory (
        product_id bigint PRIMARY KEY
            REFERENCES shop.products(product_id)
            ON DELETE RESTRICT,
        available_qty integer NOT NULL DEFAULT 0,
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT inventory_available_nonnegative
            CHECK (available_qty >= 0)
    );

Each product has at most one inventory record. The primary key `product_id` also serves as a foreign key to `products`. `ON DELETE RESTRICT` prevents deleting a product while a referencing inventory record exists.

In this simplified model, `available_qty` is the sellable quantity. If you need to distinguish physical on-hand stock, reserved stock, in-transit stock, and damaged stock, extend this into dedicated columns or an inventory ledger, and define invariants across those states.

## 4. Creating the `orders` and `order_items` Tables

### The `orders` Table

    CREATE TABLE shop.orders (
        order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        order_number text NOT NULL UNIQUE,
        customer_id bigint NOT NULL
            REFERENCES shop.customers(customer_id)
            ON DELETE RESTRICT,
        status text NOT NULL DEFAULT 'pending',
        currency char(3) NOT NULL,
        shipping_address jsonb NOT NULL,
        idempotency_key uuid NOT NULL UNIQUE,
        request_hash bytea NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT orders_number_not_blank
            CHECK (btrim(order_number) <> ''),
        CONSTRAINT orders_status_valid
            CHECK (status IN (
                'pending',
                'paid',
                'processing',
                'shipped',
                'completed',
                'cancelled'
            )),
        CONSTRAINT orders_currency_format
            CHECK (btrim(currency) ~ '^[A-Z]{3}$'),
        CONSTRAINT orders_shipping_address_object
            CHECK (jsonb_typeof(shipping_address) = 'object'),
        CONSTRAINT orders_request_hash_sha256
            CHECK (octet_length(request_hash) = 32)
    );

An order must preserve the shipping address at placement time. If you only store `customer_id` and join to the customer's current address, a customer address update could cause old orders to display the wrong destination. `shipping_address` is a structured JSONB column storing an address snapshot; fixed-structure fields that require frequent querying can be extracted into dedicated columns or a snapshot table.

`idempotency_key` identifies an order-creation request. `request_hash` stores the SHA-256 digest of the canonicalized business payload. When a client retries with the same key, the application compares hashes to confirm it is the same request. The same key with a different payload must be rejected.

The `CHECK` constraint on `status` only restricts the set of valid values. It does not enforce valid state transitions. For example, `CHECK` allows both `pending` and `completed`, but does not prevent the application from jumping straight from `pending` to `completed`. State-transition rules should be enforced via conditional `UPDATE` statements, transactional services, or triggers if centralized enforcement in the database is required.

### The `order_items` Table

    CREATE TABLE shop.order_items (
        order_item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        order_id bigint NOT NULL
            REFERENCES shop.orders(order_id)
            ON DELETE CASCADE,
        product_id bigint NOT NULL
            REFERENCES shop.products(product_id)
            ON DELETE RESTRICT,
        sku_snapshot text NOT NULL,
        product_name_snapshot text NOT NULL,
        quantity integer NOT NULL,
        unit_price numeric(12, 2) NOT NULL,
        line_total numeric(22, 2)
            GENERATED ALWAYS AS (
                quantity::numeric * unit_price
            ) STORED,
        CONSTRAINT order_items_quantity_positive
            CHECK (quantity > 0),
        CONSTRAINT order_items_price_nonnegative
            CHECK (unit_price >= 0),
        CONSTRAINT order_items_unique_product
            UNIQUE (order_id, product_id)
    );

The snapshot columns preserve product details at the time of purchase. `unit_price` in `products` is the current price; `unit_price` in `order_items` is the locked-in price for that specific order. Never join back to current prices to recalculate totals for historical orders.

`line_total` is a `STORED` generated column. PostgreSQL computes its value automatically from `quantity` and `unit_price` on insert or update. Applications cannot write directly to a generated column. This prevents bugs where a client supplies `quantity` and `unit_price` alongside an inconsistent `line_total`.

The `UNIQUE (order_id, product_id)` constraint specifies that a product can appear at most once per order. If the interface allows multiple lines of the same product with different attributes, such as size or customization, extend the unique key with the distinguishing attributes or use a line number.

`ON DELETE CASCADE` on `order_items` means deleting an order deletes its child rows. In e-commerce systems, orders should generally be cancelled or archived rather than deleted to preserve history. Cascade here illustrates dependent ownership; application permissions can prohibit `DELETE` on `orders`. Payment history tables can also block deletion.

## 5. Creating the `payments` Table

A single order may have multiple payment attempts. Do not overwrite an older attempt's status with a new attempt because reconciliation and callback history must be preserved.

    CREATE TABLE shop.payments (
        payment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        order_id bigint NOT NULL
            REFERENCES shop.orders(order_id)
            ON DELETE RESTRICT,
        provider text NOT NULL,
        provider_reference text,
        amount numeric(14, 2) NOT NULL,
        currency char(3) NOT NULL,
        status text NOT NULL DEFAULT 'pending',
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT payments_provider_not_blank
            CHECK (btrim(provider) <> ''),
        CONSTRAINT payments_amount_nonnegative
            CHECK (amount >= 0),
        CONSTRAINT payments_currency_format
            CHECK (btrim(currency) ~ '^[A-Z]{3}$'),
        CONSTRAINT payments_status_valid
            CHECK (status IN (
                'pending',
                'authorized',
                'captured',
                'failed',
                'refunded'
            )),
        CONSTRAINT payments_provider_reference_unique
            UNIQUE (provider, provider_reference)
    );

The unique constraint on `(provider, provider_reference)` prevents the same provider-issued transaction from being recorded twice. PostgreSQL allows multiple `NULL` values in a standard unique constraint, so multiple payments without a `provider_reference` can still exist. If business rules require every payment sent to a provider to have a reference, validate that condition in the update flow or add an appropriate constraint.

A payment gateway callback may be delivered multiple times. The application must use the provider reference as a deduplication key, inspect the current state, and perform updates inside a transaction. Never credit funds or mark an order paid multiple times simply because a webhook arrived more than once.

## 6. Creating Indexes for Common Queries

Primary keys and unique constraints create corresponding indexes. PostgreSQL does not automatically create indexes on referencing foreign-key columns. Therefore, review query patterns and parent-key delete/update operations to decide which indexes to add.

    CREATE INDEX orders_customer_created_idx
        ON shop.orders (customer_id, created_at DESC);

    CREATE INDEX orders_status_created_idx
        ON shop.orders (status, created_at DESC);

    CREATE INDEX order_items_product_idx
        ON shop.order_items (product_id);

    CREATE INDEX payments_order_idx
        ON shop.payments (order_id);

`orders_customer_created_idx` supports fetching a customer's most recent orders. The status index supports admin dashboards filtering orders by status and timestamp. The `product_id` index speeds up finding orders containing a product or checking referencing rows during product maintenance. `payments_order` supports retrieving an order's payment history.

The unique index `(order_id, product_id)` on `order_items` already has `order_id` as its leading column, so it can serve queries filtering by `order_id`. There is no need to add a separate single-column index on `order_id` unless the workload demonstrates a distinct benefit.

Indexes speed up reads but increase the cost of `INSERT`, `UPDATE`, `DELETE`, and storage footprint. Do not index every column. Base indexing decisions on actual queries, cardinality, selectivity, write frequency, and execution plans.

View existing indexes:

    SELECT
        schemaname,
        tablename,
        indexname,
        indexdef
    FROM pg_indexes
    WHERE schemaname = 'shop'
    ORDER BY tablename, indexname;

Use `EXPLAIN` to inspect how PostgreSQL plans to execute a query:

    EXPLAIN
    SELECT order_id, order_number, status, created_at
    FROM shop.orders
    WHERE customer_id = 42
    ORDER BY created_at DESC
    LIMIT 20;

`EXPLAIN ANALYZE` executes the statement to measure actual timings and row counts. Only run it on safe queries in an appropriate environment; for `UPDATE`/`DELETE` statements, it actually applies the changes unless wrapped in a transaction followed by `ROLLBACK`.

## 7. Inspecting the Schema and Constraints After Creation

You can use `psql` to inspect table structures:

    \dn
    \dt shop.*
    \d shop.orders
    \d shop.order_items

Commands starting with a backslash are `psql` meta-commands, not SQL sent directly to the PostgreSQL server.

To query constraints via the system catalog:

    SELECT
        conrelid::regclass AS table_name,
        conname,
        contype,
        pg_get_constraintdef(oid) AS definition,
        convalidated
    FROM pg_constraint
    WHERE connamespace = 'shop'::regnamespace
    ORDER BY conrelid::regclass::text, conname;

`contype` typically takes values `p` (primary key), `f` (foreign key), `u` (unique), `c` (check), and `x` (exclusion). `convalidated` indicates whether the constraint has been verified against all existing data. This is useful when deploying migrations using `NOT VALID`.

Inspect columns, data types, and nullability:

    SELECT
        table_name,
        column_name,
        data_type,
        is_nullable,
        column_default
    FROM information_schema.columns
    WHERE table_schema = 'shop'
    ORDER BY table_name, ordinal_position;

Catalog verification should be part of migration tests or deployment verification. Do not rely solely on a migration tool reporting success.

## 8. Inserting Sample Data and Testing Constraints

Create a customer:

    INSERT INTO shop.customers (email, full_name)
    VALUES ('lan@example.com', 'Nguyen Thi Lan')
    RETURNING customer_id;

Create products:

    INSERT INTO shop.products (
        sku, product_name, unit_price, currency
    )
    VALUES
        ('KB-001', 'Mechanical keyboard', 850000.00, 'VND'),
        ('MS-002', 'Wireless mouse', 420000.00, 'VND')
    RETURNING product_id, sku;

Assuming the two products return IDs 1 and 2 in the test database, create inventory records:

    INSERT INTO shop.inventory (product_id, available_qty)
    VALUES
        (1, 50),
        (2, 80);

In shared environments, never assume identity values always start at 1. Capture actual IDs via `RETURNING` or look them up by SKU. The ID values in examples are illustrative only.

Attempt to violate the rules:

    -- quantity must be greater than 0
    INSERT INTO shop.order_items (
        order_id, product_id, sku_snapshot,
        product_name_snapshot, quantity, unit_price
    )
    VALUES (1, 1, 'KB-001', 'Mechanical keyboard', 0, 850000.00);

The statement above must fail with the check constraint `order_items_quantity_positive`.

    -- product_id must reference an existing product
    INSERT INTO shop.inventory (product_id, available_qty)
    VALUES (999999, 10);

This statement must fail due to the foreign key constraint.

    -- Case-insensitive email uniqueness
    INSERT INTO shop.customers (email, full_name)
    VALUES ('LAN@EXAMPLE.COM', 'Lan Duplicate');

If `lan@example.com` already exists, the expression-based unique index rejects the duplicate record. The SQLSTATE is typically `23505` (`unique_violation`).

Testing both valid and invalid cases verifies that constraints are genuinely enforced in the database. Do not test validation only in UI forms, because import pipelines, batch jobs, and administrative scripts can bypass UI forms.

## 9. Creating an Order Inside a Transaction

Order creation is a multi-step workflow: identifying the request, creating the header, checking products, reserving inventory, and writing line items. If any step fails, all preceding steps must be rolled back.

### Why Is a Transaction Required?

Suppose the application decrements inventory first, then inserts `order_items`, and the insert fails. If these two operations are not in the same transaction, inventory could be reduced even though no order was created. Similarly, an order could exist with incomplete line items if the process crashes mid-flight.

A transaction ensures that all changes belonging to an order commit together or roll back together:

    BEGIN;

    -- Create order header.
    -- Reserve inventory.
    -- Insert order_items.
    -- Verify results.

    COMMIT;

If any step fails, the application executes `ROLLBACK`. In application code, use the driver or framework transaction API to guarantee rollback on exceptions.

### Idempotency During Order Creation

The client generates an idempotency key once when initiating a request and resends the exact same key on retries. The request hash is computed from the canonicalized business payload, including customer, currency, address, and line items. Exclude request timestamps or tracing metadata that vary across retries from the hash.

Create the order header:

    INSERT INTO shop.orders (
        order_number,
        customer_id,
        status,
        currency,
        shipping_address,
        idempotency_key,
        request_hash
    )
    VALUES (
        $1, $2, 'pending', $3, $4::jsonb, $5, $6
    )
    ON CONFLICT (idempotency_key) DO NOTHING
    RETURNING order_id;

If the statement returns an `order_id`, the current transaction created a new request and can proceed. If no row is returned, the application reads the existing order by key:

    SELECT order_id, request_hash, status
    FROM shop.orders
    WHERE idempotency_key = $1;

If the hashes match, this is a retry of the same request; return the existing result according to API policy. If the hashes differ, reject the request because the same key was reused for a different payload. Under `READ COMMITTED` isolation, the subsequent `SELECT` receives a fresh snapshot and can see the committed transaction holding the key. Under `REPEATABLE READ` or `SERIALIZABLE` isolation, concurrent conflicts may trigger a serialization failure; in that case, retry the entire transaction per policy.

Do not proceed to reserve inventory or write `order_items` if inserting the header did not create a new row. Otherwise, a duplicate request could still deduct stock a second time.

### Safely Reserving Inventory Under Concurrency

Do not use a two-step pattern like:

1. `SELECT available_qty`.
2. If sufficient, `UPDATE available_qty = available_qty - quantity`.

Two concurrent requests can read the same stale quantity before either updates it. Both assume stock is available and oversell inventory.

Use an atomic conditional `UPDATE`:

    UPDATE shop.inventory
    SET available_qty = available_qty - $1,
        updated_at = now()
    WHERE product_id = $2
      AND $1 > 0
      AND available_qty >= $1
    RETURNING product_id, available_qty;

If one row is returned, the quantity was reserved successfully. If no row is returned, either the product does not exist in `inventory`, stock is insufficient, or the quantity is invalid. The application should distinguish these cases if user-facing messaging requires it, but in all three cases it must roll back the order-creation transaction.

PostgreSQL locks the updated row and re-evaluates the condition appropriately when handling concurrent updates. `CHECK (available_qty >= 0)` acts as an additional safety net if another write path attempts to drive stock negative.

### Capturing Product Price and Name Snapshots

Inside the order-creation transaction, read product details from the database rather than trusting client-supplied prices. You can read and lock the product row before creating the line item:

    SELECT product_id, sku, product_name, unit_price, currency
    FROM shop.products
    WHERE product_id = $1
      AND is_active
    FOR SHARE;

After confirming the product exists, is active, and matches the order's currency, the application reserves inventory and inserts `order_items` using the values just read:

    INSERT INTO shop.order_items (
        order_id,
        product_id,
        sku_snapshot,
        product_name_snapshot,
        quantity,
        unit_price
    )
    VALUES ($1, $2, $3, $4, $5, $6);

`FOR SHARE` holds a shared lock on the product row until the transaction ends, preventing another transaction from updating or deleting that row while prices are being captured. When processing multiple products, acquire locks in ascending `product_id` order to reduce the likelihood of deadlocks.

Every product must be validated and have its inventory reserved. If any line item lacks sufficient stock or is inactive, roll back the entire order. Never commit a partial order if business rules require atomic ordering.

### Overall Application-Layer Workflow

Pseudocode:

    BEGIN;

    1. Compute request_hash from canonicalized payload.
    2. INSERT into orders with idempotency_key.
    3. If key already exists:
         read existing order;
         compare request_hash;
         if matching, return previous result;
         if different, return key conflict error;
         do not modify inventory.
    4. Normalize line items, merging duplicate products if required by the model.
    5. Process products in ascending product_id order:
         read product FOR SHARE;
         verify is_active and currency;
         run conditional UPDATE on inventory;
         if insufficient stock, ROLLBACK;
         INSERT into order_items with snapshot price and name.
    6. COMMIT;

    On error:
         ROLLBACK;
         classify error;
         retry only according to policy and reuse the same idempotency_key.

The pseudocode illustrates the business sequence. In a real application, clearly define how results are returned when the key already exists, how `order_number` collisions are handled, deadlines, and full-transaction retries. Never retry with a new idempotency key.

## 10. Calculating Order Totals and Querying History

An order total can be calculated from its line items:

    SELECT
        o.order_id,
        o.order_number,
        o.status,
        o.currency,
        o.created_at,
        COALESCE(sum(oi.line_total), 0) AS order_total
    FROM shop.orders AS o
    LEFT JOIN shop.order_items AS oi
        ON oi.order_id = o.order_id
    WHERE o.order_id = $1
    GROUP BY
        o.order_id,
        o.order_number,
        o.status,
        o.currency,
        o.created_at;

Do not use a `CHECK` constraint on `orders` to validate the sum of `order_items`, because `CHECK` constraints are not designed to query other rows or tables. If you need to store a finalized total amount, compute and write it inside the same order-creation transaction, along with reconciliation against line-item sums. If the total is purely derived data, compute it at query time or expose it via a view to avoid redundant storage.

### Listing Orders for a Customer

    SELECT
        order_id,
        order_number,
        status,
        currency,
        created_at
    FROM shop.orders
    WHERE customer_id = $1
    ORDER BY created_at DESC
    LIMIT 50;

The index `(customer_id, created_at DESC)` supports this query pattern.

### Details of an Order

    SELECT
        oi.order_item_id,
        oi.sku_snapshot,
        oi.product_name_snapshot,
        oi.quantity,
        oi.unit_price,
        oi.line_total
    FROM shop.order_items AS oi
    WHERE oi.order_id = $1
    ORDER BY oi.order_item_id;

Use snapshots to display order history. If you need additional current product details such as images or active status, you can join to `products`, but never overwrite historical values.

### Payment History

    SELECT
        payment_id,
        provider,
        provider_reference,
        amount,
        currency,
        status,
        created_at
    FROM shop.payments
    WHERE order_id = $1
    ORDER BY created_at, payment_id;

Each payment row represents an attempt or payment event. Aggregating captured amounts must account for statuses and explicit refund rules; never blindly sum all payment rows.

## 11. Updating Order Status and Recording Payments

A `CHECK` constraint ensures `status` belongs to the allowed list, but state transitions must be conditional. For instance, transition from `pending` to `paid` only if the current status is still `pending`:

    UPDATE shop.orders
    SET status = 'paid'
    WHERE order_id = $1
      AND status = 'pending'
    RETURNING order_id, status;

If no row is returned, the order may already be paid, cancelled, or in an incompatible state. The application must read the current status and handle the operation idempotently.

When receiving a webhook from a provider:

1. Verify the signature and sender origin.
2. Identify the `provider_reference` and corresponding order.
3. Begin a transaction.
4. Record or look up the payment by provider and reference.
5. If the event has already been processed, do not repeat its effects.
6. Verify `amount`, `currency`, and order status.
7. Conditionally update the payment and order.
8. Commit; if downstream systems must be notified, write an outbox record in the same transaction.

The unique constraint `(provider, provider_reference)` helps prevent a single callback from creating two payment records. However, it does not automatically enforce all business state-transition rules. Validate `amount`/`currency` and state rules inside the transaction.

When calling an external payment API, do not hold a PostgreSQL transaction open while waiting for the HTTP response. You can create a payment intent and outbox event in a transaction, after which a worker calls the provider using a stable idempotency key. Once the provider responds, the worker updates the database in a separate transaction. This pattern avoids holding connections and locks for long periods while supporting safe retries.

## 12. Data Constraints: Choosing the Right Mechanism

PostgreSQL provides multiple mechanisms to protect data integrity. Choosing the right one keeps rules readable, testable, and hard to bypass.

| Mechanism | When to Use | Examples in Schema |
|---|---|---|
| PRIMARY KEY | Every row needs a unique, non-NULL identifier | `customer_id`, `order_id` |
| FOREIGN KEY | Value must reference an existing row | `orders.customer_id`, `order_items.product_id` |
| UNIQUE | Duplicate values or combinations are disallowed | `order_number`, `idempotency_key` |
| CHECK | Condition on the individual row being written | `quantity > 0`, `unit_price >= 0` |
| NOT NULL | Value is mandatory | `email`, `status` |
| DEFAULT | Default value when caller omits the column | `created_at`, `status` |
| GENERATED | Value computed from other columns in the same row | `line_total` |
| EXCLUDE | Prevent conflicting values or ranges by operator | Useful for booking schedules or validity intervals |

### `CHECK` Does Not Replace Foreign Keys

Do not write complex triggers or `CHECK` constraints to manually verify customer existence when a foreign key accurately represents the relationship. PostgreSQL checks foreign keys consistently on insert/update and handles delete/update actions declaratively.

### `CHECK` Does Not Validate Multi-Row Aggregates

Conditions such as "the sum of `line_total` across `order_items` must not exceed the customer's credit limit" span multiple rows. `CHECK` does not safely support querying other tables. Use transactions, appropriate locking, concurrency-safe triggers, or an alternative data model to enforce that invariant.

### `DEFERRABLE` for End-of-Transaction Validation

Certain `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY`, or `EXCLUDE` constraints can be declared `DEFERRABLE` to postpone checking until the end of the transaction. This is useful for key-swapping operations or multi-step relationship updates. `CHECK` and `NOT NULL` do not have an equivalent `DEFERRABLE` mechanism.

Do not defer constraints without a clear need. Immediate checking generally catches errors earlier.

### `ON DELETE` and `ON UPDATE`

- `RESTRICT`/`NO ACTION`: prevents deleting or updating a parent row while referencing child rows exist, differing in constraint-check timing.
- `CASCADE`: automatically deletes or updates child rows along with the parent row.
- `SET NULL`: sets the child foreign key to `NULL`; appropriate only if the column is nullable and business logic permits it.
- `SET DEFAULT`: sets the default value; that value must still satisfy the foreign key if the constraint remains in effect.

Choose behavior according to the data lifecycle. For order history, keep referenced customers and products protected via `RESTRICT`, using inactive flags or soft deletes. `CASCADE` is better suited for child data that has no independent meaning once the parent row is deleted.

## 13. Testing Constraints and Edge Cases

A schema test suite should cover valid cases, constraint violations, and concurrent contention.

### Testing `NOT NULL` and `CHECK`

- Insert a customer without an email: must fail.
- Insert an email containing only whitespace: must fail.
- Insert a product with a negative price: must fail.
- Insert negative inventory: must fail.
- Insert an order item with `quantity` equal to 0 or negative: must fail.
- Insert a payment with a negative amount: must fail.

### Testing `UNIQUE`

- Create two customers with emails differing only by case but sharing the same normalized address: the second must fail.
- Create two products with the same SKU case-insensitively: the second must fail.
- Create two orders with the same `order_number`: the second must fail.
- Create two orders with the same idempotency key: only one order is created; the duplicate request must return the existing order.
- Create two payments with the same `provider` and `provider_reference`: the second record must be rejected.

### Testing `FOREIGN KEY`

- Create an order with a non-existent `customer_id`: fails.
- Create an `order_item` with a non-existent `order_id` or `product_id`: fails.
- Delete a product that already has an `order_item`: blocked by `RESTRICT`.
- Delete a customer who already has orders: blocked by `RESTRICT`.
- Delete an order that has `order_items`: child rows are `CASCADE`-deleted per the illustrative design; verify whether application policy permits this operation.

### Testing Transaction Rollback

Start a transaction, decrement inventory, and then attempt to insert an invalid order item. Roll back and verify that inventory returns to its original value. Also verify that the order header no longer exists. This confirms the steps execute within the same transaction.

### Testing Inventory Contention

Suppose `inventory.available_qty = 5`. Open two sessions and concurrently attempt to order `quantity = 4` of the same product. Use the conditional `UPDATE`:

    UPDATE shop.inventory
    SET available_qty = available_qty - 4
    WHERE product_id = 1
      AND available_qty >= 4
    RETURNING available_qty;

Only one session can reserve 4 units. The other session waits for the lock, then evaluates the condition against the updated value and returns no rows because only 1 unit remains. As a result, inventory stays non-negative and 8 total units cannot be sold from an initial stock of 5.

### Testing Duplicate Requests

Send the same idempotency key and payload concurrently from multiple clients. Verify that only one order header is created and inventory is reserved only once. Resend the same key with a different payload and verify that the API rejects it. Do not inspect only the HTTP response; query `orders`, `order_items`, and `inventory` to confirm the final state.

### Testing Duplicate Payment Callbacks

Resend the same webhook multiple times. Verify that only one payment exists per provider/reference and that the order is not updated or events emitted multiple times. If using an outbox, verify events are deduplicated at the consumer.

## 14. Organizing Safe Schema Migrations

Schemas evolve as the product grows. Migrations must be versioned, ordered, idempotently tracked by the deployment tool, and compatible with running application versions.

### Adding a New Column

If you need to add an initially nullable `phone_number`:

    ALTER TABLE shop.customers
    ADD COLUMN phone_number text;

Older application versions continue working because the new column is optional. Once new code writes data, you can backfill and add constraints incrementally.

### Adding a `CHECK` Constraint to a Populated Table

You can add a `NOT VALID` constraint to avoid scanning and validating all existing rows at `ADD` time:

    ALTER TABLE shop.products
    ADD CONSTRAINT products_price_nonnegative_v2
    CHECK (unit_price >= 0) NOT VALID;

A `NOT VALID` constraint is still enforced for subsequent inserts or updates, while skipping verification of pre-existing rows. After fixing any violating rows, run:

    ALTER TABLE shop.products
    VALIDATE CONSTRAINT products_price_nonnegative_v2;

`VALIDATE` checks existing data without holding a heavy lock like some other `ALTER TABLE` operations. You must still evaluate lock impact, load, and execution duration based on table size.

### Adding a Foreign Key to a Large Table

Similarly, you can add a foreign key `NOT VALID` and run `VALIDATE` after cleaning up orphaned rows:

    ALTER TABLE shop.order_items
    ADD CONSTRAINT order_items_product_fk_v2
    FOREIGN KEY (product_id)
    REFERENCES shop.products(product_id)
    NOT VALID;

    ALTER TABLE shop.order_items
    VALIDATE CONSTRAINT order_items_product_fk_v2;

### Creating an Index on a Table Serving Live Traffic

`CREATE INDEX CONCURRENTLY` reduces write-blocking duration compared to standard index creation on large tables, though it incurs I/O overhead and can take longer. This command cannot run inside a transaction block:

    CREATE INDEX CONCURRENTLY orders_created_idx
        ON shop.orders (created_at DESC);

If concurrent index creation fails, an invalid index may be left behind. Check the system catalog and clean up that index before retrying. Your migration tool must support marking this migration as non-transactional.

### Expand-Contract

When renaming or changing the type of a column in active use, roll out in multiple phases:

1. Expand: add the new column or structure while keeping the old column.
2. Deploy code compatible with both formats or perform controlled dual-writes.
3. Backfill historical data into the new structure in batches.
4. Verify parity and switch reads to the new column.
5. Stop writing to the old column once all application instances are upgraded.
6. Contract: drop the old column in a separate migration after confirming no dependencies remain.

Do not bundle adding a column, backfilling, switching application code, and dropping the old column into one large change that makes rollback difficult.

## 15. Schema-Based Access Control

Applications should not connect as a superuser or the schema owner role. Separate the object-owning role from runtime roles:

    CREATE ROLE shop_owner NOLOGIN;
    CREATE ROLE shop_app LOGIN;

    ALTER SCHEMA shop OWNER TO shop_owner;

    GRANT USAGE ON SCHEMA shop TO shop_app;

    GRANT SELECT, INSERT, UPDATE
    ON shop.customers, shop.products, shop.inventory,
       shop.orders, shop.order_items, shop.payments
    TO shop_app;

    GRANT USAGE, SELECT
    ON ALL SEQUENCES IN SCHEMA shop
    TO shop_app;

This is an initialization example for a fresh environment. If the role or schema already exists, inspect current state before running; do not blindly re-run `CREATE ROLE`. Grant granular privileges per use case: a payment worker might only need to read orders and update `payments`/`orders`; a catalog service might update `products` without needing privileges on `payments`.

To apply sequence and table privileges to objects created in the future, the owner can configure default privileges:

    ALTER DEFAULT PRIVILEGES
    FOR ROLE shop_owner
    IN SCHEMA shop
    GRANT SELECT, INSERT, UPDATE ON TABLES TO shop_app;

    ALTER DEFAULT PRIVILEGES
    FOR ROLE shop_owner
    IN SCHEMA shop
    GRANT USAGE, SELECT ON SEQUENCES TO shop_app;

Default privileges apply only to objects created by the specified role after the command is executed. If migrations run under a different role, configure defaults accordingly.

Do not grant `DELETE` if a service does not need to delete historical records. Nor should runtime roles be granted `CREATE` on the schema. Ensure the application's `search_path` is intentionally configured; avoid placing schemas controlled by untrusted users ahead of schemas containing sensitive functions or objects.

## 16. Common Design Mistakes

**Putting all data into a single `orders` table.** Repeating emails, product names, and addresses across multiple rows causes update anomalies. Normalize entities across relationships and store snapshots where history must be preserved.

**Using current prices to display old orders.** Product prices can change. `order_items` must store the price locked in at order placement time.

**Using floating-point types for money.** Representation errors can cause inaccurate totals and reconciliation mismatches. Use `numeric` with appropriate precision/scale and define explicit rounding rules.

**Checking inventory only with `SELECT` followed by `UPDATE`.** Two concurrent requests can sell the same stock. Use a conditional `UPDATE` or lock rows inside a transaction.

**Relying solely on application-layer validation.** Batch jobs, scripts, and other APIs can write directly. Enforce core invariants via database constraints.

**Using `CHECK` to validate other tables.** `CHECK` is not the right tool for multi-row totals or cross-table relationships. Use foreign keys, transactions, properly designed triggers, or a different data model.

**Deleting products that already appear in orders.** This can break historical lookups. Set `is_active` to `false` and retain the foreign key.

**Indexing every column.** Indexes increase storage usage and write overhead. Base decisions on query plans and workloads.

**Using a new idempotency key on retries.** Each retry becomes a new order. The key must remain stable for a given request intent.

**Failing to test concurrency.** A sequential test suite will not catch overselling, deadlocks, or duplicate requests. Test with multiple concurrent sessions.

**Adding constraints to large tables without a locking plan.** Migrations can block traffic or scan tables for a long time. Use `NOT VALID`/`VALIDATE` and `CREATE INDEX CONCURRENTLY` strategies where appropriate.

## 17. End-to-End Practice Exercise

Implement this model in a test PostgreSQL database. Use the `shop` schema and tables defined in this lesson.

### Part A: Build the Structure

1. Create the schema and six tables in the proper dependency order.
2. Create the primary keys, foreign keys, unique indexes, `CHECK` constraints, and query indexes.
3. Query the system catalog to confirm every constraint exists and is validated.
4. Create an owner role and an application role with least-privilege permissions.

### Part B: Load Data

1. Insert at least three customers and five products.
2. Create inventory records for each product.
3. Test case-insensitive duplicate emails and SKUs.
4. Test negative prices, `quantity` equal to 0, invalid currency formats, and non-existent foreign keys.
5. Record the SQLSTATE and constraint name for each error.

### Part C: Create an Order

1. Create an order containing two products.
2. Reserve inventory using a conditional `UPDATE`.
3. Store SKU, name, and price snapshots in `order_items`.
4. Calculate the order total using `SUM(line_total)`.
5. Resend the same idempotency key and confirm inventory is not reserved a second time.
6. Resend the same key with a different payload and confirm it is rejected.

### Part D: Concurrency Testing

1. Set a product's inventory to 5.
2. Open two sessions and concurrently attempt to order 4 units in each session.
3. Confirm that only one transaction succeeds.
4. Verify inventory is non-negative and only the valid order committed.
5. Create a scenario where two transactions lock multiple products in opposite orders, observe the deadlock, and fix the locking order.

### Part E: Payments

1. Create a `pending` payment for an order.
2. Simulate a successful provider callback.
3. Send the callback with the same `provider_reference` multiple times.
4. Confirm only one payment record exists and the order status updates exactly once.
5. Test a callback with a mismatched `amount` or `currency` and confirm the order is not marked paid.

### Part F: Migrations

1. Add an optional column to `customers`.
2. Backfill in batches.
3. Add a `CHECK` constraint with `NOT VALID`, clean up legacy data, and run `VALIDATE`.
4. Create an index `CONCURRENTLY` on a large test table.
5. Write an expand-contract plan for renaming a column.
6. Verify both old and new application versions during the migration window.

## 18. Practice Completion Criteria

An order management model meets the requirements when you can demonstrate the following:

- Tables have clear primary keys and relationships are enforced by foreign keys.
- Email, SKU, order number, idempotency key, and provider reference are protected by uniqueness rules.
- `quantity`, `price`, `amount`, and `available stock` cannot violate rules by becoming negative or zero.
- Orders store product and address snapshots at creation time.
- Order creation and inventory reservation occur in the same transaction.
- Two concurrent requests cannot oversell inventory.
- Retries with the same idempotency key do not create duplicate orders or double-deduct inventory.
- Duplicate payment callbacks do not record duplicate payments.
- Key queries have appropriate indexes verified with `EXPLAIN`.
- Migrations include strategies for existing data and live traffic.
- The application role only has necessary privileges.
- Valid cases, constraint violations, rollbacks, and concurrency are all tested.

## 19. PostgreSQL Reference Documentation

Consult the documentation for your deployed major version to verify exact syntax and behavior:

- PostgreSQL Documentation — Schemas: https://www.postgresql.org/docs/current/ddl-schemas.html
- PostgreSQL Documentation — Data Definition: https://www.postgresql.org/docs/current/ddl.html
- PostgreSQL Documentation — Constraints: https://www.postgresql.org/docs/current/ddl-constraints.html
- PostgreSQL Documentation — Generated Columns: https://www.postgresql.org/docs/current/ddl-generated-columns.html
- PostgreSQL Documentation — Transactions: https://www.postgresql.org/docs/current/tutorial-transactions.html
- PostgreSQL Documentation — Explicit Locking: https://www.postgresql.org/docs/current/explicit-locking.html
- PostgreSQL Documentation — Indexes: https://www.postgresql.org/docs/current/indexes.html
- PostgreSQL Documentation — CREATE INDEX: https://www.postgresql.org/docs/current/sql-createindex.html
- PostgreSQL Documentation — ALTER TABLE: https://www.postgresql.org/docs/current/sql-altertable.html
- PostgreSQL Documentation — Privileges: https://www.postgresql.org/docs/current/ddl-priv.html
