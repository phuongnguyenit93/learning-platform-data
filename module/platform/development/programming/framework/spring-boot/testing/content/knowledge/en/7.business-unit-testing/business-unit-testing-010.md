# Limits of Unit Tests with Transactions, Proxies, Validation, and Spring Configuration

Business unit tests answer the question: **“given controlled inputs and dependencies, does this method execute the rules properly?”**. They run fast because they typically invoke plain Java objects directly using mocks or fakes without starting an `ApplicationContext`. Yet a method annotated with `@Transactional`, `@Validated`, `@ConfigurationProperties`, or relying on Spring AOP can behave **completely differently when invoked through a Spring bean**.

For example, suppose a service updates a balance and then throws `RuntimeException`. A Mockito unit test can confirm the service called `repository.save(...)` before throwing. However, only by invoking the service through a Spring transaction proxy backed by a transaction manager and real database can you verify the change actually **rolled back**. Likewise, adding `@NotBlank` to a parameter does not guarantee `new Service(...).method("")` rejects empty strings; method validation requires Spring-activated Bean Validation interception.

This lesson clarifies each test level's boundary, explains what Spring executes outside a Java method body, and provides a Java 17+/Spring Boot project to verify the differences directly.

## 1. Which Evidence Is Sufficient from Unit Tests, and Which Is Not?

| Behavior to protect | What direct Mockito unit tests can prove | What is additionally needed to verify real Spring behavior |
| --- | --- | --- |
| Pricing calculations, thresholds, valid state rules | Return values, business exceptions, dependency calls for specific inputs | Integration test if outcomes also depend on wiring/DB |
| `@Transactional` | Method body reaches repository call and throws | Transaction manager, proxy, real writes, observable commit/rollback |
| `@Validated` on a service | Explicit `if`-based validation written in Java | Bean Validation + Spring method-validation interceptor/proxy on parameters/return values |
| `@Valid` at HTTP boundary | Business logic handling an already-valid DTO | Spring MVC tests verifying binding, validation, 400 errors, and response contract |
| `@ConfigurationProperties` | Service runs with a **hand-built** config object | Binder reads real properties, applies conversions, validation, and profiles/overrides |
| Constructor injection and bean wiring | Object instantiated via `new` with manual dependencies | Context creates beans with real qualifiers, conditions, and profiles |
| `@Cacheable`, `@Async`, `@PreAuthorize` (if used) | Raw method body logic stripped of interceptors | Tests through Spring-managed beans observing the respective advice |

**Distinguish two kinds of correctness:** (1) *algorithmic correctness* inside the service and (2) *operational contract correctness* when Spring creates beans and executes surrounding infrastructure. Reliable systems need both, balanced against risk.

## 2. Why Is `new Service(...)` Not Equivalent to Obtaining a Bean from Spring?

An annotated class:

```java
@Service
@Validated
public class WalletService {
    @Transactional
    public int charge(@NotBlank String owner,
                      @Positive int amount,
                      boolean rejectAfterWrite) {
        // business processing
    }
}
```

Is a **definition carrying framework metadata**. If a test calls:

```java
WalletService service = new WalletService(repository, policy);
service.charge("alice", 150, false);
```

that is an ordinary Java call on an object constructed by the test itself. Spring has created no proxy around that instance; transaction and method-validation interceptors will **not run automatically**. Annotations are not JVM statements executed inside the method body.

When Spring creates the `WalletService` bean inside a context with matching dependencies and auto-configuration, the framework can wrap it in a proxy. External calls passing through that proxy trigger advice such as transactions, validation, security, and caching.

```text
Unit test calls new WalletService(...)
  -> charge(...)  [method body]
  -> mock repository
  -> bypasses Spring proxy
  -> no annotation-driven transaction/validation guarantees

Integration test calls @Autowired WalletService
  -> Spring proxy
  -> transaction / method validation advice (as configured)
  -> charge(...)  [method body]
  -> real repository / database
  -> commit or rollback per transaction rules
```

This diagram is simplified and does not fix exact advisor ordering. Spring AOP can use JDK dynamic proxies when accessed via interfaces or class-based proxies depending on configuration. Tests must exercise the **real invocation path** rather than assuming annotations take effect regardless of how an object is called.

### Self-invocation is a common trap

In standard proxy mode, calling `this.charge(...)` **from another method on the same object** bypasses the proxy, skipping `@Transactional` or method-validation advice on `charge`.

```java
public int runInternalCharge(String owner, int amount) {
    return this.charge(owner, amount, false);
}
```

This is an **illustrative snippet** placed inside the sample service. Even when a client calls `runInternalCharge` through a Spring bean, the internal call `this.charge` is not intercepted by the proxy like an external call. Do not attempt to fix this by switching to private or final methods expecting the proxy to intercept them; fix the **bean/proxy call boundary** instead. Extract the advised work into another bean, redesign the use case, or use programmatic transaction management when appropriate. Avoid circular self-injection as a default workaround.

## 3. Limit 1 — `@Transactional`: Calling `save` Does Not Prove Commit or Rollback

`@Transactional` belongs to Spring's transaction infrastructure. It never runs when instantiating objects via `new`. In typical proxy configurations, advice starts or joins a transaction before the method call and commits or rolls back when the call finishes.

By default, **unchecked exceptions** (`RuntimeException` and subclasses) and `Error` trigger rollback; **checked exceptions** do not trigger rollback by default unless configured via `rollbackFor` or custom transaction rules. Simply throwing an exception in a method does not prove a real transaction exists.

Business scenario:

1. `alice`'s wallet starts with balance 500.
2. Deduct 150, expected balance becomes 350.
3. If the payment gateway rejects **after the write**, the service throws `ChargeRejectedException extends RuntimeException`.
4. When invoked through a transaction proxy, all JDBC writes in that transaction roll back: DB balance remains 500.
5. When invoked directly outside a transaction on an auto-commit connection, the 350 row update can remain persisted after the exception.

**A mock cannot prove step 4.** It proves only that `writeBalance("alice", 350)` was invoked. Mockito has no transaction manager, runs no SQL, and performs no DB commit/rollback.

### Two mistakes that cause false rollback conclusions

**First: annotating the test itself with `@Transactional`.** In Spring Test transaction-managed integration tests, the test framework typically opens a transaction for the test method and rolls it back afterward. Seeing an “unchanged DB after the test” can come from the **test transaction**, proving nothing about `@Transactional` on the production service. To verify a service's real transaction boundary, omit `@Transactional` on this rollback test method/class; seed data, invoke the proxy, and read the DB **after the service returns or throws**.

**Second: mocking the repository or DB.** `verify(repository).save(...)` proves an interaction; it does not prove final persisted state, transaction isolation, failure rollback, or SQL triggers. For multi-query logic or DB constraints, run integration tests against an appropriate storage engine.

## 4. Limit 2 — Spring Proxies and Advice: Annotations Do Not Mean Behavior Is Active

Beyond `@Transactional`, numerous Spring features rely on interceptors or bean lifecycles:

| Feature | What happens when called via `new` | Evidence worth verifying through Spring |
| --- | --- | --- |
| `@Transactional` | Annotation opens no transaction | Transaction exists, real commit/rollback |
| `@Validated` and method constraints | Does not block invalid arguments automatically | Method validation raises violation when called via bean |
| `@Cacheable` | Does not access Spring Cache | Cache hit/miss and invalidation per contract |
| `@Async` | Does not offload calls to an executor | Asynchronous execution and task completion |
| `@PreAuthorize` (with method security on) | Does not check permissions | Requests/methods denied or permitted per role |
| `@Value` | Fields remain unpopulated when created via `new` | Properties resolved on Spring-managed objects |
| `@PostConstruct` | Lifecycle callback does not fire automatically | Context runs callback during bean lifecycle per config |

These mechanisms are not active merely because annotations appear in code: starters, auto-configuration, enabling annotations, and supported invocation paths are all required.

With proxies, understand scope limits: `private` or `final` methods cannot be overridden normally by class-based proxies; self-invocation bypasses proxy interception. Never apply “every annotated method runs advice” mechanically. Specific features and proxy modes dictate exact boundaries.

**Unit tests remain deeply valuable:** precisely because they omit this infrastructure layer, they give rapid feedback on calculations and error paths. The mistake is using unit test passes to claim proxies, transactions, or security have been verified.

## 5. Limit 3 — `@Valid`, `@Validated`, and Bean Validation

Three distinct situations are routinely confused.

### 5.1. Explicit guards written in plain Java

```java
if (amount <= 0) {
    throw new IllegalArgumentException("amount must be positive");
}
```

This is plain Java logic. Unit tests using `new WalletService(...)` **can** verify it directly without Spring. Passing a negative amount and asserting the right exception proves the guard executes.

### 5.2. Method validation on a Spring service

```java
@Service
@Validated
public class WalletService {
    @Transactional
    public int charge(@NotBlank String owner,
                      @Positive int amount,
                      boolean rejectAfterWrite) {
        // ...
    }
}
```

`@NotBlank` and `@Positive` are constraint metadata. When a Bean Validation provider (usually via `spring-boot-starter-validation`) and Spring method validation are active, the Spring proxy validates parameters/return values on bean calls. In this example's default configuration, violating a service constraint throws `jakarta.validation.ConstraintViolationException`.

In a unit test using `new WalletService(...)`, `@NotBlank` **never executes automatically**. To test constraints in plain Java without booting Spring, instantiate a `Validator` and call `validator.validate(...)` on objects or `ExecutableValidator` on method parameters. However, that checks only the **constraint rules**, without proving the Spring proxy invokes validation at runtime.

### 5.3. Validation at controller / DTO

```java
@PostMapping("/wallets")
public ResponseEntity<Void> create(@Valid @RequestBody CreateWalletRequest body) {
    // ...
}
```

This is an **API snippet**, not part of section 7's runnable code. Spring MVC accepts the request, binds JSON into the DTO, and triggers web-boundary validation when properly configured. Use `MockMvc` or HTTP integration tests to verify status codes, error bodies, field errors, and client contracts. A unit test calling `create(new CreateWalletRequest(...))` directly **bypasses the entire MVC binding/validation pipeline**.

`@Valid` triggers object/cascaded validation; Spring's `@Validated` also selects validation groups and activates method-level validation on services. Never treat either annotation as an “instant runtime check” inside an object created via `new`.

### When should you avoid hardcoding one exception class?

Services often throw `ConstraintViolationException` under standard method validation; yet other setups may throw `MethodValidationException` or translated exceptions depending on version/config. MVC layers may return 400 via `MethodArgumentNotValidException` or newer Spring MVC mechanisms. Assert according to **your project's established contract and configuration**, rather than assuming all Spring apps throw the exact same exception class at every layer.

## 6. Limit 4 — `@ConfigurationProperties`: Hand-Built Objects Do Not Prove Property Binding

Spring Boot binds properties from `application.yml`, `application.properties`, environment variables, command-line args, and declared sources. Service unit tests often pass an object like:

```java
WalletService service = new WalletService(
        repository,
        new BillingPolicy(100));
```

This tests logic when the minimum balance is 100. Yet it **fails to test** any of the following:

- Whether the real property key is spelled right, e.g., `billing.minimum-balance`.
- Whether the context actually scans/registers the `@ConfigurationProperties` class.
- Whether values convert/bind to the right types and follow profiles/overrides.
- Whether `@NotNull` or `@Min` constraints on the configuration record are validated during Spring context startup.
- Whether missing or negative properties fail startup as intended.
- Whether multiple beans of the same type, qualifiers, or conditional configurations conflict.

`@ConfigurationProperties` does not turn a Java constructor into a validator. `new BillingPolicy(-10)` still constructs a record holding -10; constraints enforce only when processed by Bean Validation (or explicit validation code).

**Distinguish three test levels for configuration:**

1. Unit test: pass `BillingPolicy(100)`; verify algorithm logic for a concrete value.
2. Context test: load real `@ConfigurationProperties`, assert bound properties, type conversions, and constraints.
3. Profile/environment integration test: verify configuration effect across real services, transactions, and dependencies. Test profiles do not automatically prove production config is identical.

Spring Boot supports `@SpringBootTest(properties = "...")`, `@ActiveProfiles("test")`, `@TestPropertySource`, or `ApplicationContextRunner` depending on the goal. Know which property source wins in config precedence; “green tests with a hand-built default object” never catch YAML typos.

## 7. Runnable Example: One Business Flow, Two Layers of Evidence

This standalone sample project uses **Java 17+, Spring Boot 3.3.5, Gradle Groovy DSL, JUnit Jupiter, Mockito, Spring JDBC, Bean Validation, and H2**. It is intentionally minimal so the boundary between plain Java and Spring proxies can be observed in the database.

**Wallet business contract:**

- `alice`'s wallet starts with balance 500.
- `charge(owner, amount, rejectAfterWrite)` deducts `amount`; if the resulting balance falls below configured `billing.minimum-balance`, throw `IllegalArgumentException` **before writing**.
- `owner` must be non-blank (`@NotBlank`); `amount` must be positive (`@Positive`) when invoked through the Spring-managed proxy with method validation enabled.
- When `rejectAfterWrite=true`, the service throws `ChargeRejectedException` **after updating the repository**. With transactions working, the write must roll back.
- Real config threshold in `application.yml` is 100. Missing `minimum-balance` or negative values must fail Bean Validation when the context binds properties.

This example uses integer currency units for illustration. Real financial systems need explicit monetary types/units, concurrency handling, and transaction isolation; never assume an H2 demo covers all of those concerns.

### 7.1. File structure

```text
settings.gradle
build.gradle
src/main/resources/application.yml
src/main/resources/schema.sql
src/main/java/com/example/testboundary/BoundaryApplication.java
src/main/java/com/example/testboundary/BillingPolicy.java
src/main/java/com/example/testboundary/WalletRepository.java
src/main/java/com/example/testboundary/ChargeRejectedException.java
src/main/java/com/example/testboundary/WalletService.java
src/test/java/com/example/testboundary/WalletServiceUnitTest.java
src/test/java/com/example/testboundary/WalletServiceIntegrationTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'spring-test-boundary'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-jdbc` supplies `JdbcTemplate` and transaction infrastructure; H2 provides the in-memory database used by the example runtime/tests. `spring-boot-starter-validation` brings a Bean Validation provider onto the classpath. `spring-boot-starter-test` supplies JUnit Jupiter, Spring Test, and Mockito. No web server is needed since the example focuses on service/DB boundaries.

**`src/main/resources/application.yml`**

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:walletdemo;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password:
  sql:
    init:
      mode: always

billing:
  minimum-balance: 100
```

H2 creates the `wallets` schema. This configuration is an **educational example** using an in-memory DB; do not use verbatim in production.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE wallets (
    owner VARCHAR(100) PRIMARY KEY,
    balance INTEGER NOT NULL
);
```

`spring.sql.init.mode=always` runs the schema script when the datasource is built; when a test context is cached, schema creation happens once on context startup, **not before every test method**. Therefore each integration test below seeds data in `@BeforeEach`.

### 7.2. Spring Boot application and configuration binding

**`src/main/java/com/example/testboundary/BoundaryApplication.java`**

```java
package com.example.testboundary;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
```

**`src/main/java/com/example/testboundary/BillingPolicy.java`**

```java
package com.example.testboundary;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "billing")
@Validated
public record BillingPolicy(
        @NotNull @Min(0) Integer minimumBalance) {
}
```

Spring Boot binds this record via its single constructor. `@ConfigurationPropertiesScan` registers the config record; `@Validated` and constraints require a non-negative value when the **context binder/validator** runs. Java still allows `new BillingPolicy(-10)`; annotations do not block manual constructor calls.

### 7.3. JDBC repository and Spring-annotated service

**`src/main/java/com/example/testboundary/WalletRepository.java`**

```java
package com.example.testboundary;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class WalletRepository {
    private final JdbcTemplate jdbc;

    public WalletRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int findBalance(String owner) {
        return jdbc.queryForObject(
                "SELECT balance FROM wallets WHERE owner = ?",
                Integer.class, owner);
    }

    public void writeBalance(String owner, int balance) {
        int updated = jdbc.update(
                "UPDATE wallets SET balance = ? WHERE owner = ?",
                balance, owner);
        if (updated != 1) {
            throw new IllegalArgumentException("unknown wallet");
        }
    }
}
```

For a seeded `wallets` row, `findBalance` returns the owner's balance. If no row exists for the owner, Spring JDBC throws a query error; that case sits outside the valid demo scenarios.

**`src/main/java/com/example/testboundary/ChargeRejectedException.java`**

```java
package com.example.testboundary;

public class ChargeRejectedException extends RuntimeException {
    public ChargeRejectedException(String message) {
        super(message);
    }
}
```

**`src/main/java/com/example/testboundary/WalletService.java`**

```java
package com.example.testboundary;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class WalletService {
    private final WalletRepository repository;
    private final BillingPolicy policy;

    public WalletService(WalletRepository repository, BillingPolicy policy) {
        this.repository = repository;
        this.policy = policy;
    }

    @Transactional
    public int charge(@NotBlank String owner,
                      @Positive int amount,
                      boolean rejectAfterWrite) {
        int before = repository.findBalance(owner);
        int after = before - amount;

        if (after < policy.minimumBalance()) {
            throw new IllegalArgumentException(
                    "balance below configured minimum");
        }

        repository.writeBalance(owner, after);

        if (rejectAfterWrite) {
            throw new ChargeRejectedException("payment rejected");
        }

        return after;
    }
}
```

**Explaining three layers inside one method:**

- Subtraction and threshold checks are **Java logic**: direct unit tests run them.
- `@Transactional` needs **transaction advice** and a transaction manager when invoked via a Spring proxy; it does not live in the method body.
- `@NotBlank` and `@Positive` need **method validation** via a Spring proxy; they do not run on objects created with `new`.
- `BillingPolicy` passed via constructor can be hand-created in unit tests or bound by Spring; the service itself cannot tell them apart from the field value alone.

Another risk in real applications is **lost updates** when concurrent requests read and overwrite the same balance. This demo adds no locks, optimistic versioning, or atomic SQL updates; the tests below **do not prove concurrency safety**.

### 7.4. Mockito unit test: proves rules, does not prove transactions

**`src/test/java/com/example/testboundary/WalletServiceUnitTest.java`**

```java
package com.example.testboundary;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrowsExactly;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class WalletServiceUnitTest {
    @Mock
    private WalletRepository repository;

    private WalletService service;

    @BeforeEach
    void setUp() {
        service = new WalletService(repository, new BillingPolicy(100));
    }

    @Test
    void computesBalanceAndWritesExpectedValue() {
        when(repository.findBalance("alice")).thenReturn(500);

        assertEquals(350, service.charge("alice", 150, false));
        verify(repository).writeBalance("alice", 350);
    }

    @Test
    void throwsAfterWriteButCannotProveRollback() {
        when(repository.findBalance("alice")).thenReturn(500);

        ChargeRejectedException exception = assertThrowsExactly(
                ChargeRejectedException.class,
                () -> service.charge("alice", 150, true));

        assertEquals("payment rejected", exception.getMessage());
        verify(repository).writeBalance("alice", 350);
    }

    @Test
    void directInvocationDoesNotApplyMethodValidation() {
        when(repository.findBalance("")).thenReturn(500);

        assertEquals(450, service.charge("", 50, false));
        verify(repository).writeBalance("", 450);
    }

    @Test
    void preventsBalanceBelowConfiguredMinimum() {
        when(repository.findBalance("alice")).thenReturn(500);

        IllegalArgumentException exception = assertThrowsExactly(
                IllegalArgumentException.class,
                () -> service.charge("alice", 450, false));

        assertEquals("balance below configured minimum",
                exception.getMessage());
    }
}
```

The first test proves `350` is calculated properly with mocked dependencies and `BillingPolicy(100)`. The second test proves the method **calls write before throwing the runtime exception**; it cannot confirm rollback because `WalletRepository` is a mock with no database.

`directInvocationDoesNotApplyMethodValidation` is an **intentional counterexample**: `owner=""` violates `@NotBlank`, yet the call still reaches the mock repository and returns 450 because `WalletService` was constructed directly. This demonstrates the annotation's limit; in real systems, add domain guards or verify validation at the protected boundary.

The final test protects the threshold rule inside the **Java body**. Passing all unit tests still neither confirms the YAML property key nor verifies transaction proxy behavior.

### 7.5. Integration test: verifies DB rollback, proxy validation, and binding

**`src/test/java/com/example/testboundary/WalletServiceIntegrationTest.java`**

```java
package com.example.testboundary;

import jakarta.validation.ConstraintViolationException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertThrowsExactly;

@SpringBootTest
class WalletServiceIntegrationTest {
    @Autowired
    private WalletService service;

    @Autowired
    private WalletRepository repository;

    @Autowired
    private BillingPolicy policy;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void seedWallet() {
        jdbc.update("DELETE FROM wallets");
        jdbc.update(
                "INSERT INTO wallets(owner, balance) VALUES (?, ?)",
                "alice", 500);
    }

    private int balance() {
        return repository.findBalance("alice");
    }

    @Test
    void springBindsApplicationProperties() {
        assertEquals(100, policy.minimumBalance());
    }

    @Test
    void successfulChargePersistsItsChange() {
        assertEquals(350, service.charge("alice", 150, false));
        assertEquals(350, balance());
    }

    @Test
    void runtimeExceptionRollsBackDatabaseWrite() {
        assertThrowsExactly(ChargeRejectedException.class,
                () -> service.charge("alice", 150, true));

        assertEquals(500, balance());
    }

    @Test
    void proxiedMethodValidationRejectsBlankOwner() {
        assertThrows(ConstraintViolationException.class,
                () -> service.charge("", 50, false));

        assertEquals(500, balance());
    }

    @Test
    void configuredMinimumIsAppliedByService() {
        assertThrowsExactly(IllegalArgumentException.class,
                () -> service.charge("alice", 450, false));

        assertEquals(500, balance());
    }

    @Test
    void directlyConstructedServiceDoesNotOpenTransaction() {
        WalletService direct = new WalletService(repository, policy);

        assertThrowsExactly(ChargeRejectedException.class,
                () -> direct.charge("alice", 150, true));

        assertEquals(350, balance());
    }
}
```

**Reading assertions by level of evidence:**

- `springBindsApplicationProperties` confirms the application actually loads `BillingPolicy` containing 100 from the context; unit test `new BillingPolicy(100)` cannot show this.
- `successfulChargePersistsItsChange` invokes the Spring-managed bean, then reads the real DB to confirm the write committed.
- `runtimeExceptionRollsBackDatabaseWrite` triggers an unchecked exception after writing, then reads the DB **after the service threw**, expecting 500 to remain. That is concrete evidence of service rollback in this test setup.
- `proxiedMethodValidationRejectsBlankOwner` confirms validation advice is active; since `owner=""` does not exist in the DB, without validation the call would fail on a DB query. Checking the **exact exception type** `ConstraintViolationException` distinguishes the two mechanisms.
- `configuredMinimumIsAppliedByService` confirms the bean received the threshold and the service enforces 100.
- `directlyConstructedServiceDoesNotOpenTransaction` is a **counterexample deliberately kept in the demo**: even with real repository and config beans, a `WalletService` created via `new` bypasses the transaction proxy. Under H2/JDBC auto-commit here, the write of 350 persists despite the exception. That situation is **not intended as production behavior**; it shows why direct calls cannot evaluate transactions.

The integration test class intentionally **omits** `@Transactional` so framework-managed test transactions around each test method do not mask the production service's real commit/rollback behavior. `@BeforeEach` resets the table to one row; the lesson assumes sequential execution. When running tests in parallel against a shared DB, isolate databases/schemas/test rows so concurrent tests do not delete each other's data.

### 7.6. Running the example

Place or generate a Gradle Wrapper compatible with Spring Boot 3.3.x in the project directory. On Linux/macOS:

```bash
./gradlew test
./gradlew test --tests com.example.testboundary.WalletServiceUnitTest
./gradlew test --tests com.example.testboundary.WalletServiceIntegrationTest
```

On Windows, run `gradlew.bat` with the same arguments.

With matching code and environment, both unit and integration tests are **expected** to PASS. This is an expected result derived from the example logic, not stdout observed from a live run. Assertions confirm concrete states: 350 after successful charge; 500 after rollback; `ConstraintViolationException` for blank owner through proxy; 350 in the direct `new` counterexample.

To experiment intentionally:

1. Remove `@Transactional` from `WalletService.charge`. Unit tests still pass, whereas `runtimeExceptionRollsBackDatabaseWrite` FAILS because the DB retains 350.
2. Remove `@Validated` from the service (without enabling method validation another way). Unit tests do not change; integration test `proxiedMethodValidationRejectsBlankOwner` stops throwing `ConstraintViolationException`.
3. Change `billing.minimum-balance: 100` to `150`. Unit tests still use the hardcoded 100 object and miss the YAML change; integration tests checking binding 100 and the threshold fail.
4. Change `billing.minimum-balance` to a negative number. Because the context validates `BillingPolicy`, startup must fail when Bean Validation is active.
5. Remove `@ConfigurationPropertiesScan`. Spring no longer registers `BillingPolicy` via that scan path; the integration context fails to instantiate `WalletService` due to the missing dependency.

After experimenting, restore the original code and config. Never assume a failing test always produces identical exception wording: startup exception wrappers and messages vary across Boot/Bean Validation versions, while the failure phase itself is the main signal.

## 8. Additional Checks When Risk Is High

The example above demonstrates four fundamental boundaries. In real systems, expand checks according to risk type.

### 8.1. Transaction propagation, rollback rules, and checked exceptions

`@Transactional` defaults to `propagation=REQUIRED`: the method joins an active transaction or starts a new one if none exists. `REQUIRES_NEW`, nested transactions, or multiple transaction managers carry different semantics. One single-service call test does not prove propagation across multiple services, datasource/transaction-manager selection, or rollback rules for checked exceptions.

Illustrative **rollback configuration snippet**, not part of section 7's project:

```java
@Transactional(rollbackFor = java.io.IOException.class)
public void importFile() throws java.io.IOException {
    // Writes data then may throw IOException.
}
```

Pure Java unit tests observe `IOException`, yet only integration tests with real transactions verify data actually rolls back under `rollbackFor`. Likewise, wrapping a test method in `@Transactional` distorts conditions compared to real HTTP requests running on independent threads/transactions.

### 8.2. Validation: right place, right layer, right error type

For validation, prefer testing at the corresponding layer:

- Java domain rules: unit tests.
- DTO Bean Validation constraints: `Validator` tests (when testing constraints only) and Spring MVC tests when verifying binding/HTTP statuses.
- Service method parameter/return constraints: call the bean through a Spring context with `@Validated`/method-validation infrastructure active.
- Configuration properties: test context binding and startup validation, especially required keys, conversions, and invalid values.

Never force every layer to throw the same exception class. Invalid JSON on a DTO may be rejected by MVC before the service runs; service validation may throw `ConstraintViolationException`; domain rules may throw `IllegalArgumentException`. Right or wrong depends on **the contract of the layer under test**.

### 8.3. Configuration: profiles, conditions, and overrides

`@SpringBootTest` loads project/test `application.yml`, yet does not automatically prove production profiles match. For critical config, check:

- `@ConfigurationProperties` beans are registered and bind the right keys.
- Missing required values or bad types block startup.
- `@ConditionalOnProperty`, `@Profile`, or bean overrides select the right implementations.
- Property source precedence works as intended when tests add `@SpringBootTest(properties=...)`, environment variables, or `@ActiveProfiles`.
- Actual bound config drives expected logic and bean selection.

For auto-configuration libraries, `ApplicationContextRunner` spins up narrow contexts across property combinations and asserts bean presence/absence or startup failures. For business flows integrating multiple beans, `@SpringBootTest` fits better when verifying application wiring. **Never replace all unit tests with `@SpringBootTest`** merely because annotations exist.

### 8.4. In-memory databases do not guarantee production equivalence

H2 is convenient for basic transaction/rollback checks, yet cannot prove production behaviors of PostgreSQL, MySQL, Oracle, etc.—such as isolation levels, locking, SQL dialects, triggers, constraints, timezones, or specialized transaction semantics. When those details pose business risk, run integration tests against the real DB engine (e.g., via Testcontainers) with production-like schemas/migrations and settings.

A green test on H2 proves rollback/commit occurred **in H2 under the tested configuration**. Never extrapolate that claim to the entire data tier without stronger evidence.

## 9. Signs a Unit Test Is Overclaiming

| Claim | Why it is insufficient | What to add |
| --- | --- | --- |
| “`verify(save)` passed, so transaction rollback works” | Mocks hold no transaction/DB state | Integration test inspecting DB after exception |
| “Service has `@Transactional`, so calling via `new` is transactional” | Annotations do not generate advice by themselves | Fetch Spring bean and invoke via proxy |
| “`@NotBlank` guarantees blank inputs are always blocked” | Constraint metadata needs validation infrastructure | Method validation test or explicit guard |
| “`@Valid` on DTO was tested by calling the controller directly in Java” | Bypasses MVC binding/validation pipeline | MockMvc or HTTP test checking 400/body |
| “`new BillingPolicy(100)` proves YAML config is right” | Object was constructed manually | Load context and check binding/constraints |
| “`@SpringBootTest` passed so all business logic works” | Context loading asserts no business branches | Unit and integration tests with explicit expected outcomes |
| “Test had `@Transactional` and DB stayed clean, so service rollback works” | Rollback may come from the **test's own transaction** | Test service boundary without a test-managed transaction |
| “Unit test mocks dependencies, so `@Cacheable` or `@Async` are verified” | Proxy advice does not run on `new` objects | Test via managed bean with matching infrastructure |
| “H2 transaction passed, so production concurrency is safe” | Different DB engines and isolation change outcomes | Test real engine, locking/versioning, concurrent scenarios |

Several of these pitfalls can occur together: a unit test creates `new` directly, mocks repositories, and passes hand-built config objects. That is an **intentionally simplified environment**; the test should claim correctness only within that scope.

## 10. Testing Strategy Organized by Responsibility Boundary

Structure evidence so each layer answers one specific question:

1. **Unit tests for business rules**: given valid/invalid inputs, check outputs, exceptions, boundaries, and meaningful dependency calls. Use Mockito for isolation; never boot a context just to run arithmetic.
2. **Context/wiring tests**: verify Spring constructs beans, binds properties, applies profiles/qualifiers/conditions, and wires proxy infrastructure. A context test catches startup errors without proving runtime business behavior on its own.
3. **Integration tests at the service boundary**: use real repositories and a real DB, call Spring beans through proxies, and inspect state after success/failure. Crucial for transactions/rollback, method validation, and config-driven behavior.
4. **Web/API tests**: verify clients receive accurate statuses, response schemas, security/validation filters, and HTTP exception mapping. Calling controllers via `new` skips that pipeline.
5. **Production-like infrastructure tests**: when conclusions depend on DB engine, cache, message broker, concurrency, or feature flags. Balance execution cost against feature risk.

A healthy test suite does not need lots of `@SpringBootTest` classes; what matters is **verifying each mechanism outside plain Java at the right layer**. Fast unit tests paired with targeted integration tests are usually easier to maintain and diagnose than trying to solve everything with one test type.

## 11. Counterexample Exercises and Review Checklist

**Scenario A.** A test creates `new WalletService(mockRepo, new BillingPolicy(100))`, calls `charge("alice",150,true)`, and asserts `ChargeRejectedException`. Does that prove DB rollback? **No**. It proves only that the method throws along its Java branch after interacting with a mock. Read the DB after invoking through a Spring transaction proxy.

**Scenario B.** `@Transactional` sits on one method, yet another method on the same object calls `this.method()`. Is advice guaranteed to fire? **No** in standard proxy mode: self-invocation bypasses the proxy. Redesign the call boundary or use another verified mechanism.

**Scenario C.** `@NotBlank` sits on a parameter; a unit test calling `new WalletService(...).charge("",50,false)` runs without throwing. Is the annotation syntax wrong? **Not necessarily**; Bean Validation constraints are not enforced by Spring interceptors on manually instantiated objects. Test through a Spring-managed bean with method validation configured.

**Scenario D.** A test puts `@Transactional` on the test method itself, calls a non-transactional service, and sees DB writes vanish after the test. Does that prove the service rolls back? **No**. The test's own transaction may be rolling back. Test the service's real transaction boundary without a wrapping test transaction.

**Scenario E.** Unit tests pass `new BillingPolicy(100)`; in YAML the key is misspelled `billing.minimum-balnce`. Will unit tests catch the typo? **No**. Context binding tests or `@NotNull` validation during context startup catch it.

**Scenario F.** H2 integration tests pass, yet production uses another DB and suffers lost updates under concurrent load. Is there a contradiction? **No**. Sequential H2 tests do not protect real DB isolation levels or concurrency.

### QA sign-off checklist for a Spring Boot test suite

- Do critical business assertions have independent unit tests with requirements-derived expected values?
- Does any test call `new Service` and claim `@Transactional`, `@Validated`, or `@Async` has been verified?
- Could self-invocation, final/private methods, or proxy modes prevent expected advice interception?
- Do rollback tests invoke Spring-managed beans, execute real DB writes, and inspect post-exception state **without being masked by a test transaction**?
- Do validation tests distinguish plain Java guards, service-level constraints, and MVC-boundary validation?
- Are `@ConfigurationProperties` bound from real keys, validated, and tested under the right profiles?
- Do context tests claim only startup/wiring, or include dedicated behavioral assertions before making business claims?
- When DB/caching/concurrency carry risk, is the test environment close enough to production with documented limits?
- Do tests run independently without order sensitivity or state leaks via singletons/DB across cases?

**Conclusion:** Unit tests excel at verifying **business logic inside Java method bodies**. Yet `@Transactional`, Spring AOP proxies, Bean Validation, and property binding are behaviors orchestrated by the **Spring runtime**. To verify them, invoke beans inside an appropriate context, observe exceptions/responses and real state changes, and bound claims accurately to the tested environment.