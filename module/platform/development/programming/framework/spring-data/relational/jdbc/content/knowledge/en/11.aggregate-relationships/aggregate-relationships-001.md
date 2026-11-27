# Mapping Owned One-to-One Relationships in an Aggregate

In **Spring Data Relational JDBC**, an aggregate root is the entry point for reading and writing a group of objects that share the same business lifecycle. Inside an aggregate, the root can own a child entity in a **one-to-one** relationship: for example, an order has a set of shipping details, a customer profile has an identity section, or a device has its own configuration.

It is important to distinguish three ways of storing data:

- **Child entity with its own table:** the root holds a property referencing a single child entity; the child table contains a foreign key pointing back to the root. This is an owned one-to-one relationship within an aggregate.
- **Embedded value object:** the property is part of the root's value, and its columns live directly in the root table.
- **Reference to another aggregate:** the root only stores the identifier of another aggregate, typically using `AggregateReference`. The other aggregate has an independent lifecycle and ownership.

Spring Data JDBC supports one-to-one child entity references within an aggregate. When the reference is considered part of the aggregate, the root manages the child entity's lifecycle. This lesson uses PostgreSQL and Spring Data JDBC to cover mapping, schema, repository operations, and the necessary constraints.

## 1. Aggregate root and owned one-to-one relationship

Suppose a sales system has the following model:

```text
PurchaseOrder (aggregate root)
       │
       │ owns 0..1
       ▼
ShippingDetails (child entity)

PurchaseOrder
  ├── id
  ├── orderNumber
  └── shippingDetails
        ├── recipientName
        ├── street
        └── phone
```

`PurchaseOrder` is the aggregate root because business operations on orders start from it. `ShippingDetails` is a child entity because it belongs to a specific order, is not shared across multiple orders, and has no independent lifecycle.

The "owned" relationship is expressed through these rules:

1. Each `ShippingDetails` belongs to at most one `PurchaseOrder`.
2. An order may have no shipping details yet or have one set of shipping details.
3. No separate repository is created to manage `ShippingDetails` as an independent aggregate root.
4. Adding, changing, or removing shipping details is performed through operations on `PurchaseOrder`.
5. When the child reference is removed from the aggregate, the old child entity is considered no longer part of the aggregate and is deleted according to Spring Data JDBC persistence rules.

In this example, the domain-side cardinality is **0..1**: an order might not have a shipping address assigned yet. If business rules require every order to have an address, enforce that invariant when creating/updating the order.

## 2. Mapping a child entity in a separate table

Spring Data JDBC recognizes an entity-typed property referencing another entity as a one-to-one relationship or an embedded type according to the mapping model. When you want the child entity stored in a **separate table**, declare the property on the aggregate root and optionally use `@MappedCollection` to specify the foreign key column name in the child table.

Example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(idColumn = "purchase_order_id")
    private ShippingDetails shippingDetails;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderNumber, ShippingDetails shippingDetails) {
        this.orderNumber = orderNumber;
        this.shippingDetails = shippingDetails;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public ShippingDetails getShippingDetails() {
        return shippingDetails;
    }

    public void changeShippingDetails(ShippingDetails details) {
        this.shippingDetails = details;
    }
}

@Table("shipping_details")
public class ShippingDetails {

    private String recipientName;
    private String street;
    private String phone;

    protected ShippingDetails() {
    }

    public ShippingDetails(String recipientName, String street, String phone) {
        this.recipientName = recipientName;
        this.street = street;
        this.phone = phone;
    }

    public String getRecipientName() {
        return recipientName;
    }

    public String getStreet() {
        return street;
    }

    public String getPhone() {
        return phone;
    }
}
```

Here:

- `@Table("purchase_order")` specifies the table for the aggregate root.
- `@Id` marks the root's primary key.
- `shippingDetails` is a single property, not a collection.
- `@MappedCollection(idColumn = "purchase_order_id")` sets the back-reference column name in the child entity table.
- `ShippingDetails` does not need its own `@Id` in this example. For a one-to-one relationship, the child entity may or may not have an ID property; if it does not, the root's foreign key is typically used as the unique identifier in the schema.

Spring Data JDBC does not use JPA's `@OneToOne` annotation here. Do not add `@OneToOne`, `@JoinColumn`, or `cascade = ...` from JPA to a Spring Data JDBC entity expecting them to control this mapping.

## 3. Database schema and one-to-one constraint

A corresponding PostgreSQL schema:

```sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE shipping_details (
    purchase_order_id BIGINT PRIMARY KEY
        REFERENCES purchase_order(id),
    recipient_name VARCHAR(120) NOT NULL,
    street VARCHAR(255) NOT NULL,
    phone VARCHAR(30)
);
```

In the `shipping_details` table, `purchase_order_id` is both the primary key and the foreign key:

- The foreign key ensures the child entity cannot reference a nonexistent order.
- The primary key ensures each order appears at most once in the child table.
- An order without shipping details is represented by the absence of a corresponding row in `shipping_details`.

This represents a **0..1 relationship from root to child**. A plain foreign key alone does not guarantee that every order has a child row. If the business requires **strictly 1..1**, enforce that invariant in the domain/service and the order-creation transaction; or consider storing the shipping fields as embedded in the same table if they are truly a mandatory part of the root row.

If you want the child entity to have its own ID, you can design it as:

```sql
CREATE TABLE shipping_details (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL UNIQUE
        REFERENCES purchase_order(id),
    recipient_name VARCHAR(120) NOT NULL,
    street VARCHAR(255) NOT NULL,
    phone VARCHAR(30)
);
```

In that case, the `ShippingDetails` class also declares `@Id private Long id;`. The `UNIQUE(purchase_order_id)` constraint is still required so the database guarantees that one order cannot have multiple child rows. Having a separate ID is useful if you need a technical identifier for the child row, but it does not automatically make it an independent aggregate root.

### 3.1. Why must there be a UNIQUE or PRIMARY KEY on the foreign key?

If you only define:

```sql
purchase_order_id BIGINT REFERENCES purchase_order(id)
```

then multiple `shipping_details` rows can point to the same `purchase_order`. The database would then allow one order to have multiple sets of shipping details—a one-to-many relationship at the data layer.

To enforce a one-to-one relationship, a uniqueness constraint is needed on the child table side:

```sql
ALTER TABLE shipping_details
    ADD CONSTRAINT uq_shipping_details_order
    UNIQUE (purchase_order_id);
```

Domain rules in Java help the code express intent; database constraints protect the data even when SQL scripts, batch jobs, or other services write directly to the DB.

## 4. Customizing the foreign key name with @MappedCollection

If no column name is specified, Spring Data JDBC uses `NamingStrategy` to determine the back-reference based on the referenced table/entity type name. With an existing schema or when you want a clearer name, specify `idColumn` explicitly:

```java
@Table("purchase_order")
class PurchaseOrder {
    @Id
    private Long id;

    @MappedCollection(idColumn = "purchase_order_id")
    private ShippingDetails shippingDetails;
}
```

`idColumn` is the column name in the **child table** used to reference the aggregate root's ID. It is neither the Java property name on the root nor the primary key column of the root table.

For a single child property, `keyColumn` is not needed. `keyColumn` is for structures like `List` or `Map`, where the database needs an extra column to store element positions or map keys.

If you rename the table with `@Table` or change the naming strategy, verify the actual back-reference column name. Do not infer the foreign key name solely from the class name; the mapping context, annotations, and naming strategy can all affect the result.

## 5. Saving the aggregate through a repository

The repository is created for the **aggregate root**:

```java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

Creating an order along with shipping details:

```java
ShippingDetails details = new ShippingDetails(
        "Nguyen An",
        "12 Nguyen Trai, District 1",
        "0900000000"
);

PurchaseOrder order = new PurchaseOrder("PO-2026-001", details);
PurchaseOrder saved = purchaseOrderRepository.save(order);
```

When saving the root, Spring Data JDBC processes the entities belonging to the aggregate according to the mapping. The root and child entity are written within the same aggregate persistence operation; the root's ID is used to populate the back-reference in the child table. You do not need to manually fetch the root ID and run a separate insert statement for the child.

Reading it back:

```java
Optional<PurchaseOrder> result =
        purchaseOrderRepository.findById(saved.getId());

result.ifPresent(found -> {
    ShippingDetails shipping = found.getShippingDetails();
    if (shipping != null) {
        System.out.println(shipping.getRecipientName());
    }
});
```

Spring Data JDBC loads the aggregate according to its mapping; there is no need to declare a separate repository for `ShippingDetails` just to read the child part. Depending on the dialect and mapping, loading parts of the aggregate may require multiple SQL statements; do not assume the relationship is always loaded with a single JOIN statement.

### 5.1. Changing the child details

Changing the address through the aggregate root:

```java
PurchaseOrder order = purchaseOrderRepository.findById(orderId)
        .orElseThrow();

order.changeShippingDetails(new ShippingDetails(
        "Tran B",
        "45 Le Loi, District 1",
        "0911111111"
));

purchaseOrderRepository.save(order);
```

The root remains the object being saved. Spring Data JDBC manages the child entity as part of the aggregate when persisting the root. Therefore, you should not keep an independent service/repository to update `ShippingDetails` while bypassing the aggregate root.

### 5.2. Removing the child details

If an order is allowed to remove its shipping address:

```java
PurchaseOrder order = purchaseOrderRepository.findById(orderId)
        .orElseThrow();

order.changeShippingDetails(null);
purchaseOrderRepository.save(order);
```

When an owned child reference is removed from the aggregate, Spring Data JDBC treats the old child entity as no longer belonging to the aggregate and deletes the corresponding row according to its aggregate-saving mechanism. This is an important difference from an ID referencing another aggregate: removing an owned reference can delete the child entity; removing an external reference does not mean deleting the referenced aggregate.

If the application has another table or external system referencing the `shipping_details` row directly, revisit the aggregate boundaries. A child entity deleted with the root's lifecycle should not be treated as a shared resource.

## 6. Should the child entity have its own ID or use the foreign key as its identifier?

Spring Data JDBC allows a one-to-one referenced entity to have no `@Id` property of its own. The choice depends on domain semantics and schema:

| Design | Characteristics | When appropriate |
| --- | --- | --- |
| No separate ID; FK is PK | Child only exists with root; at most one child per root | Value-like child that has its own row but needs no independent identifier |
| Separate ID and UNIQUE FK | Child has a technical key, still belongs to one root | Need an internal ID for integration, audit, or technical key |
| `@Embedded` | No child table; fields become columns in the root table | Small value object that does not need a separate row |
| `AggregateReference` | Stores the ID of an independent aggregate | Referenced object has its own lifecycle and ownership |

Do not add a separate ID just because every other table has an ID. If the child is solely a component of the root, using the FK as the PK can express the ownership relationship more clearly. Conversely, if an ID is needed for an integration flow or a separate foreign key, a separate ID is a valid choice; still keep UNIQUE on the FK if the relationship is one-to-one.

## 7. Distinguishing a one-to-one child entity from @Embedded

An object nested inside an entity does not always need a separate table. If it is a **value object** and the data can live directly on the same row, use `@Embedded`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @Embedded.Nullable(prefix = "shipping_")
    private ShippingAddress shippingAddress;
}

public record ShippingAddress(
        String recipientName,
        String street,
        String phone
) {}
```

With the `shipping_` prefix, the value object's properties map to columns in the same table, for example:

```sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    shipping_recipient_name VARCHAR(120),
    shipping_street VARCHAR(255),
    shipping_phone VARCHAR(30)
);
```

`@Embedded` does not create a foreign key or rows in another table. Depending on `onEmpty`, if all embedded columns are `NULL`, the property can be materialized as `null` or an empty object. `@Embedded.Nullable` is shorthand for treating the object as null when all of its columns are empty.

Comparison:

| Criterion | One-to-one child entity in a separate table | `@Embedded` value object |
| --- | --- | --- |
| Number of tables | Root and child have separate tables | Root table only |
| Foreign key | Back-reference from child to root | None |
| Child ID | Optional | No separate ID needed |
| Lifecycle | Belongs to the aggregate root | Part of the root's value |
| Best suited for | Child with distinct structure/storage or many attributes | Pure value group that does not need its own row |

Do not use `@Embedded` if you want a child table with a foreign key. Conversely, do not create a child table just to represent a small group of values with no separate lifecycle when embedded mapping serves better.

## 8. Distinguishing owned one-to-one from AggregateReference

Suppose an order belongs to a customer. A customer can place many orders and exists independently of any individual order. `Customer` is therefore a different aggregate root, not a child entity owned inside `PurchaseOrder`.

Reference model:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.jdbc.core.mapping.AggregateReference;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {
    @Id
    private Long id;

    private AggregateReference<Customer, Long> customer;
}
```

`AggregateReference` stores the identifier of another aggregate and represents the boundary between two aggregates. Spring Data JDBC does not load the entire `Customer` as a child entity belonging to the order just because this reference exists, and deleting an order does not mean deleting the customer.

| Aspect | Owned one-to-one child | AggregateReference |
| --- | --- | --- |
| Boundary | Same aggregate | Different aggregate |
| Stored in domain object | Actual child object | ID wrapped by `AggregateReference` |
| Database tables | Child table has FK back to root | Root stores reference ID; other aggregate has its own table/lifecycle |
| Lifecycle | Root manages child | Each aggregate is saved/deleted independently |
| Removing reference | Old child entity is removed from aggregate and deleted on persistence | Does not delete the target aggregate |
| Example | Order and that order's dedicated shipping address | Order and customer |

If multiple orders reference the same customer, do not embed the `Customer` object into each order as an owned child. Use an ID/`AggregateReference` so you do not create an incorrect ownership relationship.

## 9. Transactions and consistency

Creating a root and child is usually a single business operation. If the root is inserted but the child insert fails, the system should not leave a half-saved aggregate if the domain requires them to be created together.

With Spring, you can place the operation in a service and use `@Transactional`:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final PurchaseOrderRepository repository;

    public OrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder createOrder(
            String orderNumber,
            ShippingDetails shippingDetails) {
        PurchaseOrder order =
                new PurchaseOrder(orderNumber, shippingDetails);
        return repository.save(order);
    }
}
```

The transaction manager matching the `DataSource` will manage commit/rollback. When other business operations need to participate in the same transaction, keep them within the same transaction boundary. Do not open another JDBC connection manually with `DriverManager` inside the service and expect it to automatically join Spring's transaction.

Database constraints remain important even with transactions:

- FK prevents the child from pointing to a nonexistent root.
- PK/UNIQUE on the back-reference prevents multiple children for the same root.
- NOT NULL on required columns protects child data.
- Validation/domain invariants prevent creating a root without a child when business rules require one.

A transaction ensures that statements within the transaction commit or rollback together; it does not automatically create cardinality constraints if the schema does not declare them.

## 10. Common errors and how to identify their causes

| Symptom | Possible cause | How to resolve |
| --- | --- | --- |
| `Table shipping_details does not exist` | Child table not created yet or table name does not match mapping | Check migrations and `@Table` |
| `Column purchase_order_id does not exist` | Back-reference column missing or `idColumn` is wrong | Cross-check `@MappedCollection` and DDL |
| One order has multiple child rows | FK has no UNIQUE/PRIMARY KEY | Add a unique constraint and clean up duplicate data before migration |
| Saving root produces no child | Child property is null, incorrect mapping, or schema/SQL error | Inspect object before save, mapping metadata, and SQL |
| Child deleted but row still remains | Operating outside the aggregate, wrong mapping, or root save not called | Check aggregate boundaries and repository operations |
| Deleting root triggers FK violation | Dependent rows still exist or delete order/schema constraint is unsuitable | Identify dependent rows and deletion workflow |
| Wanting a repository for child | Treating child entity as an independent aggregate root | Operate through root; if child has an independent lifecycle, revisit aggregate boundary |
| `@OneToOne` used but does not work | Brought JPA annotations into Spring Data JDBC | Use Spring Data JDBC relational mapping |
| H2 tests pass but PostgreSQL fails | Differences in dialect, DDL, or constraints | Run integration tests on PostgreSQL with migrations |

When debugging, inspect all three layers: Java mapping, database schema, and the actual SQL/exception. Do not just look at a class having a child property and assume the table and foreign key were created.

## 11. Workflow for designing an owned one-to-one relationship

When adding a one-to-one child to an aggregate:

1. **Determine ownership:** does the child belong to the root's lifecycle, or is it shared or accessed independently?
2. **Choose storage:** separate table with a child entity property, or the same table via `@Embedded`?
3. **Declare Java mapping:** root has a single property; use `@MappedCollection(idColumn = "...")` if a specific back-reference name is needed; child has the corresponding `@Table`.
4. **Design schema:** create an FK from child to root and PK/UNIQUE on the FK to enforce one-to-one cardinality.
5. **Define optional/mandatory rules:** if 0..1, the property can be null; if 1..1, check the invariant in the domain/service.
6. **Persist through root:** create, update, and remove the child through the aggregate root repository.
7. **Test on target database:** verify insert, read, update, remove, constraints, and transactions with the actual dialect.

## 12. Practice exercises

**Exercise 1 — An order with a shipping address.** Create the two tables `purchase_order` and `shipping_details`. Use `@MappedCollection(idColumn = "purchase_order_id")` for the root's single property. Save the root with the child, read it back, and verify the data in both tables.

**Exercise 2 — One-to-one constraint.** Try removing UNIQUE/PRIMARY KEY from `shipping_details.purchase_order_id` and insert two rows pointing to the same order. Observe that the database allows a one-to-many relationship. Add the constraint back and try again.

**Exercise 3 — Optional child.** Save an order without `shippingDetails`, then attach a child and save again. Next, set the property to `null`, save the root, and confirm the child row is removed from the aggregate.

**Exercise 4 — Embedded or separate table?** Convert `ShippingDetails` to `@Embedded.Nullable(prefix = "shipping_")`. Compare the DDL, SQL, and data representation with the separate-table approach.

**Exercise 5 — Aggregate boundaries.** Add a `Customer` referenced by multiple orders. Use `AggregateReference<Customer, Long>` in `PurchaseOrder` and confirm that deleting an order does not delete the customer.

### References

- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): entity references, one-to-one, back references, `@MappedCollection`, and `@Embedded`.
