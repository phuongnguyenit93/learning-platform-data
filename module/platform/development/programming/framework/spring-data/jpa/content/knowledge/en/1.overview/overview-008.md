# Learning Sequence and Running Business Model Across the Documentation

Spring Data JPA helps Spring applications work with relational data through repositories. To use it properly, three conceptual layers must be understood: **JPA** defines how entities are mapped and managed; **Hibernate** is typically the default JPA provider configured by Spring Boot; **Spring Data JPA** adds repositories, query derivation, and integration with the Spring ecosystem. Repositories do not replace SQL, database design, or transaction boundaries.

This documentation uses one running order-management business model throughout. Each new lesson adds a capability to that same model, allowing learners to see how each feature affects data, relationships, queries, and real business logic.

## 1. Learning Outcomes

After completing the Spring Data JPA track, learners should be able to:

- Translate a relational data model into entities with clear mappings and proper constraints.
- Explain the entity lifecycle, persistence context, dirty checking, flush, and commit.
- Use repositories to save, find, update, and delete data; choose appropriately between derived queries, JPQL, native SQL, and dynamic queries.
- Map bidirectional relationships without breaking foreign keys, cascades, or object state.
- Design transactions at the business layer, handle errors, and understand the effects of propagation, isolation, and read-only settings.
- Detect N+1 queries, avoid loading redundant data, paginate correctly, and choose suitable projections.
- Protect data under concurrent transactions using optimistic or pessimistic locking.
- Write persistence tests close enough to the real database management system.

## 2. Prerequisite Knowledge

Before going deeper, you should know the following:

- **Java:** classes, objects, constructors, access modifiers, interfaces, generics, collections, exceptions, enums, **BigDecimal**, **LocalDate**, and **Instant**.
- **Relational databases:** tables, rows, primary keys, foreign keys, unique constraints, **NOT NULL**, indexes, joins, aggregates, transactions, and isolation levels.
- **SQL:** **SELECT**, **INSERT**, **UPDATE**, **DELETE**, **JOIN**, **GROUP BY**, **ORDER BY**, **LIMIT**, or the equivalent pagination syntax of your database.
- **Spring:** dependency injection, beans, configuration, service layer, and how Spring manages transactions.
- **Spring Boot:** datasource configuration, drivers, schema migrations, and environment configuration.

You do not need to memorize all of SQL or the JPA specification before starting. However, when a repository query generates unexpected SQL, you must be able to read the SQL and compare it against the table model.

## 3. Recommended Study Order

| Order | Topic | Why study at this step | What you should be able to do |
|---|---|---|---|
| 1 | Architecture of JPA, Hibernate, and Spring Data JPA | Distinguish the JPA contract, provider, and repository abstraction before using APIs | Explain the path from service to repository, persistence context, and database |
| 2 | Entities, primary keys, and entity lifecycle | Every persistence operation relies on entities and their states | Distinguish transient, managed, detached, and removed; understand persist, merge, remove, flush |
| 3 | Column and data type mapping | Start with simple data before creating relationships | Map IDs, strings, money, dates/times, enums, nullability, and unique constraints |
| 4 | Repositories and CRUD | Once entities are clear, repositories become an intuitive data access point | Use `JpaRepository`, `save`, `findById`, `findAll`, `delete`, and handle `Optional` |
| 5 | Entity relationships and bidirectional consistency | Relationships require understanding foreign keys and owning sides before writing complex queries | Map `ManyToOne`, `OneToMany`, keep both sides synchronized, cascade, and orphan removal |
| 6 | Derived queries and method naming rules | Leverage simple queries before writing JPQL | Build filter queries by properties, relationships, ranges, status, and ordering |
| 7 | JPQL, `@Query`, and native queries | Choose the query language by need rather than defaulting to SQL | Distinguish JPQL using entities/properties from native SQL using tables/columns |
| 8 | Sorting, pagination, and projections | List queries need bounded data and only necessary fields | Use `Sort`, `Pageable`, `Page`, `Slice`, interface projections, and DTO projections |
| 9 | Transactions and business services | Individual operations are clear; now combine them into atomic business actions | Place `@Transactional` at the right boundaries and understand rollback, flush, commit |
| 10 | Fetching, lazy loading, and performance | Relationships exist; now learn to load data without N+1 or over-fetching | Use fetch joins, `@EntityGraph`, projections, and batch fetching deliberately |
| 11 | Dynamic queries with Specifications/Criteria | After fixed queries, learn to combine optional filters | Build composable search filters without creating many near-duplicate methods |
| 12 | Auditing, locking, and concurrent updates | When applications serve multiple users, data needs audit trails and protection | Use auditing, `@Version`, `@Lock`, and handle conflicts |
| 13 | Bulk operations, batching, and persistence context | Optimize after understanding normal behavior | Know how bulk updates differ from dirty checking and when to clear/refresh |
| 14 | Repository testing and operations | Conclude by verifying behavior in a realistic environment | Write slice/integration tests, inspect SQL, indexes, and migrations |

You can revisit an earlier step whenever practice exposes a knowledge gap. However, do not learn locking or batch optimization before understanding entity states, transactions, and relationships. Advanced topics only make sense once you understand the default behavior they alter.

## 4. The Running Business Model

### 4.1. Context

The example is a simple online store. Customers place orders; each order has multiple line items; each line item references a product and records the price at the time of ordering. An order has a status and a creation timestamp. The model is small enough to track visually yet rich enough in relationships to demonstrate nearly all Spring Data JPA features.

| Entity | Business meaning | Key data |
|---|---|---|
| Customer | Buyer | id, name, email |
| Product | Orderable product | id, sku, name, currentPrice, active |
| PurchaseOrder | A customer's order | id, orderNumber, customer, status, createdAt, items, totalAmount |
| OrderItem | A product line in an order | id, order, product, quantity, unitPrice |

Relationships between tables:

- One **Customer** can have many **PurchaseOrder** records; each order belongs to exactly one customer.
- One **PurchaseOrder** has many **OrderItem** records; each line item belongs to exactly one order.
- One **Product** can appear in many **OrderItem** records; each line item references exactly one product.
- The foreign key **customer_id** lives in the orders table; **order_id** and **product_id** live in the order items table.

You can picture the relationship diagram as follows:

```text
Customer (1) -------- (N) PurchaseOrder
                              |
                              | (1)
                              |
                              | (N)
                          OrderItem (N) -------- (1) Product
```

### 4.2. Business Rules to Keep Consistent

1. An order belongs to one customer. Do not create an order without identifying a valid customer.
2. A line item must reference a valid product and have **quantity > 0**.
3. **unitPrice** on **OrderItem** is the price snapshot taken at order time. Do not re-read **Product.currentPrice** to calculate historical orders, because product prices can change later.
4. Line item total equals **unitPrice × quantity**; order total equals the sum of line item totals.
5. An order can transition to confirmed status only when it has at least one line item and required business conditions are met.
6. Order status must transition through valid steps, such as **DRAFT → CONFIRMED → PAID → SHIPPED**; cancellation must follow separate rules. Do not allow arbitrary transitions between any two statuses.
7. Changes that create an order and add line items must live in the same transaction so partial orders are never saved.

These are rules for the learning example. In a real system, you would add inventory, tax, shipping, payment, refund, and cancellation policies according to product requirements. Do not pull those rules into entities without a business requirement.

### 4.3. Why Store Price on the Line Item?

Suppose today a product costs 100,000 VND and a customer buys two units. The order records **unitPrice = 100,000**, with a line total of 200,000 VND. Tomorrow the listed price increases to 120,000 VND. The old order history must still show 200,000 VND; therefore **OrderItem** stores the captured price, while **Product.currentPrice** reflects only the current price.

This rule distinguishes current catalog data from historical transaction data. It is an important example of why not every attribute should be derived by joining to another table.

## 5. Entity Mapping: Starting from Foreign Keys

The snippets below are **mapping illustrations**, not a standalone Java program; imports, getters, setters, and helper constructors are omitted. They capture design decisions to keep consistent across subsequent lessons.

A **PurchaseOrder** references the customer via **ManyToOne** and manages its list of line items via **OneToMany**:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true, length = 40)
    private String orderNumber;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderItem> items = new ArrayList<>();

    @Column(name = "total_amount", nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount = BigDecimal.ZERO;

    protected PurchaseOrder() {
    }

    public void addItem(OrderItem item) {
        items.add(item);
        item.attachTo(this);
    }

    public void removeItem(OrderItem item) {
        if (items.remove(item)) {
            item.detachFromOrder();
        }
    }
}
```

**OrderItem** is the side holding the **order_id** foreign key, so it is the owning side of the relationship with the order:

```java
@Entity
@Table(name = "order_items")
public class OrderItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false, precision = 19, scale = 2)
    private BigDecimal unitPrice;

    protected OrderItem() {
    }

    void attachTo(PurchaseOrder order) {
        this.order = order;
    }

    void detachFromOrder() {
        this.order = null;
    }

    public BigDecimal lineTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
```

In complete code, `OrderItem`'s constructor must validate product, quantity, and price; methods adding/removing line items must maintain both sides of the relationship and update the order total. Do not allow controllers to arbitrarily set **order**, **quantity**, **unitPrice**, or **totalAmount**. State-change and total-calculation operations should live inside aggregate behavior or an appropriate business service.

Some mapping notes:

- Entities need **@Id** and a **public** or **protected** no-arg constructor. Avoid declaring entities **final**; providers need to manage entities and proxies.
- Choose one consistent access strategy. Placing annotations on fields as shown tells JPA to use field access.
- Use **@Enumerated(EnumType.STRING)** to store enum names; **ORDINAL** stores numeric positions and can corrupt data if enum constant order changes.
- Use **BigDecimal** for money; do not use **float** or **double** for monetary calculations. Define precision/scale and rounding rules per business requirements.
- Use **Instant** for absolute timestamps; standardize time-zone storage and display between the application and database.
- **GenerationType.IDENTITY** suits certain databases but can impact batching. Choose an ID strategy based on your database and deployment requirements; do not treat one strategy as optimal for every system.
- Avoid using **@Data** or auto-generating **toString**, **equals**, and **hashCode** including every relationship. Traversing bidirectional collections can cause infinite recursion; accessing lazy relationships can emit unexpected SQL. Entity equality should be designed around entity lifecycle and the chosen ID strategy.

## 6. Owning Side, Cascade, and Relationship Lifecycle

JPA persists relationships based on the owning side. For the order–line item relationship, the **order_id** column lives in the **order_items** table, so **OrderItem.order** is the owning side. **mappedBy = "order"** in **PurchaseOrder.items** points to the Java property name on the child entity, not the SQL column name.

When adding a line item, adding it to the parent collection alone is not enough. You must also set **item.order**. Conversely, when removing, remove it from the collection and update the child side. Both steps can be encapsulated inside methods on **PurchaseOrder** so callers do not forget to update one side.

**cascade = CascadeType.ALL** on the order–line item relationship means persistence operations on the order can propagate to its items. **orphanRemoval = true** means an item removed from the relationship will be deleted when the persistence context synchronizes. Use them only when line items truly depend on the order's lifecycle.

Do not cascade delete operations from an order to **Customer** or **Product**: customers and products exist independently and may be referenced by many orders. Deleting an order must not delete a customer or product. Cascade is not a substitute for understanding data ownership.

## 7. Repositories and Queries on the Shared Model

Repositories declare the entity type and primary key type:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    List<PurchaseOrder>
        findByCustomer_IdAndStatusOrderByCreatedAtDesc(
            Long customerId,
            OrderStatus status
        );

    Page<PurchaseOrder> findByStatus(
        OrderStatus status,
        Pageable pageable
    );

    Optional<PurchaseOrder> findOneByOrderNumber(String orderNumber);
}
```

The first method name expresses the property path **customer.id**; the underscore clearly separates the relationship from the property. **JpaRepository** provides basic CRUD, pagination, and sorting. For conditional queries, Spring Data parses method names to build queries. When conditions become too complex or explicit query control is needed, use **@Query**.

JPQL example finding an order along with its customer:

```java
@Query("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.orderNumber = :orderNumber
    """)
Optional<PurchaseOrder> findWithCustomerByOrderNumber(
    @Param("orderNumber") String orderNumber
);
```

JPQL queries entities and Java properties (**PurchaseOrder**, **customer**, **orderNumber**), not SQL table/column names. Native queries use database syntax and are useful when database-specific features or SQL expressions that JPQL cannot represent cleanly are needed. In return, native queries are more tightly coupled to the schema and database engine.

Paginating a list of confirmed orders:

```java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.DESC, "createdAt")
);

Page<PurchaseOrder> page =
    repository.findByStatus(OrderStatus.CONFIRMED, pageable);
```

**Page** usually requires both a data query and a count query to calculate total pages. **Slice** only indicates whether more data follows, fitting when total record count is unnecessary. Always use a stable sort order, especially when paginating frequently changing data.

Do not return entire entities if a screen only needs order number, customer name, timestamp, and total amount. Projections or DTOs query only the needed fields, reducing payload size and preventing accidental lazy loading while serializing responses.

## 8. Transactions: Setting Boundaries Around Business Operations

An order-creation business flow might include: verifying the customer, creating a draft order, adding multiple line items, calculating the total, and saving. If one step fails, an order with only partial line items must not be left behind. Therefore, transactions should wrap business operations at the service layer:

```java
@Service
public class OrderService {

    private final PurchaseOrderRepository orderRepository;

    public OrderService(PurchaseOrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Long saveOrder(PurchaseOrder order) {
        PurchaseOrder saved = orderRepository.save(order);
        return saved.getId();
    }

    @Transactional(readOnly = true)
    public Optional<PurchaseOrder> findOrder(Long id) {
        return orderRepository.findById(id);
    }
}
```

This is an abbreviated example of transaction boundaries; a real service should accept appropriate input data, verify permissions and business rules, load related entities, and invoke aggregate behavior. Do not accept raw client-submitted entities and save them directly.

Inside a transaction, entities are managed by the persistence context. When modifying fields of a managed entity, dirty checking detects changes and the provider emits SQL on flush. **flush** synchronizes changes to the database but does not mean commit. Commit finishes the transaction; rollback reverts changes in the transaction according to Spring and database rules. Understand default rollback rules and declare **rollbackFor** when business logic has checked exceptions requiring rollback.

**readOnly = true** is an optimization hint/signal for the transaction manager and provider; it is not an absolute safeguard guaranteed to block every write statement. Avoid keeping transactions overly broad or making slow network calls while holding database locks.

## 9. Fetching and Performance

Entity relationships do not imply related data is always loaded together. **LAZY** defers loading until the property is accessed; **EAGER** asks the provider to load eagerly per the mapping contract, though it does not guarantee a single SQL statement.

N+1 occurs when an application loads N orders and then accesses each order's customer, triggering many extra queries. Solutions must depend on the use case:

- Use **join fetch** when a specific query needs relationship data.
- Use **@EntityGraph** to declare attributes to load for a repository method without changing global default mappings.
- Use DTO/interface projections when only partial data is needed.
- Consider batch fetching when multiple lazy relationships must be loaded in groups; this may be a provider-specific configuration option.
- Measure SQL and query counts in tests or development environments. Do not guess performance solely from Java method counts.

Be especially careful when paginating alongside a **OneToMany** collection fetch join: the join can duplicate parent rows and distort pagination/counts or force the provider to paginate in memory. You can paginate order IDs first and load details in a second query, or use an appropriate projection. Do not add fetch joins to every relationship merely to avoid lazy exceptions.

## 10. Dynamic Queries, Projections, and Advanced Topics

When an order search screen has many optional filters such as customer, status, date range, and total amount range, numerous derived methods quickly become unmanageable. **JpaSpecificationExecutor** and **Specification** allow composing predicates based on present criteria. Each predicate must use the proper data type, handle nulls cleanly, and be backed by indexes when querying large tables.

Projections limit fetched fields. Interface projections can be used for property-based queries or DTO projections for well-shaped results. With DTO constructor expressions in JPQL, the constructor and data types must match the select output.

When multiple transactions edit the same order concurrently, **@Version** supports optimistic locking: the update statement checks the version; if another transaction updated first, the remaining transaction receives a conflict error and must handle/retry according to business rules. Pessimistic locking (**@Lock** with **PESSIMISTIC_WRITE**) locks the record for the transaction's duration; use it when operations must be serialized, and account for deadlocks, lock duration, and access ordering.

Auditing can record **createdAt**, **createdBy**, **lastModifiedAt**, and **lastModifiedBy** using Spring Data auditing (**@CreatedDate**, **@LastModifiedDate**, **@CreatedBy**, **@LastModifiedBy**) and proper auditing configuration. This is a technical trail of record creation/modification; it does not replace business history such as who confirmed, canceled, or refunded an order.

Bulk JPQL updates/deletes run directly against the database and bypass individual entity dirty checking. The current persistence context may hold stale data; proactively flush/clear or refresh as needed. Lifecycle callbacks and managed entities are not updated automatically the way individual entity edits are. Batching reduces round-trips, but it should be measured on a real database and you should understand how the ID generation strategy affects it.

## 11. Testing and Verification

- Use **@DataJpaTest** to verify mappings, repository queries, and persistence behavior in an application slice.
- Use the same database type as production when verifying dialect, data types, locks, indexes, transactions, or native SQL. H2 is useful for fast tests, but it does not guarantee identical behavior to PostgreSQL, MySQL, or other databases.
- Use Testcontainers when repeatable real database instances are needed in integration tests.
- Verify both persisted data and behavior after reading it back; do not merely assert that a method returned an object.
- Test business rules: order totals, price snapshots at purchase time, valid statuses, rollback when adding a line item fails, and conflicts during concurrent updates.
- Inspect SQL when investigating N+1 queries, unindexed lookups, wrong pagination, or over-fetching columns.
- Use versioned migrations for controlled schema changes; do not rely on **ddl-auto=update** as a production schema management strategy.

## 12. Practice Roadmap Using the Same Model

You can use the following sequence of exercises to check your progress:

1. Create **Customer** and **Product**, save them, and read them back via repositories.
2. Create a draft **PurchaseOrder** for a customer; add two **OrderItem** instances with different quantities and captured prices.
3. Calculate the order total from line items and verify the result using **BigDecimal**.
4. Find orders by customer and status; sort newest orders first.
5. Paginate the order list; create a DTO containing only order number, customer name, timestamp, and total amount.
6. Use a transaction to confirm an order; force one step to fail and verify all changes roll back.
7. Load a list of orders with customers; observe SQL before and after adding a fetch join or entity graph.
8. Add date/status/amount filters using `Specification`.
9. Add **@Version**, simulate two transactions updating the same order concurrently, and handle the conflict.
10. Write integration tests against a database compatible with the deployment environment.

While practicing, keep entity names, property meanings, and price-snapshot rules consistent across lessons. If a lesson needs to extend the model, explicitly state the new property/table and its business rationale; do not silently change the meaning of data used in earlier lessons.

## 13. Issues to Spot Early

| Symptom | Common cause | Investigation direction |
|---|---|---|
| `LazyInitializationException` | Accessing a lazy relationship after the persistence context closed | Check transaction boundaries; use DTOs, fetch plans, or suitable queries |
| Many queries for one list | N+1 when accessing a relationship per entity | Enable SQL logging, count queries, choose entity graph/fetch join/projection |
| Added to collection but FK unchanged | Updated only the inverse side without setting the owning side | Synchronize `OrderItem.order` and `PurchaseOrder.items` |
| Deleting an order removes shared data | Cascade `REMOVE` placed on a non-owning lifecycle relationship | Cascade only to child entities truly owned by the parent |
| Enum reads wrong values after reordering constants | Using ordinal | Store enums as `STRING` and manage value changes |
| Order total changes when product price changes | Recomputing history using current price | Store captured price in `OrderItem.unitPrice` |
| Duplicate or missing paginated results | Collection join duplicates rows or unstable sort order | Inspect SQL/counts and use an appropriate pagination strategy |
| In-memory entity data stale after bulk update | Bulk query bypasses current managed state | Flush/clear/refresh persistence context appropriately |
| Duplicate data or lost updates | Missing unique constraint, transaction, or locking | Identify invariants and enforce them at database and business layers |

## 14. How to Use the Model in Subsequent Lessons

Each lesson should answer four questions before diving into APIs:

1. **What business problem is being solved?** Example: find confirmed orders for a customer.
2. **Which data is involved?** Example: `PurchaseOrder`, `Customer`, status, and creation timestamp.
3. **Which constraints must hold?** Example: the customer must exist; pagination ordering is stable; historical prices do not change.
4. **How much data needs to be read/written?** Example: list screens only need a DTO; detail screens need line items and products.

Only then choose repository methods, JPQL, projections, entity graphs, transactions, or locking. This approach separates business requirements from technical choices while keeping examples connected across lessons.

**Core principle:** entities reflect data managed by the persistence context; repositories represent data access operations; services coordinate transactions and business rules; DTOs shape data exchanged across application boundaries. Keeping these roles clear makes Spring Data JPA applications easier to test, easier to optimize, and less prone to data consistency bugs.