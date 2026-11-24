# Replacing Full-Context Tests with Slice or Unit Tests When Evidence Is Sufficient

## 1. The problem: faster tests without losing evidence

A Spring Boot project has hundreds of classes annotated with `@SpringBootTest`. Each class only checks a price calculation, a JSON field, or a repository query, yet still requires the full ApplicationContext: component scanning, auto-configuration, JPA, DataSource, security, web infrastructure, schedulers, HTTP clients, and possibly Testcontainers. In a large test suite, this incurs unnecessary startup and maintenance overhead.

A common reflex is to **replace every `@SpringBootTest` with unit tests** and call it a successful optimization. Yet doing so can erase vital evidence: proper annotation mappings, `@Valid` enforcement, security filters rejecting anonymous users, repository queries matching the dialect, proper transaction wiring, configuration properties binding, or HTTP requests actually reaching the right handler.

**Core principle:** only replace a full-context test with a unit or slice test when **the behaviors the old test was responsible for proving remain sufficiently proven** at the new boundary or in a remaining set of integration tests. Changing annotations is not the destination; **preserving the contract while cutting redundant setup** is the goal.

This lesson belongs to **Context cache and performance**. It ties together the Spring TestContext cache, context size, setup cost, number of cache keys, test isolation, and an evidence map across layers.

### After this lesson, you will be able to

1. Distinguish unit tests, Spring slice tests, full-context MockMvc integration tests, and real HTTP integration tests.
2. Select test boundaries by **the question to be proven**, not by annotation habit.
3. Evaluate when Mockito fits and when mocking deletes the very behavior under test.
4. Understand `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, and other Spring Boot test slices.
5. Keep a small **cross-layer seam test** when splitting a large full integration test into unit/slice tests.
6. Recognize differing cache-key costs caused by mock overrides, profiles, inline properties, and slices.
7. Understand why `@SpringBootTest` does not automatically open a real HTTP server, whereas `RANDOM_PORT` does.
8. Organize tests that are independent, fast, and reliable without forcing `@DirtiesContext` onto every integration test.
9. Try a Java 17+, Spring Boot 3.5.16 sample with **15 JUnit Jupiter methods** spanning four levels.
10. Build a "sufficient evidence" checklist for reviewing test-refactoring PRs.

**Version scope:** Java 17+, Spring Boot 3.5.x, Spring Framework 6.x, JUnit Jupiter, Mockito, AssertJ, Spring MVC, Spring Data JPA, H2. Spring Boot 4.x changes certain modules, starters, and test packages; imports here are chosen for **Boot 3.5.16**, not mixed with Boot 4.x guides.

## 2. Before choosing a tool, rewrite the test question

Instead of asking "should I use `@SpringBootTest` or `@WebMvcTest`?", ask: **What happens if a developer intentionally breaks this behavior? Which test must turn red?**

Example using a product-creation feature:

| Behavior/contract | When a regression is deliberately introduced | Test layer needed to catch it |
|---|---|---|
| Price must be greater than 0 in service | Service accepts price 0 | Unit service test |
| Name is trimmed before saving | Remove `trim()` | Unit service test |
| Route `POST /products` accepts JSON | Change route to `/items` | MVC slice or full MockMvc |
| Request missing name gets 400 | Remove `@NotBlank`/`@Valid` | MVC slice or full MockMvc |
| JSON response has id/name/price | Change DTO serialization | MVC slice or full MockMvc |
| JPA mapping saves price column properly | Change entity mapping/query | JPA slice or real-DB integration |
| Controller→service→repository actually wired together | Wire wrong dependency | A full-context integration test |
| Anonymous cannot create products when login required | Remove authorization rule | Security-enabled MockMvc/HTTP test |
| Real HTTP over port works | Web server/network config broken | `RANDOM_PORT` + HTTP client |
| DB transaction/retry/outbox works | Change transaction/rollback behavior | Integration test with real resources |

**"Sufficient evidence" does not mean repeating identical assertions across multiple layers.** It means every requirement has one or a few tests **actually executing across the risky boundary**, including negative cases and a small set of cross-layer wiring tests.

### 2.1. A sanity-check question before mocking

"If this collaborator is replaced by a Mockito mock, does the behavior where I want to detect bugs still execute?"

- Want to verify **the service decides to call the repository with a normalized price**: mocking the repository can be appropriate.
- Want to verify **the SQL query matches the right rows**: mocking the repository is insufficient.
- Want to verify **JSON ↔ DTO and status mapping**: mocking the service while keeping real Spring MVC makes sense.
- Want to verify **the service bean is injected into the controller on application start**: mocking the service in an MVC slice does not prove it.
- Want to verify **the security filter chain and CSRF**: do not disable filters or `permitAll` just to make the test green.
- Want to verify **HTTP TCP sockets, servlet container, and reverse-proxy assumptions**: MockMvc is insufficient; a real HTTP path is required.
- Want to verify **real Kafka publish/consume**: mocking `KafkaTemplate` is insufficient; broker integration is needed.

Mock at the boundary **outside the question being proved**. Mocking at the layer **containing the target behavior** defeats the test.

## 3. Test levels and observation scope

```text
               Real environment / cross-system
            [RANDOM_PORT + DB/IdP/broker etc.]
                       /\
                      /  \
              Full Spring Boot integration
             [@SpringBootTest + MockMvc]
                    /        \
              MVC slice     JPA slice
              [@WebMvcTest] [@DataJpaTest]
                   \          /
                    \        /
                    Pure unit tests
                      [JUnit/Mockito]
```

This diagram is a classification framework, **not** a hierarchy where "higher is always better". Each level catches a distinct class of bugs.

| Criterion | Pure unit | `@WebMvcTest` | `@DataJpaTest` | Full `@SpringBootTest` + MockMvc | Full `RANDOM_PORT` |
|---|---|---|---|---|---|
| Spring context | No | MVC slice | JPA slice | Full app | Full app + server |
| App-wide bean/component wiring | No | No | No | Yes | Yes |
| Domain branching | Yes | Service usually mocked | Possibly via repository behavior | Yes | Yes |
| JSON route/validation | No | Yes | No | Yes | Yes |
| JPA entity mapping/query | No | Usually no | Yes | Yes if using real repo | Yes if using real repo |
| Real HTTP socket | No | No | No | No | Yes |
| Production-accurate external DB dialect | No | No | Only if using matching database | Only if using matching database | Only if using matching database |
| Spring Security filters | No | Per slice context/config | Outside scope | Per full context/config | Per server config |
| Startup/setup cost | Very low | Usually lower than full | Usually lower than full | Usually higher | Usually highest |
| Cache reuse | Not needed | By slice key | By slice key | By full-context key | By web-server key |

**Do not treat this table as an absolute speed guarantee.** A full context that gets a cache hit can be very cheap on the next run; conversely, a slice loaded with excessive beans/customizers may no longer be lightweight. Measure in practice to verify the benefit.

## 4. Why do full-context tests take time?

A `@SpringBootTest` uses `SpringApplication` to build an `ApplicationContext` matching the target configuration. When the full app includes JPA, a datasource, scheduling, HTTP client wiring, observability, security, or optional integrations, startup overhead can be noticeable.

However, the Spring TestContext framework maintains a **JVM-wide static `ApplicationContext` cache**:

1. Computes a configuration cache key from application classes, context loader, profiles, property sources, context customizers, and other metadata.
2. If the key is already loaded and not evicted/dirtied, **reuses the exact existing `ApplicationContext` instance**.
3. If the key is new, creates/refreshes a context.
4. If unique contexts exceed the default cache capacity of **32**, Spring Framework uses LRU eviction.
5. If a test uses `@DirtiesContext`, the context can be closed and reloaded later.

**Therefore:** a full-context test class does not necessarily incur full startup cost if many classes share the same cache key. Optimizing a suite by converting every full-context test into dozens of distinct slice contexts **is not guaranteed** to lower total startup time.

### 4.1. Factors turning "the same full-context" into many cache keys

- Different `@ActiveProfiles`.
- Different `@SpringBootTest(properties=...)`.
- Different `@TestPropertySource`.
- Different test configuration classes/imports.
- Different `@MockitoBean`/`@MockBean` targets, qualifiers, or fallback field names.
- Different `@DynamicPropertySource` methods/context customizers.
- Different servlet/reactive environments or test slice annotations.
- Different parent contexts/hierarchies.
- A context evicted via `@DirtiesContext` or LRU.
- Tests running in **different forked JVMs** (the static cache is not cross-process).

**Distinguish context startup cost from per-method cost.** JUnit methods, fixtures, DB cleanup, transactional rollbacks, Mockito stubbing, Testcontainers operations, and HTTP requests still consume time even on a context cache hit.

### 4.2. Approximate cost model

Let:

- `S(K)`: startup time of context cache key `K`.
- `N(K)`: actual number of startups due to misses/dirtying/eviction.
- `E(i)`: execution time of method `i` including fixtures.
- `F`: fork, database/container setup, and build overhead.

Then approximate total time:

```text
Total ≈ Σ_keys [N(K) × S(K)] + Σ_methods E(i) + F
```

This is a **mental model**, not an official Spring timing formula. Do not mix figures from different machines or promise a fixed 10x threshold.

**A test conversion is beneficial when** it reduces `S(K)`, `N(K)`, or `E(i)` **without reducing necessary bug detection capability**. Measure both latency and mutation/regression coverage.

## 5. Rules for choosing: unit, slice, or keep full-context?

### 5.1. Choose a pure unit test when

The behavior under test is pure Java logic:

- business input validation without needing Spring MVC;
- text/money normalization;
- tax/discount/fee calculations;
- branch, fallback, or retry decisions independent of the framework;
- constructing command/value objects;
- business rules enforced prior to calling a persistence port.

Prefer **constructor injection** to instantiate the object and pass fakes/mocks directly. Pure unit tests **do not need** `@SpringBootTest`, `@ExtendWith(SpringExtension.class)`, `ApplicationContext`, or `@Autowired`.

Use Mockito when simulating a dependency; use fakes/real immutable objects when simpler. A unit test must verify **logical outcomes**, not merely `verify(mock)` on an unrelated call. Watch out for a classic pitfall: if a test only verifies what was stubbed, it can pass without executing any production behavior.

### 5.2. Choose `@WebMvcTest` when

The question concerns the **web layer**:

- URL route and HTTP method;
- JSON request/response binding;
- `@Valid`/Bean Validation;
- HTTP status, response headers, error mapping;
- controller exception resolution;
- Spring MVC converters/argument resolvers;
- request filters/security if genuinely loaded in the slice.

`@WebMvcTest(ProductController.class)` loads MVC infrastructure and restricts component scanning to specific web components. Regular `@Service`, `@Repository`, and many `@ConfigurationProperties` beans are excluded by default. Thus `@MockitoBean` is typically used to provide fake collaborators.

**Limitation:** mocking `ProductService` means the test **does not** prove `ProductService` works properly, that the service bean gets created, that JPA queries work, or that database commits succeed. If the web slice omits a custom `SecurityFilterChain`, do not call it a production security test.

### 5.3. Choose `@DataJpaTest` when

The question concerns **entity mapping, repository methods, or JPA queries**:

- entities persist and load by ID;
- derived queries match the entity mapping;
- JPA converters, cascades/relationships work;
- custom JPQL/SQL works against the provided datasource.

`@DataJpaTest` loads the required data JPA components, skipping services/controllers by default; typically it picks an **embedded test database** if H2/HSQL/Derby is on the classpath. By default, data JPA tests roll back transactions after each test. Remember that H2 **is not equivalent** to PostgreSQL/MySQL/Oracle in dialect, collation, JSONB, constraints, locking, sequences, or query planning. If the contract depends on the production database, use `@AutoConfigureTestDatabase(replace = NONE)` with a matching test datasource such as Testcontainers.

### 5.4. Keep `@SpringBootTest` when

The question concerns **how real layers connect together**:

- controller→service→repository via real bean injection;
- Boot auto-configuration, properties, and security policies;
- `@Transactional` proxies and bean lifecycles;
- multiple modules or conditional beans;
- filter/interceptor/configuration integration;
- a past regression caused by wiring that only appeared at startup or on the full path.

`@SpringBootTest + @AutoConfigureMockMvc` can suffice when you need the Spring container + MVC flow **without needing a real socket**. It does not open an HTTP server by default. If the goal covers network/ports/server filters/protocol boundaries, use `@SpringBootTest(webEnvironment=RANDOM_PORT)` with a real HTTP client.

## 6. An evidence-driven decision workflow

```text
Start from an existing full-context test
                   |
                   v
What must it prove?
                   |
       +-----------+-------------+
       |           |             |
    Java logic    MVC contract   JPA/query
       |           |             |
     Unit       @WebMvcTest   @DataJpaTest
       |           |             |
       +-----------+-------------+
                   |
                   v
Do any assertions still need cross-layer wiring?
              /           \
            Yes            No
            |               |
    Keep small full-context Review security/
    seam test             config/network risks
            |               |
            +-------+-------+
                    |
                    v
    Compare positive + negative evidence
                    |
                    v
     Run full suite, measure speed, QA
```

Practical steps:

1. Extract the **behaviors** protected by the old test. List endpoints, fields, constraints, queries, and integrations explicitly.
2. Classify each by the layer containing the risky implementation.
3. Write new unit/slice tests asserting both valid and invalid cases.
4. Confirm that **real** service/controller/repository beans still run together at least once in a full integration seam when layers need wiring verification.
5. Keep security/transaction/external integration tests where they guard real risks.
6. Run both old and new tests during migration, comparing pass/fail behavior and regression detection.
7. Remove redundant old tests only after sufficient evidence is in place.
8. Measure timings/counters, cache misses, context counts, memory, and CI stability.
9. Review for false positives from mocks, test data, and test profiles.
10. Never shrink test scope merely because a class is hard to boot; sometimes startup failures themselves are the bug you need to catch.

**You do not need a full-context test for every validation case.** Yet you also should not keep only unit tests and assume the whole application is wired correctly.

## 7. Runnable example: Product API with 4 layers of evidence

We build a mini Spring Boot application managing products. The goal is to show how to split a heavy full-context test suite into **4 clearly bounded suites**, while keeping one small full integration suite.

Production flow:

```text
HTTP JSON
    |
    v
ProductController (@Valid, /products)
    |
    v
ProductService (normalize + domain validation)
    |
    v
ProductRepository (Spring Data JPA)
    |
    v
Product entity / H2 test DB
```

In the example:

- Input DTO `CreateProductRequest(name, priceCents)`.
- Controller validates HTTP requests with `@NotBlank` and `@Positive`.
- `ProductService` validates domain invariants independently, trims `name`, and saves via repository.
- `ProductRepository` is a Spring Data JPA interface with derived queries.
- `ProductNotFoundException` maps to HTTP 404.
- `ProductView` is the JSON response record.
- H2 is the local test DB; no network or real credentials.
- There are **15 JUnit methods**: 5 pure unit, 5 MVC slice, 3 JPA slice, and 2 full-context seam.

**This setup omits Spring Security.** For an application with auth/CSRF, you must test policies explicitly in a security-enabled slice/full context; do not treat the demo's 2xx responses as a policy for a production API.

### 7.1. File tree

```text
build.gradle
settings.gradle
src/
├── main/
│   ├── java/com/example/testlayers/
│   │   ├── TestLayersApplication.java
│   │   ├── Product.java
│   │   ├── ProductRepository.java
│   │   ├── ProductService.java
│   │   ├── ProductController.java
│   │   ├── CreateProductRequest.java
│   │   ├── ProductView.java
│   │   └── ProductNotFoundException.java
│   └── resources/
│       └── application.properties
└── test/java/com/example/testlayers/
    ├── ProductServiceTest.java
    ├── ProductControllerWebMvcTest.java
    ├── ProductRepositoryDataJpaTest.java
    └── ProductFlowSpringBootTest.java
```

### 7.2. Gradle build

**File `build.gradle`**, Groovy DSL; requires Gradle/Java 17 toolchain and a compatible Gradle Wrapper:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**File `settings.gradle`:**

```groovy
rootProject.name = 'test-layers-demo'
```

The Spring Boot BOM manages versions of Spring Framework, JPA, Jackson, Hibernate Validator, H2, and JUnit. `spring-boot-starter-test` supplies the required JUnit Jupiter, AssertJ, and Mockito test dependencies. Spring Security is excluded from this project; if added later, MVC/security expectations would change.

### 7.3. Spring Boot application and H2 test schema

**File `src/main/java/com/example/testlayers/TestLayersApplication.java`:**

```java
package com.example.testlayers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestLayersApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestLayersApplication.class, args);
    }
}
```

**File `src/main/resources/application.properties`:**

```properties
# Local demo only; H2 is an embedded in-memory database.
spring.datasource.url=jdbc:h2:mem:layers;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
```

Using H2 is a **demo infrastructure-reduction choice**, not evidence for production dialects. In real projects, place test config in `src/test/resources/application-test.properties` or manage `@ActiveProfiles("test")` so a default demo DB never leaks into production. For this sample, `application.properties` intentionally sets H2 so all 4 test classes run locally. `spring.jpa.hibernate.ddl-auto=create-drop` generates the schema from entity metadata on context start and drops it on close; for real DBs, use Flyway/Liquibase migrations instead of demo `ddl-auto`.

## 8. Production code: JPA and domain services

### 8.1. Entity

**File `src/main/java/com/example/testlayers/Product.java`:**

```java
package com.example.testlayers;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private int priceCents;

    protected Product() {
        // For JPA
    }

    public Product(String name, int priceCents) {
        this.name = name;
        this.priceCents = priceCents;
    }

    // Explicit ID constructor is useful for unit test fixtures.
    public Product(Long id, String name, int priceCents) {
        this.id = id;
        this.name = name;
        this.priceCents = priceCents;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public int getPriceCents() {
        return priceCents;
    }
}
```

Note: the ID constructor is only for creating unit test fixtures; the repository uses the no-ID constructor so JPA generates the primary key. Exposing an ID constructor may not fit your production domain design; larger projects can use package-private fixtures/test factories or reflection test utilities. **Never invoke the explicit-ID constructor to pretend JPA persisted the entity** in repository slice tests.

### 8.2. Repository

**File `src/main/java/com/example/testlayers/ProductRepository.java`:**

```java
package com.example.testlayers;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Optional<Product> findByName(String name);

    List<Product> findByPriceCentsGreaterThan(int threshold);
}
```

Spring Data JPA implements derived queries at runtime. Unit tests mocking the repository **do not execute** these queries. `@DataJpaTest` with H2 actually runs JPA mapping and query generation.

### 8.3. DTOs

**File `src/main/java/com/example/testlayers/CreateProductRequest.java`:**

```java
package com.example.testlayers;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record CreateProductRequest(
        @NotBlank String name,
        @Positive int priceCents
) {}
```

**File `src/main/java/com/example/testlayers/ProductView.java`:**

```java
package com.example.testlayers;

public record ProductView(
        Long id,
        String name,
        int priceCents
) {}
```

Validation annotations on the request record are enforced by Spring MVC when the controller uses `@Valid @RequestBody` with a Jakarta Bean Validation provider on the classpath. For JSON inputs missing `name` or with `priceCents=0`, the MVC test must prove HTTP 400 **without invoking the service**.

### 8.4. Domain exception

**File `src/main/java/com/example/testlayers/ProductNotFoundException.java`:**

```java
package com.example.testlayers;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.NOT_FOUND)
public class ProductNotFoundException
        extends RuntimeException {

    public ProductNotFoundException(long id) {
        super("Product " + id + " not found");
    }
}
```

`@ResponseStatus` lets MVC map the exception to 404. It is not JPA configuration and needs no full application to test through the MVC slice when the mock service actually throws the exception class.

### 8.5. Service with domain behavior needing unit tests

**File `src/main/java/com/example/testlayers/ProductService.java`:**

```java
package com.example.testlayers;

import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public ProductView create(
            String name, int priceCents) {

        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        if (priceCents <= 0) {
            throw new IllegalArgumentException(
                    "priceCents must be positive");
        }

        Product saved = repository.save(
                new Product(name.trim(), priceCents));
        return toView(saved);
    }

    public ProductView find(long id) {
        if (id <= 0) {
            throw new ProductNotFoundException(id);
        }

        Product found = repository.findById(id)
                .orElseThrow(() ->
                        new ProductNotFoundException(id));
        return toView(found);
    }

    private static ProductView toView(Product product) {
        return new ProductView(
                product.getId(),
                product.getName(),
                product.getPriceCents());
    }
}
```

The service layer enforces business invariants even when not called over HTTP. This avoids relying solely on the controller's `@Valid`: a batch job or Kafka listener can still call the service directly.

The sample service has no explicit transactions; repository CRUD methods manage transactions via Spring Data JPA when needed. In a real application, if a method updates multiple rows atomically, `@Transactional` on the service and a dedicated integration test for commit/rollback/proxy behavior may be required.

### 8.6. REST Controller

**File `src/main/java/com/example/testlayers/ProductController.java`:**

```java
package com.example.testlayers;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ProductView create(
            @Valid @RequestBody CreateProductRequest request) {
        return service.create(
                request.name(), request.priceCents());
    }

    @GetMapping("/{id}")
    public ProductView get(@PathVariable long id) {
        return service.find(id);
    }
}
```

Here the controller **implements no domain rules**. It handles the HTTP path, JSON DTOs, MVC validation, status/serialization, and delegates to the service. Separating responsibilities gives unit tests and the MVC slice crisp boundaries.

## 9. Layer 1 — Unit tests for ProductService (5 methods)

**File `src/test/java/com/example/testlayers/ProductServiceTest.java`:**

```java
package com.example.testlayers;

import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ProductServiceTest {

    @Mock
    ProductRepository repository;

    @InjectMocks
    ProductService service;

    @Test
    void createTrimsNameAndReturnsSavedProduct() {
        when(repository.save(any(Product.class)))
                .thenAnswer(invocation -> {
                    Product input = invocation.getArgument(0);
                    return new Product(
                            41L,
                            input.getName(),
                            input.getPriceCents());
                });

        ProductView actual =
                service.create("  Notebook  ", 1200);

        ArgumentCaptor<Product> captor =
                ArgumentCaptor.forClass(Product.class);
        verify(repository).save(captor.capture());

        assertThat(captor.getValue().getName())
                .isEqualTo("Notebook");
        assertThat(captor.getValue().getPriceCents())
                .isEqualTo(1200);

        assertThat(actual)
                .isEqualTo(new ProductView(
                        41L, "Notebook", 1200));
    }

    @Test
    void blankNameIsRejectedBeforeRepositoryCall() {
        assertThatThrownBy(() ->
                service.create("   ", 100))
                .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(repository);
    }

    @Test
    void zeroPriceIsRejectedBeforeRepositoryCall() {
        assertThatThrownBy(() ->
                service.create("Pen", 0))
                .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(repository);
    }

    @Test
    void findingExistingProductMapsDto() {
        when(repository.findById(9L))
                .thenReturn(Optional.of(
                        new Product(9L, "Pen", 250)));

        ProductView actual = service.find(9L);

        assertThat(actual)
                .isEqualTo(new ProductView(
                        9L, "Pen", 250));
        verify(repository).findById(9L);
    }

    @Test
    void missingProductRaisesDomainException() {
        when(repository.findById(404L))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.find(404L))
                .isInstanceOf(ProductNotFoundException.class);

        verify(repository).findById(404L);
    }
}
```

### 9.1. Does this test need Spring?

**No.** `MockitoExtension` creates the mock repository, and `@InjectMocks` instantiates `ProductService` via constructor injection. There is no Spring `ApplicationContext`, no JPA, no H2, and no Spring TestContext cache lookup.

**Five conclusions proved:**

- `name` is trimmed **before `repository.save(...)`**.
- `price` is preserved accurately.
- Blank `name` causes no persistence call.
- Price 0 causes no persistence call.
- Existing/missing lookups map to the right DTO or domain exception.

The test **does not** prove Hibernate mapping, transactions, controller JSON, HTTP 404 status, or real dependency injection. Those proofs belong to the next layers.

### 9.2. Do not write a hollow unit test

A test like:

```java
when(repository.findById(9L)).thenReturn(Optional.empty());
verify(repository).findById(9L);
```

is an **anti-example**: it verifies a call never executed by the production service, so it fails—or if accidentally verifying a setup interaction, proves nothing. Always invoke `service.find(9L)` before verifying, assert the exception/outcome, and verify real behavior.

**A test that only verifies Mockito calls is insufficient when logical outcomes or domain invariants are what need protection.**

## 10. Layer 2 — `@WebMvcTest` for the controller (5 methods)

**File `src/test/java/com/example/testlayers/ProductControllerWebMvcTest.java`:**

```java
package com.example.testlayers;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductControllerWebMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    ProductService service;

    @Test
    void validCreateBindsJsonAndReturns201()
            throws Exception {
        when(service.create("Notebook", 1200))
                .thenReturn(new ProductView(
                        41L, "Notebook", 1200));

        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"Notebook\",\"priceCents\":1200}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(41))
                .andExpect(jsonPath("$.name")
                        .value("Notebook"))
                .andExpect(jsonPath("$.priceCents")
                        .value(1200));

        verify(service).create("Notebook", 1200);
    }

    @Test
    void blankNameIsRejectedWith400()
            throws Exception {
        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"  \",\"priceCents\":1200}"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void zeroPriceIsRejectedByHttpValidation()
            throws Exception {
        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"Notebook\",\"priceCents\":0}"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }

    @Test
    void validGetSerializesProductView()
            throws Exception {
        when(service.find(9L))
                .thenReturn(new ProductView(
                        9L, "Pen", 250));

        mvc.perform(get("/products/{id}", 9L))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(9))
                .andExpect(jsonPath("$.name").value("Pen"))
                .andExpect(jsonPath("$.priceCents")
                        .value(250));

        verify(service).find(9L);
    }

    @Test
    void domainNotFoundExceptionMapsTo404()
            throws Exception {
        when(service.find(404L))
                .thenThrow(
                    new ProductNotFoundException(404L));

        mvc.perform(get("/products/{id}", 404L))
                .andExpect(status().isNotFound());
    }
}
```

### 10.1. Why is mocking the service in an MVC slice sensible?

Because in this group **the question is the MVC contract**, not business logic. `ProductService` is replaced by a Mockito mock to:

- supply deterministic outputs;
- avoid needing a DataSource/JPA;
- force controller routing, `@Valid`, request body conversion, status codes, and response JSON to execute for real;
- check `verifyNoInteractions(service)` on negative validation cases, showing invalid requests are rejected before the service.

These tests **do not prove** that the service persists data or that constructor injection across the full app works. A small set of full-context tests below provides cross-layer evidence.

### 10.2. `@MockitoBean` is not `@Mock`

- `@Mock` from Mockito creates a mock in a JUnit unit test, **without replacing any bean in a Spring context**.
- `@MockitoBean` (Spring Framework 6.2, used in Boot 3.5) creates/overrides a bean inside the **test `ApplicationContext`**. It participates in Spring TestContext's context customizer/cache key.
- Legacy Spring Boot `@MockBean` was deprecated in Boot 3.4 in favor of `@MockitoBean` in Boot 3.5.
- Bean overrides can make slice/full-context cache keys differ. Avoid attaching different mock lists to every class out of convenience if they test the same MVC config.

**Never use `@MockitoBean` when the goal is verifying that the real bean was created/injected or its AOP advice runs.**

### 10.3. Note on Spring Security

The demo has no Security starter. In a real application with a `SecurityFilterChain`, `@WebMvcTest` can auto-configure Spring Security, yet custom configurations may not load in the slice the same way as in the full app. When security is under test:

- import the proper security configuration or use a security-enabled full-context test;
- use `spring-security-test` with `@WithMockUser`/`user(...)`/`csrf()` when appropriate;
- test anonymous, forbidden, and authorized paths;
- do not set `@AutoConfigureMockMvc(addFilters=false)` just to force 200 responses;
- never treat an MVC slice with fake security config as proof of production authorization.

## 11. Layer 3 — `@DataJpaTest` for persistence (3 methods)

**File `src/test/java/com/example/testlayers/ProductRepositoryDataJpaTest.java`:**

```java
package com.example.testlayers;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class ProductRepositoryDataJpaTest {

    @Autowired
    ProductRepository repository;

    @Test
    void entityIsPersistedAndFoundById() {
        Product saved = repository.saveAndFlush(
                new Product("Notebook", 1200));

        assertThat(saved.getId()).isNotNull();

        Product found = repository.findById(
                saved.getId()).orElseThrow();

        assertThat(found.getName())
                .isEqualTo("Notebook");
        assertThat(found.getPriceCents())
                .isEqualTo(1200);
    }

    @Test
    void derivedFindByNameQueryFindsRow() {
        repository.saveAndFlush(
                new Product("Pen", 250));

        Product found = repository.findByName("Pen")
                .orElseThrow();

        assertThat(found.getName()).isEqualTo("Pen");
        assertThat(found.getPriceCents())
                .isEqualTo(250);
    }

    @Test
    void greaterThanQueryFiltersRows() {
        repository.saveAndFlush(
                new Product("Pen", 250));
        repository.saveAndFlush(
                new Product("Notebook", 1200));

        assertThat(repository
                .findByPriceCentsGreaterThan(500))
                .extracting(Product::getName)
                .containsExactly("Notebook");
    }
}
```

### 11.1. What `@DataJpaTest` actually proves

- The JPA entity can be persisted and read on the **H2** test DB.
- Generated IDs and basic column mappings work.
- Spring Data derived query `findByName` works.
- `findByPriceCentsGreaterThan` generates and runs the query accurately in that environment.
- Spring/JPA transaction infrastructure for the slice loads cleanly.

Spring Boot documentation states the JPA slice is transactional by default and rolls back after every method. `@DirtiesContext` is unnecessary after each test just to prevent leftover data from the prior method, provided test transaction cleanup runs and code does not write via a separate resource or thread.

### 11.2. H2 does not prove all PostgreSQL/MySQL behavior

If production queries use JSONB, vendor-specific SQL, locking, collation, generated columns, migrations, or database-specific constraints, an H2 slice result is **insufficient**. When such evidence is needed, use Testcontainers with the matching engine/version and appropriate datasource/test database replacement settings.

A repository can pass on H2 and fail on PostgreSQL due to SQL dialect, reserved word names, timezones, or transaction isolation. Never delete a real-DB integration test just because `@DataJpaTest`(H2) is green.

### 11.3. ID constructor is for fixtures only

The JPA slice uses `new Product("...", price)` with a null ID so the database generates the ID. `new Product(9L, ...)` is strictly for unit fixtures and **must not** be used to claim an entity was persisted.

## 12. Layer 4 — Keeping a small full-context seam test (2 methods)

**File `src/test/java/com/example/testlayers/ProductFlowSpringBootTest.java`:**

```java
package com.example.testlayers;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class ProductFlowSpringBootTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ProductRepository repository;

    @Test
    void postThenGetUsesRealControllerServiceAndJpa()
            throws Exception {
        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"  Notebook  \",\"priceCents\":1200}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name")
                        .value("Notebook"))
                .andExpect(jsonPath("$.priceCents")
                        .value(1200));

        Product stored = repository
                .findByName("Notebook")
                .orElseThrow();

        mvc.perform(get("/products/{id}", stored.getId()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id")
                        .value(stored.getId()))
                .andExpect(jsonPath("$.name")
                        .value("Notebook"))
                .andExpect(jsonPath("$.priceCents")
                        .value(1200));
    }

    @Test
    void invalidJsonIsRejectedBeforePersistence()
            throws Exception {
        long before = repository.count();

        mvc.perform(post("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"name\":\"  \",\"priceCents\":0}"))
                .andExpect(status().isBadRequest());

        assertThat(repository.count()).isEqualTo(before);
    }
}
```

**These two tests are retained because they prove what isolated unit/MVC/JPA slices do not:**

- Spring Boot instantiates the **real** controller, service, and repository.
- An HTTP request dispatches through MockMvc to the real controller.
- The controller invokes the real `ProductService`, normalizing input.
- `ProductService` invokes the real `ProductRepository`, writing/reading real H2.
- The `GET` path fetches the persisted entity and serializes the response.
- Invalid input is rejected by MVC validation before reaching persistence.

This is a **cross-layer seam test**, not dozens of full-context tests repeating the same behavior with minor input variations.

### 12.1. Why does `@Transactional` roll back here?

In the default `@SpringBootTest` (`webEnvironment=MOCK`) with `@AutoConfigureMockMvc`, MockMvc requests execute **on the same test thread** rather than over TCP on a separate server thread. Spring's TestContext transaction wraps the test thread; repository operations in the demo join the test transaction, and the framework rolls it back at the end of each test.

**Important warning:** when switching to `@SpringBootTest(webEnvironment=RANDOM_PORT)` and sending real HTTP requests, the client/test thread and server thread **do not** share a transaction. `@Transactional` on the test **does not** roll back writes committed by the server. Explicit DB cleanup or isolated data/schemas are needed in that mode.

### 12.2. `@SpringBootTest` is not live HTTP by default

By default `@SpringBootTest` uses a mock web environment when Spring MVC is on the classpath, without opening an embedded HTTP socket. Add `@AutoConfigureMockMvc` to inject `MockMvc`. Only `RANDOM_PORT`/`DEFINED_PORT` makes the embedded server listen on a real port.

This matters when reviewing conversions from full-context to slice tests: **if the old test only used MockMvc, converting to `@WebMvcTest` preserves MVC routing evidence**, yet a seam test is still needed to prove real wiring. If the old test used real HTTP/sockets/TLS, switching to MockMvc **loses another boundary**.

## 13. Auditing evidence after splitting tests

| Requirement/behavior | Unit | MVC slice | JPA slice | Full seam |
|---|:---:|:---:|:---:|:---:|
| Blank name rejected by service | ✓ | — | — | Possible, at different boundary |
| Price 0 rejected by service | ✓ | — | — | Possible |
| Service trims name | ✓ | Service mocked, no | — | ✓ (real path) |
| `POST /products` → 201 | — | ✓ | — | ✓ |
| JSON response shape | — | ✓ | — | ✓ |
| `@Valid` invalid request → 400 | — | ✓ | — | ✓ |
| Domain exception → HTTP 404 | — | ✓ | — | Can be added if needed |
| Generated JPA id/columns | — | — | ✓ | ✓ |
| Spring Data derived queries | — | — | ✓ | `GET` path exercises partially |
| Controller→service bean injection | — | Service mocked | — | ✓ |
| Service→repository real persistence | Repo mocked | — | Repo only | ✓ |
| Real TCP servlet server | — | — | — | — |
| Production DB dialect/migrations | — | — | Only if matching DB used | H2 demo, no |
| Spring Security auth/CSRF | — | No dependency in demo | — | Not in demo |
| External HTTP/Kafka/cross-system transactions | — | — | — | — |

A checkmark ✓ means **verified in the example within the described scope**, not that every edge case is proved. A dash “—” means unverified at that layer; if it is an acceptance criterion, add an appropriate test. A single test can contribute to multiple requirements, but never extrapolate beyond what actually ran.

### 13.1. Expected results after migration

| Suite | Test methods | Context | Objective |
|---|---:|---|---|
| `ProductServiceTest` | 5 | No Spring | Domain behavior |
| `ProductControllerWebMvcTest` | 5 | MVC slice | HTTP binding/validation/status |
| `ProductRepositoryDataJpaTest` | 3 | JPA slice/H2 | ORM queries |
| `ProductFlowSpringBootTest` | 2 | Full context + MockMvc/H2 | Cross-layer wiring |
| **Total** | **15** | 3 Spring context types + unit | Layered evidence |

This is an **expected test plan** based on the sample code. Actual executed/passed counts must come from the Gradle/JUnit report after running; authoring does not assume execution.

## 14. Running the test suites

**Linux/macOS** with Gradle Wrapper if generated for the project:

```bash
./gradlew test --tests "com.example.testlayers.ProductServiceTest"
./gradlew test --tests "com.example.testlayers.ProductControllerWebMvcTest"
./gradlew test --tests "com.example.testlayers.ProductRepositoryDataJpaTest"
./gradlew test --tests "com.example.testlayers.ProductFlowSpringBootTest"

# All tests in the project:
./gradlew test
```

**Windows PowerShell**:

```powershell
.\gradlew.bat test --tests "com.example.testlayers.ProductServiceTest"
.\gradlew.bat test --tests "com.example.testlayers.ProductControllerWebMvcTest"
.\gradlew.bat test --tests "com.example.testlayers.ProductRepositoryDataJpaTest"
.\gradlew.bat test --tests "com.example.testlayers.ProductFlowSpringBootTest"
.\gradlew.bat test
```

If the project uses Maven, it needs a `pom.xml` with Spring Boot 3.5 parent/BOM, corresponding starters, H2, and compatible JUnit Platform/Surefire; then select tests with Maven Wrapper, e.g. `./mvnw -Dtest=ProductControllerWebMvcTest test`. This is an illustrative command for a **Maven project that has a wrapper**, not a requirement to maintain both Gradle and Maven.

When running:

- Verify Java 17+ is used by the test worker.
- Ensure H2 is on the test runtime classpath.
- Inspect reports in `build/test-results/test` and `build/reports/tests/test` (standard Gradle paths).
- Confirm expected **15 executed**, not just `BUILD SUCCESSFUL` from cache/`UP-TO-DATE`.
- Never run only `ProductServiceTest` and claim MVC/JPA/full paths were verified.

## 15. When must a full-context test NOT be replaced?

### 15.1. Security contracts

A web slice with a mocked service might return 200 without loading the production `SecurityFilterChain`, or the test might disable filters to avoid 403. That fails to test authorization, JWT decoding, CSRF, CORS/filter ordering, and role mappings. Keep **security-enabled tests** with the real security config or full context; add real HTTP integration when required.

**Never use `@AutoConfigureMockMvc(addFilters=false)` as a trick to make tests green** when the original full test verified request authentication/authorization.

### 15.2. Transaction proxy/propagation and persistence consistency

A unit test calling `new Service(repositoryMock)` **does not run Spring AOP proxies**. If a bug resides in `@Transactional`, `@Cacheable`, `@Retryable`, Spring Security method advice, or aspect ordering, a pure unit test cannot catch it. A JPA slice verifies repo behavior without verifying the service transaction boundary. Keep an integration test with the Spring-managed service bean and an appropriate DB.

### 15.3. Auto-configuration and configuration properties

A unit test exercising a class constructor does not prove Spring Boot binds `@ConfigurationProperties`, validation constraints, or `@ConditionalOnProperty` conditions. When testing custom starters, `ApplicationContextRunner` is a lightweight, suitable choice; when a bug lives in full `SpringApplication` ConfigData/profile loading, test the whole app.

### 15.4. External systems and protocol behavior

Mocking `RestClient` or `KafkaTemplate` does not prove HTTP/TLS, serialization over real transport, or Kafka producer ACKs. If old tests used Testcontainers/PostgreSQL/Kafka and caught bugs in real interactions, do not replace all of them with fakes across every suite. Keep enough integration tests for critical protocol boundaries and failure modes.

### 15.5. Real HTTP / Servlet container

MockMvc runs in-process. When verifying server ports, compression, TLS, real HTTP filters, socket requests/responses, or reverse-proxy integration, use `RANDOM_PORT` + an HTTP client (or a higher environment). An MVC slice does not cover the transport layer.

### 15.6. Past cross-layer bugs

If bugs previously surfaced from unscanned beans, mis-injected repository types, mismatched DTO schemas, or incompatible HTTP exception mappings from services, deleting all full-context tests removes your regression guard. One well-scoped seam test is usually far cheaper than debugging a production incident.

## 16. Cache reuse can make optimization outcomes counterintuitive

### 16.1. Test class count alone doesn't dictate startup count

Suppose 30 full-context classes share **one** cache key: after the first startup, most tests get a cache hit. Replacing them with 30 `@WebMvcTest` classes having 30 distinct `@MockitoBean` combinations creates 30 cache keys, each requiring an MVC context startup.

Even though an MVC context is lighter than a full context, multiplying startups can make the suite **no faster**. Therefore:

- Keep `@WebMvcTest` classes truly equivalent in config to enable cache hits.
- Avoid unnecessary unique inline properties/`@ActiveProfiles`.
- Use consistent mock bean names/qualifiers when targeting the same bean.
- Do not put `@DirtiesContext` on every class.
- Do not raise cache max size blindly just because a suite is slow.
- Measure both *context cold starts* and *method execution* times.

### 16.2. Do not force cache sharing when behaviors differ

If a service operates in two modes controlled by properties, keeping two contexts is right. If a JPA test needs real PostgreSQL while a controller slice only needs a fake service, not every test should share a single full context.

**Correctness and isolation matter more than cache hit rate.** Forcing tests onto identical config can introduce shared mutable singleton state or hide differing behaviors.

### 16.3. Static cache does not cross JVM forks

The Spring TestContext cache lives inside a single test worker JVM. Gradle `maxParallelForks`, `forkEvery`, and Maven Surefire fork settings can prevent classes in separate processes from sharing the cache. Never confuse the Gradle build cache with the Spring `ApplicationContext` cache.

## 17. Proving performance through accurate measurement

### 17.1. Prepare a baseline

Before refactoring, record on the same CI runner/config:

- Total wall-clock test time, cold and warm runs.
- JUnit executed/passed/failed/skipped counts.
- Actual context startup count.
- Spring context cache hits/misses and current size.
- Number of unique test configuration keys if instrumentation is available.
- Gradle/Maven fork/parallel settings.
- External setup time: H2/JPA, Testcontainers image pulls, migrations, server startup.
- Peak memory, CPU load, and flaky failures.

Spring Framework TestContext supports logging statistics under `org.springframework.test.context.cache` at `DEBUG` level.

**Example with Gradle test worker JVM:**

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()
    systemProperty 'logging.level.org.springframework.test.context.cache',
            'DEBUG'
}
```

This is an optional snippet. Logging configuration depends on the test logging backend; in some setups you must configure the logger in Logback/Log4j2 test config to see early Spring TestContext cache logs. Avoid leaving DEBUG on for all CI jobs, as verbose output adds noise and I/O overhead.

### 17.2. Measure after splitting tests

Re-run the **same scenarios** and environment:

1. Verify all assertions and negative cases were migrated or retained.
2. Confirm all 15 demo tests actually executed.
3. Measure context load times, per-class runtimes, and total suite duration.
4. Observe whether cache hits/misses shifted due to slice configurations.
5. Compare memory and flakiness.
6. If speed improved yet a requirement lost its guard, **the migration failed**.
7. If there was no speedup, inspect JPA/H2 startup, Gradle forks, unique cache keys, or `@DirtiesContext`.
8. Adjust test levels based on evidence, not a single local laptop benchmark.

### 17.3. Do not mandate a fixed unit/slice/full ratio

The test pyramid is a cost/boundary guideline, not a law claiming "90% unit, 10% integration" fits every project. An API heavy on data consistency and security needs more integration tests; a pure calculation library can be almost entirely unit tests. Better metrics are **critical risks covered and CI feedback latency**.

## 18. Step-by-step migration checklist for a real PR

When encountering a full-context test class with 30 methods:

1. **Read the objective of each method.** Tabulate behaviors, assertions, dependencies, and risks.
2. **Extract pure logic tests** into JUnit + Mockito/fakes, dropping Spring annotations.
3. **Extract controller serialization/validation** into `@WebMvcTest` with mocked services.
4. **Extract repository mapping/queries** into `@DataJpaTest`; pick the DB engine based on requirements.
5. **Keep minimal full-context paths that add cross-layer value**; do not keep extras just out of habit.
6. **Add security/transaction/configuration tests** if the old tests covered them.
7. **Run old and new tests side by side during transition** if possible and verify negative paths too.
8. **Fix fixtures**, never weakening production security/transaction config just to make a slice pass.
9. **Check test runner counts** to confirm CI executes all new classes.
10. **Measure timings**, context cache stats, forks, memory, and flakiness.
11. **Delete redundant old tests** only after parity is proven; review code/diffs carefully.
12. **Name tests by layer and contract** so future maintainers never mistake their scope.

### 18.1. Sample conversion table

| Old full-context test | Conversion | Evidence to preserve |
|---|---|---|
| Checks `if (price <= 0)` | `ProductServiceTest` | Exception and no repository call |
| Checks POST JSON and `@Valid` | `ProductControllerWebMvcTest` | 201/400/response JSON |
| Checks JPQL/derived finder | `ProductRepositoryDataJpaTest` | Real row persist/query |
| Checks controller → service → JPA | `ProductFlowSpringBootTest` | Real beans and database write/read |
| Checks JWT/roles/CSRF | Keep security-focused integration | Anonymous/USER/admin denied/allowed |
| Checks random port socket | Keep `RANDOM_PORT` smoke | Real HTTP client/server boundary |
| Checks DB transaction across service | Keep transaction integration | Commit/rollback/proxy behavior |

Never delete the last rows in the table just because another slice test is green: they verify completely different boundaries.

## 19. Common mistakes when shrinking scope

| Anti-pattern | Why it creates false confidence | Better approach |
|---|---|---|
| Converting all `@SpringBootTest` to unit tests | Loses framework wiring | Keep seam integration tests |
| Mocking repository and asserting SQL query works | SQL never runs | `@DataJpaTest` + real DB |
| `@WebMvcTest` with service mock claiming service was tested | Service never runs | Unit service + full seam |
| `@MockitoBean` on every bean just to boot context | Loses real bean behavior | Mock only outside test boundary |
| Picking `@WebMvcTest` to verify `@Transactional` | No service proxy/DB path | Full service integration |
| Disabling security filters so POST returns 201 | Skips CSRF/auth | Keep security-enabled tests |
| H2 passes so claiming Postgres production compatibility | Dialects differ | PostgreSQL Testcontainers tests |
| Calling `@SpringBootTest(MOCK)` a real HTTP E2E | Opens no socket | `RANDOM_PORT` HTTP client |
| `@Transactional` on `RANDOM_PORT` test expecting server rollback | Test/server threads differ | Explicit cleanup/isolated DB |
| Putting `@DirtiesContext` on every slice | Cache constantly evicted | Reset state at the proper resource |
| Random profile/inline property per test class | Many cache keys | Standardize equivalent configs |
| Lots of micro-tests, zero negative cases | Misses forbidden behaviors | Both positive and negative tests |
| Full-context test only asserting a bean exists | Low bug-detection value | Test real cross-layer behavior |
| Test runner skips integration classes while CI stays green | Silent loss of coverage | Assert executed counts |
| Calling Mockito `verify` without invoking production method | Proves nothing | Invoke SUT, assert result/side effects |
| Mocking authentication and claiming JWT signature is valid | Bypasses verification path | Real decoder/token integration |
| Skipping migrations in DB tests | Schema diverges from production | Flyway/Liquibase migration tests |
| Optimizing from a single local benchmark | Unreliable conclusion | CI baseline/repeatable measurements |

## 20. Review questions on "sufficient evidence"

When reviewing a PR converting 25 full-context tests to unit/slice tests, ask:

**Question 1. What bugs did the old test catch previously?** If it caught wiring bugs, the migration must not eliminate all wiring tests.

**Question 2. If `@Valid` is deleted, which test turns red?** MVC slice/full MockMvc must catch that invalid requests no longer return 400.

**Question 3. If `trim()` is removed from `ProductService`, which test turns red?** The unit service test asserting captured input + `ProductView` outcome.

**Question 4. If a repository query targets the wrong field, which test turns red?** The JPA slice running real derived/custom queries.

**Question 5. If `@Service` is removed or the wrong repository is injected, which test turns red?** The full-context seam test booting and calling real beans.

**Question 6. If an admin endpoint is exposed to anonymous users, which test turns red?** A security-enabled integration test enforcing the policy.

**Question 7. If an HTTP handler works in MockMvc yet fails on a real server port, which test turns red?** A `RANDOM_PORT` HTTP smoke test.

**Question 8. If transaction rollback fails, which test turns red?** A transaction integration test, not a mocked repository.

**Question 9. Did the context count actually drop?** Check cache logs and unique configs; 25 unit tests need zero contexts, whereas 25 `@WebMvcTest`s with differing mocks still spawn many context keys.

**Question 10. How much faster is it and under what conditions?** Compare cold/warm runs on the same CI worker executing the same tests—never cherry-pick.

## 21. Practice exercises with answers

### Exercise A. A discount calculation test

A test checks `PriceService.discount(1200, 10)` in pure Java, yet currently uses `@SpringBootTest` to autowire the service. Should it be converted?

**Yes, likely.** If the logic does not depend on Spring advice/config and dependencies can be faked, a pure unit test fits well. If the method relies on `@Transactional`/`@Cacheable` as part of its contract, keep a separate test for that advice.

### Exercise B. MVC validation

A test POSTing invalid `price=0` uses full-context and only asserts 400. Is switching to `@WebMvcTest` sufficient?

**Usually yes**, provided the MVC slice loads the right validators/converters and relevant security config. Use a negative assertion confirming the mocked controller collaborator/service **is not called**. Keep a full seam test if real wiring also needs checking.

### Exercise C. Repository SQL

A test for `findByPriceCentsGreaterThan` is converted to a Mockito repository mock stubbed to return the expected list. Is that sufficient?

**No.** The real query never runs; use a JPA slice or real DB test.

### Exercise D. `@WebMvcTest` missing a service bean

The slice cannot find `ProductService`, so the test class fails startup. Should the whole test revert to full-context?

**Not necessarily.** If only testing MVC, add `@MockitoBean ProductService`. If the test genuinely requires the real service, keep a full-context test with the real service.

### Exercise E. A 3-minute integration suite

Deleting everything and replacing it with 100 pure unit tests brings the suite down to 2 seconds. Is that a success?

**Not without further evidence.** You must prove all previously guarded contracts remain tested—especially cross-layer wiring, DB dialect, auth, and external integrations. Speed never compensates for lost regression coverage.

### Exercise F. `@SpringBootTest` without `RANDOM_PORT`

A test injects `MockMvc` and sends a `GET`. Does it exercise a TCP socket to embedded Tomcat?

**No.** MockMvc runs in-process. `RANDOM_PORT` and a real HTTP client are needed to test the servlet server/network boundary.

### Exercise G. `@Transactional` on a real HTTP test

A `RANDOM_PORT` test POSTs to create a DB record; adding `@Transactional` to the test guarantees the record rolls back afterward, right?

**Not guaranteed.** The test thread transaction does not cover the server thread transaction. Use DB cleanup or an isolated schema.

### Exercise H. Differing cache keys from `@MockitoBean`

Two MVC slices test the same controller with different mock field names/qualifiers. Why did startups increase?

**Bean override context customizers** participate in the key, creating separate cache entries. Standardize mock targets/field names when configurations are genuinely equivalent.

### Exercise I. When is a full context faster than a slice?

When the full context is already warm/cached in the same JVM while multiple unique slice contexts cold-start, total runtime may fail to improve after migration. **Measure** rather than trusting annotation names blindly.

### Exercise J. Moving full-context to an H2 JPA slice

Production runs a PostgreSQL JSONB query. Is a green H2 slice enough?

**No.** H2 does not prove PostgreSQL dialect/JSONB behavior. Keep a Postgres Testcontainers integration test for that query.

### Exercise K. Mock service, controller returns 201

Does that prove `repository.save` actually executed?

**No.** The MVC slice only proves controller dispatch/JSON/status and calling the mock. Full seam/DB tests prove real persistence.

### Exercise L. Skipped integration tests

The suite reports `BUILD SUCCESSFUL`, yet only 13/15 methods executed. Can you sign off migration QA PASS?

**No.** Investigate why 2 tests were skipped (filters, tags, context failure, `@Disabled`, test selection) before declaring full evidence.

## 22. Migration completion checklist

- [ ] Documented the behaviors guarded by the old full-context tests.
- [ ] Every behavior has an owning test at the right layer.
- [ ] Unit tests avoid starting a Spring context unnecessarily.
- [ ] Unit tests invoke production methods and assert real outcomes/side effects, not just mock setups.
- [ ] MVC slice tests verify routes, JSON, validation, errors, and statuses.
- [ ] `@MockitoBean` is used only for collaborators outside the MVC boundary.
- [ ] JPA slice tests use a real DB/queries, with at least one negative/boundary case when appropriate.
- [ ] Production DB-specific behavior has a real-dialect test when needed.
- [ ] A full-context seam test covers critical bean wiring.
- [ ] If security exists, tests exercise the real filter/authorization chain.
- [ ] If CSRF exists, valid/missing/invalid token scenarios match policy.
- [ ] If AOP/transaction/caching advice exists, tests run through real Spring proxies.
- [ ] If external APIs/brokers exist, appropriate contract/integration tests exist.
- [ ] If testing real HTTP, `RANDOM_PORT` and a real HTTP client are used.
- [ ] Not assuming `@Transactional` on a `RANDOM_PORT` test rolls back server-thread writes.
- [ ] Not altering production beans/security config just to make a slice start.
- [ ] Test fixtures are independent, with DB cleanup/rollback scoped properly.
- [ ] TestContext cache keys/profiles/inline props/mock customizers reviewed.
- [ ] Not applying `@DirtiesContext` indiscriminately; proper state resets in place.
- [ ] CI runs unit, MVC slice, JPA slice, seam, and required security suites.
- [ ] Both positive and negative assertions exist for critical requirements.
- [ ] Not treating green H2 tests as proof for every production dialect.
- [ ] Verified actual executed/passed/failed/skipped counts, not just a green build.
- [ ] Measured startup/cache hits/misses/cold/warm wall time in the same environment.
- [ ] Refactor reduces cost without sacrificing regression detection.
- [ ] Java 17 / Spring Boot 3.5 / Spring Framework 6 imports and versions are consistent.
- [ ] Tests expose no credentials, production data, or customer PII.
- [ ] Test names reflect their layer: Unit, WebMvc, DataJpa, SpringBoot seam.
- [ ] PR clearly documents which tests were replaced, which were kept, and why evidence is sufficient.

## 23. Conclusion

**Replacing full-context tests with slice or unit tests is a decision about evidence boundaries, not merely a performance tweak.**

- Use **unit tests** for domain behavior and branching needing no Spring.
- Use **MVC slices** for controller routes, JSON, validation, and HTTP contracts, mocking the service when appropriate.
- Use **JPA slices** for real entity mapping and queries against an appropriate test database.
- Keep **full-context seam tests** when you need to prove real Spring beans wire together across controller/service/repository and policies operate together.
- Keep **real HTTP/security/transaction/external integration tests** whenever those boundaries belong to acceptance criteria.
- Watch the **Spring TestContext cache**: many tests with the same key reuse one context, whereas unique slice configs can increase startups.
- Measure execution time, memory, and failures **alongside** coverage and negative evidence.

The Java 17+/Spring Boot 3.5 example contains 15 JUnit methods across four layers. They demonstrate that narrowing test scope can be **systematic and verifiable**: service rules run without Spring, MVC/JPA run in focused contexts, and a small seam suite protects cross-layer wiring. This article does not claim the example was compiled/executed on a specific machine; run the build and inspect test reports before using results as project evidence.

## Official Documentation

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, MockMvc, server modes, transaction rollback scope.
- [Spring Boot 3.5 — Test Slices Appendix](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): default auto-configurations per slice.
- [Spring Boot 3.5 — Testing How-to](https://docs.spring.io/spring-boot/3.5/how-to/testing.html): custom MVC config, Spring Security integration in slice tests.
- [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): static cache key, `maxSize`, LRU, DEBUG stats.
- [Spring Framework 6.2 — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): mock bean overrides, cache key qualifiers.
- [Spring Framework 6.2 — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): transactional test rollback rules.
- [Spring Boot 3.5 — DataJpaTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/orm/jpa/DataJpaTest.html): JPA slice auto-config, embedded DB, rollback.
- [Spring Boot 3.5 — WebMvcTest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html): MVC slice filters, MockMvc, and controller scans.
- [Spring Boot 3.5 — MockBean deprecation API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): `@MockBean` deprecated in favor of `@MockitoBean`.
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html): derived query generation and parsing.
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/): Jupiter methods/annotations and test execution.
