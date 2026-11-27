# Referencing by ID Instead of Embedding an Entire Aggregate

In **Spring Data Relational JDBC**, an aggregate is the consistency boundary that the application loads, modifies, and saves as a single unit. When an aggregate needs to relate to another aggregate, the standard design is to hold the **ID of the referenced aggregate** instead of embedding its entire object graph inside the current root.

For example, an order belongs to a customer. The order needs to know which customer placed it, but the customer has its own lifecycle: name, email, addresses, account status, and other orders. If the entire `Customer` object is embedded in `PurchaseOrder`, ownership boundaries become blurred, and a small change to an order could pull in loading/saving customer data. Referencing by ID allows both aggregates to maintain independent ownership and lifecycles.

Spring Data JDBC provides the `AggregateReference<T, ID>` type to represent a reference to another aggregate root. An application can also store a simple ID such as `Long customerId`. Both approaches express the relationship by identity; `AggregateReference` makes it clearer in the Java type which kind of aggregate that ID points to.

## 1. Why Define Aggregate Boundaries?

An aggregate is a group of entities/value objects that need to be protected by a consistency boundary. The aggregate root is the external entry point for changing state inside the group.

Suppose a sales system has:

~~~text
Customer aggregate
  Customer (root)
    id
    name
    email
    accountStatus
    addresses

PurchaseOrder aggregate
  PurchaseOrder (root)
    id
    customerId  --------------------+
    status                          |
    lines                           |
                                    |
                                    v
                              Customer root
~~~

`Customer` and `PurchaseOrder` are two independent aggregate roots:

- A customer can exist before placing an order and continue to exist after the order is completed.
- One customer can have many orders.
- Changing customer profile information does not require re-saving all orders.
- Updating the status of one order does not need to modify the customer's object graph.
- Each aggregate can be read and saved through its own repository.

**Aggregate boundaries are not determined solely by foreign key relationships or one-to-many relationships in the database.** They are determined by which business rules must be protected within the same unit of change.

### 1.1. Consistency Rules Inside an Aggregate

For example, in `PurchaseOrder`:

- Do not confirm an order without order lines.
- The total amount must match the order lines.
- A confirmed order cannot have lines added according to domain rules.

These rules directly involve the order's state, so the root is responsible for enforcing them.

Conversely, a rule such as "an order cannot be placed if the customer account is locked" involves the state of the `Customer` aggregate. The application needs to check customer status at the time the business operation runs, but that does not turn the entire customer into an owned part of the order.

### 1.2. Object Relationships Do Not Equal Ownership

A Java property of type `Customer` inside `PurchaseOrder` easily gives the impression that the order owns or manages the customer. In Spring Data JDBC, object relationships are interpreted according to the aggregate mapping model; putting another root directly into the graph can cause the framework to treat it as a component belonging to the aggregate being saved.

For an independent aggregate, hold an ID or `AggregateReference` to represent the association. If you want to modify the customer, call the customer's repository and perform behavior through the customer root.

## 2. How Do Embedding Object Graphs and Referencing by ID Differ?

Let's compare the two modeling approaches:

**Embedding the entire object:**

~~~java
class PurchaseOrder {
    private Customer customer;
}
~~~

**Holding a reference by ID:**

~~~java
class PurchaseOrder {
    private Long customerId;
}
~~~

Or using the dedicated type:

~~~java
class PurchaseOrder {
    private AggregateReference<Customer, Long> customer;
}
~~~

| Criterion | Embedding another aggregate object | Referencing by ID |
| --- | --- | --- |
| Ownership | Easily blurs the boundary between two aggregates | Each aggregate keeps its own repository and lifecycle |
| Data loading | Risks pulling in a large graph or unintended relationship mapping | Reads only the current root; loads the referenced root when business logic needs it |
| Data saving | May trigger save operations on a graph that does not belong to the root | Saving the current root does not imply saving the referenced root |
| Concurrency | A large graph increases the scope of data prone to conflict | Each aggregate can have its own version control |
| Performance | Easily loads more data than necessary | Can choose when and how to load related data |
| Domain API | Object relationships may encourage modifying another root directly | Clearly expresses that this is a reference, requiring operations through the appropriate repository |

This does not mean every nested object must be converted into an ID. **Value objects and child entities belonging to the same aggregate should still be represented inside the aggregate root** if they require the same consistency and have a lifecycle dependent on the root.

For example:

~~~text
PurchaseOrder aggregate
  PurchaseOrder
    shippingAddress: ShippingAddress (value object)
    lines: List<OrderLine>           (child objects)
    customer: AggregateReference     (another aggregate)
~~~

A shipping address captured at the time of placing the order can be a value object belonging to the order. Order lines are components of the order. The customer is an independent aggregate referenced by ID.

## 3. Referencing by a Simple ID

The most direct solution is to store the ID of the other aggregate as a scalar property:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    private String status;
}
~~~

Advantages:

- Simple, easy to understand, and less coupled to Spring Data JDBC-specific APIs.
- Does not pull the customer object graph into the order aggregate.
- Can clearly pass the ID across services, events, or APIs.
- Easy to write SQL, indexes, and foreign keys.

The downside is that the `Long` type does not convey the type of the referenced aggregate. If the code has multiple ID types with the same underlying type, a developer might accidentally pass `supplierId` where `customerId` is expected. This risk can be reduced with a dedicated ID value object or by using `AggregateReference`.

Service example:

~~~java
PurchaseOrder order = orderRepository.findById(orderId)
        .orElseThrow();

Customer customer = customerRepository.findById(order.getCustomerId())
        .orElseThrow(() -> new IllegalStateException(
                "Order references a non-existent customer"
        ));
~~~

The application explicitly decides when to load the customer. The order repository does not automatically load the customer via a lazy proxy.

## 4. `AggregateReference<T, ID>` in Spring Data JDBC

Spring Data JDBC provides `AggregateReference` to represent a reference to another aggregate root. The generic type consists of:

- `T`: the type of the referenced aggregate root.
- `ID`: the identifier type of that aggregate.

For example:

~~~java
AggregateReference<Customer, Long>
~~~

This means "a reference to a `Customer` aggregate, identified by a `Long`".

Import:

~~~java
import org.springframework.data.jdbc.core.mapping.AggregateReference;
~~~

Create a reference from an ID:

~~~java
AggregateReference<Customer, Long> customerReference =
        AggregateReference.to(customerId);
~~~

Get the ID from the reference:

~~~java
Long referencedCustomerId = customerReference.getId();
~~~

`AggregateReference` does not contain the full customer data. It only holds the ID and Java-level type information. When Spring Data JDBC maps the entity, the reference's ID value is stored in the corresponding column.

### 4.1. Why Is a Typed Reference Beneficial?

Compared to `Long customerId`, the `AggregateReference<Customer, Long>` type expresses intent more clearly:

~~~java
AggregateReference<Customer, Long> customer;
AggregateReference<Supplier, Long> supplier;
~~~

Both properties hold a `Long` ID, but they refer to different aggregate types. The compiler can catch some cases of passing the wrong reference type when generic types do not match.

`AggregateReference` is not a proxy object representing a loaded `Customer`. It has no `getName()` or `getEmail()` methods. To obtain customer details, the application must use the ID to query the corresponding aggregate.

### 4.2. Declaration in the Aggregate Root

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.jdbc.core.mapping.AggregateReference;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private AggregateReference<Customer, Long> customer;

    private String status;

    public PurchaseOrder(
            Long id,
            AggregateReference<Customer, Long> customer,
            String status
    ) {
        this.id = id;
        this.customer = customer;
        this.status = status;
    }

    public Long getId() {
        return id;
    }

    public AggregateReference<Customer, Long> getCustomer() {
        return customer;
    }

    public String getStatus() {
        return status;
    }
}
~~~

`@Column("customer_id")` specifies the column name that stores the reference ID. Actual table/column names must match the schema and the application's naming strategy.

### 4.3. Creating an Order with a Reference

~~~java
Long customerId = 25L;

AggregateReference<Customer, Long> customerReference =
        AggregateReference.to(customerId);

PurchaseOrder order = new PurchaseOrder(
        null,
        customerReference,
        "DRAFT"
);

PurchaseOrder saved = orderRepository.save(order);
~~~

In this example, the application creates an order with a known customer ID. Creating `AggregateReference` does not query the database to verify that the customer exists, nor does it save the customer. If it is necessary to confirm that the customer exists or is allowed to place an order, the service must perform a separate business check.

### 4.4. Reading the ID and Loading the Referenced Aggregate

~~~java
PurchaseOrder order = orderRepository.findById(orderId)
        .orElseThrow();

Long customerId = order.getCustomer().getId();

Customer customer = customerRepository.findById(customerId)
        .orElseThrow(() -> new IllegalStateException(
                "Referenced customer not found"
        ));
~~~

Reading the order returns a reference containing the ID. Calling `customerRepository.findById` is what reads the customer aggregate. Loading data is explicit and can be placed in a service, query handler, or dedicated projection.

## 5. Relational Schema: ID Column and Foreign Key

Referencing by ID in Java should be backed by an appropriate relational schema. For example:

~~~sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL UNIQUE
);

CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(24) NOT NULL,
    CONSTRAINT fk_purchase_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer(id)
);

CREATE INDEX idx_purchase_order_customer
    ON purchase_order(customer_id);
~~~

Here:

- `customer_id` is the column storing the referenced ID.
- The foreign key ensures an order does not point to a non-existent customer ID at the time the database checks the constraint.
- The index supports querying orders by customer and appropriate join operations.
- `NOT NULL` indicates that every order must have a customer; if the domain allows an order without an assigned customer, both schema and model must reflect that.

**`AggregateReference` does not automatically create a foreign key constraint.** It describes the reference value in object mapping. Constraints and indexes must be declared in the database schema/migrations.

### 5.1. Is a Foreign Key Needed When Using AggregateReference?

Normally, if the relationship must always point to a valid customer in the same database, a foreign key is a useful layer of data protection. It prevents errors caused by:

- A piece of code saving the wrong ID.
- Data written manually via SQL.
- A batch import bypassing the service.
- Another process creating an invalid reference.

However, some architectures intentionally omit physical foreign keys—for example, when referenced data belongs to a different database/service or requires separate deletion/splitting workflows. In such cases, the application must have a policy for detecting and handling orphan references. Omitting an FK should be a deliberate architectural decision.

### 5.2. Deleting a Referenced Aggregate

If `customer` is being referenced by `purchase_order`, the database may reject deleting the customer due to the foreign key. This is usually the right behavior for historical order data.

Do not choose `ON DELETE CASCADE` casually. If deleting a customer also removes historical orders, the system may violate audit or business retention requirements. Common options include:

- Preventing customer deletion while referenced orders remain.
- Soft-deleting/deactivating the customer while keeping the ID.
- Storing a snapshot of required information inside the order to preserve history.
- Using a dedicated archive/anonymize workflow when data protection rules apply.

The deletion policy must be defined at the business and schema levels; `AggregateReference` does not determine cascading behavior.

## 6. Not Embedding Other Aggregates Does Not Mean No Nested Objects

A common mistake is interpreting the rule "reference other aggregates by ID" as "every nested property must be turned into an ID". That strips the model of components that genuinely belong to the aggregate.

Distinguish by lifecycle and consistency:

| Component | Relationship to root | Common modeling approach |
| --- | --- | --- |
| `ShippingAddress` captured at order placement | Value object belonging to the order | Embed values in the aggregate, e.g., `@Embedded` |
| `OrderLine` existing only within the order lifecycle | Child entity/value belonging to the aggregate | Collection mapped with `@MappedCollection` or corresponding mapping |
| `Customer` with its own lifecycle | Independent aggregate root | Scalar ID or `AggregateReference<Customer, Long>` |
| `Product` with its own stock, price, and status | Independent aggregate root | ID reference; store a snapshot of locked-in name/price if the order needs history |
| `Payment` with an independent processing workflow | May be a separate aggregate depending on the domain | ID reference and a separate coordination workflow |

Example structure:

~~~text
PurchaseOrder aggregate
  PurchaseOrder
    customer: AggregateReference<Customer, Long>
    shippingAddress: ShippingAddress
    lines: List<OrderLine>

Customer aggregate
  Customer
    name
    email
    accountStatus

Product aggregate
  Product
    sku
    currentPrice
    inventoryPolicy
~~~

The order holds the IDs of the customer and products to identify the related aggregates. However, the order can hold `ShippingAddress` and `OrderLine` internally because they belong to the order's state.

### 6.1. Business Snapshots vs. Embedding an Aggregate

When a customer places an order, the order needs to keep the product name, price at the time of purchase, and chosen shipping address. If it only keeps `productId` and fetches the current name/price from `Product` every time history is viewed, historical records can change whenever the catalog updates.

Therefore, you can store:

~~~text
OrderLine
  productId
  productNameAtPurchase
  unitPriceAtPurchase
  quantity
~~~

`productId` is the reference to the `Product` aggregate. `productNameAtPurchase` and `unitPriceAtPurchase` are snapshots belonging to the order. A snapshot is not the entire `Product` aggregate; it is the data required to preserve transaction meaning.

## 7. ID References Do Not Auto-Load Data and Have No Lazy Loading

With Spring Data JDBC, `AggregateReference` does not behave like a JPA lazy proxy. When reading `PurchaseOrder`:

~~~text
SELECT ... FROM purchase_order WHERE id = ?
                    |
                    v
PurchaseOrder(customer = AggregateReference.to(25))
~~~

The framework does not automatically execute an extra query to load the full `Customer` just because the reference property exists.

This has several consequences:

- There is no `order.getCustomer().getName()` call.
- There are no lazy-loading exceptions as in JPA's proxy model.
- No automatic N+1 queries caused by accessing getters on a proxy.
- If a screen needs the customer name, the application must query that data intentionally.

### 7.1. Loading Data When Needed

A simple service:

~~~java
@Service
public class OrderDetailService {

    private final PurchaseOrderRepository orderRepository;
    private final CustomerRepository customerRepository;

    public OrderDetailService(
            PurchaseOrderRepository orderRepository,
            CustomerRepository customerRepository
    ) {
        this.orderRepository = orderRepository;
        this.customerRepository = customerRepository;
    }

    @Transactional(readOnly = true)
    public OrderDetail loadDetail(Long orderId) {
        PurchaseOrder order = orderRepository.findById(orderId)
                .orElseThrow();

        Customer customer = customerRepository.findById(
                order.getCustomer().getId()
        ).orElseThrow();

        return new OrderDetail(order, customer);
    }
}
~~~

`OrderDetail` here is an application-defined DTO/projection. The example assumes the corresponding repositories and constructor exist. A read-only transaction can keep read operations within the same transaction boundary according to the transaction manager configuration.

### 7.2. Avoiding N+1 When Loading Multiple Aggregates

If you load 100 orders and then call `customerRepository.findById` for each order, the application can issue 101 queries:

~~~text
1 query: load 100 orders
100 queries: load the customer for each order
-------------------------------
101 queries
~~~

ID references avoid automatic graph loading, but they do not automatically solve the need to display related data. When handling lists, consider:

- Collecting the set of unique customer IDs from the list of orders.
- Using a query by ID set (`IN`) to batch-load customers.
- Creating a dedicated projection/query that joins tables for the read view.
- Using a separate read model if read requirements are more complex than the write aggregate model.

SQL projection example:

~~~sql
SELECT
    po.id AS order_id,
    po.status,
    c.id AS customer_id,
    c.name AS customer_name
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
WHERE po.id = ?;
~~~

This join query serves reading display data. It does not mean `Customer` becomes part of the aggregate saved together with `PurchaseOrder`.

## 8. Reference Validation and Business Rules

`AggregateReference.to(customerId)` only creates a reference. It does not prove that the customer exists, is active, or is allowed to place an order.

Order creation service example:

~~~java
@Transactional
public PurchaseOrder placeOrder(Long customerId, List<OrderLine> lines) {
    Customer customer = customerRepository.findById(customerId)
            .orElseThrow(() -> new IllegalArgumentException(
                    "Customer does not exist"
            ));

    if (!customer.isActive()) {
        throw new IllegalStateException("Customer account is inactive");
    }

    PurchaseOrder order = PurchaseOrder.create(
            AggregateReference.to(customer.getId()),
            lines
    );

    return orderRepository.save(order);
}
~~~

This illustrative example assumes `Customer.isActive()` and factory `PurchaseOrder.create(...)` exist in the model. Customer verification rules are executed in the application service before creating the order.

### 8.1. Pre-Checks Do Not Replace Foreign Keys

Between reading the customer and saving the order, another process could delete the customer. If the database has a foreign key, inserting the order will be rejected if the customer no longer exists. Without a foreign key, the system needs another mechanism to guarantee valid references.

Here is the distinction between:

- **Business validation:** the customer exists and is allowed to place an order at the time of checking.
- **Referential constraint:** the customer row exists at the time the database executes insert/update.
- **State synchronization:** the account could be locked right after the check; how to handle this race condition depends on how strict the business requirement is.

If the business requires that an order cannot be placed when the account is locked concurrently, proper concurrency/transaction/locking design is needed. A single check in Java is not guaranteed to enforce the rule under all races.

### 8.2. Referencing an Aggregate in Another Service

If the customer resides in a different service/database, a standard cross-database physical foreign key cannot be created. In that case:

- Store a stable identifier ID issued by the owning service.
- Call an API or use events to check/synchronize state according to the contract.
- Handle cases where the other service is unavailable.
- Define how to handle IDs that no longer exist or data that has been deleted.
- Consider storing a snapshot of data needed for transaction history.

In this situation, `AggregateReference` can help express the referenced ID in the Java model if the ID type fits, but it does not provide network communication or distributed transactions. A cross-service reference is an integration contract, not an automatic object relationship.

## 9. Modifying and Deleting a Referenced Aggregate

Suppose a customer changes their email or name after placing an order. Because the order only holds the ID:

- The order still points to the same customer ID.
- If reading current info from the `Customer` repository, the application sees the new data.
- If the order needs to keep the info from placement time, the snapshot in the order retains the old values.

This is a key decision: **an ID reference answers which aggregate is related; a snapshot answers which data must be preserved at the business moment.**

### 9.1. Do Not Cascade Updates Across the Whole Aggregate

When saving `PurchaseOrder`, do not expect the framework to automatically save the referenced `Customer`. To update a customer, call the customer's repository/behavior separately. This prevents an order update from accidentally overwriting customer information modified elsewhere.

### 9.2. Deleting a Reference

If a customer is deleted, there are several possibilities:

| Policy | Meaning |
| --- | --- |
| Restrict/RESTRICT | Disallow deleting a customer while orders still reference them |
| Soft delete | Mark the customer inactive while retaining the row and ID |
| SET NULL | Allow an order to exist without a customer link; only sensible if the column is nullable and the domain allows it |
| Archive/anonymize | Retain required business records while changing or masking personal data according to policy |

`ON DELETE CASCADE` is usually unsuitable for orders that need historical retention, as it can delete transaction data along with the customer. Choose a policy based on retention, legal, and business requirements.

## 10. ID References and Transactions

Two independent aggregates are usually saved via separate repositories. If a use case needs to modify both, the application service can coordinate them within a shared database transaction when they use the same datasource/transaction manager and the database supports that scope.

For example:

~~~java
@Transactional
public PurchaseOrder reserveOrder(Long customerId, List<OrderLine> lines) {
    Customer customer = customerRepository.findById(customerId)
            .orElseThrow();

    customer.ensureCanPlaceOrder();

    Customer updatedCustomer = customer.recordOrderAttempt();
    customerRepository.save(updatedCustomer);

    PurchaseOrder order = PurchaseOrder.create(
            AggregateReference.to(customerId),
            lines
    );
    return orderRepository.save(order);
}
~~~

This is an example of business coordination; updating the customer in the same transaction should only be done when consistency rules truly require it and both repositories use the same transaction manager. If the two aggregates are stored in different databases or services, local `@Transactional` does not automatically create a distributed transaction.

### 10.1. Keeping Aggregates Small to Reduce Contention

If every order operation had to load and save the customer, unrelated changes could contend on the same aggregate or hold the same transaction longer. Referencing by ID reduces the scope of data loaded and modified:

~~~text
Order status change operation
  -> load PurchaseOrder
  -> check order invariants
  -> save PurchaseOrder

No need to load/save Customer if the business operation does not need Customer state.
~~~

This also reduces connection hold time and the number of SQL statements issued per use case.

### 10.2. When Asynchronous Coordination Is Needed

If a business process spans multiple aggregates or services without needing a single ACID transaction, you can use:

- Domain events to notify that a change has occurred.
- Outbox pattern to write events in the same transaction as the aggregate that raises them.
- Saga/process manager to coordinate multi-step workflows and compensation.
- Eventual consistency with explicit intermediate states.

For example, ordering and payment: an order can be created in `PENDING_PAYMENT` status; the payment service processes separately; the resulting event updates the order status. Do not embed the entire `Payment` aggregate inside `Order` just hoping one save will coordinate everything.

## 11. ID Value Object or AggregateReference?

Besides `Long`, an application can define a dedicated ID type:

~~~java
public record CustomerId(Long value) {
    public CustomerId {
        if (value == null || value <= 0) {
            throw new IllegalArgumentException("Invalid CustomerId");
        }
    }
}
~~~

This type helps prevent mixing up IDs of the same primitive type. However, mapping an ID wrapper to a JDBC column requires an appropriate converter/mapping. Do not assume every ID record is automatically converted to a scalar by Spring Data JDBC just because it has a single component.

Comparison:

| Reference style | Strengths | Considerations |
| --- | --- | --- |
| `Long customerId` | Simple, easy SQL binding, minimal framework coupling | Does not express aggregate type in the type system |
| `CustomerId` | Type-safe in the domain, can hold validation | Needs mapping/converter if persistence does not map it as desired |
| `AggregateReference<Customer, Long>` | Explicitly shows a reference to the Customer aggregate | Depends on Spring Data JDBC API and still only holds an ID |
| `Customer customer` | Easy to access object properties if data is already loaded | Risks blurring ownership and graph mapping between aggregates |

Choose the representation based on the level of type-safety needed, the framework API of your project version, and domain model clarity.

## 12. Querying Related Data for Read Views

Aggregate boundaries fit the write model, but a screen may need data from multiple aggregates. You do not need to break write boundaries to satisfy queries.

### 12.1. Query Handler Using Multiple Repositories

For a single order:

1. Read `PurchaseOrder`.
2. Get the customer ID from `AggregateReference`.
3. Read `Customer`.
4. Build the display DTO.

This approach is simple when data volume is small and the use case loads only a few aggregates.

### 12.2. SQL Projection for Lists

For large lists, a join can be more efficient than calling repositories in a loop:

~~~sql
SELECT
    po.id AS order_id,
    po.status AS order_status,
    po.customer_id,
    c.name AS customer_name
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
WHERE po.status = ?
ORDER BY po.id DESC
LIMIT ? OFFSET ?;
~~~

Results should be mapped into a DTO/projection dedicated to the screen. This read query can join tables without turning the roots into a single write aggregate.

### 12.3. When the Read Model Grows Complex

If multiple screens need to combine data from many aggregates, consider an appropriate read model or materialized view. Read data can be updated synchronously or asynchronously depending on consistency requirements. The key is not letting display needs bloat the write aggregate.

## 13. Common Mistakes

| Mistake | Consequence | Redesign approach |
| --- | --- | --- |
| Directly embedding the Customer root inside PurchaseOrder | Blurs ownership and may pull unintended graphs into mapping | Hold customer ID or AggregateReference |
| Thinking AggregateReference auto-loads Customer | Code expects lazy loading but only receives an ID | Use the ID to call the repository or a query projection |
| Thinking saving Order cascades save to Customer | Customer changes may not be saved as expected | Save aggregates separately via their own repositories |
| Treating AggregateReference as a foreign key constraint | Database can still contain orphan IDs without a constraint | Create FKs/indexes in the schema where appropriate |
| Using @MappedCollection for another aggregate root | The other root is treated as a child of the current aggregate | Use ID references across aggregate boundaries |
| Converting every nested object into an ID | Loses value objects/children that share the same invariants | Keep components belonging to the same aggregate inside the root |
| Keeping only productId and reading current price for old orders | Transaction history can change with catalog updates | Store a snapshot of name/price at purchase time |
| Calling repository in a loop for large lists | N+1 queries, increasing round-trips and latency | Batch lookup or query projection |
| Not handling deleted customers | Orphan references or lost history | Choose an appropriate FK/delete policy/soft delete |
| Thinking @Transactional spans multiple services/databases | A local transaction does not automatically become distributed | Use outbox/saga or an explicitly designed distributed mechanism |

## 14. Practical Scenarios

### Scenario A — Orders and Customers

A customer has thousands of orders. When staff change the status of one order, the system only needs to update that order.

**Design:** `PurchaseOrder` stores `AggregateReference<Customer, Long>` or `customerId`. Changing order status loads and saves only the order root; the customer is loaded only when the use case needs customer details or needs to check customer status.

### Scenario B — Orders and Shipping Addresses

A customer can change their default address after buying. Old orders must retain the exact address used when placed.

**Design:** the order stores a `ShippingAddress` snapshot as a value object belonging to the aggregate. If the current profile address is needed, reference the customer and query separately. Do not use a dynamic reference in place of a historical snapshot.

### Scenario C — Products and Order Lines

A product is an independent aggregate, while order lines belong to the order. An order line must preserve the finalized quantity, name, and price.

**Design:** `OrderLine` lives inside the `PurchaseOrder` aggregate; it holds `productId` to reference the product and stores snapshots of data needed for history. Catalog changes do not automatically alter placed orders.

### Scenario D — Customer in Another Service

Orders and customers reside in two services with two independent databases.

**Design:** store the customer ID according to the identity contract between services. There is no cross-database physical FK; you need processes for verification, synchronization, and handling invalid IDs. If customer details at order time must be preserved, store a snapshot in the order.

## 15. Process for Designing an Aggregate Reference

When an aggregate needs to relate to another aggregate, follow this sequence:

1. **Determine ownership.** Does the referenced component have its own lifecycle, or is it a child/value object belonging to the current root?
2. **Identify data to retain.** Is only the ID needed, or is a business snapshot at the time of occurrence required?
3. **Choose the reference type.** Use a scalar ID, ID value object, or `AggregateReference<T, ID>` based on type-safety and mapping needs.
4. **Design the schema.** Create the reference column, foreign key, and index where appropriate; decide nullability and delete policy.
5. **Design the use cases.** Load the referenced aggregate only when needed; validate business rules at the appropriate time.
6. **Avoid N+1.** For lists, use batch lookups or query projections.
7. **Define consistency.** Decide between a shared transaction, events/outbox/saga, or eventual consistency.
8. **Test the lifecycle.** Verify insert/load/update/delete, non-existent references, root deletion, and concurrent handling.

## Key Takeaways

An aggregate root should manage the state it owns. When relating to an independent aggregate, hold an **ID or `AggregateReference`** to express the relationship. Spring Data JDBC persists the referenced ID value, but does not automatically load the entire aggregate, does not cascade saves to other aggregates, and does not automatically create foreign keys in the database.

Keep value objects and child entities inside the aggregate when they share the same consistency boundary. Use snapshots for historical data that must remain unchanged, query projections for screens combining multiple roots, and appropriate transactions or event mechanisms when a use case must coordinate multiple aggregates. This design keeps write-model ownership clear, avoids unnecessary object graphs, and provides better control over database access costs.
