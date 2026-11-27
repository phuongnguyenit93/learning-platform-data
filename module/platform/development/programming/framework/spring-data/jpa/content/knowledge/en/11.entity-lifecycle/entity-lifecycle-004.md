# Dirty Checking and When Changes Are Detected in Spring Data JPA

Dirty checking is the mechanism by which a JPA provider tracks managed entities and automatically synchronizes their changes to the database. When an application modifies a property of a managed entity inside a transaction, it normally does not need to call `repository.save()` again to persist the change. The provider detects that the state differs from the managed state and generates a SQL UPDATE on flush.

Understanding dirty checking requires distinguishing three moments: when the Java object is modified, when JPA detects/synchronizes the change, and when the transaction commits. These do not necessarily happen at the same time. This lesson explains the entity lifecycle, snapshots, flush, transactions, detached entities, bulk updates, and how to test whether changes have actually been written.

## 1. What is dirty checking?

Suppose you have a product entity:

~~~java
Product product = entityManager.find(Product.class, 10L);
product.setPrice(new BigDecimal("120.00"));
~~~

If `product` is in the managed state in the persistence context, the JPA provider tracks it. On flush, the provider compares the current state against the previously managed state (or uses bytecode-enhancement change tracking). If it detects that a property has changed, the provider generates the corresponding SQL UPDATE.

You can visualize this as:

1. The entity is loaded or persisted and becomes managed.
2. The provider stores the state information needed to track the entity.
3. The application modifies properties of the object.
4. At flush time, the provider detects the differences.
5. The provider issues SQL INSERT/UPDATE/DELETE to synchronize the persistence context with the database.
6. Transaction commit confirms the changes according to the database's transaction mechanism.

Dirty checking is a mechanism of the persistence context/JPA provider. Spring Data JPA provides repositories for accessing entities, while `@Transactional` typically defines transaction boundaries in a Spring application.

## 2. Entity lifecycle and conditions for dirty checking to work

JPA has key entity states:

| State | Meaning | Dirty checking? |
|---|---|---|
| New / Transient | New Java object, not yet managed by a persistence context | Not yet tracked as a managed entity |
| Managed / Persistent | Entity currently belonging to a persistence context | Yes |
| Detached | Entity that was once managed but has left the persistence context | No longer tracked |
| Removed | Entity marked for deletion in the persistence context | Provider synchronizes deletion on flush |

Example:

~~~java
Product product = new Product("Keyboard", new BigDecimal("80.00"));
// product is transient.

entityManager.persist(product);
// product becomes managed.

product.setPrice(new BigDecimal("75.00"));
// dirty checking can detect the change.

entityManager.flush();
// synchronizes pending INSERT/UPDATE to the database.

entityManager.detach(product);
// product becomes detached.

product.setPrice(new BigDecimal("70.00"));
// changes on a detached object are not automatically tracked.
~~~

Key condition: the entity must still be managed at the time of modification and when the provider synchronizes state. Merely holding a Java object with an ID does not mean that object is currently managed by JPA.

### 2.1. Persistence context

A persistence context is the set of entity instances managed by an EntityManager. Within a persistence context, JPA maintains identity: for the same entity type and primary key, looking up the entity again usually returns the same managed instance.

Example:

~~~java
Product first = entityManager.find(Product.class, 10L);
Product second = entityManager.find(Product.class, 10L);

assert first == second;
~~~

In the same persistence context, both variables typically reference the same managed instance. Modifying through either variable modifies the same object that the provider is tracking.

A persistence context is usually bound to a transaction in a Spring application when using a transaction-scoped EntityManager. However, persistence context and transaction are two distinct concepts; a persistence context can have its own lifecycle depending on how it is configured.

### 2.2. Snapshots and change-detection mechanisms

Hibernate's traditional implementation keeps a snapshot of the entity's state when the entity is loaded or becomes managed. On flush, the provider compares the current state against the snapshot to determine which properties changed.

Bytecode enhancement can allow the provider to track property changes directly (self-dirty tracking), reducing some snapshot comparison overhead. This is a provider implementation detail, not something where the application has to manually call a "mark dirty" method.

Whether the provider uses snapshots or enhancement, the rule at the application level remains: modify the managed entity within the persistence context, and let the provider flush at the appropriate time.

## 3. Spring Boot example: updating an entity without calling save again

The example below uses Java 17+, Spring Boot 3.x, Spring Data JPA, and H2. Minimal structure:

~~~text
dirty-checking-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/dirtychecking/
    │   ├── DirtyCheckingApplication.java
    │   ├── Product.java
    │   ├── ProductRepository.java
    │   └── ProductService.java
    └── resources/application.properties
~~~

### 3.1. Maven dependencies

Create `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>dirty-checking-demo</artifactId>
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
~~~

The Spring Boot parent manages compatible versions of Spring Data JPA, Hibernate, and H2. In real projects, choose a Spring Boot patch version matching your project's upgrade policy rather than setting individual library versions piecemeal.

### 3.2. Product entity

Create `Product.java`:

~~~java
package com.example.dirtychecking;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Product() {
    }

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }

    @Override
    public String toString() {
        return "Product{id=" + id
                + ", name='" + name + '\''
                + ", price=" + price.toPlainString()
                + "}";
    }
}
~~~

### 3.3. Repository

Create `ProductRepository.java`:

~~~java
package com.example.dirtychecking;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

### 3.4. Service updating via dirty checking

Create `ProductService.java`:

~~~java
package com.example.dirtychecking;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {

    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public Product changePrice(Long id, BigDecimal newPrice) {
        Product product = products.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Product not found: " + id));

        product.setPrice(newPrice);

        // product is managed.
        // No need to call products.save(product) again.
        return product;
    }

    @Transactional(readOnly = true)
    public Product getProduct(Long id) {
        return products.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Product not found: " + id));
    }
}
~~~

In `changePrice`:

- `findById` loads the entity into the transaction's persistence context.
- `product` is managed.
- `setPrice` changes the Java object's state.
- When the transaction flushes/commits, the provider detects the change and generates an UPDATE.
- There is no need to call `save` again for a managed entity.

If you do call `save` on a managed entity, that operation is usually unnecessary. Spring Data JPA's `save` uses `persist` when the entity is detected as new and `merge` when the entity is not new; merge can copy state into a managed instance and return the managed instance. For an entity already loaded and managed in the current transaction, simply modify its properties.

### 3.5. H2 configuration

Create `application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:dirtydb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.open-in-view=false
~~~

`create-drop` is suitable for demos because the schema is created when the application starts and dropped when the JVM exits. Do not use this setting for databases containing data that must be preserved. In production environments, manage schemas with Flyway/Liquibase or an equivalent migration workflow.

### 3.6. Running and output

Create `DirtyCheckingApplication.java`:

~~~java
package com.example.dirtychecking;

import java.math.BigDecimal;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DirtyCheckingApplication {

    public static void main(String[] args) {
        SpringApplication.run(DirtyCheckingApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            ProductRepository products,
            ProductService service) {
        return args -> {
            Product saved = products.save(
                    new Product("Keyboard", new BigDecimal("80.00"))
            );

            Long id = saved.getId();
            System.out.println("BEFORE: " + service.getProduct(id));

            service.changePrice(id, new BigDecimal("75.00"));

            System.out.println("AFTER:  " + service.getProduct(id));
        };
    }
}
~~~

Run:

~~~bash
mvn spring-boot:run
~~~

Lines printed by the program in a fresh H2 database:

~~~text
BEFORE: Product{id=1, name='Keyboard', price=80.00}
AFTER:  Product{id=1, name='Keyboard', price=75.00}
~~~

Hibernate's SQL log will show an INSERT when creating the product and an UPDATE when the transaction in `changePrice` ends. Startup logs, DDL statements, and other framework logs may appear interleaved; the stdout above is just the two lines printed by the runner.

## 4. When dirty checking detects and writes changes

A change on a managed entity does not necessarily issue SQL immediately when the setter runs. The provider usually records the change in memory and synchronizes it at flush time.

### 4.1. Flush before commit

In a transaction with the default `AUTO` flush mode, the provider must synchronize relevant changes before the transaction commits. Therefore, the service example above can finish without explicitly calling `flush()`; the Spring transaction manager completes the transaction and JPA flushes before commit according to provider/JPA rules.

Diagram:

~~~text
@Transactional starts
        |
        v
findById() -> managed entity
        |
        v
setPrice() -> in-memory change
        |
        v
service method returns
        |
        v
flush -> issues SQL UPDATE
        |
        v
commit transaction
~~~

If an exception causes the transaction to roll back, the database does not keep the changes of that transaction, even if the SQL UPDATE was already sent to the database during flush.

### 4.2. Calling EntityManager.flush() explicitly

You can request immediate synchronization:

~~~java
@Transactional
public void updatePriceAndFlush(Long id) {
    Product product = products.findById(id).orElseThrow();
    product.setPrice(new BigDecimal("70.00"));

    entityManager.flush();
}
~~~

Flush is useful when you want to detect constraint errors early or ensure prior changes have been sent to the database before a subsequent operation. It does not end the transaction and does not guarantee that data is committed.

If flush succeeds but the transaction later rolls back, the changes are still not committed.

### 4.3. AUTO and COMMIT flush modes

JPA has two main flush modes:

- `FlushModeType.AUTO`: the provider must ensure that changes capable of affecting a query's result are reflected when the query runs; the provider may flush before the query.
- `FlushModeType.COMMIT`: the provider may defer flushing until commit; query results within a transaction before commit do not necessarily reflect unflushed changes.

In Spring Data JPA/Hibernate, a query can trigger auto-flush when needed for accurate results. Do not assume that every repository query call definitely issues a SQL flush, or that no flush occurs before commit. This also depends on flush mode, query spaces, and the provider.

You can set the flush mode at the query or persistence context level in special cases, but do not change it casually because it can make query results hard to reason about.

### 4.4. persist and IDENTITY can issue INSERT early

Dirty checking primarily concerns changes to already managed entities. For new entities using `GenerationType.IDENTITY`, Hibernate usually needs to execute the INSERT early to obtain the database-generated primary key. Therefore, do not claim that all SQL only appears at commit.

INSERT timing also depends on the ID generation strategy, provider, transaction, and the database's deferral capabilities. Distinguishing persisting a new entity from an UPDATE caused by dirty checking helps you read SQL logs more accurately.

## 5. Dirty checking across different states

### 5.1. Managed entity

~~~java
@Transactional
public void rename(Long id) {
    Product product = products.findById(id).orElseThrow();
    product.setName("New keyboard");
}
~~~

The entity is loaded within the transaction and stays managed. On flush, the provider detects the change and writes an UPDATE. No need to call `save`.

### 5.2. Detached entity

An entity can become detached when:

- Calling `entityManager.detach(entity)`.
- Calling `entityManager.clear()`, detaching all managed entities.
- Closing the persistence context.
- Ending the transaction in a transaction-scoped persistence context model.

Modifying a detached object is not automatically tracked by dirty checking:

~~~java
Product product = repository.findById(id).orElseThrow();
entityManager.detach(product);

product.setPrice(new BigDecimal("60.00"));
// This change is not automatically written to the database.
~~~

To synchronize detached state, you can use `merge`:

~~~java
Product managed = entityManager.merge(product);
~~~

`merge` copies state from the source object into a managed instance and returns that managed instance. The source object remains detached. Always use the returned value of `merge`, and do not assume the input object has become managed.

Be careful when merging an object constructed from a request containing only a subset of fields. Uninitialized properties may hold null or default values and overwrite existing data. The safe approach is usually to load the managed entity, update only permitted fields, and let dirty checking handle the rest.

### 5.3. Removed entity

When calling `entityManager.remove(entity)` or a repository delete on an appropriate entity, the managed entity is marked removed. SQL DELETE is typically issued on flush. If the transaction rolls back, the deletion is not committed.

### 5.4. New entity

An unmanaged transient entity is not tracked by dirty checking like an entity already in the database. When calling `persist` or `repository.save` on a new entity, the provider registers the entity for INSERT. Subsequent changes on the managed entity may be written with the INSERT or an UPDATE depending on flush timing and ID strategy.

## 6. Operations that bypass normal dirty checking

### 6.1. JPQL bulk update/delete

Example:

~~~java
@Modifying
@Query("""
       update Product p
       set p.active = false
       where p.discontinued = true
       """)
int deactivateDiscontinuedProducts();
~~~

Bulk JPQL DML operates directly on the database rather than loading each entity and modifying its properties. Therefore:

- Dirty checking does not run for each affected entity.
- An open persistence context may still hold stale entities that do not reflect the newly updated values.
- Per-entity lifecycle callbacks and cascades are not executed as they would be for individual entity updates.
- You must consider version fields and optimistic locking; bulk DML does not automatically perform the full version mechanism like regular entity updates.

You can configure:

~~~java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
       update Product p
       set p.active = false
       where p.discontinued = true
       """)
int deactivateDiscontinuedProducts();
~~~

`flushAutomatically` requests flushing the persistence context before running the bulk query; `clearAutomatically` clears the persistence context after the query to avoid continuing to use stale entities. Clearing can detach other managed entities, so only enable it when the caller understands the consequences.

### 6.2. Native SQL and external updates

If a SQL script, stored procedure, or another application modifies a table, the current persistence context does not automatically know about that change. Managed entities can become stale.

You can:

- Flush pending changes before running external SQL.
- Clear or refresh entities after external data changes.
- End the transaction/persistence context before re-reading.
- Use an appropriate cache strategy if a second-level cache is present.

Do not call `refresh` arbitrarily on an entity that has unflushed changes, because refresh reloads state from the database and can overwrite in-memory changes.

## 7. Controlling UPDATE columns and optimizing dirty checking

### 7.1. UPDATE may include more columns than changed

By default, Hibernate usually generates an UPDATE with all mapped updatable columns, even when only one property changed. The provider still knows the entity is dirty, though the SQL may not contain strictly the changed column alone.

With Hibernate, the `@DynamicUpdate` annotation instructs it to generate SQL UPDATE based on only the columns that actually changed:

~~~java
import org.hibernate.annotations.DynamicUpdate;

@Entity
@DynamicUpdate
public class Product {
    // entity fields
}
~~~

This is a Hibernate-specific feature. It can reduce written data when an entity has many columns, but it increases the number of distinct SQL shapes and can affect statement cache efficiency. Enable it only after measuring your actual workload.

### 7.2. @Column(updatable = false)

A property marked with:

~~~java
@Column(updatable = false)
private String externalCode;
~~~

will not be included in SQL UPDATE statements generated by the JPA provider for that property after insert. This is mapping metadata, not a special dirty-checking mechanism. Use it for values that must not be updated after creation, such as an immutable reference code. If it ever needs to change, you must design an appropriate mapping and write workflow.

### 7.3. readOnly transactions

Spring allows:

~~~java
@Transactional(readOnly = true)
public ProductSummary getSummary(Long id) {
    // read data
}
~~~

`readOnly = true` is a hint/optimization for the transaction manager and provider. With Hibernate, Spring can set an appropriate flush mode to reduce dirty-checking overhead in certain configurations. However, do not treat it as an absolute security mechanism preventing all write statements.

Do not modify entities inside a method declared read-only and expect dirty checking to write changes like a normal write transaction. Use a write `@Transactional` for operations that modify data.

## 8. Transaction boundaries and Spring proxies

`@Transactional` is typically enforced via a Spring AOP proxy. Calls from another bean go through the proxy and can open a transaction as configured. However, self-invocation (one method in the same object directly calling another method annotated with `@Transactional`) does not go through the proxy in the default proxy mode.

Example:

~~~java
@Service
public class ProductService {

    public void process(Long id) {
        changePrice(id); // self-invocation
    }

    @Transactional
    public void changePrice(Long id) {
        // Do not assume this internal call automatically opens a transaction.
    }
}
~~~

Place transaction boundaries on service methods called through a bean proxy, or extract the logic into another bean. Without an appropriate transaction, a repository method may open its own transaction for that single call, but multiple business steps will no longer share a single transaction as intended.

Dirty checking only works properly within a properly managed persistence context and transaction. If a service reads an entity in one transaction and then modifies the object after the transaction closes, the change is not automatically persisted.

## 9. Testing dirty checking with flush and clear

A good test must force the provider to flush and then clear the persistence context before re-reading. If you only re-read the same managed entity, the test might just observe the in-memory value without proving the database was updated.

~~~java
package com.example.dirtychecking;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class DirtyCheckingTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void managedEntityChangesAreWrittenAtFlush() {
        Product product = new Product(
                "Keyboard",
                new BigDecimal("80.00")
        );

        entityManager.persist(product);
        entityManager.flush();

        Long id = product.getId();

        Product managed = entityManager.find(Product.class, id);
        managed.setPrice(new BigDecimal("75.00"));

        // Force the provider to synchronize changes to the database.
        entityManager.flush();

        // Clear the persistence context so the next read does not reuse the old instance.
        entityManager.clear();

        Product reloaded = entityManager.find(Product.class, id);

        assertThat(reloaded.getPrice())
                .isEqualByComparingTo("75.00");
    }
}
~~~

`flush` ensures the SQL UPDATE is sent to the database. `clear` detaches current entities from the persistence context. The subsequent `find` must retrieve state from the database (or cache/provider depending on configuration); the test confirms the value was saved within the current database transaction.

`@DataJpaTest` normally runs in a transaction and rolls back after the test. This keeps tests isolated without leaving test data around permanently.

## 10. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| Entity modified but database unchanged | Entity is detached or transaction closed | Load entity in a write transaction and modify while managed |
| Called save yet data is still lost | Transaction rolled back or error occurred at flush/commit | Check exceptions, transaction propagation, and logs |
| No UPDATE seen immediately after setter | SQL is only issued on flush | Observe at flush/commit or call flush in tests |
| Query reads stale data inside transaction | COMMIT flush mode or query did not trigger flush | Understand flush modes, flush explicitly when needed |
| Changes overwritten during merge | Merged a detached object missing fields | Load managed entity and update only permitted fields |
| Entity still holds old values after bulk update | Persistence context does not auto-sync | Clear/refresh appropriately after bulk DML |
| N+1 queries | Reading lazy relationships in a loop | EntityGraph, fetch join, projection, or batch fetching |
| SQL UPDATE includes many columns | Provider generates statements from default mapping | Measure and consider Hibernate @DynamicUpdate |
| Read-only does not persist as expected | Transaction is marked read-only | Use a write transaction for update operations |
| Self-invocation does not start a transaction | Internal call bypasses Spring proxy | Place transaction on a proxied method or separate bean |

## 11. Practical checklist

- [ ] The entity being modified is managed in the persistence context.
- [ ] The transaction spans both reading and updating.
- [ ] No redundant save calls after modifying a managed entity.
- [ ] Understand that flush and commit are two different points in time.
- [ ] Considered AUTO/COMMIT flush mode if queries depend on unflushed changes.
- [ ] Do not use readOnly transactions for write operations.
- [ ] Do not merge a DTO/partial entity that could overwrite omitted fields.
- [ ] After bulk DML, handled stale persistence context.
- [ ] Have tests that flush, clear, and re-read to verify persisted data.
- [ ] Observed SQL and checked for N+1 when relationships are loaded.

Dirty checking reduces boilerplate update code and keeps entity state consistent within a transaction. The most important practical rule is to load the entity inside a transaction, modify it while it remains managed, let the provider flush at the appropriate time, and test by re-reading after clearing the persistence context.