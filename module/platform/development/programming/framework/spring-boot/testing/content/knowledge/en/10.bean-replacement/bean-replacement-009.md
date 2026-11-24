# Mocked Beans and Their Impact on Transaction, Cache, or Security Proxies in Spring Boot Tests

## 1. The problem: green tests where AOP behavior was never verified

In Spring Boot, much critical behavior does not sit inside the service method body itself. Spring can attach **advice** around calls to a bean via an **AOP proxy** to enforce transactions, caching, or authorization checks:

- `@Transactional`: starts or joins a transaction, committing or rolling back per configuration.
- `@Cacheable`, `@CacheEvict`, `@CachePut`: reads, writes, or evicts cache entries per policy.
- `@PreAuthorize`, `@PostAuthorize`: enforces method-level authorization when method security is enabled.

When you **replace the service bean itself with a Mockito mock**, tests may see only pre-programmed `when(...).thenReturn(...)` outputs rather than real logic. The danger is that such a test stays green while **proving nothing** about transactions, working caches, or production authorization enforcement.

In particular, never assert an absolute rule like "a mock bean definitely has no proxy." Depending on bean type, annotations, advisors, proxy-creation timing, bean override mechanics, and Spring version, a mock may or may not sit behind a proxy. **And even the presence of a proxy does not prove a specific advice executed.** Choose proper test boundaries and assert **observable behavior**, never guessing from annotation names.

Lesson goals: understand **which bean is replaced**, **whether calls traverse a proxy**, **what mocking bypasses**, and **how to write assertions** that avoid overclaiming.

## 2. Three layers to distinguish: target object, bean, and proxy

A typical AOP-enabled service call flows as follows:

```text
Controller or test calls Spring bean
               |
               v
        [AOP proxy if present]
          |      |      |
          |      |      +-- Method-security advice
          |      +--------- Cache advice
          +---------------- Transaction advice
               |
               v
        [Real target object]
               |
               v
        Repository / HTTP client
```

The diagram only illustrates **possible interceptors**; there is no guarantee all three exist, nor does it impose a fixed advice order. Actual ordering depends on advisor configuration and can affect outcomes.

Three distinct concepts:

1. **Target object:** e.g., `OrderService` holding the real Java code.
2. **Injected Spring bean:** the Spring-managed object; either the target directly or a proxy wrapping it.
3. **Mockito mock:** an object driven by stubs, skipping real method bodies unless configured otherwise.

If a test runs `new OrderService(mockRepository)`, it tests service logic while **bypassing Spring AOP proxies**. Using `@Autowired OrderService` from a context with AOP configured allows calls to go through the proxy. Replacing `OrderService` with a mock stops tests from verifying the real method body by default, even when context startup succeeds.

**Core principle:** to test transactions, caching, or security declared on a **service**, keep the **service as a real Spring-managed bean** and mock the **dependencies behind it**. To test how a controller handles service results, mocking the service can fit—just never treat that controller test as proof of the service's AOP behavior.

## 3. `@Mock`, `@MockitoBean`, `@MockitoSpyBean`, and legacy annotations

| Tool | Is the bean in Spring context replaced? | When useful? | Limitations |
|---|---|---|---|
| Mockito `@Mock` | **Not automatically** | Plain Java unit tests passing mocks via constructor | Does not test Spring DI/AOP |
| Spring TestContext `@MockitoBean` | **Yes**, replaces bean with mock or creates mock bean per default mechanism | Context tests needing a fake dependency to isolate a real service | Code on the replaced bean does not run |
| `@MockitoSpyBean` | Wraps an existing bean with a spy | Needing partial real behavior plus call tracking | Interactions with AOP/caching can be subtle; requires controlling stubbing and proxies |
| Legacy Spring Boot `@MockBean` | Replaces/creates mock bean in Boot test context | Projects on older Boot versions | Deprecated in newer Boot lines; check version to migrate appropriately |
| Legacy Spring Boot `@SpyBean` | Creates a spy for a bean in Boot test context | Legacy projects needing spies | Also requires checking AOP proxies and versions |

`@MockitoBean` and `@MockitoSpyBean` are available in Spring Framework **6.2 and later** under `org.springframework.test.context.bean.override.mockito`. On Boot 3.4+ (built on Spring Framework 6.2+) or newer compatible lines, prefer this API when present in dependencies. Do not copy those imports directly into older Boot projects lacking Spring Framework 6.2.

Sample usage:

```java
@MockitoBean
PaymentGateway paymentGateway;
```

When the test class integrates with Spring TestContext, this replaces or registers a `PaymentGateway` mock bean in the test context. It **does not** replace every bean in the application. Type/name resolution may require `@Qualifier` or explicit bean names when multiple same-type beans exist; tests must confirm they mock the **exact instance injected into the service**.

Further distinctions:
- Mockito's `@InjectMocks` builds objects and injects mocks in unit tests; it does not create a Spring application context with AOP proxies.
- Spring's `@Autowired` retrieves beans from the context. When testing AOP, calling through a Spring-injected bean is the right entry point.
- `@MockitoSpyBean` requires an existing real bean to wrap; never use it to fabricate missing beans. With stateful-advice proxies such as caches, calls during spy stubbing or verification can interact unexpectedly with advisors.

## 4. Impact table across mechanisms

| Behavior to prove | Mocking the **annotated service** | Mocking the **repository/client behind the real service** | More reliable test |
|---|---|---|---|
| Does `@Transactional` open and roll back properly? | Stubbing service output proves neither the interceptor nor rollback | Real service may traverse transaction proxy, yet a mock repository proves no DB commit/rollback | Context with real transaction manager; check transaction at boundary or real DB post-commit/rollback |
| Does `@Cacheable` avoid calling the dependency again? | Stubbing the service proves nothing about real method caching; any proxy around a mock behaves differently | Real service with cache advice plus mock gateway lets you count gateway calls | Call twice with same key through injected bean; verify result and gateway call count |
| Does `@CacheEvict` actually clear keys? | Do not infer from mock call counts | Can test real service with real cache manager and mocked dependency | Warm cache → run evict operation → read again and verify fresh fetch |
| Does `@PreAuthorize` block unauthorized access? | A green `when(...)` proves no interceptor executed | Real service has method-security advisor; mocking dependency still proves it was never called when denied | Call real bean under an unauthorized `SecurityContext` and assert access denied |
| Does the HTTP security filter block requests? | Mocking service says nothing about whether filters ran | Depends on web test slice and loaded filter chain | `MockMvc`/HTTP test with real security filters asserting 401/403 |
| Is service business logic accurate? | Skipping real logic leaves it untested | Unit or Spring test with real service and mock dependencies | Assert outputs, error paths, and business side effects |

**Never conclude that a controller test using `@MockitoBean OrderService` has tested `@Transactional`, `@Cacheable`, and `@PreAuthorize` on `OrderService`.** That test proves only controller behavior, request/response handling, and whatever components genuinely ran inside its context.

## 5. Runnable Java 17+ example: keeping the service real, mocking the gateway to test caching

### 5.1. Business requirement

A service fetches a SKU's unit price via a gateway and caches the result by SKU. For the same SKU while cached, a **second call** must return the same price **without calling the gateway again**.

To prove this, we need:
1. A **real service** with a `@Cacheable` method.
2. **Real cache infrastructure** enabled by `@EnableCaching` in the Spring context.
3. A **mock gateway** to count external lookups.
4. Calls routed through the **Spring-injected service bean**, not `new PriceService(...)`.

This example uses **Spring Framework 6.2+**, Java 17+, JUnit Jupiter, Spring TestContext, Mockito, and Spring caching modules. In compatible Spring Boot projects, dependencies typically involve `spring-boot-starter-test` and `spring-boot-starter-cache`. No database or HTTP server is needed.

### 5.2. Dependency to double

File `src/main/java/com/example/testing/PriceGateway.java`:

```java
package com.example.testing;

public interface PriceGateway {
    int fetchUnitPrice(String sku);
}
```

### 5.3. Real cached service

File `src/main/java/com/example/testing/PriceService.java`:

```java
package com.example.testing;

import org.springframework.cache.annotation.Cacheable;

public class PriceService {

    private final PriceGateway gateway;

    public PriceService(PriceGateway gateway) {
        this.gateway = gateway;
    }

    @Cacheable(cacheNames = "prices")
    public int getUnitPrice(String sku) {
        return gateway.fetchUnitPrice(sku);
    }
}
```

The class and method are `public` and non-`final`, suitable for standard class-based proxying when no business interface is declared. Do not construct `new PriceService` manually in a test verifying cache advice; a manually constructed instance bypasses bean post-processor proxying.

### 5.4. Test using `@MockitoBean` for gateway while keeping `PriceService` real

File `src/test/java/com/example/testing/PriceServiceCachingTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(classes = PriceServiceCachingTest.TestConfig.class)
class PriceServiceCachingTest {

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    static class TestConfig {

        @Bean
        CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("prices");
        }

        @Bean
        PriceService priceService(PriceGateway gateway) {
            return new PriceService(gateway);
        }
    }

    @MockitoBean
    PriceGateway gateway;

    @Autowired
    PriceService priceService;

    @Test
    void secondCallWithSameSkuUsesCache() {
        when(gateway.fetchUnitPrice("SKU-1")).thenReturn(125_000);

        int first = priceService.getUnitPrice("SKU-1");
        int second = priceService.getUnitPrice("SKU-1");

        assertEquals(125_000, first);
        assertEquals(125_000, second);
        assertTrue(AopUtils.isAopProxy(priceService));
        verify(gateway, times(1)).fetchUnitPrice("SKU-1");
    }
}
```

**Explanation of the evidence:**

- `@SpringJUnitConfig` combines `SpringExtension` and `@ContextConfiguration` for JUnit Jupiter, loading only the specified configuration.
- `@EnableCaching` activates AOP caching; `ConcurrentMapCacheManager` supplies a real `prices` cache in the test context.
- `@MockitoBean PriceGateway gateway` registers/replaces the gateway bean with a mock injected into the service constructor. **`PriceService` remains a real instance** built by the factory method and processed by the container.
- `@Autowired PriceService` retrieves the Spring-managed bean; `AopUtils.isAopProxy` confirms a proxy exists, though **that alone does not prove a cache hit**.
- Both calls with the same SKU return the right price; `verify(gateway, times(1))` is what proves the gateway was called **only once**, meaning the second call skipped re-querying within this test scope.
- Had the test replaced `PriceService` itself with a mock stubbing `getUnitPrice`, returning `125_000` would merely replay programmed values rather than proving real method caching.

This test **protects the service's cache advice** within the declared context; it does not test Redis, TTLs, eviction, or distributed caching. If production uses Redis or Caffeine with distinct expiration policies, write separate integration tests for that cache provider.

### 5.5. Running the test class

With Gradle Wrapper (Linux/macOS):

```bash
./gradlew test --tests "com.example.testing.PriceServiceCachingTest"
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.testing.PriceServiceCachingTest"
```

With Maven Wrapper (Linux/macOS):

```bash
./mvnw -Dtest=PriceServiceCachingTest test
```

On Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=PriceServiceCachingTest test
```

These commands assume compatible dependencies and a JUnit Jupiter runner (Gradle usually requires `useJUnitPlatform()`). The test produces no custom business stdout; Gradle/Maven reports record the result. Never claim the test **ran on a real project** unless you actually executed these commands.

## 6. Stateful caches: why misplacing a spy or mock causes false positives

Caching is **stateful** advice: for the same key, a call at the proxy can return straight from cache **without reaching the target**. Therefore:

- `@MockitoSpyBean` wrapping a real bean helps track certain behaviors, yet when a spy sits behind a cache proxy, `verify(spy)` sees only calls that actually reached the spy; **cache hits may never touch the spy**.
- In some proxy/spy arrangements, `when(spy.method())` can trigger real calls or invoke advice during stub setup. Prefer `doReturn(...).when(spy).method(...)` on spies to avoid running the real method during stubbing, while keeping in mind calls through proxies may still hit cache/other advisors.
- To verify **real** caching, never stop at `cacheManager.getCache("prices") != null` or `AopUtils.isAopProxy(service)`. Test **two-call/eviction behavior** while controlling cache state.
- Contexts can be **cached across tests**. `ConcurrentMapCacheManager` retains entries for the context's lifetime, so tests reusing the same SKU and context can affect each other. Isolate keys or explicitly clear caches in setup rather than relying on run order.
- If a cache stores per-user data yet keys only by SKU or ID without user context, data leaks across users. Test changing `SecurityContext` against a cache already warmed by an earlier user rather than testing only cold-cache requests.

**Warning:** `@Cacheable` can skip executing the method body entirely on a cache hit. If the method body performs manual permission checks, cache advice can cause subsequent calls to follow a different path than the first. Never assume a security annotation or an `if` check inside the target protects every cache hit; check advisor ordering and test for the actual risk.

## 7. Transactions: mocking a repository vs. mocking a service

Consider a service method:

```java
@Transactional
public void createInvoice(Invoice invoice) {
    invoiceRepository.save(invoice);
}
```

This is an **illustrative snippet** inside a service class that already has `invoiceRepository`, `import org.springframework.transaction.annotation.Transactional`, and `Invoice`; it is not a standalone file.

In a typical Spring AOP proxy setup:

```text
Test/Controller
    |
    v
[Transaction proxy]
    |
    v
InvoiceService.createInvoice(...)  <- real logic
    |
    v
InvoiceRepository                    <- may be mocked in unit/context tests
```

Three distinct scopes of proof:

1. **Mocking `InvoiceService` itself:** `verify(service).createInvoice(...)` only proves the mock was invoked. If the service method is stubbed, nothing proves the transaction interceptor ran, the repository saved, or rollback occurred.
2. **Real service via Spring proxy, mocking `InvoiceRepository`:** verifies the service constructs the right entity, calls `save` the expected number of times, and **observes an active transaction context** when a real transaction manager/config exists in the test. However, a mock repository **cannot prove DB commit or rollback**.
3. **Real service + real repository + test database:** verifies transactional effects on persisted data across commit/rollback, constraints, and SQL behavior. This is an integration test using `@SpringBootTest`, `@DataJpaTest`, or Testcontainers depending on scope.

Enabling annotation-driven transactions in plain Spring contexts typically requires `@EnableTransactionManagement` and a `PlatformTransactionManager`/appropriate transaction manager. In Boot, auto-configuration supplies that infrastructure when dependencies and settings match. **Having `@Transactional` in source code does not automatically mean transactions are active in tests.**

### 7.1. Checking whether a transaction is active when calling a mock repository

In a test with **a real service behind a transaction proxy, a real transaction manager, and a mock repository**, you can inspect transaction status right when the repository is invoked:

```java
when(invoiceRepository.save(any(Invoice.class)))
        .thenAnswer(invocation -> {
            assertTrue(
                    TransactionSynchronizationManager
                            .isActualTransactionActive());
            return invocation.getArgument(0);
        });
```

This **illustrative snippet** requires Mockito/JUnit imports, `TransactionSynchronizationManager`, and defined `Invoice`/`invoiceRepository` types. It is not a standalone complete test.

Returning `true` proves a transaction was active **at the moment the mock was called**; it does not by itself prove `createInvoice` opened it, nor that the database committed. If the test method/class itself carries `@Transactional`, the test-managed transaction can make this check pass even if the production service failed to open its boundary. To test service boundaries accurately, run outside test-managed transactions or use `TestTransaction` to explicitly control transaction completion.

### 7.2. How to verify real rollbacks

When the requirement is "write two tables or roll back both if the second step fails," unit tests with mock repositories only prove **call decisions**, not atomicity. A trustworthy integration test should:
- Use an appropriate database and transaction manager; when bugs depend on SQL dialects, use a database close to production.
- Call the method **through the Spring-injected bean/proxy**, not a manually constructed target.
- Seed clean data, trigger the exception condition, and **read back database state** across a proper transaction boundary.
- Distinguish rollback caused by the **test framework** from rollback caused by the **service**. Many Spring tests annotated `@Transactional` automatically roll back after the test, masking bugs where the service mistakenly committed.
- Confirm rollback rules: Spring defaults to rolling back on `RuntimeException`/`Error`, while checked exceptions may require explicit rules depending on configuration/version; `rollbackFor` and system config alter outcomes.

Never conclude "transactions are fine" just because `verify(repository).save(...)` passed or the test class has `@Transactional`.

## 8. Security: method-level authorization vs. HTTP filters

Spring Security enforces at least two boundaries tests must keep separate:

- **HTTP/request security:** `SecurityFilterChain` authenticates/authorizes requests before reaching controllers. `MockMvc` tests must execute through the appropriate filters to prove this behavior.
- **Method security:** `@PreAuthorize` and `@PostAuthorize` run when a Spring bean method is invoked **through the corresponding security mechanism**, typically a Spring AOP proxy enabled by `@EnableMethodSecurity`.

Spring Boot starter security **does not enable method security automatically** merely because the dependency is present; the application/test context needs `@EnableMethodSecurity` or equivalent configuration. A `@WebMvcTest` with a mocked service can verify HTTP-layer filters **if the required filters are loaded**, yet cannot prove calls into a **method-protected real service** are guarded.

Mocking a service bean annotated `@PreAuthorize` can skip the real method body, while whether advice remains attached depends on actual proxy setup. Never **infer** security is enabled or disabled solely from `@MockitoBean` or `@WithMockUser`; test both allowed and denied behaviors explicitly.

## 9. Runnable Java 17+ example: testing method security on a real bean, mocking the gateway

This example is independent of Section 5's cache test while reusing `PriceGateway`. It requires `spring-security-config`, Spring Security method-security infrastructure, and `spring-security-test` (typically via Boot's Spring Security starter/test dependencies). Both production and test classes live in `com.example.testing`.

### 9.1. Real service with `@PreAuthorize`

File `src/main/java/com/example/testing/SecuredPriceService.java`:

```java
package com.example.testing;

import org.springframework.security.access.prepost.PreAuthorize;

public class SecuredPriceService {
    private final PriceGateway gateway;

    public SecuredPriceService(PriceGateway gateway) {
        this.gateway = gateway;
    }

    @PreAuthorize("hasAuthority('PRICE_READ')")
    public int getPrice(String sku) {
        return gateway.fetchUnitPrice(sku);
    }
}
```

This file requires `PriceGateway.java` from Section 5 and Spring Security dependencies. The bean is registered via test configuration. `@PreAuthorize` takes effect only when method security is enabled.

### 9.2. Test invoking the Spring bean under two security contexts

File `src/test/java/com/example/testing/SecuredPriceServiceTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(classes = SecuredPriceServiceTest.TestConfig.class)
class SecuredPriceServiceTest {

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    static class TestConfig {
        @Bean
        SecuredPriceService securedPriceService(PriceGateway gateway) {
            return new SecuredPriceService(gateway);
        }
    }

    @MockitoBean
    PriceGateway gateway;

    @Autowired
    SecuredPriceService service;

    @Test
    @WithMockUser(authorities = "PRICE_READ")
    void callerWithAuthorityCanReadPrice() {
        when(gateway.fetchUnitPrice("SKU-1")).thenReturn(125_000);

        assertEquals(125_000, service.getPrice("SKU-1"));
        verify(gateway).fetchUnitPrice("SKU-1");
    }

    @Test
    @WithMockUser(authorities = "PRICE_WRITE")
    void callerWithoutAuthorityIsRejected() {
        assertThrows(AccessDeniedException.class,
                () -> service.getPrice("SKU-2"));
        verifyNoInteractions(gateway);
    }
}
```

Explanation:

- `@EnableMethodSecurity` registers method-security advisors in the test context.
- `SecuredPriceService` remains a **real bean** created by `@Bean` and processed by Spring to enforce `@PreAuthorize`.
- `@MockitoBean` replaces only `PriceGateway`. This lets the test prove the service runs real code and enforces authorization before calling the gateway.
- `@WithMockUser(authorities = "PRICE_READ")` sets up the `SecurityContext` for the authorized case; the other test supplies a different authority to verify denial.
- Without the required authority, `AccessDeniedException` (or a matching subtype) is asserted, and the gateway is **never called**. This is far stronger than checking a mock service throwing an exception via `thenThrow`.
- This example verifies **method security** in a minimal context; it does not test HTTP 401/403 status codes, filter chains, login flows, JWTs, or production role mappings.

`@WithMockUser` is not proof that HTTP security filters ran. It populates a test authentication inside `SecurityContext`; testing filters/requests requires dedicated HTTP tests with filters enabled.

When combining multiple proxies, observe actual runtime behavior and verify advice ordering. Never assume caching, transactions, and method security always execute in one fixed order across all configurations.

### 9.3. Run commands

Gradle (Linux/macOS):

```bash
./gradlew test --tests "com.example.testing.SecuredPriceServiceTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.testing.SecuredPriceServiceTest"
```

Maven (Linux/macOS):

```bash
./mvnw -Dtest=SecuredPriceServiceTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=SecuredPriceServiceTest test
```

The test prints no custom stdout. These examples compile and run in Java 17+ projects with the listed dependencies and configurations, though showing the code does not substitute for running it and checking your project's actual test reports.

## 10. Proxy existence does not prove transactions, caching, or security work

Common diagnostic utilities:

```java
boolean proxied = AopUtils.isAopProxy(service);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(service);
boolean cglibProxy = AopUtils.isCglibProxy(service);
```

This is an **illustrative test snippet importing `org.springframework.aop.support.AopUtils` with a `service` variable**. The booleans tell you whether the injected object is a recognized AOP proxy and which kind. They **do not** prove any particular advice executed or DB records committed. For diagnostics you can inspect the target class via `AopUtils.getTargetClass(service)`; never unwrap a proxy and call the target directly to "test transactions," as that **bypasses the exact interceptor** you want to verify.

Mockito provides `Mockito.mockingDetails(object).isMock()` to ask whether Mockito recognizes an object as a mock. However, if an injected bean is an **outer proxy wrapping a mock**, the answer on the proxy may differ from the answer on the target. Do not use a single object-type check to draw full conclusions about AOP proxy composition.

### 10.1. Self-invocation: internal calls can bypass the proxy

In Spring AOP proxy mode, **an object calling another method on itself** typically bypasses the proxy. For example:

```java
public void outer() {
    inner(); // Call within the same target object
}

@Transactional
public void inner() {
    // ...
}
```

This is an **illustrative snippet inside a class**, not a standalone file. If `outer()` is not already inside a transaction, calling `inner()` via `this` in standard proxy mode does not trigger `@Transactional` advice on `inner()`. The same caveat applies to `@Cacheable` and many method-security proxies. Mocking is not the only reason advice fails to execute: the **call path** matters too.

Standard remedies are extracting the intercepted method into a separate bean called across its bean boundary, or placing transaction/security boundaries on public service methods invoked externally; AspectJ weaving behaves differently from proxies. Avoid self-injection hacks just to route back through a proxy without understanding lifecycle and circular dependency risks.

### 10.2. Interface proxies, class proxies, and `final` methods

- **JDK dynamic proxies** operate via interfaces; callers may need to inject and invoke via the exposed interface.
- **Class-based proxies** rely on subclassing (commonly CGLIB); `final` classes or `final` methods cannot be overridden to apply subclass proxy advice.
- Methods excluded from advisor pointcuts, lacking required visibility, or not invoked through the proxy will not receive expected advice.
- Seeing `@Transactional` or `@PreAuthorize` in source code is merely metadata; enabling the corresponding infrastructure and calling properly are required for runtime behavior.

In Spring Boot, proxy selection can be influenced by global properties and auto-proxy creators in the context. Never assume every project uses the same proxy kind by default.

## 11. Combining transactions, caching, and security on the same service

When one method stacks multiple concerns, **advice ordering and cache keys** can have major consequences:

1. **Does security run before or after caching?** If cached results return before authorization advice runs, stale entries risk leaking data. Determine advisor ordering and test requests with differing permissions against a **warm cache**.
2. **Does the cache key distinguish users or tenants?** `@Cacheable(key = "#id")` may omit principal/tenant when responses depend on the caller; design keys and access controls per contract.
3. **Are eviction and transactions synchronized?** If a cache updates/evicts before a transaction fails and rolls back, cache state diverges from the database. Check transaction-aware cache configuration and commit/evict timing.
4. **Does method security run before or after the call?** `@PreAuthorize` checks beforehand; `@PostAuthorize` checks after the method returns, allowing side effects to happen beforehand. Never treat `@PostAuthorize` as blocking DB writes prior to execution.
5. **At which layer should you mock?** Mocking the service destroys the basis for verifying real logic; mocking repositories/gateways usually keeps the service and advisors in the real call path, though it never replaces DB/Redis/HTTP integration tests.

Suggested test matrix:

| Case | State | What to verify |
|---|---|---|
| First call by authorized user, empty cache | Cache miss | Returns right result, gateway called |
| Repeated call with same key and authority | Cache hit | Returns right result, gateway not called again |
| Call with same key on warm cache by unauthorized user | Different `SecurityContext` | Denied per contract, no data leaked |
| Mutate data then evict | Stale entry in cache | Subsequent read fetches fresh data |
| DB write fails mid-transaction | Exception/rollback | No partial commit persisted; cache holds no invalid state |
| Invoke service through context bean | Proxy boundary | Advisor activates per observable behavior |
| Internal call via `this` | Self-invocation | Recognize when advice is skipped under proxy mode |

One test need not cover everything. Split cache tests, method security tests, transaction integration tests, and HTTP security tests so failures remain easy to diagnose.

## 12. Common pitfalls when replacing beans in Spring Boot tests

| Mistake | Why it is dangerous | How to fix |
|---|---|---|
| `@MockitoBean` directly on a `@Transactional` service, then claiming rollback works | Real logic and DB were never exercised | Use real service + test DB, verify state after rollback |
| Mocking a `@Cacheable` service and asserting only stub values | Stubs return data without real execution | Mock gateway, keep service/cache advice real, test two calls |
| `@WithMockUser` + mock service, claiming method security blocks callers | Test proves nothing about real service's method-security advice | Use real service + `@EnableMethodSecurity`, assert allowed and denied cases |
| Thinking `@Mock` replaces a Spring bean | Service may still receive another bean | Use `@MockitoBean` with matching type/name in test context when overriding |
| Assuming proxy existence means all three advices work | Proxy may handle only one concern | Test actual behaviors and required advisor configs |
| Instantiating service via `new` when testing AOP | Bypasses Spring proxy | `@Autowired` bean from context |
| `@Cacheable` tests failing to clear cache state | Tests become order-dependent | Separate keys/data or clear caches intentionally |
| Using a spy and calling `when(spy.method())` carelessly | Can execute real method or interact with advice | Prefer `doReturn`; understand proxy/spy interaction; avoid unnecessary spies |
| Relying on `verify(repository.save())` to claim DB commit | Mocks create no real transactions | Add integration tests inspecting DB state across transaction boundaries |
| Test `@Transactional` rolls back automatically, mistaken for service rollback | Test framework itself rolled back | Test service transaction boundaries outside test-managed rollback |
| Forgetting `@EnableMethodSecurity` | `@PreAuthorize` stays inactive | Enable/configure method security in the context |
| Disabling Security filters in `MockMvc` while claiming 403/401 is tested | Real filter chain was removed from the path | Enable required filters and assert HTTP status at the proper layer |
| Overlooking self-invocation or `final` methods | Advisors cannot intercept those calls | Place boundaries on proper beans/methods and verify proxy usage |
| Using wrong bean name in override when multiple implementations exist | Wrong dependency mocked or context error | Identify exact name/qualifier and override config |

## 13. Risk-based testing strategy

A balanced suite typically layers complementary tests:

**Layer 1 – plain Java unit tests:** instantiate the real service with constructor-mocked repositories/gateways; test formulas, validation, branches, and interactions. This layer **does not** test AOP, so no Spring context is needed.

**Layer 2 – focused context tests:** use `@SpringJUnitConfig`/`@ContextConfiguration` with only the cache/security/transaction infrastructure under test. Mock dependencies via `@MockitoBean` while keeping the main bean real; verify proxy behavior. Ideal for answering "did Spring wire advisors properly and how do they behave?"

**Layer 3 – real-infrastructure integration tests:** use `@SpringBootTest`, `@DataJpaTest`, Testcontainers, test Redis instances, or equivalents to verify DB commits/rollbacks, cache providers, serialization, transaction boundaries, and Boot configuration. Never assume H2 always behaves identically to PostgreSQL.

**Layer 4 – web/API security tests:** use `MockMvc` or HTTP clients with the real `SecurityFilterChain` and required dependencies to verify 401/403/200 statuses, filters, and method security end-to-end. Mocking the service is acceptable when testing only controllers, provided separate tests protect service-level rules when those are part of the contract.

**Review assertion quality:** a green test must state **what was actually verified**, not what you hoped happened. "The real service behind the cache proxy called the gateway only once across two queries for the same SKU" is far stronger and more accurate than "mock cache works identically to production."

## 14. Checklist when a bean is mocked in AOP-enabled tests

- [ ] Identified **which** beans are mocked/spied and which run real implementations.
- [ ] Checked Spring/Boot versions and picked matching override annotations (`@MockitoBean` or version-appropriate equivalent).
- [ ] Verified `@Autowired` receives the right bean/qualifier; mocks did not override the wrong dependency.
- [ ] Clarified whether the test verifies **service logic, AOP advisors, real DB, cache provider, or HTTP security**.
- [ ] When testing AOP, calls route through Spring-managed beans/proxies rather than `new`-constructed objects.
- [ ] Transactions: real manager present and commits/rollbacks tested at meaningful boundaries; test rollback not confused with service rollback.
- [ ] Caching: verified cache miss/hit/eviction via both results and call counts, with cache state managed between cases.
- [ ] Security: `@EnableMethodSecurity` enabled where needed, both allowed/denied paths and proper `SecurityContext` tested; web tests run through real filters.
- [ ] Accounted for advisor order, self-invocation, proxy types, `final` methods, and user/tenant-scoped cache keys.
- [ ] Did not treat `AopUtils.isAopProxy`, `Mockito.mockingDetails`, or a mocked `thenReturn` as standalone proof.
- [ ] Executed the exact tests and inspected Gradle/Maven/CI reports before claiming verification on the real system.

## 15. Official references

- Spring Framework – [`@MockitoBean` and `@MockitoSpyBean`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): replacing/wrapping beans in Spring TestContext.
- Spring Framework – [Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction interceptors and AOP proxies.
- Spring Framework – [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy modes, method visibility, and self-invocation.
- Spring Security – [Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and advisors.

**Conclusion:** when replacing beans with mocks in Spring Boot tests, **the proxy call path and the replacement scope** determine what a test actually proves. To verify transactions, caching, or method security on a service, prefer **keeping the service real and Spring-injected while mocking downstream dependencies**, enabling the necessary infrastructure, and asserting boundary effects. Controller tests with mocked services remain valuable for isolating controllers, yet never serve as evidence of service-level AOP behavior. Confirming DB commits/rollbacks, Redis caching, or live HTTP security requires dedicated integration tests with matching infrastructure and configuration.
