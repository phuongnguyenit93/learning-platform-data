# The Role of Identity in Aggregate Roots and Child Entities

In Spring Data JDBC, identity helps the application answer two questions: **which business object is being referred to**, and **which aggregate that object belongs to and through which entry point it is managed**.

An aggregate root has its own identity so repositories can find, save, and delete it, and so other aggregates can reference it. A child entity may have an identity within the scope of the aggregate to distinguish elements of the same type, but its lifecycle is still managed by the root. Value objects do not need their own identity: two values are considered equivalent based on their contents.

Do not equate `@Id`, SQL primary keys, `List` position keys, business IDs, and `@Version`. They may be related, but they serve different purposes.

This lesson uses an order example consisting of order lines to explain root identity, local identity of child entities, the difference between child entities and value objects, how to map IDs in `List` and `Map` using `@MappedCollection`, as well as primary key and foreign key design.

## 1. What is identity in a domain model?

Identity makes it possible to distinguish one object from other objects even when their attributes are identical.

Suppose an order has two lines with the same product, the same quantity, and the same unit price:

~~~text
Order #500
  Line A: product=BOOK-01, quantity=1, unitPrice=100.00
  Line B: product=BOOK-01, quantity=1, unitPrice=100.00
~~~

The two lines have the same descriptive data, yet they can still be two separate business lines: one created from the first add action, and the other from the second add action. If you need to edit or remove a specific line, comparing attributes alone is not enough. The system needs an identity to tell them apart.

By contrast, two `Money(100.00, VND)` values can be considered equal if they have the same amount and currency. They do not necessarily need their own ID.

### 1.1. Entity and value object

| Concept | How it is identified | Needs identity? | Example |
|---|---|---|---|
| Aggregate root | Stable ID | Yes | `SalesOrder` |
| Child entity | Own ID or ID within root scope | Yes if it needs to be distinguished over time | `OrderLine` |
| Value object | Values/attributes | No | `Money`, `Address`, `DateRange` |
| Reference to another aggregate | ID of the referenced root | Uses the target aggregate's identity | `customerId`, `productId` |

An **Entity** is identified by its identity. An entity's attributes can change while the object remains the same object.

A **Value object** is identified by its value. If a `Money` amount changes, we usually treat it as a new value replacing the old value, not the same entity with an ID whose state is changing.

A Java object does not automatically become an entity just because it is a class. Its role depends on its business meaning and lifecycle.

## 2. An aggregate root has its own identity

The aggregate root is the entry point for external interaction with the aggregate. In Spring Data JDBC, the root is typically marked with `@Id`.

~~~java
package com.example.shop.order.domain;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    private SalesOrder() {
    }

    public SalesOrder(String status) {
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getStatus() {
        return status;
    }
}
~~~

`@Id` indicates the root's identifier property. Spring Data JDBC uses it when executing repository operations and linking component records to the root.

Repository:

~~~java
package com.example.shop.order.repository;

import com.example.shop.order.domain.SalesOrder;
import org.springframework.data.repository.CrudRepository;

public interface SalesOrderRepository
        extends CrudRepository<SalesOrder, Long> {
}
~~~

Here:

- `SalesOrder` is the domain type.
- `Long` is the root's ID type.
- `findById(500L)` finds the aggregate by the root identity.
- `save(order)` saves the aggregate through the root.
- `deleteById(500L)` requests deleting the aggregate by root ID.

Do not create separate repositories for individual child entities if they still belong to the same aggregate and do not have an independent lifecycle.

### 2.1. Root identity must be stable

A good ID must remain unchanged throughout the object's lifecycle. Do not use mutable attributes such as customer name, shipping address, or order status as the primary identity.

~~~text
SalesOrder #500
  status: DRAFT -> CONFIRMED
  shippingAddress: Address A -> Address B

The ID is still 500.
~~~

The status and address can change; the order's identity does not change.

If you use a business-issued order number such as `SO-2026-000500`, you need to decide whether it is truly a technical ID or just a business key. You can store both:

~~~sql
CREATE TABLE sales_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL
);
~~~

`id` is the stable technical key for persistence; `order_number` is the business code that may appear on documents or in the UI. If business rules allow changing the code, separating the two concepts is especially helpful.

### 2.2. Database-generated ID or application-generated ID?

There are two common approaches:

| ID assignment approach | Example | When appropriate |
|---|---|---|
| Database-generated | `BIGINT IDENTITY` | Database assigns the ID, simple for the application |
| Application-generated | `UUID` | Need to create the identity before writing, generate data offline, or exchange across multiple components |

With a database-generated ID, a new object usually does not have an ID yet. After saving, use the object returned by `save(...)` to obtain the generated ID:

~~~java
SalesOrder saved = repository.save(new SalesOrder("DRAFT"));
Long orderId = saved.getId();
~~~

Do not assume every ID strategy detects new/existing state in the same way. With an assigned ID, you need to configure newness detection to match how Spring Data JDBC determines a new entity, such as leveraging `@Version` when the design fits or the `Persistable` mechanism when needed.

The key point is: **do not assign an ID yourself and assume the repository will always treat that object as new**. How newness is detected affects whether Spring Data chooses insert or update.

## 3. Child entity identity scoped within the aggregate

A child entity belonging to an aggregate may need its own identity to distinguish elements of the same type. However, that does not make it a second aggregate root.

~~~text
Aggregate SalesOrder #500
    |
    +-- OrderLine #a1
    +-- OrderLine #b7
    +-- OrderLine #c9
~~~

A line's identity may only have meaning **within the order that owns it**. In that case, the pair `(orderId, lineId)` is the full identity:

~~~text
(500, a1)
(500, b7)
(500, c9)
~~~

A `lineId` can be generated using a UUID for convenience in distinguishing lines. But if the schema uses a composite key `(order_id, line_id)`, the line ID only needs to be unique within the scope of the order.

This reflects ownership:

- `SalesOrder` decides when to create, edit, or delete an `OrderLine`.
- External callers do not save an `OrderLine` independently through a separate repository.
- Changes to child entities go through methods on the root.
- When saving the aggregate, Spring Data JDBC persists the aggregate state according to its mechanism.

### 3.1. Does a child entity need @Id?

In the common Spring Data JDBC collection model, a child entity is mapped by a foreign key to the root and a collection key if needed. It is not necessary to place `@Id` on the child class as if it were an aggregate root.

For example, a `Map<UUID, OrderLine>` collection can use the Map key as a local identity and store that key in the `line_id` column:

~~~java
@MappedCollection(idColumn = "order_id", keyColumn = "line_id")
private Map<UUID, OrderLine> lines;
~~~

In this approach:

- `order_id` links the line to the aggregate root.
- `line_id` is the key of the entry in the Map.
- `OrderLine` is the value stored in the child table.
- The repository remains `SalesOrderRepository`.

The SQL primary key of the child table can be `(order_id, line_id)`. This is a natural design for identity scoped within an aggregate.

### 3.2. When should a child entity become an aggregate root?

Consider splitting a child entity into an aggregate root if:

- It has its own lifecycle and can continue to exist after the old root is deleted.
- Many use cases need to find or edit it independently.
- Other aggregates need to reference it directly.
- It has its own consistency rules and needs to be updated independently.
- The root's collection can grow very large, making each aggregate read/write expensive.

Do not split solely because the child table has an ID column. A SQL primary key does not determine aggregate boundaries by itself.

## 4. Distinguishing domain ID, SQL primary key, and collection key

A design can contain multiple kinds of keys:

| Key type | Example | Role |
|---|---|---|
| Aggregate root ID | `sales_orders.id` | Identifies the aggregate |
| Child ID | `line_id` | Distinguishes child entities |
| Collection key | `line_position` or Map key | Identifies an element in the collection mapping |
| SQL primary key | `(order_id, line_id)` | Ensures uniqueness in the database |
| Foreign key | `order_lines.order_id` | Links a child to the root |
| Business key | `order_number`, `sku` | Identifies according to business rules |
| Version | `version` | Controls concurrent updates |

Not every key needs to appear as a separate Java property. For instance, when using `Map<UUID, OrderLine>`, the `UUID` key is already part of the domain model; Spring Data JDBC can store it via `keyColumn`.

A technical primary key only guarantees uniqueness for the database. It does not mean the object must be accessed or updated independently from the domain.

## 5. Mapping child entities with List: position is not a stable identity

A simple option is to use `List<OrderLine>`:

~~~java
@MappedCollection(
        idColumn = "order_id",
        keyColumn = "line_position"
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Spring Data JDBC stores the collection key based on element position. The schema can be:

~~~sql
CREATE TABLE sales_order_lines (
    order_id BIGINT NOT NULL,
    line_position INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(15, 2) NOT NULL,

    PRIMARY KEY (order_id, line_position),
    FOREIGN KEY (order_id)
        REFERENCES sales_orders(id)
        ON DELETE CASCADE,

    CHECK (line_position >= 0),
    CHECK (quantity > 0),
    CHECK (unit_price >= 0)
);
~~~

With this design, `(order_id, line_position)` identifies a row in the collection. However, `line_position` is a **position**, not a stable business ID.

~~~text
Before deletion:
  position 0 -> Book
  position 1 -> Pen
  position 2 -> Notebook

After deleting position 0:
  position 0 -> Pen
  position 1 -> Notebook
~~~

The remaining two lines change position. If the application stores `line_position = 1` in a URL or external system as if it were a long-lived ID, after reordering or deleting a line, the reference may point to a different line.

**Use List when order is a natural part of the data and no stable child ID across reordering is needed.**

If you need a stable line identity, consider `Map` or adding a separate domain key.

## 6. Mapping child entities with Map: the key is a local identity

When each line needs a stable ID within the order scope, `Map<UUID, OrderLine>` is a clear choice.

~~~java
@MappedCollection(
        idColumn = "order_id",
        keyColumn = "line_id"
)
private Map<UUID, OrderLine> lines = new LinkedHashMap<>();
~~~

In the schema:

~~~sql
CREATE TABLE sales_order_lines (
    order_id BIGINT NOT NULL,
    line_id UUID NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(15, 2) NOT NULL,

    PRIMARY KEY (order_id, line_id),

    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id)
        REFERENCES sales_orders(id)
        ON DELETE CASCADE,

    CONSTRAINT ck_order_line_quantity
        CHECK (quantity > 0),

    CONSTRAINT ck_order_line_unit_price
        CHECK (unit_price >= 0)
);
~~~

The Map key is stored in `line_id`, while `order_id` identifies the aggregate that owns the line. The composite primary key ensures a line ID cannot be duplicated within the same order.

### 6.1. Child entity does not need to declare an ID duplicating the Map key

~~~java
package com.example.shop.order.domain;

import java.math.BigDecimal;

public class OrderLine {

    private Long productId;
    private int quantity;
    private BigDecimal unitPrice;

    private OrderLine() {
    }

    public OrderLine(
            Long productId,
            int quantity,
            BigDecimal unitPrice
    ) {
        if (productId == null) {
            throw new IllegalArgumentException("Product is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid unit price");
        }

        this.productId = productId;
        this.quantity = quantity;
        this.unitPrice = unitPrice;
    }

    public OrderLine withQuantity(int newQuantity) {
        return new OrderLine(productId, newQuantity, unitPrice);
    }

    public Long getProductId() {
        return productId;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }
}
~~~

In this model, the entry's identity lives in the Map key; `OrderLine` only represents the line's data. If you need to expose an ID in an API, take the Map key rather than inferring it from position.

### 6.2. Aggregate root managing the Map

~~~java
package com.example.shop.order.domain;

import java.math.BigDecimal;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("sales_orders")
public class SalesOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    @MappedCollection(
            idColumn = "order_id",
            keyColumn = "line_id"
    )
    private Map<UUID, OrderLine> lines = new LinkedHashMap<>();

    private SalesOrder() {
    }

    public static SalesOrder createDraft() {
        return new SalesOrder("DRAFT");
    }

    private SalesOrder(String status) {
        this.status = status;
    }

    public UUID addLine(
            Long productId,
            int quantity,
            BigDecimal unitPrice
    ) {
        requireDraft();

        UUID lineId = UUID.randomUUID();
        lines.put(
                lineId,
                new OrderLine(productId, quantity, unitPrice)
        );
        return lineId;
    }

    public void changeLineQuantity(UUID lineId, int quantity) {
        requireDraft();

        OrderLine current = lines.get(lineId);
        if (current == null) {
            throw new IllegalArgumentException(
                    "Order line not found: " + lineId
            );
        }

        lines.put(lineId, current.withQuantity(quantity));
    }

    public void removeLine(UUID lineId) {
        requireDraft();

        if (lines.remove(lineId) == null) {
            throw new IllegalArgumentException(
                    "Order line not found: " + lineId
            );
        }
    }

    private void requireDraft() {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException(
                    "Only a draft order can be changed"
            );
        }
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public Map<UUID, OrderLine> getLines() {
        return Collections.unmodifiableMap(lines);
    }
}
~~~

This example focuses on identity and collection mapping. In a real project, you should use an enum for status, extract money/quantity validation into appropriate domain rules, and ensure the constructor used for mapping is compatible with how Spring Data JDBC instantiates objects.

Key points:

- The line ID is created when the line is added.
- The same `lineId` still identifies that line when attributes like quantity change.
- The root checks status before editing or deleting.
- External callers do not modify the Map directly.
- There is no `OrderLineRepository`; persistence still goes through `SalesOrderRepository`.

### 6.3. APIs should accept both root ID and child ID

If a child ID is only unique within an aggregate, the API path can be:

~~~text
PATCH /orders/500/lines/6a0f...
DELETE /orders/500/lines/6a0f...
~~~

Both `orderId` and `lineId` are passed. The service loads the root using `orderId`, and then the root locates the corresponding line using `lineId`.

This approach expresses ownership and prevents treating a line ID as an independent resource without context.

## 7. A child ID does not have to be system-wide unique

With a composite key:

~~~sql
PRIMARY KEY (order_id, line_id)
~~~

The line ID only needs to be unique within each order. For example, two orders can use the same `line_id` without conflict because `order_id` differs.

If random UUIDs are used, the probability of collision is very low, yet the database constraint still enforces uniqueness by design.

There are two ways to express identity:

| Identity style | Full identity |
|---|---|
| Global ID | `lineId` |
| Local ID within aggregate | `(orderId, lineId)` |

A global ID is convenient when direct references from many places are needed, but that can also be a sign that the child entity is taking on an independent lifecycle. If the ID only makes sense inside one root, a composite ID reflects ownership better.

Do not conclude that a child entity has become an aggregate root based solely on using a UUID. **Identity and aggregate boundary are two separate decisions.**

## 8. Value objects do not need their own ID

Suppose each order line contains money information:

~~~java
public record Money(
        BigDecimal amount,
        String currency
) {
    public Money {
        if (amount == null || amount.signum() < 0) {
            throw new IllegalArgumentException("Invalid amount");
        }
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("Currency is required");
        }
    }
}
~~~

`Money` is a value object. Two values with the same amount and currency can be considered equal. It does not need a `moneyId` just to distinguish each creation.

Similarly, an `Address` embedded in an order can be a snapshot of the shipping address at the time the order was placed. If the address is just a group of values belonging to the order without its own lifecycle, it does not need its own repository or ID.

### 8.1. What if a value object changes?

With an immutable value object, we create a new value and replace the old value:

~~~java
Money oldPrice = new Money(new BigDecimal("100.00"), "VND");
Money newPrice = new Money(new BigDecimal("120.00"), "VND");
~~~

There is no tracked `Money` entity changing its identity. The difference lies in the value.

### 8.2. When does Address become an entity?

If a customer profile manages multiple addresses, where each address has a verification status, change history, label, and is updated independently, it may need an identity. However, if the address is only a shipping snapshot of an order, a value object is usually more appropriate.

Ask:

- Do we need to distinguish two objects with the same content over time?
- Do we need to update/delete one object independently?
- Is the object referenced from multiple other aggregates?
- Does it have its own business rules and lifecycle?

If not, a value object can be simpler and more accurate.

## 9. A foreign key does not automatically turn a child entity into an aggregate root

A child table needs a way to link to the root. A foreign key is how the database enforces that relationship:

~~~sql
FOREIGN KEY (order_id)
    REFERENCES sales_orders(id)
~~~

This does not mean `OrderLine` is an aggregate root. A foreign key answers **which order this record belongs to**. An aggregate boundary answers **who has the right to modify this record and which rules must be protected together with it**.

Similarly, `sales_orders.customer_id` can be a foreign key to `customers.id`, while `Customer` remains a separate aggregate. The order references the customer by ID; it does not own the customer's entire lifecycle.

~~~mermaid
flowchart TD
    subgraph ORDER["Aggregate SalesOrder"]
        ROOT["SalesOrder root<br/>id = 500"]
        CHILD["OrderLine<br/>lineId = a1"]
        ROOT -->|"own / manage"| CHILD
    end
    CUSTOMER["Customer root<br/>id = 42"]
    PRODUCT["Product root<br/>id = 20"]
    ROOT -.->|"customerId = 42"| CUSTOMER
    CHILD -.->|"productId = 20"| PRODUCT
~~~

- Solid line: ownership within the aggregate.
- Dashed line: reference to another aggregate by ID.

## 10. @Id, @Version, and business state do not replace each other

In an aggregate root, three kinds of information are commonly found:

~~~java
@Id
private Long id;

@Version
private Long version;

private OrderStatus status;
~~~

| Property | Meaning | When does it change? |
|---|---|---|
| `id` | Root identity | Assigned at creation, kept stable |
| `version` | Technical token for optimistic locking | Incremented on successful update via the version mechanism |
| `status` | Business state | Changes according to business actions |

An order can transition `DRAFT → CONFIRMED` without its ID changing. The version can also increment when another field changes even if the status stays the same.

### 10.1. Optimistic locking uses the root's version

When two transactions read the same order at version 3:

~~~text
Transaction A                 Transaction B
-------------                 -------------
Read order #500, v3           Read order #500, v3
Change line A                  Change line B
Save -> success, v4
                              Save using old v3
                              -> optimistic lock conflict
~~~

`@Version` detects that a transaction is saving based on stale state. This is a concurrency protection mechanism at the aggregate root level, not the identity of the root or child.

When a conflict occurs, the application needs to decide whether to reload, report an error, or retry according to business rules. Do not automatically retry an operation with side effects without ensuring idempotency.

### 10.2. Child status and root status

If a line has its own status, such as `ACTIVE`, `CANCELLED`, or `FULFILLED`, determine whether it is truly a rule belonging to the order.

If every line change must be controlled by the root and remain consistent with the order, the line status can be an attribute of the child entity. If the line has an independent lifecycle, is processed by multiple systems, and needs independent updates, re-examine the aggregate boundary.

Do not create a `lineVersion` just because `version` already exists on the root. Understand that Spring Data JDBC enforces optimistic locking by aggregate root and design accordingly.

## 11. When should you use a natural key, surrogate key, or composite key?

### 11.1. Natural key

A natural key is an attribute with business meaning, such as a SKU or order number. It is readable and useful for lookups, but it may change due to business processes.

If the order number is allowed to be edited, do not use it as the sole ID for all internal references.

### 11.2. Surrogate key

A surrogate key is a technical ID such as `BIGINT IDENTITY` or UUID. It carries no business meaning, but it is stable and convenient for linking.

For an aggregate root, a surrogate key is often a practical choice if the business key might change or has complex rules.

### 11.3. Composite key

A composite key combines multiple columns to ensure uniqueness:

~~~sql
PRIMARY KEY (order_id, line_id)
~~~

This clearly expresses that the child ID is only unique within an order. Another option for a List collection is `(order_id, line_position)`; however, that key depends on position, so it is unsuitable as a stable identity if elements can be reordered.

| Option | Pros | Limitations |
|---|---|---|
| Natural key | Meaningful in business, easy to read | May change or be long |
| Surrogate root ID | Stable, easy to reference | Requires keeping a separate business key if needed |
| Composite child key | Expresses ownership and local uniqueness | References require all key components |
| List position key | Simple ordered collection mapping | Changes on insert/delete/reorder |

## 12. Modifying child entities and saving the aggregate

Spring Data JDBC does not use a JPA-style persistence context or dirty checking. Modifying an object in memory does not automatically save it to the database. The application calls `save(root)` to persist the aggregate state.

Service example:

~~~java
@Service
public class OrderService {

    private final SalesOrderRepository repository;

    public OrderService(SalesOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void changeLineQuantity(
            Long orderId,
            UUID lineId,
            int quantity
    ) {
        SalesOrder order = repository.findById(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order not found"));

        order.changeLineQuantity(lineId, quantity);

        repository.save(order);
    }
}
~~~

Operation flow:

~~~text
Load SalesOrder by root ID
        |
        v
Find child by child ID within root
        |
        v
Call root behavior to change child
        |
        v
Save aggregate root
        |
        v
Database persists aggregate state
~~~

When saving an aggregate with a collection, Spring Data JDBC may delete and re-insert child records to reflect the new collection state. Therefore, do not assume that changing a single property of one line will always result in exactly one `UPDATE` statement for that line.

A stable child identity is still useful for the domain and API, but it does not mean the framework will dirty-check children by ID.

## 13. Splitting a child into a root when identity needs to be independent

Suppose an order line can now be updated directly by the fulfillment system, and referenced by shipment, invoice, and return processes. If it has an independent lifecycle, you can transition to this model:

~~~text
SalesOrder aggregate
    id
    status
    customerId

OrderLine aggregate
    id
    orderId
    productId
    quantity
    unitPrice
    fulfillmentStatus
~~~

Then:

- `OrderLine` has its own repository.
- `SalesOrder` only references lines by ID or queries lines through an appropriate relationship.
- Rules between the order and its lines must be coordinated at the application layer.
- You can no longer assume a single `save(SalesOrder)` manages the entire lifecycle of order lines.

This is a major decision. When splitting an aggregate, a business operation may have to coordinate multiple transactions or an eventual consistency workflow. Only split when the benefits of an independent lifecycle justify accepting that complexity.

## 14. Common design mistakes

| Misconception | Consequence | Correct way of thinking |
|---|---|---|
| Using List position as a business ID | Insert/delete causes the ID to change | Use a Map key or a stable child ID |
| Thinking a child table with its own PK must have a repository | Loses root control | Distinguish SQL keys from aggregate roots |
| Generating a new ID on every child update | The same entity is treated as a new object | Keep identity stable across attribute changes |
| Using a mutable name/code as the root ID | References break easily when business data changes | Use a surrogate key or an immutable business key |
| Using a child ID across multiple aggregates while the child is still managed by a root | Ambiguous ownership, hard to synchronize | Consider promoting the child to a root or referencing only through the root |
| Allowing services to mutate the Map/List directly | Bypasses invariants | Encapsulate collections and expose behavior on the root |
| Using `@Version` as an ID | Confuses optimistic lock with identity | ID identifies; version controls updates |
| Assuming UUID means an independent aggregate | Chooses the wrong domain boundary | Identity does not determine ownership |

## 15. Workflow for choosing identities in a new model

When designing an aggregate, you can follow this order.

**Step 1 — Identify the root.** Which root is the single entry point for changes that must be consistent together?

**Step 2 — Choose the root ID.** Use a stable, immutable ID; decide between database-generated or application-generated.

**Step 3 — Classify child objects.** Which objects are entities with identity? Which are only value objects identified by value?

**Step 4 — Decide child identity.** Does the child need to be stably distinguished across edits or reordering? If so, use a local domain key or another suitable identity.

**Step 5 — Choose collection mapping.**
- `List`: when order is central and position can serve as the collection key.
- `Map`: when the key is a stable identity or business key of the entry.
- Other collections: choose only after understanding how the framework maps keys and equality.

**Step 6 — Design SQL keys.** Choose primary key, foreign key, unique constraint, and indexes suited to the ID semantics.

**Step 7 — Design external references.** Other aggregates reference the root by ID. Avoid letting other aggregates depend on a child that is still within the root's lifecycle.

**Step 8 — Protect state.** Use domain methods to preserve invariants, `@Version` when optimistic locking is needed, and transactions for write operations.

~~~text
Business requirement
       |
       v
Choose aggregate root
       |
       +---- Stable Root ID
       |
       v
Classify internal components
       |
       +---- Value object -> identity by value
       |
       +---- Child entity -> local identity if needed
       |                       |
       |                       +--> List position?
       |                       +--> Map key?
       |
       v
Map with @MappedCollection
       |
       v
Design PK/FK/UNIQUE in schema
       |
       v
Operate on child through root
       |
       v
Repository saves aggregate + version controls concurrency
~~~

## 16. Reasoning exercises

**Scenario A — Two identical lines**

An order has two lines with the same `productId`, `quantity`, and `unitPrice`. The user wants to delete specifically the second line. Can those three attributes alone be used to locate the line?

**Hint:** No, if two lines can be identical. A local identity is needed, such as a UUID Map key.

**Scenario B — A list that can be reordered**

An order displays lines in an order chosen by the user. The API currently uses `line_position` as the ID. After reordering, what happens?

**Hint:** The position changes according to the new order. If the API needs a long-lived reference to the same line, use a separate stable ID.

**Scenario C — Child has a primary key**

The `order_lines` table has primary key `(order_id, line_id)`. Is it mandatory to create `OrderLineRepository`?

**Hint:** No. A SQL PK does not make a child an aggregate root. If the child still belongs to the order lifecycle, the root continues to manage it.

**Scenario D — Two systems need to edit order lines independently**

The fulfillment service needs to change the status of individual order lines in its own lifecycle. Should all lines continue to be kept inside the order aggregate?

**Hint:** Consider splitting `OrderLine` into an aggregate root or designing an appropriate coordination workflow. Base the decision on ownership and invariants, not solely on whether the table has an ID.

**Scenario E — Root status and version**

An order changes status from `DRAFT` to `CONFIRMED`, and the version increments at the same time. Does the ID change?

**Hint:** No. The ID is stable; status is the business state; version is a technical token for concurrent updates.

## 17. Key takeaways

| Component | Meaning |
|---|---|
| `@Id` on aggregate root | Identity for the repository to manage the aggregate |
| Root ID | Stable throughout the entire root lifecycle |
| Child identity | Distinguishes child entities, typically scoped within the root |
| `@MappedCollection.idColumn` | Column linking the child to the root |
| `@MappedCollection.keyColumn` | Column storing the Map key or collection position/key |
| List position | Ordering, usually not a stable ID |
| Map key | Can serve as a local identity for a child |
| SQL primary key | Guarantees uniqueness in the database |
| `@Version` | Detects update conflicts |
| Value object | Identified by value, does not need an ID |

**Identity must reflect the business lifecycle.** The root has a stable ID so external callers can find and reference it. A child entity only needs its own identity when the business must distinguish it over time; that identity can live in a Map key or a composite key with the root ID. Value objects are identified by value. When these roles are designed properly, Spring Data JDBC can persist aggregates consistently without turning every child table into an independent repository.
