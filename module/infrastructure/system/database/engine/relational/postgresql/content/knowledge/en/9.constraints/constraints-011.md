# Dividing Data Validation Between the Database and the Application

An order form can reject negative quantities, warn about malformed email addresses, or notify the user that a discount code has expired. However, data is also written from APIs, mobile apps, background workers, import scripts, and admin tools. If validation only happens in the UI, those other write paths can create invalid records. Conversely, if all validation only occurs when PostgreSQL rejects an `INSERT`, users receive cryptic technical errors, while rules depending on payments, access permissions, and business workflows remain incompletely handled.

This lesson belongs to the **Constraints** chapter of PostgreSQL and focuses on how to **divide data validation responsibilities between the database and the application**. The goal is to keep data accurate across every write path, avoid missing concurrency bugs, and provide a manageable user experience and business workflow.

Core principle:

> **The application validates early to explain and orchestrate; PostgreSQL enforces the data invariants that every write operation must obey.** A rule can be checked intentionally across multiple layers, but that does not mean both layers share the same responsibility.

## 1. Concepts to Distinguish

**Input validation**: determines whether a request has the right structure and format. For example, `quantity` must be an integer, the order date must be parseable, and a string must not consist solely of whitespace.

**Business validation**: decides whether an operation is allowed under business rules. For example, a shipped order cannot revert to draft, and a voucher does not apply to excluded products.

**Data integrity**: maintains conditions that must hold true for accepted data. For example, unique primary keys, no order lines missing a parent order, and non-negative prices.

**Authorization**: whether the caller has permission to operate on an object. An existing order ID does not mean every user is allowed to cancel that order.

**External verification**: confirms facts outside the database, such as payment receipt from a provider or OTP completion for a phone number.

Illustrative table:

| Requirement | PostgreSQL | Application |
|---|---|---|
| Required column has a value | `NOT NULL` | Check required, fail fast |
| Non-negative price | `CHECK` | Validate before sending |
| Unique customer code | `UNIQUE` | Optional UX pre-check, catch write error |
| Order must reference existing customer | `FOREIGN KEY` | Valid lookup/selection |
| Two room bookings do not overlap | `EXCLUDE` when appropriate | Display available time slots |
| Status transitions follow workflow | Partial constraint, may need transaction/trigger | Domain service decides |
| Do not oversell inventory | CHECK + atomic update/locking | Orchestrate ordering |
| Users only edit their own orders | DB permissions/RLS if applicable | Identity-based authorization |
| Email can receive mail | Cannot infer from regex alone | Email verification |
| PSP confirmed payment | Store result and protect relationships | Verify callback/provider |

A rule must be clearly defined before choosing where to implement it.

## 2. Multi-Layer Validation Model

~~~text
                    User
                     |
                     v
              +----------------+
              | UI / Client    |
              | Format, hints  |
              +----------------+
                     |
                     v
              +----------------+
              | API boundary   |
              | Parse, authN   |
              | Request schema |
              +----------------+
                     |
                     v
              +----------------+
              | Domain service |
              | Workflow, authZ|
              | External rules |
              +----------------+
                     |
                     v
              +----------------+
              | SQL transaction|
              | Atomic writes  |
              | Concurrency    |
              +----------------+
                     |
                     v
              +----------------+
              | PostgreSQL     |
              | Constraints    |
              | Integrity      |
              +----------------+
                     |
                     v
                    Data
~~~

The UI is easily bypassed via direct HTTP requests, so client-side checks are **not a trust boundary**. The API must re-parse data and authenticate/authorize; the service applies business rules; the database protects invariants through constraints and transactions.

### 2.1. Intentional Validation Duplication

A required `quantity` field must be greater than 0:

- The UI displays: "Quantity must be 1 or more".
- The API rejects `quantity` as a string or decimal if the contract requires an integer.
- The service checks whether the product is eligible for purchase.
- PostgreSQL uses `quantity INTEGER NOT NULL CHECK (quantity > 0)`.

This is not wasteful duplication: the UI optimizes the user experience, while the database is responsible for ultimate correctness.

### 2.2. No Need to Copy Every Rule Everywhere

A rule that changes daily by campaign and may call external services should not be duplicated across JavaScript, Java, PL/pgSQL, and triggers without a synchronization mechanism. Place business rules where they belong; in the database, keep the minimal invariants that can be enforced stably.

## 3. Identify Invariants Before Writing SQL

An **invariant** is something that must never be false in committed data.

Examples:

~~~text
Every customer has a unique primary key.
Every order.customer_id references an existing customer.
Every order_item.quantity is greater than 0.
Every product.stock is non-negative.
Normalized emails are unique within a tenant.
A room does not have two overlapping confirmed bookings.
~~~

These statements are more specific than "data must be valid".

### 3.1. The Scope of an Invariant Matters

"Unique email" is not clear enough. You must ask:

- Unique system-wide or per tenant?
- Case-sensitive or case-insensitive?
- Can email be omitted?
- Does soft delete release the email for reuse?
- Must the email be verified before use?

If the scope is undefined, a `UNIQUE(email)` constraint might enforce **the wrong business rule**.

### 3.2. Not Every Rule Is a Permanent Invariant

"A customer must have a shipping address" might not apply to a newly registered customer profile. However, "an order in the submitted status must have a shipping address" can be a reasonable invariant.

Choose **when** a rule must hold: on input, on submit, on payment, on commit, or upon workflow completion.

## 4. NOT NULL: Required Columns

~~~sql
CREATE TABLE customers_simple (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

PostgreSQL does not allow storing SQL `NULL` in `full_name`. If a worker bypasses the form and sends `NULL`, the database still rejects it.

### 4.1. NOT NULL Does Not Prevent Empty Strings

`''` or `'   '` is not `NULL`.

~~~sql
CREATE TABLE contacts_simple (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name TEXT NOT NULL,
    CONSTRAINT chk_display_name_not_blank
        CHECK (btrim(display_name) <> '')
);
~~~

The application should trim input and explain the error; the database enforces the invariant.

### 4.2. NULL Can Be a Valid State

A `delivered_at TIMESTAMPTZ` column can be NULL when an order has not been delivered yet. Forcing every column to be `NOT NULL` does not improve the model when NULL has a legitimate business meaning.

## 5. CHECK: Deterministic Single-Row Conditions

~~~sql
CREATE TABLE product_prices (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    amount NUMERIC(12, 2) NOT NULL,
    currency_code TEXT NOT NULL,
    CONSTRAINT chk_amount_nonnegative
        CHECK (amount >= 0),
    CONSTRAINT chk_currency_format
        CHECK (currency_code ~ '^[A-Z]{3}$')
);
~~~

The constraints above protect non-negative amounts and three-letter currency codes. However, the regex **does not confirm that the currency is actually on the business's approved list**.

### 5.1. CHECK and Three-Valued Logic

In SQL, a comparison can evaluate to `TRUE`, `FALSE`, or `UNKNOWN`. CHECK rejects when the condition is **FALSE**; **UNKNOWN** values are generally accepted.

~~~sql
CREATE TABLE nullable_prices (
    amount NUMERIC CHECK (amount > 0)
);
~~~

`INSERT ... VALUES (NULL)` into this column is not rejected by CHECK because `NULL > 0` evaluates to UNKNOWN. If a positive price is required:

~~~sql
amount NUMERIC NOT NULL CHECK (amount > 0)
~~~

### 5.2. CHECK Across Multiple Columns in the Same Row

~~~sql
CREATE TABLE appointment_windows (
    appointment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT chk_appointment_interval
        CHECK (ends_at > starts_at)
);
~~~

This rule fits well in the DB because it is simple, stable, and depends only on values within the same row.

### 5.3. Conditional CHECK

~~~sql
CREATE TABLE order_headers (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'submitted', 'cancelled')),
    shipping_address TEXT,
    CONSTRAINT chk_submitted_has_address
        CHECK (
            status <> 'submitted'
            OR NULLIF(btrim(shipping_address), '') IS NOT NULL
        )
);
~~~

Draft orders can omit the address; submitted orders must have a non-blank address.

### 5.4. Do Not Use CHECK to Count Rows in Another Table

The rule "every submitted order must have at least one order line" involves data in another table. Do not write a custom CHECK function that runs `SELECT COUNT(*)` to simulate a multi-row constraint: data can change concurrently, the check can become invalid after other changes, and it is difficult to guarantee during restore.

Use transactions, write-path design, locks, or an appropriate DB mechanism for multi-row rules.

### 5.5. CHECK Is Unsuitable for Clock-Dependent Conditions

A rule like "the order date must be greater than or equal to today" depends on the current time. If placed in a CHECK using a time-dependent function, data valid today may become invalid tomorrow without PostgreSQL automatically re-checking every row.

Determine whether the check should happen **when the user places the order** or hold permanently, then place the logic in the service or an appropriate data model.

## 6. UNIQUE: Protecting Uniqueness Under Concurrency

~~~sql
CREATE TABLE customer_emails (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL
);

CREATE UNIQUE INDEX uq_customer_email_normalized
ON customer_emails (lower(btrim(email)));
~~~

An application might pre-check:

~~~sql
SELECT EXISTS (
    SELECT 1 FROM customer_emails
    WHERE lower(btrim(email)) = lower(btrim('Alice@example.com'))
);
~~~

However, pre-checking **is not enough to prevent duplicates**.

### 6.1. Classic Race Condition

~~~text
Request A                     Request B
    |                             |
SELECT does email exist?     SELECT does email exist?
    |                             |
    No                            No
    |                             |
INSERT email                 INSERT same email
    |                             |
  Succeeded                  UNIQUE rejected
~~~

Without a unique constraint/index, two requests can both commit duplicate data. Therefore, the database must be the final arbiter; the application catches `unique_violation` and returns a clear error.

### 6.2. Tenant-Scoped UNIQUE

~~~sql
CREATE TABLE tenant_customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_code TEXT NOT NULL,
    CONSTRAINT uq_tenant_customer_code
        UNIQUE (tenant_id, customer_code)
);
~~~

If two tenants are allowed to use the same customer code, table-wide uniqueness on `customer_code` alone would be too strict.

### 6.3. NULL and UNIQUE

By default, UNIQUE in PostgreSQL allows multiple rows to contain NULL in a nullable column. PostgreSQL 15+ supports `UNIQUE NULLS NOT DISTINCT` to treat NULLs as equal when enforcing uniqueness.

~~~sql
-- PostgreSQL 15+:
CREATE TABLE external_mappings (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_code TEXT,
    CONSTRAINT uq_external_code
        UNIQUE NULLS NOT DISTINCT (external_code)
);
~~~

Do not use new-version syntax on older servers that do not support it.

### 6.4. Partial Unique Index

If emails are only unique among **non-soft-deleted** customers:

~~~sql
CREATE TABLE customers_soft_delete (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_active_email
ON customers_soft_delete (lower(btrim(email)))
WHERE deleted_at IS NULL;
~~~

The application must agree on whether an email can be reused after soft deletion. A partial index enforces the designed scope; it does not decide the policy itself.

## 7. PRIMARY KEY and FOREIGN KEY

~~~sql
CREATE TABLE sales_customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_code TEXT NOT NULL UNIQUE
);

CREATE TABLE sales_orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES sales_customers(customer_id),
    status TEXT NOT NULL DEFAULT 'draft'
);
~~~

A foreign key ensures that an order does not reference a non-existent customer, even when:

- An import job enters the wrong ID.
- Another API skips pre-checks.
- The customer is deleted in a related transaction.
- Multiple writers run concurrently.

### 7.1. Choose ON DELETE Based on Business Semantics

~~~sql
CREATE TABLE sales_order_lines (
    order_line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES sales_orders(order_id)
        ON DELETE CASCADE,
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

`ON DELETE CASCADE` can delete order lines when the order is deleted. For payment, accounting, or audit data, that behavior may violate retention policies. Do not choose cascade merely for convenience.

### 7.2. FK Does Not Replace Authorization

An existing `customer_id` can still belong to a different tenant. A foreign key only guarantees that the relationship exists; it does not prove the caller has permission to use that object.

Authorization and tenant isolation must be handled in other layers, potentially supplemented with RLS or composite keys including tenant ID where appropriate.

## 8. EXCLUDE: Preventing Overlapping Bookings

The rule "two confirmed bookings cannot overlap for the same room" involves **multiple rows**. Application pre-checks can race; a single-row CHECK is insufficient.

PostgreSQL provides exclusion constraints via GiST and range types.

~~~sql
-- Run in a test database with permission to create extensions.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE booking_rooms (
    room_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_name TEXT NOT NULL
);

CREATE TABLE room_bookings (
    booking_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id BIGINT NOT NULL REFERENCES booking_rooms(room_id),
    booking_period TSTZRANGE NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'confirmed', 'cancelled')),

    CONSTRAINT chk_period_nonempty
        CHECK (NOT isempty(booking_period)),

    CONSTRAINT ex_confirmed_room_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            booking_period WITH &&
        )
        WHERE (status = 'confirmed')
);
~~~

- `TSTZRANGE`: a range of timestamps.
- `&&`: two ranges overlap.
- `room_id WITH =`: compares the same room.
- Predicate filters for confirmed bookings.
- `btree_gist` provides the equality operator class for the required data type.

Example creating the interval `[09:00,10:00)`:

~~~sql
INSERT INTO booking_rooms (room_name)
VALUES ('Room A');

INSERT INTO room_bookings (
    room_id, booking_period, status
)
VALUES (
    1,
    tstzrange(
        TIMESTAMPTZ '2026-11-14 09:00:00+07',
        TIMESTAMPTZ '2026-11-14 10:00:00+07',
        '[)'
    ),
    'confirmed'
);
~~~

A booking starting at exactly 10:00 may be permitted because the range above excludes the 10:00 endpoint. However, a confirmed booking from 09:30 to 10:30 for the same room will conflict.

The database guarantees **no overlapping schedules**. The service must still check whether the room is under maintenance, whether the customer is eligible to book, whether the date falls within operating hours, and when to send notifications.

## 9. DEFERRABLE and Constraint Checking Timing

Some constraint types such as FK, UNIQUE, PRIMARY KEY, and EXCLUDE support `DEFERRABLE`, allowing checks to be deferred until the end of the transaction when declared appropriately.

~~~sql
CREATE TABLE departments (
    department_id BIGINT PRIMARY KEY
);

CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY,
    department_id BIGINT NOT NULL,
    CONSTRAINT fk_employees_departments
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id)
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

Inside a transaction:

~~~sql
BEGIN;

SET CONSTRAINTS fk_employees_departments DEFERRED;

INSERT INTO employees (employee_id, department_id)
VALUES (1, 10);

INSERT INTO departments (department_id)
VALUES (10);

COMMIT;
~~~

At commit time, the FK is valid.

### 9.1. CHECK and NOT NULL Are Not Deferrable in the Same Way

You cannot arbitrarily defer every CHECK/NOT NULL until the end of a transaction. Choose the right constraint type and understand PostgreSQL's limitations.

### 9.2. ON CONFLICT and Deferrable Unique Constraints

A deferrable unique constraint cannot be used as an arbiter for `INSERT ... ON CONFLICT` the way immediate unique indexes/constraints are used. Check compatibility beforehand when designing upserts.

### 9.3. Errors Can Occur at COMMIT

The application must not assume that a finished `INSERT` guarantees transaction success when deferrable constraints are present. The transaction management layer must handle exceptions on commit.

## 10. Domains for Reusable Data Type Rules

~~~sql
CREATE DOMAIN positive_quantity AS INTEGER
CHECK (VALUE > 0);

CREATE TABLE shipment_lines (
    line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quantity positive_quantity NOT NULL
);
~~~

Domains help reuse simple constraints across multiple tables. However, not every quantity value is always positive: inventory adjustment lines may need negative numbers. Choose a domain according to the semantics of the data type, without imposing a rule broader than the business logic.

## 11. Validations to Prioritize in the Application

### 11.1. Request Structure and Format

The API should verify:

- JSON matches the schema.
- Quantities are not accepted as strings when the API requires integers.
- Dates are parseable.
- No unexpected extra fields risking mass assignment.
- Request size limits.
- Required fields are present.

The database can return parse errors, but the application can provide more specific and consistent messages.

### 11.2. Email, Phone, and Address

A simple SQL regex is insufficient to confirm that an email address can receive mail, a phone number belongs to a valid subscriber, or an address lies within a delivery zone. Applications often need libraries, country-specific rule lists, or specialized services.

The database still enforces what can be determined stably: NOT NULL where needed, non-blank strings, keys/uniqueness, and references.

### 11.3. Rules Depending on External Services

Examples:

- A voucher is active on the promotion platform.
- A transaction has been confirmed by the payment gateway.
- An OTP is still valid.
- An address is supported by the shipping carrier.
- KYC has been approved.

These are facts external to the database. PostgreSQL can store verification state and protect integrity, but HTTP requests should not be placed inside `CHECK`.

### 11.4. User Experience

The UI can highlight errors as users type, preserve form data, suggest formatting, and explain rules in friendly language. Returning raw DB error messages usually hurts UX and can leak internal schema details.

## 12. State Transitions Need More Than CHECK

A CHECK:

~~~sql
CHECK (status IN ('draft','submitted','paid','shipped','cancelled'))
~~~

only verifies that the value belongs to the allowed set. It does **not** forbid transitioning from `shipped` back to `draft`.

A workflow might look like:

~~~text
draft -> submitted -> paid -> shipped
                 \
                  -> cancelled
~~~

The service must verify the current state, preconditions, permissions, and external events.

### 12.1. Conditional UPDATE to Prevent Races

~~~sql
UPDATE sales_orders
SET status = 'submitted'
WHERE order_id = 1001
  AND status = 'draft'
RETURNING order_id, status;
~~~

If no row is returned, the status has already changed or the order does not exist. The service must handle this rather than assuming the update succeeded.

### 12.2. What About Multiple Independent Writers?

If many services or jobs have permission to update status directly, checking the workflow in a single service is not enough. Options include:

- Restrict write privileges and require going through a unified service.
- Use conditional UPDATE statements and transactions.
- Use stored procedures with permission checks.
- Use triggers when a state-transition invariant truly must live in the DB.

Triggers can be helpful, but they introduce hidden logic and maintenance complexity, so they are not automatically the best choice.

## 13. Transactions Ensure Multiple Changes Succeed Together

Placing an order may require:

1. Creating the order.
2. Creating order items.
3. Deducting inventory.
4. Recording a stock reservation state.

If each statement commits separately, a failure partway through can leave an incomplete order.

~~~sql
BEGIN;

-- INSERT order
-- INSERT order_items
-- UPDATE inventory conditionally when sufficient stock remains

COMMIT;
~~~

If any step fails, the service must `ROLLBACK` according to the transaction policy.

### 13.1. Transactions Do Not Replace Business Rules

A transaction can successfully commit **semantically wrong** data if the values still satisfy constraints. Transactions provide atomicity and isolation levels, but they do not inherently know "whether this user is eligible for a discount code".

### 13.2. SELECT Followed by UPDATE Is Not Atomic

Buggy pattern:

~~~text
SELECT stock;
If stock >= 1:
    UPDATE stock = stock - 1;
~~~

Two users can read the same `stock = 1` and both decide to buy. Atomic updates, locking, or appropriate isolation must be used.

## 14. Atomic Inventory Updates

~~~sql
CREATE TABLE inventory_products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    available_quantity INTEGER NOT NULL
        CHECK (available_quantity >= 0)
);
~~~

When allocating two units:

~~~sql
UPDATE inventory_products
SET available_quantity = available_quantity - 2
WHERE product_id = 10
  AND available_quantity >= 2
RETURNING product_id, available_quantity;
~~~

If **one row** is returned, the allocation succeeded within the statement/transaction scope. If **0 rows** are returned, the product may not exist or lacks sufficient stock.

**CHECK available_quantity >= 0** still protects against another writer sending an unconditional UPDATE.

### 14.1. Why Putting the Condition Inside UPDATE Matters

PostgreSQL evaluates and updates the row under the engine's concurrency controls, avoiding the race condition of a separate read followed by a blind update.

The service still needs to:

- Link the allocation to the correct order.
- Handle idempotency on retries.
- Release reserved inventory if payment fails.
- Update related tables within the transaction.
- Handle insufficient-stock cases with clear messages.

### 14.2. SELECT FOR UPDATE

In some workflows that must read multiple attributes before deciding:

~~~sql
BEGIN;

SELECT product_id, available_quantity
FROM inventory_products
WHERE product_id = 10
FOR UPDATE;

-- Check and update inside the transaction.

COMMIT;
~~~

Row locking can be useful. However, avoid holding locks while making high-latency external API calls, and keep lock ordering consistent to reduce deadlocks.

## 15. Multi-Row and Multi-Table Invariants

For example, "order total equals the sum of order line totals" or "a submitted order must have at least one item".

These rules span multiple rows and should not be forced into a single-row CHECK.

### 15.1. Avoid Unnecessary Redundant Storage

If the order total is computed by:

~~~sql
SELECT
    order_id,
    SUM(quantity * unit_price) AS total_amount
FROM order_items
GROUP BY order_id;
~~~

consider **computing it at query time** instead of storing an extra `orders.total_amount` that can easily drift, depending on performance and business snapshot requirements.

If the total is stored for audit or performance, the service or DB write protocol must keep it consistently updated.

### 15.2. "Must Have Items Before Submit"

The service can check inside a transaction before changing status. However, if another writer can concurrently delete an item after the check, the rule can still be broken. Consider all write paths, locking, conditional updates, item deletion policies, and appropriate isolation.

### 15.3. Triggers Do Not Automatically Fix All Races

A trigger running `SELECT COUNT(*)` on another table is still subject to MVCC and concurrency rules. To protect multi-row invariants, design appropriate locking, isolation, or coordination tables.

## 16. External Workflows: Payments and Webhooks

A typical flow:

~~~text
Client requests payment
         |
         v
Service validates request + authorizes
         |
         v
Call payment provider
         |
         v
Receive authenticated webhook
         |
         v
Handle idempotency
         |
         v
Transaction records payment/order state
         |
         v
PostgreSQL constraints protect data
~~~

No CHECK constraint can prove that funds actually arrived in a bank account. The "paid" rule depends on verified events from the provider, along with retry and reconciliation mechanisms.

Commonly needed tools include:

- Idempotency keys.
- Webhook signatures.
- Outbox/inbox patterns for distributed events.
- Bounded retries.
- Reconciliation between the provider and the database.
- Ensuring DB changes occur within the same transaction.

## 17. Validation Does Not Replace Authorization

A request with a valid `order_id` and valid status can still be unauthorized if the sender does not own the order.

Defense layers include:

- Authentication at the API.
- Authorization in the domain service.
- PostgreSQL GRANT/REVOKE.
- Row-Level Security when the tenant model requires it.
- Least-privilege database roles.
- Auditing for sensitive operations.

A foreign key verifies that the referenced object **exists**; it does not confirm that the user is permitted to access that object.

### 17.1. Pooled Connections Must Manage Tenant Context

If RLS relies on a session setting to identify the current tenant, the application must set and reset that context accurately per request or transaction. Never allow a reused connection to retain the previous user's context.

## 18. SQLSTATE: Technical Error Interface Between PostgreSQL and the Application

PostgreSQL returns SQLSTATE error codes, typically five characters long. The application should use the code and constraint/index name to map errors rather than parsing DB message strings.

| SQLSTATE | Common Name | Cause |
|---|---|---|
| `23502` | not_null_violation | NULL in a NOT NULL column |
| `23503` | foreign_key_violation | FK violation |
| `23505` | unique_violation | Duplicate unique key |
| `23514` | check_violation | CHECK condition failed |
| `23P01` | exclusion_violation | Exclusion constraint violated |
| `22P02` | invalid_text_representation | String cannot be parsed into target type |
| `22001` | string_data_right_truncation | Exceeds data type length |
| `40001` | serialization_failure | Transaction must retry |
| `40P01` | deadlock_detected | PostgreSQL detected a deadlock |

### 18.1. Translating Errors into User-Facing Messages

| Error | Example API Message |
|---|---|
| `23502` | "Missing required field" |
| `23505` on email | "Email is already in use" |
| `23503` on customer | "Customer no longer exists" |
| `23514` on quantity | "Quantity must be greater than 0" |
| `23P01` on booking | "Time slot is already booked" |

Do not map **every 23505 to an email error**: there are also SKUs, invoice numbers, order codes, and idempotency keys.

### 18.2. Do Not Expose Raw SQL Error Messages to Clients

DB errors can contain table/column names and data values. The API should return stable, context-appropriate messages; internal logs must comply with sensitive-data protection policies.

### 18.3. Errors Can Occur at COMMIT

With deferrable constraints, an INSERT statement may initially succeed while the transaction fails at COMMIT. The transaction management layer must catch errors even after all individual statements have executed.

## 19. Java: Identifying Errors via SQLSTATE

~~~java
import java.sql.SQLException;

public final class DbValidationErrors {

    public static String message(SQLException error) {
        String sqlState = error.getSQLState();

        if (sqlState == null) {
            return "Unable to save data.";
        }

        return switch (sqlState) {
            case "23502" -> "Missing required field.";
            case "23503" -> "Referenced data is no longer valid.";
            case "23505" -> "Value is already in use.";
            case "23514" -> "Value violates data rules.";
            case "23P01" -> "Data conflicts with another record.";
            case "40001", "40P01" ->
                "Transaction conflict, please retry.";
            default -> "Unable to save data.";
        };
    }
}
~~~

This is an illustrative example. In real systems, accurate messages require distinguishing the specific constraint and the endpoint's business context.

With pgJDBC, you can read the constraint name from the server error:

~~~java
import java.sql.SQLException;
import org.postgresql.util.PSQLException;
import org.postgresql.util.ServerErrorMessage;

public final class ConstraintInfo {

    public static String getConstraintName(SQLException error) {
        if (error instanceof PSQLException pgError) {
            ServerErrorMessage details = pgError.getServerErrorMessage();
            return details == null ? null : details.getConstraint();
        }
        return null;
    }
}
~~~

Never let user-supplied constraint names determine permissions or operation types. Constraint names are only metadata to help the API map errors.

### 19.1. Retrying Serialization Failures

If PostgreSQL returns `40001`, you generally must **retry the entire transaction** with a retry limit and appropriate backoff. Re-running only the final UPDATE could rely on data read from a stale snapshot.

When a transaction is paired with sending emails or calling external providers, use idempotency/outbox mechanisms to avoid duplicating external side effects.

## 20. PostgreSQL Lab: A Sales Model with Layered Protection

Practice in a **test database** with CREATE SCHEMA privileges. Do not run in production. If the `validation_lab` schema already exists, choose another database or schema name.

### 20.1. Create Schema and Customers

~~~sql
CREATE SCHEMA validation_lab;

CREATE TABLE validation_lab.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL,
    full_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_customers_email_not_blank
        CHECK (btrim(email) <> ''),

    CONSTRAINT chk_customers_name_not_blank
        CHECK (btrim(full_name) <> '')
);

CREATE UNIQUE INDEX uq_customers_email_normalized
ON validation_lab.customers (lower(btrim(email)));
~~~

PostgreSQL enforces non-NULL, non-blank, and unique canonical email invariants. However, the backend must still validate format, account creation permissions, and email verification.

The normalization rule `lower(btrim(email))` is only a lab convention and does not mean every real-world email system should compare addresses case-insensitively in that exact way.

### 20.2. Create Products

~~~sql
CREATE TABLE validation_lab.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT chk_product_name_not_blank
        CHECK (btrim(product_name) <> ''),
    CONSTRAINT chk_product_price_nonnegative
        CHECK (price >= 0),
    CONSTRAINT chk_product_stock_nonnegative
        CHECK (stock >= 0)
);
~~~

### 20.3. Create Orders and Order Items

~~~sql
CREATE TABLE validation_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    shipping_address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES validation_lab.customers(customer_id),

    CONSTRAINT chk_orders_status
        CHECK (status IN ('draft', 'submitted', 'cancelled')),

    CONSTRAINT chk_submitted_address
        CHECK (
            status <> 'submitted'
            OR NULLIF(btrim(shipping_address), '') IS NOT NULL
        )
);

CREATE TABLE validation_lab.order_items (
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,

    CONSTRAINT pk_order_items
        PRIMARY KEY (order_id, product_id),

    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES validation_lab.orders(order_id),

    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id)
        REFERENCES validation_lab.products(product_id),

    CONSTRAINT chk_item_quantity
        CHECK (quantity > 0),

    CONSTRAINT chk_item_unit_price
        CHECK (unit_price >= 0)
);
~~~

### 20.4. Role of Each Constraint

| Rule | Constraint |
|---|---|
| Order must belong to a valid customer | FK |
| Status belongs to allowed set | CHECK |
| Submitted requires address | Same-row CHECK |
| A product appears at most once per order | Composite PK |
| Positive quantity | NOT NULL + CHECK |
| Non-negative unit price | NOT NULL + CHECK |
| Customer is allowed to place order | Service/authorization |
| Product is active and stock is sufficient | Service + atomic UPDATE |
| Submitted order has at least one item | Service/transaction and write-path protection |
| Order total is accurate | Calculation logic and synchronization mechanism |

### 20.5. Insert Valid Data

~~~sql
INSERT INTO validation_lab.customers (email, full_name)
VALUES ('alice@example.com', 'Alice');

INSERT INTO validation_lab.products (
    sku, product_name, price, stock
)
VALUES ('BOOK-001', 'PostgreSQL Book', 150000.00, 10);
~~~

Create a draft order and order item without guessing identity IDs:

~~~sql
WITH new_order AS (
    INSERT INTO validation_lab.orders (customer_id, status)
    SELECT customer_id, 'draft'
    FROM validation_lab.customers
    WHERE email = 'alice@example.com'
    RETURNING order_id
)
INSERT INTO validation_lab.order_items (
    order_id, product_id, quantity, unit_price
)
SELECT
    o.order_id, p.product_id, 2, p.price
FROM new_order AS o
CROSS JOIN validation_lab.products AS p
WHERE p.sku = 'BOOK-001';
~~~

The example above **does not deduct inventory yet**. In a real application, creating the order, order lines, and allocating inventory require a transaction aligned with ordering policies.

### 20.6. Test CHECK

~~~sql
-- Expected to be rejected by the DB.
UPDATE validation_lab.products
SET stock = -1
WHERE sku = 'BOOK-001';
~~~

### 20.7. Test UNIQUE

~~~sql
-- Expected to be rejected by the unique index.
INSERT INTO validation_lab.customers (email, full_name)
VALUES ('  ALICE@EXAMPLE.COM  ', 'Alice Duplicate');
~~~

`lower(btrim(email))` of the second email matches the first.

### 20.8. Test FOREIGN KEY

~~~sql
-- Expected to be rejected by the FK if this ID does not exist.
INSERT INTO validation_lab.orders (customer_id)
VALUES (999999);
~~~

### 20.9. Test Status-Based CHECK

~~~sql
-- A draft order missing an address cannot transition to submitted.
UPDATE validation_lab.orders
SET status = 'submitted'
WHERE customer_id = (
    SELECT customer_id
    FROM validation_lab.customers
    WHERE email = 'alice@example.com'
);
~~~

A valid update must include the address:

~~~sql
UPDATE validation_lab.orders
SET shipping_address = '123 Example Street',
    status = 'submitted'
WHERE customer_id = (
    SELECT customer_id
    FROM validation_lab.customers
    WHERE email = 'alice@example.com'
)
  AND status = 'draft'
RETURNING order_id, status;
~~~

### 20.10. Test Atomic Inventory Update

~~~sql
UPDATE validation_lab.products
SET stock = stock - 2
WHERE sku = 'BOOK-001'
  AND active = TRUE
  AND stock >= 2
RETURNING product_id, stock;
~~~

Returning 0 rows means the allocation condition was not met or the product does not exist. The application must not treat this as a success.

## 21. Migrations When Adding Constraints to Existing Data

A large table with existing invalid data cannot accept a new CHECK constraint if PostgreSQL must validate all rows immediately.

A phased rollout approach for supported constraint types:

~~~sql
ALTER TABLE validation_lab.products
ADD CONSTRAINT chk_products_price_v2
CHECK (price >= 0) NOT VALID;
~~~

`NOT VALID` lets you add certain constraints like CHECK/FK without immediately scanning and validating all existing rows. However, new writes/updates still enforce the rule accordingly.

After cleaning up existing data:

~~~sql
ALTER TABLE validation_lab.products
VALIDATE CONSTRAINT chk_products_price_v2;
~~~

### 21.1. NOT VALID Does Not Mean Skipping Checks for New Rows

Do not leave an unvalidated constraint as a "skip validation" mode. Quantify legacy invalid data, clean it up, validate the constraint, and monitor.

### 21.2. Not Every Constraint Supports NOT VALID

Do not assume `UNIQUE NOT VALID` works like CHECK. For uniqueness on large tables, consider creating a unique index concurrently and attaching the constraint according to the appropriate procedure/version.

### 21.3. CREATE INDEX CONCURRENTLY

`CREATE INDEX CONCURRENTLY` has operational restrictions, including not running inside a regular transaction block. If duplicate data exists, unique index creation can fail and leave an invalid index that must be handled.

Never run a production migration just because the syntax is valid; evaluate locks, duration, disk space, permissions, and rollback capability.

### 21.4. Adding NOT NULL

If a column currently contains NULLs, `SET NOT NULL` requires a strategy to backfill data first. Check your PostgreSQL version and ways to minimize scans/locks rather than assuming schema changes are always instantaneous.

## 22. Coordinating Rollouts Between Application and DB

Example new rule: submitted orders must have an address. A rollout might proceed as follows:

1. Agree on the exact rule and exceptions (in-store pickup, technical orders).
2. Audit existing submitted orders missing an address.
3. Update services/APIs to prevent creating new invalid data.
4. Update background jobs, mobile clients, and admin tools.
5. Clean up historical data according to business rules.
6. Add the constraint using an appropriate strategy.
7. Validate and monitor errors post-deployment.
8. Add corresponding tests to the pipeline.

Tightening the DB before legacy writers adapt can cause error spikes; updating only the application without ever adding the DB invariant leaves other write paths free to create invalid data. Plan compatibility in phases.

### 22.1. Meaningful Constraint Names

~~~sql
CONSTRAINT chk_submitted_address ...
CONSTRAINT uq_tenant_customer_code ...
CONSTRAINT fk_items_order ...
~~~

Clear names help with debugging, SQLSTATE mapping, and migration tracking. However, technical names do not need to be exposed to end users.

## 23. Testing Validation Layers

### 23.1. UI Tests

- Required fields are marked.
- Negative quantities are blocked on the form.
- Users receive messages in the right language.
- Different state cases are displayed consistently.

### 23.2. API/Service Tests

- Mistyped JSON is rejected.
- Cannot update another user's order.
- Invalid workflow transitions are rejected.
- Invalid payment callbacks do not mark an order as paid.
- Retries do not create duplicate transactions.
- PostgreSQL errors are mapped in a structured way.

### 23.3. Database Integration Tests

~~~sql
-- Expected to violate CHECK quantity.
INSERT INTO validation_lab.order_items (
    order_id, product_id, quantity, unit_price
)
VALUES (1, 1, 0, 10000);

-- Expected to violate FK customer.
INSERT INTO validation_lab.orders (customer_id)
VALUES (999999);

-- Expected to violate UNIQUE sku.
INSERT INTO validation_lab.products (
    sku, product_name, price, stock
)
VALUES ('BOOK-001', 'Duplicate', 100000, 1);
~~~

Tests should assert the exact SQLSTATE code and corresponding constraint in a properly seeded environment, rather than merely asserting that any exception occurred.

### 23.4. Concurrency Tests

Critical scenario:

~~~text
Initial stock = 1

Worker A wants to buy 1 unit.
Worker B wants to buy 1 unit.
Both run concurrently.

Expected:
- Only one worker allocates successfully.
- The other worker is notified of insufficient stock.
- Final stock is non-negative.
- Two confirmed orders using the same inventory do not occur.
~~~

Sequential unit tests of a service do not prove correctness under concurrency. Integration tests against real PostgreSQL are required.

### 23.5. Migration Tests

- Violating legacy data is detected.
- Cleanup does not break business semantics.
- New writes are constrained during the transition period.
- The constraint validates successfully.
- Rollback/recovery plans can be executed if failures occur.

## 24. Observing Validation Errors in Operations

After deployment, a rise in constraint error rates may indicate:

- Outdated mobile clients that have not updated.
- An import job sending bad data.
- A race condition in a service.
- Referenced data was modified.
- Drift between DB and application rules.
- A migration added a constraint before data was clean.

What to observe:

| Source | Metrics |
|---|---|
| API | Validation error count by endpoint |
| Application | SQLSTATE, constraint name, correlation ID |
| PostgreSQL | Integrity errors, deadlocks, serialization failures, lock waits |
| Business metrics | Rejected orders, booking conflicts, allocation failures |

Do not arbitrarily log sensitive data from DB error details. Error codes and constraint names are usually sufficient to classify errors without storing full emails, tokens, or customer information.

## 25. Common Misconceptions

### 25.1. "The UI already validates it, so the DB doesn't need constraints"

False. APIs, jobs, and scripts can bypass the UI.

### 25.2. "The database validates it, so the application doesn't need validation"

False. UX, request parsing, permissions, and business workflows are still needed.

### 25.3. "SELECT to check if an email exists before INSERT is safe"

False under concurrency. A DB UNIQUE constraint must make the final decision.

### 25.4. "CHECK (amount > 0) automatically prevents NULL"

False. UNKNOWN is accepted; add NOT NULL if required.

### 25.5. "A foreign key proves the user has permission to reference the row"

No. FKs check existence of the relationship; authZ is a separate concern.

### 25.6. "A row-counting trigger automatically prevents races"

Not necessarily. Proper transaction and locking design is required.

### 25.7. "Transactions guarantee all business logic is correct"

No. Transactions can commit semantically invalid values if code and constraints do not enforce the rule.

### 25.8. "Every 23505 error is a duplicate email"

False. You must inspect the specific constraint/index.

### 25.9. "CHECK status IN (...) manages transitions"

No. It only protects the valid set of states.

### 25.10. "Calling HTTP inside CHECK is a valid way to verify payments"

No. External systems are not part of PostgreSQL transactions and can time out or change state.

### 25.11. "NOT VALID allows new data to keep violating the rule"

False. For CHECK/FK using this mechanism, new writes and updates are still checked.

### 25.12. "NOT VALID works for every constraint"

False. Unique constraints require their own strategy.

### 25.13. "Retry only the final statement after SQLSTATE 40001"

Incorrect. You must retry the entire transaction and guard external side effects.

### 25.14. "All validation must go into triggers"

No. Orchestration logic, UX, and external services generally belong in the service layer. Triggers require clear justification and thorough testing.

### 25.15. "Two copies of a rule in UI and DB naturally stay identical"

No. Contract management and tests are required to prevent drift.

## 26. Decision Framework for Where Rules Belong

When encountering a new rule, ask yourself:

1. Is it something that must always be true in committed data?
2. Does it depend on a single row or multiple rows/tables?
3. Is there an appropriate PostgreSQL constraint?
4. Must it hold under concurrent transactions?
5. Does it depend on identity, tenant, or permissions?
6. Does it depend on external systems or wall-clock time?
7. Does it change frequently based on business needs?
8. Do users need early feedback to correct it?
9. When the DB rejects it, can the API translate it into a clear error?
10. Can redundant data storage be avoided?
11. Do legacy writers and historical data satisfy the rule?
12. Are concurrency tests and migration tests in place?

### 26.1. Recommended Responsibility Split

| Rule | Database | Application |
|---|---|---|
| Required name | NOT NULL | Required check |
| Non-blank name | CHECK | Trim/UX |
| Non-negative price | CHECK | Fail fast |
| Tenant-unique email | Appropriate UNIQUE | Pre-check + catch 23505 |
| Order references customer | FK | Lookup and handle 23503 |
| Non-negative stock | CHECK + atomic UPDATE | Orchestrate and report out-of-stock |
| Non-overlapping confirmed bookings | EXCLUDE when appropriate | Slot selection and conflict explanation |
| Submitted order has address | Same-row CHECK | Form and transition |
| Provider confirms payment | Store internal integrity | Webhook, auth, retry |
| User edits only own orders | RLS/GRANT if used | Authorization |
| Line totals equal order total | Data design/transaction | Calculation and synchronization |
| Promotion eligibility | Protect reference data | Domain and campaign rules |

## 27. Practice Exercises

### Exercise 1 — Item Quantity

Divide the check that quantity must be a positive integer across the UI, API, service, and database.

**Hint:** UI notifies; API parses integer; service checks purchasability; DB uses `INTEGER NOT NULL CHECK (quantity > 0)`.

### Exercise 2 — Duplicate Email Under Concurrency

Two requests both observe that an email does not exist yet. Why is a pre-check insufficient?

**Hint:** Race between SELECT and INSERT; a unique index protects the final outcome.

### Exercise 3 — NULL in CHECK

Does `amount NUMERIC CHECK (amount > 0)` block NULL?

**Hint:** No; use NOT NULL if required.

### Exercise 4 — Whitespace-Only Strings

Write a constraint forbidding the name `'   '`.

~~~sql
display_name TEXT NOT NULL
CHECK (btrim(display_name) <> '')
~~~

### Exercise 5 — Multi-Tenant Uniqueness

Each tenant has its own customer codes. Two tenants may use the same code. Write the constraint.

~~~sql
UNIQUE (tenant_id, customer_code)
~~~

### Exercise 6 — Authorization

An order ID exists, but it belongs to another customer. Are FK and CHECK enough?

**Hint:** No. Authorization and access control policies are needed.

### Exercise 7 — Atomic Stock Deduction

Stock = 1, two users buy at the same time. Write a safe UPDATE:

~~~sql
UPDATE inventory_products
SET available_quantity = available_quantity - 1
WHERE product_id = 10
  AND available_quantity >= 1
RETURNING available_quantity;
~~~

**Hint:** Only the worker that updates one row succeeds.

### Exercise 8 — Overlapping Bookings

Why doesn't `CHECK(start < end)` prevent two bookings for the same room from overlapping in time?

**Hint:** A CHECK only inspects a single row; EXCLUDE or another transaction protocol is needed.

### Exercise 9 — SQLSTATE Codes

Match `23505`, `23503`, `23514`, and `23P01` with UNIQUE, FK, CHECK, and EXCLUDE.

### Exercise 10 — Payments

Why should you not call a payment API from inside a CHECK constraint?

**Hint:** External state and side effects do not fit row-level constraints.

### Exercise 11 — NOT VALID

Explain how to add a CHECK constraint to a table containing unverified legacy data.

**Hint:** ADD CHECK NOT VALID, clean up data, VALIDATE CONSTRAINT.

### Exercise 12 — Retries

A transaction receives 40001. Should you re-run only the final INSERT statement?

**Hint:** You typically need to retry the entire transaction with a retry limit while protecting external side effects.

### Exercise 13 — Status

Does `CHECK status IN ('draft','submitted','cancelled')` forbid transitioning `cancelled -> submitted`?

**Hint:** No; transition validation is required.

### Exercise 14 — Legacy Clients

An older mobile app does not send an address on submit. If the new DB requires an address, what happens?

**Hint:** The DB rejects it; the rollout must handle writer compatibility and error messaging.

### Exercise 15 — Derived Data

When the order total always equals `SUM(quantity*price)`, name two design options.

**Hint:** Compute at query time, or store a snapshot kept synchronized via transactions.

### Exercise 16 — Error Mapping

PostgreSQL returns 23505 from index `uq_customers_email_normalized`. What should the API return?

**Hint:** User-facing message "Email is already in use", without exposing internal SQL.

## 28. Quick Reference

| Question | Answer |
|---|---|
| Does UI validation protect the DB from all writers? | No |
| Should the DB hold foundational invariants? | Yes, via constraints |
| Does the application still need validation? | Yes, for UX, workflows, security |
| Does CHECK automatically forbid NULL? | No |
| Does a UNIQUE pre-check prevent races? | No |
| Do FKs guarantee authorization? | No |
| What are exclusion constraints used for? | Enforcing multi-row mutual exclusion rules |
| Is every CHECK deferrable? | No |
| Should triggers be used for every business rule? | No |
| Non-negative stock and accurate allocation? | CHECK + atomic UPDATE/transaction |
| SQLSTATE for UNIQUE? | 23505 |
| SQLSTATE for FK? | 23503 |
| SQLSTATE for CHECK? | 23514 |
| SQLSTATE for EXCLUDE? | 23P01 |
| Serialization failure? | 40001 |
| How to retry serialization failure? | Entire transaction |
| Does NOT VALID skip checks on new writes? | No |
| Where do external payment rules belong? | Service/provider workflow |
| Where does "user edits only own orders" belong? | Authorization/RLS |
| Want good UX? | Pre-validate and map DB errors |
| Want reliable data? | Constraints and transactions across all write paths |

---

## Conclusion

**Dividing data validation between PostgreSQL and the application** is about combining complementary strengths, not picking one side and discarding the other. The UI and API validate early so users can fix inputs; domain services orchestrate business rules, access control, and external services; transactions and PostgreSQL constraints protect data at write time across multiple write paths and concurrent requests.

Invariants such as **NOT NULL, CHECK, UNIQUE, PRIMARY KEY, FOREIGN KEY, and EXCLUDE** should live in the database where appropriate, while complex workflows must be managed through services and clear transaction protocols. In particular, the "SELECT to check then INSERT" pattern does not replace uniqueness constraints or atomic updates under concurrency.

When rolling out new rules, account for legacy data, older clients, migrations, SQLSTATE codes, permissions, retries, and concurrency testing. A well-designed system not only **reports clear errors at the right time**, but also **never allows data violating invariants to commit**, whether it arrives from a form, API, batch job, or any other writer.
