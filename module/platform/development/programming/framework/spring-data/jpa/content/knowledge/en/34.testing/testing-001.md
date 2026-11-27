# Distinguishing Service Unit Tests and Repository Integration Tests in Spring Data JPA

## Lesson Objectives

After this lesson, you will be able to:

1. Distinguish **Service unit tests** and **Repository integration tests** by the **actual system under test**, **replaced dependencies**, **setup**, and **types of bugs detected**.
2. Write Service tests using **JUnit Jupiter (JUnit 5) + Mockito**, without starting Spring or connecting to a database.
3. Write Repository tests using **`@DataJpaTest` + an H2 database**, using real Spring Data JPA/Hibernate to verify mappings, derived queries, boundary conditions, and persistence.
4. Understand `@Transactional`, `flush()`, `clear()`, default rollback, and the limitations of each testing approach.
5. Choose the appropriate test level and combine both types to verify both **business rules** and **data access behavior**.

Scope: Java 17+ applications, **Spring Boot 3.5**, **Spring Data JPA**, a service using `JpaRepository`. In this lesson, “Service unit testing” means **instantiating the real Service with a mocked Repository**; “Repository integration testing” means **running the real Repository through a JPA provider with a database**.

## 1. Same Application Flow, Two Different Testing Boundaries

Suppose a product management application has the following flow:

```text
Client
  │
  ▼
Controller
  │
  ▼
ProductService                   ← UNIT TEST: real ProductService
  │                                 + ProductRepository as a Mockito mock
  ▼
ProductRepository               ← INTEGRATION TEST: real Repository
  │                                 + real JPA/Hibernate
  ▼
JPA / Hibernate                 ← mapping, SQL, flush, database constraints
  │
  ▼
Database
```

A **Service unit test** asks: “Given the result returned by the Repository, does the Service execute the business logic correctly?” For example: validating an invalid price before saving; normalizing the SKU; rejecting duplicate codes; throwing an exception when an active product is not found.

A **Repository integration test** asks: “When actually running the Repository through Spring Data JPA and the database, are the save/query results correct?” For example: does `findByActiveTrueAndPriceGreaterThanEqualOrderByPriceAsc` return the right products matching the condition, including the inclusive boundary; is the entity persisted and reloaded properly?

These two questions **complement each other**. A Service test using mocks does not prove the SQL query is right; a Repository test hitting the database does not automatically prove every business branch in the Service is right.

### Quick Comparison Table

| Criterion | Service Unit Test | Repository Integration Test |
| --- | --- | --- |
| SUT – the actual target under test | The Service class and logic inside the class | The Repository interface implemented by Spring Data, entity mappings, JPA provider, and database |
| Repository in test | Mockito mock; does not execute queries | Real Repository bean created by Spring |
| Database | Not needed | Yes (H2, PostgreSQL Testcontainers, or another test database) |
| Spring `ApplicationContext` | Usually **not** started | Starts a **test slice** with `@DataJpaTest` |
| Notable libraries | JUnit Jupiter, Mockito, AssertJ | JUnit Jupiter, Spring Boot Test, Hibernate/JPA, database |
| Time cost | Usually low, no I/O connections | Usually higher due to building context, schema, SQL |
| Bugs detected well | `if` branches, validation, calculations, transformations, dependency coordination, exceptions | Derived query names, JPQL, entity mappings, SQL constraints, flush, and real data |
| Bugs **not** proven | Real queries/DDL, rollback via Spring proxy, SQL errors | Any Service branches excluded from the slice, assumptions from mocks, full request flow |
| Test data | Stub: `when(...).thenReturn(...)` | Seed: `persist(...)` / `save(...)`, then read back through JPA |
| Isolation | Each test creates fresh mocks; no DB data | `@DataJpaTest` is transactional by default and rolls back after each test |
| Expected results | Return values, exceptions, collaborator invocations | Actual rows, query results, mappings, constraints, and state after flush/clear |

**The annotation name alone does not determine the test level.** Using `@SpringBootTest` with `@MockitoBean` on the Repository is still a test with a Spring context; it verifies wiring/configuration to some extent, but it is not a pure unit test just because a dependency is mocked. Conversely, `@DataJpaTest` running in-memory H2 is still an **integration test** because JPA and a database actually participate.

## 2. Principles for Designing a Good Test Case

Use the **Arrange – Act – Assert** pattern (equivalent to Given – When – Then):

1. **Arrange**: create input objects, configure mock behavior (unit) or insert data into the DB (integration).
2. **Act**: invoke exactly **one behavior to test**.
3. **Assert**: verify the business outcome or persistence state; only `verify` invocations when that interaction truly belongs to the behavioral contract.

A good test should:
- Have a clear behavior-oriented name, such as `rejectsDuplicateSku` and `findsActiveProductsAtInclusivePriceBoundary`.
- Include **boundary** data: values equal to the threshold, just below the threshold, active/inactive entities, non-existent records.
- Not depend on the execution order of other tests, and not “reuse” data from previous tests.
- Not assert unnecessary implementation details, such as how many times a getter was called or the order of internal methods, unless that exact order is a business requirement.
- Reflect the test boundary: unit tests need no network/database; integration tests must genuinely touch persistence.

## 3. Complete Example: One Product, Two Testing Layers

Business requirements of the example:

- When registering a product: the SKU must not be blank and must be `trim()`med; the price must be greater than 0; an existing SKU must not be accepted.
- A new product defaults to `active=true`.
- Retrieving the price by SKU must only return it when the product is still active.
- The Repository must accurately find active products with `price >= minPrice` sorted by ascending price.
- Data must be saved and reloaded properly through JPA.

Maven structure (all classes in the same package so Spring Boot scans entities/repositories):

```text
service-repository-testing/
├── pom.xml
└── src/
    ├── main/java/com/example/testing/
    │   ├── TestingApplication.java
    │   ├── Product.java
    │   ├── ProductRepository.java
    │   └── ProductService.java
    └── test/java/com/example/testing/
        ├── ProductServiceTest.java
        └── ProductRepositoryTest.java
```

The example uses **Spring Boot 3.5.16** with Java 17. Maven needs access to download dependencies from the standard repository on the first run; no separate database server is required because H2 runs in-memory.

### 3.1. Dependency Declaration — `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>service-repository-testing</artifactId>
    <version>1.0.0</version>

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

`spring-boot-starter-data-jpa` provides Spring Data JPA and Hibernate; `h2` is the embedded database used when running tests; `spring-boot-starter-test` includes JUnit Jupiter, Mockito, AssertJ, and Spring Test infrastructure. Thanks to Spring Boot dependency management, these dependencies do not need explicit individual versions.

### 3.2. Spring Boot Entry Point — `TestingApplication.java`

```java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}
```

This class helps Spring Boot locate configuration when running `@DataJpaTest`. **Service unit tests do not start this class.**

### 3.3. JPA Entity — `Product.java`

```java
package com.example.testing;

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

    @Column(nullable = false, unique = true, length = 64)
    private String sku;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active;

    protected Product() {
        // JPA requires a no-arg constructor.
    }

    public Product(String sku, BigDecimal price, boolean active) {
        this.sku = sku;
        this.price = price;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public boolean isActive() {
        return active;
    }
}
```

This is a **minimal entity for testing purposes**. In a real application, add appropriate invariants/validations and state-changing methods. `unique = true` creates a constraint in the Hibernate-generated schema for the demo, but the reliability of production constraints must be verified against the **actual production migration/schema**.

### 3.4. Real Repository — `ProductRepository.java`

```java
package com.example.testing;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {

    boolean existsBySku(String sku);

    Optional<Product> findBySku(String sku);

    Optional<Product> findBySkuAndActiveTrue(String sku);

    List<Product> findByActiveTrueAndPriceGreaterThanEqualOrderByPriceAsc(
            BigDecimal minPrice);
}
```

Spring Data JPA parses the method names and generates the queries. **Repository tests must prove that behavior against a database**—never use `Mockito.mock(ProductRepository.class)` to “test” these queries.

### 3.5. Service Containing Business Logic — `ProductService.java`

```java
package com.example.testing;

import java.math.BigDecimal;
import java.util.NoSuchElementException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Product register(String sku, BigDecimal price) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }
        if (price == null || price.signum() <= 0) {
            throw new IllegalArgumentException("Price must be positive");
        }

        String normalizedSku = sku.trim();
        if (repository.existsBySku(normalizedSku)) {
            throw new IllegalStateException("SKU already exists");
        }

        return repository.save(new Product(normalizedSku, price, true));
    }

    @Transactional(readOnly = true)
    public BigDecimal activePrice(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU must not be blank");
        }

        String normalizedSku = sku.trim();
        return repository.findBySkuAndActiveTrue(normalizedSku)
                .map(Product::getPrice)
                .orElseThrow(() ->
                        new NoSuchElementException("Active product not found"));
    }
}
```

The logic of `register` is:
1. Validate arguments.
2. Normalize the SKU.
3. Ask the repository if the SKU exists.
4. If not, create an active `Product` and call `save`.

`activePrice` asks the repository to find an **active SKU**; `Optional.empty()` results in a `NoSuchElementException`.

**Limitation:** calling `existsBySku` before `save` does not eliminate race conditions when two requests register the same SKU concurrently. A database `UNIQUE` constraint is still required to guarantee uniqueness. This is a clear example of why both unit tests and integration tests need to exist.

## 4. Service Unit Tests: JUnit + Mockito, No Spring

**`src/test/java/com/example/testing/ProductServiceTest.java`**

```java
package com.example.testing;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import java.util.NoSuchElementException;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class ProductServiceTest {

    @Mock
    private ProductRepository repository;

    @InjectMocks
    private ProductService service;

    @Test
    void registersValidProductWithNormalizedSku() {
        when(repository.existsBySku("BK-01")).thenReturn(false);
        when(repository.save(any(Product.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        Product result =
                service.register("  BK-01  ", new BigDecimal("100.00"));

        assertThat(result.getSku()).isEqualTo("BK-01");
        assertThat(result.getPrice()).isEqualByComparingTo("100.00");
        assertThat(result.isActive()).isTrue();

        verify(repository).existsBySku("BK-01");
        ArgumentCaptor<Product> productCaptor =
                ArgumentCaptor.forClass(Product.class);
        verify(repository).save(productCaptor.capture());

        assertThat(productCaptor.getValue().getSku()).isEqualTo("BK-01");
        assertThat(productCaptor.getValue().isActive()).isTrue();
    }

    @Test
    void rejectsNonPositivePriceBeforeRepositoryCall() {
        assertThatThrownBy(() ->
                service.register("BK-02", BigDecimal.ZERO))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Price must be positive");

        verifyNoInteractions(repository);
    }

    @Test
    void rejectsDuplicateSkuWithoutSaving() {
        when(repository.existsBySku("BK-01")).thenReturn(true);

        assertThatThrownBy(() ->
                service.register("BK-01", new BigDecimal("50.00")))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("SKU already exists");

        verify(repository).existsBySku("BK-01");
        verify(repository, never()).save(any(Product.class));
    }

    @Test
    void readsPriceOnlyForActiveProduct() {
        when(repository.findBySkuAndActiveTrue("BK-03"))
                .thenReturn(Optional.of(
                        new Product("BK-03", new BigDecimal("75.00"), true)));

        BigDecimal price = service.activePrice("  BK-03  ");

        assertThat(price).isEqualByComparingTo("75.00");
        verify(repository).findBySkuAndActiveTrue("BK-03");
    }

    @Test
    void reportsMissingOrInactiveProduct() {
        when(repository.findBySkuAndActiveTrue("BK-04"))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.activePrice("BK-04"))
                .isInstanceOf(NoSuchElementException.class)
                .hasMessage("Active product not found");

        verify(repository).findBySkuAndActiveTrue("BK-04");
    }
}
```

### Why Is This a Unit Test?

- `@ExtendWith(MockitoExtension.class)` manages Mockito mocks for JUnit Jupiter.
- `@Mock` creates a **fake ProductRepository**; every mocked method returns values configured by the test (or default values).
- `@InjectMocks` instantiates the **real ProductService** and injects the mocked repository via the constructor. There is no Spring ApplicationContext, Hibernate, or database.
- `when(...).thenReturn(...)` simulates **dependency results**; `thenAnswer(...)` in the example returns the object passed to `save`, standing in for a real DB.
- `assertThat(...)` asserts outcomes; `verify(...)` asserts required interactions, such as **not saving** when input is invalid.
- Tests run fast and independently: Hibernate/SQL errors do not affect testing service logic.

**Notable detail:** `result.getId()` in the first test will still typically be `null` because Mockito does not execute an `INSERT` or generate an ID. Never assert that the DB persisted successfully just because a mocked `save` was called.

**Crucial experiment:** if a derived method name in the Repository is mistyped, a Service unit test with mocks can still pass because the mock interface does not run queries. That bug requires an integration test to catch.

### What Should Be Mocked?

Mock dependencies that sit **outside the logic boundary under test**, such as a Repository, publisher/email client, or fixed clock. Do not mock `ProductService` itself when the goal is to test its business rules. Do not mock `Product` if it is simply an entity used as input/output data.

Mockito is unsuitable for proving SQL, transaction commit/rollback, `@Entity` mappings, or query performance. If a unit test requires configuring dozens of stubs just to get through the logic, revisit how the service responsibilities and test data are separated.

## 5. Repository Integration Tests: @DataJpaTest + Real H2

**`src/test/java/com/example/testing/ProductRepositoryTest.java`**

```java
package com.example.testing;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void findsOnlyActiveProductsAtInclusivePriceBoundary() {
        entityManager.persist(
                new Product("BK-90", new BigDecimal("90.00"), true));
        entityManager.persist(
                new Product("BK-100", new BigDecimal("100.00"), true));
        entityManager.persist(
                new Product("BK-150", new BigDecimal("150.00"), true));
        entityManager.persist(
                new Product("BK-200", new BigDecimal("200.00"), false));

        entityManager.flush();
        entityManager.clear();

        List<Product> actual =
                repository.findByActiveTrueAndPriceGreaterThanEqualOrderByPriceAsc(
                        new BigDecimal("100.00"));

        assertThat(actual)
                .extracting(Product::getSku)
                .containsExactly("BK-100", "BK-150");
    }

    @Test
    void persistsAndReloadsEntityMapping() {
        Product inserted = entityManager.persistAndFlush(
                new Product("BK-09", new BigDecimal("19.90"), true));
        Long generatedId = inserted.getId();

        entityManager.clear();

        Product reloaded = repository.findBySku("BK-09").orElseThrow();

        assertThat(generatedId).isNotNull();
        assertThat(reloaded.getId()).isEqualTo(generatedId);
        assertThat(reloaded.getSku()).isEqualTo("BK-09");
        assertThat(reloaded.getPrice()).isEqualByComparingTo("19.90");
        assertThat(reloaded.isActive()).isTrue();
    }

    @Test
    void excludesInactiveProductFromActiveSkuQuery() {
        entityManager.persistAndFlush(
                new Product("OFF-01", new BigDecimal("40.00"), false));
        entityManager.clear();

        assertThat(repository.findBySkuAndActiveTrue("OFF-01"))
                .isEmpty();
    }

    @Test
    void checksSkuExistenceAgainstPersistedData() {
        entityManager.persistAndFlush(
                new Product("EX-01", new BigDecimal("30.00"), true));
        entityManager.clear();

        assertThat(repository.existsBySku("EX-01")).isTrue();
        assertThat(repository.existsBySku("ABSENT-01")).isFalse();
    }
}
```

### Why Is This an Integration Test?

`@DataJpaTest` builds a **JPA-focused slice of the Spring ApplicationContext**: scanning `@Entity` classes, creating a DataSource, EntityManagerFactory, TransactionManager, and Spring Data Repositories. With H2 on the test classpath, it uses an embedded database by default. Calls to `persist`, `flush`, and Repository queries are sent to **real Hibernate and the database**.

There is no `@Mock` here: `ProductRepository` is a bean created by Spring Data JPA. As a result, the test can detect:
- Method names with wrong property names (e.g., `findByPricee...`) causing Spring Data to fail query creation.
- Column mapping errors or wrong data types.
- `>=` mistakenly written as `>`, wrong `active` filtering, wrong result ordering.
- Data not saved or not reloaded properly after clearing the persistence context.
- Certain constraint and JPQL/SQL errors that only surface when queries or `flush` execute.

**Why does the test call `entityManager.flush()` then `entityManager.clear()`?** `flush()` sends pending writes to the database within the current transaction; `clear()` evicts managed entities from the L1 cache. Subsequent queries must reload state through the persistence layer, preventing a false-positive green test simply because the old object remained in the persistence context. Even so, `flush()` **is not a commit**, and by default the data is rolled back after the test.

### Real SQL and H2 Limitations

This test executes real SQL against H2, so it is an integration test. However, **H2 is not equivalent to every production database engine**: JSONB, arrays, collations, timezones, locking, index hints, native PostgreSQL queries, transaction isolation, and dialects may differ. If production uses PostgreSQL and queries use PostgreSQL-specific features, you need integration tests running **real PostgreSQL** (typically Testcontainers) with production schema migrations. Do not use mocks as a substitute for verifying that database-specific behavior.

## 6. Running the Example and Reading Results

In the directory containing `pom.xml`, **JDK 17+ and Maven** are required. Run everything:

```bash
mvn test
```

Run each class separately if you want to compare scopes:

```bash
mvn -Dtest=ProductServiceTest test
mvn -Dtest=ProductRepositoryTest test
```

With the configuration and source code above, expected results:
- `ProductServiceTest` has **5 cases**: successful registration, invalid price, duplicate SKU, reading active price, not found/inactive.
- `ProductRepositoryTest` has **4 cases**: active filter with inclusive boundary, mapping round-trip, excluding inactive, verifying SKU existence.
- A total of **9 tests**, all **PASS** if the environment/dependencies work properly; log details, elapsed times, and Maven summary lines vary by version/plugin so do not rely on fixed stdout.

In case of failure, read the stack trace by **layer**: failures in `ProductServiceTest` point to logic/stubs/assertions; failures during `ProductRepositoryTest` startup may indicate entity/query mapping, H2/DDL, or JPA configuration issues; failures at `flush` may indicate constraints, column types, or data issues.

## 7. Distinguishing @Mock, @MockitoBean, @DataJpaTest, and @SpringBootTest

| Usage | Effect | When to Use |
| --- | --- | --- |
| Mockito's `@Mock` | Creates a fake object managed by Mockito | Service unit tests without starting Spring |
| `@InjectMocks` | Instantiates the real class and injects mocks into dependencies | Unit tests for classes with clear constructors |
| Spring Test's `@MockitoBean` | Replaces a bean in the **Spring ApplicationContext** with a Mockito mock | Tests with a Spring context, e.g. Controller/service wiring tests; unnecessary in pure unit tests |
| `@DataJpaTest` | Starts the JPA slice, real Repositories, and a test database | Repository/entity/query integration tests |
| `@SpringBootTest` | Starts a broader application context, potentially spanning multiple layers | Testing Service–Repository–DB integration, transaction proxies, wiring, or full application flows |

Starting with Spring Framework 6.2 and Spring Boot 3.4+, `@MockitoBean` is the standard annotation for overriding Spring beans in context-based tests; Spring Boot's older `@MockBean` annotation was deprecated in the 3.4 line. **Do not place `@MockitoBean` in a pure unit test expecting it to spin up a Spring context automatically**: Mockito `@Mock` is more appropriate and lighter for Service tests that do not use Spring.

`@DataJpaTest` ordinarily **does not include standard `@Service` beans in the context**. If you want to test the Service itself using a real Repository and verify `@Transactional`, use an integration test with an appropriate context configuration, typically `@SpringBootTest` paired with a test database. Do not confuse a Repository slice test with a full-stack end-to-end test.

## 8. @Transactional and Rollback: Easy Ways to Create False-Positive Tests

### 8.1. @Transactional in Service Unit Tests

In `ProductServiceTest`, `@InjectMocks` calls the constructor directly; the service **does not go through a Spring AOP transaction proxy**. Therefore:
- `@Transactional` in `ProductService` **does not actually open a transaction** in unit tests.
- Unit tests can verify throwing an exception, but **do not prove database rollback** when that exception occurs.
- Fast unit tests are intentional; they should not be treated as proof of transaction semantics.

### 8.2. @DataJpaTest Default Rollback

`@DataJpaTest` runs each test inside a transaction by default and **rolls it back when finished**. This keeps tests independent and leaves no leftover records. Because the test transaction remains open, `flush()` lets you observe constraints/queries, but **does not fully verify behaviors that only occur on commit or after commit**, such as after-commit events.

If a feature requires a real commit, consider a separate integration test with explicit transaction boundaries, such as `TestTransaction.flagForCommit()` + `TestTransaction.end()` in supported Spring transactional tests; remember to manage data cleanup after commit. For HTTP tests using `@SpringBootTest(webEnvironment = RANDOM_PORT)`, the server typically runs transactions on a separate thread, so rolling back the test client's transaction **does not roll back** server transactions.

### 8.3. Flush Before Checking Constraints

Hibernate can defer SQL INSERT/UPDATE statements until flush/commit. If you test UNIQUE, NOT NULL, or foreign key constraints by calling `repository.save(entity)` and asserting no exception, you might miss errors that surface later. Use `entityManager.flush()` or `repository.saveAndFlush(...)` in integration tests to send SQL to the database. Note that some deferred constraints in production databases are only checked at **commit**, requiring appropriate tests.

### 8.4. Dirty Checking and L1 Cache

When the same EntityManager holds a managed object, `findById` may return that exact object without issuing a new SELECT. To test a database round-trip, `flush` then `clear`. However, `clear()` detaches all entities in the persistence context; if there is unflushed data, changes can be lost. This is an intentional operation in test fixtures, not a pattern to sprinkle arbitrarily in business logic.

## 9. Cases Where One Type of Test Cannot Replace the Other

### Case 1: Derived Query Changed Incorrectly

A developer changes the repository from:

```java
List<Product> findByActiveTrueAndPriceGreaterThanEqualOrderByPriceAsc(
        BigDecimal minPrice);
```

to:

```java
List<Product> findByActiveTrueAndPriceGreaterThanOrderByPriceAsc(
        BigDecimal minPrice);
```

The code still compiles and is valid, but loses the equals sign at the boundary. Service unit tests can still PASS because the mocked Repository returns pre-configured data. A Repository test seeding a product priced at **exactly 100.00** will FAIL because the record is excluded. That is why real query behavior must be tested.

### Case 2: Service Checks Price Incorrectly

A developer changes `price.signum() <= 0` to `price.signum() < 0`, accidentally allowing a price of **0**. Repository integration tests using only valid data might still PASS. The unit test `rejectsNonPositivePriceBeforeRepositoryCall` will FAIL. That is why Service logic should be tested directly.

### Case 3: Duplicate SKU From Two Concurrent Transactions

Two requests concurrently call `existsBySku("BK-01")` and both see `false`; then both save. Unit tests confirm the duplicate-check branch works, but cannot guarantee race handling. A database UNIQUE constraint is what keeps data valid under concurrency. Only integration tests combining concurrent transactions and a production-like DB prove full race handling; the Service should translate constraint errors into an appropriate business error per the API design.

### Case 4: Transaction Must Roll Back an Entire Chain of Operations

A Service saves a Product and then calls a second operation that fails; the requirement is that **all changes must roll back**. Mocked unit tests can confirm the exception branch or method calls, but cannot prove real rollback. The Repository slice is also insufficient because it excludes the Service's transaction boundary. You need an integration test with **real Service bean + real Repository bean + database**, invoking the service through the Spring proxy and inspecting the DB after the transaction finishes.

## 10. DataJpaTest, Schemas, Migrations, and Databases in Tests

There are three levels of production fidelity:

| Database Setup | Advantages | Limitations / When to Use |
| --- | --- | --- |
| Embedded H2 via `@DataJpaTest` | Lightweight, fast, runs offline once dependencies are downloaded | Good for JPQL and common mappings; does not prove PostgreSQL, MySQL, etc. dialects/SQL |
| Local / dedicated configured test database | Can test against a real engine | Requires isolating environment, schema, data, and cleanup steps |
| Testcontainers with DB matching production type/version | Isolated and more realistic; catches engine-specific SQL/dialect/schema issues | Slower startup, requires container runtime; to be accurate, must run migrations close to production |

### Do Not Replace the DataSource When a Real Database Is Needed

`@DataJpaTest` by default can replace the application DataSource with an embedded database when H2 is on the classpath. If you want to **keep** the configured test DataSource, declare (as in Spring Boot 3.5):

```java
@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class ProductRepositoryDatabaseTest {
    // Tests use the DataSource configured by the test environment.
}
```

Import `org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase` and `org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest`. This snippet **illustrates configuration**, not a standalone test to copy into the project from section 3. Only use `Replace.NONE` when the test actually provides its own URL, credentials, and dedicated database (typically via Testcontainers/`@DynamicPropertySource` or service connection); otherwise, you risk accidentally touching an unintended database.

### Test the Real Schema Instead of Relying Solely on ddl-auto

Hibernate `ddl-auto=create-drop` generates schema from entities; this is convenient for demos, but can hide migration errors. If production uses Flyway/Liquibase, critical integration tests should run actual migrations against a test database and then verify entity mappings/queries. Never alter migration SQL just to accommodate an H2 difference when production uses PostgreSQL.

## 11. Designing an Effective Test Suite in a Spring Data JPA Project

A practical strategy:

1. **Service unit tests** for every meaningful business branch: validation, data transformation, repository call decisions, `Optional.empty()` handling, exceptions, and required events.
2. **Repository integration tests** for custom/derived queries with logic, especially `AND`/`OR`, date/time ranges, `JOIN FETCH`, `@EntityGraph`, projections, pagination, unique/foreign keys, and engine-specific SQL.
3. **Service integration tests** when proving AOP transactions, rollback, optimistic locking, multi-repository chains, after-commit events, or real bean collaboration.
4. **API/end-to-end tests** for serialization, security, HTTP contracts, routing, and deployment layers; choose representative scenarios rather than repeating every unit case.
5. **Dedicated performance/reliability measurements** for N+1, query counts, lock contention, race conditions: most value-correctness tests do not automatically prove performance or concurrency.

Test names should state the condition and outcome clearly, e.g., `findsActiveProductsAtInclusivePriceBoundary`, not just `testFindAll`. In Repository tests, insert data with `TestEntityManager` or SQL fixtures and then query with the **real Repository**; avoid using the exact method under test for both seeding and assertion as it can self-validate bugs.

To avoid test flakiness:
- Do not depend on record ordering if the query **has no `OrderBy`**; use `containsExactlyInAnyOrder` when business logic does not require sorting.
- For time, use a fixed `Clock` or `Instant` instead of `Instant.now()` in boundary assertions.
- Avoid `double` floating-point numbers for money; use `BigDecimal` and numeric comparison.
- When verifying persistence, `flush` + `clear` to separate L1 state from DB state.
- For asynchronous processing, wait on bounded, stable conditions; avoid arbitrary `Thread.sleep`.
- Do not share mutable test data or database state across tests without clear isolation mechanisms.

## 12. Checklist for Choosing a Test Type by Question

| What do you need to verify? | Suitable Test Type |
| --- | --- |
| Blank SKU or price ≤ 0 is blocked before saving? | Service unit test |
| Service calls `existsBySku` with the trimmed SKU? | Service unit test |
| Service throws an exception when repository returns `Optional.empty()`? | Service unit test |
| `findBy...GreaterThanEqual` includes the exact boundary value? | Repository integration |
| Entity maps the `price` column with the right precision/scale? | Repository integration, with the corresponding DB |
| JPQL/native query executes properly on the production dialect? | Repository integration on the production database engine |
| Real UNIQUE/foreign key/NULL constraints are enforced? | Repository integration (flush/commit depending on constraint type) |
| `@Transactional` on Service rolls back multiple writes on failure? | Service integration with Spring proxy and real database |
| Controller returns the right HTTP status/JSON? | MVC/API test, broader scope than this lesson |
| Two concurrent requests avoid lost updates? | Integration/concurrency test with real DB, transactions, and locking |

## 13. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Mocking Repository in a test named “RepositoryIntegrationTest” | Executes no queries, verifies no mappings/SQL | Use `@DataJpaTest` and the real Repository bean |
| Enabling `@SpringBootTest` for every Service unit test | Slow, prone to unintended configuration dependencies | Use `@ExtendWith(MockitoExtension.class)` when testing logic only |
| Using `@Mock` expecting Spring to inject it into the context | Spring does not override application beans | For context tests, use `@MockitoBean`; unit tests need no context |
| Calling mocked `save` and asserting DB has the record | Mock does not persist to DB or generate real IDs | Verify interactions in unit tests; save/load DB in integration tests |
| Testing only the “happy path” | Misses boundary conditions, nulls, missing data | Add exact boundary, invalid input, duplicate, and inactive cases |
| Not calling `flush` when testing constraints | Exception may not have fired yet | Flush or commit in appropriate tests |
| Not calling `clear` when verifying round-trip | L1 cache can mask reload errors | Flush then clear before reloading |
| Thinking `@DataJpaTest` tests `@Transactional` on Services | Services are usually absent from the slice | Service integration test with Spring proxy |
| Trusting H2 to reflect all production SQL | Can miss dialect/locking differences | Testcontainers or matching DB engine/version |
| Asserting order without ORDER BY | Flaky tests depending on execution plan | Add explicit ordering or order-independent assertions |
| Overusing `verify(..., times(1))` on every call | Tests tightly coupled to implementation, brittle on refactor | Verify only interactions representing mandatory behavior |
| Broadly using `@DirtiesContext` to clean test data | Significantly slower due to rebuilding context | Prefer controlled rollback/fixture isolation |

## 14. Practice Exercises

**Exercise A — Unit Test:** Add a rule to `ProductService.register`: the SKU must be at least 4 characters long after `trim()`. Write a test verifying short SKUs are rejected **before any repository call**. Do not use a Spring context.

**Exercise B — Repository Integration:** Add `List<Product> findByActiveTrueAndPriceLessThanOrderByPriceAsc(BigDecimal ceiling)`. Seed three prices `99.99`, `100.00`, `100.01`, all active, then query with ceiling `100.00`. The result must contain **only 99.99**, because `LessThan` is `<`.

**Exercise C — Mapping Check:** Create a Product, `persistAndFlush`, `clear`, then load by SKU. Compare `id`, `price`, and `active`. If you do not `clear`, what could you be inspecting from L1 without proving a round-trip?

**Exercise D — Test Level Design:** A Service updates two entities in one transaction and then throws an exception. Which test type proves **both updates roll back**? How should real dependencies and the transaction boundary be set up?

**Suggested Answers:**
- A: Unit test with `@Mock` repository and `verifyNoInteractions(repository)`.
- B: `@DataJpaTest` with real seeded rows, `flush/clear`, and asserting only the single matching SKU.
- C: It does not rule out that the managed object in L1 was returned without reading from the DB.
- D: Service integration test with a **real Spring-managed Service**, real Repository, and test DB; inspect the DB after the transaction finishes rather than just verifying mocks.

## 15. Key Takeaways

**Service Unit Test = Real Service + Mocked Repository → verifies business logic.**  
**Repository Integration Test = Real Repository + Real JPA + DB → verifies mappings/queries/persistence.**

The two test layers have different goals and costs; they do not replace each other. `@Transactional` on a Service is only properly tested when the Service runs **through a Spring proxy** in an appropriate integration test. Do not confuse `flush` with `commit`, and do not confuse L1 cache data with data reloaded from the DB.

### Official Documentation

- Spring Boot 3.5 – Testing: https://docs.spring.io/spring-boot/3.5/reference/testing/index.html
- Spring Boot 3.5 – Auto-configured Data JPA Tests and TestEntityManager: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.autoconfigured-tests
- Spring Framework 6.2 – `@MockitoBean` and `@MockitoSpyBean`: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html
- Spring Data JPA – Query Methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Framework – Test-managed transactions: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html