# Idempotency, Unique Keys, and Preventing Duplicate Writes on Retry in PostgreSQL

In real-world systems, a data write request can be sent **multiple times even when the user performs only a single action**. A network connection drops after the database has committed, the client never receives the response, a gateway retries automatically, a worker re-receives a message, or the user clicks the pay button again. If the SQL statement is designed as a brand-new write on every call, the system can create **two orders, deduct inventory twice, award points twice, or emit two events**.

The core problem is **idempotency**: when the same valid request is executed again, the observable business effect **is not multiplied**. PostgreSQL helps you build this mechanism using unique keys (`PRIMARY KEY`, `UNIQUE`, unique indexes), `INSERT ... ON CONFLICT`, transactions, update conditions, row locks, and `RETURNING`.

After this lesson, you will know how to:

- Distinguish **retry**, **idempotency**, **deduplication**, and **exactly-once**.
- Identify **business keys** and **idempotency keys** along with their uniqueness scope.
- Use `UNIQUE`/`ON CONFLICT DO NOTHING` to block duplicate row creation when two sessions run concurrently.
- Understand when `ON CONFLICT DO UPDATE` fits and why it can **break idempotency**.
- Detect the same idempotency key carrying **different request content**.
- Design a PostgreSQL transaction encompassing order creation, saving the idempotency result, and writing to a transactional outbox.
- Handle `RETURNING` returning 0 rows, concurrent transaction conflicts, isolation, and retries after errors.
- Avoid repeating non-idempotent operations such as `SET quantity = quantity - 3`.
- Test retries using the lab dataset and simulated two-session scenarios.

## 1. Why Can a Request Succeed Yet Still Be Retried by the Client?

Suppose an order-creation application works like this:

~~~text
1. Client sends POST /orders, request_id = "req-A".
2. Server runs INSERT into orders.
3. PostgreSQL COMMIT succeeds.
4. Server sends HTTP 201, but the connection drops.
5. Client assumes failure and resends req-A.
6. Without duplicate protection: server INSERTs a second order.
~~~

At step 5, the client **does not know for certain** whether the first attempt committed or not. Retrying is a standard way to achieve resilience under transient failures; the receiver must handle repeated calls safely.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    participant D as PostgreSQL
    C->>S: Create order, key=req-A
    S->>D: INSERT order
    D-->>S: COMMIT succeeds
    S--xC: Response lost
    C->>S: Retry key=req-A
    S->>D: Look up key and saved result
    D-->>S: Order created on first attempt
    S-->>C: Return previous result, do not create second order
~~~

**You cannot rely on "the client only clicks once".** Requests can be replayed by gateways, job schedulers, queue consumers, SDKs, or automatic retry logic. A data-writing system must clearly define what counts as **the same business operation**.

## 2. Distinguishing Easily Confused Concepts

| Term | Meaning | Example |
| --- | --- | --- |
| **Retry** | Re-executing a call after an error or uncertain outcome | Sending the same POST body a second time |
| **Idempotency** | Repeating the same operation does not add additional business effect | Two POSTs with the same key lead to one order |
| **Deduplication** | Detecting and discarding/not processing duplicate records | Unique index blocks two rows with the same key |
| **Business key** | A business identifier that already has inherent uniqueness | A tenant's order code |
| **Idempotency key** | Identifier for **one logical request**, kept unchanged across retries | `req-5ec...` |
| **Atomicity** | All changes in a transaction commit together or roll back together | Order + outbox commit together |
| **Exactly-once** | An end-to-end property harder than database dedupe; spans multiple systems | Not triggering two payment effects at an external provider |

Idempotency is often expressed as an operation:

~~~text
apply(request, state)
apply(request, apply(request, state))

Both must produce the same observable business effect
for the same logical request.
~~~

Note: **the returned HTTP result does not have to be byte-for-byte identical** if the API contract specifies returning `201 Created` on the first call and `200 OK` on retry. However, the **business order or payment** must not be created a second time. If the contract requires replaying the exact original status/body, you must store those response details to return them consistently.

## 3. Classifying SQL Operations by Idempotency

Not every SQL statement is idempotent:

| Operation | When run twice | Idempotent in data effect? |
| --- | --- | --- |
| `UPDATE t SET status = 'paid' WHERE id = 1` | Final state is `paid` either way | Usually yes, though it can still fire triggers/audits twice |
| `UPDATE t SET stock = stock - 3 WHERE id = 1` | Deducts 6 instead of 3 | **No** |
| `UPDATE t SET points = points + 10 WHERE id = 1` | Adds 20 instead of 10 | **No** |
| `DELETE FROM t WHERE id = 1` | Row is only deleted once | Table state is usually idempotent; check side effects |
| `INSERT INTO orders ...` | Can insert two rows | **No**, without a duplicate-preventing key |
| `INSERT ... ON CONFLICT DO NOTHING` | Subsequent runs add no row on conflicting key | Usually idempotent in row count inserted; check payload |
| `INSERT ... ON CONFLICT DO UPDATE SET count = count + 1` | Increments count every time | **No** |
| `INSERT ... ON CONFLICT DO UPDATE SET status = EXCLUDED.status` | Final state is identical | Can be idempotent in value, yet still causes update side effects |

Key point: **"An unchanged final value" does not mean every effect only happened once.** A repeated `UPDATE` can bump a version, update `updated_at`, generate WAL, fire triggers, or emit events. If you want an event emitted only once, you must explicitly enforce that **only the first action is recorded**.

## 4. Business Keys and Idempotency Keys Serve Two Different Purposes

An order may have:

- `order_id`: technical key generated by PostgreSQL.
- `(tenant_id, client_order_code)`: business key unique within a tenant.
- `(tenant_id, operation, idempotency_key)`: identifier for a **logical request** that a client may resend.

Example:

~~~text
tenant_id         = 10
client_order_code = WEB-2026-001
idempotency_key   = 12f6c1ba-... (generated for the create call)
operation         = create_order
~~~

A key is newly generated for **each new request**, but **must remain unchanged when retrying that same request**. If the client generates a different key on every retry, the server has no way to use that key to recognize them as the same operation.

### Why Is a Business Key Still Needed?

Two requests with **two different idempotency keys** might attempt to create the same business order `WEB-2026-001`. A unique constraint on the business code still protects against having two identical orders within a tenant.

Conversely, an idempotency key may be needed to protect operations not tied to an easily inferred business-key row—such as granting reward points, placing a reservation hold, or creating multiple related records.

A **business key** protects entity uniqueness; an **idempotency key** protects against reprocessing a request.

## 5. Preparing the Practice Schema

All examples use a **dedicated lab database** and the `retry_lab` schema. This script **drops the entire `retry_lab` schema if it already exists**, so do not run it on a shared database or on data you need to keep.

### 5.1. Creating the orders, request, and outbox Tables

~~~sql
-- WARNING: run only in a lab database you own.
DROP SCHEMA IF EXISTS retry_lab CASCADE;
CREATE SCHEMA retry_lab;

CREATE TABLE retry_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL CHECK (tenant_id > 0),
    client_order_code text NOT NULL,
    amount numeric(14, 2) NOT NULL CHECK (amount >= 0),
    currency text NOT NULL CHECK (currency IN ('VND', 'USD')),
    status text NOT NULL DEFAULT 'created'
        CHECK (status IN ('created', 'paid', 'cancelled')),
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_orders_tenant_code
        UNIQUE (tenant_id, client_order_code),
    CONSTRAINT chk_order_code_nonblank
        CHECK (btrim(client_order_code) <> '')
);

CREATE TABLE retry_lab.idempotency_requests (
    tenant_id integer NOT NULL CHECK (tenant_id > 0),
    operation text NOT NULL,
    idempotency_key text NOT NULL,
    request_payload jsonb NOT NULL,
    state text NOT NULL DEFAULT 'processing'
        CHECK (state IN ('processing', 'completed')),
    order_id bigint REFERENCES retry_lab.orders(order_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,

    PRIMARY KEY (tenant_id, operation, idempotency_key),
    CHECK (btrim(idempotency_key) <> ''),
    CHECK (
        (state = 'processing'
            AND order_id IS NULL
            AND completed_at IS NULL)
        OR
        (state = 'completed'
            AND order_id IS NOT NULL
            AND completed_at IS NOT NULL)
    )
);

CREATE TABLE retry_lab.outbox_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    order_id bigint NOT NULL
        REFERENCES retry_lab.orders(order_id),
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,

    CONSTRAINT uq_event_per_order
        UNIQUE (tenant_id, order_id, event_type)
);

CREATE TABLE retry_lab.inventory (
    product_id integer PRIMARY KEY,
    quantity integer NOT NULL CHECK (quantity >= 0)
);

CREATE TABLE retry_lab.stock_deductions (
    product_id integer NOT NULL
        REFERENCES retry_lab.inventory(product_id),
    operation_key text NOT NULL,
    deduct_quantity integer NOT NULL CHECK (deduct_quantity > 0),
    remaining_quantity integer,
    created_at timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (product_id, operation_key),
    CHECK (remaining_quantity IS NULL OR remaining_quantity >= 0)
);

INSERT INTO retry_lab.inventory (product_id, quantity)
VALUES (501, 8), (502, 0);
~~~

Explanation of the constraints:

| Table | Key constraint | Invariant protected |
| --- | --- | --- |
| `orders` | `UNIQUE (tenant_id, client_order_code)` | No two orders with the same code in one tenant |
| `idempotency_requests` | `PRIMARY KEY (tenant_id, operation, idempotency_key)` | One key cannot represent two requests for the same operation/tenant |
| `idempotency_requests` | `state/order_id/completed_at CHECK` | A `completed` row must have both a result and a completion timestamp |
| `outbox_events` | `UNIQUE (tenant_id, order_id, event_type)` | Never write two events of the same type for one order |
| `inventory` | `CHECK(quantity >= 0)` | Never store negative stock |
| `stock_deductions` | `PRIMARY KEY(product_id, operation_key)` | One stock-deduction request per product has at most one deduplication record |

The `state = 'processing'` columns in this lesson are used within **an uncommitted transaction** and then updated to `completed` before commit. The table still permits a `processing` row to be created by another operation; in a real system you need recovery rules for committed `processing` rows. The sample function shown later does not intentionally commit an incomplete `processing` state.

## 6. Unique Within What Scope?

If `idempotency_key = 'abc'` arrives from two different tenants, those can be **two independent, valid requests**. Therefore, the key:

~~~sql
PRIMARY KEY (tenant_id, operation, idempotency_key)
~~~

allows tenant 10 and tenant 20 to both use key `abc`, while preventing tenant 10 from processing **two different `create_order` requests** with the same key `abc`.

If the order-creation endpoint and the order-cancellation endpoint receive the same key string, the `operation` column keeps them from colliding. Some systems use a single key across the whole account/API; others namespace per endpoint. **Document the scoping rules explicitly in your API contract.**

### Do Not Use Empty Strings or Default Values as Keys

If every request missing a key is turned into `''`, they will collide with each other or be misclassified as retries. In the lab design, `idempotency_key` is `NOT NULL` and has a `CHECK` ensuring it is non-empty after trimming.

In a real API, keys should have a maximum length, be bound to the caller/tenant identity, and have enough randomness to be hard to guess. Never trust a `tenant_id` taken directly from a request without authorizing the client for that tenant.

## 7. Why SELECT Before INSERT Does Not Prevent Race Conditions

A common pattern that is **unsafe under concurrent sessions**:

~~~sql
-- Dangerous pattern without the right constraint:
SELECT order_id
FROM retry_lab.orders
WHERE tenant_id = 10
  AND client_order_code = 'WEB-001';

-- If not found, then...
INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-001', 120.00, 'VND');
~~~

What can happen:

~~~text
Session A                       Session B
---------------------------     ---------------------------
SELECT: no WEB-001 yet          SELECT: no WEB-001 yet
INSERT WEB-001                  INSERT WEB-001
COMMIT                          COMMIT
~~~

If there is **no unique constraint**, both sessions can commit and create two orders.

If there **is a unique constraint**, one session will be unable to commit the duplicate key: PostgreSQL coordinates uniqueness checks through its index/concurrency mechanism. The losing session may have to wait and then receive a unique violation error (SQLSTATE `23505`) if it uses a plain `INSERT`.

**Conclusion:** pre-checking with `SELECT` helps express business flow, but it cannot replace a database `UNIQUE` constraint. The constraint is the decisive line of defense when multiple workers or API instances run concurrently.

## 8. INSERT ... ON CONFLICT DO NOTHING

PostgreSQL provides upsert syntax to handle unique-key conflicts:

~~~sql
INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-001', 120.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO NOTHING
RETURNING order_id, tenant_id, client_order_code;
~~~

The first time, one row is inserted and `RETURNING` yields the new order's ID.

If you run the same statement again:

~~~sql
INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-001', 120.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO NOTHING
RETURNING order_id;
~~~

the result is **0 rows**, because the key `(tenant_id, client_order_code)` already exists.

Try it without leaving data behind:

~~~sql
BEGIN;

INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-001', 120.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO NOTHING
RETURNING order_id;

INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-001', 120.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO NOTHING
RETURNING order_id;

SELECT COUNT(*) AS matching_orders
FROM retry_lab.orders
WHERE tenant_id = 10
  AND client_order_code = 'WEB-001';

ROLLBACK;
~~~

Inside the transaction, the count of orders with that business code is **1**. The first `INSERT` returns an ID; the second returns no rows; after rollback the database returns to its initial state.

### Which Constraint Does ON CONFLICT (columns) Use?

`ON CONFLICT (tenant_id, client_order_code)` tells PostgreSQL to infer a matching unique index/constraint to serve as the **arbiter**. It does not mean you can pass an arbitrary set of columns that has no uniqueness protection.

You can write:

~~~sql
ON CONFLICT ON CONSTRAINT uq_orders_tenant_code DO NOTHING
~~~

if you want to name a declared unique constraint explicitly. Listing columns is often convenient when constraint names may change while uniqueness semantics stay the same; naming the constraint explicitly states the exact constraint being used.

## 9. DO NOTHING Can Still Mask Requests with Different Payloads

Suppose the first call is:

~~~sql
INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-002', 120.00, 'VND')
ON CONFLICT (tenant_id, client_order_code) DO NOTHING;
~~~

Next, the client sends the **same order code but a different amount**:

~~~sql
INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-002', 999.00, 'VND')
ON CONFLICT (tenant_id, client_order_code) DO NOTHING;
~~~

The second attempt is skipped without **reporting that the request differs from the first one**. This can be dangerous if the application mistakenly assumes 999.00 was saved or reports success using the new payload.

Therefore, a complete idempotency mechanism needs to:

1. **Prevent duplicate rows**, typically via `UNIQUE`.
2. **Verify repeated requests have the same content**, using canonical data or a fingerprint.
3. **Reject key reuse with a different payload**, typically as a business conflict error (such as HTTP 409 per the API contract).
4. **Return the first attempt's true result**, never fabricating a new result from a request with different content.

**Preventing duplicate rows does not automatically verify request equivalence.**

## 10. DO UPDATE: Upsert Can Be Useful When Semantically Appropriate

`ON CONFLICT DO UPDATE` lets you update an existing row:

~~~sql
INSERT INTO retry_lab.inventory (product_id, quantity)
VALUES (501, 20)
ON CONFLICT (product_id)
DO UPDATE
SET quantity = EXCLUDED.quantity
RETURNING product_id, quantity;
~~~

With this pattern, even if run twice, the final value for product 501 is **20**. However, in the lab, if you test on the seeded value 8, wrap the statement in `BEGIN ... ROLLBACK` so it does not affect later exercises.

`EXCLUDED` represents the candidate row proposed for `INSERT` that hit a conflict; values like `EXCLUDED.quantity` are **the values from the `INSERT` request**.

### Trap: Addition Inside DO UPDATE Is Not Idempotent

~~~sql
-- Unsafe if this request can be retried.
INSERT INTO retry_lab.inventory (product_id, quantity)
VALUES (501, 3)
ON CONFLICT (product_id)
DO UPDATE
SET quantity = retry_lab.inventory.quantity + EXCLUDED.quantity;
~~~

If product 501 already exists, each call **adds 3 more**. Retries turn into +6, +9, +12... instead of guaranteeing "one stock intake."

Similarly:

~~~sql
ON CONFLICT (account_id)
DO UPDATE
SET points = accounts.points + EXCLUDED.points
~~~

cannot prevent duplicate additions on a point-grant operation. To guarantee one addition per request, you need a ledger/movement table with a unique operation key and a transaction governing the balance change.

## 11. Avoid No-Op UPDATEs When Using Upsert

Some applications use `DO UPDATE` just so they can `RETURNING` the existing row:

~~~sql
-- Not recommended as a default idempotency trick.
INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-003', 100.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO UPDATE
SET client_order_code = EXCLUDED.client_order_code
RETURNING order_id;
~~~

It can return the existing row's `order_id`, but the `UPDATE` branch can still:

- Create a new row version and WAL records.
- Fire `UPDATE` triggers, audits, or versioning logic.
- Increase lock contention.
- Hide a payload whose amount differs from the existing row.

Do not treat "assigning a column back to itself" as a completely harmless operation.

For genuine business upserts where updates are allowed, you can update only when values actually differ:

~~~sql
INSERT INTO retry_lab.orders (
    tenant_id, client_order_code, amount, currency
)
VALUES (10, 'WEB-003', 100.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO UPDATE
SET
    amount = EXCLUDED.amount,
    currency = EXCLUDED.currency
WHERE
    retry_lab.orders.amount IS DISTINCT FROM EXCLUDED.amount
    OR retry_lab.orders.currency IS DISTINCT FROM EXCLUDED.currency
RETURNING order_id, amount, currency;
~~~

**However:** this example carries the semantics of **allowing edits to an existing order**. For a **create-once** endpoint, retrying with a different amount must be **rejected**, not silently used to modify the order. A `WHERE` clause in `DO UPDATE` is not by itself an original-request verification mechanism for idempotency.

## 12. What Does RETURNING After ON CONFLICT Mean?

| Scenario | Statement | `RETURNING` output |
| --- | --- | --- |
| New row inserted | `INSERT ... RETURNING` | The new row |
| Conflict and `DO NOTHING` | `INSERT ... ON CONFLICT DO NOTHING RETURNING` | **0 rows** |
| Conflict and `DO UPDATE` executes | `INSERT ... ON CONFLICT DO UPDATE RETURNING` | The row after `UPDATE` |
| Conflict and `DO UPDATE`'s `WHERE` is false | `INSERT ... DO UPDATE ... WHERE ... RETURNING` | **0 rows** |
| Another `UNIQUE` conflict not handled by `ON CONFLICT` | `INSERT`/`UPSERT` statement | May raise `23505` |

Therefore, **0 rows does not mean a database error**. It can mean "request already exists," "no `UPDATE` needed," or "`WHERE` condition not met." The application should look up the stored record and verify the payload to determine the business response.

## 13. Concurrency Rules of Unique Indexes

A unique index does not check only committed data as of the start of the statement. When two sessions try to insert the same key simultaneously, PostgreSQL coordinates conflicts against uncommitted transactions.

Example:

~~~text
Session A                            Session B
---------------------------------    ------------------------------
BEGIN;
INSERT key=(10, WEB-004);            BEGIN;
                                     INSERT key=(10, WEB-004)
                                     -- may wait for A
COMMIT;
                                     -- ON CONFLICT DO NOTHING: 0 rows
                                     COMMIT;
~~~

If A rolls back instead of committing, B can proceed to insert that key. If A commits, B will not insert another row with the same key.

This is why **`UNIQUE` + `ON CONFLICT`** is far stronger than calling `SELECT` to check beforehand: uniqueness is enforced under concurrent writes, not just sequential execution.

### A Subtlety with Snapshots in READ COMMITTED

At the `READ COMMITTED` isolation level, `INSERT ... ON CONFLICT DO NOTHING` can decide **not to insert because another transaction already inserted and committed**, even though that row **is not visible to the snapshot of a `SELECT` part inside the same statement**.

Consequently, a pattern that tries to combine `INSERT` with "if not inserted, `SELECT` the existing row" inside one statement using `UNION ALL` can **return 0 rows during a rare race**.

If you need the existing result after `DO NOTHING RETURNING` yields 0 rows, a clear, reliable approach is:

1. Finish the `INSERT` statement.
2. Run **a new `SELECT` statement** under `READ COMMITTED` to read the committed row.
3. Compare the payload, then return the result or a conflict error.
4. If you are running under a stricter isolation level or hit a serialization failure, retry the transaction per your policy.

Do not assume "one CTE will always see the winning record" in every concurrency scenario.

## 14. Why Must Unique Keys Usually Be NOT NULL?

In PostgreSQL, a traditional unique constraint allows **multiple `NULL` values** in one or more key columns, because by default `NULL`s are treated as distinct for uniqueness purposes.

Illustrative example:

~~~sql
CREATE TABLE retry_lab.null_unique_demo (
    demo_id integer PRIMARY KEY,
    external_reference text UNIQUE
);

INSERT INTO retry_lab.null_unique_demo
    (demo_id, external_reference)
VALUES
    (1, NULL),
    (2, NULL);
~~~

Both rows with `external_reference NULL` are accepted under the default unique constraint. If an application uses `NULL` as the idempotency key when the client omits one, uniqueness will **fail to prevent duplicates as expected**.

For idempotency keys, declare:

~~~sql
idempotency_key text NOT NULL
~~~

and validate that the value is non-blank.

### NULLS NOT DISTINCT Starting in PostgreSQL 15

PostgreSQL **15 and later** supports unique constraints/indexes with `NULLS NOT DISTINCT`, which treats `NULL`s as non-distinct for uniqueness:

~~~sql
-- PostgreSQL 15+
CREATE TABLE retry_lab.one_nullable_reference (
    reference_code text UNIQUE NULLS NOT DISTINCT
);
~~~

With that, at most one row can have `reference_code IS NULL` under this constraint.

This feature is useful for certain nullable business keys, but it is **not a good reason to allow missing idempotency keys**. For operations that require safe retries, require an explicit key value from the client/producer.

## 15. Not Every Uniqueness Rule Has the Same Contract

PostgreSQL offers:

- `PRIMARY KEY`: unique and `NOT NULL` on the key columns.
- `UNIQUE`: prevents duplicates on a column or group of columns.
- Unique index: can enforce uniqueness on expressions, partial predicates, and advanced options.
- `UNIQUE NULLS NOT DISTINCT`: supports alternative `NULL` equality starting in version 15.

For example, if an application's rules specify case-insensitive emails:

~~~sql
CREATE TABLE retry_lab.accounts (
    account_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL
);

CREATE UNIQUE INDEX uq_accounts_email_lower
ON retry_lab.accounts (lower(email));
~~~

A unique index on `lower(email)` protects a normalized key form. However, it does **not** imply that every email address in the world should be folded with `lower()`; identity rules and collation must come from business requirements.

For idempotency keys, be consistent about case sensitivity. If keys are defined as byte/case-sensitive, do not arbitrarily normalize with `lower()` without a clear API contract.

## 16. ON CONFLICT Does Not Catch Every Write Error

`ON CONFLICT` is designed for unique/exclusion constraint conflicts along its supported clauses—it **does not mean "ignore any error during INSERT"**.

Errors that can still occur include:

- `NOT NULL` or `CHECK` violations.
- Foreign key violations.
- Uniqueness violations on a different, unhandled constraint.
- Missing `INSERT`/`UPDATE`/`SELECT` privileges.
- Deadlocks or serialization failures.
- Errors raised by triggers or expressions.
- Values that cannot be cast to the column type.

For `DO UPDATE`, PostgreSQL requires a matching conflict target; arbiter inference must satisfy unique index/constraint rules. **Deferrable unique constraints cannot be used as the arbiter for `ON CONFLICT DO UPDATE`** under PostgreSQL's rules. Advanced uniqueness setups (partial unique indexes, exclusion constraints, partitioned tables) have specific rules—consult the documentation for your server version.

### A Batch INSERT That Conflicts with Itself

~~~sql
-- Example to avoid: same business key twice in VALUES.
INSERT INTO retry_lab.orders
    (tenant_id, client_order_code, amount, currency)
VALUES
    (10, 'WEB-X', 100.00, 'VND'),
    (10, 'WEB-X', 100.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO UPDATE SET amount = EXCLUDED.amount;
~~~

A single `ON CONFLICT DO UPDATE` statement cannot affect **the same target row more than once**, so it can raise a cardinality violation (`21000`). Before running a bulk upsert, deduplicate the source data by key and define which record wins when duplicates differ.

## 17. Storing a Fingerprint or Payload to Recognize True Retries

An idempotency key must be bound to **normalized request content**. If the same key arrives once with amount 100 and next with 900, it must not be treated as a valid retry of the same request.

Two storage approaches:

1. **Canonical payload**: store a `jsonb` object or the business fields that define request equivalence.
2. **Fingerprint/hash**: compute a hash from a canonical representation of the request; compare hashes while choosing a sound algorithm, normalization strategy, and collision handling.

In the lab, `idempotency_requests.request_payload jsonb` stores a JSONB object containing:

~~~json
{
  "client_order_code": "WEB-100",
  "amount": 120.00,
  "currency": "VND"
}
~~~

On retry, the server builds the same structure and compares it against the stored value using `IS DISTINCT FROM` or an appropriate equality operator.

### Why Is Normalization Needed?

Two requests can be identical in business meaning while differing in raw representation:

~~~text
currency: "vnd" vs "VND"
amount: 120 vs 120.00
key order: {"amount":120,"currency":"VND"}
           vs {"currency":"VND","amount":120}
~~~

If the API considers them equivalent, the system must define normalization **before comparison**. PostgreSQL `jsonb` normalizes object key ordering and representation differently from raw JSON text; however, all business concerns (currency codes, Unicode normalization, default fields, sensitive fields) still need explicit rules.

**Never store raw payment card numbers, access tokens, or sensitive personal data in the request table just for retry comparison.** Store only the minimal permissible business fields or a secure fingerprint following your security policy.

## 18. Store the Outcome, Not Just a "Key Seen" Marker

Suppose you only have a table like:

~~~text
idempotency_key | created_at
--------------------------------
req-A           | ...
~~~

On retry, the server knows the key appeared before, but **does not know which order was created**, what response to return, or whether the first request even finished.

In the lab, `idempotency_requests` stores:

- `tenant_id`, `operation`, `idempotency_key`: request identity.
- `request_payload`: normalized payload to detect improper key reuse.
- `state`: processing or completed.
- `order_id`: business outcome.
- `completed_at`: completion timestamp.

For other endpoints, you may also store the HTTP status code, a sanitized response body, a business object ID, or cached error results as specified by your API contract.

**Never assume every retry can simply rerun the `INSERT` and somehow get the old ID back.** The `DO NOTHING` branch returns no rows, so outcome data must be intentionally stored and queried.

## 19. Transaction Workflow with an Idempotency Key

Recommended workflow:

~~~mermaid
flowchart TD
    A["Receive tenant, operation, key, payload"] --> B["Normalize and validate"]
    B --> C["INSERT request key, ON CONFLICT DO NOTHING"]
    C --> D{"Key inserted?"}
    D -->|"Yes"| E["Create orders and outbox"]
    E --> F["Save order_id, state=completed"]
    F --> G["COMMIT and return new result"]
    D -->|"No"| H["Read existing request"]
    H --> I{"Payload matches?"}
    I -->|"No"| J["409 / conflict"]
    I -->|"Yes, completed"| K["Return previous order_id"]
    I -->|"Yes, processing"| L["Wait, poll, or retry per contract"]
~~~

**All creation steps** must execute inside the **same transaction**: claiming the key, creating the order, writing the outbox record, and marking the outcome. Do not commit a `processing` key first and then create the order outside a transaction unless you have an explicit recovery mechanism for partial states.

Independence across concurrent requests must also hold: two clients sending the same key race on the unique constraint, not on an unlocked `SELECT`.

## 20. Creating a Sample create_order_once Function in PostgreSQL

To have an example you can **genuinely call repeatedly**, let us put the transactional workflow inside a `PL/pgSQL` function. Each function call runs inside a single statement; in standard autocommit mode, PostgreSQL commits when the statement succeeds. If called inside an outer transaction, its final persistence depends on that outer transaction's `COMMIT`/`ROLLBACK`.

The function below is database-only; it **does not make HTTP calls or contact external payment systems**.

~~~sql
CREATE OR REPLACE FUNCTION retry_lab.create_order_once(
    p_tenant_id integer,
    p_idempotency_key text,
    p_client_order_code text,
    p_amount numeric,
    p_currency text
)
RETURNS TABLE (
    result_order_id bigint,
    replayed boolean
)
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    v_payload jsonb;
    v_claimed boolean;
    v_created_order_id bigint;
    v_previous_payload jsonb;
    v_previous_order_id bigint;
    v_previous_state text;
    v_currency text;
BEGIN
    -- Validate inputs before writing.
    IF p_tenant_id IS NULL OR p_tenant_id <= 0 THEN
        RAISE EXCEPTION 'Invalid tenant_id';
    END IF;

    IF p_idempotency_key IS NULL
       OR btrim(p_idempotency_key) = '' THEN
        RAISE EXCEPTION 'Missing idempotency key';
    END IF;

    IF p_client_order_code IS NULL
       OR btrim(p_client_order_code) = '' THEN
        RAISE EXCEPTION 'Missing order code';
    END IF;

    IF p_amount IS NULL OR p_amount < 0 THEN
        RAISE EXCEPTION 'Invalid amount';
    END IF;

    v_currency := upper(p_currency);
    IF v_currency IS NULL OR v_currency NOT IN ('VND', 'USD') THEN
        RAISE EXCEPTION 'Invalid currency';
    END IF;

    -- Canonical payload for the create_order endpoint.
    v_payload := jsonb_build_object(
        'client_order_code', p_client_order_code,
        'amount', p_amount,
        'currency', v_currency
    );

    -- Compete for request ownership using the PRIMARY KEY.
    v_claimed := false;

    INSERT INTO retry_lab.idempotency_requests (
        tenant_id,
        operation,
        idempotency_key,
        request_payload
    )
    VALUES (
        p_tenant_id,
        'create_order',
        p_idempotency_key,
        v_payload
    )
    ON CONFLICT (tenant_id, operation, idempotency_key)
    DO NOTHING
    RETURNING true INTO v_claimed;

    IF v_claimed IS TRUE THEN
        -- New request: create the business object.
        INSERT INTO retry_lab.orders (
            tenant_id,
            client_order_code,
            amount,
            currency
        )
        VALUES (
            p_tenant_id,
            p_client_order_code,
            p_amount,
            v_currency
        )
        RETURNING order_id INTO v_created_order_id;

        -- Record the outbox event in the same statement/transaction.
        INSERT INTO retry_lab.outbox_events (
            tenant_id,
            order_id,
            event_type,
            payload
        )
        VALUES (
            p_tenant_id,
            v_created_order_id,
            'order.created',
            jsonb_build_object(
                'order_id', v_created_order_id,
                'client_order_code', p_client_order_code,
                'amount', p_amount,
                'currency', v_currency
            )
        );

        -- Complete the request only after order/outbox creation succeeds.
        UPDATE retry_lab.idempotency_requests AS r
        SET
            state = 'completed',
            order_id = v_created_order_id,
            completed_at = now()
        WHERE r.tenant_id = p_tenant_id
          AND r.operation = 'create_order'
          AND r.idempotency_key = p_idempotency_key;

        RETURN QUERY
        SELECT v_created_order_id, false;
        RETURN;
    END IF;

    -- Key already exists: read the outcome from the winning transaction.
    SELECT
        r.request_payload,
        r.order_id,
        r.state
    INTO
        v_previous_payload,
        v_previous_order_id,
        v_previous_state
    FROM retry_lab.idempotency_requests AS r
    WHERE r.tenant_id = p_tenant_id
      AND r.operation = 'create_order'
      AND r.idempotency_key = p_idempotency_key
    FOR UPDATE;

    IF NOT FOUND THEN
        -- Under standard READ COMMITTED,
        -- this is not expected after a claim conflict.
        RAISE EXCEPTION 'Request result not visible; retry transaction';
    END IF;

    IF v_previous_payload IS DISTINCT FROM v_payload THEN
        RAISE EXCEPTION
            'Idempotency key reused with different payload';
    END IF;

    IF v_previous_state <> 'completed'
       OR v_previous_order_id IS NULL THEN
        RAISE EXCEPTION
            'Request has no completed result';
    END IF;

    RETURN QUERY
    SELECT v_previous_order_id, true;
END;
$$;
~~~

### Key Highlights of the Function

- `v_payload` is built from normalized business fields per the sample contract.
- `INSERT ... ON CONFLICT DO NOTHING RETURNING true` determines which session **claims ownership of the key**.
- The winning branch creates `orders`, writes `outbox_events`, and updates `idempotency_requests` via **sequential statements within the same function call**.
- If inserting into `orders` or `outbox_events` fails, the calling statement fails and no partial database changes are committed.
- The losing branch reads the existing request and compares payloads before returning the previous outcome.
- `FOR UPDATE` locks the fetched request row within the transaction to inspect state cleanly; it is not a substitute for the unique key during the claim step.
- `VOLATILE` is the proper declaration because the function performs `INSERT` and `UPDATE` operations.

**Scope of this example:** this design is tailored for learning, not a complete production API package. A production system also needs auth/tenant checks, response status/body storage, timeout policies, error-state caching, key expiration, SQLSTATE retry handling, and monitoring for stuck `processing` rows.

## 21. Practice: Calling with the Same Key Twice

Run inside a lab transaction and roll back:

~~~sql
BEGIN;

SELECT *
FROM retry_lab.create_order_once(
    10, 'req-A', 'WEB-100', 120.00, 'VND'
);

SELECT *
FROM retry_lab.create_order_once(
    10, 'req-A', 'WEB-100', 120.00, 'VND'
);

SELECT
    tenant_id,
    client_order_code,
    order_id,
    amount
FROM retry_lab.orders
WHERE tenant_id = 10
  AND client_order_code = 'WEB-100';

SELECT
    event_id,
    order_id,
    event_type
FROM retry_lab.outbox_events
WHERE tenant_id = 10;

SELECT
    idempotency_key,
    state,
    order_id
FROM retry_lab.idempotency_requests
WHERE tenant_id = 10
  AND operation = 'create_order';

ROLLBACK;
~~~

Expected result inside the transaction:

- First call: returns `result_order_id = N`, `replayed = false`.
- Second call: returns **the same `N`**, `replayed = true`.
- There is exactly **one `orders` row** with code `WEB-100`.
- There is exactly **one `order.created` event** for that order.
- The idempotency table has **one key `req-A`** in state `completed`.

The exact number `N` is not fixed because the identity sequence may have advanced earlier. `ROLLBACK` restores table rows to the initial lab state, but **does not guarantee the sequence resets to an earlier number**.

### Do Not Confuse Same Key with Same Order Code

If you pass a **new key** while reusing `client_order_code = 'WEB-100'`, the unique business key blocks creating a second order in the same tenant. That unique violation is a signal the application must handle by policy—checking whether this is a genuine duplicate creation or a client using the wrong key—rather than automatically turning it into an `UPDATE` of the amount.

## 22. What If the Same Key Has a Different Payload?

Test the error scenario in the lab across **two separate transactions** so each can be cleanly committed or rolled back:

~~~sql
BEGIN;

SELECT *
FROM retry_lab.create_order_once(
    10, 'req-B', 'WEB-200', 100.00, 'VND'
);

COMMIT;
~~~

Then call again with the same key but a different amount:

~~~sql
-- Business error expected.
SELECT *
FROM retry_lab.create_order_once(
    10, 'req-B', 'WEB-200', 900.00, 'VND'
);
~~~

The function rejects reusing the key with a different payload. In an API, you can map this to a conflict response (such as HTTP 409), making sure the response body does not leak another user's original request data.

**Practice note:** this example uses `COMMIT`, so it persists new rows in the lab schema. When you want a clean dataset, run tests on a freshly reset lab database or use a `SAVEPOINT` and handle the error inside a test transaction. Never run an intentionally failing statement and keep using the same transaction without rolling back.

### Why Not Accept the New Amount Automatically?

An idempotency key represents **one unique logical request**. If the same key arrives with a different payload, the system cannot conclude "this is a retry of the previous request"; silently overwriting the amount could cause billing bugs or fraud.

## 23. Testing with Two Concurrent Sessions

Open **two PostgreSQL sessions** connected to the same lab database. Use a fresh key that has never been used.

**Session A:**

~~~sql
BEGIN;

SELECT *
FROM retry_lab.create_order_once(
    10, 'req-concurrent', 'WEB-300', 300.00, 'VND'
);

-- Do not COMMIT yet; keep the transaction open to observe Session B.
~~~

**Session B (run while A is still open):**

~~~sql
BEGIN;

SELECT *
FROM retry_lab.create_order_once(
    10, 'req-concurrent', 'WEB-300', 300.00, 'VND'
);

-- The call may wait on A's unique conflict.
~~~

Switch back to A:

~~~sql
COMMIT;
~~~

Once A commits, B can proceed and return the saved result with `replayed = true`. Then in B:

~~~sql
COMMIT;
~~~

Verify:

~~~sql
SELECT COUNT(*) AS orders_count
FROM retry_lab.orders
WHERE tenant_id = 10
  AND client_order_code = 'WEB-300';
~~~

The expected result is **1**.

If A rolls back instead of committing, B can win the `INSERT` on the key and create the order as a fresh request. This demonstrates how uniqueness coordinates with uncommitted transaction state.

**Test assumptions:** these examples assume PostgreSQL's default `READ COMMITTED` isolation, the function running in an ordinary transaction, and no other worker modifying the same rows. Under `REPEATABLE READ`/`SERIALIZABLE`, you may need to retry the entire transaction on concurrency errors; do not assume a replay can always be served immediately inside an older snapshot.

## 24. Do Not Create a "processing" Key and Commit It Separately Without Recovery Logic

An anti-pattern:

~~~text
Transaction 1: INSERT request_key(state='processing') → COMMIT
Transaction 2: create order → COMMIT
Transaction 3: UPDATE request_key(state='completed') → COMMIT
~~~

If the application crashes between transactions, the key is already claimed but has no completed outcome. Subsequent retries may stay stuck forever in `processing` or duplicate side effects in an ad-hoc recovery path.

There are two intentional designs:

1. **Keep all short database operations in one transaction**, like `create_order_once`: when it commits, the key, order, and outbox complete together.
2. **A long workflow/saga with a committed `processing` state**, which requires leases/timeouts, owner tokens, recovery logic, contention locks, failure states, and an explicit retry state machine.

Do not pick model (2) just because it feels easier to split into multiple DB calls; it demands significantly more rules and safeguards.

## 25. Transactional Outbox and Duplicate Events

An order might be created only once in PostgreSQL while the application still emits **two events** if message publishing sits outside the transaction and the entire endpoint is retried.

Unsafe example:

~~~text
INSERT orders → COMMIT
Publish order.created → broker
Response timeout → retry
Publish order.created a second time
~~~

Safer database pattern:

~~~text
BEGIN
  Claim idempotency key
  INSERT orders
  INSERT outbox_events
  Mark request completed
COMMIT

Separate worker reads committed outbox rows and publishes
~~~

In the lab, `outbox_events` also defines:

~~~sql
UNIQUE (tenant_id, order_id, event_type)
~~~

This constraint prevents two outbox rows of the same event type for one order, but **does not by itself guarantee the broker receives it exactly once**. A worker can publish successfully and crash before recording `published_at`; upon recovery, it may publish again.

Therefore, consumers still need **deduplication/idempotency by `event_id` or business event key**, alongside retry policies and observability. A PostgreSQL transaction alone cannot guarantee end-to-end exactly-once delivery across external services.

## 26. Deducting Inventory Is a Non-Idempotent Operation

The `inventory` table has:

~~~sql
SELECT product_id, quantity
FROM retry_lab.inventory
ORDER BY product_id;
~~~

Seeded state: product 501 has 8; product 502 has 0.

Deducting 3 units:

~~~sql
UPDATE retry_lab.inventory
SET quantity = quantity - 3
WHERE product_id = 501
  AND quantity >= 3
RETURNING product_id, quantity;
~~~

**If this request is retried after committing**, the `UPDATE` can deduct another 3 units. The condition `quantity >= 3` prevents negative stock, but **does not prevent double deduction** while stock remains sufficient.

Likewise, placing `ON CONFLICT DO NOTHING` only on the movement log **after already deducting stock** is too late: the movement row will not duplicate, yet stock has already been reduced again.

### Bad Pattern to Avoid

~~~text
UPDATE inventory SET quantity = quantity - 3;
INSERT inventory_movements(key, delta=-3)
  ON CONFLICT DO NOTHING;
~~~

On retry, the `UPDATE` still deducts, even though the movement `INSERT` is ignored.

**Operation ownership must be claimed before applying any non-idempotent effect**, and all related actions must commit atomically.

## 27. The deduct_stock_once Function: Preventing Double Stock Deduction

The `stock_deductions` table has `PRIMARY KEY(product_id, operation_key)`. We claim this key before decrementing inventory, then store the remaining quantity.

~~~sql
CREATE OR REPLACE FUNCTION retry_lab.deduct_stock_once(
    p_product_id integer,
    p_operation_key text,
    p_quantity integer
)
RETURNS TABLE (
    quantity_remaining integer,
    replayed boolean
)
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    v_claimed boolean;
    v_remaining integer;
    v_previous_quantity integer;
    v_previous_remaining integer;
BEGIN
    IF p_product_id IS NULL THEN
        RAISE EXCEPTION 'Missing product_id';
    END IF;

    IF p_operation_key IS NULL
       OR btrim(p_operation_key) = '' THEN
        RAISE EXCEPTION 'Missing operation key';
    END IF;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION 'Quantity must be positive';
    END IF;

    v_claimed := false;

    INSERT INTO retry_lab.stock_deductions (
        product_id,
        operation_key,
        deduct_quantity
    )
    VALUES (
        p_product_id,
        p_operation_key,
        p_quantity
    )
    ON CONFLICT (product_id, operation_key)
    DO NOTHING
    RETURNING true INTO v_claimed;

    IF v_claimed IS TRUE THEN
        -- Only a new request may decrement inventory.
        UPDATE retry_lab.inventory AS i
        SET quantity = i.quantity - p_quantity
        WHERE i.product_id = p_product_id
          AND i.quantity >= p_quantity
        RETURNING i.quantity INTO v_remaining;

        IF NOT FOUND THEN
            -- Not enough stock: roll back both claim and UPDATE.
            RAISE EXCEPTION 'Insufficient or missing stock';
        END IF;

        UPDATE retry_lab.stock_deductions AS d
        SET remaining_quantity = v_remaining
        WHERE d.product_id = p_product_id
          AND d.operation_key = p_operation_key;

        RETURN QUERY SELECT v_remaining, false;
        RETURN;
    END IF;

    -- Retry: read the previously committed effect.
    SELECT
        d.deduct_quantity,
        d.remaining_quantity
    INTO
        v_previous_quantity,
        v_previous_remaining
    FROM retry_lab.stock_deductions AS d
    WHERE d.product_id = p_product_id
      AND d.operation_key = p_operation_key
    FOR UPDATE;

    IF NOT FOUND OR v_previous_remaining IS NULL THEN
        RAISE EXCEPTION 'Operation has no completed result';
    END IF;

    IF v_previous_quantity <> p_quantity THEN
        RAISE EXCEPTION
            'Operation key reused with different quantity';
    END IF;

    RETURN QUERY SELECT v_previous_remaining, true;
END;
$$;
~~~

### Practice

~~~sql
BEGIN;

SELECT *
FROM retry_lab.deduct_stock_once(
    501, 'deduct-01', 3
);

SELECT *
FROM retry_lab.deduct_stock_once(
    501, 'deduct-01', 3
);

SELECT product_id, quantity
FROM retry_lab.inventory
WHERE product_id = 501;

SELECT product_id, operation_key,
       deduct_quantity, remaining_quantity
FROM retry_lab.stock_deductions
WHERE product_id = 501;

ROLLBACK;
~~~

Inside the transaction:

- First call: `quantity_remaining = 5`, `replayed = false`.
- Second call: `quantity_remaining = 5`, `replayed = true`.
- Stock drops only **from 8 to 5**, not down to 2.
- `stock_deductions` holds one row for `deduct-01`.
- After rollback, stock is back to 8 and the deduction row is undone.

### Business Limitations of the Example

The function records **successful outcomes**. When stock is insufficient, it raises an exception and the claim rolls back, so a retry after restocking can succeed. If your API contract requires **the same key to always return the exact initial failure**, you must persist error outcomes atomically and define which errors are cached versus retried.

Also, `quantity_remaining` is **the stock level right after the first deduction**, not the live current stock when the request is replayed. This intentionally replays the original operation result. To return current stock, perform a separate query with a field name that reflects its true semantics.

## 28. Error Behavior During Retries

A client usually needs to distinguish:

| Case | Recommended handling |
| --- | --- |
| Duplicate key, same payload and completed | Return the saved result |
| Duplicate key, different payload | Return conflict; do not re-execute |
| Key does not exist yet | Process as a new request |
| `processing` record in a long workflow | Wait / poll state / apply timeout per state machine |
| SQLSTATE `23505` from another business unique key | Inspect the specific constraint; do not blindly treat as a replay |
| SQLSTATE `40001` (`serialization_failure`) | Safe to retry the **entire transaction** if workflow is retry-safe |
| SQLSTATE `40P01` (`deadlock_detected`) | Controlled transaction retry |
| Network error after `COMMIT` with unknown outcome | Resend with the **same idempotency key** and look up outcome |
| Deterministic input validation error | Return appropriate error; cache or not depending on contract |

Never lump every PostgreSQL error into an infinite retry loop. A `23505` error might mean "that order code already belongs to another request," not a transient glitch; retrying forever will never fix it.

For retryable concurrency errors, enforce a maximum retry count, backoff/jitter, logging, and verified transaction idempotency before looping.

## 29. Transaction Isolation and Whole-Transaction Retries

`READ COMMITTED` is PostgreSQL's default isolation level. Each statement typically receives a snapshot as of the start of that statement, and PostgreSQL handles concurrent updates accordingly.

Under `REPEATABLE READ` or `SERIALIZABLE`, a transaction can fail with a **serialization failure** when concurrent changes cannot be applied consistently. In that case, the application must replay the **entire read–decide–write logic of the transaction**, not just the last failing statement.

In an idempotency-key workflow:

1. Keep the **same idempotency key** across retries of the same logical request.
2. Keep all database side effects within the same transaction.
3. If the transaction rolls back, treat it as having committed no new effect.
4. If commit status is uncertain, **look up the key** in a fresh statement/transaction before assuming you need a new operation.
5. Only retry with backoff and bounded attempts; never generate a fresh `now()`, UUID, or random token as a **new idempotency key** on each retry of the same request.

### Do Not Infer Business State from SQLSTATE Alone

For instance, an `INSERT` can fail with a unique violation on `(tenant_id, client_order_code)` caused by **a different request**. Never return "order already created by this request" just because SQLSTATE is `23505`; identify the failing constraint, verify the payload, and check ownership.

## 30. Integrating with JDBC / Java

In Java, the client should generate the key **once per logical operation** and reuse it across retries. Use `PreparedStatement` to bind values—never interpolate user strings into SQL.

Example function call:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public record CreateOrderResult(long orderId, boolean replayed) {}

public static CreateOrderResult createOrderOnce(
        Connection connection,
        int tenantId,
        String idempotencyKey,
        String clientOrderCode,
        BigDecimal amount,
        String currency
) throws SQLException {

    String sql = """
        SELECT result_order_id, replayed
        FROM retry_lab.create_order_once(?, ?, ?, ?, ?)
        """;

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setInt(1, tenantId);
        ps.setString(2, idempotencyKey);
        ps.setString(3, clientOrderCode);
        ps.setBigDecimal(4, amount);
        ps.setString(5, currency);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException("No result from create_order_once");
            }

            return new CreateOrderResult(
                rs.getLong("result_order_id"),
                rs.getBoolean("replayed")
            );
        }
    }
}
~~~

This is a repository-layer example only; it omits authentication, authorization, HTTP mapping, transaction boundaries, and retry policies. If the connection is participating in a service-managed transaction, the method must not commit or roll back on its own.

### Generating the Idempotency Key at the Right Time

~~~java
// Generate ONCE when starting a new logical request:
String key = java.util.UUID.randomUUID().toString();

// Keep the same key across retries; never generate a new UUID per attempt:
CreateOrderResult result = createOrderOnce(
    connection,
    tenantId,
    key,
    orderCode,
    amount,
    "VND"
);
~~~

If the application needs to retry across process restarts, the key must be persisted in an appropriate place, such as the client request context or a durable job record. A UUID kept only in RAM is lost on restart and cannot identify the same request afterward.

### Classifying Errors

In JDBC, SQLSTATE can be read via:

~~~java
try {
    // Execute the SQL statement.
} catch (SQLException e) {
    String sqlState = e.getSQLState();

    if ("40001".equals(sqlState) || "40P01".equals(sqlState)) {
        // Retry the ENTIRE TRANSACTION under an appropriate retry policy.
    } else if ("23505".equals(sqlState)) {
        // Unique conflict: inspect the constraint and business key.
    } else {
        // Handle other errors per classification.
    }
    throw e;
}
~~~

The snippet above only illustrates error classification; do not embed an unbounded retry loop inside a repository method. Certain errors place the transaction into an aborted state, requiring a rollback before starting a new transaction.

## 31. What Should an HTTP API Return on Replay?

An API contract might specify:

| Scenario | Illustrative response |
| --- | --- |
| New request succeeds | `201 Created` + `order_id` |
| Retry with same key/payload after success | `200 OK` or replay original `201`, same `order_id` |
| Same key with different payload | `409 Conflict` |
| Request still processing in a long workflow | `202 Accepted` or `409/425` per design |
| Insufficient stock | Appropriate business error code |
| Timeout with uncertain commit | Client retries with same key |

There is no single mandatory HTTP status code across all systems. What matters is a **clear, consistent contract** and server-side idempotency enforcement.

If an identical response is required, the request table must also store the data needed to replay it, such as `http_status` and a sanitized JSON response body. If you only store the business ID, the server can reconstruct a response from current data, though fields may change over time; define the intended semantics explicitly.

## 32. Securing Idempotency Keys and Payloads

An idempotency key is a coordination token, not proof on its own that the caller is authorized to read an order.

Core principles:

- Bind keys to the authenticated **tenant/user/operation**.
- Never let user A read user B's result simply by knowing the key.
- Enforce maximum length, rate limits, and key quotas to prevent storage abuse.
- Do not log raw payloads containing payment details or sensitive PII.
- Store only minimal payloads or fingerprints in line with security policy.
- Do not rely on predictable timestamps or sequential numbers as a security boundary.
- Apply least-privilege database permissions; consider RLS or exposing controlled functions/APIs.
- For `SECURITY DEFINER` functions, pin `search_path` and manage privileges carefully; never elevate privileges merely "to make the function work."

Idempotency never replaces authorization. An unauthorized request must be rejected even if it carries a valid-looking key.

## 33. Retention, TTL, and Key Cleanup Policies

The idempotency table grows with request volume. Define a retention policy:

- Retain keys longer than the **maximum retry window** of clients, queues, or message brokers.
- Decide whether expired keys may ever be reused.
- Deleting idempotency keys too early turns a very late retry into a brand-new request.
- Business-key uniqueness can still block duplicate entities for some tables, but it will not protect every kind of side effect.
- For financial or fulfillment workflows, retention may need to be much longer than for ordinary API requests.
- Plan archiving/partitioning/purging alongside monitoring metrics.

Query to inspect aged keys:

~~~sql
SELECT
    tenant_id,
    operation,
    idempotency_key,
    completed_at
FROM retry_lab.idempotency_requests
WHERE state = 'completed'
  AND completed_at < now() - interval '30 days'
ORDER BY completed_at;
~~~

This query is **for inspection only**. Never run a blind 30-day `DELETE` in production, because retry windows, storage needs, and compliance requirements vary.

## 34. Observability and Testing Duplicate Prevention

An idempotent system needs metrics not just on successful requests, but also on **retries** and **mismatches**:

| Metric | Meaning |
| --- | --- |
| New operations | Count of new keys claimed and completed |
| Replayed operations | Retries matching key/payload that returned the stored result |
| Payload conflicts | Attempts to reuse a key with different data |
| Unique violations by constraint | Business or secondary key conflicts |
| Processing age | Keys remaining incomplete for too long |
| Serialization/deadlock retry | Transaction contention level |
| Outbox backlog | Events committed but not yet published |
| Duplicate consumer event | Duplicate events caught by consumers |

Test scenarios should cover:

1. Same key, same payload called twice sequentially.
2. Same key, same payload called concurrently in two sessions.
3. Same key, different payload.
4. Different keys, same business code.
5. Different tenants, same key.
6. Client times out after commit and retries.
7. Client disconnects before commit and the transaction rolls back.
8. Outbox worker publishes successfully but crashes before marking published.
9. Concurrent stock deductions on the same product with different operation keys.
10. Retry after insufficient stock or after key expiration.
11. Serialization failure/deadlock triggers a full-transaction retry.
12. Triggers/audit checks confirm operations do not run multiple times unexpectedly.

**Do not test only two sequential requests.** Race conditions usually surface only when multiple connections handle the same key before the first transaction commits.

## 35. Common Mistakes

### 35.1. Trusting the Frontend Not to Send Duplicates

Gateways, networks, and workers can retry independently of user behavior. Protect at the server and database layers.

### 35.2. Using SELECT-Before-INSERT Alone

Two transactions can both observe "does not exist yet." Use a unique constraint.

### 35.3. Generating a New Idempotency Key on Every Retry

Every attempt then looks like a brand-new request. Keep the logical operation's key constant.

### 35.4. Using DO NOTHING to Mask Different Payloads

Reusing a key with a different amount must not count as the same request. Compare payloads or fingerprints.

### 35.5. Abusing DO UPDATE SET col = col Just for RETURNING

This can fire triggers, write WAL, acquire extra locks, and hide payload mismatches. Use a dedicated lookup when appropriate.

### 35.6. Using DO UPDATE SET quantity = quantity + delta

Every retry adds/subtracts again. Claim the operation first inside an atomic transaction.

### 35.7. Omitting Key Scope

Tenant A's key string can collide with or expose tenant B's result if the key is not scoped to the right identity.

### 35.8. Leaving idempotency_key Nullable

Traditional `UNIQUE` allows multiple `NULL`s. Declare `NOT NULL` and validate the key.

### 35.9. Committing a processing Key Before Business Logic

If the worker crashes, the key is stuck with no result. Use an atomic transaction or a recoverable state machine.

### 35.10. Writing an Order Then Publishing Externally Before Commit

You can publish an event for a transaction that later rolls back. Use an outbox and publish after commit.

### 35.11. Assuming an Outbox Automatically Guarantees Exactly-Once Delivery

Workers can still publish duplicates after crashes. Consumers must be idempotent or deduplicate.

### 35.12. Treating Every SQLSTATE 23505 as a Request Replay

The conflict might come from a different business key or another tenant. Inspect the constraint and verify ownership/payload.

### 35.13. Treating 0 Rows from DO NOTHING RETURNING as an SQL Error

It is a normal outcome on the conflict branch. The client/server should look up the previously processed record.

### 35.14. Reading the Existing Row in the Same Statement and Expecting to Always See It

Under `READ COMMITTED`, `ON CONFLICT` can detect conflicts against rows not visible to the same statement's snapshot. Re-query in a new statement when needed.

### 35.15. Expecting a Local Unique Key to Deduplicate External API Calls

A PostgreSQL unique key cannot automatically undo a call already executed at a payment gateway or third-party service. Use partner-side idempotency and reconciliation.

### 35.16. Retrying a Transaction While Changing Request Content

Keeping the key while altering currency, amount, or order code breaks the idempotency contract. Retries of a logical request must carry equivalent data.

### 35.17. Neglecting Retention Management

Purging keys earlier than the retry window turns late retries into fresh operations.

### 35.18. Treating Cached Inventory Output as Live Current Stock

Replaying an operation can return `remaining_quantity` from when it first ran, not current stock right now. Name fields and define API contracts clearly.

## 36. Practice Exercises with Answers

Run the exercises below on the `retry_lab` schema. For data-modifying queries, wrap them in a transaction with `ROLLBACK` unless an exercise specifically observes two committed transactions in the lab database.

### Exercise 1. INSERT the Same Business Code Twice

~~~sql
BEGIN;

INSERT INTO retry_lab.orders
    (tenant_id, client_order_code, amount, currency)
VALUES
    (10, 'EX-01', 10.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO NOTHING
RETURNING order_id;

INSERT INTO retry_lab.orders
    (tenant_id, client_order_code, amount, currency)
VALUES
    (10, 'EX-01', 10.00, 'VND')
ON CONFLICT (tenant_id, client_order_code)
DO NOTHING
RETURNING order_id;

SELECT COUNT(*) AS order_count
FROM retry_lab.orders
WHERE tenant_id = 10 AND client_order_code = 'EX-01';

ROLLBACK;
~~~

**Answer:** The first `INSERT` returns an ID, the second returns 0 rows, and `order_count = 1` inside the transaction.

### Exercise 2. Can Two Tenants Use the Same Order Code?

~~~sql
BEGIN;

INSERT INTO retry_lab.orders
    (tenant_id, client_order_code, amount, currency)
VALUES
    (10, 'EX-02', 10.00, 'VND'),
    (20, 'EX-02', 20.00, 'VND')
RETURNING tenant_id, client_order_code;

ROLLBACK;
~~~

**Answer:** Yes, because the unique key is the **pair** `(tenant_id, client_order_code)`.

### Exercise 3. Same Order Code, Different Amount

**Question:** Why is `ON CONFLICT DO NOTHING` insufficient for complete idempotency?

**Answer:** It avoids inserting a duplicate row, but it fails to detect a different payload. You must compare the request payload/fingerprint and typically report a conflict when a key is misused.

### Exercise 4. Is Adding Stock Inside ON CONFLICT Retry-Safe?

~~~sql
ON CONFLICT (product_id)
DO UPDATE
SET quantity = retry_lab.inventory.quantity + EXCLUDED.quantity
~~~

**Answer:** No. Every retry increments stock again. You need an operation key/ledger and a transaction.

### Exercise 5. Calling create_order_once Twice

~~~sql
BEGIN;

SELECT * FROM retry_lab.create_order_once(
    10, 'EX-REQ-01', 'EX-ORDER-01', 99.00, 'VND'
);

SELECT * FROM retry_lab.create_order_once(
    10, 'EX-REQ-01', 'EX-ORDER-01', 99.00, 'VND'
);

ROLLBACK;
~~~

**Answer:** Both return the same `order_id`; first `replayed=false`, second `replayed=true`.

### Exercise 6. Should the Same Key with a Different Request Create a New Order?

**Answer:** No. Reusing a key with a different payload is a conflict, not a valid retry. The system must reject or handle it per its published policy, without modifying the old order.

### Exercise 7. Why Can UNIQUE Allow Two NULLs?

**Answer:** Under default semantics, PostgreSQL treats `NULL`s as distinct for uniqueness. Make idempotency keys `NOT NULL`; PostgreSQL 15+ provides `NULLS NOT DISTINCT` for other use cases.

### Exercise 8. Deduct Stock Twice with the Same Key

~~~sql
BEGIN;

SELECT * FROM retry_lab.deduct_stock_once(
    501, 'EX-STOCK-01', 3
);

SELECT * FROM retry_lab.deduct_stock_once(
    501, 'EX-STOCK-01', 3
);

SELECT quantity
FROM retry_lab.inventory
WHERE product_id = 501;

ROLLBACK;
~~~

**Answer:** Stock becomes **5**, not 2; the replay returns the saved outcome.

### Exercise 9. What About Deducting Stock with New Keys?

Inside one transaction, run sequentially:

~~~sql
BEGIN;

SELECT * FROM retry_lab.deduct_stock_once(
    501, 'EX-STOCK-A', 3
);

SELECT * FROM retry_lab.deduct_stock_once(
    501, 'EX-STOCK-B', 3
);

SELECT quantity
FROM retry_lab.inventory
WHERE product_id = 501;

ROLLBACK;
~~~

**Answer:** Two different operation keys represent **two distinct valid requests**, reducing stock from 8 to 2.

### Exercise 10. What If Stock Is Insufficient?

~~~sql
SELECT * FROM retry_lab.deduct_stock_once(
    502, 'EX-STOCK-C', 3
);
~~~

**Answer:** The function raises an error because product 502 has stock 0. No successful deduction is committed. To continue in a transaction after an error, roll back first.

### Exercise 11. Which Errors Should Trigger a Whole-Transaction Retry?

**Answer:** `40001` and `40P01` are classic cases needing a **whole-transaction** retry mechanism when the business logic is retry-safe. `23505` must be classified by constraint rather than blindly retried indefinitely.

### Exercise 12. Why Isn't Every 23505 a Request Replay?

**Answer:** The conflict may occur on `uq_orders_tenant_code` because a different request used the same business code with another key. You must inspect the request/business fields and ownership.

### Exercise 13. Lost Response After Commit

**Question:** Should the client generate a new UUID and resend?

**Answer:** No. Resend with the **same idempotency key** so the server returns the original outcome.

### Exercise 14. Does an Outbox Automatically Prevent Duplicate Publishing?

**Answer:** No. An outbox prevents data committing without its event being recorded in the same transaction; a worker can still publish twice after a crash, so consumers need idempotency/deduplication.

### Exercise 15. Choosing Keys Across Two Endpoints

An API has `create_order` and `cancel_order`; a client happens to send the same key string to both.

**Suggested answer:** Include `operation` in the unique key scope if the API contract permits reusing a key across operation types, e.g., `PRIMARY KEY(tenant_id, operation, idempotency_key)`.

### Exercise 16. When Should Idempotency Keys Be Purged?

**Suggested answer:** Only after a period well beyond the client/queue retry window and retention requirements, accounting for key reuse and business-key uniqueness. No single fixed TTL fits every system.

## 37. Production Checklist for Retry-Safe Writes

When building an endpoint or consumer that can be called multiple times:

1. **Define the logical operation** and the scope within which two requests count as identical.
2. **Require an idempotency key** or strong business key; never rely on timestamps or luck.
3. **Normalize payloads** per business rules and define how payload mismatches are detected.
4. **Create a database `UNIQUE`/`PRIMARY KEY`** scoped to tenant/user/operation, with a `NOT NULL` key column.
5. **Handle conflicts with `ON CONFLICT`/transactions**, never relying solely on `SELECT`-before-`INSERT`.
6. **Persist the business result** (ID, state, response) so replays can return it.
7. **Let only the claim winner execute side effects**, and commit the result in the same transaction.
8. **Avoid repeated addition/subtraction** without an operation ledger keyed uniquely.
9. **Use `RETURNING`** to capture the exact created ID and row, never `MAX(id)`.
10. **Handle content mismatches**: same key with different payload must not be silently ignored or used to overwrite existing rows.
11. **Protect under concurrency**: unique indexes, row locks, isolation, and transaction retries where needed.
12. **Pair with an outbox** for post-commit events, and design idempotent consumers.
13. **Classify SQLSTATE errors**: distinguish `23505` from `40001`/`40P01`; never retry all errors blindly.
14. **Manage `processing` states and recovery** if a workflow spans multiple transactions.
15. **Define retention/TTL** matching real retry windows and compliance rules.
16. **Rate-limit abuse and protect privacy** of keys, payloads, and responses.
17. **Test with at least two concurrent sessions** and simulated lost-response-after-commit failures.
18. **Emit structured metrics/logs** for new, replayed, conflicted, pending, and outbox lag counts.

When integrating with payment processors, shipping providers, or external APIs, include **partner-side idempotency and reconciliation** in the design. A PostgreSQL transaction cannot cover actions already executed in an external service outside that transaction.

## 38. PostgreSQL Documentation to Cross-Check

For real deployments, consult the official documentation for your **PostgreSQL major version**:

- [INSERT / ON CONFLICT / RETURNING](https://www.postgresql.org/docs/current/sql-insert.html): syntax and semantics of arbiters, `DO NOTHING`, and `DO UPDATE`.
- [Unique Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-UNIQUE-CONSTRAINTS): unique constraints and `NULLS NOT DISTINCT`.
- [Indexes — Unique Indexes](https://www.postgresql.org/docs/current/indexes-unique.html): enforcing uniqueness.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): behavior of `READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE`.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locks, lock waits, and deadlocks.
- [PL/pgSQL Control Structures](https://www.postgresql.org/docs/current/plpgsql-control-structures.html): branching and returning results in functions.
- [Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): SQLSTATE `23505`, `40001`, and `40P01`.
- [WITH Queries](https://www.postgresql.org/docs/current/queries-with.html): data flow and data-modifying CTEs.

`/current/` points to the latest documentation release. If you run an older server version, open the docs for that exact major version, especially for features like `NULLS NOT DISTINCT`.

## 39. Summary

A **retry-safe** write is more than an `INSERT` with `ON CONFLICT` tacked on. It is a unified contract spanning **client key, request payload, unique constraints, transactions, stored outcomes, and side effects**.

Most important principles:

- **`UNIQUE` is the concurrency barrier against duplicates.** Pre-checking with `SELECT` is not enough.
- **`ON CONFLICT DO NOTHING`** prevents creating two rows with the same key, but **does not verify matching payloads**, and the conflict branch returns no `RETURNING` rows.
- **`ON CONFLICT DO UPDATE`** is an upsert, not automatically idempotent; additions/subtractions in `UPDATE` still repeat effects.
- **Idempotency keys must be scoped and bound to canonical payloads.** Same key with a different payload must be handled as a conflict.
- **Persist the outcome** so retries can return the original business ID/response without executing a new operation.
- **Key claim and side effects must commit atomically** for short database operations; long workflows require an explicit state machine and recovery.
- **A PostgreSQL transaction does not guarantee end-to-end exactly-once across external systems**; pair it with an outbox, idempotent consumers, and partner-side idempotency.
- **Concurrency and isolation are mandatory design concerns**, especially when multiple workers handle the same key concurrently.

Whenever a request can be replayed, ensure **the same logical request produces only one committed business effect**, and every subsequent retry recognizes, verifies, and reuses the saved outcome—instead of repeating a dangerous write.
