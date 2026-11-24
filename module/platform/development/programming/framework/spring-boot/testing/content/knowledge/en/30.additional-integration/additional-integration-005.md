# Testing the Impact of Self-Invocation on Transactions, Caching, and Validation

## 1. The problem: annotations are present, yet runtime behavior defies expectations

In a Spring Boot application, you may encounter three puzzling symptoms:

- A method annotated with `@Transactional` throws a `RuntimeException`, yet an earlier INSERT **still commits**.
- A method annotated with `@Cacheable` is called repeatedly, and the expensive computation still runs every time.
- A method annotated with `@Validated` and `@NotBlank` receives an empty string **without throwing an error**, whereas calling the same method from another Spring bean throws `ConstraintViolationException`.

A primary cause is **self-invocation**: one method of the target bean invokes another method **on the same instance** via `this.method()` or an unqualified call. When an application uses Spring AOP in its default **proxy mode**, interceptors only get a chance to run for calls **passing through the proxy**. Direct calls inside the target bypass the interceptor.

Example:

~~~java
@Service
public class OrderService {

    public void placeOrder() {
        this.saveAudit();  // Self-invocation: does not go through Spring proxy
    }

    @Transactional
    public void saveAudit() {
        // JDBC write here is not automatically wrapped in a transaction
        // merely because of the annotation when called via this.saveAudit().
    }
}
~~~

Reading the source, many developers assume `@Transactional` always takes effect. In reality, the annotation is **metadata** for transaction advice to run **where the proxy intercepts the call**. It does not rewrite internal Java calls within the class.

This lesson belongs to the **Additional integration** group of Spring Boot Testing. Its focus is writing **tests that distinguish** direct calls, self-invocation, and calls through a bean proxy, while proving the concrete impact on **transactions, caching, and method validation**.

### Learning objectives

After completing this lesson, you will be able to:

1. Explain Spring AOP proxies, target objects, advice, and self-invocation accurately.
2. Identify which calls traverse the proxy and which bypass it.
3. Verify against a real database whether `@Transactional` rolls back when invoked externally vs. via `this.method()`.
4. Verify that `Propagation.REQUIRES_NEW` is ignored on self-invocation even when the outer method **already has an active transaction**.
5. Verify `@Cacheable` hits/misses via counters and `CacheManager`, rather than inferring from identical return values.
6. Test service method validation via `@Validated` and Jakarta Bean Validation constraints on parameters **and return values**.
7. Compare extracting a separate Spring bean against `TransactionTemplate`, programmatic `CacheManager`/validation, self-injection, and AspectJ weaving.
8. Avoid false positives caused by `@Transactional` on the test method itself or by `@Mock` lacking a real proxy.
9. Understand the boundaries of `@WebMvcTest` and Spring MVC 6.1+ built-in validation compared to proxy-based service method validation.
10. Run the sample **Java 17 / Spring Boot 3.5.16 / Maven / JDBC / H2 / Cache / Hibernate Validator / JUnit 5** project with tests verifying real outcomes.
11. Avoid overly broad conclusions: a direct call can **still execute inside an already-open outer transaction**, while **the inner method's own annotation metadata is ignored**.
12. Choose the right test scope: unit business logic, proxy integration tests, database transactions, and web security/validation contracts.

## 2. How do Spring AOP proxies actually work?

### 2.1. Target and proxy

When a bean carries advice from `@Transactional`, `@Cacheable`, or `@Validated`, Spring supplies a proxy to other beans and callers:

~~~text
Controller / Service B / JUnit @Autowired
                 |
                 v
        Spring-managed proxy
          |   |   |
          |   |   +-- validation advice
          |   +------ cache advice
          +---------- transaction advice
                 |
                 v
            Target object
                 |
                 +-- this.innerMethod() ----> Target object directly
                                                  |
                                                  +-- advice does not run again
~~~

In proxy mode:
- A caller invokes `springBean.innerMethod()` → the proxy intercepts the method.
- The target executes `outerMethod()` and calls `this.innerMethod()` → the call **does not route back through the proxy**.
- Calling `innerMethod()` without `this` is still self-invocation.
- Moving the method to **another Spring bean** and injecting that bean makes the call go through the callee's proxy.

Standard Spring AOP can use a **JDK dynamic proxy** (via interfaces) or a **CGLIB class-based proxy**. Both share the self-invocation limitation in Spring AOP proxy mode; switching from JDK proxies to CGLIB **does not fix** self-invocation.

### 2.2. Call graph illustration

~~~text
Client -> proxy(A) -> target(A).outer()
                          |
                          +-- this.inner() -> target(A).inner() [bypass]

Client -> proxy(B).delegate()
                    |
                    +-- proxy(A).inner() -> advice -> target(A).inner()
~~~

It is **not** that "Spring skips all logic." The inner Java method **still executes**; only cross-cutting interceptors (transaction/caching/validation) fail to run.

### 2.3. Calling a method from a constructor or `@PostConstruct`

Even when a bean will be proxied after initialization, calling an annotation-protected method from the target's constructor or `@PostConstruct` should not rely on the proxy. During initialization, the proxy may not be ready or the call is local. For startup work needing transactions or caching, extract initialization orchestration into a separate bean with an appropriate lifecycle, use `ApplicationRunner`/`ApplicationReadyEvent` or a controlled post-start mechanism, and still go through the proxy.

### 2.4. Not every annotation relies on proxies

Some annotations operate via other mechanisms (MVC argument binding/validation, Spring configuration class enhancement, ORM/JPA mapping, compile-time processing, AspectJ weaving). This lesson covers **Spring AOP proxy-based interception**. Do not memorize a blanket rule like "all self-invoked annotations fail" and apply it indiscriminately.

## 3. Self-invocation and `@Transactional`

### 3.1. Common mistake: inner method opens a transaction

~~~java
@Service
class BillingService {

    private final JdbcTemplate jdbc;

    BillingService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void bill() {
        createReceipt();   // self-calls target method
    }

    @Transactional
    public void createReceipt() {
        jdbc.update("insert into receipts (id) values (?)", 42);
        throw new IllegalStateException("failed");
    }
}
~~~

This is an architectural snippet, lacking a full runnable class and schema. When `bill()` is **non-transactional** and self-calls `createReceipt()`, the transaction advice on `createReceipt()` does not run. With JDBC auto-commit enabled, the `INSERT` has already committed when the exception is thrown. When an external caller invokes `billingService.createReceipt()` through the proxy, a transaction is opened and an unchecked exception normally triggers rollback.

**Warning:** Spring Data repository methods often carry `@Transactional` themselves. If an example calls `repository.save(...)` and concludes from a rollback that self-invocation had a transaction, you might be observing the **repository's transaction**, not the service's. The lab uses `JdbcTemplate` directly with auto-commit so boundaries stay clear.

### 3.2. Checking for an active transaction

Spring provides:

~~~java
boolean active =
        TransactionSynchronizationManager
                .isActualTransactionActive();
~~~

This snippet requires importing `org.springframework.transaction.support.TransactionSynchronizationManager`. Returning `true` means the current thread has an active Spring-managed transaction resource; it is not enough to prove exact **propagation**, **isolation**, or rollback semantics. To truly test transactions, you still need an intentional failure plus a database readback after completion.

### 3.3. Outer is already `@Transactional`: an important nuance

~~~java
@Transactional
public void outer() {
    this.innerRequiresNew();
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void innerRequiresNew() {
    // ...
}
~~~

If `outer()` is invoked by a caller through the proxy, the outer transaction **does exist**. However, `this.innerRequiresNew()` bypasses the proxy, so `REQUIRES_NEW` on the inner method **has no separate effect**. The inner code **still executes inside the active outer transaction** (on the same thread) instead of starting a new transaction. Consequently:
- If inner throws an exception and outer **catches** it, outer may still commit inner's writes too.
- If inner is invoked through **another bean's proxy**, `REQUIRES_NEW` opens an independent transaction; an unchecked exception rolls back the inner transaction, and outer can catch it and commit its own work.
- Do not overgeneralize that "self-invocation never has a transaction." Precisely stated, **the advice on the self-invoked method is not applied**, while any enclosing transaction from the caller remains active.

This is a critical scenario to test explicitly rather than checking `isActualTransactionActive()` alone.

### 3.4. `@Transactional` attributes that can be ignored

Under self-invocation, configuration placed solely on the inner method may not be enforced:
- `propagation = REQUIRES_NEW`, `MANDATORY`, `NEVER`.
- `isolation = SERIALIZABLE`.
- `timeout = ...`.
- `readOnly = true`.
- `rollbackFor = ...`.
- Qualifier specifying a particular transaction manager.

Never assume a setting applies unless the call traverses the proxy. Test with a real database and actual transaction outcomes, not just reflection inspecting annotations.

### 3.5. Rollback rules still matter

When transaction advice **does run**, Spring by default rolls back on `RuntimeException` and `Error`. Checked exceptions may commit unless `rollbackFor` or a custom policy specifies otherwise. Catching an exception inside the method without marking rollback-only can also let the transaction commit. These are **distinct from** self-invocation, though they often produce the same "did not roll back" symptom.

## 4. Self-invocation and `@Cacheable`

### 4.1. The cache interceptor also lives on the proxy

~~~java
@Service
class PriceService {

    @Cacheable(cacheNames = "quotes", key = "#p0")
    public int quote(int productId) {
        return expensiveLookup(productId);
    }

    public int quoteTwice(int productId) {
        return quote(productId) + quote(productId);
    }
}
~~~

Calling `priceService.quote(7)` through the proxy twice with the same cache key lets the second call return from cache. But `priceService.quoteTwice(7)` enters the target and calls `this.quote(7)` twice: both bypass cache advice, so `expensiveLookup` runs twice.

Both paths can return the **same value**. Hence asserting only the result is insufficient. You must check:
- Actual computation / DB query / external call counts.
- Whether a cache entry was populated.
- Results when the cache is cleared or evicted.
- Annotation key values and `condition`/`unless` behavior.

### 4.2. `@CachePut` and `@CacheEvict` are affected too

Spring Cache annotations are applied via the caching interceptor:
- `@Cacheable`: checks cache and may skip method body.
- `@CachePut`: runs method and updates cache.
- `@CacheEvict`: deletes cache entry by key or `allEntries`.
- `@Caching`: combines multiple operations.

If a method calls `this.evict(...)` or `this.refresh(...)`, that call bypasses cache advice. The consequence can be **worse than missing a cache hit**: stale data fails to be evicted, or the cache stays outdated after business state changes.

### 4.3. Cache keys must be well-defined

~~~java
@Cacheable(cacheNames = "numbers", key = "#p0")
public int compute(int number) {
    return number * 10;
}
~~~

`#p0` references the first parameter without relying on parameter name metadata for `number`. For user- or tenant-specific keys, the method signature or key expression must include all discriminating dimensions. A cache hit returning the wrong tenant's data is not a success.

### 4.4. TTL, eviction, and test isolation

Tests using `ConcurrentMapCacheManager` have no default TTL. With real Caffeine, Redis, or Ehcache, test provider-specific expiration, serialization, and eviction. Cache tests should ideally use an isolated cache manager or clear caches before each test method to prevent earlier tests from causing false passes.

### 4.5. Caching inside a transaction

When a method combines `@Transactional` and `@Cacheable`, advice ordering and cache transaction-awareness affect when puts/evicts occur. Do not assume every cache write rolls back automatically with a DB transaction: in-memory or Redis caches are not transactional JDBC resources by default. This lab **separates cached methods from transactional methods** to isolate self-invocation per concern; production code needs additional tests for post-rollback consistency, update/eviction ordering, and advice precedence.

## 5. Self-invocation and method validation

### 5.1. Conditions for service method validation to work

In Spring Boot 3.5:
- A Bean Validation provider is present (usually via `spring-boot-starter-validation`).
- The service class is Spring-managed.
- The class is annotated with `@Validated` at type level.
- Methods have Jakarta constraints on arguments or return values such as `@NotBlank`, `@NotNull`, `@Positive`, or cascaded validation as configured.
- The call passes through the method validation proxy infrastructure (typically `MethodValidationPostProcessor`).

Example:

~~~java
@Service
@Validated
public class ProductService {

    public String placeFromBatch(String code) {
        return this.place(code); // bypass validation advice
    }

    public String place(@NotBlank String code) {
        return code.strip();
    }
}
~~~

In proxy mode, `productService.place(" ")` from an external caller is rejected with Jakarta's `ConstraintViolationException`. But `productService.placeFromBatch(" ")` self-calls `place`, so validation interception for `place` **never runs**. The body executes and returns an empty string. This is a contract bug easily missed if tests only exercise the public facade superficially.

### 5.2. Parameter validation and return-value validation

Method validation can enforce:
- **Parameters**: `create(@NotBlank String code)`.
- **Return values**: `@NotBlank String create(...)` must not return blank.
- Constraint groups via `@Validated(SomeGroup.class)`.
- Cascaded object validation with `@Valid` where appropriate.

When self-invocation bypasses the interceptor, both parameter and return-value validation on the internal method are skipped. The lab tests **both**.

### 5.3. `@Valid` does not replace a `@Validated` proxy

`@Valid` marks cascaded validation when a validator runs; it **does not create an AOP proxy** to check self-calls. Type-level `@Validated` together with a Bean Validation provider enables Spring to register the method-validation proxy. Define clear validation boundaries rather than treating annotations as compiler-enforced guarantees.

### 5.4. Spring MVC controller validation does not work identically

Spring MVC 6.1+ includes **built-in method validation for controller handler methods** in the web pipeline, which in many cases needs no AOP `@Validated` proxy on controllers and even recommends omitting class-level `@Validated` to use built-in MVC method validation. Therefore:
- Do not equate service self-invocation failures with DispatcherServlet `@RequestBody`/`@RequestParam` validation failures.
- Controllers are invoked by MVC through handler adapters with dedicated exception handling.
- When testing **services** using `@Validated` AOP, invoke the bean through its proxy.
- For controller HTTP contracts, test via `MockMvc`/filters/real handler dispatch rather than calling the controller as a POJO.

### 5.5. Exceptions depend on configuration

By default, `MethodValidationPostProcessor` throws `jakarta.validation.ConstraintViolationException`. When configured to adapt violations, Spring throws `MethodValidationException`. MVC built-in validation has its own HTTP-oriented exceptions (e.g., `HandlerMethodValidationException`). Tests should match the **actual layer and configuration**, not hardcode an exception type from another layer.

## 6. Call matrix

| Call path | Inner transaction annotation | Inner `@Cacheable` | Inner `@Validated` constraint |
| --- | --- | --- | --- |
| `bean.inner()` from external caller via proxy | Can run | Can run | Can run |
| `this.inner()` within same target | **Bypasses new advice** | **Bypasses cache advice** | **Bypasses validation advice** |
| Unqualified `inner()` within target | Same as self-call | Same | Same |
| `otherBean.inner()` (`otherBean` is a Spring proxy) | Yes | Yes | Yes |
| `new Service().inner()` | No Spring proxy | No Spring cache proxy | No Spring method validation proxy |
| `@PostConstruct` self-calling `inner` | Do not rely on proxy | Do not rely on proxy | Do not rely on proxy |
| Outer method already in transaction self-calls `inner` | Inner joins **existing outer transaction**; inner metadata ignored | Inner cache advice skipped | Inner validation advice skipped |
| Properly configured AspectJ weaving | Can intercept self-call | Can intercept self-call | **Does not apply by default to Spring method-validation advisor** |

For validation, do not assume enabling AspectJ for transactions/caching automatically makes method validation intercept local calls; that is a separate infrastructure concern requiring dedicated advisor/weaving integration tests.

## 7. Runnable project: Spring Boot 3.5.16 + JDBC/H2 + Cache + Validation

### 7.1. Technical scenario

A Spring service `BoundaryService` provides:
1. `@Transactional insertThenFail`: inserts an audit row then throws an unchecked exception.
2. `selfInsertThenFail`: calls `this.insertThenFail`, **bypassing the transaction interceptor**.
3. `@Transactional isTransactionActive` and `selfTransactionActive`: observes transaction boundaries.
4. `@Cacheable compute`: increments an `AtomicInteger` on each real computation.
5. `selfComputeTwice`: calls `compute` twice via `this`, bypassing the cache.
6. `normalize(@NotBlank String)`: validated parameter.
7. `@NotBlank invalidReturn`: validated return value.
8. `selfNormalize` / `selfInvalidReturn`: two self-calls bypassing validation.
9. `@Transactional outerSelfRequiresNew` calling `this.innerRequiresNewAndFail` and catching the exception, proving `REQUIRES_NEW` is ignored.

A `CrossBeanFacade` calls `BoundaryService` via dependency injection to **restore proxy interception**. A `RequiresNewWorker` demonstrates a real inner transaction when invoked from another bean. The JUnit integration test reads H2 **after the call** to prove commit/rollback rather than relying on mocks.

### 7.2. File layout

~~~text
self-invocation-lab/
├── pom.xml
├── src/main/resources/
│   ├── application.properties
│   └── schema.sql
├── src/main/java/com/example/selfinvoke/
│   ├── SelfInvocationApplication.java
│   ├── BoundaryService.java
│   ├── RequiresNewWorker.java
│   └── CrossBeanFacade.java
└── src/test/java/com/example/selfinvoke/
    └── SelfInvocationIntegrationTest.java
~~~

**Prerequisites:** JDK 17+, Maven 3.6.3+, network or Maven cache to download dependencies. No Docker needed since the lab uses H2; to test PostgreSQL locking/transaction semantics, create a dedicated Testcontainers test.

**Self-contained:** This is a complete Maven project; snippets in other sections are explicitly marked as illustrative and should not be added unless requested.

### 7.3. pom.xml

~~~xml
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
  <artifactId>self-invocation-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-cache</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-aop</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
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
~~~

Dependency breakdown:
- `starter-jdbc`: `JdbcTemplate`, HikariCP, DataSource transaction manager.
- H2: embedded relational database; allows observing auto-commit outside Spring transactions and rollbacks when advice takes effect.
- `starter-cache` + `@EnableCaching`: caching infrastructure.
- `starter-aop`: Spring AOP/AspectJ weaver runtime support for proxies.
- `starter-validation`: Hibernate Validator/Jakarta Validation and Boot's method validation post-processor.
- `starter-test`: JUnit 5, AssertJ, Spring Test.
- Spring Boot BOM coordinates compatible versions; avoid mixing different framework major versions.

### 7.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=self-invocation-lab

spring.datasource.url=jdbc:h2:mem:self_invocation_lab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.auto-commit=true

spring.sql.init.mode=always
spring.cache.type=simple
spring.aop.proxy-target-class=true
~~~

**Role:** Hikari `auto-commit=true` ensures JDBC statements **outside any Spring transaction** commit immediately, letting the self-invocation test observe a persisted row after a `RuntimeException`. When the transaction interceptor runs, Spring's transaction manager controls commit/rollback; Hikari's pool auto-commit does not break a thread-bound transaction.

`spring.aop.proxy-target-class=true` requests class-based proxies when the framework creates proxies. Choosing CGLIB **does not make self-invocation intercepted**. Keep this setting for sample consistency, but never treat it as a "fix."

`spring.cache.type=simple` selects basic in-memory caching. In the main class, we also explicitly define `ConcurrentMapCacheManager` so behavior is straightforward to measure. No Redis or external cache dependency is included in the lab.

### 7.5. schema.sql

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE IF NOT EXISTS audit_rows (
    id INTEGER PRIMARY KEY,
    description VARCHAR(100) NOT NULL
);
~~~

A minimal schema sufficient for observing transactions. `id` is the primary key, and each test uses distinct IDs; `@BeforeEach` cleans up the DB before every test method. `IF NOT EXISTS` is supported by H2 in the lab; for production DB migrations, use Flyway or Liquibase with DB-specific schemas rather than copying this file.

### 7.6. SelfInvocationApplication.java

`src/main/java/com/example/selfinvoke/SelfInvocationApplication.java`:

~~~java
package com.example.selfinvoke;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableCaching
@EnableTransactionManagement
public class SelfInvocationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                SelfInvocationApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("numbers");
    }
}
~~~

`@EnableTransactionManagement` makes the transaction advisor explicit in the sample. With Spring Boot JDBC/DataSource, much of transaction auto-configuration is automatic, yet this annotation makes clear to learners what enables `@Transactional` metadata processing. `@EnableCaching` activates caching annotations.

Defining an explicit `CacheManager` bean ensures the `"numbers"` cache exists and can be cleared in tests. `ConcurrentMapCacheManager` fits small tests and is **not** a production distributed cache.

### 7.7. BoundaryService.java

`src/main/java/com/example/selfinvoke/BoundaryService.java`:

~~~java
package com.example.selfinvoke;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.validation.constraints.NotBlank;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class BoundaryService {

    private final JdbcTemplate jdbc;
    private final AtomicInteger calculations =
            new AtomicInteger();

    public BoundaryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // ------------------------------------------------
    // Transaction: direct proxy call vs self-invocation
    // ------------------------------------------------

    @Transactional
    public void insertThenFail(int id) {
        jdbc.update(
                "INSERT INTO audit_rows(id, description) "
                        + "VALUES (?, ?)",
                id, "inserted before exception");
        throw new IllegalStateException(
                "injected failure after INSERT");
    }

    public void selfInsertThenFail(int id) {
        // Same target: DOES NOT go through inner's transaction advice.
        this.insertThenFail(id);
    }

    @Transactional
    public boolean isTransactionActive() {
        return TransactionSynchronizationManager
                .isActualTransactionActive();
    }

    public boolean selfTransactionActive() {
        return this.isTransactionActive();
    }

    // -----------------------------------------------
    // Caching: number of times method body is actually called
    // -----------------------------------------------

    @Cacheable(cacheNames = "numbers", key = "#p0")
    public int compute(int n) {
        calculations.incrementAndGet();
        return n * 10;
    }

    public List<Integer> selfComputeTwice(int n) {
        return List.of(
                this.compute(n),
                this.compute(n));
    }

    public int computationCount() {
        return calculations.get();
    }

    public void resetComputationCounter() {
        calculations.set(0);
    }

    // -----------------------------------------------
    // Method validation: parameter and return value
    // -----------------------------------------------

    public String normalize(@NotBlank String input) {
        return input.strip();
    }

    public String selfNormalize(String input) {
        return this.normalize(input);
    }

    @NotBlank
    public String invalidReturn() {
        return " ";
    }

    public String selfInvalidReturn() {
        return this.invalidReturn();
    }

    // -------------------------------------------------
    // Inner REQUIRES_NEW is bypassed on self-invocation
    // -------------------------------------------------

    @Transactional
    public void outerWithSelfRequiresNew(
            int outerId, int innerId) {

        try {
            // Does not go through proxy: REQUIRES_NEW is bypassed.
            this.innerRequiresNewAndFail(innerId);
        }
        catch (IllegalStateException expected) {
            // Caught in outer: outer can commit.
        }

        jdbc.update(
                "INSERT INTO audit_rows(id, description) "
                        + "VALUES (?, ?)",
                outerId, "outer committed");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void innerRequiresNewAndFail(int innerId) {
        jdbc.update(
                "INSERT INTO audit_rows(id, description) "
                        + "VALUES (?, ?)",
                innerId, "inner may rollback");

        throw new IllegalStateException(
                "inner transaction failure");
    }
}
~~~

**What to observe:**

- `insertThenFail` inserts a row and throws. Called externally through the proxy → transaction rolls back; called via `selfInsertThenFail` → no inner transaction, JDBC auto-commits, so the row stays.
- `isTransactionActive` via proxy → `true`; via `selfTransactionActive` → `false`, because the wrapper method is unannotated.
- `compute` increments the counter only when the body executes. Two calls via proxy with the same key → count 1; via `selfComputeTwice` → count 2.
- `normalize` rejects blank strings when the validation interceptor runs. Via `selfNormalize("   ")`, the constraint is skipped and the body returns an empty string.
- `invalidReturn` has a return-value constraint. Via proxy it rejects the blank result; via `selfInvalidReturn` it returns blank without error.
- `outerWithSelfRequiresNew` **is called via the proxy**, so an outer transaction exists. However, self-calling inner fails to start `REQUIRES_NEW`. Outer catches the exception from inner, so both inner and outer `INSERT`s commit together. This tests propagation impact directly instead of relying on a boolean active-transaction flag.

### 7.8. RequiresNewWorker.java

`src/main/java/com/example/selfinvoke/RequiresNewWorker.java`:

~~~java
package com.example.selfinvoke;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RequiresNewWorker {

    private final JdbcTemplate jdbc;

    public RequiresNewWorker(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void insertThenFail(int innerId) {
        jdbc.update(
                "INSERT INTO audit_rows(id, description) "
                        + "VALUES (?, ?)",
                innerId, "independent inner");
        throw new IllegalStateException(
                "new transaction failed");
    }
}
~~~

`RequiresNewWorker` is a **separate bean**, so a Spring-managed caller injected via constructor invokes `insertThenFail` through its proxy. `REQUIRES_NEW` suspends the outer transaction and opens an independent one. Throwing an unchecked exception rolls back inner while outer can catch it and proceed.

Inserting the outer row **after** inner avoids H2 locking contention between the outer and inner transactions in the sample. That is a deterministic choice for the lab, not a general deadlock-avoidance rule.

### 7.9. CrossBeanFacade.java

`src/main/java/com/example/selfinvoke/CrossBeanFacade.java`:

~~~java
package com.example.selfinvoke;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CrossBeanFacade {

    private final BoundaryService boundary;
    private final RequiresNewWorker requiresNewWorker;
    private final JdbcTemplate jdbc;

    public CrossBeanFacade(
            BoundaryService boundary,
            RequiresNewWorker requiresNewWorker,
            JdbcTemplate jdbc) {
        this.boundary = boundary;
        this.requiresNewWorker = requiresNewWorker;
        this.jdbc = jdbc;
    }

    public void callTransactionalInner(int id) {
        // boundary is a Spring proxy, not this.
        boundary.insertThenFail(id);
    }

    public List<Integer> computeTwiceThroughProxy(int n) {
        return List.of(
                boundary.compute(n),
                boundary.compute(n));
    }

    public String normalizeThroughProxy(String value) {
        return boundary.normalize(value);
    }

    public String invalidReturnThroughProxy() {
        return boundary.invalidReturn();
    }

    @Transactional
    public void outerWithDelegatedRequiresNew(
            int outerId, int innerId) {
        try {
            // Call through another bean -> REQUIRES_NEW takes effect.
            requiresNewWorker.insertThenFail(innerId);
        }
        catch (IllegalStateException expected) {
            // Inner rolls back; outer can still commit.
        }

        jdbc.update(
                "INSERT INTO audit_rows(id, description) "
                        + "VALUES (?, ?)",
                outerId, "outer committed");
    }
}
~~~

Comparison:
- `BoundaryService.selfInsertThenFail`: self-call without transaction advice.
- `CrossBeanFacade.callTransactionalInner`: cross-bean call with transaction advice.
- `BoundaryService.outerWithSelfRequiresNew`: inner `REQUIRES_NEW` bypassed.
- `CrossBeanFacade.outerWithDelegatedRequiresNew`: inner rolls back in its own transaction.
- `computeTwiceThroughProxy`: cache is used because `boundary.compute` traverses the proxy.
- `normalizeThroughProxy`: Jakarta method validation is intercepted.

### 7.10. SelfInvocationIntegrationTest.java

`src/test/java/com/example/selfinvoke/SelfInvocationIntegrationTest.java`:

~~~java
package com.example.selfinvoke;

import java.util.List;
import java.util.Objects;

import jakarta.validation.ConstraintViolationException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class SelfInvocationIntegrationTest {

    @Autowired
    BoundaryService boundary;

    @Autowired
    CrossBeanFacade facade;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    CacheManager cacheManager;

    @BeforeEach
    void resetState() {
        // Non-@Transactional test: cleanup commits for real.
        jdbc.update("DELETE FROM audit_rows");
        Objects.requireNonNull(
                cacheManager.getCache("numbers")).clear();
        boundary.resetComputationCounter();
    }

    private int rows(int id) {
        Integer result = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_rows WHERE id = ?",
                Integer.class, id);
        return Objects.requireNonNull(result);
    }

    @Test
    void beanIsProxiedButItsOwnThisCallsStillBypassAdvice() {
        assertThat(AopUtils.isAopProxy(boundary)).isTrue();

        // External method invocation through proxy:
        assertThat(boundary.isTransactionActive()).isTrue();

        // Local target call does not go through transaction advice:
        assertThat(boundary.selfTransactionActive()).isFalse();
    }

    @Test
    void directProxyCallRollsBackInsertAfterRuntimeException() {
        assertThatThrownBy(() ->
                boundary.insertThenFail(101))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("injected failure");

        // Check after the proxy has completed rollback.
        assertThat(rows(101)).isZero();
    }

    @Test
    void selfInvocationBypassesTransactionAndLeavesAutocommitRow() {
        assertThatThrownBy(() ->
                boundary.selfInsertThenFail(102))
                .isInstanceOf(IllegalStateException.class);

        // No inner transaction interceptor.
        // JDBC statement auto-commits per the lab's H2/Hikari config.
        assertThat(rows(102)).isEqualTo(1);
    }

    @Test
    void separateSpringBeanRestoresTransactionRollback() {
        assertThatThrownBy(() ->
                facade.callTransactionalInner(103))
                .isInstanceOf(IllegalStateException.class);

        assertThat(rows(103)).isZero();
    }

    @Test
    void selfInvokedRequiresNewIsNotASeparateTransaction() {
        boundary.outerWithSelfRequiresNew(201, 202);

        // Inner exception is caught by outer.
        // Both writes belong to the outer transaction and commit.
        assertThat(rows(201)).isEqualTo(1);
        assertThat(rows(202)).isEqualTo(1);
    }

    @Test
    void crossBeanRequiresNewRollsBackOnlyInnerTransaction() {
        facade.outerWithDelegatedRequiresNew(203, 204);

        // Inner transaction rolls back, outer transaction commits.
        assertThat(rows(203)).isEqualTo(1);
        assertThat(rows(204)).isZero();
    }

    @Test
    void externalCacheCallRunsExpensiveBodyOnce() {
        assertThat(boundary.compute(7)).isEqualTo(70);
        assertThat(boundary.compute(7)).isEqualTo(70);

        assertThat(boundary.computationCount()).isEqualTo(1);

        Cache cache = Objects.requireNonNull(
                cacheManager.getCache("numbers"));
        assertThat(cache.get(7)).isNotNull();
    }

    @Test
    void selfInvocationBypassesCacheAdviceTwice() {
        List<Integer> result = boundary.selfComputeTwice(8);

        assertThat(result).containsExactly(80, 80);
        assertThat(boundary.computationCount()).isEqualTo(2);

        Cache cache = Objects.requireNonNull(
                cacheManager.getCache("numbers"));
        assertThat(cache.get(8)).isNull();
    }

    @Test
    void crossBeanCacheCallUsesOneCachedResult() {
        List<Integer> result =
                facade.computeTwiceThroughProxy(9);

        assertThat(result).containsExactly(90, 90);
        assertThat(boundary.computationCount()).isEqualTo(1);

        Cache cache = Objects.requireNonNull(
                cacheManager.getCache("numbers"));
        assertThat(cache.get(9)).isNotNull();
    }

    @Test
    void externalMethodValidationRejectsBlankParameter() {
        assertThatThrownBy(() ->
                boundary.normalize("   "))
                .isInstanceOf(
                        ConstraintViolationException.class);

        assertThat(boundary.normalize("  valid  "))
                .isEqualTo("valid");
    }

    @Test
    void selfInvocationBypassesParameterValidation() {
        assertThat(boundary.selfNormalize("   "))
                .isEqualTo("");
    }

    @Test
    void externalReturnValueValidationRejectsBlankResult() {
        assertThatThrownBy(() ->
                boundary.invalidReturn())
                .isInstanceOf(
                        ConstraintViolationException.class);
    }

    @Test
    void selfInvocationBypassesReturnValueValidation() {
        assertThat(boundary.selfInvalidReturn())
                .isBlank();
    }

    @Test
    void delegatedValidationThroughAnotherBeanIsIntercepted() {
        assertThatThrownBy(() ->
                facade.normalizeThroughProxy(" "))
                .isInstanceOf(
                        ConstraintViolationException.class);

        assertThatThrownBy(
                facade::invalidReturnThroughProxy)
                .isInstanceOf(
                        ConstraintViolationException.class);
    }
}
~~~

### 7.11. Explanation of each assertion group

**Transaction group (6 tests):**
- A bean having an AOP proxy does not mean self-calls are intercepted.
- External `insertThenFail` rolls back; H2 has no row 101.
- Self `insertThenFail` bypasses; H2 keeps row 102 via auto-commit.
- Cross-bean delegation through proxy rolls back; no row 103.
- Self-call to inner `REQUIRES_NEW` **opens no new transaction**; catching the exception lets outer commit rows 201 and 202.
- Delegating to `RequiresNewWorker` opens a separate transaction; inner row 204 rolls back while outer row 203 commits.

**Cache group (3 tests):**
- External `compute(7)` twice → computation count 1 and cache entry exists.
- Self `compute(8)` twice → computation count 2 and **no cache entry is created**.
- Cross-bean two calls `compute(9)` → count 1 and cache entry exists.

**Validation group (5 tests):**
- External blank parameter throws `ConstraintViolationException`; valid parameter is trimmed.
- Self blank parameter slips through and returns empty string.
- External invalid return value triggers constraint error.
- Self invalid return value slips through.
- Cross-bean delegation blocks both invalid parameters and invalid return values.

Total: **14 JUnit test methods**. The test class deliberately **omits `@Transactional`** so service transactions actually open, commit, and roll back. Adding `@Transactional` at the JUnit class/method level creates a default test-managed transaction that alters outcomes and masks failure modes, especially with `REQUIRED` propagation.

### 7.12. Running Maven and checking results

From the `self-invocation-lab` directory:

~~~bash
mvn -q clean test

mvn -q -Dtest=SelfInvocationIntegrationTest test
~~~

Expected outcome by design:
- Maven downloads dependencies and runs **14 tests**.
- `Tests run: 14, Failures: 0, Errors: 0` with compatible environment/configuration.
- Transaction tests distinguish row counts 0 vs. 1 as expected.
- Cache tests observe counters 1 vs. 2.
- Validation tests observe `ConstraintViolationException` on external/proxied calls.
- Surefire reports appear under `target/surefire-reports`.
- Maven exit code 0 on success; log formatting and elapsed times vary by environment.

**QA note:** This sample project was designed and reviewed for syntax and APIs, **without executing Maven** while authoring this knowledge article. Never claim tests actually PASSED until they are run. Project CI should execute the commands and verify the Surefire summary.

### 7.13. Should you run the app with `spring-boot:run`?

~~~bash
mvn spring-boot:run
~~~

The app can boot with H2 and the cache manager, but it exposes no REST controllers or CLI menu. The goal is JUnit integration tests, not an HTTP API. If you want to test interactively, create a controlled `ApplicationRunner` or REST endpoint invoking the proxy bean rather than instantiating the target class with `new`.

## 8. What does each test prove? Avoiding over-broad claims

### 8.1. Checking annotation presence is too weak

~~~java
assertThat(BoundaryService.class
        .getMethod("insertThenFail", int.class)
        .isAnnotationPresent(Transactional.class))
        .isTrue();
~~~

This snippet only proves the source metadata carries the annotation; it **does not** prove AOP is enabled, the bean is proxied, callers go through the proxy, the right transaction manager is chosen, or rollbacks actually occur. Meaningful tests must observe runtime outcomes.

### 8.2. `AopUtils.isAopProxy` is necessary, not sufficient

~~~java
assertThat(AopUtils.isAopProxy(service)).isTrue();
~~~

Having a proxy does not mean self-calls trigger advice. A proxy might exist for caching while lacking a transaction interceptor, or a non-public/final method may prevent advice from intercepting. Test behavior per concern.

### 8.3. `TransactionSynchronizationManager` returning `true` is not enough

When the outer method is already transactional, a self-called `innerRequiresNew` still sees an active transaction due to the inherited thread-bound context. A boolean does not prove `REQUIRES_NEW` started a separate transaction. The lab includes an **outer commit + inner rollback** test to differentiate them.

### 8.4. Identical cache return values do not prove a cache hit

~~~java
assertThat(service.compute(7)).isEqualTo(70);
assertThat(service.compute(7)).isEqualTo(70);
~~~

Both cached and uncached executions return 70. Measure computation counts, real repository/gateway calls, or cache entries. For TTL caches, test with a fake clock or provider-specific expiry when required.

### 8.5. Validation tests checking only return values are insufficient

If `normalize(" ")` returns `""`, asserting only the output misses missing validation. Write negative tests through the proxy asserting the exception. For controller validation, verify HTTP status and validation payloads at the web layer separately.

## 9. Unit tests, slice tests, and full integration tests

| Test type | Real Spring AOP proxy? | Real transaction manager? | Real cache manager? | Method validation proxy? |
| --- | --- | --- | --- | --- |
| `new BoundaryService(...)` | No | Not via AOP | Not via AOP | Not via AOP |
| Mockito `@Mock` object | No | No | No | No |
| Plain Mockito `@Spy` POJO outside Spring | Not by default | No | No | No |
| `@WebMvcTest` | Mostly MVC slice, lacks all service beans | Usually lacks real service tx setup | Not guaranteed | Does not guarantee target service proxies |
| `@JdbcTest` | JDBC slice; services need explicit import/config | Tests are usually transactional, roll back by default | Incomplete unless imported | Incomplete unless imported |
| `@DataJpaTest` | JPA slice, test-managed transaction | Yes, but default test rollback can mask commit semantics | Incomplete | Incomplete |
| `@SpringBootTest` (lab) | Yes, with proper config | Yes | Yes | Yes |
| Production-like DB/Redis + `@SpringBootTest` | Yes | Yes, real backend | Yes, real provider | Yes |
| Plain AspectJ-woven integration | Depends on weaving config | Possible | Possible | Not automatically equivalent to `MethodValidationPostProcessor` |

**Do not confuse a Mockito spy with a Spring AOP proxy.** `@MockitoBean`/`@MockitoSpyBean` also follow bean override mechanics; spying at the wrong target/proxy layer can replace the very advice under test. When testing proxy interception, keep the real bean and only stub unrelated external collaborators.

## 10. Preferred solution: split beans along boundaries

### 10.1. Why splitting beans works well

When a use case needs:
- API-facing domain orchestration.
- Per-item transactions.
- Cached read models.
- Validated inputs.

Separate responsibilities into:
- `OrchestratorService`: coordination.
- `TransactionalWorker`: transaction boundary.
- `CachedCatalogService`: cache boundary.
- `ValidatedCommandService`: validation boundary.

The orchestrator injects the interfaces/beans, so calls from the orchestrator to collaborators traverse Spring proxies. Business boundaries become clearer and easier to unit- and integration-test.

### 10.2. Illustrative pattern

~~~java
@Service
class InvoiceOrchestrator {

    private final InvoiceWriter writer;
    private final PriceCatalog catalog;
    private final InvoiceValidator validator;

    InvoiceOrchestrator(
            InvoiceWriter writer,
            PriceCatalog catalog,
            InvoiceValidator validator) {
        this.writer = writer;
        this.catalog = catalog;
        this.validator = validator;
    }

    public void create(String invoiceId) {
        validator.check(invoiceId);
        int price = catalog.cachedPrice(invoiceId);
        writer.write(invoiceId, price);
    }
}
~~~

This is a design snippet, not part of the runnable project, and assumes those collaborators exist. Its advantage is that annotations on `check`, `cachedPrice`, and `write` have clean cross-bean invocations. Do not create dozens of unnecessary classes; split along **meaningful cross-cutting boundaries**, not just to "make Spring work."

### 10.3. Why you still cannot `new` the collaborator

~~~java
InvoiceWriter writer = new InvoiceWriter(...);
writer.write(id, amount);
~~~

If `writer` does not come from the Spring container, it has no Spring AOP proxy. Splitting files alone is not enough: it must be a **managed bean** injected properly. A POJO instantiated via `new` will not receive `@Transactional` or `@Cacheable`.

## 11. Programmatic solutions when you do not want to split beans

### 11.1. `TransactionTemplate`

When you need a transaction **inside a method without relying on a proxy**, use `TransactionTemplate`:

~~~java
@Service
public class ProgrammaticBillingService {

    private final TransactionTemplate tx;
    private final JdbcTemplate jdbc;

    public ProgrammaticBillingService(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc) {
        this.tx = new TransactionTemplate(manager);
        this.jdbc = jdbc;
    }

    public void createInTransaction(int id) {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                    "INSERT INTO audit_rows(id, description) "
                            + "VALUES (?, ?)",
                    id, "programmatic");
        });
    }
}
~~~

This snippet needs imports and the matching H2 schema; use it as an architectural alternative, not as a file in the lab. The callback runs inside a transaction controlled by `TransactionTemplate` whenever the method runs, including local calls.

For `REQUIRES_NEW` programmatically, configure:
`template.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW)`. Watch transaction manager/connection pool limits and exception rollback rules.

### 11.2. Programmatic `CacheManager`

~~~java
Cache cache = cacheManager.getCache("numbers");
Integer value = cache.get(key, Integer.class);
if (value == null) {
    value = expensiveCalculation(key);
    cache.put(key, value);
}
~~~

Illustrative snippet: manual caching works inside local calls, yet must handle cache stampedes, null/value semantics, TTL, and concurrency; `@Cacheable` via proxy is usually cleaner. In production caches, avoid check-then-put races when single-flight computation is needed; use provider-specific atomic loading.

### 11.3. `Validator.validate` and `ExecutableValidator`

~~~java
Set<ConstraintViolation<SomeDto>> errors =
        validator.validate(dto);
~~~

This snippet requires a `jakarta.validation.Validator` bean and a concrete `SomeDto`. To enforce method parameter/return constraints without proxies, you can invoke Bean Validation's `ExecutableValidator` explicitly. However, that requires managing method references and errors manually; in most application services, proxy-based Spring method validation is clearer and more consistent.

## 12. Workarounds: self-injection and `AopContext`

### 12.1. Injecting a bean's own proxy

You can use a self-reference (e.g., `@Lazy` injection) to call through the proxy instead of `this`:

~~~java
@Service
class SelfAwareService {

    private final SelfAwareService proxy;

    SelfAwareService(@Lazy SelfAwareService proxy) {
        this.proxy = proxy;
    }

    void outer() {
        proxy.inner();
    }

    @Transactional
    public void inner() {
        // ...
    }
}
~~~

**This snippet carries caveats** and is excluded from the lab. Self-injection risks circular dependencies, depends on proxy styles, and hurts readability and testability. Spring Boot discourages circular references by default. If used, verify the reference actually points to the proxy rather than the raw target and causes no cycle or bootstrap failure.

### 12.2. `AopContext.currentProxy()`

A low-level workaround:

~~~java
((MyService) AopContext.currentProxy())
        .inner();
~~~

Requires `exposeProxy=true` on AOP infrastructure, the call already executing inside a proxied context, compatible proxy types, and importing `AopContext`. It tightly couples business code to Spring AOP and fails outside advised contexts. Do not choose it merely because it feels faster than splitting a bean.

### 12.3. AspectJ weaving

Spring supports `AdviceMode.ASPECTJ` for transactions and caching with proper weaving configuration (compile-time or load-time) and dependencies like `spring-aspects`. When target bytecode is woven, self-invocation can be intercepted without a Spring proxy.

However:
- Simply adding the AspectJ dependency to `pom.xml` **does not enable weaving**.
- Weaving brings its own build/runtime agent configuration, classloader behavior, and test setup.
- Do not assume Spring `@Validated` service method validation switches automatically to AspectJ just because transaction/cache weaving is enabled.
- AOT/native images and toolchains have additional caveats.
- You must run these exact integration tests under your chosen deployment mode.

For typical Spring Boot services, **extracting beans** or using **programmatic boundaries** is much easier to maintain.

## 13. Visibility, final methods, JDK/CGLIB, and annotation placement

### 13.1. Private and final methods

- Spring AOP proxy interception cannot apply to **private methods** when invoked externally; private methods cannot be overridden either.
- CGLIB class-based proxies cannot override `final` classes or methods. Annotating a `final` method can prevent advice from running.
- JDK interface proxies only expose methods declared on the proxied interfaces.
- With `@Transactional` in Spring Framework 6.x, protected/package-private methods have caveats with class-based proxies; `public` methods remain the clearest, most portable design.
- `@Cacheable` docs advise applying annotations on `public` methods when using proxies.
- Method validation generally requires externally accessible methods on Spring-managed `@Validated` beans.

### 13.2. Interface annotations vs. implementation annotations

Spring can read annotations on interface methods in certain proxy configurations, yet AspectJ weaving and class proxies differ in annotation inheritance. For transactions and caching, prefer placing annotations on concrete service implementation methods when possible so behavior does not shift if the proxy strategy changes.

### 13.3. CGLIB does not cure self-calls

Some developers enable `spring.aop.proxy-target-class=true` expecting `this.inner()` to pass through the CGLIB proxy. In Spring AOP proxy mode, internal calls execute on the target and **still bypass advice**. Spring Framework's AOP Proxying Mechanisms documentation explains this explicitly.

### 13.4. `@Configuration(proxyBeanMethods = true)` is a different mechanism

Spring `@Configuration` class enhancement intercepts calls between `@Bean` methods to enforce singleton semantics when `proxyBeanMethods=true`. That is no reason to assume self-invocations inside a `@Service` execute transaction, cache, or validation advice. The two features serve different purposes with different infrastructure.

## 14. How to test proxies instead of only plain logic?

### 14.1. Use real Spring-managed beans

For this goal, `@SpringBootTest` is a clear choice because it:
- Loads AOP, caching, validation, and transaction infrastructure.
- Loads a real `DataSourceTransactionManager` and `JdbcTemplate`.
- Loads a `CacheManager` whose entries can be inspected.
- Registers the method validation post-processor.
- Lets tests autowire both the target service proxy and a separate caller bean.

A pure unit test `new BoundaryService(jdbc)` verifies Java logic but cannot confirm Spring advice runs. Mockito mocks/spies cannot replace an AOP integration test either.

### 14.2. Avoid `@Transactional` on the test class

~~~java
@SpringBootTest
@Transactional
class MisleadingTest {
    // ...
}
~~~

When a test carries an outer transaction managed by Spring TestContext, a `@Transactional(propagation=REQUIRED)` service method joins the test's transaction. Even `this.inner()` inside the bean still sees an active transaction from the test-managed transaction, masking the fact that the inner annotation was never intercepted.

When testing real commits and rollbacks:
- Omit test-level `@Transactional`.
- Use a real DB and query after the method commits or throws.
- Or control transactions intentionally with `TestTransaction`.
- Never assert state inside the same persistence context before rollback occurs.

### 14.3. `@JdbcTest`/`@DataJpaTest` roll back by default

`@JdbcTest` and `@DataJpaTest` normally run each test inside a transaction and roll back at the end. They work well for mappings and repository queries, but are inconvenient for proving **a public service call** opens and rolls back its own transaction when the test already started one.

### 14.4. Reset caches between tests

If the cache retains `compute(7)` from an earlier test, the next test sees a computation count of 0 while still returning 70. The lab:
- Clears the `"numbers"` cache in `@BeforeEach`.
- Resets the computation counter.
- Uses distinct keys per test case.
- Asserts result, counter, and cache entry.

With Redis or Caffeine, also test provider-specific expiry, serialization, eviction, and namespacing; the lab's simple cache does not prove those behaviors.

### 14.5. Do not use Mockito `verify` instead of rollback assertions

~~~java
verify(service).insertThenFail(101);
~~~

Even when the method was called, `verify` reveals nothing about whether a transaction committed or rolled back. Insert a real row, trigger the exception, and query the DB after the transaction completes. To inspect advice ordering, add instrumentation—never replace durable state verification.

### 14.6. Check which layer threw the exception

If `normalize(" ")` is rejected:
- Jakarta Bean Validation `ConstraintViolationException` comes from the service method interceptor.
- Spring MVC `HandlerMethodValidationException` can occur on requests through a controller handler.
- Binding/validation on `@RequestBody` typically produces `MethodArgumentNotValidException`.

Different exception types do not automatically imply a self-invocation bug. Identify the exact invocation path and test layer.

## 15. Common mistakes and fixes

| Symptom | Possible cause | Check / fix |
| --- | --- | --- |
| `@Transactional` on inner method, yet `INSERT` commits | Self-invocation bypassed transaction advice | Call via another bean, verify DB rollback |
| `isActualTransactionActive()` is true, yet `REQUIRES_NEW` fails | Outer transaction already active, inner bypassed | Test independent commit/rollback |
| Changing propagation has no effect | Local call does not traverse proxy | Split bean or use `TransactionTemplate` |
| `@Cacheable` does not reduce DB queries | `this.cachedMethod()` bypassed advice | Inspect counter/cache, extract cache service |
| Self-called `@CacheEvict` does not clear cache | Local call skipped eviction advice | Cross-bean call or explicit `CacheManager` |
| `@Validated` does not reject blank service arg | Internal call bypassed proxy or provider missing | `starter-validation`, class `@Validated`, call proxy |
| Validates parameter but skips return value | Method return constraint not intercepted | Test return value via proxy |
| `@Valid` on DTO present, yet never runs | Validator not invoked at boundary | HTTP validation or manual `Validator` |
| `@SpringBootTest` test sees tx during self-call | Test-level `@Transactional` opened outer tx | Remove test tx and check durable state |
| `@WebMvcTest` misses service advice | Service/infra not loaded in slice | Full integration test or import required beans |
| Bean is not proxied | AOP/transaction/cache/validation not enabled | Inspect `AopUtils`/advisors/config |
| CGLIB enabled, yet self-call still fails | CGLIB class proxy does not intercept `this` | Split beans or apply appropriate weaving |
| `@Transactional` on private method | Proxy does not intercept private methods | Use public boundary on Spring bean |
| `@Transactional` on `final` method | Class proxy cannot override it | Avoid `final` on advised methods |
| `new Service()` skips caching | Not a Spring-managed bean | Inject from Spring context |
| `@PostConstruct` inner tx fails to run | Bean/proxy not ready or local call | Use runner/ready event through proxy |
| Method validation throws unexpected exception | MVC vs. AOP method validation or adapted mode | Verify layer and exception strategy |
| `@Cacheable` + `@Transactional` serves stale data | Cache consistency / advice ordering | Test rollback, eviction, and provider |
| Self-injection causes context startup cycle | Circular reference / proxy class mismatch | Prefer splitting beans |
| `AopContext.currentProxy()` fails | Proxy not exposed or outside advised context | Avoid coupling or configure with tests |
| AspectJ dependency added, yet self-calls still bypass | Weaving not actually enabled | Enable compiler/agent + dedicated tests |
| Direct DB writes visible to query inside same tx | Querying same tx does not prove commit | Read back after transaction finishes |
| Test class passes, yet production differs | Prod DB/cache/provider differs from H2/simple cache | Use Testcontainers / provider integration tests |
| Mockito `@Spy`/`@Mock` hides real advice | Bean replaced with test double | Keep real bean when testing interception |

### 15.1. Systematic debugging workflow

1. Identify **which annotation** is not firing: transaction, cache, or validation.
2. Trace the call graph from the caller: external bean proxy or `this`?
3. Check whether the bean came from the Spring container or `new`.
4. Confirm infrastructure is enabled: tx manager, cache manager, Bean Validation provider, `@Validated`.
5. Check method visibility, `final` modifiers, proxy type (JDK/CGLIB), and annotation placement.
6. Check whether the test class has an outer `@Transactional` or stale cached state skewing observations.
7. For transactions: inject an unchecked exception and **read back from the DB after completion**.
8. For caching: reset counters/caches and inspect actual computation counts.
9. For validation: send invalid parameters/returns through the proxy and assert the exception.
10. Once fixed, add a **cross-bean regression test** so future refactors cannot reintroduce the bypass.

## 16. Self-invocation in other integration concerns

### 16.1. `@Async`

`@Async` also relies on Spring AOP proxies by default. Calling `this.asyncMethod()` inside the same bean can execute synchronously on the caller's thread instead of dispatching to an executor. Verify thread identity/`CompletableFuture` and bounded waits in tests rather than relying on `Thread.sleep`.

~~~java
@Service
class MailDispatcher {
    public void sendAll() {
        this.sendAsync(); // Can run synchronously
    }

    @Async
    public void sendAsync() {
        // ...
    }
}
~~~

This snippet requires `@EnableAsync`, an executor, and proper imports. The primary focus of this lesson remains transactions, caching, and validation.

### 16.2. `@Retryable`

`@Retryable` in Spring Retry also uses advice/proxy infrastructure, so local calls bypass the retry interceptor. Ensure proper dependencies/configuration, public boundaries, and tests checking call counts and backoff. Do not assume `@Retryable` makes a plain Java call retry internally inside the target.

### 16.3. `@Secured` / `@PreAuthorize`

Spring Method Security also uses AOP interception. When a protected service method is self-called on the same target, inspect the proxy boundary and security configuration rather than treating controller URL authorization as a substitute for object-level service policies. This is another reason to separate cross-cutting service boundaries and test denied cases through the proxy.

### 16.4. `@EventListener` and `@TransactionalEventListener`

Event listeners have their own dispatch/lifecycle infrastructure, and `@TransactionalEventListener` has transaction phase semantics. Do not mechanically apply "self-invocation always bypasses" to every event annotation; examine who dispatches/invokes the method and how listeners are registered.

### 16.5. Reactive transactions

Reactive transactions with `TransactionalOperator` or reactive `@Transactional` use Reactor Context rather than ThreadLocal JDBC transactions. This lab uses imperative `JdbcTemplate`, where `TransactionSynchronizationManager.isActualTransactionActive()` is meaningful. With R2DBC, write dedicated tests for reactive flows and subscriptions rather than copying boolean/JDBC checks.

## 17. Impact on architecture design and code review

### 17.1. Boundary methods should be explicit

A codebase is easier to review when:
- Orchestrator methods avoid misleading annotations.
- Side-effect boundaries like `paymentWrite` live in a dedicated service.
- Cached reads live in a service with a clear caching contract.
- Validation sits at request boundaries and service boundaries per domain rules.
- Public annotated methods are invoked via managed dependencies.

Annotations should never be "decoration"; each requires integration tests protecting its semantics.

### 17.2. Prefer rollback tests over reflection tests

If the rule is "never persist the receipt when validation fails":
- A plain mock does not prove DB rollback.
- Reflection seeing `@Transactional` does not prove the proxy is active.
- A real test sets up an H2/PostgreSQL fixture, calls the external bean method, triggers an exception, and queries row counts after rollback.

### 17.3. Avoid tight coupling just to force proxying

Self-injection or `AopContext.currentProxy()` can patch a single spot locally, at a cost:
- The class becomes harder to unit-test outside Spring.
- Circular dependencies become likely.
- Proxy type changes can cause runtime casting issues.
- Business code becomes aware of AOP plumbing details.
- New developers wonder why `self.method()` is used instead of `this.method()`.

Splitting beans or using programmatic boundaries is usually far clearer.

### 17.4. Testing caching and transactions with distributed data

An H2 + simple cache test verifies Spring AOP semantics only. For production:
- PostgreSQL/MySQL: locking, isolation, and rollback differ across DB dialects.
- Redis: network errors, serialization, TTL, stale caches, and eviction timing.
- Hibernate/JPA: the first-level persistence context can make queries appear "cached" even when `@Cacheable` never ran.
- Distributed services: cache invalidation and external side effects do not share a single JDBC transaction.

Use Testcontainers/production-like services and end-to-end assertions for critical contracts, avoiding overclaiming from the lab.

## 18. Exercises

1. Run the project and inspect all 14 JUnit methods; categorize the transaction, cache, and validation groups.
2. Call `BoundaryService.insertThenFail` through the Spring bean and explain why the row rolls back.
3. Call `selfInsertThenFail` and explain why H2 retains the row despite the exception.
4. Change `spring.datasource.hikari.auto-commit=false` on a scratch branch and analyze why it changes the observation while **not fixing** the proxy bypass.
5. Add a `@Transactional(readOnly=true)` inner method and self-call it from an outer method; test whether read-only advice applies.
6. Add `Propagation.MANDATORY` to an inner method and compare external vs. self-invocation when the outer method is non-transactional.
7. Change `REQUIRES_NEW` to `REQUIRED` on both paths; reason about the behavioral difference before and after refactoring.
8. Throw a checked exception inside a proxied method; test default rollback rules and `rollbackFor`.
9. Add `@Transactional` onto a JUnit test method and observe how it masks the "no transaction" state of a self-call.
10. Create a self-called `@CacheEvict` method after an update; observe stale cache data and fix it with a cross-bean call.
11. Configure Caffeine or Redis TTL in a dedicated integration test instead of inferring TTL from `ConcurrentMapCacheManager`.
12. Replace `key="#p0"` with a key missing the tenant dimension; write a negative test demonstrating cross-tenant cache leakage.
13. Test a `@NotBlank` parameter via external call vs. self-call; compare the exception against the returned blank value.
14. Add `@Positive` to an integer parameter and verify input `0` is rejected through the proxy.
15. Add a `@NotNull` return-value constraint and test post-method validation.
16. Move `@Validated` onto a service interface instead of the concrete class and inspect behavior under JDK vs. CGLIB proxy modes.
17. Introduce an interface for the service, switch to JDK proxies, and verify autowiring/casting types.
18. Mark an advised method `final` on a scratch branch and observe proxy limitations; do not merge that branch.
19. Write a pure unit test `new BoundaryService(...)` with a mock `JdbcTemplate`; explain why it **does not** test Spring AOP.
20. Try `@WebMvcTest` loading only a controller; explain why service transactions, caching, and validation are not fully verified.
21. Turn `CrossBeanFacade` into a real application orchestrator service and measure SQL query and cache hit counts.
22. Refactor using `TransactionTemplate` instead of inner `@Transactional`; verify local calls open a transaction.
23. Test programmatic `Validator.validate(dto)` and compare it with a method-validation proxy.
24. Configure AspectJ weaving in a separate experimental module and run the same regression tests to confirm self-calls are intercepted when weaving is active.
25. Add an `@Async` inner method and compare thread identity between self-invocation and cross-bean calls.
26. Enable `@EnableMethodSecurity` and test `@PreAuthorize` under cross-bean vs. self-invocation in a separate module.
27. Create a PostgreSQL Testcontainers variant to test rollback and isolation beyond H2.
28. Draft a team code-review checklist: every annotated boundary method must have a verified caller path and matching regression test.

## 19. Pre-merge checklist

- [ ] Are `@Transactional`, `@Cacheable`, and `@Validated` actually processed by Spring infrastructure?
- [ ] Are public annotated methods invoked through proxies?
- [ ] Are there any `this.annotatedMethod()` or implicit self-calls causing bypasses?
- [ ] Are CGLIB/JDK proxy rules understood without treating CGLIB as a self-call cure?
- [ ] Are there real transaction rollback tests instead of annotation-only assertions?
- [ ] Is `REQUIRES_NEW` verified via separate commit/rollback rather than just an active-transaction boolean?
- [ ] Is test-level `@Transactional` avoided when it would mask service transaction boundaries?
- [ ] Is database state queried after the transaction finishes?
- [ ] Do caching tests assert counters, side effects, or cache contents rather than return values alone?
- [ ] Do cache keys include all required tenant/user/business dimensions?
- [ ] Are caches cleared/isolated between test methods?
- [ ] Does caching infrastructure have `@EnableCaching` and the right provider configured?
- [ ] Does method validation have a Bean Validation provider and class-level `@Validated`?
- [ ] Are invalid method parameters rejected through the proxied path?
- [ ] Are invalid return values tested as well?
- [ ] Is Spring MVC built-in validation distinguished from AOP service validation?
- [ ] Do tests avoid mocking the very proxy/service under test?
- [ ] Are both `AopUtils` checks and **behavioral assertions** present?
- [ ] Are regression tests added after refactoring to split beans?
- [ ] If using self-injection, are there no circular-reference or proxy-type bugs?
- [ ] If using AspectJ, is weaving actually active and verified at runtime?
- [ ] Are `@PostConstruct` and private/final methods avoided as advice boundaries?
- [ ] Are rollback and caching tested against production-like DBs/caches when critical?
- [ ] Are secrets and production data kept out of integration tests?
- [ ] Do Maven/JUnit reports confirm tests actually executed and behaved properly?

**Conclusion:** Self-invocation does not prevent the Java method body from running, yet under Spring AOP **proxy mode** it skips advice attached to the internal method. The result can be missing rollbacks, missed cache hits/evictions, or unenforced validation. An active outer transaction does not rescue `REQUIRES_NEW` metadata on a self-called inner method. Assert **real outcomes**: DB state after exceptions, cache computation counts, and parameter/return constraint violations; contrast self-calls with cross-bean calls, then fix by extracting beans or defining programmatic boundaries. Never rely on reflection, Mockito-only tests, or test-level `@Transactional` to infer proxy integration behavior that was never exercised.

## 20. Official references

- Spring Framework 6.2 — AOP Proxying Mechanisms (self-invocation): https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Framework 6.2 — Using `@Transactional` (proxy mode, `REQUIRES_NEW` caveats): https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2 — Transaction rollback rules: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html
- Spring Framework 6.2 — Programmatic Transaction Management / `TransactionTemplate`: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html
- Spring Framework 6.2 — Declarative Annotation-Based Caching: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework 6.2 — Java Bean Validation, `MethodValidationPostProcessor`: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Boot 3.5 — Validation: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Spring Boot 3.5 — Caching: https://docs.spring.io/spring-boot/3.5/reference/io/caching.html
- Spring Boot 3.5 — JDBC SQL Databases: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Spring Boot 3.5 — Testing Spring Boot Applications and JDBC test slices: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — `TransactionalTestExecutionListener`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/transaction/TransactionalTestExecutionListener.html
- Spring Framework 6.2 — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Boot 3.5.16 — Release notes: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now