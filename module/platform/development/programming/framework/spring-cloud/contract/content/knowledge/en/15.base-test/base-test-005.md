# Configuring Fixtures, Authentication, and Initial State in the Base Test

In **Spring Cloud Contract**, a contract file describes what the **producer** must satisfy when the **consumer** sends a request or receives a message. **Contract Verifier** can generate tests from Groovy/YAML DSL contracts, but those tests do not automatically know which order to prepare in the database, which authentication token to use, or what state to reset the application to before each run. That is a core job of the **base test**.

This article belongs to the **Base test** chapter of the **SPRING_CLOUD_CONTRACT** module. We will build a base test for an HTTP producer with Spring Boot, JUnit 5, and MockMvc: **creating deterministic fixture data**, **configuring authentication with Spring Security**, and **resetting initial state to match contract assumptions**. Then we connect producer test results to published stubs for consumers using Stub Runner and to CI verification gates.

A key takeaway: **fixtures are not the contract**. The contract specifies observable requests and responses; fixtures create the preconditions so the producer can genuinely satisfy them. If fixtures are wrong, tests can fail due to missing data rather than an API violation; if fixtures are too permissive or mock the wrong thing, tests can pass even though the real producer misses critical behavior.

## 1. What does the base test provide?

In a project configured with Spring Cloud Contract Verifier, generated tests typically **extend a base class** specified in the plugin. This class sets up the shared environment without replacing each contract's assertions.

| Responsibility | Example | If missing or wrong |
| --- | --- | --- |
| **Test context** | Boots Spring Boot, controllers, security filters, and required repositories. | Generated tests fail to run or target the wrong object. |
| **HTTP test client** | Binds `RestAssuredMockMvc` to `MockMvc` in `MOCKMVC` mode. | Requests never reach the controller under test. |
| **Fixtures** | Order ID `42` exists with `status=PAID`. | A `200` contract test gets `404` due to missing data. |
| **Authentication/authorization** | Test token carries scope `orders.read`, or security identity matches policy. | Success tests get `401`/`403`, or security checks are unintentionally bypassed. |
| **Initial state** | Clears old data and re-seeds before each test; resets mocks or clock when needed. | Tests depend on execution order and flake between pass and fail. |
| **Isolation** | Every test starts from predictable state, even when re-run individually. | One test mutating data breaks subsequent tests. |

~~~mermaid
flowchart TD
    A["Groovy/YAML contracts"] --> B["Contract Verifier generates tests"]
    B --> C["Generated test extends base test"]
    C --> D["Base test: context, fixtures, auth, state"]
    D --> E["Call producer via MockMvc/HTTP"]
    E --> F{"Status, headers, body match?"}
    F -->|No| G["Build fails; investigate source of mismatch"]
    F -->|Yes| H["Allow stub packaging/publishing workflow"]
    H --> I["Consumer tests with Stub Runner"]
~~~

In principle, **the base class should set up data and infrastructure; contracts should express communication expectations**. Avoid stuffing business assertions into a shared base test, since generated tests would re-run unrelated logic and obscure failure causes.

## 2. Sample scenario: existing order and access permissions

Suppose **Order Service** exposes an endpoint:

~~~http
GET /api/orders/42
Authorization: Bearer contract-read-token
Accept: application/json
~~~

Valid response when the caller has read permission:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"PAID"}
~~~

We want to verify four separate scenarios:

| Scenario | Data state | Authentication/authorization | Expectation |
| --- | --- | --- | --- |
| **Read order succeeds** | Order `42` exists with status `PAID`. | Valid token with scope `orders.read`. | `200` and expected JSON. |
| **Missing authentication** | Data may still exist. | No `Authorization` header sent. | `401 Unauthorized`. |
| **Insufficient permissions** | Order `42` exists. | Accepted token carrying only scope `profile.read`. | `403 Forbidden`. |
| **Order not found** | Order `99` does not exist. | Token with scope `orders.read`. | `404 Not Found`. |

Distinguishing these errors is crucial: **401** usually means the request is not properly authenticated; **403** means the identity was recognized but lacks permission; **404** in this example means **a missing resource**, not a missing stub mapping. Covering all branches in contracts prevents the producer from accidentally turning an auth failure into a business error.

**Illustrative scope:** this example uses **Spring Security OAuth2 Resource Server (JWT)**, Spring MVC, Spring Data JPA, and H2 in tests. Both tokens and data are **fake fixtures**, never valid for logging into a real system. Configuration differs if a project uses sessions/cookies, API keys, mTLS, or another authentication mechanism.

## 3. Defining contracts before preparing fixtures

Place contracts at `src/test/resources/contracts/orders/get_order.groovy` in the producer. With the Groovy DSL, one file can return a list of independent `Contract.make { ... }` entries:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

[
    Contract.make {
        name 'shouldReadPaidOrder'
        request {
            method 'GET'
            url '/api/orders/42'
            headers {
                header('Authorization', 'Bearer contract-read-token')
            }
        }
        response {
            status 200
            headers {
                contentType(applicationJson())
            }
            body(id: 42, status: 'PAID')
        }
    },
    Contract.make {
        name 'shouldRejectAnonymousRequest'
        request {
            method 'GET'
            url '/api/orders/42'
        }
        response {
            status 401
        }
    },
    Contract.make {
        name 'shouldRejectCallerWithoutReadScope'
        request {
            method 'GET'
            url '/api/orders/42'
            headers {
                header('Authorization', 'Bearer contract-no-scope-token')
            }
        }
        response {
            status 403
        }
    },
    Contract.make {
        name 'shouldReportMissingOrder'
        request {
            method 'GET'
            url '/api/orders/99'
            headers {
                header('Authorization', 'Bearer contract-read-token')
            }
        }
        response {
            status 404
        }
    }
]
~~~

Each contract specifies **one request and one expected response**. Contracts do not know whether `42` is in the database or how the JWT decoder interprets the two test tokens; that must be provided by **the base test and the application**. Requests are distinguished by path or the `Authorization` header to avoid overlapping stub mappings.

**Note:** we only assert status codes on the three error branches because this example defines no error schema. If consumers rely on `code` or `message`, add them to the contracts and verify them in producer/consumer tests; do not assume all responses sharing a status code are equivalent.

If your team prefers **YAML DSL**, each scenario can live in a separate file. Example success contract:

~~~yaml
description: Read paid order with orders.read permission
request:
  method: GET
  url: /api/orders/42
  headers:
    Authorization: Bearer contract-read-token
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
~~~

Keep only **one active contract format** per scenario in the build; do not load both equivalent YAML and Groovy files and accidentally generate duplicate tests/stubs.

## 4. Minimal producer: real controller, repository, and security

To test fixtures against a real data layer, this example uses Spring Data JPA. The code below shows **illustrative snippets** in package `com.acme.orders`; the application needs a `@SpringBootApplication` class and matching datasource configuration.

Simple entity:

~~~java
package com.acme.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;

    @Column(nullable = false)
    private String status;

    protected OrderEntity() {}

    public OrderEntity(Long id, String status) {
        this.id = id;
        this.status = status;
    }

    public Long getId() { return id; }
    public String getStatus() { return status; }
}
~~~

Repository:

~~~java
package com.acme.orders;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<OrderEntity, Long> {}
~~~

Controller calling the **real repository**:

~~~java
package com.acme.orders;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderRepository orders;

    public OrderController(OrderRepository orders) {
        this.orders = orders;
    }

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public OrderView getOrder(@PathVariable long id) {
        OrderEntity entity = orders.findById(id)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));
        return new OrderView(entity.getId(), entity.getStatus());
    }

    public record OrderView(long id, String status) {}
}
~~~

Example security configuration:

~~~java
package com.acme.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrderSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This security setup requires `GET /api/orders/**` requests to hold **authority `SCOPE_orders.read`**. Resource Server reads the bearer token, calls `JwtDecoder` to validate it, and maps the `scope` claim into authorities; the example below **mocks only the decoder** in tests while still running the **real security filter chain and authorization rules**.

To build this example, the producer project needs matching dependencies: `spring-boot-starter-web`, `spring-boot-starter-data-jpa`, `spring-boot-starter-oauth2-resource-server`; in tests, `spring-boot-starter-test`, `spring-cloud-starter-contract-verifier`, and `com.h2database:h2` (`test` scope). Spring Cloud Contract libraries/versions must match your Spring Boot/Spring Cloud versions.

## 5. Isolating the database and profile for contract tests

Generated producer tests should never run against a **shared development database** or production database. Place dedicated test configuration in `src/test/resources/application-contract.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:contractdb;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  jpa:
    hibernate:
      ddl-auto: create-drop
~~~

The `contract` profile will be activated by the base test. This config illustrates **in-memory H2** with Hibernate generating the schema for the exercise. In a real project, if the producer relies on SQL or DB features incompatible with H2, use **Testcontainers with the same database engine as production** alongside real migrations rather than forcing H2 and missing behavioral differences.

**Never put `ddl-auto: create-drop` into a production profile.** Schema drop/create settings belong strictly in isolated test environments so tests have deterministic data without harming real application data.

## 6. Complete base test: fixtures + mocked JWT + MockMvc

Create `src/test/java/com/acme/orders/ContractTestBase.java`. This is the class **generated producer tests will extend**:

~~~java
package com.acme.orders;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;

@SpringBootTest(classes = OrderApplication.class)
@AutoConfigureMockMvc
@ActiveProfiles("contract")
public abstract class ContractTestBase {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private OrderRepository orders;

    @MockBean
    private JwtDecoder jwtDecoder;

    @BeforeEach
    void prepareContracts() {
        // 1. Every contract starts from a known state.
        orders.deleteAll();
        orders.save(new OrderEntity(42L, "PAID"));

        // 2. Mock token validation results while keeping real filters/authorization.
        Jwt withPermission = Jwt.withTokenValue("contract-read-token")
            .header("alg", "RS256")
            .claim("sub", "billing-service")
            .claim("scope", "orders.read")
            .build();

        Jwt withoutPermission = Jwt.withTokenValue("contract-no-scope-token")
            .header("alg", "RS256")
            .claim("sub", "billing-service")
            .claim("scope", "profile.read")
            .build();

        when(jwtDecoder.decode("contract-read-token"))
            .thenReturn(withPermission);
        when(jwtDecoder.decode("contract-no-scope-token"))
            .thenReturn(withoutPermission);

        // 3. Generated tests call real Spring MVC through RestAssuredMockMvc.
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
~~~

This example uses the `@MockBean` API appropriate for **Spring Boot 3.3.x**. In newer Spring Boot/Spring Framework releases, `@MockBean` is deprecated in favor of Spring Test's `@MockitoBean`; when applying this to a current project, pick the compatible annotation and adjust imports. Do not copy mixed annotation versions without checking your classpath.

### 6.1. What does each part of the base test protect?

| Component | Purpose |
| --- | --- |
| `@SpringBootTest(classes = OrderApplication.class)` | Starts the producer application in the test context. |
| `@AutoConfigureMockMvc` | Creates `MockMvc` wired through Spring MVC and registered filters. |
| `@ActiveProfiles("contract")` | Selects the dedicated datasource/config for contract tests. |
| `orders.deleteAll()` | Removes leftover rows from earlier tests before seeding. |
| `orders.save(new OrderEntity(42L, "PAID"))` | Ensures valid requests for order 42 receive expected data. |
| `@MockBean JwtDecoder` | Replaces external JWT validation with deterministic decoder responses. |
| `when(jwtDecoder.decode(...))` | Controls which test token carries matching or insufficient scopes. |
| `RestAssuredMockMvc.mockMvc(mockMvc)` | Connects Rest Assured MockMvc to the Spring-booted test application. |

Setup order matters: **data and authentication must be ready before the generated test sends its request**. `@BeforeEach` in the base class is executed by JUnit Jupiter for inheriting tests, so every scenario starts from identical data; no test may assume an earlier test prepared the order for it.

**Limitation of mocking the decoder:** this verifies that a bearer token is required, how Spring Security converts `scope` to authorities, and the endpoint's 401/403 behavior. It **does not verify signatures, expiration, issuer, audience, or real JWKS fetching**. Those checks belong in dedicated security integration tests with a real decoder and proper configuration. A string like `contract-read-token` is not a real JWT; it only works because `JwtDecoder` is mocked **in the test profile**.

### 6.2. Why not put `@WithMockUser` on every generated test?

`@WithMockUser` is handy when you only want to test protected logic **under an already-authenticated identity**. However, placing it on the base class for **all** generated tests causes requests **without a token** to execute inside a pre-populated security context, breaking `401` authentication verification.

For contracts covering `200`, `401`, and `403` as in this example, let the **request header** determine which case is authenticated; a mocked decoder replaces only external JWT validation. Do not disable filters with `@AutoConfigureMockMvc(addFilters = false)` when your goal is verifying authorization requirements.

## 7. Configuring the plugin so generated tests extend the right class

Example Maven configuration in the producer's `pom.xml`:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>4.1.5</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
        <baseClassForTests>com.acme.orders.ContractTestBase</baseClassForTests>
    </configuration>
</plugin>
~~~

Version `4.1.5` is an **example for the Spring Cloud Contract 4.1.x line**, not a mandate to use that exact version; use a **compatible** combination of Spring Boot, Spring Cloud BOM, and Spring Cloud Contract plugin for your project. This is a **plugin snippet**, not a complete POM: you still need test dependencies and build configuration ensuring Maven/Gradle runs generated tests.

Three key lines:

- `testFramework=JUNIT5`: generated tests use JUnit Jupiter and inherit `@BeforeEach` setup properly.
- `testMode=MOCKMVC`: tests invoke Spring MVC inside the test context without opening a separate HTTP socket.
- `baseClassForTests`: package/class name must match **exactly** the base test you just created.

If a project has multiple contract groups requiring distinct fixtures, you can configure base classes by convention/contract path as supported by your plugin version, or structure a clear hierarchy/helper layer. Avoid dumping **all data for every API** into one giant base test: setup time balloons and tests lose business independence.

## 8. Verifying all four branches: 200, 401, 403, and 404

Running generated producer tests with the fixtures above should yield:

| Contract | Before request | How producer handles it | Expected |
| --- | --- | --- | --- |
| `shouldReadPaidOrder` | Order 42 seeded; decoder returns JWT with `orders.read`. | Security allows request; controller fetches order 42. | `200` + `PAID`. |
| `shouldRejectAnonymousRequest` | Order 42 still exists; request has no bearer token. | Security requires authentication before reaching controller. | `401`. |
| `shouldRejectCallerWithoutReadScope` | Decoder returns JWT with `profile.read`. | Caller is authenticated but lacks `SCOPE_orders.read`. | `403`. |
| `shouldReportMissingOrder` | Only order 42 seeded; no order 99; valid read scope. | Security allows request; repository finds no ID 99. | `404`. |

**Do not use a stub's `404` to conclude the controller handled a missing resource.** The generated producer tests in this table call **the real producer via MockMvc**, so a controller `404` is meaningful. On an HTTP stub, a `404` can also come from **a request failing to match any WireMock mapping**. If consumers handle resource-not-found errors, include a business error body/header so the specific mapping is verified.

### 8.1. Self-testing failure detection

Once tests are green, make each change individually and revert before trying the next:

1. Remove the seed call for order 42 → the `200` test must fail because the fixture lacks data.
2. Change the seeded status from `PAID` to `PENDING` while keeping the contract → generated test `200` must fail due to JSON mismatch.
3. Require `SCOPE_orders.write` instead of `SCOPE_orders.read` in security rules → the `200` test turns into `403`, signaling a broken auth contract.
4. Disable security filters in MockMvc → `401`/`403` tests lose reliable protection and may produce unexpected results.
5. Seed order 99 as well → the `404` test must fail because the resource is no longer missing.

When a case fails, determine whether **the fixture failed to meet preconditions** or **the implementation violated the contract**. Never alter a contract to match broken output just to turn the build green.

## 9. Initial state and independence between tests

`@BeforeEach` resetting data before each method makes the example easy to follow. Real projects, however, have state beyond the database: caches, emitted events, sequence counters, clocks, queued messages, temp files, and mocks of external systems.

An isolation checklist:

- **Database:** seed minimally and delete only test-owned rows; if multiple tests share a DB, avoid `deleteAll()` on tables holding another test's data.
- **Transactions:** check what must commit for application code to see it; do not assume test rollback automatically cleans up every change.
- **Cache:** clear or namespace keys per scenario; never serve cached responses from an earlier test.
- **Clock/timezone:** fix time via `Clock` or an injectable provider if contracts check timestamps; avoid comparing real-time `Instant.now()`.
- **Messages/outbox:** clear event records or use separate transaction/test fixtures; prevent assertions from reading leftover messages from earlier tests.
- **Mocked external dependencies:** reset and re-stub per scenario as needed; never rely on call counts from another test.
- **Auto-generated IDs:** only assert fixed IDs if fixtures guarantee them; if the producer generates dynamic IDs, use contract matchers.
- **Parallel execution:** tests sharing a DB/cache or mutating static Rest Assured config can collide; isolate data or configure parallelism carefully.

**Lesson on execution order:** generated producer tests may be ordered or named differently when adding contracts or upgrading the plugin; never rely on "test A creates, test B deletes." Every scenario must establish independent preconditions so it can run alone, re-run after failures, and run reliably in CI.

## 10. When to use `@Sql`, fixture factories, or Testcontainers?

No single seeding approach is optimal for every system:

| Setup approach | Best when | Risks / trade-offs |
| --- | --- | --- |
| `@BeforeEach` + repository | Small fixtures created cleanly through domain/repository APIs. | Broad cleanup can conflict if multiple tests share a DB. |
| `@Sql` before tests | Explicit SQL state is desired, especially with complex relational data. | Scripts depend on schema/transactions and must stay synced with migrations. |
| Fixture builder/factory | Records have many fields where only a few vary per scenario. | Over-abstracted factories hide preconditions from reviewers. |
| Testcontainers | Need PostgreSQL/MySQL/broker behavior close to production. | Slower startup; CI needs container runtime and adequate resources. |
| Mock service/repository | Goal is slice-level mapping/controller/serialization testing only. | Cannot catch query, constraint, or integration bugs skipped by mocks. |

Example: **instead of** `orders.deleteAll()/save(...)`, seed via SQL before each test:

~~~java
import org.springframework.test.context.jdbc.Sql;

@Sql(
    scripts = "/sql/order-contract-fixture.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
public abstract class ContractTestBase {
    // Keep the appropriate Spring context, MockMvc, and auth setup.
}
~~~

Example script at `src/test/resources/sql/order-contract-fixture.sql`:

~~~sql
DELETE FROM orders;
INSERT INTO orders (id, status) VALUES (42, 'PAID');
~~~

**Pick one primary seeding mechanism** per fixture to avoid redundant deletes/writes. `@Sql` participates in transactions and context lifecycles per Spring Test config; if tests start a real HTTP server, uncommitted rows inside a test transaction may **not be visible to requests on another thread**. Manage transactions/commits explicitly in that case.

With Testcontainers, beyond starting the container database, you still need a **data-reset mechanism** between contracts. Running a production-like database catches SQL differences, not stateful test coupling.

## 11. How `MOCKMVC` differs from `EXPLICIT` for fixtures and auth

The base test in section 6 targets `MOCKMVC` mode. If you choose `EXPLICIT`, generated tests send HTTP to a real server in tests. For instance, `@SpringBootTest(webEnvironment = RANDOM_PORT)` boots the app and reads `@LocalServerPort` to configure the HTTP client.

Adjustments needed:

1. **HTTP client:** `RestAssuredMockMvc.mockMvc(mockMvc)` no longer dispatches requests over a socket; the base test must configure Rest Assured's HTTP client with the base URI/port or whichever client the generated tests use.
2. **Fixture visibility:** server requests usually execute on separate threads with separate transactions. Seeded rows must be **committed/visible** before HTTP calls arrive.
3. **Security:** bearer tokens still traverse real filters. Mocking `JwtDecoder` may suffice for authorization tests, but does not verify signatures/JWKS; if testing a real decoder, configure test keys and signed tokens.
4. **Resetting:** when generated tests share a running server/database, manage data isolation and concurrency carefully, especially under parallel execution.

For **Spring WebFlux**, use `WEBTESTCLIENT` if supported by your plugin version; the base test must supply WebTestClient or matching bindings. Do not copy a `RestAssuredMockMvc` setup verbatim into a WebFlux base test and expect generated tests to use it.

For **messaging contracts**, the base test needs message-triggering hooks, fake or real broker/adapter setup, and message assertions—none of which can be replaced by HTTP MockMvc fixtures. Still, the principles of initial data, auth/authorization if applicable, and state reset remain the same.

## 12. Right fixtures, wrong green: critical traps

**Trap A — mocking the exact behavior under verification.** If the goal is verifying the controller, request mapping, and JSON serialization, mocking the underlying service may be fine. But if the goal is proving the producer actually queries order 42 properly, mocking the entire repository/service hides database bugs. Define the **test boundary** and keep critical behavior real.

**Trap B — bypassing security makes 401/403 meaningless.** Adding `@WithMockUser` globally, setting `addFilters=false`, or calling controllers directly without security filters can make tests "authenticated" without verifying bearer-token enforcement. When contracts cover authentication, send real headers in requests and use controlled test authentication.

**Trap C — treating test tokens like production tokens.** Mocking `JwtDecoder` only tests filter/authorization branches. To verify JWT signature, issuer, audience, expiry, key rotation, or JWKS failures, run separate security integration tests with a real decoder and valid signed tokens.

**Trap D — shared fixtures across tests.** One test changing `PAID` to `CANCELLED` can break another depending on execution order. Re-seed or isolate every scenario; never lock test ordering to mask state leaks.

**Trap E — assuming `@Transactional` works in every mode.** Rollback is convenient when requests share the test transaction, but with a real HTTP server on another thread or an async message consumer, transaction visibility and rollback behavior differ. Verify actual transaction boundaries for each test mode.

**Trap F — generated tests silently skipped.** A compiling base test does not mean contracts were verified. Confirm generated test classes/methods exist and test reports show the expected executed test count—not merely `BUILD SUCCESS`.

## 13. Stub Runner does not carry producer fixtures

Once producer tests pass, the build can package stubs under the `stubs` classifier, e.g.:

~~~text
com.acme:order-service:1.0.0:stubs
order-service-1.0.0-stubs.jar
~~~

**A stub is not a copy of the producer application** and does not run `ContractTestBase`, H2, or the mocked `JwtDecoder` above. Stub Runner uses **contract-generated mappings** to return documented responses for matching requests. Therefore:

- A consumer sending `Authorization: Bearer contract-read-token` receives `200` from the stub mapping, **without validating a real JWT signature**.
- A consumer omitting the header receives `401` **if** a contract mapping exists for that scenario; if a request matches no mapping, WireMock may also return `404` as a no-match.
- Testing `403` against a stub verifies how the consumer handles the error response; it **does not prove** Spring Security authorization rules work on the producer—that belongs to generated producer tests with security filters enabled.
- `200`/`401`/`403`/`404` responses are simulated independently by the stub; the stub does not query order 42 in H2 or read state created by another test.

Illustrative consumer test (requires `OrderClient`, imports, and consumer test dependencies):

~~~java
@SpringBootTest(properties = "orders.base-url=http://localhost:8089")
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs:8089",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderClientStubTest {

    @Autowired OrderClient orderClient;

    @Test
    void readsOrderWithAuthorizationHeader() {
        OrderDto dto = orderClient.getOrder(42L, "contract-read-token");
        assertThat(dto.status()).isEqualTo("PAID");
    }
}
~~~

With `LOCAL`, the stub artifact must already be installed in the producer's local Maven repository. In multi-runner CI, the producer must publish stubs to a Maven repository and the consumer uses `REMOTE`, `repositoryRoot`, and proper credentials. **You do not need to start the real producer to run consumer tests against HTTP stubs.**

## 14. Integrating fixtures, auth, and initial state into CI

The pipeline should ensure **tests run in an isolated environment** and **stubs are published only after the producer passes contracts**:

~~~mermaid
flowchart TD
    A["Checkout producer code + contracts"] --> B["Create isolated test DB/services"]
    B --> C["Verifier generates tests"]
    C --> D["Base test seeds fixtures + mocks auth appropriately"]
    D --> E["Producer tests verify 200/401/403/404"]
    E --> F{"All tests pass?"}
    F -->|No| G["Block publish; investigate fixture/auth/implementation bug"]
    F -->|Yes| H["Package and publish stubs artifact"]
    H --> I["Consumer CI downloads stub via Stub Runner"]
    I --> J["Run consumer contract tests with real client code"]
~~~

Rules to enforce:

1. **Never use production resources** for fixtures. Real secrets and tokens do not belong in test sources or contracts.
2. **Never rely on test execution order.** Every test must start deterministically, whether run alone or in the full suite.
3. **Verify auth filters are genuinely active** if contracts include `401`/`403`. Tests must not silently bypass security via global annotations.
4. **Monitor generated and executed test counts**, never treating a green build with zero generated tests as proof.
5. **Block stub publishing when producer verification fails.** Unverified stubs should not be treated as trustworthy contracts.
6. **Pin stub versions in consumer CI**, retaining active contracts to catch breaking API changes against older consumers.
7. **Separate controller-layer auth tests from real security integration tests:** if the project must verify JWT signatures, issuer, audience, and mTLS, maintain dedicated tests for those.

## 15. Base test troubleshooting table

| Symptom | Likely cause | What to check or fix |
| --- | --- | --- |
| `200` becomes `404` in producer test. | Missing fixture, wrong seeded ID, or profile points to another DB. | Check `@ActiveProfiles`, repository, and record 42 right before request. |
| `200` becomes `401`. | Missing header, unstubbed mock decoder, or mismatched token. | Compare `Authorization` in contract with `jwtDecoder.decode(...)`. |
| `200` becomes `403`. | JWT missing scope or security rule requires a different authority. | Check `scope` claim and `SCOPE_orders.read`. |
| `401` test returns `200`. | `@WithMockUser` applied globally, or security filters disabled. | Remove global mock user, enable filters, and test unauthenticated requests. |
| `403` test returns `401`. | "Insufficient scope" token was rejected by the decoder. | Mock decoder to return a valid JWT with a different scope. |
| `404` test returns `200`. | Record 99 left over from an earlier test or overly broad seeding. | Reset state per method and seed only 42. |
| Tests pass alone but fail in full suite. | Shared state/cache/mocks/clock or parallel collision. | Isolate test resources, reset fixtures, check parallel settings. |
| MockMvc test bypasses authentication. | `addFilters=false` or direct controller invocation. | Use `@AutoConfigureMockMvc` with proper filter integration. |
| `EXPLICIT` test does not see freshly seeded rows. | Transaction uncommitted while HTTP request runs on another thread. | Adjust transaction/seeding or set up outside the test transaction. |
| Generated tests miss `@BeforeEach`. | Wrong base class name or non-JUnit 5 test framework. | Check plugin `baseClassForTests` and generated test source. |
| Consumer stub passes while producer security is broken. | Stubs do not run producer filters or database. | Enforce producer verification and add security integration tests. |

## 16. Hands-on exercise and completion checklist

Try this on a Spring Boot application using Spring Cloud Contract Verifier:

1. **Create four HTTP contracts** as in section 3 for `200`/`401`/`403`/`404`.
2. **Configure isolated fixtures:** H2 test database containing order 42 (`PAID`) and lacking order 99; verify the profile is test-only.
3. **Create a JUnit 5 + MockMvc base class:** seed data in `@BeforeEach`, mock `JwtDecoder` for valid and insufficient-scope tokens, and wire `RestAssuredMockMvc`.
4. **Run generated producer tests** via Maven or Gradle as appropriate; confirm all four scenarios are generated and executed rather than just checking build status.
5. **Break fixtures intentionally:** change seeded status to `PENDING`, re-run, and watch the `200` test fail. Revert.
6. **Break auth intentionally:** change the valid token's scope to `profile.read`; the `200` test must fail with `403`. Revert.
7. **Disable filters briefly to test sensitivity** in a trial run, observe whether `401`/`403` tests still protect behavior, and restore.
8. **Test repeatability and parallel runs** where supported by the project, ensuring no state leaks across generated tests.
9. **Package/install or publish stubs after producer tests pass**; run consumer tests with Stub Runner for reading orders and handling mapped errors.
10. **Document boundaries:** note what controllers/repositories/security filters the base test covers, and what still requires real JWTs, production-like databases, or message brokers.

Completion checklist:

- [ ] Contracts clearly specify requests and `200`/`401`/`403`/`404` expectations.
- [ ] Generated tests extend the base test and setup runs before each method.
- [ ] Fixtures contain order 42 (`PAID`) and omit order 99, using an isolated test datasource.
- [ ] Mocked JWT decoder does not inadvertently disable security filters or bypass `401`/`403`.
- [ ] Intentionally altering data/status/permissions causes the corresponding test to fail.
- [ ] Producer tests execute and pass before publishing the `stubs` artifact.
- [ ] Consumer tests use Stub Runner against real client code without mistaking stubs for the producer.

## 17. Self-check questions

1. Why isn't creating the `GET /api/orders/42` contract alone enough for generated producer tests to pass?
2. Why should `@BeforeEach` seed predictable data before every test rather than relying on another test to create the order first?
3. For a Resource Server, how does mocking `JwtDecoder` differ from disabling Spring Security filters?
4. If `@WithMockUser` is placed on the base class for all generated tests, what can happen to a `401` contract?
5. Why should a token with scope `profile.read` produce `403` rather than `401` in this example?
6. When switching from `MOCKMVC` to `EXPLICIT`, why might rows seeded inside an uncommitted transaction be invisible to the HTTP server?
7. If Stub Runner returns `200` for a request carrying a test token, does that prove the producer validates JWT signatures properly?
8. Why does a green build with zero generated tests fail to prove the contract was verified?
9. When should you use Testcontainers instead of H2, and why doesn't Testcontainers automatically solve state leaks?

**Takeaway:** **The base test turns contract preconditions into a repeatable test environment**. In Spring Cloud Contract, configure fixtures, authentication, and initial state accurately for each scenario; mock only what lies outside the verification boundary; and ensure generated producer tests actually run with real security and implementation code. Only after producer verification passes should stubs be published for consumers via Stub Runner. Trustworthy contract testing requires **the right data, the right permissions, the right state, and the right test boundary**—not just a green build indicator.
