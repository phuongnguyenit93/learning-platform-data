# Reading Flow of the Aggregate Root and Owned Entities

In **Spring Data Relational JDBC**, the aggregate root is the entry point of an aggregate. When an application reads a root using a repository, Spring Data JDBC restores the state of the root along with the objects owned inside the aggregate boundary. Understanding this reading flow helps design the relationships between the root, child entities, and value objects properly, while also predicting what data is loaded, which SQL statements may be generated, and the cost of a single read.

A key aspect of Spring Data JDBC is that its model **does not rely on a persistence context or JPA-style lazy-loading proxies**. When an aggregate is read, the components belonging to the aggregate are loaded according to Spring Data JDBC's mapping mechanism. A reference to an independent aggregate only carries the ID; the framework does not automatically load the entire referenced aggregate.

This lesson focuses on the reading flow of the aggregate root and owned entities: from the repository to SQL, how collections and embedded objects are mapped, ownership rules, empty data cases, query costs, and how to choose an appropriate read query.

## 1. The aggregate root is the starting point of the reading flow

An aggregate consists of a root and the components owned by the root. The root controls the changes needed to maintain the aggregate's invariants.

Order example:

~~~text
PurchaseOrder aggregate
  PurchaseOrder (ROOT)
    id
    orderNumber
    status
    shippingAddress: ShippingAddress
    lines: List<OrderLine>
      OrderLine
        productCode
        quantity
        unitPrice
~~~

In this model:

- `PurchaseOrder` is the aggregate root.
- `ShippingAddress` is a value object belonging to the order.
- `OrderLine` is a child component owned by the order.
- Order lines and the shipping address do not have a lifecycle independent of the order in this example.

When calling:

~~~java
PurchaseOrder order = orderRepository.findById(orderId)
        .orElseThrow();
~~~

The application requests to read the aggregate through the root. The result is a `PurchaseOrder` object together with the components belonging to the aggregate mapped according to the declared metadata. The calling code does not need to look up each order line manually using a separate repository.

### 1.1. A root is not just a single row of data

In the database, the root is typically stored in a main table, while child collections reside in separate tables. However, an aggregate is a domain concept, not a single table.

~~~text
Database

purchase_order
  id | order_number | status | shipping_city

order_line
  purchase_order_id | line_position | product_code | quantity
  1001              | 0             | BOOK-A       | 2
  1001              | 1             | PEN-B        | 4

                 |
                 | Spring Data JDBC mapping
                 v

PurchaseOrder(id=1001)
  shippingAddress = ...
  lines = [OrderLine(...), OrderLine(...)]
~~~

A single aggregate read may require multiple SQL statements to reconstruct the object graph. What matters is that all of the data is returned as a single aggregate with the root as its entry point.

### 1.2. Why access through the root?

If external code loads and modifies individual `OrderLine` instances on its own, it may bypass order rules such as:

- Do not add lines when the order has already been confirmed.
- The total amount must be recalculated when quantities change.
- Do not remove the last line if the order is required to have at least one line.

Reading and modifying through the root helps the model keep responsibilities consistent. An aggregate's repository is typically declared for the root:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

The application uses the repository to retrieve the aggregate, then invokes behavior on the root.

## 2. General reading flow in Spring Data JDBC

At a conceptual level, reading an aggregate proceeds as follows:

~~~text
Application service
       |
       v
PurchaseOrderRepository.findById(id)
       |
       v
Spring Data JDBC repository infrastructure
       |
       v
DataAccessStrategy / JDBC mapping
       |
       +---- SELECT root row from purchase_order
       |
       +---- SELECT owned collection rows from order_line
       |
       +---- map embedded values from root row
       |
       v
Materialize PurchaseOrder aggregate
       |
       v
Return complete mapped aggregate to caller
~~~

The main steps:

1. The repository receives the root's ID.
2. Spring Data JDBC generates and executes the SQL statement to read the root row by ID.
3. Properties stored in the same row, such as scalars and embedded value objects, are mapped from that row.
4. For collections or child entities stored in separate tables, the framework performs the necessary read operations to retrieve the components belonging to the root.
5. The framework constructs the child objects and attaches them to the root according to the mapping metadata.
6. The repository returns the aggregate to the caller.

The exact number and shape of SQL statements depend on the aggregate structure, mapping style, dialect, and framework version. You should not assume that a single `findById` call always emits only one SQL statement.

## 3. Mapping the root and child entities with `@MappedCollection`

A collection of child entities is usually stored in a separate table. The child table's foreign key points to the aggregate root's ID.

Schema example:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL
);

CREATE TABLE order_line (
    purchase_order_id BIGINT NOT NULL,
    line_position INTEGER NOT NULL,
    product_code VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_minor_units BIGINT NOT NULL,
    PRIMARY KEY (purchase_order_id, line_position),
    FOREIGN KEY (purchase_order_id)
        REFERENCES purchase_order(id)
);
~~~

Child entity:

~~~java
public class OrderLine {
    private String productCode;
    private int quantity;
    private long unitPriceMinorUnits;

    public OrderLine(
            String productCode,
            int quantity,
            long unitPriceMinorUnits
    ) {
        if (productCode == null || productCode.isBlank()) {
            throw new IllegalArgumentException("Invalid product code");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (unitPriceMinorUnits < 0) {
            throw new IllegalArgumentException("Unit price cannot be negative");
        }
        this.productCode = productCode;
        this.quantity = quantity;
        this.unitPriceMinorUnits = unitPriceMinorUnits;
    }

    public String getProductCode() {
        return productCode;
    }

    public int getQuantity() {
        return quantity;
    }

    public long getUnitPriceMinorUnits() {
        return unitPriceMinorUnits;
    }
}
~~~

Aggregate root:

~~~java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    private String status;

    @MappedCollection(
            idColumn = "purchase_order_id",
            keyColumn = "line_position"
    )
    private List<OrderLine> lines;

    public PurchaseOrder(
            Long id,
            String orderNumber,
            String status,
            List<OrderLine> lines
    ) {
        this.id = id;
        this.orderNumber = orderNumber;
        this.status = status;
        this.lines = lines == null ? List.of() : List.copyOf(lines);
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public String getStatus() {
        return status;
    }

    public List<OrderLine> getLines() {
        return lines;
    }
}
~~~

`@MappedCollection` describes a collection belonging to the aggregate root:

- `idColumn` specifies the column in the child table that stores the root's ID.
- `keyColumn` can store the element's position when the collection needs to preserve order, such as a `List`.
- Spring Data JDBC uses this information to read the child rows associated with the root and build the collection.

Column names must match the schema. For a `Set` collection or an unordered structure, the choice of key column and child table key rules must be designed appropriately.

The example above illustrates mapping and constructor usage; a real application must ensure constructor binding and the naming strategy match the schema. Business rules such as order status and total calculation can be added to the root.

### 3.1. Foreign keys define ownership at the storage level

`order_line.purchase_order_id` links an order line to the root. This column is not the ID of an independent aggregate; it indicates which order the line belongs to.

When reading a `PurchaseOrder` with ID 1001, the framework needs to retrieve the `order_line` rows with `purchase_order_id = 1001`. Lines from other orders are not included in the current aggregate.

### 3.2. List and element ordering

If business logic requires order line ordering, use `List` and declare `keyColumn` to store the position. Without a position column, the database does not automatically guarantee query result order.

Do not rely on the physical order of rows in a table. SQL only guarantees order when an appropriate `ORDER BY` is present; the collection mapping metadata must support restoring the desired order.

## 4. Embedded objects are read from the same row

A value object does not necessarily have its own table. For example, a shipping address captured at the time the order is placed:

~~~java
public record ShippingAddress(
        String recipient,
        String street,
        String city,
        String postalCode
) {
}
~~~

The schema can include the columns:

~~~sql
ALTER TABLE purchase_order
    ADD COLUMN shipping_recipient VARCHAR(160),
    ADD COLUMN shipping_street VARCHAR(200),
    ADD COLUMN shipping_city VARCHAR(100),
    ADD COLUMN shipping_postal_code VARCHAR(20);
~~~

Mapping in the root:

~~~java
@Embedded(prefix = "shipping_")
private ShippingAddress shippingAddress;
~~~

With `@Embedded`, the components of the value object are read from the same root row. The framework does not need to query a separate address table just to construct `ShippingAddress`.

Distinction:

| Component | Common storage location | How it is read |
| --- | --- | --- |
| Root scalar property | Column in the root table | Read from the root row |
| `@Embedded` value object | Multiple columns in the root table | Constructed from the root row |
| `@MappedCollection` collection | Child table | Related rows read using the root key |
| Another aggregate referenced by ID | Reference ID column | Only the ID is read; getting its data requires a separate query |

Do not use `@Embedded` to represent an aggregate with an independent lifecycle. Having multiple fields does not make an object a separate aggregate; identity and business rules must be considered.

## 5. Child entities are loaded with the root, not via lazy proxies

Spring Data JDBC does not use a persistence context or lazy-loading proxies like Hibernate/JPA. Mapped components that are part of the aggregate are loaded as part of the aggregate reading flow.

Example:

~~~java
PurchaseOrder order = repository.findById(1001L)
        .orElseThrow();

List<OrderLine> lines = order.getLines();
~~~

The caller can access the mapped collection directly. There is no collection proxy waiting until `getLines()` is called to query the database.

This has several consequences:

- There is no JPA-style `LAZY` fetch type configuration for aggregate collections.
- There is no need to keep a session open solely to access child proxies later.
- The cost of reading an aggregate must be considered right at the moment the repository loads the root.
- An overly large aggregate can make a single root read expensive.
- Calling a getter does not automatically trigger additional queries.

### 5.1. Do not confuse with references to other aggregates

Suppose a root has:

~~~java
AggregateReference<Customer, Long> customer;
List<OrderLine> lines;
~~~

When reading the order:

- `lines` is a collection owned by the order; the framework loads it as part of the aggregate.
- `customer` is only an ID reference to the Customer aggregate; the framework does not automatically load the full Customer.

The difference:

~~~text
findById(PurchaseOrder)
        |
        +-- root row --------------------> loaded
        |
        +-- embedded ShippingAddress ---> mapped from root row
        |
        +-- owned OrderLine collection --> loaded as aggregate part
        |
        +-- AggregateReference<Customer> -> ID only
                                           |
                                           +-- explicit customerRepository.findById(...)
                                               needed to load Customer
~~~

This is the core rule for distinguishing ownership from reference. If Customer were embedded directly as an object graph, the model could inadvertently treat it as part of the order aggregate.

## 6. Concrete reading flow from the repository

Suppose:

~~~java
PurchaseOrder order = orderRepository.findById(1001L)
        .orElseThrow(() -> new OrderNotFoundException(1001L));
~~~

In terms of data, the framework needs to:

**Step 1 — Read the root**

~~~sql
SELECT id, order_number, status,
       shipping_recipient, shipping_street,
       shipping_city, shipping_postal_code
FROM purchase_order
WHERE id = ?;
~~~

**Step 2 — Read child collections**

~~~sql
SELECT purchase_order_id, line_position,
       product_code, quantity, unit_price_minor_units
FROM order_line
WHERE purchase_order_id = ?
ORDER BY line_position;
~~~

The SQL above illustrates the idea. The actual statements depend on the dialect, naming strategy, and how Spring Data JDBC implements mapping in the release being used. The framework may use different queries to load collection paths; do not hard-assume the exact SQL count solely from this example.

**Step 3 — Materialize objects**

~~~text
Root row
  -> PurchaseOrder
  -> ShippingAddress (embedded)

Child rows
  -> OrderLine objects
  -> List<OrderLine>

Combine
  -> PurchaseOrder aggregate
~~~

**Step 4 — Return to caller**

When the repository returns the result, the aggregate's components have been restored according to the mapping. If the root ID does not exist, `findById` returns `Optional.empty()`; there is no aggregate to construct.

### 6.1. Reading via query methods

A query method can look up a root by property:

~~~java
Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
~~~

The result is still an aggregate root. Spring Data JDBC must map the root and the components belonging to the aggregate according to the repository's mapping. Do not infer that querying by a non-ID property returns only a flat row unrelated to the aggregate.

If a method can match multiple roots:

~~~java
List<PurchaseOrder> findByStatus(String status);
~~~

The collection return type represents multiple aggregates. The cost of loading aggregates depends on the number of roots and the structure of owned collections. For large list screens, consider projections/read queries instead of loading every full aggregate if the UI only needs a few fields.

## 7. Missing root vs. empty collection

Two cases must be distinguished:

**Root does not exist**

~~~java
Optional<PurchaseOrder> result = repository.findById(9999L);
~~~

If there is no row in `purchase_order`, the result is `Optional.empty()`.

**Root exists but has no children**

~~~java
PurchaseOrder order = repository.findById(1001L)
        .orElseThrow();

order.getLines().isEmpty(); // true if the order has no lines yet
~~~

The root still exists; the collection is restored as an empty collection according to the model's mapping/initialization. Do not confuse having no children with the root not existing.

| Scenario | Meaning | Typical outcome |
| --- | --- | --- |
| No root row | Aggregate does not exist | Empty Optional |
| Root exists, no child rows | Aggregate exists with empty collection | Root with empty collection |
| Root exists, some child rows | Aggregate has corresponding components | Collection containing loaded children |
| Database error while reading children | Cannot complete loading aggregate | Data access exception |

Do not turn child-reading errors into an empty collection. If the child query fails due to connection loss or a SQL error, the application must know that the aggregate failed to load.

## 8. Loading multiple aggregate roots

A method such as:

~~~java
Iterable<PurchaseOrder> orders = orderRepository.findAll();
~~~

returns aggregate roots. When mapping the roots, the components belonging to each aggregate also need to be restored according to Spring Data JDBC's mechanism.

This differs from reading only the root table with custom SQL. When loading multiple aggregates, consider the total number of roots, the number of children, collection sizes, and the number of mapping paths.

Example:

~~~text
findAll()
  |
  +-- PurchaseOrder #1001
  |      +-- 2 OrderLine
  |
  +-- PurchaseOrder #1002
  |      +-- 5 OrderLine
  |
  +-- PurchaseOrder #1003
         +-- 0 OrderLine
~~~

If there are thousands of orders, materializing all roots along with their child collections can consume significant memory and time. `findAll()` is not the right choice for every screen or batch job.

### 8.1. Paginating aggregates

When you need a paginated list of roots, you can use appropriate repository paging/query support or write a dedicated query to limit roots before loading data. Verify how pagination interacts with aggregate mapping in the Spring Data JDBC version in use.

Do not arbitrarily paginate child rows if business rules require the root to always be restored in full. An aggregate with truncated children may no longer represent a valid domain state.

### 8.2. Batch processing

For jobs that need to process many roots:

- Choose a batch size that fits comfortably in memory.
- Use stable pagination conditions, typically based on an increasing key or cursor key.
- Avoid loading the entire table and then filtering in Java.
- Measure aggregate size and the number of SQL statements generated.
- Consider query projections if the job only needs a subset of data.

If a job must modify aggregates, load the root through the repository and save through the repository to preserve proper mapping and invariants.

## 9. Aggregate reading cost and performance

An aggregate root may own multiple collections. Each collection path may require an additional query. Therefore, read cost depends not only on the number of roots, but also on the aggregate structure.

Example:

~~~text
PurchaseOrder
  lines
  adjustments
  notes
  shipmentPackages
~~~

A single root read may need to load multiple child sets. When the root has nested collections, the number of read operations and the amount of data can grow with the mapping depth/structure.

### 9.1. Overly large aggregates

Signs an aggregate may be too large:

- One root contains thousands of children.
- Most use cases only need a small part of a collection.
- Every root read pulls in data unnecessary for the operation.
- A small change makes reading/saving the whole graph expensive.
- Parts of the data have independent lifecycles or change frequencies.

The solution is not to add JPA-style lazy loading to Spring Data JDBC. Revisit the aggregate boundaries:

- Which components truly must stay consistent together with the root?
- Which components can become separate aggregates?
- Can snapshots or reference IDs be stored instead?
- Can read screens use dedicated projections?

### 9.2. Do not split an aggregate just to save one SQL query

Aggregate boundaries must stem from invariants and lifecycles. Splitting children into independent roots just because a collection is large can force business rules into transactions spanning multiple roots, making consistency harder to maintain.

If child data must always change together with the root and be protected within a single transaction, keeping it inside the aggregate may be the right choice even if reading requires more queries. In that case, optimizing SQL/indexes and reducing data size per read is the appropriate direction.

### 9.3. Indexing collection foreign keys

Example child query by root:

~~~sql
SELECT *
FROM order_line
WHERE purchase_order_id = ?;
~~~

An index on the foreign key column can help the database locate child rows faster:

~~~sql
CREATE INDEX idx_order_line_purchase_order
    ON order_line(purchase_order_id);
~~~

If the child table's primary key starts with `(purchase_order_id, line_position)`, the primary key index may already support prefix lookups on `purchase_order_id`, depending on the database. Check the execution plan before adding duplicate indexes.

### 9.4. Measuring cost accurately

Observe:

- Number of SQL statements per root load.
- Query duration for root and child tables.
- Number of rows read.
- Size of the created object graph.
- Mapping time and JVM allocations.
- Connection pool wait time.
- Number of aggregates loaded per request.

SQL logging is helpful during development, but can produce large log volumes and expose sensitive data; enable it only in appropriate environments and control sensitive parameters.

## 10. Aggregate loading vs. projection reading

Aggregate repositories serve the write model and behaviors that require the full aggregate state. However, a screen might only need:

- Order number.
- Status.
- Customer name.
- Total amount.

If only those four fields are needed, loading the entire `PurchaseOrder` and every `OrderLine` can be wasteful.

A projection/read model query can be used:

~~~sql
SELECT
    po.id AS order_id,
    po.order_number,
    po.status,
    c.name AS customer_name
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
WHERE po.status = ?
ORDER BY po.id DESC;
~~~

The result can be mapped into a DTO:

~~~java
public record OrderListItem(
        Long orderId,
        String orderNumber,
        String status,
        String customerName
) {
}
~~~

A projection is a read result tailored for a specific need; it is not a full aggregate and should not be used to invoke domain behavior and then saved as a root.

### 10.1. Do not confuse projections with aggregate mapping

A custom SQL query returning a few columns does not necessarily restore child collections. If a method returns a DTO/projection, the caller should rely only on the fields provided by the query.

If a custom query returns an aggregate root, verify the query method's mapping behavior in the release being used and test the aggregate's collections. Do not assume a hand-written SQL query automatically loads all children like the standard repository read path.

### 10.2. Pragmatic CQRS

You can maintain:

- Aggregate repositories for state-changing commands and use cases requiring invariants.
- Separate projections/queries for list screens, reports, or searches.

There is no need to build a complex distributed CQRS system just because a screen needs a join. A clear read query can be enough.

## 11. Referenced aggregates are not loaded with the root

Suppose:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private AggregateReference<Customer, Long> customer;

    @MappedCollection(idColumn = "purchase_order_id")
    private List<OrderLine> lines;
}
~~~

When reading:

- `lines` belongs to the aggregate, so it is loaded.
- `customer` only holds a reference ID, so it is not automatically loaded into a `Customer`.

To display the customer name:

~~~java
PurchaseOrder order = orderRepository.findById(orderId)
        .orElseThrow();

Customer customer = customerRepository.findById(
        order.getCustomer().getId()
).orElseThrow();
~~~

For lists of many orders, avoid calling the customer repository in a loop if you can issue a batch query by ID set or a join projection.

This is an important boundary:

| Relationship | Loaded when reading root? | Reason |
| --- | --- | --- |
| Scalar property | Yes | Column belongs to the root table |
| `@Embedded` value object | Yes | Component of the same row |
| `@MappedCollection` child | Yes | Component belonging to the aggregate |
| `AggregateReference` | Reference ID only | Target aggregate has its own lifecycle |
| An independent root embedded directly into the graph | Should not be designed this way | Blurs ownership boundaries |

## 12. Transactions in the aggregate reading flow

Loading an aggregate typically consists of reading the root and reading its child components. If the application needs a consistent snapshot during concurrent updates, database transactions and isolation levels play a role.

Example:

~~~java
@Transactional(readOnly = true)
public PurchaseOrder getOrder(Long id) {
    return orderRepository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
}
~~~

A read-only transaction expresses read-only intent and can provide hints to the transaction manager/database. How a consistent snapshot is guaranteed depends on the isolation level and database; do not assume every read-only transaction automatically uses snapshot isolation.

### 12.1. Why an aggregate with multiple queries needs isolation attention

Suppose the reading flow is:

1. Read the order root.
2. Read the lines collection.

If another transaction modifies order lines between the two steps, a weak isolation level can allow the read to observe data from different points in time. Depending on the database/isolation level, the application may read a consistent state or encounter non-repeatable reads/phantoms consistent with the chosen isolation.

For use cases requiring a strict consistent snapshot, choose the appropriate isolation level and test on the target database. Do not infer from a repository returning a single object that all SQL statements necessarily run under the same snapshot if transaction boundaries are not established.

### 12.2. Do not hold transactions open longer than necessary

Once the aggregate has been read and converted into a DTO/response, avoid holding the transaction open while:

- Waiting for user input.
- Calling a slow external API.
- Generating large files.
- Sending emails or long-running synchronous messages.

Long-running transactions can hold connections and snapshots/locks longer than necessary, impacting the pool and database.

## 13. Constructors and aggregate materialization

Spring Data JDBC must construct objects from the data read. For mutable classes, the framework can instantiate the object and assign properties via its mapping mechanism. For immutable classes or Java records, the framework uses an appropriate constructor.

Root record example:

~~~java
@Table("purchase_order")
public record PurchaseOrder(
        @Id Long id,
        String orderNumber,
        String status,
        @MappedCollection(idColumn = "purchase_order_id")
        List<OrderLine> lines
) {
    public PurchaseOrder {
        lines = lines == null ? List.of() : List.copyOf(lines);
    }
}
~~~

Records provide a canonical constructor matching their components, which is convenient for restoring immutable objects. However, the collection type and child mapping must be compatible with the Spring Data JDBC version; the constructor must accept the exact mapped properties.

Do not add required constructor parameters for unpersisted data (for example, a transient UI note) and expect the framework to populate it automatically. Unmapped data should be computed/assigned in a later step or placed into a DTO.

### 13.1. Empty and immutable collections

When the constructor converts a null collection to `List.of()` and copies it via `List.copyOf`, domain code can work with a non-null collection without allowing callers to mutate it directly.

This is a Java model decision; the schema can still have no child rows. An empty collection does not mean the root does not exist.

### 13.2. Child entities and constructors

Child classes also need constructor/property mappings matching the child table columns. For immutable children, the constructor must accept the persistent data. `keyColumn` or foreign key values used for mapping can be handled by the framework via metadata; do not add them to the domain model unless needed for business logic.

When using a class with multiple constructors, you may need to mark the persistence constructor with `@PersistenceCreator`. Ensure constructor parameter names have the required metadata, such as compiling with `-parameters` when needed.

## 14. When should you load the full aggregate?

Reading the full aggregate is appropriate when the use case:

- Needs to execute domain behavior that depends on multiple components inside the root.
- Needs to verify invariants before updating.
- Needs to compute results across the entire child collection.
- Needs to modify part of the aggregate and save the root while respecting ownership rules.
- Needs a complete snapshot for a critical business operation.

For example, confirming an order requires checking that it has lines, its total amount, and its status. Reading the root along with its lines makes sense.

It is not always necessary to load the full aggregate when the use case only:

- Displays a status label.
- Counts orders by status.
- Searches by order number.
- Produces a list of IDs.
- Generates a report needing only a few columns.

In these cases, query projections or aggregate functions may be a better fit.

## 15. Common mistakes

| Mistake | Consequence | How to address |
| --- | --- | --- |
| Thinking `findById` always reads exactly one row | Overlooking the cost of reading child collections | Observe SQL and aggregate structure |
| Expecting child collections to lazy-load on getter call | Does not match the Spring Data JDBC model | Size aggregates appropriately and use projections for reads |
| Embedding another aggregate root directly into the current root | Blurs ownership and may cause unintended mapping | Use ID/`AggregateReference` |
| Using `@MappedCollection` for an independent aggregate | Turns a reference relationship into an ownership one | Use only for children owned by the aggregate |
| Thinking `@Embedded` creates a separate table | Wrong schema expectations and query count estimates | Understand embedded means columns in the same row |
| Treating a root row with an empty collection as non-existent | Incorrect business handling | Distinguish Optional root from empty child collection |
| Using `findAll` for thousands of large aggregates | Excessive memory and query overhead | Paginate/batch or use projections |
| Relying on physical order of child rows | Unstable ordering | Use `keyColumn`/order mapping and an appropriate `ORDER BY` |
| Testing only root fields | Missing collection mapping bugs | Integration test with child rows |
| Missing index on child foreign keys | Child queries by root can be slow | Inspect execution plans and indexes |
| Using a custom projection and expecting full children | DTO does not contain the full aggregate | Rely only on fields returned by the query; load aggregate separately if needed |
| Thinking a read-only transaction is always a snapshot | Actual isolation depends on database/config | Choose an appropriate isolation level and test it |

## 16. Practical scenarios

### Scenario A — Reading an order to confirm it

An order has a status, shipping address, and multiple order lines. The use case needs to validate all lines before confirming.

**Design:** read `PurchaseOrder` via the root repository. The `OrderLine` instances belonging to the aggregate are loaded according to the mapping. Call `confirm()` on the root, then save the aggregate. Do not load Customer unless the confirmation rules require customer status.

### Scenario B — Displaying an order list

The screen only needs the order number, status, and customer name; it does not need order lines.

**Design:** use a SQL projection joining the order and customer tables. Do not load the full aggregate with all child collections for a list screen.

### Scenario C — An order without lines yet

The repository finds the root, but the `order_line` table has no matching rows.

**Outcome:** the aggregate exists with an empty collection. The confirmation use case can reject it according to the invariant "an order must have at least one line".

### Scenario D — An order with thousands of lines

A single `findById` pulls in a huge collection, slowing down requests and consuming heap memory.

**How to address:** review aggregate boundaries and business needs. If the lines must remain consistent with the root, optimize queries/indexes and consider pagination in the read model. If they have an independent lifecycle, consider splitting the aggregate with an explicit consistency workflow.

### Scenario E — Customer is referenced

Order contains `AggregateReference<Customer, Long>` and a list of OrderLine items.

**Outcome:** OrderLine items are loaded with the aggregate; Customer only has its ID. When the customer name is needed, the service performs a separate lookup or uses a join projection.

## 17. Process for designing and verifying the reading flow

When adding a property or collection to an aggregate:

1. **Determine ownership:** is it a scalar, embedded value, child collection, or aggregate reference?
2. **Design the schema:** do root columns, foreign key columns, key columns, constraints, and indexes match the mapping?
3. **Choose the mapping:** use `@Embedded` for value objects in the same row; `@MappedCollection` for children owned by the aggregate; ID/`AggregateReference` for independent roots.
4. **Assess size:** how could the maximum number of children and number of collections affect load times?
5. **Choose the read API:** load the full aggregate when invariants are needed; use projections for partial read screens.
6. **Define transactions:** if a consistent snapshot across multiple SQL statements is required, choose suitable transaction/isolation settings.
7. **Inspect SQL:** observe root and child queries, indexes, and actual row counts.
8. **Integration tests:** root with children, root without children, missing root, invalid child mapping, aggregate referencing another root, and loading multiple roots.

## Key takeaways

In Spring Data JDBC, **reading an aggregate starts from the aggregate root**. The framework maps scalar properties and embedded value objects from the root row, while loading entities/collections owned by the root according to the mapping. These components do not wait for JPA-style lazy loading; therefore, aggregate size and query cost must be accounted for at design time.

Another aggregate root referenced by ID or `AggregateReference` is not loaded automatically. When its data is needed, the application explicitly calls its repository or uses a query projection. Maintaining this boundary keeps the reading flow predictable, prevents aggregates from bloating, and lets display queries be optimized independently.
