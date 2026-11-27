# Concept Map: Entity, Value Object, Aggregate, Repository, and Database Table

In **Spring Data Relational JDBC** (often shortened to **Spring Data JDBC**), we must view the same system from two sides:

- **Domain model:** which objects have their own identity, which data only carries meaning by its value, and which changes must be controlled together?
- **Relational model:** in which tables, columns, primary keys, and foreign keys is the information stored?

Spring Data JDBC bridges those two sides by mapping **aggregates** into relational data and providing **repositories** to read and write through the **aggregate root**. Understanding the five concepts—*entity, value object, aggregate, repository, and database table*—helps you design proper business boundaries before writing annotations or SQL statements.

## 1. Big Picture: Five Concepts Answering Five Different Questions

| Concept | Question to answer | Focus | Order example |
|---|---|---|---|
| **Entity** | "Is this still the same object when its attributes change?" | Identity and lifecycle | Order, order line within an order |
| **Value object** | "Are these two values equivalent in content?" | Value, typically immutable | Shipping address |
| **Aggregate** | "Which changes must follow shared rules?" | Consistency boundary and ownership | Order together with its lines and shipping address |
| **Repository** | "How does the application retrieve and persist an aggregate?" | Data access interface via the aggregate root | Order repository |
| **Database table** | "Where is object state physically stored?" | Columns, rows, keys, relational constraints | Orders table and order lines table |

These concepts **do not correspond one-to-one**: an aggregate can contain multiple entities and value objects, stored across multiple tables, yet typically has only **one repository for the aggregate root**.

## 2. Mapping from Business Objects to Data

Consider an order creation feature. An order has an identifier, status, shipping address, and multiple product lines; each line has a product, quantity, and unit price. The customer has a lifecycle independent of the order.

~~~mermaid
flowchart TB
    Service["Application / Use case"] --> Repo["PurchaseOrderRepository"]
    Repo -->|"load and save root"| Root

    subgraph Aggregate["Aggregate: PurchaseOrder"]
        Root["PurchaseOrder<br/>Entity + Aggregate Root"]
        Line["PurchaseOrderLine<br/>Child entity"]
        Address["ShippingAddress<br/>Value Object"]
        Root -->|"owns"| Line
        Root -->|"contains"| Address
    end

    Root -. "customerId" .-> Customer["Customer<br/>Independent aggregate"]
    Root -->|"data rows"| Orders[("purchase_orders")]
    Line -->|"data rows"| Lines[("purchase_order_lines")]
    Address -->|"ship_* columns"| Orders
    Lines -->|"FK: purchase_order_id"| Orders
~~~

**Solid lines within the aggregate** represent object ownership. The **dashed line via customerId** represents a reference to another aggregate by identity. The arrows to the cylinders illustrate how data is persisted; they do not mean that an entity must have exactly one table or that a value object always needs its own table.

## 3. Entity: Identified by Identity, Not Only by Attributes

An **entity** is an object with its own **identity** and lifecycle in the domain model. An order can change status from DRAFT to CONFIRMED and still remain **order number 1001**. Two orders with the same customer, same product lines, and same address are still two distinct orders if their identities differ.

For order lines, you may need to identify "which line was just edited," even when two lines have the same SKU and quantity. In that case, **PurchaseOrderLine** is an entity *inside* the order aggregate. It does not thereby become an aggregate root or become arbitrarily modifiable from outside.

At the Spring Data JDBC level:

- The **@Id** annotation identifies the ID property used for persistence; entities do not need JPA's **@Entity** annotation.
- **@Table** optionally specifies the table explicitly; by default, the framework applies a strategy to derive table/column names.
- A database ID assists with identifying records, while **business identity** may be a separate code. You should not assume the two kinds of identifiers are always synonymous.

**Distinction:** if you change the quantity on an order line, that entity may still be the same order line; if you completely change a shipping address, we usually treat it as a **new value**.

## 4. Value Object: Identified by Value

A **value object** represents a concept based on a set of attributes, **without needing its own identity**. For example, two addresses with the same street and city can be considered the same value under domain rules. An immutable type like a Java **record** fits well when all fields together form the object's value.

~~~java
public record ShippingAddress(String street, String city) {
    public ShippingAddress {
        if (street == null || street.isBlank()) {
            throw new IllegalArgumentException("Street is required");
        }
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("City is required");
        }
    }
}
~~~

Changing an address should be expressed as **assigning a new ShippingAddress**, rather than allowing external code to mutate individual fields inside it independently.

In the example below, Spring Data JDBC uses **@Embedded** to flatten ShippingAddress into the columns **ship_street** and **ship_city** right inside the orders table. This is **one mapping choice**, not the definition of a value object: a value object can also be converted into a single column using a converter, or stored in another structure if the design calls for it.

## 5. Aggregate: Boundary Preserving Business Invariants

An **aggregate** is a group of entities and value objects that must uphold shared **invariants**. Each aggregate has one **aggregate root**, which is the entity serving as the entry point for accessing and modifying that group.

In our example:

- **PurchaseOrder** is the root. Only the root exposes operations such as adding a line, changing the address, or confirming the order.
- **PurchaseOrderLine** is owned by the order; there is no business concept of "an order line existing independently outside an order."
- **ShippingAddress** is a value inside the order.
- **Customer** is a separate aggregate. The order only stores **customerId**, because a customer has an independent lifecycle.

Some invariants that can be enforced on the root:

1. Reject line quantities less than or equal to 0.
2. Disallow confirming an order when it has no lines.
3. Disallow modifying lines after confirmation (if business rules require it).

As a result, callers cannot update individual order lines directly in the database and accidentally bypass the order's rules.

**Aggregate boundaries differ from table boundaries:** an order together with its list of lines is one aggregate even though it is stored across two tables. Conversely, two rows linked by a foreign key do not necessarily belong to the same aggregate; the deciding criteria are **ownership and business consistency**.

### Aggregates Do Not Encompass Every Application Transaction

For instance, when confirming an order and deducting inventory, **PurchaseOrder** and **InventoryItem** may be two independent aggregates. In that case, an application service coordinates them, choosing an appropriate transaction/event/synchronization mechanism; you should not force them into the same aggregate just because one use case touches both.

In Spring Data JDBC, persisting an aggregate is typically performed with **save(root)**. For an existing aggregate, referenced child objects may be **deleted and re-inserted** while saving the full current state. Therefore, avoid treating **save(root)** as a minimal row-by-row update of child entities or as JPA's dirty checking mechanism.

## 6. Database Tables Are State Storage, Not Domain Boundaries

An illustrative relational schema might look like this (identity syntax and data types should be adjusted to match your database engine):

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    ship_street VARCHAR(200),
    ship_city VARCHAR(100)
);

CREATE TABLE purchase_order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL
        REFERENCES purchase_orders(id),
    line_position INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents BIGINT NOT NULL CHECK (unit_price_cents >= 0),
    UNIQUE (purchase_order_id, line_position)
);
~~~

| Domain model element | Storage location in the illustrative schema |
|---|---|
| Identity of PurchaseOrder | **purchase_orders.id** |
| Customer referenced by ID | **purchase_orders.customer_id** |
| Order status | **purchase_orders.status** |
| ShippingAddress | **purchase_orders.ship_street**, **ship_city** |
| Identity of each PurchaseOrderLine | **purchase_order_lines.id** |
| Order line ownership | **purchase_order_lines.purchase_order_id** (FK to root) |
| Line order within the list | **purchase_order_lines.line_position** |

**Primary keys (PK)** identify data rows; **foreign keys (FK)** maintain relational links; **CHECK/UNIQUE** protect certain conditions at the database level. They **complement** the business invariants on the aggregate root, but cannot express every rule by themselves, such as "an order may only be confirmed if it has at least one line."

The **customer_id** field may have a foreign key to the customers table if the schema requires it. Having an FK **does not force** Customer to become a child object of PurchaseOrder in the domain model.

## 7. How Does Spring Data JDBC Map an Aggregate?

The minimal example below demonstrates the core annotations. To use it in a project, place the Java types into appropriate files and add any remaining business operations.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;
import org.springframework.data.repository.CrudRepository;

@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    private Long customerId;
    private String status;

    @Embedded(onEmpty = Embedded.OnEmpty.USE_NULL, prefix = "ship_")
    private ShippingAddress shippingAddress;

    @MappedCollection(
        idColumn = "purchase_order_id",
        keyColumn = "line_position"
    )
    private List<PurchaseOrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
        // For the mapper to instantiate the object.
    }

    public PurchaseOrder(Long customerId, ShippingAddress shippingAddress) {
        if (customerId == null || shippingAddress == null) {
            throw new IllegalArgumentException("Customer and address required");
        }
        this.customerId = customerId;
        this.shippingAddress = shippingAddress;
        this.status = "DRAFT";
    }

    public void addLine(String sku, int quantity, long unitPriceCents) {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException("Order is already confirmed");
        }
        if (sku == null || sku.isBlank()
                || quantity <= 0 || unitPriceCents < 0) {
            throw new IllegalArgumentException("Invalid order line");
        }
        lines.add(new PurchaseOrderLine(sku, quantity, unitPriceCents));
    }

    public void confirm() {
        if (lines.isEmpty()) {
            throw new IllegalStateException("Cannot confirm an empty order");
        }
        status = "CONFIRMED";
    }

    public Long getId() {
        return id;
    }
}

// Value object: value fields reside in the same row as the root.
record ShippingAddress(String street, String city) {}

@Table("purchase_order_lines")
class PurchaseOrderLine {
    @Id
    private Long id;
    private String sku;
    private int quantity;
    private long unitPriceCents;

    protected PurchaseOrderLine() {}

    PurchaseOrderLine(String sku, int quantity, long unitPriceCents) {
        this.sku = sku;
        this.quantity = quantity;
        this.unitPriceCents = unitPriceCents;
    }
}

interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {}
~~~

**Reading the mapping diagram from the code:**

- **@Table("purchase_orders") + @Id:** PurchaseOrder is an entity stored in the orders table. In this model, it is also the aggregate root.
- **@Embedded(..., prefix = "ship_"):** fields of ShippingAddress become columns with the corresponding prefix in the root table. **OnEmpty.USE_NULL** returns **null** if all columns of the embedded value are null.
- **@MappedCollection:** PurchaseOrderLine instances are owned by the root; **idColumn** is the FK column pointing to the root, while **keyColumn** stores the element's position in the **List**.
- **CrudRepository<PurchaseOrder, Long>:** the repository operates on the **root**; no separate repository is needed for PurchaseOrderLine in this design.

Spring Data JDBC supports mapping child objects according to ownership relationships. It **does not operate like JPA**: there are no default lazy-loading proxies, no persistence context managing dirty checking, and no JPA **@OneToMany/@ManyToOne** annotations for declaring every relationship. If you reference another entity directly as a framework-mapped object, examine whether you are unintentionally pulling that entity into the same aggregate.

### Saving and Loading an Aggregate via Repository

~~~java
PurchaseOrder order = new PurchaseOrder(
    42L,
    new ShippingAddress("12 Nguyen Trai", "Ho Chi Minh City")
);
order.addLine("BOOK-01", 2, 150_000L);
order.addLine("PEN-02", 1, 20_000L);
order.confirm();

PurchaseOrder saved = repository.save(order);
Long orderId = saved.getId();

PurchaseOrder loaded = repository.findById(orderId)
    .orElseThrow();
~~~

In this usage snippet, **repository** is a variable of type PurchaseOrderRepository injected into a service class; the domain classes above only illustrate the mapping. When creating a new order, Spring Data JDBC writes the root table and child rows; when loading, it reconstructs the aggregate from the related rows according to the mapping. Calling **save** on an existing root can generate multiple SQL operations on child tables, including deleting and re-inserting them. If an application service performs multiple operations that must be consistent together, declare **@Transactional** with the appropriate business scope.

## 8. Repository: A Single Entry Point to the Aggregate Root

A repository represents a collection of aggregate roots that can be retrieved by identity or query:

~~~java
interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
    // Queries serving order use cases can be added here.
}
~~~

**A repository is not synonymous with a database table**, nor does every entity require a repository. In the example:

- PurchaseOrderRepository reads/writes **PurchaseOrder**, including parts owned inside the aggregate.
- Do not create PurchaseOrderLineRepository merely because a **purchase_order_lines** table exists.
- If a reporting screen needs to join multiple tables or multiple aggregates, use a **dedicated read model/query**; do not alter aggregate boundaries just to satisfy a display query.

The benefit is that state changes pass through the root, where business invariants are kept consistent. Only add a repository for a child entity when you genuinely redefine its ownership boundary and lifecycle.

## 9. Interpreting Relationship Types Correctly

Suppose there are three relationships as follows:

| Relationship | Domain meaning | Appropriate representation |
|---|---|---|
| PurchaseOrder → PurchaseOrderLine | Root **owns** the order lines; lines live and die with the order | Child collection (**@MappedCollection**), FK to root |
| PurchaseOrder → ShippingAddress | Root **contains a value** | Value object, optionally column-embedded with **@Embedded** |
| PurchaseOrder → Customer | Two **independent** aggregates; the order needs to know which customer placed it | Store **customerId**; access Customer through its own repository when needed |

Some common design mistakes:

1. **One table = one aggregate = one repository.** This ignores that an aggregate can span multiple tables and child entities should not be accessed independently.
2. **Any foreign key means the same aggregate.** A foreign key only expresses a data relationship; it does not say who owns the lifecycle or business rules.
3. **Putting a Customer object directly inside PurchaseOrder for convenient joins.** In Spring Data JDBC, a mapped object relationship can be interpreted as an ownership relationship. Storing the Customer ID and querying separately keeps boundaries clearer.
4. **Updating order lines directly in the DB and assuming the root remains valid.** This easily bypasses rules for adding lines, locking an order, or quantity limits; prefer using business APIs on the root.
5. **Assuming save(root) only UPDATEs a single changed row.** Spring Data JDBC targets aggregate-level operations; child collections may trigger multiple DELETE/INSERT statements. Understand the write cost and keep aggregates sufficiently small.
6. **Assuming a value object must have an ID.** A shipping address used by value typically needs no separate ID, even though its data appears in a table.

## 10. Going from Business Requirements to the Data Model

When implementing a new feature, you can ask yourself in sequence:

1. **Identity:** which objects must be recognized as "still the same thing" even when attributes change? Those are entity candidates.
2. **Value:** which information is identified by its content and should be replaced as a whole? Those are value object candidates.
3. **Invariants:** which rules must be protected when changing multiple objects together? Group the objects that need shared ownership into an aggregate.
4. **Root:** which entity is responsible for providing operations that preserve invariants? Only access and modify the aggregate through the root.
5. **Independent boundaries:** which objects have their own lifecycle? Reference other aggregates by ID rather than automatically embedding the whole object graph.
6. **Persistence and access:** choose tables/columns/FKs/constraints; map with Spring Data JDBC; create a repository for the root and add appropriate queries.

This sequence avoids working backward from a table diagram to force-fit a business model.

## 11. Self-Check with a Scenario

An e-commerce system has a **Shopping Cart**, **Cart Item Lines**, **Shipping Address**, and **Catalog Products**. Questions:

1. Must a cart item line be an aggregate root?
2. Why can the shipping address be a value object even though it is stored in a table?
3. Should the cart hold the entire Product aggregate directly, or only **productId** along with necessary details?
4. Is a shopping cart stored across two tables two separate aggregates?

**Comparison hints:** (1) No; if a line only exists inside the cart and must obey the cart's rules, it is a component owned by the root. (2) Because domain identity is based on content, while physical storage location does not dictate object kind. (3) Keeping **productId** generally clarifies the relationship between two independent aggregates; snapshot details such as name/price at the time of adding to the cart are a separate business decision. (4) No; the number of tables does not determine the number of aggregates.

What matters most to grasp is the chain of relationships: **Entities / Value Objects** make up an **Aggregate**; the **Aggregate Root** protects invariants and is accessed via a **Repository**; **Spring Data JDBC** maps aggregate state down to **relational tables and columns**. Decisions about domain boundaries should stem from identity, ownership, and business rules.
