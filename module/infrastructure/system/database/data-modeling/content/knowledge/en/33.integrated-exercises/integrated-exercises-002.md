# Drawing a Conceptual Model for Customers, Products, Orders, and Payments

## Goals and practice deliverables

In the **DATABASE_DATA_MODELING** module, we turn business requirements into a clear data model—from entities, relationships, and constraints to logical/physical schemas—while comparing relational, document, graph, and analytical options so the design can evolve and be verified. This lesson in the **Integrated Exercises** chapter takes you from a short sales prompt to a **conceptual data model** that can be discussed with domain experts.

**Prompt:** A store sells products to customers. A customer can place an order containing multiple products; each order may be unpaid, paid once, or paid in multiple installments. The system must remember which products were ordered, along with the quantities and prices agreed at the time of ordering; it must also track payment attempts even when an attempt fails.

**Deliverables to complete:**

1. A list of **entities** with business definitions and identifiers.
2. A **conceptual ER** diagram showing relationships, optionality/mandatory rules, and *cardinality*.
3. A set of **business rules** phrased as statements testable with examples.
4. Three to five **counterexample scenarios** verifying that the model preserves historical truth and avoids double-counting.
5. A list of **assumptions still needing confirmation** before implementing a logical or physical schema.

This is an exercise in building a model from hypothetical requirements; it does **not** describe the process of any specific real company. In a real project, choices such as guest checkout, draft orders, refunds, or multiple payers **must be confirmed by the business owner**.

### Concepts you will use

- **Entity:** a type of object or event with its own identity and lifecycle.
- **Attribute:** information describing an entity, with clear meaning and scope.
- **Identifier:** a characteristic that distinguishes instances of the same entity.
- **Relationship:** how entities associate according to a business rule.
- **Cardinality/optionality:** the minimum and maximum number of instances an object may link to.
- **Associative entity:** a many-to-many relationship with its own identity/attributes, such as **Order Line**.
- **Invariant:** a condition that must hold true in every valid state within the agreed scope.

## 1. Reading the prompt and underlining business facts

Read the following description before looking at the solution:

> “A customer can create multiple orders. Each submitted order belongs to one customer and consists of at least one order line. Each line records one product, quantity, and unit price at the time of ordering. A product can appear in multiple different orders. An order can have multiple payment attempts, including failed attempts. One payment attempt belongs to exactly one order.”

Breaking down the clauses:

| Statement | What to bring into the model | Verification question |
|---|---|---|
| A customer can create multiple orders | **Customer → Order** is one-to-many | Can a new customer have 0 orders? |
| Each submitted order belongs to one customer | Each **Order** has exactly one **Customer** | Is guest checkout supported? |
| An order contains multiple products | Conceptual **Order ↔ Product** many-to-many | Does the link carry quantity/unit price? |
| Order lines carry finalized quantity and unit price | Need **OrderLine** entity | Should catalog price changes alter past orders? |
| A product can appear in many orders | **Product → OrderLine** one-to-many | Can an unsold product exist? |
| An order has multiple payment attempts | **Order → Payment** one-to-many | Can an order have zero payment attempts yet? |
| Payments have different outcomes | Payment has **status/lifecycle** | Does a failed attempt count as collected cash? |
| One payment attempt belongs to one order | Each **Payment** belongs to exactly one **Order** in scope | Can one transaction pay multiple orders? |

Do not start by saying “there must be four tables.” The user mentions **four major objects**, but the fact that an order contains products with agreed quantities and prices requires examining a **fifth business entity: OrderLine**.

### 1.1. Locking assumptions for the primary solution

To give the diagram a verifiable reference answer, we agree on:

1. Modeled orders are **valid submitted/placed orders**, excluding carts and empty drafts. Each order therefore has **at least one line**.
2. Each order has **exactly one identified customer**. Guest checkout is out of scope for the primary diagram.
3. Each line links to **exactly one product** in the catalog, while **finalized quantity and unit price** belong to the **transaction line**, not as attributes that change with the product's current price.
4. A product may have **never been sold** or may appear in many lines across many orders.
5. A `Payment` represents **one distinct payment processing attempt** for an order, with statuses such as `PENDING`, `FAILED`, `CAPTURED`. A failed attempt is **not** counted as collected funds.
6. An order may have **zero payments**, one payment, or multiple payments due to retries or installments. In the primary exercise, **one payment belongs to only one order**.
7. Historical orders and products must not lose traceability simply because a customer or product updates details or becomes inactive.
8. Taxes, shipping fees, refunds, shared coupons, and multi-order batch payments are **not** in the minimal diagram; they will be treated as extensions.

**Assumptions must be declared before drawing.** Changing assumption 1 or assumption 6 alters the diagram's cardinality; there is no single “universally correct” ER diagram for every retail system.

## 2. Selecting entities by identity and lifecycle

### 2.1. The four entities named in the requirement

| Entity | Definition in this exercise | Example instance | Do not confuse with |
|---|---|---|---|
| **Customer** | Identified person/account holder placing orders | Customer `C101` | Name/email: may duplicate or change |
| **Product** | Catalog item with a stable code | Product `P220` | Transaction price on individual purchases |
| **SalesOrder** | A valid submitted purchase request | Order `O9001` | Cart, payment, or shipment |
| **Payment** | One attempt to collect funds for an order, with its own status | Failed Payment `PAY-17` | Overall payment state of the order |

### 2.2. Why add OrderLine?

Consider order `O9001`:

~~~text
Product P220: quantity 2, agreed unit price 120,000 VND
Product P310: quantity 1, agreed unit price 80,000 VND
~~~

If we only draw a many-to-many `SalesOrder — Product` relationship without modeling the line items, **quantity and unit price** have no clear place to live. The same product can be bought on two orders at different prices. Therefore we need:

**OrderLine:** an item entry recorded on a specific order, carrying product, quantity, agreed unit price/discount, and line sequence number.

~~~text
SalesOrder(O9001)
    ├── OrderLine(1) → Product(P220), quantity=2, unitPrice=120000
    └── OrderLine(2) → Product(P310), quantity=1, unitPrice=80000
~~~

OrderLine is an **associative entity** between Order and Product, yet **not merely a meaningless bridge table**. It expresses the fact “this product was ordered under these terms in a specific order.”

### 2.3. Distinguishing entities from attributes

A concept is an **attribute** when it merely describes an entity and has no identity/lifecycle that needs independent management within the exercise scope. Examples:

- `customerName`: display attribute of Customer.
- `orderedAt`: business timestamp of SalesOrder.
- `quantity`: attribute of OrderLine.
- `paymentStatus`: status of a Payment attempt.

A concept may become a **separate entity** when requirements demand enough detail:

- `PaymentMethod` becomes an entity if saved payment instruments must be managed across repeated uses.
- `Address` becomes an entity/owned value if multiple addresses and delivery histories must be tracked.
- `Refund` becomes an entity if individual refund transactions must be tracked independently.

Do not add an entity merely because a noun appears in the UI; check **identity, lifecycle, relationships, and query needs**.

## 3. Drawing the initial conceptual ERD

### 3.1. Recommended diagram within scope

~~~mermaid
erDiagram
    CUSTOMER ||--o{ SALES_ORDER : "places"
    SALES_ORDER ||--|{ ORDER_LINE : "contains"
    PRODUCT ||--o{ ORDER_LINE : "purchased_in"
    SALES_ORDER ||--o{ PAYMENT : "has_payment"
~~~

This is a **conceptual diagram**: it specifies **object types and association rules**, without yet locking in foreign key column names, SQL data types, indexes, or partitioning strategies.

### 3.2. Reading Crow's Foot notation on both ends

| Symbol at entity end | Multiplicity | Meaning |
|---|---|---|
| `||` | **1..1** | Exactly one, mandatory |
| `o|` | **0..1** | Zero or one |
| `|{` | **1..N** | One or more |
| `o{` | **0..N** | Zero or more |

For example, `CUSTOMER ||--o{ SALES_ORDER` means:

- Reading from **one SalesOrder** to Customer: an order has **exactly one Customer**.
- Reading from **one Customer** to SalesOrder: a customer may have **0 or more SalesOrders**.

Similarly, `SALES_ORDER ||--|{ ORDER_LINE` means:

- An OrderLine must belong to **exactly one SalesOrder**.
- A SalesOrder within the “valid submitted order” scope has **at least one OrderLine**.

When reading an ERD, always interpret **both directions**. Never see a crow's foot and conclude “both sides are many.”

### 3.3. Cardinality and optionality table

| Relationship | How many right-side objects per left-side object? | How many left-side objects per right-side object? |
|---|---|---|
| Customer — SalesOrder | 0..N orders for one customer | 1 customer for one order |
| SalesOrder — OrderLine | 1..N lines for one valid order | 1 order for one line |
| Product — OrderLine | 0..N lines for one product | 1 product for one line |
| SalesOrder — Payment | 0..N payment attempts for one order | 1 order for one payment |

**Cardinality describes what the business permits, not the row count currently observed in sample data.** If sample data currently has only one payment per order, that is insufficient to conclude the relationship is 1:1.

## 4. Identifiers and business-meaningful attributes

### 4.1. Describing attributes at the conceptual level

| Entity | Candidate identifier / identity | Representative business attributes |
|---|---|---|
| Customer | Stable `customerId` within source scope | Display name, active status, permitted contact channels |
| Product | `productId` or defined stable SKU/variant | Name, description, sellable status, current list price |
| SalesOrder | Stable `orderId`; display `orderNumber` may differ | Placed timestamp, order status, currency, shipping address at order time if needed |
| OrderLine | `(orderId,lineNo)` when an order has multiple lines | Product, quantity, agreedUnitPrice, lineDiscount |
| Payment | Internal/published `paymentId` and appropriate provider reference | Amount, currency, method, status, requestedAt, capturedAt |

At the **conceptual level**, `orderId` and `lineNo` express **business identity**. There is no need yet to decide `UUID` vs `BIGINT`, physical composite keys vs surrogate keys. Those decisions belong to **logical/physical modeling**.

**Do not default to email as the Customer key.** Emails can change, be shared, or be omitted; a stable `customerId` is usually a better identity in this exercise. Likewise, a display `orderNumber` may only be unique per store/tenant.

### 4.2. A product may have multi-level identifiers

In practice, “Product” might look like:

~~~text
Product: Basic T-shirt
  Variant / SKU: T-shirt - M - Blue
  Variant / SKU: T-shirt - L - Blue
~~~

If customers order **specific variants**, an OrderLine must reference **SKU/Variant**, not just the generic Product name. There are two options:

- **Exercise's simplifying assumption:** each `Product` is already a sellable item with a stable code and line unit price.
- **Practical extension:** add `ProductVariant`; OrderLine references the exact Variant to avoid mixing up size/color.

Do not insert Variant into the primary diagram when the prompt does not require it, but document this assumption so the diagram does not mislead implementers.

### 4.3. What information must be preserved at order time?

A Product's list price may increase from 120,000 to 150,000 after a customer places an order. We must still be able to answer: **at what price did the customer order?**

Therefore `agreedUnitPrice` belongs on **OrderLine**, rather than relying solely on Product's `currentPrice`.

If voucher reconciliation is required when a Product changes name or is discontinued, OrderLine/order may also need a **snapshot of name, SKU, description/tax rate at sale time**, per policy. This is a decision about **transaction history**, not blind copying of every Product attribute.

## 5. Step-by-step guide to drawing a conceptual diagram

### Step 1 — List nouns and identify candidate entities

Underline *customer, product, order, payment*. Check whether each noun has its own identity, can exist independently, and needs to be queried.

### Step 2 — Uncover the truth behind many-to-many relationships

“An order has many products; a product appears in many orders” forms an M:N relationship. Ask: **where do quantity and price belong?** If they belong to a specific purchase instance, create **OrderLine** as an associative entity.

### Step 3 — Write two sentences for every relationship

Example:

~~~text
One Customer may have 0..N SalesOrders.
One SalesOrder must belong to exactly 1 Customer.

One valid SalesOrder contains 1..N OrderLines.
One OrderLine must belong to exactly 1 SalesOrder.

One Product may appear in 0..N OrderLines.
One OrderLine must reference exactly 1 Product.

One SalesOrder may have 0..N Payments.
One Payment must belong to exactly 1 SalesOrder.
~~~

### Step 4 — Add identifiers and minimal attributes

Record `customerId`, `productId`, `orderId`, `(orderId,lineNo)`, `paymentId`; then place `quantity` and `agreedUnitPrice` on **OrderLine**, and `amount` and `status` on **Payment**.

### Step 5 — Test a counterexample for every notation

If you drew Order–Payment as 1:1, test an **unpaid** order, or a **failed payment followed by a retry**. If the diagram cannot represent it, adjust the relationship to 0..N according to the chosen assumptions.

### Step 6 — Document scope and open items

Mark the diagram as a “proposed design” only after listing **guest checkout, draft orders, refunds, batch payments, products/variants, and statuses** as items requiring confirmation.

### Step 7 — Review with domain experts

Do not vaguely ask “is the diagram right?”. Ask using **concrete scenarios**: “What if a customer has 0 orders?”, “Can one order use 2 payment cards?”, “What if two attempts with the same provider return duplicate callbacks?”.

## 6. Validating the diagram with a small dataset

Suppose the store has:

### 6.1. Customers

| Customer | Name |
|---|---|
| `C101` | An |
| `C102` | Binh |
| `C103` | Chi |

`C103` just registered and **has not placed an order yet**. This customer's existence proves why the SalesOrder end of Customer–SalesOrder must allow **0**.

### 6.2. Products

| Product | Name | Current catalog price |
|---|---|---:|
| `P220` | Notebook | 150,000 VND |
| `P310` | Pen | 80,000 VND |
| `P450` | Water bottle | 200,000 VND |

`P450` has no orders yet; it is still a valid Product. `P220` currently costs 150,000 but previously sold at 120,000.

### 6.3. Orders

| Order | Customer | Status | Placed at |
|---|---|---|---|
| `O9001` | `C101` | `CONFIRMED` | 2026-11-20 09:00 UTC |
| `O9002` | `C101` | `CONFIRMED` | 2026-11-21 10:00 UTC |
| `O9003` | `C102` | `CONFIRMED` | 2026-11-21 11:00 UTC |

`C101` has **two orders**, `C102` has **one order**, and `C103` has **zero orders**.

### 6.4. Order lines

| Order | Line | Product | Quantity | Agreed unit price | Line amount |
|---|---:|---|---:|---:|---:|
| `O9001` | 1 | `P220` | 2 | 120,000 | 240,000 |
| `O9001` | 2 | `P310` | 1 | 80,000 | 80,000 |
| `O9002` | 1 | `P220` | 1 | 150,000 | 150,000 |
| `O9003` | 1 | `P310` | 3 | 80,000 | 240,000 |

Simplifying assumption: no discounts/taxes/shipping fees yet, all in VND. Thus:

\[
\text{lineAmount}=\text{quantity}\times\text{agreedUnitPrice}.
\]

And:

\[
\begin{aligned}
\text{O9001 total}&=240.000+80.000=320.000,\\
\text{O9002 total}&=150.000,\\
\text{O9003 total}&=240.000.
\end{aligned}
\]

**The current price of P220 must not be retroactively applied to O9001.** Without storing the agreed unit price on OrderLine, simply changing a Product's price corrupts past order totals.

### 6.5. Payment attempts

| Payment | Order | Requested amount | Status | Considered collected cash? |
|---|---|---:|---|---:|
| `PAY-01` | `O9001` | 320,000 | `FAILED` | 0 |
| `PAY-02` | `O9001` | 200,000 | `CAPTURED` | 200,000 |
| `PAY-03` | `O9001` | 120,000 | `CAPTURED` | 120,000 |
| `PAY-04` | `O9003` | 240,000 | `PENDING` | 0 at time of check |

`O9002` has no payment attempts yet. Under the assumption **CAPTURED = collection confirmed**, we have:

~~~text
O9001:
    Merchandise subtotal by line = 320,000
    Total requested across attempts = 640,000
    Recorded collected cash = 200,000 + 120,000 = 320,000

O9002:
    Merchandise subtotal by line = 150,000
    No Payment yet => collected cash = 0

O9003:
    Merchandise subtotal by line = 240,000
    Payment PENDING => not yet added to collected cash
~~~

**Key takeaway:** `SUM(Payment.amount)` across **all statuses** is not “collected cash.” For `O9001`, total requested across three attempts is 640,000, while actual captured cash per the example rule is only 320,000.

If payments have statuses like `AUTHORIZED`, `PARTIALLY_CAPTURED`, `VOIDED`, `REFUNDED`, or multiple captures per authorization, you must redefine the **grain of Payment** or add **PaymentCapture/Refund** so “funds authorized/held” is not confused with “cash captured.”

## 7. Testing the diagram with “can this happen?” questions

### 7.1. Customer who has never bought anything

**Scenario:** `C103` exists but has no orders.

**Expectation:** Valid. The Customer → SalesOrder relationship has **0..N** on the order side, not **1..N**.

### 7.2. Product that has never been sold

**Scenario:** `P450` is published in the catalog but does not appear in any OrderLine.

**Expectation:** Valid. Product → OrderLine allows **0..N**. Deleting a Product solely because it has no sales is a separate business policy decision.

### 7.3. One order with multiple products

**Scenario:** `O9001` contains P220 and P310.

**Expectation:** Valid. One SalesOrder links to **multiple OrderLines**. Each OrderLine links to one Product; never try to store `productId1`, `productId2` directly on SalesOrder.

### 7.4. One product appearing in multiple orders at different prices

**Scenario:** P220 in `O9001` has price 120,000; in `O9002` it has price 150,000.

**Expectation:** Valid. Transaction price belongs on **OrderLine**. A single price on Product cannot express purchase history.

### 7.5. Unpaid order

**Scenario:** `O9002` has been placed but the customer hasn't initiated payment yet.

**Expectation:** Valid. SalesOrder → Payment allows **0**.

### 7.6. Rejected payment followed by retries

**Scenario:** `PAY-01` fails; two subsequent attempts `PAY-02` and `PAY-03` collect the full amount in two installments.

**Expectation:** There are **three Payments** linked to the same Order; each Payment carries its own status and amount. Never overwrite `PAY-01` to succeeded if the business needs payment attempt history.

### 7.7. An order line without an order

**Scenario:** There is an `OrderLine` for P220 with no identifiable SalesOrder.

**Expectation:** Invalid within exercise scope. Every OrderLine belongs to **exactly one** SalesOrder. Items in a cart or quote are not OrderLines of a placed order unless the model is extended.

### 7.8. A Payment not belonging to any order

**Scenario:** The provider sends a transaction that cannot yet be mapped to an `orderId`.

**Expectation:** The integration layer may need to park the message in a **reconciliation staging area**; however, a **business Payment accepted into the core model** must link to exactly one SalesOrder. Never attach it to a random order just to satisfy the relationship.

## 8. Turning the diagram into testable business rules

An ER diagram cannot express all invariants by itself. Write the rules as statements:

| Code | Rule | Test/Verification |
|---|---|---|
| BR-01 | Each placed order belongs to exactly one identified customer | No order with unknown Customer |
| BR-02 | A customer may have zero orders | Customer C103 is valid |
| BR-03 | A placed order has at least one line | Reject confirmed order with 0 OrderLines |
| BR-04 | Each OrderLine belongs to one Order and references one Product | No orphan lines |
| BR-05 | A Product may have never been ordered | Product P450 is valid |
| BR-06 | Line quantity is positive within exercise scope | No line with quantity = 0 or negative |
| BR-07 | Transaction price is locked on OrderLine, not recomputed from Product | O9001 retains P220 price = 120,000 |
| BR-08 | Each Payment represents a distinct processing attempt | Payment ID distinguishes attempts |
| BR-09 | An order may have 0..N Payments | O9002 has 0; O9001 has 3 |
| BR-10 | A Payment belongs to exactly one Order in exercise scope | Do not split one Payment across orders |
| BR-11 | `FAILED`/`PENDING` Payments do not add to collected cash | O9001 excludes PAY-01 |
| BR-12 | Currency and monetary formulas of order/payment must match | Never add two different currencies |
| BR-13 | Never delete order history when a product changes price or is hidden | Old orders remain queryable and reconcilable |
| BR-14 | Retried callbacks/payment requests must not create duplicate logical records | Idempotency via provider key |

Some rules are **simple constraints** (each OrderLine has one Product), while others require **application logic or transactions** (an order must have at least one line when confirmed) or **provider integration handling** (duplicate payment callbacks). Conceptual modeling helps us discover rules; **it does not mean all of them can be enforced by FKs alone**.

### 8.1. “Order total” does not always equal total Payment amount

Never write a blanket invariant like:

~~~text
SUM(OrderLine.amount) = SUM(Payment.amount) at all times
~~~

It breaks when an order is unpaid, payment fails, payment is partial, paid in installments, has taxes/fees, order-level discounts, refunds, or pending reconciliation.

Instead, documentation must distinguish:

- **Merchandise subtotal:** sum of locked line amounts across OrderLines.
- **Payable amount:** amount due on the order after applicable charges/discounts.
- **Captured amount:** total cash actually collected per valid capture transactions.
- **Refunded amount:** total cash refunded, if the model supports refunds.
- **Outstanding balance:** remaining amount due per approved financial definition.

In the minimal example, *payable* happens to equal *subtotal*, but **never force that as a rule for every store**.

### 8.2. Consistency between order status and payment status

Order may carry:

~~~text
OrderStatus: CONFIRMED, CANCELLED, FULFILLED ...
~~~

Payment may carry:

~~~text
PaymentStatus: PENDING, FAILED, CAPTURED ...
~~~

These are **two distinct lifecycles**. A `CONFIRMED` order is not necessarily `PAID`. A `CAPTURED` payment does not automatically prove products have been delivered.

If an order-level “`PAID`” status is needed, determine whether it is a **managed business state** or a **derived state computed from captured vs payable amounts**. If both are stored, update and reconciliation rules are needed so they do not drift.

## 9. Common modeling mistakes and how to fix them

### Mistake A — Attaching products directly to the order

~~~mermaid
erDiagram
    CUSTOMER ||--o{ SALES_ORDER : "places"
    SALES_ORDER }o--o{ PRODUCT : "buys"
    SALES_ORDER ||--o{ PAYMENT : "pays"
~~~

This diagram expresses a many-to-many Order–Product relationship, yet **fails to show where quantity, locked unit price, line sequence, and line discount live**. If a system only needed “which products relate to an order,” a bare M:N might suffice. For this exercise, **it is insufficient**.

**Fix:** create `OrderLine` and place the attributes of a purchase line onto this entity. The M:N becomes two 1:N edges meeting at OrderLine.

### Mistake B — Forcing every order to have exactly one Payment

~~~mermaid
erDiagram
    SALES_ORDER ||--|| PAYMENT : "only_once"
~~~

An unpaid order cannot exist; a rejected payment followed by a retry cannot record all processing attempts. This diagram fails immediately against the sample dataset.

**Fix:** `SALES_ORDER ||--o{ PAYMENT`, while agreeing that Payment is **one attempt/transaction**, not the aggregate payment status of the order.

### Mistake C — Putting quantity on Product

If Product has an attribute `quantity` without clarifying its meaning, the question “how many P220 units did order O9001 buy?” cannot be answered from stock quantity or catalog quantity. **Ordered quantity** belongs to **OrderLine**; **inventory quantity** belongs to a separate location/time warehouse model if needed.

### Mistake D — Using names or display codes as keys

Customers share names, products share names, and order numbers can repeat across stores. Using `customerName` or `productName` as an identifier merges two distinct valid objects. Choose a **stable ID with a clear namespace** before moving to the logical schema.

## 10. Redrawing the ERD with attributes to complete the submission

Once relationships are locked, add key attributes to the diagram. Here `string`, `number`, `money`, `datetime` are **illustrative descriptive labels in Mermaid**, not commitments to SQL types or DBMS currency rules.

~~~mermaid
erDiagram
    CUSTOMER {
        string customerId
        string displayName
        string lifecycleStatus
    }
    PRODUCT {
        string productId
        string productName
        money currentListPrice
        string catalogStatus
    }
    SALES_ORDER {
        string orderId
        string orderNumber
        datetime placedAt
        string currency
        string orderStatus
    }
    ORDER_LINE {
        number lineNo
        number quantity
        money agreedUnitPrice
        money lineDiscount
    }
    PAYMENT {
        string paymentId
        string providerReference
        money requestedAmount
        string currency
        string paymentStatus
        datetime requestedAt
    }

    CUSTOMER ||--o{ SALES_ORDER : "places"
    SALES_ORDER ||--|{ ORDER_LINE : "contains"
    PRODUCT ||--o{ ORDER_LINE : "appears_in"
    SALES_ORDER ||--o{ PAYMENT : "receives_payment"
~~~

### How to read the attributed diagram

- `CUSTOMER.customerId` identifies a Customer; **do not use name** as the key.
- `SALES_ORDER.orderId` identifies an Order, while `orderNumber` may serve as the document code.
- `ORDER_LINE.lineNo` is scoped **within one order**; it is not designed as a globally unique standalone number. An example identity is `(orderId,lineNo)`.
- `ORDER_LINE.agreedUnitPrice` and `lineDiscount` describe purchase terms; line total can be derived by formula.
- `PRODUCT.currentListPrice` describes the **current** catalog; it must not alter historical locked line prices.
- `PAYMENT.requestedAmount` is the amount requested for processing, **not** synonymous with collected cash across all statuses.

**Diagram note:** Mermaid requires type-like labels for attributes; here we have not yet set `PRIMARY KEY`, `FOREIGN KEY`, `VARCHAR(40)`, index types, or SQL constraints. Those belong to subsequent design stages.

## 11. Questions that force the model to change

Not every retail variation should be squeezed into a minimal ERD. Learners must know **when assumptions must change**.

### 11.1. The store allows guest checkout

New requirement: “Customers can buy without registering. An order still has a buyer and contact details at placement time.”

There are at least two approaches:

**Option A — Customer represents any buyer identity:** create a stable Customer/Buyer identity even for guests, with separate policies for contact info and permissions. The rule that each SalesOrder belongs to one Customer remains intact, though **the definition of Customer changes**.

**Option B — An Order may omit a registered Customer:** change the relationship to `REGISTERED_CUSTOMER` to **0..1**, while storing minimal guest transaction fields per policy:

~~~mermaid
erDiagram
    REGISTERED_CUSTOMER o|--o{ SALES_ORDER : "may_place"
    SALES_ORDER ||--|{ ORDER_LINE : "contains"
~~~

A guest order may have no RegisteredCustomer; a registered customer's order has at most one RegisteredCustomer. Buyer or recipient info must be modeled **explicitly per business requirements**, rather than treating `NULL customerId` as meaning the order has no buyer.

**Do not pick an approach merely because adding a nullable column is easy.** Ask how the system recognizes returning guests, handles guest order access, enforces PII/retention policies, and links orders if a guest later registers.

### 11.2. Draft orders or empty carts

If the same `SalesOrder` entity is created as soon as a cart opens, it may initially have **0 OrderLines**. The Order → OrderLine relationship must become **0..N** across the full lifecycle; the rule **“a CONFIRMED order has at least one line”** becomes a **state-dependent constraint**.

Another option is creating an independent `Cart` entity separate from `SalesOrder`; only upon valid checkout is an order created with at least one line. These two options differ in lifecycle, inventory sync, identity, and cart history needs.

**The 1..N diagram in the primary solution applies only to placed orders**, and does not assert every system must create an Order once a cart gets an item.

### 11.3. The same product can repeat in one order

An order has two lines for the same `productId=P220`, for instance:

~~~text
lineNo=1: P220, quantity=1, regular price
lineNo=2: P220, quantity=1, gift wrap or different promotion
~~~

If this is valid, `(orderId,productId)` **must not be chosen as the OrderLine identity**. `(orderId,lineNo)` or a stable `orderLineId` fits better. If the business requires merging identical products into one line, that rule must be documented and tested.

### 11.4. One bank transfer pays multiple orders

The primary solution assumes one `Payment` belongs to exactly one Order. Yet if a single bank transfer can pay `O9001` and `O9002` together, that relationship **no longer holds**.

We need an associative entity **PaymentAllocation**, meaning “a portion of a payment transaction allocated to one order.” Conceptual option:

~~~mermaid
erDiagram
    SALES_ORDER ||--o{ PAYMENT_ALLOCATION : "allocated_to"
    PAYMENT ||--o{ PAYMENT_ALLOCATION : "splits_into"
~~~

Now:

- A Payment may have **0..N PaymentAllocations** when newly received and awaiting reconciliation; or **1..N** if transactions are only recognized once linked to orders.
- A SalesOrder can receive allocations from multiple Payments.
- Each PaymentAllocation links **exactly one** Payment and **exactly one** SalesOrder.
- Must include **`allocatedAmount`, currency, status, and an invariant preventing over-allocation** per financial policy.

Never just draw `SALES_ORDER }o--o{ PAYMENT` and forget the amount of **each allocation**. PaymentAllocation is precisely where M:N relationship attributes belong.

### 11.5. Partial or multiple refunds

If a `CAPTURED` payment can be refunded across two transactions, do not simply flip Payment from `CAPTURED` to `REFUNDED` and lose track of original collected cash and individual refunds.

An extended model:

~~~mermaid
erDiagram
    SALES_ORDER ||--o{ PAYMENT : "has_payment"
    PAYMENT ||--o{ REFUND : "has_refund"
~~~

Assuming each Refund links to exactly one captured Payment, **one Payment can have 0..N Refunds**. Add `refundId`, refund amount, status, timestamp, provider reference, and an anti-over-refund rule. If the provider refunds at the order level or across payments, a different model is required.

**Never automatically add `Refund.requestedAmount` to total refunded** if refunds have not yet succeeded.

### 11.6. Multiple participants per order

The buyer, recipient, invoice party, and payer **are not necessarily the same Customer**. If the business needs to distinguish them, name roles `Buyer`, `Recipient`, `BillToParty`, `Payer` and decide whether they are relationship types or separate entities.

Do not use a single generic `customer_id` to stand in for all four roles by default. **The same label does not mean two concepts share the same identity or responsibility**.

### 11.7. Discontinued items or anonymized customers

Product `P220` may be discontinued next month, and Customer `C101` may request account closure. That **does not automatically allow deleting all related OrderLines and Payments**, since transactions may need retention for reconciliation/contractual obligations.

The conceptual model must describe **lifecycles**:

- Product can transition to `INACTIVE` while historical order lines still reference it.
- Finalized order lines may retain minimal/authoritative voucher snapshot data.
- Customer can be anonymized or have personal data separated per policy; never retain PII arbitrarily past lawful limits.
- Payment data often involves sensitive info. Data contracts should never blindly copy card numbers/tokens onto Order.

Retention and deletion details must be decided with data owners/legal; **an ERD does not solve data protection requirements on its own**.

## 12. Distinguishing conceptual, logical, and physical models

### 12.1. Conceptual level — *what we are doing in this exercise*

Answers **which objects exist, how they relate, and which rules hold**:

~~~text
Customer 1 — 0..N SalesOrder
SalesOrder 1 — 1..N OrderLine
Product 1 — 0..N OrderLine
SalesOrder 1 — 0..N Payment
~~~

No need to decide `BIGINT`/UUID, index specs, partitions, FK column names, storage placement, or PostgreSQL/MySQL/document DB.

### 12.2. Logical level — translating meaning into a keyed schema

If choosing a relational model, a **logical sketch** (not production SQL yet) might look like:

~~~text
Customer(
    customer_id [identifier],
    display_name,
    lifecycle_status
)

Product(
    product_id [identifier],
    product_name,
    current_list_price,
    catalog_status
)

SalesOrder(
    order_id [identifier],
    customer_id [references Customer],
    placed_at,
    currency,
    order_status
)

OrderLine(
    order_id [references SalesOrder],
    line_no,
    product_id [references Product],
    quantity,
    agreed_unit_price,
    line_discount
)

Payment(
    payment_id [identifier],
    order_id [references SalesOrder],
    provider_reference,
    amount,
    currency,
    status,
    requested_at
)
~~~

Differences:

- `OrderLine` has an example identity `(order_id,line_no)`.
- `SalesOrder.customer_id`, `OrderLine.product_id`, `Payment.order_id` are **logical links** corresponding to the ERD.
- Rules like **an Order must have at least one Line when CONFIRMED**, **no collection exceeding policy**, and **callback idempotency** may require transactions/application logic, not just FKs.
- `current_list_price` is a current catalog attribute, distinct from each line's `agreed_unit_price`.

### 12.3. Physical level — optimizing for a DBMS and workload

Only after the logical model is approved do you decide:

- Should `customer_id`, `order_id` use UUID, BIGINT, or namespaced IDs?
- Should monetary columns use `NUMERIC` or integer minor units? Currency and precision constraints?
- Which indexes support queries like “orders by customer” or “unreconciled payments”?
- Does `UNIQUE(provider, providerReference)` match the real transaction scope and lifecycle?
- How large will OrderLine/Payment row counts grow; is time-based partitioning needed?
- Are dedicated transactions, foreign keys, outbox, audit, retention, and encryption needed?

**Never let ORM quirks or DBMS features alter business cardinality.** Another technology might embed OrderLines in a document array, yet the fact “one order has multiple lines and one product can appear in multiple orders” must still be modeled accurately.

## 13. From conceptual model to runnable verification checks

**An ERD is a hypothesis about business structure.** To prove it fits, turn its relationships into valid/invalid input test cases and verify them at the appropriate application and database layers.

### 13.1. Decision table for a placed order

| Customer exists? | Line count | Every line has valid Product? | Outcome per exercise assumptions |
|---|---:|---|---|
| Yes | 1 | Yes | Accept, if other conditions pass |
| Yes | 3 | Yes | Accept |
| Yes | 0 | — | Reject **order confirmation** |
| No | 1 | Yes | Reject within non-guest scope |
| Yes | 1 | No | Reject or quarantine for source fix; never auto-assign a Product |

If the system supports draft orders, `line count = 0` may be allowed while `orderStatus='DRAFT'`, yet still blocked upon transitioning to `CONFIRMED` per chosen policy.

### 13.2. Payment decision table

| Order | Payment count | Scenario | Structurally valid? |
|---|---:|---|---|
| `O9002` | 0 | No payment attempted yet | Yes |
| `O9003` | 1 | One pending payment | Yes |
| `O9001` | 3 | One FAILED, two CAPTURED | Yes |
| `O9001` | 2 | Two Payments with different IDs from retried provider event | Likely **logical duplicate**, requires idempotency |
| No matching Order | 1 | Unassigned payment | Not valid as an accepted Payment in the minimal model |

**“Structurally valid” does not automatically mean “financially valid.”** For instance, a `CAPTURED` Payment with `amount=-100` violates the non-negative collection assumption; two Payments sharing a provider reference may be duplicate callbacks. Such rules must also be tested.

### 13.3. Pseudo-code checking a checkout operation

~~~text
confirmOrder(customerId, draftLines):
    assert customerId identifies an eligible Customer
    assert draftLines contains at least one line

    for each line:
        assert product exists and may be ordered
        assert quantity > 0
        assert agreedUnitPrice is accepted and currency is defined

    in one consistent operation / transaction:
        create SalesOrder with stable ID
        create its OrderLine records
        persist agreed prices and quantities
        record a valid order state transition

    return orderId
~~~

This is **business-rule pseudo-code**, not a distributed transaction design with inventory or payments. If stock reservation, promotion calculation, shipping, or tax is needed, those are additional steps/domains with their own invariants.

### 13.4. Illustrative SQL verifying grain and totals

Suppose the team implements the logical relational schema above and adds appropriate keys/physical types. The following SQL statements **illustrate post-implementation verification checks**, not commands required inside a conceptual ERD.

Check that no two rows share the same `(order_id,line_no)` identity:

~~~sql
SELECT order_id, line_no, COUNT(*) AS occurrences
FROM order_line
GROUP BY order_id, line_no
HAVING COUNT(*) > 1;
~~~

If `order_id` is only unique per tenant, both the query and the key must include `tenant_id`; never rely on `order_id` alone merely because test data has not collided yet.

Check for confirmed orders missing order lines:

~~~sql
SELECT o.order_id
FROM sales_order AS o
LEFT JOIN order_line AS l
  ON l.order_id = o.order_id
WHERE o.order_status = 'CONFIRMED'
GROUP BY o.order_id
HAVING COUNT(l.line_no) = 0;
~~~

This is a **post-hoc audit check**. The “no confirming empty orders” invariant is best enforced inside the state-transition workflow with proper transactions/constraints; **an FK from OrderLine to Order does not by itself force an Order to have at least one Line**.

Compute order-level subtotal and captured cash **in two separate aggregations**:

~~~sql
WITH line_subtotals AS (
    SELECT
        order_id,
        SUM(
            quantity * agreed_unit_price - line_discount
        ) AS merchandise_subtotal
    FROM order_line
    GROUP BY order_id
),
captured_payments AS (
    SELECT
        order_id,
        SUM(amount) AS captured_amount
    FROM payment
    WHERE payment_status = 'CAPTURED'
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(l.merchandise_subtotal, 0) AS merchandise_subtotal,
    COALESCE(p.captured_amount, 0) AS captured_amount
FROM sales_order AS o
LEFT JOIN line_subtotals AS l ON l.order_id = o.order_id
LEFT JOIN captured_payments AS p ON p.order_id = o.order_id;
~~~

**Why aggregate separately?** An order has 2 OrderLines and 3 Payments. A direct JOIN yields:

~~~text
SalesOrder
   JOIN OrderLine   → 2 rows
   JOIN Payment     → 2 × 3 = 6 rows
~~~

If you compute `SUM(lineAmount)` over 6 joined rows, each line amount repeats **3 times**; if you compute `SUM(paymentAmount)`, each payment repeats **2 times**. That is a **fanout** bug. Preserve grain and aggregate each source to the **order level** before joining the two measures.

In the example, `COALESCE` turning missing payments into 0 is used **intentionally** for the “total recorded collected cash” report; it does not mean every `NULL` in every business context should become 0.

### 13.5. Verifying amounts with an end-to-end test case

~~~text
Given:
    O9001 has lines: 2 × 120000 and 1 × 80000
    PAY-01: FAILED, 320000
    PAY-02: CAPTURED, 200000
    PAY-03: CAPTURED, 120000

When:
    compute order merchandise subtotal
    compute captured amount

Then:
    merchandise subtotal = 320000 VND
    captured amount = 320000 VND
    captured payment count = 2
    payment attempt count = 3
~~~

If a report returns `payment attempt count=2`, it dropped the failed attempt. If it returns `captured amount=640000`, it included failed attempts or multiplied rows via a JOIN.

## 14. APIs, events, and time: boundaries you should not overlook

The conceptual model can inform service contracts, yet **API responses and events do not have to mirror storage structure**.

### 14.1. API for viewing a current order

A customer-facing API might return a projection:

~~~json
{
  "orderId": "O9001",
  "status": "CONFIRMED",
  "currency": "VND",
  "lines": [
    {"lineNo": 1, "productCode": "P220", "quantity": 2, "agreedUnitPrice": "120000.00"},
    {"lineNo": 2, "productCode": "P310", "quantity": 1, "agreedUnitPrice": "80000.00"}
  ],
  "merchandiseSubtotal": "320000.00",
  "paymentSummary": {
    "capturedAmount": "320000.00"
  }
}
~~~

This contract need not expose full Provider details, FAILED attempts, or technical metadata if its goal is just a summary view. However, the **reconciliation team** may require a separate API showing detailed Payment history.

### 14.2. Events are not table snapshots

Example:

~~~json
{
  "eventId": "evt-001",
  "eventType": "order.confirmed",
  "occurredAt": "2026-11-20T09:00:00Z",
  "orderId": "O9001",
  "schemaVersion": 1
}
~~~

An event represents **the fact that an order was confirmed at a point in time**, not the entire current state of the order. Events have their own IDs for deduplication; one order can emit many events such as confirmed, cancelled, and delivered. When a real system allows “payment before confirmation,” lifecycle flows and constraints will differ from this exercise's assumptions.

### 14.3. Timestamps and history must have clear semantics

Distinguish:

- `placedAt`: when the order was placed.
- `agreedUnitPrice`: price applied at line-lock time.
- `payment.requestedAt`: when the payment attempt was created.
- `payment.capturedAt`: when the attempt was confirmed captured, if applicable.
- `ingestedAt`: when the pipeline received the data, if syncing to an analytical warehouse.

Never use `ingestedAt` as the sales date or collection date. If a Product changes name, price, or status after ordering, historical documents must retain their transaction-time meaning per agreed rules.

### 14.4. Data protection considerations

An ERD typically shows only relationships, while real implementation also requires:

- Authorization checks: customer `C101` can only view orders they are permitted to see; knowing `orderId` alone grants no access.
- Never embed sensitive card numbers/payment tokens into regular order tables.
- Separate current identity data from retained voucher records per policy.
- Define customer anonymization/deletion rules and retention for derived records.
- Idempotency when a provider sends callbacks with the same `providerReference` repeatedly; uniqueness scope may depend on provider/account and event type.

These are **related requirements** documented for handoff to logical modeling and integration design, not a reason to turn the conceptual ERD into an inventory of every API, index, or protocol.

## 15. An ERD review checklist for study teams

Before submitting, fill out a review table:

| Review question | Answer in primary solution |
|---|---|
| Business units being modeled? | Customer, product, placed order, order line, payment attempt |
| Total number of entity types? | **5 types** in the minimal diagram |
| Required associative entity? | **OrderLine** |
| How many Orders per Customer? | **0..N** |
| How many Customers per Order? | **1** under non-guest assumption |
| How many OrderLines per Order? | **1..N** when modeling placed orders only |
| How many Products per OrderLine? | **1** |
| How many OrderLines per Product? | **0..N** |
| How many Payments per Order? | **0..N** |
| How many Orders per Payment? | **1** |
| Where does the actual purchase price live? | **OrderLine.agreedUnitPrice** |
| Are FAILED attempts counted as collected cash? | **No** |
| Are merchandise totals and Payments summed after a direct JOIN? | **No**, aggregate by grain first |
| What needs further follow-up? | Guest/draft/variant/refund/allocation/currency/tax/retention |

A strong submission includes not only the diagram, but also **a one-page design decision sheet**:

~~~text
Model: Customer – Product – SalesOrder – OrderLine – Payment
Scope: confirmed/placed orders, identified customer, no refunds
Grain:
  SalesOrder = one placed order
  OrderLine = one item line within one placed order
  Payment = one distinct payment-processing attempt
Identity:
  Customer.customerId, Product.productId, SalesOrder.orderId
  OrderLine(orderId,lineNo), Payment.paymentId
Relationships:
  Customer 1 — 0..N SalesOrder
  SalesOrder 1 — 1..N OrderLine
  Product 1 — 0..N OrderLine
  SalesOrder 1 — 0..N Payment
History:
  agreedUnitPrice stays on OrderLine
Money:
  capturedAmount excludes FAILED/PENDING
Open questions:
  guest checkout, drafts, product variants, refunds,
  split/aggregated payments, currency, taxes, PII retention
~~~

**Evaluation rule:** If someone who was not in the discussion can read the scope, relationships, boundary conditions, and undecided assumptions from your document, the model is ready as a foundation for logical design.

## 16. Integrated practice problems with worked solutions

You should **sketch or answer on your own first**, then compare your **reasoning**—not just entity names—against the solutions.

### Exercise 1 — Identifying necessary entities

The prompt mentions customer, product, order, and payment. Each order contains multiple products, with quantities and purchase prices that can vary across orders. Can we design with just four entities? Name any additional entity and explain.

**Solution:** We need **OrderLine** to represent **one purchase line within an order** and store `quantity`, `agreedUnitPrice`, and `lineDiscount`. Order ↔ Product is M:N; OrderLine turns each side into a 1:N relationship with a place to attach purchase-specific attributes. Four entities would only suffice if there were no need to manage lines/purchase terms, which contradicts the prompt.

### Exercise 2 — Reading Crow's Foot in both directions

Given `CUSTOMER ||--o{ SALES_ORDER`. How many orders can a customer have? How many customers can an order have?

**Solution:** One Customer can have **0..N SalesOrders**; each SalesOrder belongs to **exactly 1 Customer**. Do not infer backwards that an Order has multiple Customers just because one end has a crow's foot.

### Exercise 3 — Testing optionality with a customer who has not purchased

Customer `C103` just registered and has no orders yet. Is `CUSTOMER ||--|{ SALES_ORDER` appropriate?

**Solution:** **No**, because `|{` on the SalesOrder side forces every Customer to have **at least one order**. Within exercise scope, customers exist independently of orders; fix to `CUSTOMER ||--o{ SALES_ORDER`.

### Exercise 4 — Choosing OrderLine grain and identity

`O9001` has two lines for the same `P220`: one at regular price, one with gift wrapping. A team proposes `(orderId,productId)` as the OrderLine key. Is that sufficient?

**Solution:** **No**, if two lines for the same product are permitted. `(orderId,productId)` treats them as one, losing the promotion/gift-wrap distinction. Use `(orderId,lineNo)` or a stable `orderLineId` and keep each line's reference to Product. If the business mandates merging identical products into one line, document that constraint explicitly.

### Exercise 5 — Product price changes after ordering

An bought two P220 notebooks at 120,000 each yesterday. Today the Product is updated to `currentListPrice=150,000`. What is the old order's subtotal assuming no discounts or fees?

**Solution:** \(2\times120.000=240.000\) VND. Locked transaction prices live on `OrderLine.agreedUnitPrice`, not looked up from `Product.currentListPrice` to alter history.

### Exercise 6 — Can an unsold product exist?

Product P450 was just added to the catalog and no one has ordered it yet. What happens if we draw `PRODUCT ||--|{ ORDER_LINE`?

**Solution:** The diagram forces every Product to have **at least one OrderLine**, contradicting the scenario. It must be `PRODUCT ||--o{ ORDER_LINE`: a product can appear in **0..N** lines, while each OrderLine still needs exactly one Product.

### Exercise 7 — A placed order with 0 lines

The system creates an Order in status `CONFIRMED` with no OrderLines. Is this valid under the primary assumptions? If drafts are allowed, what must change?

**Solution:** Invalid for **placed orders** within exercise scope. If Orders can be drafts, the full lifecycle allows **0..N** lines, and the `DRAFT → CONFIRMED` transition rule must enforce **at least one line**. Alternatively, separate `Cart` from `SalesOrder` to preserve placed-order semantics.

### Exercise 8 — An order with no payment attempts yet

`O9002` has one P220 line and has not called a payment provider yet. Is a 1:1 Order–Payment relationship suitable?

**Solution:** No. An order can have **0 Payments**; the minimal relationship is `SALES_ORDER ||--o{ PAYMENT` under the rule “each Payment belongs to one Order.” Never fabricate a dummy 0-VND Payment just to satisfy a relationship.

### Exercise 9 — Failed attempt followed by successful payments

An order has `PAY-01 FAILED 320000`, `PAY-02 CAPTURED 200000`, `PAY-03 CAPTURED 120000`. How many payment attempts exist? How much is considered successfully collected?

**Solution:** There are **3 attempts/transactions**, of which **2 are CAPTURED**. Successfully collected cash is \(200.000+120.000=320.000\) VND. `FAILED` does not count toward collected cash. If the provider also has `AUTHORIZED` before capture, define that separately too.

### Exercise 10 — Fanout when summing amounts

Order `O9001` has 2 OrderLines and 3 Payments. How many rows does a direct JOIN between OrderLine and Payment on `orderId` produce? Why would `SUM(OrderLine.amount)` be wrong?

**Solution:** It produces **6 rows**, repeating each OrderLine 3 times. Summing over the joined result multiplies the 320,000 subtotal into **960,000**. Aggregate subtotal at the line grain to **one row per Order**, aggregate captured payments separately at the Payment grain to **one row per Order**, and then JOIN.

### Exercise 11 — Order numbers unique only within a store

Store A and Store B both issue `orderNumber=000123`. How do you avoid confusing the two orders?

**Solution:** Use an `orderId` guaranteed unique in the appropriate scope, or a composite identity like `(storeId,orderNumber)`/`(tenantId,orderNumber)` if that matches actual numbering rules. The field name `orderNumber` alone never proves global uniqueness.

### Exercise 12 — Guest checkout

The system lets users buy without creating an account. Each order must still know a buyer and how to send confirmation. Can we simply delete the Order–Customer relationship in the ERD?

**Solution:** Do not arbitrarily delete the relationship and lose buyer semantics. Two valid approaches: (1) define Customer/Buyer identity to include guests; (2) give Order a **0..1 RegisteredCustomer** link and store buyer details at placement time per policy. Confirm guest order access, contact rules, linking when a guest later registers, and PII retention.

### Exercise 13 — One Payment paying multiple orders

A customer makes one bank transfer of 470,000 VND to pay orders O9001 (320,000) and O9002 (150,000). Does “one Payment belongs to exactly one Order” still hold? Fix the model.

**Solution:** **No** longer true if the bank transfer is modeled as a single Payment. Add **PaymentAllocation** at the grain **one allocation from a Payment to an Order**; two rows allocate 320,000 and 150,000, summing to 470,000 if policy requires full allocation. Enforce payment status, currency, and anti-over-allocation checks.

### Exercise 14 — Two-part refund

Payment `PAY-02` captured 200,000, then refunded 50,000 and 30,000 in two separate transactions. Should we overwrite `PAY-02.amount=120000` to represent the net balance?

**Solution:** No, if independent capture/refund history is needed. Keep **Payment CAPTURED=200,000** intact and add **Refund** for the two successful refunds, each with its own identity and status. Total refunded is 80,000; **net captured on that transaction** is 120,000 by formula, without erasing the original 200,000 collection.

### Exercise 15 — Different customer roles

A buyer sends a gift to a friend, the invoice goes to a company, and payment is made using someone else's card. Can a single `customerId` default to all four roles?

**Solution:** No. `buyer`, `recipient`, `billToParty`, and `payer` are **distinct roles**; depending on the case they may be the same or different parties. Clarify permissions/responsibilities for each role and add explicit relationships/identifiers instead of overloading one ambiguous column.

### Exercise 16 — Translating conceptual to logical

Why does the conceptual diagram write `SalesOrder 1 — 0..N Payment` without specifying `payment.order_id BIGINT`?

**Solution:** The conceptual model focuses on **meaning and cardinality**. `payment.order_id` is a **logical** representation of that link in a relational schema; choosing `BIGINT`, UUID, FK index, and storage engine are **physical** decisions. Those choices must serve—not alter—confirmed business rules.

### Exercise 17 — Verifying duplicate payment callbacks

The provider sends the `CAPTURED` callback for the same transaction three times. The system saved three Payments with different IDs and tripled the collected total. Where is the bug?

**Solution:** There is an **idempotency / event-or-transaction identity** bug in integration. Identify the provider transaction reference and its uniqueness scope, distinguish three deliveries from **one logical transaction**, and handle retries safely. Having a Payment entity in the ERD **does not automatically stop** duplicate callbacks; business testing must cover it.

### Exercise 18 — Different storage models must still preserve the same facts

A team plans to store Orders in a document DB, embedding `lines[]` and `payments[]` in each document. They conclude “since it's a document DB, we don't need OrderLine.” Are they right?

**Solution:** Incorrect **semantically**. You may not need a separate physical collection for OrderLine if embedded inside the Order document, yet each element of `lines[]` still represents **an order line** with identity, price, quantity, and Product link. The conceptual model must still capture that fact; physical representation is a separate choice.

## 17. Pre-submission self-assessment checklist

- [ ] Clearly stated **scope**: placed orders, identified customers, Payment as an attempt, excluding refunds.
- [ ] Identified the **5 entities** in the primary solution: Customer, Product, SalesOrder, OrderLine, Payment.
- [ ] Defined the **grain** of SalesOrder, OrderLine, and Payment.
- [ ] Separated **Customer ID** from name/email and **Order ID** from display order number.
- [ ] Modeled Customer → Order **0..N**, Order → Customer **1**.
- [ ] Modeled Order → OrderLine **1..N** for placed orders only.
- [ ] Modeled Product → OrderLine **0..N**, OrderLine → Product **1**.
- [ ] Modeled Order → Payment **0..N**, Payment → Order **1** within scope.
- [ ] Placed **quantity** and **agreedUnitPrice** on OrderLine, not solely on Product.
- [ ] Distinguished **current catalog price** from **transaction price at placement**.
- [ ] Specified that `FAILED`/`PENDING` Payments do not generate collected cash.
- [ ] Distinguished merchandise subtotal, payable amount, captured cash, and refunds.
- [ ] Tested customer with zero orders, unsold product, unpaid order, and failed payment.
- [ ] Tested one Product across multiple orders at different prices, and repeated Product lines if permitted.
- [ ] Verified no double-counting when joining two 1:N sets (OrderLine and Payment).
- [ ] Defined ID namespaces by tenant/store and handling of duplicate callbacks.
- [ ] Recorded **open questions** on guest checkout, drafts, SKU/variants, taxes, refunds, and batch payments.
- [ ] Identified cases needing **PaymentAllocation**, Refund, or role-specific relationships.
- [ ] Identified data ownership for customer/product/order/payment and what must be retained over time.
- [ ] Separated the **conceptual diagram** from logical schema, FKs, indexes, and DBMS choice.
- [ ] Defined **acceptance tests** and counterexample scenarios for key cardinalities.

## 18. Summary: from four nouns to a verifiable model

From the requirement “customers, products, orders, and payments,” we do not stop at drawing four boxes. To capture a purchase line with locked quantity and price, we must add **OrderLine**:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ SALES_ORDER : "places"
    SALES_ORDER ||--|{ ORDER_LINE : "contains"
    PRODUCT ||--o{ ORDER_LINE : "appears_in"
    SALES_ORDER ||--o{ PAYMENT : "has"
~~~

This diagram holds **within the declared scope**: placed orders have at least one line, each order belongs to an identified customer, each Payment is one processing attempt belonging to one order, and an order may have zero or multiple payment attempts.

**Five key takeaways:**

1. **Entities must reflect business facts**, not just match nouns in the prompt. OrderLine has distinct meaning because it holds the price and quantity of a specific purchase.
2. **Cardinalities must be read in both directions and tested with counterexamples.** Unpurchased customers, unsold products, and unpaid orders are normal cases.
3. **Order status and timestamp differ from payment status and timestamp.** A placed order is not automatically fully paid; a failed attempt is not collected cash.
4. **Transaction history must preserve finalized meaning.** A Product changing price or becoming inactive must never silently alter historical orders.
5. **No single ERD fits every variation.** Guest checkout, drafts, multi-order payments, refunds, and multiple buyer roles will change or extend the model.

**Remember:** A **good conceptual model** is not judged solely by neat lines and notation. It enables domain stakeholders to answer precisely: **“what does one record represent, how many other objects can each object link to, and which rules must always hold?”** Once assumptions, grains, relationships, and verification checks are clear, moving to relational, document, graph, or analytical implementations rests on solid, evolvable ground.
