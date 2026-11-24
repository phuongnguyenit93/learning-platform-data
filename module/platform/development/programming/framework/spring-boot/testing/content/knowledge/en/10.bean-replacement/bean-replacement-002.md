# `@MockitoBean`, `@MockitoSpyBean`, and Supported Spring Framework Versions

When writing tests for Spring Boot, we often want to load part of a **real Spring ApplicationContext** while replacing a dependency with a controllable Mockito object. For example, a pricing service runs as a real bean while an external catalog over HTTP is replaced by a mock so the test avoids network calls. In other cases, we want to **preserve the real logic** of a bean while observing calls or overriding a specific behavior with a spy.

The Spring TestContext Framework provides two annotations for **bean replacement in a test context**:

- **`@MockitoBean`**: registers a **Mockito mock** in the Spring ApplicationContext, replacing the selected bean or (by default) creating a new mock bean if none exists.
- **`@MockitoSpyBean`**: **wraps an existing real bean** in a Mockito spy; real behavior executes by default unless specific calls are stubbed.

These two annotations belong to **Spring Framework 6.2 and later**; they are neither aliases for Mockito's `@Mock`/`@Spy` nor in the same package as Spring Boot's legacy `@MockBean`/`@SpyBean`. This lesson covers exact versions and imports, bean selection, `REPLACE_OR_CREATE` and `WRAP` strategies, runnable Java 17+ JUnit Jupiter examples, migration, and common pitfalls.

## 1. Distinguishing plain Mockito from Spring bean overrides

There are three ways to create test doubles, each serving a different scope:

| Tool | Where is the object created/managed? | When should it be used? |
|---|---|---|
| `Mockito.mock(Catalog.class)` or `@Mock` | Plain test/JUnit/Mockito; **does not replace Spring beans** | Unit tests instantiating services via `new`, with no context needed |
| `@MockitoBean` | Spring TestContext **replaces or registers a bean in ApplicationContext** with a mock | Slice/integration-style tests needing real services/controllers while controlling collaborators |
| `@MockitoSpyBean` | Spring TestContext **wraps a real bean in ApplicationContext** with a spy | Preserving real behavior while observing invocations or stubbing selectively |

For instance, Mockito's `@Mock PriceCatalog catalog;` **does not automatically cause `@Autowired OrderService` to receive that mock**. If Spring wired `OrderService` with another catalog bean, stubbing the `@Mock` field has no effect on `OrderService`. `@MockitoBean` modifies the test context's bean configuration so other beans are injected with the overridden dependency.

Conversely, if a test only verifies pure Java logic and you can construct `new OrderService(mockCatalog)` directly, prefer plain Mockito/JUnit: it runs faster, has clearer boundaries, and avoids `@SpringBootTest`.

## 2. Which versions support them?

**The Spring Framework milestone is 6.2.** Exact annotation names and imports:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
```

Do not confuse them with the legacy annotations:

```java
// Legacy Spring Boot API, not Spring Framework 6.2 annotations:
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;
```

Version orientation across common release lines:

| Library line | Status |
|---|---|
| **Spring Framework 6.0 / 6.1** | Lacks `org.springframework.test.context.bean.override.mockito.MockitoBean` and `MockitoSpyBean`. Using them requires upgrading Spring Framework to a compatible version—not just changing imports. |
| **Spring Framework 6.2.x** | **Provides** both annotations in `spring-test`. **Field-level** usage is the illustrative style compatible with 6.2.0. |
| **Spring Framework 7.0.x** | **Continues supporting** TestContext's Mockito bean override mechanism. Certain detailed behaviors may differ from 6.2; check the docs for your exact version. |
| **Typical Spring Boot 3.0–3.3** | Manages Spring Framework earlier than 6.2. Usually relies on Boot's `@MockBean`/`@SpyBean` or plain Mockito tests. |
| **Spring Boot 3.4 / 3.5** | Typically manages Spring Framework 6.2, allowing migration to `@MockitoBean` / `@MockitoSpyBean`. Boot's `@MockBean` and `@SpyBean` are **deprecated as of 3.4.0** and scheduled for removal in Boot 4.0. |
| **Spring Boot 4.0** | Spring Boot **removes** legacy `@MockBean`/`@SpyBean` and uses Spring Framework's bean override annotations. Boot 4 aligns with Spring Framework 7 and compatible dependencies. |

Do not infer versions just from seeing `org.springframework.boot` packages in source code. Inspect the **actual dependency tree** of your module. In projects with Maven/Gradle Wrappers, reference commands are:

```bash
# Maven: check the actual Spring Framework test dependency resolved
./mvnw dependency:tree -Dincludes=org.springframework:spring-test

# Gradle: inspect the dependency on the test runtime classpath
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
```

These are build-tool commands, not commands for running a standalone Java file; in multi-module builds, target the appropriate module. If compilation fails with `package org.springframework.test.context.bean.override.mockito does not exist`, first verify the module has `spring-test` **6.2+** rather than inventing imports or forcing an individual version that conflicts with the Spring Boot BOM.

**Patch-level compatibility note:** **Spring Framework 6.2.0** Javadoc introduced `@MockitoBean`/`@MockitoSpyBean` on **fields**. Later 6.2 reference documentation also describes **type-level** configuration with `types` and meta-annotations; before using extended features, verify the exact API of your **installed 6.2.x version** instead of assuming the initial patch includes every later attribute. The runnable examples in this lesson intentionally use **field-level annotations**.

## 3. Override mechanics: why mocks differ fundamentally from spies

### `@MockitoBean` — REPLACE_OR_CREATE

By default, Spring TestContext searches for a matching bean and replaces it with a **mock**. If no bean is found, **REPLACE_OR_CREATE** can **create a new mock bean**. While convenient in some slice tests, this carries a hazard: a real bean missing due to wrong imports or config can leave tests passing because a mock was created automatically.

When an **original bean is strictly required**, use:

```java
@MockitoBean(enforceOverride = true)
PriceCatalog catalog;
```

`enforceOverride = true` switches to **REPLACE**: if no bean exists to replace, test context creation fails instead of silently creating a new mock. This snippet represents a **field inside a Spring TestContext test class**, not a standalone program.

Mockito mocks return default values when unstubbed: `0` for numbers, `false` for booleans, and `null` for references depending on type and Mockito defaults. Therefore, **never treat unstubbed mock return values as real business behavior**. When code genuinely needs a product/price returned, stub specific conditions with `when(...).thenReturn(...)`.

### `@MockitoSpyBean` — WRAP

A spy keeps the real bean and wraps it in a Mockito spy. For unstubbed calls, the spy **executes real logic**. This helps verify that a service method ran or override one method in hard-to-build scenarios, while also keeping all side effects present in the real bean.

```java
@MockitoSpyBean
OrderPricingService pricingService;
```

`@MockitoSpyBean` requires **exactly one existing candidate bean**; "create an empty spy if missing" makes no sense. If the bean is absent, multiple unresolved candidates exist, or the bean is unsupported in that version, context initialization fails. Consequently, `@MockitoBean` and `@MockitoSpyBean` **cannot be swapped by simply renaming the annotation**.

| Criterion | `@MockitoBean` | `@MockitoSpyBean` |
|---|---|---|
| Object in context | Mockito mock | Mockito spy wrapping the original bean |
| When unstubbed | Mockito default behavior, **no real logic called** | **Calls real logic** of the bean |
| Strategy | `REPLACE_OR_CREATE`; `enforceOverride=true` enforces `REPLACE` | `WRAP` |
| Original bean missing | Can create a new mock by default | **Fails** because there is no bean to wrap |
| Side effects | Avoids running real behavior of replaced bean | May execute real I/O, state updates, logging, or transactions |
| Primary strength | Isolates collaborators, simulates outputs/errors | Tests real behavior and verifies calls |
| Primary risk | Over-mocking yields passing tests despite wrong results | Incorrect stubbing triggers real logic and side effects |

## 4. Complete Java 17+ and Spring TestContext example

We will build a quoting service. The `OrderPricingService` bean is real code depending on the `PriceCatalog` port. In the mock test, Spring replaces the catalog bean with a mock. In the spy test, Spring wraps the **real service bean** with a spy while keeping the catalog mocked to avoid unnecessary I/O.

File layout:

```text
src/
├── main/java/com/example/shop/pricing/
│   ├── PriceCatalog.java
│   └── OrderPricingService.java
└── test/java/com/example/shop/pricing/
    ├── PricingTestConfig.java
    ├── PriceCatalogMockTest.java
    └── OrderPricingServiceSpyTest.java
```

### 4.1. Production dependency interface

File **`src/main/java/com/example/shop/pricing/PriceCatalog.java`**:

```java
package com.example.shop.pricing;

@FunctionalInterface
public interface PriceCatalog {
    long unitPriceVnd(String sku);
}
```

This is a simple **port**. In a real application, the adapter might query a DB or call a catalog API. In the tests below, no real remote service is needed.

### 4.2. Service under test

File **`src/main/java/com/example/shop/pricing/OrderPricingService.java`**:

```java
package com.example.shop.pricing;

import java.util.Objects;

public class OrderPricingService {
    private final PriceCatalog catalog;

    public record Quote(String sku, int quantity, long totalVnd) {
    }

    public OrderPricingService(PriceCatalog catalog) {
        this.catalog = Objects.requireNonNull(catalog, "catalog");
    }

    public Quote quote(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        long unitPrice = catalog.unitPriceVnd(sku);
        if (unitPrice < 0) {
            throw new IllegalStateException("negative price from catalog");
        }
        long total = Math.multiplyExact(unitPrice, quantity);
        return new Quote(sku, quantity, total);
    }
}
```

The service validates inputs before calling the catalog, computes the total using `Math.multiplyExact` to prevent silent integer overflow, and returns a `record` with value-based equality. The example performs no DB writes or HTTP calls; its purpose is demonstrating **a real bean using a dependency replaced with a mock by Spring**.

### 4.3. Small, well-bounded Spring test configuration

File **`src/test/java/com/example/shop/pricing/PricingTestConfig.java`**:

```java
package com.example.shop.pricing;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class PricingTestConfig {
    @Bean
    PriceCatalog priceCatalog() {
        return sku -> 90_000L; // Real bean replaced by a mock in tests.
    }

    @Bean
    OrderPricingService orderPricingService(PriceCatalog catalog) {
        return new OrderPricingService(catalog);
    }
}
```

The configuration defines two singleton beans. `PriceCatalog` is genuinely registered so tests can use `enforceOverride=true` and demonstrate **REPLACE**, rather than accidentally creating a new bean. `OrderPricingService` still obtains `PriceCatalog` via DI; when Spring builds the test context, it applies test bean overrides before injecting the catalog into the service.

### 4.4. Mock a dependency, keep the real service

File **`src/test/java/com/example/shop/pricing/PriceCatalogMockTest.java`**:

```java
package com.example.shop.pricing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(PricingTestConfig.class)
class PriceCatalogMockTest {
    @MockitoBean(enforceOverride = true)
    PriceCatalog catalog;

    @Autowired
    OrderPricingService pricingService;

    @Test
    void returnsQuoteUsingTheMockedCatalog() {
        when(catalog.unitPriceVnd("BOOK-1")).thenReturn(125_000L);

        OrderPricingService.Quote quote =
                pricingService.quote("BOOK-1", 2);

        assertEquals(new OrderPricingService.Quote(
                "BOOK-1", 2, 250_000L), quote);
        verify(catalog).unitPriceVnd("BOOK-1");
    }

    @Test
    void invalidQuantityDoesNotCallTheCatalog() {
        assertThrows(IllegalArgumentException.class,
                () -> pricingService.quote("BOOK-1", 0));
        verifyNoInteractions(catalog);
    }
}
```

Both assertions serve distinct purposes: the first verifies the real service bean computes the result using the price from the **mock bean**; the second verifies invalid input does not trigger a dependency call. If a plain `@Mock PriceCatalog catalog` were placed on the class while still autowiring the service from the context, the test could end up stubbing a **different object** from the dependency used by the service.

### 4.5. Spy a real bean, observe and stub selectively

File **`src/test/java/com/example/shop/pricing/OrderPricingServiceSpyTest.java`**:

```java
package com.example.shop.pricing;

import org.junit.jupiter.api.Test;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(PricingTestConfig.class)
class OrderPricingServiceSpyTest {
    @MockitoBean(enforceOverride = true)
    PriceCatalog catalog;

    @MockitoSpyBean
    OrderPricingService pricingService;

    @Test
    void spyCallsTheRealMethodByDefault() {
        when(catalog.unitPriceVnd("BOOK-1")).thenReturn(125_000L);

        OrderPricingService.Quote quote =
                pricingService.quote("BOOK-1", 2);

        assertEquals(new OrderPricingService.Quote(
                "BOOK-1", 2, 250_000L), quote);
        verify(pricingService).quote("BOOK-1", 2);
        verify(catalog).unitPriceVnd("BOOK-1");
    }

    @Test
    void doReturnStubsSpyWithoutCallingTheRealMethod() {
        OrderPricingService.Quote controlled =
                new OrderPricingService.Quote("BOOK-2", 1, 999L);

        doReturn(controlled).when(pricingService).quote("BOOK-2", 1);

        assertEquals(controlled, pricingService.quote("BOOK-2", 1));
        verify(pricingService).quote("BOOK-2", 1);
        verifyNoInteractions(catalog);
    }
}
```

In the first test, the spy executes real logic and allows verifying calls on both the service and the mock catalog. In the second test, `doReturn(...).when(spy)...` stubs the spy method directly **without calling real logic while setting up the stub**; the 999 VND result is purely an intentional value demonstrating the spy mechanism, not a production business rule. `verifyNoInteractions(catalog)` confirms the real method did not run unexpectedly in that case.

**Why avoid `when(pricingService.quote(...)).thenReturn(...)` on a spy?** Mockito must evaluate `pricingService.quote(...)` while building the stub; that can invoke real logic before `thenReturn` applies, causing I/O, data mutation, or errors from unstubbed dependencies. On spies, prefer `doReturn`, `doThrow`, and `doNothing` when you want to avoid calling the real method during stubbing.

### 4.6. Results and run commands

The five files above form a **source-complete Java 17+ example**, requiring Spring Framework `spring-test` **6.2+**, Spring Context, JUnit Jupiter/Platform, and Mockito on the test classpath. A Spring Boot 3.4+ or 4.x project with `spring-boot-starter-test` and compatible versions typically supplies these dependencies. No `@SpringBootTest`, web server, or DB is needed; `@SpringJUnitConfig` loads a compact context with just the example's two beans.

In a module with Maven Wrapper:

```bash
./mvnw -Dtest=PriceCatalogMockTest,OrderPricingServiceSpyTest test
```

Or Gradle Wrapper with the `test` task configured for JUnit Platform:

```bash
./gradlew test --tests "com.example.shop.pricing.PriceCatalogMockTest" --tests "com.example.shop.pricing.OrderPricingServiceSpyTest"
```

On Windows, use `mvnw.cmd` or `gradlew.bat`; run only the command matching your project's build tool. With the exact classes and config above, **4 test methods are expected to PASS, 0 FAIL**. There is no fixed business stdout: JUnit/Surefire/Gradle reporting may vary by plugin version.

**Scope of proof:** the tests verify the bean override mechanism and `OrderPricingService` logic within a **Spring test context**. They do not prove that an external network catalog adapter works, real transactions are safe, or full application configuration runs. Those questions require corresponding integration/contract tests.

## 5. Selecting beans: type, name, and qualifier

By default, Spring searches for a bean by the **type of the annotated field**. If only one `PriceCatalog` exists, `@MockitoBean PriceCatalog catalog` identifies the bean without a name. If **two beans share the same type**, selection by type can be ambiguous; use `@Qualifier` or explicit `name`.

Illustrative example, assuming the context has a bean named `primaryCatalog`:

```java
@MockitoBean(name = "primaryCatalog", enforceOverride = true)
PriceCatalog catalog;
```

Or:

```java
@MockitoBean(enforceOverride = true)
@Qualifier("primaryCatalog")
PriceCatalog catalog;
```

You need `import org.springframework.beans.factory.annotation.Qualifier` for the second form. These are **field snippets** replacing the mock field in the test, not standalone Java files. `name` targets a specific bean; `@Qualifier` helps disambiguate candidates when multiple compatible beans exist.

If `@Qualifier` is omitted, the **field name** may be used as a fallback qualifier. This leads to an easily overlooked detail: **field names and qualifiers form part of how Spring TestContext computes context cache keys**. Two tests mocking the same bean with different field names can unnecessarily spin up separate contexts. Across multiple test classes sharing configuration, name mock fields consistently to maximize context reuse.

When using class-level annotations in patch versions that support them, you may see syntax like:

```java
@MockitoBean(types = {PaymentGateway.class, EmailClient.class})
class PaymentFlowTest {
    // Test methods...
}
```

This snippet **only illustrates Spring Framework versions that support class-level `types`** with hypothetical types; **do not treat it as guaranteed API on Spring Framework 6.2.0**. When specifying `name` at the type level, there must be exactly one entry in `types` matching that bean according to API rules. Composed meta-annotations can reuse multiple mocks where supported, but avoid turning every test into an overly broad context.

## 6. Scopes, AOP proxies, FactoryBeans, and context hierarchies

### Bean scopes

**Early Spring Framework 6.2** only supported Mockito bean overrides on **singletons**; attempting to override prototype/request/session-scoped beans can cause test context creation to fail. Subsequent Framework lines/versions changed how non-singletons are handled, so do not infer scope behavior for a different project version from the latest docs. In the example, both beans are singletons, avoiding this issue.

Check the documentation for your **pinned version** if you must mock/spy non-singleton beans or scoped proxies. In particular, turning a prototype into a singleton mock (even if allowed by a version) also **alters scope semantics**, meaning test results no longer prove how production handles multiple instances.

### Spring AOP and proxies

A mock bean replaced by `@MockitoBean` is not the original bean executing logic; tests should not use such mocks to prove `@Transactional`, `@Cacheable`, or `@Retryable` on the real bean. When wrapping with a spy, interactions with AOP proxies can get tricky: Spring's proxy might wrap the spy or affect verification/stubbing. Verify whether the verified object is the proxy or target, and when genuinely testing transactions/caching, prefer integration tests with the relevant infrastructure.

### Beans created by `FactoryBean`

With `@MockitoBean`, overriding the product of a `FactoryBean` allows Spring to replace the definition with a mock of **the type produced by the factory**. With `@MockitoSpyBean`, the spy targets the **object created by the factory**, not necessarily the `FactoryBean` itself. This detail matters when testing beans produced through factories or auto-configuration.

### `@ContextHierarchy`

If a test uses multiple parent/child `ApplicationContext`s, Mockito bean overrides may apply **across multiple levels** by default, causing missing-bean errors or unintended overrides. Use `contextName` matching the `@ContextConfiguration` level name you want to target:

```java
@MockitoBean(contextName = "app-config")
PriceCatalog catalog;
```

This is a field snippet for a test actually using `@ContextHierarchy` with an `app-config` context level. Do not add `contextName` when there is only a single standard context.

## 7. Mockito reset, isolation, and context cache

Spring TestContext resets mocks/spies according to lifecycle rules. In common versions of `@MockitoBean`/`@MockitoSpyBean`, `reset` defaults to **`MockReset.AFTER`**, meaning Mockito interactions/stubbings are reset after each test method. You can select another mode via the `reset` attribute when justified, though mock state should not be shared between tests.

**Note three distinct kinds of state:**

1. **Mockito state**: recorded calls and stubs; reset clears this metadata.
2. **Spring ApplicationContext**: can be cached and reused across test classes with equivalent configurations; context caching does not reset a database.
3. **Real state inside a spied bean**: Mockito reset **does not undo real side effects** that occurred, does not roll back a DB, does not revert file/network I/O, and does not automatically reset mutable fields on target beans.

Accordingly, when spying on a stateful service or one performing I/O, tests need proper fixtures/cleanup. Under parallel test execution, consider shared contexts, mock state, and race conditions; resetting a mock in one test can affect another test running concurrently against the same mock. Do not reach casually for `@DirtiesContext` just to "clear Mockito history," as it defeats context caching and increases runtime.

## 8. Migrating from Spring Boot `@MockBean`/`@SpyBean`

Example in legacy Spring Boot:

```java
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;

// Field in test:
@MockBean
PriceCatalog catalog;

@SpyBean
OrderPricingService pricingService;
```

With Spring Framework 6.2+ and supporting Boot versions, the new style is:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

// Field in test:
@MockitoBean
PriceCatalog catalog;

@MockitoSpyBean
OrderPricingService pricingService;
```

These snippets only illustrate **imports/fields in a test class**, not a standalone Java program. In Spring Boot 3.4/3.5, the legacy API is deprecated; in Boot 4.0, it **has been removed**. Not every project can get by with a mechanical swap of two imports: check the Framework version, bean selection, scopes, whether spied classes actually have a real bean to wrap, tests placing legacy annotations on **`@Configuration` classes**, and legacy attributes lacking 1:1 mappings in the new API.

**Important migration note:** the new Framework annotations apply on **test fields or test types** as supported by the version; **do not place `@MockitoBean` on a field inside a `@Configuration` class assuming it mirrors legacy `@MockBean`**. To reuse mock setups, consider a version-appropriate meta-annotation or an explicit `@TestConfiguration`/`@Bean`.

Recommended upgrade workflow:

1. Check the actual `spring-test` version resolved; avoid manually bumping a single artifact incompatibly with the Spring Boot BOM.
2. Switch imports to `org.springframework.test.context.bean.override.mockito` in tests using a Spring context.
3. For beans that **must exist for real**, enable `enforceOverride=true` to expose missing-bean configuration bugs.
4. Audit tests with **multiple candidates of the same type**, specific bean names, and `@Qualifier`; standardize field names to avoid breaking cache keys.
5. For spies, verify a real bean exists and choose `doReturn`/`doThrow` when real methods must not run during stubbing.
6. Run tests at class, suite, and CI levels; confirm the **right** beans are replaced and verifications operate on the objects used by services/controllers.
7. Only after tests pass and assertions remain valid, remove legacy Boot API usage; never treat successful compilation alone as proof that behavior remained intact.

## 9. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| `Cannot resolve symbol MockitoBean` | `spring-test` below 6.2 or wrong package import | Check dependency tree, use Framework's import, pick compatible versions |
| Context still loads real client when mock expected | Used plain Mockito `@Mock` rather than bean override | Use `@MockitoBean` on a Spring test class with `SpringExtension` registered |
| Test passes even though bean to mock does not exist | `@MockitoBean` defaults to **create** a new mock if missing | Use `enforceOverride=true` when replacing a real bean is required |
| `@MockitoSpyBean` fails during bootstrap | Missing original bean, multiple candidates, or incompatible scope | Load proper config, specify `name`/`@Qualifier`, check scope and version |
| Spy accidentally calls DB/HTTP when declaring stub | `when(spy.realMethod())` can execute real method | Use `doReturn(...).when(spy)...` or `doThrow(...).when(spy)...` |
| `verify(mock)` sees no calls | Injected bean is not the stubbed mock, or code skipped that branch | Verify override is in the service's context, check qualifiers and test config |
| Several test classes restart contexts repeatedly | Differing field names/qualifiers change cache keys | Use consistent mock naming and configuration |
| Spy runs real code and leaks state across tests | Spy wraps stateful bean; Mockito reset does not restore business state | Use proper fixtures and cleanup; avoid spying mutable singletons |
| Spy verification becomes confusing with transaction/cache proxies | Spring AOP wraps the spied object | Understand proxy layering; use proper integration tests for AOP |
| Boot 4 upgrade fails importing `MockBean` | Legacy Boot API removed | Migrate to `@MockitoBean`/`@MockitoSpyBean` and check behavioral differences |
| Mock inside `@Configuration` ignored by Framework | New annotation does not support legacy config-field pattern | Place annotation on test class or use a version-compatible composed annotation |
| Test needs real DB but mocks repository | Override eliminates the boundary being verified | Separate unit/slice tests from real integration tests; do not mock core dependencies |

## 10. Pre-use and pre-upgrade checklist

- [ ] I confirmed the test uses Spring Framework **6.2+** or a newer version providing the annotations.
- [ ] Imports are `org.springframework.test.context.bean.override.mockito.MockitoBean` / `MockitoSpyBean`.
- [ ] I use **plain JUnit/Mockito** when a Spring context is unnecessary.
- [ ] When using `@MockitoBean`, I explicitly decided whether **`enforceOverride=true`** is needed or creation is allowed.
- [ ] When using `@MockitoSpyBean`, **exactly one original bean candidate** exists and real side effects are controlled.
- [ ] With multiple beans of the same type, I use explicit and consistent `name` or qualifiers.
- [ ] I accounted for scopes, AOP proxies, `FactoryBean`, and context hierarchies if present.
- [ ] I understand how `doReturn` differs from `when` on spies; no unintended real method calls occur during stubbing.
- [ ] Mocks/spies reset according to lifecycle, while real state in beans/DBs is still cleaned up.
- [ ] Tests assert **outputs and interactions** fitting the goal, not merely `assertNotNull`.
- [ ] Before moving to Boot 4, I audited and removed legacy `@MockBean`/`@SpyBean` usage.
- [ ] I ran tests with Maven/Gradle on the project's actual Spring/JUnit/Mockito versions.

**Conclusion:** use `@MockitoBean` to **replace a Spring bean with a mock** and `@MockitoSpyBean` to **wrap a real bean with a spy** inside the test ApplicationContext. The minimum version threshold is **Spring Framework 6.2**; when migrating from Spring Boot 3.4/3.5 to Boot 4, update the legacy annotations while also auditing **bean selection, scopes, proxies, and real behavior** rather than merely swapping imports.

### Official documentation by version

- [Spring Framework 6.2 — `@MockitoBean` and `@MockitoSpyBean`](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Framework 6.2.0 — Javadoc `@MockitoBean`](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html)
- [Spring Framework 6.2.0 — Javadoc `@MockitoSpyBean`](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoSpyBean.html)
- [Spring Boot 3.4 — deprecated `@MockBean`](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/MockBean.html)
- [Spring Boot 4.0 — Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
