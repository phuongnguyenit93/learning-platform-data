# UNIQUE and FOREIGN KEY Constraints and Error Timing in Spring Data JPA

A Spring Data JPA test can call `repository.save(entity)` and **see no exception**, even when the data actually violates a **unique constraint** or **foreign key**. The primary reason is that JPA/Hibernate manages a **persistence context** and can defer SQL statements until **flush**. Conversely, some ID generation strategies (such as `IDENTITY`) must execute INSERT early; some database constraints (such as PostgreSQL's `DEFERRABLE INITIALLY DEFERRED`) can postpone checking until **commit**, even after SQL has run.

Therefore, testing data integrity properly requires answering four questions:

1. **Which constraints truly exist in the database schema?** Java annotations describe mappings, while production schemas may be managed by Flyway/Liquibase.
2. **What data violates them?** Duplicate unique keys, referencing a nonexistent parent, deleting a parent referenced by a child, and so on.
3. **At what moment do SQL execution and constraint checks happen?** `save/persist`, auto-flush, `saveAndFlush`, `EntityManager.flush`, or `commit`.
4. **At which layer is the exception observed?** JDBC, Hibernate, Jakarta Persistence, the Spring Data repository, or the transaction commit boundary.

This Knowledge article focuses on **Spring Data JPA**, covering UNIQUE/FK constraints, an error-timing diagram, writing `@DataJpaTest` with reliable assertions, and a runnable **Java 17 + Spring Boot 3.5 + H2** example. At the end, it contrasts testing on H2 with production PostgreSQL using deferred constraints.

## 1. Two Critical Constraint Types

### 1.1. UNIQUE — Preventing Duplicate Values on a Key

A business key such as a product `sku` must be unique across the table. The database can enforce this via:

```sql
ALTER TABLE products
    ADD CONSTRAINT uk_products_sku UNIQUE (sku);
```

The command above is a **SQL DDL example**; it runs only when table `products` already exists and has no conflicting constraint name. In a JPA entity:

```java
@Entity
@Table(
    name = "products",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_products_sku",
        columnNames = "sku"))
class Product {
    // @Id, sku, ...
}
```

This is a **mapping snippet**, not a complete Java file. `@Table(uniqueConstraints=...)` describes the constraint when a **schema generation tool** emits DDL; it does not mean Hibernate “checks for duplicates” in Java before every `save()`.

A unique key can span **multiple columns**—for example, duplicate external codes are forbidden within the same tenant, while two different tenants may share the same code:

```java
@Table(name = "orders",
       uniqueConstraints = @UniqueConstraint(
           name = "uk_orders_tenant_external",
           columnNames = {"tenant_id", "external_code"}))
```

`@Column(unique = true)` expresses **uniqueness on a single column**. For composite uniqueness, `@UniqueConstraint(columnNames = {...})` is clearer. In a real database, a constraint may be backed by an index; however, a **non-unique index** only speeds up queries and never prevents duplicate rows.

**Important note on NULL:** many databases permit multiple `NULL` values in a UNIQUE column because NULL does not compare equal like ordinary values; some DBs provide alternative NULL semantics. If a field **must be unique and present**, require both **`NOT NULL`** and **`UNIQUE`**, and check your target DB's actual schema behavior.

### 1.2. FOREIGN KEY — Child Must Reference an Existing Parent

Suppose a `Product` must belong to a `Category`:

```sql
ALTER TABLE products
    ADD CONSTRAINT fk_products_categories
    FOREIGN KEY (category_id)
    REFERENCES categories (id);
```

This is also a **DDL snippet**, requiring both tables and compatible data. An FK ensures `products.category_id`, when **non-null**, references a valid `categories.id`. If `category_id` cannot be null, **`NOT NULL`** is needed alongside the FK. Without a real database constraint, a `@ManyToOne` annotation in code **is not enough** for the database to protect referential integrity by itself.

Corresponding JPA mapping:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(
    name = "category_id",
    nullable = false,
    foreignKey = @ForeignKey(name = "fk_products_categories"))
private Category category;
```

- `@ManyToOne` models the object association from child to parent; `LAZY` controls how the association is loaded, **not FK checking**.
- `optional=false` expresses a required association in the JPA model; the ORM may throw when the field is null.
- `@JoinColumn(nullable=false)` signals NOT NULL column creation if Hibernate generates DDL; it does not replace checking an existing production schema.
- `@ForeignKey(name=...)` supplies metadata/name for the **FK constraint during DDL generation**, not an early JVM check.
- JPA `CascadeType.PERSIST`/`REMOVE` **differs** from database `ON DELETE CASCADE`. Never assume deleting a Category automatically deletes Products unless cascading was intentionally designed.

**Key test cases:** INSERTing a product with a nonexistent `category_id` must fail; deleting a category while dependent products remain must fail when the FK lacks cascade/set-null rules. Using direct SQL/JDBC to test physical FKs can be clearer than passing an unpersisted parent Java object — the latter is sometimes rejected by the ORM **before the database ever checks the FK**.

## 2. Differences Between Bean Validation, JPA Mapping, and Database Constraints

| Checking Layer | Examples | When Errors Can Surface | What It Proves |
|---|---|---|---|
| **Bean Validation** | `@NotNull`, `@Size`, `@Valid` | When validation is invoked or JPA lifecycle events trigger validation if provider/integration is present | DTO/entity satisfies validation rules; **does not prove DB UNIQUE/FK** |
| **JPA/Hibernate object graph** | `optional=false`, transient association | `persist`/`flush` depending on mapping, generator, and ORM | Object graph/association has mapping or state error |
| **Database NOT NULL/UNIQUE/FK** | `NOT NULL`, `uk_products_sku`, `fk_products_categories` | When DB executes SQL or at **commit** if constraint is deferred | **Real database** protects integrity |
| **Spring DAO exception translation** | `DataIntegrityViolationException` | When JDBC/repository exception passes through a translating layer | How the error is surfaced to application layers |

Keep three easily confused exceptions distinct:

- **`jakarta.validation.ConstraintViolationException`**: *Bean Validation* failure (e.g., `@NotBlank`) — does not necessarily involve SQL.
- **`org.hibernate.exception.ConstraintViolationException`**: Hibernate wrapping a constraint error reported by **SQL/database** (may include constraint name/SQLState depending on driver).
- **`org.springframework.dao.DataIntegrityViolationException`**: Spring's abstraction for data-access integrity failures, usually translated by repositories/`JdbcTemplate` from `SQLException`/Hibernate exceptions.

In Hibernate/JPA, errors may also be wrapped in `PersistenceException`, `TransactionSystemException`, or transaction-boundary exceptions. **Do not write a test expecting one exact exception class across every DB, timing, and call layer.** Pick the abstraction fitting the test layer and inspect the root cause/constraint name when the contract truly relies on it.

## 3. Error Timing: `persist`, `save`, `flush`, Queries, and Commit

Typical flow with `GenerationType.SEQUENCE`, an active transaction, and a database checking constraints **immediately when SQL executes**:

```text
new Product(...)                  transient object
      |
      v
repository.save(product)          persist/merge into persistence context
      |                             (may obtain sequence ID)
      |                             INSERT may still sit in queue
      v
entityManager.flush()             Hibernate emits INSERT/UPDATE/DELETE SQL
      |
      +-- DB UNIQUE/FK valid ---> SQL succeeds, transaction stays open
      |
      +-- DB UNIQUE/FK invalid -> SQL error, usually translated by Spring
      |
      v
transaction COMMIT                 if unflushed: may flush here
                                   with DEFERRABLE: may check constraint here
```

### `repository.save()` Is Not an Instant `INSERT` Command

Spring Data JPA `save` normally calls `EntityManager.persist` for new entities or `merge` for existing ones. Hibernate uses a **write-behind persistence context**, so **database** constraint checks typically do not occur until SQL statements are emitted.

With **`SEQUENCE`**, the ORM can obtain an ID from the sequence **without INSERTing the row yet**. Thus:

```java
Product p = repository.save(new Product("SKU-1", category));
assertNotNull(p.getId());
```

A non-null ID only means the entity has an identifier; it **does not prove the database accepted the row**, nor does it prove the transaction will commit successfully. This snippet relies on the `Product` class from the upcoming example and is not standalone.

### `IDENTITY` Typically INSERTs Early to Obtain the ID

With `GenerationType.IDENTITY`, the database generates the ID during the INSERT; Hibernate **usually must execute the INSERT immediately at persist/save** to learn the ID. Therefore UNIQUE/FK failures can erupt inside `save()`, **before calling `flush()`**. Never teach “UNIQUE violations only happen in saveAndFlush” as an invariable rule.

Some Hibernate configurations/versions have mechanisms to defer identity inserts in special cases. What should be emphasized is that **generation strategy and flush mode govern timing**, rather than guessing from API names.

### Flush Does Not Mean Commit

- `EntityManager.flush()` / `repository.flush()`: synchronizes pending changes into SQL; **does not commit**, so the transaction can still roll back.
- `repository.saveAndFlush(entity)`: saves then flushes; useful when you want **immediate** constraint errors to surface right at the test assertion, though it cannot force every error to appear there.
- Automatic flush (`FlushModeType.AUTO`) can happen before queries needing synchronized data or at commit. Exact timing depends on query/ORM/configuration.
- In DBs with **deferred** constraints, SQL can succeed at flush and **fail only at commit**, because the DB postpones validity checks until transaction end.

**Never catch an error and keep using the same persistence context/transaction as though nothing happened.** After a failed flush/JDBC command, the transaction may be marked rollback-only or left in a broken state; in PostgreSQL, a transaction hitting a SQL error normally requires rollback before any further SQL can run. Each negative test should end right after its assertion so Spring TestContext handles rollback; to verify commit-time exceptions, test **at the commit boundary** in a separate transaction.

## 4. Immediate vs. Deferrable Constraints: Only the DB Decides

By default, many DBs enforce UNIQUE/FK at **SQL statement time**. However, PostgreSQL supports **`DEFERRABLE`** for certain constraints such as UNIQUE and FOREIGN KEY.

PostgreSQL example (independent of JPA):

```sql
CREATE TABLE pg_categories (
    id bigint PRIMARY KEY
);

CREATE TABLE pg_products (
    id bigint PRIMARY KEY,
    sku text NOT NULL,
    category_id bigint NOT NULL,
    CONSTRAINT uq_pg_products_sku
        UNIQUE (sku) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT fk_pg_products_categories
        FOREIGN KEY (category_id) REFERENCES pg_categories(id)
        DEFERRABLE INITIALLY DEFERRED
);
```

With `INITIALLY DEFERRED`, PostgreSQL allows **temporary violations** inside a transaction while requiring data to be **valid at COMMIT**. Forward-reference example:

```sql
BEGIN;
INSERT INTO pg_products(id, sku, category_id)
    VALUES (1, 'SKU-1', 42);
INSERT INTO pg_categories(id) VALUES (42);
COMMIT;
```

The snippet above can **commit successfully** because by transaction end parent `42` exists, even though it did not exist when inserting the child. Without inserting the parent, the deferred FK makes **COMMIT fail**. Similarly, a deferred UNIQUE constraint can permit two rows with the same `sku` temporarily, then fail at commit if the conflict remains unresolved.

```sql
BEGIN;
INSERT INTO pg_products(id, sku, category_id) VALUES (2, 'DUP', 42);
INSERT INTO pg_products(id, sku, category_id) VALUES (3, 'DUP', 42);
-- COMMIT will report a UNIQUE error if both DUP rows remain.
ROLLBACK;
```

The second snippet intentionally **ROLLBACKs instead of executing a failing COMMIT** so no data is persisted; to verify failure timing, run a committing transaction in an **isolated test DB** and assert the exception at the commit boundary. In PostgreSQL:

```sql
-- Inside the transaction, switch deferred constraints to immediate checking:
SET CONSTRAINTS uq_pg_products_sku, fk_pg_products_categories IMMEDIATE;
```

`SET CONSTRAINTS` can trigger immediate validation of existing violations upon switching to IMMEDIATE. It is PostgreSQL syntax, **not JPQL or portable SQL**.

**Do not assume H2 shares PostgreSQL's deferrable semantics.** The runnable examples in section 6 use H2 to test immediate UNIQUE/FK constraints and flushing. To test **commit-time deferral**, use real PostgreSQL in tests (such as Testcontainers) with real DDL migrations; do not try to turn a commit-time error into a flush-time error just by calling `saveAndFlush`.

PostgreSQL note: `NOT DEFERRABLE` is the default; only constraints declared `DEFERRABLE` can be postponed via `INITIALLY DEFERRED`/`SET CONSTRAINTS`. `ON CONFLICT` also has restrictions against targeting a deferrable unique constraint as a conflict arbiter.

## 5. Runnable Example: Spring Boot 3.5, JPA, H2, and 6 Checks

The example uses two entities: `Category` (parent) and `Product` (child).

- `categories.code` is unique; `products.sku` has a UNIQUE constraint named `uk_products_sku`.
- `products.category_id` has a non-null FK to `categories.id`; **`ON DELETE CASCADE` is NOT enabled**.
- Both entities use **`SEQUENCE`** so we can illustrate `save` assigning IDs without INSERTing yet, while `flush` triggers SQL.
- `@DataJpaTest` uses an in-memory H2 database with a dedicated transaction per test and rollback afterward; no HTTP server starts.
- Spring Data repository tests check unique violations via `saveAndFlush`/`flush`. `JdbcTemplate` tests bypass the ORM to **prove physical FKs** are enforced by the database.

### 5.1. Directory Tree

```text
jpa-constraints/
├── pom.xml
└── src/
    ├── main/java/com/example/catalog/
    │   ├── CatalogApplication.java
    │   ├── Category.java
    │   ├── CategoryRepository.java
    │   ├── Product.java
    │   └── ProductRepository.java
    └── test/java/com/example/catalog/
        └── ConstraintTimingTest.java
```

### 5.2. `pom.xml`: Java 17 + JPA + H2 Test Database

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>jpa-constraints</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Here `spring-boot-starter-data-jpa` provides Hibernate/JPA and Spring Data; H2 suffices to run immediate-constraint tests in memory. `spring-boot-starter-test` provides JUnit Jupiter/AssertJ/Spring Test. Dependency versions are managed by the Boot BOM; in real projects, pick a Spring Boot patch aligned with your organization's maintenance policy.

### 5.3. Spring Boot Application Config

File **`src/main/java/com/example/catalog/CatalogApplication.java`**:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

`@DataJpaTest` in the corresponding test package locates `@SpringBootApplication` in the same root package; it still scopes beans to JPA without loading unnecessary controllers/services.

### 5.4. `Category` Entity as Parent

File **`src/main/java/com/example/catalog/Category.java`**:

```java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

@Entity
@Table(name = "categories")
public class Category {
    @Id
    @GeneratedValue(
            strategy = GenerationType.SEQUENCE,
            generator = "category_id_generator")
    @SequenceGenerator(
            name = "category_id_generator",
            sequenceName = "category_id_seq",
            allocationSize = 1)
    private Long id;

    @Column(name = "code", nullable = false, unique = true, length = 64)
    private String code;

    protected Category() {
        // Required by JPA.
    }

    public Category(String code) {
        this.code = code;
    }

    public Long getId() {
        return id;
    }

    public String getCode() {
        return code;
    }
}
```

Unique `Category.code` is an example of single-column uniqueness. `@SequenceGenerator` lets Hibernate allocate identifiers from a sequence without **forcing immediate INSERTs like IDENTITY** under normal conditions.

### 5.5. `Product` Entity as Child, with UNIQUE and FK

File **`src/main/java/com/example/catalog/Product.java`**:

```java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.ForeignKey;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "products",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_products_sku",
                columnNames = {"sku"}))
public class Product {
    @Id
    @GeneratedValue(
            strategy = GenerationType.SEQUENCE,
            generator = "product_id_generator")
    @SequenceGenerator(
            name = "product_id_generator",
            sequenceName = "product_id_seq",
            allocationSize = 1)
    private Long id;

    @Column(name = "sku", nullable = false, length = 64)
    private String sku;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
            name = "category_id",
            nullable = false,
            foreignKey = @ForeignKey(name = "fk_products_categories"))
    private Category category;

    protected Product() {
        // Required by JPA.
    }

    public Product(String sku, Category category) {
        this.sku = sku;
        this.category = category;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public Category getCategory() {
        return category;
    }
}
```

The entity uses **DDL-generation annotations** when Hibernate is permitted to create the schema in tests. `Product` requires a real `Category` parent; however, creating an unpersisted Java `Category` object may cause Hibernate to report an **unsaved transient association** rather than a foreign key `SQLException`. Therefore, the FK test below uses a **JDBC SQL insert** with a nonexistent ID to deliberately test the database constraint.

### 5.6. Spring Data JPA Repositories

File **`src/main/java/com/example/catalog/CategoryRepository.java`**:

```java
package com.example.catalog;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CategoryRepository extends JpaRepository<Category, Long> {
}
```

File **`src/main/java/com/example/catalog/ProductRepository.java`**:

```java
package com.example.catalog;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
    Optional<Product> findBySku(String sku);
}
```

Both repositories inherit `saveAndFlush`/`flush` from `JpaRepository`. `findBySku` uses Spring Data query derivation; the happy-path test flushes and clears the persistence context before reading to give strong evidence of database state.

### 5.7. Complete Tests: 6 Independent `@Test` Methods

File **`src/test/java/com/example/catalog/ConstraintTimingTest.java`**:

```java
package com.example.catalog;

import javax.sql.DataSource;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DataJpaTest(
        showSql = false,
        properties = "spring.jpa.hibernate.ddl-auto=create-drop")
class ConstraintTimingTest {

    @Autowired
    private CategoryRepository categories;

    @Autowired
    private ProductRepository products;

    @Autowired
    private DataSource dataSource;

    @PersistenceContext
    private EntityManager entityManager;

    private JdbcTemplate jdbc;

    @BeforeEach
    void createJdbcHelper() {
        jdbc = new JdbcTemplate(dataSource);
    }

    @Test
    void validSkuAndForeignKeyCanBePersistedAndLoaded() {
        Category category = categories.saveAndFlush(new Category("BOOKS"));
        products.saveAndFlush(new Product("SKU-001", category));

        entityManager.clear(); // Clear JPA cache to reload via repository.
        Product loaded = products.findBySku("SKU-001").orElseThrow();

        assertEquals("SKU-001", loaded.getSku());
        assertEquals("BOOKS", loaded.getCategory().getCode());
    }

    @Test
    void duplicateUniqueSkuFailsWhenSaveAndFlushExecutesSql() {
        Category category = categories.saveAndFlush(new Category("BOOKS"));
        products.saveAndFlush(new Product("SKU-DUP", category));

        DataIntegrityViolationException error = assertThrows(
                DataIntegrityViolationException.class,
                () -> products.saveAndFlush(
                        new Product("SKU-DUP", category)));

        assertNotNull(error.getMostSpecificCause());
        // End test; do not continue operating on the failed transaction.
    }

    @Test
    void saveCanAssignSequenceIdsBeforeUniqueCheckAtFlush() {
        Category category = categories.saveAndFlush(new Category("BOOKS"));

        Product first = products.save(new Product("SKU-LATER", category));
        Product second = products.save(new Product("SKU-LATER", category));

        assertNotNull(first.getId());
        assertNotNull(second.getId());

        assertThrows(
                DataIntegrityViolationException.class,
                products::flush);
        // With SEQUENCE and standard flush mode, INSERT waits until flush.
    }

    @Test
    void databaseForeignKeyRejectsOrphanInsert() {
        assertThrows(
                DataIntegrityViolationException.class,
                () -> jdbc.update(
                        "INSERT INTO products(id, sku, category_id) " +
                        "VALUES (?, ?, ?)",
                        900_001L, "SKU-ORPHAN", 999_999L));
        // Bypass ORM => physical FK violation in H2.
    }

    @Test
    void databaseForeignKeyBlocksDeletingReferencedParent() {
        Category category = categories.saveAndFlush(new Category("BOOKS"));
        products.saveAndFlush(new Product("SKU-CHILD", category));

        assertThrows(
                DataIntegrityViolationException.class,
                () -> jdbc.update(
                        "DELETE FROM categories WHERE id = ?",
                        category.getId()));
    }

    @Test
    void differentSkuValuesAreAllowedUnderSameParent() {
        Category category = categories.saveAndFlush(new Category("BOOKS"));
        products.saveAndFlush(new Product("SKU-A", category));
        products.saveAndFlush(new Product("SKU-B", category));

        entityManager.clear();

        assertTrue(products.findBySku("SKU-A").isPresent());
        assertTrue(products.findBySku("SKU-B").isPresent());
    }
}
```

**Why these tests are designed this way:**

- **Happy path** proves valid data is permitted by both UNIQUE and FK; `entityManager.clear()` prevents merely reading back the managed object from the persistence context.
- **Duplicate on `saveAndFlush`** confirms Spring Data repository surfaces `DataIntegrityViolationException` when SQL violates `uk_products_sku`. Never rely on exact H2 error message wording: it can change across DBs/vendors/drivers.
- **Two `save` calls then `flush`** uses `SEQUENCE` intentionally. Two entities having IDs **does not guarantee** two rows were inserted; flush exposes the collision. This test illustrates one valid path rather than claiming every `save` defers INSERT across all mappings.
- **Orphan insert via JDBC** proves the **database** itself has an FK to `categories`. If you only create `new Category` and assign it to a child, the ORM may throw a transient-object error before reaching the DB, leaving the test without proof of a physical FK.
- **Deleting parent** uses JDBC to verify the FK blocks DELETE while a Product exists, unlike JPA cascading if entity mappings were configured differently.
- **Two distinct SKUs** proves uniqueness does not block valid records under the same category.

Tests expecting failures **do not run further queries/repository operations after catching the exception** because the failed transaction may no longer be reliable. Each test has its own transaction and `@DataJpaTest` rolls back at the end. This prevents fixture leakage across test methods. Do not control test execution order or depend on state left by another test.

### 5.8. Running Tests and Expected Results

In the directory containing `pom.xml`, with **JDK 17+** and Maven:

```bash
mvn test
```

If using the Maven Wrapper:

```bash
./mvnw test
```

Or run individually:

```bash
mvn -Dtest=ConstraintTimingTest test
```

On Windows, use `mvnw.cmd` if the Wrapper exists, or `mvn` when Maven is installed. With the exact files/mappings/H2 in the example, expect **6 tests run, 0 failures, 0 errors**. Tests violating UNIQUE/FK **PASS because `assertThrows` catches the expected exception**, not because the database permits the violation. JUnit/Surefire may still log SQL errors to stderr while tests PASS; that is not necessarily a test failure.

**Example limitations:** tests run on **H2** with immediate constraints and Hibernate-generated DDL in the test context. They **do not prove** production migrations created the exact constraint names/definitions, nor compatibility with PostgreSQL deferrable constraints or transaction isolation. Testing against a production-like database is covered in section 7.

## 6. `@DataJpaTest` Default Transactional Behavior: “False-Green” Bugs

In Spring Boot 3.5, `@DataJpaTest` typically creates a JPA slice, uses an embedded test database if present, and makes each test **transactional + rolled back afterward**. This is great for repository mappings/queries, with two major consequences.

### 6.1. `save()` Without Flush: Test Does Not Prove DB Constraints

Unreliable test example:

```java
@Test
void doesNotActuallyCheckUniqueAtDatabase() {
    products.save(new Product("DUP", category));
    products.save(new Product("DUP", category));
    // Test ends and rolls back; INSERT may never have run!
}
```

This is **only an anti-pattern snippet** where `category` is an assumed fixture; it is not a standalone runnable method. In `@DataJpaTest`, without a flush or query triggering SQL, the test can **pass despite the violation** because rollback simply drops unsynchronized changes. Call `saveAndFlush`/`flush` to test immediate constraints, or **truly commit a transaction** to test deferrable ones.

### 6.2. Flush Can Happen Before a Query

```java
products.save(new Product("DUP", category));
products.save(new Product("DUP", category));
products.count(); // With AUTO, the query may trigger a flush before SELECT.
```

This is a cautionary snippet: `count()` **is not a uniqueness test**, yet Hibernate may flush pending inserts before the query, making the exception appear at `count` instead of `save`. Do not deduce where an exception originates simply by reading code line order.

### 6.3. Commit-Time Failures Must Be Tested at the Commit Boundary

When using PostgreSQL `DEFERRABLE INITIALLY DEFERRED`, a `@DataJpaTest` that rolls back at the end of the method **may never execute the commit step where the DB catches the violation**. To prove commit failure:

1. Stand up a test database on the target engine (typically **PostgreSQL Testcontainers**) and apply the Flyway/Liquibase migrations containing the deferrable constraint.
2. Execute operations inside a transaction that **actually attempts to commit** (e.g., an independent `TransactionTemplate` transaction, not nested inside an outer rolling-back test transaction).
3. Assert the exception at **`commit`/the `TransactionTemplate.execute` boundary**, not merely around `save` or `flush`.
4. Safely roll back/clean up test fixtures and ensure no shared database is corrupted.

Conceptual example **not runnable on H2**:

```java
assertThrows(RuntimeException.class, () ->
    transactionTemplate.executeWithoutResult(status -> {
        // save two duplicate-key rows checked by a DEFERRABLE constraint at commit
        repository.save(new Product("DUP", existingCategory));
        repository.save(new Product("DUP", existingCategory));
        repository.flush(); // May still not fail due to deferred constraint.
    })
);
```

This snippet intentionally **does not run standalone**: `transactionTemplate`, `repository`, `existingCategory`, and the deferrable PostgreSQL schema must be set up in an integration test; avoid catching broad `RuntimeException` in production tests without inspecting the specific cause/constraint. In real tests, catch the boundary-appropriate exception and verify the expected constraint's root cause so you do not confuse it with connection or mapping errors.

## 7. Production Schema: Hibernate DDL Differs from Flyway/Liquibase Migrations

In `@DataJpaTest(properties="spring.jpa.hibernate.ddl-auto=create-drop")`, Hibernate **creates the test schema** from annotations. Production normally uses versioned DDL migrations:

```sql
CREATE TABLE categories (
    id BIGINT PRIMARY KEY,
    code VARCHAR(64) NOT NULL,
    CONSTRAINT uk_categories_code UNIQUE (code)
);

CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(64) NOT NULL,
    category_id BIGINT NOT NULL,
    CONSTRAINT uk_products_sku UNIQUE (sku),
    CONSTRAINT fk_products_categories
        FOREIGN KEY (category_id) REFERENCES categories (id)
);
```

This is **illustrative DDL**, not a complete migration script ready for any DBMS (lacking sequences, identity/default IDs, required indexes, and versioning). When the production schema is built by Flyway/Liquibase, `@Column(unique=true)` or `@ForeignKey` **does not run migrations** on an existing DB. Hence tests on a Hibernate-generated H2 schema can pass while production lacks the constraint and admits invalid data.

Recommended production-like verification workflow:

1. Use Testcontainers or an isolated test database **matching the production engine/major version**.
2. Execute the **same Flyway/Liquibase migration scripts** used at deploy time, rather than generating a different schema solely from annotations.
3. Use `spring.jpa.hibernate.ddl-auto=validate` (or consistent config) to catch certain mapping mismatches; **do not rely solely on `validate` to prove every UNIQUE/FK exists**, as schema validation has limits.
4. Run **direct JDBC** tests: duplicate SKU INSERT must fail; orphan FK INSERT must fail; deleting a referenced parent must fail per policy (or cascade/set-null if designed).
5. Verify **exact failure timing**: immediate constraints at SQL statement execution, deferred constraints at commit.
6. For multi-tenant data, test **composite uniqueness** allowing the same external code in different tenants while failing within the same tenant.
7. Verify service/API exception mapping (e.g., HTTP 409 for duplicate SKU) in **higher-level tests**, without making the JPA slice responsible for HTTP statuses.

If the database uses deferrable constraints or vendor-specific SQL (partial unique indexes, case-insensitive uniqueness, PostgreSQL `NULLS NOT DISTINCT`), H2 is insufficient proof. You need the **real database** with migrations and boundary test data.

## 8. Commit-Time Errors Impact Service and HTTP API Design

A `@Transactional` service method can return from its body before the **Spring transaction interceptor attempts to commit**. Thus code like:

```java
@Transactional
public Product create(Product product) {
    try {
        return repository.save(product);
    } catch (DataIntegrityViolationException ex) {
        // Not guaranteed to catch UNIQUE error occurring at flush/commit afterward.
        throw ex;
    }
}
```

is an illustrative service snippet, not standalone. If SQL has not run when `save` returns, the `try/catch` inside the method will miss errors thrown later at commit.

Better design practices:

- Treat database UNIQUE/FK constraints as the **final source of truth**, rather than replacing them with `existsBySku` before INSERT (race condition between concurrent requests).
- If the app must return a specific domain error for duplicates, understand the **transaction boundary**, where exception translation happens, and where mapping to a conflict response belongs—for example, at an **outer service/controller advice boundary** after the transactional method finishes.
- You can call `saveAndFlush` intentionally inside a transaction to catch **immediate** uniqueness violations early, though **you cannot force a deferred commit-time constraint to fail before COMMIT** via flush alone.
- After a violation, **roll back the transaction**; never keep reusing the same `EntityManager` hoping to patch the object and commit.
- For FKs, distinguish “parent lost” due to concurrent deletion, invalid reference, and transient association bugs; return domain/HTTP errors per contract without leaking raw SQL/messages.

### Race Condition: `existsBySku` Helps UX, Not Uniqueness Enforcement

Two concurrent requests A and B can both see `existsBySku("SKU-1") == false` and both attempt INSERT. Without a schema **UNIQUE** constraint, both can commit and duplicate the data. With UNIQUE, the database permits only one valid outcome per isolation/constraint; the losing request must handle the integrity failure. Proving this requires a **concurrency integration test with independent transactions** on the target DB — unit tests mocking `existsBySku` cannot prove database atomicity.

### Do Not Map Every `DataIntegrityViolationException` to HTTP 409

`DataIntegrityViolationException` can cover **unique, FK, NOT NULL**, and other errors. If an API specifies `409 Conflict` for duplicate business keys, identify the **exact constraint/code** reliably. An FK failure caused by a mapping bug should not be masked as “SKU already exists” merely because it shares Spring's exception class. Database messages and constraint names vary by driver/vendor, so avoid brittle string parsing when structured metadata or domain checks are available.

## 9. Layer-by-Layer Error Comparison Table

| Scenario | Where Can the Error Occur? | How to Test It? |
|---|---|---|
| `Product` with duplicate `sku`, SEQUENCE | When pending INSERT flushes, query auto-flushes, or at commit | `@DataJpaTest`, create valid row then `saveAndFlush` duplicate row |
| Duplicate `sku` using IDENTITY | INSERT may happen immediately on `save/persist` | Assert around the operation actually executing SQL, without pinning an arbitrary line |
| Duplicate `sku` in PostgreSQL deferred UNIQUE | May fail only at **COMMIT** | Test on real PostgreSQL with an independent committing transaction |
| `Product` with `category=null` and `optional=false` | Hibernate may check nullability before SQL; DB also has NOT NULL | Test mapping and DB NOT NULL separately; do not treat ORM exception as SQL FK |
| `Product` pointing to unsaved `new Category` | Hibernate may report transient object error before DB | To test physical FK, use JDBC orphan ID or controlled managed reference |
| `Product` with nonexistent `category_id` | SQL INSERT/UPDATE rejected by FK (immediate) | Direct JDBC test on DB with real FK |
| Deleting `Category` that still has Products | SQL DELETE of parent rejected by FK unless cascade/set-null applies | Direct JDBC delete or repository delete + flush test |
| Valid ORM mapping but migration lacks FK | No integrity check in production DB | Test migrations on production-like DB and attempt invalid SQL |
| `@Transactional` test rolls back without flushing | Constraint may never have been checked | Flush immediate constraints or run real commit tests when needed |
| Service catches only around `save` | Error escapes method at transaction commit | Test transactional boundary and API error translation |

**General lesson:** pinpoint **who checks, when it checks, and where the exception emerges**. The exact same invalid data can raise different exceptions depending on execution path, mapping, and database.

## 10. Practical Debugging: Inspecting SQL, Root Causes, and Transaction State

When a test fails unexpectedly, recommended inspection order:

1. **Schema:** does the real constraint exist? Exact name and columns? Is NOT NULL present? Which table/column does the FK reference? Any `ON DELETE` rule?
2. **Data fixture:** was the parent persisted, does the `id` exist in the DB, is this check running in another transaction?
3. **Timing:** did code only `save` or also `flush`? Is `IDENTITY` causing an immediate INSERT? Did a query auto-flush? Is `DEFERRABLE` involved?
4. **Exception stack:** Spring `DataIntegrityViolationException`, Hibernate SQL exception, or Bean Validation exception? Are SQLState/vendor code/constraint name available?
5. **Transaction state:** did the SQL error mark it rollback-only? Did you roll back before running further SQL?
6. **Environment:** H2 or PostgreSQL? Schema created by Hibernate or real migrations? Is the test using an embedded DB instead of the intended URL?

With Spring Boot 3.5, enable SQL logging **in a test profile when debugging**, for example:

```properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

This is a **debug-only** properties snippet, not a production setting. SQL logs reveal when statements execute, yet **do not prove commit succeeded**; inspect DB transaction/constraint logs when testing deferred checks. Avoid writing credentials or sensitive data into bind logs in uncontrolled environments.

## 11. Checklist for Testing UNIQUE/FK and Timing

- [ ] Distinguished **database constraints**, JPA association metadata, and Bean Validation.
- [ ] UNIQUE/FK constraints **actually exist in the test schema**, not just as annotations.
- [ ] If a key cannot be null, both UNIQUE and NOT NULL exist per DB contract.
- [ ] For composite uniqueness, tested both duplicate within the same scope and valid reuse across scopes.
- [ ] Know whether the ID generator is SEQUENCE, IDENTITY, or another strategy, and its effect on INSERT timing.
- [ ] Never treat `save()` as proof the database accepted the data.
- [ ] Immediate-constraint tests call `saveAndFlush`/`flush` or execute an explicit JDBC statement.
- [ ] When testing deferred constraints, **attempt COMMIT** on a DB supporting deferral instead of flushing and rolling back.
- [ ] `@DataJpaTest` tests do not continue issuing queries in a transaction after an expected SQL exception.
- [ ] Catch `DataIntegrityViolationException` at the Spring data-access boundary and inspect root causes when needed; do not confuse with Jakarta Validation exceptions.
- [ ] Tested orphan FKs using real SQL, not only unpersisted object graphs.
- [ ] Tested deleting a referenced parent and verified the intended `ON DELETE` policy.
- [ ] Verified production-matching database engine/migrations when risks are DDL/vendor-specific.
- [ ] Never rely on `existsBySku` to replace DB UNIQUE against race conditions.
- [ ] Never lump every integrity failure into a single wrong business error.
- [ ] If the API requires HTTP 409/400, added web/integration tests for exception mapping outside the JPA slice.
- [ ] Successfully ran the test suite and understood why a test **PASSES even though an operation inside throws an exception**.

**Conclusion:** **UNIQUE and FOREIGN KEY are database constraints that must physically exist in DDL.** `save` only updates persistence state; `flush` synchronizes SQL without committing; `commit` is the final boundary where the DB enforces integrity, especially for **DEFERRABLE** constraints. Writing reliable tests requires crafting violating data, forcing SQL or commit **at the appropriate point**, catching exceptions at the right layer, and ensuring the test database actually supports what you aim to prove.

### Official Documentation

- [Spring Boot 3.5 — `@DataJpaTest` Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html)
- [Hibernate ORM User Guide — Flushing](https://docs.hibernate.org/stable/orm/userguide/html_single/)
- [Spring Data JPA — Persisting Entities / `save`](https://docs.spring.io/spring-data/jpa/reference/jpa/entity-persistence.html)
- [Jakarta Persistence — `@UniqueConstraint`, `@JoinColumn`, `@ForeignKey`](https://jakarta.ee/specifications/persistence/)
- [PostgreSQL — CREATE TABLE, `DEFERRABLE` and `INITIALLY DEFERRED`](https://www.postgresql.org/docs/current/sql-createtable.html)
- [Spring Framework — Data Access Exception Hierarchy](https://docs.spring.io/spring-framework/reference/data-access/dao.html)