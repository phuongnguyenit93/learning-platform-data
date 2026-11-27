# Redesigning Boundaries When Invariants Cannot Be Enforced Safely

A system may already partition data successfully for capacity and latency, yet still **fail to protect business truth**: two shards sell the same last ticket, two services redeem the same voucher, or two regions spend from one shared budget. Every node obeys every local constraint, yet the system-wide outcome is invalid.

In these situations, adding foreign keys, local transactions, retries, or end-of-day audit jobs is sometimes not enough. The real problem is that **data participating in an invariant does not sit inside the same boundary that can be updated consistently**. If an invariant must hold at the moment a command is accepted, the architecture must clearly define **who holds final decision authority**, based on what state, and protected by which transactional mechanism.

This lesson belongs to the **Distribution and Partitioning** chapter of the **DATABASE_DATA_MODELING** module. The focus is on turning business rules into data models, keys, partitions, ownership boundaries, and sound write paths, while analyzing how to compare relational, document, graph, and analytical warehouse stores when scaling or preserving history.

> **Principle:** When an important invariant cannot be enforced at reasonable cost, consider **redesigning owner boundaries, aggregates, shard keys, or commit scopes**, rather than merely detecting corrupt data afterward and patching it later.

## 1. Invariants and commit scopes

An **invariant** is a predicate that must hold at a defined point in a business workflow.

Examples:

- **Inventory:** for a warehouse and SKU, reserved quantity never exceeds sellable on-hand stock.
- **Vouchers:** a voucher can be redeemed at most once within its defined scope.
- **Orders:** an order may be marked CONFIRMED only if required line items exist and are valid.
- **Multi-tenancy:** an Order of tenant A must never reference a Customer belonging to tenant B.
- **Budgets:** total accepted spend never exceeds the approved budget.
- **Money transfers:** a transfer is never considered complete if one required half of the effect still fails.

A statement like “never oversell inventory” is too vague to implement. You must clarify:

1. Is inventory **per SKU and warehouse**, or pooled across the entire network?
2. Does “selling” occur when the user clicks buy, when reservation succeeds, upon payment, or at shipment?
3. Do orders awaiting payment **pre-reserve** stock, and for how long?
4. Are duplicate requests sharing an **operation_id** counted again?
5. Who is authorized to adjust stock and cancel reservations?
6. At what moment must the rule hold: before ACCEPTED, at COMMIT, or post-reconciliation?

A sharper formulation:

> For each `(tenant_id, warehouse_id, sku_id)`, `ReserveStock` may return ACCEPTED only after durably recording the reservation and updating `reserved` within **the same transaction boundary** so that `reserved <= on_hand`; repeating the same `operation_id` produces no additional hold.

Such an invariant enables a clear **inventory aggregate**. Yet it still does not enforce a company-wide stock cap if two warehouses draw from a shared physical pool: that is a **different invariant** with a different scope.

### 1.1. Six questions before choosing a mechanism

| Question | Example details to confirm |
| --- | --- |
| **Scope** | Unique per tenant, warehouse, campaign, or whole enterprise? |
| **Data set** | A single row, an Order and its Lines, or a sum across shards? |
| **Writers** | Only one service, or APIs, batches, admins, and consumers writing concurrently? |
| **Time** | Must hold at COMMIT, or tolerate up to 5 minutes of skew? |
| **Failure** | If a node is lost, may new commands still be accepted? |
| **Proof** | PK/FK/CHECK, atomic UPDATE, transaction, registry, escrow, or reconciliation? |

What matters most is **when success is announced**. If you tell a customer “your ticket is reserved” before the system makes an atomic decision, and later discover an oversell and send an apology email, the invariant “never promise two people the same seat” has already been violated.

## 2. Distinguishing boundaries in distributed models

| Boundary | Nature | Invariant enforcement capability |
| --- | --- | --- |
| **Row** | Single record with columns | CHECK, NOT NULL, atomic UPDATE |
| **Table/relation** | Multiple rows, keys, and FKs | UNIQUE, FK, transactions when DBMS supports them |
| **Business aggregate** | Data sharing an owner to enforce write rules | Enforced if all writers go through the owner and transaction |
| **Partition** | Physical slice of a table via RANGE/HASH/LIST | Not equivalent to an independent database |
| **Shard** | Data split across nodes/DBs that commit independently | Local transactions; cross-shard needs engine support or protocol |
| **Service** | API, ownership, and deployment boundary | No automatic cross-service transactions |
| **Region** | Geographic location of records/replicas/owners | Subject to replication lag, failover, and split-brain |

A PostgreSQL table using **PARTITION BY HASH** whose partitions live in **the same database** can still participate in that database's transactions. That **differs** from splitting across multiple independent PostgreSQL databases: independent databases do not automatically share FKs, SERIALIZABLE transactions, or global UNIQUE constraints.

**An aggregate is not a table.** An Order spanning `Order` and `OrderLine` tables can be one aggregate if all confirm, add, edit, and delete commands go through one owner. Conversely, a `StockBalances` table holding many rows may treat each `(warehouse, SKU)` pair as its own separate aggregate.

### 2.1. What is co-location?

Two datasets are **co-located** when the system routes them to a single place capable of validating and committing the same invariant together.

~~~text
Before:
  Orders      --shard by customer_id--> A
  OrderLines  --shard by product_id --> B/C/D

  Confirming an Order must check across multiple shards.

After:
  Orders      --shard by order_id--> Owner(order_id)
  OrderLines  --shard by order_id--> Owner(order_id)

  An Order and its Lines reside at the same owner.
~~~

This choice may cause queries like “all Lines of Product P” to fan out across shards. If the order-confirmation path is critical and needs strong consistency, that trade-off makes sense; product reporting can use a read model or analytics mart.

**Placing data near each other is not enough** if writers still write to two independent sources of truth. You must design **routing, transactions, and write authority** together.

## 3. Why local transactions do not enforce global invariants

Suppose a campaign has a budget of **1,000,000 VND**, with **900,000 VND** already spent. Two regions both attempt to approve an 80,000 spend:

~~~text
Spent:        900,000
Remaining:    100,000

Shard A reads 100,000 remaining -> accepts +80,000
Shard B reads 100,000 remaining -> accepts +80,000

Approved: 1,060,000 > 1,000,000
~~~

Each shard may run a local transaction and report zero errors. A **`SELECT` sum across replicas** can be even worse if replicas lag.

For the invariant:

~~~text
SUM(accepted_spend WHERE campaign_id = X) <= budget(X)
~~~

protection must cover **every command that increments `accepted_spend` for X**. Running SERIALIZABLE locally on each shard without cross-shard transactions or validation is insufficient. Retries also help nothing when two shards **detect no conflict**.

### 3.1. Can end-of-day reconciliation fix this?

Reconciliation can detect budget overruns. Yet if both spends were already committed to external partners, “deleting one row” does not undo the real business commitment.

Post-event reconciliation fits metrics that **tolerate temporary drift**, such as dashboard view counts, backed by an approved correction workflow. It cannot replace atomic decisions for invariants that cannot be validly compensated.

### 3.2. A read replica is not an owner

A cache reading 5 tickets left **is not authority to issue 5 tickets**. The ticket owner still needs an atomic reservation operation. The UI can display “estimated availability,” while only a committed result from the owner counts as **successfully reserved**.

## 4. Mapping invariants by coordination cost

| Invariant | True scope | Boundary choice |
| --- | --- | --- |
| Quantity > 0 | Single row | NOT NULL, CHECK |
| `reserved <= on_hand` | Single warehouse + SKU | Single balance owner, atomic UPDATE |
| OrderLine belongs to same tenant as Order | Single Order | Composite tenant/order key and same-DB FK |
| CONFIRMED Order has Lines | Order + Line set | Single aggregate owner + transaction |
| Email unique within tenant | Single tenant | Per-tenant UNIQUE and co-location |
| Email unique system-wide | All tenants | Global registry/owner by email |
| Single-use voucher | One voucher code within scope | Owner/guard keyed by voucher |
| Campaign spend <= budget | Entire campaign | Budget owner or escrow |
| Event never counted twice | One source event | Deduplication owner/registry by event ID |
| Published KPI reports must be traceable | Multiple facts and versions | Versioned mart + reconciliation |

A UNIQUE constraint **per shard** is unique only **within each shard**. If two identical emails route to two different shards, you cannot call that global uniqueness. Likewise, an FK **checked via an API GET** is not equivalent to a DBMS-enforced FK inside a transaction, because the parent object could be deleted or moved between the check and the child write.

Classify by **the scope requiring consistency**, not by current table names or service names.

## 5. Five strategies when current boundaries fall short

### 5.1. Change the shard key to co-locate protected data

If Order and OrderLine must update together, shard by `order_id`/`tenant_id` instead of `product_id`. If tickets must be sold at most once, shard by **`seat_id`/`event_id`** instead of `customer_id`. This turns a cross-shard invariant into a **local invariant at the owner**.

Trade-off: queries along other dimensions may need scatter-gather, projections, or dedicated search indexes.

### 5.2. Create a centralized decision owner per object

A `VoucherOwner` or `CampaignBudgetOwner` makes the official redeem/approve decision. Supporting data can live on other shards; only **acceptance authority** is centralized where atomic conditions can be checked.

Trade-off: hot keys, lock contention, cross-region latency, and failover concerns—yet invariants become unambiguous.

### 5.3. Partition spend authority (escrow/quota)

If total quotas granted to shards never exceed the shared budget and no shard exceeds its grant, total spend cannot breach the budget.

~~~text
Campaign budget: 1,000,000
Shard A allocated: 400,000
Shard B allocated: 350,000
Shard C allocated: 250,000
Total allocated: 1,000,000
~~~

Each shard checks locally. However, **rebalancing quotas across shards** must prevent double-allocation: A and B cannot both raise their own quotas by reading a stale copy. A shard exhausting its quota may temporarily reject requests even while other shards hold unused allowance.

### 5.4. Turn a cross-service transaction into a stateful workflow

A checkout flow may transition:

~~~text
PENDING -> STOCK_RESERVED -> PAYMENT_AUTHORIZED -> CONFIRMED
        -> CANCELLED / COMPENSATING / MANUAL_REVIEW
~~~

Each step confirms only after its respective owner commits. Sagas need **idempotency, timeouts, retries, intermediate states, and valid compensations**. A Saga **is not equivalent** to an atomic transaction across all participating services.

### 5.5. Narrow or redefine the invariant by business decision

If the true requirement is email uniqueness **per tenant**, no global registry is needed. If dashboards tolerate 5 minutes of lag, there is no need to lock every shard to update charts. If each warehouse owns its own SKU stock, the whole network need not reserve from one shared pool.

This is a **business contract change**, not an arbitrary technical optimization. For money, safety, permissions, and user commitments, obtain explicit approval before relaxing scopes or accepting temporary drift.

## 6. Case A: inventory reservation at the warehouse + SKU owner

Suppose warehouse 10 has 10 units of SKU 501, with 8 already reserved. Two requests both try to reserve 2 more units.

### 6.1. PostgreSQL schema

~~~sql
CREATE TABLE stock_balances (
    tenant_id BIGINT NOT NULL,
    warehouse_id BIGINT NOT NULL,
    sku_id BIGINT NOT NULL,
    on_hand INTEGER NOT NULL CHECK (on_hand >= 0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    PRIMARY KEY (tenant_id, warehouse_id, sku_id),
    CHECK (reserved <= on_hand)
);

CREATE TABLE stock_reservations (
    reservation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    operation_id TEXT NOT NULL,
    warehouse_id BIGINT NOT NULL,
    sku_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    status TEXT NOT NULL
        CHECK (status IN ('ACTIVE', 'CONSUMED', 'RELEASED')),
    UNIQUE (tenant_id, operation_id),
    FOREIGN KEY (tenant_id, warehouse_id, sku_id)
        REFERENCES stock_balances(tenant_id, warehouse_id, sku_id)
);

INSERT INTO stock_balances
    (tenant_id, warehouse_id, sku_id, on_hand, reserved)
VALUES (1, 10, 501, 10, 8);

-- The eight previously reserved units have a corresponding reservation record.
-- Keeps sample data consistent with the reconciliation query in section 14.
INSERT INTO stock_reservations
    (tenant_id, operation_id, warehouse_id, sku_id, quantity, status)
VALUES (1, 'existing-reservation', 10, 501, 8, 'ACTIVE');
~~~

The **grain** of `stock_balances` is one row per **tenant × warehouse × SKU**. The FK ensures reservations point to an existing balance row. CHECK protects single-row quantities, yet the invariant **`reserved` equals the sum of ACTIVE reservations** spans multiple rows and is not automatically enforced by CHECK.

### 6.2. Conditional UPDATE and reservation in the same transaction

A reserve command can execute **inside the same PostgreSQL database/owner**:

~~~sql
BEGIN;

INSERT INTO stock_reservations
    (tenant_id, operation_id, warehouse_id, sku_id, quantity, status)
VALUES (1, 'order901-line1', 10, 501, 2, 'ACTIVE')
ON CONFLICT (tenant_id, operation_id) DO NOTHING
RETURNING reservation_id;

-- ONLY IF the INSERT above returned exactly 1 row:
UPDATE stock_balances
SET reserved = reserved + 2
WHERE tenant_id = 1
  AND warehouse_id = 10
  AND sku_id = 501
  AND on_hand - reserved >= 2
RETURNING on_hand, reserved;

-- If UPDATE did not return exactly 1 row: ROLLBACK.
-- If both succeeded: COMMIT.
COMMIT;
~~~

**Do not execute the script above blindly:** the application or stored procedure must branch after each `RETURNING`. If INSERT returns **0 rows** because `operation_id` already exists, **skip the UPDATE**; read the existing reservation and compare payload (`SKU`/`warehouse`/`quantity`) to return an idempotent result or report a conflict. If INSERT returns one row while UPDATE returns 0 rows, **ROLLBACK**—never leave an orphaned reservation.

UPDATE evaluates on the current row with the predicate **`on_hand - reserved >= 2`** to decide atomically on that row. In PostgreSQL, concurrent commands modifying the same balance row serialize via row locks. Return ACCEPTED only after the transaction commits.

### 6.3. Release must also happen at most once

~~~sql
BEGIN;

UPDATE stock_reservations
SET status = 'RELEASED'
WHERE tenant_id = 1
  AND operation_id = 'order901-line1'
  AND status = 'ACTIVE'
RETURNING warehouse_id, sku_id, quantity;

-- ONLY IF it returned exactly 1 row, decrement reserved in balance
-- by the exact quantity/warehouse/sku returned above.
UPDATE stock_balances
SET reserved = reserved - 2
WHERE tenant_id = 1
  AND warehouse_id = 10
  AND sku_id = 501
  AND reserved >= 2;

-- If the balance UPDATE affected 0 rows: ROLLBACK.
-- If both succeeded: COMMIT.
COMMIT;
~~~

A real procedure must use **the quantity from the transitioned row**, never trusting a release quantity supplied by the caller. Retrying release after the reservation is already RELEASED must not decrement `reserved` a second time.

When goods physically ship, transitioning to CONSUMED may need to decrement **both `on_hand` and `reserved`** in one transaction per warehouse policy. Never use release in place of consume, as they are distinct business events.

### 6.4. Limitations of the example

- CHECK does not prove `reserved = SUM(quantity of ACTIVE reservations)`.
- Two APIs authorized to edit `stock_balances` and `stock_reservations` independently can still create drift.
- This invariant applies **per warehouse/SKU**. If two warehouses draw from one physical stock pool, ownership must be elevated to the pool or an allocation authority.
- If the Stock DB and Reservation DB are separate systems, the example **no longer shares one transaction** and needs an additional coordination protocol.

## 7. Case B: enforcing a budget cap via a budget owner

The campaign-wide budget has the invariant:

~~~text
accepted_spend(campaign) <= approved_budget(campaign)
~~~

If spend approvals happen across multiple independent shards, each shard can be “locally valid” while overspending the total.

### 7.1. Using a single decision row

~~~sql
CREATE TABLE campaign_budgets (
    campaign_id BIGINT PRIMARY KEY,
    budget_vnd BIGINT NOT NULL CHECK (budget_vnd >= 0),
    spent_vnd BIGINT NOT NULL DEFAULT 0 CHECK (spent_vnd >= 0),
    CHECK (spent_vnd <= budget_vnd)
);

CREATE TABLE campaign_spend_events (
    campaign_id BIGINT NOT NULL
        REFERENCES campaign_budgets(campaign_id),
    operation_id TEXT NOT NULL,
    amount_vnd BIGINT NOT NULL CHECK (amount_vnd > 0),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (campaign_id, operation_id)
);

INSERT INTO campaign_budgets(campaign_id, budget_vnd, spent_vnd)
VALUES (42, 1000000, 900000);

-- The previously approved 900,000 spend has a corresponding event.
INSERT INTO campaign_spend_events
    (campaign_id, operation_id, amount_vnd)
VALUES (42, 'existing-approved-spend', 900000);
~~~

Approve an 80,000 spend using a **conditionally branched sequence**:

~~~sql
BEGIN;

INSERT INTO campaign_spend_events
    (campaign_id, operation_id, amount_vnd)
VALUES (42, 'req-abc', 80000)
ON CONFLICT (campaign_id, operation_id) DO NOTHING
RETURNING operation_id;

-- ONLY IF INSERT created exactly one row:
UPDATE campaign_budgets
SET spent_vnd = spent_vnd + 80000
WHERE campaign_id = 42
  AND budget_vnd - spent_vnd >= 80000
RETURNING budget_vnd, spent_vnd;

-- If INSERT collided: do not increment spent, verify payload.
-- If UPDATE affected 0 rows: ROLLBACK.
-- Only COMMIT if both new steps succeeded.
COMMIT;
~~~

With 100,000 remaining, two concurrent transactions trying to add 80,000 on **the single owner row** cannot both succeed when transactions and predicates are enforced as specified.

Trade-off: a hot campaign can create row lock contention. You can switch to **escrow allocation**, provided every grant, revocation, and transfer of spend authority prevents double-issuance. Never split quotas based on sums read from a lagging replica.

### 7.2. Reallocating quotas

Suppose shard A runs out of quota while B has 50,000 left. If A needs 20,000, a transfer protocol must:

1. Verify B holds **at least 20,000 unused allowance**.
2. Lock or revoke that allowance on B using a network/retry-safe mechanism.
3. Grant 20,000 allowance to A **exactly once**.
4. Log the transfer history and handle unknown states if any step fails.

Never let A increment its own quota and “hope” B decrements later, as both could spend the same allowance during the lag window.

## 8. Case C: co-locating by tenant with composite keys and FKs

A SaaS system has Customer, Order, and OrderLine. Business rules require each OrderLine to belong to an Order in the same tenant, and each Order to point to a Customer in the same tenant. When customer/order IDs are only unique per tenant, every FK must include `tenant_id`.

Example of **partitioning within a single PostgreSQL database**, not multi-server database sharding:

~~~sql
CREATE TABLE tenant_customers (
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    email_normalized TEXT NOT NULL,
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, email_normalized)
) PARTITION BY HASH (tenant_id);

CREATE TABLE tenant_customers_p0
PARTITION OF tenant_customers
FOR VALUES WITH (MODULUS 2, REMAINDER 0);

CREATE TABLE tenant_customers_p1
PARTITION OF tenant_customers
FOR VALUES WITH (MODULUS 2, REMAINDER 1);

CREATE TABLE tenant_orders (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')
    ),
    PRIMARY KEY (tenant_id, order_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES tenant_customers(tenant_id, customer_id)
) PARTITION BY HASH (tenant_id);

CREATE TABLE tenant_orders_p0
PARTITION OF tenant_orders
FOR VALUES WITH (MODULUS 2, REMAINDER 0);

CREATE TABLE tenant_orders_p1
PARTITION OF tenant_orders
FOR VALUES WITH (MODULUS 2, REMAINDER 1);

CREATE TABLE tenant_order_lines (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sku_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES tenant_orders(tenant_id, order_id)
) PARTITION BY HASH (tenant_id);

CREATE TABLE tenant_order_lines_p0
PARTITION OF tenant_order_lines
FOR VALUES WITH (MODULUS 2, REMAINDER 0);

CREATE TABLE tenant_order_lines_p1
PARTITION OF tenant_order_lines
FOR VALUES WITH (MODULUS 2, REMAINDER 1);
~~~

The PK/UNIQUE keys on partitioned tables include **`tenant_id`** (the partition key) as required by PostgreSQL. Composite FKs stop an OrderLine in tenant A from pointing to an Order/Customer that exists only in tenant B. All three tables route by tenant, paving the way for co-location if an **independent sharding design later** uses the same routing.

**Important distinction:** PostgreSQL partitioning here is still **one database with cross-partition transactions**; FKs are enforced by the DBMS. If each partition moves to an independent server/database, never assume cross-server FKs or transactions automatically persist.

### 8.1. Testing with two-tenant data

~~~sql
INSERT INTO tenant_customers
    (tenant_id, customer_id, email_normalized)
VALUES
    (1, 101, 'a@example.test'),
    (2, 101, 'a@example.test');

INSERT INTO tenant_orders
    (tenant_id, order_id, customer_id, status)
VALUES (1, 5001, 101, 'DRAFT');

INSERT INTO tenant_order_lines
    (tenant_id, order_id, line_no, sku_id, quantity)
VALUES (1, 5001, 1, 9001, 2);

-- Tenant 2 does not have Order 5001: the statement below is rejected by the FK.
INSERT INTO tenant_order_lines
    (tenant_id, order_id, line_no, sku_id, quantity)
VALUES (2, 5001, 1, 9001, 2);
~~~

Two tenants sharing `email_normalized` is allowed here: UNIQUE guards **per-tenant**, not platform-wide email uniqueness. The normalized email is assumed to follow application policy; a simple `lower()` is not a reliable universal email normalization standard for every case.

### 8.2. Ensuring a CONFIRMED Order has at least one Line

An FK from Line to Order ensures every child has a parent, not that every parent always has a child.

~~~sql
SELECT o.tenant_id, o.order_id
FROM tenant_orders AS o
WHERE o.status = 'CONFIRMED'
  AND NOT EXISTS (
      SELECT 1
      FROM tenant_order_lines AS l
      WHERE l.tenant_id = o.tenant_id
        AND l.order_id = o.order_id
  );
~~~

This query **detects** violations—it does not prevent them. To enforce the invariant on write, the Order owner must:

1. Lock the Order and verify status inside a transaction.
2. Verify at least one valid Line exists.
3. Transition `DRAFT -> CONFIRMED` when preconditions pass.
4. Ensure every Line delete/edit uses **the same locking convention and status check**; forbid deleting the last line of a CONFIRMED Order.
5. Commit or roll back the entire transaction.

If the confirmation API checks properly while a background job deletes Lines bypassing the owner, the invariant can still break. **The write-ownership boundary** must encompass every relevant write path.

## 9. Global uniqueness: changing scope, key sharding, or registry

“Email unique platform-wide” differs dramatically from “email unique within a tenant.”

- **Per-tenant:** `UNIQUE(tenant_id, email_normalized)` suffices when rows of the same tenant reside where uniqueness is supported.
- **Global:** if Customers are sharded by tenant, you need a mechanism checking emails across every tenant.
- **Shard by email:** routes identical emails to the same owner; changing an email may require moving shards or a separate lookup.
- **Global registry:** one owner holds email registration authority; Customer shards only use emails approved by the registry.

Example global registration table:

~~~sql
CREATE TABLE global_email_registry (
    email_normalized TEXT PRIMARY KEY,
    identity_id BIGINT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (
        status IN ('RESERVED', 'ACTIVE', 'RELEASE_PENDING')
    )
);
~~~

A registry can atomically claim an email. Yet **registry succeeds, Customer shard fails** remains a two-system problem. You need stateful workflows, idempotency, timeouts, expiry/reconciliation, and rules for when an account becomes ACTIVE.

Ask further: is email a **username**, contact channel, or profile attribute? Can a shared support email belong to multiple users? Is an old email still reserved after soft-deleting an account? Imposing a global invariant when the business only needs per-tenant uniqueness creates unnecessary bottlenecks.

## 10. Time-based partitioning and global UNIQUE limitations

Large event tables are often partitioned by day/month for storage management and query pruning. Yet the invariant “a `source_event_id` is accepted at most once” **has no date in its uniqueness scope**.

Suppose source event E-100 occurs on Oct 10, and is later replayed with the same ID and a modified timestamp of Nov 10. If each partition only has `UNIQUE(source_event_id)`, E-100 can appear once **in each partition**.

### 10.1. PostgreSQL RANGE partition example

~~~sql
CREATE TABLE meter_events (
    tenant_id BIGINT NOT NULL,
    source_event_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    device_id BIGINT NOT NULL,
    value_num NUMERIC(18, 5) NOT NULL,
    PRIMARY KEY (occurred_at, tenant_id, source_event_id)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE meter_events_oct
PARTITION OF meter_events
FOR VALUES FROM ('2026-10-01 00:00:00+00')
           TO ('2026-11-01 00:00:00+00');

CREATE TABLE meter_events_nov
PARTITION OF meter_events
FOR VALUES FROM ('2026-11-01 00:00:00+00')
           TO ('2026-12-01 00:00:00+00');
~~~

The PK guards **`(occurred_at, tenant_id, source_event_id)`**, not **`(tenant_id, source_event_id)`** across all timestamps. The same ID with a different `occurred_at` can enter two partitions without violating the PK.

In PostgreSQL, UNIQUE/PRIMARY KEY constraints on partitioned tables must include **the partition key columns** under current restrictions. Never assume you can slap a table-wide `UNIQUE(source_event_id)` onto a table partitioned by `occurred_at` and expect the DBMS to enforce uniqueness across all partitions automatically.

### 10.2. Creating a time-independent ingestion registry

~~~sql
CREATE TABLE accepted_source_events (
    tenant_id BIGINT NOT NULL,
    source_system TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    first_accepted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, source_system, source_event_id)
);
~~~

If the registry and `meter_events` share **the same database transaction**, the ingestion path can:

1. INSERT into `accepted_source_events` by source ID.
2. On ID conflict, compare payloads; a valid retry creates no new event, while a differing payload is flagged.
3. If the registry insert succeeds, INSERT into `meter_events`.
4. Commit both, or roll back both.

If the registry lives in an **independent database** from `meter_events`, that sequence is no longer automatically atomic. You need a single ingestion owner, genuine distributed transactions, or a pending/published stateful workflow.

**Never confuse partition pruning with invariants.** Time partitioning can accelerate reports, yet it does not stop duplicate events, late events, backfills, or corrections that change partitions.

## 11. When invariants span multiple services or shards

An order may need to reserve stock at two warehouses and confirm payment:

~~~mermaid
flowchart LR
    O["Order Owner"] --> WA["Stock Owner A"]
    O --> WB["Stock Owner B"]
    O --> P["Payment Owner"]
~~~

Requirement:

> An Order transitions to CONFIRMED only once both warehouses have reserved sufficient stock and payment is verified per policy.

**A transaction inside the Order DB** cannot automatically roll back steps already committed in two Stock DBs or an external payment gateway.

### 11.1. Three primary architectural options

**Co-locate data into one transaction boundary:** if objects must truly commit together and centralization is tolerable, move shard/aggregate ownership so operations fit inside one transaction of a suitable DBMS. Trade-off: hot keys, write latency, and geographic distribution difficulty.

**Distributed transaction/2PC:** some distributed DBs support cross-shard transactions or two-phase commit. Verify participating systems, coordinator crash recovery, lock hold times, timeouts, and availability. Opening two connections, calling `BEGIN` on both, and committing sequentially **is not** 2PC. External payment providers do not automatically join database 2PC either.

**Saga/workflow:** when steps are business-compensable, maintain a state machine and idempotent commands:

~~~text
PENDING
  -> RESERVED_AT_A
  -> RESERVED_AT_A_AND_B
  -> PAYMENT_AUTHORIZED
  -> CONFIRMED

When a step fails:
  -> COMPENSATING
  -> RELEASE committed reservations
  -> VOID payment authorization when permitted
  -> CANCELLED or MANUAL_REVIEW
~~~

### 11.2. Mandatory guarantees for Sagas

- Each service owner **enforces its local invariant**: warehouses never over-reserve, payments never double-capture.
- Every command carries a stable **`operation_id`**; retries never create new side effects.
- Only the Order owner transitions to CONFIRMED after collecting all required evidence.
- PENDING and COMPENSATING are **real business states**, never misrepresented as finished transactions.
- Timeouts can leave an **unknown outcome**; query status by idempotency key rather than assuming a failed call means the remote side did not commit.
- Compensations can fail and need retries and escalation; never call them atomic rollbacks.
- If a step is irreversible (goods shipped, non-cancelable bank transfer), use a **dedicated remediation workflow** or enforce stronger pre-commit decisions.

Sagas do not provide all-or-nothing atomicity at every instant. They preserve consistency **of the end-state process** with explicit intermediate states. If the business strictly forbids exposing intermediate states, consider stronger transactions/coordination or redesigning commitments.

### 11.3. Outbox and retries do not replace cross-service atomicity

The transactional outbox writes “local change committed” and the outgoing event **in the same database transaction**. Downstream consumers process the event and deduplicate by `event_id`.

That solves part of **not losing events after a local commit**, yet it does not guarantee consumers have finished processing or that two services committed together. APIs returning CONFIRMED must follow workflow contracts, not merely “an event was sent.”

## 12. Single writer, read models, and CQRS boundaries

One decision authority can feed multiple read copies:

~~~mermaid
flowchart TB
    CMD["Commands"] --> OWN["Aggregate Owner + Transaction"]
    OWN --> LOG["Outbox / CDC"]
    LOG --> RD["Read Model"]
    LOG --> AN["Analytics Mart"]
    RD --> API["API read"]
    AN --> BI["Dashboard"]
~~~

- **Owner:** authorized to accept or reject changes per invariants.
- **Read model:** optimized for search, filtering, and read latency; may lag.
- **Analytics mart:** combines sources for analysis with explicit refresh windows.
- **Outbox/CDC:** syncs committed changes; needs replay, dedup, and reconciliation.

If an API writes straight into the Read Model and treats it as truth, ownership boundaries collapse. Document the **source of truth**, authorized writers of authoritative data, and who owns error recovery.

Reading **`available_stock = 5`** from a read replica does not authorize an API to confirm a 5-unit hold without calling the Stock Owner. Replicas may display “roughly 5 left,” while **`ReserveStock`** must validate at the decision authority.

### 12.1. Every write path must follow the rules

An invariant can be broken by:

- Normal APIs validating properly while bulk import jobs bypass checks.
- Admin scripts directly mutating `budget`/`spent` or `reserved`.
- Consumers replaying an event twice without deduplication.
- Flows deleting the last Line of a CONFIRMED Order without locking the Order.
- Dual-write migrations letting two owners accept commands simultaneously.
- A legacy service retaining write credentials after ownership transfer.

**Changing boundaries must include DB permissions, routing, code paths, batch jobs, and runbooks**, not just renaming a microservice or adding an API layer.

## 13. Migrating shard keys: the worst hazard is two concurrent writers

Suppose tenant 1 moves from shard A to B:

~~~text
Old route: tenant 1 -> shard A
New route: tenant 1 -> shard B

Client X still writes to A using the old route.
Client Y writes to B using the new route.

Each place believes it is the owner.
~~~

If both accept voucher redemptions or stock reservations, data is valid **within each shard** yet wrong **across the tenant**. Successfully copying row counts does not prevent this split-brain.

### 13.1. Verifiable migration workflow

1. **List invariants:** what must hold before, during, and after cutover?
2. **Define transfer scope:** tenant, `aggregate_id`, key-range, or `voucher_code`?
3. **Define owner/routing map:** a business key has only one commit-authorized owner.
4. **Snapshot backfill:** copy data and business keys while preserving stable ID mappings.
5. **Sync deltas:** use idempotent CDC/outbox/replay and track lag.
6. **Verify consistency:** PK/FK/uniques, row counts by business key, balances, event offsets, and state totals.
7. **Block dual writers:** use controlled write pauses or enforced fencing/owner-epoch before cutover.
8. **Switch routes:** commands arriving on old routes must be rejected/forwarded, never independently committed.
9. **Post-cutover monitoring:** lag, hung operations, mismatches, timeouts, and retries.
10. **Conditional rollback:** never blindly flip back to A if A missed updates post-cutover.

“Write to both A and B” dual-write is not inherently safe: succeeding on A and failing on B diverges state, and both accepting commands can double business effects.

### 13.2. Fencing and owner epochs

One way to govern authority transfers uses monotonically increasing epochs:

~~~text
tenant 1, owner = A, epoch = 7
after cutover:
tenant 1, owner = B, epoch = 8
~~~

Writers attach their epoch and command handlers reject stale epochs. However, **merely storing the epoch in an asynchronously replicated metadata table is insufficient** if A can still commit under epoch 7 after B already accepted epoch 8.

Fencing must bind to **authoritative write capability** or strong consensus/leases/locks so the old owner truly loses write power upon handoff. Test under network partitions, timeouts, and leader failovers.

## 14. Verifying invariants after boundary changes

Migration verification goes beyond comparing `COUNT(*)` or grand `SUM`s. Opposite errors can cancel out, or total reservations can match while assigned to the wrong warehouses.

### 14.1. Non-negative stock within capacity

~~~sql
SELECT tenant_id, warehouse_id, sku_id, on_hand, reserved
FROM stock_balances
WHERE on_hand < 0
   OR reserved < 0
   OR reserved > on_hand;
-- Expected: zero rows.
~~~

Reconcile materialized `reserved` against ACTIVE reservations:

~~~sql
SELECT b.tenant_id, b.warehouse_id, b.sku_id,
       b.reserved,
       COALESCE(r.active_qty, 0) AS active_qty
FROM stock_balances AS b
LEFT JOIN (
    SELECT tenant_id, warehouse_id, sku_id,
           SUM(quantity) AS active_qty
    FROM stock_reservations
    WHERE status = 'ACTIVE'
    GROUP BY tenant_id, warehouse_id, sku_id
) AS r
  ON r.tenant_id = b.tenant_id
 AND r.warehouse_id = b.warehouse_id
 AND r.sku_id = b.sku_id
WHERE b.reserved <> COALESCE(r.active_qty, 0);
~~~

This query assumes all reserved quantities are recorded as ACTIVE in this table with no parallel reservation flow. If intermediate states or inventory adjustments exist, adapt the formula to the **business contract** rather than treating every mismatch as data corruption.

### 14.2. Materialized budget reconciled against spend events

~~~sql
SELECT b.campaign_id, b.budget_vnd, b.spent_vnd
FROM campaign_budgets AS b
WHERE b.spent_vnd < 0
   OR b.spent_vnd > b.budget_vnd;

SELECT b.campaign_id, b.spent_vnd,
       COALESCE(e.event_amount_vnd, 0) AS event_amount_vnd
FROM campaign_budgets AS b
LEFT JOIN (
    SELECT campaign_id, SUM(amount_vnd) AS event_amount_vnd
    FROM campaign_spend_events
    GROUP BY campaign_id
) AS e ON e.campaign_id = b.campaign_id
WHERE b.spent_vnd <> COALESCE(e.event_amount_vnd, 0);
~~~

In this model, events only increase accepted spend. Once refunds/reversals exist, reconcile using **net effects** or valid deltas rather than mechanically summing positive events.

### 14.3. CONFIRMED Order without Lines

~~~sql
SELECT o.tenant_id, o.order_id
FROM tenant_orders AS o
WHERE o.status = 'CONFIRMED'
  AND NOT EXISTS (
      SELECT 1
      FROM tenant_order_lines AS l
      WHERE l.tenant_id = o.tenant_id
        AND l.order_id = o.order_id
  );
~~~

If rows return, trace every writer permitted to mutate status or lines. This indicates a **write-path or transition-policy bug**, not evidence that you just need another index.

### 14.4. Multi-level reconciliation

Pre/post-migration verification should cover:

| Level | What to compare |
| --- | --- |
| **Business ID** | Any missing, duplicate, or invalidly re-owned records? |
| **Tenant/Shard** | Does every object reside at exactly one authoritative owner? |
| **Relationships** | FKs/parent-child, tenant scope, status transitions |
| **Scoped totals** | Budget/campaign, reserved/warehouse/SKU |
| **Events** | Were `operation_id`/source IDs processed exactly once? |
| **Time** | Late events, backfills, epochs, and cutover timestamps |
| **Error states** | PENDING/COMPENSATING needing retries or manual intervention |
| **Performance** | Hot keys, p95/p99 commits, CDC lag, read latency |

A matching global sum never proves **subgroups** or individual **business keys** are right.

## 15. Boundary selection matrix by scenario

| Scenario | Option worth considering | Risks/trade-offs |
| --- | --- | --- |
| Order + Line need a shared transaction | Co-locate by order/tenant | Product-based queries may fan out |
| Stock per warehouse/SKU | Owner and conditional UPDATE on balance | Lock contention on hot SKUs |
| Shared stock allocated across warehouses | Shared owner or escrow quotas | Quota transfers need a protocol |
| Single-use voucher | Owner/registry by voucher | Hot keys and failover |
| Per-tenant unique email | `UNIQUE(tenant_id,email)` | Allows duplicates across tenants |
| System-wide unique email | Global registry or shard by email | Workflows across Customer shards |
| Campaign spend within budget | Single owner or allocated spend quotas | Lock contention / underutilization |
| Payment and stock in separate services | Saga or genuine distributed transaction | Intermediate states / 2PC overhead |
| Time-partitioned events, global ID | Dedupe registry outside time partition | Registry must sit safely on ingest path |
| Dashboard needing cross-shard data | Read model/mart with freshness SLA | Never use for transactional approvals |
| Moving tenant to a new shard | Backfill + fencing + cutover | Split-brain, replay, hard rollback |
| Global invariant too expensive | Negotiate scope/commit semantics change | Requires business sign-off |

**Warning signs to stop and redesign:** every write request calls multiple services just to check a mandatory condition; FKs are “checked via GET API”; the same key can be accepted on multiple shards; the system relies on nightly jobs to fix already-confirmed commitments; or a migration grants write authority to two owners at once.

## 16. Trade-offs among performance, availability, and correctness

Stronger invariant enforcement can raise costs:

- **Write p95/p99:** extra coordination and locking can increase command latency.
- **Throughput:** a hot budget/stock row can cap commands per second.
- **Availability:** when the owner is unreachable, commands may have to reject/wait instead of accepting unchecked writes.
- **Read amplification:** partitioning by business owner can force queries on other dimensions to fan out.
- **Data movement:** changing shard keys requires backfill/CDC, cutover control, and split-brain risk management.
- **Operational burden:** reconciliation, deadlock/serialization retries, Saga recovery, and alerting.

Benchmark with hot/cold data, realistic read–write mixes, shard counts, and geographic distances. Never extrapolate a few milliseconds on a small table into linear scalability.

If FKs/uniques/row locks slow writes down, first ask whether you can **shrink owner scope**, **split authority via escrow**, **tune indexes/transactions**, or **separate read models**. Dropping constraints and relying on post-hoc cleanup jobs changes the guarantee level—it is not a free optimization.

### 16.1. Enforce strictly, not blindly everywhere

Not every analytical query needs a cross-shard transaction. Product revenue can aggregate from committed events with a 1-minute lag, governed by backfill and reconciliation rules. Nor should every Customer in a tenant contend on one coarse lock when the invariant applies **per Order**.

The goal is **coordinating exactly where required**, not cramming the whole system into one giant transaction.

## 17. Comparing relational, document, graph, and warehouse models

| Technology | Useful boundaries | What must NOT be assumed |
| --- | --- | --- |
| **Relational** | PK/FK/UNIQUE and transactions per aggregate/shard | Single-DB FKs do not automatically become cross-server FKs |
| **Document** | Document/aggregate updated atomically if DB supports it | Multiple related documents are not automatically atomic |
| **Graph** | Owner/transaction for nodes/edges needing validation | Traversing stale replicas does not prove current permissions/cycles |
| **Warehouse** | Facts/dimensions, versioned marts, reconciliation | End-of-day rollups do not prevent overselling at checkout |

### 17.1. Document: embedding co-lifecycle data

An Order document:

~~~json
{
  "tenantId": 1,
  "orderId": 5001,
  "status": "DRAFT",
  "lines": [
    {"lineNo": 1, "skuId": 9001, "quantity": 2}
  ]
}
~~~

helps validate status and lines inside one document update **if** the engine supports atomic document updates and all writers comply. Yet Inventory and Payment in separate documents/services still require coordination; embedding Lines does not create a checkout-wide transaction.

### 17.2. Graph: invariants over edges and paths

An org/authorization graph may require “each resource has one direct owner” or “reporting hierarchy is acyclic.” Updating an edge may require inspecting a subgraph; if edges span partitions, local checks do not prove global acyclicity.

Choose a subgraph owner, serialized command path, or strong consistency protocol. Accept post-hoc checks only when temporary cycles cannot compromise security or safety.

### 17.3. Warehouse: reconciliation rather than selling decisions

An hourly inventory mart suits trend analysis, not deciding who gets the last two units under concurrent checkout traffic. Commands must hit the **Stock Owner**. Conversely, never force every dashboard to hit the owner under heavy locks when a projection with a clear SLA suffices.

## 18. Redesign and migration workflow

1. **Write the invariant** as a formula, scope, and time when it must hold.
2. **List all participating data** and current owners/shards.
3. **List all writers**, including batches/imports/admins and consumers.
4. **Construct a race schedule** showing how two requests can break the invariant.
5. **Verify real transaction capabilities** per node and across nodes.
6. **Prefer co-locating** data and write authority that must update together.
7. **If hot owner,** evaluate escrow/quotas or safely proven authority splitting.
8. **If cross-service,** define state machines, idempotency, unknown outcomes, and compensations.
9. **If invariant scope must change,** obtain business sign-off and update API/report contracts.
10. **Design PK/FK/UNIQUE** for the new scope without omitting partition keys or tenants.
11. **Plan the migration** with backfill, CDC, fencing, cutover, and proper rollback.
12. **Test concurrency/failover** before and after cutover.
13. **Reconcile by business key** and invariants, not just SUM/COUNT.
14. **Measure operations** across hot keys, write latency, locks, replication lag, and throughput.
15. **Document the architecture decision** so future writers never break the boundary.

### 18.1. Decision record template

~~~text
Invariant:
  A voucher is redeemed at most once within a tenant.

Scope:
  (tenant_id, voucher_code)

Old routing:
  Redemption sharded by customer_id.
  Two customers could redeem the same voucher on two shards.

New owner:
  VoucherOwner sharded by (tenant_id, voucher_code).

Write protocol:
  AVAILABLE -> REDEEMED via atomic transition at the owner.
  operation_id is stored for safe retries.

Cross-service lifecycle:
  Order transitions to CONFIRMED only per workflow rules.
  Compensation/release occurs only when voucher policy permits.

Read model:
  Committed events are replicated for reporting.
  Projections hold no authority to approve redemptions.

Migration:
  Backfill, block legacy writers, fence, cutover, reconcile.

Validation:
  No voucher has more than one valid redemption.
  Retries/concurrent requests do not increment redemption counts.
  No two owners ever hold commit authority simultaneously.
~~~

This is an illustrative design record, not a claim that every voucher becomes reusable whenever an Order cancels. Voucher lifecycles must follow business policy.

## 19. Case-study exercises with solution hints

### Case 1. Re-choosing a shard key

**Prompt:** Orders are sharded by `customer_id`, OrderLines by `product_id`. CONFIRMED requires an Order to have Lines in the same tenant. What is hard to enforce?

**Hint:** Validation and commit must span shards. Consider co-locating by **`(tenant_id, order_id)`** with one aggregate owner; use composite FKs within one DB and a unified transaction/write path for all OrderLine mutations.

### Case 2. Single-use voucher

**Prompt:** Two different customers apply the same voucher and land on two `customer_id` shards. Is a local UNIQUE enough?

**Hint:** Not if uniqueness is per voucher. Assign an owner/registry keyed by **voucher code within scope** with atomic transitions; use `operation_id` against retries.

### Case 3. Local SERIALIZABLE

**Prompt:** A campaign has 100,000 left. Two shards both spend 80,000, each running SERIALIZABLE. Why can it still overspend?

**Hint:** Without cross-shard coordination, the two transactions see no shared conflict. Use a budget owner or escrow spend quotas with protected total allocation.

### Case 4. Two stock reservation requests

**Prompt:** `on_hand = 10`, `reserved = 8`, two requests each ask for 2. Why is `SELECT` then `UPDATE` insufficient?

**Hint:** Both reading 2 remaining can lead to two promises. Use a conditional atomic UPDATE at StockOwner in one transaction with reservation/idempotency, returning ACCEPTED only after commit.

### Case 5. Payment fails after reservation

**Prompt:** Stock DB committed a reservation; Payment Service declines. Does rolling back the Order DB return the stock?

**Hint:** No. You need an idempotent `ReleaseReservation` or a genuinely supported distributed transaction protocol; a Saga records compensation states and retries. Compensation is not an atomic rollback.

### Case 6. Per-tenant vs. global email

**Prompt:** Does `UNIQUE(tenant_id,email_normalized)` on a tenant-sharded table guarantee an email is used once across the whole SaaS?

**Hint:** No. That is per-tenant uniqueness. Global uniqueness needs an email-keyed registry/owner or matching routing, plus lifecycle coordination between the registry and Customer.

### Case 7. Event ID across time partitions

**Prompt:** The same event E100 is written in October and November with different `occurred_at` values. Does `PK(occurred_at,event_id)` block it?

**Hint:** No, because the two composite keys differ. Deduplicate by source event ID within scope using a protocol that preserves uniqueness across partitions; PostgreSQL partitioned UNIQUE constraints are subject to partition-key rules.

### Case 8. Dual write during migration

**Prompt:** A tenant migrates A -> B and the system accepts writes on both sides for one hour to avoid downtime. Is this guaranteed safe?

**Hint:** No; split-brain can occur. Only one owner may accept commands at a time, enforced via fencing/epochs or a controlled write pause; copy deltas idempotently and reconcile post-cutover.

### Case 9. Reconciling only total reservations

**Prompt:** Before and after migration, total `reserved` is 500, yet some reservations point to the wrong warehouse. Can the data be declared correct?

**Hint:** No. Reconcile by **tenant, warehouse, SKU, `operation_id`, status, quantity**, and concrete FKs/invariants.

### Case 10. Escrow quota exhaustion on one shard

**Prompt:** Shard A is out of quota; B has 50,000 left. May A raise its own quota by 20,000 and ask B to deduct later?

**Hint:** No, because both sides could spend that same allowance. Use a non-overlapping quota transfer protocol; until safely transferred, A must wait or reject even though system-wide quota remains.

### Case 11. Replica reports tickets available

**Prompt:** A replica shows three tickets left. The API marks a sale successful without calling the ticket owner. Is this safe?

**Hint:** No. The replica may lag; commands must reserve atomically at the owner before promising a sale.

### Case 12. Relaxing an invariant for speed

**Prompt:** A team wants to drop the global email registry, run a nightly deduplication job, and still advertise “system-wide unique email.”

**Hint:** No. That is an unapproved change to the guarantee level. Either optimize the registry, change routing, or formally update the contract to per-tenant if the business agrees.

## 20. Acceptance checklist

- [ ] Invariants have **explicit scopes and enforcement moments** documented.
- [ ] The owner deciding command acceptance is unique at commit time.
- [ ] Data updated together is co-located or backed by sound coordination.
- [ ] PK/FK/UNIQUE match tenant, shard, and business keys; global uniqueness is not confused with local uniqueness.
- [ ] Every API, job, import, and admin script obeys the owner/write path.
- [ ] Retries/idempotency produce no duplicate effects for the same `operation_id`.
- [ ] Saga flows define intermediate states, compensations, and unknown-outcome handling.
- [ ] Quotas/escrow never double-issue spend authority during transfers.
- [ ] Every read copy defines a freshness SLA and is never used in place of the owner for strong decisions.
- [ ] Migrations cover backfill, CDC, fencing, cutover, reconciliation, and evaluated rollbacks.
- [ ] Concurrency, failover, split-brain, duplicates, and late adjustments are tested.
- [ ] Data verification checks business IDs, tenants, statuses, and invariants—not just COUNTs.
- [ ] Latency, contention, throughput, recoverability, and partitioning costs are measured.
- [ ] Ownership decisions and remaining monitored assumptions are documented.

## 21. Key takeaways

- **Invariants dictate boundaries**, not the reverse: if an important invariant must query multiple shards on every write, revisit the shard key/aggregate/owner.
- **Partitioning inside one database differs from independent sharded databases.** Transactions, FKs, and UNIQUE constraints must be verified against the exact DBMS and deployment topology.
- **Co-locating or routing by business key** turns many cross-node invariants into local checks.
- **Global uniqueness, campaign budgets, and single-use vouchers** require a single owner or safe quota-allocation protocol; local transactions alone create no global guarantee.
- **Sagas govern workflows and compensations** without creating a system-wide atomic transaction; compensations can also fail.
- **Outbox, CDC, projections, and read replicas** improve sync and reads—they never replace the owner's acceptance authority.
- **Changing a shard key changes ownership**, not just row placement; cutover must block concurrent dual writers.
- **Reconciliation by invariants and business keys** matters more than comparing row counts or totals, because detailed errors can cancel each other out.

A trustworthy distributed design is not one that avoids coordination altogether. It is one that **knows which invariants require coordination, places decision authority at the right boundary, shrinks the coordination scope to what is reasonable, and provides evidence that published states obey the business contract**.
