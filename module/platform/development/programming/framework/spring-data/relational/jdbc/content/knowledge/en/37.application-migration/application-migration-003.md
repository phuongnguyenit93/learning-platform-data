# Replacing JPA Annotations with Spring Data JDBC Metadata

Migrating an application from JPA to Spring Data JDBC is not simply swapping annotation imports by similar names. The two frameworks have different persistence models: JPA manages entities through a persistence context, object associations, and dirty checking; Spring Data JDBC focuses on aggregates, repositories, and more explicit SQL operations.

During migration, you need to re-map the intent of the domain model and database schema. Some annotations share similar names such as `@Table`, `@Column`, `@Id`, and `@Version`, yet live in different packages. Other JPA annotations have no direct counterpart because Spring Data JDBC does not provide lazy loading, a persistence context, cascade graphs, or ORM-style association mapping.

This lesson guides you through replacing JPA metadata with Spring Data JDBC metadata, translating entity relationships into suitable aggregates/collections, configuring IDs, embedded value objects, auditing, and converters, while highlighting cases that require redesign rather than mechanical annotation replacement.

## 1. Start from the Persistence Model Differences

### 1.1. JPA Manages Entities in a Persistence Context

In JPA, entities are typically managed by an `EntityManager`. Once an entity is loaded into the persistence context, field changes can be written to the database on flush/commit without calling repository save for every mutation.

JPA also supports:

- Entity associations via `@OneToOne`, `@OneToMany`, `@ManyToOne`, and `@ManyToMany`.
- Fetch strategies such as LAZY/EAGER.
- Cascade operations and orphan removal.
- Dirty checking.
- Entity lifecycle callbacks.
- Inheritance mapping and various other ORM strategies.

### 1.2. Spring Data JDBC Manages Aggregates

Spring Data JDBC does not maintain a persistence context and does not track every object mutation in a long-lived session. The application loads an aggregate, mutates state, and calls repository save to persist it.

The model is organized around the aggregate root:

- The aggregate root is the entry point for loading/saving a group of owned objects.
- Child objects inside an aggregate are persisted alongside the aggregate root according to mapping.
- Other aggregates are referenced by identifier; no automatic object associations are created across aggregates.
- There are no JPA-style lazy-loading proxies.
- There is no automatic dirty checking; repository save must be called.
- The database schema must be managed by migrations or a separate process.

Example:

```text
JPA:
Order --@OneToMany--> OrderLine
  |
  +-- EntityManager tracks the entity graph

Spring Data JDBC:
PurchaseOrder (aggregate root)
  |
  +-- @MappedCollection --> OrderLine
  |
  +-- repository.save(purchaseOrder)

Customer (another aggregate)
  ^
  |
  +-- customerId (identifier reference)
```

Before changing annotations, decide which objects belong to the same aggregate and which objects are independent aggregates. This decision shapes saving, transactions, concurrency, and performance.

## 2. Core Annotations: Table, Id, and Column

Several annotations share names with JPA, but you must use the Spring Data annotations.

| Meaning | JPA | Spring Data JDBC |
| --- | --- | --- |
| Mark entity/table | `jakarta.persistence.Entity`, `Table` | `org.springframework.data.relational.core.mapping.Table` |
| Mark ID | `jakarta.persistence.Id` | `org.springframework.data.annotation.Id` |
| Map column name | `jakarta.persistence.Column` | `org.springframework.data.relational.core.mapping.Column` |
| Ignore property | `jakarta.persistence.Transient` | `org.springframework.data.annotation.Transient` |
| Optimistic version | `jakarta.persistence.Version` | `org.springframework.data.annotation.Version` |

Do not mix both annotation sets just because they share simple names. IDEs can auto-import the wrong package when both JPA and Spring Data dependencies are present during a transition period.

### 2.1. @Table

JPA:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    // ...
}
```

Spring Data JDBC:

```java
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {
    // ...
}
```

Spring Data Relational's `@Table` specifies the table name for the mapped aggregate/entity. JPA's `@Entity` is not needed; Spring Data JDBC does not use it to manage mappings.

If `@Table` is omitted, Spring Data derives the table name from the class name via the naming strategy. With existing schemas or specific naming conventions, declare it explicitly to prevent mismatches across environments.

### 2.2. @Id

JPA:

```java
import jakarta.persistence.Id;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;

@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Spring Data JDBC:

```java
import org.springframework.data.annotation.Id;

@Id
private Long id;
```

Spring Data JDBC does not use `@GeneratedValue`. For database-generated identity keys, configure the ID column in the schema so the database generates values on insert. When a new entity has a null ID, Spring Data JDBC can detect newness and retrieve the generated key based on database/driver capabilities.

Illustrative DDL:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE
);
```

Do not carry `GenerationType.IDENTITY`, `SEQUENCE`, or `TABLE` over to Spring Data JDBC. If the system uses sequences or custom ID generation, clarify the database/driver mechanism and how IDs are supplied in the application; custom ID generation before saving may be needed.

If the application assigns UUIDs or other IDs prior to calling save, review how Spring Data JDBC detects new entities. With a non-null ID, the framework may treat an entity as existing depending on the newness strategy. You can use a version property or implement `Persistable` with `isNew()` when exact insert/update state control is needed.

### 2.3. @Column

JPA:

```java
import jakarta.persistence.Column;

@Column(name = "order_number", nullable = false, length = 40)
private String orderNumber;
```

Spring Data JDBC:

```java
import org.springframework.data.relational.core.mapping.Column;

@Column("order_number")
private String orderNumber;
```

Spring Data JDBC's `@Column` maps a property to a column name. JPA attributes like `nullable`, `length`, and `unique` do not translate into schema-generation metadata here.

Nullability, lengths, unique constraints, and data types must be defined in schemas/migrations:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE
);
```

Spring Data JDBC focuses on mapping objects to an existing schema. Manage DDL with Flyway, Liquibase, or your project's schema provisioning tool.

## 3. Converting a Simple JPA Entity

JPA example:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    @Column(nullable = false, unique = true)
    private String email;

    @Version
    private Long version;

    // Constructor, getters, setters.
}
```

Spring Data JDBC:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    private String email;

    @Version
    private Long version;

    // Constructor, getters, and domain behavior.
}
```

Repository:

```java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
```

Migration points:

- Remove `@Entity`.
- Use Spring Data Relational `@Table`.
- Use Spring Data Commons `@Id` and `@Version`.
- Use Spring Data Relational `@Column`.
- Remove `@GeneratedValue` and delegate ID generation to schema/database or a custom mechanism.
- Move constraints into DDL/migrations.
- Replace `JpaRepository` with an appropriate repository abstraction such as `CrudRepository` or `ListCrudRepository`.

If paging/sorting is needed, use the repository interfaces and query support provided by your Spring Data JDBC version. Do not assume every `JpaRepository` method exists identically on JDBC repositories.

## 4. Converting @OneToMany to @MappedCollection

JPA commonly models one-to-many relationships with association annotations:

```java
@OneToMany(
    mappedBy = "purchaseOrder",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

In Spring Data JDBC, if `OrderLine` is owned by `PurchaseOrder`, represent the collection within the aggregate using `@MappedCollection`.

```java
import org.springframework.data.relational.core.mapping.MappedCollection;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;

    @MappedCollection(
        idColumn = "purchase_order_id",
        keyColumn = "line_number"
    )
    private List<OrderLine> lines = new ArrayList<>();
}
```

Child entity:

```java
@Table("order_lines")
public class OrderLine {

    private String productCode;
    private Integer quantity;
    private BigDecimal unitPrice;

    // Constructor and accessors.
}
```

Illustrative schema:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE order_lines (
    purchase_order_id BIGINT NOT NULL,
    line_number INTEGER NOT NULL,
    product_code VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (purchase_order_id, line_number),
    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (purchase_order_id)
        REFERENCES purchase_orders(id)
);
```

`idColumn` is the column on the child table holding the aggregate root's ID. `keyColumn` stores the collection's key/index when element distinction is needed—such as element position in a `List` or key in a `Map`. Column names must match the actual schema.

### 4.1. @MappedCollection Expresses Ownership

When a collection is mapped inside an aggregate:

- The aggregate root is the entry point for loading and saving the collection.
- Child objects are saved with the aggregate root per the persistence model.
- No back-reference property to the root such as `OrderLine.purchaseOrder` is needed just for JPA relationship management.
- The foreign key lives on the child table and points back to the aggregate root.
- Adding and removing children should go through aggregate domain methods.

Example:

```java
public void addLine(
        String productCode,
        int quantity,
        BigDecimal unitPrice) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
            "Quantity must be greater than 0"
        );
    }

    lines.add(new OrderLine(
        productCode,
        quantity,
        unitPrice
    ));
}

public void removeLine(String productCode) {
    lines.removeIf(line ->
        line.getProductCode().equals(productCode)
    );
}
```

After modifying the collection, call `repository.save(order)` to persist the aggregate. Spring Data JDBC does not have automatic dirty checking like JPA.

### 4.2. @MappedCollection with Set, List, and Map

`@MappedCollection` can customize the aggregate reference column and key/index column:

```java
@MappedCollection(idColumn = "order_id")
private Set<OrderTag> tags = new LinkedHashSet<>();
```

For `Map`:

```java
@MappedCollection(
    idColumn = "order_id",
    keyColumn = "attribute_name"
)
private Map<String, OrderAttribute> attributes =
    new LinkedHashMap<>();
```

For `List`, the key column can store element position. Design the key column's data type and constraints to match collection semantics.

Do not assume database row order is inherently stable without a key/index or an explicit `ORDER BY`. If order is part of the domain, persist and retrieve it explicitly.

## 5. Converting @ManyToOne and @ManyToMany

There is no direct one-for-one replacement of every JPA association with an equivalent Spring Data JDBC annotation. Examine aggregate boundaries.

### 5.1. @ManyToOne to Another Aggregate

JPA:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
```

In Spring Data JDBC, if `Customer` is a separate aggregate, usually store the reference ID:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;
}
```

The `purchase_orders` table keeps the `customer_id` foreign key. When `Customer` details are needed, the application service loads it via `CustomerRepository` or a suitable query projection.

```java
@Transactional(readOnly = true)
public OrderDetails getDetails(Long orderId) {
    PurchaseOrder order = orders.findById(orderId)
        .orElseThrow();

    Customer customer = customers.findById(order.getCustomerId())
        .orElseThrow();

    return new OrderDetails(order, customer);
}
```

These are two aggregates loaded separately. There is no lazy proxy automatically standing in for a `customer` property.

### 5.2. @ManyToMany

JPA:

```java
@ManyToMany
@JoinTable(
    name = "product_categories",
    joinColumns = @JoinColumn(name = "product_id"),
    inverseJoinColumns = @JoinColumn(name = "category_id")
)
private Set<Category> categories;
```

With Spring Data JDBC, consider modeling the link table as a dedicated association entity or aggregate:

```java
@Table("product_category_links")
public class ProductCategoryLink {

    @Id
    private Long id;

    @Column("product_id")
    private Long productId;

    @Column("category_id")
    private Long categoryId;
}
```

If the relationship carries attributes such as order, assignment time, assigned by, or status, an association entity expresses the domain clearly.

If the link table is owned by one aggregate root, you can model it as a child inside that aggregate using `@MappedCollection`. If both sides are independent aggregates, store reference IDs and manage links via a dedicated repository/service.

### 5.3. @JoinColumn

JPA's `@JoinColumn` has no one-to-one equivalent annotation for all relationships in Spring Data JDBC.

- For child collections, use `@MappedCollection(idColumn = "...")` on the aggregate root property to specify the FK column on the child table.
- For references to other aggregates, map the ID column with `@Column` or a naming convention.
- For link tables, model association rows and declare FKs via migrations.

Do not place JPA's `@JoinColumn` on a Spring Data JDBC property expecting the framework to generate association mappings.
## 6. Converting @Embeddable and @Embedded

JPA uses `@Embeddable` to define a value object and `@Embedded` to store its properties in the owning entity's table. In Spring Data JDBC, simply annotate the property with `@Embedded`; the value type does not need `@Embeddable`.

Spring Data JDBC example:

```java
import org.springframework.data.relational.core.mapping.Embedded;

public class Address {
    private String street;
    private String city;
    private String postalCode;
}

@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String name;

    @Embedded(prefix = "shipping_")
    private Address shippingAddress;
}
```

Columns map to `shipping_street`, `shipping_city`, and `shipping_postal_code`. Prefixes avoid column name collisions if an aggregate has multiple value objects of the same type, such as shipping and billing addresses.

### 6.1. Handling Empty Value Objects

`@Embedded` lets you configure behavior when all columns of the embedded object are null:

```java
@Embedded(
    prefix = "shipping_",
    onEmpty = Embedded.OnEmpty.USE_NULL
)
private Address shippingAddress;
```

With `USE_NULL`, if all prefixed columns are null, the property maps to null. With `USE_EMPTY`, the framework instantiates the embedded object even when its internal values are all null. Pick semantics that match your domain and existing schema.

If the domain requires `Address` to always exist, ensure schemas and validation enforce that invariant. Mapping annotations do not replace `NOT NULL` constraints or business checks.

## 7. Converting @ElementCollection and Value Collections

JPA can store value collections using `@ElementCollection` with `@CollectionTable`. In Spring Data JDBC, model the collection in a way compatible with relational mapping and aggregate ownership. For collections whose elements have structure or require keys/indices, create a value/child type and use `@MappedCollection`:

```java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @MappedCollection(
        idColumn = "customer_id",
        keyColumn = "phone_position"
    )
    private List<PhoneNumber> phoneNumbers =
        new ArrayList<>();
}

public class PhoneNumber {
    @Column("phone_number")
    private String value;
}
```

The schema can use a composite key consisting of `customer_id` and `phone_position`. This design makes it explicit that the collection belongs to the `Customer` aggregate and preserves ordering if required by the domain.

For simple collections, verify type mapping and converter support in your Spring Data JDBC version. If per-element metadata is needed later, a child class is usually clearer than a scalar collection.

## 8. Converting @Version and Optimistic Locking

JPA:

```java
@Version
private Long version;
```

Spring Data JDBC also supports optimistic locking with an identically named annotation in a different package:

```java
import org.springframework.data.annotation.Version;

@Version
private Long version;
```

When saving an aggregate, Spring Data JDBC uses the version to detect concurrent updates. If the version in the database no longer matches the version read by the aggregate, the operation can fail with `OptimisticLockingFailureException`.

The version column must exist in the schema:

```sql
ALTER TABLE purchase_orders
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
```

Do not use `jakarta.persistence.Version` on Spring Data JDBC entities. Also do not manually increment the version inside domain methods if the framework manages the version on repository save.

If custom direct SQL `UPDATE` statements exist, those statements must manually check the old version condition and increment the version properly. Custom SQL does not automatically apply repository optimistic-locking metadata.

## 9. Converting Auditing Metadata

JPA can use entity listeners and callbacks to populate created/modified fields. Spring Data JDBC has its own auditing support.

```java
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;

public class Customer {

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedDate;
}
```

Enable auditing via configuration:

```java
@Configuration
@EnableJdbcAuditing
public class JdbcAuditingConfiguration {
}
```

If the current actor is needed, provide an `AuditorAware`:

```java
@Bean
AuditorAware<String> auditorAware() {
    return () -> Optional.of("system");
}
```

In real applications, obtain the actor from the security context or appropriate execution context. If controllable timestamps are needed in tests, configure a `DateTimeProvider`.

Auditing only runs for lifecycle operations managed by Spring Data JDBC. Direct SQL through `JdbcTemplate` or custom statements does not automatically trigger auditing callbacks. If direct SQL writes exist, update audit columns explicitly or use database triggers consistently.

## 10. Converting Converters and Enum Mappings

JPA typically uses `@Convert`/`AttributeConverter` to translate Java types to database types. Spring Data JDBC uses Spring Data custom conversions.

Example domain enum stored as a short code:

```java
public enum OrderStatus {
    PENDING,
    CONFIRMED,
    CANCELLED
}
```

Writing converter:

```java
@WritingConverter
public class OrderStatusWritingConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return switch (source) {
            case PENDING -> "P";
            case CONFIRMED -> "C";
            case CANCELLED -> "X";
        };
    }
}
```

Reading converter:

```java
@ReadingConverter
public class OrderStatusReadingConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return switch (source) {
            case "P" -> OrderStatus.PENDING;
            case "C" -> OrderStatus.CONFIRMED;
            case "X" -> OrderStatus.CANCELLED;
            default -> throw new IllegalArgumentException(
                "Unknown order status: " + source
            );
        };
    }
}
```

Register converters in Spring Data JDBC configuration, for example via `AbstractJdbcConfiguration.userConverters()`:

```java
@Configuration
public class JdbcConversionConfiguration
        extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
            new OrderStatusWritingConverter(),
            new OrderStatusReadingConverter()
        );
    }
}
```

Exact hook/configuration names must match your Spring Data Relational version. In Spring Boot, avoid registering conflicting conversion beans; integrate converters using the configuration mechanism already used by your application.

Do not assume legacy JPA converters will automatically be invoked by Spring Data JDBC. Test both read and write directions against existing database data.

## 11. @Transient and Non-Persisted Properties

JPA:

```java
@Transient
private BigDecimal calculatedTotal;
```

Spring Data JDBC:

```java
import org.springframework.data.annotation.Transient;

@Transient
private BigDecimal calculatedTotal;
```

Properties annotated as transient are not mapped to columns. They can hold derived values on domain objects or in-memory-only data.

Do not confuse Spring Data's `@Transient` with Java's `transient` keyword. During migration, inspect imports and verify the property does not appear in generated SQL or mappings.

## 12. JPA Annotations Without Direct Counterparts

| JPA Annotation/Capability | How to Handle in Spring Data JDBC |
| --- | --- |
| `@Entity` | Remove; use `@Table` when an explicit table name is needed. |
| `@GeneratedValue` | Use database-supported ID generation or generate IDs in application/custom code. |
| `@OneToMany` | If child belongs to aggregate, use `@MappedCollection`. |
| `@ManyToOne` | Typically store foreign key as an ID; load the other aggregate separately. |
| `@OneToOne` | Determine whether value object, owned child, or separate aggregate; no general annotation replacement. |
| `@ManyToMany` | Model association row/link entity with clear ownership. |
| `@JoinColumn` | Use `@MappedCollection(idColumn=...)` for children or `@Column` for ID references. |
| `@JoinTable` | Design association table and separate child/aggregate mapping. |
| `fetch = LAZY/EAGER` | No JPA-style lazy-loading proxies; design explicit query/load boundaries. |
| `cascade` / `orphanRemoval` | Manage objects belonging to the aggregate through the root and call save; redefine ownership. |
| `@Embeddable` / `@AttributeOverride` | Use value types with `@Embedded(prefix=...)`. |
| `@ElementCollection` | Model aggregate-owned collection with suitable mapping, usually `@MappedCollection`. |
| `@EntityListeners` | Use Spring Data entity callbacks/auditing or application services. |
| `@Convert` | Use Spring Data custom converters. |
| `@OrderColumn` | Use key/index column on `@MappedCollection` if ordering is domain data. |
| `@Inheritance` / discriminator mapping | Design concrete tables and mappings; no general ORM inheritance mapping equivalent. |
| `@Formula` | Use queries, projections, or custom SQL to compute values. |
| `@Temporal` | Prefer Java Time types and corresponding JDBC mappings. |
| `@Lob` | Choose SQL types and Java types suited to database/driver; test actual mapping. |

Do not try to preserve the entire JPA object graph verbatim by only swapping annotations. If the domain relies on lazy associations, cross-aggregate cascades, or dirty checking, refactor application services and transaction boundaries.

## 13. Repositories and Query Metadata Also Need Updating

JPA repositories typically extend `JpaRepository` and may use JPQL or native queries. Spring Data JDBC repositories typically extend `CrudRepository` or `ListCrudRepository`:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    List<PurchaseOrder> findByStatus(OrderStatus status);
}
```

For custom SQL, use Spring Data JDBC's `@Query`:

```java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    @Query("""
        SELECT id, order_number, status, version
        FROM purchase_orders
        WHERE status = :status
        ORDER BY id
        """)
    List<PurchaseOrder> findByStatus(@Param("status") String status);
}
```

Spring Data JDBC queries are SQL operating against the database schema. They are not JPQL; you cannot keep JPQL using entity/property names and merely swap the annotation import.

If a query returns a DTO/projection, verify how columns map to constructors/properties. For complex joins, aggregate roots, or reporting, consider custom repositories/`JdbcTemplate` or MyBatis as needed.

## 14. Complete Aggregate Migration Example

Suppose the current JPA model includes `PurchaseOrder`, `OrderLine`, and `Customer`:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(
        mappedBy = "purchaseOrder",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    @Version
    private Long version;
}
```

Before migrating, decide:

- `PurchaseOrder` is the aggregate root.
- `OrderLine` is owned by `PurchaseOrder`.
- `Customer` is a separate aggregate.
- `PurchaseOrder` holds the customer ID.
- `ShippingAddress` (if present) is an embeddable value object.
- Order invariants are checked in domain methods.

Spring Data JDBC model:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("customer_id")
    private Long customerId;

    @MappedCollection(
        idColumn = "purchase_order_id",
        keyColumn = "line_number"
    )
    private List<OrderLine> lines = new ArrayList<>();

    @Version
    private Long version;

    public void addLine(OrderLine line) {
        lines.add(line);
    }

    public void removeLine(int index) {
        lines.remove(index);
    }
}
```

Child:

```java
public class OrderLine {

    @Column("product_code")
    private String productCode;

    private Integer quantity;

    @Column("unit_price")
    private BigDecimal unitPrice;
}
```

Application service:

```java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository orders;

    public PurchaseOrderService(
            PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public PurchaseOrder addLine(
            Long orderId,
            OrderLine line) {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow();

        order.addLine(line);
        return orders.save(order);
    }
}
```

The write path explicitly shows loading, mutating the aggregate, and saving. If a use case needs `Customer` details, the service loads `Customer` separately or queries a DTO joining both tables.

## 15. Schema Migrations When Updating Metadata

Annotation mappings and the database schema must remain synchronized. Spring Data JDBC does not alter the schema simply because code switched from JPA annotations to Spring Data annotations.

A safe workflow:

1. Inventory existing tables, columns, foreign keys, indexes, and constraints.
2. Identify the aggregate root and ownership for each child table.
3. Document ID generation, versioning, auditing, and converters in use.
4. Migrate annotations and imports aggregate by aggregate.
5. Write migrations if table/column names, key columns, or constraints change.
6. Update SQL queries, repository methods, and custom mappers.
7. Verify legacy data compatibility with new converters.
8. Run integration tests on a production-equivalent database.
9. Migrate application services from dirty checking to explicit saves.
10. Deploy in compatible phases if old and new code coexist during rolling deployments.

Do not rename columns solely to match a new naming convention without reason. Keeping the existing schema and mapping accurately via `@Column`/`@MappedCollection` usually lowers migration risk.

## 16. Testing After Migration

### 16.1. Basic Mapping Tests

Use `@DataJdbcTest` to confirm aggregates insert, load, and update properly:

```java
@DataJdbcTest
class PurchaseOrderRepositoryTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Test
    void savesAndLoadsAggregate() {
        PurchaseOrder order = PurchaseOrder.create(42L);
        order.addLine(
            new OrderLine("SKU-1", 2, new BigDecimal("12.50"))
        );

        PurchaseOrder saved = orders.save(order);

        PurchaseOrder loaded =
            orders.findById(saved.getId()).orElseThrow();

        assertThat(loaded.getCustomerId()).isEqualTo(42L);
        assertThat(loaded.getLines()).hasSize(1);
    }
}
```

The test schema must include tables, foreign keys, and key columns matching the mapping. If using a migration tool in production, consider running migrations in tests so hand-written test schemas do not drift.

### 16.2. Testing Embedded Value Objects

Verify prefixed columns read correctly, two embedded objects of the same type do not collide on column names, all-null embedded column semantics match `onEmpty`, and value objects persist cleanly when modified.

### 16.3. Testing Generated IDs and Assigned IDs

Verify the database generates IDs for new entities with null IDs. If using UUIDs or application-assigned IDs, test the newness strategy so the repository inserts instead of mistakenly updating.

### 16.4. Testing Optimistic Locking and Auditing

Read two copies with the same version, save one, and confirm the stale copy fails with a conflict. If auditing is enabled, verify created/modified fields are populated according to the configured auditor and clock.

### 16.5. Testing Queries and Transactions

Ensure custom SQL uses accurate column names after migration, operations requiring atomicity run inside the same transaction, direct SQL does not inadvertently bypass version/audit behavior, aggregate children save/delete according to chosen ownership, and no code remains dependent on lazy loading or `EntityManager`.

## 17. JPA-to-Spring Data JDBC Migration Checklist

| Item | Questions to Answer |
| --- | --- |
| Aggregate boundary | Which object is the root, which are children, and which are separate aggregates? |
| Table/column | Switched to Spring Data Relational `@Table`/`@Column` in the right package? |
| ID | Does the database or application generate IDs? How are new entities detected? |
| Version | Using `org.springframework.data.annotation.Version` and does the version column exist? |
| One-to-many | Child collections converted to `@MappedCollection` with right FK/key columns? |
| Many-to-one | Object associations converted to identifier references where needed? |
| Many-to-many | Association tables have clear ownership and mapping? |
| Embedded | Value objects using `@Embedded` and suitable prefixes? |
| Converter | Reading/writing conversions registered and tested bidirectionally? |
| Auditing | `@EnableJdbcAuditing` enabled and auditor/time providers supplied? |
| Repository | Removed `JpaRepository`/JPQL and migrated to JDBC repositories/queries? |
| Lifecycle | Dirty checking/cascade/lazy behavior replaced by service and aggregate methods? |
| Schema | Do migrations preserve constraints, indexes, foreign keys, and legacy data? |
| Tests | Are integration tests running on a production-equivalent database and driver? |

## 18. Common Issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Entity is not mapped | Still using `@Entity` or JPA annotations. | Use Spring Data `@Table`, `@Id`, `@Column`. |
| Wrong `@Id` package imported | IDE picked `jakarta.persistence.Id`. | Select `org.springframework.data.annotation.Id`. |
| ID is not generated | Expecting `@GeneratedValue` to work in Spring Data JDBC. | Configure database identity/default or a custom ID generator. |
| Repository updates instead of inserting | Pre-assigned ID makes entity look existing. | Check version/newness and implement `Persistable` when needed. |
| Child table is not saved | Missing `@MappedCollection` or wrong FK column. | Check aggregate ownership, `idColumn`, `keyColumn`, and schema. |
| Customer object does not auto-load | Expecting `@ManyToOne`/lazy proxy. | Store customer ID and load/query separately. |
| Field changes are not persisted | Expecting JPA dirty checking. | Call repository `save` within an appropriate transaction. |
| Child deletion behaves unexpectedly | Expecting JPA cascade/`orphanRemoval`. | Mutate collection via aggregate root then save; verify mapping. |
| Embedded columns collide | Multiple value objects share property names. | Use `@Embedded(prefix = "...")`. |
| Constraints are not created | Using JPA `@Column` nullable/unique attributes. | Define constraints in migrations. |
| JPQL fails to execute | Reusing JPA queries in JDBC repositories. | Write SQL targeting real table/column names. |
| Auditing does not update | Auditing not enabled or writing with direct SQL. | Configure auditing and handle direct SQL explicitly. |
| Enums read incorrectly | JPA converters are ignored by Spring Data JDBC. | Register reading/writing converters and test legacy data. |

> **Migrating JPA to Spring Data JDBC is a persistence model shift, not merely swapping annotations.** Use Spring Data's `@Table`, `@Column`, `@Id`, and `@Version`; use `@MappedCollection` for aggregate-owned children and `@Embedded` for value objects. Reference other aggregates by ID, manage schemas via migrations, and replace dirty checking, cascading, and lazy loading with domain methods, repository saves, and explicit queries.

### References

- [Spring Data Relational — Mapping](https://docs.spring.io/spring-data/relational/reference/mapping.html): mapping metadata and object-relational mapping conventions.
- [Spring Data JDBC — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): aggregates, embedded objects, and mapped collections.
- [Spring Data JDBC — Entity Persistence](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): inserts/updates, IDs, and optimistic locking.
- [Spring Data JDBC — Custom Conversions](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): converting between Java types and JDBC types.
- [Spring Data JDBC — Auditing](https://docs.spring.io/spring-data/relational/reference/jdbc/auditing.html): auditing annotations and auditor configuration.
- [Spring Data JDBC — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): repository queries and custom SQL.
- [Spring Data Commons — Persistable API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Persistable.html): customizing new entity detection.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): semantics of JPA entities, relationships, lifecycles, and mappings.
