# Multi-Level Ownership Relationships and Table Operation Ordering

In Spring Data JDBC, an aggregate can contain multiple levels of owned objects: the aggregate root manages child entities, and child entities can in turn manage grandchild entities. When mapped to a database, each level can reside in its own table, linked by a foreign key pointing to the **primary key of its direct parent object**.

This design must clarify two things:

- **Ownership in the domain:** which object controls the lifecycle and is allowed to modify which object?
- **Dependencies in the database:** which table must have a parent record before inserting a child record, and which table must be deleted first to avoid violating foreign keys?

This lesson uses the example of an order having multiple shipments, with each shipment having multiple parcels:

~~~text
PurchaseOrder (aggregate root)
    |
    +-- Shipment (child entity)
    |      |
    |      +-- Parcel (grandchild entity)
    |      +-- Parcel
    |
    +-- Shipment
           |
           +-- Parcel
~~~

This entire tree belongs to one aggregate if its components share the same consistency boundary and lifecycle. In that case, the application operates through `PurchaseOrderRepository`; do not create separate repositories for `Shipment` or `Parcel` simply because they are stored in separate tables.

## 1. What is multi-level ownership?

An ownership relationship describes how a parent object controls the lifecycle of a child object. If a child object is removed from the aggregate, Spring Data JDBC treats that referenced object as a component to be removed from the aggregate's persisted data upon saving.

For example:

- `PurchaseOrder` owns `Shipment` instances.
- Each `Shipment` owns `Parcel` instances.
- A `Parcel` does not exist independently of its shipment.
- A `Shipment` has no separate repository if it is still managed solely through the order.

This is a one-parent-many-children relationship at each level. A child object belongs to one owner inside the aggregate; the same entity should not be used as a child of two different roots.

### 1.1. Ownership vs. reference

Not every relationship between two objects is an ownership relationship.

| Relationship | Example | How to express |
|---|---|---|
| Root owns child | `PurchaseOrder` → `Shipment` | Nested entity / `@MappedCollection` |
| Child owns grandchild | `Shipment` → `Parcel` | Nested `@MappedCollection` |
| Aggregate references another aggregate | `Shipment` → `Warehouse` | ID or `AggregateReference` |
| Multiple aggregates share an object | Multiple orders share a `Customer` | Separate aggregate, referenced by ID |

Spring Data JDBC restricts managed entity relationships within an aggregate to one-to-one or one-to-many forms. Many-to-one or many-to-many relationships typically mark boundaries between aggregates; in those cases, reference by ID or `AggregateReference`.

For example, one warehouse can serve many shipments. Do not embed the entire `Warehouse` into each `Shipment` as an owned child entity. You can store `warehouseId` or use `AggregateReference<Warehouse, Long>`.

### 1.2. Why must there be one clear owner?

If the same child entity is referenced by two roots, deleting or saving one root could alter data that the other root relies on. Lifecycle rules would become ambiguous.

An aggregate should have an ownership tree structure:

~~~text
One root
   |
   +-- Child A
   |     +-- Grandchild A1
   |     +-- Grandchild A2
   |
   +-- Child B
         +-- Grandchild B1
~~~

Links referencing other aggregates are separate edges, not ownership branches in this tree.

## 2. From the Java model to foreign keys

Spring Data JDBC uses `@MappedCollection` to configure collections stored in separate tables. Two key attributes:

- `idColumn`: foreign key column in the child table, referencing the primary key of the **direct parent object**.
- `keyColumn`: column storing the `List` position or `Map` key.

At nested levels, the rule applies per relationship. If `Shipment` has its own ID, the `parcels` table can hold `shipment_id` referencing `shipments.id`.

~~~text
Java object graph                         Relational tables

PurchaseOrder (id=100)                    purchase_orders
  |                                          id = 100
  +-- Shipment (id=700)                       |
  |      |                                    v
  |      +-- Parcel                           shipments
  |      +-- Parcel                             id = 700
  |                                             order_id = 100
  +-- Shipment                                  |
                                                v
                                              parcels
                                                shipment_id = 700
~~~

Crucial point: `parcels.shipment_id` references `shipments.id`, not `purchase_orders.id` directly. Each level uses the key of its direct owner to express the relationship.

## 3. Designing a three-level example

Suppose business rules specify:

- An order has many shipments.
- Each shipment has many parcels.
- A shipment belongs to exactly one order.
- A parcel belongs to exactly one shipment.
- Shipment contents cannot be modified after the order is closed.
- Parcels only have meaning within their shipment.

| Domain type | Role | Table | Link key |
|---|---|---|---|
| `PurchaseOrder` | Aggregate root | `purchase_orders` | `id` |
| `Shipment` | Level-1 child entity | `shipments` | `order_id` |
| `Parcel` | Level-2 child entity | `parcels` | `shipment_id` |

We give `Shipment` its own ID because the `Parcel` level needs to reference `Shipment`'s primary key. `Parcel` does not need its own ID in this example; the pair `(shipment_id, parcel_no)` identifies a parcel within a shipment.

## 4. Mapping PurchaseOrder owning Shipment

Aggregate root:

~~~java
package com.example.shipping.order.domain;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    @MappedCollection(
            idColumn = "order_id",
            keyColumn = "shipment_no"
    )
    private List<Shipment> shipments = new ArrayList<>();

    private PurchaseOrder() {
    }

    private PurchaseOrder(String status) {
        this.status = status;
    }

    public static PurchaseOrder open() {
        return new PurchaseOrder("OPEN");
    }

    public void addShipment(Shipment shipment) {
        if (!"OPEN".equals(status)) {
            throw new IllegalStateException(
                    "Cannot add a shipment to a closed order"
            );
        }
        shipments.add(shipment);
    }

    public void close() {
        if (shipments.isEmpty()) {
            throw new IllegalStateException(
                    "Cannot close an order without shipments"
            );
        }
        status = "CLOSED";
    }

    public void addParcel(int shipmentIndex, Parcel parcel) {
        if (!"OPEN".equals(status)) {
            throw new IllegalStateException(
                    "Cannot change shipments of a closed order"
            );
        }
        shipments.get(shipmentIndex).addParcel(parcel);
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public List<Shipment> getShipments() {
        return Collections.unmodifiableList(shipments);
    }
}
~~~

`@MappedCollection(idColumn = "order_id")` requires the `shipments` table to have an `order_id` column referencing `purchase_orders.id`.

Because the property is a `List`, a key column is needed to store element positions. Here the column is named `shipment_no`; in this mapping it is the **element position in the List**, not automatically a stable business shipment code.

## 5. Mapping Shipment owning Parcel

Level-one child entity:

~~~java
package com.example.shipping.order.domain;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("shipments")
public class Shipment {

    @Id
    private Long id;

    private String carrierCode;

    @MappedCollection(
            idColumn = "shipment_id",
            keyColumn = "parcel_no"
    )
    private List<Parcel> parcels = new ArrayList<>();

    private Shipment() {
    }

    public Shipment(String carrierCode) {
        if (carrierCode == null || carrierCode.isBlank()) {
            throw new IllegalArgumentException(
                    "Carrier code is required"
            );
        }
        this.carrierCode = carrierCode;
    }

    void addParcel(Parcel parcel) {
        parcels.add(parcel);
    }

    public Long getId() {
        return id;
    }

    public String getCarrierCode() {
        return carrierCode;
    }

    public List<Parcel> getParcels() {
        return Collections.unmodifiableList(parcels);
    }
}
~~~

Notably, `Shipment` has `@Id` even though it is not the aggregate root. This ID is the primary key of the record in the `shipments` table, and it also allows the `parcels` table to reference a specific shipment.

`@MappedCollection(idColumn = "shipment_id")` is placed on `Shipment`'s `parcels` property, so `shipment_id` in the `parcels` table references `shipments.id`.

Do not interpret `@Id` on `Shipment` as permission for the application to create a `ShipmentRepository` and modify shipments outside `PurchaseOrder`. The aggregate root role still belongs to `PurchaseOrder`.

### 5.1. Level-two child entity Parcel

~~~java
package com.example.shipping.order.domain;

import java.math.BigDecimal;
import org.springframework.data.relational.core.mapping.Table;

@Table("parcels")
public class Parcel {

    private String trackingCode;
    private BigDecimal weightKg;

    private Parcel() {
    }

    public Parcel(String trackingCode, BigDecimal weightKg) {
        if (trackingCode == null || trackingCode.isBlank()) {
            throw new IllegalArgumentException(
                    "Tracking code is required"
            );
        }
        if (weightKg == null || weightKg.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Weight must be positive"
            );
        }

        this.trackingCode = trackingCode;
        this.weightKg = weightKg;
    }

    public String getTrackingCode() {
        return trackingCode;
    }

    public BigDecimal getWeightKg() {
        return weightKg;
    }
}
~~~

`Parcel` has no separate `@Id`. In the example, it is identified by its position in a `Shipment`'s `List`. The table uses a composite key `(shipment_id, parcel_no)`.

If business rules require a stable parcel code referenced by another shipping system, add an appropriate identifier. You can use `Map<ParcelId, Parcel>` with `keyColumn` storing the Map key. Do not use a `List` position as a durable ID because inserting, removing, or sorting can change positions.

## 6. Corresponding relational schema

Sample DDL for PostgreSQL:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT ck_purchase_order_status
        CHECK (status IN ('OPEN', 'CLOSED', 'CANCELLED'))
);

CREATE TABLE shipments (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    shipment_no INTEGER NOT NULL,
    carrier_code VARCHAR(80) NOT NULL,

    CONSTRAINT fk_shipment_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_shipment_order_position
        UNIQUE (order_id, shipment_no),

    CONSTRAINT ck_shipment_no
        CHECK (shipment_no >= 0)
);

CREATE TABLE parcels (
    shipment_id BIGINT NOT NULL,
    parcel_no INTEGER NOT NULL,
    tracking_code VARCHAR(100) NOT NULL,
    weight_kg NUMERIC(10, 3) NOT NULL,

    CONSTRAINT pk_parcel
        PRIMARY KEY (shipment_id, parcel_no),

    CONSTRAINT fk_parcel_shipment
        FOREIGN KEY (shipment_id)
        REFERENCES shipments(id)
        ON DELETE CASCADE,

    CONSTRAINT uq_parcel_tracking
        UNIQUE (tracking_code),

    CONSTRAINT ck_parcel_no
        CHECK (parcel_no >= 0),

    CONSTRAINT ck_parcel_weight
        CHECK (weight_kg > 0)
);

CREATE INDEX idx_shipments_order_id
    ON shipments(order_id);

CREATE INDEX idx_parcels_shipment_id
    ON parcels(shipment_id);
~~~

Key constraints:

- `shipments.order_id` references `purchase_orders.id`.
- `parcels.shipment_id` references `shipments.id`.
- `shipment_no` is the `List` position within an order.
- `parcel_no` is the `List` position within a shipment.
- `tracking_code` has a unique constraint if business rules require tracking codes to be globally unique across the system.

`ON DELETE CASCADE` on both foreign keys expresses the policy of deleting child records when the parent record is deleted. This is database-layer behavior. Spring Data JDBC also manages components belonging to the aggregate when deleting or saving the root; do not confuse `ON DELETE CASCADE` with JPA's cascade annotations.

In a real system, decide whether physical deletion of orders/shipments is permitted or whether status should simply transition to `CANCELLED`. For shipping and audit data, soft delete or retaining history is usually more appropriate than physical deletion.

## 7. Relationship diagram and foreign key direction

~~~mermaid
erDiagram
    PURCHASE_ORDERS ||--o{ SHIPMENTS : owns
    SHIPMENTS ||--o{ PARCELS : owns

    PURCHASE_ORDERS {
        bigint id PK
        bigint version
        varchar status
    }

    SHIPMENTS {
        bigint id PK
        bigint order_id FK
        integer shipment_no
        varchar carrier_code
    }

    PARCELS {
        bigint shipment_id PK,FK
        integer parcel_no PK
        varchar tracking_code
        numeric weight_kg
    }
~~~

Ownership direction in Java goes from parent down to child:

~~~text
PurchaseOrder -> Shipment -> Parcel
~~~

Foreign keys in the database live on the child table side:

~~~text
shipments.order_id -> purchase_orders.id
parcels.shipment_id -> shipments.id
~~~

This is the general pattern for multi-level ownership relationships. If an additional `ParcelItem` level were added, that table would hold an FK to `Parcel`'s primary key, and write operations would continue respecting that dependency.

## 8. Insert order when creating a new aggregate

When saving a new aggregate, Spring Data JDBC inserts the aggregate root first, then inserts directly and indirectly referenced entities.

For the example above, the foreign key relationships require the order:

~~~text
1. INSERT purchase_orders
       |
       | generates purchase_orders.id
       v
2. INSERT shipments
       |
       | obtains shipments.id
       v
3. INSERT parcels
~~~

Reason:

- `shipments.order_id` needs the value of `purchase_orders.id`.
- `parcels.shipment_id` needs the value of `shipments.id`.
- Inserting `parcels` before `shipments` exists cannot satisfy the FK.

Use case example:

~~~java
@Transactional
public Long createOrder() {
    PurchaseOrder order = PurchaseOrder.open();

    Shipment shipment = new Shipment("FAST-EXPRESS");
    shipment.addParcel(
            new Parcel("TRACK-001", new BigDecimal("1.250"))
    );
    shipment.addParcel(
            new Parcel("TRACK-002", new BigDecimal("0.850"))
    );

    order.addShipment(shipment);

    PurchaseOrder saved = orderRepository.save(order);
    return saved.getId();
}
~~~

When the database generates IDs for the root and `Shipment`, Spring Data JDBC uses those values to write the lower levels. Use the object returned from `save(...)` to get the saved root's ID.

The order above is the logical dependency order between tables. Do not rely on a fixed order among sibling records that have no dependency relationship; if you need to see the exact SQL, enable JDBC logging or verify via integration tests on the real database.

## 9. Delete and update order with foreign keys

### 9.1. Deleting an aggregate

If the database uses plain FKs without cascade, dependent records must be deleted before parent records:

~~~text
DELETE parcels
       |
       v
DELETE shipments
       |
       v
DELETE purchase_orders
~~~

If `purchase_orders` is deleted first, the database can reject it because `shipments` still references it. Likewise, `shipments` cannot be deleted while `parcels` still references it.

With `ON DELETE CASCADE`, the database can automatically delete child levels when the root is deleted. However, align the cascade policy between the schema and how Spring Data JDBC manages the aggregate; do not arbitrarily add cascade to references pointing to other aggregates.

Spring Data JDBC provides aggregate deletion through the root repository. The goal is to delete the root along with every entity belonging to that aggregate. There is no need to call child repositories manually to delete them when the entities are genuinely components of the same aggregate.

### 9.2. Saving an existing aggregate

When saving an existing aggregate root, Spring Data JDBC's standard persistence mechanism:

1. Deletes referenced entities inside the aggregate.
2. Updates the aggregate root row.
3. Re-inserts referenced entities according to the current state.

With multi-level relationships, the deletion step must respect foreign keys at child levels; the re-insertion step must follow parent-before-child order.

~~~text
DELETE descendants
        |
        v
UPDATE aggregate root
        |
        v
INSERT direct children
        |
        v
INSERT nested children
~~~

Spring Data JDBC does not keep an old snapshot of the entire aggregate to diff field-by-field like JPA's dirty checking. Consequently, even when changing only one small property on a `Parcel`, calling `save(order)` can result in deleting and re-inserting the referenced entities.

This has performance implications:

- The larger the aggregate, the more SQL operations may occur.
- Child tables with unique constraints or FKs from external systems must be designed to tolerate this replacement strategy.
- If you frequently need to update a single record independently, revisit the aggregate boundary.
- If a specialized update operation is needed, you can use deliberate custom SQL/repository queries, provided root invariants are still protected.

### 9.3. Why can't you arbitrarily UPDATE just one child table?

If `Parcel` is a component belonging to `Shipment`, and `Shipment` belongs to `PurchaseOrder`, updating `Parcel` directly could bypass `Shipment` and `PurchaseOrder` rules.

For example, an order is already closed, yet a service updates `parcels.weight_kg` directly. The database might still accept it because FKs and CHECKs pass, while business rules forbid modifying shipment contents after closing the order.

The aggregate root guards that rule. Any custom SQL must include equivalent status and concurrency checks.

## 10. Transactions protect multi-level operation sequences

When a use case modifies multiple tables within the same aggregate, the SQL statements must run inside a single transaction to ensure atomicity.

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository repository;

    public OrderApplicationService(
            PurchaseOrderRepository repository
    ) {
        this.repository = repository;
    }

    @Transactional
    public void addParcel(
            Long orderId,
            int shipmentIndex,
            String trackingCode,
            BigDecimal weightKg
    ) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order not found"));

        order.addParcel(
                shipmentIndex,
                new Parcel(trackingCode, weightKg)
        );

        repository.save(order);
    }
}
~~~

This example illustrates loading the root, accessing a child component, and saving the root. In a real domain, expose a method like `PurchaseOrder.addParcel(...)` so the root itself checks order status and locates the shipment; do not let the service mutate internal collections directly.

If inserting at the `parcels` level fails due to a duplicate `tracking_code`, the transaction must roll back earlier operations of that save. Without a transaction wrapping a sequence of multiple repository calls, there is a risk of partial data being written.

Spring Data JDBC CRUD repositories have their own transaction semantics; `@Transactional` on the application service clearly defines the boundary for a use case coordinating multiple operations.

### 10.1. Optimistic locking on the aggregate root

If the root has `@Version`, Spring Data JDBC checks the version on update. When another transaction has modified the root, the save can fail with `OptimisticLockingFailureException`.

~~~text
Transaction A                 Transaction B
-------------                 -------------
Read order #100, v4           Read order #100, v4
Add parcel A                  Add parcel B
Save -> root v5
                              Save using v4
                              -> optimistic lock conflict
~~~

The version belongs to the root and protects aggregate updates. It does not replace foreign keys across levels, nor does it automatically protect custom SQL operations that bypass the root.

When a conflict occurs, the application must reload and apply business policy; it should not blindly overwrite the newer state.

## 11. Multi-level relationships and many-to-many relationships

A common mistake is seeing a table with multiple foreign keys and concluding all those relationships belong to one aggregate.

For example, `Shipment` has a `Warehouse`:

- One warehouse can be used by many shipments.
- One shipment selects one warehouse.
- A warehouse has a lifecycle independent of the order.
- Deleting or changing an order must not delete the warehouse.

This is a reference from one aggregate to another, not ownership. It can be represented as:

~~~java
import org.springframework.data.relational.core.mapping.AggregateReference;

public class Shipment {

    private AggregateReference<Warehouse, Long> warehouse;

    // ...
}
~~~

And the table:

~~~sql
ALTER TABLE shipments
    ADD COLUMN warehouse_id BIGINT NOT NULL;

ALTER TABLE shipments
    ADD CONSTRAINT fk_shipment_warehouse
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id);
~~~

`warehouse_id` is a reference to another aggregate. Spring Data JDBC does not load and delete `Warehouse` as a child entity of `PurchaseOrder`.

If there is a many-to-many relationship between two independent sets—for example, products and promotions—an appropriate association model (an association table or a dedicated association aggregate) is normally needed. Do not build a cyclic object graph expecting Spring Data JDBC to manage it as a single aggregate.

## 12. Choosing ON DELETE CASCADE, RESTRICT, or soft delete

The deletion policy in the database must reflect the business lifecycle.

| Policy | Behavior | Appropriate when |
|---|---|---|
| `ON DELETE CASCADE` | Deletes child records when parent is deleted | Child components have no meaning existing independently |
| `ON DELETE RESTRICT` / `NO ACTION` | Blocks deleting parent while referencing records remain | Historical data must be preserved or other aggregates reference it |
| Soft delete | Keeps records, changes status | Needed for audit, history lookup, or process compliance |

For `purchase_orders → shipments → parcels`, cascade can make sense if physically deleting an order means deleting the entire data tree. However, in real systems, shipped orders usually need to be kept for auditing; in that case, transitioning status or archiving history is often more appropriate.

For `shipments → warehouses`, cascade from shipment to warehouse is normally not used because the warehouse is not owned by the shipment.

**Do not configure cascade just to make an FK error go away.** Determine which data is genuinely allowed to be deleted alongside its parent data.

## 13. Limits and costs of deeply nested aggregates

Multi-level ownership helps the domain reflect business structure, but you should not nest deeply just to build a pretty object tree.

### 13.1. Write cost scales with the whole tree

If an order has 30 shipments, and each shipment has 100 parcels, the aggregate can contain 3,000 child entities. One small change can cause Spring Data JDBC to delete and re-insert many referenced records.

Before adding another level into an aggregate, ask:

- Does that level need to change in the same use case as the root?
- Must invariants be maintained across all levels?
- What is the maximum number of elements?
- How frequently is each level updated?
- Does any system need to update a single element independently?

If a level is large and has an independent lifecycle, splitting it into a separate aggregate may make more sense.

### 13.2. Loading multiple levels may use multiple SQL statements

In traditional loading, Spring Data JDBC loads the root and referenced entities with separate queries. Single Query Loading was introduced in Spring Data JDBC 3.2, but it has conditions and limitations; nested collections are a case not supported in that mode according to current documentation.

Therefore, do not assume a multi-level aggregate is always loaded with a single SQL statement. When performance matters, measure query counts and returned data, and consider dedicated projections/read models for screens.

### 13.3. Avoid ownership cycles

Do not design:

~~~text
Order -> Shipment -> Parcel -> Order
~~~

An object cycle prevents ownership from being a clean tree and makes relationship mapping difficult. If `Parcel` needs to know the order code, pass the needed info or use a reference ID at the application layer; do not create a back-reference object closing the loop.

Spring Data JDBC also discourages keeping back-reference properties or collection keys in domain objects solely to mirror FK columns managed by the framework. If those values are truly needed on the object, they can be populated after conversion via a callback and transient properties.

## 14. Operation ordering in schema migrations

The order of creating tables and constraints in migrations should also follow dependencies:

1. Create root table `purchase_orders`.
2. Create `shipments` table with FK to `purchase_orders`.
3. Create `parcels` table with FK to `shipments`.
4. Create additional indexes and constraints.

When rolling back a migration or dropping a schema, the order is usually reversed:

1. Drop `parcels` table.
2. Drop `shipments` table.
3. Drop `purchase_orders` table.

~~~sql
DROP TABLE parcels;
DROP TABLE shipments;
DROP TABLE purchase_orders;
~~~

If using a migration framework, version schema changes and do not edit migrations already applied to shared environments. When renaming FK columns or restructuring child levels, add data migrations if existing records must be preserved.

Table-creation DDL is not the SQL execution order when `repository.save(...)` runs. Both workflows relate to FKs, but they occur at different times.

## 15. Verifying operation order with integration tests and SQL logs

To verify multi-level mapping, test against the application's actual database and JDBC driver.

Valuable test scenarios:

- Save a new order with one shipment and two parcels; verify root, child, and grandchild are created.
- Reload the root; verify the levels are reconstructed accurately.
- Add a parcel and save; verify the final state reflects the object graph.
- Remove a shipment from the collection and save; verify parcels belonging to that shipment are gone.
- Delete the aggregate; verify all components are handled per policy.
- Attempt to write an invalid FK; verify the database rejects it and the transaction rolls back.
- Have two transactions concurrently update a root with `@Version`; verify the conflict is detected.

You can enable JDBC SQL logging to observe `INSERT`, `DELETE`, and `UPDATE` statements. When analyzing, compare the ordering against FK dependencies rather than merely counting SQL statements.

Do not write a unit test that only asserts annotations exist. What needs verification is **table structure, linked data, transactions, and actual repository behavior**.

## 16. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Every table must have its own repository | Repositories are typically created for aggregate roots; child tables can be managed by the root |
| `@Id` on a child turns it into a root | `@Id` can be the PK of a child table; ownership is still determined by the root |
| `idColumn` always points to the root ID | For nested relationships, it references the primary key of the direct parent entity |
| Just insert the root, child order does not matter | FKs require parent records to exist before child records |
| With `ON DELETE CASCADE`, the domain ignores lifecycle | Cascade is a database policy; the domain still decides whether deletion is permitted |
| `save(root)` only updates the changed element | Spring Data JDBC may delete and re-insert referenced entities |
| Every FK relationship is ownership | An FK only represents a storage link; lifecycle and aggregate boundaries must be evaluated |
| Transactions are only needed for the root table | Saving an aggregate once can affect multiple tables; transactions protect atomicity |
| Nested collections always load with one query | Loading behavior depends on version/features; do not assume a single SQL statement |

## 17. Workflow for designing multi-level ownership relationships

When translating a business model into Spring Data JDBC mapping, you can follow these steps:

**Step 1 — Choose the aggregate root.** Identify the single entry point for operations requiring consistency.

**Step 2 — Draw the ownership tree.** Every child has one clear parent; add levels only when lifecycle semantics justify them.

**Step 3 — Separate external references.** Many-to-one or many-to-many usually uses ID/`AggregateReference`, not embedded owned entities.

**Step 4 — Decide IDs at each level.** Any level that needs to be referenced by FK from a lower level needs an appropriate primary key. `List`/`Map` collections have corresponding key columns.

**Step 5 — Map each relationship.** Use `@MappedCollection(idColumn=..., keyColumn=...)` with column names matching the schema. `idColumn` points to the direct parent's PK.

**Step 6 — Design PK/FK/UNIQUE/CHECK.** Protect uniqueness, integrity, and dependency order.

**Step 7 — Define deletion policy.** Choose cascade, restrict, or soft delete according to the real lifecycle.

**Step 8 — Anticipate SQL ordering.** Insert from parent down to child; delete in reverse to respect FKs. For updating existing aggregates, understand the strategy of deleting referenced entities, updating the root, and re-inserting entities.

**Step 9 — Wrap use cases in transactions.** Ensure multi-table operation sequences roll back together on failure.

**Step 10 — Measure aggregate size.** If a level becomes too large or needs independent updates, consider splitting aggregates and building coordination workflows.

~~~text
Business rules
      |
      v
Aggregate root
      |
      v
Ownership tree
      |
      +---- Child entity
      |        |
      |        +---- Nested child entity
      |
      +---- External aggregate reference (ID)
      |
      v
Tables + PK/FK/key columns
      |
      v
Insert: parent -> child -> grandchild
Update: delete references -> update root -> reinsert references
Delete: descendants -> ancestors (or DB cascade)
      |
      v
Transaction + integration verification
~~~

## 18. Reasoning exercises

**Scenario A — Adding another level of detail**

A `PurchaseOrder` has many `Shipment`s, each `Shipment` has many `Parcel`s, and each `Parcel` has many `ParcelItem`s. Which table should the FK column of `ParcelItem` reference?

**Hint:** If `Parcel` is the direct parent of `ParcelItem`, the FK must reference the primary key of `parcels`, not `purchase_orders`.

**Scenario B — Deleting a Shipment**

A shipment has 5 parcels. If the `parcels.shipment_id` FK has no cascade, can the `shipments` row be deleted first?

**Hint:** Not while parcels still reference it. Delete the `parcels` first or configure an appropriate cascade.

**Scenario C — Modifying one Parcel**

Only `weightKg` of one parcel is changed, then `orderRepository.save(order)` is called. Can you assume only a single UPDATE statement runs on the `parcels` table?

**Hint:** No. Spring Data JDBC may delete and re-insert referenced entities in the aggregate when saving an existing root.

**Scenario D — Shared Warehouse**

Many orders ship from the same warehouse. Should `Warehouse` be embedded as a child entity of every `PurchaseOrder`?

**Hint:** No. A warehouse has an independent lifecycle and is referenced by many aggregates; use an ID or `AggregateReference`.

**Scenario E — Closed order**

A service updates `parcels.tracking_code` directly via SQL, bypassing `PurchaseOrder`. The FK remains valid, yet business rules forbid editing closed orders. Where is the flaw?

**Hint:** SQL constraints cannot replace aggregate invariants. Custom operations must check root status and concurrency per business policy.

## 19. Takeaways

| Component | Role |
|---|---|
| Aggregate root | Entry point managing the entire ownership tree |
| Child entity | Component whose lifecycle is controlled by its parent/root |
| `@MappedCollection.idColumn` | FK to the direct parent's primary key |
| `@MappedCollection.keyColumn` | `List` position or `Map` key |
| `@Id` on child | Primary key for the child table when needed |
| Foreign key | Protects storage relationships |
| Insert | Root/parent first, child after |
| Delete | Child before parent, or use appropriate cascade |
| Update existing aggregate | Delete referenced entities, update root, re-insert entities |
| `@Transactional` | Protects use case atomicity |
| `@Version` | Detects concurrent update conflicts on the root |
| `AggregateReference` | References another aggregate by ID |

**Multi-level ownership must be clear in both the domain and the schema.** In Java, the root controls children and children control grandchildren. In the database, each child table holds an FK to its direct parent's primary key. Because FKs establish dependency order, inserts flow top-down from parent to child and deletes flow in reverse. Spring Data JDBC persists aggregates across the entire reference tree, so transactions, constraints, and aggregate size must be designed together.

## References

- [Spring Data Relational — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): `@MappedCollection`, back references, nested entities, and aggregate references.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): insert, update, and delete ordering for referenced entities when saving an aggregate.
- [Spring Data Relational — Lifecycle Events](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html): save/delete operation lifecycle on aggregate roots and callbacks.
