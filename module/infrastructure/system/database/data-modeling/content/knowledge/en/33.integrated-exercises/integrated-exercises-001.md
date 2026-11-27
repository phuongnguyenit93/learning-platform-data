# Sales Process Discovery and Building a Business Glossary

This lesson belongs to the **Integrated Exercises** chapter, connecting requirements discovery skills with data modeling and data verification.

## 1. Integrated exercise: start from the business domain, not from tables

In the **DATABASE_DATA_MODELING** module, the goal is to turn business requirements into a data model that can be explained, evolved, and verified: entities, relationships, constraints, normalization, keys, indexes, and physical schemas; while also comparing relational, document, graph, and analytical models. To execute those steps correctly, the designer must understand **the process that creates and uses data** before drawing an ERD or writing SQL.

The topic of this lesson is **sales process discovery and building a business glossary**. This is an input exercise for subsequent modeling steps, not an exercise that asks you to immediately implement a complete schema.

A seemingly simple statement such as:

> “Each order has one payment, and revenue is calculated based on delivered orders.”

may contain three unverified assumptions:

- Does an order truly have only one payment, or can it be paid in multiple installments?
- Does “delivered order” mean all shipment parcels were delivered, or only part of them?
- Is “revenue” the placed order value, captured cash, value of delivered goods, or net amount after returns?

If you turn those three statements into attributes and relationships before conducting discovery, the data model may be **syntactically valid but semantically wrong for the business**. A good business glossary clarifies the meaning and scope of each term before choosing keys, relationship cardinalities, and formulas.

### Learning outcomes

After this lesson, learners can:

1. Define the discovery scope and the data decisions that need to be finalized.
2. Build a list of stakeholders, roles, and interview questions for each sales step.
3. Map the **as-is** process, distinguishing actual current operations from the desired **to-be** process.
4. Capture main flows, exceptions, statuses, actors, timestamps, and data sources.
5. Build a business glossary with **definitions, applicability boundaries, examples, counterexamples, owners, and evidence sources**.
6. Distinguish easily confused terms: product/SKU, order/shipment, payment/capture, return/refund, sales volume/revenue, on-hand/available quantity.
7. Translate discovery findings into a list of **candidate entities, grains, keys, relationships, and business invariants** without locking in physical details too early.
8. Verify concepts using concrete scenarios, source reconciliation, and review sessions.

## 2. Hypothetical context: an omnichannel retail store

This exercise uses a hypothetical company named **An Nhiên Retail**. This is a fictional scenario created to practice discovery and does not represent the processes of any real business.

The company sells household care products across three channels:

- **In-store POS:** staff can create direct sales transactions; customers do not necessarily have an account.
- **Website:** customers add items to a cart, confirm an order, and choose payment and delivery options.
- **Partner marketplace:** partners push orders into the system via API or sync files; partner order codes have their own identifier namespace.

Participating departments:

| Department | Actual work | Critical data |
|---|---|---|
| Sales/POS | Intake and confirm purchase demand | Cart, transaction, line items, channel |
| Customer Support (CSKH) | Change address, cancel orders, receive return requests | Order status, request, reason |
| Warehouse | Reserve stock, pick, pack, dispatch | Physical stock, reservations, dispatch notes |
| Delivery | Hand over, deliver each parcel, return undelivered parcels | Parcels, waybills, delivery attempts, outcomes |
| Payments | Receive/reconcile payments | Authorization, capture, transaction, refund |
| Accounting | Record invoices and financial entries | Vouchers, amounts, tax, period |
| Marketing | Track sales and promotions | Campaigns, promo codes, segments |
| Data/BI | Build reports, standardize KPI definitions | Grain, fact, dimension, timestamps |
| Security/Privacy | Audit how customer data is used | PII catalog, permissions, retention |

**Sample constraints:** an order can be shipped in multiple parcels, paid in multiple installments, partially returned, and refunded across multiple transactions. Source order codes can collide across channels. Learners must verify these assumptions as if working on a real project.

### 2.1. What role does the learner play?

The learner acts as a **data analyst/data architect** collaborating with a product owner. The job is not merely asking “what columns do we need?”, but discovering:

- What **work** are users actually doing?
- When is data **created, updated, finalized, cancelled, or archived as history**?
- Does one term carry different meanings across different departments?
- Which record is the **authoritative source**?
- Which conditions must hold true in all cases?
- What must be retained to explain a historical report or past transaction?

## 3. Inputs, outputs, and acceptance criteria

Hypothetical inputs:

1. Scenario description of An Nhiên Retail in this lesson.
2. Simulated interview transcripts or discovery notes from each role.
3. Sample orders, payments, shipments, and returns provided in later sections.
4. Unverified assumptions; these must be labeled instead of being treated as fact.

Deliverables to complete:

| Code | Deliverable | Question it answers |
|---|---|---|
| D01 | **Scope & discovery brief** | What decisions is discovery locking down; what is the scope? |
| D02 | **Stakeholder map** | Who understands and has authority to confirm each area? |
| D03 | **As-is process** | How does selling actually happen in practice? |
| D04 | **Exception & lifecycle matrix** | What happens on failure, cancellation, split shipment, or return? |
| D05 | **Business glossary** | What does each term mean, and what does it include/exclude? |
| D06 | **Data source/ownership inventory** | Where does data originate, where is it managed, and where is it used? |
| D07 | **Business rule catalog** | Which invariants must be protected? |
| D08 | **Open questions & decision log** | What is still debated, who decides, and with what evidence? |
| D09 | **Candidate model handoff** | Which entities, grains, keys, and relationships need further analysis? |
| D10 | **Review & evidence record** | Who reviewed it and have edge cases been covered? |

**There is no need yet to write full DDL, pick all indexes, or design partitions.** Physical decisions only make sense after understanding grain, data sources, and workload. You may include example keys/SQL to test hypotheses, but you must clearly label them as **candidates**.

### 3.1. Definition of done

The exercise is considered complete when another reader reviewing D01–D10 can:

- Distinguish “order placed”, “goods delivered”, “cash captured”, and “goods returned”.
- Explain **one** end-to-end transaction example from start to finish.
- Know which identifiers trace records across systems and which are only display labels.
- Know which parts are approved and which remain hypotheses.
- Point out which data will produce **multiple rows** when an order has multiple shipments or payments.
- Avoid producing a revenue formula that conflicts across reports without explicitly documenting the differences.

## 4. Scoping discovery and defining decision questions

Do not try to survey “the entire retail workflow” in a single workshop. Write a concise scope brief.

~~~text
Problem statement:
  Omnichannel sales data discovery and terminology alignment.

Start point:
  A customer or staff member creates a purchase request that may become an order.

End point:
  The order is completed/cancelled; returns and refunds may occur.

In scope:
  Cart/order/order lines; order-level promotions; payment allocations;
  inventory reservations; dispatch; shipment parcels; returns; refunds;
  channel/source identities; status milestones.

Out of scope for the initial discovery round:
  General ledger accounting, inventory valuation, demand forecasting,
  supplier management, multi-country tax strategies.

Decisions to lock down:
  Order/line identity; payment/shipment event grain;
  statuses and timestamps; metric definitions; business glossary.
~~~

Marking an item “out of scope” does not mean it does not exist. For instance, **taxes and invoices** may be critical dependencies for revenue; you must record who owns them and when follow-up discovery is needed.

### 4.1. As-is and to-be are two different sources of truth

- **As-is:** what staff and systems are actually doing today, including manual handling or workarounds.
- **To-be:** the process the business wants to adopt after improvements.
- **Policy:** published rules, which may differ from operational reality.
- **System behavior:** what APIs/schemas currently support, which may differ from both as-is and policy.

Never draw the to-be flow and label it as-is. A “delivery completed” field might currently be updated manually even though policy documents describe automatic updates from the carrier.

### 4.2. Defining domain boundaries

Example:

~~~mermaid
flowchart LR
    C["Customer / Staff"] --> SALES["Sales: orders"]
    SALES --> PAY["Payments: collection"]
    SALES --> WH["Warehouse: dispatch"]
    WH --> SHIP["Delivery: parcel delivery"]
    SHIP --> SERVICE["CSKH: returns"]
    PAY --> SERVICE
    SALES --> BI["Analytics: reporting"]
    PAY --> BI
    SHIP --> BI
~~~

This is a **context** diagram; it does not prove there are foreign keys across databases. Cross-service relationships may be maintained via business IDs, APIs, events, or reconciliation; this must be investigated separately.

## 5. Mapping stakeholders before interviewing

Someone who knows an activity happens does not necessarily have the authority to decide KPI definitions or financial rules.

| Role | Information to gather | Expected sign-off authority |
|---|---|---|
| Sales owner | Meaning of order, statuses, and changes/cancellations | Sales process |
| POS staff | Actual steps, exceptions, and error corrections | Counter operational evidence |
| Website product owner | Checkout, cart, displayed prices | Approved web behavior |
| Warehouse | Reservation, packing, split parcels | Goods movement and quantities |
| Payment specialist | Authorization, capture, refund, retry | Payment transaction semantics |
| Accounting | Vouchers, recognition timing, reconciliation | Authoritative financial metrics |
| CSKH | Refunds, exchanges, cancellations, exception handling | Customer request handling rules |
| BI analyst | Currently computed KPIs and report discrepancies | Metric definitions submitted for approval |
| Backend/data engineer | Source of truth, IDs, events, schema | Current system behavior |
| Privacy/security | PII, retention, access permissions | Compliant protection policies |

### 5.1. Lightweight RACI for documentation

In each artifact, you can record:

~~~text
R – Responsible: person drafting, consolidating, and updating the document.
A – Accountable: person approving the business content.
C – Consulted: domain roles consulted for expertise.
I – Informed: groups notified when changes occur.
~~~

For example, the definition of **Captured Payment Amount** may involve consulting both the payment specialist and accounting, but a single final owner must be agreed upon. Avoid leaving three teams with three calculation methods and no designated authority.

### 5.2. Conflicts are signals for discovery

When Sales says “a successful order means delivered”, Payment says “success means money captured”, and BI says “success means not cancelled”, **do not arbitrarily pick one definition**. Record all three distinct concepts, collect illustrative examples, and hold a terminology sign-off session.

## 6. Pre-discovery preparation: questions, evidence, assumptions

Before interviews, prepare:

- Objectives and decisions to finalize.
- Existing workflow documentation, if officially provided.
- List of source systems and related reports.
- Several representative simulated transactions.
- List of **unproven assumptions**.
- Rules for taking notes, assigning owners, and confirming findings post-interview.

### 6.1. Labeling certainty levels

| Label | Meaning | How to handle |
|---|---|---|
| **CONFIRMED** | Confirmed by the owner with supporting basis | Can be used as a design requirement |
| **OBSERVED** | Seen in data/logs/operations | Must verify whether it represents a general rule |
| **HYPOTHESIS** | Hypothesis proposed by the designer | Follow up; do not treat as an invariant |
| **DISPUTED** | Two parties give different definitions | Assign an owner to resolve |
| **OPEN** | No answer yet | Record due date and impact |
| **OUT_OF_SCOPE** | Not part of this round | Record dependencies if significant |

For example, the statement “each order has only one payment” if seen in only two samples is merely **OBSERVED**; it must not be promoted to **CONFIRMED** without asking about multiple payments, failures, and partial captures.

### 6.2. Preparing negative examples

Include questions such as:

- What happens if payment fails after stock is reserved?
- What if a SKU is temporarily out of stock in warehouse A but available in warehouse B?
- What if an order is cancelled after one parcel has already been handed over to the carrier?
- What if a customer returns a partial quantity of an order line?
- What if a marketplace API sends the same order code twice?
- What if an order is created at 23:55 but synced after 00:00?
- What if goods are delivered but the customer's COD payment is not yet reconciled?

Negative cases usually reveal grains, statuses, and timestamps that the “happy path” hides.

## 7. Interview question bank by process step

Do not ask generic questions like “What tables are in the system?”. Ask participants to **walk through a real or anonymized transaction**.

### 7.1. Sales/POS/website

1. What condition creates an **order**, and what condition only creates a **cart**?
2. Is the order ID assigned at draft time or upon confirmation?
3. Does POS accept walk-in guest customers?
4. At what exact moment are prices and promotions locked?
5. Can quantity, address, or fulfillment channel be edited after confirmation?
6. Can orders be split or merged? Which source record retains the relationship?
7. Can an order contain the same SKU multiple times with different promotions?
8. Are there pre-orders, deposits, or backorders without available stock?

### 7.2. Warehouse/delivery

1. How does “stock reservation” differ from “warehouse dispatch”?
2. Which source calculates available quantity?
3. Can one order line be split across multiple warehouses or parcels?
4. Can one parcel contain items from multiple orders?
5. Are multiple delivery attempts supported? Who confirms “delivered”?
6. When delivery fails, what state are the goods in and when do they return to available stock?
7. When goods are returned, do they re-enter sellable inventory immediately?

### 7.3. Payments/accounting

1. What is the difference between **authorization**, **capture**, **settlement**, and **refund**?
2. Are failed payment attempts still stored?
3. Can one order be paid using two different payment methods?
4. Can one payment cover multiple orders, or can one order be funded by multiple payments?
5. Does COD upon delivery mean the same thing as a payment gateway capture?
6. Can refunds happen multiple times, and can they be partial?
7. Does revenue reporting use order date, capture date, fulfillment date, or posting date?
8. How are taxes, shipping fees, discounts, and returns calculated?

### 7.4. CSKH and BI

1. How do you distinguish pre-delivery cancellation, post-delivery return, and exchange?
2. Is return status tracked at the **request**, **line**, or **parcel** level?
3. If a customer returns items but hasn't been refunded yet, how do reports reflect it?
4. Which status does the “successful orders” dashboard currently filter on?
5. Is yesterday's report restated when a refund arrives late?
6. Are there shadow data tables outside the main flow, such as Excel sheets or paper slips?
7. Which roles have permission to view contact information and purchase history?
8. Which reconciliation checks detect duplicate, missing, or late-arriving data?

## 8. Running the interview: moving from behavior to data

A 45–60 minute practical framework could look like:

| Phase | Guiding question | Output |
|---|---|---|
| Opening | “What are we locking down today?” | Scope and objectives |
| Storytelling | “Let's walk through a concrete order from start to finish.” | Business timeline |
| Exception probing | “Has the opposite case ever happened?” | Branching flows |
| Source tracing | “Who enters this status? In which system?” | Ownership/data flow |
| Term definition | “When you say payment, do you mean attempt, capture, or settled cash?” | Glossary |
| Rule checking | “What must never be allowed to happen?” | Invariants |
| Wrap-up | “What is confirmed; what still needs follow-up?” | Decisions/open issues |

### 8.1. Speculation-free interview notes template

~~~text
OBS-001
Source: Interview with payment specialist; 2026-11-22.
Statement: "An order can have multiple payment attempts."
Evidence: Demo transaction T-01 (PII removed).
Tentative interpretation: PaymentAttempt has its own grain.
Status: OBSERVED.
Open question: Can an order have multiple successful CAPTURES?
Verification owner: Payment lead.
~~~

Separate **user quotes**, **analyst interpretations**, and **approved decisions**. Otherwise, a hypothesis gets quoted as fact in downstream documents.

### 8.2. Do not record unnecessary personal data

During real discovery, sample orders must be anonymized/tokenized. Never copy passwords, payment gateway tokens, card numbers, detailed delivery addresses, or unnecessary customer data into the business glossary or meeting notes. Model documentation may include sensitivity classifications and links to secure systems without storing actual values.

## 9. Mapping the as-is process around data creation points

A hypothetical main flow diagram:

~~~mermaid
flowchart TD
    A["Customer selects items / POS records demand"] --> B["Cart or purchase request"]
    B --> C{"Confirm order?"}
    C -->|No| D["Cart saved or abandoned"]
    C -->|Yes| E["Create order and order lines"]
    E --> F["Check promotions, pricing, stock source"]
    F --> G{"Can fulfill?"}
    G -->|No| H["Wait for stock / cancel per policy"]
    G -->|Yes| I["Reserve stock / prepare fulfillment"]
    I --> J["Authorize or capture per method"]
    J --> K{"Payment valid?"}
    K -->|No| L["Await retry / cancel / release reservation"]
    K -->|Yes| M["Pick, pack, create parcels"]
    M --> N["Deliver / counter pickup"]
    N --> O{"Return requested?"}
    O -->|Yes| P["Return request → receive goods → inspect"]
    P --> Q["Decide and execute refund"]
    O -->|No| R["End business lifecycle"]
    Q --> R
~~~

The diagram **illustrates a common sequence**, not a rule that “every order must be paid before delivery”: COD, deposits, post-pay, and POS may follow different orders. During discovery, create separate lanes/branches per method.

### 9.1. Attaching data events to steps

| Step | Possible recorded event or change | Do not equate with |
|---|---|---|
| Customer adds item | CartItemAdded | OrderLineCreated |
| Customer places order | OrderPlaced | PaymentCaptured |
| Stock reserved | StockReserved | StockDispatched |
| Parcel created | ShipmentPacked | ShipmentDelivered |
| Payment accepted | PaymentAuthorized | PaymentCaptured |
| Cash collected | PaymentCaptured | ProviderSettled |
| Parcel delivered | DeliveryConfirmed | OrderFullyFulfilled |
| Customer requests return | ReturnRequested | ItemReceived |
| Warehouse receives return | ReturnItemReceived | RefundCompleted |
| Refund completes | RefundSucceeded | ReturnApproved |

These event names are **modeling candidates**. You must ask whether the source system actually emits such events or simply overwrites current state. Never treat illustrative event names as existing contracts.

## 10. Capturing two detailed process branches: web and POS

Two channels selling the same products may have different finalization points.

### 10.1. Hypothetical website flow

~~~text
Cart
 -> CheckoutStarted
 -> OrderPlaced
 -> InventoryReserved
 -> PaymentAuthorized/Captured (depends on method)
 -> Shipment(s)
 -> DeliveryConfirmed
 -> OrderCompleted
~~~

Questions:

- Do the cart and the order share the same ID?
- Are prices locked at CheckoutStarted or OrderPlaced?
- Can an order exist if inventory reservation fails?
- If payment times out but actually gets captured, how does the system reconcile?
- If a shipment delivers partially, what does the order status show?

### 10.2. Hypothetical POS flow

~~~text
POS transaction started
 -> Scan item lines
 -> Apply discount
 -> Collect payment / record COD if policy permits
 -> Issue receipt
 -> Release goods at counter
 -> Transaction finalized
~~~

Questions:

- Is a POS transaction the same SalesOrder type as a website order?
- If a customer returns an item without an account, what identity is used to look up the transaction?
- Is the receipt printed before or after capture?
- Does offline POS issue a local ID? Is a namespace needed when syncing?
- Does scanning the same SKU twice create two lines or increment the quantity of one line?

### 10.3. Separating what “has happened” from what “is permitted”

For instance, observed data shows POS created transactions without a registered customer. This proves **guest sales occur in practice**, but does not prove every product type and payment method allows guest sales. Rules must be confirmed by channel, order type, and lifecycle stage.
## 11. End-to-end scenario to stress-test terminology

The discovery team receives an illustrative scenario from the retail system. All amounts are assumed to be in **VND**, excluding taxes and third-party payment fees so the exercise focuses on data structure.

~~~text
Order: WEB-O145
Tenant: RETAIL-VN
Channel: WEB
Customer: C501

Line L1: SKU-A × 2, unit price 120,000
Line L2: SKU-B × 1, unit price  80,000

Gross merchandise before discount:    320,000
Discount on L1: 10,000 × 2 =          -20,000
Merchandise value after discount:     300,000
Shipping fee:                          30,000
Customer payable for order:           330,000
~~~

The system records:

~~~text
Payment P1: captured 200,000
Payment P2: captured 130,000
Total captured:      330,000

Shipment S1: SKU-A × 1, SKU-B × 1
Shipment S2: SKU-A × 1

Return R1:  SKU-A × 1 (from a specific shipment)
Refund F1:  110,000 (120,000 - 10,000 allocated discount)

Assume shipping fee is non-refundable.
After refund, captured minus refund: 220,000
~~~

This is **one** order, **two** order lines, **two** payment captures, **two** shipments, **one** return request/line, and **one** refund. If the Order table is designed with single-valued `payment_id`, `shipment_id`, and `refund_id` columns, the model will lose data or overwrite prior records.

### 11.1. Arithmetic verification formulas

| Value | Calculation | Result |
|---|---|---:|
| Gross merchandise | 2 × 120,000 + 1 × 80,000 | 320,000 |
| Item discount | 2 × 10,000 | 20,000 |
| Net merchandise before returns | 320,000 − 20,000 | 300,000 |
| Order payable | 300,000 + 30,000 | 330,000 |
| Captured amount | 200,000 + 130,000 | 330,000 |
| Return-adjusted merchandise | 300,000 − 110,000 | 190,000 |
| Net captured after refund | 330,000 − 110,000 | 220,000 |

The **220,000** on the last row is not automatically **accounting revenue**: it is **captured minus refunded** in this example scenario, which includes the 30,000 shipping fee and ignores taxes, recognition timing, or accounting policies.

### 11.2. Different types of quantities

- **Ordered quantity** of SKU-A: 2.
- **Shipped quantity** of SKU-A: 2 across S1 and S2.
- **Returned quantity** of SKU-A: 1.
- **Retained quantity** of SKU-A after return: 1, assuming no loss/exchange and both shipments were actually delivered.

Do not place a single **quantity** column on the Order table and reuse it for every query. Quantity must be tied to a **grain** and an activity type.

## 12. Payment discovery: attempt, authorization, capture, and refund

The word “payment” can refer to different objects:

| Term | Grain | Business milestone | Questions to ask |
|---|---|---|---|
| **Payment intent** | One intent to pay an amount | Customer chooses payment method | How many intents can one order have? |
| **Payment attempt** | One try with gateway/method | Request sent to provider | Does a retry share the same attempt ID? |
| **Authorization** | An amount approved/held | Provider responds | Can it expire or be voided? |
| **Capture** | One collection recorded by provider | Captured/succeeded | Are partial/multiple captures allowed? |
| **Settlement** | One reconciliation/payout per provider rules | Settlement date | Does it differ from capture date? |
| **Refund request** | One request to refund | CSKH/customer requests | Can it be rejected? |
| **Refund transaction** | One execution of returning funds | Provider executes | Can one request create multiple refunds? |

Decision question: “Can one Payment have multiple transactions?” If yes, **Payment** may be an aggregate containing attempts/captures/refunds; each transaction needs **its own ID and timestamp**.

### 12.1. Failure followed by retry

~~~text
Attempt A1: timeout, status unknown
Attempt A2: succeeded, captured 130,000
Late callback for A1: provider reports captured 130,000
~~~

If the system does not cross-check transaction IDs and idempotency, it may charge twice. The glossary must clearly define **successful capture**, **unresolved attempt**, **duplicate callback**, and the reconciliation procedure. Never rely on `paid=true` as the sole evidence.

### 12.2. Probing when the business says “paid”

Ask:

- Has it been **authorized** or **captured**?
- Has money entered the bank account, or did the provider only confirm capture?
- Was there a reversal/refund?
- Does “paid” apply to the whole order or just one installment?
- For COD, what information proves the cash was received?
- Which timestamp is used for reconciliation?

When answers differ across departments, do not collapse them into a single status with unclear semantics.

## 13. Delivery and return discovery: lines, parcels, attempts

An order with two shipments in the example is an opportunity to uncover **many-to-many relationships**:

~~~mermaid
erDiagram
    SALES_ORDER ||--|{ ORDER_LINE : "contains"
    SALES_ORDER ||--o{ SHIPMENT : "fulfilled via"
    SHIPMENT ||--|{ SHIPMENT_LINE : "contains"
    ORDER_LINE ||--o{ SHIPMENT_LINE : "allocated to"
    ORDER_LINE ||--o{ RETURN_LINE : "may return"
    RETURN_REQUEST ||--|{ RETURN_LINE : "contains"
    SHIPMENT ||--o{ DELIVERY_ATTEMPT : "may attempt multiple times"
~~~

This is a **logical candidate diagram**, not a conclusion that every shipment only contains lines from a single order. A system that consolidates parcels across orders needs a more complex Shipment–Order relationship, which must be verified.

### 13.1. Statuses that need separate definitions

- **Shipment packed:** parcel has been packed.
- **Dispatched:** warehouse has handed over to the carrier.
- **In transit:** parcel is on the way.
- **Delivered:** parcel is recorded as successfully delivered by the authoritative source.
- **Delivery attempt failed:** one delivery attempt failed; the shipment is not necessarily cancelled.
- **Returned to sender:** parcel returns to warehouse after failed delivery.
- **Return requested:** customer requests to return a quantity.
- **Return received:** returned goods have been received.
- **Return accepted:** decision to accept the return, possibly after inspection.
- **Refund succeeded:** refund cash flow has succeeded.

**Return received** does not necessarily mean **refund succeeded**. One discovery task is to check whether the current system merges these two milestones into a single status.

### 13.2. Multiple events do not mean multiple objects

One parcel can have three **DeliveryAttempts**: two failed attempts followed by success. Distinguish **shipment identity** from **attempt identity**, avoiding counting one parcel as three shipments.

## 14. Inventory discovery: stock on hand, reserved, and available

Sales says “out of stock” while Warehouse says “15 units left”. Both may be right if they are referring to two different quantity types.

A possible modeling formula:

~~~text
Available-to-promise
= On-hand
- Reserved
- Blocked
+ policy-approved incoming supply (if any)
~~~

Each component must be defined within **warehouse, batch/lot, SKU, and point-in-time scope**, rather than assuming a simplistic formula for every business.

| Term | Meaning to investigate |
|---|---|
| On-hand | Physical quantity recorded in the warehouse |
| Reserved | Quantity held for specific demand/orders |
| Blocked | Quantity held back due to inspection, damage, or other reasons |
| Available-to-promise | Quantity that can be promised per sourcing rules |
| Picked | Items picked from shelves, not necessarily dispatched |
| Dispatched | Left the warehouse per dispatch voucher |
| In-transit | Currently with delivery carrier |
| Returned-not-inspected | Returned to warehouse but not yet approved for resale |

### 14.1. An order reservation can be split

SKU-A qty 2 is initially reserved at warehouse W1. Later, 1 is shipped from W1 and 1 from W2. Thus a **reservation** is not necessarily a single number on the order; it may require `(orderLine, warehouse, reservationId, quantity, status)`.

If an investigator only asks “is there a stock quantity?” and models a single `product.stock` column, multi-warehouse and reservation scenarios will break the design.

## 15. Status is a lifecycle, not just one long enum

An Order can have multiple independent status dimensions:

- **Order lifecycle:** draft, placed, confirmed, cancelled, completed.
- **Payment state:** unpaid, partially captured, captured, partially refunded.
- **Fulfillment state:** unallocated, reserved, partially shipped, fully shipped.
- **Delivery state:** not dispatched, in transit, partially delivered, delivered.
- **Return state:** none, requested, partially returned, returned.

Do not try to force everything into one enum:

~~~text
ORDER_PAID_SHIPPED_PARTIAL_DELIVERED_REFUND_PENDING
~~~

The number of combinations explodes and invalid states become hard to control. Discovery must identify **the source of each status dimension** and when a UI displays a composite summary status.

### 15.1. Matrix of sample combinations

| Order | Payment | Fulfillment | Can it happen? |
|---|---|---|---|
| Placed | Unpaid | Unreserved | Possible, depending on channel |
| Confirmed | PartiallyCaptured | Reserved | Possible if paid in installments |
| Confirmed | Captured | PartiallyShipped | Possible |
| Cancelled | Refunded | PartiallyShipped | Must clarify handling of dispatched parcels |
| Completed | Captured | Returned | Must define if completed can reopen |
| Draft | FullyShipped | — | Usually anomalous, check exceptions |

**“Possible”** in the table is an exercise hypothesis. Learners must mark CONFIRMED/REJECTED/OPEN according to stakeholder decisions.

### 15.2. Do state transitions need history?

If you only store `current_status`, the system can answer “what is the order's state right now?” but struggles to answer “when was the order confirmed?” and “which states has it passed through?”.

Discovery must decide whether you need:

- Event log with `event_id`, `actor`, `timestamp`.
- State history with `[valid_from, valid_to)`.
- Bitemporal history if you must distinguish effective time from when the system learned of it.
- Audit trail for manual edits.

Do not adopt event sourcing just because history is needed; a history or audit table may suffice. However, if timeline reconstruction is required, every major milestone must have clear semantics and a reliable source.

## 16. Time discovery: which timestamp does each system use?

An order can have:

| Timestamp | Question | Expected source |
|---|---|---|
| cart_created_at | When was the cart created? | Web/POS |
| order_placed_at | When did the customer confirm placement? | Sales |
| order_accepted_at | When did the system accept the order? | Sales |
| payment_authorized_at | When did the provider approve the hold? | Payment |
| captured_at | When was the capture recorded? | Payment/provider |
| shipment_dispatched_at | When did goods leave the warehouse? | Warehouse |
| delivered_at | When did the carrier record successful delivery? | Delivery |
| return_requested_at | When did the customer request a return? | CSKH |
| return_received_at | When did the warehouse receive the return? | Warehouse |
| refunded_at | When did the refund succeed? | Payment |
| source_event_at | When does the source say the event happened? | Source system |
| ingested_at | When did the integration pipeline receive the data? | Data pipeline |

Do not assume **`order_placed_at = row_created_at`**. If a partner marketplace sends data late, the two timestamps may be hours apart.

### 16.1. Midnight boundary example

~~~text
23:55 on 30/06 (Vietnam time):
  Customer places an order on the partner marketplace.

00:15 on 01/07 (Vietnam time):
  Internal system receives and stores the order.
~~~

A report of “orders placed by customers on 30/06” differs from “orders received by the system on 01/07”. Both can be useful if the **time definition** is explicit.

When writing the glossary, **Order Date**, **Ingestion Date**, and **Payment Date** must specify formulas, timezones, and scope.

### 16.2. Cutoff boundaries for measures

If a sales report states “as of 23:59 on the last day of the month”, ask:

- In **which local timezone**?
- Is late-arriving data backfilled?
- Are reports restated when a refund occurs next month?
- Is there a period-close snapshot or a live query?
- Is the upper bound **`[start, next_start)`** to avoid dropping microseconds?

These questions affect downstream temporal modeling and analytics.

## 17. Mapping data sources and owning systems

You cannot build a trustworthy glossary without knowing which data comes from an authoritative source.

| Concept | Expected creation source | Authoritative source to confirm | Downstream consumers |
|---|---|---|---|
| Order | POS/Web/Marketplace | Sales order service or external source per scope | Warehouse, payment, BI |
| Product/SKU | Catalog/PIM | Catalog owner | Sales, warehouse, BI |
| Price snapshot | Checkout/POS | Sales transaction | Accounting, BI |
| Inventory reservation | Inventory service | Inventory | Warehouse, Sales |
| Payment attempt/capture | Payment provider/adapter | Payment ledger/integration | Sales, accounting, BI |
| Shipment/attempt | WMS/TMS/carrier | Fulfillment/delivery per event | CSKH, BI |
| Return request | CSKH/web | Return management | Warehouse, Payment |
| Refund transaction | Payment provider/finance | Payment/refund service | CSKH, accounting |
| Customer/account | Identity/CRM | Depends on identity type | Sales, marketing |
| Sales KPI | BI/finance | Approved metric owner | Leadership |

This is a **hypothetical table** for the exercise; do not treat these system names as default sources of truth in a real organization.

### 17.1. One concept can have multiple keys

Example:

~~~text
sales_order_id: internal UUID
marketplace_order_id: code issued by marketplace
external_source_system: source name/ID
pos_transaction_number: POS receipt/document number
~~~

Ask:

- Is the external code unique **across the whole marketplace, per store, or per day**?
- If an order is re-imported, which key is used for deduplication?
- If the marketplace changes codes, is there a crosswalk?
- If an order is split into two fulfillment units, how many IDs exist?
- Is the relationship between these keys one-to-one, one-to-many, or many-to-many?

### 17.2. Simplified data lineage

~~~mermaid
flowchart LR
    WEB["Web/POS/Marketplace"] --> S["Sales - Order/Line"]
    CAT["Catalog"] --> S
    S --> WH["Warehouse - Reservation/Shipment"]
    S --> PAY["Payment - Attempts/Captures"]
    WH --> RET["Returns"]
    PAY --> REF["Refunds"]
    S --> FACT["Fact Sales Line"]
    WH --> FACT
    PAY --> MET["Finance / Metrics"]
    REF --> MET
    FACT --> MET
~~~

This diagram shows **conceptual lineage**; it does not mean a fact table should simultaneously JOIN all raw shipments and payments on `order_id`, as doing so causes fanout and multiplies metrics.

## 18. Collecting sample data without jumping to false conclusions

A discovery sample set should cover normal flows, exceptions, and boundary cases.

| Sample | Scenario | What to learn |
|---|---|---|
| T01 | Single-line order, single capture, single parcel | Baseline |
| T02 | Two-line order, two captures | Payment cardinality |
| T03 | One line split across two shipments | ShipmentLine grain |
| T04 | Cancelled before delivery, already captured | Cancellation vs refund |
| T05 | Partial return after delivery | ReturnLine, refund allocation |
| T06 | Marketplace retries with same order code | Idempotency/source namespace |
| T07 | Guest POS without a Customer account | Optional identity |
| T08 | COD delivery, reconciled one day later | Payment vs delivery time |
| T09 | Marketplace data arrives late across day boundary | Event time vs ingestion time |
| T10 | Same SKU in two warehouses | Stock scope |
| T11 | Product changes category mid-period | Temporal relationship |
| T12 | Refund created but provider fails | Refund lifecycle |

**Sample data is observational evidence, not the complete rule set.** Even if 100 samples show only one payment per order, you must still ask whether partial payments are permitted and could appear in the future.

### 18.1. Cross-checking three layers of evidence

For a claim like “one order always has one payment”, cross-check:

1. **Business:** which rule does the domain authority approve?
2. **System behavior:** what do the API flow, states, and database currently allow?
3. **Observed data:** are there records disproving or confirming the constraint?

When the three layers conflict, mark **DISPUTED** and note why. Never pick the SQL schema as “business truth” just because it currently has a single-valued FK.

## 19. How does a business glossary differ from a data dictionary?

A **business glossary** defines the **concepts** used by the organization. A **data dictionary** defines **concrete data structures** such as tables, columns, data types, nullability, defaults, constraints, and lineage.

Example:

~~~text
Business glossary:
  "Sales Order" = a recorded purchase commitment with a persistent identity,
  line items, and commercial terms at a confirmation milestone.

Data dictionary:
  sales_order.order_id UUID NOT NULL PRIMARY KEY
  sales_order.placed_at TIMESTAMPTZ NULL
  sales_order.status_code VARCHAR(...) NOT NULL
~~~

One concept may span multiple tables. One physical table may hold data from multiple concepts if denormalized. Therefore, the glossary and data dictionary must be **linked**, not treated as a renamed list of columns.

### 19.1. Anatomy of a good definition

A definition should:

- Use business language and avoid circularly defining a term using itself.
- Specify the **triggering event or condition of existence**.
- Specify **inclusions and exclusions**.
- State the **grain/identity** when the concept has records.
- Distinguish it from closely related terms.
- Include examples and counterexamples.
- Record owner, evidence source, status, and version.

Poor example:

> “An order is an order created in the system.”

Better example:

> “A sales order is a recorded purchase request with a persistent ID, containing line items and commercial terms at the time of acceptance. Unconfirmed carts do not count as orders; full payment or full delivery is not a prerequisite for an order to exist.”

The latter definition is **a candidate for this scenario**; the owner still must confirm the exact “recorded” milestone and whether draft orders are permitted.

## 20. Template structure for a business glossary entry

| Field | Meaning |
|---|---|
| **term_id** | Stable identifier for the term |
| **preferred_term_vi** | Standard Vietnamese term |
| **preferred_term_en** | English term if needed |
| **aliases** | Synonyms / legacy UI screen names |
| **definition** | Non-circular business definition |
| **scope/context** | Bounded context, tenant, market, channel |
| **grain** | What one record or unit of measure represents |
| **identity_rule** | Identification rules, uniqueness scope |
| **inclusions** | Cases included |
| **exclusions** | Cases excluded |
| **example** | Example meeting the definition |
| **counterexample** | Counterexample helping differentiate |
| **related_terms** | Connected concepts |
| **system_mapping** | Related tables, APIs, events, fields |
| **owner** | Authorized approver |
| **source/evidence** | Policy, interviews, data profiling, decisions |
| **status/version** | Draft/Disputed/Approved, date/version |

Not every term needs all 17 fields in a published summary view. However, the **authoritative glossary** must store enough metadata for traceability and to prevent recurring debates.

### 20.1. Reference YAML format for a term

~~~yaml
term_id: TERM-SALES-ORDER
preferred_term_vi: "Đơn hàng"
preferred_term_en: "Sales Order"
scope: "Sales / omnichannel"
definition: >-
  A purchase request recorded by an authoritative system,
  with a persistent identifier and commercial terms;
  payment or delivery may happen later.
grain: "One created order, not one product line"
identity_rule: "Global order ID; namespaced source code"
inclusions: "Placed orders even if not yet paid"
exclusions: "Unconfirmed carts, payment attempts, shipments"
status: "DRAFT"
owner: "Sales domain owner"
evidence: "OBS-001 / Sales workshop"
~~~

This is **a sample format for a glossary entry**, not metadata to put into lesson YAML. In real applications, consider separating inclusions/exclusions into structured lists or relationships if searchability and version control are needed.
## 21. Sample business glossary: from customer to order

The following table is a **reference draft** for learners to bring into a workshop. All definitions are in **DRAFT** status until confirmed by owners.

| ID | Preferred term | Expected business definition | Do not equate with |
|---|---|---|---|
| TERM-001 | **Buyer** | Person or organization initiating a purchase request under the identity provided by the channel | Login account |
| TERM-002 | **Customer Account** | Profile used for authentication, permissions, and customer contact | Every walk-in buyer |
| TERM-003 | **Guest Buyer** | Buyer without an attached login account in the current transaction | A buyer with no identity in any system |
| TERM-004 | **Cart** | Set of item selections and tentative terms prior to confirmation | Recorded order |
| TERM-005 | **Sales Order** | Purchase request with a persistent ID, commercial terms, and lifecycle status | Payment/Shipment |
| TERM-006 | **Order Line** | A commercial position recorded on an order, containing SKU, quantity, captured price, and related discounts | SKU or a shipment parcel |
| TERM-007 | **Product** | Catalog object with identity and business attributes; may contain multiple variants | A SKU in all situations |
| TERM-008 | **SKU / Stock Keeping Unit** | Product/variant unit managed by code within a defined catalog/warehouse namespace | Product name |
| TERM-009 | **Captured Unit Price** | Unit price used to calculate the transaction at the defined lock milestone | Current catalog list price |
| TERM-010 | **Promotion** | Promotional rule with eligibility conditions and effective period | Discount amount on a line |
| TERM-011 | **Discount Amount** | Reduction allocated to an order or line according to finalized rules | Return fee, refund |
| TERM-012 | **Shipping Charge** | Fee charged to the customer for delivery service on the order | Actual carrier cost incurred by the company |

### 21.1. Scenario testing the first definitions

**Can one Order Line have the same SKU as another Order Line?**

Example:

~~~text
Line 1: SKU-A, qty 1, member promotion.
Line 2: SKU-A, qty 1, other promotion.
~~~

If the business allows this, you cannot treat **`UNIQUE(order_id, sku_id)`** as a universal invariant. You may use **`UNIQUE(order_id, line_no)`** or a surrogate `line_id`. This modeling consequence comes from the **Order Line concept**, not from database engine choice.

### 21.2. Lock down the grain of Product and SKU

A Product may represent a general product model, while a SKU represents a sellable/stocked variant. For example, a “Model A” shirt has SKUs per size/color. Yet in some businesses, Product and SKU are 1:1. Do not impose unnecessary structure if stakeholders confirm different semantics.

**The glossary must reflect the actual business**, rather than copying generic definitions and forcing data to fit.

## 22. Sample business glossary: payment, warehouse, delivery, and returns

| ID | Preferred term | Expected grain/semantics | Common confusion |
|---|---|---|---|
| TERM-013 | **Payment Attempt** | One payment interaction with a method/provider | Does not guarantee funds collected |
| TERM-014 | **Authorization** | Response permitting a hold/approval of an expected amount | Not synonymous with capture |
| TERM-015 | **Capture** | A transaction successfully recording collection of a specified amount | Not automatically settlement |
| TERM-016 | **Settlement** | Confirmation/payout step under provider contract | Different timestamp from capture |
| TERM-017 | **Inventory Reservation** | An allocation of available stock for demand at a warehouse and time | Not warehouse dispatch |
| TERM-018 | **On-hand** | Quantity managed at a location/warehouse per WMS source | Not always sellable |
| TERM-019 | **Available-to-promise** | Policy-based calculation from stock, reservations, and other statuses | Not simply on-hand |
| TERM-020 | **Shipment** | Fulfillment/delivery unit with its own ID, containing shipped lines | Not the entire order |
| TERM-021 | **Shipment Line** | An allocation of OrderLine quantity into a Shipment | Not a new OrderLine |
| TERM-022 | **Delivery Attempt** | One attempt by the carrier to deliver a parcel | Not a new Shipment |
| TERM-023 | **Return Request** | A request record to return goods, with decision and status | Not a Refund |
| TERM-024 | **Return Line** | A returned quantity tied to a purchased line/shipment per policy | Not an aggregated SKU count |
| TERM-025 | **Refund Transaction** | One execution returning funds to a method/destination per approved plan | Does not mean goods are received back |
| TERM-026 | **Cancelled Order** | Order transitioned to cancelled status per policy | Not synonymous with returned order |
| TERM-027 | **Received Return Item** | Returned goods recorded at the receiving point | Does not automatically become resalable |
| TERM-028 | **Delivered Quantity** | Quantity with proof of successful delivery at the cutoff | Not shipped quantity |

### 22.1. Metric definitions require formulas and time axes

Some glossary entries are **entities**, while others are **measures/metrics**. For a metric, a single descriptive sentence is insufficient. Document:

~~~text
TERM-METRIC-GROSS-MERCH
Name: Gross Merchandise Amount
Calculation grain: selected order lines in the period
Definition: SUM(ordered_quantity × captured_unit_price)
Includes: merchandise value before discounts
Excludes: shipping fees, refunds, taxes per
  exercise scope excluding tax
Time axis: order_placed_at in approved timezone
Owner: Sales/Finance (pending confirmation)
Status: DRAFT
~~~

**Do not automatically call this metric “accounting revenue”.** Calculating financial revenue also requires recognition basis, taxes, returns, fiscal periods, accounting policy, and finance sign-off.

### 22.2. Four figures easily given the same label “sales”

Using sample order O145:

| Proposed technical name | Formula in example | Value |
|---|---|---:|
| **gross_merchandise_amount** | Merchandise value before discount | 320,000 |
| **net_merchandise_before_returns** | Gross minus item discount | 300,000 |
| **order_payable_amount** | Net merchandise plus shipping fee | 330,000 |
| **net_captured_after_refunds** | Total captured minus successful refunds | 220,000 |

If Dashboard A labels 330,000 as sales and Dashboard B labels 300,000 as sales, both may have valid metrics for their respective purposes, but **a shared generic label misleads readers**. Standardized names, formulas, and scope notes are required.

## 23. Synonyms, homonyms, and terminology conflicts

A business glossary is not just a dictionary of definitions. It is **a mechanism to surface disagreements and align language**.

### 23.1. Synonyms with different definitions

For instance, POS staff say “sales slip”, web says “order”, and ERP says “sales document”. The three words might all refer to SalesOrder or three distinct document types depending on finalization timing.

Document:

~~~text
Preferred term: Sales Order
Confirmed aliases: "Web order", "POS order" (within defined scope)
Not synonyms: Cart, Invoice, Receipt, Shipment
~~~

Never declare **invoice** an alias of order: invoices and orders may have a many-to-one relationship or different recognition conditions.

### 23.2. One word carrying multiple meanings across bounded contexts

| Word in use | Sales meaning | Warehouse meaning | Finance meaning | Resolution |
|---|---|---|---|---|
| Success | Customer placed order | All goods delivered | Cash recognized/settled | Name OrderAccepted, Delivered, Captured/Settled |
| Return | Customer returns goods | Goods return to stock | Money refunded | Return vs Refund |
| Stock | Available to sell | On-hand | Inventory valuation | ATP, QuantityOnHand, InventoryValue |
| Customer | Account | Recipient | Billing party on voucher | Buyer, Account, Recipient, BillingParty |
| Sales | Order value | Dispatched quantity | Financial metric | Separate metric contracts |
| Cancel | Cancel order | Cancel dispatch | Reverse transaction/void | Separate lifecycles |

### 23.3. Conflict resolution workflow

1. Record the exact **two or more definitions** in use, along with who stated them.
2. Find a **counterexample transaction** where they yield different results.
3. Identify the **bounded context**: do both areas really need the same term?
4. If they are two concepts, assign **two distinct names** and define their relationship.
5. If a single shared metric is needed, designate an owner, formula, time axis, population, and data latency expectations.
6. Update the glossary, rule catalog, API/data contracts, and examples.
7. Record a decision ID, effective date, and affected dashboards.
8. Obtain owner sign-off; never let an analyst unilaterally decide accounting or business policy.

**The goal is not to force every department to use the same number for every purpose**, but to make each term precise enough to avoid contradiction within the same scope.

## 24. Turning the glossary into candidate entities and grains

After discovery, build a **candidate model** table. This bridges to logical design and does not mandate that every row becomes a physical table.

| Candidate | Grain | Candidate key | Relationships to verify |
|---|---|---|---|
| **SalesOrder** | One order | global_order_id | Order has N lines/payments/shipments |
| **OrderLine** | One line of an order | line_id or (order_id, line_no) | Belongs to one Order, references SKU snapshot |
| **ProductIdentity** | One logical product | tenant/source/product_code | Has N SKUs/versions |
| **SkuIdentity** | One SKU code in namespace | tenant/catalog/sku_code | Belongs to Product per policy |
| **PaymentAttempt** | One attempt to pay | attempt_id or namespaced provider ref | Belongs to intent/order/payment |
| **PaymentCapture** | One successful collection | capture_id | May link to order via allocation |
| **PaymentAllocation** | One portion of captured cash allocated to an order | allocation_id or composite | Needed if one capture pays multiple orders |
| **InventoryReservation** | One quantity hold at a warehouse | reservation_id | Links orderLine/SKU/warehouse |
| **Shipment** | One parcel/fulfillment unit | shipment_id | Has N shipment lines |
| **ShipmentLine** | One quantity allocated to a parcel | shipment_line_id | Links OrderLine and Shipment |
| **DeliveryAttempt** | One parcel delivery attempt | attempt_id | Belongs to Shipment |
| **ReturnRequest** | One return request | return_request_id | Has N return lines |
| **ReturnLine** | One returned quantity from a purchased line | return_line_id | Links OrderLine/ShipmentLine per rule |
| **RefundTransaction** | One refund payout | refund_id | Links payment capture/return per policy |
| **CustomerIdentity** | One scoped subject profile | canonical_id | Guest vs account/crosswalk |
| **OrderStatusEvent** | One timestamped state transition | event_id | Belongs to Order, ordered |
| **SalesLineFact** | One fact row at a defined milestone | source_line_id + snapshot/cutoff | Links dimensions/metrics |

### 24.1. Grain must be stated in a plain sentence

Example:

> “One ShipmentLine is a quantity of one OrderLine allocated to exactly one Shipment.”

From this sentence, one OrderLine can have multiple ShipmentLines if split across parcels. Conversely, one ShipmentLine record must not simultaneously represent three order lines, as quantity attribution would break down.

### 24.2. Source keys must include a namespace

~~~text
Marketplace A:
  source_order_id = 1001

POS Store HN-01:
  local_transaction_id = 1001
~~~

Both **1001** values can be valid simultaneously. A source key may require `(source_system, store_id, local_id)`; finalize this only after asking the issuing system within what scope IDs are reused.

Using a UUID as an internal ID is helpful, but it does not replace **source identity** or idempotency keys.

### 24.3. A diagram line does not prove a physical FK

Sales and Payment may live in separate databases. A line connecting Order–Payment on a diagram denotes a **business relationship**, not automatic proof of a cross-system physical `FOREIGN KEY`.

Document whether the link is enforced by DB constraint, API validation, outbox/CDC, or reconciliation so teams understand the consistency guarantees.

## 25. Business-rule catalog: from statements to verifiable conditions

Many rules cannot be seen from an ERD or a single sample row. Use stable rule IDs and record **source, scope, and status**.

| Rule ID | Proposed rule | Where to verify |
|---|---|---|
| BR-001 | OrderLine must belong to a valid SalesOrder | Sales owner, DB |
| BR-002 | Within an order, line_no cannot duplicate | Sales, import |
| BR-003 | A CONFIRMED order has at least one valid line | Sales, workflow |
| BR-004 | Ordered quantity of a line > 0 for standard sales lines | Sales, returns exceptions |
| BR-005 | ShipmentLine must reference an order line and have quantity > 0 | Warehouse |
| BR-006 | Total shipped quantity cannot exceed ordered quantity unless governed by special policy | Warehouse, Sales |
| BR-007 | Capture/refund must carry a transaction ID to guard against retries | Payment |
| BR-008 | Total successful refunds cannot exceed refundable captured amount | Finance, Payment |
| BR-009 | Same source order identity must not create two orders on retry | Integration |
| BR-010 | ReturnLine requires an eligible purchase source/line | CSKH, Returns |
| BR-011 | Returned quantity cannot exceed validly received quantity per policy | Returns |
| BR-012 | Line captured unit price preserves history when catalog prices change | Sales, Finance |
| BR-013 | Available stock must be scoped by warehouse/SKU/time | Warehouse |
| BR-014 | Partial delivery must not automatically mark the entire order fully delivered | Delivery |
| BR-015 | Reports specify time axis, timezone, and data status clearly | BI, Finance |
| BR-016 | Multi-tenant data must enforce tenant scope on every FK/identity | Security, DB |

Rules may be revised after workshops. Do not rush to enforce BR-008 with a single-row CHECK constraint: total refunds span **multiple transactions** and may require locking/versioning or a reservation mechanism.

### 25.1. Complete rule record template

~~~text
rule_id: BR-008
Name: Successful refund amount cap
Scope: One capture or refundable amount pool
Description:
  Total succeeded refunds must not exceed the refundable balance
  after adjustments/voids and valid allocations.
Source: Payment lead + Finance owner
Assumption: Refunds are strictly bounded by captured amount
Edge cases:
  Two concurrent refunds; one failed refund; callback retry.
Enforcement candidate:
  Transaction/version check + ledger invariant.
Test:
  Two concurrent refunds cannot jointly exceed remaining balance.
Status: OPEN – policy confirmation needed.
~~~

**Approving owners can change a rule**, but if the rule is already implemented in code or metrics, changes require versioning and impact analysis.

## 26. Verifying with a concrete transaction, not just paper definitions

For order WEB-O145, trace:

~~~text
SalesOrder O145
 ├─ OrderLine L1: SKU-A, qty 2
 └─ OrderLine L2: SKU-B, qty 1

Payment Captures
 ├─ P1: 200,000
 └─ P2: 130,000

Shipments
 ├─ S1: L1 qty 1; L2 qty 1
 └─ S2: L1 qty 1

Return
 └─ R1: L1 qty 1

Refund
 └─ F1: 110,000
~~~

### 26.1. Why raw joins on order_id multiply numbers

Suppose you JOIN SalesOrder with two PaymentCaptures and two Shipments on `order_id`:

~~~text
O145 × 2 PaymentCaptures × 2 Shipments = 4 result rows.
~~~

If you then compute **`SUM(payment.amount)`** directly over those four rows, the two payments are duplicated per shipment, yielding **660,000** instead of **330,000**. Joining the two order lines as well multiplies rows further.

This is **fanout**, not evidence that the order had four payment amounts.

### 26.2. Correct querying per grain

Total captured per order should be aggregated **at the payment capture grain** first:

~~~sql
SELECT
    order_id,
    SUM(captured_amount) AS captured_total
FROM payment_capture
WHERE capture_status = 'SUCCEEDED'
GROUP BY order_id;
~~~

This illustrative SQL assumes you have confirmed that each capture row belongs to a single order. If a payment can allocate across multiple orders, aggregate from **`payment_allocation`** rather than adding the entire capture to every order.

Similarly, total shipped quantity per order line must be aggregated from ShipmentLine, rather than using `COUNT(Shipment)` as shipped item count.

### 26.3. How to verify a metric

For the metric “Net merchandise before returns”:

1. State the **source grain**: one OrderLine.
2. State the **formula**: `quantity × capturedUnitPrice − allocatedItemDiscount`.
3. State the **status filter**: which orders/lines are included.
4. State the **time axis**: order placed, shipped, or another date.
5. State the **timezone** and late-data handling rule.
6. Specify whether **return adjustments** belong in this metric or a separate metric.
7. Reconcile example O145 to get 300,000.
8. Add to the glossary with status and owner.

Skipping a single step can cause two pipelines to output two different numbers that both look plausible.

## 27. Workshop for resolving conflicts and locking the glossary

A common situation:

- Sales: “An order succeeds as soon as the customer confirms placement.”
- Warehouse: “An order succeeds when all parcels are delivered.”
- Payment: “An order succeeds when full capture arrives.”
- BI: “Our dashboard counts non-cancelled orders.”

These definitions cannot share a single **`order_success`** attribute without scope/disambiguation.

### 27.1. Using comparison scenarios

| Scenario | Placed | Fully captured | Fully delivered | Not cancelled |
|---|---|---|---|---|
| O1 just placed, unpaid | Yes | No | No | Yes |
| O2 captured, not yet delivered | Yes | Yes | No | Yes |
| O3 delivered, COD not reconciled | Yes | Uncertain | Yes | Yes |
| O4 partially delivered, remainder cancelled | Yes | Depends | No | Policy-dependent |
| O5 fully delivered, then partially refunded | Yes | Yes before refund | Yes | Possibly |

The team can agree on distinct names:

- **OrderPlacedCount**: count of orders reaching placed milestone.
- **FullyCapturedOrderCount**: count of orders with full capture recorded per policy.
- **FullyDeliveredOrderCount**: count of orders with full delivered quantity per policy.
- **NonCancelledOrderCount**: count of orders not in cancelled status at cutoff.

These are **four distinct KPIs**, not four ways to write the same KPI.

### 27.2. Decision log template

~~~text
DEC-007
Issue:
  The term "successful order" has 4 interpretations.

Decision:
  Retire the generic term in new metrics.
  Use the 4 distinct names defined in the glossary.

Impact:
  Sales, Finance, and Delivery dashboards and metric APIs.
  Users must select the specific metric.

Owner: Product + Finance + BI
Status: PROPOSED (pending approval)
Effective version: upon approval
Evidence: Workshop W-02, scenarios O1–O5
~~~

**Do not mark APPROVED** when only one person has spoken. The status field tells readers what truly carries authority.

## 28. Session-by-session practice guide: groups of 4–6

The exercise can be organized into practice sessions with participants playing stakeholders and reviewers. If studying solo, answer from both sides and verify against sample data.

| Session | Task | Output |
|---|---|---|
| **Session 1** | Read scenario; define scope; build stakeholder map | D01, D02 |
| **Session 2** | Simulated interviews with Sales, Payment, Warehouse, CSKH | OBS/HYPOTHESIS/OPEN notes |
| **Session 3** | Map as-is, main flows, and exceptions | D03, D04 |
| **Session 4** | Build 20–30 terms, add aliases and counterexamples | D05 |
| **Session 5** | Identify authoritative sources, grains, and identities | D06, D09 |
| **Session 6** | Write business rules, disputes, and decisions | D07, D08 |
| **Session 7** | Cross-review against O145 and 12 boundary samples | D10 |
| **Session 8** | Finalize v1 glossary, prepare logical modeling handoff | Versioned dossier |

### 28.1. Simulated interview tasks

Each team assigns four roles: Sales owner, Payment lead, Warehouse lead, and Data analyst. The analyst must probe until able to explain:

1. When does a Cart become an Order?
2. What types of Orders exist?
3. Can one OrderLine appear in two Shipments?
4. Can one order have two successful captures?
5. What creates a ReturnRequest and when are items considered received?
6. How does a failed refund differ from a rejected return?
7. When is a SKU considered sellable at a specific warehouse?
8. Which channel issues source IDs and what is their uniqueness scope?
9. Which KPIs change due to late-arriving data?
10. Who approves the “revenue” formula?
11. Which formula does the system currently implement versus what policy wants?
12. Are timestamps and units of measure standardized?

Any question lacking sufficient evidence must stay **OPEN**, never filled with guesses.

### 28.2. Self-completion checklist

- Draw an as-is flowchart with at least three exception branches.
- Build a table of 25 terms containing at least definition, scope, examples, exclusions, owner, and status.
- Select 10 rules with `BR-xxx` IDs and link each to at least one test case.
- Create 6 counterexamples for easily confused terms.
- Produce a candidate model including at least Order, OrderLine, PaymentCapture, ShipmentLine, and ReturnLine.
- Write a data lineage from web order to BI dashboard.
- Explain why a raw JOIN of payments and shipments can cause fanout.
- Distinguish order date, capture date, delivered date, and ingestion date.
- Record at least 5 genuinely important open questions.
- Conduct a peer review: another person must read your artifacts and walk through transaction O145.

## 29. Reference solution guide and things not to finalize yet

This is an **evaluation guide**, not a single standard schema for every retailer.

### 29.1. Candidate diagram post-discovery

~~~mermaid
erDiagram
    CUSTOMER ||--o{ SALES_ORDER : "may place"
    SALES_ORDER ||--o{ ORDER_LINE : "contains"
    ORDER_LINE ||--o{ SHIPMENT_LINE : "allocated to"
    SHIPMENT ||--|{ SHIPMENT_LINE : "contains"
    SHIPMENT ||--o{ DELIVERY_ATTEMPT : "delivered via"
    SALES_ORDER ||--o{ PAYMENT_CAPTURE : "may be collected by"
    SALES_ORDER ||--o{ RETURN_REQUEST : "has return request"
    RETURN_REQUEST ||--o{ RETURN_LINE : "contains"
    ORDER_LINE ||--o{ RETURN_LINE : "purchase source"
    PAYMENT_CAPTURE ||--o{ REFUND_TRANSACTION : "may refund"
~~~

**Important notes:**

- The CUSTOMER–SALES_ORDER relationship is drawn 0..N because a customer may not have placed an order yet, while **whether an order requires a customer account remains an open question** (guest buyer).
- Linking PAYMENT_CAPTURE directly to one order only holds if the business confirms payments cannot allocate across multiple orders; otherwise **PaymentAllocation** is required.
- A ReturnLine may need a link to ShipmentLine to prove delivered source goods, depending on policy.
- A Shipment may contain lines from multiple orders if allowed; the diagram assumes single-order shipments for simplicity and must be verified.
- Connector lines represent **business relationships**; in a multi-service architecture there may be no physical FKs.

### 29.2. One strong glossary entry beats ten column names

Example for **“Captured Unit Price”**:

~~~text
term_id: TERM-009
definition:
  Unit price on an OrderLine fixed at the transaction
  lock milestone defined by the Sales owner.
grain:
  One unit price per order line or finalized line version.
scope:
  One tenant, one currency, one channel/source.
example:
  SKU-A has captured_unit_price 120,000 on O145.
counterexample:
  Catalog currently displays 130,000 for SKU-A.
business_rule:
  Never overwrite historical line prices just because catalog prices change.
owner:
  Sales owner; Finance consulted.
status:
  DRAFT until owner approves the exact lock milestone.
~~~

### 29.3. Calculating the four figures in scenario O145

- Gross merchandise before discount: **320,000 VND**.
- Item discount: **20,000 VND**.
- Merchandise after discount, before returns: **300,000 VND**.
- Total customer payable including shipping: **330,000 VND**.
- Two captures: **200,000 + 130,000 = 330,000 VND**.
- One sample return/refund: **110,000 VND**.
- Captured minus refunded: **220,000 VND**.

Do not treat **220,000** automatically as “recognized net revenue” because accounting rules, fees, and taxes are not yet finalized. This is a problem of **metric naming and approval governance**, not just arithmetic.

### 29.4. Questions that are still valid when unanswered

A well-executed team submission might explicitly state:

- “No authoritative confirmation yet on whether guest orders require `customer_id`.”
- “Not yet finalized whether payment captures can allocate across multiple orders.”
- “Policy not yet finalized on shipping fee treatment during partial returns.”
- “Not yet finalized whether returned items can be received at a different warehouse.”
- “Not yet finalized whether financial KPIs use `order_placed_at` or `captured_at`.”

**Documenting an important open question accurately is better than inventing a false constraint.**

## 30. Practice grading rubric

Reference total **100 points**, emphasizing clarity and verifiability over diagram count.

| Criterion | Max points | High-quality bar |
|---|---:|---|
| **Scope and stakeholders** | 10 | Clear objectives, owners, boundaries, and accurate roles |
| **As-is + exceptions** | 15 | Payment, delivery, cancellation, return, and late-data branches not missed |
| **Business glossary** | 25 | Clear, non-circular definitions with scope/grain/aliases and counterexamples |
| **Identity, source, and time** | 15 | Namespaces, authoritative sources, and timestamps properly separated |
| **Business rules and test cases** | 15 | Verifiable invariants, separating assumptions from facts |
| **Conflict resolution** | 10 | Decision log, owners, and non-conflicting metric definitions |
| **Documentation and presentation** | 10 | Readable artifacts with versioning, evidence, privacy, and handoff |
| **Total** | **100** | No critical errors in grain or measures |

### 30.1. Severe point deductions

- Treating Cart as Order without specifying the conversion milestone.
- Assuming one Order has only one Payment/Shipment despite O145 disproving it.
- Using “successful” without specifying order, payment, or delivery.
- Merging Return and Refund into one entity without justification.
- Computing `SUM(amount)` after joining multiple 1–N relationships without protecting grain.
- Using local IDs as global IDs when multiple sources can collide.
- Omitting source/owner for revenue metrics.
- Using captured amount as accounting revenue without clarifying policy.
- Labeling a hypothesis as APPROVED without sign-off.
- Copying real customer/payment info into discovery documents.

### 30.2. Glossary quality checklist

For each term, ask:

1. **Unique meaning:** within the same scope, is there one primary definition?
2. **Non-circular:** does it avoid simply repeating the term name?
3. **Scope:** are tenant/channel/bounded context and applicability period clear?
4. **Grain:** is it clear what one record or value represents?
5. **Counterexample:** does it distinguish closely related terms?
6. **Traceable:** are source and verifying owner recorded?
7. **Testable:** is there a transaction example confirming or refuting it?
8. **Governed:** are review status and version present?

If not, the glossary remains a draft and must not be used as a final data contract for implementation.

## 31. Handoff checklist and next modeling steps

Before handing discovery outputs over to logical modeling:

- **Scope:** are start/end points and out-of-scope systems clearly stated?
- **As-is:** where does actual flow differ from policy/to-be?
- **Stakeholders:** who is accountable for each group of terms/rules?
- **Evidence:** are there IDs for interviews, sample transactions, and observed data?
- **Glossary:** are Order, Line, SKU, Capture, Shipment, Return, Refund, and metrics unambiguous?
- **Identity:** do internal ID, source ID, and idempotency key have proper namespaces?
- **Grain:** does every candidate entity have a sentence stating “one row is one what”?
- **Cardinality:** have one-order-many-payments/shipments and one-line-many-shipments been verified?
- **State:** are order/payment/fulfillment/return lifecycles kept from arbitrary merging?
- **Temporal:** are order time, capture time, delivery time, event time, and ingestion time separated?
- **Metrics:** do measures have formulas, filter statuses, units, timezones, and owners?
- **History:** have changes requiring historical tracking been identified?
- **Sources:** are authoritative systems, downstream consumers, and reconciliation mechanisms documented?
- **Constraints:** do key rules have test cases without prematurely imposing unverified schemas?
- **Disputes:** do conflicting definitions have decision logs/open issues?
- **Privacy:** are documents free of unnecessary PII and payment tokens/details?
- **Version:** is it clear which glossary and process sections are approved vs draft?
- **Next step:** is there a list of candidate entities, relationships, grains, and open questions to start the logical ERD?

### 31.1. Post-discovery workflow chain

~~~mermaid
flowchart TD
    A["As-is process discovery"] --> B["Glossary + business rules"]
    B --> C["Lock entity grain & identity"]
    C --> D["Logical model: PK/FK/cardinality"]
    D --> E["Constraints, normalization, temporal history"]
    E --> F["Choose relational/document/graph/analytical model"]
    F --> G["Physical schema, indexes, partitions, migrations"]
    G --> H["Test data, queries, and concurrency"]
    H --> I["Review model & update glossary"]
~~~

**Conclusion:** a trustworthy data model must start from **what the business actually does**, not from pre-existing column names. Process discovery exposes data creation points, state transitions, one-to-many, many-to-many, and exceptions; the business glossary clarifies **what an object or measure means, in what scope, and by which source**. Once terms, grains, timestamps, and invariants have been articulated and verified with examples, designing ERDs, choosing keys, normalizing, building facts/dimensions, and tuning queries rest on an accurate, evolvable, and verifiable foundation.
