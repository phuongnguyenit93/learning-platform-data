# Orders: Data Snapshots, State Management, and Transaction Boundaries

An order is a commitment made at **a specific point in time**: which products the customer chose, in what quantities, at what prices and promotional terms, where to deliver, under what shipping conditions, and which states the order subsequently transitioned through. If an application only stores `productId` and `quantity` and queries current product details on every display, yesterday's invoice could change when a seller edits the product name, price, or tax rate today. If two concurrent processes mark an order as `PAID` and `CANCELLED` without checking its prior state, the system might both issue a refund and ship the goods.

The MongoDB document model is well-suited for **encapsulating data that changes together and needs to be read as a unit**, but that does not mean putting *everything* related to an order into one document. The product catalog, shared inventory, payment gateway transactions, accounting ledgers, integration logs, and delivery workflows each have their own lifecycles and consistency boundaries.

The lesson **“Orders: Data Snapshots, State Management, and Transaction Boundaries”** in the **Application Design** chapter of the **MongoDB Document Database Engine** module builds an order model capable of explaining history, withstanding concurrent requests, recovering from failures, and integrating with external systems in a controlled manner.

The three most important design decisions:

1. **What to snapshot, what to reference?** Information used to define the order's commercial commitment must be preserved at checkout time; entities with independent lifecycles are usually referenced.
2. **How does state change?** Do not rely on a bare `status` field that can be overwritten arbitrarily; use a state machine, transition conditions, versioning, and auditing.
3. **Where are the transaction boundaries?** A single MongoDB document update is atomic within that document; multiple documents require a transaction when a cross-document invariant truly exists; external payment gateways and shipping carriers **do not participate in MongoDB transactions**.

> **Core rule:** A confirmed order must never silently change meaning because the catalog or price list changed. Any published state must correspond to real business evidence. And a retriable request must avoid creating duplicate orders, charging twice, or deducting inventory a second time.

---

## 1. An Order Is a Business Aggregate, Not Just a Record

An order typically passes through the following phases:

```text
Cart
    │
    ▼
Create order / lock pricing
    │
    ▼
Reserve stock / confirm availability
    │
    ▼
Payment / confirm payment method
    │
    ▼
Prepare order (packing)
    │
    ▼
Hand off to carrier
    │
    ▼
Complete / cancel / refund / dispute
```

These steps do not share the same owner and do not complete simultaneously. An order therefore needs all of the following:

- **Committed data at checkout**: items, prices, quantities, taxes, promotions, shipping fees.
- **Current status**: pending payment, paid, shipped, cancelled, etc.
- **State audit trail**: who, when, by which event, and with what outcome.
- **Reference identifiers**: customer, products, warehouse, payment intent, shipments.
- **Versioning and concurrency**: prevent stale commands from overwriting newer states.
- **Consistency boundaries**: changes that must succeed together versus changes coordinated via workflows.

### 1.1. An Aggregate Does Not Mean One Document Containing Everything

In domain-driven design, an *aggregate* is a boundary for consistency rules. MongoDB can store major parts of an aggregate inside a single document to leverage single-document atomicity, yet an order tied to entities like inventory, a payment ledger, and fulfillment does not automatically turn all of them into one small transaction.

### 1.2. Distinguishing Sources of Truth

| Data | Recommended source of truth |
|---|---|
| Current product name and description | Product catalog |
| Price accepted by the customer | Snapshot inside the order |
| Confirmed order total | Order pricing snapshot |
| Available inventory quantity | Inventory service/collection |
| Actual captured/refunded amount | Payment provider and reconciled payment/ledger records |
| Actual shipping progress | Shipping/fulfillment service |
| User-facing composite status | Order projection backed by evidence |
| Sync/inter-service event log | Outbox/events with separate retention |

A bare `order.paymentStatus = "PAID"` is insufficient proof that funds were actually captured by the payment gateway without a reconciled transaction record.

## 2. Example Problem: A Multi-Tenant Sales System

Suppose an application serves multiple stores (*tenants*). Each tenant has:

- Its own products and price lists;
- Orders carrying tenant-scoped identifiers;
- Warehouses across multiple locations;
- Diverse payment methods;
- Product names/images/prices that can change over time.

An order `ORD-2026-001` belonging to tenant `TENANT-A` contains two line items, is paid via an external gateway, and may be shipped in two parcels.

Business requirements:

1. Once an order is confirmed, never alter historical prices when the catalog changes.
2. Never create two orders for a retried checkout request.
3. Never oversell beyond inventory according to the reservation policy.
4. Never transition from `CANCELLED` to `SHIPPED` due to a late callback.
5. Support reconciling amounts, quantities, and refund flows.
6. Support recovering jobs that crashed between DB writes and external service calls.
7. Read order history pages quickly without re-joining the entire catalog.

## 3. Choosing Document Boundaries

A common design:

```text
orders
  └── One document per order
        ├── Order identity
        ├── Order lines (snapshots)
        ├── Totals and currency
        ├── Checkout snapshot
        ├── Current status + revision
        └── Small state summary

inventory
  └── Stock per SKU/warehouse

stock_reservations
  └── Reservation per order/line/warehouse

payment_attempts
  └── One or more payment attempts

payment_ledger
  └── Charge/refund transactions, preferably append-only

shipments
  └── One or more shipping parcels

outbox_events
  └── Events to publish to external systems
```

Fields sharing the same lifecycle and frequently read/written together are well worth **embedding** in `orders`. Objects with frequent updates, independent ownership, potentially unbounded growth, or cross-order query needs should generally be **referenced**.

### 3.1. Why Is Embedding `orderLines` Appropriate?

Most orders have a small, bounded number of line items. When reading order details, users need all line items immediately. Keeping `items` inside the order document provides a consistent single read and enables atomic updates within the order document.

### 3.2. Do Not Embed the Entire Catalog Product

A product appears in millions of orders. Embedding **the entire product record and current operational data** bloats the document, stores unnecessary information, and blurs the snapshot definition. Store only the fields that establish the commitment and support historical display.

### 3.3. Do Not Embed Unbounded Payment Event History

An order can receive many retries, webhooks, payment authorizations, captures, and refunds. Appending all raw events into `orders.events` lets the document grow unboundedly, hit the BSON document limit, and become a write hotspot. Use a separate events/payment records collection and keep only a small summary on the order.

## 4. Reference Order Document

Mock data example:

```javascript
{
  _id: "ORD-2026-001",
  tenantId: "TENANT-A",
  customerId: "CUS-102",

  orderNo: "2026-001",
  idempotencyKey: "checkout-8d2f...",
  schemaVersion: 3,
  revision: NumberLong("8"),

  placedAt: ISODate("2026-11-14T04:15:00Z"),
  currency: "VND",

  items: [
    {
      lineId: "L1",
      productId: "PROD-101",
      sku: "SHIRT-BLUE-M",
      snapshot: {
        name: "Blue shirt size M",
        variantLabel: "Blue / M",
        sellerName: "Store A",
        catalogVersion: NumberLong("15")
      },
      quantity: NumberInt(2),
      unitPriceMinor: NumberLong("250000"),
      discountMinor: NumberLong("20000"),
      taxMinor: NumberLong("0"),
      lineTotalMinor: NumberLong("480000")
    },
    {
      lineId: "L2",
      productId: "PROD-202",
      sku: "CAP-BLACK",
      snapshot: {
        name: "Black cap",
        variantLabel: "Black",
        sellerName: "Store A",
        catalogVersion: NumberLong("3")
      },
      quantity: NumberInt(1),
      unitPriceMinor: NumberLong("150000"),
      discountMinor: NumberLong("0"),
      taxMinor: NumberLong("0"),
      lineTotalMinor: NumberLong("150000")
    }
  ],

  pricing: {
    itemsSubtotalMinor: NumberLong("650000"),
    discountsMinor: NumberLong("20000"),
    shippingMinor: NumberLong("30000"),
    taxMinor: NumberLong("0"),
    grandTotalMinor: NumberLong("660000"),
    pricingRuleVersion: "pricing-v7",
    calculatedAt: ISODate("2026-11-14T04:14:58Z")
  },

  deliverySnapshot: {
    recipientName: "Test recipient",
    addressLine: "Anonymized address",
    city: "Sample city",
    countryCode: "VN",
    serviceCode: "STANDARD"
  },

  status: "PAID",
  paymentStatus: "CAPTURED",
  fulfillmentStatus: "NOT_STARTED",

  payment: {
    provider: "provider-x",
    paymentIntentId: "PAY-INTENT-001",
    capturedMinor: NumberLong("660000")
  },

  createdAt: ISODate("2026-11-14T04:15:00Z"),
  updatedAt: ISODate("2026-11-14T04:20:00Z")
}
```

Illustrative calculation: `2 × 250000 + 150000 = 650000`; discount `20000`, shipping `30000`, grand total `660000` minor units. For VND, the application must document currency storage and rounding rules; do not assume the suffix `Minor` means “cents” for every currency.

### 4.1. Does `_id` Have to Be an ObjectId?

Not necessarily. A system can use `ObjectId`, standard BSON UUID, a String order ID, or a compound identity. What matters is:

- Unique per business rules;
- Deterministically reproducible on retry;
- Does not leak sensitive information;
- Supports the shard key/index strategy;
- Easy to correlate with payment/fulfillment systems.

### 4.2. `tenantId` Cannot Be Treated as a Decorative Field

Every query and write in a shared collection must preserve tenant scope, except for explicitly authorized admin operations. Enforce authorization at the service boundary; merely having an index containing tenant does not protect cross-tenant data.

## 5. What Is a Snapshot at Order Placement Time?

A **snapshot** captures what the customer and seller agreed upon at the moment the contract was formed. It is different from a *cache* of the current product.

Example:

```text
Nov 14:
  Shirt named "Blue shirt"
  Price 250000 VND
  Customer orders 2 pieces

Nov 15:
  Seller renames to "Premium shirt"
  Listed price changes to 320000 VND
```

The old order's invoice must still show the accepted name/price per business rules, rather than displaying 320000 and recalculating the total.

### 5.1. Fields That Should Usually Be Snapshotted

| Group | Example fields | Reason |
|---|---|---|
| Product identity | Product ID, SKU, variant IDs | Traceability |
| Display | Name, variant, seller label | Historical display |
| Commercial | Unit price, discounts, tax, currency | Monetary proof |
| Fulfillment | Shipping service, fee, delivery address at checkout | Delivery/reconciliation |
| Rule references | Pricing/tax/promotion rule version | Explain calculations |
| Contract | Terms/policy version or hash when needed | Auditing |
| Timestamp | Confirmation timestamp in UTC | Time-based traceability |

### 5.2. Fields Usually Kept as References Instead of Full Snapshots

- Current available inventory;
- Current price for new purchases;
- Currently open shipping options;
- Product ratings/reviews;
- Full customer profile;
- Payment provider secrets/tokens;
- Unbounded raw webhook payloads;
- Shipment lifecycle;
- Long event histories.

### 5.3. A Snapshot Does Not Mean Never Editable Under Any Circumstance

There are cases where the **delivery address must be updated after placement**, but you must distinguish:

- Initial `deliverySnapshot`;
- Approved `deliveryCurrent` or shipment destination;
- Audit of who requested the change, allowed conditions, and timestamp;
- Impact on shipping fees/taxes if any.

Never silently overwrite the original address and lose track of the prior commitment.

## 6. `productId` Is a Reference, Snapshot Is Historical Evidence

A line item can store both:

```javascript
{
  productId: "PROD-101",
  sku: "SHIRT-BLUE-M",
  snapshot: {
    name: "Blue shirt size M",
    unit: "piece",
    sellerName: "Store A"
  },
  unitPriceMinor: NumberLong("250000")
}
```

`productId` lets you link back to the catalog when viewing current details. `snapshot` preserves historical display even if the product is hidden, renamed, or discontinued.

### 6.1. What If the Catalog Deleted the Product?

The order must still return the minimum information required for transactions/reconciliation under the retention policy. The UI can display “product no longer available” alongside the snapshot name.

### 6.2. Is a Larger Snapshot Always Better?

No. Storing excessive product data increases storage cost and PII/IP exposure. Choose fields based on what must be proven contractually and operationally, avoiding copying long HTML descriptions, binary images, internal secrets, or unnecessary inventory metadata.

### 6.3. What If a Name/Description Violates Policy?

Display may need to be hidden/redacted per policy, while the transaction record is retained under protected auditing mechanisms. Separate evidence preservation from public UI rendering.

## 7. Capturing Prices at the Right Time and Avoiding TOCTOU

A **time-of-check to time-of-use** bug:

```text
T1 API reads current price = 250000
T2 Seller changes price = 270000
T3 API creates order and fetches product price again
T4 Client is charged a different total than confirmed
```

A solid flow:

```text
User selects cart
      │
      ▼
Quote pricing v7 (with quoteId and expiry)
      │
      ▼
User confirms quote
      │
      ▼
Server verifies quote is still valid
      │
      ▼
Create order with exact accepted snapshot
```

A quote can bind to:

- Product/variant IDs;
- Quantities;
- Currency;
- Unit prices;
- Discounts;
- Tax/shipping;
- Expiration;
- Rule/version;
- Customer/tenant scope;
- Hash/signature or server-stored immutable quote.

### 7.1. Do Not Trust Prices Sent by the Frontend

The frontend could send `unitPrice=1` by tampering with the request. The backend must calculate/verify prices from an authoritative source or a server-issued quote bound to identity and expiry.

### 7.2. What to Do When a Quote Expires?

Require recalculation and fresh customer confirmation of the new price. Do not silently change the total after the user clicked confirm without an explicit rule allowing it.

## 8. Currency, Scale, and Precision

Two common models:

1. **Minor units with Int64:** `amountMinor: NumberLong("660000")`, paired with `currency`.
2. **Decimal128:** `amount: NumberDecimal("660000.00")`, paired with a currency/scale policy.

Do not use `double` for monetary amounts requiring decimal precision without an explicit rounding and verification policy.

### 8.1. What Do Minor Units Mean?

The “smallest unit” depends on the currency. USD normally uses cents; VND typically uses whole dong in retail systems; other currencies follow different rules. The system should define:

```text
currency = "VND"
amountMinor = 660000
scale = per versioned currency/config
```

Avoid hardcoding “every currency has 2 decimal places”.

### 8.2. Do Not Add Amounts in Different Currencies

```text
500000 VND + 20 USD
```

is not a valid total. For multi-currency checkout, you need an exchange-rate snapshot, currency conversion rules, rounding, rate source, and audit trail.

### 8.3. Every Calculation Must Have Invariants

For example:

```text
itemsSubtotal = Σ(quantity × unitPrice)
discountsTotal = sum of applied discounts
taxTotal = sum of taxes per rules
shipping = locked shipping fee
grandTotal = itemsSubtotal - discountsTotal + taxTotal + shipping
```

Verify:

- Non-negative except for credits/refunds modeled separately;
- No Int64 overflow;
- Consistent currency;
- Proper rounding rules;
- Discounts do not exceed valid bounds;
- Line totals and order total reconcile.

### 8.4. Unit Tests for Totals

```text
2 × 250000 = 500000
1 × 150000 = 150000
Subtotal = 650000
Discount = 20000
Shipping = 30000
Tax = 0
Grand total = 660000
```

Unit prices after confirmation must be read from the snapshot during audit recalculation, not from the live catalog.

## 9. Taxes, Promotions, and Shipping Fees Must Be Versioned

Taxes, promotions, and shipping rates change over time.

Snapshot the meaningful inputs/outputs:

```javascript
pricing: {
  couponCode: "WELCOME",
  promotionRuleId: "PROMO-77",
  promotionRuleVersion: "v4",
  taxPolicyVersion: "tax-2026-11",
  shippingQuoteId: "SHIP-Q-919",
  itemsSubtotalMinor: NumberLong("650000"),
  discountsMinor: NumberLong("20000"),
  taxMinor: NumberLong("0"),
  shippingMinor: NumberLong("30000"),
  grandTotalMinor: NumberLong("660000")
}
```

### 9.1. Is Storing `couponCode` Enough?

No. If a promotion changes from 10% to 5% today, querying the current coupon cannot accurately reconstruct the historical discount reason. Store the applied result/version and required audit details.

### 9.2. Discount Allocation per Line

When cancelling or refunding partially, you need to know how the discount was allocated to each line item. Storing only `discountTotal` leaves you without the data to compute an accurate refund for 1 of 2 items.

### 9.3. Jurisdiction-Based Taxes

Address, country, item category, and timestamp can affect taxes. Do not alter taxes on past orders when a new tax config is deployed, unless an explicit adjustment workflow with separate auditing applies.

## 10. Order Status Is a State Machine

A minimal design might look like:

```text
          CREATED
             │
             ▼
      PENDING_PAYMENT
       │           │
   pay success     timeout/cancel
       │           │
       ▼           ▼
      PAID      CANCELLED
       │
       ▼
    PACKING
       │
       ▼
    SHIPPED
       │
       ▼
    DELIVERED
```

In reality, there are **payment failures, refunds, returns, and partial shipments**, so a single enum can become overloaded.

### 10.1. Splitting Statuses by Subdomain

One model:

```javascript
{
  status: "CONFIRMED",
  paymentStatus: "CAPTURED",
  fulfillmentStatus: "PARTIALLY_SHIPPED",
  refundStatus: "NONE"
}
```

`status` is the user-level composite status; the sub-statuses reflect independent domains.

### 10.2. Do Not Create a Meaningless Cartesian Product

Allowing 7 order states × 6 payment × 6 fulfillment × 5 refund produces 1,260 theoretical combinations, many of them invalid. Design **cross-status invariants** instead of treating every field as completely independent.

### 10.3. Separate Technical Errors from Business States

A `payment callback timeout` does not necessarily mean `PAYMENT_FAILED`: the gateway may have captured the payment while the webhook has not arrived yet. Use states like `PAYMENT_UNKNOWN`/`RECONCILIATION_REQUIRED` when appropriate instead of blindly cancelling or re-charging.

## 11. State Transition Matrix

An example rule table:

| Current state | Command/event | New state | Condition |
|---|---|---|---|
| `CREATED` | Submit checkout | `PENDING_PAYMENT` | Pricing snapshot valid |
| `PENDING_PAYMENT` | Payment captured | `PAID` | Verified provider event/amount |
| `PENDING_PAYMENT` | User cancel | `CANCELLED` | Not captured or policy permits |
| `PENDING_PAYMENT` | Payment expired | `CANCELLED` | No unreconciled capture |
| `PAID` | Start packing | `PACKING` | Inventory committed |
| `PACKING` | Handoff to carrier | `SHIPPED` | Shipment created |
| `SHIPPED` | Delivery confirmed | `DELIVERED` | Carrier evidence |
| `PAID` | Approved cancellation | `CANCEL_PENDING_REFUND` | Not yet shipped, approved |
| `CANCEL_PENDING_REFUND` | Refund confirmed | `CANCELLED` | Refund recorded |
| `DELIVERED` | Return approved | `RETURN_IN_PROGRESS` | Policy permits |
| `RETURN_IN_PROGRESS` | Refund complete | `REFUNDED` or `CLOSED` | Return/refund reconciled |

This table is only an illustrative model. Real domains may involve COD, marketplace split settlements, preorders, digital goods, or multi-leg delivery.

### 11.1. Never Transition States via Arbitrary `$set`

An API like:

```javascript
db.orders.updateOne(
  { _id: orderId },
  { $set: { status: request.body.status } }
);
```

is dangerous without checking authorization and transition rules. A caller could move an order from `CANCELLED` to `DELIVERED` without any shipment.

### 11.2. Transitions Should Carry Provenance

Record:

```text
commandType
actor/system
eventId
sourceRevision
timestamp
reasonCode
evidenceReference
```

This is data for auditing and reconciliation, without forcing every status field to become a full event-sourced system.

## 12. Critical Invariants

Examples:

1. `grandTotalMinor` equals the committed formula.
2. `items` is non-empty when confirming a standard sales order.
3. Each line has `quantity > 0`.
4. Consistent currency.
5. Each `(tenantId, orderNo)` is unique.
6. One idempotency key creates at most one order within the defined scope.
7. `capturedMinor` does not exceed the authorized amount per the payment contract.
8. `refundedMinor` does not exceed the corresponding captured amount.
9. Never `SHIPPED` without fulfillment evidence.
10. Never `CANCELLED` once shipped unless the domain defines a separate return/recall flow.
11. Never ship the same line/quantity twice.
12. Never oversell if inventory policy forbids it.
13. Every mutation carries revision/audit tracking.
14. A single provider event ID never produces business side effects twice.

**Business invariants** dictate consistency boundaries. Do not choose transactions solely based on how many collections hold the data.

## 13. A Single MongoDB Document Updates Atomically

MongoDB supports write atomicity on a **single document** per server semantics, even when modifying multiple fields in the same update.

Example:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-2026-001",
    tenantId: "TENANT-A",
    status: "PENDING_PAYMENT"
  },
  {
    $set: {
      status: "PAID",
      paymentStatus: "CAPTURED",
      "payment.capturedMinor": NumberLong("660000"),
      updatedAt: new Date()
    },
    $inc: { revision: NumberLong("1") }
  }
);
```

If the filter matches, all fields change in one document-level atomic operation. If it does not match, it will never partially update `status` while skipping `paymentStatus`.

### 13.1. Atomic Updates Do Not Mean Business-Valid Commands

If code fails to verify a payment event, the database can still atomically set `PAID`. MongoDB provides atomicity, while the service must verify **permission** and **evidence** before executing.

### 13.2. Checking `matchedCount`

```javascript
const r = db.orders.updateOne(
  {
    _id: "ORD-2026-001",
    tenantId: "TENANT-A",
    status: "PENDING_PAYMENT"
  },
  {
    $set: { status: "PAID" },
    $inc: { revision: NumberLong("1") }
  }
);

printjson({
  matched: r.matchedCount,
  modified: r.modifiedCount
});
```

If `matchedCount = 0`, the order may not exist, the tenant may be wrong, or the status already changed. Do not blindly treat this as a “MongoDB error and retry infinitely”.

## 14. Optimistic Concurrency Control with `revision`

A guard against lost updates:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-2026-001",
    tenantId: "TENANT-A",
    revision: NumberLong("8"),
    status: "PAID"
  },
  {
    $set: {
      status: "PACKING",
      updatedAt: new Date()
    },
    $inc: {
      revision: NumberLong("1")
    }
  }
);
```

The worker reads revision 8 and uses that exact revision in the filter. If another worker has already updated it to 9, the filter no longer matches.

### 14.1. Race Example

```text
T1 Worker A reads PAID, rev=8
T2 Worker B reads PAID, rev=8
T3 A updates PACKING, rev=9 → success
T4 B updates CANCELLED with rev=8 → matchedCount=0
```

Worker B must **re-read and decide according to the new state's rules**, never drop the revision filter and overwrite.

### 14.2. Are Both `status` and `revision` Needed?

In many cases, having both is advisable:

- `revision`: guarantees no overwrite by any concurrent change.
- `status`: expresses the business precondition directly.

If the business logic only needs a transition from a specific status, CAS on status may suffice. If multiple changing fields affect the decision, revision catches any intervening mutation.

### 14.3. Revision Is Not a Timestamp

Do not use `updatedAt` as a version simply because it is convenient to display. Clock skew, timestamp resolution, and concurrent writers can make timestamp comparisons unsafe; an explicit counter or version token is easier to reason about.

## 15. Java Sync Driver Example for Safe State Updates

Example using the MongoDB Java Sync Driver:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;

import org.bson.Document;
import org.bson.conversions.Bson;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

public final class OrderTransitions {

    public static boolean markPacking(
        MongoCollection<Document> orders,
        String tenantId,
        String orderId,
        long expectedRevision
    ) {
        Bson filter = and(
            eq("_id", orderId),
            eq("tenantId", tenantId),
            eq("status", "PAID"),
            eq("revision", expectedRevision)
        );

        Bson update = combine(
            set("status", "PACKING"),
            currentDate("updatedAt"),
            inc("revision", 1L)
        );

        UpdateResult result = orders.updateOne(filter, update);
        return result.getMatchedCount() == 1;
    }
}
```

This code assumes `revision` is stored as BSON Int64. For legacy records with Int32 or missing revisions, migration and mapping tests are needed first. Consistently use Java `long` for new revisions.

### 15.1. Return Meaningful Results

`false` does not necessarily mean a server error; the service should re-read within tenant scope and return one of:

- Order does not exist;
- Unauthorized;
- Invalid state transition;
- Version conflict;
- Already processed.

Do not disclose the existence of another tenant's order when the caller lacks permission.

### 15.2. When to Use `findOneAndUpdate`?

When you need the **post-update document** in one operation, use `findOneAndUpdate` with `ReturnDocument.AFTER`, matching filter, and options.

```java
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;

Document after = orders.findOneAndUpdate(
    filter,
    update,
    new FindOneAndUpdateOptions()
        .returnDocument(ReturnDocument.AFTER)
);
```

If `after == null`, the filter did not match. This is not a cross-collection transaction.

## 16. Transitions Requiring Multiple Conditions

For example, transitioning `PACKING → SHIPPED` when:

- A shipment reference exists;
- Eligible lines have been handed off;
- Payment state satisfies policy;
- No cancellation is in progress.

You can filter:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-2026-001",
    tenantId: "TENANT-A",
    status: "PACKING",
    paymentStatus: "CAPTURED",
    "fulfillmentStatus": "READY_FOR_HANDOFF"
  },
  {
    $set: {
      status: "SHIPPED",
      fulfillmentStatus: "SHIPPED",
      updatedAt: new Date()
    },
    $inc: { revision: NumberLong("1") }
  }
);
```

However, the shipment record is a separate entity. If a business invariant requires **order status and shipment creation to commit together**, you need a transaction or an event/saga design with intermediate states.

### 16.1. Do Not Promise “Handed to Carrier” Just Because the DB Write Succeeded

Carrier events must be verified via reconcilable APIs/webhooks/references. A DB update alone does not create physical shipping.

## 17. Order Cancellation and Races with Payment

One common race condition:

```text
T1 User clicks Cancel order
T2 Payment provider captures successfully
T3 Cancel service sets status = CANCELLED
T4 Webhook service sets status = PAID
```

If you only `$set` by `_id`, the final outcome depends on whichever message arrives last.

### 17.1. Designing Intermediate States

One approach:

```text
PENDING_PAYMENT
      │
      ├── Request cancel → CANCEL_REQUESTED
      │                         │
      │                         ├── Verify no capture → CANCELLED
      │                         └── Capture found → REFUND_REQUIRED
      │
      └── Capture confirmed → PAID
```

### 17.2. Communicating with the Payment Provider

If the provider supports cancelling a payment intent, you can request cancellation. However, network timeouts leave outcomes uncertain, requiring provider queries or reconciliation by event ID/intent ID.

### 17.3. Never Auto-Refund Multiple Times

Refund commands must carry an idempotency key and check the already-refunded amount. Duplicate webhooks must never trigger a second refund.

## 18. Payments: Separating Order Status and Payment Records

A structure:

```javascript
// payment_attempts
{
  _id: "PAY-ATTEMPT-001",
  tenantId: "TENANT-A",
  orderId: "ORD-2026-001",
  provider: "provider-x",
  providerIntentId: "PI-0001",
  status: "CAPTURED",
  authorizedMinor: NumberLong("660000"),
  capturedMinor: NumberLong("660000"),
  currency: "VND",
  createdAt: ISODate("2026-11-14T04:16:00Z"),
  capturedAt: ISODate("2026-11-14T04:20:00Z")
}
```

The order holds only a **summary/reference**:

```javascript
payment: {
  provider: "provider-x",
  paymentIntentId: "PI-0001",
  capturedMinor: NumberLong("660000")
}
```

Payment attempts and ledgers should also record provider event IDs, operation IDs, method/authorization status, and reconciliation metadata per security policies.

### 18.1. Do Not Store Arbitrary Card Data

Do not copy PAN/CVV/payment secrets into MongoDB just because you “want a snapshot”. Use provider tokens/references in accordance with security standards and applicable regulations.

### 18.2. The Provider Is the Reconciliation Source for Funds

`paymentStatus` on the order should be synchronized via **provider-confirmed events/reconciliation** and payment records, not via a frontend success redirect URL.

## 19. Transaction Boundary #1: Order Document Only

If a business command only needs to modify fields within one order:

```text
Mark order PACKING
  status
  fulfillmentStatus
  revision
  updatedAt
```

A single-document atomic update is usually sufficient. There is no need to open a multi-document transaction just to sound safer.

Advantages:

- Fewer round trips;
- High throughput;
- Fewer timeouts/conflicts;
- Less transaction retry boilerplate;
- Clear invariant boundary.

The precondition is that all data that **must** change together resides in one document and has appropriate authorization/validation.

## 20. Transaction Boundary #2: Multiple Documents in the Same MongoDB

For example:

- Insert order document;
- Insert reservation document;
- Decrement available inventory on a stock document;
- Write an outbox event.

If business logic forbids a state where “an order is created but inventory is not reserved”, you may need a **multi-document transaction** on a supported deployment.

```text
MongoDB transaction
   ├── Insert order
   ├── Decrement available stock (conditional)
   ├── Insert stock reservation
   └── Insert outbox event
Commit / Abort
```

### 20.1. When Do Transactions Apply?

- The invariant genuinely spans multiple documents;
- All data resides in a MongoDB deployment/topology supporting transactions;
- Transaction duration is short;
- Load is suitable;
- Retry logic handles transient conflicts and ambiguous commits;
- No slow external HTTP calls happen while holding the transaction open.

### 20.2. Transactions Are Not the Solution for Every Workflow

An order can live for days; you cannot hold a transaction open from order placement until delivery. Transactions only fit **short** steps with clear commit conditions.

## 21. Java Session Transaction Example

Illustrative structure:

```java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;

import org.bson.Document;

public void createOrderAndOutbox(
    MongoClient client,
    MongoCollection<Document> orders,
    MongoCollection<Document> outbox,
    Document order,
    Document event
) {
    try (ClientSession session = client.startSession()) {
        session.startTransaction();

        try {
            orders.insertOne(session, order);
            outbox.insertOne(session, event);
            session.commitTransaction();
        } catch (RuntimeException ex) {
            session.abortTransaction();
            throw ex;
        }
    }
}
```

This is an **illustrative skeleton**, not production-ready:

- Needs handling for transient transaction errors;
- May need to retry the entire transaction using the appropriate API;
- When commit outcomes are unknown, must distinguish retrying commit vs. retrying the business command;
- Needs appropriate write concern/read concern;
- Guard against duplicate orders/events via stable IDs/unique indexes;
- Never mutate/reuse data with external side effects inside a retry callback.

The MongoDB Java Driver offers version-specific transaction callbacks/helpers, which should generally be preferred to reduce retry boilerplate errors.

### 21.1. A `commitTransaction()` Timeout Does Not Prove Abort

If the server committed but the response was lost on the network, the client does not yet know the outcome. Never create a new order with a fresh ID before checking the stable identity/idempotency contract.

### 21.2. Never Put HTTP Calls Inside a Transaction

Architecturally flawed:

```text
start MongoDB transaction
  insert order
  call payment gateway over HTTP
  wait 30 seconds
  insert payment log
commit
```

If the HTTP call or transaction times out, the external payment may have succeeded while the MongoDB transaction aborts. There is no end-to-end atomicity.

## 22. Inventory Is an Independent Boundary

Each SKU/warehouse has finite inventory contended over by **many different orders**.

```javascript
// inventory
{
  _id: {
    tenantId: "TENANT-A",
    warehouseId: "WH-01",
    sku: "SHIRT-BLUE-M"
  },
  available: NumberLong("10"),
  reserved: NumberLong("0"),
  sold: NumberLong("0"),
  revision: NumberLong("20")
}
```

Inventory data should not be embedded wholesale into orders because individual orders do not own shared inventory.

### 22.1. Read-Then-Write Is Wrong Under Contention

```text
Order A reads available = 1
Order B reads available = 1
Order A places order for 1 item
Order B places order for 1 item
```

If both read first and update later, overselling can occur.

### 22.2. Conditional Update on One Stock Document

```javascript
const r = db.inventory.updateOne(
  {
    _id: {
      tenantId: "TENANT-A",
      warehouseId: "WH-01",
      sku: "SHIRT-BLUE-M"
    },
    available: { $gte: NumberLong("2") }
  },
  {
    $inc: {
      available: NumberLong("-2"),
      reserved: NumberLong("2"),
      revision: NumberLong("1")
    }
  }
);

if (r.matchedCount !== 1) {
  print("Insufficient stock or stock record does not exist");
}
```

The filter and `$inc` execute atomically on **this stock document**, preventing two commands from consuming the same `available` stock once depleted per the filter condition.

### 22.3. Stock Documents Becoming Hotspots

If thousands of orders contend for one popular SKU, a single stock document can suffer write contention. You may need warehouse/bucket allocation, queues, a dedicated reservation service, or another design, while preserving global invariants and anti-oversell guarantees.

## 23. Separate Reservations Solve Expiration and Release

A reservation record:

```javascript
{
  _id: "RES-ORD-2026-001-L1-WH01",
  tenantId: "TENANT-A",
  orderId: "ORD-2026-001",
  lineId: "L1",
  warehouseId: "WH-01",
  sku: "SHIRT-BLUE-M",
  quantity: NumberLong("2"),
  status: "HELD",
  expiresAt: ISODate("2026-11-14T04:30:00Z")
}
```

Reservation states:

```text
HELD → COMMITTED
  │
  └── RELEASED / EXPIRED
```

### 23.1. A Reservation Is a Temporary Hold

It holds stock for an order pending payment completion per policy; it does not mean the goods are sold and delivered.

### 23.2. When to Release?

- Checkout is cancelled;
- Payment intent timeout is verified;
- User abandons checkout;
- Fraud review rejects the order;
- Order moves to a state permitting reservation release.

### 23.3. Releases Must Be Idempotent

If a cancellation webhook arrives twice, never add back `available` twice. Use a reservation state guard:

```text
HELD → RELEASED : release stock exactly once
RELEASED → RELEASED : no-op
COMMITTED → RELEASED : only as permitted by business rules
```

With reservations and stock in two documents, use a transaction or a ledger/outbox/reconciliation mechanism to avoid releasing one side without updating the other.

## 24. TTL Does Not Automatically Restore Inventory

A common mistake:

```javascript
db.stock_reservations.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
```

and assuming MongoDB deletes the reservation immediately and automatically increments `inventory.available`.

TTL only performs **background deletion of eligible documents**; it does not update stock documents. Deleting the reservation can even destroy the evidence needed to restore stock.

### 24.1. A Better Design

- Keep reservation records with status/expiry;
- A scheduler or worker claims expired reservations;
- Conditionally transition `HELD → EXPIRED`;
- Within the same appropriate transaction, restore stock and record an event;
- Purge historical records only after a separate retention period.

TTL can apply to **completed records** no longer needed for reconciliation, per compliance policies.

### 24.2. Time-Based Expiration Is Not Millisecond-Exact

Do not rely on the TTL monitor as a clock guaranteeing instant release. Business logic must check `expiresAt` at processing time when needed.

## 25. Transaction Boundary #3: MongoDB and the Payment Provider

A payment provider does not participate in your application's MongoDB transaction:

```text
MongoDB order update ──────┐
                           ├── No built-in distributed atomic commit
External payment capture ─┘
```

Scenarios:

1. DB commit succeeds, HTTP payment fails.
2. HTTP payment succeeds, DB update fails.
3. Both succeed, but the process crashes before ACK.
4. Provider sends the webhook twice.
5. Webhook arrives before the HTTP response.
6. User cancels while capture is in flight.

Correctness depends on **orchestration, idempotency, durable events, and reconciliation**, not an imaginary database transaction spanning everything.

## 26. Saga: Workflows with Compensating Actions

A simple saga:

```text
Create PENDING_PAYMENT order
           │
           ▼
Reserve inventory
           │
           ▼
Request payment authorization/capture
      ┌────┴─────┐
   Success      Failure
      │            │
      ▼            ▼
 Mark PAID      Release reservation
      │            │
      ▼            ▼
 Confirm stock  Mark failed/cancelled
```

If payment was captured yet stock is unavailable, the saga may have to **refund** rather than “rolling back” an external payment via MongoDB abort.

### 26.1. Compensation Is Not a Transaction Rollback

Compensation is a new business action:

- Payment capture → refund;
- Inventory hold → release;
- Shipment label created → cancel shipment (if provider permits);
- User notification sent → cannot be completely “undone”, requires sending a follow-up correction notice.

Never assume every external side effect has a clean inverse compensation.

### 26.2. Sagas Must Have Durable State

Persist workflow ID, current step, command/event IDs, attempt count, deadline, and last error. If a process crashes, another worker can resume from the committed state.

### 26.3. Never Retry Permanent Failures Infinitely

For example, invalid payment credentials or fraud-rejected orders need a clear failure state. Transient timeouts can be retried up to a limit with backoff and outcome verification before sending a fresh request.

## 27. Transactional Outbox: Bridging DB Transactions and Message Delivery

An anti-pattern:

```text
1. orders.insertOne()
2. messageBroker.publish("OrderCreated")
```

If the process dies after step 1, the event is never published. If the broker receives the event but the response is lost, an app retry may publish a duplicate.

**Transactional outbox** persists the event in MongoDB inside the same transaction as the business change, and a dispatcher then sends it to the broker.

```text
MongoDB transaction
     ├── Insert/Update order
     └── Insert outbox event
             │
          COMMIT
             │
             ▼
       Outbox dispatcher
             │
             ▼
       Message broker / service
             │
             ▼
       Consumer idempotency
```

### 27.1. Outbox Document Example

```javascript
{
  _id: "evt-ORD-2026-001-paid-v8",
  tenantId: "TENANT-A",
  aggregateType: "Order",
  aggregateId: "ORD-2026-001",
  aggregateRevision: NumberLong("8"),
  eventType: "OrderPaid",
  eventVersion: 2,
  occurredAt: ISODate("2026-11-14T04:20:00Z"),
  payload: {
    orderId: "ORD-2026-001",
    amountMinor: NumberLong("660000"),
    currency: "VND"
  },
  state: "PENDING",
  attempts: 0
}
```

Do not copy the entire order snapshot containing addresses/PII into the event if downstream consumers only need order ID and amount.

### 27.2. Outbox Does Not Guarantee System-Wide Exactly-Once

A dispatcher can publish successfully and crash before marking `SENT`; upon restart it may publish the event again. Consumers must deduplicate by event ID or process idempotently.

### 27.3. Outbox Lifecycle

```text
PENDING → CLAIMED → SENT
             │
             └── RETRY / DEAD_LETTER
```

Requires claim leases/ownership, retry limits, backoff, alerts, retention cleanup, and metrics.

## 28. Order + Outbox Transaction Example

Java Sync Driver structure:

```java
try (ClientSession session = client.startSession()) {
    session.startTransaction();

    try {
        UpdateResult transition = orders.updateOne(
            session,
            Filters.and(
                Filters.eq("_id", orderId),
                Filters.eq("tenantId", tenantId),
                Filters.eq("status", "PENDING_PAYMENT"),
                Filters.eq("revision", expectedRevision)
            ),
            Updates.combine(
                Updates.set("status", "PAID"),
                Updates.inc("revision", 1L),
                Updates.currentDate("updatedAt")
            )
        );

        if (transition.getMatchedCount() != 1) {
            throw new IllegalStateException("Order transition conflict");
        }

        outbox.insertOne(
            session,
            new Document("_id", eventId)
                .append("tenantId", tenantId)
                .append("aggregateId", orderId)
                .append("eventType", "OrderPaid")
                .append("aggregateRevision", expectedRevision + 1)
                .append("state", "PENDING")
                .append("createdAt", new java.util.Date())
        );

        session.commitTransaction();
    } catch (RuntimeException ex) {
        session.abortTransaction();
        throw ex;
    }
}
```

`client`, `orders`, `outbox`, `orderId`, `tenantId`, `expectedRevision`, and `eventId` are pre-initialized and validated application variables; proper session/transaction retry logic is required, so do not use this snippet directly as a complete program.

### 28.1. Is a Transaction Needed?

If the order update and event insert **must** commit together, a transaction is the clearest choice in a supported MongoDB deployment. Another option is embedding a small outbox marker inside the order document for a dispatcher to extract, though size, ordering, and lifecycle must be managed.

### 28.2. Never Send Messages Inside an Auto-Retried Callback

If a transaction helper retries its callback, calling a payment provider or message broker directly inside the callback can send duplicate external side effects. Callbacks should only contain safely retriable DB operations.

## 29. What Role Do Change Streams Play?

MongoDB change streams let consumers receive events about committed changes according to supported semantics and topology.

They can be used to:

- Update read models;
- Synchronize search;
- Detect order status changes;
- Implement certain forms of CDC;
- Assist outbox dispatching.

However:

- Change stream events can be reprocessed during retries/resumes;
- Resume tokens must be saved only after downstream application succeeds;
- Oplog window/retention limits resume capability;
- They do not equate to an infinite durable business event log;
- Consumers may need initial snapshots and reconciliation;
- They do not automatically provide end-to-end exactly-once guarantees.

### 29.1. Outbox and Change Streams Complement Each Other

A design might look like:

```text
MongoDB transaction → outbox collection
                           │
                      change stream
                           │
                       dispatcher
                           │
                       message broker
```

The outbox retains durable event state and retry metadata, while the change stream enables near-real-time change detection. Have a recovery plan if a consumer falls outside the oplog window.

## 30. Checkout and Order Creation Idempotency

A user clicks “Place Order” twice or an HTTP request is retried.

If every request generates a new `_id`:

```text
Request 1 → Order A
Request 2 → Order B
```

duplicate orders, duplicate stock holds, and double payment calls can occur.

### 30.1. Stable Idempotency Key

The client sends a unique key per checkout attempt; the server binds it to:

- Tenant/customer;
- Request fingerprint/canonical payload;
- Order ID;
- Processing state;
- Expiry/retention;
- Result reference.

Example:

```javascript
{
  tenantId: "TENANT-A",
  idempotencyKey: "checkout-8d2f...",
  orderId: "ORD-2026-001",
  payloadHash: "sha256:...",
  status: "COMPLETED"
}
```

### 30.2. Unique Constraint

If using a `checkout_requests` collection:

```javascript
db.checkout_requests.createIndex(
  { tenantId: 1, idempotencyKey: 1 },
  { unique: true, name: "uq_tenant_checkout_key" }
);
```

Do not rely on two requests both checking “does not exist yet” and then inserting safely. A unique constraint prevents races at the database level.

### 30.3. Same Key, Different Payload

If an idempotency key was already used for a different cart, the service must not return “success” for the new content. Verify the canonical payload hash and return a conflict per contract.

### 30.4. Retention Must Be Long Enough

An idempotency record expiring too early can let an old request create a duplicate. Retention depends on payment/provider retry windows, business policy, and compliance.

## 31. Webhook Idempotency

Payment providers frequently resend webhooks if they do not receive an ACK, and events may arrive out of the expected order.

An event record:

```javascript
{
  _id: "provider-x:event-0001",
  tenantId: "TENANT-A",
  provider: "provider-x",
  eventType: "payment.captured",
  providerIntentId: "PI-0001",
  receivedAt: ISODate("2026-11-14T04:20:01Z"),
  processingStatus: "PROCESSED"
}
```

### 31.1. Verify Events Before Writing

- Verify the signature from the provider;
- Check timestamp/replay window per the provider API;
- Check tenant/account mapping;
- Correlate the order/payment intent;
- Verify amount/currency;
- Persist the event ID/deduplication key;
- Transition state conditionally;
- Return ACK per protocol only after persisting state durably.

### 31.2. Duplicate Events Must Not Increment Captured Amount Again

An unsafe pattern:

```javascript
{ $inc: { "payment.capturedMinor": amount } }
```

if every duplicate webhook executes it again. Rely on unique payment records/operation IDs or update idempotently to the verified confirmed state.

### 31.3. Out-of-Order Events

If a “refunded” event arrives before “captured” due to delivery delay, do not necessarily reject it permanently. Hold it pending reconciliation and query the provider as the source of truth, rather than overwriting state with “whichever network event arrived last”.

## 32. Accounting Ledgers and Audits Differ from Order Status

An order may:

- Capture 660000;
- Refund 100000;
- Refund another 560000;
- Have separate fees and settlement entries.

A bare `paymentStatus = "REFUNDED"` cannot explain all financial movements.

An append-only ledger structure:

```javascript
{
  _id: "LEDGER-0001",
  tenantId: "TENANT-A",
  orderId: "ORD-2026-001",
  paymentAttemptId: "PAY-ATTEMPT-001",
  providerOperationId: "CAPTURE-001",
  entryType: "CAPTURE",
  amountMinor: NumberLong("660000"),
  currency: "VND",
  recordedAt: ISODate("2026-11-14T04:20:00Z")
}
```

A refund:

```javascript
{
  _id: "LEDGER-0002",
  tenantId: "TENANT-A",
  orderId: "ORD-2026-001",
  providerOperationId: "REFUND-001",
  entryType: "REFUND",
  amountMinor: NumberLong("100000"),
  currency: "VND",
  recordedAt: ISODate("2026-11-15T02:00:00Z")
}
```

### 32.1. Do Not Mutate Financial History Arbitrarily

If corrections are needed, record adjustment/offsetting entries per policy with audit trails. Official financial ledgers may require double-entry bookkeeping, reconciliation, immutability, and stricter access controls than this example.

### 32.2. Snapshot Totals Differ from Net Collected Totals

```text
Order grandTotal: 660000
Captured: 660000
Refunded: 100000
Net captured: 560000
```

All three figures carry distinct meaning; never overwrite `grandTotal` to 560000 after a refund, as that erases the original commitment.

## 33. Partial Refunds

When refunding only one line or partial quantity, determine:

- Line ID and quantity being refunded;
- Snapshot unit price;
- Discount and tax allocation;
- Shipping refund policy;
- Remaining captured amount eligible for refund;
- Previous refunds;
- Provider refund ID;
- Return/quality checks.

### 33.1. Do Not Calculate Refunds from the Live Catalog

If the product price increased, refunding at the current price is wrong. Use the order snapshot and the applicable refund policy.

### 33.2. Preventing Refunds Exceeding Total Capture

An invariant:

\[
\sum \text{refundSuccessfulMinor} \leq \text{capturedMinor}
\]

Under concurrent refunds, checking in Java and calling the provider separately lets two requests exceed the cap together. Use a refund amount reservation/authorization via CAS/transaction alongside provider idempotency, and reconcile with the provider.

### 33.3. A Refund Does Not Mean Cancelling the Order

A delivered order may be partially refunded during a return workflow. Do not force the entire order status to `CANCELLED` when only one line is refunded.

## 34. Partial Shipments

An order has two lines: one has shipped, while the other lacks stock.

Having only:

```javascript
fulfillmentStatus: "SHIPPED"
```

can be misleading.

Design:

```text
NOT_STARTED
ALLOCATED
PARTIALLY_SHIPPED
SHIPPED
PARTIALLY_DELIVERED
DELIVERED
RETURN_IN_PROGRESS
```

And shipment records:

```javascript
{
  _id: "SHIP-001",
  tenantId: "TENANT-A",
  orderId: "ORD-2026-001",
  lines: [
    { lineId: "L1", shippedQuantity: 1 }
  ],
  carrierCode: "CARRIER-X",
  trackingReference: "TRACK-001",
  status: "IN_TRANSIT"
}
```

### 34.1. Per-Line Invariant

```text
shippedQuantity(line) <= orderedQuantity(line) - cancelledQuantity(line)
```

If reshipments, lost shipments, or returns exist, extend the model rather than blindly adding/subtracting without context.

### 34.2. Shipment Events Can Arrive Late or Duplicate

Carrier webhooks must be deduplicated by event ID, preventing delivery status from regressing from `DELIVERED` back to `IN_TRANSIT` if a stale event arrives late.

## 35. How to Store State Transition History?

There are three common options.

### 35.1. Store Only the Current State

```javascript
{
  status: "PAID",
  updatedAt: ISODate("...")
}
```

Simple, but difficult to audit when you need to know the previous state and who triggered the change.

### 35.2. Embed a Small Bounded History

```javascript
{
  status: "PAID",
  recentTransitions: [
    {
      from: "CREATED",
      to: "PENDING_PAYMENT",
      eventId: "E1",
      at: ISODate("...")
    },
    {
      from: "PENDING_PAYMENT",
      to: "PAID",
      eventId: "E2",
      at: ISODate("...")
    }
  ]
}
```

Suitable when only a few recent events are needed. Never append unboundedly: documents have a BSON limit, and every update to a hot document carries a cost.

### 35.3. Separate Events Collection

```javascript
{
  _id: "ORD-2026-001:REV-8",
  tenantId: "TENANT-A",
  orderId: "ORD-2026-001",
  revision: NumberLong("8"),
  fromStatus: "PENDING_PAYMENT",
  toStatus: "PAID",
  causeEventId: "provider-x:event-0001",
  occurredAt: ISODate("...")
}
```

Can be written inside a transaction alongside the order update to maintain consistency between the summary and history when required by invariants.

### 35.4. Event Sourcing Is Optional

Storing event history does not force full event sourcing. Event sourcing requires the event log to be the source of truth, projection replay/versioning, and event schema migrations. For many products, an order document + audit/outbox is far easier to operate.

## 36. Document Size and Unbounded Arrays

MongoDB enforces a BSON document size limit (typically 16 MiB in standard versions); an order with 10 line items differs vastly from an order with 100,000 lines.

Review:

- Maximum line items per business rules;
- Snapshot size per line;
- Gift messages/comments;
- Audit entries;
- Discount allocations;
- Fulfillment events;
- Provider payloads;
- Images/blobs.

### 36.1. Avoid Unbounded Embedded Data

Unbounded arrays such as `paymentAttempts`, `webhookEvents`, `statusHistory`, and `trackingEvents` belong in separate collections or a bounded summary mechanism.

### 36.2. Bound Order Lines by Domain

If marketplace orders can have hundreds of thousands of lines, you may need a separate `order_lines` collection and a different transaction/read model. Do not wait for MongoDB limits to tell you the model is broken.

### 36.3. Do Not Store Binary Image Files in Order Snapshots

Store a controlled identifier/URL or immutable asset reference to avoid bloating orders and depending on short-lived expiring URLs.

## 37. Reading Orders: Projections and Data Access Patterns

An order list page typically needs:

```text
orderId
placedAt
status
grandTotal
currency
itemCount
preview items (1–2 lines)
```

It does not need full shipping addresses, payment attempts, or audit events.

### 37.1. Projections in `mongosh`

```javascript
db.orders.find(
  {
    tenantId: "TENANT-A",
    customerId: "CUS-102"
  },
  {
    orderNo: 1,
    placedAt: 1,
    status: 1,
    currency: 1,
    "pricing.grandTotalMinor": 1,
    "items.snapshot.name": 1
  }
)
.sort({ placedAt: -1, _id: -1 })
.limit(20);
```

For large items arrays, consider `$slice` projections or storing a list summary field instead of reading every line name.

### 37.2. Detail View

Order detail views can read the entire snapshot, while out-of-aggregate data such as shipment tracking or payment attempts should be fetched via dedicated services/repositories with proper permissions.

### 37.3. Never Join the Catalog to Reconstruct History

You may query the catalog to display currently available products or reorder links, but prices and names in order records must come from the snapshot per contract.

## 38. Indexes for Order Workloads

Common queries:

```javascript
// Find one order for a tenant
db.orders.findOne({
  tenantId: "TENANT-A",
  _id: "ORD-2026-001"
});

// History by customer
db.orders.find({
  tenantId: "TENANT-A",
  customerId: "CUS-102"
}).sort({ placedAt: -1, _id: -1 }).limit(20);

// Pending orders
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID"
}).sort({ placedAt: 1 }).limit(100);
```

Candidate indexes:

```javascript
db.orders.createIndex(
  { tenantId: 1, customerId: 1, placedAt: -1, _id: -1 },
  { name: "idx_tenant_customer_recent_orders" }
);

db.orders.createIndex(
  { tenantId: 1, status: 1, placedAt: 1 },
  { name: "idx_tenant_status_queue" }
);

db.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  { unique: true, name: "uq_tenant_order_no" }
);
```

Do not create all of them blindly just because they appear in examples; use `explain("executionStats")` and measure p95/p99, index size, and write maintenance overhead.

### 38.1. The `_id` Index Already Exists

MongoDB creates an index on `_id` by default. If IDs are globally unique, `_id` lookups are very efficient, though the application must still verify tenant/authorization. You may not need an extra `{tenantId,_id}` index unless workload and sharding constraints require it.

### 38.2. Queue Indexes Can Be Partial

If most orders are completed and workers only poll `status: "PAID"`, a partial index reduces index footprint:

```javascript
db.orders.createIndex(
  { tenantId: 1, placedAt: 1 },
  {
    name: "idx_paid_order_queue",
    partialFilterExpression: { status: "PAID" }
  }
);
```

Queries must imply the partial index filter so the planner can safely use it without missing results.

### 38.3. Unique Indexes Are a Business Contract

Do not rely solely on application-level `existsByOrderNo` checks before inserting, because concurrent requests can pass the check together. Unique constraints combined with idempotency block duplicates at the database layer.

## 39. Sharding: Choosing Keys by Query Patterns and Distribution

If order volume grows massive, sharding may be needed. Consider:

- Queries mostly filter by tenant and order ID;
- Few tenants vs. many tenants;
- One giant tenant vs. even distribution;
- Write rate over time;
- Historical query/sort patterns;
- Unique orderNo/idempotency constraints;
- Cross-shard transaction costs;
- TTL/archival policies.

### 39.1. Do Not Default to Shard Key `{tenantId:1}`

If one tenant is huge, all of its orders can create a hotspot or distribute poorly. If sharding by monotonically increasing `createdAt`, a hotspot can form on the shard receiving current writes. Analyze distribution and query targeting.

### 39.2. Unique Indexes and Shard Keys

MongoDB sharded collections impose **specific constraints on unique indexes and shard keys**. Do not assume any `{tenantId,orderNo}` index can be created as unique under any shard key. Check the documentation for your MongoDB Server version and specific data model.

### 39.3. Cross-Shard Transactions Have Costs

A transaction updating an order on shard A and stock on shard B incurs more coordination and resource overhead than single-shard or single-document operations. Do not pick shard keys that turn every checkout into a distributed transaction when avoidable without breaking the model.

### 39.4. Do Not Optimize Solely for Inserts

Orders are also read by customer, status queues, refunds, and audits. Choosing a shard key must balance write distribution, query targeting, growth, and administrative operations.

## 40. Schema Validation for Order Documents

MongoDB supports collection validators based on `$jsonSchema` to prevent malformed types and shapes.

Conceptual example:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: [
      "tenantId",
      "status",
      "currency",
      "items",
      "pricing",
      "revision"
    ],
    properties: {
      tenantId: { bsonType: "string" },
      status: {
        enum: [
          "CREATED",
          "PENDING_PAYMENT",
          "PAID",
          "PACKING",
          "SHIPPED",
          "DELIVERED",
          "CANCELLED",
          "CANCEL_PENDING_REFUND",
          "REFUNDED"
        ]
      },
      currency: { bsonType: "string" },
      items: {
        bsonType: "array",
        minItems: 1
      },
      revision: { bsonType: "long" },
      pricing: {
        bsonType: "object",
        required: ["grandTotalMinor"],
        properties: {
          grandTotalMinor: { bsonType: "long" }
        }
      }
    }
  }
}
```

This is a schema shape example and does not cover every additional status mentioned earlier. In production, select an **enum consistent with the real state machine**, version the schema, and test it.

### 40.1. Validators Do Not Replace Workflow Rules

MongoDB `$jsonSchema` can verify `status` belongs to an enum, but it does not know whether `SHIPPED` can transition to `CANCELLED`. You still need CAS, transactions, and domain service logic.

### 40.2. Strict Schemas Can Impact Legacy Records

If older records store `revision` as Int32 or omit `pricing`, enabling strict validation can cause updates to fail. Use expand-and-contract, backfills, and staged validator rollouts.

### 40.3. Do Not Use Validators Instead of Authorization

A validator does not stop a user in tenant A from writing an order for tenant B. Permissions and tenant context must be enforced at the service/database access boundary.

## 41. Access Control and Sensitive Data

Orders commonly contain:

- Recipient name and address;
- Phone number;
- Customer information;
- Transaction value;
- Personal item details;
- Tracking references;
- Delivery notes.

### 41.1. Separating Views by Role

| Role | Information typically visible |
|---|---|
| Buyer | Their own orders |
| Seller | Line items they are responsible for fulfilling |
| Warehouse | SKU, quantity, required shipping address/label |
| Carrier | Minimal delivery details |
| Accounting | Amounts, taxes, payment/ledger references |
| Customer support | Status and fields needed for the ticket |
| Operations admin | Audited access per role, not all PII by default |

In multi-seller marketplaces, one order can hold items from multiple sellers. Do not return full customer addresses/payment data or another seller's line items if policy forbids it.

### 41.2. Potential Conflict Between Snapshots and Retention

Some records must be retained for reconciliation/invoicing, while PII must be deleted/masked per laws and policies once its purpose ends. Design field-level encryption, retention, pseudonymization, or separate encrypted address documents/references where appropriate.

### 41.3. Never Log Full Orders

A safer log entry:

```text
traceId
tenant scope (per policy)
orderId
transitionFrom
transitionTo
revision
paymentEventId
errorCode
elapsedMs
```

Avoid logging raw recipient addresses, payment tokens, API credentials, or full webhook bodies.

## 42. TTL and Order Deletion

Never attach a TTL index directly to `orders.placedAt` just because you “want to clean up old data” without an explicit retention policy.

TTL on orders can erase:

- Records legally required for retention;
- Data needed for refunds/chargebacks;
- Business audit trails;
- Records under active disputes;
- Ledger reconciliation evidence.

A structured strategy:

```text
Active orders
     │
     ▼
Closed + retention eligible
     │
     ▼
Archive/export under policy
     │
     ▼
Integrity/audit confirmation
     │
     ▼
Delete or anonymize according to requirements
```

### 42.1. TTL Fits Temporary Data Better

Expired quotes, deduplication caches, or temporary checkout sessions can use TTL when a clear deletion policy exists and correctness is unaffected. TTL deletion is **asynchronous**, so business expiration must still be enforced in application logic.

## 43. CQRS and Materialized Read Models

If reporting needs daily order totals by tenant and status, you do not need to scan all orders every time.

You can maintain a read model:

```javascript
{
  _id: {
    tenantId: "TENANT-A",
    day: "2026-11-14",
    status: "PAID"
  },
  orderCount: NumberLong("1000"),
  grossMinor: NumberLong("660000000"),
  computedAt: ISODate("...")
}
```

### 43.1. Read Models Are Not the Source of Truth for Payments

This is a projection that can lag and can be rebuilt from orders/ledgers/events per contract. Do not use reporting totals from a read model to assert that a payment provider has settled funds accurately.

### 43.2. Rebuilds Need Idempotency

If a consumer replays an event twice, `$inc` on order counts can double-count. Deduplicate events or rebuild by recomputing and applying `$set` to a verified state.

### 43.3. Eventual Consistency Is an Explicit Choice

The application must decide which views tolerate a few seconds of lag and which must read directly from the source of truth—such as verifying payment status before shipping.

## 44. Correctness Under Retries and Unknown Outcomes

Hard scenarios:

| Scenario | Risk | Mitigation |
|---|---|---|
| Client timeout after order insert | Creating a second order | Stable order/idempotency key |
| MongoDB commit succeeds, response lost | Retrying business action twice | Read-after-retry/reconcile |
| Payment capture succeeds, callback lost | Order remains pending | Provider reconciliation |
| Duplicate webhook | Double PAID/duplicate ledger | Unique provider event/operation ID |
| Inventory release retried | Restoring stock twice | Reservation state transition guard |
| Outbox publish succeeds, marker fails | Event re-sent | Consumer deduplication |
| Out-of-order shipment webhook | State regression | Version/event-time state rules |
| Refund timeout | Duplicate refund | Provider idempotency + ledger reconciliation |
| Partial stock allocation | Partially reserved order | Transaction or compensation |
| Order snapshot write error | Price recalculated | Immutable quote ID and retry contract |

### 44.1. Retryable Writes Do Not Mean Exactly-Once Business Execution

The MongoDB Driver provides retryable writes for eligible operations at the protocol level. However, retries at the HTTP layer or job level with a new request ID can still create duplicate effects. Business-level idempotency remains essential.

### 44.2. Do Not Turn Timeouts into “Failures” Prematurely

A timeout is an **unknown outcome** whenever the command or provider might have processed it. Use reconciliation states and stable request/event identities.

## 45. Incident: `PAID` Without Reserved Stock

A broken flow:

```text
1. Capture payment
2. Create order
3. Decrement inventory
4. Inventory insufficient
```

At this point, money was taken with no stock available.

### 45.1. An Alternative Workflow

```text
1. Validate quote
2. Create PENDING_PAYMENT order + reserve stock
3. Request payment
4. On verified success, commit reservation
5. On failure/expiry, release stock
```

This workflow lowers the risk but does not eliminate every edge case: payment might succeed after expiration or reservation release. The saga needs refund/backorder policies and reconciliation.

### 45.2. Never Hold a Stock Reservation Inside a Long MongoDB Transaction Waiting for Payment

Transactions have timeouts and overhead, making them unsuitable for waiting while a customer completes OTP or a provider sends a callback. Persist the reservation durably **in a short transaction**, then process payment asynchronously.

## 46. Incident: `CANCELLED` When a Payment Callback Arrives Later

Investigate:

1. Did the payment provider authorize/capture?
2. Which order transition committed first?
3. Did the cancel path request provider cancellation?
4. Was a refund created/idempotent?
5. Under what state was the reservation released?
6. What are the event IDs and sequences/watermarks?
7. Was the customer notification accurate?

A domain-dependent resolution:

```text
CANCELLED + capture confirmed
       │
       ▼
REFUND_REQUIRED
       │
       ▼
Provider refund request with stable key
       │
       ▼
REFUND_CONFIRMED
       │
       ▼
CLOSED
```

Do not flip the order back to `PAID` just because the capture webhook arrived last; a compensating state may be required.

## 47. Incident: Historical Prices Changed

Symptom: the old order detail page shows a different total than the issued invoice.

Typical causes:

- UI joins the catalog and reads live `product.price`;
- Backend recomputes pricing from current promotions;
- Snapshot omitted tax/shipping allocations;
- Monetary data suffered wrong type conversion;
- Refund overwrote the original grand total;
- Unbounded embedded item updates regardless of status;
- Query projection omitted part of the snapshot.

### 47.1. Resolution

- Stop displaying/recalculating from the live catalog where it violates the contract;
- Preserve original confirmed data/invoices;
- Reconcile snapshots against payments/ledgers;
- Fix the read path instead of randomly mutating historical orders;
- If snapshots are missing, recover from backed-up sources/evidence;
- Add a test verifying “changing catalog price after order placement does not alter the order”.

## 48. Schema Versioning and Migration

An order can live for years while the application evolves its schema.

Example:

```text
Schema v1:
  amountTotal: double

Schema v2:
  grandTotalMinor: long
  currency: string

Schema v3:
  pricing: { subtotal, tax, discount, grandTotal }
```

### 48.1. Do Not Assume Every Version Has New Fields

Readers require:

- Schema version;
- Backward-compatible mappers;
- Default values only when justified;
- Explicit migrations;
- Data backfills;
- Tests with historical fixtures.

### 48.2. Expand-and-Contract

```text
Add new fields (backward compatible)
      │
Deploy dual-readable code
      │
Backfill existing orders
      │
Reconcile amounts
      │
Switch reads to new schema
      │
Remove old fields after rollback window
```

For commercial data, never convert a Double to decimal and claim original precision was restored if the Double source was already rounded.

### 48.3. Do Not Alter Snapshots Because a Product Was Renamed

A schema migration can restructure a field from `snapshot.productName` to `snapshot.name`, yet **must never change the economic content** of the snapshot.

## 49. Testing Single-Document Atomic Transitions

A staging scenario:

```text
Order status = PAID, revision=8

Worker A:
  PACKING if PAID and rev=8

Worker B:
  CANCEL_REQUESTED if PAID and rev=8
```

Expected:

- At most one transition matches revision 8;
- Revision after success = 9;
- The other worker receives a conflict;
- The losing worker re-reads and acts per the state machine;
- No inconsistent `status` vs. payment/fulfillment fields.

### 49.1. Tests Need Real Concurrency

Single-threaded unit tests do not catch races. Run integration tests against a MongoDB test deployment firing concurrent requests with the same revision and verify invariants.

### 49.2. Retry Test Cases

- Same command ID sent twice;
- Timeout after commit;
- Duplicate webhook;
- Worker restart;
- Network disconnect;
- Primary election in a test environment;
- Out-of-order carrier events.

## 50. Testing Transaction Boundaries

A test for order + reservation + stock + outbox:

1. Capture initial state.
2. Seed sufficient stock.
3. Run a successful transaction.
4. Verify order, reservation, stock, and event all appear together.
5. Intentionally inject an error mid-operation in staging.
6. Verify transaction abort leaves no half-written state.
7. Test transient errors/retries.
8. Test unknown commit outcomes where the test harness allows.
9. Verify idempotency and unique constraints.

### 50.1. Never Test by Deleting Production Data

Fault injection requires isolated environments, mock fixtures, and proper permissions.

### 50.2. Do Not Forget External Effects

A MongoDB transaction test does not prove the payment provider will not double-charge. Test saga/payment idempotency separately using a sandbox provider or mock simulating timeouts and duplicates.

## 51. Testing Totals and Snapshot Immutability

Tests should cover:

- Catalog price changes after order placement;
- Product deleted/hidden after order placement;
- Discount ends;
- Tax policy changes;
- Shipping quote expires;
- Large quantities and Int64 overflow;
- Different currencies;
- Partial refund;
- Cancelling one line;
- Decimal/rounding;
- Legacy data missing allocations;
- Same SKU across variants;
- Multi-tenant same orderNo.

Expected: historical orders still reflect the **accepted quote/snapshot**, and any adjustments carry separate audit trails.

## 52. Load and Contention Testing

Orders are typically read-heavy and updated infrequently, whereas hot-SKU stock can be heavily updated.

Metrics:

```text
Checkout success rate
Order creation p95/p99
State transition conflict rate
Payment reconciliation lag
Reservation expiry backlog
Oversell anomaly count
Order duplicate count
Outbox pending age
CDC lag
MongoDB transaction abort/retry count
Stock document write contention
CPU/IO/cache/replication lag
```

### 52.1. Managing Hot Keys

If all flash-sale orders contend on a single stock document, CAS prevents overselling but can spike write latency and contended retries. This requires capacity planning, queuing/throttling, inventory partitioning, or adjusting reservation policies.

### 52.2. Do Not Increase Batch Size and Concurrency Unboundedly

A background worker processing 100,000 refunds/tracking updates concurrently can cause pool contention and degrade checkout p99. Bounded queues and rate limits protect SLOs.

## 53. End-to-End Checkout Flow

Diagram:

```text
Client
  │
  ├── 1. GET quote
  │       └── Server calculates totals
  │
  └── 2. POST checkout + idempotencyKey
             │
             ▼
       Validate quote/tenant
             │
             ▼
       MongoDB short transaction
         ├── Claim/create checkout request
         ├── Create PENDING_PAYMENT order (snapshot)
         ├── Conditionally reserve inventory
         └── Write outbox PaymentRequested
             │
             ▼
       Commit
             │
             ▼
       Worker calls payment provider (outside transaction)
             │
             ▼
       Provider webhook/response
             │
             ▼
       Verify + dedupe + reconcile
             │
             ▼
       MongoDB short transaction
         ├── Update order with CAS
         ├── Record payment attempt/ledger
         ├── Commit reservation as applicable
         └── Outbox OrderPaid / PaymentFailed
             │
             ▼
       Fulfillment consumes event
             │
             ▼
       Shipment with own state and retries
```

### 53.1. Reservations Can Be Split into a Separate Saga

In deployments with multiple warehouses or an independent inventory service, the reserve step may not share a MongoDB transaction with the order. In that case, use outbox/saga with compensation and timeouts. Do not force services on separate clusters into a single MongoDB transaction.

### 53.2. Request Idempotency and Provider Idempotency Differ

Stable IDs are required at both layers:

```text
checkout idempotency key
order ID
stock reservation ID
payment provider idempotency key
payment attempt ID
webhook provider event ID
outbox event ID
shipment request ID
refund request ID
```

Each ID protects against a different class of retries and concurrency.

## 54. Cancellation Flow with Unknown Payment Outcome

```text
User asks cancel
       │
       ▼
CAS order → CANCEL_REQUESTED
       │
       ▼
Check payment provider state
       │
       ├── Not captured
       │     └── Cancel payment intent
       │           └── Release reservation
       │                 └── CANCELLED
       │
       ├── Captured
       │     └── Request refund with stable key
       │           └── REFUND_PENDING
       │                 └── On confirmed refund → CANCELLED/CLOSED
       │
       └── Unknown
             └── RECONCILIATION_REQUIRED
                    └── Query/retry safely
```

Never tell the user “Cancelled and refunded” without provider evidence. The UI can display “Processing cancellation/refund” per the domain contract.

## 55. Design Decision Table

| Question | Usually appropriate choice |
|---|---|
| Where do product details in an order come from? | Confirmed snapshot on the order |
| Current product details? | Catalog reference |
| Prices and currency? | Snapshot, clear units and rounding |
| Order with few line items? | Embed items |
| Thousands of line items with independent updates? | Consider separate order_lines |
| Transitioning one status on one order? | Atomic conditional update/CAS |
| Order and outbox must commit together? | MongoDB transaction or single-document design |
| Order and stock in the same MongoDB? | Transaction if cross-doc invariant exists |
| Calling payment gateway? | Saga/outbox/idempotency, no open MongoDB tx |
| Shared inventory? | Independent collection/service, conditional decrement |
| Expiring reservations? | Expiry worker + idempotent release; do not rely on TTL |
| Duplicate webhooks? | Verify/dedupe provider event ID |
| Multiple refunds? | Refund ledger + provider idempotency |
| Long-term audit needed? | Separate event/ledger collection |
| Heavy history queries? | Compound indexes/read models |
| Multiple tenants? | Tenant-scoped auth, IDs/indexes/sharding |
| Large documents? | Bounded embedded data, references |
| Schema evolving over time? | Versioned migrations + backward compatibility |

## 56. Common Anti-Patterns

| Anti-pattern | Harm | Remediation |
|---|---|---|
| Order stores only `productId`, reads live catalog price | Historical orders change price | Snapshot price/name/variant |
| Frontend sends amount to charge | Price tampering | Server-side quote verification |
| Unverified `double` for money | Rounding errors | Int64 minor units/Decimal128 |
| Omitting currency | Mixing incompatible units | Currency on order and payment |
| Single `status` for all flows | State explosion | Substates + invariants |
| Arbitrary `$set` on status | Races, illegal transitions | FSM + conditional updates |
| No revision field | Lost updates | Optimistic concurrency |
| Blindly retrying on `matchedCount=0` | Overwriting newer status | Re-read and decide |
| Read stock then deduct later | Overselling | Atomic conditional `$inc` |
| Using TTL reservations to auto-restore stock | Lost inventory | Expiry workflow + release |
| Payment HTTP inside MongoDB transaction | Long tx, non-atomic external side | Saga/outbox |
| DB commit then non-durable publish | Lost events | Transactional outbox |
| Assuming outbox is exactly-once | Downstream duplicates | Consumer idempotency |
| Last-arriving webhook wins | State regression | Event verification + state rules |
| Retrying refund without key | Double refund | Stable provider idempotency |
| Overwriting grand total on refund | Lost history | Separate refund/ledger records |
| Embedding all raw webhook events | Oversized documents | Separate bounded event store |
| Storing card/secret tokens in snapshot | Security risk | Provider references |
| Enforcing unique orderNo via app check | Duplicate race | Unique index |
| Updates missing tenant scope | Cross-tenant corruption | Auth + tenant-scoped filters |
| Ignoring shard key/unique rules | Constraint errors | Version-specific sharding design |
| Schema validation replacing FSM | Does not block invalid transitions | Domain guards |
| Restoring old backups app cannot read | Mapping errors | Schema versioning/compat tests |
| Deleting orders arbitrarily via TTL | Lost records | Retention/archival policy |
| Testing only happy path | Failures on retry/failover | Concurrency/fault tests |
| UI marks PAID on redirect | False payment state | Provider-confirmed status |

## 57. Hands-On Exercises

### Exercise 1 — Classifying Snapshots and References

Given the fields: `productId`, `productName`, `currentProductPrice`, `unitPriceAtCheckout`, `sellerId`, `inventoryAvailable`, `shippingAddress`, `paymentIntentId`, `providerSecret`, `trackingEvents`, decide which fields are snapshotted on the order, which reference other collections/services, and which must never be stored.

### Exercise 2 — Designing an Order Document

Write a MongoDB document containing:

- Tenant and order identity;
- Two line items;
- Product snapshots;
- Int64 monetary fields and currency;
- Discount, tax, shipping;
- Delivery snapshot;
- Status and revision;
- Payment reference.

Verify the total formula.

### Exercise 3 — Price Changes After Confirmation

On day T0 a customer orders product P priced at 200000; on day T1 the catalog changes to 260000.

1. Which price must the order history page display?
2. What is `productId` still used for?
3. What if the product is deleted?
4. Which data is used to calculate a refund?
5. What test catches the bug of querying the current price?

### Exercise 4 — State Machine

Design transitions across:

```text
CREATED, PENDING_PAYMENT, PAID, PACKING,
SHIPPED, DELIVERED, CANCEL_REQUESTED, CANCELLED
```

Write the matrix of valid/invalid transitions and their reasons.

### Exercise 5 — CAS

Two concurrent workers read `PAID`, `revision=8`.

1. Write `updateOne` for the packing worker.
2. Write `updateOne` for the cancel worker.
3. Prove at most one command matches revision 8.
4. What must the losing worker do?
5. Why not update purely by `_id`?

### Exercise 6 — Reading the Post-Update Result

Write a Java Sync Driver `findOneAndUpdate` using `ReturnDocument.AFTER` to transition `PAID→PACKING`, enforcing tenant scope and revision. Handle the `null` return case.

### Exercise 7 — Inventory Reservation

A stock record has `available=1`; two customers each order 1 simultaneously.

1. Why can read-then-write oversell?
2. Write the conditional `$inc`.
3. Why is `matchedCount=0` not a network error?
4. Which fields does a reservation need?
5. How do you release on cancellation without crediting twice?

### Exercise 8 — Reservation TTL

A reservation expires after 15 minutes.

1. Does TTL automatically update `inventory.available`?
2. Write the `HELD→EXPIRED` transition.
3. Where is a transaction or compensation needed?
4. What if a worker processes it twice?
5. When can reservation history be deleted?

### Exercise 9 — Transaction Boundaries

Classify the following pairs of operations:

- Changing `status` and `revision` on one order;
- Inserting an order and inserting an outbox event;
- Decrementing stock and creating a reservation;
- Writing to MongoDB and calling a payment gateway;
- Creating a shipment record and calling a carrier;
- Writing a payment ledger entry and updating the order summary.

Explain when to use single-document atomicity, multi-document transactions, or sagas.

### Exercise 10 — Mid-Transaction Failure

In staging, create an order and reservation inside a transaction; inject a failure before commit. Verify the expected DB state, then test unknown commit outcomes and idempotency.

### Exercise 11 — Duplicate Payment Callback

The provider sends a capture event for 660000 twice.

1. What is the unique key?
2. Should `$inc` be used on captured amount?
3. When an event was already processed, what do you do?
4. What if the provider and order status conflict?
5. What data does a reconciliation job need?

### Exercise 12 — Cancel/Capture Race

Reproduce the competing cancel and capture flows.

1. Choose intermediate states.
2. What is the CAS filter?
3. What if capture already happened when the order cancels?
4. How does the refund require idempotency?
5. What should the UI display when the outcome is uncertain?

### Exercise 13 — Outbox

Design an `OrderPaid` outbox event:

- Event ID;
- Aggregate ID/revision;
- Tenant;
- Minimal payload;
- Status/attempts/lease;
- Timestamp.

Explain why the dispatcher can publish duplicates and how consumers deduplicate.

### Exercise 14 — Partial Refund

Order 660000 was captured; 100000 is refunded.

1. Does `grandTotal` change?
2. What are `capturedMinor` and `refundedMinor`?
3. How do you prevent refund > captured?
4. Is the current catalog price relevant?
5. What does the audit/ledger record need?

### Exercise 15 — Partial Fulfillment

An order has line L1 quantity 3; shipment A delivers 1, shipment B delivers 2.

1. What `fulfillmentStatus` values are needed?
2. Verify shippedQuantity ≤ orderedQuantity.
3. How are duplicate webhooks handled?
4. Should every tracking event be embedded?
5. How do carrier status and order status differ?

### Exercise 16 — Indexes

Design indexes for:

- Customer order history;
- `PAID` orders queue;
- Unique `(tenantId,orderNo)`;
- Checkout idempotency.

Explain read/write/storage trade-offs and sharding constraints if applicable.

### Exercise 17 — Multi-Tenant Security

Tenant A attempts to access tenant B's order.

1. Where is the auth boundary?
2. Which fields go into the update filter?
3. How do you prevent leaks in logs?
4. Which lines can a seller view?
5. How should address data be stored and retained?

### Exercise 18 — Recovery Testing

Simulate:

```text
Order DB commit success
Payment provider captured success
Webhook lost
Worker crashed
```

Design a resume/reconciliation mechanism ensuring no second order is created and no duplicate charge occurs.

### Exercise 19 — Schema Migration

Migrate from `total: double` to `pricing.grandTotalMinor: long`.

1. Write an expand-and-contract plan.
2. When can original decimal precision not be recovered?
3. Does the backfill need reconciliation against the ledger?
4. When do you enable strict schema validation?
5. When is it safe to remove the old field?

### Exercise 20 — Design Review

A team proposes:

```text
orders:
  items reference catalog only
  paymentStatus string
  status modified by any service
  inventoryAvailable embedded
  all webhook events embedded
  retry on every error
```

List risks regarding historical pricing, concurrency, overselling, document growth, idempotency, and security. Propose an alternative with clear boundaries.

## 58. Pre-Release Order Feature Checklist

### Snapshots and Money

- [ ] Snapshot names/variants/SKUs/prices at confirmation time.
- [ ] Catalog references used for live features, never replacing history.
- [ ] Quotes/pricing verified by the backend.
- [ ] Monetary types, currency, and scale explicitly defined.
- [ ] Subtotal/discount/tax/shipping/total formulas tested.
- [ ] Rounding and discount allocation rules defined.
- [ ] Snapshots exclude unnecessary sensitive data.
- [ ] Historical prices remain unchanged when sellers update the catalog.

### State and Concurrency

- [ ] State machine and transition matrix defined.
- [ ] Invariants across order/payment/fulfillment/refund enforced.
- [ ] Critical updates filter on status/revision.
- [ ] Handle `matchedCount=0` as a conflict/condition, never blind retry.
- [ ] Status transitions audited.
- [ ] No unbounded historical arrays.
- [ ] Tests cover cancel/capture and payment/shipping races.
- [ ] Idempotency keys in place for checkout and provider operations.

### Transactions and Integration

- [ ] Single-document atomicity leveraged appropriately.
- [ ] Multi-document transactions used only where invariants require.
- [ ] Transactions kept short with no external HTTP calls inside.
- [ ] Saga/compensation workflows ready for payment/fulfillment.
- [ ] Inventory reservations prevent overselling.
- [ ] Stock releases are idempotent without relying on TTL auto-restoration.
- [ ] Outbox/event delivery is durable with consumer deduplication.
- [ ] Plan in place to reconcile unknown payment outcomes.
- [ ] Refund/ledger operations enforce unique IDs and amount bounds.

### Operations and Data

- [ ] Indexes driven by real query shapes.
- [ ] Unique constraints compatible with tenant/shard keys.
- [ ] Schema validators versioned and migrated safely.
- [ ] Monitoring for p95/p99, conflicts, and payment/CDC lag.
- [ ] Backup/restore and backward schema compatibility tested.
- [ ] PII protected with appropriate RBAC/encryption/retention.
- [ ] Runbook ready for payment captured while order is not PAID.
- [ ] Runbook ready for order cancelled after capture.
- [ ] Adequate capacity planned for peak SKUs/hot inventory.
- [ ] Tested against network failures, duplicate events, and process crashes.

## 59. Order Inconsistency Incident Runbook

A template:

```text
INCIDENT ID:
START TIME:
TENANT / ORDER SCOPE:
BUSINESS IMPACT:
OWNER:

SYMPTOM:
  Order status:
  Payment provider status:
  Reservation status:
  Shipment status:

EVIDENCE:
  Order _id / revision:
  Checkout idempotency key:
  Payment intent / event IDs:
  Reservation IDs:
  Outbox event IDs:
  Redacted logs / traces:

CLASSIFICATION:
  Duplicate request
  Lost/late webhook
  Unknown payment outcome
  Inventory oversell
  Invalid transition
  Schema migration issue
  External service outage

CONTAINMENT:
  Pause offending worker?
  Restrict duplicate retries?
  Alert support/payment operations?

RECOVERY:
  Read provider authoritative result
  Reconcile ledger
  CAS order state transition
  Refund or release stock as needed
  Replay/dedupe outbox
  Validate fulfillment state

POSTCONDITIONS:
  No duplicate charge/refund
  No oversell
  Financial amounts reconcile
  Snapshot unchanged
  All transitions authorized
  Audit complete

DECISION:
  GO / HOLD / RECOVER / ESCALATE
```

Never patch production with `$set:{status:"PAID"}` without verifying actual funds, provider event identity, and related invariants.

## 60. References

In production implementations, verify against your exact **MongoDB Server, Java Driver, and topology**:

- [MongoDB Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Embedded Data vs References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/)
- [MongoDB Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB `findAndModify`](https://www.mongodb.com/docs/manual/reference/command/findAndModify/)
- [MongoDB `updateOne`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/)
- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB `$jsonSchema`](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/)
- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Atlas Backup and Restore](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)

## Conclusion

Designing orders in MongoDB requires more than a collection with `items`, `total`, and `status` fields. An order is **a record of a commercial commitment and the progression of fulfilling that commitment**.

**Data snapshots** preserve prices, quantities, discounts, taxes, shipping, and display details needed at confirmation time. As a result, historical orders and invoices do not change when the catalog, price list, or promotions change later. References to products and customers remain useful, yet cannot replace snapshots.

**State** must be governed by a state machine, invariants, and conditional updates on `_id`/tenant/status/revision. MongoDB atomically updates multiple fields within a single document, while transition validity remains enforced by domain logic and business evidence.

**Transaction boundaries** must align with what truly needs to commit together. Within one document, use single-document atomicity. Across multiple MongoDB documents requiring joint consistency, use short transactions where appropriate. For payment providers, carriers, or external systems, use sagas, outboxes, idempotency, compensation, and reconciliation—never expect a MongoDB transaction to span external HTTP calls.

Finally, design for the hard edge cases: checkout retries, concurrent workers racing on status changes, payment succeeding with a lost callback, expired stock reservations, partial refunds, split shipments, duplicate webhooks, long-term historical retention, and schema migrations. Those exact edge cases determine whether a model is safe in real production operation.

**A strong order design preserves the truth of the placement moment, protects state transition rules, and knows exactly when to use an atomic update, a transaction, or a recoverable compensating workflow.**
