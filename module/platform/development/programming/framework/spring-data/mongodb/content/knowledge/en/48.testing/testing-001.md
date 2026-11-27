# Choosing Unit Tests, Repository Tests, and Integration Tests by Objective

Testing a **Spring Data MongoDB** application does not have a single one-size-fits-all choice. An email normalization rule can be tested with Java and Mockito in a few milliseconds, but knowing whether a **MongoRepository** queries correctly by method name, or whether a **MongoTemplate** aggregation runs on real MongoDB, requires using MongoDB. When you need to verify the service, transactions, and configuration of the whole application, you need to expand the scope to an **integration test**.

This lesson in the **Testing** chapter guides you on how to choose **unit tests**, **repository tests**, and **integration tests** by verification objective, design examples for **SPRING_DATA_MONGODB**, organize test data, and avoid green tests that fail to catch production bugs.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Classify the risk to verify into **business rules**, **mapping and queries**, or **coordinated behavior across multiple components**.
2. Choose the smallest test scope sufficient to detect the target defect.
3. Write **unit tests** for a service using a MongoDB repository with JUnit 5 and Mockito, without starting a Spring context.
4. Write **repository tests** using **@DataMongoTest** combined with real MongoDB via Testcontainers.
5. Write **integration tests** using **@SpringBootTest** to verify that the service, repository, configuration, and MongoDB work together.
6. Determine when you must test **indexes, aggregations, transactions, optimistic locking, and reactive streams**.

## 2. Start from the Question: “What Do We Want to Prove?”

| Objective to verify | Preferred test level | Real MongoDB needed? | Why? |
| --- | --- | --- | --- |
| String normalization, input validation, business calculations | **Unit test** | No | Behavior lives in plain Java and can be isolated via mock dependencies. |
| Service calls repository under right conditions, reacts when dependency fails | **Unit test** | No | Control inputs, results, exceptions, and interactions with mocks. |
| **findByEmail**, **Criteria**, **Query**, **Aggregation** build the right query | **Repository test** | Yes | Must verify mapping and how MongoDB executes the query. |
| **@Document**, **@Field**, converter, BSON, how **_id** is mapped | **Repository test** | Yes | Mockito does not simulate BSON conversion and mapping mechanisms. |
| Unique index creation, duplicate key checks, collation | **Repository test** | Yes | Requires the MongoDB engine and actual indexes. |
| Service calls multiple repositories, events, converters, or transaction manager | **Integration test** | Yes, if the flow uses MongoDB | Must verify component boundaries and Spring configuration. |
| HTTP endpoint → service → repository → MongoDB | **Integration test** | Yes, when verifying real persistence | Tests wiring, serialization, validation, and exception handling together. |
| Atomic update, concurrent write, transaction, read concern | **Repository / Integration test** | Yes, with an appropriate topology | This is MongoDB behavior and cannot be concluded from mocks. |
| Backpressure, subscription cancellation, retry with ReactiveMongoTemplate | **Unit + Integration test** | Depends on behavior | Use StepVerifier for operators; real DB to test queries and I/O. |
| Performance of indexes and aggregations on large data | Separate **Performance / load test** | Yes, representative data and environment | Functional tests do not prove production performance. |

**Rule:** classify by the **evidence required**, not by the name of the class under test. A test for a service that mocks the entire **MongoRepository** is still a unit test; it does **not** verify MongoDB queries.

~~~mermaid
flowchart TD
    A["What needs to be proved?"] --> B{"Can the Java rule be separated from the database?"}
    B -- "Yes" --> C["Unit test: JUnit + Mockito"]
    B -- "No" --> D{"Does almost the entire application need to run?"}
    D -- "No" --> E["Repository test: @DataMongoTest + real MongoDB"]
    D -- "Yes" --> F["Integration test: @SpringBootTest + real MongoDB"]
    E --> G["Special features: compatible topology and server version"]
    F --> G
~~~

## 3. A Running Example

Suppose a customer management application allows registering an email. The business requirements are:

- Email is **trimmed** and converted to lowercase before writing.
- Blank emails are rejected.
- An email can only be registered once; MongoDB must enforce this with a **unique index**.
- New customers are created with status **ACTIVE**.
- Customers can be queried by status, sorted by email ascending.

**Entity — Customer.java:**

~~~java
package example.customer;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class Customer {
    @Id
    private String id;

    @Indexed(unique = true)
    private String email;

    private String status;

    protected Customer() {
        // For the mapping mechanism.
    }

    public Customer(String email, String status) {
        this.email = email;
        this.status = status;
    }

    public String getId() { return id; }
    public String getEmail() { return email; }
    public String getStatus() { return status; }
}
~~~

**Repository — CustomerRepository.java:**

~~~java
package example.customer;

import java.util.List;
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<Customer, String> {

    boolean existsByEmail(String email);

    Optional<Customer> findByEmail(String email);

    List<Customer> findByStatusOrderByEmailAsc(String status);
}
~~~

**Service — CustomerRegistrationService.java:**

~~~java
package example.customer;

import java.util.Locale;
import org.springframework.stereotype.Service;

@Service
public class CustomerRegistrationService {
    private final CustomerRepository repository;

    public CustomerRegistrationService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer register(String rawEmail) {
        if (rawEmail == null || rawEmail.isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }

        String email = rawEmail.trim().toLowerCase(Locale.ROOT);
        if (repository.existsByEmail(email)) {
            throw new IllegalStateException("Email already registered");
        }

        return repository.save(new Customer(email, "ACTIVE"));
    }
}
~~~

The **existsByEmail** check helps return a business error early, but **does not prevent a race condition** when two requests simultaneously check an email that does not exist yet. A **unique index in MongoDB** is the final line of defense against duplicate writes. A real-world application needs to map **DuplicateKeyException** to an appropriate domain error or HTTP response.

The examples below use **JUnit Jupiter**, **Mockito**, **Spring Boot 3.x / Spring Data MongoDB 4.x**, and **Testcontainers 1.x** to illustrate concrete imports and classes. If your project uses a different major version, check the Testcontainers packages, connection properties, and compatible libraries against your active BOM before copying.

## 4. Unit Test: Verify Business Logic Without Starting MongoDB

Unit tests focus on the service's decisions—for example, blank emails are rejected before calling the repository; strings are normalized; already-registered emails throw an exception; and new customers have status **ACTIVE**.

~~~java
package example.customer;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CustomerRegistrationServiceTest {

    @Mock
    CustomerRepository repository;

    @InjectMocks
    CustomerRegistrationService service;

    @Test
    void shouldNormalizeEmailAndSaveActiveCustomer() {
        when(repository.existsByEmail("ada@example.com")).thenReturn(false);
        when(repository.save(any(Customer.class)))
            .thenAnswer(invocation -> invocation.getArgument(0));

        Customer result = service.register(" Ada@Example.COM ");

        ArgumentCaptor<Customer> captor =
            ArgumentCaptor.forClass(Customer.class);
        verify(repository).save(captor.capture());

        assertEquals("ada@example.com", captor.getValue().getEmail());
        assertEquals("ACTIVE", captor.getValue().getStatus());
        assertEquals("ada@example.com", result.getEmail());
    }

    @Test
    void shouldRejectBlankEmailWithoutAccessingDatabase() {
        assertThrows(IllegalArgumentException.class,
            () -> service.register("   "));
        verifyNoInteractions(repository);
    }

    @Test
    void shouldRejectAlreadyRegisteredEmail() {
        when(repository.existsByEmail("ada@example.com")).thenReturn(true);

        assertThrows(IllegalStateException.class,
            () -> service.register("Ada@example.com"));

        verify(repository, never()).save(any(Customer.class));
    }
}
~~~

**What this unit test proves:** normalization logic, rejection conditions, information sent to the dependency, and branching based on mock results. **What it does not prove:** whether MongoDB has a unique index, whether **existsByEmail** queries properly, whether the document maps properly, or whether **save** fails on duplicate writes.

You do not need **@SpringBootTest**, **@DataMongoTest**, or **@MockBean** to test this class. The less infrastructure a test initializes, the faster it runs and the easier it is to pinpoint failures.

## 5. Repository Test: Prove Mapping and Queries on Real MongoDB

**@DataMongoTest** is a Spring Boot test slice for MongoDB: it creates a context focused on MongoDB components such as **MongoTemplate**, mapping, and repositories, while restricting scanning of beans outside this scope. It does **not** automatically guarantee a running MongoDB instance. For tests that carry real value for queries, use real MongoDB via Testcontainers or a managed MongoDB test instance.

The example below uses Testcontainers 1.x with Docker available. Minimal dependencies in test scope include **spring-boot-starter-test**, **org.testcontainers:junit-jupiter**, and **org.testcontainers:mongodb** (versions must align with dependency management).

~~~java
package example.customer;

import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@DataMongoTest
@Testcontainers
class CustomerRepositoryTest {

    @Container
    static final MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongodbProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", mongo::getReplicaSetUrl);
    }

    @Autowired
    CustomerRepository repository;

    @Autowired
    MongoTemplate template;

    @BeforeEach
    void resetData() {
        repository.deleteAll();
    }

    @Test
    void shouldFindActiveCustomersOrderedByEmail() {
        repository.saveAll(List.of(
            new Customer("zoe@example.com", "ACTIVE"),
            new Customer("ada@example.com", "ACTIVE"),
            new Customer("bob@example.com", "INACTIVE")
        ));

        List<String> emails = repository
            .findByStatusOrderByEmailAsc("ACTIVE")
            .stream().map(Customer::getEmail).toList();

        assertEquals(
            List.of("ada@example.com", "zoe@example.com"),
            emails
        );
    }

    @Test
    void shouldEnforceUniqueEmailInMongoDB() {
        // Create a real index: do not rely on auto-index-creation.
        template.indexOps(Customer.class).ensureIndex(
            new Index().on("email", Sort.Direction.ASC).unique()
        );

        repository.save(new Customer("ada@example.com", "ACTIVE"));

        assertThrows(DuplicateKeyException.class,
            () -> repository.save(
                new Customer("ada@example.com", "ACTIVE")
            ));
    }
}
~~~

**Points to observe:**

- The test verifies BSON serialization, mapping back to **Customer**, the derived query, and the actual results returned by MongoDB.
- **findByStatusOrderByEmailAsc** is genuinely verified; Mockito cannot catch a misspelled property name or how the database executes the query.
- **@Indexed(unique = true)** declares intent; creating indexes from annotations depends on **auto-index-creation**. The test explicitly calls **ensureIndex** to prove the engine rejects duplicate data.
- **@DataMongoTest** does not automatically load any service. You can use **@Import** if it fits the test goal, but a multi-bean flow is usually clearer in an integration test.
- **mongo:7.0** is just an example. Use a server version close to production, especially when testing operators, aggregations, indexes, or transactions.

**Version note:** some newer Testcontainers major versions change the package or API of **MongoDBContainer**. The example above is for **Testcontainers 1.x**; choose imports and dependencies matching your actual version and do not mix multiple major versions.

## 6. Integration Test: Service, Spring Context, and MongoDB Together

**@SpringBootTest** loads the application's ApplicationContext and tests beans, real configuration, services, and repositories working together. It is suited for bugs caused by wiring, profiles, converters, event listeners, transaction managers, or integrated dependencies. You do not need a full context to test every repository method.

The example below assumes the actual application has a **@SpringBootApplication** class and can component-scan **CustomerRegistrationService**:

~~~java
package example.customer;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Testcontainers
class CustomerRegistrationIntegrationTest {

    @Container
    static final MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongodbProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", mongo::getReplicaSetUrl);
    }

    @Autowired
    CustomerRegistrationService service;

    @Autowired
    CustomerRepository repository;

    @BeforeEach
    void resetData() {
        repository.deleteAll();
    }

    @Test
    void registrationShouldPersistNormalizedEmail() {
        Customer saved = service.register("  Ada@Example.COM ");
        assertNotNull(saved.getId());
        assertEquals("ada@example.com", saved.getEmail());

        Customer stored = repository
            .findByEmail("ada@example.com")
            .orElseThrow();
        assertEquals(saved.getId(), stored.getId());
        assertEquals("ACTIVE", stored.getStatus());
    }
}
~~~

This test verifies the **CustomerRegistrationService → CustomerRepository → MongoDB** flow, the write result, and the ability to read the document back. With **@SpringBootTest(webEnvironment = RANDOM_PORT)**, you can extend it to send HTTP requests via **TestRestTemplate**, **WebTestClient**, or an appropriate HTTP client, testing request validation, JSON, security, and exception mapping.

**Configuration for real applications:** **@SpringBootTest** activates the beans required by the full application. If the project also includes Kafka, S3, external HTTP services, or an authentication server, you must configure suitable fakes/test doubles or test instances for those dependencies. The absence of external services does not mean MongoDB is wrong, but skipping critical dependencies also fails to prove the whole flow.

| Criterion | **@DataMongoTest** | **@SpringBootTest** |
| --- | --- | --- |
| Spring context | Only MongoDB components and related configuration | Most or all of the application per test configuration |
| Application-defined services | Usually not loaded unless imported | Loaded if within component scan scope |
| Best suited for | Derived queries, mapping, BSON, indexes, MongoTemplate | Wiring, service + DB, transactions, security/HTTP when needed |
| Speed and fault isolation | Usually faster, fewer dependencies | Usually slower, more components can fail |
| Real MongoDB? | **Yes**, when configured with Testcontainers/real DB | **Yes**, when configured with Testcontainers/real DB |

Note: although **@DataMongoTest** is called a “slice test”, when used with real MongoDB it is still an **integration test at the repository–database boundary**. The three labels in this lesson distinguish **goals and scope**, not three strictly separate worlds.

## 7. MongoTemplate, Criteria, and Aggregation: How to Choose Tests?

With **MongoTemplate**, a single method may perform Java calculations while also building a complex **Query**. You should classify them:

- Pure Java filter-building functions, input checks, or business branching: unit tests when independent of the engine.
- **Criteria**, **Update**, **findAndModify**, **bulk operations**, **aggregation**, BSON conversion, collation, and MongoDB operators: repository tests on a real server.
- Flows with multiple document-modifying operations, events, or transactions: integration tests with the appropriate infrastructure.

Example of a conditional query:

~~~java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<Customer> findActiveCustomers(MongoTemplate template) {
    Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
    ).with(Sort.by(Sort.Direction.ASC, "email"));
    return template.find(query, Customer.class);
}
~~~

The snippet above illustrates the method body inside a custom repository or DAO, not a standalone Java file. Only a test against the database proves that field names are mapped properly and sorting works as expected. For **$match → $group → $sort** aggregations, create fixture data representing multiple groups, empty datasets, and null fields; assert the **final result**, not just that aggregate was called.

When testing bulk updates, do not check only **matchedCount**: understand **modifiedCount**, which fields changed, whether documents outside the condition were overwritten, and whether re-running is idempotent. For **findAndModify**, check which version of the document is returned (before or after update) according to **FindAndModifyOptions**.

## 8. Indexes, Transactions, and Optimistic Locking Need Specific Conditions

### 8.1. Testing Indexes Meaningfully

An index affects both **correctness** (e.g., unique constraints) and **performance** (index plans). These two kinds of evidence are different:

- **Correctness:** confirm the index has the designed keys and unique/TTL/collation options; test duplicate inserts and null/missing states if required by the business logic.
- **Performance:** use **explain("executionStats")** with sufficiently representative data to inspect **winningPlan**, **totalDocsExamined**, **totalKeysExamined**, and **nReturned**. A test with 5 documents does not prove a query will be fast on 10 million documents.

TTL indexes rely on a background deletion thread and do not run with millisecond precision. Do not write tests assuming documents vanish immediately at the TTL mark. Verify index configuration first; if testing actual deletion delay, use a separate test with an appropriate wait window.

### 8.2. Testing Transactions

MongoDB multi-document transactions require a **replica set** or **sharded cluster** environment and **MongoTransactionManager** (or **ReactiveMongoTransactionManager** for reactive). Testing transactions against a standalone MongoDB and concluding the application is broken is inaccurate.

A meaningful test must prove:

1. Within a transaction, two successful write operations are committed together.
2. When the second operation fails, data from the first operation is **not** committed.
3. Reading outside the transaction after the failure confirms no partial writes remain.
4. Spring actually manages the transaction for the flow under test; watch out for **@Transactional** self-invocation and ensure reactive pipelines are subscribed to.

Avoid putting **@Transactional** on the test itself and checking state before the test's transaction ends, as that can mask commit/rollback bugs in the service. Usually you should call the transactional service, let the method return or throw an exception, and then query again in a fresh scope.

### 8.3. Optimistic Locking and Concurrent Updates

With a **@Version** field, simulate two reads with the same version, write the first, and then write the second. The expected result is that the second operation encounters **OptimisticLockingFailureException** under the proper conditions, instead of silently overwriting newer data.

For concurrent operations, a sequential mock repository **cannot** prove atomicity, race conditions, or conflict resolution. You need tests against real MongoDB with concurrently coordinated requests, asserting the final invariants: **no duplicate emails**, **no lost updates**, and **no partial writes across a transaction**.

## 9. ReactiveMongoRepository and ReactiveMongoTemplate

In the reactive stack, separate **stream processing** from **MongoDB I/O**.

**Reactive unit tests** verify operators, error branches, and retries with **StepVerifier** when the publisher does not depend on the DB:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveRuleTest {
    Mono<String> normalize(String raw) {
        return Mono.justOrEmpty(raw)
            .filter(s -> !s.isBlank())
            .map(s -> s.trim().toLowerCase(java.util.Locale.ROOT))
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Email is required")
            ));
    }

    @Test
    void normalizesWithoutMongoDB() {
        StepVerifier.create(normalize(" Ada@Example.COM "))
            .expectNext("ada@example.com")
            .verifyComplete();
    }
}
~~~

**Reactive repository/integration tests** must subscribe to the publisher so the operation actually executes:

~~~java
StepVerifier.create(reactiveRepository.findByEmail("ada@example.com"))
    .assertNext(customer ->
        assertEquals("ada@example.com", customer.getEmail()))
    .verifyComplete();
~~~

In the second snippet, **reactiveRepository** is a **ReactiveMongoRepository** configured with a real test MongoDB and pre-seeded with matching data. Without a subscription, many reactive I/O operations do not execute, and a test that merely calls the method and returns can pass falsely.

With concurrency, test subscription cancellation, timeouts, backpressure, and how retries affect write operations. Do not use **Thread.sleep** to simulate uncontrolled delays; prefer virtual time for pure Reactor operators and integration tests when driver/network behavior is involved.

## 10. Data, Environment, and Test Independence

A good test must be **repeatable** when run alone, as part of the full suite, or in parallel on CI.

| Issue | Appropriate approach |
| --- | --- |
| Data from a previous test breaks the next test | Use a dedicated database/collection or delete deterministic data in **@BeforeEach**; avoid wiping a shared DB. |
| Multiple tests write to the same collection | Use a separate namespace per test or disable parallel execution for tests sharing state. |
| Server version and feature differences | Run a production-compatible container/cluster and document the version; add dedicated environments for special features. |
| Unique/TTL index does not exist yet | Create indexes explicitly in fixtures or migration setup; do not assume annotations auto-create them. |
| Dynamic time or generated IDs cause flakiness | Fix **Clock** in unit tests; assert properties of generated IDs instead of hardcoding random values. |
| External services cause unrelated failures | Use service fakes/test doubles or dedicated containers depending on the integration test objective. |
| Docker unavailable in CI | Configure a Testcontainers-compatible Docker runner; clearly mark skipped tests instead of treating them as verified. |
| Running many test contexts consumes memory | Reuse context configurations sensibly, and limit fixtures and concurrent containers. |

**Automatic rollback is not needed in every MongoDB test.** For ordinary tests, cleaning data between tests or using a dedicated database can be simpler. If a test requires transactions, it must verify commit/rollback of that feature itself; putting a transactional annotation on every test can make assertions diverge from production behavior.

With **@DataMongoTest**, check the entity/repository packages: if the test class sits outside the package tree Spring scans for beans, configure explicit scanning or imports. A missing repository bean is often caused by the test slice and package structure, not necessarily MongoDB.

## 11. Designing a Test Suite by Risk

Do not write hundreds of integration tests repeating the same business conditions. Layer tests by risk and diagnostic value:

| Test group | Primary goal | Examples | When to run |
| --- | --- | --- | --- |
| **Unit** | Java rules and branching | Blank email; normalization; dependency error | Every commit / locally |
| **Repository slice** | BSON mapping, queries, indexes | Derived queries, Criteria, duplicate key | Every PR / CI |
| **Full integration** | Wiring, service–repository, transactions | Customer registration really persists; rollback | Every PR or integration suite |
| **Contract / API** | Interfaces and formats | JSON schema, HTTP status, duplicate error | On API changes |
| **Performance** | Query plans, throughput, latency | Aggregation on representative data | On index/query changes or periodically |

**Minimal yet meaningful example** for the registration feature:

- Unit: 3–5 tests covering valid data, null/blank, known duplicate, normalization.
- Repository: 2–4 tests covering mapping, email lookup, status list ordering, and unique index.
- Integration: 1–2 tests covering the service actually persisting successfully and handling duplicate errors from the DB.
- When adding transactions, aggregations, concurrency, or reactive flows, add tests specifically at the **newly introduced risk point** instead of duplicating all scenarios across every layer.

Tests that verify method calls in excessive detail easily become **implementation tests**: refactoring internals while preserving behavior still breaks them. In unit tests, verify business-meaningful interactions; in repository and integration tests, prefer asserting **data state and final outcomes**.

## 12. Misleading Test Patterns to Avoid

### “Mockito Proves the Repository Query Works”

~~~java
when(repository.findByEmail("ada@example.com"))
    .thenReturn(java.util.Optional.of(
        new Customer("ada@example.com", "ACTIVE")
    ));
~~~

This is **configuring mock behavior**, not verifying **findByEmail**. To test a derived query, send data through real MongoDB and call the real repository.

### “@DataMongoTest Includes a Server by Default”

This annotation manages Spring's **test slice** and MongoDB configuration; the test still needs an available MongoDB instance. Do not assume embedded MongoDB starts automatically across all Spring Boot versions. If using a fake or embedded engine, understand how it differs from real MongoDB, especially regarding transactions, indexes, and aggregations.

### “A Single Successful Insert Test Proves the Unique Index”

Inserting one document can succeed even when the unique index does not exist. To prove uniqueness, ensure the index exists and attempt a duplicate insert.

### “A Small Dataset Is Enough to Prove a Query Is Fast”

Correct results and a good query plan are two different goals. To check performance, measure with data size, cardinality, and distribution close to production.

### “Calling a Reactive Method Means Data Was Saved”

A **Mono** or **Flux** typically does not execute write operations until it is subscribed to. Use **StepVerifier** or an explicit subscriber and verify MongoDB state after the publisher completes.

## 13. Checklist Before Choosing and Writing Tests

1. **Write one sentence about what you need to prove:** “Email is normalized” or “Unique index rejects two duplicate documents”?
2. **Pick the smallest scope containing the behavior:** plain Java → unit; queries/mapping → repository; coordinating beans and infrastructure → integration.
3. **Choose real or fake dependencies based on risk:** mock service boundaries where appropriate, and use real MongoDB when verifying MongoDB behavior.
4. **Match version/topology:** replica set when testing transactions, appropriate server version when using new operators/indexes.
5. **Prepare fixtures including edge cases:** null, missing, empty, duplicate, Unicode, legacy data, and varied BSON types where relevant.
6. **Assert observable outcomes:** return values, exceptions, saved documents, indexes, and post-rollback data.
7. **Keep tests independent:** repeatable, runnable in isolation, and consistent on CI.
8. **State the limits of the suite:** unit tests do not verify queries; repository slices do not verify full wiring; small integration tests do not prove production performance.

## 14. Practice Exercise

**Problem:** Extend **CustomerRegistrationService** to reject disallowed email domains and implement finding customers by status from a **MongoRepository**.

**Requirements:**

1. Create unit tests for allowed and disallowed domains; use Mockito to assert the repository is not called when the email is invalid.
2. Add a repository query to find **ACTIVE** customers ordered by email ascending. Write a **@DataMongoTest** with at least three documents and assert the result ordering.
3. Create an actual unique index and attempt a duplicate insert with the same email; explain why calling **existsByEmail** alone is insufficient.
4. Use **@SpringBootTest** to register a customer through the service, read it back via the repository, and verify the normalized data.
5. Name scenarios where the suite above is **not enough**, such as concurrent registrations, multi-document transactions, or complex aggregations; propose appropriate additional tests.

**Completion criteria:** not only green tests, but each test group must clearly state its objective, which part of the system is actually executed, and the limits of its evidence. With Spring Data MongoDB, **unit tests protect logic**, **repository tests protect queries and mapping**, and **integration tests protect the coordinated behavior of the application with MongoDB**.
