# Criteria for using a full context instead of unit tests or test slices

In Spring Boot, `@SpringBootTest` asks Spring Boot to create the **application's `ApplicationContext` according to the selected configuration and profiles**. This allows testing multiple beans and framework mechanisms working together, yet typically costs more startup time, demands more dependencies/infrastructure, and makes root causes harder to pinpoint than narrow tests.

**Just because a feature spans multiple layers does not mean every test for it must use a full context.** The right question is: *“What do we want to conclude from a passing test, and which components must run for real for that conclusion to hold value?”* If you are only verifying a pricing rule, plain JUnit is enough. If verifying HTTP binding, `@WebMvcTest` is usually suitable. If proving controller, service, transaction, repository, and datasource configuration work together, `@SpringBootTest` with matching test infrastructure may be necessary.

This lesson focuses on **decision criteria for choosing a full context instead of unit tests or test slices**, rather than treating `@SpringBootTest` as the default tool for every test in Spring Boot.

## 1. Understand the three scope levels before choosing

### Unit test: testing Java logic without Spring

A unit test instantiates the object under test with `new`, supplies inputs/appropriate doubles, and asserts meaningful outputs, exceptions, or interactions. It requires no Spring `ApplicationContext`.

Example of a valid promo-code rule:

```java
assertTrue(CouponRule.valid("WELCOME"));
assertFalse(CouponRule.valid("bad"));
```

If `CouponRule` is a plain Java class with no HTTP/DB/config, a full context only makes the test slower and environment-dependent without adding any evidence about the rule itself.

### Test slice: loading only one relevant framework layer

Spring Boot test slices target a single infrastructure layer:

- `@WebMvcTest`: MVC controllers, binding, validation, HTTP status/JSON, and essential web/security infrastructure.
- `@DataJpaTest`: JPA mappings, repositories, queries, and slice-scoped database.
- `@JdbcTest`: JDBC/`JdbcTemplate` plus the datasource portion needed for JDBC testing.
- `@JsonTest`: JSON serialization/deserialization.
- `@WebFluxTest`: HTTP layer of Spring WebFlux applications.
- Other test slices: chosen according to the technology and Spring Boot version actually in use.

A slice **does not mean “without Spring”**: it still builds an `ApplicationContext`, yet narrows the bean set and auto-configuration. If a controller's dependency lives outside the web slice, use `@MockitoBean` appropriately to provide a mock rather than loading all services and repositories.

### Full context: running multiple components and wiring together

`@SpringBootTest` discovers or accepts the application's Spring Boot configuration, applies auto-configuration, and constructs the context based on `classes`, `properties`, active profiles, and actual test conditions. It generally loads a broader scope than slices and lets real production beans interact.

**Yet “full” does not mean “identical to production”.** Tests may use different profiles, H2 instead of PostgreSQL, mocked HTTP clients, no message broker, or mock servlets instead of a real HTTP server. The test contract is only established within the scope of **components and infrastructure that actually ran**.

| Question | Unit test | Test slice | `@SpringBootTest` |
| --- | --- | --- | --- |
| Loads a Spring ApplicationContext? | No | Yes, narrow scope | Yes, per application config |
| Runs real service logic? | Yes, if real service is instantiated | Only if service is brought into slice | Usually yes, unless mocked/replaced |
| Testing a pure rule? | **Ideal fit** | Usually too broad | Usually too broad |
| Testing HTTP binding/status? | No, if calling method directly | **Ideal fit with MVC/WebFlux slice** | Yes, if test goes through matching HTTP infra |
| Testing JPA SQL/mappings? | No with mocked repository | **Good fit with repository slice** | Yes if DB/repository run for real |
| Testing controller–service–repository link? | Not automatically | Usually outside slice | **Good fit when beans run for real** |
| Testing auto-config/profiles/qualifiers/bean wiring? | No | Slice portion only | **Good fit when real configuration matters** |
| Startup time and cost? | Usually lowest | Medium | Usually higher |
| Easy to isolate when failing? | High | Fairly high | Requires analyzing more layers |

## 2. Criteria for using a full context: “what evidence is needed?”

A test should be promoted from unit/slice to full context when **at least one risk cannot be reliably verified at a narrow boundary**, and that risk justifies the higher cost.

### Criterion 1 — Must prove cross-layer wiring

Example: “`POST /coupons` goes through the controller, invokes the service, runs a JDBC insert, and returns a response reflecting the persisted count”. A controller test mocking the service proves routing/JSON; a service test mocking the repository proves the insert call was requested; yet **neither proves the real beans are wired together properly in the application configuration**.

A full-context test fits when protecting that integrated path, including bean scanning, constructor injection, transaction manager, and datasource.

### Criterion 2 — Behavior depends on Spring proxies/interceptors

Examples include `@Transactional`, `@Cacheable`, `@PreAuthorize`, and other advisors/proxies. If a test uses `new Service(...)`, those annotations do not activate transactions, caching, or method-security interceptors. If a slice omits the matching proxy infrastructure, a slice test still lacks sufficient proof.

Use a context with real beans and real advice. **It does not always require a full `@SpringBootTest`**: for a minimally configured proxy, `@SpringJUnitConfig` may suffice. Pick full context when you also need to prove **production configuration and multiple advisors/managers operate together**.

### Criterion 3 — Auto-configuration and bean conditions are part of the contract

For instance, a `DataSource`/`TransactionManager` created only under a profile, a bean activated by a property, or an implementation selected via `@Primary`/`@Qualifier`. Unit tests ignore Spring configuration; slice tests may intentionally exclude those beans.

Full-context tests shine at catching missing beans, misconfigured profiles, unactivated conditional auto-configuration, or wrong implementation selection. Be careful though: **a test declaring a mock to fill in for a missing bean can hide the very wiring bug you wanted to catch**. When proving a bean must exist, use strict override strategies or explicit configuration assertions rather than blindly adding new mocks.

### Criterion 4 — Data/operations must pass through multiple real adapters

Examples: “an order request commits a transaction and the record is queried back”; “an outbox event writes to DB and relays via broker”; “HTTP client serialization combined with adapter timeouts/retries”.

If the risk resides in SQL syntax, migrations, transactions, or protocols, **mocking those adapters will not provide equivalent evidence**. A full context with matching DB/broker/HTTP test infrastructure verifies the flow. Still, when testing only a repository query or an HTTP client adapter in isolation, a **slice/adapter test** remains narrower and more efficient.

### Criterion 5 — Bugs only surface when components interact

Bugs can emerge from coordination: controller passes the wrong field to service; service picks the wrong transaction manager; Bean Validation sits on a non-invoked layer; security filters diverge from method security; Jackson format changes break clients.

Full-context tests are a **safety net for a few critical journeys**, not a reason to run every edge case at full scale. One happy path and selected high-risk failure paths complement unit/slice tests covering wide variations.

### Criterion 6 — Must run under configuration close to deployment

If the requirement states “under profile `test`/`staging`, bean A connects to DB B, migrates the schema, and handles requests”, use a context whose config/profiles closely match the target. Differing configuration can invalidate conclusions.

**Never claim an H2 test proves PostgreSQL-specific constraints/dialects/locking are right.** When the system relies on PostgreSQL, specialized SQL, Redis TTLs, Kafka consumer offsets, or network security, run matching infrastructure (such as Testcontainers for DBs/brokers when appropriate) if that is what needs proving.

## 3. Practical decision tree

```text
Start from the behavior/bug you need to guard
              |
              v
Does Spring need to process anything for the behavior to occur?
       /                         \
      No                         Yes
      |                           |
  Plain JUnit                     v
                          Only one layer?
                            /         \
                          Yes           No
                          |              |
                  Web/JPA/JDBC/JSON       v
                     test slice      Multiple beans,
                          |           proxies/config
                          |              |
                          v              v
                  Slice enough?      Use appropriate
                     /    \         context, consider
                   Yes     No        @SpringBootTest
                   |        |
                 Stop    Raise scope
               at slice  per risk
```

Quick checklist before adding `@SpringBootTest`:

1. **Without starting Spring, what fails to execute?** If you cannot answer, try a unit test first.
2. **With only a test slice, what evidence is missing?** If none, stick with the slice.
3. **Inside the full-context test, which adapters are still mocked/faked?** Limit your claims about those mocked adapters accordingly.
4. **If the test fails, can you tell which layer broke?** Keep unit/slice tests to pinpoint failures.
5. **Do you need a real server/DB/broker or just an `ApplicationContext`?** Match `webEnvironment` and fixtures/infra to the exact goal.

If the goal is solely “can the context start?”, a full-context smoke test has value. If the goal is transaction commit or HTTP serialization, **asserting merely that the context starts is not enough**.

## 4. `webEnvironment` modes of `@SpringBootTest`

`@SpringBootTest` does not open a real HTTP port by default. Common values of `SpringBootTest.WebEnvironment`:

| Value | Primary Behavior | Best When |
| --- | --- | --- |
| `MOCK` (default) | Creates a simulated web application context when the app is a web app, **without starting a real embedded server** | Integration tests using `MockMvc` or needing no socket |
| `RANDOM_PORT` | Starts a web server on a random port | Testing HTTP over a real network stack, cookies/redirects/servlet container behavior |
| `DEFINED_PORT` | Starts server on configured port | Fixed port strictly mandatory; usually poorly suited for parallel CI |
| `NONE` | Creates no web environment | Full application beans needed without web infrastructure |

### `MOCK` does not supply `MockMvc` automatically in every setup

In standard Spring Boot MVC tests, `@SpringBootTest` paired with `@AutoConfigureMockMvc` lets you inject `MockMvc`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class CouponFullContextTest {
    @Autowired MockMvc mvc;
}
```

This is a class structure snippet, not a standalone test file. `@AutoConfigureMockMvc` comes from Spring Boot test auto-configuration; exact packages/dependencies can vary across Boot generations. Runnable examples in section 6 use **Spring Boot 3.4/3.5** import syntax. MockMvc executes MVC requests/responses through servlet test infrastructure **without opening a real socket**.

### `RANDOM_PORT` provides broader proof at the HTTP layer

`@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` starts a real server on a dynamic port. Test clients can issue HTTP calls to that port using an HTTP client matching your Boot version; if TLS, proxies, or wire behavior must be verified, configure accordingly.

**Transaction trap:** when the test's HTTP client and the server's request handler execute on **two separate threads**, a transaction controlled by `@Transactional` on the test method does not automatically encompass the server-side transaction. If the server writes to the DB and commits, rolling back the test transaction does not delete that data. Fixture setup and cleanup must reflect the real execution path. Relying on `@Transactional` on a `RANDOM_PORT` test to “auto-clean the DB” leaks rows across cases.

## 5. Comparing via one feature: saving a coupon code

Consider the behavior “a user submits a valid coupon code; the application stores it in the database and returns HTTP 201 with the current row count”.

- **Unit test** proves the valid-code rule.
- **Web slice** proves request mapping and JSON response when the service is mocked.
- **Full context** proves controller, real service, `JdbcTemplate`, transaction manager, schema, and H2 operate together.

When selecting test levels, explicitly state which pieces are mocked in each example.

**Example rules:**

1. Coupon codes consist solely of ASCII uppercase letters `A–Z`, length 4 to 12 characters.
2. Invalid codes are rejected with `IllegalArgumentException` before inserting.
3. Valid codes are inserted into table `coupons`, column `code` having a unique constraint.
4. Controller returns HTTP 201 with JSON containing `code` and `total` on successful save.
5. On invalid input, controller maps to HTTP 400 with an `error` field.

**Technology scope to run the example:** Java 17+, Spring Boot **3.4/3.5**, Spring MVC, Spring JDBC, H2, JUnit Jupiter, and Mockito in tests. For Spring Boot 4+, check exact test module artifacts/packages before copying imports; the full-context decision criteria remain identical.

Project structure:

```text
src/
├── main/java/example/fullcontext/
│   ├── CouponApplication.java
│   ├── CouponRule.java
│   ├── CouponRuleDemo.java
│   ├── CouponService.java
│   └── CouponController.java
├── main/resources/schema.sql
└── test/java/example/fullcontext/
    ├── CouponRuleTest.java
    ├── CouponControllerSliceTest.java
    └── CouponFullContextTest.java
```

### 5.1. Required Gradle configuration

In a Spring Boot 3.4/3.5 project already configured with the `org.springframework.boot` Gradle plugin, Java toolchain, and compatible dependency management, the relevant portion in `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This snippet is **not a complete standalone `build.gradle`**, because plugins, repositories, and versions are managed by the Spring Boot project. With Boot 3.4/3.5, the standard test starter supplies JUnit Jupiter, Mockito, and Spring Boot test infrastructure. `@MockitoBean` belongs to Spring Framework TestContext 6.2+ included in compatible test dependencies.

H2 is used **solely to illustrate controller–service–database wiring**, not to prove production PostgreSQL/MySQL SQL behavior.

### 5.2. Spring Boot application

Create `src/main/java/example/fullcontext/CouponApplication.java`:

```java
package example.fullcontext;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CouponApplication {
    public static void main(String[] args) {
        SpringApplication.run(CouponApplication.class, args);
    }
}
```

Place the application class in root package `example.fullcontext` so default Spring component scanning detects the controller and service in the same package.

### 5.3. Pure Java rule: CouponRule

Create `src/main/java/example/fullcontext/CouponRule.java`:

```java
package example.fullcontext;

public final class CouponRule {
    private CouponRule() {
    }

    public static boolean valid(String code) {
        return code != null && code.matches("[A-Z]{4,12}");
    }
}
```

This class needs no Spring. `matches("[A-Z]{4,12}")` anchors across the entire string, so `"WELCOME"` is valid, `"bad"` fails lowercase, and `"ABC"` fails length.

### 5.4. Service executing JDBC and transactions

Create `src/main/java/example/fullcontext/CouponService.java`:

```java
package example.fullcontext;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CouponService {
    private final JdbcTemplate jdbc;

    public CouponService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public int register(String code) {
        if (!CouponRule.valid(code)) {
            throw new IllegalArgumentException("invalid code");
        }

        jdbc.update(
                "INSERT INTO coupons(code) VALUES (?)",
                code);

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM coupons",
                Integer.class);
        return count;
    }
}
```

Meaning:

- Spring creates the `CouponService` bean via `@Service` and injects `JdbcTemplate` from JDBC auto-configuration.
- `@Transactional` applies when the method is called through a Spring-managed bean proxy; unit tests using `new` do not prove transaction interception.
- Validation runs before insert; invalid data never touches the DB.
- After inserting, the service queries count to return the result.
- The unique constraint on `code` in the schema prevents inserting duplicate coupons; dedicated tests can verify constraint errors if required by business rules.

### 5.5. Controller and JSON response

Create `src/main/java/example/fullcontext/CouponController.java`:

```java
package example.fullcontext;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/coupons")
public class CouponController {
    private final CouponService service;

    public CouponController(CouponService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<CouponReceipt> create(
            @RequestParam String code) {
        int total = service.register(code);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new CouponReceipt(code, total));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> invalidCode(
            IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("error", ex.getMessage()));
    }

    public record CouponReceipt(String code, int total) {
    }
}
```

The controller knows no SQL; it delegates to the service. `@ExceptionHandler` here maps `IllegalArgumentException` from the controller/service within MVC handling scope to HTTP 400. That is this example's contract, not a claim that every application must use identical exception mapping.

### 5.6. Schema for the H2 datasource

Create `src/main/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS coupons (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(32) NOT NULL UNIQUE
);
```

In a Spring Boot project with an embedded H2 datasource and standard SQL initialization, `schema.sql` executes during datasource initialization. If a project uses Flyway/Liquibase, adjust initialization/migrations for tests; **never layer two migration systems on top of each other without a plan**.

## 6. Three tests on the same feature, three distinct claims

### 6.1. Unit test: coupon rule

Create `src/test/java/example/fullcontext/CouponRuleTest.java`:

```java
package example.fullcontext;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CouponRuleTest {
    @ParameterizedTest
    @ValueSource(strings = {"WELCOME", "SAVE", "ABCDEFGHIJKL"})
    void acceptsUppercaseCodesWithinLength(String code) {
        assertTrue(CouponRule.valid(code));
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {"bad", "ABC", "ABC123", "ABCDEFGHIJKLM"})
    void rejectsInvalidCodes(String code) {
        assertFalse(CouponRule.valid(code));
    }
}
```

This comprises **9 invocations** (3 valid + 2 null/empty + 4 invalid strings = 9 runs). To avoid miscounting: the valid group has **3**, the invalid group has **6**, giving exactly **9 invocations** across **2 parameterized test methods**. No Spring context, database, or MockMvc is involved. This test guards the rule with a very tight boundary without needing `@SpringBootTest`.

Technical note: the 12-letter `ABCDEFGHIJKL` is the valid boundary, and 13-letter `ABCDEFGHIJKLM` is invalid. Boundary inputs carry far more value than arbitrary strings.

### 6.2. MVC slice: HTTP contract when service is mocked

Create `src/test/java/example/fullcontext/CouponControllerSliceTest.java`:

```java
package example.fullcontext;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CouponController.class)
class CouponControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    CouponService service;

    @Test
    void returnsCreatedResponseFromServiceResult() throws Exception {
        when(service.register("WELCOME")).thenReturn(1);

        mvc.perform(post("/coupons")
                        .param("code", "WELCOME"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.code").value("WELCOME"))
                .andExpect(jsonPath("$.total").value(1));

        verify(service).register("WELCOME");
    }
}
```

This test creates a Spring MVC context **without loading the real service or database**. `@MockitoBean` creates/replaces the service bean to satisfy the controller's dependency. If green, you can conclude `POST /coupons` routing, request parameters, and JSON responses **in the web slice** match the mocked return value.

**You cannot conclude** that the JDBC insert succeeded or transactions worked: the service is a mock, so `register` never ran real logic. If the app has Spring Security on the classpath, MVC tests may run security filters; configure authentication/test filters per contract rather than disabling security just to turn tests green. This minimal example **declares no Security starter**.

### 6.3. Full context: controller → real service → JDBC → DB

Create `src/test/java/example/fullcontext/CouponFullContextTest.java`:

```java
package example.fullcontext;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CouponFullContextTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void clearRows() {
        jdbc.update("DELETE FROM coupons");
    }

    @Test
    void postRequestPersistsCouponAndReturnsResponse()
            throws Exception {

        mvc.perform(post("/coupons")
                        .param("code", "WELCOME"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.code").value("WELCOME"))
                .andExpect(jsonPath("$.total").value(1));

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM coupons",
                Integer.class);
        assertEquals(1, count);
    }

    @Test
    void invalidCodeReturnsBadRequestWithoutInsert()
            throws Exception {

        mvc.perform(post("/coupons")
                        .param("code", "bad"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("invalid code"));

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM coupons",
                Integer.class);
        assertEquals(0, count);
    }
}
```

**Here is where the full context adds value:**

1. Spring Boot finds `CouponApplication` and loads the controller, service, datasource, JDBC, transaction manager, and matching auto-configuration.
2. `MockMvc` simulates HTTP requests through MVC infrastructure; **no real network port is opened**.
3. Spring injects the **real service** into the controller; `CouponService.register` performs validation, JDBC insert, and query.
4. H2 executes the SQL schema. Assertions count actual rows instead of merely calling `verify(mockRepository).save(...)`.
5. The invalid input case maps to HTTP 400 with **no new row** in the DB.

The test intentionally **does not mock `CouponService` or `JdbcTemplate`**, because its purpose is proving the integrated path. `@BeforeEach` clears rows so cases remain independent under standard sequential execution. If parallel test execution is enabled against the same H2 datasource, deeper database/schema/fixture isolation is needed; `DELETE` before tests does not guard against concurrent races between methods.

**Limitation:** this test proves Spring MVC → service → Spring JDBC → H2 inside `ApplicationContext`. It **does not yet** prove requests over TCP/embedded servers, PostgreSQL behavior, or external email/payment/broker systems.

### 6.4. Running each level with Gradle

From the project root containing the Gradle wrapper:

```bash
./gradlew test --tests example.fullcontext.CouponRuleTest
./gradlew test --tests example.fullcontext.CouponControllerSliceTest
./gradlew test --tests example.fullcontext.CouponFullContextTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.fullcontext.CouponRuleTest"
.\gradlew.bat test --tests "example.fullcontext.CouponControllerSliceTest"
.\gradlew.bat test --tests "example.fullcontext.CouponFullContextTest"
```

**Expected outcome when properly configured:** unit has 9 invocations, MVC slice has 1 test method, full context has 2 test methods; all pass. Gradle reports and stdout vary by runner version/config, so do not pin a fixed stdout string to the test command. Inspect test reports to check names and durations of each group.

### 6.5. Running plain Java directly via javac/java

To verify the rule **without Gradle/Spring/JUnit**, create `src/main/java/example/fullcontext/CouponRuleDemo.java`:

```java
package example.fullcontext;

public class CouponRuleDemo {
    public static void main(String[] args) {
        System.out.println(CouponRule.valid("WELCOME"));
        System.out.println(CouponRule.valid("bad"));
        System.out.println(CouponRule.valid("ABC"));
    }
}
```

Run in the project directory with JDK 17+:

```bash
javac -d out src/main/java/example/fullcontext/CouponRule.java src/main/java/example/fullcontext/CouponRuleDemo.java
java -cp out example.fullcontext.CouponRuleDemo
```

**Exact stdout:**

```text
true
false
false
```

This is purely a plain Java demo. It **does not verify** Spring contexts, controllers, databases, or transaction annotations; those require running the JUnit/Spring tests above.

## 7. Why not replace all unit/slice tests with full-context tests?

A full-context test traverses many layers, yet **a failure can originate from many places**: missing bean, datasource failing to boot, missing schema, security filter blocking requests, serialization errors, uncommitted transactions, or broken business rules.

If every edge case ran through `@SpringBootTest`:

- Bootstrap and DB fixture costs multiply; tight edit-test feedback loops slow down.
- An environment glitch can turn scores of tests red even when business logic is sound.
- Test names stop pinpointing which layer broke, dragging out debugging.
- Tests easily share data and context state, especially when parallelized.
- Over-mocking inside a full context can leave tests still failing to verify real integration.

**A balanced distribution:**

- Dense unit tests for rules, state transitions, exceptions, and calculations.
- Focused slice tests covering HTTP binding, validation, JSON, JPA queries, or JDBC adapters.
- Selective full-context tests for a handful of **critical paths**: boot/wiring, cross-layer happy paths, rollback/authorization/caching at real boundaries, and historical integration regressions.

There is no rigid rule like 70% unit, 20% slice, 10% full. Base the split on risk, test cost, and the evidence needed. **Wider is not automatically better** if a test does not observe the right behavior.

## 8. Choosing full context vs. a focused Spring TestContext

Between plain unit tests and Boot slices lies a middle ground: using `@SpringJUnitConfig` to construct **a purposefully minimal Spring context**.

For instance, to test `@Cacheable` on a service with a `CacheManager`: build a configuration containing only that service, cache manager, and `@EnableCaching`. That test still exercises Spring AOP proxies **without** all of application auto-configuration, a DB, or a web server.

Likewise, `@PreAuthorize` method security can run in a small context with `@EnableMethodSecurity` and a test `SecurityContext`. When testing Spring transaction proxies, you need a matching transaction manager/datasource without necessarily booting the whole REST API.

**Use full `@SpringBootTest` when what needs proving is the broader application's own configuration/wiring**: multiple beans, auto-configuration conditions, the security chain, multiple transaction managers, production cache managers, or multi-adapter interactions. A minimal context suffices for **framework behavior**, yet may not prove **production wiring behavior**.

## 9. Traps of full-context tests

### 9.1. `@Transactional` on a test can mask commit behavior

Spring Test supports `@Transactional` on test methods to auto-roll back when tests finish. That is great for data isolation, yet if the goal is **confirming a service commits**, asserting via a DB query inside the same test transaction can see uncommitted data.

For a service commit/rollback test, verify at the true transaction boundary: invoke the bean proxy outside any test-managed transaction and check the database **after the service finishes**. With `RANDOM_PORT`, the test thread's transaction does not govern the server thread anyway. Never claim commit/rollback works solely because a test auto-rolls back at teardown.

### 9.2. Some dependencies remain mocked

`@SpringBootTest` can still use `@MockitoBean` to swap out external clients, yet **never claim a mocked adapter was tested for real**. Mocking an HTTP client protects service orchestration and wiring of other beans, while leaving the client's serialization/timeouts unproven.

Mocking the very service annotated with `@Transactional`/`@Cacheable`/method security can bypass the target's advice chain. Keep targets real whenever proving proxies.

### 9.3. Test profiles differ from production

Tests running with `@ActiveProfiles("test")` or property overrides may select different beans/datasources than production. That is helpful to avoid external systems, provided conclusions stay bounded. A `test`-profile context does not guarantee `prod` has the same beans when `@Profile`, `@ConditionalOnProperty`, or environment-based config are used.

If the risk sits in production configuration, add a smoke/integration test loading config close enough to the target. Never casually define a test bean to patch over a missing production bean and conclude everything works.

### 9.4. H2 and production databases can behave differently

H2 works well for common SQL flows, yet proves nothing about PostgreSQL/MySQL dialects, JSON/array types, indexes, transaction isolation, locking, or engine-specific migrations. When real bugs depend on the DB engine, use **Testcontainers** or a matching environment and clean test data explicitly.

### 9.5. Shared `ApplicationContext`, DB, and caches

Spring TestContext caches and reuses `ApplicationContext` across tests with equivalent configuration. That is a sensible optimization, yet it **does not automatically reset** mutable singleton state, DBs, caches, brokers, or files.

- Create isolated test data and clean up.
- Avoid depending on test execution order.
- If running in parallel, isolate transactions, schemas, databases/containers, or key namespaces as needed.
- Use `@DirtiesContext` only when genuinely tearing down a dirtied context; it raises runtime significantly.
- Avoid heavy `@BeforeEach` HTTP/DB calls on every test when fixtures can be prepared more efficiently while staying independent.

### 9.6. Context startup tests do not check every route

A `@SpringBootTest` with only `contextLoads()` is useful as a **wiring smoke test**, yet sends no requests, invokes no proxied methods, and proves no DB commits. To verify a business flow, execute that flow and assert observable outcomes.

### 9.7. Security filters and method security

In an app with Spring Security, `MockMvc` can run the security filter chain, rejecting requests with 401/403/CSRF. That may be the **intended** part of the contract. When testing HTTP security, supply proper authentication/tokens; never use `addFilters=false` or disable security just to get another status assertion passing and claim security was tested.

`@PreAuthorize` method security is another layer; testing the service directly through its proxy proves method rules without proving HTTP filters or JWT decoders. Pick the boundary your users actually depend on.

## 10. Real costs of full contexts: deciding by signals

Costs go beyond a few seconds of bootstrap:

| Cost or Risk | Symptom | Mitigation |
| --- | --- | --- |
| Initializing lots of auto-config/beans | First test slow, verbose bean logs | Favor unit/slice tests for narrow cases |
| DB/container/migration startup | Slow CI, flaky resource timeouts | Share controlled containers/fixtures, pick few critical paths |
| Shared data | Passes alone, fails in full suite | Clean/isolate data, avoid order dependencies |
| Multi-layer failures | Long stack traces, unclear whether SQL or MVC failed | Keep unit/slice tests to localize issues |
| Mocks hiding wiring | Full context green despite missing production adapter | Check override strategy and real config |
| Parallel test execution | Races on DB tables or cache keys | Isolate state per test, tune parallelization |
| Production environment drift | H2 passes, PostgreSQL fails | Use the real engine when risk demands it |
| Overly broad test suite | Every edge case boots `@SpringBootTest` | Move logic cases to unit tests, single-layer contracts to slices |

Keeping a few **full-context tests driven by clear questions** usually yields a far better evidence-to-cost ratio than turning the entire suite into heavy integration tests. If pipelines must verify deployment or live networking, build dedicated tests targeting appropriately configured environments.

## 11. Common mistakes when choosing test levels

**1. Assuming `@SpringBootTest` always starts an HTTP server.** Default `MOCK` opens no real socket. Use `RANDOM_PORT` or matching configuration for network calls.

**2. Using `@SpringBootTest` for an `if` branch or regex.** Plain unit tests prove the rule completely and run much faster.

**3. Running `@WebMvcTest` and concluding the database saved rows.** When the service is mocked, the test only proves the web contract against stubbed output.

**4. Using a mock repository and concluding transaction rollback works.** Verifying mock calls does not mean a DB transaction happened. Check persistence via an appropriate integration test.

**5. Using full context yet mocking every relevant target.** A test can be “full context” while bypassing the very behavior you wanted to guard.

**6. Ignoring profiles/conditional beans.** Green tests only confirm the active config/profiles loaded, not every deployment environment.

**7. Using H2 to prove production-specific SQL.** Switch to the matching DB engine whenever contracts rely on engine-specific data types or transaction semantics.

**8. Forgetting to check side effects.** HTTP 201 does not automatically prove a DB commit. Pair requests with repository/JDBC assertions or clients observing real infrastructure.

**9. Putting `@Transactional` on a test and concluding the service commits.** Reading data inside the same test transaction is not proof of committing after the service call.

**10. Testing `RANDOM_PORT` yet expecting test-thread rollback.** Requests run on the server thread; server-written data requires explicit cleanup.

**11. Disabling security filters to force status codes.** If security is part of the contract, test with proper filters/roles/tokens.

**12. Having only a `contextLoads()` test for a complex feature.** It catches bean initialization failures, yet tests neither routes, transactions, nor business logic without invoking them.

**13. Putting `@DirtiesContext` everywhere to deal with dirty data.** Repeatedly rebuilding contexts is costly and does not replace proper cleanup.

**14. Stuffing boundary cases into full-context tests.** Multi-branch regex/validation logic belongs in narrow tests; reserve integration paths for representative cases.

## 12. Checklist for choosing `@SpringBootTest`

Before writing:

- Is the contract to prove a **pure rule, single infrastructure layer, or cross-layer link**?
- Can I articulate the **evidence gap** left by unit/slice tests?
- Which beans must run for real? Is any mocked bean preventing the test from proving what I intend?
- Do I need real framework proxies, auto-configuration, profiles, transaction managers, or security chains?
- For DB/broker/HTTP, which implementation is used; is it faithful enough to production for the risk under test?
- Should `@SpringBootTest` use `MOCK`, `RANDOM_PORT`, or `NONE`?
- Does the test also need `@AutoConfigureMockMvc` or an appropriate HTTP client?
- Can fixtures and test data stay isolated/cleaned across context caching and parallel suite runs?

After running:

- Does the test assert **outputs + side effects** at the right boundary, not just context creation?
- Are failures localized by corresponding unit/slice tests?
- Did the test genuinely exercise production beans/proxies/config meant to be proven?
- What conclusions remain unproven due to using H2/mocks/test profiles/socketless MockMvc?
- Could this full-context test be replaced by a smaller slice without losing needed evidence?
- If the test is slow/flaky, should I **narrow its boundary**, improve fixtures, or split risks into separate tests?

**Conclusion:** `@SpringBootTest` fits when **evidence requires multiple real Spring Boot beans and infrastructure layers to collaborate**, especially wiring/auto-configuration, transaction/security/cache proxies, and critical cross-layer journeys. Unit tests should still guard detailed logic, while test slices guard individual layer contracts. Pick the **narrowest level that proves the requirement**, then add targeted full-context tests to cover integration risks that narrow tests cannot see.
