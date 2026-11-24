# Spring Proxies in Tests: Transactions, Caching, and Method Security

In a Spring Boot application, a method annotated with `@Transactional`, `@Cacheable`, or `@PreAuthorize` can behave **very differently when invoked through a Spring-managed bean** compared to calling it directly on an object created with `new`. The reason is usually a **Spring AOP proxy**: an intermediary object that intercepts calls to open/close transactions, read/write caches, or check permissions before forwarding to the business code.

This lesson belongs to the **Spring TestContext** group: the goal is not merely to verify plain Java logic, but to verify that **the path through the Spring proxy actually works in a test context**. Transactions, caching, and method security share the common trait that framework behavior typically happens *outside the method body*, yet each has its own observable contract and suitable test style.

## 1. Distinguishing Real Methods, Beans, Proxies, and Proxied Calls

Consider a conceptual example:

```java
@Transactional
public void transfer() {
    debit();
    credit();
}
```

An annotation is metadata, not a Java statement that creates a transaction by itself. With Spring's proxy-based transaction mechanism, when an external bean calls `transfer()` through the proxy, the interceptor gets a chance to start a transaction, run the real logic, and then commit or roll back based on the outcome. If you write `new TransferService(...).transfer()`, Spring has no opportunity to intercept the call.

```text
                         bean reference injected by Spring
Caller  -----------------------------------------------+
                                                      |
                                                      v
                                           [Spring AOP proxy]
                                            /      |       \
                                    transaction  cache  authorization
                                            \      |       /
                                                      |
                                                      v
                                               [Target object]
                                                      |
                                                      v
                                              Business method
```

**Core concepts to grasp:**

- **Target:** the object holding the business logic; its Java methods run as usual.
- **Proxy:** the object Spring provides to callers, which can execute one or more interceptors/advisors before and after the call.
- **Advice/interceptor:** framework logic (transactions, caching, authorization) applied when a method matches the configuration.
- **`ApplicationContext`:** where Spring creates beans, resolves dependencies, registers proxy infrastructure, and supplies bean references.
- **Spring TestContext:** Spring Test infrastructure integrated with JUnit Jupiter to create and reuse an `ApplicationContext` in tests; for example `@SpringJUnitConfig` and `@SpringBootTest`.

**Key point:** for proxy-based features, **"the test method ran correctly" does not mean "the annotation was executed by Spring."** Tests must go through the bean obtained from the context and verify a characteristic effect of the proxy, not just business output.

## 2. When Do Tests Need Spring and When Do They Not?

| What Needs to Be Verified | Unit Test with `new Service(...)` | Test with a Spring Context |
| --- | --- | --- |
| Calculation functions, validation, pure state machines | Suitable, fast | Usually unnecessary |
| Whether a service calls a repository port | Suitable with mocks/fakes | Add only when wiring or integration is needed |
| `@Transactional` actually rolls back written data | No; annotations do not run themselves | Needs proxy + transaction manager + real data source |
| `@Cacheable` returns cached result without re-running target | No if calling target via `new` | Needs caching advisor + real `CacheManager` |
| `@PreAuthorize` blocks unauthorized callers | No if calling target via `new` | Needs method-security interceptor + `SecurityContext` |
| JSON binding, filter chain, HTTP status | No | Needs MVC/WebFlux slice or appropriate integration test |
| Redis TTL, DB isolation, real transaction propagation | Mocks cannot prove this | Needs adapter/integration test with real infrastructure |

Do not use `@SpringBootTest` for every test just because the source code lives in a Spring Boot project. **Widen a test's scope only when the behavior to prove genuinely depends on Spring or infrastructure.** Conversely, when requirements explicitly involve transaction, cache, or security proxies, plain Java tests alone are insufficient.

## 3. Proxy Types and Situations Where Advice Easily Fails to Run

At a basic level, Spring AOP can use a **JDK dynamic proxy** (typically for interfaces) or a **class-based proxy** via subclassing (commonly called a CGLIB proxy). Selection depends on interfaces, proxy settings, and the active mechanism.

- **JDK dynamic proxy:** the proxy implements the proxied interfaces; a bean typed by its interface works normally, whereas casting to the concrete implementation class may fail.
- **Class-based proxy:** the proxy is a subclass of the target class. `final` methods cannot be overridden to intercept via subclassing; `final` classes also prevent creating subclass proxies. Private methods are not interception points for standard external proxy calls.
- **Self-invocation:** when a method inside the target calls `this.anotherMethod()`, the internal call normally does not exit and re-enter **through the proxy**, so proxy-based advice on `anotherMethod()` may be bypassed.
- **Objects created with `new`:** not proxy beans, even if the class has annotations.
- **Unenabled annotations:** you can add `@Transactional`/`@Cacheable`/`@PreAuthorize` without enabling transaction/caching/method-security infrastructure; plain Java logic still executes and can produce a "false green" test.

A self-invocation snippet just to visualize:

```java
public String outer(String sku) {
    return this.cachedPrice(sku); // Internal call inside the target
}

@Cacheable("prices")
public String cachedPrice(String sku) {
    return fetchPrice(sku);
}
```

This is an **illustrative method snippet**, not a standalone runnable class (`fetchPrice` is absent). If a caller invokes `outer(...)` on the bean, the internal call `this.cachedPrice(...)` will not necessarily pass through caching advice. A better design moves the intercepted boundary to a separate bean and calls **the injected proxy bean**, or restructures so advice applies at the proper public entrypoint. Do not route calls through `ApplicationContext` or self-injection just to "force the proxy" without evaluating the design impact.

**Do not guess the proxy type from an annotation alone.** Inspect proxies using Spring APIs when diagnosing—such as `AopUtils.isAopProxy(bean)`, `AopUtils.isJdkDynamicProxy(bean)`, or `AopUtils.isCglibProxy(bean)`. More important than identifying the proxy kind is testing the **real effects** of transactions, caching, and security.

## 4. Spring TestContext Example Verifying All Three Proxies

The example below uses **Java 17+, JUnit Jupiter, Spring TestContext, H2 in-memory, and Spring Security method security**. The goal is to run real code through proxies without mocking the interceptors themselves. It intentionally configures a small context using `@SpringJUnitConfig` rather than bootstrapping the entire application.

**Three independent behaviors to verify:**

1. `AuditService.addThenFail(...)` inserts a row via JDBC and then throws `IllegalStateException`. When the transaction interceptor runs, the data must roll back. `addNormally(...)` must commit.
2. `PriceService.quote(sku)` computes a value and increments a counter. With `@Cacheable`, two calls through the proxy with the same key return the same result while the target computes only once.
3. `DocumentService.readSecret()` permits only authority `doc:read` per `@PreAuthorize`. Callers lacking that authority are blocked before receiving data.

### 4.1. Preparing Dependencies

The example can run in a Spring Boot/Gradle project with plugins, repositories, and dependency management configured. Relevant lines in `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is an **additive configuration snippet**, not a complete standalone `build.gradle`. `spring-security-test` provides test support such as `@WithMockUser`; do not assume this dependency is present simply because a project includes `spring-boot-starter-test`. H2 is an in-memory test database; when production uses a database with its own dialect or constraints, write integration tests against that DB engine.

Create a single file:

```text
src/test/java/example/testing/proxy/ProxyBehaviorTest.java
```

The test defines nested classes and configuration internally so no extra source files are needed for the example.

### 4.2. Complete Test File: `ProxyBehaviorTest.java`

```java
package example.testing.proxy;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(ProxyBehaviorTest.Config.class)
class ProxyBehaviorTest {

    @Autowired
    private AuditService auditService;

    @Autowired
    private PriceService priceService;

    @Autowired
    private DocumentService documentService;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private CacheManager cacheManager;

    @BeforeEach
    void resetState() {
        jdbc.execute("""
            CREATE TABLE IF NOT EXISTS audit_entry (
                id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                note VARCHAR(100) NOT NULL
            )
            """);
        jdbc.update("DELETE FROM audit_entry");

        Cache cache = Objects.requireNonNull(
                cacheManager.getCache("prices"));
        cache.clear();
    }

    @Test
    void servicesAreSpringAopProxies() {
        assertTrue(AopUtils.isAopProxy(auditService));
        assertTrue(AopUtils.isAopProxy(priceService));
        assertTrue(AopUtils.isAopProxy(documentService));
    }

    @Test
    void transactionRollsBackOnRuntimeException() {
        assertThrows(IllegalStateException.class,
                () -> auditService.addThenFail("failed"));

        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_entry", Long.class);
        assertEquals(0L, count.longValue());
    }

    @Test
    void transactionCommitsOnNormalReturn() {
        auditService.addNormally("ok");

        Long count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_entry", Long.class);
        assertEquals(1L, count.longValue());
    }

    @Test
    void cacheAvoidsRecomputingForSameKey() {
        int before = priceService.computations();

        String first = priceService.quote("SKU-1");
        String second = priceService.quote("SKU-1");
        String other = priceService.quote("SKU-2");

        assertEquals(first, second);
        assertNotEquals(first, other);
        assertEquals(before + 2, priceService.computations());
    }

    @Test
    @WithMockUser(authorities = "doc:read")
    void authorizedCallerCanRead() {
        assertEquals("classified", documentService.readSecret());
    }

    @Test
    @WithMockUser(authorities = "doc:write")
    void callerWithoutReadAuthorityIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> documentService.readSecret());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    @EnableCaching
    @EnableMethodSecurity
    static class Config {

        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:proxy_lesson;DB_CLOSE_DELAY=-1",
                    "sa", "");
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("prices");
        }

        @Bean
        AuditService auditService(JdbcTemplate jdbc) {
            return new AuditService(jdbc);
        }

        @Bean
        PriceService priceService() {
            return new PriceService();
        }

        @Bean
        DocumentService documentService() {
            return new DocumentService();
        }
    }

    public static class AuditService {
        private final JdbcTemplate jdbc;

        public AuditService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void addNormally(String note) {
            jdbc.update(
                    "INSERT INTO audit_entry(note) VALUES (?)", note);
        }

        @Transactional
        public void addThenFail(String note) {
            jdbc.update(
                    "INSERT INTO audit_entry(note) VALUES (?)", note);
            throw new IllegalStateException("failed deliberately");
        }
    }

    public static class PriceService {
        private final AtomicInteger counter = new AtomicInteger();

        @Cacheable(cacheNames = "prices")
        public String quote(String sku) {
            return sku + "#" + counter.incrementAndGet();
        }

        public int computations() {
            return counter.get();
        }
    }

    public static class DocumentService {
        @PreAuthorize("hasAuthority('doc:read')")
        public String readSecret() {
            return "classified";
        }
    }
}
```

**Self-contained design:** all demo classes, configuration, and services are defined in the same Java file. `AuditService`, `PriceService`, and `DocumentService` are nested `public static` **non-final** classes, and their proxied methods are `public` and non-final. Spring registers them via `@Bean`, and the test uses the exact references injected by the context. With this specific configuration, no repository interface or HTTP controller is needed.

**Do not place `@Transactional` on the test class or test methods** in this example. The goal is to observe the transaction opened by the *service proxy* and inspect the persisted data **after the service call completes**. If the test itself runs inside a transaction rolled back by Spring Test afterward, rows visible inside that shared transaction can produce misleading evidence.

### 4.3. Running the Test File

From the root directory of a Gradle project with the wrapper:

```bash
./gradlew test --tests example.testing.proxy.ProxyBehaviorTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.proxy.ProxyBehaviorTest"
```

**Expected:** there are **6 test methods** and all pass when the listed dependencies are properly configured, H2 is on the test runtime classpath, and Spring TestContext builds the context successfully. Gradle/JUnit has no single fixed stdout string; inspect the test runner report to verify each test.

This file **is not a plain Java program run with `javac File.java; java File`**: it depends on Spring Framework, Spring Security, JUnit, and H2, so it requires the configured dependency classpath and test engine via Gradle or Maven. Do not fabricate `javac/java` stdout for this framework test. If you want to test pure business rules, write a separate `new Service(...)` test—though that will not verify proxies.

### 4.4. Explaining Why Each Test Matters

**Test 1 — proxy exists.** `AopUtils.isAopProxy(...)` signals that Spring is providing an AOP-proxied reference. It helps diagnose missing `@EnableTransactionManagement`/`@EnableCaching`/`@EnableMethodSecurity`, though **merely having a proxy does not prove the right effect**. The remaining tests verify each behavior.

**Test 2 — real rollback.** `auditService.addThenFail("failed")` passes through the transaction interceptor; `JdbcTemplate` joins the transaction on the same `DataSource` as `DataSourceTransactionManager`. After the runtime exception, the transaction must roll back. The test queries the table via JDBC after the method finishes and expects **0 rows**. Calling a non-transactional object via `new AuditService(jdbc)` would let the insert auto-commit on the datasource before the exception is thrown; the rollback test catches that difference.

**Test 3 — real commit.** `addNormally("ok")` completes normally. Afterward, JDBC sees one existing row. This acts as a companion check for the rollback test, preventing false confidence in "0 rows" when inserts never happened at all. In real systems, you can also assert `note` values, uniqueness, and transaction isolation if part of the contract.

**Test 4 — real caching.** `PriceService.quote("SKU-1")` runs the target and increments `counter`. The second call with the same key hits the cache advisor and returns the stored value without incrementing the counter. Calling with `SKU-2` uses a different key so the target computes again. The test checks the delta `before + 2` instead of assuming the counter starts at 0, because the bean/context may be reused across tests; only the cache is cleared before each test.

**Tests 5–6 — real method security.** `@WithMockUser(authorities = "doc:read")` populates a test `Authentication` in `SecurityContext`, so `hasAuthority('doc:read')` passes. With `doc:write`, the method-security proxy rejects the call with an `AccessDeniedException` subtype. This test verifies **method-level authorization** through the proxy; it **does not send an HTTP request**, and does not prove security filter chains or HTTP 403 status codes.

## 5. Which Spring TestContext Should You Use?

Drawing the right boundary keeps tests fast while still proving proxy behavior.

| Tool | Context | When to Use |
| --- | --- | --- |
| JUnit + `new Service(...)` | No Spring | Pure rules, conditional logic, orchestration with mocks |
| `@SpringJUnitConfig(Config.class)` | Minimal Spring context with test-specified beans/configs | Want to verify specific AOP proxies without full app auto-configuration |
| `@SpringBootTest` | Broad Boot context, application auto-configuration | Need to prove production wiring and the app's real transaction/cache/security beans |
| `@DataJpaTest` | JPA/repository slice | Verifying mappings/queries; does not automatically prove service-layer AOP |
| `@WebMvcTest` + `MockMvc` | MVC slice and HTTP infrastructure | Need controller request/validation/filter/status behavior and HTTP-layer security |
| Tests using real Redis/DB/brokers | Corresponding adapters/infrastructure | Need to prove TTL, serialization, unique constraints, transaction isolation, network behavior |

**`@SpringJUnitConfig`** pairs Spring Test configuration with JUnit Jupiter. It builds the context from `Config`; in the example we explicitly enabled the three features with `@EnableTransactionManagement`, `@EnableCaching`, and `@EnableMethodSecurity`. Because full Spring Boot auto-configuration is not enabled, it is transparent which beans participate.

**`@SpringBootTest`** fits when verifying real application configuration—provided you ensure the right beans and test profile are active. A test that mocks out the target bean or fakes the transaction manager can unintentionally **stop verifying what the author meant to prove**.

**TestContext caching:** Spring Test can reuse an `ApplicationContext` across tests with equivalent configurations to save bootstrap time. Therefore, mutable bean state, caches, and DB data **do not reset automatically** after each method. The example test explicitly clears the table and cache in `@BeforeEach`. For parallel tests, isolate databases, caches, and contexts properly; do not treat `@BeforeEach` on a shared DB as thread-safe for parallel execution.

## 6. Transaction Proxies: Mechanics and Required Evidence

### 6.1. When Is a Transaction Created?

With proxy-based declarative transactions, the flow is typically:

```text
Caller -> transactional proxy
       -> TransactionInterceptor / transaction manager
       -> begin or join transaction according to propagation
       -> target business method (JDBC/JPA work)
       -> commit on normal return
       -> rollback for configured failure types
       -> return/throw to caller
```

Actual details depend on `Propagation`, isolation, transaction manager, exception types, and infrastructure. **`@Transactional` does not start a transaction if the call bypasses Spring's configured proxy mechanism.**

Cases your tests should cover:

- Success: evidence that changes actually **committed** after the proxy method returned.
- Runtime exception: data written during the transaction **rolled back**.
- Checked exception: by default Spring typically **does not roll back** on a checked exception alone; if business rules require rollback, declare `rollbackFor` or equivalent policy and test with real data.
- Propagation: with `REQUIRES_NEW`, the inner transaction can commit independently of the outer transaction, so a unit test mocking the repository cannot prove the outcome.
- Self-invocation: a method inside the same target calling another annotated method via `this` can bypass the proxy, so new propagation does not trigger automatically.

**Checked exception example (illustrative, not a standalone runnable class):**

```java
@Transactional(rollbackFor = IOException.class)
public void importFile() throws IOException {
    repository.save(record);
    throw new IOException("invalid source");
}
```

Because this is an illustrative method snippet, it assumes `repository` and `record` are already defined. Accurate transaction tests need a database environment and post-exception rollback verification. Do not toggle `rollbackFor` by guesswork: if a checked exception represents a business failure meaning "cannot continue," design and test the rollback policy explicitly.

### 6.2. The Test-Managed Transaction Rollback Trap

Spring Test can use `@Transactional` on a test method to open a transaction and roll it back after the test. This is helpful for **isolating test data**, but it can prevent service transaction tests from reflecting real commits.

Example:

```java
@Transactional
@Test
void example() {
    service.save(...);
    assertEquals(1, repository.count());
}
```

This is an illustrative structural snippet, not standalone. If the service joins the transaction opened by **the test**, `repository.count()` sees **uncommitted** data within that same transaction. A passing test does not prove the service actually commits; when the test method completes, Spring Test rolls everything back. To test a service's commit/rollback behavior as in Section 4, **omit `@Transactional` on the test**, call the proxy bean, and read the database after the service transaction finishes.

If you need to test logic inside a test-managed transaction, keep the distinction clear: using `@Transactional` on tests for cleanup is sensible, but do not cite it as evidence of an annotated service's commit/rollback behavior. For complex cases, use `TransactionTemplate`, `TestTransaction`, or appropriate framework transaction APIs and verify the exact commit/rollback boundaries intended.

### 6.3. Proxies, Public Methods, and Self-Invocation

In standard proxy configurations, annotations on public methods invoked through the bean proxy are the most predictable pattern. Private methods do not become proxy entrypoints merely by adding `@Transactional`. With class-based proxies, `final` methods cannot be overridden to intercept; interface-based JDK proxies carry their own constraints. Never cite an annotation's presence in source code as proof that advice executed.

**Separate beans when independent transactions are needed:** if `OrderService.place` must call `PaymentService.charge` in a separate transaction/propagation, inject `PaymentService` as a bean and invoke it through that reference. Transaction tests must prove what happens when a method fails, not merely `verify(paymentService).charge(...)`.

## 7. Cache Proxies: Compute Once, Serve from Cache Many Times

### 7.1. `@Cacheable` Genuinely Changes the Call Path

When a `@Cacheable` method is invoked through its proxy:

1. The cache interceptor determines the cache name and cache key (from parameters or key configuration).
2. If a valid entry exists in the cache, the interceptor **returns that cached result immediately**, skipping the target.
3. On a cache miss, the target executes; the result is stored in the cache under the configured policy for future calls.

Therefore, a meaningful test must prove that **the target does not execute again** for the same key. In the example, `computations()` increments exactly twice for two distinct keys despite three calls.

**Things to avoid:**

- Calling `new PriceService().quote("SKU-1")` twice and thinking caching is broken. That object bypasses the caching proxy.
- Calling a method on the same target that delegates internally to a `@Cacheable` method and expecting a cache hit. Self-invocation can bypass the proxy.
- Only asserting that two calls return the same value. If the target is a deterministic pure function, that assertion passes **even without caching**. Measure target executions or actual outbound calls.
- Failing to clear caches between tests. An entry left by an earlier test can make the current test pass or fail for the wrong reason.

### 7.2. Related Annotations

- `@Cacheable`: uses the cache to avoid recomputing when the key hits.
- `@CachePut`: always executes the method and updates the cache as configured; does not skip the target like `@Cacheable`.
- `@CacheEvict`: removes a cache entry or clears a cache region as configured during mutations.
- `@Caching`: groups multiple caching operations.

Illustrative example (inside a proxied bean, not a complete class):

```java
@CacheEvict(cacheNames = "prices", key = "#sku")
public void changePrice(String sku, BigDecimal newPrice) {
    repository.update(sku, newPrice);
}
```

This snippet assumes `repository`, `BigDecimal`, and matching cache keys are configured. If reads use a different key than evictions, stale data will keep being served. Real systems must also consider transaction commits and eviction timing: evicting cache before a transaction fails can cause temporary inconsistency. A test using only `ConcurrentMapCacheManager` **does not prove** Redis TTL, distributed locking, serialization, or multi-node update behavior.

### 7.3. Production Cache Tests vs. Minimal Cache Tests

In Section 4, `ConcurrentMapCacheManager` is an **in-JVM** cache used to prove the advisor and key matching. It fits the goal "a second call through the caching proxy skips the target." When production uses Redis or Caffeine with TTLs, eviction policies, serialization, and concurrency behavior, write **adapter/integration tests** against the real production implementation.

For mutable cached data, test **stale-data risk**, invalidation rules, and when cache entries change—not just the happy path. With parallel tests, a shared cache can break counter and hit/miss independence.

## 8. Method Security: Not an HTTP Filter and Not Manual Role Checks

### 8.1. `@EnableMethodSecurity` and `@PreAuthorize`

Spring Security provides method-level interception independent of whether the caller arrives via HTTP, a scheduler, or messaging. Configuration:

```java
@EnableMethodSecurity
```

enables method security infrastructure (with options appropriate for your version/config). A method annotated with:

```java
@PreAuthorize("hasAuthority('doc:read')")
public String readSecret() {
    return "classified";
}
```

must be invoked **through the bean proxy** for the authorization interceptor to evaluate the expression. If permissions are insufficient, an authorization exception is thrown before the target runs. In Section 4's test, `@WithMockUser` establishes a simulated `SecurityContext` without requiring an HTTP login flow.

### 8.2. What Exactly Does `@WithMockUser` Test?

`@WithMockUser(authorities = "doc:read")` sets up a test `Authentication` holding the exact authority `doc:read`. When the method is called via the proxy, `hasAuthority('doc:read')` evaluates against that context. With `doc:write`, the test proves access is denied.

Distinguish two common attributes:

- `@WithMockUser(roles = "ADMIN")` normally grants authority `ROLE_ADMIN`; matches `hasRole('ADMIN')` under the default prefix convention.
- `@WithMockUser(authorities = "doc:read")` grants the **exact specified authority string** without adding `ROLE_`; matches expressions using `hasAuthority('doc:read')`.

Do not confuse `roles = "doc:read"` with `authorities = "doc:read"`; that creates a different `SecurityContext` and fails tests even when the business method has no bug.

**Unauthorized tests** must call the proxy bean, for example:

```java
@WithMockUser(authorities = "doc:write")
@Test
void cannotReadWithoutAuthority() {
    assertThrows(AccessDeniedException.class,
            () -> documentService.readSecret());
}
```

This snippet resides in a test class with `documentService` and JUnit/Spring Security Test configured. Do not mock `DocumentService` and verify it was called: a mock does not carry Spring's security advice, and "mock was invoked" does not prove the authorization policy.

### 8.3. When Must You Test HTTP Security?

Method security tests **do not** verify the filter chain, sessions/CSRF, JWT decoders, URL matchers, `AuthenticationEntryPoint`, or how exceptions translate into HTTP 401/403. To protect REST contracts, add tests via `MockMvc`/`WebTestClient` or integration tests with the real security filter and configuration.

Conversely, an HTTP test checking only "anonymous receives 401" at the filter layer may not prove `@PreAuthorize` rules on the service. Each boundary answers a different question; test both if your system relies on both URL security and method security.

### 8.4. Testing Without Authentication

If a method has `@PreAuthorize` and no `Authentication` is present in `SecurityContext`, the call is typically denied and may throw a different exception type than **authenticated-but-unauthorized**, depending on Spring Security version and config. For stable tests, distinguish **unauthenticated** vs. **authenticated but unauthorized** cases per policy; do not write a single catch-all assertion for every failure and ignore HTTP status mapping.

If you want to test `@Secured` or JSR-250 annotations, check the corresponding enablement flags (e.g., `securedEnabled`, `jsr250Enabled` on `@EnableMethodSecurity`) and required dependencies/config. **`@PreAuthorize`** in the example works with the enabled configuration shown.

## 9. False Positives: Green Tests That Prove Nothing About Proxies

Several testing patterns commonly mislead evaluations:

**1. Instantiating with `new`:**

```java
DocumentService direct = new DocumentService();
String actual = direct.readSecret();
```

In a test, this Java code **calls the target directly and can return `"classified"` with no authority**—because annotations do not block calls on their own. This snippet illustrates **proxy bypass**, not a production pattern for code requiring method security.

**2. Mocking the annotated target with Mockito:** stubbing `when(annotatedService.someMethod()).thenReturn(...)` can replace the target completely; if the goal is proving transaction/cache/security proxies, mocking the target skips real advice.

**3. Asserting pure return values:** two calls to a `@Cacheable` method returning the same value do not prove caching, because a deterministic target returns the same value anyway. Count target executions or observe outbound calls.

**4. Testing `@Transactional` without a DB:** `verify(repository).save(...)` only proves a call was made, not commit or rollback. Use a real transaction manager and suitable test DB.

**5. Annotating the test with `@Transactional` and crediting service rollback:** data rolling back after the test may come from **Spring Test**, not the service's annotation. Invoke the service outside a test-managed transaction when verifying service commit/rollback.

**6. Annotation present without enablement:** a class with `@Cacheable` but no `@EnableCaching` or matching auto-configuration runs like an ordinary method. The same applies to method security and transaction managers. Functional tests catch missing enablement when the effect fails to appear.

**7. Self-invocation calls:** `this.saveTransactional()`/`this.cachedCall()` can bypass the proxy; tests must reproduce the actual external caller path if advice is expected there.

**8. Careless use of `final`:** `final` classes or methods can block class-based proxies; do not assume every proxy behaves identically. Design public bean entrypoints and choose a suitable proxy strategy.

**9. Unreset caches/DBs between tests:** a second test appears to get a cache hit or missing rows even when the logic is broken. Isolate data, caches, `SecurityContext`, and external resources per test.

**10. Mistaking `@WithMockUser` for real login testing:** it simulates an `Authentication` for method security boundaries, without testing passwords, JWTs, or sessions.

## 10. Organizing Real-World Tests by Verification Scope

Tests can be organized into three complementary layers:

1. **Business unit tests without Spring:** use constructor injection and test doubles to verify service decisions—fast, thorough edge cases.
2. **Small Spring TestContext for proxies:** use `@SpringJUnitConfig` with real advisors and beans to verify transactions, caching, and method security at method boundaries—as in this lesson.
3. **Integration/contract tests with production config:** use `@SpringBootTest` or appropriate slices with real DB/cache/security infrastructure depending on what needs protection—higher cost, proves wiring and adapters.

Avoid cramming every mechanism into one huge test. Section 4 put three groups into one file to highlight their shared proxy nature, whereas real projects can split them into `AuditTransactionTest`, `PriceCacheTest`, and `DocumentMethodSecurityTest` by responsibility. Each group can choose tailored fixtures and infrastructure: an accurate DB for transactions, an appropriate cache manager for caching, and proper security context/authorization for method security.

**A review plan before writing tests:**

| Question | Choice |
| --- | --- |
| Rules use only `if/else` and plain data? | JUnit test with `new` |
| Need to prove Spring actually created a proxy? | Inject bean from TestContext and check `AopUtils` when helpful |
| Need to prove rollback/commit? | Call proxy bean, use a real DB, and read state after the transaction |
| Need to prove cache hit skips target? | Configure `CacheManager`, call proxy repeatedly with same key, count target executions |
| Need to prove method authorization? | Enable method security, use `@WithMockUser`/`SecurityContext`, call proxy |
| Need to prove Redis/HTTP/production transaction manager? | Use integration/adapter tests with matching infrastructure/config |
| Tests slow and shared data causes flakiness? | Narrow the context, reset state/fixtures, isolate parallel runs |

## 11. Advanced Scenarios Where Quick Conclusions Fail

### 11.1. A Method with Both `@Transactional` and `@Cacheable`

When multiple advisors apply, interceptor ordering and the timing of cache updates/evictions relative to transaction commits can affect consistency. For example, if a DB operation fails after the cache was already evicted or updated, temporary inconsistency can occur. Do not assume every cache operation occurs **after commit** just because a method has `@Transactional`. Tests must state expectations for cache update timing, transaction synchronization policy, and real configuration.

### 11.2. New Transactions and Propagation

A `@Transactional(propagation = Propagation.REQUIRES_NEW)` method called **through a proxy** can suspend the outer transaction and start an independent one. If called via `this` inside the same class, the annotation may not be intercepted as expected. For payment/audit flows, DB tests must verify which records actually commit or roll back as required, not just verify the method was invoked.

### 11.3. Spring Tests and Preemptive Timeouts

JUnit's `assertTimeoutPreemptively(...)` can execute its callback on a **different thread**. Spring Test transactions are typically bound to a thread via `ThreadLocal`; callbacks on another thread **do not participate in the test-managed transaction**, leaving side effects unrolled-back contrary to expectations. In DB tests, avoid swapping `assertTimeout` for preemptive timeouts carelessly. If I/O timeouts must be enforced, use client/driver timeouts or controlled integration tests with explicit cleanup.

### 11.4. Multiple Transaction Managers / Cache Managers

In applications with multiple datasources or cache managers, an annotation may need to specify its target manager; using the wrong one lets the method run while the target system's state goes unmanaged. For instance, `@Transactional("ordersTransactionManager")` or `@Cacheable(cacheManager = "redisCacheManager", ...)` works only when that bean is registered. Tests must verify the **selected infrastructure**, not just the annotation syntax.

### 11.5. Mocking Can Erase the Behavior Under Test

When replacing beans with Mockito in Spring tests (annotation names vary across Spring Boot/Spring Framework versions), mocking **the annotated bean itself** removes or alters the production proxy/advisor path you wanted to verify. To test a proxy, keep the real target bean and mock only **out-of-scope dependencies** (such as a downstream HTTP client) if needed.

### 11.6. TestContext Caching Does Not Mean Resource Isolation

Spring Test's cache retains the `ApplicationContext` to save bootstrap time; it does not promise to reset cache contents, databases, mutable singleton fields, or external state. Use fixtures with clear setup/cleanup, leverage test transactions only where appropriate, and minimize shared mutable state under parallel execution. `@DirtiesContext` can force a fresh context, but slows tests down; do not use it as a default fix for dirty data when state can be cleaned at the proper boundary.

## 12. QA Checklist for Proxies in Spring TestContext

Before writing the test:

- **SUT:** are we verifying pure logic or Spring AOP mechanics? If testing a proxy, does the test get the bean from a Spring context?
- **Enablement:** has the context enabled transaction management, caching, and method security within the right scope?
- **Proxy shape:** can the called bean/method actually be intercepted (entrypoint, visibility, `final`, interfaces, proxy strategy)?
- **Self-invocation:** are there `this.method()` calls that bypass advice?
- **Evidence:** for transactions, committed/rolled-back data; for caching, hits/misses and target execution count; for security, access granted/denied.
- **Fixtures:** does the test isolate DB/cache/`SecurityContext` and avoid test-order dependency?
- **Scope:** minimal context or full Boot context? With multiple managers, does the test use production's matching beans/config?
- **Boundary:** does the test prove only an in-memory proxy or also production Redis/HTTP/JPA/DB behavior?

After the test turns green:

- Are we sure it didn't pass just because of a mocked target or leftover cache entry from an earlier run?
- Were transactions verified after the service call outside a test-managed transaction?
- Did unauthorized outcomes come from the method interceptor rather than an unrelated HTTP filter?
- Is any external data left behind after the test, especially with preemptive timeouts or `REQUIRES_NEW` propagation?
- If proxy mode changes during refactoring, does the test still verify the contract rather than locking onto AOP implementation details?

**Remember:** `@Transactional`, `@Cacheable`, and `@PreAuthorize` take effect when calls go through **Spring-managed bean proxies**. Therefore, tests for transactions, caching, and method security must use **an appropriate Spring TestContext, real beans, and assertions on advice effects**. Plain `new Service(...)` unit tests remain very valuable for business logic, but they are not proof of proxies.
