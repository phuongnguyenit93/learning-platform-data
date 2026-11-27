# Transaction-Time Price and Address Snapshots vs. Read-Acceleration Copies

## Learning Objectives

After this lesson, you will be able to:

- Distinguish a **transaction-time snapshot** from a **read-acceleration copy (read projection)** of current data, even when both hold identical values initially.
- Precisely identify the **commitment event**, effective timestamp, data source, and mutation rules for prices, product names, shipping addresses, and billing addresses.
- Design relational models storing confirmed prices and addresses along with appropriate keys, constraints, transactions, and verification queries.
- Prevent historical data from being rewritten when the product catalog, customer profile, or current address book changes.
- Evaluate storing snapshots in relational, document, event, or analytical models; handle order edits, refunds, legacy data backfills, and personal data protection.

This lesson belongs to the **Denormalization** chapter of **DATABASE_DATA_MODELING**. Translating business requirements into entities, relationships, keys, indexes, and physical schemas must rest on **data semantics over time**. Storing a structurally similar field can be sound design for transaction history yet dangerous redundancy when used to mirror current state.

## 1. Story of an Order: Same Initial Value, Different Lifecycle Rules

On Oct 01, a customer confirms purchasing two units of Product A at **unit price 150,000 VND**, shipped to **12 Hoa Street, District X**. The system records a confirmed order. On Oct 20, the store raises Product A's price to **180,000 VND**. On Oct 25, the customer changes their default address in their address book to **55 La Street, District Y**.

Now consider four different questions:

1. **Today's product page** must show the new price of 180,000 VND.
2. **Confirmed order details** must show the locked-in unit price of 150,000 VND, not today's price.
3. **The customer profile** must show the current address, 55 La Street.
4. **The Oct 01 order confirmation record** must still show the address the customer approved at checkout: 12 Hoa Street.

If order history queries always JOIN to mutable **products.current_price** or **customer_addresses**, historical orders silently mutate whenever current profiles change. This bug breaks invoicing, dispute resolution, financial reconciliation, customer support, and proof of what terms were confirmed.

Conversely, when copying a current category name into a product-card table solely to skip a JOIN, the copy **must be updated** when the category name changes. One field must **stay fixed**, while the other must **track its source**: that is the fundamental difference.

> **A transaction snapshot answers "What was confirmed back then?"; a read-acceleration copy answers "What is the current state, and how fresh is it?".**

## 2. Distinguish by Semantics, Not by Occurrence Count

| Criterion | Transaction Snapshot | Read-Acceleration Copy |
| --- | --- | --- |
| Business question | What price, address, or terms were locked in at an event? | What is the current price, name, label, or info? |
| Examples | **order_items.unit_price_at_confirmation**, **orders.ship_to_line1_at_confirmation** | **product_cards.current_price_display**, **product_cards.category_name_display** |
| Initial value source | Validated price/address at confirmation, including promos and customer selections | Current attributes of a product, category, author, or account |
| When current source changes | **Must not auto-update** confirmed records | **Must refresh** according to consistency contract |
| Authoritative source afterward | Confirmed transaction record is authoritative for that historical fact | Original business record remains the source of truth |
| Verification | Checked against confirmed terms, events, or receipts; not current catalog price | Checked against current source, factoring in version and lag |
| Remediation | Audited adjustments, revisions, or policy-compliant compensating events | Refresh, reconcile, or rebuild from source |
| Risk if updated wrongly | Rewrites history, corrupts amounts and receipts | Serves stale info, desynchronizes screens |
| Risk if retained too long | Stores personal data beyond retention limits | Exposes stale copies outside current access controls |

The same pair of tables can participate in **both patterns**:

- **catalog_products.current_price**: currently effective list price, subject to change.
- **order_items.unit_price_at_confirmation**: price applied to the order line upon confirmation, kept as historical proof.
- **product_cards.current_price_display**: copy of the current price serving product cards, allowed slight lag under async sync.

Do not assume that two columns holding "150000" automatically violate normalization. Historical data and current data are **two distinct facts along different time axes**. Snapshot attributes still produce physical repetition, yet the reason for storing them is **transaction semantics**, not merely saving a JOIN.

## 3. Precisely Define "At Transaction Time"

The phrase "at purchase time" is easily misunderstood. An e-commerce flow has many milestones:

~~~text
View product -> Add to cart -> Receive quote
        -> Confirm order -> Payment -> Delivery -> Refund
~~~

The price on the product page, quoted price in the cart, price the customer **agrees to pay**, actual captured amount, and final net amount after refunds can all differ. Similarly, the address in the address book, confirmed checkout address, shipping label address, and actual address delivered to by the carrier can diverge.

Therefore, before creating a snapshot, answer:

1. **Which event marks the commitment boundary?** In this example it is **OrderConfirmed**, when the system accepts the order after validation.
2. **Who owns the authoritative value?** The pricing and order systems validate prices; the customer selects an address, while the server verifies the choice and copies the required fields.
3. **Which fields must stay immutable?** Unit prices and addresses approved at the commitment event; later changes are recorded separately per business rules.
4. **What are the currency and arithmetic definitions?** Pre- or post-discount, tax-inclusive or exclusive, currency code, rounding rules, and quantity.
5. **Are post-confirmation edits allowed?** If yes, which fields, who approves, are replacement documents issued, and how is edit history preserved?

A practical naming convention includes the temporal boundary: **unit_price_at_confirmation**, **ship_to_line1_at_confirmation**. Clear names prevent query authors from accidentally pulling current values into historical reports. Even with clear naming, enforce contracts and constraints in write-path code.

### 3.1. Business Event Snapshots Differ from Database Technical Snapshots

Here **snapshot** refers to **business values captured at a commitment event**. It is not synonymous with a full-database snapshot, storage snapshot, or PostgreSQL's **REPEATABLE READ** isolation level.

A transaction running under **READ COMMITTED** can still capture a valid business snapshot if prices/addresses are validated, locked or version-checked, and written in the same transaction. Conversely, merely raising the isolation level while reading stale prices or trusting client-supplied prices fails to produce a trustworthy business snapshot.

## 4. Relational Model: Keeping Current and Committed Data in Their Proper Places

Suppose the requirement is to capture **unit price, product name, and chosen shipping address** at order confirmation. Minimal PostgreSQL example:

~~~sql
CREATE TABLE catalog_products (
    product_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL,
    current_unit_price NUMERIC(18, 2) NOT NULL
        CHECK (current_unit_price >= 0),
    currency CHAR(3) NOT NULL,
    price_version BIGINT NOT NULL DEFAULT 1
        CHECK (price_version >= 1)
);

CREATE TABLE customer_addresses (
    address_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    recipient_name TEXT NOT NULL,
    line1 TEXT NOT NULL,
    city TEXT NOT NULL,
    country_code CHAR(2) NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    client_request_id TEXT NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    currency CHAR(3) NOT NULL,
    source_address_id BIGINT NULL
        REFERENCES customer_addresses(address_id)
        ON DELETE SET NULL,
    ship_to_name_at_confirmation TEXT NOT NULL,
    ship_to_line1_at_confirmation TEXT NOT NULL,
    ship_to_city_at_confirmation TEXT NOT NULL,
    ship_to_country_at_confirmation CHAR(2) NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('CONFIRMED', 'SHIPPED', 'CANCELLED'))
);

CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NULL
        REFERENCES catalog_products(product_id)
        ON DELETE SET NULL,
    product_name_at_confirmation TEXT NOT NULL,
    unit_price_at_confirmation NUMERIC(18, 2) NOT NULL
        CHECK (unit_price_at_confirmation >= 0),
    product_price_version_at_confirmation BIGINT NOT NULL
        CHECK (product_price_version_at_confirmation >= 1),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    line_subtotal NUMERIC(22, 2)
        GENERATED ALWAYS AS
        (quantity * unit_price_at_confirmation) STORED
);

CREATE INDEX idx_order_items_order_id ON order_items(order_id);
~~~

This is an **illustrative schema**, not a complete production payment model. It intentionally omits discounts, taxes, shipping fees, exchange rates, refunds, and multi-currency lines on a single order. Production systems must model those components explicitly and enforce currency compatibility. **line_subtotal** here is strictly **quantity × unit_price_at_confirmation**; it alone does not represent the customer's total payable amount.

### 4.1. Why Still Keep product_id and source_address_id?

Reference keys answer **"which entity did this transaction involve?"**, whereas snapshots answer **"which values were locked in?"**. Keeping both helps:

- **product_id** enables linking to the current product, product-level analytics, or SKU lookup, if the product still exists.
- **product_name_at_confirmation** and **unit_price_at_confirmation** preserve old order contents even when product names or prices change.
- **source_address_id** records which saved address the customer picked at that moment, if that reference still exists.
- **ship_to_*_at_confirmation** preserves confirmed details even if the address book entry is later edited or deleted.

In this example, **ON DELETE SET NULL** clears the pointer to the live record if deleted while keeping the committed snapshot intact. That is **one modeling choice**, not a blanket retention rule. When privacy regulations or retention policies require erasing or masking snapshots, follow those policies; never use foreign keys as an excuse to retain snapshots indefinitely.

### 4.2. Never Overload One Address for Every Role

**Shipping address**, **billing address**, and **contact address** can all differ. A schema using a single **orders.address** for every purpose easily causes workflow bugs. When multiple address roles are needed, store separate snapshot column groups or an **order_address_snapshots** table keyed by **(order_id, address_role)** with roles such as **SHIPPING** and **BILLING**.

If one order ships multiple packages to different addresses, the snapshot grain may need to be **per shipment** rather than per order. Match snapshot grain to the entity actually committed, not whatever is quickest to put in one table.

## 5. Order Confirmation Must Capture Snapshots in a Reliable Workflow

Trusting a browser-submitted **unit_price = 150000** and copying it straight into the order is a severe bug, since clients can tamper with requests. The server must validate product selection, applicable price, promotions, and address before persisting.

For a minimal single-product, single-address flow, PostgreSQL can capture the snapshot in **one statement** inside a transaction:

~~~sql
BEGIN;

WITH selected_product AS MATERIALIZED (
    SELECT
        product_id, display_name, current_unit_price,
        currency, price_version
    FROM catalog_products
    WHERE product_id = 501
    FOR SHARE
),
selected_address AS MATERIALIZED (
    SELECT
        address_id, recipient_name, line1, city, country_code
    FROM customer_addresses
    WHERE address_id = 77
      AND customer_id = 42
    FOR SHARE
),
created_order AS (
    INSERT INTO orders (
        order_id,
        client_request_id,
        customer_id,
        confirmed_at,
        currency,
        source_address_id,
        ship_to_name_at_confirmation,
        ship_to_line1_at_confirmation,
        ship_to_city_at_confirmation,
        ship_to_country_at_confirmation,
        status
    )
    SELECT
        9001,
        'request-42-9001',
        42,
        clock_timestamp(),
        p.currency,
        a.address_id,
        a.recipient_name,
        a.line1,
        a.city,
        a.country_code,
        'CONFIRMED'
    FROM selected_product AS p
    CROSS JOIN selected_address AS a
    RETURNING order_id
)
INSERT INTO order_items (
    order_item_id,
    order_id,
    product_id,
    product_name_at_confirmation,
    unit_price_at_confirmation,
    product_price_version_at_confirmation,
    quantity
)
SELECT
    9101,
    o.order_id,
    p.product_id,
    p.display_name,
    p.current_unit_price,
    p.price_version,
    2
FROM created_order AS o
CROSS JOIN selected_product AS p
RETURNING order_item_id, unit_price_at_confirmation, line_subtotal;

COMMIT;
~~~

**How to read the example:** **selected_product** locks and reads the current accepted price and version; **selected_address** validates and reads the customer's address; **created_order** writes the chosen address; the final step writes the product's name, price, and version onto the order line. Because all CTEs run inside one statement, order and line creation are atomic at the statement level.

**Required application-level checks:** verify **exactly one line item** is returned before committing; if product or address is missing/invalid, **ROLLBACK**. The example uses hardcoded IDs for readability; production code uses bound parameters, authorization checks, stock availability, quantity bounds, currency checks, and full price adjustments. Handle lock errors, deadlocks, duplicate submissions, and retries per business rules.

### 5.1. Why Use FOR SHARE?

In PostgreSQL, **FOR SHARE** row locks on source rows force concurrent price or address updates to coordinate with order confirmation when touching the locked row. Under default **READ COMMITTED** isolation, the statement waits for concurrent updates and observes the committed state per PostgreSQL locking rules.

This narrows the race window when confirmation and price edits happen concurrently. However, **locks are a technical primitive, not a business contract**: a 15-minute quoted price, customer-specific promo, inventory reservation, or locked FX rate each require dedicated business rules. In distributed systems, a single database row lock cannot protect sources owned by other services; use versioned/identified quotes, confirmation tokens, or appropriate distributed workflows.

The **price_version** column records which catalog price version was read, yet **storing only the version number never replaces storing the locked price**. If price tables change without full immutable history, a bare version number cannot reconstruct the transaction amount.

### 5.2. Retrying a Request Must Not Create Two Orders

**client_request_id** carries a UNIQUE constraint so retrying the same confirmation request cannot create a second order under that ID. When a client retries after a timeout, a fresh **INSERT** hits the unique constraint violation. The application should load the existing order, verify the retried request carries matching business intent, and return that result; **never generate a new ID behind the scenes to create a duplicate order**.

In production systems, idempotency keys may need scoping by **customer_id** or tenant, retention windows, and payload fingerprints—plus distinguishing genuine retries from a customer intentionally placing a second order. A SQL transaction with unique keys can still behave wrongly if the boundary of "one order placement" is ill-defined.

## 6. Transaction Price Is Not Always the List Price

The example above uses **current_unit_price** solely to illustrate snapshotting. In reality, the customer-approved price often results from multiple layers:

~~~text
List price / customer-tier price
          |
          v
Promotions and coupon codes
          |
          v
Tax, fee, and rounding rules
          |
          v
Confirmed quote
          |
          v
Transaction-time price and line components
~~~

To store this accurately, specify:

- **Currency:** VND, USD, etc.; decimal scale and rounding rules. Never add different currencies directly.
- **Unit price semantics:** before or after discount, tax-inclusive or tax-exclusive. A bare **unit_price** column name is ambiguous.
- **Quantity and unit of measure:** pieces, kg, hours; does changing quantity re-trigger volume pricing tiers?
- **Discounts:** promo code, line-level discount allocation rules, order-level vs. shipping discounts.
- **Taxes:** tax rate and amount under the rule active at commitment, taxable base, and rounding. Current tax rates cannot rewrite taxes on historical receipts.
- **Exchange rate:** if currency conversion occurs, capture timestamp, rate source, source currency, converted amount, and rounding.
- **Collected amount:** may differ from expected confirmed amount due to partial payments, adjustments, or refunds.

An extended model might retain **list_unit_price_at_confirmation**, **discount_amount_at_confirmation**, **tax_amount_at_confirmation**, **final_line_amount**, and **currency**, alongside policy evidence where needed. You do not have to store every intermediate number if reproducibility is guaranteed—but never expect to recompute historical totals from **current prices, tax rates, or promotions**.

**Invariants must reflect the actual pricing contract.** Simple example: **line_subtotal = quantity × unit_price_at_confirmation**. With discounts and taxes, include those terms and rounding order so totals reproduce down to the smallest currency unit. An undefined "total_amount" column causes reconciliation failures even when update code runs error-free.

### 6.1. Price Changes After Confirmation: Preserving History

Verification example:

~~~sql
-- Today's catalog price:
UPDATE catalog_products
SET current_unit_price = 180000.00,
    price_version = price_version + 1
WHERE product_id = 501;

-- Confirmed order line retains the old price:
SELECT
    oi.order_item_id,
    oi.product_name_at_confirmation,
    oi.unit_price_at_confirmation,
    oi.quantity,
    oi.line_subtotal
FROM order_items AS oi
WHERE oi.order_id = 9001;
~~~

If the order was confirmed at 150,000 VND, querying the order line continues returning **150,000** and **300,000 VND** for quantity two. Updating **catalog_products** does not touch **order_items**—which is precisely the historical requirement.

Never write a job that "refreshes all historical order prices" from the current catalog. Doing so destroys **at_confirmation** semantics, even if both tables look consistent afterward.

## 7. Transaction Addresses Should Be Modeled as Business Evidence

An address is more than a single string. Depending on fulfillment and invoicing needs, you may require:

- Recipient name and contact method.
- Street number/name, apartment details, district, city/province, and country code.
- Postal code where applicable.
- Billing address, legal entity name, or tax identification details.
- Address normalization version or carrier validation result.
- Timestamp of customer approval and selection verification method.

Copying the address from **customer_addresses** to **orders.ship_to_*_at_confirmation** records what the customer approved. Subsequent edits to the customer's default address book must not mutate confirmed orders.

**Distinguish the confirmed address from the actual delivery address.** If a customer calls to change the destination after confirmation and the seller approves, create a new **shipping_instruction_revision** or **shipment_address_snapshot** record. Never silently overwrite the original confirmation and erase the audit trail.

Example extension modeling shipping instruction revisions:

~~~sql
CREATE TABLE order_shipping_revisions (
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    revision_no INTEGER NOT NULL CHECK (revision_no > 0),
    recorded_at TIMESTAMPTZ NOT NULL,
    approved_by TEXT NOT NULL,
    recipient_name TEXT NOT NULL,
    line1 TEXT NOT NULL,
    city TEXT NOT NULL,
    country_code CHAR(2) NOT NULL,
    change_reason TEXT NOT NULL,
    PRIMARY KEY (order_id, revision_no)
);
~~~

This table records each approved revision. When the initial snapshot lives on **orders**, clearly specify which record represents the original baseline, which revision governs fulfillment, and how the active address is resolved. Serialize concurrent revision numbering; a UNIQUE constraint alone will not prevent conflicts if application code reads-and-increments revision numbers without locking.

### 7.1. Never Treat Snapshots as a License to Keep Personal Data Forever

Addresses, recipient names, and phone numbers are personal data (PII). Transaction proof may justify retaining certain fields for a bounded period, subject to **legal basis, access restrictions, retention schedules, erasure/anonymization workflows, and copy controls**.

A system may need to:

- Restrict who can view full historical shipping addresses.
- Encrypt data, audit access logs, and mask fields in support UIs when full details are unnecessary.
- Enforce distinct retention limits per document type and operational record.
- Avoid spreading historical addresses into search indexes, caches, or analytics stores unless required.
- Implement deletion or anonymization workflows covering copies and secondary storage.

**Preserving historical facts** does not mean every PII field remains readable forever. Data models must separate transaction integrity from retention and privacy policies.

## 8. Joins That Corrupt History

### 8.1. Reading Current Price for Old Invoices

~~~sql
-- Wrong when locked-in price is required:
SELECT
    oi.order_item_id,
    oi.quantity,
    p.current_unit_price,
    oi.quantity * p.current_unit_price AS line_amount
FROM order_items AS oi
JOIN catalog_products AS p ON p.product_id = oi.product_id
WHERE oi.order_id = 9001;
~~~

This query replaces historical prices with current prices. It can also **drop rows** if the product was later deleted and **product_id** became NULL. For past invoices, read **unit_price_at_confirmation**, **product_name_at_confirmation**, **quantity**, and the confirmed transaction amounts.

If you want to **also** display today's price for comparison, LEFT JOIN the catalog and alias both columns distinctly; never overwrite historical prices.

### 8.2. Reading Current Address for Confirmed Orders

~~~sql
-- Wrong when the address confirmed at order time is required:
SELECT a.line1, a.city
FROM orders AS o
JOIN customer_addresses AS a
    ON a.address_id = o.source_address_id
WHERE o.order_id = 9001;
~~~

If the customer edits their address book, this query returns the new address; if the address was deleted, it returns zero rows. To inspect the original confirmation, read **orders.ship_to_line1_at_confirmation** and its sibling snapshot columns.

A different query might intentionally fetch the current address book to pre-fill a new checkout—which is fine when the **use case** truly calls for the current address.

### 8.3. "Syncing" Snapshots via Bulk-Update Triggers

If a trigger on catalog price updates automatically overwrites **every order_items.unit_price_at_confirmation** for that product, the system is rewriting history. That pattern belongs to a **read projection**, not a **snapshot**. Before writing a trigger, ask which business question the target column answers.

## 9. Verifying Snapshots vs. Verifying Current-State Copies

For a read-acceleration copy like **product_cards.current_price_display**, the invariant might be:

> Once the projection has processed price version V, the displayed price equals the source price at exact version V.

Verify by comparing price/version pairs, sync lag, and processed events. On drift, refresh or rebuild the projection.

For order-line price snapshots, **there is no invariant saying "transaction price = today's catalog price."** Appropriate invariants instead include:

- Confirmed line quantity is **greater than 0**.
- Unit price at confirmation and currency satisfy the transaction contract; line total matches the locked formula.
- Prices and addresses on finalized orders are never mutated by catalog or profile updates.
- When adjustments occur, the system traces original values, deltas, actor, and reason.
- Each **client_request_id** maps to at most one order placement per deduplication rules.

Example calculation check in the illustrative schema:

~~~sql
SELECT
    oi.order_item_id,
    oi.line_subtotal,
    oi.quantity * oi.unit_price_at_confirmation
        AS expected_subtotal
FROM order_items AS oi
WHERE oi.line_subtotal IS DISTINCT FROM
      oi.quantity * oi.unit_price_at_confirmation;
~~~

With a generated column as defined above, the database maintains the value automatically. Still, this query illustrates the **right kind of invariant**: cross-checking committed fields against each other, never against current catalog prices.

If cross-checking against approved quotes, **approved_quotes**, **quote_lines**, or **OrderConfirmed** events retain the terms committed at that event. Comparison rules must clarify quote expiration and replacement semantics. Never assume every quote became a confirmed order.

### 9.1. Audit Trails and Immutability Boundaries

A snapshot is normally **immutable post-confirmation**, though business needs sometimes require fixing address typos, issuing credit memos/adjustments, or canceling and re-ordering. Options include:

- **Keep original + versioned revisions**: ideal when exact change history must remain inspectable.
- **Record compensating/adjustment events**: fits payment, refund, and ledger flows.
- **Issue superseding documents**: fits formal invoicing workflows, maintaining links and statuses across documents.
- **Restrict direct UPDATEs** via DB permissions, owning-service boundaries, controlled triggers, or append-only tables where appropriate.

These options do not mean every snapshot must be physically immutable in every situation. What matters is that **confirmed facts and post-confirmation adjustments remain distinguishable, traceable, and reproducible under policy**.

## 10. When Can You Just Store Price/Address History and Query by Time?

A fair counterargument is: "If we have an effective-dated price history table, why not JOIN to find the price at confirmation time instead of copying it onto the order line?"

You can model a **temporal price history table** or **Slowly Changing Dimension Type 2**:

~~~text
product_price_history
  product_id
  effective_from
  effective_to
  unit_price
  currency
  price_policy_id
~~~

A transaction can then JOIN on **product_id** and **effective_from ≤ confirmed_at < effective_to** to look up the historical price. However, this only reconstructs transactions reliably if:

1. Every price version ever applied is retained completely without unhandled gaps or overlaps.
2. The effective list price truly equals the transaction price—no custom discounts, negotiations, taxes, FX rates, or overrides altered it.
3. Confirmation timestamps and version-precedence rules are strictly consistent.
4. Retroactive corrections to the price table either never alter preserved orders or preserve full audit versions.
5. Products and terms remain referenceable even if the active catalog is modified or retired.

When those conditions hold and business needs only require reconstruction from controlled pricing tables, temporal joins can work. Yet many orders carry **individually accepted terms**, making direct capture on the transaction record the clearest way to preserve truth. Temporal price tables and transaction snapshots complement each other: one records **published effective prices**, while the other records **exact terms applied to a transaction**.

**Two time dimensions:** when historical data undergoes retroactive corrections, distinguish **valid time** (when a fact applies in business reality) from **transaction/recorded time** (when the system recorded or learned it). Bitemporal modeling fits complex audit problems, yet still does not replace capturing committed transaction amounts.

## 11. Post-Confirmation Changes: Create New Business Records, Don't Blindly Rewrite the Past

Common scenarios:

| Scenario | Recommended Data Handling | What to Avoid |
| --- | --- | --- |
| Catalog price rises after order placement | Keep locked price on past order lines; apply new price to new orders | UPDATE prices on already-confirmed order lines |
| Customer edits default address | Update live address book; preserve old order snapshots | JOIN live profile to re-render order history |
| Customer changes delivery address post-confirmation (approved) | Create new revision / shipping instruction with approval trail | Overwriting initial confirmed address without trace |
| Customer edits quantity before confirmation | Recompute quote, re-confirm if needed | Treating stale cart subtotal as committed price |
| Partial return | Record return/refund lines and refunded amount per policy | Silently editing original item price to "match remaining balance" |
| Order cancellation | Record cancellation status/event, settle payment obligations | Deleting snapshots needed for reconciliation without process |
| Document adjustment | Issue adjustment document or linked revision | Overwriting old documents without audit trail |

**Post-transaction monetary adjustments** do not necessarily alter the originally confirmed amount. For instance, a customer buys 300,000 VND and receives a 100,000 VND refund: "gross ordered value" and "net revenue" are two separate metrics. Overloading one column for both corrupts both design and reporting.

## 12. Handling Legacy Systems That Never Stored Snapshots

Migrating legacy data is harder than adding a column. Suppose the legacy system stored only **order_items.product_id** and read prices from **catalog_products.current_unit_price**. After multiple price changes, you cannot reliably deduce historical paid prices from today's catalog alone.

A controlled migration workflow:

1. **Define the new contract** and exact cutover timestamp when snapshot capture begins officially.
2. **Add new columns** accommodating the transition; keep them nullable initially and track data-quality flags as appropriate.
3. **Enable snapshot writes for new orders**, covering every confirmation path without gaps from cutover onward.
4. **Gather historical evidence for old orders:** issued invoices, payment captures, valid price-history logs, saved quotes, or event logs.
5. **Backfill only where evidence exists**, documenting source, method, and confidence; explicitly mark unrecoverable fields as unverified per policy.
6. **Reconcile** against documents and payment totals; inspect discrepancies, currencies, rounding, and multi-edit cases.
7. **Switch read paths** for new and legacy orders based on data completeness, with explicit handling for records lacking historical evidence.

**Never assume by default** that today's product price equals last year's transaction price, or today's default address equals an old shipping address. Backfilling that way makes reports look "complete" while actually **fabricating history**.

During transition, a nullable field meaning "unknown" differs fundamentally from zero; never replace NULL with 0 when 0 is a valid monetary amount. If **NOT NULL** constraints are desired for new orders, enforce them progressively after verifying data and write paths.

## 13. Snapshots in Document, Graph, and Analytical Models

Distinguishing current state from point-in-time facts applies equally outside relational databases.

| Model | How Transaction Snapshots Are Represented | Risks to Control |
| --- | --- | --- |
| **Relational** | **at_confirmation** columns on order lines or FK-linked snapshot tables | Accidentally joining live tables, missing write paths, non-atomic confirmation |
| **Document** | **order** document embeds line items, locked prices, and shipping address | Overwriting snapshots during profile sync; document size and cross-store atomicity limits |
| **Graph** | **Order–Product** edge carries event price, or **OrderLine** vertex holds locked terms | Traversing to current price on Product vertex instead of edge/event terms |
| **Analytics** | Sales fact holds transaction-time amounts; historical dimensions capture context | Using current-only dimensions to misclassify historical records |
| **Event log** | **OrderConfirmed** carries committed payload; adjustments emit follow-up events | Missing schema versions, dropped events, out-of-order replay, incomplete fields |

In a document database, **embedding the shipping address inside the order document** is usually convenient because it is read alongside the order and must remain frozen at confirmation. Conversely, embedding the **customer's current address** into millions of documents for profile display is a very different sync problem.

In a graph database, current price properties on Product vertices change over time; **transaction prices** belong on the entity/edge representing the purchase event or order line. Following edges straight to current price properties recreates the exact same historical bug.

In analytics, "Sales by **current** category" differs from "Sales by category **at time of sale**." Locked monetary amounts live in the fact table; classification attributes require either current dimensions or effective-dated dimensions depending on the question. Never build one summary table and serve both interpretations without explicit labeling.

## 14. Decision Framework: Snapshot, Read Copy, or Both?

Before adding a duplicated column, complete a table **for each attribute**:

| Question | If Transaction Snapshot | If Read-Acceleration Copy |
| --- | --- | --- |
| What must it answer? | What price/address was confirmed when? | What current price/address/name is displayed now? |
| Commitment event? | OrderConfirmed, InvoiceIssued, ShipmentDispatched, etc. | Not necessarily tied to an immutable commitment event |
| Value creation source | Validated terms and selections at the event | Authoritative live table/service owning the attribute |
| When live source changes | Preserve, or record audited revision | Sync per consistency rules and allowed lag |
| How to verify correctness? | Reconcile against receipts/terms/events and pricing formulas | Reconcile against live source, versions, and lag |
| What must be protected? | Transaction history, PII, financial integrity | Consistency, access control, cache/projection freshness |
| Performance trade-off needed? | Store to preserve historical truth regardless of JOIN speed | Duplicate only when workload and benchmarks justify it |
| How to handle errors? | Investigate evidence, apply audited adjustment | Refresh or rebuild from source of truth |

A system may legitimately need **all three places**: **catalog_products.current_unit_price** for live pricing; **order_items.unit_price_at_confirmation** for committed orders; and **product_cards.current_price_display** for search pages. Those three columns do not share one update contract, so one sync rule cannot govern all three.

## 15. Practice Exercises

### Exercise 1 — Price Changes Before Delivery

A customer confirms an order for 3 pens at 20,000 VND/pen, excluding other fees. Two days later, the catalog list price rises to 25,000 VND/pen before shipment.

**Question:** In confirmed order details, should you read the current product table or the order-line price? What is the line total for the three pens in this example?

### Exercise 2 — Default Address Change

A customer places an order with Address A, then updates their default address to B. Support needs to verify where the customer approved shipping at checkout; the next-purchase checkout screen needs to suggest an address.

**Question:** Where should each screen read its data from?

### Exercise 3 — Quoted Price and Promo Code

A product lists at 500,000 VND, but the customer applies a 50,000 VND voucher and confirms a final pre-tax price of 450,000 VND. The system only records **product_id** and the general catalog **price_version**.

**Question:** Why is that insufficient to reconstruct the transaction amount? What else should be stored?

### Exercise 4 — Backfilling Legacy Data

There are 200,000 historical orders storing only product_id without locked-in prices. Catalog prices changed many times; the team proposes running **UPDATE order_items SET unit_price_at_confirmation = products.current_unit_price**.

**Question:** Is this trustworthy? If no historical receipts exist, how should legacy records be handled?

### Exercise 5 — Shipping Address Changed Post-Confirmation

An order confirmed Address A, but the customer calls to switch to B before dispatch. Staff approve, and the carrier delivers to B.

**Question:** Should you overwrite the original snapshot to B or create an additional record? What minimum fields are needed to explain the divergence?

### Suggested Answers

1. Read **unit_price_at_confirmation** on the order line: **3 × 20,000 = 60,000 VND** assuming no discounts, fees, or taxes. The 25,000 VND price applies only to new effective catalog periods.
2. Support reads the **order-confirmation address snapshot** (A); the new-checkout screen can read the **current address book** (B). If actual delivery instructions changed later, also inspect the active shipping revision.
3. A general catalog price version does not capture customer-specific vouchers or agreed terms. Store the locked price/discount fields or sufficient evidence to reproduce the formula, currency, taxes, and rounding rules.
4. Untrustworthy: current prices do not prove past prices. Search invoices, payment captures, quotes, or other evidence; where none exist, mark records **unverified** per migration policy rather than writing current prices as historical fact.
5. Preserve the record that **A was originally confirmed**, and add an approved **shipping revision/instruction for B**; capture timestamp, approving actor, reason, effective address, and link to the shipment. Keep rules unambiguous for resolving the active delivery address.

## 16. Takeaways

**A transaction-time price or address snapshot is a historical fact anchored to a business boundary.** It may physically duplicate data that once appeared in product or profile tables, yet must never track subsequent live changes merely to make two tables match.

**A read-acceleration copy is a read model of mutable state.** It requires a source of truth, refresh rules, lag bounds, and reconciliation; creating one should follow access-pattern analysis and measurement evidence.

When designing, ask: **"Which point in time must this field answer for, should later source edits change that answer, and what evidence verifies it?"** Answering these three questions prevents rewriting history and keeps your data model safe to evolve.
