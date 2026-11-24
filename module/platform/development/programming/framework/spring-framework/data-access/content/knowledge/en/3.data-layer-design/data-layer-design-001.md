# Distinguishing DAO, Repository, Service, and Domain Objects in Spring Framework

> **Learning context:** This lesson belongs to the **Data Layer Design** section of Spring Framework. The four terms DAO, Repository, Service, and domain object often appear together, yet they describe **different responsibilities**. They are not automatically four mandatory layers for every application. The goal is to determine where to place data queries, business rules, transaction orchestration, and the business model; and to know when they can be merged or separated with good reason.

## 1. A Concrete Scenario to Distinguish Roles

A store has two products: 5 copies of a Java book and 3 copies of a Spring book in stock. The request `checkout(1, 2, 2, 1)` means ordering 2 Java books and 1 Spring book in a single checkout. The system needs to:

1. Verify that both products exist and that the requested quantities are positive and do not exceed available stock.
2. Decrement the corresponding stock.
3. If one product does not have enough stock, **the entire request fails**, without keeping the stock deduction from the earlier product.
4. Under concurrent requests, avoid erroneously overwriting stock state that someone else just changed.

Four components answer different questions:

- **Domain object `Product`:** "Is a product allowed to reserve an additional `quantity`? If so, what is the next valid stock state?"
- **DAO `JdbcProductDao`:** "How do we read the `id, sku, available_stock, version` columns from the `product` table and send the UPDATE statement?"
- **Repository `ProductRepository`:** "Through what interface does the business layer find and save a `Product`, without needing to know SQL or database tables?"
- **Application Service `CheckoutService`:** "In what sequence should the multi-product ordering use case execute, within what transaction, and how should business errors be returned?"

**Practical rule of thumb:** the domain object holds business state rules; the DAO holds low-level storage operations; the Repository is the gateway for retrieving/saving domain objects; the Service orchestrates a complete business action.

## 2. Comparing Responsibilities in One Table

| Criterion | Domain object | DAO (Data Access Object) | Repository | Service (Application Service) |
| --- | --- | --- | --- | --- |
| Primary focus | State, meaning, business rules, and behavior | Technical data read/write, SQL, row mapping | Provide a collection of objects/aggregates in domain language | Use case orchestration, operation policies, transactions |
| Typical input | Quantities, values, other states | SQL keys, query conditions, parameters | Domain IDs, domain-meaningful criteria, domain objects | Use case command/request |
| Typical output | Valid state/behavior or rule violation error | Row, persistence record, updated row count | Domain object/aggregate or `Optional` | Use case result, receipt/DTO, or error |
| Knows JDBC/JPA? | Preferably does not need to know | Usually knows JDBC/SQL or storage API well | **Contract** does not need to know; **adapter implementation** knows | Does not need to know query details |
| Knows transactions? | Does not start transactions itself | Participates in transactions managed by upper layer | Participates in transactions, usually does not decide use case scope | Usually defines the boundary for the whole use case |
| Example | `product.reserve(2)` | `UPDATE product SET ...` | `products.findById(id)`, `products.save(product)` | `checkout(first, second)` |

**This distinction is by responsibility, not by class name.** A class named `ProductRepository` that only returns `ResultSet` and contains SQL may actually be doing DAO work. A `ProductService` that merely forwards each CRUD call without any orchestration or policy may be a redundant layer. Conversely, a class annotated with `@Repository` in Spring can directly implement both DAO and Repository when the problem is simple; it is not mandatory to create an extra adapter just to have all four classes.

## 3. Call Flow and Dependency Relationships

A design with clear boundaries typically follows this flow:

~~~mermaid
flowchart TD
    Caller["Controller / CLI / message consumer"] --> App["CheckoutService\nuse case + transaction"]
    App --> Domain["Product\ncheck rules, produce valid state"]
    App --> Port["ProductRepository\ndomain contract"]
    Port -. "implemented by" .-> Adapter["JdbcProductRepository\ndomain <-> row mapping"]
    Adapter --> DAO["JdbcProductDao\nSQL + JdbcTemplate"]
    DAO --> DB[("Database / product table")]
~~~

The arrows show how code **calls or depends**. `Product` **does not call down to the database**. The Application Service operates on `Product` and the `Repository` interface. The adapter maps between `Product` and the actual data; the DAO handles SQL. SQL goes through JDBC/DataSource to the DBMS, but that is the data access mechanism beneath the DAO rather than an additional business role.

The module structure can be organized into:

~~~text
com.example.boundaries
├── domain
│   ├── Product.java                 # domain object
│   └── ProductRepository.java       # domain-oriented access port
├── service
│   └── CheckoutService.java         # use case + transaction
├── data
│   ├── JdbcProductDao.java          # SQL, ProductRow
│   └── JdbcProductRepository.java   # adapter + mapping
└── DaoRepositoryLessonApplication.java
~~~

In domain-oriented layering, `domain` does not import `data`; `data` can import `domain` to implement the contract. Spring injects the `ProductRepository` implementation into the Service at runtime. This is **dependency inversion at the contract level**, as opposed to having the service depend directly on a concrete SQL class.

The repository interface can also be placed in the `application` package instead of `domain`, depending on scale and architectural style. What matters is that **the contract reflects business needs** and does not force upper layers to know storage details.

## 4. Domain Object: Modeling Meaning and Invariants

A **domain object** is a Java object used to represent a business concept. It can be:

- **Domain entity:** has a stable identity, such as a `Product` with an ID; its state may change over time. In DDD, entity equality usually cares about identity, not just all fields.
- **Value object:** defined by its values, such as `Money(amount, currency)` or `Address`; usually immutable and compared by value.
- **Aggregate:** a cluster of objects with an aggregate root that enforces cross-cluster invariants. Repositories usually operate at the aggregate boundary rather than creating a repository for every table.
- **Domain service:** describes a domain rule that does not naturally belong to a single entity/value object, such as a pricing policy based on multiple factors; distinct from an Application Service that orchestrates use cases.

Example of the `Product.reserve(quantity)` rule:

~~~java
public Product reserve(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("Quantity must be positive");
    }
    if (quantity > availableStock) {
        throw new IllegalStateException("Insufficient stock: " + sku);
    }
    return new Product(id, sku, availableStock - quantity, version);
}
~~~

This is domain behavior: a product does not allow a reservation quantity of 0, negative, or greater than available stock. It **does not need to know** whether the data lives in PostgreSQL, H2, a file, or memory. The example uses an immutable `record Product` to make state transitions easy to track; this record is a **domain state snapshot**. If a system uses a full DDD entity model with identity-based equality, consider a class with appropriate identity semantics rather than defaulting to Java record equality (which compares all components) as entity equality.

### Domain Invariants and Database Constraints Complement Each Other

Checking `availableStock >= 0` when creating a `Product` helps prevent creating meaningless Java states; `CHECK (available_stock >= 0)` in the schema helps protect data when there are multiple write paths. The two levels of checks serve different purposes: the domain expresses the business reason; the database preserves data structure and constraints, even when another process writes directly to the table.

### A Domain Object Is Not Synonymous with a JPA Entity

A class annotated with `@Entity` belongs to JPA's persistence model. It **can** simultaneously be a domain entity if its structure and behavior fit; however, in complex systems, a JPA entity containing technical mappings, lazy proxies, or table relationships can be separated from the domain model. Not every table must have a domain entity, and not every domain object must have a table.

## 5. DAO: Technical Details of Data Access

A DAO typically knows "how to talk to the data store":

- Write SQL/JPQL or call a driver/client; bind parameters instead of concatenating input strings.
- Map `ResultSet` to `ProductRow` or an appropriate persistence type.
- Return the number of updated rows, keys, queried data, or data access exceptions.
- Use appropriate resource management APIs (with Spring JDBC, `JdbcTemplate` handles Statement/ResultSet lifecycle and Connection coordination).

Example DAO signatures in the hands-on example:

~~~java
Optional<ProductRow> findById(long id);
int updateStock(long id, int newStock, long expectedVersion);
~~~

The signatures speak the storage language: a row from the product table and the number of SQL rows actually updated. The DAO does not need to decide "is the cart valid?", "must two products be processed as a single unit?", or "what HTTP status code should a failed transaction return?". Those concerns belong to the domain, Service, or presentation/communication layer.

**DAO is a pattern**, not a dedicated Spring annotation. Spring's `@Repository` annotation is a stereotype that registers a persistence-layer bean and can enable persistence exception translation; there is no rule that every DAO must be named `*Repository` or that every class annotated with `@Repository` fulfills the full DDD Repository pattern.

In a small JDBC project, a `JdbcProductRepository` class directly containing `JdbcTemplate` can make sense. Splitting into `JdbcProductDao` and `JdbcProductRepository` should provide real value (separating SQL/row mapping from domain mapping, sharing adapters, supporting backend migration), rather than merely increasing the file count.

## 6. Repository: An Interface in Domain Language

A Repository gives the impression of operating on a **collection of domain objects**. For example:

~~~java
public interface ProductRepository {
    Optional<Product> findById(long id);
    void save(Product product);
}
~~~

The Service knows `Product` and `ProductRepository`; it does not need to know the `product` table, the `SELECT` statement, `JdbcTemplate`, or how to map a SQL row. The adapter converts from `ProductRow` to `Product` on read and from `Product` to SQL parameters on write.

The word "Repository" has **two common usages**:

1. **Repository pattern in domain/DDD design:** a contract reflecting how to retrieve/save aggregates using domain concepts; the interface may be owned by the domain or application layer, while an adapter in infrastructure implements it.
2. **Spring Data repository:** an interface such as `JpaRepository<ProductEntity, Long>` that uses Spring Data's implementation generation mechanism. It reduces persistence boilerplate but remains entity-based infrastructure tied to framework conventions; it does not automatically turn every CRUD query into a good domain model.

For instance, a method `findActiveOrdersForCustomer(customerId)` clearly expresses a domain need. There is no need to proliferate endless `findByField1AndField2And...` methods just because Spring Data supports derived query methods. Conversely, very simple CRUD may only need a Spring Data repository directly inside a Service, provided the architecture does not require a separate persistence port.

### Should Repositories Be Per Table or Per Aggregate?

For pure CRUD applications, a repository per entity/table is a common choice. In DDD design, repositories usually follow the **aggregate root**. For example, `Order` contains `OrderLine`; if modifying an `OrderLine` could break an order invariant, updates should go through `Order`, and `OrderRepository` helps enforce those rules. That does not mean every system must apply full DDD; choose based on rule complexity.

## 7. Service: Orchestrating Use Cases and Preserving Atomicity

An Application Service describes *the action the system performs* rather than SQL details:

~~~text
checkout(...)
    -> validate overall request
    -> load Product A via ProductRepository
    -> ask Product A to reserve(qtyA)
    -> save Product A
    -> load Product B via ProductRepository
    -> ask Product B to reserve(qtyB)
    -> save Product B
    -> complete or roll back everything
~~~

Appropriate responsibilities for a Service include:

- Orchestrating multiple domain objects/repositories; deciding the step order of a use case.
- Defining an appropriate transaction boundary, such as `@Transactional` for checkout.
- Enforcing application-level authorization (if needed) and command-handling policies, idempotency, and other integration orchestration.
- Converting domain state into use case output (DTO/receipt) without exposing the persistence model to the API.

**Do not cram all rules into the Service.** A Service packed with hundreds of `if` statements directly expressing every `Product` state while `Product` holds only getters/setters is often a sign of an **anemic domain model** in a problem with complex rules. When a rule pertains only to the state of one object, prefer placing it on that object; when a use case coordinates multiple objects and resources, the Service orchestrates.

### Application Service vs. Domain Service

- **Application Service:** "Load data, invoke domain rules, save results, publish post-transaction events" — coordinates workflow and transactions.
- **Domain Service:** "Calculate discount policy based on order state and customer" — a business rule that does not belong to a single entity alone.

A domain service does not necessarily need `@Service`; it can be a plain Java class. In Spring, `@Service` is a bean registration stereotype and **does not automatically distinguish** an application service from a domain service.

### Transactions Usually Wrap the Use Case

In Spring's common proxy mode, `@Transactional` on a public Service method is invoked **through the Spring proxy**. Repository/JDBC operations sharing the same transaction-aware `DataSource` participate in the active transaction. Errors matching the rollback rule (by default, unchecked exceptions) trigger a rollback. If transactions were marked only on individual DAO methods, saving two products could commit independently and fail to preserve checkout atomicity.

A private helper called **inside** a public transactional method still runs within the already-opened transaction. However, placing `@Transactional` **only** on a private helper or relying on self-invocation via `this.method()` does not trigger a new proxy call; boundaries must be designed clearly.

## 8. Distinguishing Domain Object, Persistence Model, DTO, and Command

Types commonly confused with the four main components:

| Type | Purpose | Example | Should it be exposed via API? |
| --- | --- | --- | --- |
| Domain object | Business-meaningful rules and state | `Product`, `Money`, `Order` | Depends on architecture, though usually there is a conversion layer |
| Persistence model/row | Describes how data is stored | `ProductRow(id, sku, stock, version)` | Usually not |
| JPA entity | Object managed/mapped by JPA to a table | `@Entity ProductEntity` | Avoid exposing directly when there are lazy fields, sensitive data, or schema coupling |
| Command/request DTO | Expresses use case input | `CheckoutCommand(productIds, quantities)` | Can be received/constructed from an HTTP request |
| Response DTO | Shape of output data | `CheckoutReceipt(orderId, lines)` | Usually yes |

**Mapping is not business logic:** `ProductRow → Product` only converts the storage structure into the domain representation; validating a valid order quantity belongs to domain behavior. If `Product` and the table match in a small problem, sharing a model is acceptable when coupling is acceptable. Separating models is a **choice about complexity and evolvability**, not a mandatory ceremony.

## 9. Runnable Example: Java 21, Spring Boot, Spring JDBC, and H2

The example intentionally keeps **both DAO and Repository adapter** to make the boundary visible. In a real project, the two infrastructure layers can be merged if they only forward calls uselessly. The console program boots the Spring context, retrieves beans via DI, operates on two products, and prints before/after state. No HTTP server is needed.

### 9.1. File Layout and Dependencies

~~~text
build.gradle
src/main/resources/application.properties
src/main/resources/schema.sql
src/main/resources/data.sql
src/main/java/com/example/boundaries/DaoRepositoryLessonApplication.java
src/main/java/com/example/boundaries/domain/Product.java
src/main/java/com/example/boundaries/domain/ProductRepository.java
src/main/java/com/example/boundaries/data/JdbcProductDao.java
src/main/java/com/example/boundaries/data/JdbcProductRepository.java
src/main/java/com/example/boundaries/service/CheckoutService.java
~~~

**`build.gradle`** — the example uses known pinned versions for reproducibility. Java toolchain 21 must be installed or configured for Gradle to provision.

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

**`src/main/resources/application.properties`** — Spring Boot initializes the `DataSource`/HikariCP and runs the two SQL scripts. Disable the web server because the program only uses `CommandLineRunner`.

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:dao_repository_lesson;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

**`src/main/resources/schema.sql`** — `version` serves optimistic concurrency, while `CHECK` lets the DB independently guard against negative stock.

~~~sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(60) NOT NULL UNIQUE,
    available_stock INT NOT NULL CHECK (available_stock >= 0),
    version BIGINT NOT NULL CHECK (version >= 0)
);
~~~

**`src/main/resources/data.sql`**:

~~~sql
INSERT INTO product (id, sku, available_stock, version)
VALUES (1, 'JAVA-BOOK', 5, 0);

INSERT INTO product (id, sku, available_stock, version)
VALUES (2, 'SPRING-BOOK', 3, 0);
~~~

### 9.2. Plain Java Domain Object: `Product.java`

~~~java
package com.example.boundaries.domain;

public record Product(long id, String sku, int availableStock, long version) {
    public Product {
        if (id <= 0 || sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("Invalid product identity");
        }
        if (availableStock < 0 || version < 0) {
            throw new IllegalArgumentException("Invalid product state");
        }
    }

    public Product reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (quantity > availableStock) {
            throw new IllegalStateException("Insufficient stock: " + sku);
        }
        return new Product(id, sku, availableStock - quantity, version);
    }
}
~~~

**What to observe:** No `@Component`, `@Entity`, `JdbcTemplate`, or SQL. The domain protects valid state and expresses the `reserve` behavior in business vocabulary. The returned object preserves the `version` that was read; the version increments only when the SQL UPDATE succeeds. Because this is an immutable Java record, the repository persists the new snapshot after the domain behavior runs.

### 9.3. Repository Contract: `ProductRepository.java`

~~~java
package com.example.boundaries.domain;

import java.util.Optional;

public interface ProductRepository {
    Optional<Product> findById(long id);
    void save(Product product);
}
~~~

The Service imports this interface, not the JDBC implementation. The contract speaks only of `Product` and ID; missing data is represented with `Optional.empty()`.

### 9.4. DAO: `JdbcProductDao.java`

~~~java
package com.example.boundaries.data;

import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class JdbcProductDao {
    private final JdbcTemplate jdbc;

    public JdbcProductDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<ProductRow> findById(long id) {
        return jdbc.query(
            "SELECT id, sku, available_stock, version FROM product WHERE id = ?",
            (rs, rowNum) -> new ProductRow(
                rs.getLong("id"),
                rs.getString("sku"),
                rs.getInt("available_stock"),
                rs.getLong("version")
            ),
            id
        ).stream().findFirst();
    }

    public int updateStock(long id, int newStock, long expectedVersion) {
        return jdbc.update(
            "UPDATE product " +
            "SET available_stock = ?, version = version + 1 " +
            "WHERE id = ? AND version = ?",
            newStock, id, expectedVersion
        );
    }
}

record ProductRow(long id, String sku, int stock, long version) {}
~~~

**Two types in one Java file:** the public class `JdbcProductDao` and the package-private record `ProductRow` are both in package `com.example.boundaries.data`, which is valid in Java. The DAO returns a **row model** and the UPDATE row count, not a checkout concept. `?` placeholders are bound using `PreparedStatement` via `JdbcTemplate`, avoiding SQL injection from parameter string concatenation. Querying 0 rows returns `Optional.empty()`; updating 0 rows indicates either the `version` condition did not match or the record does not exist.

### 9.5. Repository Adapter: `JdbcProductRepository.java`

~~~java
package com.example.boundaries.data;

import com.example.boundaries.domain.Product;
import com.example.boundaries.domain.ProductRepository;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcProductRepository implements ProductRepository {
    private final JdbcProductDao dao;

    public JdbcProductRepository(JdbcProductDao dao) {
        this.dao = dao;
    }

    @Override
    public Optional<Product> findById(long id) {
        return dao.findById(id)
            .map(row -> new Product(
                row.id(), row.sku(), row.stock(), row.version()
            ));
    }

    @Override
    public void save(Product product) {
        int updated = dao.updateStock(
            product.id(), product.availableStock(), product.version()
        );
        if (updated != 1) {
            throw new IllegalStateException(
                "Concurrent product update: " + product.id()
            );
        }
    }
}
~~~

**This is the translation point:** the DAO understands `ProductRow` and SQL statements; the adapter understands both the row and the domain `Product`, performs mapping, and checks whether the write succeeded. If someone else has already changed the version, the UPDATE with `WHERE version = ?` updates zero rows and the adapter raises an error. That is a simple **optimistic concurrency control** mechanism; in a real application, use a clearly classified exception and decide retries according to business rules.

### 9.6. Application Service: `CheckoutService.java`

~~~java
package com.example.boundaries.service;

import com.example.boundaries.domain.Product;
import com.example.boundaries.domain.ProductRepository;
import java.util.NoSuchElementException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {
    private final ProductRepository products;

    public CheckoutService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public void checkout(long firstId, int firstQty, long secondId, int secondQty) {
        if (firstId == secondId) {
            throw new IllegalArgumentException("Products must be distinct");
        }
        reserveAndSave(firstId, firstQty);
        reserveAndSave(secondId, secondQty);
    }

    private void reserveAndSave(long id, int quantity) {
        Product current = products.findById(id)
            .orElseThrow(() -> new NoSuchElementException("Product: " + id));
        Product reserved = current.reserve(quantity);
        products.save(reserved);
    }
}
~~~

Here, **the Service contains no SQL**, **the DAO contains no checkout rules**, and **`Product` knows nothing about transactions**. Calling `reserveAndSave` sequentially for two products shows why the transaction wraps the entire public method: if updating the first product has already completed but the second item lacks sufficient stock, the unchecked exception on the second call causes Spring to roll back both UPDATEs. The private method is a helper running inside the already-opened transaction and needs no separate annotation.

### 9.7. Entry Point and stdout: `DaoRepositoryLessonApplication.java`

~~~java
package com.example.boundaries;

import com.example.boundaries.domain.ProductRepository;
import com.example.boundaries.service.CheckoutService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DaoRepositoryLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(DaoRepositoryLessonApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CheckoutService checkout, ProductRepository products) {
        return args -> {
            show("Before", products);
            checkout.checkout(1L, 2, 2L, 1);
            show("After success", products);

            try {
                checkout.checkout(1L, 1, 2L, 99);
            } catch (IllegalStateException ex) {
                System.out.println("Failed checkout: " + ex.getMessage());
            }

            show("After rollback", products);
        };
    }

    private static void show(String label, ProductRepository products) {
        var javaBook = products.findById(1L).orElseThrow();
        var springBook = products.findById(2L).orElseThrow();
        System.out.printf(
            "%s: JAVA-BOOK=%d, SPRING-BOOK=%d%n",
            label, javaBook.availableStock(), springBook.availableStock()
        );
    }
}
~~~

In the directory containing `build.gradle`, if a Gradle wrapper is present: run `./gradlew bootRun` on Linux/macOS or `.\gradlew.bat bootRun` on Windows PowerShell. If a compatible Gradle is installed without a wrapper: `gradle bootRun`. The program may print additional Spring logs; **the lines actively printed by the demo code** must be:

~~~text
Before: JAVA-BOOK=5, SPRING-BOOK=3
After success: JAVA-BOOK=3, SPRING-BOOK=2
Failed checkout: Insufficient stock: SPRING-BOOK
After rollback: JAVA-BOOK=3, SPRING-BOOK=2
~~~

**Successful run:** Product A's state is transitioned by the domain from 5 → 3; the Repository persists version 0 → 1. Product B transitions 3 → 2, version 0 → 1. The Service finishes normally, so the transaction commits.

**Failed run:** Product A is temporarily decremented 3 → 2 (in a new transaction), but Product B requests 99, so `Product.reserve` throws `IllegalStateException`. The Spring JDBC transaction manager rolls back; A remains 3 and B remains 2 after the transaction. Product A's version value in the database also reverts to the previously committed version. There is no manual SQL rollback written in the Repository or DAO.

**Example limitations:** There is no real shopping cart, orders table, payment, security, retry policy, event publishing, or auditing; `checkout` here is purely a stock-decrement use case to illustrate layer boundaries. The "no negative stock" rule together with optimistic versioning is necessary but not sufficient for designing a production checkout system. When using a different database, verify transaction isolation, deadlock handling, and SQL dialect on the actual engine.

## 10. Tracing a Call Across the Four Roles

| Step | Class / method | Which responsibility? | Practical signal |
| --- | --- | --- | --- |
| 1 | `CheckoutService.checkout` | Application Service | Use case starts, Spring opens/holds transaction |
| 2 | `ProductRepository.findById` | Repository contract | Service requests a domain object, sees no SQL |
| 3 | `JdbcProductRepository.findById` | Repository Adapter | Converts `ProductRow` into `Product` |
| 4 | `JdbcProductDao.findById` | DAO | JDBC executes parameterized `SELECT` |
| 5 | `Product.reserve` | Domain object | Enforces quantity rules, produces valid state |
| 6 | `ProductRepository.save` | Repository contract | Service requests persisting the domain result |
| 7 | `JdbcProductDao.updateStock` | DAO | UPDATE with `version` as a condition |
| 8 | `CheckoutService` finishes/throws | Application Service + transaction manager | Commits both products or rolls back both |

To diagnose a real bug, ask **is it a wrong rule, wrong data, or wrong transaction?** If negative order quantities are accepted, look at the domain invariant. If SQL reads the wrong column, look at the DAO/mapping. If an UPDATE succeeds despite a stale version, check the persistence-layer condition and save-result handling. If Product A was decremented while Product B failed, check the Service transaction boundary and proxy call path.

## 11. When Using Spring Data JPA, How Do the Boundaries Change?

With JPA, many applications do not write a separate JDBC DAO; Spring Data generates the repository implementation from an interface:

~~~java
// JPA structure example, illustrating the API rather than a standalone runnable file.
public interface ProductJpaRepository
        extends org.springframework.data.jpa.repository.JpaRepository<ProductEntity, Long> {
}
~~~

`ProductEntity` here must be an entity class properly mapped with `@Entity`; the snippet above intentionally describes only the **Spring Data contract**, not a standalone compilable program.

The boundaries can be:

~~~text
CheckoutService
  -> ProductRepository (domain port, if separation is needed)
      -> JpaProductRepositoryAdapter
          -> ProductJpaRepository (Spring Data JPA)
              -> EntityManager / JPA provider
                  -> JDBC / Database
~~~

Or in a simple CRUD application:

~~~text
ProductService -> ProductJpaRepository -> JPA provider -> Database
~~~

Having no manual JDBC DAO is normal; **the Repository still handles retrieving/saving data**, while the JPA provider handles SQL and mapping. If a JPA entity also holds domain behavior and meets domain requirements, it can be used directly. If the entity is heavily shaped by schema, lazy loading, ORM lifecycle, and persistence structure, separate the domain `Product` from the stored `ProductEntity`.

**Difference from JDBC:** JPA tracks entities in a persistence context; dirty checking and `flush` may emit SQL later than the moment a setter is called, whereas a `JdbcTemplate.update` call typically sends SQL immediately. Regardless of the underlying technology, the Service should still manage the use case's transaction; do not rely on each save statement acting as an independent transaction.

## 12. Choosing the Right Level of Layer Separation

There is no mandatory formula of "1 controller → 1 service → 1 repository → 1 DAO → 1 entity" for every feature.

**Case A — Small CRUD, few rules:** A Spring Data repository returns JPA entities directly to a thin Service or simple handler; favor concise, clear code. If a Service only calls a single repository method without any use case logic, consider whether it is even needed. Even when simple, avoid putting SQL directly into the Controller.

**Case B — JDBC with clear mapping and rules:** Service → Repository interface → JDBC adapter. The adapter can use `JdbcTemplate` directly; split out a DAO only when SQL/row mapping has a lifecycle of its own or the adapter coordinates multiple data sources.

**Case C — Complex business logic, multiple aggregates/stores:** Behavior-rich domain model, aggregate-oriented repository ports, use-case application services, and suitable persistence adapters. Prioritize domain testability and the ability to swap storage technologies with minimal impact on the business core.

**Do not rely directly on annotation names:** `@Service` and `@Repository` are Spring stereotypes. Responsibility placement is decided by design; adding annotations does not automatically create a cleanly separated architecture.

A practical rule of thumb: **define a Repository interface when the business layer needs a stable contract or persistence independence**. If there is only one simple implementation, everything lives in the same module, and the rate of change is low, creating a separate interface remains a trade-off; avoid abstractions solely to guard against a hypothetical future need.

## 13. Domain Rules, Transactions, and Concurrency

Clear role separation helps surface **two kinds of correctness**:

1. **Object-level correctness:** `Product.reserve` cannot produce a negative state. This can be tested directly with plain Java, without a Spring context.
2. **Multi-operation/database-level correctness:** both saves belong to one transaction, and concurrent requests do not overwrite each other. This requires coordinating the Service, Repository adapter, SQL conditions, and DBMS.

In the example, `WHERE id = ? AND version = ?` detects whether a record has changed since the Service read it. If the version does not match, UPDATE returns 0; the Repository throws an error; the transaction fails. This is **manual optimistic locking**. JPA can support the same idea via `@Version`, though you must understand flush timing and the corresponding exceptions. Under very high contention, consider database-level locking or business-conditional UPDATE statements.

**Do not put connection holding or transactions inside domain objects:** A domain object should not call `entityManager.flush()`, `jdbc.update()`, or `connection.commit()`. When a domain exception occurs, the Service decides how the use case responds; the transaction manager coordinates rollback. In single-DataSource JDBC, manually calling `dataSource.getConnection()` and committing inside a DAO can break the transaction boundary managed by Spring. Use `JdbcTemplate` or Spring-compatible transaction APIs.

If a use case calls an external payment API outside the database, the database transaction **does not automatically cover** the external payment operation. Multi-system workflows require dedicated design (idempotency, outbox, appropriate saga/compensation). That is an orchestration responsibility of the application layer and cannot be solved merely by adding `@Transactional` to a DAO.

## 14. Placing Tests at the Right Boundaries

| Test case | Primary component | Expected evidence |
| --- | --- | --- |
| Order 0 copies, -1 copy, exceeding stock | `Product.reserve` | Throws rule-appropriate error, never creates invalid `Product` |
| Missing row read, SQL mapping, versioned update | `JdbcProductDao` | Proper `Optional.empty()`; updated rows = 1 or 0 per condition |
| Row-to-domain mapping and passing `expectedVersion` | `JdbcProductRepository` | `Product` fields match, save conflict raises error |
| Checkout two products with sufficient stock | `CheckoutService` | Calls save twice properly, sensible order, completes use case |
| Second product insufficient after first updated | Spring integration test with real transaction | Database does not retain the first UPDATE after rollback |
| Two requests concurrently update the same version | Concurrent integration test | No silent lost update; error/retry follows policy |

**Distinguish mock tests from transaction tests:** A unit test using a mocked `ProductRepository` can verify Service orchestration, but cannot prove that database rollback or the Spring proxy actually worked. Use integration tests through real Spring beans with an actual `DataSource` or suitable environment to verify atomicity, SQL, constraints, and locking. For JDBC DAOs, `@JdbcTest` can provide a JDBC test slice; for JPA, `@DataJpaTest` serves JPA persistence. Transaction tests should avoid letting the test's own transaction mask the use case's commit/rollback.

## 15. Common Misconceptions

| Misconception | Why it goes wrong | Better guidance |
| --- | --- | --- |
| "DAO and Repository are always two mandatory layers" | Both sometimes solve the same CRUD query | Separate only when there is clear distinct responsibility and separation value |
| "Repository means Spring Data `JpaRepository`" | One is a domain pattern, the other a framework API | Understand that the domain contract and ORM-based implementation are two different levels |
| "Service contains every single rule" | Domain objects become data-only, making invariants hard to keep | Put state-coupled behavior in the domain; let the Service orchestrate |
| "A JPA entity is always a good domain entity" | Mapping/lazy loading/schema can distort the model | Share when it fits, separate when coupling causes problems |
| "Every table must have a Repository" | DDD repositories usually follow aggregates, not tables | Identify business consistency boundaries |
| "Having `@Transactional` guarantees two updates share a transaction" | Self-invocation, mismatched transaction managers, manually opened Connections | Verify proxies, transaction manager, and enlisted resources |
| "Domain validation removes the need for DB constraints" | Multiple processes and race conditions can still violate rules | Domain rules + DB constraints/locking/versioning |
| "DTO, row, and domain object are one and the same" | Field names, semantics, and lifecycles differ | Map explicitly at API/persistence boundaries when needed |
| "Repository turns all errors into `null` or `false`" | Conflates not-found, conflict, timeout, and SQL errors | Use `Optional` for missing data; appropriate exceptions for technical errors/violations |
| "Mocked Service unit tests alone are enough" | Fails to verify SQL, commit/rollback, pool, DB constraints | Add integration tests along high-risk paths |

A note on **exception translation**: Spring JDBC uses `DataAccessException` (unchecked) for many data access errors. In JPA, `@Repository` with appropriate Spring infrastructure can participate in persistence exception translation. A Service may choose to translate such errors into specific application outcomes, but should not turn every infrastructure error into "not found" or retry unconditionally.

## 16. Self-Check and Design Exercise

**Question 1.** Which layer does the rule "order quantity must be positive and not exceed current stock" belong to?  
**Answer:** The behavior of `Product`/domain object fits because the rule depends directly on product state. Database constraints/concurrency still need to protect data when multiple transactions run concurrently.

**Question 2.** Where should `SELECT id, sku ... FROM product WHERE id = ?` live?  
**Answer:** In the DAO or Repository's persistence adapter, not in `Product` or the Application Service.

**Question 3.** Can the interface `Optional<Product> findById(long id)` be used by the Service without knowing the backend?  
**Answer:** Yes. That is the advantage of a domain-oriented Repository contract; the adapter implements the storage details.

**Question 4.** Checkout two products: UPDATE A succeeds, then B fails. Who is responsible for ensuring a single unit of transaction?  
**Answer:** The Application Service defines the transaction boundary for the whole use case; the Spring transaction manager and DBMS execute commit/rollback, while the DAOs enlist in the proper transaction.

**Question 5.** If an application only has single-table CRUD, is creating a separate Repository interface, implementation, DAO, and mapper always better than a `JdbcTemplate`-based Repository?  
**Answer:** No. The design should reflect real complexity and boundaries of change, avoiding pass-through layers that carry no distinct responsibility.

**Exercise:** Add a `returnStock(productId, quantity)` business operation. Place the `quantity > 0` rule and post-return state creation on `Product`; add a versioned save operation on Repository/DAO; have the Service load `Product`, invoke the behavior, and save within a transaction. Then write an integration test: given two commands targeting the same version, only one update may succeed; the other must receive a clear conflict signal. Be careful to avoid integer overflow when adding large return quantities to stock.

## 17. Design Takeaways

- **Domain object** holds business meaning, valid state, and behavior; it does not need to know SQL/JDBC.
- **DAO** speaks the storage infrastructure language: queries, row mapping, updated row counts.
- **Repository** gives the Service a port to retrieve/save domain objects; the adapter can use a DAO, direct JDBC, or Spring Data JPA.
- **Application Service** organizes the use case, coordinates domain/repositories, and defines transaction boundaries.
- **Separate layers with purpose:** use fewer layers when responsibilities are genuinely simple, while keeping clear boundaries where change, invariants, and consistency matter.

When encountering a new method, ask: "Is this an **object rule**, a **query detail**, a **retrieval contract**, or a **use-case orchestration step**?" That answer points to the right place for the code far better than looking at filename suffixes.
