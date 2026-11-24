# Testing Roadmap: From Plain Java to Multi-Component Integration in Spring Boot

## 1. Why Learn in This Order?

A Spring Boot application has many layers of responsibility: business rules, orchestration services, HTTP controllers, JSON mapping, security, Spring configuration, database access, and sometimes external APIs or message brokers. No single test type checks all of those responsibilities effectively. A sensible learning path is to **start from the smallest behavior that can be verified independently**, then deliberately widen the test boundary when you need evidence of collaboration.

Mental model:

```text
Plain Java rules
    ↓ add simulated collaborators
Service + mock/fake (still without booting Spring)
    ↓ add part of Spring infrastructure
Web slice / persistence slice
    ↓ wire real beans and application classes
@SpringBootTest + MockMvc + database
    ↓ add deployment environment and real dependencies
HTTP on real port + database/containers + connected systems
```

“Bigger” does not mean “better”. Smaller tests are usually fast, low-noise, and pinpoint bugs near their source; broad integration tests catch wiring errors that unit tests cannot see. A good test suite combines both according to system risks.

| Stage | Target and Boundary | Spring Context | Primary Evidence | What It Cannot Prove |
| --- | --- | --- | --- | --- |
| 1. Plain Java unit | Functions, rules, domain objects | No | Logic, data boundaries, exceptions | Dependency injection, HTTP, SQL |
| 2. Unit with mock/fake | Service and simulated dependency ports | No | Service decisions, collaborator calls | Real contracts between beans, DB |
| 3. Slice | Subset of web, JPA, JSON... | Yes, only required parts | Mapping, validation, serialization, JPA queries/mapping | Full application flow |
| 4. App integration | Controller → service → repository → DB | Yes, near/full | Bean config and data flowing across layers | Real interactions with unattached services |
| 5. Infrastructure/flow integration | Real HTTP, DB/containers, queues, or protocol-level simulated APIs | Yes and related infrastructure | Environment config, protocols, transactions, connection errors | Every production issue |

**Test-type decision question:** “If this bug happened, what is the smallest layer sufficient to reproduce and prove it?” Only widen scope when the new boundary holds behavior that needs verification.

## 2. Minimal Preparation Before Writing Tests

With Java 17+ and a Spring Boot project having JUnit Jupiter, Mockito, and testing libraries from the dependency set matching your Spring Boot version, organize source code in the familiar layout:

```text
src/
├── main/java/example/
│   ├── ShippingFee.java
│   └── CheckoutService.java
└── test/java/example/
    ├── ShippingFeeTest.java
    └── CheckoutServiceTest.java
```

In a Gradle project using Spring Boot 3.x, the common setup is:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an illustrative configuration snippet—add it to your existing build if equivalent declarations are missing; do not create duplicate `dependencies` or `test` blocks. In Spring Boot 4.x, feature-specific test starters may be split; check dependencies and annotation packages for your exact version.

Run tests with the project's own Gradle Wrapper:

```bash
./gradlew test
./gradlew test --tests example.ShippingFeeTest
```

On Windows PowerShell, use `.\gradlew.bat test` or `.\gradlew.bat test --tests example.ShippingFeeTest`. These commands assume the project has configured JUnit Platform and dependencies; there is no need to start the Spring Boot app to run the first two unit tests. With Maven, the standard command is `mvn test` when the build configures the corresponding test engine.

Each test should follow **Arrange – Act – Assert**: prepare data, execute one behavior, verify one meaningful result. Test names describe the rule, e.g., `freeShippingAtThreshold` instead of `test1`.

## 3. Stage 1 — Unit Tests Completely Without Spring

Suppose the shipping fee is 30,000 VND if the order subtotal is under 500,000 VND, free from 500,000 VND upward; negative subtotals are invalid. This is a pure rule, requiring no beans, databases, or mocks.

**File `src/main/java/example/ShippingFee.java`:**

```java
package example;

public final class ShippingFee {
    private ShippingFee() {}

    public static long forSubtotal(long subtotal) {
        if (subtotal < 0) {
            throw new IllegalArgumentException("subtotal must be non-negative");
        }
        return subtotal >= 500_000L ? 0L : 30_000L;
    }
}
```

**File `src/test/java/example/ShippingFeeTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingFeeTest {
    @ParameterizedTest
    @CsvSource({
        "0, 30000",
        "499999, 30000",
        "500000, 0",
        "800000, 0"
    })
    void calculatesFeeAtBoundaries(long subtotal, long expectedFee) {
        assertEquals(expectedFee, ShippingFee.forSubtotal(subtotal));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> ShippingFee.forSubtotal(-1L));
    }
}
```

These two files compile and run in a project declaring JUnit Jupiter. `ShippingFee.java` alone compiles with `javac src/main/java/example/ShippingFee.java`; the test file requires JUnit on the test classpath, so use the build tool. There is no business stdout: passing tests are reported by the runner as **passed**, with exact counts/messages depending on Gradle and version.

Key takeaways:

- Test **equivalence partitions** and **boundary values** (499,999 and 500,000) instead of just one “nice” input.
- Verify both valid and exception paths without starting `ApplicationContext`.
- Do not slap `@SpringBootTest` onto a plain Java rule: it increases runtime and failure surface without adding evidence.
- Monetary rules here use `long` in whole VND units; when fractional values or multiple currencies exist, pick an appropriate money model/`BigDecimal` and specified rounding rather than defaulting to `double`.

**Stage completion check:** you can point out which specific test catches a change at the 500,000 threshold, explain why Spring is unneeded, and add one new boundary case.

## 4. Stage 2 — Service Unit Tests with Mockito, Still Without Spring

Services often decide **when** to invoke dependencies. For example, checkout calls a payment gateway and then saves a receipt ID. We test orchestration decisions using simulated collaborators, without executing real payments or database writes.

**File `src/main/java/example/CheckoutService.java`:**

```java
package example;

import java.util.Objects;

public final class CheckoutService {
    public interface PaymentGateway {
        String charge(long amount);
    }

    public interface ReceiptStore {
        void save(String receiptId);
    }

    private final PaymentGateway gateway;
    private final ReceiptStore store;

    public CheckoutService(PaymentGateway gateway, ReceiptStore store) {
        this.gateway = Objects.requireNonNull(gateway);
        this.store = Objects.requireNonNull(store);
    }

    public String checkout(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        String receiptId = gateway.charge(amount);
        store.save(receiptId);
        return receiptId;
    }
}
```

**File `src/test/java/example/CheckoutServiceTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class CheckoutServiceTest {
    @Test
    void chargesThenStoresReceipt() {
        var gateway = mock(CheckoutService.PaymentGateway.class);
        var store = mock(CheckoutService.ReceiptStore.class);
        when(gateway.charge(120_000L)).thenReturn("pay-42");

        var service = new CheckoutService(gateway, store);
        String result = service.checkout(120_000L);

        assertEquals("pay-42", result);
        verify(gateway).charge(120_000L);
        verify(store).save("pay-42");
    }

    @Test
    void invalidAmountDoesNotTouchDependencies() {
        var gateway = mock(CheckoutService.PaymentGateway.class);
        var store = mock(CheckoutService.ReceiptStore.class);
        var service = new CheckoutService(gateway, store);

        assertThrows(IllegalArgumentException.class,
                () -> service.checkout(0L));
        verifyNoInteractions(gateway, store);
    }
}
```

Mockito creates doubles and records interactions; `CheckoutService` itself is still created with `new`. This test verifies the service returns the right ID, passes the right amount, and avoids calling dependencies when input is invalid. It does **not** verify that the database received a row, HTTP returned 201, the real payment gateway works, or Spring wiring is valid.

Tool distinctions:

- **Stubs** return preset data; **mocks** often also verify interactions.
- **Fakes** are simplified working implementations, such as a `Map`-backed receipt store. Fakes are helpful when you want to verify state instead of call counts.
- Mock **boundaries you control** (payment gateway, clock, external gateway) and verify observable outcomes. Avoid mocking every value object, DTO, collection, or internal method.
- With a long dependency chain, a test checking only `verify(...)` does not necessarily reflect business outcomes; prefer asserting outputs/state first, and verifying key calls second.

**Stage completion check:** tests run without Spring; you can explain which dependencies are simulated, which kinds of bugs can be caught, and why tests with real adapters are still needed.

## 5. Stage 3 — Adding Spring Selectively: Slice Tests

A **slice test** loads a subset of the Spring context to verify framework behavior at a specific boundary, typically faster and easier to diagnose than running the full application. A slice is not a “pure unit test”: it includes Spring, yet intentionally avoids loading every bean.

### 5.1. HTTP Slice with `@WebMvcTest`

Suppose when wiring the app, `CheckoutController` handles `POST /checkout?amount=120000` and calls `CheckoutService`. Illustrative controller:

```java
@RestController
@RequestMapping("/checkout")
class CheckoutController {
    private final CheckoutService service;

    CheckoutController(CheckoutService service) {
        this.service = service;
    }

    @PostMapping
    ResponseEntity<Map<String, String>> create(@RequestParam long amount) {
        String id = service.checkout(amount);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("receiptId", id));
    }
}
```

Illustrative MVC slice test for Spring Boot 3.4+ with Spring Framework 6.2+ (add corresponding imports):

```java
@WebMvcTest(CheckoutController.class)
class CheckoutControllerWebTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    CheckoutService service;

    @Test
    void returns201AndReceiptId() throws Exception {
        when(service.checkout(120_000L)).thenReturn("pay-42");

        mvc.perform(post("/checkout").param("amount", "120000"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.receiptId").value("pay-42"));
    }
}
```

Here `MockMvc` goes through Spring's MVC request handling, mapping, and response conversion **without opening a real HTTP server**; `CheckoutService` is a mock bean. You need static imports for `post`, `status`, `jsonPath` from Spring MockMvc, `when` from Mockito, plus annotations from the right packages.

**Version note:** in Spring Boot 3.3 and earlier, Spring Boot's `@MockBean` was standard; Spring Framework 6.2+ introduced `@MockitoBean`, which newer Spring Boot versions prefer. Spring Boot 4.x moves some test packages/dependencies by module; check your project version before copying imports. If Spring Security filters are active in the slice, requests need an appropriate identity/CSRF; 401/403 errors may reflect security policy rather than broken mapping.

An MVC slice tests routing, statuses, body, JSON, validation, error handling (e.g., `@ControllerAdvice`), and configured filters; it does not prove real service logic or JPA persistence.

### 5.2. Persistence Slice with `@DataJpaTest`

Use `@DataJpaTest` when checking entity mapping, repositories, queries, constraints, and JPA interactions. The example below is **only an excerpt**: the project needs an existing `ReceiptEntity` with a matching constructor and `ReceiptJpaRepository` with `findByGatewayId`.

```java
@DataJpaTest
class ReceiptJpaRepositoryTest {
    @Autowired
    ReceiptJpaRepository repository;

    @Test
    void canFindPersistedReceipt() {
        repository.saveAndFlush(new ReceiptEntity("pay-42"));

        assertThat(repository.findByGatewayId("pay-42"))
                .isPresent();
    }
}
```

Most `@DataJpaTest` setups default to an embedded database when a suitable driver is present; tests run in transactions and roll back after each test. Depending on the project, choose a real database or Testcontainers to check SQL compatibility, migrations, constraints, and how the production database handles data. H2 does not always replicate PostgreSQL/MySQL behavior accurately (data types, syntax, transactions, indexes).

Choose slices by boundary:

| Want to Verify | Starting Point |
| --- | --- |
| Routes, statuses, JSON/validation in Servlet MVC | `@WebMvcTest` + `MockMvc` |
| Entities, repositories, JPA queries | `@DataJpaTest` |
| Reactive WebFlux HTTP handling | `@WebFluxTest` + `WebTestClient` |
| Custom JSON configuration | JSON test slice matching your version |
| Only a function or orchestration service | Plain JUnit/Mockito, no slice needed yet |

Separate slices do not automatically combine into a full integration test. If bugs only appear when service, repository, transaction, and controller run together, widen the boundary.

**Stage completion check:** you can name one thing the MVC slice guarantees, one thing the JPA slice guarantees, and at least one thing neither can guarantee when run alone.

## 6. Stage 4 — Integrating Multiple Real Layers in the Same Application

At this point, we want to verify a flow: **request → controller → service → storage adapter → JPA repository → database**. This is the right point for `@SpringBootTest`; it builds an application context close to the real app. You can pair it with `@AutoConfigureMockMvc` to test the MVC flow without opening a TCP port.

For this example to connect the stages, the app must supply real beans for `CheckoutService` and `ReceiptStore` (adapting `ReceiptJpaRepository`), while `PaymentGateway` is a port that can be swapped for a mock in tests. The controller and repository snippets above are **illustrative components that must be implemented/wired in the project**, not a complete app solely by copying the test below.

```java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class CheckoutFlowIT {
    @Autowired
    MockMvc mvc;

    @Autowired
    ReceiptJpaRepository receipts;

    @MockitoBean
    CheckoutService.PaymentGateway gateway;

    @BeforeEach
    void cleanData() {
        receipts.deleteAll();
    }

    @Test
    void httpCheckoutPersistsReceipt() throws Exception {
        when(gateway.charge(120_000L)).thenReturn("pay-42");

        mvc.perform(post("/checkout").param("amount", "120000"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.receiptId").value("pay-42"));

        assertThat(receipts.findByGatewayId("pay-42"))
                .isPresent();
    }
}
```

This test gets its strength from **real wiring**: if beans are missing, mappings misconfigured, data conversion broken, repository fails to save, or transactions/configuration are wrong, it can catch them. The payment gateway stays intentionally mocked because CI should not call real payment processors.

Decisions to state explicitly:

1. `@SpringBootTest` defaults to `webEnvironment = MOCK`; it creates a mock web environment for web apps, **without starting a real server**. `@AutoConfigureMockMvc` adds the tool to dispatch requests in-process.
2. `@SpringBootTest(webEnvironment = RANDOM_PORT)` actually starts an HTTP server on a random port; use a suitable HTTP client to verify the real transport path.
3. `@ActiveProfiles("test")` only selects a profile; it does not automatically ensure test DBs, credentials, or external services are isolated. Configure datasources, dummy secrets, test endpoints, and resources properly.
4. Placing `@Transactional` on a Spring test usually rolls back the test thread's transaction afterward; with `RANDOM_PORT`, client and server run on different threads and transactions, so **test rollback does not automatically roll back server-committed data**.
5. Cleanup choices must match the test level: rollback, dedicated transactions, truncate/isolated schema, unique data, or isolated containers. Never depend on test execution order.
6. If Spring Security is present, test both permitted and denied permissions; do not disable filters merely to turn tests green when those tests are meant to verify security.

**Stage completion check:** you have at least one test proving observable outcomes across two real layers (e.g., HTTP 201 **and** receipt saved in DB), while clearly identifying which dependencies remain simulated.

## 7. Stage 5 — Attaching Real Dependencies and Verifying Protocols/Environments

When the risk lies in differences between environments and doubles, extend tests to infrastructure components. For example: service connecting to real PostgreSQL, migrations running on startup, queries using JSONB, Redis caching, Kafka publish/consume, or HTTP clients with timeouts/retries.

**Testcontainers** provisions databases/brokers inside containers for testing. With Spring Boot supporting service connections, a PostgreSQL skeleton looks like:

```java
@Testcontainers
@SpringBootTest
@AutoConfigureMockMvc
class CheckoutPostgresIT {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // @Autowired MockMvc, repository, and @Test methods similar to the Stage 4 flow.
}
```

This is an **illustrative skeleton**, not a standalone test file: it requires Testcontainers/JUnit integration dependencies, the PostgreSQL driver, Spring Boot Testcontainers support, Docker/a container runtime, and matching application classes. `@ServiceConnection` can supply connection details to auto-configuration; when integrating technologies/versions without support for it, `@DynamicPropertySource` is another dynamic configuration mechanism. Verify exact imports for your version.

Deciding what should be real vs. simulated:

- **Real database via container:** suits dialect-specific queries, migrations, schema/constraints, isolation, and transactions.
- **External HTTP services:** prefer mock server/WireMock over real HTTP to verify URL, method, headers, payload, error codes, timeouts, and retries; avoid accidentally calling third-party or production APIs.
- **Real message broker via container:** suits proving serialization, topics/queues, consumer groups, retries/DLQ, and asynchronicity; merely mocking the publisher only proves the call.
- **Real HTTP server:** use `RANDOM_PORT` when checking sockets, container filters, cookies, redirects, and network serialization; `MockMvc` suffices for most internal MVC contracts.
- **UI/user end-to-end:** add only when needed to verify UI interactions or deployed service chains; keep counts small since they run slowly and are noise-prone.

For example, a full checkout flow test can catch bugs individual unit tests miss: incoming JSON failing to bind, uncommitted transactions, repository saving wrong currency/ID, migrations missing indexes/constraints, HTTP client sending wrong headers, or consumer reading mismatched message schemas.

## 8. Recommended Practice Sequence

Use **one end-to-end business story**, adding infrastructure stage by stage to see clearly when each kind of bug surfaces. For the checkout scenario:

| Step | Task | Completion Criteria |
| --- | --- | --- |
| 1 | Write shipping fee tests at boundary values | Tests run without Spring; breaking the threshold turns tests red |
| 2 | Test checkout service with mock payment/store | Proves correct amount, receipt ID, and no external calls on invalid input |
| 3 | Create an MVC slice for the checkout endpoint | Proves request, response, validation, and 4xx/2xx statuses |
| 4 | Create a JPA slice for receipts | Real write/read, catching mapping or query errors |
| 5 | Wire `@SpringBootTest` + `MockMvc` + test DB | A request goes through controller, service, repository, and confirms DB state |
| 6 | Swap test DB for PostgreSQL Testcontainers | Catches SQL/schema/migration differences vs. real DB |
| 7 | Test outbound HTTP/broker and an intentional failure flow | Verifies protocol, timeout/retry, or event propagation |

Not every project needs all seven steps. An algorithmic library may focus on steps 1–2; a service with a database and external integrations needs more of 4–7. Choose by **the impact if a bug slips through**, rather than setting a quota like “all tests must boot Spring”.

### Extra Practice: Same Bug, Three Catch Points

Suppose sending amount = 0 still causes the system to create a payment.

1. Unit test `CheckoutServiceTest` fails if the service does not block amount ≤ 0.
2. MVC slice can fail if the API must reject with 400 yet the controller lacks validation/exception mapping. Mocking the service to return normally will not by itself prove the domain rule.
3. Full integration test can prove a 400 response **and** that the database receipt count did not increase; this is end-to-end data-protection evidence.

These three layers answer three different questions. Do not treat three identical tests as necessary; pick assertions characteristic of each boundary.

## 9. Tips for Fast, Reliable, Valuable Tests

### Data Design and Isolation

- Create the minimal data needed per test using clear factories/builders. Avoid shared fixtures full of hidden defaults.
- Every test must run independently in any order; never let test A prepare data for test B.
- Fix time using an injected `Clock` in services; avoid depending on `LocalDateTime.now()`, time zones, or CI wall-clock time.
- Use unique IDs, transaction rollbacks in the right places, or boundary-level DB cleanup; never share a production DB.
- For async systems, wait on bounded conditions (polling/Awaitility), not fixed `Thread.sleep` calls guessing when a message was processed.
- Set sensible HTTP/DB timeouts; simulate network failures and verify retry/idempotency behavior if required.
- If tests depend on Testcontainers, document Docker/runtime requirements clearly in CI run instructions.

### Performance and Suite Structure

- Keep plain unit tests as the fast feedback lane during coding; group heavy integration tests under appropriate pipelines/execution profiles.
- Spring TestContext caches contexts; differing configs/profiles/mocks increase the number of loaded contexts. Do not use `@DirtiesContext` unless resetting the context is genuinely needed.
- Use `@SpringBootTest` when multi-bean interaction must be proven; use slices when web/JPA contracts suffice; use plain JUnit when only logic is needed.
- If splitting out an `integrationTest` task in Gradle, configure the matching source set/test suite; `./gradlew integrationTest` is not a guaranteed default task in every project.

### Common Errors and Fixing at the Right Layer

| Symptom | Common Cause | How to Verify/Fix |
| --- | --- | --- |
| Tiny unit test takes forever to start | Unnecessary `@SpringBootTest` | Remove context, instantiate with `new` |
| MVC slice fails to find service bean | Slice does not scan regular services | Provide mock or test configuration at the boundary |
| Service test passes yet REST returns 404/400 | Mocks only verify service, not MVC mapping/binding | Add `@WebMvcTest` |
| JPA test passes on H2 yet fails in production | Dialect/schema/transaction differs from real DB | Testcontainers with matching DB engine |
| Integration test flakes when run in a group | Leftover state, duplicate data, time/order dependence | Isolate data and time sources |
| `@Transactional` leaves data behind after real HTTP | Server transaction differs from test thread transaction | Explicit DB cleanup or isolated schema/container |
| Request gets 401/403 | Security filters, authentication, or CSRF | Configure test security per policy, assert expected status |
| Mock verify test passes yet data is wrong | Asserted calls only, missing observable outcomes | Assert actual response, state, or record |

Do not confuse **high coverage** with **sufficient evidence**: coverage only shows lines executed, not that assertions verify the right rules. When fixing a bug, prioritize adding a test that reproduces the bug before fixing it, then keep it as a regression guard.

## 10. Test Selection Map and Self-Review Checklist

```text
Need to test a pure rule?
  └─ Yes → Plain JUnit, boundary-value table.
  └─ No: does the service have dependencies?
       └─ Yes, only need service decisions → JUnit + mock/fake.
       └─ Need framework verification (HTTP/JPA)?
            └─ Single slice → @WebMvcTest / @DataJpaTest.
            └─ Multiple layers in one request → @SpringBootTest + MockMvc.
                 └─ Need real protocol/DB/network → RANDOM_PORT / Testcontainers /
                    mock server / broker matching the risk.
```

Before considering a stage complete, ask yourself:

- **Which behavior** is the test verifying and which assertion proves it?
- Which layers/components are **real**, and which are mocks/fakes? Did I accidentally mock out the very thing being tested?
- Does the detected failure belong to the current test boundary, or should a slice/integration test be added?
- Are data, time, network, profiles, secrets, and execution order isolated enough to repeat reliably in CI?
- If the test is green yet production fails, what **evidence gap** remains?
- Is a heavy integration test catching unique wiring bugs, or merely repeating what unit tests already cover?

**Target outcome:** learners can start with Spring-free Java tests, deliberately add Mockito to isolate dependencies, choose the right slice for adapters/framework behavior, then build multi-layer flows and extend to real databases/protocols when risk demands it. The value of this roadmap lies in **knowing why to widen test boundaries** while keeping tests as simple as possible.

## Official Documentation for Version Cross-Reference

- Spring Boot — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Boot — Testcontainers: https://docs.spring.io/spring-boot/reference/testing/testcontainers.html
- Spring Framework — Mockito bean overrides: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html
- JUnit User Guide: https://docs.junit.org/current/user-guide/
- Testcontainers Java: https://java.testcontainers.org/