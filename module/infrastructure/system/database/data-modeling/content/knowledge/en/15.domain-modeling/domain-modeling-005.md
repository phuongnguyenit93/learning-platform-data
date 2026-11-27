# Referencing Between Aggregates by Identifier

## Learning Objectives

After this lesson, you will be able to:

- Explain why relationships **between two aggregates** are usually expressed using **the identifier of the aggregate root** rather than embedding and directly mutating the entire target object.
- Distinguish ID references, database foreign keys, data **snapshots**, and read-only replicated data.
- Design identifiers with explicit scope, stability, and semantics; apply strongly typed IDs to avoid mixing up objects.
- Decide when to verify the existence, state, or access permissions of a reference and handle cases where the source changes, is deleted, or is not yet synchronized.
- Map cross-aggregate relationships to relational, document, graph, and analytical models while protecting invariants and write paths.
- Recognize risks related to transactions, concurrency, data integrity, and authorization when moving from business diagrams to physical design.

In the **DATABASE_DATA_MODELING** module, many relationships in business requirements do not mean all entities must be loaded and written together. For example, an order belongs to a customer, includes items from a catalog, and holds reservation results from inventory. The system needs to **link** those pieces of information, yet each data group has its own owner and lifecycle. Referencing by identifier is how we express that boundary directly in the model.

## 1. An Identifier Is a Link, Not Ownership

An **aggregate** is a group of objects with an **aggregate root** responsible for protecting invariants that must remain consistent within a local transaction. **Referencing by identifier** means an aggregate holds the identity value of another root—for example, `Order` holds `customerId` instead of embedding a mutable full `Customer` object.

Suppose a sales system has four aggregates:

| Aggregate | Data owner and main invariants | Root identifier |
| --- | --- | --- |
| Customer | Profile, account status, current contact details | `customerId` |
| Product | Item code, name, and current catalog listing details | `productId` |
| Order | Line items, locked-in prices, transaction info, and order status | `orderId` |
| StockReservation | Stock reservation rights, expiration, and reservation outcome | `reservationId` |

The relationships can be expressed as:

~~~mermaid
flowchart TB
    U["Use case: Place order"]
    U --> O

    subgraph SALES["Sales — Order Aggregate"]
        O["Order root<br/>orderId, customerId"]
        L["OrderLine<br/>productId, priceSnapshot"]
        O -->|"manages order lines"| L
    end

    C["Customer root"]
    P["Product root"]
    R["StockReservation root"]
    O -.->|"customerId"| C
    L -.->|"productId"| P
    O -.->|"reservationId (when present)"| R
~~~

Solid lines represent members coordinated by `Order`. Dashed lines represent **links by identifier**. Customer data may change email; Catalog may change prices; inventory may expire a reservation—yet `Order` retains its own identity and update rules.

An ID reference **does not mean** the target root is loaded in memory, guaranteed to exist at read time, or mutable by the code holding the ID. Any operation affecting a referenced aggregate must go through its authoritative owner.

### Three Concepts to Distinguish

| Concept | Where does it live? | What does it guarantee? | What does it NOT guarantee automatically? |
| --- | --- | --- | --- |
| **Domain ID reference** | Attribute or value object in the model | Expresses which other object the business logic refers to | Existence, latest state, or access permission |
| **Foreign key** | Relational database schema | Depending on configuration, ensures the key points to an existing row in the same database | Record belongs to the right context, writer is authorized, or business state is valid |
| **Snapshot** | Historical data stored by the consumer | Preserves values at a defined point in time | Automatic synchronization with current source data |

These three tools can **be used together** depending on requirements. DDD commonly encourages linking via root IDs to reduce model coupling; there is no rule banning foreign keys for every ID reference in every system.

## 2. Why Not Reference Directly by Object?

Imagine the `Order` class holds a `Customer` object field, `Customer` holds a list of `Order`s, and `Product` holds purchased `OrderLine`s. If any operation can traverse fields and mutate data, problems emerge:

1. **Unclear write authority:** changing the delivery address on an `Order` could accidentally alter the `Customer` profile used for other orders.
2. **Coupled lifecycles:** deleting a `Product` might be interpreted as having to delete historical `Order` lines.
3. **Excessive data loading:** loading one `Order` could pull in `Customer`, all of that Customer's orders, and the entire related `Product` tree.
4. **Ambiguous transactions:** developers might assume mutating an object graph is one atomic transaction even when data lives in multiple aggregates or services.
5. **Hard to evolve:** changing `Product`'s internal structure forces `Sales` code to know the new details even though `Sales` only needs `productId` and the locked-in price.

Using **`customerId`**, **`productId`**, and access contracts makes it explicit: `Order` knows **which object**, without implicitly owning that object's **internal state**.

> Useful design rule: **from outside an aggregate, interact through that aggregate's root; relationships with other aggregates are primarily expressed using the root's ID**. In some implementations, related objects may be loaded for reading, but never let that reference become a write path bypassing ownership.

## 3. Choosing Identifiers with the Right Semantics and Scope

A good ID answers three questions: **what kind of object** does it identify, **within what scope** is it unique, and is it **stable across the lifecycle**?

### 3.1. Business IDs and Storage Keys

For example, a `Product` has an internal UUID and a SKU code like `LAPTOP-14`. A SKU may change when a business reclassifies, reuses, or merges catalogs; a UUID may be more stable as a linking key. Conversely, in some domains, the SKU itself is a strictly governed identity. There is no blanket formula to pick UUID for every problem: first ask the business whether the code can change or collide across warehouses or sellers.

| Identifier type | Example | Risks to consider |
| --- | --- | --- |
| Internally generated key | `UUID`, `BIGINT` identity | When exposed externally, requires exposure, mapping, and stability policies |
| Business code | `orderNumber`, `contractCode` | Format, uniqueness scope, or generation rules per year/branch may change |
| Scoped composite key | `(tenantId, productId)`, `(offeringId, seatNo)` | Dropping the scope part can point to the wrong object |
| Partner system ID | `externalCustomerId`, `paymentProviderId` | Unique only within that provider/namespace; must be distinguished from internal IDs |

**Do not use email, phone number, or person name as the default ID:** those values can change and also carry personal data that does not belong in every integration record.

### 3.2. Tenant and Namespace Scope

In a **multi-tenant** system, product ID 42 in tenant A may differ from product ID 42 in tenant B. In that case, the complete identifier is `(tenantId, productId)`, unless products are assigned globally unique IDs under a strictly enforced rule.

A query filtering only by `product_id = 42` could return another organization's record; therefore, tenant scope must flow through schemas, APIs, queries, and authorization policies.

**An ID is not an access pass.** Knowing a UUID does not authorize a user to read or modify that aggregate. Application services must still verify permissions on the object and tenant; the database layer can add Row-Level Security or an equivalent mechanism.

### 3.3. Dedicated ID Types in Source Code

If `customerId` and `productId` are both raw `UUID`s, swapping the two arguments may go undetected by the compiler. You can wrap IDs in value objects:

~~~java
import java.util.Objects;
import java.util.UUID;

record CustomerId(UUID value) {
    CustomerId {
        Objects.requireNonNull(value);
    }
}

record ProductId(UUID value) {
    ProductId {
        Objects.requireNonNull(value);
    }
}

record OrderId(UUID value) {
    OrderId {
        Objects.requireNonNull(value);
    }
}

record ProductReference(ProductId productId, String nameSnapshot) {
    ProductReference {
        Objects.requireNonNull(productId);
        Objects.requireNonNull(nameSnapshot);
    }
}

final class Order {
    private final OrderId id;
    private final CustomerId customerId;

    Order(OrderId id, CustomerId customerId) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
    }

    OrderId id() { return id; }
    CustomerId customerId() { return customerId; }
}
~~~

Here **`CustomerId`** is a value object identifying another **`Customer` entity**. There is no contradiction: the ID value has no independent business lifecycle, while the object it identifies remains an entity with identity. When mapping to SQL, ID wrappers can be unwrapped to `UUID`; saving and reconstituting must preserve the exact ID type.

## 4. ID, Snapshot, or Embedded Object: Deciding by Need

Let us analyze an order's requirements:

| Need | Appropriate representation | Rationale |
| --- | --- | --- |
| Know which customer placed the order to query the owner | `customerId` | Links to `Customer` with its own lifecycle |
| Save recipient name and delivery address at confirmation | `recipientNameSnapshot`, `shippingAddressSnapshot` | Preserves the transaction even if the customer profile changes |
| Record which item was purchased | `productId` | Cross-references catalog or traces business origin |
| Preserve item name, purchase price, currency at checkout | `productNameSnapshot`, `priceSnapshot` | Catalog's price and name today may differ from purchase day |
| Change a line's quantity in a DRAFT Order | `OrderLine` managed by `Order` | Status and total invariants belong to `Order` |
| Display the customer's current name on an admin screen | Query `Customer` or a read model | Needs latest data or bounded staleness |
| Store a valid stock reservation outcome | `reservationId`, received outcome status, expiration | Does not directly mutate `StockReservation` from `Order` |

**Snapshots and IDs complement each other.** Using only a snapshot loses the link back to the source object; using only an ID and reading current data alters historical meaning. Only when an object's lifecycle directly depends on the root and must be mutated alongside the root should you consider placing it **in the same aggregate**.

For pure read data, do not build a massive aggregate. Use composed queries or dedicated projections; read models answer different questions than write models.

## 5. What Is Guaranteed When Linking by ID?

A reference does not automatically create consistency. Distinguish three levels of validation:

1. **Structurally valid:** the ID has the right type and valid scope. For instance, `productId` is a UUID and `tenantId` is populated.
2. **Actually exists:** the referenced object exists according to the authoritative source at the time of check.
3. **Eligible for use:** the object is in a suitable business state. A `Product` may exist yet be discontinued; a `Customer` may exist yet be suspended.

These levels may need checking at different moments. For example:

- When **creating a DRAFT Order**, Sales may need to verify the Customer belongs to the tenant and the Product is currently orderable.
- When **confirming an Order**, Sales must verify conditions critical at confirmation time—for example, the accepted price matches a valid quote version and the stock reservation has not expired.
- When **reading a historical Order**, Sales does not necessarily require the Product to still be on sale. Purchased details are preserved via snapshots.

If a Customer is deleted after an Order is confirmed, that does not mean the Order immediately becomes invalid. You need lifecycle and archival policies: retain identifiers for auditability where legal, anonymize personal data per regulations, or record a tombstone for deactivated objects.

### The Time Window Between Check and Write

Consider this sequence:

~~~text
T1: Sales asks Catalog: Is Product P available for sale? -> Yes
T2: Catalog changes P to DISCONTINUED
T3: Sales writes Order referencing P
~~~

Checking at T1 does not guarantee Product state remains unchanged at T3. This is the **time-of-check to time-of-use (TOCTOU)** problem. Handling it must fit business rules:

- If orders rely on an **active quote**, obtain a `quoteId`/version with a committed validity window and confirm under that contract.
- If the Product must strictly be on sale **at the exact moment of confirmation**, place the confirmation check at the Product owner or use a protocol with an explicit linearization point; a casual pre-check request can become stale immediately after returning.
- If "was published when creating DRAFT" is sufficient, a snapshot with timestamp and verification source may suffice.

Referencing by ID forces you to state **which commitment is truly needed**; placing two IDs side by side does not solve race conditions by itself.

## 6. Mapping to SQL: Internal Foreign Keys, Cross-Aggregate IDs

In the following PostgreSQL example, Sales owns `Order` and `OrderLine`. Customer and Catalog are separate models that may live in the same or different databases; Sales stores their IDs without managing their lifecycles.

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.orders (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    recipient_name_snapshot TEXT NOT NULL,
    shipping_address_snapshot JSONB NOT NULL
        CHECK (jsonb_typeof(shipping_address_snapshot) = 'object'),
    status VARCHAR(16) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE sales.order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id UUID NOT NULL,
    sku_snapshot TEXT NOT NULL,
    product_name_snapshot TEXT NOT NULL,
    unit_price_amount NUMERIC(19, 2) NOT NULL
        CHECK (unit_price_amount >= 0),
    currency_code CHAR(3) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.orders(tenant_id, order_id)
);

-- Query orders for a customer within a tenant ordered by time.
CREATE INDEX orders_by_customer
    ON sales.orders(tenant_id, customer_id, created_at DESC);
~~~

Domain-meaningful decisions:

- **Primary key `(tenant_id, order_id)`** scopes Orders to a tenant. `OrderLine` references `Order` via a **composite FK** so it can never accidentally link to a row from another tenant.
- **`customer_id`** and **`product_id`** are ID references to other roots. Sales code knows which objects are involved, without automatically granting write access to Customer or Catalog.
- **`recipient_name_snapshot`**, **`shipping_address_snapshot`**, **`product_name_snapshot`**, and **`unit_price_amount`** capture details at defined business moments. The application layer must agree on when snapshots are locked in.
- **`CHECK`** protects per-row validity; it does not check whether the Product is currently sellable or the Customer is permitted to buy. Cross-source constraints belong to business contracts.
- The `orders_by_customer` index serves an assumed real query; other indexes should come from actual workloads and query plans rather than creating every imaginable index upfront.

### Should You Use Foreign Keys from Sales to Catalog or Customer?

There is no absolute ban or mandate:

| Deployment condition | Cross-aggregate FK can help when | Considerations when deciding |
| --- | --- | --- |
| Same database and same lifecycle owner | You want the DB to block dangling references and govern deletes uniformly | FKs do not enforce business state; `ON DELETE CASCADE` can destroy history |
| Same database but independent bounded contexts | You intentionally accept coupling within a stable monolith | Migrations, permissions, and delete timing become coupled across contexts |
| Different databases/services | Direct SQL FKs across independent DBs are not possible | Requires APIs/events, command-time checks, dangling-data policy, and reconciliation |

The pattern above omits direct FKs to Customer/Product because owners may deploy independently. That is an **architectural choice**; omitting FKs does not mean permitting garbage references. You must define validation mechanisms, lifecycle events, and ways to repair broken links.

### Transactions and Optimistic Locking Remain Needed on the Owning Aggregate

`OrderLine` belongs to `Order`, so every line edit must obey `Order`'s status and version:

~~~sql
BEGIN;

UPDATE sales.orders
SET version = version + 1
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND status = 'DRAFT'
  AND version = :expected_version;

-- Must verify exactly one row was updated.
-- If 0, ROLLBACK and handle conflict or access error.

UPDATE sales.order_line
SET quantity = :new_quantity
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND line_no = :line_no;

-- Verify exactly one row and :new_quantity > 0.
-- Otherwise, ROLLBACK the entire transaction.

COMMIT;
~~~

All write paths on `Order` must obey the shared lock/version protocol; if other code mutates `OrderLine` directly without checking the root's version, invariants can be broken. Referencing `Product` does not expand Sales's transaction scope into Catalog.

## 7. Lifecycle and Integrity of References

A reference can become unreachable because the source object is deleted, merged, moved across tenants, or re-keyed. The design must explicitly specify behavior:

| Scenario | Decision needed |
| --- | --- |
| Product is discontinued | Preserve past orders and snapshots; block or conditionally allow new orders per policy |
| Customer is temporarily suspended | Decide whether new orders are blocked; do not automatically delete order history |
| Customer is deleted or requests personal data erasure | Separate data required for legal/audit retention from data to anonymize/erase; avoid arbitrary cascades |
| Two Customers are merged | Store old ID -> canonical ID mapping or alias policy; decide whether historical references are updated |
| Referenced ID not found on read | Show snapshot or "no longer available" status, log anomaly for reconciliation; do not auto-create a stub object |
| Change message arrives late | Use source version/sequence, rules to discard stale events, and resynchronization mechanisms |

**Delete policies** must be decided at the business level. Cascading deletes from `Customer` to `Orders` are usually inappropriate when finalized orders must be retained for accounting/audit. In other cases, child entities wholly dependent on a root can be deleted with the root; that is an internal relationship with a different policy.

If a reference uses an ID from an external system, record the **namespace/issuer** alongside the ID whenever collisions are possible—for example, `(provider, providerCustomerId)`. If a partner changes its codes, let the integration layer maintain a stable mapping table rather than forcing every consuming aggregate to translate on its own.

## 8. Integration via Contracts: IDs Must Carry Exact Meaning

When data lives in another service, design explicit contracts for IDs, versions, timestamps, and publishers. Example of a Catalog event published when a Product is discontinued:

~~~json
{
  "eventId": "f64999db-d6e9-47a9-b1c4-1152798fd632",
  "eventType": "ProductDiscontinued",
  "productId": "8415699d-8119-4b28-aaf8-9e95c46c5a33",
  "tenantId": "98094b91-18cb-4be1-aa9e-a1e8ce79e594",
  "productVersion": 18,
  "occurredAt": "2026-11-20T09:00:00Z",
  "reason": "END_OF_LIFE"
}
~~~

A confirmed Order does not need to change its price or name; Sales can consume the event to update search projections or mark the Product unorderable. If Sales maintains a Product status projection, keep in mind projections **can lag** and cannot replace the authoritative source when a rule needs an immediate decision.

Typical flow:

~~~mermaid
sequenceDiagram
    participant S as Sales
    participant C as Catalog
    participant I as Inventory
    participant P as Payment

    S->>C: GetProduct(productId, tenantId)
    C-->>S: ProductView / quoteId / version
    S->>S: Create Order and store productId + snapshot
    S->>I: Reserve(orderId, productId, quantity, requestId)
    I-->>S: reservationId, expiresAt
    S->>P: Authorize(paymentRequestId, amount)
    P-->>S: paymentId, outcome
    S->>S: Verify outcomes, transition Order status
~~~

In this diagram, **`productId`** is a communication identifier, not a promise that Product will keep the same price forever. Prices must tie to quotes/snapshots and validity policies; **`reservationId`** identifies a stock hold right, not a permanent guarantee that stock remains untouched indefinitely.

To handle production realities:

- **Idempotency keys** identify *one request*, distinct from aggregate IDs. For instance, two retries of the same payment command must share the same `paymentRequestId`; two new purchases must use new keys.
- **`eventId`** helps consumers deduplicate; the source aggregate's `version` or sequence prevents applying an older event after a newer one.
- **Transactional outbox** helps persist state and outbound messages in one local transaction. Consumers should still track processed events (**inbox/deduplication**) for effective-once business processing.
- If an operation spans multiple sources, use intermediate states and compensation on failure; do not assume cross-service rollback.

Contract design must avoid a subtle bug: a `CustomerId` issued by Customer Management and a `buyerId` in Sales **are not necessarily the same concept** if Sales defines `Buyer` differently. Two values both typed as `UUID` do not prove semantic equivalence; a boundary translation layer (**anti-corruption layer**) may be required.

## 9. Querying Across Aggregates Without Coupling Write Authority

An `OrderDetail` screen wants to display:

- the Order and locked-in line items owned by Sales;
- the customer's current name owned by Customer;
- the product's current image owned by Catalog;
- payment status owned by Payment.

There are two main approaches:

**Read-time composition:** An application/query service fetches `Order` by `orderId`, extracts `customerId` and the set of `productId`s, and makes **batch** API calls to Customer/Catalog. This avoids N+1 queries, though latency and availability depend on the downstream services.

**Dedicated read model (projection):** A consumer subscribes to change events and builds an `OrderDetailView` combining fields from multiple sources. Reads are fast, though data may lag and requires versions, sync timestamps, and handling of duplicate/out-of-order events.

| Read requirement | Suitable option | Notes |
| --- | --- | --- |
| Display exact transaction history | Snapshot inside `Order` | Never re-read current price to overwrite old prices |
| Look up current customer name | Customer API or projection | Handle not-found, anonymization, and privacy rules |
| List thousands of Orders for a Product | Query/read model indexed by `productId` | Avoid loading full aggregate graphs just to filter |
| Decide whether to grant a stock hold | Authoritative Inventory API/command | Never rely on a potentially stale stock projection |

A reporting projection may contain both `productId` and `customerId`, yet it never becomes the owner of Product or Customer. **Optimizing the read path is never a reason to merge write boundaries.**

## 10. Storage Engines Do Not Change Reference Semantics

| Technology | Representing external references | Risks to verify |
| --- | --- | --- |
| **Relational** | `customer_id`, `product_id` columns; intentional FKs within same DB | Cross-context FKs couple deletes/migrations; joins do not prove shared aggregate membership |
| **Document** | `customerId` field and `orderLines` elements containing `productId`; embedded snapshots | Embedding the entire `Customer` causes stale copies and costly updates |
| **Graph** | `Order` node linked to `Customer`/`Product` via directed edges | Edges do not grant write permission or create cross-root transactions automatically |
| **Analytical** | `FactOrderLine` holding `customerKey`/`productKey` and corresponding dimensions | Warehouse surrogate keys may differ from source IDs; delayed updates and history tracking needed |

Example of an `Order` document:

~~~json
{
  "orderId": "835d7a89-4885-4632-8c29-6ac320ad131b",
  "tenantId": "98094b91-18cb-4be1-aa9e-a1e8ce79e594",
  "customerId": "0a99c918-fb49-41ed-8a82-6e81f2303f04",
  "recipientNameSnapshot": "Nguyen An",
  "orderLines": [
    {
      "lineNo": 1,
      "productId": "8415699d-8119-4b28-aaf8-9e95c46c5a33",
      "productNameSnapshot": "Laptop 14 inch",
      "unitPriceAmount": "23000000.00",
      "currency": "VND",
      "quantity": 1
    }
  ]
}
~~~

`OrderLines` are **internal** to the `Order` aggregate, so embedding them can be convenient if the DBMS supports atomic updates at the document level. `Customer` is still referenced by ID, and the locked recipient name is a snapshot. Switching from relational to document storage does not turn `Customer` into an `Order` member.

In an analytical warehouse, dimension surrogate keys may differ from original `customerId`s in order to track historical changes. Keep a clear mapping from the source ID and its scope to the dimension key, avoiding confusion between a source ID and an internal warehouse key.

## 11. Process for Designing a Cross-Aggregate Reference

When encountering "A relates to B", answer in order:

1. **Do A and B have independent lifecycles?** If yes, they are likely two aggregates; do not conclude from the ERD alone.
2. **What does A need to know about B?** Just an identifier, a historical snapshot, or current live data?
3. **What kind of ID is it?** Root ID, business code, tenant-scoped composite key, or partner system ID?
4. **Who has authority to create/edit/delete B?** Write paths must go through the root or service owning B.
5. **When must the reference be valid?** At draft creation, at confirmation, throughout its lifecycle, or only at read time?
6. **What happens if B changes or disappears?** Block new actions, keep snapshots, anonymize, store a tombstone, or reconcile?
7. **Which constraints need immediate consistency?** Use constraints/transactions at the authoritative source; design a protocol across systems.
8. **How do we verify it?** Test wrong-tenant IDs, missing objects, deletion during confirmation, retries, late events, and reads when the source is temporarily down.

The expected deliverable is a concise **reference contract**:

| Contract attribute | Example |
| --- | --- |
| ID source | Catalog issues `ProductId` |
| Uniqueness scope | `(tenantId, productId)` |
| Reference holder | `Sales/OrderLine` |
| Accompanying data | `productNameSnapshot`, `unitPriceSnapshot` |
| Write-time validation | Product belongs to tenant and is eligible for purchase under active policy |
| When source is deleted/deactivated | Preserve order history; block new purchases if ineligible |
| Read rules | Historical data from snapshot; current attributes from Catalog or projection |

Writing such a contract helps developers, QA, and DBAs share the exact meaning of an ID column instead of assuming a foreign key alone is enough.

## 12. Practice Exercise: Multi-Branch Library System

**Scenario:** A library system has `Member`, `BookCatalog`, `PhysicalCopy`, and `Loan`. One book title has multiple physical copies; a physical copy can only be borrowed under one active `Loan` at a time. Members can change their names, and titles can change names or be retired from the catalog, yet past loan transactions must remain auditable. The system spans multiple branches that have overlapping copy numbers.

**Tasks:**

1. Propose roots for `Member`, `BookCatalog`, `PhysicalCopy`, and `Loan`. Which relationships should store another root's ID? Which could be internal members inside an aggregate?
2. Choose the complete identifier for `PhysicalCopy` in a multi-branch system; explain the risk of using only `copyNo`.
3. When creating a `Loan`, which data needs snapshotting and which should be queried live?
4. Write the invariant "a `PhysicalCopy` cannot have two active `Loan`s" and propose how to protect it against two concurrent requests.
5. If a `BookCatalog` entry is retired after a book was borrowed, how should historical `Loan`s behave?

**One solution approach:**

- `Member` has `memberId`; `BookCatalog` has `bookId`; `PhysicalCopy` has a branch-scoped `copyId` or `(branchId, copyNo)`; `Loan` has `loanId`. `Loan` stores `memberId`, `copyId`, and title/borrower snapshots per archival policy, without embedding `Member`/`BookCatalog` objects that could be mutated from `Loan`.
- A specific copy can be identified by `(branchId, copyNo)` if `copyNo` is unique only per branch. If the system issues a global `copyId`, enforce actual uniqueness rather than relying on application hope.
- `Loan` stores checkout date, due date, branch, and transaction terms. Current cover image/phone number are read-only lookup details depending on purpose; title/name at checkout time may require snapshots for legal and business auditing.
- The lending authority must execute **one atomic operation** when issuing a copy. If `Loan` and `CopyAvailability` share a database, you can use a partial `UNIQUE` index on open loan records within a transaction, or conditional status updates on the Copy. Simply running a `SELECT` ("copy is free") followed by an unlocked `INSERT` can produce two locally valid `Loan`s that conflict globally.
- When `BookCatalog` is retired, do not cascade-delete historical `Loan`s. Retain necessary IDs or tombstones, committed snapshots, and anonymization policies where appropriate.

To verify, simulate two readers borrowing the last copy simultaneously, a `Member` changing name during an active `Loan`, a `BookCatalog` entry being retired, and a copy transferring branches. If the model cannot explain which ID stays constant, where write authority lives, and which operation must be atomic, revisit the boundaries.

## 13. Common Mistakes and Checklist

| Design mistake | Harm | Remedy |
| --- | --- | --- |
| Order holds a Customer object and edits it directly | Violates ownership; can corrupt other orders' data | Store `customerId`; edit `Customer` only through Customer's root |
| Storing only `productId` without saving purchase price | Historical orders change meaning when Catalog changes prices | Store both the ID and a snapshot locked at checkout |
| Treating an FK as proof of business eligibility | Row exists, yet may be suspended or discontinued | Check business conditions and version/validity |
| Omitting `tenantId` from keys/queries | Cross-tenant reference mix-ups and data leaks | Carry full namespace and enforce authorization |
| Using mutable business codes as stable IDs without a policy | Code changes break links | Choose stable IDs or define alias/migration workflows |
| Cascade-deleting historical data of another aggregate | Destroys auditability and violates lifecycle boundaries | Define delete policies, tombstones, and anonymization |
| Relying on stale read replicas to confirm strong transactions | Accepts expired prices, capacity, or statuses | Validate against the authoritative source via proper contracts |
| Retrying integration commands with a new ID each attempt | Risk of duplicate reservations or double charges | Use a stable idempotency key per logical request |

Before finalizing a schema, verify:

- Is it clear which **aggregate root**, bounded context, and namespace every ID points to?
- Are primary root IDs clearly separated from business codes and idempotency/event IDs?
- Are historical fields snapshotted at the exact business moment that must be preserved?
- Who verifies the existence, state, version, and access rights of the referenced object?
- Which integrity rules are enforced by FK/UNIQUE/CHECK, and which require transactions or cross-system protocols?
- When the source changes, deletes, goes offline, or emits late events, does the system have defined and reconcilable behavior?
- Do cross-aggregate read queries avoid N+1 calls, meet latency bounds, and avoid becoming backdoor write paths?

**Conclusion:** Referencing by identifier lets aggregates **connect while retaining independent identity, lifecycle, and change authority**. Good design specifies each ID's scope, when it must be validated, which data is snapshotted, which source owns each invariant, and which mechanisms enforce them. Once those are clear, keys, indexes, schemas, and integration contracts truly serve the business model—whether backed by relational, document, graph, or analytical databases.
