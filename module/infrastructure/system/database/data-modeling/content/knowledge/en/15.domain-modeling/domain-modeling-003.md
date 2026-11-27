# Consistency Clusters (Aggregates) and Root Objects Controlling Change

## Learning Objectives

After this lesson, you will be able to:

- Explain **aggregates**, **aggregate roots**, and **business invariants** using a scenario with multiple related entities.
- Choose aggregate boundaries based on conditions that must be immediately consistent after a transaction, rather than based on the number of tables, screens, or services.
- Design write operations to pass through the aggregate root; distinguish internal references, ID references, and snapshot data.
- Map write boundaries to keys, relationships, transactions, and concurrency control mechanisms in a relational database.
- Recognize cross-aggregate rules, organize asynchronous coordination, and test for race conditions, duplicate messages, and lost responses.
- Evaluate the pros and cons of implementing aggregates on relational, document, graph, and analytical data models.

In **DATABASE_DATA_MODELING**, a good data schema must answer the question: **who is allowed to modify which data, and what must remain true after every change?** Knowing that an order consists of an Order table and an OrderLine table does not tell you whether line items can be edited after confirmation, or whether two concurrent requests can cause a lost update. Aggregates are the design tool that answers those questions.

## 1. An Aggregate Is a Business Consistency Boundary

An **aggregate** is a collection of domain objects managed as a single consistency unit. It has one **aggregate root**, which is the object used from outside to execute operations that change internal state. The root is responsible for enforcing **invariants**—conditions that must hold true across all valid states after a business operation completes.

Example in sales:

- **Order** is the aggregate root, with its own ID and status.
- **OrderLine** is a child entity: it has an identity within the order, a quantity, and a locked-in unit price.
- **Money** is a value object: composed of an amount and a currency; values do not need separate identities.
- **Customer**, **InventoryBalance**, and **Payment** have their own lifecycles, so they are not members of the Order aggregate by default.

A visual perspective:

~~~mermaid
flowchart TB
    Client["Use case: Update quantity"]
    Client -->|"order.changeQuantity(lineId, qty)"| Order

    subgraph OA["Order Aggregate — one consistency boundary"]
      Order["Order (aggregate root)"]
      LineA["OrderLine #1 (child entity)"]
      LineB["OrderLine #2 (child entity)"]
      MoneyA["Money (value object)"]
      Order -->|"coordinates changes"| LineA
      Order -->|"coordinates changes"| LineB
      LineA --- MoneyA
    end

    Customer["Customer (separate aggregate)"]
    Stock["StockBalance (separate aggregate)"]
    Order -.->|"references customerId"| Customer
    Order -.->|"requests stock reservation"| Stock
~~~

Solid lines represent control inside Order; dashed lines represent relationships with other aggregates. This diagram illustrates **business responsibilities**, not a requirement that Order and OrderLine be stored in the same document.

### Distinguishing Three Easily Confused Boundaries

| Concept | Primary question | Example |
| --- | --- | --- |
| **Bounded context** | Which domain model and business language apply in this scope? | Sales defines Order, locked-in prices, and confirmation states |
| **Aggregate** | Which data must change together to guarantee local invariants? | An Order and the line items belonging to that order |
| **Database/schema/service** | Which technology stores and deploys the data? | `orders` and `order_line` tables in the `sales` schema |

A bounded context can contain many aggregates. One aggregate can span multiple tables; conversely, one table can store many independent aggregates (each row being a root). **Do not use FKs, 1-N relationships, or folder structures to automatically infer aggregate boundaries.**

## 2. From Business Requirements to an Invariant List

Suppose a user can add, remove, and update product quantities while an order is in the DRAFT state. After confirmation, the order's line items and purchase prices cannot be modified. Analysis table:

| Rule | Must be consistent immediately after the operation? | Who enforces it? |
| --- | --- | --- |
| Every line item has a positive quantity | Yes | Order/OrderLine |
| Lines within the same Order have distinct IDs | Yes | Order |
| An Order cannot be confirmed without any lines | Yes | Order |
| A CONFIRMED order cannot have its prices or quantities edited | Yes | Order and Sales write paths |
| Order total matches line items and rounding rules | Yes, if the total is persisted as authoritative data | Order |
| Warehouse cannot reserve more stock than available | Yes, but within the Inventory context | StockBalance/Reservation |
| Sales workflow only completes after Payment succeeds | Requires coordination across multiple aggregates/contexts | Business workflow; Order checks received evidence |

The first five rows justify grouping Order and OrderLine into an aggregate. Inventory and payment rules are still vital, but pulling all of Inventory and Payment into Order just to get a single transaction usually leads to tight coupling, heavy write contention, and difficulty evolving the system.

**Invariants are chosen by the business**, not from a generic wish that data across screens "always looks identical." For example, the total amount can be derived from the lines instead of duplicated; if it is stored, the application must treat updating lines and updating the total as a single atomic change.

## 3. The Root Controls Change Through Behavior

The aggregate root is the **write gateway** of the aggregate. External callers may know an OrderLine exists or view a snapshot of it, but they must not directly mutate fields that Order needs to control.

Design domain-meaningful operations:

| Operation | Preconditions | Postconditions |
| --- | --- | --- |
| `addLine(product, price, qty)` | Order is DRAFT; qty > 0; valid unit price | New unique line added, same currency |
| `changeQuantity(lineId, qty)` | Order is DRAFT; line exists; qty > 0 | Only the targeted line changes quantity; total recalculates accurately |
| `removeLine(lineId)` | Order is DRAFT; line exists | Line is removed; a DRAFT order may become empty |
| `confirm()` | Order is DRAFT; at least one line exists; related prerequisites verified | Status becomes CONFIRMED; line items can no longer be edited |
| `cancel()` | Current state permits cancellation per policy | Valid status; emits compensation actions if stock was reserved |

Avoid APIs like `setStatus(value)`, `setLines(value)`, or `setTotal(value)` that let external code make arbitrary changes. Such setters easily produce invalid states like "CONFIRMED with no lines" or "total differs from line sum."

### Concise Java Example

The code below illustrates an aggregate with explicit behavior. It targets Java 17+ and assumes one currency per order and two decimal places for unit prices; these are **example** rules, not a universal standard for every currency.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

record Money(BigDecimal amount, Currency currency) {
    Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
        amount = amount.setScale(2, RoundingMode.UNNECESSARY);
        if (amount.signum() < 0) throw new IllegalArgumentException("Negative price");
    }

    Money plus(Money other) {
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(amount.add(other.amount), currency);
    }

    Money times(int quantity) {
        if (quantity <= 0) throw new IllegalArgumentException("Invalid quantity");
        return new Money(amount.multiply(BigDecimal.valueOf(quantity)), currency);
    }
}

record LineView(UUID id, String productId, Money unitPrice, int quantity) {}
enum Status { DRAFT, CONFIRMED, CANCELLED }

// Only the aggregate root owns and coordinates the map of lines.
final class Order {
    private final UUID id;
    private final Currency currency;
    private final Map<UUID, LineView> lines = new LinkedHashMap<>();
    private Status status = Status.DRAFT;

    Order(UUID id, Currency currency) {
        this.id = Objects.requireNonNull(id);
        this.currency = Objects.requireNonNull(currency);
    }

    void addLine(UUID lineId, String productId, Money price, int quantity) {
        requireDraft();
        Objects.requireNonNull(lineId);
        Objects.requireNonNull(productId);
        Objects.requireNonNull(price);
        if (quantity <= 0) throw new IllegalArgumentException("quantity <= 0");
        if (!currency.equals(price.currency())) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        if (lines.containsKey(lineId)) {
            throw new IllegalArgumentException("Duplicate line ID");
        }
        lines.put(lineId, new LineView(lineId, productId, price, quantity));
    }

    void changeQuantity(UUID lineId, int newQuantity) {
        requireDraft();
        if (newQuantity <= 0) throw new IllegalArgumentException("quantity <= 0");
        LineView old = lines.get(lineId);
        if (old == null) throw new IllegalArgumentException("Unknown line");
        lines.put(lineId,
            new LineView(old.id(), old.productId(), old.unitPrice(), newQuantity));
    }

    Money total() {
        Money sum = new Money(BigDecimal.ZERO, currency);
        for (LineView line : lines.values()) {
            sum = sum.plus(line.unitPrice().times(line.quantity()));
        }
        return sum;
    }

    void confirm() {
        requireDraft();
        if (lines.isEmpty()) throw new IllegalStateException("Empty order");
        status = Status.CONFIRMED;
    }

    Map<UUID, LineView> linesView() { return Map.copyOf(lines); }
    Status status() { return status; }
    UUID id() { return id; }

    private void requireDraft() {
        if (status != Status.DRAFT) {
            throw new IllegalStateException("Order is not editable");
        }
    }
}
~~~

Lines are represented by an **immutable record** (`LineView`). The root swaps in a new record when quantity changes while keeping `lineId`. A Java object does not need to be mutated in-place for the business concept of **a line item with identity** to persist; business identity and memory address are two different things.

The `linesView()` method returns an unmodifiable copy of the map; callers cannot grab the internal data structure to bypass root checks. If a `LineView` contained mutable components, an appropriate deep snapshot would still be needed.

This snippet intentionally omits repositories, database transactions, event persistence, and payment policies. The root protects invariants **in memory**; when multiple processes run concurrently, the system must add consistency mechanisms at the storage layer.

## 4. Rules for Choosing Aggregate Boundaries

A practical design method:

1. **List business commands.** Who issues the command, and what does it change? For example, "confirm order" or "reserve 3 items at warehouse A".
2. **Write down post-command invariants.** What must be true the instant the write succeeds? Separate point-in-time conditions from workflows that complete later.
3. **Find data groups that must be read/written atomically.** If two elements must always be checked together to protect an invariant, they are candidates for the same aggregate.
4. **Pick a business-meaningful root.** The root has an ID, behavior, and authority over its members; do not pick a root simply because it is a parent table with many FKs.
5. **Check size and write contention.** A root with millions of members or updated by every user will cause locking, conflicts, and heavy loading costs.
6. **Handle remaining relationships via IDs and contracts.** Define which data is snapshotted, which is referenced, and when verification from another aggregate is required.

Inventory example: instead of making **one** Warehouse aggregate manage every SKU at every location, you can model `StockBalance` keyed by `(warehouseId, sku)`. The invariant "do not reserve more than available quantity" is enforced independently per SKU at each warehouse, reducing contention.

However, if the business requires a stock transfer between two warehouses to simultaneously debit the source warehouse and credit the destination warehouse, that is an **invariant across two StockBalances**. You must weigh using a local transaction spanning both roots if they share a store and require strict atomicity, versus using a transfer workflow with intermediate states and reconciliation. Do not pretend two separate roots automatically provide cross-system atomicity.

### When to Split or Merge?

| Symptom | How to evaluate |
| --- | --- |
| Every operation must load a huge object tree | The aggregate may be too wide; identify which invariants genuinely require atomicity |
| Two data groups are always updated together and frequently fail from partial writes | A local invariant may have been split; consider merging or using an explicit transaction |
| A child entity is modified independently by multiple departments | It may have its own lifecycle and should become the root of another aggregate |
| Two roots only need to be displayed side by side | Keep them separate; use composed queries or a read model for reading |
| Every update to one object locks the entire organization | The boundary may be too coarse; split by independent decision-making units |

**There is no universal rule that "aggregates should be as small as possible" or "an aggregate must equal one document."** The right balance is determined by invariants, contention levels, and data access patterns.

## 5. Relationships Inside and Outside an Aggregate

### Internal Members

`OrderLine` is typically controlled by `Order`: adding, removing, and updating line quantities all require checking Order's status. A write transaction on Order may update both the header and lines, but everything must commit or roll back as a single unit.

### Other Aggregates

Order can hold `customerId`, `sku`, or `productId` without making Customer, Stock, or Product internal members. An external ID is a **reference**, not permission to mutate the referenced object's data.

For instance, Sales needs to remember the 23,000,000 VND unit price of an item at purchase time. If it only kept `productId` and always read the latest price from Catalog, historical orders would change meaning whenever Catalog updated prices. Therefore, `OrderLine` stores `priceSnapshot` and `productNameSnapshot` per the committed transaction.

Read paths can join multiple sources, while write paths must respect ownership. Do not merge Order, Product, and Customer into one aggregate simply because the order detail screen displays all three.

### Root and Repository

Repositories are designed around loading/saving the aggregate root (e.g., `OrderRepository`); exposing an `OrderLineRepository` for other code to arbitrarily edit lines is discouraged. A dedicated query layer for reporting can read data at the line level without becoming a write path that bypasses invariants.

A typical application command:

~~~text
ChangeOrderQuantity(orderId, lineId, newQuantity, expectedVersion)
  -> Application service checks permissions
  -> OrderRepository loads Order
  -> Order.changeQuantity(lineId, newQuantity)
  -> OrderRepository saves Order with version check
  -> Transaction commits
~~~

From outside the aggregate, you see the root and business operations; the details of child entities remain governed by the root.

## 6. Mapping an Aggregate to PostgreSQL

We keep the relational schema clean: Order and OrderLine live in **two tables**, even though they form one aggregate; the unit price `Money` uses an amount column on OrderLine paired with the currency column on Order.

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.orders (
    order_id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    currency CHAR(3) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sales.order_line (
    order_id UUID NOT NULL REFERENCES sales.orders(order_id),
    line_id UUID NOT NULL,
    product_id VARCHAR(64) NOT NULL,
    product_name_snapshot TEXT NOT NULL,
    unit_price_amount NUMERIC(19, 2) NOT NULL
        CHECK (unit_price_amount >= 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_id)
);
~~~

Explaining the choices:

- **`orders.order_id`** is the identity of the aggregate root. **`(order_id, line_id)`** identifies a line **within** an Order, without forcing every line to have a globally unique standalone ID.
- The FK from `order_line` to `orders` protects the local relationship. The composite primary key also creates an index leading with `order_id`, supporting loading all lines of an order.
- **`product_id`** is a reference ID pointing to Catalog. Snapshot columns protect committed details; they do not need to update whenever source data changes.
- `CHECK` and `NOT NULL` block certain invalid row-level data. They **do not** automatically guarantee that a CONFIRMED Order has at least one line or that lines cannot be modified after confirmation.
- **`version`** serves concurrent update control; it is not a new ID for Order on each update.

When displaying an order, query the header and lines within the same snapshot/transaction if a point-in-time consistent view is required. Additional indexes for querying by `customer_id` and `created_at` should only be designed after knowing the actual workload, sort order, and data volume.

### Write Transactions Must Encompass Members

Example of adding a line to a DRAFT Order using **optimistic locking** on the root:

~~~sql
BEGIN;

-- This step also holds a row lock on Order until the end of the transaction.
UPDATE sales.orders
SET version = version + 1
WHERE order_id = :order_id
  AND status = 'DRAFT'
  AND version = :expected_version;

-- The application MUST verify updated row count = 1.
-- If 0: ROLLBACK and report a conflict or invalid state.

INSERT INTO sales.order_line
    (order_id, line_id, product_id, product_name_snapshot,
     unit_price_amount, quantity)
VALUES
    (:order_id, :line_id, :product_id, :name_snapshot,
     :unit_price, :quantity);

COMMIT;
~~~

In this example, the application service already loaded the data and invoked domain behavior before generating SQL commands. The repository must persist all aggregate changes within **a single transaction**. If the `INSERT` fails, the entire transaction rolls back, including the `version` increment.

Every command that adds, edits, or deletes a line or transitions status must participate in **the same root locking/versioning protocol**. If a process modifies `order_line` directly without incrementing `version` or checking status, aggregate rules can be broken even when standard commands lock properly. Restrict write paths via DB privileges, repository interfaces, and, when necessary, defensive constraints/triggers.

### Confirming an Order and Multi-Row Invariants

Confirming an order requires checking for at least one line and status DRAFT. An illustrative conditional update:

~~~sql
BEGIN;

UPDATE sales.orders AS o
SET status = 'CONFIRMED',
    version = version + 1
WHERE o.order_id = :order_id
  AND o.status = 'DRAFT'
  AND o.version = :expected_version
  AND EXISTS (
      SELECT 1
      FROM sales.order_line AS l
      WHERE l.order_id = o.order_id
  );

-- Verify exactly 1 row updated; otherwise ROLLBACK.
COMMIT;
~~~

Concurrency note: the `EXISTS` clause is only safe as part of a **consistent write protocol**. If every line-deletion operation also locks Order first before modifying `order_line`, no valid process can silently delete the last line during confirmation. If any write path bypasses the root, `EXISTS` alone does not protect the invariant against all race conditions.

Common technical options:

- **Optimistic locking:** read version, write conditionally against the old version, report conflict if 0 rows updated. Fits aggregates with low write contention.
- **Pessimistic locking:** use `SELECT ... FOR UPDATE` or update the root to lock the record when many commands contend. The trade-off is wait time and deadlock risk if lock ordering is inconsistent.
- **Constraints:** `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `CHECK`, and exclusion constraints depending on the rule type. These are a reliable safeguard for constraints the DB can express.

Choose a strategy based on business needs, throughput, conflict rate, and database engine; avoid relying solely on application-layer checks and assuming they will hold under concurrent requests.

## 7. Distinguishing Local Invariants from Cross-Aggregate Workflows

Suppose Sales confirms an order once it receives sufficient stock reservation and payment details. Four aggregates may participate:

- `Order` in Sales owns line items, locked-in prices, and order status.
- `StockBalance`/`Reservation` in Inventory owns available quantities and reservation rights.
- `Payment` in Payment owns authorization/capture outcomes and gateway references.
- `Customer` in Customer Management owns customer profiles.

Do not place all four under one root because they have separate lifecycles and change rules. A sample coordination flow:

~~~mermaid
sequenceDiagram
    participant S as Sales / Order
    participant I as Inventory
    participant P as Payment
    S->>S: Create order pending confirmation
    S->>I: ReserveStock(requestId, sku, qty)
    I->>I: Check and reserve stock atomically
    I-->>S: StockReserved(reservationId)
    S->>P: AuthorizePayment(paymentRequestId)
    P->>P: Record payment outcome
    P-->>S: PaymentAuthorized(paymentId)
    S->>S: Verify evidence, confirm Order
~~~

This is the happy-path coordination model when both steps succeed. For production operation, you must also account for **reservation rejections, payment failures, timeouts, duplicate messages, delayed arrivals, and reservation cancellations**.

- Inventory must prevent a SKU at a warehouse from being reserved beyond available stock inside a local transaction—for example, via a conditional update `available >= quantity`.
- Payment must handle duplicate commands using a stable idempotency key to avoid double-charging on retries.
- Sales must record outcomes from the other systems keyed by request/event ID and only transition state once required evidence has been accepted.
- When a later step fails, the workflow needs compensation actions (such as releasing reserved stock); compensation is a business operation, not a multi-service ACID rollback.

If using a message broker, a **transactional outbox** helps persist aggregate changes and outbound events in the same local transaction. Consumers still need deduplication and handling for out-of-order messages. **Eventual consistency** means having defined intermediate states, recovery/reconciliation mechanisms, and acceptable latency bounds.

### A Critical Local Condition in Inventory

When multiple Orders request to reserve the same SKU, the root controlling `StockBalance` must protect the non-negative `available` condition:

~~~sql
-- Illustrates an atomic deduction of available stock on a single row.
UPDATE inventory.stock_balance
SET available = available - :quantity,
    reserved = reserved + :quantity
WHERE warehouse_id = :warehouse_id
  AND sku = :sku
  AND available >= :quantity;
~~~

The application must verify exactly one row was updated and record the reservation in **the same transaction**. This command also needs an idempotency mechanism keyed by `reservationRequestId` so retries do not deduct stock multiple times. The Inventory schema and table were not defined in the earlier Sales SQL example; the query above merely illustrates another aggregate's constraint.

**Important limitation:** guaranteeing stock per SKU independently does not automatically guarantee "reserve all SKUs in an order or reserve none." If all-or-nothing reservation across a multi-SKU cart is required, you must design a suitable transaction within the same DBMS or a batch reservation workflow with explicit rollback/compensation.

## 8. An Aggregate Does Not Necessarily Map to One Physical Record

In practice, mapping takes several forms:

| Technology | Representation | What to verify |
| --- | --- | --- |
| **Relational database** | One root and members across multiple tables, saved in a transaction | FKs, locks, versions, header/detail consistency; no shortcut writes |
| **Document database** | One Order document embedding lines, address, and price snapshots | Atomic write scope of the DBMS; document size limits; members with independent lifecycles |
| **Graph database** | Root, members, and references as nodes/edges | Network relationships do not automatically define transaction boundaries or write authority |
| **Analytical data warehouse** | `FactOrderLine`, `factPayment`, and dimensions | Read projections for analytics, possibly delayed; not the source enforcing transactional invariants |

An Order document can be very convenient for loading and saving all lines together, but if an Order accumulates millions of events and dependent records, embedding everything in one document causes update friction and bloat. In relational databases, two tables can still form **one logical aggregate** via transactions. Choose physical structure based on invariants, read/write patterns, scalability, and evolution needs.

An analytical system can join Orders with Payments to build reports, but that **does not** mean the two domains are merged into one aggregate. Reporting data is typically a snapshot or projection with bounded staleness.

## 9. Concurrency Scenarios to Verify

### Two Requests Editing the Same Order

Suppose T1 and T2 both read Order version 7. T1 modifies line 1; T2 modifies line 2. If both write back the entire order without checking, the later write can overwrite the earlier one (**lost update**). With optimistic locking, T1 saves successfully and bumps `version` to 8; T2's write with `expectedVersion = 7` is rejected; the application re-reads and applies the command per policy.

### Confirming While Another User Deletes the Last Line

If one transaction is confirming while another deletes the last line, root-level locking order and status checks must guarantee that **no CONFIRMED order without lines can exist** after commit. This illustrates why placing rules inside an `Order` class still requires proper DB transactions.

### Two Orders Buying the Last Remaining Item

Two separate Order aggregates can both be internally valid. **Inventory** is the authority responsible for granting reservations on the final item. If both Orders check quantity against a cached stock copy, both could accept the same item. Quantity checks and deductions must happen at the inventory owner via atomic operations.

### A Message Delivered Twice

If the same `ReserveStock` command is resent after a timeout, Inventory must recognize the already-processed `requestId` and return a consistent result; the root and stock-reservation transaction must coordinate with a request-tracking table to avoid double-reserving. The same principle applies to payment commands and cross-system event handling.

## 10. Common Aggregate Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Defining aggregate boundaries by following all FKs | Oversized roots, expensive transactions, high contention | Group by local invariants and write authority |
| Making every table its own aggregate | Multi-table rules suffer partial writes; no coordinating root | Group members whose invariants must be protected together |
| Allowing direct edits to child entities via public repositories | Bypasses root status checks | Route all writes through root behavior and transactions |
| Sharing one status enum across all services | Semantic drift; tight coupling between systems | Separate data ownership and integration contracts |
| Using optimistic locking without bumping version on line edits | Concurrent requests can overwrite or break invariants | Every aggregate write command shares the lock/version protocol |
| Treating every cross-aggregate rule as needing a distributed transaction | Poor fault tolerance, heavy coupling and locking | Separate local invariants from cross-context workflows |
| Using events without idempotency/retry handling | Duplicate reservations, payments, or updates | Use `requestId`/`eventId`, outbox/inbox, and deduplication |
| Using reporting tables as the primary write source | Stale state leads to incorrect decisions | Read from the authoritative source when executing commands |

## 11. Practice Exercise: Movie Seat Booking

**Scenario:** A ticketing platform manages showtimes. A customer wants to hold two seats, A1 and A2, for 5 minutes. Available seats must not be held simultaneously by another customer. Once payment succeeds, the system issues tickets. A customer might click Pay twice due to a slow connection.

**Tasks:**

1. Propose aggregate roots for **Booking** and for holding **one seat at one showtime**. Specify the data inside each aggregate and appropriate identities.
2. Write three local invariants and one rule that must be coordinated across aggregates.
3. Analyze two requests trying to hold seat A1 simultaneously; identify the DB or repository mechanism that prevents double-holding.
4. If the business requires **holding both A1 and A2 or holding neither**, how must aggregate boundaries change? Can you just use two independent transactions?
5. When a payment times out and the system retries, how do you avoid issuing tickets twice or charging twice?

**Guided solution approach:**

- `Booking` has `bookingId`, locked-in ticket/price details, status, and the requested seat list. Holding a single seat can be managed by a `SeatAllocation`/`SeatReservation` root identified by `(showtimeId, seatId)`, along with status and hold expiration.
- Local invariants include: a confirmed Booking cannot change ticket prices; hold expiration time must be after hold start time; a single seat at a showtime cannot have two active holds. Cross-aggregate rule: issue tickets only when the seat hold is still valid and payment status meets requirements.
- Preventing double-holds requires an **atomic** operation at the seat manager, using transactions/locks and constraints suited to the current state. Reading "seat is free" for the screen and writing later without locks/conditions is insufficient under concurrent requests.
- If A1 and A2 must be held as an atomic batch, consider a single transaction in the Seat Allocation service that controls both seats in a consistent lock order. You could design the aggregate at a seat-inventory/showtime unit suited to the batch, while weighing contention and size. If holding spans multiple systems, an orchestration and compensation workflow is required; two independent commits do not automatically provide "all-or-nothing."
- For payments and ticket issuance, use an idempotency key, `paymentAttempt` and `booking` identifiers, controlled state transitions, and processed-event tracking. Put expiration handling and refund/seat-release processes in place when states diverge across parties.

There is no single aggregate design that fits every ticketing system. What must be evaluated is invariant protection, seat contention levels, multi-seat atomicity requirements, data storage design, and failure compensation workflows.

## 12. Pre-Implementation Checklist

- Does every aggregate have a **business-named root**, a clear ID, and an explicit lifecycle?
- Which invariants must hold after **every local commit**? Which are achieved only after a multi-step workflow?
- Are child entities and value objects modified **only through the root**? Are there any direct write paths bypassing validation?
- Do all operations modifying an aggregate share the same **transaction + lock/version** protocol and conflict handling?
- Are relationships to other aggregates expressed via IDs/contracts, and is historical data snapshotted in the right place?
- Are transactions too wide, or are aggregates too large and creating write bottlenecks?
- Have concurrent requests, duplicate messages, expirations, and mid-flight failures been covered by test scenarios?
- Which rules are enforced directly by the DB, which by the domain/application layer, and what safeguards exist if data is written outside the normal flow?

**Conclusion:** An aggregate is **a boundary for protecting invariants**, and an aggregate root is **the coordination point for changes** within that boundary. Proper design goes beyond drawing entity relationships—it defines commands, preconditions/postconditions, transactions, concurrency control, and contracts with other aggregates. That is how business requirements become clear data models that can be verified and evolved as the system scales.
