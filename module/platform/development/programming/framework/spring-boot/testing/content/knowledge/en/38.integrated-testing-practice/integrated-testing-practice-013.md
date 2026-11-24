# Summarizing the Requirements, Evidence, and Limitations Matrix Across Test Types

In the **Integrated Practice** group of the **Spring Boot - testing** module, a system is not proven correct merely by saying “the tests are green.” You need to answer: **which specific requirement was verified, at what layer, by which assertions, and what remains unproven?** That is the purpose of the **requirements – tests – evidence – limitations traceability matrix**. It ties together unit testing, Mockito, Spring test slices, JDBC, API/HTTP integration, Testcontainers, contract testing, security, resilience, and CI into a QA mechanism that can be explained, re-run, and audited.

This lesson uses **Java 17, Spring Boot 3.5, JUnit Jupiter 5, Mockito, Spring MVC/MockMvc, JdbcTemplate, H2, and TestRestTemplate**. The hands-on section includes a runnable project with **18 JUnit methods** spread across five test classes, paired with a matrix of requirements, acceptance criteria, evidence, and limitations. It also includes a Java SE demo with `javac`/`java` commands and exact stdout. An extended PostgreSQL Testcontainers test is clearly marked as **optional**, running only when you add its dependencies and have a Docker runtime.

**Core takeaway:** Choose the **cheapest test type that still proves the specific risk**. Pure unit tests prove algorithms; Mockito proves interactions with a mocked collaborator; MockMvc proves the Spring MVC contract without opening a server socket; JDBC slices prove SQL against the **database actually used in the test**; `RANDOM_PORT` proves real HTTP and persistence across the server thread; Testcontainers verifies real engine and protocol semantics without proving production HA, load, or SLOs. Anything lacking evidence must be explicitly documented rather than marked PASS.

## 1. Requirements, Assertions, Scope, and Limitations Are Four Separate Questions

| Component | Question | Example | Do Not Do |
| --- | --- | --- | --- |
| **Requirement** | What must the app do? | Quantities 0 and 11 must be rejected | Use coverage % instead of business acceptance |
| **Evidence** | What did the test observe/assert? | `assertThrows` and `verifyNoInteractions` | Call a method without asserting |
| **Boundary** | Which real components ran? | Real MVC with mocked service | Call it full end-to-end |
| **Limitation** | What remains unproven? | No real TCP or SQL in an MVC slice | Leave the gaps column blank because tests are green |
| **Artifact** | Who can inspect the results? | JUnit XML, CI run, commit, fixture | Screenshot only “BUILD SUCCESSFUL” |

A test must have an **independent oracle**: expected values come from the requirement or contract, never computed by the same implementation under test. For errors, assert the exception type, status/code, and side effects; for data, assert exact rows/fields and post-transaction state. “Does not throw” is rarely enough to prove a business outcome.

A test result is meaningful only alongside the **code version, inputs/fixtures, environment, framework/DB versions, timestamp, and test execution status**. A defined method is not automatically discovered by the JUnit engine; a skipped class is not VERIFIED.

## 2. Layered Test Model by Responsibility

```text
        User / critical end-to-end journey
                     /\
                    /  \
             Real HTTP / API contract
                 /----------\
            Spring/DB integration
             /----------------\
        MVC / JDBC / JSON test slices
          /----------------------\
       Pure unit and Mockito tests
     /----------------------------\
    Compile, lint, type and static checks
```

Higher layers include more real components, take longer to set up, and make failures harder to localize. Lower layers test many edge cases quickly and consistently, but do not prove collaboration across systems.

**Do not conflate:**

- Unit tests **do not require mocks**: plain Java objects can be tested directly.
- Integration tests **do not require Docker**: real JDBC/H2 inside a Spring test slice already integrates a database, though its fidelity to production PostgreSQL is lower.
- E2E tests **do not prove all system conditions**: one happy path still misses permissions, concurrency, cache expiry, or outages.
- Coverage **does not prove strong assertions**: 100% LINE/BRANCH coverage can still miss an off-by-one bug or missing tenant filtering.

The matrix must reflect multiple complementary tests for a single requirement whenever there are multiple failure boundaries.

## 3. Test Type – Evidence – Limitations Selection Table

| Test layer / tool | Real components in test | Valuable evidence | Limitations |
| --- | --- | --- | --- |
| JUnit pure unit | Plain Java logic | Outputs, exceptions, invariants, boundaries | No Spring wiring, HTTP, or DB |
| Mockito `@Mock`/`MockitoExtension` | Real service, fake collaborators | `verify`, arguments, error propagation, no calls | Does not prove real SQL/API or proxy/AOP |
| Spring `ApplicationContextRunner` | Selected bean configuration | Property binding, conditional beans, startup failures | Not a full app or server |
| `@JsonTest` | JSON mapper/modules | Field names, dates, nulls, no sensitive fields | No MVC status or auth |
| `@WebMvcTest` + `MockMvc` | MVC controller/converters/advice, usually mocked service | HTTP status, headers, JSON, request binding | No real socket; DB/service mocked |
| `@WebFluxTest` + `WebTestClient` | Reactive web layer | `Mono`/`Flux` responses, routing/status | Not a full reactive deployment |
| `@RestClientTest` | Client construction, JSON/HTTP mapping, mock remote | Expected outbound URI/headers/request/body | No real remote server or network timeout |
| `@JdbcTest` | `JdbcTemplate` + `DataSource` | SQL/row mapping, generated keys, DB constraints | H2 is not PostgreSQL |
| `@DataJdbcTest` | Spring Data JDBC repositories/aggregates | Repository persistence/model mapping | No MVC or full service |
| `@DataJpaTest` | JPA repositories/`EntityManager` | JPQL/flush/relations/constraints | No HTTP; DB dialect may differ |
| `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | Full context and mocked MVC environment | Bean wiring + HTTP contract via `MockMvc` | No TCP or embedded server |
| `@SpringBootTest(RANDOM_PORT)` | Embedded server, real HTTP, app services | POST/GET, headers, committed persistence | No ingress/TLS/replica network unless built |
| Testcontainers | Real DB/broker/cache container | Engine-specific SQL/protocol/error semantics | Not prod HA, load, or security |
| Consumer/provider contract | Contract fixtures and provider verification | Schema/example compatibility | Not full live provider behavior |
| Security integration | Auth filters, roles, security context | 401/403, tenant isolation, no side effects | Does not replace threat modeling/pentest |
| Load/soak/fault injection | Target topology and workload | p95/p99, saturation, recovery | Does not model every production pattern |

**Note:** `@…Test` slices load only a subset of Spring Boot auto-configurations. If a component is excluded, you must `@Import` or mock the bean; do not assume the entire app started. For transactional tests, rollback depends on Spring TestContext and thread binding; it does not undo side effects outside the transaction.

## 4. Traceability Matrix Schema for Engineering Teams

| Column | Description |
| --- | --- |
| Requirement ID | Stable ID in ticket/spec |
| Acceptance criterion | Measurable outcome and boundary conditions |
| Risk/severity | Impact if broken |
| Test design/level | Unit, MVC, JDBC, HTTP, DB container, contract, perf |
| Fixture/input | Inputs, rows, clock, profile, upstream responses |
| Expected evidence | Detailed assertions, exceptions, side effects |
| Test ID | File/class/method, or contract path |
| Actual run evidence | Report URL, commit, environment, status |
| Not proven | Remaining risks; never leave blank |
| Owner/CI gate | Responsible team and run cadence |
| State | VERIFIED / FAILED / PARTIAL / BLOCKED / NOT_IMPLEMENTED |

**Example:** “quantity must be in [1,10]; outside range POST returns 400 and persists no order” is a measurable requirement. Three layers of evidence can apply: `OrderPolicyTest` throws an exception; `OrderControllerTest` returns 400; `RealHttpOrderTest` gets real HTTP 400 and SQL count=0. Do not use a single unit assertion to claim all three boundaries are protected.

## 5. Applying the Matrix to the Order Creation API

The demo project provides `POST /orders` and `GET /orders/{id}`, uppercase SKU 2–12 characters, quantity 1..10, price 250 cents per unit. Persistence uses JDBC; creating returns 201 + `Location`, and missing GET returns 404.

| ID | Condition | Minimum test types | Assertions/evidence | Not yet proven |
| --- | --- | --- | --- | --- |
| ORD-01 | quantity 1 and 10 are valid | Pure JUnit | Total 250/2500 | HTTP/JDBC |
| ORD-02 | quantity 0 and 11 are invalid | Unit + MVC + real HTTP | Exception/400/DB count=0 | Ingress |
| ORD-03 | null/lowercase SKU rejected | Unit + service | `IllegalArgumentException`, no SQL call | Other Unicode/locale policies |
| ORD-04 | Exact price math, no floating point | Pure JUnit | 2 × 250 = 500 cents | Tax/other currencies |
| ORD-05 | Service passes exact values to repository | Mockito unit | `verify("SKU-1",2,500)` | Real SQL |
| ORD-06 | Valid POST → 201, `Location`, and JSON | MVC slice + HTTP | Status/header/id/body | Gateway/TLS |
| ORD-07 | Existing GET → 200, matching record | MVC/HTTP | SKU, qty, cents, id | Authorization |
| ORD-08 | Missing GET → 404, no internal leak | MVC | HTTP 404 + generic JSON | Real routing/security |
| ORD-09 | SQL INSERT/SELECT roundtrip works | JDBC slice | Generated ID, fields, count | PostgreSQL-specific behavior |
| ORD-10 | DB blocks null SKU | JDBC slice | `DataIntegrityViolationException` | Production schema if different |
| ORD-11 | Real HTTP POST commits to DB | `RANDOM_PORT` | 201 + GET + DB count=1 | Cluster/replicas |
| ORD-12 | Invalid HTTP request does not write DB | `RANDOM_PORT` | 400 + DB count=0 | Concurrent side effects |
| ORD-13 | Real PostgreSQL dialect/driver | Testcontainers | SQL casts/constraints on Postgres | HA/production load |
| ORD-14 | Duplicate POST/retry creates no duplicate | Concurrency+DB+HTTP | Idempotency key/unique count | Not implemented |
| ORD-15 | Unauthorized user/tenant denied access | Security+DB | 401/403, no rows/leaks | Not implemented |
| ORD-16 | Provider/consumer schemas compatible | Contract verification | Schema/version examples | Provider uptime |
| ORD-17 | Timeout never reports false success | HTTP fault injection | Unknown/retry/reconciliation | Not implemented |
| ORD-18 | p95 under SLO at approved load | Load test | Workload + latency/error graphs | Test topology ≠ production |

**ORD-01..12** have illustrative test code below across different scopes; **ORD-13** has an optional Docker test; **ORD-14..18** are deliberate gaps in the demo and must never be reported as “PASS.” In a real product, each gap needs an owner and mitigation plan.

## 6. Scope of the Runnable Project

All demo files use package `example.evidence`. There is a Spring Boot main class, JDBC interface + implementation, policy, service, controller, error advice, SQL schema, and five test classes. There is no auth, inventory, payment, or event bus; this example teaches **layered evidence**, not a production ordering system.

```text
evidence-matrix/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/evidence/
    │   │   ├── EvidenceApplication.java
    │   │   ├── OrderPolicy.java
    │   │   ├── OrderRequest.java
    │   │   ├── OrderReceipt.java
    │   │   ├── OrderStore.java
    │   │   ├── JdbcOrderStore.java
    │   │   ├── OrderNotFoundException.java
    │   │   ├── OrderService.java
    │   │   ├── OrderController.java
    │   │   ├── OrderErrorAdvice.java
    │   │   └── OrderPolicyDemo.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/example/evidence/
        ├── OrderPolicyTest.java
        ├── OrderServiceTest.java
        ├── OrderControllerTest.java
        ├── JdbcOrderStoreTest.java
        └── RealHttpOrderTest.java
```

**Behavior diagram:**

```text
POST /orders
  |
  v
OrderController -- JSON request/response & HTTP 201
  |
  v
OrderService ---- @Transactional
  |
  +---- OrderPolicy ---- SKU, quantity, totalCents (pure Java)
  |
  +---- OrderStore interface
           |
           v
       JdbcOrderStore ---- SQL / generated key / constraint
           |
           v
          H2

GET /orders/{id} -> OrderService.find -> JdbcOrderStore.find
                                  -> OrderNotFoundException -> 404
```

## 7. `build.gradle` – Minimal Dependencies, No Docker

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Spring Boot 3.5** uses Spring Framework 6.2, so the imports in `@WebMvcTest` and `@MockitoBean` match that release line. When upgrading to Boot 4, test starter and package changes will need review. Java 17 is the baseline. H2 is a real embedded database, but it is not PostgreSQL. `useJUnitPlatform()` enables JUnit Jupiter test discovery.

**Maven/Gradle:** Let the Boot BOM align JUnit, Mockito, JDBC, and Spring Test versions; do not pin an incompatible Jupiter Engine separately from the Platform. A compatible Gradle Wrapper must be generated before running `./gradlew`; `build.gradle` alone does not generate the wrapper.

## 8. `schema.sql` and Embedded DB Configuration

Create `src/main/resources/application.properties`:

```properties
spring.datasource.generate-unique-name=true
spring.sql.init.mode=always
```

Create `src/main/resources/schema.sql`:

```sql
CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(12) NOT NULL,
    quantity INTEGER NOT NULL,
    total_cents INTEGER NOT NULL
);
```

Having H2 on the runtime classpath lets Boot auto-configure an embedded `DataSource`. Each context can get its own database name; `schema.sql` runs during SQL initialization. `NOT NULL` is a database contract testable with real SQL. There is no Flyway or Liquibase in this demo: in production products, migrations should be versioned and tested against official PostgreSQL or matching Testcontainers images.

## 9. `OrderPolicy.java`: Spring-Free Logic

Create `src/main/java/example/evidence/OrderPolicy.java`:

```java
package example.evidence;

public final class OrderPolicy {
    public int totalCents(String sku, int quantity) {
        if (sku == null
                || !sku.matches("[A-Z0-9-]{2,12}")) {
            throw new IllegalArgumentException("invalid sku");
        }

        if (quantity < 1 || quantity > 10) {
            throw new IllegalArgumentException(
                    "quantity must be 1..10");
        }

        return Math.multiplyExact(quantity, 250);
    }
}
```

Rules: SKU 2..12 uppercase ASCII/alphanumeric/hyphen; qty 1..10; unit price 250 integer cents. `sku == null` is safe thanks to short-circuit `||`. `Math.multiplyExact` guards against overflow if limits ever expand, though qty ≤ 10 cannot overflow under the current contract.

**Unit-level evidence:** expectations derived from rules: `qty=1 → 250`, `qty=10 → 2500`, invalid → exception. **Not proven:** query binding, response mapping, or DB transactions.

## 10. Request and Response DTO Records

Create `src/main/java/example/evidence/OrderRequest.java`:

```java
package example.evidence;

public record OrderRequest(String sku, int quantity) {
}
```

Create `src/main/java/example/evidence/OrderReceipt.java`:

```java
package example.evidence;

public record OrderReceipt(
        long id, String sku,
        int quantity, int totalCents) {
}
```

Spring Boot 3.5 with Jackson supports serializing and deserializing Java 17 records. The API response exposes `id`, `sku`, `quantity`, and `totalCents`. When real schemas evolve, add tests covering nulls/defaults, unknown fields, backwards compatibility, sensitive fields, currency/precision, timezones, and enum versioning.

## 11. `OrderStore.java`: Repository Abstraction

Create `src/main/java/example/evidence/OrderStore.java`:

```java
package example.evidence;

import java.util.Optional;

public interface OrderStore {

    long create(
            String sku, int quantity, int totalCents);

    Optional<OrderReceipt> find(long id);

    long count();
}
```

Service unit tests mock `OrderStore` to verify **invocations** without needing a database. However, Mockito proves nothing about SQL; a JDBC slice is needed to verify the implementation.

## 12. `JdbcOrderStore.java`: SQL Implementation

Create `src/main/java/example/evidence/JdbcOrderStore.java`:

```java
package example.evidence;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcOrderStore implements OrderStore {
    private final JdbcTemplate jdbc;

    public JdbcOrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public long create(
            String sku, int quantity, int totalCents) {
        KeyHolder keys = new GeneratedKeyHolder();

        jdbc.update(connection -> {
            PreparedStatement ps =
                    connection.prepareStatement(
                            "INSERT INTO orders "
                            + "(sku, quantity, total_cents) "
                            + "VALUES (?, ?, ?)",
                            Statement.RETURN_GENERATED_KEYS);
            ps.setString(1, sku);
            ps.setInt(2, quantity);
            ps.setInt(3, totalCents);
            return ps;
        }, keys);

        Number key = keys.getKey();
        if (key == null) {
            throw new IllegalStateException(
                    "database did not return id");
        }
        return key.longValue();
    }

    @Override
    public Optional<OrderReceipt> find(long id) {
        return jdbc.query(
                "SELECT id, sku, quantity, total_cents "
                + "FROM orders WHERE id = ?",
                (rs, row) -> new OrderReceipt(
                        rs.getLong("id"),
                        rs.getString("sku"),
                        rs.getInt("quantity"),
                        rs.getInt("total_cents")),
                id).stream().findFirst();
    }

    @Override
    public long count() {
        Long value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM orders", Long.class);
        return value == null ? 0L : value;
    }
}
```

The SQL uses a prepared statement with bound parameters, and the generated key is null-checked. `JdbcTemplate` translates `SQLException` into the appropriate `DataAccessException` hierarchy. **JDBC integration evidence** must assert the generated ID, query results, and constraints; never call a mocked repository unit test an SQL test.

## 13. `OrderNotFoundException` and `OrderService`

Create `src/main/java/example/evidence/OrderNotFoundException.java`:

```java
package example.evidence;

public final class OrderNotFoundException
        extends RuntimeException {
    public OrderNotFoundException(long id) {
        super("order not found: " + id);
    }
}
```

Create `src/main/java/example/evidence/OrderService.java`:

```java
package example.evidence;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderPolicy policy;
    private final OrderStore store;

    public OrderService(
            OrderPolicy policy, OrderStore store) {
        this.policy = policy;
        this.store = store;
    }

    @Transactional
    public OrderReceipt create(OrderRequest request) {
        int total = policy.totalCents(
                request.sku(), request.quantity());
        long id = store.create(
                request.sku(), request.quantity(), total);

        return new OrderReceipt(
                id, request.sku(),
                request.quantity(), total);
    }

    @Transactional(readOnly = true)
    public OrderReceipt find(long id) {
        return store.find(id)
                .orElseThrow(
                        () -> new OrderNotFoundException(id));
    }
}
```

Spring manages transactions via a proxy around `@Transactional` on the service bean. If a unit test instantiates `new OrderService(...)`, the business logic still runs, **without passing through Spring transaction advice**. Therefore a Mockito unit test cannot prove rollback/commit behavior; you need HTTP integration or Spring-managed service integration backed by a database.

## 14. `OrderController` and Error Advice

Create `src/main/java/example/evidence/OrderController.java`:

```java
package example.evidence;

import java.net.URI;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<OrderReceipt> create(
            @RequestBody OrderRequest request) {
        OrderReceipt receipt = service.create(request);

        return ResponseEntity.created(
                URI.create("/orders/" + receipt.id()))
                .body(receipt);
    }

    @GetMapping("/{id}")
    public OrderReceipt find(@PathVariable long id) {
        return service.find(id);
    }
}
```

Create `src/main/java/example/evidence/OrderErrorAdvice.java`:

```java
package example.evidence;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class OrderErrorAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> badInput() {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "invalid order input"));
    }

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<Map<String, String>> notFound() {
        return ResponseEntity.status(404)
                .body(Map.of("error", "order not found"));
    }
}
```

The controller returns **201 + `Location` + JSON** on creation, **200** on GET, **400** for invalid domain input, and **404** for a missing ID. Malformed JSON is rejected by Spring MVC message conversion before the service is invoked.

**A `@WebMvcTest` mocking the service** can assert body, headers, and status, without exercising SQL or network transport. A full HTTP test with the real service and DB covers that remaining scope.

## 15. `EvidenceApplication.java`: A Single Application Root

Create `src/main/java/example/evidence/EvidenceApplication.java`:

```java
package example.evidence;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class EvidenceApplication {

    @Bean
    OrderPolicy orderPolicy() {
        return new OrderPolicy();
    }

    public static void main(String[] args) {
        SpringApplication.run(
                EvidenceApplication.class, args);
    }
}
```

Spring component scanning discovers the repository, service, controller, and advice in the same package. `PricePolicy` is plain Java declared as a bean in the main configuration. Avoid having multiple `@SpringBootConfiguration` classes with unclear scope under the test root, because Boot test slices may resolve the wrong configuration.

## 16. `OrderPolicyTest.java` – 4 JUnit Unit Methods

Create `src/test/java/example/evidence/OrderPolicyTest.java`:

```java
package example.evidence;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderPolicyTest {
    private final OrderPolicy policy = new OrderPolicy();

    @Test
    void validBoundaryQuantitiesHaveExactTotals() {
        assertEquals(250,
                policy.totalCents("SKU-1", 1));
        assertEquals(2500,
                policy.totalCents("SKU-1", 10));
    }

    @Test
    void nullSkuIsRejected() {
        assertThrows(
                IllegalArgumentException.class,
                () -> policy.totalCents(null, 2));
    }

    @Test
    void lowercaseSkuIsRejected() {
        assertThrows(
                IllegalArgumentException.class,
                () -> policy.totalCents("sku-1", 2));
    }

    @Test
    void outsideQuantityRangeIsRejected() {
        assertThrows(
                IllegalArgumentException.class,
                () -> policy.totalCents("SKU-1", 0));
        assertThrows(
                IllegalArgumentException.class,
                () -> policy.totalCents("SKU-1", 11));
    }
}
```

These are **4 JUnit methods** proving ORD-01..04 within the pure policy scope. No Spring context, SQL, or HTTP runs here. Testing right at `quantity=1` and `10` matters: a mutant changing `quantity > 10` to `quantity >= 10` is caught by testing at 10, whereas testing only `quantity=2` misses it.

## 17. `OrderServiceTest.java` – 4 Mockito Methods

Create `src/test/java/example/evidence/OrderServiceTest.java`:

```java
package example.evidence;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    OrderStore store;

    private OrderService service;

    @BeforeEach
    void setUp() {
        service = new OrderService(
                new OrderPolicy(), store);
    }

    @Test
    void passesCorrectValuesToRepository() {
        when(store.create("SKU-1", 2, 500))
                .thenReturn(42L);

        OrderReceipt result =
                service.create(new OrderRequest("SKU-1", 2));

        assertEquals(
                new OrderReceipt(42L, "SKU-1", 2, 500),
                result);
        verify(store).create("SKU-1", 2, 500);
    }

    @Test
    void invalidSkuDoesNotTouchStore() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.create(
                        new OrderRequest("lowercase", 2)));

        verifyNoInteractions(store);
    }

    @Test
    void invalidQuantityDoesNotTouchStore() {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.create(
                        new OrderRequest("SKU-1", 11)));

        verifyNoInteractions(store);
    }

    @Test
    void repositoryErrorIsNotHidden() {
        when(store.create("SKU-1", 2, 500))
                .thenThrow(
                        new IllegalStateException("db unavailable"));

        assertThrows(
                IllegalStateException.class,
                () -> service.create(
                        new OrderRequest("SKU-1", 2)));

        verify(store).create("SKU-1", 2, 500);
    }
}
```

**4 methods**: real service + mocked collaborator. `MockitoExtension` initializes `@Mock`. `verifyNoInteractions(store)` proves validation runs **before** external side effects. `verify(store).create("SKU-1",2,500)` checks the passed arguments, not only the mocked return value. **Limitation:** neither the database nor the Spring transaction proxy runs in this test.

## 18. `OrderControllerTest.java` – 5 MockMvc Methods

Create `src/test/java/example/evidence/OrderControllerTest.java`:

```java
package example.evidence;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    OrderService service;

    @Test
    void postCreatesResourceWithLocation() throws Exception {
        when(service.create(
                new OrderRequest("SKU-1", 2)))
                .thenReturn(
                        new OrderReceipt(42L, "SKU-1", 2, 500));

        mvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(
                                "{\"sku\":\"SKU-1\",\"quantity\":2}"))
                .andExpect(status().isCreated())
                .andExpect(
                        header().string("Location", "/orders/42"))
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(
                        jsonPath("$.totalCents").value(500));
    }

    @Test
    void domainValidationBecomes400() throws Exception {
        when(service.create(
                new OrderRequest("SKU-1", 0)))
                .thenThrow(
                        new IllegalArgumentException("invalid qty"));

        mvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(
                                "{\"sku\":\"SKU-1\",\"quantity\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(
                        jsonPath("$.error")
                                .value("invalid order input"));
    }

    @Test
    void getReturnsExistingReceipt() throws Exception {
        when(service.find(42L))
                .thenReturn(
                        new OrderReceipt(42L, "SKU-1", 2, 500));

        mvc.perform(get("/orders/42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("SKU-1"))
                .andExpect(
                        jsonPath("$.totalCents").value(500));
    }

    @Test
    void notFoundMapsTo404() throws Exception {
        when(service.find(999L))
                .thenThrow(new OrderNotFoundException(999L));

        mvc.perform(get("/orders/999"))
                .andExpect(status().isNotFound())
                .andExpect(
                        jsonPath("$.error")
                                .value("order not found"));
    }

    @Test
    void malformedJsonNeverCallsService() throws Exception {
        mvc.perform(post("/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{bad-json"))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(service);
    }
}
```

**5 methods** assert binding/serialization, 201 + `Location`, JSON fields, 400/404 error mappings, and malformed JSON rejection. `@MockitoBean` from Spring Framework 6.2 overrides/registers a **mock bean in the `ApplicationContext`**, distinct from a Mockito `@Mock` field.

**Limitation:** `MockMvc` opens no network socket and the service is mocked; it **does not** prove transactions, database behavior, or real server behavior. When Spring Security is present, MVC slices may apply security filters; add tests with appropriate users, roles, and CSRF tokens rather than disabling all security filters just to turn tests green.

## 19. `JdbcOrderStoreTest.java` – 3 `@JdbcTest` Methods

Create `src/test/java/example/evidence/JdbcOrderStoreTest.java`:

```java
package example.evidence;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest
@Import(JdbcOrderStore.class)
class JdbcOrderStoreTest {

    @Autowired
    JdbcOrderStore store;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void insertAndFindRoundtrip() {
        long id = store.create("SKU-1", 2, 500);

        assertTrue(id > 0);
        assertEquals(
                new OrderReceipt(id, "SKU-1", 2, 500),
                store.find(id).orElseThrow());
        assertEquals(1L, store.count());
    }

    @Test
    void unknownIdReturnsEmpty() {
        assertFalse(
                store.find(9_999_999L).isPresent());
        assertEquals(0L, store.count());
    }

    @Test
    void notNullConstraintIsEnforcedByDatabase() {
        assertThrows(
                DataIntegrityViolationException.class,
                () -> jdbc.update(
                        "INSERT INTO orders "
                        + "(sku, quantity, total_cents) "
                        + "VALUES (?, ?, ?)",
                        (Object) null, 1, 250));
    }
}
```

**3 methods** run against a **real JDBC/`DataSource` on H2**. `@JdbcTest` is transactional by default and rolls back after each method; `@Import(JdbcOrderStore.class)` brings in the repository implementation because the slice does not scan arbitrary services or DAOs. `schema.sql` creates the table; the real DB `NOT NULL` constraint throws a `SQLException` translated by Spring into `DataIntegrityViolationException`.

`@DataJdbcTest` targets Spring Data JDBC repositories and aggregates; because this project uses plain JDBC directly, `@JdbcTest` fits best. If production uses PostgreSQL, H2 tests still do not prove PostgreSQL syntax, indexes, isolation, JSONB, migrations, or drivers.

## 20. `RealHttpOrderTest.java` – 2 HTTP Integration Methods

Create `src/test/java/example/evidence/RealHttpOrderTest.java`:

```java
package example.evidence;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpOrderTest {

    @Autowired
    TestRestTemplate http;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void prepare() {
        jdbc.update("DELETE FROM orders");
    }

    @AfterEach
    void cleanup() {
        jdbc.update("DELETE FROM orders");
    }

    @Test
    void postCommitsAndGetReturnsSameReceipt() {
        ResponseEntity<OrderReceipt> created =
                http.postForEntity(
                        "/orders",
                        new OrderRequest("SKU-1", 2),
                        OrderReceipt.class);

        assertEquals(
                HttpStatus.CREATED, created.getStatusCode());

        OrderReceipt receipt = created.getBody();
        assertNotNull(receipt);
        assertTrue(receipt.id() > 0);
        assertEquals(500, receipt.totalCents());

        assertNotNull(
                created.getHeaders().getLocation());
        assertEquals(
                "/orders/" + receipt.id(),
                created.getHeaders()
                        .getLocation().getPath());

        ResponseEntity<OrderReceipt> fetched =
                http.getForEntity(
                        "/orders/{id}",
                        OrderReceipt.class,
                        receipt.id());

        assertEquals(
                HttpStatus.OK, fetched.getStatusCode());
        assertEquals(receipt, fetched.getBody());

        assertEquals(
                1L,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orders",
                        Long.class));
    }

    @Test
    void invalidPostReturns400AndDoesNotPersist() {
        ResponseEntity<String> result =
                http.postForEntity(
                        "/orders",
                        new OrderRequest("SKU-1", 0),
                        String.class);

        assertEquals(
                HttpStatus.BAD_REQUEST,
                result.getStatusCode());
        assertNotNull(result.getBody());
        assertTrue(result.getBody()
                .contains("invalid order input"));

        assertEquals(
                0L,
                jdbc.queryForObject(
                        "SELECT COUNT(*) FROM orders",
                        Long.class));
    }
}
```

**2 methods** start a real embedded server on `RANDOM_PORT` and send requests with `TestRestTemplate` over HTTP loopback. Combined assertions across **HTTP 201/400, `Location`, response body, GET roundtrip, and JDBC row count** deliver stronger evidence than a `MockMvc` test with a mocked service.

**Why `@AfterEach` `DELETE` matters:** the HTTP server handles requests on a **different thread** from the test method, so `@Transactional` on the test would not roll back the server-side transaction. The demo cleans up explicitly. However, truncating/deleting the whole table is only safe when the test DB is not shared by parallel test writers; real systems should use per-test schemas/databases, test tenants/IDs, or ownership-scoped cleanup.

**Limitations:** loopback does not verify an ingress proxy, TLS, auth providers, multi-replica consistency, the production database, retry storms, or p95 under load. Write dedicated tests when those are requirements.

## 21. Total Test Method Count and Verification Matrix

| Test class | `@Test` methods | Scope |
| --- | ---: | --- |
| `OrderPolicyTest` | 4 | Pure Java SKU/quantity/price rules |
| `OrderServiceTest` | 4 | Mockito interactions |
| `OrderControllerTest` | 5 | MVC routes, JSON, status codes |
| `JdbcOrderStoreTest` | 3 | H2 SQL/constraints |
| `RealHttpOrderTest` | 2 | Real HTTP + committed DB state |
| **Total** | **18** | |

**18 is the count of methods defined in source code**, not proof that 18 methods executed in a learner's environment. To mark them VERIFIED, CI must record executed count, skipped count, error details, and artifacts. Never infer full requirement coverage from branch coverage or method counts.

**Mapping:** ORD-01..04 rely on unit tests; ORD-05 on Mockito; ORD-06..08 on MVC; ORD-09/10 on JDBC; ORD-11/12 on HTTP/JDBC; ORD-13..18 require additional verification.

## 22. `OrderPolicyDemo.java` – Deterministic Java SE Stdout

Create `src/main/java/example/evidence/OrderPolicyDemo.java`:

```java
package example.evidence;

public class OrderPolicyDemo {
    public static void main(String[] args) {
        OrderPolicy policy = new OrderPolicy();

        System.out.println(
                "one=" + policy.totalCents("SKU-1", 1));
        System.out.println(
                "two=" + policy.totalCents("SKU-1", 2));
        System.out.println(
                "ten=" + policy.totalCents("SKU-1", 10));

        try {
            policy.totalCents("SKU-1", 11);
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "invalid=" + error.getMessage());
        }
    }
}
```

Run from the project root with JDK 17+:

```bash
javac -d out src/main/java/example/evidence/OrderPolicy.java src/main/java/example/evidence/OrderPolicyDemo.java
java -cp out example.evidence.OrderPolicyDemo
```

**Exact** stdout:

```text
one=250
two=500
ten=2500
invalid=quantity must be 1..10
```

Running the Java SE demo **does not** start Spring, JUnit, JDBC, or HTTP and must never be recorded in the matrix as a Spring integration PASS. It serves solely as a standalone check for pure Java logic.

## 23. Commands to Run JUnit and Collect Build Evidence

Linux/macOS:

```bash
./gradlew test --tests example.evidence.OrderPolicyTest
./gradlew test --tests example.evidence.OrderServiceTest
./gradlew test --tests example.evidence.OrderControllerTest
./gradlew test --tests example.evidence.JdbcOrderStoreTest
./gradlew test --tests example.evidence.RealHttpOrderTest
./gradlew clean test
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.evidence.OrderPolicyTest"
.\gradlew.bat test --tests "example.evidence.OrderServiceTest"
.\gradlew.bat test --tests "example.evidence.OrderControllerTest"
.\gradlew.bat test --tests "example.evidence.JdbcOrderStoreTest"
.\gradlew.bat test --tests "example.evidence.RealHttpOrderTest"
```

Standard build reports reside at:

```text
build/test-results/test/*.xml
build/reports/tests/test/index.html
```

Record the CI job link, commit SHA, JDK/Boot versions, test names, fixture schema, and environment. Inspect **executed/skipped/failed** counts together; `BUILD SUCCESSFUL` does not guarantee all requirements were tested if the test engine failed to discover tests, filters excluded them, or tests were skipped. Avoid hardcoding Gradle stdout expectations because logging and up-to-date/build-cache behavior vary.

## 24. PostgreSQL Testcontainers: An Additional Evidence Tier

If ORD-13 requires real PostgreSQL, H2 is insufficient. With **Boot 3.5 / Testcontainers 1.x**, add to `dependencies` in `build.gradle`:

```groovy
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
testImplementation 'org.testcontainers:junit-jupiter'
testImplementation 'org.testcontainers:postgresql'
testRuntimeOnly 'org.postgresql:postgresql'
```

You can then add `src/test/java/example/evidence/PostgresEvidenceTest.java` (**optional** test, excluded from the default demo's 18 methods):

```java
package example.evidence;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@Testcontainers
class PostgresEvidenceTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("evidence");

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void usesActualPostgresUuidType() {
        String value = jdbc.queryForObject(
                "SELECT '00000000-0000-0000-0000-000000000001'::uuid::text",
                String.class);

        assertEquals(
                "00000000-0000-0000-0000-000000000001",
                value);
    }
}
```

This tests real Postgres protocol, driver, and SQL inside a container, and **requires a Docker-compatible runtime**. `@ServiceConnection` supplies connection details so the app's `DataSource` targets the container without hardcoding mapped ports or passwords. If the container cannot start, the job must FAIL or be marked BLOCKED/explicitly skipped—never reported as DB VERIFIED.

**Not proven:** production DB HA, isolation at large data scale, migration drift, replication/network latency, or security policies. When migrating from H2 to Postgres, run Flyway/Liquibase migrations and test unique/index/locking/transaction semantics on the real engine.

**Version caveat:** Testcontainers 2 (paired with Boot 4) changes PostgreSQL/JUnit Jupiter artifacts and `PostgreSQLContainer` imports. This example uses Testcontainers 1 compatible with Boot 3.5; do not copy it verbatim when upgrading to Boot 4.

## 25. Contract Tests – Consumer Fakes Are Not Provider Verification

A contract test suite must distinguish:

- **Unit fake gateway**: tests how the app handles mocked 200/404/503 responses per expected mappings.
- **`@RestClientTest` / `MockRestServiceServer`**: verifies request URI, headers, JSON serialization, and response decoding against mock HTTP server semantics at the client layer.
- **WireMock loopback real socket**: sends real network/protocol requests to a mock HTTP server, testing client timeout and error mapping.
- **Consumer-driven contract** (e.g., Pact): captures consumer expectations and executes provider verification against the real provider or a sufficiently faithful environment.
- **Staging E2E**: sends requests across real service boundaries.
- **Production monitoring**: detects provider drift, outages, and latency after rollout.

A mock returning 200 matching your fixture **does not prove** the production provider always returns that schema. Provider contract verification **does not prove** production performance or retry behavior. The matrix must separately record consumer test results, provider verification, contract version, and uncovered risks.

## 26. Security, Tenants, and Sensitive Data

| Requirement | Test level | Recommended evidence | Limitation |
| --- | --- | --- | --- |
| Unauthenticated user cannot POST | MVC/security integration | 401 + no DB write | Does not verify external IdP |
| Wrong role cannot write | Security + real service | 403 + zero side effects | Token transport untested |
| Tenant A user cannot read tenant B | DB/HTTP security integration | 403/404, no cross-tenant rows | Replica/cache paths untested |
| Invalid/expired JWT signature rejected | Auth filter integration | 401, no service call | IdP outages/key rotation still carry risk |
| JSON never exposes tokens/passwords | `@JsonTest` + MVC | Sensitive fields absent | Logs/traces remain a risk |
| CSRF enforced for form/session flows | MockMvc + `spring-security-test` | Missing token rejected | Deployment cookie policy |

**`@WithMockUser`** is convenient for testing authorization once Spring Security is wired, but it does not prove real JWT signature validation or OIDC discovery. This demo **has no Spring Security**; ORD-15 is an unimplemented gap and must not be marked security VERIFIED based on the existing HTTP tests.

## 27. Transactions and Async: Test-Managed Rollback Is Not Universal Cleanup

In Spring TestContext, test-managed transactions typically bind to a **`ThreadLocal`** on the test thread. Under `@JdbcTest` or a `@Transactional` test, Spring rolls back when the method finishes (unless configured otherwise). However:

- In `@SpringBootTest(webEnvironment=RANDOM_PORT)`, the HTTP client and server run on different threads, so server-side transactions **do not** roll back with the test thread.
- An `@Async` executor or worker runs outside the test thread and does not automatically inherit the test-managed transaction.
- `@Transactional(REQUIRES_NEW)` uses a separate propagation and commit boundary.
- `assertTimeoutPreemptively(...)` can execute its body on another thread, causing database work to escape the test transaction. For DB-bound tests, prefer non-preemptive timeouts where appropriate.
- External HTTP or messaging side effects are never rolled back by a local DB transaction.
- A client timeout does not prove the server failed to commit; retried POSTs need an idempotency key or reconciliation.

**Proper evidence:** when testing rollback, force a failure and query state at the right transaction boundary; with real HTTP, inspect data after the response and clean up committed rows; with async work, await completion with a bounded timeout and assert worker-side state. Merely seeing `@Transactional` on a service proves nothing about tested behavior.

## 28. Concurrency and Idempotency Are Distinct Gaps

A test that creates an order once does not prove duplicate prevention when two concurrent requests arrive. Requirement ORD-14 requires:

1. A contract defining same idempotency key → at most one logical order.
2. A DB unique constraint or explicit transactional state machine.
3. Concurrent requests synchronized via barriers/latches to hit simultaneously.
4. Bounded `Future.get`/waits and executor cleanup.
5. Assertions on **final DB state**, response/error behavior, and row counts.
6. Retry after timeout and process-restart scenarios where applicable.

Even when a stress test passes, it cannot exhaust every interleaving, so you still need sound reasoning around atomicity/DB constraints and production observability. Idempotency is absent from this demo, so ORD-14 = `NOT_IMPLEMENTED`.

## 29. Resilience, Timeouts, and Fallbacks: What Does Each Test Prove?

| Question | Good evidence | Invalid inference |
| --- | --- | --- |
| Does the client request timeout actually fire? | Local HTTP server delays response, bounded failure | A mocked exception is not a network timeout test |
| Does retry trigger only on transient errors? | Fake gateway + virtual time/attempt counter | Retrying is always safe for POST |
| Does the circuit breaker OPEN at threshold? | Real breaker state + fake port, assert no new call | OPEN aborts already in-flight calls |
| Does `HALF_OPEN` recovery work? | State-transition and probe tests | One `Thread.sleep` proves enough |
| Does the fallback enforce a safe policy? | 503/degraded marker + no false success | Fallback data is valid for every tenant |
| Does the provider recover under outage? | Controlled fault injection + recovery metrics | One success = production SLO |

Testing timeout property binding differs from testing real network timeouts; testing a fallback policy differs from testing application consistency after a timeout. Keep those assertions separate in the matrix. For operations with critical side effects, never return “success” from a fallback simply because an upstream dependency is unavailable.

## 30. Config/Profiles and the Spring TestContext Cache

For `@ConditionalOnProperty`, use `ApplicationContextRunner.withPropertyValues(...)` to test multiple configuration vectors quickly and in isolation; for full-app tests, use `@SpringBootTest(properties=...)` or `@TestPropertySource`. Avoid mutating JVM-wide `System.setProperty` across parallel tests and assuming beans rebind automatically after context refresh.

Example **snippet (not a standalone runnable file)**:

```java
new ApplicationContextRunner()
    .withUserConfiguration(MyConfiguration.class)
    .withPropertyValues("app.feature.enabled=false")
    .run(context -> {
        assertThat(context)
            .doesNotHaveBean(ExternalFeature.class);
    });
```

Real classes and imports are required—do not copy the snippet verbatim and claim it compiles. `ApplicationContextRunner` proves **bean presence and property binding**, not HTTP or DB behavior. Spring TestContext caching reuses contexts with equivalent configurations; mutable singleton caches can leak across tests. `@DirtiesContext` only recreates the context; it does not reset static fields, system properties, `Locale`/`TimeZone`, external DBs/files, or background tasks.

## 31. Actionable Evidence Reports and QA States

| State | Exact meaning | Decision |
| --- | --- | --- |
| VERIFIED | Test ran in appropriate environment, assertions passed, artifacts exist | Record commit/versions and limitations |
| FAILED | Expected and observed differ | Triage and block gate per severity |
| PARTIAL | Only some requirements or boundaries have evidence | Record gaps and owners |
| BLOCKED | Cannot run due to missing Docker, credentials, or environment | Never mark PASS |
| NOT_IMPLEMENTED | Missing tests or required capability | File ticket, owner, deadline/mitigation |
| NOT_APPLICABLE | Out of approved scope | Document rationale |

An **illustrative record**, not an actual run result:

```json
{
  "requirementId": "ORD-11",
  "test": "RealHttpOrderTest.postCommitsAndGetReturnsSameReceipt",
  "environment": "Java17/Boot3.5/H2",
  "expected": [
    "HTTP 201",
    "Location matches generated ID",
    "HTTP GET returns stored receipt",
    "SQL count = 1"
  ],
  "execution": "EXAMPLE_NOT_EXECUTED",
  "limitations": [
    "PostgreSQL not proven",
    "TLS/ingress not proven",
    "concurrent duplicate handling not proven"
  ]
}
```

**Important:** When publishing lessons or reviewing unexecuted code, keep the `EXAMPLE_NOT_EXECUTED` label. “Source defines 18 `@Test` methods” is a structural fact; “18 tests PASS” can only come from the test runner.

## 32. CI, Test Counts, Coverage, and Artifacts

Run:

```bash
./gradlew clean test
```

Typical JUnit/Gradle artifacts:

```text
build/test-results/test/*.xml
build/reports/tests/test/index.html
```

Archive **commit SHA, JDK/Boot/DB versions, test IDs, environment, input fixtures, executed/skipped/failed counts, and report URLs**. A green build with filtered or skipped tests cannot verify full requirements. When running Testcontainers, ensure a Docker-compatible runtime in CI; if the job is required, never skip it silently.

JaCoCo LINE/BRANCH coverage indicates executed code paths but **does not** measure assertion quality. `assertDoesNotThrow` can stay green while computing the wrong price; real tests must assert exact `totalCents`, HTTP status/body, and final DB state.

With mutation testing (PIT), a mutant turning `quantity > 10` into `quantity >= 10` should be killed by the `qty=10` unit test. Even so, mutation scores include equivalent mutants and never replace compliance or contract tests.

CI should separate jobs by risk: fast pure/Mockito/MVC/JDBC tests, real HTTP integration, optional real DB containers, and contract/security/performance suites. On failure, upload logs and reports using CI `always()`, but **never** swallow exit codes with `|| true`.

## 33. Common Mistakes

1. Using a unit policy test to claim the HTTP API is verified.
2. Relying solely on Mockito stubs to claim database constraints pass.
3. Labeling `MockMvc` as a real HTTP socket test.
4. Treating H2 as proof of PostgreSQL JSONB, locking, or transaction behavior.
5. Marking PASS when container tests skipped due to missing Docker.
6. Testing `@Transactional` with `new Service()` bypassing the Spring proxy.
7. Assuming test transaction rollback covers the HTTP server thread.
8. Using `assertTimeoutPreemptively`, pushing DB work outside the `ThreadLocal` transaction.
9. Asserting only 201 without checking `Location`, JSON, or DB state.
10. Testing only happy paths while ignoring negative, null, and boundary cases.
11. Computing expected values with the method under test instead of an independent oracle.
12. Defining tests that the JUnit runner never discovers.
13. Having high coverage with assertion-free tests.
14. Skipping provider verification and trusting only consumer fake responses.
15. Running concurrency tests without awaiting all workers and asserting final state.
16. Calling `@WithMockUser` tests proof of JWT signature integration.
17. Omitting checks for 401/403 and no side effects on critical auth requirements.
18. Mutating global system properties, `Locale`, or `TimeZone`, making CI flaky.
19. Letting mutable Spring singleton state leak across the TestContext cache.
20. Loading full Spring contexts for every unit test, slowing suites and obscuring failures.
21. Failing to clean up HTTP-committed rows or executors after tests.
22. Omitting evidence limitations in QA reports.
23. Using unpinned or uncontrolled images in Docker/Testcontainers tests.
24. Uploading test reports or trace logs containing PII or secrets publicly.
25. Using laptop benchmarks to guarantee production SLOs.

## 34. Matrix Completion Checklist

**Requirements:** Does every entry have an ID and measurable acceptance criterion? Are risk, owner, and priority set? For bounded conditions, are exact boundary and out-of-bounds cases included? Are negative failure and side-effect requirements specified?

**Test design:** Is the chosen test boundary strong enough without over-using full contexts? Are unit, mock, MVC, JDBC, HTTP, container, contract, security, and performance scopes separated? Where mocks are used, are the faked parts documented?

**Evidence:** Do assertions check exact values, statuses, bodies, and exceptions? Are interactions/`noInteractions` verified? Are post-commit SQL queries checking persistence? Are environment, fixtures, versions, and execution artifacts recorded? Are discovered methods separated from executed methods?

**Limitations:** Is H2 vs PostgreSQL documented? `MockMvc` vs real TCP? Test thread vs server thread transactions? Contract mocks vs real providers? Security fixtures vs real token verification? Load test topology vs production?

**CI:** Did required jobs execute without silent skips? Is a Docker runtime available if Testcontainers are required? Are JUnit XML reports, HTML reports, coverage, and logs published with proper access controls? Are `PARTIAL`/`BLOCKED`/`NOT_IMPLEMENTED` items tracked with owners instead of marked PASS? Are gaps revisited whenever requirements change?

**Conclusion:** **The requirements – evidence – limitations matrix** turns “lots of tests” into “justified confidence in critical behavior.” A single requirement may demand multiple layers of evidence; a test may prove one boundary thoroughly while proving nothing about another. Select tests by risk, write independent assertions, inspect real artifacts, and proactively document **what remains unproven**. That is how Spring Boot testing guides release decisions rather than merely counting green checkmarks.

## 35. Official References

- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `MockMvc`, `RANDOM_PORT`, slices, transactional caveats.
- [Spring Boot 3.5 – Test Slices](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html): `JdbcTest`/`DataJdbcTest`/`DataJpaTest`/`JsonTest`/`RestClientTest`.
- [Spring Boot 3.5 – Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `@ServiceConnection`, `@Container`, Docker lifecycle.
- [Spring Framework – Test-managed Transactions](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): `ThreadLocal` rollback and preemptive timeouts.
- [Spring Framework – MockitoBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): bean overrides and mocks.
- [Spring Framework – MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): MVC contracts without a real server.
- [Spring Framework – TestContext Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): context lifecycle and shared state.
- [JUnit Jupiter 5 User Guide](https://docs.junit.org/5.12.2/user-guide/): tests, assertions, and extensions.
- [Mockito](https://site.mockito.org/): verification and mock lifecycle.
- [Testcontainers for Java](https://java.testcontainers.org/): real DB/broker integration.
- [JaCoCo Counters](https://www.jacoco.org/jacoco/trunk/doc/counters.html): line/branch limitations.
