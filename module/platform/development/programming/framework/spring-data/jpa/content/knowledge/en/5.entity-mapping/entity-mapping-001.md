# @Entity, @Table, and the Relationship Between Entity Name and Table Name

In JPA, **the Entity name and the database table name are two different identifiers**. The entity name is used in JPQL and JPA APIs; the table name specifies the physical table mapped in the database. A Java class can keep the name `PurchaseOrder`, be declared with the entity name `OrderRecord`, and simultaneously map to the `purchase_orders` table.

Understanding these two naming layers correctly helps avoid query errors, mapping errors, table name conflicts, and mismatches between code and schema. This lesson uses Spring Data JPA with Jakarta Persistence in Spring Boot 3.x.

## 1. Distinguishing class name, entity name, and table name

There are three concepts to separate:

| Concept | Example | Where it is used |
|---|---|---|
| Java class name | `PurchaseOrder` | Java type, constructor, repository generic |
| JPA entity name | `OrderRecord` | JPQL, entity name in JPA metadata, and some query APIs |
| Database table name | `purchase_orders` | SQL, database schema, migrations, and DB admin tools |

If no custom name is declared, the default entity name is the class name without its package. For example, the class `com.example.orders.PurchaseOrder` has the default entity name `PurchaseOrder`.

The `@Entity(name = "...")` annotation allows changing the entity name. The `@Table(name = "...")` annotation specifies the database table to which the entity maps.

Example:

```java
@Entity(name = "OrderRecord")
@Table(name = "purchase_orders")
public class PurchaseOrder {
    // ...
}
```

In this example:

- Java code still declares the type `PurchaseOrder`.
- JPQL references the entity by the name `OrderRecord`.
- SQL accesses the `purchase_orders` table.
- Spring Data repository still declares generics with the Java type `PurchaseOrder`.

Changing the entity name does not change the Java class name and does not change the table name. Changing the table name does not automatically change the entity name.

## 2. @Entity declares a persistent entity

A class managed by JPA must be annotated with `@Entity`. The annotation belongs to the `jakarta.persistence` package in Jakarta Persistence, used with Spring Boot 3.x.

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Customer() {
    }
}
```

Basic rules of an entity:

1. The class must be a top-level class or a suitable static nested class; do not declare an entity as `final`.
2. The entity must have a `public` or `protected` no-argument constructor, so the provider can instantiate the entity.
3. The entity must have a primary key annotated with `@Id` or `@EmbeddedId`.
4. Persistent attributes must follow JPA access rules. When using field access, the provider reads/writes fields; when using property access, the provider uses getters/setters.
5. `final` should not be used for persistent fields or methods that the provider needs to manage/proxy.
6. Do not mark every attribute as persistent mindlessly. Use `@Transient` for state used only for in-memory processing and not persisted to the database.

An entity is an object with identity and a persistence lifecycle. It differs from a DTO, request model, or utility class that only holds data. Do not annotate every Java class with `@Entity`; only objects belonging to the data model that need to be managed by JPA should be entities.

### 2.1. Default entity name

If the `name` attribute is not passed, the default entity name is the simple name of the class:

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;
}
```

The default entity name is `PurchaseOrder`, not `com.example.orders.PurchaseOrder`. Because the entity name is used in JPQL, two entities in the same persistence unit should not have duplicate entity names. If two modules have classes with the same name, consider setting an explicit entity name or separating persistence units along appropriate data boundaries.

### 2.2. Setting an explicit entity name

```java
@Entity(name = "OrderRecord")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

The name in `@Entity(name = "OrderRecord")` is a logical name in JPA. It is not the table name and not the Spring bean name. This name must be unique within the persistence unit so JPQL can distinguish entities.

Do not arbitrarily change the entity name when the application has JPQL strings, named queries, native mappings, or code using JPA metadata referencing the old name. If you change it, you must find and update all usages.

## 3. @Table maps the entity to a physical table

`@Table` specifies the table where the entity is stored. If omitted, JPA uses the default table name rule based on the entity name; the physical result may also be affected by the implicit/physical naming strategy configured by the provider or Spring Boot.

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;
}
```

By declaring `name = "purchase_orders"`, we explicitly express the contract between the entity and the database. This approach is useful when the class name follows Java camelCase conventions while the table name follows SQL snake_case conventions, or when the database already has an independently managed schema.

### 3.1. Common attributes of @Table

| Attribute | Meaning | Example |
|---|---|---|
| `name` | Table name | `purchase_orders` |
| `schema` | Schema containing the table | `sales` |
| `catalog` | Catalog containing the table, depending on the database | `shop_catalog` |
| `uniqueConstraints` | Declares unique constraints at the table level | `order_number` must be unique |
| `indexes` | Declares indexes at the table level | Index on `created_at` |

A more complete example:

```java
@Entity
@Table(
    name = "purchase_orders",
    schema = "sales",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_purchase_orders_order_number",
            columnNames = "order_number"
        )
    },
    indexes = {
        @Index(
            name = "idx_purchase_orders_created_at",
            columnList = "created_at"
        )
    }
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, length = 40)
    private String orderNumber;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected PurchaseOrder() {
    }
}
```

In the example, `schema = "sales"` requires the table to reside in the sales schema of the database. The schema must exist or be managed by migrations/deployment configuration. Not all databases organize schemas/catalogs in the same way.

`uniqueConstraints` and `indexes` are mapping metadata that the provider can use when generating schema. They do not automatically guarantee that production migrations have created the constraint/index. If Flyway or Liquibase is the source of schema management, migrations must still declare the corresponding unique constraints and indexes.

### 3.2. @Table and @Column do two different things

`@Table` maps the entity to a table. `@Column` maps a persistent attribute to a column in that table.

```java
@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "product_code", nullable = false, unique = true, length = 30)
    private String code;

    @Column(name = "display_name", nullable = false, length = 160)
    private String name;

    @Column(name = "current_price", nullable = false, precision = 19, scale = 2)
    private BigDecimal currentPrice;
}
```

Here `products` is the table; `product_code`, `display_name`, and `current_price` are columns. The column name in `@Column` is also the database name, not the Java property name.

A single-column unique constraint can be declared with `@Column(unique = true)`. If you need a multi-column constraint or want to name the constraint, use `@Table(uniqueConstraints = ...)`. Avoid declaring the same constraint redundantly in multiple places without a reason.

## 4. Default names and naming strategy

If `@Table(name = ...)` is not declared, the provider needs to infer the table name from the mapping. Spring Boot/Hibernate can apply two layers of rules:

- **Implicit naming strategy:** determines the logical name when the mapping does not explicitly specify a name.
- **Physical naming strategy:** transforms the logical name into a physical name suited to database conventions.

For example, the Java name `purchaseOrder` can be converted to the physical name `purchase_order` according to the camelCase-to-snake_case naming strategy. The attribute name `createdAt` can become `created_at`.

Do not assume every project or provider uses the same rule. Naming strategies can be customized via Hibernate configuration. An entity that works in a local environment may fail in another environment if the schema and naming strategy are inconsistent.

To control mapping:

1. Check the application's implicit and physical naming strategy configuration.
2. Inspect the SQL generated by Hibernate or the database metadata.
3. Cross-check table/column names against migrations.
4. For tables with legacy names, abbreviated names, names containing keywords, or special rules, explicitly declare `@Table(name = ...)` and `@Column(name = ...)`.

Example Hibernate configuration that can set a custom physical naming strategy:

```yaml
spring:
  jpa:
    hibernate:
      naming:
        physical-strategy: org.hibernate.boot.model.naming.CamelCaseToUnderscoresNamingStrategy
```

This is a Hibernate class. Only configure it when you want to explicitly select that rule and have verified its impact across all mappings. Do not change the naming strategy in an existing system with a schema without checking migrations, because changing it may cause the provider to look for tables/columns under different names.

## 5. JPQL uses entity name, SQL uses table name

This is the difference most likely to cause errors when using `@Entity(name)` and `@Table(name)`.

Suppose the mapping is:

```java
@Entity(name = "OrderRecord")
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Column(name = "order_number")
    private String orderNumber;
}
```

JPQL references the entity name and Java property:

```java
@Query("""
    select o
    from OrderRecord o
    where o.orderNumber = :orderNumber
    """)
Optional<PurchaseOrder> findByOrderNumber(
    @Param("orderNumber") String orderNumber
);
```

In JPQL:

- `OrderRecord` is the entity name.
- `orderNumber` is the Java property.
- Do not use `purchase_orders` or `order_number` in the JPQL query above.

Native SQL references table and column names:

```java
@Query(
    value = """
        select *
        from purchase_orders
        where order_number = :orderNumber
        """,
    nativeQuery = true
)
Optional<PurchaseOrder> findNativeByOrderNumber(
    @Param("orderNumber") String orderNumber
);
```

In native SQL:

- `purchase_orders` is the table name.
- `order_number` is the column name.
- SQL syntax and functions depend on the database.

Spring Data derived queries are based on Java property names, not table names:

```java
Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
```

Spring Data parses the method name according to entity properties and builds a query suitable for the JPA provider. Therefore, changing `@Table(name = ...)` usually does not require changing derived methods, whereas changing a Java property name can affect method names and JPQL.

## 6. Where do entity relationships use table and column names?

When mapping relationships, annotations reference either Java properties or database names depending on the annotation:

- `mappedBy` takes the Java property name on the owning side.
- `@JoinColumn(name = ...)` takes the foreign key column name in the database.
- `@JoinTable(name = ...)` takes the join table name in the database.
- JPQL path expressions use Java property names.

Example order - customer relationship:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();
}

@Entity(name = "OrderRecord")
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;
}
```

Here:

- `mappedBy = "customer"` points to the `customer` field in PurchaseOrder.
- `@JoinColumn(name = "customer_id")` specifies the foreign key column in the `purchase_orders` table.
- `Customer` and `OrderRecord` are the entity names in JPQL if Customer's name is not changed.
- `customers` and `purchase_orders` are the physical table names.

JPQL to fetch orders by customer:

```java
select o
from OrderRecord o
where o.customer.id = :customerId
```

The corresponding SQL may access `purchase_orders.customer_id`, but JPQL does not need to know that column name. The provider translates the mapping into SQL.

## 7. Special table names, keywords, and case sensitivity

Avoid naming tables or columns after SQL keywords such as `order`, `user`, `group`, `select`. Some databases accept them when identifiers are quoted, but quoting rules and case sensitivity vary by database management system.

For example, if an existing table is named `order`, you may need to use dialect-specific quoting or corresponding mapping configuration. However, names like `purchase_orders` are generally easier to use and less database-dependent.

Quoted identifiers may become case-sensitive depending on the database. PostgreSQL, for instance, treats unquoted identifiers by folding them to lowercase; quoted identifiers preserve their exact casing. Therefore, do not arbitrarily mix `PurchaseOrders`, `purchase_orders`, and `"PurchaseOrders"`.

For legacy schemas:

1. Verify the exact table/column names from the database or migrations.
2. Verify the schema/catalog and the connected user's permissions.
3. Declare mapping names that match accurately.
4. Run tests initializing EntityManagerFactory and repository queries against the same type of database.
5. Do not rename tables in annotations without a migration or schema compatibility plan.

## 8. @Table is not an annotation for every class

Only entities map to a table via `@Table`. Several other mapping types have their own behavior:

| Annotation / class type | Has its own entity identity? | Has its own default table? |
|---|---:|---:|
| `@Entity` | Yes | Has mapped table |
| `@MappedSuperclass` | No | No |
| `@Embeddable` | No | No; fields are embedded into the owning entity |
| `@Embedded` | Does not create a new entity | Uses the columns of the owning entity's table |

Example of a mapped superclass containing shared fields:

```java
@MappedSuperclass
public abstract class AuditableEntity {

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at")
    private Instant updatedAt;
}

@Entity
@Table(name = "products")
public class Product extends AuditableEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
}
```

`AuditableEntity` has no table of its own. Its persistent attributes are included in the mapping of the child entity Product. `@Table(name = "products")` belongs to Product.

With inheritance between entities, the `@Inheritance` strategy determines how the hierarchy is stored: SINGLE_TABLE, JOINED, or TABLE_PER_CLASS. You cannot conclude that each subclass always has an independent table; you need to read the specific inheritance strategy and mapping.

## 9. Named queries and locations referencing entity name

Besides JPQL written in `@Query`, the entity name also appears in named queries:

```java
@Entity(name = "OrderRecord")
@Table(name = "purchase_orders")
@NamedQuery(
    name = "OrderRecord.findByStatus",
    query = """
        select o
        from OrderRecord o
        where o.status = :status
        """
)
public class PurchaseOrder {

    @Id
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;
}
```

The named query is registered under its own query name `OrderRecord.findByStatus`, while the JPQL part still uses the entity name `OrderRecord`. The named query name is a query identifier, not a table name.

When changing an entity name, review:

- JPQL in `@Query`.
- `@NamedQuery` and `@NamedQueries`.
- `@NamedEntityGraph` if it references related entity/attribute metadata.
- JPQL in code using EntityManager.
- Dynamic query configurations or libraries referencing the entity name.

Native queries and migrations need to review table/column names instead of the entity name.

## 10. Synchronizing mapping with schema migrations

In projects using Flyway or Liquibase, migrations are where the actual schema is described. JPA annotations describe how entities map onto that schema. The two sources must agree.

Example SQL migration:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uk_purchase_orders_order_number UNIQUE (order_number)
);

CREATE INDEX idx_purchase_orders_created_at
    ON purchase_orders (created_at);
```

The corresponding mapping must use the exact names:

```java
@Entity
@Table(
    name = "purchase_orders",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_purchase_orders_order_number",
        columnNames = "order_number"
    ),
    indexes = @Index(
        name = "idx_purchase_orders_created_at",
        columnList = "created_at"
    )
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_number", nullable = false, length = 40)
    private String orderNumber;

    @Column(name = "customer_id", nullable = false)
    private Long customerId;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;
}
```

This is a minimal mapping example to illustrate naming; if customer_id is a relationship to Customer, you should use a `@ManyToOne` association and `@JoinColumn` instead of a Long field in a real domain model. The migration also needs to create a foreign key to the customers table if data rules require it.

Do not rely on `@Table` or `@Column` automatically creating tables when production uses `ddl-auto=validate`. Validate only checks compatibility; it does not create or alter the schema. Changes must be put into migrations and deployed in order.

## 11. Verifying mapping at application startup

Incorrect table name or column name errors are typically detected when Hibernate initializes the EntityManagerFactory, when validating the schema, or when queries execute. You can verify using these steps:

1. Check whether the entity package is scanned by the right persistence unit.
2. Check entity name and table name separately.
3. Check whether the physical naming strategy transforms logical names.
4. Check schema/catalog and database user permissions.
5. Check that migrations created the correct tables, columns, constraints, and indexes.
6. Run repository tests to verify JPQL, derived queries, and native queries.

A simple repository test:

```java
@DataJpaTest
class PurchaseOrderRepositoryTest {

    @Autowired
    private PurchaseOrderRepository repository;

    @Test
    void findsOrderByOrderNumber() {
        PurchaseOrder order = new PurchaseOrder();
        order.setOrderNumber("PO-1001");
        repository.saveAndFlush(order);

        Optional<PurchaseOrder> result =
                repository.findByOrderNumber("PO-1001");

        assertThat(result).isPresent();
    }
}
```

This is an illustrative skeleton; real entities may require additional mandatory fields such as customer, status, or createdAt. Tests need to initialize complete valid data according to entity invariants. `saveAndFlush` pushes SQL down to the database within the test so many mapping errors surface right at the check point.

For native queries, you should test against the same type of database as production. H2 may differ in reserved words, identifier case, data types, functions, and dialect, so it is not sufficient to verify all native SQL.

## 12. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| @Entity(name) is the table name | It is the entity name used in JPA/JPQL |
| @Table(name) is the entity name | It is the database table name |
| JPQL uses table and column names | JPQL uses entity names and property names |
| Native SQL uses the entity name | Native SQL uses database table and column names |
| Repository generic must use the entity name | Generic repository uses the Java class, e.g. JpaRepository<PurchaseOrder, Long> |
| mappedBy takes the foreign key column name | mappedBy takes the field/property name on the owning side |
| @JoinColumn takes the Java field name | name is the database column name |
| @Table automatically creates production schema | Schema creation depends on DDL generation or migrations |
| Changing table name requires changing JPQL entity name | The two identifiers are independent; only update the corresponding references |
| Every class with @MappedSuperclass has a table | A mapped superclass has no table of its own |

## 13. Hands-on exercises

1. Create a `PurchaseOrder` entity with the default entity name and table name `purchase_orders`.
2. Write a JPQL query using the default entity name and the `orderNumber` property.
3. Change the entity name to `OrderRecord`; update the JPQL and named query while keeping the class name and table name unchanged.
4. Write a native query accessing `purchase_orders.order_number`; compare it with JPQL.
5. Declare `@Table(schema = "sales")` and check the generated SQL on a database that has the sales schema.
6. Create a unique constraint for `order_number` and an index for `created_at`; cross-check the annotations against a migration.
7. Use `@MappedSuperclass` for auditing fields and confirm that the child entity's table contains the inherited columns.
8. Configure `ddl-auto=validate`, intentionally change one column name in the mapping, and observe the startup or query error.
9. Try a derived query after changing the entity name; confirm the method is still based on the Java property.
10. Run an integration test against the same database type as the deployment environment.

**Core principle:** the class name is the Java type; the entity name is the JPA identifier used by JPQL; the table name is the physical identifier in the database. `@Entity` declares an entity, `@Table` maps the entity to a table, and `@Column` maps a property to a column. When writing queries, choose the right naming system: JPQL uses entity/property; native SQL uses table/column.
