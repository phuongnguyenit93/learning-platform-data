# Entities, Value Objects, and Domain Services in Data Modeling

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **entities**, **value objects**, and **domain services** by identity, equality rules, lifecycle, and business responsibility.
- Analyze a requirement to decide which concepts need an identity key, which should be immutable values, and which rules belong in a domain service.
- Translate a model into keys, relationships, constraints, indexes, and transactions while still protecting business invariants.
- Distinguish domain services, application services, infrastructure services, and aggregate consistency boundaries.
- Evaluate how these concepts map onto relational, document, graph, and analytical data stores.

In the **DATABASE_DATA_MODELING** module, data design starts by understanding a business requirement: customers may edit item quantities before confirming an order, but a locked-in unit price must not change with the next day's catalog price. Simply listing Customer, Order, and Product tables is not enough; you must know which objects have a lifecycle, which values are preserved as-is, and who is responsible for enforcing rules.

## 1. Distinguishing Three Roles in a Domain Model

Consider three statements:

1. Order #A123 remains the same order after the customer changes the delivery address.
2. Two monetary amounts of 100,000 VND have the same business meaning if the amount and currency are equal.
3. An order's discount is calculated from its line items, membership tier, and current promotional policy.

Statement (1) calls for an **entity** because an identity persists across changes. Statement (2) calls for a **value object** because content determines equality. Statement (3) may call for a **domain service** if the pricing behavior is a rule combining multiple concepts that does not naturally belong to a single object.

| Aspect | Entity | Value Object | Domain Service |
| --- | --- | --- | --- |
| What gives it meaning | Identity and lifecycle | Set of component values | Business behavior/policy |
| Equality | Same identity within a defined scope | Equivalent attribute values | No object identity mechanism needed like an entity |
| Mutability | State can change, identity stays stable | Prefers immutability and replacement with a new value | Performs operations, usually does not hold long-term business state |
| Examples | Order, Customer, InventoryReservation | Money, DateRange, AddressSnapshot | MembershipDiscountService, CommissionPolicy |
| Storage | Keyed record with a lifecycle | Embedded columns, nested document, or specialized structure | Business logic code; does not default to its own table |

These are **roles within the domain model**, not a one-to-one mapping to Java classes or SQL tables. A row in a database is not necessarily a domain entity; a value object can span multiple columns, or occasionally be stored in a separate table for technical reasons.

## 2. Entities: Same Identity Across States

### 2.1. Identity Is Not a Name or Arbitrary Attributes

A customer who changes their name, phone number, or address is still the same Customer. An order transitioning from draft to confirmed is still the same Order. If a model identifies objects by mutable attributes, links and history easily break.

Identity choices should be clearly separated:

- **Internal key:** auto-generated UUID or BIGINT; typically used to keep data links stable.
- **Business code:** customer-facing order number, contract code, case number. This code may have its own format and uniqueness scope rules.
- **Parent-dependent identity:** order line #1 is only unique within a specific order; a composite key `(order_id, line_no)` makes sense. Two lines with the same sequence number in two different orders are not the same entity.

Email addresses and phone numbers usually should not serve as a Customer's immutable identifier because they can change or be reassigned. If an email must be unique within a scope, that is **a separate business constraint**, not necessarily the primary key.

### 2.2. Entities Have a Lifecycle and Behavior

Suppose Order follows these rules:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT: Create order
    DRAFT --> DRAFT: Edit line items
    DRAFT --> CONFIRMED: Confirm
    DRAFT --> CANCELLED: Cancel
    CONFIRMED --> [*]
    CANCELLED --> [*]
~~~

- Only an Order in the DRAFT state can have its line items modified.
- Before confirmation, the order must have at least one line and each line must have a quantity greater than 0.
- The locked-in unit price must be stored to preserve history; updating list prices does not automatically modify existing orders.
- If a total amount is stored, that total must match the line item data, currency, and rounding rules.

These are the domain's **invariants** and state transition rules. Invariants must be enforced across all write paths, not just in UI forms. Under concurrent updates, transactions and conflict control at the storage layer must also participate in protecting them.

### 2.3. Entity and Aggregate Are Not Synonymous

An **aggregate** is a group of objects managed through an **aggregate root** to protect invariants that must remain consistent within a single local transaction.

For example: Order can be an aggregate root and OrderLine a child entity. When changing a line's quantity, the request should go through Order's behavior to check the state and recalculate totals. Customer has a different lifecycle from Order, so it is typically a separate aggregate. Order only needs to hold `customerId` and a snapshot of committed details, without directly modifying the Customer profile.

A **bounded context** defines where a model/business language is valid; an aggregate defines the consistency boundary of changes. A bounded context contains many aggregates. Putting two tables in the same schema does not prove they belong to the same aggregate.

## 3. Value Objects: Equal by Content

A **value object** has no independent business identity. Two `Money` values with the same amount and currency must be equivalent according to the rules of the `Money` type, regardless of where they were created. Conversely, 100,000 VND and 100,000 USD are two different values.

| Value object | Meaningful components | Rules to protect |
| --- | --- | --- |
| Money | amount, currency | Add money only in the same currency; define precision and rounding |
| DateRange | start, end | start is not after end; clarify whether the interval is closed or half-open |
| Quantity | amount, unit | Never arbitrarily add 2 kg and 3 pieces |
| GeoCoordinate | latitude, longitude | Latitude and longitude must be within valid ranges |
| AddressSnapshot | recipient, street, region, country | Captures info at transaction time; replace the whole value on edit |

Value objects should **self-validate** on creation and favor **immutability**. For instance, instead of mutating the `street`/`city` fields of an `AddressSnapshot` referenced by multiple orders, create a new `AddressSnapshot` and assign it to an order that is still allowed to be edited.

A value object does not merely hold data. `Money` can add, subtract, and compare; `DateRange` can check for overlap. Placing behavior on the right type avoids loose clusters of primitive variables and reduces the need for unnecessary service classes.

**Semantic note:** two addresses with identical strings do not prove they refer to the same physical location. If you need to manage a location with an ID, verification status, and change history, the concept `DeliveryLocation` may become an entity. Meanwhile, the address recorded on an order is usually just a snapshot value object.

## 4. Domain Services: Where Rules Without a Natural Owner Live

A **domain service** represents a business-meaningful operation or policy that does not naturally belong to a single entity or value object. For example, a discount rule depends on order contents, membership tier, and promotional campaigns. Order does not own the entire membership policy; nor should it call the database directly to load member details every time a price is calculated.

One design option is to have `MembershipDiscountService` accept prepared inputs and return the discount `Money`. The domain service handles the **calculation policy**, while loading data, managing transactions, and persisting results belong to other responsibilities.

| Service type | Responsibility | Example |
| --- | --- | --- |
| **Domain service** | Calculate or decide business rules | Calculate discount from order + membership tier + policy version |
| **Application service** | Orchestrate a use case, check permissions, load/save aggregates, open transactions | ConfirmOrderUseCase |
| **Infrastructure service** | Connect to databases, APIs, notification systems | PostgresOrderRepository, PaymentGatewayAdapter |

A domain service can accept an interface to query domain information, but its impact on transactions and latency must be explicitly designed. For pricing calculations, passing in the required data makes the operation easy to test, infrastructure-independent, and free of accidental I/O.

**Do not dump all business logic into OrderService:** if Order only has getters/setters and `OrderService` directly mutates status, quantities, prices, and totals, invariants become scattered. Behavior directly tied to an aggregate should reside on the aggregate itself; domain services are for rules with no natural single owner.

## 5. Java Example: Order, OrderLine, Money, and Discount Service

The following example assumes an order uses a single currency, prices have two decimal places, and discounts follow membership tiers. Production systems must account for currency-specific decimal scales, taxes, and rounding rules.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.Currency;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

// VALUE OBJECT: compared by value, no ID needed.
record Money(BigDecimal amount, Currency currency) {
    Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
        amount = amount.setScale(2, RoundingMode.UNNECESSARY);
    }

    Money add(Money other) {
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Different currencies");
        }
        return new Money(amount.add(other.amount), currency);
    }

    Money multiply(int quantity) {
        if (quantity <= 0) throw new IllegalArgumentException("quantity <= 0");
        return new Money(amount.multiply(BigDecimal.valueOf(quantity)), currency);
    }
}

// CHILD ENTITY: lineId stays the same when quantity is updated.
final class OrderLine {
    private final UUID lineId;
    private final String productId;
    private final Money unitPriceSnapshot;
    private int quantity;

    OrderLine(UUID lineId, String productId, Money unitPrice, int quantity) {
        this.lineId = Objects.requireNonNull(lineId);
        this.productId = Objects.requireNonNull(productId);
        this.unitPriceSnapshot = Objects.requireNonNull(unitPrice);
        changeQuantity(quantity);
    }

    UUID lineId() { return lineId; }
    Money subtotal() { return unitPriceSnapshot.multiply(quantity); }

    void changeQuantity(int newQuantity) {
        if (newQuantity <= 0) throw new IllegalArgumentException("quantity <= 0");
        quantity = newQuantity;
    }
}

enum OrderStatus { DRAFT, CONFIRMED, CANCELLED }
enum CustomerTier { NORMAL, SILVER, GOLD }

// AGGREGATE ROOT: operations modifying lines must go through Order.
final class Order {
    private final UUID id;
    private final Currency currency;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;

    Order(UUID id, Currency currency) {
        this.id = Objects.requireNonNull(id);
        this.currency = Objects.requireNonNull(currency);
    }

    void addLine(UUID lineId, String productId, Money price, int quantity) {
        requireDraft();
        if (!currency.equals(price.currency())) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        if (lines.stream().anyMatch(line -> line.lineId().equals(lineId))) {
            throw new IllegalArgumentException("Duplicate line identity");
        }
        lines.add(new OrderLine(lineId, productId, price, quantity));
    }

    void changeQuantity(UUID lineId, int quantity) {
        requireDraft();
        OrderLine line = lines.stream()
            .filter(item -> item.lineId().equals(lineId))
            .findFirst()
            .orElseThrow(() -> new IllegalArgumentException("Line not found"));
        line.changeQuantity(quantity);
    }

    Money subtotal() {
        Money result = new Money(BigDecimal.ZERO, currency);
        for (OrderLine line : lines) result = result.add(line.subtotal());
        return result;
    }

    void confirm() {
        requireDraft();
        if (lines.isEmpty()) throw new IllegalStateException("Order is empty");
        status = OrderStatus.CONFIRMED;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Order cannot be changed");
        }
    }
}

// DOMAIN SERVICE: computes a rule involving both the order and membership policy.
final class MembershipDiscountService {
    Money discountFor(Order order, CustomerTier tier) {
        BigDecimal rate = switch (Objects.requireNonNull(tier)) {
            case NORMAL -> new BigDecimal("0.00");
            case SILVER -> new BigDecimal("0.05");
            case GOLD -> new BigDecimal("0.10");
        };
        Money subtotal = order.subtotal();
        BigDecimal reduction = subtotal.amount()
            .multiply(rate).setScale(2, RoundingMode.HALF_UP);
        return new Money(reduction, subtotal.currency());
    }
}
~~~

Decisions to observe:

- Order and OrderLine have **distinct identities within their appropriate scope**; updating quantity does not create a new line, and changing status does not create a new order.
- Money has two components, `amount`/`currency`, normalized to two decimal places to avoid `BigDecimal` scale discrepancies when comparing by value in this example.
- Order blocks adding duplicate line IDs, editing after confirmation, and confirming an empty order. OrderLine is not exposed externally for other classes to mutate directly, bypassing aggregate root rules.
- `MembershipDiscountService` applies the policy from passed-in values. The application must decide when to snapshot the membership tier and rule version, and persist the applied discount if auditability is required.

This is domain illustration code and does not yet cover transactions, persistence, tax policies, or line-level discount allocation. Nor does `confirm()` by itself prove that inventory reserved stock or payment succeeded; cross-context conditions require a dedicated coordination workflow.

## 6. Mapping the Model to a Relational Schema

A PostgreSQL example:

~~~sql
CREATE SCHEMA sales;

CREATE TABLE sales.orders (
    order_id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    status VARCHAR(12) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    currency VARCHAR(3) NOT NULL
        CHECK (currency ~ '^[A-Z]{3}$'),
    -- AddressSnapshot stored as columns on Order.
    shipping_recipient TEXT NOT NULL,
    shipping_street TEXT NOT NULL,
    shipping_city TEXT NOT NULL,
    shipping_country_code VARCHAR(2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sales.order_line (
    order_id UUID NOT NULL
        REFERENCES sales.orders(order_id),
    line_id UUID NOT NULL,
    product_id VARCHAR(64) NOT NULL,
    product_name_snapshot TEXT NOT NULL,
    unit_price_amount NUMERIC(19, 2) NOT NULL
        CHECK (unit_price_amount >= 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_id)
);
~~~

**Order** maps to a row keyed by `order_id`; **OrderLine** has a unique identity within Order via the composite key `(order_id, line_id)`. This key also supports querying lines by `order_id` since it is the leading prefix of the primary key index.

**Money** for line price is split into `unit_price_amount` and Order's `currency`: in this example an order allows only one currency, so when reconstituting `Money` for a line, the mapper combines the line's amount with the order's currency. If lines are allowed to use different currencies, the model and conversion rules must be explicitly changed.

**AddressSnapshot** does not need its own `address_id`: the `shipping_*` columns together represent the address value at placement time. Storing addresses on Customer and dynamically referencing them would cause historical orders to change whenever the current profile is updated.

**MembershipDiscountService** does not need a table just because it has "service" in its name. However, if policies change over time, the business may need a policy table with code, effective period, and version, along with the locked-in discount amount on the order. Separate **the rule-processing service** from **the policy-describing data**.

Use `product_id` to reconcile with Catalog and `product_name_snapshot`/price to preserve history. If Product belongs to another bounded context, avoid assuming cross-system FKs are always appropriate; ownership, integration interfaces, and handling of missing references must be defined.

### Invariants SQL Does Not Enforce Automatically

PRIMARY KEY, FOREIGN KEY, CHECK, and NOT NULL protect per-row constraints and local relationships. However:

1. A CHECK on `status` only restricts the set of values; it does not forbid jumping directly from CANCELLED to CONFIRMED.
2. "A CONFIRMED order must have lines" is a multi-row condition that must be protected within a transaction or by an appropriate DB mechanism.
3. "Do not modify prices after confirmation" spans the Order and line tables and must be blocked across all write paths; depending on strictness, access controls and triggers can be added.
4. When two requests modify an order concurrently, locking or version checks are required. A transaction that reads and then writes without conflict control risks lost updates.

Example of a conditional state transition step:

~~~sql
UPDATE sales.orders
SET status = 'CONFIRMED', version = version + 1
WHERE order_id = :order_id
  AND status = 'DRAFT'
  AND version = :expected_version;
~~~

The application must check the number of updated rows; if it is 0, the status/version has changed and the conflict must be handled. When modifying line items, that operation must also participate in the same transaction and version control strategy as Order; incrementing `version` only at confirmation is not enough to protect concurrent line edits.

## 7. Cases Where Entity and Value Object Are Easily Confused

### What Is OrderLine?

If the business needs to edit, delete, refund, reconcile, and track individual lines by ID, `OrderLine` has an identity within Order and is therefore a child entity. If a cart is always replaced wholesale as a list of values with no per-item lifecycle, a collection of value objects can also make sense. Having a separate table does not by itself decide the domain role.

### What Is an Address?

A committed shipping address is usually an `AddressSnapshot` value object. An entry in an "address book" that a customer creates, names, edits, deletes, and manages independently can be a `SavedAddress` entity. Both concepts have similar text fields but different lifecycles.

### Is an Identifier an Entity?

`OrderId` can be a value object wrapping a UUID so it is never accidentally passed where a `CustomerId` is expected. That does not turn Order into a value object: **the identifier** is a value, whereas **the order** is an object with history, state, and identity.

### Monetary Amounts and Exchange Rates

`Money` is typically a value object. An exchange rate at a point in time is a value with units and a source; if you need to track individual issuances, providers, effective periods, and revisions, an `ExchangeRateQuote` record may become a separate entity or historical event. The choice depends on whether the business needs to track the identity of that record itself.

A helpful litmus test: "If two objects have identical current attributes, does the business still need to distinguish them?" If yes, you usually need an entity. "If you replace an object with a copy of equivalent value, would the business notice any difference?" If no, it is usually a value object.

## 8. Assigning the Right Responsibilities to a Domain Service

Consider this policy: GOLD customers receive a 10% merchandise discount, capped at 200,000 VND, applicable only to eligible products; separate vouchers follow an agreed application order.

- **Order** owns its line items, locked-in prices, status, and the final order discount.
- **Membership** provides the effective membership tier at the time of application.
- **Promotion policy** expresses rates, caps, eligible items, discount stacking order, and effective version.
- **Pricing domain service** computes the discount value, allocates it across lines if needed, and returns a business-meaningful result.
- **Application service** loads data, checks permissions/preconditions, selects the policy version, invokes the domain, writes results in a transaction, and publishes integration messages if any.

If a calculation genuinely belongs only to `Money`, put that behavior on `Money`; if a change depends solely on Order state, put it on Order. Only create a domain service when domain behavior has no natural single owner, avoiding turning every behavior into a service method.

In the data model, decide **which results to persist**: `discount_amount`, `policy_id`, `policy_version`, and per-line allocated discounts for accurate refunds. Never recalculate historical orders using today's policy if customer agreements require preserving locked-in values.

## 9. Same Model, Multiple Storage Engines

| Storage type | Common mapping | Points to verify |
| --- | --- | --- |
| Relational | Order and OrderLine as tables; Money/Address as columns | FK, UNIQUE, CHECK, transactions, concurrency control |
| Document | Order document containing `lines` and `shippingAddress` | Convenient aggregate-level reads/writes; watch document size limits and entities with independent lifecycles |
| Graph | Order, Customer, Product as nodes and links as edges | Edges aid relationship traversal, but do not automatically determine ownership or invariants |
| Analytical/Columnar | FactOrderLine and historical dimensions | Serves reporting/aggregation; usually a read replica rather than replacing the transactional write source |

Example representing Order as a document:

~~~json
{
  "orderId": "b188c0f3-83de-49be-8f84-fcdbbfbdc168",
  "status": "CONFIRMED",
  "currency": "VND",
  "shippingAddress": {
    "recipient": "Nguyen An",
    "street": "12 Nguyen Trai",
    "city": "Ho Chi Minh City",
    "countryCode": "VN"
  },
  "lines": [
    {
      "lineId": "9c640fdf-dfba-43d9-92f4-2b5e5f8646ed",
      "productId": "LAPTOP-001",
      "unitPriceAmount": "23000000.00",
      "quantity": 1
    }
  ]
}
~~~

Order is still an entity, Money is still a value object, and OrderLine can still be a child entity. Moving from tables to documents **does not change the domain nature**. Money in the JSON example uses a decimal string to avoid binary floating-point precision loss in parsers; the application must parse it into an appropriate decimal type.

In graph or analytical stores, terms like node, edge, fact, and dimension describe storage/query structures; they do not automatically correspond to entities/value objects in domain design.

## 10. Common Modeling Mistakes

| Symptom | Consequence | Remedy |
| --- | --- | --- |
| Creating separate IDs for every Money and AddressSnapshot | Unnecessary joins, artificial identities, hard to enforce valid values | Use value objects and store within the aggregate |
| Comparing Customers by name or phone number | Updating contact info breaks identity | Choose a stable identity; enforce uniqueness constraints separately |
| Using double to store money | Binary representation and rounding errors | BigDecimal/NUMERIC with currency and explicit rounding policy |
| Mutating an AddressSnapshot shared across multiple orders | Shipping history changes unexpectedly | Make value objects immutable; replace with a new snapshot |
| Putting all rules into classes named Service | Entities become pure CRUD, invariants are scattered | Return behavior to the appropriate entities/value objects |
| Domain service directly calling HTTP and writing to DB | Hard to test, transactions and failures hard to control | Separate application orchestration and infrastructure adapters |
| Relying solely on CHECK for order status | Allows invalid workflow state transitions | Protect the state machine in domain behavior and write operations |
| Using FKs to unify all contexts | Schema/lifecycle coupling outside ownership | Define ownership and integration contracts first |

## 11. Practice Exercise

**Scenario:** A medical appointment booking system manages patients, appointments, consultation time slots, clinic addresses, and cancellation fees. Patients can change their phone number. A clinic may move to a new location in the future; booked appointments must retain the committed location and fee schedule.

**Tasks:**

1. Classify `Patient`, `Appointment`, `TimeSlot`, `ClinicAddressSnapshot`, and `CancellationFeePolicy` as entities, value objects, or domain policies/services. Explain why.
2. Write three business invariants and propose primary/foreign keys for the appointment data.
3. State which details must be snapshotted and how to prevent two people from booking the same doctor at overlapping times.
4. Explain the difference between checking per-row status and checking multi-row time-slot overlaps.

**Reference solution approach:**

- `Patient` and `Appointment` are entities because they have identities and lifecycles. `TimeSlot(start, end)` is a value object with the constraint `start < end`. `ClinicAddressSnapshot` is a value object recording the location at booking time. The fee policy can be a value object describing rates/conditions; the calculation based on multiple inputs (cancellation timing, appointment type, policy version) can belong to a domain service.
- Example invariants: `start` before `end`; no two active bookings for the same doctor with overlapping time ranges; completed or cancelled appointments cannot arbitrarily have their time changed. The appointment table has fields such as `appointment_id`, `patient_id`, `doctor_id`, `start_at`, `end_at`, `status`, `address_snapshot...`, `fee_amount`, `currency`, `policy_version`, `version`.
- Preventing double-booking is a **multi-row** constraint. In PostgreSQL, you can use an exclusion constraint on `doctor_id` and the time range for active appointments, or design appropriate transactions/locks. Simply reading to see a slot is free and then running INSERT risks race conditions; per-row CHECK constraints are insufficient.
- Snapshotting location, fee, and policy version ensures confirmed appointments do not change when current reference data changes.

## 12. Model Review Checklist

- Which objects have their own identity and history? Are identity keys stable and uniqueness scopes explicit?
- Which values should be encapsulated and validated like Money, Quantity, DateRange, or AddressSnapshot?
- Which behaviors belong on entities/value objects, and which genuinely require a domain service?
- Which aggregate root controls updates and invariants within a transaction?
- Which constraints can the DB enforce directly, and which require a state machine, locks/versioning, and application coordination?
- Which prices, addresses, and policies must be snapshotted and versioned for historical auditability?
- Do the chosen relational, document, graph, or analytical structures serve the read/write patterns and evolvability well?

**Conclusion:** An entity answers "is this still the same object over time?", a value object answers "which components define this value?", and a domain service describes "which business rule has no natural single owner?". Clearly distinguishing these three roles helps select keys, storage structures, transaction boundaries, and consistency enforcement points directly from business requirements.
