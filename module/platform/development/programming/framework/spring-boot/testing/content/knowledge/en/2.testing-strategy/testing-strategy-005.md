# Selecting Real Components, Fakes, Stubs, Mocks, or Containerized Services

In a Spring Boot testing strategy, the first question is not “Should we use Mockito or Testcontainers?” but **which components must run for real so the test catches the specific defect we care about**. A `PaymentGateway` might be a stub in a pricing test, a mock in a charge-command test, or a real sandbox connection in an integration test. Picking the wrong one can make tests fast yet worthless, or slow and hard to diagnose.

**Learning objectives:** distinguish real components, fakes, stubs, mocks, and containerized services; choose based on scope and risk; write unit and integration tests with clear evidence; recognize the limits of each choice.

## 1. Clearly Distinguishing Each Component Type

*Test double* is the umbrella term for an object replacing a collaborator in a test. “Mock” is often used colloquially for all of them, but when designing tests you must distinguish their roles.

| Component | Nature | Use When | Cannot Prove on Its Own |
| --- | --- | --- | --- |
| **Real component** | Actual production implementation/configuration within the test scope | Testing business logic, validation, mappers, Spring wiring, real transactions, or security | Other dependencies that have been replaced |
| **Fake** | A working but simplified implementation, e.g., a repository backed by a `HashMap` | Needing state across multiple read/write steps in unit tests | SQL, locking, unique constraints, rollbacks, latency, or real DB errors |
| **Stub** | Returns preconfigured values or errors | Fixing inputs to exercise success/failure branches | Whether the real dependency handles the request/protocol properly |
| **Mock** | Records/verifies calls, arguments, and invocation counts | Contract requires proving an outbound command was issued | Whether the external system actually completed the command |
| **Real service in a container** | Runs real PostgreSQL/Redis/Kafka… from an image in an ephemeral environment | Defect depends on SQL dialect, driver, schema, protocol, transactions, or integration config | Production scale and full production infrastructure |

A **Spy** is another variant: most real logic runs while calls to the object are observed. Avoid spies if they are only used to reach internal details the test does not need to know about.

Two crucial points:

- An object created by `Mockito.mock(...)` **can act as a stub** when you only configure `when(...).thenReturn(...)`, or as a **mock** when you use `verify(...)` to check interactions. The role depends on what the test asserts, not the API name.
- PostgreSQL inside Testcontainers is still **real PostgreSQL**, only deployed elsewhere. A `HashMap`-based fake repository is a simplified implementation and lacks PostgreSQL's full semantics.

## 2. Start by Asking “What Does This Test Need to Prove?”

Before choosing dependencies, clarify:

1. **Behavior:** which input or event triggers the feature?
2. **Observable outcome:** which return value, persisted state, HTTP status/body, message, or call must be right?
3. **Risk:** does correctness depend on SQL, transactions, serialization, security, networking, or real Spring configuration?
4. **Boundary:** are you testing a plain Java class, a Spring slice, multiple beans, or the whole system?
5. **Cost:** which parts can be replaced while preserving the defect signal you want?

From there:

- **Keep real** the logic under test. To test `PricingService`, do not mock `PricingService` itself.
- **Stub** inputs when you need deterministic data or exceptions to exercise branches.
- **Fake** state when you need multiple reads/writes but storage-engine behavior is not the focus.
- **Mock** side effects when you must prove an outbound command was issued with exact arguments/counts.
- **Container** when real infrastructure semantics are the subject of the test: queries, constraints, migrations, transaction isolation, Redis TTL, broker acknowledgements…
- **Real Spring context** when testing dependency injection, AOP, filter chains, validation, and framework beans.

The goal is to **replace as little as possible while avoiding replacements that hide the defect**. There is no rule that “unit tests must always mock repositories” or “integration tests must always use Docker.”

## 3. Selection Matrix for Spring Boot

| Scenario | Component That Must Be Real | Useful Replacement | Signal to Assert |
| --- | --- | --- | --- |
| Calculating fees, discounts, taxes | Domain/service | Stub fee config, fake catalog | Total amount, invariants |
| Out of stock must not charge payment | Checkout service | Fake inventory, mock payment port | Stock unchanged; gateway never called |
| Emitting an event with key/payload | Service creating event | Mock publisher | One call with expected arguments |
| MVC binding, JSON, validation, exception mapping | Controller and web MVC pipeline | `@WebMvcTest`, mock collaborating service | HTTP status, body, headers |
| Repository queries, unique constraints, rollbacks | Entities/repositories, transactions, DB driver | PostgreSQL/MySQL in a container | Real data/schema/transaction behavior |
| Spring `@Transactional`, `@Cacheable`, `@PreAuthorize` | Spring-managed bean and required AOP/filters | Replace unrelated I/O if possible | Advice and security effects in action |
| Redis cache expiration or Kafka consumer group | Adapter/driver, Redis/Kafka | Container of the matching service | TTL/ack/ordering/serialization |
| Partner HTTP returns 429/500 or weird JSON | HTTP client, retry/error mapping | HTTP stub server (e.g., WireMock) | Real request hitting stub server and response handling |
| Checking endpoint role rules | Security chain and endpoint | `@WithMockUser` when only testing authorization | 403/200 per role |
| JWT signature / OIDC discovery | Security chain and token validation | Real test tokens / test identity provider | Real protocol verification |
| Multi-layer order placement workflow | Relevant services, repositories, adapters | DB container, stub server for third parties | End-to-end state within chosen scope |

**H2 is not identical to PostgreSQL.** H2 is a real database, but its dialect, data types, isolation levels, and constraints can differ. If your goal is testing PostgreSQL queries, use real PostgreSQL. Similarly, a mocked repository cannot prove a query or entity mapping works.

## 4. Complete Example: Fake for Inventory, Mock for Payment Gateway

Suppose `CheckoutService` checks stock, calculates the charge, sends a payment request, and deducts inventory. We want to test business logic without a Spring context, DB, or network yet. A fake tracks remaining stock; a mock verifies the payment command.

The file `src/test/java/example/CheckoutServiceTest.java` below is self-contained with all interfaces/classes needed for the example. It runs in any Java 17+ project with JUnit Jupiter and Mockito (such as via `spring-boot-starter-test`).

~~~java
package example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class CheckoutServiceTest {

    interface Inventory {
        int stockOf(String sku);
        int priceCents(String sku);
        void decrease(String sku, int quantity);
    }

    interface PaymentGateway {
        void charge(int amountCents);
    }

    static final class CheckoutService {
        private final Inventory inventory;
        private final PaymentGateway payment;

        CheckoutService(Inventory inventory, PaymentGateway payment) {
            this.inventory = inventory;
            this.payment = payment;
        }

        void checkout(String sku, int quantity) {
            if (quantity <= 0 || inventory.stockOf(sku) < quantity) {
                throw new IllegalArgumentException("Not enough stock");
            }

            int amount = Math.multiplyExact(inventory.priceCents(sku), quantity);
            payment.charge(amount);
            inventory.decrease(sku, quantity);
        }
    }

    static final class FakeInventory implements Inventory {
        private int stock;

        FakeInventory(int initialStock) {
            this.stock = initialStock;
        }

        private void requireBook(String sku) {
            if (!"BOOK".equals(sku)) {
                throw new IllegalArgumentException("Unknown SKU");
            }
        }

        @Override
        public int stockOf(String sku) {
            requireBook(sku);
            return stock;
        }

        @Override
        public int priceCents(String sku) {
            requireBook(sku);
            return 1_500;
        }

        @Override
        public void decrease(String sku, int quantity) {
            requireBook(sku);
            stock -= quantity;
        }
    }

    @Test
    void chargesOnceAndDecreasesInventory() {
        FakeInventory inventory = new FakeInventory(3);
        PaymentGateway payment = mock(PaymentGateway.class);

        new CheckoutService(inventory, payment).checkout("BOOK", 2);

        assertEquals(1, inventory.stockOf("BOOK"));
        verify(payment).charge(3_000);
    }

    @Test
    void doesNotChargeWhenStockIsInsufficient() {
        FakeInventory inventory = new FakeInventory(1);
        PaymentGateway payment = mock(PaymentGateway.class);

        assertThrows(IllegalArgumentException.class,
                () -> new CheckoutService(inventory, payment).checkout("BOOK", 2));

        assertEquals(1, inventory.stockOf("BOOK"));
        verifyNoInteractions(payment);
    }

    @Test
    void keepsInventoryWhenChargeFails() {
        FakeInventory inventory = new FakeInventory(3);
        PaymentGateway payment = mock(PaymentGateway.class);
        doThrow(new IllegalStateException("Payment rejected"))
                .when(payment).charge(3_000);

        assertThrows(IllegalStateException.class,
                () -> new CheckoutService(inventory, payment).checkout("BOOK", 2));

        assertEquals(3, inventory.stockOf("BOOK"));
        verify(payment).charge(3_000);
    }
}
~~~

In a Gradle module configured with `spring-boot-starter-test`:

~~~bash
./gradlew test --tests example.CheckoutServiceTest
~~~

**Expected outcome:** all three tests pass (Gradle reports `BUILD SUCCESSFUL` if the full configuration and test runtime are valid); the tests print no stdout. No Spring ApplicationContext or Docker is needed.

Explanation:

- `CheckoutService` runs **for real**, because testing its logic is the goal.
- `FakeInventory` holds state and is asserted directly via `stockOf`, so no internal fake verification is needed. It only knows SKU `BOOK` and does not pretend to simulate DBs, transactions, or concurrency.
- `PaymentGateway` is a Mockito mock because the required observable outcome is the `charge(3_000)` command; `verify` checks for one invocation by default. In the third test, `doThrow` also uses the same mock to **stub a failure**.
- The out-of-stock test verifies both the state outcome and that **no charge command was sent** using `verifyNoInteractions`.
- Do not use `@SpringBootTest` before wiring or framework behavior needs testing.

If you only wanted to test inventory deduction and intentionally ignore payment interaction, you could replace the gateway with a stub:

~~~java
PaymentGateway stubPayment = amountCents -> { };
~~~

This stub returns normally for any amount, but **does not prove a payment command was sent or sent accurately**. When the contract requires issuing a command, a mock with clear assertions is more appropriate.

Important limitation: the example does not handle distributed consistency failures where payment succeeds but inventory update fails. That risk requires transaction/saga or compensation design and dedicated integration tests; it cannot be inferred from the pure Java tests above.

## 5. When You Need Real Services in Containers

Fakes/mocks are well suited for unit tests, but cannot detect:

- PostgreSQL-incompatible queries, index bugs, foreign keys, or unique constraints.
- Entity mappings diverging from the real schema, or broken Flyway/Liquibase migrations.
- JDBC driver issues, connection pool bugs, transaction boundaries, and rollbacks.
- Redis TTLs, serialization, or locking semantics.
- Kafka ack/offset/consumer-group behavior, message codecs, and broker protocols.
- Wrong endpoints, headers, bodies, timeouts, or retries over real HTTP.

For DBs/brokers, use real adapters and containerized services. For partner HTTP services, depending on the goal, use an HTTP stub server to test network requests/responses while controlling replies; call a real sandbox only when verifying the partner side's contract.

### Testcontainers + JDBC Example with PostgreSQL

The following example applies to Spring Boot 3.x with `@ServiceConnection` (since 3.1). The project must have a `@SpringBootApplication` so Spring test discovers configuration in the package hierarchy, Testcontainers-compatible Docker, `spring-boot-starter-jdbc`, `spring-boot-starter-test`, `spring-boot-testcontainers`, `org.testcontainers:junit-jupiter`, `org.testcontainers:postgresql`, and the PostgreSQL JDBC driver. Manage versions via the Spring Boot BOM.

File `src/test/java/example/PostgresJdbcTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;

@JdbcTest
@Testcontainers
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgresJdbcTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void executesPostgresArrayOperator() {
        Boolean result = jdbc.queryForObject(
                "SELECT ARRAY[1, 2, 3] @> ARRAY[2]", Boolean.class);

        assertEquals(Boolean.TRUE, result);
    }
}
~~~

~~~bash
./gradlew test --tests example.PostgresJdbcTest
~~~

**Role of each piece:**

- `@JdbcTest` boots a Spring slice for JDBC; no full web application needed.
- `@AutoConfigureTestDatabase(replace = NONE)` prevents Spring from replacing the datasource with an embedded database.
- `@Testcontainers` and `@Container` manage the PostgreSQL container lifecycle.
- `@ServiceConnection` passes the container's connection details into Spring Boot without hardcoding host/port.
- Real `JdbcTemplate` executes SQL using PostgreSQL's `@>` array operator, catching dialect differences that fakes or H2 cannot represent.

This tests **connectivity and SQL features**, not a business repository. To test `OrderRepository`, keep the real repository, apply your application's schema/migrations, write records, and assert meaningful results, constraints, or rollbacks. If not using `@ServiceConnection`, register `spring.datasource.url`, username, and password with `@DynamicPropertySource` reading dynamic values from the container. Never hardcode container ports.

If a CI environment lacks Docker, container tests will fail due to missing infrastructure; distinguish container startup failures from application logic bugs.

## 6. Choosing Reasonable Test Layers in Spring Boot

| Layer | What Runs for Real | What Is Usually Replaced | Purpose |
| --- | --- | --- | --- |
| **Unit test** | Plain Java service/domain | Stubs/fakes/mocks on dependency interfaces | Business branches, edge cases, required outbound calls |
| **Slice test** | One framework slice: `@WebMvcTest`, `@JsonTest`, `@JdbcTest`, `@DataJpaTest` | Out-of-slice beans; real DB when needed | Binding, JSON, Spring Data mappings, HTTP contracts |
| **Integration test** | Multiple beans, transactions, security, adapters | Containers for infra; stub server for partners | Wiring, configuration, protocols, persistence |
| **End-to-end** | Flow from client across real services | External systems outside test scope | Essential cross-system scenarios |

Annotation reminders:

- `@Mock` with `MockitoExtension` or direct `mock(...)` calls are for unit tests, needing no Spring `ApplicationContext`.
- Inside a Spring test context, to **replace an injected bean**, Spring Boot up through 3.3 typically uses `@MockBean`. From Spring Boot 3.4 onward, `@MockBean` is deprecated in favor of Spring Framework's `@MockitoBean`; Spring Boot 4 removes the older API. Check your module's version and imports before using.
- `@WebMvcTest` focuses on controllers, request binding, and MVC infrastructure; mock services at the boundary when services are not the target. To test full filter chains or real server integration, pick the matching scope.
- `@WithMockUser` helps test role-based authorization with a simulated identity; it **does not** test JWT signatures, token expiration, or real OIDC discovery.

Test counts should reflect risk: many small unit tests for business branches; selective integration tests for database, security, messaging, and serialization; few end-to-end tests for critical flows. Booting many Spring contexts simply because “tests feel higher quality” rarely yields proportional evidence.

## 7. A Repeatable Decision Process

For each collaborator of the object under test:

1. **Does it contain logic or mechanics we must prove?** Keep the real implementation.
2. **Only need preselected return values or errors?** Use a stub, including no-op responses or scripted exceptions.
3. **Need simple state across multiple operations?** Use a small fake with a clear contract and per-test data isolation.
4. **Is calling the dependency itself a business outcome?** Use a mock; `verify` only the exact arguments/counts that truly matter.
5. **Does the defect live in SQL/schema/transactions/protocols/external config?** Use the real adapter with a container or suitable test endpoint.
6. **Need to keep fake behavior aligned with the real adapter?** Add contract/integration tests so the fake never drifts from the contract.
7. **Is the test repeatable locally and in CI?** Fix clocks/randoms/fixtures, and avoid shared mutable state and hardcoded ports.

For example, the same `OrderRepository` has two completely valid roles: in `OrderServiceTest`, a fake repository helps test ordering rules; in `OrderRepositoryIT`, both the repository and PostgreSQL must be real to verify queries and transactions. They prove two different things.

## 8. Common Mistakes

**Mocking the thing you are testing.** If you mock `OrderService` and assert the stubbed return value, the test proves nothing about `OrderService`. Keep the SUT (system under test) real.

**Mocking too deeply.** Mocking controllers, services, mappers, repositories, and domain objects reduces the test to replaying a hardcoded script. Prefer real objects for internal logic and test doubles at I/O boundaries.

**Verifying every internal call.** `verify(repository).save(...)` can break after a valid refactor even though outcomes stay correct. When observable state/responses exist, assert those instead; verify calls when the call itself is the contract.

**Assuming a fake behaves like a database.** A `HashMap` fake does not enforce foreign keys, unique constraints, locking, or rollbacks. Never infer SQL correctness from unit tests using fakes.

**Stubs hiding network bugs.** Mocking an HTTP client to return a parsed DTO leaves URLs, methods, headers, JSON, status mapping, and retries untested. Use a stub server on the HTTP wire to check protocol behavior as needed.

**Replacing beans disables AOP.** If the target is `@Transactional`, `@Cacheable`, `@Retryable`, or security advice, do not mock the bean or instantiate it with `new` outside the context and assume Spring mechanisms work.

**Using containers for every test.** Containers carry startup overhead and require Docker. Use them only when real semantics are the goal; keep fixtures lean, clean up data, and manage lifecycle and isolation properly.

**Non-deterministic tests.** System clocks, unseeded randomness, `Thread.sleep`, fixed ports, shared data, and test-order dependencies make suites flaky. Inject `Clock`, fix seeds, wait on bounded conditions, use dynamic ports, and isolate fixtures.

**Confusing passing tests with complete evidence.** Unit tests with mocks/fakes prove logic under assumptions about collaborators; integration tests verify specific real connections; end-to-end and operational tests cover other scopes. Every test should be clear about its boundary.

## 9. Pre-Completion Checklist

- [ ] Test names describe observable behavior, and assertions check the exact expected outcomes.
- [ ] The component containing the logic under test runs for real.
- [ ] Every stub/fake/mock has a concrete rationale and does not mask the defect signal being sought.
- [ ] Fakes simulate only stated small invariants; DB/broker invariants have real tests.
- [ ] Mocks verify only contractual interactions, avoiding coupling to unnecessary implementation details.
- [ ] Query/schema/transaction/protocol tests run on real technology when that is the primary risk.
- [ ] Spring Boot annotations and dependencies match the module version.
- [ ] CI provides Docker if Testcontainers is needed; data and ports are isolated.
- [ ] The suite covers both business errors and connectivity failures at critical boundaries.

**Mnemonic:** *real* for behavior under test; *stub* for controlled inputs; *fake* for simplified state; *mock* for required interactions; *container* for real infrastructure semantics. Always choose based on the defect you want the test to catch.

### References

- Martin Fowler, [Test Double](https://martinfowler.com/bliki/TestDouble.html) — terminology for fake, stub, mock, spy.
- [Spring Framework: `@MockitoBean` and `@MockitoSpyBean`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html) — overriding beans in Spring tests.
- [Spring Framework: `@DynamicPropertySource`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dynamicpropertysource.html) — registering dynamic properties in integration tests.
- [Spring Boot 3.4 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes) — deprecation of `@MockBean`.