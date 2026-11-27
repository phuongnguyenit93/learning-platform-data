# Inventory: Conditional Updates and Preventing Double Decrements in MongoDB

## Lesson Objectives

In sales, ticketing, reservation, and resource allocation systems, “decrementing inventory” seems like a simple subtraction command. Yet there are two **distinct** bugs to prevent:

- **Overselling:** two different requests are both confirmed when only one item remains in stock. The fix is enforcing a sufficient-stock condition directly inside an **atomic update**.
- **Double decrement:** one request successfully deducts stock, but the response is lost; the client or queue retries the same request and stock is deducted a second time. The fix is a **stable idempotency key** paired with proof that the effect was committed.

MongoDB supports atomic single-document updates, the `$inc` operator, `$gte` filters, unique indexes, retryable writes, and multi-document transactions. However, **a conditional update that prevents overselling does not automatically prevent retried requests**. Conversely, a unique marker in a separate document from the stock document is not automatically atomic either.

This lesson belongs to **MongoDB Document Database Engine → Application Design → Inventory: Conditional Updates and Preventing Double Decrements in MongoDB**.

Objectives:

1. Distinguish `on_hand`, `available`, `reserved`, and stock movements.
2. Define invariants for each inventory bucket by tenant, warehouse, and SKU.
3. Use `updateOne` with `available >= quantity` and `$inc` to prevent overselling.
4. Interpret `matchedCount` and `modifiedCount` correctly.
5. Explain why read–modify–save and blind `$inc` retries are unsafe.
6. Design stable reservation IDs, request fingerprints, and unique business keys.
7. Use a reservation ledger + transaction to commit the marker together with the decrement.
8. Handle duplicate requests, duplicate keys, and unknown transaction commit results.
9. Design exactly-once reserve, release, expire, and fulfill transitions.
10. Handle multiple SKUs/warehouses, payment callbacks, outboxes, and event retries.
11. Write Java Sync Driver and Spring Data MongoTemplate examples.
12. Build concurrency tests, reconciliation, metrics, and runbooks.

> Both guardrails must coexist: **a quantity condition at write time** and **deduplication proof by business ID**.

---

## 1. Defining the Exact Meaning of Each Number

Example inventory document:

    {
      _id: "tenant-a|wh-hcm|SKU-01",
      tenant_id: "tenant-a",
      warehouse_id: "wh-hcm",
      sku: "SKU-01",
      on_hand: NumberLong("10"),
      reserved: NumberLong("3"),
      available: NumberLong("7"),
      version: NumberLong("12"),
      updated_at: ISODate("2026-11-14T02:00:00Z")
    }

In the sample model:

| Field | Explanation |
|---|---|
| `on_hand` | Physical units in the warehouse, including reserved items |
| `reserved` | Units held for active reservations |
| `available` | Units still eligible to be reserved/sold |
| `tenant_id` | Data owner |
| `warehouse_id` | Physical warehouse |
| `sku` | Product variant identifier |
| `version` | Update generation for optimistic concurrency |
| `updated_at` | Timestamp of the change |

Formula in the simple model:

    on_hand = available + reserved
    available >= 0
    reserved  >= 0
    on_hand   >= 0

This is **a convention of this model**, not a mandatory formula across all WMS systems. If inventory includes damaged goods, quarantine, in-transit stock, safety stock, or backorders, additional fields and business-accurate invariants are needed.

### 1.1. Reserving Two Units

    Before: on_hand=10, reserved=3, available=7
    After:  on_hand=10, reserved=5, available=5

The items have not left the warehouse; they simply can no longer be promised to another request.

### 1.2. Releasing a Two-Unit Reservation

    Before: on_hand=10, reserved=5, available=5
    After:  on_hand=10, reserved=3, available=7

### 1.3. Fulfilling and Shipping Two Units

    Before: on_hand=10, reserved=5, available=5
    After:  on_hand=8,  reserved=3, available=5

Do not increment available when shipping: it was already decremented at reservation time.

### 1.4. Receiving Stock

Receiving 5 sellable units increases both `on_hand` and `available` by 5, leaving `reserved` unchanged. If the inbound event is re-sent, you still need a movement ID to prevent double-crediting.

---

## 2. One Document Represents One Inventory Bucket

One partitioning scheme:

    tenant-a / wh-hcm / SKU-01 -> document A
    tenant-a / wh-hn  / SKU-01 -> document B
    tenant-a / wh-hcm / SKU-02 -> document C

Each bucket has a stable ID. Never embed millions of SKUs and reservations into one array inside a giant document.

You can create a compound unique index:

    db.inventory.createIndex(
      {
        tenant_id: 1,
        warehouse_id: 1,
        sku: 1
      },
      {
        unique: true,
        name: "uq_inventory_bucket"
      }
    );

If `_id` is already a strictly encoded composite key, unique `_id` may suffice for identity, while whether to add the compound index depends on queries. Do not concatenate arbitrary delimiters if tenant/SKU values can contain the separator character.

### 2.1. Why Does Document-Level Atomicity Help?

`available` and `reserved` live in **the same document**, so MongoDB can update both fields in a single atomic write. If they lived in two documents, a transaction or consistency protocol would be needed.

### 2.2. Hot SKUs

A very hot product can cause many requests to update the same document concurrently; adding shards does not automatically distribute a single hot document. You still need to benchmark contention, retry rates, and consider quota/escrow mechanisms if deeper scaling is truly required.

---

## 3. Read–Modify–Save Causes Race Conditions

Unsafe code:

    Inventory inv = repository.findById(stockId)
        .orElseThrow();

    if (inv.getAvailable() >= quantity) {
        inv.setAvailable(
            inv.getAvailable() - quantity
        );
        repository.save(inv);
        return "RESERVED";
    }

    return "OUT_OF_STOCK";

When available=1:

    T1 Request A reads available=1
    T2 Request B reads available=1
    T3 Request A checks qty=1 -> OK
    T4 Request B checks qty=1 -> OK
    T5 Request A saves available=0
    T6 Request B saves available=0
    T7 Both report RESERVED even though only 1 item existed

The final available count is still 0, so simply checking “non-negative” in the database is not enough to detect business overselling.

### 3.1. Java Locks Are Not Enough

`synchronized` only protects a single JVM. Multiple pods, services, job scripts, and queue consumers can still write to the same MongoDB document concurrently. The predicate must be enforced at the database write.

### 3.2. Principle

Never read and then issue an unconditional write. Put **available >= quantity** directly into the filter of `updateOne`.

---

## 4. Atomic Conditional Decrement in mongosh

Run the following commands only in a lab environment:

    use inventory_lab

    db.inventory.insertOne({
      _id: "tenant-a|wh-hcm|SKU-01",
      tenant_id: "tenant-a",
      warehouse_id: "wh-hcm",
      sku: "SKU-01",
      on_hand: NumberLong("10"),
      reserved: NumberLong("3"),
      available: NumberLong("7"),
      version: NumberLong("12"),
      updated_at: new Date()
    });

Reserve two units:

    const qty = NumberLong("2");

    const result = db.inventory.updateOne(
      {
        _id: "tenant-a|wh-hcm|SKU-01",
        tenant_id: "tenant-a",
        available: { $gte: qty }
      },
      {
        $inc: {
          available: NumberLong("-2"),
          reserved: NumberLong("2"),
          version: NumberLong("1")
        },
        $currentDate: {
          updated_at: true
        }
      }
    );

    printjson(result);

### 4.1. Why Is This Correct Under Concurrency?

Two clients both send q=2 when available starts at 2: one update decrements it to 0; the other update no longer matches `available >= 2`. MongoDB evaluates the predicate atomically during the document write.

### 4.2. Why Decrement available and Increment reserved Together?

If you issue two separate `updateOne` calls, a crash between them breaks `on_hand=available+reserved`. A single combined update preserves the document-level invariant.

### 4.3. Do Not Use upsert

Never add `upsert:true` for reservations. When available is insufficient or the bucket does not exist, upsert may attempt to insert a new invalid record or trigger duplicate key errors.

### 4.4. Validate Quantity

Reject qty<=0, values above domain maximums, wrong numeric types, and overflows. If qty=-2, negating a negative number ends up adding stock.

---

## 5. Understanding matched and modified Results

With an acknowledged updateOne:

    {
      acknowledged: true,
      matchedCount: 1,
      modifiedCount: 1,
      upsertedId: null
    }

| Matched | Modified | Meaning |
|---:|---:|---|
| 1 | 1 | One bucket was modified |
| 0 | 0 | No matching bucket: insufficient stock, wrong tenant, or missing ID |
| 1 | 0 | Matched but unmodified; rare with `$inc` q>0 |
| Unacknowledged | Uncertain | Handle write concern/network/unknown outcome |

`matchedCount=0` does not automatically prove out-of-stock. An authorized lookup may be needed to classify missing/closed/insufficient stock; never leak the existence of another tenant's bucket.

When the UI shows “1 item left”, that number may be stale. Only a **committed write satisfying the predicate** confirms a successful reservation.

---

## 6. Trap: Conditional Decrements Still Deduct Twice

Suppose available=10:

    Client sends R100, qty=2
       |
    MongoDB updates available 10 -> 8
       |
    Server commits but response is lost
       |
    Client times out and retries R100
       |
    MongoDB updates available 8 -> 6

Both times `available>=2` holds true. The result is a double decrement.

### 6.1. Sources of Retries

- API gateway/client timeouts.
- User clicking a button twice.
- At-least-once queue redelivery.
- Worker restart after DB commit but before message ACK.
- Duplicate payment/shipping callbacks.
- Batch/job replays.
- Application retry policies re-invoking methods.

### 6.2. Retryable Writes Do Not Replace Business Idempotency

The MongoDB Driver offers retryable writes for certain operations using protocol-level identities. However, a new HTTP request or a consumer reprocessing a message typically creates a brand new MongoDB operation. The business layer must still recognize the same reservation ID.

### 6.3. Two Distinct Questions

- **Condition:** “Does the warehouse currently have enough for q?”
- **Idempotency:** “Has business operation R100 already been applied?”

**Both** must be answered before treating a reservation as correct.

---

## 7. Designing a Stable Idempotency Key

Example request:

    {
      "reservationId": "resv-2026-000123",
      "orderId": "ORD-101",
      "lineId": "LINE-1",
      "warehouseId": "wh-hcm",
      "sku": "SKU-01",
      "quantity": 2
    }

### 7.1. Preserve the ID Across Retries

If request R100 times out and is retried, keep `reservationId=R100`. Never generate a fresh UUID per retry attempt.

### 7.2. Scope the ID to the Business Domain

You can derive a stable identity from:

    tenant_id + order_id + line_id + generation

If the same line can create a new reservation after a release/expiry, increment the generation. Never reuse a terminal ID to “re-reserve”.

### 7.3. Key Reuse with Different Parameters

R100 sent first for SKU-01 qty=2 and later for SKU-02 qty=5 must return an **idempotency conflict** without altering inventory. Compare immutable fields or a canonical request fingerprint (tenant, stock ID, SKU, order, line, qty, type).

### 7.4. Retention

Markers must be retained long enough to cover replay/queue retention, late callbacks, disputes, or legal policies. If TTL deletes the proof too early, a delayed retry may be treated as a new request and deduct stock again.

### 7.5. Duplicate Checkout Before Reservation

If one checkout button click spawns **two new order IDs**, each creating a different reservation, the inventory ledger will not recognize them as duplicates. Idempotency is required at the checkout/order creation API as well, not only in inventory.

---

## 8. Reservation Ledger

An `inventory_reservations` collection:

    {
      _id: "resv-2026-000123",
      tenant_id: "tenant-a",
      order_id: "ORD-101",
      line_id: "LINE-1",
      stock_id: "tenant-a|wh-hcm|SKU-01",
      warehouse_id: "wh-hcm",
      sku: "SKU-01",
      quantity: NumberLong("2"),
      request_fingerprint: "sha256-canonical-params",
      state: "ACTIVE",
      created_at: ISODate("2026-11-14T03:00:00Z"),
      expires_at: ISODate("2026-11-14T03:15:00Z")
    }

The ledger holds:

- Stable ID and unique business key.
- Immutable parameters to detect misuse.
- State `ACTIVE`, `RELEASED`, `EXPIRED`, `FULFILLED`.
- Proof that the request committed.
- Data to reconcile stock counters.
- Timestamps/request origin for auditing.

`_id` already has a unique index. You can add a compound unique index on tenant/order/line/generation when the schema uses all of those fields:

    db.inventory_reservations.createIndex(
      {
        tenant_id: 1,
        order_id: 1,
        line_id: 1,
        generation: 1
      },
      {
        unique: true,
        name: "uq_reservation_business"
      }
    );

If not using generation, omit that field from the index and define one unique reservation per order line. Schema validation must align with the key design.

---

## 9. Why Adding Only a Unique Marker Is Not Enough

First mistake:

    1. insert reservation marker R100
    2. decrement inventory

Crash between steps: the marker exists, but stock was not decremented. Retries see the marker and **falsely** return ALREADY_RESERVED.

Second mistake:

    1. decrement inventory
    2. insert reservation marker R100

Crash between steps: stock was decremented, but no marker exists. Retries decrement stock a second time.

### 9.1. A Unique Index Only Protects the Marker

It does not automatically ensure two writes across **two documents** commit together.

### 9.2. Common Approach

Use a multi-document transaction containing both the reservation insert and the conditional inventory update. When stock is insufficient, throw/abort the entire transaction so no ACTIVE marker is saved.

### 9.3. Other Options

A single-document atomic protocol with bounded markers or a saga with proven state/recovery can also be correct. Never issue two non-transactional writes and assume “crashes rarely happen in practice”.

---

## 10. Reservation Transaction Sequence

    BEGIN TRANSACTION
        |
        +-- Look up reservation R100
        |      +-- exists, same fingerprint, ACTIVE: ALREADY_RESERVED
        |      +-- exists, terminal: return terminal outcome
        |      +-- exists, different fingerprint: CONFLICT
        |
        +-- Insert R100 with state ACTIVE
        |
        +-- updateOne inventory:
        |      filter stock_id + tenant + available >= q
        |      $inc available -q, reserved +q
        |      matched=0: abort
        |
    COMMIT: both marker and inventory succeed together

### 10.1. Requirements

Multi-document transactions require a replica set or sharded cluster on a supported MongoDB version. A local standalone `mongod` is insufficient for transaction labs; a single-member replica set can be used.

### 10.2. Keep It Short and Bounded

Do not make HTTP calls, send emails, or charge payments inside a transaction. Touch only the required MongoDB documents. Long transactions increase write conflicts, latency, and resource consumption.

### 10.3. Do Not Change the ID on Retry

If an order request for the same business action generates a new marker, the transaction can still decrement stock twice. Accurate identity is just as critical as the transaction itself.

---

## 11. Java Sync Driver: Conditional Update

This method prevents **overselling**, not duplicate business requests yet.

    import com.mongodb.client.MongoCollection;
    import com.mongodb.client.result.UpdateResult;
    import org.bson.Document;

    import static com.mongodb.client.model.Filters.and;
    import static com.mongodb.client.model.Filters.eq;
    import static com.mongodb.client.model.Filters.gte;
    import static com.mongodb.client.model.Updates.combine;
    import static com.mongodb.client.model.Updates.currentDate;
    import static com.mongodb.client.model.Updates.inc;

    public final class StockUpdate {

        public static boolean reserveConditional(
                MongoCollection<Document> inventory,
                String stockId,
                String tenantId,
                long quantity) {

            if (quantity <= 0) {
                throw new IllegalArgumentException(
                    "Quantity must be positive"
                );
            }

            UpdateResult result = inventory.updateOne(
                and(
                    eq("_id", stockId),
                    eq("tenant_id", tenantId),
                    gte("available", quantity)
                ),
                combine(
                    inc("available", -quantity),
                    inc("reserved", quantity),
                    inc("version", 1L),
                    currentDate("updated_at")
                )
            );

            if (!result.wasAcknowledged()) {
                throw new IllegalStateException(
                    "Unacknowledged stock write"
                );
            }

            return result.getMatchedCount() == 1;
        }
    }

### 11.1. Return Success Only on a Committed Result

If the client receives no response, do not conclude the update failed; its state may be unknown. Without a ledger, the application cannot tell whether this request was applied just by inspecting current available stock.

### 11.2. Numeric Types

Standardize on BSON Int64/Java long. Disallow negative qty, never use floating-point numbers for integer quantities, guard upper bounds/overflow, and avoid null/string fields in stock counters.

---

## 12. Java Sync Driver: Idempotent Reservation Transaction

Java 17+ example using `record` to represent the request. Assumes collections, indexes, and a transaction-capable deployment are set up.

    import com.mongodb.ReadConcern;
    import com.mongodb.ReadPreference;
    import com.mongodb.TransactionOptions;
    import com.mongodb.WriteConcern;

    import com.mongodb.client.ClientSession;
    import com.mongodb.client.MongoClient;
    import com.mongodb.client.MongoCollection;
    import com.mongodb.client.result.UpdateResult;

    import org.bson.Document;
    import java.util.Objects;

    import static com.mongodb.client.model.Filters.and;
    import static com.mongodb.client.model.Filters.eq;
    import static com.mongodb.client.model.Filters.gte;
    import static com.mongodb.client.model.Updates.combine;
    import static com.mongodb.client.model.Updates.inc;

    public class ReservationService {

        public enum Outcome {
            RESERVED, ALREADY_RESERVED
        }

        public record Request(
            String reservationId,
            String tenantId,
            String stockId,
            String sku,
            long quantity,
            String fingerprint
        ) {}

        private final MongoClient client;
        private final MongoCollection<Document> inventory;
        private final MongoCollection<Document> reservations;

        public ReservationService(
            MongoClient client,
            MongoCollection<Document> inventory,
            MongoCollection<Document> reservations
        ) {
            this.client = client;
            this.inventory = inventory;
            this.reservations = reservations;
        }

        public Outcome reserve(Request req) {
            if (req.quantity() <= 0) {
                throw new IllegalArgumentException("quantity");
            }

            TransactionOptions options =
                TransactionOptions.builder()
                    .readConcern(ReadConcern.SNAPSHOT)
                    .writeConcern(WriteConcern.MAJORITY)
                    .readPreference(ReadPreference.primary())
                    .build();

            try (ClientSession session = client.startSession()) {
                return session.withTransaction(() -> {

                    Document old = reservations.find(
                        session,
                        eq("_id", req.reservationId())
                    ).first();

                    if (old != null) {
                        checkSame(old, req);

                        if ("ACTIVE".equals(
                                old.getString("state"))) {
                            return Outcome.ALREADY_RESERVED;
                        }

                        throw new IllegalStateException(
                            "Reservation already terminal"
                        );
                    }

                    Document marker = new Document()
                        .append("_id", req.reservationId())
                        .append("tenant_id", req.tenantId())
                        .append("stock_id", req.stockId())
                        .append("sku", req.sku())
                        .append("quantity", req.quantity())
                        .append(
                            "request_fingerprint",
                            req.fingerprint()
                        )
                        .append("state", "ACTIVE")
                        .append(
                            "created_at",
                            new java.util.Date()
                        );

                    reservations.insertOne(session, marker);

                    UpdateResult r = inventory.updateOne(
                        session,
                        and(
                            eq("_id", req.stockId()),
                            eq("tenant_id", req.tenantId()),
                            gte("available", req.quantity())
                        ),
                        combine(
                            inc("available", -req.quantity()),
                            inc("reserved", req.quantity()),
                            inc("version", 1L)
                        )
                    );

                    if (r.getMatchedCount() != 1) {
                        throw new InsufficientStock();
                    }

                    return Outcome.RESERVED;
                }, options);
            }
        }

        private static void checkSame(
            Document marker,
            Request req
        ) {
            boolean same =
                Objects.equals(
                    marker.getString("tenant_id"),
                    req.tenantId()
                )
                && Objects.equals(
                    marker.getString("stock_id"),
                    req.stockId()
                )
                && Objects.equals(
                    marker.getString("sku"),
                    req.sku()
                )
                && marker.getLong("quantity")
                    == req.quantity()
                && Objects.equals(
                    marker.getString("request_fingerprint"),
                    req.fingerprint()
                );

            if (!same) {
                throw new IllegalArgumentException(
                    "Idempotency key reused with changed input"
                );
            }
        }

        public static class InsufficientStock
                extends RuntimeException {
            public InsufficientStock() {
                super("Inventory insufficient");
            }
        }
    }

### 12.1. Marker and Stock Commit Together

If the marker insert executes but the stock filter does not match, throwing aborts the transaction, avoiding a bogus ACTIVE marker.

### 12.2. The Driver May Run the Callback More Than Once

`withTransaction` includes retry semantics for transient transaction errors. Never charge a payment provider, send emails, or publish messages directly inside the callback.

### 12.3. Contention on the Same ID

Two transactions with the same R100 can both read “not found”, and then one receives a duplicate key or write conflict. An outer handler must read/reconcile the committed marker and verify fingerprint and state. Never treat every duplicate key blindly as a successful duplicate.

### 12.4. Terminal States

If R100 is already RELEASED/EXPIRED/FULFILLED, retrying reserve must not deduct stock. This example throws a domain exception; production can return a typed terminal outcome.

---

## 13. Unknown Commit Results and Correct Retries

Timeline:

    T1 Transaction inserts reservation R100
    T2 Transaction decrements available 10 -> 8
    T3 MongoDB commit succeeds
    T4 Commit ACK is lost on the network
    T5 Client sees timeout / unknown commit
    T6 Client retries R100

Handling:

1. Preserve the same R100 and canonical request fingerprint.
2. Let the driver retry commit via supported APIs where applicable.
3. If the outcome remains unknown, **do not report definite failure**.
4. Query the reservation ledger to verify committed state with primary/appropriate read consistency.
5. If ACTIVE with matching fingerprint, conclude it is already reserved; do not decrement again.
6. If still unresolved, use bounded backoff/reconciliation/PENDING response.
7. Never generate a new reservation ID to work around the error.

### 13.1. Distinguishing Error Labels

`TransientTransactionError` generally allows retrying the entire transaction per contract. `UnknownTransactionCommitResult` concerns the commit outcome, requiring commit retry/reconciliation rather than running a fresh business operation.

### 13.2. One Read Returning “Not Found” Does Not Prove Failure

A competing transaction may still be committing or a secondary may be lagging. Never infer from a single read's absence that “stock was not deducted”.

### 13.3. Never Blindly Retry `$inc` from HTTP Retries

Retrying a new method call does not necessarily preserve the MongoDB protocol operation identity of retryable writes. A **business ID** is the true guardrail across HTTP, queues, and process restarts.

---

## 14. Spring Data MongoTemplate

An equivalent conditional update:

    import com.mongodb.client.result.UpdateResult;
    import org.springframework.data.mongodb.core.MongoTemplate;
    import org.springframework.data.mongodb.core.query.Criteria;
    import org.springframework.data.mongodb.core.query.Query;
    import org.springframework.data.mongodb.core.query.Update;

    public final class InventoryTemplateService {

        private final MongoTemplate template;

        public InventoryTemplateService(
            MongoTemplate template
        ) {
            this.template = template;
        }

        public boolean reserveConditional(
            String stockId,
            String trustedTenantId,
            long qty
        ) {
            if (qty <= 0) {
                throw new IllegalArgumentException("qty");
            }

            Query query = Query.query(
                Criteria.where("_id").is(stockId)
                    .and("tenant_id").is(trustedTenantId)
                    .and("available").gte(qty)
            );

            Update update = new Update()
                .inc("available", -qty)
                .inc("reserved", qty)
                .inc("version", 1L)
                .currentDate("updated_at");

            UpdateResult result = template.updateFirst(
                query,
                update,
                "inventory"
            );

            if (!result.wasAcknowledged()) {
                throw new IllegalStateException(
                    "Write unacknowledged"
                );
            }

            return result.getMatchedCount() == 1;
        }
    }

### 14.1. Field Names

This example uses the collection-name overload, so paths are raw BSON keys. With typed entities annotated with `@Field`, Spring Data mapping can translate Java properties to BSON. Verify exact mappings and tenant filters.

### 14.2. Spring Transaction Manager

    import org.springframework.context.annotation.Bean;
    import org.springframework.context.annotation.Configuration;
    import org.springframework.data.mongodb.MongoDatabaseFactory;
    import org.springframework.data.mongodb.MongoTransactionManager;

    @Configuration
    class MongoTxConfig {

        @Bean
        MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory
        ) {
            return new MongoTransactionManager(factory);
        }
    }

Then use a service method annotated with `@Transactional(transactionManager="mongoTransactionManager")` to insert the marker and update stock in the same transaction. It must be invoked through a Spring-managed proxy; self-invocation can bypass transaction advice. Importantly, the standalone `reserveConditional` snippet above does **not** yet prevent double decrements; you must integrate the ledger as explained in the transaction model.

### 14.3. `@Version` Differs from Idempotency

Spring Data `@Version` can support optimistic locking with `save` on applicable API paths, but template updates do not automatically inject an expected version filter into every command; furthermore, version does not indicate whether request R100 was already processed.

---

## 15. Reservation State Machine

    NEW
     |
     v
    ACTIVE
      | \
      |  +----- FULFILLED
      |
      +-------- RELEASED
      |
      +-------- EXPIRED

Terminal states never transition back to ACTIVE under the same ID.

| Transition | Inventory change |
|---|---|
| NEW → ACTIVE | available−q, reserved+q |
| ACTIVE → RELEASED | available+q, reserved−q |
| ACTIVE → EXPIRED | available+q, reserved−q |
| ACTIVE → FULFILLED | on_hand−q, reserved−q |
| RELEASED/EXPIRED → ACTIVE same ID | Disallowed |
| Terminal → terminal on duplicate request | Return recorded outcome, do not change stock |

### 15.1. Exactly-Once Release

In the same transaction:

- Read reservation R100.
- If already RELEASED, return ALREADY_RELEASED.
- If FULFILLED, cannot release again.
- Only when ACTIVE, CAS ACTIVE→RELEASED.
- Update inventory with `reserved>=q`, `$inc available:+q` and `reserved:-q`.
- If the stock update does not match, abort so no invalid state is persisted.

### 15.2. Why Is `reserved>=q` Not Enough?

Total reserved may still be high due to other active reservations. If a cancel callback for R100 runs twice, the second run could still match and wrongly add to available. **CAS on the reservation state** is what prevents double release.

### 15.3. Fulfillment

When goods physically leave the warehouse, CAS ACTIVE→FULFILLED in the same transaction decrements `on_hand` and `reserved`, leaving `available` unchanged. Retried shipping callbacks must not decrement again.

### 15.4. Refunds and Returns

A financial refund does not mean goods have returned to the warehouse. Returns may require inspection, damaged/quarantine classification, and a separate stock movement before increasing available.

---

## 16. Reservation Expiration and the TTL Trap

The worker needs to find:

    db.inventory_reservations.find({
      state: "ACTIVE",
      expires_at: { $lte: new Date() }
    }).sort({
      expires_at: 1,
      _id: 1
    }).limit(100);

Inside a transaction, the worker verifies the reservation is still ACTIVE and expired, transitions ACTIVE→EXPIRED, and increments available/decrements reserved in the same commit.

### 16.1. TTL Does Not Automatically Release Stock

A TTL index only deletes the reservation document; **it does not automatically update inventory**. Deleting an ACTIVE marker both fails to restore stock and destroys idempotency proof.

### 16.2. TTL for Cleaning Up Terminal Records

A `delete_after_at` field can be used for terminal records after a sufficiently long retention period, though delayed retries could arrive after TTL deletion. Prove that retention ensures old operations cannot be reprocessed.

### 16.3. TTL Is Not Deadline-Exact

TTL deletion is a background process and can lag. Expiration workers must rely on `expires_at` and state conditions, never on whether a marker was deleted.

### 16.4. Expiry vs. Payment Race

A payment callback and an expiry worker compete for ACTIVE. Only one terminal transition commits. The order/payment state machine must handle funds arriving after expiry, never silently reviving a terminal reservation.

---

## 17. Multiple SKUs, Multiple Warehouses, and Transactions

An order:

    {
      "orderId": "ORD-101",
      "lines": [
        { "sku": "SKU-01", "warehouse": "HCM", "qty": 2 },
        { "sku": "SKU-02", "warehouse": "HCM", "qty": 1 }
      ]
    }

Two SKUs are two inventory documents.

### 17.1. All-or-Nothing

If SKU-01 has enough stock while SKU-02 does not, reserving via two separate updates leaves a partial hold. If business rules require all-or-nothing across the order, use a transaction covering all stock updates + reservation markers + order state.

### 17.2. Partial Reservations

If business rules permit backorders/partial fulfillment, record explicit line-level states and compensation. Never report “fully reserved” when only part succeeded.

### 17.3. Merging Duplicate-Bucket Line Items

Two lines with the same tenant+warehouse+SKU should have their quantities summed with overflow checks to simplify reconciliation and reduce repeated touches on the same document.

### 17.4. Multi-Warehouse

For example, HCM has 3 and HN has 4, and an order needs 5, so 3+2 can be allocated if policy allows. This spans multiple stock documents; use a transaction or a stateful recoverable saga rather than reading total available and deducting arbitrarily from one warehouse.

### 17.5. Transaction Duration

Keep transactions short, use stable order/reservation identities, sort bucket IDs in a consistent order where helpful, and bound retries on write conflicts.

## 18. Single-Document Idempotency: Valid but Hard to Scale

A transaction-free option is storing applied operation IDs directly inside the stock document:

    db.inventory.updateOne(
      {
        _id: "tenant-a|wh-hcm|SKU-01",
        available: { $gte: NumberLong("2") },
        applied_ids: { $ne: "R100" }
      },
      {
        $inc: {
          available: NumberLong("-2"),
          reserved: NumberLong("2")
        },
        $addToSet: {
          applied_ids: "R100"
        }
      }
    );

### 18.1. What Is Correct About It?

The filter requiring R100's absence and the decrement + marker addition execute in one atomic document update. Two requests with the same ID will not both match when the marker is stored properly.

### 18.2. Why Is It Not Widely Used?

`applied_ids` grows unboundedly over the years. MongoDB documents have a 16 MiB BSON limit; growing arrays cause hot documents, write amplification, and maintenance overhead.

### 18.3. Why Not Prune Old IDs?

If you prune R100 from the array too early, a delayed retry of R100 can deduct stock again. You cannot drop markers just because “5 minutes passed” if a queue might replay after a day.

### 18.4. Standalone `$addToSet` Does Not Prevent Double Decrements

Without the filter `applied_ids:{$ne:"R100"}`, the update's `$inc` still runs a second time even though `$addToSet` skips adding a duplicate entry.

### 18.5. Conclusion

Only use this approach if operation markers are **bounded** with clear generations/retention guaranteeing late retries never exceed retention. For long-lived inventory, a separate reservation ledger + transaction is usually easier to operate.

---

## 19. Optimistic Versioning Does Not Replace an Idempotency Key

You can use an expected version:

    db.inventory.updateOne(
      {
        _id: "tenant-a|wh-hcm|SKU-01",
        version: NumberLong("12"),
        available: { $gte: NumberLong("2") }
      },
      {
        $inc: {
          available: NumberLong("-2"),
          reserved: NumberLong("2"),
          version: NumberLong("1")
        }
      }
    );

### 19.1. What Does Version Protect?

If two writers read the same version=12, only one CAS update succeeds. That prevents lost updates on stale snapshots.

### 19.2. Why Is It Not Enough Against Double Decrements?

An HTTP retry can read version=13 and apply the same business operation R100 a second time. Version only tells you “the document changed”, not “R100 was already applied”.

### 19.3. Distinction

| Mechanism | Question answered |
|---|---|
| `available >= q` | Is there enough stock right now? |
| `version == expected` | Has the state been modified by another writer since read? |
| `reservation_id` unique | Has this business operation already been processed? |
| Multi-document transaction | Did the marker and counter commit together? |
| Reconciliation | Do existing records still satisfy invariants? |

### 19.4. Version Differs from Schema Version

`schema_version` marks the document structure, not the optimistic update counter. Never use one field for both purposes.

---

## 20. Stock Movement Ledger: Every Movement Has an Identity

Not only reservations need idempotency. Receiving, shipping, returning, and inventory adjustments can also repeat.

An `inventory_movements` document:

    {
      _id: "MOVE-1001",
      tenant_id: "tenant-a",
      stock_id: "tenant-a|wh-hcm|SKU-01",
      type: "RECEIVE",
      quantity: NumberLong("5"),
      external_reference: "PO-987",
      created_at: new Date()
    }

### 20.1. Receiving Stock

    db.inventory.updateOne(
      { _id: "tenant-a|wh-hcm|SKU-01" },
      {
        $inc: {
          on_hand: NumberLong("5"),
          available: NumberLong("5")
        }
      }
    );

If event MOVE-1001 is emitted twice, the command above adds 10 instead of 5. A unique movement ID and movement marker must commit atomically with the inventory update or follow an equivalent event-sourced protocol.

### 20.2. Shipping Stock

`SHIP` is not merely decrementing `on_hand`. If items were reserved, transition the reservation ACTIVE→FULFILLED and decrement `reserved` in the same transaction.

### 20.3. Cycle Counts / Adjustments

A blind `set available=100` from a stale snapshot can overwrite newer reservations. Use an adjustment movement with reason codes, before/after audit, version CAS, and authorization workflows.

### 20.4. Inter-Warehouse Transfers

Moving 5 units from HCM to HN requires source/destination movement IDs and an in-transit policy; updating two stock buckets needs a transaction or a saga with reconciliation.

### 20.5. Returns

A financial return after a refund does not automatically add to available. Goods must be received, inspected, and classified as sellable vs. non-sellable.

---

## 21. Database Schema, Indexes, and Guards

### 21.1. Unique Inventory Bucket

    db.inventory.createIndex(
      {
        tenant_id: 1,
        warehouse_id: 1,
        sku: 1
      },
      {
        unique: true
      }
    );

### 21.2. Unique Reservation Business Key

    db.inventory_reservations.createIndex(
      {
        tenant_id: 1,
        order_id: 1,
        line_id: 1
      },
      {
        unique: true
      }
    );

Only use this key if each order line has exactly one reservation over its entire lifecycle. If new attempts/generations occur after cancellation, include generation and ensure the schema stores its value.

### 21.3. Index for the Expiration Worker

    db.inventory_reservations.createIndex({
      state: 1,
      expires_at: 1,
      _id: 1
    });

### 21.4. Index for Reconciliation

    db.inventory_reservations.createIndex({
      tenant_id: 1,
      state: 1,
      stock_id: 1
    });

Measure real workloads. Too many indexes slow down writes, especially when state changes frequently.

### 21.5. Validation for Non-Negative Numbers

On a **new collection used in a lab**, for example:

    db.createCollection("inventory_guarded", {
      validator: {
        $jsonSchema: {
          bsonType: "object",
          required: [
            "tenant_id",
            "warehouse_id",
            "sku",
            "on_hand",
            "available",
            "reserved"
          ],
          properties: {
            on_hand: {
              bsonType: "long",
              minimum: 0
            },
            available: {
              bsonType: "long",
              minimum: 0
            },
            reserved: {
              bsonType: "long",
              minimum: 0
            }
          }
        }
      }
    });

A validator is only one layer of shape/non-negativity protection. It does **not** enforce `on_hand=available+reserved`, business-effect uniqueness, or atomic stock/reservation consistency. If legacy data uses Int32 instead of Int64, migrate and stage validator rollouts before enabling strict mode.

### 21.6. Tenant Permission Conditions

All writes must be scoped to a trusted tenant. Never rely on a self-declared tenant ID in an unverified request body.

---

## 22. Idempotent API Contract

Example REST request (textual representation, not Java syntax):

    POST /api/inventory/reservations
    Idempotency-Key: R100
    Content-Type: application/json

    {
      "orderId": "ORD-101",
      "lineId": "LINE-1",
      "warehouseId": "wh-hcm",
      "sku": "SKU-01",
      "quantity": 2
    }

### 22.1. First Commit

    {
      "reservationId": "R100",
      "state": "ACTIVE",
      "quantity": 2,
      "result": "RESERVED"
    }

### 22.2. Retry with Same ID and Same Payload

    {
      "reservationId": "R100",
      "state": "ACTIVE",
      "quantity": 2,
      "result": "ALREADY_RESERVED"
    }

Never deduct stock a second time.

### 22.3. Out of Stock

    {
      "reservationId": "R101",
      "result": "OUT_OF_STOCK"
    }

If the transaction aborts on out-of-stock, no marker may be created. Retrying R101 **after stock has been replenished** can succeed. If the API must keep returning the rejected outcome across all retries, persist the rejection result under an appropriate protocol; define this requirement explicitly.

### 22.4. Unknown Outcome

If the commit result is unknown, return `PENDING/UNKNOWN` or a retriable response with the reservation ID and a lookup mechanism. Never say “not reserved” when MongoDB may have already committed.

### 22.5. Key Reuse with Different Payload

Return a conflict, do not overwrite the old marker's data, and do not silently deduct the new quantity.

### 22.6. Time Scope

An idempotency ID must remain valid at least as long as clients/queues can replay. For inventory in financial or fulfillment systems, retention must also satisfy audit/compliance policies.

---

## 23. Decoupling Order State from Stock State

An order may be:

- `PENDING_PAYMENT` after reservation.
- `PAID` after successful payment.
- `CANCELLED` before fulfillment.
- `SHIPPED` when dispatched from the warehouse.
- `REFUNDED` after refund.

Reservations have their own lifecycle `ACTIVE/EXPIRED/RELEASED/FULFILLED`. Never infer:

- Paid == shipped.
- Refunded == returned to available stock.
- Cancelled callback == stock was definitely never deducted.
- Order creation == stock reservation already committed.

### 23.1. Multi-Document Transitions

If placing an order must create the order, reserve multiple SKUs, and emit an outbox event all-or-nothing, those documents must share a transaction or a saga with compensation. Never merely update inventory, call the order service, and assume two systems are automatically atomic.

### 23.2. Outbox Event

Example:

    {
      _id: "EVT-R100-RESERVED",
      reservation_id: "R100",
      type: "InventoryReserved",
      payload: {
        order_id: "ORD-101",
        quantity: NumberLong("2")
      },
      published_at: null
    }

Outbox inserts happen inside **the same MongoDB transaction**; a relay publishes after commit. If the relay crashes after publishing but before marking published, consumers can still receive duplicates and must deduplicate by event ID.

### 23.3. Never Charge Payment Inside a Transaction Callback

MongoDB cannot roll back a charge already sent to an external provider. Transaction callbacks can re-run; external effects require provider idempotency keys and dedicated state machines.

---

## 24. Multi-Tenant and Security

### 24.1. Trusted Tenant

In an HTTP service, `tenantId` must come from the authenticated principal/session, never solely from client JSON. All queries and writes include the tenant condition.

### 24.2. SKU and Warehouse Ownership

Backend-constructed stock IDs can include tenant, yet you must still verify that the SKU/warehouse belongs to the tenant, the user is authorized to place orders, and the stock bucket is active.

### 24.3. Avoid Mass Assignment

Never accept arbitrary request bodies containing `available`, `reserved`, `on_hand`, `tenant_id`, or `state` and map them straight into `$set`. Only privileged services control stock movements.

### 24.4. Do Not Log Secrets/PII

When debugging, log reservation ID, stock bucket ID, request fingerprint, matched/modified counts, transaction status, and retry count; redact customer/payment data.

### 24.5. Never Use Exception Details to Leak Cross-Tenant Data

If a request targets a stock ID belonging to another tenant, return a generic error per API policy. Keep detailed audits internal with restricted access.

---

## 25. Never Read Stale Secondaries to Confirm Reservations

MongoDB replica sets have a primary and secondaries; secondary reads can lag. A UI reading available from a secondary and showing “5 left” is not proof of availability when a reservation request hits the server.

### 25.1. The Source of Truth Is the Conditional Write

The `available>=quantity` predicate must live inside the write. If a client relies on a cached value to decide a sale, overselling can occur even with a fast cache.

### 25.2. Write Concern

`WriteConcern.MAJORITY` for transaction commits provides durability per replicated deployment semantics. It does not eliminate unknown commit outcomes over the network.

### 25.3. Read Concern and Outcome Lookups

After a timeout, inspect the reservation ledger using primary/appropriate read concern while accounting for lag and in-flight transactions. A single read missing the marker does not prove failure.

### 25.4. Retryable Writes vs. At-Least-Once Delivery

Driver protocol retries do not guarantee exactly-once effects across an HTTP/event architecture. Business IDs and ledgers remain essential.

---

## 26. Reconciliation: Finding Stock Counters Diverging from the Ledger

If the model defines `reserved` as the sum of quantities across ACTIVE reservations, we can compute it from the ledger:

    db.inventory_reservations.aggregate([
      {
        $match: {
          tenant_id: "tenant-a",
          state: "ACTIVE"
        }
      },
      {
        $group: {
          _id: "$stock_id",
          ledger_reserved: { $sum: "$quantity" },
          reservation_count: { $sum: 1 }
        }
      },
      {
        $lookup: {
          from: "inventory",
          localField: "_id",
          foreignField: "_id",
          as: "bucket"
        }
      },
      {
        $unwind: {
          path: "$bucket",
          preserveNullAndEmptyArrays: true
        }
      },
      {
        $project: {
          _id: 1,
          ledger_reserved: 1,
          inventory_reserved: "$bucket.reserved",
          difference: {
            $subtract: [
              { $ifNull: ["$bucket.reserved", 0] },
              "$ledger_reserved"
            ]
          }
        }
      },
      {
        $match: {
          difference: { $ne: 0 }
        }
      }
    ]);

### 26.1. Query Limitations

Because the pipeline starts from ACTIVE reservations, it does not list buckets that have **no ACTIVE reservations** yet still have a non-zero reserved counter. A separate query is required for that case.

### 26.2. Concurrent Changes

While writes are occurring, a long query may observe inconsistent points in time depending on read concern and execution semantics. Use appropriate snapshots or repeat reconciliation and account for the consistency window; never immediately patch a transient mismatch.

### 26.3. Ledgers Must Match the Contract

If a `CONFIRMED` state also holds stock or if reserved includes backorders, adjust predicates/groups accordingly. Never replace the invariant with a domain-inaccurate quick script.

### 26.4. Never Overwrite Counters Blindly

When a discrepancy appears, inspect reservation events, order states, movement ledgers, physical stock, and concurrency. Fix via audited adjustments with unique operation IDs, not by blindly setting numbers to match.

---

## 27. Detecting Negative Counters and Inconsistencies

Negative counters:

    db.inventory.find({
      tenant_id: "tenant-a",
      $or: [
        { available: { $lt: 0 } },
        { reserved: { $lt: 0 } },
        { on_hand: { $lt: 0 } }
      ]
    });

Checking the equation in the simple model:

    db.inventory.find({
      tenant_id: "tenant-a",
      $expr: {
        $ne: [
          "$on_hand",
          {
            $add: [
              "$available",
              "$reserved"
            ]
          }
        ]
      }
    });

### 27.1. When Null/Missing Exists

`$add` and BSON type comparisons require valid numeric data. If a legacy collection has null/string/missing fields, classify invalid types first so results are not misinterpreted.

### 27.2. Do Not Equate Physical Audits with the Ledger

`on_hand = available + reserved` is only internal consistency; physical counts can differ due to shrinkage, damaged stock, or unrecorded receipts. Cycle counting is a separate process.

### 27.3. When Drift Is Detected

Record the incident ID, tenant/SKU/warehouse, list of relevant reservation/movement IDs, timestamps, versions, and writers; apply corrections based on the designated source of truth.

---

## 28. Metrics and Alerting

| Suggested metric | What it detects |
|---|---|
| `inventory_negative_count` | Stock buckets with negative numbers |
| `inventory_invariant_mismatch_count` | on_hand differs from available+reserved |
| `inventory_ledger_drift_count` | Reserved counter diverges from ACTIVE ledger |
| `reserve_new_success_total` | New business reservations actually committed |
| `reserve_duplicate_total` | Retries validly deduplicated |
| `idempotency_conflict_total` | Same key with different payload |
| `reserve_insufficient_total` | Out of stock |
| `transaction_write_conflict_total` | Contention |
| `transaction_unknown_commit_total` | Unresolved commit outcomes |
| `reservation_expired_active_backlog` | Expired holds not yet released |
| `release_duplicate_total` | Duplicate cancel/expiry callbacks |
| `fulfillment_duplicate_total` | Duplicate ship callbacks |
| `queue_redelivery_total` | At-least-once replays |
| `reserve_latency_p95/p99` | SLOs and hot SKU pressure |
| `reconciliation_lag_seconds` | Repair/reconciliation lag |

These names are example application metrics, not built-in default `mongod` metrics.

### 28.1. Count Business Effects, Not Retries

A retry of R100 returning ALREADY_RESERVED is not a new reservation. Counting it as a new sale corrupts reports even if stock was not deducted twice.

### 28.2. Critical Alerts

Negative counts >0, persistent drift, unresolved unknown commits, steadily growing expiration backlogs, duplicate spikes, or excessive hot-SKU latency require investigation.

---

## 29. Concurrency Test: Two Orders, One Item

Setup:

    available=1
    reserved=0
    on_hand=1

Two requests with **different IDs** A and B, both qty=1, run concurrently.

Correct result:

    A RESERVED, B OUT_OF_STOCK
    or B RESERVED, A OUT_OF_STOCK

    available=0
    reserved=1
    on_hand=1
    ACTIVE reservations count=1

Both requests must never succeed.

### 29.1. Barrier/Parallel Execution

Use two threads or two service instances, synchronize on a barrier, and fire requests together. Repeat the test many times to raise race likelihood, while remembering this does not replace proving atomic query semantics.

### 29.2. Inspect Raw BSON

Read counters and the ledger directly from MongoDB at the end of the test, rather than relying solely on HTTP responses.

### 29.3. Do Not Use Locks in Tests That Mask Races

If requests fail to run truly in parallel due to a local lock, the test may pass while the distributed service remains broken.

---

## 30. Double-Decrement Test: Same ID When Plenty of Stock Exists

Setup:

    available=10
    reserved=0
    on_hand=10
    request R100 qty=2

Send R100 twice, both sequentially and concurrently.

Correct result:

    First R100 -> RESERVED
    Retry R100 -> ALREADY_RESERVED

    available=8
    reserved=2
    on_hand=10
    ACTIVE marker R100 count=1

If available=6, you have prevented overselling but **failed to prevent double decrements**.

### 30.1. Payload Mismatch

R100 sent first with q=2 and later with q=5 must return a conflict and leave stock untouched.

### 30.2. Unknown Outcome

Simulate disconnect/timeout after commit, then retry with the same key. Never let a new request generate a different key.

### 30.3. Concurrent Duplicate Key

Two transactions insert R100 simultaneously; one may receive a duplicate key or write conflict. The handler must reconcile the marker rather than returning a false failure or deducting again.

### 30.4. Retention

Replay R100 after the longest queue retention window. If markers were purged, verify the architecture still blocks stale duplicates.

---

## 31. State Machine and Failure Tests

Mandatory scenarios:

1. Double cancel R100: available increments only once.
2. Double ship R100: on_hand decrements only once.
3. Cancel vs. ship: only one terminal transition commits.
4. Expire vs. payment: state is never both EXPIRED and FULFILLED.
5. Crash between marker insert and stock decrement: transaction rolls back both.
6. Crash after transaction commit but before HTTP response: retry is idempotent.
7. One SKU sufficient, another insufficient: all-or-nothing order transaction rolls back.
8. Two SKUs hitting the same stock bucket: total quantity is accurate, no double counting.
9. Warehouse wrong tenant: update does not match or is denied authorization.
10. Missing inventory record: never creates negative stock via upsert.
11. Qty=0/negative/over max: rejected without writing.
12. Mixed BSON int32/int64/null: validation/decoding is never bypassed.
13. Replica primary stepdown: retry/reconciliation handles uncertainty.
14. Consumer redelivery: same movement ID never re-adds or re-deducts.
15. Expiry worker restart: never releases the same reservation twice.

### 31.1. Test on a Replica Set

Transaction behavior cannot be fully verified on a standalone mongod. Use a test replica set (single-member works) with JUnit/Testcontainers or an equivalent harness.

### 31.2. Fault Injection

Disconnect right around commit, kill workers mid-step, duplicate messages, and reorder callbacks. Verify the **final database state**, not merely exception types.

---

## 32. Hot SKUs, Sharding, and Performance

### 32.1. One Hot Document Remains a Contention Point

Even in a sharded cluster with many shards, a very hot SKU's inventory bucket still updates one document. Sharding does not let multiple writers freely decrement the same counter without coordination.

### 32.2. Conditional Updates Are Very Cheap by ID

`_id` has a default index. When queries target a unique stock ID and tenant check, an index on `available` is usually unnecessary just for reservations; indexing a rapidly changing field increases write cost.

### 32.3. Escrow/Quota Buckets

An advanced architecture splits sellable quota into multiple buckets, each with its own conditional decrement. However, total initial quota must never exceed physical stock; transferring quota between buckets requires transactions/fencing and reconciliation. Never split counters arbitrarily and sum them unchecked.

### 32.4. Caching

You can cache available counts for display, yet reservation success must come from the database write. Cached/stale data or expired Redis leases cannot protect invariants when the database is the source of truth.

### 32.5. Proper Benchmarking

Measure throughput, p95/p99 latency, write conflict rates, transaction retries, primary CPU, replication lag, and reconciliation backlogs on hot SKUs. Never claim a fixed throughput number applies across all deployments.

---

## 33. Runbook When Double Decrements Are Detected

### Step 1 — Stabilize

- Throttle retry storms/redeliveries.
- Pause faulty writers via feature flag if available.
- Never delete reservation/movement proofs.
- Never run collection-wide stock addition scripts before understanding the impact.

### Step 2 — Scope

Identify tenant, warehouse, SKU, reservation ID, order line, request ID, timestamps, retry counts, application version, and worker.

### Step 3 — Compare Sources

Inventory counters, reservation ledger, movement IDs, order state, payment/shipping events, and transaction/driver errors. Check whether two distinct IDs were created for one checkout or the same ID ran twice.

### Step 4 — Root Cause

- Missing key?
- Key regenerated?
- Marker not atomic with decrement?
- Fresh `$inc` retried after unknown outcome?
- Release/ship callback ran repeatedly?
- TTL deleted proof too early?
- Legacy writer bypassed the protocol?

### Step 5 — Correction

Use audited adjustments with unique movement IDs, authorized scope, CAS/transactions, and reconciliation. Never silently set available based on estimates.

### Step 6 — Prevent Recurrence

Add stable IDs/unique indexes/transactions/state CAS, fix retry policies, extend retention, and add multi-instance/fault-injection tests.

---

## 34. Runbook for Overselling or Negative Available

### Step 1 — Stop Inaccurate Promises

Temporarily block reservations for the affected hot SKU/bucket within incident policy, without arbitrarily halting unrelated payment/fulfillment systems.

### Step 2 — Inspect Write Paths

- Any read–modify–save?
- Missing `available>=qty` in update filters?
- Any `upsert:true`?
- Any negative qty?
- Any job/script setting available directly?
- Wrong warehouse/tenant ID?
- Duplicate stock buckets?

### Step 3 — Inspect Affected Orders

If two orders were confirmed for one unit, business workflows must resolve oversold orders/backorders/refunds; fixing counters alone is insufficient.

### Step 4 — Reconcile

Cross-check reservations, movements, physical stock, queue events, and audit records.

### Step 5 — Controlled Repair

Use unique adjustment movements + transactions and verification; never edit multiple stock buckets haphazardly while live concurrent traffic runs.

### Step 6 — Monitor

Ensure alerts for negative counters, idempotency conflicts, unknown commits, and drift return to acceptable thresholds.

---

## 35. Anti-Patterns to Avoid

| Anti-pattern | Why it is wrong | Replace with |
|---|---|---|
| `find` then `save` without CAS | Races, lost updates | Atomic conditional `updateOne` |
| Checking available only in Java | Check and write separated in time | `available >= q` in the filter |
| Blind `$inc` retries | Double decrement | Stable operation ID + ledger |
| New UUID per retry | Defeats deduplication | Preserve request ID |
| Separate marker insert then decrement | Crash creates false success | Transaction |
| Decrement then insert marker | Crash causes duplicate effect | Transaction |
| Treating duplicate key as always success | Could be key reuse with changed payload | Compare fingerprint/state |
| Treating timeout as rollback | Commit may have succeeded | Reconcile unknown outcome |
| `upsert:true` when reserving | Can insert unintended records | Update-only |
| `$addToSet` marker without filter | `$inc` can still execute | Dedupe filter + atomic write |
| Unbounded array of IDs | BSON 16 MiB/hotspot | Separate reservation collection |
| TTL deleting ACTIVE markers | Fails to release stock, loses proof | Expiration worker transaction |
| Two cancels both `$inc +q` | Double release | State CAS |
| Two ships both `$inc -q` | Double decrement on_hand | State CAS |
| JVM-only locking | Fails across multiple instances | Database atomicity |
| Reading secondary to decide reserve | Stale available | Predicate at write time |
| Refund directly increments available | Goods may not have returned | Return/inspection workflow |
| Counting only API successes | Retries counted as business events | Metrics by unique IDs |
| Assuming validator minimum=0 suffices | Does not stop duplicate effects | Ledger/transaction |
| Overwriting counters on drift | Masks root cause | Audited reconciliation |

---

## 36. Pre-Deployment Checklist

### 36.1. Data Model

- [ ] `on_hand`, `available`, `reserved` have clear contracts.
- [ ] Single unique bucket per tenant/warehouse/SKU.
- [ ] Consistent numeric types and valid bounds.
- [ ] Reservations have stable IDs and immutable request fields.
- [ ] Terminal states cannot revert to ACTIVE under the same ID.
- [ ] Movement IDs for receive/ship/return/adjust/transfer.
- [ ] Idempotency retention exceeds the replay window.

### 36.2. Concurrency

- [ ] `available>=q` filter enforced directly on the write.
- [ ] `$inc` on available/reserved in the same document update.
- [ ] Qty>0, bounds/overflow checked.
- [ ] No upsert on reserve.
- [ ] Ledger marker + stock effect in the same transaction.
- [ ] Release/expire/ship protected by state CAS.
- [ ] Multi-SKU all-or-nothing covered by transactions.
- [ ] Transient/write-conflict retries bounded with no external side effects inside callbacks.

### 36.3. System Correctness

- [ ] Unique business keys and fingerprints.
- [ ] Duplicate requests return the prior outcome.
- [ ] Unknown commits have lookup/reconciliation.
- [ ] Outbox publishing and consumer deduplication.
- [ ] Tenant authorization on every operation.
- [ ] Appropriate schema validation and indexes.
- [ ] No TTL deletion of ACTIVE markers.
- [ ] Monitoring for negative/drift/duplicate/unknown anomalies.
- [ ] Concurrency + crash + message replay tests on a replica set.

---

## 37. Hands-On Exercises

1. **Invariant:** Given on_hand=20 and reserved=5, calculate available. If reserved=23, diagnose.
2. **Stock bucket:** Create an Int64 `inventory` document by tenant+warehouse+SKU.
3. **Index:** Create a compound unique index for buckets. Test inserting a duplicate.
4. **Atomic decrement:** Write `updateOne` with available≥q, decrementing available and incrementing reserved.
5. **Race:** Stock=1, two requests with distinct IDs qty=1. Prove only one succeeds.
6. **Input:** Test qty=0, negative, huge, null, and string.
7. **Result:** Distinguish matched=0 due to insufficient stock vs. missing bucket.
8. **Double decrement:** Stock=10, send the same request twice without a ledger; observe the bug.
9. **Stable key:** Generate deterministic reservation IDs per order line/attempt.
10. **Fingerprint:** Resend the same ID with a different quantity; must conflict.
11. **Unique ledger:** Create `inventory_reservations` and appropriate unique indexes.
12. **Marker-first crash:** Insert marker then crash before stock decrement; describe the discrepancy.
13. **Effect-first crash:** Decrement before marker then crash; explain why retries fail.
14. **Transaction:** Insert marker + conditional decrement inside a transaction.
15. **Duplicate concurrency:** Two transactions both with R100; handle duplicate key via reconciliation.
16. **Unknown commit:** Simulate lost commit ACK and retry R100 without deducting twice.
17. **Spring Data:** Write a MongoTemplate conditional update and integrate MongoTransactionManager.
18. **Version:** Compare expected version CAS with an idempotency ID.
19. **Double cancel:** Two CANCEL callbacks release stock only once.
20. **Expire worker:** Transition overdue ACTIVE to EXPIRED and release inside a transaction.
21. **TTL:** Explain why TTL on ACTIVE markers corrupts stock.
22. **Ship:** ACTIVE→FULFILLED decrements reserved/on_hand while leaving available unchanged.
23. **Expire vs. ship:** Run concurrently; only one terminal transition commits.
24. **Multi-SKU:** One line sufficient, one insufficient; all-or-nothing holds nothing partially.
25. **Multi-warehouse:** Allocate 5 items across HCM=3 and HN=4 per policy.
26. **Receive:** Duplicate inbound event; use unique movement ID to avoid double-crediting.
27. **Reconciliation:** Sum ACTIVE reservations and compare against inventory.reserved.
28. **Monitoring:** Design a dashboard for negative counts, drift, retries, and expiration backlogs.
29. **Security:** Prevent clients from supplying tenant_id or modifying counters directly.
30. **Production design:** Diagram order/reserve/payment/ship/cancel/expire/outbox with retries, transactions, tests, and runbooks.

---

## 38. Review Questions

1. How does `on_hand` differ from `available` and `reserved`?
2. When does `on_hand=available+reserved` stop holding?
3. Why is a single unique inventory bucket needed per tenant–warehouse–SKU?
4. What does MongoDB's single-document atomicity protect?
5. Why can read–modify–save oversell without available turning negative?
6. What does `$gte` in the update filter do?
7. Why must `$inc` on available and reserved be in the same command?
8. Why must negative quantities be rejected?
9. Why is `upsert:true` unsuitable when reserving?
10. Does matched=0 always mean out of stock?
11. When available=1, what must happen for two requests with different IDs and qty=1?
12. Why does a conditional decrement not prevent duplicate requests on its own?
13. Do driver retryable writes protect against new HTTP replays?
14. At what business level should a stable idempotency key be created?
15. Why does generating a new UUID per retry break deduplication?
16. Can the same ID with a different quantity be treated as a valid retry?
17. What problem does a unique reservation marker solve?
18. Why must the marker and stock effect share the same transaction?
19. What two failure modes occur when crashing between two separate writes?
20. When a duplicate key occurs, when do you return already reserved?
21. When must a duplicate key return a conflict?
22. How do `TransientTransactionError` and `UnknownTransactionCommitResult` differ?
23. Why does a timeout not prove a rollback?
24. Why look up the reservation marker after a timeout instead of just reading available?
25. What are ReadConcern.SNAPSHOT and WriteConcern.MAJORITY used for?
26. Why must a transaction callback never charge a payment?
27. How does ACTIVE→RELEASED affect counters?
28. Why does checking reserved>=q fail to prevent double release?
29. How does CAS ACTIVE→RELEASED prevent updating twice?
30. How does ACTIVE→FULFILLED differ from RELEASED regarding on_hand?
31. Why does a refund not mean inventory returned?
32. Does a TTL index automatically release stock?
33. What must the expiration worker do inside the same transaction?
34. How is competition between expire and a payment callback resolved?
35. When is a transaction needed for a multi-SKU order?
36. When is partial reservation valid?
37. Why must quantities for duplicate stock buckets be merged?
38. Is a hot SKU automatically distributed by sharding alone?
39. Why is cached available insufficient to decide a reservation?
40. What limitations does a single-document applied IDs array hit?
41. Does standalone `$addToSet` prevent `$inc` on duplicate IDs?
42. Does optimistic versioning replace an idempotency key?
43. Why do receive/adjust/transfer need movement IDs?
44. Which crash window does an outbox close?
45. Does an outbox guarantee messages are published exactly once?
46. Why do downstream consumers need deduplication?
47. Which metrics detect negative stock and ledger drift?
48. Can reconciliation observe temporary mismatches during concurrent writes?
49. Why not silently set available to a newly measured count without an audit?
50. Which tests prove both overselling and double decrements are prevented?

---

## 39. Summary

A reliable inventory system in MongoDB must simultaneously protect **quantities, business identities, states, and recoverability**:

1. **Preventing overselling:** use `updateOne` with `available>=quantity` directly at write time, updating available−q and reserved+q in the same document.
2. **Preventing double decrements:** use stable reservation IDs, unique markers, fingerprints, and durable outcomes; never retry `$inc` as a fresh operation.
3. **Atomicity between ledger and stock:** when markers and inventory span two documents, use multi-document transactions or another proven protocol; never accept marker-first/effect-first crash windows.
4. **State machine:** reserve, release, expire, and fulfill must use CAS/transactions to stop double releases, double shipments, and callback races.
5. **Multi-SKU/multi-warehouse:** all-or-nothing requires transactions; partial fulfillment requires explicit state.
6. **External integrations:** payments/shipping/brokers/outboxes need independent retries and idempotency; never equate payment success with shipped stock.
7. **Operations:** unique indexes, schema validation, tenant isolation, monitoring, reconciliation, retention, and concurrency fault tests matter just as much as the update statement itself.

**The final test:** If MongoDB commits a decrement of 2 units, the HTTP response is lost, and the same request is resent while plenty of stock remains, can your system **prove** that the second attempt made zero changes to inventory? If not, your system only has an atomic decrement, not an idempotent inventory operation.

## References

- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions in Applications](https://www.mongodb.com/docs/manual/core/transactions-in-applications/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/)
- [MongoDB Manual — `$inc`](https://www.mongodb.com/docs/manual/reference/operator/update/inc/)
- [MongoDB Manual — `$gte`](https://www.mongodb.com/docs/manual/reference/operator/query/gte/)
- [MongoDB Manual — `$setOnInsert`](https://www.mongodb.com/docs/manual/reference/operator/update/setOnInsert/)
- [MongoDB Manual — `$addToSet`](https://www.mongodb.com/docs/manual/reference/operator/update/addToSet/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [Spring Data MongoDB — Template CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB — Client Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking)
