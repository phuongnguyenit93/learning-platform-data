# Synchronizing Changes Across Java Models, Storage, Events, and Reports

## Learning Objectives

After this lesson, you will be able to:

- Determine the impact of **a single business change** across the Java domain model, storage schema, integration events/APIs, and reporting model simultaneously.
- Distinguish **structural compatibility** from **semantic compatibility**, especially when adding fields, changing monetary calculations, renaming statuses, or altering grain.
- Design an **expand → backfill/migrate → switch → contract** roadmap capable of running old and new application versions side-by-side during a deployment window.
- Protect business invariants with Java, CHECK/FK constraints, transactions, optimistic locking, and reconciliation checks while schemas are being upgraded.
- Evolve integration events by version while preserving the meaning of committed events, idempotency, ordering, replayability, and consumer upgrade paths.
- Evolve analytical facts, dimensions, and metrics without conflating **gross sales value**, **payable amount**, **captured cash**, and **accounting revenue**.
- Build compatibility matrices, quality gates, operational observability, rollback/roll-forward strategies, and legacy data handling workflows.
- Compare differences when applying these patterns across relational, document, graph, or analytical databases.

In **DATABASE_DATA_MODELING**, the job is not only translating requirements into verifiable entities, relationships, constraints, keys, indexes, and physical schemas. A sound model must also **evolve when business rules change** without corrupting stored records, published events, or issued reports. The **Model Evolution** chapter treats change as a journey spanning multiple data representations rather than a single class edit and `ALTER TABLE`.

## 1. Why must all four layers evolve around the same meaning?

A single change can be viewed across four layers:

| Layer | Question on change | What breaks easily if overlooked |
| --- | --- | --- |
| **Java/domain model** | Which invariants and behaviors change? | App miscomputes totals or permits invalid states |
| **Storage** | How are legacy rows represented, and do constraints/indexes still hold? | Incomplete backfill; new rows break old readers |
| **Events/contracts** | How do recipients interpret fields, statuses, and units? | Old consumers misinterpret data even when JSON parses |
| **Reports/analytics** | Do grain, metrics, history, and legacy data handling change? | Sales sums look arithmetically valid yet carry wrong meaning |

The layers do not need an identical structure. A Java aggregate may hold a `Money` value object; PostgreSQL may store `BIGINT` VND; integration messages may publish string amounts and currency; fact tables may store separate additive measures. **What must stay synchronized is the contract of meaning and correctness**, not forcing identical field lists everywhere.

~~~mermaid
flowchart TB
    R["Business requirement<br/>add order-line discount"]
    R --> D["Java Domain<br/>total calculation rules"]
    R --> S["Storage<br/>columns & constraints"]
    R --> E["Event/API contract<br/>version & semantics"]
    R --> M["Reporting model<br/>grain & metrics"]
    D --> W["Transactional write"]
    S --> W
    W --> O["Committed outbox"]
    O --> E
    E --> P["Consumers / CDC / ETL"]
    P --> M
    M --> Q["Reconciliation & verification"]
    Q -.-> R
~~~

If only one dimension changes:

- Java begins applying discounts before storage has the column: data cannot be recovered or totals recompute wrongly.
- Storage adds the new column while old apps still write: defaults and rows created by old writers must be interpreted accurately.
- Producer changes event field meaning while keeping the old version: consumers miscompute KPIs silently without errors.
- Dashboard keeps the old formula: discounts look like revenue errors or gross revenue silently turns into net revenue.

## 2. Running scenario: adding a per-unit item discount

Suppose the sales system initially has no discounts. An `Order` consists of `OrderLine`s:

~~~text
Before change:
OrderLine { lineNo, skuId, quantity, unitPriceVnd }
Order     { orderId, status, totalVnd }

totalVnd = SUM(quantity × unitPriceVnd)
~~~

Under the old contract, **`totalVnd` means the amount the customer must pay for the items**, not a field intentionally representing list price before discounts. Because discounts did not exist yet, gross list price and payable total were equal.

New requirement: allow a **fixed per-unit discount on each order line**, not exceeding unit price; payable total decreases by the discount amount. Example:

| Line | Quantity | Unit price | Discount per unit | Gross value | Total discount | Payable |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| T-shirt | 2 | 100,000 | 10,000 | 200,000 | 20,000 | 180,000 |
| Cap | 1 | 50,000 | 0 | 50,000 | 0 | 50,000 |
| **Total** | | | | **250,000** | **20,000** | **230,000** |

New invariants:

\[
0 \le d_i \le p_i,\qquad q_i>0,
\]

\[
\text{gross}=\sum_i q_ip_i,\quad
\text{discount}=\sum_i q_id_i,\quad
\text{payable}=\text{gross}-\text{discount}.
\]

Here \(p_i\) is unit price in VND, \(d_i\) is per-unit discount, and \(q_i\) is quantity. Discounts cannot exceed line price, totals cannot be negative, and every multiplication/addition must guard against overflow. This lesson does **not** cover order-level discounts, taxes, shipping, foreign currencies, multi-source vouchers, or refunds; if the domain expands further, a fuller pricing/allocation model is needed.

### Unchanged semantic contract of `totalVnd`

Key decision: the legacy **`totalVnd` field continues to mean the payable amount**. For old orders with discount=0, `totalVnd = gross = payable`. For new discounted orders, `totalVnd = payable`. Since legacy consumers were promised `totalVnd` is the payable amount, preserving that meaning maintains compatibility.

Had the old contract defined `totalVnd` as **pre-discount gross value**, you could not silently switch it to payable and still call it backward compatible. In that case, you must keep the old meaning or issue a new contract/field and migrate consumers in a controlled way. **Same name and same data type never prove same meaning.**

## 3. Impact mapping before editing code

A seemingly simple UI change can ripple across:

| Component | Current | After change | Decision to record explicitly |
| --- | --- | --- | --- |
| Java `OrderLine` | `quantity`, `unitPriceVnd` | add `discountPerUnitVnd` | Constraint 0 ≤ discount ≤ price |
| Java `Order` | `totalVnd()` | `gross()`, `discount()`, `payable()` | Legacy `totalVnd` equals `payable` |
| SQL `order_line` | `quantity`, `unit_price_vnd` | add `discount_per_unit_vnd` | Default/backfill legacy rows = 0 |
| SQL `order_header` | `total_vnd` | add `gross_total_vnd`, `discount_total_vnd` | Keep `total_vnd = payable` |
| API response | `totalVnd` | add optional breakdown | Old clients not forced to read new fields |
| Integration event | `OrderPaid v1`: `totalVnd` | `OrderPaid v2`: `gross/discount/payable` | Versioning, consumer migration |
| Analytics fact | `paid_line_amount_vnd` | `gross/discount/net_paid_vnd` | Same sales-line grain, no duplication |
| KPI dashboard | total paid | distinguish `gross`, `discount`, `payable` | Update labels and metric owners |
| ETL/CDC | reads price and quantity | reads discount + version | Retries, late data, backfill |
| Monitoring | no discount check | reconcile `gross − discount = payable` | Thresholds and alerts |

Beyond new columns, audit every **write path**: web checkout, mobile apps, order import batches, order-edit jobs, admin tools, message listeners, and ops scripts. If a legacy writer still recomputes total from `quantity × unitPrice` and overwrites an order after a new writer applied a discount, data corrupts even though `ALTER TABLE` succeeded.

### Compatibility matrix across rollout phases

| Component | Legacy schema | Expanded schema, discount off | Discount data present |
| --- | --- | --- | --- |
| **Old application** | Works | Continues if new columns are nullable/defaulted and old field meanings stay intact | **Unsafe** if old writer edits a discounted order using legacy logic |
| **New application** | Can fail querying missing columns | Works after ordered deployment | Works under new invariants |
| **Old event consumer** | Reads v1 | Reads v1 per contract | Safe only while `totalVnd` retains its promised meaning |
| **New event consumer** | Lacks breakdown data | Receives v2 or adapter with valid defaults | Processes breakdown with proper version |
| **Old report** | Total = gross = payable | Remains accurate while discount=0 | Must review **labels and formulas**; never call it gross |

The safe rollout path is usually **expanding storage first**, upgrading all critical writers to understand the new columns, reconciling, and **only then enabling discounts**. This is a **data-level feature gate**, not merely a UI toggle: hiding a discount button from users does not stop batch jobs or other APIs from writing discounts.

## 4. New Java model: invariants belong to domain behavior

The Java 17 snippet below expresses the calculation and guards state. It contains no SQL, REST, or Kafka logic.

~~~java
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

record OrderLine(
        int lineNo, UUID skuId, int quantity,
        long unitPriceVnd, long discountPerUnitVnd) {
    OrderLine {
        Objects.requireNonNull(skuId);
        if (lineNo <= 0 || quantity <= 0
                || unitPriceVnd < 0
                || discountPerUnitVnd < 0
                || discountPerUnitVnd > unitPriceVnd) {
            throw new IllegalArgumentException("Invalid order line");
        }
    }

    long grossVnd() {
        return Math.multiplyExact((long) quantity, unitPriceVnd);
    }

    long discountVnd() {
        return Math.multiplyExact(
            (long) quantity, discountPerUnitVnd);
    }

    long payableVnd() {
        return Math.subtractExact(grossVnd(), discountVnd());
    }
}

record OrderAmounts(long grossVnd, long discountVnd, long payableVnd) {
    OrderAmounts {
        if (grossVnd < 0 || discountVnd < 0
                || discountVnd > grossVnd
                || payableVnd != grossVnd - discountVnd) {
            throw new IllegalArgumentException("Invalid amounts");
        }
    }
}

enum OrderState { DRAFT, PAID, CANCELLED }

record PaymentEvidence(UUID captureId, long capturedVnd, Instant capturedAt) {
    PaymentEvidence {
        Objects.requireNonNull(captureId);
        Objects.requireNonNull(capturedAt);
        if (capturedVnd < 0) throw new IllegalArgumentException("amount");
    }
}

record OrderPaid(
        UUID eventId, UUID orderId, long aggregateVersion,
        Instant occurredAt, OrderAmounts amounts, UUID captureId) {}

final class SalesOrder {
    private final UUID orderId;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderState state = OrderState.DRAFT;
    private long version;

    SalesOrder(UUID orderId) {
        this.orderId = Objects.requireNonNull(orderId);
    }

    void addLine(OrderLine line) {
        if (state != OrderState.DRAFT) {
            throw new IllegalStateException("Order not editable");
        }
        Objects.requireNonNull(line);
        if (lines.stream().anyMatch(x -> x.lineNo() == line.lineNo())) {
            throw new IllegalArgumentException("Duplicate line number");
        }
        // Pre-check new totals for overflow before mutating state.
        Math.addExact(amounts().grossVnd(), line.grossVnd());
        Math.addExact(amounts().discountVnd(), line.discountVnd());
        Math.addExact(amounts().payableVnd(), line.payableVnd());
        lines.add(line);
        version++;
    }

    OrderAmounts amounts() {
        long gross = 0, discount = 0;
        for (OrderLine line : lines) {
            gross = Math.addExact(gross, line.grossVnd());
            discount = Math.addExact(discount, line.discountVnd());
        }
        return new OrderAmounts(
            gross, discount, Math.subtractExact(gross, discount));
    }

    OrderPaid recordCapturedPayment(UUID eventId, PaymentEvidence evidence) {
        if (state != OrderState.DRAFT || lines.isEmpty()) {
            throw new IllegalStateException("Order cannot be paid");
        }
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(evidence);
        OrderAmounts total = amounts();
        if (evidence.capturedVnd() != total.payableVnd()) {
            throw new IllegalStateException("Captured amount mismatch");
        }
        state = OrderState.PAID;
        version++;
        return new OrderPaid(
            eventId, orderId, version, evidence.capturedAt(),
            total, evidence.captureId());
    }

    List<OrderLine> lines() { return List.copyOf(lines); }
    UUID id() { return orderId; }
    OrderState state() { return state; }
    long version() { return version; }
}
~~~

This `Order` example uses **PaymentCaptured evidence supplied by an authoritative Payment context**; never trust an arbitrary `capturedVnd` sent by a client. Production systems must verify source authenticity, tenant authorization, `captureId` deduplication, payment/order linkage, and timeouts. Returning `OrderPaid` here creates only an **in-memory domain event**; the integration event must be persisted only when the corresponding business transaction commits.

### Java responsibilities differ from schema responsibilities

- Constructors/value objects enforce **single-line** conditions.
- The aggregate computes totals and controls state transitions; callers cannot directly set totals.
- Repositories must rehydrate saved state **without re-invoking `addLine` or `recordCapturedPayment`** to simulate history, as doing so increments versions and triggers side effects.
- Use `Math.multiplyExact/addExact/subtractExact` to catch integer overflow. If business amounts can exceed `long` range, use `BigDecimal`/`NUMERIC` with agreed units and precision.
- The application service retains `originalVersion` upon loading, enforces optimistic concurrency in the DB, and maps `OrderPaid` to the integration contract.

Correct Java arithmetic does not replace database checks under **concurrent requests or alternate SQL write paths**.

## 5. Legacy model and new storage target

Suppose the OLTP source uses PostgreSQL; minimal legacy schema:

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.order_header (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL
        CHECK (status IN ('DRAFT', 'PAID', 'CANCELLED')),
    total_vnd BIGINT NOT NULL CHECK (total_vnd >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    paid_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, order_id),
    CHECK (status <> 'PAID' OR paid_at IS NOT NULL)
);

CREATE TABLE sales.order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sku_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.order_header (tenant_id, order_id)
);
~~~

The new requirement **does not force immediately renaming `total_vnd`**. Keeping it as **payable amount** allows old apps to keep reading under the existing contract. Add:

- `order_line.discount_per_unit_vnd`, defaulting to 0 for legacy rows.
- `order_header.gross_total_vnd` and `discount_total_vnd` for reconciliation and hot queries.
- Total check: `gross − discount = total_vnd`.
- Once `PAID`, finalized prices and discounts must stay immutable per policy; fixes go through controlled adjustments/corrections rather than silently mutating history.

Use **meaning-explicit measure names**: `grossTotalVnd`, `discountTotalVnd`, `payableTotalVnd`. While keeping `totalVnd` for compatibility, docs and mappers must stipulate **`totalVnd = payableTotalVnd`**, never leaving each module to guess.

## 6. Expand: adding schema changes that tolerate legacy versions

An illustrative **EXPAND** phase migration:

~~~sql
-- Run under versioned schema migration management.
-- Verify locks, permissions, and actual deployment impact before production.

ALTER TABLE sales.order_line
    ADD COLUMN discount_per_unit_vnd BIGINT DEFAULT 0;

ALTER TABLE sales.order_header
    ADD COLUMN gross_total_vnd BIGINT,
    ADD COLUMN discount_total_vnd BIGINT;

-- CHECK NOT VALID avoids scanning all legacy data on constraint creation.
-- PostgreSQL still validates newly INSERTed/UPDATEd rows.
ALTER TABLE sales.order_line
    ADD CONSTRAINT ck_discount_per_unit
    CHECK (
        discount_per_unit_vnd IS NOT NULL
        AND discount_per_unit_vnd >= 0
        AND discount_per_unit_vnd <= unit_price_vnd
    ) NOT VALID;

-- Both total columns remain nullable during transition.
ALTER TABLE sales.order_header
    ADD CONSTRAINT ck_order_amount_breakdown
    CHECK (
        (gross_total_vnd IS NULL AND discount_total_vnd IS NULL)
        OR
        (
            gross_total_vnd IS NOT NULL
            AND discount_total_vnd IS NOT NULL
            AND gross_total_vnd >= 0
            AND discount_total_vnd >= 0
            AND discount_total_vnd <= gross_total_vnd
            AND gross_total_vnd - discount_total_vnd = total_vnd
        )
    ) NOT VALID;
~~~

**Why not enforce NOT NULL on all new columns immediately?** Un-backfilled legacy header rows lack gross/discount; enforcing too early blocks deployment. On `order_line`, `DEFAULT 0` gives legacy rows a valid "no discount" meaning and lets old writers INSERT without specifying the new column; any app explicitly trying to INSERT `NULL` is still blocked by the `CHECK`.

**PostgreSQL note:** `NOT VALID` on a `CHECK` skips scanning existing rows at creation, yet **newly inserted or updated rows must satisfy the CHECK**. Adding columns/defaults and running `VALIDATE CONSTRAINT` have engine- and version-specific locking behaviors; test against your actual PostgreSQL version and data scale rather than assuming every `ALTER TABLE` is zero-downtime.

During expand, **the discount feature remains disabled**. Old writers unaware of discounts can still write with `discount=0`; only once required writers, readers, and pipelines have upgraded should discounts > 0 be enabled. Check old code for column-less `INSERT`s, `SELECT *` positional mapping, or auto-serializers—such habits can break compatibility even when new columns are nullable.

## 7. Backfill: bringing legacy data into the new semantics

A core rule: **having no discounts before the feature existed** does not mean new columns can stay `NULL` forever. Valid legacy orders satisfy:

\[
\text{discount}=0,\quad
\text{gross}=\text{legacy total},\quad
\text{payable}=\text{legacy total}.
\]

Every backfill must be **safely re-runnable**, checkpointed, progress-monitored, and incapable of overwriting valid updates from the new application.

### 7.1. Backfilling immutable PAID orders

Suppose the domain contract guarantees that orders **PAID** before the feature rolled out do not undergo normal line edits. Then gross can be recomputed from `OrderLine` with `discount=0`. Example SQL for a controlled slice:

~~~sql
WITH line_sums AS (
    SELECT l.tenant_id, l.order_id,
           SUM(l.quantity::NUMERIC * l.unit_price_vnd) AS gross,
           SUM(
               l.quantity::NUMERIC
               * COALESCE(l.discount_per_unit_vnd, 0)
           ) AS discount
    FROM sales.order_line AS l
    JOIN sales.order_header AS o
      ON o.tenant_id = l.tenant_id
     AND o.order_id = l.order_id
    WHERE o.status = 'PAID'
      AND o.gross_total_vnd IS NULL
      AND o.tenant_id = :tenant_id
    GROUP BY l.tenant_id, l.order_id
)
UPDATE sales.order_header AS o
SET gross_total_vnd = s.gross,
    discount_total_vnd = s.discount
FROM line_sums AS s
WHERE o.tenant_id = s.tenant_id
  AND o.order_id = s.order_id
  AND o.status = 'PAID'
  AND o.gross_total_vnd IS NULL
  AND s.gross - s.discount = o.total_vnd;
~~~

**This illustrates logic, not a complete production backfill.** It intentionally **never alters `total_vnd`** to hide source inconsistencies. If `gross − discount` differs from the legacy total, the row is skipped and must land in a discrepancy report. If `gross` exceeds `BIGINT` range, raise an error/investigate instead of truncating; using `NUMERIC` inside `SUM` catches sums overflowing target bounds. `PAID` data is safe to backfill this way only if truly **immutable** under the source write protocol.

For `DRAFT` or still-editable orders, a different strategy is required:

- All writers must **lock the Order root** before editing lines.
- Backfill each Order inside a transaction, reading lines/versions under the same locking protocol.
- Avoid reading stale lines and updating summaries after another writer modified them.
- Or schedule a brief write-freeze window if product and SLA allow.

At scale, backfill must batch by stable keys (keyset/chunk), checkpoint, throttle locks/I/O, handle retries per error class, and track expected counts. Never run an unbounded `UPDATE` over tens of millions of orders during peak hours assuming OLTP latency will stay unaffected.

### 7.2. SQL query to detect header-vs-line discrepancies

~~~sql
WITH sums AS (
    SELECT tenant_id, order_id,
           SUM(quantity::NUMERIC * unit_price_vnd) AS gross,
           SUM(quantity::NUMERIC *
               COALESCE(discount_per_unit_vnd, 0)) AS discount
    FROM sales.order_line
    WHERE tenant_id = :tenant_id
    GROUP BY tenant_id, order_id
)
SELECT o.order_id, o.status, o.total_vnd,
       o.gross_total_vnd, o.discount_total_vnd,
       s.gross AS recomputed_gross,
       s.discount AS recomputed_discount,
       s.gross - s.discount AS recomputed_payable
FROM sales.order_header AS o
LEFT JOIN sums AS s
  ON s.tenant_id = o.tenant_id AND s.order_id = o.order_id
WHERE o.tenant_id = :tenant_id
  AND (
      s.order_id IS NULL
      OR o.gross_total_vnd IS NULL
      OR o.discount_total_vnd IS NULL
      OR o.gross_total_vnd IS DISTINCT FROM s.gross
      OR o.discount_total_vnd IS DISTINCT FROM s.discount
      OR o.total_vnd IS DISTINCT FROM (s.gross - s.discount)
  );
~~~

This query **assumes every Order has at least one line**, including `DRAFT`s. If the domain allows temporarily empty `DRAFT`s, classify them separately rather than flagging all empty `DRAFT`s as errors. It can also be resource-intensive: run against a read replica/consistent snapshot or in batches aligned to the authoritative cutoff; never treat an inconsistent point-in-time read during active writes as definitive proof of errors.

### 7.3. Tightening constraints once data and writers are ready

~~~sql
-- Run ONLY after backfill and reconciliation PASS.
ALTER TABLE sales.order_line
    VALIDATE CONSTRAINT ck_discount_per_unit;

ALTER TABLE sales.order_header
    VALIDATE CONSTRAINT ck_order_amount_breakdown;

-- Next step only once ALL headers, including DRAFT, carry breakdowns.
ALTER TABLE sales.order_header
    ADD CONSTRAINT ck_amount_breakdown_present
    CHECK (
        gross_total_vnd IS NOT NULL
        AND discount_total_vnd IS NOT NULL
    ) NOT VALID;

-- Do not run yet if legacy writers still insert headers missing breakdowns.
ALTER TABLE sales.order_header
    VALIDATE CONSTRAINT ck_amount_breakdown_present;

-- Consider ALTER COLUMN SET NOT NULL in a separate CONTRACT step,
-- after verifying locking behavior on your exact engine/version.
~~~

**Ordering is part of correctness.** A passing `VALIDATE` does not prove legacy writers stopped omitting the new columns if the constraint still permits `NULL`. Before forbidding `NULL` writes, ensure **every writer supports the columns** (or uses a compatibility-tested default/trigger). For new columns lacking a valid universal default, never fill `0` merely to make a migration pass.

## 8. Syncing Java ↔ SQL write paths across coexisting versions

An old writer unaware of discounts might load an `Order` and rewrite all `OrderLine`s with default discount `0`. Once discounted orders exist, that causes **lost business meaning**, not just a lost update. Therefore block old writers from modifying orders created or updated under the new model.

Typical rollout strategy:

1. Deploy the expanded schema.
2. Deploy new Java with mappers that understand legacy rows: transitional `NULL` maps to `0` **only when the legacy contract proves zero discounts existed**.
3. Deploy all **command writers**, batches, admin tools, imports, and related services.
4. Enable `discount > 0` writes only after verifying no legacy write path remains that could corrupt data.
5. For discounted orders, enforce a shared version/lock protocol across all mutations.

**Never do uncoordinated dual-writes**: writing an `Order` to two schemas/databases simultaneously and hoping both stay identical. If one write succeeds and the other times out, two competing sources of truth emerge. When moving data across stores, establish one authoritative source and update direction; CDC/outbox, checkpoints, replay, and reconciliation are far easier to control than one request writing independently to two stores.

### Payment transition and outbox in the same commit

Once the `Payment` context supplies valid capture evidence, `Sales` transitions the `Order` to `PAID` and records the integration event inside a **local transaction**:

~~~sql
CREATE TABLE IF NOT EXISTS sales.order_outbox (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    order_version BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.order_header (tenant_id, order_id)
);

BEGIN;

UPDATE sales.order_header
SET status = 'PAID',
    paid_at = :captured_at,
    total_vnd = :payable_vnd,
    gross_total_vnd = :gross_vnd,
    discount_total_vnd = :discount_vnd,
    version = :new_version
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND status = 'DRAFT'
  AND version = :expected_version
  AND :new_version > :expected_version
  AND :gross_vnd >= :discount_vnd
  AND :payable_vnd = :gross_vnd - :discount_vnd
RETURNING version;

-- If not exactly 1 row returned: ROLLBACK, do not write event.
-- OrderLines must match gross/discount and be protected in the
-- same transaction under the same root-locking protocol.

INSERT INTO sales.order_outbox (
    event_id, tenant_id, order_id, order_version,
    event_type, schema_version, occurred_at, payload
) VALUES (
    :event_id, :tenant_id, :order_id, :new_version,
    'sales.order-paid', 2, :captured_at,
    jsonb_build_object(
        'orderId', :order_id,
        'grossVnd', :gross_vnd_text,
        'discountVnd', :discount_vnd_text,
        'payableVnd', :payable_vnd_text,
        'currency', 'VND'
    )
);

COMMIT;
~~~

This transaction illustrates **a single `DRAFT → PAID` transition** in a simplified system. It assumes lines are already stored accurately and all line mutations obey root locking/versioning. If line changes must be saved in the same command, do so inside this same transaction. The application must inspect the returned row count and conditions before `COMMIT`; SQL does not automatically `ROLLBACK` just because an `UPDATE` matched 0 rows.

Because **Payment** owns its own authoritative source, `Sales` must verify `captureId`, `amount`, `orderId`, `tenant`, and idempotency of the payment result. Committing in `Sales` does not mean it shared an ACID transaction with the payment gateway.

**Domain and storage changes must commit together atomically**, while broker publishing can happen asynchronously via the outbox. The relay may republish after a crash between send and marking `published_at`, so consumers need deduplication. When retrying a `PAID` command, never mint a new `eventId` for an already-committed fact and publish it as a second payment.

## 9. Event contract: from `OrderPaidV1` to `OrderPaidV2`

Old published contract:

~~~json
{
  "eventId": "2ef6d3b4-809e-4a44-95fa-f2d1c1e15470",
  "eventType": "sales.order-paid",
  "schemaVersion": 1,
  "tenantId": "517da76b-b642-4842-84db-17f4b54c9203",
  "aggregateId": "038b3e41-894a-410e-899e-25fb5e22cf30",
  "aggregateVersion": 6,
  "occurredAt": "2026-11-01T09:00:00Z",
  "payload": {
    "orderId": "038b3e41-894a-410e-899e-25fb5e22cf30",
    "totalVnd": "250000"
  }
}
~~~

**Promised semantics:** `totalVnd` is **the payable/paid amount for the order's items**, not pre-discount list value. Since this order had no discount, `payable = 250,000`.

New contract:

~~~json
{
  "eventId": "448ce62a-0e46-41ab-b88b-979fd4908548",
  "eventType": "sales.order-paid",
  "schemaVersion": 2,
  "tenantId": "517da76b-b642-4842-84db-17f4b54c9203",
  "aggregateId": "b1c06314-3994-4396-a43d-6785a177edfa",
  "aggregateVersion": 9,
  "occurredAt": "2026-11-22T09:00:00Z",
  "payload": {
    "orderId": "b1c06314-3994-4396-a43d-6785a177edfa",
    "grossVnd": "250000",
    "discountVnd": "20000",
    "payableVnd": "230000",
    "currency": "VND"
  }
}
~~~

**These illustrate two events from two different Orders**, not the same `eventId` re-emitted with differing payloads. `schemaVersion` identifies the **payload contract**, while `aggregateVersion` identifies the **Order state version**. They evolve independently.

### Consumer migration plan

- **Consumer v1:** expects a contract carrying `totalVnd` meaning payable. While still supported, an adapter can project v2 events down to v1 with **`totalVnd = payableVnd`**, preserving promised semantics.
- **Consumer v2:** uses `grossVnd`, `discountVnd`, and `payableVnd` for reports or workflows needing a breakdown; must validate currency and consistency.
- **Migrating consumers:** may read v1 and v2 via versioned adapters/upcasters, yet **must never assume `gross = payable, discount = 0` for newly discounted transactions** from a v1 payload alone. If a breakdown is required, query the authoritative source or report unknown/missing data.

If publishing **both v1 and v2 projections for the same fact** during transition, specify which topic/consumer reads which, provide a shared **`logicalOccurrenceId`** or proper dedup rule, and ensure reports never double-count both as two `OrderPaid` occurrences. An easier-to-control design keeps **one canonical event in the outbox**, with a compatibility layer translating onto a v1 channel for specific subscribers until they upgrade.

### Compatibility is more than adding/removing fields

| Event change | Potentially compatible? | Notes |
| --- | --- | --- |
| Add optional field with clear semantic default | Usually yes | Consumers must ignore unknown fields |
| Rename `totalVnd` to `payableVnd` and drop old field | No for v1 consumers reading old field | Needs new version or adapter |
| Change `totalVnd` from payable to gross under same name | **No** | Semantic bug even if schema validates |
| Change whole VND to thousands of VND | **No** | Monetary amounts wrong by 1,000× |
| Add new status enum | Depends on contract | Legacy clients/consumers may fail exhaustive switches |
| Change `eventId` on broker redelivery | Unsafe | Breaks dedup, multiplies side effects |
| Use `aggregateVersion` as `schemaVersion` | Conceptual error | Loses independent versioning |

**A schema registry only guards part of structural compatibility.** An event keeping identical JSON structure while changing meaning from "paid" to "payment authorized" is a breaking business change no schema validator catches.

## 10. Replay, CDC, ordering, and consumer idempotency

When a new consumer rebuilds a projection from history, the questions go beyond "are messages still in the broker?":

1. **Are enough v1/v2 events retained across the rebuild window?**
2. **Does the consumer have adapters decoding every historical version?**
3. **Does v1 data hold enough info for gross/discount, or only payable?**
4. **When corrections/refunds occurred, which events reverse or adjust metrics?**
5. **Will replaying re-send emails, charges, or external side effects?**

An application consumer can guard itself with an inbox key:

~~~sql
CREATE SCHEMA IF NOT EXISTS integration;

CREATE TABLE integration.processed_event (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);

-- Start consumer's local transaction:
-- INSERT processed_event(...); if key already exists, treat as processed.
-- If new, update consumer's projection / aggregate in the
-- same transaction; ACK broker only after commit succeeds.
~~~

If v1 and v2 versions express the same business occurrence using **different `eventId`s**, this table does not prevent double counting by itself. You must key by **`logicalOccurrenceId`** or restrict each consumer to one canonical stream. For external side effects outside the transaction (emails, payment gateways), destination-side idempotency or reconciliation is also needed.

**CDC row change ≠ domain event.** Seeing an `UPDATE` whose sole purpose was backfilling `gross_total_vnd` does not mean a new payment occurred. A pipeline consuming physical changes must distinguish:

- schema/backfill updates;
- real business state transitions;
- corrective data repairs;
- redeliveries of the same change.

Never treat every `UPDATE` on `order_header` as an `OrderPaid` trigger or revenue increment.

**Ordering:** `aggregateVersion` applies strictly within one Order, and versions can increment on changes **that do not emit `OrderPaid`**. Consumers must not assume versions 1, 2, 3... are consecutive events of the same event type. Where ordering matters, rely on authoritative stream sequences, snapshot contracts, and gap detection; wall-clock timestamps do not establish global order.

## 11. Reporting: evolving facts and metrics at the right grain

The analytics path must keep these questions distinct:

- **Gross goods value:** sum of `quantity × unitPrice` across eligible lines.
- **Discount given:** sum of `quantity × discountPerUnit`.
- **Net paid goods value:** `gross − discount` for lines belonging to `PAID` Orders per contract.
- **Payment captured:** authoritative result from `Payment`, which may differ in timing or unit from line recognition.
- **Refund:** actual refunded amounts, requiring their own fact/rules.
- **Accounting revenue:** may depend on fulfillment, performance obligations, taxes, and accounting standards; never equate blindly with any single metric above.

Suppose each `PAID` Order means **the entire order item value was captured exactly once**, excluding taxes/fees/cancellations/refunds. We choose a fact at grain:

> **One row = one `OrderLine` of a `PAID` Order**, keyed by `(tenantId, orderId, lineNo)`, carrying price snapshot at sale time, `gross/discount/net` measures, and `paidAt`.

Example fact table:

~~~sql
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE mart.fact_paid_order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL,
    sku_id UUID NOT NULL,
    paid_at TIMESTAMPTZ NOT NULL,
    paid_date DATE NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
    discount_per_unit_vnd BIGINT NOT NULL
        CHECK (discount_per_unit_vnd >= 0),
    gross_vnd BIGINT NOT NULL CHECK (gross_vnd >= 0),
    discount_vnd BIGINT NOT NULL CHECK (discount_vnd >= 0),
    net_paid_vnd BIGINT NOT NULL CHECK (net_paid_vnd >= 0),
    source_order_version BIGINT NOT NULL,
    transform_version INTEGER NOT NULL,
    load_batch_id UUID NOT NULL,
    PRIMARY KEY (tenant_id, order_id, line_no),
    CHECK (discount_per_unit_vnd <= unit_price_vnd),
    CHECK (discount_vnd <= gross_vnd),
    CHECK (gross_vnd - discount_vnd = net_paid_vnd)
);

CREATE INDEX fact_paid_line_by_date
    ON mart.fact_paid_order_line (tenant_id, paid_date, sku_id);
~~~

**This is an illustrative target schema**, not necessarily a direct `ALTER` on an already populated warehouse table. In real migrations, expand facts / preserve old views, backfill history, and migrate BI gradually. If partial captures or multiple settlements occur per `OrderLine`, a grain of **one paid line** no longer fits: consider a **capture allocation** fact with its own key instead. Never add columns while keeping a primary key that no longer represents the grain of the fact.

### Updating metrics to reflect true meaning

~~~sql
SELECT paid_date,
       SUM(gross_vnd) AS gross_goods_vnd,
       SUM(discount_vnd) AS discount_given_vnd,
       SUM(net_paid_vnd) AS net_paid_goods_vnd,
       COUNT(DISTINCT order_id) AS paid_orders
FROM mart.fact_paid_order_line
WHERE tenant_id = :tenant_id
  AND paid_date >= DATE '2026-11-01'
  AND paid_date <  DATE '2026-12-01'
GROUP BY paid_date
ORDER BY paid_date;
~~~

**`COUNT(DISTINCT order_id)`** counts Orders per day within the tenant; an Order with two lines counts as **one Order**, not two. If one Order has lines spanning multiple payment dates, review grain/cutoff conventions. `paid_date` must use a **consistent business timezone/cutoff**, never arbitrary CDC ingest dates.

### Never just relabel a dashboard and call it done

If an old report labeled "Sales" actually measured **`totalVnd = payable`**, once discounts arrive you must:

- Keep the legacy metric as **net paid goods value** and update labels/documentation clearly.
- Add the new **gross goods value** metric from unit price snapshots without assuming `gross = net` post-launch.
- Report `discount = gross − net` and reconcile sums at each grain.
- If **accounting revenue** is needed, integrate the proper recognition source and tax/refund/fulfillment rules; never rename `net_paid` to `revenue`.

For periods prior to discount launch, backfilling `discount = 0` is valid only if **legacy policy truly had zero discounts**; if external vouchers existed outside `OrderLine`, **filling 0 is false**. Document legacy completeness in metadata/quality flags.

## 12. Coordinating fact, dimension, and pipeline evolution

Suppose BI reads a legacy fact table having only `paid_amount_vnd`. A compatible plan:

1. **Expand fact:** add nullable `gross_vnd`, `discount_vnd`, `net_paid_vnd`; do not break legacy queries.
2. **Build transform v2:** source price/discount snapshots from `Sales` or `OrderPaidV2` per contract; where breakdowns are absent, fetch from supplementary sources or flag incomplete.
3. **Historical backfill:** write by key `(tenantId, orderId, lineNo)` carrying `sourceVersion`, `transformVersion`, and `loadBatchId` for audit/reprocessing.
4. **Reconcile:** total net in fact v2 must equal total paid in source for the same period/definition. `Gross − discount` must equal `net` on every row and group.
5. **Run parallel dashboards:** compare old and new metrics on identical cutoffs; do not expect new gross to equal old net once discounts start.
6. **Switch semantic layer:** repoint dashboard queries to explicitly named fields; version metrics and record the effective switch date.
7. **Contract:** drop legacy fact fields only once zero jobs/BI queries reference them and recovery paths exist.

### Late-arriving data and retroactive corrections

`OrderPaid` events may reach the warehouse days after payment; group them by the defined **`paidAt`**, not consumer arrival time. If the source corrects a discount due to an incident or refund, enforce a clear policy:

- **Correction/restatement:** update the properly grained fact and dependent summaries, publishing a new metric version/cutoff.
- **Adjustment fact:** record a separate adjusting entry, avoiding double-adjusting both old numbers and adjustments.
- **Refund event/fact:** a refund row has its own `refundId` and timestamp, never turning one `OrderPaid` into two sales.

With SCD Type 2 for SKUs/categories or segments, facts must link to the **dimension version effective at transaction time** or store an appropriate snapshot. Re-categorizing a product today does not mean rewriting historical transactions. Changing monetary metrics and changing historical categorization are distinct semantic changes requiring separate tests.

### Rebuilds must not duplicate rows

Fact backfills re-running must **MERGE/UPSERT** by the stable grain key, never `INSERT` duplicate copies that get `SUM`med together. Generating a fresh `loadId` on every replay and placing it in the business key creates phantom revenue. `loadBatchId` serves lineage only, **never replacing the fact's business key**.

## 13. Deployment order: never force the whole system to upgrade at once

In practice, multiple app replicas, long-running batches, external-team consumers, and cached dashboards coexist. A change is safe only when **every version pair that can interact during rollout** has been verified.

~~~mermaid
flowchart TB
    A["1. Lock semantic contract<br/>and impact matrix"]
    B["2. Expand schema<br/>nullable/default columns, constraints"]
    C["3. Upgrade Java writers/readers<br/>discount still disabled"]
    D["4. Backfill + reconciliation<br/>and compatibility checks"]
    E["5. Publish event v2<br/>consumer upgrades/adapters"]
    F["6. Upgrade fact + BI pipeline<br/>shadow comparison"]
    G["7. Feature gate ON<br/>allow discount > 0"]
    H["8. Monitor, tune<br/>and contract legacy schema"]
    A --> B --> C --> D --> E --> F --> G --> H
~~~

This sequence is **one viable plan**, not a rigid law for all systems. Event v2 can go live before every consumer migrates if adapters exist and legacy consumers keep receiving the old contract. However, **never turn on a feature producing new data before critical writers understand it**.

### Stage gates across phases

| Phase | Minimum exit criteria to proceed |
| --- | --- |
| Lock semantics | Owners of Sales, Payment, Analytics, and consumers confirm what `totalVnd` means |
| Expand storage | Old/new code tested against expanded schema; schema rollback planned |
| Deploy Java | Zero legacy writers remain able to edit discounted orders; APIs/batches support new fields |
| Backfill | Null counts within threshold; financial discrepancies resolved |
| Events | Producer/consumer contract tests PASS; zero double-counting across v1/v2 |
| Fact/reports | `Gross − discount = net`; parallel dashboards align on proper metrics |
| Enable feature | Safe kill-switch ready; dashboards and monitors recognize discount data |
| Contract | Zero dependencies on legacy fields; historical storage/reads verified |

A feature sometimes spans **several application deployments yet only one semantic transition**. For example, all orders keep `discount=0` until writers are proven upgraded. Upgrading Java code and enabling discount business behavior do not need to occur simultaneously.

### Scoped and time-bounded feature flags

If the feature is enabled only for tenant A:

- Validate tenant identity on every server command; never trust a client-supplied `tenantId` field blindly.
- Legacy writers in tenant B still emit `discount=0`, while the schema supports both.
- Multi-tenant reports must know each tenant's discount effective date.
- When turning a flag off, **never try to force already-discounted orders back into the old state**; the flag only blocks creating new discounted orders or routes to controlled handling.

## 14. Rollback and roll-forward: can old code read new data?

**Rolling back the application after discounted orders exist** is completely different from rolling back before enabling the feature:

| Incident timing | Viable rollback approach | What must NOT be done |
| --- | --- | --- |
| Schema expanded only; no `discount > 0` yet | Usually safe to run old app temporarily if compat tests PASS | Rush to `DROP` columns while new builds still query them |
| New Java deployed, feature still off | Disable feature / roll back app logic if compat with schema holds | Ignore batch writers or consumers |
| Orders with `discount > 0` already created | **Prefer roll-forward/hotfix or safe read-only guard** | Let old writers recompute `payable = original gross` |
| Event v2 published; old consumer failing | Route via adapter/versioning; pause consumer and replay | Mint a new event for the same business occurrence to "resend" |
| Fact/report formula wrong | Halt official KPI publication; rebuild with new version and reconcile | Silently tweak totals without an audit trail |

If the old binary cannot understand or preserve stored discounts, rolling back that binary can **corrupt data**. A safer move is halting discount writes, shipping a forward-compatible hotfix, or putting affected flows into selective read-only mode. Never treat rollback as merely swapping a container image tag.

### Contracting the schema after new data exists

Drop legacy columns/fields only once:

1. All writers and readers use the new representation.
2. V1 consumers have migrated or run through SLA-backed adapters.
3. Historical backfill/rebuild is verified and legacy reports remain readable.
4. Backup, restore, replay, and rollback procedures fit the contracted schema.
5. External queries, views, exports, admin scripts, and BI tools are audited.
6. A maintenance window, error monitoring, and an explicit owner approving breaking compatibility are in place.

**Never run `DROP COLUMN total_vnd` simply because the Java class no longer has that field.** As long as reporting tools or external consumers depend on the old contract, dropping it is a breaking change.

## 15. Multi-layer synchronization testing

Unit tests checking Java getters and setters are insufficient. Each layer needs its own evidence, and layers must be **reconciled against one another**.

### 15.1. Domain unit tests: values, invariants, versions

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class OrderEvolutionTest {
    @Test
    void oldOrderWithZeroDiscountKeepsOldTotalMeaning() {
        var line = new OrderLine(1, UUID.randomUUID(), 2, 100_000, 0);
        assertEquals(200_000, line.grossVnd());
        assertEquals(0, line.discountVnd());
        assertEquals(200_000, line.payableVnd());
    }

    @Test
    void discountedLinesMaintainGrossMinusDiscountEqualsPayable() {
        var order = new SalesOrder(UUID.randomUUID());
        order.addLine(new OrderLine(1, UUID.randomUUID(), 2, 100_000, 10_000));
        order.addLine(new OrderLine(2, UUID.randomUUID(), 1, 50_000, 0));

        var totals = order.amounts();
        assertEquals(250_000, totals.grossVnd());
        assertEquals(20_000, totals.discountVnd());
        assertEquals(230_000, totals.payableVnd());
    }

    @Test
    void discountCannotExceedUnitPrice() {
        assertThrows(IllegalArgumentException.class,
            () -> new OrderLine(1, UUID.randomUUID(), 1, 100_000, 100_001));
    }

    @Test
    void capturedAmountMustMatchPayable() {
        var order = new SalesOrder(UUID.randomUUID());
        order.addLine(new OrderLine(1, UUID.randomUUID(), 1, 100_000, 10_000));
        var evidence = new PaymentEvidence(
            UUID.randomUUID(), 100_000, Instant.parse("2026-11-22T09:00:00Z"));
        assertThrows(IllegalStateException.class,
            () -> order.recordCapturedPayment(UUID.randomUUID(), evidence));
        assertEquals(OrderState.DRAFT, order.state());
    }
}
~~~

These tests verify only the **in-memory** model. To guarantee real data never corrupts under concurrency, run integration tests against the actual storage engine rather than mocking repositories.

### 15.2. End-to-end data-path test matrix

| Test | Target | Expected outcome |
| --- | --- | --- |
| Java old line `discount=0` | Legacy data compatibility | `payable=gross`, `totalVnd` meaning preserved |
| Java new line `discount>0` | New formula and invariants | `gross − discount = payable` |
| Negative/excess discount or `long` overflow | Invalid inputs | Rejected before persistence |
| Old app `INSERT` into expanded schema | Migration compatibility | `discount` defaults to 0; no mapper crash |
| Old app attempts `UPDATE` on discounted order | Preventing stale overwrite | Blocked/gated; discounts preserved |
| Re-running backfill | Idempotency | Totals unchanged; already-processed rows untouched |
| Backfill hits missing lines / mismatched totals | Data quality | Quarantined/alerted; never mutates `total` to mask bug |
| Two `PAID` commands with same `expectedVersion` | Concurrency | At most one transaction commits |
| Header update succeeds yet outbox insert fails | Transaction | Entire transaction including header rolls back |
| Broker redelivers identical `eventId` | Consumer idempotency | No duplicate revenue or side effects |
| Consumer v1 handles event v2 via adapter | Compatibility | `totalVnd` remains payable |
| Same occurrence routed across two versions | Double counting | Business occurrence counted once |
| Old event replayed after discount launch | Historical accuracy | Never invents gross for events lacking breakdown |
| Old/new dashboards on `discount=0` data | Parallel run | Net metrics match at identical cutoff |
| Dashboard with discounts | Metric definition | `Gross` exceeds `net` by exact `discount` |
| Late-arriving event | Business date | Bucketed by `paidAt`, not `ingestAt` |
| Tenant B accesses Tenant A's Order | Security | Denied; zero data leakage |
| Binary rollback after enabling discounts | Data safety | Legacy writer blocked from corrupting data |

### 15.3. Property-based and reconciliation tests

Beyond fixed cases, generate varied valid lines with quantity, price, and discount and assert:

\[
\forall\ \text{valid order}:\
\text{gross}\ge\text{discount}\ge0,\quad
\text{payable}=\text{gross}-\text{discount}\ge0.
\]

Verify invariants across boundaries:

~~~text
Java amounts()           = persisted header breakdown
Persisted order lines    = persisted header breakdown
Committed OrderPaidV2    = persisted Order state at event version
Analytics paid-line fact = committed source OrderLine snapshots
BI net-paid metric       = SUM(valid fact.net_paid_vnd)
~~~

Not every pair can be joined in one synchronous transaction—especially an eventually consistent warehouse. Reconcile across **matching tenant, business date, currency, cutoff/watermark, and `sourceVersion`**, documenting acceptable lag. Differences caused by late data must be classified, never ignored or patched directly in dashboards to make numbers look right.

## 16. Operational observability and post-deployment incident debugging

A migration does not end when `ALTER TABLE` succeeds. Monitor **both invariants and data flow**:

| Signal | Why it matters |
| --- | --- |
| Rate of `order_line` with `NULL`/out-of-range discount | Legacy writer, un-backfilled data, or input bug |
| Header `gross − discount` differs from `total` | Financial invariant broken |
| Rate of version-conflict commands | Old/new writers contending; may need retry tuning |
| Remaining code paths writing old columns | Not yet ready to contract schema |
| Outbox lag and duplicate publishes | Relay issues or normal retries needing consumer dedup |
| Consumer schema rejections / DLQ | v1/v2 event incompatibility |
| Share of events missing breakdown | Cannot build full gross/discount metrics |
| Duplicate fact keys or backward `sourceVersion` | CDC, replay, or mapping bug |
| Source total vs. BI net gap at cutoff | Pipeline bug, late data, or definition mismatch |
| Dashboard query errors after view switch | Reporting consumer incompatible |
| Tenant/schema migration permissions | Data leakage or privilege creep |

### An investigation walkthrough

After enabling discounts for 5% of tenants, the dashboard shows gross 250M, discount 20M, yet net is 231M instead of 230M. Do not rush to patch a column:

1. Verify the dashboard's metric definition, time window, timezone, and dataset version.
2. Query the fact table for rows where `gross − discount ≠ net`; if every row satisfies the check, inspect grouping/filtering or duplicate JOINs.
3. Reconcile against source Orders by `(tenantId, orderId, lineNo)` and `sourceVersion`.
4. Check whether v1 and v2 events for **the same occurrence** were counted twice.
5. Check whether a Payment capture or refund landed on a different date or belongs to a different metric.
6. If the transform is buggy, halt official metric publication, fix the code, and rebuild the affected scope with a new `transformVersion`.
7. Audit the fix decision and compare before/after numbers; never silently overwrite previously published reports.

**Lineage** links dashboard row → fact grain → event/source Order → schema/transform version. Without stable keys and source metadata, debugging devolves into guesswork regardless of how many timestamp columns a table has.

## 17. Differences across relational, document, graph, and analytical models

The overarching principles remain semantic compatibility and write ownership, while physical mechanics vary:

| Data model | Typical change | Transitional mechanism | Pitfalls |
| --- | --- | --- | --- |
| **Relational** | Add discount column, constraint, index | Expand/backfill/validate, versions/transactions | DDL locks, old writer `UPDATE` drops fields, stale summary columns |
| **Document** | Add `discountPerUnitVnd` inside `lines` array | Conditional reader defaults, `schemaVersion`/doc migration, conditional updates | Old docs lack field; full-doc replacement wipes new fields |
| **Graph** | Add pricing/promotion/version relationships | Migrate nodes/edges and query with new semantics | New edge does not automatically enforce Order edit permissions or pricing |
| **Columnar warehouse / lakehouse** | Add measures, change grain, partition, semantic layer | Fact v2, backfill/MERGE, parallel views, metric versions | Double counting, late data, history rewrites, old queries reading wrong columns |

### Documents and mixed-version readers

An old Order document has:

~~~json
{
  "orderId": "O-101",
  "schemaVersion": 1,
  "lines": [
    { "lineNo": 1, "quantity": 2, "unitPriceVnd": 100000 }
  ],
  "totalVnd": 200000
}
~~~

A new reader can interpret **`discountPerUnitVnd = 0`** for v1 documents, because the v1 contract guaranteed no discounts existed. When writing a v2 document:

~~~json
{
  "orderId": "O-101",
  "schemaVersion": 2,
  "lines": [
    {
      "lineNo": 1,
      "quantity": 2,
      "unitPriceVnd": 100000,
      "discountPerUnitVnd": 10000
    }
  ],
  "grossTotalVnd": 200000,
  "discountTotalVnd": 20000,
  "totalVnd": 180000
}
~~~

**Warning:** an old writer might load the full v2 document, ignore unknown `discountPerUnitVnd`, and overwrite the whole document in v1 format, **erasing the new fields**. Conditional updates/versioning and blocking old writers from editing v2 documents are critical—read-time defaults alone are not enough.

### Graph and analytics also need migration contracts

In a graph, `Product` and `Promotion` may become linked nodes, yet the discount locked on an `OrderLine` still requires **a snapshot or point-in-time fact**. Linking an `OrderLine` directly to today's `Promotion` price causes yesterday's Order history to mutate whenever a promotion changes.

In a warehouse, if a change alters **grain** from one `OrderLine` to one capture/refund per `OrderLine`, create a new fact grain or properly keyed model—**never cram multiple captures under a single `OrderLine` key** hoping aggregates sort themselves out.

## 18. Practice exercise: adding tax to ride-hailing trip fares

**Context:** A ride-hailing platform stores `Trip` with distance in km, base fare, and total fare in VND. Previously no separate tax or surcharge existed. New policy requires displaying **`fareBeforeTax`**, **`taxAmount`**, and **`totalCharged`**, with some trips receiving service-type discounts/exemptions. Old and new invoices must reconcile. `Payment` and `Analytics` live in separate bounded contexts.

### Questions

1. Write invariants for `TripAmount`. When both discount and tax apply, which contract governs order of operations and rounding? Why must you never guess?
2. Propose changes to the Java `Trip` aggregate and a `MoneyVnd` value object. Avoid arbitrary `setTaxAmount` setters bypassing policy.
3. Design storage evolution via expand → backfill → enforce → contract; what meaning must legacy `total_vnd` keep during transition?
4. Some older trips lack stored tax breakdown, though accounting computed taxes elsewhere. Can you backfill `taxAmount = 0` for all of them? If not, what should you do?
5. Design `TripChargedV2`, the v1 consumer plan, idempotency, and deployment sequence prior to enabling tax.
6. Design a fact table at the grain of one completed charged trip and metrics for pre-tax fare / tax / total charged. If multiple captures occur per Trip, what new grain is appropriate?
7. If rolling back Java after taxed trips exist, how could old writers corrupt data? Propose a guard against unsafe writes.
8. Write test cases covering negative amounts, rounding, old/new app compatibility, late events, duplicate captures, and dashboard reconciliation.

### Suggested approach

- **Domain:** `TripPricing`/`TripAmount` holds `fareBeforeTax`, `discount`, `taxableBase`, `tax`, and `totalCharged`. The formula is finalized only once business/policy owners lock deduction order, tax type, rate, rounding unit, and effective date—never assume tax applies pre-discount or post-discount.
- **Storage:** add nullable/default breakdown columns only where historical meaning is proven; backfill from the authoritative accounting ledger rather than writing `0` into tax fields if accounting computed taxes elsewhere.
- **Events:** `TripChargedV2` publishes named amounts, currency, `occurredAt`, `eventId`, and `schemaVersion`. V1 consumers keep receiving `totalCharged` via adapter if legacy total meant **actual charged amount**, never flipping it to "pre-tax".
- **Reporting:** fact grained at one `TripCharged` when policy allows single capture; with multiple captures, use one capture or allocation per key with clear aggregation rules.
- **Rollout:** upgrade writers and pipelines before flipping the flag; reconcile per-trip and period totals; contract schema per schedule. Once taxed rows exist, rolling back an old binary unaware of tax risks erasing breakdowns.
- **Testing:** arithmetic properties and versioned policy rules, non-corrupting backfill, deduplicated occurrence counting, atomic outbox writes, and complete cutoff-aligned reports.

## 19. Handover checklist and conclusion

Before declaring any model change complete, verify:

- **Semantics:** do old and new fields preserve documented meanings, units, statuses, and recognition timestamps?
- **Domain:** are invariants enforced in the right aggregate/value object, and obeyed by all command writers?
- **Schema:** are new columns, defaults, keys, constraints, indexes, and migrations safe under coexisting old/new instances?
- **Backfill:** are historical rules evidenced, idempotently re-runnable, discrepancy-reconciled, and explicit about `NULL` handling?
- **Concurrency:** do all write paths honor root versions/locks, with zero old writers silently overwriting new data?
- **Events:** do v1/v2 contracts have clear ownership, `schemaVersion`, `eventId`, and correlation without silent field redefinitions?
- **Outbox/inbox:** are state truth and publish intent committed in the same transaction, with retry/duplicate/out-of-order handling?
- **Consumers:** are compatibility matrices, adapter/contract tests, handover plans, and v1 retirement timelines in place?
- **Reporting:** are grain, gross/discount/net, history, timezones, metric versions, SCDs, and corrections addressed?
- **Reconciliation:** can you trace Java/domain → SQL → event → fact → KPI by ID, cutoff, and version?
- **Deployment:** have expand/migrate/switch/contract steps been ordered and feature gates defined?
- **Rollback:** if new data already exists, will reverting to old binaries lose information, and is a safe roll-forward plan ready?
- **Security:** are tenant isolation, PII, event payloads, historical read permissions, and retention controlled?
- **Observability:** can you detect financial drift, failed messages, lag, schema conflicts, and broken reports post-deploy?
- **Testing:** have unit, real-DB integration, contract, replay, boundary, and shadow-reporting tests all PASSED?

**Conclusion:** Synchronizing changes across Java, storage, events, and reports is not about syncing **field names**, but about protecting **one business truth across coexisting representations and versions**. Java enforces behavior and invariants; the database guards data at commit time; events publish versioned contracts; analytical models interpret data by explicit grain, metrics, and point-in-time rules. A safe change follows **expand → migrate/reconcile → switch → contract**, never enables new behavior before critical writers understand it, and never mistakes code rollback for sufficient protection once data has evolved. Designed this way, a data model can evolve, trace lineage, and prove correctness without distorting past business commitments.
